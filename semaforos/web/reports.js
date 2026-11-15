'use strict';

const byId = id => document.getElementById(id);
const team = location.pathname === '/reportes';
const pageSize = 20;
const params = new URLSearchParams(location.search);
const selectedRecord = team ? params.get('registro') : null;
const selectedType = params.get('tipo');
const evidenceTypes = {
  audio:['audio de WhatsApp','audios de WhatsApp'],
  audio_video:['audio extraído de video','audios extraídos de video'],
  image:['foto','fotos'],
  video:['video original','videos originales'],
  chat:['chat TXT','chats TXT'],
  frame:['fotograma','fotogramas'],
  other:['otro archivo','otros archivos']
};

const dateTime = new Intl.DateTimeFormat('es-CO', {dateStyle:'medium',timeStyle:'short',timeZone:'America/Bogota'});
const states = {pendiente:'Revisión pendiente',revisado:'Revisado',completado:'Procesamiento completo',
  en_cola:'En cola',procesando:'Procesando',parcial_con_errores:'Procesamiento parcial'};
let accessKey = '';
let view = null;
let selected = null;
let request = null;
let page = 0;

function node(tag, text) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  return result;
}
function svg(tag, attrs, label) {
  const result = document.createElementNS('http://www.w3.org/2000/svg',tag);
  for (const [key,value] of Object.entries(attrs)) result.setAttribute(key,value);
  if (label) result.textContent = label;
  return result;
}
function formatDate(value) {
  return value ? dateTime.format(new Date(value)) : 'Sin fecha disponible';
}
async function get(path, options = {}) {
  const headers = new Headers(options.headers);
  if (team) headers.set('Authorization', 'Bearer ' + accessKey);
  const response = await fetch(path, {...options, headers, cache:'no-store'});
  if (response.status === 401) {
    logout();
    throw Error('La clave no es válida. Vuelve a ingresarla.');
  }
  if (response.status === 409) throw Error('El reporte cambió o faltan datos. Revisa el formulario y actualiza el corte.');
  if (!response.ok) throw Error('No se pudo completar la solicitud.');
  return response;
}

function drawMap(data) {
  const map=data.map;
  const chart=svg('svg',{viewBox:`0 0 ${map.width} ${map.height}`,'aria-label':'Mapa geográfico de los reportes ubicados',role:'group'});
  for (const polygon of map.polygons) {
    const d=polygon.map(ring=>'M '+ring.map(point=>point.join(' ')).join(' L ')+' Z').join(' ');
    chart.append(svg('path',{d,class:'map-city'}));
  }
  for (const line of map.grid) {
    const [x1,y1]=line.from,[x2,y2]=line.to;
    chart.append(svg('line',{x1,y1,x2,y2,class:'map-grid'}),
      svg('text',{x:line.vertical?x1:x1-33,y:line.vertical?y1+15:y1-2,class:'map-grid-label'},line.label));
  }
  chart.append(svg('text',{x:16,y:21,class:'map-grid-label'},'N ↑'));
  const groups=new Map();
  for(const marker of map.markers) {
    const key=marker.x+':'+marker.y;
    if(!groups.has(key)) groups.set(key,[]);
    groups.get(key).push(marker);
  }
  for(const group of groups.values()) {
    const {x,y} = group[0];
    const codes=new Set(group.map(marker=>marker.code));
    const found=data.items.filter(row=>codes.has(row.code));
    const crossings=[...new Set(found.map(row=>row.intersection).filter(Boolean))].join(', ');
    const label=team?[...codes].join(', '):(crossings||'Cruce ubicado')+' · '+group.length+' registros';
    const pin=svg('circle',{cx:x,cy:y,r:group.length>1?8:5,class:'map-pin',tabindex:0,role:'button','aria-label':label});
    pin.append(svg('title',{},label));
    const choose=()=>{
      byId('mapSelection').textContent=team?found.map(row=>row.code+' · '+row.intersection).join(' | '):label;
      if(team && found.length===1) edit(found[0]);
    };
    pin.onclick=choose;
    pin.onkeydown=event=>{
      if(event.key==='Enter'||event.key===' '){event.preventDefault();choose();}
    };
    chart.append(pin);
    if(group.length>1) chart.append(svg('text',{x,y,class:'map-count'},String(group.length)));
  }
  byId('reportMap').replaceChildren(chart);
  byId('mapLegend').textContent=(data.boundary_version
    ? 'Perímetro urbano de Cali · Planeación / IDESC · CC BY-SA 4.0.'
    : 'Cuadrícula de referencia. Falta cargar el perímetro urbano oficial.')
    + (map.markers.length ? ' Cada punto rojo ubica uno o más reportes.' : ' Aún no hay puntos para mostrar.');
}

