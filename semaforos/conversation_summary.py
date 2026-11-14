"""Conservative, source-linked summaries of what people reported."""
import re
from collections import Counter, defaultdict
from urllib.parse import parse_qs, unquote, urlsplit
from .messages import is_team_sender

NUMBER_WORDS = (
    'cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince '
    'dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro '
    'veinticinco veintiseis veintisiete veintiocho veintinueve'
).split()
NUMBERS = dict(zip(NUMBER_WORDS, range(len(NUMBER_WORDS))))
NUMBERS.update(zip('primera segunda tercera cuarta quinta sexta septima octava novena decima'.split(), range(1, 11)))
NUMBERS.update(un=1, una=1, cien=100, ciento=100)
TENS = dict(zip('treinta cuarenta cincuenta sesenta setenta ochenta noventa'.split(), range(30, 100, 10)))
NUMBER = r'(?:\d{1,3}|(?:ciento )?(?:' + '|'.join(TENS) + r')(?: y (?:' + '|'.join(NUMBER_WORDS[1:10]) + r'))?|'+ '|'.join(sorted(NUMBERS, key=len, reverse=True)) + r')'
ROAD = r'(?:calle|carrera|avenida|diagonal|transversal|cra\.?|cl\.?|av\.?)'
ROAD_NUMBER = NUMBER + r'(?:(?:[a-z]|\s+[a-z])(?!\w))?(?:\s+bis\b)?'
INTERSECTION = re.compile(rf'\b(?P<a>{ROAD}\s+{ROAD_NUMBER}|(?:la\s+)?{NUMBER})\s+(?:con|esquina con|cruce con|y)\s+(?P<b>{ROAD}\s+{ROAD_NUMBER}|(?:la\s+)?{NUMBER})\b')
STREET = re.compile(rf'\b{ROAD}\s+{ROAD_NUMBER}\b')
DURATION = re.compile(rf'\b(?:{NUMBER}|varios?|varias?|muchos?|muchas?)\s+(?:dias?|semanas?|mes(?:es)?|horas?|años?)\b|\bdesde\s+(?:ayer|anoche|anteayer|el\s+(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo))\b')
COUNT = re.compile(rf'\b({NUMBER})\s+semaforos?\b')
COORDINATE_PAIR = r'([+-]?\d{1,3}\.\d{3,})\s*[,;]\s*([+-]?\d{1,3}\.\d{3,})'
MAP_URL = re.compile(r'https?://[^\s<>]+', re.I)
PATTERNS = {
    'falla_mencionada': r'\b(?:apag[ao]d[oa]s?|dañad[oa]s?|averiad[oa]s?|mal[oa]s?|fuera de servicio|sin funcionar|no (?:esta[n]? funcionando|funciona[n]?|sirve[n]?|prende[n]?)|intermiten\w*|desincroniz\w*|sin sincron\w*)\b',
    'accidente_mencionado': r'\b(?:accidentes?|choques?|colisi(?:on|ones)|atropell\w*|se (?:chocaron|estrellaron)|choco|estrello)\b',
    'riesgo_o_casi_accidente': r'\b(?:casi|por poco|a punto de|riesgo|peligro|posibles?|evitar|prevenir|puede[n]? (?:chocar|accidentarse)|podria[n]? (?:chocar|accidentarse))\b',
    'agentes_de_transito': r'\b(?:guardas?|agentes? de transito|policia de transito|autoridades? de transito|alfere[zc]\w*)\b',
    'regulacion_del_trafico': r'\b(?:regul\w*|dirig\w*|control\w*|organiz\w*|dando paso)\b.{0,45}\b(?:trafico|transito|paso|carros|vehiculos|movilidad)\b|\b(?:dando paso|paleter[oa]s?|banderiller[oa]s?|reguladores? viales?)\b',
    'congestion': r'\b(?:trancon(?:es)?|congestion\w*|embotell\w*|atasco|trancado|trafico pesado)\b',
}
COMPILED = {key: re.compile(value) for key, value in PATTERNS.items()}
NEGATION = re.compile(r'\b(?:no (?:hay|hubo|ha habido|habia|paso|ocurrio|se produjo|llego|esta|estaba|vino|vimos)|sin (?:ningun |ninguna )?|ni)\s*(?:ningun\w*\s+|un\w*\s+|\w+\s+){0,3}$')


def folded(text):
    # Preserve ñ and character offsets for literal excerpts.
    return text.lower().translate(str.maketrans('áéíóúü', 'aeiouu'))


def number_value(text):
    if text.isdecimal():
        return int(text)
    if text.startswith('ciento '):
        return 100 + number_value(text[7:])
    if ' y ' in text:
        tens, units = text.split(' y ', 1)
        return TENS[tens] + NUMBERS[units]
    return NUMBERS.get(text, TENS.get(text))


def normalize_road(road):
    road = re.sub(r'^la\s+', '', road)
    road = re.sub(r'^(?:cra|cl|av)\.?\s+', lambda m: {
        'cra': 'carrera ', 'cl': 'calle ', 'av': 'avenida '
    }[m.group(0).strip().rstrip('.')], road)
    return re.sub(rf'\b{NUMBER}\b', lambda m: str(number_value(m.group())), road)


