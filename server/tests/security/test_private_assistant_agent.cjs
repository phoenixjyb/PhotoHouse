'use strict';
const assert=require('node:assert/strict');
const PrivateAssistant=require('../../backend/app/ui/access/assistant-private-workspace.js');

const threadId='11111111-1111-4111-8111-111111111111';
const firstId='22222222-2222-4222-8222-222222222222';
const secondId='33333333-3333-4333-8333-333333333333';
const library='family-a',binding='a'.repeat(64),fingerprint='b'.repeat(64);
const filters={media:['image'],text:'family picnic'};
const interpretation={date_basis:'capture',people:[],tags:[],locations:[],perspective:null};
const item={id:'101',kind:'image',width:640,height:480,duration_sec:null,
  taken_at:'2032-09-14T10:00:00Z',thumbnail_url:'/assets/101/thumbnail?library=family-a',
  match_reasons:[]};
function caps(searchVersion=3,available=true){return {version:1,available,threads:true,
  preferences:true,preferences_applied:true,server_owned_turns:true,reply_speech:false,
  search:{version:searchVersion,date_basis:'capture',perspective:null}};}
function result(version=2){
  const context={library_id:library,binding,fingerprint,filters,visible_ids:['101'],total:1,
    search_version:version};
  return {version,kind:'results',reply:'Found one photo.',context,filters,items:[item],
    total:1,has_more:false,effect:null,interpretation};
}
function envelope(id,rid,{recovered=false,revision=1,turn=result()}={}){
  return {version:1,thread_id:id,request_id:rid,status:'completed',revision,recovered,
    error:null,result:turn};
}
function thread(revision=0){return {thread_id:threadId,library_id:library,
  created_at:'2026-10-16T00:00:00Z',updated_at:'2026-10-16T00:00:00Z',
  expires_at:'2026-11-15T00:00:00Z',revision};}
function httpError(status,code){return Object.assign(new Error(code),{status,code});}
function deferred(){let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};}

function makeController({agentError=null,agentResponse=null,base=caps(),failTurn=false,
  pendingAgent=[],agentRequests=null}={}){
  const calls=[],scope={account:'synthetic-account',library,generation:1,locked:false};
  let sequence=0,posts=0,probeNumber=0;
  const ids=[threadId,firstId,secondId];
  const request=async(path,options={})=>{
    const header=options.extraHeaders?.['X-PhotoHouse-Search-Version']??null;
    const call={path,method:options.method,header,body:options.body};calls.push(call);
    if(path.startsWith('/assistant/workspace/v1/capabilities?'))return base;
    if(path.startsWith('/assistant/workspace/v1/agent-capabilities?')){
      assert.equal(options.method,'GET');
      probeNumber++;
      agentRequests?.push(call);
      const pending=pendingAgent[probeNumber-1];
      if(pending)return pending.promise;
      if(agentError)throw agentError;
      return agentResponse||{version:1,available:true,profile:'agent_media_search_v1'};
    }
    if(path.startsWith('/assistant/workspace/v1/saved-memory-capabilities?'))
      return {version:1,available:true};
    if(path==='/assistant/workspace/v1/threads'&&options.method==='POST')
      return {version:1,thread:thread(0)};
    if(path===`/assistant/workspace/v1/threads/${threadId}/turns`){
      posts++;
      if(failTurn)throw httpError(503,'unavailable');
      const version=header==='2'?2:3;
      return envelope(threadId,options.body.request_id,
        {revision:1,turn:result(version)});
    }
    if(path.startsWith(`/assistant/workspace/v1/threads/${threadId}/requests/`)){
      const rid=path.split('/requests/')[1].split('?')[0];
      return envelope(threadId,rid,{recovered:true,revision:1,turn:result(2)});
    }
    throw new Error(`Unexpected request: ${options.method} ${path}`);
  };
  const controller=PrivateAssistant.createController({scope:()=>scope,request,
    newUUID:()=>ids[sequence++]||'44444444-4444-4444-8444-444444444444'});
  return {controller,calls,scope,get posts(){return posts;}};
}

