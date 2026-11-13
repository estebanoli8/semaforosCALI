"""Two bounded lanes; maintenance remains serialized and jobs retain their leases."""
import sys
import time
import json
from .store import Store, LOCK_KEY
from .config import storage_root
from .uploads import Uploads
from .worker import expand, execute_child
from .findings import index_pending


def once(store,root,lane):
    key=LOCK_KEY+(10 if lane=='text' else 11)
    stages=['text','lights'] if lane=='text' else ['audio','detect','video']
    with store.connect() as c:
        if not c.execute('SELECT pg_try_advisory_lock(%s) AS ok',(key,)).fetchone()['ok']:
            c.commit();return False
        c.commit()
        try:
            # Shared global lock prevents overlap with legacy/diagnostic workers.
            if not c.execute('SELECT pg_try_advisory_lock_shared(%s) AS ok',(LOCK_KEY,)).fetchone()['ok']:
                c.commit();return False
            c.commit()
            try:
                with store.connect() as maintenance:
                    maintenance.execute('SELECT pg_advisory_lock(%s)',(LOCK_KEY+12,));maintenance.commit()
                    try:
                        Uploads(store,root).process_one_locked()
                        expand(store,root);index_pending(store)
                        candidate=maintenance.execute("""SELECT id FROM jobs WHERE stage=ANY(%s)
                            AND ((state='pending' AND available_at<=now()) OR (state='running' AND lease_until<now()))
                            ORDER BY created_at LIMIT 1""",(stages,)).fetchone()
                        maintenance.commit()
                    finally:
                        maintenance.execute('SELECT pg_advisory_unlock(%s)',(LOCK_KEY+12,));maintenance.commit()
                if not candidate:return False
                job=store.claim(c,job_id=candidate['id'])
                if not job:return False
                print(json.dumps({'lane':lane,'stage':job['stage'],'event':'started','job_id':str(job['id'])}),flush=True)
                try:store.complete(c,job,execute_child(store,c,job,root))
                except Exception as exc:store.fail(c,job,getattr(exc,'error_code',type(exc).__name__))
                return True
            finally:
                c.execute('SELECT pg_advisory_unlock_shared(%s)',(LOCK_KEY,));c.commit()
        finally:
            c.execute('SELECT pg_advisory_unlock(%s)',(key,));c.commit()


def main():
    lane=sys.argv[1]
    if lane not in ('text','media'):raise SystemExit('invalid_lane')
    store=Store();root=storage_root()
    while True:
        try:
            if not once(store,root,lane):time.sleep(2)
        except Exception as exc:
            print(json.dumps({'lane':lane,'error':type(exc).__name__}),flush=True);time.sleep(5)


if __name__=='__main__':main()
