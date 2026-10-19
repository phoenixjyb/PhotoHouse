/* Synthetic library-wide photo-stack API -> Chromium fixture. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-library-photo-stacks-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||'python3',[path.join(__dirname,'library_photo_stacks_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0;const pending=new Map();let readyResolve,readyReject;
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const message=JSON.parse(line);if(message.ready){readyResolve();return;}const item=pending.get(message.id);if(item){pending.delete(message.id);item.resolve(message);}});
bridge.on('exit',code=>{if(code){readyReject(new Error('Synthetic gallery bridge exited '+code));for(const item of pending.values())item.reject(new Error('Synthetic gallery bridge exited'));}});
function rpc(request){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({id,request})+'\n');});}
let browser,context,page;const errors=[],outside=[],requests=[],preferenceBodies=[];
let unsupported=false,malformed=false,serverError=false,holdPreference=false,preferenceFailureStatus=0,preferenceUnknownStatus=0,heldResolve,releaseHeld;
function release(){releaseHeld?.();releaseHeld=null;}
async function startContext(){
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){outside.push(url.origin);await route.abort();return;}
    requests.push({method:request.method(),path:url.pathname+url.search});
    if(request.method()==='GET'&&url.pathname==='/photo-stacks/gallery'&&unsupported){await route.fulfill({status:404,headers:{'content-type':'application/json'},body:'{"detail":"unsupported"}'});return;}
    if(request.method()==='GET'&&url.pathname==='/photo-stacks/gallery'&&serverError){await route.fulfill({status:503,headers:{'content-type':'application/json'},body:'{"detail":"temporary"}'});return;}
    if(request.method()==='POST'&&url.pathname==='/photo-stacks/preferences')preferenceBodies.push(JSON.parse(request.postData()||'{}'));
    if(request.method()==='POST'&&url.pathname==='/photo-stacks/preferences'&&preferenceFailureStatus){const status=preferenceFailureStatus;preferenceFailureStatus=0;await route.fulfill({status,headers:{'content-type':'application/json'},body:'{"detail":"synthetic preference denial"}'});return;}
    const headers=await request.allHeaders();
    if(!headers['sec-fetch-site']){let origin='';try{origin=new URL(request.frame().url()).origin;}catch{}headers['sec-fetch-site']=origin===url.origin?'same-origin':'none';}
    delete headers['content-length'];
    let response=await rpc({method:request.method(),path:url.pathname+url.search,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    if(request.method()==='GET'&&url.pathname==='/photo-stacks/gallery'&&malformed&&response.status===200){const body=JSON.parse(Buffer.from(response.body,'base64').toString());if(body.photo_stacks?.groups?.length)body.photo_stacks.groups[0].count+=1;response.body=Buffer.from(JSON.stringify(body)).toString('base64');}
    if(request.method()==='POST'&&url.pathname==='/photo-stacks/preferences'&&preferenceUnknownStatus){response.status=preferenceUnknownStatus;response.body=Buffer.from('{"detail":"synthetic lost response"}').toString('base64');preferenceUnknownStatus=0;}
    if(request.method()==='POST'&&url.pathname==='/photo-stacks/preferences'&&holdPreference){holdPreference=false;heldResolve?.();await new Promise(resolve=>releaseHeld=resolve);}
    const responseHeaders={...response.headers};delete responseHeaders['content-length'];delete responseHeaders['content-encoding'];
    try{await route.fulfill({status:response.status,headers:responseHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|canceled|cancelled|Invalid InterceptionId/.test(error.message))throw error;}
  });
  context.on('page',target=>target.on('pageerror',error=>errors.push(error.message)));
  page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
}
async function signIn(phone='+12025550102'){
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN','Chinese is the default locale');
  await page.locator('#login-tab').click();await page.locator('#phone').fill(phone);await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#library').waitFor({state:'visible',timeout:15000});await page.locator('.asset').first().waitFor({timeout:15000});
}
const cards=()=>page.locator('#grid>.asset');
const groupMembers=['100','101','102'];
const check=message=>console.log('PASS '+message);
(async()=>{
  await ready;browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  await startContext();await signIn();
  assert.equal(await page.locator('#photo-stack-reset').isVisible(),true,'library scope keeps reset available even if groups later dissolve');
  assert.match(await page.locator('#photo-stack-help').textContent(),/全相册/);
  assert.match(await page.locator('#photo-stack-status').textContent(),/只保存我的显示方式/);
  assert.equal(await cards().count(),12,'page size counts twelve collapsed visible positions');
  assert.equal(await page.locator('.photo-stack-count').count(),1,'the group whose raw members straddle the twelve-item boundary is represented once on this page');
  assert.equal(await page.locator('#grid .asset[data-asset-id="102"] .photo-stack-count').count(),1,'the indexed group cover is visible');
  for(const id of ['100','101'])assert.equal(await page.locator(`#grid .asset[data-asset-id="${id}"]`).count(),0,`collapsed member ${id} is represented by cover 102`);
  assert.equal(await page.locator('#next').isEnabled(),true);
  await page.screenshot({path:path.join(artifacts,'library-photo-stacks-desktop-gallery.png'),fullPage:true});
  await page.locator('#next').click();await page.locator('.asset').first().waitFor();
  assert.equal(await page.locator('.photo-stack-count').count(),0,'the library-wide group is not repeated on the next collapsed-position page');
  await page.locator('#previous').click();await page.locator('.photo-stack-count').waitFor();
  const currentCover=await page.locator('.photo-stack-count').locator('xpath=ancestor::article').getAttribute('data-asset-id');
  await page.locator(`#grid .asset[data-asset-id="${currentCover}"] .photo-stack-action[data-stack-action="expand"]`).click();
  for(const id of groupMembers)assert.equal(await page.locator(`#grid .asset[data-asset-id="${id}"]`).count(),1,`expanded stack member ${id} is visible exactly once`);
  for(const id of groupMembers){
    await page.locator(`#grid .asset[data-asset-id="${id}"] .asset-open`).click();await page.locator('#viewer').waitFor({state:'visible'});
    assert.match(await page.locator('#view-position').textContent(),/\/ 14$/,'viewer keeps the full ordinary metadata sequence while showing a stack member');
    await page.locator('#close-viewer').click();
  }
  const member=page.locator('#grid .asset[data-asset-id="101"]');await member.locator('.photo-stack-action[data-stack-action="cover"]').click();
  await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-count').waitFor();
  assert.equal(await page.locator('.photo-stack-count').count(),1,'choosing a cover saves and refetches the same page');
  assert.deepEqual(Object.keys(preferenceBodies.at(-1)).sort(),['cover_asset_id','group_id','index_revision','reset','revision','separate_asset_id'].sort(),'preference write uses only the strict contract fields');
  assert.equal(preferenceBodies.at(-1).cover_asset_id,'101');assert.equal(preferenceBodies.at(-1).revision,'0');assert.equal(preferenceBodies.at(-1).reset,'0');
  await page.locator('#refresh').click();await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-count').waitFor();
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});await signIn('+12025550100');
  assert.equal(await page.locator('#grid .asset[data-asset-id="102"] .photo-stack-count').count(),1,'another account sees the indexed default cover, not the member saved choice');
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});await signIn();
  assert.equal(await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-count').count(),1,'the member choice is restored after signing in again');
  await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-action[data-stack-action="expand"]').click();
  await page.locator('#grid .asset[data-asset-id="100"] .photo-stack-action[data-stack-action="separate"]').click();
  await page.locator('.photo-stack-count').waitFor();
  assert.equal(await page.locator('.photo-stack-count').count(),1,'remaining two members keep their stack after one is separated');
  assert.equal(await page.locator('#grid .asset[data-asset-id="100"]').count(),0,'separated member retains its gallery position on the following page');
  assert.equal(preferenceBodies.at(-1).separate_asset_id,'100');assert.equal(preferenceBodies.at(-1).cover_asset_id,'');assert.equal(preferenceBodies.at(-1).revision,'1');
  await page.locator('#next').click();await page.locator('#grid .asset[data-asset-id="100"] .asset-open').waitFor();
  assert.equal(await page.locator('#grid .asset[data-asset-id="100"]').count(),1,'separated asset remains available once on the next collapsed-position page');
  await page.locator('#previous').click();await page.locator('.photo-stack-count').waitFor();
  await page.locator('#photo-stack-reset').click();await page.locator('#grid .asset[data-asset-id="102"] .photo-stack-count').waitFor();
  assert.equal(preferenceBodies.at(-1).reset,'1');assert.equal(preferenceBodies.at(-1).group_id,'');assert.equal(preferenceBodies.at(-1).revision,'2');
  check('twelve collapsed positions, cross-page uniqueness, full member visibility, persisted cover/separate/reset choices');

  let preferenceStart=preferenceBodies.length;
  preferenceFailureStatus=409;
  await page.locator('#grid .asset[data-asset-id="102"] .photo-stack-action[data-stack-action="expand"]').click();
  await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-action[data-stack-action="cover"]').click();
  await page.locator('#grid .asset[data-asset-id="102"] .photo-stack-count').waitFor();
  assert.equal(preferenceBodies.length,preferenceStart+1,'a stale-choice response is followed by one read and no write replay');
  assert.equal(preferenceBodies.at(-1).cover_asset_id,'101');
  check('409 choice conflict refreshes without replaying a write');

  preferenceStart=preferenceBodies.length;
  preferenceUnknownStatus=503;
  await page.locator('#grid .asset[data-asset-id="102"] .photo-stack-action[data-stack-action="expand"]').click();
  await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-action[data-stack-action="cover"]').click();
  await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-count').waitFor();
  assert.equal(preferenceBodies.length,preferenceStart+1,'an unknown write outcome is reconciled by reading, with no write replay');
  check('unknown preference outcome reconciles through a read only');

  preferenceStart=preferenceBodies.length;holdPreference=true;const duplicateHeld=new Promise(resolve=>heldResolve=resolve);
  await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-action[data-stack-action="expand"]').click();
  const duplicateChoice=page.locator('#grid .asset[data-asset-id="102"] .photo-stack-action[data-stack-action="cover"]');
  await duplicateChoice.click();await duplicateHeld;
  assert.equal(await duplicateChoice.isDisabled(),true,'all saved-choice controls are disabled during a write');
  await duplicateChoice.evaluate(node=>node.dispatchEvent(new MouseEvent('click',{bubbles:true})));
  assert.equal(preferenceBodies.length,preferenceStart+1,'a second click cannot submit against the same preference revision');
  release();await page.locator('#grid .asset[data-asset-id="102"] .photo-stack-count').waitFor();
  check('in-flight choice is single-flight even for a repeated click');

  preferenceStart=preferenceBodies.length;preferenceFailureStatus=403;
  await page.locator('#grid .asset[data-asset-id="102"] .photo-stack-action[data-stack-action="expand"]').click();
  await page.locator('#grid .asset[data-asset-id="100"] .photo-stack-action[data-stack-action="separate"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('#grid>.asset').length===0);
  await page.locator('#status').getByText(/访问权限已发生变化|access changed/).waitFor();
  assert.equal(await cards().count(),0,'denied preference writes clear the previously protected gallery during access recovery');
  assert.equal(preferenceBodies.length,preferenceStart+1,'the denied preference request was not retried');
  await page.locator('#refresh').click();await page.locator('.photo-stack-count').waitFor();
  check('403 preference denial invokes normal access recovery and hides the protected gallery');

  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.fontSize='150%';document.body.style.fontSize='150%';});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'Chinese controls fit at 150% text on a phone viewport');
  await page.locator('.photo-stack-count').locator('xpath=ancestor::article').locator('.photo-stack-action[data-stack-action="expand"]').click();
  await page.locator('#grid .asset[data-asset-id="100"]').waitFor();
  await page.screenshot({path:path.join(artifacts,'library-photo-stacks-phone-zh-150.png'),fullPage:true});
  await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='en');
  await page.locator('#photo-stack-status').getByText(/only you/).waitFor();
  assert.match(await page.locator('#photo-stack-status').textContent(),/only you/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'English controls fit at 150% text on a phone viewport');
  await page.locator('.photo-stack-count').locator('xpath=ancestor::article').locator('.photo-stack-action[data-stack-action="expand"]').click();
  await page.locator('#grid .asset[data-asset-id="100"]').waitFor();
  await page.screenshot({path:path.join(artifacts,'library-photo-stacks-phone-en-150.png'),fullPage:true});
  check('Chinese and English library-scope labels render at 150% text');

  malformed=true;let before=requests.length;await page.locator('#refresh').click();await page.locator('#photo-stack-status').getByText(/suggestions|分组建议/).waitFor();
  assert.equal(await page.locator('.photo-stack-count').count(),0,'malformed v2 envelope cannot hide any ordinary asset');
  assert(requests.slice(before).some(item=>item.method==='GET'&&new URL('https://photohouse.test'+item.path).pathname==='/assets'&&!new URL('https://photohouse.test'+item.path).searchParams.has('photo_stacks')),'invalid envelope falls back to ordinary assets');
  malformed=false;check('invalid v2 metadata fails open through ordinary assets');

  unsupported=true;before=requests.length;await page.locator('#refresh').click();await page.locator('#photo-stack-toggle').waitFor({state:'visible'});
  const fallback=requests.slice(before).filter(item=>item.method==='GET'&&new URL('https://photohouse.test'+item.path).pathname==='/assets');
  assert.equal(fallback.filter(item=>new URL('https://photohouse.test'+item.path).searchParams.get('photo_stacks')==='1').length,1,'404 uses one legacy optional-extension fallback');
  assert.equal(fallback.filter(item=>!new URL('https://photohouse.test'+item.path).searchParams.has('photo_stacks')).length,0);unsupported=false;
  serverError=true;before=requests.length;await page.locator('#refresh').click();await page.waitForTimeout(300);
  assert.equal(requests.slice(before).filter(item=>item.method==='GET'&&new URL('https://photohouse.test'+item.path).pathname==='/assets').length,0,'non-404 errors are not treated as an unsupported extension');serverError=false;
  check('404 fallback is narrow; server errors do not trigger fallback');

  await page.reload();await page.locator('.photo-stack-count').waitFor();holdPreference=true;const held=new Promise(resolve=>heldResolve=resolve);
  const firstCover=page.locator('.photo-stack-count').locator('xpath=ancestor::article');await firstCover.locator('.photo-stack-action[data-stack-action="expand"]').click();
  await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-action[data-stack-action="cover"]').click();await held;
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});await signIn('+12025550101');
  await page.locator('#grid .asset[data-asset-id="202"]').waitFor();release();await page.waitForTimeout(300);
  assert.equal(await page.locator('#grid .asset[data-asset-id="202"]').count(),1,'late preference response cannot update another account gallery');
  assert.equal(await page.locator('#grid .asset[data-asset-id="101"]').count(),0,'previous account member does not reappear after late reply');
  assert.deepEqual(outside,[]);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checks:['cross-page group appears once','viewer members remain in ordinary sequence','cover/separate/reset refetch','409 and unknown outcomes reconcile without write replay','preference writes are single-flight','401/403 invoke access recovery and clear protected media','account-scoped late reply is discarded','404 fallback and malformed-envelope behavior','Chinese and English 150% full-gallery renders'],browser:browser.version(),outsideRequests:outside,pageErrors:errors,evidence:'Synthetic migrated SQLite, generated media and Chromium only; no household account or media'},null,2));
  console.log(`Library photo-stack browser checks complete. Artifacts: ${artifacts}`);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{release();if(browser)await browser.close();if(!bridge.stdin.destroyed&&!bridge.stdin.writableEnded)bridge.stdin.end(JSON.stringify({id:++serial,command:'quit'})+'\n');});
