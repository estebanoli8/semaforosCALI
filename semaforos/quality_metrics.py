"""Latest saved human evaluations and per-call instrumentation for the text cohort."""
from collections import Counter
from .text_fields import FIELDS


def summarize_reviews(rows):
    counts={stage:{key:Counter(samples=0,tp=0,fp=0,fn=0,tn=0) for key in FIELDS}
            for stage in ('audio','text')}
    photos=Counter(samples=0,exact=0,observed=0,detected=0,abs_error=0)
    for row in rows:
        stage,label=row['stage'],row['human_label']
        if stage=='detect':
            seen,found=label['observed'],label['detected']
            photos.update(samples=1, exact=int(seen==found), observed=seen,detected=found,abs_error=abs(seen-found))
            continue
        for key,pair in label.items():
            if key not in FIELDS:
                continue
            observed,detected=pair['observed'],pair['detected']
            kind='tp' if observed and detected else 'fn' if observed else 'fp' if detected else 'tn'
            counts[stage][key].update([kind,'samples'])
    result={}
    for stage,fields in counts.items():
        eligible=[]
        for field in fields.values():
            denominator=2*field['tp']+field['fp']+field['fn']
            field['f1']=2*field['tp']/denominator if denominator else None
            if denominator:
                eligible.append(field['f1'])
        result[stage]={'fields':fields,'macro_f1':sum(eligible)/len(eligible) if eligible else None,
                       'fields_with_f1':len(eligible)}
    result['detect']={**photos,'exact_rate':photos['exact']/photos['samples'] if photos['samples'] else None}
    return result


def collect(db, experiment, since):
    params={'experiment':experiment,'since':since}
    reviewed=db.execute("""
        SELECT DISTINCT ON (r.id) j.stage,v.human_label
        FROM reviews v JOIN runs r ON r.id=v.run_id JOIN jobs j ON j.id=r.job_id
        WHERE (v.field='frame_counts' AND j.stage='detect' OR
               v.field='semantic_fields' AND j.stage IN ('text','audio'))
          AND (%(experiment)s::text IS NULL OR j.experiment_id=%(experiment)s)
          AND (%(since)s::timestamptz IS NULL OR j.created_at>=%(since)s)
          AND NOT (j.payload ? 'superseded_by_review')
        ORDER BY r.id,v.created_at DESC,v.id DESC
    """,params).fetchall()
    calls=db.execute("""
        WITH by_conversation AS (
          SELECT e.conversation_id,count(*) AS calls,
                 sum((a->>'prompt_eval_count')::bigint) AS in_tokens,
                 sum((a->>'eval_count')::bigint) AS out_tokens,
                 sum((a->>'seconds')::double precision) AS seconds,
                 count(*) FILTER (WHERE a->>'status'='truncated') AS truncated,
                 count(*) FILTER (WHERE a->>'status'='error') AS errors
          FROM runs r JOIN jobs j ON j.id=r.job_id JOIN evidence e ON e.id=j.evidence_id
          CROSS JOIN LATERAL jsonb_array_elements(coalesce(r.output->'ollama_calls','[]'::jsonb)) a
          WHERE j.stage='text' AND NOT (j.payload ? 'superseded_by_review')
            AND (%(experiment)s::text IS NULL OR j.experiment_id=%(experiment)s)
            AND (%(since)s::timestamptz IS NULL OR j.created_at>=%(since)s)
          GROUP BY e.conversation_id
        )
        SELECT count(*) AS conversations,coalesce(sum(calls),0)::bigint AS calls,
               sum(in_tokens)::bigint AS input_tokens,sum(out_tokens)::bigint AS output_tokens,
               coalesce(sum(truncated),0)::bigint AS truncated, coalesce(sum(errors),0)::bigint AS errors,
               percentile_cont(.5) WITHIN GROUP (ORDER BY calls) AS calls_p50,
               percentile_cont(.5) WITHIN GROUP (ORDER BY in_tokens) AS input_tokens_p50,
               percentile_cont(.5) WITHIN GROUP (ORDER BY out_tokens) AS output_tokens_p50,
               percentile_cont(.5) WITHIN GROUP (ORDER BY seconds) AS total_seconds_p50,
               percentile_cont(.9) WITHIN GROUP (ORDER BY seconds) AS total_seconds_p90
        FROM by_conversation
    """,params).fetchone()
    alerts=db.execute("""
        WITH latest AS (
            SELECT DISTINCT ON (p.evidence_id) p.id,p.evidence_id,p.parser_version,p.format_health,p.created_at
            FROM chat_parses p ORDER BY p.evidence_id,p.created_at DESC,p.id DESC
        )
        SELECT l.evidence_id,e.original_name,c.original_name AS conversation_name,l.parser_version,
               l.format_health,l.created_at
        FROM latest l JOIN evidence e ON e.id=l.evidence_id JOIN conversations c ON c.id=e.conversation_id
        WHERE l.format_health->>'severity' IN ('warning','degraded')
            AND (%(since)s::timestamptz IS NULL OR l.created_at>=%(since)s)
        ORDER BY l.created_at DESC,l.evidence_id LIMIT 100
    """,params).fetchall()
    return {'human_evaluations':summarize_reviews(reviewed),'qwen_calls':calls,'chat_format_alerts':alerts}
