"""ZIP por bloques. PostgreSQL confirma offsets; el trabajador importa fuera de HTTP."""
import hashlib
import os
from pathlib import Path
import re
import shutil
from uuid import UUID, uuid4
from psycopg.types.json import Jsonb
from .files import canonical_hash, contained
from .store import LOCK_KEY

CHUNK_BYTES = 4 * 1024**2
DISK_LOCK = LOCK_KEY + 2


class UploadError(ValueError):
    pass


class Uploads:
    def __init__(self, store, root, reserve=None):
        self.store = store
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.reserve = int(os.getenv('SC_RESERVE_BYTES', str(3 * 1024**3))) if reserve is None else reserve
        if self.reserve < 0:raise ValueError('invalid_disk_reserve')

    def path(self, row):
        return contained(self.root, f"uploads/{UUID(str(row['id']))}/{row['original_name']}")

    @staticmethod
    def public(row):
        return {key:row[key] for key in ('id','original_name','size_bytes','received_bytes','state',
                    'experiment_id','config_hash','attempts','result','error_code','created_at','updated_at')}

    def get(self, ident):
        with self.store.connect() as c:
            row=c.execute('SELECT * FROM uploads WHERE id=%s',(ident,)).fetchone()
        if not row:raise UploadError('upload_not_found')
        return self.public(row)

    def create(self, name, size, experiment, config):
        if (not isinstance(name,str) or not name.lower().endswith('.zip') or '/' in name
                or '\\' in name or any(ord(x)<32 for x in name) or len(name.encode('utf-8'))>240):
            raise UploadError('invalid_zip_name')
        if type(size) is not int or not 0<size<=2**53-1:raise UploadError('invalid_size')
        if not isinstance(experiment,str) or not 1<=len(experiment.strip())<=100:raise UploadError('invalid_experiment')
        row={'id':uuid4(),'original_name':name}
        path=self.path(row)
        try:
            with self.store.connect() as c:
                c.execute('SELECT pg_advisory_xact_lock(%s)',(DISK_LOCK,))
                reserved=c.execute("SELECT coalesce(sum(size_bytes-received_bytes),0) AS n FROM uploads WHERE state='receiving'").fetchone()['n']
                if shutil.disk_usage(self.root).free<self.reserve+size+reserved:raise UploadError('insufficient_disk_space')
                path.parent.mkdir(parents=True,exist_ok=True);path.touch(exist_ok=False)
                row=c.execute('''INSERT INTO uploads(id,original_name,size_bytes,experiment_id,config,config_hash)
                    VALUES(%s,%s,%s,%s,%s,%s) RETURNING *''',
                    (row['id'],name,size,experiment.strip(),Jsonb(config),canonical_hash(config))).fetchone()
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return self.public(row)

    def append(self, ident, offset, data, digest):
        if (type(offset) is not int or offset<0 or not 0<len(data)<=CHUNK_BYTES
                or not re.fullmatch('[a-f0-9]{64}',digest) or hashlib.sha256(data).hexdigest()!=digest):
            raise UploadError('invalid_chunk')
        with self.store.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(%s)',(DISK_LOCK,))
            row=c.execute('SELECT * FROM uploads WHERE id=%s FOR UPDATE',(ident,)).fetchone()
            if not row:raise UploadError('upload_not_found')
            if row['state']!='receiving':raise UploadError('upload_not_receiving')
            if offset+len(data)>row['size_bytes']:raise UploadError('chunk_exceeds_size')
            path=self.path(row)
            if offset<row['received_bytes']:
                if offset+len(data)>row['received_bytes']:raise UploadError('chunk_order_conflict')
                with path.open('rb') as f:
                    f.seek(offset);existing=f.read(len(data))
                if hashlib.sha256(existing).hexdigest()!=digest:raise UploadError('resume_content_mismatch')
                return self.public(row)
            if offset!=row['received_bytes']:raise UploadError('chunk_order_conflict')
            if shutil.disk_usage(self.root).free<self.reserve+len(data):raise UploadError('insufficient_disk_space')
            with path.open('r+b') as f:
                if f.seek(0,2)<offset:raise UploadError('stored_chunk_missing')
                # Una caída entre fsync y COMMIT deja una cola no confirmada, que se descarta.
                f.truncate(offset);f.seek(offset);f.write(data);f.flush();os.fsync(f.fileno())
            row=c.execute('UPDATE uploads SET received_bytes=%s,updated_at=now() WHERE id=%s RETURNING *',
                          (offset+len(data),ident)).fetchone()
        return self.public(row)

    def finish(self, ident):
        with self.store.connect() as c:
            row=c.execute('SELECT * FROM uploads WHERE id=%s FOR UPDATE',(ident,)).fetchone()
            if not row:raise UploadError('upload_not_found')
            if row['state']=='receiving':
                if row['received_bytes']!=row['size_bytes']:raise UploadError('upload_incomplete')
                if self.path(row).stat().st_size!=row['size_bytes']:raise UploadError('stored_size_mismatch')
                row=c.execute("UPDATE uploads SET state='queued',updated_at=now() WHERE id=%s RETURNING *",(ident,)).fetchone()
            elif row['state'] not in ('queued','importing','received'):raise UploadError('invalid_upload_state')
        return self.public(row)

    def cancel(self, ident):
        with self.store.connect() as c:
            row=c.execute('SELECT * FROM uploads WHERE id=%s FOR UPDATE',(ident,)).fetchone()
            if not row:raise UploadError('upload_not_found')
            if row['state'] not in ('receiving','queued','error','cancelled'):raise UploadError('cannot_cancel_import')
            row=c.execute("UPDATE uploads SET state='cancelled',updated_at=now() WHERE id=%s RETURNING *",(ident,)).fetchone()
        self.path(row).unlink(missing_ok=True)
        return self.public(row)

    def retry(self, ident):
        with self.store.connect() as c:
            row=c.execute('SELECT * FROM uploads WHERE id=%s FOR UPDATE',(ident,)).fetchone()
            if not row:raise UploadError('upload_not_found')
            if row['state']!='error':raise UploadError('only_errors_can_retry')
            if not self.path(row).is_file():raise UploadError('stored_zip_missing')
            row=c.execute("UPDATE uploads SET state='queued',attempts=0,error_code=NULL,updated_at=now() WHERE id=%s RETURNING *",(ident,)).fetchone()
        return self.public(row)

    def process_locked(self, ident):
        """Importa exactamente una carga. Solo bajo LOCK_KEY de sesión."""
        from .ingest import import_zip
        # El archivo original ya es durable antes de confirmar 'received'. Si hubo
        # caída después del COMMIT, eliminar exclusivamente la copia de transporte.
        with self.store.connect() as c:
            finished=c.execute("SELECT id,original_name FROM uploads WHERE state IN ('received','cancelled') AND NOT transport_cleaned LIMIT 50").fetchall()
        for item in finished:
            self.path(item).unlink(missing_ok=True)
            with self.store.connect() as c:c.execute('UPDATE uploads SET transport_cleaned=true WHERE id=%s',(item['id'],))
        with self.store.connect() as c:
            row=c.execute("SELECT * FROM uploads WHERE id=%s AND state IN ('queued','importing') FOR UPDATE SKIP LOCKED",(ident,)).fetchone()
            if not row:return None
            if row['attempts']>=3:
                c.execute("UPDATE uploads SET state='error',error_code='import_interrupted_repeatedly',updated_at=now() WHERE id=%s",(row['id'],))
                return self.get(ident)
            c.execute("UPDATE uploads SET state='importing',attempts=attempts+1,updated_at=now() WHERE id=%s",(row['id'],))
        try:
            result=import_zip(self.store,self.root,self.path(row),row['config'],row['experiment_id'])
            with self.store.connect() as c:
                c.execute("UPDATE uploads SET state='received',result=%s,error_code=NULL,updated_at=now() WHERE id=%s",(Jsonb(result),row['id']))
        except Exception as exc:
            # Nunca devolver texto de conexión, claves o contenido ciudadano como error.
            known={'insufficient_disk_space','unsafe_zip_path','duplicate_zip_path','too_many_zip_entries',
                   'chat_requires_streaming_parser','stored_zip_modified','immutable_file_changed'}
            code=str(exc) if str(exc) in known else type(exc).__name__
            with self.store.connect() as c:
                c.execute("UPDATE uploads SET state='error',error_code=%s,updated_at=now() WHERE id=%s",(code,row['id']))
            return self.get(ident)
        # Si falla la limpieza, el próximo ciclo la recupera; no degradar una
        # importación ya confirmada a error ni volver a inferir sus archivos.
        try:
            self.path(row).unlink(missing_ok=True)
            with self.store.connect() as c:c.execute('UPDATE uploads SET transport_cleaned=true WHERE id=%s',(row['id'],))
        except OSError:pass
        return self.get(ident)

    def process_one_locked(self):
        """Importa la carga más antigua. Solo bajo LOCK_KEY de sesión."""
        with self.store.connect() as c:
            row=c.execute("SELECT id FROM uploads WHERE state IN ('queued','importing') ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if not row:return False
        self.process_locked(row['id'])
        return True
