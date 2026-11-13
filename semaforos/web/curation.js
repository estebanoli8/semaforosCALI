'use strict';
// Media are fetched privately only when opened; no video player is created.
const curatedUrls=new Set();
function cnode(tag,text){const e=document.createElement(tag);if(text)e.textContent=text;return e;}
async function privateMedia(url,element){
  const r=await fetch(url,{headers:{Authorization:'Bearer '+token}});
  if(!r.ok)throw new Error('Archivo no disponible');
  const u=URL.createObjectURL(await r.blob());curatedUrls.add(u);element.src=u;
}
const processing=$('overallProgress').closest('section');
processing.querySelector('h2').textContent='Procesamiento y resultados de los modelos';
processing.querySelector('.tag').textContent='Revisión por conversación';
const legacyJobs=$('jobsRows').closest('.tableScroll');legacyJobs.hidden=true;
$('jobPage').parentElement.hidden=true;
$('modelResultsRows').closest('section').hidden=true;
const curate=cnode('div');processing.append(curate);
const reviewer=cnode('input');reviewer.placeholder='Nombre de quien revisa';reviewer.maxLength=100;
processing.append(reviewer,button('Actualizar conversaciones',loadCuration));
for(const id of ['comparisonWorkspace','reviewWorkspace']){
  const section=$(id),details=cnode('details'),summary=cnode('summary',id==='comparisonWorkspace'?'Versiones de conversaciones':'Organizar reportes');
  section.before(details);details.append(summary,section);
}
async function loadCuration(){
  for(const url of curatedUrls)URL.revokeObjectURL(url);curatedUrls.clear();curate.replaceChildren();
  let offset=0;
  const more=button('Más conversaciones',async()=>{await page();});
  async function page(){
    const data=await api('/conversations?offset='+offset+'&limit=10');offset+=data.items.length;
    for(const conversation of data.items){
      const group=cnode('details'),title=cnode('summary',conversation.original_name),body=cnode('div');
      group.append(title,body);curate.insertBefore(group,more);
      group.ontoggle=async()=>{if(!group.open||body.childNodes.length)return;try{
        const parents=new Map();let next=0;
        do{
          const data=await api('/curation/'+conversation.id+'?offset='+next);
          for(const item of data.items){
            let target=body;
            if(item.parent_id){
              if(!parents.has(item.parent_id)){
                const d=cnode('details'),s=cnode('summary','Fotogramas y audio extraído del video'),grid=cnode('div');
                grid.className='curationGrid';d.append(s,grid);body.append(d);parents.set(item.parent_id,grid);
              }target=parents.get(item.parent_id);
            }
            const card=cnode('article');card.className='curationCard';
            card.append(cnode('h3',(stages[item.stage]||item.stage)+' · '+item.file_name),cnode('p',states[item.state]||item.state));
            if(item.modality==='frame')card.append(cnode('small','Segundo '+(item.metadata?.segundo??'—')));
            const output=item.output||{};
            const readable=cnode('div',resultVariables({...item,output_summary:item.stage==='video'?{frame_count:output.fotogramas?.length,has_audio:!!output.audio}:output}));
            readable.className='modelText';card.append(readable);
            if(item.stage==='text'){
              const original=cnode('details');original.append(cnode('summary','Mensaje original'),cnode('p',(item.payload.sources||[]).map(s=>s.text).join('\n')));card.append(original);
            }
            if(item.stage==='detect'&&item.run_id&&item.state==='completed'){
              const img=cnode('img');img.alt='Detección de semáforos';img.className='curationImage';
              const open=button('Ver foto / fotograma',async()=>{await privateMedia('/runs/'+item.run_id+'/annotated',img);});card.append(img,open);
            }
            if(item.stage==='audio'){
              const audio=cnode('audio');audio.controls=true;audio.preload='none';
              card.append(audio,button('Escuchar',async()=>{if(!audio.src)await privateMedia('/evidence/'+item.evidence_id+'/download',audio);await audio.play();}),button('1×',()=>{audio.playbackRate=1;}),button('1,5×',()=>{audio.playbackRate=1.5;}));
            }
            if(item.run_id)card.append(button('Salida del modelo',()=>showRun({...item,conversation_name:conversation.original_name})));
            if(item.state==='completed'&&item.stage!=='video'){
              const status=cnode('p',item.review?'Revisión: '+item.review.decision:'Pendiente de revisión humana');card.append(status);
              async function save(decision,text){
                if(!reviewer.value.trim())throw new Error('Escribe tu nombre como revisor.');
                const result=await api('/runs/'+item.run_id+'/curation',{method:'POST',json:{decision,reviewer:reviewer.value.trim(),text}});
                status.textContent=decision==='approved'?'Aprobado':decision==='corrected'?'Transcripción corregida. Revisar la extracción derivada.':'No evaluable';
              }
              card.append(button('Aprobar',()=>save('approved')),button('No evaluable',()=>save('not_evaluable')));
              if(item.stage==='audio'){
                const edit=cnode('details'),text=cnode('textarea');text.value=item.review?.text??output.text??'';
                edit.append(cnode('summary','Corregir transcripción'),text,button('Guardar corrección y aprobar',()=>save('corrected',text.value)));card.append(edit);
              }
            }
            target.append(card);
          }next=data.next_offset;
        }while(next!==null);
      }catch(e){body.append(cnode('p',e.message));}};
    }more.hidden=offset>=data.total;
  }
  curate.append(more);await page();
}
document.addEventListener('sc:logout',()=>{for(const u of curatedUrls)URL.revokeObjectURL(u);curatedUrls.clear();curate.replaceChildren();});