def gps_coordinates(text):
    """Read coordinate-bearing map links and explicitly labelled GPS pairs."""
    candidates = []
    for match in MAP_URL.finditer(text):
        literal = match.group().rstrip('.,)')
        try:
            url = urlsplit(literal)
        except ValueError:
            continue
        host = url.hostname or ''
        if host not in {'maps.google.com', 'www.google.com', 'google.com', 'maps.apple.com', 'www.openstreetmap.org', 'openstreetmap.org'}:
            continue
        if host in {'www.google.com', 'google.com'} and not url.path.startswith('/maps'):
            continue
        try:
            params = parse_qs(url.query, max_num_fields=50)
        except ValueError:
            continue
        # Prefer a destination or pin over the map viewport center.
        values = [v for key in ('destination', 'query', 'q', 'll') for v in params.get(key, [])]
        if host.endswith('openstreetmap.org') and params.get('mlat') and params.get('mlon'):
            values.append(params['mlat'][0] + ',' + params['mlon'][0])
        pairs = [re.fullmatch(COORDINATE_PAIR, v.strip()) for v in values]
        found = next((pair for pair in pairs if pair), None)
        if found:
            candidates.append((found.groups(), literal))
        else:
            pin = re.search(r'!3d([+-]?\d+\.\d{3,})!4d([+-]?\d+\.\d{3,})', unquote(url.path))
            if pin:
                candidates.append((pin.groups(), literal))
    for match in re.finditer(r'(?:\bgps\b|coordenadas|ubicaci[oó]n|location)\s*[:=]?\s*' + COORDINATE_PAIR, text, re.I):
        candidates.append((match.groups(), match.group()))
    for line in text.splitlines():
        pair = re.fullmatch(COORDINATE_PAIR, line.strip())
        if pair:
            candidates.append((pair.groups(), line.strip()))
    result = {}
    for (lat, lon), literal in candidates:
        lat, lon = float(lat), float(lon)
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            result.setdefault((lat, lon), {'latitude': lat, 'longitude': lon, 'literal': literal})
    return list(result.values())


def report_context(text):
    # Remove map URLs from lexical analysis while keeping original character offsets.
    lexical = MAP_URL.sub(lambda match: ' ' * len(match.group()), text)
    normalized = folded(lexical)
    locations = []
    for match in INTERSECTION.finditer(normalized):
        # An unlabelled pair needs a semáforo/crossing context and explicit "con".
        sides = (match['a'], match['b'])
        named = any(re.match(ROAD, side) for side in sides)
        if named or (' con ' in match.group() and re.search(r'\b(?:semaforos?|cruce|esquina|interseccion)\b', normalized)):
            label = ' con '.join(normalize_road(side) for side in sides)
            locations.append({'label': label, 'literal': text[match.start():match.end()],
                              'intersection': True, 'road_types_explicit': all(re.match(ROAD, side) for side in sides)})
    if not locations:
        for match in STREET.finditer(normalized):
            locations.append({'label': normalize_road(match.group()), 'literal': text[match.start():match.end()],
                              'intersection': False, 'road_types_explicit': True})
    mentions = []
    for sentence in re.finditer(r'[^.!?;\n]+[!?]?', normalized):
        part = sentence.group().strip()
        if not part:
            continue
        risk = bool(COMPILED['riesgo_o_casi_accidente'].search(part))
        for category, pattern in COMPILED.items():
            for match in pattern.finditer(part):
                qualifier = 'pregunta' if part.endswith('?') else 'negado' if NEGATION.search(part[:match.start()]) else 'mencionado'
                if category == 'accidente_mencionado' and risk and qualifier == 'mencionado':
                    qualifier = 'riesgo_o_casi'
                mentions.append({'category': category, 'qualifier': qualifier,
                                 'literal': text[sentence.start():sentence.end()].strip()[:350]})
                break
    quantities = [number_value(match[1]) for match in COUNT.finditer(normalized)
                  if not NEGATION.search(normalized[max(0,match.start()-55):match.start()])
                  and '?' not in normalized[match.end():].split('.')[0]]
    return {'locations': locations, 'gps': gps_coordinates(text), 'mentions': mentions,
            'durations': [text[m.start():m.end()] for m in DURATION.finditer(normalized)],
            'quantities': [n for n in quantities if n and n > 0],
            'traffic_signal_mentioned': bool(re.search(r'\bsemaforos?\b', normalized))}


