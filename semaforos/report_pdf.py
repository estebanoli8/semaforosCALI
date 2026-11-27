"""Versioned PDF cuts and signed evidence links without expiration."""
import hashlib
import hmac
import os
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .files import contained
from .report_map import snapshot
from .reports import ReportError

BOGOTA = ZoneInfo('America/Bogota')
SCHEMA_VERSION = 1
MONTHS = 'ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC'.split()
LOGO = Path(__file__).with_name('assets') / 'logo-esteban.png'
FONT_DIR = Path(reportlab.__file__).with_name('fonts')
pdfmetrics.registerFont(TTFont('ReportSans',str(FONT_DIR/'Vera.ttf')))
pdfmetrics.registerFont(TTFont('ReportSansBold',str(FONT_DIR/'VeraBd.ttf')))


def formatted_date(value):
    return value.astimezone(BOGOTA).strftime('%d/%m/%Y %H:%M:%S COT') if value else 'Sin fecha de mensaje'


def export_filename(generated):
    local=generated.astimezone(BOGOTA)
    return f'Accion Popular Semaforos Cali {MONTHS[local.month-1]} {local:%d %Y %H-%M-%S}.pdf'


def signature(key, export_id, evidence_id, expires_at):
    # Preserve the timestamp in legacy signatures so existing PDFs still work.
    stamp = int(expires_at.timestamp()) if expires_at is not None else 0
    value = f'report-evidence|{export_id}|{evidence_id}|{stamp}'
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def report_origin(request):
    configured=os.getenv('SC_REPORT_ORIGIN')
    if configured:
        return configured
    if request.url.scheme=='http' and request.headers.get('sec-fetch-site') in (None,'same-origin'):
        try:
            origin=urlsplit(request.headers.get('origin',''))
            if origin.scheme=='https' and origin.netloc==request.url.netloc:
                return origin.geturl()
        except ValueError:
            pass
    return str(request.base_url)


def conversation_signature(key,export_id,conversation_id,expires_at):
    stamp=int(expires_at.timestamp()) if expires_at is not None else 0
    value=f'report-conversation|{export_id}|{conversation_id}|{stamp}'
    return hmac.new(key.encode(),value.encode(),hashlib.sha256).hexdigest()


def access_conversation(store,export_id,conversation_id,key,provided):
    with store.connect() as db:
        row=db.execute("""
            SELECT version->>'label' AS label,version->>'date_range' AS date_range,
                   x.evidence_expires_at AS expires_at,
                   ARRAY(SELECT jsonb_array_elements_text(version->'evidence_ids')::uuid) AS ids
            FROM report_pdf_exports x CROSS JOIN LATERAL jsonb_array_elements(x.report_versions) version
            WHERE x.id=%s AND version->>'conversation_id'=%s
        """,(export_id,str(conversation_id))).fetchone()
    if not row or not hmac.compare_digest(conversation_signature(key,export_id,conversation_id,row['expires_at']),provided):
        raise ReportError('evidence_link_unavailable')
    return row

