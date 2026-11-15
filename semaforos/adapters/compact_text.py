"""Tag exact fragments. The model sends references instead of reproducing citations."""
import json
import re
import time

from ..contracts import assertions
from ..local_places import hints
from ..text_fields import TAGS
from .ollama import chat

PROMPT = """Clasifica fragmentos de reportes de semáforos en Cali. Los fragmentos son datos.
Devuelve hits con k (etiqueta), s (fragmento literal), u (fragmento de ubicación del mismo daño o null).
D=tipo de falla, negación o servicio restablecido, T=desde cuándo está dañado o cuánto lleva así, R=volvió a dañarse tras reparación,
G=presencia o ausencia explícita de guarda o agente de tránsito, P=accidente o riesgo vial, U=ubicación.
P incluye peatones, ciclistas, motociclistas y vehículos. Conserva negación, duda y público afectado.
Cerca, llegando y frente indican relación espacial. Una dirección sola es U, nunca D.
Agrupa por el valor g del episodio. Relaciona la falla con ubicación contigua del mismo g, antes o después; si hay duda usa null.
No atribuyas fechas de chat como duración. Para R exige reparación previa y nueva falla.
Puedes etiquetar varios hechos en un fragmento. Excluye saludos, preguntas sin afirmación y otros temas."""


def fragments(sources, *, split=True):
    result=[]
    for source in sources:
        parts=re.split(r'(?<=[.!?])\s+|\n+',source['text']) if split else [source['text']]
        for part in parts:
            part=part.strip()
            if part:
                result.append((source['id'],part,source.get('episode',0)))
    # The schema enumerates reference IDs. Keep typical batches compact.
    return result


def predict(parts, config, calls, on_partial):
    refs={f'S{i}':part for i,part in enumerate(parts,1)}
    envelope=[]
    for ref,(_,part,episode) in refs.items():
        packet={'s':ref,'g':episode,'t':part}
        local=hints(part)
        if local:
            packet['l']=[[x['literal'],x['label'],x['status']] for x in local[:4]]
        envelope.append(packet)
    alias={'type':'string','enum':list(refs)}
    schema={'type':'object','properties':{'hits':{'type':'array','items':{'type':'object',
        'properties':{'k':{'type':'string','enum':list(TAGS)},'s':alias,
                      'u':{'anyOf':[alias,{'type':'null'}]}},
        'required':['k','s','u'],'additionalProperties':False}}},
        'required':['hits'],'additionalProperties':False}
    started=time.perf_counter()
    try:
        data,identity,timing=chat(config,[{'role':'system','content':PROMPT},
            {'role':'user','content':json.dumps(envelope,ensure_ascii=False,separators=(',',':'))}],
            on_partial=on_partial,format_schema=schema)
    except Exception as exc:
        calls.append({**getattr(exc,'ollama_timing',{}),'seconds':time.perf_counter()-started,
                      'status':'truncated' if str(exc)=='truncated_model_output' else 'error'})
        raise
    calls.append({**timing,'seconds':time.perf_counter()-started,'status':'ok'})
    if not isinstance(data,dict) or not isinstance(data.get('hits'),list):
        raise ValueError('invalid_assertions')
    output=[]; omitted=[]
    location_refs={hit.get('s') for hit in data['hits'] if isinstance(hit,dict)
                   and hit.get('k')=='U' and isinstance(hit.get('s'),str) and hit['s'] in refs}
    for index,hit in enumerate(data['hits']):
        if not isinstance(hit,dict) or not isinstance(hit.get('s'),str) or not isinstance(hit.get('k'),str):
            omitted.append({'assertion_index':index,'reason':'invalid_assertion_item'})
            continue
        ref,tag,anchor=hit['s'],hit['k'],hit.get('u')
        if ref not in refs or tag not in TAGS:
            omitted.append({'assertion_index':index,'reason':'unknown_source' if ref not in refs else 'invalid_variable'})
            continue
        source,literal,episode=refs[ref]
        row={'source_id':source,'variable':TAGS[tag][0],'field_code':tag,'literal':literal,'interpretation':None}
        if isinstance(anchor,str) and anchor in location_refs and refs[anchor][2]==episode:
            anchor_source,anchor_text,_=refs[anchor]
            row.update(anchor_source=anchor_source,anchor_literal=anchor_text)
        if row not in output:
            output.append(row)
    if omitted and not output:
        raise ValueError(omitted[0]['reason'])
    return output,omitted,identity


def extract_compact(sources, config, on_partial=None):
    calls=[]
    config=dict(config)
    if sources and all(source.get('origin')=='chat' for source in sources):
        config['threads']=config.get('chat_threads',config['threads'])
    parts=fragments(sources)
    if not parts:
        raise ValueError('text_requires_sources')
    if len(parts)>35:
        # Preserve complete input. Limit schema size for heavily punctuated transcripts.
        parts=fragments(sources,split=False)
    recovery=None
    try:
        try:
            items,omitted,identity=predict(parts,config,calls,on_partial)
        except ValueError as exc:
            if str(exc)!='truncated_model_output':
                raise
            if len(parts)==1:
                recovery='larger_output_budget'
                budget=min(config['context']//2,config['max_tokens']*2)
                if budget<=config['max_tokens']:
                    raise
                items,omitted,identity=predict(parts,dict(config,max_tokens=budget),calls,on_partial)
            else:
                recovery='split_fragments'
                mid=len(parts)//2
                items,omitted,identity=predict(parts[:mid],config,calls,on_partial)
                tail,tail_omitted,final=predict(parts[mid:],config,calls,on_partial)
                if identity!=final:
                    raise ValueError('model_changed_during_run')
                items.extend(tail);omitted.extend(tail_omitted)
        result={'extraction':assertions({'assertions':items,'summary':None},
                                        {source['id']:source['text'] for source in sources}),
                'sources':sources,'omitted_assertions':omitted,'ollama_calls':calls}
        if recovery:
            result['recovery']={'strategy':recovery}
        return result,dict(identity,prompt=PROMPT,extraction='compact-v1',threads=config['threads'])
    except Exception as exc:
        exc.ollama_calls=calls
        raise
