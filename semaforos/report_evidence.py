"""Evidence counts for public rows and an authenticated file inventory."""
from collections import Counter, defaultdict

from .messages import is_team_sender
from .reports import ReportError


def evidence_type(row):
    if row['modality']=='audio':
        return 'audio_video' if row['parent_modality']=='video' else 'audio'
    return row['modality']


def with_video_family(inventory, selected):
    """Include parent video and its derived evidence for direct file links."""
    ids=set(selected)&inventory.keys()
    ids.update(inventory[ident]['parent_id'] for ident in tuple(ids)
               if inventory[ident]['parent_id'] in inventory)
    videos={ident for ident in ids if inventory[ident]['modality']=='video'}
    ids.update(ident for ident,row in inventory.items() if row['parent_id'] in videos)
    return ids

def attach_evidence(c, items, evidence_code=None, *, detail=False, export=False):
    if evidence_code is not None:
        items = [item for item in items if item['code']==evidence_code]
        if not items:
            raise ReportError('public_record_not_found')
    conversation_ids = list({item['_conversation_id'] for item in items})
    inventories = defaultdict(dict)
    for row in c.execute('''
        SELECT e.conversation_id,e.id,e.parent_id,e.modality,e.original_name,e.metadata,p.modality AS parent_modality,
               ARRAY(SELECT m.sender_visible FROM message_attachments a JOIN messages m ON m.id=a.message_id
                     WHERE a.state='linked' AND a.evidence_id IN (e.id,e.parent_id)) AS senders
        FROM evidence e LEFT JOIN evidence p ON p.id=e.parent_id
        WHERE e.conversation_id=ANY(%s::uuid[]) AND e.modality<>'annotated'
        ORDER BY e.created_at,e.id
    ''',(conversation_ids,)):
        if row['modality']=='audio' and row['senders'] and all(is_team_sender(sender) for sender in row['senders']):
            continue
        inventories[row['conversation_id']][row['id']]=row
    linked = defaultdict(set)
    message_ids = list({ident for item in items for ident in item.get('_source_ids',[])})
    for row in c.execute('''
        SELECT m.id AS source_id,m.evidence_id FROM messages m WHERE m.id=ANY(%s::uuid[])
        UNION
        SELECT a.message_id AS source_id,a.evidence_id FROM message_attachments a
        WHERE a.state='linked' AND a.message_id=ANY(%s::uuid[])
    ''',(message_ids,message_ids)):
        linked[row['source_id']].add(row['evidence_id'])

    counted = {}
    for item in items:
        conversation_id=item.pop('_conversation_id')
        inventory = inventories[conversation_id]
        report_files = item.pop('_report_evidence_ids',None)
        source_ids = item.pop('_source_ids',[])
        scope = 'registro'
        if report_files is not None:
            selected = {ident for ident in report_files if ident in inventory}
        else:
            selected = {ident for source in source_ids for ident in linked[source] | {source} if ident in inventory}
            selected = with_video_family(inventory, selected)
            # When the chat does not link any media to this row, label the inventory as conversational.
            if not any(inventory[ident]['modality']!='chat' for ident in selected):
                scope='conversacion'
                selected=set(inventory)
        if not any(inventory[ident]['modality']=='chat' for ident in selected):
            selected.update(ident for ident,row in inventory.items() if row['modality']=='chat')
        matching = [row for ident,row in inventory.items() if ident in selected]
        counts = dict(Counter(evidence_type(row) for row in matching))
        counted.update((row['id'],evidence_type(row)) for row in matching)
        item['evidence_counts']=counts
        item['evidence_scope']=scope
        if export:
            item['evidence']=[{'id':row['id'],'modality':evidence_type(row),'name':row['original_name']}
                              for row in matching]
        if evidence_code is not None:
            result={'scope':scope,'counts':counts,'intersection':item['intersection'],'items':[
                {'id':row['id'],'type':evidence_type(row),'name':row['original_name']} for row in matching]}
            if detail:
                from .source_detail import enrich
                result.update(situacion_presentada=item.get('situacion_presentada') or item['description'],
                              date=item['date'])
                for file in result['items']:
                    if file['type']=='frame':
                        frame=inventory[file['id']]
                        file.update(video_id=frame['parent_id'],time=frame['metadata'].get('segundo'))
                enrich(c,conversation_id,result['items'],inventory)
            return result
    return dict(Counter(counted.values()))
