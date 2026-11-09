// Prueba del navegador con servidor simulado: sin secretos ni datos ciudadanos.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createHash}=require('node:crypto');
const {mkdirSync}=require('node:fs');
const {chromium}=require('playwright');
const server=spawn('python',['-m','http.server','8765','--bind','127.0.0.1','--directory','semaforos/web'],{stdio:'ignore'});
(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1100}});
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    let session=null,interrupt=true,chunks=0,replays=0;
    let report=null,relation=null;
    const finding={id:'f-synthetic',variable:'ubicacion',origin:'chat',literal:'Quinta con 5',display_literal:'Quinta con 5',sent_at:'2026-11-01T15:00:00Z',source_ref:{text:'[01/11/26, 10:00] Vecina sintética: Quinta con 5, apagado.'},report_codes:[]};
    const chunkSize=4194304;
    const file=Buffer.alloc(chunkSize+23,65);
    await page.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url()),path=url.pathname;
      if(['/', '/panel.js', '/panel.css', '/review.js', '/comparison.js'].includes(path))return route.continue();
      if(path==='/favicon.ico')return route.fulfill({status:204});
      assert.equal(request.headers().authorization,'Bearer '+'x'.repeat(32));
      let result;
      if(path==='/summary')result={conversations:103,original_files:870,disk_free_bytes:120*1024**3,disk_reserve_bytes:3*1024**3,chunk_bytes:chunkSize,tasks:[{stage:'audio',state:'completed',n:50},{stage:'detect',state:'pending',n:100}]};
      else if(path==='/export-indexes')result={total:2,items:[{id:'parse-a',zip_name:'Chat.zip',chat_name:'_chat.txt'},{id:'parse-b',zip_name:'Chat (1).zip',chat_name:'_chat.txt'}]};
      else if(path==='/conversation-comparison')result={relation:'derecha_contiene_izquierda',shared_occurrences:2,requires_human_review:true};
      else if(path==='/export-relations'&&request.method()==='GET')result={total:relation?1:0,version:relation?1:0,items:relation?[relation]:[]};
      else if(path==='/export-relations'&&request.method()==='POST'){
        const body=request.postDataJSON();assert.equal(body.expected_version,0);assert.equal(body.decision,'misma_conversacion');assert.ok(body.request_id);relation={...body,version:1};result=relation;
      }
      else if(path==='/jobs')result={total:0,items:[]};
      else if(path==='/conversations')result={total:1,items:[{id:'conversation-synthetic',original_name:'Conversación sintética'}]};
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
    await page.locator('#loadReview').click();
    await page.locator('#reviewConversation').selectOption('conversation-synthetic');
    await page.locator('#loadProposals').click();
    await page.getByRole('button',{name:'Revisar estas fuentes',exact:true}).click();
    assert.equal(await page.getByRole('checkbox',{name:'Seleccionar Quinta con 5'}).isChecked(),true);
    assert.equal(report,null);
    await page.locator('#primaryFinding').selectOption(finding.id);
    await page.locator('#reportReviewer').fill('Evaluador sintético');
    await page.locator('#reportReason').fill('Primer hecho: una ubicación respaldada por el chat');
    await page.locator('#createReport').click();
    await page.locator('#reportDetailBox').waitFor({state:'visible'});
    assert.equal(report.revision,'pendiente');assert.deepEqual(report.findings,[finding]);
    assert.match(await page.locator('#reportTitle').textContent(),/R-000001/);
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
