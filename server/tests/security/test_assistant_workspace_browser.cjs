/* End-to-end private assistant workspace checks against a synthetic ASGI app. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-workspace-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'../.venv/bin/python'),[path.join(__dirname,'assistant_workspace_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
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
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await installSyntheticTransport(context);
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#grid .asset').first().waitFor();
  const assistantPanel=page.locator('#assistant-panel');
  if(!await assistantPanel.evaluate(el=>el.open))await assistantPanel.locator(':scope > summary').click();
  const workspace='/assistant/workspace/v1';
  const requests=(method,suffix)=>browserRequests.filter(x=>x.method===method&&x.path.startsWith(suffix));
  const turns=()=>browserRequests.filter(x=>x.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(x.path));
  const threadCreates=()=>browserRequests.filter(x=>x.method==='POST'&&x.path===workspace+'/threads');
  const callCommand=async command=>{const result=await rpc({command});assert.equal(result.ok,true);};
  const readCapabilities=()=>page.evaluate(async()=>{const response=await fetch('/assistant/workspace/v1/capabilities?library_id=family-a');return response.json();});
  const workspacePanel=page.locator('#assistant-private');
  await workspacePanel.waitFor({state:'visible',timeout:10000});
  assert.match(await page.locator('#assistant-private-new').innerText(),/新对话|新建|创建|开始/,'Chinese is the default private pane language');
  await page.locator('#assistant-private-status').waitFor();
  checkpoint('The signed-in page exposes the private workspace in the default Chinese UI');

  // Admission is derived from both a healthy v2 store and a live discovery runtime.
  await callCommand('discovery-off');
  assert.equal((await readCapabilities()).server_owned_turns,false,'server-owned turns are false without discovery');
  await callCommand('workspace-unhealthy');
  assert.equal((await readCapabilities()).server_owned_turns,false,'server-owned turns are false when the v2 store is unhealthy');
  await callCommand('workspace-healthy');await callCommand('discovery-on');
  assert.equal((await readCapabilities()).server_owned_turns,true,'healthy v2 store and discovery enable server-owned turns');
  await page.locator('#assistant-private-new').waitFor({state:'visible'});
  checkpoint('Server-owned turn admission is false without discovery and returns when the synthetic discovery index is available');

  // Create through the keyboard, then make a grounded server-owned search.
  const firstCreateCount=threadCreates().length;
  await page.locator('#assistant-private-new').focus();await page.keyboard.press('Enter');
  await page.waitForFunction(()=>document.querySelector('#assistant-private-select')?.value);
  await page.waitForFunction(()=>document.getElementById('assistant-private-new')&&!document.getElementById('assistant-private-new').disabled,
    null,{timeout:10000});
  assert.equal(threadCreates().length,firstCreateCount+1,'keyboard activation creates one scoped thread');
  let threadId=await page.locator('#assistant-private-select').inputValue();
  assert.match(threadId,/^[0-9a-f-]{36}$/i);
  await page.locator('#assistant-text').fill('找照片');
  await page.locator('#assistant-send').click({timeout:5000});
  await page.waitForFunction(()=>/找到|照片|项/.test(document.getElementById('assistant-reply').innerText));
  await page.waitForFunction(()=>document.querySelector('#assistant-private-status').textContent.length>0);
  assert.equal(turns().length,1);
  let submitted=JSON.parse(turns()[0].body);assert.equal(submitted.library_id,'family-a');assert.equal(submitted.text,'找照片');assert.equal(submitted.expected_revision,0);
  assert.equal(await page.locator('#assistant-reply').isVisible(),true);
  assert.match(await page.locator('#assistant-reply').innerText(),/找到|照片|项/);
  const firstReply=await page.locator('#assistant-reply').innerText();
  assert(await page.locator('#assistant-private-status').innerText().then(t=>t.length>0));
  checkpoint('A private thread is created by keyboard and the first query returns a grounded reply');

  // Persist and read the exact exchange; history is text-only and has no replay side effect.
  const speechBefore=await page.evaluate(()=>window.__phSpeechCalls);
  const opensBefore=browserRequests.filter(x=>/\/assets\/[^/]+(?:\/open|\/original)(?:\?|$)/.test(x.path)).length;
  await page.locator('#assistant-private-refresh').click();
  const option=page.locator('#assistant-private-select');
  await option.selectOption('');
  const historyRead=page.waitForResponse(response=>response.request().method()==='GET'&&response.url().includes(`${workspace}/threads/${threadId}?`));
  await option.selectOption(threadId);await historyRead;
  await page.locator('#assistant-turn-trail').getByText('找照片',{exact:true}).waitFor();
  await page.locator('#assistant-turn-trail').getByText(firstReply,{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.__phSpeechCalls),speechBefore,'opening history never starts speech');
  assert.equal(browserRequests.filter(x=>/\/assets\/[^/]+(?:\/open|\/original)(?:\?|$)/.test(x.path)).length,opensBefore,'history never opens media');
  const detailGets=requests('GET',`${workspace}/threads/${threadId}?`);
  assert(detailGets.length>=1);assert(detailGets.every(x=>x.path.includes('library_id=family-a')));
  checkpoint('Saved history shows its input and reply with no automatic speech or media open');

  // Locale is persisted per account; English and Chinese replies follow the saved preference.
  await page.locator('#assistant-private .assistant-private-preferences > summary').click();
  const englishPreference=page.waitForResponse(response=>response.request().method()==='PUT'&&response.url().includes(`${workspace}/preferences`));
  await page.locator('#assistant-private-locale').selectOption('en');await englishPreference;
  await page.waitForFunction(()=>!document.getElementById('assistant-private-locale').disabled);
  const chineseBaseline=await page.locator('#assistant-reply').innerText();
  await page.locator('#assistant-text').fill('find photos');await page.locator('#assistant-send').click();
  await page.waitForFunction(baseline=>document.getElementById('assistant-reply').innerText!==baseline&&/Found|photo|item/i.test(document.getElementById('assistant-reply').innerText),chineseBaseline);
  assert.match(await page.locator('#assistant-reply').innerText(),/Found|photo|item/i);
  const enTurn=turns().at(-1),enPayload=JSON.parse(enTurn.body);assert.equal(enPayload.expected_revision,1);
  const chinesePreference=page.waitForResponse(response=>response.request().method()==='PUT'&&response.url().includes(`${workspace}/preferences`));
  await page.locator('#assistant-private-locale').selectOption('zh');await chinesePreference;
  await page.waitForFunction(()=>!document.getElementById('assistant-private-locale').disabled);
  const englishBaseline=await page.locator('#assistant-reply').innerText();
  await page.locator('#assistant-text').fill('查找照片');await page.locator('#assistant-send').click();
  await page.waitForFunction(baseline=>document.getElementById('assistant-reply').innerText!==baseline&&/找到|照片|项/.test(document.getElementById('assistant-reply').innerText),englishBaseline);
  const zhTurn=turns().at(-1);assert.equal(JSON.parse(zhTurn.body).expected_revision,2);
  const threadFromPath=turn=>turn.path.split('/')[5];
  assert.equal(threadFromPath(enTurn),threadId);assert.equal(threadFromPath(zhTurn),threadId);
  checkpoint('Saved locale preferences produce English and Chinese grounded replies in the same thread');

  // Let the server commit a turn, drop its POST response, then recover through the exact GET identity.
  loseNextTurn=true;const beforeLost=turns().length;
  await page.locator('#assistant-text').fill('找公园照片');await page.locator('#assistant-send').click();
  await page.locator('#assistant-private-recover').waitFor({state:'visible'});
  assert.equal(turns().length,beforeLost+1);
  const lost=turns().at(-1),lostPayload=JSON.parse(lost.body),lostThread=lost.path.split('/')[5];
  assert.equal(lostThread,threadId);assert.equal(lostPayload.text,'找公园照片');
  const postsBeforeRecover=turns().length;
  await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(()=>document.getElementById('assistant-private-recover').hidden||document.getElementById('assistant-private-recover').disabled);
  assert.equal(turns().length,postsBeforeRecover,'recovery never repeats the turn POST');
  const recoveryPath=`${workspace}/threads/${lostThread}/requests/${lostPayload.request_id}?library_id=family-a`;
  const recovered=requests('GET',recoveryPath);assert(recovered.length>=1,'recovery reads the exact thread and request ID');
  assert.equal(recovered.at(-1).method,'GET');
  assert.equal(await page.evaluate(()=>window.__phSpeechCalls),speechBefore,'recovered history does not repeat speech');
  checkpoint('A lost POST response recovers by one exact request GET and never duplicates the turn');

  // Abort the browser wait after the server has committed; the user's draft remains available.
  const cancelGate=gateTurn();await page.locator('#assistant-text').fill('draft survives cancellation');
  const beforeCancel=turns().length;await page.locator('#assistant-send').click();await cancelGate.seen;
  await page.locator('#assistant-cancel').waitFor({state:'visible'});
  await page.locator('#assistant-cancel').click();
  await page.waitForFunction(()=>document.getElementById('assistant-text').value==='draft survives cancellation');
  assert.equal(await page.locator('#assistant-text').inputValue(),'draft survives cancellation');
  cancelGate.release();await page.waitForTimeout(30);
  assert.equal(turns().length,beforeCancel+1);
  const beforeCancelRecovery=turns().length;await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(()=>document.getElementById('assistant-private-recover').hidden||document.getElementById('assistant-private-recover').disabled);
  assert.equal(turns().length,beforeCancelRecovery,'cancellation recovery is GET-only');
  checkpoint('Cancel stops waiting and preserves the draft while the server result remains recoverable');

  // A turn can be lost before it reaches the server. GET 404 remains an explicit
  // uncertainty gate: the question is preserved until the user acknowledges and
  // chooses to create a fresh thread, with no repeated turn POST.
  const beforeUnreceivedTurn=turns().length;
  const beforeUnreceivedCreate=threadCreates().length;
  const unreceivedQuestion='这条请求没有到达服务器';
  loseNextTurnBeforeServer=true;
  await page.locator('#assistant-text').fill(unreceivedQuestion);
  await page.locator('#assistant-send').click();
  await page.locator('#assistant-private-recover').waitFor({state:'visible'});
  const unreceivedTurn=turns().at(-1),unreceivedPayload=JSON.parse(unreceivedTurn.body);
  assert.equal(unreceivedTurn.serverReached,false,'the simulated lost turn is aborted before the ASGI server receives it');
  assert.equal(unreceivedTurn.droppedBeforeServer,true);
  assert.equal(unreceivedPayload.text,unreceivedQuestion);
  assert.equal(await page.locator('#assistant-text').inputValue(),unreceivedQuestion,'the failed request question remains in the composer');
  const unreceivedPath=`${workspace}/threads/${threadId}/requests/${unreceivedPayload.request_id}?library_id=family-a`;
  const unreceived404=page.waitForResponse(response=>response.request().method()==='GET'&&response.url().includes(unreceivedPath)&&response.status()===404);
  await page.locator('#assistant-private-recover').click();await unreceived404;
  assert.equal(turns().length,beforeUnreceivedTurn+1,'GET 404 does not resend the turn');
  assert.equal(await page.locator('#assistant-text').inputValue(),unreceivedQuestion,'GET 404 preserves the question');
  await page.locator('#assistant-private-abandon').waitFor({state:'visible'});
  await page.locator('#assistant-private-abandon').click();
  const abandonConfirmation=page.locator('#assistant-private-abandon-confirm');
  await abandonConfirmation.waitFor({state:'visible'});
  assert.match(await abandonConfirmation.innerText(),/服务器可能仍会完成之前的请求/,'the explicit abandon confirmation warns the server may still finish');
  assert.equal(threadCreates().length,beforeUnreceivedCreate,'opening the warning does not create a thread');
  assert.equal(turns().length,beforeUnreceivedTurn+1,'opening the warning does not retry the turn');
  await page.locator('#assistant-private-abandon-yes').click();
  await page.waitForFunction(oldId=>{
    const select=document.getElementById('assistant-private-select');return select?.value&&select.value!==oldId;
  },threadId,{timeout:10000});
  threadId=await page.locator('#assistant-private-select').inputValue();
  assert.equal(await page.locator('#assistant-text').inputValue(),unreceivedQuestion,'the new thread keeps the question as an unsent draft');
  assert.equal(threadCreates().length,beforeUnreceivedCreate+1,'fresh thread creation follows only the explicit confirmation');
  assert.equal(turns().length,beforeUnreceivedTurn+1,'the unreceived turn is never resent after GET 404 and abandon');
  checkpoint('A turn lost before server receipt returns exact GET 404; explicit warning/abandon creates a fresh thread and preserves the question without resending');

  // A thread-creation POST lost before receipt retains its exact client ID and
  // draft. Reconciliation must first issue GET for that ID; only after the
  // explicit 404 does the user get a same-ID retry action.
  const creationDraft='草稿在创建恢复后仍保留';
  const beforeUnreceivedCreation=threadCreates().length;
  const beforeUnreceivedCreationTurns=turns().length;
  loseNextCreationBeforeServer=true;
  await page.locator('#assistant-text').fill(creationDraft);
  await page.locator('#assistant-private-new').click();
  await page.locator('#assistant-private-reconcile').waitFor({state:'visible'});
  const droppedCreation=threadCreates().at(-1);
  const droppedCreationId=JSON.parse(droppedCreation.body).thread_id;
  assert.equal(droppedCreation.serverReached,false,'the simulated lost creation is aborted before the ASGI server receives it');
  assert.equal(droppedCreation.droppedBeforeServer,true);
  assert.match(droppedCreationId,/^[0-9a-f-]{36}$/i);
  assert.equal(await page.locator('#assistant-text').inputValue(),creationDraft,'failed creation preserves the visible draft');
  const exactThreadPath=`${workspace}/threads/${droppedCreationId}?library_id=family-a`;
  const creation404=page.waitForResponse(response=>response.request().method()==='GET'&&response.url().includes(exactThreadPath)&&response.status()===404);
  await page.locator('#assistant-private-reconcile').click();await creation404;
  assert.equal(await page.locator('#assistant-text').inputValue(),creationDraft,'exact GET 404 preserves the draft');
  await page.locator('#assistant-private-retry-creation').waitFor({state:'visible'});
  assert.equal(threadCreates().length,beforeUnreceivedCreation+1,'GET 404 alone never retries creation');
  const sameIdCreated=page.waitForResponse(response=>response.request().method()==='POST'&&response.url().endsWith(`${workspace}/threads`)&&response.status()===201);
  await page.locator('#assistant-private-retry-creation').click();await sameIdCreated;
  await page.waitForFunction(id=>document.getElementById('assistant-private-select')?.value===id,droppedCreationId,{timeout:10000});
  const creationAttempts=threadCreates().slice(beforeUnreceivedCreation);
  assert.equal(creationAttempts.length,2,'the second creation POST occurs only after explicit retry');
  assert.deepEqual(creationAttempts.map(request=>JSON.parse(request.body).thread_id),[droppedCreationId,droppedCreationId],
    'retry uses the exact pending creation ID');
  assert.equal(creationAttempts[0].serverReached,false);
  assert.equal(creationAttempts[1].serverReached,true);
  assert.equal(creationAttempts[1].response.thread.thread_id,droppedCreationId);
  assert.equal(await page.locator('#assistant-text').inputValue(),creationDraft,'same-ID retry preserves the draft');
  threadId=droppedCreationId;
  assert.equal(turns().length,beforeUnreceivedCreationTurns,'creation recovery does not submit a turn');
  checkpoint('A creation lost before server receipt requires exact GET 404 and explicit same-ID retry while preserving the draft');

  // Two-step delete keeps the thread until the explicit confirmation action.
  await page.locator('#assistant-private-delete').click();
  await page.locator('#assistant-private-delete-confirm').waitFor({state:'visible'});
  assert.equal(await page.locator('#assistant-private-select').inputValue(),threadId);
  const listBeforeDelete=browserRequests.filter(x=>x.method==='GET'&&x.path===`${workspace}/threads?library_id=family-a`).length;
  await page.locator('#assistant-private-delete-confirm').focus();await page.keyboard.press('Enter');
  await page.waitForFunction(id=>!Array.from(document.querySelector('#assistant-private-select').options).some(o=>o.value===id),threadId);
  assert(browserRequests.some(x=>x.method==='DELETE'&&x.path===`${workspace}/threads/${threadId}`));
  assert(browserRequests.filter(x=>x.method==='GET'&&x.path===`${workspace}/threads?library_id=family-a`).length>=listBeforeDelete);
  checkpoint('Thread deletion requires a second keyboard-confirmed action');

  // Visual and keyboard checks at the requested viewports.
  await page.setViewportSize({width:1280,height:900});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'desktop UI has no horizontal overflow');
  await page.screenshot({path:path.join(artifacts,'assistant-workspace-desktop-1280.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  if(!await page.locator('#assistant-private .assistant-private-preferences').evaluate(el=>el.open))await page.locator('#assistant-private .assistant-private-preferences > summary').click();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'private workspace has no horizontal overflow at 390px with 150% root font size');
  assert(await workspacePanel.isVisible());
  for(const id of ['assistant-private-new','assistant-private-select','assistant-private-refresh','assistant-private-locale']){
    const control=page.locator('#'+id);assert(await control.isVisible(),`${id} is reachable in the narrow viewport`);
    const role=await control.getAttribute('role'),name=await control.getAttribute('aria-label'),label=await control.getAttribute('aria-labelledby');
    assert(role||name||label||await control.evaluate(el=>!!(el.labels?.length||el.textContent.trim())),`${id} has an accessible name`);
  }
  await page.screenshot({path:path.join(artifacts,'assistant-workspace-mobile-390px-150pct.png'),fullPage:true});
  await page.evaluate(()=>{document.documentElement.style.fontSize='';});

  // Inspect the actual centered dialog at each size. The pane controls live in
  // its scrolling content while the composer stays in the separate footer row.
  await page.setViewportSize({width:1280,height:900});
  await page.locator('#memory-assistant').scrollIntoViewIfNeeded();
  await page.locator('#memory-assistant').click();
  const dialog=page.locator('#assistant-workspace-dialog'),content=page.locator('#assistant-workspace-content'),footer=page.locator('#assistant-workspace-footer');
  await dialog.waitFor({state:'visible'});assert.equal(await dialog.evaluate(el=>el.open),true);
  assert.equal(await page.locator('#assistant-private').evaluate(el=>el.closest('#assistant-workspace-content')?.id),'assistant-workspace-content');
  const assertVisibleInWorkspace=async ids=>{
    for(const id of ids){
      const control=page.locator('#'+id);await control.scrollIntoViewIfNeeded();assert(await control.isVisible(),`${id} is visible after scrolling`);
      const measurement=await control.evaluate(el=>{const r=el.getBoundingClientRect(),c=document.getElementById('assistant-workspace-content').getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,contentTop:c.top,contentBottom:c.bottom,contentLeft:c.left,contentRight:c.right};});
      assert(measurement.top>=measurement.contentTop-1&&measurement.bottom<=measurement.contentBottom+1&&measurement.left>=measurement.contentLeft-1&&measurement.right<=measurement.contentRight+1,
        `${id} can be scrolled fully inside dialog content: ${JSON.stringify(measurement)}`);
    }
  };
  const assertDialogRows=async label=>{
    const geometry=await page.evaluate(()=>{
      const box=el=>{const r=el.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height};};
      return {width:innerWidth,height:innerHeight,dialog:box(document.getElementById('assistant-workspace-dialog')),
        content:box(document.getElementById('assistant-workspace-content')),footer:box(document.getElementById('assistant-workspace-footer')),
        composer:box(document.getElementById('assistant-text')),send:box(document.getElementById('assistant-send'))};
    });
    const {dialog:d,content:c,footer:f,composer:t,send:s,width,height}=geometry;
    assert(d.top>=-1&&d.left>=-1&&d.right<=width+1&&d.bottom<=height+1,`${label}: dialog fits viewport ${JSON.stringify(geometry)}`);
    assert(c.bottom<=f.top+1,`${label}: dialog content does not cover its footer ${JSON.stringify(geometry)}`);
    assert(f.top>=d.top&&f.bottom<=d.bottom+1&&t.top>=f.top&&t.bottom<=f.bottom+1&&s.top>=f.top&&s.bottom<=f.bottom+1,
      `${label}: composer and send button stay in visible footer ${JSON.stringify(geometry)}`);
    assert(await page.locator('#assistant-text').isVisible());assert(await page.locator('#assistant-send').isVisible());
  };
  await assertVisibleInWorkspace(['assistant-private-new','assistant-private-select','assistant-private-refresh']);
  const preferences=page.locator('#assistant-private .assistant-private-preferences');
  if(!await preferences.evaluate(el=>el.open))await preferences.locator(':scope > summary').click();
  await assertVisibleInWorkspace(['assistant-private-locale']);await assertDialogRows('desktop 1280px');
  await content.evaluate(el=>{el.scrollTop=0;});await page.screenshot({path:path.join(artifacts,'assistant-private-dialog-desktop.png'),fullPage:false});

  // A larger default font is a separate, layout-realistic stress case at the
  // 390 CSS-pixel phone width. It does not claim native browser zoom behavior.
  await page.evaluate(()=>{document.documentElement.style.zoom='';document.documentElement.style.fontSize='150%';});
  await page.setViewportSize({width:390,height:844});
  await assertVisibleInWorkspace(['assistant-private-new','assistant-private-select','assistant-private-refresh']);
  await page.locator('#assistant-text').scrollIntoViewIfNeeded();await page.locator('#assistant-send').scrollIntoViewIfNeeded();
  await assertDialogRows('390px with 150% root font size');
  await page.evaluate(()=>{document.documentElement.style.fontSize='';});

  // Model a 390x844 physical phone view at 150% with its corresponding CSS
  // viewport and device scale factor, rather than applying CSS zoom to the app.
  phoneContext=await browser.newContext({viewport:{width:260,height:563},deviceScaleFactor:1.5,serviceWorkers:'block',storageState:await context.storageState()});
  await installSyntheticTransport(phoneContext);
  const phonePage=await phoneContext.newPage();phonePage.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  await phonePage.goto('https://photohouse.test/ui');await phonePage.locator('#grid .asset').first().waitFor();
  await phonePage.locator('#memory-assistant').click();
  page=phonePage;
  const phoneDialog=page.locator('#assistant-workspace-dialog');
  await phoneDialog.waitFor({state:'visible'});assert.equal(await phoneDialog.evaluate(el=>el.open),true);
  assert.equal(await page.locator('#assistant-private').evaluate(el=>el.closest('#assistant-workspace-content')?.id),'assistant-workspace-content');
  await page.locator('#assistant-private').waitFor({state:'visible'});
  await assertVisibleInWorkspace(['assistant-private-new','assistant-private-select','assistant-private-refresh']);
  const phonePreferences=page.locator('#assistant-private .assistant-private-preferences');
  if(!await phonePreferences.evaluate(el=>el.open))await phonePreferences.locator(':scope > summary').click();
  await assertVisibleInWorkspace(['assistant-private-locale']);
  await page.locator('#assistant-text').scrollIntoViewIfNeeded();await page.locator('#assistant-send').scrollIntoViewIfNeeded();
  await assertDialogRows('260x563 CSS viewport at device scale 1.5');
  await page.locator('#assistant-private-select').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'assistant-private-dialog-phone150.png'),fullPage:false,scale:'device'});
  const phoneScreenshot=fs.readFileSync(path.join(artifacts,'assistant-private-dialog-phone150.png'));
  assert.equal(phoneScreenshot.readUInt32BE(16),390,'150% phone screenshot is 390 physical pixels wide');
  assert.equal(phoneScreenshot.readUInt32BE(20),845,'Chromium device-scale screenshot captures the 563 CSS-pixel height');
  assert.deepEqual(pageErrors,[]);assert.deepEqual(blockedOrigins,[],'all browser requests use the synthetic photohouse.test origin');
  checkpoint('Centered dialog screenshots confirm scrollable workspace controls and an unobstructed composer footer at desktop and a 260x563 CSS viewport rendered at device scale 1.5');
  checkpoint('Desktop and 390px with 150% root font size render without horizontal overflow; the focused phone dialog uses 260x563 CSS pixels at device scale 1.5; controls have accessible names and no page errors');

  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checkpoints,requests:browserRequests.map(x=>({method:x.method,path:x.path})),pageErrors,syntheticBackend:true,transport:'Chromium requests intercepted and fulfilled through an in-process ASGI TestClient; only photohouse.test is allowed; no external network'},null,2));
  console.log(`Assistant private workspace browser checks: ${checkpoints.length} passed. Artifacts: ${artifacts}`);
})().catch(async error=>{
  let uiState=null;try{uiState=await page?.evaluate(()=>({privateHidden:document.getElementById('assistant-private')?.hidden,
    privateStatusLength:document.getElementById('assistant-private-status')?.textContent.length,
    privateModule:typeof window.PhotoHousePrivateAssistant,
    sendDisabled:document.getElementById('assistant-send')?.disabled,textDisabled:document.getElementById('assistant-text')?.disabled,
    newDisabled:document.getElementById('assistant-private-new')?.disabled,scopeStatusLength:document.getElementById('assistant-status')?.textContent.length,
    authenticated:!document.getElementById('auth')?.checkVisibility()}));}catch{}
  console.error('BROWSER_DIAGNOSTICS '+JSON.stringify({requests:browserRequests.map(x=>({method:x.method,path:x.path,status:x.status,
    server_owned_turns:x.response?.server_owned_turns})),uiState,pageErrors}));
  console.error(error.stack||error);process.exitCode=1;
}).finally(async()=>{
  try{releaseHeldTurn?.();}catch(_){}
  try{await phoneContext?.close();}catch(_){}try{await context?.close();}catch(_){}try{await browser?.close();}catch(_){}
  try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.stdin.end();}catch(_){}
});
