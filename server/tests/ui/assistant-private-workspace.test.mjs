import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';

const require=createRequire(import.meta.url);
const {createController,PrivateAssistantError,safeJson,validateExchange,validateResult,validateEnvelope,validateCapabilities,validateSavedMemoryActionCapabilities,validateThread,validateHistoryPage}=require('../../backend/app/ui/access/assistant-private-workspace.js');
const threadId='22222222-2222-4222-8222-222222222222';
const requestId='11111111-1111-4111-8111-111111111111';
const library='library-a';
const stamp='2026-10-12T00:00:00Z';
const thread=(revision=0,id=threadId)=>({thread_id:id,library_id:library,created_at:stamp,updated_at:stamp,expires_at:'2026-11-11T00:00:00Z',revision,exchange_count:0});
const result={version:1,kind:'results',reply:'Found 1 photo.',context:null,filters:null,items:[],total:0,has_more:false,effect:null};
const envelope=(status='completed',recovered=false,revision=1)=>({version:1,thread_id:threadId,request_id:requestId,status,revision,recovered,error:null,result:status==='completed'?result:null});
const workspaceCaps=(overrides={})=>({version:1,available:true,threads:true,preferences:true,preferences_applied:false,server_owned_turns:true,...overrides});
const savedMemoryCapabilities=available=>({version:1,available});
const savedMemorySpeechCapabilities=available=>({version:1,available});
const savedMemoryReaderCapabilities=available=>({version:1,available});
const savedMemoryFollowupCapabilities=available=>({version:1,available});
const savedMemoryReadingCapabilities=available=>({version:1,available});
const savedMemoryActionCapabilities=available=>({version:1,available});
const memoryBinding={kind:'story',id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',revision:'2',source_revision:'b'.repeat(64)};
const memoryResult=(overrides={})=>({version:1,kind:'memory_cards',reply:'Found 1 saved memory.',context:{kind:'saved_memory',library_id:library,source_revision:'c'.repeat(64),references:[{...memoryBinding}]},filters:null,items:[],total:1,has_more:false,effect:null,memory_cards:[{...memoryBinding,title:'A family day 👨‍👩‍👧‍👦',excerpt:'We walked beside the water.'}],...overrides});
const memoryClarification=(overrides={})=>({version:1,kind:'clarification',reply:'Say a phrase to search saved memories.',context:null,filters:null,items:[],total:0,has_more:false,effect:null,memory_cards:[],...overrides});

test('saved-memory action capability and action proposals are exact, fresh, and ordinal-bound',async()=>{
  const action={type:'read_opening',ordinal:0},fresh=memoryResult({memory_action:action});
  assert.deepEqual(validateResult(fresh,library,false,true,true).memory_action,action);
  for(const bad of [
    {...fresh,memory_action:{type:'read_opening',ordinal:12}},
    {...fresh,memory_action:{type:'open',ordinal:0,asset_id:'42'}},
    {...fresh,memory_action:{type:'delete',ordinal:0}},
    {...memoryClarification(),memory_action:action}
  ])assert.throws(()=>validateResult(bad,library,false,true,true),e=>e.code==='invalid_response');
  assert.throws(()=>validateResult(fresh,library,false,true,false),e=>e.code==='invalid_response');
  assert.throws(()=>validateResult(fresh,library,true,true,true),e=>e.code==='invalid_response','recovery cannot restore a navigable action');
  assert.deepEqual(validateSavedMemoryActionCapabilities({version:1,available:false}),{version:1,available:false});
  assert.throws(()=>validateSavedMemoryActionCapabilities({version:1,available:true,extra:false}),e=>e.code==='invalid_response');

  let turnCount=0;
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps();
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-action-capabilities'))return savedMemoryActionCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns')){turnCount++;return {...envelope('completed',false,turnCount),request_id:options.body.request_id,result:turnCount===1?memoryResult():fresh};}
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,'33333333-3333-4333-8333-333333333333']});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();
  assert.equal(await h.controller.savedMemoryActionsCapabilities(),true);
  await h.controller.create();await h.controller.send('find saved memories');
  const completed=await h.controller.send('read the first saved memory');
  const actionTurn=h.calls.filter(call=>call.path.endsWith('/turns')).at(-1);
  assert.deepEqual(actionTurn.body.accepts,['saved_memory_cards_v1','saved_memory_actions_v1']);
  assert.deepEqual(actionTurn.body.memory_parent,{request_id:requestId,revision:1},'action parent binding works independently of the followup probe');
  assert.equal(completed.recovered,false);assert.deepEqual(h.controller.state().currentResult.memory_action,action);
  assert.equal(h.controller.state().savedMemoryActionReady,true,'the action requires the current visible source cohort');
});

test('saved-memory action probe preserves old-route fallback and revokes on true base denial',async()=>{
  let baseReads=0;
  const fallback=harness(async(path)=>{
    if(path.includes('/capabilities?')){baseReads++;return workspaceCaps();}
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-action-capabilities'))throw Object.assign(new Error('old optional route'),{status:403});
    throw Error(`unexpected ${path}`);
  });
  await fallback.controller.capabilities();await fallback.controller.savedMemoryCapabilities();
  assert.equal(await fallback.controller.savedMemoryActionsCapabilities(),false);
  assert.equal(baseReads,2,'an optional route 403 is disambiguated by the same authenticated base probe');
  assert.equal(fallback.controller.state().locked,false,'a legacy route boundary does not revoke the authorized workspace');

  let deniedBaseReads=0;
  const denied=harness(async(path)=>{
    if(path.includes('/capabilities?')){deniedBaseReads++;if(deniedBaseReads===1)return workspaceCaps();throw Object.assign(new Error('authorization revoked'),{status:403});}
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-action-capabilities'))throw Object.assign(new Error('old optional route'),{status:403});
    throw Error(`unexpected ${path}`);
  });
  await denied.controller.capabilities();await denied.controller.savedMemoryCapabilities();
  await assert.rejects(denied.controller.savedMemoryActionsCapabilities(),e=>e.status===403);
  assert.equal(denied.controller.state().locked,true,'a real authorization denial clears the local scope');
});
const exchange=(revision,id=`${String(revision).padStart(8,'0')}-4444-4444-8444-${String(revision).padStart(12,'0')}`)=>({exchange_id:id,revision,created_at:stamp,expires_at:'2026-11-11T00:00:00Z',input_text:`Question ${revision}`,reply:`Reply ${revision}`,cards:[],receipt_count:0});
const detail=(from,to,hasOlder=false,overrides={})=>({version:1,thread:thread(to),exchanges:Array.from({length:to-from+1},(_,i)=>exchange(from+i)),has_older_exchanges:hasOlder,...overrides});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
function harness(handler=async()=>{throw new Error('unexpected request')},opts={}){
  let current={account:'account-a',library,generation:1,locked:false},next=0;const calls=[],changes=[];
  const controller=createController({scope:()=>current,request:async(path,options)=>{calls.push({path,...options});const value=await handler(path,options,calls);if(path.includes('/speech')&&opts.autoSpeechResponse!==false){const segment=path.match(/\/segments\/(0|[1-9][0-9]*)\/speech$/),headers=new Headers({
      'X-PhotoHouse-Request-Id':options.extraHeaders?.['X-PhotoHouse-Request-Id']||'',
      'X-PhotoHouse-Tracking':'enabled','X-PhotoHouse-Receipt-Status':'succeeded',
      'Content-Type':'audio/wav','Cache-Control':'private, no-store','Content-Encoding':'identity',
      ...(segment?{'X-PhotoHouse-Playback-Tracking':'enabled','X-PhotoHouse-Reading-Segment':segment[1],'X-PhotoHouse-Reading-Segment-Count':'3'}:{})
    });const custom=typeof opts.speechHeaders==='function'?opts.speechHeaders(path,options):opts.speechHeaders;for(const [key,val] of Object.entries(custom||{})){if(val===null)headers.delete(key);else headers.set(key,String(val));}options.onResponse?.({ok:true,status:opts.speechStatus??200,headers});}return value;},
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

function wavChunk(name,payload){const part=new Uint8Array(8+payload.length+(payload.length&1)),view=new DataView(part.buffer);for(let i=0;i<4;i++)part[i]=name.charCodeAt(i);view.setUint32(4,payload.length,true);part.set(payload,8);return part;}
function pcmWav({channels=1,rate=16000,bits=16,dataBytes=320,ancillary=false,badByteRate=false}={}){
  const align=channels*(bits/8),format=new Uint8Array(16),fv=new DataView(format.buffer);fv.setUint16(0,1,true);fv.setUint16(2,channels,true);fv.setUint32(4,rate,true);fv.setUint32(8,rate*align+(badByteRate?1:0),true);fv.setUint16(12,align,true);fv.setUint16(14,bits,true);
  const data=new Uint8Array(dataBytes),chunks=[];if(ancillary)chunks.push(wavChunk('JUNK',new Uint8Array([1,2,3])));chunks.push(wavChunk('fmt ',format),wavChunk('data',data));if(ancillary)chunks.push(wavChunk('LIST',new Uint8Array([4,5])));
  const length=12+chunks.reduce((sum,chunk)=>sum+chunk.length,0),bytes=new Uint8Array(length),view=new DataView(bytes.buffer),label=(at,value)=>[...value].forEach((c,i)=>bytes[at+i]=c.charCodeAt(0));
  label(0,'RIFF');view.setUint32(4,length-8,true);label(8,'WAVE');let offset=12;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}return new Blob([bytes],{type:'audio/wav'});
}
function fakeWav(){return pcmWav();}
async function preparedSpeech({headers,autoSpeechResponse=true,audio=fakeWav(),reply='Question reply.'}={}){
  const ids=[threadId,requestId,'33333333-3333-4333-8333-333333333333'];
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread(0,threadId)};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:contextualResult({reply})};
    if(path.includes('/speech'))return audio;throw Error(`unexpected ${path}`);
  },{ids,autoSpeechResponse,speechHeaders:headers});
  await h.controller.capabilities();await h.controller.create();await h.controller.send('question');return h;
}

