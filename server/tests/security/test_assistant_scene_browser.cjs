/* Scene workspace against synthetic identities, vectors and mock encoder only. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const coverageMode=process.env.PH_SCENE_COVERAGE==='1';
const pageMode=process.env.PH_SCENE_PAGES==='1';
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-workspace-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'../.venv/bin/python'),[path.join(__dirname,'assistant_workspace_browser_bridge.py')],{cwd:root,env:{...process.env,PH_SCENE_FIXTURE:'1',...(pageMode?{PH_SCENE_PAGES:'1'}:{})},stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pendingRpc=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const call=pendingRpc.get(result.id);if(call){pendingRpc.delete(result.id);call.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Browser bridge exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Browser bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const browserRequests=[],pageErrors=[],checkpoints=[],blockedOrigins=[];
let loseNextTurn=false,loseNextTurnBeforeServer=false,loseNextCreationBeforeServer=false,holdNextTurn=null,releaseHeldTurn=null;
let coverageSummary=null;
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
  const captureCoverageReply=async(label,width,fontSize)=>{
    const height=width===390?845:900;
    await page.setViewportSize({width,height});
    await page.evaluate(size=>document.documentElement.style.fontSize=size,fontSize);
    const content=page.locator('#assistant-workspace-content'),reply=page.locator('#assistant-reply');
    await content.evaluate(element=>{element.scrollTop=element.scrollHeight;});
    await reply.scrollIntoViewIfNeeded();
    const bounds=await reply.boundingBox(),contentBounds=await content.boundingBox();
    assert(bounds&&contentBounds&&bounds.y>=contentBounds.y&&bounds.y+bounds.height<=contentBounds.y+contentBounds.height,
      `${label} full disclosure paragraph should be visible inside the assistant dialog`);
    await page.screenshot({path:path.join(artifacts,`coverage-${label}.png`),fullPage:false});
    if(width===390)assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,
      `${label} viewport should not overflow horizontally`);
  };
  await ordinary('找示例儿童在2026年的照片');
  await page.locator('#assistant-text').fill('unsent main search draft');
  await page.locator('#assistant-scene').waitFor({state:'visible'});await page.locator('#assistant-scene > summary').click();
  assert.match(await page.locator('#assistant-scene-scope').innerText(),/示例儿童/);assert.match(await page.locator('#assistant-scene-scope').innerText(),/2026-01-01/);
  await page.locator('#assistant-scene-text').fill('孩子 flying a kite 蓝桥旁');assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);
  await page.locator('#assistant-scene-confirm').check();assert.equal(await page.locator('#assistant-scene-send').isEnabled(),true);
  await page.locator('#assistant-scene-text').fill('中'.repeat(171));assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);
  await page.locator('#assistant-scene-text').fill('a kite\nblue bridge');assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);
  checkpoint('Scene input shows reviewed person/date/photo conditions, requires acknowledgement, and rejects overflow and multiline wording');
  const search=await submitScene('孩子 flying a kite 蓝桥旁');
  assert.equal(search.status,200,JSON.stringify(search.response));assert.equal(search.headers['x-photohouse-search-version'],'4');assert.deepEqual(JSON.parse(search.body).accepts,['scene_search_v1']);
  if(pageMode){assert.equal(search.response.result.total,46);assert.equal(search.response.result.items.length,20);assert.equal(search.response.result.has_more,true);assert.equal(search.response.result.context.visible_ids.length,20);}
  else assert.deepEqual(search.response.result.items.map(x=>x.id),['102','101']);assert.equal(search.response.result.filters.people.ids[0],'301');assert.equal(search.response.result.filters.date.from,'2026-01-01');
  if(coverageMode){
    const details=search.response.result.semantic.coverage_details;
    assert.match(details.policy_sha256,/^[0-9a-f]{64}$/);
    assert.deepEqual({...details,policy_sha256:'<pinned-policy>'},{version:1,policy_sha256:'<pinned-policy>',state:'partial',catalog_images:pageMode?111:67,searchable_images:pageMode?46:2,omitted_images:65,matched_omitted_images:0});
    coverageSummary={state:details.state,catalog_images:details.catalog_images,searchable_images:details.searchable_images,omitted_images:details.omitted_images,matched_omitted_images:details.matched_omitted_images,reply_languages:[]};
    const reply=search.response.result.reply;assert.match(reply,/65 张尚未建立索引/);assert.match(reply,/0 张未参与相似度排序/);assert.match(reply,/仍可通过普通搜索查找/);
    await captureCoverageReply('zh-desktop',1280,'');await captureCoverageReply('zh-phone-150',390,'150%');
    await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
    coverageSummary.reply_languages.push('zh');
  }
  await page.locator('#assistant-scene-ranking').waitFor({state:'visible'});assert.match(await page.locator('#assistant-scene-ranking').innerText(),/近似排序/);
  assert.equal(await page.locator('.assistant-scene-rank').count(),pageMode?20:2);assert.equal(await page.locator('#assistant-speech').isVisible(),false);assert.equal(await page.locator('#viewer').isVisible(),false);
  if(pageMode)assert.doesNotMatch(await page.locator('#assistant-scene-ranking-help').innerText(),/当前只提供前 20|Only the first 20/);
  assert.equal(await page.locator('#assistant-scene-confirm').isChecked(),false);
  await page.locator('#assistant-scene-ranking').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-desktop-zh.png'),fullPage:false});
  checkpoint('Explicit mixed-language scene turn preserves hard filters, shows approximate ranking separately, and performs no speech/open action');
  if(pageMode){
    assert.equal(await page.locator('#assistant-scene-page-next').isEnabled(),true);assert.equal(await page.locator('#assistant-scene-page-previous').isDisabled(),true);
    await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
    await page.locator('#assistant-scene-page-next').click();await page.waitForFunction(()=>document.querySelector('#assistant-scene-page-position')?.textContent.includes('21–40'));
    assert.match(await page.locator('#assistant-scene-page-position').innerText(),/46/);assert.match(await page.locator('#assistant-scene-page-position').innerText(),/2\/3/);
    let visibleRanks=await page.locator('#assistant-results .assistant-scene-rank').allTextContents();assert.equal(visibleRanks.length,20);assert.equal(visibleRanks[0],'画面相似度排序 #21');assert.equal(visibleRanks.at(-1),'画面相似度排序 #40');
    if(coverageMode)assert.match(await page.locator('#assistant-reply').innerText(),/65 张尚未建立索引/);
    await page.locator('#assistant-scene-ranking').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-page-zh-phone-150.png'),fullPage:false});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
    await page.locator('#assistant-scene-page-next').click();await page.waitForFunction(()=>document.querySelector('#assistant-scene-page-position')?.textContent.includes('41–46'));
    visibleRanks=await page.locator('#assistant-results .assistant-scene-rank').allTextContents();assert.equal(visibleRanks.length,6);assert.equal(visibleRanks[0],'画面相似度排序 #41');assert.equal(visibleRanks.at(-1),'画面相似度排序 #46');
    if(coverageMode)assert.match(await page.locator('#assistant-reply').innerText(),/65 张尚未建立索引/);
    await page.locator('#assistant-scene-page-previous').click();await page.waitForFunction(()=>document.querySelector('#assistant-scene-page-position')?.textContent.includes('21–40'));
    const threadDetailReadsBefore=browserRequests.filter(x=>x.method==='GET'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\?/.test(x.path)).length;
    await page.locator('#assistant-scene-page-return').click();await page.locator('#assistant-scene-page-return').waitFor({state:'hidden'});
    assert.equal(browserRequests.filter(x=>x.method==='GET'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\?/.test(x.path)).length,threadDetailReadsBefore+1);
    await page.waitForFunction(()=>document.querySelectorAll('#assistant-results .assistant-scene-rank').length===20);
    visibleRanks=await page.locator('#assistant-results .assistant-scene-rank').allTextContents();assert.equal(visibleRanks.length,20);assert.equal(visibleRanks[0],'画面相似度排序 #1');assert.equal(visibleRanks.at(-1),'画面相似度排序 #20');
    await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
    checkpoint('Chinese continuation pages show 20/6 cards with global ranks, support Previous and fresh Return, and fit 390px at 150%');
  }
  const english=await submitScene('a child flying a kite beside a blue bridge');assert.equal(english.response.result.context.scene.query,'a child flying a kite beside a blue bridge');
  if(coverageMode){
    const details=english.response.result.semantic.coverage_details;assert.deepEqual({...details,policy_sha256:'<pinned-policy>'},{version:1,policy_sha256:'<pinned-policy>',state:'partial',catalog_images:pageMode?111:67,searchable_images:pageMode?46:2,omitted_images:65,matched_omitted_images:0});
    const reply=english.response.result.reply;assert.match(reply,/65 are not indexed yet/);assert.match(reply,/0 photos within your current filters were not ranked/);assert.match(reply,/You can still look for those photos using ordinary search/);
    await captureCoverageReply('en-desktop',1280,'');await captureCoverageReply('en-phone-150',390,'150%');
    await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
    coverageSummary.reply_languages.push('en');checkpoint('Partial coverage metadata and Chinese/English ordinary-search disclosures render fully at desktop and 390px/150%');
  }
  // Exclusions are refused before encoding; the durable refusal requires deliberate GET reload before rewording.
  const encoderBeforeRefusal=(await rpc({command:'scene-stats'})).calls,turnsBeforeRefusal=turns().length;
  const refusal=await submitScene('孩子在紫色桥边放风筝，但不要有红色汽车');
  assert.equal(refusal.status,200);assert.equal(refusal.response.status,'failed');assert.equal(refusal.response.error,'scene_query_unsupported');assert.equal(refusal.response.result,null);
  await page.locator('#assistant-scene-reword').waitFor({state:'visible'});
  assert.equal(await page.locator('#assistant-scene-text').inputValue(),'孩子在紫色桥边放风筝，但不要有红色汽车');
  assert.equal(await page.locator('#assistant-text').inputValue(),'unsent main search draft');
  assert.equal(await page.locator('#assistant-results .assistant-result').count(),0);assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);
  const zhRewordHelp=await page.locator('#assistant-scene-reword-help').innerText();
  for(const wording of ['排除条件','没有执行画面查找','原请求（含排除条件）仍保留','哪些可见特征','完整修订后的画面请求','只有提交后','人物、日期或媒体条件','主输入框提交完整查找'])assert(zhRewordHelp.includes(wording),`Chinese scene-reword help should explain ${wording}`);
  assert.equal((await rpc({command:'scene-stats'})).calls,encoderBeforeRefusal);assert.equal(turns().length,turnsBeforeRefusal+1);
  await page.locator('#assistant-scene-reword').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-reword-desktop-zh.png'),fullPage:false});
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  await page.locator('#assistant-scene-reword').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-reword-phone-zh-150.png'),fullPage:false});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  await page.locator('#assistant-scene-reword').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-reword-zh.png'),fullPage:false});
  const selectedThread=await page.locator('#assistant-private-select').inputValue(),beforeHardReload=browserRequests.length;
  await page.reload();await page.locator('#grid .asset').first().waitFor();await page.locator('[href="#assistant-panel"]').first().click();
  await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});await reopen(selectedThread);
  if(!await page.locator('#assistant-scene').evaluate(el=>el.open))await page.locator('#assistant-scene > summary').click();
  await page.locator('#assistant-scene-reword').waitFor({state:'visible'});
  assert.equal(await page.locator('#assistant-scene-text').inputValue(),'孩子在紫色桥边放风筝，但不要有红色汽车');
  assert.equal(await page.locator('#assistant-results .assistant-result').count(),0);
  assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);
  await page.locator('#assistant-scene-reword').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'scene-reword-hard-reload-zh.png'),fullPage:false});
  const hardReloadRequests=browserRequests.slice(beforeHardReload);
  const projectedRead=hardReloadRequests.find(x=>x.method==='GET'&&x.path.includes(`/threads/${selectedThread}?`));
  assert(projectedRead,'reopening the thread after a page reload should request durable refusal state');
  assert.equal(projectedRead.headers['x-photohouse-search-version'],undefined);
  assert.equal(projectedRead.headers['x-photohouse-scene-reword-version'],'1');
  assert.equal(hardReloadRequests.some(x=>x.method==='POST'&&x.path.endsWith('/turns')),false);
  assert.equal((await rpc({command:'scene-stats'})).calls,encoderBeforeRefusal);
  const beforeReload=browserRequests.length;
  await page.locator('#assistant-scene-reload').click();await page.locator('#assistant-scene-reword').waitFor({state:'hidden'});
  assert.equal(await page.locator('#assistant-scene-text').inputValue(),'孩子在紫色桥边放风筝，但不要有红色汽车');
  assert.equal((await rpc({command:'scene-stats'})).calls,encoderBeforeRefusal);assert.equal(turns().length,turnsBeforeRefusal+1);
  const reloadRequests=browserRequests.slice(beforeReload);assert(reloadRequests.some(x=>x.method==='GET'&&/\/threads\/[0-9a-f-]+\?/.test(x.path)));
  assert(reloadRequests.some(x=>x.method==='GET'&&/\/requests\//.test(x.path)));assert.equal(reloadRequests.some(x=>x.method==='POST'),false);
  await page.locator('#assistant-scene-ranking').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-reword-reloaded-zh.png'),fullPage:false});
  const reworded=await submitScene('孩子在桥边牵着红色风筝');assert.equal(reworded.response.status,'completed');
  assert.equal(reworded.response.result.context.scene.query,'孩子在桥边牵着红色风筝');
  assert.deepEqual(reworded.response.result.context.scene.scope,english.response.result.context.scene.scope);
  checkpoint('Unsupported scene wording is retained for editing; explicit GET reload restores the previous scope, then a deliberate reworded POST succeeds');
  // Lose the response after a second semantic refusal; recovery must return that receipt with GET only.
  const encoderBeforeLostRefusal=(await rpc({command:'scene-stats'})).calls,turnsBeforeLostRefusal=turns().length;
  await rpc({command:'scene-unsupported-next'});loseNextTurn=true;
  const lostRefusal=page.waitForEvent('requestfailed',{predicate:r=>r.method()==='POST'&&/\/turns$/.test(new URL(r.url()).pathname)});
  await page.locator('#assistant-scene-text').fill('孩子在雾中的木桥旁');await page.locator('#assistant-scene-confirm').check();await page.locator('#assistant-scene-send').click();await lostRefusal;
  await page.locator('#assistant-private-recover').waitFor({state:'visible'});const unsupportedRequestId=turns().at(-1).response.request_id;
  assert.equal(turns().length,turnsBeforeLostRefusal+1);assert.equal((await rpc({command:'scene-stats'})).calls,encoderBeforeLostRefusal+1);
  await page.locator('#assistant-private-recover').click();await page.locator('#assistant-scene-reword').waitFor({state:'visible'});
  const replay=browserRequests.filter(x=>x.method==='GET'&&x.path.includes('/requests/'+unsupportedRequestId)).at(-1);
  assert(replay);assert.equal(replay.headers['x-photohouse-search-version'],'4');assert.equal(replay.response.status,'failed');assert.equal(replay.response.error,'scene_query_unsupported');
  assert.equal((await rpc({command:'scene-stats'})).calls,encoderBeforeLostRefusal+1);assert.equal(turns().length,turnsBeforeLostRefusal+1);
  await page.locator('#assistant-scene-reload').click();await page.locator('#assistant-scene-reword').waitFor({state:'hidden'});
  checkpoint('Lost unsupported response replays the same failed code through v4 GET without another POST or encoder call');
  // Start another explicit scene request, lose its response, then disable encoding.
  loseNextTurn=true;const before=turns().length;
  const failed=page.waitForEvent('requestfailed',{predicate:r=>r.method()==='POST'&&/\/turns$/.test(new URL(r.url()).pathname)});
  await page.locator('#assistant-scene-text').fill('孩子在蓝桥旁放风筝');await page.locator('#assistant-scene-confirm').check();await page.locator('#assistant-scene-send').click();await failed;
  await page.locator('#assistant-private-recover').waitFor({state:'visible'});await page.waitForFunction(()=>!document.querySelector('#assistant-private-recover').disabled);
  assert.equal(turns().length,before+1);const lost=turns().at(-1);const calls=(await rpc({command:'scene-stats'})).calls;await rpc({command:'scene-encoder-off'});
  await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(expected=>document.querySelectorAll('.assistant-scene-rank').length===expected&&!document.querySelector('#assistant-private-new').disabled,pageMode?20:2);
  assert.equal(turns().length,before+1);assert.equal((await rpc({command:'scene-stats'})).calls,calls);
  const reads=browserRequests.filter(x=>x.method==='GET'&&x.path.includes('/requests/'+lost.response.request_id));assert.equal(reads.at(-1).headers['x-photohouse-search-version'],'4');
  assert.equal(await page.locator('#assistant-speech').isVisible(),false);
  await reopen();
  await page.waitForFunction(expected=>document.querySelectorAll('.assistant-scene-rank').length===expected&&!document.querySelector('#assistant-private-new').disabled,pageMode?20:2);
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
  if(pageMode){
    assert.match(await page.locator('#assistant-scene-ranking-help').innerText(),/Return to the first results before changing your search/);
    await rpc({command:'scene-encoder-on'});
    await page.locator('#assistant-scene-page-next').click();await page.waitForFunction(()=>document.querySelector('#assistant-scene-page-position')?.textContent.includes('21–40'));
    const enPosition=await page.locator('#assistant-scene-page-position').innerText();assert.match(enPosition,/46/);assert.match(enPosition,/2 of 3/);
    const enRanks=await page.locator('#assistant-results .assistant-scene-rank').allTextContents();assert.equal(enRanks.length,20);assert.equal(enRanks[0],'Scene similarity rank #21');assert.equal(enRanks.at(-1),'Scene similarity rank #40');
    if(coverageMode)assert.match(await page.locator('#assistant-reply').innerText(),/65 张尚未建立索引/);
    await page.locator('#assistant-scene-ranking').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-page-en-phone-150.png'),fullPage:false});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
    await page.locator('#assistant-scene-page-return').click();await page.locator('#assistant-scene-page-return').waitFor({state:'hidden'});
    await page.waitForFunction(()=>document.querySelectorAll('#assistant-results .assistant-scene-rank').length===20);
    const firstPageRanks=await page.locator('#assistant-results .assistant-scene-rank').allTextContents();assert.equal(firstPageRanks.length,20);assert.equal(firstPageRanks[0],'Scene similarity rank #1');assert.equal(firstPageRanks.at(-1),'Scene similarity rank #20');
    checkpoint('English continuation page and Return stay understandable at 390px/150% and preserve global ranks');
  }
  const englishPriorScene=await page.locator('#assistant-scene-query').innerText(),englishEncoderBefore=(await rpc({command:'scene-stats'})).calls,englishTurnsBefore=turns().length;
  await rpc({command:'scene-encoder-on'});
  const englishRefusal=await submitScene('a child flying beside a purple bridge, but no red cars');
  assert.equal(englishRefusal.response.status,'failed');assert.equal(englishRefusal.response.error,'scene_query_unsupported');
  await page.locator('#assistant-scene-reword').waitFor({state:'visible'});
  assert.equal(await page.locator('#assistant-scene-text').inputValue(),'a child flying beside a purple bridge, but no red cars');
  const enRewordHelp=await page.locator('#assistant-scene-reword-help').innerText();
  for(const wording of ['exclusions','item is absent','No scene search was applied','original request, including its exclusions','Which visible feature should I look for?','complete revised scene request','only on submission','people, date, and media conditions','complete search in the main composer'])assert(enRewordHelp.includes(wording),`English scene-reword help should explain ${wording}`);
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  await page.locator('#assistant-scene-reword').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-reword-desktop-en.png'),fullPage:false});
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  await page.locator('#assistant-scene-reword').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-reword-phone-en-150.png'),fullPage:false});
  assert.match(await page.locator('#assistant-scene-reword-help').innerText(),/No scene search was applied/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  assert.equal(await page.locator('#assistant-scene-text').inputValue(),'a child flying beside a purple bridge, but no red cars');
  assert.equal((await rpc({command:'scene-stats'})).calls,englishEncoderBefore);assert.equal(turns().length,englishTurnsBefore+1);
  await page.locator('#assistant-scene-reload').click();await page.locator('#assistant-scene-reword').waitFor({state:'hidden'});
  assert.equal(await page.locator('#assistant-scene-query').innerText(),englishPriorScene);
  assert.equal(await page.locator('#assistant-scene-text').inputValue(),'a child flying beside a purple bridge, but no red cars');
  assert.equal((await rpc({command:'scene-stats'})).calls,englishEncoderBefore);assert.equal(turns().length,englishTurnsBefore+1);
  await rpc({command:'scene-encoder-off'});
  await page.locator('#assistant-scene-text').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-phone-en-150.png'),fullPage:false});
  await page.locator('#assistant-scene-back').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'scene-phone-en-actions-150.png'),fullPage:false});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  checkpoint('Chinese and English 390px 150-percent dialog renders keep scope, input, acknowledgement and ranking readable');
  // Revalidate the actual latest owned scene after synthetic artifact damage.
  const encoderBeforeCorrupt=(await rpc({command:'scene-stats'})).calls;
  await rpc({command:'scene-corrupt'});
  await reopen();await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  assert.equal(await page.locator('#assistant-results .assistant-result').count(),0);assert.equal(await page.locator('#assistant-scene-ranking').isVisible(),false);assert.equal((await rpc({command:'scene-stats'})).calls,encoderBeforeCorrupt);
  checkpoint('Corrupt artifact readback withholds old result cards without model replay');
  // Current conditions can only be changed through a full ordinary search.
  const ordinaryScope=await ordinary('find photos of Sample Child in 2026');assert.equal(ordinaryScope.response.result.kind,'results');
  const unresolved=await ordinary('only photos of Unknown Stranger');assert.equal(unresolved.response.result.kind,'clarification');
  assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);await page.locator('#assistant-scene > summary').click();assert.equal(await page.locator('#assistant-scene-unready').isVisible(),true);
  const count=turns().length;assert.equal(await page.locator('#assistant-scene-text').isDisabled(),true);assert.equal(turns().length,count);
  const clean=await ordinary('find photos of Sample Child in 2026');assert.equal(clean.response.result.kind,'results');assert.equal(clean.response.result.version,2);
  assert.equal(await page.locator('#assistant-scene-ranking').isVisible(),false);
  checkpoint('Unresolved conditions block scene action; a complete ordinary search leaves the scene and resolves scope');
  const capOffQuery='a child beside a purple bridge, but no red cars';
  const capOffRefusal=await submitScene(capOffQuery);assert.equal(capOffRefusal.response.status,'failed');assert.equal(capOffRefusal.response.error,'scene_query_unsupported');
  const capOffThread=await page.locator('#assistant-private-select').inputValue(),beforeCapOffReload=browserRequests.length;
  await rpc({command:'scene-off'});await page.reload();await page.locator('#grid .asset').first().waitFor();
  await page.locator('[href="#assistant-panel"]').first().click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});await reopen(capOffThread);
  if(!await page.locator('#assistant-scene').evaluate(el=>el.open))await page.locator('#assistant-scene > summary').click();
  await page.locator('#assistant-scene-reword').waitFor({state:'visible'});
  assert.equal(await page.locator('#assistant-scene-text').inputValue(),capOffQuery);
  assert.equal(await page.locator('#assistant-scene-text').isDisabled(),true);
  assert.equal(await page.locator('#assistant-scene-confirm').isDisabled(),true);
  assert.equal(await page.locator('#assistant-scene-send').isDisabled(),true);
  assert.equal(await page.locator('#assistant-results .assistant-result').count(),0);
  const capOffReads=browserRequests.slice(beforeCapOffReload);
  assert.equal(capOffReads.some(x=>x.method==='POST'&&x.path.endsWith('/turns')),false);
  const capOffDetail=capOffReads.find(x=>x.method==='GET'&&x.path.includes(`/threads/${capOffThread}?`));
  assert(capOffDetail);assert.equal(capOffDetail.headers['x-photohouse-scene-reword-version'],'1');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.locator('#assistant-scene-reword').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'scene-reword-capability-off-zh.png'),fullPage:false});
  await page.locator('#assistant-scene-text').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'scene-reword-capability-off-draft-zh.png'),fullPage:false});
  checkpoint('Persisted refusal remains visible with exact draft and no cards when scene capability is off; reword controls stay disabled');
  assert.deepEqual(pageErrors,[]);assert.deepEqual(blockedOrigins,[]);assert.equal(browserRequests.filter(r=>/\/speech$/.test(new URL(r.path,'https://photohouse.test').pathname)).length,0);
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checkpoints,pageErrors,blockedOrigins,generatedVectors:true,mockEncoder:true,modelRelevanceQualified:false,scenePageFixture:pageMode?{generated_assets:44,eligible_total:46,page_size:20}:null,coverage:coverageSummary},null,2));
  console.log(`Scene browser checks: ${checkpoints.length} passed. Artifacts: ${artifacts}`);
})().catch(async error=>{console.error(error);try{await page?.screenshot({path:path.join(artifacts,'failure.png'),fullPage:false});console.error(JSON.stringify(await page?.evaluate(()=>Object.fromEntries(['assistant-scene-page-next','assistant-scene-page-previous','assistant-scene-page-position','assistant-private-status'].map(id=>{const el=document.getElementById(id);return[id,el?{disabled:el.disabled,text:el.textContent,hidden:el.hidden}:null]}))),null,2));console.error(JSON.stringify(browserRequests.filter(x=>x.path.includes('/scene-pages')||x.path.includes('/scene-page-capabilities')).map(x=>({method:x.method,path:x.path,status:x.status,error:x.response?.error||null,page:x.response?.page||null,item_count:x.response?.items?.length||0})),null,2));}catch{}process.exitCode=1;}).finally(async()=>{await context?.close();await browser?.close();try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');}catch{}bridge.kill();});
