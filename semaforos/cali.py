"""Nomenclatura caleña para cruces reportados en lenguaje cotidiano."""
import re

# POT / IDESC. Las equivalencias numeradas se aplican al corredor citado.
ALIASES = (
    (r'paso\s*ancho|paso\s*anch[oa]', 'avenida Pasoancho', 'calle'),
    (r'sim[oó]n?\s+bol[ií]va?r|sim\.?\s+bol[ií]va?r|sim[oó]n', 'avenida Simón Bolívar', 'calle'),
    (r'ro[o]?s[e]?v[e]?lt|rosbel[t]?', 'avenida Roosevelt', 'calle'),
    (r'circunvalar|cirucunvalar|circunbalar|circunvalacion', 'avenida Circunvalar', 'avenida'),
    (r'ciudad\s+de\s+cali', 'avenida Ciudad de Cali', 'avenida'),
    (r'autopista\s+sur\s*oriental|autopista\s+sur', 'autopista Suroriental', 'calle'),
    (r'autopista\s+oriental|autopista\s+sim[oó]n\s+bol[ií]var', 'autopista Oriental', 'calle'),
)
PREFIXES = {
    'carrera':'carrera', 'carreras':'carrera','cra':'carrera','cr':'carrera','kra':'carrera','kr':'carrera','k':'carrera',
    'calle':'calle','calles':'calle','cll':'calle','cl':'calle','c':'calle',
    'avenida':'avenida','avenidas':'avenida','av':'avenida','diagonal':'diagonal','dg':'diagonal',
    'transversal':'transversal','tv':'transversal',
}
ORDINALS = dict(zip('primera segunda tercera cuarta quinta sexta septima octava novena decima'.split(),range(1,11)))
ONES = 'uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro veinticinco veintiseis veintisiete veintiocho veintinueve'.split()
VALUES = dict(zip(ONES,range(1,30)),**ORDINALS)
TENS = dict(zip('treinta cuarenta cincuenta sesenta setenta ochenta noventa'.split(),range(30,100,10)))
WORDS = r'(?:'+'|'.join(TENS)+r')(?: y (?:'+'|'.join(ONES[:9])+r'))?|'+ '|'.join(sorted(VALUES,key=len,reverse=True))
NUM = rf'(?:[1-9]\d{{0,2}}|{WORDS})(?:[a-z](?=\b))?(?:\s+bis\b)?(?:\s+(?:norte|oeste|sur)\b)?'
PREFIX = r'(?:'+'|'.join(sorted(PREFIXES,key=len,reverse=True))+r')'
TYPED = rf'(?P<prefix>{PREFIX})\.?\s*(?P<number>{NUM})'
NAMES = '|'.join(pattern for pattern,_,_ in ALIASES)
AXIS = re.compile(rf'(?<!\w)(?:(?P<alias>(?:(?:avenida|av\.?)\s+|la\s+)?(?:{NAMES}))|(?P<local>la\s+(?:quinta|44))|{TYPED}|(?:la\s+)?(?P<bare>{NUM}))(?!\w)')
SEPARATOR = re.compile(r'\s*(?:(?:,|/|&|\bcon\b|\by\b|\besquina(?:\s+con)?\b|\bcruce\s+con\b)\s*)?\s*')
NUMBERED_ROAD = r'(?:calle|carrera|avenida|diagonal|transversal) \d{1,3}[a-z]?(?: bis)?(?: norte| oeste| sur)?'
DISPLAY_ROAD = r'(?:'+NUMBERED_ROAD+'|'+ '|'.join(re.escape(label) for _,label,_ in ALIASES)+r')'
ANY_ROAD = re.compile(DISPLAY_ROAD,re.I)
CROSSING = re.compile(rf'{DISPLAY_ROAD} con {DISPLAY_ROAD}',re.I)
MASK = re.compile(r'https?://\S+|<[^>]*>')
AV_PREFIX = re.compile(r'^(?:(?:avenida|av\.?)\s+|la\s+)')
CONTEXT = re.compile(r'\b(?:semaforos?|cruce|esquina|trafico|transito)\b')