test('reply speech capability is optional and must be boolean',()=>{
  assert.equal(validateCapabilities(workspaceCaps()).reply_speech,false);
  assert.equal(validateCapabilities(workspaceCaps({reply_speech:true})).reply_speech,true);
  assert.throws(()=>validateCapabilities(workspaceCaps({reply_speech:'yes'})),e=>e.code==='invalid_response');
});

test('only a fresh private completion can request scoped reply audio',async()=>{
  const speechId='33333333-3333-4333-8333-333333333333';let wav=fakeWav();
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread(0,threadId)};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:contextualResult({reply:'家'.repeat(200)})};
    if(path.endsWith(`/requests/${requestId}/speech`)){assert.equal(options.method,'POST');return wav;}
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,speechId]});
  await h.controller.capabilities();await h.controller.create();h.controller.setDraft('find photos');
  const completed=await h.controller.send();assert.equal(completed.recovered,false);assert.equal(h.controller.state().speechReady,true);assert.equal(h.controller.state().speechReplyBytes,600);
  const audio=await h.controller.speakReply();assert.equal(audio,wav);
  const call=h.calls.at(-1);assert.equal(call.path,`/assistant/workspace/v1/threads/${threadId}/requests/${requestId}/speech`);
  assert.deepEqual(call.body,{library_id:library,expected_revision:1});
  assert.deepEqual(call.extraHeaders,{'X-PhotoHouse-Request-Id':speechId,'X-PhotoHouse-Parent-Request-Id':requestId});
  assert.equal(call.responseType,'blob');assert.equal(Object.hasOwn(call.body,'text'),false);assert.equal(Object.hasOwn(call.body,'context'),false);assert.equal(Object.hasOwn(call.body,'language'),false);
});

test('reply speech accepts bounded PCM WAV variants and ancillary RIFF chunks',async()=>{
  for(const audio of [
    pcmWav({channels:2,rate:44100,bits:24,dataBytes:600,ancillary:true}),
    pcmWav({channels:2,rate:48000,bits:32,dataBytes:384000}),
    pcmWav({channels:1,rate:8000,bits:8,dataBytes:240000,ancillary:true})
  ]){const h=await preparedSpeech({audio});assert.equal(await h.controller.speakReply(),audio);}
});

test('reply speech rejects overlong or internally inconsistent PCM WAV',async()=>{
  for(const audio of [pcmWav({rate:8000,bits:8,dataBytes:240001}),pcmWav({channels:2,rate:44100,bits:24,badByteRate:true})]){
    const h=await preparedSpeech({audio});await assert.rejects(h.controller.speakReply(),e=>e.code==='invalid_response');
  }
});

test('reply speech requires genuine successful no-store audio response metadata',async()=>{
  const badHeaders=[
    {'X-PhotoHouse-Tracking':'disabled'},
    {'X-PhotoHouse-Receipt-Status':'failed'},
    {'X-PhotoHouse-Request-Id':'44444444-4444-4444-8444-444444444444'},
    {'Content-Type':'application/json'},
    {'Cache-Control':'private, no-cache'},
    {'Content-Encoding':'gzip'}
  ];
  for(const headers of badHeaders){const h=await preparedSpeech({headers});await assert.rejects(h.controller.speakReply(),e=>e.code==='invalid_response');}
  const missing=await preparedSpeech({autoSpeechResponse:false});await assert.rejects(missing.controller.speakReply(),e=>e.code==='invalid_response');
});

test('local speech source wipe is safe after lock or close',async()=>{
  const locked=await preparedSpeech();locked.setScope({locked:true});assert.doesNotThrow(()=>locked.controller.discardSpeechSource());assert.equal(locked.controller.state().speechReady,false);
  const closed=await preparedSpeech();closed.controller.close();assert.doesNotThrow(()=>closed.controller.discardSpeechSource());
});

test('scope and source are rechecked after asynchronous WAV validation',async()=>{
  const gate=deferred(),started=deferred(),audio=fakeWav(),original=audio.arrayBuffer.bind(audio);Object.defineProperty(audio,'arrayBuffer',{value:()=>{started.resolve();return gate.promise;}});
  const h=await preparedSpeech({audio});const speech=h.controller.speakReply();await started.promise;await h.controller.send('newer question');gate.resolve(await original());
  await assert.rejects(speech,e=>e.code==='aborted');
});

test('recovered completions and over-limit replies never request speech',async()=>{
  const speechId='33333333-3333-4333-8333-333333333333';let recovered=true,reply='x',speechPosts=0;
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread(0,options.body.thread_id)};
    if(path.endsWith('/turns'))return {...envelope('completed',recovered,1),request_id:options.body.request_id,result:contextualResult({reply})};
    if(path.includes('/speech')){speechPosts++;return fakeWav();}throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,speechId]});
  await h.controller.capabilities();await h.controller.create();await h.controller.send('question');
  assert.equal(h.controller.state().speechReady,false);await assert.rejects(h.controller.speakReply(),e=>e.code==='invalid_input');
  recovered=false;reply='家'.repeat(201);await h.controller.send('second question');assert.equal(h.controller.state().speechReady,true);assert.equal(h.controller.state().speechReplyBytes,603);
  await assert.rejects(h.controller.speakReply(),e=>e.code==='invalid_input');assert.equal(speechPosts,0);
});

test('late reply audio is fenced when a newer turn invalidates its source',async()=>{
  const speechId='33333333-3333-4333-8333-333333333333',gate=deferred(),started=deferred();let turn=0;
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread(0,threadId)};
    if(path.endsWith('/turns')){turn++;return {...envelope('completed',false,turn),request_id:options.body.request_id};}
    if(path.includes('/speech')){started.resolve();await gate.promise;return fakeWav();}throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,speechId,'44444444-4444-4444-8444-444444444444']});
  await h.controller.capabilities();await h.controller.create();await h.controller.send('first');
  const speech=h.controller.speakReply();await started.promise;await h.controller.send('new turn');gate.resolve();
  await assert.rejects(speech,e=>e.code==='aborted');assert.equal(h.controller.state().speechReady,true);assert.equal(h.controller.state().speechReplyBytes,new TextEncoder().encode('Found 1 photo.').length);
});

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
  const detail={version:1,thread:thread(4),exchanges:[exchange(4)],latest_request_id:requestId,has_older_exchanges:true};
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

test('history capabilities default off, labels are strictly opted in, and safe Unicode plain text is accepted',async()=>{
  const base=workspaceCaps();
  assert.equal(validateCapabilities(base).thread_labels,false);
  assert.equal(validateCapabilities(base).history_paging,false);
  assert.throws(()=>validateCapabilities({...base,history_paging:'true'}),e=>e.code==='invalid_response');
  const label='家庭 📷 <b>夏天</b>';
  assert.equal(validateThread({...thread(),label},library,true).label,label);
  assert.equal(validateThread({...thread(),label:null},library,true).label,null);
  for(const invalid of ['',`😀`.repeat(65),'  ', 'bad\u0001label'])
    assert.throws(()=>validateThread({...thread(),label:invalid},library,true),e=>e.code==='invalid_response');
  assert.throws(()=>validateThread({...thread(),label:'unexpected'},library),e=>e.code==='invalid_response');
  assert.throws(()=>validateThread(thread(),library,true),e=>e.code==='invalid_response');

  const off=harness(async()=>({version:1,threads:[thread()]}));
  await off.controller.list();
  assert.equal(off.calls[0].path,`/assistant/workspace/v1/threads?library_id=${library}`);
  const on=harness(async(path)=>path.includes('/capabilities?')?workspaceCaps({thread_labels:true}):
    {version:1,threads:[{...thread(),label}]});
  await on.controller.capabilities();
  const optedIn=await on.controller.list();
  assert.equal(optedIn[0].label,label);
  assert.match(on.calls[1].path,/include_labels=true/);
});

