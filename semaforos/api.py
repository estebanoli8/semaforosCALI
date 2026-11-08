"""API privada de procesamiento/revisión. No es aún el portal ciudadano."""
import hmac
import os
from uuid import UUID
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from .config import load_config, storage_root
from .store import Store
from .files import contained
from .worker import text_chunks
from .evaluation import wer, detection_metrics, light_metrics


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
        if not hmac.compare_digest(authorization,'Bearer '+token):raise HTTPException(401,'Acceso privado')
    app=FastAPI(title='Semáforos Cali · Núcleo privado',dependencies=[Depends(auth)],docs_url=None,redoc_url=None,openapi_url=None)
    @app.get('/health')
    def health():
        with store.connect() as c:c.execute('SELECT 1 FROM schema_migrations LIMIT 1')
        import shutil
        disk=shutil.disk_usage(root)
        return {'database':'ok','free_bytes':disk.free,'total_bytes':disk.total,'scope':'private_processing_core'}
    @app.get('/jobs')
    def jobs(offset:int=0,limit:int=50):
        if offset<0 or not 1<=limit<=200:raise HTTPException(400,'Paginación inválida')
        with store.connect() as c:
            rows=c.execute('SELECT id,evidence_id,stage,experiment_id,state,attempts,created_at,expanded_at,expansion_error FROM jobs ORDER BY created_at,id LIMIT %s OFFSET %s',(limit,offset)).fetchall()
            total=c.execute('SELECT count(*) AS n FROM jobs').fetchone()['n']
        return {'total':total,'items':rows}
    @app.post('/jobs')
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
    @app.get('/runs/{run_id}')
    def run(run_id:UUID):
        with store.connect() as c:r=c.execute('SELECT * FROM runs WHERE id=%s',(run_id,)).fetchone()
        if not r:raise HTTPException(404,'Ejecución no encontrada')
        return r
    @app.post('/reviews')
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
    return app
