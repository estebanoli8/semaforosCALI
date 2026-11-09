"""Lectura conservadora de exportaciones WhatsApp. Nunca altera el texto fuente."""
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARSER_VERSION = 'whatsapp-1'
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
        if match: boundaries.append((cursor, match))
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
                item['kind'] = 'system'
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
