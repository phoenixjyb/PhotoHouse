/* Explicit locale changes may restore a freshly authorized private thread. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-locale-resume-'));
fs.mkdirSync(artifacts,{recursive:true,mode:0o700});fs.chmodSync(artifacts,0o700);console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'../.venv/bin/python'),
  [path.join(__dirname,'assistant_workspace_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,omitNextThread=null,denyNextCapabilities=false,changeNextAccount=null,holdNextCapabilities=null,holdNextThreadRead=null,failNextThreadRead=false,threadReadFailureStatus=500,holdNextTurn=null;
const pendingRpc=new Map(),requests=[],pageErrors=[],blockedOrigins=[],gates=new Set();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const call=pendingRpc.get(result.id);if(call){pendingRpc.delete(result.id);call.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Synthetic API bridge exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Synthetic API bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const body=response=>JSON.parse(Buffer.from(response.body,'base64').toString('utf8'));
const jsonResponse=(response,status,value)=>({...response,status,headers:{...response.headers,'content-type':'application/json'},body:Buffer.from(JSON.stringify(value)).toString('base64')});
function gate(){let arrive,release,finish;const arrived=new Promise(resolve=>arrive=resolve),released=new Promise(resolve=>release=resolve),finished=new Promise(resolve=>finish=resolve);
  const value={arrived,released,finished,arrive,release,finish};gates.add(value);return value;}
let browser,context,page;
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),
    args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});context.setDefaultTimeout(15000);
  await context.addInitScript(()=>{
    window.__phSpeechCalls=0;window.__phMediaOpenCalls=0;window.__phGetUserMediaCalls=0;
    try{Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak(){window.__phSpeechCalls++;},cancel(){},get speaking(){return false;}}});}catch{}
    const media=navigator.mediaDevices||{};try{Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:media});}catch{}
    try{Object.defineProperty(media,'getUserMedia',{configurable:true,value:()=>{window.__phGetUserMediaCalls++;return Promise.reject(new Error('Synthetic capture must not start'));}});}catch{}
  });
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){blockedOrigins.push(url.origin);await route.abort();return;}
    const entry={method:request.method(),path:url.pathname+url.search,headers:await request.allHeaders(),body:request.postData()||''};requests.push(entry);
    const headers={...entry.headers};delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const response=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});entry.status=response.status;
    if(entry.method==='GET'&&url.pathname==='/auth/session'&&changeNextAccount){
      const account=changeNextAccount;changeNextAccount=null;const value=body(response);value.account_id=account;value.phone_login=account;
      const altered=jsonResponse(response,response.status,value);await route.fulfill({status:altered.status,headers:altered.headers,body:Buffer.from(altered.body,'base64')});return;
    }
    if(entry.method==='GET'&&url.pathname==='/assistant/workspace/v1/capabilities'&&denyNextCapabilities){
      denyNextCapabilities=false;const denied=jsonResponse(response,403,{detail:'synthetic permission change'});
      await route.fulfill({status:denied.status,headers:denied.headers,body:Buffer.from(denied.body,'base64')});return;
    }
    if(entry.method==='GET'&&url.pathname==='/assistant/workspace/v1/capabilities'&&holdNextCapabilities){
      const held=holdNextCapabilities;holdNextCapabilities=null;held.arrive();await held.released;held.finish();gates.delete(held);
    }
    if(entry.method==='GET'&&url.pathname==='/assistant/workspace/v1/threads'&&omitNextThread){
      const omit=omitNextThread;omitNextThread=null;const value=body(response);value.threads=value.threads.filter(thread=>thread.thread_id!==omit);
      const altered=jsonResponse(response,response.status,value);await route.fulfill({status:altered.status,headers:altered.headers,body:Buffer.from(altered.body,'base64')});return;
    }
    if(entry.method==='GET'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+$/.test(url.pathname)&&holdNextThreadRead){
      const held=holdNextThreadRead;holdNextThreadRead=null;entry.testHeldLocaleRead=true;held.arrive();await held.released;held.finish();gates.delete(held);
      if(failNextThreadRead){failNextThreadRead=false;entry.testOverrideStatus=threadReadFailureStatus;const denied=jsonResponse(response,threadReadFailureStatus,{detail:'superseded locale read'});await route.fulfill({status:denied.status,headers:denied.headers,body:Buffer.from(denied.body,'base64')});return;}
    }
    if(entry.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&holdNextTurn){
      const held=holdNextTurn;holdNextTurn=null;held.arrive();await held.released;held.finish();gates.delete(held);
    }
    const outputHeaders={...response.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try{await route.fulfill({status:response.status,headers:outputHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|abort|Invalid InterceptionId/.test(error.message))throw error;}
  });
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  const closeWorkspace=async()=>{if(await page.locator('#assistant-workspace-dialog').evaluate(dialog=>dialog.open)){await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.getElementById('assistant-workspace-dialog').open);}};
  const openAssistantPanel=async()=>{if(!await page.locator('#assistant-panel').evaluate(panel=>panel.open))await page.locator('#assistant-panel > summary').click();await page.locator('#assistant-private-new').waitFor({state:'visible'});};
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  for(const command of ['workspace-healthy','discovery-on']){const result=await rpc({command});assert.equal(result.ok,true);}
  await page.locator('#assistant-panel > summary').click();await page.locator('#assistant-private-new').waitFor({state:'visible'});
  const privatePrefix='/assistant/workspace/v1',threads=()=>requests.filter(item=>item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(item.path));
  const detailGets=id=>requests.filter(item=>item.method==='GET'&&item.path.startsWith(`${privatePrefix}/threads/${id}?`));
  const turn=async(text,revision)=>{
    const expected=threads().length+1,finished=page.waitForResponse(response=>response.request().method()==='POST'&&/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(new URL(response.url()).pathname));
    await page.locator('#assistant-text').fill(text);await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled);await page.locator('#assistant-send').click();
    const response=await finished;assert.equal(response.status(),200);
    await page.waitForFunction(()=>document.getElementById('assistant-cancel').hidden);
    assert.equal(threads().length,expected);const sent=JSON.parse(threads().at(-1).body);assert.equal(sent.expected_revision,revision);return sent;
  };
  await page.locator('#assistant-private-new').click();await page.waitForFunction(()=>!!document.getElementById('assistant-private-select')?.value);
  const threadId=await page.locator('#assistant-private-select').inputValue();await turn('找照片',0);await turn('找最近的照片',1);
  await page.locator('#assistant-text').fill('保留这个未发送草稿');
  const beforeLocale={turns:threads().length,details:detailGets(threadId).length,speech:await page.evaluate(()=>window.__phSpeechCalls),media:await page.evaluate(()=>window.__phMediaOpenCalls),asr:requests.filter(item=>item.path==='/assistant/v1/transcribe').length};
  const initialSourceLang=await page.evaluate(()=>document.documentElement.lang);await page.locator('#language').click();await page.waitForFunction(source=>document.documentElement.lang!==source,initialSourceLang);
  await page.locator('#memory-assistant-link').click();await page.locator('#assistant-workspace-dialog[open]').waitFor();
  try{await page.waitForFunction(id=>document.getElementById('assistant-private-select')?.value===id,threadId);}
  catch(error){console.error('resume state',JSON.stringify({threadId,selected:await page.locator('#assistant-private-select').inputValue(),draft:await page.locator('#assistant-text').inputValue(),
    status:await page.locator('#assistant-status').textContent(),privateStatus:await page.locator('#assistant-private-status').textContent(),trail:await page.locator('#assistant-turn-trail-list > li').count(),
    routes:requests.filter(item=>item.path.includes('/assistant/workspace/v1/')).map(item=>({method:item.method,path:item.path,status:item.status}))}));throw error;}
  assert.equal(await page.locator('#assistant-text').inputValue(),'保留这个未发送草稿');
  assert.equal(await page.locator('#assistant-turn-trail-list > li').count(),2,'the exact server-confirmed two exchanges return');
  assert.equal(detailGets(threadId).length,beforeLocale.details+1,'resume performs one fresh exact-thread read');
  assert.equal(threads().length,beforeLocale.turns,'locale restore does not submit a turn');
  assert.equal(await page.evaluate(()=>window.__phSpeechCalls),beforeLocale.speech,'locale restore does not start speech');
  assert.equal(await page.evaluate(()=>window.__phGetUserMediaCalls),0,'locale restore does not start microphone capture');
  assert.equal(requests.filter(item=>item.path==='/assistant/v1/transcribe').length,beforeLocale.asr,'locale restore does not transcribe');
  assert.equal(requests.filter(item=>/\/assets\/[^/]+\/(?:open|original)(?:\?|$)/.test(item.path)).length,beforeLocale.media,'locale restore does not open media');
  assert.equal(await page.locator('#assistant-results .assistant-result').count(),0,'fresh read leaves prior result cards unloaded');
  const freshDetail=detailGets(threadId).at(-1);assert.match(freshDetail.path,/library_id=family-a$/);
  await turn('查找最近的照片',2);
  assert.equal(threads().at(-1).path,`${privatePrefix}/threads/${threadId}/turns`,'an explicit follow-up uses the restored exact thread');
  assert.equal(JSON.parse(threads().at(-1).body).expected_revision,2,'an explicit follow-up uses the fresh server revision');
  const capturedDraft='captured before locale restore',latestDraft='actually typed while locale read was held';
  await closeWorkspace();await page.locator('#assistant-text').fill(capturedDraft);
  const nextLocaleDetailCount=detailGets(threadId).length,latestRead=gate();holdNextThreadRead=latestRead;
  const latestSourceLang=await page.evaluate(()=>document.documentElement.lang);await page.locator('#language').click();await page.waitForFunction(source=>document.documentElement.lang!==source,latestSourceLang);
  await latestRead.arrived;await page.locator('#memory-assistant-link').click();await page.locator('#assistant-workspace-dialog[open]').waitFor();
  await page.locator('#assistant-text').fill(latestDraft);latestRead.release();gates.delete(latestRead);await latestRead.finished;
  await page.waitForFunction(()=>document.getElementById('assistant-turn-trail-list')?.children.length===3);
  assert.equal(await page.locator('#assistant-text').inputValue(),latestDraft,'a newer user edit during the read wins over the captured draft');
  assert.equal(detailGets(threadId).length,nextLocaleDetailCount+1,'the gated locale read is exact-thread and one-shot');
  console.log('PASS a newer draft typed during the fresh read wins');

  await closeWorkspace();omitNextThread=threadId;const missingThreadDetailCount=detailGets(threadId).length;
  const missingSourceLang=await page.evaluate(()=>document.documentElement.lang);await page.locator('#language').click();await page.waitForFunction(source=>document.documentElement.lang!==source,missingSourceLang);
  await page.locator('#memory-assistant-link').click();await page.locator('#assistant-workspace-dialog[open]').waitFor();
  await page.waitForFunction(()=>document.getElementById('assistant-private-select')?.value==='');
  assert.equal(detailGets(threadId).length,missingThreadDetailCount,'a thread absent from the freshly authorized list is never read');
  assert.equal(await page.locator('#assistant-text').inputValue(),'','missing thread discards the current draft');
  console.log('PASS explicit locale round trip restores exact private history and an unsent draft with GET-only reads');
  console.log('PASS a thread removed from the fresh authorized list is not resumed');

  // A denied fresh capability check clears the previous thread and draft.
  await page.locator('#assistant-private-new').click();await page.waitForFunction(()=>!!document.getElementById('assistant-private-select')?.value);
  const deniedThread=await page.locator('#assistant-private-select').inputValue();await turn('查找照片',0);
  await closeWorkspace();await page.locator('#assistant-text').fill('permission scoped draft');denyNextCapabilities=true;
  const deniedSourceLang=await page.evaluate(()=>document.documentElement.lang);await page.locator('#language').click();await page.waitForFunction(source=>document.documentElement.lang!==source,deniedSourceLang);
  await page.locator('#memory-assistant-link').click();await page.locator('#assistant-workspace-dialog[open]').waitFor();
  await page.waitForFunction(()=>document.getElementById('assistant-private-select')?.value==='');
  assert.equal(await page.locator('#assistant-text').inputValue(),'','a denied capability refresh discards private draft');
  assert.equal(detailGets(deniedThread).length,0,'a denied capability refresh never reads the prior thread');
  console.log('PASS a fresh capability denial clears private resume state');

  await closeWorkspace();await page.reload();await page.locator('#grid .asset').first().waitFor();await openAssistantPanel();
  // A turn already in progress is never turned into a locale resume intent.
  await page.locator('#assistant-private-new').click();await page.waitForFunction(()=>!!document.getElementById('assistant-private-select')?.value);
  const pendingThread=await page.locator('#assistant-private-select').inputValue(),pending=gate();holdNextTurn=pending;
  const detailCountBeforePending=detailGets(pendingThread).length;
  await page.locator('#assistant-text').fill('查找正在等待的照片');await page.locator('#assistant-send').click();await pending.arrived;
  const postCount=threads().length,pendingSourceLang=await page.evaluate(()=>document.documentElement.lang);
  page.once('dialog',dialog=>{void dialog.accept();});await page.locator('#language').click();
  await page.waitForFunction(source=>document.documentElement.lang!==source,pendingSourceLang);
  assert.equal(threads().length,postCount,'locale action during a submitted turn does not duplicate it');pending.release();gates.delete(pending);
  await pending.finished;await page.waitForFunction(()=>document.getElementById('assistant-cancel').hidden);
  assert.equal(detailGets(pendingThread).length,detailCountBeforePending,'a pending turn is not converted into a resume read');
  console.log('PASS an in-flight turn is excluded from locale resume');

  // A superseded, delayed old-thread failure cannot clear a newer conversation.
  await closeWorkspace();await page.locator('#assistant-text').fill('old locale attempt');
  const oldReadCount=detailGets(pendingThread).length,oldRead=gate();holdNextThreadRead=oldRead;failNextThreadRead=true;
  const oldSourceLang=await page.evaluate(()=>document.documentElement.lang);await page.locator('#language').click();await page.waitForFunction(source=>document.documentElement.lang!==source,oldSourceLang);await oldRead.arrived;
  const supersedingSession=page.waitForResponse(response=>response.request().method()==='GET'&&new URL(response.url()).pathname==='/auth/session');
  await page.locator('#language').click();await supersedingSession;await openAssistantPanel();
  await page.locator('#assistant-private-new').click();await page.waitForFunction(()=>!!document.getElementById('assistant-private-select')?.value);
  const newerThread=await page.locator('#assistant-private-select').inputValue();await turn('查找更新后的照片',0);
  const newerDraft='newer valid conversation draft';await page.locator('#assistant-text').fill(newerDraft);
  oldRead.release();gates.delete(oldRead);await oldRead.finished;
  assert.equal(detailGets(pendingThread).length,oldReadCount+1,'the superseded request remains a single old-thread read');
  assert.equal(await page.locator('#assistant-private-select').inputValue(),newerThread,'old completion cannot replace the newer thread');
  assert.equal(await page.locator('#assistant-turn-trail-list > li').count(),1,'old completion cannot clear the newer conversation');
  assert.equal(await page.locator('#assistant-text').inputValue(),newerDraft,'old completion cannot clear the newer draft');
  console.log('PASS a superseded locale read cannot mutate the newer same-scope conversation');

  // A deliberate same-generation thread switch supersedes locale resumption.
  for(const failOldRead of [false,true]){
    await closeWorkspace();const oldThread=await page.locator('#assistant-private-select').inputValue();
    const oldRead=gate(),oldDetailCount=detailGets(oldThread).length,oldHeldCount=detailGets(oldThread).filter(item=>item.testHeldLocaleRead).length;holdNextThreadRead=oldRead;failNextThreadRead=failOldRead;threadReadFailureStatus=500;
    const sourceLang=await page.evaluate(()=>document.documentElement.lang);await page.locator('#language').click();await page.waitForFunction(source=>document.documentElement.lang!==source,sourceLang);await oldRead.arrived;
    const sessionsBeforeAction=requests.filter(item=>item.method==='GET'&&item.path==='/auth/session').length;
    await page.locator('#memory-assistant-link').click();await page.locator('#assistant-workspace-dialog[open]').waitFor();
    await page.locator('#assistant-private-management-toggle').click();
    await page.locator('#assistant-private-select').selectOption(threadId);
    await page.waitForFunction(id=>document.getElementById('assistant-private-select')?.value===id&&document.getElementById('assistant-turn-trail-list')?.children.length===3,threadId);
    const manualThread=await page.locator('#assistant-private-select').inputValue();
    const manualDraft=failOldRead?'draft after delayed failure':'draft after delayed read';await page.locator('#assistant-text').fill(manualDraft);
    oldRead.release();gates.delete(oldRead);await oldRead.finished;
    assert.equal(detailGets(oldThread).filter(item=>item.testHeldLocaleRead).length,oldHeldCount+1,'the locale operation held exactly one read of the old thread');
    assert.ok(detailGets(oldThread).length>oldDetailCount,'the old thread read was issued before the deliberate switch');
    assert.equal(requests.filter(item=>item.method==='GET'&&item.path==='/auth/session').length,sessionsBeforeAction,'the manual switch stays in the locale restore generation');
    if(failOldRead)assert.equal(detailGets(oldThread).filter(item=>item.testHeldLocaleRead).at(-1)?.testOverrideStatus,500,'the delayed old read fails after the manual switch');
    assert.equal(await page.locator('#assistant-private-select').inputValue(),manualThread,'old completion cannot replace the deliberate thread');
    assert.equal(await page.locator('#assistant-turn-trail-list > li').count(),3,'old completion cannot clear the deliberate thread history');
    assert.equal(await page.locator('#assistant-text').inputValue(),manualDraft,'old completion cannot clear the deliberate draft');
  }
  console.log('PASS deliberate same-generation thread changes supersede locale reads on success and failure');

  // A late completion from the previous generation cannot rebind after library navigation.
  await closeWorkspace();await page.locator('#assistant-text').fill('discard across library navigation');
  const oldDetailCount=detailGets(pendingThread).length,capabilityGate=gate();holdNextCapabilities=capabilityGate;
  const lateSourceLang=await page.evaluate(()=>document.documentElement.lang);await page.locator('#language').click();await page.waitForFunction(source=>document.documentElement.lang!==source,lateSourceLang);
  await capabilityGate.arrived;
  await page.locator('#library-select').evaluate(select=>{const option=document.createElement('option');option.value='family-b';option.textContent='family-b';select.append(option);select.value='family-b';select.dispatchEvent(new Event('change',{bubbles:true}));});
  capabilityGate.release();gates.delete(capabilityGate);await capabilityGate.finished;
  await page.waitForFunction(()=>document.getElementById('assistant-private-select')?.value==='');
  assert.equal(detailGets(pendingThread).length,oldDetailCount,'the old generation never reads a thread after library navigation');
  assert.equal(await page.locator('#assistant-text').inputValue(),'','library change discards the old draft');
  console.log('PASS late locale restore cannot rebind across a library generation change');

  await openAssistantPanel();await page.locator('#assistant-private-new').click();await page.waitForFunction(()=>!!document.getElementById('assistant-private-select')?.value);
  const accountThread=await page.locator('#assistant-private-select').inputValue();await turn('查找照片',0);
  await closeWorkspace();await page.locator('#assistant-text').fill('account scoped draft');
  const accountDetailCount=detailGets(accountThread).length;changeNextAccount='alternate-synthetic-account';
  const accountSourceLang=await page.evaluate(()=>document.documentElement.lang);await page.locator('#language').click();await page.waitForFunction(source=>document.documentElement.lang!==source,accountSourceLang);
  await page.waitForFunction(()=>document.getElementById('account-label').textContent==='alternate-synthetic-account');
  assert.equal(detailGets(accountThread).length,accountDetailCount,'a changed account never reads the old account thread');
  assert.equal(await page.locator('#assistant-text').inputValue(),'','an account change discards the old account draft');
  console.log('PASS changed account identity discards the old thread and draft');
  assert.deepEqual(pageErrors,[]);assert.deepEqual(blockedOrigins,[]);
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({requests:requests.length,pageErrors,blockedOrigins},null,2),{mode:0o600});
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  for(const item of gates){item.release();item.finish();}try{await context?.close();}catch{}try{await browser?.close();}catch{}
  try{bridge.stdin.write(JSON.stringify({command:'quit',id:++serial})+'\n');}catch{}
  await new Promise(resolve=>{if(bridge.exitCode!==null)return resolve();const timer=setTimeout(()=>{bridge.kill('SIGTERM');resolve();},3000);bridge.once('exit',()=>{clearTimeout(timer);resolve();});});
});
