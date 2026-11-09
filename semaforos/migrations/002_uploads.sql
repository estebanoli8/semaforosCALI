-- Sesiones de transporte: separadas de conversaciones, evidencias y reportes.
CREATE TABLE uploads (
    id UUID PRIMARY KEY,
    original_name TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK(size_bytes > 0),
    received_bytes BIGINT NOT NULL DEFAULT 0 CHECK(received_bytes >= 0 AND received_bytes <= size_bytes),
    state TEXT NOT NULL DEFAULT 'receiving' CHECK(state IN ('receiving','queued','importing','received','error','cancelled')),
    experiment_id TEXT NOT NULL,
    config JSONB NOT NULL,
    config_hash TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    result JSONB,
    error_code TEXT,
    transport_cleaned BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX uploads_queue ON uploads(state,created_at);
