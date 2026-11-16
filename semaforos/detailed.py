"""Private conversation report assembled from the latest extraction of each source."""
import re
from hashlib import sha256
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

from .conversation_summary import folded, gps_coordinates
from .local_places import hints
from .messages import is_team_message, team_message_ids
from .report_evidence import evidence_type, with_video_family
from .reports import ReportError
from .text_fields import FIELDS, TAGS
from .whatsapp import BANNERS, useful_segments

MONTHS = 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split()
BOGOTA=ZoneInfo('America/Bogota')
AGENT=re.compile(r'\b(?:guardas?|agentes?(?: de transito)?|alfere[zc]\w*|policia de transito)\b')
RISK=re.compile(r'\b(?:accident\w*|choc\w*|atropell\w*|riesg\w*|peligr\w*|colisi\w*)\b')
RECURRENCE=re.compile(r'\b(?:volvi[oó] a (?:dañ|fall)|se dañ[oó] (?:otra vez|de nuevo)|despu[eé]s de (?:arregl|repar))',re.I)

RESTORED=re.compile(r'\b(?:ya (?:funciona\w*|prende\w*|(?:lo |la |los |las )?(?:arreglaron|repararon))|'
                    r'no (?:esta\w* )?(?:dañad\w*|apagad\w*))\b')


def date_label(value):
    if not value:
        return 'Sin fecha disponible'
    date=value.astimezone(BOGOTA)
    return f'{MONTHS[date.month-1]} / {date.day:02} / {date.year}'


def field_code(claim):
    tag=claim.get('field_code')
    if isinstance(tag,str) and tag in TAGS:
        return tag
    variable=claim['variable']
    if variable in ('ubicacion','tiempo_sin_funcionar'):
        return 'U' if variable=='ubicacion' else 'T'
    if variable=='descripcion_dano':
        return 'R' if RECURRENCE.search(claim['literal']) else 'D'
    text=folded(claim['literal'])
    return 'G' if AGENT.search(text) else 'P' if RISK.search(text) else None


def location_values(text):
    values=hints(text)
    if values:
        return [(v['label'],v['status']) for v in values]
    gps=gps_coordinates(text)
    if gps:
        return [(f'GPS {v["latitude"]}, {v["longitude"]}','referencia') for v in gps]
    return []


def run_sources(run):
    return run['output'].get('sources',run['payload'].get('sources',[]))