(async()=>{
  {
    const probes=[];
    const {controller,calls}=makeController({agentError:httpError(404,'unavailable'),agentRequests:probes});
    await controller.capabilities();
    assert.equal(controller.state().agentAvailable,false);
    assert.equal(await controller.agentCapabilities(),false);
    assert.equal(controller.state().agentAvailable,false);
    assert.equal(probes.length,1);
    assert.match(probes[0].path,/^\/assistant\/workspace\/v1\/agent-capabilities\?library_id=family-a$/);
    assert.equal(probes[0].header,'2');
    controller.close();
    assert.equal(controller.state().agentAvailable,false);
    assert.equal(calls.filter(call=>call.path.endsWith('/turns')).length,0);
  }
  {
    const baseCaps=caps(),{controller,calls}=makeController({base:baseCaps});
    await controller.capabilities();await controller.agentCapabilities();
    assert.equal(await controller.savedMemoryCapabilities(),true);
    await controller.create();
    const sent=await controller.send('find our picnic',{agent:true});
    assert.equal(sent.result.version,2);
    const turn=calls.find(call=>call.path.endsWith('/turns'));
    assert.equal(turn.header,'2');
    assert.deepEqual(turn.body,{library_id:library,request_id:firstId,expected_revision:0,
      text:'find our picnic',accepts:['agent_media_search_v1']});
    assert.equal(controller.state().currentResult.version,2);
    baseCaps.available=false;await controller.capabilities();
    assert.equal(controller.state().agentAvailable,false,
      'base capability refresh/unavailability invalidates the prior agent result');
    await assert.rejects(controller.send('another query',{agent:true}),error=>error.code==='unavailable');
    assert.equal(calls.filter(call=>call.path.endsWith('/turns')).length,1);
    controller.close();
  }
  {
    const {controller,calls}=makeController();
    await controller.capabilities();await controller.agentCapabilities();await controller.create();
    const sent=await controller.send('find our picnic');
    assert.equal(sent.result.version,3);
    const turn=calls.find(call=>call.path.endsWith('/turns'));
    assert.equal(turn.header,'3');
    assert.deepEqual(turn.body,{library_id:library,request_id:firstId,expected_revision:0,
      text:'find our picnic'});
    controller.close();
  }
  {
    const {controller,calls}=makeController();
    await controller.capabilities();await controller.create();
    await assert.rejects(controller.send('find our picnic',{agent:true}),
      error=>error.code==='unavailable');
    assert.equal(calls.filter(call=>call.path.endsWith('/turns')).length,0,
      'unavailable agent does not fall back to ordinary search');
    controller.close();
  }
  {
    const gate=deferred(),probes=[];
    const {controller,scope}=makeController({pendingAgent:[gate],agentRequests:probes});
    await controller.capabilities();
    const pending=controller.agentCapabilities();
    scope.library='family-b';
    gate.resolve({version:1,available:true,profile:'agent_media_search_v1'});
    await assert.rejects(pending,error=>error.code==='scope_changed');
    assert.equal(controller.state().agentAvailable,false);
    controller.close();
  }
  {
    const first=deferred(),probes=[];
    const {controller}=makeController({pendingAgent:[first],agentRequests:probes});
    await controller.capabilities();
    const older=controller.agentCapabilities();
    assert.equal(await controller.agentCapabilities(),true);
    first.resolve({version:1,available:false,profile:'agent_media_search_v1'});
    assert.equal(await older,true,'stale capability response cannot replace the latest result');
    assert.equal(controller.state().agentAvailable,true);
    assert.equal(probes.length,2);
    controller.close();
  }
  {
    const {controller,calls}=makeController({failTurn:true});
    await controller.capabilities();await controller.agentCapabilities();await controller.create();
    await assert.rejects(controller.send('find our picnic',{agent:true}),error=>error.status===503);
    const pending=controller.state().pendingTurn;
    assert.equal(pending.agent,true);assert.equal(pending.search_version,2);
    const recovered=await controller.recover(threadId,firstId);
    assert.equal(recovered.result.version,2);
    assert.equal(controller.state().pendingTurn,null);
    assert.equal(calls.filter(call=>call.method==='POST'&&call.path.endsWith('/turns')).length,1);
    const readback=calls.find(call=>call.method==='GET'&&call.path.includes('/requests/'));
    assert.equal(readback.header,'2');
    controller.close();
  }
  console.log('Private assistant agent controller checks: optional capability, exact agent send, ordinary send isolation, scope/nonce fencing, and v2 recovery passed.');
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
