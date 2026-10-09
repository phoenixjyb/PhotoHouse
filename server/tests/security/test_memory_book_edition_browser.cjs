'use strict';
/* Real Chromium with a no-listener synthetic ASGI bridge; no model requests. */
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=path.resolve(__dirname,'../..'),artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-edition-browser-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'memory_book_edition_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,seed;const pending=new Map(),ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){seed=value;readyResolve();return;}const waiter=pending.get(value.id);if(waiter){pending.delete(value.id);waiter.resolve(value);}});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));bridge.on('exit',code=>{if(code){const error=new Error('Synthetic edition bridge exited '+code);readyReject(error);for(const waiter of pending.values())waiter.reject(error);}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
let browser,context,page,failCommittedSave=true,acceptDialogs=true,malformCapsOnce=false,malformDetailOnce=false,holdProposal=false,proposalArrived,releaseProposal,proposalReady,proposalRelease;const calls=[],external=[],errors=[];
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block'});
  await context.addCookies([{name:seed.cookie_name,value:seed.session_cookie,url:'https://photohouse.test/',httpOnly:true,secure:true,sameSite:'Strict'}]);
  await context.route('**/*',async route=>{
    const request=route.request(),u=new URL(request.url());if(u.origin!=='https://photohouse.test'){external.push(u.origin);await route.abort();return;}
    if(u.pathname==='/'){await route.fulfill({contentType:'text/html',body:'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main><div id="community"></div></main></body></html>'});return;}
    const entry={method:request.method(),path:u.pathname+u.search,body:request.postData()};calls.push(entry);
    const response=await rpc({method:entry.method,path:entry.path,headers:await request.allHeaders(),body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    if(u.pathname.endsWith('/edition-capabilities')&&malformCapsOnce){malformCapsOnce=false;await route.fulfill({status:200,contentType:'application/json',body:'{"version":1,"enabled":"true","can_save":true}'});return;}
    if(/\/editions\/[0-9a-f-]{36}$/.test(u.pathname)&&malformDetailOnce){malformDetailOnce=false;const value=JSON.parse(Buffer.from(response.body,'base64').toString());value.state='source_changed';await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});return;}
    if(u.pathname.includes('/editions/proposals/')&&holdProposal){proposalArrived();await proposalRelease;}
    if(entry.method==='POST'&&/\/editions\?/.test(entry.path)&&response.status===200&&failCommittedSave){failCommittedSave=false;await route.fulfill({status:503,contentType:'application/json',body:'{"error":"Synthetic lost save receipt"}'});return;}
    await route.fulfill({status:response.status,contentType:response.content_type||'application/json',body:Buffer.from(response.body,'base64')});
  });
  page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>acceptDialogs?dialog.accept():dialog.dismiss());
  await page.goto('https://photohouse.test/');await page.addStyleTag({content:fs.readFileSync(path.join(root,'backend/app/ui/access/styles.css'),'utf8')});await page.addStyleTag({content:'html{font-size:150%}'});
  await page.addScriptTag({content:fs.readFileSync(path.join(root,'backend/app/ui/access/memory-community.js'),'utf8')});
  await page.evaluate(async seed=>{
    window.__scope={account:'synthetic-owner',library:'family-a',language:'zh',locked:false};window.__failures=[];
    const request=async(path,options={})=>{const suffix=path.includes('?')?'&':'?';const headers={'X-CSRF-Token':seed.csrf_token};let url=path+suffix+'library='+encodeURIComponent(window.__scope.library),method=options.method||'GET';
      // Narrative generation itself is covered elsewhere. Reuse the seeded,
      // actor-owned ready job to exercise this adoption path without a provider.
      if(method==='POST'&&path==='/memory-community/v1/jobs'){url='/memory-community/v1/jobs/'+seed.job_id+'?library=family-a';method='GET';}
      if(options.body)headers['Content-Type']='application/json';
      const response=await fetch(url,{method,headers,credentials:'same-origin',signal:options.signal,...(method!=='GET'&&options.body?{body:JSON.stringify(options.body)}:{})});
      if(!response.ok){const error=new Error('Synthetic HTTP '+response.status);error.status=response.status;throw error;}return response.json();};
    const book=await request('/memory-community/v1/books/'+seed.book_id);window.__target={...book,type:'memoir'};
    window.__community=window.PhotoHouseMemoryCommunity({scope:()=>window.__scope,request,onError:error=>window.__failures.push(error.status)});
    await window.__community.attach(document.querySelector('#community'),window.__target);
  },seed);
  await page.getByRole('tab',{name:'整理建议',exact:true}).click();await page.locator('.memory-community-form button[type=submit]').click();await page.locator('.memory-edition-open').waitFor();
  assert.equal(calls.filter(call=>call.path.includes('/editions')).length,0,'job completion never adopts an edition');
  await page.locator('.memory-edition-open').click();await page.getByText('此相册库暂未开放回忆录版本保存。整理稿仍可在这里核对。',{exact:true}).waitFor();
  assert.equal(await page.locator('.memory-edition-form').count(),0,'default-off capability exposes no write form');
  await rpc({command:'editions-on'});malformCapsOnce=true;const capCount=calls.filter(call=>call.path.includes('/edition-capabilities')).length;
  await page.locator('.memory-edition-check-again').click();await page.waitForFunction(()=>window.__failures.length>0);assert.equal(calls.filter(call=>call.path.includes('/edition-capabilities')).length,capCount+1);assert.equal(await page.locator('.memory-edition-form').count(),0,'malformed capability cannot open a write form');
  await page.locator('.memory-edition-check-again').click();await page.locator('.memory-edition-form').waitFor();
  const form=page.locator('.memory-edition-form');assert(await form.locator('button[type=submit]').isDisabled(),'a proposal is not review confirmation');
  await form.locator('input[name=edition_title]').fill('家人核对的花园回忆 <b>原样文字</b>');await form.locator('.memory-edition-chapter summary').first().click();await form.locator('textarea[name=edition_chapter_0]').fill('奶奶讲起合成花园的片段；年份尚待家人确认。');
  const pendingForm=await form.elementHandle();const shelfReload=page.locator('.memory-edition-shelf-retry').count().then(n=>n?'.memory-edition-shelf-retry':'.memory-edition-shelf-refresh');await page.locator(await shelfReload).click();await page.getByText('还没有已保存的家庭版本。',{exact:true}).waitFor();assert(await pendingForm.evaluate(node=>node.isConnected),'shelf refresh preserves the pending editor DOM identity');assert.equal(await form.locator('input[name=edition_title]').inputValue(),'家人核对的花园回忆 <b>原样文字</b>','shelf refresh preserves unsaved editor text');
  await form.locator('input[name=edition_reviewed]').check();await form.locator('textarea[name=edition_chapter_0]').fill('奶奶讲起合成花园的片段；年份仍待家人确认。');assert(await form.locator('button[type=submit]').isDisabled(),'editing invalidates the prior review confirmation');
  acceptDialogs=false;await page.getByRole('tab',{name:'一起聊回忆',exact:true}).click();assert.equal(await form.locator('input[name=edition_title]').inputValue(),'家人核对的花园回忆 <b>原样文字</b>','declining discard keeps the manuscript');acceptDialogs=true;
  await form.locator('textarea[name=edition_chapter_0]').evaluate(input=>input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true})));
  await page.getByRole('tab',{name:'一起聊回忆',exact:true}).click();assert(await form.isVisible(),'IME composition blocks navigation');
  await form.locator('textarea[name=edition_chapter_0]').evaluate(input=>input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true})));
  assert(await form.locator('button[type=submit]').isDisabled(),'composition completion requires fresh review');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'Chinese large text does not overflow horizontally');
  await form.locator('input[name=edition_reviewed]').check();await page.screenshot({path:path.join(artifacts,'review-zh-390px-text150.png'),fullPage:true});
  await form.locator('button[type=submit]').click();await page.getByText('暂时无法确认保存结果。稿件已保留；重试会使用完全相同的内容。',{exact:true}).waitFor();
  assert(await form.locator('input[name=edition_title]').isDisabled(),'uncertain saves freeze the exact manuscript');const firstSave=calls.find(call=>call.method==='POST'&&call.path.includes('/editions?'));assert(firstSave);
  const jobsBeforeRetry=calls.filter(call=>call.method==='POST'&&call.path.includes('/jobs?')).length;
  await page.locator('.memory-community-form button[type=submit]').click();assert.equal(calls.filter(call=>call.method==='POST'&&call.path.includes('/jobs?')).length,jobsBeforeRetry,'uncertain save blocks a new generation');
  await page.getByRole('tab',{name:'一起聊回忆',exact:true}).click();assert(await form.isVisible(),'uncertain save blocks switching into a conversation');
  await form.locator('button[type=submit]').click();await page.getByText('家庭版本已保存。',{exact:true}).waitFor();const saves=calls.filter(call=>call.method==='POST'&&call.path.includes('/editions?'));assert.equal(saves.length,2);assert.equal(saves[0].body,saves[1].body,'retry reuses identical payload and mutation');
  await page.locator('.memory-edition-shelf-refresh').click();await page.locator('.memory-edition-shelf-read').first().waitFor();assert.equal(await page.locator('.memory-edition-shelf-item').count(),1,'metadata shelf lists saved editions without prose');await page.locator('.memory-edition-shelf-read').first().click();await page.locator('.memory-edition-shelf h4').filter({hasText:'家人核对的花园回忆 <b>原样文字</b>'}).waitFor();assert.match(await page.locator('.memory-edition-shelf').innerText(),/年份仍待家人确认/);
  await page.locator('.memory-edition-read').click();await page.locator('.memory-edition-review h4').filter({hasText:'家人核对的花园回忆 <b>原样文字</b>'}).waitFor();assert.equal(await page.locator('.memory-edition-review b').count(),0,'title is text, never injected markup');assert.match(await page.locator('.memory-edition-review').innerText(),/年份仍待家人确认/);
  await page.screenshot({path:path.join(artifacts,'saved-zh-390px-text150.png'),fullPage:true});
  malformDetailOnce=true;await page.locator('.memory-edition-shelf-read').first().click();await page.getByText('暂时无法核对这个版本；整理文字已隐藏，请重新读取。',{exact:true}).waitFor();assert.equal(await page.locator('.memory-edition-shelf h4').count(),0,'fresh malformed shelf detail clears prior prose');
  await page.locator('.memory-edition-shelf-detail-retry').click();await page.locator('.memory-edition-shelf h4').first().waitFor();
  malformDetailOnce=true;await page.locator('.memory-edition-read').click();await page.getByText('这个版本的来源已变化或被删除，整理文字已隐藏。',{exact:true}).waitFor();assert.equal(await page.locator('.memory-edition-review h4').count(),0,'malformed changed-source response cannot retain old prose');
  await page.locator('.memory-edition-read').click();await page.locator('.memory-edition-review h4').filter({hasText:'家人核对的花园回忆 <b>原样文字</b>'}).waitFor();
  await rpc({command:'scrub-source'});await page.locator('.memory-edition-shelf-refresh').click();await page.locator('.memory-edition-shelf-read').first().click();await page.getByText('来源已变化或已删除，整理文字已隐藏。',{exact:true}).waitFor();assert.equal(await page.locator('.memory-edition-shelf h4').count(),0,'source invalidation clears prior shelf title and prose');
  await page.locator('.memory-edition-read').click();await page.getByText('这个版本的来源已变化或被删除，整理文字已隐藏。',{exact:true}).waitFor();assert.equal(await page.locator('.memory-edition-review h4').count(),0,'source invalidation clears prior title and prose');assert.doesNotMatch(await page.locator('.memory-edition-review').innerText(),/年份仍待家人确认/);
  await page.evaluate(async()=>{window.__community.clear();window.__scope.language='en';await window.__community.attach(document.querySelector('#community'),window.__target);});await page.getByRole('tab',{name:'Draft suggestions',exact:true}).click();await page.locator('.memory-community-form button[type=submit]').click();await page.locator('.memory-edition-open').click();await page.locator('.memory-edition-form').waitFor();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'English large text does not overflow horizontally');await page.screenshot({path:path.join(artifacts,'review-en-390px-text150.png'),fullPage:true});
  await page.evaluate(async()=>{window.__community.clear();await window.__community.attach(document.querySelector('#community'),window.__target);});await page.getByRole('tab',{name:'Draft suggestions',exact:true}).click();await page.locator('.memory-community-form button[type=submit]').click();await page.locator('.memory-edition-open').waitFor();
  holdProposal=true;proposalReady=new Promise(resolve=>proposalArrived=resolve);proposalRelease=new Promise(resolve=>releaseProposal=resolve);await page.locator('.memory-edition-open').click();await proposalReady;
  const before=calls.filter(call=>call.method==='POST'&&call.path.includes('/editions?')).length;await page.evaluate(()=>{window.__scope.account='synthetic-other';window.__community.clear();});releaseProposal();holdProposal=false;await page.waitForLoadState('networkidle');assert.equal(await page.locator('.memory-edition-review').count(),0,'account change clears reviewed manuscript');assert.equal(calls.filter(call=>call.method==='POST'&&call.path.includes('/editions?')).length,before,'scope clearing never saves');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);console.log(JSON.stringify({status:'passed',save_requests:saves.length,identical_retry:true,browser_errors:errors.length,external_requests:external.length,artifacts}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;}).finally(async()=>{if(page&&process.exitCode)await page.screenshot({path:path.join(artifacts,'failure.png'),fullPage:true}).catch(()=>{});if(context)await context.close();if(browser)await browser.close();if(!bridge.killed){bridge.stdin.end(JSON.stringify({command:'quit'})+'\n');bridge.kill();}});