test('explicit older pages are validated, merged once, and preserve draft and grounded context',async()=>{
  const detail45={...detail(26,45,true,{latest_request_id:requestId})};
  const page6to25={version:1,thread_id:threadId,snapshot_revision:45,before_revision:26,
    exchanges:Array.from({length:20},(_,i)=>exchange(i+6)),has_older_exchanges:true,next_before_revision:6};
  const page1to5={version:1,thread_id:threadId,snapshot_revision:45,before_revision:6,
    exchanges:Array.from({length:5},(_,i)=>exchange(i+1)),has_older_exchanges:false,next_before_revision:null};
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({history_paging:true});
    if(path===`/assistant/workspace/v1/threads/${threadId}?library_id=${library}`)return detail45;
    if(path.includes('/requests/'))return {...envelope('completed',true,45),result:contextualResult()};
    if(path.includes('/history?')&&path.includes('before_revision=26'))return page6to25;
    if(path.includes('/history?')&&path.includes('before_revision=6'))return page1to5;
    throw Error(`unexpected request ${options.method} ${path}`);
  });
  await h.controller.capabilities();
  const initial=await h.controller.read(threadId);
  assert.equal(initial.exchanges.length,20);
  assert.equal(h.controller.state().historyDetail.snapshot_revision,45);
  assert.equal(h.controller.state().historyDetail.before_revision,26);
  assert.equal(h.controller.state().currentResult.kind,'results');
  h.controller.setDraft('keep this draft');
  assert.equal(h.calls.filter(c=>c.path.includes('/history?')).length,0);
  const first=await h.controller.older();
  assert.equal(first.exchanges.length,40);
  assert.deepEqual(first.exchanges.map(x=>x.revision),Array.from({length:40},(_,i)=>i+6));
  assert.equal(first.before_revision,6);assert.equal(first.has_older_exchanges,true);
  const second=await h.controller.older();
  assert.equal(second.exchanges.length,45);
  assert.deepEqual(second.exchanges.map(x=>x.revision),Array.from({length:45},(_,i)=>i+1));
  assert.equal(second.has_older_exchanges,false);assert.equal(second.before_revision,null);
  assert.equal(h.controller.state().draft,'keep this draft');
  assert.equal(h.controller.state().currentResult.kind,'results');
  assert.equal(h.controller.state().contextState,'ready');
  assert.equal(h.controller.state().historyRefreshRequired,false);
  assert.deepEqual(h.calls.filter(c=>c.path.includes('/history?')).map(c=>c.method),['GET','GET']);
});

test('history page validator rejects envelope, cursor, ordering and size mismatches',()=>{
  const valid={version:1,thread_id:threadId,snapshot_revision:45,before_revision:26,
    exchanges:[exchange(6),exchange(25)],has_older_exchanges:true,next_before_revision:6};
  assert.equal(validateHistoryPage(valid,threadId,library,45,26).exchanges.length,2);
  const malformed=[
    {...valid,extra:true},
    {...valid,thread_id:'33333333-3333-4333-8333-333333333333'},
    {...valid,snapshot_revision:44},
    {...valid,before_revision:25},
    {...valid,exchanges:[exchange(25),exchange(6)]},
    {...valid,exchanges:[exchange(6),exchange(6,'33333333-3333-4333-8333-333333333333')]},
    {...valid,exchanges:[exchange(6),exchange(25)],next_before_revision:25},
    {...valid,exchanges:[],has_older_exchanges:true,next_before_revision:1},
    {...valid,exchanges:Array.from({length:21},(_,i)=>exchange(i+1)),has_older_exchanges:false,next_before_revision:null},
    {...valid,exchanges:[exchange(26)]},
  ];
  for(const value of malformed)assert.throws(()=>validateHistoryPage(value,threadId,library,45,26),e=>e.code==='invalid_response');
});

test('an expired history snapshot requires an explicit detail refresh and never merges the page',async()=>{
  const h=harness(async(path)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({history_paging:true});
    if(path.includes('/history?'))throw Object.assign(new Error('revision changed'),{status:409});
    return detail(26,45,true);
  });
  await h.controller.capabilities();await h.controller.read(threadId,{hydrate:false});
  const before=h.controller.state().historyDetail.exchanges.map(x=>x.exchange_id);
  await assert.rejects(h.controller.older(),e=>e.status===409);
  assert.equal(h.controller.state().historyRefreshRequired,true);
  assert.equal(h.controller.state().historyDetail.history_stale,true);
  assert.deepEqual(h.controller.state().historyDetail.exchanges.map(x=>x.exchange_id),before);
  assert.equal(h.calls.filter(c=>c.path.includes('/history?')).length,1);
});

test('starting a new thread and deleting the active thread clear owned history',async()=>{
  const newId='33333333-3333-4333-8333-333333333333';
  const h=harness(async(path,options)=>{
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread(0,options.body.thread_id)};
    if(path.includes('/history?'))return {version:1,thread_id:threadId,snapshot_revision:1,before_revision:1,exchanges:[],has_older_exchanges:false,next_before_revision:null};
    if(path.includes(`/threads/${threadId}?`))return detail(1,1,true);
    if(path.includes(`/threads/${newId}?`))return {version:1,thread:thread(0,newId),exchanges:[]};
    if(path===`/assistant/workspace/v1/threads/${newId}`&&options.method==='DELETE')return {deleted:true,thread_id:newId};
    throw Error(`unexpected ${options.method} ${path}`);
  },{ids:[newId]});
  await h.controller.read(threadId,{hydrate:false});
  assert.ok(h.controller.state().historyDetail);
  await h.controller.create();
  assert.equal(h.controller.state().historyDetail,null);
  await h.controller.read(newId,{hydrate:false});
  assert.ok(h.controller.state().historyDetail);
  await h.controller.delete(newId);
  assert.equal(h.controller.state().historyDetail,null);
});

test('engine-off reads retain history without request hydration and server labels are requested only when advertised',async()=>{
  const label='Summer photos';
  const h=harness(async(path)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({available:false,server_owned_turns:false,thread_labels:true});
    if(path.includes('/threads?'))return {version:1,threads:[{...thread(),label}]};
    if(path.includes('/threads/')&&path.includes('?'))return detail(1,1,false,{latest_request_id:requestId});
    throw Error('unexpected request');
  });
  await h.controller.capabilities();
  const rows=await h.controller.list();
  assert.equal(rows[0].label,label);
  assert.match(h.calls[1].path,/include_labels=true/);
  const read=await h.controller.read(threadId);
  assert.equal(read.exchanges.length,1);
  assert.equal(read.context_state,'unloaded');
  assert.deepEqual(h.calls.map(c=>c.method),['GET','GET','GET']);
  assert.equal(h.calls.some(c=>c.path.includes('/requests/')),false);
});

test('turn and recovery invalidate paging until an explicit latest detail reload',async()=>{
  let revisionNow=2;
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({history_paging:true});
    if(path.endsWith('/threads'))return {version:1,thread:thread()};
    if(path.includes('/history?'))return {version:1,thread_id:threadId,snapshot_revision:revisionNow,before_revision:1,exchanges:[],has_older_exchanges:false,next_before_revision:null};
    if(path.includes(`/threads/${threadId}?`))return detail(1,2,true,{thread:thread(revisionNow)});
    if(path.endsWith('/turns')){revisionNow=3;throw Error('ambiguous');}
    if(path.includes('/requests/'))return envelope('completed',true,3);
    throw Error(`unexpected ${options.method} ${path}`);
  },{ids:[threadId,requestId]});
  await h.controller.capabilities();await h.controller.create();
  await h.controller.read(threadId,{hydrate:false});h.controller.setDraft('keep after uncertainty');
  await assert.rejects(h.controller.send());
  assert.equal(h.controller.state().historyRefreshRequired,true);
  assert.equal(h.controller.state().historyDetail.history_stale,true);
  assert.equal(h.controller.state().draft,'keep after uncertainty');
  h.controller.setDraft('separate unsent draft');
  await h.controller.recover(threadId,requestId);
  assert.equal(h.controller.state().historyRefreshRequired,true);
  assert.equal(h.controller.state().draft,'separate unsent draft');
  const refreshed=await h.controller.read(threadId,{hydrate:false});
  assert.equal(refreshed.snapshot_revision,3);
  assert.equal(h.controller.state().historyRefreshRequired,false);
});

