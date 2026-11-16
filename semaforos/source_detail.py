"""Attach model output and WhatsApp provenance to one private evidence inventory."""
from collections import defaultdict

from .cali import locations
from .conversation_summary import folded
from .messages import is_team_sender

STAGES = {'chat':'text', 'audio':'audio', 'audio_video':'audio', 'video':'video', 'frame':'detect', 'image':'detect'}


def crossings(text):
    return {' con '.join(sorted(x['label'].split(' con '))) for x in locations(text) if x['intersection']}


def media_location(message, messages, transcript):
    if message:
        own=crossings(message['body_text'])
        if len(own)==1:
            return next(iter(own)), message['sent_at'], 'mensaje vinculado'
    else:
        own=set()
    if message and message['sent_at'] and not own:
        previous=[]; following=[]
        for candidate in messages:
            if (not candidate['sent_at'] or candidate['ordinal']==message['ordinal']
                    or candidate['evidence_id']!=message['evidence_id']
                    or folded(candidate['sender_visible'] or '')!=folded(message['sender_visible'] or '')):
                continue
            delta=(candidate['sent_at']-message['sent_at']).total_seconds()
            if abs(delta)>120:
                continue
            (following if candidate['ordinal']>message['ordinal'] else previous).append(candidate)
        candidates={}
        for group in (reversed(previous),following):
            for candidate in group:
                found=crossings(candidate['body_text'])
                for place in found:
                    candidates.setdefault(place,candidate['sent_at'])
                if found or folded(candidate['body_text']).startswith(('otro ', 'otra ')):
                    break
        if len(candidates)==1:
            place,when=next(iter(candidates.items()))
            return place,when,'mensaje cercano del mismo remitente'
    spoken=crossings(transcript or '')
    if len(spoken)==1:
        return next(iter(spoken)), message['sent_at'] if message else None, 'audio vinculado'
    return None,None,None


def result_for(rows, kind):
    if not rows:
        return {'state':'absent'}
    # One current job per source, except that a chat can have several independent fragments.
    first=rows[0]
    state=first['state']
    effective=rows if kind=='chat' else rows[:1]
    output=[row for row in effective if row['state']=='completed' and row['output']]
    result={'state':state,'error':first['error_code']}
    if kind=='chat':
        states={row['state'] for row in effective}
        result['state']='running' if 'running' in states else 'pending' if 'pending' in states else (
            'partial' if output and 'failed' in states else 'failed' if 'failed' in states else 'completed')
        failed=next((row['error_code'] for row in effective if row['state']=='failed'),None)
        omitted=sum(len(row['output'].get('omitted_assertions',[])) for row in output)
        if omitted and result['state']=='completed':
            result['state']='partial'
            failed='afirmaciones sin respaldo literal'
        result['error']=failed
        extractions=[row['output'].get('extraction',row['output']) for row in output]
        result['evaluations']=[{'run_id':row['run_id'],'review':row.get('semantic_review'),
                                'assertions':extraction.get('assertions',[]), 'sources':row.get('sources') or []}
                               for row,extraction in zip(output,extractions)]
        result.update(summaries=list(dict.fromkeys(x['summary'] for x in extractions if x.get('summary'))),
                      assertions=[item for x in extractions for item in x.get('assertions',[])])
    elif kind in ('audio','audio_video') and output:
        result['text']=first['literal_text']
    elif kind in ('frame','image') and output:
        result['automatic_count']=len(first['output'].get('objects',[]))
    completed = output[0] if output else None
    if completed and kind in ('chat','audio','audio_video','frame','image'):
        result.update(run_id=completed['run_id'],review=completed['human_label'])
        if kind in ('audio','audio_video'):
            result['semantic_review']=completed.get('semantic_review')
    return result


