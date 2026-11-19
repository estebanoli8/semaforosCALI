"""Consolidación con PostgreSQL real; inferencia sintética, nunca ciudadanos reales."""
import copy
import os
import re
from datetime import datetime, timezone
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

    def test_export_filename_uses_colombia_date_at_utc_rollover(self):
        from semaforos.report_pdf import export_filename
        self.assertEqual(export_filename(datetime(2026,11,17,2,34,6,tzinfo=timezone.utc)),
                         'Accion Popular Semaforos Cali NOV 16 2026 21-34-06.pdf')


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

    def test_end_to_end_report_map_public_projection_pdf_and_metrics(self):
        import hashlib
        from semaforos.report_pdf import signature

        boundary_dir=self.root/'cartografia'
        boundary_dir.mkdir()
        (boundary_dir/'cali-urbano.geojson').write_text(
            '{"type":"Polygon","coordinates":[[[-76.60,3.30],[-76.48,3.30],'
            '[-76.48,3.52],[-76.60,3.52],[-76.60,3.30]]]}')
        first,_=self.create()
        second,_=self.create(self.selected(['Carrera 70','intermitente']))
        self.assertEqual(self.client.get('/report-map').status_code,401)
        preliminary=self.client.get('/semaforos/datos').json()
        self.assertEqual(preliminary['conversations_included'],1)
        self.assertGreaterEqual(len(preliminary['items']),2)
        self.assertTrue(all(row['preliminary'] and row['revision']=='pendiente' for row in preliminary['items']))
        self.assertNotIn('Vecina',str(preliminary))
        self.assertEqual(self.client.get('/reports',headers=self.auth).json()['total'],2)
        self.assertEqual(self.client.post('/report-exports',json={}).status_code,401)
        self.assertEqual(self.client.get('/reportes').status_code,200)
        self.assertEqual(self.client.get('/semaforos').status_code,200)
        for report in (first,second):
            data={'expected_report_version':1,'expected_version':0,
                  'latitude':3.43,'longitude':-76.53,'intersection':'Calle 5 con Carrera 70',
                  'public_description':'Falla comunicada por la ciudadanía.',
                  'reviewer':'Revisión sintética','published':True}
            url='/reports/'+report['id']+'/map'
            saved=self.client.put(url,headers=self.auth,json=data)
            self.assertEqual(saved.status_code,200,saved.text)
            self.assertEqual(self.client.put(url,headers=self.auth,json=data).status_code,409)
        cut=self.client.get('/semaforos/datos').json()
        self.assertEqual({x['code'] for x in cut['items']},{first['code'],second['code']})
        self.assertEqual(len(cut['map']['markers']),2)
        self.assertTrue(all(row['reports_at_intersection']==2 for row in cut['items']))
        self.assertTrue(all(row['revision']=='pendiente' for row in cut['items']))
        self.assertTrue(all(set(row)=={'code','date','intersection','description','latitude','longitude',
                                     'processing','revision','reports_at_intersection','map_state',
                                     'evidence_counts','evidence_scope'}
                            for row in cut['items']))
        self.assertNotIn('Vecina',str(cut))
        self.assertEqual(self.client.get('/model-metrics',headers=self.auth).json()['stages'][0]['completed'],1)

        with TestClient(self.client.app,base_url='https://testserver') as https:
            pdf=https.post('/report-exports',headers=self.auth,json={'share_evidence':True})
            self.assertEqual(pdf.status_code,200,pdf.text if pdf.status_code!=200 else None)
            self.assertTrue(pdf.content.startswith(b'%PDF'))
            export_id=pdf.headers['x-report-export-id']
            fetch=https.get('/report-exports/'+export_id,headers=self.auth)
            self.assertEqual(fetch.content,pdf.content)
            with self.store.connect() as c:
                stored=c.execute('SELECT * FROM report_pdf_exports WHERE id=%s',(export_id,)).fetchone()
                self.assertEqual(stored['sha256'],hashlib.sha256(pdf.content).hexdigest())
                self.assertEqual(len(stored['report_versions']),2)
                e=stored['evidence_ids'][0]
                expires=stored['evidence_expires_at']
            proof=signature('x'*32,export_id,e,expires)
            path=f'/informe/evidencia/{export_id}/{e}'
            self.assertEqual(https.get(path).status_code,404)
            self.assertEqual(https.get(path,params={'firma':proof}).status_code,200)
            self.assertEqual(https.get(f'/informe/evidencia/{export_id}/{uuid4()}',params={'firma':proof}).status_code,404)
            with self.store.connect() as c:
                c.execute("UPDATE report_pdf_exports SET evidence_expires_at=now()-interval '1 hour' WHERE id=%s",(export_id,))
            self.assertEqual(https.get(path,params={'firma':proof}).status_code,404)

    def test_automatic_public_results_keep_independent_reports_without_leaking_sources(self):
        for index, text in enumerate((
                'Semáforo apagado en Calle 5 con Carrera 70. WhatsApp 3001234567.',
                'El semáforo en Carrera 70 con Calle 5 está apagado. Soy Reportante Privado.'),1):
            path = self.root / f'WhatsApp privado {index}.zip'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('_chat.txt',f'[30/10/26, 10:00] Remitente privado {index}: {text}')
            import_zip(self.store,self.root,path,self.config,'Publicación de prueba')
            once(self.store,self.root,runner=self.infer)
        data=self.client.get('/semaforos/datos').json()
        self.assertEqual(data['conversations_included'],3)
        crossing=[row for row in data['items'] if row['intersection']=='calle 5 con carrera 70']
        self.assertEqual(data['items'][:2],crossing)
        self.assertEqual(len(crossing),2)
        self.assertEqual(len({row['code'] for row in crossing}),2)
        self.assertTrue(all(row['reports_at_intersection']==2 and row['latitude'] is None for row in crossing))
        self.assertEqual(self.client.get('/reports',headers=self.auth).json()['total'],0)
        for private in ('Reportante Privado','Remitente privado','3001234567','WhatsApp privado'):
            self.assertNotIn(private,str(data))

    def test_public_evidence_counts_and_originals_require_team_key(self):
        from io import BytesIO
        from PIL import Image
        from psycopg.types.json import Jsonb
        from semaforos.files import sha256
        from uuid import UUID

        def file(name,modality,parent=None):
            path=self.root/name
            if modality in ('frame','image'):
                Image.new('RGB',(1000,700),'blue').save(path)
            else:
                path.write_bytes(b'synthetic attachment')
            return self.store.evidence(UUID(self.cid),name,modality,name,path.stat().st_size,sha256(path),parent=parent)

        audio=file('voz privada.ogg','audio')
        video=file('video privado.mp4','video')
        derived=file('audio derivado.wav','audio',video)
        frame=file('fotograma.jpg','frame',video)
        photo=file('foto privada.jpg','image')
        unlinked=file('foto sin vínculo.jpg','image')
        original_annotation=self.root/'annotated.jpg'
        Image.new('RGB',(1000,700),'red').save(original_annotation)
        job_id=self.store.enqueue(photo,'detect','test-annotations',self.config)
        source=self.findings[0]['message_id']
        with self.store.connect() as c:
            c.execute("UPDATE jobs SET state='completed', attempts=1 WHERE id=%s",(job_id,))
            c.execute('''INSERT INTO runs (id,job_id,attempt,state,finished_at,output)
                VALUES (%s,%s,1,'completed',now(),%s)''',
                (uuid4(),job_id,Jsonb({'objects':[{'bbox':[1,2,3,4]}],'annotation':str(original_annotation)})))
            for name,ident in [('voz.ogg',audio),('video.mp4',video),('foto.jpg',photo)]:
                c.execute("INSERT INTO message_attachments VALUES(%s,%s,%s,'linked')",(source,name,ident))
        data=self.client.get('/semaforos/datos').json()
        item=next(row for row in data['items'] if row['evidence_scope']=='registro')
        counts={'chat':1,'audio':1,'video':1,'audio_video':1,'image':1,'frame':1}
        self.assertEqual(item['evidence_counts'],counts)
        self.assertEqual(data['totals']['photos'],2)
        self.assertEqual(data['totals']['videos'],1)
        self.assertEqual(data['totals']['audios'],2)
        for private in (str(audio),'voz privada.ogg','_chat.txt','evidence_ids','_source_ids'):
            self.assertNotIn(private,str(data))
        path='/public-records/'+item['code']+'/evidence'
        self.assertEqual(self.client.get(path).status_code,401)
        evidence=self.client.get(path,headers=self.auth).json()
        self.assertEqual(evidence['scope'],'registro')
        self.assertEqual(evidence['counts'],counts)
        self.assertTrue({str(i) for i in (audio,video,derived,photo,frame)} <= {f['id'] for f in evidence['items']})
        self.assertNotIn(str(unlinked),{f['id'] for f in evidence['items']})
        txt=next(f for f in evidence['items'] if f['type']=='chat')
        original='/evidence/'+txt['id']+'/download'
        self.assertEqual(self.client.get(original).status_code,401)
        self.assertIn(b'Vecina',self.client.get(original,headers=self.auth).content)
        with TestClient(self.client.app,base_url='https://testserver') as browser:
            record='/report-media/records/'+item['code']
            self.assertEqual(browser.get(record).status_code,401)
            self.assertEqual(browser.post('/report-media/session').status_code,401)
            login=browser.post('/report-media/session',headers=self.auth)
            self.assertEqual(login.status_code,204)
            self.assertIn('HttpOnly',login.headers['set-cookie'])
            self.assertIn('Secure',login.headers['set-cookie'])
            self.assertIn('Path=/',login.headers['set-cookie'])
            self.assertEqual(browser.get('/team-session').status_code,200)
            self.assertEqual(browser.get('/action-records').status_code,200)
            self.assertEqual(browser.post('/report-exports',json={},
                                          headers={'Origin':'https://invalid.example'}).status_code,403)
            media=browser.get(record).json()
            by_type={file['type']:file for file in media['items']}
            content=browser.get(by_type['chat']['content']).text
            self.assertIn('Quinta con 5, apagado.',content)
            self.assertIn('Carrera 70, intermitente.',content)
            for media_type in ('audio','audio_video','video'):
                response=browser.get(by_type[media_type]['content'],headers={'Range':'bytes=0-3'})
                self.assertEqual(response.status_code,206,response.text)
                self.assertEqual(response.content,b'synt')
            for media_type,want_annotation in (('image',True),('frame',False)):
                response=browser.get(by_type[media_type]['thumbnail'])
                self.assertEqual(response.status_code,200)
                with Image.open(BytesIO(response.content)) as thumbnail:
                    self.assertLessEqual(thumbnail.width,480)
                    r,_,b=thumbnail.getpixel((0,0))
                    self.assertEqual(r>b,want_annotation)
            self.assertEqual(browser.get(by_type['image']['thumbnail'][:-1]+'Z').status_code,404)
            self.assertEqual(browser.delete('/report-media/session',headers={'Origin':'https://testserver'}).status_code,204)
            self.assertEqual(browser.get(by_type['chat']['content']).status_code,401)


    def test_action_report_export_reviews_and_selective_replay(self):
        from semaforos.reprocess import queue_sources
        data=self.client.get('/action-records',headers=self.auth).json()
        self.assertIsNone(data['map'])
        self.assertTrue(data['items'])
        self.assertTrue(all(r['description']==r['situacion_presentada'] for r in data['items']))
        export=self.client.post('/report-exports',headers=self.auth,json={'action_report':True})
        self.assertEqual(export.status_code,200)
        self.assertTrue(export.content.startswith(b'%PDF-'))
        with TestClient(self.client.app,base_url='https://testserver') as browser:
            browser.post('/report-media/session',headers=self.auth)
            item=data['items'][0]
            url='/report-media/records/'+item['code']
            detail=browser.get(url).json()
            self.assertEqual(detail['situacion_presentada'],item['description'])
            chat=next(f for f in detail['items'] if f['type']=='chat')
            self.assertEqual(chat['analysis']['state'],'completed')
            review={'run_id':chat['analysis']['run_id'],'field':'location_detected','label':False,'reviewer':'Equipo'}
            self.assertEqual(browser.post('/reviews',json=review).status_code,403)
            self.assertEqual(browser.post('/reviews',json=review,headers={'Origin':'https://testserver'}).status_code,200)
            detail=browser.get(url).json()
            self.assertIs(next(f for f in detail['items'] if f['type']=='chat')['analysis']['review'],False)
        audio=self.store.evidence(self.cid,'audio.ogg','audio','voz.ogg',1,'1'*64)
        video=self.store.evidence(self.cid,'video.mp4','video','video.mp4',1,'2'*64)
        self.store.evidence(self.cid,'from-video.wav','audio','pista.wav',1,'3'*64,parent=video)
        frame=self.store.evidence(self.cid,'frame.jpg','frame','fotograma.jpg',1,'4'*64,parent=video)
        self.store.enqueue(frame,'detect','test-base',self.config)
        self.assertEqual(queue_sources(self.store,self.config,conversation=self.cid)['audios_de_video'],1)
        with self.store.connect() as c:
            self.assertFalse(c.execute("SELECT 1 FROM jobs WHERE experiment_id='accion-popular-v2'").fetchone())
        for _ in range(2):
            queue_sources(self.store,self.config,conversation=self.cid,apply=True)
        with self.store.connect() as c:
            jobs=c.execute("SELECT stage,evidence_id FROM jobs WHERE experiment_id='accion-popular-v2'").fetchall()
        self.assertEqual(len([job for job in jobs if job['stage']=='audio']),2)
        self.assertTrue(any(job['evidence_id']==audio for job in jobs))
        self.assertEqual({job['stage'] for job in jobs},{'audio','text'})


    def test_five_conversation_pilot_selects_distinct_cases_and_reuses_the_selection(self):
        from semaforos.optimize_queue import FIVE,prepare
        from semaforos.pilot import CASES

        candidates={}
        for case in (*CASES,'otro'):
            text='[13/11/26, 10:00] Vecina: Calle 18 con Carrera 15.\n'
            if case=='gps':
                text+='[13/11/26, 10:01] Vecina: https://maps.google.com/?q=3.472345,-76.511703\n'
            elif case=='multiples_cruces':
                text+='[13/11/26, 11:00] Vecina: Calle 16 con Carrera 80.\n'
            elif case=='remitente_operador':
                text+='[13/11/26, 10:01] Esteban Oli semaforos dañados: Gracias por el aviso.\n'
            path=self.root/(case+'.zip')
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('_chat.txt',text)
                archive.writestr('identificador.txt',case)
            cid=import_zip(self.store,self.root,path,self.config,'case-'+case)['conversation_id']
            candidates[case]=cid
            with self.store.connect() as db:
                jobs=db.execute("""SELECT j.id FROM jobs j JOIN evidence e ON e.id=j.evidence_id
                    WHERE e.conversation_id=%s""",(cid,)).fetchall()
                for item in jobs:
                    job=self.store.claim(db,job_id=item['id'])
                    self.store.complete(db,job,{'result':{'extraction':{'assertions':[]}},
                                                'metrics':{},'model_identity':{}})
                if case in ('audio_whatsapp','audio_video'):
                    parent=self.store.evidence(cid,case+'.mp4','video','clip.mp4',1,'a'*64) if case=='audio_video' else None
                    audio=self.store.evidence(cid,case+'.opus','audio','voz.opus',1,'b'*64,parent=parent)
                    ident=self.store.enqueue(audio,'audio','case-'+case,self.config)
                    job=self.store.claim(db,job_id=ident)
                    self.store.complete(db,job,{'result':{'text':'Calle 18 con Carrera 15.','segments':[]},
                                                'metrics':{},'model_identity':{}})
                    db.execute('UPDATE jobs SET expanded_at=now() WHERE id=%s',(ident,))

        estimate=prepare(self.store,self.config,pilot_five=True)
        self.assertEqual(estimate['experiment'],FIVE)
        self.assertEqual({item['caso']:item['conversation_id'] for item in estimate['seleccion']},
                         {key:candidates[key] for key in CASES})
        self.assertEqual(estimate['casos_sin_candidato_distinto'],[])
        applied=prepare(self.store,self.config,pilot_five=True,apply=True)
        self.assertEqual(applied['audio_batches'],2)
        self.assertGreaterEqual(applied['chat_batches'],5)
        retry=prepare(self.store,self.config,pilot_five=True,apply=True)
        self.assertEqual(retry['audio_batches'],2)
        self.assertCountEqual(retry['seleccion'],applied['seleccion'])
        with self.store.connect() as db:
            result=db.execute('SELECT stage,count(*) AS n FROM jobs WHERE experiment_id=%s GROUP BY stage',(FIVE,)).fetchall()
        self.assertEqual(result,[{'stage':'text','n':applied['chat_batches']+applied['audio_batches']}])

    def test_detailed_crossings_filter_their_evidence_and_export_links(self):
        path=self.root/'WhatsApp Chat - \u2068@CiudadanaBogota\u2069 (1).zip'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('_chat.txt',
                '[01/11/26, 10:00] Vecina: Quinta con 5, apagado <attached: foto-primera.jpg>\n'
                '[02/11/26, 11:00] Vecina: Carrera 70, intermitente <attached: foto-segunda.jpg>\n')
            for name in ('foto-primera.jpg','foto-segunda.jpg','sin-vinculo.jpg'):
                archive.writestr(name,'imagen sintética '+name)
        cid=import_zip(self.store,self.root,path,self.config,'test-episodes')['conversation_id']
        with self.store.connect() as c:
            jobs=c.execute("""SELECT j.id FROM jobs j JOIN evidence e ON j.evidence_id=e.id
                WHERE e.conversation_id=%s AND j.stage='text'""",(cid,)).fetchall()
            for entry in jobs:
                job=self.store.claim(c,job_id=entry['id'])
                self.store.complete(c,job,self.infer(self.store,c,job,self.root))
        items=self.client.get('/detailed-records',headers=self.auth).json()['items']
        row=next(item for item in items if item['id']==cid)
        self.assertEqual(row['archive_label'],'@CiudadanaBogota (1)')
        self.assertEqual(row['unassigned_evidence_count'],1)
        self.assertEqual(len(row['episodes']),2)
        self.assertTrue(all(ep['evidence_counts']=={'image':1,'chat':1} for ep in row['episodes']))
        with TestClient(self.client.app,base_url='https://testserver') as browser:
            base='/report-media/conversations/'+cid
            first_episode=next(ep for ep in row['episodes'] if ep['location']=='Calle 5 con Carrera 5')
            query={'episodio':first_episode['id']}
            self.assertEqual(browser.get(base,params=query).status_code,401)
            browser.post('/report-media/session',headers=self.auth)
            first=browser.get(base,params=query).json()
            self.assertEqual(first['scope'],'registro')
            self.assertEqual(first['intersection'],first_episode['location'])
            self.assertEqual({file['name'] for file in first['items']},{'_chat.txt','foto-primera.jpg'})
            self.assertEqual({file['name'] for file in browser.get(base).json()['items']},
                             {'_chat.txt','foto-primera.jpg','foto-segunda.jpg','sin-vinculo.jpg'})
            self.assertEqual(browser.get(base,params={'episodio':'0'*16}).status_code,404)
            with patch.dict(os.environ,{'SC_REPORT_ORIGIN':''}):
                mismatch=self.client.post('/report-exports',headers={**self.auth,'Origin':'https://otro.example'},
                                          json={'detailed_report':True})
                self.assertEqual(mismatch.json()['detail'],'https_report_origin_required')
                export=self.client.post('/report-exports',headers={**self.auth,'Origin':'https://testserver',
                                   'Sec-Fetch-Site':'same-origin'},json={'detailed_report':True})
            self.assertEqual(export.status_code,200, export.text[:200] if export.status_code!=200 else '')
            urls=re.findall(rb'/URI \(https://testserver(/informe/conversaciones/([a-f0-9-]+)/'+cid.encode()+
                            rb'\?firma=([a-f0-9]+))\)',export.content)
            self.assertEqual(len(urls),2)
            self.assertEqual(urls[0],urls[1])
            url=urls[0]
            self.assertRegex(export.headers['X-Report-Filename'],
                             r'^Accion Popular Semaforos Cali [A-Z]{3} \d{2} \d{4} \d{2}-\d{2}-\d{2}\.pdf$')
            saved=browser.get('/report-exports/'+url[1].decode(),headers=self.auth)
            self.assertEqual(export.headers['Content-Disposition'],saved.headers['Content-Disposition'])
            path=f'/report-media/informes/{url[1].decode()}/conversaciones/{cid}'
            proof=url[2].decode()
            self.store.evidence(cid,'reciente.jpg','image','reciente.jpg',1,'d'*64)
            with TestClient(self.client.app,base_url='https://testserver') as recipient:
                self.assertEqual(recipient.get(url[0].decode()).status_code,200)
                self.assertEqual(recipient.get(base).status_code,401)
                self.assertEqual(recipient.get(path,params={'firma':'0'*64}).status_code,404)
                # A new extraction cannot break a PDF link to the saved inventory.
                with patch('semaforos.detailed.compose',side_effect=AssertionError('unexpected recomposition')):
                    copied=recipient.get(path,params={'firma':proof})
                self.assertEqual(copied.status_code,200)
                self.assertEqual(copied.json()['archive_label'],'@CiudadanaBogota (1)')
                self.assertEqual(copied.json()['date_range'],'01 nov 2026 - 02 nov 2026')
                items=copied.json()['items']
                self.assertEqual({file['name'] for file in items},
                                 {'_chat.txt','foto-primera.jpg','foto-segunda.jpg','sin-vinculo.jpg'})
                self.assertTrue(all('analysis' not in file for file in items))
                chat=next(file for file in items if file['type']=='chat')
                self.assertIn('Quinta con 5',recipient.get(chat['content']).text)
                self.assertEqual(recipient.get(chat['download']).status_code,200)
                with self.store.connect() as db:
                    db.execute("UPDATE report_pdf_exports SET evidence_expires_at=now()-interval '1 hour' WHERE id=%s",(url[1].decode(),))
                self.assertEqual(recipient.get(path,params={'firma':proof}).status_code,404)

    def test_historical_batch_keeps_previous_extractions_out_of_its_report(self):
        from semaforos.optimize_queue import prepare
        from semaforos.store import LOCK_KEY
        batch='detalle-qwen-arquitectura-prueba'
        params={'experimento':batch}
        self.assertEqual(prepare(self.store,self.config,historical=True,experiment_id=batch)['conversations'],1)
        old=self.client.get('/detailed-records',headers=self.auth).json()['items'][0]
        self.assertTrue(any(ep['location'] for ep in old['episodes']))
        with self.store.connect() as worker:
            worker.execute('SELECT pg_advisory_xact_lock_shared(%s)',(LOCK_KEY,))
            first=prepare(self.store,self.config,historical=True,experiment_id=batch,apply=True)
            repeated=prepare(self.store,self.config,historical=True,experiment_id=batch,apply=True)
        self.assertEqual(first['queued_conversations'],1)
        self.assertGreater(first['batch_jobs'],0)
        self.assertEqual(repeated['batch_jobs'],first['batch_jobs'])
        pending=self.client.get('/detailed-records',params=params,headers=self.auth).json()
        self.assertEqual(pending['experiment'],batch)
        self.assertEqual(pending['items'][0]['analysis_state'],'pending')
        self.assertTrue(all(not ep['location'] for ep in pending['items'][0]['episodes']))
        with self.store.connect() as db:
            ids=db.execute('SELECT id FROM jobs WHERE experiment_id=%s',(batch,)).fetchall()
            self.assertEqual(len(ids),first['batch_jobs'])
            for row in ids:
                job=self.store.claim(db,job_id=row['id'])
                self.store.complete(db,job,self.infer(self.store,db,job,self.root))
        ready=self.client.get('/detailed-records',params=params,headers=self.auth).json()['items'][0]
        self.assertEqual(ready['analysis_state'],'completed')
        self.assertTrue(any(ep['location'] for ep in ready['episodes']))

    def test_detailed_report_date_pdf_reviews_and_queue_replacement(self):
        from semaforos.optimize_queue import prepare
        from semaforos.report_pdf import signature
        from semaforos.messages import index_chat
        from semaforos.whatsapp import PARSER_VERSION
        with self.store.connect() as c:
            chat=c.execute("SELECT id,storage_path FROM evidence WHERE conversation_id=%s AND modality='chat'",(self.cid,)).fetchone()
        data=self.client.get('/detailed-records',headers=self.auth)
        self.assertEqual(data.status_code,200)
        row=data.json()['items'][0]
        self.assertEqual(row['reporter'],'Vecina')
        self.assertTrue(row['date_from'].startswith('2026-11-01T15:00:00'))
        self.assertTrue(row['date_to'].startswith('2026-11-02T16:00:00'))
        self.assertEqual(row['evidence_counts'],{'chat':1})
        with TestClient(self.client.app,base_url='https://testserver') as browser:
            browser.post('/report-media/session',headers=self.auth)
            media=browser.get('/report-media/conversations/'+self.cid)
            self.assertEqual(media.status_code,200)
            chat_item=media.json()['items'][0]
            self.assertEqual(chat_item['type'],'chat')
            review={'run_id':chat_item['analysis']['evaluations'][0]['run_id'],'field':'semantic_fields',
                    'label':{'dano':{'observed':True,'detected':True}},'reviewer':'Equipo'}
            self.assertEqual(browser.post('/reviews',headers={'Origin':'https://testserver'},json=review).status_code,200)
            quality=browser.get('/model-metrics').json()['human_evaluations']['text']
            self.assertEqual(quality['fields']['dano']['samples'],1)
            self.assertEqual(quality['fields']['gestion']['samples'],0)
            self.assertEqual(quality['macro_f1'],1)
            pdf=browser.post('/report-exports',headers=self.auth,json={'detailed_report':True})
            self.assertEqual(pdf.status_code,200)
            self.assertTrue(pdf.content.startswith(b'%PDF-'))
            ident=pdf.headers['X-Report-Export-ID']
            with self.store.connect() as c:
                exp=c.execute('SELECT evidence_ids,evidence_expires_at FROM report_pdf_exports WHERE id=%s',(ident,)).fetchone()
            self.assertEqual(exp['evidence_ids'],[chat['id']])
            token=signature('x'*32,ident,chat['id'],exp['evidence_expires_at'])
            direct=browser.get(f'/informe/evidencia/{ident}/{chat["id"]}?firma={token}')
            self.assertIn('Quinta con 5',direct.text)
        old={**self.config,'text':{'model':'test','threads':4}}
        old_job=self.store.enqueue(chat['id'],'text','legacy-test',old,{'sources':[]})
        self.assertEqual(prepare(self.store,self.config,conversation=self.cid)['pending_jobs'],1)
        self.assertGreater(prepare(self.store,self.config,conversation=self.cid,apply=True)['chat_batches'],0)
        self.assertEqual(prepare(self.store,self.config,conversation=self.cid)['pending_jobs'],0)
        pending=self.client.get('/detailed-records',headers=self.auth).json()['items'][0]
        self.assertEqual(pending['analysis_state'],'pending')
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT payload FROM jobs WHERE id=%s',(old_job,)).fetchone()['payload']
                             ['superseded_by_review'],'detalle-qwen-v3')
        proof=self.store.evidence(self.cid,'unrecognized.txt','chat','unrecognized.txt',5,'3'*64)
        with self.store.connect() as c:
            c.execute('INSERT INTO source_texts VALUES (%s,%s)',(proof,'15/11/2026 10.00 | Ciudadana | Falla'))
        index_chat(self.store,proof,self.config)
        alerts=self.client.get('/model-metrics',headers=self.auth).json()['chat_format_alerts']
        self.assertTrue(any(a['parser_version']==PARSER_VERSION and a['format_health']['severity']=='degraded' for a in alerts))

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

    def test_same_crossing_from_another_citizen_remains_a_separate_report(self):
        first, _ = self.create(self.selected(['Quinta con 5', 'apagado']))
        path = self.root / 'Otro ciudadano.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('_chat.txt', '[01/11/26, 10:02] Otro: Quinta con 5, apagado.\n')
        imported = import_zip(self.store, self.root, path, self.config, 'otro')
        once(self.store, self.root, runner=self.infer)
        findings = self.client.get('/findings?conversation_id=' + imported['conversation_id'],
                                   headers=self.auth).json()['items']
        second, _ = self.create([finding['id'] for finding in findings])
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(self.client.get('/reports', headers=self.auth).json()['active'], 2)

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
