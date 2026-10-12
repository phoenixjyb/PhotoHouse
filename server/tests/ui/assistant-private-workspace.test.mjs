import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';

const require=createRequire(import.meta.url);
const {createController,PrivateAssistantError,safeJson,validateExchange,validateResult,validateEnvelope}=require('../../backend/app/ui/access/assistant-private-workspace.js');
const threadId='22222222-2222-4222-8222-222222222222';
const requestId='11111111-1111-4111-8111-111111111111';
const library='library-a';
const stamp='2026-10-12T00:00:00Z';
const thread=(revision=0,id=threadId)=>({thread_id:id,library_id:library,created_at:stamp,updated_at:stamp,expires_at:'2026-11-11T00:00:00Z',revision,exchange_count:0});
const result={version:1,kind:'results',reply:'Found 1 photo.',context:null,filters:null,items:[],total:0,has_more:false,effect:null};
const envelope=(status='completed',recovered=false,revision=1)=>({version:1,thread_id:threadId,request_id:requestId,status,revision,recovered,error:null,result:status==='completed'?result:null});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
function harness(handler=async()=>{throw new Error('unexpected request')},opts={}){
  let current={account:'account-a',library,generation:1,locked:false},next=0;const calls=[],changes=[];
  const controller=createController({scope:()=>current,request:async(path,options)=>{calls.push({path,...options});return handler(path,options,calls);},
    newUUID:()=>opts.ids?.[next++]||requestId,onChange:s=>changes.push(s),hydrateResults:opts.hydrateResults||(async v=>v)});
  return {controller,calls,changes,setScope:v=>{current={...current,...v};},getScope:()=>current};
}
test('ambiguous turn keeps the draft and exact identity; recovery is GET-only',async()=>{
  let postCount=0;
  // Seed the controller using its public creation operation.
  // Use stable ID for creation and a second ID for the turn in this independent instance.
  const h2=harness(async(path,options)=>{if(path.endsWith('/threads'))return {version:1,thread:thread()};
    if(path.endsWith('/turns')){postCount++;throw Error('lost');}
    if(path.includes('/requests/'))return envelope('completed',true,1);throw Error('unexpected');},{ids:[threadId,requestId]});
  await h2.controller.create();h2.controller.setDraft('find family photos');
  await assert.rejects(h2.controller.send(),e=>e instanceof PrivateAssistantError&&e.code==='request_failed');
  const pending=h2.controller.state().pendingTurn;
  assert.deepEqual({request_id:pending.request_id,expected_revision:pending.expected_revision,text:pending.text,status:pending.status},
    {request_id:requestId,expected_revision:0,text:'find family photos',status:'uncertain'});
  assert.equal(h2.controller.state().draft,'find family photos');
  const recovered=await h2.controller.recover(threadId,requestId);
  assert.equal(recovered.recovered,true);assert.equal(recovered.result.effect,null);
  assert.equal(postCount,1);assert.equal(h2.calls.filter(x=>x.method==='POST'&&x.path.endsWith('/turns')).length,1);
  assert.equal(h2.calls.at(-1).method,'GET');assert.equal(h2.controller.state().pendingTurn,null);
});

test('scope change aborts requests and discards their completions and drafts',async()=>{
  const gate=deferred(),started=deferred();
  const h=harness(async(_path,{signal})=>{started.resolve();await gate.promise;if(signal.aborted){const e=new Error('aborted');e.name='AbortError';throw e;}return {version:1,threads:[]};});
  h.controller.setDraft('private draft');const read=h.controller.list();await started.promise;
  h.setScope({account:'account-b',library:'library-b',generation:2});
  gate.resolve();await assert.rejects(read);
  const state=h.controller.state();assert.equal(state.account,'account-b');assert.equal(state.library,'library-b');assert.equal(state.draft,'');assert.deepEqual(state.threads,[]);
  assert.equal(h.calls[0].signal.aborted,true);
});

