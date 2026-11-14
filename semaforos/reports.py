"""Consolidación explícita y revisable; predicciones y versiones nunca se borran."""
from uuid import uuid4
from psycopg.types.json import Jsonb
from .files import canonical_hash


class ReportError(ValueError): pass


def detail(c, ident):
    report=c.execute('SELECT * FROM reports WHERE id=%s',(ident,)).fetchone()
    if not report:raise ReportError('report_not_found')
    findings=c.execute('''SELECT f.* FROM findings f JOIN report_findings rf ON f.id=rf.finding_id
        WHERE rf.report_id=%s ORDER BY f.created_at,f.id''',(ident,)).fetchall()
    main=next(f for f in findings if f['id']==report['primary_finding_id'])
    fields={f'{v}_{suffix}':[] for suffix in ('texto','audio') for v in ('ubicacion_semaforo','descripcion_dano','tiempo_sin_funcionar','afectaciones_ciudadanos')}
    names={'ubicacion':'ubicacion_semaforo','descripcion_dano':'descripcion_dano','tiempo_sin_funcionar':'tiempo_sin_funcionar','afectaciones':'afectaciones_ciudadanos'}
    for f in findings:
        key=names[f['variable']]+'_'+('texto' if f['origin']=='chat' else 'audio')
        fields[key].append({'finding_id':str(f['id']),'literal':f['display_literal'],'origin':f['origin']})
    prediction_rows=c.execute('SELECT * FROM finding_predictions WHERE finding_id=ANY(%s::uuid[]) ORDER BY run_id,assertion_index',([f['id'] for f in findings],)).fetchall()
    by_finding={f['id']:[] for f in findings}
    for prediction in prediction_rows:by_finding[prediction['finding_id']].append(prediction)
    for f in findings:f['predictions']=by_finding[f['id']]
    messages=[f['message_id'] for f in findings if f['message_id']]
    evidence=c.execute('''WITH RECURSIVE linked AS (
        SELECT evidence_id AS id FROM findings f JOIN report_findings rf ON rf.finding_id=f.id WHERE rf.report_id=%s
        UNION SELECT evidence_id FROM message_attachments WHERE message_id=ANY(%s::uuid[]) AND state='linked'),
        ancestors AS (SELECT e.id,e.parent_id FROM evidence e JOIN linked l ON e.id=l.id
            UNION SELECT e.id,e.parent_id FROM evidence e JOIN ancestors a ON e.id=a.parent_id),
        family AS (SELECT id FROM ancestors UNION SELECT e.id FROM evidence e JOIN family p ON e.parent_id=p.id)
        SELECT e.id,e.parent_id,e.modality,e.original_name,e.sha256 FROM evidence e JOIN family f ON e.id=f.id ORDER BY e.created_at,e.id''',(ident,messages)).fetchall()
    eids=[e['id'] for e in evidence]
    jobs=c.execute("SELECT state,expanded_at,expansion_error,updated_at FROM jobs WHERE evidence_id=ANY(%s::uuid[]) AND stage<>'lights'",(eids,)).fetchall()
    if any(j['state']=='running' for j in jobs):processing='procesando'
    elif any(j['state']=='pending' for j in jobs):processing='en_cola'
    elif any(j['state']=='failed' or j['expansion_error'] for j in jobs):processing='parcial_con_errores'
    elif any(j['expanded_at'] is None for j in jobs):processing='procesando'
    else:processing='completado'
    dates=[f['sent_at'] for f in findings if f['sent_at']]
    outdated=report['revision']=='revisado' and any(j['updated_at']>report['updated_at'] or j['state'] in ('pending','running') for j in jobs)
    report.update(code_display=f"R-{report['code']:06d}",report_date=main['sent_at'],last_message_at=max(dates) if dates else None,
                  fields=fields,findings=findings,evidence=evidence,processing_state=processing,
                  review_outdated=outdated,revision_effective='pendiente' if outdated else report['revision'])
    return report


