CREATE TABLE finding_indexes (
 run_id UUID PRIMARY KEY REFERENCES runs(id), state TEXT NOT NULL CHECK(state IN ('completed','error')),
 error_code TEXT, indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE findings (
 id UUID PRIMARY KEY, conversation_id UUID NOT NULL REFERENCES conversations(id),
 evidence_id UUID NOT NULL REFERENCES evidence(id), message_id UUID REFERENCES messages(id),
 transcript_id UUID REFERENCES transcripts(id), variable TEXT NOT NULL CHECK(variable IN ('ubicacion','descripcion_dano','tiempo_sin_funcionar','afectaciones')),
 origin TEXT NOT NULL CHECK(origin IN ('chat','audio_whatsapp','audio_video')),
 literal TEXT NOT NULL, display_literal TEXT NOT NULL, spans JSONB NOT NULL,
 source_ref JSONB NOT NULL, sent_at TIMESTAMPTZ, stable_key CHAR(64) UNIQUE NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX findings_conversation_idx ON findings(conversation_id,created_at,id);
CREATE TABLE finding_predictions (
 finding_id UUID NOT NULL REFERENCES findings(id), run_id UUID NOT NULL REFERENCES runs(id),
 assertion_index INT NOT NULL, interpretation TEXT, PRIMARY KEY(run_id,assertion_index)
);
CREATE TABLE reports (
 id UUID PRIMARY KEY, code BIGSERIAL UNIQUE NOT NULL,
 conversation_id UUID NOT NULL REFERENCES conversations(id),
 primary_finding_id UUID NOT NULL REFERENCES findings(id), summary TEXT,
 revision TEXT NOT NULL DEFAULT 'pendiente' CHECK(revision IN ('pendiente','revisado','descartado')),
 version INT NOT NULL DEFAULT 1 CHECK(version>0),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE report_findings (
 report_id UUID NOT NULL REFERENCES reports(id), finding_id UUID NOT NULL REFERENCES findings(id),
 PRIMARY KEY(report_id,finding_id)
);
CREATE TABLE report_events (
 request_id UUID PRIMARY KEY, payload_hash CHAR(64) NOT NULL,
 report_id UUID NOT NULL REFERENCES reports(id), version INT NOT NULL,
 action TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL,
 snapshot JSONB NOT NULL, response JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(report_id,version)
);