test('history paging is stale fenced by scope changes and the 200 exchange cap',async()=>{
  const gate=deferred(),started=deferred();
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({history_paging:true});
    if(path.includes(`/threads/${threadId}?`))return detail(181,200,true);
    if(path.includes('/history?')){started.resolve();await gate.promise;if(options.signal.aborted){const e=new Error('aborted');e.name='AbortError';throw e;}return {version:1,thread_id:threadId,snapshot_revision:200,before_revision:181,exchanges:Array.from({length:20},(_,i)=>exchange(i+161)),has_older_exchanges:true,next_before_revision:161};}
    throw Error('unexpected request');
  });
  await h.controller.capabilities();await h.controller.read(threadId,{hydrate:false});
  const pending=h.controller.older();await started.promise;h.setScope({account:'account-b',library:'library-b',generation:2});gate.resolve();
  await assert.rejects(pending);assert.equal(h.controller.state().historyDetail,null);
  assert.equal(h.calls.at(-1).signal.aborted,true);

  // Rebuild a full 200-row buffer and verify a page cannot push it beyond the cap.
  let pageNo=0;
  const capped=harness(async(path)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({history_paging:true});
    if(path.includes(`/threads/${threadId}?`))return detail(221,240,true);
    if(path.includes('/history?')){pageNo++;const before=Number(new URLSearchParams(path.split('?')[1]).get('before_revision'));const values=Array.from({length:20},(_,i)=>exchange(before-20+i));const hasOlder=before>21;return {version:1,thread_id:threadId,snapshot_revision:240,before_revision:before,exchanges:values,has_older_exchanges:hasOlder,next_before_revision:hasOlder?before-20:null};}
    throw Error('unexpected request');
  });
  await capped.controller.capabilities();await capped.controller.read(threadId,{hydrate:false});
  while(capped.controller.state().historyDetail.exchanges.length<180)await capped.controller.older();
  const before=capped.controller.state().historyDetail;
  await assert.rejects(capped.controller.older(),error=>error.code==='invalid_response');
  assert.equal(capped.controller.state().historyDetail,before);
  assert.equal(before.exchanges.length,180);
});

test('saved-memory capability probe is explicit, exact, and fail closed',async()=>{
  let answer=savedMemoryCapabilities(true);
  const h=harness(async(path)=>{if(path.includes('/capabilities?'))return workspaceCaps();assert(path.endsWith('/saved-memory-capabilities?library_id=library-a'));return answer;});
  assert.equal(h.controller.state().savedMemoryAvailable,false);assert.equal(h.calls.length,0,'reading state performs no probe');
  assert.equal(await h.controller.savedMemoryCapabilities(),false);assert.equal(h.calls.length,0,'saved-memory probe requires known base capabilities');
  await h.controller.capabilities();assert.equal(await h.controller.savedMemoryCapabilities(),true);assert.equal(h.calls.length,2);assert.equal(h.calls[1].method,'GET');
  assert.equal(h.controller.state().savedMemoryAvailable,true);
  const disabled=harness(async(path)=>path.includes('/capabilities?')?workspaceCaps():savedMemoryCapabilities(false));await disabled.controller.capabilities();assert.equal(await disabled.controller.savedMemoryCapabilities(),false);assert.equal(disabled.controller.state().savedMemoryAvailable,false);
  for(answer of [undefined,{version:1,available:'yes'},{version:1,available:true,extra:true}]){
    const malformed=harness(async(path)=>path.includes('/capabilities?')?workspaceCaps():answer);await malformed.controller.capabilities();assert.equal(await malformed.controller.savedMemoryCapabilities(),false);assert.equal(malformed.controller.state().savedMemoryAvailable,false);
  }
  for(const status of [404,503]){
    const unavailable=harness(async(path)=>{if(path.includes('/capabilities?'))return workspaceCaps();throw Object.assign(new Error('private detail'),{status});});await unavailable.controller.capabilities();
    assert.equal(await unavailable.controller.savedMemoryCapabilities(),false);assert.equal(unavailable.controller.state().savedMemoryAvailable,false);
  }
  for(const status of [401,403]){
    const denied=harness(async(path)=>{if(path.includes('/capabilities?'))return workspaceCaps();throw Object.assign(new Error('private detail'),{status});});await denied.controller.capabilities();
    await assert.rejects(denied.controller.savedMemoryCapabilities(),error=>error.code==='access_denied'&&error.status===status);
    assert.equal(denied.controller.state().savedMemoryAvailable,false);assert.equal(denied.controller.state().locked,true);
  }
});

test('saved-memory probe is scope fenced and stale capability is cleared on base capability loss, scope and close',async()=>{
  const gate=deferred(),started=deferred();
  const h=harness(async(path)=>{if(path.includes('/saved-memory-capabilities')){started.resolve();await gate.promise;return savedMemoryCapabilities(true);}if(path.includes('/capabilities?'))return workspaceCaps();return workspaceCaps({server_owned_turns:false});});
  await h.controller.capabilities();
  const pending=h.controller.savedMemoryCapabilities();await started.promise;h.setScope({account:'account-b',library:'library-b',generation:2});gate.resolve();
  await assert.rejects(pending,error=>error.code==='scope_changed');assert.equal(h.controller.state().savedMemoryAvailable,false);

  let baseAvailable=false;const current=harness(async(path)=>path.includes('/saved-memory-capabilities')?savedMemoryCapabilities(true):workspaceCaps({server_owned_turns:baseAvailable}));
  await current.controller.capabilities();assert.equal(await current.controller.savedMemoryCapabilities(),false);
  assert.equal(await current.controller.savedMemoryCapabilities(),false,'a feature probe cannot override known base capability loss');
  baseAvailable=true;await current.controller.capabilities();assert.equal(await current.controller.savedMemoryCapabilities(),true);current.controller.close();assert.equal(current.controller.state().savedMemoryAvailable,false);
});

test('saved-memory followup probe is independent, exact, and optional',async()=>{
  for(const status of [404,503]){
    const h=harness(async(path)=>{if(path.includes('/capabilities?'))return workspaceCaps();if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);throw Object.assign(new Error('optional route unavailable'),{status});});
    await h.controller.capabilities();await h.controller.savedMemoryCapabilities();
    assert.equal(await h.controller.savedMemoryFollowupCapabilities(),false);assert.equal(h.controller.state().savedMemoryAvailable,true);
    assert.equal(h.controller.state().savedMemoryFollowupAvailable,false);
  }
  for(const answer of [undefined,{version:1,available:'yes'},{version:1,available:true,extra:true}]){
    const h=harness(async(path)=>{if(path.includes('/capabilities?'))return workspaceCaps();if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);return answer;});
    await h.controller.capabilities();await h.controller.savedMemoryCapabilities();assert.equal(await h.controller.savedMemoryFollowupCapabilities(),false);
  }
  const h=harness(async(path)=>{if(path.includes('/capabilities?'))return workspaceCaps();if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);return savedMemoryFollowupCapabilities(true);});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();assert.equal(await h.controller.savedMemoryFollowupCapabilities(),true);
  assert.equal(h.calls.at(-1).method,'GET');assert.match(h.calls.at(-1).path,/saved-memory-followup-capabilities\?library_id=library-a$/);
});

test('an optional followup 403 is rechecked against base capabilities before preserving private state',async()=>{
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);
    if(path.includes('/saved-memory-reader-capabilities'))return savedMemoryReaderCapabilities(true);
    if(path.includes('/saved-memory-followup-capabilities'))throw Object.assign(new Error('unknown optional route'),{status:403});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),request_id:options.body.request_id,result:memoryResult()};
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId]});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.savedMemoryReaderCapabilities();
  await h.controller.create();await h.controller.send('find saved memories');const result=h.controller.state().currentResult;
  assert.equal(h.controller.state().savedMemoryReaderReady,true);assert.equal(h.controller.state().speechReady,true);
  assert.equal(await h.controller.savedMemoryFollowupCapabilities(),false);
  assert.equal(h.calls.filter(call=>call.path.includes('/capabilities?')).length,2,'403 revalidates the existing base route');
  assert.equal(h.controller.state().locked,false);assert.equal(h.controller.state().currentResult,result);
  assert.equal(h.controller.state().savedMemoryAvailable,true);assert.equal(h.controller.state().savedMemoryReaderReady,true);
  assert.equal(h.controller.state().speechReady,true,'optional route denial preserves explicit reply speech');
});

test('an optional followup 403 revokes private state when base capability revalidation is denied',async()=>{
  let baseReads=0;
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?')){baseReads++;if(baseReads===1)return workspaceCaps();throw Object.assign(new Error('authorization lost'),{status:401});}
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-followup-capabilities'))throw Object.assign(new Error('unknown optional route'),{status:403});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    throw Error(`unexpected ${path}`);
  },{ids:[threadId]});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.create();
  await assert.rejects(h.controller.savedMemoryFollowupCapabilities(),error=>error.code==='access_denied');
  assert.equal(baseReads,2);assert.equal(h.controller.state().locked,true);assert.equal(h.controller.state().activeThread,null);
});

test('a late 403 base recheck cannot bind followup support across a scope change',async()=>{
  const gate=deferred(),started=deferred();let baseReads=0;
  const h=harness(async(path)=>{
    if(path.includes('/capabilities?')){baseReads++;if(baseReads===1)return workspaceCaps();started.resolve();await gate.promise;return workspaceCaps();}
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-followup-capabilities'))throw Object.assign(new Error('unknown optional route'),{status:403});
    throw Error(`unexpected ${path}`);
  });
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();
  const probe=h.controller.savedMemoryFollowupCapabilities();await started.promise;
  h.setScope({account:'account-b',library:'library-b',generation:2});gate.resolve();
  await assert.rejects(probe,error=>error.code==='scope_changed');
  assert.equal(h.controller.state().account,'account-b');assert.equal(h.controller.state().savedMemoryFollowupAvailable,false);
});

