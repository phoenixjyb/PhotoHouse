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
  cwd:root,env:{...process.env,PH_SCENE_FIXTURE:'1',PH_SCENE_PAGES:'1',PH_JOIN_SELECTED_STORY:process.env.PH_JOIN_SELECTED_STORY||'0'},stdio:['pipe','pipe','pipe']});
const joinedStory=process.env.PH_JOIN_SELECTED_STORY==='1';
const bridgeClosed=new Promise(resolve=>bridge.once('close',resolve));
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
let holdResultAvailability=null;
let failNextFrameEdit=false;
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
    if(holdResultAvailability&&req.method()==='GET'&&url.pathname==='/assistant/workspace/v1/result-page-capabilities'){
      const gate=holdResultAvailability;holdResultAvailability=null;gate.arrive();await gate.wait;
    }
    const isFreshReceipt=req.method()==='GET'&&freshReadPath(url.pathname+url.search);
    if(isFreshReceipt&&failNextFreshCheck){
      const status=failNextFreshCheck;failNextFreshCheck=null;await route.fulfill({status,contentType:'application/json',body:'{"detail":"synthetic fresh authorization denied"}'});return;
    }
    if(isFreshReceipt&&holdFreshCheck){
      const gate=holdFreshCheck;holdFreshCheck=null;arriveFreshCheck();await gate;
    }
    const isStoryPreview=req.method()==='POST'&&url.pathname==='/story-workspace/preview';
    if(isStoryPreview&&failNextFrameEdit){
      failNextFrameEdit=false;entry.status=503;await route.fulfill({status:503,contentType:'application/json',body:'{"detail":"synthetic frame preview failure"}'});return;
    }
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
  const hideExisting=page.locator('#assistant-story-hide-existing');
  const keepSearching=page.locator('#assistant-add-keep-searching');
  if(joinedStory){
    const storyTheme=page.locator('#story-workspace-theme');
    const resultPagePath=/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/result-pages$/;
    const waitForCards=ids=>page.waitForFunction(expected=>{
      const cards=[...document.querySelectorAll('#assistant-results .assistant-result')];
      return cards.length===expected.length&&cards.every((card,index)=>card.dataset.assetId===expected[index]);
    },ids);
    const advanceResultPage=async(pageNumber)=>{
      const resultResponse=page.waitForResponse(response=>
        response.request().method()==='POST'&&resultPagePath.test(new URL(response.url()).pathname));
      await page.locator('#assistant-result-page-next').click();
      const response=await resultResponse;
      assert.equal(response.status(),200);
      const result=await response.json();
      assert.equal(result.version,1);
      assert.equal(result.page,pageNumber);
      const ids=result.items.map(item=>item.id);
      assert(ids.length>0&&ids.length<=20,'ordinary next page returns a bounded result page');
      await waitForCards(ids);
      return ids;
    };
    const prepareRows=()=>requests.filter(item=>item.method==='POST'&&item.path.startsWith('/story-workspace/drafts/prepare'));
    const saves=()=>requests.filter(item=>item.method==='POST'&&memoryStoryPath(item.path));
    const beforeJoinedStart={prepares:prepareRows().length,saves:saves().length,outlines:requests.filter(item=>item.method==='POST'&&storyPreviewPath(item.path)).length};
    await search('找示例儿童的照片');
    const initial=turnPosts().at(-1).response.result;
    assert.deepEqual(initial.filters.people,{ids:['301'],match:'any'});
    assert.deepEqual(initial.filters.media,['image']);
    await search('只看2026年的');
    const refined=turnPosts().at(-1).response.result;
    assert.deepEqual(refined.filters.people,{ids:['301'],match:'any'});
    assert.deepEqual(refined.filters.date,{from:'2026-01-01',to:'2026-12-31'});
    assert.equal(refined.total,45);
    const firstPage=await pickIds();
    assert.equal(firstPage.length,20);
    const firstPick=firstPage.includes('101')?'101':firstPage[0];
    await page.locator(`.assistant-story-pick[value="${firstPick}"]`).check();
    let laterPick;
    for(let pageNumber=2;pageNumber<=3&&!laterPick;pageNumber++){
      const ids=await advanceResultPage(pageNumber);
      assert.equal(await page.locator('.assistant-result-why').count(),0);
      laterPick=firstPick==='101'?ids[0]:ids.find(id=>id==='101');
    }
    assert(laterPick,'a later page provides the second pick, including the family-note photo');
    await page.locator(`.assistant-story-pick[value="${laterPick}"]`).check();
    await page.locator('#assistant-result-page-return').click();
    await waitForCards(firstPage);
    const joinedOrder=[firstPick,laterPick];
    assert.deepEqual(await selectedIds(),joinedOrder);
    const why=page.getByRole('button',{name:'第 20 项结果的匹配说明',exact:true});
    await why.waitFor();
    const beforeWhy=turnPosts().length,composer=page.locator('#assistant-text');
    await composer.fill('保留这条未发送的草稿。');
    await why.press('Enter');
    assert.equal(await composer.inputValue(),'保留这条未发送的草稿。');
    await composer.fill('');
    await page.setViewportSize({width:390,height:845});
    await page.evaluate(()=>document.documentElement.style.fontSize='150%');
    await why.scrollIntoViewIfNeeded();
    assert(await why.evaluate(el=>el.getBoundingClientRect().height>=44&&el.scrollWidth<=el.clientWidth));
    await page.screenshot({path:path.join(artifacts,'why-result-action-phone-zh-150.png')});
    await why.press('Enter');
    const question=await composer.inputValue();
    assert.equal(question,'为什么是第20项结果？');
    assert.equal(await composer.evaluate(el=>el===document.activeElement),true);
    assert.equal(turnPosts().length,beforeWhy);
    await page.evaluate(()=>document.documentElement.style.fontSize='');
    await page.setViewportSize({width:1280,height:960});
    await search(question);
    const explained=turnPosts().at(-1).response.result;
    assert.equal(explained.kind,'results');
    assert.equal(explained.effect,null);
    assert.deepEqual(explained.filters,refined.filters);
    assert.deepEqual(explained.context,refined.context);
    assert.deepEqual(explained.items,refined.items);
    assert.match(explained.reply,/第20项的匹配说明/);
    assert.match(explained.reply,/人物筛选有已审核匹配记录/);
    assert.match(explained.reply,/拍摄日期筛选有匹配记录/);
    await page.waitForFunction(reply=>document.querySelector('#assistant-reply')?.textContent===reply,explained.reply);
    assert.deepEqual(await selectedIds(),joinedOrder,'an unchanged match explanation keeps picks from both pages in order');
    pass('A grounded match explanation requires explicit Send and retains the existing results and ordered picks');
    const threadId=await page.locator('#assistant-private-select').inputValue();
    const resumeKey='photohouse.assistant.story-selection.v1';
    const stored=await page.evaluate(key=>JSON.parse(sessionStorage.getItem(key)),resumeKey);
    assert.equal(stored.thread_id,threadId);
    assert.equal(stored.request_id,turnPosts().at(-1).response.request_id);
    assert.equal(stored.revision,turnPosts().at(-1).response.revision);
    assert.deepEqual(stored.picks.map(pick=>pick.id),joinedOrder);
    const reloadStart=requests.length;
    const turnsBeforeReload=turnPosts().length;
    let arriveAvailability,releaseAvailability;
    const availabilityRequested=new Promise(resolve=>{arriveAvailability=resolve;});
    const availabilityHeld=new Promise(resolve=>{releaseAvailability=resolve;});
    holdResultAvailability={arrive:arriveAvailability,wait:availabilityHeld};
    await page.setViewportSize({width:390,height:845});
    await page.reload();await page.locator('#grid .asset').first().waitFor();
    assert.equal(await page.evaluate(key=>sessionStorage.getItem(key)!==null,resumeKey),true,'the signed-in same-library refresh keeps the tab record');
    if(!await page.locator('#assistant-workspace-dialog').isVisible()){
      await page.locator('[href="#assistant-panel"]').first().click();
    }
    await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
    const conversation=page.locator('#assistant-private-select');
    if(!await conversation.isVisible())await page.locator('#assistant-private-management-toggle').click();
    assert.deepEqual(await selectedIds(),[],'reload keeps the selection private until the conversation is opened');
    const latestRead=page.waitForResponse(response=>response.request().method()==='GET'&&freshReadPath(response.url()));
    try{
      await conversation.selectOption(threadId);
      const [read]=await Promise.all([latestRead,availabilityRequested]);
      assert.equal(read.status(),200);
      assert.deepEqual(await selectedIds(),[],'picks stay hidden while the paging capability read is outstanding');
    }finally{releaseAvailability();}
    await page.waitForFunction(order=>{
      const listed=[...document.querySelectorAll('#assistant-story-selected-list [data-asset-id]')];
      return listed.length===order.length&&listed.every((item,index)=>item.dataset.assetId===order[index]);
    },joinedOrder);
    const reopenedReads=requests.slice(reloadStart);
    assert.equal(reopenedReads.filter(item=>item.method==='GET'&&freshReadPath(item.path)).length,1);
    assert.equal(reopenedReads.filter(item=>item.method==='GET'&&item.path.startsWith('/assistant/workspace/v1/result-page-capabilities')).length,1);
    assert.equal(reopenedReads.filter(item=>item.method==='POST'&&resultPagePath.test(new URL(item.path,'https://photohouse.test').pathname)).length,1);
    assert.equal(turnPosts().length,turnsBeforeReload,'resuming picks keeps the existing search turn');
    pass('Reopening after a phone-size tab refresh restores both picks in order even when the paging capability response is delayed');
    assert.equal(prepareRows().length,beforeJoinedStart.prepares);assert.equal(saves().length,beforeJoinedStart.saves);
    assert.equal(requests.filter(item=>item.method==='POST'&&storyPreviewPath(item.path)).length,beforeJoinedStart.outlines,
      'search, refinement, paging and selecting do not generate a story before the editor action');
    const handoffStart=requests.length;
    await page.locator('#assistant-shape-story').click();
    await page.locator('#story-workspace').waitFor({state:'visible'});
    const freshCheck=requests.slice(handoffStart).find(item=>item.method==='GET'&&freshReadPath(item.path));
    assert(freshCheck,'the ordinary handoff rereads the exact current result');
    assert.deepEqual(await page.locator('#story-selection input:checked').evaluateAll(nodes=>nodes.map(node=>node.value)),joinedOrder);
    assert.equal(prepareRows().length,beforeJoinedStart.prepares);assert.equal(saves().length,beforeJoinedStart.saves);
    assert.equal(requests.filter(item=>item.method==='POST'&&storyPreviewPath(item.path)).length,beforeJoinedStart.outlines,
      'opening the editor performs neither outline generation nor proposal generation');
    const joinedTitle='家人的海边片段';await page.locator('#story-workspace-title').fill(joinedTitle);await storyTheme.selectOption('trip');
    const capabilitiesResponse=page.waitForResponse(response=>new URL(response.url()).pathname==='/story-workspace/drafts/capabilities');
    await page.locator('#story-build').click();
    const capabilities=await capabilitiesResponse.then(response=>response.json());
    assert.equal(capabilities.enabled,true,`synthetic provider capability enabled: ${JSON.stringify(capabilities)}`);
    assert.equal(capabilities.can_prepare,true,`joined member may prepare: ${JSON.stringify(capabilities)}`);
    await page.locator('.story-chapter-card textarea[maxlength="6000"]').first().waitFor();
    const chapters=page.locator('.story-chapter-card');
    await chapters.first().locator('.story-source-opt-in').click();
    await chapters.first().locator('.story-chapter-split').click();assert.equal(await chapters.count(),2);
    const expectedChapters=joinedOrder.map(id=>[id]),familyChapterIndex=joinedOrder.indexOf('101');
    assert.deepEqual(await chapters.evaluateAll(cards=>cards.map(card=>[...card.querySelectorAll('.story-chapter-strip img')].map(img=>img.alt))),expectedChapters);
    const familyNoteId='family-11111111-1111-4111-8111-111111111111';
    const familyChapter=chapters.nth(familyChapterIndex);
    const selectedSource=familyChapter.locator(`.story-source-choice input[value="${familyNoteId}"]`);
    await selectedSource.waitFor({state:'visible'});
    const familyChapterSources=familyChapter.locator('.story-source-choice input[type="checkbox"]');
    for(let index=0;index<await familyChapterSources.count();index++)await familyChapterSources.nth(index).uncheck();
    await selectedSource.check();
    assert.deepEqual(await familyChapter.locator('.story-source-choice input:checked').evaluateAll(nodes=>nodes.map(node=>node.value)),[familyNoteId]);
    assert.equal(await chapters.nth(1-familyChapterIndex).locator('.story-source-choice input:checked').count(),0);
    assert.equal(prepareRows().length,beforeJoinedStart.prepares);assert.equal(saves().length,beforeJoinedStart.saves,
      'chapter arrangement and explicit family-source selection do not generate or save');
    const prepareBefore=prepareRows().length;
    const proposalResponse=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname==='/story-workspace/drafts/prepare');
    await page.locator('.story-draft-prepare').click();await proposalResponse;
    assert.equal(prepareRows().length,prepareBefore+1);assert.equal(saves().length,beforeJoinedStart.saves);
    const proposalCall=prepareRows().at(-1);assert.equal(proposalCall.status,200);
    const generated=proposalCall.response;assert.equal(generated.state,'needs_review');
    assert.equal(generated.chapters[familyChapterIndex].narration,'合成整理文字，仅供家人核对。');
    assert.deepEqual(generated.chapters[familyChapterIndex].citations.map(citation=>citation.source_id),[familyNoteId]);
    const proposal=JSON.parse(proposalCall.body);
    assert.deepEqual(proposal.selection.asset_ids,joinedOrder);
    assert.deepEqual(proposal.selection.chapters.map(chapter=>chapter.asset_ids),expectedChapters);
    assert.deepEqual(proposal.selection.chapters.map(chapter=>chapter.evidence_ids),expectedChapters.map((_chapter,index)=>index===familyChapterIndex?[familyNoteId]:[]));
    await page.waitForFunction(({chapter,narration})=>
      document.querySelectorAll('.story-chapter-card textarea[maxlength="6000"]')[chapter]?.value===narration,
      {chapter:familyChapterIndex,narration:generated.chapters[familyChapterIndex].narration});
    const reviewedNarration='家人核对后的海边回忆。';
    await familyChapter.locator('textarea[maxlength="6000"]').fill(reviewedNarration);
    await page.locator('.story-draft-reviewed').check();
    assert.equal(await page.locator('#story-save-memory').isDisabled(),false);
    assert.equal(saves().length,beforeJoinedStart.saves,'a prepared and reviewed proposal is still unsaved');
    const saveStart=requests.length;await page.locator('#story-save-memory').click();
    await page.waitForFunction(()=>/Saved in this library|已保存/.test(document.querySelector('#story-workspace-status')?.textContent||''));
    const saved=saves().at(-1);assert(saved&&requests.indexOf(saved)>=saveStart);
    const savedBody=JSON.parse(saved.body),savedChapters=JSON.parse(savedBody.chapters);
    assert.equal(savedBody.title,joinedTitle);assert.equal(savedBody.theme,'trip');assert.equal(savedBody.asset_ids,joinedOrder.join(','));
    assert.deepEqual(savedChapters.map(chapter=>chapter.asset_ids),expectedChapters);
    assert.deepEqual(savedChapters.map(chapter=>chapter.evidence_ids),expectedChapters.map((_chapter,index)=>index===familyChapterIndex?[familyNoteId]:[]));
    const storyId=saved.response.id;assert(storyId);
    const saveCount=saves().length,prepareCount=prepareRows().length;
    await page.locator('#story-workspace-close').click();
    const shelfCard=page.locator('#saved-memory-list .saved-memory-card').filter({hasText:joinedTitle});
    const reopenStart=requests.length;
    await shelfCard.locator('button').first().click();await page.locator('#story-reader').waitFor({state:'visible'});
    const reopenedCall=requests.slice(reopenStart).find(item=>{
      const url=new URL(item.path,'https://photohouse.test');
      return item.method==='GET'&&url.pathname===`/memory-stories/${storyId}`&&url.searchParams.get('source_review')==='1';
    });
    assert(reopenedCall,'reopening uses the current authorized source-review projection');
    const reopened=reopenedCall.response;
    assert.equal(reopened.saved,true);assert.equal(reopened.id,storyId);assert.equal(reopened.title,joinedTitle);
    assert.deepEqual(reopened.items.map(item=>item.id),joinedOrder);
    assert.deepEqual(reopened.chapters.map(chapter=>chapter.asset_ids),expectedChapters);
    assert.deepEqual(reopened.chapters.map(chapter=>chapter.evidence_ids),expectedChapters.map((_chapter,index)=>index===familyChapterIndex?[familyNoteId]:[]));
    assert.equal(reopened.chapters[familyChapterIndex].narration,reviewedNarration);
    const reopenedFamilyNote=reopened.items.find(item=>item.id==='101')?.evidence.find(evidence=>evidence.id===familyNoteId);
    assert.equal(reopenedFamilyNote?.source,'family');assert.equal(reopenedFamilyNote?.text,'Synthetic original wording kept private');
    assert.equal(saves().length,saveCount);assert.equal(prepareRows().length,prepareCount);
    pass('Joined Jude Search/refinement, paged ordered selection, chapters, explicit family evidence, reviewed proposal, save and reopen uses one ordinary UI/API journey');
    assert.deepEqual(blocked,[]);assert.deepEqual(errors,[]);
    const pageCalls=requests.filter(item=>resultPagePath.test(item.path));
    const receiptCalls=requests.filter(item=>item.method==='GET'&&freshReadPath(item.path));
    const summary={checks,elapsed_ms:Date.now()-startedAt,assistant_turn_posts:turnPosts().length,result_page_posts:pageCalls.filter(item=>item.method==='POST').length,fresh_current_result_gets:receiptCalls.length,story_outline_posts:requests.filter(item=>item.method==='POST'&&storyPreviewPath(item.path)).length,story_saves:requests.filter(item=>item.method==='POST'&&memoryStoryPath(item.path)).length,requests:requests.length,blockedOrigins:blocked,pageErrors:errors,syntheticBackend:true};
    fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify(summary,null,2));console.log('RESULT '+JSON.stringify({...summary,artifacts}));return;
  }
  await search('找示例儿童的视频');
  assert.deepEqual(turnPosts().at(-1).response.result.items.map(item=>item.kind),['video']);
  assert.equal(await picks().count(),1,'a video result also has an asset-bound selection control');
  await search('找示例儿童');
  assert.equal(await page.locator('.assistant-result').evaluateAll(cards=>cards.length>0),true);
  assert.equal(await page.locator('#assistant-story-selection').isVisible(),true);
  assert.equal(await page.locator('#assistant-shape-album').isHidden(),true,'contributors cannot start an album');
  assert.equal(await hideExisting.isHidden(),true,'plain search-to-story has no existing frames to hide');
  assert.equal(await keepSearching.isHidden(),true,'the continuation action is chapter-scoped');
  assert.match(await count(),/0\s*\/\s*24/);
  assert.equal(await picks().count(),await resultCards.count());
  assert.deepEqual(await resultCards.evaluateAll(cards=>cards.map(card=>card.dataset.assetId)),await pickIds());
  await resultCards.first().getByRole('button',{name:'打开照片',exact:true}).click();
  await page.locator('#viewer').waitFor({state:'visible'});
  assert.equal(await page.locator('#viewer-story-pick').isVisible(),false,'ordinary viewer has no story-selection action');
  await page.locator('#close-viewer').click();await page.locator('#viewer').waitFor({state:'hidden'});
  await page.locator('#memory-assistant-link').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  pass('Result cards expose asset-bound selection controls and an empty, visible selection toolbar');

  // A normal search result uses image fixtures; the separate video-filtered
  // turn above proved video controls, and scene pages below exercise persistence.
  const firstId=(await pickIds())[0],keyboardPick=page.locator(`.assistant-story-pick[value="${firstId}"]`);
  await keyboardPick.focus();await page.keyboard.press('Space');assert.equal(await keyboardPick.isChecked(),true);
  assert.deepEqual(await selectedIds(),[firstId]);assert.equal(new Set(await selectedIds()).size,1);assert.match(await count(),/1\s*\/\s*24/);
  await page.keyboard.press('Space');assert.equal(await keyboardPick.isChecked(),false);assert.match(await count(),/0\s*\/\s*24/);
  await keyboardPick.check();
  const beforeHistoryReload=turnPosts().length;
  await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-reload-history').click();
  await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  assert.deepEqual(await selectedIds(),[firstId],'reloading the current conversation retains the selected authorized frame');
  assert.equal(turnPosts().length,beforeHistoryReload,'loading the result again does not submit a new turn');
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
  if(!await page.locator('#assistant-story-selected').evaluate(node=>node.open))await page.locator('#assistant-story-selected > summary').click();
  const lastAtCap=secondPage[3];
  await page.locator(`#assistant-story-selected-list [data-selection-id="${lastAtCap}"][data-selection-action="earlier"]`).click();
  assert.match(await count(),/24\s*\/\s*24/,'moving a frame preserves the full selection');
  assert.equal(await page.locator(`.assistant-story-pick[value="${secondPage[4]}"]`).isDisabled(),true);
  await page.locator(`#assistant-story-selected-list [data-selection-id="${lastAtCap}"][data-selection-action="later"]`).click();
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
  let expectedOrder=[pageOne[0],'102','101'];assert.deepEqual(await selectedIds(),expectedOrder);
  await page.locator('#assistant-result-page-return').click();await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId===expected,pageOne[0]);
  assert.equal(await page.locator(`.assistant-story-pick[value="${pageOne[0]}"]`).isChecked(),true);
  assert.deepEqual(await selectedIds(),expectedOrder,'ordinary page return preserves mixed media and deliberate order');
  if(!await page.locator('#assistant-story-selected').evaluate(node=>node.open))await page.locator('#assistant-story-selected > summary').click();
  const moveButton=(id,action)=>page.locator(`#assistant-story-selected-list [data-selection-id="${id}"][data-selection-action="${action}"]`);
  const beforeMove=requests.length;
  await moveButton('101','earlier').focus();await page.keyboard.press('Space');
  assert.deepEqual(await selectedIds(),[pageOne[0],'101','102']);
  assert.equal(await moveButton('101','earlier').evaluate(node=>node===document.activeElement),true,'keyboard focus follows the moved frame');
  await page.keyboard.press('Enter');expectedOrder=['101',pageOne[0],'102'];
  assert.deepEqual(await selectedIds(),expectedOrder,'an off-page photo can be moved to the start using the keyboard');
  assert.equal(await moveButton('101','earlier').isDisabled(),true);assert.equal(await moveButton('102','later').isDisabled(),true);
  assert.equal(await moveButton('101','later').evaluate(node=>node===document.activeElement),true,'focus moves to an enabled control at the boundary');
  assert.match(await moveButton('101','later').getAttribute('aria-label'),/101/);
  await page.keyboard.press('Space');expectedOrder=[pageOne[0],'101','102'];
  assert.deepEqual(await selectedIds(),expectedOrder,'moving later also preserves every selected frame');
  assert.equal(requests.length,beforeMove,'reordering creates no API requests');
  for(const [width,scale] of [[1280,100],[390,150],[320,200]]){
    await page.setViewportSize({width,height:900});await page.evaluate(value=>document.documentElement.style.fontSize=`${value}%`,scale);
    await page.locator('#assistant-story-selected').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(artifacts,`assistant-order-${width}-${scale}.png`),fullPage:false});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`ordering fits ${width}px at ${scale}% text`);
    const targets=await page.locator('#assistant-story-selected-list button').evaluateAll(buttons=>buttons.map(button=>{const box=button.getBoundingClientRect();return {action:button.dataset.selectionAction,width:box.width,height:box.height,left:box.left,right:box.right,viewport:innerWidth};}));
    assert.equal(targets.every(box=>box.width>=44&&box.height>=44&&box.left>=0&&box.right<=box.viewport),true,`ordering targets at ${width}px/${scale}%: ${JSON.stringify(targets)}`);
  }
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  pass('Keyboard reordering keeps off-page media, accessible focus and touch targets without another API request');
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
  assert.equal(await keepSearching.isHidden(),true,'whole-story additions still use the standard add action');
  assert.match(await page.locator('#assistant-workspace-close').innerText(),/返回故事|Return to story/i);
  assert.equal(turnPosts().length,preArrangeTurns,'opening Assistant does not submit a search turn');
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/0\s*\/\s*24\b/,'the nested counter shows the 24-frame Jude batch limit');
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
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/0\s*\/\s*24\b/,'the nested counter shows the 24-frame Jude batch limit');
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
  const beforeFilter=turnPosts().length;
  await hideExisting.check();
  assert.equal(await duplicatePick.isHidden(),true,'the filter removes duplicate cards from this result page');
  assert.equal(turnPosts().length,beforeFilter,'the filter uses the displayed result and does not trigger another search');
  const appendPhoto=nestedPageOne.find(id=>!initialStoryIds.includes(id));assert(appendPhoto,'page one has an additional synthetic photo');
  const appendPhotoItem=appendTurn.items.find(item=>item.id===appendPhoto);assert.equal(appendPhotoItem.kind,'image');
  for(const id of nestedPageOne.filter(id=>!initialStoryIds.includes(id)))await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  const firstPageId=nestedPageOne[0];await page.locator('#assistant-result-page-next').click();
  await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId!==expected,firstPageId);
  const nestedPageTwo=await pickIds();for(const id of nestedPageTwo.slice(0,6))await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/24\s*\/\s*24\b/,'the nested picker reaches the exact batch limit');
  assert.match(await page.locator('#assistant-story-selection-status').innerText(),/已选完|available new frames/i);
  const cappedCandidate=nestedPageTwo[6];assert(cappedCandidate);assert.equal(await page.locator(`.assistant-story-pick[value="${cappedCandidate}"]`).isDisabled(),true,'the next unchecked frame is disabled at the nested limit');
  await page.locator('#assistant-story-selection-clear').click();assert.match(await page.locator('#assistant-story-selection-count').innerText(),/0\s*\/\s*24\b/);
  await page.locator('#assistant-result-page-return').click();await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId===expected,nestedPageOne[0]);
  assert.equal(await hideExisting.isChecked(),true,'the filter survives paging while adding to this story');
  assert.equal(await duplicatePick.isHidden(),true,'the returned first page still hides existing frames');
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
  assert.equal(await hideExisting.isChecked(),false,'starting another add resets the optional filter');
  assert.equal(beforeReopenTurns,turnPosts().length,'reopening nested Assistant does not submit a search turn');
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/0\s*\/\s*24\b/,'reopening starts with no newly selected frames');
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
  await page.locator('.assistant-result[data-asset-id="102"]').getByRole('button',{name:'打开视频',exact:true}).click();
  await page.locator('#viewer').waitFor({state:'visible'});
  const viewerPick=page.locator('#viewer-story-pick');assert.equal(await viewerPick.isVisible(),true,'nested Assistant result viewer exposes the selection action');
  assert.match(await viewerPick.innerText(),/选入故事|Select for story/i);
  await viewerPick.click();assert.deepEqual(await selectedIds(),[appendPhoto,'102'],'viewed video is added to the pending selection without closing the viewer');
  assert.match(await viewerPick.innerText(),/从选择中移除|Remove .* from selection/i);
  await viewerPick.click();assert.deepEqual(await selectedIds(),[appendPhoto],'the viewer action removes its selected result without closing the viewer');
  assert.match(await viewerPick.innerText(),/选入故事|Select for story/i);await viewerPick.click();
  assert.deepEqual(await selectedIds(),[appendPhoto,'102']);
  await page.screenshot({path:path.join(artifacts,'nested-video-viewer-selection.png'),fullPage:false});
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  assert.equal(await viewerPick.evaluate(button=>{
    const choice=button.getBoundingClientRect(),viewer=document.querySelector('#viewer').getBoundingClientRect();
    return choice.height>=48&&choice.left>=viewer.left&&choice.right<=viewer.right&&choice.top>=viewer.top&&choice.bottom<innerHeight;
  }),true,'the story selection action fits the phone viewer at enlarged text');
  await page.screenshot({path:path.join(artifacts,'nested-video-viewer-phone-390-150.png'),fullPage:false});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  await page.locator(`#viewer-filmstrip button[data-viewer-index="${appendFinalPage.indexOf('101')}"]`).click();
  await page.waitForFunction(()=>document.querySelector('#viewer-title')?.textContent.includes('101'));
  await viewerPick.click();
  assert.deepEqual(await selectedIds(),[appendPhoto,'102','101'],'filmstrip navigation keeps the picker and selects the viewed photo');
  await page.keyboard.press('Escape');await page.locator('#viewer').waitFor({state:'hidden'});
  await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  assert.deepEqual(await selectedIds(),[appendPhoto,'102','101'],'viewer choices remain pending when Escape returns to Assistant');
  const appendedIds=[appendPhoto,'102','101'];assert.deepEqual(await selectedIds(),appendedIds,'new photo/video choices retain deliberate click order');
  assert.match(await page.locator('#assistant-story-selection-count').innerText(),/3\s*\/\s*24\b/);
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
  await search('找示例儿童的视频');
  assert.deepEqual(await pickIds(),['102'],'the video-only search returns a frame that is already in the story');
  await hideExisting.check();
  assert.equal(await resultCards.first().isHidden(),true);
  assert.match(await page.locator('#assistant-story-page-empty').textContent(),/这一页.*已在故事中|All frames.*already in your story/i);
  await hideExisting.uncheck();
  assert.equal(await resultCards.first().isVisible(),true);
  assert.equal(await picks().first().isDisabled(),true);
  assert.equal(await page.locator('#assistant-story-page-empty').textContent(),'');
  await search('找示例儿童');
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
  const remove=page.locator(`.story-chapter-remove-frame[data-asset-id="${lastPhoto}"]`),undoRemoval=page.locator('#story-undo-frames');
  const beforeRemoval=await storyValues();
  const beforeRemovalWrites=requests.filter(isStoryUpdate).length;
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  await remove.scrollIntoViewIfNeeded();
  assert.equal(await remove.evaluate(button=>button.getBoundingClientRect().height>=44),true);
  assert.equal(await page.locator('#story-workspace').evaluate(dialog=>dialog.scrollWidth<=dialog.clientWidth+1),true,'saved story editor fits the phone horizontally');
  await page.screenshot({path:path.join(artifacts,'chapter-remove-phone-390-150.png'),fullPage:false});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  failNextFrameEdit=true;await remove.click();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('.story-chapter-frame-status')).some(node=>/暂时无法移除|Could not remove/.test(node.textContent)));
  assert.deepEqual(await storyValues(),beforeRemoval,'failed removal keeps all fields and frames');
  await remove.click();
  await page.waitForFunction(()=>/已从草稿中移除|Frame removed/.test(document.querySelector('#story-workspace-status')?.textContent||''));
  assert.deepEqual(await storyValues(),{...beforeRemoval,ids:appendedStoryIds});
  assert.match(await undoRemoval.textContent(),/撤销刚移除|Undo last removal/);
  assert.equal(requests.filter(isStoryUpdate).length,beforeRemovalWrites,'draft removal waits for explicit Save');
  const beforeUndoRemoval=requests.filter(r=>storyPreviewPath(r.path)).length;
  await undoRemoval.click();
  assert.deepEqual(await storyValues(),beforeRemoval,'undo restores the exact verified order and writing');
  assert.equal(requests.filter(r=>storyPreviewPath(r.path)).length,beforeUndoRemoval);
  await remove.click();await undoRemoval.waitFor({state:'visible'});
  await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>/Saved in this library|已保存/.test(document.querySelector('#story-workspace-status')?.textContent||''));
  const savedRemoval=requests.filter(isStoryUpdate).at(-1);
  assert.equal(savedRemoval.status,200);
  assert.equal(savedRemoval.response.id,saveCall.response.id);
  assert.equal(savedRemoval.response.revision,(BigInt(update.response.revision)+1n).toString());
  assert.deepEqual(savedRemoval.response.items.map(item=>item.id),appendedStoryIds);
  pass('Removing a chapter frame preserves writing and order through a failed attempt, undo and explicit revision save');

  // A chapter-scoped add inserts before later chapters and retains their prose.
  await page.locator('#story-workspace-close').click();
  await page.locator('[href="#assistant-panel"]').first().click();
  await search('找示例儿童');
  const [chapterOpening,chapterFollowing,chapterAddition]=await pickIds();
  for(const id of [chapterOpening,chapterFollowing])await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  await page.locator('#assistant-shape-story').click();await page.locator('#story-workspace').waitFor({state:'visible'});
  const chapterStoryTitle='桥边散步的两个片段';
  await page.locator('#story-workspace-title').fill(chapterStoryTitle);await storyTheme.selectOption('trip');
  await page.locator('#story-build').click();await page.locator('.story-source-opt-in').first().click();
  await page.locator('.story-chapter-split').first().click();
  const chapters=page.locator('.story-chapter-card');
  const chapterLayout=()=>chapters.evaluateAll(cards=>cards.map(card=>[...card.querySelectorAll('.story-chapter-strip img')].map(img=>img.alt)));
  assert.equal(await chapters.locator('.story-chapter-remove-frame').count(),0,'each chapter keeps at least one frame');
  await chapters.nth(0).locator('label input').first().fill('走到桥边');
  await chapters.nth(1).locator('label input').first().fill('准备回家');
  await chapters.nth(0).locator('textarea[maxlength="6000"]').fill('第一章的家人原话');
  await chapters.nth(1).locator('textarea[maxlength="6000"]').fill('后面一章的家人原话');
  const chapterFind=chapters.nth(0).locator('.story-chapter-find-frames');
  await page.setViewportSize({width:390,height:845});await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  assert.equal(await chapterFind.evaluate(button=>button.scrollWidth<=button.clientWidth+1),true);
  await chapterFind.click();
  assert.match(await page.locator('#assistant-story-selection-title').innerText(),/第\s*1\s*章|chapter 1/i);
  assert.match(await count(),/0\s*\/\s*3\b/,'one frame in the chapter leaves three chapter slots');
  assert.match(await keepSearching.innerText(),/添加并继续查找|Add and keep searching/);
  assert.equal(await keepSearching.isDisabled(),true,'choose a new frame before adding');
  assert.equal(await keepSearching.evaluate(button=>button.scrollWidth<=button.clientWidth+1),true,'the continuation action wraps at enlarged phone text');
  await hideExisting.check();
  assert.equal(await hideExisting.evaluate(input=>input.closest('label').scrollWidth<=input.closest('label').clientWidth),true,'the filter fits at enlarged phone text');
  await page.locator('#assistant-story-selection').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'chapter-frame-picker-phone-390-150.png'),fullPage:false});
  await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.documentElement.style.fontSize='');
  await page.locator(`.assistant-result[data-asset-id="${chapterAddition}"]`)
    .getByRole('button',{name:'打开照片',exact:true}).click();
  await page.locator('#viewer').waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('#viewer-story-pick').disabled);
  assert.match(await page.locator('#view-position').textContent(),/1\s*\/\s*18\b/,'viewer navigation excludes the two hidden story frames');
  await page.locator('#viewer-story-pick').click();
  await page.keyboard.press('Escape');
  await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  assert.equal(await hideExisting.isChecked(),true,'the view returns to the same filtered picker');
  assert.deepEqual(await selectedIds(),[chapterAddition]);
  pass('An optional duplicate filter survives paging and preview, explains an all-duplicate page, and leaves search results and picks intact');
  const beforeChapterAdd=requests.length;
  const chapterAddedStatus=()=>page.waitForFunction(()=>/已将所选画面添加到本章|Frames added to this chapter/.test(document.querySelector('#assistant-story-selection-status')?.textContent||''));
  await page.locator('#assistant-story-selection').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'chapter-frame-picker-desktop.png'),fullPage:false});
  await keepSearching.focus();await page.keyboard.press('Enter');await chapterAddedStatus();
  assert.deepEqual(await chapterLayout(),[[chapterOpening,chapterAddition],[chapterFollowing]]);
  assert.equal(await page.locator('#assistant-workspace-dialog').isVisible(),true,'a successful batch keeps the chapter picker open');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'assistant-text','keyboard focus continues at the search input');
  assert.match(await count(),/0\s*\/\s*2\b/);
  assert.deepEqual(await selectedIds(),[]);
  assert.equal(await hideExisting.isChecked(),true);
  const additionCard=resultCards.locator(`input[value="${chapterAddition}"]`);
  assert.equal(await additionCard.isHidden(),true,'the newly added frame is hidden by the duplicate filter');
  await hideExisting.uncheck();assert.equal(await additionCard.isDisabled(),true,'showing a newly added frame does not let it be picked again');
  assert.equal(await page.locator('#assistant-workspace-dialog').evaluate(node=>node.open),true);
  assert.equal(requests.slice(beforeChapterAdd).some(item=>item.method==='POST'&&/\/turns$/.test(item.path)),false,'adding frames does not send another search');

  await search('找示例儿童的照片');
  const firstPhotoPage=await pickIds();
  const strip=page.locator('#assistant-results.assistant-results--strip');
  await page.setViewportSize({width:390,height:845});
  await strip.scrollIntoViewIfNeeded();
  assert.equal(await strip.evaluate(node=>node.scrollWidth>node.clientWidth),true,'dated results overflow within the strip');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'the strip does not widen the phone layout');
  assert.equal(await strip.locator('.assistant-thumbnail-number').first().textContent(),'1');
  await strip.focus();await page.keyboard.press('ArrowRight');
  await page.waitForFunction(()=>document.querySelector('#assistant-results').scrollLeft>0);
  await page.locator('#assistant-strip-back').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-results').scrollLeft===0);
  await strip.scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'jude-thumbnail-strip-phone.png'),fullPage:false});
  await page.setViewportSize({width:1280,height:900});
  await strip.scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'jude-thumbnail-strip-desktop.png'),fullPage:false});

  await page.locator('#assistant-result-page-next').click();
  await page.waitForFunction(expected=>{const card=document.querySelector('.assistant-result');return card&&card.dataset.assetId!==expected;},firstPhotoPage[0]);
  const laterPhoto=(await pickIds())[0],laterPick=page.locator(`.assistant-story-pick[value="${laterPhoto}"]`);
  await laterPick.check();
  failNextFrameEdit=true;await keepSearching.click();
  await page.waitForFunction(()=>/暂时无法添加|could not be added/i.test(document.querySelector('#assistant-story-selection-status')?.textContent||''));
  assert.deepEqual(await chapterLayout(),[[chapterOpening,chapterAddition],[chapterFollowing]],'a failed later batch keeps the first addition and both chapters');
  await laterPick.check();await keepSearching.click();await chapterAddedStatus();
  assert.match(await count(),/0\s*\/\s*1\b/);
  assert.equal((await pickIds())[0],laterPhoto,'the picker stays on the same result page');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'assistant-result-page-return','later pages focus the action that enables the next search');
  await page.keyboard.press('Enter');
  await page.waitForFunction(expected=>document.querySelector('.assistant-result')?.dataset.assetId===expected,firstPhotoPage[0]);
  await hideExisting.check();

  await search('找示例儿童的视频');
  assert.equal(await hideExisting.isChecked(),true,'the duplicate filter stays set across new searches in this picker');
  assert.deepEqual(await pickIds(),['102']);
  await picks().first().check();await keepSearching.click();await chapterAddedStatus();
  assert.match(await count(),/0\s*\/\s*0\b/);
  assert.match(await page.locator('[data-i18n="assistantStoryHelp"]').innerText(),/本章已满|This chapter is full/);
  assert.equal(await keepSearching.isDisabled(),true,'a full chapter cannot add more frames');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'assistant-workspace-close');
  await page.keyboard.press('Enter');await page.locator('#assistant-workspace-dialog').waitFor({state:'hidden'});
  const chapterOrder=[[chapterOpening,chapterAddition,laterPhoto,'102'],[chapterFollowing]];
  assert.deepEqual(await chapterLayout(),chapterOrder);
  assert.equal(await page.locator('#story-workspace-title').inputValue(),chapterStoryTitle);
  assert.equal(await storyTheme.inputValue(),'trip');
  assert.deepEqual(await chapters.evaluateAll(cards=>cards.map(card=>card.querySelector('label input').value)),['走到桥边','准备回家']);
  assert.deepEqual(await chapters.locator('textarea[maxlength="6000"]').evaluateAll(nodes=>nodes.map(node=>node.value)),['第一章的家人原话','后面一章的家人原话']);
  assert.equal(requests.slice(beforeChapterAdd).some(item=>item.method==='POST'&&memoryStoryPath(item.path)),false);
  pass('One chapter picker accepts ordered photos and a video across three searches, refreshes the duplicate filter and capacity, and preserves draft edits on retry');
  const chapterThumbnail=await chapters.nth(0).locator(`.story-chapter-strip img[alt="${chapterOpening}"]`).elementHandle();
  const selectionThumbnail=await page.locator(`.story-frame-choice:has(input[value="${chapterOpening}"]) img`).elementHandle();
  const loadedThumbnails=[chapterThumbnail,selectionThumbnail];
  await Promise.all(loadedThumbnails.map(handle=>handle.evaluate(async img=>{img.loading='eager';await img.decode();})));
  const thumbnailReads=()=>requests.filter(item=>item.method==='GET'&&item.path.startsWith(`/assets/${chapterOpening}/thumbnail?`)).length;
  const beforeMoveThumbnails=thumbnailReads();
  const openingMove=page.locator(`[data-order-id="${chapterAddition}"][data-order-step="-1"]`);
  const laterChapterMove=page.locator(`[data-order-id="${chapterFollowing}"][data-order-step="-1"]`);
  assert.equal(await laterChapterMove.isDisabled(),true,'the order controls preserve chapter boundaries');
  assert.equal(await page.locator(`[data-start-id="${chapterFollowing}"]`).isDisabled(),true,'opening choices stay in the first chapter');
  failNextFrameEdit=true;await openingMove.click();
  await page.waitForFunction(()=>/暂时无法调整顺序|Could not move/.test(document.querySelector('#story-workspace-status')?.textContent||''));
  assert.deepEqual(await chapterLayout(),chapterOrder,'a failed reorder does not change chapter membership or frame order');
  await openingMove.click();
  await page.waitForFunction(()=>/已更新本章|Updated the frame order/.test(document.querySelector('#story-workspace-status')?.textContent||''));
  const reorderedChapter=[[chapterAddition,chapterOpening,laterPhoto,'102'],[chapterFollowing]];
  assert.deepEqual(await chapterLayout(),reorderedChapter);
  assert.equal(JSON.parse(requests.filter(item=>item.method==='POST'&&storyPreviewPath(item.path)).at(-1).body).asset_ids,reorderedChapter.flat().join(','));
  assert.deepEqual(await chapters.locator('textarea[maxlength="6000"]').evaluateAll(nodes=>nodes.map(node=>node.value)),['第一章的家人原话','后面一章的家人原话']);
  assert.match(await page.locator('#story-undo-frames').textContent(),/撤销刚调整|Undo last move/);
  await page.locator('#story-undo-frames').click();
  assert.deepEqual(await chapterLayout(),chapterOrder,'undo restores the authored chapter order');
  for(const handle of loadedThumbnails){
    assert.equal(await handle.evaluate(img=>img.isConnected&&img.naturalWidth>0),true,'loaded frame thumbnail survives the edit and undo');
    await handle.dispose();
  }
  assert.equal(thumbnailReads(),beforeMoveThumbnails,'reorder and undo make no repeat thumbnail request for the loaded frame');
  pass('Reordering and undo keep loaded chapter and selection thumbnails without another download');
  await page.locator(`[data-start-id="${chapterAddition}"]`).click();
  await page.waitForFunction(()=>/已更新本章|Updated the frame order/.test(document.querySelector('#story-workspace-status')?.textContent||''));
  assert.deepEqual(await chapterLayout(),reorderedChapter);
  assert.equal(requests.slice(beforeChapterAdd).some(item=>item.method==='POST'&&memoryStoryPath(item.path)),false);
  pass('The order controls move frames within their chapter, keep both narrations and let the author undo or choose the opener');

  // Continue from a 23-frame draft, using the last available slot in chapter six.
  await page.locator('#story-workspace-close').click();
  await page.locator('[href="#assistant-panel"]').first().click();await search('找示例儿童');
  const almostFull=await pickIds();assert.equal(almostFull.length,20);
  for(const id of almostFull)await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  await page.locator('#assistant-result-page-next').click();
  await page.waitForFunction(expected=>{const card=document.querySelector('.assistant-result');return card&&card.dataset.assetId!==expected;},almostFull[0]);
  const finalSlots=await pickIds();
  for(const id of finalSlots.slice(0,3))await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  await Promise.all([
    page.waitForEvent('dialog').then(async dialog=>{assert.equal(dialog.type(),'confirm');await dialog.accept();}),
    page.locator('#assistant-shape-story').click(),
  ]);
  await page.locator('#story-workspace').waitFor({state:'visible'});
  await page.locator('#story-build').click();await chapters.nth(5).waitFor();
  assert.deepEqual((await chapterLayout()).map(ids=>ids.length),[4,4,4,4,4,3]);
  await chapters.nth(5).locator('.story-chapter-find-frames').click();
  assert.match(await count(),/0\s*\/\s*1\b/);
  await page.locator(`.assistant-story-pick[value="${finalSlots[3]}"]`).check();
  assert.equal(await page.locator(`.assistant-story-pick[value="${finalSlots[4]}"]`).isDisabled(),true,'the active selection cannot exceed the remaining slot in this chapter');
  const beforeCapAdd=requests.length;
  await keepSearching.click();await chapterAddedStatus();
  assert.equal(await page.locator(`.assistant-story-pick[value="${finalSlots[4]}"]`).isDisabled(),true,'filling this chapter leaves no slots in its picker');
  await page.locator('#assistant-workspace-close').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'hidden'});
  assert.deepEqual((await chapterLayout()).flat(),[...almostFull,...finalSlots.slice(0,4)]);
  assert.match(await page.locator('#story-selection-count').innerText(),/24\s*\/\s*48\b/);
  assert.equal(await page.locator('#story-find-more-frames').isEnabled(),true);
  assert.equal(requests.slice(beforeCapAdd).some(item=>item.method==='POST'&&memoryStoryPath(item.path)),false);
  pass('Filling the sixth chapter keeps earlier frames in order and leaves the editor open for more chapters');

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

  await page.locator('#assistant-workspace-close').click();
  const discardGeneratedDraft=dialog=>dialog.accept();
  page.once('dialog',discardGeneratedDraft);
  try{await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});}
  finally{page.off('dialog',discardGeneratedDraft);}
  await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');
  await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  // Leave the album list on page two in the disposable library before creating from Search.
  const seeded=await page.evaluate(async()=>{
    const session=await fetch('/auth/session');
    const {csrf_token}=await session.json();
    const library=document.querySelector('#library-select').value;
    const statuses=[];
    for(let number=1;number<=11;number++){
      const response=await fetch('/admin/albums?'+new URLSearchParams({library}),{
        method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf_token},
        body:JSON.stringify({title:`Synthetic older album ${number}`,title_zh:'',description:'',
          theme:'custom',asset_ids:'',cover_asset_id:'',mutation_id:crypto.randomUUID()}),
      });
      statuses.push(response.status);
    }
    return statuses;
  });
  assert.deepEqual(seeded,Array(11).fill(200));
  const albumsPanel=page.locator('#albums-panel');
  if(!await albumsPanel.evaluate(node=>node.open))await albumsPanel.locator('summary').first().click();
  await page.locator('#album-next').click();
  await page.locator('#album-list').getByRole('heading',{name:'Synthetic older album 1',exact:true}).waitFor();
  await page.locator('#memory-assistant-link').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  await page.locator('#assistant-private-new').click();await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  await search('找示例儿童');
  const draftAlbum=page.locator('#assistant-shape-album');
  assert.equal(await draftAlbum.isDisabled(),true,'the owner must explicitly choose at least one result');
  const albumIds=(await pickIds()).slice(0,2).reverse();assert.equal(albumIds.length,2);
  for(const id of albumIds)await page.locator(`.assistant-story-pick[value="${id}"]`).check();
  const albumWrites=()=>requests.filter(item=>item.method==='POST'&&item.path.startsWith('/admin/albums?'));
  const beforeAlbums=albumWrites().length;
  const albumReceiptArrived=new Promise(resolve=>{arriveFreshCheck=resolve;});
  const albumReceiptSettled=new Promise(resolve=>{settleHeldFreshCheck=resolve;});
  holdFreshCheck=new Promise(resolve=>{releaseFreshCheck=resolve;});
  await draftAlbum.click();await albumReceiptArrived;
  try{await page.locator('#assistant-workspace-close').click();}
  finally{releaseFreshCheck();}
  await albumReceiptSettled;
  await page.locator('#memory-assistant-link').click();await page.locator('#assistant-workspace-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#album-editor').isHidden(),true);
  assert.equal(albumWrites().length,beforeAlbums);
  assert.deepEqual(await selectedIds(),albumIds,'closing a late album handoff keeps the current search selection');

  await page.setViewportSize({width:390,height:844});
  await draftAlbum.click();await page.locator('#album-editor').waitFor({state:'visible'});
  await page.evaluate(()=>{document.documentElement.style.zoom='150%';});
  assert.equal(await page.locator('#assistant-workspace-dialog').isHidden(),true);
  assert.equal(await page.locator('#album-title').inputValue(),'');
  assert.deepEqual(await page.locator('#album-selected .album-selection').evaluateAll(rows=>rows.map(row=>row.dataset.assetId)),albumIds);
  assert.equal(albumWrites().length,beforeAlbums,'preparing the album writes nothing');
  assert.equal(await page.locator('#album-choices button').count(),0,'the draft loads extra choices only on request');
  assert(await page.locator('#album-editor').evaluate(el=>el.scrollWidth<=el.clientWidth),'album draft fits at 390px and 150%');
  await page.locator('#album-editor').screenshot({path:path.join(artifacts,'search-album-draft-mobile-150-zh.png')});
  await page.locator('.album-picker > summary').click();await page.locator('#album-choices button').first().waitFor();
  const extra=page.locator('#album-choices button[aria-disabled="false"]').first();
  const extraId=await extra.getAttribute('data-asset-id');
  const extraChoice=page.locator(`#album-choices button[data-asset-id="${extraId}"]`);
  const albumRow=id=>page.locator(`#album-selected .album-selection[data-asset-id="${id}"]`);
  const albumOrder=()=>page.locator('#album-selected .album-selection').evaluateAll(rows=>rows.map(row=>row.dataset.assetId));
  await extraChoice.press('Enter');
  assert.deepEqual(await albumOrder(),[...albumIds,extraId]);
  assert.equal(await extraChoice.getAttribute('aria-disabled'),'true');
  assert.match(await extraChoice.locator('.album-choice-position').textContent(),/第 3 项/);
  await extraChoice.press('Enter');
  assert.deepEqual(await albumOrder(),[...albumIds,extraId],'a selected picker item cannot be added twice');
  const earlier=albumRow(extraId).locator('[data-action="moveUp"]');
  await earlier.press('Enter');
  assert.deepEqual(await albumOrder(),[albumIds[0],extraId,albumIds[1]]);
  assert.equal(await earlier.evaluate(node=>document.activeElement===node),true);
  await earlier.press('Enter');
  assert.equal(await albumRow(extraId).evaluate(node=>document.activeElement===node),true);
  assert.match(await extraChoice.locator('.album-choice-position').textContent(),/第 1 项/);
  await page.setViewportSize({width:1280,height:900});
  await page.evaluate(()=>{document.documentElement.style.zoom='';});
  await page.locator('#album-editor').screenshot({path:path.join(artifacts,'search-album-picker-desktop-zh.png')});
  await albumRow(extraId).locator('[data-action="remove"]').press('Enter');
  assert.equal(await albumRow(albumIds[0]).evaluate(node=>document.activeElement===node),true);
  assert.equal(await extraChoice.getAttribute('aria-disabled'),'false');
  assert.equal(await extraChoice.locator('.album-choice-position').isHidden(),true);
  assert.deepEqual(await albumOrder(),albumIds);
  assert.equal(albumWrites().length,beforeAlbums,'ordering and marking choices never save by themselves');
  await page.locator('.album-picker > summary').click();
  await page.locator('#album-title').fill('合成：从搜索创建的相册');
  await page.locator('#album-save').click();await page.locator('#album-editor').waitFor({state:'hidden'});
  const savedHeading=page.locator('#album-list').getByRole('heading',{name:'合成：从搜索创建的相册',exact:true});
  await savedHeading.waitFor();
  assert.equal(await page.locator('#album-previous').isDisabled(),true);
  assert.equal(await savedHeading.evaluate(node=>document.activeElement===node),true);
  assert.equal(albumWrites().length,beforeAlbums+1);
  const savedAlbum=albumWrites().at(-1);
  assert.equal(savedAlbum.status,200);
  assert.deepEqual(JSON.parse(savedAlbum.body).asset_ids.split(','),albumIds);
  assert.deepEqual(savedAlbum.response.asset_ids,albumIds);
  assert.equal(savedAlbum.response.cover_asset_id,albumIds[0]);
  await page.evaluate(()=>{document.documentElement.style.zoom='';});
  pass('Owners can save the current Search selection as an ordered family album after review; closing a pending handoff creates nothing');
  assert.deepEqual(blocked,[],'all external origins are blocked without a successful outside request');assert.deepEqual(errors,[]);
  const pageCalls=requests.filter(item=>/\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/requests\/[0-9a-f-]+\/result-pages(?:\?|$)/.test(item.path));
  const receiptCalls=requests.filter(item=>item.method==='GET'&&freshReadPath(item.path));
  const summary={checks,elapsed_ms:Date.now()-startedAt,assistant_turn_posts:turnPosts().length,result_page_posts:pageCalls.filter(item=>item.method==='POST').length,
    fresh_current_result_gets:receiptCalls.length,story_outline_posts:requests.filter(item=>item.method==='POST'&&storyPreviewPath(item.path)).length,
    story_saves:requests.filter(item=>item.method==='POST'&&memoryStoryPath(item.path)).length,requests:requests.length,
    blockedOrigins:blocked,pageErrors:errors,syntheticBackend:true};
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify(summary,null,2));
  console.log('RESULT '+JSON.stringify({...summary,artifacts}));
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{
  try{
    if(holdFreshCheck)releaseFreshCheck();
    if(holdStoryPreview)releaseStoryPreview();
    if(browser)await browser.close();
  }finally{
    if(!joinedStory){
      try{bridge.stdin.write('{"command":"quit"}\n');bridge.kill();}catch{}
    }else{
      if(bridge.exitCode===null&&!bridge.stdin.destroyed)bridge.stdin.end('{"command":"quit"}\n');
      let timer;
      const timeout=new Promise(resolve=>{timer=setTimeout(()=>resolve(null),5000);});
      const exitCode=await Promise.race([bridgeClosed,timeout]);
      clearTimeout(timer);
      if(exitCode!==0){
        bridge.kill();
        console.error('The generated story fixture did not close cleanly');
        process.exitCode=1;
      }
    }
  }
});
