/* Search-v2 user journey against generated media, identities and private graph. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-workspace-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'../.venv/bin/python'),[path.join(__dirname,'assistant_workspace_browser_bridge.py')],{cwd:root,env:{...process.env,PH_SEARCH_FIXTURE:'1'},stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pendingRpc=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){readyResolve();return;}const call=pendingRpc.get(result.id);if(call){pendingRpc.delete(result.id);call.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Browser bridge exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Browser bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const browserRequests=[],pageErrors=[],checkpoints=[],blockedOrigins=[],timings=[];
let loseNextTurn=false,loseNextTurnBeforeServer=false,loseNextCreationBeforeServer=false,holdNextTurn=null,releaseHeldTurn=null;
function gateTurn(){let arrive,release;const seen=new Promise(resolve=>{arrive=resolve;});const released=new Promise(resolve=>{release=resolve;});releaseHeldTurn=release;holdNextTurn={arrive,released};return {seen,release:()=>{releaseHeldTurn=null;release();}};}
function checkpoint(text){checkpoints.push(text);console.log('PASS '+text);}
function body(response){return JSON.parse(Buffer.from(response.body,'base64').toString());}
let browser,context,phoneContext,page;
async function installSyntheticTransport(targetContext){
  await targetContext.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){blockedOrigins.push(url.origin);await route.abort();return;}
    const entry={method:request.method(),path:url.pathname+url.search,headers:await request.allHeaders(),body:request.postData()||'',serverReached:false};browserRequests.push(entry);
    if(entry.method==='POST'&&url.pathname==='/assistant/workspace/v1/threads'&&loseNextCreationBeforeServer){
      loseNextCreationBeforeServer=false;entry.droppedBeforeServer=true;await route.abort('failed');return;
    }
    if(entry.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&loseNextTurnBeforeServer){
      loseNextTurnBeforeServer=false;entry.droppedBeforeServer=true;await route.abort('failed');return;
    }
    const headers={...entry.headers};delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    entry.serverReached=true;
    const response=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    entry.status=response.status;
    try{entry.response=body(response);}catch{}
    if(entry.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&holdNextTurn){
      const gate=holdNextTurn;holdNextTurn=null;gate.arrive();await gate.released;
    }
    if(entry.method==='POST'&&/^\/assistant\/workspace\/v1\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&loseNextTurn){
      loseNextTurn=false;await route.abort('failed');return;
    }
    const outputHeaders={...response.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try{await route.fulfill({status:response.status,headers:outputHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  await targetContext.addInitScript(()=>{
    window.__phSpeechCalls=0;
    try{Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak(){window.__phSpeechCalls++;},cancel(){},get speaking(){return false;}}});}catch{}
  });
}
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});context.setDefaultTimeout(15000);
  await installSyntheticTransport(context);
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');
  await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();
  await page.locator('#grid .asset').first().waitFor();
  if(!await page.locator('#assistant-panel').evaluate(el=>el.open))await page.locator('#assistant-panel > summary').click();
  await page.locator('#assistant-search-perspective').waitFor({state:'visible'});
  assert.match(await page.locator('#assistant-search-perspective').innerText(),/示例儿童/);
  await page.locator('#assistant-private-new').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-private-select')?.value&&!document.querySelector('#assistant-private-new').disabled);
  const turns=()=>browserRequests.filter(x=>x.method==='POST'&&/\/threads\/[0-9a-f-]+\/turns$/.test(new URL(x.path,'https://photohouse.test').pathname));
  const submit=async()=>{
    const n=turns().length;
    const response=page.waitForResponse(r=>r.request().method()==='POST'&&/\/threads\/[0-9a-f-]+\/turns$/.test(new URL(r.url()).pathname));response.catch(()=>{});
    const start=performance.now();await page.locator('#assistant-send').click();await response;
    await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
    const elapsed=performance.now()-start;
    assert.equal(turns().length,n+1);const entry=turns().at(-1);assert.equal(entry.status,200,JSON.stringify(entry.response));assert.equal(entry.headers['x-photohouse-search-version'],'2');
    timings.push({kind:entry.response.result.kind,elapsed_ms:Math.round(elapsed),turn_posts:turns().length-n});return entry.response;
  };
  const send=async text=>{
    await page.locator('#assistant-text').fill(text);
    return submit();
  };
  const result=await send('找示例儿童和妈妈在海边的照片');
  assert.equal(result.result.version,2);assert.deepEqual(result.result.filters.people,{ids:['301','302'],match:'all'});
  assert.deepEqual(result.result.items.map(x=>x.id),['101','102']);
  assert.match(result.result.reply,/已确认的标注/);assert.match(result.result.reply,/同一项/);
  await page.waitForFunction(value=>document.querySelector('#assistant-reply')?.textContent===value,result.result.reply);
  await page.locator('#assistant-reply').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'people-scope-desktop-zh.png'),fullPage:false});
  await page.locator('#assistant-search-summary').waitFor({state:'visible'});
  const summary=await page.locator('#assistant-search-summary').innerText();
  assert.match(summary,/示例儿童/);assert.match(summary,/示例成人/);assert.match(summary,/海边/);assert.match(summary,/同时|全部|所有/);
  assert.equal(await page.locator('.assistant-match-reasons').count(),2);
  for(const text of await page.locator('.assistant-match-reasons').allTextContents()){assert.match(text,/示例儿童/);assert.match(text,/示例成人/);}
  assert.match(await page.locator('#assistant-results').innerText(),/AI|生成/);
  assert.match(await page.locator('#assistant-results').innerText(),/回忆/);
  assert.doesNotMatch(await page.locator('#assistant-results').innerText(),/Synthetic original wording|source_id|11111111/);
  checkpoint('Chinese joint person/relative/text search resolves both reviewed people and shows private perspective, conditions and source labels');
  await page.screenshot({path:path.join(artifacts,'search-desktop-zh.png'),fullPage:false});
  await page.locator('#assistant-results').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'search-desktop-evidence-zh.png'),fullPage:false});
  const refined=await send('只看2026年的');
  assert.deepEqual(refined.result.filters.people,{ids:['301','302'],match:'all'});assert.equal(refined.result.filters.text,'海边');
  assert.deepEqual(refined.result.items.map(x=>x.id),['101','102']);assert.match(await page.locator('#assistant-search-summary').innerText(),/2026-01-01|2026-12-31/);
  checkpoint('Date refinement preserves both-person and text constraints and labels the capture-date basis');
  const opened=await send('打开第二个');assert.deepEqual(opened.result.effect,{type:'open_asset',asset_id:'102'});
  await page.locator('#viewer').waitFor({state:'visible'});await page.locator('#close-viewer').click();
  checkpoint('Open second uses the current ordered list, including the authored-evidence ranking');
  loseNextTurn=true;const before=turns().length;const lostFailed=page.waitForEvent('requestfailed',{predicate:r=>r.method()==='POST'&&/\/threads\/[0-9a-f-]+\/turns$/.test(new URL(r.url()).pathname)});
  await page.locator('#assistant-text').fill('找示例儿童和妈妈在海边的照片');await page.locator('#assistant-send').click();await lostFailed;
  if(!await page.locator('#assistant-private-management').evaluate(el=>el.open))await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-recover').waitFor({state:'visible'});
  assert.equal(turns().length,before+1);const lost=turns().at(-1);assert.equal(lost.response.result.version,2);
  await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(()=>document.querySelectorAll('#assistant-results .assistant-result').length===2&&!document.querySelector('#assistant-private-new').disabled);
  const reads=browserRequests.filter(x=>x.method==='GET'&&x.path.includes('/requests/'+lost.response.request_id));
  assert.ok(reads.length>0);assert.ok(reads.every(x=>x.headers['x-photohouse-search-version']==='2'));
  assert.equal(turns().length,before+1);assert.equal(await page.locator('#viewer').isVisible(),false);
  assert.equal(await page.evaluate(()=>window.__phSpeechCalls),0);
  checkpoint('Lost response recovers with a version-bound GET only; it does not resend, open a viewer or speak');
  // Keyboard refinement and enlarged bilingual rendering use the same live controller.
  await page.setViewportSize({width:390,height:845});
  await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  await page.locator('#assistant-text').focus();await page.locator('#assistant-text').fill('只看2026年的');
  const keyboardBefore=turns().length;await page.keyboard.press('Control+Enter');
  await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled);
  assert.equal(turns().length,keyboardBefore+1);
  await page.locator('#assistant-search-summary').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'search-phone-zh-150.png'),fullPage:false});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.locator('#assistant-results').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'search-phone-evidence-zh-150.png'),fullPage:false});
  const languageCaps=page.waitForResponse(r=>new URL(r.url()).pathname==='/assistant/workspace/v1/capabilities'&&r.status()===200);languageCaps.catch(()=>{});
  await page.locator('#language').click();await languageCaps;
  await page.waitForFunction(()=>document.documentElement.lang==='en'&&!document.querySelector('#assistant-private').hidden&&!document.querySelector('#assistant-private-new').disabled);
  await page.locator('#assistant-search-perspective').waitFor({state:'visible'});
  await send('find photos containing "beach"');
  await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled&&document.querySelectorAll('#assistant-results .assistant-result').length===2);
  assert.match(await page.locator('#assistant-search-summary').innerText(),/Text|Contains|beach/);
  assert.match(await page.locator('#assistant-results').innerText(),/AI.generated|Generated|generated/);
  await page.locator('#assistant-search-summary').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'search-phone-en-150.png'),fullPage:false});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.locator('#assistant-results').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(artifacts,'search-phone-evidence-en-150.png'),fullPage:false});
  checkpoint('Keyboard submission and Chinese/English 390px enlarged layouts retain readable conditions and generated-evidence labels');
  // These descriptions must ask for evidence, without inventing visual matches.
  const anchored=await send('find Sample Child photos in 2026');
  const vague=await send('the photos where we were celebrating indoors');
  assert.equal(vague.result.kind,'clarification');assert.match(vague.result.reply,/searchable evidence/);assert.match(vague.result.reply,/\?/);
  for(const key of ['context','filters','items','total'])assert.deepEqual(vague.result[key],anchored.result[key]);
  const videos=await send('only videos and keep the same people');assert.deepEqual(videos.result.filters.people,anchored.result.filters.people);assert.deepEqual(videos.result.filters.date,anchored.result.filters.date);assert.deepEqual(videos.result.filters.media,['video']);
  assert.equal(videos.result.total,0,'generated fixture has no video match; the assistant must not broaden it');
  const earlier=await send('再早一点');assert.equal(earlier.result.kind,'clarification');assert.match(earlier.result.reply,/哪段更早的时间？/);
  for(const key of ['context','filters','items','total'])assert.deepEqual(earlier.result[key],videos.result[key]);
  checkpoint('Vague wording asks for evidence; video and ambiguous-date follow-ups retain the exact person and date, including empty results');
  await page.setViewportSize({width:390,height:845});await page.locator('#assistant-reply').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'clarification-phone-zh-150.png'),fullPage:false});

  const held=gateTurn(),beforePending=turns().length;
  await page.locator('#assistant-text').fill('only photos');const pendingStart=performance.now();await page.locator('#assistant-send').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-send').disabled&&!document.querySelector('#assistant-cancel').hidden);
  const pendingMs=performance.now()-pendingStart;
  await held.seen;assert.equal(await page.locator('#assistant-results .assistant-result').count(),0,'old result cards are withheld while pending');
  await page.locator('#assistant-send').evaluate(button=>button.click());assert.equal(turns().length,beforePending+1,'disabled Send cannot duplicate the pending request');
  await page.locator('#assistant-cancel').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-text').value==='only photos');
  held.release();await page.locator('#assistant-private-recover').waitFor({state:'visible'});
  const beforeRecovery=turns().length;await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled&&document.querySelectorAll('#assistant-results .assistant-result').length>0);
  assert.equal(turns().length,beforeRecovery,'cancelled wait recovers through GET only');
  const recovered=browserRequests.filter(entry=>entry.method==='GET'&&entry.path.includes('/requests/')&&entry.response?.status==='completed').at(-1).response.result;
  assert.deepEqual(recovered.filters.people,videos.result.filters.people);assert.deepEqual(recovered.filters.date,videos.result.filters.date);assert.deepEqual(recovered.filters.media,['image']);
  timings.push({kind:'pending_feedback',elapsed_ms:Math.round(pendingMs),turn_posts:1,recovery_turn_posts:0});
  checkpoint('Pending feedback appears before completion, duplicate Send is blocked, and cancellation preserves the draft and exact context for GET-only recovery');
  // A no-match result describes the evidence boundary without relaxing people.
  const empty=await send('find Sample Child and Sample Adult photos in 2099');
  assert.equal(empty.result.total,0);assert.deepEqual(empty.result.items,[]);
  assert.deepEqual(empty.result.filters.people,{ids:['301','302'],match:'all'});
  assert.match(empty.result.reply,/confirmed assignments only/);assert.match(empty.result.reply,/same item/);
  assert.match(empty.result.reply,/any date/);assert.equal(empty.result.effect,null);
  await page.waitForFunction(value=>document.querySelector('#assistant-reply')?.textContent===value,empty.result.reply);
  await page.locator('#assistant-reply').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'people-scope-phone-en-150.png'),fullPage:false});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  const explained=await send('为什么没有结果');
  for(const key of ['context','filters','items','total','has_more','interpretation'])assert.deepEqual(explained.result[key],empty.result[key]);
  assert.match(explained.result.reply,/已确认的标注/);assert.match(explained.result.reply,/同一项/);
  await page.waitForFunction(value=>document.querySelector('#assistant-reply')?.textContent===value,explained.result.reply);
  await page.setViewportSize({width:320,height:845});
  await page.locator('#assistant-reply').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'people-scope-phone-zh-150-320.png'),fullPage:false});
  const overflow320=await page.evaluate(()=>({width:innerWidth,page:document.documentElement.scrollWidth,
    elements:Array.from(document.querySelectorAll('body *')).filter(node=>{const r=node.getBoundingClientRect();return r.width>0&&r.right>innerWidth+1;}).slice(0,12).map(node=>({tag:node.tagName,id:node.id,className:typeof node.className==='string'?node.className:'',right:node.getBoundingClientRect().right,width:node.getBoundingClientRect().width}))}));
  assert.equal(overflow320.page<=overflow320.width+1,true,JSON.stringify(overflow320));
  checkpoint('Reviewed-person scope stays visible in enlarged English/Chinese empty replies without changing joint filters, context or opening media');
  const anyPerson=page.locator('#assistant-search-refinements').getByRole('button',{name:'Any person',exact:true});
  await anyPerson.waitFor();
  const beforeClear=turns().length;
  await page.locator('#assistant-text').fill('My existing draft');
  await anyPerson.click();
  assert.equal(await page.locator('#assistant-text').inputValue(),'My existing draft');
  await page.locator('#assistant-text').fill('');
  await anyPerson.press('Enter');
  assert.equal(await page.locator('#assistant-text').inputValue(),'anyone');
  assert.equal(turns().length,beforeClear,'preparing a change leaves the active filters in place');
  const cleared=await submit();
  const {people,...retained}=empty.result.filters;
  assert.deepEqual(cleared.result.filters,retained);
  assert.equal(turns().length,beforeClear+1);
  await anyPerson.waitFor({state:'detached'});
  checkpoint('Any person preserves the composer draft and clears only the people filter after explicit submission');

  const placeCases=[
    {language:'en',query:'find Sample Child and Sample Adult photos in Example region in 2026 containing "beach"',
      button:'Any place',instruction:'anywhere',place:'Example region',caption:'beach',width:1440},
    {language:'zh',query:'找示例儿童和示例成人在示例地区的照片，2026年，包含"海边"',
      button:'不限地点',instruction:'不限地点',place:'示例地区',caption:'海边',width:390},
  ];
  for(const {language,query,button,instruction,place,caption,width} of placeCases){
    await page.setViewportSize({width,height:845});
    if(language==='zh'){
      const capabilities=page.waitForResponse(r=>new URL(r.url()).pathname==='/assistant/workspace/v1/capabilities'&&r.status()===200);
      capabilities.catch(()=>{});
      await page.locator('#language').click();
      await capabilities;
      await page.waitForFunction(()=>document.documentElement.lang==='zh-CN'&&!document.querySelector('#assistant-private-new').disabled);
    }
    const located=await send(query);
    assert.equal(located.result.kind,'results',JSON.stringify(located.result));
    assert.deepEqual(located.result.filters,{
      media:['image'],date:{from:'2026-01-01',to:'2026-12-31'},
      people:{ids:['301','302'],match:'all'},locations:['601'],text:caption,
    });
    assert.deepEqual(located.result.items.map(item=>item.id),['101']);
    const searchSummary=page.locator('#assistant-search-summary');
    const anyPlace=searchSummary.getByRole('button',{name:button,exact:true});
    await anyPlace.waitFor({timeout:5000});
    const beforePlace=turns().length;
    const composer=page.locator('#assistant-text');
    await composer.fill('My unsent draft');
    await anyPlace.click();
    assert.equal(await composer.inputValue(),'My unsent draft');
    await composer.fill('');
    await anyPlace.press('Enter');
    assert.equal(await composer.inputValue(),instruction);
    assert((await searchSummary.innerText()).includes(place));
    assert.equal(turns().length,beforePlace,'preparing the place change sends no turn');
    await anyPlace.scrollIntoViewIfNeeded();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await page.screenshot({path:path.join(artifacts,'any-place-'+language+'.png'),fullPage:false});
    const updated=await submit();
    const {locations,...expected}=located.result.filters;
    assert.deepEqual(updated.result.filters,expected);
    assert.deepEqual(updated.result.items.map(item=>item.id).sort(),['101','102']);
    assert.equal(updated.result.effect,null);
    assert.equal(turns().length,beforePlace+1);
    await anyPlace.waitFor({state:'detached'});
    assert(!(await searchSummary.innerText()).includes(place));
  }
  checkpoint('English and Chinese place controls preserve drafts and clear only place after Send');
  assert.deepEqual(pageErrors,[]);assert.deepEqual(blockedOrigins,[]);
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checkpoints,pageErrors,blockedOrigins,syntheticBackend:true,externalRequests:0,timings,timing_scope:'Generated ASGI bridge + browser click-to-render; not native or provider latency'},null,2));
  console.log(`Search browser checks: ${checkpoints.length} passed. Artifacts: ${artifacts}`);
})().catch(async error=>{console.error(error);try{console.error(await page?.evaluate(()=>({send:document.querySelector('#assistant-send')?.disabled,status:document.querySelector('#assistant-status')?.textContent,privateStatus:document.querySelector('#assistant-private-status')?.textContent,lang:document.documentElement.lang}))); await page?.screenshot({path:path.join(artifacts,'failure.png'),fullPage:false});console.error(JSON.stringify(browserRequests.slice(-6).map(x=>({method:x.method,path:x.path,status:x.status,response:x.response})),null,2));}catch{}process.exitCode=1;}).finally(async()=>{await context?.close();await browser?.close();try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');}catch{}bridge.kill();});