test('closing aborts outstanding requests and makes late results inert',async()=>{
  const gate=deferred(),started=deferred();const h=harness(async(_p,{signal})=>{started.resolve();await gate.promise;return {version:1,threads:[]};});
  const request=h.controller.list();await started.promise;h.controller.close();gate.resolve();await assert.rejects(request);
  assert.equal(h.controller.state().closed,true);assert.equal(h.controller.state().threads.length,0);assert.equal(h.calls[0].signal.aborted,true);
});

test('creation ambiguity keeps its UUID and can be reconciled only by GET',async()=>{
  const ids=[threadId,'33333333-3333-4333-8333-333333333333'];
  const h=harness(async(path,options)=>{if(options.method==='POST')throw Error('lost response');
    if(path.includes(`/threads/${threadId}?`))return {version:1,thread:thread(),exchanges:[]};throw Error('unexpected');},{ids});
  await assert.rejects(h.controller.create());assert.equal(h.controller.state().pendingCreation.thread_id,threadId);
  const adopted=await h.controller.reconcileCreation();assert.equal(adopted.thread.thread_id,threadId);
  assert.deepEqual(h.calls.map(c=>c.method),['POST','GET']);assert.equal(h.calls[0].body.thread_id,threadId);
  assert.equal(h.controller.state().pendingCreation,null);
});

test('opening history performs request GETs and never restores saved cards as actions',async()=>{
  const exchange={exchange_id:'44444444-4444-4444-8444-444444444444',request_id:requestId,revision:1,created_at:stamp,expires_at:'2026-11-11T00:00:00Z',input_text:'find',reply:'Found.',cards:[{type:'media',count:1,actionable:false}],receipt_count:0};
  const h=harness(async(path,options)=>{
    if(path===`/assistant/workspace/v1/threads/${threadId}?library_id=${library}`)return {version:1,thread:thread(1),exchanges:[exchange],latest_request_id:requestId};
    if(path.includes('/requests/'))return envelope('completed',true,1);
    throw Error('unexpected request');
  });
  const detail=await h.controller.read(threadId);
  assert.equal(detail.exchanges[0].cards[0].actionable,false);
  assert.equal(Object.hasOwn(detail.exchanges[0].cards[0],'id'),false);
  assert.equal(h.calls.length,2);
  assert(h.calls.every(x=>x.method==='GET'));
  assert.equal(detail.current_result.kind,'results');
  assert.equal(detail.context_state,'requires_search');
});

test('malformed turn response keeps its submitted text and request identity pending',async()=>{
  const h=harness(async(path,options)=>{
    if(path.endsWith('/threads'))return {version:1,thread:thread()};
    if(path.endsWith('/turns'))return {version:1,thread_id:threadId,request_id:'33333333-3333-4333-8333-333333333333',status:'completed',revision:1,recovered:false,error:null,result};
    throw Error('unexpected request');
  },{ids:[threadId,requestId]});
  await h.controller.create();h.controller.setDraft('preserve this text');
  await assert.rejects(h.controller.send(),e=>e.code==='invalid_response');
  assert.equal(h.controller.state().draft,'preserve this text');
  assert.equal(h.controller.state().pendingTurn.request_id,requestId);
  assert.equal(h.controller.state().pendingTurn.text,'preserve this text');
  assert.equal(h.calls.filter(x=>x.method==='POST'&&x.path.endsWith('/turns')).length,1);
});

test('history cards expose only safe type/count data and never an action',()=>{
  const card=validateExchange({exchange_id:threadId,request_id:requestId,revision:1,created_at:stamp,expires_at:'2026-11-11T00:00:00Z',input_text:'find',reply:'Found.',cards:[{type:'media',count:2,actionable:false}],receipt_count:1});
  assert.deepEqual(card.cards,[{type:'media',count:2,actionable:false}]);
  assert.equal(JSON.stringify(card).includes('asset_id'),false);
  assert.throws(()=>validateExchange({exchange_id:threadId,revision:1,created_at:stamp,expires_at:stamp,input_text:'x',reply:'y',cards:[{type:'media',count:1,actionable:true}],receipt_count:0}),/invalid_response/);
});

