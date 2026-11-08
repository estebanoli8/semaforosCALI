CREATE TABLE conversations (
 id UUID PRIMARY KEY, source_key TEXT UNIQUE NOT NULL, original_name TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), metadata JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE evidence (
 id UUID PRIMARY KEY, conversation_id UUID NOT NULL REFERENCES conversations(id),
 parent_id UUID REFERENCES evidence(id), modality TEXT NOT NULL CHECK(modality IN ('chat','image','audio','video','frame','annotated','other')),
 original_name TEXT NOT NULL, storage_path TEXT NOT NULL UNIQUE,
 sha256 CHAR(64) NOT NULL, size_bytes BIGINT NOT NULL CHECK(size_bytes>=0),
 metadata JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE jobs (
 id UUID PRIMARY KEY, evidence_id UUID NOT NULL REFERENCES evidence(id),
 stage TEXT NOT NULL CHECK(stage IN ('audio','detect','lights','text','video')),
 experiment_id TEXT NOT NULL, config JSONB NOT NULL, config_hash CHAR(64) NOT NULL,
 code_version TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}',
 request_key CHAR(64) NOT NULL UNIQUE,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','running','completed','failed')),
 attempts INT NOT NULL DEFAULT 0, max_attempts INT NOT NULL DEFAULT 2 CHECK(max_attempts>0),
 lease_token UUID, lease_until TIMESTAMPTZ, expanded_at TIMESTAMPTZ, expansion_error TEXT, available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX jobs_queue_idx ON jobs(state,available_at,created_at);
CREATE TABLE runs (
 id UUID PRIMARY KEY, job_id UUID NOT NULL REFERENCES jobs(id), attempt INT NOT NULL,
 started_at TIMESTAMPTZ NOT NULL DEFAULT now(), finished_at TIMESTAMPTZ,
 state TEXT NOT NULL CHECK(state IN ('running','completed','failed','interrupted')),
 model_identity JSONB, metrics JSONB, output JSONB, error_code TEXT,
 UNIQUE(job_id,attempt)
);
CREATE TABLE transcripts (
 id UUID PRIMARY KEY, run_id UUID NOT NULL UNIQUE REFERENCES runs(id),
 evidence_id UUID NOT NULL REFERENCES evidence(id), literal_text TEXT NOT NULL,
 segments JSONB NOT NULL, language TEXT
);
CREATE TABLE detections (
 id UUID PRIMARY KEY, run_id UUID NOT NULL REFERENCES runs(id),
 evidence_id UUID NOT NULL REFERENCES evidence(id), object_index INT NOT NULL,
 bbox JSONB NOT NULL, score DOUBLE PRECISION, width INT NOT NULL, height INT NOT NULL,
 UNIQUE(run_id,object_index)
);
CREATE TABLE light_readings (
 id UUID PRIMARY KEY, run_id UUID NOT NULL REFERENCES runs(id), detection_id UUID NOT NULL REFERENCES detections(id),
 red BOOLEAN, yellow BOOLEAN, green BOOLEAN,
 reading_state TEXT NOT NULL CHECK(reading_state IN ('alguna_visible','ninguna_visible','indeterminado')),
 reason TEXT, UNIQUE(run_id,detection_id)
);
CREATE TABLE reviews (
 id UUID PRIMARY KEY, run_id UUID NOT NULL REFERENCES runs(id),
 field TEXT NOT NULL, human_label JSONB NOT NULL, reviewer TEXT NOT NULL,
 comment TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE evaluations (
 id UUID PRIMARY KEY, review_id UUID NOT NULL REFERENCES reviews(id),
 metrics JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE source_texts (
 evidence_id UUID PRIMARY KEY REFERENCES evidence(id), literal_text TEXT NOT NULL
);
CREATE TABLE source_archives (
 id UUID PRIMARY KEY, conversation_id UUID NOT NULL REFERENCES conversations(id),
 sha256 CHAR(64) NOT NULL, original_name TEXT NOT NULL, storage_path TEXT NOT NULL UNIQUE,
 size_bytes BIGINT NOT NULL, received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
