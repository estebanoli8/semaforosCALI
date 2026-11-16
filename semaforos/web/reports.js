'use strict';

const byId = id => document.getElementById(id);
const team = location.pathname === '/reportes';
const pageSize = 20;
const params = new URLSearchParams(location.search);
const selectedRecord = team ? params.get('registro') : null;
const selectedConversation = team ? params.get('conversacion') : null;
const selectedEpisode = selectedConversation ? params.get('episodio') : null;
const selectedType = params.get('tipo') === 'audio_video' ? 'video' : params.get('tipo');
const locationEditor = team && params.has('ubicaciones') && !selectedRecord && !selectedConversation;
const detailed = team && !locationEditor;
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
  details.append(node('small',(row.evidence_scope==='conversacion')?'De la conversación':'Vinculados al registro'));
  const list=node('ul');
  for(const [key,labels] of groups) {
    const entry=node('li');
    const count=counts[key];
    const link=evidenceLink(count+' '+labels[count===1?0:1],{registro:row.code,tipo:key});
    link.title='Abrir detalle en una pestaña nueva';
    entry.append(link);list.append(entry);
  }
  details.append(list);cell.append(details);
  return cell;
}

const fieldLabels={dano:'Daño',gestion:'Gestión',peligro:'Peligro',ubicacion:'Ubicación'};
const tagLabels={D:'Tipo de falla',T:'Desde cuándo está dañado',R:'Reincidencia tras reparación',
  G:'Gestión',P:'Peligro',U:'Ubicación'};
const sources={chat:'Chat TXT',audio_whatsapp:'Audio de WhatsApp',audio_video:'Audio de video'};
const localDate = new Intl.DateTimeFormat('es-CO',{month:'long',day:'2-digit',year:'numeric',timeZone:'America/Bogota'});
function dateLabel(value) {
  if(!value)return 'Sin fecha disponible';
  const parts=Object.fromEntries(localDate.formatToParts(new Date(value)).map(p=>[p.type,p.value]));
  return parts.month+' / '+parts.day+' / '+parts.year;
}
function dateRange(from,to) {
  return from?dateLabel(from)+' – '+dateLabel(to):dateLabel(null);
}
function appendFindingLiteral(line, literal, pins) {
  const matches=pins.map(pin=>({pin,index:literal.indexOf(pin.literal)}))
    .filter(({pin,index})=>index>=0 && pin.literal).sort((a,b)=>a.index-b.index);
  let offset=0;
  for(const {pin,index} of matches) {
    if(index<offset || !Number.isFinite(pin.latitude) || !Number.isFinite(pin.longitude) ||
        Math.abs(pin.latitude)>90 || Math.abs(pin.longitude)>180)continue;
    const link=node('a',pin.literal);
    link.href='https://maps.google.com/?q='+pin.latitude+','+pin.longitude;
    link.target='_blank';
    link.rel='noopener noreferrer';
    line.append(document.createTextNode(literal.slice(offset,index)),link);
    offset=index+pin.literal.length;
  }
  line.append(document.createTextNode(literal.slice(offset)));
}
function episodeDescription(episodes, state, showLocation=true) {
  const box=node('div');
  const pending=state==='pending';
  if(pending || state==='partial')box.append(node('p',pending?'Análisis de fuentes en curso.':
    'Descripción parcial. Alguna fuente no terminó correctamente.'));

  for(const episode of episodes) {
    if(showLocation && episode.location) {
      const note=episode.location_status?.replaceAll('_',' ');
      box.append(node('h4',episode.location+(note?' · '+note:'')));
    }
    const findings=node('div');
    findings.className='episode-findings';
    if(episode.inferred_fault && !pending && state!=='partial') {
      const inferred=node('p','Semáforo dañado, inferido por el contexto del reporte.');
      const origin=sources[episode.fields.ubicacion?.[0]?.origin];
      if(origin)inferred.append(node('small',' — '+origin));
      findings.append(inferred);
    }
    const seen=new Set();
    for(const key of Object.keys(fieldLabels)) {
      for(const hit of episode.fields[key]||[]) {
        const literal=hit.literal?.trim();
        if(!literal)continue;
        const identity=literal.normalize('NFC').replace(/\s+/g,' ').toLocaleLowerCase('es-CO');
        if(seen.has(identity))continue;
        seen.add(identity);
        const metadata=[sources[hit.origin],hit.code==='T'&&hit.date?'Mensaje del '+dateLabel(hit.date):null].filter(Boolean);
        const line=node('p');
        appendFindingLiteral(line,literal,hit.gps||[]);
        if(metadata.length)line.append(node('small',' — '+metadata.join(' · ')));
        findings.append(line);
      }
    }
    if(findings.children.length)box.append(findings);
  }
  return box;
}

