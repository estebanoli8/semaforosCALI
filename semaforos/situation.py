"""Controlled textual synthesis suitable for a citizen report table."""
TOPIC_PHRASES = {
    'agentes_de_transito':'el relato menciona guardas o agentes de tránsito',
    'regulacion_informal':'se relata que particulares dirigen el tráfico',
    'regulacion_del_trafico':'se menciona regulación del tránsito',
    'accidente_mencionado':'se mencionan accidentes o choques',
    'riesgo_o_casi_accidente':'se menciona riesgo vial o un casi accidente',
    'congestion':'se reporta congestión',
    'desorden':'se describe desorden vial',
    'afectacion_peatonal':'se describe dificultad o riesgo al cruzar',
    'demora':'se mencionan demoras',
    'miedo':'el relato expresa miedo',
    'frustracion':'el relato expresa frustración o molestia',
}


def _sentence(text):
    return text[:1].upper()+text[1:]+'.'


def synthesize(location,topics,fault_types,durations,*,found_fault=False):
    location_phrase=f' en {location}' if location else ''
    fault=bool(fault_types or found_fault or 'falla_mencionada' in topics)
    if fault and fault_types:
        opening='Se reporta una falla'+location_phrase+' ('+', '.join(sorted(fault_types))+')'
    elif fault:
        opening='Se reporta una falla del semáforo'+location_phrase
    elif location:
        opening='El reporte ubica la evidencia en '+location
    else:
        opening='El material del reporte está disponible para revisión'
    sentences=[_sentence(opening)]
    if durations and fault:
        sentences.append(_sentence('Tiempo mencionado '+', '.join(sorted(durations))))
    for key,phrase in TOPIC_PHRASES.items():
        if key in topics and not (key=='regulacion_del_trafico' and 'regulacion_informal' in topics):
            sentences.append(_sentence(phrase))
    return ' '.join(sentences)
