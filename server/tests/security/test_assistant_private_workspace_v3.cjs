'use strict';
const assert=require('node:assert/strict');
const PrivateAssistant=require('../../backend/app/ui/access/assistant-private-workspace.js');

const library='family-a';
const threadId='11111111-1111-4111-8111-111111111111';
const requestId='22222222-2222-4222-8222-222222222222';
const speechId='33333333-3333-4333-8333-333333333333';
const binding='a'.repeat(64),fingerprint='b'.repeat(64);
const filters={media:['image'],descriptive:{version:1,concepts:[{surface:'孩子在海边玩耍',alternatives:['孩子在海边玩耍','儿童在海边玩']},{surface:'夕阳',alternatives:['孩子在海边玩耍','夕阳','日落']}]}};
const interpretation={date_basis:'capture',people:[],tags:[],locations:[],perspective:null};
const item={id:'101',kind:'image',width:640,height:480,duration_sec:null,taken_at:'2032-09-14T10:00:00Z',thumbnail_url:'/assets/101/thumbnail?library=family-a',match_reasons:[]};
function result(version=3,extraFilters=filters){
  const context={library_id:library,binding,fingerprint,filters:extraFilters,visible_ids:['101'],total:1,search_version:version};
  return {version,kind:'results',reply:'Found one photo.',context,filters:extraFilters,items:[item],total:1,has_more:false,effect:null,interpretation};
}
function envelope(id=threadId,rid=requestId,{recovered=false,revision=1,turn=result()}={}){
  return {version:1,thread_id:id,request_id:rid,status:'completed',revision,recovered,error:null,result:turn};
}
function thread(revision=0){
  return {thread_id:threadId,library_id:library,created_at:'2026-10-16T00:00:00Z',updated_at:'2026-10-16T00:00:00Z',expires_at:'2026-11-15T00:00:00Z',revision};
}
function capabilities(version){
  return {version:1,available:true,threads:true,preferences:true,preferences_applied:true,server_owned_turns:true,
    reply_speech:true,...(version?{search:{version,date_basis:'capture',perspective:null}}:{})};
}
function httpError(status,code){return Object.assign(new Error(code),{status,code});}
function responseHeaders(values){return {get:key=>values[key.toLowerCase()]??null};}
function wavBlob(){
  const bytes=new Uint8Array(46),view=new DataView(bytes.buffer),put=(at,text)=>{for(let i=0;i<text.length;i++)bytes[at+i]=text.charCodeAt(i);};
  put(0,'RIFF');view.setUint32(4,38,true);put(8,'WAVE');put(12,'fmt ');view.setUint32(16,16,true);
  view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,8000,true);view.setUint32(28,16000,true);
  view.setUint16(32,2,true);view.setUint16(34,16,true);put(36,'data');view.setUint32(40,2,true);
  return new Blob([bytes],{type:'audio/wav'});
}
function makeController({supported=3,unsupported=[],capabilityError=null,turnError=false,requestConflict=false,hydrateResults=async value=>value}={}){
  const calls=[],scope={account:'synthetic-account',library,generation:1,locked:false};let requestCounter=0;
  const request=async(path,options={})=>{
    const header=options.extraHeaders?.['X-PhotoHouse-Search-Version']??null,parentRequestId=options.extraHeaders?.['X-PhotoHouse-Parent-Request-Id']??null;
    calls.push({path,method:options.method,header,parentRequestId,body:options.body});
    if(path.includes('/capabilities?')){
      if(capabilityError)throw capabilityError;
      if(unsupported.includes(header))throw httpError(400,'search_version_unsupported');
      return capabilities(supported);
    }
    if(path==='/assistant/workspace/v1/threads'&&options.method==='POST')return {version:1,thread:thread(0)};
    if(path===`/assistant/workspace/v1/threads/${threadId}/turns`){if(turnError)throw httpError(503,'unavailable');return envelope(threadId,options.body.request_id,{revision:1,turn:result()});}
    if(path.endsWith('/speech')){
      const rid=options.extraHeaders['X-PhotoHouse-Request-Id'];
      options.onResponse({ok:true,status:200,headers:responseHeaders({
        'cache-control':'no-store','content-type':'audio/wav','x-photohouse-request-id':rid,
        'x-photohouse-tracking':'enabled','x-photohouse-receipt-status':'succeeded'})});
      return wavBlob();
    }
    if(path.startsWith(`/assistant/workspace/v1/threads/${threadId}/requests/`)){
      if(requestConflict)throw httpError(409,'context_changed');
      const rid=path.split('/requests/')[1].split('?')[0];return envelope(threadId,rid,{recovered:true,revision:1,turn:result()});
    }
    if(path.startsWith(`/assistant/workspace/v1/threads/${threadId}?`))return {version:1,thread:thread(1),exchanges:[],latest_request_id:requestId};
    throw new Error(`Unexpected synthetic request: ${options.method} ${path}`);
  };
  const ids=[threadId,requestId,speechId];
  const controller=PrivateAssistant.createController({scope:()=>scope,request,newUUID:()=>ids[requestCounter++]||'44444444-4444-4444-8444-444444444444',hydrateResults});
  return {controller,calls,scope};
}
async function expectNegotiation({supported,unsupported=[],headers}){
  const {controller,calls}=makeController({supported,unsupported});
  const value=await controller.capabilities();
  assert.equal(value.search?.version??null,supported||null);
  assert.deepEqual(calls.map(call=>call.header),headers);
  controller.close();
}

