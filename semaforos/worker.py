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


def text_chunks(text, source_id, origin):
    # Los fragmentos se conservan completos en cada salida; no generan reportes por sí solos.
    for offset in range(0,len(text),2400):
        yield [{'id':f'{source_id}:{offset}','text':text[offset:offset+2400],
                'origin':origin,'source_id':str(source_id),'char_start':offset}]


def expand(store, root, conversation_id=None):
    """Reconciliación idempotente: recupera una caída tras guardar la predicción."""
    with store.connect() as c:
        rows=c.execute("""SELECT j.*,r.id AS run_id,r.output,e.storage_path,e.conversation_id,e.modality
            FROM jobs j JOIN runs r ON r.job_id=j.id AND r.state='completed'
            JOIN evidence e ON e.id=j.evidence_id
            WHERE j.state='completed' AND j.expanded_at IS NULL
            AND (%s::uuid IS NULL OR e.conversation_id=%s::uuid)
            ORDER BY j.created_at LIMIT 20""",(conversation_id,conversation_id)).fetchall()
    for job in rows:
        try:
            result=job['output'];config=job['config'];experiment=job['experiment_id']
            if job['stage']=='audio':
                origin='audio_video' if job['payload'].get('from_video') else 'audio_whatsapp'
                for sources in text_chunks(result['text'],job['run_id'],origin):
                    store.enqueue(job['evidence_id'],'text',experiment,config,{'sources':sources,'transcription_run_id':str(job['run_id'])})
            elif job['stage']=='detect':
                with store.connect() as c:
                    detections=c.execute('SELECT id,bbox FROM detections WHERE run_id=%s ORDER BY object_index',(job['run_id'],)).fetchall()
                if detections:
                    store.enqueue(job['evidence_id'],'lights',experiment,config,{'detections':[{'id':str(d['id']),'bbox':d['bbox']} for d in detections],'detector_run_id':str(job['run_id'])})
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
    folder=contained(root,f"runs/{job['run_id']}");folder.mkdir(parents=True,exist_ok=True)
    spec={'storage':str(root),'path':job['storage_path'],'sha256':job['sha256'],
          'output_dir':str(folder.relative_to(root)/'artifacts'),'stage':job['stage'],
          'config':job['config'],'payload':job['payload'],'evidence_id':str(job['evidence_id'])}
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
