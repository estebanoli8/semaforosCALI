"""Carga reanudable, duradera y acotada en memoria. Una réplica del servidor.

SQLite registra sesiones, no reemplaza la futura base de dominio PostgreSQL.
Los archivos completos se validan fuera de la petición HTTP.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path


class Uploads:
    def __init__(self, root, reserve_bytes=3 * 1024**3, chunk_bytes=4 * 1024**2):
        self.root = Path(root)
        self.folder = self.root / 'cargas'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.reserve = reserve_bytes
        self.chunk_bytes = chunk_bytes
        self.lock = threading.RLock()
        with self.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL,
                received INTEGER NOT NULL, state TEXT NOT NULL, error TEXT NOT NULL,
                result TEXT, created REAL NOT NULL, updated REAL NOT NULL)''')
            c.execute("UPDATE uploads SET state='pendiente' WHERE state='validando'")

    def connect(self):
        c = sqlite3.connect(self.root / 'cargas.sqlite', timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def path(self, ident):
        if not re.fullmatch('[a-f0-9]{32}', ident):
            raise ValueError('ID de carga inválido')
        return self.folder / (ident + '.part')

    def get(self, ident):
        self.path(ident)
        with self.connect() as c:
            row = c.execute('SELECT * FROM uploads WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise ValueError('Carga no encontrada')
        data = dict(row)
        if data['result']:
            data['result'] = json.loads(data['result'])
        return data

    def create(self, name, size):
        if (not isinstance(name, str) or not name.lower().endswith('.zip')
                or '/' in name or '\\' in name or '\x00' in name or len(name) > 512):
            raise ValueError('Nombre de ZIP inválido')
        if type(size) is not int or size <= 0 or size > 2**53 - 1:
            raise ValueError('Tamaño inválido')
        with self.lock:
            with self.connect() as c:
                reserved = c.execute("SELECT COALESCE(SUM(size-received),0) FROM uploads WHERE state='recibiendo'").fetchone()[0]
                if shutil.disk_usage(self.root).free < self.reserve + size + reserved:
                    raise ValueError('Espacio insuficiente: se preserva la reserva y las cargas en curso')
                ident = uuid.uuid4().hex
                self.path(ident).touch(exist_ok=False)
                now = time.time()
                c.execute('INSERT INTO uploads VALUES(?,?,?,?,?,?,?,?,?)',
                          (ident, name, size, 0, 'recibiendo', '', None, now, now))
            return self.get(ident)

    def check(self, ident, offset, length, digest):
        """Verifica bloques existentes al reanudar; nombre/fecha no prueban igualdad."""
        if (type(offset) is not int or type(length) is not int or offset < 0
                or not 0 < length <= self.chunk_bytes or not re.fullmatch('[a-f0-9]{64}', digest)):
            raise ValueError('Bloque inválido')
        with self.lock:
            row = self.get(ident)
            if row['state'] != 'recibiendo':
                raise ValueError('La carga ya no recibe bloques')
            if offset + length > row['size']:
                raise ValueError('Bloque excede tamaño declarado')
            if offset == row['received']:
                return False
            if offset + length > row['received']:
                raise ValueError('Orden de bloques incorrecto')
            with self.path(ident).open('rb') as f:
                f.seek(offset)
                actual = hashlib.sha256(f.read(length)).hexdigest()
            if actual != digest:
                raise ValueError('El archivo seleccionado no coincide con los bloques guardados')
            return True

    def append(self, ident, offset, data, digest):
        if not data or len(data) > self.chunk_bytes or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Contenido o huella del bloque inválido')
        with self.lock:
            if self.check(ident, offset, len(data), digest):
                return self.get(ident)  # Repetición de una petición confirmada antes de desconectarse.
            if shutil.disk_usage(self.root).free < self.reserve + len(data):
                raise ValueError('Carga pausada por espacio insuficiente')
            target = self.path(ident)
            with target.open('r+b') as f:
                # Descartar una escritura que no alcanzó a confirmarse en SQLite.
                f.truncate(offset)
                f.seek(offset)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            with self.connect() as c:
                c.execute('UPDATE uploads SET received=?,updated=? WHERE id=?',
                          (offset + len(data), time.time(), ident))
            return self.get(ident)

    def finish(self, ident):
        with self.lock:
            row = self.get(ident)
            if row['state'] == 'recibiendo':
                if row['received'] != row['size']:
                    raise ValueError('Todavía faltan bloques')
                with self.connect() as c:
                    c.execute("UPDATE uploads SET state='pendiente',updated=? WHERE id=?", (time.time(), ident))
            return self.get(ident)

    def cancel(self, ident):
        with self.lock:
            row = self.get(ident)
            if row['state'] not in ('recibiendo', 'error', 'cancelado'):
                raise ValueError('Solo se cancelan cargas incompletas o con error')
            with self.connect() as c:
                c.execute("UPDATE uploads SET state='cancelado',updated=? WHERE id=?", (time.time(), ident))
            self.path(ident).unlink(missing_ok=True)

    def process_one(self, register):
        with self.lock:
            with self.connect() as c:
                row = c.execute("SELECT * FROM uploads WHERE state='pendiente' ORDER BY created LIMIT 1").fetchone()
                if row is None:
                    return False
                c.execute("UPDATE uploads SET state='validando',updated=? WHERE id=?", (time.time(), row['id']))
        target = self.path(row['id'])
        staging = target.with_suffix('.register')
        try:
            # El registrador puede mover su entrada. Mantener el original hasta
            # confirmar estado permite reintentar tras caída entre mover y guardar.
            staging.unlink(missing_ok=True)
            os.link(target, staging)
            result = register(staging, row['name'])
            with self.connect() as c:
                c.execute("UPDATE uploads SET state='recibido',result=?,error='',updated=? WHERE id=?",
                          (json.dumps(result, ensure_ascii=False), time.time(), row['id']))
            target.unlink(missing_ok=True)
        except Exception as exc:
            with self.connect() as c:
                c.execute("UPDATE uploads SET state='error',error=?,updated=? WHERE id=?",
                          (str(exc)[:1000], time.time(), row['id']))
        finally:
            staging.unlink(missing_ok=True)
        return True

    def listing(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT id,name,size,received,state,error FROM uploads ORDER BY created DESC LIMIT 200')]
