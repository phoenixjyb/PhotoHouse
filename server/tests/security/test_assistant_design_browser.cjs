/* Generated private-workspace design regression journey; no real media or model calls. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..'),artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-design-'));
fs.mkdirSync(artifacts,{recursive:true,mode:0o700});fs.chmodSync(artifacts,0o700);console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'assistant_pending_recovery_browser_bridge.py'),'--private-workspace'],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pending=new Map(),requests=[],blockedOrigins=[],pageErrors=[],checkpoints=[],syntheticMedia=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){readyResolve();return;}const call=pending.get(value.id);if(call){pending.delete(value.id);call.resolve(value);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Fixture bridge exited (${code})`));for(const call of pending.values())call.reject(new Error('Fixture bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
function pass(text){checkpoints.push(text);console.log('PASS '+text);}
function writeShot(name){const target=path.join(artifacts,name);return page.screenshot({path:target,fullPage:false}).then(()=>fs.chmodSync(target,0o600)).then(()=>target);}
let browser,context,page,overrideCapability,releaseCapability;
let capabilityCaptureCalls=0;
const capabilityPath='/assistant/v1/capabilities';

async function exerciseCapabilityRecovery(){
  const trigger=page.locator('#memory-assistant-link'),dialog=page.locator('#assistant-workspace-dialog');
  const status=dialog.locator('#assistant-status'),composer=dialog.locator('#assistant-text');
  const capabilityReads=()=>requests.filter(item=>item.path.startsWith(capabilityPath+'?'));
  const scriptReads=()=>requests.filter(item=>item.path.startsWith('/ui/assistant-private-workspace.js?')).length;
  const open=async()=>{await trigger.focus();await page.keyboard.press('Enter');await dialog.waitFor();};
  const close=async()=>{
    await page.keyboard.press('Escape');
    await dialog.waitFor({state:'hidden'});
    assert.equal(await trigger.evaluate(node=>node===document.activeElement),true);
  };
  const signIn=async(phone,asset)=>{
    await page.locator('#phone').fill(phone);
    await page.locator('#password').fill('Synthetic family passphrase!');
    await page.locator('#auth-submit').click();
    await page.locator(`#grid .asset[data-asset-id="${asset}"]`).waitFor();
  };
  const reloadGallery=async()=>{await page.goto('https://photohouse.test/ui');await page.locator('#grid .asset').first().waitFor();};
  const afterRender=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const waitForRetryNotice=async copy=>{
    await page.waitForFunction(expected=>{
      const notice=document.querySelector('#assistant-status'),pane=document.querySelector('#assistant-workspace-content');
      const text=notice.getBoundingClientRect(),bounds=pane.getBoundingClientRect();
      return notice.textContent===expected&&document.activeElement===notice&&
        text.top>=bounds.top-1&&text.bottom<=bounds.bottom+1;
    },copy);
    assert.equal(await status.getAttribute('role'),'status');
    assert.equal(await composer.isVisible(),false);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'recovery notice fits the viewport');
  };
  const recover=async()=>{
    const before=capabilityReads().length,modules=scriptReads(),start=performance.now();
    await open();
    await composer.waitFor();
    await page.waitForFunction(()=>document.activeElement?.id==='assistant-private-new');
    assert.equal(await status.textContent(),'');
    await afterRender();
    assert.equal(capabilityReads().length,before+1,'reopen issues one fresh capability GET');
    assert.equal(capabilityReads().at(-1).status,200);
    assert.equal(scriptReads(),modules,'reopen reuses the loaded Jude module');
    return Math.round(performance.now()-start);
  };

  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>{document.documentElement.style.fontSize='150%';});
  const zh='暂时无法打开小贾。请返回，再打开小贾重试。';
  for(const attempt of [1,2]){
    const before=capabilityReads().length;
    overrideCapability=async()=>({status:503});
    await open();
    await waitForRetryNotice(zh);
    await afterRender();
    assert.equal(capabilityReads().length,before+1,`503 attempt ${attempt} makes one capability GET`);
    if(attempt===1)await writeShot('assistant-capability-retry-zh-390-150.png');
    await close();
  }
  const zhReopenToComposerMs=await recover();
  await close();
  pass('Chinese keyboard recovery at 390px/150% reveals the notice; two 503s each require explicit reopen');

  await reloadGallery();
  await page.locator('#language').click();
  await page.waitForFunction(()=>document.documentElement.lang==='en'&&document.querySelector('#grid .asset'));
  overrideCapability=async()=>({abort:true});
  await open();
  await waitForRetryNotice('Jude couldn’t load. Return and reopen Jude to try again.');
  await writeShot('assistant-capability-retry-en-390.png');
  await close();
  const enReopenToComposerMs=await recover();
  await close();
  pass('English keyboard recovery retries a dropped capability request and clears the notice');

  for(const {response,copy} of [
    {response:{status:200,body:{version:1,enabled:false,text:false}},copy:/暂时不可用/},
    {response:{status:403},copy:/无法确认你的访问权限/},
  ]){
    await reloadGallery();
    const before=capabilityReads().length;
    overrideCapability=async()=>response;
    await open();
    await page.waitForFunction(pattern=>new RegExp(pattern).test(document.querySelector('#assistant-status').textContent),copy.source);
    await page.waitForFunction(()=>!document.querySelector('#assistant-voice-session-status').textContent.startsWith('正在检查'));
    await close();
    await open();
    await afterRender();
    assert.equal(capabilityReads().length,before+1,'a disabled or denied response is not retried on reopen');
    assert.match(await status.textContent(),copy);
    assert.equal(await composer.isVisible(),false);
    await close();
  }
  pass('A successful disabled response and permission denial keep their status and do not retry');

  await reloadGallery();
  const held=page.waitForRequest(request=>new URL(request.url()).pathname===capabilityPath);
  let finishOldResponse;
  const oldResponseFinished=new Promise(resolve=>{finishOldResponse=resolve;});
  const released=new Promise(resolve=>{releaseCapability=resolve;});
  overrideCapability=async()=>{await released;return {status:503,finished:finishOldResponse};};
  await open();
  await held;
  assert.match(capabilityReads().at(-1).path,/library_id=family-a$/);
  await dialog.locator('#assistant-workspace-lock').click();
  await page.locator('#auth').waitFor();
  await signIn('+12025550101','201');
  await open();
  await composer.waitFor();
  assert.match(capabilityReads().at(-1).path,/library_id=family-b$/);
  releaseCapability();
  releaseCapability=null;
  await oldResponseFinished;
  await afterRender();
  assert.equal(await status.textContent(),'','old account failure cannot replace current status');
  assert.equal(await composer.isVisible(),true);
  const readsInCurrentScope=capabilityReads().length;
  await close();
  await open();
  await afterRender();
  assert.equal(capabilityReads().length,readsInCurrentScope,'the old failure cannot mark the current scope for retry');
  await close();
  assert(!requests.some(item=>item.method!=='GET'&&item.path.startsWith('/assistant/')),
    'capability recovery does not create conversations, send turns, or start voice requests');
  assert.equal(capabilityCaptureCalls,0,'recovery never requests the microphone');
  pass('A delayed capability failure from the signed-out scope is discarded with no conversation, turn or capture');

  await page.locator('#logout').click();
  await page.locator('#auth').waitFor();
  await signIn('+12025550100','101');
  await page.setViewportSize({width:1280,height:900});
  return {zhReopenToComposerMs,enReopenToComposerMs};
}
(async()=>{
  await ready;browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},hasTouch:true,serviceWorkers:'block'});context.setDefaultTimeout(15000);
  await context.exposeBinding('__capabilityCaptureAttempt',()=>{capabilityCaptureCalls++;});
  await context.addInitScript(()=>{
    if(navigator.mediaDevices)navigator.mediaDevices.getUserMedia=async()=>{
      await window.__capabilityCaptureAttempt();
      throw new Error('The generated browser fixture does not capture audio');
    };
  });
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());if(url.origin!=='https://photohouse.test'){blockedOrigins.push(url.origin);await route.abort();return;}
    const headers={...await request.allHeaders()};delete headers['content-length'];headers['sec-fetch-site']=headers['sec-fetch-site']||'same-origin';
    const entry={method:request.method(),path:url.pathname+url.search,body:request.postData()||''};requests.push(entry);
    if(entry.method==='GET'&&url.pathname===capabilityPath&&overrideCapability){
      const respond=overrideCapability;overrideCapability=null;
      const fault=await respond();
      entry.status=fault.abort?'transport error':fault.status;
      try{
        if(fault.abort)await route.abort('failed');
        else await route.fulfill({status:fault.status,contentType:'application/json',headers:{'cache-control':'no-store'},body:JSON.stringify(fault.body||{})});
      }catch(error){
        if(!/closed|handled|canceled|cancelled|Invalid InterceptionId/.test(error.message))throw error;
      }finally{
        fault.finished?.();
      }
      return;
    }
    const response=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});entry.status=response.status;
    const responseHeaders={...response.headers};delete responseHeaders['content-length'];delete responseHeaders['content-encoding'];
    // The closed gallery fixture intentionally has metadata but no thumbnail files.
    if(entry.method==='GET'&&/^\/assets\/(101|102)\/thumbnail(?:\?|$)/.test(entry.path)&&response.status===404){
      syntheticMedia.push({path:entry.path,reason:'generated fixture metadata has no thumbnail file',replacement:'tiny generated SVG'});
      await route.fulfill({status:200,contentType:'image/svg+xml',headers:{'cache-control':'no-store'},body:'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 8 8"><rect width="8" height="8" fill="#e5e7eb"/></svg>'});return;
    }
    await route.fulfill({status:response.status,headers:responseHeaders,body:Buffer.from(response.body,'base64')});
  });
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');
  const checkPageReflow=async(label)=>{
    const shape=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,offenders:[...document.querySelectorAll('body *')].filter(node=>node.getClientRects().length&&getComputedStyle(node).visibility!=='hidden'&&node.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(node=>({id:node.id,tag:node.tagName,right:node.getBoundingClientRect().right}))}));
    assert(shape.scrollWidth<=shape.width,`${label}: page reflows without horizontal clipping ${JSON.stringify(shape)}`);return shape;
  };
  const inputBorder=await page.locator('#phone').evaluate(node=>{const colors=['borderTopColor','backgroundColor'].map(key=>getComputedStyle(node)[key].match(/[0-9.]+/g).slice(0,3).map(Number));const lum=rgb=>rgb.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);const [a,b]=colors.map(lum);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);});
  assert(inputBorder>=3,'sign-in field has a visible boundary against its surface');
  await page.setViewportSize({width:390,height:844});await writeShot('signed-out-phone-390.png');
  await page.setViewportSize({width:320,height:720});await page.evaluate(()=>document.documentElement.style.fontSize='200%');await checkPageReflow('signed out at 320 and 200% text');
  await page.evaluate(()=>document.documentElement.style.fontSize='');await page.setViewportSize({width:1280,height:900});
  await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
  await writeShot('library-desktop-1280.png');await page.setViewportSize({width:390,height:844});await writeShot('library-phone-390.png');
  await page.setViewportSize({width:320,height:720});await page.evaluate(()=>document.documentElement.style.fontSize='200%');await checkPageReflow('signed-in library at 320 and 200% text');
  await page.evaluate(()=>document.documentElement.style.fontSize='');await page.setViewportSize({width:1280,height:900});pass('Signed-out and signed-in library pages reflow at 320px with 200% root text');
  const capabilityRecovery=await exerciseCapabilityRecovery();
  const trigger=page.locator('#memory-assistant');await trigger.scrollIntoViewIfNeeded();await trigger.click();
  const dialog=page.locator('#assistant-workspace-dialog');await dialog.waitFor({state:'visible'});
  assert.equal(await dialog.evaluate(node=>node.open),true,'assistant opens as a native modal');
  assert.equal(await dialog.getAttribute('aria-labelledby'),'assistant-workspace-title');
  assert.equal(await dialog.locator('#assistant-workspace-title').evaluate(node=>node.tagName),'H1','modal title is the first-level heading');
  assert(await page.evaluate(()=>document.getElementById('assistant-workspace-dialog').contains(document.activeElement)),'opening moves keyboard focus into the modal');
  await page.keyboard.press('Tab');assert(await page.evaluate(()=>document.getElementById('assistant-workspace-dialog').contains(document.activeElement)),'Tab remains within the native modal');
  await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.getElementById('assistant-workspace-dialog').open);
  assert.equal(await page.evaluate(()=>document.activeElement.id),'memory-assistant','Escape returns focus to the existing opener');pass('Native dialog name, heading, contained keyboard focus, and Escape return focus');
  await trigger.click();await dialog.waitFor({state:'visible'});await page.locator('#assistant-private').waitFor({state:'visible'});
  const create=page.locator('#assistant-private-new');await create.waitFor({state:'visible'});await create.click();
  await page.waitForFunction(()=>!!document.getElementById('assistant-private-select')?.value);
  const thread=await page.locator('#assistant-private-select').inputValue();assert.match(thread,/^[0-9a-f-]{36}$/i,'fixture creates a scoped private thread');
  const turnPath=`/assistant/workspace/v1/threads/${thread}/turns`;
  for(const text of ['找照片','再找视频']){
    await page.locator('#assistant-text').fill(text);const response=page.waitForResponse(item=>item.request().method()==='POST'&&new URL(item.url()).pathname===turnPath);
    await page.locator('#assistant-send').click();assert.equal((await response).status(),200,`${text} completes in the private conversation`);
    await page.waitForFunction(()=>!document.getElementById('assistant-private-new').disabled);
  }
  const sent=requests.filter(item=>item.method==='POST'&&item.path===turnPath);assert.equal(sent.length,2,'journey submits exactly two explicit private follow-ups');assert.deepEqual(sent.map(item=>JSON.parse(item.body).text),['找照片','再找视频']);
  pass('One active private chat accepts two explicit typed follow-ups');
  const parseColor=value=>{const m=value.match(/rgba?\(([^)]+)\)/);if(!m)return null;const n=m[1].split(',').map(Number);return n.length<3?null:{r:n[0],g:n[1],b:n[2],a:n[3]??1};};
  const inspect=async(label,width,height,fontScale,screenshot)=>{
    await page.waitForFunction(()=>!document.getElementById('assistant-private-new').disabled&&!document.getElementById('assistant-form').hidden&&!document.getElementById('assistant-workspace-footer').hidden);
    await page.setViewportSize({width,height});await page.evaluate(scale=>{document.documentElement.style.fontSize=scale?`${scale}%`:'';},fontScale);
    const measurements=await page.evaluate(()=>{
      const dialog=document.getElementById('assistant-workspace-dialog'),footer=document.getElementById('assistant-workspace-footer'),rect=node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};
      const visible=node=>!!node.getClientRects().length&&getComputedStyle(node).visibility!=='hidden';
      const controls=[...dialog.querySelectorAll('button,summary,select,textarea,input:not([type=hidden]),[role=button]')].filter(node=>visible(node)&&!node.disabled&&!node.closest('[hidden]'));
      const textNodes=[...dialog.querySelectorAll('*')].filter(node=>visible(node)&&[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&child.textContent.trim()));
      const backgrounds=node=>{const chain=[];for(let el=node;el&&el!==dialog.parentElement;el=el.parentElement)chain.unshift(getComputedStyle(el).backgroundColor);let base={r:255,g:255,b:255};for(const value of chain){const m=value.match(/rgba?\(([^)]+)\)/);if(!m)continue;const n=m[1].split(',').map(Number),a=n[3]??1;base={r:n[0]*a+base.r*(1-a),g:n[1]*a+base.g*(1-a),b:n[2]*a+base.b*(1-a)};}return base;};
      const colorRows=textNodes.filter(node=>!node.closest(':disabled')).map(node=>({label:node.id||node.className||node.tagName,font:parseFloat(getComputedStyle(node).fontSize),weight:getComputedStyle(node).fontWeight,fg:getComputedStyle(node).color,bg:backgrounds(node)})).filter(row=>row.font<(row.weight==='bold'||Number(row.weight)>=700?18.67:24));
      const placeholder=document.querySelector('#assistant-text'),style=getComputedStyle(placeholder,'::placeholder');colorRows.push({label:'assistant-text::placeholder',font:parseFloat(getComputedStyle(placeholder).fontSize),weight:'400',fg:style.color,bg:{r:255,g:255,b:255}});
      return {width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,dialog:rect(dialog),footer:rect(footer),footerPaddingBottom:parseFloat(getComputedStyle(footer).paddingBottom),controls:controls.map(node=>({label:node.id||node.tagName,width:rect(node).width,height:rect(node).height})),colors:colorRows,composerBorder:getComputedStyle(document.querySelector('#assistant-form')).borderTopColor};
    });
    const lum=color=>{const c=[color.r,color.g,color.b].map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2];};
    const boundary=parseColor(measurements.composerBorder);assert(1.05/(lum(boundary)+.05)>=3,`${label}: composer boundary contrast is at least 3:1`);
    const failing=measurements.colors.filter(row=>{const fg=parseColor(row.fg);if(!fg)return false;const ratio=(Math.max(lum(fg),lum(row.bg))+.05)/(Math.min(lum(fg),lum(row.bg))+.05);row.ratio=Number(ratio.toFixed(2));return row.ratio<4.5;});
    assert(measurements.dialog.x>=-1&&measurements.dialog.y>=-1&&measurements.dialog.right<=width+1&&measurements.dialog.bottom<=height+1,`${label}: dialog remains inside viewport ${JSON.stringify(measurements.dialog)}`);
    assert(measurements.footer.y>=measurements.dialog.y&&measurements.footer.bottom<=measurements.dialog.bottom+1&&measurements.footerPaddingBottom>=12,`${label}: composer footer stays visible with viewport padding ${JSON.stringify(measurements.footer)}`);
    assert(measurements.scrollWidth<=width,`${label}: no page-level horizontal overflow`);
    const tooSmall=measurements.controls.filter(control=>control.width<44||control.height<44);assert.deepEqual(tooSmall,[],`${label}: enabled visible touch controls meet 44px target ${JSON.stringify(tooSmall)}`);
    assert.deepEqual(failing,[],`${label}: small text and placeholder contrast is at least 4.5:1 ${JSON.stringify(failing)}`);
    if(screenshot)await writeShot(screenshot);return measurements;
  };
  const resumeFixtureThread=async()=>{
    if(await page.locator('#assistant-private-select').inputValue()===thread)return;
    await page.locator('#assistant-private-management-toggle').click();
    await page.waitForFunction(id=>[...document.getElementById('assistant-private-select').options].some(option=>option.value===id),thread);
    const read=page.waitForResponse(response=>response.request().method()==='GET'&&new URL(response.url()).pathname===`/assistant/workspace/v1/threads/${thread}`);
    await page.locator('#assistant-private-select').selectOption(thread);assert.equal((await read).status(),200,'locale restore reads the current authorized thread');
    await page.waitForFunction(()=>!document.getElementById('assistant-private-new').disabled);
    if(await page.locator('#assistant-private-management').evaluate(node=>node.open))await page.locator('#assistant-private-management-toggle').click();
    assert.equal(requests.filter(item=>item.method==='POST'&&item.path===turnPath).length,2,'opening history does not replay a turn');
  };
  const english=page.locator('#language');await page.locator('#assistant-workspace-close').click();await english.click();await page.waitForFunction(()=>document.querySelector('#assistant-panel > summary')?.textContent==='Jude · PhotoHouse Assistant');await trigger.click();await dialog.waitFor({state:'visible'});assert.equal(await dialog.locator('#assistant-workspace-title').innerText(),'Jude · PhotoHouse Assistant','English locale is exercised');
  await resumeFixtureThread();const desktop=await inspect('English desktop 1280',1280,900,0,'assistant-design-en-desktop-1280.png');
  await page.locator('#assistant-workspace-close').click();await english.click();await page.waitForFunction(()=>document.querySelector('#assistant-panel > summary')?.textContent==='小贾 · 拾光助手');await trigger.click();await dialog.waitFor({state:'visible'});assert.equal(await dialog.locator('#assistant-workspace-title').innerText(),'小贾 · 拾光助手','Chinese locale is exercised');
  await resumeFixtureThread();const phone390=await inspect('Chinese phone 390',390,844,0,'assistant-design-zh-phone-390.png');
  const phone320=await inspect('Chinese phone 320',320,720,150,'assistant-design-zh-phone-320-text150.png');
  const phone200=await inspect('Chinese phone 320 at 200% text resize',320,720,200,'assistant-design-zh-phone-320-text200.png');
  // A generated paused-state styling fixture must still leave a usable
  // conversation at large text size; it does not start voice or a request.
  await page.locator('#assistant-text').fill('Generated paused-layout draft');
  const pausedStyle=await page.evaluate(()=>{
    const voice=document.getElementById('assistant-voice-session'),saved={hidden:voice.hidden,phase:voice.dataset.phase,buttons:[...voice.querySelectorAll('button')].map(button=>({id:button.id,hidden:button.hidden})),status:document.getElementById('assistant-voice-session-status').textContent};
    voice.hidden=false;voice.dataset.phase='paused';document.getElementById('assistant-voice-title').textContent='语音已暂停';document.getElementById('assistant-voice-mic-state').textContent='麦克风关闭';document.getElementById('assistant-voice-session-status').textContent='语音已暂停，可以继续输入。';document.getElementById('assistant-voice-start').hidden=true;
    document.getElementById('assistant-voice-pause').hidden=true;document.getElementById('assistant-voice-resume').hidden=false;document.getElementById('assistant-voice-end').hidden=false;return saved;
  });
  const pausedPaneHeight=await page.locator('#assistant-workspace-content').evaluate(node=>node.clientHeight);
  assert(pausedPaneHeight>=80,'paused voice at 200% text retains a usable conversation pane');
  // Enter the composer from an enabled header control. Refocusing an
  // already focused textarea after a synthetic layout change does not invoke
  // native focus scrolling, and is not a keyboard navigation action.
  await page.locator('#assistant-workspace-close').focus();assert.equal(await page.evaluate(()=>document.activeElement.id),'assistant-workspace-close');await page.locator('#assistant-text').focus();const pausedComposer=await page.locator('#assistant-text').evaluate(node=>{const r=node.getBoundingClientRect(),dialog=document.getElementById('assistant-workspace-dialog');return {top:r.top,bottom:r.bottom,viewport:innerHeight,focus:document.activeElement.id,scrollTop:dialog.scrollTop,scrollHeight:dialog.scrollHeight,clientHeight:dialog.clientHeight};});assert(pausedComposer.top>=0&&pausedComposer.bottom<=pausedComposer.viewport,`large-text paused composer remains keyboard reachable ${JSON.stringify(pausedComposer)}`);
  await page.locator('#assistant-send').focus();
  assert(await page.locator('#assistant-send').evaluate(node=>{const r=node.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}),'large-text paused Send action stays reachable by keyboard');
  await writeShot('assistant-design-paused-phone-text200.png');
  await page.locator('#assistant-text').fill('');
  await page.evaluate(saved=>{const voice=document.getElementById('assistant-voice-session');voice.hidden=saved.hidden;if(saved.phase===undefined)delete voice.dataset.phase;else voice.dataset.phase=saved.phase;for(const button of saved.buttons)document.getElementById(button.id).hidden=button.hidden;document.getElementById('assistant-voice-session-status').textContent=saved.status;document.getElementById('assistant-workspace-dialog').scrollTop=0;},pausedStyle);
  await page.emulateMedia({reducedMotion:'reduce',forcedColors:'active'});await page.locator('#assistant-workspace-close').focus();await page.keyboard.press('Tab');
  const focusStyle=await page.evaluate(()=>{const node=document.activeElement,style=getComputedStyle(node);return {tag:node.tagName,id:node.id,outlineStyle:style.outlineStyle,outlineWidth:parseFloat(style.outlineWidth),outlineColor:style.outlineColor};});
  assert.notEqual(focusStyle.outlineStyle,'none','forced-colors keeps a native visible keyboard focus outline');assert(focusStyle.outlineWidth>=2,'focus outline remains at least two CSS pixels');
  // Exercise the active decorative CSS state without requesting a microphone.
  const voiceStyleState=await page.locator('#assistant-voice-session').evaluate(node=>{const old={mic:node.dataset.micLive,phase:node.dataset.phase};node.dataset.micLive='true';node.dataset.phase='listening';return old;});
  const motion=await page.locator('.assistant-voice-orb span').first().evaluate(node=>getComputedStyle(node).animationName);assert.equal(motion,'none','reduced motion disables even the active decorative voice animation');
  await page.emulateMedia({reducedMotion:'no-preference',forcedColors:'none'});assert.equal(await page.locator('.assistant-voice-orb span').first().evaluate(node=>getComputedStyle(node).animationName),'jude-listening','decoration is opt-in only when reduced motion is not requested');
  await page.locator('#assistant-voice-session').evaluate((node,old)=>{for(const [key,value] of [['micLive',old.mic],['phase',old.phase]]){if(value===undefined)delete node.dataset[key];else node.dataset[key]=value;}},voiceStyleState);
  await page.emulateMedia({reducedMotion:'reduce',forcedColors:'active'});
  await writeShot('assistant-design-zh-phone-forced-colors.png');pass('Reduced-motion and forced-colors retain a visible keyboard focus indicator');
  assert.deepEqual(blockedOrigins,[],'every request stayed on the synthetic fixture origin');assert.deepEqual(pageErrors,[],'page has no uncaught errors');
  const evidence={checkpoints,desktop,phone390,phone320Text150:phone320,phone320Text200:phone200,pausedPaneHeight,pausedStateFixtureOnly:true,focusStyle,screenshots:['signed-out-phone-390.png','library-desktop-1280.png','library-phone-390.png','assistant-design-en-desktop-1280.png','assistant-design-zh-phone-390.png','assistant-design-zh-phone-320-text150.png','assistant-design-zh-phone-320-text200.png','assistant-design-zh-phone-forced-colors.png','assistant-design-paused-phone-text200.png'],syntheticBackend:true,syntheticMedia,blockedOrigins,pageErrors,requests:requests.map(({method,path,status})=>({method,path,status})),textResize:'root font-size 150% and 200%; no browser zoom or deviceScaleFactor',origin:'https://photohouse.test only'};
  evidence.capabilityRecovery=capabilityRecovery;
  evidence.screenshots.push('assistant-capability-retry-zh-390-150.png','assistant-capability-retry-en-390.png');
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify(evidence,null,2),{mode:0o600});fs.chmodSync(path.join(artifacts,'result.json'),0o600);
  console.log('Assistant design browser journey ready. Artifacts: '+artifacts);
})().catch(async error=>{console.error(error.stack||error);process.exitCode=1;try{await writeShot('failure.png');}catch{}}).finally(async()=>{releaseCapability?.();if(context)await context.unrouteAll({behavior:'ignoreErrors'});if(browser)await browser.close();try{bridge.stdin.end(JSON.stringify({command:'quit'})+'\n');await Promise.race([new Promise(resolve=>bridge.once('exit',resolve)),new Promise(resolve=>setTimeout(resolve,3000))]);if(bridge.exitCode===null)bridge.kill();}catch{bridge.kill();}});
