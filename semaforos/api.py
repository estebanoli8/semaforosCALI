"""API privada de procesamiento/revisión. No es aún el portal ciudadano."""
import hmac
import json
import os
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from pathlib import Path
from .uploads import Uploads, UploadError, CHUNK_BYTES
from pydantic import BaseModel, Field
from .config import load_config, storage_root
from .store import Store
from .files import contained
from .messages import chat_sources
from .evaluation import wer, detection_metrics, light_metrics
from .reports import ReportError, change as change_report, detail as report_detail


class ExportDecision(BaseModel):
    request_id: UUID
    left_parse_id: UUID
    right_parse_id: UUID
    expected_version: int = Field(ge=0)
    decision: Literal['misma_conversacion','distintas','pendiente']
    reviewer: str = Field(min_length=1,max_length=100)
    reason: str = Field(min_length=1,max_length=2000)


class ReportChange(BaseModel):
    request_id: UUID
    action: Literal['create','attach','replace','review']
    finding_ids: list[UUID] = Field(default_factory=list,max_length=200)
    primary_finding_id: UUID | None = None
    expected_version: int | None = Field(default=None,ge=1)
    summary: str | None = Field(default=None,max_length=4000)
    reviewer: str = Field(min_length=1,max_length=100)
    reason: str = Field(min_length=1,max_length=2000)
    revision: Literal['pendiente','revisado','descartado'] | None = None


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
            rows=c.execute('''SELECT j.id,j.evidence_id,j.stage,j.experiment_id,j.state,j.attempts,
                j.created_at,j.expanded_at,j.expansion_error,r.id AS run_id,r.error_code AS run_error_code,
                e.original_name AS file_name,e.modality,e.metadata AS evidence_metadata,
                parent.original_name AS parent_name,v.original_name AS conversation_name
                FROM jobs j JOIN evidence e ON e.id=j.evidence_id
                JOIN conversations v ON v.id=e.conversation_id
                LEFT JOIN evidence parent ON parent.id=e.parent_id
                LEFT JOIN LATERAL (SELECT id,error_code FROM runs WHERE job_id=j.id ORDER BY attempt DESC LIMIT 1) r ON true
                ORDER BY j.created_at DESC,j.id LIMIT %s OFFSET %s''',(limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM jobs').fetchone()['n']
        for row in rows:
            if row['state']=='running' and row['run_id']:
                path=contained(root,f"runs/{row['run_id']}/progress.json")
                try:
                    if path.stat().st_size<=8192:row['progress']=json.loads(path.read_text())
                except (OSError,ValueError):pass
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
            return {'job_ids':[str(store.enqueue(e['id'],'text',body.experiment_id,config,{'sources':part})) for part in chat_sources(store,e['id'],config)]}
        raise HTTPException(400,'Modalidad sin etapa automática')
    @private.post('/jobs/{ident}/retry')
    def retry_text(ident:UUID):
        state=store.retry_failed_text(ident)
        if state=='not_found':raise HTTPException(404,'Tarea no encontrada')
        if state!='queued':raise HTTPException(409,state)
        return {'state':state}
    @private.get('/runs/{run_id}')
    def run(run_id:UUID):
        with store.connect() as c:r=c.execute('SELECT * FROM runs WHERE id=%s',(run_id,)).fetchone()
        if not r:raise HTTPException(404,'Ejecución no encontrada')
        return r

    @private.get('/runs/{run_id}/annotated')
    def annotated(run_id:UUID):
        with store.connect() as c:
            row=c.execute('''SELECT r.output FROM runs r JOIN jobs j ON j.id=r.job_id
                WHERE r.id=%s AND r.state='completed' AND j.stage='detect' ''',(run_id,)).fetchone()
        if not row:raise HTTPException(404,'Anotación no disponible')
        try:
            relative=Path(row['output']['annotation']).resolve().relative_to(root.resolve())
            path=contained(root,str(relative))
        except (KeyError,ValueError):raise HTTPException(404,'Anotación no disponible')
        if not path.is_file() or path.suffix.lower() not in ('.jpg','.jpeg'):
            raise HTTPException(404,'Anotación no disponible')
        return FileResponse(path,media_type='image/jpeg',content_disposition_type='inline')
    @private.get('/evidence/{evidence_id}/chat-parses')
    def chat_parses(evidence_id:UUID):
        with store.connect() as c:
            return {'items':c.execute('SELECT * FROM chat_parses WHERE evidence_id=%s ORDER BY created_at DESC,id',(evidence_id,)).fetchall()}
    @private.get('/chat-parses/{parse_id}/messages')
    def messages(parse_id:UUID,offset:int=0,limit:int=50):
        if offset<0 or not 1<=limit<=200:raise HTTPException(400,'Paginación inválida')
        with store.connect() as c:
            if not c.execute('SELECT id FROM chat_parses WHERE id=%s',(parse_id,)).fetchone():raise HTTPException(404,'Lectura de chat no encontrada')
            rows=c.execute('SELECT * FROM messages WHERE parse_id=%s ORDER BY ordinal LIMIT %s OFFSET %s',(parse_id,limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM messages WHERE parse_id=%s',(parse_id,)).fetchone()['n']
            attachments=c.execute('SELECT * FROM message_attachments WHERE message_id=ANY(%s::uuid[]) ORDER BY filename_literal',([row['id'] for row in rows],)).fetchall() if rows else []
            grouped={row['id']:[] for row in rows}
            for attachment in attachments:grouped[attachment['message_id']].append(attachment)
            for row in rows:row['attachments']=grouped[row['id']]
        return {'total':total,'items':rows}
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

    @app.exception_handler(ReportError)
    async def report_error(request,exc):
        return JSONResponse(status_code=409,content={'detail':str(exc)})

    @app.get('/comparison.js')
    def comparison_script():return FileResponse(Path(__file__).with_name('web')/'comparison.js',media_type='text/javascript')

    @private.get('/export-indexes')
    def export_indexes(offset:int=0,limit:int=50):
        if offset<0 or not 1<=limit<=200:raise HTTPException(400,'Paginación inválida')
        with store.connect() as c:
            rows=c.execute('SELECT p.id,p.created_at,p.parser_version,e.original_name AS chat_name,v.original_name AS zip_name FROM chat_parses p JOIN evidence e ON e.id=p.evidence_id JOIN conversations v ON v.id=e.conversation_id ORDER BY p.created_at DESC,p.id LIMIT %s OFFSET %s',(limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM chat_parses').fetchone()['n']
        return {'items':rows,'total':total}

    @private.get('/export-relations')
    def export_relations(left_parse_id:UUID,right_parse_id:UUID,offset:int=0,limit:int=20):
        if offset<0 or not 1<=limit<=100:raise HTTPException(400,'Paginación inválida')
        left,right=sorted([str(left_parse_id),str(right_parse_id)])
        with store.connect() as c:
            rows=c.execute('SELECT * FROM export_relation_events WHERE left_parse_id=%s AND right_parse_id=%s ORDER BY version DESC LIMIT %s OFFSET %s',(left,right,limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM export_relation_events WHERE left_parse_id=%s AND right_parse_id=%s',(left,right)).fetchone()['n']
        return {'items':rows,'total':total,'version':total}

    @private.post('/export-relations')
    def export_decision(body:ExportDecision):
        from .reconciliation import decide
        try:return decide(store,body.model_dump(mode='json'))
        except ValueError as exc:raise HTTPException(409,str(exc))

    @private.get('/conversation-comparison')
    def conversation_comparison(left_parse_id:UUID,right_parse_id:UUID):
        from .reconciliation import compare_parses
        try:return compare_parses(store,left_parse_id,right_parse_id)
        except ValueError as exc:raise HTTPException(422,str(exc))

    @private.get('/report-proposals')
    def report_proposals(conversation_id:UUID,offset:int=0,limit:int=20):
        if offset<0 or not 1<=limit<=50:raise HTTPException(400,'Paginación inválida')
        from .proposals import proposals
        try:return proposals(store,conversation_id,offset,limit)
        except ValueError as exc:raise HTTPException(422,str(exc))

    @private.get('/conversations')
    def conversations(offset:int=0,limit:int=50):
        if offset<0 or not 1<=limit<=200:raise HTTPException(400,'Paginación inválida')
        with store.connect() as c:
            rows=c.execute('SELECT id,original_name,created_at FROM conversations ORDER BY created_at DESC,id LIMIT %s OFFSET %s',(limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM conversations').fetchone()['n']
        return {'items':rows,'total':total}

    @private.get('/findings')
    def findings(conversation_id:UUID,offset:int=0,limit:int=50,unassigned:bool=False):
        if offset<0 or not 1<=limit<=200:raise HTTPException(400,'Paginación inválida')
        predicate='f.conversation_id=%s'
        if unassigned:predicate+=" AND NOT EXISTS(SELECT 1 FROM report_findings rf JOIN reports r ON r.id=rf.report_id WHERE rf.finding_id=f.id AND r.revision<>'descartado')"
        with store.connect() as c:
            rows=c.execute('SELECT f.*,ARRAY(SELECT r.code FROM reports r JOIN report_findings rf ON rf.report_id=r.id WHERE rf.finding_id=f.id AND r.revision<>\'descartado\' ORDER BY r.code) AS report_codes FROM findings f WHERE '+predicate+' ORDER BY f.created_at,f.id LIMIT %s OFFSET %s',(conversation_id,limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM findings f WHERE '+predicate,(conversation_id,)).fetchone()['n']
        return {'items':rows,'total':total}

    @private.get('/reports')
    def reports(conversation_id:UUID|None=None,offset:int=0,limit:int=50):
        if offset<0 or not 1<=limit<=200:raise HTTPException(400,'Paginación inválida')
        clause=' WHERE r.conversation_id=%s' if conversation_id else ''
        params=[conversation_id] if conversation_id else []
        with store.connect() as c:
            rows=c.execute('SELECT r.*,f.sent_at AS report_date FROM reports r JOIN findings f ON f.id=r.primary_finding_id'+clause+' ORDER BY r.created_at DESC,r.id LIMIT %s OFFSET %s',params+[limit,offset]).fetchall()
            total=c.execute('SELECT count(*) AS n FROM reports r'+clause,params).fetchone()['n']
            active=c.execute("SELECT count(*) AS n FROM reports r"+clause+(' AND ' if clause else ' WHERE ')+"r.revision<>'descartado'",params).fetchone()['n']
        return {'items':rows,'total':total,'active':active}

    @private.get('/reports/{ident}')
    def report(ident:UUID):
        with store.connect() as c:return report_detail(c,ident)

    @private.get('/reports/{ident}/history')
    def report_history(ident:UUID,offset:int=0,limit:int=20):
        if offset<0 or not 1<=limit<=100:raise HTTPException(400,'Paginación inválida')
        with store.connect() as c:
            rows=c.execute('SELECT version,action,reviewer,reason,snapshot,created_at FROM report_events WHERE report_id=%s ORDER BY version DESC LIMIT %s OFFSET %s',(ident,limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM report_events WHERE report_id=%s',(ident,)).fetchone()['n']
        return {'items':rows,'total':total}

    @private.post('/reports')
    def create_report(body:ReportChange):
        if body.action!='create':raise HTTPException(400,'Se requiere create')
        return change_report(store,body.model_dump(mode='json',exclude_unset=True))

    @private.post('/reports/{ident}/changes')
    def edit_report(ident:UUID,body:ReportChange):
        if body.action=='create':raise HTTPException(400,'Usa /reports para crear')
        return change_report(store,body.model_dump(mode='json',exclude_unset=True),ident)

    @private.get('/evidence/{ident}/download')
    def download_evidence(ident:UUID):
        with store.connect() as c:row=c.execute('SELECT storage_path,original_name FROM evidence WHERE id=%s',(ident,)).fetchone()
        if not row:raise HTTPException(404,'Evidencia no encontrada')
        path=contained(root,row['storage_path'])
        if not path.is_file():raise HTTPException(404,'Archivo no disponible')
        return FileResponse(path,filename=Path(row['original_name']).name,media_type='application/octet-stream')

    @app.middleware('http')
    async def private_headers(request,call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'none'; script-src 'self'; style-src 'self'; img-src blob:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        return response

    # Carcasa sin datos: las operaciones y consultas requieren Bearer.
    @app.get('/')
    def panel():return FileResponse(Path(__file__).with_name('web')/'index.html')
    @app.get('/panel.js')
    def panel_js():return FileResponse(Path(__file__).with_name('web')/'panel.js',media_type='text/javascript')
    @app.get('/panel.css')
    def panel_css():return FileResponse(Path(__file__).with_name('web')/'panel.css',media_type='text/css')
    @app.get('/review.js')
    def review_js():return FileResponse(Path(__file__).with_name('web')/'review.js',media_type='text/javascript')

    @private.get('/summary')
    def summary():
        import shutil
        with store.connect() as c:
            conversations=c.execute('SELECT count(*) AS n FROM conversations').fetchone()['n']
            evidence=c.execute('SELECT count(*) AS n FROM evidence WHERE parent_id IS NULL').fetchone()['n']
            states=c.execute('SELECT stage,state,count(*) AS n FROM jobs GROUP BY stage,state ORDER BY stage,state').fetchall()
            index_errors=c.execute("SELECT count(*) AS n FROM finding_indexes WHERE state='error'").fetchone()['n']
        return {'conversations':conversations,'original_files':evidence,'tasks':states,
                'disk_free_bytes':shutil.disk_usage(root).free,'disk_reserve_bytes':uploads.reserve,'chunk_bytes':CHUNK_BYTES,'finding_index_errors':index_errors}

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
