import argparse
import json
from pathlib import Path
from .store import Store,LOCK_KEY
from .config import load_config,storage_root
from .ingest import import_zip


def main():
    parser=argparse.ArgumentParser(description='Núcleo privado Semáforos Cali')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('migrate')
    p=sub.add_parser('import');p.add_argument('zip',nargs='+');p.add_argument('--experiment',required=True)
    sub.add_parser('worker')
    args=parser.parse_args();store=Store()
    if args.command=='migrate':store.migrate();print('Migraciones aplicadas en base exclusiva de Semáforos.')
    elif args.command=='worker':
        from .worker import main as worker_main
        worker_main()
    else:
        config=load_config();root=storage_root()
        with store.connect() as c:
            if not c.execute('SELECT pg_try_advisory_lock(%s) AS ok',(LOCK_KEY,)).fetchone()['ok']:
                raise SystemExit('Trabajador ocupado. Usa la carga web para dejar el ZIP en cola.')
            c.commit()
            try:
                for source in args.zip:
                    try:print(json.dumps(import_zip(store,root,Path(source),config,args.experiment)))
                    except Exception as exc:print(json.dumps({'status':'error','code':type(exc).__name__}))
            finally:c.execute('SELECT pg_advisory_unlock(%s)',(LOCK_KEY,));c.commit()

if __name__=='__main__':main()
