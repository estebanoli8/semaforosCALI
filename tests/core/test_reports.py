"""Consolidación con PostgreSQL real; inferencia sintética, nunca ciudadanos reales."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile
from fastapi.testclient import TestClient
from semaforos.api import create_app
from semaforos.config import load_config
from semaforos.findings import clean_quote,index_run,index_pending
from semaforos.ingest import import_zip
from semaforos.store import Store
from semaforos.worker import once


class QuoteTests(unittest.TestCase):
    def test_clean_quote_changes_only_presentation(self):
        original='Apagado <attached: foto.jpg> desde ayer.'
        self.assertEqual(clean_quote(original),'Apagado  desde ayer.')
        self.assertIn('<attached:',original)


@unittest.skipUnless(os.getenv('SC_TEST_DSN'),'PostgreSQL de CI requerido')
class ReportTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(os.environ['SC_TEST_DSN'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT current_database() AS n').fetchone()['n'],'semaforos_test')
            c.execute('DROP SCHEMA IF EXISTS semaforos CASCADE')
        self.store.migrate();self.config=load_config()
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'SC_RESERVE_BYTES':'0'});self.env.start()
        self.client=TestClient(create_app(self.store,self.root,self.config,'x'*32))
        self.auth={'Authorization':'Bearer '+'x'*32}
        path=self.root/'Vecina sintética.zip'
        with zipfile.ZipFile(path,'w') as z:z.writestr('_chat.txt','[01/11/26, 10:00] Vecina: Quinta con 5, apagado.\n[02/11/26, 11:00] Vecina: Carrera 70, intermitente.\n')
        self.imported=import_zip(self.store,self.root,path,self.config,'A');self.cid=self.imported['conversation_id']
        once(self.store,self.root,runner=self.infer)
        self.findings=self.client.get('/findings?conversation_id='+self.cid,headers=self.auth).json()['items']

    def tearDown(self):self.client.close();self.env.stop();self.temp.cleanup()

    @staticmethod
    def infer(store,c,job,root):
        items=[]
        for source in job['payload']['sources']:
            for quote,var in [('Quinta con 5','ubicacion'),('apagado','descripcion_dano'),('Carrera 70','ubicacion'),('intermitente','descripcion_dano')]:
                if quote in source['text']:items.append({'source_id':source['id'],'variable':var,'literal':quote,'interpretation':None})
        return {'result':{'extraction':{'assertions':items,'summary':'Ejemplo sintético'},'sources':job['payload']['sources']},'metrics':{},'model_identity':{'test_double':True}}

    def selected(self,quotes):return [f['id'] for f in self.findings if f['literal'] in quotes]

    def create(self,ids=None):
        ids=ids or self.selected(['Quinta con 5','apagado'])
        data={'request_id':str(uuid4()),'action':'create','finding_ids':ids,'primary_finding_id':ids[0],'reviewer':'Equipo de prueba','reason':'Primer hecho, un cruce identificado'}
        response=self.client.post('/reports',headers=self.auth,json=data)
        self.assertEqual(response.status_code,200,response.text)
        return response.json(),data

    def test_indexes_do_not_make_one_report_per_message(self):
        self.assertEqual(len(self.findings),4)
        self.assertEqual(self.client.get('/reports',headers=self.auth).json()['total'],0)
        report,_=self.create()
        data=self.client.get('/reports/'+report['id'],headers=self.auth).json()
        self.assertEqual(len(data['fields']),8)
        self.assertEqual(data['fields']['ubicacion_semaforo_texto'][0]['literal'],'Quinta con 5')
        self.assertEqual(data['fields']['ubicacion_semaforo_audio'],[])
        self.assertEqual(data['revision'],'pendiente')
        self.assertTrue(data['report_date'].startswith('2026-11-01T15:00:00'))
        self.assertNotIn('duracion_calculada',data)

    def test_repeated_inference_reuses_findings_preserving_predictions(self):
        eid=self.imported['evidence_ids'][0]
        response=self.client.post('/jobs',headers=self.auth,json={'evidence_id':eid,'experiment_id':'B'})
        self.assertEqual(response.status_code,200,response.text)
        once(self.store,self.root,runner=self.infer)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM findings').fetchone()['n'],4)
            self.assertEqual(c.execute('SELECT count(*) AS n FROM finding_predictions').fetchone()['n'],8)
            for row in c.execute('SELECT run_id FROM finding_indexes').fetchall():index_run(self.store,row['run_id'])

    def test_create_is_idempotent_and_duplicate_group_is_rejected(self):
        report,payload=self.create()
        again=self.client.post('/reports',headers=self.auth,json=payload)
        self.assertEqual(again.json(),report)
        payload['request_id']=str(uuid4())
        response=self.client.post('/reports',headers=self.auth,json=payload)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['detail'],'same_sources_already_grouped')
        self.assertEqual(self.client.get('/reports',headers=self.auth).json()['total'],1)

    def test_two_crossings_can_be_split_without_deleting_predictions(self):
        one,_=self.create(self.selected(['Quinta con 5','apagado']))
        two,_=self.create(self.selected(['Carrera 70','intermitente']))
        self.assertNotEqual(one['id'],two['id'])
        self.assertEqual(self.client.get('/reports',headers=self.auth).json()['active'],2)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) AS n FROM findings').fetchone()['n'],4)

    def test_review_attach_reopens_and_stale_edit_is_rejected(self):
        ids=self.selected(['Quinta con 5']);report,_=self.create(ids)
        change={'request_id':str(uuid4()),'action':'review','revision':'revisado','expected_version':1,'reviewer':'Revisor','reason':'Cotejado con mensaje original'}
        path='/reports/'+report['id']+'/changes'
        response=self.client.post(path,headers=self.auth,json=change)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['version'],2)
        attach={'request_id':str(uuid4()),'action':'attach','finding_ids':self.selected(['apagado']),'expected_version':2,'reviewer':'Revisor','reason':'Complemento del mismo hecho'}
        response=self.client.post(path,headers=self.auth,json=attach)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['revision'],'pendiente')
        stale=dict(attach,request_id=str(uuid4()))
        self.assertEqual(self.client.post(path,headers=self.auth,json=stale).status_code,409)
        history=self.client.get('/reports/'+report['id']+'/history',headers=self.auth).json()
        self.assertEqual(history['total'],3)
        self.assertEqual(len(history['items'][-1]['snapshot']['findings']),1)
        self.assertEqual(len(history['items'][0]['snapshot']['findings']),2)

    def test_discard_changes_count_but_keeps_sources_and_history(self):
        report,_=self.create()
        data={'request_id':str(uuid4()),'action':'review','revision':'descartado','expected_version':1,'reviewer':'Revisor','reason':'Agrupación equivocada'}
        response=self.client.post('/reports/'+report['id']+'/changes',headers=self.auth,json=data)
        self.assertEqual(response.status_code,200,response.text)
        result=self.client.get('/reports',headers=self.auth).json()
        self.assertEqual(result['total'],1);self.assertEqual(result['active'],0)
        self.assertEqual(len(self.client.get('/findings?conversation_id='+self.cid+'&unassigned=true',headers=self.auth).json()['items']),4)

    def test_replace_preserves_previous_snapshot_and_requires_primary(self):
        report,_=self.create();ids=self.selected(['Carrera 70','intermitente'])
        data={'request_id':str(uuid4()),'action':'replace','finding_ids':ids,'primary_finding_id':ids[0],'expected_version':1,'reviewer':'Revisor','reason':'Corregir agrupación equivocada'}
        response=self.client.post('/reports/'+report['id']+'/changes',headers=self.auth,json=data)
        self.assertEqual(response.status_code,200,response.text)
        history=self.client.get('/reports/'+report['id']+'/history',headers=self.auth).json()
        self.assertEqual(history['items'][0]['snapshot']['fields']['ubicacion_semaforo_texto'][0]['literal'],'Carrera 70')
        self.assertEqual(history['items'][1]['snapshot']['fields']['ubicacion_semaforo_texto'][0]['literal'],'Quinta con 5')

    def test_private_routes_and_original_download(self):
        report,_=self.create()
        for path in ['/conversations','/findings?conversation_id='+self.cid,'/reports','/reports/'+report['id'],'/reports/'+report['id']+'/history','/evidence/'+self.imported['evidence_ids'][0]+'/download']:
            self.assertEqual(self.client.get(path).status_code,401,path)
        r=self.client.get('/evidence/'+self.imported['evidence_ids'][0]+'/download',headers=self.auth)
        self.assertEqual(r.status_code,200);self.assertIn('attachment',r.headers['content-disposition'])
        self.assertIn('Vecina',r.text)

    def test_forged_source_text_never_becomes_a_finding(self):
        eid=self.imported['evidence_ids'][0]
        self.store.enqueue(eid,'text','forged',self.config,{'sources':[{'id':'forged','source_id':eid,'origin':'chat','char_start':0,'text':'inventado'}]})
        def forged(*a):return {'result':{'assertions':[{'source_id':'forged','variable':'ubicacion','literal':'inventado'}]},'metrics':{},'model_identity':{}}
        once(self.store,self.root,runner=forged)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM findings').fetchone()['n'],4)
            self.assertEqual(c.execute("SELECT count(*) AS n FROM finding_indexes WHERE state='error'").fetchone()['n'],1)

    def test_later_processing_flags_old_review_as_outdated(self):
        report,_=self.create()
        self.client.post('/reports/'+report['id']+'/changes',headers=self.auth,json={'request_id':str(uuid4()),'action':'review','revision':'revisado','expected_version':1,'reviewer':'Equipo','reason':'Cotejado'})
        self.client.post('/jobs',headers=self.auth,json={'evidence_id':self.imported['evidence_ids'][0],'experiment_id':'new-model'})
        data=self.client.get('/reports/'+report['id'],headers=self.auth).json()
        self.assertTrue(data['review_outdated']);self.assertEqual(data['revision_effective'],'pendiente')
        self.assertEqual(data['revision'],'revisado')

    def test_audio_findings_use_transcript_and_only_explicit_message_date(self):
        path=self.root/'Audio sintético.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('_chat.txt','[03/11/26, 08:00] Vecina: <attached: nota.opus>\n')
            z.writestr('nota.opus',b'synthetic audio')
        imported=import_zip(self.store,self.root,path,self.config,'audio')
        def infer(store,c,job,root):
            if job['stage']=='audio':return {'result':{'text':'Quinta con 5, apagado.','segments':[],'language':'es'},'metrics':{},'model_identity':{'test_double':True}}
            return self.infer(store,c,job,root)
        for _ in range(5):
            if not once(self.store,self.root,runner=infer):break
        findings=self.client.get('/findings?conversation_id='+imported['conversation_id'],headers=self.auth).json()['items']
        self.assertEqual(len(findings),2)
        for f in findings:
            self.assertEqual(f['origin'],'audio_whatsapp');self.assertIsNotNone(f['transcript_id'])
            self.assertIsNotNone(f['message_id']);self.assertTrue(f['sent_at'].startswith('2026-11-03T13:00:00'))
        ids=[f['id'] for f in findings];report,_=self.create(ids)
        data=self.client.get('/reports/'+report['id'],headers=self.auth).json()
        self.assertEqual(data['fields']['ubicacion_semaforo_audio'][0]['literal'],'Quinta con 5')
        self.assertEqual(data['fields']['ubicacion_semaforo_texto'],[])

    def test_cross_conversation_grouping_is_not_silently_accepted(self):
        path=self.root/'Otro chat.zip'
        with zipfile.ZipFile(path,'w') as z:z.writestr('_chat.txt','[05/11/26, 10:00] Otro: Carrera 70, intermitente.\n')
        imported=import_zip(self.store,self.root,path,self.config,'otro');once(self.store,self.root,runner=self.infer)
        other=self.client.get('/findings?conversation_id='+imported['conversation_id'],headers=self.auth).json()['items'][0]['id']
        first=self.findings[0]['id']
        data={'request_id':str(uuid4()),'action':'create','finding_ids':[first,other],'primary_finding_id':first,'reviewer':'Equipo','reason':'No se debe fusionar sin revisar las conversaciones'}
        response=self.client.post('/reports',headers=self.auth,json=data)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['detail'],'cross_conversation_link_requires_review')


if __name__=='__main__':unittest.main()
