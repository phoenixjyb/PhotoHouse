/* Synthetic browser coverage for the bounded, in-page voice-search turn trail. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-assistant-trail-'));
fs.mkdirSync(artifacts,{recursive:true,mode:0o700});fs.chmodSync(artifacts,0o700);console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python'),
  [path.join(__dirname,'assistant_pending_recovery_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,turnNumber=0,dropNextTurn=false,malformedNextTurn=false,holdNextTurn=null,nextReplyOverride=null;
const pendingRpc=new Map(),requests=[],pageErrors=[],externalOrigins=[],activeGates=new Set();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{
  const result=JSON.parse(line);if(result.ready){readyResolve();return;}
  const call=pendingRpc.get(result.id);if(call){pendingRpc.delete(result.id);call.resolve(result);}
});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Synthetic API bridge exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Synthetic API bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
function responseGate(){
  let arrive,release,finish;
  const gate={cancelExpected:false,arrived:new Promise(resolve=>{arrive=resolve;}),released:new Promise(resolve=>{release=resolve;}),
    finished:new Promise(resolve=>{finish=resolve;}),arrive:()=>arrive(),finish:()=>finish(),release:()=>{release();activeGates.delete(gate);}};
  activeGates.add(gate);return gate;
}
function turnResponse(body){
  const sequence=++turnNumber,id=String(200+sequence),clarification=body.text.includes('clarify');
  const context=clarification&&body.context?body.context:{
    library_id:body.library_id,binding:'a'.repeat(64),fingerprint:'b'.repeat(64),filters:{},visible_ids:[id],total:1};
  const reply=nextReplyOverride!==null?(value=>{nextReplyOverride=null;return value;})(nextReplyOverride):sequence===1?'Assistant reply <img src=x onerror="window.__trailXss=1">':
    body.text.includes('clarify')?'Please clarify that detail.':`Reply ${sequence}`;
  return {version:1,kind:clarification?'clarification':'results',reply,context,
    filters:context.filters,items:[{id,kind:'image'}],total:1,has_more:false,effect:null};
}
let browser,context,page;
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),
    args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){externalOrigins.push(url.origin);await route.abort();return;}
    const entry={method:request.method(),path:url.pathname+url.search,body:request.postData()||''};requests.push(entry);
    if(entry.method==='GET'&&/^\/assets\/[1-9][0-9]*\/thumbnail$/.test(url.pathname)){
      await route.fulfill({status:200,contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pXcAAAAASUVORK5CYII=','base64')});return;
    }
    if(entry.method==='POST'&&url.pathname==='/assistant/v1/turns'){
      if(dropNextTurn){dropNextTurn=false;await route.abort('failed');return;}
      if(malformedNextTurn){malformedNextTurn=false;await route.fulfill({status:200,contentType:'application/json',
        headers:{'cache-control':'no-store'},body:JSON.stringify({version:1,kind:'results',reply:'Malformed response',context:null,filters:null,total:0,has_more:false,effect:null})});return;}
      const body=JSON.parse(entry.body),response=turnResponse(body),gate=holdNextTurn;
      if(gate){holdNextTurn=null;gate.arrive();await gate.released;}
      try{await route.fulfill({status:200,contentType:'application/json',headers:{'cache-control':'no-store'},body:JSON.stringify(response)});}
      catch(error){if(!gate?.cancelExpected&&!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
      finally{gate?.finish();}
      return;
    }
    const headers=await request.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const response=await rpc({method:entry.method,path:entry.path,headers,
      body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    const outputHeaders={...response.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try{await route.fulfill({status:response.status,headers:outputHeaders,body:Buffer.from(response.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});
  const signIn=async phone=>{await page.locator('#phone').fill(phone);await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();};
  await signIn('+12025550100');
  await page.locator('#assistant-panel > summary').click();await page.locator('#assistant-form').waitFor({state:'visible'});
  const submit=async text=>{
    const expected=turnNumber+1,expectedTrailCount=Math.min(await page.locator('#assistant-turn-trail-list > li').count()+1,8);
    await page.locator('#assistant-text').fill(text);
    try{await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled,null,{timeout:8000});}
    catch(error){console.error('assistant send state',JSON.stringify(await page.evaluate(()=>({disabled:document.getElementById('assistant-send').disabled,
      status:document.getElementById('assistant-status').textContent,pendingHidden:document.getElementById('assistant-pending-turn').hidden,
      receiptHidden:document.getElementById('assistant-receipt').hidden,formHidden:document.getElementById('assistant-form').hidden,
      recovery:sessionStorage.getItem('photohouse.assistant.turn-recovery.v1')}))));throw error;}
    await page.locator('#assistant-send').click();
    const afterSubmit=await page.evaluate(()=>({focus:document.activeElement?.id,scrollY:window.scrollY}));
    await page.waitForFunction(count=>document.querySelectorAll('#assistant-turn-trail-list > li').length===count,expectedTrailCount);
    const expectedReply=expected===1?'Assistant reply <img src=x onerror="window.__trailXss=1">':
      text.includes('clarify')?'Please clarify that detail.':`Reply ${expected}`;
    await page.waitForFunction(value=>document.querySelector('#assistant-reply')?.textContent===value,expectedReply);
    const reveal=await page.locator('#assistant-turn-trail-list').evaluate(list=>{
      const entry=list.lastElementChild,reply=entry?.lastElementChild,listRect=list.getBoundingClientRect(),entryRect=entry?.getBoundingClientRect(),replyRect=reply?.getBoundingClientRect();
      return {bounded:list.clientHeight<=parseFloat(getComputedStyle(list).maxHeight)+1,
        latestVisible:!!entryRect&&!!replyRect&&entryRect.bottom<=listRect.bottom+1&&replyRect.bottom<=listRect.bottom+1&&replyRect.top>=listRect.top-1,
        scrollTop:list.scrollTop,focus:document.activeElement?.id,scrollY:window.scrollY};
    });
    assert(reveal.bounded,'turn trail uses a bounded, scrollable region when its content exceeds the cap');
    assert(reveal.latestVisible,'newest completed turn is revealed inside the trail region');
    assert.equal(reveal.focus,afterSubmit.focus,'revealing the newest turn does not move keyboard focus');
    assert.equal(reveal.scrollY,afterSubmit.scrollY,'revealing the newest turn does not scroll the page');
  };
  const scaleTrailText150=()=>page.locator('#assistant-turn-trail').evaluate(root=>{
    const nodes=[root,...root.querySelectorAll('*')].filter(node=>[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&child.textContent.trim()));
    const rows=nodes.map((node,index)=>{const style=getComputedStyle(node);return {index,size:parseFloat(style.fontSize),line:parseFloat(style.lineHeight),oldSize:node.style.fontSize,oldLine:node.style.lineHeight};});
    rows.forEach(row=>{const node=nodes[row.index];node.dataset.assistantTrailFont=String(row.index);node.style.fontSize=`${row.size*1.5}px`;if(Number.isFinite(row.line))node.style.lineHeight=`${row.line*1.5}px`;});
    return rows;
  });
  const restoreTrailText=rows=>page.locator('#assistant-turn-trail').evaluate((root,values)=>{
    const nodes=[root,...root.querySelectorAll('*')].filter(node=>[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&child.textContent.trim()));
    for(const row of values){const node=nodes[row.index];node.style.fontSize=row.oldSize;node.style.lineHeight=row.oldLine;delete node.dataset.assistantTrailFont;}
  },rows);
  const trailGeometry=()=>page.evaluate(()=>{
    const rect=node=>{if(!node)return null;const value=node.getBoundingClientRect();return {left:value.left,right:value.right,top:value.top,bottom:value.bottom};};
    const section=document.querySelector('#assistant-turn-trail'),list=document.querySelector('#assistant-turn-trail-list');
    const entries=[...document.querySelectorAll('#assistant-turn-trail-list > li')];
    return {width:innerWidth,height:innerHeight,pageWidth:document.documentElement.scrollWidth,
      sectionWidth:section.scrollWidth,sectionClientWidth:section.clientWidth,listWidth:list.scrollWidth,listClientWidth:list.clientWidth,
      listHeight:list.clientHeight,listScrollHeight:list.scrollHeight,listScrollTop:list.scrollTop,listMaxHeight:getComputedStyle(list).maxHeight,
      section:rect(section),list:rect(list),heading:rect(document.querySelector('#assistant-turn-trail-title')),
      latestControl:rect(document.querySelector('#assistant-turn-trail-latest')),
      latestControlHidden:document.querySelector('#assistant-turn-trail-latest').hidden,
      latestReply:rect(entries.at(-1)?.lastElementChild),entries:entries.map(entry=>({rect:rect(entry),scrollWidth:entry.scrollWidth,clientWidth:entry.clientWidth}))};
  });
  const trailReadingPosition=()=>page.locator('#assistant-turn-trail-list').evaluate(list=>{
    const bounds=list.getBoundingClientRect();return {scrollTop:list.scrollTop,scrollHeight:list.scrollHeight,clientHeight:list.clientHeight,
      visible:[...list.children].map(item=>({id:item.dataset.assistantTurnId,offset:item.getBoundingClientRect().top-bounds.top,
        visible:item.getBoundingClientRect().bottom>bounds.top&&item.getBoundingClientRect().top<bounds.bottom})).filter(item=>item.visible)};
  });
  await page.setViewportSize({width:390,height:1024});
  await submit('<img src=x onerror="window.__trailXss=1">');
  assert.equal(await page.locator('#assistant-turn-trail-list img').count(),0,'HTML-looking user and assistant text creates no elements');
  assert.match(await page.locator('#assistant-turn-trail-list').innerText(),/<img src=x onerror="window.__trailXss=1">/,'HTML-looking text remains readable');
  assert.equal(await page.evaluate(()=>window.__trailXss===1),false,'rendering the trail does not execute markup');
  for(let index=1;index<10;index++)await submit(`查找照片 ${index}`);
  assert.equal(await page.locator('#assistant-turn-trail').isVisible(),true);
  assert.equal(await page.locator('#assistant-turn-trail-title').textContent(),'本页最近对话');
  assert.equal(await page.locator('#assistant-turn-trail-list > li').count(),8,'trail retains no more than eight successful exchanges');
  const trail=await page.locator('#assistant-turn-trail-list').innerText();
  assert.equal(trail.includes('查找照片 2'),true,'oldest retained exchange is the third sent turn');
  assert.equal(trail.includes('查找照片 1'),false,'oldest exchange was evicted at the eight-turn cap');
  assert.equal(trail.includes('Reply 10'),true,'latest successful reply appears in trail');
  assert.equal(await page.locator('#assistant-turn-trail-list > li').evaluateAll(rows=>new Set(rows.map(row=>row.dataset.assistantTurnId)).size),8,'each rendered exchange has an independent client-local identity');
  assert.equal(await page.locator('#assistant-results .assistant-result p').first().textContent(),'照片 210','current result cards remain from the latest turn');
  assert.equal(await page.locator('#assistant-turn-trail-list img').count(),0,'history entries create no HTML from response text');
  assert.equal(await page.evaluate(()=>JSON.stringify(Object.keys(sessionStorage))),JSON.stringify([]),'turn text is not persisted in browser storage');
  const postsBeforeScroll=requests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/turns').length,requestsBeforeScroll=requests.length,pageYBeforeScroll=await page.evaluate(()=>window.scrollY);
  await page.locator('#assistant-turn-trail-list').evaluate(list=>{list.scrollTop=Math.min(list.scrollHeight-list.clientHeight,list.firstElementChild.getBoundingClientRect().height+20);});
  const beforeHeld=await trailReadingPosition(),oldestBefore=await page.locator('#assistant-turn-trail-list > li').first().getAttribute('data-assistant-turn-id');
  assert(beforeHeld.visible.length>0&&beforeHeld.visible[0].id!==oldestBefore,'reading position is away from the oldest row before a delayed reply');
  assert.equal(requests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/turns').length,postsBeforeScroll,'manual trail scrolling starts no assistant request');
  assert.equal(requests.length,requestsBeforeScroll,'manual trail scrolling sends no network request');assert.equal(await page.evaluate(()=>window.scrollY),pageYBeforeScroll,'manual trail scrolling does not move the page');
  const heldReply=responseGate();holdNextTurn=heldReply;nextReplyOverride='Reply 10';
  await page.locator('#assistant-text').fill('repeat an identical reply while I read');
  await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled);await page.locator('#assistant-send').click();await heldReply.arrived;
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),false,'no jump indicator appears before the held reply succeeds');
  const heldCount=await page.locator('#assistant-turn-trail-list > li').count(),heldFocus=await page.evaluate(()=>document.activeElement.id),heldPageY=await page.evaluate(()=>window.scrollY);
  heldReply.release();await heldReply.finished;
  await page.waitForFunction(()=>{const entries=document.querySelectorAll('#assistant-turn-trail-list > li'),last=entries[entries.length-1];return entries.length===8&&last?.querySelector('.assistant-turn-trail-text')?.textContent==='repeat an identical reply while I read'&&last?.lastElementChild?.textContent==='Reply 10';});
  const afterHeld=await trailReadingPosition(),survivingAnchor=beforeHeld.visible[0];
  assert.equal(heldCount,8,'the delayed response does not change history before release');
  assert(afterHeld.visible.some(entry=>entry.id===survivingAnchor.id),'cap eviction keeps the first visible surviving exchange in view');
  assert(Math.abs(afterHeld.visible.find(entry=>entry.id===survivingAnchor.id).offset-survivingAnchor.offset)<2,'cap eviction restores the surviving row reading offset');
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),true,'a completed reply outside the reading position shows Jump to latest');
  assert.equal(await page.locator('#assistant-turn-trail-latest').textContent(),'跳到最新','Chinese jump control is localized');
  assert.equal(await page.locator('#assistant-turn-trail-list > li').evaluateAll(rows=>rows.at(-1).lastElementChild.textContent===rows.at(-2).lastElementChild.textContent),true,'the fixture returns two identical replies');
  assert.equal(await page.locator('#assistant-turn-trail-list > li').evaluateAll(rows=>rows.at(-1).dataset.assistantTurnId===rows.at(-2).dataset.assistantTurnId),false,'identical reply text does not collapse distinct exchanges');
  assert.equal(await page.evaluate(()=>document.activeElement.id),heldFocus,'a delayed completion does not move keyboard focus');
  assert.equal(await page.evaluate(()=>window.scrollY),heldPageY,'a delayed completion does not move the page');
  assert.equal(requests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/turns').length,postsBeforeScroll+1,'scrolling itself did not add a send');
  await page.waitForFunction(()=>document.getElementById('assistant-cancel').hidden);
  const beforeLocale=await trailReadingPosition();let sessionRefresh=page.waitForResponse(response=>new URL(response.url()).pathname==='/auth/session');let galleryRefresh=page.waitForResponse(response=>{const url=new URL(response.url());return url.pathname==='/assets'&&url.searchParams.get('page_size')==='24';});await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='en');await Promise.all([sessionRefresh,galleryRefresh]);
  assert.equal(await page.locator('#assistant-turn-trail-latest').textContent(),'Jump to latest','locale render updates the control label');
  const afterEnglishLocale=await trailReadingPosition();assert.equal(afterEnglishLocale.visible[0].id,beforeLocale.visible[0].id,'locale render retains the same reading row');
  assert(Math.abs(afterEnglishLocale.visible[0].offset-beforeLocale.visible[0].offset)<2,'locale render retains the reading offset');
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),true,'locale render keeps the jump indicator');
  sessionRefresh=page.waitForResponse(response=>new URL(response.url()).pathname==='/auth/session');galleryRefresh=page.waitForResponse(response=>{const url=new URL(response.url());return url.pathname==='/assets'&&url.searchParams.get('page_size')==='24';});await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='zh-CN');await Promise.all([sessionRefresh,galleryRefresh]);
  assert.equal(await page.locator('#assistant-turn-trail-latest').textContent(),'跳到最新','returning locale restores the Chinese control label');
  const afterChineseLocale=await trailReadingPosition();assert.equal(afterChineseLocale.visible[0].id,beforeLocale.visible[0].id,'round-trip locale render retains the same reading row');
  assert(Math.abs(afterChineseLocale.visible[0].offset-beforeLocale.visible[0].offset)<2,'round-trip locale render retains the reading offset');
  const zhFonts=await scaleTrailText150();await page.locator('#assistant-turn-trail-title').evaluate(node=>node.scrollIntoView({block:'center',inline:'nearest'}));
  const zhLayout=await trailGeometry();
  assert.equal(zhLayout.width,390,'Chinese capture keeps the actual 390px viewport');
  assert(zhLayout.pageWidth<=390,'Chinese trail has no page overflow at 390px');
  assert(zhLayout.sectionWidth<=zhLayout.sectionClientWidth+1&&zhLayout.listWidth<=zhLayout.listClientWidth+1,'Chinese trail has no internal horizontal overflow');
  assert(zhLayout.listScrollHeight>zhLayout.listHeight&&zhLayout.listHeight<=384,'Chinese trail is bounded while retaining scrollable history');
  assert(zhLayout.latestControlHidden===false&&zhLayout.latestControl.left>=0&&zhLayout.latestControl.right<=390&&zhLayout.latestControl.top>=0&&zhLayout.latestControl.bottom<=zhLayout.height,'Chinese Jump to latest control stays fully visible in the capture viewport');
  assert(zhLayout.latestControl.bottom-zhLayout.latestControl.top>=44,'Chinese jump control retains a usable touch target');
  assert(zhLayout.heading.left>=0&&zhLayout.heading.right<=390&&zhLayout.heading.top>=0&&zhLayout.heading.bottom<=zhLayout.height,`Chinese trail label stays in the capture viewport: ${JSON.stringify(zhLayout)}`);
  assert(zhLayout.entries.every(item=>item.rect.left>=0&&item.rect.right<=390&&item.scrollWidth<=item.clientWidth+1),'Chinese trail cards stay in bounds and wrap');
  const zhScaled=await page.evaluate(rows=>{const root=document.querySelector('#assistant-turn-trail'),nodes=[root,...root.querySelectorAll('*')].filter(node=>[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&child.textContent.trim()));return rows.every(row=>Math.abs(parseFloat(getComputedStyle(nodes[row.index]).fontSize)-row.size*1.5)<0.2);},zhFonts);
  assert(zhScaled,'Chinese trail text is individually scaled to 150%');
  await page.locator('#assistant-turn-trail-list').focus();
  assert.equal(await page.locator('#assistant-turn-trail-list').getAttribute('aria-labelledby'),'assistant-turn-trail-title','scroll region has a localized accessible name');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'assistant-turn-trail-list','scroll region is keyboard focusable');
  const zhKeyboardPageY=await page.evaluate(()=>window.scrollY);
  await page.keyboard.press('Home');const zhTop=await page.locator('#assistant-turn-trail-list').evaluate(list=>list.scrollTop);
  await page.keyboard.press('PageDown');const zhPageDown=await page.locator('#assistant-turn-trail-list').evaluate(list=>list.scrollTop);
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),true,'keyboard scrolling through older rows preserves the jump indicator');
  const zhCapture=path.join(artifacts,'assistant-turn-trail-zh-390px-text150.png');await page.screenshot({path:zhCapture,fullPage:false});fs.chmodSync(zhCapture,0o600);
  await page.keyboard.press('End');const zhKeyboardEnd=await page.locator('#assistant-turn-trail-list').evaluate(list=>({scrollTop:list.scrollTop,
    pageY:window.scrollY,focus:document.activeElement.id,latestBottom:list.lastElementChild.getBoundingClientRect().bottom,listBottom:list.getBoundingClientRect().bottom}));
  assert(zhTop<=1&&zhPageDown>zhTop&&zhKeyboardEnd.scrollTop>=zhPageDown,'keyboard Home/PageDown/End scrolls the trail region');
  assert(zhKeyboardEnd.latestBottom<=zhKeyboardEnd.listBottom+1,'keyboard End reveals the newest Chinese turn');
  assert.equal(zhKeyboardEnd.focus,'assistant-turn-trail-list','keyboard scrolling retains focus in the trail');
  assert.equal(zhKeyboardEnd.pageY,zhKeyboardPageY,'keyboard scrolling does not move the page');
  await page.waitForFunction(()=>document.querySelector('#assistant-turn-trail-latest').hidden===true);
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),false,'natural keyboard End clears the jump indicator at the trail tail');
  await page.locator('#assistant-turn-trail-list').evaluate(list=>list.scrollTop=list.scrollHeight);
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),false,'native tail scrolling keeps the jump indicator clear');
  await page.locator('#assistant-send').focus();
  await restoreTrailText(zhFonts);
  console.log('ZH_LAYOUT '+JSON.stringify(zhLayout));
  console.log('PASS Chinese eight-turn trail at actual 390px viewport with 150% text');

  const posts=()=>requests.filter(item=>item.method==='POST'&&item.path==='/assistant/v1/turns');
  const secondTurnPayload=JSON.parse(posts()[1].body);
  assert.deepEqual(Object.keys(secondTurnPayload).sort(),['context','library_id','text'],'follow-ups send only the existing request fields');
  assert.deepEqual(Object.keys(secondTurnPayload.context).sort(),['binding','filters','fingerprint','library_id','total','visible_ids'],'turn trail is not a context field');
  assert.equal(JSON.stringify(secondTurnPayload.context).includes('<img src=x'),false,'displayed user/reply text is absent from future context');
  assert.equal(JSON.stringify(secondTurnPayload.context).includes('查找照片 1'),false,'displayed history is not prompt context');

  const trailBeforeMalformed=await page.locator('#assistant-turn-trail-list > li').count(),postsBeforeMalformed=posts().length;
  malformedNextTurn=true;await page.locator('#assistant-text').fill('malformed response must not enter history');
  await page.locator('#assistant-send').click();await page.locator('#assistant-pending-turn').waitFor();
  await page.waitForFunction(()=>document.getElementById('assistant-status').textContent==='无法安全显示这条回复，请重试。');
  assert.equal(await page.locator('#assistant-turn-trail-list > li').count(),trailBeforeMalformed,'malformed replies are excluded from completed history');
  assert.equal((await page.locator('#assistant-turn-trail-list').innerText()).includes('malformed response must not enter history'),false);
  assert.equal(await page.locator('#assistant-status').textContent(),'无法安全显示这条回复，请重试。','malformed response keeps the existing safe error');
  await page.locator('#assistant-pending-ack').click();
  assert.equal(await page.locator('#assistant-turn-trail').isVisible(),false,'acknowledging malformed output resets history');
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),false,'malformed-output reset clears the jump indicator');
  assert.equal(posts().length,postsBeforeMalformed+1,'malformed request is not automatically retried');

  await submit('find photos after malformed response');
  let latestResultId=String(200+turnNumber);
  const beforeClarification=posts().length;await submit('please clarify this detail');
  const clarificationPayload=JSON.parse(posts().at(-1).body);
  assert.equal(clarificationPayload.context.visible_ids[0],latestResultId,'follow-up keeps the prior visible-result context');
  assert.equal(JSON.stringify(clarificationPayload.context).includes('find photos after malformed response'),false,'history text is not sent as context');
  assert.equal(await page.locator('#assistant-reply').textContent(),'Please clarify that detail.','clarification reply is visible');
  assert.equal(posts().length,beforeClarification+1,'a clarification turn runs only after explicit submit');

  const turnCountBeforeFailure=await page.locator('#assistant-turn-trail-list > li').count();dropNextTurn=true;
  await page.locator('#assistant-text').fill('uncertain query must not enter history');await page.locator('#assistant-send').click();
  await page.locator('#assistant-pending-turn').waitFor();
  assert.equal(await page.locator('#assistant-turn-trail-list > li').count(),turnCountBeforeFailure,'uncertain submissions never enter completed history');
  assert.equal((await page.locator('#assistant-turn-trail-list').innerText()).includes('uncertain query must not enter history'),false);
  const postCountBeforeAck=posts().length;await page.locator('#assistant-pending-ack').click();
  assert.equal(await page.locator('#assistant-turn-trail').isVisible(),false,'explicit reset clears the temporary trail');
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),false,'uncertain-request reset clears the jump indicator');
  assert.equal(posts().length,postCountBeforeAck,'acknowledging an uncertain request does not resend it');
  nextReplyOverride='T'.repeat(3500);await page.locator('#assistant-text').fill('first exchange has a very tall synthetic reply');
  await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled);await page.locator('#assistant-send').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-turn-trail-list > li:last-child .assistant-turn-trail-text')?.textContent==='first exchange has a very tall synthetic reply');
  const tallAtTail=await page.locator('#assistant-turn-trail-list').evaluate(list=>({replyBottom:list.lastElementChild.lastElementChild.getBoundingClientRect().bottom,listBottom:list.getBoundingClientRect().bottom}));
  assert(tallAtTail.replyBottom<=tallAtTail.listBottom+1,'following the first exchange reveals its latest reply even when its row is taller than the viewport');
  for(let index=1;index<8;index++)await submit(`cap eviction row ${index}`);
  const tallBefore=await page.locator('#assistant-turn-trail-list').evaluate(list=>{list.scrollTop=0;const bounds=list.getBoundingClientRect();return {scrollHeight:list.scrollHeight,clientHeight:list.clientHeight,
    visible:[...list.children].map(row=>({id:row.dataset.assistantTurnId,top:row.getBoundingClientRect().top-bounds.top,bottom:row.getBoundingClientRect().bottom-bounds.top,
      reply:row.lastElementChild.textContent})).filter(row=>row.bottom>0&&row.top<bounds.height),ids:[...list.children].map(row=>row.dataset.assistantTurnId)};});
  assert(tallBefore.scrollHeight>tallBefore.clientHeight&&tallBefore.visible.length===1&&tallBefore.visible[0].reply.length>=3500,'a single tall oldest exchange fills the visible reading region');
  const evictTall=responseGate();holdNextTurn=evictTall;await page.locator('#assistant-text').fill('evict the only visible tall exchange');
  await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled);await page.locator('#assistant-send').click();await evictTall.arrived;evictTall.release();await evictTall.finished;
  await page.waitForFunction(()=>{const rows=document.querySelectorAll('#assistant-turn-trail-list > li'),last=rows[rows.length-1];return rows.length===8&&last?.querySelector('.assistant-turn-trail-text')?.textContent==='evict the only visible tall exchange';});
  const afterTall=await page.locator('#assistant-turn-trail-list').evaluate(list=>{const bounds=list.getBoundingClientRect();return {scrollTop:list.scrollTop,first:list.firstElementChild.dataset.assistantTurnId,
    visible:[...list.children].map(row=>({id:row.dataset.assistantTurnId,top:row.getBoundingClientRect().top-bounds.top,bottom:row.getBoundingClientRect().bottom-bounds.top})).filter(row=>row.bottom>0&&row.top<bounds.height)};});
  assert.equal(afterTall.scrollTop,0,'when cap eviction removes every prior visible row, the reader falls back to the oldest remaining row');
  assert.equal(afterTall.first,tallBefore.ids[1],'the first remaining exchange is the deterministic fallback anchor');
  assert(afterTall.visible.some(row=>row.id===tallBefore.ids[1]),'fallback keeps the oldest remaining exchange visible');
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),true,'the fallback remains marked as away from the newest reply');
  await page.waitForFunction(()=>document.getElementById('assistant-cancel').hidden);
  const postsBeforeTrailClear=posts().length;await page.locator('#assistant-clear').click();
  await page.waitForFunction(()=>document.getElementById('assistant-turn-trail').hidden);
  const clearedTrail=await page.locator('#assistant-turn-trail-list').evaluate(list=>({scrollTop:list.scrollTop,scrollHeight:list.scrollHeight}));
  assert.equal(clearedTrail.scrollTop,0,'empty scope reset returns the list to its start');
  assert.equal(clearedTrail.scrollHeight,0,'scope reset leaves no hidden old trail content');
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),false,'scope reset clears the jump indicator');
  assert.equal(posts().length,postsBeforeTrailClear,'clearing reading history does not send a request');
  console.log('PASS follow-up payload stays structured; malformed and uncertain turns are excluded without resend');

  await page.evaluate(()=>{document.documentElement.style.zoom='';});
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  await page.locator('#language').click();await page.waitForFunction(()=>document.documentElement.lang==='en');
  await signIn('+12025550100');await page.locator('#assistant-panel').evaluate(element=>{element.open=true;});await page.locator('#assistant-form').waitFor({state:'visible'});
  await page.setViewportSize({width:390,height:1024});await submit('find photos');await submit('find more photos');await submit('find another set');await submit('find one more set');await submit('find one more');await submit('find another');
  const englishReading=await page.locator('#assistant-turn-trail-list').evaluate(list=>{list.scrollTop=Math.min(list.scrollHeight-list.clientHeight,list.firstElementChild.getBoundingClientRect().height+20);const bounds=list.getBoundingClientRect();return [...list.children].map(row=>({id:row.dataset.assistantTurnId,offset:row.getBoundingClientRect().top-bounds.top,visible:row.getBoundingClientRect().bottom>bounds.top&&row.getBoundingClientRect().top<bounds.bottom})).filter(row=>row.visible);});
  const englishHeld=responseGate();holdNextTurn=englishHeld;await page.locator('#assistant-text').fill('English reply while reading older turns');await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled);
  await page.locator('#assistant-send').click();await englishHeld.arrived;englishHeld.release();await englishHeld.finished;
  await page.waitForFunction(()=>{const rows=document.querySelectorAll('#assistant-turn-trail-list > li'),last=rows[rows.length-1];return document.querySelector('#assistant-turn-trail-latest').hidden===false&&last?.querySelector('.assistant-turn-trail-text')?.textContent==='English reply while reading older turns';});
  const englishAfter=await page.locator('#assistant-turn-trail-list').evaluate(list=>{const bounds=list.getBoundingClientRect();return [...list.children].map(row=>({id:row.dataset.assistantTurnId,offset:row.getBoundingClientRect().top-bounds.top,visible:row.getBoundingClientRect().bottom>bounds.top&&row.getBoundingClientRect().top<bounds.bottom})).filter(row=>row.visible);});
  assert(englishReading.length&&englishAfter.some(row=>row.id===englishReading[0].id),'English held response preserves the visible reading row');
  assert(Math.abs(englishAfter.find(row=>row.id===englishReading[0].id).offset-englishReading[0].offset)<2,'English held response preserves the row offset');
  assert.equal(await page.locator('#assistant-turn-trail-latest').textContent(),'Jump to latest','English jump control is localized');
  assert.equal(await page.locator('#assistant-turn-trail-title').textContent(),'Recent turns on this page');
  const enFonts=await scaleTrailText150();await page.locator('#assistant-turn-trail-title').evaluate(node=>node.scrollIntoView({block:'center',inline:'nearest'}));
  const enLayout=await trailGeometry();
  assert.equal(enLayout.width,390,'English capture keeps the actual 390px viewport');
  assert(enLayout.pageWidth<=390,'English trail has no page overflow at 390px');
  assert(enLayout.sectionWidth<=enLayout.sectionClientWidth+1&&enLayout.listWidth<=enLayout.listClientWidth+1,'English trail has no internal horizontal overflow');
  assert(enLayout.listHeight<=384,'English trail respects the bounded height');
  assert(enLayout.latestControlHidden===false&&enLayout.latestControl.left>=0&&enLayout.latestControl.right<=390&&enLayout.latestControl.top>=0&&enLayout.latestControl.bottom<=enLayout.height,'English Jump to latest control stays fully visible in the capture viewport');
  assert(enLayout.latestControl.bottom-enLayout.latestControl.top>=44,'English jump control retains a usable touch target');
  assert(enLayout.heading.left>=0&&enLayout.heading.right<=390&&enLayout.heading.top>=0&&enLayout.heading.bottom<=enLayout.height,'English trail label stays in the capture viewport');
  assert(enLayout.entries.every(item=>item.rect.left>=0&&item.rect.right<=390&&item.scrollWidth<=item.clientWidth+1),'English trail cards stay in bounds and wrap');
  const enScaled=await page.evaluate(rows=>{const root=document.querySelector('#assistant-turn-trail'),nodes=[root,...root.querySelectorAll('*')].filter(node=>[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&child.textContent.trim()));return rows.every(row=>Math.abs(parseFloat(getComputedStyle(nodes[row.index]).fontSize)-row.size*1.5)<0.2);},enFonts);
  assert(enScaled,'English trail text is individually scaled to 150%');
  const enCapture=path.join(artifacts,'assistant-turn-trail-en-390px-text150.png');await page.screenshot({path:enCapture,fullPage:false});fs.chmodSync(enCapture,0o600);
  await restoreTrailText(enFonts);
  const pageYBeforeJump=await page.evaluate(()=>window.scrollY);await page.locator('#assistant-turn-trail-latest').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-turn-trail-latest').hidden===true);
  const englishJump=await page.locator('#assistant-turn-trail-list').evaluate(list=>({scrollTop:list.scrollTop,maximum:list.scrollHeight-list.clientHeight,latestBottom:list.lastElementChild.getBoundingClientRect().bottom,listBottom:list.getBoundingClientRect().bottom,focus:document.activeElement.id}));
  assert(englishJump.scrollTop>=englishJump.maximum-1&&englishJump.latestBottom<=englishJump.listBottom+1,'explicit Jump to latest reveals the newest reply and clears its control');
  assert.equal(englishJump.focus,'assistant-turn-trail-list','explicit jump leaves focus in the trail after hiding its control');
  assert.equal(await page.evaluate(()=>window.scrollY),pageYBeforeJump,'explicit jump does not move the page');
  console.log('EN_LAYOUT '+JSON.stringify(enLayout));
  const postsBeforeReload=posts().length;await page.reload();await page.locator('#grid .asset').first().waitFor();
  await page.locator('#assistant-panel').evaluate(element=>{element.open=true;});await page.locator('#assistant-form').waitFor({state:'visible'});
  assert.equal(await page.locator('#assistant-turn-trail').isVisible(),false,'reload clears in-memory exchanges');
  assert.equal(posts().length,postsBeforeReload,'reload does not replay completed or uncertain turns');
  await submit('找照片');assert.equal(await page.locator('#assistant-turn-trail').isVisible(),true,'new page can start a fresh temporary trail');
  console.log('PASS English localization, narrow layout, reload clearing, and no automatic turn replay');

  const currentGate=responseGate();holdNextTurn=currentGate;
  const historyBeforeCurrentDelay=await page.locator('#assistant-turn-trail-list > li').count();
  await page.locator('#assistant-text').fill('delayed current account success');
  await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled);await page.locator('#assistant-send').click();await currentGate.arrived;
  assert.equal(await page.locator('#assistant-turn-trail-list > li').count(),historyBeforeCurrentDelay,'delayed response is not displayed before it resolves');
  currentGate.release();await currentGate.finished;
  await page.waitForFunction(count=>document.querySelectorAll('#assistant-turn-trail-list > li').length===count,historyBeforeCurrentDelay+1);
  assert((await page.locator('#assistant-turn-trail-list').innerText()).includes('delayed current account success'),'valid delayed result is added while its original account/library remains current');
  assert.equal(await page.locator('#assistant-results .assistant-result p').first().textContent(),`照片 ${200+turnNumber}`,'current-scope delayed success keeps its newest results current');
  console.log('PASS delayed valid response enters history only after completion in its current scope');

  const delayedGate=responseGate();holdNextTurn=delayedGate;
  await page.locator('#assistant-text').fill('old account delayed success');
  await page.waitForFunction(()=>!document.getElementById('assistant-send').disabled);await page.locator('#assistant-send').click();await delayedGate.arrived;
  const delayedPayload=JSON.parse(posts().at(-1).body);assert.equal(delayedPayload.library_id,'family-a');assert.equal(delayedPayload.text,'old account delayed success');
  await page.locator('#logout').click();await page.locator('#auth').waitFor({state:'visible'});
  await signIn('+12025550101');await page.locator('#assistant-panel').evaluate(element=>{element.open=true;});
  await page.locator('#assistant-form').waitFor({state:'visible'});
  delayedGate.cancelExpected=true;delayedGate.release();await delayedGate.finished;
  assert.equal(await page.locator('#library-select').inputValue(),'family-b','new account has entered its separate library');
  assert.equal(await page.locator('#assistant-turn-trail').isVisible(),false,'account change clears prior exchanges');
  assert.equal(await page.locator('#assistant-turn-trail-latest').isVisible(),false,'account change clears the jump indicator');
  assert.equal(await page.locator('#assistant-turn-trail-list').evaluate(list=>list.scrollTop),0,'account scope reset returns the empty trail to its start');
  assert.equal((await page.locator('#assistant-reply').textContent()).includes('Reply'),false,'delayed old-account success cannot replace the current account view');
  assert.equal((await page.locator('#assistant-turn-trail-list').innerText()).includes('old account delayed success'),false,'delayed old-account question is never added to current history');
  assert.deepEqual(externalOrigins,[],'browser made no external-origin requests');console.log('EXTERNAL_ORIGINS []');
  assert.deepEqual(pageErrors,[],'no browser errors');
  console.log('PASS delayed old-account success cannot enter the current conversation');
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{
  for(const gate of [...activeGates]){gate.cancelExpected=true;gate.release();}
  if(browser)await browser.close();try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');}catch{}
  bridge.kill();
});
