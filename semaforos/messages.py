"""Índice versionado de mensajes y enlaces explícitos a archivos originales."""
from pathlib import PurePosixPath
from uuid import uuid4
from psycopg.types.json import Jsonb
from .files import canonical_hash
from .whatsapp import PARSER_VERSION, options, parse_chat, message_chunks


def index_chat(store, evidence_id, config):
    settings = options(config.get('whatsapp'))
    with store.connect() as c:
        source = c.execute('SELECT s.literal_text,e.conversation_id FROM source_texts s JOIN evidence e ON e.id=s.evidence_id WHERE s.evidence_id=%s', (evidence_id,)).fetchone()
        if not source: raise ValueError('source_text_not_found')
        key = canonical_hash([str(evidence_id), source['literal_text'], PARSER_VERSION, settings])
        # Serialize indexing, including API calls, without blocking model inference.
        c.execute('SELECT pg_advisory_xact_lock(%s)', (int(key[:15], 16),))
        old = c.execute('SELECT id FROM chat_parses WHERE parse_key=%s', (key,)).fetchone()
        if old: return old['id']
        ident = uuid4()
        c.execute('INSERT INTO chat_parses(id,evidence_id,parser_version,options,parse_key) VALUES(%s,%s,%s,%s,%s)',
                  (ident, evidence_id, PARSER_VERSION, Jsonb(settings), key))
        evidence = c.execute('SELECT id,original_name FROM evidence WHERE conversation_id=%s AND parent_id IS NULL AND modality<>%s', (source['conversation_id'], 'chat')).fetchall()
        columns = ['ordinal','char_start','char_end','raw_text','body_text','sender_visible','timestamp_literal','sent_at','timestamp_status','kind','timezone_name','timezone_assumed','date_order_used','date_order_assumed','century_assumed']
        for message in parse_chat(source['literal_text'], settings):
            mid = uuid4()
            c.execute('INSERT INTO messages(id,parse_id,evidence_id,'+','.join(columns)+') VALUES('+','.join(['%s']*(3+len(columns)))+')',
                      [mid,ident,evidence_id]+[message[x] for x in columns])
            for filename in message['attachment_names']:
                normalized = filename.replace('\\','/')
                matches = [e for e in evidence if e['original_name'].replace('\\','/') == normalized]
                if not matches and '/' not in normalized:
                    matches = [e for e in evidence if PurePosixPath(e['original_name'].replace('\\','/')).name == normalized]
                state = 'linked' if len(matches)==1 else 'ambiguous' if matches else 'missing'
                c.execute('INSERT INTO message_attachments(message_id,filename_literal,evidence_id,state) VALUES(%s,%s,%s,%s)',
                          (mid,filename,matches[0]['id'] if len(matches)==1 else None,state))
        return ident


def chat_sources(store, evidence_id, config):
    ident = index_chat(store, evidence_id, config)
    with store.connect() as c:
        # Server-side cursor avoids copying every message into a second Python list.
        with c.cursor(name='chat_sources') as cursor:
            cursor.execute('SELECT * FROM messages WHERE parse_id=%s ORDER BY ordinal', (ident,))
            yield from message_chunks(cursor)
