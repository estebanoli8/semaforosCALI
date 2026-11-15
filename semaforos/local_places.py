"""Conservative location hints grounded in the Cali catalog and literal source."""
import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .cali import locations

SPATIAL = re.compile(r'\b(?:frente|cerca|lado|llegando|pasando|al frente|esquina|cruce|calle|carrera|cra|kr|cll|sem[aá]foro)\b', re.I)
PAIR = re.compile(r'(?<![\w\d-])(\d{1,3})\s*(?:con|[x×])\s*(\d{1,3})(?![\w\d-])', re.I)
AMBIGUOUS = {'cvc', 'la cvc', 'la estacion', 'imbanaco', 'la santiago', 'uao', 'el pascual', 'huv'}


def fold(text):
    return ''.join(char for char in unicodedata.normalize('NFD',text.lower()) if not unicodedata.combining(char))


@lru_cache(maxsize=1)
def catalog():
    path=Path(__file__).with_name('assets')/'referentes-cali-v0.1.csv'
    with path.open(encoding='utf-8-sig',newline='') as stream:
        return [(row['nombre_canonico'],row['estatus_catalogo'],alias.strip())
                for row in csv.DictReader(stream) for alias in row['variantes_sugeridas'].split(';') if alias.strip()]


def hints(text):
    recognized=[{'label':p['label'],'status':'cruce_explicito','literal':p['literal']}
                for p in locations(text) if p['intersection'] and p['road_types_explicit']]
    if recognized:
        return recognized
    normalized=fold(text)
    # Applicability of an alias is independent of certainty about a specific crossing.
    places={}
    for name,status,alias in catalog():
        alias=fold(alias)
        if alias in AMBIGUOUS and not SPATIAL.search(text):
            continue
        match=re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',normalized)
        if match:
            places.setdefault(name,{'label':name,'status':'referencia_no_confirmada' if status=='alias_por_confirmar'
                                    else 'referencia','literal':text[match.start():match.end()]})
    results=list(places.values())
    for pair in PAIR.finditer(text):
        a,b=pair.groups()
        # Bare pairs carry a candidate, including the local reading of 5 x 5.
        results.append({'label':f'Calle {a} con Carrera {b}','status':'por_confirmar','literal':pair[0]})
    if not results:
        results=[{'label':x['label'],'status':'via_mencionada','literal':x['literal']} for x in locations(text)]
    return results
