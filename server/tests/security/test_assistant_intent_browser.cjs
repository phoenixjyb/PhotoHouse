/* V3 descriptive planning through the native UI and protected workspace route. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-intent-v3-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'../.venv/bin/python'),[path.join(__dirname,'assistant_intent_browser_fixture.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pendingRpc=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){readyResolve();return;}const call=pendingRpc.get(value.id);if(call){pendingRpc.delete(value.id);call.resolve(value);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Intent browser fixture exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Intent browser fixture exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const browserRequests=[],pageErrors=[],blockedOrigins=[];
let loseNextTurn=false;
function responseBody(response){return JSON.parse(Buffer.from(response.body,'base64').toString());}
function plannerCalls(){return rpc({command:'planner-stats'}).then(value=>value.calls);}
let browser,context,page;
async function installSyntheticTransport(targetContext){
  await targetContext.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){blockedOrigins.push(url.origin);await route.abort();return;}
    const entry={method:request.method(),path:url.pathname+url.search,headers:await request.allHeaders(),body:request.postData()||'',serverReached:false};browserRequests.push(entry);
    const headers={...entry.headers};delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    entry.serverReached=true;
    const response=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    entry.status=response.status;try{entry.response=responseBody(response);}catch{}
    if(entry.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&loseNextTurn){loseNextTurn=false;await route.abort('failed');return;}
    const outputHeaders={...response.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try{await route.fulfill({status:response.status,headers:outputHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  await targetContext.addInitScript(()=>{window.__phSpeechCalls=0;try{Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak(){window.__phSpeechCalls++;},cancel(){},get speaking(){return false;}}});}catch{}});
}
function turnEntries(){return browserRequests.filter(entry=>entry.method==='POST'&&/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(new URL(entry.path,'https://photohouse.test').pathname));}
async function send(text,{keyboard=false,lose=false}={}){
  const before=turnEntries().length;loseNextTurn=lose;
  await page.locator('#assistant-text').fill(text);
  const isTurn=request=>request.method()==='POST'&&/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(new URL(request.url()).pathname);
  if(lose){
    const failed=page.waitForEvent('requestfailed',{predicate:isTurn});await page.locator('#assistant-send').click();await failed;
  }else{
    const response=page.waitForResponse(value=>isTurn(value.request()));response.catch(()=>{});
    if(keyboard){await page.locator('#assistant-text').focus();await page.keyboard.press('Control+Enter');}
    else await page.locator('#assistant-send').click();
    await response;await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  }
  assert.equal(turnEntries().length,before+1);return turnEntries().at(-1);
}
async function seedLegacyHistoryWithBrowserCredentials(auth){
  const requestHeaders={'Content-Type':'application/json','Cookie':auth.cookie,
    'Origin':auth.origin,'Sec-Fetch-Site':auth.fetchSite,'X-CSRF-Token':auth.csrf};
  const created=await rpc({method:'POST',path:'/assistant/workspace/v1/threads',headers:requestHeaders,
    body:Buffer.from(JSON.stringify({library_id:'family-a'})).toString('base64')});
  if(created.status!==201)throw new Error(`Legacy thread seed failed: ${created.status}`);
  const thread=responseBody(created).thread,requestId=require('node:crypto').randomUUID();
  const turn=await rpc({method:'POST',path:`/assistant/workspace/v1/threads/${thread.thread_id}/turns`,
    headers:{...requestHeaders,'X-PhotoHouse-Search-Version':'2'},
    body:Buffer.from(JSON.stringify({library_id:'family-a',request_id:requestId,
      expected_revision:thread.revision,
      text:'find photos of Sample Child in September 2032 containing "secret memory phrase"'})).toString('base64')});
  if(turn.status!==200)throw new Error(`Legacy v2 turn seed failed: ${turn.status}`);
  if(responseBody(turn).result?.version!==2)throw new Error('Legacy seed did not produce a v2 result');
  return {thread_id:thread.thread_id,request_id:requestId};
}
async function openPrivateWorkspace(){
  await page.goto('https://photohouse.test/ui');
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#grid .asset').first().waitFor();
  if(!await page.locator('#assistant-panel').evaluate(element=>element.open))await page.locator('#assistant-panel > summary').click();
  await page.locator('#assistant-search-perspective').waitFor({state:'visible'});
  await page.locator('#assistant-private-new').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-private-select')?.value&&!document.querySelector('#assistant-private-new').disabled);
  const browserCreate=browserRequests.find(entry=>entry.method==='POST'&&entry.path==='/assistant/workspace/v1/threads'&&entry.status===201);
  assert.ok(browserCreate?.headers?.cookie&&browserCreate.headers['x-csrf-token'],'the live browser workspace create supplies session-bound credentials');
  const legacy=await seedLegacyHistoryWithBrowserCredentials({cookie:browserCreate.headers.cookie,
    csrf:browserCreate.headers['x-csrf-token'],origin:browserCreate.headers.origin,
    fetchSite:browserCreate.headers['sec-fetch-site']});
  await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-refresh').click();
  await page.locator(`#assistant-private-select option[value="${legacy.thread_id}"]`).waitFor({state:'attached'});
  const detail=page.waitForResponse(response=>response.request().method()==='GET'&&response.url().includes(`/assistant/workspace/v1/threads/${legacy.thread_id}?`));
  await page.locator('#assistant-private-select').selectOption(legacy.thread_id);await detail;
  await page.waitForFunction(()=>document.querySelectorAll('#assistant-results .assistant-result').length===2);
  const legacyRead=browserRequests.filter(entry=>entry.method==='GET'&&entry.path.includes(`/requests/${legacy.request_id}`));
  assert.ok(legacyRead.some(entry=>entry.headers['x-photohouse-search-version']==='3'),
    'a v3 client hydrates saved v2 request results with the negotiated v3 readback header');
  assert.ok(legacyRead.some(entry=>entry.status===200&&entry.response?.result?.version===2),
    'saved v2 results retain their actual result version during same-session history hydration');
  await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-new').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-private-select')?.value&&!document.querySelector('#assistant-private-new').disabled);
}
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});context.setDefaultTimeout(15000);await installSyntheticTransport(context);
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  await openPrivateWorkspace();

  const phrase='find photos of Sample Child playing in snow red coat in September 2032 containing "secret memory phrase"';
  const initial=await send(phrase),first=initial.response.result;
  assert.equal(initial.headers['x-photohouse-search-version'],'3');assert.equal(initial.status,200,JSON.stringify(initial.response));
  assert.equal(first.version,3);assert.equal(first.context.search_version,3);
  assert.deepEqual(first.filters.people,{ids:['301'],match:'any'});
  assert.deepEqual(first.filters.date,{from:'2032-09-01',to:'2032-09-30'});
  assert.deepEqual(first.filters.media,['image']);assert.equal(first.filters.text,'secret memory phrase');
  assert.deepEqual(first.filters.descriptive.concepts.map(item=>item.surface),['playing in snow','red coat']);
  assert.deepEqual(first.items.map(item=>item.id),['101']);assert.equal(first.items[0].kind,'image');
  assert.equal(await plannerCalls(),1);
  await page.locator('#assistant-search-summary').waitFor({state:'visible'});
  let summary=await page.locator('#assistant-search-summary').innerText();
  for(const visible of ['playing in snow','red coat','Sample Child','2032-09','secret memory phrase'])assert.ok(summary.includes(visible),`summary lacks ${visible}: ${summary}`);
  assert.doesNotMatch(summary,/在雪地玩|红色外套/,'alternatives stay out of the visible summary');
  await page.screenshot({path:path.join(artifacts,'intent-v3-desktop-1280.png'),fullPage:false});

  const correction=await send('不是red coat，是blue coat'),paired=correction.response.result;
  assert.equal(correction.status,200,JSON.stringify(correction.response));assert.equal(paired.version,3);
  assert.deepEqual(paired.filters.people,first.filters.people);assert.deepEqual(paired.filters.date,first.filters.date);
  assert.deepEqual(paired.filters.media,first.filters.media);assert.equal(paired.filters.text,first.filters.text);
  assert.deepEqual(paired.filters.descriptive.concepts.map(item=>item.surface),['playing in snow','blue coat']);
  assert.deepEqual(paired.items.map(item=>item.id),['103'],'paired correction replaces red coat with the matching synthetic blue-coat item');
  assert.equal(await plannerCalls(),2,'paired description correction invokes the planner once');
  await page.locator('#assistant-search-summary').waitFor({state:'visible'});
  const pairedSummary=await page.locator('#assistant-search-summary').innerText();
  for(const visible of ['playing in snow','blue coat','Sample Child','2032-09','secret memory phrase'])assert.ok(pairedSummary.includes(visible),`corrected summary lacks ${visible}: ${pairedSummary}`);
  assert.doesNotMatch(pairedSummary,/在雪地玩|红色外套|蓝外套/,'the visible correction summary uses concept surfaces, not alternatives');
  await page.screenshot({path:path.join(artifacts,'intent-v3-correction-desktop-1280.png'),fullPage:false});

  const refined=await send('只看2032年9月2日'),second=refined.response.result;
  assert.equal(refined.headers['x-photohouse-search-version'],'3');assert.equal(second.version,3);
  assert.deepEqual(second.filters.date,{from:'2032-09-02',to:'2032-09-02'});
  assert.deepEqual(second.filters.people,first.filters.people);assert.equal(second.filters.text,first.filters.text);
  assert.deepEqual(second.filters.descriptive,paired.filters.descriptive);
  assert.deepEqual(second.items.map(item=>item.id),['103']);assert.equal(await plannerCalls(),2,'deterministic date follow-up does not replan');

  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  await page.locator('#assistant-search-summary').scrollIntoViewIfNeeded();
  const phoneSummary=await page.locator('#assistant-search-summary').innerText();
  for(const visible of ['Sample Child','secret memory phrase','playing in snow','blue coat','2032-09-02','媒体类型'])assert.ok(phoneSummary.includes(visible),`phone conditions omit ${visible}: ${phoneSummary}`);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await page.locator('#assistant-search-summary').screenshot({path:path.join(artifacts,'intent-v3-correction-phone-summary-390-font150.png')});
  await page.screenshot({path:path.join(artifacts,'intent-v3-correction-phone-390-font150.png'),fullPage:false});
  const keyboard=await send('只看2032年9月2日',{keyboard:true});
  assert.equal(keyboard.headers['x-photohouse-search-version'],'3');
  assert.deepEqual(keyboard.response.result.filters.descriptive,paired.filters.descriptive);
  assert.equal(await plannerCalls(),2,'keyboard date follow-up preserves the planned description');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.locator('#assistant-search-summary').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'intent-v3-phone-390-font150.png'),fullPage:false});

  const callsBeforeRecovery=await plannerCalls();
  await send(phrase,{lose:true});
  assert.equal(await plannerCalls(),callsBeforeRecovery+1,'a newly submitted descriptive query invokes the fixture planner once');
  if(!await page.locator('#assistant-private-management').evaluate(element=>element.open))await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-recover').waitFor({state:'visible'});
  await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(()=>document.querySelectorAll('#assistant-results .assistant-result').length===1&&!document.querySelector('#assistant-private-new').disabled);
  const lost=turnEntries().at(-1);assert.equal(lost.response.result.version,3);
  const recoveredReads=browserRequests.filter(entry=>entry.method==='GET'&&entry.path.includes('/requests/'+lost.response.request_id));
  assert.ok(recoveredReads.length>0);assert.ok(recoveredReads.every(entry=>entry.headers['x-photohouse-search-version']==='3'));
  assert.equal(turnEntries().length,5,'recovery reads the original request instead of resubmitting it');
  assert.equal(await plannerCalls(),callsBeforeRecovery+1,'recovery returns the stored plan without calling the planner again');
  assert.deepEqual((await page.evaluate(()=>window.__phSpeechCalls)),0);
  const recovered=lost.response.result;
  assert.equal(recovered.context.search_version,3);assert.deepEqual(recovered.filters.descriptive,first.filters.descriptive);
  assert.deepEqual(recovered.filters.people,first.filters.people);assert.equal(recovered.filters.text,first.filters.text);
  await page.screenshot({path:path.join(artifacts,'intent-v3-phone-recovered-390-font150.png'),fullPage:false});

  const priorRecoveryThread=await page.locator('#assistant-private-select').inputValue();
  if(!await page.locator('#assistant-private-management').evaluate(element=>element.open))await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-new').click();
  await page.waitForFunction(previous=>document.querySelector('#assistant-private-select')?.value&&document.querySelector('#assistant-private-select').value!==previous,
    priorRecoveryThread);
  await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  const callsBeforeCorrectionRecovery=await plannerCalls();
  await send(phrase);
  assert.equal(await plannerCalls(),callsBeforeCorrectionRecovery+1);
  const correctionTurnCount=turnEntries().length;
  await send('不是red coat，是blue coat',{lose:true});
  assert.equal(await plannerCalls(),callsBeforeCorrectionRecovery+2,'the interrupted paired correction is planned once');
  const callsAfterCorrection=await plannerCalls();
  if(!await page.locator('#assistant-private-management').evaluate(element=>element.open))await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(()=>document.querySelectorAll('#assistant-results .assistant-result').length===1&&!document.querySelector('#assistant-private-new').disabled);
  assert.equal(turnEntries().length,correctionTurnCount+1,'correction recovery performs a readback instead of submitting a duplicate turn');
  assert.equal(await plannerCalls(),callsAfterCorrection,'correction recovery does not invoke the planner again');
  const recoveredCorrection=turnEntries().at(-1).response.result;
  assert.deepEqual(recoveredCorrection.filters.descriptive.concepts.map(item=>item.surface),['playing in snow','blue coat']);
  assert.deepEqual(recoveredCorrection.filters.people,first.filters.people);
  assert.deepEqual(recoveredCorrection.filters.date,first.filters.date);
  assert.deepEqual(recoveredCorrection.filters.media,first.filters.media);
  assert.equal(recoveredCorrection.filters.text,first.filters.text);
  assert.deepEqual(recoveredCorrection.items.map(item=>item.id),['103']);
  const recoveredCorrectionSummary=await page.locator('#assistant-search-summary').innerText();
  assert.ok(recoveredCorrectionSummary.includes('blue coat'));
  await page.screenshot({path:path.join(artifacts,'intent-v3-correction-recovered-phone-390-font150.png'),fullPage:false});

  const priorThread=await page.locator('#assistant-private-select').inputValue();
  if(!await page.locator('#assistant-private-management').evaluate(element=>element.open))await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-new').click();
  await page.waitForFunction(previous=>document.querySelector('#assistant-private-select')?.value&&document.querySelector('#assistant-private-select').value!==previous,
    priorThread);
  await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  const pendingQuery='find photos of Sample Child from childhood playing in snow red coat containing "secret memory phrase"';
  const plannerBeforePending=await plannerCalls();
  const pendingAsk=await send(pendingQuery),pendingResult=pendingAsk.response.result;
  assert.equal(pendingAsk.status,200);assert.equal(pendingAsk.headers['x-photohouse-search-version'],'3');
  assert.equal(pendingResult.version,3);assert.equal(pendingResult.kind,'clarification');assert.equal(pendingResult.context,null);
  assert.deepEqual(pendingResult.items,[]);assert.equal(await plannerCalls(),plannerBeforePending,
    'the date-pending clarification does not invoke the descriptive planner');
  assert.equal(JSON.stringify(pendingAsk.response).includes('pending_intent'),false,
    'private pending state is never returned in the turn response');
  const pendingThread=await page.locator('#assistant-private-select').inputValue();
  const answer=await send('September 2032'),answered=answer.response.result;
  assert.equal(answer.status,200);assert.equal(answer.headers['x-photohouse-search-version'],'3');
  assert.equal(answered.kind,'results');assert.equal(answered.context.search_version,3);
  assert.deepEqual(answered.filters.people,{ids:['301'],match:'any'});
  assert.deepEqual(answered.filters.date,{from:'2032-09-01',to:'2032-09-30'});
  assert.deepEqual(answered.filters.media,['image']);assert.equal(answered.filters.text,'secret memory phrase');
  assert.deepEqual(answered.filters.descriptive.concepts.map(item=>item.surface),['playing in snow','red coat']);
  assert.deepEqual(answered.items.map(item=>item.id),['101']);
  assert.equal(await plannerCalls(),plannerBeforePending+1,'answer planning sees the original request once, excluding the date answer');
  assert.equal(JSON.stringify(answer.response).includes('pending_intent'),false,
    'resolved turn response contains only public search data');
  if(!await page.locator('#assistant-private-management').evaluate(element=>element.open))await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-refresh').click();
  const option=page.locator('#assistant-private-select');await option.selectOption('');
  const pendingHistoryResponse=page.waitForResponse(response=>response.request().method()==='GET'&&response.url().includes(`/assistant/workspace/v1/threads/${pendingThread}?`));
  await option.selectOption(pendingThread);await pendingHistoryResponse;
  const pendingHistory=browserRequests.find(entry=>entry.method==='GET'&&entry.path.includes(`/assistant/workspace/v1/threads/${pendingThread}?`)&&entry.status===200)?.response;
  assert.ok(pendingHistory,'resolved conversation history is read back from the workspace API');
  assert.deepEqual(pendingHistory.exchanges.map(exchange=>exchange.input_text),[pendingQuery,'September 2032'],
    'the original search and its short date answer remain separate history inputs');
  assert.equal(JSON.stringify(pendingHistory).includes('pending_intent'),false,
    'thread history never exposes private pending state');
  const trailInputs=await page.locator('#assistant-turn-trail-list .assistant-turn-trail-entry').evaluateAll(entries=>entries.map(entry=>entry.querySelector('.assistant-turn-trail-text')?.textContent));
  assert.deepEqual(trailInputs,[pendingQuery,'September 2032'],'visible history retains both user inputs independently');
  await page.locator('#assistant-search-summary').waitFor({state:'visible'});
  const pendingSummary=await page.locator('#assistant-search-summary').innerText();
  for(const value of ['Sample Child','2032-09','playing in snow','red coat','secret memory phrase'])assert.ok(pendingSummary.includes(value),`resolved pending summary lacks ${value}: ${pendingSummary}`);
  await page.locator('#assistant-search-summary').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'intent-v3-pending-date-answer-phone-390-font150.png'),fullPage:false});

  const emptyEntry=await send('find photos of Sample Child in September 2032 playing in snow green coat containing "secret memory phrase"');
  const empty=emptyEntry.response.result;
  assert.equal(empty.kind,'results');assert.equal(empty.total,0);assert.deepEqual(empty.items,[]);
  assert.deepEqual(empty.filters.descriptive.concepts.map(item=>item.surface),['playing in snow','green coat']);
  assert.ok((await page.locator('#assistant-search-summary').innerText()).includes('green coat'));
  assert.match(await page.locator('#assistant-reply').innerText(),/remove the "clue wording" clue|去掉“某条线索”线索/);
  const beforeRemovalCalls=await plannerCalls(),beforeRemovalTurns=turnEntries().length;
  await send('请去掉green coat这条线索',{lose:true});
  assert.equal(await plannerCalls(),beforeRemovalCalls,'explicit single-clue removal does not call the model');
  if(!await page.locator('#assistant-private-management').evaluate(element=>element.open))await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-recover').waitFor({state:'visible'});
  await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(()=>document.querySelectorAll('#assistant-results .assistant-result').length===2&&!document.querySelector('#assistant-private-new').disabled);
  const removed=turnEntries().at(-1).response.result;
  assert.deepEqual(removed.items.map(item=>item.id),['101','103']);
  assert.deepEqual(removed.filters.descriptive.concepts.map(item=>item.surface),['playing in snow']);
  for(const key of ['people','media','date','text'])assert.deepEqual(removed.filters[key],empty.filters[key],`removal retains ${key}`);
  assert.equal(turnEntries().length,beforeRemovalTurns+1,'lost removal recovers the saved result without another turn');
  assert.equal(await plannerCalls(),beforeRemovalCalls,'removal recovery does not plan again');
  const removedSummary=await page.locator('#assistant-search-summary').innerText();
  for(const value of ['playing in snow','Sample Child','2032-09','secret memory phrase'])assert.ok(removedSummary.includes(value));
  assert.doesNotMatch(removedSummary,/green coat/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.locator('#assistant-search-summary').screenshot({path:path.join(artifacts,'intent-v3-remove-clue-phone-summary-390-font150.png')});
  await page.screenshot({path:path.join(artifacts,'intent-v3-remove-clue-recovered-phone-390-font150.png'),fullPage:false});

  const beforeWhyCalls=await plannerCalls();
  const whyEntry=await send('为什么是第一项',{keyboard:true}),explained=whyEntry.response.result;
  assert.equal(explained.kind,'results');assert.equal(explained.effect,null);
  for(const key of ['context','filters','items','total','has_more'])assert.deepEqual(explained[key],removed[key],`why-result preserves ${key}`);
  assert.equal(await plannerCalls(),beforeWhyCalls,'why-result explanations do not invoke the model');
  const whyReply=await page.locator('#assistant-reply').innerText();
  assert.match(whyReply,/Match explanation for result 1|第1项的匹配说明/);
  assert.match(whyReply,/edited caption|编辑说明/);
  assert.doesNotMatch(whyReply,/A child playing in snow wearing|在雪地玩/,'raw caption text and model alternatives stay out of the explanation');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.locator('#assistant-reply').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'intent-v3-why-result-phone-390-font150.png'),fullPage:false});

  assert.deepEqual(pageErrors,[]);assert.deepEqual(blockedOrigins,[]);
  const evidence={nativeBrowser:true,syntheticBackend:true,externalRequests:0,checkpoints:[
    'v3 descriptive query keeps image media, reviewed person, date, and exact quoted text filters',
    'summary shows concept surfaces and withholds alternatives',
    'paired Chinese correction replaces only red coat, preserves snow and hard filters, and shows matching blue-coat result',
    'date refinement preserves descriptive filters without replanning',
    '390px at 150% font and keyboard submission complete without horizontal overflow',
    'lost v3 turn recovers with a versioned GET and no second planning call',
    'lost paired correction recovers the corrected blue-coat plan without resubmission or replanning',
    'v3 client hydrates an older saved v2 result with a version-bound history read',
    'short date answer resolves a saved clarification, retains every original filter, and keeps both inputs separately in private history',
    'explicit single-clue removal repairs empty results while retaining every hard condition; lost response recovers without another turn or model call',
    'a Chinese why-result question explains current filters and edited-caption evidence while preserving result order and invoking no model or open action'],
    plannerCalls:await plannerCalls(),headers:turnEntries().map(entry=>entry.headers['x-photohouse-search-version']),pageErrors,blockedOrigins};
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify(evidence,null,2));
  for(const checkpoint of evidence.checkpoints)console.log('PASS '+checkpoint);
  console.log(`Intent browser checks: ${evidence.checkpoints.length} passed. Artifacts: ${artifacts}`);
})().catch(async error=>{console.error(error.stack||error);try{console.error(await page?.evaluate(()=>({send:document.querySelector('#assistant-send')?.disabled,status:document.querySelector('#assistant-status')?.textContent,privateStatus:document.querySelector('#assistant-private-status')?.textContent,lang:document.documentElement.lang})));await page?.screenshot({path:path.join(artifacts,'failure.png'),fullPage:false});console.error(JSON.stringify(browserRequests.slice(-8).map(entry=>({method:entry.method,path:entry.path,status:entry.status,response:entry.response})),null,2));}catch{}process.exitCode=1;}).finally(async()=>{await context?.close();await browser?.close();try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');}catch{}bridge.kill();});
