"""Public, allow-listed projection of already available conversation results."""
import re
from collections import defaultdict
from zoneinfo import ZoneInfo

from .conversation_summary import folded, report_context, source_rows
from .files import canonical_hash
from .findings import ACTIVE_FINDING
from .messages import is_team_sender

CALI = ZoneInfo('America/Bogota')
# Generated crossing strings have two explicit road names and short road numbers.
ROAD = r'(?:calle|carrera|avenida|diagonal|transversal) \d{1,3}(?: ?[a-z])?(?: bis)?'
CROSSING = re.compile(rf'{ROAD} con {ROAD}')
NAMED_ROAD = re.compile(ROAD)
SIGNAL_GPS = re.compile(
    r'\b(?:gps|coordenadas?|ubicacion|localizacion)\s+(?:(?:exact[ao]s?|reportad[ao]s?)\s+)?'
    r'de(?:l| la)\s+(?:semaforo|cruce|interseccion)\b'
)
PUBLIC_TOPICS = {
    'falla_mencionada': 'Falla mencionada',
    'accidente_mencionado': 'Mención de accidente o choque',
    'riesgo_o_casi_accidente': 'Riesgo o casi accidente mencionado',
    'agentes_de_transito': 'Mención de agentes de tránsito',
    'regulacion_del_trafico': 'Mención de personas regulando el tráfico',
    'congestion': 'Congestión mencionada',
    'miedo': 'Miedo expresado',
    'frustracion': 'Frustración o molestia expresada',
}
FAULT_TYPES = {
    'apagado': r'\b(?:apag\w*|no prende[n]?|sin luces?)\b',
    'intermitencia': r'\bintermiten\w*\b',
    'falta de sincronización': r'\b(?:desincroniz\w*|sin sincron\w*)\b',
    'fuera de servicio': r'\b(?:fuera de servicio|sin funcionar|no funciona[n]?)\b',
}
MODALITIES = {'chat':'texto','audio_whatsapp':'audio de WhatsApp','audio_video':'audio de video'}
FINDING_LABELS = {
    'ubicacion':'Ubicación mencionada',
    'descripcion_dano':'Descripción de falla registrada',
    'tiempo_sin_funcionar':'Duración mencionada',
    'afectaciones':'Afectación mencionada',
}


JOBS_QUERY = """
SELECT e.conversation_id,
       bool_or(j.state='running') AS running,
       bool_or(j.state='pending') AS pending,
       bool_or(j.state='failed' OR j.expansion_error IS NOT NULL OR
               r.output->'omitted_assertions' <> '[]'::jsonb) AS errors,
       count(*) FILTER (WHERE j.stage='detect' AND j.state='completed') AS images,
       count(*) FILTER (WHERE j.stage='detect' AND j.state='completed' AND EXISTS (
           SELECT 1 FROM detections d WHERE d.run_id=r.id)) AS images_with_signal
FROM jobs j JOIN evidence e ON e.id=j.evidence_id
LEFT JOIN LATERAL (SELECT id, output FROM runs WHERE job_id=j.id ORDER BY attempt DESC LIMIT 1) r ON true
WHERE j.stage IN ('text','audio','detect','video') AND NOT (j.payload ? 'superseded_by_review')
GROUP BY e.conversation_id
HAVING bool_or(j.state IN ('completed','failed'))
"""


def source_features(source, findings):
    context = report_context(source['text'])
    locations = {item['label'] for item in context['locations']
                 if CROSSING.fullmatch(item['label']) or NAMED_ROAD.fullmatch(item['label'])}
    locations = {' con '.join(sorted(place.split(' con '))) if CROSSING.fullmatch(place) else place
                 for place in locations}
    # A GPS pin from an attachment, device position or isolated map link may be private.
    # Only a point explicitly described as the intersection/signal can be eligible.
    point = None
    if (len(locations)==1 and CROSSING.fullmatch(next(iter(locations)))
            and len(context['gps'])==1 and SIGNAL_GPS.search(folded(source['text']))):
        result = context['gps'][0]
        point = (result['latitude'],result['longitude'])
    topics = {m['category'] for m in context['mentions'] if m['qualifier']=='mencionado'}
    if any(m['qualifier']=='riesgo_o_casi' for m in context['mentions']):
        topics.add('riesgo_o_casi_accidente')
    text = folded(source['text'])
    if re.search(r'\b(?:me da miedo|nos da miedo|tengo miedo|tenemos miedo|me asusta)\b', text):
        topics.add('miedo')
    if re.search(r'\b(?:me da rabia|nos da rabia|me frustra|nos frustra|me molesta|nos molesta)\b', text):
        topics.add('frustracion')
    # Literal durations are already extracted by a closed vocabulary and contain no free text.
    durations = {folded(value) for value in context['durations']}
    fault_types = {label for label,pattern in FAULT_TYPES.items()
                   for m in context['mentions']
                   if m['category']=='falla_mencionada' and m['qualifier']=='mencionado'
                   and re.search(pattern,folded(m['literal']))}
    return {'locations':locations,'point':point,'topics':topics,'durations':durations,
            'findings':findings,'fault_types':fault_types,'quantities':context['quantities'],
            'signal_mention':context['traffic_signal_mentioned']}