test('fresh saved-memory followup sends exact parent after End and refreshes the current anchor',async()=>{
  let turns=0;
  const second='33333333-3333-4333-8333-333333333333';
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps();
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-followup-capabilities'))return savedMemoryFollowupCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns')){turns++;return {...envelope('completed',false,turns),request_id:options.body.request_id,result:memoryResult()};}
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,second]});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.savedMemoryFollowupCapabilities();
  await h.controller.create();await h.controller.send('find saved memories');
  assert.equal(h.controller.state().savedMemoryFollowupReady,true);
  h.controller.discardSpeechSource();assert.equal(h.controller.state().savedMemoryFollowupReady,true,'End only revokes speech, not the explicit text followup anchor');
  await h.controller.send('what is the first saved memory about');
  const followup=h.calls.filter(call=>call.method==='POST'&&call.path.endsWith('/turns')).at(-1);
  assert.deepEqual(followup.body,{library_id:library,request_id:second,expected_revision:1,text:'what is the first saved memory about',accepts:['saved_memory_cards_v1'],memory_parent:{request_id:requestId,revision:1}});
  assert.equal(h.controller.state().savedMemoryFollowupReady,true,'a fresh cards result owns a new followup anchor');
});

test('saved-memory parent is omitted after media result or history reload',async()=>{
  let turns=0;const ids=[threadId,requestId,'33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444','55555555-5555-4555-8555-555555555555'];
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps();if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-followup-capabilities'))return savedMemoryFollowupCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns')){turns++;return {...envelope('completed',false,turns),request_id:options.body.request_id,result:turns===1?memoryResult():result};}
    if(path===`/assistant/workspace/v1/threads/${threadId}?library_id=${library}`)return detail(1,3);
    throw Error(`unexpected ${path}`);
  },{ids});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();assert.equal(await h.controller.savedMemoryFollowupCapabilities(),true);
  await h.controller.create();await h.controller.send('find saved memories');assert.equal(h.controller.state().savedMemoryFollowupReady,true);
  await h.controller.send('show photos');assert.deepEqual(h.calls.filter(call=>call.method==='POST'&&call.path.endsWith('/turns')).at(-1).body.memory_parent,{request_id:requestId,revision:1});
  assert.equal(h.controller.state().currentResult.kind,'results');assert.equal(h.controller.state().savedMemoryFollowupReady,false);
  await h.controller.send('show another photo');assert.equal(Object.hasOwn(h.calls.filter(call=>call.method==='POST'&&call.path.endsWith('/turns')).at(-1).body,'memory_parent'),false,'a media result cannot seed a memory parent');
  await h.controller.read(threadId,{hydrate:false});assert.equal(h.controller.state().currentResult,null);
  await h.controller.send('continue search');assert.equal(Object.hasOwn(h.calls.filter(call=>call.method==='POST'&&call.path.endsWith('/turns')).at(-1).body,'memory_parent'),false,'history reload cannot seed a memory parent');
});

test('clarification and recovered completions never seed saved-memory parents',async()=>{
  let turns=0;const ids=[threadId,requestId,'33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444'];
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps();if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-followup-capabilities'))return savedMemoryFollowupCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns')){turns++;if(turns===1)return {...envelope('completed',false,1),request_id:options.body.request_id,result:memoryClarification()};throw Error('lost response');}
    if(path.includes(`/requests/${ids[2]}`))return {...envelope('completed',true,2),request_id:ids[2],result};
    throw Error(`unexpected ${path}`);
  },{ids});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.savedMemoryFollowupCapabilities();await h.controller.create();
  await h.controller.send('find a saved memory');assert.equal(h.controller.state().savedMemoryFollowupReady,false);
  await assert.rejects(h.controller.send('introduce these memories'));
  assert.equal(Object.hasOwn(h.calls.filter(call=>call.method==='POST'&&call.path.endsWith('/turns')).at(-1).body,'memory_parent'),false,'clarification has no source cohort');
  await h.controller.recover(threadId,ids[2]);assert.equal(h.controller.state().currentResult.kind,'results');
  await assert.rejects(h.controller.send('what is the first saved memory about'));
  assert.equal(Object.hasOwn(h.calls.filter(call=>call.method==='POST'&&call.path.endsWith('/turns')).at(-1).body,'memory_parent'),false,'a recovered completion has no fresh display anchor');
});

test('saved-memory reader probe is optional and preserves fresh cards when unavailable',async()=>{
  const h=harness(async(path)=>{if(path.includes('/capabilities?'))return workspaceCaps();if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);if(path.includes('/saved-memory-reader-capabilities'))throw Object.assign(new Error('old server'),{status:404});if(path.endsWith('/threads')&&h.controller.state().pendingCreation)return {version:1,thread:thread()};if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:memoryResult()};throw Error(`unexpected ${path}`);},{ids:[threadId,requestId]});
  await h.controller.capabilities();assert.equal(await h.controller.savedMemoryCapabilities(),true);assert.equal(await h.controller.savedMemoryReaderCapabilities(),false);
  await h.controller.create();await h.controller.send('find saved memories');
  assert.equal(h.controller.state().currentResult.kind,'memory_cards');assert.equal(h.controller.state().savedMemoryReaderAvailable,false);
  assert.equal(h.calls.some(call=>call.path.includes('/memory-cards/')),false);
});

test('saved-memory reader GET is bound to a fresh card, exact revision and current scope',async()=>{
  const reader={version:1,id:memoryBinding.id,revision:memoryBinding.revision,type:'story',title:'Saved story'};
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps();if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);if(path.includes('/saved-memory-reader-capabilities'))return savedMemoryReaderCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:memoryResult()};
    if(path===`/assistant/workspace/v1/threads/${threadId}?library_id=library-a`)return detail(1,1);
    if(path.includes('/memory-cards/0?'))return {version:1,kind:'story',reader};throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId]});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();assert.equal(await h.controller.savedMemoryReaderCapabilities(),true);await h.controller.create();await h.controller.send('find saved memories');
  const result=h.controller.state().currentResult,postCount=h.calls.filter(call=>call.method==='POST').length;
  const handoff=await h.controller.openMemoryCard(0,(kind,value)=>kind==='story'&&value.id===memoryBinding.id);
  assert.equal(handoff.kind,'story');assert.equal(handoff.reader,reader);assert.equal(handoff.card.id,memoryBinding.id);
  assert.equal(h.calls.at(-1).method,'GET');assert.match(h.calls.at(-1).path,new RegExp(`/threads/${threadId}/requests/${requestId}/memory-cards/0\\?library_id=library-a&expected_revision=1`));
  assert.equal(h.calls.filter(call=>call.method==='POST').length,postCount);assert.equal(h.controller.state().currentResult,result);
  await assert.rejects(h.controller.openMemoryCard(1,()=>true),error=>error.code==='invalid_input');
  h.controller.setDraft('keep typed draft');
  await h.controller.read(threadId,{hydrate:false});assert.equal(h.controller.state().currentResult,null);
  await assert.rejects(h.controller.openMemoryCard(0,()=>true),error=>error.code==='invalid_input');
  assert.equal(h.controller.state().draft,'keep typed draft');
});

test('late reader handoffs cannot outlive a new turn or account and library scope',async()=>{
  const gate=deferred(),started=deferred();let turns=0;
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps();if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);if(path.includes('/saved-memory-reader-capabilities'))return savedMemoryReaderCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns')){turns++;return turns===1?{...envelope('completed',false,1),result:memoryResult()}:{...envelope('completed',false,2),request_id:options.body.request_id,result};}
    if(path.includes('/memory-cards/0?')){started.resolve();await gate.promise;return {version:1,kind:'story',reader:{id:memoryBinding.id,revision:memoryBinding.revision,type:'story'}};}
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,'44444444-4444-4444-8444-444444444444']});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.savedMemoryReaderCapabilities();await h.controller.create();await h.controller.send('find saved memories');
  const opening=h.controller.openMemoryCard(0,()=>true);await started.promise;await h.controller.send('show photos');gate.resolve();
  await assert.rejects(opening,error=>error.code==='scope_changed');assert.equal(h.controller.state().currentResult.kind,'results');
  assert.equal(h.controller.state().openingMemoryCard,false);
  const delayed=deferred(),arrived=deferred();
  const scoped=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps();if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);if(path.includes('/saved-memory-reader-capabilities'))return savedMemoryReaderCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:memoryResult()};
    if(path.includes('/memory-cards/0?')){arrived.resolve();await delayed.promise;return {version:1,kind:'story',reader:{id:memoryBinding.id,revision:memoryBinding.revision,type:'story'}};}
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId]});
  await scoped.controller.capabilities();await scoped.controller.savedMemoryCapabilities();await scoped.controller.savedMemoryReaderCapabilities();await scoped.controller.create();await scoped.controller.send('find saved memories');
  const stale=scoped.controller.openMemoryCard(0,()=>true);await arrived.promise;scoped.setScope({account:'account-b',library:'library-b',generation:2});delayed.resolve();
  await assert.rejects(stale,error=>error.code==='scope_changed');assert.equal(scoped.controller.state().currentResult,null);assert.equal(scoped.controller.state().savedMemoryReaderReady,false);
});