function catalog(row) {
  const cell=node('td');
  cell.className='report-catalog';
  const counts=row.evidence_counts||{};
  const groups=Object.entries(evidenceTypes).filter(([key])=>counts[key]>0);
  if(!groups.length) { cell.textContent='Sin archivos vinculados'; return cell; }
  const details=node('details');
  const total=groups.reduce((sum,[key])=>sum+counts[key],0);
  details.append(node('summary',total+(total===1?' archivo':' archivos')));
  details.append(node('small',row.evidence_scope==='conversacion'?'De la conversación':'Vinculados al registro'));
  const list=node('ul');
  for(const [key,labels] of groups) {
    const entry=node('li');
    const count=counts[key];
    const link=node('a',count+' '+labels[count===1?0:1]);
    link.href='/reportes?'+new URLSearchParams({registro:row.code,tipo:key});
    link.target='_blank';link.rel='noopener noreferrer';link.title='Abrir con la clave del equipo';
    entry.append(link);list.append(entry);
  }
  details.append(list);cell.append(details);
  return cell;
}

function renderRows() {
  if(!view) return;
  const rows=byId('reportRows');
  rows.replaceChildren();
  const query=byId('reportSearch').value.trim().toLocaleLowerCase('es-CO');
  const matching=view.items.filter(row=>((team?row.code+' ':'')+(row.intersection||'')).toLocaleLowerCase('es-CO').includes(query));
  const end = Math.min(matching.length,(page+1)*pageSize);
  for(const row of matching.slice(page*pageSize,end)) {
    const tr=node('tr');
    if(team) {
      const code=node('td');
      const button=node('button',row.code);
      button.type='button';button.className='secondary';button.onclick=()=>edit(row);
      code.append(button);tr.append(code);
    }
    const description=node('td',row.description||'Por consolidar');
    description.className='report-description';
    tr.append(node('td',formatDate(row.date)),node('td',row.intersection||'Por revisar'),description);
    if(team) tr.append(node('td',[states[row.revision],states[row.processing]].filter(Boolean).join(' · ')));
    tr.append(node('td',row.reports_at_intersection??'—'));
    if(!team) tr.append(catalog(row));
    rows.append(tr);
  }
  byId('reportEmpty').textContent=matching.length?'':'Aún no hay reportes para mostrar con esta selección.';
  byId('reportPageInfo').textContent=matching.length?`${page*pageSize+1}–${end} de ${matching.length}`:'0';
  byId('prevReport').disabled=page===0;
  byId('nextReport').disabled=end>=matching.length;
}

function render() {
  const stats=byId('reportStats');
  stats.replaceChildren();
  const latest = view.items.reduce((date,row)=>row.date && (!date || new Date(row.date)>new Date(date))?row.date:date,null);
  const statsItems = [[team?'Reportes del corte':'Registros del corte',view.items.length],
    [team?'Reportes ubicados':'Registros ubicados',view.map.markers.length],['Último registro',formatDate(latest)]];
  if(!team) statsItems.unshift(['Conversaciones incluidas',view.conversations_included??0]);
  for(const [label,count] of statsItems) {
    const card=node('article');
    card.append(node('span',label),node('strong',count));stats.append(card);
  }
  byId('mapSelection').textContent='';
  drawMap(view);
  if(team || view.map.markers.length) byId('recordsPanel').before(byId('mapPanel'));
  else byId('recordsPanel').after(byId('mapPanel'));
  renderRows();
}
async function loadEvidence(signal) {
  byId('reportStatus').textContent='Consultando evidencias…';
  try {
    const response=await get('/public-records/'+encodeURIComponent(selectedRecord)+'/evidence',{signal});
    const data=await response.json();
    if(signal.aborted)return;
    const label=evidenceTypes[selectedType]?.[1];
    const items=label?data.items.filter(item=>item.type===selectedType):data.items;
    byId('evidenceTitle').textContent=label?'Evidencias · '+label:'Evidencias';
    byId('evidenceScope').textContent=data.scope==='conversacion'?'Archivos de la conversación':'Archivos vinculados al registro';
    const list=byId('evidenceFiles');
    list.replaceChildren(...items.map(fileItem));
    if(!items.length)list.append(node('li','No hay archivos de este tipo en el corte actual.'));
    byId('reportLogin').hidden=true;
    byId('evidenceAccess').hidden=false;
    byId('reportStatus').textContent='';
  } catch(error) {
    if(error.name!=='AbortError')byId('reportStatus').textContent=error.message;
  }
}

