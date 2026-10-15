"use strict";
/* Browser -> actual protected ASGI -> synthetic SQLite. No HTTP listener or model. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{createInterface}=require('node:readline');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..'),artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-groups-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,browser,ctx,hold=null,corrupt=false,fail=false;const pending=new Map(),errors=[],external=[],checks=[],requests=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready)readyResolve();else{const item=pending.get(value.id);if(item){pending.delete(value.id);item.resolve(value);}}});
bridge.stderr.on('data',v=>process.stderr.write(v));bridge.on('exit',code=>{if(code){readyReject(new Error('Bridge failed'));for(const item of pending.values())item.reject(new Error('Bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const pass=name=>{checks.push(name);console.log('PASS '+name);};
(async()=>{
 await ready;await rpc({command:'mutate',scenario:'memory-groups'});
 browser=await chromium.launch({headless:true,executablePath:process.env.PH_BROWSER_EXECUTABLE,args:['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND']});
 ctx=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block'});
 await ctx.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
  requests.push({method:req.method(),path:url.pathname,body:req.postData()});
  const headers=await req.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
  const result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
  let status=result.status,body=Buffer.from(result.body,'base64');
  if(fail&&req.method()==='POST'&&url.pathname==='/memory-groups'){fail=false;status=503;body=Buffer.from('{"detail":"Synthetic uncertain response"}');}
  const output={...result.headers};delete output['content-length'];delete output['content-encoding'];
  await route.fulfill({status,headers:output,body});
 });
 const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await page.goto('https://photohouse.test/ui');await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
 await page.locator('#grid [data-asset-id="101"]').click();await page.locator('#memory-groups summary').waitFor();
 assert.equal(requests.filter(r=>r.path==='/memory-groups/capabilities').length,0);
 await page.locator('#memory-groups summary').click();await page.locator('.memory-group-create').click();
 await page.locator('.memory-group-story-choice input').check();await page.locator('.memory-group-suggest').click();
 await page.locator('.memory-group-suggestion').first().waitFor();assert.equal(await page.locator('.memory-group-suggestion input').isChecked(),true);
 assert.match(await page.locator('.memory-group-count').textContent(),/^2 \/ 24/);
 await page.locator('#memory-groups').evaluate(el=>{const dialog=el.closest('dialog');dialog.scrollTop+=el.getBoundingClientRect().top-dialog.getBoundingClientRect().top-16;});
 await page.screenshot({path:path.join(artifacts,'memory-groups-desktop-zh.png')});
 pass('Explicit expansion loads capabilities; time and image suggestions are visible and editable before save');
 await page.locator('.memory-group-suggestion input').uncheck();await page.locator('.memory-group-suggest').click();await page.waitForFunction(()=>!document.querySelector('.memory-group-suggest').disabled);
 const proposal=JSON.parse(requests.filter(r=>r.path==='/memory-groups/proposals').at(-1).body);assert.equal(proposal.asset_ids,'101');assert.equal(proposal.excluded_asset_ids,'102');
 assert.equal(await page.locator('.memory-group-suggestion').count(),0);pass('Removing a suggestion sends a sticky exclusion and refresh stays anchored to the original photo');
 // Manually reinclude an excluded item, then lose the save response after commit.
 await page.locator('.memory-group-gallery-choice input[value="102"]').click();fail=true;await page.locator('.memory-group-save').click();await page.locator('.memory-group-save-retry').waitFor();
 const sent=JSON.parse(requests.filter(r=>r.method==='POST'&&r.path==='/memory-groups').at(-1).body);
 assert.equal(sent.asset_ids,'101,102');assert.equal(sent.source_story_ids.split(',').length,1);assert.equal(Object.keys(sent).sort().join(','),'asset_ids,excluded_asset_ids,mutation_id,revision,source_story_ids,theme');assert(!JSON.stringify(sent).includes('一家人'));
 await page.locator('.memory-group-save-retry').click();await page.locator('.memory-group-card').waitFor();
 const writes=requests.filter(r=>r.method==='POST'&&r.path==='/memory-groups');assert.deepEqual(JSON.parse(writes.at(-1).body),sent);
 assert.equal(await page.locator('.memory-group-card').count(),1);assert.match(await page.locator('.memory-group-source').textContent(),/讲述人：家人/);
 pass('Save sends references only; a lost successful response retries the exact request and creates one group');
 await page.locator('#close-viewer').click();await page.locator('#grid [data-asset-id="102"]').click();await page.locator('#memory-groups summary').click();await page.locator('.memory-group-card').waitFor();
 assert.match(await page.locator('.memory-group-source').textContent(),/一家人沿着湖边/);pass('The original note appears with attribution when opening a different group member');
 await page.locator('.memory-group-edit').click();assert.equal(await page.locator('.memory-group-story-choice input:checked').count(),1);
 await page.setViewportSize({width:390,height:844});await page.locator('#memory-groups').evaluate(el=>el.style.fontSize='150%');
 for(const selector of ['#memory-groups','.memory-group-editor','.memory-group-items'])assert(await page.locator(selector).first().evaluate(el=>el.scrollWidth<=el.clientWidth),selector+' fits enlarged text');
 await page.locator('#memory-groups').evaluate(el=>{const dialog=el.closest('dialog');dialog.scrollTop+=el.getBoundingClientRect().top-dialog.getBoundingClientRect().top-16;});await page.screenshot({path:path.join(artifacts,'memory-groups-mobile-zh.png')});
 await page.locator('.memory-group-save').focus();assert.equal(await page.locator('.memory-group-save').evaluate(el=>el===document.activeElement),true);
 pass('Existing source linkage survives edit on another photo; mobile enlarged text and keyboard focus render');
 await page.locator('.memory-group-cancel').click();await page.locator('#close-viewer').click();await page.locator('#language').click();await page.locator('#grid [data-asset-id="101"]').waitFor();await page.locator('#grid [data-asset-id="101"]').click();await page.locator('#memory-groups summary').click();await page.locator('.memory-group-card').waitFor();assert.equal(await page.locator('#memory-groups summary').textContent(),'Family memory groups');
 await page.screenshot({path:path.join(artifacts,'memory-groups-mobile-en.png')});
 await page.locator('#close-viewer').click();await page.locator('#logout').click();await page.locator('#auth').waitFor();assert.equal(await page.locator('.memory-group-source').count(),0);assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);pass('English UI and logout clear private group text without browser storage or external requests');
 fs.writeFileSync(path.join(artifacts,'checks.json'),JSON.stringify({checks,errors,external,fixture:'Actual ASGI with generated vectors, thumbnails and family note; no inference'},null,2));console.log('ARTIFACTS '+artifacts);
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(ctx)await ctx.close();if(browser)await browser.close();bridge.stdin.end();});
