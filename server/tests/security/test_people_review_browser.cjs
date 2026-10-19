/* Chromium owner journey over synthetic migrated SQLite and the real ASGI app. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-people-review-'));
fs.mkdirSync(artifacts,{recursive:true});
const python=process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python');
const pythonPath=[path.join(root,'backend'),path.join(root,'tests'),process.env.PYTHONPATH].filter(Boolean).join(path.delimiter);
const bridge=spawn(python,[path.join(__dirname,'people_review_browser_bridge.py')],{cwd:root,env:{...process.env,PYTHONPATH:pythonPath},stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve;const ready=new Promise(resolve=>readyResolve=resolve),pending=new Map();
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const m=JSON.parse(line);if(m.ready)readyResolve(m);else{pending.get(m.id)?.(m);pending.delete(m.id);}});
function rpc(message){return new Promise(resolve=>{const id=++serial;pending.set(id,resolve);bridge.stdin.write(JSON.stringify({...message,id})+'\n');});}
const errors=[],outside=[],requests=[],reviewBodies=[];let forcedPostStatus=null,loseNextPost=false,held=null,browser;
function holdNextReviewGet(){let release,arrive;const gate=new Promise(r=>release=r),arrived=new Promise(r=>arrive=r);held={gate,arrive};return {release,arrived};}
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  const context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!=='https://photohouse.test'){outside.push(url.origin);return route.abort();}
    const isReviewGet=req.method()==='GET'&&/\/admin\/people\/[^/]+\/review$/.test(url.pathname);
    if(isReviewGet&&held){const wait=held;held=null;wait.arrive();await wait.gate;}
    const headers=await req.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    let result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    requests.push({method:req.method(),path:url.pathname,status:result.status,...(result.status>=400?{body:Buffer.from(result.body,'base64').toString().slice(0,300)}:{})});
    if(req.method()==='POST'&&/\/admin\/faces\/[^/]+\/review$/.test(url.pathname)){
      reviewBodies.push(JSON.parse(req.postData()||'{}'));
      if(forcedPostStatus){result={status:forcedPostStatus,headers:{'content-type':'application/json','cache-control':'no-store'},body:Buffer.from(JSON.stringify({detail:'synthetic outcome'})).toString('base64')};forcedPostStatus=null;}
      else if(loseNextPost){loseNextPost=false;return route.abort();}
    }
    const outputHeaders={...result.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try{await route.fulfill({status:result.status,headers:outputHeaders,body:Buffer.from(result.body,'base64')});}catch(error){if(!/closed|handled|canceled|cancelled/.test(error.message))throw error;}
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto('https://photohouse.test/ui');
  await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#library').waitFor({state:'visible',timeout:10000}).catch(async error=>{throw new Error(`${error.message}; status=${await page.locator('#status').textContent()}; auth=${await page.locator('#auth-feedback').textContent()}; requests=${JSON.stringify(requests)}`);});
  assert.equal(await page.locator('#people-panel').isVisible(),true,`owner people panel unavailable: ${await page.locator('#status').textContent()}`);
  await page.locator('#people-panel > summary').click();
  const person=page.locator('.person-card[data-person-id="1"]');await person.waitFor();
  await person.getByRole('button',{name:'复核系统建议的人脸'}).click();
  const cards=page.locator('.people-review-card');await cards.first().waitFor();
  await page.waitForFunction(()=>[...document.querySelectorAll('.people-review-card img')].length>0&&[...document.querySelectorAll('.people-review-card img')].every(img=>img.complete&&img.naturalWidth>0));
  assert.equal(await page.locator('.people-review-card input[type=checkbox]:checked').count(),0,'faces must never be preselected');
  assert.equal(reviewBodies.length,0,'opening a queue must never save a confirmation');
  await page.screenshot({path:path.join(artifacts,'people-review-desktop-1280.png'),fullPage:true});
  await page.locator('#people-review').screenshot({path:path.join(artifacts,'people-review-panel-desktop-1280.png')});
  await page.locator('#language').click();
  await page.waitForFunction(()=>document.documentElement.lang==='en');
  await page.screenshot({path:path.join(artifacts,'people-review-desktop-1280-en.png'),fullPage:true});
  await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='zh-CN');
  await page.waitForFunction(()=>[...document.querySelectorAll('.people-review-card input[type=checkbox]')].every(input=>!input.disabled));
  await cards.nth(0).locator('input[type=checkbox]').check();
  await page.locator('#people-review-continue').click();
  assert.equal(await page.locator('#people-review-step .people-review-selected img').count(),1,'the final step shows only the selected crop');
  await page.screenshot({path:path.join(artifacts,'people-review-confirm-desktop-1280.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  await page.screenshot({path:path.join(artifacts,'people-review-confirm-mobile-390.png'),fullPage:true});
  await page.locator('#people-review').screenshot({path:path.join(artifacts,'people-review-panel-mobile-390-150.png')});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'mobile layout must not overflow');
  await page.evaluate(()=>{document.documentElement.style.fontSize='';});
  await page.locator('#people-review-step input[type=checkbox]').check();await page.locator('#people-review-step button.primary').click();
  await page.waitForFunction(()=>document.querySelector('#people-review-status').textContent.includes('已记录'));
  assert.equal(reviewBodies.length,1,'only one selected face is posted');assert.equal(reviewBodies[0].person_id,'1');
  assert.equal(requests.filter(item=>item.method==='POST'&&item.path.endsWith('/review')).length,1);
  await page.locator('#people-review-refresh').click();await cards.first().waitFor();
  await page.waitForFunction(()=>[...document.querySelectorAll('.people-review-card img')].length>0&&[...document.querySelectorAll('.people-review-card img')].every(img=>img.complete&&img.naturalWidth>0));
  await page.locator('.people-review-card').first().getByRole('button',{name:'人物不对'}).click();
  await page.locator('.face-picker').waitFor();
  await page.getByRole('button',{name:/Other sample/}).click();
  const correctedQueue=page.waitForResponse(response=>response.request().method()==='GET'&&new URL(response.url()).pathname==='/admin/people/1/review');
  await page.locator('.face-picker .assignment-review button').filter({hasText:'确认归属'}).click();
  await correctedQueue;
  await page.locator('.people-review-card').first().waitFor();
  await page.waitForFunction(()=>document.querySelectorAll('.people-review-card input[type=checkbox]:checked').length===0);
  assert.equal(await page.locator('.people-review-card input[type=checkbox]:checked').count(),0,'correction clears the batch selection');

  // Stale revision response clears the batch and offers a user initiated refresh, with no retry.
  forcedPostStatus=409;await page.locator('#people-review-refresh').click();await cards.first().waitFor();
  await page.waitForFunction(()=>[...document.querySelectorAll('.people-review-card img')].every(img=>img.complete&&img.naturalWidth>0));
  await page.locator('.people-review-card').first().locator('input[type=checkbox]').check();await page.locator('#people-review-continue').click();await page.locator('#people-review-step input[type=checkbox]').check();await page.locator('#people-review-step button.primary').click();
  await page.waitForFunction(()=>document.querySelector('#people-review-status').textContent.includes('人脸或人物信息已变化'));
  const afterConflict=reviewBodies.length;await page.waitForTimeout(100);assert.equal(reviewBodies.length,afterConflict,'409 must not be retried automatically');
  assert.equal(await page.locator('.people-review-card').count(),0,'stale batch is removed');
  await page.locator('#people-review-refresh').click();await cards.first().waitFor();

  // A lost response after the real ASGI save is uncertain; refreshing reconciles the queue.
  await page.waitForFunction(()=>[...document.querySelectorAll('.people-review-card img')].every(img=>img.complete&&img.naturalWidth>0));
  loseNextPost=true;await page.locator('.people-review-card').first().locator('input[type=checkbox]').check();await page.locator('#people-review-continue').click();await page.locator('#people-review-step input[type=checkbox]').check();await page.locator('#people-review-step button.primary').click();
  await page.waitForFunction(()=>document.querySelector('#people-review-status').textContent.includes('部分确认可能已保存'));
  const afterLost=reviewBodies.length;await page.waitForTimeout(100);assert.equal(reviewBodies.length,afterLost,'uncertain POST must not be retried');
  await page.locator('#people-review-refresh').click();await page.waitForFunction(()=>document.querySelector('#people-review-status').textContent.includes('没有可复核的人脸')||document.querySelectorAll('.people-review-card').length>0);

  // A late queue response from the previous authenticated generation cannot repopulate after logout.
  const delayed=holdNextReviewGet();await page.locator('#people-review-refresh').click();await delayed.arrived;
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});delayed.release();
  await page.waitForTimeout(100);assert.equal(await page.locator('#people-review').isVisible(),false);
  assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
  console.log(JSON.stringify({passed:['no automatic save and no preselection','selected-subset review step','390px and 1280px screenshots','explicit per-face confirmation','wrong-person picker clears prior selection','409 and unknown POST outcomes are never retried','stale account response is suppressed'],artifacts,posts:reviewBodies.length}));
  await context.close();
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.stdin.end();});
