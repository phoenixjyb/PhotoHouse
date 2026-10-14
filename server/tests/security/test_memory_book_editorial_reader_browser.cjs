'use strict';
/* Protected synthetic editorial reading; no listener or household connection. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-editorial-reader-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'memory_book_editorial_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,resolveReady,rejectReady,bookId,csrfToken,sessionCookie,cookieName;const pending=new Map();
const ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){bookId=value.book_id;csrfToken=value.csrf_token;sessionCookie=value.session_cookie;cookieName=value.cookie_name;resolveReady();return;}const item=pending.get(value.id);if(item){pending.delete(value.id);item.resolve(value);}});
bridge.on('exit',code=>{if(code){rejectReady(new Error('Synthetic bridge failed'));for(const item of pending.values())item.reject(new Error('Synthetic bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
let browser,context,page,holdEditorial=null,holdRefs=null,overrideEditorial=null,overrideParent=false,overrideChild=false,editorialStatusOverride=null,refsStatusOverride=null;const requests=[],errors=[],checks=[];
const pass=name=>{checks.push(name);console.log('PASS '+name);};
const html=fs.readFileSync(path.join(root,'backend/app/ui/access/index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
(async()=>{
 await ready;
 browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
 context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block'});
 await context.addCookies([{name:cookieName,value:sessionCookie,url:'https://photohouse.test/',httpOnly:true,secure:true,sameSite:'Strict'}]);
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());if(url.origin!=='https://photohouse.test'){await route.abort();return;}
  if(url.pathname==='/'){await route.fulfill({status:200,contentType:'text/html',body:html});return;}
  requests.push({method:req.method(),path:url.pathname+url.search});
  const result=await rpc({method:req.method(),path:url.pathname+url.search,headers:await req.allHeaders(),body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
  let body=Buffer.from(result.body,'base64');
  if(req.method()==='GET'&&url.pathname==='/memory-community/v1/books/'+bookId&&overrideParent){overrideParent=false;const dto=JSON.parse(body);dto.stories[1].revision=String(BigInt(dto.stories[1].revision)+1n);body=Buffer.from(JSON.stringify(dto));}
  if(req.method()==='GET'&&/^\/memory-stories\/[0-9a-f-]+$/.test(url.pathname)&&overrideChild){overrideChild=false;const dto=JSON.parse(body);dto.revision=String(BigInt(dto.revision)+1n);body=Buffer.from(JSON.stringify(dto));}
  if(req.method()==='GET'&&url.pathname.endsWith('/contribution-refs')&&holdRefs){const hold=holdRefs;holdRefs=null;hold.arrive();await hold.release;}
  if(req.method()==='GET'&&url.pathname.endsWith('/editorial')&&overrideEditorial){const transform=overrideEditorial;overrideEditorial=null;body=Buffer.from(JSON.stringify(transform(JSON.parse(body))));}
  if(req.method()==='GET'&&url.pathname.endsWith('/editorial')&&holdEditorial){const hold=holdEditorial;holdEditorial=null;hold.arrive();await hold.release;}
  let responseStatus=result.status;
  if(req.method()==='GET'&&url.pathname.endsWith('/editorial')&&editorialStatusOverride!==null)responseStatus=editorialStatusOverride;
  if(req.method()==='GET'&&url.pathname.endsWith('/contribution-refs')&&refsStatusOverride!==null){responseStatus=refsStatusOverride;refsStatusOverride=null;}
  try{await route.fulfill({status:responseStatus,contentType:result.content_type||'application/json',body});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
 });
 page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
 await page.goto('https://photohouse.test/');await page.addStyleTag({content:fs.readFileSync(path.join(root,'backend/app/ui/access/styles.css'),'utf8')+'\n:root{font-size:150%}'});
 await page.addScriptTag({content:fs.readFileSync(path.join(root,'backend/app/ui/access/story-workspace.js'),'utf8')});
 await page.evaluate(async ({id,csrf})=>{
  window.__scope={account:'synthetic-owner',library:'family-a',language:'zh',locked:false};window.__errors=[];window.__editorialResponses=0;
  window.__request=async(p,options={})=>{const u=new URL(p,location.href);u.searchParams.set('library','family-a');const response=await fetch(u.pathname+u.search,{method:options.method||'GET',headers:{'Content-Type':'application/json','Sec-Fetch-Site':'same-origin','X-CSRF-Token':csrf},...(options.body===undefined?{}:{body:JSON.stringify(options.body)})});if(!response.ok){const error=new Error('Synthetic request failed '+response.status+': '+await response.text());error.status=response.status;throw error;}const result=await response.json();if(u.pathname.endsWith('/editorial'))window.__editorialResponses++;return result;};
  window.__book=await window.__request('/memory-community/v1/books/'+id);
  window.__createEditorial=async()=>{
   const book=window.__book,refs=[];
   for(const story of book.stories){const dto=await window.__request('/memory-stories/'+story.id+'/contribution-refs?revision='+story.revision);const group=dto.chapters.find(chapter=>chapter.contribution_ids.length);refs.push({story_id:story.id,story_revision:story.revision,chapter_id:group.id,contribution_id:group.contribution_ids[0]});}
   await window.__request('/memory-community/v1/books/'+id+'/editorial',{method:'PUT',body:{version:1,revision:book.revision,mutation_id:crypto.randomUUID(),children:book.stories.map(story=>({story_id:story.id,revision:story.revision})),introduction_source_refs:[refs[0]],transitions:[{left_story_id:book.stories[0].id,right_story_id:book.stories[1].id,text:'从那次相聚，到下一段旅程，我们把家人的声音留在故事之间。',source_refs:[refs[1]]}]}});
   window.__book=await window.__request('/memory-community/v1/books/'+id);
  };
  window.__workspace=window.PhotoHouseStoryWorkspace({scope:()=>window.__scope,request:window.__request,savedRequest:window.__request,mediaURL:()=>'/synthetic-preview',openAsset:()=>{},openAssistant:()=>{},onError:error=>window.__errors.push(error.status||error.message)});
  window.__workspace.openBook(window.__book);
 },{id:bookId,csrf:csrfToken});
 const reader=page.locator('#memory-book-reader');await reader.waitFor({state:'visible'});
 await page.waitForFunction(()=>window.__editorialResponses>=1);
 const memoirFontGroup=reader.getByRole('group',{name:'阅读字号'}),introduction=reader.locator('.memory-book-introduction'),introBase=parseFloat(await introduction.evaluate(node=>getComputedStyle(node).fontSize));
 const memoirStandard=memoirFontGroup.getByRole('button',{name:'标准'}),memoirLarger=memoirFontGroup.getByRole('button',{name:'较大'}),memoirSmaller=memoirFontGroup.getByRole('button',{name:'较小'});
 assert(await memoirFontGroup.isVisible(),'memoir exposes one named text-size group outside its replaceable chapter pane');assert.equal(await memoirStandard.getAttribute('aria-pressed'),'true');
 assert(await memoirFontGroup.locator('button').evaluateAll(nodes=>nodes.every(node=>node.getBoundingClientRect().width>=48&&node.getBoundingClientRect().height>=48)),'memoir font presets have48px targets at390px/150%');
 const fontRequestsBefore=requests.length,bookHeadingSize=parseFloat(await reader.locator('#memory-book-reader-title').evaluate(node=>getComputedStyle(node).fontSize));
 await memoirLarger.focus();const focusBefore=await memoirLarger.evaluate(node=>node===document.activeElement),scrollBefore=await reader.evaluate(node=>node.scrollTop);await memoirLarger.click();
 assert(Math.abs(parseFloat(await introduction.evaluate(node=>getComputedStyle(node).fontSize))/introBase-1.25)<.01,'memoir introduction uses the1.25 prose scale');assert.equal(await memoirLarger.evaluate(node=>node===document.activeElement),focusBefore);assert.equal(await reader.evaluate(node=>node.scrollTop),scrollBefore);assert.equal(requests.length,fontRequestsBefore,'changing reading size sends no request');
 assert.equal(parseFloat(await reader.locator('#memory-book-reader-title').evaluate(node=>getComputedStyle(node).fontSize)),bookHeadingSize,'memoir title stays outside the prose scale');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Chinese memoir preset fits390px at150%');
 await memoirSmaller.click();assert(Math.abs(parseFloat(await introduction.evaluate(node=>getComputedStyle(node).fontSize))/introBase-.9)<.01,'memoir Smaller uses the0.9 scale');await memoirStandard.click();assert(Math.abs(parseFloat(await introduction.evaluate(node=>getComputedStyle(node).fontSize))/introBase-1)<.01,'memoir Standard restores the base size');
 await memoirLarger.click();await reader.screenshot({path:path.join(artifacts,'memoir-font-presets-zh-390-150.png')});
 await page.evaluate(()=>{window.__scope.language='en';window.__workspace.translate();});
 const englishMemoirFontGroup=reader.getByRole('group',{name:'Reading size'}),englishMemoirLarger=englishMemoirFontGroup.getByRole('button',{name:'Larger'});
 assert.equal(await englishMemoirLarger.getAttribute('aria-pressed'),'true','live memoir translation preserves the selected preset');assert(Math.abs(parseFloat(await introduction.evaluate(node=>getComputedStyle(node).fontSize))/introBase-1.25)<.01,'memoir introduction remains enlarged across live translation');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'English named controls fit390px at150%');await reader.screenshot({path:path.join(artifacts,'memoir-font-presets-en-390-150.png')});
 await page.evaluate(()=>{window.__scope.language='zh';window.__workspace.translate();});
 assert.equal(await reader.locator('.memory-book-editorial-reading-status').count(),0);assert.equal(await reader.locator('.memory-book-introduction-sources details').count(),0);
 pass('First-time empty editorial sidecar is accepted without an unavailable warning');
 await reader.locator('header button').click();await page.evaluate(async()=>{await window.__createEditorial();window.__workspace.openBook(window.__book);});
 await reader.locator('.memory-book-introduction-sources details').waitFor({state:'attached'});
 const replacementFontGroup=reader.getByRole('group',{name:'阅读字号'});assert.equal(await replacementFontGroup.getByRole('button',{name:'标准'}).getAttribute('aria-pressed'),'true','opening the replacement memoir resets to Standard');
 assert.equal(requests.filter(item=>/\/contributions\/[^/]+\?/.test(item.path)).length,0,'loading citations fetches no original contribution detail');
 await reader.locator('.memory-book-toc button').nth(1).click();
 await reader.locator('.memory-book-editorial-reading-transition').waitFor();
 assert.match(await reader.locator('.memory-book-editorial-reading-transition').textContent(),/从那次相聚/);
 const transitionProse=reader.locator('.memory-book-editorial-reading-transition .memory-book-reading-prose'),transitionBase=parseFloat(await transitionProse.evaluate(node=>getComputedStyle(node).fontSize));
 const transitionTitleSize=parseFloat(await reader.locator('.memory-book-editorial-reading-transition .eyebrow').evaluate(node=>getComputedStyle(node).fontSize));
 const transitionLarger=replacementFontGroup.getByRole('button',{name:'较大'});await transitionLarger.click();
 assert(Math.abs(parseFloat(await transitionProse.evaluate(node=>getComputedStyle(node).fontSize))/transitionBase-1.25)<.01,'the between-story transition follows the selected prose scale');
 assert.equal(parseFloat(await reader.locator('.memory-book-editorial-reading-transition .eyebrow').evaluate(node=>getComputedStyle(node).fontSize)),transitionTitleSize,'transition label stays outside the prose scale');
 const nextChildStoryTitle=await page.evaluate(()=>window.__book.stories[1].title),firstChildStoryTitle=await page.evaluate(()=>window.__book.stories[0].title);
 await reader.locator('.memory-book-reading-controls button').first().click();await page.waitForFunction(title=>document.querySelector('#memory-book-reader .memory-book-reading h3')?.textContent===title,firstChildStoryTitle);
 assert.equal(await transitionLarger.getAttribute('aria-pressed'),'true','crossing to the previous child story retains the book reading size');
 await reader.locator('.memory-book-reading-controls button').nth(1).click();await page.waitForFunction(title=>document.querySelector('#memory-book-reader .memory-book-reading h3')?.textContent===title,nextChildStoryTitle);
 assert.equal(await transitionLarger.getAttribute('aria-pressed'),'true','crossing to the next child story retains the book reading size');
 assert(Math.abs(parseFloat(await reader.locator('.memory-book-reading-prose').last().evaluate(node=>getComputedStyle(node).fontSize))/transitionBase-1.25)<.01,'the selected memoir scale survives chapter-pane replacement');
 assert(await page.evaluate(()=>document.querySelector('#memory-book-reader').scrollWidth<=document.querySelector('#memory-book-reader').clientWidth),'reader fits390px at150% text');
 await page.screenshot({path:path.join(artifacts,'memoir-editorial-reader-zh-150.png')});
 pass('Current saved transition is read between stories at390px/150% Chinese text');
 const jump=reader.locator('.memory-book-editorial-reading-transition details');await jump.locator('summary').click();await jump.locator('button').click();
 await reader.locator('.story-reader-sources').waitFor({state:'attached'});
 await page.waitForFunction(()=>document.querySelector('#memory-book-reader .story-reader-sources')?.open===true);
 assert.equal(requests.filter(item=>/\/contributions\/[^/]+(?:\?|$)/.test(item.path)).length,0,'citation navigation selects a source without loading original text/audio');
 assert(await reader.locator('[data-contribution-id] button').first().isVisible());
 pass('Explicit citation jump selects its chapter and opens source choices without auto-loading originals');
 const originalsBeforeExplicitOpen=requests.filter(item=>/\/contributions\/[^/]+(?:\?|$)/.test(item.path)).length;
 await reader.locator('.story-reader-sources [data-contribution-id] button').first().click();
 await page.waitForFunction(()=>document.querySelector('#memory-book-reader [data-contribution-id] .story-contribution-source-detail')?.hidden===false);
 assert.equal(requests.filter(item=>/\/contributions\/[^/]+(?:\?|$)/.test(item.path)).length,originalsBeforeExplicitOpen+1,'original family wording loads only after its explicit source action');
 pass('Original family wording loads only after its explicit source action');

 await reader.locator('header button').click();await page.evaluate(()=>window.__workspace.openBook(window.__book));
 refsStatusOverride=503;await reader.locator('.memory-book-toc button').nth(1).click();
 const topSourceStatus=reader.locator('.memory-book-source-status-note');
 await reader.locator('.memory-book-source-retry').waitFor({state:'visible'});
 assert.match(await topSourceStatus.textContent(),/来源链接暂不可用/);
 assert.equal(await reader.locator('.story-reader-sources').evaluateAll(nodes=>nodes.every(node=>!node.open)),true,'source failure remains visible while the disclosure stays closed');
 await page.screenshot({path:path.join(artifacts,'memoir-source-unavailable-zh-150.png')});
 const originalsBeforeRetry=requests.filter(item=>/\/contributions\/[^/]+(?:\?|$)/.test(item.path)).length;
 const writesBeforeRetry=requests.filter(item=>['POST','PUT','PATCH','DELETE'].includes(item.method)&&/memory-stories|memory-community\/v1\/books/.test(item.path)).length;
 const readingContextBeforeRetry=await reader.evaluate(element=>element.__photoHouseReadingContext());
 let retryArrive,retryRelease;const retrySeen=new Promise(resolve=>retryArrive=resolve),retryReleased=new Promise(resolve=>retryRelease=resolve);holdRefs={arrive:retryArrive,release:retryReleased};
 await reader.locator('.memory-book-source-retry').click();
 await retrySeen;
 assert.match(await topSourceStatus.textContent(),/正在核实本章/,'retry exposes the checking state outside the disclosure');
 assert.equal(await reader.locator('.memory-book-source-retry').count(),0,'duplicate retries are unavailable while checking');
 assert.deepEqual(await reader.evaluate(element=>element.__photoHouseReadingContext()),readingContextBeforeRetry,'retry preserves the current book/story/chapter identity');
 await page.screenshot({path:path.join(artifacts,'memoir-source-checking-zh-150.png')});
 retryRelease();
 await page.waitForFunction(()=>{const text=document.querySelector('#memory-book-reader .memory-book-source-status-note')?.textContent||'';return /本章已核实|本章没有已保存/.test(text);});
 assert.equal(await reader.locator('.story-reader-sources').evaluateAll(nodes=>nodes.every(node=>!node.open)),true,'successful retry leaves the source disclosure closed');
 assert.equal(requests.filter(item=>/\/contributions\/[^/]+(?:\?|$)/.test(item.path)).length,originalsBeforeRetry,'retry refreshes references without loading original contribution text or audio');
 assert.equal(requests.filter(item=>['POST','PUT','PATCH','DELETE'].includes(item.method)&&/memory-stories|memory-community\/v1\/books/.test(item.path)).length,writesBeforeRetry,'retry creates no story, editorial or save mutation');
 assert.match(await topSourceStatus.textContent(),/本章已核实 \d+ 条|本章没有已保存/,'Chinese status reports current source-link results');
 pass('Chapter source checking/failure is visible outside the disclosure; explicit retry refreshes references only');

 await reader.locator('header button').click();await page.evaluate(()=>{window.__scope.language='en';window.__workspace.openBook(window.__book);});
 const freshEnglishFontGroup=reader.getByRole('group',{name:'Reading size'});assert(await freshEnglishFontGroup.isVisible());assert.equal(await freshEnglishFontGroup.getByRole('button',{name:'Default'}).getAttribute('aria-pressed'),'true','a fresh English memoir starts at Default');await reader.screenshot({path:path.join(artifacts,'memoir-font-presets-en-fresh-390-150.png')});
 await reader.locator('.memory-book-toc button').nth(1).click();
 await page.waitForFunction(()=>{const text=document.querySelector('#memory-book-reader .memory-book-source-status-note')?.textContent||'';return /source link|source links/.test(text)&&!/^Checking/.test(text);});
 assert.match(await reader.locator('.memory-book-source-status-note').textContent(),/source link|source links/,'English reader reports the available source-link state');
 await page.screenshot({path:path.join(artifacts,'memoir-source-available-en-150.png')});
 await reader.locator('header button').click();await page.evaluate(()=>{window.__scope.language='zh';window.__workspace.openBook(window.__book);});

 await reader.locator('header button').click();await page.evaluate(()=>window.__workspace.openBook(window.__book));await reader.locator('.memory-book-introduction-sources details').waitFor({state:'attached'});overrideParent=true;
 await reader.locator('.memory-book-toc button').nth(1).click();await reader.locator('.memory-book-reopen').waitFor();assert.equal(await reader.locator('.memory-book-editorial-reading-transition').count(),0);assert.equal(await reader.locator('.memory-book-introduction-sources details').count(),0);
 pass('Changed child revision in the reauthorized parent withholds the opened snapshot');
 await reader.locator('header button').click();await page.evaluate(()=>window.__workspace.openBook(window.__book));await reader.locator('.memory-book-introduction-sources details').waitFor({state:'attached'});overrideChild=true;
 await reader.locator('.memory-book-toc button').nth(1).click();await reader.locator('.memory-book-reopen').waitFor();assert.equal(await reader.locator('.memory-book-editorial-reading-transition').count(),0);assert.equal(await reader.locator('.memory-book-reading h4').count(),0);assert.equal(await reader.locator('.memory-book-introduction-sources details').count(),0);
 pass('Child revision race after editorial loading cannot combine new chapters with stale passages');

 await reader.locator('header button').click();await rpc({command:'editorial-off'});await page.evaluate(()=>window.__workspace.openBook(window.__book));
 await reader.locator('.memory-book-toc button').nth(1).click();await reader.locator('.memory-book-reading h4').waitFor();
 assert.equal(await reader.locator('.memory-book-editorial-reading-transition').count(),0);assert.equal(await reader.locator('.memory-book-editorial-reading-status').count(),0);
 pass('Default-off503 keeps legacy reading available without exposing an error');
 await reader.locator('header button').click();await rpc({command:'editorial-on'});
 editorialStatusOverride=404;await page.evaluate(()=>{window.__errors=[];window.__workspace.openBook(window.__book);});
 await reader.locator('.memory-book-toc button').nth(1).click();await reader.locator('.memory-book-reading h4').waitFor();
 assert.equal(await reader.locator('.memory-book-editorial-reading-transition').count(),0);assert.equal(await reader.locator('.memory-book-editorial-reading-status').count(),0);assert.deepEqual(await page.evaluate(()=>window.__errors),[]);
 pass('Legacy server404 keeps memoir reading available without an optional-feature warning');
 await reader.locator('header button').click();editorialStatusOverride=null;
 // A malformed current response must not display its prose.
 overrideEditorial=dto=>({...dto,transitions:dto.transitions.map(item=>({...item,source_refs:[]}))});
 await page.evaluate(()=>window.__workspace.openBook(window.__book));await reader.locator('.memory-book-editorial-reading-status').waitFor();
 assert.equal(await reader.locator('.memory-book-introduction-sources details').count(),0);
 pass('Malformed editorial response is withheld');
 await reader.locator('header button').click();await rpc({command:'delete-source'});await page.evaluate(()=>window.__workspace.openBook(window.__book));
 await reader.locator('.memory-book-editorial-reading-status').waitFor();assert.match(await reader.locator('.memory-book-editorial-reading-status').textContent(),/来源已变化/);
 await reader.locator('.memory-book-toc button').nth(1).click();await reader.locator('.memory-book-reading h4').waitFor();assert.equal(await reader.locator('.memory-book-editorial-reading-transition').count(),0);
 pass('Deleted source produces source_changed and withholds old transition prose');
 await reader.locator('header button').click();let refsArrive,refsRelease;const refsSeen=new Promise(resolve=>refsArrive=resolve),refsReleased=new Promise(resolve=>refsRelease=resolve);holdRefs={arrive:refsArrive,release:refsReleased};
 await page.evaluate(()=>window.__workspace.openBook(window.__book));await reader.locator('.memory-book-toc button').nth(1).click();await refsSeen;
 await page.evaluate(()=>{window.__scope.library='family-b';window.__workspace.clear();});refsRelease();await page.waitForTimeout(40);
 assert.equal(await page.locator('#memory-book-reader').count(),0);assert.equal(await page.locator('body').textContent().then(text=>text.includes('Checking this chapter’s saved family-memory links')),false,'late source lookup is fenced after a protected scope change');
 pass('Late source-reference response is fenced after account/library scope changes');
 await page.evaluate(()=>{window.__scope.library='family-a';window.__workspace.openBook(window.__book);});
 let arrive,release;const seen=new Promise(resolve=>arrive=resolve),released=new Promise(resolve=>release=resolve);holdEditorial={arrive,release:released};
 await page.evaluate(()=>window.__workspace.openBook(window.__book));await seen;await page.evaluate(()=>{window.__scope.library='family-b';window.__workspace.clear();});release();await page.waitForTimeout(40);
 assert.equal(await page.locator('#memory-book-reader').count(),0);assert.equal(await page.locator('body').textContent().then(text=>text.includes('从那次相聚')),false);
 pass('Late editorial response is fenced after protected scope changes');
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(artifacts,'receipt.json'),JSON.stringify({checks,pageErrors:errors,requests:requests.length},null,2));console.log('ARTIFACTS_DIR '+artifacts);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(context)await context.close();if(browser)await browser.close();bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');});