def _axis(match):
    if match['alias']:
        alias=AV_PREFIX.sub('',match['alias'])
        return next((label,kind,True) for pattern,label,kind in ALIASES if re.fullmatch(pattern,alias))
    if match['local']:
        return ('calle 5','calle',True) if match['local'].endswith('quinta') else ('carrera 44','carrera',True)
    raw=match['number'] or match['bare']
    if not raw[0].isdecimal():
        word_match=re.match(WORDS,raw)
        word=word_match[0]
        if ' y ' in word:
            tens,one=word.split(' y ')
            number=TENS[tens]+VALUES[one]
        else:
            number=VALUES.get(word,TENS.get(word))
        raw=str(number)+raw[len(word):]
    kind=PREFIXES.get(match['prefix'])
    return (kind+' '+raw if kind else raw),kind,bool(kind)


def _pair(left,right,gap,road_context):
    a,kind_a,explicit_a=left
    b,kind_b,explicit_b=right
    if not SEPARATOR.fullmatch(gap) or (not kind_a and not kind_b):
        return None
    # Un número aislado solo completa un eje si el otro fija su tipo.
    if not explicit_a or not explicit_b:
        if not re.search(r'\b(?:con|y)\b|,|/',gap) or (not gap.strip() and not road_context):
            return None
        known=kind_a or kind_b
        if known not in ('calle','carrera'):
            return None
        complement='carrera' if known=='calle' else 'calle'
        if not kind_a:a=complement+' '+a
        if not kind_b:b=complement+' '+b
    if a==b or (kind_a==kind_b and kind_a in ('calle','carrera')):
        # Dos calles explícitas pueden encontrarse, por ejemplo en un ramal.
        if a==b or not re.search(r'\b(?:con|esquina|cruce)\b',gap):
            return None
    return ' con '.join(sorted((a,b),key=str.casefold)),explicit_a and explicit_b


def locations(text):
    from .conversation_summary import folded
    normalized=folded(MASK.sub(lambda match:' '*len(match[0]),text))
    found={}
    for line in re.finditer(r'[^\n;]+',normalized):
        axes=[(axis,_axis(axis)) for axis in AXIS.finditer(line[0])]
        pairs={}
        cursor = 0
        while cursor + 1 < len(axes):
            a,left=axes[cursor]
            b,right=axes[cursor+1]
            gap=line[0][a.end():b.start()]
            match=_pair(left,right,gap,bool(CONTEXT.search(line[0])))
            if match:
                pairs[match]=(a.start(),b.end())
            cursor += 2 if match else 1
        # Enumeración como “Calle 16 con carrera 98, carrera 86, carrera 85”.
        if len(axes)>2:
            first,base=axes[0]
            _,second=axes[1]
            if base[1]=='calle' and second[1]=='carrera':
                for (previous,_),(axis,road) in zip(axes[1:],axes[2:]):
                    if road[1]!='carrera' or not re.fullmatch(r'\s*(?:,|y)\s*',line[0][previous.end():axis.start()]):
                        break
                    match=_pair(base,road,' con ',True)
                    if match:pairs[match]=(first.start(),axis.end())
        if pairs:
            for (label,explicit),(start,end) in pairs.items():
                found.setdefault(label,{'label':label,'literal':text[line.start()+start:line.start()+end],
                                        'intersection':True,'road_types_explicit':explicit})
        else:
            for axis,(label,_,explicit) in axes:
                if axis['local'] and not CONTEXT.search(line[0]):
                    continue
                if explicit and (label!='avenida Ciudad de Cali' or re.match(r'(?:avenida|av\.)',axis[0])):
                    found.setdefault(label,{'label':label,'literal':text[line.start()+axis.start():line.start()+axis.end()],
                                            'intersection':False,'road_types_explicit':True})
    return list(found.values())
