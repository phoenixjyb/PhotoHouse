/* Receipt-only recovery for an ambiguous protected assistant POST. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-pending-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'assistant_pending_recovery_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pendingRpc=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const call=pendingRpc.get(result.id);if(call){pendingRpc.delete(result.id);call.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Browser bridge exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Browser bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const browserRequests=[],pageErrors=[],checkpoints=[];
let holdNextTurn=null,dropNextTurn=false,failNextTurn=false,forceTrackingDisabled=false,receiptOverride=null,receiptOperationOverride=null;
function gateTurn(){let arrive,release;const seen=new Promise(resolve=>{arrive=resolve;});const released=new Promise(resolve=>{release=resolve;});holdNextTurn={arrive,released};return {seen,release};}
function count(method,pathPart){return browserRequests.filter(item=>item.method===method&&item.path.startsWith(pathPart)).length;}
function checkpoint(text){checkpoints.push(text);console.log('PASS '+text);}
function jsonResponse(response,status,body){return {...response,status,headers:{...response.headers,'content-type':'application/json'},body:Buffer.from(JSON.stringify(body)).toString('base64')};}
let browser,context,page;
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){await route.abort();return;}
    const entry={method:request.method(),path:url.pathname+url.search,headers:await request.allHeaders(),body:request.postData()||''};browserRequests.push(entry);
    const headers={...entry.headers};delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    let response;
    if(entry.method==='POST'&&url.pathname==='/assistant/v1/turns'&&failNextTurn){
      failNextTurn=false;await rpc({command:'discovery-off'});response=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});await rpc({command:'discovery-on'});
    }else response=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    if(entry.method==='GET'&&url.pathname==='/assistant/v1/capabilities'){
      const value=JSON.parse(Buffer.from(response.body,'base64').toString());value.transcribe=true;response=jsonResponse(response,response.status,value);
    }
    if(entry.method==='GET'&&/^\/assistant\/v1\/receipts\/[0-9a-f-]+$/.test(url.pathname)&&receiptOverride){
      const mode=receiptOverride;receiptOverride=null;
      if(mode==='404')response=jsonResponse(response,404,{error:'receipt_unavailable',detail:'Receipt unavailable'});
      else {const ident=url.pathname.split('/').at(-1);response=jsonResponse(response,200,{version:1,request_id:ident,operation:receiptOperationOverride||'turn',status:mode});receiptOperationOverride=null;}
    }
    if(entry.method==='POST'&&url.pathname==='/assistant/v1/turns'&&forceTrackingDisabled){
      forceTrackingDisabled=false;response=jsonResponse(response,503,{error:'tracking_unavailable',detail:'Request tracking unavailable'});
      response.headers={...response.headers,'x-photohouse-tracking':'disabled'};
      delete response.headers['x-photohouse-request-id'];delete response.headers['x-photohouse-receipt-status'];
    }
    if(entry.method==='POST'&&url.pathname==='/assistant/v1/turns'&&holdNextTurn){
      const gate=holdNextTurn;holdNextTurn=null;gate.arrive();await gate.released;
    }
    if(entry.method==='POST'&&url.pathname==='/assistant/v1/turns'&&dropNextTurn){dropNextTurn=false;await route.abort('failed');return;}
    const outputHeaders={...response.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try{await route.fulfill({status:response.status,headers:outputHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  await context.addInitScript(()=>{
    window.__phGetUserMediaCalls=0;
    const media=navigator.mediaDevices||{};
    try{Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:media});}catch{}
    try{Object.defineProperty(media,'getUserMedia',{configurable:true,value:()=>{window.__phGetUserMediaCalls++;return Promise.reject(new Error('Synthetic capture must not start'));}});window.__phGetUserMediaStubbed=true;}catch{window.__phGetUserMediaStubbed=false;}
  });
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await page.evaluate(()=>window.__phGetUserMediaStubbed),true,'browser microphone permission path is instrumented');
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#grid .asset').first().waitFor();
  await page.locator('#assistant-panel > summary').click();await page.locator('#assistant-form').waitFor({state:'visible'});
  const posts=()=>browserRequests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/turns');
  const getReceipts=()=>browserRequests.filter(item=>item.method==='GET'&&/^\/assistant\/v1\/receipts\//.test(item.path));
  const recoveryKey='photohouse.assistant.turn-recovery.v1';
  const storedRecovery=()=>page.evaluate(key=>sessionStorage.getItem(key),recoveryKey);
  const writeRecovery=value=>page.evaluate(({key,pointer})=>sessionStorage.setItem(key,JSON.stringify(pointer)),{key:recoveryKey,pointer:value});
  const writeRecoveryRaw=raw=>page.evaluate(({key,value})=>sessionStorage.setItem(key,value),{key:recoveryKey,value:raw});
  const beginAmbiguousTurn=async text=>{
    dropNextTurn=true;await page.locator('#assistant-text').fill(text);await page.locator('#assistant-send').click();
    await page.locator('#assistant-pending-turn').waitFor();await page.waitForFunction(()=>document.getElementById('assistant-cancel').hidden);
  };
  const recoveryControlsVisibility=async()=>page.evaluate(()=>{
    const nav=document.querySelector('#memory-navigation'),targets=['assistant-receipt-status','assistant-receipt-check','assistant-clear'];
    const nr=nav.getBoundingClientRect();
    const details=targets.map(id=>{
      const el=document.getElementById(id),r=el.getBoundingClientRect();
      const x=r.left+r.width/2,y=r.top+r.height/2,hit=document.elementFromPoint(x,y);
      const overlapsNav=r.left<nr.right&&r.right>nr.left&&r.top<nr.bottom&&r.bottom>nr.top;
      return {id,visible:!el.hidden&&r.width>0&&r.height>0&&r.top>=0&&r.bottom<=innerHeight,overlapsNav,hit:hit?.id||hit?.tagName||null,hitInside:!!hit&&(hit===el||el.contains(hit))};
    });
    return {ok:details.every(item=>item.visible&&!item.overlapsNav&&item.hitInside),details};
  });

  // Chinese pending recovery card remains usable on a narrow viewport at 150% zoom.
  await page.setViewportSize({width:390,height:844});dropNextTurn=true;
  await page.locator('#assistant-text').fill('查找照片');await page.locator('#assistant-send').click();await page.locator('#assistant-pending-turn').waitFor();
  const localePostCount=posts().length;await page.locator('#language').click();
  assert.match(await page.locator('#assistant-pending-status').textContent(),/outcome is unknown|Sending this request/);
  assert.equal(await page.locator('#assistant-pending-question').textContent(),'查找照片');assert.equal(posts().length,localePostCount);
  await page.locator('#language').click();assert.match(await page.locator('#assistant-pending-status').textContent(),/结果尚不确定|正在提交/);
  assert.equal(await page.locator('#assistant-clear').textContent(),'清空输入');
  await page.evaluate(()=>{document.documentElement.style.zoom='150%';});
  assert.equal(await page.locator('#assistant-pending-question').textContent(),'查找照片');
  assert(await page.locator('#assistant-pending-check').isVisible());assert(await page.locator('#assistant-pending-ack').isVisible());assert(await page.locator('#assistant-pending-ack').isEnabled());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Chinese pending UI fits 390px at 150% zoom');
  await page.locator('#assistant-pending-turn').scrollIntoViewIfNeeded();
  assert(await page.locator('#assistant-pending-check').isVisible());assert(await page.locator('#assistant-pending-ack').isVisible());
  await page.screenshot({path:path.join(artifacts,'assistant-pending-zh-390px-150pct.png'),fullPage:false});
  await page.locator('#assistant-pending-ack').click();await page.evaluate(()=>{document.documentElement.style.zoom='';});
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});await page.locator('#language').click();
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#grid .asset').first().waitFor();await page.locator('#assistant-panel').evaluate(el=>{el.open=true;});await page.locator('#assistant-form').waitFor({state:'visible'});
  checkpoint('Chinese pending card renders with reachable receipt and acknowledgement controls at 390px and 150% zoom');

  // A completed valid reply clears only the submitted text, preserving input typed while waiting.
  const postsBeforeGate=posts().length;let gate=gateTurn();await page.locator('#assistant-text').fill('find photos');await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled);await page.locator('#assistant-send').click();await gate.seen;
  assert(await page.locator('#assistant-pending-turn').isVisible());assert.equal(await page.locator('#assistant-pending-question').textContent(),'find photos');
  assert.equal(await page.locator('#assistant-text').inputValue(),'','accepted POST moves its question into the pending card');
  assert.equal(await page.locator('#assistant-receipt-id').isVisible(),false,'request UUID stays behind collapsed details');
  await page.locator('#assistant-text').fill('draft to clear');const postCountBeforeClear=posts().length;
  await page.locator('#assistant-clear').click();assert.equal(await page.locator('#assistant-text').inputValue(),'','clear empties only the composer while a turn is pending');
  assert(await page.locator('#assistant-pending-turn').isVisible());assert.equal(posts().length,postCountBeforeClear,'clear cannot acknowledge or resend a pending turn');
  await page.locator('#assistant-text').fill('new unsent draft');assert.equal(await page.locator('#assistant-send').isDisabled(),true);
  assert.equal(await page.locator('#assistant-mic').isDisabled(),true);assert.equal(count('POST','/assistant/v1/transcribe'),0);
  assert(await page.locator('#assistant-pending-check').isVisible());assert(await page.locator('#assistant-pending-ack').isVisible());assert(await page.locator('#assistant-cancel').isVisible());
  await page.locator('#assistant-form').evaluate(form=>form.requestSubmit());await page.waitForTimeout(20);assert.equal(posts().length,postsBeforeGate+1,'direct form submission cannot double-post while pending');
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'pending UI fits mobile width');
  await page.screenshot({path:path.join(artifacts,'assistant-pending-mobile.png'),fullPage:true});
  gate.release();await page.locator('#assistant-pending-turn').waitFor({state:'hidden'});await page.locator('#assistant-reply').waitFor();
  assert.equal(await page.locator('#assistant-text').inputValue(),'new unsent draft','valid response preserves later typing');assert.equal(posts().length,postsBeforeGate+1);
  checkpoint('Pending is immutable/read-only, disables submit and recording, and successful completion preserves a newer draft');

  // Cancel stops waiting only. An actual server receipt can still report success; checking it is GET-only.
  await page.locator('#assistant-clear').click();gate=gateTurn();await page.locator('#assistant-text').fill('find videos');await page.locator('#assistant-send').click();await gate.seen;
  assert(await page.locator('#assistant-pending-turn').isVisible());await page.locator('#assistant-text').fill('keep this draft on acknowledge');
  await page.locator('#assistant-cancel').click();await page.locator('#assistant-pending-status').waitFor();
  await page.locator('#assistant-pending-turn').getByText(/server may still process/i).waitFor();
  await page.waitForFunction(()=>document.getElementById('assistant-cancel').hidden);assert.equal(await page.locator('#assistant-pending-question').textContent(),'find videos');
  gate.release();await page.waitForTimeout(30);const turnPostsBeforeCheck=posts().length,readsBefore=getReceipts().length;
  await page.locator('#assistant-pending-check').click();await page.locator('#assistant-pending-status').getByText(/reply and updated context were not recovered/i).waitFor();
  assert.equal(await page.locator('#assistant-reply').textContent(),'','old reply is not presented as the missing answer');
  assert.equal(posts().length,turnPostsBeforeCheck,'checking receipt never repeats the turn POST');assert.equal(getReceipts().length,readsBefore+1);
  assert.equal(getReceipts().at(-1).method,'GET');
  assert(await page.locator('#assistant-pending-check').isVisible());assert(await page.locator('#assistant-pending-ack').isVisible());
  await page.screenshot({path:path.join(artifacts,'assistant-pending-success-receipt-mobile.png'),fullPage:true});
  await page.locator('#assistant-pending-ack').click();await page.locator('#assistant-pending-turn').waitFor({state:'hidden'});
  assert.equal(await page.locator('#assistant-text').inputValue(),'keep this draft on acknowledge','acknowledgement preserves newer draft');
  await page.locator('#assistant-text').fill('find photos');await page.locator('#assistant-send').click();await page.locator('#assistant-reply').waitFor();
  const afterAckPayload=JSON.parse(posts().at(-1).body||'{}');assert.equal(afterAckPayload.text,'find photos');assert.equal(afterAckPayload.context,null,'acknowledgement clears the old context');
  checkpoint('Cancel retains the question; receipt GET reports unrecovered reply/context; acknowledgement preserves draft and clears prior context');

  // A real failed HTTP outcome remains pending; restoration fills an empty composer but never submits.
  await page.locator('#assistant-clear').click();failNextTurn=true;await page.locator('#assistant-text').fill('find photos');await page.locator('#assistant-send').click();
  await page.locator('#assistant-pending-restore').waitFor({state:'visible'});const failedCount=posts().length,failedQuestion='find photos';
  assert.equal(await page.locator('#assistant-text').inputValue(),'');const failedRequestId=await page.locator('#assistant-receipt-id').inputValue();
  await page.locator('#assistant-pending-restore').click();await page.locator('#assistant-pending-turn').waitFor({state:'hidden'});
  assert.equal(await page.locator('#assistant-text').inputValue(),failedQuestion);assert.equal(posts().length,failedCount,'restoring never sends');
  await page.locator('#assistant-send').click();await page.locator('#assistant-reply').waitFor();
  assert.notEqual(posts().at(-1).headers['x-photohouse-request-id'],failedRequestId,'explicit resubmission gets a fresh request ID');
  checkpoint('Failed receipt restores only into an empty composer and requires an explicit new send');

  // An interrupted receipt uses the same guarded restoration; a newer draft wins.
  await page.locator('#assistant-clear').click();dropNextTurn=true;await page.locator('#assistant-text').fill('find videos');await page.locator('#assistant-send').click();
  await page.locator('#assistant-pending-turn').waitFor();await page.waitForFunction(()=>document.getElementById('assistant-cancel').hidden);receiptOverride='interrupted';
  await page.locator('#assistant-pending-check').click();await page.locator('#assistant-pending-restore').waitFor({state:'visible'});
  await page.locator('#assistant-text').fill('keep newer draft');assert(await page.locator('#assistant-pending-restore').isDisabled());
  assert(await page.locator('#assistant-pending-turn').isVisible(),'disabled restore leaves the pending card open');
  assert.equal(await page.locator('#assistant-pending-question').textContent(),'find videos','refused restore retains the pending question');
  assert.equal(await page.locator('#assistant-text').inputValue(),'keep newer draft');await page.locator('#assistant-pending-ack').click();await page.locator('#assistant-pending-turn').waitFor({state:'hidden'});
  assert.equal(await page.locator('#assistant-text').inputValue(),'keep newer draft');checkpoint('Interrupted status restore refuses to replace a newer draft; explicit acknowledgement closes pending');

  // A receipt for a different operation is invalid and cannot clear a pending turn.
  await page.locator('#assistant-clear').click();dropNextTurn=true;await page.locator('#assistant-text').fill('find photos');await page.locator('#assistant-send').click();
  await page.locator('#assistant-pending-turn').waitFor();await page.waitForFunction(()=>document.getElementById('assistant-cancel').hidden);
  receiptOperationOverride='speech';receiptOverride='succeeded';await page.locator('#assistant-pending-check').click();
  await page.locator('#assistant-pending-help').getByText(/could not verify|could not be checked/i).waitFor();
  assert(await page.locator('#assistant-pending-turn').isVisible());assert.equal(await page.locator('#assistant-pending-question').textContent(),'find photos');
  await page.locator('#assistant-pending-ack').click();checkpoint('A mismatched receipt operation is rejected and leaves the pending turn intact');

  // A missing receipt is not proof that the request was not processed; tracking-disabled has no ID lookup.
  await page.locator('#assistant-clear').click();dropNextTurn=true;await page.locator('#assistant-text').fill('find photos');await page.locator('#assistant-send').click();
  await page.locator('#assistant-pending-turn').waitFor();await page.waitForFunction(()=>document.getElementById('assistant-cancel').hidden);receiptOverride='404';
  await page.locator('#assistant-pending-check').click();await page.locator('#assistant-pending-help').getByText(/does not mean the request was not processed/i).waitFor();
  const unknownPosts=posts().length;await page.locator('#assistant-text').fill('new input after 404');await page.locator('#assistant-pending-ack').click();
  assert.equal(await page.locator('#assistant-text').inputValue(),'new input after 404');assert.equal(posts().length,unknownPosts);
  await page.locator('#assistant-clear').click();forceTrackingDisabled=true;dropNextTurn=false;await page.locator('#assistant-text').fill('find videos');await page.locator('#assistant-send').click();
  await page.locator('#assistant-pending-status').getByText(/does not show whether the server processed/i).waitFor();
  assert.equal(await page.locator('#assistant-pending-check').isDisabled(),true);assert(await page.locator('#assistant-pending-ack').isEnabled());await page.locator('#assistant-pending-ack').click();
  checkpoint('404 and tracking-disabled states remain uncertain and expose an explicit acknowledge path');

  // A dropped reply survives a same-tab reload as a scope-bound receipt pointer only.
  await beginAmbiguousTurn('private question must not persist');
  const pointerRaw=await storedRecovery(),pointer=JSON.parse(pointerRaw),postCountBeforeReload=posts().length,receiptCountBeforeReload=getReceipts().length;
  assert.deepEqual(Object.keys(pointer).sort(),['account_id','library_id','request_id','version']);
  assert.equal(pointer.version,1);assert.equal(pointer.request_id,posts().at(-1).headers['x-photohouse-request-id']);
  assert.equal(pointerRaw.includes('private question'),false);
  await page.reload();await page.locator('#assistant-receipt-check').waitFor({state:'visible'});
  assert.equal(await page.locator('#assistant-receipt-id').inputValue(),pointer.request_id);
  assert.match(await page.locator('#assistant-receipt-status').textContent(),/可能已到达服务器|may have reached the server/);
  assert.equal(posts().length,postCountBeforeReload,'reload recovery never resends the turn');
  assert.equal(getReceipts().length,receiptCountBeforeReload,'receipt lookup is user initiated, not automatic');
  await page.locator('#assistant-text').fill('must not submit while recovery is unresolved');
  await page.locator('#assistant-form').evaluate(form=>form.requestSubmit());await page.waitForTimeout(20);
  assert.equal(posts().length,postCountBeforeReload,'direct form submission is rejected while recovered outcome is unresolved');
  await page.locator('#assistant-mic').evaluate(button=>button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,cancelable:true,isPrimary:true,pointerId:77})));
  await page.waitForTimeout(20);assert.equal(await page.evaluate(()=>window.__phGetUserMediaCalls),0,'synthetic mic pointerdown cannot acquire audio during unresolved recovery');
  await page.locator('#assistant-text').fill('');
  await page.locator('#assistant-transcript').evaluate(el=>{el.value='injected transcript';document.getElementById('assistant-use-transcript').dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));});
  assert.equal(await page.locator('#assistant-text').inputValue(),'','transcript insertion is rejected while recovered outcome is unresolved');
  assert.equal(posts().length,postCountBeforeReload,'submission and transcript insertion bypass attempts create no new turn POST');
  await page.evaluate(()=>{document.documentElement.style.zoom='';});await page.setViewportSize({width:1280,height:900});
  await page.locator('#assistant-panel').evaluate(el=>{el.open=true;el.scrollIntoView({block:'center'});});await page.locator('#assistant-receipt-status').scrollIntoViewIfNeeded();
  await page.locator('#assistant-receipt-check').scrollIntoViewIfNeeded();
  await page.evaluate(()=>{const nav=document.querySelector('#memory-navigation'),clear=document.querySelector('#assistant-clear'),overlap=nav.getBoundingClientRect().bottom+12-clear.getBoundingClientRect().top;if(overlap>0)window.scrollBy(0,-overlap);});
  let visibility=await recoveryControlsVisibility();assert(visibility.ok,`desktop recovery status and controls are in viewport and clear of sticky navigation: ${JSON.stringify(visibility.details)}`);
  await page.screenshot({path:path.join(artifacts,'assistant-recovery-desktop.png'),fullPage:false});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.zoom='150%';});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'recovery offer fits 390px viewport');
  await page.locator('#assistant-panel').evaluate(el=>{el.open=true;el.scrollIntoView({block:'center'});});await page.locator('#assistant-receipt-status').scrollIntoViewIfNeeded();
  await page.locator('#assistant-receipt-check').scrollIntoViewIfNeeded();
  await page.evaluate(()=>{const nav=document.querySelector('#memory-navigation'),clear=document.querySelector('#assistant-clear'),overlap=nav.getBoundingClientRect().bottom+12-clear.getBoundingClientRect().top;if(overlap>0)window.scrollBy(0,-overlap);});
  visibility=await recoveryControlsVisibility();assert(visibility.ok,`390px recovery status and controls are in viewport and clear of sticky navigation: ${JSON.stringify(visibility.details)}`);
  await page.screenshot({path:path.join(artifacts,'assistant-recovery-mobile-390px-150pct.png'),fullPage:false});
  await page.evaluate(()=>{document.documentElement.style.zoom='';});
  assert.match(await page.locator('#assistant-clear').textContent(),/确认并重新开始|Acknowledge and start fresh/);
  await page.locator('#assistant-receipt-check').click();
  await page.locator('#assistant-receipt-status').getByText(/无法恢复其回复和搜索上下文|reply and search context are unavailable/).waitFor();
  assert.equal(posts().length,postCountBeforeReload,'receipt GET does not duplicate the POST');
  assert.equal(getReceipts().length,receiptCountBeforeReload+1);assert.equal(getReceipts().at(-1).method,'GET');
  assert.equal(await storedRecovery(),null,'terminal confirmation clears the tab recovery pointer');
  assert.equal(await page.locator('#assistant-receipt-check').isDisabled(),true,'terminal recovered receipt remains disabled after the request finally handler');
  assert.equal(await page.locator('#assistant-reply').textContent(),'','receipt status does not fabricate a recovered answer');
  await page.locator('#assistant-text').fill('a new explicit search');
  assert.equal(await page.locator('#assistant-send').isDisabled(),false,'terminal recovered receipt unblocks a new explicit turn');
  const postCountAfterRecovery=posts().length;await page.locator('#assistant-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!!document.getElementById('assistant-reply').textContent.trim());
  assert.equal(posts().length,postCountAfterRecovery+1,'an explicit new turn works after terminal recovery');
  checkpoint('Same-scope reload offers an explicit receipt GET only, retains no query text, and reports missing reply/context honestly');

  // Account/library mismatches and malformed storage never trigger a receipt lookup.
  const beforeScopeCheck=getReceipts().length;
  await writeRecovery({...pointer,account_id:'different-account'});await page.reload();await page.locator('#grid .asset').first().waitFor();
  assert.equal(await storedRecovery(),null);assert.equal(getReceipts().length,beforeScopeCheck);
  await writeRecovery({...pointer,library_id:'not-a-member-library'});await page.reload();await page.locator('#grid .asset').first().waitFor();
  assert.equal(await storedRecovery(),null);assert.equal(getReceipts().length,beforeScopeCheck);
  const invalidPointers=['{malformed',JSON.stringify({...pointer,extra:'not allowed'}),JSON.stringify({...pointer,request_id:'not-a-uuid'}),'x'.repeat(513)];
  for(const invalid of invalidPointers){await writeRecoveryRaw(invalid);await page.reload();await page.locator('#grid .asset').first().waitFor();
    assert.equal(await storedRecovery(),null);assert.equal(getReceipts().length,beforeScopeCheck);}
  assert.deepEqual(pageErrors,[]);checkpoint('Account/library mismatch and malformed tab storage clear without receipt access or page errors');
  await page.locator('#assistant-panel > summary').click();await page.locator('#assistant-form').waitFor({state:'visible'});

  // sessionStorage write failure leaves the existing same-page pending flow intact.
  await page.evaluate(key=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(name,value){if(name===key)throw new DOMException('blocked','SecurityError');return original.call(this,name,value);};},recoveryKey);
  const receiptsBeforeStorageFailure=getReceipts().length;await beginAmbiguousTurn('storage failure question');
  assert.equal(await page.locator('#assistant-pending-question').textContent(),'storage failure question');assert.equal(await storedRecovery(),null);
  const postsBeforeStorageReload=posts().length;await page.reload();await page.locator('#grid .asset').first().waitFor();
  assert.equal(posts().length,postsBeforeStorageReload);assert.equal(getReceipts().length,receiptsBeforeStorageFailure);
  assert.equal(await page.locator('#assistant-receipt').isVisible(),false);await page.locator('#assistant-panel > summary').click();
  checkpoint('sessionStorage failure preserves current-page receipt UI without preventing the turn or triggering reload replay');

  // Switching authenticated scope fences an old in-flight response and hides its input.
  gate=gateTurn();await page.locator('#assistant-text').fill('private old-scope question');await page.locator('#assistant-send').click();await gate.seen;
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await storedRecovery(),null,'explicit logout clears the pending recovery pointer');
  assert.equal(await page.locator('#assistant-text').inputValue(),'');assert.equal(await page.locator('#assistant-pending-turn').isVisible(),false);
  gate.release();await page.waitForTimeout(50);assert.equal(await page.locator('#assistant-text').inputValue(),'');
  assert.equal(await page.locator('#assistant-pending-question').textContent(),'');
  assert.equal(browserRequests.some(item=>item.method==='POST'&&item.path==='/assistant/v1/turns'&&item.body.includes('private old-scope question')),true);
  assert.deepEqual(pageErrors,[]);assert(getReceipts().every(item=>item.method==='GET'));
  checkpoint('Logout clears/fences a pending request without restoring its private question after the old response returns');

  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checkpoints,turnPosts:posts().length,receiptGets:getReceipts().length,pageErrors,syntheticBackend:true,syntheticAsrCapabilityOverride:true,transport:'Chromium intercepted requests fulfilled through an in-process ASGI TestClient bridge; no listener or production endpoint'},null,2));
  console.log(`Assistant pending recovery checks: ${checkpoints.length} passed. Artifacts: ${artifacts}`);
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{
  try{await context?.close();}catch(_){}try{await browser?.close();}catch(_){}
  try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.stdin.end();}catch(_){}
});
