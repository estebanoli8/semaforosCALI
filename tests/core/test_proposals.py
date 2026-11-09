import os,unittest,zipfile
from uuid import uuid4
import test_reports
from semaforos.proposals import classify
from semaforos.ingest import import_zip
from semaforos.worker import once

class ClassificationTests(unittest.TestCase):
    def test_ambiguous_or_incomplete_is_not_ready(self):
        fs=[dict(id='1',message_id='m',variable='ubicacion',literal='Quinta'),dict(id='2',message_id='m',variable='ubicacion',literal='Sexta')]
        r=classify(fs);self.assertEqual(r['status'],'requiere_separacion_o_contexto');self.assertIn('ubicacion_ausente_o_multiple',r['reasons'])
    def test_candidate_still_requires_human(self):
        fs=[dict(id='1',message_id='m',variable='ubicacion',literal='Quinta'),dict(id='2',message_id='m',variable='descripcion_dano',literal='apagado')]
        r=classify(fs);self.assertEqual(r['status'],'candidato_revisable');self.assertTrue(r['requires_human_review'])

@unittest.skipUnless(os.getenv('SC_TEST_DSN'),'PostgreSQL de CI requerido')
class ProposalTests(unittest.TestCase):
    setUp=test_reports.ReportTests.setUp
    tearDown=test_reports.ReportTests.tearDown
    infer=staticmethod(test_reports.ReportTests.infer)
    selected=test_reports.ReportTests.selected
    create=test_reports.ReportTests.create
    def get(self,cid):return self.client.get('/report-proposals?conversation_id='+cid,headers=self.auth)
    def test_proposals_do_not_create_reports_and_existing_sources_are_marked(self):
        r=self.get(self.cid);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['total'],2)
        self.assertTrue(all(p['status']=='candidato_revisable' for p in r.json()['items']))
        self.assertEqual(self.client.get('/reports',headers=self.auth).json()['total'],0)
        self.create();self.assertEqual(sum(p['status']=='con_fuentes_ya_agrupadas' for p in self.get(self.cid).json()['items']),1)
    def test_only_confirmed_direct_relation_exposes_possible_repeat(self):
        report,_=self.create()
        path=self.root/'Chat ampliado (2).zip'
        with zipfile.ZipFile(path,'w') as z:z.writestr('_chat.txt','[01/11/26, 10:00] Vecina: Quinta con 5, apagado.\n[03/11/26, 10:00] Vecina: Quinta con 5, apagado.\n')
        imported=import_zip(self.store,self.root,path,self.config,'expanded');once(self.store,self.root,runner=self.infer)
        cid=imported['conversation_id'];self.assertTrue(all(not p['related_reports'] for p in self.get(cid).json()['items']))
        with self.store.connect() as c:
            ids=[str(c.execute('SELECT p.id FROM chat_parses p JOIN evidence e ON e.id=p.evidence_id WHERE e.conversation_id=%s',(x,)).fetchone()['id']) for x in (self.cid,cid)]
        data=dict(request_id=str(uuid4()),left_parse_id=ids[0],right_parse_id=ids[1],expected_version=0,decision='misma_conversacion',reviewer='Equipo',reason='Cotejadas')
        result=self.client.post('/export-relations',headers=self.auth,json=data);self.assertEqual(result.status_code,200,result.text)
        proposals=self.get(cid).json()['items'];related=[p for p in proposals if p['related_reports']]
        self.assertEqual(len(related),1);self.assertEqual(related[0]['related_reports'][0]['id'],report['id'])
        self.assertFalse(related[0]['duplicate_confirmed'])
        self.assertEqual(self.client.get('/reports',headers=self.auth).json()['total'],1)
        data.update(request_id=str(uuid4()),expected_version=1,decision='distintas')
        self.client.post('/export-relations',headers=self.auth,json=data)
        self.assertTrue(all(not p['related_reports'] for p in self.get(cid).json()['items']))
    def test_auth_and_pagination(self):
        self.assertEqual(self.client.get('/report-proposals?conversation_id='+self.cid).status_code,401)
        self.assertEqual(len(self.client.get('/report-proposals?conversation_id='+self.cid+'&limit=1',headers=self.auth).json()['items']),1)
        self.assertEqual(self.client.get('/report-proposals?conversation_id='+self.cid+'&limit=0',headers=self.auth).status_code,400)
