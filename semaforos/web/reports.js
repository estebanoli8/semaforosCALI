'use strict';

const byId = id => document.getElementById(id);
const team = location.pathname === '/reportes';
const pageSize = 20;
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
    const label=group.map(marker=>marker.code).join(', ');
    const pin=svg('circle',{cx:x,cy:y,r:group.length>1?8:5,class:'map-pin',tabindex:0,role:'button','aria-label':label});
    pin.append(svg('title',{},label));
    const choose=()=>{
      const codes=new Set(group.map(marker=>marker.code));
      const rows=data.items.filter(row=>codes.has(row.code));
      byId('mapSelection').textContent=rows.map(row=>row.code+' · '+row.intersection).join(' | ');
      if(team && rows.length===1) edit(rows[0]);
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

function renderRows() {
  if(!view) return;
  const rows=byId('reportRows');
  rows.replaceChildren();
  const query=byId('reportSearch').value.trim().toLocaleLowerCase('es-CO');
  const matching=view.items.filter(row=>(row.code+' '+(row.intersection||'')).toLocaleLowerCase('es-CO').includes(query));
  const end = Math.min(matching.length,(page+1)*pageSize);
  for(const row of matching.slice(page*pageSize,end)) {
    const tr=node('tr');
    const code=node('td');
    if(team) {
      const button=node('button',row.code);
      button.type='button';button.className='secondary';button.onclick=()=>edit(row);code.append(button);
    } else code.textContent=row.code;
    tr.append(code);
    for(const label of [formatDate(row.date),row.intersection||'Por revisar',row.description||'Por consolidar',
      [row.preliminary?'Preliminar · sin revisión humana':states[row.revision],states[row.processing]]
        .filter(Boolean).join(' · '),row.reports_at_intersection??'—']) {
      tr.append(node('td',label));
    }
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
  renderRows();
}
async function load() {
  request?.abort();
  const current=new AbortController();
  request=current;
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
  byId('reportEvidence').replaceChildren();
  for(const evidence of row.evidence) {
    const item=node('li');
    const button=node('button','Descargar '+evidence.modality);
    button.className='secondary';
    button.onclick=async()=>{
      try {
        const response=await get('/evidence/'+evidence.id+'/download');
        download(await response.blob(),evidence.name.split(/[\\/]/).pop());
      } catch(error) {byId('editStatus').textContent=error.message;}
    };
    item.append(button,node('span',evidence.name));
    byId('reportEvidence').append(item);
  }
  byId('editPanel').scrollIntoView({block:'start'});
}
function logout() {
  request?.abort();request=null;accessKey='';view=null;selected=null;
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
byId('teamLinks').hidden=!team;
byId('reportRefresh').onclick=load;
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
