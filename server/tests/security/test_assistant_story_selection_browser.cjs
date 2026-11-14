/* Generated browser journey for assistant result selection and story handoff. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-story-selection-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'../.venv/bin/python'),[path.join(__dirname,'assistant_story_selection_browser_bridge.py')],{
  cwd:root,env:{...process.env,PH_SCENE_FIXTURE:'1',PH_SCENE_PAGES:'1'},stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pending=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){readyResolve();return;}const call=pending.get(value.id);if(call){pending.delete(value.id);call.resolve(value);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Synthetic bridge exited (${code})`));for(const call of pending.values())call.reject(new Error('Synthetic bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const requests=[],blocked=[],errors=[],checks=[];
const startedAt=Date.now();
let failNextFreshCheck=null,holdFreshCheck=null,arriveFreshCheck=null,releaseFreshCheck=null;
const pass=name=>{checks.push(name);console.log('PASS '+name);};
const responseBody=response=>JSON.parse(Buffer.from(response.body,'base64').toString());
const freshReadPath=value=>/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/current-result(?:\?|$)/.test(value);
let browser,context,page;
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});context.setDefaultTimeout(15000);
  await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!=='https://photohouse.test'){blocked.push(url.origin);await route.abort();return;}
    const entry={method:req.method(),path:url.pathname+url.search,body:req.postData()||''};requests.push(entry);
    const isFreshReceipt=req.method()==='GET'&&freshReadPath(url.pathname+url.search);
    if(isFreshReceipt&&failNextFreshCheck){
      const status=failNextFreshCheck;failNextFreshCheck=null;await route.fulfill({status,contentType:'application/json',body:'{"detail":"synthetic fresh authorization denied"}'});return;
    }
    if(isFreshReceipt&&holdFreshCheck){
      const gate=holdFreshCheck;holdFreshCheck=null;arriveFreshCheck();await gate;
    }
    const headers={...await req.allHeaders()};delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const response=await rpc({method:req.method(),path:entry.path,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    entry.status=response.status;try{entry.response=responseBody(response);}catch{}
    const out={...response.headers};delete out['content-length'];delete out['content-encoding'];
    try{await route.fulfill({status:response.status,headers:out,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  page=await context.newPage();page.on('pageerror',error=>errors.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  await page.locator('[href="#assistant-panel"]').first().click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});await page.locator('#assistant-private-new').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-private-select')?.value&&!document.querySelector('#assistant-private-new').disabled);
  const turnPosts=()=>requests.filter(item=>item.method==='POST'&&/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(item.path));
  const search=async text=>{const before=turnPosts().length;if(await page.locator('#assistant-scene').evaluate(node=>node.open)&&await page.locator('#assistant-scene-back').isVisible())await page.locator('#assistant-scene-back').click();await page.locator('#assistant-text').fill(text);await page.locator('#assistant-send').click();await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);assert.equal(turnPosts().length,before+1);};
  const picks=()=>page.locator('.assistant-result .assistant-story-pick');
  const pickIds=()=>picks().evaluateAll(nodes=>nodes.map(node=>node.value));
  const selectedIds=()=>page.locator('#assistant-story-selected-list [data-asset-id]').evaluateAll(nodes=>nodes.map(node=>node.dataset.assetId));
  const count=()=>page.locator('#assistant-story-selection-count').innerText();
  const resultCards=page.locator('#assistant-results .assistant-result');
  await search('找示例儿童的视频');
  assert.deepEqual(turnPosts().at(-1).response.result.items.map(item=>item.kind),['video']);
  assert.equal(await picks().count(),1,'a video result also has an asset-bound selection control');
  await search('找示例儿童');
  assert.equal(await page.locator('.assistant-result').evaluateAll(cards=>cards.length>0),true);
  assert.equal(await page.locator('#assistant-story-selection').isVisible(),true);
  assert.match(await count(),/0\s*\/\s*24/);
  assert.equal(await picks().count(),await resultCards.count());
  assert.deepEqual(await resultCards.evaluateAll(cards=>cards.map(card=>card.dataset.assetId)),await pickIds());
  pass('Result cards expose asset-bound selection controls and an empty, visible selection toolbar');

  // A normal search result uses image fixtures; the separate video-filtered
  // turn above proved video controls, and scene pages below exercise persistence.
  const firstId=(await pickIds())[0],keyboardPick=page.locator(`.assistant-story-pick[value="${firstId}"]`);
  await keyboardPick.focus();await page.keyboard.press('Space');assert.equal(await keyboardPick.isChecked(),true);
  assert.deepEqual(await selectedIds(),[firstId]);assert.equal(new Set(await selectedIds()).size,1);assert.match(await count(),/1\s*\/\s*24/);
  await page.keyboard.press('Space');assert.equal(await keyboardPick.isChecked(),false);assert.match(await count(),/0\s*\/\s*24/);
  await keyboardPick.check();
  await page.locator('#assistant-story-selection-clear').click();assert.match(await count(),/0\s*\/\s*24/);
  await search('找示例儿童');
  assert.match(await count(),/0\s*\/\s*24/,'a new result turn starts with an empty selection');
  pass('Selection identities stay unique, Clear empties the choice, and a new result turn resets it');

  // The scene fixture has 46 synthetic images on three 20-item pages.
  if(!await page.locator('#assistant-scene').evaluate(node=>node.open))await page.locator('#assistant-scene > summary').click();
  await page.locator('#assistant-scene-text').fill('孩子 flying a kite 蓝桥旁');await page.locator('#assistant-scene-confirm').check();await page.locator('#assistant-scene-send').click();
  await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);assert.equal(await resultCards.count(),20);
  assert.equal(await page.locator('#assistant-scene-page-next').isEnabled(),true);
  const firstPage=await pickIds();assert.equal(new Set(firstPage).size,20);
  for(const id of firstPage.slice(0,20))await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  await page.locator('#assistant-scene-page-next').click();await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId!==expected,firstPage[0]);
  const secondPage=await pickIds();assert.equal(secondPage.length,20);
  for(const id of secondPage.slice(0,4))await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  assert.match(await count(),/24\s*\/\s*24/);assert.equal(await page.locator('#assistant-shape-story').isDisabled(),false);
  assert.deepEqual(await selectedIds(),[...firstPage,...secondPage.slice(0,4)]);
  const overflow=secondPage[4];assert.equal(await page.locator(`.assistant-story-pick[value="${overflow}"]`).isDisabled(),true);
  await page.locator('#assistant-scene-page-return').click();await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId===expected,firstPage[0]);
  assert.equal(await page.locator('.assistant-story-pick:checked').count(),20,'returning to page one retains its checked controls');
  assert.match(await count(),/24\s*\/\s*24/,'the cross-page count remains stable');
  assert.deepEqual(await selectedIds(),[...firstPage,...secondPage.slice(0,4)]);
  await page.setViewportSize({width:1280,height:900});
  await page.locator('#assistant-story-selection').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'assistant-selection-toolbar-desktop.png'),fullPage:false});
  await page.locator('#assistant-results .assistant-result').first().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'assistant-selection-cards-desktop.png'),fullPage:false});
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'assistant selection fits 390px at 150% text');
  await page.locator('#assistant-story-selection').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'assistant-selection-toolbar-phone-390-150.png'),fullPage:false});
  await page.locator('#assistant-results .assistant-result').first().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'assistant-selection-cards-phone-390-150.png'),fullPage:false});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  pass('Paging preserves deliberate selection order, deduplicates identities, and enforces the 24-item cap');

  // Remove an off-page item from the toolbar, then choose a 24th item again.
  const remote=secondPage[0];if(!await page.locator('#assistant-story-selected').evaluate(node=>node.open))await page.locator('#assistant-story-selected > summary').click();
  const removeRemote=page.locator(`#assistant-story-selected-list [data-asset-id="${remote}"]`);await removeRemote.focus();await page.keyboard.press('Space');
  assert.equal((await selectedIds()).includes(remote),false);assert.match(await count(),/23\s*\/\s*24/);
  await page.locator('#assistant-scene-page-next').click();await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId!==expected,firstPage[0]);
  await page.locator(`.assistant-story-pick[value="${overflow}"]`).check();
  assert.match(await count(),/24\s*\/\s*24/);

  // Hold the exact receipt read, then change scope by logging out before the
  // late result can open the editor.
  const lateArrival=new Promise(resolve=>arriveFreshCheck=resolve);holdFreshCheck=new Promise(resolve=>releaseFreshCheck=resolve);
  const beforeLate=requests.length;
  await page.locator('#assistant-shape-story').click();await lateArrival;
  assert.equal(await page.locator('#assistant-shape-story').isDisabled(),true,'the action stays disabled while its fresh receipt is pending');
  assert.match(await page.locator('#assistant-story-selection-status').innerText(),/核对|checking/i);
  await page.locator('#assistant-workspace-lock').click();await page.locator('#auth').waitFor({state:'visible'});
  releaseFreshCheck();holdFreshCheck=null;await page.waitForTimeout(100);
  assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),false,'late receipt after logout cannot open the editor');
  assert.equal(requests.slice(beforeLate).some(item=>item.method==='POST'&&item.path==='/story-workspace/preview'),false);
  assert.equal(requests.slice(beforeLate).some(item=>item.method==='POST'&&item.path==='/memory-stories'),false);
  pass('Logout invalidates a pending handoff; its late fresh receipt cannot prepare or save a story');

  // Reauthenticate, start a new private search and prepare its selected IDs.
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  await page.locator('[href="#assistant-panel"]').first().click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});await page.locator('#assistant-private-new').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-private-select')?.value&&!document.querySelector('#assistant-private-new').disabled);
  await search('找示例儿童');assert.match(await count(),/0\s*\/\s*24/);
  const broadTurn=turnPosts().at(-1).response.result;assert.equal(broadTurn.total,46);assert.equal(await picks().count(),20);
  const pageOne=await pickIds();await page.locator(`.assistant-story-pick[value="${pageOne[0]}"]`).check();
  for(let pageNumber=0;pageNumber<2;pageNumber++){
    const first=(await pickIds())[0];await page.locator('#assistant-result-page-next').click();
    await page.waitForFunction(expected=>{const card=document.querySelector('.assistant-result');return card&&card.dataset.assetId!==expected;},first);
  }
  const finalPage=await pickIds();assert(finalPage.includes('102')&&finalPage.includes('101'),'last ordinary result page contains the synthetic video and photo');
  const finalPageResult=requests.filter(item=>item.method==='POST'&&/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/result-pages(?:\?|$)/.test(item.path)).at(-1).response;
  assert.equal(finalPageResult.items.find(item=>item.id==='102').kind,'video');assert.equal(finalPageResult.items.find(item=>item.id==='101').kind,'image');
  await page.locator('.assistant-story-pick[value="102"]').check();await page.locator('.assistant-story-pick[value="101"]').check();
  const expectedOrder=[pageOne[0],'102','101'];assert.deepEqual(await selectedIds(),expectedOrder);
  await page.locator('#assistant-result-page-return').click();await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId===expected,pageOne[0]);
  assert.equal(await page.locator(`.assistant-story-pick[value="${pageOne[0]}"]`).isChecked(),true);
  assert.deepEqual(await selectedIds(),expectedOrder,'ordinary page return preserves mixed media and deliberate order');
  const ordinaryPageGets=requests.filter(item=>item.method==='GET'&&/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/result-pages(?:\?|$)/.test(item.path)).length;
  const ordinaryPagePosts=requests.filter(item=>item.method==='POST'&&/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/result-pages(?:\?|$)/.test(item.path)).length;
  assert(ordinaryPageGets+ordinaryPagePosts>=2,'later ordinary result pages were fetched without another search turn');
  const beforeSuccess=requests.length;await page.locator('#assistant-shape-story').click();
  await page.locator('#story-workspace').waitFor({state:'visible'});
  const check=requests.slice(beforeSuccess).find(item=>item.method==='GET'&&freshReadPath(item.path));assert(check,'story handoff reads the exact fresh current result');
  const editorIds=await page.locator('#story-selection input').evaluateAll(nodes=>nodes.map(node=>node.value));
  assert.equal(await page.locator('#story-selection input:checked').count(),editorIds.length);
  assert.deepEqual(editorIds,expectedOrder);
  assert.equal(await page.locator('#story-reader').isVisible(),false);
  assert.equal(requests.slice(beforeSuccess).some(item=>item.method==='POST'&&item.path==='/memory-stories'),false,'opening the editor never saves');
  assert.equal(requests.slice(beforeSuccess).some(item=>item.method==='POST'&&item.path==='/story-workspace/preview'),false,'opening the editor does not generate a story preview');
  await page.waitForFunction(expected=>{const images=[...document.querySelectorAll('#story-selection img')];return images.length===expected&&images.every(image=>image.complete&&image.naturalWidth>0);},expectedOrder.length);
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  await page.locator('#story-selection').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'story-editor-selection-desktop.png'),fullPage:false});
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'phone layout has no horizontal overflow at 150% text');
  await page.locator('#story-selection').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'story-editor-selection-phone-390-150.png'),fullPage:false});
  assert.equal(requests.slice(beforeSuccess).some(item=>item.method==='POST'&&item.path==='/memory-stories'),false);
  pass('Fresh current-result check opens the editor with only the ordered selected IDs, all checked, without saving or previewing');

  // Refinement starts a new query turn and must clear the previous selection.
  await page.locator('#story-workspace-close').click();await page.waitForFunction(()=>!document.querySelector('#story-workspace').open);
  await page.locator('[href="#assistant-panel"]').first().click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  await page.locator('#assistant-private-new').click();await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  await search('找示例儿童');await picks().first().check();assert.match(await count(),/1\s*\/\s*24/);
  await search('找示例儿童的照片');assert.match(await count(),/0\s*\/\s*24/);
  assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),false);
  pass('A later refined/new assistant turn clears story selection');
  await picks().first().check();
  failNextFreshCheck=403;const beforeDenied=requests.length;
  const deniedReceipt=page.waitForResponse(response=>response.request().method()==='GET'&&freshReadPath(new URL(response.url()).pathname+new URL(response.url()).search)&&response.status()===403);
  await page.locator('#assistant-shape-story').click();await deniedReceipt;
  await page.waitForFunction(()=>/暂时|无法|unavailable/i.test(document.querySelector('#assistant-status')?.textContent||'')&&
    /0\s*\/\s*24/.test(document.querySelector('#assistant-story-selection-count')?.textContent||''));
  assert.equal(await page.locator('.assistant-story-pick:checked').count(),0,'a denied fresh check clears stale result selections');
  assert.equal(await page.locator('#assistant-shape-story').isDisabled(),true,'the handoff action remains disabled after permission denial');
  assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),false);
  assert.equal(await page.locator('#auth').isVisible(),false,'a failed fresh result check does not sign out an otherwise authorized page');
  assert.equal(requests.slice(beforeDenied).some(item=>item.method==='POST'&&item.path==='/story-workspace/preview'),false);
  assert.equal(requests.slice(beforeDenied).some(item=>item.method==='POST'&&item.path==='/memory-stories'),false);
  pass('A fresh permission denial blocks story preparation and saving');
  assert.deepEqual(blocked,[],'all external origins are blocked without a successful outside request');assert.deepEqual(errors,[]);
  const pageCalls=requests.filter(item=>/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/result-pages(?:\?|$)/.test(item.path));
  const receiptCalls=requests.filter(item=>item.method==='GET'&&freshReadPath(item.path));
  const summary={checks,elapsed_ms:Date.now()-startedAt,assistant_turn_posts:turnPosts().length,result_page_posts:pageCalls.filter(item=>item.method==='POST').length,
    fresh_current_result_gets:receiptCalls.length,story_outline_posts:requests.filter(item=>item.method==='POST'&&item.path==='/story-workspace/preview').length,
    story_saves:requests.filter(item=>item.method==='POST'&&item.path==='/memory-stories').length,requests:requests.length,
    blockedOrigins:blocked,pageErrors:errors,syntheticBackend:true};
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify(summary,null,2));
  console.log('RESULT '+JSON.stringify({...summary,artifacts}));
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{try{if(holdFreshCheck)releaseFreshCheck();if(browser)await browser.close();}finally{try{bridge.stdin.write('{"command":"quit"}\n');bridge.kill();}catch{}}});
