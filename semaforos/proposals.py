"""Deterministic grouping suggestions. Never create reports or infer incident identity."""
from collections import defaultdict

RULE_VERSION='message-grouping-v1'


def classify(findings):
    locations={f['literal'].strip().casefold() for f in findings if f['variable']=='ubicacion'}
    reasons=[]
    if not all(f.get('message_id') for f in findings):reasons.append('fuente_sin_mensaje_inequivoco')
    if len(locations)!=1:reasons.append('ubicacion_ausente_o_multiple')
    if not any(f['variable']=='descripcion_dano' for f in findings):reasons.append('sin_descripcion_de_dano')
    if len(findings)>200:reasons.append('demasiadas_afirmaciones_para_una_operacion')
    return {'status':'requiere_separacion_o_contexto' if reasons else 'candidato_revisable',
            'reasons':reasons,'rule_version':RULE_VERSION,'requires_human_review':True,
            'primary_finding_id':next((str(f['id']) for f in findings if f['variable']=='ubicacion'),None)}


def proposals(store,conversation_id,offset=0,limit=20):
    with store.connect() as c:
        total=c.execute('SELECT count(DISTINCT coalesce(message_id,id)) AS n FROM findings WHERE conversation_id=%s',(conversation_id,)).fetchone()['n']
        groups=c.execute('SELECT coalesce(message_id,id) AS gid FROM findings WHERE conversation_id=%s GROUP BY 1 ORDER BY 1 LIMIT %s OFFSET %s',(conversation_id,limit,offset)).fetchall()
        ids=[g['gid'] for g in groups]
        rows=c.execute('SELECT * FROM findings WHERE conversation_id=%s AND coalesce(message_id,id)=ANY(%s::uuid[]) ORDER BY created_at,id LIMIT 2001',(conversation_id,ids)).fetchall()
        if len(rows)>2000:raise ValueError('reduce_page_size_too_many_findings')
        grouped=defaultdict(list)
        for row in rows:grouped[row['message_id'] or row['id']].append(row)
        items=[]
        for g in groups:
            fs=grouped[g['gid']];result=classify(fs)
            own=c.execute('''SELECT DISTINCT r.id,r.code,r.conversation_id FROM reports r JOIN report_findings rf ON rf.report_id=r.id
                WHERE r.revision<>'descartado' AND rf.finding_id=ANY(%s::uuid[])''',([f['id'] for f in fs],)).fetchall()
            related=[]
            if fs[0]['message_id']:
                # Only direct, latest, human-confirmed relations; never transitive assumptions.
                related=c.execute('''WITH latest AS (
                    SELECT DISTINCT ON(left_parse_id,right_parse_id) * FROM export_relation_events
                    ORDER BY left_parse_id,right_parse_id,version DESC)
                    SELECT DISTINCT r.id,r.code,r.conversation_id,m2.id AS message_id
                    FROM messages m JOIN latest rel ON (m.parse_id=rel.left_parse_id OR m.parse_id=rel.right_parse_id)
                    JOIN messages m2 ON m2.parse_id=CASE WHEN m.parse_id=rel.left_parse_id THEN rel.right_parse_id ELSE rel.left_parse_id END
                    JOIN findings f ON f.message_id=m2.id AND f.origin='chat'
                    JOIN report_findings rf ON rf.finding_id=f.id JOIN reports r ON r.id=rf.report_id
                    WHERE m.id=%s AND rel.decision='misma_conversacion' AND r.revision<>'descartado'
                    AND m.kind='message' AND m2.kind='message' AND m.sender_visible=m2.sender_visible
                    AND m.timestamp_literal=m2.timestamp_literal AND m.body_text=m2.body_text
                    AND m.sender_visible IS NOT NULL AND m.timestamp_literal IS NOT NULL
                    AND r.conversation_id<>%s''',(fs[0]['message_id'],conversation_id)).fetchall()
            if own:result['status']='con_fuentes_ya_agrupadas'
            elif related:result['status']='posible_reporte_en_otra_exportacion'
            result.update(group_id=str(g['gid']),findings=fs,existing_reports=own,related_reports=related,
                          duplicate_confirmed=False)
            items.append(result)
        return {'total':total,'items':items,'rule_version':RULE_VERSION}
