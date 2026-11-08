"""Inventario por contenido y candidatas de versión; nunca fusiona reportes."""
import hashlib
import json
import re
import unicodedata
import zipfile
from pathlib import PurePosixPath

def family(name):
    value = re.sub('[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', name)
    value = unicodedata.normalize('NFC', value).replace('\xa0', ' ').replace('\u202f', ' ')
    value = re.sub(r'\s*\(\d+\)(?=\.zip$)', '', value, flags=re.I)
    return value.casefold().strip()

def content_manifest(path):
    files = []
    seen = set()
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or entry.filename.startswith('__MACOSX/'):
                continue
            normalized = str(PurePosixPath(entry.filename.replace('\\', '/')))
            if normalized in seen:
                raise ValueError('ZIP con rutas duplicadas: ' + normalized)
            seen.add(normalized)
            digest = hashlib.sha256()
            with archive.open(entry) as stream:
                for block in iter(lambda: stream.read(1024*1024), b''):
                    digest.update(block)
            files.append(dict(archivo=normalized, bytes=entry.file_size, sha256=digest.hexdigest(),
                              fecha_interna_zip=list(entry.date_time)))
    canonical = sorted((f['archivo'], f['sha256']) for f in files)
    return dict(huella_contenido=hashlib.sha256(json.dumps(canonical, ensure_ascii=False).encode()).hexdigest(),
                archivos=files)
