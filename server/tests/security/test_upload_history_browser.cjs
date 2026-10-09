/* Chromium -> real protected ASGI -> synthetic migrated DB, with no listener. */
'use strict';
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'upload-history-browser-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'upload_history_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let next=0,readyResolve;const ready=new Promise(r=>readyResolve=r),pending=new Map();
bridge.stderr.on('data',v=>process.stderr.write(v));
createInterface({input:bridge.stdout}).on('line',line=>{const m=JSON.parse(line);if(m.ready)readyResolve(m);else{pending.get(m.id)?.(m);pending.delete(m.id);}});
function rpc(m){return new Promise(resolve=>{const id=++next;pending.set(id,resolve);bridge.stdin.write(JSON.stringify({...m,id})+'\n');});}
let historyUnavailable=false,holdHistory=false,releaseHistory,historyHeld,holdNoteTextSave=false,releaseNoteTextSave,noteTextSaveHeld,nextNoteTextFailure=false,holdNoteAudioSave=false,releaseNoteAudioSave,noteAudioSaveHeld,nextNoteAudioFailure=false,malformedNoteLimit=false;const errors=[],outside=[],requests=[],noteTextMutations=[],noteAudioMutations=[];
let browser;
(async()=>{
  const seed=await ready;
  browser=await chromium.launch({headless:true,args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  const context=await browser.newContext({viewport:{width:1200,height:900},serviceWorkers:'block'});
  await context.addInitScript(()=>{window.__noteMedia=[];window.__noteContexts=[];window.__noteHoldResume=false;const media=navigator.mediaDevices||{};try{Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:media});}catch{}Object.defineProperty(media,'getUserMedia',{configurable:true,value:()=>new Promise(resolve=>{const track={stopped:false,stopCount:0,stop(){this.stopped=true;this.stopCount++;}};const stream={getTracks:()=>[track]};window.__noteMedia.push({resolve,track,stream});})});Object.defineProperty(window,'AudioContext',{configurable:true,value:class{constructor(){this.sampleRate=16000;this.destination={};this.processor=null;this.resumeResolve=null;this.closed=false;window.__noteContexts.push(this);}createMediaStreamSource(){return {connect(){},disconnect(){}};}createScriptProcessor(){return this.processor={onaudioprocess:null,connect(){},disconnect(){}};}resume(){if(window.__noteHoldResume)return new Promise(resolve=>this.resumeResolve=resolve);return Promise.resolve();}close(){this.closed=true;return Promise.resolve();}}});window.__noteResolveMedia=index=>window.__noteMedia[index]?.resolve(window.__noteMedia[index].stream);window.__noteEmitFrames=(index,count)=>{const processor=window.__noteContexts[index]?.processor;for(let i=0;i<count;i++)processor?.onaudioprocess?.({inputBuffer:{getChannelData:()=>new Float32Array(4096)}});};window.__noteReleaseResume=index=>window.__noteContexts[index]?.resumeResolve?.();});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){outside.push(url.origin);return route.abort();}
    const headers=await request.allHeaders();delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    if(request.method()==='POST'&&url.pathname==='/upload-annotations/text'){
      const body=request.postDataJSON();noteTextMutations.push(body.mutation_id);
      if(nextNoteTextFailure){nextNoteTextFailure=false;requests.push([request.method(),url.pathname,503]);return route.fulfill({status:503,contentType:'application/json',body:'{}'});}
    }
    if(request.method()==='POST'&&url.pathname==='/upload-annotations/audio'){
      noteAudioMutations.push(headers['x-annotation-mutation-id']);
      if(nextNoteAudioFailure){nextNoteAudioFailure=false;requests.push([request.method(),url.pathname,503]);return route.fulfill({status:503,contentType:'application/json',body:'{}'});}
    }
    const result=await rpc({method:request.method(),path:url.pathname+url.search,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    requests.push([request.method(),url.pathname,result.status]);
    if(request.method()==='POST'&&url.pathname==='/upload-annotations/text'&&holdNoteTextSave){holdNoteTextSave=false;await new Promise(resolve=>{releaseNoteTextSave=resolve;noteTextSaveHeld?.();});}
    if(request.method()==='POST'&&url.pathname==='/upload-annotations/audio'&&holdNoteAudioSave){holdNoteAudioSave=false;await new Promise(resolve=>{releaseNoteAudioSave=resolve;noteAudioSaveHeld?.();});}
    if(url.pathname==='/uploads'&&request.method()==='GET'){
      if(historyUnavailable)return route.fulfill({status:503,contentType:'application/json',body:'{}'});
      if(holdHistory){holdHistory=false;await new Promise(resolve=>{releaseHistory=resolve;historyHeld?.();});}
    }
    const outputHeaders={...result.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];let outputBody=Buffer.from(result.body,'base64');
    if(malformedNoteLimit&&request.method()==='GET'&&url.pathname==='/ui/app.js'){
      const source=outputBody.toString(),valid='},60,{isCurrent:current,signal:owner.controller.signal})';
      assert(source.includes(valid),'the synthetic malformed-call fixture finds the production owner call');
      outputBody=Buffer.from(source.replace(valid,'},{isCurrent:current,signal:owner.controller.signal})'));
    }
    await route.fulfill({status:result.status,headers:outputHeaders,body:outputBody});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('https://photohouse.test/ui');
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#my-uploads-open').waitFor();
  if(await page.locator('#my-uploads-open').textContent()==='我的上传'){await page.locator('#language').click();await page.waitForFunction(()=>document.querySelector('#my-uploads-open').textContent==='My uploads');}
  await page.waitForFunction(()=>document.querySelectorAll('#grid .asset').length>0&&document.querySelector('#status').textContent==='');
  assert.equal(await page.locator('#uploads-open').isVisible(),false);
  await page.locator('#my-uploads-open').click();
  await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10).catch(async error=>{console.error(requests,errors,await page.locator('#my-uploads-status').textContent(),await page.locator('#my-uploads-panel').evaluate(e=>e.open));throw error;});
  assert.match(await page.locator('.receipt-card').first().textContent(),/awaiting owner review/);
  assert.equal(await page.locator('.receipt-card').getByRole('button',{name:'Open',exact:true}).count(),0);
  await page.locator('#my-uploads-next').click();
  await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===2);
  await page.locator('#my-uploads-previous').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  assert.equal(requests.filter(r=>r[1]==='/upload-annotations').length,0);
  await rpc({command:'approve'});await page.locator('#my-uploads-refresh').click();
  await page.locator('.receipt-card').getByRole('button',{name:'Open',exact:true}).waitFor();
  malformedNoteLimit=true;const guardPage=await context.newPage();guardPage.on('pageerror',e=>errors.push(e.message));await guardPage.goto('https://photohouse.test/ui');await guardPage.locator('#my-uploads-open').waitFor();await guardPage.locator('#my-uploads-open').click();await guardPage.locator(`.receipt-card[data-asset="${seed.asset_id}"]`).waitFor();await guardPage.locator(`.receipt-card[data-asset="${seed.asset_id}"]`).locator('.annotation-open').click();await guardPage.locator('.annotation-dialog .annotation-composer').waitFor();await guardPage.locator('.annotation-composer button').nth(1).click();await guardPage.waitForFunction(()=>document.querySelector('.annotation-dialog[open] .annotation-status')?.textContent.length>0);assert.equal(await guardPage.evaluate(()=>window.__noteMedia.length),0,'malformed capture duration is rejected before a microphone prompt');assert.equal(await guardPage.evaluate(()=>window.__noteContexts.length),0,'malformed capture duration is rejected before AudioContext construction');await guardPage.close();malformedNoteLimit=false;console.log('PASS malformed note capture limit is rejected before permission or audio context setup');
  const selectedCard=page.locator(`.receipt-card[data-asset="${seed.asset_id}"]`);
  await selectedCard.locator('.annotation-open').click();
  await selectedCard.locator('.annotation-dialog .annotation-composer').waitFor();
  assert.equal(await selectedCard.getByLabel('Where should this note appear?').inputValue(),'');
  assert.match(await selectedCard.locator('.annotation-original-help').textContent(),/original text or recording stays visible/);
  await selectedCard.getByLabel('Write a note').fill('The family walked by the lake.');
  await selectedCard.getByRole('button',{name:'Save note'}).click();
  await selectedCard.getByText('The family walked by the lake.').waitFor();
  assert.equal(await selectedCard.getByLabel('Write a note').inputValue(),'','a successful text-note receipt clears the draft it saved');
  await selectedCard.getByLabel('Where should this note appear?').selectOption(String(seed.asset_id));
  await selectedCard.getByLabel('Write a note').fill('Only this photo shows the blue kite.');
  await selectedCard.getByRole('button',{name:'Save note'}).click();
  await selectedCard.getByText('Only this photo shows the blue kite.').waitFor();
  await selectedCard.locator('.annotation-dialog').screenshot({path:path.join(artifacts,'family-note-dialog-desktop.png')});
  await selectedCard.locator('.annotation-dialog-heading button').click();
  await page.locator('#my-uploads-refresh').click();
  await page.locator(`.receipt-card[data-asset="${seed.asset_id}"]`).locator('.annotation-open').click();
  await page.locator(`.receipt-card[data-asset="${seed.asset_id}"]`).getByText('The family walked by the lake.').waitFor();
  await page.locator(`.receipt-card[data-asset="${seed.asset_id}"]`).getByText('Only this photo shows the blue kite.').waitFor();
  const noteCard=page.locator(`.receipt-card[data-asset="${seed.asset_id}"]`),noteText=noteCard.getByLabel('Write a note'),noteFile=noteCard.getByLabel('Add a WAV recording (up to 2 MiB)');
  await noteFile.setInputFiles({name:'synthetic.wav',mimeType:'audio/wav',buffer:Buffer.alloc(46)});assert.equal(await noteCard.getByRole('button',{name:'Save recording'}).isDisabled(),false,'a selected synthetic audio file enables audio save before the busy check');
  await noteText.fill('Submitted original; keep later words.');holdNoteTextSave=true;const heldTextSave=new Promise(resolve=>noteTextSaveHeld=resolve);await noteCard.getByRole('button',{name:'Save note'}).click();await heldTextSave;
  for(const control of [noteCard.getByLabel('Where should this note appear?'),noteCard.getByLabel('Language'),noteCard.getByLabel('I agree to local processing for a transcript and suggestions'),noteText,noteCard.getByLabel('Add a WAV recording (up to 2 MiB)'),noteCard.getByRole('button',{name:'Save note'}),noteCard.getByRole('button',{name:'Save recording'}),noteCard.getByRole('button',{name:'Record with microphone'})])assert.equal(await control.isDisabled(),true,'a pending text save freezes note and capture controls');
  await noteCard.getByRole('button',{name:'Record with microphone'}).evaluate(button=>button.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})));
  assert.equal(await page.evaluate(()=>window.__noteMedia.length),0,'programmatic capture during a note save does not prompt for a microphone');
  await noteText.evaluate(field=>{field.value='Newer words typed after submit';field.dispatchEvent(new Event('input',{bubbles:true}));});releaseNoteTextSave();
  await noteCard.getByText('Submitted original; keep later words.').waitFor();assert.equal(await noteText.inputValue(),'Newer words typed after submit','a success receipt clears only the exact draft sent');assert.equal(await noteText.isDisabled(),false,'successful save releases the reviewed composer');
  await noteText.fill('Retry the same note.');nextNoteTextFailure=true;await noteCard.getByRole('button',{name:'Save note'}).click();await noteCard.getByText('Save could not be confirmed. Your note is kept; retry to confirm the same save.').waitFor();assert.equal(await noteText.inputValue(),'Retry the same note.','failed save retains its original text');assert.equal(await noteText.isDisabled(),false,'failed save makes the composer editable');const failedMutation=noteTextMutations.at(-1);await noteCard.getByRole('button',{name:'Save note'}).click();await noteCard.getByText('Retry the same note.').waitFor();assert.equal(noteTextMutations.at(-1),failedMutation,'retry reuses the same mutation ID');assert.equal(await noteText.inputValue(),'','confirmed retry clears the same reviewed draft');
  console.log('PASS note save freezes edits/capture; success preserves newer words and failed retry preserves and reuses its mutation');
  const syntheticWav=Buffer.alloc(44+8000*2);syntheticWav.write('RIFF',0);syntheticWav.writeUInt32LE(syntheticWav.length-8,4);syntheticWav.write('WAVEfmt ',8);syntheticWav.writeUInt32LE(16,16);syntheticWav.writeUInt16LE(1,20);syntheticWav.writeUInt16LE(1,22);syntheticWav.writeUInt32LE(16000,24);syntheticWav.writeUInt32LE(32000,28);syntheticWav.writeUInt16LE(2,32);syntheticWav.writeUInt16LE(16,34);syntheticWav.write('data',36);syntheticWav.writeUInt32LE(syntheticWav.length-44,40);syntheticWav.writeInt16LE(120,44);
  await noteCard.getByLabel('I agree to local processing for a transcript and suggestions').check();await noteFile.setInputFiles({name:'synthetic.wav',mimeType:'audio/wav',buffer:syntheticWav});holdNoteAudioSave=true;const heldAudioSave=new Promise(resolve=>noteAudioSaveHeld=resolve);await noteCard.getByRole('button',{name:'Save recording'}).click();await heldAudioSave;
  for(const control of [noteCard.getByLabel('Where should this note appear?'),noteCard.getByLabel('Language'),noteCard.getByLabel('I agree to local processing for a transcript and suggestions'),noteText,noteFile,noteCard.getByRole('button',{name:'Save note'}),noteCard.getByRole('button',{name:'Record with microphone'}),noteCard.getByRole('button',{name:'Save recording'})])assert.equal(await control.isDisabled(),true,'a pending audio save freezes note and capture controls');
  await noteFile.evaluate((input,bytes)=>{const transfer=new DataTransfer();transfer.items.add(new File([new Uint8Array(bytes)],'newer.wav',{type:'audio/wav'}));input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));},Array.from(syntheticWav));releaseNoteAudioSave();await noteCard.getByText('Recording saved.').waitFor();assert.equal(await noteFile.evaluate(input=>input.files[0]?.name),'newer.wav','an audio receipt clears only the exact recording it saved');assert.equal(await noteCard.getByRole('button',{name:'Save recording'}).isDisabled(),false,'successful audio receipt releases the composer with the newer recording intact');
  nextNoteAudioFailure=true;await noteCard.getByRole('button',{name:'Save recording'}).click();await noteCard.getByText('Recording could not be saved. Please check it and retry.').waitFor();assert.equal(await noteFile.evaluate(input=>input.files[0]?.name),'newer.wav','failed audio save preserves its selected original');assert.equal(await noteCard.getByRole('button',{name:'Save recording'}).isDisabled(),false,'failed audio save enables retry');const failedAudioMutation=noteAudioMutations.at(-1);await noteCard.getByRole('button',{name:'Save recording'}).click();await noteCard.getByText('Recording saved.').waitFor();assert.equal(noteAudioMutations.at(-1),failedAudioMutation,'audio retry reuses its mutation ID');assert.equal(await noteFile.evaluate(input=>input.files.length),0,'confirmed audio retry clears the exact recording');
  console.log('PASS audio save freezes fields, preserves a newer selected file, and failed retry reuses its mutation ID');
  await noteText.fill('Detached composer cannot save.');holdNoteTextSave=true;const detachedSaveHeld=new Promise(resolve=>noteTextSaveHeld=resolve);await noteCard.getByRole('button',{name:'Save note'}).click();await detachedSaveHeld;const oldSave=await noteCard.getByRole('button',{name:'Save note'}).elementHandle(),oldRecord=await noteCard.getByRole('button',{name:'Record with microphone'}).elementHandle(),requestsBeforeDetached=noteTextMutations.length;
  await noteCard.locator('.annotation-dialog-heading button').click();await noteCard.locator('.annotation-open').click();await noteCard.locator('.annotation-dialog .annotation-composer').waitFor();await oldSave.evaluate(button=>button.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})));await oldRecord.evaluate(button=>button.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})));
  assert.equal(noteTextMutations.length,requestsBeforeDetached,'a detached composer cannot start a second note save after the same dialog reopens');assert.equal(await page.evaluate(()=>window.__noteMedia.length),0,'a detached composer cannot start microphone capture after reopen');releaseNoteTextSave();console.log('PASS reopened note dialog rejects detached save and capture callbacks');
  await noteFile.setInputFiles([]);
  const noteContextsBeforePermission=await page.evaluate(()=>window.__noteContexts.length);
  const audioUploadsBeforePermission=requests.filter(r=>r[0]==='POST'&&r[1]==='/upload-annotations/audio').length;
  const pendingComposer=await noteCard.locator('.annotation-dialog .annotation-composer').elementHandle();
  await pendingComposer.evaluate(box=>{const cleanup=box._annotationCloseCleanup;box._annotationCloseCleanup=()=>{box.dataset.testCaptureDisposed='yes';cleanup();};});
  await noteCard.getByRole('button',{name:'Record with microphone'}).click();await page.waitForFunction(()=>window.__noteMedia.length===1);
  await noteCard.locator('.annotation-dialog-heading button').click();assert.equal(await pendingComposer.evaluate(box=>box.dataset.testCaptureDisposed),'yes','closing the note dialog disposes its current composer');assert.equal(await noteCard.locator('.annotation-dialog').evaluate(dialog=>dialog.open),false,'the synthetic note dialog is closed before delayed permission resolves');
  assert.equal(await page.evaluate(()=>window.__noteContexts.length),noteContextsBeforePermission,'closing a note dialog while permission is pending creates no context before the delayed stream is released');await page.evaluate(()=>window.__noteResolveMedia(0));await page.waitForFunction(()=>window.__noteMedia[0].track.stopped);
  assert.equal(await page.evaluate(previous=>window.__noteContexts.slice(previous).every(context=>context.closed),noteContextsBeforePermission),true,'a late resolved permission cannot leave an AudioContext open');
  assert.equal(await page.evaluate(()=>window.__noteMedia[0].track.stopCount),1,'closing a note dialog stops late microphone permission exactly once');
  assert.equal(requests.filter(r=>r[0]==='POST'&&r[1]==='/upload-annotations/audio').length,audioUploadsBeforePermission,'closing note capture before permission resolves cannot upload audio');
  console.log('PASS closing family-note dialog aborts pending microphone setup and discards its late stream');
  await noteCard.locator('.annotation-open').click();await noteCard.locator('.annotation-dialog .annotation-composer').waitFor();const durationContext=await page.evaluate(()=>window.__noteContexts.length);await page.evaluate(()=>{window.__noteHoldResume=true;});await noteCard.getByRole('button',{name:'Record with microphone'}).click();await page.waitForFunction(()=>window.__noteMedia.length===2);await page.evaluate(()=>window.__noteResolveMedia(1));await page.waitForFunction(count=>window.__noteContexts.length===count+1,durationContext);await page.waitForFunction(index=>typeof window.__noteContexts[index].resumeResolve==='function',durationContext);await page.evaluate(index=>window.__noteEmitFrames(index,235),durationContext);await noteCard.locator('.annotation-status').getByText('Recording ready. Save it to this batch or item.').waitFor();
  assert.equal(await noteCard.getByRole('button',{name:'Record with microphone'}).isDisabled(),false,'a duration-complete note is no longer stuck in startup while resume is pending');assert.equal(await noteCard.getByRole('button',{name:'Stop recording'}).isVisible(),false,'a duration-complete handle is not adopted after its callback already ran');await page.evaluate(index=>window.__noteReleaseResume(index),durationContext);await page.waitForTimeout(20);assert.equal(await noteCard.getByRole('button',{name:'Stop recording'}).isVisible(),false,'late setup return cannot reinstall a stopped capture');
  console.log('PASS maximum-duration callback before resume settles clears startup without adopting the stopped handle');await noteCard.locator('.annotation-dialog-heading button').click();
  const otherCard=page.locator(`.receipt-card[data-asset="${seed.other_asset_id}"]`);
  await otherCard.locator('.annotation-open').click();
  await otherCard.getByText('The family walked by the lake.').waitFor();
  assert.equal(await otherCard.getByText('Only this photo shows the blue kite.').count(),0);
  await otherCard.locator('.annotation-dialog-heading button').click();
  await page.locator('#my-uploads-panel').screenshot({path:path.join(artifacts,'my-uploads-desktop.png')});
  await page.locator('.receipt-card').getByRole('button',{name:'Open',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#viewer-media .viewer-surface img')?.naturalWidth>0).catch(async error=>{console.error(requests.slice(-20),errors,await page.locator('#status').textContent(),await page.locator('#viewer').evaluate(e=>e.open),await page.locator('#view-quality').textContent());throw error;});
  assert.match(await page.locator('#viewer-title').textContent(),new RegExp(String(seed.asset_id)));
  await page.locator('#close-viewer').click();
  await page.setViewportSize({width:390,height:844});await page.locator('#language').click();
  await page.waitForFunction(()=>document.querySelector('#my-uploads-open').textContent==='我的上传');
  await page.locator('#my-uploads-open').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  assert.match(await page.locator('.receipt-card').first().textContent(),/已加入相册库/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  await page.locator(`.receipt-card[data-asset="${seed.asset_id}"]`).locator('.annotation-open').click();
  await page.locator(`.receipt-card[data-asset="${seed.asset_id}"]`).locator('.annotation-dialog .annotation-composer').waitFor();
  assert.equal(await page.locator('.annotation-dialog[open]').evaluate(element=>element.scrollWidth<=element.clientWidth),true);
  await page.locator('.annotation-dialog[open]').screenshot({path:path.join(artifacts,'family-note-dialog-phone-zh.png')});
  await page.locator('.annotation-dialog[open] .annotation-dialog-heading button').click();
  await page.locator('#my-uploads-panel').screenshot({path:path.join(artifacts,'my-uploads-phone-zh.png')});
  await page.locator('#my-uploads-panel > summary').click();
  await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===0);
  await page.locator('#my-uploads-open').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  historyUnavailable=true;await page.locator('#my-uploads-refresh').click();
  await page.waitForFunction(()=>document.querySelector('#my-uploads-status').textContent.includes('暂时无法'));
  assert.equal(await page.locator('.receipt-card').count(),0);
  assert.equal(await page.locator('#library').isVisible(),true);
  historyUnavailable=false;await page.locator('#my-uploads-refresh').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  holdHistory=true;const held=new Promise(resolve=>historyHeld=resolve);
  await page.locator('#my-uploads-refresh').click();await held;
  await page.locator('#my-uploads-panel > summary').click();releaseHistory();
  await page.waitForFunction(()=>!document.querySelector('#my-uploads-panel').open&&document.querySelectorAll('.receipt-card').length===0);
  await page.locator('#my-uploads-open').click();await page.waitForFunction(()=>document.querySelectorAll('.receipt-card').length===10);
  await rpc({command:'revoke'});await page.locator('#my-uploads-refresh').click();
  await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await page.locator('.receipt-card').count(),0);
  assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
  console.log(JSON.stringify({passed:['member history distinct from owner review','10 plus 2 pagination','pending has no open','notes load only when dialog opens','real promotion reflected after refresh','folder and item notes saved and scoped through signed-in browser','approved opens authorized viewer','Chinese narrow dialog without overflow','closing clears receipts','503 clears rows while gallery remains usable','late closed-panel response discarded','revocation clears private history'],artifacts}));
  await context.close();
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.stdin.end();});
