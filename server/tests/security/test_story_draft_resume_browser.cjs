'use strict';
/* First-story guide: real Web UI and closed ASGI over synthetic SQLite. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-story-draft-resume-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pending=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const call=pending.get(result.id);if(call){pending.delete(result.id);call.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Browser bridge failed (${code})`));for(const call of pending.values())call.reject(new Error('Browser bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const external=[],errors=[],requests=[];
let browser,context,page,shelfMode=null,shelfHold=false,releaseShelf,arriveShelf,previewHold=false,releasePreview,arrivePreview;
let firstSave=true,saveBodies=[],saveResponses=[],denyPreview=false,stripEvidence=false,saveFailures=[];
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const ignoreClosedRoute=error=>{if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;};
const count=(method,pattern)=>requests.filter(item=>item.method===method&&pattern.test(item.path)).length;
const pass=label=>console.log('PASS '+label);
const waitForRecorded=async(predicate,label,timeoutMs=8000)=>{const deadline=Date.now()+timeoutMs;while(Date.now()<deadline){const value=requests.find(predicate);if(value)return value;await new Promise(resolve=>setTimeout(resolve,25));}throw new Error(`Timed out waiting for ${label}`);};
const waitForShelfFailure=status=>waitForRecorded(item=>item.status===status&&item.method==='GET'&&/^\/memory-stories(?:\?|$)/.test(item.path),`${status} shelf response`);

const testRun=(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1200,height:900},serviceWorkers:'block',acceptDownloads:true});
  await context.addInitScript(()=>{
    let Constructor;
    Object.defineProperty(window,'PhotoHouseStoryWorkspace',{configurable:true,get:()=>Constructor,set:value=>{
      Constructor=config=>{
        let forcedAccount=null,forcedLanguage=null;const originalScope=config.scope;
        const instance=value({...config,scope:()=>({...originalScope(),...(forcedAccount?{account:forcedAccount}:{}),...(forcedLanguage?{language:forcedLanguage}:{})})});
        window.__storyWorkspaceTest=instance;window.__storyWorkspaceTestScope=config.scope;
        window.__setStoryWorkspaceTestAccount=account=>{forcedAccount=account;};
        window.__setStoryWorkspaceTestLanguage=language=>{forcedLanguage=language;instance.translate();};
        return instance;
      };
    }});
  });
  await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    const entry={method:req.method(),path:url.pathname+url.search,...(req.postDataBuffer()?{body:req.postData()}:{} )};requests.push(entry);
    if(entry.method==='GET'&&/^\/memory-stories(?:\?|$)/.test(entry.path)&&shelfMode){
      const status=shelfMode;shelfMode=null;entry.status=status;
      try{await route.fulfill({status,contentType:'application/json',body:JSON.stringify({detail:'synthetic shelf response'})});}catch(error){ignoreClosedRoute(error);}return;
    }
    if(denyPreview&&url.pathname==='/story-workspace/preview'){entry.status=403;await route.fulfill({status:403,contentType:'application/json',body:'{"detail":"synthetic revoked selection"}'});return;}
    if(req.method()==='POST'&&url.pathname==='/memory-stories'&&saveFailures.length){const status=saveFailures.shift();entry.status=status;await route.fulfill({status,contentType:'application/json',body:'{"detail":"synthetic uncommitted/rejected save"}'});return;}
    const headers=await req.allHeaders();delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']=new URL(req.frame().url()).origin===url.origin?'same-origin':'none';
    const result=await rpc({method:req.method(),path:entry.path,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    entry.status=result.status;
    if(stripEvidence&&url.pathname==='/story-workspace/preview'&&result.status===200){const fresh=JSON.parse(Buffer.from(result.body,'base64').toString());fresh.selection_revision='0'.repeat(64);for(const item of fresh.items)item.evidence=[];for(const chapter of fresh.chapters)chapter.evidence_ids=[];result.body=Buffer.from(JSON.stringify(fresh)).toString('base64');}
    if(entry.method==='GET'&&/^\/memory-stories(?:\?|$)/.test(entry.path)&&shelfHold){shelfHold=false;arriveShelf.resolve();await releaseShelf.promise;}
    if(entry.method==='POST'&&url.pathname==='/story-workspace/preview'&&previewHold){previewHold=false;arrivePreview.resolve();await releasePreview.promise;entry.heldSettled=true;}
    if(entry.method==='POST'&&url.pathname==='/memory-stories'){
      saveBodies.push(entry.body);
      const saved=JSON.parse(Buffer.from(result.body,'base64').toString());saveResponses.push(saved);
      if(firstSave){firstSave=false;try{await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'synthetic response lost after commit'})});}catch(error){ignoreClosedRoute(error);}return;}
    }
    const responseHeaders={...result.headers};delete responseHeaders['content-length'];delete responseHeaders['content-encoding'];
    try{await route.fulfill({status:result.status,headers:responseHeaders,body:Buffer.from(result.body,'base64')});}catch(error){ignoreClosedRoute(error);}
  });
  page=await context.newPage();page.on('pageerror',error=>errors.push(error.stack||error.message));
  const login=async(phone='+12025550100')=>{
    await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});
    await page.locator('#phone').fill(phone);await page.locator('#password').fill('Synthetic family passphrase!');
    await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  };
  await login();
  page.on('dialog',dialog=>void dialog.accept());
  await page.locator('#memory-guide').waitFor({state:'visible'});
  const body=page.locator('#story-chapter-editor .story-chapter-card textarea[maxlength="6000"]').first();
  const authored='河边的那天下午，Jane 讲了一个故事。<b>这是原话</b>\n还记得风的声音。';
  const title='还记得那阵风';
  await page.locator('#memory-guide').click();
  await page.locator('#story-selection input[value="101"]').check();
  await page.locator('#story-selection input[value="102"]').check();
  await page.locator('#story-guide-next').click();
  await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  await page.locator('#story-workspace-title').fill(title);await body.fill(authored);
  await page.locator('#story-workspace-title').dispatchEvent('compositionstart');
  assert.equal(await page.locator('#story-local-save').isDisabled(),true);
  await page.locator('#story-workspace-title').dispatchEvent('compositionend');
  await page.locator('#story-local-save').click();
  await page.waitForFunction(()=>/草稿已保存|draft saved/i.test(document.querySelector('#story-local-editor-status').textContent));
  assert.equal(saveBodies.length,0,'private draft save never publishes a story');
  await page.reload();await page.locator('#story-local-resume').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),false,'no automatic restore');
  assert.equal((await page.locator('#story-local-draft').textContent()).includes(authored),false,'shelf never previews private prose');
  const previousPreviews=count('POST',/^\/story-workspace\/preview(?:\?|$)/);
  await page.locator('#story-local-resume').click();await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  assert.equal(await body.inputValue(),authored);assert.equal(await page.locator('#story-workspace-title').inputValue(),title);
  assert.equal(count('POST',/^\/story-workspace\/preview(?:\?|$)/),previousPreviews+1,'resume obtains fresh whole-selection evidence');
  assert.equal(await page.locator('#story-save-memory').isDisabled(),true,'restored content requires renewed review');
  assert.equal(await page.locator('#story-local-reviewed').isChecked(),false);
  pass('Explicit encrypted draft survives reload with exact wording and fresh references');

  // The same browser slot cannot be restored into another account identity.
  await page.evaluate(()=>{window.__storyWorkspaceTest.clear();window.__setStoryWorkspaceTestAccount('other-account');window.__storyWorkspaceTest.setItems([]);});
  await page.waitForTimeout(100);
  assert.equal(await page.locator('#story-local-resume').isVisible(),false,'another account has no draft affordance');
  assert.equal(await body.count(),0,'scope teardown removes private prose');
  await page.reload();await page.locator('#story-local-resume').waitFor({state:'visible'});

  denyPreview=true;await page.locator('#story-local-resume').click();
  await waitForRecorded(item=>item.status===403&&item.path.startsWith('/story-workspace/preview'),'revoked preview');
  await page.locator('#story-local-draft').waitFor({state:'hidden'});
  assert.equal(await page.locator('#story-workspace').evaluate(node=>node.open),false,'revoked media cannot restore cached prose');
  denyPreview=false;await page.reload();await page.locator('#story-local-resume').waitFor({state:'visible'});
  pass('Account and revoked-selection guards preserve storage without revealing stale prose');
  stripEvidence=true;await page.locator('#story-local-resume').click();
  await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  assert.equal(await body.inputValue(),authored,'changed sources keep exact original wording');
  assert.equal(await page.locator('#story-chapter-editor .story-reference-list article').count(),0,'withdrawn references are not revived');
  assert.equal(await page.locator('#story-save-memory').isDisabled(),true);
  stripEvidence=false;await page.reload();await page.locator('#story-local-resume').waitFor({state:'visible'});
  pass('Changed evidence is rebuilt while wording survives and publication requires review');


  await page.locator('#story-local-resume').click();await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  const latestWords=authored+'\n保存草稿后又补充的一句话。';await body.fill(latestWords);
  assert.match(await page.locator('#story-local-editor-status').textContent(),/还有改动|Changes are not/);
  await page.locator('#story-local-reviewed').check();
  await page.locator('#story-guide-next').click();await page.locator('#story-workspace[data-guide-step="review"]').waitFor();
  await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>/尚未确认|not confirmed|could not finish|未能完成/i.test(document.querySelector('#story-workspace-status')?.textContent||''));
  assert.equal(saveBodies.length,1);
  const frozen=saveBodies[0];
  await page.reload();await page.locator('#story-local-resume').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-local-delete').isDisabled(),true,'uncertain recovery cannot be silently discarded');
  await page.locator('#story-local-resume').click();await page.locator('#story-workspace').waitFor({state:'visible'});
  assert.equal(saveBodies.length,1,'resume never submits an uncertain save automatically');
  assert.equal(await body.isDisabled(),true,'frozen save cannot be edited into another request');
  assert.equal(await body.inputValue(),latestWords,'durable pending journal keeps edits made after Save draft');
  // The guide normally reveals publication only on review. Recovery must expose retry immediately.
  await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>/已保存|saved/i.test(document.querySelector('#story-workspace-status')?.textContent||''));
  assert.equal(saveBodies.length,2);assert.equal(saveBodies[1],frozen,'recovered publication uses byte-identical body and mutation UUID');
  assert.equal(saveResponses[0].id,saveResponses[1].id,'server replay identifies the same story');
  await page.locator('#story-workspace-close').click();
  await page.reload();await page.locator('#saved-memory-list .saved-memory-card').first().waitFor();
  assert.equal(await page.locator('#story-local-resume').isVisible(),false,'confirmed publication clears matching recovery');
  pass('Lost publication response survives reload and retries the exact save without duplication');

  // New unrelated draft: explicit deletion only removes the local slot.
  await page.locator('#memory-guide').click();await page.locator('#story-selection input[value="101"]').check();
  await page.locator('#story-guide-next').click();await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  await body.fill('另一段还没有分享的回忆。');await page.locator('#story-local-save').click();
  await page.waitForFunction(()=>/草稿已保存|draft saved/i.test(document.querySelector('#story-local-editor-status').textContent));
  saveFailures=[503,409];
  await page.locator('#story-guide-next').click();await page.locator('#story-workspace[data-guide-step="review"]').waitFor();
  await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>/尚未确认|not confirmed|could not finish|未能完成/i.test(document.querySelector('#story-workspace-status')?.textContent||''));
  await page.reload();await page.locator('#story-local-resume').waitFor({state:'visible'});
  stripEvidence=true;await page.locator('#story-local-resume').click();await page.locator('#story-workspace').waitFor({state:'visible'});stripEvidence=false;
  await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>!document.querySelector('#story-local-save').disabled&&
    !document.querySelector('#story-local-review').hidden&&!document.querySelector('#story-local-reviewed').checked);
  const rejected=await page.evaluate(async()=>{
    const store=await window.PhotoHouseStoryDraftStore.create();
    try{return (await store.load(window.__storyWorkspaceTestScope())).payload;}finally{store.close();}
  });
  assert.equal(rejected.pending,null,'definitive rejection releases only the frozen request');
  assert.equal(rejected.selection_revision,'0'.repeat(64),'editable recovery keeps the fresh selection revision');
  assert.equal(await page.locator('#story-save-memory').isDisabled(),true,'definitive rejection requires fresh review');
  pass('A rejected recovered save retains fresh revision and requires renewed review');
  await page.locator('#story-workspace-close').click();
  await page.locator('#story-local-delete').click();await page.locator('#story-local-draft').waitFor({state:'hidden'});
  assert.equal(await page.locator('#saved-memory-list .saved-memory-card').count(),1);
  pass('Explicit deletion removes only the private draft and keeps the published story');

  // Render the restored-wording controls at narrow width in both languages.
  await page.locator('#memory-guide').click();await page.locator('#story-selection input[value="101"]').check();
  await page.locator('#story-guide-next').click();await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  await body.fill('稍后继续。');await page.setViewportSize({width:390,height:844});
  for(const language of ['zh','en']){
    await page.evaluate(language=>window.__setStoryWorkspaceTestLanguage(language),language);
    await page.evaluate(()=>{for(const node of document.querySelectorAll('#story-workspace *')){const size=parseFloat(getComputedStyle(node).fontSize);if(!node.dataset.draftScale){node.style.fontSize=(size*1.5)+'px';node.dataset.draftScale='1';}}});
    await page.locator('#story-local-save').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(artifacts,'story-private-draft-390-'+language+'.png')});
    const overflow=await page.locator('#story-workspace').evaluate(root=>{const right=root.getBoundingClientRect().right;return [...root.querySelectorAll('*')].filter(node=>node.getBoundingClientRect().right>right+1).map(node=>({id:node.id,tag:node.tagName,cls:node.className,width:node.getBoundingClientRect().width})).slice(0,12);});
    assert.deepEqual(overflow,[],'narrow dialog fits '+language);
    const dimensions=await page.locator('#story-workspace').evaluate(node=>({scroll:node.scrollWidth,client:node.clientWidth}));
    if(dimensions.scroll>dimensions.client)console.log('OVERFLOW',await page.locator('#story-workspace').evaluate(root=>[...root.querySelectorAll('*')].filter(node=>node.scrollWidth>node.clientWidth&&node.getClientRects().length).map(node=>({tag:node.tagName,id:node.id,cls:node.className,scroll:node.scrollWidth,client:node.clientWidth,width:node.getBoundingClientRect().width,overflow:getComputedStyle(node).overflowX})).slice(0,25)));
    assert(dimensions.scroll<=dimensions.client,'dialog scroll width '+language+' '+JSON.stringify(dimensions));
    assert(await page.locator('#story-local-save').evaluate(node=>node.getBoundingClientRect().height>=48),'touch target '+language);
    await page.screenshot({path:path.join(artifacts,'story-private-draft-390-'+language+'.png')});
  }
  assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
  pass('Chinese and English device-draft controls fit a narrow screen');
})().finally(async()=>{try{await context?.close();await browser?.close();}finally{bridge.stdin.end();bridge.kill();}});
const watchdog=setTimeout(()=>{console.error('FAIL story draft journey timed out');bridge.kill();process.exit(1);},150000);
testRun.then(()=>{clearTimeout(watchdog);},error=>{clearTimeout(watchdog);console.error(error);process.exitCode=1;});
