/* Real synthetic gallery API -> Chromium, using no listening server or family media. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-photo-stacks-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||'python3',[path.join(__dirname,'photo_stacks_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0;const pending=new Map();let readyResolve,readyReject;
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const message=JSON.parse(line);if(message.ready){readyResolve();return;}const item=pending.get(message.id);if(item){pending.delete(message.id);item.resolve(message);}});
bridge.on('exit',code=>{if(code){readyReject(new Error('Synthetic gallery bridge exited '+code));for(const item of pending.values())item.reject(new Error('Synthetic gallery bridge exited'));}});
function rpc(request){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({id,request})+'\n');});}
let browser,context,page;const errors=[],outside=[],requests=[];
let unsupported=false,malformed=false,omitExtension=false,holdLibrary=null,heldResolve,releaseHeld;
function release(){releaseHeld?.();releaseHeld=null;}
async function startContext(){
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){outside.push(url.origin);await route.abort();return;}
    requests.push({method:request.method(),path:url.pathname+url.search});
    if(request.method()==='GET'&&url.pathname==='/assets'&&url.searchParams.get('photo_stacks')==='1'&&unsupported){
      await route.fulfill({status:404,headers:{'content-type':'application/json'},body:'{"detail":"unsupported"}'});return;
    }
    const headers=await request.allHeaders();
    if(!headers['sec-fetch-site']){
      let origin='';try{origin=new URL(request.frame().url()).origin;}catch{}
      headers['sec-fetch-site']=origin===url.origin?'same-origin':'none';
    }
    delete headers['content-length'];
    let response=await rpc({method:request.method(),path:url.pathname+url.search,headers,
      body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    if(request.method()==='GET'&&url.pathname==='/assets'&&url.searchParams.get('photo_stacks')==='1'&&malformed&&response.status===200){
      const body=JSON.parse(Buffer.from(response.body,'base64').toString());
      if(body.photo_stacks?.groups?.length)body.photo_stacks.groups[0].count+=1;
      response.body=Buffer.from(JSON.stringify(body)).toString('base64');
    }
    if(request.method()==='GET'&&url.pathname==='/assets'&&url.searchParams.get('photo_stacks')==='1'&&omitExtension&&response.status===200){
      const body=JSON.parse(Buffer.from(response.body,'base64').toString());delete body.photo_stacks;
      response.body=Buffer.from(JSON.stringify(body)).toString('base64');
    }
    if(request.method()==='GET'&&url.pathname==='/assets'&&url.searchParams.get('library')===holdLibrary&&url.searchParams.get('photo_stacks')==='1'){
      heldResolve?.();await new Promise(resolve=>releaseHeld=resolve);
    }
    const responseHeaders={...response.headers};delete responseHeaders['content-length'];delete responseHeaders['content-encoding'];
    try{await route.fulfill({status:response.status,headers:responseHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|canceled|cancelled|Invalid InterceptionId/.test(error.message))throw error;}
  });
  context.on('page',target=>target.on('pageerror',error=>errors.push(error.message)));
  page=await context.newPage();
}
async function signIn(){
  await page.goto('https://photohouse.test/ui');
  await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN','Chinese is the default locale');
  await page.locator('#login-tab').click();
  await page.locator('#phone').fill('+12025550102');
  await page.locator('#password').fill('Synthetic family passphrase!');
  await page.locator('#auth-submit').click();
  await page.locator('#library').waitFor({state:'visible',timeout:15000});
  await page.locator('.asset').first().waitFor({timeout:15000});
}
const cards=()=>page.locator('#grid>.asset');
const check=message=>console.log('PASS '+message);
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  await startContext();await signIn();
  assert.equal(await page.locator('#photo-stack-toggle').textContent(),'显示全部照片');
  assert.equal(await page.locator('#photo-stack-status').textContent(),'','the success toolbar shows its grouping help only once');
  assert.equal(await page.locator('.photo-stack-count').count(),1);
  assert.match(await page.locator('.photo-stack-count').textContent(),/3 张照片/);
  await page.locator('#grid .asset[data-asset-id="102"] img').evaluate(image=>image.decode());
  assert(await page.locator('#grid .asset[data-asset-id="102"] img').evaluate(image=>image.naturalWidth>0),'cover uses a generated, valid synthetic thumbnail');
  assert.equal(await cards().count(),3,'the 100/101/102 photo stack is represented by one card while video and standalone photo remain visible');
  assert.equal(await page.locator('#grid .asset[data-asset-id="104"]').count(),1,'normal video remains in the gallery');
  assert.equal(await page.locator('#grid .asset[data-asset-id="106"]').count(),1,'unmatched photo remains in the gallery');
  await page.locator('#photo-stack-toggle').click();assert.equal(await cards().count(),5,'show-all restores every page item');
  await page.locator('#photo-stack-toggle').click();assert.equal(await cards().count(),3,'stack mode collapses only validated members');
  const expandControl=page.locator('#grid .photo-stack-action[data-stack-action="expand"]');await expandControl.focus();await expandControl.press('Enter');
  assert.equal(await page.locator('#grid .asset[data-asset-id="100"],#grid .asset[data-asset-id="101"],#grid .asset[data-asset-id="102"]').count(),3,'expansion exposes all three originals');
  assert.equal(await page.evaluate(()=>document.activeElement?.dataset.stackAction),'collapse','keyboard expansion transfers focus to the new collapse control');
  await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement?.dataset.stackAction),'expand','keyboard collapse transfers focus back to the new expand control');
  await page.keyboard.press('Enter');assert.equal(await page.locator('#grid .asset[data-asset-id="100"],#grid .asset[data-asset-id="101"],#grid .asset[data-asset-id="102"]').count(),3,'keyboard re-expansion keeps all originals available');
  assert.equal(await page.locator('#grid .photo-stack-action[data-stack-action="cover"]').count(),3,'each expanded photo has a view-only cover choice');
  await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-action[data-stack-action="cover"]').click();
  assert.equal(await page.locator('#grid .photo-stack-action[data-stack-action="cover"][aria-current="true"]').count(),1,'chosen cover is reflected with a current state');
  await page.locator('#grid .photo-stack-action[data-stack-action="collapse"]').click();
  assert.equal(await page.locator('#grid .asset[data-asset-id="101"] .photo-stack-count').count(),1,'collapsing uses the newly chosen cover');
  await page.locator('#grid .photo-stack-action[data-stack-action="expand"]').click();
  await page.locator('#grid .asset[data-asset-id="100"] .photo-stack-action[data-stack-action="separate"]').click();
  assert.equal(await cards().count(),5,'separating a stack-id member keeps the two-member stack expanded and all page items visible');
  for(const id of ['100','101','102'])assert.equal(await page.locator(`#grid .asset[data-asset-id="${id}"]`).count(),1,`original ${id} occurs exactly once after separation`);
  await page.locator('#refresh').click();await page.locator('.photo-stack-count').waitFor();
  const coverCard=page.locator('#grid .asset[data-asset-id="102"]');
  await coverCard.click();
  await page.locator('#viewer').waitFor({state:'visible'});
  await page.locator('#viewer-sequence').waitFor({state:'visible'});
  assert.match(await page.locator('#view-position').textContent(),/2 \/ 5/,'viewer sequence retains the full uncollapsed page');
  await page.locator('#view-next').click();await page.waitForFunction(()=>document.querySelector('#viewer-title')?.textContent.includes('100'));
  await page.locator('#close-viewer').click();
  check('Chinese default, stack/show-all, video visibility, expand, cover choice, separate-original control and full-page viewer sequence');

  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>{document.documentElement.style.fontSize='150%';document.body.style.fontSize='150%';});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'150% large text at phone width has no horizontal overflow');
  await page.locator('#photo-stack-tools').screenshot({path:path.join(artifacts,'photo-stacks-phone-zh-150.png')});
  await page.screenshot({path:path.join(artifacts,'photo-stacks-phone-gallery-zh-150.png')});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>{document.documentElement.style.fontSize='100%';document.body.style.fontSize='100%';});
  await page.locator('#photo-stack-tools').screenshot({path:path.join(artifacts,'photo-stacks-desktop-zh.png')});
  await page.evaluate(()=>window.scrollTo(0,Math.max(0,document.querySelector('#photo-stack-tools').getBoundingClientRect().top+scrollY-120)));
  await page.screenshot({path:path.join(artifacts,'photo-stacks-desktop-gallery-zh.png')});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.fontSize='150%';document.body.style.fontSize='150%';});
  await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='en'&&document.querySelector('.photo-stack-count'));
  assert.equal(await page.locator('#photo-stack-toggle').textContent(),'Show all photos');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'English labels at 150% text stay within the phone viewport');
  await page.locator('#photo-stack-tools').screenshot({path:path.join(artifacts,'photo-stacks-phone-en-150.png')});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>{document.documentElement.style.fontSize='100%';document.body.style.fontSize='100%';});
  await page.locator('#photo-stack-tools').screenshot({path:path.join(artifacts,'photo-stacks-desktop-en.png')});
  await page.evaluate(()=>window.scrollTo(0,Math.max(0,document.querySelector('#photo-stack-tools').getBoundingClientRect().top+scrollY-120)));
  await page.screenshot({path:path.join(artifacts,'photo-stacks-desktop-gallery-en.png')});
  await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='zh-CN'&&document.querySelector('.photo-stack-count'));
  check('Chinese and English controls render at desktop and phone widths; both phone locales fit at 150% text');

  omitExtension=true;await page.locator('#refresh').click();
  await page.locator('#photo-stack-status').getByText('分组建议', {exact:false}).waitFor();
  assert.equal(await page.locator('#photo-stack-toggle').isVisible(),false,'a missing optional extension never activates hiding');
  assert.equal(await cards().count(),5,'a 200 response with no extension shows every page item');omitExtension=false;
  check('missing optional metadata fails open with every photo and video visible');

  malformed=true;await page.locator('#refresh').click();
  await page.locator('#photo-stack-status').getByText('分组建议', {exact:false}).waitFor();
  assert.equal(await page.locator('#photo-stack-toggle').isVisible(),false,'malformed group metadata never activates hiding');
  assert.equal(await cards().count(),5,'malformed metadata falls back to all page items');malformed=false;
  check('malformed extension metadata fails open with all photos and video visible');

  unsupported=true;const beforeFallback=requests.length;await page.locator('#refresh').click();
  await page.locator('#photo-stack-status').getByText('暂不支持', {exact:false}).waitFor();
  const fallbackCalls=requests.slice(beforeFallback).filter(item=>item.method==='GET'&&new URL('https://photohouse.test'+item.path).pathname==='/assets');
  assert.equal(fallbackCalls.filter(item=>new URL('https://photohouse.test'+item.path).searchParams.has('photo_stacks')).length,1,'unsupported opt-in is requested once');
  assert.equal(fallbackCalls.filter(item=>!new URL('https://photohouse.test'+item.path).searchParams.has('photo_stacks')).length,1,'only an explicit 404 triggers one unflagged fallback');
  assert.equal(await cards().count(),5);unsupported=false;
  check('unsupported extension uses one explicit 404 fallback and no polling or automatic retry');

  holdLibrary='family-b';const arrived=new Promise(resolve=>heldResolve=resolve);
  await page.locator('#library-select').selectOption('family-b');await arrived;
  assert.equal(await cards().count(),0,'switching library clears the old page before the new page response');
  holdLibrary=null;
  await page.locator('#library-select').selectOption('family-a');
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('#grid .asset')).some(card=>card.dataset.assetId==='104'));
  release();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('#grid .asset')).some(card=>card.dataset.assetId==='104'));
  assert.equal(await page.locator('#grid .asset[data-asset-id="202"]').count(),0,'late library-B response cannot repopulate library-A grid');
  check('library switch clears stale page content and a late response from its prior scope is discarded');

  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await cards().count(),0,'logout removes all prior gallery cards');
  assert.equal(await page.locator('#photo-stack-tools').isVisible(),false,'logout clears grouping UI state');
  assert.equal(await page.evaluate(()=>Object.keys(localStorage).some(key=>/photo.?stack/i.test(key))),false,'stack member IDs and choices are not persisted in local storage');
  assert.deepEqual(outside,[]);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checks:['Chinese default and page-local stack controls','phone/desktop rendering at 150% text','malformed metadata fails open','404 fallback is one-shot','library change clears stale content','late scoped response is discarded','logout clears grouping state'],browser:browser.version(),outsideRequests:outside,pageErrors:errors,evidence:'Synthetic migrated SQLite and Chromium only; no household account or media'},null,2));
  console.log(`Photo stack browser checks complete. Artifacts: ${artifacts}`);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{release();if(browser)await browser.close();if(!bridge.stdin.destroyed&&!bridge.stdin.writableEnded)bridge.stdin.end(JSON.stringify({id:++serial,command:'quit'})+'\n');});
