"""Afirmaciones normalizadas, respaldadas por las entradas reales de cada ejecución."""
import re
from uuid import UUID, uuid4
from psycopg.types.json import Jsonb
from .contracts import assertions
from .files import canonical_hash

# Keep history but omit findings supported only by superseded extractions.
ACTIVE_FINDING = """(NOT EXISTS(SELECT 1 FROM finding_predictions fp JOIN runs r ON r.id=fp.run_id
    JOIN jobs j ON j.id=r.job_id WHERE fp.finding_id=f.id AND j.payload ? 'superseded_by_review')
    OR EXISTS(SELECT 1 FROM finding_predictions fp JOIN runs r ON r.id=fp.run_id
    JOIN jobs j ON j.id=r.job_id WHERE fp.finding_id=f.id AND NOT (j.payload ? 'superseded_by_review')))"""


def clean_quote(text):
    # Solo presentación; el texto íntegro permanece en literal y en el original.
    return re.sub(r'<(?:attached|adjunto):[^<>]*>', '', text, flags=re.I).strip()


def occurrences(text, quote, start):
    result=[]; offset=0
    while True:
        found=text.find(quote,offset)
        if found<0:return result
        result.append([start+found,start+found+len(quote)]);offset=found+1


def index_run(store, run_id):
    with store.connect() as c:
        row=c.execute("""SELECT r.output,j.payload,j.evidence_id,e.conversation_id FROM runs r
            JOIN jobs j ON j.id=r.job_id JOIN evidence e ON e.id=j.evidence_id
            WHERE r.id=%s AND r.state='completed' AND j.stage='text' FOR UPDATE OF r""",(run_id,)).fetchone()
        if not row:raise ValueError('completed_text_run_required')
        old=c.execute('SELECT state FROM finding_indexes WHERE run_id=%s',(run_id,)).fetchone()
        if old and old['state']=='completed':return
        sources={s['id']:s for s in row['payload'].get('sources',[])}
        output=row['output'];extraction=output.get('extraction',output)
        assertions(extraction,{key:s['text'] for key,s in sources.items()})
        for index,item in enumerate(extraction['assertions']):
            source=sources[item['source_id']];origin=source.get('origin');start=source.get('char_start')
            if type(start) is not int or start<0:raise ValueError('invalid_source_offset')
            mid=None;tid=None;date=None
            if origin=='chat':
                record=c.execute('SELECT literal_text FROM source_texts WHERE evidence_id=%s',(row['evidence_id'],)).fetchone()
                if not record:raise ValueError('chat_source_missing')
                full=record['literal_text'];basis=str(row['evidence_id'])
                if source.get('message_id'):
                    msg=c.execute('SELECT * FROM messages WHERE id=%s AND evidence_id=%s',(UUID(source['message_id']),row['evidence_id'])).fetchone()
                    if not msg or start<msg['char_start'] or start+len(source['text'])>msg['char_end']:raise ValueError('message_source_mismatch')
                    mid=msg['id'];date=msg['sent_at'];basis=str(mid)
            elif origin in ('audio_whatsapp','audio_video'):
                transcript=c.execute('SELECT * FROM transcripts WHERE run_id=%s AND evidence_id=%s',(row['payload'].get('transcription_run_id'),row['evidence_id'])).fetchone()
                if not transcript:raise ValueError('transcript_source_missing')
                tid=transcript['id'];full=transcript['literal_text'];basis=str(tid)
                if row['payload'].get('transcription_review_id'):
                    review=c.execute("""SELECT human_label FROM reviews WHERE id=%s AND run_id=%s
                        AND field='curation'""",(row['payload']['transcription_review_id'],transcript['run_id'])).fetchone()
                    if not review or review['human_label'].get('decision')!='corrected':raise ValueError('correction_source_missing')
                    full=review['human_label']['text'];basis=str(tid)+':review:'+row['payload']['transcription_review_id']
                # Solo referencias explícitas; un video puede ser padre del audio.
                linked=c.execute('''WITH RECURSIVE parents AS (
                    SELECT id,parent_id FROM evidence WHERE id=%s UNION ALL
                    SELECT e.id,e.parent_id FROM evidence e JOIN parents p ON e.id=p.parent_id)
                    SELECT DISTINCT m.id,m.sent_at FROM parents p JOIN message_attachments a ON a.evidence_id=p.id
                    JOIN messages m ON m.id=a.message_id WHERE a.state='linked' ''',(row['evidence_id'],)).fetchall()
                if len(linked)==1:mid=linked[0]['id'];date=linked[0]['sent_at']
            else:raise ValueError('invalid_source_origin')
            if full[start:start+len(source['text'])]!=source['text']:raise ValueError('source_text_modified')
            spans=occurrences(source['text'],item['literal'],start)
            key=canonical_hash([basis,origin,item['variable'],item['literal'],spans])
            finding=c.execute('''INSERT INTO findings(id,conversation_id,evidence_id,message_id,transcript_id,variable,origin,literal,display_literal,spans,source_ref,sent_at,stable_key)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(stable_key) DO UPDATE SET stable_key=EXCLUDED.stable_key RETURNING id''',
                (uuid4(),row['conversation_id'],row['evidence_id'],mid,tid,item['variable'],origin,item['literal'],clean_quote(item['literal']),Jsonb(spans),Jsonb(source),date,key)).fetchone()['id']
            c.execute('INSERT INTO finding_predictions(finding_id,run_id,assertion_index,interpretation) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(finding,run_id,index,item.get('interpretation')))
        c.execute("INSERT INTO finding_indexes(run_id,state) VALUES(%s,'completed') ON CONFLICT(run_id) DO UPDATE SET state='completed',error_code=NULL,indexed_at=now()",(run_id,))


def index_pending(store, conversation_id=None):
    with store.connect() as c:
        rows=c.execute("""SELECT r.id FROM runs r JOIN jobs j ON j.id=r.job_id
            JOIN evidence e ON e.id=j.evidence_id
            WHERE r.state='completed' AND j.stage='text' AND NOT EXISTS(SELECT 1 FROM finding_indexes f WHERE f.run_id=r.id)
            AND NOT (j.payload ? 'superseded_by_review')
            AND (%s::uuid IS NULL OR e.conversation_id=%s::uuid)
            ORDER BY r.finished_at,r.id LIMIT 10""",(conversation_id,conversation_id)).fetchall()
    for row in rows:
        try:index_run(store,row['id'])
        except (ValueError,TypeError,KeyError) as exc:
            with store.connect() as c:c.execute("INSERT INTO finding_indexes(run_id,state,error_code) VALUES(%s,'error',%s) ON CONFLICT DO NOTHING",(row['id'],type(exc).__name__))
