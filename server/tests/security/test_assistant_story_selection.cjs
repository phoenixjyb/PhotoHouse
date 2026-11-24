'use strict';
const assert=require('node:assert/strict');
const PrivateAssistant=require('../../backend/app/ui/access/assistant-private-workspace.js');

const library='family-a',threadId='11111111-1111-4111-8111-111111111111';
const ids=Array.from({length:26},(_,index)=>String(101+index));
const binding='a'.repeat(64),fingerprint='b'.repeat(64);
const interpretation={date_basis:'capture',people:[],tags:[],locations:[],perspective:null};
const media=ids.map((id,index)=>({id,kind:index===2?'other':index%2?'video':'image',width:640,height:480,
  duration_sec:index%2?12:null,taken_at:'2032-09-14T10:00:00Z',thumbnail_url:`/assets/${id}/thumbnail?library=${library}`}));
function result(){
  const filters={media:['image','video','other']};
  return {version:3,kind:'results',reply:'Found items.',context:{library_id:library,binding,fingerprint,
    filters,visible_ids:ids.slice(0,20),total:ids.length,search_version:3},filters,items:media.slice(0,20),total:ids.length,has_more:true,effect:null,interpretation};
}
function sceneResult(){
  const value=imageResult();value.version=4;value.items=value.items.map(item=>({...item,semantic_score:0.75}));
  const scope={...value.context};value.context.search_version=4;value.context.scene={version:1,query:'孩子 flying a kite 蓝桥旁',scope,scores:value.items.map(()=>0.75)};
  value.semantic={mode:'text_to_image',score_kind:'cosine',candidate_count:value.total,coverage:'complete_eligible_images',needs_review:true};
  return value;
}
function imageResult(){const value=result();value.filters.media=['image'];value.context.filters.media=['image'];value.items=value.items.map(item=>({...item,kind:'image'}));return value;}
function thread(revision){return {thread_id:threadId,library_id:library,created_at:'2026-10-16T00:00:00Z',
  updated_at:'2026-10-16T00:00:00Z',expires_at:'2026-11-15T00:00:00Z',revision};}
function envelope(requestId,revision,turn=result()){
  return {version:1,thread_id:threadId,request_id:requestId,status:'completed',revision,recovered:false,error:null,result:turn};
}
function caps(){return {version:1,available:true,threads:true,preferences:true,preferences_applied:true,
  server_owned_turns:true,search:{version:3,date_basis:'capture',perspective:null}};}
