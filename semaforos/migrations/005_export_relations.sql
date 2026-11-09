CREATE TABLE export_relation_events (
 request_id UUID PRIMARY KEY,
 left_parse_id UUID NOT NULL REFERENCES chat_parses(id),
 right_parse_id UUID NOT NULL REFERENCES chat_parses(id),
 version INT NOT NULL CHECK(version>0),
 decision TEXT NOT NULL CHECK(decision IN ('misma_conversacion','distintas','pendiente')),
 reviewer TEXT NOT NULL, reason TEXT NOT NULL,
 payload_hash CHAR(64) NOT NULL, comparison JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CHECK(left_parse_id<right_parse_id),
 UNIQUE(left_parse_id,right_parse_id,version)
);