def make_item(conversation_id, source_group, day, location, values, processing, *, points_allowed):
    dates = [source['sent_at'] for source,_ in values if source['sent_at']]
    topics = set().union(*(features['topics'] for _,features in values))
    durations = set().union(*(features['durations'] for _,features in values))
    findings = set().union(*(features['findings'] for _,features in values))
    modalities = {MODALITIES[source['origin']] for source,_ in values}
    descriptions = [label for key,label in PUBLIC_TOPICS.items() if key in topics]
    if not descriptions:
        descriptions = [label for key,label in FINDING_LABELS.items() if key in findings]
    fault_types = set().union(*(features['fault_types'] for _,features in values))
    quantities = {n for _,features in values for n in features['quantities']}
    if fault_types:
        descriptions.append('Tipo de falla mencionado: '+', '.join(sorted(fault_types)))
    if quantities:
        descriptions.append('Cantidad de semáforos mencionada: '+', '.join(str(n) for n in sorted(quantities)))
    if durations:
        descriptions.append('Tiempo mencionado: '+', '.join(sorted(durations)))
    if modalities:
        descriptions.append('Fuentes: '+', '.join(sorted(modalities)))
    if not descriptions or not (topics or findings or location or durations or quantities):
        descriptions.insert(0,'Resultado disponible sin una falla o un cruce identificable automáticamente')
    if processing['images']:
        descriptions.append(
            f'Detección visual en {processing["images_with_signal"]} de {processing["images"]} '
            'fotos o fotogramas de la conversación')
    points = {features['point'] for _,features in values if features['point']}
    lat,lon = next(iter(points)) if points_allowed and len(points)==1 else (None,None)
    code = canonical_hash([str(conversation_id),source_group,str(day),location])[:16].upper()
    return {'code':'P-'+code,'date':min(dates) if dates else None,'intersection':location,
            'description': ' · '.join(descriptions), 'revision':'pendiente',
            'processing':'procesando' if processing['running'] else 'en_cola' if processing['pending'] else
                          'parcial_con_errores' if processing['errors'] else 'completado',
            'latitude':lat,'longitude':lon,'preliminary':True,'_public':True}


def automatic_items(c, blocked_sources, *, points_allowed):
    jobs = {row['conversation_id']:row for row in c.execute(JOBS_QUERY)}
    findings = defaultdict(set)
    for row in c.execute('''
        SELECT CASE WHEN f.origin='chat' THEN f.message_id ELSE f.evidence_id END AS source_id, f.variable
        FROM findings f WHERE '''+ACTIVE_FINDING):
        findings[row['source_id']].add(row['variable'])

    grouped = defaultdict(list)
    represented = set()
    for source in source_rows(c):
        conv = source['conversation_id']
        if conv not in jobs or is_team_sender(source['sender']):
            continue
        if source['id'] in blocked_sources:
            represented.add(conv)
            continue
        if not source['text'].strip():
            continue
        features = source_features(source,findings[source['id']])
        day = source['sent_at'].astimezone(CALI).date() if source['sent_at'] else None
        grouped[conv,source['sender'],day].append((source,features))

    result = []
    visible_conversations = set()
    for (conv,sender,day), values in grouped.items():
        locations = set().union(*(features['locations'] for _,features in values))
        intersections = {place for place in locations if CROSSING.fullmatch(place)}
        places = intersections or locations
        relevant = [(source,features) for source,features in values
                    if any(features[key] for key in ('locations','topics','durations','findings','signal_mention','point'))]
        if not relevant:
            continue
        assigned = False
        for place in sorted(places):
            related = [(source,features) for source,features in relevant
                       if features['locations']=={place} or (len(places)==1 and
                           (not features['locations'] or features['locations'] & {place}))]
            # When several crosses appear, publish their names independently.
            # Ambiguous narratives remain in a separate row without location.
            result.append(make_item(conv,sender,day,place,related,jobs[conv],points_allowed=points_allowed))
            assigned |= bool(related)
        ambiguous = [(source,features) for source,features in relevant
                     if len(places)>1 and (len(features['locations'])!=1 or not (features['locations'] & places))]
        if not places or ambiguous or not assigned:
            result.append(make_item(conv,sender,day,None,ambiguous or relevant,jobs[conv],points_allowed=False))
        visible_conversations.add(conv)

    for conv in sorted(jobs.keys()-visible_conversations-represented):
        result.append(make_item(conv,None,None,None,[],jobs[conv],points_allowed=False))
        visible_conversations.add(conv)
    return result, visible_conversations
