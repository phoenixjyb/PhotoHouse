'use strict';
/* Saved-story refinement stays review-only through the real workspace UI. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs/promises');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'memory_community_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,storyId,story,readyResolve,readyReject;const pending=new Map(),requests=[],pageErrors=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){storyId=value.story_id;readyResolve();return;}const call=pending.get(value.id);if(call){pending.delete(value.id);call.resolve(value);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Synthetic bridge failed (${code})`));for(const call of pending.values())call.reject(new Error('Synthetic bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const jobId='5f79b251-a8fd-43b6-bfc2-d130b6055fb6',modelTitle='MODEL_TITLE_MUST_NOT_APPEAR',originalTitle='一起走过的日子';let saveBodies=[];
let browser,context,page,jobPolls=0,refinementPosts=0,external=[],staleMetadata=false,noAutoJob=true,confirmAction='accept',dialogWaiter=null;
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
      responseBody=Buffer.from(JSON.stringify({version:1,id:jobId,kind:'narrative',state:'queued',created_at:1900000000,updated_at:1900000000,expires_at:1900003600,error_code:null,result:null,needs_review:true,base_revision:story.revision}));status=200;headersOut={'content-type':'application/json'};
    }else if(entry.method==='GET'&&url.pathname==='/memory-community/v1/capabilities'){
      const result=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});status=result.status;responseBody=Buffer.from(result.body,'base64');headersOut={...result.headers};
      const caps=JSON.parse(responseBody.toString());caps.enabled=true;caps.auto_refinement_enabled=true;responseBody=Buffer.from(JSON.stringify(caps));
    }else if(entry.method==='GET'&&url.pathname==='/memory-community/v1/jobs/'+jobId){
      jobPolls++;const state=jobPolls===1?'deferred':'ready';
      const result=state==='ready'?{version:1,title:modelTitle,chapters:story.chapters.map(chapter=>({id:chapter.id,narration:'待家人核对的整理建议：湖边散步。',source_ids:[]})),questions:['那天还有谁同行？'],needs_review:true}:null;
      responseBody=Buffer.from(JSON.stringify({version:1,id:jobId,kind:'narrative',state,created_at:1900000000,updated_at:1900000000,expires_at:1900003600,error_code:null,result,needs_review:true,base_revision:story.revision}));status=200;headersOut={'content-type':'application/json'};
    }else{
      if(entry.method==='PUT'&&url.pathname==='/memory-stories/'+storyId)saveBodies.push(JSON.parse((request.postDataBuffer()||Buffer.alloc(0)).toString()));
      const result=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});status=result.status;responseBody=Buffer.from(result.body,'base64');headersOut={...result.headers};
      if(entry.method==='GET'&&url.pathname==='/memory-stories/'+storyId&&status===200){
        story=JSON.parse(responseBody.toString());story.auto_refinement=noAutoJob?null:{version:1,id:jobId,kind:'narrative',state:'queued',created_at:1900000000,updated_at:1900000000,expires_at:1900003600,error_code:null,result:null,needs_review:true,base_revision:staleMetadata?'999':story.revision};
        responseBody=Buffer.from(JSON.stringify(story));
      }
    }
    delete headersOut['content-length'];delete headersOut['content-encoding'];await route.fulfill({status,headers:headersOut,body:responseBody});
  });
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));page.on('dialog',dialog=>{const dismiss=confirmAction==='dismiss';if(dismiss)confirmAction='accept';void (dismiss?dialog.dismiss():dialog.accept()).then(()=>{if(dialogWaiter){dialogWaiter();dialogWaiter=null;}}).catch(()=>{});});
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  await page.locator('.saved-memory-cover').first().click();const panel=page.locator('#story-reader-title').locator('xpath=..').locator('.story-auto-refinement');await panel.waitFor({timeout:5000});
  assert.match(await panel.textContent(),/本地 AI 整理建议 · 待核对/);const original='家人一起沿着湖边散步，留下了这段回忆。',originalReaderHeading=await page.locator('#story-reader-title').textContent();assert.equal(await page.locator('#story-reader-text').textContent(),original);
  assert.equal(await panel.getByRole('button',{name:'整理这个故事'}).count(),1,'the existing story has an explicit refinement action');assert.equal(refinementPosts,0,'opening the saved story does not queue generation');
  await panel.getByRole('button',{name:'整理这个故事'}).click();await panel.getByText('整理任务已排队。稍后会自动检查；你也可以手动刷新。').waitFor();assert.equal(refinementPosts,1,'one explicit click queues one revision-bound refinement');assert.equal(await page.locator('#story-reader-text').textContent(),original,'queueing never edits the saved story');
  await page.locator('#story-reader-close').click();await page.waitForTimeout(3200);assert.equal(jobPolls,0,'closing the story stops queued-job polling');
  noAutoJob=false;staleMetadata=true;await page.locator('.saved-memory-cover').first().click();await page.locator('#story-reader').waitFor({state:'visible'});assert.equal(await page.locator('.story-auto-refinement').count(),0,'metadata for a different base revision is refused');await page.locator('#story-reader-close').click();staleMetadata=false;
  await page.locator('.saved-memory-cover').first().click();await page.locator('#story-reader-title').locator('xpath=..').locator('.story-auto-refinement').waitFor();
  const deferNotice='资料暂时忙碌，稍后会继续检查本地 AI 建议。';
  await panel.getByText(deferNotice,{exact:true}).waitFor({timeout:7000});assert.equal(jobPolls,1,'deferred is shown as a temporary state and remains pollable');
  await page.waitForFunction(()=>document.querySelector('.story-auto-refinement-status')?.textContent.includes('建议已就绪'),null,{timeout:7000});
  assert.match(await panel.textContent(),/待家人核对的整理建议：湖边散步。/);assert.match(await panel.textContent(),/那天还有谁同行/);assert.match(await panel.textContent(),/原标题保留/);assert.match(await panel.textContent(),new RegExp(originalTitle));assert.equal(await panel.getByText(modelTitle,{exact:true}).count(),0,'the model title is not presented as a replacement');assert.equal(await page.locator('#story-reader-title').textContent(),originalReaderHeading,'the reader heading remains unchanged');assert.equal(await page.locator('#story-reader-text').textContent(),original,'the saved reader keeps showing its original text');
  const rows=panel.locator('.story-auto-refinement-row');assert.equal(await rows.count(),1,'the story comparison is grouped by chapter');
  const row=rows.first(),originalCard=row.locator('.story-auto-refinement-comparison'),suggestedCard=row.locator('.story-auto-refinement-chapter');
  assert.equal(await originalCard.isVisible(),true);assert.equal(await suggestedCard.isVisible(),true);
  assert.match(await originalCard.locator('h5').textContent(),/当前保存的原文/);assert.match(await originalCard.textContent(),new RegExp(original));
  assert.match(await suggestedCard.locator('h5').textContent(),/整理建议/);assert.match(await suggestedCard.textContent(),/待家人核对的整理建议：湖边散步。/);
  if(process.env.PH_BROWSER_ARTIFACTS){
    await fs.mkdir(process.env.PH_BROWSER_ARTIFACTS,{recursive:true});
    await panel.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-review-desktop.png')});
    await page.setViewportSize({width:390,height:844});
    const phonePanelBox=await panel.boundingBox();assert.ok(phonePanelBox&&phonePanelBox.x>=0&&phonePanelBox.x+phonePanelBox.width<=390,'the refinement panel fits the phone viewport');
    assert.equal(await row.evaluate(node=>node.scrollWidth<=node.clientWidth),true,'chapter comparison fits at 390px');
    await panel.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-review-phone-viewport.png')});
    const scaled=await panel.evaluate(root=>[...root.querySelectorAll('*')].filter(node=>[...node.childNodes].some(child=>child.nodeType===3&&child.textContent.trim())).map((node,index)=>{const style=getComputedStyle(node),row={index,size:parseFloat(style.fontSize),height:parseFloat(style.lineHeight),font:node.style.fontSize,line:node.style.lineHeight};node.dataset.reviewScale=String(index);node.style.fontSize=`${row.size*1.5}px`;if(Number.isFinite(row.height))node.style.lineHeight=`${row.height*1.5}px`;return row;}));
    assert.equal(await row.evaluate(node=>node.scrollWidth<=node.clientWidth),true,'chapter comparison wraps at 150% text');
    await panel.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-local-ai-review-phone-text150-viewport.png')});
    await panel.evaluate((root,rows)=>rows.forEach(row=>{const node=root.querySelector(`[data-review-scale="${row.index}"]`);if(node){node.style.fontSize=row.font;node.style.lineHeight=row.line;delete node.dataset.reviewScale;}}),scaled);
    await page.setViewportSize({width:1280,height:900});
  }
  const keepWrites=requests.filter(item=>['PUT','DELETE'].includes(item.method)).length,keepGenerations=generationPosts(),keepRefinements=refinementPosts;
  await panel.getByRole('button',{name:'保留原文',exact:true}).click();
  await panel.getByText('已保留原文，AI 建议未保存。',{exact:true}).waitFor();
  assert.equal(await panel.locator('.story-auto-refinement-row').count(),0,'keeping the original hides the suggestion comparison');
  assert.equal(requests.filter(item=>['PUT','DELETE'].includes(item.method)).length,keepWrites,'keeping the original does not write');assert.equal(generationPosts(),keepGenerations,'keeping the original does not generate');assert.equal(refinementPosts,keepRefinements);
  await panel.getByRole('button',{name:'重新审核建议',exact:true}).click();await panel.locator('.story-auto-refinement-row').waitFor();
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
  assert.equal(generationPosts(),0,'display and polling never create a generation job');
  confirmAction='dismiss';const dismissed=new Promise(resolve=>{dialogWaiter=resolve;});
  await readerPanel.getByRole('button',{name:'审核通过，带入编辑'}).click();await dismissed;
  await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-reader-text').textContent(),original,'declining the adoption confirmation preserves the saved original');assert.equal(saveBodies.length,0,'declining adoption issues no save');
  confirmAction='accept';const accepted=new Promise(resolve=>{dialogWaiter=resolve;});
  await readerPanel.getByRole('button',{name:'审核通过，带入编辑'}).click();await accepted;
  await page.locator('#story-chapter-editor .story-auto-refinement-status').getByText('本地 AI 建议已带入编辑，尚未保存。你可以继续修改，再点击“保存到相册库”。',{exact:true}).waitFor();
  await page.locator('#story-chapter-editor textarea').first().waitFor();assert.equal(await page.locator('#story-workspace-title').inputValue(),originalTitle,'bringing prose into the editor preserves the saved story title');
  const approvedText='待家人核对的整理建议：湖边散步。家人补充：那天夕阳很美。';
  const narration=page.locator('#story-chapter-editor textarea').first();assert.match(await narration.inputValue(),/待家人核对的整理建议：湖边散步。/,'the suggestion is only brought into the editable draft after confirmation');
  await narration.fill(approvedText);assert.equal(saveBodies.length,0,'editing an adopted suggestion still does not save automatically');
  await page.locator('#story-save-memory').click();const deadline=Date.now()+5000;while(Date.now()<deadline&&!requests.some(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId)))await new Promise(resolve=>setTimeout(resolve,25));
  const save=requests.find(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId));assert.ok(save,'the adopted wording is saved only by the explicit Save action');assert.match(save.path,/[?&]auto_refine=0(?:&|$)/,'the adoption save skips one refinement cycle');
  assert.equal(saveBodies.length,1);assert.equal(saveBodies[0].title,originalTitle,'the explicit adoption save keeps the saved story title');assert.equal(JSON.parse(saveBodies[0].chapters)[0].narration,approvedText,'the explicit save persists the reviewed edit');
  noAutoJob=true;
  await page.locator('#story-workspace-close').click();await page.locator('#story-workspace').waitFor({state:'hidden'});
  await page.locator('.saved-memory-cover').first().click();await page.locator('#story-reader-text').getByText(approvedText,{exact:true}).waitFor();assert.equal(await page.locator('#story-reader-title').textContent(),originalReaderHeading,'reopening the saved story keeps the original title');
  assert.equal(generationPosts(),0);assert.equal(refinementPosts,1);assert.deepEqual(external,[]);assert.deepEqual(pageErrors,[]);assert.ok(jobPolls>=3,'deferred and ready refinement states were both polled');const terminalPollCount=jobPolls;await page.waitForTimeout(3200);assert.equal(jobPolls,terminalPollCount,'polling stops when the job reaches ready');
  console.log('PASS local refinement defer-to-ready, original/suggestion comparison, keep-and-reopen review, declined adoption, edited explicit save and saved-story reopen');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{try{await context?.close();await browser?.close();}finally{if(bridge&&!bridge.killed){bridge.stdin.end();bridge.kill();}}});
