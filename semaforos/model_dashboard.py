"""Private aggregates from the latest execution of each processing task."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo('America/Bogota')

DASHBOARD_QUERY = """
WITH quality_by_run AS (
    SELECT DISTINCT ON (rv.run_id) rv.run_id, ev.metrics
    FROM reviews rv JOIN evaluations ev ON ev.review_id=rv.id
    WHERE rv.field IN ('transcription','boxes')
       OR (rv.field='curation' AND ev.metrics->>'reference_kind'='human_correction')
    ORDER BY rv.run_id, rv.created_at DESC, ev.created_at DESC, ev.id DESC
), observed AS (
    SELECT j.id, j.stage,
           CASE WHEN j.state='completed' AND r.output ? 'excluded' THEN 'excluded'
                WHEN j.state='completed' AND r.output->'omitted_assertions' <> '[]'::jsonb THEN 'partial'
                ELSE j.state END AS state,
           (r.finished_at AT TIME ZONE 'America/Bogota')::date AS finished_day,
           r.error_code, r.metrics, q.metrics AS quality, generation.*,
           (r.output->>'needs_review'='true') AS audio_needs_review,
           CASE j.stage
               WHEN 'text' THEN coalesce(r.model_identity->>'model', j.config->'text'->>'model')
               WHEN 'audio' THEN coalesce(r.model_identity->>'repository', j.config->'audio'->>'repository')
               WHEN 'detect' THEN coalesce(r.model_identity->>'weights',
                                           regexp_replace(j.config->'detect'->>'weights', '^.*/', ''))
               WHEN 'video' THEN 'FFmpeg'
           END AS model_name
    FROM jobs j
    LEFT JOIN LATERAL (
        SELECT id, finished_at, error_code, metrics, output, model_identity
        FROM runs WHERE job_id=j.id ORDER BY attempt DESC LIMIT 1
    ) r ON true
    LEFT JOIN quality_by_run q ON q.run_id=r.id AND j.state='completed'
    LEFT JOIN LATERAL (
        SELECT sum((timing->>'prompt_eval_count')::bigint) AS input_tokens,
               sum((timing->>'eval_count')::bigint) AS output_tokens,
               sum((timing->>'eval_count')::bigint)
                   FILTER (WHERE (timing->>'eval_duration')::bigint>0) AS timed_tokens,
               sum((timing->>'eval_duration')::bigint)
                   FILTER (WHERE (timing->>'eval_duration')::bigint>0
                           AND timing->>'eval_count' IS NOT NULL) AS generation_ns
        FROM (
            SELECT element AS timing FROM jsonb_array_elements(coalesce(r.output->'ollama_calls','[]'::jsonb)) element
            UNION ALL
            SELECT r.output->'ollama_timings' AS timing WHERE NOT (r.output ? 'ollama_calls')
            UNION ALL
            SELECT part->'ollama_timings'
            FROM jsonb_array_elements(coalesce(r.output->'recovery'->'batches','[]'::jsonb)) part
        ) generation_batches
    ) generation ON j.stage='text' AND j.state='completed'
    WHERE j.stage IN ('audio','detect','text','video')
      AND NOT (j.payload ? 'superseded_by_review')
      AND (%(experiment)s::text IS NULL OR j.experiment_id=%(experiment)s)
      AND (%(since)s::timestamptz IS NULL OR j.created_at >= %(since)s)
), by_stage AS (
    SELECT stage, array_agg(DISTINCT model_name ORDER BY model_name)
                  FILTER (WHERE model_name IS NOT NULL) AS models,
           count(*) FILTER (WHERE state='completed') AS completed,
           count(*) FILTER (WHERE state='partial') AS partial,
           count(*) FILTER (WHERE state='failed') AS failed,
           count(*) FILTER (WHERE state='running') AS running,
           count(*) FILTER (WHERE state='pending') AS pending,
           count(*) FILTER (WHERE state='excluded') AS excluded,
           count(metrics->>'wall_seconds') FILTER (WHERE state IN ('completed','partial')) AS time_samples,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY (metrics->>'wall_seconds')::double precision)
               FILTER (WHERE state IN ('completed','partial')) AS seconds_p50,
           percentile_cont(0.9) WITHIN GROUP (ORDER BY (metrics->>'wall_seconds')::double precision)
               FILTER (WHERE state IN ('completed','partial')) AS seconds_p90,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY (metrics->>'cpu_seconds')::double precision)
               FILTER (WHERE state IN ('completed','partial')) AS cpu_seconds_p50,
           percentile_cont(0.9) WITHIN GROUP (ORDER BY (metrics->>'peak_rss_bytes')::double precision)
               FILTER (WHERE state IN ('completed','partial')) AS rss_bytes_p90,
           count(output_tokens) AS token_samples,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY input_tokens) AS input_tokens_p50,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY output_tokens) AS output_tokens_p50,
           sum(timed_tokens) * 1000000000.0 / nullif(sum(generation_ns),0) AS tokens_per_second,
           count(*) FILTER (WHERE state='completed' AND audio_needs_review IS NOT NULL) AS audio_check_samples,
           count(*) FILTER (WHERE state='completed' AND audio_needs_review) AS audio_needs_review,
           count(*) FILTER (WHERE quality->>'wer' IS NOT NULL OR quality ? 'iou_threshold') AS quality_samples,
           sum((quality->>'word_errors')::bigint)
               FILTER (WHERE quality->>'wer' IS NOT NULL) AS word_errors,
           sum((quality->>'reference_words')::bigint)
               FILTER (WHERE quality->>'wer' IS NOT NULL) AS reference_words,
           sum((quality->>'true_positive')::bigint) AS tp,
           sum((quality->>'false_positive')::bigint) AS fp,
           sum((quality->>'false_negative')::bigint) AS fn
    FROM observed GROUP BY stage
), daily AS (
    SELECT finished_day AS day, stage,
           count(*) FILTER (WHERE state IN ('completed','partial')) AS results,
           count(*) FILTER (WHERE state='failed') AS failed
    FROM observed WHERE finished_day >= %(chart_start)s
      AND state IN ('completed','partial','failed')
    GROUP BY finished_day, stage
), errors AS (
    SELECT stage, coalesce(error_code,'sin_codigo') AS code, count(*) AS count
    FROM observed WHERE state='failed' GROUP BY stage, coalesce(error_code,'sin_codigo')
)
SELECT coalesce((SELECT jsonb_agg(to_jsonb(b)) FROM by_stage b), '[]') AS stages,
       coalesce((SELECT jsonb_agg(to_jsonb(d) ORDER BY d.day,d.stage) FROM daily d), '[]') AS daily,
       coalesce((SELECT jsonb_agg(to_jsonb(e) ORDER BY e.count DESC,e.stage,e.code) FROM errors e), '[]') AS errors,
       coalesce((SELECT jsonb_agg(experiment_id ORDER BY experiment_id) FROM (
           SELECT DISTINCT experiment_id FROM jobs
           WHERE stage IN ('audio','detect','text','video') AND NOT (payload ? 'superseded_by_review')
       ) experiments), '[]') AS experiments
"""


def dashboard(store, experiment, days):
    now = datetime.now(BOGOTA)
    chart_days = min(days or 14, 14)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    chart_start = today.date() - timedelta(days=chart_days - 1)
    since = today - timedelta(days=days - 1) if days else None
    from .quality_metrics import collect
    with store.connect() as connection:
        result = connection.execute(DASHBOARD_QUERY, {
            'experiment': experiment, 'since': since, 'chart_start': chart_start,
        }).fetchone()
        result.update(collect(connection,experiment,since))
    result['chart_days'] = [(chart_start + timedelta(days=index)).isoformat()
                            for index in range(chart_days)]
    result['as_of'] = now.isoformat()
    return result
