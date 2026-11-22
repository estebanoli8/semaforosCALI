"""Latest saved human evaluations and per-call instrumentation for the text cohort."""
from collections import Counter
from math import sqrt
from .text_fields import FIELDS


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _binary_metrics(field):
    """Return interpretable metrics without inventing values for empty denominators."""
    tp,fp,fn,tn=(field[key] for key in ('tp','fp','fn','tn'))
    field['observed_positive']=tp+fn
    field['detected_positive']=tp+fp
    field['precision']=_ratio(tp,tp+fp)
    field['recall']=_ratio(tp,tp+fn)
    field['specificity']=_ratio(tn,tn+fp)
    field['accuracy']=_ratio(tp+tn,field['samples'])
    field['f1']=_ratio(2*tp,2*tp+fp+fn)
    rates=[value for value in (field['recall'],field['specificity']) if value is not None]
    field['balanced_accuracy']=sum(rates)/len(rates) if len(rates)==2 else None
    return field


def summarize_reviews(rows):
    counts={stage:{key:Counter(samples=0,tp=0,fp=0,fn=0,tn=0) for key in FIELDS}
            for stage in ('audio','text')}
    semantic={stage:Counter(evaluations=0,fields_evaluated=0,correct_labels=0,
                            exact_evaluations=0) for stage in ('audio','text')}
    photos=Counter(samples=0,exact=0,within_one=0,over=0,under=0,
                   observed=0,detected=0,abs_error=0,squared_error=0,bias_sum=0)
    for row in rows:
        stage,label=row['stage'],row['human_label']
        if stage=='detect':
            seen,found=label['observed'],label['detected']
            error=found-seen
            photos.update(samples=1,exact=int(error==0),within_one=int(abs(error)<=1),
                          over=int(error>0),under=int(error<0),observed=seen,detected=found,
                          abs_error=abs(error),squared_error=error**2,bias_sum=error)
            continue
        comparisons=[]
        for key,pair in label.items():
            if key not in FIELDS:
                continue
            observed,detected=pair['observed'],pair['detected']
            kind='tp' if observed and detected else 'fn' if observed else 'fp' if detected else 'tn'
            counts[stage][key].update([kind,'samples'])
            comparisons.append(observed==detected)
        if comparisons:
            semantic[stage].update(evaluations=1,fields_evaluated=len(comparisons),
                                   correct_labels=sum(comparisons),
                                   exact_evaluations=int(all(comparisons)))
    result={}
    for stage,fields in counts.items():
        for field in fields.values():
            _binary_metrics(field)
        eligible=[field['f1'] for field in fields.values() if field['f1'] is not None]
        totals=Counter()
        for field in fields.values():
            totals.update({key:field[key] for key in ('samples','tp','fp','fn','tn')})
        _binary_metrics(totals)
        summary=semantic[stage]
        result[stage]={
            'fields':fields,
            'evaluations':summary['evaluations'],
            'fields_evaluated':summary['fields_evaluated'],
            'exact_evaluations':summary['exact_evaluations'],
            'exact_match_rate':_ratio(summary['exact_evaluations'],summary['evaluations']),
            'label_accuracy':_ratio(summary['correct_labels'],summary['fields_evaluated']),
            'macro_f1':sum(eligible)/len(eligible) if eligible else None,
            'fields_with_f1':len(eligible),
            'micro':totals,
        }
    result['detect']={
        **photos,
        'exact_rate':_ratio(photos['exact'],photos['samples']),
        'within_one_rate':_ratio(photos['within_one'],photos['samples']),
        'mae':_ratio(photos['abs_error'],photos['samples']),
        'rmse':sqrt(photos['squared_error']/photos['samples']) if photos['samples'] else None,
        'mean_bias':_ratio(photos['bias_sum'],photos['samples']),
        'relative_abs_error':_ratio(photos['abs_error'],photos['observed']),
    }
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