function error(status,code){return Object.assign(new Error(code),{status,code});}
function makeController({holdResult=false,denyResult=false,latestMismatch=false,denyCurrent=false,denyBaseCapabilities=false,resultPageCapabilityAvailable=true,sceneSetup=false}={}){
  const scope={account:'synthetic-account',library,generation:1,locked:false},calls=[];
  let counter=0,latestRequestId=null,latestRevision=0,holdResolve=null,held=null,capabilityCalls=0,pageCapabilityDenied=false,pageCapabilityAvailable=resultPageCapabilityAvailable;
  const uuid=()=>counter++===0?threadId:`22222222-2222-4222-8222-${String(counter).padStart(12,'0')}`;
  const request=async(path,options={})=>{
    calls.push({path,method:options.method,body:options.body});
    if(path.includes('/capabilities?')){capabilityCalls++;if(denyBaseCapabilities&&capabilityCalls>1)throw error(403,'access_denied');return caps();}
    if(path.includes('/scene-search-capabilities?'))return {version:1,available:true,search_version:4,media:['image']};
    if(path.includes('/scene-page-capabilities?'))return {version:1,available:true,page_size:20};
    if(path.includes('/result-page-capabilities?')){if(pageCapabilityDenied)throw error(403,'access_denied');return {version:1,available:pageCapabilityAvailable,page_size:20};}
    if(path===`/assistant/workspace/v1/threads`&&options.method==='POST')return {version:1,thread:thread(0)};
    if(path===`/assistant/workspace/v1/threads/${threadId}/turns`){
      latestRequestId=options.body.request_id;latestRevision=options.body.expected_revision+1;
      return envelope(latestRequestId,latestRevision,options.body.accepts?.includes('scene_search_v1')?sceneResult():sceneSetup?imageResult():result());
    }
    if(path.endsWith('/scene-pages')){
      const page=options.body.page,offset=(page-1)*20,items=media.slice(offset,offset+20).map(item=>({...item,kind:'image',semantic_score:0.75}));
      return {version:1,thread_id:threadId,request_id:latestRequestId,revision:latestRevision,page,page_size:20,total:ids.length,has_more:offset+20<ids.length,binding,fingerprint,ranking_sha256:'c'.repeat(64),items,semantic:{mode:'text_to_image',score_kind:'cosine',candidate_count:ids.length,coverage:'complete_eligible_images',needs_review:true}};
    }
    if(path.endsWith('/result-pages')){
      const page=options.body.page,offset=(page-1)*20;
      return {version:1,library_id:library,thread_id:threadId,request_id:latestRequestId,revision:latestRevision,
        search_version:3,binding,fingerprint,page,page_size:20,total:ids.length,has_more:offset+20<ids.length,items:media.slice(offset,offset+20)};
    }
    if(path.includes(`/requests/${latestRequestId}/current-result?`)){
      const requestedId=path.split('/requests/')[1].split('/')[0];
      if(denyCurrent)throw error(403,'access_denied');
      if(latestMismatch)throw error(409,'context_changed');
      if(denyResult)throw error(403,'access_denied');
      if(holdResult){holdResult=false;held=new Promise(resolve=>{holdResolve=resolve;});await held;}
      if(requestedId!==latestRequestId)throw error(409,'context_changed');
      return {...envelope(requestedId,latestRevision),recovered:true};
    }
    if(path.includes('/current-result?'))throw error(409,'context_changed');
    if(path.includes(`/requests/${latestRequestId}`)){
      if(denyResult)throw error(403,'access_denied');
      if(holdResult){holdResult=false;held=new Promise(resolve=>{holdResolve=resolve;});await held;}
      return {...envelope(path.split('/requests/')[1].split('?')[0],latestRevision),recovered:true};
    }
    if(path.startsWith(`/assistant/workspace/v1/threads/${threadId}?`)){
      return {version:1,thread:thread(latestRevision),exchanges:[],latest_request_id:latestMismatch?'33333333-3333-4333-8333-333333333333':latestRequestId};
    }
    throw new Error(`Unexpected synthetic request: ${options.method} ${path}`);
  };
  const controller=PrivateAssistant.createController({scope:()=>scope,request,newUUID:uuid});
  return {controller,scope,calls,release(){holdResolve?.();},setLatestMismatch(value){latestMismatch=value;},deny(){denyResult=true;},denyPageCapability(){pageCapabilityDenied=true;},disablePageCapability(){pageCapabilityAvailable=false;}};
}

