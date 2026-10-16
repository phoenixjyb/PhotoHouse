/* Scene workspace against synthetic identities, vectors and mock encoder only. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-workspace-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'../.venv/bin/python'),[path.join(__dirname,'assistant_workspace_browser_bridge.py')],{cwd:root,env:{...process.env,PH_SCENE_FIXTURE:'1'},stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pendingRpc=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const call=pendingRpc.get(result.id);if(call){pendingRpc.delete(result.id);call.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Browser bridge exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Browser bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const browserRequests=[],pageErrors=[],checkpoints=[],blockedOrigins=[];
let loseNextTurn=false,loseNextTurnBeforeServer=false,loseNextCreationBeforeServer=false,holdNextTurn=null,releaseHeldTurn=null;
function gateTurn(){let arrive,release;const seen=new Promise(resolve=>{arrive=resolve;});const released=new Promise(resolve=>{release=resolve;});releaseHeldTurn=release;holdNextTurn={arrive,released};return {seen,release:()=>{releaseHeldTurn=null;release();}};}
function checkpoint(text){checkpoints.push(text);console.log('PASS '+text);}
function body(response){return JSON.parse(Buffer.from(response.body,'base64').toString());}
let browser,context,phoneContext,page;
async function installSyntheticTransport(targetContext){
  await targetContext.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){blockedOrigins.push(url.origin);await route.abort();return;}
    const entry={method:request.method(),path:url.pathname+url.search,headers:await request.allHeaders(),body:request.postData()||'',serverReached:false};browserRequests.push(entry);
    if(entry.method==='POST'&&url.pathname==='/assistant/workspace/v1/threads'&&loseNextCreationBeforeServer){
      loseNextCreationBeforeServer=false;entry.droppedBeforeServer=true;await route.abort('failed');return;
    }
    if(entry.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&loseNextTurnBeforeServer){
      loseNextTurnBeforeServer=false;entry.droppedBeforeServer=true;await route.abort('failed');return;
    }
    const headers={...entry.headers};delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    entry.serverReached=true;
    const response=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    entry.status=response.status;
    try{entry.response=body(response);}catch{}
    if(entry.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&holdNextTurn){
      const gate=holdNextTurn;holdNextTurn=null;gate.arrive();await gate.released;
    }
    if(entry.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&loseNextTurn){
      loseNextTurn=false;await route.abort('failed');return;
    }
    const outputHeaders={...response.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try{await route.fulfill({status:response.status,headers:outputHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  await targetContext.addInitScript(()=>{
    window.__phSpeechCalls=0;
    try{Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak(){window.__phSpeechCalls++;},cancel(){},get speaking(){return false;}}});}catch{}
  });
}
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});context.setDefaultTimeout(15000);await installSyntheticTransport(context);
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#grid .asset').first().waitFor();
  await page.locator('[href="#assistant-panel"]').first().click();
  await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  await page.locator('#assistant-private-new').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-private-select')?.value&&!document.querySelector('#assistant-private-new').disabled);
  const turns=()=>browserRequests.filter(x=>x.method==='POST'&&/\/threads\/[0-9a-f-]+\/turns$/.test(new URL(x.path,'https://photohouse.test').pathname));
  const ordinary=async text=>{
    if(await page.locator('#assistant-scene').evaluate(el=>el.open)&&await page.locator('#assistant-scene-back').isVisible())await page.locator('#assistant-scene-back').click();
    const n=turns().length;await page.locator('#assistant-text').fill(text);await page.locator('#assistant-send').click();
    await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);assert.equal(turns().length,n+1);return turns().at(-1);
  };
  const reopen=async(id=null)=>{
    if(!await page.locator('#assistant-private-management').evaluate(el=>el.open))await page.locator('#assistant-private-management-toggle').click();
    const selected=id||await page.locator('#assistant-private-select').inputValue();
    const response=page.waitForResponse(r=>r.request().method()==='GET'&&/\/threads\/[0-9a-f-]+$/.test(new URL(r.url()).pathname));
    await page.locator('#assistant-private-select').selectOption(selected);await response;
    await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  };
  const submitScene=async text=>{
    if(!await page.locator('#assistant-scene').evaluate(el=>el.open))await page.locator('#assistant-scene > summary').click();
    await page.locator('#assistant-scene-text').fill(text);await page.locator('#assistant-scene-confirm').check();await page.locator('#assistant-scene-send').click();
    await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);return turns().at(-1);
  };
  await ordinary('找示例儿童在2026年的照片');
  await page.locator('#assistant-scene').waitFor({state:'visible'});await page.locator('#assistant-scene > summary').click();
  assert.match(await page.locator('#assistant-scene-scope').innerText(),/示例儿童/);assert.match(await page.locator('#assistant-scene-scope').innerText(),/2026-01-01/);
  await page.locator('#assistant-scene-text').fill('孩子 flying a kite 蓝桥旁');assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);
  await page.locator('#assistant-scene-confirm').check();assert.equal(await page.locator('#assistant-scene-send').isEnabled(),true);
  await page.locator('#assistant-scene-text').fill('中'.repeat(171));assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);
  await page.locator('#assistant-scene-text').fill('a kite\nblue bridge');assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);
  checkpoint('Scene input shows reviewed person/date/photo conditions, requires acknowledgement, and rejects overflow and multiline wording');
  const search=await submitScene('孩子 flying a kite 蓝桥旁');
  assert.equal(search.status,200,JSON.stringify(search.response));assert.equal(search.headers['x-photohouse-search-version'],'4');assert.deepEqual(JSON.parse(search.body).accepts,['scene_search_v1']);
  assert.deepEqual(search.response.result.items.map(x=>x.id),['102','101']);assert.equal(search.response.result.filters.people.ids[0],'301');assert.equal(search.response.result.filters.date.from,'2026-01-01');
  await page.locator('#assistant-scene-ranking').waitFor({state:'visible'});assert.match(await page.locator('#assistant-scene-ranking').innerText(),/近似排序/);
  assert.equal(await page.locator('.assistant-scene-rank').count(),2);assert.equal(await page.locator('#assistant-speech').isVisible(),false);assert.equal(await page.locator('#viewer').isVisible(),false);
  assert.equal(await page.locator('#assistant-scene-confirm').isChecked(),false);
  await page.locator('#assistant-scene-ranking').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-desktop-zh.png'),fullPage:false});
  checkpoint('Explicit mixed-language scene turn preserves hard filters, shows approximate ranking separately, and performs no speech/open action');
  const english=await submitScene('a child flying a kite beside a blue bridge');assert.equal(english.response.result.context.scene.query,'a child flying a kite beside a blue bridge');
  // Start another explicit scene request, lose its response, then disable encoding.
  loseNextTurn=true;const before=turns().length;
  const failed=page.waitForEvent('requestfailed',{predicate:r=>r.method()==='POST'&&/\/turns$/.test(new URL(r.url()).pathname)});
  await page.locator('#assistant-scene-text').fill('孩子在蓝桥旁放风筝');await page.locator('#assistant-scene-confirm').check();await page.locator('#assistant-scene-send').click();await failed;
  await page.locator('#assistant-private-recover').waitFor({state:'visible'});await page.waitForFunction(()=>!document.querySelector('#assistant-private-recover').disabled);
  assert.equal(turns().length,before+1);const lost=turns().at(-1);const calls=(await rpc({command:'scene-stats'})).calls;await rpc({command:'scene-encoder-off'});
  await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(()=>document.querySelectorAll('.assistant-scene-rank').length===2&&!document.querySelector('#assistant-private-new').disabled);
  assert.equal(turns().length,before+1);assert.equal((await rpc({command:'scene-stats'})).calls,calls);
  const reads=browserRequests.filter(x=>x.method==='GET'&&x.path.includes('/requests/'+lost.response.request_id));assert.equal(reads.at(-1).headers['x-photohouse-search-version'],'4');
  assert.equal(await page.locator('#assistant-speech').isVisible(),false);
  await reopen();
  await page.waitForFunction(()=>document.querySelectorAll('.assistant-scene-rank').length===2&&!document.querySelector('#assistant-private-new').disabled);
  assert.equal((await rpc({command:'scene-stats'})).calls,calls);
  checkpoint('Lost response and history reopen retain v4 order through GET only with encoder disabled');
  // User-facing enlarged bilingual controls, within the real assistant dialog.
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  await page.locator('#assistant-scene > summary').scrollIntoViewIfNeeded();
  if(!await page.locator('#assistant-scene').evaluate(el=>el.open))await page.locator('#assistant-scene > summary').click();
  await page.locator('#assistant-scene-text').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-phone-zh-150.png'),fullPage:false});
  await page.locator('#assistant-scene-back').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-phone-zh-actions-150.png'),fullPage:false});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.locator('#assistant-scene-text').focus();await page.keyboard.press('Tab');assert.equal(await page.locator('#assistant-scene-confirm').evaluate(el=>el===document.activeElement),true);
  const savedThread=await page.locator('#assistant-private-select').inputValue();
  await page.locator('#assistant-workspace-close').click();const sceneReprobe=page.waitForResponse(r=>new URL(r.url()).pathname==='/assistant/workspace/v1/scene-search-capabilities'&&r.status()===200);await page.locator('#language').click();await sceneReprobe;
  await page.waitForFunction(()=>document.documentElement.lang==='en'&&!document.querySelector('#assistant-private-new').disabled);
  await page.locator('[href="#assistant-panel"]').first().click();await reopen(savedThread);
  await page.locator('#assistant-scene-ranking').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-phone-en-ranking-150.png'),fullPage:false});
  assert.match(await page.locator('#assistant-scene-ranking').innerText(),/approximate ranking/);
  await page.locator('#assistant-scene-text').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-phone-en-150.png'),fullPage:false});
  await page.locator('#assistant-scene-back').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-phone-en-actions-150.png'),fullPage:false});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  checkpoint('Chinese and English 390px 150-percent dialog renders keep scope, input, acknowledgement and ranking readable');
  // Revalidate the actual latest owned scene after synthetic artifact damage.
  await rpc({command:'scene-corrupt'});
  await reopen();await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  assert.equal(await page.locator('#assistant-results .assistant-result').count(),0);assert.equal(await page.locator('#assistant-scene-ranking').isVisible(),false);assert.equal((await rpc({command:'scene-stats'})).calls,calls);
  checkpoint('Corrupt artifact readback withholds old result cards without model replay');
  // Current conditions can only be changed through a full ordinary search.
  const ordinaryScope=await ordinary('find photos of Sample Child in 2026');assert.equal(ordinaryScope.response.result.kind,'results');
  const unresolved=await ordinary('only photos of Unknown Stranger');assert.equal(unresolved.response.result.kind,'clarification');
  assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);await page.locator('#assistant-scene > summary').click();assert.equal(await page.locator('#assistant-scene-unready').isVisible(),true);
  const count=turns().length;assert.equal(await page.locator('#assistant-scene-text').isDisabled(),true);assert.equal(turns().length,count);
  const clean=await ordinary('find photos of Sample Child in 2026');assert.equal(clean.response.result.kind,'results');assert.equal(clean.response.result.version,2);
  assert.equal(await page.locator('#assistant-scene-ranking').isVisible(),false);
  checkpoint('Unresolved conditions block scene action; a complete ordinary search leaves the scene and resolves scope');
  assert.deepEqual(pageErrors,[]);assert.deepEqual(blockedOrigins,[]);assert.equal(browserRequests.filter(r=>/\/speech$/.test(new URL(r.path,'https://photohouse.test').pathname)).length,0);
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checkpoints,pageErrors,blockedOrigins,generatedVectors:true,mockEncoder:true,modelRelevanceQualified:false},null,2));
  console.log(`Scene browser checks: ${checkpoints.length} passed. Artifacts: ${artifacts}`);
})().catch(async error=>{console.error(error);try{await page?.screenshot({path:path.join(artifacts,'failure.png'),fullPage:false});console.error(JSON.stringify(browserRequests.slice(-5).map(x=>({path:x.path,status:x.status,response:x.response})),null,2));}catch{}process.exitCode=1;}).finally(async()=>{await context?.close();await browser?.close();try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');}catch{}bridge.kill();});
