'use strict';
// Sin tokens en localStorage, URL o cookies. Datos y acciones solo por Bearer.
const $=id=>document.getElementById(id);
const states={receiving:'Recibiendo',queued:'En cola de importación',importing:'Validando ZIP',received:'Importado',error:'Error de importación',cancelled:'Cancelado',pending:'Pendiente',running:'Procesando',completed:'Completado',failed:'Falló'};
const stages={audio:'Audio → texto',detect:'Detección de semáforos',lights:'Lectura de luces',text:'Extracción de texto',video:'Preparación de video'};
let token='',timer=null,busy=false,pause=false,uploadOffset=0,jobOffset=0,uploadTotal=0,jobTotal=0,chunkSize=4194304;
let selectedJobId=null,selectedState=null,annotationUrl=null;
const pageSize=25;
function notice(text){$('notice').textContent=text;}
function size(n){return (n/1024**3).toFixed(2)+' GiB';}
async function api(path,options={}){
  const headers={...options.headers,Authorization:'Bearer '+token};
  if(options.json!==undefined){headers['Content-Type']='application/json';options.body=JSON.stringify(options.json);}
  const response=await fetch(path,{...options,headers,cache:'no-store'});
  const body=await response.json();
  if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Solicitud no aceptada ('+response.status+')');
  return body;
}
function button(text,action){const b=document.createElement('button');b.className='secondary';b.textContent=text;b.onclick=async()=>{b.disabled=true;try{await action();await refresh();}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;}
function row(table,values){const tr=document.createElement('tr');for(const value of values){const td=document.createElement('td');if(value instanceof Node)td.append(value);else td.textContent=String(value??'—');tr.append(td);}table.append(tr);}
function jobSource(item){
  const box=document.createElement('div');box.textContent=stages[item.stage]||item.stage;
  const source=document.createElement('span');source.className='jobOrigin';
  const metadata=item.evidence_metadata||{};
  if(item.modality==='frame')source.textContent=(item.parent_name||'Video')+' · segundo '+(metadata.segundo??'?')+' · '+item.file_name;
  else if(item.modality==='audio'&&item.parent_name)source.textContent=(item.parent_name||'Video')+' · audio extraído';
  else source.textContent=item.file_name||'Archivo sin nombre';
  const conversation=document.createElement('span');conversation.className='jobOrigin';conversation.textContent='Conversación: '+(item.conversation_name||'—');
  box.append(source,conversation);return box;
}
function jobBar(item){
  const box=document.createElement('div');box.className='jobProgress';
  const bar=document.createElement('progress');bar.max=100;
  const fraction=item.progress?.fraction;
  if(item.state==='completed'||item.state==='failed')bar.value=100;
  else if(item.state==='pending')bar.value=0;
  else if(typeof fraction==='number'&&Number.isFinite(fraction))bar.value=Math.max(0,Math.min(99,Math.round(fraction*100)));
  bar.setAttribute('aria-label','Avance de '+(stages[item.stage]||item.stage));
  const description=document.createElement('small');description.textContent=item.state==='failed'?'Finalizó con error: '+(item.run_error_code||'ver salida'):
    item.state==='completed'?'Terminada':item.state==='pending'?'En espera':item.progress?.phase||'En ejecución; tiempo desconocido';
  box.append(bar,description);return box;
}
function clearAnnotation(){if(annotationUrl)URL.revokeObjectURL(annotationUrl);annotationUrl=null;$('annotatedImage').hidden=true;$('annotatedImage').removeAttribute('src');$('annotationNotice').textContent='';}
async function showRun(item){
  selectedJobId=item.id;selectedState=item.state;$('resultBox').hidden=false;clearAnnotation();
  $('resultStatus').textContent=(stages[item.stage]||item.stage)+' · '+(states[item.state]||item.state)+' · '+(item.file_name||'');
  $('modelText').textContent='';$('result').textContent='';
  if(item.state==='running'){
    $('modelText').textContent=item.progress?.preview||item.progress?.phase||'El modelo está trabajando; todavía no ha producido texto.';
  }
  if(!item.run_id)return;
  const run=await api('/runs/'+item.run_id);
  if(selectedJobId!==item.id)return;
  $('result').textContent=JSON.stringify(run,null,2);
  if(run.state==='failed'||run.state==='interrupted')$('modelText').textContent='La ejecución terminó con '+(run.error_code||'un error')+'. Revisa el código de error en los datos técnicos.';
  if(run.state!=='completed')return;
  if(item.stage==='audio')$('modelText').textContent=run.output?.text||'No se detectó habla para transcribir.';
  if(item.stage==='text'){
    const extraction=run.output?.extraction||run.output||{};
    $('modelText').textContent='Resumen: '+(extraction.summary||'Sin resumen')+'\n\n'+
      (extraction.assertions||[]).map(x=>x.variable+': '+x.literal).join('\n');
  }
  if(item.stage==='video')$('modelText').textContent=(run.output?.fotogramas?.length||0)+' fotogramas seleccionados. '+(run.output?.audio?'Audio extraído.':'Video sin pista de audio.');
  if(item.stage==='detect'){
    $('modelText').textContent=(run.output?.objects?.length||0)+' semáforos detectados en esta imagen. Las cajas rojas muestran las detecciones del modelo, pendientes de revisión.';
    const response=await fetch('/runs/'+item.run_id+'/annotated',{headers:{Authorization:'Bearer '+token},cache:'no-store'});
    if(selectedJobId!==item.id)return;
    if(response.ok){
      const image=await response.blob();if(selectedJobId!==item.id)return;
      annotationUrl=URL.createObjectURL(image);$('annotatedImage').src=annotationUrl;$('annotatedImage').hidden=false;
    }
    else $('annotationNotice').textContent='La imagen anotada aún no está disponible.';
  }
  if(item.stage==='lights')$('modelText').textContent=(run.output?.objects||[]).map(x=>JSON.stringify(x)).join('\n')||'No hubo luces evaluables.';
}
async function refresh(){
  if(!token)return;
  const [summary,uploads,jobs]=await Promise.all([api('/summary'),api('/uploads?offset='+uploadOffset+'&limit='+pageSize),api('/jobs?offset='+jobOffset+'&limit='+pageSize)]);
  chunkSize=summary.chunk_bytes;$('conversations').textContent=summary.conversations;$('originals').textContent=summary.original_files;
  $('space').textContent=size(summary.disk_free_bytes);$('reserve').textContent='Reserva protegida: '+size(summary.disk_reserve_bytes);
  $('updated').textContent='Actualizado: '+new Date().toLocaleTimeString('es-CO');
  uploadTotal=uploads.total;jobTotal=jobs.total;
  const total=summary.tasks.reduce((n,x)=>n+x.n,0);
  const finished=summary.tasks.filter(x=>x.state==='completed'||x.state==='failed').reduce((n,x)=>n+x.n,0);
  const failed=summary.tasks.filter(x=>x.state==='failed').reduce((n,x)=>n+x.n,0);
  $('overallProgress').value=total?Math.round(100*finished/total):0;
  $('overallStatus').textContent=`${finished} de ${total} tareas conocidas finalizaron (${failed} con error). `+
    `Avance: ${total?Math.round(100*finished/total):0}%.`;
  $('uploadCount').textContent=uploadTotal+' cargas registradas';$('uploadsRows').replaceChildren();
  for(const item of uploads.items){
    const actions=document.createElement('div');
    if(['receiving','queued','error'].includes(item.state))actions.append(button('Cancelar',()=>api('/uploads/'+item.id+'/cancel',{method:'POST'})));
    if(item.state==='error')actions.append(button('Reintentar',()=>api('/uploads/'+item.id+'/retry',{method:'POST'})));
    row($('uploadsRows'),[item.original_name,Math.floor(item.received_bytes/item.size_bytes*100)+'%',states[item.state],item.error_code||'',actions]);
  }
  if(!uploads.items.length)row($('uploadsRows'),['Aún no hay cargas en esta página.','','','','']);
  $('jobsRows').replaceChildren();
  for(const item of jobs.items){
    const action=item.run_id?button(item.state==='running'?'Ver avance':'Ver salida',async()=>{await showRun(item);$('resultBox').scrollIntoView({behavior:'smooth'});}):'Pendiente';
    row($('jobsRows'),[jobSource(item),item.experiment_id,states[item.state]+(item.expansion_error?' · revisar encadenamiento':''),jobBar(item),item.attempts,action]);
    if(selectedJobId===item.id&&item.state==='running'&&selectedState==='running'){
      $('modelText').textContent=item.progress?.preview||item.progress?.phase||'En ejecución; aún no hay texto parcial.';
    }
    if(selectedJobId===item.id&&item.state!==selectedState)showRun(item).catch(e=>notice(e.message));
  }
  if(!jobs.items.length)row($('jobsRows'),['Sin tareas en esta página.','','','','','']);
  $('stageStats').replaceChildren();
  if(summary.finding_index_errors){const warning=document.createElement('span');warning.textContent=summary.finding_index_errors+' salidas de texto requieren revisar su indexación; no equivalen a cero hallazgos.';$('stageStats').append(warning);}
  for(const item of summary.tasks){const s=document.createElement('span');s.textContent=stages[item.stage]+' · '+states[item.state]+': '+item.n;$('stageStats').append(s);}
  for(const [name,offset,total] of [['Uploads',uploadOffset,uploadTotal],['Jobs',jobOffset,jobTotal]]){
    $('previous'+name).disabled=offset===0;$('next'+name).disabled=offset+pageSize>=total;
    $(name==='Uploads'?'uploadPage':'jobPage').textContent=total?`${offset+1}–${Math.min(offset+pageSize,total)} de ${total}`:'0 registros';
  }
}
async function candidates(){
  const items=[];
  for(let offset=0;;offset+=200){const result=await api('/uploads?offset='+offset+'&limit=200');items.push(...result.items.filter(x=>x.state==='receiving'));if(offset+200>=result.total)break;}
  return items;
}
async function digest(data){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(x=>x.toString(16).padStart(2,'0')).join('');}
function log(message){const li=document.createElement('li');li.textContent=message;$('uploadLog').append(li);}
$('loginForm').onsubmit=async event=>{event.preventDefault();token=$('token').value;try{await refresh();$('token').value='';$('login').hidden=true;$('workspace').hidden=false;notice('');clearInterval(timer);timer=setInterval(()=>refresh().catch(e=>notice(e.message)),5000);}catch(e){token='';notice('No se pudo entrar: '+e.message);}};
$('logout').onclick=()=>{document.dispatchEvent(new Event('sc:logout'));pause=true;token='';clearInterval(timer);clearAnnotation();selectedJobId=null;$('workspace').hidden=true;$('login').hidden=false;$('result').textContent='';$('modelText').textContent='';$('resultBox').hidden=true;notice('Sesión cerrada. Las tareas ya en cola continúan en el servidor.');};
$('pause').onclick=()=>{pause=true;$('uploadStatus').textContent='Pausando al terminar el bloque actual…';};
$('closeResult').onclick=()=>{selectedJobId=null;selectedState=null;clearAnnotation();$('resultBox').hidden=true;};
$('upload').onclick=async()=>{
  if(busy)return;
  const files=[...$('files').files],experiment=$('experiment').value.trim();
  if(!files.length||!experiment){notice('Selecciona archivos ZIP y un nombre de experimento.');return;}
  if(!crypto.subtle){notice('La carga requiere HTTPS para verificar las huellas de los archivos.');return;}
  busy=true;pause=false;$('upload').disabled=true;$('pause').disabled=false;$('files').disabled=true;$('experiment').disabled=true;
  try{
    const resumable=await candidates();
    for(let i=0;i<files.length&&!pause;i++){
      const file=files[i];let session;
      try{
        session=resumable.find(x=>x.original_name===file.name&&x.size_bytes===file.size&&x.experiment_id===experiment);
        if(session)resumable.splice(resumable.indexOf(session),1);
        else session=await api('/uploads',{method:'POST',json:{name:file.name,size:file.size,experiment_id:experiment}});
        // Reenviar/verificar bloques previos evita confiar en nombre, tamaño o fecha.
        for(let offset=0;offset<file.size;offset+=chunkSize){
          if(pause)break;
          const data=await file.slice(offset,offset+chunkSize).arrayBuffer();
          const hash=await digest(data);
          await api('/uploads/'+session.id+'/chunk?offset='+offset,{method:'PUT',headers:{'Content-Type':'application/octet-stream','X-Chunk-SHA256':hash},body:data});
          $('progress').value=(offset+data.byteLength)/file.size*100;
          $('uploadStatus').textContent=`${i+1}/${files.length} · ${file.name} · ${Math.floor($('progress').value)}% verificado y recibido`;
        }
        if(!pause){await api('/uploads/'+session.id+'/finish',{method:'POST'});log(file.name+' · en cola de importación');}
      }catch(e){log(file.name+' · '+e.message);if(e.message==='resume_content_mismatch')notice('Hay una carga incompleta con ese nombre y contenido distinto. Cancela esa carga y selecciona el ZIP correcto. No se ha sobrescrito.');}
    }
    $('uploadStatus').textContent=pause?'Subida pausada. Selecciona los mismos ZIP para reanudar; lo ya en cola sigue procesándose.':'Subida terminada. Revisa Cargas: “Importado” confirma el ingreso; no significa que el análisis haya finalizado.';
    await refresh();
  }catch(e){notice(e.message);}finally{busy=false;$('upload').disabled=false;$('pause').disabled=true;$('files').disabled=false;$('experiment').disabled=false;}
};
for(const name of ['Uploads','Jobs'])for(const direction of ['previous','next'])$(direction+name).onclick=async()=>{if(name==='Uploads')uploadOffset=Math.max(0,uploadOffset+(direction==='next'?pageSize:-pageSize));else jobOffset=Math.max(0,jobOffset+(direction==='next'?pageSize:-pageSize));try{await refresh();}catch(e){notice(e.message);}};