def summarize(sources):
    groups = defaultdict(list)
    for source in sources:
        sender = source.get('sender')
        if not is_team_sender(sender):
            groups[sender].append(source)
    result = []
    for sender, rows in groups.items():
        locations, gps, mentions, durations = {}, {}, {}, {}
        quantities = []
        has_report = False
        for source in rows:
            context = report_context(source['text'])
            origin = {'origin': source['origin'], 'source_id': str(source['id'])}
            for item in context['locations']:
                key = tuple(sorted(item['label'].split(' con ')))
                locations.setdefault(key, dict(item, **origin))
            for item in context['gps']:
                gps.setdefault((item['latitude'], item['longitude']), dict(item, **origin))
            for item in context['mentions']:
                mentions.setdefault((item['category'], item['qualifier'], folded(item['literal'])), dict(item, **origin))
            for literal in context['durations']:
                durations.setdefault(folded(literal), dict(literal=literal, **origin))
            quantities.extend(context['quantities'])
            has_report |= context['traffic_signal_mentioned'] and any(
                m['qualifier'] == 'mencionado' and m['category']=='falla_mencionada' for m in context['mentions'])
        if not (locations or gps or mentions or durations or quantities or has_report):
            continue
        intersections = sum(item['intersection'] for item in locations.values())
        # Repeated mentions and multiple cameras never add to a physical count.
        estimate = max(intersections if has_report or quantities else 0, max(quantities, default=0), int(has_report)) or None
        result.append({'reporter': sender, 'reported_estimate': estimate,
                       'explicit_quantities': sorted(set(quantities)),
                       'locations': list(locations.values()), 'gps': list(gps.values()),
                       'mentions': list(mentions.values()), 'durations': list(durations.values())})
    return result


def source_rows(connection, conversation_id=None):
    # Read the latest parse and one transcript per audio, with preference for a human correction.
    return connection.execute("""
        WITH selected_evidence AS (
            SELECT e.* FROM evidence e WHERE (%(cid)s::uuid IS NULL OR e.conversation_id=%(cid)s::uuid)
              AND e.modality IN ('chat','audio')
        ), latest_parse AS (
            SELECT DISTINCT ON (p.evidence_id) p.id FROM chat_parses p
            JOIN selected_evidence e ON e.id=p.evidence_id
            ORDER BY p.evidence_id,p.created_at DESC,p.id DESC
        ), latest_audio AS (
            SELECT DISTINCT ON (e.id) e.conversation_id,e.id,e.parent_id,
                coalesce(correction.human_label->>'text',r.output->>'analysis_text',t.literal_text) AS text
            FROM selected_evidence e JOIN transcripts t ON t.evidence_id=e.id
            JOIN runs r ON r.id=t.run_id
            LEFT JOIN LATERAL (
                SELECT rv.human_label FROM reviews rv WHERE rv.run_id=r.id AND rv.field='curation'
                  AND rv.human_label->>'decision'='corrected'
                ORDER BY rv.created_at DESC,rv.id DESC LIMIT 1
            ) correction ON true
            WHERE r.state='completed' AND NOT (r.output ? 'excluded')
            ORDER BY e.id,(correction.human_label IS NOT NULL) DESC,r.finished_at DESC,r.id DESC
        )
        SELECT e.conversation_id,m.id,m.sender_visible AS sender,m.body_text AS text,'chat' AS origin
        FROM latest_parse p JOIN messages m ON m.parse_id=p.id JOIN selected_evidence e ON e.id=m.evidence_id
        WHERE m.kind<>'system'
        UNION ALL
        SELECT a.conversation_id,a.id,linked.sender,a.text,
            CASE WHEN a.parent_id IS NULL THEN 'audio_whatsapp' ELSE 'audio_video' END
        FROM latest_audio a LEFT JOIN LATERAL (
            SELECT CASE WHEN count(DISTINCT m.sender_visible)=1 AND count(*)=count(m.sender_visible)
                THEN min(m.sender_visible) END AS sender,
                bool_and(lower(btrim(m.sender_visible))='esteban oli') AS team_only
            FROM message_attachments ma JOIN messages m ON m.id=ma.message_id
            WHERE ma.state='linked' AND ma.evidence_id IN (a.id,a.parent_id)
        ) linked ON true WHERE linked.team_only IS DISTINCT FROM true
        """, {'cid': conversation_id})


def conversation_report(store, conversation_id):
    with store.connect() as connection:
        return {'reporters': summarize(source_rows(connection, conversation_id))}


def statistics(store):
    groups = defaultdict(list)
    with store.connect() as connection:
        for source in source_rows(connection):
            if source['text'].strip() and not is_team_sender(source['sender']):
                groups[source['conversation_id']].append(source)
    topics = Counter()
    totals = Counter(conversations_analyzed=len(groups), conversations_with_mentions=0,
                     reporter_groups=0, groups_with_gps=0, groups_with_duration=0, groups_with_count=0)
    for rows in groups.values():
        reports = summarize(rows)
        totals['conversations_with_mentions'] += bool(reports)
        totals['reporter_groups'] += len(reports)
        totals['groups_with_gps'] += sum(bool(report['gps']) for report in reports)
        totals['groups_with_duration'] += sum(bool(report['durations']) for report in reports)
        totals['groups_with_count'] += sum(report['reported_estimate'] is not None for report in reports)
        for report in reports:
            topics.update({m['category'] for m in report['mentions'] if m['qualifier']=='mencionado'})
    return {**totals, 'topics': dict(topics)}
