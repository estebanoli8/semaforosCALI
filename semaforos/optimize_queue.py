"""Prepare the queued cohort for compact Qwen, or deliberately replay historical text."""
import argparse
import json
from collections import Counter
from uuid import UUID

from psycopg.types.json import Jsonb
from .config import load_config
from .files import canonical_hash
from .messages import chat_sources, team_audio
from .store import LOCK_KEY, Store
from .worker import text_chunks

PILOT='detalle-qwen-v3'
HISTORY='detalle-qwen-v3-historico'


def prepare(store, config, *, apply=False, historical=False, conversation=None):
    if config['text'].get('extraction')!='compact-v1':
        raise ValueError('La configuración debe activar compact-v1')
    experiment=HISTORY if historical else PILOT
    counts=Counter()
    with store.connect() as db:
        if apply and not db.execute('SELECT pg_try_advisory_xact_lock(%s) AS locked',(LOCK_KEY,)).fetchone()['locked']:
            raise RuntimeError('Hay un trabajador activo. Pausa el procesamiento y vuelve a ejecutar el comando.')
        if historical:
            chats=db.execute("""
                SELECT e.id AS evidence_id,e.conversation_id FROM source_texts s
                JOIN evidence e ON e.id=s.evidence_id
                WHERE (%s::uuid IS NULL OR e.conversation_id=%s)
            """,(conversation,conversation)).fetchall()
            existing=[]
        else:
            existing=db.execute("""
                SELECT j.*,e.modality,e.conversation_id FROM jobs j JOIN evidence e ON e.id=j.evidence_id
                WHERE (j.state='pending' OR (j.state='running' AND j.lease_until<now())) AND j.stage IN ('text','audio','video')
                  AND j.config->'text'->>'extraction' IS DISTINCT FROM 'compact-v1'
                  AND NOT (j.payload ? 'superseded_by_review')
                  AND (%s::uuid IS NULL OR e.conversation_id=%s)
                ORDER BY j.created_at
            """,(conversation,conversation)).fetchall()
            chats=list({r['evidence_id']:r for r in existing if r['stage']=='text' and r['modality']=='chat'}.values())
        counts['conversations']=len({r['conversation_id'] for r in chats+existing})
        counts['pending_jobs']=len(existing)
        counts['chats']=len(chats)
        if not historical and conversation is None:
            uploads=db.execute("""
                SELECT id,config FROM uploads WHERE state IN ('receiving','queued','importing')
                AND config->'text'->>'extraction' IS DISTINCT FROM 'compact-v1'
            """).fetchall()
            counts['uploads']=len(uploads)
            if apply:
                for upload in uploads:
                    fresh={**upload['config'],'text':config['text']}
                    db.execute("""UPDATE uploads SET config=%s,config_hash=%s,experiment_id=%s
                        WHERE id=%s AND state IN ('receiving','queued','importing')""",
                        (Jsonb(fresh),canonical_hash(fresh),experiment,upload['id']))
        if apply:
            for chat in chats:
                for sources in chat_sources(store,chat['evidence_id'],config):
                    store.enqueue(chat['evidence_id'],'text',experiment,config,{'sources':sources},connection=db)
                    counts['chat_batches']+=1
            for job in existing:
                if job['stage']!='text' or job['modality']!='chat':
                    fresh={**job['config'],'text':config['text']}
                    store.enqueue(job['evidence_id'],job['stage'],experiment,fresh,job['payload'],connection=db)
                    counts['requeued_jobs']+=1
                if job['state']=='running':
                    db.execute("""UPDATE runs SET state='interrupted',finished_at=now(),error_code='worker_lost'
                        WHERE job_id=%s AND state='running'""",(job['id'],))
                db.execute("""UPDATE jobs SET payload=payload||%s,updated_at=now(),state='pending',
                    lease_until=NULL,lease_token=NULL WHERE id=%s""",(Jsonb({'superseded_by_review':experiment}),job['id']))
        if historical:
            audios=db.execute("""
                SELECT DISTINCT ON (e.id) e.id,e.conversation_id,e.parent_id,r.id AS run_id,t.literal_text,r.output,
                       v.id AS review_id,v.human_label->>'text' AS corrected
                FROM evidence e JOIN transcripts t ON t.evidence_id=e.id JOIN runs r ON r.id=t.run_id
                LEFT JOIN LATERAL (
                    SELECT id,human_label FROM reviews WHERE run_id=r.id AND field='curation'
                      AND human_label->>'decision'='corrected'
                    ORDER BY created_at DESC,id DESC LIMIT 1
                ) v ON true
                WHERE r.state='completed' AND NOT (r.output ? 'excluded')
                  AND (%s::uuid IS NULL OR e.conversation_id=%s)
                ORDER BY e.id,(v.id IS NOT NULL) DESC,r.finished_at DESC NULLS LAST,r.id DESC
            """,(conversation,conversation)).fetchall()
            counts['conversations']=len({r['conversation_id'] for r in chats+audios})
            for audio in audios:
                if team_audio(store,audio['id']):
                    counts['transcripts_skipped']+=1
                    continue
                counts['transcripts']+=1
                if apply:
                    origin='audio_video' if audio['parent_id'] else 'audio_whatsapp'
                    parts=audio['output'].get('analysis_parts')
                    if audio['review_id']:
                        parts=[{'text':audio['corrected'],'offset':0}]
                    elif parts is None:
                        parts=[{'text':audio['literal_text'],'offset':0}]
                    for part in parts:
                        for batch in text_chunks(part['text'],audio['run_id'],origin,part['offset']):
                            payload={'sources':batch,'transcription_run_id':str(audio['run_id'])}
                            if audio['review_id']:
                                payload['transcription_review_id']=str(audio['review_id'])
                            store.enqueue(audio['id'],'text',experiment,config,payload,connection=db)
                            counts['audio_batches']+=1
    return {'mode':'aplicado' if apply else 'estimación','experiment':experiment,**counts}


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--apply',action='store_true')
    cli.add_argument('--historico',action='store_true')
    cli.add_argument('--conversation',type=UUID)
    args=cli.parse_args()
    print(json.dumps(prepare(Store(),load_config(),apply=args.apply,historical=args.historico,
                             conversation=args.conversation),ensure_ascii=False))


if __name__=='__main__':
    main()