def change(store, payload, report_id=None):
    # Idempotencia también en doble clic/reintento y control de edición concurrente.
    key=canonical_hash([str(report_id) if report_id else None,payload])
    request_id=payload['request_id'];action=payload['action']
    if action not in ('create','attach','replace','review'):raise ReportError('invalid_action')
    if not payload.get('reviewer','').strip() or not payload.get('reason','').strip():raise ReportError('reviewer_and_reason_required')
    if action=='review' and (payload.get('finding_ids') or payload.get('primary_finding_id')):raise ReportError('review_cannot_change_sources')
    if action=='review' and payload.get('revision') not in ('pendiente','revisado','descartado'):raise ReportError('invalid_revision')
    if action!='review' and payload.get('revision') is not None:raise ReportError('source_change_requires_pending_review')
    with store.connect() as c:
        c.execute('SELECT pg_advisory_xact_lock(%s)',(int(canonical_hash(request_id)[:15],16),))
        event=c.execute('SELECT payload_hash,response FROM report_events WHERE request_id=%s',(request_id,)).fetchone()
        if event:
            if event['payload_hash']!=key:raise ReportError('request_id_reused')
            return event['response']
        ids=list(dict.fromkeys(payload.get('finding_ids',[])))
        if action in ('create','attach','replace'):
            if not ids:raise ReportError('select_at_least_one_finding')
            found=c.execute('SELECT id,conversation_id FROM findings WHERE id=ANY(%s::uuid[])',(ids,)).fetchall()
            if len(found)!=len(ids):raise ReportError('unknown_finding')
            conversations={str(f['conversation_id']) for f in found}
            if len(conversations)!=1:raise ReportError('cross_conversation_link_requires_review')
        if action=='create':
            if report_id is not None:raise ReportError('unexpected_report_id')
            primary=payload.get('primary_finding_id')
            if primary not in ids:raise ReportError('primary_finding_must_be_selected')
            cid=next(iter(conversations))
            c.execute('SELECT id FROM conversations WHERE id=%s FOR UPDATE',(cid,))
            duplicate=c.execute("""SELECT r.id FROM reports r JOIN report_findings rf ON rf.report_id=r.id
                WHERE r.conversation_id=%s AND r.revision<>'descartado' GROUP BY r.id
                HAVING array_agg(rf.finding_id ORDER BY rf.finding_id) = ARRAY(SELECT unnest(%s::uuid[]) ORDER BY 1)""",(cid,ids)).fetchone()
            if duplicate:raise ReportError('same_sources_already_grouped')
            report_id=uuid4()
            c.execute('INSERT INTO reports(id,conversation_id,primary_finding_id,summary) VALUES(%s,%s,%s,%s)',(report_id,next(iter(conversations)),primary,payload.get('summary')))
        else:
            row=c.execute('SELECT * FROM reports WHERE id=%s FOR UPDATE',(report_id,)).fetchone()
            if not row:raise ReportError('report_not_found')
            if row['version']!=payload.get('expected_version'):raise ReportError('version_conflict_reload')
            if action in ('attach','replace') and conversations!={str(row['conversation_id'])}:raise ReportError('cross_conversation_link_requires_review')
            if action=='replace':
                if payload.get('primary_finding_id') not in ids:raise ReportError('primary_finding_must_be_selected')
                c.execute('DELETE FROM report_findings WHERE report_id=%s',(report_id,))
                c.execute('UPDATE reports SET primary_finding_id=%s WHERE id=%s',(payload['primary_finding_id'],report_id))
            if action not in ('attach','replace','review'):raise ReportError('invalid_action')
            revision=payload.get('revision','pendiente') if action=='review' else 'pendiente'
            c.execute('UPDATE reports SET revision=%s,version=version+1,updated_at=now() WHERE id=%s',(revision,report_id))
            if 'summary' in payload:c.execute('UPDATE reports SET summary=%s WHERE id=%s',(payload['summary'],report_id))
        for finding in ids:
            c.execute('INSERT INTO report_findings(report_id,finding_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(report_id,finding))
        report=detail(c,report_id)
        # Captura fiel de cada versión; incluye fuentes y versiones de predicción.
        from fastapi.encoders import jsonable_encoder
        snapshot=jsonable_encoder(report)
        response={'id':str(report_id),'code':report['code_display'],'version':report['version'],'revision':report['revision']}
        c.execute('INSERT INTO report_events(request_id,payload_hash,report_id,version,action,reviewer,reason,snapshot,response) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                  (request_id,key,report_id,report['version'],action,payload['reviewer'],payload['reason'],Jsonb(snapshot),Jsonb(response)))
        return response
