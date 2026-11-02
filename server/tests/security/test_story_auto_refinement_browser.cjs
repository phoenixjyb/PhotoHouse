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
let browser,context,page,jobPolls=0,refinementPosts=0,external=[],staleMetadata=false,noAutoJob=true;
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
      jobPolls++;const state=jobPolls===1?'queued':'ready';
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
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));page.on('dialog',dialog=>{void dialog.accept().catch(()=>{});});
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  await page.locator('.saved-memory-cover').first().click();const panel=page.locator('#story-reader-title').locator('xpath=..').locator('.story-auto-refinement');await panel.waitFor({timeout:5000});
  assert.match(await panel.textContent(),/AI 整理建议/);const original='家人一起沿着湖边散步，留下了这段回忆。',originalReaderHeading=await page.locator('#story-reader-title').textContent();assert.equal(await page.locator('#story-reader-text').textContent(),original);
  assert.equal(await panel.getByRole('button',{name:'整理这个故事'}).count(),1,'the existing story has an explicit refinement action');assert.equal(refinementPosts,0,'opening the saved story does not queue generation');
  await panel.getByRole('button',{name:'整理这个故事'}).click();await panel.getByText('整理任务已排队。稍后会自动检查；你也可以手动刷新。').waitFor();assert.equal(refinementPosts,1,'one explicit click queues one revision-bound refinement');assert.equal(await page.locator('#story-reader-text').textContent(),original,'queueing never edits the saved story');
  await page.locator('#story-reader-close').click();await page.waitForTimeout(3200);assert.equal(jobPolls,0,'closing the story stops queued-job polling');
  noAutoJob=false;staleMetadata=true;await page.locator('.saved-memory-cover').first().click();await page.locator('#story-reader').waitFor({state:'visible'});assert.equal(await page.locator('.story-auto-refinement').count(),0,'metadata for a different base revision is refused');await page.locator('#story-reader-close').click();staleMetadata=false;
  await page.locator('.saved-memory-cover').first().click();await page.locator('#story-reader-title').locator('xpath=..').locator('.story-auto-refinement').waitFor();
  await page.waitForFunction(()=>document.querySelector('.story-auto-refinement-status')?.textContent.includes('建议已就绪'),null,{timeout:7000});
  assert.match(await panel.textContent(),/待家人核对的整理建议：湖边散步。/);assert.match(await panel.textContent(),/那天还有谁同行/);assert.match(await panel.textContent(),/原标题保留 \/ Original title kept/);assert.match(await panel.textContent(),new RegExp(originalTitle));assert.equal(await panel.getByText(modelTitle,{exact:true}).count(),0,'the model title is not presented as a replacement');assert.equal(await page.locator('#story-reader-title').textContent(),originalReaderHeading,'the reader heading remains unchanged');assert.equal(await page.locator('#story-reader-text').textContent(),original,'the saved reader keeps showing its original text');
  if(process.env.PH_BROWSER_ARTIFACTS){await fs.mkdir(process.env.PH_BROWSER_ARTIFACTS,{recursive:true});await panel.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-title-preservation-desktop.png')});await page.setViewportSize({width:390,height:844});const phonePanelBox=await panel.boundingBox();assert.ok(phonePanelBox&&phonePanelBox.x>=0&&phonePanelBox.x+phonePanelBox.width<=390,'the refinement panel fits the phone viewport');await panel.screenshot({path:path.join(process.env.PH_BROWSER_ARTIFACTS,'story-title-preservation-phone.png')});await page.setViewportSize({width:1280,height:900});}
  await page.locator('#story-reader-edit').click();const editor=page.locator('#story-chapter-editor .story-auto-refinement');await editor.waitFor();assert.match(await editor.textContent(),/原标题保留 \/ Original title kept/);assert.match(await editor.textContent(),new RegExp(originalTitle));assert.equal(await editor.getByText(modelTitle,{exact:true}).count(),0,'the model title stays absent in editor review');
  await editor.getByRole('button',{name:'在阅读器中核对并带入编辑'}).click();const readerPanel=page.locator('#story-reader-title').locator('xpath=..').locator('.story-auto-refinement');await readerPanel.waitFor();
  const generationPosts=()=>requests.filter(item=>item.method==='POST'&&item.path.startsWith('/memory-community/v1/jobs')).length;assert.equal(generationPosts(),0,'display and polling never create a generation job');
  await readerPanel.getByRole('button',{name:'将建议带入编辑'}).click();await page.locator('#story-chapter-editor textarea').first().waitFor();assert.equal(await page.locator('#story-workspace-title').inputValue(),originalTitle,'bringing prose into the editor preserves the saved story title');
  assert.match(await page.locator('#story-chapter-editor').textContent(),/待家人核对的整理建议：湖边散步。/,'the suggestion is only brought into the editable draft after confirmation');
  await page.locator('#story-save-memory').click();const deadline=Date.now()+5000;while(Date.now()<deadline&&!requests.some(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId)))await new Promise(resolve=>setTimeout(resolve,25));
  const save=requests.find(item=>item.method==='PUT'&&item.path.startsWith('/memory-stories/'+storyId));assert.ok(save,'the adopted wording is saved only by the explicit Save action');assert.match(save.path,/[?&]auto_refine=0(?:&|$)/,'the adoption save skips one refinement cycle');
  assert.equal(saveBodies.length,1);assert.equal(saveBodies[0].title,originalTitle,'the explicit adoption save keeps the saved story title');assert.equal(generationPosts(),0);assert.equal(refinementPosts,1);assert.deepEqual(external,[]);assert.deepEqual(pageErrors,[]);assert.ok(jobPolls>=2,'queued refinement was polled until ready');const terminalPollCount=jobPolls;await page.waitForTimeout(3200);assert.equal(jobPolls,terminalPollCount,'polling stops when the job reaches ready');
  console.log('PASS saved-story explicit refinement, no load-time queue, stale-revision refusal, close/terminal polling stops, original title and text comparison, prose-only explicit adoption and one-save refinement skip');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{try{await context?.close();await browser?.close();}finally{if(bridge&&!bridge.killed){bridge.stdin.end();bridge.kill();}}});
