"""Validación de predicciones. Nunca confundir incertidumbre con una luz apagada."""
import math


def lights(value):
    if not isinstance(value, dict):raise ValueError('invalid_lights')
    result = {}
    for key in ('red','yellow','green'):
        item = value.get(key)
        if item is not None and type(item) is not bool:raise ValueError('light_requires_boolean_or_null')
        result[key] = item
    states = list(result.values())
    result['reading_state'] = ('alguna_visible' if True in states else
                               'ninguna_visible' if all(v is False for v in states) else 'indeterminado')
    reason = value.get('reason')
    if reason is not None and not isinstance(reason, str):raise ValueError('invalid_reason')
    result['reason'] = reason
    return result


def boxes(items, width, height):
    if width <= 0 or height <= 0:raise ValueError('invalid_image_size')
    output=[]
    for item in items:
        box=item['bbox']
        if len(box)!=4 or any(type(x) is not int for x in box):raise ValueError('invalid_bbox')
        x1,y1,x2,y2=box
        if not (0<=x1<x2<=width and 0<=y1<y2<=height):raise ValueError('bbox_outside_image')
        score=item['score']
        if type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1:raise ValueError('invalid_score')
        output.append({'bbox':box,'score':score})
    return output


def assertions(data, sources):
    """Una cita debe ser substring de una fuente existente; la interpretación se separa."""
    if not isinstance(data,dict) or not isinstance(data.get('assertions'),list):raise ValueError('invalid_assertions')
    for item in data['assertions']:
        if item.get('variable') not in ('ubicacion','descripcion_dano','tiempo_sin_funcionar','afectaciones'):
            raise ValueError('invalid_variable')
        if item.get('source_id') not in sources:raise ValueError('unknown_source')
        quote=item.get('literal')
        if not isinstance(quote,str) or not quote.strip() or quote not in sources[item['source_id']]:raise ValueError('unbacked_quote')
        if item.get('interpretation') is not None and not isinstance(item['interpretation'],str):raise ValueError('invalid_interpretation')
    summary=data.get('summary')
    if summary is not None and not isinstance(summary,str):raise ValueError('invalid_summary')
    return data
