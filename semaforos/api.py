"""API privada de procesamiento/revisión. No es aún el portal ciudadano."""
import hmac
import os
from uuid import UUID
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from pathlib import Path
from .uploads import Uploads, UploadError, CHUNK_BYTES
from pydantic import BaseModel, Field
from .config import load_config, storage_root
from .store import Store
from .files import contained
from .worker import text_chunks
from .evaluation import wer, detection_metrics, light_metrics


class UploadStart(BaseModel):
    name: str
    size: int = Field(strict=True,gt=0,le=2**53-1)
    experiment_id: str = Field(default='exploracion-local-v1',min_length=1,max_length=100)


class Enqueue(BaseModel):
    evidence_id: UUID
    experiment_id: str = Field(min_length=1,max_length=100)


class Review(BaseModel):
    run_id: UUID
    field: str
    label: object
    reviewer: str = Field(min_length=1,max_length=100)
    comment: str | None = Field(default=None,max_length=4000)


def create_app(store=None, root=None, config=None, token=None):
    store=store or Store();root=root or storage_root();config=config or load_config()
    token=token or os.environ['SC_API_TOKEN']
    if len(token)<32:raise ValueError('SC_API_TOKEN_requires_32_characters')
    def auth(authorization: str=Header(default='')):
        if not hmac.compare_digest(authorization.encode(),('Bearer '+token).encode()):raise HTTPException(401,'Acceso privado')
    app=FastAPI(title='Semáforos Cali · Núcleo privado',docs_url=None,redoc_url=None,openapi_url=None)
    private=APIRouter(dependencies=[Depends(auth)])
    uploads=Uploads(store,root)
    @private.get('/health')
    def health():
        with store.connect() as c:c.execute('SELECT 1 FROM schema_migrations LIMIT 1')
        import shutil
        disk=shutil.disk_usage(root)
        return {'database':'ok','free_bytes':disk.free,'total_bytes':disk.total,'scope':'private_processing_core'}
    @private.get('/jobs')
    def jobs(offset:int=0,limit:int=50):
        if offset<0 or not 1<=limit<=200:raise HTTPException(400,'Paginación inválida')
        with store.connect() as c:
            rows=c.execute('SELECT j.id,j.evidence_id,j.stage,j.experiment_id,j.state,j.attempts,j.created_at,j.expanded_at,j.expansion_error,(SELECT r.id FROM runs r WHERE r.job_id=j.id ORDER BY r.attempt DESC LIMIT 1) AS run_id FROM jobs j ORDER BY j.created_at DESC,j.id LIMIT %s OFFSET %s',(limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM jobs').fetchone()['n']
        return {'total':total,'items':rows}
    @private.post('/jobs')
    def enqueue(body:Enqueue):
        with store.connect() as c:e=c.execute('SELECT * FROM evidence WHERE id=%s',(body.evidence_id,)).fetchone()
        if not e:raise HTTPException(404,'Evidencia no encontrada')
        stage={'image':'detect','frame':'detect','audio':'audio','video':'video'}.get(e['modality'])
        if stage:return {'job_ids':[str(store.enqueue(e['id'],stage,body.experiment_id,config))]}
        if e['modality']=='chat':
            with store.connect() as c:row=c.execute('SELECT literal_text FROM source_texts WHERE evidence_id=%s',(e['id'],)).fetchone()
            if not row:raise HTTPException(409,'Texto fuente pendiente de importar')
            return {'job_ids':[str(store.enqueue(e['id'],'text',body.experiment_id,config,{'sources':part})) for part in text_chunks(row['literal_text'],e['id'],'chat')]}
        raise HTTPException(400,'Modalidad sin etapa automática')
    @private.get('/runs/{run_id}')
    def run(run_id:UUID):
        with store.connect() as c:r=c.execute('SELECT * FROM runs WHERE id=%s',(run_id,)).fetchone()
        if not r:raise HTTPException(404,'Ejecución no encontrada')
        return r
    @private.post('/reviews')
    def review(body:Review):
        if body.field not in ('transcription','boxes','lights','assertions'):raise HTTPException(400,'Campo de revisión inválido')
        with store.connect() as c:r=c.execute("SELECT r.*,j.stage FROM runs r JOIN jobs j ON j.id=r.job_id WHERE r.id=%s AND r.state='completed'",(body.run_id,)).fetchone()
        if not r:raise HTTPException(404,'Predicción completada no encontrada')
        if {'transcription':'audio','boxes':'detect','lights':'lights','assertions':'text'}[body.field]!=r['stage']:raise HTTPException(400,'Campo incompatible con la etapa')
        # Validar antes de registrar la etiqueta; las observaciones sin métrica se conservan.
        metrics=None
        try:
            if body.field=='transcription':metrics=wer(body.label,r['output']['text'])
            elif body.field=='boxes':metrics=detection_metrics(r['output']['objects'],body.label)
            elif body.field=='lights':
                if not isinstance(body.label,dict) or 'detection_id' not in body.label:raise ValueError()
                obj=next(x for x in r['output']['objects'] if x['detection_id']==body.label['detection_id'])
                metrics=light_metrics(obj,body.label)
            elif not isinstance(body.label,list):raise ValueError()
        except (ValueError,TypeError,KeyError,StopIteration):raise HTTPException(400,'Formato de etiqueta inválido')
        ident=store.review(body.run_id,body.field,body.label,body.reviewer,body.comment)
        if metrics is not None:
            from psycopg.types.json import Jsonb
            from uuid import uuid4
            with store.connect() as c:c.execute('INSERT INTO evaluations(id,review_id,metrics) VALUES(%s,%s,%s)',(uuid4(),ident,Jsonb(metrics)))
        return {'review_id':str(ident),'metrics':metrics,'original_prediction_preserved':True}
    @app.exception_handler(UploadError)
    async def upload_error(request,exc):
        return JSONResponse(status_code=409,content={'detail':str(exc)})

    @app.middleware('http')
    async def private_headers(request,call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        return response

    # Carcasa sin datos: las operaciones y consultas requieren Bearer.
    @app.get('/')
    def panel():return FileResponse(Path(__file__).with_name('web')/'index.html')
    @app.get('/panel.js')
    def panel_js():return FileResponse(Path(__file__).with_name('web')/'panel.js',media_type='text/javascript')
    @app.get('/panel.css')
    def panel_css():return FileResponse(Path(__file__).with_name('web')/'panel.css',media_type='text/css')

    @private.get('/summary')
    def summary():
        import shutil
        with store.connect() as c:
            conversations=c.execute('SELECT count(*) AS n FROM conversations').fetchone()['n']
            evidence=c.execute('SELECT count(*) AS n FROM evidence WHERE parent_id IS NULL').fetchone()['n']
            states=c.execute('SELECT stage,state,count(*) AS n FROM jobs GROUP BY stage,state ORDER BY stage,state').fetchall()
        return {'conversations':conversations,'original_files':evidence,'tasks':states,
                'disk_free_bytes':shutil.disk_usage(root).free,'disk_reserve_bytes':uploads.reserve,'chunk_bytes':CHUNK_BYTES}

    @private.post('/uploads')
    def start_upload(body:UploadStart):
        return uploads.create(body.name,body.size,body.experiment_id,config)
    @private.get('/uploads')
    def list_uploads(offset:int=0,limit:int=100):
        if offset<0 or not 1<=limit<=200:raise HTTPException(400,'Paginación inválida')
        with store.connect() as c:
            rows=c.execute('SELECT * FROM uploads ORDER BY created_at DESC,id LIMIT %s OFFSET %s',(limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM uploads').fetchone()['n']
        return {'total':total,'items':[uploads.public(r) for r in rows]}
    @private.get('/uploads/{ident}')
    def upload_status(ident:UUID):return uploads.get(ident)
    @private.put('/uploads/{ident}/chunk')
    async def chunk(ident:UUID,request:Request,offset:int, x_chunk_sha256:str=Header(default='')):
        data=bytearray()
        async for block in request.stream():
            if len(data)+len(block)>CHUNK_BYTES:raise HTTPException(413,'Bloque mayor a 4 MiB')
            data.extend(block)
        return await run_in_threadpool(uploads.append,ident,offset,bytes(data),x_chunk_sha256)
    @private.post('/uploads/{ident}/finish')
    def finish_upload(ident:UUID):return uploads.finish(ident)
    @private.post('/uploads/{ident}/cancel')
    def cancel_upload(ident:UUID):return uploads.cancel(ident)
    @private.post('/uploads/{ident}/retry')
    def retry_upload(ident:UUID):return uploads.retry(ident)

    app.include_router(private)
    return app