def compose(runs, message_evidence=None, *, excluded_messages=()):
    """Combine exact assertions. Keep multiple locations and uncertain associations distinct."""
    claims=[]; places={}; seen=set()
    attachments=message_evidence or {}
    for run in runs:
        sources={s['id']:s for s in run_sources(run) if 'id' in s and
                 isinstance(s.get('text'),str) and s.get('message_id') not in excluded_messages}
        output=run['output']
        for claim in output.get('extraction',output).get('assertions',[]):
            tag=field_code(claim)
            src=sources.get(claim.get('source_id'))
            literal=claim.get('literal')
            if not tag or not src or not isinstance(literal,str) or not literal.strip() or literal not in src['text']:
                continue
            row={'code':tag,'literal':literal,'origin':src.get('origin'),'date':src.get('sent_at') or run.get('source_date'),
                 'evidence_id':run['evidence_id']}
            anchor=sources.get(claim.get('anchor_source'),{})
            anchor_text=claim.get('anchor_literal')
            valid_anchor=anchor_text if isinstance(anchor_text,str) and anchor_text in anchor.get('text','') else None
            # The same source may include several clues. Never choose one arbitrarily.
            local=location_values(literal) if tag=='U' else []
            if tag=='U' and not local:
                # Qwen can identify verbal directions outside the static catalog.
                local=[(literal,'ubicacion_reportada')]
            if tag!='U':
                local=location_values(valid_anchor or src['text']) or location_values(run.get('source_anchor') or '')
            for place,status in local:
                places.setdefault(place,status)
            message_ids=[src.get('message_id')]
            if valid_anchor:
                message_ids.append(anchor.get('message_id'))
            claims.append((row,[place for place,_ in local],(run['job_id'],src.get('episode',0)),message_ids))
        # A processed location-only message can be useful even if Qwen returned no U.
        for src in sources.values():
            local=location_values(src['text'])
            for place,status in local:
                places.setdefault(place,status)
                claims.append(({'code':'U','literal':src['text'],'origin':src.get('origin'),
                                'date':src.get('sent_at') or run.get('source_date'),'evidence_id':run['evidence_id']},[place],(run['job_id'],src.get('episode',0)),[src.get('message_id')]))
            if RESTORED.search(folded(src['text'])):
                claims.append(({'code':'D','literal':src['text'],'origin':src.get('origin'),
                                'date':src.get('sent_at') or run.get('source_date'),'evidence_id':run['evidence_id']},
                               [place for place,_ in local],(run['job_id'],src.get('episode',0)),[src.get('message_id')]))
    if not claims:
        return [{'location':None,'location_status':None,'inferred_fault':False,
                 'fields':{name:[] for name in FIELDS}}]
    result={place:{'location':place,'location_status':status,'inferred_fault':False,
                   'fields':{name:[] for name in FIELDS}} for place,status in places.items()}
    by_job=defaultdict(set)
    linked=defaultdict(set)
    for row,locations,job_id,_ in claims:
        by_job[job_id].update(locations)
    routed=[]
    message_targets=defaultdict(set)
    for row,locations,job_id,message_ids in claims:
        candidate=locations or list(by_job[job_id])
        targets=candidate if row['code']=='U' and candidate else [candidate[0] if len(candidate)==1 else None]
        for target in targets:
            routed.append((target,row,message_ids))
            for ident in message_ids:
                message_targets[ident].add(target)
    for target,row,message_ids in routed:
        group=result.setdefault(target,{'location':None,'location_status':None,'inferred_fault':False,
                                        'fields':{name:[] for name in FIELDS}})
        linked[target].add(row['evidence_id'])
        for ident in message_ids:
            if len(message_targets[ident])==1:
                linked[target].update(attachments.get(ident,()))
        tag=row['code']
        key=(target,tag,folded(row['literal']).strip(),str(row['evidence_id']))
        if key in seen:
            continue
        seen.add(key)
        group['fields'][TAGS[tag][1]].append(row)
    for place,group in result.items():
        group['evidence_ids']=linked[place]
        fields=group['fields']
        group['inferred_fault']=bool(group['location'] and fields['ubicacion'] and
                                    not any(fields[key] for key in ('dano','gestion','peligro')))
    return list(result.values())


