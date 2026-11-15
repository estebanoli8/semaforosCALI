import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from semaforos.api import create_app
from semaforos.config import load_config
from semaforos.store import Store


@unittest.skipUnless(os.getenv('SC_TEST_DSN'), 'Requires test PostgreSQL')
class ModelDashboardTest(unittest.TestCase):
    def test_aggregate_access_filters_and_independent_labels(self):
        store = Store(os.environ['SC_TEST_DSN'])
        with store.connect() as connection:
            self.assertEqual(connection.execute('SELECT current_database() AS n').fetchone()['n'],
                             'semaforos_test')
            connection.execute('DROP SCHEMA IF EXISTS semaforos CASCADE')
        store.migrate()
        config = load_config()
        conversation = store.conversation('synthetic', 'private-name')
        evidence = store.evidence(conversation, 'secret.ogg', 'audio', 'secret.ogg', 1, '0' * 64)
        rows = [
            ('audio', 'completed', 'baseline', {}),
            ('audio', 'completed', 'baseline', {}),
            ('detect', 'completed', 'baseline', {}),
            ('text', 'completed', 'baseline', {'omitted_assertions': [{'reason':'unbacked_quote'}]}),
            ('text', 'failed', 'baseline', {}),
            ('text', 'failed', 'other', {}),
            ('text', 'pending', 'baseline', {}),
            ('audio', 'completed', 'baseline', {'excluded':'team_sender'}),
        ]
        runs = []
        with store.connect() as connection:
            for index, (stage, state, experiment, output) in enumerate(rows):
                job_id = store.enqueue(evidence, stage, experiment, config,
                                       {'index':index}, connection=connection)
                connection.execute('UPDATE jobs SET state=%s WHERE id=%s', (state,job_id))
                if state == 'pending':
                    connection.execute("UPDATE jobs SET created_at=now()-interval '40 days' WHERE id=%s",
                                       (job_id,))
                    continue
                connection.execute("""INSERT INTO runs(id,job_id,attempt,state,finished_at,error_code)
                    VALUES(%s,%s,1,'failed',now(),'HTTPError')""", (uuid4(),job_id))
                run_id = uuid4()
                runs.append(run_id)
                connection.execute("""INSERT INTO runs
                    (id,job_id,attempt,state,finished_at,output,metrics,error_code)
                    VALUES(%s,%s,2,%s,now(),%s,%s,%s)""",
                    (run_id,job_id,state,Jsonb(output),Jsonb({'wall_seconds':index+2}),
                     'unbacked_quote' if state=='failed' else None))
            for run, field, metrics in [
                (runs[0], 'curation', {'reference_kind':'human_correction','wer':1/3,
                                       'word_errors':1,'reference_words':3}),
                (runs[0], 'curation', {'reference_kind':'human_approval','wer':0,
                                       'word_errors':0,'reference_words':3}),
                (runs[1], 'curation', {'reference_kind':'human_approval','wer':0,
                                       'word_errors':0,'reference_words':3}),
                (runs[2], 'boxes', {'iou_threshold':.5,'true_positive':2,
                                     'false_positive':1,'false_negative':3}),
            ]:
                review_id = uuid4()
                connection.execute("""INSERT INTO reviews(id,run_id,field,human_label,reviewer)
                    VALUES(%s,%s,%s,'{}','synthetic')""",(review_id,run,field))
                connection.execute('INSERT INTO evaluations(id,review_id,metrics) VALUES(%s,%s,%s)',
                                   (uuid4(),review_id,Jsonb(metrics)))
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(store,Path(directory),config,'x'*32)) as client:
                self.assertEqual(client.get('/model-metrics').status_code,401)
                self.assertEqual(client.get('/metricas').status_code,200)
                response = client.get('/model-metrics?experiment=baseline&days=30',
                                      headers={'Authorization':'Bearer '+'x'*32})
                self.assertEqual(response.status_code,200,response.text)
        data = response.json()
        self.assertNotIn('private-name',response.text)
        self.assertNotIn('secret.ogg',response.text)
        self.assertEqual(data['experiments'],['baseline','other'])
        by_stage = {stage['stage']:stage for stage in data['stages']}
        self.assertEqual(by_stage['audio']['completed'],2)
        self.assertEqual(by_stage['audio']['excluded'],1)
        self.assertEqual(by_stage['audio']['seconds_p50'],2.5)
        self.assertEqual(by_stage['audio']['quality_samples'],1)
        self.assertEqual(by_stage['audio']['reference_words'],3)
        self.assertEqual(by_stage['detect']['tp'],2)
        self.assertEqual(by_stage['detect']['fn'],3)
        self.assertEqual(by_stage['text']['partial'],1)
        self.assertEqual(by_stage['text']['pending'],0)
        self.assertEqual(data['errors'],[{'stage':'text','code':'unbacked_quote','count':1}])
        self.assertEqual(sum(day['results'] for day in data['daily']),4)
