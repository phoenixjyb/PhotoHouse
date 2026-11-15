"use strict";
/* Browser -> actual protected ASGI -> synthetic SQLite. No HTTP listener or model. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..'),artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-related-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,browser,ctx,hold=null,holdAppend=null,corrupt=false,fail=false,failAppend=false;const pending=new Map(),errors=[],external=[],checks=[],requests=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready)readyResolve();else{const item=pending.get(value.id);if(item){pending.delete(value.id);item.resolve(value);}}});
bridge.stderr.on('data',v=>process.stderr.write(v));bridge.on('exit',code=>{if(code){readyReject(new Error('Bridge failed'));for(const item of pending.values())item.reject(new Error('Bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const pass=name=>{checks.push(name);console.log('PASS '+name);};
(async()=>{
 await ready;await rpc({command:'mutate',scenario:'many-assets'});await rpc({command:'mutate',scenario:'related-day-seed'});browser=await chromium.launch({headless:true,executablePath:process.env.PH_BROWSER_EXECUTABLE,args:['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND']});
 ctx=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block'});
 await ctx.addInitScript(()=>{let factory;Object.defineProperty(window,'PhotoHouseStoryWorkspace',{configurable:true,get:()=>factory,set:value=>{factory=config=>{let language=null;const original=config.scope;const instance=value({...config,scope:()=>({...original(),...(language?{language}:{})})});window.__relatedTest=instance;window.__relatedLanguage=value=>{language=value;instance.translate();};return instance;};}});});
 await ctx.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
  requests.push({method:req.method(),path:url.pathname,body:req.postData()});const headers=await req.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
  const result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
  let body=Buffer.from(result.body,'base64'),status=result.status,complete=null;
  if(url.pathname==='/story-workspace/related-media'){
   if(hold){const gate=hold;hold=null;gate.arrive();await gate.wait;complete=gate.complete;}
   if(corrupt){const value=JSON.parse(body);if(corrupt==='date')value.items[0].taken_at+='garbage';else value.items[0].thumbnail_url='/assets/201/thumbnail?library=family-b';body=Buffer.from(JSON.stringify(value));corrupt=false;}
   if(fail){fail=false;status=503;body=Buffer.from('{"detail":"Related moments unavailable"}');}
  }
  if(url.pathname==='/story-workspace/preview'){
   if(holdAppend){const gate=holdAppend;holdAppend=null;gate.arrive();await gate.wait;}
   if(failAppend){failAppend=false;status=503;body=Buffer.from('{"detail":"Frame preview unavailable"}');}
  }
  const output={...result.headers};delete output['content-length'];delete output['content-encoding'];try{await route.fulfill({status,headers:output,body});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/i.test(error.message))throw error;}finally{complete?.();}
 });
 const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await page.goto('https://photohouse.test/ui');await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();

 const open=async()=>{await page.evaluate(()=>window.__relatedTest.open(['101'],'trip'));await page.locator('#story-workspace').waitFor();await page.locator('#story-related summary').click();};
 const find=page.locator('#story-related-find'),rows=page.locator('.story-related-card');
 await open();assert.equal(requests.filter(r=>r.path==='/story-workspace/related-media').length,0);
 await find.click();await rows.first().waitFor();assert.equal(await rows.count(),20);
 assert.deepEqual(await rows.locator('button').evaluateAll(nodes=>nodes.map(n=>n.dataset.relatedId)),Array.from({length:20},(_,i)=>String(1129-i)));
 assert.match(await rows.first().textContent(),/▶/);assert.match(await page.locator('#story-selection-count').textContent(),/^1 \/ 24/);
 assert.equal(await rows.locator('[data-related-id="102"]').count(),0);assert.equal(await rows.locator('[data-related-id="101"]').count(),0);
 pass('Explicit lookup returns bounded mixed-media same-day candidates, excludes seed and filename-only dates, selects nothing');
 const mediaFilter=page.locator('#story-related-media');
 let arriveFilter,releaseFilter,completeFilter;
 const filterReached=new Promise(resolve=>arriveFilter=resolve),filterSettled=new Promise(resolve=>completeFilter=resolve);
 hold={arrive:arriveFilter,wait:new Promise(resolve=>releaseFilter=resolve),complete:completeFilter};
 await mediaFilter.selectOption('image');await filterReached;
 try{
  await mediaFilter.selectOption('video');
  await page.waitForFunction(()=>document.querySelectorAll('.story-related-card').length===1&&document.querySelector('.story-related-card button')?.dataset.relatedId==='1129');
 }finally{releaseFilter();}
 await filterSettled;
 assert.deepEqual(await rows.locator('button').evaluateAll(nodes=>nodes.map(node=>node.dataset.relatedId)),['1129']);
 assert.equal(await page.locator('#story-related-more').isHidden(),true);
 await mediaFilter.selectOption('image');
 await page.waitForFunction(()=>document.querySelector('.story-related-card button')?.dataset.relatedId==='1128');
 assert.equal(await rows.locator('[data-related-id="1129"]').count(),0);
 assert.match(await page.locator('#story-selection-count').textContent(),/^1 \/ 24/);
 await mediaFilter.selectOption('all');
 await page.waitForFunction(()=>document.querySelector('.story-related-card button')?.dataset.relatedId==='1129');
 pass('Photo and video filters restart same-day paging and ignore a late result from the previous filter');
 await page.locator('#story-related-more').click();await page.waitForFunction(()=>document.querySelector('.story-related-card button')?.dataset.relatedId==='1109');assert.equal(await rows.count(),9);assert.equal(await page.locator('#story-related-more').isVisible(),false);
 await find.click();await page.waitForFunction(()=>document.querySelector('.story-related-card button')?.dataset.relatedId==='1129');
 await page.screenshot({path:path.join(artifacts,'related-moments-desktop-zh.png'),fullPage:true});
 await rows.locator('[data-related-id="1129"]').click();assert.match(await page.locator('#story-selection-count').textContent(),/^2 \/ 24/);assert.equal(await rows.locator('[data-related-id="1129"]').isDisabled(),true);
 const built=page.waitForResponse(r=>new URL(r.url()).pathname==='/story-workspace/preview');await page.locator('#story-build').click();assert.equal((await built).status(),200);await page.locator('.story-chapter-card textarea').first().waitFor();
 assert.equal(JSON.parse(requests.filter(r=>r.path==='/story-workspace/preview').at(-1).body).asset_ids,'101,1129');
 assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/memory-stories').length,0);pass('Cursor pagination advances; explicit inclusion preserves seed order and reloads evidence without saving');
 const prose='家人亲口讲述的回忆，保留我们的原话。';await page.locator('.story-chapter-card textarea').first().fill(prose);
 corrupt=true;await find.click();await page.waitForFunction(()=>document.querySelector('#story-related-status').textContent.includes('暂时'));assert.equal(await rows.count(),0);assert.equal(await page.locator('.story-chapter-card textarea').first().inputValue(),prose);
 corrupt='date';await find.click();await page.waitForFunction(()=>document.querySelector('#story-related-status').textContent.includes('暂时'));assert.equal(await rows.count(),0);assert.equal(await page.locator('.story-chapter-card textarea').first().inputValue(),prose);
 fail=true;await find.click();await page.waitForFunction(()=>!document.querySelector('#story-related-find').disabled);assert.equal(await page.locator('.story-chapter-card textarea').first().inputValue(),prose);assert.match(await page.locator('#story-selection-count').textContent(),/^2 \/ 24/);pass('Malformed date, foreign-library response and transient failure preserve edited prose and selection');
 await find.click();await rows.first().waitFor();
 const title=page.locator('#story-workspace-title'),chapterTitle=page.locator('.story-chapter-card label input').first(),narration=page.locator('.story-chapter-card textarea[maxlength="6000"]').first();
 await title.fill('同一天的家人回忆');await chapterTitle.fill('记得那一天');
 const appendCandidate=rows.locator('button:enabled').first(),appendId=await appendCandidate.getAttribute('data-related-id');
 const candidateThumb=await appendCandidate.evaluateHandle(button=>button.closest('article').querySelector('img'));
 await candidateThumb.evaluate(img=>{img.loading='eager';});
 await page.waitForFunction(img=>img.complete,candidateThumb);
 const candidateRequests=()=>requests.filter(request=>request.path===`/assets/${appendId}/thumbnail`).length;
 const beforeFailedAppend=candidateRequests();
 failAppend=true;await appendCandidate.click();
 await page.waitForFunction(()=>document.querySelector('#story-related-status').textContent.includes('暂时无法添加'));
 assert.equal(await candidateThumb.evaluate(img=>img.isConnected),true,'a failed add keeps the existing thumbnail node');
 assert.equal(candidateRequests(),beforeFailedAppend,'retry feedback does not download the same candidate thumbnail');
 assert.equal(await appendCandidate.evaluate(button=>button===document.activeElement),true,'a failed add returns focus to the same frame');
 assert.equal(await narration.inputValue(),prose);assert.match(await page.locator('#story-selection-count').textContent(),/^2 \/ 24/);
 let arriveAppend,releaseAppend;
 const appendReached=new Promise(resolve=>arriveAppend=resolve);
 holdAppend={arrive:arriveAppend,wait:new Promise(resolve=>releaseAppend=resolve)};
 await appendCandidate.click();await appendReached;
 try{
  assert.equal(await rows.locator('button:enabled').count(),0,'a pending add prevents a duplicate click or concurrent add');
  assert.equal(await candidateThumb.evaluate(img=>img.isConnected),true,'the candidate stays visible during validation');
  await narration.fill(prose+' 我们还记得当时的笑声。');
  await narration.evaluate(node=>node.setSelectionRange(4,9));
 }finally{releaseAppend();}
 await page.waitForFunction(()=>document.querySelector('#story-selection-count').textContent.startsWith('3 / 24'));
 assert.equal(JSON.parse(requests.filter(r=>r.path==='/story-workspace/preview').at(-1).body).asset_ids,`101,1129,${appendId}`);
 assert.equal(await title.inputValue(),'同一天的家人回忆');assert.equal(await chapterTitle.inputValue(),'记得那一天');
 assert.equal(await narration.inputValue(),prose+' 我们还记得当时的笑声。');
 assert.deepEqual(await narration.evaluate(node=>[document.activeElement===node,node.selectionStart,node.selectionEnd]),[true,4,9]);
 assert.equal(await rows.locator('[data-related-id="'+appendId+'"]').isDisabled(),true);
 assert.equal(await candidateThumb.evaluate(img=>img.isConnected),true,'adding a frame keeps the same recommendation page');
 await candidateThumb.dispose();
 assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/memory-stories').length,0);
 pass('Appending a same-day result preserves live draft edits and order after a retry without saving');
 pass('Frame checks, failed adds and success preserve visible candidate thumbnails and keep retry keyboard focus');
 const undo=page.locator('#story-undo-frames'),beforeUndo=requests.filter(r=>r.path==='/story-workspace/preview').length;
 await page.setViewportSize({width:390,height:844});await page.locator('#story-workspace').evaluate(el=>el.style.fontSize='150%');
 assert.equal(await undo.isVisible(),true);
 assert.equal(await page.locator('.story-selection-actions').evaluate(el=>el.scrollWidth<=el.clientWidth),true);
 await undo.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'related-undo-mobile-150.png')});
 await page.setViewportSize({width:1280,height:960});await page.locator('#story-workspace').evaluate(el=>el.style.fontSize='');
 await undo.click();
 assert.match(await page.locator('#story-selection-count').textContent(),/^2 \/ 24/);
 assert.deepEqual(await page.locator('#story-selection input:checked').evaluateAll(nodes=>nodes.map(node=>node.value)),['101','1129']);
 assert.equal(await title.inputValue(),'同一天的家人回忆');assert.equal(await chapterTitle.inputValue(),'记得那一天');
 assert.equal(await narration.inputValue(),prose+' 我们还记得当时的笑声。');
 assert.equal(requests.filter(r=>r.path==='/story-workspace/preview').length,beforeUndo,'undo restores the verified in-memory draft');
 await find.click();await rows.locator('[data-related-id="'+appendId+'"]').click();
 await undo.waitFor({state:'visible'});
 await narration.fill('添加画面后写下的故事。');assert.equal(await undo.isHidden(),true,'undo expires after a later edit');
 assert.match(await page.locator('#story-selection-count').textContent(),/^3 \/ 24/);
 assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/memory-stories').length,0);
 pass('Undo last add restores the earlier frame order and draft, and later wording edits expire the undo');
 await page.setViewportSize({width:390,height:844});await page.locator('#story-workspace').evaluate(el=>el.style.fontSize='150%');
 for(const sel of ['#story-related','#story-related-media','.story-related-items','.story-related-card'])assert(await page.locator(sel).first().evaluate(el=>el.scrollWidth<=el.clientWidth),sel+' fits at enlarged text');
 await page.locator('#story-related').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'related-moments-mobile-zh.png')});
 await page.evaluate(()=>window.__relatedLanguage('en'));assert.equal(await find.textContent(),'Find moments from these days');await page.screenshot({path:path.join(artifacts,'related-moments-mobile-en.png')});pass('Chinese and English picker render at 390px with 150 percent text');
 await page.setViewportSize({width:1280,height:960});await page.locator('#story-workspace').evaluate(el=>el.style.fontSize='');
 await page.evaluate(()=>window.__relatedTest.open(['101','102'],'trip'));
 await page.locator('#story-build').click();await page.locator('.story-source-opt-in').first().click();
 await page.locator('.story-chapter-split').first().click();
 const chapters=page.locator('.story-chapter-card'),chapterFilter=page.locator('#story-related-chapter');
 assert.equal(await chapters.count(),2);
 await chapters.nth(0).locator('textarea[maxlength="6000"]').fill('Our words from the first chapter');
 await chapters.nth(1).locator('textarea[maxlength="6000"]').fill('Our words from the next chapter');
 if(!await page.locator('#story-related').evaluate(el=>el.open))await page.locator('#story-related summary').click();
 assert.equal(await chapterFilter.inputValue(),'all','all selected capture days remain the default');
 await chapterFilter.selectOption('chapter-1');await mediaFilter.selectOption('video');
 await find.click();const chapterCandidate=rows.locator('[data-related-id="1129"]');await chapterCandidate.waitFor();
 const lastRelated=()=>JSON.parse(requests.filter(r=>r.path==='/story-workspace/related-media').at(-1).body);
 assert.equal(lastRelated().asset_ids,'101','only the chosen chapter supplies the recorded date seeds');
 assert.equal(await chapterCandidate.textContent(),'Add to chapter');
 await page.setViewportSize({width:390,height:844});await page.locator('#story-workspace').evaluate(el=>el.style.fontSize='150%');
 assert(await chapterFilter.evaluate(el=>el.scrollWidth<=el.clientWidth),'the chapter filter fits at enlarged phone text');
 await chapterFilter.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'chapter-related-mobile-150-en.png')});
 await page.evaluate(()=>window.__relatedLanguage('zh'));await page.screenshot({path:path.join(artifacts,'chapter-related-mobile-150-zh.png')});
 await page.evaluate(()=>window.__relatedLanguage('en'));
 await page.setViewportSize({width:1280,height:960});await page.locator('#story-workspace').evaluate(el=>el.style.fontSize='');
 await chapterCandidate.click();await page.waitForFunction(()=>document.querySelector('#story-selection-count').textContent.startsWith('3 / 24'));
 assert.equal(await chapterCandidate.textContent(),'Added','the open chapter picker keeps the result page after adding');
 assert.deepEqual(await chapters.evaluateAll(cards=>cards.map(card=>[...card.querySelectorAll('.story-chapter-strip img')].map(img=>img.alt))),[['101','1129'],['102']]);
 assert.deepEqual(await chapters.locator('textarea[maxlength="6000"]').evaluateAll(nodes=>nodes.map(node=>node.value)),['Our words from the first chapter','Our words from the next chapter']);
 let oldChapterArrive,oldChapterRelease,oldChapterComplete;
 const oldChapterReached=new Promise(resolve=>oldChapterArrive=resolve),oldChapterFinished=new Promise(resolve=>oldChapterComplete=resolve);
 hold={arrive:oldChapterArrive,wait:new Promise(resolve=>oldChapterRelease=resolve),complete:oldChapterComplete};
 await find.click();await oldChapterReached;
 try{
  await chapterFilter.selectOption('chapter-2');
  await page.waitForFunction(()=>document.querySelector('#story-related-status').textContent.startsWith('No other moments found'));
  assert.equal(lastRelated().asset_ids,'102','chapter changes start a fresh lookup with the new chapter only');
 }finally{oldChapterRelease();}
 await oldChapterFinished;assert.equal(await rows.count(),0);
 await mediaFilter.selectOption('all');await page.waitForFunction(()=>!document.querySelector('#story-related-find').disabled);
 assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/memory-stories').length,0);
 pass('Same-day suggestions can match and add within one chapter, preserve both narrations and ignore a delayed result from another chapter');
 async function late(edit){let arrive,release,complete;const reached=new Promise(r=>arrive=r),wait=new Promise(r=>release=r),finished=new Promise(r=>complete=r);hold={arrive,wait,complete};await find.click();await reached;await edit();release();await finished;assert.equal(await rows.count(),0);}
 await late(()=>page.locator('#story-selection-clear').click());assert.match(await page.locator('#story-selection-count').textContent(),/^0 \/ 24/);pass('A selection change invalidates a late response');
 await page.locator('#story-workspace-close').click();await page.evaluate(()=>window.__relatedTest.open(Array.from({length:29},(_,i)=>String(1101+i)),'trip'));if(!(await page.locator('#story-related').evaluate(el=>el.open)))await page.locator('#story-related summary').click();
 await find.click();await rows.first().waitFor();assert.equal(await rows.locator('button:enabled').count(),0);pass('Selection limit disables all candidate additions');
 await late(async()=>{await page.locator('#story-workspace-close').click();await page.locator('#logout').click();await page.locator('#auth').waitFor();});
 assert.equal(await page.locator('#story-selection img').count(),0);assert.equal(await page.locator('#story-chapter-editor').textContent(),'');assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);pass('Logout clears candidate media; late response cannot repopulate private UI; zero external requests or browser errors');
 fs.writeFileSync(path.join(artifacts,'checks.json'),JSON.stringify({checks,errors,external,fixture:'Actual ASGI with synthetic assets; no inference'},null,2));console.log('ARTIFACTS '+artifacts);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(ctx)await ctx.close();if(browser)await browser.close();bridge.stdin.end();});
