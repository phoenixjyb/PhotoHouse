'use strict';
/* Actual-ASGI browser check for immutable uncertain retries and explicit narrative recovery. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');
const root=path.resolve(__dirname,'../..');
const python=process.env.PH_BROWSER_PYTHON||path.join(root,'.venv/bin/python');
const bridge=spawn(python,[path.join(__dirname,'memory_community_browser_bridge.py')],{cwd:root,stdio:['pipe','pipe','pipe']});
let serial=0,readyResolve,readyReject,storyId,browser,context,page,uncertainOnce=false,queuedOnce=false,terminalJob=null,posts=[];
const pending=new Map(),failures=[];
const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
bridge.stderr.on('data',chunk=>process.stderr.write(chunk));
createInterface({input:bridge.stdout}).on('line',line=>{const result=JSON.parse(line);if(result.ready){storyId=result.story_id;readyResolve();return;}const call=pending.get(result.id);if(call){pending.delete(result.id);call.resolve(result);}});
bridge.on('exit',code=>{if(code){readyReject(new Error(`Community bridge failed (${code})`));for(const call of pending.values())call.reject(new Error('Community bridge failed'));}});
const rpc=message=>new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});bridge.stdin.write(JSON.stringify({...message,id})+'\n');});
const pass=message=>console.log('PASS '+message);

(async()=>{
  await ready;
  browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
  context=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block'});
  await context.addInitScript(()=>{let Wrapped;Object.defineProperty(window,'PhotoHouseMemoryCommunity',{configurable:true,get:()=>Wrapped,set:value=>{Wrapped=config=>{let language=null;const originalScope=config.scope,originalRequest=config.request;const instance=value({...config,scope:()=>({...((typeof originalScope==='function'?originalScope():originalScope)||{}),...(language?{language}:{})}),request:originalRequest});window.__memoryCommunityForTest=instance;window.__translateCommunityForTest=next=>{language=next;return instance.translate();};return instance;};}});});
  await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='https://photohouse.test'){await route.abort();return;}
    const headers=await request.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
    const method=request.method(),body=request.postDataBuffer()||Buffer.alloc(0);
    const result=await rpc({method,path:url.pathname+url.search,headers,body:body.toString('base64')});
    let responseBody=Buffer.from(result.body,'base64'),status=result.status;
    if(method==='POST'&&url.pathname==='/memory-community/v1/jobs'){
      const payload=JSON.parse(body.toString());posts.push(payload);
      if(uncertainOnce){uncertainOnce=false;status=503;responseBody=Buffer.from(JSON.stringify({detail:'Synthetic uncertain response'}));}
      else if(queuedOnce){queuedOnce=false;const accepted=JSON.parse(responseBody.toString());accepted.state='queued';accepted.result=null;terminalJob={id:accepted.id,state:'queued'};responseBody=Buffer.from(JSON.stringify(accepted));}
      else if(posts.length===3){await rpc({command:'worker-job'});}
    }
    if(method==='GET'&&/^\/memory-community\/v1\/jobs\/[0-9a-f-]+$/.test(url.pathname)&&terminalJob?.id===url.pathname.split('/').at(-1)){
      const job=JSON.parse(responseBody.toString());job.state=terminalJob.state;job.result=null;
      if(job.state==='failed'){job.error_code='synthetic_failure';terminalJob=null;}else terminalJob={...terminalJob,state:'failed'};
      responseBody=Buffer.from(JSON.stringify(job));
    }
    const responseHeaders={...result.headers};delete responseHeaders['content-length'];delete responseHeaders['content-encoding'];
    try{await route.fulfill({status,headers:responseHeaders,body:responseBody});}catch(error){if(!/closed|handled|cancel|Invalid InterceptionId/.test(error.message))throw error;}
  });
  page=await context.newPage();page.on('pageerror',error=>failures.push(error.stack||error.message));
  await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('.saved-memory-cover').first().waitFor();
  await page.locator('.saved-memory-cover').first().click();await page.locator('#story-reader-community .memory-community[data-state=ready]').waitFor();
  await page.locator('#story-reader-community .memory-story-drafting-open').click();const instructions=page.locator('#story-reader-community textarea[name=instructions]');await instructions.waitFor();
  const exact='保留家人的说法，并把时间线整理清楚。';await instructions.fill(exact);uncertainOnce=true;
  await page.getByRole('button',{name:'生成待核实建议'}).click();await page.getByRole('button',{name:'重试同一份建议请求'}).waitFor();assert.equal(posts.length,1);assert.equal(posts[0].instructions,exact);
  queuedOnce=true;await page.getByRole('button',{name:'重试同一份建议请求'}).click();await page.locator('.memory-community-job-status').filter({hasText:'已排队'}).waitFor();
  assert.equal(await instructions.inputValue(),exact,'accepted queued job retains the exact instructions visibly');assert.equal(await instructions.isDisabled(),true,'queued attempt prevents duplicate submission and editing');
  await page.getByRole('button',{name:'用这段说明重新生成'}).waitFor({timeout:10000});assert.equal(posts.length,2);assert.equal(posts[1].mutation_id,posts[0].mutation_id,'uncertain confirmation retry reuses the exact mutation');assert.deepEqual(posts[1],posts[0],'uncertain confirmation retry resends the immutable payload');
  assert.equal(await instructions.inputValue(),exact,'terminal failure restores the exact wording');assert.equal(await page.locator('.memory-community-job-status').innerText(),'整理暂未完成');
  await instructions.fill('');await page.evaluate(()=>window.__translateCommunityForTest('en'));await page.waitForFunction(()=>document.querySelector('#story-reader-community textarea[name="instructions"]')?.isConnected);assert.equal(await page.locator('#story-reader-community textarea[name=instructions]').inputValue(),'','clearing a failed attempt remains an intentional edit after translation rerender');
  await page.evaluate(()=>window.__translateCommunityForTest('zh'));await page.waitForFunction(()=>document.querySelector('#story-reader-community textarea[name="instructions"]')?.isConnected);assert.equal(await page.locator('#story-reader-community textarea[name=instructions]').inputValue(),'','terminal wording is restored only once, not on every render');await page.locator('#story-reader-community textarea[name=instructions]').fill(exact);
  const before=await rpc({command:'state'});await page.getByRole('button',{name:'用这段说明重新生成'}).click();await page.locator('#story-reader-community .memory-community-proposal').filter({hasText:'需要核对的家庭回忆建议'}).waitFor({timeout:10000});
  assert.equal(posts.length,3);assert.notEqual(posts[2].mutation_id,posts[0].mutation_id,'deliberate new attempt receives a new mutation id');assert.equal(posts[2].instructions,exact,'deliberate new attempt retains the exact author wording');
  const after=await rpc({command:'state'});assert.equal(after.state.story_revision,before.state.story_revision,'new proposal does not save a story revision');assert.equal(after.state.story_content,before.state.story_content,'new proposal leaves saved prose unchanged');
  assert.deepEqual(failures,[],'actual-ASGI recovery flow has no browser errors');pass('Uncertain retry reuses an immutable request; queued and failed states retain instructions; a deliberate new attempt uses a new mutation without saving');
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;}).finally(async()=>{try{await context?.close();}catch(_){}try{await browser?.close();}catch(_){}try{bridge.stdin.write(JSON.stringify({command:'quit'})+'\n');bridge.kill();}catch(_){}});
