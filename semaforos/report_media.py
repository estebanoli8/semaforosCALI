"""Private report viewing with a short-lived team session."""
import hashlib
import hmac
import mimetypes
import os
import re
import secrets
import tempfile
import time
from pathlib import Path
from typing import Literal
from uuid import UUID
from urllib.parse import urlsplit

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from PIL import Image, ImageOps

from .files import contained
from .report_map import snapshot
from .reports import ReportError

COOKIE = 'sc_team_session'
PREFIX = '/report-media'
SESSION_SECONDS = 4 * 60 * 60
SESSION_PATTERN = re.compile(r'[0-9]{1,12}\.[A-Za-z0-9_-]{24}\.[a-f0-9]{64}')


def sign(key, value):
    return hmac.new(key.encode(),value.encode(),hashlib.sha256).hexdigest()


def new_session(key):
    identity = f'{int(time.time())+SESSION_SECONDS}.{secrets.token_urlsafe(18)}'
    return f'{identity}.{sign(key,"session|"+identity)}'


def session_identity(key, cookie):
    if not SESSION_PATTERN.fullmatch(cookie):
        raise HTTPException(401,'Acceso del equipo requerido')
    identity,proof=cookie.rsplit('.',1)
    expires,_=identity.split('.',1)
    if int(expires)<=time.time() or not hmac.compare_digest(proof,sign(key,'session|'+identity)):
        raise HTTPException(401,'Acceso del equipo requerido')
    return identity


def require_same_origin(request):
    try:
        origin = urlsplit(request.headers.get('origin',''))
    except ValueError as exc:
        raise HTTPException(403,'Origen de solicitud inválido') from exc
    if (origin.scheme not in ('https','http') or origin.netloc!=request.url.netloc
            or request.headers.get('sec-fetch-site') not in (None,'same-origin')):
        raise HTTPException(403,'Origen de solicitud inválido')


def token_for_file(key, identity, ident):
    return sign(key,f'file|{identity}|{ident}')


def generate_thumbnail(root, ident, version, source):
    path=contained(root,f'previews/{ident}/{version}.jpg')
    if path.is_file():
        return path
    path.parent.mkdir(parents=True,exist_ok=True)
    with Image.open(source) as image:
        oriented=ImageOps.exif_transpose(image)
        oriented.thumbnail((480,320))
        with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.jpg',delete=False) as tmp:
            name=tmp.name
        try:
            oriented.convert('RGB').save(name,format='JPEG',quality=82)
            os.replace(name,path)
        finally:
            Path(name).unlink(missing_ok=True)
    return path


def photo_thumbnail(store,root,row,original):
    with store.connect() as c:
        last=c.execute('''
            SELECT r.id,r.output->>'annotation' AS annotation,r.output->'objects' AS boxes
            FROM runs r JOIN jobs j ON j.id=r.job_id
            WHERE j.evidence_id=%s AND j.stage='detect' AND r.state='completed'
            ORDER BY r.finished_at DESC NULLS LAST,r.id DESC LIMIT 1
        ''',(row['id'],)).fetchone()
    if last and last['boxes'] and last['annotation']:
        try:
            annotated=contained(root,last['annotation'])
            return generate_thumbnail(root,row['id'],str(last['id']),annotated)
        except (OSError,ValueError):
            pass
    try:
        return generate_thumbnail(root,row['id'],'original-v1',original)
    except (OSError,ValueError,Image.DecompressionBombError) as exc:
        raise HTTPException(404,'Miniatura no disponible') from exc


def create_media_router(store, root, key, team_auth):
    router=APIRouter(prefix=PREFIX)

    def media_auth(session: str = Cookie(default='',alias=COOKIE)):
        return session_identity(key,session)

    @router.post('/session',dependencies=[Depends(team_auth)],status_code=204)
    def login():
        response=Response(status_code=204)
        response.set_cookie(COOKIE,new_session(key),max_age=SESSION_SECONDS,
                            path='/',httponly=True,secure=True,samesite='strict')
        return response

    @router.delete('/session',status_code=204)
    def logout(request: Request):
        require_same_origin(request)
        response=Response(status_code=204)
        response.delete_cookie(COOKIE,path='/',httponly=True,secure=True,samesite='strict')
        return response

    def signed_inventory(result,identity):
        for item in result['items']:
            proof=token_for_file(key,identity,item['id'])
            base=f'{PREFIX}/files/{item["id"]}'
            item['content']=f'{base}/content?firma={proof}'
            item['download']=f'{base}/download?firma={proof}'
            if item['type'] in ('image','frame'):
                item['thumbnail']=f'{base}/thumbnail?firma={proof}'
        return result

    @router.get('/records/{code}')
    def inventory(code: str,identity: str=Depends(media_auth)):
        try:
            result=snapshot(store,root,team=True,evidence_code=code)
        except ReportError:
            try:
                result=snapshot(store,root,public=True,evidence_code=code)
            except ReportError as exc:
                raise HTTPException(404,'Registro no disponible') from exc
        return signed_inventory(result,identity)

    @router.get('/conversations/{ident}')
    def citizen_inventory(ident: UUID,episodio: str | None=Query(None,pattern=r'^[a-f0-9]{16}$'),
                          identity: str=Depends(media_auth)):
        from .detailed import conversation_evidence
        try:
            return signed_inventory(conversation_evidence(store,ident,episodio),identity)
        except ReportError as exc:
            raise HTTPException(404,'Conversación no disponible') from exc

    @router.get('/files/{ident}/{kind}')
    def file(ident: UUID,kind: Literal['content','thumbnail','download'],
             firma: str=Query('',max_length=64),identity: str=Depends(media_auth)):
        if not hmac.compare_digest(firma,token_for_file(key,identity,ident)):
            raise HTTPException(404,'Archivo no disponible')
        with store.connect() as c:
            row=c.execute('SELECT id,storage_path,original_name,modality,sha256 FROM evidence WHERE id=%s',
                          (ident,)).fetchone()
            if not row:
                raise HTTPException(404,'Archivo no disponible')
            if kind=='content' and row['modality']=='chat':
                chat=c.execute('SELECT literal_text FROM source_texts WHERE evidence_id=%s',(ident,)).fetchone()
                if chat is not None:
                    return PlainTextResponse(chat['literal_text'])
        original=contained(root,row['storage_path'])
        if kind=='thumbnail' and row['modality'] in ('image','frame'):
            return FileResponse(photo_thumbnail(store,root,row,original),media_type='image/jpeg')
        if not original.is_file():
            raise HTTPException(404,'Archivo no disponible')
        if kind=='download':
            return FileResponse(original,filename=Path(row['original_name']).name,media_type='application/octet-stream')
        if kind=='content' and row['modality'] in ('audio','video'):
            media_type=mimetypes.guess_type(row['original_name'])[0]
            if not media_type and Path(row['original_name']).suffix.lower()=='.opus':
                media_type='audio/ogg'
            if media_type and media_type.startswith(row['modality']+'/'):
                return FileResponse(original,media_type=media_type,content_disposition_type='inline')
        raise HTTPException(404,'Vista previa no disponible')

    return router
