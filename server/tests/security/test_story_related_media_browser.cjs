"use strict";
/* Browser -> actual protected ASGI -> synthetic SQLite. No HTTP listener or model. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..'),artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-related-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,browser,ctx,hold=null,corrupt=false,fail=false;const pending=new Map(),errors=[],external=[],checks=[],requests=[];
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
 await find.click();await rows.first().waitFor();await page.setViewportSize({width:390,height:844});await page.locator('#story-workspace').evaluate(el=>el.style.fontSize='150%');
 for(const sel of ['#story-related','.story-related-items','.story-related-card'])assert(await page.locator(sel).first().evaluate(el=>el.scrollWidth<=el.clientWidth),sel+' fits at enlarged text');
 await page.locator('#story-related').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'related-moments-mobile-zh.png')});
 await page.evaluate(()=>window.__relatedLanguage('en'));assert.equal(await find.textContent(),'Find moments from these days');await page.screenshot({path:path.join(artifacts,'related-moments-mobile-en.png')});pass('Chinese and English picker render at 390px with 150 percent text');
 async function late(edit){let arrive,release,complete;const reached=new Promise(r=>arrive=r),wait=new Promise(r=>release=r),finished=new Promise(r=>complete=r);hold={arrive,wait,complete};await find.click();await reached;await edit();release();await finished;assert.equal(await rows.count(),0);}
 await late(()=>page.locator('#story-selection-clear').click());assert.match(await page.locator('#story-selection-count').textContent(),/^0 \/ 24/);pass('A selection change invalidates a late response');
 await page.locator('#story-workspace-close').click();await page.evaluate(()=>window.__relatedTest.open(Array.from({length:29},(_,i)=>String(1101+i)),'trip'));if(!(await page.locator('#story-related').evaluate(el=>el.open)))await page.locator('#story-related summary').click();
 await find.click();await rows.first().waitFor();assert.equal(await rows.locator('button:enabled').count(),0);pass('Selection limit disables all candidate additions');
 await late(async()=>{await page.locator('#story-workspace-close').click();await page.locator('#logout').click();await page.locator('#auth').waitFor();});
 assert.equal(await page.locator('#story-selection img').count(),0);assert.equal(await page.locator('#story-chapter-editor').textContent(),'');assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);pass('Logout clears candidate media; late response cannot repopulate private UI; zero external requests or browser errors');
 fs.writeFileSync(path.join(artifacts,'checks.json'),JSON.stringify({checks,errors,external,fixture:'Actual ASGI with synthetic assets; no inference'},null,2));console.log('ARTIFACTS '+artifacts);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(ctx)await ctx.close();if(browser)await browser.close();bridge.stdin.end();});
