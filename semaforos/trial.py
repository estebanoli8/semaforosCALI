"""Una inferencia controlada con configuración actual; no drena la cola existente."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import time
from .config import load_config, storage_root
from .store import LOCK_KEY, Store
from .worker import execute_child


def run_trial(store, root, config, stage, experiment, runner=None):
    if stage not in ('text','lights'):raise ValueError('invalid_trial_stage')
    with store.connect() as c:
        if not c.execute('SELECT pg_try_advisory_lock(%s) AS acquired',(LOCK_KEY,)).fetchone()['acquired']:
            raise RuntimeError('worker_still_running')
        c.commit()
        try:
            # Elegir la entrada más pequeña que ya falló. No muestra contenido ciudadano.
            source=c.execute('''SELECT * FROM jobs WHERE stage=%s AND state='failed'
                ORDER BY length(payload::text),created_at LIMIT 1''',(stage,)).fetchone()
            # La próxima transacción debe tener un now() posterior al alta del trabajo.
            c.commit()
            if not source:raise ValueError('no_failed_source_for_trial')
            cfg=deepcopy(config);cfg['max_attempts']=1
            ident=store.enqueue(source['evidence_id'],stage,experiment,cfg,source['payload'])
            job=store.claim(c,job_id=ident)
            if not job:return {'job_id':str(ident),'status':'already_attempted'}
            try:
                started=time.monotonic();last=[None]
                def report(progress):
                    phase=str(progress.get('phase') or 'Procesando')
                    fraction=progress.get('fraction')
                    percent=f' · {max(0,min(100,round(fraction*100)))}%' if isinstance(fraction,(int,float)) else ''
                    marker=(phase,percent,progress.get('characters'))
                    if marker!=last[0]:
                        print(f'[{time.monotonic()-started:5.0f}s] {phase}{percent}',flush=True)
                        last[0]=marker
                output=(runner(store,c,job,root) if runner else
                        execute_child(store,c,job,root,progress_reporter=report))
                store.complete(c,job,output)
                return {'job_id':str(ident),'run_id':str(job['run_id']),'stage':stage,
                        'status':'completed','seconds':output['metrics'].get('wall_seconds')}
            except Exception as exc:
                code=getattr(exc,'error_code',type(exc).__name__)
                store.fail(c,job,code)
                return {'job_id':str(ident),'run_id':str(job['run_id']),'stage':stage,
                        'status':'failed','error_code':code}
        finally:
            c.execute('SELECT pg_advisory_unlock(%s)',(LOCK_KEY,));c.commit()


def main():
    if os.getenv('SC_PROCESS','all').strip().lower()!='api':
        raise SystemExit('DETENIDO: desplegar primero con SC_PROCESS=api para mantener la cola detenida.')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['text','lights'],required=True)
    parser.add_argument('--experiment',default='prueba-controlada-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    args=parser.parse_args()
    print('Iniciando una sola tarea de '+args.stage+'. El avance aparece en el panel privado.',flush=True)
    result=run_trial(Store(),storage_root(),load_config(),args.stage,args.experiment)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='completed' else 1


if __name__=='__main__':raise SystemExit(main())
