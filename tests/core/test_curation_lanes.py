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