test('wire validators reject unsafe revisions, cross-library rows, duplicate keys and invalid turn results',async()=>{
  assert.throws(()=>safeJson('{"version":1,"version":1}'),/invalid_response/);
  assert.throws(()=>safeJson('{"revision":9007199254740992}'),/invalid_response/); // caller schema also rejects unsafe values
  assert.throws(()=>validateExchange({exchange_id:threadId,revision:9007199254740992,created_at:stamp,expires_at:stamp,input_text:'x',reply:'y',cards:[],receipt_count:0}),/invalid_response/);
  const h=harness(async()=>({version:1,threads:[{...thread(),library_id:'library-b'}]}));
  await assert.rejects(h.controller.list(),e=>e.code==='invalid_response');
});

test('invalid draft and preferences fail before network requests',async()=>{
  const h=harness(async()=>({version:1,locale:null,reply_length:null,voice_pace:null,revision:0}));
  assert.throws(()=>h.controller.setDraft('x'.repeat(1025)),e=>e.code==='invalid_input');
  await assert.rejects(h.controller.updatePreferences({voice_pace:'fast'}),e=>e.code==='invalid_input');
  assert.equal(h.calls.length,0);
});

const asset=(id='42',lib=library)=>({id,kind:'image',width:640,height:480,duration_sec:null,taken_at:'2024-04-05 12:13:14',thumbnail_url:`/assets/${id}/thumbnail?library=${encodeURIComponent(lib)}`});
const context=(lib=library)=>({library_id:lib,binding:'a'.repeat(64),fingerprint:'b'.repeat(64),filters:{},visible_ids:['42'],total:1});
const contextualResult=(overrides={})=>({version:1,kind:'results',reply:'Found 1 photo.',context:context(),filters:{},items:[asset()],total:1,has_more:false,effect:null,...overrides});

test('strict result grammar accepts clarification and unsupported, and binds result to this library',()=>{
  for(const kind of ['clarification','unsupported'])assert.equal(validateResult(contextualResult({kind}),library).kind,kind);
  assert.throws(()=>validateResult(contextualResult({context:context('library-b')}),library),e=>e.code==='invalid_response');
  assert.throws(()=>validateResult(contextualResult({items:[asset('43')]}),library),e=>e.code==='invalid_response');
  assert.equal(validateResult(contextualResult({context:null,filters:null,items:[],total:0,has_more:false}),library).context,null);
});

test('open effects are allowed only on fresh POSTs and point to a visible item',()=>{
  const opened=contextualResult({kind:'open',reply:'Opening result.',effect:{type:'open_asset',asset_id:'42'}});
  assert.equal(validateResult(opened,library,false).effect.asset_id,'42');
  assert.throws(()=>validateResult(opened,library,true),e=>e.code==='invalid_response');
  assert.throws(()=>validateResult({...opened,effect:{type:'open_asset',asset_id:'43'}},library,false),e=>e.code==='invalid_response');
  assert.throws(()=>validateResult({...opened,kind:'results'},library,false),e=>e.code==='invalid_response');
  assert.throws(()=>validateResult(contextualResult({items:[{...asset(),thumbnail_url:'https://photohouse.invalid/assets/42/thumbnail?library=library-a'}]}),library,false),e=>e.code==='invalid_response');
  assert.throws(()=>validateResult(contextualResult({items:[{...asset(),width:true}]}),library),e=>e.code==='invalid_response');
  assert.throws(()=>validateResult(contextualResult({items:[{...asset(),unexpected:'source binding'}]}),library),e=>e.code==='invalid_response');
});