function evidenceLink(label, params) {
  const link=node('a',label);
  link.href='/reportes?'+new URLSearchParams(params);
  link.target='_blank';
  link.rel='noopener noreferrer';
  return link;
}

function detailedEpisode(row, episode) {
  const report=node('details');
  report.className='citizen-report';
  const label=episode.location||'Ubicación sin identificar';
  const summary=node('summary');
  summary.append(node('span',label),node('small',dateRange(row.date_from,row.date_to)));
  report.append(summary);
  report.addEventListener('toggle',()=>{
    if(!report.open || report.children.length>1)return;
    const body=node('div');
    body.className='citizen-report-body';
    body.append(episodeDescription([episode],row.analysis_state,false));
    const files=node('div');
    files.className='citizen-report-files';
    files.append(node('h4','Evidencias'));
    const links=node('ul');
    for(const [key,labels] of Object.entries(evidenceTypes)) {
      const count=episode.evidence_counts?.[key]||0;
      if(!count || key==='audio_video')continue;
      const item=node('li');
      item.append(evidenceLink(count+' '+labels[count===1?0:1],{conversacion:row.id,episodio:episode.id,tipo:key}));
      links.append(item);
    }
    if(links.children.length)files.append(links);
    else files.append(node('p','Sin archivos vinculados a este reporte.'));
    if(row.unassigned_evidence_count)files.append(evidenceLink('Ver archivos de la conversación',{conversacion:row.id}));
    body.append(files);
    report.append(body);
  });
  return report;
}

function renderDetailed(query) {
  const list=byId('citizenReports');
  const groups=new Map();
  for(const row of view.items) {
    const label=row.archive_label||row.reporter;
    const nameMatch=[label,row.reporter].some(value=>value.toLocaleLowerCase('es-CO').includes(query));
    const reports=row.episodes.filter(ep=>nameMatch||(ep.location||'Ubicación sin identificar').toLocaleLowerCase('es-CO').includes(query));
    if(!reports.length)continue;
    if(!groups.has(row.reporter_key))groups.set(row.reporter_key,{label,items:[]});
    const {items}=groups.get(row.reporter_key);
    for(const episode of reports)items.push({row,episode});
  }
  list.replaceChildren();
  for(const {label,items} of groups.values()) {
    const person=node('details');
    person.className='citizen-reports';
    const summary=node('summary');
    summary.append(node('span',label),node('small',items.length+(items.length===1?' reporte':' reportes')));
    person.append(summary);
    person.addEventListener('toggle',()=>{
      if(!person.open || person.children.length>1)return;
      const reports=node('div');
      reports.className='citizen-report-list';
      reports.append(...items.map(({row,episode})=>detailedEpisode(row,episode)));
      person.append(reports);
    });
    list.append(person);
  }
  byId('reportEmpty').textContent=groups.size?'':'Aún no hay reportes para mostrar con esta búsqueda.';
}

