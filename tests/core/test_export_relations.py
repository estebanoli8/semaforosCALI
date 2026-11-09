import os,tempfile,unittest,zipfile
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from semaforos.api import create_app
from semaforos.store import Store
from semaforos.config import load_config
from semaforos.ingest import import_zip

@unittest.skipUnless(os.getenv('SC_TEST_DSN'),'PostgreSQL de CI requerido')
class ExportRelationTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(os.environ['SC_TEST_DSN'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT current_database() AS n').fetchone()['n'],'semaforos_test')
            c.execute('DROP SCHEMA IF EXISTS semaforos CASCADE')
        self.store.migrate();self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);config=load_config()
        for n in range(2):
            path=root/f'Chat ({n}).zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('_chat.txt','[01/11/26, 10:00] Vecina: Apagado.\n'+('[02/11/26, 10:00] Vecina: Sigue igual.\n' if n else ''))
            import_zip(self.store,root,path,config,'test')
        self.client=TestClient(create_app(self.store,root,config,'x'*32));self.auth={'Authorization':'Bearer '+'x'*32}
        rows=self.client.get('/export-indexes',headers=self.auth).json()['items'];self.ids=[r['id'] for r in rows]
        self.data=dict(request_id=str(uuid4()),left_parse_id=self.ids[0],right_parse_id=self.ids[1],expected_version=0,decision='misma_conversacion',reviewer='Equipo',reason='Cotejo manual')
    def tearDown(self):self.client.close();self.temp.cleanup()
    def test_history_replay_conflict_and_reversal(self):
        r=self.client.post('/export-relations',headers=self.auth,json=self.data);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['version'],1)
        self.assertEqual(self.client.post('/export-relations',headers=self.auth,json=self.data).json(),r.json())
        stale=dict(self.data,request_id=str(uuid4()))
        self.assertEqual(self.client.post('/export-relations',headers=self.auth,json=stale).status_code,409)
        revised=dict(stale,expected_version=1,decision='distintas')
        self.assertEqual(self.client.post('/export-relations',headers=self.auth,json=revised).json()['version'],2)
        q=f'?left_parse_id={self.ids[1]}&right_parse_id={self.ids[0]}'
        h=self.client.get('/export-relations'+q,headers=self.auth).json();self.assertEqual(h['total'],2)
        self.assertEqual(h['items'][1]['decision'],'misma_conversacion')
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM conversations').fetchone()['n'],2)
    def test_private_and_invalid(self):
        self.assertEqual(self.client.get('/export-indexes').status_code,401)
        self.assertEqual(self.client.post('/export-relations',json=self.data).status_code,401)
        invalid=dict(self.data,right_parse_id=self.ids[0]);self.assertEqual(self.client.post('/export-relations',headers=self.auth,json=invalid).status_code,409)
        invalid=dict(self.data,reviewer=' ');self.assertEqual(self.client.post('/export-relations',headers=self.auth,json=invalid).status_code,409)
    def test_compare_and_pagination(self):
        r=self.client.get(f'/conversation-comparison?left_parse_id={self.ids[0]}&right_parse_id={self.ids[1]}',headers=self.auth)
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['shared_occurrences'],1)
        self.assertEqual(len(self.client.get('/export-indexes?limit=1',headers=self.auth).json()['items']),1)