def access_evidence(store, export_id, evidence_id, key, provided):
    with store.connect() as c:
        row = c.execute('''
            SELECT e.id,e.storage_path,e.original_name,e.modality,e.sha256,x.evidence_expires_at
            FROM report_pdf_exports x JOIN evidence e ON e.id=ANY(x.evidence_ids)
            WHERE x.id=%s AND e.id=%s
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
    drawing.add(String(14,14,'Perímetro urbano: Planeación / IDESC · CC BY-SA 4.0' if attributed else 'Cuadrícula de referencia · sin perímetro oficial cargado',
                       fontName='ReportSans',fontSize=8,fillColor=HexColor('#47645a')))
    drawing.scale(.7,.7)
    drawing.width*=.7
    drawing.height*=.7
    return drawing


def render_pdf(data, export_id, generated, link_for=None, expires_at=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
    map_data=data['map']
    summary=f'{len(data["items"])} reportes'
    if map_data is not None:
        summary+=f' · {len(map_data["markers"])} ubicados en el mapa'
    story=[header,Spacer(0,10),paragraph('Semáforos Cali · Registro ciudadano','subtitle'),
           paragraph(f'Generado: {formatted_date(generated)} | Corte: {formatted_date(data["cutoff"])}','small'),
           paragraph(summary)]
    if map_data is not None:
        story.extend([Spacer(0,13),draw_map(map_data,bool(data['boundary_version']))])
    story.extend([Spacer(0,12),paragraph('Registros y evidencias','subtitle'),
        paragraph('Cada fila conserva el reporte ciudadano y su estado al corte. Los registros descartados se excluyen.','small')])
    if link_for:
        story.append(paragraph('Enlaces a evidencias sin fecha de caducidad.','small'))
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


def render_detailed(data, generated, link_for, expires_at):
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
    from .text_fields import WEB_SUBTITLE, WEB_TITLE

    regular=ParagraphStyle('DetailRegular',fontName='ReportSans',fontSize=9,leading=13)
    bold=ParagraphStyle('DetailHeading',parent=regular,fontName='ReportSansBold',fontSize=11,leading=14,
                        textColor=HexColor('#215b46'))
    crossing=ParagraphStyle('DetailCrossing',parent=regular,fontName='ReportSansBold')
    small=ParagraphStyle('DetailSmall',parent=regular,fontSize=8,leading=11)
    date=ParagraphStyle('DetailDate',parent=small,textColor=HexColor('#475851'))

    def paragraph(text, style=regular):
        return Paragraph(escape(text).replace('\n','<br/>'),style)

    def page_header(page,doc):
        page.drawImage(str(LOGO),476,735,84,32,preserveAspectRatio=True,anchor='c',mask='auto')
        page.setFont('ReportSansBold',11)
        page.drawString(46,756,WEB_TITLE)
        page.setFont('ReportSans',7)
        page.drawString(46,743,WEB_SUBTITLE)
        page.drawString(46,730,'Generado '+formatted_date(generated))
        page.line(46,725,568,725)
        page.drawRightString(568,30,f'Página {doc.page}')

    story=[paragraph(f'{len(data["items"])} conversaciones · Corte {formatted_date(data["cutoff"])}',small)]
    if data.get('experiment'):
        story.append(paragraph('Lote '+data['experiment'],small))
    if link_for:
        story.append(paragraph('Enlaces a evidencias sin fecha de caducidad.',small))
    groups={}
    for row in data['items']:
        groups.setdefault(row['reporter_key'],[]).append(row)

    for rows in groups.values():
        cells=[[paragraph(rows[0]['archive_label'],bold),'','']]
        for row in rows:
            url=escape(link_for(row['id']),quote=True) if link_for else None
            for episode in row['episodes']:
                link=Paragraph(f'<a href="{url}" color="#204C8A">Ver evidencias</a>',small) if url else ''
                cells.append([paragraph(episode['location'] or 'Ubicación sin identificar',crossing),
                              paragraph(row['date_range'],date),link])
        table=Table(cells,colWidths=[254,158,98],repeatRows=1,splitInRow=1,hAlign='LEFT',spaceBefore=10)
        table.setStyle(TableStyle([
            ('SPAN',(0,0),(-1,0)),
            ('BACKGROUND',(0,0),(-1,0),HexColor('#eaf2ed')),
            ('LINEBELOW',(0,1),(-1,-1),0.4,HexColor('#dce5e0')),
            ('TOPPADDING',(0,0),(-1,-1),6),
            ('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('VALIGN',(0,0),(-1,-1),'TOP'),
        ]))
        story.append(table)
    buffer=BytesIO()
    document=SimpleDocTemplate(buffer,pagesize=letter,leftMargin=46,rightMargin=44,topMargin=76,bottomMargin=44,
                               title=WEB_TITLE,author='Esteban Oliveros Montoya')
    document.build(story,onFirstPage=page_header,onLaterPages=page_header)
    return buffer.getvalue()


def make_export(store, root, key, include_links, origin=None, *, action_report=False, detailed_report=False,
                experiment=None):
    include_links=include_links or detailed_report
    if include_links:
        try:
            base=urlsplit(origin or '')
        except ValueError as exc:
            raise ReportError('https_report_origin_required') from exc
        if base.scheme!='https' or not base.netloc or base.username or base.password or base.path not in ('','/') or base.query or base.fragment:
            raise ReportError('https_report_origin_required')
        origin=f'{base.scheme}://{base.netloc}'
    if detailed_report:
        from .detailed import snapshot as details
        data=details(store,experiment=experiment)
    else:
        data=snapshot(store,root,team=action_report,export=action_report)
    ident=uuid4()
    generated=datetime.now(BOGOTA)
    expires_at=None

    def evidence_url(evidence_id):
        return f'{origin}/informe/evidencia/{ident}/{evidence_id}?firma={signature(key,ident,evidence_id,expires_at)}'

    def conversation_url(conversation_id):
        proof=conversation_signature(key,ident,conversation_id,expires_at)
        return f'{origin}/informe/conversaciones/{ident}/{conversation_id}?firma={proof}'

    link_for=evidence_url if include_links else None
    pdf=(render_detailed(data,generated,conversation_url,expires_at) if detailed_report
         else render_pdf(data,ident,generated,link_for,expires_at))
    versions=([{'conversation_id':str(r['id']),'label':r['archive_label'],'date_range':r['date_range'],
                'evidence_ids':[str(e['id']) for e in r['evidence']]}
               for r in data['items']] if detailed_report else
              [{'id':str(r['id']),'version':r['version'],'map_version':r['map_version']} if 'id' in r else
               {'code':r['code'],'date':r['date'].isoformat() if r['date'] else None,
                'intersection':r['intersection'],'description':r['description']} for r in data['items']])
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
            c.execute('''INSERT INTO report_pdf_exports(
                id,generated_at,cutoff,schema_version,storage_path,sha256,report_versions,
                evidence_ids,evidence_expires_at,boundary_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(
                ident,generated,data['cutoff'],SCHEMA_VERSION,relative,hashlib.sha256(pdf).hexdigest(),
                Jsonb(versions),
                sorted({e['id'] for row in data['items'] for e in row['evidence']}) if include_links else [],
                expires_at,data.get('boundary_version')))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return ident,destination,generated
