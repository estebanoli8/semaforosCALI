"""Lectura conservadora de exportaciones WhatsApp. Nunca altera el texto fuente."""
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARSER_VERSION = 'whatsapp-2'
DEFAULT_OPTIONS = {'date_order': 'DMY', 'timezone': 'America/Bogota', 'two_digit_century': 2000}
MARKS = '\ufeff\u200e\u200f\u202a\u202b\u202c\u2066\u2067\u2068\u2069'
PREFIX = '[' + MARKS + ']*'
DATE = r'\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}'
TIME = r'\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP]\.?\s*[mM]\.?)?'
HEADER = re.compile(r'^' + PREFIX + r'(?:\[(?P<ios_date>' + DATE + r'),?\s+(?P<ios_time>' + TIME + r')\]\s*|(?P<android_date>' + DATE + r'),?\s+(?P<android_time>' + TIME + r')\s+-\s+)(?P<payload>.*)$')
ATTACHED = re.compile(r'<(?:attached|adjunto):\s*([^<>\r\n]+)>', re.I)
NAMED_ATTACHMENT = re.compile(r'^([^\r\n<>]+?)\s+\((?:archivo adjunto|file attached)\)\s*$', re.I | re.M)


def options(value=None):
    result = dict(DEFAULT_OPTIONS, **(value or {}))
    if result['date_order'] not in ('DMY', 'MDY', 'AUTO'):
        raise ValueError('invalid_whatsapp_date_order')
    if result['two_digit_century'] not in (1900, 2000):
        raise ValueError('invalid_whatsapp_century')
    ZoneInfo(result['timezone'])
    return result


def timestamp(date, clock, config):
    """AUTO no resuelve 03/04; DMY/MDY son supuestos explícitos de configuración."""
    raw = re.split(r'[/.-]', date)
    a, b, year = map(int, raw)
    order = config['date_order']
    century_assumed = False
    if len(raw[0]) == 4:
        year, month, day = a, b, year
        used_order = 'YMD'
    else:
        if order == 'AUTO':
            if a > 12 and b <= 12: used_order = 'DMY'
            elif b > 12 and a <= 12: used_order = 'MDY'
            else: return {'sent_at': None, 'timestamp_status': 'ambiguous_date', 'date_order_used': None, 'century_assumed': False}
        else: used_order = order
        day, month = (a, b) if used_order == 'DMY' else (b, a)
        if len(raw[2]) == 2:
            year += config['two_digit_century']; century_assumed = True
    normalized = re.sub(r'[\s.]', '', clock).lower()
    ampm = normalized[-2:] if normalized.endswith(('am', 'pm')) else None
    if ampm: normalized = normalized[:-2]
    nums = list(map(int, normalized.split(':')))
    hour, minute = nums[:2]; second = nums[2] if len(nums) == 3 else 0
    try:
        if ampm:
            if not 1 <= hour <= 12: raise ValueError()
            hour = hour % 12 + (12 if ampm == 'pm' else 0)
        value = datetime(year, month, day, hour, minute, second, tzinfo=ZoneInfo(config['timezone']))
        return {'sent_at': value.astimezone(timezone.utc).isoformat(), 'timestamp_status': 'parsed_assumed_timezone',
                'date_order_used': used_order, 'century_assumed': century_assumed}
    except ValueError:
        return {'sent_at': None, 'timestamp_status': 'invalid_datetime', 'date_order_used': used_order, 'century_assumed': century_assumed}


