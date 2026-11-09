'use strict';
// Comparte api() autenticada con panel.js; nunca persiste contactos o claves.
let conversationOffset=0,findingOffset=0,reportOffset=0,currentReport=null;
let conversationTotal=0,findingTotal=0,reportTotal=0,reviewBusy=false;
const selected=new Map(),reviewPageSize=25;
const variableNames={ubicacion:'Ubicación',descripcion_dano:'Daño relatado',tiempo_sin_funcionar:'Tiempo declarado',afectaciones:'Afectaciones'};
function reviewNotice(message){$('reviewNotice').textContent=message;}
function chosen(){
  const previous=$('primaryFinding').value;$('primaryFinding').replaceChildren();
  $('primaryFinding').append(new Option('Elige el mensaje principal',''));
  for(const f of selected.values()){const option=document.createElement('option');option.value=f.id;option.textContent=variableNames[f.variable]+' · '+f.display_literal.slice(0,90);$('primaryFinding').append(option);}
  if(selected.has(previous))$('primaryFinding').value=previous;
  $('selectedFindings').textContent=selected.size+' afirmaciones seleccionadas (incluye otras páginas)';
}
async function loadConversations(){
  const data=await api('/conversations?offset='+conversationOffset+'&limit='+reviewPageSize);
  conversationTotal=data.total;selected.clear();chosen();currentReport=null;$('reportDetailBox').hidden=true;$('findingRows').replaceChildren();$('reportRows').replaceChildren();
  $('reviewConversation').replaceChildren(new Option('Selecciona una conversación',''));
  for(const item of data.items)$('reviewConversation').append(new Option(item.original_name,item.id));
  $('previousConversations').disabled=conversationOffset===0;$('nextConversations').disabled=conversationOffset+reviewPageSize>=data.total;
}
async function loadFindings(){
  const cid=$('reviewConversation').value;if(!cid)return;
  const data=await api('/findings?conversation_id='+cid+'&offset='+findingOffset+'&limit='+reviewPageSize);
  findingTotal=data.total;
  $('findingRows').replaceChildren();
  for(const f of data.items){
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=selected.has(f.id);checkbox.setAttribute('aria-label','Seleccionar '+f.display_literal);
    checkbox.onchange=()=>{if(checkbox.checked)selected.set(f.id,f);else selected.delete(f.id);chosen();};
    const quote=document.createElement('div'),text=document.createElement('p');text.textContent=f.display_literal;quote.append(text);
    const more=document.createElement('details'),title=document.createElement('summary'),raw=document.createElement('pre');
    title.textContent='Ver fuente original';raw.textContent=f.source_ref.text;more.append(title,raw);quote.append(more);
    row($('findingRows'),[checkbox,variableNames[f.variable]+' · '+f.origin,quote,f.sent_at?new Date(f.sent_at).toLocaleString('es-CO',{timeZone:'America/Bogota'}):'Fecha desconocida',(f.report_codes||[]).map(n=>'R-'+String(n).padStart(6,'0')).join(', ')||'Sin agrupar']);
  }
  if(!data.items.length)row($('findingRows'),['','Aún no hay afirmaciones extraídas.','','','']);
  $('findingPage').textContent=`${findingOffset+1}–${Math.min(findingOffset+reviewPageSize,data.total)} de ${data.total}`;
  $('previousFindings').disabled=findingOffset===0;$('nextFindings').disabled=findingOffset+reviewPageSize>=data.total;
}
async function loadReports(){
  const cid=$('reviewConversation').value;if(!cid)return;
  const data=await api('/reports?conversation_id='+cid+'&offset='+reportOffset+'&limit='+reviewPageSize);
  reportTotal=data.total;
  $('reportRows').replaceChildren();$('reportCount').textContent=data.active+' reportes vigentes · '+data.total+' con historial de descartados';
  for(const r of data.items){const b=button('Abrir',()=>openReport(r.id));row($('reportRows'),['R-'+String(r.code).padStart(6,'0'),r.revision,r.version,b]);}
  $('reportPage').textContent=`${reportOffset+1}–${Math.min(reportOffset+reviewPageSize,data.total)} de ${data.total}`;
  $('previousReports').disabled=reportOffset===0;$('nextReports').disabled=reportOffset+reviewPageSize>=data.total;
}
async function openReport(id){
  currentReport=await api('/reports/'+id);selected.clear();for(const f of currentReport.findings)selected.set(f.id,f);chosen();
  $('primaryFinding').value=currentReport.primary_finding_id;$('reportSummary').value=currentReport.summary||'';
  $('reportTitle').textContent=currentReport.code_display+' · versión '+currentReport.version+' · '+(currentReport.revision_effective||currentReport.revision)+(currentReport.review_outdated?' · hay procesamiento posterior a la revisión':'');
  $('reportDetail').textContent=JSON.stringify(currentReport,null,2);$('reportDetailBox').hidden=false;
  $('attachReport').disabled=false;$('replaceReport').disabled=false;await loadFindings();
}
let pendingReportRequest=null;
async function mutateReport(action,revision){
  const reviewer=$('reportReviewer').value.trim(),reason=$('reportReason').value.trim();
  if(!reviewer||!reason)throw Error('Indica quién revisa y el motivo de la decisión.');
  if(action!=='create'&&!currentReport)throw Error('Abre el reporte que quieres modificar.');
  const data={action,reviewer,reason};
  if(action!=='review'){
    data.finding_ids=[...selected.keys()];
    if(!data.finding_ids.length)throw Error('Selecciona al menos una afirmación.');
    if(data.finding_ids.length>200)throw Error('Selecciona hasta 200 afirmaciones por operación.');
  }
  if(action==='create'||action==='replace')data.primary_finding_id=$('primaryFinding').value;
  if((action==='create'||action==='replace')&&!data.primary_finding_id)throw Error('Elige la fuente principal que define la fecha del reporte.');
  if(action==='create'||action==='replace'||action==='review')data.summary=$('reportSummary').value.trim()||null;
  if(action!=='create')data.expected_version=currentReport.version;
  if(revision)data.revision=revision;
  const path=action==='create'?'/reports':'/reports/'+currentReport.id+'/changes';
  const signature=JSON.stringify([path,data]);
  // Reintentar una petición cuya respuesta se perdió conserva su idempotency key.
  if(!pendingReportRequest||pendingReportRequest.signature!==signature)pendingReportRequest={signature,id:crypto.randomUUID()};
  data.request_id=pendingReportRequest.id;
  const result=await api(path,{method:'POST',json:data});pendingReportRequest=null;
  await openReport(result.id);await loadReports();reviewNotice('Guardado '+result.code+' · versión '+result.version+'. Predicciones originales conservadas.');
}
function guarded(id,fn){$(id).onclick=async()=>{if(reviewBusy)return;reviewBusy=true;const controls=[...$('reviewWorkspace').querySelectorAll('button')];for(const b of controls)b.disabled=true;$('reviewConversation').disabled=true;try{await fn();}catch(e){reviewNotice(e.message);}finally{
  reviewBusy=false;$('reviewConversation').disabled=false;
  for(const b of controls)b.disabled=false;
  $('attachReport').disabled=!currentReport;$('replaceReport').disabled=!currentReport;
  $('previousFindings').disabled=findingOffset===0;$('previousReports').disabled=reportOffset===0;$('previousConversations').disabled=conversationOffset===0;
  $('nextFindings').disabled=findingOffset+reviewPageSize>=findingTotal;$('nextReports').disabled=reportOffset+reviewPageSize>=reportTotal;$('nextConversations').disabled=conversationOffset+reviewPageSize>=conversationTotal;
}};}
guarded('loadReview',loadConversations);
$('reviewConversation').onchange=async()=>{selected.clear();chosen();currentReport=null;findingOffset=0;reportOffset=0;$('reportDetailBox').hidden=true;$('attachReport').disabled=true;$('replaceReport').disabled=true;$('reportSummary').value='';try{await Promise.all([loadFindings(),loadReports()]);}catch(e){reviewNotice(e.message);}};
guarded('clearFindings',async()=>{selected.clear();chosen();await loadFindings();});
for(const [id,action,revision] of [['createReport','create'],['attachReport','attach'],['replaceReport','replace'],['approveReport','review','revisado'],['pendingReport','review','pendiente'],['discardReport','review','descartado']])guarded(id,()=>mutateReport(action,revision));
guarded('historyReport',async()=>{if(!currentReport)return;$('reportDetail').textContent=JSON.stringify(await api('/reports/'+currentReport.id+'/history'),null,2);});
for(const direction of ['previous','next']){
  guarded(direction+'Conversations',async()=>{conversationOffset=Math.max(0,conversationOffset+(direction==='next'?reviewPageSize:-reviewPageSize));await loadConversations();});
  guarded(direction+'Findings',async()=>{findingOffset=Math.max(0,findingOffset+(direction==='next'?reviewPageSize:-reviewPageSize));await loadFindings();});
  guarded(direction+'Reports',async()=>{reportOffset=Math.max(0,reportOffset+(direction==='next'?reviewPageSize:-reviewPageSize));await loadReports();});
}
document.addEventListener('sc:logout',()=>{selected.clear();currentReport=null;pendingReportRequest=null;chosen();for(const id of ['findingRows','reportRows','reportDetail'])$(id).replaceChildren();$('reportDetailBox').hidden=true;$('reportReviewer').value='';$('reportReason').value='';$('reportSummary').value='';});
