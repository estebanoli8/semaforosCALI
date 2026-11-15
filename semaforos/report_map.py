"""Projection of curated reports and one geographic snapshot for web and PDF."""
import hashlib
import json
import math
import os
import unicodedata
from collections import Counter
from pathlib import Path

from .conversation_summary import gps_coordinates
from .reports import ReportError, detail
from .public_results import CROSSING, automatic_items, source_features, situation_text
from .report_evidence import attach_evidence

CALI_EXTENT = (-76.62, 3.29, -76.44, 3.55)
WIDTH, HEIGHT, PAD = 720, 430, 40


def boundary(root):
    path = Path(os.getenv('SC_URBAN_BOUNDARY') or root / 'cartografia' / 'cali-urbano.geojson')
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
        if data['type'] == 'FeatureCollection':
            geometries = [feature['geometry'] for feature in data['features']]
        elif data['type'] == 'Feature':
            geometries = [data['geometry']]
        else:
            geometries = [data]
        polygons = []
        for geometry in geometries:
            if geometry['type'] not in ('Polygon', 'MultiPolygon'):
                raise ValueError('expected_polygon')
            groups = geometry['coordinates']
            for polygon in [groups] if geometry['type'] == 'Polygon' else groups:
                rings = [[(float(point[0]), float(point[1])) for point in ring] for ring in polygon]
                if not rings or any(len(ring) < 4 or ring[0] != ring[-1] for ring in rings):
                    raise ValueError('invalid_ring')
                if any(not (-77 < x < -76 and 3 < y < 4) for ring in rings for x, y in ring):
                    raise ValueError('expected_cali_wgs84')
                polygons.append(rings)
        if not polygons:
            raise ValueError('empty_boundary')
        points = [point for polygon in polygons for ring in polygon for point in ring]
        if len({x for x,_ in points}) < 2 or len({y for _,y in points}) < 2:
            raise ValueError('degenerate_boundary')
        return polygons, 'sha256:' + hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return [], None


def contains(ring, x, y):
    inside = False
    last_x, last_y = ring[-1]
    for next_x, next_y in ring:
        cross = (x-last_x)*(next_y-last_y) - (y-last_y)*(next_x-last_x)
        if (abs(cross) < 1e-12 and min(last_x,next_x) <= x <= max(last_x,next_x)
                and min(last_y,next_y) <= y <= max(last_y,next_y)):
            return True
        if (last_y > y) != (next_y > y) and x < last_x+(y-last_y)*(next_x-last_x)/(next_y-last_y):
            inside = not inside
        last_x, last_y = next_x, next_y
    return inside


def inside_city(polygons, lon, lat):
    if not polygons:
        return None
    return any(contains(p[0],lon,lat) and not any(contains(r,lon,lat) for r in p[1:]) for p in polygons)


def coordinates(lat, lon):
    if (lat is None) != (lon is None):
        raise ReportError('coordinates_require_pair')
    if lat is not None and (not math.isfinite(lat) or not math.isfinite(lon)
                            or not (-90 <= lat <= 90 and -180 <= lon <= 180)):
        raise ReportError('invalid_coordinates')


def crossing_key(text):
    key = ' '.join(unicodedata.normalize('NFKC', text).casefold().split())
    return ' con '.join(sorted(key.split(' con '))) if CROSSING.fullmatch(key) else key