async function load() {
  request?.abort();
  const current=new AbortController();
  request=current;
  if(selectedRecord)return loadEvidence(current.signal);
  byId('reportStatus').textContent='Consultando reportes…';
  try {
    const response=await get(team?'/report-map':'/semaforos/datos',{signal:current.signal});
    const data=await response.json();
    if(request!==current)return;
    view=data;page=0;
    render();
    byId('reportWork').hidden=false;
    byId('pdfPanel').hidden=!team;
    byId('reportLogin').hidden=true;
    byId('reportStatus').textContent='Corte '+formatDate(view.cutoff)+' · hora de Cali';
  } catch(error) {
    if(error.name!=='AbortError')byId('reportStatus').textContent=error.message;
  }
}
function download(blob, name) {
  const url=URL.createObjectURL(blob);
  const anchor=node('a');
  anchor.href=url;anchor.download=name;anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),30000);
}
function fileItem(file) {
  const item=node('li');
  const button=node('button','Descargar');
  button.className='secondary';
  button.onclick=async()=>{
    try {
      const response=await get('/evidence/'+file.id+'/download');
      download(await response.blob(),file.name.split(/[\\/]/).pop());
    } catch(error) { byId('reportStatus').textContent=error.message; }
  };
  item.append(node('span',file.name),button);
  return item;
}
function edit(row) {
  selected=row;
  byId('editPanel').hidden=false;
  byId('editTitle').textContent='Revisar ubicación · '+row.code;
  byId('crossing').value=row.intersection||'';
  byId('latitude').value=row.latitude??'';
  byId('longitude').value=row.longitude??'';
  byId('publicDescription').value=row.public_description||'';
  byId('publishReport').checked=row.published;
  byId('editStatus').textContent=row.location_stale?'Cambiaron las fuentes. Vuelve a verificar esta ubicación.':
    row.map_state==='fuera_del_mapa'?'El punto queda fuera del mapa. Revisa las coordenadas.':'';
  byId('coordinateCandidates').replaceChildren();
  const seen=new Set();
  for(const pair of row.coordinates_candidates) {
    const label=pair.latitude+', '+pair.longitude;
    if(seen.has(label))continue;
    seen.add(label);
    const button=node('button','Usar GPS sugerido · '+label);
    button.type='button';button.className='secondary';
    button.onclick=()=>{byId('latitude').value=pair.latitude;byId('longitude').value=pair.longitude;};
    byId('coordinateCandidates').append(button);
  }
  byId('reportEvidence').replaceChildren(...row.evidence.map(fileItem));
  byId('editPanel').scrollIntoView({block:'start'});
}
function logout() {
  request?.abort();request=null;accessKey='';view=null;selected=null;
  byId('evidenceAccess').hidden=true;byId('evidenceFiles').replaceChildren();
  byId('reportWork').hidden=true;byId('editPanel').hidden=true;byId('reportLogin').hidden=false;
  for(const id of ['reportStats','reportRows','reportMap','reportEvidence','coordinateCandidates'])byId(id).replaceChildren();
  byId('locationForm').reset();
  byId('reportSearch').value='';
  byId('shareEvidence').checked=false;
  for(const id of ['reportStatus','mapSelection','editTitle','editStatus'])byId(id).textContent='';
}
byId('audience').textContent=team?'Acceso privado':'Consulta pública';
byId('reportLogin').hidden=!team;
byId('preliminaryNote').hidden=team;
byId('recordCodeHeader').hidden=!team;
byId('recordStateHeader').hidden=!team;
byId('recordEvidenceHeader').hidden=team;
byId('crossingCountNote').hidden=team;
if(!team) {
  byId('reportIntro').textContent='Consulta los cruces y las evidencias disponibles en los reportes ciudadanos.';
  byId('reportSearch').labels[0].textContent='Buscar por cruce';
  byId('reportSearch').placeholder='Calle o carrera';
}
byId('teamLinks').hidden=!team;
byId('updateRecords').onclick=load;
byId('evidenceLogout').onclick=logout;
byId('reportSearch').oninput=()=>{page=0;renderRows();};
byId('prevReport').onclick=()=>{page--;renderRows();};
byId('nextReport').onclick=()=>{page++;renderRows();};
byId('reportLogout').onclick=logout;
byId('reportLoginForm').onsubmit=event=>{
  event.preventDefault();
  accessKey=byId('reportKey').value;
  byId('reportKey').value='';
  load();
};
byId('locationForm').onsubmit=async event=>{
  event.preventDefault();
  if(!selected)return;
  const ident=selected.id;
  const body={expected_report_version:selected.version,expected_version:selected.map_version,
    intersection:byId('crossing').value,latitude:byId('latitude').value===''?null:byId('latitude').valueAsNumber,
    longitude:byId('longitude').value===''?null:byId('longitude').valueAsNumber,public_description:byId('publicDescription').value,
    reviewer:byId('mapReviewer').value,published:byId('publishReport').checked};
  const status=byId('editStatus');
  try {
    await get('/reports/'+ident+'/map',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    await load();
    const row=view?.items.find(item=>item.id===ident);
    if(row)edit(row);
    status.textContent='Ubicación y visibilidad guardadas. '+status.textContent;
  } catch(error) {status.textContent=error.message;}
};
byId('exportPdf').onclick=async()=>{
  const button=byId('exportPdf');
  button.disabled=true;
  byId('reportStatus').textContent='Generando informe…';
  try {
    const response=await get('/report-exports',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({share_evidence:byId('shareEvidence').checked})});
    const ident=response.headers.get('X-Report-Export-ID');
    download(await response.blob(),'semaforos-cali-'+ident+'.pdf');
    byId('reportStatus').textContent='Informe generado · '+ident;
  } catch(error) {byId('reportStatus').textContent=error.message;}
  finally {button.disabled=false;}
};
if(!team)load();
