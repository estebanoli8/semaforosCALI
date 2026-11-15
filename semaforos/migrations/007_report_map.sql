CREATE TABLE report_map_entries (
 report_id UUID PRIMARY KEY REFERENCES reports(id),
 primary_finding_id UUID NOT NULL REFERENCES findings(id),
 finding_ids UUID[] NOT NULL,
 version INT NOT NULL CHECK(version > 0),
 intersection TEXT NOT NULL,
 public_description TEXT,
 latitude DOUBLE PRECISION,
 longitude DOUBLE PRECISION,
 published BOOLEAN NOT NULL DEFAULT false,
 reviewer TEXT NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CHECK ((latitude IS NULL) = (longitude IS NULL)),
 CHECK (latitude BETWEEN -90 AND 90),
 CHECK (longitude BETWEEN -180 AND 180),
 CHECK (NOT published OR public_description IS NOT NULL)
);
CREATE TABLE report_pdf_exports (
 id UUID PRIMARY KEY,
 generated_at TIMESTAMPTZ NOT NULL,
 cutoff TIMESTAMPTZ NOT NULL,
 schema_version INT NOT NULL,
 storage_path TEXT NOT NULL UNIQUE,
 sha256 CHAR(64) NOT NULL,
 report_versions JSONB NOT NULL,
 evidence_ids UUID[] NOT NULL,
 evidence_expires_at TIMESTAMPTZ,
 boundary_version TEXT
);