def parse_chat(text, config=None):
    config = options(config)
    boundaries = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        match = HEADER.match(line.rstrip('\r\n'))
        if match or HEADER_CANDIDATE.match(line.lstrip(MARKS+' ')):
            boundaries.append((cursor, match))
        cursor += len(line)
    if not boundaries or boundaries[0][0] > 0: boundaries.insert(0, (0, None))
    records = []
    for index, (start, match) in enumerate(boundaries):
        end = boundaries[index+1][0] if index+1 < len(boundaries) else len(text)
        raw = text[start:end]
        item = {'ordinal': index, 'char_start': start, 'char_end': end, 'raw_text': raw,
                'body_text': raw, 'sender_visible': None, 'timestamp_literal': None,
                'sent_at': None, 'timestamp_status': 'unparsed', 'kind': 'unparsed',
                'timezone_name': config['timezone'], 'timezone_assumed': True,
                'date_order_used': None, 'date_order_assumed': config['date_order'] != 'AUTO', 'century_assumed': False}
        if match:
            date = match['ios_date'] or match['android_date']
            clock = match['ios_time'] or match['android_time']
            item['timestamp_literal'] = raw[:match.start('payload')]
            item.update(timestamp(date, clock, config))
            item['date_order_assumed'] = config['date_order'] != 'AUTO' and item['date_order_used'] != 'YMD'
            payload = match['payload']
            # Un aviso sin remitente se conserva; no se convierte en denuncia ciudadana.
            separator = payload.find(': ')
            if separator > 0:
                item['sender_visible'] = payload[:separator]
                item['body_text'] = raw[match.start('payload')+separator+2:]
                item['kind'] = 'message'
            else:
                item['body_text'] = raw[match.start('payload'):]
                item['kind'] = 'unparsed' if unknown_sender(payload) else 'system'
        item['attachment_names'] = list(dict.fromkeys(
            [m.group(1).strip(MARKS+' \t') for m in ATTACHED.finditer(item['body_text'])] +
            [m.group(1).strip(MARKS+' \t') for m in NAMED_ATTACHMENT.finditer(item['body_text'])]))
        records.append(item)
    return records


def message_chunks(records):
    """Agrupa mensajes sin perder sus IDs. Un mensaje muy largo conserva sus offsets."""
    batch = []
    for record in records:
        if record['kind'] == 'system': continue
        raw = record['raw_text']
        for offset in range(0, len(raw), 1800):
            source = {'id': f"{record['id']}:{offset}", 'message_id': str(record['id']),
                      'source_id': str(record['evidence_id']), 'origin': 'chat',
                      'text': raw[offset:offset+1800], 'char_start': record['char_start']+offset,
                      'sent_at': record['sent_at'].isoformat() if hasattr(record['sent_at'], 'isoformat') else record['sent_at'],
                      'timestamp_status': record['timestamp_status'], 'timezone_assumed': record['timezone_assumed']}
            if batch and len(json.dumps(batch+[source], ensure_ascii=False)) > 5500:
                yield batch; batch = []
            batch.append(source)
    if batch: yield batch


# A likely new header starts with a date and a clock. Plain continuation lines,
# coordinates, and dates mentioned in prose are outside this denominator.
HEADER_CANDIDATE = re.compile(r"^[\[\(]?(?:\d{1,4}[/.–-]\d{1,2}[/.–-]\d{1,4})"
                              r"[ T,\]]{1,5}\d{1,2}[:.]\d{2}")
ATTACHMENT_CANDIDATE = re.compile(r"(?:<[^<>]{0,15}:?\s*)?[^\n<>]{0,200}\.(?:opus|ogg|mp4|jpe?g|png)\b", re.I)
OBSOLETE_MEDIA = re.compile(r"^<?(?:media omitted|image omitted|video omitted|audio omitted|sticker omitted|"
                            r"multimedia omitid[oa]|imagen omitida|video omitido|audio omitido|sticker omitido)>?\.?$",re.I)
BANNERS = (
    'messages and calls are end-to-end encrypted. only people in this chat can read, listen to, or share them.',
    'los mensajes y las llamadas están cifrados de extremo a extremo. solo las personas en este chat pueden leerlos, escucharlos o compartirlos.',
    'los mensajes y las llamadas están cifrados de extremo a extremo. nadie fuera de este chat, ni siquiera whatsapp, puede leerlos ni escucharlos.',
)


def unknown_sender(payload):
    return bool(': ' not in payload and re.match(r'^[^|—]{1,80}\s+(?:\||—|→)\s+\S',payload))


