/* Chromium -> protected synthetic ASGI -> isolated receipts; prep responses are generated fixtures. */
'use strict';
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'upload-preparation-browser-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'upload_preparation_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let next=0,readyResolve,readyReject,bridgeError=null;const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;}),pending=new Map();
bridge.stderr.on('data',v=>process.stderr.write(v));bridge.on('error',e=>{bridgeError=e;readyReject(e);});
createInterface({input:bridge.stdout}).on('line',line=>{const m=JSON.parse(line);if(m.ready)readyResolve(m);else{pending.get(m.id)?.(m);pending.delete(m.id);}});
function rpc(message){return new Promise(resolve=>{const id=++next;pending.set(id,resolve);bridge.stdin.write(JSON.stringify({...message,id})+'\n');});}
let historyByPage=new Map(),prepMode='normal',historyFixtureMode='normal',holdNext=false,heldResolve,releaseHeld,prepHold=null;const requests=[],outside=[],pageErrors=[];
const keys=(o)=>Object.keys(o).sort().join(',');
function makePreparation(page){const history=historyByPage.get(page);if(!history)return {version:1,page,page_size:10,total:0,items:[]};
  const items=history.items.map((r,index)=>({asset_id:r.asset_id,created_at:r.created_at,bytes:r.bytes,kind:r.kind,state:r.state,library_id:r.library_id,
    processing:{stages:{preview:index===0?'pending':'finished',index:index===0?'running':'pending',faces:r.kind==='video'?'not_applicable':index===0?'finished':'unknown',caption:index===0?'unknown':'running',video_probe:r.kind==='image'?'not_applicable':'failed'},records:{image_vector:false,caption:false,face_detections:true},availability:{preview:'unknown',playback:r.kind==='image'?'not_applicable':'unknown'}}}));
  if(prepMode==='running')items[0].processing.stages.index='running';
  if(prepMode==='finished'){for(const stage of ['preview','index','faces','caption'])items[0].processing.stages[stage]='finished';}
  if(prepMode==='failure'){items[0].processing.stages.caption='failed';items[0].processing.stages.index='dead';}
  if(prepMode==='unknown'){items[0].processing.stages.preview='unknown';items[0].processing.stages.index='unknown';items[0].processing.stages.caption='unknown';}
  if(prepMode==='malformed')items[0].processing.stages.index='invented';
  if(prepMode==='badavailability')items[0].processing.availability.preview='not_applicable';
  if(prepMode==='foreign')items[0].asset_id='999999999999';
  if(prepMode==='membership-revoked'){for(const item of items){item.state='unavailable';item.library_id=null;item.processing=null;}}
  if(prepMode==='tainted')items[0].processing.caption_text='CAPTION_SENTINEL';
  const result={version:1,page,page_size:10,total:history.total,items};
  if(prepMode==='wrongpage')result.page=page+1;
  if(prepMode==='reordered')result.items.reverse();
  return result;
}
(async()=>{
 let browser,context;
 try{
  const seed=await ready;
  browser=await chromium.launch({headless:true,executablePath:process.env.PH_BROWSER_EXECUTABLE||undefined,args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1200,height:900},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());if(url.origin!=='https://photohouse.test'){outside.push(url.origin);return route.abort();}
    if(url.pathname==='/upload-preparation'&&req.method()==='GET'){
      const pageNo=Number(url.searchParams.get('page')||1);requests.push([req.method(),url.pathname,pageNo]);
      if(holdNext){holdNext=false;heldResolve?.();await new Promise(resolve=>releaseHeld=resolve);}
      if(prepMode.startsWith('unsupported'))return route.fulfill({status:Number(prepMode.slice(-3)),contentType:'application/json',body:'{}'});
      if(prepMode==='temporary')return route.fulfill({status:503,contentType:'application/json',body:'{}'});
      if(prepMode==='unauthorized')return route.fulfill({status:401,contentType:'application/json',body:'{}'});
      if(prepMode==='forbidden')return route.fulfill({status:403,contentType:'application/json',body:'{}'});
      let data=makePreparation(pageNo);if(prepMode==='malformed')data={version:1,page:pageNo,page_size:10,total:99,items:data.items};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
    }
    const headers=await req.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    let body=Buffer.from(result.body,'base64');requests.push([req.method(),url.pathname,result.status]);
    if(req.method()==='GET'&&url.pathname==='/uploads'&&result.status===200){try{const data=JSON.parse(body.toString());if(historyFixtureMode==='awaiting'&&data.items[0]){data.items[0].state='awaiting_review';data.items[0].library_id=null;body=Buffer.from(JSON.stringify(data));}historyByPage.set(data.page,data);}catch{}}
    const output={...result.headers};delete output['content-length'];delete output['content-encoding'];
    await route.fulfill({status:result.status,headers:output,body});
  });
  const page=await context.newPage();page.on('pageerror',e=>pageErrors.push(e.message));
  const refreshPreparation=async(mode)=>{prepMode=mode;const responsePromise=page.waitForResponse(response=>{const url=new URL(response.url());return url.pathname==='/upload-preparation'&&response.request().method()==='GET';});await page.locator('#my-uploads-refresh').click();return responsePromise;};
  await page.goto('https://photohouse.test/ui');
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#my-uploads-open').waitFor({state:'visible'});const initialPreparation=page.waitForResponse(response=>new URL(response.url()).pathname==='/upload-preparation'&&response.request().method()==='GET');await page.locator('#my-uploads-open').click();await initialPreparation;
  await page.locator('.receipt-card').first().waitFor();await page.locator('.upload-preparation').first().waitFor();
  await page.waitForFunction(()=>document.querySelector('.preparation-row'));
  assert.equal(requests.filter(r=>r[1]==='/upload-preparation').length,1,'status loads only after opening upload history');
  const first=page.locator('.receipt-card').first(),prep=first.locator('.upload-preparation');
  assert.match(await prep.textContent(),/预览|Preview/);assert.match(await prep.textContent(),/未知|unknown/);
  assert.match(await prep.textContent(),/可用情况|Availability/);assert.match(await prep.textContent(),/不适用|Not applicable/);
  assert.equal((await prep.textContent()).includes('ready'),false,'finished task never implies ready');
  await page.keyboard.press('Tab');
  // Native details remains keyboard operable and announces its summary.
  await prep.locator('summary').focus();await page.keyboard.press('Enter');assert.equal(await prep.evaluate(e=>e.open),true);
  await prep.locator('summary').click();await first.evaluate(e=>e.scrollIntoView({block:'center',inline:'nearest'}));await first.screenshot({path:path.join(artifacts,'upload-preparation-desktop-zh.png')});
  await page.evaluate(()=>{document.documentElement.style.zoom='150%';});await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'150% phone layout has no horizontal overflow');
  const positionPhoneCard=()=>page.locator('.receipt-card').first().evaluate(e=>{const nav=document.querySelector('.memory-navigation'),target=nav?nav.getBoundingClientRect().bottom+12:80;window.scrollBy(0,e.getBoundingClientRect().top-target);});
  await positionPhoneCard();const phoneGeometry=await page.locator('.receipt-card').first().evaluate(e=>({top:e.getBoundingClientRect().top,navBottom:document.querySelector('.memory-navigation')?.getBoundingClientRect().bottom||0,summaryTop:e.querySelector('.upload-preparation summary').getBoundingClientRect().top}));assert.ok(phoneGeometry.top>=phoneGeometry.navBottom,'receipt remains below the sticky navigation');assert.ok(phoneGeometry.summaryTop>=phoneGeometry.navBottom,'preparation summary remains visible below the sticky navigation');await page.screenshot({path:path.join(artifacts,'upload-preparation-phone-150-zh.png')});
  await prep.locator('summary').click();await prep.locator('summary').evaluate(e=>e.scrollIntoView({block:'center',inline:'nearest'}));await page.evaluate(()=>{const nav=document.querySelector('.memory-navigation'),summary=document.querySelector('.upload-preparation summary');window.scrollBy(0,summary.getBoundingClientRect().top-(nav?nav.getBoundingClientRect().bottom:0)-12);});const expandedGeometry=await prep.locator('summary').evaluate(e=>({top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom,navBottom:document.querySelector('.memory-navigation')?.getBoundingClientRect().bottom||0,navHeight:document.querySelector('.memory-navigation')?.getBoundingClientRect().height||0}));assert.ok(expandedGeometry.navHeight===0||expandedGeometry.navBottom>0,'sticky navigation remains visible while inspecting details');assert.ok(expandedGeometry.top>=expandedGeometry.navBottom,'expanded preparation summary is not covered by navigation');assert.ok(expandedGeometry.bottom<=844,'expanded summary remains within the phone viewport');await page.screenshot({path:path.join(artifacts,'upload-preparation-phone-150-expanded-zh.png')});
  await page.locator('#language').click();await page.locator('#my-uploads-panel').waitFor();
  await page.waitForFunction(()=>document.querySelector('#my-uploads-panel').open===false||document.querySelector('#my-uploads-open').hidden===false);
  const reopenAfterClose=page.waitForResponse(response=>new URL(response.url()).pathname==='/upload-preparation'&&response.request().method()==='GET');await page.locator('#my-uploads-open').click();await reopenAfterClose;await page.locator('.receipt-card').first().waitFor();await page.waitForFunction(()=>document.querySelector('.preparation-row'));
  assert.match(await page.locator('.upload-preparation').first().textContent(),/Preview|Index|Records found/);

  await refreshPreparation('running');await page.waitForFunction(()=>document.querySelector('.upload-preparation')?.textContent.includes('Running'));
  await refreshPreparation('finished');await page.waitForFunction(()=>document.querySelector('.preparation-compact')?.textContent.includes('Processing tasks finished'));
  const finishedText=await page.locator('.upload-preparation').first().textContent();assert.match(finishedText,/Finished/);assert.match(finishedText,/Not verified/);assert.equal(finishedText.toLowerCase().includes('ready'),false);
  await refreshPreparation('reordered');await page.waitForFunction(()=>document.querySelector('.upload-preparation')?.textContent.includes('Running'));assert.match(await page.locator('.receipt-card').first().locator('.preparation-row').filter({hasText:'Search task'}).textContent(),/Running/,'reordered response items attach by asset ID');
  await refreshPreparation('failure');await page.waitForFunction(()=>document.querySelector('.preparation-attention'));
  assert.match(await page.locator('.preparation-attention').first().textContent(),/upload|重新上传/i);assert.equal(await page.locator('.upload-preparation').first().getByRole('button',{name:/retry|重试/i}).count(),0);
  for(const mode of ['unknown','malformed','badavailability','foreign','wrongpage','tainted']){await refreshPreparation(mode);await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10&&document.querySelector('.upload-preparation')?.textContent.match(/unknown|unavailable|暂时无法/i));assert.equal(await page.locator('.receipt-card').count(),10);assert.match(await page.locator('.upload-preparation').first().textContent(),/unknown|Unknown|未知|unavailable|暂时无法/i);assert.equal((await page.locator('.upload-preparation').first().textContent()).includes('CAPTION_SENTINEL'),false);}
  historyFixtureMode='awaiting';await refreshPreparation('nonavailableprocessing');await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10&&document.querySelector('.upload-preparation')?.textContent.includes('unavailable'));assert.equal(await page.locator('.receipt-card').first().locator('.preparation-row').count(),0,'nonavailable receipts cannot show processing evidence');historyFixtureMode='normal';await refreshPreparation('normal');await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10&&document.querySelector('.preparation-row'));
  for(const mode of ['unsupported404','unsupported405','unsupported501','temporary']){await refreshPreparation(mode);await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10&&document.querySelector('.upload-preparation')?.textContent.match(/unavailable|not supported|暂不支持|暂时无法/i));assert.equal(await page.locator('.receipt-card').count(),10);}
  for(const mode of ['unauthorized','forbidden']){await refreshPreparation(mode);await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===0&&document.querySelector('#my-uploads-panel').open===false);prepMode='normal';await page.locator('#my-uploads-open').waitFor({state:'visible'});const reply=page.waitForResponse(response=>new URL(response.url()).pathname==='/upload-preparation'&&response.request().method()==='GET');await page.locator('#my-uploads-open').click();await reply;await page.waitForFunction(()=>document.querySelector('.preparation-row'));}
  // A delayed response from a closed panel must not repopulate protected detail.
  prepMode='normal';holdNext=true;const wasHeld=new Promise(resolve=>heldResolve=resolve);await page.locator('#my-uploads-refresh').click();await wasHeld;await page.locator('#my-uploads-panel > summary').click();releaseHeld?.();await page.waitForTimeout(50);assert.equal(await page.locator('.receipt-card').count(),0);
  const reopenedPreparation=page.waitForResponse(response=>new URL(response.url()).pathname==='/upload-preparation'&&response.request().method()==='GET');await page.locator('#my-uploads-open').click();await reopenedPreparation;await page.locator('.receipt-card').first().waitFor();await page.waitForFunction(()=>document.querySelector('.preparation-row'));
  // Page 1 preparation is held while page 2 becomes current; its response cannot replace page 2.
  holdNext=true;const pageHold=new Promise(resolve=>heldResolve=resolve);await page.locator('#my-uploads-refresh').click();await pageHold;await page.locator('#my-uploads-next').click();await page.waitForFunction(()=>document.querySelector('#my-uploads-page-label').textContent.includes('2'));await page.waitForFunction(()=>document.querySelector('.preparation-row'));releaseHeld?.();await page.waitForTimeout(50);assert.match(await page.locator('#my-uploads-page-label').textContent(),/2/);
  await page.evaluate(()=>{document.documentElement.style.zoom='100%';});await page.setViewportSize({width:1200,height:900});
  await page.locator('.upload-preparation').first().locator('summary').click();await page.locator('.receipt-card').first().evaluate(e=>e.scrollIntoView({block:'center',inline:'nearest'}));await page.locator('.receipt-card').first().screenshot({path:path.join(artifacts,'upload-preparation-desktop-en.png')});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  // Sign out while a protected status reply is pending, then switch accounts.
  holdNext=true;const accountHold=new Promise(resolve=>heldResolve=resolve);await page.locator('#my-uploads-refresh').click();await accountHold;await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});releaseHeld?.();await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#my-uploads-open').waitFor({state:'visible'});await page.locator('#my-uploads-open').click();await page.locator(`.receipt-card[data-asset="${seed.owner_asset_id}"]`).waitFor();assert.equal(await page.locator(`.receipt-card[data-asset="${seed.owner_asset_id}"]`).count(),1);assert.equal(await page.locator(`.receipt-card[data-asset="${seed.asset_ids[0]}"]`).count(),0,'the previous account receipt does not reappear after a delayed response');
  // Revoke the member while an authorized preparation request is in flight.
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#my-uploads-open').waitFor({state:'visible'});const memberPreparation=page.waitForResponse(response=>new URL(response.url()).pathname==='/upload-preparation'&&response.request().method()==='GET');await page.locator('#my-uploads-open').click();await memberPreparation;await page.waitForFunction(()=>document.querySelector('.preparation-row'));holdNext=true;const membershipHold=new Promise(resolve=>heldResolve=resolve);await page.locator('#my-uploads-refresh').click();await membershipHold;await rpc({command:'revoke-member'});prepMode='membership-revoked';releaseHeld?.();await page.waitForFunction(()=>document.querySelector('.receipt-card')&&document.querySelector('.receipt-card .upload-preparation')?.textContent.includes('unavailable'));assert.equal(await page.locator('.receipt-card').first().locator('.preparation-row').count(),0,'membership loss removes previously authorized processing details');
  assert.deepEqual(pageErrors,[]);assert.deepEqual(outside,[]);
  console.log(JSON.stringify({passed:['pending/running/finished with availability unknown','failure guidance without retry','unknown/malformed/foreign identity never leaks task data','unsupported and temporary responses preserve receipts','401 and 403 clear stale protected history','reordered preparation items match by asset ID','close, page, logout and account changes discard late responses','Chinese and English desktop and 150% phone layout','native keyboard-accessible disclosure'],artifacts,preparationRequests:requests.filter(r=>r[1]==='/upload-preparation').length}));
 }catch(error){console.error(error);process.exitCode=1;}
 finally{if(context)await context.close();if(browser)await browser.close();bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.stdin.end();}
})();