test('POST replay may be recovered, GET requires recovered and both enforce fixed error codes',()=>{
  const post={...envelope('completed',true,1),result:contextualResult()};
  assert.equal(validateEnvelope(post,threadId,requestId,library,'POST').recovered,true);
  const recoveredOpen={...post,result:contextualResult({kind:'open',effect:{type:'open_asset',asset_id:'42'}})};
  assert.throws(()=>validateEnvelope(recoveredOpen,threadId,requestId,library,'POST'),e=>e.code==='invalid_response');
  assert.throws(()=>validateEnvelope({...post,recovered:false},threadId,requestId,library,'GET'),e=>e.code==='invalid_response');
  assert.throws(()=>validateEnvelope({...post,error:'raw provider failure'},threadId,requestId,library,'POST'),e=>e.code==='invalid_response');
  const failed={version:1,thread_id:threadId,request_id:requestId,status:'failed',revision:0,recovered:true,error:'assistant_unavailable',result:null};
  assert.equal(validateEnvelope(failed,threadId,requestId,library,'GET').error,'assistant_unavailable');
  assert.throws(()=>validateEnvelope({...failed,error:'raw provider failure'},threadId,requestId,library,'GET'),e=>e.code==='invalid_response');
});

test('thread read hydrates only one latest request, honors hydrate false, and never promotes stale result revision',async()=>{
  const detail={version:1,thread:thread(4),exchanges:[],latest_request_id:requestId,has_older_exchanges:true};
  const h=harness(async(path)=>path.includes('/requests/')?{...envelope('completed',true,3),result:contextualResult()}:detail);
  const read=await h.controller.read(threadId);
  assert.equal(h.calls.length,2);assert.equal(h.calls.at(-1).method,'GET');
  assert.equal(read.has_older_exchanges,true);assert.equal(read.current_result,null);assert.equal(read.context_state,'stale');
  assert.equal(Object.hasOwn(read.latest_request,'result'),false);
  assert.equal(h.controller.state().activeThread.revision,3);assert.equal(h.controller.state().revision,3);
  const other=harness(async()=>detail);await other.controller.read(threadId,{hydrate:false});
  assert.equal(other.calls.length,1);assert.equal(other.controller.state().contextState,'unloaded');
});

test('history remains readable when its latest committed result is expired or its context changed',async()=>{
  const exchange={exchange_id:'44444444-4444-4444-8444-444444444444',request_id:requestId,revision:4,created_at:stamp,expires_at:'2026-11-11T00:00:00Z',input_text:'find old photos',reply:'Saved reply.',cards:[{type:'media',count:1,actionable:false}],receipt_count:0};
  for(const status of [404,409]){
    const detail={version:1,thread:thread(4),exchanges:[exchange],latest_request_id:requestId,has_older_exchanges:true};
    const h=harness(async(path)=>{if(path.includes('/requests/'))throw Object.assign(new Error('secret provider/body detail'),{status});return detail;});
    const read=await h.controller.read(threadId);
    assert.equal(read.exchanges[0].reply,'Saved reply.');
    assert.equal(read.has_older_exchanges,true);
    assert.equal(read.context_state,'requires_search');
    assert.equal(read.current_result,null);
    assert.equal(Object.hasOwn(read,'latest_request'),false);
    assert.equal(h.controller.state().revision,4);
    assert.equal(h.controller.state().currentResult,null);
    assert.deepEqual(h.calls.map(x=>x.method),['GET','GET']);
  }
});

test('authorization denial locks and clears client state until scope generation changes',async()=>{
  const h=harness(async()=>{throw Object.assign(new Error('secret details'),{status:401});});
  h.controller.setDraft('private text');
  await assert.rejects(h.controller.list(),e=>e.code==='access_denied'&&e.status===401);
  assert.equal(h.controller.state().locked,true);
  assert.equal(h.controller.state().draft,'');
  assert.deepEqual(h.controller.state().threads,[]);
  await assert.rejects(h.controller.list(),e=>e.code==='scope_changed');
  assert.equal(h.calls.length,1);
  h.setScope({generation:2});
  assert.equal(h.controller.state().locked,false);
});

