'use strict';
// Private, lazy media; polling preserves playback and edits. No video player.
const curatedUrls=new Set(),curationGroups=new Map();
let curationOffset=0,curationBusy=false,curationEpoch=0;
function cnode(tag,text){const e=document.createElement(tag);if(text)e.textContent=text;return e;}
function releaseMedia(element){for(const media of element.querySelectorAll('img,audio'))if(curatedUrls.delete(media.src))URL.revokeObjectURL(media.src);}
async function privateMedia(url,element){
  const epoch=curationEpoch,r=await fetch(url,{headers:{Authorization:'Bearer '+token},cache:'no-store'});
  if(!r.ok)throw new Error('Archivo no disponible');
  const blob=await r.blob();if(epoch!==curationEpoch||!element.isConnected)return;
  const u=URL.createObjectURL(blob);curatedUrls.add(u);element.src=u;
}
const processing=$('overallProgress').closest('section');
processing.querySelector('h2').textContent='Procesamiento y resultados de los modelos';
processing.querySelector('.tag').textContent='Revisión por conversación';
$('jobsRows').closest('.tableScroll').hidden=true;$('jobPage').parentElement.hidden=true;
$('modelResultsRows').closest('section').hidden=true;
const reviewer=cnode('input');reviewer.placeholder='Nombre de quien revisa';reviewer.maxLength=100;reviewer.setAttribute('aria-label','Nombre de quien revisa');
const curate=cnode('div');curate.id='curation';
const moreConversations=button('Más conversaciones',()=>loadCurationConversations());
processing.append(reviewer,button('Actualizar conversaciones',()=>loadCuration()),curate,moreConversations);
processing.append(cnode('p','Aprobar valida esta salida del modelo; no certifica el daño físico. Los originales y las predicciones se conservan.'));
for(const id of ['comparisonWorkspace','reviewWorkspace']){
  const section=$(id),details=cnode('details'),summary=cnode('summary',id==='comparisonWorkspace'?'Versiones de conversaciones':'Organizar reportes');
  section.before(details);details.append(summary,section);
}
const lazyImages=new IntersectionObserver(entries=>{
  for(const entry of entries)if(entry.isIntersecting){const img=entry.target;lazyImages.unobserve(img);
    privateMedia(img.dataset.url,img).catch(()=>{img.alt='Miniatura no disponible; abre la salida del modelo';});}
},{rootMargin:'150px'});
function makeCard(item,conversation){
  const card=cnode('article');card.className='curationCard';card.dataset.jobId=item.id;
  card.append(cnode('h3',(stages[item.stage]||item.stage)+' · '+item.file_name),cnode('p',states[item.state]||item.state),jobBar(item));
  if(item.started_at&&item.state==='running')card.append(cnode('small','Inicio: '+new Date(item.started_at).toLocaleTimeString('es-CO')));
  if(item.modality==='frame')card.append(cnode('small','Segundo '+(item.metadata?.segundo??'—')));
  if(item.payload?.superseded_by_review){card.append(cnode('p','Salida anterior: sustituida por una transcripción corregida.'));return card;}
  if(item.payload?.legacy_mixed_senders){
    card.append(cnode('p','Salida antigua con mensajes del equipo. Reprocesa solo los mensajes ciudadanos.'),button('Reprocesar mensajes ciudadanos',()=>api('/jobs',{method:'POST',json:{evidence_id:item.evidence_id,experiment_id:item.experiment_id}})));return card;
  }
  const output=item.output||{},readable=cnode('div');readable.className='modelText';
  readable.textContent=item.state==='running'?(item.progress?.preview||item.progress?.phase||'Modelo en ejecución; porcentaje aún no disponible.'):
    item.state==='completed'?(item.stage==='audio'?(item.review?.text??output.text??'Sin habla detectada'):resultVariables({...item,output_summary:item.stage==='video'?{frame_count:output.fotogramas?.length,has_audio:!!output.audio}:output})):
    item.state==='failed'?'Error: '+(item.run_error_code||'ver salida'):'Esperando su turno.';
  card.append(readable);
  if(item.stage==='video'&&output.estado_audio==='error_extraccion'){
    card.append(cnode('p','No se pudo extraer una pista de audio válida. Revisa el video original.'));
  }
  if(item.stage==='text'){
    const original=cnode('details');original.append(cnode('summary','Fuentes originales'),cnode('p',(item.payload?.sources||[]).map(s=>s.text).join('\n')));card.append(original);
  }
  if(item.stage==='detect'&&item.run_id&&item.state==='completed'){
    const img=cnode('img');img.alt='Semáforos detectados con bounding boxes';img.className='curationImage';img.loading='lazy';
    img.dataset.url='/runs/'+item.run_id+'/thumbnail';card.append(img);lazyImages.observe(img);
    card.append(button('Ampliar imagen',async()=>{await showRun(item);$('resultBox').scrollIntoView({behavior:'smooth'});}));
  }
  if(item.stage==='audio'){
    if(output.needs_review)card.append(cnode('p',output.status==='sin_voz_clara'?
      'Sin voz clara. Escucha el original y corrige la transcripción si se entiende.':
      'Transcripción con pasajes inciertos. Revisa el audio.'));
    const audio=cnode('audio');audio.controls=true;audio.preload='none';
    card.append(audio,button('Escuchar',async()=>{if(!audio.src)await privateMedia('/evidence/'+item.evidence_id+'/audio',audio);if(audio.src)await audio.play();}),button('1×',()=>{audio.playbackRate=1;}),button('1,5×',()=>{audio.playbackRate=1.5;}));
  }
  if(item.run_id)card.append(button('Salida del modelo',async()=>{await showRun({...item,conversation_name:conversation.original_name});$('resultBox').scrollIntoView({behavior:'smooth'});}));
  if(item.state==='failed'&&['text','audio'].includes(item.stage))card.append(button('Reintentar',()=>api('/jobs/'+item.id+'/retry',{method:'POST'})));
  if(item.state==='completed'&&item.stage!=='video'){
    const status=cnode('p',item.review?'Revisión: '+({approved:'Aprobado',corrected:'Corregido y aprobado',not_evaluable:'No evaluable'}[item.review.decision]):'Pendiente de revisión humana');card.append(status);
    async function save(decision,text){
      if(!reviewer.value.trim())throw new Error('Escribe tu nombre como revisor.');
      await api('/runs/'+item.run_id+'/curation',{method:'POST',json:{decision,reviewer:reviewer.value.trim(),text}});
      status.textContent=decision==='approved'?'Aprobado':decision==='corrected'?'Corrección guardada; nueva extracción en cola.':'No evaluable';card.dataset.signature='';
    }
    card.append(button('Aprobar',()=>save('approved')),button('No evaluable',()=>save('not_evaluable')));
    if(item.stage==='audio'){
      const edit=cnode('details'),text=cnode('textarea');text.value=item.review?.text??output.text??'';text.setAttribute('aria-label','Transcripción corregida');
      edit.append(cnode('summary','Corregir transcripción'),text,button('Guardar corrección y aprobar',()=>save('corrected',text.value)));card.append(edit);
    }
  }
  return card;
}
const reportLabels={falla_mencionada:'Falla reportada',accidente_mencionado:'Accidentes o choques',
  riesgo_o_casi_accidente:'Riesgo o casi accidente',agentes_de_transito:'Guardas o agentes',
  regulacion_del_trafico:'Personas regulando el tránsito',congestion:'Congestión'};
