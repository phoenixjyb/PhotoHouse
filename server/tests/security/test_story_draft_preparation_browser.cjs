'use strict';
/* Browser -> real closed ASGI -> generated SQLite/synthetic provider. No listener. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-selected-draft-'));
fs.mkdirSync(artifacts,{recursive:true,mode:0o700});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'story_draft_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,browser,context,page,held=null,heldCapability=null,corrupt=false,loseSave=false;
const pending=new Map(),checks=[],requests=[],errors=[],external=[],saveBodies=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){readyResolve(value);return;}const call=pending.get(value.id);if(call){pending.delete(value.id);call.resolve(value);}});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
bridge.on('exit',code=>{if(code){readyReject(new Error('Synthetic bridge failed'));for(const call of pending.values())call.reject(new Error('Synthetic bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const pass=name=>{checks.push(name);console.log('PASS '+name);};
const delay=()=>{let done;const promise=new Promise(resolve=>done=resolve);return {promise,done};};
const writes=()=>requests.filter(row=>['POST','PUT'].includes(row.method)&&/^\/memory-stories(?:\?|\/|$)/.test(row.path));
const prepareRows=()=>requests.filter(row=>row.method==='POST'&&row.path.startsWith('/story-workspace/drafts/prepare'));
(async()=>{
 await ready;
 browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
 context=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block'});
 await context.addInitScript(()=>{let factory;Object.defineProperty(window,'PhotoHouseStoryWorkspace',{configurable:true,get:()=>factory,set:value=>{factory=config=>{let language=null;const scope=config.scope;const instance=value({...config,scope:()=>({...scope(),...(language?{language}:{})})});window.__draftTestLanguage=next=>{language=next;instance.translate();};return instance;};}});});
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
  const row={method:request.method(),path:url.pathname+url.search};
  if(url.pathname.startsWith('/story-workspace/')||url.pathname.startsWith('/memory-stories'))row.body=request.postData();
  requests.push(row);
  const headers=await request.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
  const response=await rpc({method:row.method,path:row.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
  row.status=response.status;let status=response.status,body=Buffer.from(response.body,'base64');
  if(url.pathname==='/story-workspace/drafts/prepare'){
   if(corrupt&&status===200){corrupt=false;const payload=JSON.parse(body);payload.chapters[0].citations[0].source_id='foreign-source';body=Buffer.from(JSON.stringify(payload));}
   if(held){const gate=held;held=null;gate.arrived.done();await gate.release.promise;gate.finished.done();}
  }
  if(url.pathname==='/story-workspace/drafts/capabilities'&&heldCapability){const gate=heldCapability;heldCapability=null;gate.arrived.done();await gate.release.promise;}
  if(['POST','PUT'].includes(row.method)&&url.pathname.startsWith('/memory-stories')){
   saveBodies.push(row.body);
   if(loseSave&&status===200){loseSave=false;status=503;body=Buffer.from('{"detail":"Synthetic lost response after commit"}');}
  }
  if(url.pathname.startsWith('/memory-stories')&&status===200)row.responseBody=body.toString('utf8');
  const output={...response.headers};delete output['content-length'];delete output['content-encoding'];
  try{await route.fulfill({status,headers:output,body});}catch(error){if(!/closed|handled|cancel|InterceptionId/i.test(error.message))throw error;}
 });
 page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());
 const signIn=async()=>{await page.goto('https://photohouse.test/ui');await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();};
 const open=async()=>{await page.locator('.memory-theme[data-theme=trip]').click();await page.locator('#story-build').click();await page.locator('.story-chapter-card textarea[maxlength="6000"]').first().waitFor();};
 const words=()=>page.locator('.story-chapter-card textarea[maxlength="6000"]').first();
 const panel=()=>page.locator('.story-draft-preparation');
 const chooseSources=async()=>{
  await page.waitForFunction(()=>document.querySelector('.story-source-opt-in')||document.querySelector('.story-source-choice input[type=checkbox]'));
  const opt=page.locator('.story-source-opt-in').first();if(await opt.count()&&await opt.isVisible())await opt.click();
  const choices=page.locator('.story-source-choice input[type=checkbox]');await choices.first().waitFor();
  for(let i=0;i<await choices.count();i++)await choices.nth(i).uncheck();
  const family=page.locator('.story-source-choice').filter({hasText:'合成家人原话'}).locator('input[type=checkbox]').first();await family.check();
 };
 const prepare=async()=>{await page.locator('.story-draft-prepare').click();await page.waitForFunction(()=>document.querySelector('.story-chapter-card textarea[maxlength="6000"]')?.value.includes('合成整理文字'));};
 await rpc({command:'mutate',scenario:'disable-draft-ui'});await signIn();await open();
 assert.equal(await panel().isVisible(),false);assert.equal(prepareRows().length,0);pass('Default-off hides AI controls and never prepares');
 assert.equal((await rpc({command:'provider-status'})).generation_calls,0);
 await page.locator('#story-workspace-close').click();await rpc({command:'mutate',scenario:'enable-draft-ui'});
 const capabilityGate={arrived:delay(),release:delay()};heldCapability=capabilityGate;await open();await capabilityGate.arrived.promise;
 await words().fill('能力检查期间的家人文字。');await words().focus();const chapterField=await words().elementHandle();capabilityGate.release.done();await panel().waitFor();
 assert.equal(await chapterField.evaluate(node=>node===document.activeElement&&node.isConnected&&node.value==='能力检查期间的家人文字。'),true);
 pass('Delayed capability negotiation preserves focused chapter wording');await chooseSources();
 await words().fill('家人自己写下的原话。');await page.locator('.story-draft-direction').fill('保留家人的说法。');
 const before=writes().length;await prepare();assert.equal(writes().length,before);assert.equal(await page.locator('#story-save-memory').isDisabled(),true);
 const sent=JSON.parse(prepareRows().at(-1).body);assert.equal(sent.selection.source_policy,'chapter_sources_v1');assert.equal(sent.selection.chapters[0].evidence_ids.length,1);assert(sent.selection.chapters[0].evidence_ids[0].startsWith('family-'));assert.equal('sources' in sent,false);assert.equal(sent.author_direction,'保留家人的说法。');
 assert.equal(await page.locator('.story-draft-direction').inputValue(),sent.author_direction);assert.equal(await page.locator('.story-draft-direction').isDisabled(),true);
 pass('Explicit photo/memory choices prepare a review-only draft through protected ASGI');
 await words().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'draft-chapters-desktop-zh.png')});
 const citations=panel().locator('details');if(await citations.count())await citations.first().locator('summary').click();
 assert.match(await panel().textContent(),/合成家人原话/);assert.match(await panel().textContent(),/合成家人/);
 await words().fill('家人核对并修改后的故事。');await page.locator('.story-draft-reviewed').check();assert.equal(await page.locator('#story-save-memory').isDisabled(),false);
 await words().fill('家人核对并再次修改后的故事。');assert.equal(await page.locator('.story-draft-reviewed').isChecked(),false);assert.equal(await page.locator('#story-save-memory').isDisabled(),true);
 await page.locator('.story-draft-reviewed').check();
 assert.equal(await page.locator('#story-export').isDisabled(),true);assert.equal(await page.locator('#story-local-save').isDisabled(),true);
 pass('Citations show original family wording; edits invalidate explicit review');
 await page.locator('.story-draft-preparation').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'draft-editor-desktop-zh.png')});
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.style.fontSize='24px');await panel().scrollIntoViewIfNeeded();
 assert(await page.locator('#story-workspace').evaluate(node=>node.scrollWidth<=node.clientWidth));await page.screenshot({path:path.join(artifacts,'draft-editor-mobile-zh-text150.png')});
 const focusable=page.locator('.story-draft-reviewed');await focusable.focus();await page.keyboard.press('Space');assert.equal(await focusable.isChecked(),false);await page.keyboard.press('Space');
 pass('Chinese phone layout at 150% text and keyboard review control fit');
 loseSave=true;await page.locator('#story-save-memory').click();await page.waitForFunction(()=>document.getElementById('story-save-memory').textContent.includes('重试'));
 await page.evaluate(()=>window.__draftTestLanguage('en'));assert.equal(await words().inputValue(),'家人核对并再次修改后的故事。');await page.evaluate(()=>window.__draftTestLanguage('zh'));assert.equal(await words().inputValue(),'家人核对并再次修改后的故事。');
 await page.locator('#story-save-memory').click();await page.waitForFunction(()=>document.getElementById('story-workspace-status').textContent.includes('已保存'));
 assert.equal(saveBodies.length,2);assert.equal(saveBodies[0],saveBodies[1]);const saved=JSON.parse(saveBodies[0]);assert.equal(saved.source_policy,'chapter_sources_v1');assert.equal(JSON.parse(saved.chapters)[0].narration,'家人核对并再次修改后的故事。');assert.equal('citations' in JSON.parse(saved.chapters)[0],false);
 pass('Only explicit Save writes; a lost save response retries the identical mutation');
 const createResult=JSON.parse(writes().at(-1).responseBody);assert.equal(createResult.saved,true);assert.match(createResult.id,/^[0-9a-f-]{36}$/);assert.equal(createResult.source_policy,'chapter_sources_v1');
 const chosenSourceId=sent.selection.chapters[0].evidence_ids[0];assert(createResult.items.some(item=>item.evidence.some(evidence=>evidence.id===chosenSourceId&&evidence.source==='family')));
 const savesBeforeReopen=saveBodies.length,preparesBeforeReopen=prepareRows().length;
 await page.locator('#story-workspace-close').click();await page.locator('#saved-memory-list .saved-memory-card button').first().waitFor();
 await page.locator('#saved-memory-list .saved-memory-card button').first().click();await page.locator('#story-reader').waitFor({state:'visible'});
 await page.waitForFunction(()=>document.querySelector('#story-reader')?.open===true&&document.querySelector('#story-reader-text')?.textContent==='家人核对并再次修改后的故事。');
 const reopenedRequest=requests.find(row=>{if(row.method!=='GET'||!row.path.startsWith(`/memory-stories/${createResult.id}?`))return false;const query=new URLSearchParams(row.path.split('?')[1]);return query.get('source_review')==='1'&&query.get('library')==='family-a';});assert(reopenedRequest);const reopened=JSON.parse(reopenedRequest.responseBody);
 assert.equal(reopened.saved,true);assert.equal(reopened.source_policy,'chapter_sources_v1');assert.equal(reopened.chapters[0].narration,'家人核对并再次修改后的故事。');
 assert(reopened.chapters[0].evidence_ids.includes(chosenSourceId));assert(reopened.items.some(item=>item.evidence.some(evidence=>evidence.id===chosenSourceId&&evidence.source==='family')));
 const reopenedSources=page.locator('#story-reader .story-reader-sources');await reopenedSources.locator('summary').click();assert.match(await reopenedSources.textContent(),/合成家人原话/);
 assert.equal(saveBodies.length,savesBeforeReopen);assert.equal(prepareRows().length,preparesBeforeReopen);
 pass('The exact saved story reopens with edited wording and current authorized evidence, without another prepare or save');
 await page.locator('#story-reader-close').click();await open();await chooseSources();await words().fill('取消前保留的家人文字。');
 const gate={arrived:delay(),release:delay(),finished:delay()};held=gate;await page.locator('.story-draft-prepare').click();await gate.arrived.promise;await page.locator('.story-draft-cancel').click();gate.release.done();await gate.finished.promise;await page.waitForTimeout(100);
 assert.equal(await words().inputValue(),'取消前保留的家人文字。');assert.equal(await page.locator('.story-draft-reviewed').isChecked(),false);assert.equal(await page.locator('.story-draft-reviewed').isDisabled(),true);pass('Cancel fences late replies and preserves prior family wording');
 corrupt=true;await page.locator('.story-draft-prepare').click();await page.locator('.story-draft-retry:visible').waitFor();
 assert.equal(await words().inputValue(),'取消前保留的家人文字。');assert.equal(await words().isDisabled(),true);assert.equal(await page.locator('#story-save-memory').isDisabled(),true);
 const frozenPrepare=prepareRows().at(-1).body;await page.locator('.story-draft-retry').click();await page.waitForFunction(()=>document.querySelector('.story-chapter-card textarea[maxlength="6000"]')?.value.includes('合成整理文字'));
 assert.equal(prepareRows().at(-1).body,frozenPrepare);pass('Foreign citations are rejected; explicit retry freezes the exact request and prior wording');
 await page.locator('.story-source-choice').filter({hasText:'合成家人原话'}).locator('input[type=checkbox]').first().uncheck();
 assert.equal(await words().inputValue(),'取消前保留的家人文字。');assert.equal(await page.locator('.story-draft-reviewed').isDisabled(),true);
 assert.equal(await page.locator('.story-draft-prose-origin').count(),0);pass('Changing selected memories clears generated words and restores the earlier draft');
 await chooseSources();await prepare();const abandonedId=JSON.parse(prepareRows().at(-1).body).request_id;
 await page.locator('#story-build').click();await page.waitForFunction(()=>!document.querySelector('.story-draft-prose-origin')&&document.querySelector('.story-source-opt-in'));
 assert(requests.some(row=>row.path.startsWith('/story-workspace/drafts/cancel')&&JSON.parse(row.body).request_id===abandonedId));
 await chooseSources();await words().fill('取消前保留的家人文字。');pass('Replacing the outline retires its AI proposal and cancels the registered result');
 await rpc({command:'mutate',scenario:'expire-draft-result'});await prepare();await page.locator('#story-preview').click();await page.locator('#story-reader .story-draft-prose-origin').waitFor();
 await page.waitForFunction(()=>!document.getElementById('story-reader').open&&document.querySelector('.story-chapter-card textarea[maxlength="6000"]')?.value==='取消前保留的家人文字。',null,{timeout:5000});
 pass('Fixed expiry clears the open AI preview and restores the prior draft');
 await page.evaluate(()=>window.__draftTestLanguage('en'));await page.evaluate(()=>document.documentElement.style.fontSize='24px');await panel().waitFor();await panel().scrollIntoViewIfNeeded();assert(await page.locator('#story-workspace').evaluate(node=>node.scrollWidth<=node.clientWidth));await page.screenshot({path:path.join(artifacts,'draft-editor-mobile-en-text150.png')});pass('English phone controls remain readable at 150% text');
 const writesBeforeConflict=writes().length;await rpc({command:'mutate',scenario:'change-family-source',text:'合成家人修订后的原话。'});await page.locator('.story-draft-prepare').click();
 await page.waitForFunction(()=>document.querySelector('.story-draft-status')?.textContent.includes('Selected sources or story revision changed'));
 assert.equal(await words().inputValue(),'取消前保留的家人文字。');assert.equal(await page.locator('.story-draft-prepare').isDisabled(),true);assert.equal(writes().length,writesBeforeConflict);
 pass('A changed server source requires fresh source review and never applies or saves stale wording');
 await page.locator('#story-workspace-close').click();await page.locator('#logout').click();await page.locator('#auth').waitFor();assert.equal(await page.locator('.story-draft-preparation:visible').count(),0);
 assert.deepEqual(external,[]);assert.deepEqual(errors,[]);pass('Logout clears protected content; no external request or browser error');
 const providerStatus=await rpc({command:'provider-status'});assert(providerStatus.generation_calls>0);assert.equal(providerStatus.cleanup_calls,providerStatus.generation_calls);assert.equal(providerStatus.http_closed,providerStatus.generation_calls);assert.equal(providerStatus.active,0);assert.equal(providerStatus.native_model,false);assert.equal(providerStatus.transport,'synthetic-in-memory');
 pass('The async local adapter uses only mocked HTTP and reconciles every synthetic generation');
 delete providerStatus.id;
 fs.writeFileSync(path.join(artifacts,'checks.json'),JSON.stringify({checks,errors,external,prepare_requests:prepareRows().length,explicit_save_requests:saveBodies.length,provider_status:providerStatus,fixture:'Generated SQLite, synthetic local transport/native owner, real protected ASGI'},null,2));console.log('ARTIFACTS '+artifacts);
})().catch(async error=>{console.error(error);process.exitCode=1;fs.writeFileSync(path.join(artifacts,'checks.json'),JSON.stringify({status:'failed',checks,error:String(error),errors,external},null,2));try{await page?.screenshot({path:path.join(artifacts,'failure.png')});}catch(_){}}).finally(async()=>{try{await context?.close();await browser?.close();}finally{bridge.stdin.end();}});
