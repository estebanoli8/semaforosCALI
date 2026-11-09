'use strict';
let exportsOffset=0,relationVersion=null,relationPair=null,relationRequest=null,relationBusy=false;
const pairQuery=()=>new URLSearchParams({left_parse_id:$('leftExport').value,right_parse_id:$('rightExport').value}).toString();
function resetComparison(){relationVersion=null;relationPair=null;relationRequest=null;$('saveRelation').disabled=true;$('comparisonResult').textContent='';$('relationHistory').textContent='';}
async function compareExports(){
  if(!$('leftExport').value||!$('rightExport').value||$('leftExport').value===$('rightExport').value)throw Error('Selecciona dos exportaciones diferentes.');
  resetComparison();const query=pairQuery();
  const [comparison,history]=await Promise.all([api('/conversation-comparison?'+query),api('/export-relations?'+query)]);
  $('comparisonResult').textContent=JSON.stringify(comparison,null,2);$('relationHistory').textContent=JSON.stringify(history,null,2);
  relationVersion=history.version;relationPair=query;$('saveRelation').disabled=false;
  if(history.items.length)$('relationDecision').value=history.items[0].decision;
}
function relationAction(id,fn){$(id).onclick=async()=>{if(relationBusy)return;relationBusy=true;
  const controls=[...$('comparisonWorkspace').querySelectorAll('button,select,input,textarea')],disabled=controls.map(x=>x.disabled);controls.forEach(x=>x.disabled=true);
  try{await fn();$('relationNotice').textContent='Operación completada. Los originales y los conteos no se modificaron.';}catch(e){$('relationNotice').textContent=e.message;}
  finally{relationBusy=false;controls.forEach((x,i)=>x.disabled=disabled[i]);$('saveRelation').disabled=relationVersion===null;}
};}
relationAction('loadExports',async()=>{
  const data=await api('/export-indexes?offset='+exportsOffset+'&limit=50');
  for(const item of data.items)for(const id of ['leftExport','rightExport']){
    if([...$(id).options].some(o=>o.value===item.id))continue;
    $(id).append(new Option(item.zip_name+' · '+item.chat_name+' · '+item.id.slice(0,8),item.id));
  }
  exportsOffset+=data.items.length;$('exportCount').textContent=` ${exportsOffset} de ${data.total}`;
});
relationAction('compareExports',compareExports);
for(const id of ['leftExport','rightExport'])$(id).onchange=resetComparison;
relationAction('saveRelation',async()=>{
  if(relationVersion===null||relationPair!==pairQuery())throw Error('Primero compara las exportaciones.');
  const data={left_parse_id:$('leftExport').value,right_parse_id:$('rightExport').value,expected_version:relationVersion,decision:$('relationDecision').value,reviewer:$('relationReviewer').value.trim(),reason:$('relationReason').value.trim()};
  if(!data.reviewer||!data.reason)throw Error('Indica revisor y motivo.');
  const signature=JSON.stringify(data);if(!relationRequest||relationRequest.signature!==signature)relationRequest={signature,id:crypto.randomUUID()};
  await api('/export-relations',{method:'POST',json:{...data,request_id:relationRequest.id}});await compareExports();
});
document.addEventListener('sc:logout',()=>{resetComparison();exportsOffset=0;for(const id of ['leftExport','rightExport'])$(id).replaceChildren(new Option('Selecciona',''));for(const id of ['relationReviewer','relationReason'])$(id).value='';$('relationNotice').textContent='';$('exportCount').textContent='';});
