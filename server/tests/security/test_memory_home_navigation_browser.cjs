'use strict';
// Browser -> closed ASGI -> synthetic SQLite. No listener or real family data.
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..'),artifacts=fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-memory-navigation-'));
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pending=new Map(),errors=[],external=[],requests=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const item=pending.get(result.id);if(item){pending.delete(result.id);item.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error('Bridge failed'));for(const item of pending.values())item.reject(new Error('Bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
let browser,ctx,assistantTextFixture=false;
(async()=>{
 await ready;browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
 ctx=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block'});
 await ctx.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
  requests.push({method:req.method(),path:url.pathname});if(assistantTextFixture&&url.pathname==='/assistant/v1/capabilities'){await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,enabled:true,text:true,transcribe:false,speech:false})});return;}const headers=await req.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']=new URL(req.frame().url()).origin===url.origin?'same-origin':'none';
  const result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});const output={...result.headers};delete output['content-length'];delete output['content-encoding'];await route.fulfill({status:result.status,headers:output,body:Buffer.from(result.body,'base64')});
 });
 const page=await ctx.newPage();page.on('pageerror',error=>errors.push(error.message));
 await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
 await page.waitForFunction(()=>document.querySelector('#saved-memory-status').textContent.includes('还没有'));
 assert.equal(await page.locator('#memory-books-link').isVisible(),false,'unsupported memoir entry stays absent');
 await page.locator('#memory-navigation a[href="#saved-memory-panel"]').focus();await page.keyboard.press('Enter');
 await page.waitForFunction(()=>document.activeElement?.id==='saved-memory-heading');
 assert.equal(await page.locator('#memory-navigation a[href="#saved-memory-panel"]').getAttribute('aria-current'),'location');
 console.log('PASS Empty story shelf is reachable by keyboard without a media-dependent hero');
 await page.locator('#memory-albums-link').click();await page.waitForFunction(()=>document.querySelector('#albums-panel').open&&document.activeElement===document.querySelector('#albums-panel > summary'));
 await page.locator('#memory-assistant-link').click();await page.waitForFunction(()=>document.activeElement===document.querySelector('#assistant-panel > summary'));assert.equal(await page.locator('#assistant-form').isVisible(),false);
 await page.locator('#memory-navigation a[href="#grid"]').click();await page.waitForFunction(()=>document.activeElement?.id==='grid');
 console.log('PASS Albums expand, media receives focus, and unavailable assistant focuses its visible summary');
 assistantTextFixture=true;
 await rpc({command:'mutate',scenario:'enable-story-source-detail-fixture'});await page.reload();await page.locator('#memory-books-link').waitFor({state:'visible'});await page.locator('#memory-books-link').click();await page.waitForFunction(()=>document.activeElement?.classList.contains('memory-community-books-heading'));
 await page.waitForFunction(()=>document.querySelector('#memory-books-link').getAttribute('aria-current')==='location');
 await page.evaluate(()=>{document.documentElement.style.fontSize='150%';document.body.style.fontSize='24px';});await page.locator('#memory-books-link').click();
 await page.waitForFunction(()=>document.querySelector('#memory-navigation').getBoundingClientRect().top>=-1);
 const layout=await page.evaluate(()=>{const nav=document.querySelector('#memory-navigation'),heading=document.activeElement;return {overflow:document.documentElement.scrollWidth>innerWidth,nav:nav.getBoundingClientRect().toJSON(),heading:heading.getBoundingClientRect().toJSON(),links:[...nav.querySelectorAll('a:not([hidden])')].map(el=>({text:el.textContent,rect:el.getBoundingClientRect().toJSON()}))};});
 assert.equal(layout.overflow,false);assert(layout.heading.top>=layout.nav.bottom-1,'focused heading remains below wrapped sticky navigation');for(const item of layout.links){assert(item.rect.height>=44);assert(item.rect.right<=390);}
 await page.screenshot({path:path.join(artifacts,'memoir-navigation-390-font150.png')});
 console.log('PASS Qualified memoir entry appears, wraps at 390px/150%, and does not cover its focused heading');
 await page.locator('#memory-assistant-link').click();await page.waitForFunction(()=>document.activeElement?.id==='assistant-text');await page.locator('#assistant-text').fill('先写下要问的问题，还没有发送');const before=requests.filter(item=>item.method==='POST').length;
 await page.locator('#memory-navigation a[href="#grid"]').click();await page.waitForFunction(()=>document.activeElement?.id==='grid');await page.locator('#memory-assistant-link').click();assert.equal(await page.locator('#assistant-text').inputValue(),'先写下要问的问题，还没有发送');assert.equal(requests.filter(item=>item.method==='POST').length,before);
 console.log('PASS Enabled synthetic text assistant preserves its unsent draft through navigation');

 await page.locator('#memory-navigation a[href="#saved-memory-panel"]').click();await page.screenshot({path:path.join(artifacts,'story-navigation-390-font150.png')});
 await page.locator('#language').click();await page.waitForFunction(()=>document.querySelector('#memory-navigation').getAttribute('aria-label')==='Memory navigation');assert.equal(await page.locator('#memory-navigation a').first().textContent(),'Stories');await page.locator('#memory-navigation a[href="#grid"]').click();await page.waitForFunction(()=>document.activeElement?.id==='grid');assert.equal(await page.locator('#grid').getAttribute('aria-label'),'Photos and videos');
 await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelectorAll('#memory-navigation [aria-current]').length===0);
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);console.log('PASS Language and signed-out states keep navigation scope honest');console.log(JSON.stringify({artifacts,checks:5,externalRequests:external.length,pageErrors:errors.length}));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(ctx)await ctx.close();if(browser)await browser.close();bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.stdin.end();});
