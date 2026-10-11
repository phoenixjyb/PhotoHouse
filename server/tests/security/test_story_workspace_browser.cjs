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
let browser,ctx,hold=null,releaseHold,arrivedHold,titleHold=null,releaseTitleHold,arrivedTitleHold,titleSelectionBody=null,sourceCapabilityDelay=false,sourceCapabilityGate=null,releaseSourceCapability,sourceCapabilityArrival=null,resolveSourceCapabilityArrival,sourceCapabilityRequestsHeld=0,sourceCapabilityUnavailableStatus=403,sourceCapabilityUnavailableGate=null,releaseSourceCapabilityUnavailable,sourceCapabilityUnavailableArrival=null,resolveSourceCapabilityUnavailableArrival,sourceAccessCheckGate=null,releaseSourceAccessCheck,sourceAccessCheckArrival=null,resolveSourceAccessCheckArrival,revokeOnNextSessionCheck=false,shelfHold=null,releaseShelfHold,arrivedShelfHold,corruptShelfTheme=false,constrainPreviewEvidence=true,previewEvidence=null,sourceCapabilitiesAvailable=false,duplicateAiPreview=false,sourceSaveRetryTest=false,sourceSaveAttempts=0,sourceSaveBodies=[],sourceSavedFixture=null,lastPreviewPayload=null;const errors=[],external=[],checks=[],requests=[];
const pass=name=>{checks.push(name);console.log('PASS '+name);};
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  ctx=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block',acceptDownloads:true});
  await ctx.addInitScript(()=>{const utterances=[];class MockUtterance{constructor(text){this.text=text;}}const voices=[{name:'Synthetic local Chinese',lang:'zh-CN',localService:true},{name:'Synthetic local English',lang:'en-US',localService:true},{name:'Synthetic remote Chinese',lang:'zh-CN',localService:false}];const synth={speaking:false,pending:false,paused:false,cancelCount:0,resumeCount:0,getVoices:()=>voices,speak(value){utterances.push(value);this.speaking=true;},pause(){this.paused=true;},resume(){this.resumeCount++;this.paused=false;},cancel(){this.cancelCount++;this.speaking=false;this.pending=false;}};Object.defineProperty(window,'speechSynthesis',{configurable:true,value:synth});window.SpeechSynthesisUtterance=MockUtterance;window.__mockSpeech={utterances,synth};let Constructor;Object.defineProperty(window,'PhotoHouseStoryWorkspace',{configurable:true,get:()=>Constructor,set:value=>{Constructor=config=>{let forcedLanguage=null;const originalScope=config.scope;const instance=value({...config,scope:()=>({...originalScope(),...(forcedLanguage?{language:forcedLanguage}:{})})});window.__setStoryWorkspaceTestLanguage=language=>{forcedLanguage=language;instance.translate();};window.__storyWorkspaceTest=instance;return instance;};}});});
  await ctx.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    requests.push({method:req.method(),path:url.pathname+url.search,...(url.pathname==='/story-workspace/preview'?{body:req.postData()}:{} )});
    if(req.method()==='GET'&&url.pathname==='/story-workspace/source-capabilities'&&!sourceCapabilitiesAvailable){if(sourceCapabilityUnavailableGate){resolveSourceCapabilityUnavailableArrival();await sourceCapabilityUnavailableGate;}await route.fulfill({status:sourceCapabilityUnavailableStatus,contentType:'application/json',body:'{"detail":"not found"}'});return;}
    if(req.method()==='GET'&&url.pathname==='/story-workspace/source-capabilities'&&sourceCapabilityDelay){sourceCapabilityRequestsHeld++;if(sourceCapabilityRequestsHeld===2)resolveSourceCapabilityArrival();await sourceCapabilityGate;await route.fulfill({status:200,contentType:'application/json',body:'{"version":1,"source_policy":"chapter_sources_v1","max_sources_per_chapter":12,"needs_review":true}'});return;}
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
    if(sourceSaveRetryTest&&req.method()==='GET'&&url.pathname==='/memory-stories/00000000-0000-4000-8000-000000000099'&&url.searchParams.get('source_review')==='1'&&sourceSavedFixture){await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(sourceSavedFixture)});return;}
    if(titleHold&&req.method()==='POST'&&url.pathname==='/story-workspace/title-suggestions'){
      const gate=titleHold;titleHold=null;titleSelectionBody=req.postData();arrivedTitleHold();await gate;const body=JSON.parse(req.postData()),chapters=JSON.parse(body.chapters),source=chapters[0].evidence_ids[0];
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,selection_revision:body.selection_revision,needs_review:true,titles:[{text:'A delayed reviewed title',source_ids:[source]}]})});return;
    }
    const headers=await req.allHeaders();delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']=new URL(req.frame().url()).origin===url.origin?'same-origin':'none';
    const result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
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
  sourceCapabilitiesAvailable=true;
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
  const titleContext=JSON.parse(titleSelectionBody);assert.equal(titleContext.source_policy,'chapter_sources_v1');assert.deepEqual(JSON.parse(titleContext.chapters)[0].evidence_ids,[await sourceChoices.first().inputValue()],'title context receives only the explicitly selected chapter source');
  const keyboardChoice=sourceChoices.first(),keyboardInitial=await keyboardChoice.isChecked();await keyboardChoice.focus();await page.keyboard.press('Space');assert.equal(await keyboardChoice.isChecked(),!keyboardInitial,'native checkbox toggles from keyboard focus');await page.keyboard.press('Space');assert.equal(await keyboardChoice.isChecked(),keyboardInitial,'keyboard can restore the explicit source choice');
  await page.setViewportSize({width:1280,height:960});assert.equal(await keyboardChoice.evaluate(input=>getComputedStyle(input).outlineStyle),'solid','keyboard-focused source checkbox has a visible focus ring');await page.locator('.story-source-selection').first().screenshot({path:path.join(artifacts,'story-source-selection-desktop-keyboard-en.png')});await page.screenshot({path:path.join(artifacts,'story-source-selection-desktop-en.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.zoom='150%';window.__setStoryWorkspaceTestLanguage('zh');});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert(await page.locator('.story-source-selection').first().evaluate(el=>el.scrollWidth<=el.clientWidth),'Chinese source choices fit a 390px viewport at 150% zoom');await page.locator('.story-source-selection').first().screenshot({path:path.join(artifacts,'story-source-selection-mobile-150-zh.png')});
  await page.evaluate(()=>{document.documentElement.style.zoom='';window.__setStoryWorkspaceTestLanguage('en');});await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>{document.documentElement.style.zoom='150%';});assert(await page.locator('.story-source-selection').first().evaluate(el=>el.scrollWidth<=el.clientWidth),'source choices fit a 390px viewport at 150% zoom');await page.locator('.story-source-selection').first().screenshot({path:path.join(artifacts,'story-source-selection-mobile-150-en.png')});await page.evaluate(()=>{document.documentElement.style.zoom='';});
  pass('Source selection is explicit, supports selected and empty chapters, and fits mobile at 150% zoom');
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
  duplicateAiPreview=true;await page.evaluate(()=>window.__storyWorkspaceTest.open());await page.locator('#story-build').click();
  await page.waitForFunction(()=>document.querySelector('#story-workspace-status')?.textContent.includes('could not be arranged'));
  assert.equal(await page.locator('.story-chapter-card').count(),0,'repeated AI evidence across items is rejected before editor render');
  await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();await page.locator('#story-workspace-close').click();
  pass('Malformed repeated AI evidence is rejected while identical attributed family evidence remains valid');
  await page.waitForFunction(()=>document.querySelectorAll('#saved-memory-list .saved-memory-card').length===8);
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
  await page.locator('#library-select').selectOption('family-a');await page.locator('#grid .asset').first().waitFor();await page.evaluate(()=>window.__storyWorkspaceTest.open(['101','102'],'trip'));await page.locator('#story-workspace').waitFor({state:'visible'});revokeOnNextSessionCheck=true;
  await page.locator('#story-build').evaluate(button=>button.click());await page.waitForFunction(()=>document.querySelector('#library-select')?.value===''&&document.querySelectorAll('#grid .asset').length===0&&document.querySelector('#story-chapter-editor')?.textContent==='');
  assert.equal(await page.locator('#auth').isVisible(),false,'revoked library membership does not leave authenticated UI showing private media');assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),false,'revoked capability clears the private story editor');
  pass('403 capability rechecks membership, rejects revoked access, and ignores stale checks after scope changes');
  assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
  pass('Large album choices remain available, cap is enforced, a later frame reaches the protected API, and choices clear at logout');
  fs.writeFileSync(path.join(artifacts,'checks.json'),JSON.stringify({checks,errors,external,fixture:'synthetic ASGI; Fetch Metadata explicitly modeled',saved_story_shelf_fixture:'synthetic response adapter; backend filtering separately covered by API tests'},null,2));
  console.log('ARTIFACTS '+artifacts);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(ctx)await ctx.close();if(browser)await browser.close();bridge.stdin.end();});
