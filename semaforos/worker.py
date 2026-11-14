import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from .files import atomic_json, contained, sha256
from .store import LOCK_KEY, Store


class AdapterFailure(Exception):
    def __init__(self, code):
        self.error_code=code if isinstance(code,str) and code.isidentifier() and len(code)<=100 else 'adapter_failed'
        super().__init__(self.error_code)


def text_chunks(text, source_id, origin, start=0):
    # Prefer sentence or word boundaries and retain exact offsets in the transcript.
    offset = 0
    while offset < len(text):
        end = min(offset + 1800, len(text))
        if end < len(text):
            boundary = max(text.rfind(mark, offset + 900, end) for mark in ('. ', '? ', '! ', '\n'))
            if boundary < 0:
                boundary = text.rfind(' ', offset + 900, end)
            if boundary >= 0:
                end = boundary + 1
        absolute = start + offset
        yield [{'id':f'{source_id}:{absolute}', 'text':text[offset:end],
                'origin':origin, 'source_id':str(source_id), 'char_start':absolute}]
        offset = end


def expand(store, root, conversation_id=None):
    """Reconciliación idempotente: recupera una caída tras guardar la predicción."""
    with store.connect() as c:
        rows=c.execute("""SELECT j.*,r.id AS run_id,r.output,e.storage_path,e.conversation_id,e.modality
            FROM jobs j JOIN runs r ON r.job_id=j.id AND r.state='completed'
            JOIN evidence e ON e.id=j.evidence_id
            WHERE j.stage<>'lights' AND j.state='completed' AND j.expanded_at IS NULL
            AND (%s::uuid IS NULL OR e.conversation_id=%s::uuid)
            ORDER BY j.created_at LIMIT 20""",(conversation_id,conversation_id)).fetchall()
    for job in rows:
        try:
            result=job['output'];config=job['config'];experiment=job['experiment_id']
            if job['stage']=='audio':
                from .messages import team_audio
                if team_audio(store,job['evidence_id']):
                    with store.connect() as c:c.execute('UPDATE jobs SET expanded_at=now() WHERE id=%s',(job['id'],))
                    continue
                origin='audio_video' if job['payload'].get('from_video') else 'audio_whatsapp'
                with store.connect() as c:
                    current=c.execute('SELECT expanded_at FROM jobs WHERE id=%s FOR UPDATE',(job['id'],)).fetchone()
                    if current['expanded_at'] is not None:continue
                    parts = result.get('analysis_parts')
                    sources_by_part = (
                        (sources for part in parts for sources in
                         text_chunks(part['text'], job['run_id'], origin, part['offset']))
                        if parts is not None else text_chunks(result['text'], job['run_id'], origin)
                    )
                    for sources in sources_by_part:
                        store.enqueue(job['evidence_id'],'text',experiment,config,{'sources':sources,'transcription_run_id':str(job['run_id'])},connection=c)
                    c.execute('UPDATE jobs SET expanded_at=now() WHERE id=%s',(job['id'],))
            elif job['stage']=='detect':
                path=Path(result['annotation'])
                relative=str(path.resolve().relative_to(root.resolve()));contained(root,relative)
                store.evidence(job['conversation_id'],relative,'annotated',path.name,path.stat().st_size,sha256(path),{'run_id':str(job['run_id'])},job['evidence_id'])
            elif job['stage']=='video':
                base=contained(root,f"runs/{job['run_id']}/artifacts/{result['sha256_video']}")
                items=[(f,'frame','detect') for f in result['fotogramas']]
                if result['audio']:items.append((result['audio'],'audio','audio'))
                for item,modality,stage in items:
                    path=contained(base,item['archivo'])
                    if sha256(path)!=item['sha256']:raise ValueError('derived_checksum_mismatch')
                    eid=store.evidence(job['conversation_id'],str(path.relative_to(root)),modality,item['archivo'],path.stat().st_size,item['sha256'],dict(item,run_id=str(job['run_id'])),job['evidence_id'])
                    store.enqueue(eid,stage,experiment,config,{'from_video':True,'video_evidence_id':str(job['evidence_id'])})
            with store.connect() as c:c.execute('UPDATE jobs SET expanded_at=now(),expansion_error=NULL WHERE id=%s',(job['id'],))
        except Exception as exc:
            with store.connect() as c:c.execute('UPDATE jobs SET expansion_error=%s WHERE id=%s',(type(exc).__name__,job['id']))