def format_health(text, records):
    counts={'ios':0,'android':0,'unknown_headers':0,'unknown_attachments':0,'invalid_timestamps':0,'unknown_sender_shape':0}
    for line in text.splitlines():
        match=HEADER.match(line)
        if match:
            counts['ios' if match['ios_date'] else 'android']+=1
            payload=match['payload']
            if unknown_sender(payload):
                counts['unknown_sender_shape']+=1
        elif HEADER_CANDIDATE.match(line.lstrip(MARKS+' ')):
            counts['unknown_headers']+=1
    for record in records:
        if record['timestamp_status'] in ('invalid_datetime','ambiguous_date'):
            counts['invalid_timestamps']+=1
        for line in record['body_text'].splitlines():
            line=line.strip(MARKS+' \t')
            if (line.startswith('<') or line.endswith(')')) and ATTACHMENT_CANDIDATE.search(line):
                if not (ATTACHED.search(line) or NAMED_ATTACHMENT.search(line)):
                    counts['unknown_attachments']+=1
    recognized=counts['ios']+counts['android']
    probable=recognized+counts['unknown_headers']
    missing=counts['unknown_headers']+counts['invalid_timestamps']
    fraction=missing/probable if probable else None
    reasons=[key for key in ('unknown_headers','unknown_attachments','invalid_timestamps','unknown_sender_shape') if counts[key]]
    if not recognized and text.strip(MARKS+' \t\r\n'):
        reasons.append('no_recognized_header')
    severity='degraded' if 'no_recognized_header' in reasons or (fraction is not None and fraction>.10) else (
        'warning' if reasons else 'ok')
    return {**counts,'probable_headers':probable,'recognized_headers':recognized,'unreadable_fraction':fraction,
            'severity':severity,'reasons':reasons,'monitor_version':'chat-format-1'}


def useful_segments(body):
    # Keep exact source offsets across excluded attachment markers or banner lines.
    blocked=sorted([(m.start(),m.end()) for regex in (ATTACHED,NAMED_ATTACHMENT) for m in regex.finditer(body)])
    start=0
    for a,b in blocked+[(len(body),len(body))]:
        chunk=body[start:a]
        cursor=start
        for line in chunk.splitlines(keepends=True):
            normalized=' '.join(line.strip(MARKS+' \t\r\n').casefold().split())
            if normalized in BANNERS or OBSOLETE_MEDIA.fullmatch(normalized):
                if cursor>start:
                    yield start,body[start:cursor]
                start=cursor+len(line)
            cursor+=len(line)
        if a>start:
            yield start,body[start:a]
        start=max(start,b)


def compact_sources(records):
    """Batch contiguous messages with an identical author, keeping exact offsets."""
    batch=[]; size=0; prior_sender=None; prior_time=None; episode=0
    for record in records:
        if record['kind']=='system':
            continue
        body=record['body_text']
        raw=record['raw_text']
        offset=record['char_start']+len(raw)-len(body)
        sender=record['sender_visible']
        time=record['sent_at']
        if isinstance(time,str):
            time=datetime.fromisoformat(time)
        if sender!=prior_sender or (time and prior_time and abs((time-prior_time).total_seconds())>1800):
            episode+=1
            prior_time=None
        for start,segment in useful_segments(body):
            for pos in range(0,len(segment),1700):
                raw_part=segment[pos:pos+1700]
                part=raw_part.strip(MARKS+' \t\r\n')
                if not part:
                    continue
                begin=offset+start+pos+len(raw_part)-len(raw_part.lstrip(MARKS+' \t\r\n'))
                if batch and (size+len(part)>2100 or len(batch)>=25):
                    yield batch
                    batch=[];size=0
                batch.append({'id':f"{record['id']}:{begin-record['char_start']}",
                              'message_id':str(record['id']),'source_id':str(record['evidence_id']),
                              'origin':'chat','text':part,'char_start':begin,'episode':episode,
                              'sent_at':time.isoformat() if time else None,
                              'timestamp_status':record['timestamp_status'],'timezone_assumed':record['timezone_assumed']})
                size+=len(part)
        prior_sender=sender
        if time:
            prior_time=time
    if batch:
        yield batch