const qualifiers={negado:' · negado en la fuente',pregunta:' · pregunta',riesgo_o_casi:' · riesgo o casi accidente'};
const sourceLabels={chat:'chat',audio_whatsapp:'audio de WhatsApp',audio_video:'audio de video'};
function renderMicroReport(target,data){
  const signature=JSON.stringify(data);
  if(target.dataset.signature===signature)return;
  target.dataset.signature=signature;
  target.replaceChildren(cnode('h3','Microreporte por reportante'));
  if(!data.reporters.length){target.append(cnode('p','Aún no hay menciones identificadas en las fuentes disponibles.'));return;}
  for(const report of data.reporters){
    const card=cnode('article');card.className='curationCard';
    card.append(cnode('h4',report.reporter||'Remitente sin identificar'),
      cnode('p',report.reported_estimate==null?'Cantidad de semáforos sin precisar':
        'Semáforos reportados, estimación: '+report.reported_estimate));
    if(report.explicit_quantities.length)card.append(cnode('p','Cantidades mencionadas: '+report.explicit_quantities.join(', ')));
    const locations=cnode('ul');
    for(const item of report.locations)locations.append(cnode('li',item.label+
      (item.road_types_explicit?'':' (tipo de vía sin precisar)')+' · '+sourceLabels[item.origin]));
    for(const item of report.gps){
      const li=cnode('li','GPS · '+sourceLabels[item.origin]+' · ');
      const link=cnode('a',item.latitude+', '+item.longitude);
      link.href='https://www.openstreetmap.org/?mlat='+item.latitude+'&mlon='+item.longitude+'#map=18/'+item.latitude+'/'+item.longitude;
      link.target='_blank';link.rel='noopener noreferrer';li.append(link);locations.append(li);
    }
    if(locations.childElementCount)card.append(cnode('strong','Ubicación'),locations);
    if(report.durations.length)card.append(cnode('p','Tiempo mencionado: '+report.durations.map(x=>x.literal).join(' · ')));
    const context=cnode('ul');
    for(const item of report.mentions.slice(0,5)){
      context.append(cnode('li',reportLabels[item.category]+(qualifiers[item.qualifier]||'')+' · «'+item.literal+'» · '+sourceLabels[item.origin]));
    }
    if(context.childElementCount)card.append(context);
    if(report.mentions.length>5){
      const more=cnode('details'),rest=cnode('ul');
      for(const item of report.mentions.slice(5))rest.append(cnode('li',reportLabels[item.category]+(qualifiers[item.qualifier]||'')+' · «'+item.literal+'» · '+sourceLabels[item.origin]));
      more.append(cnode('summary','Más contexto del reporte'),rest);card.append(more);
    }
    target.append(card);
  }
}
$('refreshReportStats').onclick=async()=>{
  const target=$('reportStatistics');
  try{
    const stats=await api('/report-statistics');
    const entries=[
      ['Conversaciones analizadas',stats.conversations_analyzed],
      ['Conversaciones con menciones',stats.conversations_with_mentions],
      ['Grupos por reportante y conversación',stats.reporter_groups],
      ['Grupos con GPS',stats.groups_with_gps],
      ['Grupos con duración',stats.groups_with_duration],
      ['Grupos con cantidad estimada',stats.groups_with_count],
      ...Object.entries(reportLabels).map(([key,label])=>[label,stats.topics[key]??0])
    ];
    const list=cnode('ul');
    for(const [label,value] of entries)list.append(cnode('li',label+' · '+value));
    target.replaceChildren(list);
  }catch(error){target.textContent=error.message;}
};
async function updateGroup(group){
  if(group.busy||!group.element.open)return;group.busy=true;const epoch=curationEpoch;
  try{
    const report=await api('/conversations/'+group.conversation.id+'/micro-report');
    if(epoch!==curationEpoch||!group.element.open)return;
    renderMicroReport(group.report,report);
    for(let offset=0;offset<=group.offset;offset+=100){
      const data=await api('/curation/'+group.conversation.id+'?offset='+offset);if(epoch!==curationEpoch)return;
      for(const item of data.items){
        const signature=JSON.stringify([item.state,item.run_id,item.progress,item.review,item.payload?.superseded_by_review]);
        const old=group.cards.get(item.id);
        if(old&&(old.dataset.signature===signature||old.contains(document.activeElement)||[...old.querySelectorAll('audio')].some(a=>!a.paused)))continue;
        let target=group.body;
        if(item.parent_id){
          if(!group.parents.has(item.parent_id)){
            const d=cnode('details'),grid=cnode('div');grid.className='curationGrid';
            d.append(cnode('summary','Video: '+(item.parent_name||'original')+' · fotogramas y audio'),grid);group.body.append(d);group.parents.set(item.parent_id,grid);
          }target=group.parents.get(item.parent_id);
        }
        const card=makeCard(item,group.conversation);card.dataset.signature=signature;
        if(old){releaseMedia(old);old.replaceWith(card);}else target.append(card);group.cards.set(item.id,card);
      }
      if(offset===group.offset)group.more.hidden=data.next_offset===null;
    }
  }finally{group.busy=false;}
}
async function loadCurationConversations(offset=curationOffset){
  const epoch=curationEpoch,data=await api('/conversations?offset='+offset+'&limit=10');if(epoch!==curationEpoch)return;
  curationOffset=Math.max(curationOffset,offset+data.items.length);
  for(const conversation of data.items){
    if(curationGroups.has(conversation.id))continue;
    const element=cnode('details'),body=cnode('div');element.className='curationConversation';
    const group={element,body,conversation,report:cnode('div'),offset:0,cards:new Map(),parents:new Map(),busy:false};
    group.more=button('Más resultados de esta conversación',async()=>{group.offset+=100;await updateGroup(group);});group.more.hidden=true;
    element.append(cnode('summary',conversation.original_name),group.report,body,group.more);curate.append(element);curationGroups.set(conversation.id,group);
    element.name='curation-conversations';
    element.ontoggle=()=>{
      if(element.open)updateGroup(group).catch(e=>notice(e.message));
      else for(const audio of element.querySelectorAll('audio'))audio.pause();
    };
  }
  moreConversations.hidden=curationOffset>=data.total;
}
async function loadCuration(){
  if(curationBusy||!token)return;curationBusy=true;
  try{await loadCurationConversations(0);for(const group of curationGroups.values())await updateGroup(group);}
  finally{curationBusy=false;}
}
document.addEventListener('sc:refreshed',()=>loadCuration().catch(e=>notice(e.message)));
document.addEventListener('sc:logout',()=>{curationEpoch++;lazyImages.disconnect();for(const u of curatedUrls)URL.revokeObjectURL(u);curatedUrls.clear();curate.replaceChildren();curationGroups.clear();$('reportStatistics').replaceChildren();curationOffset=0;});
