'use strict';
/* Optional cloud requires exact-preview consent through the real workspace UI. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
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

const {createHash}=require('node:crypto');
let browser,context,page,enabled=false,previewCount=0,sendCount=0,wire;
(async()=>{
 await ready;
 browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update','--no-first-run','--host-resolver-rules=MAP * ~NOTFOUND']});
 context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());assert.equal(url.origin,'https://photohouse.test');
  const headers=await request.allHeaders();delete headers['content-length'];if(!headers['sec-fetch-site'])headers['sec-fetch-site']='same-origin';
  const entry={method:request.method(),path:url.pathname+url.search};requests.push(entry);
  let status,headersOut,responseBody;
  if(url.pathname.endsWith('/proofreading/preview')){
   assert.equal(request.method(),'POST');previewCount++;
   wire=JSON.stringify({model:'synthetic-cloud',messages:[{role:'user',content:JSON.stringify({chapters:story.chapters.map(c=>({narration:c.narration}))})}]});
   responseBody=Buffer.from(JSON.stringify({schema:'photohouse.private.story_cloud_proofreading_preview.v1',preview_id:'5f79b251-a8fd-43b6-bfc2-d130b6055fb6',base_revision:story.revision,enabled,configured:enabled,provider:'DeepSeek',model:'synthetic-cloud',endpoint:'https://api.deepseek.com/chat/completions',request_body:wire,request_sha256:createHash('sha256').update(wire).digest('hex'),expires_in_seconds:600}));status=200;headersOut={'content-type':'application/json'};
  }else if(url.pathname.endsWith('/proofreading/confirm')){
   const b=JSON.parse(request.postData());assert.equal(b.confirmed,'yes');assert.equal(b.request_sha256,createHash('sha256').update(wire).digest('hex'));sendCount++;
   responseBody=Buffer.from(JSON.stringify({version:1,title:story.title,base_revision:story.revision,needs_review:true,saved:false,chapters:story.chapters.map(c=>({id:c.id,narration:c.narration?c.narration+' 云端校对建议，等待核对。':''}))}));status=200;headersOut={'content-type':'application/json'};
  }else{
   const result=await rpc({method:entry.method,path:entry.path,headers,body:(request.postDataBuffer()||Buffer.alloc(0)).toString('base64')});status=result.status;responseBody=Buffer.from(result.body,'base64');headersOut={...result.headers};
   if(request.method()==='GET'&&url.pathname==='/memory-stories/'+storyId&&status===200)story=JSON.parse(responseBody.toString());
  }
  delete headersOut['content-length'];delete headersOut['content-encoding'];await route.fulfill({status,headers:headersOut,body:responseBody});
 });
 page=await context.newPage();page.on('pageerror',error=>pageErrors.push(error.stack||error.message));page.on('dialog',dialog=>{void dialog.accept().catch(()=>{});});
 await page.goto('https://photohouse.test/ui');await page.locator('#auth').waitFor({state:'visible'});await page.locator('#phone').fill('+12025550100');await page.locator('#password').fill('Synthetic family passphrase!');await page.locator('#auth-submit').click();await page.locator('#grid .asset').first().waitFor();
 await page.locator('.saved-memory-cover').first().click();const panel=page.locator('#story-reader details.story-cloud-review');await panel.waitFor();assert.equal(await panel.evaluate(node=>node.open),false,'cloud review starts collapsed');assert.equal(sendCount,0);assert.equal(previewCount,0,'opening story never builds or sends cloud request');
 await panel.locator(':scope > summary').click();assert.equal(await panel.evaluate(node=>node.open),true,'opening the cloud review is a separate user action');
 await panel.getByRole('button',{name:'预览发送内容'}).click();await panel.locator('pre').waitFor();assert.equal(await panel.locator('pre').textContent(),wire);assert.match(await panel.textContent(),/当前只可预览/);assert.equal(await panel.getByRole('checkbox').isChecked(),false);assert.equal(await panel.getByRole('checkbox').isDisabled(),true);assert.equal(sendCount,0);
 await panel.getByRole('button',{name:'关闭预览'}).click();assert.equal(await panel.locator('pre').count(),0);enabled=true;
 await panel.getByRole('button',{name:'预览发送内容'}).click();await panel.locator('pre').waitFor();assert.equal(await panel.getByRole('checkbox').isChecked(),false);assert.equal(await panel.getByRole('button',{name:'确认发送这份请求'}).isDisabled(),true);
 await page.screenshot({path:process.env.PH_CLOUD_SCREENSHOT_DIR+'/story-cloud-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:process.env.PH_CLOUD_SCREENSHOT_DIR+'/story-cloud-mobile.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.querySelector('#story-reader').scrollWidth>document.querySelector('#story-reader').clientWidth+2),false,'mobile dialog has no horizontal overflow');
 await panel.getByRole('checkbox').check();await panel.getByRole('button',{name:'确认发送这份请求'}).click();await panel.getByText('云端建议 · 尚未保存').waitFor();assert.equal(sendCount,1);assert.match(await panel.textContent(),/云端校对建议/);assert.equal(await panel.getByRole('button',{name:'确认发送这份请求'}).isDisabled(),true);
 assert.equal(requests.filter(r=>r.method==='PUT'&&r.path.startsWith('/memory-stories/')).length,0,'cloud result never autosaves');
 await panel.getByRole('button',{name:'将建议带入编辑'}).click();await page.locator('#story-workspace').waitFor({state:'visible'});assert.match(await page.locator('#story-chapter-editor textarea').first().inputValue(),/云端校对建议/);assert.equal(requests.filter(r=>r.method==='PUT'&&r.path.startsWith('/memory-stories/')).length,0,'adoption remains unsaved');assert.deepEqual(pageErrors,[]);
 console.log('PASS optional cloud default-off preview, exact body, unchecked consent, one send, review-only adoption, desktop/mobile layout');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{try{await context?.close();await browser?.close();}finally{if(bridge&&!bridge.killed){bridge.stdin.end();bridge.kill();}}});