def once(store, root, runner=None):
    with store.connect() as c:
        if not c.execute('SELECT pg_try_advisory_lock(%s) AS acquired',(LOCK_KEY,)).fetchone()['acquired']:
            c.commit();return False
        c.commit()
        try:
            from .uploads import Uploads
            imported=Uploads(store,root).process_one_locked()
            expand(store,root)
            from .findings import index_pending
            index_pending(store)
            job=store.claim(c)
            if not job:return imported
            try:
                output=(runner or execute_child)(store,c,job,root)
                store.complete(c,job,output)
            except Exception as exc:
                store.fail(c,job,getattr(exc,'error_code',type(exc).__name__))
            expand(store,root)
            index_pending(store)
            return True
        finally:
            c.execute('SELECT pg_advisory_unlock(%s)',(LOCK_KEY,));c.commit()


def execute_child(store,c,job,root,progress_reporter=None):
    from .messages import team_audio,is_team_sender
    # Recheck older queued jobs too; sender inference is never based on proximity.
    if job['stage']=='audio' and team_audio(store,job['evidence_id']):
        return {'result':{'text':'','segments':[],'excluded':'team_sender_audio'},
                'metrics':{'wall_seconds':0},'model_identity':{'provider':'sender_filter'}}
    payload=dict(job['payload'])
    if job['stage']=='text':
        mids=[s['message_id'] for s in payload.get('sources',[]) if s.get('message_id')]
        if mids:
            with store.connect() as lookup:
                rows=lookup.execute('SELECT id,sender_visible FROM messages WHERE id=ANY(%s::uuid[])',(mids,)).fetchall()
            excluded={str(row['id']) for row in rows if is_team_sender(row['sender_visible'])}
            payload['sources']=[s for s in payload.get('sources',[]) if s.get('message_id') not in excluded]
        if team_audio(store,job['evidence_id']):payload['sources']=[]
        if not payload.get('sources'):
            return {'result':{'extraction':{'summary':'','assertions':[]},'excluded':'team_sender'},
                    'metrics':{'wall_seconds':0},'model_identity':{'provider':'sender_filter'}}
    folder=contained(root,f"runs/{job['run_id']}");folder.mkdir(parents=True,exist_ok=True)
    spec={'storage':str(root),'path':job['storage_path'],'sha256':job['sha256'],
          'output_dir':str(folder.relative_to(root)/'artifacts'),'stage':job['stage'],
          'config':job['config'],'payload':payload,'evidence_id':str(job['evidence_id'])}
    atomic_json(folder/'input.json',spec)
    result_file=folder/'output.json'
    progress_file=folder/'progress.json';last_progress=[None]
    deadline=time.monotonic()+job['config']['timeout_seconds']
    with (folder/'process.log').open('wb') as log:
        process=subprocess.Popen([sys.executable,'-m','semaforos.inference',str(folder/'input.json'),str(result_file)],
                                  stdout=log,stderr=log,start_new_session=True)
        try:
            while process.poll() is None:
                store.heartbeat(c,job)
                if progress_reporter and progress_file.is_file():
                    try:
                        current=json.loads(progress_file.read_text()[:8192])
                        signature=tuple(current.get(key) for key in
                                        ('phase','fraction','current','total','characters'))
                        if signature!=last_progress[0]:
                            progress_reporter(current);last_progress[0]=signature
                    except (OSError,ValueError,TypeError):pass
                if time.monotonic()>deadline:raise TimeoutError('inference_timeout')
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
            if process.returncode:
                try:code=json.loads(result_file.read_text()).get('error_code')
                except (OSError,ValueError,AttributeError):code='adapter_failed'
                raise AdapterFailure(code)
            output=json.loads(result_file.read_text())
            if set(('result','metrics','model_identity'))-output.keys():raise ValueError('invalid_adapter_output')
            return output
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait()


def main():
    from .config import storage_root
    store=Store();root=storage_root()
    while True:
        try:
            if not once(store,root):time.sleep(2)
        except Exception as exc:
            print(json.dumps({'event':'worker_error','code':type(exc).__name__}),flush=True)
            time.sleep(5)


if __name__=='__main__':main()
