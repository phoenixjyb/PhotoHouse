/* Generated browser journey for negotiated private saved-memory cards. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-saved-memory-assistant-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'../.venv/bin/python'),
  [path.join(__dirname,'assistant_saved_memory_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,fixtureInfo;const pending=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{
  const result=JSON.parse(line);
  if(result.ready){fixtureInfo=result;readyResolve();return;}
  const request=pending.get(result.id);if(request){pending.delete(result.id);request.resolve(result);}
});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Saved-memory browser bridge exited (${code})`));for(const item of pending.values())item.reject(new Error('Saved-memory browser bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const requests=[],errors=[],external=[],checks=[];
let probeMode='live',dropNextTurnResponse=false;
let browser,context,page;
const pass=label=>{checks.push(label);console.log('PASS '+label);};
const decode=response=>JSON.parse(Buffer.from(response.body,'base64').toString('utf8'));
const turns=()=>requests.filter(item=>item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(item.path));
const cards=()=>page.locator('#assistant-results .assistant-memory-card');
const routeMemoryPath='/assistant/workspace/v1/saved-memory-capabilities';
async function installTransport(target){
  await target.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    const item={method:request.method(),path:url.pathname+url.search,
      headers:await request.allHeaders(),body:request.postData()||'',serverReached:false};
    requests.push(item);
    if(item.method==='GET'&&url.pathname===routeMemoryPath&&probeMode==='missing'){
      item.syntheticMissingProbe=true;item.status=404;
      await route.fulfill({status:404,contentType:'application/json',body:'{"detail":"Not Found"}'});return;
    }
    const headers={...item.headers};delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    item.serverReached=true;
    const result=await rpc({method:item.method,path:item.path,headers,
      body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    item.status=result.status;
    try{item.response=decode(result);}catch{}
    const out={...result.headers};delete out['content-length'];delete out['content-encoding'];
    if(item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&dropNextTurnResponse){
      dropNextTurnResponse=false;item.responseDroppedAfterServer=true;await route.abort('failed');return;
    }
    try{await route.fulfill({status:result.status,headers:out,body:Buffer.from(result.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  await target.addInitScript(()=>{
    window.__savedMemoryXss=0;window.__phSpeechCalls=0;
    try{Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak(){window.__phSpeechCalls++;},cancel(){},get speaking(){return false;}}});}catch{}
  });
}
const callCommand=async command=>{const response=await rpc({command});assert.equal(response.ok,true,`bridge command ${command}`);};
const probeReads=()=>requests.filter(item=>item.method==='GET'&&item.path.startsWith(routeMemoryPath));
async function waitForTurnCount(before){
  const deadline=Date.now()+10000;
  while(turns().length<=before&&Date.now()<deadline)await page.waitForTimeout(20);
  assert.equal(turns().length,before+1,'one turn request is issued');
  const current=turns().at(-1);
  while(!current.response&&!current.responseDroppedAfterServer&&Date.now()<deadline)await page.waitForTimeout(20);
  assert(current.response||current.responseDroppedAfterServer,'turn reaches a completed synthetic response or the deliberate drop gate');
  return current;
}
async function submit(text,{keyboard=false}={}){
  const before=turns().length;
  await page.locator('#assistant-text').fill(text);
  if(keyboard){
    await page.locator('#assistant-text').focus();await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>document.activeElement?.id),'assistant-send','keyboard Tab reaches the send action');
    await page.keyboard.press('Enter');
  }else await page.locator('#assistant-send').click();
  return waitForTurnCount(before);
}
async function ensureThread(){
  const select=page.locator('#assistant-private-select');
  if(await select.count()===0)throw new Error('Private conversation selector is missing');
  if(!await select.inputValue()){
    if(!await page.locator('#assistant-private-management').evaluate(node=>node.open))
      await page.locator('#assistant-private-management-toggle').click();
    await page.locator('#assistant-private-new').click();
    await page.waitForFunction(()=>!!document.querySelector('#assistant-private-select')?.value,{},{timeout:10000});
  }
}
async function reloadAndLogin(){
  await page.reload();
  if(await page.locator('#auth').isVisible()){
    await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');
    await page.locator('#auth-submit').click();
  }
  await page.locator('#grid .asset').first().waitFor();
  const panel=page.locator('#assistant-panel');
  if(!await panel.evaluate(node=>node.open))await panel.locator(':scope > summary').click();
  await page.locator('#assistant-private').waitFor({state:'visible',timeout:10000});
}
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),
    args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await installTransport(context);
  page=await context.newPage();page.on('pageerror',error=>errors.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');
  await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  const assistantPanel=page.locator('#assistant-panel');
  if(!await assistantPanel.evaluate(node=>node.open))await assistantPanel.locator(':scope > summary').click();
  await page.locator('#assistant-private').waitFor({state:'visible',timeout:10000});
  const initialProbeDeadline=Date.now()+10000;
  while(!probeReads().length&&Date.now()<initialProbeDeadline)await page.waitForTimeout(20);
  assert(probeReads().length>0,`private panel requests the optional probe; requests=${requests.map(item=>item.path).join(',')}`);

  const baseCapabilities=await page.evaluate(async()=>{
    const response=await fetch('/assistant/workspace/v1/capabilities?library_id=family-a');return response.json();
  });
  for(const key of ['saved_memory_cards','saved_memory_cards_enabled','memory_cards'])assert.equal(Object.hasOwn(baseCapabilities,key),false,`base capabilities stay closed to optional ${key}`);
  const probeDeadline=Date.now()+10000;
  while(!probeReads().some(item=>item.response?.available===true)&&Date.now()<probeDeadline)await page.waitForTimeout(20);
  assert(probeReads().some(item=>item.response?.available===true),'separate current-library probe enables saved-memory cards');
  const baseEntry=requests.find(item=>item.method==='GET'&&item.path.startsWith('/assistant/workspace/v1/capabilities'));
  assert(baseEntry?.response,'base capabilities request is observed');
  for(const key of ['saved_memory_cards','saved_memory_cards_enabled','memory_cards'])assert.equal(Object.hasOwn(baseEntry.response,key),false);
  const probeEntry=probeReads().find(item=>item.response?.available===true);
  const listEntry=requests.find(item=>item.method==='GET'&&item.path.startsWith('/assistant/workspace/v1/threads?'));
  const preferencesEntry=requests.find(item=>item.method==='GET'&&item.path.startsWith('/assistant/workspace/v1/preferences?'));
  assert(baseEntry&&listEntry&&preferencesEntry&&probeEntry&&requests.indexOf(baseEntry)<requests.indexOf(listEntry)&&
    requests.indexOf(listEntry)<requests.indexOf(preferencesEntry)&&requests.indexOf(preferencesEntry)<requests.indexOf(probeEntry),
    'optional probe follows base capabilities, list and preferences for the current library');
  pass('Member workspace reads a separate current-library saved-memory probe without changing base capabilities');

  const privatePanel=page.locator('#assistant-private');
  if(!await privatePanel.locator('#assistant-private-management').evaluate(node=>node.open))
    await privatePanel.locator('#assistant-private-management-toggle').click();
  await ensureThread();
  const initialMediaRequests=requests.filter(item=>/^\/assets\/[^/]+\/(?:thumbnail|open|original)(?:\?|$)/.test(item.path)).length;
  const speechBefore=await page.evaluate(()=>window.__phSpeechCalls);
  const storyQuery='搜索故事 野餐';
  const storyTurn=await submit(storyQuery);
  await cards().waitFor({state:'visible',timeout:10000});
  const storyCard=cards().first();
  assert.equal(await cards().count(),1,'kind-filtered story command renders exactly its matching story');
  assert.equal(await storyCard.locator('.assistant-memory-kind').innerText(),'已保存的故事');
  assert.equal(await storyCard.locator('h3').innerText(),fixtureInfo.story_title);
  assert.equal(await storyCard.locator('.assistant-memory-excerpt').innerText(),fixtureInfo.story_excerpt);
  assert.equal(await storyCard.locator('button,a,input,img,audio,video').count(),0,'memory cards contain no action or media elements');
  assert.equal(await page.evaluate(()=>window.__savedMemoryXss),0,'hostile source text executes no markup');
  assert.equal(storyTurn.body&&JSON.parse(storyTurn.body).text,storyQuery,'fresh story request is recorded');
  const storyPayload=JSON.parse(storyTurn.body);
  assert.deepEqual(storyPayload.accepts,['saved_memory_cards_v1'],'client opts in on the explicit command only');
  assert.equal(storyTurn.response.status,'completed');
  assert.equal(storyTurn.response.result.kind,'memory_cards');
  assert.equal(storyTurn.response.result.effect,null);assert.deepEqual(storyTurn.response.result.items,[]);
  assert.deepEqual(storyTurn.response.result.memory_cards.map(card=>card.id),[fixtureInfo.story_id]);
  assert.equal(requests.filter(item=>/^\/assets\/[^/]+\/(?:thumbnail|open|original)(?:\?|$)/.test(item.path)).length,initialMediaRequests,
    'fresh saved-memory cards do not hydrate or open media');
  assert.equal(await page.evaluate(()=>window.__phSpeechCalls),speechBefore,'fresh saved-memory cards do not start TTS');
  assert.equal(requests.some(item=>item.path.includes('/speech')),false,'no speech route is called for the card reply');
  pass('Fresh story card renders source title/excerpt as text with no script execution, action, media hydration, effect or speech');

  // A memoir-specific command proves the kind filter and the accessible card
  // layout at a phone-equivalent width and 150% font size.
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  const memoirTurn=await submit('找回忆册 野餐',{keyboard:true});
  await page.waitForFunction(title=>Array.from(document.querySelectorAll('#assistant-results .assistant-memory-card h3')).some(node=>node.textContent===title),
    fixtureInfo.memoir_title,{timeout:10000});
  assert.equal(await cards().count(),1,'memoir filter renders one memoir result');
  const memoirCard=cards().first();
  assert.equal(await memoirCard.locator('.assistant-memory-kind').innerText(),'已保存的回忆册');
  assert.equal(await memoirCard.locator('h3').innerText(),fixtureInfo.memoir_title);
  assert.equal(await memoirCard.locator('.assistant-memory-excerpt').innerText(),'野餐之后，我们记下了家人一起度过的时光。');
  assert.equal(await memoirCard.locator('button,a,input,img,audio,video').count(),0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'390px page has no horizontal overflow at 150% font size');
  assert(await memoirCard.evaluate(node=>node.scrollWidth<=node.clientWidth),'memoir card has no horizontal overflow');
  await page.screenshot({path:path.join(artifacts,'assistant-saved-memory-memoir-phone-150-zh.png'),fullPage:true});
  assert.deepEqual(JSON.parse(memoirTurn.body).accepts,['saved_memory_cards_v1']);
  pass('Fresh memoir card stays plain and fits a 390px viewport with 150% text; Tab and Enter send the query');

  // Lose a completed POST response and recover the existing request. The safe
  // persisted projection has no fresh card IDs, context, items or effects.
  const beforeLost=turns().length;dropNextTurnResponse=true;
  await page.locator('#assistant-text').fill('找回忆 野餐');await page.locator('#assistant-send').click();
  const lost=await waitForTurnCount(beforeLost);
  await page.locator('#assistant-private-recover').waitFor({state:'visible',timeout:10000});
  assert(lost.responseDroppedAfterServer);
  const lostBody=JSON.parse(lost.body);assert.deepEqual(lostBody.accepts,['saved_memory_cards_v1']);
  const recoverButton=page.locator('#assistant-private-recover');await recoverButton.click();
  await page.waitForFunction(()=>document.getElementById('assistant-private-recover')?.hidden===true||document.getElementById('assistant-private-recover')?.disabled===true,{},{timeout:10000});
  assert.equal(turns().length,beforeLost+1,'recovery does not repeat the turn POST');
  const recovered=requests.filter(item=>item.method==='GET'&&item.path.includes('/requests/'+lostBody.request_id+'?')).at(-1);
  assert(recovered?.response,'completed uncertain turn is read with the exact GET request ID');
  const recoveredResult=recovered.response.result;
  assert.equal(recovered.response.recovered,true);assert.equal(recoveredResult.effect,null);
  assert.equal(recoveredResult.context,null);assert.deepEqual(recoveredResult.items,[]);
  assert.equal(Object.hasOwn(recoveredResult,'memory_cards'),false,'recovery does not return fresh cards');
  assert.equal(JSON.stringify(recoveredResult).includes(fixtureInfo.story_id),false);
  assert.equal(JSON.stringify(recoveredResult).includes(fixtureInfo.memoir_id),false);
  assert.equal(await cards().count(),0,'recovered result does not render a fresh card');
  const history=await page.evaluate(async threadId=>{
    const response=await fetch(`/assistant/workspace/v1/threads/${threadId}?library_id=family-a`);return response.json();
  },lost.path.split('/')[5]);
  assert(history.exchanges.length>=3);
  for(const forbiddenId of [fixtureInfo.story_id,fixtureInfo.memoir_id])assert.equal(JSON.stringify(history).includes(forbiddenId),false,
    'history does not expose source IDs');
  for(const exchange of history.exchanges)for(const reference of exchange.cards){
    assert.deepEqual(Object.keys(reference).sort(),['actionable','count','type']);assert.equal(reference.actionable,false);
  }
  pass('GET recovery and history expose only the legacy safe result and opaque non-actionable reference counts');

  // Turning the server flag off or losing the optional probe must preserve the
  // exact legacy request shape with no accepts field.
  await callCommand('saved-memory-off');await reloadAndLogin();
  const offDeadline=Date.now()+10000;
  while(!probeReads().some(item=>item.response?.available===false)&&Date.now()<offDeadline)await page.waitForTimeout(20);
  const offProbe=probeReads().findLast(item=>item.response?.available===false);
  assert.equal(offProbe?.response?.available,false,`disabled feature probe reports unavailable; requests=${requests.map(item=>item.path).join(',')}`);
  await ensureThread();const beforeOff=turns().length;await page.locator('#assistant-text').fill('搜索故事 野餐');await page.locator('#assistant-send').click();
  const offTurn=await waitForTurnCount(beforeOff);
  await page.waitForFunction(n=>document.querySelectorAll('#assistant-private-recover').length===1&&
    (document.querySelector('#assistant-private-recover').hidden||document.querySelector('#assistant-private-recover').disabled),beforeOff,{timeout:10000});
  const offBody=JSON.parse(offTurn.body);assert.equal(Object.hasOwn(offBody,'accepts'),false,'disabled probe preserves legacy body');
  pass('Server-disabled saved-memory capability keeps the turn request in its legacy shape');

  await callCommand('saved-memory-on');probeMode='missing';await reloadAndLogin();
  const missingDeadline=Date.now()+10000;
  while(!probeReads().some(item=>item.syntheticMissingProbe)&&Date.now()<missingDeadline)await page.waitForTimeout(20);
  assert(probeReads().some(item=>item.syntheticMissingProbe),'missing optional probe is simulated as a 404');
  await ensureThread();const beforeMissing=turns().length;
  const missingTurn=await submit('搜索故事 野餐');
  const missingBody=JSON.parse(missingTurn.body);assert.equal(Object.hasOwn(missingBody,'accepts'),false,'missing probe preserves legacy body');
  pass('Missing optional capability probe leaves legacy turn JSON without card opt-in');

  assert.deepEqual(external,[],'browser makes no request outside the synthetic origin');
  assert.deepEqual(errors,[],'browser has no uncaught JavaScript errors');
  console.log(`CHECKPOINTS ${checks.length}`);
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{
  try{await page?.close();await context?.close();await browser?.close();}catch{}
  try{bridge.stdin.write('{"command":"quit"}\n');bridge.stdin.end();}catch{}
  if(bridge.exitCode===null)bridge.kill();
});