(async()=>{
  {
    const {controller,calls}=makeController();
    await controller.capabilities();await controller.create();await controller.send('Find family photos and videos');
    assert.equal(controller.state().storySelectionReady,true,'a current result permits selection before anything is selected');
    controller.toggleStoryItem('101');controller.toggleStoryItem('102');
    assert.deepEqual(controller.state().storySelection.map(item=>item.id),['101','102'],'selection preserves user order');
    assert.throws(()=>controller.toggleStoryItem('103'),error=>error.code==='invalid_input','unsupported media cannot be selected');
    controller.toggleStoryItem('101');controller.toggleStoryItem('101');
    assert.deepEqual(controller.state().storySelection.map(item=>item.id),['102','101'],'duplicate toggles do not duplicate IDs');
    const prepared=await controller.prepareStorySelection();
    assert.deepEqual(prepared.map(item=>item.id),['102','101']);
    assert.equal(Object.isFrozen(prepared),true);assert.equal(Object.isFrozen(prepared[0]),true);
    assert.equal(calls.filter(call=>call.method==='POST'&&call.path.endsWith('/turns')).length,1,
      'preparation only reads the existing result; it does not create a turn');
    assert.equal(calls.some(call=>call.method==='GET'&&call.path.includes('/current-result?')),true,
      'preparation uses the latest-any-status current-result guard');
    assert.equal(calls.some(call=>call.method==='GET'&&call.path.includes(`/threads/${threadId}?`)),false,
      'freshness comes from one guarded read, not latest-completed thread metadata');
    controller.close();
  }
  {
    const {controller}=makeController();await controller.capabilities();await controller.create();await controller.send('First search');
    controller.toggleStoryItem('101');await controller.send('Refined search');
    assert.deepEqual(controller.state().storySelection,[],'a new/refined turn invalidates the prior selection');
    assert.equal(controller.state().storySelectionReady,true);
    controller.close();
  }
  {
    const fixture=makeController(),{controller,calls}=fixture;
    await controller.capabilities();await controller.resultPageCapabilities();await controller.create();
    await controller.send('Choose frames for a story');
    controller.toggleStoryItem('102');await controller.resultPage(2);controller.toggleStoryItem('121');
    controller.moveStoryItem('121',-1);
    const started=calls.length;
    await controller.read(threadId,{preserveStorySelection:true});
    assert.deepEqual(controller.state().storySelection.map(item=>item.id),['121','102'],
      'reloading the same current conversation retains the exact ordered selection');
    assert.equal(calls.slice(started).filter(call=>call.path.includes('/current-result?')).length,1);
    assert(calls.slice(started).every(call=>call.method==='GET'),'restoring the selection only reads the existing result');
    fixture.deny();
    await controller.read(threadId,{preserveStorySelection:true});
    assert.deepEqual(controller.state().storySelection,[],'unconfirmed result authority clears the old selection');
    controller.close();
  }
  {
    const {controller,calls}=makeController();await controller.capabilities();await controller.resultPageCapabilities();await controller.create();await controller.send('Choose story frames');
    controller.toggleStoryItem('101');controller.toggleStoryItem('102');await controller.resultPage(2);controller.toggleStoryItem('121');
    const before=controller.state().storySelection.slice(),callCount=calls.length;
    const moved=controller.moveStoryItem('121',-1);assert.equal(Object.isFrozen(moved),true);
    assert.deepEqual(moved.map(item=>item.id),['101','121','102']);
    controller.moveStoryItem('121',-1);controller.moveStoryItem('101',1);
    assert.deepEqual(controller.state().storySelection.map(item=>item.id),['121','102','101'],'off-page frames can move in both directions');
    for(const item of before)assert.strictEqual(controller.state().storySelection.find(frame=>frame.id===item.id),item,'movement preserves authorized media metadata');
    controller.moveStoryItem('121',-1);controller.moveStoryItem('101',1);
    assert.deepEqual(controller.state().storySelection.map(item=>item.id),['121','102','101'],'first and last boundaries are no-ops');
    assert.throws(()=>controller.moveStoryItem('126',-1),error=>error.code==='invalid_input','unselected media cannot be introduced by moving');
    for(const direction of [0,2,'1',null])assert.throws(()=>controller.moveStoryItem('121',direction),error=>error.code==='invalid_input');
    assert.equal(calls.length,callCount,'movement does not read, search, generate, or save');
    await controller.returnResults();
    assert.deepEqual((await controller.prepareStorySelection()).map(item=>item.id),['121','102','101'],'fresh handoff retains the deliberate cross-page order');
    controller.close();
  }
  {
    const fixture=makeController({holdResult:true}),{controller}=fixture;
    await controller.capabilities();await controller.create();await controller.send('Choose frames');controller.toggleStoryItem('101');controller.toggleStoryItem('102');
    const pending=controller.prepareStorySelection();await new Promise(resolve=>setImmediate(resolve));
    assert.throws(()=>controller.moveStoryItem('102',-1),error=>error.code==='conflict','movement cannot race the fresh editor handoff');
    fixture.release();assert.deepEqual((await pending).map(item=>item.id),['101','102']);controller.close();
  }
  {
    const {controller,calls}=makeController();await controller.capabilities();await controller.resultPageCapabilities();await controller.create();await controller.send('Find a long result set');
    for(const id of ids.slice(0,20))if(id!=='103')controller.toggleStoryItem(id);
    assert.equal(controller.state().storySelection.length,19);
    const page=await controller.resultPage(2);assert.equal(page.items.length,6);assert.equal(page.has_more,false);
    for(const item of page.items.slice(0,5))controller.toggleStoryItem(item.id);
    assert.equal(controller.state().storySelection.length,24);
    assert.throws(()=>controller.toggleStoryItem(page.items[5].id),error=>error.code==='invalid_input','the handoff remains capped at 24 unique media');
    controller.moveStoryItem(page.items[4].id,-1);
    assert.equal(controller.state().storySelection.length,24,'reordering does not change the selection cap');
    assert.throws(()=>controller.toggleStoryItem(page.items[5].id),error=>error.code==='invalid_input');
    controller.clearStorySelection();await controller.returnResults();
    for(const id of ids.slice(0,20))if(id!=='103')controller.toggleStoryItem(id);
    await controller.resultPage(2);for(const item of media.slice(20,25))controller.toggleStoryItem(item.id);
    assert.equal(controller.state().storySelection.length,24);
    await assert.rejects(controller.send('Refine while on page two'),error=>error.code==='conflict','a non-first page must be returned before refining');
    const selectedBeforeReturn=controller.state().storySelection.map(item=>item.id);
    const returned=await controller.returnResults();assert.equal(returned.current_result.items.length,20);
    assert.equal(controller.state().resultPageActive,false);assert.deepEqual(controller.state().storySelection.map(item=>item.id),selectedBeforeReturn,
      'returning to the first page preserves ordered choices from all pages');
    const prepared=await controller.prepareStorySelection();assert.equal(prepared.length,24);
    assert.equal(calls.filter(call=>call.method==='POST'&&call.path.endsWith('/turns')).length,1,
      'paging, return and preparation do not create assistant turns');
    assert.equal(calls.filter(call=>call.method==='POST'&&call.path.endsWith('/result-pages')).length,2);
    controller.close();
  }
  {
    const fixture=makeController(),{controller}=fixture;
    await controller.capabilities();await controller.resultPageCapabilities();await controller.create();await controller.send('Find a long result set');
    await controller.resultPage(2);assert.equal(controller.state().storySelection.length,0);
    fixture.denyPageCapability();
    assert.equal(await controller.resultPageCapabilities(),false);
    assert.equal(controller.state().resultPageActive,false,'an old-route optional 403 exits page mode');
    assert.equal(controller.state().currentResult,null,'stale page/result content is cleared when Return cannot be trusted');
    assert.equal(controller.state().storySelectionReady,false);
    controller.close();
  }
  {
    const fixture=makeController({sceneSetup:true,resultPageCapabilityAvailable:false}),{controller}=fixture;
    await controller.capabilities();await controller.sceneCapabilities();await controller.scenePageCapabilities();
    await controller.create();await controller.send('Find images');await controller.sendScene('孩子 flying a kite 蓝桥旁');await controller.scenePage(2);controller.toggleStoryItem(ids[20]);
    assert.deepEqual(controller.state().storySelection.map(item=>item.id),[ids[20]]);
    assert.equal(await controller.resultPageCapabilities(),false);
    assert.deepEqual(controller.state().storySelection.map(item=>item.id),[ids[20]],
      'ordinary paging capability loss does not prune a selection from semantic scene pages');
    assert.equal(controller.state().scenePageActive,true);
    controller.close();
  }
  {
    const fixture=makeController(),{controller}=fixture;
    await controller.capabilities();await controller.resultPageCapabilities();await controller.create();await controller.send('Find a long result set');
    controller.toggleStoryItem(ids[0]);await controller.resultPage(2);controller.toggleStoryItem(ids[20]);
    await controller.returnResults();assert.deepEqual(controller.state().storySelection.map(item=>item.id),[ids[0],ids[20]]);
    fixture.disablePageCapability();assert.equal(await controller.resultPageCapabilities(),false);
    assert.deepEqual(controller.state().storySelection.map(item=>item.id),[ids[0]],
      'loss of paging removes off-page choices while preserving valid first-page choices');
    controller.close();
  }
  {
    const {controller,setLatestMismatch}=makeController();await controller.capabilities();await controller.create();await controller.send('Find a photo');
    controller.toggleStoryItem('101');setLatestMismatch(true);
    await assert.rejects(controller.prepareStorySelection(),error=>error.code==='context_changed');
    assert.deepEqual(controller.state().storySelection,[],'a latest-request conflict clears the selection');
    assert.equal(controller.state().storySelectionReady,false,'a failed freshness check also revokes its result source');
    controller.close();
  }
  {
    const fixture=makeController({holdResult:true});const {controller}=fixture;
    await controller.capabilities();await controller.create();await controller.send('Find a photo');controller.toggleStoryItem('101');
    const pending=controller.prepareStorySelection();
    await new Promise(resolve=>setImmediate(resolve));
    controller.toggleStoryItem('101');fixture.release();
    await assert.rejects(pending,error=>error.code==='scope_changed','a selection change during readback suppresses the handoff');
    assert.deepEqual(controller.state().storySelection,[]);
    controller.close();
  }
  {
    const fixture=makeController({holdResult:true});const {controller}=fixture;
    await controller.capabilities();await controller.create();await controller.send('Original search');controller.toggleStoryItem('101');
    const pending=controller.prepareStorySelection();await new Promise(resolve=>setImmediate(resolve));
    await controller.send('New search');controller.toggleStoryItem('102');fixture.release();
    await assert.rejects(pending,error=>error.code==='context_changed');
    assert.deepEqual(controller.state().storySelection.map(item=>item.id),['102'],
      'an old readback cannot clear a newer search selection');
    controller.close();
  }
  {
    const fixture=makeController({denyResult:true,denyBaseCapabilities:true});const {controller}=fixture;
    await controller.capabilities();await controller.create();await controller.send('Find a photo');controller.toggleStoryItem('101');
    await assert.rejects(controller.prepareStorySelection(),error=>error.code==='access_denied');
    assert.deepEqual(controller.state().storySelection,[],'permission revocation clears selected media');
    assert.equal(controller.state().locked,true);
    controller.close();
  }
  {
    const fixture=makeController({denyCurrent:true});const {controller,calls}=fixture;
    await controller.capabilities();await controller.create();await controller.send('Find a photo');controller.toggleStoryItem('101');
    await assert.rejects(controller.prepareStorySelection(),error=>error.code==='unavailable',
      'an older API boundary 403 disables this optional handoff without treating membership as revoked');
    assert.equal(controller.state().locked,false);
    assert.deepEqual(controller.state().storySelection,[]);
    assert.equal(calls.filter(call=>call.path.includes('/capabilities?')).length,2,'the base capability route distinguishes old-route 403 from revoked membership');
    controller.close();
  }
  {
    const fixture=makeController({denyCurrent:true,denyBaseCapabilities:true});const {controller}=fixture;
    await controller.capabilities();await controller.create();await controller.send('Find a photo');controller.toggleStoryItem('101');
    await assert.rejects(controller.prepareStorySelection(),error=>error.code==='access_denied');
    assert.equal(controller.state().locked,true,'a real base capability 403 still revokes membership');
    controller.close();
  }
  {
    const fixture=makeController();const {controller,scope}=fixture;
    await controller.capabilities();await controller.create();await controller.send('Find a photo');controller.toggleStoryItem('101');
    scope.generation++;
    assert.deepEqual(controller.state().storySelection,[],'account/library generation changes clear selection');
    assert.equal(controller.state().storySelectionReady,false);
    controller.close();
  }
  {
    const fixture=makeController();const {controller,scope}=fixture;
    await controller.capabilities();await controller.create();await controller.send('Find a photo');controller.toggleStoryItem('101');
    scope.library='family-b';
    assert.throws(()=>controller.toggleStoryItem('101'),error=>error.code==='conflict',
      'a direct deselection synchronizes scope before returning any older-library selection');
    assert.deepEqual(controller.state().storySelection,[]);
    controller.close();
  }
  {
    const {controller,scope}=makeController();await controller.capabilities();await controller.create();await controller.send('Choose frames');controller.toggleStoryItem('101');controller.toggleStoryItem('102');
    scope.generation++;
    assert.throws(()=>controller.moveStoryItem('102',-1),error=>error.code==='conflict','movement rechecks account/library generation');
    assert.deepEqual(controller.state().storySelection,[]);controller.close();
  }
  console.log('Private assistant story selection checks: ordered items, eligibility, de-duplication, refinement, fresh latest-request readback, conflict, permission revocation and stale selection passed.');
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
