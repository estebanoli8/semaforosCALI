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
    const chunkSize=4194304;
    const file=Buffer.alloc(chunkSize+23,65);
    await page.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url()),path=url.pathname;
      if(['/', '/panel.js', '/panel.css'].includes(path))return route.continue();
      if(path==='/favicon.ico')return route.fulfill({status:204});
      assert.equal(request.headers().authorization,'Bearer '+'x'.repeat(32));
      let result;
      if(path==='/summary')result={conversations:103,original_files:870,disk_free_bytes:120*1024**3,disk_reserve_bytes:3*1024**3,chunk_bytes:chunkSize,tasks:[{stage:'audio',state:'completed',n:50},{stage:'detect',state:'pending',n:100}]};
      else if(path==='/jobs')result={total:0,items:[]};
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
    mkdirSync('test-artifacts',{recursive:true});
    await page.screenshot({path:'test-artifacts/panel-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
    await page.screenshot({path:'test-artifacts/panel-mobile.png',fullPage:true});
    assert.deepEqual(await page.evaluate(()=>Object.keys(localStorage)),[]);
    await page.locator('#logout').click();
    await page.locator('#login').waitFor({state:'visible'});
    assert.deepEqual(errors,[]);
    console.log('Panel: acceso, carga de dos bloques, interrupción/reanudación, móvil y salida OK (API simulada).');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.kill());
