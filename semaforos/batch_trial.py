"""Procesa una carga elegida sin drenar la cola histórica."""
import argparse
import json
import os
import time
from uuid import UUID
from .config import storage_root
from .findings import index_pending
from .store import LOCK_KEY, Store
from .uploads import Uploads
from .worker import execute_child, expand


LABELS={'audio':'Audio → texto','detect':'Detección de semáforos','lights':'Revisión de luces',
        'text':'Extracción de datos','video':'Preparación de video'}


def queued(store):
    with store.connect() as c:
        return c.execute("""SELECT id,original_name,state,experiment_id,received_bytes,created_at
            FROM uploads WHERE state IN ('queued','importing') ORDER BY created_at,id""").fetchall()


def counts(store, conversation_id):
    with store.connect() as c:
        rows=c.execute("""SELECT j.state,count(*) AS n FROM jobs j JOIN evidence e ON e.id=j.evidence_id
            WHERE e.conversation_id=%s GROUP BY j.state""",(conversation_id,)).fetchall()
    return {row['state']:row['n'] for row in rows}


def run_upload(store, root, upload_id, max_jobs=500):
    uploads=Uploads(store,root)
    with store.connect() as lock:
        if not lock.execute('SELECT pg_try_advisory_lock(%s) AS acquired',(LOCK_KEY,)).fetchone()['acquired']:
            raise RuntimeError('worker_still_running')
        lock.commit()
        try:
            upload=uploads.process_locked(upload_id)
            if not upload:raise ValueError('upload_not_queued')
            if upload['state']!='received':return {'upload_id':str(upload_id),'status':upload['state'],'error_code':upload['error_code']}
            conversation_id=upload['result']['conversation_id']
            started=time.monotonic();executed=0
            while executed<max_jobs:
                expand(store,root,conversation_id)
                index_pending(store,conversation_id)
                job=store.claim(lock,conversation_id=conversation_id)
                current=counts(store,conversation_id)
                total=sum(current.values());done=current.get('completed',0)+current.get('failed',0)
                if not job:
                    if not current.get('pending',0) and not current.get('running',0):break
                    time.sleep(2);continue
                executed+=1
                label=LABELS.get(job['stage'],job['stage'])
                print(f"\n[{done}/{total}] {label} · {job['original_name']} · intento {job['attempts']}",flush=True)
                last=[None]
                def report(progress):
                    fraction=progress.get('fraction');pct=(round(fraction*100) if isinstance(fraction,(int,float)) else None)
                    marker=(progress.get('phase'),pct,progress.get('current'),progress.get('characters'))
                    if marker!=last[0]:
                        print(f"  {progress.get('phase') or label}"+(f" · {pct}%" if pct is not None else ''),flush=True)
                        last[0]=marker
                try:
                    output=execute_child(store,lock,job,root,progress_reporter=report)
                    store.complete(lock,job,output);print('  ✅ Completado',flush=True)
                except Exception as exc:
                    code=getattr(exc,'error_code',type(exc).__name__)
                    store.fail(lock,job,code);print(f'  ❌ {code}',flush=True)
            expand(store,root,conversation_id);index_pending(store,conversation_id)
            final=counts(store,conversation_id)
            status='limit_reached' if final.get('pending',0) or final.get('running',0) else 'finished'
            return {'upload_id':str(upload_id),'conversation_id':str(conversation_id),'status':status,
                    'seconds':round(time.monotonic()-started,1),'jobs':final}
        finally:
            lock.execute('SELECT pg_advisory_unlock(%s)',(LOCK_KEY,));lock.commit()


def main():
    if os.getenv('SC_PROCESS','all').strip().lower()!='api':
        raise SystemExit('DETENIDO: SC_PROCESS debe ser api para no mezclar la cola histórica.')
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list',action='store_true',help='lista cargas pendientes')
    group.add_argument('--queued-one',action='store_true',help='procesa solo si existe exactamente una carga pendiente')
    group.add_argument('--upload-id',type=UUID,help='procesa exactamente este ID')
    parser.add_argument('--max-jobs',type=int,default=500)
    args=parser.parse_args();store=Store()
    rows=queued(store)
    if args.list:
        for row in rows:print(json.dumps({key:str(value) for key,value in row.items()},ensure_ascii=False))
        return 0
    if args.queued_one:
        if len(rows)!=1:raise SystemExit(f'DETENIDO: hay {len(rows)} cargas pendientes; usa --list y --upload-id.')
        ident=rows[0]['id']
    else:ident=args.upload_id
    print(f'Procesamiento aislado de la carga {ident}. La cola histórica no se tocará.',flush=True)
    result=run_upload(store,storage_root(),ident,args.max_jobs)
    print('\n'+json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result.get('status')=='finished' else 1


if __name__=='__main__':raise SystemExit(main())