def save_location(store, ident, body):
    coordinates(body['latitude'], body['longitude'])
    title = body['intersection'].strip()
    description = (body['public_description'] or '').strip() or None
    reviewer = body['reviewer'].strip()
    if not title or not reviewer or (body['published'] and not description):
        raise ReportError('public_fields_required' if body['published'] else 'location_fields_required')
    with store.connect() as c:
        report = c.execute('SELECT version,primary_finding_id,revision FROM reports WHERE id=%s FOR UPDATE',
                           (ident,)).fetchone()
        if not report:
            raise ReportError('report_not_found')
        if report['revision']=='descartado' or report['version'] != body['expected_report_version']:
            raise ReportError('version_conflict_reload')
        previous = c.execute('SELECT version FROM report_map_entries WHERE report_id=%s',(ident,)).fetchone()
        previous_version = previous['version'] if previous else 0
        if previous_version != body['expected_version']:
            raise ReportError('version_conflict_reload')
        findings = c.execute('SELECT finding_id FROM report_findings WHERE report_id=%s ORDER BY finding_id',
                             (ident,)).fetchall()
        version = previous_version + 1
        c.execute('''
            INSERT INTO report_map_entries(report_id,primary_finding_id,finding_ids,version,intersection,
                public_description,latitude,longitude,published,reviewer)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(report_id) DO UPDATE SET primary_finding_id=EXCLUDED.primary_finding_id,
                finding_ids=EXCLUDED.finding_ids,version=EXCLUDED.version,intersection=EXCLUDED.intersection,
                public_description=EXCLUDED.public_description,latitude=EXCLUDED.latitude,
                longitude=EXCLUDED.longitude,published=EXCLUDED.published,reviewer=EXCLUDED.reviewer,updated_at=now()
        ''', (ident,report['primary_finding_id'],[row['finding_id'] for row in findings],version,title,
              description,body['latitude'],body['longitude'],body['published'],reviewer))
    return {'version':version}


def build_map(rows, polygons):
    west, south, east, north = CALI_EXTENT
    if polygons:
        points = [xy for p in polygons for ring in p for xy in ring]
        west, south = min(x for x,_ in points), min(y for _,y in points)
        east, north = max(x for x,_ in points), max(y for _,y in points)
    ratio = math.cos(math.radians((south + north) / 2))
    scale = min((WIDTH-2*PAD)/(east-west)/ratio, (HEIGHT-2*PAD)/(north-south))
    mid_x, mid_y = (west+east)/2, (south+north)/2

    def project(x, y):
        return [round(WIDTH/2+(x-mid_x)*scale*ratio,2),round(HEIGHT/2-(y-mid_y)*scale,2)]

    grid = []
    for i in range(1,5):
        x, y = west+(east-west)*i/5, south+(north-south)*i/5
        grid += [{'from': project(x,south),'to':project(x,north),'label':f'{x:.3f}°','vertical':True},
                 {'from': project(west,y),'to':project(east,y),'label':f'{y:.3f}°','vertical':False}]
    markers = []
    for row in rows:
        lat, lon = row['latitude'], row['longitude']
        if lat is None:
            row['map_state']='sin_ubicacion'
            continue
        is_inside = inside_city(polygons,lon,lat)
        if is_inside is False or not (west<=lon<=east and south<=lat<=north):
            row['map_state']='fuera_del_mapa'
            if row.pop('_public',False):
                row['latitude']=row['longitude']=None
            continue
        row['map_state']='en_mapa' if is_inside else 'sin_perimetro_verificado'
        x,y = project(lon,lat)
        markers.append({'code':row['code'],'x':x,'y':y,
                        'verified':bool(is_inside)})
    for row in rows:
        row.pop('_public',None)
    return {'width':WIDTH,'height':HEIGHT,'grid':grid,
            'polygons':[[[project(x,y) for x,y in ring] for ring in polygon] for polygon in polygons],
            'markers':markers}


REPORTS_QUERY = '''
SELECT r.id,r.conversation_id,r.primary_finding_id,l.version AS map_version,l.intersection,l.public_description,l.latitude,l.longitude,l.published,
       l.primary_finding_id=r.primary_finding_id AND l.finding_ids=ARRAY(
           SELECT finding_id FROM report_findings WHERE report_id=r.id ORDER BY finding_id
       ) AS location_current
FROM reports r LEFT JOIN report_map_entries l ON l.report_id=r.id
WHERE r.revision<>'descartado'
'''


