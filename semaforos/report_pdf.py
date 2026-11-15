"""Versioned PDF cuts and expiring evidence links."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta
from html import escape
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from .files import contained
from .report_map import snapshot
from .reports import ReportError

BOGOTA = ZoneInfo('America/Bogota')
SCHEMA_VERSION = 1
LINK_DAYS = 7
LOGO = Path(__file__).with_name('assets') / 'logo-esteban.png'


def formatted_date(value):
    return value.astimezone(BOGOTA).strftime('%d/%m/%Y %H:%M:%S COT') if value else 'Sin fecha de mensaje'


def signature(key, export_id, evidence_id, expires_at):
    value = f'report-evidence|{export_id}|{evidence_id}|{int(expires_at.timestamp())}'
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def access_evidence(store, export_id, evidence_id, key, provided):
    with store.connect() as c:
        row = c.execute('''
            SELECT e.storage_path, e.original_name, x.evidence_expires_at
            FROM report_pdf_exports x JOIN evidence e ON e.id=ANY(x.evidence_ids)
            WHERE x.id=%s AND e.id=%s AND x.evidence_expires_at > now()
        ''', (export_id,evidence_id)).fetchone()
    if not row or not hmac.compare_digest(signature(key,export_id,evidence_id,row['evidence_expires_at']),provided):
        raise ReportError('evidence_link_unavailable')
    return row


def draw_map(chart, attributed):
    from reportlab.graphics.shapes import Circle, Drawing, Line, Path as ShapePath, Rect, String
    from reportlab.lib.colors import HexColor, white

    width,height=chart['width'],chart['height']
    drawing=Drawing(width,height)
    drawing.add(Rect(0,0,width,height,fillColor=HexColor('#f3f8f6'),strokeColor=HexColor('#cbd9d2')))
    grid=[]
    for line in chart['grid']:
        (x1,y1),(x2,y2)=line['from'],line['to']
        grid.append(Line(x1,height-y1,x2,height-y2,strokeColor=HexColor('#bdcec7'),strokeWidth=.6))
        x,y=(x1,height-y1-13) if line['vertical'] else (x1-30,height-y1-2)
        grid.append(String(x,y,line['label'],fontName='ReportSans',fontSize=8,fillColor=HexColor('#47645a')))
    for polygon in chart['polygons']:
        path=ShapePath(fillColor=HexColor('#dbece2'),strokeColor=HexColor('#5e8070'),strokeWidth=1.2,fillMode=0)
        for ring in polygon:
            path.moveTo(ring[0][0],height-ring[0][1])
            for x,y in ring[1:]:
                path.lineTo(x,height-y)
            path.closePath()
        drawing.add(path)
    for line in grid:
        drawing.add(line)
    points={}
    for marker in chart['markers']:
        position=(marker['x'],height-marker['y'])
        points[position]=points.get(position,0)+1
    for (x,y),count in points.items():
        drawing.add(Circle(x,y,6 if count>1 else 4,fillColor=HexColor('#ac2835'),strokeColor=white,strokeWidth=1))
        if count>1:
            drawing.add(String(x,y-2.5,str(count),fontName='ReportSans',fontSize=6,textAnchor='middle',fillColor=white))
    north=HexColor('#14382d')
    drawing.add(String(14,height-18,'N',fontName='ReportSans',fontSize=9,fillColor=north))
    for x1,y1,x2,y2 in [(27,height-19,27,height-11),(24,height-14,27,height-11),(30,height-14,27,height-11)]:
        drawing.add(Line(x1,y1,x2,y2,strokeColor=north,strokeWidth=.8))
    drawing.add(String(14,14,'Fuente: IDESC · Perímetro urbano' if attributed else 'Cuadrícula de referencia · sin perímetro oficial cargado',
                       fontName='ReportSans',fontSize=8,fillColor=HexColor('#47645a')))
    drawing.scale(.7,.7)
    drawing.width*=.7
    drawing.height*=.7
    return drawing


def render_pdf(data, export_id, generated, link_for=None, expires_at=None):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    fonts=Path(reportlab.__file__).with_name('fonts')
    pdfmetrics.registerFont(TTFont('ReportSans',str(fonts/'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('ReportSansBold',str(fonts/'VeraBd.ttf')))
    styles={
        'title':ParagraphStyle('ReportTitle',fontName='ReportSansBold',fontSize=25,leading=28,textColor=colors.HexColor('#14382d')),
        'subtitle':ParagraphStyle('ReportSubtitle',fontName='ReportSansBold',fontSize=13,leading=17,textColor=colors.HexColor('#14382d')),
        'body':ParagraphStyle('ReportBody',fontName='ReportSans',fontSize=9.5,leading=13,alignment=TA_LEFT,splitLongWords=True),
        'small':ParagraphStyle('ReportNote',fontName='ReportSans',fontSize=8,leading=11,textColor=colors.HexColor('#425d53'),splitLongWords=True),
    }

    def paragraph(value,style='body'):
        return Paragraph(escape(str(value)).replace('\n','<br/>'),styles[style])

    def footer(page,doc):
        page.setFont('ReportSans',8)
        page.setFillColor(colors.HexColor('#425d53'))
        page.drawString(48,30,f'Semáforos Cali  ·  {export_id}')
        page.drawRightString(564,30,f'Página {doc.page}')

    logo=Image(str(LOGO),width=84,height=34,kind='proportional')
    header=Table([[paragraph('Informe general de reportes','title'),logo]],colWidths=(402,102))
    header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0)]))
    story=[header,Spacer(0,10),paragraph('Semáforos Cali · Registro ciudadano','subtitle'),
           paragraph(f'Generado: {formatted_date(generated)} | Corte: {formatted_date(data["cutoff"])}','small'),
           paragraph(f'{len(data["items"])} reportes · {len(data["map"]["markers"])} ubicados en el mapa','body'),
           Spacer(0,13),draw_map(data['map'],bool(data['boundary_version'])),Spacer(0,12),
           paragraph('Registros y evidencias','subtitle'),
           paragraph('Cada fila conserva el reporte ciudadano y su estado al corte. Los registros descartados se excluyen.','small')]
    if expires_at:
        story.append(paragraph('Los enlaces a evidencias vencen el '+formatted_date(expires_at)+'.','small'))
    if not data['items']:
        story.append(paragraph('Aún no hay reportes consolidados para incluir.'))
    for row in data['items']:
        crossing=row['intersection'] or 'Intersección pendiente'
        count=row['reports_at_intersection']
        title=f'{row["code"]} · {crossing}'
        description=row['description'] or 'Descripción pendiente de consolidación.'
        intro=paragraph(f'{formatted_date(row["date"])} · Revisión: {row["revision"]} · Procesamiento: '
                        f'{row["processing"].replace("_"," ")}' + (f' · {count} reportes en este cruce' if count else ''),'small')
        story.append(KeepTogether([Spacer(0,9),paragraph(title,'subtitle'),intro]))
        story.append(paragraph(description))
        if row['evidence']:
            links=[]
            for index, evidence in enumerate(row['evidence'],1):
                label=escape(f'{index}. {evidence["modality"]} · {evidence["name"]}')
                if link_for:
                    label=f'<a href="{escape(link_for(evidence["id"]),quote=True)}" color="#204C8A">{label}</a>'
                links.append(Paragraph(label,styles['small']))
            story.extend(links)
    buffer=BytesIO()
    document=SimpleDocTemplate(buffer,pagesize=letter,leftMargin=48,rightMargin=48,topMargin=46,bottomMargin=47,
                               title='Informe general - Semáforos Cali',author='Esteban Oliveros Montoya')
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()


def make_export(store, root, key, include_links, origin=None):
    if include_links:
        base=urlsplit(origin or '')
        if base.scheme!='https' or not base.netloc or base.username or base.password or base.path not in ('','/') or base.query or base.fragment:
            raise ReportError('https_report_origin_required')
        origin=f'{base.scheme}://{base.netloc}'
    data=snapshot(store,root)
    ident=uuid4()
    generated=datetime.now(BOGOTA)
    expires_at=generated+timedelta(days=LINK_DAYS) if include_links else None

    def evidence_url(evidence_id):
        return f'{origin}/informe/evidencia/{ident}/{evidence_id}?firma={signature(key,ident,evidence_id,expires_at)}'

    pdf=render_pdf(data,ident,generated,evidence_url if include_links else None,expires_at)
    relative=f'informes/{ident}.pdf'
    destination=contained(root,relative)
    destination.parent.mkdir(parents=True,exist_ok=True)
    tmp=None
    try:
        with NamedTemporaryFile(dir=destination.parent,delete=False) as f:
            tmp=Path(f.name)
            f.write(pdf)
        os.replace(tmp,destination)
        with store.connect() as c:
            c.execute('INSERT INTO report_pdf_exports VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',(
                ident,generated,data['cutoff'],SCHEMA_VERSION,relative,hashlib.sha256(pdf).hexdigest(),
                Jsonb([{'id':str(r['id']),'version':r['version'],'map_version':r['map_version']} for r in data['items']]),
                sorted({e['id'] for row in data['items'] for e in row['evidence']}) if include_links else [],
                expires_at,data['boundary_version']))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return ident,destination
