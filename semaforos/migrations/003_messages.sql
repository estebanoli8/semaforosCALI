CREATE TABLE chat_parses (
 id UUID PRIMARY KEY, evidence_id UUID NOT NULL REFERENCES source_texts(evidence_id),
 parser_version TEXT NOT NULL, options JSONB NOT NULL, parse_key CHAR(64) NOT NULL UNIQUE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE messages (
 id UUID PRIMARY KEY, parse_id UUID NOT NULL REFERENCES chat_parses(id),
 evidence_id UUID NOT NULL REFERENCES source_texts(evidence_id), ordinal INT NOT NULL,
 char_start INT NOT NULL, char_end INT NOT NULL, raw_text TEXT NOT NULL, body_text TEXT NOT NULL,
 sender_visible TEXT, timestamp_literal TEXT, sent_at TIMESTAMPTZ,
 timestamp_status TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('message','system','unparsed')),
 timezone_name TEXT NOT NULL, timezone_assumed BOOLEAN NOT NULL,
 date_order_used TEXT, date_order_assumed BOOLEAN NOT NULL, century_assumed BOOLEAN NOT NULL,
 UNIQUE(parse_id,ordinal), CHECK(char_start>=0 AND char_end>=char_start)
);
CREATE INDEX messages_parse_time_idx ON messages(parse_id,sent_at);
CREATE TABLE message_attachments (
 message_id UUID NOT NULL REFERENCES messages(id), filename_literal TEXT NOT NULL,
 evidence_id UUID REFERENCES evidence(id),
 state TEXT NOT NULL CHECK(state IN ('linked','missing','ambiguous')),
 PRIMARY KEY(message_id,filename_literal),
 CHECK((state='linked') = (evidence_id IS NOT NULL))
);
