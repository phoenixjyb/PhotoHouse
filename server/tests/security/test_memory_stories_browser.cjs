'use strict';
/* Actual browser -> closed ASGI -> migrated synthetic SQLite; no HTTP listener. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-saved-stories-web-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pending=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const request=pending.get(result.id);if(request){pending.delete(result.id);request.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error('Bridge failed'));for(const item of pending.values())item.reject(new Error('Bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
let browser,ctx,hold=null,releaseHold,arrivedHold;const errors=[],external=[],checks=[];let dropSave=false;const saveBodies=[],storyWriteBodies=[];let savedStoryPayload=null,proposalFixture=null;
const syntheticContribution={id:'a0000000-0000-4000-8000-000000000001',kind:'text',state:'accepted',author_id:'synthetic-family-member',byline:'测试家人',text:'合成贡献：湖边散步时，大家一起唱了歌。',chapter_id:null,processing_consent:true,created_at:1,updated_at:1};
const pass=name=>{checks.push(name);console.log('PASS '+name);};
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  ctx=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block',acceptDownloads:true});
  await ctx.addInitScript(()=>{let Constructor;Object.defineProperty(window,'PhotoHouseStoryWorkspace',{configurable:true,get:()=>Constructor,set:value=>{Constructor=config=>{let language=null;const originalScope=config.scope;const instance=value({...config,scope:()=>({...originalScope(),...(language?{language}:{})})});window.__storyWorkspaceTest=instance;window.__setStoryWorkspaceTestLanguage=next=>{language=next;instance.translate();};return instance;};}});});
  await ctx.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    if(req.method()==='GET'&&url.pathname==='/memory-community/v1/capabilities'){
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,enabled:true,contributions_enabled:true,generation_enabled:false})});return;
    }
    // Preserve a deterministic legacy-client path for the additive refs API.
    // The focused contribution-ref browser journey exercises the real a0 route.
    if(req.method()==='GET'&&/^\/memory-stories\/[0-9a-f-]{36}\/contribution-refs$/.test(url.pathname)){
      await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Contribution references unavailable'})});return;
    }
    if(req.method()==='GET'&&savedStoryPayload?.id&&url.pathname===`/memory-community/v1/stories/${savedStoryPayload.id}/contributions`){
      await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({version:1,story_id:savedStoryPayload.id,page:1,page_size:16,items:[syntheticContribution],can_review:false,can_delete:false,has_more:false})});return;
    }
    const headers=await req.allHeaders();delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']=new URL(req.frame().url()).origin===url.origin?'same-origin':'none';
    if(url.pathname==='/memory-stories'&&req.method()==='POST')saveBodies.push(req.postData());
    if(/^\/memory-stories\/[0-9a-f-]{36}$/.test(url.pathname)&&['POST','PUT'].includes(req.method()))storyWriteBodies.push({method:req.method(),body:req.postData()});
    const result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    if(req.method()==='GET'&&/^\/memory-stories\/[0-9a-f-]{36}$/.test(url.pathname)&&result.status===200)savedStoryPayload=JSON.parse(Buffer.from(result.body,'base64').toString());
    if(proposalFixture&&req.method()==='GET'&&url.pathname==='/memory-community/v1/jobs/'+proposalFixture.job.id){await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(proposalFixture.job)});return;}
    if(dropSave&&url.pathname==='/memory-stories'&&req.method()==='POST'){dropSave=false;await route.abort('failed');return;}
    if(hold&&url.pathname==='/story-workspace/preview'){const gate=hold;hold=null;arrivedHold();await gate;}
    const output={...result.headers};delete output['content-length'];delete output['content-encoding'];
    try{await route.fulfill({status:result.status,headers:output,body:Buffer.from(result.body,'base64')});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  let dismissDialogs=false;const dialogMessages=[];
  const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{dialogMessages.push(d.message());return dismissDialogs?d.dismiss():d.accept();});
  async function login(phone='+12025550100'){await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill(phone);await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();}
  await rpc({command:'mutate',scenario:'many-assets'});
  await login();await page.waitForFunction(()=>document.querySelector('#saved-memory-status').textContent.includes('还没有'));
  await page.locator('#memory-create').click();
  await page.locator('#story-selection-clear').click();const choices=page.locator('#story-selection input');for(let i=0;i<6;i++)await choices.nth(i).check();
  await page.locator('#story-workspace-title').fill('一起走过的日子');await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();
  assert.equal(await page.locator('.story-chapter-card').count(),2);
  await page.locator('.story-chapter-card input').first().fill('出发，和家人在一起');
  await page.locator('.story-chapter-card textarea').first().fill('这是家人写下的一段回忆。\n我们想记住一起走过的日子。');
  dropSave=true;await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>document.querySelector('#story-workspace-status').textContent.includes('保存结果尚未确认'));
  assert.equal(await page.locator('.story-chapter-card textarea').first().isDisabled(),true);
  await rpc({command:'mutate',scenario:'memory-concurrent-reorder'});
  await page.locator('#story-save-memory').click();await page.waitForFunction(()=>document.querySelector('#story-workspace-status').textContent.includes('已保存到'));
  assert.equal(saveBodies.length,2);assert.equal(saveBodies[0],saveBodies[1]);
  assert.match(await page.locator('#story-workspace-status').textContent(),/最新版本/);
  assert.equal(await page.locator('#story-selection input').first().inputValue(),
    JSON.parse(saveBodies[0]).asset_ids.split(',')[1]);
  await page.waitForFunction(()=>document.querySelectorAll('.saved-memory-card').length===1);assert.equal(await page.locator('.saved-memory-card').count(),1);
  pass('Lost save response retries the identical mutation and opens the current reordered saved story');
  await page.locator('#story-workspace-close').click();await page.reload();await page.locator('.saved-memory-card').waitFor();
  assert.equal(await page.locator('.saved-memory-card .saved-memory-copy button').textContent(),'阅读故事');
  assert.match(await page.locator('.saved-memory-cover').getAttribute('aria-label'),/^阅读故事:/);
  await page.screenshot({path:path.join(artifacts,'saved-story-home-desktop-zh.png'),fullPage:true});
  await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-workspace').isVisible(),false,'saved stories open without an editor behind the reader');
  assert.equal(await page.locator('#story-reader-edit').isVisible(),true,'the author sees an explicit edit action');
  assert.match(await page.locator('#story-reader-close').textContent(),/返回故事列表/);
  assert.equal(await page.locator('#story-reader-title').textContent(),'出发，和家人在一起');
  assert.match(await page.locator('#story-reader-text').textContent(),/家人写下/);
  assert.match(await page.locator('#story-reader-eyebrow').textContent(),/已保存故事/);
  pass('Saved private chapters survive refresh and reopen in the cinematic reader');
  await page.locator('#story-reader-play').click();assert.equal(await page.locator('#story-reader-play').getAttribute('aria-pressed'),'true');
  await page.waitForFunction(()=>document.querySelectorAll('#story-reader-frames button')[1].getAttribute('aria-pressed')==='true',{},{timeout:10000});
  await page.locator('#story-reader-next').click();assert.equal(await page.locator('#story-reader-play').getAttribute('aria-pressed'),'false');
  assert.match(await page.locator('#story-reader-eyebrow').textContent(),/2 \/ 2/);
  await page.locator('#story-reader-previous').click();
  await page.locator('#story-reader').screenshot({path:path.join(artifacts,'saved-story-reader-desktop-zh.png')});
  pass('User-started paced playback advances frames; manual chapter navigation pauses playback');
  await page.locator('#story-reader-chapters button').nth(1).click();await page.locator('#story-reader-frames button').nth(1).click();
  const resumedChapter=await page.locator('#story-reader-chapters button[aria-current=step]').textContent();
  const resumedFrame=await page.locator('#story-reader-frames button[aria-pressed=true]').getAttribute('aria-label');
  await page.locator('#story-reader-close').click();await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-reader-chapters button[aria-current=step]').textContent(),resumedChapter,'same revision resumes its chapter');
  assert.equal(await page.locator('#story-reader-frames button[aria-pressed=true]').getAttribute('aria-label'),resumedFrame,'same revision resumes its frame');
  await page.locator('#story-reader-edit').click();assert.equal(await page.locator('#story-reader').isVisible(),false);assert.equal(await page.locator('#story-workspace').isVisible(),true);
  assert.match(await page.locator('.story-chapter-card textarea').first().inputValue(),/家人写下/,'explicit edit hydrates the exact saved chapter');
  await page.locator('.story-chapter-card textarea').first().fill('保存一个新版本后，从故事开头重新阅读。');await page.locator('#story-preview').click();
  assert.equal(await page.locator('#story-workspace').isVisible(),true,'preview from the saved editor keeps its editor open');
  assert.equal(await page.locator('#story-reader-edit').isVisible(),false,'editor preview does not offer a redundant Edit action');
  assert.match(await page.locator('#story-reader-close').textContent(),/^返回$/,'editor preview returns to its editor');
  await page.locator('#story-reader-close').click();assert.equal(await page.locator('#story-workspace').isVisible(),true);
  assert.equal(await page.locator('.story-chapter-card textarea').first().inputValue(),'保存一个新版本后，从故事开头重新阅读。');
  await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>document.querySelector('#story-workspace-status').textContent.includes('已保存到'));
  await page.locator('#story-workspace-close').click();await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-reader-chapters button[aria-current=step]').evaluate(node=>Array.from(node.parentElement.children).indexOf(node)),0,'a new revision starts at its beginning');
  assert.equal(await page.locator('#story-reader-frames button[aria-pressed=true]').getAttribute('aria-label'),await page.locator('#story-reader-frames button').first().getAttribute('aria-label'));
  pass('Saved story positions resume within a revision and reset after an explicit edit is saved');
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.zoom='150%';});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'390px reader remains reachable at 150% zoom');
  assert(await page.locator('#story-reader').evaluate(el=>el.scrollWidth<=el.clientWidth),'reader controls do not force horizontal scrolling');
  await page.locator('#story-reader').screenshot({path:path.join(artifacts,'saved-story-reader-mobile-150-zh.png')});await page.evaluate(()=>{document.documentElement.style.zoom='';});await page.locator('#story-reader-close').click();
  await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});await page.locator('#story-reader-edit').click();await page.locator('.story-chapter-card textarea').first().fill('新补充的文字不会被别人覆盖。');
  await rpc({command:'mutate',scenario:'memory-concurrent-edit'});
  await page.locator('#story-save-memory').click();await page.waitForFunction(()=>document.querySelector('#story-workspace-status').textContent.includes('已有变化'));
  assert.equal(await page.locator('.story-chapter-card textarea').first().inputValue(),'新补充的文字不会被别人覆盖。');
  assert.equal(await page.locator('.story-chapter-card textarea').first().isDisabled(),false);
  pass('Concurrent edits leave the local draft editable and offer explicit saved-version reload');
  await page.locator('#story-workspace-close').click();await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  await page.locator('#story-reader-chapters button').nth(1).click();await page.locator('#story-reader-frames button').nth(1).click();
  await page.locator('#story-reader-close').click();await page.locator('#logout').click();await page.locator('#auth').waitFor();
  assert.equal(await page.locator('.saved-memory-card').count(),0);assert.equal(await page.locator('#story-reader-text').textContent(),'');
  await login('+12025550102');await page.locator('.saved-memory-card').waitFor();await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-workspace').isVisible(),false);assert.equal(await page.locator('#story-reader-edit').isVisible(),false,'viewer has no edit action');
  await page.locator('#story-reader-close').click();await page.screenshot({path:path.join(artifacts,'saved-story-home-mobile-zh.png'),fullPage:true});
  pass('Approved viewer can reopen but cannot edit; logout removes private shelf and reader text');
  await page.locator('#logout').click();await page.locator('#auth').waitFor();await login();await page.locator('.saved-memory-card').waitFor();await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-reader-chapters button[aria-current=step]').evaluate(node=>Array.from(node.parentElement.children).indexOf(node)),0,'logout clears saved-story resume positions');
  assert.equal(await page.locator('#story-reader-frames button[aria-pressed=true]').getAttribute('aria-label'),await page.locator('#story-reader-frames button').first().getAttribute('aria-label'));
  await page.locator('#story-reader-close').click();
  await page.setViewportSize({width:1280,height:960});await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  await page.locator('#story-reader-related').click();assert.equal(await page.locator('#assistant-text').inputValue(),'找照片 一起走过的日子');
  assert.equal(await page.locator('#story-reader').isVisible(),false);assert.equal(await page.locator('#story-workspace').isVisible(),false);
  pass('Reader hands the story title to an editable assistant search without submitting it');
  await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  const voiceTab=page.locator('#story-reader-community').getByRole('tab',{name:'家人的声音'});await voiceTab.click();
  const contribution=page.locator('#story-reader-community .memory-contribution').filter({hasText:'测试家人'});await contribution.waitFor();
  assert.match(await contribution.textContent(),/合成贡献：湖边散步时，大家一起唱了歌。/,'the controlled contribution-list fixture presents the original separately from story chapters');
  await page.locator('#story-reader-close').click();await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  assert.match(await page.locator('#story-reader-community').textContent(),/合成贡献：湖边散步时，大家一起唱了歌。/,'the accepted original remains in its separate contribution list');
  assert(savedStoryPayload?.chapters?.length>=1,'the saved story response is available to bind the verified proposal');
  const proposalChapterData=savedStoryPayload.chapters.map((chapter,index)=>({id:chapter.id,narration:index===0?'这是一段仅引用家人原始贡献的合成整理建议。':'基于本章既有画面参考的核对建议。',source_ids:index===0?[`contribution-${syntheticContribution.id}`]:chapter.evidence_ids}));
  const proposalJobId='f0000000-0000-4000-8000-000000000001';
  proposalFixture={job:{id:proposalJobId,state:'ready',kind:'narrative',base_revision:savedStoryPayload.revision,result:{version:1,title:savedStoryPayload.title,needs_review:true,chapters:proposalChapterData}}};
  const proposal={story_id:savedStoryPayload.id,revision:savedStoryPayload.revision,job_id:proposalJobId,
    chapters:proposalChapterData.map(section=>({id:section.id,narration:section.narration})),
    source_refs:proposalChapterData.map(section=>({chapter_id:section.id,source_ids:section.source_ids}))};
  const originalReaderText=await page.locator('#story-reader-text').textContent(),writesBeforeProposal=storyWriteBodies.length;
  dismissDialogs=true;await page.evaluate(value=>window.__storyWorkspaceTest.acceptProposal(value),proposal);
  assert(dialogMessages.some(message=>/当前故事格式无法保留这些引用/.test(message)),'the Chinese confirmation names the references that cannot be saved');
  assert.equal(await page.locator('#story-reader').isVisible(),true,'canceling source loss leaves the reader open');
  assert.equal(await page.locator('#story-reader-text').textContent(),originalReaderText,'canceling source loss leaves current prose unchanged');
  assert.equal(await page.locator('#story-workspace').isVisible(),false,'canceling does not open or replace the editor draft');
  assert.equal(storyWriteBodies.length,writesBeforeProposal,'canceling performs no story write');
  dismissDialogs=false;await page.evaluate(value=>window.__storyWorkspaceTest.acceptProposal(value),proposal);
  await page.locator('#story-workspace').waitFor({state:'visible'});
  const sourceWarning=page.locator('.story-chapter-card[data-chapter-id="'+proposalChapterData[0].id+'"] .story-proposal-reference-note');await sourceWarning.waitFor();
  assert.match(await sourceWarning.textContent(),/家人提供的原始回忆仍在单独的「家人的声音」列表中/);
  await page.evaluate(()=>window.__setStoryWorkspaceTestLanguage('en'));
  assert.match(await sourceWarning.textContent(),/The original family memory remains in the separate family voices list/,'the chapter review note localizes to English');
  await page.evaluate(()=>window.__setStoryWorkspaceTestLanguage('zh'));
  assert.match(await sourceWarning.textContent(),/家人提供的原始回忆仍在单独的「家人的声音」列表中/);
  assert.equal(await page.locator('.story-chapter-card[data-chapter-id="'+proposalChapterData[0].id+'"] textarea').inputValue(),proposalChapterData[0].narration);
  assert.equal(await page.locator('#story-workspace-status').textContent(),'章节提纲已准备好，可以编辑、预览或下载。');
  await sourceWarning.scrollIntoViewIfNeeded();await sourceWarning.screenshot({path:path.join(artifacts,'story-proposal-source-warning-zh.png')});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.documentElement.style.zoom='150%';});
  assert(await page.locator('#story-workspace').evaluate(node=>node.scrollWidth<=node.clientWidth),'source note fits the story editor at 390px and 150% text size');
  await sourceWarning.scrollIntoViewIfNeeded();await sourceWarning.screenshot({path:path.join(artifacts,'story-proposal-source-warning-mobile-150-zh.png')});
  await page.evaluate(()=>{document.documentElement.style.zoom='';});await page.setViewportSize({width:1280,height:960});
  await page.locator('#story-save-memory').click();await page.waitForFunction(()=>document.querySelector('#story-workspace-status').textContent.includes('已保存到'));
  const acceptedSave=storyWriteBodies.at(-1),acceptedChapters=JSON.parse(JSON.parse(acceptedSave.body).chapters);
  assert.equal(acceptedSave.method,'PUT','only explicit Save writes the accepted proposal');
  assert.equal(acceptedChapters[0].evidence_ids.length,0,'the existing story contract saves the contribution-only chapter without unsupported refs');
  assert.equal(acceptedChapters[0].narration,proposalChapterData[0].narration);
  assert.equal(await page.locator('.story-proposal-reference-note').count(),0,'successful save clears draft-only warning metadata');
  await page.locator('#story-workspace-close').click();await page.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  await page.locator('#story-reader-community').getByRole('tab',{name:'家人的声音'}).click();
  assert.match(await page.locator('#story-reader-community').textContent(),/合成贡献：湖边散步时，大家一起唱了歌。/,'explicitly saved editorial text did not replace or delete the original contribution');
  pass('Contribution-only source loss is confirmed before adoption, reviewed in the editor, and only explicit save uses the current story contract');
  await page.locator('#story-reader-contribute').click();await page.locator('#viewer').waitFor({state:'visible'});
  pass('Contribute action opens the current protected asset for its family memory');
  assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(artifacts,'checks.json'),JSON.stringify({checks,errors,external,fixture:'synthetic ASGI; lost reply, concurrent edit, and ready narrative job intercepted for contribution-source adoption review'},null,2));console.log('ARTIFACTS '+artifacts);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(ctx)await ctx.close();if(browser)await browser.close();bridge.stdin.end();});