test('legacy requests remain byte-shape unchanged and no capability probe is implicit',async()=>{
  const h=harness(async(path,options)=>{if(options.method==='POST'&&path.endsWith('/threads'))return {version:1,thread:thread()};if(path.endsWith('/turns'))return envelope('completed',false,1);throw Error('unexpected');},{ids:[threadId,requestId]});
  await h.controller.create();h.controller.setDraft('find photos');await h.controller.send();
  assert.equal(h.calls.length,2);assert.deepEqual(Object.keys(h.calls.at(-1).body).sort(),['expected_revision','library_id','request_id','text']);
  assert.equal(h.controller.state().savedMemoryAvailable,false);
});

test('explicitly negotiated send adds only the fixed accepts token and skips media hydration',async()=>{
  let hydrated=0;
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps();
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:memoryResult()};
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId],hydrateResults:async value=>{hydrated++;return value;}});
  await h.controller.capabilities();assert.equal(await h.controller.savedMemoryCapabilities(),true);await h.controller.create();h.controller.setDraft('find saved memories');
  const completed=await h.controller.send();const request=h.calls.at(-1);
  assert.deepEqual(request.body,{library_id:library,request_id:requestId,expected_revision:0,text:'find saved memories',accepts:['saved_memory_cards_v1']});
  assert.equal(hydrated,0);assert.equal(completed.result.kind,'memory_cards');assert.equal(h.controller.state().contextState,'requires_search');
  assert.equal(h.controller.state().speechReady,false);assert.equal(h.controller.state().savedMemoryAvailable,true);
  assert.equal(Object.isFrozen(completed.result),true);assert.equal(Object.isFrozen(completed.result.context),true);
  assert.equal(Object.isFrozen(completed.result.memory_cards),true);assert.equal(Object.isFrozen(completed.result.memory_cards[0]),true);
  assert.equal(Object.isFrozen(completed.result.context.references[0]),true);
  await assert.rejects(h.controller.speakReply(),error=>error.code==='invalid_input');
  assert.equal(h.calls.some(x=>x.path.includes('/speech')),false,'memory result creates no speech source or request');
});

test('late memory completion is hidden and left uncertain after base capability loss',async()=>{
  const gate=deferred(),started=deferred();let baseAvailable=true,hydrated=0;
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps({available:baseAvailable,server_owned_turns:baseAvailable});
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns')){started.resolve();await gate.promise;return {...envelope('completed',false,1),result:memoryResult()};}
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId],hydrateResults:async value=>{hydrated++;return value;}});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.create();h.controller.setDraft('find memories');
  const sent=h.controller.send();await started.promise;baseAvailable=false;await h.controller.capabilities();gate.resolve();
  await assert.rejects(sent,error=>error.code==='context_changed');
  assert.equal(h.controller.state().pendingTurn.status,'uncertain');assert.equal(h.controller.state().draft,'find memories');
  assert.equal(h.controller.state().currentResult,null);assert.equal(h.controller.state().speechReady,false);assert.equal(hydrated,0);
  assert.equal(h.controller.state().savedMemoryAvailable,false);assert.equal(h.calls.filter(x=>x.method==='POST'&&x.path.endsWith('/turns')).length,1);
});

test('recovery never accepts or hydrates negotiated memory cards',async()=>{
  const h=harness(async(path,options)=>{
    if(path.includes('/capabilities?'))return workspaceCaps();
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))throw Error('ambiguous');
    if(path.includes('/requests/'))return {...envelope('completed',true,1),result:memoryResult()};
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId]});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.create();h.controller.setDraft('find memories');
  await assert.rejects(h.controller.send());
  await assert.rejects(h.controller.recover(threadId,requestId),error=>error.code==='invalid_response');
  assert.equal(h.controller.state().draft,'find memories');assert.equal(h.controller.state().currentResult,null);
  assert.deepEqual(h.calls.map(x=>x.method),['GET','GET','POST','POST','GET']);
  assert.equal(h.calls.some(x=>x.method==='GET'&&x.path.includes('/saved-memory-capabilities')),true);
});

test('saved-memory clarification is negotiated, has no source refs, and may use existing reply speech',async()=>{
  const h=harness(async(path,options)=>{
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:memoryClarification()};
    if(path.includes('/speech'))return fakeWav();
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,'33333333-3333-4333-8333-333333333333']});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.create();
  const done=await h.controller.send('找回忆');assert.equal(done.result.kind,'clarification');assert.deepEqual(done.result.memory_cards,[]);
  assert.equal(h.controller.state().speechReady,true);assert.equal(await h.controller.speakReply() instanceof Blob,true);
});

test('fresh memory cards seed reply speech only after both exact capability probes',async()=>{
  const speechId='33333333-3333-4333-8333-333333333333';let speechPosts=0;
  const h=harness(async(path,options)=>{
    if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:memoryResult()};
    if(path.includes('/speech')){speechPosts++;assert.deepEqual(options.body,{library_id:library,expected_revision:1});return fakeWav();}
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,speechId]});
  await h.controller.capabilities();assert.equal(await h.controller.savedMemoryCapabilities(),true);
  assert.deepEqual(h.calls.slice(0,3).map(x=>x.path.split('?')[0]),[
    '/assistant/workspace/v1/capabilities','/assistant/workspace/v1/saved-memory-capabilities',
    '/assistant/workspace/v1/saved-memory-speech-capabilities']);
  assert.equal(h.controller.state().savedMemorySpeechAvailable,true);await h.controller.create();await h.controller.send('find memory');
  assert.equal(h.controller.state().speechReady,true);assert.equal(h.controller.state().savedMemoryAvailable,true);
  assert.equal(await h.controller.speakReply() instanceof Blob,true);assert.equal(speechPosts,1);
});

test('missing or unavailable memory speech capability keeps cards available and never seeds speech',async()=>{
  for(const unavailable of [404,503,'malformed']){
    const h=harness(async(path,options)=>{
      if(path.includes('/saved-memory-speech-capabilities')){if(unavailable==='malformed')return {version:1,available:true,unexpected:true};throw Object.assign(new Error('private detail'),{status:unavailable});}
      if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
      if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
      if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
      if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:memoryResult()};
      if(path.includes('/speech'))throw Error('speech must remain disabled');
      throw Error(`unexpected ${path}`);
    },{ids:[threadId,requestId]});
    await h.controller.capabilities();assert.equal(await h.controller.savedMemoryCapabilities(),true);
    assert.equal(h.controller.state().savedMemoryAvailable,true);assert.equal(h.controller.state().savedMemorySpeechAvailable,false);
    await h.controller.create();await h.controller.send('find memory');assert.equal(h.controller.state().speechReady,false);
    await assert.rejects(h.controller.speakReply(),error=>error.code==='invalid_input');assert.equal(h.calls.some(x=>x.path.includes('/speech')),false);
  }
});

test('new speech probe aborts active memory audio and late bytes are refused',async()=>{
  const gate=deferred(),started=deferred(),speechId='33333333-3333-4333-8333-333333333333';
  const h=harness(async(path,options)=>{
    if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:memoryResult()};
    if(path.includes('/speech')){started.resolve();await gate.promise;return fakeWav();}
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,speechId]});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.create();await h.controller.send('find memory');
  const pending=h.controller.speakReply();await started.promise;assert.equal(h.calls.at(-1).signal.aborted,false);
  // A fresh optional recheck revokes the memory source before its new result arrives.
  const recheck=h.controller.savedMemorySpeechCapabilities();assert.equal(h.calls.at(-1).path.includes('/saved-memory-speech-capabilities'),true);
  assert.equal(h.calls.find(x=>x.path.includes('/speech')).signal.aborted,true);
  gate.resolve();await recheck;await assert.rejects(pending,error=>error.code==='aborted');
});

test('recovered memory turn never seeds reply speech after safe GET summary recovery',async()=>{
  const h=harness(async(path,options)=>{
    if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))throw Error('ambiguous POST');
    if(path.includes('/requests/'))return {...envelope('completed',true,1),result};
    if(path.includes('/speech'))throw Error('recovered memory replies cannot request speech');
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,'33333333-3333-4333-8333-333333333333']});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.create();h.controller.setDraft('find memories');
  await assert.rejects(h.controller.send());const recovered=await h.controller.recover(threadId,requestId);
  assert.equal(recovered.recovered,true);assert.equal(recovered.result.kind,'results');
  assert.equal(h.controller.state().speechReady,false);await assert.rejects(h.controller.speakReply(),error=>error.code==='invalid_input');
  assert.equal(h.calls.some(x=>x.path.includes('/speech')),false);
});