def enrich(db,conversation_id,items,inventory,*,experiment=None,include_analysis=True):
    messages=[]; linked={}
    for message in db.execute("""
        SELECT m.id,m.ordinal,m.evidence_id,m.sender_visible,m.sent_at,m.body_text,
               ARRAY(SELECT a.evidence_id FROM message_attachments a
                     WHERE a.message_id=m.id AND a.state='linked') AS attachments
        FROM messages m JOIN chat_parses p ON p.id=m.parse_id JOIN evidence e ON e.id=p.evidence_id
        WHERE e.conversation_id=%s AND p.id=(SELECT p2.id FROM chat_parses p2
            WHERE p2.evidence_id=p.evidence_id ORDER BY p2.created_at DESC,p2.id DESC LIMIT 1)
        ORDER BY m.evidence_id,m.ordinal
    """,(conversation_id,)):
        if is_team_sender(message['sender_visible']) or not message['sender_visible']:
            continue
        messages.append(message)
        for ident in message['attachments']:
            linked[ident]=message if ident not in linked else None
    rows=defaultdict(list)
    for row in db.execute("""
        SELECT j.evidence_id,j.stage,j.state,j.experiment_id,j.config->'text'->>'extraction' AS version,j.payload->>'transcription_run_id' AS transcribed_from,r.id AS run_id,r.error_code,r.output,
               t.literal_text,v.human_label,semantic.human_label AS semantic_review,j.payload->'sources' AS sources
        FROM jobs j JOIN evidence e ON e.id=j.evidence_id
        LEFT JOIN LATERAL (SELECT r.* FROM runs r WHERE r.job_id=j.id ORDER BY r.attempt DESC LIMIT 1) r ON true
        LEFT JOIN transcripts t ON t.run_id=r.id
        LEFT JOIN LATERAL (SELECT human_label FROM reviews
            WHERE run_id=r.id AND field=CASE WHEN j.stage='detect' THEN 'frame_counts' ELSE 'location_detected' END
            ORDER BY created_at DESC,id DESC LIMIT 1) v ON true
        LEFT JOIN LATERAL (SELECT human_label FROM reviews
            WHERE run_id=r.id AND field='semantic_fields'
            ORDER BY created_at DESC,id DESC LIMIT 1) semantic ON true
        WHERE e.conversation_id=%s AND j.stage IN ('video','audio','text','detect')
            AND NOT (j.payload ? 'superseded_by_review')
            AND (%s::text IS NULL OR j.stage<>'text' OR j.experiment_id=%s)
            AND (%s OR j.stage='audio')
        ORDER BY (j.config->'text'->>'extraction'='compact-v1') DESC NULLS LAST,j.created_at DESC,j.id DESC
    """,(conversation_id,experiment,experiment,include_analysis)):
        group=rows[row['evidence_id'],row['stage']]
        if not group or all(row[key]==group[0][key] for key in ('experiment_id','version','transcribed_from')):
            group.append(row)
    audio_by_video={row['parent_id']:ident for ident,row in inventory.items()
                    if row['parent_id'] and row['modality']=='audio'}
    locations_by_id={}
    for item in items:
        ident,kind=item['id'],item['type']
        if include_analysis:
            item['analysis']=result_for(rows[ident,STAGES.get(kind)],kind)
            if kind=='audio':
                item['extraction']=result_for(rows[ident,'text'],'chat')
            if kind=='video':
                audio=audio_by_video.get(ident)
                item['transcription']=result_for(rows[audio,'audio'],'audio_video') if audio else {
                    'state':'no_audio' if item['analysis']['state']=='completed' else item['analysis']['state'],
                    'error':item['analysis'].get('error')}
                item['extraction']=result_for(rows[audio,'text'],'chat')
        if kind in ('image','video','frame','audio'):
            parent=inventory[ident]['parent_id']
            source_id=parent or ident
            if source_id not in locations_by_id:
                message=linked.get(source_id)
                derived=audio_by_video.get(source_id)
                audio_rows=rows[derived or source_id,'audio']
                transcript=audio_rows[0]['literal_text'] if audio_rows else None
                place,when,origin=media_location(message,messages,transcript)
                item_time=message['sent_at'] if message else None
                locations_by_id[source_id]=(place,when,origin,item_time)
            item['crossing'],item['crossing_time'],item['crossing_source'],item['sent_at']=locations_by_id[source_id]
