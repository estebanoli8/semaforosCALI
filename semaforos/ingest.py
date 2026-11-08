"""Importación privada de ZIP locales; originales inmutables y espacio controlado."""
import mimetypes
import hashlib
from uuid import uuid4
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile
from .files import contained, sha256, canonical_hash
from .worker import text_chunks

MODES={'.txt':'chat','.jpg':'image','.jpeg':'image','.png':'image','.webp':'image',
       '.opus':'audio','.ogg':'audio','.m4a':'audio','.mp3':'audio','.wav':'audio',
       '.mp4':'video','.mov':'video','.webm':'video','.3gp':'video','.mkv':'video','.avi':'video','.m4v':'video'}


def import_zip(store,root,source,config,experiment):
    source=Path(source);digest=sha256(source)
    reserve=int(os.getenv('SC_RESERVE_BYTES',str(3*1024**3)))
    with zipfile.ZipFile(source) as archive:
        entries=archive.infolist()
        if len(entries)>100000:raise ValueError('too_many_zip_entries')
        seen=set();expanded=0
        for item in entries:
            p=PurePosixPath(item.filename.replace('\\','/'))
            if p.is_absolute() or '..' in p.parts or not p.parts or ':' in p.parts[0] or stat.S_ISLNK(item.external_attr>>16):raise ValueError('unsafe_zip_path')
            if str(p) in seen:raise ValueError('duplicate_zip_path')
            seen.add(str(p));expanded+=item.file_size
        if shutil.disk_usage(root).free<reserve+expanded+source.stat().st_size:raise ValueError('insufficient_disk_space')
        manifest=[]
        for item in entries:
            if item.is_dir() or item.filename.startswith('__MACOSX/'):continue
            h=hashlib.sha256()
            with archive.open(item) as stream:
                for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
            manifest.append((str(PurePosixPath(item.filename.replace('\\','/'))),h.hexdigest()))
        content_hash=canonical_hash(sorted(manifest))
        cid=store.conversation(content_hash,source.stem,{'content_hash':content_hash,'version_link':'requires_review'})
        folder=contained(root,f'originals/{cid}');folder.mkdir(parents=True,exist_ok=True)
        original=folder/'archives'/digest/source.name
        original.parent.mkdir(parents=True,exist_ok=True)
        if not original.exists():
            tmp=original.with_suffix('.tmp')
            try:
                shutil.copyfile(source,tmp);tmp.replace(original)
            finally:tmp.unlink(missing_ok=True)
        elif sha256(original)!=digest:raise ValueError('stored_zip_modified')
        with store.connect() as c:
            c.execute('INSERT INTO source_archives(id,conversation_id,sha256,original_name,storage_path,size_bytes) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(storage_path) DO NOTHING',
                      (uuid4(),cid,digest,source.name,str(original.relative_to(root)),source.stat().st_size))
            canonical_name=c.execute('SELECT original_name FROM conversations WHERE id=%s',(cid,)).fetchone()['original_name']
        ids=[];scheduled=[]
        # source.zip y carpeta original separados para evitar colisiones de nombres internos.
        original_folder=folder/'contents'/canonical_name
        for item in entries:
            if item.is_dir() or item.filename.startswith('__MACOSX/'):continue
            relative=PurePosixPath(item.filename.replace('\\','/'))
            target=contained(original_folder,str(relative));target.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=folder,delete=False) as handle:tmp=Path(handle.name)
            try:
                with archive.open(item) as src,tmp.open('wb') as dest:
                    while block:=src.read(1024**2):
                        if shutil.disk_usage(root).free<reserve+len(block):raise ValueError('insufficient_disk_space')
                        dest.write(block)
                actual=sha256(tmp)
                if target.exists():
                    if sha256(target)!=actual:raise ValueError('immutable_file_changed')
                else:tmp.replace(target)
            finally:tmp.unlink(missing_ok=True)
            modality=MODES.get(target.suffix.lower(),'other')
            eid=store.evidence(cid,str(target.relative_to(root)),modality,item.filename,target.stat().st_size,actual,
                               {'zip_sha256':digest,'zip_filename':source.name,'original_folder':source.stem,'mime':mimetypes.guess_type(target.name)[0]})
            ids.append(str(eid))
            stage={'image':'detect','audio':'audio','video':'video'}.get(modality)
            if stage:scheduled.append((eid,stage,{}))
            elif modality=='chat':
                if target.stat().st_size>32*1024**2:raise ValueError('chat_requires_streaming_parser')
                text=target.read_text(encoding='utf-8-sig')
                with store.connect() as c:
                    c.execute('INSERT INTO source_texts(evidence_id,literal_text) VALUES(%s,%s) ON CONFLICT(evidence_id) DO NOTHING',(eid,text))
                for sources in text_chunks(text,eid,'chat'):
                    scheduled.append((eid,'text',{'sources':sources}))
        for eid,stage,payload in scheduled:store.enqueue(eid,stage,experiment,config,payload)
        return {'conversation_id':str(cid),'evidence_ids':ids,'zip_sha256':digest}
