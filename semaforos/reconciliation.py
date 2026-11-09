"""Comparación conservadora entre exportaciones: propuestas, nunca fusiones."""
from collections import Counter
from .files import canonical_hash


def fingerprint(message):
    if message.get('kind') != 'message' or not message.get('sender_visible') or not message.get('timestamp_literal'):
        return None
    # No normalizar contenido, fechas ni nombres: preferimos revisión a falsas coincidencias.
    return canonical_hash([message['sender_visible'], message['timestamp_literal'], message['body_text']])


def compare(left, right):
    a=[fingerprint(m) for m in left];b=[fingerprint(m) for m in right]
    a=[x for x in a if x];b=[x for x in b if x]
    ca,cb=Counter(a),Counter(b);shared=sum((ca&cb).values())
    def subsequence(small,large):
        stream=iter(large)
        return all(any(x==wanted for x in stream) for wanted in small)
    relation='sin_coincidencia'
    if shared:
        relation='solapamiento_parcial'
        if a==b:relation='mensajes_comparables_identicos'
        elif len(b)>len(a) and subsequence(a,b):relation='derecha_contiene_izquierda'
        elif len(a)>len(b) and subsequence(b,a):relation='izquierda_contiene_derecha'
    return {'relation':relation,'left_comparable':len(a),'right_comparable':len(b),
            'left_uncomparable':len(left)-len(a),'right_uncomparable':len(right)-len(b),
            'shared_occurrences':shared,'left_only_occurrences':sum((ca-cb).values()),
            'right_only_occurrences':sum((cb-ca).values()),'requires_human_review':True,
            'same_conversation_confirmed':False,'attachments_compared':False}


def compare_parses(store,left_id,right_id):
    with store.connect() as c:
        parses=c.execute('SELECT id,parser_version,options FROM chat_parses WHERE id=ANY(%s::uuid[])',([left_id,right_id],)).fetchall()
        if len({str(p['id']) for p in parses}) != len({str(left_id),str(right_id)}):raise ValueError('parse_not_found')
        if any(p['parser_version']!=parses[0]['parser_version'] or p['options']!=parses[0]['options'] for p in parses):raise ValueError('incompatible_parser_configuration')
        sides=[]
        for ident in (left_id,right_id):
            rows=c.execute('SELECT kind,sender_visible,timestamp_literal,body_text FROM messages WHERE parse_id=%s ORDER BY ordinal LIMIT 10001',(ident,)).fetchall()
            if len(rows)>10000:raise ValueError('comparison_limit_10000_messages')
            sides.append(rows)
        return dict(compare(*sides),left_parse_id=str(left_id),right_parse_id=str(right_id))


def decide(store,payload):
    """Append-only pair decision, with optimistic concurrency and request replay."""
    from psycopg.types.json import Jsonb
    left,right=sorted([str(payload['left_parse_id']),str(payload['right_parse_id'])])
    if left==right:raise ValueError('choose_two_different_exports')
    if not payload['reviewer'].strip() or not payload['reason'].strip():raise ValueError('reviewer_and_reason_required')
    if payload['decision'] not in ('misma_conversacion','distintas','pendiente'):raise ValueError('invalid_decision')
    snapshot=compare_parses(store,left,right)
    digest=canonical_hash(payload)
    with store.connect() as c:
        # Always lock request before pair: safe replay even with changed pair inputs.
        c.execute('SELECT pg_advisory_xact_lock(%s)',(int(canonical_hash(str(payload['request_id']))[:15],16),))
        old=c.execute('SELECT * FROM export_relation_events WHERE request_id=%s',(payload['request_id'],)).fetchone()
        if old:
            if old['payload_hash']!=digest:raise ValueError('request_id_reused')
            return old
        c.execute('SELECT pg_advisory_xact_lock(%s)',(int(canonical_hash([left,right])[:15],16),))
        last=c.execute('SELECT max(version) AS v FROM export_relation_events WHERE left_parse_id=%s AND right_parse_id=%s',(left,right)).fetchone()['v'] or 0
        if payload['expected_version']!=last:raise ValueError('version_conflict_reload')
        return c.execute('''INSERT INTO export_relation_events(request_id,left_parse_id,right_parse_id,version,decision,reviewer,reason,payload_hash,comparison)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
            (payload['request_id'],left,right,last+1,payload['decision'],payload['reviewer'],payload['reason'],digest,Jsonb(snapshot))).fetchone()