def snapshot(store, root, *, public=False, evidence_code=None, team=False, export=False):
    listing=public or team
    polygons, boundary_version = ([], None) if team else boundary(root)
    items = []
    public_conversations = set()
    with store.connect() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        cutoff=c.execute('SELECT now() AS cutoff').fetchone()['cutoff']
        published_ids = []
        condition = ' AND l.published' if public else ''
        for location in c.execute(REPORTS_QUERY+condition+' ORDER BY r.code DESC').fetchall():
            current = location['location_current']
            if public and not current:
                continue
            report = detail(c,location['id'])
            # Draft/coincidental GPS from a source stays in the private review form.
            lat, lon = (location['latitude'], location['longitude']) if current else (None,None)
            if public and not polygons:
                lat=lon=None
            findings = report['findings']
            title = (location['intersection'] if current else None) or next((
                next((p['interpretation'] for p in reversed(f['predictions']) if p['interpretation']),
                     f['display_literal']) for f in findings if f['variable']=='ubicacion'),None)
            if public:
                description=location['public_description']
            else:
                damages=list(dict.fromkeys(f['display_literal'] for f in findings if f['variable']=='descripcion_dano'))
                description=report['summary'] or '\n'.join(damages) or None
            data={'code':report['code_display'],'date':report['report_date'],'intersection':title,
                  'description':description,'revision':report['revision_effective'],
                  'processing':report['processing_state'],'latitude':lat,'longitude':lon}
            if team:
                features=source_features({'text':'\n'.join(f['literal'] or '' for f in findings)},set())
                description=situation_text(title,features['topics'],features['fault_types'],features['durations'],
                    found_fault=any(f['variable']=='descripcion_dano' for f in findings))
                data.update(description=description,situacion_presentada=description)
                if export:
                    data.update(id=report['id'],version=report['version'],map_version=location['map_version'] or 0)
            if listing:
                data.update(_public=True,_conversation_id=location['conversation_id'],
                            _report_evidence_ids=[e['id'] for e in report['evidence']])
                published_ids.append(location['id'])
                public_conversations.add(location['conversation_id'])
            else:
                data.update(id=report['id'],version=report['version'],map_version=location['map_version'] or 0,
                    location_stale=bool(location['map_version'] and not current),
                    public_description=location['public_description'] if current else None,
                    published=bool(current and location['published']),
                    coordinates_candidates=[{'latitude':x['latitude'],'longitude':x['longitude']}
                        for f in findings if f['variable']=='ubicacion' for x in gps_coordinates(f['literal'])],
                    evidence=[{'id':e['id'],'modality':e['modality'],'name':e['original_name']} for e in report['evidence']])
            items.append(data)
        if listing:
            blocked = {row['source_id'] for row in c.execute('''
                SELECT CASE WHEN f.origin='chat' THEN f.message_id ELSE f.evidence_id END AS source_id
                FROM reports r JOIN report_findings rf ON rf.report_id=r.id JOIN findings f ON f.id=rf.finding_id
                WHERE r.revision='descartado' OR r.id=ANY(%s::uuid[])
            ''',(published_ids,))}
            projected, conversations = automatic_items(c,blocked,points_allowed=bool(polygons))
            if team:
                for row in projected:
                    row['description']=row['situacion_presentada']
            items.extend(projected)
            public_conversations.update(conversations)
            evidence = attach_evidence(c,items,evidence_code,detail=team,export=export)
            if evidence_code is not None:
                return evidence

    def intersection_key(row):
        title=row['intersection']
        if title and (not row.get('preliminary') or CROSSING.fullmatch(title)):
            return crossing_key(title)
        return None

    if listing:
        items.sort(key=lambda row: (intersection_key(row) is not None,
                                    row['date'] is not None,row['date'],row['code']), reverse=True)
    keys=[intersection_key(row) for row in items]
    totals=Counter(key for key in keys if key is not None)
    for row,key in zip(items,keys):
        row['reports_at_intersection']=totals[key] if key else None
    chart=None if team else build_map(items,polygons)
    response={'cutoff':cutoff,'items':items,'map':chart,'boundary_version':boundary_version}
    if public and not team:
        for item in items:
            item.pop('situacion_presentada',None)
    if listing:
        response['conversations_included']=len(public_conversations)
        response['totals']={'records':len(items),'crossings':len(totals),'photos':evidence.get('image',0),
                            'videos':evidence.get('video',0),'audios':evidence.get('audio',0)+evidence.get('audio_video',0),
                            'whatsapp_audios':evidence.get('audio',0),'video_audios':evidence.get('audio_video',0)}
    return response
