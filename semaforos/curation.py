"""Human labels and corrected extraction, without rewriting model predictions."""
from uuid import uuid4
from psycopg.types.json import Jsonb
from .evaluation import wer
from .worker import text_chunks


def save(store, run_id, decision, reviewer, text=None):
    if not reviewer.strip():
        raise ValueError('Escribe tu nombre como revisor.')
    with store.connect() as c:
        r=c.execute("""SELECT r.*,j.stage,j.evidence_id,j.experiment_id,j.config,j.payload
            FROM runs r JOIN jobs j ON j.id=r.job_id
            WHERE r.id=%s AND r.state='completed' FOR UPDATE OF j""",(run_id,)).fetchone()
        if not r:raise ValueError('Resultado no disponible')
        if r['payload'].get('superseded_by_review'):
            raise ValueError('Esta extracción fue sustituida por una corrección. Revisa la nueva salida.')
        if decision=='corrected' and (r['stage']!='audio' or text is None):
            raise ValueError('La corrección literal requiere una transcripción')
        ident=uuid4()
        previous=c.execute("""SELECT human_label FROM reviews WHERE run_id=%s
            AND field='curation' ORDER BY created_at DESC,id DESC LIMIT 1""",(run_id,)).fetchone()
        prior=previous['human_label'] if previous else {}
        effective=text if decision=='corrected' else prior.get('text',r['output'].get('text'))
        label={'decision':decision,'text':effective,'reviewer':reviewer.strip(),
               'dependent_extraction_requires_review':decision=='corrected'}
        c.execute('INSERT INTO reviews(id,run_id,field,human_label,reviewer) VALUES(%s,%s,%s,%s,%s)',
                  (ident,run_id,'curation',Jsonb(label),reviewer.strip()))
        queued=[]
        if r['stage']=='audio' and decision!='not_evaluable':
            # Self-approval is a review decision, not an independent reference corpus.
            metrics=wer(effective,r['output']['text'])
            metrics['reference_kind']='human_correction' if effective!=r['output']['text'] else 'human_approval'
            c.execute('INSERT INTO evaluations(id,review_id,metrics) VALUES(%s,%s,%s)',
                      (uuid4(),ident,Jsonb(metrics)))
        if decision=='corrected':
            c.execute("""UPDATE jobs SET payload=payload || %s WHERE stage='text'
                AND payload->>'transcription_run_id'=%s""",
                (Jsonb({'superseded_by_review':str(ident)}),str(run_id)))
            origin='audio_video' if r['payload'].get('from_video') else 'audio_whatsapp'
            for sources in text_chunks(effective,run_id,origin):
                for source in sources:source['transcription_review_id']=str(ident)
                queued.append(str(store.enqueue(r['evidence_id'],'text',r['experiment_id'],r['config'],
                    {'sources':sources,'transcription_run_id':str(run_id),'transcription_review_id':str(ident)},connection=c)))
            # Prevent the original transcript from being expanded again after a correction.
            c.execute('UPDATE jobs SET expanded_at=now() WHERE id=%s',(r['job_id'],))
        return {'saved':True,'review_id':str(ident),'job_ids':queued,
                'dependent_extraction_requires_review':decision=='corrected'}