test('pending turn blocks read and create until recovery or explicit abandonment',async()=>{
  const h=harness(async(path,options)=>{if(path.endsWith('/threads'))return {version:1,thread:thread(0,options.body.thread_id)};if(path.endsWith('/turns'))throw Error('ambiguous');if(path.includes('/requests/'))return {version:1,thread_id:threadId,request_id:requestId,status:'pending',revision:0,recovered:true,error:null,result:null};throw Error('unexpected');},{ids:[threadId,requestId,'33333333-3333-4333-8333-333333333333']});
  await h.controller.create();h.controller.setDraft('preserve me');await assert.rejects(h.controller.send());
  await assert.rejects(h.controller.read(threadId),e=>e.code==='conflict');
  await assert.rejects(h.controller.create(),e=>e.code==='conflict');
  await h.controller.recover(threadId,requestId);assert.equal(h.controller.state().pendingTurn.status,'pending');
  assert.equal(h.controller.abandonPending(),'preserve me');assert.equal(h.controller.state().pendingTurn,null);
  const created=await h.controller.create();assert.equal(created.thread.thread_id,'33333333-3333-4333-8333-333333333333');
  assert.equal(h.controller.state().draft,'preserve me');
});

test('failed recovery clears the blocker and preserves the original draft for a new explicit turn',async()=>{
  const h=harness(async(path)=>{if(path.endsWith('/threads'))return {version:1,thread:thread()};if(path.endsWith('/turns'))throw Error('ambiguous');if(path.includes('/requests/'))return {version:1,thread_id:threadId,request_id:requestId,status:'interrupted',revision:0,recovered:true,error:'turn_interrupted',result:null};throw Error('unexpected');},{ids:[threadId,requestId]});
  await h.controller.create();h.controller.setDraft('find this');await assert.rejects(h.controller.send());
  const recovered=await h.controller.recover(threadId,requestId);
  assert.equal(recovered.status,'interrupted');assert.equal(h.controller.state().pendingTurn,null);
  assert.equal(h.controller.state().draft,'find this');
});

test('safe JSON rejects duplicate keys and raw responses over 256 KiB',()=>{
  assert.throws(()=>safeJson('{"x":1,"x":2}'),e=>e.code==='invalid_response');
  assert.throws(()=>safeJson(`{"text":"${'x'.repeat(262145)}"}`),e=>e.code==='invalid_response');
});

test('late completion cannot hydrate or publish after a different thread read takes ownership',async()=>{
  const otherId='33333333-3333-4333-8333-333333333333',gate=deferred(),started=deferred();let hydrated=0;
  const detail1={version:1,thread:thread(1),exchanges:[],latest_request_id:requestId};
  const detail2={version:1,thread:thread(0,otherId),exchanges:[]};
  const h=harness(async(path)=>{if(path.includes(`/threads/${threadId}/requests/`)){started.resolve();await gate.promise;return {...envelope('completed',true,1),result:contextualResult()};}
    return path.startsWith(`/assistant/workspace/v1/threads/${threadId}?`)?detail1:detail2;},{hydrateResults:async value=>{hydrated++;return value;}});
  const first=h.controller.read(threadId);await started.promise;const second=await h.controller.read(otherId,{hydrate:false});gate.resolve();await assert.rejects(first);
  assert.equal(second.thread.thread_id,otherId);assert.equal(h.controller.state().activeThread.thread_id,otherId);assert.equal(hydrated,0);
});

test('changing threads aborts an already running result hydration',async()=>{
  const otherId='33333333-3333-4333-8333-333333333333',gate=deferred(),hydrating=deferred();let aborted=false;
  const detail1={version:1,thread:thread(1),exchanges:[],latest_request_id:requestId};
  const detail2={version:1,thread:thread(0,otherId),exchanges:[]};
  const h=harness(async(path)=>path.includes('/requests/')?{...envelope('completed',true,1),result:contextualResult()}:
    path.startsWith(`/assistant/workspace/v1/threads/${threadId}?`)?detail1:detail2,
  {hydrateResults:async(value,{signal})=>{hydrating.resolve();signal.addEventListener('abort',()=>{aborted=true;});await gate.promise;return value;}});
  const first=h.controller.read(threadId);await hydrating.promise;
  const second=await h.controller.read(otherId,{hydrate:false});
  gate.resolve();await assert.rejects(first);
  assert.equal(aborted,true);
  assert.equal(second.thread.thread_id,otherId);
  assert.equal(h.controller.state().activeThread.thread_id,otherId);
  assert.equal(h.controller.state().currentResult,null);
});