test('memory result grammar is exact, bounded and accepted only for negotiated fresh POST',()=>{
  const fresh={...envelope('completed',false,1),result:memoryResult()};
  assert.throws(()=>validateResult(fresh.result,library),error=>error.code==='invalid_response');
  assert.throws(()=>validateEnvelope(fresh,threadId,requestId,library,'POST'),error=>error.code==='invalid_response');
  const allowed=validateEnvelope(fresh,threadId,requestId,library,'POST',true);assert.equal(allowed.result.memory_cards.length,1);
  const clarification={...fresh,result:memoryClarification()};assert.equal(validateEnvelope(clarification,threadId,requestId,library,'POST',true).result.kind,'clarification');
  assert.throws(()=>validateEnvelope({...fresh,recovered:true},threadId,requestId,library,'POST',true),error=>error.code==='invalid_response');
  assert.throws(()=>validateEnvelope({...fresh,recovered:true},threadId,requestId,library,'GET',true),error=>error.code==='invalid_response');

  const invalid=[
    memoryResult({memory_cards:[{...memoryResult().memory_cards[0],id:memoryBinding.id.toUpperCase()}]}),
    memoryResult({memory_cards:[{...memoryResult().memory_cards[0],revision:'02'}]}),
    memoryResult({memory_cards:[{...memoryResult().memory_cards[0],source_revision:'B'.repeat(64)}]}),
    memoryResult({memory_cards:[{...memoryResult().memory_cards[0],title:'x'.repeat(641)}]}),
    memoryResult({memory_cards:[{...memoryResult().memory_cards[0],title:'x'.repeat(321)+'😀'.repeat(321)}]}),
    memoryResult({memory_cards:[{...memoryResult().memory_cards[0],excerpt:'😀'.repeat(241)}]}),
    memoryResult({memory_cards:[{...memoryResult().memory_cards[0],excerpt:'x'.repeat(961)}]}),
    memoryResult({context:{...memoryResult().context,references:[]}}),
    memoryResult({total:257,has_more:true}),
    memoryResult({items:[asset()]}),
    memoryResult({effect:{type:'open_asset',asset_id:'42'}}),
    memoryResult({memory_cards:[memoryResult().memory_cards[0],memoryResult().memory_cards[0]],total:2,has_more:false,context:{...memoryResult().context,references:[{...memoryBinding},{...memoryBinding}]}})
  ];
  for(const value of invalid)assert.throws(()=>validateResult(value,library,false,true),error=>error.code==='invalid_response');
});

test('saved-memory opening probe uses the exact optional capability grammar and scoped fallback',async()=>{
  const h=harness(async(path)=>{if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);if(path.includes('/saved-memory-reading-capabilities'))return savedMemoryReadingCapabilities(true);throw Error(`unexpected ${path}`);});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();assert.equal(h.controller.state().savedMemoryReadingAvailable,false);
  assert.equal(await h.controller.savedMemoryReadingCapabilities(),true);
  const probe=h.calls.at(-1);assert.equal(probe.method,'GET');assert.match(probe.path,/^\/assistant\/workspace\/v1\/saved-memory-reading-capabilities\?library_id=library-a$/);
  for(const response of [{version:1,available:true,extra:false},{version:'1',available:true},{version:1,available:'yes'}]){
    const malformed=harness(async(path)=>path.includes('/saved-memory-reading-capabilities')?response:path.includes('/saved-memory-speech-capabilities')?savedMemorySpeechCapabilities(true):path.includes('/saved-memory-capabilities')?savedMemoryCapabilities(true):workspaceCaps({reply_speech:true}));
    await malformed.controller.capabilities();await malformed.controller.savedMemoryCapabilities();assert.equal(await malformed.controller.savedMemoryReadingCapabilities(),false);
  }
  let baseReads=0;const fallback=harness(async(path)=>{if(path.includes('/capabilities?')){baseReads++;return workspaceCaps({reply_speech:true});}if(path.includes('/saved-memory-reading-capabilities'))throw Object.assign(new Error('unknown optional route'),{status:403});if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);throw Error(`unexpected ${path}`);});
  await fallback.controller.capabilities();await fallback.controller.savedMemoryCapabilities();assert.equal(await fallback.controller.savedMemoryReadingCapabilities(),false);
  assert.equal(baseReads,2);assert.equal(fallback.controller.state().locked,false);assert.equal(fallback.controller.state().savedMemoryAvailable,true);
});

async function preparedMemoryOpening({handler,ids=[threadId,requestId,'33333333-3333-4333-8333-333333333333'],speechHeaders,autoSpeechResponse=true}={}){
  const h=harness(async(path,options)=>{
    if(path.includes('/saved-memory-reading-capabilities'))return savedMemoryReadingCapabilities(true);
    if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread(0,threadId)};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),request_id:options.body.request_id,result:memoryResult()};
    if(path.includes('/memory-cards/0/speech'))return handler?handler(path,options):fakeWav();
    if(path===`/assistant/workspace/v1/threads/${threadId}?library_id=${library}`)return detail(1,1);
    throw Error(`unexpected ${path}`);
  },{ids,speechHeaders,autoSpeechResponse});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.savedMemoryReadingCapabilities();await h.controller.create();await h.controller.send('search saved memories');
  return h;
}

async function preparedMemorySegments({handler,ids=[threadId,requestId,'33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444'],speechHeaders}={}){
  const h=harness(async(path,options)=>{
    if(path.includes('/saved-memory-segment-reading-capabilities'))return {version:1,available:true};
    if(path.includes('/saved-memory-reading-capabilities'))return savedMemoryReadingCapabilities(true);
    if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread(0,threadId)};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),request_id:options.body.request_id,result:memoryResult()};
    if(path.includes('/segments/')&&path.endsWith('/speech'))return handler?handler(path,options):fakeWav();
    if(path===`/assistant/workspace/v1/threads/${threadId}?library_id=${library}`)return detail(1,1);
    throw Error(`unexpected ${path}`);
  },{ids,speechHeaders});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.savedMemoryReadingCapabilities();
  await h.controller.savedMemorySpeechCapabilities();await h.controller.savedMemorySegmentReadingCapabilities();await h.controller.create();
  await h.controller.send('search saved memories');return h;
}

test('saved-memory section speech is route-bound and requires playback outcome tracking',async()=>{
  const h=await preparedMemorySegments();assert.equal(h.controller.state().savedMemorySegmentReadingReady,true);
  const first=await h.controller.speakMemorySegment(0,0);assert.equal(first.audio instanceof Blob,true);assert.equal(first.segmentCount,3);
  const call=h.calls.at(-1);assert.equal(call.path,`/assistant/workspace/v1/threads/${threadId}/requests/${requestId}/memory-cards/0/segments/0/speech`);
  assert.deepEqual(call.body,{library_id:library,expected_revision:1});
  assert.deepEqual(call.extraHeaders,{'X-PhotoHouse-Request-Id':'33333333-3333-4333-8333-333333333333','X-PhotoHouse-Parent-Request-Id':requestId});
  assert.equal(call.responseType,'blob','the section transport returns audio bytes only');
  const next=await h.controller.speakMemorySegment(0,1,{expectedSegmentCount:first.segmentCount});assert.equal(next.segmentCount,3);
  assert.match(h.calls.at(-1).path,/\/segments\/1\/speech$/);
  for(const headers of [
    {'X-PhotoHouse-Playback-Tracking':null},
    {'X-PhotoHouse-Playback-Tracking':'disabled'},
    {'X-PhotoHouse-Playback-Tracking':'enabled, enabled'},
    {'X-PhotoHouse-Reading-Segment':null},
    {'X-PhotoHouse-Reading-Segment':'0, 0'},
    {'X-PhotoHouse-Reading-Segment':'00'},
    {'X-PhotoHouse-Reading-Segment':'1'},
    {'X-PhotoHouse-Reading-Segment-Count':null},
    {'X-PhotoHouse-Reading-Segment-Count':'03'},
    {'X-PhotoHouse-Reading-Segment-Count':'3, 3'},
    {'X-PhotoHouse-Reading-Segment-Count':'0'}
  ]){
    const bad=await preparedMemorySegments({speechHeaders:headers});
    await assert.rejects(bad.controller.speakMemorySegment(0,0),error=>error.code==='invalid_response');
  }
  const changed=await preparedMemorySegments({speechHeaders:path=>path.includes('/segments/1/')?{'X-PhotoHouse-Reading-Segment-Count':'4'}:{}});
  const initial=await changed.controller.speakMemorySegment(0,0);
  await assert.rejects(changed.controller.speakMemorySegment(0,1,{expectedSegmentCount:initial.segmentCount}),error=>error.code==='invalid_response',
    'continuation refuses a changed server count');
});

test('section speech optional 403 rechecks the existing base capability route',async()=>{
  let baseReads=0;
  const h=harness(async(path)=>{
    if(path.includes('/capabilities?')){baseReads++;return workspaceCaps({reply_speech:true});}
    if(path.includes('/saved-memory-segment-reading-capabilities'))throw Object.assign(new Error('old optional route'),{status:403});
    if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/saved-memory-reading-capabilities'))return savedMemoryReadingCapabilities(true);
    throw Error(`unexpected ${path}`);
  });
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.savedMemoryReadingCapabilities();
  await h.controller.savedMemorySpeechCapabilities();assert.equal(await h.controller.savedMemorySegmentReadingCapabilities(),false);
  assert.equal(baseReads,2,'unknown optional route gets one exact base recheck');
  assert.equal(h.controller.state().locked,false,'legacy route 403 does not revoke current workspace authorization');
  assert.equal(h.controller.state().savedMemoryAvailable,true);
});

