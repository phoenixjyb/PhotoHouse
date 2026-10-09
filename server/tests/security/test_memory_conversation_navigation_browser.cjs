'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||process.env.PLAYWRIGHT_MODULE_PATH||'playwright-core');

const storyId='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const newest='11111111-1111-4111-8111-111111111111';
const older='22222222-2222-4222-8222-222222222222';
const targetStory=(revision,id=storyId)=>({type:'story',id,revision:String(revision),title:'Synthetic story',language:'zh',selection_revision:'a'.repeat(64),can_edit:false,chapters:[{id:'chapter-1',title:'Chapter',asset_ids:['1'],evidence_ids:[]}]});

(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.PH_BROWSER_EXECUTABLE?{executablePath:process.env.PH_BROWSER_EXECUTABLE}:{})});
  try{
    const page=await browser.newPage();await page.setContent('<!doctype html><html><body><main id="mount"></main></body></html>');
    const artifacts=process.env.PH_BROWSER_ARTIFACTS||fs.mkdtempSync(path.join(os.tmpdir(),'photohouse-memory-navigation-'));fs.mkdirSync(artifacts,{recursive:true});
    const externalRequests=[],pageErrors=[];page.on('request',request=>{if(/^https?:/.test(request.url()))externalRequests.push(request.url());});page.on('pageerror',error=>pageErrors.push(error.message));
    await page.addStyleTag({content:fs.readFileSync(path.resolve(__dirname,'../../backend/app/ui/access/styles.css'),'utf8')});
    await page.evaluate(()=>{window.__storageWrites=[];for(const name of ['localStorage','sessionStorage'])Object.defineProperty(window,name,{configurable:true,value:{setItem(key,value){window.__storageWrites.push({name,key,value:String(value)});},getItem(){return null;},removeItem(){},clear(){}}});});
    await page.addScriptTag({path:path.resolve(__dirname,'../../backend/app/ui/access/memory-community.js')});
    const setup=async({kind='story',membershipRevision=3,target=targetStory(1),listItems=null}={})=>page.evaluate(({kind,membershipRevision,target,newest,older,listItems})=>{
      const host=document.querySelector('#mount');host.replaceChildren();document.querySelectorAll('#book-mount').forEach(node=>node.remove());const bookHost=document.createElement('div');bookHost.id='book-mount';document.body.append(bookHost);const scope={account:'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',library:'synthetic-library',membership_revision:membershipRevision,language:'zh',locked:false};
      const calls=[],list=listItems||[{id:newest,created_at:100,expires_at:2000000000,first_message_preview:'Newest thread'},{id:older,created_at:90,expires_at:2000000000,first_message_preview:'Older thread'}];let failTurnsFor=null,holdList=false,holdTurn=null,denyNext=null,holdDenial=false;
      const ui=window.PhotoHouseMemoryCommunity({scope,request:async(path,options={})=>{
        calls.push({path,method:options.method||'GET',body:options.body});
        if(denyNext&&path.includes(denyNext.path)){const denied=denyNext;denyNext=null;const error=new Error('synthetic access denial');error.status=denied.status;if(holdDenial){holdDenial=false;return new Promise((resolve,reject)=>window.__navigation.releaseDenial=()=>reject(error));}throw error;}
        if(path.endsWith('/capabilities'))return {version:1,enabled:true,contributions_enabled:false,generation_enabled:true};
        if(path==='/memory-community/v1/books?page=1')return {version:1,library_id:'synthetic-library',page:1,page_size:8,has_more:false,can_create:false,items:[]};
        if(path.includes('/conversations?')){const response={version:1,items:list.slice()};if(holdList){holdList=false;return new Promise(resolve=>window.__navigation.releaseList=()=>resolve(response));}return response;}
        const match=path.match(/\/conversations\/([0-9a-f-]+)\/turns\?/);if(match){if(match[1]===failTurnsFor)throw new Error('synthetic turn read failure');const response={version:1,id:match[1],page:1,has_more:false,items:[{id:`turn-${match[1]}`,sequence:1,state:'ready',input_text:`History for ${match[1]}`,reply_text:'Synthetic reply'}]};if(match[1]===holdTurn)return new Promise(resolve=>window.__navigation.releaseTurn=()=>resolve(response));return response;}
        throw new Error(`Unexpected synthetic request: ${path}`);
      }});
      const activeTarget=kind==='memoir'?{type:'memoir',id:target.id,revision:target.revision,title:target.title,stories:target.stories}:target;
      window.__navigation={host,bookHost,scope,calls,list,ui,target:activeTarget,setTurnFailure(id){failTurnsFor=id;},holdList(){holdList=true;},holdTurn(id){holdTurn=id;},deny(path,status=403){denyNext={path,status};},holdDenial(){holdDenial=true;}};return true;
    },{kind,membershipRevision,target,newest,older,listItems});
    const openChat=async()=>{await page.locator('#mount [role="tab"]').filter({hasText:'一起聊回忆'}).click();};
    const waitReady=async()=>page.locator('#mount .memory-chat-conversation-select').waitFor();
    const detachAttach=async(target)=>{await page.evaluate(next=>{const n=window.__navigation;n.ui.detach(n.host);n.target=next||n.target;},target||null);await page.evaluate(async()=>{const n=window.__navigation;await n.ui.attach(n.host,n.target);});};

    await setup();await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();
    const select=page.locator('#mount .memory-chat-conversation-select');assert.equal(await select.inputValue(),newest,'initial authorized initialization uses the newest listed conversation');
    await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await page.locator('#mount textarea[name="message"]').fill('PRIVATE UNSENT CHAT DRAFT');
    assert.equal(await page.evaluate(()=>window.__navigation.calls.some(call=>call.method==='POST')),false,'selecting history and editing the composer make no writes');
    await detachAttach();await openChat();await waitReady();await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    assert.equal(await select.inputValue(),older,'a previously selected older thread restores from the fresh authorized list');
    assert.equal(await page.locator('#mount textarea[name="message"]').inputValue(),'','conversation restoration leaves the composer empty');
    assert.match(await page.locator('#mount [role="status"]').allTextContents().then(values=>values.join(' ')),/已回到上次选择的对话。/,'restoration notice appears only after the fresh turn read');
    assert.equal(await page.evaluate(()=>window.__storageWrites.length),0,'conversation restoration writes no local or session storage');
    assert.equal(await page.evaluate(()=>window.__navigation.calls.some(call=>call.method==='POST')),false,'conversation restoration sends no command, reply, or message');
    await page.setViewportSize({width:390,height:844});await page.locator('#mount').scrollIntoViewIfNeeded();
    const zhLayout=await page.locator('#mount .memory-chat-conversations').evaluate(root=>{for(const node of [root,...root.querySelectorAll('*')]){const style=getComputedStyle(node),font=parseFloat(style.fontSize),line=parseFloat(style.lineHeight);node.style.fontSize=`${font*1.5}px`;if(Number.isFinite(line))node.style.lineHeight=`${line*1.5}px`;}return {overflow:root.scrollWidth>root.clientWidth+1,documentOverflow:document.documentElement.scrollWidth>390};});
    assert.equal(zhLayout.overflow,false,'Chinese conversation controls fit at 390px/150% with the application stylesheet');assert.equal(zhLayout.documentOverflow,false,'Chinese page fits at 390px/150% with the application stylesheet');await page.screenshot({path:path.join(artifacts,'conversation-restore-zh-390px-text150.png'),fullPage:true});
    await page.evaluate(()=>{window.__navigation.scope.language='en';return window.__navigation.ui.translate();});await page.locator('#mount .memory-chat-conversation-select').waitFor();
    assert.match(await page.locator('#mount [role="status"]').allTextContents().then(values=>values.join(' ')),/Returned to the conversation you last selected\./,'the restoration notice follows the active language');
    const enLayout=await page.locator('#mount .memory-chat-conversations').evaluate(root=>{for(const node of [root,...root.querySelectorAll('*')]){const style=getComputedStyle(node),font=parseFloat(style.fontSize),line=parseFloat(style.lineHeight);node.style.fontSize=`${font*1.5}px`;if(Number.isFinite(line))node.style.lineHeight=`${line*1.5}px`;}return {overflow:root.scrollWidth>root.clientWidth+1,documentOverflow:document.documentElement.scrollWidth>390};});
    assert.equal(enLayout.overflow,false,'English conversation controls fit at 390px/150% with the application stylesheet');assert.equal(enLayout.documentOverflow,false,'English page fits at 390px/150% with the application stylesheet');await page.screenshot({path:path.join(artifacts,'conversation-restore-en-390px-text150.png'),fullPage:true});await page.evaluate(()=>{window.__navigation.scope.language='zh';return window.__navigation.ui.translate();});await page.setViewportSize({width:1280,height:900});
    console.log('PASS selected old thread restores after a fresh list and turn read; draft remains empty with no storage or write');

    await setup();await page.evaluate(async()=>{const n=window.__navigation;await n.ui.attach(n.host,n.target);await n.ui.books(n.bookHost);});
    assert.equal(await page.evaluate(()=>window.__navigation.calls.some(call=>call.path==='/memory-community/v1/books?page=1')),true,'book directory loads while a story reader with membership revision 3 is attached');
    assert.equal(await page.locator('#book-mount .memory-community-books-heading').textContent(),'家庭回忆录','book response is accepted alongside the attached reader');
    await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    console.log('PASS valid membership revision permits book directory reads while a story reader is attached');

    for(const change of ['membership','targetRevision']){
      const newTarget=change==='targetRevision'?targetStory(2):undefined;
      if(change==='membership')await page.evaluate(()=>window.__navigation.scope.membership_revision++);
      await detachAttach(newTarget);await openChat();await waitReady();
      assert.equal(await select.inputValue(),newest,`${change} change falls back to the newest authorized thread`);
      await page.evaluate(()=>window.__navigation.ui.clear());
      await page.evaluate(async next=>{const n=window.__navigation;n.host.replaceChildren();await n.ui.attach(n.host,next||n.target);},newTarget||null);
      await openChat();await waitReady();
    }
    await setup();await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await detachAttach({...targetStory(1),id:'ffffffff-ffff-4fff-8fff-ffffffffffff'});await openChat();await waitReady();assert.equal(await select.inputValue(),newest,'a target ID change changes the restoration scope');
    await setup();await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await page.evaluate(()=>window.__navigation.scope.membership_revision=null);await detachAttach();await openChat();await waitReady();assert.equal(await select.inputValue(),newest,'missing usable membership revision disables restoration');
    console.log('PASS membership, target ID, target revision, and missing membership revision use safe fallback');

    const bookId='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';const memoir=stories=>({type:'memoir',id:bookId,revision:'4',title:'Synthetic memoir',stories});
    const children=[{id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',revision:'1'},{id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd',revision:'2'}];
    await setup({kind:'memoir',target:memoir(children)});await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await detachAttach(memoir([children[1],children[0]]));await openChat();await waitReady();assert.equal(await select.inputValue(),newest,'reordering memoir children changes the restoration scope');
    await page.evaluate(()=>window.__navigation.ui.clear());await page.evaluate(async target=>window.__navigation.ui.attach(window.__navigation.host,target),memoir(children));await openChat();await waitReady();
    await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await detachAttach(memoir([{...children[0],revision:'3'},children[1]]));await openChat();await waitReady();assert.equal(await select.inputValue(),newest,'changing a memoir child revision changes the restoration scope');
    console.log('PASS memoir child order and revisions invalidate the remembered selection');

    await setup();await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await page.evaluate(()=>{window.__navigation.list.splice(1,1);window.__navigation.ui.detach(window.__navigation.host);});
    const turnCountBefore=await page.evaluate(()=>window.__navigation.calls.filter(call=>call.path.includes('/turns?')).length);
    await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();
    assert.equal(await select.inputValue(),newest,'an expired or omitted conversation falls back to a currently listed thread');
    assert.equal(await page.evaluate(()=>window.__navigation.calls.filter(call=>call.path.includes(`/conversations/${'22222222-2222-4222-8222-222222222222'}/turns?`)).length),1,'a missing ID never triggers another stale turn-history read');
    assert.equal(await page.evaluate(()=>window.__navigation.calls.filter(call=>call.path.includes('/turns?')).length),turnCountBefore+1,'only the selected fresh list item is loaded');
    console.log('PASS missing conversation ID falls back without a stale turn request');

    await setup();await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await page.evaluate(()=>{window.__navigation.setTurnFailure('22222222-2222-4222-8222-222222222222');window.__navigation.ui.detach(window.__navigation.host);});
    await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();
    assert.doesNotMatch(await page.locator('#mount').innerText(),/已回到上次选择的对话。|Returned to the conversation you last selected\./,'a failed fresh turn read never claims restoration');
    await page.evaluate(()=>window.__navigation.ui.clear());await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();
    assert.equal(await select.inputValue(),newest,'whole clear invalidates the previous thread hint');
    console.log('PASS failed turn load shows no restoration claim; whole clear drops the hint');

    for(const deniedPath of ['/conversations?','/conversations/22222222-2222-4222-8222-222222222222/turns?'])for(const status of [401,403]){
      await setup();await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
      await page.evaluate(({path,status})=>{const n=window.__navigation;n.ui.detach(n.host);n.deny(path,status);},{path:deniedPath,status});
      await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();
      assert.doesNotMatch(await page.locator('#mount').innerText(),/已回到上次选择的对话。|Returned to the conversation you last selected\./,'403 never leaves a false restoration notice');
      await page.evaluate(()=>window.__navigation.ui.detach(window.__navigation.host));await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();
      assert.equal(await select.inputValue(),newest,`${status} ${deniedPath.includes('/turns?')?'denied history':'denied directory'} clears the old hint independently of onError`);
    }
    console.log('PASS 401/403 directory and history denials clear matching hints before successful reattach');

    await setup();await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await page.evaluate(()=>{const n=window.__navigation;n.ui.detach(n.host);n.deny('/conversations?',403);n.holdDenial();n.oldDeniedAttach=n.ui.attach(n.host,n.target);});await page.waitForFunction(()=>typeof window.__navigation.releaseDenial==='function');
    await page.evaluate(()=>{const n=window.__navigation;n.scope.membership_revision=4;});await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await page.evaluate(()=>window.__navigation.releaseDenial());await page.evaluate(async()=>window.__navigation.oldDeniedAttach);await page.evaluate(()=>window.__navigation.ui.detach(window.__navigation.host));await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();
    assert.equal(await select.inputValue(),older,'a late old-revision denial cannot clear the newer revision hint');
    console.log('PASS late access denial cannot clear a newer active membership selection');

    await setup();await page.evaluate(()=>{const n=window.__navigation,stale={id:'33333333-3333-4333-8333-333333333333',created_at:80,expires_at:2000000000,first_message_preview:'Stale membership preview'};n.list.splice(0,n.list.length,stale);n.holdList();n.staleAttach=n.ui.attach(n.host,n.target);});
    await page.waitForFunction(()=>typeof window.__navigation.releaseList==='function');
    await page.evaluate(()=>{const n=window.__navigation;n.list.splice(0,n.list.length,{id:'11111111-1111-4111-8111-111111111111',created_at:100,expires_at:2000000000,first_message_preview:'Newest thread'},{id:'22222222-2222-4222-8222-222222222222',created_at:90,expires_at:2000000000,first_message_preview:'Older thread'});n.scope.membership_revision++;});
    await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));
    await page.evaluate(()=>window.__navigation.releaseList());await page.evaluate(async()=>window.__navigation.staleAttach);
    await openChat();await waitReady();assert.equal(await select.inputValue(),newest,'same-target membership change reattaches before any stale list selection');
    assert.doesNotMatch(await page.locator('#mount').innerText(),/Stale membership preview|History for 33333333/,'late list response cannot expose stale preview or history');
    assert.equal(await page.evaluate(()=>window.__navigation.calls.filter(call=>call.path.includes('/turns?')).length),1,'late list response cannot trigger a stale turn read');
    console.log('PASS delayed list from an old membership is discarded before conversation state changes');

    await setup();await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await page.evaluate(()=>{const n=window.__navigation;n.ui.detach(n.host);n.holdTurn('22222222-2222-4222-8222-222222222222');n.staleAttach=n.ui.attach(n.host,n.target);});await page.waitForFunction(()=>typeof window.__navigation.releaseTurn==='function');
    await page.evaluate(()=>window.__navigation.scope.membership_revision++);await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));
    await page.evaluate(()=>window.__navigation.releaseTurn());await page.evaluate(async()=>window.__navigation.staleAttach);await openChat();await waitReady();
    assert.equal(await select.inputValue(),newest,'same-target membership change discards the remembered ID before a pending turn read returns');
    assert.doesNotMatch(await page.locator('#mount').innerText(),/History for 22222222|已回到上次选择的对话/,'late turn response adds no old message and no restoration notice');
    console.log('PASS delayed history from an old membership is discarded before turns are installed');

    for(const change of ['account','library','locked','membership-null-valid','membership-valid-null']){
      await setup({membershipRevision:change==='membership-null-valid'?null:3});await page.evaluate(()=>{const n=window.__navigation;n.holdList();n.staleAttach=n.ui.attach(n.host,n.target);});await page.waitForFunction(()=>typeof window.__navigation.releaseList==='function');
      await page.evaluate(value=>{const n=window.__navigation;if(value==='account')n.scope.account='99999999-9999-4999-8999-999999999999';if(value==='library')n.scope.library='other-library';if(value==='locked')n.scope.locked=true;if(value==='membership-null-valid')n.scope.membership_revision=4;if(value==='membership-valid-null')n.scope.membership_revision=null;n.releaseList();},change);
      await page.evaluate(async()=>window.__navigation.staleAttach);
      assert.doesNotMatch(await page.locator('#mount').innerText(),/History for 11111111|History for 22222222|Returned to the conversation|已回到上次选择的对话/ ,`${change} change rejects delayed list and history output`);
      assert.equal(await page.evaluate(()=>window.__navigation.calls.filter(call=>call.path.includes('/turns?')).length),0,`${change} change stops before history is requested`);
      console.log(`PASS delayed list response is fenced after ${change} changes`);

      await setup({membershipRevision:change==='membership-null-valid'?null:3});await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
      await page.evaluate(value=>{const n=window.__navigation;n.ui.detach(n.host);n.holdTurn(value==='membership-null-valid'?'11111111-1111-4111-8111-111111111111':'22222222-2222-4222-8222-222222222222');n.staleAttach=n.ui.attach(n.host,n.target);},change);await page.waitForFunction(()=>typeof window.__navigation.releaseTurn==='function');
      await page.evaluate(value=>{const n=window.__navigation;if(value==='account')n.scope.account='99999999-9999-4999-8999-999999999999';if(value==='library')n.scope.library='other-library';if(value==='locked')n.scope.locked=true;if(value==='membership-null-valid')n.scope.membership_revision=4;if(value==='membership-valid-null')n.scope.membership_revision=null;n.releaseTurn();},change);await page.evaluate(async()=>window.__navigation.staleAttach);
      assert.doesNotMatch(await page.locator('#mount').innerText(),/History for 22222222|Returned to the conversation|已回到上次选择的对话/ ,`${change} change rejects a delayed private turn page`);
      console.log(`PASS delayed turn history is fenced after ${change} changes`);
    }

    await setup({listItems:[{id:'invalid-id',created_at:10,expires_at:20,first_message_preview:'invalid'}]});await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));
    assert.equal(await page.evaluate(()=>window.__navigation.calls.filter(call=>call.path.includes('/turns?')).length),0,'invalid authorized-list data cannot request turn history');
    assert.doesNotMatch(await page.locator('#mount').innerText(),/invalid/,'invalid list data never reaches visible conversation content');
    console.log('PASS malformed conversation list is refused without a turn request or visible content');

    await setup();await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    for(let index=0;index<16;index++){
      const id=`${String(index+1).padStart(8,'0')}-aaaa-4aaa-8aaa-aaaaaaaaaaaa`;
      await page.evaluate(async next=>{const n=window.__navigation;await n.ui.attach(n.host,next);},targetStory(1,id));
    }
    await page.evaluate(async target=>window.__navigation.ui.attach(window.__navigation.host,target),targetStory(1));await openChat();await waitReady();
    assert.equal(await select.inputValue(),newest,'the oldest hint is evicted when the process-memory cap of 16 is exceeded');
    console.log('PASS conversation hint map evicts beyond 16 scope entries');

    const memoirTarget={type:'memoir',id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',revision:'4',title:'Synthetic memoir',stories:[{id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',revision:'1'},{id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd',revision:'2'}]};
    await setup({kind:'memoir',target:memoirTarget});await page.evaluate(async()=>window.__navigation.ui.attach(window.__navigation.host,window.__navigation.target));await openChat();await waitReady();await select.selectOption(older);await page.locator('#mount .memory-chat-turn').filter({hasText:`History for ${older}`}).waitFor();
    await detachAttach();await openChat();await waitReady();assert.equal(await select.inputValue(),older,'memoir conversation restores within unchanged ordered child scope');
    assert.match(await page.locator('#mount [role="status"]').allTextContents().then(values=>values.join(' ')),/已回到上次选择的对话。/,'memoir restoration notice follows successful authorized turn loading');
    console.log('PASS authorized memoir conversation restores with the ordered child scope');
    assert.deepEqual(externalRequests,[],'browser journey makes zero external requests');assert.deepEqual(pageErrors,[],'browser journey has zero page errors');
    console.log('PASS zero external requests and zero page errors');console.log(`ARTIFACTS ${artifacts}`);
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
