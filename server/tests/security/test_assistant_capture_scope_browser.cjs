/* Synthetic capture startup fencing across account reset and delayed browser audio APIs. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=require('node:path').resolve(__dirname,'../..');
const bridge=spawn(process.env.PH_BROWSER_PYTHON||require('node:path').join(root,'.venv/bin/python'),
  [require('node:path').join(__dirname,'assistant_pending_recovery_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,nextAsrText='synthetic scoped transcript';
const pendingRpc=new Map(),requests=[],externalOrigins=[],pageErrors=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){readyResolve();return;}const call=pendingRpc.get(value.id);if(call){pendingRpc.delete(value.id);call.resolve(value);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Synthetic API bridge exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Synthetic API bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
let browser,context,page;
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),
    args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await context.addInitScript(()=>{
    window.__phMediaRequests=[];window.__phContexts=[];window.__phHoldResume=false;
    const media=navigator.mediaDevices||{};try{Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:media});}catch{}
    Object.defineProperty(media,'getUserMedia',{configurable:true,value:()=>new Promise(resolve=>{
      const track={stopped:false,stopCount:0,stop(){this.stopped=true;this.stopCount++;}},stream={getTracks:()=>[track]};
      window.__phMediaRequests.push({resolve,stream,track});
    })});
    class SyntheticAudioContext{
      constructor(){this.sampleRate=16000;this.destination={};this.processor=null;this.closed=false;this.closeCount=0;this.resumeResolve=null;this.id=window.__phContexts.length;window.__phContexts.push(this);}
      createMediaStreamSource(){return {connect(){},disconnect(){}};}
      createScriptProcessor(){const processor={onaudioprocess:null,connect(){},disconnect(){}};this.processor=processor;return processor;}
      resume(){if(window.__phHoldResume)return new Promise(resolve=>{this.resumeResolve=resolve;});return Promise.resolve();}
      close(){this.closed=true;this.closeCount++;return Promise.resolve();}
    }
    Object.defineProperty(window,'AudioContext',{configurable:true,value:SyntheticAudioContext});
    window.__phResolveMedia=index=>window.__phMediaRequests[index]?.resolve(window.__phMediaRequests[index].stream);
    window.__phMediaTrackStopped=index=>window.__phMediaRequests[index]?.track.stopped===true;
    window.__phReleaseResume=index=>window.__phContexts[index]?.resumeResolve?.();
    window.__phEmitAudio=(index,length=4096)=>window.__phContexts[index]?.processor?.onaudioprocess?.({inputBuffer:{getChannelData:()=>new Float32Array(length)}});
  });
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){externalOrigins.push(url.origin);await route.abort();return;}
    const entry={method:request.method(),path:url.pathname+url.search,headers:await request.allHeaders(),body:request.postData()||''};requests.push(entry);
    if(entry.method==='POST'&&url.pathname==='/assistant/v1/transcribe'){
      const requestId=entry.headers['x-photohouse-request-id'];
      await route.fulfill({status:200,contentType:'application/json',headers:{'cache-control':'no-store','X-PhotoHouse-Tracking':'enabled','X-PhotoHouse-Request-Id':requestId,'X-PhotoHouse-Receipt-Status':'succeeded'},body:JSON.stringify({version:1,text:nextAsrText,language:'en'})});return;
    }
    if(entry.method==='POST'&&url.pathname.endsWith('/outcome')){await route.fulfill({status:204,headers:{'cache-control':'no-store'},body:''});return;}
    const headers={...entry.headers};delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const result=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    let response={...result};
    if(entry.method==='GET'&&url.pathname==='/assistant/v1/capabilities'){
      const payload={version:1,enabled:true,text:true,transcribe:true,speech:false};response={...result,status:200,headers:{...result.headers,'content-type':'application/json'},body:Buffer.from(JSON.stringify(payload)).toString('base64')};
    }
    const outputHeaders={...response.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try{await route.fulfill({status:response.status,headers:outputHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});
  const signIn=async phone=>{await page.locator('#phone').fill(phone);await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();await page.locator('#assistant-panel').evaluate(panel=>{panel.open=true;});await page.locator('#assistant-form').waitFor({state:'visible'});};
  const mediaCount=()=>page.evaluate(()=>window.__phMediaRequests.length),contexts=()=>page.evaluate(()=>window.__phContexts.length);
  const startCapture=async expected=>{await page.locator('#assistant-mic').evaluate(button=>button.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})));await page.waitForFunction(count=>window.__phMediaRequests.length===count,expected);};
  const holdCapture=async expected=>{const box=await page.locator('#assistant-mic').boundingBox();assert(box,'microphone control is visible');await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.waitForFunction(count=>window.__phMediaRequests.length===count,expected);};
  const resolveMedia=index=>page.evaluate(value=>window.__phResolveMedia(value),index);
  const transcriptions=()=>requests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/transcribe');
  const turns=()=>requests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/turns');
  const waitReview=()=>page.locator('#assistant-transcript-review').waitFor({state:'visible'});

  await signIn('+12025550100');
  await startCapture(1);assert.equal(await page.locator('#assistant-status').textContent(),'正在打开麦克风…','pending permission has a localized opening status');assert.equal(await page.locator('#assistant-send').isDisabled(),true,'first account capture startup blocks Send');
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  await signIn('+12025550101');
  await startCapture(2);assert.equal(await page.locator('#assistant-send').isDisabled(),true,'new account capture startup blocks Send');
  await resolveMedia(0);await page.waitForFunction(()=>window.__phMediaRequests[0].track.stopped);
  assert.equal(await contexts(),0,'stale getUserMedia completion stops its stream before creating AudioContext');
  assert.equal(await page.locator('#assistant-send').isDisabled(),true,'stale finally cannot enable new account Send');
  assert.equal(await page.locator('#assistant-mic').isDisabled(),true,'stale finally cannot enable new account capture');
  assert.equal(await mediaCount(),2,'stale completion does not prompt for another capture');
  await resolveMedia(1);await page.locator('#assistant-stop').waitFor({state:'visible'});
  assert.equal(await page.locator('#assistant-mic').getAttribute('aria-pressed'),'true','current account capture becomes active');
  assert.equal(await page.locator('#assistant-status').textContent(),'正在录音，最长 30 秒。','active capture shows the recording status');
  await page.evaluate(()=>window.__phEmitAudio(0));await page.locator('#assistant-stop').click();await waitReview();
  assert.equal(transcriptions().length,1,'only the current account recording reaches ASR');
  assert.equal(await page.locator('#assistant-transcript').inputValue(),nextAsrText);
  console.log('PASS delayed old-account getUserMedia stops its tracks before AudioContext; current account remains blocked until its own stream resolves');

  await page.locator('#assistant-discard-transcript').click();
  await holdCapture(3);assert.equal(await page.locator('#assistant-status').textContent(),'正在打开麦克风…','hold gesture reports permission wait before stream resolution');
  await resolveMedia(2);await page.waitForFunction(()=>document.getElementById('assistant-mic').getAttribute('aria-pressed')==='true');
  assert.equal(await page.locator('#assistant-status').textContent(),'正在录音，最长 30 秒。','hold gesture reports recording after stream resolution');
  await page.evaluate(()=>window.__phEmitAudio(1));await page.mouse.up();await waitReview();
  assert.equal(transcriptions().length,2,'actual pointer hold and release submits exactly one ASR request');
  assert.equal(await page.locator('#assistant-transcript').inputValue(),nextAsrText);
  console.log('PASS real mouse hold resolves permission, records, and sends one ASR request on release');

  await page.locator('#assistant-discard-transcript').click();
  await startCapture(4);await resolveMedia(3);await page.locator('#assistant-stop').waitFor({state:'visible'});
  await page.evaluate(()=>window.__phEmitAudio(2));await page.locator('#assistant-recording-cancel').click();
  await page.waitForFunction(()=>window.__phMediaRequests[3].track.stopped);
  assert.equal(transcriptions().length,2,'explicit recording cancellation does not POST audio');
  assert.equal(turns().length,0,'recording cancellation does not submit an assistant search');
  assert.equal(await page.locator('#assistant-transcript-review').isVisible(),false,'cancelled audio does not create transcript review');
  console.log('PASS explicit recording cancellation sends neither ASR audio nor an assistant turn');

  await page.evaluate(()=>{window.__phHoldResume=true;});
  await startCapture(5);await resolveMedia(4);await page.waitForFunction(()=>window.__phContexts.length===4);
  await page.locator('#assistant-clear').click();
  await page.waitForFunction(()=>window.__phMediaRequests[4].track.stopped&&window.__phContexts[3].closed);
  assert.equal(await page.evaluate(()=>window.__phMediaRequests[4].track.stopCount),1,'scope reset stops the pending-resume stream exactly once before resume settles');
  assert.equal(await page.evaluate(()=>window.__phContexts[3].closeCount),1,'scope reset closes the pending-resume context exactly once before resume settles');
  await startCapture(6);await resolveMedia(5);await page.waitForFunction(()=>window.__phContexts.length===5);
  await page.evaluate(()=>window.__phReleaseResume(4));await page.waitForFunction(()=>document.getElementById('assistant-mic').getAttribute('aria-pressed')==='true');
  await page.evaluate(()=>window.__phEmitAudio(3,480000));await page.waitForFunction(()=>window.__phMediaRequests[4].track.stopped);
  await page.evaluate(()=>window.__phReleaseResume(3));await page.waitForTimeout(50);
  assert.equal(await page.locator('#assistant-mic').getAttribute('aria-pressed'),'true','stale processor completion cannot clear the current capture');
  assert.equal(await page.locator('#assistant-send').isDisabled(),true,'stale resume cleanup cannot enable Send during current capture');
  assert.equal(await page.locator('#assistant-mic').isDisabled(),true,'stale resume cleanup cannot enable another capture');
  assert.equal(await mediaCount(),6,'stale resume does not cause a new microphone prompt');
  assert.equal(transcriptions().length,2,'stale processor does not submit audio for transcription');
  assert.equal(await page.evaluate(()=>window.__phContexts[3].closed),true,'stale resumed context is closed');
  await page.evaluate(()=>window.__phEmitAudio(4));await page.locator('#assistant-stop').click();await waitReview();
  assert.equal(transcriptions().length,3,'current capture reaches ASR only after explicit Stop');
  assert.equal(await page.locator('#assistant-transcript').inputValue(),nextAsrText);
  console.log('PASS stale resume and processor completion cannot invoke ASR or clear current capture; current capture succeeds after explicit Stop');

  await page.locator('#assistant-discard-transcript').click();
  await holdCapture(7);await page.mouse.up();
  await page.getByText('录音尚未开始，请再次按住说话。').waitFor();
  assert.equal(await page.locator('#assistant-mic').isDisabled(),false,'releasing during permission wait immediately clears the startup guard');
  await resolveMedia(6);await page.waitForFunction(()=>window.__phMediaRequests[6].track.stopped);
  assert.equal(await contexts(),5,'late permission after hold release never creates an audio context');
  assert.equal(transcriptions().length,3,'releasing before capture starts sends no audio to ASR');
  await page.evaluate(()=>{window.__phHoldResume=false;});
  await startCapture(8);await resolveMedia(7);await page.locator('#assistant-stop').waitFor({state:'visible'});
  await page.evaluate(()=>window.__phEmitAudio(5));await page.locator('#assistant-stop').click();await waitReview();
  assert.equal(transcriptions().length,4,'a fresh explicit capture works after pending hold release');
  console.log('PASS pending hold release aborts microphone setup, discards late permission, and leaves fresh explicit capture available');

  await page.locator('#assistant-discard-transcript').click();
  await startCapture(9);await resolveMedia(8);await page.locator('#assistant-stop').waitFor({state:'visible'});
  await page.evaluate(()=>window.__phEmitAudio(6));await page.locator('#assistant-clear').click();
  await page.waitForFunction(()=>window.__phMediaRequests[8].track.stopped&&window.__phContexts[6].closed);
  assert.equal(await page.evaluate(()=>window.__phMediaRequests[8].track.stopCount),1,'scope reset aborts an active capture stream exactly once');
  assert.equal(await page.evaluate(()=>window.__phContexts[6].closeCount),1,'scope reset closes the active capture context exactly once');
  assert.equal(transcriptions().length,4,'scope reset signal discards an active recording without ASR');
  console.log('PASS abort signal discards active assistant capture and closes its resources exactly once');

  await page.locator('#assistant-text').fill('Keep this typed question while the page is hidden.');
  await page.evaluate(()=>{window.__phHoldResume=true;});
  await startCapture(10);await resolveMedia(9);await page.waitForFunction(()=>window.__phContexts.length===8);
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>window.__phMediaRequests[9].track.stopped&&window.__phContexts[7].closed);
  assert.equal(await page.evaluate(()=>window.__phMediaRequests[9].track.stopCount),1,'visibility invalidation stops pending-resume tracks immediately and exactly once');
  assert.equal(await page.evaluate(()=>window.__phContexts[7].closeCount),1,'visibility invalidation closes pending-resume context before resume settles');
  assert.equal(await page.locator('#assistant-text').inputValue(),'Keep this typed question while the page is hidden.','ordinary background invalidation preserves typed composer text');
  assert.equal(transcriptions().length,4,'background invalidation of pending resume cannot submit an ASR request');
  await page.evaluate(()=>window.__phReleaseResume(7));await page.waitForTimeout(30);
  assert.equal(transcriptions().length,4,'late resume completion after visibility invalidation remains discarded');
  console.log('PASS visibility invalidation immediately cancels pending-resume assistant capture, preserves typed text, and sends no ASR');

  assert.deepEqual(externalOrigins,[],'synthetic capture flow made no external requests');
  assert.deepEqual(pageErrors,[],'synthetic capture flow has no browser errors');
  console.log('EXTERNAL_ORIGINS []');
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');}catch{}bridge.kill();
});
