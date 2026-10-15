'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

class Node {
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;this.listeners={};this.dataset={};this.attributes={};this.className='';this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.open=false;this.name='';this.type='';this.selected=false;this._text='';}
  get isConnected(){let current=this;while(current?.parentNode)current=current.parentNode;return current===document;}
  set textContent(value){this._text=String(value??'');for(const child of this.children)child.parentNode=null;this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  set innerHTML(_value){throw new Error('innerHTML must not be used');}
  append(...items){for(const item of items){if(!item)continue;if(item.parentNode)item.remove();item.parentNode=this;this.children.push(item);if(this.tagName==='SELECT'&&(item.selected||!this.value))this.value=item.value;}}
  replaceChildren(...items){this.textContent='';this.append(...items);}
  replaceWith(...items){if(!this.parentNode)return;const parent=this.parentNode;let index=parent.children.indexOf(this);this.remove();for(const item of items){if(item.parentNode)item.remove();item.parentNode=parent;parent.children.splice(index++,0,item);}}
  remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(child=>child!==this);this.parentNode=null;}}
  setAttribute(key,value){this.attributes[key]=String(value);}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  async dispatch(name,extra={}){if(name==='click'&&this.disabled)return;for(const fn of this.listeners[name]||[])await fn({preventDefault(){},target:this,...extra});if(name==='click'&&this.tagName==='BUTTON'&&this.type==='submit'){let form=this.parentNode;while(form&&form.tagName!=='FORM')form=form.parentNode;if(form)await form.dispatch('submit');}}
  matches(selector){if(selector.startsWith('.'))return this.className.split(/\s+/).includes(selector.slice(1));if(selector==='input,select,button')return ['INPUT','SELECT','BUTTON'].includes(this.tagName);if(selector==='input')return this.tagName==='INPUT';if(selector==='select')return this.tagName==='SELECT';if(selector==='button')return this.tagName==='BUTTON';if(selector==='form')return this.tagName==='FORM';if(/^[a-z][a-z0-9]*$/i.test(selector))return this.tagName===selector.toUpperCase();return false;}
  querySelectorAll(selector){const out=[];for(const child of this.children){if(child.matches(selector))out.push(child);out.push(...child.querySelectorAll(selector));}return out;}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
