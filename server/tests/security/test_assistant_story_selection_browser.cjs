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
let failNextFreshCheck=null,holdFreshCheck=null,arriveFreshCheck=null,releaseFreshCheck=null,settleHeldFreshCheck=null;
let holdStoryPreview=null,arriveStoryPreview=null,releaseStoryPreview=null,settleHeldStoryPreview=null;
const pass=name=>{checks.push(name);console.log('PASS '+name);};
const responseBody=response=>JSON.parse(Buffer.from(response.body,'base64').toString());
const freshReadPath=value=>/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/current-result(?:\?|$)/.test(value);
const storyPreviewPath=value=>/\/story-workspace\/preview(?:\?|$)/.test(value);
const memoryStoryPath=value=>/\/memory-stories(?:\?|$)/.test(value);
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
    const isStoryPreview=req.method()==='POST'&&url.pathname==='/story-workspace/preview';
    if(isStoryPreview&&holdStoryPreview){
      const gate=holdStoryPreview;holdStoryPreview=null;arriveStoryPreview();await gate;
    }
    const headers={...await req.allHeaders()};delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const response=await rpc({method:req.method(),path:entry.path,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    entry.status=response.status;try{entry.response=responseBody(response);}catch{}
    const out={...response.headers};delete out['content-length'];delete out['content-encoding'];
    try{await route.fulfill({status:response.status,headers:out,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
    finally{
      if(isFreshReceipt&&settleHeldFreshCheck){const settle=settleHeldFreshCheck;settleHeldFreshCheck=null;settle();}
      if(isStoryPreview&&settleHeldStoryPreview){const settle=settleHeldStoryPreview;settleHeldStoryPreview=null;settle();}
    }
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
  assert.equal(requests.slice(beforeLate).some(item=>item.method==='POST'&&storyPreviewPath(item.path)),false);
  assert.equal(requests.slice(beforeLate).some(item=>item.method==='POST'&&memoryStoryPath(item.path)),false);
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
  const editorIds=await page.locator('#story-selection input:checked').evaluateAll(nodes=>nodes.map(node=>node.value));
  assert.equal(await page.locator('#story-selection input:checked').count(),editorIds.length);
  assert.deepEqual(editorIds,expectedOrder);
  assert.equal(await page.locator('#story-reader').isVisible(),false);
  assert.equal(requests.slice(beforeSuccess).some(item=>item.method==='POST'&&memoryStoryPath(item.path)),false,'opening the editor never saves');
  assert.equal(requests.slice(beforeSuccess).some(item=>item.method==='POST'&&storyPreviewPath(item.path)),false,'opening the editor does not generate a story preview');
  await page.waitForFunction(expected=>{const images=[...document.querySelectorAll('#story-selection img')];return images.length===expected&&images.every(image=>image.complete&&image.naturalWidth>0);},expectedOrder.length);
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  await page.locator('#story-selection').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'story-editor-selection-desktop.png'),fullPage:false});
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'phone layout has no horizontal overflow at 150% text');
  await page.locator('#story-selection').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'story-editor-selection-phone-390-150.png'),fullPage:false});
  assert.equal(requests.slice(beforeSuccess).some(item=>item.method==='POST'&&memoryStoryPath(item.path)),false);
  pass('Fresh current-result check opens the editor with only the ordered selected IDs, all checked, without saving or previewing');

  // Keep one image in the story selection so the video and photo from the
  // final result page remain eligible as new frames in the append journey.
  for(const id of editorIds.slice(1))await page.locator(`#story-selection input[value="${id}"]`).uncheck();
  const initialStoryTitle='周末沿着河边散步';
  const storyTheme=page.locator('#story-workspace-theme');
  await page.locator('#story-workspace-title').fill(initialStoryTitle);await storyTheme.selectOption('trip');
  let initialStoryIds=[editorIds[0]];
  const preArrangeTurns=turnPosts().length;
  await page.locator('#story-find-more-frames').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),true,'Find more frames keeps the unarranged story open underneath Assistant');
  assert.match(await page.locator('#assistant-shape-story').innerText(),/添加所选画面|Add selected frames/i);
  assert.match(await page.locator('#assistant-workspace-close').innerText(),/返回故事|Return to story/i);
  assert.equal(turnPosts().length,preArrangeTurns,'opening Assistant does not submit a search turn');
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/0\s*\/\s*23\b/,'the nested counter reports 23 available slots after the existing frame');
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'nested Assistant fits a 390px viewport at 150% text');
  await page.locator('#assistant-story-selection').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'story-append-assistant-phone-390-150.png'),fullPage:false});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  await search('找示例儿童');
  const preArrangeTurn=turnPosts().at(-1).response.result,preArrangeItems=preArrangeTurn.items;
  const preArrangePhoto=preArrangeItems.find(item=>item.kind==='image'&&!initialStoryIds.includes(item.id));assert(preArrangePhoto);
  const preArrangePick=page.locator(`.assistant-story-pick[value="${preArrangePhoto.id}"]`);await preArrangePick.check();
  const beforePreArrangeAppend=requests.length;
  await page.locator('#assistant-shape-story').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'hidden'});
  const twoFrameStoryIds=[...initialStoryIds,preArrangePhoto.id];
  await page.waitForFunction(expected=>JSON.stringify([...document.querySelectorAll('#story-selection input:checked')].map(node=>node.value))===JSON.stringify(expected),twoFrameStoryIds);
  initialStoryIds=twoFrameStoryIds;
  assert.equal(await page.locator('#story-workspace-title').inputValue(),initialStoryTitle,'pre-Arrange append keeps the authored title');
  assert.equal(await storyTheme.inputValue(),'trip','pre-Arrange append keeps the selected theme');
  assert.equal(requests.slice(beforePreArrangeAppend).filter(item=>item.method==='GET'&&freshReadPath(item.path)).length,1,'pre-Arrange append revalidates current results');
  assert.equal(requests.slice(beforePreArrangeAppend).some(item=>item.method==='POST'&&storyPreviewPath(item.path)),false,'pre-Arrange append does not create a story preview');
  assert.equal(requests.slice(beforePreArrangeAppend).some(item=>item.method==='POST'&&memoryStoryPath(item.path)),false,'pre-Arrange append does not save');
  pass('Pre-Arrange Find more frames appends a second photo while preserving title and theme without preview or save');

  await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();
  const firstChapter=page.locator('.story-chapter-card').first(),chapterTitleInput=firstChapter.locator('label input').first(),chapterNarrationInput=firstChapter.locator('textarea[maxlength="6000"]');
  const initialChapterTitle='沿河出发',initialNarration='先在桥边停一停，等大家都跟上，再继续往前走。';
  await chapterTitleInput.fill(initialChapterTitle);await chapterNarrationInput.fill(initialNarration);
  const storyValues=async()=>({title:await page.locator('#story-workspace-title').inputValue(),theme:await storyTheme.inputValue(),chapterTitle:await page.locator('.story-chapter-card').first().locator('label input').first().inputValue(),narration:await page.locator('.story-chapter-card').first().locator('textarea[maxlength="6000"]').inputValue(),ids:await page.locator('#story-selection input:checked').evaluateAll(nodes=>nodes.map(node=>node.value))});
  const beforeNestedValues=await storyValues();assert.deepEqual(beforeNestedValues,{title:initialStoryTitle,theme:'trip',chapterTitle:initialChapterTitle,narration:initialNarration,ids:twoFrameStoryIds});
  const beforeNestedTurns=turnPosts().length,beforeNestedSaves=requests.filter(item=>item.method==='POST'&&memoryStoryPath(item.path)).length;
  await page.locator('#story-find-more-frames').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),true,'Find more frames keeps the arranged draft open underneath Assistant');
  assert.equal(turnPosts().length,beforeNestedTurns,'opening nested Assistant does not submit a search turn');
  assert.equal(requests.filter(item=>item.method==='POST'&&memoryStoryPath(item.path)).length,beforeNestedSaves,'opening nested Assistant does not save the draft');
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/0\s*\/\s*22\b/,'the nested counter reports 22 remaining slots after two existing frames');
  await page.locator('#assistant-story-selection').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'story-append-assistant-desktop.png'),fullPage:false});
  pass('Opening nested Assistant leaves the arranged authored draft visible without another search or save');

  // A delayed current-result recheck is cancelled by Return to story. Its
  // eventual response must not append the tentative pick or disturb prose.
  await search('找示例儿童');
  const appendTurn=turnPosts().at(-1).response.result;assert.equal(appendTurn.total,46);
  const nestedPageOne=await pickIds();assert.equal(nestedPageOne.length,20);
  const duplicateId=initialStoryIds[0],duplicatePick=page.locator(`.assistant-story-pick[value="${duplicateId}"]`);
  assert.equal(await duplicatePick.isDisabled(),true,'a frame already in the story cannot be selected twice');
  const duplicateCopy=await duplicatePick.evaluate(node=>node.closest('.assistant-result')?.innerText||'');
  assert.match(duplicateCopy,/已在.*故事|已加入|already in (the )?story/i,'duplicate choice has localized Already in story guidance');
  const appendPhoto=nestedPageOne.find(id=>!initialStoryIds.includes(id));assert(appendPhoto,'page one has an additional synthetic photo');
  const appendPhotoItem=appendTurn.items.find(item=>item.id===appendPhoto);assert.equal(appendPhotoItem.kind,'image');
  for(const id of nestedPageOne.filter(id=>!initialStoryIds.includes(id)))await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  const firstPageId=nestedPageOne[0];await page.locator('#assistant-result-page-next').click();
  await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId!==expected,firstPageId);
  const nestedPageTwo=await pickIds();for(const id of nestedPageTwo.slice(0,4))await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/22\s*\/\s*22\b/,'the nested picker reaches the exact remaining-frame cap');
  assert.match(await page.locator('#assistant-story-selection-status').innerText(),/已选完|available new frames/i);
  const cappedCandidate=nestedPageTwo[4];assert(cappedCandidate);assert.equal(await page.locator(`.assistant-story-pick[value="${cappedCandidate}"]`).isDisabled(),true,'the next unchecked frame is disabled at the nested limit');
  await page.locator('#assistant-story-selection-clear').click();assert.match(await page.locator('#assistant-story-selection-count').innerText(),/0\s*\/\s*22\b/);
  await page.locator('#assistant-result-page-return').click();await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId===expected,nestedPageOne[0]);
  const tentative=page.locator(`.assistant-story-pick[value="${appendPhoto}"]`);await tentative.focus();await page.keyboard.press('Space');assert.equal(await tentative.isChecked(),true,'keyboard Space selects the additional photo');
  const lateReturn=new Promise(resolve=>arriveFreshCheck=resolve),freshReturned=new Promise(resolve=>settleHeldFreshCheck=resolve);
  holdFreshCheck=new Promise(resolve=>releaseFreshCheck=resolve);
  await page.locator('#assistant-shape-story').click();await lateReturn;
  assert.equal(await page.locator('#assistant-shape-story').isDisabled(),true,'nested append disables while the fresh receipt is pending');
  await page.locator('#assistant-workspace-close').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'hidden'});
  releaseFreshCheck();holdFreshCheck=null;await freshReturned;
  await page.waitForTimeout(100);
  assert.deepEqual(await storyValues(),beforeNestedValues,'Return to story discards the stale append and preserves all authored draft fields');
  assert.equal(requests.filter(item=>item.method==='POST'&&memoryStoryPath(item.path)).length,beforeNestedSaves);
  pass('Return to story cancels a delayed append and preserves frame order, title, theme and chapter prose');

  // Reopen and deliberately append one new photo followed by a video and a
  // photo from the final page. Existing story frames remain unavailable.
  const beforeReopenTurns=turnPosts().length;
  await page.locator('#story-find-more-frames').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  assert.equal(beforeReopenTurns,turnPosts().length,'reopening nested Assistant does not submit a search turn');
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/0\s*\/\s*22\b/,'reopening starts with no newly selected frames');
  await search('找示例儿童');
  const pageOneAppend=await pickIds(),pageOneItems=turnPosts().at(-1).response.result.items;
  const appendPhotoPick=page.locator(`.assistant-story-pick[value="${appendPhoto}"]`);await appendPhotoPick.focus();await page.keyboard.press('Space');
  assert.equal(await appendPhotoPick.isChecked(),true);assert.equal(pageOneItems.find(item=>item.id===appendPhoto).kind,'image');
  for(let pageNumber=0;pageNumber<2;pageNumber++){
    const first=(await pickIds())[0];await page.locator('#assistant-result-page-next').click();
    await page.waitForFunction(expected=>{const card=document.querySelector('.assistant-result');return card&&card.dataset.assetId!==expected;},first);
  }
  const appendFinalPage=await pickIds();assert(appendFinalPage.includes('102')&&appendFinalPage.includes('101'));
  const appendFinalResult=requests.filter(item=>item.method==='POST'&&/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/result-pages(?:\?|$)/.test(item.path)).at(-1).response;
  assert.equal(appendFinalResult.items.find(item=>item.id==='102').kind,'video');assert.equal(appendFinalResult.items.find(item=>item.id==='101').kind,'image');
  await page.locator('.assistant-story-pick[value="102"]').check();await page.locator('.assistant-story-pick[value="101"]').check();
  const appendedIds=[appendPhoto,'102','101'];assert.deepEqual(await selectedIds(),appendedIds,'new photo/video choices retain deliberate click order');
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/3\s*\/\s*22\b/);
  await page.locator('#assistant-result-page-return').click();await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId===expected,pageOneAppend[0]);
  // After Arrange, Add selected frames fetches fresh metadata via the story
  // preview endpoint. Hold that request and return to the draft while pending;
  // the late response must not overwrite or append into the authored draft.
  const heldPreviewArrival=new Promise(resolve=>arriveStoryPreview=resolve),heldPreviewSettled=new Promise(resolve=>settleHeldStoryPreview=resolve);
  holdStoryPreview=new Promise(resolve=>releaseStoryPreview=resolve);
  const beforeHeldPreview=requests.length,beforeHeldTurns=turnPosts().length;
  await page.locator('#assistant-shape-story').click();await heldPreviewArrival;
  const heldPreviewCall=requests.slice(beforeHeldPreview).find(item=>item.method==='POST'&&storyPreviewPath(item.path));
  assert(heldPreviewCall,'append with an arranged draft requests fresh story metadata');
  const heldPreviewBody=JSON.parse(heldPreviewCall.body);assert.deepEqual(heldPreviewBody.asset_ids.split(','),[...initialStoryIds,...appendedIds]);assert.equal(heldPreviewBody.title,'');
  await page.locator('#assistant-workspace-close').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'hidden'});
  releaseStoryPreview();holdStoryPreview=null;await heldPreviewSettled;
  await page.waitForTimeout(100);
  assert.deepEqual(await storyValues(),beforeNestedValues,'Return to story discards the late preview and retains all authored draft fields');
  assert.equal(requests.slice(beforeHeldPreview).filter(item=>item.method==='POST'&&memoryStoryPath(item.path)).length,0);
  assert.equal(turnPosts().length,beforeHeldTurns,'the held append and return do not start a new search turn');
  pass('Returning during a held append preview preserves the existing authored draft');

  const beforeAppendReopenTurns=turnPosts().length;
  await page.locator('#story-find-more-frames').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  assert.equal(turnPosts().length,beforeAppendReopenTurns,'reopening after a cancelled preview does not submit a search turn');
  await search('找示例儿童');
  const retryPageOne=await pickIds();assert(retryPageOne.includes(appendPhoto));
  await page.locator(`.assistant-story-pick[value="${appendPhoto}"]`).check();
  for(let pageNumber=0;pageNumber<2;pageNumber++){
    const first=(await pickIds())[0];await page.locator('#assistant-result-page-next').click();
    await page.waitForFunction(expected=>{const card=document.querySelector('.assistant-result');return card&&card.dataset.assetId!==expected;},first);
  }
  await page.locator('.assistant-story-pick[value="102"]').check();await page.locator('.assistant-story-pick[value="101"]').check();
  assert.deepEqual(await selectedIds(),appendedIds,'reselected append order remains photo, video, photo');
  await page.locator('#assistant-result-page-return').click();await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId===expected,retryPageOne[0]);
  const beforeAppend=requests.length,beforeAppendTurns=turnPosts().length,beforeAppendOutlines=requests.filter(item=>item.method==='POST'&&storyPreviewPath(item.path)).length;
  await page.locator('#assistant-shape-story').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'hidden'});
  assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),true,'Add selected frames returns to the existing story editor');
  const appendedStoryIds=[...initialStoryIds,...appendedIds];
  await page.waitForFunction(expected=>JSON.stringify([...document.querySelectorAll('#story-selection input:checked')].map(node=>node.value))===JSON.stringify(expected),appendedStoryIds);
  assert.deepEqual(await storyValues(),{title:initialStoryTitle,theme:'trip',chapterTitle:initialChapterTitle,narration:initialNarration,ids:appendedStoryIds});
  assert.equal(turnPosts().length,beforeAppendTurns,'fresh revalidation and append do not submit another search turn');
  assert.equal(requests.filter(item=>item.method==='POST'&&storyPreviewPath(item.path)).length,beforeAppendOutlines+1,'append fetches one fresh metadata preview without rebuilding chapter text');
  const appendPreview=requests.slice(beforeAppend).find(item=>item.method==='POST'&&storyPreviewPath(item.path));
  assert(appendPreview,'append performs a fresh metadata preview');
  const appendPreviewBody=JSON.parse(appendPreview.body);assert.deepEqual(appendPreviewBody.asset_ids.split(','),appendedStoryIds);assert.equal(appendPreviewBody.title,'');
  assert.equal(requests.slice(beforeAppend).filter(item=>item.method==='POST'&&memoryStoryPath(item.path)).length,0,'append never saves automatically');
  const appendedFreshReads=requests.slice(beforeAppend).filter(item=>item.method==='GET'&&freshReadPath(item.path));assert.equal(appendedFreshReads.length,1,'append revalidates the latest current result exactly once');

  // Explicitly save only after inspecting the preserved draft. This synthetic
  // save proves both the selection revision and chapter flattening order.
  const beforeExplicitSave=requests.length;await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>/Saved in this library|已保存/.test(document.querySelector('#story-workspace-status')?.textContent||''));
  const saveCall=requests.slice(beforeExplicitSave).find(item=>item.method==='POST'&&memoryStoryPath(item.path));assert(saveCall,'the explicit save action submits one synthetic story');
  const savedBody=JSON.parse(saveCall.body),savedChapters=JSON.parse(savedBody.chapters);
  assert.equal(savedBody.asset_ids,appendedStoryIds.join(','));assert.deepEqual(savedChapters.flatMap(chapter=>chapter.asset_ids),appendedStoryIds);
  assert.deepEqual(savedChapters.map(chapter=>chapter.asset_ids.length),[4,1],'combined selection fills the first chapter and creates the next chapter in order');
  assert.equal(savedChapters[0].title,initialChapterTitle);assert.equal(savedChapters[0].narration,initialNarration);
  assert.equal(savedBody.title,initialStoryTitle);assert.equal(savedBody.theme,'trip');assert.match(savedBody.selection_revision,/^[0-9a-f]{64}$/);
  assert.equal(saveCall.response.selection_revision,savedBody.selection_revision);assert.deepEqual(saveCall.response.items.map(item=>item.id),appendedStoryIds);
  assert.equal(requests.slice(beforeExplicitSave).filter(item=>item.method==='POST'&&memoryStoryPath(item.path)).length,1);
  pass('Nested Assistant appends ordered photo/video frames, preserves authored draft text, and explicit synthetic save stores the exact selection revision and order');

  const lastPhoto=retryPageOne.find(id=>!appendedStoryIds.includes(id));assert(lastPhoto);
  const updatePath=`/memory-stories/${saveCall.response.id}`;
  const isStoryUpdate=item=>item.method==='PUT'&&item.path.split('?')[0]===updatePath;
  await page.locator('#story-find-more-frames').click();
  await page.locator(`.assistant-story-pick[value="${lastPhoto}"]`).check();
  await page.locator('#assistant-shape-story').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'hidden'});
  const updatedStoryIds=[...appendedStoryIds,lastPhoto];
  assert.deepEqual(await storyValues(),{title:initialStoryTitle,theme:'trip',chapterTitle:initialChapterTitle,narration:initialNarration,ids:updatedStoryIds});
  assert.equal(requests.some(isStoryUpdate),false,'appending to a saved story still requires explicit Save');
  await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>/Saved in this library|已保存/.test(document.querySelector('#story-workspace-status')?.textContent||''));
  const update=requests.find(isStoryUpdate);assert.equal(update?.status,200);
  assert.equal(update.response.id,saveCall.response.id);
  assert.equal(update.response.revision,(BigInt(saveCall.response.revision)+1n).toString());
  assert.deepEqual(update.response.items.map(item=>item.id),updatedStoryIds);
  pass('Appending to an editable saved story preserves the same story ID and saves a new revision only on request');

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
  assert.equal(requests.slice(beforeDenied).some(item=>item.method==='POST'&&storyPreviewPath(item.path)),false);
  assert.equal(requests.slice(beforeDenied).some(item=>item.method==='POST'&&memoryStoryPath(item.path)),false);
  pass('A fresh permission denial blocks story preparation and saving');
  assert.deepEqual(blocked,[],'all external origins are blocked without a successful outside request');assert.deepEqual(errors,[]);
  const pageCalls=requests.filter(item=>/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/result-pages(?:\?|$)/.test(item.path));
  const receiptCalls=requests.filter(item=>item.method==='GET'&&freshReadPath(item.path));
  const summary={checks,elapsed_ms:Date.now()-startedAt,assistant_turn_posts:turnPosts().length,result_page_posts:pageCalls.filter(item=>item.method==='POST').length,
    fresh_current_result_gets:receiptCalls.length,story_outline_posts:requests.filter(item=>item.method==='POST'&&storyPreviewPath(item.path)).length,
    story_saves:requests.filter(item=>item.method==='POST'&&memoryStoryPath(item.path)).length,requests:requests.length,
    blockedOrigins:blocked,pageErrors:errors,syntheticBackend:true};
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify(summary,null,2));
  console.log('RESULT '+JSON.stringify({...summary,artifacts}));
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{try{if(holdFreshCheck)releaseFreshCheck();if(holdStoryPreview)releaseStoryPreview();if(browser)await browser.close();}finally{try{bridge.stdin.write('{"command":"quit"}\n');bridge.kill();}catch{}}});