function renderRows() {
  if(!view) return;
  const rows=byId('reportRows');
  rows.replaceChildren();
  const query=byId('reportSearch').value.trim().toLocaleLowerCase('es-CO');
  if(detailed)return renderDetailed(query);
  const matching=view.items.filter(row=>((team?row.code+' ':'')+(row.intersection||'')).toLocaleLowerCase('es-CO').includes(query));
  const end = Math.min(matching.length,(page+1)*pageSize);
  for(const row of matching.slice(page*pageSize,end)) {
    const tr=node('tr');
    if(locationEditor) {
      const code=node('td');
      const button=node('button',row.code);
      button.type='button';button.className='secondary';button.onclick=()=>edit(row);
      code.append(button);tr.append(code);
    }
    const description=node('td');
    description.className='report-description';
    if(row.preliminary && row.description) {
      const list=node('ul');
      list.className='report-points';
      for(const part of row.description.split(' · ')) {
        const entry=node('li');
        const separator=part.indexOf(': ');
        if(separator>0) {
          entry.append(node('strong',part.slice(0,separator)+': '),document.createTextNode(part.slice(separator+2)));
        } else entry.textContent=part;
        list.append(entry);
      }
      description.append(list);
    } else description.textContent=row.description||'Por consolidar';
    tr.append(node('td',formatDate(row.date)),node('td',row.intersection||'Por revisar'),description);
    if(locationEditor) tr.append(node('td',[states[row.revision],states[row.processing]].filter(Boolean).join(' · ')));
    tr.append(node('td',row.reports_at_intersection??'—'));
    if(!locationEditor) tr.append(catalog(row));
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
  stats.hidden=detailed;
  if(detailed) {
    byId('mapPanel').hidden=true;
    renderRows();
    return;
  }

  const latest = view.items.reduce((date,row)=>row.date && (!date || new Date(row.date)>new Date(date))?row.date:date,null);
  const total=view.totals||{};
  const conversations=view.conversations_included??0;
  const statsItems = locationEditor ? [['Reportes del corte',view.items.length],
    ['Reportes ubicados',view.map.markers.length],['Último registro',formatDate(latest)]] :
    [['Reportes',total.records??view.items.length,conversations+(conversations===1?' conversación incluida':' conversaciones incluidas')],
     ['Fotos',total.photos??0],['Videos',total.videos??0],
     ['Audios',total.audios??0,(total.whatsapp_audios??0)+' de WhatsApp · '+(total.video_audios??0)+' de video'],
     ['Cruces identificados',total.crossings??0]];
  for(const [label,count,detail] of statsItems) {
    const card=node('article');
    card.append(node('span',label),node('strong',count));
    if(detail)card.append(node('small',detail));
    stats.append(card);
  }
  byId('mapSelection').textContent='';
  byId('mapPanel').hidden=team && !locationEditor;
  if(!byId('mapPanel').hidden) {
    drawMap(view);
    if(locationEditor || view.map.markers.length) byId('recordsPanel').before(byId('mapPanel'));
    else byId('recordsPanel').after(byId('mapPanel'));
  }
  renderRows();
}
function playable(file) {
  const isVideo=file.type==='video';
  const wrap=node('div');
  const player=node(isVideo?'video':'audio');
  player.controls=true;
  player.preload='none';
  player.src=file.content;
  if(isVideo)player.playsInline=true;
  const speeds=node('div');
  speeds.className='evidence-speeds';
  speeds.setAttribute('aria-label','Velocidad de reproducción');
  speeds.append(node('span','Velocidad'));
  for(const [rate,label] of [[1,'1×'],[1.5,'1,5×'],[2,'2×']]) {
    const button=node('button',label);
    button.type='button';
    button.className='secondary';
    button.setAttribute('aria-pressed',String(rate===1));
    button.onclick=()=>{
      player.defaultPlaybackRate=rate;
      player.playbackRate=rate;
      for(const control of speeds.querySelectorAll('button'))control.setAttribute('aria-pressed',String(control===button));
    };
    speeds.append(button);
  }
  player.addEventListener('error',()=>{
    if(!wrap.querySelector('.media-error')) {
      const note=node('p','Vista previa no disponible en este navegador. Puedes descargar el archivo.');
      note.className='media-error muted';
      wrap.append(note);
    }
  });
  wrap.append(player,speeds);
  return wrap;
}
function chatPreview(file, open) {
  const details=node('details');
  const text=node('pre');
  details.append(node('summary','Leer chat completo'),text);
  details.addEventListener('toggle',async()=>{
    if(!details.open || text.dataset.loaded)return;
    text.dataset.loaded='loading';
    text.textContent='Abriendo chat…';
    try {
      const response=await fetch(file.content,{cache:'no-store'});
      if(!response.ok)throw Error('El chat no está disponible. Actualiza el visor para volver a abrirlo.');
      text.textContent=await response.text();
      text.dataset.loaded='yes';
    } catch(error) {
      delete text.dataset.loaded;
      text.textContent=error.message;
    }
  });
  details.open=open;
  return details;
}
const modelStates = {
  pending:'Pendiente de procesamiento', running:'Modelo en ejecución',
  failed:'Falló el modelo', partial:'La extracción produjo resultados parciales',
  absent:'No hay una ejecución registrada para esta evidencia',
  no_audio:'El video no tiene una pista de audio disponible'
};
const variables = {
  ubicacion:'Ubicación', descripcion_dano:'Daño descrito',
  tiempo_sin_funcionar:'Duración mencionada', afectaciones:'Afectaciones'
};
function reviewForm(result, mode) {
  const form=node('form');
  form.className='evidence-review';
  const stored=result.review;
  const inputs=[];
  const count=mode==='frame_counts';
  const semantic=mode==='semantic_fields';
  const fields=semantic?Object.entries(fieldLabels):[[null,null]];
  for(const [field,label] of fields) {
    const group=semantic?node('fieldset'):form;
    if(semantic)group.append(node('legend',label));
    for(const [name,caption] of (count||semantic)?[['observed','Observado'],['detected','Detectado']]:[['location','Detectó ubicación']]) {
      const input=node('input'), wrapper=node('label');
      input.type=count?'number':'checkbox';
      if(count) {
        input.min=0;input.max=1000;input.step=1;input.required=true;
        input.value=stored?.[name]??(name==='detected'?result.automatic_count??'':'');
        wrapper.append(caption,input);
      } else {
        input.checked=semantic?stored?.[field]?.[name]===true:stored===true;
        wrapper.append(input,caption);
      }
      inputs.push({field,name,input});group.append(wrapper);
    }
    if(semantic)form.append(group);
  }
  const save=node('button','Guardar evaluación');
  save.type='submit';save.className='secondary';save.classList.toggle('saved',stored!=null);
  form.addEventListener('input',()=>{save.classList.remove('saved');status.textContent='Cambios pendientes';});
  const status=node('small',stored==null?'Sin evaluación guardada':'Evaluación guardada');
  status.setAttribute('role','status');
  form.append(save,status);
  form.onsubmit=async event=>{
    event.preventDefault();save.disabled=true;
    let label;
    if(count)label=Object.fromEntries(inputs.map(({name,input})=>[name,input.valueAsNumber]));
    else if(semantic) {
      label={};
      for(const {field,name,input} of inputs)(label[field] ||= {})[name]=input.checked;
    } else label=inputs[0].input.checked;
    try {
      await get('/reviews',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({run_id:result.run_id,field:mode,label,reviewer:byId('evidenceReviewer').value.trim()||'Equipo'})});
      save.classList.add('saved');status.textContent='Evaluación guardada';
    } catch(error) {status.textContent=error.message;}
    finally {save.disabled=false;}
  };
  return form;
}
function showModel(card, result, kind) {
  if(!result)return;
  const title=kind==='extraction'?'Extracción de Qwen':kind==='chat'?'Interpretación de chat TXT':
    kind==='video'?'Transcripción del audio extraído del video':
    kind==='frame'?'Evaluación del fotograma':kind==='image'?'Evaluación de la foto':'Transcripción del audio de WhatsApp';
  card.append(node('h5',title));
  if(result.state!=='completed') {
    const status=node('p',(modelStates[result.state]||'Sin salida')+(result.error?' · '+result.error:''));
    status.className='muted';
    card.append(status);
  }
  if(kind==='chat'||kind==='extraction') {
    for(const summary of result.summaries||[])card.append(node('p',summary));
    const assertions=node('dl');
    for(const item of result.assertions||[]) {
      assertions.append(node('dt',tagLabels[item.field_code]||variables[item.variable]||item.variable),
        node('dd',[item.interpretation,item.literal].filter((value,index,list)=>value && list.indexOf(value)===index).join(' · ')));
    }
    if(assertions.children.length)card.append(assertions);
    if(result.state==='completed'&&!result.summaries?.length&&!result.assertions?.length)
      card.append(node('p','El modelo terminó sin hallazgos.'));
  } else if(kind==='frame'||kind==='image') {
    if(result.automatic_count!==undefined)card.append(node('small','Cajas del modelo: '+result.automatic_count));
  } else if(result.state==='completed') {
    const transcript=node('p',result.text||'No se detectó habla para transcribir.');
    transcript.className='evidence-transcript';
    card.append(transcript);
  }
  if(kind==='frame'||kind==='image') {
    if(result.run_id)card.append(reviewForm(result,'frame_counts'));
  } else if(selectedConversation) {
    if(kind==='chat'||kind==='extraction') {
      for(const [index,evaluation] of (result.evaluations||[]).entries()) {
        const block=node('details');
        block.open=true;
        block.append(node('summary','Evaluación Qwen'+(result.evaluations.length>1?' · Fragmento '+(index+1):'')));
        const extracted=node('ul');
        for(const assertion of evaluation.assertions||[])extracted.append(node('li',
          (tagLabels[assertion.field_code]||variables[assertion.variable]||assertion.variable)+' · '+assertion.literal));
        if(extracted.children.length)block.append(extracted);
        else block.append(node('p','Sin hallazgos en esta ejecución.'));
        if(result.evaluations.length>1 && evaluation.sources?.length) {
          const excerpt=node('details');
          excerpt.append(node('summary','Ver texto de este fragmento'),node('pre',evaluation.sources.map(source=>source.text).join('\n')));
          block.append(excerpt);
        }
        block.append(reviewForm(evaluation,'semantic_fields'));card.append(block);
      }
    } else if(result.run_id) {
      card.append(node('h5','Evaluación Whisper'),reviewForm({...result,review:result.semantic_review},'semantic_fields'));
    }
  } else if(result.run_id && kind!=='extraction')card.append(reviewForm(result,'location_detected'));
}
function evidenceCard(file) {
  const card=node('article');
  card.className='evidence-card'+(file.type==='frame'?' evidence-frame':'');
  const local=['image','video','frame'].includes(file.type);
  card.append(node('h4',local?(file.crossing||'Cruce por identificar'):file.name));
  if(local)card.append(node('small',file.name+(file.time!=null?' · segundo '+file.time:'')));
  if(file.sent_at)card.append(node('p','Enviado '+formatDate(file.sent_at)));
  if(local && file.crossing_source) {
    const source=node('small','Ubicación asociada por '+file.crossing_source+
      (file.crossing_time?' · '+formatDate(file.crossing_time):''));
    card.append(source);
  }
  if(file.thumbnail) {
    const thumb=node('img');
    thumb.src=file.thumbnail;
    thumb.loading='lazy';
    thumb.alt=file.name;
    thumb.addEventListener('error',()=>{
      thumb.replaceWith(node('p','Miniatura no disponible. Puedes descargar el original.'));
    });
    card.append(thumb);
  }
  if(['audio','video'].includes(file.type))card.append(playable(file));
  if(file.type==='chat')card.append(chatPreview(file,Boolean(selectedConversation)||selectedType==='chat'));
  if(['chat','frame','image','audio','video'].includes(file.type))
    showModel(card,file.type==='video'?file.transcription:file.analysis,file.type);
  if(selectedConversation && file.extraction)showModel(card,file.extraction,'extraction');
  const link=node('a','Descargar original');
  link.href=file.download;
  link.download=file.name;
  card.append(link);
  return card;
}
function renderEvidence(data) {
  byId('evidenceTitle').textContent=data.intersection?'Evidencias · '+data.intersection:'Evidencias del reporte';
  const scope=data.scope==='conversacion'?'Archivos de la conversación':'Archivos vinculados al registro';
  byId('evidenceScope').textContent=data.date?scope+' · '+formatDate(data.date):scope;
  if(data.episodes) {
    byId('evidenceTitle').textContent=data.intersection||data.archive_label||data.reporter;
    byId('evidenceScope').textContent=scope+' · '+dateRange(data.date_from,data.date_to);
    byId('evidenceSituation').replaceChildren(episodeDescription(data.episodes,data.analysis_state,!data.intersection));
  } else byId('evidenceSituation').textContent=data.situacion_presentada||'Situación por consolidar';
  const list=byId('evidenceFiles'),nav=byId('evidenceTypes');
  list.replaceChildren();nav.replaceChildren();
  for(const [type,labels] of Object.entries(evidenceTypes)) {
    if(type==='audio_video')continue;
    const files=data.items.filter(item=>item.type===type);
    if(!files.length)continue;
    const title=files.length+' '+labels[files.length===1?0:1];
    const group=node('div');
    group.id='files-'+type;
    group.className='evidence-set';
    const heading=node('h3',title);
    heading.tabIndex=-1;
    const link=node('a',title);
    link.href='#'+group.id;
    nav.append(link);
    const cards=node('div');
    cards.className='evidence-grid';
    group.append(heading);
    if(type==='frame') {
      const byVideo=new Map();
      for(const file of files) {
        const frames=byVideo.get(file.video_id)||[];
        frames.push(file);
        byVideo.set(file.video_id,frames);
      }
      for(const [videoId,frames] of byVideo) {
        const video=data.items.find(item=>item.id===videoId);
        const bucket=node('details');
        const grid=node('div');
        grid.className='evidence-grid';
        grid.append(...frames.sort((a,b)=>(a.time??0)-(b.time??0)).map(evidenceCard));
        bucket.open=selectedType==='frame' && byVideo.size===1;
        bucket.append(node('summary',(video?.crossing||video?.name||'Video')+' · '+frames.length+
          (frames.length===1?' fotograma':' fotogramas')),grid);
        group.append(bucket);
      }
    } else {
      cards.append(...files.map(evidenceCard));
      group.append(cards);
    }
    list.append(group);
  }
  if(!list.children.length)list.append(node('p','No hay archivos en el corte actual.'));
  byId('reportLogin').hidden=true;
  byId('evidenceAccess').hidden=false;
  byId('reportStatus').textContent='';
  if(byId('files-'+selectedType))byId('files-'+selectedType).scrollIntoView({block:'start'});
}

