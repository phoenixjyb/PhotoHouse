/* Protected browser-to-ASGI PH-A1 integration with a scripted decision fixture. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-local-agent-browser-'));
fs.mkdirSync(artifacts,{recursive:true});console.log('ARTIFACTS_DIR '+artifacts);
const bridge=spawn(process.env.PH_BROWSER_PYTHON||path.join(root,'../.venv/bin/python'),
  [path.join(__dirname,'agent_browser_bridge.py')],
  {cwd:root,env:{...process.env,PH_SEARCH_FIXTURE:'1'},stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject;const pendingRpc=new Map();
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const value=JSON.parse(line);if(value.ready){readyResolve();return;}const call=pendingRpc.get(value.id);if(call){pendingRpc.delete(value.id);call.resolve(value);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Browser bridge exited (${code})`));for(const call of pendingRpc.values())call.reject(new Error('Browser bridge exited'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pendingRpc.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const requests=[],errors=[],blocked=[];let loseNextAgentResponse=false,browser,context,page;
const checkpoint=label=>console.log('PASS '+label);
function responseBody(value){return JSON.parse(Buffer.from(value.body,'base64').toString());}
async function installTransport(target){
  await target.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){blocked.push(url.origin);await route.abort();return;}
    const entry={method:request.method(),path:url.pathname+url.search,headers:await request.allHeaders(),
      body:request.postData()||'',status:null,response:null};requests.push(entry);
    const headers={...entry.headers};delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const result=await rpc({method:entry.method,path:entry.path,headers,
      body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});
    entry.status=result.status;try{entry.response=responseBody(result);}catch{}
    const agentTurn=entry.method==='POST'&&/\/threads\/[0-9a-f-]+\/turns$/.test(url.pathname)&&
      (()=>{try{return JSON.parse(entry.body).accepts?.includes('agent_media_search_v1')===true;}catch{return false;}})();
    if(agentTurn&&loseNextAgentResponse){loseNextAgentResponse=false;await route.abort('failed');return;}
    const outputHeaders={...result.headers};delete outputHeaders['content-length'];delete outputHeaders['content-encoding'];
    try{await route.fulfill({status:result.status,headers:outputHeaders,body:Buffer.from(result.body,'base64')});}
    catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
}
async function loginAndOpen(){
  await page.goto('https://photohouse.test/ui');
  if(await page.locator('#phone').isVisible()){
    await page.locator('#phone').fill('+12025550102');await page.locator('#password').fill('Synthetic family passphrase!');
    await page.locator('#auth-submit').click();
  }
  await page.locator('#grid .asset').first().waitFor();
  if(!await page.locator('#assistant-panel').evaluate(el=>el.open))await page.locator('#assistant-panel > summary').click();
  await page.locator('#assistant-search-perspective').waitFor({state:'visible'});
}
const turns=()=>requests.filter(item=>item.method==='POST'&&/\/threads\/[0-9a-f-]+\/turns$/.test(new URL(item.path,'https://photohouse.test').pathname));
(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),
    args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:390,height:845},serviceWorkers:'block'});context.setDefaultTimeout(15000);
  await installTransport(context);page=await context.newPage();page.on('pageerror',error=>errors.push(error.stack||error.message));
  await loginAndOpen();
  await page.locator('#assistant-private-new').click();
  await page.waitForFunction(()=>document.querySelector('#assistant-private-select')?.value&&!document.querySelector('#assistant-private-new').disabled);
  const absentCapability=requests.find(item=>item.method==='GET'&&new URL(item.path,'https://photohouse.test').pathname==='/assistant/workspace/v1/agent-capabilities');
  assert.ok(absentCapability,'agent capability route should be queried');assert.equal(absentCapability.status,200);assert.equal(absentCapability.response.available,false);
  assert.equal(await page.locator('#assistant-agent-send').isHidden(),true,'control stays hidden when agent is absent');
  checkpoint('Absent agent capability keeps the new control hidden');

  await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  await page.locator('#assistant-text').fill('find photos containing beach');
  const ordinaryBefore=turns().length;await page.locator('#assistant-send').click();
  await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled&&document.querySelectorAll('#assistant-results .assistant-result').length>0);
  assert.equal(turns().length,ordinaryBefore+1);const ordinary=turns().at(-1);
  assert.equal(ordinary.status,200);assert.equal(JSON.parse(ordinary.body).accepts,undefined);
  let stats=await rpc({command:'agent-stats'});assert.equal(stats.calls,0,'ordinary Find must not invoke planner');
  checkpoint('Ordinary Find remains usable and does not call the agent provider');

  await rpc({command:'agent-enable'});await page.reload();await loginAndOpen();
  await page.waitForFunction(()=>document.querySelector('#assistant-agent-send')&&!document.querySelector('#assistant-agent-send').hidden);
  const capabilityReads=()=>requests.filter(item=>item.method==='GET'&&
    new URL(item.path,'https://photohouse.test').pathname==='/assistant/workspace/v1/agent-capabilities');
  await rpc({command:'agent-disable'});
  const disabledCapability=page.waitForResponse(r=>new URL(r.url()).pathname==='/assistant/workspace/v1/agent-capabilities'&&r.status()===200);
  disabledCapability.catch(()=>{});await page.reload();await loginAndOpen();await disabledCapability;
  assert.equal(capabilityReads().at(-1).response.available,false);
  assert.equal(await page.locator('#assistant-agent-send').isHidden(),true,'control stays hidden when supervisor is disabled');
  checkpoint('A present but disabled supervisor also keeps the new control hidden');

  await rpc({command:'agent-enable'});await page.reload();await loginAndOpen();
  await page.waitForFunction(()=>document.querySelector('#assistant-agent-send')&&!document.querySelector('#assistant-agent-send').hidden);
  if(!await page.locator('#assistant-private-select').inputValue()){
    await page.locator('#assistant-private-new').click();
    await page.waitForFunction(()=>document.querySelector('#assistant-private-select')?.value&&!document.querySelector('#assistant-private-new').disabled);
  }
  await page.locator('#assistant-text').fill('find photos containing beach');
  await page.screenshot({path:path.join(artifacts,'agent-control-phone-zh-390-150.png'),fullPage:false});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  assert.match(await page.locator('#assistant-agent-send').innerText(),/小贾查找/);

  // A real response is returned by the protected ASGI route, then deliberately
  // dropped at the browser boundary to exercise same-request GET recovery.
  const turnBefore=turns().length;loseNextAgentResponse=true;
  const failedRequest=page.waitForEvent('requestfailed',event=>event.method()==='POST'&&/\/threads\/[0-9a-f-]+\/turns$/.test(new URL(event.url()).pathname));
  await page.locator('#assistant-agent-send').click();await failedRequest;
  await page.locator('#assistant-private-management-toggle').click();
  await page.locator('#assistant-private-recover').waitFor({state:'visible'});
  assert.equal(turns().length,turnBefore+1);const agentTurn=turns().at(-1);
  assert.equal(agentTurn.status,200);assert.equal(agentTurn.headers['x-photohouse-search-version'],'2');
  assert.deepEqual(JSON.parse(agentTurn.body).accepts,['agent_media_search_v1']);
  const sent=JSON.parse(agentTurn.body),threadId=new URL(agentTurn.path,'https://photohouse.test').pathname.split('/')[5];
  await page.locator('#assistant-private-recover').click();
  await page.waitForFunction(()=>!document.querySelector('#assistant-private-new').disabled&&document.querySelectorAll('#assistant-results .assistant-result').length===2);
  const getPath=`/assistant/workspace/v1/threads/${threadId}/requests/${sent.request_id}?library_id=family-a`;
  const receiptGets=requests.filter(item=>item.method==='GET'&&item.path===getPath);
  assert.ok(receiptGets.length>0,'recovery should read this conversation/request');
  assert.ok(receiptGets.every(item=>item.headers['x-photohouse-search-version']==='2'));
  assert.equal(turns().length,turnBefore+1,'recovery must not send a second POST');
  assert.equal(await page.locator('#assistant-results .assistant-result').count(),agentTurn.response.result.items.length);
  assert.equal(agentTurn.response.result.kind,'results');assert.ok(agentTurn.response.result.total>0);
  stats=await rpc({command:'agent-stats'});assert.equal(stats.calls,4);assert.deepEqual(stats.tools,
    ['get_search_capabilities','search_media','inspect_current_results']);
  checkpoint('LocalToolAgentRuntime decisions drive protected Search; authorized results reopen by GET without another turn or generation');

  const languageCaps=page.waitForResponse(r=>new URL(r.url()).pathname==='/assistant/workspace/v1/capabilities'&&r.status()===200);languageCaps.catch(()=>{});
  await page.locator('#language').click();await languageCaps;
  await page.waitForFunction(()=>document.documentElement.lang==='en'&&!document.querySelector('#assistant-agent-send').hidden);
  await page.setViewportSize({width:390,height:845});
  await page.evaluate(()=>document.documentElement.style.fontSize='150%');
  await page.locator('#assistant-text').fill('find photos about beach');
  await page.locator('#assistant-agent-send').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(artifacts,'agent-control-phone-en-390-150.png'),fullPage:false});
  assert.match(await page.locator('#assistant-agent-send').innerText(),/Ask Jude/);
  assert.equal(await page.locator('#assistant-agent-send').isDisabled(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  checkpoint('Chinese and English 390px layouts at 150% text retain the explicit AI control without horizontal overflow');
  assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  fs.writeFileSync(path.join(artifacts,'result.json'),JSON.stringify({checkpoints:3,pageErrors:errors,blockedOrigins:blocked,
    syntheticDecisionProvider:true,localToolAgentRuntime:true,protectedAsgi:true},null,2));
  console.log(`Local agent browser checks: 3 passed. Artifacts: ${artifacts}`);
})().catch(async error=>{console.error(error);try{console.error(await page?.evaluate(()=>({agentHidden:document.querySelector('#assistant-agent-send')?.hidden,
  status:document.querySelector('#assistant-status')?.textContent,privateStatus:document.querySelector('#assistant-private-status')?.textContent,
  lang:document.documentElement.lang})));await page?.screenshot({path:path.join(artifacts,'failure.png'),fullPage:false});
  console.error(JSON.stringify(requests.slice(-8).map(item=>({method:item.method,path:item.path,status:item.status,response:item.response})),null,2));}catch{}process.exitCode=1;
}).finally(async()=>{await context?.close();await browser?.close();try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');}catch{}bridge.kill();});
