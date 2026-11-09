"""Integración real en PostgreSQL; inferencia simulada, sin datos ciudadanos."""
import copy
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import zipfile
from uuid import UUID
from fastapi.testclient import TestClient
from semaforos.api import create_app
from semaforos.config import load_config
from semaforos.store import Store
from semaforos.uploads import Uploads, UploadError, CHUNK_BYTES
from semaforos.worker import once
from semaforos.ingest import import_zip


def archive(text='[01/11/26, 10:00:00] Vecino: Quinta con quinta, apagado.\n',unsafe=False):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('../escape.txt' if unsafe else '_chat.txt',text)
    return stream.getvalue()


@unittest.skipUnless(os.getenv('SC_TEST_DSN'),'PostgreSQL de CI requerido')
class UploadTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(os.environ['SC_TEST_DSN'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT current_database() AS n').fetchone()['n'],'semaforos_test')
            c.execute('DROP SCHEMA IF EXISTS semaforos CASCADE')
        self.store.migrate()
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'SC_RESERVE_BYTES':'0'});self.env.start()
        self.config=load_config();self.uploads=Uploads(self.store,self.root)
        self.client=TestClient(create_app(self.store,self.root,self.config,'x'*32))
        self.auth={'Authorization':'Bearer '+'x'*32}

    def tearDown(self):
        self.env.stop();self.client.close();self.temp.cleanup()

    def stage(self,data,name='WhatsApp Chat - Ejemplo (1).zip'):
        row=self.uploads.create(name,len(data),'prueba-web',self.config)
        self.uploads.append(row['id'],0,data,hashlib.sha256(data).hexdigest())
        return self.uploads.finish(row['id'])

    def test_http_auth_boundaries_and_stream_limit(self):
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response.headers['cache-control'])
        self.assertEqual(self.client.get('/panel.js').status_code,200)
        for path in ['/uploads','/jobs','/summary','/health']:
            self.assertEqual(self.client.get(path).status_code,401)
        result=self.client.post('/uploads',headers=self.auth,json={'name':'uno.zip','size':CHUNK_BYTES+1,'experiment_id':'x'})
        self.assertEqual(result.status_code,200,result.text)
        ident=result.json()['id']
        response=self.client.put(f'/uploads/{ident}/chunk?offset=0',headers=self.auth,content=b'x'*(CHUNK_BYTES+1))
        self.assertEqual(response.status_code,413)
        self.assertEqual(self.uploads.get(ident)['received_bytes'],0)
        for name in ['../x.zip','x/uno.zip','x\\uno.zip','no.txt','a\x00.zip']:
            with self.assertRaises(UploadError):self.uploads.create(name,10,'x',self.config)

    def test_chunk_replay_restart_tail_and_content_mismatch(self):
        row=self.uploads.create('uno.zip',6,'x',self.config);ident=row['id']
        self.uploads.append(ident,0,b'abc',hashlib.sha256(b'abc').hexdigest())
        self.assertEqual(self.uploads.append(ident,0,b'abc',hashlib.sha256(b'abc').hexdigest())['received_bytes'],3)
        with self.assertRaises(UploadError):self.uploads.append(ident,0,b'xxx',hashlib.sha256(b'xxx').hexdigest())
        with self.uploads.path(row).open('ab') as f:f.write(b'uncommitted-tail')
        recovered=Uploads(self.store,self.root)
        recovered.append(ident,3,b'def',hashlib.sha256(b'def').hexdigest())
        self.assertEqual(recovered.path(row).read_bytes(),b'abcdef')
        self.assertEqual(recovered.finish(ident)['state'],'queued')
        with self.assertRaises(UploadError):recovered.append(ident,0,b'abc',hashlib.sha256(b'abc').hexdigest())

    def test_parallel_replayed_chunk_is_confirmed_once(self):
        row=self.uploads.create('uno.zip',3,'x',self.config)
        def append(_):return Uploads(self.store,self.root).append(row['id'],0,b'abc',hashlib.sha256(b'abc').hexdigest())
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(append,range(2)))
        self.assertEqual([r['received_bytes'] for r in results],[3,3])
        self.assertEqual(self.uploads.path(row).read_bytes(),b'abc')

    def test_web_to_queue_to_prediction_and_duplicate_zip(self):
        data=archive();r=self.client.post('/uploads',headers=self.auth,json={'name':'Conversación (1).zip','size':len(data),'experiment_id':'prueba-web'})
        ident=r.json()['id']
        h=dict(self.auth,**{'X-Chunk-SHA256':hashlib.sha256(data).hexdigest()})
        self.assertEqual(self.client.put(f'/uploads/{ident}/chunk?offset=0',headers=h,content=data).status_code,200)
        self.assertEqual(self.client.post(f'/uploads/{ident}/finish',headers=self.auth).json()['state'],'queued')
        def infer(store,c,job,root):
            self.assertEqual(job['stage'],'text')
            self.assertEqual(job['payload']['sources'][0]['text'],'[01/11/26, 10:00:00] Vecino: Quinta con quinta, apagado.\n')
            return {'result':{'assertions':[],'summary':'Predicción sintética'},'metrics':{'wall_seconds':1},'model_identity':{'test_double':True}}
        self.assertTrue(once(self.store,self.root,runner=infer))
        uploaded=self.uploads.get(ident)
        self.assertEqual(uploaded['state'],'received')
        self.assertFalse(self.uploads.path(uploaded).exists())
        self.assertEqual(self.client.get('/summary',headers=self.auth).json()['conversations'],1)
        jobs=self.client.get('/jobs',headers=self.auth).json()['items']
        self.assertEqual(jobs[0]['state'],'completed');self.assertIsNotNone(jobs[0]['run_id'])
        self.assertEqual(self.client.get('/runs/'+jobs[0]['run_id'],headers=self.auth).status_code,200)
        self.stage(data,'Conversación (2).zip')
        self.assertTrue(once(self.store,self.root,runner=lambda *a:self.fail('Duplicado no debe inferirse otra vez')))
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM conversations').fetchone()['n'],1)
            self.assertEqual(c.execute('SELECT count(*) AS n FROM jobs').fetchone()['n'],1)
            self.assertEqual(c.execute('SELECT count(*) AS n FROM source_archives').fetchone()['n'],2)
            originals=c.execute('SELECT storage_path FROM source_archives').fetchall()
        for item in originals:self.assertEqual((self.root/item['storage_path']).read_bytes(),data)

    def test_bad_zip_isolated_retry_cancel_and_recovery_after_import(self):
        bad=self.stage(b'not zip','bad.zip');self.assertTrue(once(self.store,self.root))
        self.assertEqual(self.uploads.get(bad['id'])['state'],'error')
        self.assertEqual(self.uploads.retry(bad['id'])['state'],'queued')
        self.assertEqual(self.uploads.cancel(bad['id'])['state'],'cancelled')
        good=self.stage(archive(),'good.zip')
        import_zip(self.store,self.root,self.uploads.path(good),self.config,'prueba-web')
        # Caída después de persistir originales y tareas, antes de confirmar la carga.
        with self.store.connect() as c:c.execute("UPDATE uploads SET state='importing',attempts=1 WHERE id=%s",(good['id'],))
        output={'result':{'assertions':[]},'metrics':{},'model_identity':{'test_double':True}}
        self.assertTrue(once(self.store,self.root,runner=lambda *a:output))
        self.assertEqual(self.uploads.get(good['id'])['state'],'received')
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) AS n FROM jobs').fetchone()['n'],1)

    def test_unsafe_archive_rejected_and_configuration_frozen(self):
        bad=self.stage(archive(unsafe=True),'bad.zip');once(self.store,self.root)
        self.assertEqual(self.uploads.get(bad['id'])['error_code'],'unsafe_zip_path')
        self.assertFalse((self.root/'escape.txt').exists())
        good=self.stage(archive(),'good.zip')
        self.config['text']['model']='changed-after-upload'
        seen=[]
        def infer(store,c,job,root):
            seen.append(job['config']['text']['model'])
            return {'result':{'assertions':[]},'metrics':{},'model_identity':{'test_double':True}}
        once(self.store,self.root,runner=infer)
        self.assertEqual(seen,['qwen3:4b-instruct'])

    def test_disk_reservation_and_pagination(self):
        from collections import namedtuple
        Disk=namedtuple('Disk','total used free')
        with patch('semaforos.uploads.shutil.disk_usage',return_value=Disk(100,0,100)):
            self.uploads.create('one.zip',70,'x',self.config)
            with self.assertRaises(UploadError):self.uploads.create('two.zip',40,'x',self.config)
        for i in range(102):self.uploads.create(f'{i}.zip',1,'x',self.config)
        page=self.client.get('/uploads?offset=100&limit=20',headers=self.auth).json()
        self.assertEqual(page['total'],103);self.assertEqual(len(page['items']),3)
