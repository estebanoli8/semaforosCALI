"""PostgreSQL exclusivo de Semáforos; cambios de esquema explícitos y versionados."""
import json
import os
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from . import __version__
from .files import canonical_hash, sha256

LOCK_KEY = 2026110801


class Store:
    def __init__(self, dsn=None):
        self.dsn = dsn or os.environ['SC_DATABASE_URL']

    def connect(self):
        c = psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=10)
        # No permitir ejecutar migraciones accidentalmente contra contratos/n8n.
        name = c.execute('SELECT current_database() AS name').fetchone()['name']
        if not name.startswith('semaforos_'):
            c.close();raise ValueError('database_name_must_start_with_semaforos_')
        c.execute('SET search_path TO semaforos,public')
        c.commit()
        return c

    def migrate(self):
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_KEY+1,))
            c.execute('CREATE SCHEMA IF NOT EXISTS semaforos')
            c.execute('CREATE TABLE IF NOT EXISTS semaforos.schema_migrations(name TEXT PRIMARY KEY,sha256 TEXT NOT NULL,applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
            for path in sorted(Path(__file__).with_name('migrations').glob('*.sql')):
                old=c.execute('SELECT sha256 FROM schema_migrations WHERE name=%s',(path.name,)).fetchone()
                digest=sha256(path)
                if old:
                    if old['sha256']!=digest:raise ValueError('applied_migration_changed')
                    continue
                c.execute(path.read_text())
                c.execute('INSERT INTO schema_migrations(name,sha256) VALUES(%s,%s)',(path.name,digest))

    def conversation(self, source_key, name, metadata=None):
        with self.connect() as c:
            return c.execute('''INSERT INTO conversations(id,source_key,original_name,metadata) VALUES(%s,%s,%s,%s)
                ON CONFLICT(source_key) DO UPDATE SET source_key=EXCLUDED.source_key RETURNING id''',
                (uuid4(),source_key,name,Jsonb(metadata or {}))).fetchone()['id']

    def evidence(self, conversation_id, path, modality, original_name, size, digest, metadata=None, parent=None):
        with self.connect() as c:
            old=c.execute('SELECT * FROM evidence WHERE storage_path=%s',(path,)).fetchone()
            if old:
                if old['sha256']!=digest or str(old['conversation_id'])!=str(conversation_id):raise ValueError('immutable_evidence_mismatch')
                return old['id']
            return c.execute('''INSERT INTO evidence(id,conversation_id,parent_id,modality,original_name,storage_path,sha256,size_bytes,metadata)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (uuid4(),conversation_id,parent,modality,original_name,path,digest,size,Jsonb(metadata or {}))).fetchone()['id']

    def enqueue(self, evidence_id, stage, experiment, config, payload=None):
        if stage not in ('audio','detect','lights','text','video'):raise ValueError('invalid_stage')
        payload=payload or {}
        with self.connect() as c:
            evidence=c.execute('SELECT sha256 FROM evidence WHERE id=%s',(evidence_id,)).fetchone()
            if not evidence:raise ValueError('unknown_evidence')
            key=canonical_hash([str(evidence_id),evidence['sha256'],stage,experiment,config,payload,__version__])
            return c.execute('''INSERT INTO jobs(id,evidence_id,stage,experiment_id,config,config_hash,code_version,payload,request_key,max_attempts)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(request_key) DO UPDATE SET request_key=EXCLUDED.request_key RETURNING id''',
                (uuid4(),evidence_id,stage,experiment,Jsonb(config),canonical_hash(config),__version__,Jsonb(payload),key,config['max_attempts'])).fetchone()['id']

    def claim(self, c):
        # El llamador conserva advisory lock de sesión durante TODO el proceso pesado.
        c.execute("UPDATE runs SET state='interrupted',finished_at=now(),error_code='worker_lost' WHERE state='running' AND job_id IN (SELECT id FROM jobs WHERE state='running' AND lease_until<now())")
        c.execute("UPDATE jobs SET state='failed',updated_at=now() WHERE state='running' AND lease_until<now() AND attempts>=max_attempts")
        row=c.execute("""SELECT j.*,e.storage_path,e.sha256,e.conversation_id,e.modality,e.metadata AS evidence_metadata
            FROM jobs j JOIN evidence e ON e.id=j.evidence_id
            WHERE (j.state='pending' AND j.available_at<=now() OR j.state='running' AND j.lease_until<now())
            AND j.attempts<j.max_attempts ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1""").fetchone()
        if not row:c.commit();return None
        token=uuid4();run_id=uuid4()
        c.execute("UPDATE jobs SET state='running',attempts=attempts+1,lease_token=%s,lease_until=now()+interval '90 seconds',updated_at=now() WHERE id=%s",(token,row['id']))
        c.execute("INSERT INTO runs(id,job_id,attempt,state) VALUES(%s,%s,%s,'running')",(run_id,row['id'],row['attempts']+1))
        c.commit();row.update(lease_token=token,run_id=run_id,attempts=row['attempts']+1)
        return row

    def heartbeat(self, c, job):
        changed=c.execute("UPDATE jobs SET lease_until=now()+interval '90 seconds' WHERE id=%s AND lease_token=%s AND state='running'",(job['id'],job['lease_token'])).rowcount
        c.commit()
        if changed!=1:raise RuntimeError('lease_lost')

    def complete(self, c, job, output):
        row=c.execute('SELECT state,lease_token FROM jobs WHERE id=%s FOR UPDATE',(job['id'],)).fetchone()
        if row['state']!='running' or row['lease_token']!=job['lease_token']:raise RuntimeError('lease_lost')
        c.execute("UPDATE runs SET state='completed',finished_at=now(),output=%s,metrics=%s,model_identity=%s WHERE id=%s",(Jsonb(output['result']),Jsonb(output['metrics']),Jsonb(output['model_identity']),job['run_id']))
        if job['stage']=='audio':
            r=output['result']
            c.execute('INSERT INTO transcripts(id,run_id,evidence_id,literal_text,segments,language) VALUES(%s,%s,%s,%s,%s,%s)',
                (uuid4(),job['run_id'],job['evidence_id'],r['text'],Jsonb(r['segments']),r.get('language')))
        elif job['stage']=='detect':
            r=output['result']
            for i,item in enumerate(r['objects']):
                c.execute('INSERT INTO detections(id,run_id,evidence_id,object_index,bbox,score,width,height) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (uuid4(),job['run_id'],job['evidence_id'],i,Jsonb(item['bbox']),item['score'],r['width'],r['height']))
        elif job['stage']=='lights':
            for item in output['result']['objects']:
                c.execute('INSERT INTO light_readings(id,run_id,detection_id,red,yellow,green,reading_state,reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (uuid4(),job['run_id'],item['detection_id'],item['red'],item['yellow'],item['green'],item['reading_state'],item.get('reason')))
        c.execute("UPDATE jobs SET state='completed',lease_until=NULL,updated_at=now() WHERE id=%s",(job['id'],))
        c.commit()

    def fail(self, c, job, code):
        c.rollback()
        row=c.execute('SELECT * FROM jobs WHERE id=%s FOR UPDATE',(job['id'],)).fetchone()
        if row['state']!='running' or row['lease_token']!=job['lease_token']:raise RuntimeError('lease_lost')
        state='pending' if row['attempts']<row['max_attempts'] else 'failed'
        c.execute("UPDATE runs SET state='failed',finished_at=now(),error_code=%s WHERE id=%s",(code,job['run_id']))
        c.execute("UPDATE jobs SET state=%s,lease_until=NULL,available_at=now()+interval '30 seconds',updated_at=now() WHERE id=%s",(state,job['id']))
        c.commit()

    def retry_failed_model(self, ident):
        """Queue one more model attempt; preserve old failed runs for review."""
        with self.connect() as c:
            row=c.execute('SELECT stage,state,attempts FROM jobs WHERE id=%s FOR UPDATE',(ident,)).fetchone()
            if row is None:return 'not_found'
            if row['stage'] not in ('text','lights') or row['state']!='failed':return 'not_failed_model'
            if row['attempts']>=5:return 'retry_limit_reached'
            c.execute('''UPDATE jobs SET state='pending',max_attempts=attempts+1,
                available_at=now(),lease_token=NULL,lease_until=NULL,updated_at=now()
                WHERE id=%s''',(ident,))
            return 'queued'

    def review(self, run_id, field, label, reviewer, comment=None):
        with self.connect() as c:
            return c.execute('INSERT INTO reviews(id,run_id,field,human_label,reviewer,comment) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id',
                (uuid4(),run_id,field,Jsonb(label),reviewer,comment)).fetchone()['id']
