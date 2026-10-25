import test from 'node:test';
import assert from 'node:assert/strict';
import Private from '../../backend/app/ui/access/assistant-private-workspace.js';
const library='family-a',tid='11111111-1111-4111-8111-111111111111',rid='22222222-2222-4222-8222-222222222222';
const hash='a'.repeat(64),fp='b'.repeat(64),query='孩子 flying a kite 蓝桥旁';
const caps={version:1,available:true,threads:true,preferences:true,preferences_applied:true,server_owned_turns:true,reply_speech:true,search:{version:3,date_basis:'capture',perspective:null}};
const sceneCaps={version:1,available:true,search_version:4,media:['image']};
const thread=revision=>({thread_id:tid,library_id:library,revision,created_at:'2032-09-01T00:00:00Z',updated_at:'2032-09-01T00:00:00Z',expires_at:'2032-10-01T00:00:00Z'});
const filters={media:['image'],people:{ids:['301'],match:'any'},date:{from:'2032-09-01',to:'2032-09-30'}};
const interpretation={date_basis:'capture',people:[{id:'301',label:'Sample Child / 示例儿童'}],tags:[],locations:[],perspective:null};
const item={id:'101',kind:'image',width:640,height:480,duration_sec:null,taken_at:'2032-09-01',thumbnail_url:'/assets/101/thumbnail?library=family-a',match_reasons:[]};
function ordinary(){return {version:3,kind:'results',reply:'Found.',context:{library_id:library,binding:hash,fingerprint:fp,filters:structuredClone(filters),visible_ids:['101'],total:1,search_version:3},filters:structuredClone(filters),items:[structuredClone(item)],total:1,has_more:false,effect:null,interpretation:structuredClone(interpretation)};}
function scene(){const base=ordinary();return {...base,version:4,context:{...base.context,search_version:4,scene:{version:1,query,scope:structuredClone(base.context),scores:[.75]}},items:[{...base.items[0],semantic_score:.75}],semantic:{mode:'text_to_image',score_kind:'cosine',candidate_count:1,coverage:'complete_eligible_images',needs_review:true}};}
function largeScene(total=100000){const value=scene(),ids=Array.from({length:20},(_,i)=>String(101+i));value.context.total=total;value.context.scene.scope.total=total;value.context.visible_ids=ids;value.context.scene.scope.visible_ids=ids;value.context.scene.scores=ids.map(()=>.75);value.items=ids.map((id)=>({...structuredClone(item),id,thumbnail_url:`/assets/${id}/thumbnail?library=${library}`,semantic_score:.75}));value.total=total;value.has_more=true;value.semantic.candidate_count=total;return value;}
const env=(result,id=rid,recovered=false)=>({version:1,thread_id:tid,request_id:id,status:'completed',revision:result.version===4?2:1,recovered,error:null,result});
const failed=(id=rid,recovered=false,code='scene_query_unsupported',revision=1)=>({version:1,thread_id:tid,request_id:id,status:'failed',revision,recovered,error:code,result:null});
const error=(status,code='unavailable')=>Object.assign(new Error(code),{status,code});
function setup({probe=sceneCaps,turn=null,read=null,detail=null}={}){
 const calls=[],scope={account:'fictional',library,generation:1,locked:false};let n=0;
 const request=async(path,options)=>{calls.push({path,...options});
  if(path.includes('/scene-search-capabilities?')){if(probe instanceof Error)throw probe;return typeof probe==='function'?probe():probe;}
  if(path.includes('/capabilities?'))return caps;
  if(path.endsWith('/threads')&&options.method==='POST')return {version:1,thread:thread(0)};
  if(path.includes('/threads/')&&options.method==='DELETE')return {deleted:true,thread_id:tid};
  if(path.endsWith('/turns')){if(options.extraHeaders?.['X-PhotoHouse-Search-Version']==='4'){if(turn) return turn(options);return env(scene(),options.body.request_id);}return env(ordinary(),options.body.request_id);}
  if(path.includes('/requests/'))return read?read(path,options):env(scene(),path.split('/requests/')[1].split('?')[0],true);
  if(path.includes('/threads/'))return detail?detail(path,options):{version:1,thread:thread(2),exchanges:[],latest_request_id:rid};
  throw Error('unexpected fixture request');
 };
 const c=Private.createController({scope:()=>scope,request,newUUID:()=>n++===0?tid:rid});
 return {c,calls,scope};
}
async function ready(f){await f.c.capabilities();await f.c.sceneCapabilities();await f.c.create();await f.c.send('find photos of Sample Child in September 2032');assert.equal(f.c.state().sceneReady,true);}
test('scene capability is separate and closed; ordinary negotiation rejects v4',()=>{
 assert.equal(Private.validateSceneCapabilities(sceneCaps).available,true);
 for(const bad of [{...sceneCaps,search_version:3},{...sceneCaps,media:['video']},{...sceneCaps,extra:true},{...sceneCaps,available:1}])assert.throws(()=>Private.validateSceneCapabilities(bad));
 assert.throws(()=>Private.validateCapabilities({...caps,search:{version:4,date_basis:'capture',perspective:null}}));
});
test('v4 requires explicit negotiation and validates complete scope, scores and presentation',()=>{
 const value=scene();assert.equal(Private.validateResult(value,library,false,false,false,4).version,4);
 assert.throws(()=>Private.validateResult(value,library,false,false,false,3));
 assert.throws(()=>Private.validateResult(ordinary(),library,false,false,false,4));
 assert.equal(Private.validateResult(ordinary(),library,true,false,false,4).version,3);
 const mutations=[v=>v.effect={type:'open_asset',asset_id:'101'},v=>v.kind='clarification',v=>v.items[0].kind='video',v=>v.items[0].semantic_score=Infinity,v=>v.items[0].semantic_score=.5,v=>v.context.scene.scores=[1.01],v=>v.context.scene.scope.library_id='other',v=>v.context.scene.scope.search_version=4,v=>v.context.scene.query='x\ny',v=>v.context.scene.query='中'.repeat(171),v=>v.context.scene.extra=true,v=>v.filters.people.ids=['302'],v=>v.interpretation.people[0].id='302',v=>v.semantic.needs_review=false,v=>v.semantic.candidate_count=2,v=>v.semantic.coverage='partial',v=>v.semantic.extra=true,v=>v.context.scene.scope.filters.media=['video'],v=>v.context.scene.scope.filters.descriptive={version:1,concepts:[{surface:'beach',alternatives:['beach']}]},v=>v.items[0].thumbnail_url='/assets/101/thumbnail?library=other'];
 for(const mutate of mutations){const bad=scene();mutate(bad);assert.throws(()=>Private.validateResult(bad,library,false,false,false,4));}
});
test('semantic coverage details are optional, exact, bounded and cross-validated',()=>{
 const legacy=Private.validateResult(scene(),library,false,false,false,4);assert.deepEqual(Object.keys(legacy.semantic),['mode','score_kind','candidate_count','coverage','needs_review']);
 const complete=scene();complete.semantic.coverage_details={version:1,policy_sha256:'c'.repeat(64),state:'complete',catalog_images:100,searchable_images:100,omitted_images:0,matched_omitted_images:0};
 const parsedComplete=Private.validateResult(complete,library,false,false,false,4);assert.equal(parsedComplete.semantic.coverage_details.state,'complete');assert.ok(Object.isFrozen(parsedComplete.semantic.coverage_details));
 const partial=scene();partial.semantic.coverage_details={version:1,policy_sha256:'a'.repeat(64),state:'partial',catalog_images:100,searchable_images:90,omitted_images:10,matched_omitted_images:2};
 assert.equal(Private.validateResult(partial,library,false,false,false,4).semantic.coverage_details.omitted_images,10);
 const large=Private.validateResult(largeScene(),library,false,false,false,4);assert.equal(large.total,100000);assert.equal(large.items.length,20);
 const invalid=[
  {...partial.semantic.coverage_details,version:2},
  {...partial.semantic.coverage_details,policy_sha256:'A'.repeat(64)},
  {...partial.semantic.coverage_details,policy_sha256:'c'.repeat(63)},
  {...partial.semantic.coverage_details,state:'complete'},
  {...partial.semantic.coverage_details,extra:false},
  {...partial.semantic.coverage_details,catalog_images:true},
  {...partial.semantic.coverage_details,catalog_images:1.5},
  {...partial.semantic.coverage_details,catalog_images:100001},
  {...complete.semantic.coverage_details,searchable_images:0},
  {...partial.semantic.coverage_details,searchable_images:91},
  {...partial.semantic.coverage_details,omitted_images:0},
  {...partial.semantic.coverage_details,matched_omitted_images:11},
  {...partial.semantic.coverage_details,searchable_images:100,omitted_images:0,matched_omitted_images:0}
 ];
 for(const details of invalid){const bad=scene();bad.semantic.coverage_details=details;assert.throws(()=>Private.validateResult(bad,library,false,false,false,4));}
 const tooManyCandidates=scene();tooManyCandidates.semantic.coverage_details={...partial.semantic.coverage_details,searchable_images:0,omitted_images:100};assert.throws(()=>Private.validateResult(tooManyCandidates,library,false,false,false,4));
 const tooManyCombined=largeScene(99);tooManyCombined.semantic.coverage_details={...partial.semantic.coverage_details,catalog_images:100,searchable_images:90,omitted_images:10,matched_omitted_images:2};assert.throws(()=>Private.validateResult(tooManyCombined,library,false,false,false,4));
 const unsafeCandidate=scene();unsafeCandidate.semantic.candidate_count=Number.MAX_SAFE_INTEGER+1;assert.throws(()=>Private.validateResult(unsafeCandidate,library,false,false,false,4));
});
test('scene POST sends only exact opt-in and bound revision, preserves main draft and never offers speech',async()=>{
 const f=setup();await ready(f);f.c.setDraft('unsent ordinary conditions');f.c.setSceneDraft(query);await f.c.sendScene();
 const sent=f.calls.filter(c=>c.path.endsWith('/turns')).at(-1);
 assert.equal(sent.extraHeaders['X-PhotoHouse-Search-Version'],'4');assert.deepEqual(sent.body,{library_id:library,request_id:rid,expected_revision:1,text:query,accepts:['scene_search_v1']});
 assert.equal(f.c.state().draft,'unsent ordinary conditions');assert.equal(f.c.state().sceneDraft,'');assert.equal(f.c.state().speechReady,false);await assert.rejects(f.c.speakReply());
 f.c.close();
});
test('lost scene POST recovers GET-only with original v4 after capability loss and preserves input edit',async()=>{
 const f=setup({turn:()=>{throw error(503);}});await ready(f);f.c.setSceneDraft(query);await assert.rejects(f.c.sendScene());
 assert.equal(f.c.state().pendingTurn.search_version,4);assert.equal(f.c.state().currentResult,null);assert.equal(f.c.state().sceneReady,false);assert.equal(f.c.state().sceneRewordRequired,false);
 await f.c.capabilities();f.c.setSceneDraft('a different draft');await f.c.recover(tid,rid);
 assert.equal(f.c.state().sceneDraft,'a different draft');assert.equal(f.c.state().currentResult.version,4);assert.equal(f.c.state().speechReady,false);
 const reads=f.calls.filter(c=>c.path.includes('/requests/'));assert.equal(reads.length,1);assert.equal(reads[0].extraHeaders['X-PhotoHouse-Search-Version'],'4');assert.equal(f.calls.filter(c=>c.path.endsWith('/turns')).length,2);f.c.close();
});
test('durable unsupported scene failure clears results, keeps both drafts, and only reload unlocks explicit rewording',async()=>{
 let scenePosts=0;const f=setup({turn:options=>{if(scenePosts++===0)return failed(options.body.request_id);const result=scene();result.context.scene.query=options.body.text;return {...env(result,options.body.request_id),revision:2};},read:path=>{if(!path.includes('/requests/'))return null;return {...env(scene(),path.split('/requests/')[1].split('?')[0],true),revision:1};},detail:()=>({version:1,thread:thread(1),exchanges:[],latest_request_id:rid})});
 await ready(f);f.c.setDraft('unsent ordinary conditions');f.c.setSceneDraft(query);const envelope=await f.c.sendScene();
 assert.equal(envelope.status,'failed');assert.equal(envelope.error,'scene_query_unsupported');assert.equal(f.c.state().pendingTurn,null);
 assert.equal(f.c.state().currentResult,null);assert.equal(f.c.state().sceneDraft,query);assert.equal(f.c.state().draft,'unsent ordinary conditions');
 assert.equal(f.c.state().sceneRewordRequired,true);assert.equal(f.c.state().sceneReady,false);
 const posts=f.calls.filter(c=>c.path.endsWith('/turns')).length;await assert.rejects(f.c.sendScene('another wording'));assert.equal(f.calls.filter(c=>c.path.endsWith('/turns')).length,posts);
 f.c.setSceneDraft('reword typed before reload');const getsBeforeReload=f.calls.filter(c=>c.method==='GET').length;await f.c.read(tid,{sceneReloadGuard:true});assert.equal(f.c.state().sceneDraft,'reword typed before reload');assert.equal(f.c.state().sceneRewordRequired,false);assert.equal(f.c.state().sceneReady,true);assert.equal(f.c.state().currentResult.version,4);
 const result=await f.c.sendScene();assert.equal(result.status,'completed');
 const sent=f.calls.filter(c=>c.path.endsWith('/turns')).at(-1);assert.equal(sent.body.text,'reword typed before reload');assert.deepEqual(sent.body.accepts,['scene_search_v1']);
 assert.equal(sent.body.expected_revision,1);assert.equal(f.c.state().draft,'unsent ordinary conditions');assert.equal(f.c.state().sceneDraft,'');
 assert.equal(f.calls.filter(c=>c.path.includes('/requests/')).length,1);assert.equal(f.calls.filter(c=>c.method==='GET').length-getsBeforeReload,3);f.c.close();
});
test('opt-in thread read restores only the newest refusal cue and never hydrates the older result',async()=>{
 const cue={version:1,request_id:rid,revision:1,query:'a dog not on grass'};
 const f=setup({turn:options=>failed(options.body.request_id),
  read:path=>({...env(scene(),path.split('/requests/')[1].split('?')[0],true),revision:1}),
  detail:()=>({version:1,thread:thread(1),exchanges:[],latest_request_id:rid,scene_reword:cue})});
 await ready(f);f.c.setDraft('ordinary draft');f.c.setSceneDraft(query);await f.c.sendScene();
 f.c.setSceneDraft('');
 const before=f.calls.filter(c=>c.path.includes('/requests/')).length;
 const restored=await f.c.read(tid);
 const threadRead=f.calls.filter(c=>c.path.includes('/threads/')&&!c.path.includes('/requests/')).at(-1);
 assert.equal(threadRead.extraHeaders['X-PhotoHouse-Search-Version'],undefined);
 assert.equal(threadRead.extraHeaders['X-PhotoHouse-Scene-Reword-Version'],'1');
 assert.equal(restored.scene_reword.query,cue.query);assert.equal(f.c.state().sceneDraft,cue.query);
 assert.equal(f.c.state().sceneRewordRequired,true);assert.equal(f.c.state().currentResult,null);
 assert.equal(f.c.state().contextState,'requires_search');
 assert.equal(f.calls.filter(c=>c.path.includes('/requests/')).length,before);
 const posts=f.calls.filter(c=>c.path.endsWith('/turns')).length;
 f.c.setSceneDraft('reword typed after reload');
 await f.c.read(tid,{sceneReloadGuard:true});
 assert.equal(f.c.state().sceneDraft,'reword typed after reload');
 assert.equal(f.c.state().sceneRewordRequired,false);assert.equal(f.c.state().currentResult.version,4);
 assert.equal(f.calls.filter(c=>c.path.endsWith('/turns')).length,posts);
 await f.c.sendScene();
 assert.equal(f.calls.filter(c=>c.path.endsWith('/turns')).at(-1).body.text,'reword typed after reload');
 assert.equal(f.c.state().draft,'ordinary draft');f.c.close();
});
test('opt-in thread read rejects malformed refusal projection without publishing it',async()=>{
 for(const scene_reword of [
  {version:1,request_id:rid,revision:0,query:'a dog not on grass'},
  {version:1,request_id:rid,revision:1,query:'bad\nquery'},
  {version:1,request_id:rid,revision:1,query:'a'.repeat(513)},
  {version:1,request_id:rid,revision:1,query:'a dog not on grass',extra:true}
 ]){
  const f=setup({detail:()=>({version:1,thread:thread(1),exchanges:[],latest_request_id:null,scene_reword})});
  await ready(f);await assert.rejects(f.c.read(tid),error=>error.code==='invalid_response');
  assert.equal(f.c.state().sceneDraft,'');assert.equal(f.c.state().sceneRewordRequired,false);f.c.close();
 }
});
test('thread-read confirmation binds the cue identity as well as revision and completed pointer',async()=>{
 for(const guarded of [false,true]){
  const firstCue={version:1,request_id:rid,revision:1,query:'a dog not on grass'};
  const secondCue={version:1,request_id:'33333333-3333-4333-8333-333333333333',revision:1,query:'a phone not in a house'};
  let details=0;
  const f=setup({turn:options=>failed(options.body.request_id),
   read:path=>({...env(scene(),path.split('/requests/')[1].split('?')[0],true),revision:1}),
   detail:()=>({version:1,thread:thread(1),exchanges:[],latest_request_id:rid,scene_reword:++details===1?firstCue:secondCue})});
  await ready(f);await f.c.sendScene(query);f.c.setSceneDraft('edited draft survives cue change');
  const posts=f.calls.filter(c=>c.path.endsWith('/turns')).length;
  await assert.rejects(f.c.read(tid,{sceneReloadGuard:guarded}),error=>error.code==='conflict');
  assert.equal(details,2);assert.equal(f.c.state().sceneDraft,'edited draft survives cue change');
  assert.equal(f.c.state().sceneRewordRequired,true);assert.equal(f.c.state().currentResult,null);
  assert.equal(f.c.state().contextState,'requires_search');
  assert.equal(f.calls.filter(c=>c.path.endsWith('/turns')).length,posts);f.c.close();
 }
});
test('refusal draft is retained as read-only guidance when scene capability is unavailable',async()=>{
 const cue={version:1,request_id:rid,revision:1,query:'a dog not on grass'};
 const f=setup({probe:{...sceneCaps,available:false},detail:()=>({version:1,thread:thread(1),exchanges:[],latest_request_id:rid,scene_reword:cue})});
 await f.c.capabilities();assert.equal(await f.c.sceneCapabilities(),false);await f.c.create();
 const detail=await f.c.read(tid);
 const threadRead=f.calls.filter(c=>c.path.includes('/threads/')&&!c.path.includes('/requests/')).at(-1);
 assert.equal(threadRead.extraHeaders['X-PhotoHouse-Scene-Reword-Version'],'1');
 assert.equal(f.c.state().sceneAvailable,false);assert.equal(f.c.state().sceneDraft,cue.query);
 assert.equal(f.c.state().sceneRewordRequired,true);assert.equal(f.c.state().sceneReady,false);
 assert.equal(f.c.state().currentResult,null);assert.equal(detail.scene_reword.query,cue.query);f.c.close();
});
test('lost unsupported scene response is resolved by one v4 GET and preserves a newer draft edit',async()=>{
 const f=setup({turn:()=>{throw error(503);},read:path=>path.includes('/requests/')?failed(path.split('/requests/')[1].split('?')[0],true):env(ordinary(),rid,true)});
 await ready(f);f.c.setSceneDraft(query);await assert.rejects(f.c.sendScene());f.c.setSceneDraft('edited after response was lost');
 const getsBefore=f.calls.filter(c=>c.method==='GET').length;const recovered=await f.c.recover(tid,rid);
 assert.equal(recovered.status,'failed');assert.equal(recovered.error,'scene_query_unsupported');assert.equal(f.c.state().pendingTurn,null);
 assert.equal(f.c.state().sceneDraft,'edited after response was lost');assert.equal(f.c.state().sceneRewordRequired,true);assert.equal(f.c.state().currentResult,null);
 const gets=f.calls.filter(c=>c.method==='GET').slice(getsBefore);assert.equal(gets.length,1);assert.equal(gets[0].extraHeaders['X-PhotoHouse-Search-Version'],'4');
 assert.equal(f.calls.filter(c=>c.path.endsWith('/turns')).length,2);f.c.close();
});
test('reword hint survives a stale reload and clears with a source change without restoring cards',async()=>{
 const stale=setup({turn:options=>failed(options.body.request_id),read:path=>path.includes('/requests/')?({...env(scene(),path.split('/requests/')[1].split('?')[0],true),revision:1}):{version:1,thread:thread(3),exchanges:[],latest_request_id:rid}});
 await ready(stale);await stale.c.sendScene(query);assert.equal(stale.c.state().sceneRewordRequired,true);
 await assert.rejects(stale.c.read(tid,{sceneReloadGuard:true}));assert.equal(stale.c.state().sceneRewordRequired,true);assert.equal(stale.c.state().currentResult,null);assert.equal(stale.c.state().sceneReady,false);stale.c.close();
 const changed=setup({turn:options=>failed(options.body.request_id)});await ready(changed);await changed.c.sendScene(query);assert.equal(changed.c.state().sceneRewordRequired,true);
 changed.scope.library='another-library';changed.scope.generation++;const snapshot=changed.c.state();
 assert.equal(snapshot.sceneRewordRequired,false);assert.equal(snapshot.currentResult,null);assert.equal(snapshot.sceneDraft,'');assert.equal(snapshot.draft,'');changed.c.close();
});
test('guarded reload rejects a latest-request change and never publishes hydrated stale cards',async()=>{
 let detailReads=0;const replacement='33333333-3333-4333-8333-333333333333';
 const f=setup({turn:options=>failed(options.body.request_id),read:path=>({...env(scene(),path.split('/requests/')[1].split('?')[0],true),revision:1}),detail:()=>({version:1,thread:thread(1),exchanges:[],latest_request_id:++detailReads===1?rid:replacement})});
 await ready(f);await f.c.sendScene(query);assert.equal(f.c.state().sceneRewordRequired,true);
 await assert.rejects(f.c.read(tid,{sceneReloadGuard:true}),error=>error.code==='conflict');
 assert.equal(detailReads,2);assert.equal(f.c.state().sceneRewordRequired,true);assert.equal(f.c.state().currentResult,null);assert.equal(f.c.state().sceneReady,false);f.c.close();
});
test('deleting the active thread clears its scene reword hint',async()=>{
 const f=setup({turn:options=>failed(options.body.request_id)});await ready(f);await f.c.sendScene(query);assert.equal(f.c.state().sceneRewordRequired,true);
 await f.c.delete(tid);assert.equal(f.c.state().activeThread,null);assert.equal(f.c.state().sceneRewordRequired,false);f.c.close();
});
test('scene unsupported error requires the failed status and v4 negotiation',()=>{
 const bad=failed();assert.throws(()=>Private.validateEnvelope(bad,tid,rid,library,'POST',false,false,3));
 assert.throws(()=>Private.validateEnvelope({...bad,status:'completed'},tid,rid,library,'POST',false,false,4));
 assert.throws(()=>Private.validateEnvelope({...bad,error:'unsupported_query'},tid,rid,library,'POST',false,false,4));
});
test('unsupported receipt revision mismatch remains uncertain and does not offer reword reload',async()=>{
 const fresh=setup({turn:options=>failed(options.body.request_id,false,'scene_query_unsupported',2)});await ready(fresh);fresh.c.setSceneDraft(query);
 await assert.rejects(fresh.c.sendScene(),error=>error.code==='invalid_response');assert.equal(fresh.c.state().pendingTurn.status,'uncertain');assert.equal(fresh.c.state().sceneRewordRequired,false);fresh.c.close();
 const recovered=setup({turn:()=>{throw error(503);},read:path=>path.includes('/requests/')?failed(path.split('/requests/')[1].split('?')[0],true,'scene_query_unsupported',2):env(ordinary(),rid,true)});
 await ready(recovered);recovered.c.setSceneDraft(query);await assert.rejects(recovered.c.sendScene());await assert.rejects(recovered.c.recover(tid,rid),error=>error.code==='invalid_response');
 assert.equal(recovered.c.state().pendingTurn.status,'uncertain');assert.equal(recovered.c.state().sceneRewordRequired,false);recovered.c.close();
});
test('reopen uses v4 only after optional probe and restores no speech or action',async()=>{
 const f=setup();await f.c.capabilities();await f.c.sceneCapabilities();const detail=await f.c.read(tid);
 assert.equal(detail.current_result.version,4);assert.equal(f.c.state().speechReady,false);assert.equal(f.calls.find(c=>c.path.includes('/requests/')).extraHeaders['X-PhotoHouse-Search-Version'],'4');f.c.close();
});
test('404 and old-route 403 probe leave ordinary search and main draft usable',async()=>{
 for(const status of [404,403]){const f=setup({probe:error(status)});await f.c.capabilities();f.c.setDraft('kept');assert.equal(await f.c.sceneCapabilities(),false);assert.equal(f.c.state().locked,false);assert.equal(f.c.state().draft,'kept');await f.c.create();await f.c.send('photos');assert.equal(f.c.state().currentResult.version,3);f.c.close();}
});
test('true authorization denial clears both drafts and all scoped results',async()=>{
 const f=setup({probe:error(401)});await f.c.capabilities();f.c.setDraft('private');f.c.setSceneDraft('private scene');await assert.rejects(f.c.sceneCapabilities());assert.equal(f.c.state().locked,true);assert.equal(f.c.state().draft,'');assert.equal(f.c.state().sceneDraft,'');f.c.close();
});
test('clarification retaining old cards, video and descriptive scopes cannot enable scene action',async()=>{
 for(const change of [v=>v.kind='clarification',v=>{v.filters.media=['video'];v.context.filters.media=['video'];},v=>{const desc={version:1,concepts:[{surface:'beach',alternatives:['beach']}]};v.filters.descriptive=desc;v.context.filters.descriptive=desc;}]){
  const f=setup({read:()=>{const v=ordinary();change(v);return env(v,rid,true);}});await f.c.capabilities();await f.c.sceneCapabilities();await f.c.read(tid);assert.equal(f.c.state().sceneReady,false);await assert.rejects(f.c.sendScene(query));assert.equal(f.calls.filter(c=>c.path.endsWith('/turns')).length,0);f.c.close();
 }
});
test('scene input rejects control and UTF8 overflow before request allocation',async()=>{
 const f=setup();await ready(f);const before=f.calls.length;
 for(const text of ['','a\nb','a\tb','a\u0085b','中'.repeat(171)])await assert.rejects(f.c.sendScene(text));
 assert.equal(f.calls.length,before);f.c.close();
});
test('late scene response after account/library change cannot restore content',async()=>{
 let finish;const f=setup({turn:()=>new Promise(resolve=>finish=resolve)});await ready(f);f.c.setSceneDraft(query);const pending=f.c.sendScene();f.scope.library='other';f.scope.generation++;f.c.state();finish(env(scene()));await assert.rejects(pending);assert.equal(f.c.state().currentResult,null);assert.equal(f.c.state().sceneDraft,'');assert.equal(f.c.state().sceneAvailable,false);f.c.close();
});
test('out-of-order scene probes cannot re-enable a revoked feature',async()=>{
 let finish;let n=0;const f=setup({probe:()=>n++===0?new Promise(resolve=>finish=resolve):{...sceneCaps,available:false}});await f.c.capabilities();const old=f.c.sceneCapabilities();assert.equal(await f.c.sceneCapabilities(),false);finish(sceneCaps);await old;assert.equal(f.c.state().sceneAvailable,false);f.c.close();
});
test('abandoning a scene request does not turn its visual text into ordinary hard conditions',async()=>{
 const f=setup({turn:()=>{throw error(503);}});await ready(f);f.c.setDraft('ordinary draft');f.c.setSceneDraft(query);await assert.rejects(f.c.sendScene());assert.equal(f.c.abandonPending(),'ordinary draft');assert.equal(f.c.state().sceneDraft,query);f.c.close();
});
test('fresh response must retain exact query, original scope and next revision',async()=>{
 for(const mutate of [v=>v.result.context.scene.query='different scene',v=>v.result.context.scene.scope.fingerprint='c'.repeat(64),v=>v.revision=9]){
  const f=setup({turn:o=>{const value=env(scene(),o.body.request_id);mutate(value);return value;}});await ready(f);f.c.setSceneDraft(query);await assert.rejects(f.c.sendScene(),e=>e.code==='invalid_response');assert.equal(f.c.state().currentResult,null);assert.equal(f.c.state().pendingTurn.search_version,4);assert.equal(f.c.state().sceneDraft,query);f.c.close();
 }
});
test('definitive 400/409 refusals do not strand an unaccepted request in recovery',async()=>{
 for(const status of [400,409]){
  const f=setup({turn:()=>{throw error(status,'invalid_request');}});await ready(f);f.c.setSceneDraft(query);await assert.rejects(f.c.sendScene(),e=>e.status===status);assert.equal(f.c.state().pendingTurn,null);assert.equal(f.c.state().sceneDraft,query);assert.equal(f.c.state().currentResult,null);assert.equal(f.c.state().historyRefreshRequired,true);await f.c.send('find photos of Sample Child');assert.equal(f.c.state().currentResult.version,3);assert.equal(f.calls.filter(c=>c.path.includes('/requests/')).length,0);f.c.close();
 }
});