async function loadEvidence(signal) {
  byId('reportStatus').textContent='Consultando evidencias…';
  try {
    const base=selectedConversation?'/report-media/conversations/':'/report-media/records/';
    const query=selectedEpisode?'?'+new URLSearchParams({episodio:selectedEpisode}):'';
    const response=await fetch(base+encodeURIComponent(selectedConversation||selectedRecord)+query,{signal,cache:'no-store'});
    if(response.status===401) {
      byId('evidenceAccess').hidden=true;
      byId('evidenceFiles').replaceChildren();
      byId('reportLogin').hidden=false;
      byId('reportStatus').textContent='';
      return;
    }
    if(!response.ok)throw Error('No se pudo abrir el registro.');
    const data=await response.json();
    if(!signal.aborted)renderEvidence(data);
  } catch(error) {
    if(error.name!=='AbortError')byId('reportStatus').textContent=error.message;
  }
}

async function load() {
  request?.abort();
  const current=new AbortController();
  request=current;
  if(selectedRecord||selectedConversation)return loadEvidence(current.signal);
  byId('reportStatus').textContent='Consultando reportes…';
  try {
    const response=await get(locationEditor?'/report-map':team?'/detailed-records':'/semaforos/datos',{signal:current.signal});
    const data=await response.json();
    if(request!==current)return;
    view=data;page=0;
    render();
    byId('reportWork').hidden=false;
    byId('pdfPanel').hidden=!team;
    byId('reportLogin').hidden=true;
    byId('reportStatus').textContent=params.has('detalle')&&!detailed
      ?'Selecciona una evidencia del reporte que quieras abrir.'
      :'Corte '+formatDate(view.cutoff)+' · hora de Cali';
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
  request?.abort();request=null;view=null;selected=null;
  byId('evidenceAccess').hidden=true;byId('evidenceFiles').replaceChildren();byId('evidenceTypes').replaceChildren();
  byId('reportWork').hidden=true;byId('editPanel').hidden=true;byId('reportLogin').hidden=false;
  for(const id of ['reportStats','reportRows','citizenReports','reportMap','reportEvidence','coordinateCandidates'])byId(id).replaceChildren();
  byId('locationForm').reset();
  byId('reportSearch').value='';
  if(byId('shareEvidence'))byId('shareEvidence').checked=false;
  for(const id of ['reportStatus','mapSelection','editTitle','editStatus'])byId(id).textContent='';
}
byId('audience').textContent=team?'Acceso privado':'Consulta pública';
byId('reportLogin').hidden=!team;
byId('preliminaryNote').hidden=team;
byId('recordCodeHeader').hidden=!locationEditor;
byId('recordStateHeader').hidden=!locationEditor;
byId('recordEvidenceHeader').hidden=locationEditor;
byId('crossingCountNote').hidden=locationEditor||detailed;
byId('recordCrossingHeader').hidden=detailed;
byId('recordCrossingCountHeader').hidden=detailed;
if(detailed) {
  byId('recordsTable').hidden=true;
  byId('reportPagination').hidden=true;
  byId('citizenReports').hidden=false;
  byId('recordsPanel').querySelector('h2').textContent='Reportes por ciudadano';
  byId('pdfSummary').textContent='El PDF reúne nombres, cruces y enlaces a las evidencias.';
  byId('reportSearch').labels[0].textContent='Buscar por ciudadano o ubicación';
  byId('reportSearch').placeholder='Nombre, celular, dirección o referencia';
  byId('shareEvidence').checked=true;
  byId('shareEvidence').parentElement.replaceChildren(document.createTextNode('El PDF contiene enlaces directos válidos durante 7 días. Quien reciba el enlace podrá abrir la evidencia.'));
}

if(!locationEditor&&!detailed) {
  byId('reportIntro').textContent='Consulta los cruces y las evidencias disponibles en los reportes ciudadanos.';
  byId('reportSearch').labels[0].textContent='Buscar por cruce';
  byId('reportSearch').placeholder='Calle o carrera';
}
byId('updateRecords').onclick=load;
async function signOut() {
  try {await teamSession.close();logout();}
  catch(error) {byId('reportStatus').textContent=error.message;}
}
byId('evidenceLogout').onclick=signOut;
byId('reportSearch').oninput=()=>{page=0;renderRows();};
byId('prevReport').onclick=()=>{page--;renderRows();};
byId('nextReport').onclick=()=>{page++;renderRows();};
byId('reportLogout').onclick=signOut;
byId('reportLoginForm').onsubmit=async event=>{
  event.preventDefault();
  const key=byId('reportKey').value;
  byId('reportKey').value='';
  try {
    await teamSession.open(key);
    await load();
  } catch(error) {
    byId('reportStatus').textContent=error.message;
  }
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
      body:JSON.stringify({share_evidence:detailed||byId('shareEvidence')?.checked,detailed_report:detailed,action_report:!locationEditor})});
    const ident=response.headers.get('X-Report-Export-ID');
    download(await response.blob(),'semaforos-cali-'+ident+'.pdf');
    byId('reportStatus').textContent='Informe generado · '+ident;
  } catch(error) {byId('reportStatus').textContent=error.message;}
  finally {button.disabled=false;}
};
if(!team)load();
else teamSession.active().then(active=>{if(active)load();});