(async()=>{
  const caps3=PrivateAssistant.validateCapabilities(capabilities(3));assert.equal(caps3.search.version,3);
  await expectNegotiation({supported:3,headers:['3']});
  await expectNegotiation({supported:2,unsupported:['3'],headers:['3','2']});
  await expectNegotiation({supported:null,unsupported:['3','2'],headers:['3','2',null]});
  {
    const {controller,calls}=makeController({capabilityError:httpError(403,'access_denied')});
    await assert.rejects(controller.capabilities(),error=>error.code==='access_denied');
    assert.deepEqual(calls.map(call=>call.header),['3'],'permission errors do not trigger an older-version retry');controller.close();
  }
  {
    const {controller,calls}=makeController({capabilityError:httpError(400,'invalid_request')});
    await assert.rejects(controller.capabilities(),error=>error.code==='request_failed');
    assert.deepEqual(calls.map(call=>call.header),['3'],'generic invalid requests do not trigger an older-version retry');controller.close();
  }

  const valid=PrivateAssistant.validateResult(result(),library,false,false,false,3);
  assert.equal(valid.version,3);assert.equal(valid.context.search_version,3);
  assert.equal(valid.filters.descriptive.concepts[0].surface,'孩子在海边玩耍');
  const invalid=value=>assert.throws(()=>PrivateAssistant.validateResult(result(3,{descriptive:value}),library,false,false,false,3),error=>error.code==='invalid_response');
  invalid({version:1,concepts:[]});
  invalid({version:1,concepts:Array.from({length:7},(_,i)=>({surface:`scene ${i}`,alternatives:['photo']}))});
  invalid({version:1,concepts:[{surface:'scene',alternatives:Array.from({length:5},(_,i)=>`alt ${i}`)}]});
  invalid({version:1,concepts:[{surface:'x'.repeat(129),alternatives:['alt']}]});
  invalid({version:1,concepts:[{surface:' scene',alternatives:['alt']}]});
  invalid({version:1,concepts:[{surface:'scene\u0085',alternatives:['alt']}]});
  invalid({version:1,concepts:[{surface:'Beach',alternatives:['sea']},{surface:'Ｂｅａｃｈ',alternatives:['shore']}]});
  invalid({version:1,concepts:[{surface:'beach',alternatives:['Sea','Ｓｅａ']}]});
  const oversized=Array.from({length:6},(_,i)=>({surface:`s${i}`+'x'.repeat(126),alternatives:Array.from({length:4},(_,j)=>`a${i}${j}`+'x'.repeat(125))}));
  invalid({version:1,concepts:oversized});
  assert.throws(()=>PrivateAssistant.validateResult(result(2,{descriptive:filters.descriptive}),library,false,false,false,2),error=>error.code==='invalid_response');
  const legacyV2=result(2,{media:['image'],text:'secret memory phrase'});
  assert.throws(()=>PrivateAssistant.validateResult(legacyV2,library,false,false,false,3),error=>error.code==='invalid_response',
    'a fresh turn cannot downgrade from negotiated v3 to v2');
  const hydratedV2=PrivateAssistant.validateResult(legacyV2,library,true,false,false,3);
  assert.equal(hydratedV2.version,2);assert.equal(hydratedV2.context.search_version,2,
    'history and recovery may hydrate an older stored v2 exchange under v3 negotiation');
  {
    const mismatched=result();mismatched.context.search_version=2;
    assert.throws(()=>PrivateAssistant.validateResult(mismatched,library,false,false,false,3),error=>error.code==='invalid_response',
      'v3 turn and context versions must agree');
  }

  {
    const {controller,calls}=makeController();await controller.capabilities();await controller.create();
    const parentRequestId='11111111-1111-4111-8111-111111111111';
    const sent=await controller.send('孩子在海边',{parentRequestId});assert.equal(sent.result.version,3);
    const turnCall=calls.find(call=>call.path.endsWith('/turns'));
    assert.equal(turnCall.header,'3','v3 turns retain the negotiated version header');
    assert.equal(turnCall.parentRequestId,parentRequestId,'a bound ASR parent is carried only as the protected turn header');
    assert.deepEqual(turnCall.body,{library_id:library,request_id:requestId,expected_revision:0,text:'孩子在海边'},'ASR provenance never changes the private turn JSON body');
    assert.equal(controller.state().currentResult.filters.descriptive.concepts[0].surface,'孩子在海边玩耍');
    const audio=await controller.speakReply();assert.equal(audio.type,'audio/wav');
    assert.equal(calls.find(call=>call.path.endsWith('/speech')).header,'3','v3 reply speech retains the negotiated version header');
    controller.close();
  }
  {
    const {controller,calls}=makeController();await controller.capabilities();await controller.create();
    await assert.rejects(controller.send('孩子在海边',{parentRequestId:'not-a-request-id'}),error=>error.code==='invalid_input');
    assert.equal(calls.filter(call=>call.path.endsWith('/turns')).length,0,'invalid ASR receipt IDs cannot reach the private turn route');
    controller.close();
  }
  {
    const {controller,calls}=makeController({turnError:true});await controller.capabilities();await controller.create();
    await assert.rejects(controller.send('孩子在海边'),error=>error.status===503);
    assert.equal(controller.state().pendingTurn.search_version,3);
    const recovered=await controller.recover(threadId,requestId);assert.equal(recovered.result.version,3);
    assert.equal(calls.find(call=>call.path.includes('/requests/')).header,'3','recovery readback stays on v3');controller.close();
  }
  {
    const {controller,calls}=makeController();await controller.capabilities();
    const read=await controller.read(threadId);assert.equal(read.current_result.version,3);
    assert.equal(calls.find(call=>call.path.includes('/requests/')).header,'3','history hydration reads the v3 result');controller.close();
  }
  {
    const {controller}=makeController({requestConflict:true});await controller.capabilities();
    const read=await controller.read(threadId);assert.equal(read.context_state,'requires_search');
    assert.equal(controller.state().currentResult,null,'a source-changed readback does not retain old search context');controller.close();
  }
  console.log('Private assistant search-v3 client checks: negotiation, strict filters, readback, source-change recovery, turn and speech headers passed.');
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