test('section response bytes are discarded after result, scope, or capability refresh changes',async()=>{
  for(const interrupt of ['result','scope','refresh']){
    const gate=deferred(),started=deferred();
    const h=await preparedMemorySegments({handler:async(_path,{signal})=>{started.resolve();await gate.promise;if(signal.aborted){const error=new Error('aborted');error.name='AbortError';throw error;}return fakeWav();},ids:[threadId,requestId,'33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444']});
    const pending=h.controller.speakMemorySegment(0,0);await started.promise;
    if(interrupt==='result')await h.controller.send('replace saved-memory result');
    else if(interrupt==='scope')h.setScope({account:'account-b',library:'library-b',generation:2});
    else await h.controller.savedMemorySegmentReadingCapabilities();
    h.controller.state();const call=h.calls.find(item=>item.path.includes('/segments/0/speech'));
    assert.equal(call.signal.aborted,true,`${interrupt} fences the in-flight segment response`);
    gate.resolve();await assert.rejects(pending);
    assert.equal(h.controller.state().segmentMemorySpeechIndex,null,`${interrupt} clears section progress`);
  }
});

test('late finally from an aborted segment cannot clear a requalified same-index request marker',async()=>{
  const firstGate=deferred(),firstStarted=deferred(),replacementGate=deferred(),replacementStarted=deferred();let speechRequestCount=0;
  const h=await preparedMemorySegments({handler:async(_path,{signal})=>{
    speechRequestCount++;
    if(speechRequestCount===1){firstStarted.resolve();await firstGate.promise;if(signal.aborted){const error=new Error('aborted');error.name='AbortError';throw error;}}
    if(speechRequestCount===2){replacementStarted.resolve();await replacementGate.promise;}
    return fakeWav();
  },ids:[threadId,requestId,'33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444','55555555-5555-4555-8555-555555555555']});
  const oldRequest=h.controller.speakMemorySegment(0,0);await firstStarted.promise;
  assert.equal(await h.controller.savedMemorySegmentReadingCapabilities(),true,'refresh resets and then requalifies the current segment capability');
  const replacement=h.controller.speakMemorySegment(0,0);await replacementStarted.promise;
  assert.equal(h.calls.find(item=>item.path.endsWith('/segments/0/speech')).signal.aborted,true,'the old segment request was aborted by refresh');
  firstGate.resolve();await assert.rejects(oldRequest);
  assert.equal(h.controller.state().segmentMemorySpeechOrdinal,0,'old finally preserves the replacement request ordinal');
  assert.equal(h.controller.state().segmentMemorySpeechIndex,0,'old finally preserves the replacement request index');
  await assert.rejects(h.controller.speakMemorySegment(0,0),error=>error.code==='invalid_input','a third direct request stays blocked while replacement playback is unresolved');
  replacementGate.resolve();const ready=await replacement;assert.equal(ready.segmentCount,3);
  assert.equal(h.controller.state().segmentMemorySpeechIndex,null,'the owning completion clears its marker');
});

test('explicit fresh card opening speech posts only bound identities and validates private audio',async()=>{
  const h=await preparedMemoryOpening();assert.equal(h.controller.state().savedMemoryReadingReady,true);
  const audio=await h.controller.speakMemoryOpening(0);assert.equal(audio instanceof Blob,true);
  const call=h.calls.at(-1);assert.equal(call.path,`/assistant/workspace/v1/threads/${threadId}/requests/${requestId}/memory-cards/0/speech`);
  assert.deepEqual(call.body,{library_id:library,expected_revision:1});
  assert.deepEqual(call.extraHeaders,{'X-PhotoHouse-Request-Id':'33333333-3333-4333-8333-333333333333','X-PhotoHouse-Parent-Request-Id':requestId});
  assert.equal(call.responseType,'blob');assert.equal(Object.hasOwn(call.body,'text'),false);assert.equal(Object.hasOwn(call.body,'title'),false);
  assert.equal(h.controller.state().openingMemorySpeechOrdinal,null);
  for(const headers of [{'X-PhotoHouse-Tracking':'disabled'},{'X-PhotoHouse-Receipt-Status':'failed'},{'Cache-Control':'private, no-cache'},{'Content-Type':'application/json'}]){
    const bad=await preparedMemoryOpening({speechHeaders:headers});
    await assert.rejects(bad.controller.speakMemoryOpening(0),error=>error.code==='invalid_response');
  }
  const missing=await preparedMemoryOpening({autoSpeechResponse:false});await assert.rejects(missing.controller.speakMemoryOpening(0),error=>error.code==='invalid_response');
});

test('opening speech loses late bytes after a new turn, Stop, history read, or scope change',async()=>{
  for(const interrupt of ['turn','stop','history','scope']){
    const gate=deferred(),started=deferred();
    const h=await preparedMemoryOpening({handler:async()=>{started.resolve();await gate.promise;return fakeWav();},ids:[threadId,requestId,'33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444']});
    const opening=h.controller.speakMemoryOpening(0);await started.promise;
    if(interrupt==='turn')await h.controller.send('another search');
    else if(interrupt==='stop')h.controller.discardSpeechSource();
    else if(interrupt==='history')await h.controller.read(threadId,{hydrate:false});
    else h.setScope({account:'account-b',library:'library-b',generation:2});
    gate.resolve();await assert.rejects(opening);
    if(interrupt==='turn')assert.equal(h.controller.state().currentResult.kind,'memory_cards');
    if(interrupt==='scope')assert.equal(h.controller.state().currentResult,null);
  }
});

test('late opening finally from a refreshed probe cannot clear a same-card retry marker',async()=>{
  const firstGate=deferred(),firstStarted=deferred(),retryGate=deferred(),retryStarted=deferred();let speechRequestCount=0;
  const h=await preparedMemoryOpening({handler:async(_path,{signal})=>{
    speechRequestCount++;
    if(speechRequestCount===1){firstStarted.resolve();await firstGate.promise;if(signal.aborted){const error=new Error('aborted');error.name='AbortError';throw error;}}
    if(speechRequestCount===2){retryStarted.resolve();await retryGate.promise;}
    return fakeWav();
  },ids:[threadId,requestId,'33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444','55555555-5555-4555-8555-555555555555']});
  const oldRequest=h.controller.speakMemoryOpening(0);await firstStarted.promise;
  assert.equal(await h.controller.savedMemoryReadingCapabilities(),true,'reader capability refresh requalifies the current source');
  const retry=h.controller.speakMemoryOpening(0);await retryStarted.promise;
  assert.equal(h.calls.find(item=>item.path.endsWith('/memory-cards/0/speech')).signal.aborted,true,'refresh aborted the earlier opening request');
  firstGate.resolve();await assert.rejects(oldRequest);
  assert.equal(h.controller.state().openingMemorySpeechOrdinal,0,'old finally preserves the replacement opening marker');
  await assert.rejects(h.controller.speakMemoryOpening(0),error=>error.code==='invalid_input','a third opening request stays blocked while retry is unresolved');
  retryGate.resolve();assert.equal(await retry instanceof Blob,true);
  assert.equal(h.controller.state().openingMemorySpeechOrdinal,null,'the owning opening completion clears its marker');
});

test('reading probe revocation and authorization denial clear active opening capability',async()=>{
  const gate=deferred(),started=deferred();let readingAvailable=true;
  const h=harness(async(path,options)=>{
    if(path.includes('/saved-memory-reading-capabilities'))return savedMemoryReadingCapabilities(readingAvailable);
    if(path.includes('/saved-memory-speech-capabilities'))return savedMemorySpeechCapabilities(true);
    if(path.includes('/saved-memory-capabilities'))return savedMemoryCapabilities(true);
    if(path.includes('/capabilities?'))return workspaceCaps({reply_speech:true});
    if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread()};
    if(path.endsWith('/turns'))return {...envelope('completed',false,1),result:memoryResult()};
    if(path.includes('/memory-cards/0/speech')){started.resolve();await gate.promise;return fakeWav();}
    throw Error(`unexpected ${path}`);
  },{ids:[threadId,requestId,'33333333-3333-4333-8333-333333333333']});
  await h.controller.capabilities();await h.controller.savedMemoryCapabilities();await h.controller.savedMemoryReadingCapabilities();await h.controller.create();await h.controller.send('search saved memories');
  const pending=h.controller.speakMemoryOpening(0);await started.promise;readingAvailable=false;
  assert.equal(await h.controller.savedMemoryReadingCapabilities(),false);assert.equal(h.calls.find(call=>call.path.includes('/memory-cards/0/speech')).signal.aborted,true);
  gate.resolve();await assert.rejects(pending);assert.equal(h.controller.state().savedMemoryReadingReady,false);
  const denied=await preparedMemoryOpening({handler:async()=>{throw Object.assign(new Error('authorization lost'),{status:403});}});
  await assert.rejects(denied.controller.speakMemoryOpening(0),error=>error.code==='access_denied');assert.equal(denied.controller.state().locked,true);
});
