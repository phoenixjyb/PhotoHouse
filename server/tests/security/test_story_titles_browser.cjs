"use strict";
/* Browser -> actual protected ASGI -> synthetic SQLite. No HTTP listener or model. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..'),artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-titles-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,browser,ctx,hold=null,corrupt=false,fail=false;const pending=new Map(),errors=[],external=[],checks=[],requests=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready)readyResolve();else{const item=pending.get(value.id);if(item){pending.delete(value.id);item.resolve(value);}}});
bridge.stderr.on('data',v=>process.stderr.write(v));bridge.on('exit',code=>{if(code){readyReject(new Error('Bridge failed'));for(const item of pending.values())item.reject(new Error('Bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const pass=name=>{checks.push(name);console.log('PASS '+name);};
(async()=>{
 await ready;browser=await chromium.launch({headless:true,args:['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND']});
 ctx=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block'});
 await ctx.addInitScript(()=>{let factory;Object.defineProperty(window,'PhotoHouseStoryWorkspace',{configurable:true,get:()=>factory,set:value=>{factory=config=>{let language=null;const original=config.scope;const instance=value({...config,scope:()=>({...original(),...(language?{language}:{})})});window.__titleTestLanguage=value=>{language=value;instance.translate();};return instance;};}});});
 await ctx.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
  requests.push({method:req.method(),path:url.pathname,body:req.postData()});const headers=await req.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
  const result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
  let body=Buffer.from(result.body,'base64'),status=result.status,complete=null;
  if(url.pathname==='/story-workspace/title-suggestions'){
   if(hold){const gate=hold;hold=null;gate.arrive();await gate.wait;complete=gate.complete;}
   if(corrupt){corrupt=false;const value=JSON.parse(body);value.titles[0].source_ids=['foreign-source'];body=Buffer.from(JSON.stringify(value));}
   if(fail){fail=false;status=503;body=Buffer.from('{"detail":"Title suggestions unavailable"}');}
  }
  const output={...result.headers};delete output['content-length'];delete output['content-encoding'];try{await route.fulfill({status,headers:output,body});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/i.test(error.message))throw error;}finally{complete?.();}
 });
 const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await page.goto('https://photohouse.test/ui');await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
 const open=async()=>{await page.locator('.memory-theme[data-theme=trip]').click();await page.locator('#story-build').click();await page.locator('.story-chapter-card textarea').first().waitFor();};
 await open();assert.equal(await page.locator('.story-title-assistance').isVisible(),false);pass('Default-off capability hides optional title controls; drafting works');
 await page.locator('#story-workspace-close').click();await rpc({command:'mutate',scenario:'enable-story-title-fixture'});await open();
 const action=page.locator('.story-title-assistance > button');await action.waitFor({state:'visible'});
 await page.locator('.story-chapter-card textarea').first().fill('家人一起散步，这是我们留下的回忆。');const original=await page.locator('#story-workspace-title').inputValue();
 await action.click();await page.locator('.story-title-choice').first().waitFor();assert.equal(await page.locator('#story-workspace-title').inputValue(),original);assert.equal(await page.locator('.story-title-choice b').count(),0);assert.match(await page.locator('.story-title-choice').nth(1).textContent(),/<b>/);
 assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/memory-stories').length,0);
 await page.screenshot({path:path.join(artifacts,'title-review-desktop-zh.png'),fullPage:true});pass('Grounded candidates render literally, preserve the current title, and do not save');
 await page.locator('.story-title-choice').first().click();assert.equal(await page.locator('#story-workspace-title').inputValue(),'一起走过的午後');assert.equal(await page.locator('.story-title-choice').count(),0);pass('Explicit choice updates only the editable draft title');
 async function delayed(edit,composing=false){let arrive,release;const reached=new Promise(r=>arrive=r),wait=new Promise(r=>release=r);hold={arrive,wait};await action.click();await reached;await edit();const response=page.waitForResponse(r=>r.url().includes('/story-workspace/title-suggestions'));release();await response;if(composing){assert.equal(await page.locator('.story-title-choice').count(),0);await page.locator('#story-workspace-title').dispatchEvent('compositionend');}await page.waitForFunction(()=>!document.querySelector('.story-title-assistance > button').disabled);assert.equal(await page.locator('.story-title-choice').count(),0);}
 await delayed(()=>page.locator('#story-workspace-title').fill('我自己写的标题'));assert.equal(await page.locator('#story-workspace-title').inputValue(),'我自己写的标题');
 await delayed(()=>page.locator('.story-chapter-card textarea').first().fill('修改后的原话。'));
 await delayed(()=>page.locator('#story-workspace-title').dispatchEvent('compositionstart'),true);
 pass('Typing, chapter edits and IME composition invalidate delayed suggestions');
 corrupt=true;await action.click();await page.waitForFunction(()=>document.querySelector('.story-title-assistance [role=status]').textContent.includes('暂不可用'));assert.equal(await page.locator('.story-title-choice').count(),0);
 fail=true;await action.click();await page.waitForFunction(()=>!document.querySelector('.story-title-assistance > button').disabled);assert.equal(await page.locator('#story-workspace-title').inputValue(),'我自己写的标题');
 pass('Malformed citations and provider failure preserve manual work and allow retry');
 await action.click();await page.locator('.story-title-choice').first().waitFor();await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.style.fontSize='24px');
 assert(await page.locator('#story-workspace').evaluate(el=>el.scrollWidth<=el.clientWidth));await action.scrollIntoViewIfNeeded();await page.locator('.story-title-sources summary').first().click();await page.locator('.story-title-assistance').screenshot({path:path.join(artifacts,'title-review-mobile-zh.png')});pass('Chinese title review fits a 390px viewport at enlarged text');
 await page.evaluate(()=>window.__titleTestLanguage('en'));await page.locator('.story-title-assistance > button').waitFor();assert.equal(await action.textContent(),'Suggest a title');await action.click();await page.locator('.story-title-choice').first().waitFor();await action.scrollIntoViewIfNeeded();await page.locator('.story-title-assistance').screenshot({path:path.join(artifacts,'title-review-mobile-en.png')});pass('English controls retain the draft and use the same bounded title contract');await page.locator('.story-title-choice').first().click();await page.locator('#story-workspace-title').fill('A title edited by the family');const saved=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/memory-stories');await page.locator('#story-save-memory').click();assert.equal((await saved).status(),200);await page.waitForFunction(()=>document.getElementById('story-workspace-status').textContent.includes('Saved in'));const mutation=JSON.parse(requests.filter(r=>r.method==='POST'&&r.path==='/memory-stories').at(-1).body);assert.equal(mutation.title,'A title edited by the family');assert.match(JSON.parse(mutation.chapters)[0].narration,/修改后的原话/);pass('Explicit save persists the family-edited title and unchanged narration through the existing API');let arrive,release,complete;const reached=new Promise(r=>arrive=r),wait=new Promise(r=>release=r),finished=new Promise(r=>complete=r);hold={arrive,wait,complete};await action.click();await reached;await page.locator('#story-workspace-close').click();await page.locator('#logout').click();await page.locator('#auth').waitFor();release();await finished;assert.equal(await page.locator('.story-title-choice').count(),0);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 pass('Logout clears candidates; zero external requests and browser errors');
 fs.writeFileSync(path.join(artifacts,'checks.json'),JSON.stringify({checks,errors,external,fixture:'Actual ASGI; synthetic title adapter, no model'},null,2));console.log('ARTIFACTS '+artifacts);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(ctx)await ctx.close();if(browser)await browser.close();bridge.stdin.end();});