const document=new Node('document');document.createElement=tag=>new Node(tag);
const scope={account:'member-1',library:'library-1',language:'zh',epoch:3,locked:false};
const asset={id:'101',kind:'image',thumbnail_url:'/assets/101/thumbnail?library=library-1',taken_at:'2025-06-01T09:00:00Z'};
const other={id:'102',kind:'image',thumbnail_url:'/assets/102/thumbnail?library=library-1',taken_at:'2025-06-01T09:05:00Z'};
const story={id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',asset_id:'101',title:'海边的一天',text:'只属于家人的原话',byline:'妈妈',author_id:'member-2'};
let generated=0;
const context={window:{confirm:()=>true,crypto:{randomUUID:()=>`bbbbbbbb-bbbb-4bbb-8bbb-${String(++generated).padStart(12,'0')}`}},document,URL,crypto:{randomUUID:()=>`bbbbbbbb-bbbb-4bbb-8bbb-${String(++generated).padStart(12,'0')}`},console};
vm.runInNewContext(fs.readFileSync(require('node:path').resolve(__dirname,'../../backend/app/ui/access/memory-groups.js'),'utf8'),context,{filename:'memory-groups.js'});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const byClass=(root,name)=>root.querySelector(`.${name}`);
const click=async(root,name)=>{const control=byClass(root,name);assert.ok(control,`missing .${name}`);await control.dispatch('click');return control;};
async function main(){
  // A response arriving after its containing view is disconnected cannot repopulate it.
  let finishCapabilities;const staleCalls=[];
  const staleApi=(path)=>{staleCalls.push(path);return new Promise(resolve=>finishCapabilities=resolve);};
  const staleHost=new Node('main');document.append(staleHost);const stale= context.window.PhotoHouseMemoryGroups.create({scope,api:staleApi});
  stale.mount(staleHost,asset,[],[]);const staleDetails=staleHost.querySelector('.memory-group-root');staleDetails.open=true;await staleDetails.dispatch('toggle');staleHost.remove();finishCapabilities({enabled:true,manual:true,suggestions:true});await flush();
  assert.deepEqual(staleCalls,['/memory-groups/capabilities']);assert.equal(staleDetails.querySelector('.memory-group-create'),null);

  const host=new Node('main');document.append(host);const calls=[];let failSave=true,savedGroup=null;
  const api=async(path,options={})=>{
    calls.push({path,options});
    if(path==='/memory-groups/capabilities')return {version:1,enabled:true,manual:true,suggestions:true};
    if(path.startsWith('/assets/101/memory-groups'))return {version:1,library_id:'library-1',asset_id:'101',items:savedGroup?[savedGroup]:[]};
    if(path==='/memory-groups/proposals')return {version:1,library_id:'library-1',status:'ready',needs_review:true,seed_asset_ids:['101'],items:options.body.excluded_asset_ids?[]:[{...other,matched_seed_asset_id:'101',time_reason:'same_recorded_day'}]};
    if(path==='/memory-groups'&&options.method==='POST'){
      if(failSave){failSave=false;throw new Error('synthetic uncertain save');}
      savedGroup={version:1,id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',library_id:'library-1',revision:'1',theme:'everyday',asset_ids:['101'],excluded_asset_ids:['102'],source_story_ids:[story.id],items:[asset],sources:[story],can_edit:true};return savedGroup;
    }
    throw new Error(`Unexpected API call: ${path}`);
  };
  const ui=context.window.PhotoHouseMemoryGroups.create({scope,api});const handle=ui.mount(host,asset,[story],[other]);
  const details=host.querySelector('.memory-group-root');details.open=true;await details.dispatch('toggle');await flush();
  assert.equal(calls.filter(call=>call.path==='/memory-groups/capabilities').length,1);
  await click(host,'memory-group-create');
  const suggest=byClass(host,'memory-group-suggest');await suggest.dispatch('click');await flush();
  const candidate=byClass(host,'memory-group-suggestion')?.querySelector('input');assert.ok(candidate?.checked,'suggestions are visible but remain an explicit editable checkbox');
  candidate.checked=false;await candidate.dispatch('change');assert.equal(byClass(host,'memory-group-member').querySelectorAll('.memory-group-remove').length,0,'unchecked recommendation is removed from selected membership');
  candidate.checked=true;await candidate.dispatch('change');await click(host,'memory-group-remove');
  await suggest.dispatch('click');await flush();
  const proposalCalls=calls.filter(call=>call.path==='/memory-groups/proposals');
  assert.equal(proposalCalls.at(-1).options.body.excluded_asset_ids,'102','removed suggestions stay excluded on refresh');
  assert.equal(proposalCalls.at(-1).options.body.asset_ids,'101','refresh stays anchored to the original seed instead of expanding transitively');
  // Select the matching source and save. The body contains a source ID, never its prose.
  const source=byClass(host,'memory-group-story-choice')?.querySelector('input');assert.ok(source);source.checked=true;await source.dispatch('change');
  await byClass(host,'memory-group-editor').dispatch('submit');await flush();
  const firstSave=calls.find(call=>call.path==='/memory-groups'&&call.options.method==='POST');assert.ok(firstSave);
  assert.deepEqual(JSON.parse(JSON.stringify(firstSave.options.body)),{
    asset_ids:'101',excluded_asset_ids:'102',source_story_ids:story.id,theme:'everyday',revision:'0',mutation_id:'bbbbbbbb-bbbb-4bbb-8bbb-000000000001'
  });
  assert.equal(JSON.stringify(firstSave.options.body).includes(story.text),false,'saved group references source IDs without copying shared prose');
  const retry=byClass(host,'memory-group-save-retry');assert.ok(retry,'uncertain save has an explicit retry');
  const pendingSnapshot=JSON.stringify(firstSave.options.body);await retry.dispatch('click');await flush();
  const saves=calls.filter(call=>call.path==='/memory-groups'&&call.options.method==='POST');
  assert.equal(saves.length,2);assert.equal(JSON.stringify(saves[1].options.body),pendingSnapshot,'retry reuses the exact body and mutation ID');
  assert.ok(host.textContent.includes(story.text)&&host.textContent.includes(story.byline),'the saved group shows original prose with its author attribution');
  assert.ok(host.textContent.includes('2025年6月1日 · 09:00 UTC'),'capture time is concise and keeps its written UTC meaning');
  assert.equal(handle.canLeave(),true);

  // Same target remount merges newly paged notes without dropping an open draft.
  const secondStory={...story,id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd',title:'补充的一页'};
  await click(host,'memory-group-create');
  const editor=byClass(host,'memory-group-editor');ui.mount(host,asset,[story,secondStory],[other]);
  assert.equal(byClass(host,'memory-group-editor'),editor,'same-scope note paging preserves the editor node');
  assert.ok(host.textContent.includes(secondStory.title),'same-scope note paging refreshes available sources');
  assert.equal(ui.canLeave(),true,'a clean editor leaves without prompting');
  await click(host,'memory-group-cancel');
  ui.clear();

  const otherStory={...secondStory,id:'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',asset_id:'102',byline:'爸爸'};
  savedGroup={version:1,id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',library_id:'library-1',revision:'1',theme:'everyday',asset_ids:['101','102'],excluded_asset_ids:[],source_story_ids:[story.id,otherStory.id],items:[asset,other],sources:[story,otherStory],can_edit:true};
  let editedBody=null;const editApi=api; // keep the same route fixture, then inspect and emulate this edit below
  const editUi=context.window.PhotoHouseMemoryGroups.create({scope,api:async(path,options={})=>{
    if(path.startsWith('/assets/101/memory-groups'))return {version:1,library_id:'library-1',asset_id:'101',items:[savedGroup]};
    if(path==='/memory-groups/cccccccc-cccc-4ccc-8ccc-cccccccccccc'&&options.method==='PUT'){
      editedBody=JSON.parse(JSON.stringify(options.body));savedGroup={...savedGroup,version:1,revision:'2',asset_ids:['102'],excluded_asset_ids:['101'],source_story_ids:[otherStory.id],items:[other],sources:[otherStory]};return savedGroup;
    }
    return editApi(path,options);
  }});
  editUi.mount(host,asset,[story],[other]);const editDetails=host.querySelector('.memory-group-root');editDetails.open=true;await editDetails.dispatch('toggle');await flush();
  await click(host,'memory-group-edit');
  const linkedChoices=byClass(host,'memory-group-story-choices').querySelectorAll('input');
  assert.equal(linkedChoices.length,2,'edit choices merge notes from other group members');assert.ok(linkedChoices.find(input=>input.value===otherStory.id).checked,'an existing source from another member remains checked');
  const removeFirst=byClass(host,'memory-group-members').querySelector('.memory-group-remove');await removeFirst.dispatch('click');
  await byClass(host,'memory-group-editor').dispatch('submit');await flush();
  assert.equal(editedBody.asset_ids,'102','editing may remove the current photo when another member remains');
  assert.equal(editedBody.source_story_ids,otherStory.id,'the other member note stays linked after removing the current photo');
  console.log('PASS memory group stale reads, persistent exclusions, original-seed suggestions, source-ID writes, exact retry, and preserving edits');
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
