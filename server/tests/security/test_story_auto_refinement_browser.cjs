'use strict';
/* Saved-story refinement stays review-only through the real workspace UI. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'memory_community_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe'],env:{...process.env,PH_BROWSER_MULTICHAPTER_STORY:'1'}});
let serial=0,storyId,story,readyResolve,readyReject;const pending=new Map(),requests=[],pageErrors=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){storyId=value.story_id;readyResolve();return;}const call=pending.get(value.id);if(call){pending.delete(value.id);call.resolve(value);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Synthetic bridge failed (${code})`));for(const call of pending.values())call.reject(new Error('Synthetic bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const jobId='5f79b251-a8fd-43b6-bfc2-d130b6055fb6',modelTitle='MODEL_TITLE_MUST_NOT_APPEAR',originalTitle='一起走过的日子';let saveBodies=[];
let browser,context,page,jobPolls=0,refinementPosts=0,external=[],staleMetadata=false,noAutoJob=true,realShelfDraft=false,confirmAction='accept',dialogWaiter=null;
let previousJobError=null, refuseNextRetry=false;
const generationPosts=()=>requests.filter(item=>item.method==='POST'&&item.path.startsWith('/memory-community/v1/jobs')).length;
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    const headers=await request.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const entry={method:request.method(),path:url.pathname+url.search};requests.push(entry);
    let responseBody,status,headersOut;
    if(entry.method==='POST'&&url.pathname==='/memory-stories/'+storyId+'/refinement'){
      const body=JSON.parse((request.postDataBuffer()||Buffer.alloc(0)).toString());assert.equal(body.revision,story.revision);refinementPosts++;
      if(refuseNextRetry){
        refuseNextRetry=false;status=503;
        responseBody=Buffer.from(JSON.stringify({detail:'Synthetic local retry unavailable'}));
      }else{
        previousJobError=null;status=200;
        responseBody=Buffer.from(JSON.stringify({version:1,id:jobId,kind:'narrative',state:'queued',created_at:1900000000,updated_at:1900000000,expires_at:1900003600,error_code:null,result:null,needs_review:true,base_revision:story.revision}));
      }
      headersOut={'content-type':'application/json'};
    }else if(entry.method==='GET'&&url.pathname==='/memory-community/v1/capabilities'){
      const result=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});status=result.status;responseBody=Buffer.from(result.body,'base64');headersOut={...result.headers};
      const caps=JSON.parse(responseBody.toString());caps.enabled=true;caps.auto_refinement_enabled=true;responseBody=Buffer.from(JSON.stringify(caps));
    }else if(entry.method==='GET'&&url.pathname==='/memory-community/v1/jobs/'+jobId){
      jobPolls++;const state=jobPolls===1?'deferred':'ready';
      const result=state==='ready'?{version:1,title:modelTitle,chapters:story.chapters.map(chapter=>({id:chapter.id,narration:chapter.id==='chapter-2'?'待家人核对的整理建议：湖边散步。':chapter.narration,source_ids:[]})),questions:['那天还有谁同行？'],needs_review:true}:null;
      responseBody=Buffer.from(JSON.stringify({version:1,id:jobId,kind:'narrative',state,created_at:1900000000,updated_at:1900000000,expires_at:1900003600,error_code:null,result,needs_review:true,base_revision:story.revision}));status=200;headersOut={'content-type':'application/json'};
    }else{
      if(entry.method==='PUT'&&url.pathname==='/memory-stories/'+storyId)saveBodies.push(JSON.parse((request.postDataBuffer()||Buffer.alloc(0)).toString()));
      const result=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});status=result.status;responseBody=Buffer.from(result.body,'base64');headersOut={...result.headers};
      if(entry.method==='GET'&&url.pathname==='/memory-stories/'+storyId&&status===200){
        story=JSON.parse(responseBody.toString());if(!realShelfDraft)story.auto_refinement=noAutoJob?null:{version:1,id:jobId,kind:'narrative',state:previousJobError?'failed':'queued',created_at:1900000000,updated_at:1900000000,expires_at:1900003600,error_code:previousJobError,result:null,needs_review:true,base_revision:staleMetadata?'999':story.revision};
        responseBody=Buffer.from(JSON.stringify(story));
      }
    }
    entry.status=status;delete headersOut['content-length'];delete headersOut['content-encoding'];await route.fulfill({status,headers:headersOut,body:responseBody});
  });
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));page.on('dialog',dialog=>{const dismiss=confirmAction==='dismiss';if(dismiss)confirmAction='accept';void (dismiss?dialog.dismiss():dialog.accept()).then(()=>{if(dialogWaiter){dialogWaiter();dialogWaiter=null;}}).catch(()=>{});});
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  await page.locator('.saved-memory-cover').first().click();const panel=page.locator('#story-reader-title').locator('xpath=..').locator('.story-auto-refinement');await panel.waitFor({timeout:5000});
  assert.deepEqual(story.chapters.map(chapter=>chapter.id),['chapter-1','chapter-2'],'both generated chapters were saved through the fixture API');assert.deepEqual(story.chapters.map(chapter=>chapter.asset_ids),[['101'],['102']],'the generated saved chapters retain their ordered frame references');
  assert.match(await panel.textContent(),/本地 AI 整理建议 · 待核对/);const original='家人一起沿着湖边散步，留下了这段回忆。',originalReaderHeading=await page.locator('#story-reader-title').textContent();assert.equal(await page.locator('#story-reader-text').textContent(),original);
  assert.equal(await panel.getByRole('button',{name:'整理这个故事'}).count(),1,'the existing story has an explicit refinement action');assert.equal(refinementPosts,0,'opening the saved story does not queue generation');
  await panel.getByRole('button',{name:'整理这个故事'}).click();await panel.getByText('整理任务已排队。稍后会自动检查；你也可以手动刷新。').waitFor();assert.equal(refinementPosts,1,'one explicit click queues one revision-bound refinement');assert.equal(await page.locator('#story-reader-text').textContent(),original,'queueing never edits the saved story');
  await page.locator('#story-reader-close').click();await page.waitForTimeout(3200);assert.equal(jobPolls,0,'closing the story stops queued-job polling');
  noAutoJob=false;staleMetadata=true;await page.locator('.saved-memory-cover').first().click();await page.locator('#story-reader').waitFor({state:'visible'});assert.equal(await page.locator('.story-auto-refinement').count(),0,'metadata for a different base revision is refused');await page.locator('#story-reader-close').click();staleMetadata=false;
  const retry=panel.getByRole('button',{name:'重试本地整理',exact:true});
  previousJobError='source_changed';
  await page.locator('.saved-memory-cover').first().click();await panel.waitFor();
  assert.equal(await retry.count(),0,'a changed-source failure cannot be retried');
  await page.locator('#story-reader-close').click();
  previousJobError='model_timeout';
  await page.locator('.saved-memory-cover').first().click();await retry.waitFor();
  assert.equal(await retry.isEnabled(),true,'the opened reader enables an eligible retry');
  assert.equal(await panel.getAttribute('data-job-id'),jobId);
  assert.equal(refinementPosts,1,'reopening a failed job does not retry automatically');
  refuseNextRetry=true;
  await retry.press('Enter');
  await panel.getByText('暂时无法重试此整理建议。请稍后再试。',{exact:true}).waitFor();
  assert.equal(refinementPosts,2);
  assert.equal(await page.locator('#story-reader-text').textContent(),original);
  await retry.press('Enter');
  await panel.getByText('整理任务已排队。稍后会自动检查；你也可以手动刷新。').waitFor();
  assert.equal(refinementPosts,3,'each explicit retry makes one request for the same story revision');
  assert.equal(await panel.getAttribute('data-job-id'),jobId);
  assert.equal(await retry.count(),0);
  assert.equal(saveBodies.length,0,'retry neither edits nor saves the story');
  console.log('PASS A failed saved-story refinement offers an explicit same-job retry and keeps the original intact');
  const deferNotice='资料暂时忙碌，稍后会继续检查本地 AI 建议。';
  await panel.getByText(deferNotice,{exact:true}).waitFor({timeout:7000});assert.equal(jobPolls,1,'deferred is shown as a temporary state and remains pollable');
  await page.waitForFunction(()=>document.querySelector('.story-auto-refinement-status')?.textContent.includes('建议已就绪'),null,{timeout:7000});
  assert.match(await panel.textContent(),/待家人核对的整理建议：湖边散步。/);assert.match(await panel.textContent(),/那天还有谁同行/);assert.match(await panel.textContent(),/原标题保留/);assert.match(await panel.textContent(),new RegExp(originalTitle));assert.equal(await panel.getByText(modelTitle,{exact:true}).count(),0,'the model title is not presented as a replacement');assert.equal(await page.locator('#story-reader-title').textContent(),originalReaderHeading,'the reader heading remains unchanged');assert.equal(await page.locator('#story-reader-text').textContent(),original,'the saved reader keeps showing its original text');
  const rows=panel.locator('.story-auto-refinement-row'),sections=panel.locator('.story-auto-refinement-section');assert.equal(await rows.count(),2,'the saved story comparison includes both chapters');assert.equal(await sections.count(),2);
  const firstRow=rows.nth(0),firstOriginal=firstRow.locator('.story-auto-refinement-comparison'),firstSuggested=firstRow.locator('.story-auto-refinement-chapter');
  assert.equal(await firstOriginal.isVisible(),true);assert.equal(await firstSuggested.isVisible(),true);
  assert.match(await firstOriginal.textContent(),new RegExp(original));assert.match(await firstSuggested.textContent(),new RegExp(original),'the first chapter wording is unchanged in the suggestion');
  assert.equal(await firstRow.locator('mark').count(),0,'unchanged chapters have no highlights');
  const secondRow=rows.nth(1),originalCard=secondRow.locator('.story-auto-refinement-comparison'),suggestedCard=secondRow.locator('.story-auto-refinement-chapter');
  assert.equal(await originalCard.isVisible(),true);assert.equal(await suggestedCard.isVisible(),true);
  assert.match(await originalCard.locator('h5').textContent(),/当前保存的原文/);assert.match(await originalCard.textContent(),/家人接着坐在湖边聊天，记录那天的心情。/);
  assert.match(await suggestedCard.locator('h5').textContent(),/整理建议/);assert.match(await suggestedCard.textContent(),/待家人核对的整理建议：湖边散步。/);
  assert.equal(await originalCard.locator('p').textContent(),'家人接着坐在湖边聊天，记录那天的心情。');
  assert.equal(await suggestedCard.locator('p').textContent(),'待家人核对的整理建议：湖边散步。');
  assert((await originalCard.locator('mark').allTextContents()).join('').includes('聊天'));
  assert((await suggestedCard.locator('mark').allTextContents()).join('').includes('整理建议'));
  await panel.getByText('已标出两版文字之间的变化。',{exact:true}).waitFor();
  if(process.env.PH_BROWSER_ARTIFACTS){
    await fs.mkdir(process.env.PH_BROWSER_ARTIFACTS,{recursive:true});
    await panel.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-review-desktop.png')});
    await page.setViewportSize({width:390,height:844});
    const phonePanelBox=await panel.boundingBox();assert.ok(phonePanelBox&&phonePanelBox.x>=0&&phonePanelBox.x+phonePanelBox.width<=390,'the refinement panel fits the phone viewport');
    assert.equal(await secondRow.evaluate(node=>node.scrollWidth<=node.clientWidth),true,'chapter comparison fits at 390px');
    await panel.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-review-phone-viewport.png')});
    const scaled=await panel.evaluate(root=>[...root.querySelectorAll('*')].filter(node=>[...node.childNodes].some(child=>child.nodeType===3&&child.textContent.trim())).map((node,index)=>{const style=getComputedStyle(node),row={index,size:parseFloat(style.fontSize),height:parseFloat(style.lineHeight),font:node.style.fontSize,line:node.style.lineHeight};node.dataset.reviewScale=String(index);node.style.fontSize=`${row.size*1.5}px`;if(Number.isFinite(row.height))node.style.lineHeight=`${row.height*1.5}px`;return row;}));
    assert.equal(await secondRow.evaluate(node=>node.scrollWidth<=node.clientWidth),true,'chapter comparison wraps at 150% text');
    await panel.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-review-phone-text150-viewport.png')});
    await panel.evaluate((root,rows)=>rows.forEach(row=>{const node=root.querySelector(`[data-review-scale="${row.index}"]`);if(node){node.style.fontSize=row.font;node.style.lineHeight=row.line;delete node.dataset.reviewScale;}}),scaled);
    await page.setViewportSize({width:1280,height:900});
  }
  await page.locator('#story-reader-close').click();
  const preparedShelf=await rpc({command:'seed-shelf-refinement'});
  assert.match(preparedShelf.job_id,/^[0-9a-f-]{36}$/);
  realShelfDraft=true;
  const readsBeforeShelf=requests.length;
  await page.locator('#saved-memory-refresh').click();
  const shelfReview=page.getByRole('button',{name:`核对 AI 草稿: ${originalTitle}`,exact:true});
  await shelfReview.waitFor();
  assert.equal(await page.locator('.saved-refinement-review').count(),1);
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  assert(await shelfReview.evaluate(el=>el.getBoundingClientRect().height>=44&&el.scrollWidth<=el.clientWidth));
  if(process.env.PH_BROWSER_ARTIFACTS){
    await shelfReview.scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'review-from-saved-stories-phone-zh-150.png')});
  }
  await shelfReview.press('Enter');
  await panel.waitFor({state:'visible'});
  assert.equal(await panel.locator('h3').evaluate(el=>el===document.activeElement),true);
  assert.equal(await page.locator('#story-reader-text').textContent(),original);
  assert.match(await panel.textContent(),/待家人核对的整理建议：湖边散步。/);
  assert.match(await panel.textContent(),/合成的另一种第一章写法。/);
  assert(requests.slice(readsBeforeShelf).every(row=>['GET','HEAD'].includes(row.method)));
  const firstChapterChoice=panel.locator('.story-auto-refinement-section[data-chapter-id="chapter-1"] input');
  const secondChapterChoice=panel.locator('.story-auto-refinement-section[data-chapter-id="chapter-2"] input');
  assert.equal(await firstChapterChoice.isChecked(),true);
  assert.equal(await secondChapterChoice.isChecked(),true);
  await firstChapterChoice.press('Space');
  assert.equal(await firstChapterChoice.isChecked(),false);
  await secondChapterChoice.uncheck();
  assert.equal(await panel.getByRole('button',{name:'审核通过，带入编辑'}).isDisabled(),true);
  await secondChapterChoice.check();
  if(process.env.PH_BROWSER_ARTIFACTS){
    const firstChoiceLabel=panel.locator('.story-auto-refinement-section[data-chapter-id="chapter-1"] label');
    await firstChoiceLabel.scrollIntoViewIfNeeded();
    assert(await firstChoiceLabel.evaluate(el=>el.getBoundingClientRect().height>=44&&el.scrollWidth<=el.clientWidth));
    await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-refinement-chapter-choice-phone-zh-150.png')});
  }
  await page.evaluate(()=>{document.documentElement.style.fontSize='';});
  await page.setViewportSize({width:1280,height:900});
  console.log('PASS One keyboard action opens the current prepared draft from its saved story without restarting refinement or saving');

  const keepWrites=requests.filter(item=>['PUT','DELETE'].includes(item.method)).length,keepGenerations=generationPosts(),keepRefinements=refinementPosts;
  await panel.getByRole('button',{name:'保留原文',exact:true}).click();
  await panel.getByText('已保留原文，AI 建议未保存。',{exact:true}).waitFor();
  assert.equal(await panel.locator('.story-auto-refinement-row').count(),0,'keeping the original hides the suggestion comparison');
  assert.equal(requests.filter(item=>['PUT','DELETE'].includes(item.method)).length,keepWrites,'keeping the original does not write');assert.equal(generationPosts(),keepGenerations,'keeping the original does not generate');assert.equal(refinementPosts,keepRefinements);
  await panel.getByRole('button',{name:'重新审核建议',exact:true}).click();await panel.locator('.story-auto-refinement-row').first().waitFor();
  assert.equal(await firstChapterChoice.isChecked(),false);
  assert.equal(await secondChapterChoice.isChecked(),true);
  assert.equal(generationPosts(),keepGenerations,'returning to review reuses the ready suggestion');assert.equal(refinementPosts,keepRefinements);
  if(process.env.PH_BROWSER_ARTIFACTS){
    await page.setViewportSize({width:390,height:844});
    const reader=page.locator('#story-reader'),adoptButton=panel.getByRole('button',{name:'审核通过，带入编辑',exact:true}),keepButton=panel.getByRole('button',{name:'保留原文',exact:true});
    for(const control of [adoptButton,keepButton]){
      await control.scrollIntoViewIfNeeded();assert.equal(await control.isVisible(),true,'reader action is visible after scrolling');
      assert.equal(await control.evaluate(button=>{const rect=button.getBoundingClientRect(),reader=document.querySelector('#story-reader').getBoundingClientRect();return rect.top>=reader.top&&rect.bottom<=reader.bottom;}),true,'reader action fits within the reader viewport after scrolling');
    }
    assert.equal(await reader.evaluate(node=>node.scrollWidth<=node.clientWidth),true,'the reader has no horizontal overflow at 390px');
    await keepButton.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-review-phone-actions.png')});
    await page.setViewportSize({width:1280,height:900});
  }
  await page.locator('#story-reader-edit').click();const editor=page.locator('#story-chapter-editor .story-auto-refinement');await editor.waitFor();assert.match(await editor.textContent(),/原标题保留/);assert.match(await editor.textContent(),new RegExp(originalTitle));assert.equal(await editor.getByText(modelTitle,{exact:true}).count(),0,'the model title stays absent in editor review');
  await editor.getByRole('button',{name:'在阅读器中核对并带入编辑'}).click();const readerPanel=page.locator('#story-reader-title').locator('xpath=..').locator('.story-auto-refinement');await readerPanel.waitFor();
  assert.equal(await firstChapterChoice.isChecked(),false);
  assert.equal(await secondChapterChoice.isChecked(),true);
  assert.equal(generationPosts(),0,'display and polling never create a generation job');
  confirmAction='dismiss';const dismissed=new Promise(resolve=>{dialogWaiter=resolve;});
  await readerPanel.getByRole('button',{name:'审核通过，带入编辑'}).click();await dismissed;
  await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-reader-text').textContent(),original,'declining the adoption confirmation preserves the saved original');assert.equal(saveBodies.length,0,'declining adoption issues no save');assert.equal(requests.filter(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId)).length,0,'declining adoption issues zero story PUTs');
  let phoneEditorBaseSize;
  if(process.env.PH_BROWSER_ARTIFACTS){
    await page.setViewportSize({width:390,height:844});
    phoneEditorBaseSize=await page.evaluate(()=>{
      const root=document.querySelector('#story-workspace'),nodes=[root,root.querySelector('.story-workspace-heading h2'),root.querySelector('#story-chapter-editor'),root.querySelector('#story-approval-status'),...root.querySelectorAll('#story-draft-actions button')];
      const snapshots=nodes.map(node=>({node,prior:node.style.fontSize,size:parseFloat(getComputedStyle(node).fontSize)}));
      for(const item of snapshots){item.node.dataset.approvalScale='150';item.node.dataset.approvalPriorFont=item.prior;item.node.style.fontSize=`${item.size*1.5}px`;}
      return snapshots[2].size;
    });
  }
  confirmAction='accept';const accepted=new Promise(resolve=>{dialogWaiter=resolve;});
  const approveButton=readerPanel.getByRole('button',{name:'审核通过，带入编辑'});await approveButton.focus();await approveButton.press('Enter');await accepted;
  assert.equal(saveBodies.length,0,'approval does not issue a save');assert.equal(requests.filter(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId)).length,0,'approval issues zero story PUTs');
  await page.locator('#story-approval-status').getByText('已带入草稿',{exact:true}).waitFor();
  await page.locator('#story-chapter-editor textarea[maxlength="6000"]').first().waitFor();assert.equal(await page.locator('#story-workspace-title').inputValue(),originalTitle,'bringing prose into the editor preserves the saved story title');
  const approvedText='待家人核对的整理建议：湖边散步。家人补充：那天夕阳很美。',chapter1=page.locator('#story-chapter-editor .story-chapter-card[data-chapter-id="chapter-1"]'),chapter2=page.locator('#story-chapter-editor .story-chapter-card[data-chapter-id="chapter-2"]');
  await chapter2.waitFor();assert.equal(await page.locator('#story-chapter-editor .story-chapter-card').count(),2,'approval preserves both saved chapter cards');
  assert.equal(await chapter1.locator('textarea[maxlength="6000"]').inputValue(),'家人一起沿着湖边散步，留下了这段回忆。','approval leaves the unchanged first chapter intact');
  assert.match(await chapter2.locator('textarea[maxlength="6000"]').inputValue(),/待家人核对的整理建议：湖边散步。/,'only the second chapter suggestion is brought into the editable draft');
  assert.equal(await chapter2.evaluate(card=>{const box=card.getBoundingClientRect();return box.top>=0&&box.top<innerHeight&&box.bottom>0;}),true,'approval scrolls the changed chapter card into view');
  assert.equal(await chapter2.evaluate(card=>card.contains(document.activeElement)),true,'approval focuses the changed chapter card');
  if(process.env.PH_BROWSER_ARTIFACTS){
    const chapterCardSize=await chapter2.evaluate(node=>parseFloat(getComputedStyle(node).fontSize));assert.ok(chapterCardSize>=phoneEditorBaseSize*1.4,`chapter card uses 150% text sizing before approval (${chapterCardSize}px from ${phoneEditorBaseSize}px)`);
    assert.ok(await page.locator('#story-approval-status').evaluate(node=>parseFloat(getComputedStyle(node).fontSize))>16,'approval status is enlarged before approval');
    assert.ok(await page.locator('#story-save-memory').evaluate(node=>parseFloat(getComputedStyle(node).fontSize))>16,'Save button is enlarged before approval');
  }
  assert.equal(await page.locator('#story-approval-status').textContent(),'已带入草稿');
  const saveButton=page.locator('#story-save-memory');assert.match(await saveButton.textContent(),/保存到相册库/,'the explicit Save label is in Chinese');assert.equal(await saveButton.isVisible(),true,'explicit Save remains visible after approval');assert.equal(await saveButton.isEnabled(),true,'explicit Save is enabled after approval');
  if(process.env.PH_BROWSER_ARTIFACTS){
    assert.equal(await page.locator('#story-workspace').evaluate(root=>{const target=root.querySelector('.story-chapter-card[data-chapter-id="chapter-2"]')?.getBoundingClientRect(),head=root.querySelector('.story-workspace-heading')?.getBoundingClientRect(),bar=root.querySelector('#story-draft-actions')?.getBoundingClientRect();return Boolean(target&&head&&bar&&head.bottom<=target.top&&target.top<bar.top);}),true,'the changed card sits below the workspace heading and above draft actions');
    const dialog=page.locator('#story-workspace'),approvalStatus=page.locator('#story-approval-status');
    for(const control of [approvalStatus,saveButton]){const box=await control.evaluate((node,dialogNode)=>{const rect=node.getBoundingClientRect(),frame=dialogNode.getBoundingClientRect();return {inside:rect.width>0&&rect.height>0&&rect.top>=frame.top&&rect.bottom<=frame.bottom&&rect.top>=0&&rect.bottom<=innerHeight,top:rect.top,bottom:rect.bottom,dialogTop:frame.top,dialogBottom:frame.bottom,viewportHeight:innerHeight};},await dialog.elementHandle());assert.equal(box.inside,true,`${control===approvalStatus?'approval text':'Save button'} stays inside the visible 390px dialog at 150% text without scrolling: ${JSON.stringify(box)}`);}
    await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-approval-to-edit-phone-390-text150.png')});
    await page.locator('#story-workspace').evaluate(root=>{
      for(const node of [root,...root.querySelectorAll('[data-approval-scale="150"]')]){if(node.dataset.approvalScale!=='150')continue;node.style.fontSize=node.dataset.approvalPriorFont||'';delete node.dataset.approvalScale;delete node.dataset.approvalPriorFont;}
    });
    await page.setViewportSize({width:1280,height:900});
    await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-approval-desktop.png')});
  }
  await chapter2.locator('textarea[maxlength="6000"]').fill(approvedText);assert.equal(saveBodies.length,0,'editing an adopted suggestion still does not save automatically');assert.equal(requests.filter(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId)).length,0,'approval and editing issue zero story PUTs');
  await saveButton.click();const deadline=Date.now()+5000;while(Date.now()<deadline&&!requests.some(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId)))await new Promise(resolve=>setTimeout(resolve,25));
  const save=requests.find(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId));assert.ok(save,'the adopted wording is saved only by the explicit Save action');assert.match(save.path,/[?&]auto_refine=0(?:&|$)/,'the adoption save skips one refinement cycle');
  assert.equal(saveBodies.length,1);assert.equal(requests.filter(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId)).length,1,'exactly one story PUT is sent by explicit Save');await page.locator('#story-workspace-status').getByText('已保存到这个相册库',{exact:false}).waitFor();assert.equal(save.status,200,'the fixture API confirms the explicit story Save');assert.equal(saveBodies[0].title,originalTitle,'the explicit adoption save keeps the saved story title');
  const savedChapters=JSON.parse(saveBodies[0].chapters);assert.deepEqual(savedChapters.map(chapter=>chapter.id),['chapter-1','chapter-2'],'the explicit save preserves chapter IDs and order');assert.equal(savedChapters[0].narration,'家人一起沿着湖边散步，留下了这段回忆。','the explicit save keeps the original for the unchecked chapter');assert.equal(savedChapters[1].narration,approvedText,'the explicit save persists only the reviewed second chapter edit');
  assert.deepEqual(savedChapters.map(chapter=>chapter.asset_ids),[['101'],['102']],'the explicit save preserves chapter frame ownership and order');
  assert.equal((await page.locator('#story-approval-status').textContent()).trim(),'','approval status clears after confirmed Save');assert.equal(await page.locator('#story-approval-status').isHidden(),true,'approval status is hidden after confirmed Save');
  noAutoJob=true;realShelfDraft=false;
  await page.locator('#story-workspace-close').click();await page.locator('#story-workspace').waitFor({state:'hidden'});
  await page.locator('.saved-memory-cover').first().click();await page.locator('#story-reader-chapters').getByRole('button').nth(1).click();await page.locator('#story-reader-text').getByText(approvedText,{exact:true}).waitFor();assert.equal(await page.locator('#story-reader-memory-title').textContent(),originalTitle,'reopening the saved story keeps its original story title');
  assert.equal(generationPosts(),0);assert.equal(refinementPosts,3);assert.deepEqual(external,[]);assert.deepEqual(pageErrors,[]);
  assert.equal(jobPolls,2,'deferred and ready refinement states were both polled');
  assert.equal(requests.filter(row=>row.method==='GET'&&row.path.startsWith(`/memory-community/v1/jobs/${preparedShelf.job_id}?`)).length,2,'both adoption attempts recheck the real ready shelf job');
  const terminalPollCount=jobPolls;await page.waitForTimeout(3200);assert.equal(jobPolls,terminalPollCount,'polling stops when the job reaches ready');
  await page.locator('#story-reader-close').click();noAutoJob=false;await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='en');
  await page.locator('.saved-memory-cover').first().click();await page.waitForFunction(()=>document.querySelector('.story-auto-refinement-status')?.textContent.includes('ready'),null,{timeout:7000});
  await page.locator('#story-reader-edit').click();const englishEditor=page.locator('#story-chapter-editor .story-auto-refinement');await englishEditor.waitFor();await englishEditor.getByRole('button',{name:'Review and bring into the reader'}).click();
  const englishReaderPanel=page.locator('#story-reader-title').locator('xpath=..').locator('.story-auto-refinement');await englishReaderPanel.waitFor();
  const englishApprove=englishReaderPanel.getByRole('button',{name:'Approve and edit'});await englishApprove.focus();await englishApprove.press('Enter');
  await page.locator('#story-approval-status').getByText('Applied to draft',{exact:true}).waitFor();const englishSave=page.locator('#story-save-memory');assert.equal((await englishSave.textContent()).trim(),'Save to library');assert.equal(await englishSave.isVisible(),true);assert.equal(await englishSave.isEnabled(),true);assert.equal(requests.filter(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId)).length,1,'English approval also issues no story PUT');
  if(process.env.PH_BROWSER_ARTIFACTS)await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-approval-english-desktop.png')});
  assert.deepEqual(external,[]);assert.deepEqual(pageErrors,[]);
  console.log('PASS local refinement defer-to-ready, chapter-specific review, declined approval, explicit save/reopen and English approval labels');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{try{await context?.close();await browser?.close();}finally{if(bridge&&!bridge.killed){bridge.stdin.end();bridge.kill();}}});
