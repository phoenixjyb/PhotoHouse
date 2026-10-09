/* Synthetic ASR acceptance, request linkage, and scope fencing for Web assistant. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-transcript-'));
fs.mkdirSync(artifacts,{recursive:true,mode:0o700});fs.chmodSync(artifacts,0o700);console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),
  [path.join(__dirname,'assistant_pending_recovery_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,nextAsr=null,nextTurn=0;
const pendingRpc=new Map(),requests=[],pageErrors=[],externalOrigins=[],activeGates=new Set();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){readyResolve();return;}const call=pendingRpc.get(value.id);if(call){pendingRpc.delete(value.id);call.resolve(value);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Synthetic API bridge exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Synthetic API bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
function gate(){let arrive,release,finish;const value={arrived:new Promise(resolve=>{arrive=resolve;}),released:new Promise(resolve=>{release=resolve;}),finished:new Promise(resolve=>{finish=resolve;}),arrive:()=>arrive(),release:()=>release(),finish:()=>finish()};activeGates.add(value);return value;}
function responseHeaders(requestId,mode='enabled'){
  if(mode==='disabled')return {'X-PhotoHouse-Tracking':'disabled'};
  return {'X-PhotoHouse-Tracking':'enabled','X-PhotoHouse-Request-Id':requestId,'X-PhotoHouse-Receipt-Status':'succeeded'};
}
let browser,context,page;
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),
    args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await context.addInitScript(()=>{
    window.__phGetUserMediaCalls=0;window.__phAudioProcessors=[];window.__phMalformedWav=false;
    const stream={getTracks:()=>[{stop(){}}]};
    const media=navigator.mediaDevices||{};try{Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:media});}catch{}
    Object.defineProperty(media,'getUserMedia',{configurable:true,value:async()=>{window.__phGetUserMediaCalls++;return stream;}});
    class SyntheticAudioContext{
      constructor(){this.sampleRate=16000;this.destination={};this.processor=null;}
      createMediaStreamSource(){return {connect(){},disconnect(){}};}
      createScriptProcessor(){const processor={onaudioprocess:null,connect(){},disconnect(){}};this.processor=processor;window.__phAudioProcessors.push(processor);return processor;}
      async resume(){this.processor?.onaudioprocess?.({inputBuffer:{getChannelData:()=>new Float32Array(4096)}});}
      async close(){}
    }
    Object.defineProperty(window,'AudioContext',{configurable:true,value:SyntheticAudioContext});
    const OriginalFile=window.File;
    Object.defineProperty(window,'File',{configurable:true,writable:true,value:class SyntheticFile extends OriginalFile{
      constructor(parts,name,options){
        if(window.__phMalformedWav&&options?.type==='audio/wav'&&parts?.[0] instanceof ArrayBuffer){
          const damaged=parts[0].slice(0);new DataView(damaged).setUint32(24,8000,true);parts=[damaged];window.__phMalformedWav=false;
        }
        super(parts,name,options);
      }
    }});
    window.__phSyntheticAudio=true;
  });
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){externalOrigins.push(url.origin);await route.abort();return;}
    const entry={method:request.method(),path:url.pathname+url.search,headers:await request.allHeaders(),body:request.postData()||''};requests.push(entry);
    if(entry.method==='POST'&&url.pathname==='/assistant/v1/transcribe'){
      const requestId=entry.headers['x-photohouse-request-id'],mode=nextAsr||{text:'synthetic transcript',language:'en',tracking:'enabled'};nextAsr=null;
      if(mode.gate){mode.gate.arrive();await mode.gate.released;}
      const body=mode.malformed?{version:1,text:mode.text||'bad result',language:'invalid'}:{version:1,text:mode.text,language:mode.language||'en'};
      try{await route.fulfill({status:200,contentType:'application/json',headers:{'cache-control':'no-store',...responseHeaders(requestId,mode.tracking||'enabled')},body:JSON.stringify(body)});}
      catch(error){if(!/closed|handled|cancel|abort|Invalid InterceptionId/i.test(error.message))throw error;}
      finally{mode.gate?.finish();activeGates.delete(mode.gate);}
      return;
    }
    if(entry.method==='POST'&&url.pathname==='/assistant/v1/turns'){
      nextTurn++;const requestBody=JSON.parse(entry.body),id=String(700+nextTurn),ctx={library_id:requestBody.library_id,binding:'a'.repeat(64),fingerprint:'b'.repeat(64),filters:{},visible_ids:[id],total:1};
      const reply={version:1,kind:'results',reply:`Synthetic reply ${nextTurn}`,context:ctx,filters:{},items:[{id,kind:'image'}],total:1,has_more:false,effect:null};
      await route.fulfill({status:200,contentType:'application/json',headers:{'cache-control':'no-store',...responseHeaders(entry.headers['x-photohouse-request-id'])},body:JSON.stringify(reply)});return;
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
  assert.equal(await page.evaluate(()=>window.__phSyntheticAudio),true);
  const signIn=async phone=>{await page.locator('#phone').fill(phone);await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();};
  const turns=()=>requests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/turns');
  const transcriptions=()=>requests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/transcribe');
  const openAssistant=async()=>{await page.locator('#assistant-panel').evaluate(panel=>{panel.open=true;});await page.locator('#assistant-form').waitFor({state:'visible'});};
  const submitText=async text=>{const expected=Math.min(await page.locator('#assistant-turn-trail-list > li').count()+1,8),response=page.waitForResponse(value=>value.url().endsWith('/assistant/v1/turns'));await page.locator('#assistant-text').fill(text);await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled);await page.locator('#assistant-form').evaluate(form=>form.requestSubmit());await response;await page.waitForFunction(count=>document.querySelectorAll('#assistant-turn-trail-list > li').length===count,expected);await page.waitForFunction(value=>document.querySelector('#assistant-reply')?.textContent===value,`Synthetic reply ${nextTurn}`);};
  const record=async()=>{const previous=transcriptions().length;await page.locator('#assistant-mic').evaluate(button=>button.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})));await page.locator('#assistant-stop').waitFor({state:'visible',timeout:5000});await page.locator('#assistant-stop').click();return previous+1;};
  const waitReview=async()=>await page.locator('#assistant-transcript-review').waitFor({state:'visible'});
  const scaleText150=()=>page.locator('#assistant-panel').evaluate(root=>{
    const nodes=[root,...root.querySelectorAll('*')].filter(node=>node.tagName==='TEXTAREA'||[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&child.textContent.trim()));
    const rows=nodes.map((node,index)=>({index,size:parseFloat(getComputedStyle(node).fontSize),line:parseFloat(getComputedStyle(node).lineHeight),oldSize:node.style.fontSize,oldLine:node.style.lineHeight}));
    rows.forEach(row=>{const node=nodes[row.index];node.style.fontSize=`${row.size*1.5}px`;if(Number.isFinite(row.line))node.style.lineHeight=`${row.line*1.5}px`;});return rows;
  });
  const textScaleValid=rows=>page.locator('#assistant-panel').evaluate((root,values)=>{const nodes=[root,...root.querySelectorAll('*')].filter(node=>node.tagName==='TEXTAREA'||[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&child.textContent.trim()));return values.every(row=>Math.abs(parseFloat(getComputedStyle(nodes[row.index]).fontSize)-row.size*1.5)<0.2);},rows);
  const restoreTextScale=rows=>page.locator('#assistant-panel').evaluate((root,values)=>{const nodes=[root,...root.querySelectorAll('*')].filter(node=>node.tagName==='TEXTAREA'||[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&child.textContent.trim()));for(const row of values){nodes[row.index].style.fontSize=row.oldSize;nodes[row.index].style.lineHeight=row.oldLine;}},rows);
  const layout=()=>page.evaluate(()=>({width:innerWidth,pageWidth:document.documentElement.scrollWidth,review:(()=>{const r=document.querySelector('#assistant-transcript-review').getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};})(),panel:document.querySelector('#assistant-panel').getBoundingClientRect().toJSON()}));
  await signIn('+12025550100');await openAssistant();await page.setViewportSize({width:390,height:844});
  for(let index=0;index<8;index++)await submitText(`先前的问题 ${index+1}`);
  const list=page.locator('#assistant-turn-trail-list');assert(await list.evaluate(node=>node.scrollHeight>node.clientHeight),'seeded conversation makes the turn region scrollable');
  await list.evaluate(node=>node.scrollTop=120);const trailScrollBefore=await list.evaluate(node=>node.scrollTop);

  const held=gate();nextAsr={text:'识别出来的家人原话',language:'zh',tracking:'enabled',gate:held};
  await page.locator('#assistant-text').fill('发送前的手动文字');
  const postCount=turns().length;const getUserMediaBefore=await page.evaluate(()=>window.__phGetUserMediaCalls);
  await record();await Promise.race([held.arrived,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Timed out waiting for synthetic ASR route')),15000))]);
  assert.equal(await page.locator('#assistant-send').isDisabled(),true,'transcribing disables visible send');
  assert.equal(await page.locator('#assistant-mic').isDisabled(),true,'transcribing disables fresh capture');
  await page.locator('#assistant-form').evaluate(form=>form.requestSubmit());
  assert.equal(turns().length,postCount,'programmatic submit is rejected while ASR is pending');
  await page.locator('#language').click();
  assert.equal(await page.locator('#assistant-turn-trail-list .assistant-turn-trail-role').first().textContent(),'You');
  assert.equal(await list.evaluate(node=>node.scrollTop),trailScrollBefore,'language change preserves trail scroll');
  const afterLanguage=await page.evaluate(()=>({focus:document.activeElement.id,pageY:window.scrollY}));
  held.release();await held.finished;await waitReview();
  assert.equal(await page.locator('#assistant-text').inputValue(),'发送前的手动文字','typed composer text is preserved when ASR finishes');
  assert.equal(await page.locator('#assistant-transcript').inputValue(),'识别出来的家人原话');
  assert.equal(await page.locator('#assistant-transcript-language').textContent(),'Detected language: Chinese','English UI localizes the detected language label');
  await page.locator('#language').click();
  assert.equal(await page.locator('#assistant-transcript-language').textContent(),'识别语言: 中文','Chinese UI relabels the pending transcript language');
  await page.locator('#language').click();
  assert.equal(await page.locator('#assistant-transcript-language').textContent(),'Detected language: Chinese','switching back restores the English transcript language label');
  assert.equal(await page.locator('#assistant-send').isDisabled(),true,'unused transcript review blocks send');
  assert.equal(await page.evaluate(()=>window.__phGetUserMediaCalls),getUserMediaBefore+1);
  await page.locator('#assistant-form').evaluate(form=>form.requestSubmit());
  await page.locator('#assistant-mic').dispatchEvent('click');
  assert.equal(turns().length,postCount,'review blocks direct form submission');
  assert.equal(await page.evaluate(()=>window.__phGetUserMediaCalls),getUserMediaBefore+1,'review blocks a fresh capture');
  assert.equal(await page.evaluate(()=>document.activeElement.id),afterLanguage.focus,'language relabeling does not shift focus during pending ASR');
  assert.equal(await page.evaluate(()=>window.scrollY),afterLanguage.pageY,'language relabeling does not scroll the page during pending ASR');
  const englishScale=await scaleText150();await page.locator('#assistant-transcript-review').evaluate(node=>node.scrollIntoView({block:'center',inline:'nearest'}));
  let view=await layout();assert.equal(view.width,390);assert(view.pageWidth<=390,`English transcript review fits 390px: ${JSON.stringify(view)}`);assert(await textScaleValid(englishScale),'English review applies 150% text size to labels and editable fields');const englishLayout=view;
  const englishCapture=path.join(artifacts,'assistant-transcript-en-390px-text150.png');await page.screenshot({path:englishCapture,fullPage:false});fs.chmodSync(englishCapture,0o600);
  await restoreTextScale(englishScale);
  console.log('PASS typed composer survives ASR; pending transcription/review blocks submit and new capture; tracked identity stays pending until Add');

  await page.locator('#language').click();
  assert.equal(await page.locator('#assistant-turn-trail-list .assistant-turn-trail-role').first().textContent(),'你');
  assert.equal(await list.evaluate(node=>node.scrollTop),trailScrollBefore,'second language change preserves trail scroll');
  const longMixed='中A👨‍👩‍👧‍👦'.repeat(70);await page.locator('#assistant-transcript').fill(longMixed);
  const typedOverflow='typed 保留 👨‍👧';await page.locator('#assistant-text').fill(typedOverflow);
  await page.locator('#assistant-use-transcript').click();
  assert.equal(await page.locator('#assistant-text').inputValue(),typedOverflow,'overflow leaves the typed draft intact');
  assert.equal(await page.locator('#assistant-transcript').inputValue(),longMixed,'overflow leaves the editable transcript intact');
  assert.equal(await page.locator('#assistant-transcript-review').isVisible(),true,'overflow keeps review available for editing');
  assert.match(await page.locator('#assistant-status').textContent(),/超过 1,024 个 UTF-8 字节/,'Chinese overflow explains the byte limit without truncation');
  const chineseScale=await scaleText150();await page.locator('#assistant-transcript-review').evaluate(node=>node.scrollIntoView({block:'center',inline:'nearest'}));
  view=await layout();assert.equal(view.width,390);assert(view.pageWidth<=390,`Chinese transcript review fits 390px: ${JSON.stringify(view)}`);assert(await textScaleValid(chineseScale),'Chinese review applies 150% text size to labels and editable fields');const chineseLayout=view;
  const chineseCapture=path.join(artifacts,'assistant-transcript-zh-390px-text150.png');await page.screenshot({path:chineseCapture,fullPage:false});fs.chmodSync(chineseCapture,0o600);await restoreTextScale(chineseScale);
  await page.locator('#assistant-text').fill('a'.repeat(1010));await page.locator('#assistant-transcript').fill('b'.repeat(13));
  assert.equal(new TextEncoder().encode((await page.locator('#assistant-text').inputValue())+'\n'+(await page.locator('#assistant-transcript').inputValue())).length,1024);
  const trackedTranscriptId=transcriptions().at(-1).headers['x-photohouse-request-id'];
  await page.locator('#assistant-use-transcript').click();
  assert.equal(await page.locator('#assistant-text').inputValue(),'a'.repeat(1010)+'\n'+'b'.repeat(13),'Add preserves composer and inserts the transcript after one newline');
  assert.equal(await page.locator('#assistant-transcript-review').isVisible(),false);
  const acceptedText=await page.locator('#assistant-text').inputValue(),acceptedExpected=Math.min(nextTurn+1,8),acceptedResponse=page.waitForResponse(value=>value.url().endsWith('/assistant/v1/turns'));
  await page.locator('#assistant-form').evaluate(form=>form.requestSubmit());await acceptedResponse;
  await page.waitForFunction(count=>document.querySelectorAll('#assistant-turn-trail-list > li').length===count,acceptedExpected);
  const acceptedTurn=turns().at(-1);assert.equal(acceptedTurn.body&&JSON.parse(acceptedTurn.body).text,acceptedText,'wire query retains the exact 1,024-byte text');
  assert.equal(acceptedTurn.headers['x-photohouse-parent-request-id'],trackedTranscriptId,'explicit Add links the successful tracked transcription as parent');
  console.log('PASS overflow preserves mixed Chinese/emoji text; exact 1,024 UTF-8 byte Add sends tracked ASR parent');

  nextAsr={text:'discarded tracked words',language:'en',tracking:'enabled'};await record();await waitReview();
  const discardedTranscriptId=transcriptions().at(-1).headers['x-photohouse-request-id'];
  await page.locator('#assistant-discard-transcript').click();assert.equal(await page.locator('#assistant-text').inputValue(),'','discard does not insert speech');
  await submitText('manual after discard');const unlinked=turns().at(-1);
  assert.equal(unlinked.headers['x-photohouse-parent-request-id'],undefined,'discarded tracked ASR is not linked to later manual send');
  console.log('PASS discard clears pending ASR identity and later manual send has no parent');

  nextAsr={text:'must stay hidden',language:'en',malformed:true};await record();
  await page.waitForFunction(()=>document.getElementById('assistant-status').textContent.includes('语音识别失败'));
  assert.equal(await page.locator('#assistant-transcript-review').isVisible(),false,'malformed ASR response never enters review');
  assert.equal(turns().at(-1).headers['x-photohouse-parent-request-id'],undefined,'malformed response cannot provide a parent');
  nextAsr={text:'untracked transcript',language:'en',tracking:'disabled'};await record();await waitReview();
  await page.locator('#assistant-use-transcript').click();const untrackedExpected=Math.min(await page.locator('#assistant-turn-trail-list > li').count()+1,8),untrackedResponse=page.waitForResponse(value=>value.url().endsWith('/assistant/v1/turns'));
  await page.locator('#assistant-form').evaluate(form=>form.requestSubmit());await untrackedResponse;await page.waitForFunction(count=>document.querySelectorAll('#assistant-turn-trail-list > li').length===count,untrackedExpected);
  const untrackedTurn=turns().at(-1);assert.equal(untrackedTurn.headers['x-photohouse-parent-request-id'],undefined,'disabled ASR tracking cannot be sent as parent');
  console.log('PASS malformed and tracking-disabled ASR never create a tracked turn parent');

  await page.locator('#assistant-clear').click();
  const malformedCount=transcriptions().length,malformedDraft='typed text survives malformed generated audio';
  await page.locator('#assistant-text').fill(malformedDraft);await page.evaluate(()=>{window.__phMalformedWav=true;});await record();
  await page.waitForFunction(()=>document.getElementById('assistant-status').textContent.includes('语音识别失败'));
  assert.equal(transcriptions().length,malformedCount,'generated WAV with a damaged sample-rate header is rejected before POST');
  assert.equal(await page.locator('#assistant-text').inputValue(),malformedDraft,'malformed generated WAV rejection preserves typed draft');
  assert.equal(await page.locator('#assistant-transcript-review').isVisible(),false,'malformed generated WAV never enters transcript review');
  console.log('PASS malformed generated WAV is rejected before POST and preserves typed draft');

  await page.locator('#assistant-clear').click();
  nextAsr={text:'old account late result',language:'en',tracking:'enabled',gate:gate()};const staleGate=nextAsr.gate;
  await record();await staleGate.arrived;await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  await signIn('+12025550101');await openAssistant();
  const currentGate=gate();nextAsr={text:'current account transcription',language:'en',tracking:'enabled',gate:currentGate};
  await record();await currentGate.arrived;await page.locator('#assistant-text').fill('typed during current ASR');
  assert.equal(await page.locator('#assistant-send').isDisabled(),true,'current scope ASR blocks its send control');
  staleGate.release();await staleGate.finished;await page.waitForTimeout(50);
  assert.equal(await page.locator('#assistant-transcript-review').isVisible(),false,'late old ASR cannot enter the new account review');
  assert.equal(await page.locator('#assistant-text').inputValue(),'typed during current ASR','old attempt cleanup preserves current composer text');
  assert.equal(await page.locator('#assistant-send').isDisabled(),true,'old attempt cleanup cannot enable send during current transcription');
  currentGate.release();await currentGate.finished;await waitReview();
  assert.equal(await page.locator('#assistant-transcript').inputValue(),'current account transcription','current scope ASR completes after stale cleanup');
  assert.equal(await page.locator('#assistant-text').inputValue(),'typed during current ASR');
  await page.locator('#assistant-discard-transcript').click();await submitText('new account manual query');
  assert.equal(turns().at(-1).headers['x-photohouse-parent-request-id'],undefined,'scope change and discard clear accepted ASR parent identity');
  assert.deepEqual(externalOrigins,[],'synthetic browser did not request external origins');console.log('EXTERNAL_ORIGINS []');
  assert.deepEqual(pageErrors,[],'synthetic transcript flow has no browser errors');
  console.log('PASS old-account delayed ASR is fenced after scope change');
  console.log('EN_LAYOUT '+JSON.stringify(englishLayout));console.log('ZH_LAYOUT '+JSON.stringify(chineseLayout));
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{
  for(const value of activeGates){value.release();}
  if(browser)await browser.close();try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');}catch{}bridge.kill();
});
