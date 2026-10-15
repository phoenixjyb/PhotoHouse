/* Generated browser journey for negotiated private saved-memory cards. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-saved-memory-assistant-'));
fs.mkdirSync(artifacts,{recursive:true,mode:0o700});fs.chmodSync(artifacts,0o700);console.log('ARTIFACTS_DIR '+artifacts);
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
let probeMode='live',speechProbeMode='live',readingProbeMode='live',segmentReadingProbeMode='live',readerProbeMode='live',dropNextTurnResponse=false,readerGate=null,turnGate=null,openingSpeechGate=null,segmentSpeechGate=null;
let lateReaderCapabilityGate=null,lateReadingCapabilityGate=null,lateSegmentCapabilityGate=null;
let followupProbeMode='live',followupProbeGate=null,voiceTranscript='',reloadRequestStart=0;
let browser,context,page;
const pass=label=>{checks.push(label);console.log('PASS '+label);};
const deferredGate=()=>{let arrive,release;const reached=new Promise(resolve=>{arrive=resolve;}),waiting=new Promise(resolve=>{release=resolve;});return {reached,arrive,release,waiting};};
async function holdPrimaryActionCapabilities(){
  await page.waitForFunction(()=>{const state=window.__privateAssistantController?.state();return state?.savedMemoryAvailable===true&&state.savedMemorySpeechAvailable===true&&state.savedMemoryReaderAvailable===true&&state.savedMemoryReadingAvailable===true&&state.savedMemorySegmentReadingAvailable===true&&state.savedMemoryFollowupAvailable===true;},{},{timeout:10000});
  const reader=deferredGate(),opening=deferredGate(),segments=deferredGate();
  lateReaderCapabilityGate=reader;lateReadingCapabilityGate=opening;lateSegmentCapabilityGate=segments;
  await page.evaluate(()=>{const controller=window.__privateAssistantController;
    window.__latePrimaryActionCapabilityReads=Promise.all([controller.savedMemoryReaderCapabilities(),controller.savedMemoryReadingCapabilities(),controller.savedMemorySegmentReadingCapabilities()]);});
  let deadline;
  try{await Promise.race([Promise.all([reader.reached,opening.reached,segments.reached]),new Promise((_,reject)=>{deadline=setTimeout(()=>reject(new Error('Optional capability gates were not reached')),10000);})]);}
  catch(error){reader.release();opening.release();segments.release();throw error;}
  finally{clearTimeout(deadline);} 
  return {release(){reader.release();opening.release();segments.release();},complete(){return page.evaluate(()=>window.__latePrimaryActionCapabilityReads);}};
}
const decode=response=>JSON.parse(Buffer.from(response.body,'base64').toString('utf8'));
const turns=()=>requests.filter(item=>item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(item.path));
const cards=()=>page.locator('#assistant-results .assistant-memory-card');
const routeMemoryPath='/assistant/workspace/v1/saved-memory-capabilities';
const routeMemorySpeechPath='/assistant/workspace/v1/saved-memory-speech-capabilities';
const routeMemoryReaderPath='/assistant/workspace/v1/saved-memory-reader-capabilities';
const routeMemoryFollowupPath='/assistant/workspace/v1/saved-memory-followup-capabilities';
const routeMemoryReadingPath='/assistant/workspace/v1/saved-memory-reading-capabilities';
const routeMemorySegmentReadingPath='/assistant/workspace/v1/saved-memory-segment-reading-capabilities';
const routeMemoryActionPath='/assistant/workspace/v1/saved-memory-action-capabilities';
const readerCalls=()=>requests.filter(item=>item.method==='GET'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/memory-cards\//.test(item.path));
const speechCalls=()=>requests.filter(item=>item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/speech$/.test(item.path));
const openingSpeechCalls=()=>requests.filter(item=>item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/memory-cards\/(?:0|[1-9]|1[01])\/speech$/.test(item.path));
const segmentSpeechCalls=()=>requests.filter(item=>item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/memory-cards\/(?:0|[1-9]|1[01])\/segments\/(?:0|[1-9][0-9]?|1[01][0-9]|12[0-7])\/speech$/.test(item.path));
const segmentAudio=()=>{const data=Buffer.alloc(2),header=Buffer.alloc(44);header.write('RIFF',0);header.writeUInt32LE(38,4);header.write('WAVEfmt ',8);header.writeUInt32LE(16,16);header.writeUInt16LE(1,20);header.writeUInt16LE(1,22);header.writeUInt32LE(8000,24);header.writeUInt32LE(16000,28);header.writeUInt16LE(2,32);header.writeUInt16LE(16,34);header.write('data',36);header.writeUInt32LE(data.length,40);return Buffer.concat([header,data]);};
async function installTransport(target){
  await target.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    const item={method:request.method(),path:url.pathname+url.search,
      headers:await request.allHeaders(),body:request.postData()||'',serverReached:false};
    requests.push(item);
    const lateCapabilityGate=item.method==='GET'&&url.pathname===routeMemoryReaderPath?lateReaderCapabilityGate:
      item.method==='GET'&&url.pathname===routeMemoryReadingPath?lateReadingCapabilityGate:
      item.method==='GET'&&url.pathname===routeMemorySegmentReadingPath?lateSegmentCapabilityGate:null;
    if(lateCapabilityGate){if(url.pathname===routeMemoryReaderPath)lateReaderCapabilityGate=null;
      else if(url.pathname===routeMemoryReadingPath)lateReadingCapabilityGate=null;else lateSegmentCapabilityGate=null;
      lateCapabilityGate.arrive();await lateCapabilityGate.waiting;}
    if(item.method==='GET'&&url.pathname===routeMemorySegmentReadingPath){item.syntheticSegmentCapability=true;item.status=segmentReadingProbeMode==='missing'?404:segmentReadingProbeMode==='forbidden'?403:200;item.response=item.status===200?{version:1,available:true}:undefined;item.responseHeaders={'cache-control':'no-store'};await route.fulfill({status:item.status,contentType:'application/json',headers:item.responseHeaders,body:JSON.stringify(item.response||{detail:'Not Found'})});return;}
    if(item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/memory-cards\/(?:0|[1-9]|1[01])\/segments\/(?:0|[1-9][0-9]?|1[01][0-9]|12[0-7])\/speech$/.test(url.pathname)){
      if(segmentSpeechGate){const gate=segmentSpeechGate;segmentSpeechGate=null;gate.arrive();await gate.waiting;}
      item.syntheticSegmentSpeech=true;item.status=200;const requestId=item.headers['x-photohouse-request-id'],segment=Number(url.pathname.match(/\/segments\/(\d+)\/speech$/)?.[1]);
      item.responseHeaders={'cache-control':'no-store','content-type':'audio/wav','x-photohouse-tracking':'enabled','x-photohouse-playback-tracking':'enabled','x-photohouse-request-id':requestId,'x-photohouse-receipt-status':'succeeded','x-photohouse-reading-segment':String(segment),'x-photohouse-reading-segment-count':'3'};
      try{await route.fulfill({status:200,contentType:'audio/wav',headers:item.responseHeaders,body:segmentAudio()});}catch(error){if(!/closed|handled|cancel|abort|Invalid InterceptionId/i.test(error.message))throw error;}return;
    }
    if(item.method==='POST'&&url.pathname==='/assistant/v1/transcribe'&&voiceTranscript){
      item.status=200;
      item.syntheticTranscription=true;item.responseHeaders={'cache-control':'no-store','x-photohouse-tracking':'disabled','x-photohouse-receipt-status':'disabled'};
      await route.fulfill({status:200,contentType:'application/json',headers:item.responseHeaders,body:JSON.stringify({version:1,text:voiceTranscript,language:'zh'})});return;
    }
    if(item.method==='GET'&&url.pathname===routeMemoryPath&&probeMode==='missing'){
      item.syntheticMissingProbe=true;item.status=404;
      await route.fulfill({status:404,contentType:'application/json',body:'{"detail":"Not Found"}'});return;
    }
    if(item.method==='GET'&&url.pathname===routeMemorySpeechPath&&speechProbeMode==='missing'){
      item.syntheticMissingProbe=true;item.status=404;
      await route.fulfill({status:404,contentType:'application/json',body:'{"detail":"Not Found"}'});return;
    }
    if(item.method==='GET'&&url.pathname===routeMemoryReaderPath&&readerProbeMode==='missing'){
      item.syntheticMissingProbe=true;item.status=404;
      await route.fulfill({status:404,contentType:'application/json',body:'{"detail":"Not Found"}'});return;
    }
    if(item.method==='GET'&&url.pathname===routeMemoryFollowupPath&&followupProbeMode==='missing'){
      item.syntheticMissingProbe=true;item.status=404;
      await route.fulfill({status:404,contentType:'application/json',body:'{"detail":"Not Found"}'});return;
    }
    if(item.method==='GET'&&url.pathname===routeMemoryFollowupPath&&followupProbeGate){const gate=followupProbeGate;followupProbeGate=null;item.syntheticFollowupGate=true;gate.arrive();await gate.waiting;}
    if(item.method==='GET'&&url.pathname===routeMemoryReadingPath&&readingProbeMode==='missing'){
      item.syntheticMissingProbe=true;item.status=404;
      await route.fulfill({status:404,contentType:'application/json',body:'{"detail":"Not Found"}'});return;
    }
    if(item.method==='GET'&&url.pathname===routeMemoryReadingPath&&readingProbeMode==='forbidden'){
      item.syntheticMissingProbe=true;item.status=403;
      await route.fulfill({status:403,contentType:'application/json',body:'{"detail":"Forbidden"}'});return;
    }
    if(item.method==='GET'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/memory-cards\//.test(url.pathname)&&readerGate){const gate=readerGate;readerGate=null;gate.arrive();await gate.waiting;}
    if(item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/memory-cards\/(?:0|[1-9]|1[01])\/speech$/.test(url.pathname)&&openingSpeechGate){const gate=openingSpeechGate;openingSpeechGate=null;gate.arrive();await gate.waiting;}
    if(item.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&turnGate){const gate=turnGate;turnGate=null;gate.arrive();await gate.waiting;}
    const headers={...item.headers};delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    item.serverReached=true;
    const result=await rpc({method:item.method,path:item.path,headers,
      body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    item.status=result.status;
    item.responseHeaders=result.headers;
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
    window.__phAudioPlayCalls=0;window.__phAudioPauseCalls=0;window.__phRevokedAudioUrls=[];
    window.__phAudioPlayDeferred=false;window.__phAudioPlayStarted=false;window.__phAudioPlayRelease=null;
    window.__phMicCalls=0;window.__privateAssistantController=null;
    try{Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak(){window.__phSpeechCalls++;},cancel(){},get speaking(){return false;}}});}catch{}
    let privateApi=null;
    Object.defineProperty(window,'PhotoHousePrivateAssistant',{configurable:true,
      get(){return privateApi;},set(value){privateApi={...value,
        createController(options){const controller=value.createController(options);window.__privateAssistantController=controller;return controller;},
      };
      }});
    const media=window.HTMLMediaElement?.prototype;
    if(media){
      const originalPlay=media.play,originalPause=media.pause,originalLoad=media.load,originalRemoveAttribute=media.removeAttribute;
      Object.defineProperty(media,'paused',{configurable:true,get(){return this.__phPlaying!==true;}});
      Object.defineProperty(media,'ended',{configurable:true,get(){return this.__phEnded===true;}});
      media.play=function(){if(this.id!=='assistant-speech-audio')return originalPlay.call(this);window.__phAudioPlayCalls++;if(window.__phAudioPlayDeferred){window.__phAudioPlayStarted=true;return new Promise(resolve=>{window.__phAudioPlayRelease=()=>{window.__phAudioPlayDeferred=false;resolve();};});}this.__phPlaying=true;return Promise.resolve();};
      media.pause=function(){if(this.id!=='assistant-speech-audio')return originalPause.call(this);this.__phPlaying=false;window.__phAudioPauseCalls++;};
      media.load=function(){if(this.id!=='assistant-speech-audio')return originalLoad.call(this);this.__phEnded=false;};
      media.removeAttribute=function(name){if(this.id==='assistant-speech-audio'&&name==='src')this.__phPlaying=false;return originalRemoveAttribute.call(this,name);};
    }
    const NativeAudio=window.Audio;window.Audio=function(...args){return document.getElementById('assistant-speech-audio')||new NativeAudio(...args);};window.Audio.prototype=NativeAudio.prototype;
    const revoke=URL.revokeObjectURL.bind(URL);
    URL.revokeObjectURL=url=>{if(typeof url==='string'&&url.startsWith('blob:'))window.__phRevokedAudioUrls.push(url);return revoke(url);};
    try{const devices=navigator.mediaDevices,original=devices?.getUserMedia?.bind(devices);if(original)devices.getUserMedia=(...args)=>{window.__phMicCalls++;return original(...args);};}catch{}
  });
}
const callCommand=async command=>{const response=await rpc({command});assert.equal(response.ok,true,`bridge command ${command}`);};
const currentPageRequests=()=>requests.slice(reloadRequestStart);
const probeReads=()=>currentPageRequests().filter(item=>item.method==='GET'&&item.path.startsWith(routeMemoryPath));
const baseCapabilityReads=()=>currentPageRequests().filter(item=>item.method==='GET'&&item.path.startsWith('/assistant/workspace/v1/capabilities?'));
const speechProbeReads=()=>currentPageRequests().filter(item=>item.method==='GET'&&item.path.startsWith(routeMemorySpeechPath));
const readerProbeReads=()=>currentPageRequests().filter(item=>item.method==='GET'&&item.path.startsWith(routeMemoryReaderPath));
const followupProbeReads=()=>currentPageRequests().filter(item=>item.method==='GET'&&item.path.startsWith(routeMemoryFollowupPath));
const readingProbeReads=()=>currentPageRequests().filter(item=>item.method==='GET'&&item.path.startsWith(routeMemoryReadingPath));
const segmentReadingProbeReads=()=>currentPageRequests().filter(item=>item.method==='GET'&&item.path.startsWith(routeMemorySegmentReadingPath));
const actionProbeReads=()=>currentPageRequests().filter(item=>item.method==='GET'&&item.path.startsWith(routeMemoryActionPath));
async function waitForOptional403Recheck(probeReads,featureStateKey,label){
  const deadline=Date.now()+10000;
  const expectedPath='/assistant/workspace/v1/capabilities?library_id=family-a';
  let probe=null,recheck=null,state=null,settled=false;
  while(Date.now()<deadline){
    probe=probeReads().find(item=>item.status===403);
    if(probe){
      const probeIndex=requests.indexOf(probe);
      recheck=baseCapabilityReads().find(item=>requests.indexOf(item)>probeIndex&&item.path===expectedPath&&item.status===200&&item.response?.available===true&&item.response?.server_owned_turns===true);
      if(recheck){
        state=await page.evaluate(()=>window.__privateAssistantController.state());
        settled=state.capabilities?.available===true&&state.capabilities?.server_owned_turns===true&&state.capabilities?.reply_speech===true&&state.savedMemoryAvailable===true&&state.savedMemorySpeechAvailable===true&&state[featureStateKey]===false&&!state.locked;
        if(settled)break;
      }
    }
    await page.waitForTimeout(20);
  }
  assert(probe,`${label}: optional route returned its simulated 403`);
  assert(recheck,`${label}: a later exact-library base capability request completed successfully`);
  assert.equal(recheck.path,expectedPath,`${label}: recheck is for the current library`);
  assert.equal(recheck.status,200,`${label}: base capability recheck succeeded`);
  assert.equal(recheck.response?.available,true,`${label}: base capability response remains available`);
  assert.equal(recheck.response?.server_owned_turns,true,`${label}: base capability response preserves server-owned turns`);
  assert(settled,`${label}: base and saved-memory capabilities settle in the current unlocked scope`);
  assert.equal(state.locked,false,`${label}: the current scope remains unlocked`);
  assert.equal(state[featureStateKey],false,`${label}: only the optional capability remains unavailable`);
  return {probe,recheck};
}
const fakeTtsCalls=async()=>{const response=await rpc({command:'tts-calls'});assert.equal(response.ok,true);return response.calls;};
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
  const current=await waitForTurnCount(before);
  if(current.response?.status==='completed'&&current.response.result?.kind==='memory_cards'){
    // The bridge records a response before fetch JSON and the UI render finish.
    // Bind subsequent assertions to this exact revision and rendered cohort.
    await page.waitForFunction(({revision,ids})=>{
      const state=window.__privateAssistantController?.state(),result=state?.currentResult;
      const nodes=[...document.querySelectorAll('#assistant-results .assistant-memory-card')];
      return state?.revision===revision&&!state.pendingTurn&&result?.kind==='memory_cards'&&
        nodes.length===ids.length&&nodes.every((node,index)=>
          node.__assistantMemorySource===result.memory_cards[index]&&node.__assistantMemorySource?.id===ids[index]);
    },{revision:current.response.revision,ids:current.response.result.memory_cards.map(card=>card.id)},{timeout:10000});
  }
  return current;
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
  reloadRequestStart=requests.length;
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
  const actionProbeDeadline=Date.now()+10000;
  while(!actionProbeReads().some(item=>item.response?.available===true)&&Date.now()<actionProbeDeadline)await page.waitForTimeout(20);
  const actionProbeEntry=actionProbeReads().find(item=>item.response?.available===true);
  assert(actionProbeEntry,'separate saved-memory action probe reports available');
  const speechProbeDeadline=Date.now()+10000;
  while(!speechProbeReads().some(item=>item.response?.available===true)&&Date.now()<speechProbeDeadline)await page.waitForTimeout(20);
  const speechProbeEntry=speechProbeReads().find(item=>item.response?.available===true);
  assert(speechProbeEntry,'separate saved-memory speech probe reports the synthetic local provider and journal available');
  const readerProbeDeadline=Date.now()+10000;
  while(!readerProbeReads().some(item=>item.response?.available===true)&&Date.now()<readerProbeDeadline)await page.waitForTimeout(20);
  const readerProbeEntry=readerProbeReads().find(item=>item.response?.available===true);
  assert(readerProbeEntry,'separate saved-memory full-reader probe reports available');
  const followupProbeDeadline=Date.now()+10000;
  while(!followupProbeReads().some(item=>item.response?.available===true)&&Date.now()<followupProbeDeadline)await page.waitForTimeout(20);
  const followupProbeEntry=followupProbeReads().find(item=>item.response?.available===true);
  assert(followupProbeEntry,'separate saved-memory followup probe reports available');
  const readingProbeDeadline=Date.now()+10000;
  while(!readingProbeReads().some(item=>item.response?.available===true)&&Date.now()<readingProbeDeadline)await page.waitForTimeout(20);
  const readingProbeEntry=readingProbeReads().find(item=>item.response?.available===true);
  assert(readingProbeEntry,'separate current-library opening probe reports available');
  const segmentReadingProbeDeadline=Date.now()+10000;
  while(!segmentReadingProbeReads().some(item=>item.response?.available===true)&&Date.now()<segmentReadingProbeDeadline)await page.waitForTimeout(20);
  const segmentReadingProbeEntry=segmentReadingProbeReads().find(item=>item.response?.available===true);
  assert(segmentReadingProbeEntry,'separate current-library section-reading probe reports available');
  assert.deepEqual(Object.keys(segmentReadingProbeEntry.response).sort(),['available','version']);assert.deepEqual(segmentReadingProbeEntry.response,{version:1,available:true});
  const policyCard=page.locator('#saved-memory-list article').filter({hasText:'来源审阅回忆录重开检查'});
  await policyCard.waitFor({state:'visible',timeout:10000});
  await policyCard.locator('.saved-memory-copy button').click();
  await page.locator('#story-reader').waitFor({state:'visible',timeout:10000});
  assert.equal(await page.locator('#story-reader-memory-title').innerText(),'来源审阅回忆录重开检查',
    'existing shelf reopen accepts a saved story carrying source review policy');
  assert(requests.some(item=>item.method==='GET'&&item.path.startsWith(`/memory-stories/${fixtureInfo.profiled_story_id}?`)&&new URLSearchParams(item.path.split('?')[1]).get('library')==='family-a'&&new URLSearchParams(item.path.split('?')[1]).get('source_review')==='1'),
    'existing shelf reopen requests the source-reviewed saved story profile');
  await page.locator('#story-reader-close').click();
  await page.locator('#story-reader').waitFor({state:'hidden'});
  pass('Existing saved-story reopen preserves and validates the authorized source-review profile');
  const listEntry=requests.find(item=>item.method==='GET'&&item.path.startsWith('/assistant/workspace/v1/threads?'));
  const preferencesEntry=requests.find(item=>item.method==='GET'&&item.path.startsWith('/assistant/workspace/v1/preferences?'));
  assert(baseEntry&&listEntry&&preferencesEntry&&probeEntry&&requests.indexOf(baseEntry)<requests.indexOf(listEntry)&&
    requests.indexOf(listEntry)<requests.indexOf(preferencesEntry)&&requests.indexOf(preferencesEntry)<requests.indexOf(probeEntry)&&
    requests.indexOf(probeEntry)<requests.indexOf(speechProbeEntry)&&requests.indexOf(speechProbeEntry)<requests.indexOf(actionProbeEntry)&&requests.indexOf(actionProbeEntry)<requests.indexOf(readingProbeEntry)&&requests.indexOf(readingProbeEntry)<requests.indexOf(segmentReadingProbeEntry)&&requests.indexOf(segmentReadingProbeEntry)<requests.indexOf(readerProbeEntry)&&
    requests.indexOf(readerProbeEntry)<requests.indexOf(followupProbeEntry),
    'optional probes follow base capabilities, list and preferences for the current library');
  pass('Member workspace reads a separate exact version-1 section-reading probe without changing base capabilities');

  const privatePanel=page.locator('#assistant-private');
  if(!await privatePanel.locator('#assistant-private-management').evaluate(node=>node.open))
    await privatePanel.locator('#assistant-private-management-toggle').click();
  await ensureThread();
  const initialMediaRequests=requests.filter(item=>/^\/assets\/[^/]+\/(?:thumbnail|open|original)(?:\?|$)/.test(item.path)).length;
  const speechBefore=await page.evaluate(()=>window.__phSpeechCalls);
  const storyQuery='搜索故事 野餐';
  const delayedChinesePrimaryActions=await holdPrimaryActionCapabilities();
  const storyTurn=await submit(storyQuery);
  await cards().waitFor({state:'visible',timeout:10000});
  assert.equal(await cards().first().locator(':scope > .assistant-memory-primary-actions').count(),0,'Chinese card initially renders without a primary action row while optional capabilities are pending');
  delayedChinesePrimaryActions.release();await delayedChinesePrimaryActions.complete();
  await page.waitForFunction(()=>{const state=window.__privateAssistantController?.state(),card=document.querySelector('#assistant-results .assistant-memory-card'),row=card?.querySelector(':scope > .assistant-memory-primary-actions');
    return state?.savedMemoryReaderReady===true&&state?.savedMemoryReadingReady===true&&state?.savedMemorySegmentReadingAvailable===true&&
      row?.querySelector('.assistant-memory-open')&&row.querySelector('.assistant-memory-opening')&&row.querySelector('.assistant-memory-segment-reading')&&row.querySelector('.assistant-memory-segment-stop');},{},{timeout:10000});
  assert.equal(await cards().first().locator(':scope > .assistant-memory-primary-actions').count(),1,'late Chinese readiness creates exactly one direct primary action row');
  const storyCard=cards().first();
  await storyCard.screenshot({path:path.join(artifacts,'assistant-saved-memory-card-desktop-zh.png')});
  await page.screenshot({path:path.join(artifacts,'assistant-saved-memory-desktop-zh.png'),fullPage:true});
  assert.equal(await cards().count(),1,'kind-filtered story command renders exactly its matching story');
  assert.equal(await storyCard.locator('.assistant-memory-kind').innerText(),'已保存的故事');
  assert.equal(await storyCard.locator('h3').innerText(),fixtureInfo.story_title);
  assert.equal(await storyCard.locator('.assistant-memory-excerpt').innerText(),fixtureInfo.story_excerpt);
  assert.equal(await storyCard.locator('button,a,input,img,audio,video').count(),6,'the card exposes explicit reader, opening, section-read and local Stop actions plus two draft-only followups');
  assert.equal(await storyCard.locator('.assistant-memory-followup').count(),2,'ordinal followup chips are attached to the current source card');
  const allMemoriesChip=page.getByRole('button',{name:'全部回忆. 介绍这些回忆',exact:true});
  const summaryChip=storyCard.getByRole('button',{name:'讲了什么. 第1段回忆讲了什么',exact:true});
  const chaptersChip=storyCard.getByRole('button',{name:'章节. 第1段回忆有哪些章节',exact:true});
  assert.equal(await allMemoriesChip.innerText(),'全部回忆','overview prompt uses a compact localized visible label');
  assert.equal(await allMemoriesChip.getAttribute('aria-label'),'全部回忆. 介绍这些回忆','overview accessible name starts with its visible label and keeps its exact full prompt');
  assert.equal(await summaryChip.innerText(),'讲了什么','summary prompt uses a compact localized visible label');
  assert.equal(await summaryChip.getAttribute('aria-label'),'讲了什么. 第1段回忆讲了什么','summary accessible name starts with its visible label and keeps its exact ordinal prompt');
  assert.equal(await chaptersChip.innerText(),'章节','chapter prompt uses a compact localized visible label');
  assert.equal(await chaptersChip.getAttribute('aria-label'),'章节. 第1段回忆有哪些章节','chapter accessible name starts with its visible label and keeps its exact ordinal prompt');
  const primaryActions=storyCard.locator('.assistant-memory-primary-actions');
  assert.equal(await primaryActions.locator('button').count(),4,'reader and speech controls share one primary action row');
  assert.match(await storyCard.locator('.assistant-memory-open').innerText(),/打开已保存的故事|Open saved story/);
  assert.equal(await page.evaluate(()=>window.__savedMemoryXss),0,'hostile source text executes no markup');
  assert.equal(storyTurn.body&&JSON.parse(storyTurn.body).text,storyQuery,'fresh story request is recorded');
  const storyPayload=JSON.parse(storyTurn.body);
  const turnId=storyPayload.request_id;
  assert.deepEqual(storyPayload.accepts,['saved_memory_cards_v1','saved_memory_actions_v1'],'client opts into current-library saved-memory actions only after its exact capability probe');
  assert.equal(storyTurn.response.status,'completed');
  assert.equal(storyTurn.response.result.kind,'memory_cards');
  assert.equal(storyTurn.response.result.effect,null);assert.deepEqual(storyTurn.response.result.items,[]);
  assert.deepEqual(storyTurn.response.result.memory_cards.map(card=>card.id),[fixtureInfo.story_id]);
  assert.equal(requests.filter(item=>/^\/assets\/[^/]+\/(?:thumbnail|open|original)(?:\?|$)/.test(item.path)).length,initialMediaRequests,
    'fresh saved-memory cards do not hydrate or open media');
  assert.equal(await page.evaluate(()=>window.__phSpeechCalls),speechBefore,'fresh saved-memory cards do not start TTS');
  assert.equal(speechCalls().length,0,'no private speech route is called before explicit playback');
  assert.equal(openingSpeechCalls().length,0,'no opening speech route is called before explicit playback');
  assert.equal(segmentSpeechCalls().length,0,'no section audio is requested before the explicit section-reading tap');
  await page.evaluate(()=>{const card=document.querySelector('#assistant-results .assistant-memory-card');if(card){card.querySelector('h3').textContent='湖边的家庭散步';card.querySelector('.assistant-memory-excerpt').textContent='野餐后，一家人在湖边散步，记录了共同度过的时光。';}});
  const sectionButton=storyCard.locator('.assistant-memory-segment-reading');assert.match(await sectionButton.innerText(),/分段朗读故事第一章|Read the first chapter in sections/);
  assert.match(await storyCard.locator('.assistant-memory-segment-help').innerText(),/每次朗读一段|Reads one section at a time/);
  assert.match(await storyCard.locator('.assistant-memory-segment-help').innerText(),/麦克风保持关闭|microphone stays off/);
  const sectionTurnsBefore=turns().length,sectionMicBefore=await page.evaluate(()=>window.__phMicCalls),sectionOpensBefore=requests.filter(item=>/^\/assets\/[^/]+\/(?:open|original)(?:\?|$)/.test(item.path)).length;
  await sectionButton.click();
  const firstSectionDeadline=Date.now()+10000;while(segmentSpeechCalls().length<1&&Date.now()<firstSectionDeadline)await page.waitForTimeout(20);
  assert.equal(segmentSpeechCalls().length,1,'one explicit tap requests only the first section');
  const firstSection=segmentSpeechCalls()[0],firstSectionPayload=JSON.parse(firstSection.body),firstSectionId=firstSection.headers['x-photohouse-request-id'];
  assert.match(firstSection.path,new RegExp(`/requests/${turnId}/memory-cards/0/segments/0/speech$`));
  assert.deepEqual(Object.keys(firstSectionPayload).sort(),['expected_revision','library_id']);
  assert.deepEqual(firstSectionPayload,{library_id:'family-a',expected_revision:storyTurn.response.revision});
  assert.notEqual(firstSectionId,turnId);assert.equal(firstSection.headers['x-photohouse-parent-request-id'],turnId);
  assert.equal(firstSection.headers['x-photohouse-reading-segment'],undefined,'segment index comes from the exact route path, not an extra request header');
  await page.waitForFunction(()=>/朗读第 1\/3 段|Reading segment 1\/3/.test(document.querySelector('.assistant-memory-segment-reading')?.textContent||''));
  assert.equal(await sectionButton.isDisabled(),true,'the card cannot request another segment during playback');
  assert.equal(segmentSpeechCalls().length,1,'Continue is unavailable until playback ends');
  assert.equal(firstSection.responseHeaders['x-photohouse-reading-segment'],'0');assert.equal(firstSection.responseHeaders['x-photohouse-reading-segment-count'],'3');
  assert.equal(firstSection.responseHeaders['x-photohouse-playback-tracking'],'enabled','section audio carries the required playback outcome tracking contract');
  await storyCard.screenshot({path:path.join(artifacts,'assistant-memory-segment-1-playing-desktop-zh.png')});
  await page.setViewportSize({width:390,height:1100});await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  assert(await storyCard.locator('.assistant-memory-segment-stop').isVisible(),'active section exposes a card-local Stop beside the current memory');
  assert(await storyCard.locator('.assistant-memory-primary-actions').getByRole('button',{name:'停止朗读这一段',exact:true}).isVisible(),'late Chinese Stop control has a visible accessible label in the primary action row');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'active section Stop fits the 390px Chinese page at 150% text');
  const primaryPhoneGeometry=await primaryActions.evaluate(row=>{const rowRect=row.getBoundingClientRect(),card=row.closest('.assistant-memory-card'),cardRect=card.getBoundingClientRect();return {width:innerWidth,rowWidth:row.clientWidth,rowScrollWidth:row.scrollWidth,cardWidth:card.clientWidth,cardScrollWidth:card.scrollWidth,
    controls:[...row.querySelectorAll('button')].filter(button=>!button.hidden).map(button=>{const r=button.getBoundingClientRect();return {height:r.height,left:r.left,right:r.right,rowLeft:rowRect.left,rowRight:rowRect.right,cardLeft:cardRect.left,cardRight:cardRect.right};})};});
  assert(primaryPhoneGeometry.rowScrollWidth<=primaryPhoneGeometry.rowWidth,'primary action row wraps without its own horizontal overflow at Chinese 150%');
  assert(primaryPhoneGeometry.cardScrollWidth<=primaryPhoneGeometry.cardWidth,'primary action row fits within its source card at Chinese 150%');
  assert(primaryPhoneGeometry.controls.every(item=>item.height>=48&&item.left>=item.rowLeft-1&&item.right<=item.rowRight+1&&item.left>=item.cardLeft&&item.right<=item.cardRight),'visible primary controls retain 48px targets within the row and card at Chinese 150%');
  await storyCard.screenshot({path:path.join(artifacts,'assistant-memory-segment-playing-phone-150-zh.png')});
  await page.locator('#assistant-speech-audio').evaluate(node=>node.dispatchEvent(new Event('ended')));
  await page.waitForFunction(()=>/继续第 2\/3 段|Continue segment 2\/3/.test(document.querySelector('.assistant-memory-segment-reading')?.textContent||''));
  assert.equal(segmentSpeechCalls().length,1,'successful playback completion exposes an explicit Continue without auto-requesting it');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'section progress fits the 390px Chinese page at 150% text');
  assert(await storyCard.evaluate(node=>node.scrollWidth<=node.clientWidth),'section progress and controls wrap within the card');
  await storyCard.screenshot({path:path.join(artifacts,'assistant-memory-segment-continue-phone-150-zh.png')});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>{document.documentElement.style.fontSize='';});
  for(const expectedSegment of [1,2]){
    await sectionButton.click();
    const deadline=Date.now()+10000;while(segmentSpeechCalls().length<expectedSegment+1&&Date.now()<deadline)await page.waitForTimeout(20);
    assert.equal(segmentSpeechCalls().length,expectedSegment+1,'each Continue tap requests exactly one next segment');
    const item=segmentSpeechCalls().at(-1),payload=JSON.parse(item.body);
    assert.match(item.path,new RegExp(`/requests/${turnId}/memory-cards/0/segments/${expectedSegment}/speech$`));
    assert.deepEqual(Object.keys(payload).sort(),['expected_revision','library_id']);
    assert.equal(item.headers['x-photohouse-reading-segment'],undefined,'continuation sends no uncontracted segment request header');
    assert.equal(item.headers['x-photohouse-parent-request-id'],turnId);
    assert.equal(item.responseHeaders['x-photohouse-reading-segment'],String(expectedSegment));
    assert.equal(item.responseHeaders['x-photohouse-reading-segment-count'],'3');
    assert.equal(item.responseHeaders['x-photohouse-playback-tracking'],'enabled');
    await page.waitForFunction(segment=>new RegExp(`朗读第 ${segment+1}\\/3 段|Reading segment ${segment+1}\\/3`).test(document.querySelector('.assistant-memory-segment-reading')?.textContent||''),expectedSegment);
    await page.locator('#assistant-speech-audio').evaluate(node=>node.dispatchEvent(new Event('ended')));
    if(expectedSegment===1)await page.waitForFunction(()=>/继续第 3\/3 段|Continue segment 3\/3/.test(document.querySelector('.assistant-memory-segment-reading')?.textContent||''));
  }
  await page.waitForFunction(()=>/这段回忆已读完|This memory is finished/.test(document.querySelector('.assistant-memory-segment-status')?.textContent||''));
  assert.equal(segmentSpeechCalls().length,3,'the final segment completes with no automatic fourth request');
  assert.equal(turns().length,sectionTurnsBefore,'section narration does not submit or create an assistant turn');
  assert.equal(await page.evaluate(()=>window.__phMicCalls),sectionMicBefore,'section narration never starts microphone listening');
  assert.equal(requests.filter(item=>/^\/assets\/[^/]+\/(?:open|original)(?:\?|$)/.test(item.path)).length,sectionOpensBefore,'segment speech does not implicitly fetch full reader text or originals');
  await sectionButton.click();const stopAgainDeadline=Date.now()+10000;while(segmentSpeechCalls().length<4&&Date.now()<stopAgainDeadline)await page.waitForTimeout(20);
  await page.waitForFunction(()=>/朗读第 1\/3 段|Reading segment 1\/3/.test(document.querySelector('.assistant-memory-segment-reading')?.textContent||''));
  await storyCard.locator('.assistant-memory-segment-stop').click();
  await page.waitForFunction(()=>/分段朗读故事第一章|Read the first chapter in sections/.test(document.querySelector('.assistant-memory-segment-reading')?.textContent||'')&&document.querySelector('.assistant-memory-segment-status')?.hidden===true);
  assert.equal(segmentSpeechCalls().length,4,'Stop cancels the active segment without requesting Continue');
  pass('Saved story section narration is tap-by-tap, source-bound, and continues only after successful playback completion');
  await page.evaluate(({title,excerpt})=>{const card=document.querySelector('#assistant-results .assistant-memory-card');if(card){card.querySelector('h3').textContent=title;card.querySelector('.assistant-memory-excerpt').textContent=excerpt;}},{title:fixtureInfo.story_title,excerpt:fixtureInfo.story_excerpt});
  await page.evaluate(()=>{window.__phAudioPlayCalls=0;window.__phAudioPauseCalls=0;});
  assert(await page.locator('#assistant-play').isVisible(),'fresh owned card reply exposes an explicit playback action');
  assert.match(await page.locator('#assistant-play').innerText(),/播放语音回复|Play spoken reply/);
  const callCountBefore=await fakeTtsCalls();assert.equal(callCountBefore.length,0,'fake local TTS has no automatic calls');
  await page.locator('#assistant-play').click();
  const speechDeadline=Date.now()+10000;
  while((!speechCalls().at(-1)?.response||!(await fakeTtsCalls()).length)&&Date.now()<speechDeadline)await page.waitForTimeout(20);
  assert.equal(speechCalls().length,1,'one explicit click makes exactly one typed reply speech request');
  const speechRequest=speechCalls()[0],speechPayload=JSON.parse(speechRequest.body);
  assert.match(speechRequest.path,new RegExp(`/requests/${turnId}/speech$`),'speech is bound to the exact fresh turn');
  assert.deepEqual(Object.keys(speechPayload).sort(),['expected_revision','library_id']);
  assert.equal(speechPayload.library_id,'family-a');assert.equal(speechPayload.expected_revision,storyTurn.response.revision);
  assert.notEqual(speechRequest.headers['x-photohouse-request-id'],turnId,'speech receives a distinct request ID');
  assert.equal(speechRequest.headers['x-photohouse-parent-request-id'],turnId,'speech is correlated to the card-producing turn');
  assert.equal(speechRequest.status,200);assert.equal(speechRequest.response,undefined,'WAV response is not parsed as JSON');
  assert((speechRequest.headers.accept||'').includes('audio/wav'));
  assert.equal(speechRequest.responseHeaders['x-photohouse-request-id'],speechRequest.headers['x-photohouse-request-id']);
  assert.equal(speechRequest.responseHeaders['x-photohouse-tracking'],'enabled');
  assert.equal(speechRequest.responseHeaders['x-photohouse-receipt-status'],'succeeded');
  const fakeCalls=await fakeTtsCalls();assert.equal(fakeCalls.length,1);
  assert.equal(fakeCalls[0].reply,storyTurn.response.result.reply,'TTS receives the exact server-owned generic reply');
  assert.equal(fakeCalls[0].language,'zh');
  assert.equal(requests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/turns').length,0,
    'typed reply playback does not start listening or submit another turn');
  assert.equal(await page.evaluate(()=>window.__phSpeechCalls),speechBefore,'reply audio does not fall back to browser TTS');
  assert.equal(page.url(),'https://photohouse.test/ui','reply speech does not navigate to a reader');
  pass('Fresh story card stays inert until explicit play requests one correlated local rendering of its exact generic reply');
  await page.waitForFunction(()=>window.__phAudioPlayCalls===1&&document.getElementById('assistant-speech-audio')?.paused===false);
  const audio=page.locator('#assistant-speech-audio'),activeAudioUrl=await audio.getAttribute('src');
  assert.match(activeAudioUrl||'',/^blob:/,'explicit play starts held audio playback');
  const turnsBeforeSpeechLoss=turns().length,opensBeforeSpeechLoss=requests.filter(item=>/\/assets\/[^/]+\/open(?:\?|$)/.test(item.path)).length,revokedBeforeSpeechLoss=(await page.evaluate(()=>window.__phRevokedAudioUrls.length));
  const micCallsBeforeSpeechLoss=await page.evaluate(()=>window.__phMicCalls);
  await callCommand('saved-memory-speech-off');
  assert.equal(await page.evaluate(()=>window.__privateAssistantController.savedMemorySpeechCapabilities()),false,
    'the explicit capability refresh observes speech disabled');
  const stopped=await page.waitForFunction(expectedRevocations=>document.getElementById('assistant-speech-audio')?.paused===true&&
    document.getElementById('assistant-speech')?.hidden===true&&document.getElementById('assistant-speech-stop')?.hidden===true&&
    window.__phRevokedAudioUrls.length===expectedRevocations,revokedBeforeSpeechLoss+1,{timeout:3000}).then(()=>true).catch(()=>false);
  if(!stopped)console.error('SPEECH_LOSS_STATE',JSON.stringify(await page.evaluate(()=>({controller:window.__privateAssistantController?.state(),
    audio:{paused:document.getElementById('assistant-speech-audio')?.paused,src:document.getElementById('assistant-speech-audio')?.getAttribute('src')},
    speechHidden:document.getElementById('assistant-speech')?.hidden,stopHidden:document.getElementById('assistant-speech-stop')?.hidden,
    playCalls:window.__phAudioPlayCalls,pauseCalls:window.__phAudioPauseCalls,revoked:window.__phRevokedAudioUrls}))));
  assert.equal(stopped,true,'active private reply audio stops after the speech capability is lost');
  assert.equal(await audio.getAttribute('src'),null,'speech capability loss removes the active audio source');
  assert(await audio.evaluate(node=>node.hidden),'audio element remains hidden from the page');
  assert.equal(await page.locator('#assistant-play').isDisabled(),false,'speech loss leaves no stuck disabled play control');
  assert.equal(await cards().count(),1,'speech loss retains the saved-memory card');
  assert.equal(await cards().first().locator('h3').innerText(),fixtureInfo.story_title,'the source card text remains visible');
  assert.equal(turns().length,turnsBeforeSpeechLoss,'speech capability loss sends no new turn');
  assert.equal(requests.filter(item=>/\/assets\/[^/]+\/open(?:\?|$)/.test(item.path)).length,opensBeforeSpeechLoss,
    'speech capability loss does not open a reader or media');
  assert.equal(await page.evaluate(()=>window.__phMicCalls),micCallsBeforeSpeechLoss,'speech capability loss never starts microphone capture');
  assert.deepEqual((await page.evaluate(()=>window.__phRevokedAudioUrls)).slice(-1),[activeAudioUrl],'the active object URL is revoked');
  assert.equal(await page.evaluate(()=>window.__phAudioPauseCalls)>0,true,'active playback is explicitly paused');
  pass('Losing the saved-memory speech probe while audio is active pauses and revokes it while retaining the card');

  await callCommand('reply-speech-on');
  assert.equal(await page.evaluate(()=>window.__privateAssistantController.savedMemorySpeechCapabilities()),true);
  assert.equal(await page.evaluate(()=>window.__privateAssistantController.savedMemoryReadingCapabilities()),true);
  assert.equal(await page.evaluate(()=>window.__privateAssistantController.savedMemorySegmentReadingCapabilities()),true);
  const openingTurn=await submit(storyQuery),openingTurnId=JSON.parse(openingTurn.body).request_id;
  const openingCard=cards().first(),openingButton=openingCard.locator('.assistant-memory-opening'),turnsBeforeOpening=turns().length;
  assert.match(await openingButton.innerText(),/朗读开篇|Read opening/);
  await page.evaluate(()=>{
    const devices=navigator.mediaDevices;
    devices.getUserMedia=async()=>{window.__phMicCalls++;const track={stopped:false,stop(){this.stopped=true;window.__phTrackStopped=true;}};window.__phVoiceTrack=track;return {getTracks:()=>[track]};};
    window.__phTrackStopped=false;window.__phAudioProcessors=[];
    window.__phAudioContextCloseDeferred=false;window.__phAudioContextCloseStarted=false;window.__phAudioContextCloseRelease=null;
    window.AudioContext=class{constructor(){this.sampleRate=16000;this.destination={};}createMediaStreamSource(){return {connect(){},disconnect(){}};}createScriptProcessor(){const processor={onaudioprocess:null,connect(){},disconnect(){}};window.__phAudioProcessors.push(processor);return processor;}resume(){return Promise.resolve();}close(){if(window.__phAudioContextCloseDeferred){window.__phAudioContextCloseStarted=true;return new Promise(resolve=>{window.__phAudioContextCloseRelease=()=>{window.__phAudioContextCloseDeferred=false;resolve();};});}return Promise.resolve();}};
    window.__phFeed=(value,count)=>{const processor=window.__phAudioProcessors.at(-1);if(!processor?.onaudioprocess)return false;const data=new Float32Array(count);data.fill(value);processor.onaudioprocess({inputBuffer:{getChannelData:()=>data}});return true;};
  });
  const micBeforeSectionConflict=await page.evaluate(()=>window.__phMicCalls),asrBeforeSectionConflict=requests.filter(item=>item.path==='/assistant/v1/transcribe').length;
  await openingCard.locator('.assistant-memory-segment-reading').click();
  const conflictSpeechDeadline=Date.now()+10000;while(segmentSpeechCalls().length<5&&Date.now()<conflictSpeechDeadline)await page.waitForTimeout(20);
  assert.equal(segmentSpeechCalls().length,5,'capture conflict starts from one explicit section tap');
  await page.waitForFunction(()=>/朗读第 1\/3 段|Reading segment 1\/3/.test(document.querySelector('.assistant-memory-segment-reading')?.textContent||''));
  await page.locator('#assistant-voice-start').click();
  await page.waitForFunction(()=>document.getElementById('assistant-voice-session')?.dataset.phase==='listening'&&document.getElementById('assistant-stop')?.hidden===false);
  await page.waitForFunction(()=>document.getElementById('assistant-speech-audio')?.paused===true&&document.getElementById('assistant-speech-audio')?.getAttribute('src')===null);
  const turnsDuringCapture=turns().length;
  await page.evaluate(()=>document.getElementById('assistant-text').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true,bubbles:true})));
  assert.equal(turns().length,turnsDuringCapture,'keyboard shortcut cannot submit while continuous capture owns the voice session');
  assert.equal(await page.evaluate(()=>document.getElementById('assistant-send').disabled),true,'capture state keeps the existing Send guard active for keyboard input');
  assert(await openingCard.locator('.assistant-memory-segment-stop').isHidden(),'manual capture clears the card-local section Stop state');
  assert.match(await openingCard.locator('.assistant-memory-segment-reading').innerText(),/分段朗读故事第一章|Read the first chapter in sections/,'manual capture clears section progress before recording');
  assert.equal(await page.evaluate(()=>window.__phMicCalls),micBeforeSectionConflict+1,'section cancellation allows only the explicit continuous-capture request');
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>window.__phMicCalls),micBeforeSectionConflict+1,'canceled section audio does not restart microphone capture');
  await page.locator('#assistant-voice-end').click();
  await page.waitForFunction(()=>window.__phVoiceTrack?.stopped===true);
  assert.equal(requests.filter(item=>item.path==='/assistant/v1/transcribe').length,asrBeforeSectionConflict,'canceling the section conflict never submits audio for ASR');
  pass('Explicit continuous capture cancels section playback before listening without narration capture or automatic restart');
  await page.evaluate(()=>{window.__phAudioPlayCalls=0;window.__phAudioPauseCalls=0;});
  const micBeforeOpening=await page.evaluate(()=>window.__phMicCalls);
  await page.locator('#assistant-voice-start').click();
  await page.waitForFunction(()=>document.getElementById('assistant-voice-session')?.dataset.phase==='listening');
  await page.waitForFunction(before=>window.__phMicCalls===before+1&&!!window.__phVoiceTrack,micBeforeOpening);
  await page.waitForFunction(()=>document.getElementById('assistant-stop')?.hidden===false);
  const openingPlayBaseline=await page.evaluate(()=>window.__phAudioPlayCalls);
  const openingGate=deferredGate();openingSpeechGate=openingGate;
  await openingButton.click();await openingGate.reached;
  assert.match(await openingButton.innerText(),/正在准备开篇|Preparing opening/,'card action exposes preparing state');
  assert.equal(await openingButton.isDisabled(),true,'duplicate opening requests are blocked while preparing');
  assert.equal(await page.locator('#assistant-speech-stop').isVisible(),true,'Stop is available while synthesis is pending');
  await openingCard.screenshot({path:path.join(artifacts,'assistant-memory-opening-preparing-desktop-zh.png')});
  await page.evaluate(()=>{window.__phAudioPlayDeferred=true;window.__phAudioPlayStarted=false;});
  const foregroundVoiceEnded=await page.waitForFunction(()=>window.__phTrackStopped===true&&document.getElementById('assistant-voice-end')?.hidden===true&&document.getElementById('assistant-voice-start')?.hidden===false,{},{timeout:3000}).then(()=>true).catch(()=>false);
  assert.equal(foregroundVoiceEnded,true,'opening action ends the active foreground voice session');
  openingGate.release();
  const openingDeadline=Date.now()+10000;
  while((!openingSpeechCalls().at(-1)?.responseHeaders||(await fakeTtsCalls()).length<2)&&Date.now()<openingDeadline)await page.waitForTimeout(20);
  assert.equal(openingSpeechCalls().length,1,'one card click makes one source-opening speech request');
  const openingRequest=openingSpeechCalls()[0],openingPayload=JSON.parse(openingRequest.body);
  assert.match(openingRequest.path,new RegExp(`/requests/${openingTurnId}/memory-cards/0/speech$`));
  assert.deepEqual(Object.keys(openingPayload).sort(),['expected_revision','library_id']);
  assert.deepEqual(openingPayload,{library_id:'family-a',expected_revision:openingTurn.response.revision});
  assert.notEqual(openingRequest.headers['x-photohouse-request-id'],openingTurnId);
  assert.equal(openingRequest.headers['x-photohouse-parent-request-id'],openingTurnId);
  assert.equal(openingRequest.status,200);assert.equal(openingRequest.response,undefined);
  assert.equal(openingRequest.responseHeaders['x-photohouse-tracking'],'enabled');
  assert.equal(openingRequest.responseHeaders['x-photohouse-receipt-status'],'succeeded');
  const openingCalls=await fakeTtsCalls();assert.equal(openingCalls.length,2);
  assert.equal(openingCalls[1].reply,fixtureInfo.story_excerpt,'TTS receives the saved first chapter narration');
  assert.equal(openingCalls[1].language,'zh');
  const openingAudio=page.locator('#assistant-speech-audio');
  await page.waitForFunction(()=>window.__phAudioPlayStarted===true);
  assert.match(await openingButton.innerText(),/正在准备开篇|Preparing opening/,'the card stays in preparing state until media play resolves');
  assert.equal(await page.locator('#assistant-speech-stop').isVisible(),true,'Stop remains available while media play is pending');
  await page.locator('#assistant-speech-stop').click();
  assert.match(await openingButton.innerText(),/朗读开篇|Read opening/,'Stop during pending media play clears the opening action');
  assert.equal(await page.locator('#assistant-speech-stop').isVisible(),false,'Stop immediately releases the ended operation');
  const retryGate=deferredGate();openingSpeechGate=retryGate;await openingButton.click();await retryGate.reached;
  assert.match(await openingButton.innerText(),/正在准备开篇|Preparing opening/,'a newer opening attempt owns the card while the old play promise is pending');
  assert.equal(await page.locator('#assistant-speech-stop').isVisible(),true,'the newer operation owns the global Stop control');
  await page.evaluate(()=>window.__phAudioPlayRelease?.());
  await page.waitForFunction(()=>window.__phAudioPlayDeferred===false&&document.getElementById('assistant-speech-audio')?.paused===true&&
    document.getElementById('assistant-speech-stop')?.hidden===false&&/正在准备开篇|Preparing opening/.test(document.querySelector('.assistant-memory-opening')?.textContent||''));
  assert.equal(await page.evaluate(()=>document.getElementById('assistant-speech-audio')?.getAttribute('src')),null,'stale cleanup leaves the newer request audio element untouched');
  pass('opening audio waits for confirmed play and stale Stop cleanup preserves a newer operation');
  retryGate.release();
  const resumedOpeningDeadline=Date.now()+10000;
  while((openingSpeechCalls().length<2||!openingSpeechCalls().at(-1)?.responseHeaders||(await fakeTtsCalls()).length<3)&&Date.now()<resumedOpeningDeadline)await page.waitForTimeout(20);
  assert.equal(openingSpeechCalls().length,2,'explicit retry makes one fresh opening request after Stop');
  const resumedOpeningRequest=openingSpeechCalls()[1],resumedOpeningPayload=JSON.parse(resumedOpeningRequest.body);
  assert.match(resumedOpeningRequest.path,new RegExp(`/requests/${openingTurnId}/memory-cards/0/speech$`));
  assert.deepEqual(resumedOpeningPayload,{library_id:'family-a',expected_revision:openingTurn.response.revision});
  assert.equal(resumedOpeningRequest.headers['x-photohouse-parent-request-id'],openingTurnId);
  const resumedOpeningCalls=await fakeTtsCalls();assert.equal(resumedOpeningCalls.length,3);
  assert.equal(resumedOpeningCalls[2].reply,fixtureInfo.story_excerpt,'explicit retry synthesizes only the first chapter narration');
  await page.waitForFunction(base=>window.__phAudioPlayCalls===base+2&&document.getElementById('assistant-speech-audio')?.paused===false,openingPlayBaseline);
  const openingAudioUrl=await openingAudio.getAttribute('src');assert.match(openingAudioUrl||'',/^blob:/);
  assert.match(await openingButton.innerText(),/停止朗读|Stop reading/,'the active card action exposes a stop state');
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  await page.screenshot({path:path.join(artifacts,'assistant-memory-opening-playing-phone-150-zh.png'),fullPage:true});
  await openingCard.screenshot({path:path.join(artifacts,'assistant-memory-opening-playing-card-phone-150-zh.png')});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'playing state fits a 390px viewport at 150% text');
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>{document.documentElement.style.fontSize='';});
  const playCallsBeforeManualStart=await page.evaluate(()=>window.__phAudioPlayCalls),openingPostsBeforeManualStart=openingSpeechCalls().length;
  await page.evaluate(()=>{
    const devices=navigator.mediaDevices;window.__phManualReadyTrack=null;
    devices.getUserMedia=async()=>{window.__phMicCalls++;const track={stopped:false,stop(){this.stopped=true;}};window.__phManualReadyTrack=track;return {getTracks:()=>[track]};};
  });
  await page.evaluate(()=>document.getElementById('assistant-mic').click());
  await page.waitForFunction(()=>document.getElementById('assistant-stop')?.hidden===false&&document.getElementById('assistant-mic')?.getAttribute('aria-pressed')==='true');
  await page.waitForFunction(()=>document.getElementById('assistant-speech-audio')?.paused===true&&document.getElementById('assistant-speech-audio')?.getAttribute('src')===null);
  assert.equal(await page.evaluate(()=>window.__phAudioPlayCalls),playCallsBeforeManualStart,'explicit mic start cancels opening audio without restarting it');
  assert.match(await openingButton.innerText(),/朗读开篇|Read opening/,'explicit capture clears the opening playback action');
  assert.equal(openingSpeechCalls().length,openingPostsBeforeManualStart,'starting capture sends no additional opening request');
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>window.__phAudioPlayCalls),playCallsBeforeManualStart,'stopped source audio does not relisten after capture starts');
  await page.locator('#assistant-recording-cancel').click();
  await page.waitForFunction(()=>window.__phManualReadyTrack?.stopped===true);
  assert.equal(await page.evaluate(url=>window.__phRevokedAudioUrls.includes(url),openingAudioUrl),true,'Stop revokes the opening audio URL');
  assert.equal(await page.evaluate(()=>window.__phMicCalls),micBeforeOpening+2,'opening playback and the explicit manual start make no automatic microphone restart');
  assert.equal(await page.evaluate(()=>window.__phVoiceTrack.stopped),true,'opening playback ends the active foreground voice session');
  assert.equal(turns().length,turnsBeforeOpening,'opening playback does not submit a new assistant turn');
  const manualTurnCount=turns().length,manualAsrCount=requests.filter(item=>item.path==='/assistant/v1/transcribe').length;
  await page.evaluate(()=>{
    const devices=navigator.mediaDevices;window.__phManualCaptureCalls=0;window.__phManualReadyTrack=null;
    devices.getUserMedia=async()=>{window.__phManualCaptureCalls++;const track={stopped:false,stop(){this.stopped=true;}};window.__phManualReadyTrack=track;return {getTracks:()=>[track]};};
  });
  await page.locator('#assistant-text').fill('保留这段手动录音前的草稿');
  await page.evaluate(()=>document.getElementById('assistant-mic').click());
  await page.waitForFunction(()=>document.getElementById('assistant-stop')?.hidden===false&&document.getElementById('assistant-mic')?.getAttribute('aria-pressed')==='true');
  const readyCaptureGate=deferredGate();openingSpeechGate=readyCaptureGate;await openingButton.click();await readyCaptureGate.reached;
  assert.equal(await page.evaluate(()=>window.__phManualReadyTrack?.stopped),true,'opening discards and stops an already-ready manual capture');
  assert.equal(await page.locator('#assistant-stop').isHidden(),true,'manual capture controls clear before source speech starts');
  assert.equal(await page.locator('#assistant-text').inputValue(),'保留这段手动录音前的草稿','opening preserves the typed draft');
  assert.equal(requests.filter(item=>item.path==='/assistant/v1/transcribe').length,manualAsrCount,'discarding manual capture never submits it for ASR');
  assert.equal(turns().length,manualTurnCount,'discarding manual capture never sends a turn');
  readyCaptureGate.release();
  const readyCaptureDeadline=Date.now()+10000;
  while((!openingSpeechCalls().at(-1)?.responseHeaders||(await fakeTtsCalls()).length<4)&&Date.now()<readyCaptureDeadline)await page.waitForTimeout(20);
  assert.equal(openingSpeechCalls().length,3,'ready capture interruption requests only the explicit opening audio');
  await page.waitForFunction(base=>window.__phAudioPlayCalls===base+3&&document.getElementById('assistant-speech-audio')?.paused===false,openingPlayBaseline);
  await page.locator('#assistant-speech-stop').click();
  await page.waitForFunction(()=>document.getElementById('assistant-speech-audio')?.paused===true);

  await page.evaluate(()=>{
    const devices=navigator.mediaDevices;window.__phLatePermissionTrack=null;window.__phManualPermissionResolve=null;
    devices.getUserMedia=()=>{window.__phManualCaptureCalls++;return new Promise(resolve=>{window.__phManualPermissionResolve=()=>{const track={stopped:false,stop(){this.stopped=true;}};window.__phLatePermissionTrack=track;resolve({getTracks:()=>[track]});};});};
  });
  await page.locator('#assistant-text').fill('权限等待期间继续保留草稿');
  await page.evaluate(()=>document.getElementById('assistant-mic').click());
  await page.waitForFunction(()=>typeof window.__phManualPermissionResolve==='function');
  const pendingCaptureGate=deferredGate();openingSpeechGate=pendingCaptureGate;await openingButton.click();await pendingCaptureGate.reached;
  assert.equal(await page.locator('#assistant-stop').isHidden(),true,'opening cancels a manual capture still waiting for microphone permission');
  assert.equal(await page.locator('#assistant-text').inputValue(),'权限等待期间继续保留草稿','permission-pending interruption preserves the typed draft');
  assert.equal(requests.filter(item=>item.path==='/assistant/v1/transcribe').length,manualAsrCount,'permission-pending capture is never submitted for ASR');
  assert.equal(turns().length,manualTurnCount,'permission-pending capture sends no assistant turn');
  await page.evaluate(()=>window.__phManualPermissionResolve?.());
  await page.waitForFunction(()=>window.__phLatePermissionTrack?.stopped===true);
  pendingCaptureGate.release();
  const pendingCaptureDeadline=Date.now()+10000;
  while((!openingSpeechCalls().at(-1)?.responseHeaders||(await fakeTtsCalls()).length<5)&&Date.now()<pendingCaptureDeadline)await page.waitForTimeout(20);
  assert.equal(openingSpeechCalls().length,4,'permission-pending capture interruption requests only the explicit opening audio');
  await page.waitForFunction(base=>window.__phAudioPlayCalls===base+4&&document.getElementById('assistant-speech-audio')?.paused===false,openingPlayBaseline);
  await page.locator('#assistant-speech-stop').click();
  await page.waitForFunction(()=>document.getElementById('assistant-speech-audio')?.paused===true);
  const openingPostsBeforeCloseRace=openingSpeechCalls().length;
  await page.evaluate(()=>{
    const devices=navigator.mediaDevices;window.__phManualCloseTrack=null;window.__phAudioContextCloseDeferred=true;window.__phAudioContextCloseStarted=false;
    devices.getUserMedia=async()=>{const track={stopped:false,stop(){this.stopped=true;}};window.__phManualCloseTrack=track;return {getTracks:()=>[track]};};
  });
  await page.evaluate(()=>document.getElementById('assistant-mic').click());
  await page.waitForFunction(()=>document.getElementById('assistant-stop')?.hidden===false&&window.__phManualCloseTrack);
  await openingButton.click();
  await page.waitForFunction(()=>window.__phAudioContextCloseStarted===true);
  assert.equal(await page.evaluate(()=>window.__phManualCloseTrack?.stopped),true,'manual tracks stop before delayed AudioContext.close completes');
  assert.equal(openingSpeechCalls().length,openingPostsBeforeCloseRace,'opening request waits for manual capture cleanup');
  assert.equal(await page.locator('#assistant-speech-stop').isVisible(),true,'preparing opening exposes Stop during delayed capture cleanup');
  await page.locator('#assistant-speech-stop').click();
  assert.equal(await page.locator('#assistant-speech-stop').isHidden(),true,'Stop invalidates the preparing opening during capture cleanup');
  const newerReadGate=deferredGate();openingSpeechGate=newerReadGate;
  await page.evaluate(()=>{window.__phAudioContextCloseRelease?.();document.querySelector('.assistant-memory-opening')?.click();});
  await newerReadGate.reached;
  await page.waitForTimeout(50);
  assert.equal(openingSpeechCalls().length,openingPostsBeforeCloseRace+1,'only the newer Read posts when delayed cleanup settles');
  assert.match(await openingButton.innerText(),/正在准备开篇|Preparing opening/,'stale cleanup cannot clear the newer Read');
  assert.equal(await page.locator('#assistant-speech-stop').isVisible(),true,'stale cleanup cannot hide the newer Stop control');
  newerReadGate.release();
  const delayedCloseDeadline=Date.now()+10000;
  while((!openingSpeechCalls().at(-1)?.responseHeaders||(await fakeTtsCalls()).length<6)&&Date.now()<delayedCloseDeadline)await page.waitForTimeout(20);
  assert.equal(openingSpeechCalls().length,openingPostsBeforeCloseRace+1,'the stopped old operation never posts after capture cleanup releases');
  await page.waitForFunction(base=>window.__phAudioPlayCalls===base+5&&document.getElementById('assistant-speech-audio')?.paused===false,openingPlayBaseline);
  await page.locator('#assistant-speech-stop').click();
  await page.waitForFunction(()=>document.getElementById('assistant-speech-audio')?.paused===true);
  assert.equal(requests.filter(item=>item.path==='/assistant/v1/transcribe').length,manualAsrCount,'neither manual capture path calls ASR');
  assert.equal(turns().length,manualTurnCount,'neither manual capture path submits a new turn');
  assert.equal(await page.locator('#assistant-text').inputValue(),'权限等待期间继续保留草稿','source speech leaves the typed draft intact through playback');
  pass('Manual ready/pending capture interruption, close-race ownership and reverse mic cancellation preserve drafts without ASR or relisten');
  const speechJournal=await rpc({command:'speech-journal'});assert.equal(speechJournal.ok,true);
  const openingJournal=speechJournal.rows.find(row=>row.request_id===openingRequest.headers['x-photohouse-request-id']);
  assert(openingJournal,'opening request has its private playback receipt');
  assert.equal(openingJournal.input_text,null);assert.equal(openingJournal.recognized_text,null);
  assert.equal(JSON.stringify(openingJournal).includes(fixtureInfo.story_excerpt),false,'opening source text stays out of private journal fields');
  const resumedOpeningJournal=speechJournal.rows.find(row=>row.request_id===resumedOpeningRequest.headers['x-photohouse-request-id']);
  assert(resumedOpeningJournal,'retried opening request has its private playback receipt');
  assert.equal(resumedOpeningJournal.input_text,null);assert.equal(resumedOpeningJournal.recognized_text,null);
  pass('Fresh card opening speech uses one bound local WAV request, ends foreground voice, stops explicitly, and stores no source text in the private journal');

  const postsBeforeStoryOpen=turns().length,readerReadsBeforeStoryOpen=readerCalls().length;
  await page.locator('.assistant-memory-open').click();
  await page.locator('#story-reader').waitFor({state:'visible',timeout:10000});
  await page.locator('#story-reader').screenshot({path:path.join(artifacts,'assistant-saved-story-reader-desktop.png')});
  assert.equal(await page.locator('#story-reader-memory-title').innerText(),fixtureInfo.story_title,'reader receives the same saved story');
  assert.equal(readerCalls().length,readerReadsBeforeStoryOpen+1,'one protected reader GET opens the selected story');
  const storyReaderRequest=readerCalls().at(-1),storyReaderBody=storyReaderRequest.response;
  assert(storyReaderRequest.path.includes(`/requests/${JSON.parse(openingTurn.body).request_id}/memory-cards/0?`));
  assert.equal(storyReaderRequest.status,200);assert.deepEqual(Object.keys(storyReaderBody).sort(),['kind','reader','version']);
  assert.equal(storyReaderBody.kind,'story');assert.equal(storyReaderBody.reader.id,fixtureInfo.story_id);
  assert.equal(storyReaderBody.reader.revision,openingTurn.response.result.memory_cards[0].revision);
  assert.equal(turns().length,postsBeforeStoryOpen,'opening a saved story sends no assistant turn POST');
  assert.equal(requests.filter(item=>item.method==='POST'&&/\/memory-stories(?:\?|$)|\/memory-community\/v1\/books(?:\?|$)/.test(item.path)).length,0,'handoff sends no source mutation POST');
  await page.locator('#story-reader-close').click();await page.locator('#story-reader').waitFor({state:'hidden'});
  await page.locator('#memory-assistant').click();await page.locator('#assistant-private').waitFor({state:'visible',timeout:10000});

  // Draft chips stay local until Send. The overview, outline and preview each
  // advance the revision while retaining the exact visible source cohort.
  const beforeAllStories=turns().length,allStories=await submit('搜索故事 双故事');
  assert.equal(cards().count?await cards().count():0,allStories.response.result.memory_cards.length);
  assert(allStories.response.result.memory_cards.length>=2,`unfiltered story search exposes the second saved memory: ${JSON.stringify(allStories.response.result)}`);
  const displayedIds=allStories.response.result.memory_cards.map(card=>card.id),allStoriesParent=JSON.parse(allStories.body);
  const overviewChip=page.locator('.assistant-memory-followups .assistant-memory-followup').first();
  await overviewChip.click();
  assert.equal(turns().length,beforeAllStories+1,'overview tap fills a draft without sending');
  assert.equal(await page.locator('#assistant-text').inputValue(),'介绍这些回忆');
  const overview=await submit('介绍这些回忆');
  assert.deepEqual(JSON.parse(overview.body).memory_parent,{request_id:allStoriesParent.request_id,revision:allStories.response.revision});
  assert.deepEqual(overview.response.result.memory_cards.map(card=>card.id),displayedIds,'overview retains the complete current display cohort');
  assert.equal(overview.response.result.kind,'memory_cards');assert(overview.response.revision>allStories.response.revision);
  const secondCard=cards().nth(1),outlineChip=secondCard.locator('.assistant-memory-followup').nth(1);
  await outlineChip.click();assert.equal(await page.locator('#assistant-text').inputValue(),'第2段回忆有哪些章节');
  const beforeOutline=turns().length;assert.equal(beforeOutline,beforeAllStories+2,'outline tap remains draft-only');
  const outline=await submit('第2段回忆有哪些章节');
  assert.deepEqual(JSON.parse(outline.body).memory_parent,{request_id:JSON.parse(overview.body).request_id,revision:overview.response.revision});
  assert.deepEqual(outline.response.result.memory_cards.map(card=>card.id),displayedIds);
  assert(outline.response.revision>overview.response.revision);assert.match(outline.response.result.memory_cards[1].excerpt,/章节目录|Chapters:/);
  const previewChip=cards().nth(1).locator('.assistant-memory-followup').first();await previewChip.click();
  assert.equal(await page.locator('#assistant-text').inputValue(),'第2段回忆讲了什么');
  const preview=await submit('第2段回忆讲了什么');
  assert.deepEqual(JSON.parse(preview.body).memory_parent,{request_id:JSON.parse(outline.body).request_id,revision:outline.response.revision});
  assert.deepEqual(preview.response.result.memory_cards.map(card=>card.id),displayedIds);
  assert(preview.response.revision>outline.response.revision);assert.equal(preview.response.result.memory_cards.length,displayedIds.length);
  assert.match(preview.response.result.memory_cards[1].excerpt,/双故事/,'preview refreshes its excerpt from the current source');
  const openingActionBefore=openingSpeechCalls().length,ttsBeforeAction=(await fakeTtsCalls()).length;
  const readAction=await submit('朗读第二个故事的开篇');
  assert.deepEqual(readAction.response.result.memory_action,{type:'read_opening',ordinal:1},'backend proposal keeps its index in the exact current cohort');
  const secondActionCard=cards().nth(1),readActionButton=secondActionCard.locator('.assistant-memory-action');
  assert.equal(await cards().first().locator('.assistant-memory-action').count(),0,'action is attached only to its proposed card');
  assert.equal(await readActionButton.count(),1,'a typed read proposal appears as an explicit button');
  assert.equal(openingSpeechCalls().length,openingActionBefore,'typed command does not automatically request opening audio');
  assert.equal((await fakeTtsCalls()).length,ttsBeforeAction,'typed command does not automatically synthesize speech');
  // Security assertions already exercised the hostile source title above.
  // Wait for the new turn to render, then use a plain label for screenshots.
  await page.waitForFunction(()=>{const action=document.querySelector('#assistant-results .assistant-memory-action[data-ordinal="1"]');return !!action&&!!action.closest('.assistant-memory-card');});
  await page.evaluate(()=>{const card=document.querySelector('#assistant-results .assistant-memory-action[data-ordinal="1"]')?.closest('.assistant-memory-card');if(card){card.querySelector('h3').textContent='湖边双故事回忆';card.querySelector('.assistant-memory-excerpt').textContent='家人在湖边散步，记录了这段共同的回忆。';}});
  await secondActionCard.scrollIntoViewIfNeeded();await readActionButton.scrollIntoViewIfNeeded();
  await secondActionCard.screenshot({path:path.join(artifacts,'assistant-memory-action-desktop.png')});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'action card stays within a phone viewport at 150% text');
  assert(await secondActionCard.evaluate(node=>node.scrollWidth<=node.clientWidth),'action card wraps at 150% text');
  await secondActionCard.screenshot({path:path.join(artifacts,'assistant-memory-action-phone-150.png')});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>{document.documentElement.style.fontSize='';});
  await readActionButton.click();
  const actionSpeechDeadline=Date.now()+10000;
  while((openingSpeechCalls().length<openingActionBefore+1||!openingSpeechCalls().at(-1)?.responseHeaders||(await fakeTtsCalls()).length<ttsBeforeAction+1)&&Date.now()<actionSpeechDeadline)await page.waitForTimeout(20);
  assert.equal(openingSpeechCalls().length,openingActionBefore+1,'the explicit typed action makes one scoped opening request');
  assert.match(openingSpeechCalls().at(-1).path,new RegExp(`/requests/${JSON.parse(readAction.body).request_id}/memory-cards/1/speech$`));
  assert.equal((await fakeTtsCalls()).length,ttsBeforeAction+1);
  await page.locator('#assistant-speech-stop').click();
  await page.waitForFunction(()=>document.getElementById('assistant-speech-audio')?.paused===true);
  const openAction=await submit('打开第二个故事');
  assert.deepEqual(openAction.response.result.memory_action,{type:'open',ordinal:1});
  const openActionCard=cards().nth(1),openActionButton=openActionCard.locator('.assistant-memory-action');
  assert.equal(await openActionButton.count(),1,'a typed open proposal is also an explicit button');
  assert.equal(readerCalls().filter(item=>item.path.includes(`/requests/${JSON.parse(openAction.body).request_id}/`)).length,0,'typed open proposal does not prefetch its reader');
  await openActionButton.click();
  await page.locator('#story-reader').waitFor({state:'visible',timeout:10000});
  assert.equal(await page.locator('#story-reader-memory-title').innerText(),openAction.response.result.memory_cards[1].title);
  assert.equal(turns().at(-1).response.result.memory_action.ordinal,1);
  await page.locator('#story-reader-close').click();await page.locator('#story-reader').waitFor({state:'hidden'});
  await page.locator('#memory-assistant').click();await page.locator('#assistant-private').waitFor({state:'visible',timeout:10000});
  pass('Typed saved-memory actions stay explicit, point at the proposed card, and reuse protected reader and opening routes');
  voiceTranscript='朗读第二个故事的开篇';
  const micBeforeVoiceAction=await page.evaluate(()=>window.__phMicCalls),voiceActionTurns=turns().length,voiceActionOpenings=openingSpeechCalls().length,voiceActionTts=(await fakeTtsCalls()).length;
  await page.locator('#assistant-voice-start').click();
  await page.waitForFunction(()=>document.getElementById('assistant-voice-session')?.dataset.phase==='listening');
  assert.equal(await page.evaluate(()=>window.__phFeed(.35,5120)),true,'synthetic voiced frames reach the active voice processor');
  assert.equal(await page.evaluate(()=>window.__phFeed(0,20480)),true,'synthetic silence closes the utterance');
  const voiceActionTurn=await waitForTurnCount(voiceActionTurns);
  assert.equal(voiceActionTurn.response.result.memory_action.type,'read_opening','continuous voice submits the negotiated memory action');
  const voiceActionDeadline=Date.now()+10000;
  while((openingSpeechCalls().length<voiceActionOpenings+1||!openingSpeechCalls().at(-1)?.responseHeaders||(await fakeTtsCalls()).length<voiceActionTts+1)&&Date.now()<voiceActionDeadline)await page.waitForTimeout(20);
  assert.equal(openingSpeechCalls().length,voiceActionOpenings+1,'fresh voice action dispatches one opening request');
  assert.equal((await fakeTtsCalls()).length,voiceActionTts+1,'fresh voice action starts source-bound opening playback');
  await page.waitForFunction(()=>document.getElementById('assistant-voice-session')?.dataset.phase==='speaking');
  const voiceActionCard=cards().nth(1);
  assert.equal(await voiceActionCard.getAttribute('aria-current'),'true','the active card is announced as the current voice action target');
  assert(await voiceActionCard.evaluate(node=>node.classList.contains('assistant-memory-card--action-target')),'the active card has a visible focus cue');
  assert(await page.locator('#assistant-status').innerText().then(text=>/正在朗读|Reading/.test(text)),'the page gives a short cue for the selected card action');
  await voiceActionCard.evaluate(card=>{card.querySelector('h3').textContent='湖边双故事回忆';card.querySelector('.assistant-memory-excerpt').textContent='家人在湖边散步，记录了这段共同的回忆。';});
  assert.equal(await page.locator('#assistant-voice-pause').isVisible(),true,'Pause remains visible while the selected opening plays');
  assert.equal(await page.locator('#assistant-voice-end').isVisible(),true,'End remains visible while the selected opening plays');
  await voiceActionCard.scrollIntoViewIfNeeded();
  await voiceActionCard.screenshot({path:path.join(artifacts,'assistant-memory-voice-target-desktop.png')});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  await voiceActionCard.scrollIntoViewIfNeeded();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'voice action target fits a phone viewport at 150% text');
  assert.equal(await page.locator('#assistant-voice-pause').isVisible(),true,'Pause remains visible in the phone voice action view');
  assert.equal(await page.locator('#assistant-voice-end').isVisible(),true,'End remains visible in the phone voice action view');
  await voiceActionCard.screenshot({path:path.join(artifacts,'assistant-memory-voice-target-phone-150.png')});
  await page.screenshot({path:path.join(artifacts,'assistant-memory-voice-target-phone-150-page.png'),fullPage:true});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>{document.documentElement.style.fontSize='';});
  const micDuringPlayback=await page.evaluate(()=>window.__phMicCalls),voiceActionAudio=page.locator('#assistant-speech-audio');
  await voiceActionAudio.evaluate(node=>node.dispatchEvent(new Event('error')));
  await page.waitForFunction(()=>document.getElementById('assistant-voice-session')?.dataset.phase==='paused');
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>window.__phMicCalls),micDuringPlayback,'asynchronous media error never restarts microphone capture');
  assert.equal(await page.evaluate(()=>window.__phTrackStopped),true,'media error releases the active microphone track');
  assert.equal(await voiceActionAudio.evaluate(node=>node.paused),true,'media error pauses the active opening audio');
  await page.locator('#assistant-voice-end').click();
  await page.waitForFunction(()=>document.getElementById('assistant-voice-start')?.hidden===false);
  voiceTranscript='';
  pass('Continuous voice reads only after the fresh action, and a later media error pauses without auto-listening');
  const ambiguousAction=await submit('打开第三个故事');
  assert.deepEqual(JSON.parse(ambiguousAction.body).memory_parent,{request_id:JSON.parse(voiceActionTurn.body).request_id,revision:voiceActionTurn.response.revision});
  assert.equal(ambiguousAction.response.result.kind,'memory_cards');
  assert.equal(Object.hasOwn(ambiguousAction.response.result,'memory_action'),false,'out-of-range action stays a no-action result');
  assert.equal(ambiguousAction.response.result.memory_cards.length,displayedIds.length,'out-of-range action retains the complete fresh cohort for a follow-up choice');
  await page.waitForFunction(()=>document.querySelectorAll('#assistant-results .assistant-memory-card').length>0&&document.querySelectorAll('#assistant-results .assistant-memory-action').length===0);
  assert.equal(await cards().locator('.assistant-memory-action').count(),0,'an ambiguous action renders no executable action button');
  assert.equal(await cards().nth(1).getAttribute('aria-current'),null,'a later no-action turn clears the prior voice focus cue');
  const ambiguous=await submit('第3段回忆有哪些章节');
  assert.deepEqual(JSON.parse(ambiguous.body).memory_parent,{request_id:JSON.parse(ambiguousAction.body).request_id,revision:ambiguousAction.response.revision});
  assert.equal(ambiguous.response.result.kind,'clarification');assert.deepEqual(ambiguous.response.result.memory_cards,[],'out-of-range ordinal is refused without inventing a source');
  pass('Saved-memory chips only draft; overview, second outline, preview and refusal use the exact latest source revision');

  // A memoir-specific command proves the kind filter and the accessible card
  // layout at a phone-equivalent width and 150% font size.
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  const memoirTurn=await submit('找回忆录 野餐',{keyboard:true});
  await page.waitForFunction(title=>Array.from(document.querySelectorAll('#assistant-results .assistant-memory-card h3')).some(node=>node.textContent===title),
    fixtureInfo.memoir_title,{timeout:10000});
  assert.equal(await cards().count(),1,'memoir filter renders one memoir result');
  const memoirCard=cards().first();
  assert.equal(await memoirCard.locator('.assistant-memory-kind').innerText(),'已保存的回忆录');
  assert.equal(await memoirCard.locator('h3').innerText(),fixtureInfo.memoir_title);
  assert.equal(await memoirCard.locator('.assistant-memory-excerpt').innerText(),'野餐之后，我们记下了家人一起度过的时光。');
  assert.equal(await memoirCard.locator('button,a,input,img,audio,video').count(),6,'memoir card adds explicit section-read and local Stop actions');
  assert.match(await memoirCard.locator('.assistant-memory-opening').innerText(),/朗读开篇|Read opening/);
  assert.match(await memoirCard.locator('.assistant-memory-open').innerText(),/打开回忆录|Open memoir/);
  assert(await memoirCard.locator('.assistant-memory-open').isVisible(),'explicit memoir reader action is visible on the card');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'390px page has no horizontal overflow at 150% font size');
  assert(await memoirCard.evaluate(node=>node.scrollWidth<=node.clientWidth),'memoir card has no horizontal overflow');
  await memoirCard.screenshot({path:path.join(artifacts,'assistant-saved-memory-memoir-card-phone-150-zh.png')});
  await page.screenshot({path:path.join(artifacts,'assistant-saved-memory-memoir-phone-150-zh.png'),fullPage:true});
  const postsBeforeMemoirOpen=turns().length,readerReadsBeforeMemoirOpen=readerCalls().length,playCallsBeforeMemoirReader=await page.evaluate(()=>window.__phAudioPlayCalls);
  await memoirCard.locator('.assistant-memory-open').click();
  await page.locator('#memory-book-reader').waitFor({state:'visible',timeout:10000});
  await page.locator('#memory-book-reader').screenshot({path:path.join(artifacts,'assistant-saved-memoir-reader-phone-150-zh.png')});
  assert(await page.locator('#memory-book-reader').evaluate(node=>node.scrollWidth<=node.clientWidth),'memoir reader fits its 390px, 150% text viewport');
  assert(await page.locator('.memory-book-toc button').first().evaluate(node=>node.scrollWidth<=node.clientWidth),'long memoir chapter title wraps inside its table-of-contents control');
  assert.equal(await page.locator('#memory-book-reader-title').innerText(),fixtureInfo.memoir_title);
  assert.equal(readerCalls().length,readerReadsBeforeMemoirOpen+1,'one protected reader GET opens the selected memoir');
  const memoirReaderRequest=readerCalls().at(-1),memoirReaderBody=memoirReaderRequest.response;
  assert(memoirReaderRequest.path.includes(`/requests/${JSON.parse(memoirTurn.body).request_id}/memory-cards/0?`));
  assert.equal(memoirReaderRequest.status,200);assert.deepEqual(Object.keys(memoirReaderBody).sort(),['kind','reader','version']);
  assert.equal(memoirReaderBody.kind,'memoir');assert.equal(memoirReaderBody.reader.id,fixtureInfo.memoir_id);
  assert.equal(memoirReaderBody.reader.revision,memoirTurn.response.result.memory_cards[0].revision);
  assert.equal(turns().length,postsBeforeMemoirOpen,'opening a memoir sends no assistant turn POST');
  assert.equal(requests.filter(item=>item.method==='POST'&&/\/memory-stories(?:\?|$)|\/memory-community\/v1\/books(?:\?|$)/.test(item.path)).length,0,'handoff sends no source mutation POST');
  assert.equal(await page.evaluate(()=>window.__phAudioPlayCalls),playCallsBeforeMemoirReader,'the reader does not autoplay speech');
  await page.keyboard.press('Escape');await page.locator('#memory-book-reader').waitFor({state:'hidden'});
  await page.locator('#memory-assistant').click();await page.locator('#assistant-private').waitFor({state:'visible',timeout:10000});
  assert.deepEqual(JSON.parse(memoirTurn.body).accepts,['saved_memory_cards_v1','saved_memory_actions_v1']);
  pass('Fresh memoir card stays plain and fits a 390px viewport with 150% text; Tab and Enter send the query');

  // Lose a completed POST response and recover the existing request. The safe
  // persisted projection has no fresh card IDs, context, items or effects.
  const beforeLost=turns().length;dropNextTurnResponse=true;
  await page.locator('#assistant-text').fill('找回忆 野餐');await page.locator('#assistant-send').click();
  const lost=await waitForTurnCount(beforeLost);
  await page.locator('#assistant-private-recover').waitFor({state:'visible',timeout:10000});
  assert(lost.responseDroppedAfterServer);
  const lostBody=JSON.parse(lost.body);assert.deepEqual(lostBody.accepts,['saved_memory_cards_v1','saved_memory_actions_v1']);
  const speechCountBeforeRecovery=speechCalls().length,ttsCountBeforeRecovery=(await fakeTtsCalls()).length;
  const recoverButton=page.locator('#assistant-private-recover');await recoverButton.click();
  await page.waitForFunction(()=>document.getElementById('assistant-private-recover')?.hidden===true||document.getElementById('assistant-private-recover')?.disabled===true,{},{timeout:10000});
  assert.equal(turns().length,beforeLost+1,'recovery does not repeat the turn POST');
  const recovered=requests.filter(item=>item.method==='GET'&&item.path.includes('/requests/'+lostBody.request_id+'?')).at(-1);
  assert(recovered?.response,'completed uncertain turn is read with the exact GET request ID');
  const recoveredResult=recovered.response.result;
  assert.equal(recovered.response.recovered,true);assert.equal(recoveredResult.effect,null);
  assert.equal(recoveredResult.context,null);assert.deepEqual(recoveredResult.items,[]);
  assert.equal(speechCalls().length,speechCountBeforeRecovery,'GET recovery never repeats private reply speech');
  assert.equal((await fakeTtsCalls()).length,ttsCountBeforeRecovery,'GET recovery never synthesizes audio');
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

  // A missing second probe must not disable the independently negotiated card
  // feature. It only withholds the explicit speech action for this scope.
  const ttsBeforeFallback=(await fakeTtsCalls()).length;
  await callCommand('reply-speech-on');probeMode='live';speechProbeMode='missing';await reloadAndLogin();
  const fallbackMemoryDeadline=Date.now()+10000;
  while(!probeReads().some(item=>item.response?.available===true)&&Date.now()<fallbackMemoryDeadline)await page.waitForTimeout(20);
  const fallbackSpeechDeadline=Date.now()+10000;
  while(!speechProbeReads().some(item=>item.syntheticMissingProbe)&&Date.now()<fallbackSpeechDeadline)await page.waitForTimeout(20);
  assert(probeReads().some(item=>item.response?.available===true),'card capability remains available');
  assert(speechProbeReads().some(item=>item.syntheticMissingProbe),'only the optional speech probe is missing');
  await ensureThread();
  const beforeFallback=turns().length;const fallbackTurn=await submit('搜索故事 野餐');
  await cards().waitFor({state:'visible',timeout:10000});
  assert.equal(JSON.parse(fallbackTurn.body).accepts?.[0],'saved_memory_cards_v1');
  assert.equal(await cards().count(),1,'saved-memory card still renders with a missing speech probe');
  assert.equal(await page.locator('#assistant-play').isHidden(),true,'missing speech probe hides reply playback');
  assert.equal(speechCalls().length,1,'missing probe does not call speech endpoint');
  assert.equal((await fakeTtsCalls()).length,ttsBeforeFallback,'missing probe does not synthesize audio');
  pass('Missing saved-memory speech probe preserves cards and withholds speech playback');

  readerProbeMode='missing';speechProbeMode='live';await reloadAndLogin();
  const readerFallbackDeadline=Date.now()+10000;
  while(!readerProbeReads().some(item=>item.syntheticMissingProbe)&&Date.now()<readerFallbackDeadline)await page.waitForTimeout(20);
  assert(readerProbeReads().some(item=>item.syntheticMissingProbe),'old servers can omit the optional full-reader probe');
  await ensureThread();const readerFallbackTurn=await submit('搜索故事 野餐');await cards().waitFor({state:'visible',timeout:10000});
  assert.equal(await cards().count(),1,'reader capability failure preserves fresh saved-memory cards');
  assert.equal(await cards().first().locator('.assistant-memory-open').count(),0,'reader capability failure leaves cards without a reader action');
  assert.equal(await cards().first().locator('.assistant-memory-opening').count(),1,'opening playback remains independently available without the full reader');
  assert.equal(JSON.parse(readerFallbackTurn.body).accepts?.[0],'saved_memory_cards_v1');
  pass('Missing optional reader capability preserves cards and the legacy handoff boundary');

  readingProbeMode='missing';readerProbeMode='live';await reloadAndLogin();
  const readingFallbackDeadline=Date.now()+10000;
  while(!readingProbeReads().some(item=>item.syntheticMissingProbe)&&Date.now()<readingFallbackDeadline)await page.waitForTimeout(20);
  assert(readingProbeReads().some(item=>item.syntheticMissingProbe),'old server can omit the optional opening capability');
  await ensureThread();const readingFallbackTurn=await submit('搜索故事 野餐');await cards().waitFor({state:'visible',timeout:10000});
  assert.equal(await cards().count(),1,'missing opening capability preserves the saved-memory card');
  assert.equal(await cards().first().locator('.assistant-memory-opening').count(),0,'missing opening capability hides the opening action');
  assert.equal(JSON.parse(readingFallbackTurn.body).accepts?.[0],'saved_memory_cards_v1');
  pass('Missing optional opening capability leaves saved-memory cards available without a speech action');

  await callCommand('reply-speech-on');readingProbeMode='forbidden';await reloadAndLogin();
  const deniedReadingDeadline=Date.now()+10000;
  while(!readingProbeReads().some(item=>item.syntheticMissingProbe&&item.status===403)&&Date.now()<deniedReadingDeadline)await page.waitForTimeout(20);
  assert(readingProbeReads().some(item=>item.syntheticMissingProbe&&item.status===403),'unknown-route 403 is simulated for the optional opening probe');
  await waitForOptional403Recheck(readingProbeReads,'savedMemoryReadingAvailable','optional opening probe 403');
  await ensureThread();const deniedReadingTurn=await submit('搜索故事 野餐');await cards().waitFor({state:'visible',timeout:10000});
  assert.equal(await cards().first().locator('.assistant-memory-opening').count(),0,'unknown optional route 403 hides only the opening action');
  assert.equal(await cards().first().locator('.assistant-memory-open').count(),1,'403 fallback preserves the separate saved reader');
  assert.equal(JSON.parse(deniedReadingTurn.body).accepts?.[0],'saved_memory_cards_v1');
  pass('Unknown-route 403 triggers an exact base capability recheck and preserves the authorized card and reader scope');

  segmentReadingProbeMode='missing';readingProbeMode='live';await reloadAndLogin();
  const missingSegmentDeadline=Date.now()+10000;while(!segmentReadingProbeReads().some(item=>item.status===404)&&Date.now()<missingSegmentDeadline)await page.waitForTimeout(20);
  assert(segmentReadingProbeReads().some(item=>item.status===404),'old server can omit the optional section-reading probe');
  await ensureThread();const missingSegmentTurn=await submit('搜索故事 野餐');await cards().waitFor({state:'visible',timeout:10000});
  assert.equal(await cards().first().locator('.assistant-memory-segment-reading').count(),0,'missing section capability hides only section narration');
  assert.equal(await cards().first().locator('.assistant-memory-opening').count(),1,'missing section capability preserves the existing opening action');
  assert.equal(JSON.parse(missingSegmentTurn.body).accepts?.[0],'saved_memory_cards_v1');
  pass('Missing optional section-reading capability preserves cards and the existing opening action');

  segmentReadingProbeMode='forbidden';await reloadAndLogin();
  const deniedSegmentDeadline=Date.now()+10000;while(!segmentReadingProbeReads().some(item=>item.status===403)&&Date.now()<deniedSegmentDeadline)await page.waitForTimeout(20);
  assert(segmentReadingProbeReads().some(item=>item.status===403),'unknown-route 403 is simulated for the section-reading probe');
  await waitForOptional403Recheck(segmentReadingProbeReads,'savedMemorySegmentReadingAvailable','optional section-reading probe 403');
  await ensureThread();const deniedSegmentTurn=await submit('搜索故事 野餐');await cards().waitFor({state:'visible',timeout:10000});
  assert.equal(await cards().first().locator('.assistant-memory-segment-reading').count(),0,'optional 403 leaves section narration unavailable');
  assert.equal(await cards().first().locator('.assistant-memory-opening').count(),1,'optional 403 leaves the independent opening action available');
  assert.equal(JSON.parse(deniedSegmentTurn.body).accepts?.[0],'saved_memory_cards_v1');
  pass('Unknown-route 403 safely leaves section narration unavailable in the current unlocked scope');

  segmentReadingProbeMode='live';followupProbeMode='missing';readerProbeMode='live';speechProbeMode='live';await reloadAndLogin();
  const followupFallbackDeadline=Date.now()+10000;
  while(!followupProbeReads().some(item=>item.syntheticMissingProbe)&&Date.now()<followupFallbackDeadline)await page.waitForTimeout(20);
  assert(followupProbeReads().some(item=>item.syntheticMissingProbe),'old server followup probe returns its simulated 404');
  assert(readerProbeReads().some(item=>item.response?.available===true),'reader capability remains available without followup capability');
  assert(speechProbeReads().some(item=>item.response?.available===true),'reply speech capability remains available without followup capability');
  await ensureThread();const noFollowupTurn=await submit('搜索故事 野餐');await cards().waitFor({state:'visible',timeout:10000});
  const oldShapeBody=JSON.parse(noFollowupTurn.body);
  assert.deepEqual(Object.keys(oldShapeBody).sort(),['accepts','expected_revision','library_id','request_id','text']);
  assert.equal(await cards().count(),1,'missing followup route preserves memory cards');
  assert.equal(await cards().first().locator('.assistant-memory-open').count(),1,'missing followup route preserves the full reader');
  assert(await page.locator('#assistant-play').isVisible(),'missing followup route preserves explicit reply speech');
  assert.equal(await cards().first().locator('.assistant-memory-followup').count(),0,'old server exposes no followup chips');
  pass('Missing optional followup probe preserves the prior turn body, cards, reader and speech');

  await callCommand('reply-speech-on');readerProbeMode='live';speechProbeMode='live';readingProbeMode='live';followupProbeMode='live';
  const delayedFollowupGate=deferredGate();followupProbeGate=delayedFollowupGate;await reloadAndLogin();await delayedFollowupGate.reached;
  const liveReaderDeadline=Date.now()+10000;
  while(!readerProbeReads().some(item=>item.response?.available===true)&&Date.now()<liveReaderDeadline)await page.waitForTimeout(20);
  await page.waitForFunction(()=>{const snapshot=window.__privateAssistantController?.state();return snapshot?.savedMemoryAvailable===true&&snapshot.savedMemoryActionsAvailable===true&&snapshot.savedMemoryReaderAvailable===true&&snapshot.savedMemoryFollowupAvailable===false;},{},{timeout:10000});
  await ensureThread();const scopeTurn=await submit('搜索故事 野餐');
  assert.deepEqual(JSON.parse(scopeTurn.body).accepts,['saved_memory_cards_v1','saved_memory_actions_v1'],'final scope-fencing turn waits for and opts into both live saved-memory capabilities');
  assert.equal(scopeTurn.response?.status,'completed');assert.equal(scopeTurn.response.result.kind,'memory_cards');
  try{await cards().waitFor({state:'visible',timeout:10000});}catch(error){
    const ui=await page.evaluate(()=>{const snapshot=window.__privateAssistantController?.state();return {status:document.querySelector('#assistant-status')?.textContent,privateStatus:document.querySelector('#assistant-private-status')?.textContent,privateVisible:document.querySelector('#assistant-private')?.hidden===false,resultKind:snapshot?.currentResult?.kind,revision:snapshot?.revision,pendingTurn:snapshot?.pendingTurn?.status,savedMemoryAvailable:snapshot?.savedMemoryAvailable,savedMemoryActionReady:snapshot?.savedMemoryActionReady,readerReady:snapshot?.savedMemoryReaderReady,cards:document.querySelectorAll('#assistant-results .assistant-memory-card').length};});
    console.error('SCOPE_SEARCH_DIAGNOSTIC',JSON.stringify({request:{path:scopeTurn.path,status:scopeTurn.status,body:scopeTurn.body},response:scopeTurn.response,ui}));throw error;
  }
  const scopeCardTitle=scopeTurn.response.result.memory_cards[0].title;
  await page.waitForFunction(title=>document.querySelector('#assistant-results .assistant-memory-card h3')?.textContent===title,scopeCardTitle,{timeout:10000});
  assert.equal(await cards().first().locator('.assistant-memory-followup').count(),0,'the exact current story card has no followups until its delayed capability returns');
  await page.locator('#assistant-text').focus();const turnsBeforeFollowupReady=turns().length;
  const heldFollowup=followupProbeReads().find(item=>item.syntheticFollowupGate);assert(heldFollowup,'the optional followup capability response is held during the current story render');
  delayedFollowupGate.release();
  await page.waitForFunction(()=>{const snapshot=window.__privateAssistantController?.state();return snapshot?.savedMemoryFollowupReady===true&&snapshot.currentResult?.kind==='memory_cards';},{},{timeout:10000});
  const delayedOverview=page.getByRole('button',{name:'全部回忆. 介绍这些回忆',exact:true});
  const delayedSummary=cards().first().getByRole('button',{name:'讲了什么. 第1段回忆讲了什么',exact:true});
  const delayedChapters=cards().first().getByRole('button',{name:'章节. 第1段回忆有哪些章节',exact:true});
  await delayedOverview.waitFor({state:'visible',timeout:10000});await delayedSummary.waitFor({state:'visible',timeout:10000});await delayedChapters.waitFor({state:'visible',timeout:10000});
  assert.equal(await page.locator('#assistant-results > .assistant-memory-followups[data-followup-kind="overview"]').count(),1,'late readiness adds only one overview group');
  assert.equal(await cards().first().locator('.assistant-memory-followups[data-followup-kind="card"] .assistant-memory-followup').count(),2,'late readiness adds exactly the current card prompt pair');
  assert.equal(await page.evaluate(()=>document.activeElement?.id),'assistant-text','late capability adds buttons without moving focus');
  assert.equal(turns().length,turnsBeforeFollowupReady,'late capability adds draft controls without submitting a turn');
  await page.setViewportSize({width:390,height:1100});await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  const lateChipLayout=await cards().first().evaluate(card=>[...card.querySelectorAll('.assistant-memory-followups')].map(group=>({width:group.clientWidth,scrollWidth:group.scrollWidth,
    buttons:[...group.querySelectorAll('button')].map(button=>button.getBoundingClientRect().height)})));
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'late localized chips fit the 390px page at 150% text');
  assert(lateChipLayout.length===1&&lateChipLayout.every(group=>group.scrollWidth<=group.width&&group.buttons.every(height=>height>=44)),`late localized chips wrap without overflow and keep 44px targets: ${JSON.stringify(lateChipLayout)}`);
  await cards().first().screenshot({path:path.join(artifacts,'assistant-memory-late-followups-phone-150-zh.png')});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>{document.documentElement.style.fontSize='';});
  pass('A delayed current-scope followup capability adds exact source-bound chips without focus movement or submission');
  const oldReaderGate=deferredGate();readerGate=oldReaderGate;
  await cards().first().locator('.assistant-memory-open').click();await oldReaderGate.reached;
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible',timeout:10000});
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#grid .asset').first().waitFor();
  const returningPanel=page.locator('#assistant-panel');if(!await returningPanel.evaluate(node=>node.open))await returningPanel.locator(':scope > summary').click();
  await page.locator('#assistant-private').waitFor({state:'visible',timeout:10000});await ensureThread();
  const nextTurnGate=deferredGate();turnGate=nextTurnGate;const beforeReplacementTurn=turns().length;
  await page.locator('#assistant-text').fill('新的助手请求');await page.locator('#assistant-send').click();await nextTurnGate.reached;
  oldReaderGate.release();await page.waitForTimeout(100);
  assert.equal(await page.locator('#assistant-send').isDisabled(),true,'a late old-scope reader completion cannot release the new turn busy lock');
  nextTurnGate.release();await waitForTurnCount(beforeReplacementTurn);
  pass('A delayed old-scope reader reply cannot release a replacement assistant operation');

  await ensureThread();await submit('搜索故事 野餐');await cards().waitFor({state:'visible',timeout:10000});
  const cancelSection=cards().first().locator('.assistant-memory-segment-reading'),lateSegmentGate=deferredGate();segmentSpeechGate=lateSegmentGate;
  const playsBeforeLateSegment=await page.evaluate(()=>window.__phAudioPlayCalls),micBeforeLateSegment=await page.evaluate(()=>window.__phMicCalls);
  await cancelSection.click();await lateSegmentGate.reached;
  const replacementMemoryTurn=await submit('找回忆录 野餐');
  await page.waitForFunction(title=>Array.from(document.querySelectorAll('#assistant-results .assistant-memory-card h3')).some(node=>node.textContent===title),fixtureInfo.memoir_title,{timeout:10000});
  lateSegmentGate.release();await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>window.__phAudioPlayCalls),playsBeforeLateSegment,'late segment audio from a replaced result never reaches playback');
  assert.equal(await page.evaluate(()=>window.__phMicCalls),micBeforeLateSegment,'canceling a stale segment never starts microphone listening');
  assert.equal(await cards().first().locator('h3').innerText(),fixtureInfo.memoir_title,'the replacement source remains current after the late response');
  assert.equal(await cards().first().locator('.assistant-memory-segment-status').isHidden(),true,'stale section completion leaves no progress on the replacement card');
  assert.equal(JSON.parse(replacementMemoryTurn.body).text,'找回忆录 野餐');
  pass('Replacing a saved-memory result aborts and ignores a late section response');

  await page.locator('#language').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-workspace-title')?.textContent==='PhotoHouse Memory Assistant',{},{timeout:10000});
  const workspacePanel=page.locator('#assistant-panel');if(!await workspacePanel.evaluate(node=>node.open))await workspacePanel.locator(':scope > summary').click();
  await page.locator('#assistant-private').waitFor({state:'visible',timeout:10000});await ensureThread();
  const delayedEnglishPrimaryActions=await holdPrimaryActionCapabilities();
  const englishSegmentTurn=await submit('搜索故事 野餐');
  assert.equal(englishSegmentTurn.response.result.kind,'memory_cards','English story request returns the expected current card result');
  try{
    await page.waitForFunction(({title,label})=>document.querySelector('#assistant-results .assistant-memory-card h3')?.textContent===title&&
      document.querySelector(`#assistant-results .assistant-memory-followup[aria-label="${label}"]`),
      {title:fixtureInfo.story_title,label:'All memories. introduce these memories'},{timeout:10000});
  }catch(error){
    const snapshot=await page.evaluate(()=>{const state=window.__privateAssistantController?.state(),thread=state?.activeThread,result=state?.currentResult;
      return {currentResultKind:result?.kind,memoryCardCount:result?.memory_cards?.length,followupReady:state?.savedMemoryFollowupReady,
        savedMemoryAvailable:state?.savedMemoryAvailable,pendingTurn:state?.pendingTurn?.status??!!state?.pendingTurn,pendingCreation:!!state?.pendingCreation,
        revisionMatchesThread:state?.revision===thread?.revision,cardTitles:[...document.querySelectorAll('#assistant-results .assistant-memory-card h3')].map(node=>node.textContent),
        followupNames:[...document.querySelectorAll('#assistant-results .assistant-memory-followup')].map(node=>node.getAttribute('aria-label'))};});
    console.log('SAVED_MEMORY_FOLLOWUP_DIAGNOSTIC '+JSON.stringify({snapshot,turnRequestId:JSON.parse(englishSegmentTurn.body).request_id,
      turnResponse:englishSegmentTurn.response?.status,followupCapabilityReceipts:followupProbeReads().map(item=>({method:item.method,path:item.path,status:item.status})),
      latestTurnRequest:turns().at(-1)?.path}));
    throw error;
  }
  await cards().waitFor({state:'visible',timeout:10000});
  assert.equal(await cards().first().locator(':scope > .assistant-memory-primary-actions').count(),0,'late optional reader probes leave the freshly rendered English card without a primary action row');
  delayedEnglishPrimaryActions.release();await delayedEnglishPrimaryActions.complete();
  await page.waitForFunction(()=>{const controller=window.__privateAssistantController,state=controller?.state(),card=document.querySelector('#assistant-results .assistant-memory-card'),row=card?.querySelector(':scope > .assistant-memory-primary-actions');
    return state?.savedMemoryReaderReady===true&&state?.savedMemoryReadingReady===true&&state?.savedMemorySegmentReadingAvailable===true&&
      row?.querySelector('.assistant-memory-open')&&row.querySelector('.assistant-memory-opening')&&row.querySelector('.assistant-memory-segment-reading')&&row.querySelector('.assistant-memory-segment-stop');},{},{timeout:10000});
  assert.equal(await cards().first().locator(':scope > .assistant-memory-primary-actions').count(),1,'late readiness creates exactly one direct primary action row');
  assert.equal(await cards().first().locator('.assistant-memory-segment-reading').innerText(),'Read the first chapter in sections');
  assert.equal(await cards().first().locator('.assistant-memory-segment-help').innerText(),'Reads one section at a time. Choose Continue after playback; the microphone stays off.');
  const englishAllMemories=page.getByRole('button',{name:'All memories. introduce these memories',exact:true});
  const englishSummary=cards().first().getByRole('button',{name:'Summary. what is the first saved memory about',exact:true});
  const englishChapters=cards().first().getByRole('button',{name:'Chapters. what chapters does the first saved memory have',exact:true});
  assert.equal(await englishAllMemories.innerText(),'All memories');assert.equal(await englishAllMemories.getAttribute('aria-label'),'All memories. introduce these memories');
  assert.equal(await englishSummary.innerText(),'Summary');
  assert.equal(await englishSummary.getAttribute('aria-label'),'Summary. what is the first saved memory about');
  assert.equal(await englishChapters.innerText(),'Chapters');
  assert.equal(await englishChapters.getAttribute('aria-label'),'Chapters. what chapters does the first saved memory have');
  await page.evaluate(()=>{const card=document.querySelector('#assistant-results .assistant-memory-card');if(card){card.querySelector('h3').textContent='Family walk by the lake';card.querySelector('.assistant-memory-excerpt').textContent='After the picnic, the family walked by the lake and kept a note of their time together.';}});
  await page.setViewportSize({width:390,height:1100});await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'English section card fits the 390px viewport at 150% text');
  assert(await cards().first().evaluate(node=>node.scrollWidth<=node.clientWidth),'English section card wraps within the narrow viewport');
  const englishActionRow=cards().first().locator('.assistant-memory-primary-actions');
  const englishIdleActions=await englishActionRow.evaluate(row=>({rowWidth:row.clientWidth,rowScrollWidth:row.scrollWidth,cardWidth:row.closest('.assistant-memory-card').clientWidth,
    cardScrollWidth:row.closest('.assistant-memory-card').scrollWidth,buttons:[...row.querySelectorAll('button')].filter(button=>!button.hidden).map(button=>button.getBoundingClientRect().height)}));
  assert(englishIdleActions.rowScrollWidth<=englishIdleActions.rowWidth&&englishIdleActions.cardScrollWidth<=englishIdleActions.cardWidth,'English primary actions wrap within the card at 390px and 150% text');
  assert(englishIdleActions.buttons.every(height=>height>=48),'English primary actions retain 48px targets at 390px and 150% text');
  await cards().first().locator('.assistant-memory-segment-reading').click();
  await page.waitForFunction(()=>/Reading segment 1\/3/.test(document.querySelector('.assistant-memory-segment-reading')?.textContent||''));
  assert(await cards().first().locator('.assistant-memory-segment-stop').isVisible(),'English section playback exposes its local Stop action');
  assert(await englishActionRow.getByRole('button',{name:'Stop this section',exact:true}).isVisible(),'late English Stop control has a visible accessible label in the primary action row');
  const englishPlayingActions=await englishActionRow.evaluate(row=>({rowWidth:row.clientWidth,rowScrollWidth:row.scrollWidth,cardWidth:row.closest('.assistant-memory-card').clientWidth,
    cardScrollWidth:row.closest('.assistant-memory-card').scrollWidth,stop:row.querySelector('.assistant-memory-segment-stop').getBoundingClientRect().height}));
  assert(englishPlayingActions.rowScrollWidth<=englishPlayingActions.rowWidth&&englishPlayingActions.cardScrollWidth<=englishPlayingActions.cardWidth&&englishPlayingActions.stop>=48,'English active Stop wraps in the 48px action row at 390px and 150% text');
  await cards().first().screenshot({path:path.join(artifacts,'assistant-memory-segment-en-phone-150.png')});
  await page.screenshot({path:path.join(artifacts,'assistant-memory-segment-en-phone-150-full.png'),fullPage:true});
  await cards().first().locator('.assistant-memory-segment-stop').click();
  pass('English section-reading action remains readable at 390px with 150% text');

  assert.deepEqual(external,[],'browser makes no request outside the synthetic origin');
  assert.deepEqual(errors,[],'browser has no uncaught JavaScript errors');
  console.log(`CHECKPOINTS ${checks.length}`);
})().catch(async error=>{console.error(error.stack||error);if(page)try{console.error('BROWSER_STATE',JSON.stringify({url:page.url(),errors,authVisible:await page.locator('#auth').isVisible(),assetCount:await page.locator('#grid .asset').count()}));}catch{}process.exitCode=1;}).finally(async()=>{
  try{await page?.close();await context?.close();await browser?.close();}catch{}
  try{for(const name of fs.readdirSync(artifacts)){const item=path.join(artifacts,name);if(fs.statSync(item).isFile())fs.chmodSync(item,0o600);}fs.chmodSync(artifacts,0o700);}catch{}
  try{bridge.stdin.write('{"command":"quit"}\n');bridge.stdin.end();}catch{}
  if(bridge.exitCode===null)bridge.kill();
});
