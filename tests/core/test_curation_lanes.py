import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from semaforos.store import Store,LOCK_KEY
from semaforos.config import load_config
from semaforos.files import sha256
from semaforos.lanes import once
from semaforos.worker import expand
from semaforos.curation import save


@unittest.skipUnless(os.getenv('SC_TEST_DSN'),'Requires test PostgreSQL')
class CurationLanesTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(os.environ['SC_TEST_DSN'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT current_database() AS n').fetchone()['n'],'semaforos_test')
            c.execute('DROP SCHEMA IF EXISTS semaforos CASCADE')
        self.store.migrate();self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=load_config();cid=self.store.conversation('fixture','Synthetic')
        path=self.root/'audio.ogg';path.write_bytes(b'fixture')
        self.eid=self.store.evidence(cid,'audio.ogg','audio','audio.ogg',7,sha256(path))

    def tearDown(self):self.temp.cleanup()

    def audio_output(self):
        return {'result':{'text':'Quinta con seis','segments':[]},'metrics':{},'model_identity':{'fixture':True}}

    def test_correction_queues_only_new_text_and_preserves_prediction(self):
        ident=self.store.enqueue(self.eid,'audio','trial',self.config)
        with self.store.connect() as c:
            job=self.store.claim(c,job_id=ident);self.store.complete(c,job,self.audio_output())
        expand(self.store,self.root)
        from semaforos.findings import index_run
        with self.store.connect() as c:
            old_text=self.store.claim(c)
            source=old_text['payload']['sources'][0]
            self.store.complete(c,old_text,{'result':{'extraction':{'summary':'Ubicación',
                'assertions':[{'source_id':source['id'],'variable':'ubicacion','literal':'Quinta con seis','interpretation':None}]}},'metrics':{},'model_identity':{}})
        index_run(self.store,old_text['run_id'])
        answer=save(self.store,job['run_id'],'corrected','Reviewer','Quinta con cinco')
        self.assertEqual(len(answer['job_ids']),1)
        expand(self.store,self.root)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT output FROM runs WHERE id=%s',(job['run_id'],)).fetchone()['output']['text'],'Quinta con seis')
            rows=c.execute("SELECT payload FROM jobs WHERE stage='text'").fetchall()
            self.assertEqual(len(rows),2)
            self.assertEqual(sum('superseded_by_review' in r['payload'] for r in rows),1)
            corrected=[r for r in rows if 'transcription_review_id' in r['payload']][0]
            self.assertEqual(corrected['payload']['sources'][0]['text'],'Quinta con cinco')
            claimed=self.store.claim(c)
            self.assertEqual(str(claimed['id']),answer['job_ids'][0])
        save(self.store,job['run_id'],'approved','Reviewer')
        with self.store.connect() as c:
            label=c.execute("SELECT human_label FROM reviews ORDER BY created_at DESC LIMIT 1").fetchone()['human_label']
            self.assertEqual(label['text'],'Quinta con cinco')
        from semaforos.findings import index_run
        source=claimed['payload']['sources'][0]
        with self.store.connect() as c:
            self.store.complete(c,claimed,{'result':{'extraction':{'summary':'Ubicación reportada',
                'assertions':[{'source_id':source['id'],'variable':'ubicacion','literal':'Quinta con cinco','interpretation':None}]}},'metrics':{},'model_identity':{}})
        index_run(self.store,claimed['run_id'])
        with self.store.connect() as c:
            finding=c.execute("SELECT literal,source_ref FROM findings WHERE literal='Quinta con cinco'").fetchone()
            self.assertEqual(finding['literal'],'Quinta con cinco')
            self.assertEqual(finding['source_ref']['transcription_review_id'],answer['review_id'])
            cid=c.execute('SELECT conversation_id FROM evidence WHERE id=%s',(self.eid,)).fetchone()['conversation_id']
        from fastapi.testclient import TestClient
        from semaforos.api import create_app
        client=TestClient(create_app(self.store,self.root,self.config,'x'*32))
        headers={'Authorization':'Bearer '+'x'*32}
        self.assertEqual(client.get('/curation/'+str(cid)).status_code,401)
        rows=client.get('/curation/'+str(cid),headers=headers)
        self.assertEqual(rows.status_code,200);self.assertEqual(len(rows.json()['items']),3)
        findings=client.get('/findings?conversation_id='+str(cid),headers=headers).json()
        self.assertEqual([f['literal'] for f in findings['items']],['Quinta con cinco'])
        proposals=client.get('/report-proposals?conversation_id='+str(cid),headers=headers).json()
        self.assertEqual(proposals['total'],1)

    def test_zip_filters_team_text_and_explicit_audio_but_keeps_unknown(self):
        import zipfile
        from semaforos.detailed import snapshot
        from semaforos.ingest import import_zip
        from semaforos.worker import execute_child

        archive=self.root/'fixture.zip'
        team_text='Calle 99 con carrera 99, mensaje del equipo'
        compact_text='Segunda nota privada del equipo'
        citizen_text='Quinta con cinco apagado'
        original=(
            f'[13/11/26, 3:40:59\u202fPM] Esteban Oli semaforos dañados: {team_text}\n'
            'Continuación privada.\n'
            f'[13/11/26, 3:41:59\u202fPM] \u200eEsteban Oli semáforos dañados:{compact_text} <attached: team.opus>\n'
            f'[13/11/26, 3:42:59\u202fPM] Vecina:\u202f{citizen_text} <attached: citizen.opus>\n'
        )
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('_chat.txt',original)
            for name in ('team.opus','citizen.opus','unknown.opus'):
                z.writestr(name,b'fixture')
        cid=import_zip(self.store,self.root,archive,self.config,'fixture')['conversation_id']
        with self.store.connect() as c:
            rows=c.execute("""SELECT j.stage,j.payload,e.original_name FROM jobs j
                JOIN evidence e ON e.id=j.evidence_id""").fetchall()
            messages=c.execute("""SELECT id,evidence_id
                FROM messages ORDER BY ordinal""").fetchall()
            audio=c.execute("SELECT id FROM evidence WHERE original_name='team.opus'").fetchone()['id']
            self.assertEqual(c.execute('SELECT literal_text FROM source_texts').fetchone()['literal_text'],original)
            # Simulate older indexed messages losing the sender when whitespace differed.
            c.execute('UPDATE messages SET sender_visible=NULL WHERE id=%s',(messages[1]['id'],))
        queued=[r['original_name'] for r in rows]
        self.assertNotIn('team.opus',queued)
        self.assertIn('citizen.opus',queued)
        self.assertIn('unknown.opus',queued)
        expected_sources=[s for r in rows if r['stage']=='text' for s in r['payload']['sources']]
        self.assertEqual([s['text'] for s in expected_sources],[citizen_text])

        historic=[]
        for i,(record,literal) in enumerate(zip(messages,(team_text,compact_text,citizen_text))):
            historic.append({'id':str(i),'origin':'chat','text':literal,'message_id':str(record['id'])})
        prior_job=self.store.enqueue(messages[0]['evidence_id'],'text','old-queue',self.config,{'sources':historic})
        prior_audio=self.store.enqueue(audio,'audio','old-queue',self.config)
        with self.store.connect() as c:
            job=self.store.claim(c,job_id=prior_job)
            class InputCaptured(Exception):
                pass
            with patch('semaforos.worker.atomic_json',side_effect=InputCaptured) as capture:
                with self.assertRaises(InputCaptured):
                    execute_child(self.store,c,job,self.root)
            self.assertEqual(capture.call_args.args[1]['payload']['sources'],historic[-1:])
            self.store.complete(c,job,{'result':{'extraction':{'assertions':[]}},'metrics':{},'model_identity':{}})
            job=self.store.claim(c,job_id=prior_audio)
            with patch('semaforos.worker.atomic_json') as capture:
                result=execute_child(self.store,c,job,self.root)
                capture.assert_not_called()
            self.assertEqual(result['result']['excluded'],'team_sender_audio')
        detail=next(row for row in snapshot(self.store)['items'] if str(row['id'])==cid)
        self.assertNotIn('99',str([episode['location'] for episode in detail['episodes']]))
        self.assertNotIn('team.opus',[item['name'] for item in detail['evidence']])

    def test_two_lanes_overlap_but_duplicate_lane_and_legacy_do_not(self):
        self.store.enqueue(self.eid,'audio','trial',self.config)
        self.store.enqueue(self.eid,'text','trial',self.config,{'sources':[]})
        entered=threading.Barrier(2);release=threading.Event();errors=[]
        def runner(store,c,job,root):
            entered.wait(timeout=15)
            if not release.wait(timeout=15):raise RuntimeError('test_timeout')
            return self.audio_output() if job['stage']=='audio' else {'result':{'extraction':{'assertions':[]}},'metrics':{},'model_identity':{}}
        def work(lane):
            try:once(self.store,self.root,lane,runner=runner)
            except Exception as exc:errors.append(exc)
        # Avoid unrelated indexing in this lock/concurrency test.
        with patch('semaforos.lanes.index_pending'),patch('semaforos.lanes.expand'):
            a=threading.Thread(target=work,args=('text',));b=threading.Thread(target=work,args=('media',));a.start();b.start()
            import time
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                with self.store.connect() as c:
                    count=c.execute("SELECT count(*) AS n FROM jobs WHERE state='running'").fetchone()['n']
                if count==2:break
                time.sleep(.05)
            try:
                self.assertEqual(count,2)
                self.assertFalse(once(self.store,self.root,'text',runner=lambda *args:self.fail('duplicate lane')))
                with self.store.connect() as c:
                    self.assertFalse(c.execute('SELECT pg_try_advisory_lock(%s) AS ok',(LOCK_KEY,)).fetchone()['ok'])
            finally:release.set();a.join(20);b.join(20)
        self.assertFalse(a.is_alive());self.assertFalse(b.is_alive());self.assertEqual(errors,[])

    def test_exhausted_pending_job_does_not_block_lane(self):
        old=self.store.enqueue(self.eid,'text','old',self.config,{'sources':[]})
        new=self.store.enqueue(self.eid,'text','new',self.config,{'sources':[]})
        with self.store.connect() as c:c.execute('UPDATE jobs SET attempts=max_attempts WHERE id=%s',(old,))
        with patch('semaforos.lanes.index_pending'),patch('semaforos.lanes.expand'):
            self.assertTrue(once(self.store,self.root,'text',runner=lambda *args:{'result':{},'metrics':{},'model_identity':{}}))
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT state FROM jobs WHERE id=%s',(new,)).fetchone()['state'],'completed')
