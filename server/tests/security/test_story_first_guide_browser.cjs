'use strict';
/* First-story guide: real Web UI and closed ASGI over synthetic SQLite. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-first-story-guide-'));
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
let firstSave=true,saveBodies=[],saveResponses=[];
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
        window.__storyWorkspaceTest=instance;
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
    const headers=await req.allHeaders();delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']=new URL(req.frame().url()).origin===url.origin?'same-origin':'none';
    const result=await rpc({method:req.method(),path:entry.path,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    entry.status=result.status;
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
  // Arm before login: the first authenticated shelf request is the readiness gate.
  shelfHold=true;arriveShelf=deferred();releaseShelf=deferred();
  await login();

  // A pending, failed, or denied saved-story shelf cannot expose first-story guidance.
  await arriveShelf.promise;assert.equal(await page.locator('#memory-guide').isVisible().catch(()=>false),false,'guide stays absent while the saved-story capability response is pending');
  releaseShelf.resolve();await page.locator('#memory-guide').waitFor({state:'visible'});assert.equal(await page.locator('#memory-guide').isEnabled(),true);
  assert.equal(await page.locator('.saved-memory-card').count(),0,'the first-story guide is shown for an empty shelf');
  assert.equal((await page.locator('#saved-memory-status').textContent()).trim().length>0,true,'empty shelf guidance follows a completed shelf load');
  pass('First-story guidance appears after a successful can_create shelf response');
  for(const status of [503,403]){
    shelfMode=status;await page.reload();
    await waitForShelfFailure(status);
    assert.equal(await page.locator('#memory-guide').isVisible().catch(()=>false),false,`${status} shelf response does not advertise first-story guidance`);
  }
  await page.reload();await page.locator('#grid .asset').first().waitFor();await page.locator('#memory-guide').waitFor({state:'visible'});
  await page.screenshot({path:path.join(artifacts,'first-story-guide-home-1200-zh.png'),fullPage:true});

  // Hold a real preview response across scope teardown; its completion must be stale.
  await page.locator('#memory-guide').click();await page.locator('#story-workspace[data-guide-step="frames"]').waitFor();
  assert.equal(await page.locator('#story-selection input:checked').count(),0,'guided flow starts with no selected frames');
  await page.locator('#story-selection input[value="101"]').check();await page.locator('#story-selection input[value="102"]').check();
  previewHold=true;arrivePreview=deferred();releasePreview=deferred();await page.locator('#story-guide-next').click();await arrivePreview.promise;
  await page.evaluate(()=>{window.__storyWorkspaceTest.clear();window.__setStoryWorkspaceTestAccount('stale-account');});
  assert.equal(await page.locator('#story-workspace').evaluate(dialog=>dialog.open),false,'scope clear closes the first guide before another can start');
  releasePreview.resolve();await waitForRecorded(item=>item.heldSettled===true,'held preview response to settle');await page.waitForTimeout(50);
  assert.equal(await page.locator('#story-chapter-editor .story-chapter-card').count(),0,'a preview completing after scope clear cannot mount stale chapters');
  assert.equal(await page.locator('#story-workspace[data-guide-step="words"]').count(),0,'a stale preview cannot advance the guide');
  pass('A held preview is ignored after clearing private scope');

  // Begin a fresh guide and complete the first-story draft in the real app.
  await page.reload();await page.locator('#grid .asset').first().waitFor();await page.locator('#memory-guide').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-workspace').evaluate(dialog=>dialog.open),false,'the new home starts with the guide closed');
  const guide=page.locator('#story-workspace'),ids=['102','101'];
  await page.locator('#memory-guide').click();await page.locator('#story-workspace[data-guide-step="frames"]').waitFor();
  assert.equal(await page.locator('#story-guide-heading').isVisible(),true,'guided dialog has its own heading');
  assert.equal(await page.locator('#story-guide-progress [aria-current="step"]').count(),1,'progress marks exactly one current step');
  assert.equal(await page.locator('#story-selection input:checked').count(),0);
  await page.locator('#story-selection input[value="101"]').check();await page.locator('#story-selection input[value="102"]').check();
  await page.screenshot({path:path.join(artifacts,'first-story-guide-frames-1200-zh.png')});
  const applyGuideTextScale=scale=>page.evaluate(scale=>{
    const previous=window.__guideFontInline||new Map();for(const [node,value] of previous)if(node.isConnected)node.style.fontSize=value;
    window.__guideFontInline=new Map();if(scale===1)return;
    const snapshot=[document.documentElement,...document.querySelectorAll('*')].map(node=>({node,computed:getComputedStyle(node).fontSize,inline:node.style.fontSize}));
    for(const item of snapshot){window.__guideFontInline.set(item.node,item.inline);const pixels=parseFloat(item.computed);if(Number.isFinite(pixels))item.node.style.fontSize=`${pixels*scale}px`;}
  },scale);
  const assertGuideFits=async label=>{
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${label}: page has no horizontal overflow`);
    assert(await guide.evaluate(node=>node.scrollWidth<=node.clientWidth),`${label}: dialog has no horizontal overflow`);
    const visibleButtons=await page.locator('#story-guide-next,#story-guide-back').evaluateAll(nodes=>nodes.filter(node=>node.getClientRects().length>0).map(node=>({width:node.getBoundingClientRect().width,height:node.getBoundingClientRect().height})));
    assert(visibleButtons.length>0,`${label}: a guide navigation button is visible`);
    assert(visibleButtons.every(button=>button.width>=48&&button.height>=48),`${label}: visible guide navigation buttons meet the 48px target`);
  };
  await page.setViewportSize({width:390,height:844});await applyGuideTextScale(1.5);await assertGuideFits('Chinese frame step at 390px and 150% text');
  await page.screenshot({path:path.join(artifacts,'first-story-guide-frames-390-150-zh.png')});
  await page.evaluate(()=>window.__setStoryWorkspaceTestLanguage('en'));await applyGuideTextScale(1.5);await assertGuideFits('English frame step at 390px and 150% text');
  await page.screenshot({path:path.join(artifacts,'first-story-guide-frames-390-150-en.png')});
  await page.setViewportSize({width:320,height:720});await applyGuideTextScale(1.5);await assertGuideFits('English frame step at 320px and 150% text');
  await page.screenshot({path:path.join(artifacts,'first-story-guide-frames-320-en.png')});
  await page.setViewportSize({width:1200,height:900});await applyGuideTextScale(1);await page.evaluate(()=>window.__setStoryWorkspaceTestLanguage('zh'));

  const previewsBefore=count('POST',/^\/story-workspace\/preview(?:\?|$)/),writesBefore=count('POST',/^\/memory-stories(?:\?|$)/);
  await page.locator('#story-guide-next').focus();await page.keyboard.press('Enter');await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  assert.equal(await page.locator('#story-guide-progress [aria-current="step"]').count(),1,'word step remains identified in progress');
  await page.locator('#story-chapter-editor .story-chapter-card').first().waitFor();
  assert.equal(count('POST',/^\/story-workspace\/preview(?:\?|$)/),previewsBefore+1,'the first Next makes one existing outline request');
  const outline=JSON.parse(requests.filter(item=>item.method==='POST'&&/^\/story-workspace\/preview(?:\?|$)/.test(item.path)).at(-1).body);
  assert.equal(outline.asset_ids,ids.join(','),'outline receives only the explicitly selected asset IDs');
  assert((await page.locator('#story-chapter-editor .story-chapter-card textarea[maxlength="6000"]').evaluateAll(nodes=>nodes.map(node=>node.value))).every(value=>value===''),'guided chapter editors start blank instead of keeping instructional scaffold text');
  const outlineCount=count('POST',/^\/story-workspace\/preview(?:\?|$)/);
  await page.locator('#story-guide-next').click();await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  assert.equal(await page.locator('#story-guide-status').isVisible(),true,'empty wording keeps a visible guide prompt');
  assert.match(await page.locator('#story-guide-status').textContent(),/一句|回忆|sentence|memory/i,'the guide requests at least one remembered sentence');
  assert.equal(count('POST',/^\/story-workspace\/preview(?:\?|$)/),outlineCount,'an empty outline makes no second preview request');
  assert.equal(await page.locator('#story-workspace').getAttribute('data-guide-step'),'words','an empty outline cannot advance to review');
  await page.locator('#story-workspace-theme').selectOption('trip');
  await page.locator('#story-workspace[data-guide-step="frames"]').waitFor();
  assert.equal(await page.locator('#story-guide-next').isEnabled(),true,'changing the theme returns to a usable frame step');
  await page.locator('#story-guide-next').click();await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  assert.equal(await page.locator('#story-workspace-theme').inputValue(),'trip','new outline uses the explicitly chosen theme');
  const authored='家人留下了字面文本 <script>不要执行</script> & 永远记得。',manualTitle='第一次家庭故事';
  await page.locator('#story-workspace-title').fill(manualTitle);
  await page.locator('#story-chapter-editor .story-chapter-card textarea[maxlength="6000"]').first().fill(authored);
  await page.locator('#story-workspace-title').dispatchEvent('compositionstart');
  for(const id of ['story-guide-next','story-guide-back','story-guide-advanced'])assert.equal(await page.locator('#'+id).isDisabled(),true,'IME composition fences '+id);
  await page.locator('#story-guide-back').evaluate(button=>button.dispatchEvent(new MouseEvent('click',{bubbles:true})));
  assert.equal(await guide.getAttribute('data-guide-step'),'words','synthetic Back cannot abandon IME composition');
  await page.locator('#story-workspace-title').dispatchEvent('compositionend');
  const previewCountAfterOutline=count('POST',/^\/story-workspace\/preview(?:\?|$)/);
  await page.locator('#story-guide-back').click();await page.locator('#story-workspace[data-guide-step="frames"]').waitFor();
  assert.deepEqual(await page.locator('#story-selection input:checked').evaluateAll(nodes=>nodes.map(node=>node.value)),ids,'Back preserves frame selection');
  await page.locator('#story-guide-next').click();await page.locator('#story-workspace[data-guide-step="words"]').waitFor();
  assert.equal(await page.locator('#story-workspace-title').inputValue(),manualTitle,'Back preserves the manual title');
  assert.equal(await page.locator('#story-chapter-editor .story-chapter-card textarea[maxlength="6000"]').first().inputValue(),authored,'Back preserves exact chapter text');
  assert.equal(count('POST',/^\/story-workspace\/preview(?:\?|$)/),previewCountAfterOutline,'returning to words does not request another outline');
  assert.equal(count('POST',/^\/memory-stories(?:\?|$)/),writesBefore,'outline and Back do not save a story');
  assert.equal(await page.locator('#story-save-memory').isVisible(),false,'Save is hidden before review');
  await page.setViewportSize({width:390,height:844});await applyGuideTextScale(1.5);await assertGuideFits('word step at 390px and 150% text');
  await page.screenshot({path:path.join(artifacts,'first-story-guide-words-390-150-zh.png')});
  await applyGuideTextScale(1);await page.screenshot({path:path.join(artifacts,'first-story-guide-words-390-zh.png')});
  await page.setViewportSize({width:1200,height:900});await applyGuideTextScale(1);
  await page.locator('#story-workspace-title').focus();await page.keyboard.press('Enter');await page.locator('#story-workspace[data-guide-step="review"]').waitFor();
  assert.equal(await page.locator('#story-guide-progress [aria-current="step"]').count(),1,'review step remains identified in progress');
  const review=page.locator('#story-guide-review');await review.waitFor({state:'visible'});
  assert.equal(await page.locator('#story-guide-status').textContent(),'','the old empty-wording warning is cleared after valid progression');
  assert.equal((await review.textContent()).includes(authored),true,'review presents the exact authored text');
  assert.equal(await review.locator('script').count(),0,'authored markup is shown as text, not inserted as a live element');
  assert.equal(await page.locator('#story-save-memory').isVisible(),true,'explicit Save appears only on review');
  assert.equal(count('POST',/^\/memory-stories(?:\?|$)/),writesBefore,'review performs no story write');
  await page.setViewportSize({width:390,height:844});await applyGuideTextScale(1.5);await assertGuideFits('review step at 390px and 150% text');
  await page.screenshot({path:path.join(artifacts,'first-story-guide-review-390-150-zh.png')});
  await applyGuideTextScale(1);await page.screenshot({path:path.join(artifacts,'first-story-guide-review-390-zh.png')});
  await page.setViewportSize({width:1200,height:900});await applyGuideTextScale(1);
  await page.locator('#story-preview').click();await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-reader-text').textContent(),authored,'actual reader preview renders the exact user text');
  await page.locator('#story-reader-close').click();await page.locator('#story-workspace[data-guide-step="review"]').waitFor();
  assert.equal(count('POST',/^\/memory-stories(?:\?|$)/),writesBefore,'preview performs no story write');
  pass('Outline, chapter edit, Back, safe review and Reader preview keep saving explicit');

  await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>/尚未确认|not confirmed|could not finish|未能完成/i.test(document.querySelector('#story-workspace-status')?.textContent||''));
  assert.equal(saveBodies.length,1,'first save reached the real API and committed once before its response was replaced');
  assert.equal(saveResponses[0]?.saved,true,'the synthetic ASGI save committed a saved story');
  const firstBody=JSON.parse(saveBodies[0]);assert.equal(firstBody.title,manualTitle);assert.equal(JSON.parse(firstBody.chapters)[0].narration,authored);
  await page.locator('#story-save-memory').click();
  await page.waitForFunction(()=>/已保存到|Saved in this library|latest version is now open/i.test(document.querySelector('#story-workspace-status')?.textContent||''));
  assert.equal(saveBodies.length,2,'retry reached the same save endpoint exactly once more');
  assert.equal(saveBodies[1],saveBodies[0],'uncertain retry is byte-identical, including mutation ID');
  assert.equal(saveResponses[1]?.id,saveResponses[0]?.id,'idempotent retry returns the story committed by the first request');
  assert.equal(JSON.parse(saveBodies[1]).mutation_id,firstBody.mutation_id,'retry retains the original mutation ID');
  assert.equal(await guide.getAttribute('data-guide-step'),null,'successful save ends the guided step state');
  assert.equal(await page.locator('#story-workspace').isVisible(),true,'successful guide save leaves the normal editor open');
  pass('A lost save response retries the same committed story and returns to the normal editor');

  await page.locator('#story-workspace-close').click();await guide.waitFor({state:'hidden'});
  const savedCard=page.locator('.saved-memory-card').filter({hasText:manualTitle});
  await savedCard.waitFor();await savedCard.locator('.saved-memory-cover').click();await page.locator('#story-reader').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-reader-text').textContent(),authored,'reopening the saved synthetic story keeps the exact authored text');
  await page.locator('#story-reader-close').click();await context.clearCookies();
  const viewerShelf=page.waitForResponse(response=>new URL(response.url()).pathname==='/memory-stories'&&response.status()===200);
  await login('+12025550102');await viewerShelf;
  await page.waitForFunction(()=>document.querySelector('#saved-memory-refresh')?.disabled===false);
  assert.equal(await page.locator('#memory-guide').isVisible(),false,'a real viewer account cannot create stories');
  assert.equal(await page.locator('.story-first-guide-empty').count(),0,'a real viewer is not offered first-story guidance');
  pass('The actual viewer role does not expose a creation guide');
  assert.equal(external.length,0,`browser attempted external origins: ${JSON.stringify(external)}`);
  assert.deepEqual(errors,[],`page errors: ${JSON.stringify(errors)}`);
  pass('Saved story reopens with the authored chapter intact and no external browser traffic');
})();
let watchdog;
Promise.race([testRun,new Promise((_,reject)=>{watchdog=setTimeout(()=>reject(new Error('Browser guide test exceeded 120 seconds')),120000);})])
  .catch(async error=>{console.error(error.stack||error);console.error(JSON.stringify({errors,shelves:requests.filter(item=>item.path.startsWith('/memory-stories')).map(({method,path,status})=>({method,path,status}))}));if(page&&!page.isClosed()){console.error(JSON.stringify(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('*')].filter(n=>n.getClientRects().length&&n.getBoundingClientRect().right>innerWidth+1).slice(0,20).map(n=>({tag:n.tagName,id:n.id,classes:n.className,width:n.getBoundingClientRect().width,right:n.getBoundingClientRect().right}))})).catch(()=>({}))));await page.screenshot({path:path.join(artifacts,'failure.png')}).catch(()=>{});}process.exitCode=1;})
  .finally(async()=>{clearTimeout(watchdog);if(browser)await browser.close();if(bridge&&bridge.exitCode===null){bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.kill();}});
