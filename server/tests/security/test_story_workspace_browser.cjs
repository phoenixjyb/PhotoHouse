'use strict';
/* Actual browser -> closed ASGI -> migrated synthetic SQLite; no HTTP listener. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-story-web-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pending=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const request=pending.get(result.id);if(request){pending.delete(result.id);request.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error('Bridge failed'));for(const item of pending.values())item.reject(new Error('Bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
let browser,ctx,hold=null,releaseHold,arrivedHold,titleHold=null,releaseTitleHold,arrivedTitleHold,titleSelectionBody=null,sourceCapabilityDelay=false,sourceCapabilityGate=null,releaseSourceCapability,sourceCapabilityArrival=null,resolveSourceCapabilityArrival,sourceCapabilityRequestsHeld=0,sourceCapabilityUnavailableStatus=403,sourceCapabilityUnavailableGate=null,releaseSourceCapabilityUnavailable,sourceCapabilityUnavailableArrival=null,resolveSourceCapabilityUnavailableArrival,sourceAccessCheckGate=null,releaseSourceAccessCheck,sourceAccessCheckArrival=null,resolveSourceAccessCheckArrival,revokeOnNextSessionCheck=false,shelfHold=null,releaseShelfHold,arrivedShelfHold,corruptShelfTheme=false,constrainPreviewEvidence=true,previewEvidence=null,sourceCapabilitiesAvailable=false,duplicateAiPreview=false,sourceSaveRetryTest=false,sourceSaveAttempts=0,sourceSaveBodies=[],sourceSavedFixture=null,lastPreviewPayload=null,dictationCapabilityStatus=200,dictationCapabilityPayload=null,dictationCapabilityGate=null,releaseDictationCapability,dictationCapabilityArrival=null,resolveDictationCapabilityArrival,dictationTranscribeStatus=200,dictationTranscribeGate=null,releaseDictationTranscribe,dictationTranscribeArrival=null,resolveDictationTranscribeArrival,dictationTranscriptions=0,dictationTranscript='Synthetic reviewed transcript',dictationSaveRetryTest=false,dictationSaveAttempts=0,dictationSavedFixture=null;const errors=[],external=[],checks=[],requests=[],authExchanges=[];
const pass=name=>{checks.push(name);console.log('PASS '+name);};
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  ctx=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block',acceptDownloads:true});
  await ctx.addInitScript(()=>{const utterances=[];class MockUtterance{constructor(text){this.text=text;}}const voices=[{name:'Synthetic local Chinese',lang:'zh-CN',localService:true},{name:'Synthetic local English',lang:'en-US',localService:true},{name:'Synthetic remote Chinese',lang:'zh-CN',localService:false}];const synth={speaking:false,pending:false,paused:false,cancelCount:0,resumeCount:0,getVoices:()=>voices,speak(value){utterances.push(value);this.speaking=true;},pause(){this.paused=true;},resume(){this.resumeCount++;this.paused=false;},cancel(){this.cancelCount++;this.speaking=false;this.pending=false;}};Object.defineProperty(window,'speechSynthesis',{configurable:true,value:synth});window.SpeechSynthesisUtterance=MockUtterance;window.__mockSpeech={utterances,synth};window.__dictationMetrics={permissionRequests:0,trackStops:0,contextCloses:0,autoStopEvents:0};Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{window.__dictationMetrics.permissionRequests++;if(window.__dictationPermissionGate)await window.__dictationPermissionGate;const track={stop(){window.__dictationMetrics.trackStops++;}};return {getTracks:()=>[track]};}}});class MockAudioContext{constructor(){this.sampleRate=16000;this.destination={};window.__dictationMetrics.contextCloses=window.__dictationMetrics.contextCloses;}createMediaStreamSource(){return {connect(){},disconnect(){}};}createScriptProcessor(){const processor={onaudioprocess:null,connect(){},disconnect(){}};this.processor=processor;return processor;}resume(){if(window.__dictationAutoStopBeforeResume){this.processor?.onaudioprocess?.({inputBuffer:{getChannelData:()=>new Float32Array(window.__dictationAutoStopSamples||480000).fill(.03)}});window.__dictationMetrics.autoStopEvents++;return window.__dictationResumeGate||Promise.resolve();}if(!window.__dictationNoSamples)setTimeout(()=>this.processor?.onaudioprocess?.({inputBuffer:{getChannelData:()=>new Float32Array(4096).fill(.03)}}),0);return Promise.resolve();}close(){window.__dictationMetrics.contextCloses++;return Promise.resolve();}}window.AudioContext=MockAudioContext;let Constructor;Object.defineProperty(window,'PhotoHouseStoryWorkspace',{configurable:true,get:()=>Constructor,set:value=>{Constructor=config=>{let forcedLanguage=null;const originalScope=config.scope;const instance=value({...config,scope:()=>({...originalScope(),...(forcedLanguage?{language:forcedLanguage}:{})})});window.__setStoryWorkspaceTestLanguage=language=>{forcedLanguage=language;instance.translate();};window.__storyWorkspaceTest=instance;return instance;};}});});
  await ctx.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    requests.push({method:req.method(),path:url.pathname+url.search,...(url.pathname==='/story-workspace/preview'?{body:req.postData()}:{} )});
    if(req.method()==='GET'&&url.pathname==='/assistant/v1/capabilities'){
      if(dictationCapabilityGate){const gate=dictationCapabilityGate;dictationCapabilityGate=null;resolveDictationCapabilityArrival();await gate;}
      if(dictationCapabilityStatus!==200){try{await route.fulfill({status:dictationCapabilityStatus,contentType:'application/json',body:'{"detail":"synthetic voice denial"}'});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}return;}
      try{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dictationCapabilityPayload||{version:1,transcribe:true,max_audio_seconds:30})});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}return;
    }
    if(req.method()==='POST'&&url.pathname==='/assistant/v1/transcribe'){
      dictationTranscriptions++;if(dictationTranscribeGate){const gate=dictationTranscribeGate;dictationTranscribeGate=null;resolveDictationTranscribeArrival();await gate;}
      if(dictationTranscribeStatus!==200){try{await route.fulfill({status:dictationTranscribeStatus,contentType:'application/json',body:'{"detail":"synthetic voice denial"}'});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}return;}
      try{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,language:'en',text:dictationTranscript})});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}return;
    }
    if(req.method()==='GET'&&url.pathname==='/story-workspace/source-capabilities'&&!sourceCapabilitiesAvailable){if(sourceCapabilityUnavailableGate){resolveSourceCapabilityUnavailableArrival();await sourceCapabilityUnavailableGate;}await route.fulfill({status:sourceCapabilityUnavailableStatus,contentType:'application/json',body:'{"detail":"not found"}'});return;}
    if(req.method()==='GET'&&url.pathname==='/story-workspace/source-capabilities'&&sourceCapabilityDelay){sourceCapabilityRequestsHeld++;if(sourceCapabilityRequestsHeld===2)resolveSourceCapabilityArrival();await sourceCapabilityGate;await route.fulfill({status:200,contentType:'application/json',body:'{"version":1,"source_policy":"chapter_sources_v1","max_sources_per_chapter":12,"needs_review":true}'});return;}
    if(req.method()==='GET'&&url.pathname==='/story-workspace/source-capabilities'&&sourceCapabilitiesAvailable){await route.fulfill({status:200,contentType:'application/json',body:'{"version":1,"source_policy":"chapter_sources_v1","max_sources_per_chapter":12,"needs_review":true}'});return;}
    if(req.method()==='GET'&&url.pathname==='/auth/session'&&sourceAccessCheckGate){const gate=sourceAccessCheckGate;sourceAccessCheckGate=null;resolveSourceAccessCheckArrival();await gate;}
    if(req.method()==='GET'&&url.pathname==='/auth/session'&&revokeOnNextSessionCheck){revokeOnNextSessionCheck=false;await rpc({command:'mutate',scenario:'revoke-member'});}
    if(req.method()==='GET'&&url.pathname==='/story-workspace/title-capabilities'){await route.fulfill({status:200,contentType:'application/json',body:'{"version":1,"enabled":true,"max_suggestions":3,"needs_review":true}'});return;}
    if(req.method()==='GET'&&url.pathname==='/memory-stories'){
      const theme=url.searchParams.get('theme'),page=Number(url.searchParams.get('page')||1),all=Array.from({length:10},(_,i)=>({id:`00000000-0000-4000-8000-${String(i+1).padStart(12,'0')}`,title:`合成保存故事 ${i+1}`,theme:i===9?'birthday':'trip',cover_asset_id:i%2?'102':'101',item_count:2,chapter_count:1}));
      let rows=theme==='grandparents'?[]:theme?all.filter(item=>item.theme===theme):all;const selected=rows.slice((page-1)*8,page*8),payload={library_id:'family-a',page,page_size:8,has_more:page*8<rows.length,can_create:true,items:selected};
      if(shelfHold&&theme==='trip'&&page===1){const gate=shelfHold;shelfHold=null;arrivedShelfHold();await gate;}
      if(corruptShelfTheme&&theme){corruptShelfTheme=false;if(payload.items.length)payload.items[0].theme='birthday';}
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload)});return;
    }
    if(sourceSaveRetryTest&&req.method()==='POST'&&url.pathname==='/memory-stories'&&url.searchParams.get('source_review')==='1'){
      sourceSaveAttempts++;sourceSaveBodies.push(req.postData());
      if(sourceSaveAttempts===1){await route.fulfill({status:503,contentType:'application/json',body:'{"detail":"synthetic uncertain save"}'});return;}
      const body=JSON.parse(req.postData()),chapters=JSON.parse(body.chapters);
      sourceSavedFixture={...lastPreviewPayload,saved:true,generator:'family_edited_outline',id:'00000000-0000-4000-8000-000000000099',revision:'1',can_edit:true,source_policy:'chapter_sources_v1',title:body.title,theme:body.theme,language:body.language,chapters};
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(sourceSavedFixture)});return;
    }
    if(dictationSaveRetryTest&&req.method()==='POST'&&url.pathname==='/memory-stories'&&!url.searchParams.has('source_review')){
      dictationSaveAttempts++;if(dictationSaveAttempts===1){await route.fulfill({status:503,contentType:'application/json',body:'{"detail":"synthetic uncertain save"}'});return;}
      const body=JSON.parse(req.postData());dictationSavedFixture={...lastPreviewPayload,saved:true,generator:'family_edited_outline',id:'00000000-0000-4000-8000-000000000098',revision:'1',can_edit:true,title:body.title,theme:body.theme,language:body.language,chapters:JSON.parse(body.chapters)};
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dictationSavedFixture)});return;
    }
    if(sourceSaveRetryTest&&req.method()==='GET'&&url.pathname==='/memory-stories/00000000-0000-4000-8000-000000000099'&&url.searchParams.get('source_review')==='1'&&sourceSavedFixture){await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(sourceSavedFixture)});return;}
    if(titleHold&&req.method()==='POST'&&url.pathname==='/story-workspace/title-suggestions'){
      const gate=titleHold;titleHold=null;titleSelectionBody=req.postData();arrivedTitleHold();await gate;const body=JSON.parse(req.postData()),chapters=JSON.parse(body.chapters),source=chapters[0].evidence_ids[0];
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,selection_revision:body.selection_revision,needs_review:true,titles:[{text:'A delayed reviewed title',source_ids:[source]}]})});return;
    }
    const headers=await req.allHeaders();delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']=new URL(req.frame().url()).origin===url.origin?'same-origin':'none';
    const result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    if(url.pathname.startsWith('/auth/')){let summary={};if(url.pathname==='/auth/session'&&result.status===200){try{const value=JSON.parse(Buffer.from(result.body,'base64').toString());summary={account_id:value.account_id,memberships:Array.isArray(value.memberships)?value.memberships.map(member=>({library_id:member.library_id,available:member.available,role:member.role})):null};}catch{}}authExchanges.push({method:req.method(),path:url.pathname,status:result.status,...summary});}
    if(hold&&url.pathname==='/story-workspace/preview'){const gate=hold;hold=null;arrivedHold();await gate;}
    let body=Buffer.from(result.body,'base64');
    if(constrainPreviewEvidence&&req.method()==='POST'&&url.pathname==='/story-workspace/preview'){
      constrainPreviewEvidence=false;const payload=JSON.parse(body.toString()),section=payload.chapters[0];
      const [firstItem,secondItem]=payload.items;
      if(!section||payload.items.length!==2||!firstItem.evidence.length||!secondItem.evidence.length)throw new Error('Fixture needs two cited chapter assets with source text');
      const family={id:'family-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',source:'family',title:'合成家人回忆',text:'<em>家人原话</em> & 仅作界面测试'};
      const sharedId='family-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',shared={id:sharedId,source:'family',title:'共同回忆',text:'两张照片共享的合成回忆',revision:3,origin_asset_id:'999',byline:'<em>Grandma</em> & family'};
      const firstShared=shared,secondShared=shared;
      firstItem.evidence.push(family,firstShared);secondItem.evidence.push(secondShared);
      const firstAsset=firstItem.id,secondAsset=secondItem.id;
      payload.chapters=[
        {...section,id:'chapter-1',title:'第一章',asset_ids:[firstAsset],evidence_ids:[family.id,sharedId]},
        {...section,id:'chapter-2',title:'第二章',asset_ids:[secondAsset],evidence_ids:[sharedId]}
      ];
      previewEvidence={family,sharedId,sharedText:shared.text,sharedByline:shared.byline,uncited:firstItem.evidence.find(item=>item.id!==family.id&&item.id!==sharedId)};
      body=Buffer.from(JSON.stringify(payload));
    } else if(req.method()==='POST'&&url.pathname==='/story-workspace/preview'&&result.status===200){
      // Later browser checkpoints retain one ephemeral family-source marker so
      // the logout test can prove private reader DOM is cleared while mounted.
      const payload=JSON.parse(body.toString()),item=payload.items[0],id='family-clear-fixture';
      item.evidence.push({id,source:'family',title:'',text:'合成家庭来源清除检查'});
      const section=payload.chapters.find(value=>value.asset_ids.includes(item.id));if(section)section.evidence_ids.push(id);
      if(duplicateAiPreview){duplicateAiPreview=false;const repeated=payload.items[0].evidence.find(value=>value.source==='ai');if(repeated&&payload.items[1])payload.items[1].evidence.push(structuredClone(repeated));}
      body=Buffer.from(JSON.stringify(payload));
    }
    if(req.method()==='POST'&&url.pathname==='/story-workspace/preview'&&result.status===200)lastPreviewPayload=JSON.parse(body.toString());
    if(shelfHold&&url.pathname==='/memory-stories'&&url.searchParams.get('theme')==='trip'){const gate=shelfHold;shelfHold=null;arrivedShelfHold();await gate;}
    if(corruptShelfTheme&&url.pathname==='/memory-stories'&&url.searchParams.has('theme')){corruptShelfTheme=false;const payload=JSON.parse(body.toString());if(payload.items?.length)payload.items[0].theme='birthday';body=Buffer.from(JSON.stringify(payload));}
    const output={...result.headers};delete output['content-length'];delete output['content-encoding'];
    try{await route.fulfill({status:result.status,headers:output,body});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  let dismissDialogs=false,dialogCount=0;
  const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{dialogCount++;return dismissDialogs?d.dismiss():d.accept();});
  async function login(phone='+12025550102'){await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill(phone);await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();}
  await login();
  assert.equal(await page.locator('.memory-theme').count(),6);
  assert.equal(await page.locator('#memory-home').isVisible(),true);
  assert.match(await page.locator('.memory-home-copy h2').textContent(),/值得慢慢看/);
  await page.screenshot({path:path.join(artifacts,'memory-home-desktop-zh.png'),fullPage:true});
  pass('Chinese memory home and six theme entries use authorized gallery media');
  await page.locator('.memory-theme[data-theme=trip]').click();
  assert.equal(await page.locator('#story-workspace').isVisible(),true);
  assert.equal(await page.locator('#story-workspace-theme').inputValue(),'trip');
  assert.equal(await page.locator('#story-selection input:checked').count(),2);
  await page.locator('.story-frame-order button[aria-label="向后移动 102"]').click();
  assert.deepEqual(await page.locator('#story-selection input').evaluateAll(nodes=>nodes.map(n=>n.value)),['101','102']);
  await page.locator('#story-workspace-title').fill('湖边的一天');
  sourceCapabilityUnavailableArrival=new Promise(resolve=>resolveSourceCapabilityUnavailableArrival=resolve);sourceCapabilityUnavailableGate=new Promise(resolve=>releaseSourceCapabilityUnavailable=resolve);const deniedCapability=page.waitForResponse(response=>{const url=new URL(response.url());return url.pathname==='/story-workspace/source-capabilities'&&response.status()===403;});
  await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();await sourceCapabilityUnavailableArrival;
  await page.evaluate(()=>{const textarea=document.querySelector('.story-chapter-card textarea');window.__sourceCapabilityForbiddenTextarea=textarea;textarea.focus();textarea.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true,data:''}));textarea.value+='仍在输入';textarea.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:'仍在输入'}));});
  releaseSourceCapabilityUnavailable();sourceCapabilityUnavailableGate=null;await deniedCapability;await page.evaluate(()=>window.__sourceCapabilityForbiddenTextarea.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'仍在输入'})));
  assert(await page.evaluate(()=>window.__sourceCapabilityForbiddenTextarea.isConnected&&document.activeElement===window.__sourceCapabilityForbiddenTextarea&&window.__sourceCapabilityForbiddenTextarea.value.includes('仍在输入')),'a legacy 403 keeps the focused composing draft intact');assert(await page.locator('#story-workspace').evaluate(node=>node.open),'optional capability 403 does not clear the active story workspace');assert.equal(await page.locator('#auth').isVisible(),false,'optional capability 403 does not trigger authentication expiry UI');
  pass('Legacy capability 403 falls back without clearing a composing draft or opening authentication UI');
  assert.equal(await page.locator('.story-chapter-card').count(),2);
  assert.equal(await page.locator('.story-source-opt-in').count(),0,'an older server leaves source-choice controls unavailable');
  await page.locator('.story-chapter-card input').first().fill('从这段回忆开始');
  await page.locator('.story-chapter-card textarea').first().fill('那天下午，我们沿着湖边慢慢走。\n这段文字由家人补充。');
  dismissDialogs=true;
  await page.locator('#story-workspace-theme').selectOption('birthday');
  assert.equal(await page.locator('#story-workspace-theme').inputValue(),'trip');
  await page.locator('#story-selection input').first().click();
  assert.equal(await page.locator('#story-selection input:checked').count(),2);
  await page.locator('#story-build').click();
  assert.match(await page.locator('.story-chapter-card textarea').first().inputValue(),/家人补充/);
  dismissDialogs=false;
  pass('Cancelling replacement preserves edited narration, selected frames and theme');
  await page.locator('.story-reference-list summary').first().click();
  assert.match(await page.locator('.story-reference-list').first().textContent(),/AI 观察.*待核实/);
  await page.screenshot({path:path.join(artifacts,'story-editor-desktop-zh.png'),fullPage:true});
  pass('Authenticated multi-media outline, editable chapter and separate AI references');
  const downloadEvent=page.waitForEvent('download');await page.locator('#story-export').click();
  const download=await downloadEvent;await download.saveAs(path.join(artifacts,'synthetic-story-draft.json'));
  const exported=JSON.parse(fs.readFileSync(path.join(artifacts,'synthetic-story-draft.json'),'utf8'));
  assert.equal(exported.saved,false);assert.equal(exported.title,'湖边的一天');assert.match(exported.chapters[0].narration,/家人补充/);assert.equal(Object.hasOwn(exported,'source_policy'),false,'legacy draft export does not claim an explicit source policy');
  await page.locator('#story-preview').click();if(!(await page.locator('#story-reader').isVisible()))throw new Error('Reader failed to open: '+JSON.stringify(errors));await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-workspace').isVisible(),true,'draft preview retains its existing editor underneath');
  assert.equal(await page.locator('#story-reader-title').textContent(),'从这段回忆开始');
  await page.waitForFunction(()=>Boolean(document.querySelector('#story-reader-stage img')?.naturalWidth));
  await page.screenshot({path:path.join(artifacts,'story-reader-desktop-zh.png'),fullPage:true});
  pass('Edited narrative is read literally in cinematic preview and explicit draft download');
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert(await page.locator('#story-reader').evaluate(el=>el.scrollWidth<=el.clientWidth));
  await page.screenshot({path:path.join(artifacts,'story-reader-mobile-zh.png'),fullPage:true});
  const chapterSources=page.locator('#story-reader .story-reader-sources');assert.equal(await chapterSources.count(),1,'reader offers references for the active chapter');
  assert.equal(await chapterSources.evaluate(node=>node.open),false,'source disclosure starts collapsed');
  assert.equal(await chapterSources.locator('summary').evaluate(node=>getComputedStyle(node).display),'list-item','native details marker remains visible');
  assert.deepEqual(await chapterSources.locator('[data-evidence-id]').evaluateAll(nodes=>nodes.map(node=>node.dataset.evidenceId)),[previewEvidence.family.id,previewEvidence.sharedId],'reader includes only the cited evidence attached to this chapter');
  assert.equal(await chapterSources.locator(`[data-evidence-id="${previewEvidence.uncited.id}"]`).count(),0,'reader excludes evidence attached to this image when the chapter did not cite it');
  assert.match(await chapterSources.textContent(),/参考资料，不代表已核实事实/);
  assert.equal(await chapterSources.locator('[data-evidence-id] strong').count(),2,'each canonical source is rendered once in the chapter');
  assert.equal(await chapterSources.locator('[data-evidence-id="' + previewEvidence.sharedId + '"]').count(),1);
  const zhSourceText=await chapterSources.textContent();
  assert.match(zhSourceText,/家人提供的文字/);
  assert.match(zhSourceText,/来源素材 999/);
  assert.ok(zhSourceText.includes(previewEvidence.sharedByline));
  assert.equal(await chapterSources.locator('em').count(),0,'family wording is rendered as literal text, never interpreted as markup');
  assert.match(await chapterSources.textContent(),/<em>家人原话<\/em> & 仅作界面测试/);
  await chapterSources.locator('summary').press('Enter');assert.equal(await chapterSources.evaluate(node=>node.open),true,'native disclosure opens from the keyboard');
  await chapterSources.screenshot({path:path.join(artifacts,'story-reader-sources-mobile-zh.png')});
  const postsBeforeTranslation=requests.filter(item=>item.method==='POST').length;
  await page.evaluate(()=>window.__setStoryWorkspaceTestLanguage('en'));
  assert.equal(await chapterSources.evaluate(node=>node.open),true,'translation preserves disclosure state');
  assert.equal(await chapterSources.locator('summary').textContent(),'View sources for this chapter');
  assert.equal(await chapterSources.locator('.story-reader-sources-note').textContent(),'These are references cited for this chapter; they are not verified facts.');
  assert.equal(await chapterSources.locator('[data-evidence-id] strong').first().textContent(),'Family-provided wording');
  assert.match(await chapterSources.textContent(),/Source item 999/);
  assert.ok((await chapterSources.textContent()).includes(previewEvidence.sharedByline));
  assert.equal(requests.filter(item=>item.method==='POST').length,postsBeforeTranslation,'source translation sends no request');
  await page.evaluate(()=>{window.__setStoryWorkspaceTestLanguage('zh');window.__setStoryWorkspaceTestLanguage(null);});
  const narration=page.locator('.story-narration-controls');
  assert.equal(await narration.count(),1);assert.equal(await page.evaluate(()=>window.__mockSpeech.utterances.length),0,'loading a reader must not autoplay narration');
  await narration.getByRole('button',{name:'朗读本章'}).click();
  assert.equal(await page.evaluate(()=>window.__mockSpeech.utterances.length),1);assert.match(await narration.textContent(),/正在朗读本章/);
  await narration.getByRole('button',{name:'暂停朗读'}).click();assert.equal(await page.evaluate(()=>window.__mockSpeech.synth.paused),true);
  await narration.getByRole('button',{name:'继续朗读'}).click();assert.equal(await page.evaluate(()=>window.__mockSpeech.synth.paused),false);
  await narration.getByRole('button',{name:'暂停朗读'}).click();await narration.getByRole('button',{name:'停止朗读'}).click();assert.equal(await page.evaluate(()=>window.__mockSpeech.synth.paused),true,'mock cancel preserves paused state');
  const resumeCount=await page.evaluate(()=>window.__mockSpeech.synth.resumeCount);await narration.getByRole('button',{name:'朗读本章'}).click();assert.equal(await page.evaluate(()=>window.__mockSpeech.synth.paused),false,'new explicit start resumes after paused cancel');assert.equal(await page.evaluate(()=>window.__mockSpeech.synth.resumeCount),resumeCount+1);
  const callsBeforeStop=await page.evaluate(()=>window.__mockSpeech.utterances.length);await narration.getByRole('button',{name:'停止朗读'}).click();
  await page.evaluate(()=>window.__mockSpeech.utterances[0].onend?.());assert.equal(await page.evaluate(()=>window.__mockSpeech.utterances.length),callsBeforeStop,'late end callback cannot restart a cancelled utterance');
  await narration.getByRole('button',{name:'朗读本章'}).click();assert.equal(await page.evaluate(()=>window.__mockSpeech.utterances.length),callsBeforeStop+1);
  await page.locator('#story-reader-play').click();assert.equal(await page.evaluate(()=>window.__mockSpeech.synth.speaking),false,'story slideshow activation stops narration');await page.locator('#story-reader-play').click();
  await page.locator('#story-reader-next').click();assert.equal(await page.evaluate(()=>window.__mockSpeech.synth.speaking),false,'chapter change cancels narration');
  assert.equal(await page.locator('#story-reader .story-reader-sources').evaluate(node=>node.open),false,'chapter change closes the source disclosure');
  assert.deepEqual(await page.locator('#story-reader .story-reader-sources [data-evidence-id]').evaluateAll(nodes=>nodes.map(node=>node.dataset.evidenceId)),[previewEvidence.sharedId]);
  assert.equal(await page.locator('#story-reader .story-reader-sources').locator(`[data-evidence-id="${previewEvidence.sharedId}"]`).count(),1,'shared citation ID does not expose a sibling asset’s second record');
  assert.ok((await page.locator('#story-reader .story-reader-sources').textContent()).includes(previewEvidence.sharedText));
  assert.ok((await page.locator('#story-reader .story-reader-sources').textContent()).includes(previewEvidence.sharedByline));
  await page.locator('#story-reader-previous').click();
  assert.equal(await page.evaluate(()=>window.__mockSpeech.synth.speaking),false,'navigation cancels narration');
  await page.evaluate(()=>{document.documentElement.style.zoom='150%';});
  assert(await narration.evaluate(el=>el.scrollWidth<=el.clientWidth),'150% narration controls remain within their reader column');await narration.scrollIntoViewIfNeeded();
  await narration.screenshot({path:path.join(artifacts,'story-narration-mobile-150-zh.png')});
  assert.equal(await chapterSources.evaluate(node=>node.open),false);await chapterSources.screenshot({path:path.join(artifacts,'story-reader-sources-mobile-150-closed-zh.png')});
  await chapterSources.locator('summary').press('Enter');assert(await chapterSources.evaluate(node=>node.scrollWidth<=node.clientWidth),'expanded chapter sources fit at 150% zoom');await chapterSources.screenshot({path:path.join(artifacts,'story-reader-sources-mobile-150-zh.png')});
  assert.equal(await page.locator('#story-reader').evaluate(el=>el.open),true,'reader remains open during chapter narration checks');
  await page.screenshot({path:path.join(artifacts,'story-reader-mobile-150-zh.png')});
  await page.evaluate(()=>{document.documentElement.style.zoom='';});
  const beforeClosePlay=await page.evaluate(()=>window.__mockSpeech.utterances.length);await narration.getByRole('button',{name:'朗读本章'}).click();assert.equal(await page.evaluate(()=>window.__mockSpeech.utterances.length),beforeClosePlay+1,'explicit play starts before close test');const cancelCount=await page.evaluate(()=>window.__mockSpeech.synth.cancelCount);await page.locator('#story-reader-close').click();await page.locator('#story-reader').waitFor({state:'hidden'});
  assert(await page.evaluate(count=>window.__mockSpeech.synth.cancelCount>count,cancelCount),'closing the reader cancels active narration');
  pass('Mock local voice is explicit, pausable, cancellable and never resumes after chapter or frame navigation');
  assert(await page.locator('#story-workspace').evaluate(el=>el.scrollWidth<=el.clientWidth));
  await page.screenshot({path:path.join(artifacts,'story-editor-mobile-zh.png'),fullPage:true});
  if(await page.locator('#story-workspace').evaluate(dialog=>dialog.open)){await page.locator('#story-workspace-close').evaluate(button=>button.click());await page.locator('#story-workspace').waitFor({state:'hidden'});}
  await page.screenshot({path:path.join(artifacts,'memory-home-mobile-zh.png'),fullPage:true});
  pass('390px home, editor and story preview have no horizontal overflow');
  sourceCapabilitiesAvailable=true;constrainPreviewEvidence=true;
  await page.locator('#language').click();
  sourceCapabilityRequestsHeld=0;sourceCapabilityArrival=new Promise(resolve=>resolveSourceCapabilityArrival=resolve);sourceCapabilityGate=new Promise(resolve=>releaseSourceCapability=resolve);sourceCapabilityDelay=true;
  await page.locator('#memory-create').click();
  assert.match(await page.locator('#story-workspace-heading').textContent(),/Story draft/);
  await page.locator('#story-workspace-title').fill('<img src=x onerror=alert(1)>');await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();
  await sourceCapabilityArrival;
  await page.evaluate(()=>{const textarea=document.querySelector('.story-chapter-card textarea');window.__sourceCapabilityFocusedTextarea=textarea;textarea.focus();textarea.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true,data:''}));textarea.value+='正在输入';textarea.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:'正在输入'}));});
  sourceCapabilityDelay=false;releaseSourceCapability();await page.locator('.story-source-opt-in').first().waitFor();await page.evaluate(()=>window.__sourceCapabilityFocusedTextarea.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'正在输入'})));
  assert(await page.evaluate(()=>window.__sourceCapabilityFocusedTextarea.isConnected&&document.activeElement===window.__sourceCapabilityFocusedTextarea&&window.__sourceCapabilityFocusedTextarea.value.includes('正在输入')),'late capability discovery preserves the composing narration node, text and focus');
  await page.locator('.story-source-opt-in').first().waitFor();
  const discardPromptsBeforeOptIn=dialogCount;
  await page.locator('.story-source-opt-in').first().click();
  assert.equal(dialogCount,discardPromptsBeforeOptIn,'explicit source review does not prompt to discard edited narration');assert.match(await page.locator('.story-chapter-card textarea').first().inputValue(),/正在输入/,'source opt-in preserves the edited chapter text');
  const sourceChoices=page.locator('.story-chapter-card').first().locator('.story-source-choice input');
  assert(await sourceChoices.count()>0,'explicit opt-in exposes references available to the chapter');
  await sourceChoices.evaluateAll(nodes=>nodes.forEach(input=>{input.checked=false;input.dispatchEvent(new Event('change',{bubbles:true}));}));
  assert.equal(await sourceChoices.evaluateAll(nodes=>nodes.filter(input=>input.checked).length),0,'a chapter can intentionally cite no source');
  await sourceChoices.first().check();assert.equal(await sourceChoices.evaluateAll(nodes=>nodes.filter(input=>input.checked).length),1,'chapter sources can be selected individually');
  const reviewedDownload=page.waitForEvent('download');await page.locator('#story-export').click();const reviewedDraftDownload=await reviewedDownload;await reviewedDraftDownload.saveAs(path.join(artifacts,'chapter-source-reviewed-draft.json'));const reviewedDraft=JSON.parse(fs.readFileSync(path.join(artifacts,'chapter-source-reviewed-draft.json'),'utf8'));assert.equal(reviewedDraft.source_policy,'chapter_sources_v1','offline export preserves the explicit source-review policy');assert.deepEqual(reviewedDraft.chapters[0].evidence_ids,[await sourceChoices.first().inputValue()],'offline export preserves the reviewed chapter source selection');
  await page.locator('.story-title-assistance button').first().waitFor();let titleArrival;const titleArrived=new Promise(resolve=>titleArrival=resolve);titleHold=new Promise(resolve=>releaseTitleHold=resolve);arrivedTitleHold=titleArrival;await page.locator('.story-title-assistance button').first().click();await titleArrived;
  await sourceChoices.first().uncheck();releaseTitleHold();await page.waitForTimeout(80);assert.equal(await page.locator('.story-title-choice').count(),0,'a delayed title result cannot restore suggestions after chapter sources change');await sourceChoices.first().check();
  const titleContext=JSON.parse(titleSelectionBody),titleChapters=JSON.parse(titleContext.chapters),renderedLayout=await page.locator('.story-chapter-card').evaluateAll(cards=>cards.map(card=>[...card.querySelectorAll('.story-chapter-strip img')].map(image=>image.alt))),secondChapterChoices=page.locator('.story-chapter-card').nth(1).locator('.story-source-choice input'),firstSelectedSources=await sourceChoices.evaluateAll(nodes=>nodes.filter(input=>input.checked).map(input=>input.value)),secondSelectedSources=await secondChapterChoices.evaluateAll(nodes=>nodes.filter(input=>input.checked).map(input=>input.value));assert.equal(titleContext.source_policy,'chapter_sources_v1');assert.deepEqual(titleChapters.map(chapter=>chapter.asset_ids),renderedLayout,'profiled title context preserves the actual generated manual 1+1 chapter layout');assert.equal(titleChapters.length,2);assert(titleChapters.every(chapter=>chapter.asset_ids.length===1),'the reviewed manual layout assigns one selected frame to each chapter');assert.deepEqual(titleChapters.map(chapter=>chapter.evidence_ids),[firstSelectedSources,secondSelectedSources],'each title chapter carries only its own explicitly selected evidence');
  const keyboardChoice=sourceChoices.first(),keyboardInitial=await keyboardChoice.isChecked();await keyboardChoice.focus();await page.keyboard.press('Space');assert.equal(await keyboardChoice.isChecked(),!keyboardInitial,'native checkbox toggles from keyboard focus');await page.keyboard.press('Space');assert.equal(await keyboardChoice.isChecked(),keyboardInitial,'keyboard can restore the explicit source choice');
  await page.setViewportSize({width:1280,height:960});assert.equal(await keyboardChoice.evaluate(input=>getComputedStyle(input).outlineStyle),'solid','keyboard-focused source checkbox has a visible focus ring');await page.locator('.story-source-selection').first().screenshot({path:path.join(artifacts,'story-source-selection-desktop-keyboard-en.png')});await page.screenshot({path:path.join(artifacts,'story-source-selection-desktop-en.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.zoom='150%';window.__setStoryWorkspaceTestLanguage('zh');});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert(await page.locator('.story-source-selection').first().evaluate(el=>el.scrollWidth<=el.clientWidth),'Chinese source choices fit a 390px viewport at 150% zoom');await page.locator('.story-source-selection').first().screenshot({path:path.join(artifacts,'story-source-selection-mobile-150-zh.png')});
  await page.evaluate(()=>{document.documentElement.style.zoom='';window.__setStoryWorkspaceTestLanguage('en');});await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>{document.documentElement.style.zoom='150%';});assert(await page.locator('.story-source-selection').first().evaluate(el=>el.scrollWidth<=el.clientWidth),'source choices fit a 390px viewport at 150% zoom');await page.locator('.story-source-selection').first().screenshot({path:path.join(artifacts,'story-source-selection-mobile-150-en.png')});await page.evaluate(()=>{document.documentElement.style.zoom='';});
  pass('Source selection is explicit, supports selected and empty chapters, and fits mobile at 150% zoom');
  let layoutTitleArrival;const layoutTitleArrived=new Promise(resolve=>layoutTitleArrival=resolve);titleHold=new Promise(resolve=>releaseTitleHold=resolve);arrivedTitleHold=layoutTitleArrival;await page.locator('.story-title-assistance button').first().click();await layoutTitleArrived;sourceCapabilityRequestsHeld=1;sourceCapabilityArrival=new Promise(resolve=>resolveSourceCapabilityArrival=resolve);sourceCapabilityGate=new Promise(resolve=>releaseSourceCapability=resolve);sourceCapabilityDelay=true;await page.evaluate(()=>window.__storyWorkspaceTest.open(['101','102'],'trip'));await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();await sourceCapabilityArrival;sourceCapabilityDelay=false;releaseSourceCapability();releaseTitleHold();await page.waitForTimeout(80);assert.equal(await page.locator('.story-title-choice').count(),0,'a delayed title from the replaced manual layout cannot appear in the new chapter draft');await page.locator('.story-source-opt-in').first().waitFor();await page.waitForFunction(()=>{const button=document.querySelector('.story-source-opt-in');return button&&!button.disabled;});await page.locator('.story-source-opt-in').first().click();const newStorySources=page.locator('.story-chapter-card').first().locator('.story-source-choice input');await newStorySources.first().waitFor();await newStorySources.evaluateAll(nodes=>nodes.forEach(input=>{input.checked=false;input.dispatchEvent(new Event('change',{bubbles:true}));}));await newStorySources.first().check();await page.locator('#story-workspace-title').fill('<img src=x onerror=alert(1)>');pass('A delayed reviewed title is discarded when its manual chapter layout is replaced');
  assert.equal(await page.locator('#story-workspace-title').inputValue(),'<img src=x onerror=alert(1)>');
  assert.equal(await page.locator('#story-chapter-editor img[src="x"]').count(),0);
  await page.locator('#story-preview').click();await page.locator('#story-reader').waitFor({state:'visible'});
  await page.locator('.story-narration-controls').getByRole('button',{name:'Read this chapter aloud'}).click();
  assert.equal(await page.evaluate(()=>window.__mockSpeech.utterances.at(-1).voice.lang),'en-US','English text uses a local English voice');
  await page.locator('#story-reader').press('Escape');assert.equal(await page.evaluate(()=>window.__mockSpeech.synth.speaking),false,'Escape closes the reader and cancels speech');
  sourceSaveRetryTest=true;await page.locator('#story-save-memory').click();await page.waitForFunction(()=>document.querySelector('#story-workspace-status')?.textContent.includes('not confirmed'));
  await page.locator('#story-save-memory').click();await page.waitForFunction(()=>document.querySelector('#story-workspace-status')?.textContent.includes('Saved in this library'),null,{timeout:8000}).catch(async error=>{console.log('SAVE DEBUG',sourceSaveAttempts,sourceSavedFixture&&Object.keys(sourceSavedFixture),await page.locator('#story-workspace-status').textContent(),errors);throw error;});
  assert.equal(sourceSaveAttempts,2,'uncertain source-profile save is retried');assert.equal(sourceSaveBodies[0],sourceSaveBodies[1],'retry reuses the exact immutable body and mutation ID');
  const savedRequestBody=JSON.parse(sourceSaveBodies[0]);assert.equal(savedRequestBody.source_policy,'chapter_sources_v1');assert.equal(JSON.parse(savedRequestBody.chapters)[0].evidence_ids.length,1,'save retains only the selected source reference');
  await page.evaluate(id=>window.__storyWorkspaceTest.reopen(id),sourceSavedFixture.id);await page.locator('#story-reader').waitFor({state:'visible'});
  assert(await page.locator('#story-reader-edit').isVisible(),`saved source-profile story exposes its edit action: ${JSON.stringify({errors})}`);await page.locator('#story-reader-edit').evaluate(button=>button.click());await page.locator('#story-reader').waitFor({state:'hidden'});await page.locator('#story-workspace').waitFor({state:'visible'});await page.locator('.story-source-selection').first().waitFor();
  assert.equal(await page.locator('.story-chapter-card').first().locator('.story-source-choice input:checked').count(),1,'saved source selection is restored when reopening the story');
  sourceSaveRetryTest=false;
  pass('Profiled save preserves the same request across an uncertain retry and restores chapter choices on reopen');
  if(await page.locator('#story-workspace').evaluate(dialog=>dialog.open))await page.locator('#story-workspace-close').evaluate(button=>button.click());
  pass('English workspace and user-provided markup remain literal text');
  duplicateAiPreview=true;await page.evaluate(()=>window.__storyWorkspaceTest.open(['101','102'],'trip'));await page.locator('#story-build').click();
  await page.waitForFunction(()=>document.querySelector('#story-workspace-status')?.textContent.includes('could not be arranged'));
  assert.equal(await page.locator('.story-chapter-card').count(),0,'repeated AI evidence across items is rejected before editor render');
  await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();await page.locator('#story-workspace-close').click();
  pass('Malformed repeated AI evidence is rejected while identical attributed family evidence remains valid');
  await page.locator('#saved-memory-refresh').click();await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===8);
  const hasListCall=(pageNumber,theme)=>requests.some(item=>{const parsed=new URL(item.path,'https://photohouse.test');if(!parsed.pathname.endsWith('/memory-stories'))return false;const query=parsed.searchParams;return query.get('page')===String(pageNumber)&&(theme===null?!query.has('theme'):query.get('theme')===theme);});
  assert(hasListCall(1,null),'All keeps the existing all-stories request path without a theme parameter');
  assert.equal(await page.locator('#saved-memory-filters button').count(),7);assert.equal(await page.locator('#saved-memory-filters [aria-pressed=true]').getAttribute('data-theme'),'all');
  assert.equal(await page.locator('#saved-memory-list .saved-memory-card').count(),8);assert(await page.locator('#saved-memory-more').isVisible(),'all stories paginate globally');await page.locator('#saved-memory-more').click();await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===10);
  await page.locator('#saved-memory-filters [data-theme=trip]').click();await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===8);assert(hasListCall(1,'trip'));assert(await page.locator('#saved-memory-more').isVisible());await page.locator('#saved-memory-more').click();await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===9);assert(hasListCall(2,'trip'));
  await page.locator('#saved-memory-filters [data-theme=birthday]').click();await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===1);const birthdayRefresh=page.waitForRequest(req=>new URL(req.url()).searchParams.get('theme')==='birthday'&&new URL(req.url()).searchParams.get('page')==='1');await page.locator('#saved-memory-refresh').click();await birthdayRefresh;await page.waitForFunction(()=>!document.querySelector('#saved-memory-refresh').disabled);assert(hasListCall(1,'birthday'));
  await page.locator('#saved-memory-filters [data-theme=grandparents]').click();await page.waitForFunction(()=>document.querySelector('.saved-memory-empty'));assert.match(await page.locator('.saved-memory-empty').textContent(),/No saved stories under this theme yet/);assert.equal(await page.locator('#saved-memory-more').isHidden(),true);await page.locator('.saved-memory-empty-actions button').first().click();await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===8);assert.equal(await page.locator('#saved-memory-filters [data-theme=all]').getAttribute('aria-pressed'),'true');
  let shelfArrival;const shelfArrived=new Promise(resolve=>shelfArrival=resolve);shelfHold=new Promise(resolve=>releaseShelfHold=resolve);arrivedShelfHold=shelfArrival;await page.locator('#saved-memory-filters [data-theme=trip]').click();await shelfArrived;await page.locator('#saved-memory-filters [data-theme=birthday]').click();await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===1);releaseShelfHold();await page.waitForTimeout(80);assert.equal(await page.locator('#saved-memory-filters [data-theme=birthday]').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('#saved-memory-list .saved-memory-card').count(),1,'late trip response cannot replace current birthday filter');
  let logoutArrival;const logoutArrived=new Promise(resolve=>logoutArrival=resolve);shelfHold=new Promise(resolve=>releaseShelfHold=resolve);arrivedShelfHold=logoutArrival;await page.locator('#saved-memory-filters [data-theme=trip]').click();await logoutArrived;await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});releaseShelfHold();await page.waitForTimeout(80);assert.equal(await page.locator('#saved-memory-list .saved-memory-card').count(),0,'late filtered reply after account clear cannot restore prior cards');assert.equal(await page.locator('#saved-memory-filters [data-theme=all][aria-pressed=true]').count(),1);await login();await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===8);
  corruptShelfTheme=true;await page.locator('#saved-memory-filters [data-theme=trip]').click();await page.waitForFunction(()=>document.querySelector('#saved-memory-status')?.textContent.includes('暂不可用'));assert.equal(await page.locator('#saved-memory-list .saved-memory-card').count(),0,'mismatched server theme is rejected before render');
  await page.locator('#saved-memory-refresh').click();await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===8);await page.setViewportSize({width:1280,height:960});await page.locator('#saved-memory-panel').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'saved-story-theme-shelf-desktop-top.png')});await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.evaluate(()=>{document.documentElement.style.zoom='150%';});assert(await page.locator('#saved-memory-filters').evaluate(el=>el.scrollWidth<=el.clientWidth));await page.locator('#saved-memory-panel').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'saved-story-theme-shelf-mobile-150-zh-top.png')});await page.locator('#saved-memory-panel').screenshot({path:path.join(artifacts,'saved-story-theme-shelf-mobile-150-zh.png')});await page.evaluate(()=>{document.documentElement.style.zoom='';});
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});assert.equal(await page.locator('#saved-memory-filters [data-theme=all][aria-pressed=true]').count(),1,'account clear resets selection to All');await login();await page.waitForFunction(()=>document.querySelector('#saved-memory-filters [data-theme=all][aria-pressed=true]'));await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===8);assert(hasListCall(1,null),'relogin starts in All with a fresh first-page request');
  pass('Saved story theme filters use server pagination, preserve selection on refresh, reject stale/mismatched replies and wrap at mobile zoom');
  await page.locator('#memory-create').click();
  await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();
  await page.locator('#story-preview').click();await page.locator('#story-reader').waitFor({state:'visible'});
  assert.match(await page.locator('#story-reader').textContent(),/合成家庭来源清除检查/,'synthetic family wording is present before account clear');
  await page.locator('#story-reader-close').click();await page.locator('#story-workspace-close').click();
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-reader .story-reader-sources').count(),0,'account clear removes private source disclosures from closed reader DOM');
  assert.doesNotMatch(await page.locator('#story-reader').textContent(),/合成家庭来源清除检查|家人原话/,'account clear removes synthetic private source wording from reader DOM');
  await login();
  await page.locator('#memory-create').click();
  hold=new Promise(resolve=>releaseHold=resolve);const arrived=new Promise(resolve=>arrivedHold=resolve);
  await page.locator('#story-build').click();await arrived;await page.locator('#story-workspace-close').click();
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});releaseHold();
  await page.waitForTimeout(100);
  assert.equal(await page.locator('#story-reader .story-reader-sources').count(),0,'logout removes private source disclosures from closed reader DOM');
  assert.doesNotMatch(await page.locator('#story-reader').textContent(),/合成家庭来源清除检查|家人原话/,'logout removes synthetic private source wording from reader DOM');
  assert.equal(await page.locator('#story-reader').isVisible(),false);
  assert.equal(await page.locator('#story-selection img').count(),0);
  assert.equal(await page.locator('#story-chapter-editor').textContent(),'');
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
  pass('Logout clears drafts/media; late preview cannot repopulate private UI; no browser storage');
  await login();await rpc({command:'mutate',scenario:'many-assets'});
  const albumIds=Array.from({length:29},(_,i)=>String(1101+i));
  await page.evaluate(ids=>window.__storyWorkspaceTest.open(ids,'trip'),albumIds);
  assert.equal(await page.locator('#story-selection input').count(),8,'album choices are paged in bounded groups');
  assert.equal(await page.locator('#story-selection input[value="1101"]').getAttribute('aria-label'),'画面 1101','ID-only album choices do not claim a media kind before metadata is loaded');
  assert.match(await page.locator('#story-selection-count').textContent(),/24 \/ 24.*共 29/);
  assert.match(await page.locator('#story-workspace-status').textContent(),/默认选中前 24/);
  const seen=await page.locator('#story-selection input').evaluateAll(nodes=>nodes.map(node=>node.value));
  for(let i=0;i<3;i++){await page.locator('#story-selection-next').click();seen.push(...await page.locator('#story-selection input').evaluateAll(nodes=>nodes.map(node=>node.value)));}
  assert.deepEqual(seen,albumIds,'every album choice remains reachable across pages');
  assert.equal(await page.locator('#story-selection input[value="1129"]').isDisabled(),true,'limit requires unchecking a choice first');
  await page.locator('#story-selection input[value="1129"]').evaluate(input=>{input.checked=true;input.dispatchEvent(new Event('change',{bubbles:true}));});
  assert.equal(await page.locator('#story-selection input[value="1129"]').isChecked(),false,'handler also enforces the cap');
  const detached=await page.locator('#story-selection input[value="1129"]').elementHandle();
  await page.locator('#story-selection-clear').click();assert.match(await page.locator('#story-selection-count').textContent(),/^0 \/ 24/);assert.equal(await page.locator('#story-build').isDisabled(),true);
  await detached.evaluate(input=>{input.checked=true;input.dispatchEvent(new Event('change',{bubbles:true}));});
  assert.match(await page.locator('#story-selection-count').textContent(),/^0 \/ 24/,'detached page choices cannot change a later selection');await detached.dispose();
  await page.locator('#story-selection-first').click();assert.match(await page.locator('#story-selection-count').textContent(),/^24 \/ 24/);
  await page.locator('#story-selection input[value="1101"]').uncheck();
  for(let i=0;i<3;i++)await page.locator('#story-selection-next').click();
  await page.locator('#story-selection input[value="1129"]').check();
  await page.evaluate(()=>window.__storyWorkspaceTest.open(['1101','1101'],'trip'));
  assert.equal(await page.locator('#story-selection input').count(),5,'malformed replacement preserves existing page and choices');
  assert.equal(await page.locator('#story-selection input[value="1129"]').isChecked(),true);
  await page.locator('#story-workspace').evaluate(el=>{el.style.fontSize='150%';el.scrollTop=0;});
  for(const selector of ['.story-selection-panel','.story-selection-actions','.story-selection-pages','.story-writing-panel'])assert(await page.locator(selector).evaluate(el=>el.scrollWidth<=el.clientWidth),`${selector} fits the 390px viewport at 150% text`);
  await page.locator('#story-workspace').screenshot({path:path.join(artifacts,'story-album-choices-mobile-150-zh.png')});
  await page.evaluate(()=>window.__storyWorkspaceTest.setItems([{id:'101',kind:'image'},{id:'102',kind:'video'}]));
  assert.match(await page.locator('#story-selection-count').textContent(),/^24 \/ 24.*共 29/,'a late gallery refresh does not replace the active album snapshot');
  await page.locator('.story-frame-start[aria-label="设为开头 1129"]').click();
  assert.equal(await page.locator('#story-selection input').first().inputValue(),'1129','a later selected frame can become the story cover/opening');
  await page.locator('#story-build').click();await page.waitForFunction(()=>document.querySelectorAll('.story-chapter-card').length===6);
  const outgoing=JSON.parse(requests.filter(r=>r.method==='POST'&&r.path.startsWith('/story-workspace/preview')).at(-1).body);
  assert.deepEqual(outgoing.asset_ids.split(','),['1129',...albumIds.slice(1,24)],'only selected IDs, in the displayed order, go to the real protected API');
  assert.match(await page.locator('#story-selection-count').textContent(),/^24 \/ 24.*共 29/,'building preserves the full album choice pool');
  {
    await page.evaluate(()=>window.__setStoryWorkspaceTestLanguage('en'));
    const chapter=page.locator('.story-chapter-card').first(),body=chapter.locator('textarea').first(),record=chapter.locator('.story-dictation-record'),help=chapter.locator('.story-dictation-help');assert(await help.isVisible(),'privacy and review terms are visible before recording');assert.match(await help.textContent(),/not saved as an original family recording[\s\S]*30 days/i,'pre-record help explains transient audio and 30-day recognized-text/status receipts');
    await body.fill('Typed before recording');const bodyHandle=await body.elementHandle(),saveRequestsBefore=requests.filter(item=>item.method==='POST'&&item.path.startsWith('/memory-stories')).length;
    dictationTranscript='Recognized after review';dictationTranscribeArrival=new Promise(resolve=>resolveDictationTranscribeArrival=resolve);dictationTranscribeGate=new Promise(resolve=>releaseDictationTranscribe=resolve);
    const requestsBefore=dictationTranscriptions;await record.focus();assert.equal(await record.evaluate(node=>document.activeElement===node),true,'the chapter record action is keyboard reachable');await page.keyboard.press('Enter');await chapter.locator('.story-dictation-stop').waitFor({state:'visible'});assert.equal(await page.evaluate(()=>window.__dictationMetrics.permissionRequests),1,'microphone permission is requested only after the explicit record action');
    await chapter.locator('.story-dictation-stop').click();await dictationTranscribeArrival;
    await body.evaluate(node=>{node.focus();node.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true,data:''}));node.value+='\nTyped during transcription';node.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:'Typed during transcription'}));});
    assert.equal(await body.evaluate(node=>node.isConnected&&document.activeElement===node),true,'transcription keeps the live narration textarea and focus mounted');
    releaseDictationTranscribe();dictationTranscribeGate=null;await chapter.locator('.story-dictation-review').waitFor({state:'visible'});assert.equal(await chapter.locator('.story-dictation-review textarea').inputValue(),'Recognized after review');
    await page.setViewportSize({width:1280,height:960});await chapter.locator('.story-chapter-dictation').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'story-dictation-review-desktop-en.png')});
    await page.setViewportSize({width:390,height:844});await chapter.locator('.story-chapter-dictation').scrollIntoViewIfNeeded();await page.evaluate(()=>{document.documentElement.style.zoom='150%';});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'English dictation review fits a 390px viewport at 150% zoom');assert(await chapter.locator('.story-chapter-dictation').evaluate(el=>el.scrollWidth<=el.clientWidth),'English dictation panel has no local horizontal overflow at 150% zoom');await chapter.locator('.story-chapter-dictation').screenshot({path:path.join(artifacts,'story-dictation-review-mobile-150-en.png')});await page.evaluate(()=>{document.documentElement.style.zoom='';});await page.setViewportSize({width:1280,height:960});
    await body.evaluate(node=>node.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true,data:'輸入中'})));assert.equal(await chapter.locator('.story-dictation-actions button').first().isDisabled(),true,'Add stays disabled while chapter text is composing');
    await body.evaluate(node=>node.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'輸入中'})));await chapter.locator('.story-dictation-actions button').first().click();
    assert.equal(await bodyHandle.evaluate(node=>node.isConnected),true,'the same narration textarea remains mounted after review');
    assert.equal(await body.inputValue(),'Typed before recording\nTyped during transcription\n\nRecognized after review','Add appends reviewed words after the latest typed narration with a paragraph break');
    assert.equal(dictationTranscriptions,requestsBefore+1);const metrics=await page.evaluate(()=>window.__dictationMetrics);assert(metrics.trackStops>=1&&metrics.contextCloses>=1,'recording stops microphone tracks and closes its audio context');
    assert.equal(requests.filter(item=>item.method==='POST'&&item.path.startsWith('/memory-stories')).length,saveRequestsBefore,'dictation and Add never save the story');await bodyHandle.dispose();
    await page.evaluate(()=>window.__setStoryWorkspaceTestLanguage('zh'));assert.match(await help.textContent(),/语音服务会保留 30 天/,'pre-record explanation is localized in Chinese');await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.zoom='150%';});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Chinese dictation controls fit a 390px viewport at 150% zoom');await page.evaluate(()=>{document.documentElement.style.zoom='';});await page.setViewportSize({width:1280,height:960});
    pass('Chapter dictation uses explicit record, editable review and Add; concurrent typing, IME, append and audio teardown are preserved');
  }
  {
    const chapter=page.locator('.story-chapter-card').first(),body=chapter.locator('textarea').first(),record=chapter.locator('.story-dictation-record');
    await body.fill('a'.repeat(5999));dictationTranscript='x';await record.click();await chapter.locator('.story-dictation-stop').waitFor({state:'visible'});
    await page.locator('#story-preview').click();assert.equal(await page.locator('#story-reader').evaluate(dialog=>dialog.open),false,'preview is blocked while recording');
    const sourceOptIn=page.locator('.story-source-opt-in').first();if(await sourceOptIn.count()){await sourceOptIn.click();assert.equal(await page.locator('.story-source-choice').count(),0,'source review cannot change while voice is pending');}
    await page.locator('#story-save-memory').click();assert.match(await chapter.locator('.story-dictation-status').textContent(),/Add or discard|添加或丢弃/,'save requires resolving the pending recording');
    await chapter.locator('.story-dictation-stop').click();await chapter.locator('.story-dictation-review').waitFor({state:'visible'});await page.setViewportSize({width:390,height:844});await chapter.locator('.story-chapter-dictation').scrollIntoViewIfNeeded();await page.evaluate(()=>{document.documentElement.style.zoom='150%';});assert(await chapter.locator('.story-chapter-dictation').evaluate(el=>el.scrollWidth<=el.clientWidth),'Chinese dictation review has no horizontal overflow at 150% zoom');await chapter.locator('.story-chapter-dictation').screenshot({path:path.join(artifacts,'story-dictation-review-mobile-150-zh.png')});await page.evaluate(()=>{document.documentElement.style.zoom='';});await page.setViewportSize({width:1280,height:960});await chapter.locator('.story-dictation-actions button').first().click();
    assert.equal(await body.inputValue(),'a'.repeat(5999),'over-limit insertion preserves the typed chapter');assert.equal(await chapter.locator('.story-dictation-review textarea').inputValue(),'x','over-limit insertion preserves the full transcript');assert.match(await chapter.locator('.story-dictation-status').textContent(),/6000 UTF-8 bytes|6000 UTF-8 字节/);
    const transcript=chapter.locator('.story-dictation-review textarea');await transcript.fill('invalid\u0001text');await chapter.locator('.story-dictation-actions button').first().click();assert.equal(await body.inputValue(),'a'.repeat(5999),'invalid edited transcript never enters chapter text');assert.equal(await chapter.locator('.story-dictation-review').isVisible(),true,'invalid transcript remains available for correction');assert.match(await chapter.locator('.story-dictation-status').textContent(),/invalid characters|无效字符/);await transcript.fill('x');
    await body.fill('short');await chapter.locator('.story-dictation-actions button').first().click();assert.equal(await body.inputValue(),'short\n\nx','shortened insertion keeps the paragraph break');
    await body.fill('Keep this wording');await record.click();await chapter.locator('.story-dictation-stop').waitFor({state:'visible'});await chapter.locator('.story-dictation-cancel').click();
    assert.equal(await body.inputValue(),'Keep this wording','cancel discards only volatile voice input');assert.equal(await chapter.locator('.story-dictation-review').isHidden(),true);assert.equal(await page.evaluate(()=>window.__dictationMetrics.permissionRequests),3);
    await record.click();await chapter.locator('.story-dictation-stop').waitFor({state:'visible'});await chapter.locator('.story-dictation-stop').click();await chapter.locator('.story-dictation-review').waitFor({state:'visible'});const retainedTranscript=await chapter.locator('.story-dictation-review textarea').inputValue();dismissDialogs=true;const leaveAccepted=await page.evaluate(()=>window.__storyWorkspaceTest.canLeave());dismissDialogs=false;assert.equal(leaveAccepted,false,'declining the dirty-draft leave confirmation refuses navigation');assert.equal(await page.locator('#story-workspace').evaluate(dialog=>dialog.open),true,'declined dirty-draft navigation leaves the workspace open');assert.equal(await chapter.locator('.story-dictation-review').isVisible(),true,'declined leave retains the pending transcript');assert.equal(await chapter.locator('.story-dictation-review textarea').inputValue(),retainedTranscript,'declined leave keeps transcript text unchanged');await chapter.locator('.story-dictation-actions button').nth(1).click();
    pass('Pending voice blocks save and preview, UTF-8 overflow keeps both texts, and explicit cancel discards only the transcript');
  }
  {
    dictationSaveRetryTest=true;const title=page.locator('#story-workspace-title');await title.fill('Dictation retry story');await page.locator('#story-save-memory').click();await page.waitForFunction(()=>/not confirmed|尚未确认/.test(document.querySelector('#story-workspace-status')?.textContent||''));
    assert.equal(await page.locator('.story-dictation-record').first().isDisabled(),true,'an uncertain save freezes recording');const capsBefore=requests.filter(item=>item.path.startsWith('/assistant/v1/capabilities')).length;await page.locator('.story-dictation-record').first().evaluate(button=>button.click());assert.equal(requests.filter(item=>item.path.startsWith('/assistant/v1/capabilities')).length,capsBefore,'frozen retry starts no capability or microphone work');
    await page.locator('#story-save-memory').click();await page.waitForFunction(()=>/Saved in this library|保存到这个相册库/.test(document.querySelector('#story-workspace-status')?.textContent||''));
    assert.equal(dictationSaveAttempts,2,'the exact pending save can be retried');dictationSaveRetryTest=false;pass('An uncertain save disables dictation until the identical story save is retried');
  }
  await page.locator('#story-selection-next').click();assert.equal(await page.locator('#story-selection input').count(),8);
  await page.locator('#story-workspace-close').click();
  await page.evaluate(()=>window.__storyWorkspaceTest.open(['101','102'],'trip'));
  assert.equal(await page.locator('#story-selection input[value="102"]').getAttribute('aria-label'),'视频 102','ID-only choices reuse known gallery metadata without claiming an immediate playback action');
  await page.locator('#story-workspace-close').click();await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-selection img').count(),0,'large album choice pool clears at logout');
  await rpc({command:'mutate',scenario:'member-second-library'});await login();assert.equal(await page.locator('#library-select option[value="family-b"]').count(),1,'stale authorization fixture has a second available library');sourceCapabilitiesAvailable=false;sourceCapabilityUnavailableStatus=403;
  sourceAccessCheckArrival=new Promise(resolve=>resolveSourceAccessCheckArrival=resolve);sourceAccessCheckGate=new Promise(resolve=>releaseSourceAccessCheck=resolve);
  await page.evaluate(()=>window.__storyWorkspaceTest.open());await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();await sourceAccessCheckArrival;
  await page.locator('#library-select').selectOption('family-b');await page.locator('#grid .asset').first().waitFor();releaseSourceAccessCheck();sourceAccessCheckGate=null;await page.waitForTimeout(100);
  assert.equal(await page.locator('#library-select').inputValue(),'family-b','late source authorization result cannot invalidate the newly selected library');assert.equal(await page.locator('#auth').isVisible(),false,'stale source authorization result cannot log out the fresh scope');assert.equal(await page.locator('#story-chapter-editor').textContent(),'','scope change clears the old private draft');
  {
    dictationCapabilityStatus=200;dictationCapabilityArrival=new Promise(resolve=>resolveDictationCapabilityArrival=resolve);dictationCapabilityGate=new Promise(resolve=>releaseDictationCapability=resolve);
    await page.evaluate(()=>window.__storyWorkspaceTest.open());await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();const permissionRequests=await page.evaluate(()=>window.__dictationMetrics.permissionRequests);await page.locator('.story-dictation-record').first().click();await dictationCapabilityArrival;
    await page.locator('#story-workspace-close').click();releaseDictationCapability();dictationCapabilityGate=null;await page.waitForTimeout(80);
    assert.equal(await page.evaluate(()=>window.__dictationMetrics.permissionRequests),permissionRequests,'a late capability response after close cannot start microphone capture');assert.equal(await page.locator('.story-dictation-review').first().isHidden(),true,'closed capability request cannot open a transcript review');
    pass('Closing during capability lookup aborts the request before microphone permission or capture');
  }
  {
    dictationCapabilityStatus=200;dictationTranscribeStatus=200;dictationTranscribeArrival=new Promise(resolve=>resolveDictationTranscribeArrival=resolve);dictationTranscribeGate=new Promise(resolve=>releaseDictationTranscribe=resolve);const beforeScopeCapture=await page.evaluate(()=>({...window.__dictationMetrics}));
    await page.evaluate(()=>window.__storyWorkspaceTest.open());await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();const chapter=page.locator('.story-chapter-card').first();await chapter.locator('.story-dictation-record').click();await chapter.locator('.story-dictation-stop').waitFor({state:'visible'});await chapter.locator('.story-dictation-stop').click();await dictationTranscribeArrival;
    await page.locator('#library-select').selectOption('family-a');await page.locator('#grid .asset').first().waitFor();releaseDictationTranscribe();dictationTranscribeGate=null;await page.waitForTimeout(100);
    assert.equal(await page.locator('#story-chapter-editor').textContent(),'','late ASR cannot repopulate a draft after changing libraries');assert.equal(await page.locator('.story-dictation-review').count(),0);const afterScopeCapture=await page.evaluate(()=>window.__dictationMetrics);assert(afterScopeCapture.trackStops>beforeScopeCapture.trackStops&&afterScopeCapture.contextCloses>beforeScopeCapture.contextCloses,'scope cancellation tears down active audio resources');
    pass('Library changes abort active transcription and prevent late chapter review from returning');
  }
  {
    const permissionRequests=await page.evaluate(()=>window.__dictationMetrics.permissionRequests);dictationCapabilityPayload={version:2,transcribe:true,max_audio_seconds:31};await page.evaluate(()=>window.__storyWorkspaceTest.open());await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();const record=page.locator('.story-dictation-record').first();await record.click();await page.waitForFunction(()=>/Voice transcription is unavailable|语音转写暂不可用/.test(document.querySelector('.story-chapter-dictation .story-dictation-status')?.textContent||''));assert.equal(await page.evaluate(()=>window.__dictationMetrics.permissionRequests),permissionRequests,'invalid capability version/duration cannot begin capture');dictationCapabilityPayload=null;await page.locator('#story-workspace-close').click();pass('Unsupported capability version and out-of-range audio duration are refused before microphone access');
  }
  {
    dictationCapabilityStatus=401;await page.evaluate(()=>window.__storyWorkspaceTest.open());await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();const permissionRequests=await page.evaluate(()=>window.__dictationMetrics.permissionRequests);await page.locator('.story-dictation-record').first().click();await page.waitForFunction(()=>document.querySelector('#story-chapter-editor')?.textContent===''&&!document.querySelector('#story-workspace')?.open);
    assert.equal(await page.evaluate(()=>window.__dictationMetrics.permissionRequests),permissionRequests,'capability denial never opens the microphone');dictationCapabilityStatus=200;await rpc({command:'mutate',scenario:'restore-member'});if(!await page.locator('#auth').isVisible()){await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});}const priorLoginStatuses=authExchanges.filter(entry=>entry.method==='POST'&&entry.path==='/auth/login').map(entry=>entry.status);assert.deepEqual(priorLoginStatuses,[200,200,200,200,200,200],'the six earlier generated fixture sign-ins all succeeded');await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');const limitedLogin=page.waitForResponse(response=>new URL(response.url()).pathname==='/auth/login');await page.locator('#auth-submit').click();const limitedResponse=await limitedLogin;assert.equal(limitedResponse.status(),429,'the existing synthetic admission limit remains active before advancing the clock');assert.equal(authExchanges.filter(entry=>entry.method==='POST'&&entry.path==='/auth/login').at(-1)?.status,429,'the seventh sign-in is refused by the six-attempt fixture limit');await rpc({command:'mutate',scenario:'advance-auth-window'});await login();assert.equal(authExchanges.filter(entry=>entry.method==='POST'&&entry.path==='/auth/login').at(-1)?.status,200,'the seventh sign-in succeeds after advancing only the synthetic clock beyond the admission window');
    await page.evaluate(()=>window.__storyWorkspaceTest.open());await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();dictationTranscribeStatus=403;const chapter=page.locator('.story-chapter-card').first();await chapter.locator('.story-dictation-record').click();await chapter.locator('.story-dictation-stop').waitFor({state:'visible'});await chapter.locator('.story-dictation-stop').click();await page.waitForFunction(()=>document.querySelector('#story-chapter-editor')?.textContent===''&&!document.querySelector('#story-workspace')?.open);
    assert.equal(await page.locator('.story-dictation-review').count(),0,'transcription denial clears private review text');dictationTranscribeStatus=200;await rpc({command:'mutate',scenario:'restore-member'});if(!await page.locator('#auth').isVisible()){await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});}await rpc({command:'mutate',scenario:'advance-auth-window'});await login();
    pass('401 capability and 403 transcription denials clear the protected editor without showing a transcript');
  }
  await page.locator('#library-select').selectOption('family-a');await page.locator('#grid .asset').first().waitFor();await page.evaluate(()=>window.__storyWorkspaceTest.open(['101','102'],'trip'));await page.locator('#story-workspace').waitFor({state:'visible'});revokeOnNextSessionCheck=true;
  await page.locator('#story-build').evaluate(button=>button.click());await page.waitForFunction(()=>document.querySelector('#library-select')?.value===''&&document.querySelectorAll('#grid .asset').length===0&&document.querySelector('#story-chapter-editor')?.textContent==='');
  assert.equal(await page.locator('#auth').isVisible(),false,'revoked library membership does not leave authenticated UI showing private media');assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),false,'revoked capability clears the private story editor');
  pass('403 capability rechecks membership, rejects revoked access, and ignores stale checks after scope changes');
  {
    await rpc({command:'mutate',scenario:'restore-member'});if(!await page.locator('#auth').isVisible()){await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});}await rpc({command:'mutate',scenario:'advance-auth-window'});await login();await page.locator('#library-select').selectOption('family-a');await page.locator('#grid .asset').first().waitFor();
    await page.evaluate(()=>window.__storyWorkspaceTest.open());await page.locator('#story-build').click();const chapter=page.locator('.story-chapter-card').first(),record=chapter.locator('.story-dictation-record');await record.waitFor();
    const before=await page.evaluate(()=>({...window.__dictationMetrics})),transcriptionsBefore=dictationTranscriptions;await page.evaluate(()=>{let resolve;window.__dictationPermissionGate=new Promise(done=>resolve=done);window.__releaseDictationPermission=()=>{resolve();window.__dictationPermissionGate=null;};});
    await record.click();await page.waitForFunction(previous=>window.__dictationMetrics.permissionRequests>previous,before.permissionRequests);await chapter.locator('.story-dictation-cancel').waitFor({state:'visible'});
    assert.equal(await chapter.locator('.story-dictation-stop').isHidden(),true,'Stop is hidden while getUserMedia permission is pending');assert.match(await chapter.locator('.story-dictation-status').textContent(),/Waiting for microphone permission|等待麦克风权限/,'startup has its own pending-permission state');
    await chapter.locator('.story-dictation-cancel').click();await page.evaluate(()=>window.__releaseDictationPermission());await page.waitForFunction(previous=>window.__dictationMetrics.trackStops>previous,before.trackStops);assert.equal(await chapter.locator('.story-dictation-review').isHidden(),true,'late permission cannot create a review after startup cancellation');assert.equal(dictationTranscriptions,transcriptionsBefore,'cancelled permission startup never sends audio to transcription');
    await page.evaluate(()=>{window.__dictationNoSamples=true;});await record.click();await chapter.locator('.story-dictation-stop').waitFor({state:'visible'});await chapter.locator('.story-dictation-stop').click();await page.waitForFunction(()=>document.querySelector('.story-dictation-record')&&!document.querySelector('.story-dictation-record').hidden&&/Recording did not start or finish|录音未能开始或完成/.test(document.querySelector('.story-dictation-status')?.textContent||''));assert.equal(dictationTranscriptions,transcriptionsBefore,'an empty capture is reset before transcription');
    await page.evaluate(()=>{window.__dictationNoSamples=false;});const body=chapter.locator('textarea').first();await body.fill('Keep the chapter');dictationTranscript='recognized words';await record.click();await chapter.locator('.story-dictation-stop').waitFor({state:'visible'});await chapter.locator('.story-dictation-stop').click();await chapter.locator('.story-dictation-review').waitFor({state:'visible'});const transcript=chapter.locator('.story-dictation-review textarea');assert.equal(await transcript.inputValue(),'recognized words','recognized service text uses its closed-v1 bound');await transcript.fill('x'.repeat(6001));await chapter.locator('.story-dictation-actions button').first().click();assert.equal(await body.inputValue(),'Keep the chapter','edited overflow cannot replace existing chapter wording');assert.equal((await transcript.inputValue()).length,6001,'overflow leaves the entire edited transcript for trimming');await transcript.fill('trimmed and reviewed');await chapter.locator('.story-dictation-actions button').first().click();assert.equal(await body.inputValue(),'Keep the chapter\n\ntrimmed and reviewed');
    dictationTranscript='x'.repeat(1025);await record.click();await chapter.locator('.story-dictation-stop').waitFor({state:'visible'});await chapter.locator('.story-dictation-stop').click();await page.waitForFunction(()=>/Transcription could not finish|转写未能完成/.test(document.querySelector('.story-dictation-status')?.textContent||''));assert.equal(await chapter.locator('.story-dictation-review').isHidden(),true,'recognized text over the closed-v1 1024-byte bound is refused');assert.equal(await body.inputValue(),'Keep the chapter\n\ntrimmed and reviewed','oversized recognized response cannot change chapter wording');
    assert(before.trackStops<await page.evaluate(()=>window.__dictationMetrics.trackStops),'cancelled delayed permission stops the late-arriving microphone stream');pass('Permission startup exposes Cancel only, empty capture resets, and long valid transcripts remain editable through chapter overflow');
    dictationTranscript='Auto-ready recording';dictationCapabilityPayload={version:1,transcribe:true,max_audio_seconds:1};const autoStopBefore=await page.evaluate(()=>window.__dictationMetrics.autoStopEvents),autoTranscriptionsBefore=dictationTranscriptions;await page.evaluate(()=>{window.__dictationAutoStopSamples=16000;window.__dictationAutoStopBeforeResume=true;let resolve;window.__dictationResumeGate=new Promise(done=>resolve=done);window.__releaseDictationResume=()=>{resolve();window.__dictationResumeGate=null;};});
    await record.click();await page.waitForFunction(previous=>window.__dictationMetrics.autoStopEvents>previous,autoStopBefore);assert.equal(await chapter.locator('.story-dictation-stop').isHidden(),true,'auto-ready capture remains in startup until resume settles');assert.equal(await chapter.locator('.story-dictation-cancel').isVisible(),true,'startup can still be cancelled while resume is pending');await page.evaluate(()=>window.__releaseDictationResume());await chapter.locator('.story-dictation-review').waitFor({state:'visible'});assert.equal((await chapter.locator('.story-dictation-review textarea').inputValue()),'Auto-ready recording','a valid file completed before resume settles still reaches transcript review');assert.equal(dictationTranscriptions,autoTranscriptionsBefore+1,'already-stopped valid capture is transcribed once');await page.evaluate(()=>{window.__dictationAutoStopBeforeResume=false;});
    const staleCancel=await chapter.locator('.story-dictation-cancel').elementHandle();await chapter.locator('.story-dictation-actions button').last().click();await page.evaluate(()=>window.__storyWorkspaceTest.open(['101','102'],'trip'));await page.locator('#story-build').click();const nextChapter=page.locator('.story-chapter-card').first(),nextRecord=nextChapter.locator('.story-dictation-record');await nextRecord.waitFor();dictationCapabilityPayload=null;dictationTranscript='New session survives stale cancel';await nextRecord.click();await nextChapter.locator('.story-dictation-stop').waitFor({state:'visible'});await staleCancel.evaluate(button=>button.click());assert.equal(await nextChapter.locator('.story-dictation-stop').isVisible(),true,'a detached prior session cancel cannot invalidate the newer recording');await nextChapter.locator('.story-dictation-stop').click();await nextChapter.locator('.story-dictation-review').waitFor({state:'visible'});assert.equal((await nextChapter.locator('.story-dictation-review textarea').inputValue()),'New session survives stale cancel','new session remains usable after stale cancel callback');assert.equal(dictationTranscriptions,autoTranscriptionsBefore+2,'subsequent recording proves the capture reservation was released');
    pass('Auto-ready capture before delayed resume transcribes and releases capture; stale detached cancel leaves a newer session usable');
  }
  assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
  pass('Large album choices remain available, cap is enforced, a later frame reaches the protected API, and choices clear at logout');
  fs.writeFileSync(path.join(artifacts,'checks.json'),JSON.stringify({checks,errors,external,fixture:'synthetic ASGI; Fetch Metadata explicitly modeled',saved_story_shelf_fixture:'synthetic response adapter; backend filtering separately covered by API tests'},null,2));
  console.log('ARTIFACTS '+artifacts);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(ctx)await ctx.close();if(browser)await browser.close();bridge.stdin.end();});
