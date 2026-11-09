import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
import zipfile
from semaforos.config import load_config
from semaforos.store import Store,LOCK_KEY
from semaforos.files import sha256
from semaforos.worker import once
from semaforos.ingest import import_zip


@unittest.skipUnless(os.getenv('SC_TEST_DSN'),'Requiere PostgreSQL de pruebas; GitHub Actions lo provisiona')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(os.environ['SC_TEST_DSN'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT current_database() AS n').fetchone()['n'],'semaforos_test')
            c.execute('DROP SCHEMA IF EXISTS semaforos CASCADE')
        self.store.migrate()
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=load_config()
        self.cid=self.store.conversation('synthetic','Conversación ficticia')
        path=self.root/'audio.ogg';path.write_bytes(b'synthetic fixture - not actual audio')
        self.eid=self.store.evidence(self.cid,'audio.ogg','audio','audio.ogg',path.stat().st_size,sha256(path))

    def tearDown(self):self.temp.cleanup()

    def test_migrations_are_repeatable(self):
        self.store.migrate()
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) AS n FROM schema_migrations').fetchone()['n'],3)

    def test_idempotent_jobs_and_new_experiment(self):
        first=self.store.enqueue(self.eid,'audio','A',self.config)
        self.assertEqual(first,self.store.enqueue(self.eid,'audio','A',self.config))
        self.assertNotEqual(first,self.store.enqueue(self.eid,'audio','B',self.config))

    def test_global_lock_prevents_two_heavy_workers(self):
        self.store.enqueue(self.eid,'audio','A',self.config)
        with self.store.connect() as c:
            c.execute('SELECT pg_advisory_lock(%s)',(LOCK_KEY,));c.commit()
            self.assertFalse(once(self.store,self.root,runner=lambda *args: self.fail('No debe ejecutarse')))
            c.execute('SELECT pg_advisory_unlock(%s)',(LOCK_KEY,));c.commit()

    def test_expired_lease_preserves_attempt_history(self):
        ident=self.store.enqueue(self.eid,'audio','A',self.config)
        with self.store.connect() as c:
            old=self.store.claim(c)
            c.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(ident,));c.commit()
            new=self.store.claim(c)
            self.assertEqual(new['id'],old['id']);self.assertNotEqual(new['lease_token'],old['lease_token'])
            self.assertEqual(c.execute('SELECT state FROM runs WHERE id=%s',(old['run_id'],)).fetchone()['state'],'interrupted')
            with self.assertRaises(RuntimeError):self.store.complete(c,old,{})

    def test_audio_followup_and_review_preserve_prediction(self):
        self.store.enqueue(self.eid,'audio','A',self.config)
        def result(*args):
            return {'result':{'text':' El semáforo está apagado.','segments':[{'start':0,'end':2,'text':' El semáforo está apagado.'}],'language':'es'},'metrics':{'wall_seconds':1},'model_identity':{'test_double':True}}
        self.assertTrue(once(self.store,self.root,runner=result))
        with self.store.connect() as c:
            transcript=c.execute('SELECT * FROM transcripts').fetchone()
            self.assertEqual(transcript['literal_text'],' El semáforo está apagado.')
            self.assertEqual(c.execute("SELECT count(*) AS n FROM jobs WHERE stage='text'").fetchone()['n'],1)
        from fastapi.testclient import TestClient
        from semaforos.api import create_app
        client=TestClient(create_app(self.store,self.root,self.config,'x'*32))
        self.assertEqual(client.get('/jobs').status_code,401)
        response=client.post('/reviews',headers={'Authorization':'Bearer '+'x'*32},json={'run_id':str(transcript['run_id']),'field':'transcription','label':'El semáforo estaba apagado.','reviewer':'evaluador_sintetico'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['metrics']['wer'],.25)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT literal_text FROM transcripts').fetchone()['literal_text'],' El semáforo está apagado.')

    def test_failure_retries_then_stops(self):
        config=copy.deepcopy(self.config);config['max_attempts']=1
        self.store.enqueue(self.eid,'audio','A',config)
        def broken(*args):raise ValueError('simulated_failure')
        self.assertTrue(once(self.store,self.root,runner=broken))
        self.assertFalse(once(self.store,self.root,runner=broken))
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT state FROM jobs').fetchone()['state'],'failed')

    def test_zip_literal_content_duplicate_and_path_escape(self):
        path=self.root/'WhatsApp Chat - Ejemplo.zip'
        text='[01/11/26, 10:00:00] Vecino: Quinta con quinta, apagado.\n'
        with zipfile.ZipFile(path,'w') as z:z.writestr('_chat.txt',text)
        from unittest.mock import patch
        with patch.dict(os.environ,{'SC_RESERVE_BYTES':'0'}):
            first=import_zip(self.store,self.root,path,self.config,'A')
            again=import_zip(self.store,self.root,path,self.config,'A')
        self.assertEqual(first,again)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT literal_text FROM source_texts').fetchone()['literal_text'],text)
        bad=self.root/'bad.zip'
        with zipfile.ZipFile(bad,'w') as z:z.writestr('../outside.txt','forbidden')
        with self.assertRaises(ValueError):import_zip(self.store,self.root,bad,self.config,'A')

    def test_message_index_is_versioned_and_links_only_explicit_unique_files(self):
        from semaforos.messages import index_chat,chat_sources
        from unittest.mock import patch
        text='[01/11/26, 10:00] Vecina: <attached: foto.jpg>\r\n[01/11/26, 10:01] Vecina: <attached: repetida.jpg>\r\n[01/11/26, 10:02] Vecina: <attached: ausente.opus>\r\n'
        path=self.root/'Mensajes.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('_chat.txt',text)
            for name in ['foto.jpg','a/repetida.jpg','b/repetida.jpg']:z.writestr(name,b'synthetic image')
        with patch.dict(os.environ,{'SC_RESERVE_BYTES':'0'}):result=import_zip(self.store,self.root,path,self.config,'messages')
        with self.store.connect() as c:
            evidence=c.execute("SELECT id FROM evidence WHERE modality='chat'").fetchone()['id']
            records=c.execute('SELECT * FROM messages ORDER BY ordinal').fetchall()
            links=c.execute('SELECT filename_literal,state,evidence_id FROM message_attachments').fetchall()
            self.assertEqual(c.execute('SELECT literal_text FROM source_texts').fetchone()['literal_text'],text)
        self.assertEqual(''.join(r['raw_text'] for r in records),text)
        self.assertEqual({r['filename_literal']:r['state'] for r in links},{'foto.jpg':'linked','repetida.jpg':'ambiguous','ausente.opus':'missing'})
        first=index_chat(self.store,evidence,self.config)
        self.assertEqual(first,index_chat(self.store,evidence,self.config))
        changed=copy.deepcopy(self.config);changed['whatsapp']['date_order']='AUTO'
        second=index_chat(self.store,evidence,changed)
        self.assertNotEqual(first,second)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM chat_parses').fetchone()['n'],2)
            self.assertTrue(all(r['sent_at'] is None for r in c.execute('SELECT sent_at FROM messages WHERE parse_id=%s',(second,))))
        sources=[s for group in chat_sources(self.store,evidence,self.config) for s in group]
        self.assertEqual({s['message_id'] for s in sources},{str(r['id']) for r in records})
        self.assertEqual(''.join(s['text'] for s in sources),text)

    def test_message_api_requires_auth_and_preserves_source_dates(self):
        from fastapi.testclient import TestClient
        from semaforos.api import create_app
        from unittest.mock import patch
        path=self.root/'Ejemplo.zip'
        with zipfile.ZipFile(path,'w') as z:z.writestr('_chat.txt','1/11/2026, 10:00 - Vecino: Lleva tres días apagado.\n')
        with patch.dict(os.environ,{'SC_RESERVE_BYTES':'0'}):result=import_zip(self.store,self.root,path,self.config,'messages')
        client=TestClient(create_app(self.store,self.root,self.config,'x'*32));auth={'Authorization':'Bearer '+'x'*32}
        eid=result['evidence_ids'][0]
        path=f'/evidence/{eid}/chat-parses'
        self.assertEqual(client.get(path).status_code,401)
        parse_id=client.get(path,headers=auth).json()['items'][0]['id']
        path=f'/chat-parses/{parse_id}/messages'
        self.assertEqual(client.get(path).status_code,401)
        data=client.get(path,headers=auth).json()
        self.assertEqual(data['total'],1)
        from datetime import datetime
        self.assertEqual(datetime.fromisoformat(data['items'][0]['sent_at']).isoformat(),'2026-11-01T15:00:00+00:00')
        self.assertEqual(data['items'][0]['body_text'],'Lleva tres días apagado.\n')
        self.assertEqual(client.get(path+'?offset=1',headers=auth).json()['items'],[])
        self.assertEqual(client.get(path+'?limit=1000',headers=auth).status_code,400)
        client.close()
