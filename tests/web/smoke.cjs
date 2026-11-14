// Prueba del navegador con servidor simulado: sin secretos ni datos ciudadanos.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createHash}=require('node:crypto');
const {mkdirSync}=require('node:fs');
const {chromium}=require('playwright');
const server=spawn('python',['-m','http.server','8765','--bind','127.0.0.1','--directory','semaforos/web'],{stdio:'ignore'});
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.SC_CHROMIUM_PATH?{executablePath:process.env.SC_CHROMIUM_PATH}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1100}});
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    let session=null,interrupt=true,chunks=0,replays=0;
    let report=null,relation=null,showSyntheticJob=false,curationLabel=null;
    const finding={id:'f-synthetic',variable:'ubicacion',origin:'chat',literal:'Quinta con 5',display_literal:'Quinta con 5',sent_at:'2026-11-01T15:00:00Z',source_ref:{text:'[01/11/26, 10:00] Vecina sintética: Quinta con 5, apagado.'},report_codes:[]};
    const chunkSize=4194304;
    const file=Buffer.alloc(chunkSize+23,65);
    await page.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url()),path=url.pathname;
      if(['/', '/panel.js', '/panel.css', '/review.js', '/comparison.js','/curation.js','/curation.css'].includes(path))return route.continue();
      if(path==='/favicon.ico')return route.fulfill({status:204});
      assert.equal(request.headers().authorization,'Bearer '+'x'.repeat(32));
      let result;
      if(path==='/summary')result={conversations:103,original_files:870,disk_free_bytes:120*1024**3,disk_reserve_bytes:3*1024**3,chunk_bytes:chunkSize,tasks:showSyntheticJob?[{stage:'detect',state:'completed',n:1},{stage:'text',state:'running',n:1}]:[{stage:'audio',state:'completed',n:50},{stage:'detect',state:'pending',n:100}]};
      else if(path==='/export-indexes')result={total:2,items:[{id:'parse-a',zip_name:'Chat.zip',chat_name:'_chat.txt'},{id:'parse-b',zip_name:'Chat (1).zip',chat_name:'_chat.txt'}]};
      else if(path==='/conversation-comparison')result={relation:'derecha_contiene_izquierda',shared_occurrences:2,requires_human_review:true};
      else if(path==='/export-relations'&&request.method()==='GET')result={total:relation?1:0,version:relation?1:0,items:relation?[relation]:[]};
      else if(path==='/export-relations'&&request.method()==='POST'){
        const body=request.postDataJSON();assert.equal(body.expected_version,0);assert.equal(body.decision,'misma_conversacion');assert.ok(body.request_id);relation={...body,version:1};result=relation;
      }
      else if(path==='/jobs')result=showSyntheticJob?{total:2,items:[
        {id:'job-frame',stage:'detect',state:'completed',attempts:1,run_id:'run-frame',file_name:'frame-01.jpg',parent_name:'video-sintetico.mp4',conversation_name:'Chat sintético.zip',modality:'frame',evidence_metadata:{segundo:2},experiment_id:'synthetic'},
        {id:'job-text',stage:'text',state:'running',attempts:1,run_id:'run-text',file_name:'_chat.txt',conversation_name:'Chat sintético.zip',modality:'chat',progress:{phase:'Generando JSON',preview:'{"summary":"Quinta con 5"'},experiment_id:'synthetic'}]}:{total:0,items:[]};
      else if(['/runs/run-frame/annotated','/runs/run-frame/thumbnail'].includes(path))return route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lV0AAAAASUVORK5CYII=','base64')});
      else if(path==='/runs/run-frame')result={id:'run-frame',state:'completed',output:{objects:[{bbox:[1,2,3,4]}]}};
      else if(path==='/runs/run-text')result={id:'run-text',state:'running',output:null};
      else if(path==='/conversations')result={total:2,items:[{id:'conversation-synthetic',original_name:'Conversación sintética'},{id:'other',original_name:'Otra conversación sintética'}]};
      else if(path==='/conversations/conversation-synthetic/micro-report')result={reporters:[{
        reporter:'Vecina sintética',reported_estimate:1,explicit_quantities:[1],locations:[],
        gps:[{latitude:3.432,longitude:-76.531,origin:'chat'}],durations:[],mentions:[]}]};
      else if(path==='/conversations/other/micro-report')result={reporters:[]};
      else if(path==='/curation/other')result={next_offset:null,items:[]};
      else if(path==='/report-statistics')result={conversations_analyzed:2,conversations_with_mentions:1,
        reporter_groups:1,groups_with_gps:1,groups_with_duration:0,groups_with_count:1,topics:{falla_mencionada:1}};
      else if(path==='/curation/conversation-synthetic')result={next_offset:null,items:[
        {id:'job-frame',stage:'detect',state:'completed',run_id:'run-frame',file_name:'frame-01.jpg',parent_id:'video-synthetic',parent_name:'video-sintetico.mp4',modality:'frame',metadata:{segundo:2},payload:{},output:{objects:[{bbox:[1,2,3,4],score:0.9}]}},
        {id:'job-audio',stage:'audio',state:'completed',run_id:'run-audio',file_name:'audio.ogg',evidence_id:'audio-synthetic',modality:'audio',payload:{},output:{text:'Quinta con seis'},review:curationLabel},
        {id:'job-text',stage:'text',state:'running',run_id:'run-text',file_name:'_chat.txt',modality:'chat',payload:{sources:[{text:'Quinta con 5'}]},progress:{phase:'Generando JSON',preview:'Quinta con 5'}}]};
      else if(path==='/runs/run-audio/curation'){
        curationLabel=request.postDataJSON();assert.equal(curationLabel.reviewer,'Revisora de prueba');
        result={saved:true,job_ids:curationLabel.decision==='corrected'?['corrected-text']:[]};
      }
      else if(path==='/report-proposals')result={total:1,items:[{status:'candidato_revisable',reasons:[],findings:[finding],primary_finding_id:finding.id,existing_reports:[],related_reports:[]}]};
      else if(path==='/findings')result={total:1,items:[finding]};
      else if(path==='/reports'&&request.method()==='GET')result={total:report?1:0,active:report?1:0,items:report?[report]:[]};
      else if(path==='/reports'&&request.method()==='POST'){
        const body=request.postDataJSON();assert.equal(body.action,'create');assert.deepEqual(body.finding_ids,[finding.id]);assert.equal(body.primary_finding_id,finding.id);assert.equal(body.reviewer,'Evaluador sintético');assert.ok(body.request_id);
        report={id:'report-synthetic',code:1,code_display:'R-000001',version:1,revision:'pendiente',primary_finding_id:finding.id,findings:[finding],summary:null};finding.report_codes=[1];
        result={id:report.id,code:report.code_display,version:1,revision:'pendiente'};
      }else if(path==='/reports/report-synthetic')result=report;
      else if(path==='/uploads'&&request.method()==='GET')result={total:session?1:0,items:session?[session]:[]};
      else if(path==='/uploads'&&request.method()==='POST'){
        const body=request.postDataJSON();assert.equal(body.experiment_id,'exploracion-local-v1');
        session={id:'synthetic-id',original_name:body.name,size_bytes:body.size,received_bytes:0,state:'receiving',experiment_id:body.experiment_id};result=session;
      }else if(path.endsWith('/chunk')){
        const data=request.postDataBuffer(),offset=Number(url.searchParams.get('offset'));
        assert.equal(request.headers()['x-chunk-sha256'],createHash('sha256').update(data).digest('hex'));
        assert.ok(data.length<=chunkSize);assert.deepEqual(data,file.subarray(offset,offset+data.length));
        if(offset===chunkSize&&interrupt){interrupt=false;return route.abort('connectionreset');}
        if(offset<session.received_bytes)replays++;else session.received_bytes+=data.length;
        chunks++;result=session;
      }else if(path.endsWith('/finish')){
        assert.equal(session.received_bytes,file.length);session.state='queued';result=session;
      }else throw new Error('Ruta inesperada '+path);
      await route.fulfill({json:result});
    });
    for(let i=0;i<30;i++){
      try{await page.goto('http://127.0.0.1:8765');break;}catch(e){if(i===29)throw e;await new Promise(r=>setTimeout(r,100));}
    }
    await page.locator('#token').fill('x'.repeat(32));await page.getByRole('button',{name:'Entrar',exact:true}).click();
    await page.locator('#workspace').waitFor({state:'visible'});
    assert.equal(await page.locator('#conversations').textContent(),'103');
    await page.locator('#files').setInputFiles({name:'Conversación sintética (1).zip',mimeType:'application/zip',buffer:file});
    await page.locator('#upload').click();
    await page.waitForFunction(()=>!document.getElementById('upload').disabled);
    assert.equal(session.received_bytes,chunkSize);assert.equal(session.state,'receiving');
    await page.locator('#upload').click();
    await page.waitForFunction(()=>!document.getElementById('upload').disabled);
    assert.equal(session.state,'queued');assert.equal(replays,1);assert.equal(chunks,3);
    showSyntheticJob=true;await page.evaluate(()=>refresh());
    assert.match(await page.locator('#overallStatus').textContent(),/1 de 2 tareas conocidas/);
    assert.equal(await page.locator('#overallProgress').getAttribute('value'),'50');
    assert.match(await page.locator('#jobsRows').textContent(),/video-sintetico.mp4 · segundo 2/);
    await page.getByText('Conversación sintética',{exact:true}).click();
    await page.getByText('Video: video-sintetico.mp4 · fotogramas y audio',{exact:true}).click();
    await page.locator('.curationImage').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>document.querySelector('.curationImage')?.src.startsWith('blob:'));
    assert.equal(await page.locator('video').count(),0);
    await page.getByRole('button',{name:'Ampliar imagen'}).click();
    await page.locator('#annotatedImage').waitFor({state:'visible'});
    await page.getByRole('button',{name:'Cerrar',exact:true}).click();
    await page.locator('[data-job-id="job-text"]').getByRole('button',{name:'Salida del modelo'}).click();
    assert.match(await page.locator('#modelText').textContent(),/Quinta con 5/);
    await page.getByRole('button',{name:'Cerrar',exact:true}).click();
    await page.getByLabel('Nombre de quien revisa',{exact:true}).fill('Revisora de prueba');
    const audioCard=page.locator('[data-job-id="job-audio"]');
    await audioCard.getByText('Corregir transcripción',{exact:true}).click();
    await page.getByLabel('Transcripción corregida').fill('Quinta con cinco');
    await page.evaluate(()=>refresh());
    assert.equal(await page.getByLabel('Transcripción corregida').inputValue(),'Quinta con cinco');
    await audioCard.getByRole('button',{name:'1,5×',exact:true}).click();
    assert.equal(await audioCard.locator('audio').evaluate(a=>a.playbackRate),1.5);
    await audioCard.getByRole('button',{name:'Guardar corrección y aprobar'}).click();
    assert.equal(curationLabel.text,'Quinta con cinco');assert.equal(curationLabel.decision,'corrected');
    await page.getByRole('link',{name:'3.432, -76.531'}).waitFor({state:'visible'});
    await page.getByText('Otra conversación sintética',{exact:true}).click();
    await page.waitForFunction(()=>document.querySelectorAll('.curationConversation[open]').length===1);
    assert.equal(await page.locator('.curationConversation[open] > summary').textContent(),'Otra conversación sintética');
    await page.locator('#refreshReportStats').click();
    await page.waitForFunction(()=>document.getElementById('reportStatistics').textContent.includes('Grupos con GPS · 1'));
    await page.getByText('Organizar reportes',{exact:true}).click();
    await page.locator('#loadReview').click();
    await page.locator('#reviewConversation').selectOption('conversation-synthetic');
    await page.locator('#loadProposals').click();
    await page.getByRole('button',{name:'Revisar estas fuentes',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#findingRows input[type="checkbox"]')?.checked===true);
    assert.equal(await page.getByRole('checkbox',{name:'Seleccionar Quinta con 5'}).isChecked(),true);
    assert.equal(report,null);
    await page.locator('#primaryFinding').selectOption(finding.id);
    await page.locator('#reportReviewer').fill('Evaluador sintético');
    await page.locator('#reportReason').fill('Primer hecho: una ubicación respaldada por el chat');
    await page.locator('#createReport').click();
    await page.locator('#reportDetailBox').waitFor({state:'visible'});
    assert.equal(report.revision,'pendiente');assert.deepEqual(report.findings,[finding]);
    assert.match(await page.locator('#reportTitle').textContent(),/R-000001/);
    await page.getByText('Versiones de conversaciones',{exact:true}).click();
    await page.locator('#loadExports').click();
    await page.locator('#leftExport').selectOption('parse-a');await page.locator('#rightExport').selectOption('parse-b');
    await page.locator('#compareExports').click();await page.waitForFunction(()=>!document.getElementById('saveRelation').disabled);
    await page.locator('#relationReviewer').fill('Equipo');await page.locator('#relationReason').fill('Comparado con originales');
    await page.locator('#relationDecision').selectOption('misma_conversacion');await page.locator('#saveRelation').click();
    await page.waitForFunction(()=>document.getElementById('relationHistory').textContent.includes('misma_conversacion'));
    assert.equal(relation.version,1);
    mkdirSync('test-artifacts' ,{recursive:true});
    await page.screenshot({path:'test-artifacts/panel-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
    await page.screenshot({path:'test-artifacts/panel-mobile.png',fullPage:true});
    assert.deepEqual(await page.evaluate(()=>Object.keys(localStorage)),[]);
    await page.locator('#logout').click();
    await page.locator('#login').waitFor({state:'visible'});
    assert.deepEqual(errors,[]);
    console.log('Panel: acceso, carga interrumpida/reanudada, agrupación explícita en reporte, móvil y salida OK (API simulada).');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.kill());
