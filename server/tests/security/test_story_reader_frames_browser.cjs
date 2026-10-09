'use strict';
/* Real Web story workspace -> closed ASGI -> synthetic SQLite, with local media only. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-reader-frames-'));
fs.mkdirSync(artifacts,{recursive:true});
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pending=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const request=pending.get(result.id);if(request){pending.delete(result.id);request.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error('Bridge failed'));for(const item of pending.values())item.reject(new Error('Bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
let browser,ctx;const errors=[],external=[],requests=[],checks=[];
const pass=name=>{checks.push(name);console.log('PASS '+name);};
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  ctx=await browser.newContext({viewport:{width:1280,height:960},deviceScaleFactor:1.5,serviceWorkers:'block'});
  await ctx.addInitScript(()=>{let Constructor;Object.defineProperty(window,'PhotoHouseStoryWorkspace',{configurable:true,get:()=>Constructor,set:value=>{Constructor=config=>{let forcedLanguage=null;const originalScope=config.scope;const instance=value({...config,scope:()=>({...originalScope(),...(forcedLanguage?{language:forcedLanguage}:{})})});window.__setStoryWorkspaceTestLanguage=language=>{forcedLanguage=language;instance.translate();};window.__storyWorkspaceTest=instance;return instance;};}});});
  await ctx.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!=='https://photohouse.test'){external.push(url.origin);await route.abort();return;}
    requests.push({method:req.method(),path:url.pathname+url.search});
    const headers=await req.allHeaders();delete headers['content-length'];
    if(!headers['sec-fetch-site'])headers['sec-fetch-site']=new URL(req.frame().url()).origin===url.origin?'same-origin':'none';
    const result=await rpc({method:req.method(),path:url.pathname+url.search,headers,body:(req.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    const output={...result.headers};delete output['content-length'];delete output['content-encoding'];
    await route.fulfill({status:result.status,headers:output,body:Buffer.from(result.body,'base64')});
  });
  const page=await ctx.newPage();page.on('pageerror',error=>errors.push(error.message));
  async function login(){await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();}
  async function buildAndRead(ids){
    await page.evaluate(values=>window.__storyWorkspaceTest.open(values,'trip'),ids);
    await page.locator('#story-build').click();await page.locator('.story-chapter-card').first().waitFor();
    await page.locator('#story-preview').click();await page.locator('#story-reader').waitFor({state:'visible'});
    await page.locator('#story-reader-frames button').first().waitFor();
  }
  await login();
  await rpc({command:'mutate',scenario:'many-assets'});await rpc({command:'mutate',scenario:'related-day-seed'});
  const ids=[...Array.from({length:23},(_,index)=>String(1101+index)),'1129'];
  await buildAndRead(ids);
  assert.equal(await page.locator('#story-reader-frames button').count(),4,'real 24-frame outline keeps the four-per-chapter reader contract');
  assert.equal(await page.locator('#story-reader-chapters button').count(),6,'24 frames are arranged into six chapters');
  assert.equal(await page.locator('#story-reader-frames button[data-kind=video]').count(),0,'first chapter contains photos only in the synthetic ordering');
  const firstButton=page.locator('#story-reader-frames button').first();
  assert.equal(await firstButton.getAttribute('aria-label'),'照片 1 / 4');
  assert.equal(await page.locator('#story-reader-frame-status').textContent(),'当前画面：照片 1 / 4');
  assert(await page.locator('#story-reader-frames button').evaluateAll(nodes=>nodes.every(node=>node.getBoundingClientRect().width>=44&&node.getBoundingClientRect().height>=44)),'all frame controls meet the 44px target');
  await page.setViewportSize({width:260,height:563});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'reader page fits a 390px physical viewport at 150% effective zoom');
  assert(await page.locator('#story-reader').evaluate(element=>element.scrollWidth<=element.clientWidth),'reader fits its narrow effective viewport');
  const strip=page.locator('#story-reader-frames');
  await page.locator('#story-reader-chapters button').last().click();
  assert.equal(await page.locator('#story-reader-frames button[data-kind=video]').count(),1,'a later chapter exposes the video affordance');
  await strip.evaluate(node=>{node.scrollLeft=0;});
  await firstButton.focus();
  await page.locator('#story-reader').evaluate(node=>{if(node.scrollHeight>node.clientHeight)node.scrollTop=8;});
  const beforeScroll=await page.evaluate(()=>({x:scrollX,y:scrollY,readerTop:document.querySelector('#story-reader').scrollTop}));
  await page.keyboard.press('ArrowRight');await page.keyboard.press('ArrowRight');await page.keyboard.press('ArrowRight');
  const selected=page.locator('#story-reader-frames button[aria-pressed=true]');
  assert.equal(await selected.getAttribute('aria-label'),'视频 4 / 4','keyboard navigation reaches last frame and localizes its media type');
  assert.equal(await selected.evaluate(node=>document.activeElement===node),true,'explicit keyboard navigation keeps focus on the selected frame');
  assert(await strip.evaluate(node=>node.scrollLeft>0),'last frame is revealed by scrolling only the filmstrip');
  assert(await selected.evaluate(node=>{const host=document.querySelector('#story-reader-frames'),a=host.getBoundingClientRect(),b=node.getBoundingClientRect();return b.left>=a.left-1&&b.right<=a.right+1;}),'selected control is visible inside the filmstrip');
  assert.deepEqual(await page.evaluate(()=>({x:scrollX,y:scrollY,readerTop:document.querySelector('#story-reader').scrollTop})),beforeScroll,'frame navigation does not scroll the page or reader dialog');
  assert.equal(await page.locator('#story-reader-frame-status').textContent(),'当前画面：视频 4 / 4');
  const retiredVideo=await page.locator('#story-reader-stage .story-video-open').elementHandle();
  const retiredStageImage=await page.locator('#story-reader-stage img').elementHandle();
  await strip.evaluate(node=>{node.scrollLeft=0;});const beforeClickScroll=await page.evaluate(()=>({x:scrollX,y:scrollY,readerTop:document.querySelector('#story-reader').scrollTop}));
  await page.locator('#story-reader-frames button').nth(3).click();
  assert.equal(await page.locator('#story-reader-frames button[aria-pressed=true]').getAttribute('aria-label'),'视频 4 / 4','click selection reaches and retains the last frame');
  assert(await strip.evaluate(node=>node.scrollLeft>0),'click selection reveals the frame inside the filmstrip');
  assert.deepEqual(await page.evaluate(()=>({x:scrollX,y:scrollY,readerTop:document.querySelector('#story-reader').scrollTop})),beforeClickScroll,'click selection does not scroll the page or reader dialog');
  await page.screenshot({path:path.join(artifacts,'reader-filmstrip-390-150-zh.png')});
  const beforeLanguage=await page.evaluate(()=>({scrollLeft:document.querySelector('#story-reader-frames').scrollLeft,readerTop:document.querySelector('#story-reader').scrollTop,activeAsset:document.activeElement?.dataset.assetId}));
  await page.evaluate(()=>window.__setStoryWorkspaceTestLanguage('en'));
  assert.equal(await strip.getAttribute('aria-label'),'Frames in this chapter');
  assert.equal(await selected.getAttribute('aria-label'),'Video 4 of 4');
  assert.equal(await page.locator('#story-reader-frame-status').textContent(),'Current frame: Video 4 of 4');
  assert.deepEqual(await page.evaluate(()=>({scrollLeft:document.querySelector('#story-reader-frames').scrollLeft,readerTop:document.querySelector('#story-reader').scrollTop,activeAsset:document.activeElement?.dataset.assetId})),beforeLanguage,'language change preserves strip position, focus and reader scroll');
  await page.screenshot({path:path.join(artifacts,'reader-filmstrip-390-150-en.png')});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#story-reader-chapters button').last().click();
  const lastChapter=await page.locator('#story-reader-title').textContent();
  await page.locator('#story-reader-previous').click();
  assert.notEqual(await page.locator('#story-reader-title').textContent(),lastChapter,'previous chapter remains explicit and changes the reader chapter');
  assert.equal(await page.locator('#story-reader-frames button[aria-pressed=true]').getAttribute('aria-label'),'Photo 1 of 4');
  await page.locator('#story-reader-next').click();
  assert.equal(await page.locator('#story-reader-title').textContent(),lastChapter,'next chapter returns to the previously viewed final chapter');
  assert.equal(await page.locator('#story-reader-frames button[aria-pressed=true]').getAttribute('aria-label'),'Photo 1 of 4','chapter navigation starts at the chapter opening frame');
  pass('24 frames in six chapters use a localized, scrollable 44px filmstrip with explicit keyboard and chapter navigation');

  await page.locator('#story-reader-close').click();await page.locator('#story-workspace-close').click();
  await page.evaluate(()=>window.__setStoryWorkspaceTestLanguage('zh'));
  const staleFrame=await page.locator('#story-reader-frames button').nth(3).elementHandle();
  const staleChapter=await page.locator('#story-reader-chapters button').last().elementHandle();
  await buildAndRead(ids.slice(0,2));
  // Settle lazy thumbnails in the newly mounted editor and reader before
  // attributing later media requests to a retained detached control.
  await page.locator('#story-workspace img,#story-reader img').evaluateAll(images=>images.forEach(image=>{image.loading='eager';}));
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('#story-workspace img,#story-reader img')).every(image=>image.complete),null,{timeout:10000});
  const mediaRequestList=()=>requests.filter(request=>/^\/assets\/\d+\/(?:thumbnail|display|playback|media)(?:\?|$)/.test(request.path)).map(request=>`${request.method} ${request.path}`);
  const stateBeforeStaleClick=await page.evaluate(()=>({title:document.querySelector('#story-reader-title').textContent,frame:document.querySelector('#story-reader-frames [aria-pressed=true]')?.dataset.assetId,chapter:document.querySelector('#story-reader-chapters [aria-current=step]')?.textContent,frameCount:document.querySelectorAll('#story-reader-frames button').length}));
  const mediaBeforeStaleClick=mediaRequestList();
  await staleFrame.evaluate(button=>button.click());await staleChapter.evaluate(button=>button.click());await page.waitForTimeout(50);
  assert.deepEqual(await page.evaluate(()=>({title:document.querySelector('#story-reader-title').textContent,frame:document.querySelector('#story-reader-frames [aria-pressed=true]')?.dataset.assetId,chapter:document.querySelector('#story-reader-chapters [aria-current=step]')?.textContent,frameCount:document.querySelectorAll('#story-reader-frames button').length})),stateBeforeStaleClick,'detached frame/chapter callbacks cannot mutate the newly opened reader');
  assert.deepEqual(mediaRequestList(),mediaBeforeStaleClick,'detached reader controls issue no new media requests');
  const currentStage=await page.locator('#story-reader-stage').innerHTML();
  await retiredStageImage.evaluate(image=>{image.dispatchEvent(new Event('error'));image.dispatchEvent(new Event('error'));});
  assert.equal(await page.locator('#story-reader-stage').innerHTML(),currentStage,'late error callbacks from a retired preview cannot alter the current reader');
  await retiredVideo.evaluate(button=>button.click());
  assert.equal(await page.locator('#story-reader').evaluate(dialog=>dialog.open),true,'a retired video control cannot close the current story');
  assert.deepEqual(mediaRequestList(),mediaBeforeStaleClick,'retired preview/video callbacks issue no new media requests');
  await retiredStageImage.dispose();await retiredVideo.dispose();
  await staleFrame.dispose();await staleChapter.dispose();
  pass('Detached frame/chapter/video controls and retired preview errors are inert after another story opens');
  await page.locator('#story-reader-close').click();await page.locator('#story-workspace-close').click();
  for(const size of [1,2]){
    await buildAndRead(ids.slice(0,size));
    assert.equal(await page.locator('#story-reader-frames button').count(),size,`${size}-frame chapter renders only its available controls`);
    assert.equal(await page.locator('#story-reader-frames button[aria-pressed=true]').getAttribute('aria-label'),`照片 1 / ${size}`);
    await page.locator('#story-reader-close').click();await page.locator('#story-workspace-close').click();
  }
  pass('One-frame and two-frame chapter strips render within the existing API contract');

  const brokenId='1125';
  await ctx.route(`https://photohouse.test/assets/${brokenId}/thumbnail*`,route=>route.fulfill({status:503,body:'unavailable'}));
  await buildAndRead(['1124','1125','1126','1127']);
  const broken=page.locator(`#story-reader-frames button[data-asset-id="${brokenId}"]`);
  await page.waitForFunction(id=>document.querySelector(`#story-reader-frames button[data-asset-id="${id}"] .story-reader-frame-fallback`),brokenId);
  await broken.click();assert.equal(await broken.getAttribute('aria-pressed'),'true','failed thumbnail leaves its frame control selectable');
  pass('Unavailable thumbnail falls back visually while keeping selection available');

  await page.locator('#story-reader-close').click();await page.locator('#story-workspace-close').click();
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  assert.equal(await page.locator('#story-reader-frames').evaluate(node=>node.children.length),0,'logout clears reader frame controls');
  assert.equal(await page.locator('#story-reader-frame-status').count(),0,'logout clears the live frame status');
  assert.equal(requests.filter(request=>/\/memory-stories(?:\/|\?|$)/.test(request.path)&&['POST','PUT','DELETE'].includes(request.method)).length,0,'reading/navigation created no saved story or mutation');
  assert.deepEqual(external,[],'browser made no external requests');assert.deepEqual(errors,[],'browser emitted no page errors');
  pass('Logout clears reader state; no external requests, saved-story writes or page errors');
  await browser.close();bridge.kill();
  console.log(JSON.stringify({checks,artifacts,requests:requests.length,externalRequests:external.length,pageErrors:errors.length}));
})().catch(async error=>{console.error(error);try{await browser?.close();}catch{}bridge.kill();process.exitCode=1;});
