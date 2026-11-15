// Prueba del navegador con servidor simulado: sin secretos ni datos ciudadanos.
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createHash}=require('node:crypto');
const {mkdirSync,readFileSync}=require('node:fs');
const {chromium}=require('playwright');
const server=spawn('python',['-m','http.server','8765','--bind','127.0.0.1','--directory','semaforos/web'],{stdio:'ignore'});
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.SC_CHROMIUM_PATH?{executablePath:process.env.SC_CHROMIUM_PATH}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1100}});
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    let session=null,interrupt=true,chunks=0,replays=0;
    const uploadedNames=[];
    let report=null,relation=null,showSyntheticJob=false,curationLabel=null,locationSaved=false,publicPin=false,mediaSession=false;
    const finding={id:'f-synthetic',variable:'ubicacion',origin:'chat',literal:'Quinta con 5',display_literal:'Quinta con 5',sent_at:'2026-11-01T15:00:00Z',source_ref:{text:'[01/11/26, 10:00] Vecina sintética: Quinta con 5, apagado.'},report_codes:[]};
    const citizen={id:'conversation-synthetic',reporter:'Ciudadana sintética',reporter_key:'citizen',
      date_from:'2026-11-03T15:00:00Z',date_to:'2026-11-14T15:00:00Z',
      episodes:[{location:'Calle 5 con Carrera 70',location_status:'cruce_explicito',inferred_fault:false,
        fields:{dano:[{code:'T',literal:'Desde hace 12 días',origin:'chat'}],gestion:[],peligro:[],ubicacion:[]}}],
      evidence_counts:{chat:1}};
    const chunkSize=4194304;
    const file=Buffer.alloc(chunkSize+23,65);
    await page.context().route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url()),path=url.pathname;
      if(['/reportes','/semaforos'].includes(path))return route.fulfill({
        contentType:'text/html',body:readFileSync('semaforos/web/reports.html')});
      if(path==='/marca-esteban.png')return route.fulfill({contentType:'image/png',body:readFileSync('semaforos/assets/logo-esteban.png')});
      if(path==='/semaforos/datos'){
        assert.equal(request.headers().authorization,undefined);
        return route.fulfill({json:{cutoff:'2026-11-14T12:00:00Z',boundary_version:null,conversations_included:1,
          totals:{records:1,crossings:1,photos:3,videos:1,audios:3,whatsapp_audios:2,video_audios:1},
          items:[{code:'P-SYNTHETIC',date:'2026-11-14T11:00:00Z',intersection:'calle 5 con carrera 70',
            description:'Falla mencionada',revision:'pendiente',processing:'completado',preliminary:true,
            reports_at_intersection:1,evidence_scope:'registro',evidence_counts:{chat:1,audio:2,audio_video:1,image:3}}],
          map:{width:720,height:430,markers:publicPin?[{code:'P-SYNTHETIC',x:360,y:250}]:[],polygons:[],grid:[]}}});
      }
      if(['/', '/panel.js', '/panel.css', '/review.js', '/comparison.js','/curation.js','/curation.css',
          '/team.js','/metrics.html','/metrics.js','/metrics.css','/reports.js','/reports.css'].includes(path))return route.continue();
      if(path==='/favicon.ico')return route.fulfill({status:204});
      if(path==='/report-media/session'){
        if(request.method()==='DELETE'){mediaSession=false;return route.fulfill({status:204});}
        assert.equal(request.headers().authorization,'Bearer '+'x'.repeat(32));
        mediaSession=true;return route.fulfill({status:204});
      }
      if(path==='/team-session')return route.fulfill({status:mediaSession?200:401,json:{active:mediaSession}});
      if(path.startsWith('/report-media/')) {
        if(!mediaSession) return route.fulfill({status:401});
        if(['/report-media/records/P-SYNTHETIC','/report-media/conversations/conversation-synthetic'].includes(path)){
          return route.fulfill({json:{scope:'registro',intersection:'Calle 5 con Carrera 70',
            situacion_presentada:'Se reporta una falla.',
            ...(path.includes('/conversations/')?citizen:{}),
            items:[['text','chat','chat-sintético.txt'],['image','image','foto-sintética.jpg'],
              ['audio','audio','voz-sintética.ogg'],['video','video','video-sintético.mp4']]
              .map(([id,type,name])=>({id,type,name,content:'/report-media/files/'+id+'/content',
                download:'/report-media/files/'+id+'/download',thumbnail:type==='image'?'/marca-esteban.png':undefined,
                analysis:type==='chat'?{state:'completed',summaries:['Se identificó un cruce'],run_id:'run-synthetic',evaluations:[{run_id:'run-synthetic'}]}:
                  type==='audio'?{state:'failed',error:'adapter_failed'}:undefined,
                transcription:type==='video'?{state:'completed',text:'Transcripción sintética del video'}:undefined}))}});
        }
        if(path==='/report-media/files/text/content')return route.fulfill({contentType:'text/plain; charset=utf-8',
          body:'Primera línea del chat\nÚltima línea del chat'});
        if(path==='/report-media/files/text/download')return route.fulfill({contentType:'application/octet-stream',
          body:'Texto original'});
        return route.fulfill({status:404});
      }
      assert.equal(request.headers().authorization,undefined);
      assert.equal(mediaSession,true);
      let result;
      if(path==='/summary')result={conversations:103,original_files:870,disk_free_bytes:120*1024**3,disk_reserve_bytes:3*1024**3,chunk_bytes:chunkSize,tasks:showSyntheticJob?[{stage:'detect',state:'completed',n:1},{stage:'text',state:'running',n:1}]:[{stage:'audio',state:'completed',n:50},{stage:'detect',state:'pending',n:100}]};
      else if(path==='/model-metrics'){
        const filtered=url.searchParams.get('experiment')==='test';
        result={stages:[{stage:'audio',models:['Whisper Small'],completed:filtered?1:3,partial:0,
          failed:0,pending:0,running:0,excluded:0,seconds_p50:2.5,seconds_p90:4,time_samples:3,
          quality_samples:1,word_errors:2,reference_words:8}],
          as_of:'2026-11-14T10:00:00-05:00',chart_days:['2026-11-13','2026-11-14'],
          daily:[{day:'2026-11-14',stage:'audio',results:1,failed:0}],errors:[],experiments:['test']};
      }
      else if(path==='/detailed-records'){
        result={cutoff:'2026-11-14T12:00:00Z',items:[citizen]};
      }
      else if(path==='/action-records'){
        result={cutoff:'2026-11-14T12:00:00Z',map:null,conversations_included:1,totals:{records:1,crossings:1},
          items:[{code:'P-SYNTHETIC',date:'2026-11-14T11:00:00Z',intersection:'calle 5 con carrera 70',
            description:'Se reporta una falla.',reports_at_intersection:1,evidence_scope:'registro',evidence_counts:{chat:1}}]};
      }
      else if(path==='/reviews'&&request.method()==='POST'){
        const body=request.postDataJSON();
        if(body.field==='semantic_fields')assert.deepEqual(body.label.dano,{observed:true,detected:false});
        else {assert.equal(body.field,'location_detected');assert.equal(body.label,false);}
        result={id:'review-synthetic'};
      }
      else if(path==='/report-map'){
        result={cutoff:'2026-11-14T12:00:00Z',boundary_version:'test',map:{width:720,height:430,
          markers:locationSaved?[{code:'R-000001',x:360,y:250}]:[],polygons:[],grid:[]},
          items:[{id:'report-synthetic',code:'R-000001',version:1,map_version:locationSaved?1:0,
            date:'2026-11-01T15:00:00Z',intersection:'Calle 5 con Carrera 70',description:'Semáforo reportado apagado',
            revision:'pendiente',processing:'completado',reports_at_intersection:1,
            latitude:locationSaved?3.432:null,longitude:locationSaved?-76.531:null,
            published:false,evidence:[],coordinates_candidates:[{latitude:3.432,longitude:-76.531}]}]};
      }
      else if(path==='/reports/report-synthetic/map'){
        const body=request.postDataJSON(); assert.equal(body.latitude,3.432);assert.equal(body.published,false);
        locationSaved=true;result={version:1};
      }
      else if(path==='/report-exports')return route.fulfill({contentType:'application/pdf',
        headers:{'X-Report-Export-ID':'example-cut'},body:Buffer.from('%PDF-1.4')});
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
        uploadedNames.push(body.name);
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
    const chosenNames = await page.evaluate(() => selectZipVersions([
      {name:'Chat (1).zip'}, {name:'Chat (10).ZIP'}, {name:'Chat (2).zip'},
      {name:'Chat.zip'}, {name:'Otra conversación.zip'}, {name:'Incidente (Sur).zip'}
    ]).map(group => group.winner.name));
    assert.deepEqual(chosenNames,['Chat (10).ZIP','Otra conversación.zip','Incidente (Sur).zip']);
    await page.locator('#files').setInputFiles([
      {name:'Conversación sintética (1).zip',mimeType:'application/zip',buffer:Buffer.from('older')},
      {name:'Conversación sintética (3).zip',mimeType:'application/zip',buffer:file},
      {name:'Conversación sintética.zip',mimeType:'application/zip',buffer:Buffer.from('base')},
      {name:'Conversación sintética (2).zip',mimeType:'application/zip',buffer:Buffer.from('old')}
    ]);
    assert.match(await page.locator('#zipSelection').textContent(),/1 ZIP para subir · 3 versiones repetidas omitidas/);
    await page.locator('#upload').click();
    await page.waitForFunction(()=>!document.getElementById('upload').disabled);
    assert.equal(session.received_bytes,chunkSize);assert.equal(session.state,'receiving');
    await page.locator('#upload').click();
    await page.waitForFunction(()=>!document.getElementById('upload').disabled);
    assert.equal(session.state,'queued');assert.equal(replays,1);assert.equal(chunks,3);
    assert.deepEqual(uploadedNames,['Conversación sintética (3).zip']);
    assert.match(await page.locator('#uploadLog').textContent(),/Conversación sintética \(2\)\.zip · omitido/);
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
    await page.goto('http://127.0.0.1:8765/metrics.html');
    assert.equal(await page.locator('#metricsWorkspace').isVisible(),false);
    await page.getByLabel('Clave de acceso del equipo').fill('x'.repeat(32));
    await page.getByRole('button',{name:'Entrar',exact:true}).click();
    await page.getByText('WER · tasa de error de palabras').waitFor();
    assert.match(await page.locator('#metricsContent').textContent(),/25 %/);
    assert.equal(await page.locator('#metricsContent').getByRole('img').count(),2);
    const filtered=page.waitForResponse(resp=>resp.url().includes('/model-metrics?experiment=test'));
    await page.locator('#metricsExperiment').selectOption('test');
    await filtered;
    await page.waitForFunction(()=>document.querySelector('.metrics-list b')?.textContent==='1');
    await page.locator('#metricsDailyStage').selectOption('text');
    await page.getByText('Sin resultados finalizados en las fechas del gráfico.').waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
    await page.screenshot({path:'test-artifacts/metrics-mobile.png',fullPage:true});
    await page.getByRole('button',{name:'Salir',exact:true}).click();
    await page.locator('#login').waitFor({state:'visible'});
    assert.equal(await page.locator('#metricsContent').textContent(),'');
    assert.deepEqual(errors,[]);
    await page.goto('http://127.0.0.1:8765/reportes?ubicaciones=1');
    await page.locator('#reportKey').fill('x'.repeat(32));
    await page.getByRole('button',{name:'Entrar',exact:true}).click();
    await page.getByRole('button',{name:'R-000001',exact:true}).click();
    await page.getByRole('button',{name:/Usar GPS sugerido/}).click();
    await page.locator('#mapReviewer').fill('Evaluador sintético');
    await page.getByRole('button',{name:'Guardar ubicación y visibilidad'}).click();
    await page.locator('.map-pin').waitFor();
    const pdfDownload=page.waitForEvent('download');
    await page.getByRole('button',{name:'Descargar informe PDF'}).click();
    assert.equal((await pdfDownload).suggestedFilename(),'semaforos-cali-example-cut.pdf');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    await page.screenshot({path:'test-artifacts/reports-mobile.png',fullPage:true});
    await page.goto('http://127.0.0.1:8765/reportes');
    await page.getByText('Desde cuándo está dañado · Desde hace 12 días',{exact:false}).waitFor();
    await page.getByText('noviembre / 03 / 2026 – noviembre / 14 / 2026').waitFor();
    assert.equal(await page.locator('#recordsPanel thead th:visible').count(),3);
    assert.equal(await page.getByRole('link',{name:'Reporte',exact:true}).count(),0);
    assert.equal(await page.locator('#mapPanel').isVisible(),false);
    assert.equal(await page.locator('#reportLogin').isVisible(),false);
    await page.getByText('1 archivo',{exact:true}).click();
    const popup = page.waitForEvent('popup');
    await page.getByRole('link',{name:'1 chat TXT'}).click();
    const detail=await popup;
    await detail.getByText('Se identificó un cruce',{exact:true}).waitFor();
    await detail.getByText('Transcripción sintética del video',{exact:true}).waitFor();
    assert.equal(await detail.locator('#reportLogin').isVisible(),false);
    const form=detail.locator('#files-chat .evidence-review');
    await form.locator('fieldset').first().getByRole('checkbox',{name:'Observado',exact:true}).check();
    const save=form.getByRole('button',{name:'Guardar evaluación',exact:true});
    await save.click();
    await detail.getByText('Evaluación guardada',{exact:true}).waitFor();
    assert.equal(await save.evaluate(button=>button.classList.contains('saved')),true);
    assert.equal(new URL(page.url()).pathname,'/reportes');
    await detail.close();
    await page.goto('http://127.0.0.1:8765/semaforos');
    await page.getByText('1 conversación incluida',{exact:true}).waitFor();
    assert.match(await page.locator('#reportStats').textContent(),/Fotos3Videos1Audios3/);
    assert.match(await page.locator('#reportStats').textContent(),/Cruces identificados1/);
    await page.getByText('calle 5 con carrera 70',{exact:true}).waitFor();
    assert.equal(await page.locator('#recordCodeHeader').isVisible(),false);
    assert.equal(await page.locator('#recordStateHeader').isVisible(),false);
    await page.getByText('Registros en este cruce',{exact:true}).first().waitFor();
    assert.ok(await page.evaluate(()=>document.getElementById('recordsPanel')
      .compareDocumentPosition(document.getElementById('mapPanel')) & Node.DOCUMENT_POSITION_FOLLOWING));
    assert.equal(await page.locator('#pdfPanel').isVisible(),false);
    assert.ok(await page.getByAltText('Ingeniero Esteban Oli').evaluate(img=>img.complete && img.naturalWidth>0));
    await page.getByText('7 archivos',{exact:true}).click();
    await page.getByRole('link',{name:'2 audios de WhatsApp',exact:true}).waitFor();
    await page.getByRole('link',{name:'1 audio extraído de video',exact:true}).waitFor();
    await page.getByRole('link',{name:'3 fotos',exact:true}).waitFor();
    const target=await page.getByRole('link',{name:'1 chat TXT',exact:true}).getAttribute('href');
    publicPin=true;
    await page.getByRole('button',{name:'Actualizar',exact:true}).click();
    await page.locator('.map-pin').waitFor();
    assert.ok(await page.evaluate(()=>document.getElementById('mapPanel')
      .compareDocumentPosition(document.getElementById('recordsPanel')) & Node.DOCUMENT_POSITION_FOLLOWING));
    mediaSession=false;
    await page.goto('http://127.0.0.1:8765'+target);
    await page.locator('#reportLogin').waitFor({state:'visible'});
    assert.equal(await page.locator('#evidenceAccess').isVisible(),false);
    await page.locator('#reportKey').fill('x'.repeat(32));
    await page.getByRole('button',{name:'Entrar',exact:true}).click();
    await page.getByText('Última línea del chat',{exact:false}).waitFor();
    await page.locator('#files-image img').waitFor();
    assert.equal(await page.locator('#evidenceAccess audio').count(),1);
    assert.equal(await page.locator('#evidenceAccess video').count(),1);
    await page.locator('#files-audio').getByRole('button',{name:'1,5×',exact:true}).click();
    await page.locator('#files-video').getByRole('button',{name:'2×',exact:true}).click();
    assert.equal(await page.locator('#files-audio audio').evaluate(el=>el.playbackRate),1.5);
    assert.equal(await page.locator('#files-video video').evaluate(el=>el.playbackRate),2);
    const original=page.waitForEvent('download');
    await page.locator('#files-chat').getByRole('link',{name:'Descargar original',exact:true}).click();
    assert.equal((await original).suggestedFilename(),'chat-sintético.txt');
    await page.goto('http://127.0.0.1:8765'+target.replace('tipo=chat','tipo=video'));
    await page.locator('#files-video').waitFor({state:'visible'});
    assert.equal(await page.locator('#reportLogin').isVisible(),false);
    await page.locator('#evidenceLogout').click();
    await page.locator('#reportLogin').waitFor({state:'visible'});
    assert.equal(await page.locator('#evidenceFiles').textContent(),'');
    assert.deepEqual(errors,[]);
    console.log('Panel: acceso, carga interrumpida/reanudada, agrupación explícita en reporte, móvil y salida OK (API simulada).');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.kill());