def read_conversations(db, selected=None, *, include_evidence=False):
    conversations=db.execute("""
        SELECT id,original_name FROM conversations WHERE (%s::uuid IS NULL OR id=%s)
        ORDER BY created_at DESC,id DESC
    """,(selected,selected)).fetchall()
    ids=[row['id'] for row in conversations]
    inventories=defaultdict(dict)
    for row in db.execute("""
        SELECT e.id,e.conversation_id,e.original_name,e.modality,e.parent_id,e.metadata,p.modality AS parent_modality,
               ARRAY(SELECT ARRAY[m.sender_visible,m.raw_text] FROM message_attachments a
                     JOIN messages m ON m.id=a.message_id
                     WHERE a.state='linked' AND a.evidence_id IN (e.id,e.parent_id)) AS senders
        FROM evidence e LEFT JOIN evidence p ON p.id=e.parent_id
        WHERE e.conversation_id=ANY(%s::uuid[]) AND e.modality<>'annotated'
        ORDER BY e.created_at,e.id
    """,(ids,)):
        if row['modality']=='audio' and row['senders'] and all(is_team_message(*s) for s in row['senders']):
            continue
        inventories[row['conversation_id']][row['id']]=row
    attachments=defaultdict(set)
    for row in db.execute("""
        SELECT a.message_id,a.evidence_id FROM message_attachments a JOIN evidence e ON e.id=a.evidence_id
        WHERE a.state='linked' AND e.conversation_id=ANY(%s::uuid[])
    """,(ids,)):
        attachments[str(row['message_id'])].add(row['evidence_id'])
    messages=defaultdict(list)
    for row in db.execute("""
        WITH parses AS (
          SELECT DISTINCT ON (p.evidence_id) p.id,e.conversation_id
          FROM chat_parses p JOIN evidence e ON e.id=p.evidence_id
          WHERE e.conversation_id=ANY(%s::uuid[]) ORDER BY p.evidence_id,p.created_at DESC,p.id DESC
        )
        SELECT p.conversation_id,m.sender_visible,m.sent_at,m.body_text,m.raw_text
        FROM parses p JOIN messages m ON m.parse_id=p.id WHERE m.kind='message'
        ORDER BY m.sent_at NULLS LAST,m.ordinal
    """,(ids,)):
        if not row['sender_visible'] or is_team_message(row['sender_visible'],row['raw_text']):
            continue
        if any(
                part.strip() for _,part in useful_segments(row['body_text'])):
            messages[row['conversation_id']].append(row)
        else:
            # Media-only reports still contribute dates. The technical banner does not.
            if ' '.join(row['body_text'].strip().casefold().split()) not in BANNERS:
                messages[row['conversation_id']].append(row)

    runs=defaultdict(list); current={}
    for row in db.execute("""
        SELECT e.conversation_id,j.id AS job_id,j.evidence_id,j.experiment_id,j.config,j.payload,r.output,
               linked.source_date,linked.source_anchor
        FROM jobs j JOIN evidence e ON e.id=j.evidence_id JOIN runs r ON r.job_id=j.id
        LEFT JOIN LATERAL (
            SELECT CASE WHEN count(DISTINCT m.id)=1 THEN to_char(min(m.sent_at) AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"+00:00"') END AS source_date,
                   CASE WHEN count(DISTINCT m.id)=1 THEN min(m.body_text) END AS source_anchor
            FROM message_attachments a JOIN messages m ON m.id=a.message_id
            JOIN chat_parses p ON p.id=m.parse_id
            WHERE a.state='linked' AND e.modality='audio' AND a.evidence_id IN (e.id,e.parent_id)
              AND p.id=(SELECT p2.id FROM chat_parses p2 WHERE p2.evidence_id=p.evidence_id
                        ORDER BY p2.created_at DESC,p2.id DESC LIMIT 1)
        ) linked ON true
        WHERE e.conversation_id=ANY(%s::uuid[]) AND j.stage='text' AND j.state='completed'
          AND r.state='completed' AND NOT (j.payload ? 'superseded_by_review') AND NOT (r.output ? 'excluded')
        ORDER BY (j.config->'text'->>'extraction'='compact-v1') DESC NULLS LAST,j.created_at DESC,j.id DESC
    """,(ids,)):
        cid,ident=row['conversation_id'],row['evidence_id']
        if ident not in inventories[cid]:
            continue
        source_key=(row['experiment_id'],row['config']['text'].get('extraction'),row['payload'].get('transcription_run_id'))
        if current.setdefault(ident,source_key)==source_key:
            runs[cid].append(row)
    excluded_messages=team_message_ids(db,(source for group in runs.values()
                                           for run in group for source in run_sources(run)))
    processing={row['conversation_id']:row for row in db.execute("""
        WITH candidates AS (
          SELECT e.conversation_id,j.* FROM jobs j JOIN evidence e ON e.id=j.evidence_id
          WHERE e.conversation_id=ANY(%s::uuid[]) AND j.stage IN ('audio','video','text')
            AND NOT (j.payload ? 'superseded_by_review')
        ), latest AS (
          SELECT DISTINCT ON (evidence_id,stage) evidence_id,stage,experiment_id,
                 config->'text'->>'extraction' AS version
          FROM candidates ORDER BY evidence_id,stage,
            (config->'text'->>'extraction'='compact-v1') DESC NULLS LAST,created_at DESC,id DESC
        )
        SELECT j.conversation_id,
               bool_or(j.state IN ('pending','running') OR
                       (j.stage IN ('audio','video') AND j.state='completed' AND j.expanded_at IS NULL)) AS pending,
               bool_or(j.state='failed' OR j.expansion_error IS NOT NULL) AS failed
        FROM candidates j JOIN latest l USING (evidence_id,stage,experiment_id)
        WHERE j.config->'text'->>'extraction' IS NOT DISTINCT FROM l.version
        GROUP BY j.conversation_id
    """,(ids,))}
    result=[]
    for conversation in conversations:
        cid=conversation['id']; inventory=inventories[cid]
        dates=[m['sent_at'] for m in messages[cid] if m['sent_at']]
        people=list(dict.fromkeys(m['sender_visible'].strip().strip('\u200e\u200f') for m in messages[cid]))
        reporter=' · '.join(people) if people else conversation['original_name']
        archive_label=re.sub(r'^(?:WhatsApp Chat\s*-\s*|Chat de WhatsApp con\s+)', '',
                             conversation['original_name'],flags=re.I).strip() or reporter
        key=str(cid)
        for label in (reporter, re.sub(r'\s*\([0-9]+\)$','',archive_label)):
            phone=re.sub(r'[\s()+-]','',label)
            if phone.isdecimal() and len(phone)>=8:
                key=phone
                break
        evidence=[{'id':row['id'],'type':evidence_type(row),'name':row['original_name']}
                  for row in inventory.values()]
        status=processing.get(cid,{})
        state='pending' if status.get('pending') else 'partial' if status.get('failed') else 'completed'
        episodes=compose(runs[cid],attachments,excluded_messages=excluded_messages)
        assigned=set()
        for episode in episodes:
            location=episode['location']
            episode['id']=sha256((location or '').encode()).hexdigest()[:16]
            selected=with_video_family(inventory,episode.pop('evidence_ids',()))
            assigned.update(selected)
            files=[file for file in evidence if file['id'] in selected]
            episode['evidence_counts']=dict(Counter(file['type'] for file in files))
            if include_evidence:
                episode['evidence']=files
        unassigned=[file for file in evidence if file['id'] not in assigned]
        item={'id':cid,'reporter':reporter,'archive_label':archive_label,'analysis_state':state,'reporter_key':key,
              'date_from':min(dates,default=None),'date_to':max(dates,default=None),'episodes':episodes,
              'evidence_counts':dict(Counter(file['type'] for file in evidence)),
              'unassigned_evidence_count':len(unassigned)}
        if include_evidence:
            item.update(evidence=evidence,unassigned_evidence=unassigned)
        result.append(item)
    return result,inventories


def snapshot(store):
    with store.connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        cutoff=db.execute('SELECT now() AS cutoff').fetchone()['cutoff']
        rows,_=read_conversations(db,include_evidence=True)
    return {'cutoff':cutoff,'items':rows}


def conversation_evidence(store, ident, episode_id=None):
    from .source_detail import enrich
    with store.connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        rows,inventories=read_conversations(db,ident,include_evidence=True)
        if not rows:
            raise ReportError('conversation_not_found')
        row=rows[0]
        items=row.pop('evidence')
        row.pop('unassigned_evidence')
        if episode_id is not None:
            episode=next((item for item in row['episodes'] if item['id']==episode_id),None)
            if episode is None:
                raise ReportError('report_episode_not_found')
            items=episode['evidence']
            row.update(episodes=[episode],intersection=episode['location'])
        inventory=inventories[ident]
        for item in items:
            if item['type']=='frame':
                frame=inventory[item['id']]
                item.update(video_id=frame['parent_id'],time=frame['metadata'].get('segundo'))
        enrich(db,ident,items,inventory)
        return {**row,'scope':'registro' if episode_id else 'conversacion','items':items}
