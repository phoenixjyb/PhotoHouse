'use strict';
/* Private assistant conversation client. No browser storage or implicit network work. */
(function install(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.PhotoHousePrivateAssistant = api;
})(typeof globalThis === 'object' ? globalThis : this, function createPrivateAssistantModule() {
  const BASE = '/assistant/workspace/v1';
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const CANONICAL_MEMORY_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const PREFS = Object.freeze({locale:[null,'zh','en'], reply_length:[null,'brief','standard'], voice_pace:[null,'slow','normal']});
  const CARD_TYPES = new Set(['media','album','story','memoir','timeline','unavailable']);
  const SAFE_CODES = new Set(['unavailable','invalid_response','conflict','request_failed','aborted','scope_changed','closed','invalid_input','search_version_unsupported','scene_query_unsupported']);
  const STORE_ERRORS = new Set(['assistant_unavailable','context_changed','request_cancelled','access_denied','invalid_request','storage_unavailable','turn_interrupted']);
  const MAX_ASSET_ID = 9223372036854775807n;
  const MAX_MEMORY_REVISION = 9223372036854775806n;
  const MAX_MEMORY_CARDS = 12;
  const MAX_MEMORY_RESULTS = 256;

  class PrivateAssistantError extends Error {
    constructor(code,status=null) { super(SAFE_CODES.has(code)||STORE_ERRORS.has(code)?code:'request_failed'); this.name='PrivateAssistantError'; this.code=SAFE_CODES.has(code)||STORE_ERRORS.has(code)?code:'request_failed';this.status=status; }
  }
  const fail = code => { throw new PrivateAssistantError(code); };
  const isObject = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const safeInt = v => Number.isSafeInteger(v) && v >= 0;
  const uuid = v => typeof v === 'string' && UUID.test(v);
  const byteLength = value => new TextEncoder().encode(value).length;
  async function validateSpeechBlob(value) {
    const maxBytes=2*1024*1024;
    if(typeof Blob!=='function'||!(value instanceof Blob)||value.size<44||value.size>maxBytes||value.type.split(';')[0].trim().toLowerCase()!=='audio/wav')fail('invalid_response');
    // The server accepts bounded PCM RIFF/WAVE files rather than one encoder's
    // exact 44-byte header. Parse every chunk against both the RIFF and Blob bounds.
    const bytes=new Uint8Array(await value.arrayBuffer());
    try {
    if(bytes.length!==value.size)fail('invalid_response');
    const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
    const label=(at,want)=>at>=0&&at+want.length<=bytes.length&&Array.from({length:want.length},(_,i)=>String.fromCharCode(bytes[at+i])).join('')===want;
    if(!label(0,'RIFF')||!label(8,'WAVE'))fail('invalid_response');
    const end=8+view.getUint32(4,true);if(end!==bytes.length||end<12)fail('invalid_response');
    let offset=12,format=null,dataBytes=null;
    while(offset<end){
      if(offset+8>end)fail('invalid_response');
      const name=String.fromCharCode(...bytes.subarray(offset,offset+4)),size=view.getUint32(offset+4,true),start=offset+8,chunkEnd=start+size,paddedEnd=chunkEnd+(size&1);
      if(chunkEnd> end||paddedEnd>end)fail('invalid_response');
      if(name==='fmt '){
        if(format||size<16)fail('invalid_response');
        const code=view.getUint16(start,true),channels=view.getUint16(start+2,true),rate=view.getUint32(start+4,true),byteRate=view.getUint32(start+8,true),align=view.getUint16(start+12,true),bits=view.getUint16(start+14,true);
        const expectedAlign=channels*(bits/8);
        if(code!==1||![1,2].includes(channels)||![8,16,24,32].includes(bits)||bits%8!==0||rate<8000||rate>48000||align!==expectedAlign||byteRate!==rate*align)fail('invalid_response');
        format={channels,rate,align};
      }else if(name==='data'){
        if(dataBytes!==null)fail('invalid_response');dataBytes=size;
      }
      offset=paddedEnd;
    }
    if(offset!==end||!format||!dataBytes||dataBytes%format.align!==0||dataBytes/format.align>format.rate*30)fail('invalid_response');
    return value;
    } finally { bytes.fill(0); }
  }
  function exactKeys(value, required, optional=[]) {
    if (!isObject(value)) return false;
    const allowed = new Set([...required,...optional]);
    return required.every(key=>Object.hasOwn(value,key)) && Object.keys(value).every(key=>allowed.has(key));
  }
  function validUtc(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$/.test(value)) return false;
    const n=Date.parse(value); return Number.isFinite(n) && new Date(n).toISOString().startsWith(value.slice(0,19));
  }
  function safeJson(raw,maxBytes=262144) {
    if (typeof raw !== 'string') return raw;
    if (!Number.isSafeInteger(maxBytes)||maxBytes<1||byteLength(raw)>maxBytes) fail('invalid_response');
    // Parse while checking each object's keys; JSON.parse alone silently accepts duplicates.
    let i=0;
    const ws=()=>{while(/[\t\n\r ]/.test(raw[i]||''))i++;};
    const string=()=>{const start=i;if(raw[i++]!=='"')fail('invalid_response');while(i<raw.length){const c=raw[i++];if(c==='"'){try{return JSON.parse(raw.slice(start,i));}catch(_){fail('invalid_response');}}if(c==='\\'){i++;}else if(c<' ')fail('invalid_response');}fail('invalid_response');};
    const value=()=>{ws();const c=raw[i];if(c==='{'){i++;ws();const keys=new Set();if(raw[i]==='}'){i++;return;}while(true){ws();const key=string();if(keys.has(key))fail('invalid_response');keys.add(key);ws();if(raw[i++]!==':')fail('invalid_response');value();ws();if(raw[i]==='}'){i++;return;}if(raw[i++]!==',')fail('invalid_response');}}
      if(c==='['){i++;ws();if(raw[i]===']'){i++;return;}while(true){value();ws();if(raw[i]===']'){i++;return;}if(raw[i++]!==',')fail('invalid_response');}}
      if(c==='"'){string();return;}const tail=raw.slice(i);const m=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(tail);if(!m)fail('invalid_response');if(/^-?(?:0|[1-9]\d*)$/.test(m[0])&&!Number.isSafeInteger(Number(m[0])))fail('invalid_response');i+=m[0].length;};
    value();ws();if(i!==raw.length)fail('invalid_response');
    try{return JSON.parse(raw);}catch(_){fail('invalid_response');}
  }
  function validateThread(row, library, includeLabel=false) {
    const required=['thread_id','library_id','created_at','updated_at','expires_at','revision'];
    if(includeLabel)required.push('label');
    if(!exactKeys(row,required,['exchange_count']) ||
      !uuid(row.thread_id) || row.library_id!==library || !validUtc(row.created_at) || !validUtc(row.updated_at) ||
      !validUtc(row.expires_at) || !safeInt(row.revision) || (Object.hasOwn(row,'exchange_count')&&!safeInt(row.exchange_count))) fail('invalid_response');
    if(includeLabel&&row.label!==null&&(typeof row.label!=='string'||!row.label.trim()||[...row.label].length>64||/\p{Cc}/u.test(row.label)))fail('invalid_response');
    return Object.freeze({...row});
  }
  function validateExchange(row) {
    if(!exactKeys(row,['exchange_id','revision','created_at','expires_at','input_text','reply','cards','receipt_count'],['request_id']) ||
      !uuid(row.exchange_id) || !safeInt(row.revision) || !validUtc(row.created_at) || !validUtc(row.expires_at) ||
      typeof row.input_text!=='string'||byteLength(row.input_text)>1024 || typeof row.reply!=='string'||byteLength(row.reply)>262144 ||
      !Array.isArray(row.cards)||row.cards.length>6||!safeInt(row.receipt_count)||row.receipt_count>20||(Object.hasOwn(row,'request_id')&&!uuid(row.request_id))) fail('invalid_response');
    const cards=row.cards.map(card=>{if(!exactKeys(card,['type','count','actionable'])||!CARD_TYPES.has(card.type)||!safeInt(card.count)||card.count<1||card.count>40||card.actionable!==false)fail('invalid_response');return Object.freeze({type:card.type,count:card.count,actionable:false});});
    return Object.freeze({exchange_id:row.exchange_id,revision:row.revision,created_at:row.created_at,expires_at:row.expires_at,input_text:row.input_text,reply:row.reply,cards:Object.freeze(cards),receipt_count:row.receipt_count,...(row.request_id?{request_id:row.request_id}:{})});
  }
  function validateCapabilities(v) {
    if(!exactKeys(v,['version','available','threads','preferences','preferences_applied','server_owned_turns'],['applied_preferences','thread_labels','history_paging','reply_speech','search'])||v.version!==1||
      ['available','threads','preferences','preferences_applied','server_owned_turns'].some(k=>typeof v[k]!=='boolean')||
      ['thread_labels','history_paging','reply_speech'].some(k=>Object.hasOwn(v,k)&&typeof v[k]!=='boolean')||
      (Object.hasOwn(v,'applied_preferences')&&(!Array.isArray(v.applied_preferences)||v.applied_preferences.some(x=>x!=='locale')||new Set(v.applied_preferences).size!==v.applied_preferences.length)))fail('invalid_response');
    let search=null;
    if(Object.hasOwn(v,'search')){
      const raw=v.search;
      if(!exactKeys(raw,['version','date_basis','perspective'])||![2,3].includes(raw.version)||raw.date_basis!=='capture'||
        !(raw.perspective===null||(isObject(raw.perspective)&&exactKeys(raw.perspective,['label'])&&validInterpretationLabel(raw.perspective.label))))fail('invalid_response');
      search=Object.freeze({version:raw.version,date_basis:'capture',perspective:raw.perspective===null?null:Object.freeze({label:raw.perspective.label})});
    }
    return Object.freeze({...v,thread_labels:v.thread_labels===true,history_paging:v.history_paging===true,reply_speech:v.reply_speech===true,search,
      ...(v.applied_preferences?{applied_preferences:Object.freeze([...v.applied_preferences])}:{})});
  }
  function validateSavedMemoryFollowupCapabilities(v) {
    if(!exactKeys(v,['version','available'])||v.version!==1||typeof v.available!=='boolean')fail('invalid_response');
    return Object.freeze({version:1,available:v.available});
  }
  function validateSavedMemoryActionCapabilities(v) { return validateSavedMemoryFollowupCapabilities(v); }
  function validatePrefs(v) {
    if(!exactKeys(v,['version','locale','reply_length','voice_pace','revision'])||v.version!==1||!safeInt(v.revision)||
      Object.keys(PREFS).some(k=>!PREFS[k].includes(v[k])))fail('invalid_response');
    return Object.freeze({locale:v.locale,reply_length:v.reply_length,voice_pace:v.voice_pace,revision:v.revision});
  }
  function assetId(value) { return typeof value==='string'&&/^[1-9][0-9]{0,18}$/.test(value)&&BigInt(value)<=MAX_ASSET_ID; }
  function safeDisplayText(value,maxBytes) { return typeof value==='string'&&!!value.trim()&&byteLength(value)<=maxBytes&&!/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value); }
  function validInterpretationLabel(value) { return safeDisplayText(value,512); }
  function descriptiveText(value) { return typeof value==='string'&&!!value.trim()&&value===value.trim()&&byteLength(value)<=128&&!/\p{Cc}/u.test(value); }
  function descriptiveKey(value) { return value.normalize('NFKC').toLowerCase(); }
  function validateDescriptive(value) {
    if(!exactKeys(value,['version','concepts'])||value.version!==1||!Array.isArray(value.concepts)||value.concepts.length<1||value.concepts.length>6)fail('invalid_response');
    const surfaces=new Set();for(const concept of value.concepts){
      if(!isObject(concept)||typeof concept.surface!=='string'||!descriptiveText(concept.surface))fail('invalid_response');
      const key=descriptiveKey(concept.surface);if(surfaces.has(key))fail('invalid_response');surfaces.add(key);
    }
    const concepts=value.concepts.map(concept=>{
      if(!exactKeys(concept,['surface','alternatives'])||!descriptiveText(concept.surface)||!Array.isArray(concept.alternatives)||concept.alternatives.length<1||concept.alternatives.length>4)fail('invalid_response');
      const alternatives=new Set();
      for(const alternative of concept.alternatives){
        if(!descriptiveText(alternative))fail('invalid_response');
        const key=descriptiveKey(alternative);if(alternatives.has(key))fail('invalid_response');alternatives.add(key);
      }
      return Object.freeze({surface:concept.surface,alternatives:Object.freeze([...concept.alternatives])});
    });
    let bytes;try{bytes=byteLength(JSON.stringify(value));}catch(_){fail('invalid_response');}
    if(bytes>4096)fail('invalid_response');
    return Object.freeze({version:1,concepts:Object.freeze(concepts)});
  }
  function validateFilters(value,searchVersion=1) {
    if(!isObject(value)||Object.keys(value).some(k=>!['people','date','caption','tags','locations','media',...(searchVersion>=2?['text']:[]),...(searchVersion===3?['descriptive']:[])].includes(k)))fail('invalid_response');
    const idsOk=ids=>Array.isArray(ids)&&ids.length>0&&ids.length<=20&&new Set(ids).size===ids.length&&ids.every(assetId);
    if(Object.hasOwn(value,'people')||Object.hasOwn(value,'tags'))for(const key of ['people','tags'])if(Object.hasOwn(value,key)){
      const item=value[key];if(!exactKeys(item,['ids','match'])||!idsOk(item.ids)||!['any','all'].includes(item.match))fail('invalid_response');
    }
    if(Object.hasOwn(value,'locations')&&(!idsOk(value.locations)))fail('invalid_response');
    if(Object.hasOwn(value,'media')){const vals=value.media;if(!Array.isArray(vals)||vals.length<1||vals.length>3||new Set(vals).size!==vals.length||vals.some(x=>!['image','video','other'].includes(x)))fail('invalid_response');}
    if(Object.hasOwn(value,'date')){const d=value.date;if(!exactKeys(d,['from','to'])||!(d.from===null||validDay(d.from))||!(d.to===null||validDay(d.to))||(d.from===null&&d.to===null)||(d.from&&d.to&&d.from>d.to))fail('invalid_response');}
    if(Object.hasOwn(value,'caption')&&(typeof value.caption!=='string'||!value.caption.trim()||byteLength(value.caption)>512||/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value.caption)))fail('invalid_response');
    if(Object.hasOwn(value,'text')&&!safeDisplayText(value.text,512))fail('invalid_response');
    return Object.freeze({...value,...(Object.hasOwn(value,'descriptive')?{descriptive:validateDescriptive(value.descriptive)}:{})});
  }
  function validDay(value) { if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;const d=new Date(`${value}T00:00:00Z`);return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===value; }
  function canonical(value) { if(Array.isArray(value))return `[${value.map(canonical).join(',')}]`;if(isObject(value))return `{${Object.keys(value).sort().map(k=>`${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;return JSON.stringify(value); }
  function validateContext(value, library, searchVersion=1) {
    if(value===null)return null;
    const version=Object.hasOwn(value,'search_version')?value.search_version:1;
    if(!exactKeys(value,['library_id','binding','fingerprint','filters','visible_ids','total'],['search_version'])||value.library_id!==library||!/^([0-9a-f]{64})$/.test(value.binding)||!/^([0-9a-f]{64})$/.test(value.fingerprint)||!Array.isArray(value.visible_ids)||value.visible_ids.length>20||
      new Set(value.visible_ids).size!==value.visible_ids.length||!value.visible_ids.every(assetId)||!safeInt(value.total)||value.total>100000||value.visible_ids.length!==Math.min(20,value.total)||!isObject(value.filters))fail('invalid_response');
    if(Object.hasOwn(value,'search_version')&&![2,3].includes(version))fail('invalid_response');
    if(Object.hasOwn(value.filters,'text')&&version<2||Object.hasOwn(value.filters,'descriptive')&&version!==3)fail('invalid_response');
    return Object.freeze({library_id:value.library_id,binding:value.binding,fingerprint:value.fingerprint,filters:validateFilters(value.filters,version),visible_ids:Object.freeze([...value.visible_ids]),total:value.total,...(version>=2?{search_version:version}:{})});
  }
  function validateMatchReason(reason) {
    if(!isObject(reason)||typeof reason.source!=='string')fail('invalid_response');
    if(reason.source==='photo_memory'){
      if(!exactKeys(reason,['source','source_id','revision'])||!safeDisplayText(reason.source_id,128)||!Number.isSafeInteger(reason.revision)||reason.revision<1)fail('invalid_response');
    }else if(reason.source==='edited_caption'||reason.source==='generated_caption'){
      if(!exactKeys(reason,['source','source_id','revision'])||!assetId(reason.source_id)||!/^([0-9a-f]{64})$/.test(reason.revision))fail('invalid_response');
    }else if(reason.source==='reviewed_person'){
      if(!exactKeys(reason,['source','source_id'])||!assetId(reason.source_id))fail('invalid_response');
    }else if(reason.source==='capture_date'){
      if(!exactKeys(reason,['source','value'])||!validDay(reason.value))fail('invalid_response');
    }else fail('invalid_response');
    return Object.freeze({...reason});
  }
  function validateItem(item, library, searchVersion=1) {
    if(!exactKeys(item,['id','kind','width','height','duration_sec','taken_at','thumbnail_url'],searchVersion>=2?['match_reasons']:[])||!assetId(item.id)||!['image','video','other'].includes(item.kind)||
      ![item.width,item.height].every(x=>x===null||(Number.isSafeInteger(x)&&x>=1&&x<=1000000))||
      !(item.duration_sec===null||(typeof item.duration_sec==='number'&&Number.isFinite(item.duration_sec)&&item.duration_sec>=0&&item.duration_sec<=1e9))||
      !(item.taken_at===null||(typeof item.taken_at==='string'&&byteLength(item.taken_at)<=64&&!/[\u0000-\u001f\u007f]/.test(item.taken_at)))||typeof item.thumbnail_url!=='string')fail('invalid_response');
    if(!item.thumbnail_url.startsWith('/')||item.thumbnail_url.startsWith('//')||item.thumbnail_url.includes('\\'))fail('invalid_response');
    let parsed;try{parsed=new URL(item.thumbnail_url,'https://photohouse.invalid/');}catch(_){fail('invalid_response');}
    if(parsed.origin!=='https://photohouse.invalid'||parsed.pathname!==`/assets/${item.id}/thumbnail`||parsed.hash||parsed.searchParams.getAll('library').length!==1||parsed.searchParams.get('library')!==library||[...parsed.searchParams.keys()].some(k=>k!=='library'))fail('invalid_response');
    if(Object.hasOwn(item,'match_reasons')&&(!Array.isArray(item.match_reasons)||item.match_reasons.length>64))fail('invalid_response');
    return Object.freeze({...item,...(Object.hasOwn(item,'match_reasons')?{match_reasons:Object.freeze(item.match_reasons.map(validateMatchReason))}:{})});
  }
  function validMemoryText(value,maxPoints,maxBytes,{allowNewlines=false}={}) {
    if(typeof value!=='string'||!value.trim()||[...value].length>maxPoints||byteLength(value)>maxBytes)return false;
    for(const char of value){
      const cp=char.codePointAt(0);
      if(cp>=0xd800&&cp<=0xdfff)return false;
      if(allowNewlines&&(char==='\n'||char==='\t'))continue;
      if(/[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}]/u.test(char)&&char!=='\u200c'&&char!=='\u200d')return false;
    }
    return true;
  }
  function validateMemoryBinding(value) {
    if(!exactKeys(value,['kind','id','revision','source_revision'])||
      !['story','memoir'].includes(value.kind)||typeof value.id!=='string'||!CANONICAL_MEMORY_UUID.test(value.id)||
      typeof value.revision!=='string'||!/^[1-9][0-9]{0,18}$/.test(value.revision)||
      BigInt(value.revision)>MAX_MEMORY_REVISION||typeof value.source_revision!=='string'||
      !/^[0-9a-f]{64}$/.test(value.source_revision))fail('invalid_response');
    return Object.freeze({kind:value.kind,id:value.id,revision:value.revision,source_revision:value.source_revision});
  }
  function validateSavedMemoryResult(v,library,allowActions=false) {
    const keys=['version','kind','reply','context','filters','items','total','has_more','effect','memory_cards'];
    if(Object.hasOwn(v,'memory_action'))keys.push('memory_action');
    if(!exactKeys(v,keys)||v.version!==1||typeof v.reply!=='string'||v.reply.length>4000||byteLength(v.reply)>8192||
      !Array.isArray(v.items)||v.items.length!==0||v.filters!==null||v.effect!==null||
      !Array.isArray(v.memory_cards)||v.memory_cards.length>MAX_MEMORY_CARDS||!safeInt(v.total)||v.total>MAX_MEMORY_RESULTS||
      typeof v.has_more!=='boolean')fail('invalid_response');
    if(v.kind==='clarification'){
      if(v.context!==null||v.total!==0||v.has_more||v.memory_cards.length!==0||Object.hasOwn(v,'memory_action'))fail('invalid_response');
      return Object.freeze({...v,context:null,filters:null,items:Object.freeze([]),effect:null,memory_cards:Object.freeze([])});
    }
    if(v.kind!=='memory_cards'||!isObject(v.context)||
      !exactKeys(v.context,['kind','library_id','source_revision','references'])||
      v.context.kind!=='saved_memory'||v.context.library_id!==library||
      typeof v.context.source_revision!=='string'||!/^[0-9a-f]{64}$/.test(v.context.source_revision)||
      !Array.isArray(v.context.references)||v.context.references.length!==v.memory_cards.length||
      v.memory_cards.length!==Math.min(v.total,MAX_MEMORY_CARDS)||v.has_more!==(v.total>v.memory_cards.length))fail('invalid_response');
    const cards=[],references=[],seen=new Set();
    for(let index=0;index<v.memory_cards.length;index++){
      const card=v.memory_cards[index];
      if(!exactKeys(card,['kind','id','revision','source_revision','title','excerpt'])||
        !validMemoryText(card.title,640,640)||!validMemoryText(card.excerpt,240,960,{allowNewlines:true}))fail('invalid_response');
      const binding=validateMemoryBinding({kind:card.kind,id:card.id,revision:card.revision,source_revision:card.source_revision});
      const identity=`${binding.kind}:${binding.id}`;if(seen.has(identity))fail('invalid_response');seen.add(identity);
      const contextBinding=validateMemoryBinding(v.context.references[index]);
      if(canonical(contextBinding)!==canonical(binding))fail('invalid_response');
      references.push(contextBinding);
      cards.push(Object.freeze({...binding,title:card.title,excerpt:card.excerpt}));
    }
    let memoryAction;
    if(Object.hasOwn(v,'memory_action')){
      const action=v.memory_action;
      if(!allowActions||!exactKeys(action,['type','ordinal'])||!['open','read_opening'].includes(action.type)||
        !Number.isSafeInteger(action.ordinal)||action.ordinal<0||action.ordinal>=cards.length)fail('invalid_response');
      memoryAction=Object.freeze({type:action.type,ordinal:action.ordinal});
    }
    return Object.freeze({...v,context:Object.freeze({kind:'saved_memory',library_id:library,source_revision:v.context.source_revision,references:Object.freeze(references)}),
      filters:null,items:Object.freeze([]),effect:null,memory_cards:Object.freeze(cards),...(memoryAction?{memory_action:memoryAction}:{})});
  }
  function validateInterpretation(value,filters) {
    if(!exactKeys(value,['date_basis','people','tags','locations','perspective'])||value.date_basis!=='capture'||
      !Array.isArray(value.people)||!Array.isArray(value.tags)||!Array.isArray(value.locations)||
      !(value.perspective===null||(isObject(value.perspective)&&exactKeys(value.perspective,['label'])&&validInterpretationLabel(value.perspective.label))))fail('invalid_response');
    const labels=(rows,key)=>{
      if(rows.length>20)fail('invalid_response');
      return Object.freeze(rows.map(row=>{if(!exactKeys(row,['id','label'])||!assetId(row.id)||!validInterpretationLabel(row.label))fail('invalid_response');return Object.freeze({id:row.id,label:row.label});}));
    };
    const people=labels(value.people,'people'),tags=labels(value.tags,'tags'),locations=labels(value.locations,'locations');
    const selectedPeople=filters.people?.ids||[],selectedTags=filters.tags?.ids||[],selectedLocations=filters.locations||[];
    const ids=rows=>rows.map(row=>row.id);
    if(canonical(ids(people))!==canonical(selectedPeople)||canonical(ids(tags))!==canonical(selectedTags)||canonical(ids(locations))!==canonical(selectedLocations))fail('invalid_response');
    return Object.freeze({date_basis:'capture',people,tags,locations,perspective:value.perspective===null?null:Object.freeze({label:value.perspective.label})});
  }
  function validateResult(v, library, recovered=false, allowMemory=false, allowMemoryActions=false, searchVersion=1) {
    if(v?.version===4){if(searchVersion!==4)fail('invalid_response');return validateSceneResult(v,library);}
    if(searchVersion===4&&!recovered)fail('invalid_response');
    if(isObject(v)&&(v.kind==='memory_cards'||Object.hasOwn(v,'memory_cards'))){
      if(!allowMemory||recovered)fail('invalid_response');
      return validateSavedMemoryResult(v,library,allowMemoryActions);
    }
    const v2=v?.version===2,v3=v?.version===3,searchV2Plus=v2||v3;
    if(searchVersion===1&&searchV2Plus||searchVersion===2&&v3||searchVersion===3&&!v3&&!recovered)fail('invalid_response');
    if(searchVersion===2&&!v2&&!recovered)fail('invalid_response');
    if(!exactKeys(v,['version','kind','reply','context','filters','items','total','has_more','effect'],searchV2Plus?['interpretation']:[])||(!searchV2Plus&&v.version!==1)||!['results','open','clarification','unsupported'].includes(v.kind)||typeof v.reply!=='string'||v.reply.length>4000||byteLength(v.reply)>8192||
      !Array.isArray(v.items)||v.items.length>20||!safeInt(v.total)||v.total>100000||typeof v.has_more!=='boolean') fail('invalid_response');
    if(searchV2Plus&&!Object.hasOwn(v,'interpretation'))fail('invalid_response');
    const resultVersion=searchV2Plus?v.version:1;
    const context=validateContext(v.context,library,resultVersion),filters=v.filters===null?null:validateFilters(v.filters,resultVersion),items=v.items.map(item=>validateItem(item,library,resultVersion));
    if(context===null){if(items.length!==0||v.total!==0||filters!==null||v.has_more||v.effect!==null)fail('invalid_response');}
    else if(context.library_id!==library||canonical(filters)!==canonical(context.filters)||v.total!==context.total||items.length!==context.visible_ids.length||items.some((item,i)=>item.id!==context.visible_ids[i])||v.has_more!==(context.total>context.visible_ids.length)||searchV2Plus&&context.search_version!==resultVersion||!searchV2Plus&&context.search_version!==undefined)fail('invalid_response');
    const interpretation=searchV2Plus&&Object.hasOwn(v,'interpretation')?validateInterpretation(v.interpretation,filters||{}):undefined;
    if(v.effect!==null&&(!exactKeys(v.effect,['type','asset_id'])||v.effect.type!=='open_asset'||!assetId(v.effect.asset_id)||!items.some(x=>x.id===v.effect.asset_id)))fail('invalid_response');
    if((v.kind==='open')!==(v.effect!==null))fail('invalid_response');
    if(recovered&&(v.kind==='open'||v.effect!==null))fail('invalid_response');
    return Object.freeze({...v,context,filters,items:Object.freeze(items),...(interpretation?{interpretation}:{}),effect:v.effect===null?null:Object.freeze({...v.effect})});
  }
  function validateSceneCapabilities(v){
    if(!exactKeys(v,['version','available','search_version','media'])||v.version!==1||typeof v.available!=='boolean'||v.search_version!==4||canonical(v.media)!=='["image"]')fail('invalid_response');
    return Object.freeze({...v,media:Object.freeze(['image'])});
  }
  function validateScenePage(v,library,threadId,requestId,revision,page){
    if(!exactKeys(v,['version','thread_id','request_id','revision','page','page_size','total','has_more','binding','fingerprint','ranking_sha256','items','semantic'])||v.version!==1||v.thread_id!==threadId||v.request_id!==requestId||v.revision!==revision||v.page!==page||v.page_size!==20||!safeInt(v.total)||v.total<=20||v.total>100000||typeof v.has_more!=='boolean'||typeof v.binding!=='string'||!/^[0-9a-f]{64}$/.test(v.binding)||typeof v.fingerprint!=='string'||!/^[0-9a-f]{64}$/.test(v.fingerprint)||typeof v.ranking_sha256!=='string'||!/^[0-9a-f]{64}$/.test(v.ranking_sha256)||!Array.isArray(v.items)||v.items.length>20||!exactKeys(v.semantic,['mode','score_kind','candidate_count','coverage','needs_review'],['coverage_details'])||v.semantic.mode!=='text_to_image'||v.semantic.score_kind!=='cosine'||v.semantic.candidate_count!==v.total||!safeInt(v.semantic.candidate_count)||v.semantic.coverage!=='complete_eligible_images'||v.semantic.needs_review!==true)fail('invalid_response');
    const offset=(page-1)*20,expected=Math.min(20,Math.max(0,v.total-offset));
    if(v.items.length!==expected||v.has_more!==(offset+20<v.total))fail('invalid_response');
    const items=v.items.map(item=>{if(!isObject(item)||!Object.hasOwn(item,'semantic_score')||typeof item.semantic_score!=='number'||!Number.isFinite(item.semantic_score)||item.semantic_score < -1||item.semantic_score>1)fail('invalid_response');const {semantic_score,...base}=item;return Object.freeze({...validateItem(base,library,2),semantic_score});});
    if(items.some(item=>item.kind!=='image')||new Set(items.map(item=>item.id)).size!==items.length||items.some((item,i)=>i>0&&item.semantic_score>items[i-1].semantic_score))fail('invalid_response');
    let coverageDetails;
    if(Object.hasOwn(v.semantic,'coverage_details')){const d=v.semantic.coverage_details;if(!exactKeys(d,['version','policy_sha256','state','catalog_images','searchable_images','omitted_images','matched_omitted_images'])||d.version!==1||typeof d.policy_sha256!=='string'||!/^[0-9a-f]{64}$/.test(d.policy_sha256)||!['complete','partial'].includes(d.state)||!safeInt(d.catalog_images)||!safeInt(d.searchable_images)||!safeInt(d.omitted_images)||!safeInt(d.matched_omitted_images)||d.catalog_images<1||d.catalog_images>100000||d.searchable_images<1||d.searchable_images>d.catalog_images||d.omitted_images>d.catalog_images||d.matched_omitted_images>d.omitted_images||d.searchable_images+d.omitted_images!==d.catalog_images||(d.state==='partial')!==(d.omitted_images>0)||v.total>d.searchable_images||v.total+d.matched_omitted_images>d.catalog_images)fail('invalid_response');coverageDetails=Object.freeze({...d});}
    const semantic=Object.freeze({...v.semantic,...(coverageDetails?{coverage_details:coverageDetails}:{})});
    return Object.freeze({...v,items:Object.freeze(items),semantic});
  }
  function validSceneQuery(value){return typeof value==='string'&&!!value.trim()&&byteLength(value)<=512&&!/\p{Cc}/u.test(value);}
  function validateSceneResult(v,library){
    if(!exactKeys(v,['version','kind','reply','context','filters','items','total','has_more','effect','interpretation','semantic'])||v.version!==4||v.kind!=='results'||v.effect!==null||!safeDisplayText(v.reply,8192)||v.reply.length>4000||!Array.isArray(v.items)||v.items.length>20||!safeInt(v.total)||v.total>100000||typeof v.has_more!=='boolean')fail('invalid_response');
    const c=v.context;
    if(!exactKeys(c,['library_id','binding','fingerprint','filters','visible_ids','total','search_version','scene'])||c.search_version!==4||!exactKeys(c.scene,['version','query','scope','scores'])||c.scene.version!==1||!validSceneQuery(c.scene.query)||![2,3].includes(c.scene.scope?.search_version))fail('invalid_response');
    const scope=validateContext(c.scene.scope,library,c.scene.scope.search_version);
    if(!scope||Object.hasOwn(scope.filters,'descriptive')||scope.filters.media&&canonical(scope.filters.media)!=='["image"]')fail('invalid_response');
    const {scene,...base}=c, context=validateContext({...base,search_version:2},library,2),filters=validateFilters(v.filters,2);
    if(canonical(filters)!==canonical(context.filters)||canonical(filters)!==canonical({...scope.filters,media:['image']})||v.total!==context.total||v.total>scope.total||!Array.isArray(scene.scores)||scene.scores.length!==context.visible_ids.length||scene.scores.some((score,i)=>typeof score!=='number'||!Number.isFinite(score)||score < -1||score>1||i>0&&score>scene.scores[i-1]))fail('invalid_response');
    const items=v.items.map((item,i)=>{
      if(!isObject(item)||!Object.hasOwn(item,'semantic_score')||item.semantic_score!==scene.scores[i])fail('invalid_response');
      const {semantic_score,...baseItem}=item,checked=validateItem(baseItem,library,2);
      if(checked.kind!=='image'||checked.id!==context.visible_ids[i])fail('invalid_response');
      return Object.freeze({...checked,semantic_score});
    });
    if(items.length!==context.visible_ids.length||v.has_more!==(v.total>items.length)||!exactKeys(v.semantic,['mode','score_kind','candidate_count','coverage','needs_review'],['coverage_details'])||v.semantic.mode!=='text_to_image'||v.semantic.score_kind!=='cosine'||!safeInt(v.semantic.candidate_count)||v.semantic.candidate_count!==v.total||v.semantic.coverage!=='complete_eligible_images'||v.semantic.needs_review!==true)fail('invalid_response');
    let coverageDetails;
    if(Object.hasOwn(v.semantic,'coverage_details')){
      const details=v.semantic.coverage_details;
      if(!exactKeys(details,['version','policy_sha256','state','catalog_images','searchable_images','omitted_images','matched_omitted_images'])||details.version!==1||typeof details.policy_sha256!=='string'||!/^[0-9a-f]{64}$/.test(details.policy_sha256)||!['complete','partial'].includes(details.state)||!Number.isSafeInteger(details.catalog_images)||details.catalog_images<1||details.catalog_images>100000||!Number.isSafeInteger(details.searchable_images)||details.searchable_images<1||details.searchable_images>details.catalog_images||!Number.isSafeInteger(details.omitted_images)||details.omitted_images<0||details.omitted_images>details.catalog_images||!Number.isSafeInteger(details.matched_omitted_images)||details.matched_omitted_images<0||details.matched_omitted_images>details.omitted_images||details.searchable_images+details.omitted_images!==details.catalog_images||(details.state==='partial')!==(details.omitted_images>0)||v.semantic.candidate_count>details.searchable_images||v.semantic.candidate_count+details.matched_omitted_images>details.catalog_images)fail('invalid_response');
      coverageDetails=Object.freeze({version:1,policy_sha256:details.policy_sha256,state:details.state,catalog_images:details.catalog_images,searchable_images:details.searchable_images,omitted_images:details.omitted_images,matched_omitted_images:details.matched_omitted_images});
    }
    const semantic=Object.freeze({mode:v.semantic.mode,score_kind:v.semantic.score_kind,candidate_count:v.semantic.candidate_count,coverage:v.semantic.coverage,needs_review:true,...(coverageDetails?{coverage_details:coverageDetails}:{})});
    return Object.freeze({...v,context:Object.freeze({...context,search_version:4,scene:Object.freeze({version:1,query:scene.query,scope,scores:Object.freeze([...scene.scores])})}),filters,items:Object.freeze(items),interpretation:validateInterpretation(v.interpretation,filters),semantic});
  }
  function validateEnvelope(v, threadId, requestId, library, mode, allowMemory=false, allowMemoryActions=false, searchVersion=1) {
    if(!exactKeys(v,['version','thread_id','request_id','status','revision','recovered','error','result'])||v.version!==1||v.thread_id!==threadId||v.request_id!==requestId||
      !['pending','completed','failed','interrupted'].includes(v.status)||!safeInt(v.revision)||typeof v.recovered!=='boolean'||(mode==='GET'&&!v.recovered)||
      !(v.error===null||(typeof v.error==='string'&&(STORE_ERRORS.has(v.error)||searchVersion===4&&v.status==='failed'&&v.error==='scene_query_unsupported')))||
      !(v.result===null||(v.status==='completed'&&validateResult(v.result,library,v.recovered,allowMemory&&mode==='POST'&&!v.recovered,allowMemoryActions&&mode==='POST'&&!v.recovered,searchVersion)))) fail('invalid_response');
    if((v.status==='completed')!==!!v.result || (v.status==='failed'||v.status==='interrupted')!==(v.error!==null))fail('invalid_response');
    if((v.status==='pending'||v.status==='completed')&&v.error!==null)fail('invalid_response');
    return Object.freeze({...v,result:v.result?validateResult(v.result,library,v.recovered,allowMemory&&mode==='POST'&&!v.recovered,allowMemoryActions&&mode==='POST'&&!v.recovered,searchVersion):null});
  }
  function validateThreadDetail(v, library, expectedId, sceneRewordOptIn=false) {
    if(typeof sceneRewordOptIn!=='boolean'||!exactKeys(v,['version','thread','exchanges'],['latest_request_id','has_older_exchanges',...(sceneRewordOptIn?['scene_reword']:[])])||v.version!==1||!Array.isArray(v.exchanges)||
      v.exchanges.length>20||
      (Object.hasOwn(v,'latest_request_id')&&v.latest_request_id!==null&&!uuid(v.latest_request_id))||
      (Object.hasOwn(v,'has_older_exchanges')&&typeof v.has_older_exchanges!=='boolean'))fail('invalid_response');
    const thread=validateThread(v.thread,library);if(thread.thread_id!==expectedId)fail('invalid_response');
    let sceneReword;
    if(Object.hasOwn(v,'scene_reword')){
      const cue=v.scene_reword;
      if(cue!==null&&(!exactKeys(cue,['version','request_id','revision','query'])||cue.version!==1||!uuid(cue.request_id)||!safeInt(cue.revision)||cue.revision!==thread.revision||!validSceneQuery(cue.query)))fail('invalid_response');
      sceneReword=cue===null?null:Object.freeze({...cue});
    }
    const exchanges=v.exchanges.map(validateExchange);let previous=0;const ids=new Set();for(const e of exchanges){if(e.revision<=previous||ids.has(e.exchange_id))fail('invalid_response');previous=e.revision;ids.add(e.exchange_id);}
    if(v.has_older_exchanges===true&&exchanges.length===0)fail('invalid_response');
    return Object.freeze({version:1,thread,exchanges:Object.freeze(exchanges),...(Object.hasOwn(v,'latest_request_id')?{latest_request_id:v.latest_request_id}:{}),...(Object.hasOwn(v,'has_older_exchanges')?{has_older_exchanges:v.has_older_exchanges}:{}),...(Object.hasOwn(v,'scene_reword')?{scene_reword:sceneReword}:{})});
  }
  function validateHistoryPage(v, threadId, library, snapshotRevision, beforeRevision) {
    if(!exactKeys(v,['version','thread_id','snapshot_revision','before_revision','exchanges','has_older_exchanges','next_before_revision'])||
      v.version!==1||v.thread_id!==threadId||!safeInt(v.snapshot_revision)||v.snapshot_revision!==snapshotRevision||
      !safeInt(v.before_revision)||v.before_revision<1||v.before_revision!==beforeRevision||snapshotRevision<beforeRevision||
      !Array.isArray(v.exchanges)||v.exchanges.length>20||typeof v.has_older_exchanges!=='boolean'||
      !(v.next_before_revision===null||(safeInt(v.next_before_revision)&&v.next_before_revision>0)))fail('invalid_response');
    const exchanges=v.exchanges.map(validateExchange);let previous=0;const ids=new Set();
    for(const exchange of exchanges){
      if(exchange.revision<=previous||exchange.revision>=beforeRevision||exchange.revision>snapshotRevision||ids.has(exchange.exchange_id))fail('invalid_response');
      previous=exchange.revision;ids.add(exchange.exchange_id);
    }
    if(v.has_older_exchanges){
      if(exchanges.length===0||v.next_before_revision!==exchanges[0].revision||v.next_before_revision>=beforeRevision)fail('invalid_response');
    }else if(v.next_before_revision!==null)fail('invalid_response');
    return Object.freeze({...v,exchanges:Object.freeze(exchanges)});
  }
  function validateCreation(v, library, id) {
    if(!exactKeys(v,['version','thread'])||v.version!==1)fail('invalid_response');const thread=validateThread(v.thread,library);if(thread.thread_id!==id)fail('invalid_response');return Object.freeze({version:1,thread});
  }
  function safeFailure(error) {
    if(error instanceof PrivateAssistantError)return error;
    if(error?.name==='AbortError')return new PrivateAssistantError('aborted');
    const status=Number(error?.status);
    if(error?.code==='search_version_unsupported'&&status===400)return new PrivateAssistantError('search_version_unsupported',400);
    if(status===401||status===403)return new PrivateAssistantError('access_denied',status);
    if(status===404)return new PrivateAssistantError('unavailable',404);
    if(status===409)return new PrivateAssistantError('context_changed',409);
    return new PrivateAssistantError('request_failed',Number.isInteger(status)&&status>=400?status:null);
  }

  function createController({scope,request,newUUID,onChange=()=>{},hydrateResults=async result=>result}={}) {
    if(typeof scope!=='function'||typeof request!=='function')throw new TypeError('scope and request are required');
    let closed=false,instance=1,scopeStamp='',revokedStamp=null,revision=0,activeThread=null,draft='',sceneDraft='',sceneRewordRequired=false,sceneAvailable=false,sceneProbeNonce=0,scenePageProbeNonce=0,scenePageAvailable=false,scenePageActive=false,scenePageResult=null,scenePageLoading=false,sceneRequestId=null,pendingTurn=null,pendingCreation=null,capabilities=null,capabilitiesProbeNonce=0,savedMemoryAvailable=false,savedMemorySpeechAvailable=false,savedMemoryReaderAvailable=false,savedMemoryFollowupAvailable=false,savedMemoryReadingAvailable=false,savedMemorySegmentReadingAvailable=false,savedMemoryActionsAvailable=false,savedMemoryProbeNonce=0,savedMemorySpeechProbeNonce=0,savedMemoryReaderProbeNonce=0,savedMemoryFollowupProbeNonce=0,savedMemoryReadingProbeNonce=0,savedMemorySegmentReadingProbeNonce=0,savedMemoryActionsProbeNonce=0,threads=[],preferences=null,currentResult=null,contextState='unavailable',historyDetail=null,historyLoading=false,historyRefreshRequired=false,historyNonce=0,controllers=new Set(),hydrationControllers=new Set(),speechControllers=new Set(),readGeneration=0,speechSource=null,savedMemoryReaderSource=null,openingMemoryCard=false,openingMemorySpeechOrdinal=null,openingMemorySpeechEntry=null,segmentMemorySpeechOrdinal=null,segmentMemorySpeechIndex=null,segmentMemorySpeechEntry=null;
    const snapshot=()=>{const s=scope()||{};return {account:s.account??null,library:s.library==null?null:String(s.library),generation:s.generation??s.membershipGeneration??s.epoch??null,locked:!!s.locked};};
    const stamp=s=>JSON.stringify([s.account,s.library,s.generation,s.locked]);
    const stateValue=()=>{const s=snapshot(),memorySpeechReady=!speechSource?.savedMemory||(savedMemoryAvailable&&savedMemorySpeechAvailable),readerReady=!!savedMemoryReaderSource&&savedMemoryReaderAvailable&&savedMemoryAvailable&&savedMemoryReaderSource.thread_id===activeThread?.thread_id&&savedMemoryReaderSource.revision===revision&&savedMemoryReaderSource.result===currentResult&&savedMemoryReaderSource.account===s.account&&savedMemoryReaderSource.library===s.library&&savedMemoryReaderSource.generation===s.generation&&!pendingTurn&&!pendingCreation&&!s.locked&&revokedStamp!==stamp(s),freshMemorySource=!!savedMemoryReaderSource&&savedMemoryReaderSource.result===currentResult&&savedMemoryReaderSource.thread_id===activeThread?.thread_id&&savedMemoryReaderSource.revision===revision&&activeThread?.revision===revision&&savedMemoryReaderSource.account===s.account&&savedMemoryReaderSource.library===s.library&&savedMemoryReaderSource.generation===s.generation&&currentResult?.kind==='memory_cards'&&currentResult.memory_cards.length>0&&!pendingTurn&&!pendingCreation&&!s.locked&&revokedStamp!==stamp(s),followupReady=freshMemorySource&&savedMemoryFollowupAvailable&&savedMemoryAvailable,savedMemoryReadingReady=freshMemorySource&&savedMemoryReadingAvailable&&savedMemoryAvailable,savedMemorySegmentReadingReady=freshMemorySource&&savedMemorySegmentReadingAvailable&&savedMemoryAvailable&&savedMemorySpeechAvailable&&capabilities?.available===true&&capabilities?.server_owned_turns===true&&capabilities?.reply_speech===true,savedMemoryActionReady=freshMemorySource&&savedMemoryActionsAvailable&&savedMemoryAvailable,speechReady=!!speechSource&&speechSource.kind!=='open'&&capabilities?.reply_speech===true&&memorySpeechReady&&speechSource.thread_id===activeThread?.thread_id&&speechSource.revision===revision&&speechSource.account===s.account&&speechSource.library===s.library&&speechSource.generation===s.generation&&!pendingTurn&&!pendingCreation&&!scenePageActive&&!scenePageLoading&&!s.locked&&revokedStamp!==stamp(s);return Object.freeze({closed,locked:s.locked||revokedStamp===stamp(s),account:s.account,library:s.library,capabilities,savedMemoryAvailable,savedMemorySpeechAvailable,savedMemoryReaderAvailable,savedMemoryFollowupAvailable,savedMemoryReadingAvailable,savedMemorySegmentReadingAvailable,savedMemorySegmentReadingReady,savedMemoryActionsAvailable,savedMemoryActionReady,savedMemoryFollowupReady:followupReady,savedMemoryReaderReady:readerReady,savedMemoryReadingReady,openingMemoryCard,openingMemorySpeechOrdinal,segmentMemorySpeechOrdinal,segmentMemorySpeechIndex,threads:Object.freeze(threads.slice()),activeThread,draft,sceneDraft,sceneRewordRequired,sceneAvailable,sceneReady:sceneReady(),scenePageAvailable,scenePageActive,scenePageResult,scenePageLoading,sceneRequestId,pendingTurn:pendingTurn&&Object.freeze({...pendingTurn}),pendingCreation:pendingCreation&&Object.freeze({...pendingCreation}),preferences,revision,currentResult,contextState,historyDetail,historyLoading,historyRefreshRequired,speechReady,speechReplyBytes:speechReady?speechSource.replyBytes:null,speechKind:speechReady?speechSource.kind:null});};
    const sceneReady=()=>sceneAvailable&&!scenePageActive&&!sceneRewordRequired&&capabilities?.available===true&&capabilities?.server_owned_turns===true&&activeThread?.revision===revision&&contextState==='ready'&&currentResult?.kind==='results'&&[2,3,4].includes(currentResult.version)&&!!currentResult.context&&!Object.hasOwn(currentResult.filters,'descriptive')&&(!currentResult.filters.media||canonical(currentResult.filters.media)==='["image"]')&&!pendingTurn&&!pendingCreation&&!snapshot().locked&&!closed;
    const resultContextState=value=>value?.context?'ready':'requires_search';
    const negotiatedSearchVersion=()=>capabilities?.search?.version===3?3:capabilities?.search?.version===2?2:1;
    const ownHistory=detail=>Object.freeze({...detail,snapshot_revision:detail.thread.revision,
      before_revision:detail.exchanges[0]?.revision??null,history_stale:false,history_limit_reached:false});
    const staleHistory=detail=>Object.freeze({...detail,before_revision:null,has_older_exchanges:false,history_stale:true,history_limit_reached:false});
    function clearHistory(){historyNonce++;historyLoading=false;historyDetail=null;historyRefreshRequired=false;}
    function abortSpeechCalls(predicate=()=>true){for(const entry of speechControllers)if(predicate(entry.source))entry.controller.abort();}
    function clearSpeechSource(){speechSource=null;abortSpeechCalls();}
    function clearMemorySpeechSource(){if(speechSource?.savedMemory)speechSource=null;abortSpeechCalls(source=>source?.savedMemory===true);}
    function resetMemorySegmentSpeech(){segmentMemorySpeechOrdinal=null;segmentMemorySpeechIndex=null;segmentMemorySpeechEntry=null;abortSpeechCalls(source=>source?.savedMemorySegment===true);}
    function invalidateHistory(){historyNonce++;historyLoading=false;historyRefreshRequired=true;if(historyDetail)historyDetail=staleHistory(historyDetail);}
    const publish=()=>{try{onChange(stateValue());}catch(_){}};
    const state=()=>{sync();return stateValue();};
    const abortHydrations=()=>{for(const c of hydrationControllers)c.abort();hydrationControllers.clear();};
    let sceneRankingDigest=null;
    function clearScenePage(){scenePageActive=false;scenePageResult=null;scenePageLoading=false;}
    function clearScopeData(){sceneProbeNonce++;scenePageProbeNonce++;sceneAvailable=false;scenePageAvailable=false;sceneRequestId=null;sceneRankingDigest=null;clearScenePage();sceneDraft='';sceneRewordRequired=false;instance++;capabilitiesProbeNonce++;for(const c of controllers)c.abort();controllers.clear();abortHydrations();readGeneration++;historyNonce++;savedMemoryProbeNonce++;savedMemorySpeechProbeNonce++;savedMemoryReaderProbeNonce++;savedMemoryFollowupProbeNonce++;savedMemoryReadingProbeNonce++;savedMemorySegmentReadingProbeNonce++;savedMemoryActionsProbeNonce++;savedMemoryAvailable=false;savedMemorySpeechAvailable=false;savedMemoryReaderAvailable=false;savedMemoryFollowupAvailable=false;savedMemoryReadingAvailable=false;savedMemorySegmentReadingAvailable=false;savedMemoryActionsAvailable=false;savedMemoryReaderSource=null;openingMemoryCard=false;openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;resetMemorySegmentSpeech();historyDetail=null;historyLoading=false;historyRefreshRequired=false;capabilities=null;threads=[];activeThread=null;draft='';pendingTurn=null;pendingCreation=null;preferences=null;revision=0;currentResult=null;contextState='unavailable';clearSpeechSource();}
    function sync(){const s=snapshot(),key=stamp(s);if(key!==scopeStamp){scopeStamp=key;revokedStamp=null;clearScopeData();publish();}return s;}
    const assertCurrent=(base,token)=>{if(closed)fail('closed');const now=snapshot();if(stamp(now)!==scopeStamp)sync();if(stamp(now)!==stamp(base)||token!==instance||base.locked||!base.account||!base.library||revokedStamp===stamp(now))fail('scope_changed');};
    function revoke(base){revokedStamp=stamp(base);clearScopeData();publish();}
    async function call(path,method,body,base,token,extra={}) {assertCurrent(base,token);const c=new AbortController(),upstream=extra.signal,abort=()=>c.abort(),{maxJsonBytes,...requestOptions}=extra;if(upstream?.aborted)c.abort();else upstream?.addEventListener('abort',abort,{once:true});controllers.add(c);try{const raw=await request(path,{...requestOptions,method,body,signal:c.signal});assertCurrent(base,token);return safeJson(raw,maxJsonBytes??262144);}catch(e){const safe=safeFailure(e);if(safe.status===401||safe.status===403)revoke(base);throw safe;}finally{upstream?.removeEventListener('abort',abort);controllers.delete(c);}}
    // Optional feature routes on older APIs can return a boundary 403. Keep that
    // denial local until the base workspace capability route is rechecked.
    async function callOptionalCapability(path,base,token){assertCurrent(base,token);const c=new AbortController();controllers.add(c);try{const raw=await request(path,{method:'GET',signal:c.signal});assertCurrent(base,token);return safeJson(raw);}catch(e){const safe=safeFailure(e);if(safe.status===401){assertCurrent(base,token);revoke(base);}throw safe;}finally{controllers.delete(c);}}
    function begin(){if(closed)fail('closed');const s=sync();if(s.locked||!s.account||!s.library||revokedStamp===stamp(s))fail('scope_changed');return {base:s,token:instance};}
    async function hydrateResult(value,t,metadata={}){assertCurrent(t.base,t.token);if(metadata.readTicket!==undefined&&metadata.readTicket!==readGeneration)fail('scope_changed');const c=new AbortController();hydrationControllers.add(c);try{const hydrated=await hydrateResults(value,{...metadata,signal:c.signal});assertCurrent(t.base,t.token);if(metadata.readTicket!==undefined&&metadata.readTicket!==readGeneration)fail('scope_changed');return hydrated;}catch(e){throw safeFailure(e);}finally{hydrationControllers.delete(c);}}
    function setDraft(value){begin();if(typeof value!=='string'||byteLength(value)>1024)fail('invalid_input');draft=value;publish();return draft;}
    async function capabilitiesRead(){
      sceneProbeNonce++;sceneAvailable=false;
      const t=begin(),nonce=++capabilitiesProbeNonce,path=`${BASE}/capabilities?${new URLSearchParams({library_id:t.base.library})}`;
      let raw;
      try{raw=await call(path,'GET',undefined,t.base,t.token,{extraHeaders:{'X-PhotoHouse-Search-Version':'3'}});}
      catch(error){if(error.status!==400||error.code!=='search_version_unsupported')throw error;if(nonce!==capabilitiesProbeNonce){assertCurrent(t.base,t.token);fail('conflict');}
        try{raw=await call(path,'GET',undefined,t.base,t.token,{extraHeaders:{'X-PhotoHouse-Search-Version':'2'}});}
        catch(olderError){if(olderError.status!==400||olderError.code!=='search_version_unsupported')throw olderError;if(nonce!==capabilitiesProbeNonce){assertCurrent(t.base,t.token);fail('conflict');}raw=await call(path,'GET',undefined,t.base,t.token);}}
      assertCurrent(t.base,t.token);if(nonce!==capabilitiesProbeNonce)fail('conflict');
      const v=validateCapabilities(raw);capabilities=v;
      if(!v.available||!v.server_owned_turns){savedMemoryProbeNonce++;savedMemorySpeechProbeNonce++;savedMemoryReaderProbeNonce++;savedMemoryFollowupProbeNonce++;savedMemoryReadingProbeNonce++;savedMemorySegmentReadingProbeNonce++;savedMemoryActionsProbeNonce++;savedMemoryAvailable=false;savedMemorySpeechAvailable=false;savedMemoryReaderAvailable=false;savedMemoryFollowupAvailable=false;savedMemoryReadingAvailable=false;savedMemorySegmentReadingAvailable=false;savedMemoryActionsAvailable=false;savedMemoryReaderSource=null;openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;resetMemorySegmentSpeech();clearMemorySpeechSource();abortSpeechCalls(source=>source?.savedMemoryOpening===true);}else if(v.reply_speech!==true){savedMemorySpeechProbeNonce++;savedMemoryReadingProbeNonce++;savedMemorySegmentReadingProbeNonce++;savedMemorySpeechAvailable=false;savedMemoryReadingAvailable=false;savedMemorySegmentReadingAvailable=false;openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;resetMemorySegmentSpeech();clearMemorySpeechSource();abortSpeechCalls(source=>source?.savedMemoryOpening===true);}publish();return v;
    }
    async function sceneCapabilitiesRead(){
      const t=begin(),nonce=++sceneProbeNonce;sceneAvailable=false;publish();
      if(capabilities?.available!==true||capabilities?.server_owned_turns!==true)return false;
      try{const raw=await callOptionalCapability(`${BASE}/scene-search-capabilities?${new URLSearchParams({library_id:t.base.library})}`,t.base,t.token);
        const value=validateSceneCapabilities(raw);assertCurrent(t.base,t.token);if(nonce!==sceneProbeNonce)return sceneAvailable;sceneAvailable=value.available;publish();return sceneAvailable;
      }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed'||safe.status===401)throw safe;assertCurrent(t.base,t.token);if(nonce!==sceneProbeNonce)return sceneAvailable;if(safe.status===403){await capabilitiesRead();assertCurrent(t.base,t.token);return false;}sceneAvailable=false;publish();return false;}
    }
    async function scenePageCapabilitiesRead(){
      const t=begin(),nonce=++scenePageProbeNonce;scenePageAvailable=false;scenePageResult=null;publish();
      if(capabilities?.available!==true||capabilities?.server_owned_turns!==true)return false;
      try{const value=await callOptionalCapability(`${BASE}/scene-page-capabilities?${new URLSearchParams({library_id:t.base.library})}`,t.base,t.token);
        if(!exactKeys(value,['version','available','page_size'])||value.version!==1||typeof value.available!=='boolean'||value.page_size!==20)fail('invalid_response');
        assertCurrent(t.base,t.token);if(nonce!==scenePageProbeNonce)return scenePageAvailable;scenePageAvailable=value.available;if(!value.available){scenePageResult=null;scenePageLoading=false;}publish();return scenePageAvailable;
      }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed'||safe.status===401)throw safe;assertCurrent(t.base,t.token);if(nonce!==scenePageProbeNonce)return scenePageAvailable;scenePageAvailable=false;scenePageResult=null;scenePageLoading=false;publish();return false;}
    }
    async function scenePageRead(page){
      const t=begin();
      if(!scenePageAvailable||!sceneAvailable||capabilities?.available!==true||capabilities?.server_owned_turns!==true||!activeThread||!sceneRequestId||currentResult?.version!==4||
          currentResult.context?.scene?.scope?.library_id!==t.base.library||!safeInt(currentResult.total)||currentResult.total<=20||currentResult.total>100000||
          !Number.isSafeInteger(page)||page<1||page>Math.ceil(currentResult.total/20)||
          pendingTurn||pendingCreation||scenePageLoading||speechControllers.size||openingMemoryCard||openingMemorySpeechOrdinal!==null)fail('conflict');
      const threadId=activeThread.thread_id,requestId=sceneRequestId,expectedRevision=revision,savedResult=currentResult,capabilityNonce=scenePageProbeNonce,ticket=++readGeneration;
      if(typeof savedResult.context?.binding!=='string'||typeof savedResult.context?.fingerprint!=='string'||!Array.isArray(savedResult.context?.visible_ids)||savedResult.context.visible_ids.length!==savedResult.items.length||savedResult.items.length<1||savedResult.items.length>20)fail('conflict');
      const digest=sceneRankingDigest;
      scenePageActive=true;scenePageLoading=true;scenePageResult=null;publish();
      const controller=new AbortController();controllers.add(controller);
      try{
        const body={version:1,library_id:t.base.library,expected_revision:expectedRevision,page};
        if(digest)body.ranking_sha256=digest;
        const raw=await call(`${threadPath(threadId)}/requests/${encodeURIComponent(requestId)}/scene-pages`,'POST',body,t.base,t.token,
          {signal:controller.signal,extraHeaders:{'X-PhotoHouse-Search-Version':'4'}});
        assertCurrent(t.base,t.token);if(ticket!==readGeneration||sceneRequestId!==requestId||activeThread?.thread_id!==threadId||revision!==expectedRevision||currentResult!==savedResult||scenePageProbeNonce!==capabilityNonce||!scenePageAvailable||!sceneAvailable||capabilities?.available!==true||capabilities?.server_owned_turns!==true)fail('scope_changed');
        const checked=validateScenePage(raw,t.base.library,threadId,requestId,expectedRevision,page);
        if(checked.binding!==savedResult.context.binding||checked.fingerprint!==savedResult.context.fingerprint||checked.total!==savedResult.total||digest&&checked.ranking_sha256!==digest)fail('invalid_response');
        sceneRankingDigest=checked.ranking_sha256;scenePageResult=checked;scenePageLoading=false;publish();return checked;
      }catch(error){if(ticket===readGeneration&&sceneRequestId===requestId&&activeThread?.thread_id===threadId&&revision===expectedRevision){scenePageLoading=false;scenePageResult=null;publish();}throw safeFailure(error);}
      finally{controllers.delete(controller);}
    }
    async function returnSceneResults(){
      if(!scenePageActive||!activeThread||!sceneRequestId)fail('conflict');
      if(scenePageLoading||speechControllers.size||openingMemoryCard||openingMemorySpeechOrdinal!==null)fail('conflict');
      const t=begin(),scopeInstance=t.token,threadId=activeThread.thread_id,requestId=sceneRequestId,expectedRevision=revision,savedResult=currentResult;
      scenePageLoading=true;scenePageResult=null;sceneRankingDigest=null;publish();
      try{
        const pending=read(threadId,{sceneReturn:true}),ticket=readGeneration;
        const detail=await pending;
        if(instance!==scopeInstance||readGeneration!==ticket||activeThread?.thread_id!==threadId||sceneRequestId!==requestId||revision!==expectedRevision)fail('scope_changed');
        if(detail.latest_request_id!==requestId||detail.thread.revision!==expectedRevision||currentResult?.version!==4||currentResult.total!==savedResult?.total||currentResult.context?.binding!==savedResult?.context?.binding||currentResult.context?.fingerprint!==savedResult?.context?.fingerprint){
          currentResult=null;contextState='requires_search';scenePageLoading=false;scenePageResult=null;publish();fail('conflict');
        }
        clearScenePage();sceneRankingDigest=null;publish();return detail;
      }catch(error){
        if(instance===scopeInstance&&activeThread?.thread_id===threadId&&sceneRequestId===requestId&&revision===expectedRevision){scenePageLoading=false;scenePageActive=true;scenePageResult=null;publish();}
        throw safeFailure(error);
      }
    }
    function setSceneDraft(value){begin();if(typeof value!=='string'||byteLength(value)>4096)fail('invalid_input');sceneDraft=value;publish();}
    async function savedMemoryCapabilitiesRead(){const t=begin(),nonce=++savedMemoryProbeNonce;savedMemoryAvailable=false;savedMemorySpeechProbeNonce++;savedMemoryReaderProbeNonce++;savedMemoryFollowupProbeNonce++;savedMemoryReadingProbeNonce++;savedMemorySegmentReadingProbeNonce++;savedMemoryActionsProbeNonce++;savedMemorySpeechAvailable=false;savedMemoryReaderAvailable=false;savedMemoryFollowupAvailable=false;savedMemoryReadingAvailable=false;savedMemorySegmentReadingAvailable=false;savedMemoryActionsAvailable=false;openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;resetMemorySegmentSpeech();abortSpeechCalls(source=>source?.savedMemoryOpening===true);clearMemorySpeechSource();publish();if(capabilities?.available!==true||capabilities?.server_owned_turns!==true)return false;try{
      const raw=await call(`${BASE}/saved-memory-capabilities?${new URLSearchParams({library_id:t.base.library})}`,'GET',undefined,t.base,t.token);
      assertCurrent(t.base,t.token);if(nonce!==savedMemoryProbeNonce)return savedMemoryAvailable;
      savedMemoryAvailable=exactKeys(raw,['version','available'])&&raw.version===1&&typeof raw.available==='boolean'&&raw.available&&capabilities?.available===true&&capabilities?.server_owned_turns===true;
      if(!savedMemoryAvailable){savedMemoryReadingProbeNonce++;savedMemoryReadingAvailable=false;savedMemorySegmentReadingProbeNonce++;savedMemorySegmentReadingAvailable=false;resetMemorySegmentSpeech();openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;abortSpeechCalls(source=>source?.savedMemoryOpening===true);}
      publish();if(savedMemoryAvailable&&nonce===savedMemoryProbeNonce&&capabilities?.reply_speech===true)await savedMemorySpeechCapabilitiesRead();return savedMemoryAvailable;
    }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed'||safe.code==='access_denied')throw safe;
      assertCurrent(t.base,t.token);if(nonce===savedMemoryProbeNonce){savedMemoryAvailable=false;savedMemoryReadingAvailable=false;savedMemorySegmentReadingProbeNonce++;savedMemorySegmentReadingAvailable=false;resetMemorySegmentSpeech();openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;publish();}return false;}}
    async function savedMemoryActionsCapabilitiesRead(){const t=begin(),nonce=++savedMemoryActionsProbeNonce;savedMemoryActionsAvailable=false;publish();if(!savedMemoryAvailable||capabilities?.available!==true||capabilities?.server_owned_turns!==true)return false;try{
      const raw=await callOptionalCapability(`${BASE}/saved-memory-action-capabilities?${new URLSearchParams({library_id:t.base.library})}`,t.base,t.token);
      assertCurrent(t.base,t.token);if(nonce!==savedMemoryActionsProbeNonce)return savedMemoryActionsAvailable;
      savedMemoryActionsAvailable=validateSavedMemoryActionCapabilities(raw).available&&savedMemoryAvailable&&capabilities?.available===true&&capabilities?.server_owned_turns===true;
      publish();return savedMemoryActionsAvailable;
    }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed')throw safe;assertCurrent(t.base,t.token);
      if(safe.status===403){
        const base=await capabilitiesRead();
        assertCurrent(t.base,t.token);if(nonce!==savedMemoryActionsProbeNonce)return savedMemoryActionsAvailable;
        capabilities=base;
        if(!base.available||!base.server_owned_turns){savedMemoryProbeNonce++;savedMemorySpeechProbeNonce++;savedMemoryReaderProbeNonce++;savedMemoryFollowupProbeNonce++;savedMemoryReadingProbeNonce++;savedMemoryAvailable=false;savedMemorySpeechAvailable=false;savedMemoryReaderAvailable=false;savedMemoryFollowupAvailable=false;savedMemoryReadingAvailable=false;savedMemoryReaderSource=null;clearMemorySpeechSource();}
        savedMemoryActionsAvailable=false;publish();return false;
      }
      if(safe.status===401)throw safe;
      if(nonce===savedMemoryActionsProbeNonce){savedMemoryActionsAvailable=false;publish();}return false;}}
    async function savedMemorySpeechCapabilitiesRead(){const t=begin(),nonce=++savedMemorySpeechProbeNonce;savedMemorySpeechAvailable=false;savedMemoryReadingProbeNonce++;savedMemoryReadingAvailable=false;savedMemorySegmentReadingProbeNonce++;savedMemorySegmentReadingAvailable=false;resetMemorySegmentSpeech();openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;abortSpeechCalls(source=>source?.savedMemoryOpening===true);clearMemorySpeechSource();publish();if(!savedMemoryAvailable||capabilities?.available!==true||capabilities?.server_owned_turns!==true||capabilities?.reply_speech!==true)return false;try{
      const raw=await call(`${BASE}/saved-memory-speech-capabilities?${new URLSearchParams({library_id:t.base.library})}`,'GET',undefined,t.base,t.token);
      assertCurrent(t.base,t.token);if(nonce!==savedMemorySpeechProbeNonce)return savedMemorySpeechAvailable;
      savedMemorySpeechAvailable=exactKeys(raw,['version','available'])&&raw.version===1&&typeof raw.available==='boolean'&&raw.available&&savedMemoryAvailable&&capabilities?.available===true&&capabilities?.server_owned_turns===true&&capabilities?.reply_speech===true;
      publish();return savedMemorySpeechAvailable;
    }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed'||safe.code==='access_denied')throw safe;
      assertCurrent(t.base,t.token);if(nonce===savedMemorySpeechProbeNonce){savedMemorySpeechAvailable=false;savedMemoryReadingProbeNonce++;savedMemoryReadingAvailable=false;savedMemorySegmentReadingProbeNonce++;savedMemorySegmentReadingAvailable=false;resetMemorySegmentSpeech();openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;abortSpeechCalls(source=>source?.savedMemoryOpening===true);clearMemorySpeechSource();publish();}return false;}}
    async function savedMemoryReadingCapabilitiesRead(){const t=begin(),nonce=++savedMemoryReadingProbeNonce;savedMemoryReadingAvailable=false;openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;abortSpeechCalls(source=>source?.savedMemoryOpening===true);publish();if(!savedMemoryAvailable||capabilities?.available!==true||capabilities?.server_owned_turns!==true||capabilities?.reply_speech!==true||!savedMemorySpeechAvailable)return false;try{
      const raw=await callOptionalCapability(`${BASE}/saved-memory-reading-capabilities?${new URLSearchParams({library_id:t.base.library})}`,t.base,t.token);
      assertCurrent(t.base,t.token);if(nonce!==savedMemoryReadingProbeNonce)return savedMemoryReadingAvailable;
      savedMemoryReadingAvailable=validateSavedMemoryFollowupCapabilities(raw).available&&savedMemoryAvailable&&savedMemorySpeechAvailable&&capabilities?.available===true&&capabilities?.server_owned_turns===true&&capabilities?.reply_speech===true;
      publish();return savedMemoryReadingAvailable;
    }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed')throw safe;assertCurrent(t.base,t.token);
      if(safe.status===403){
        try{
          const base=await capabilitiesRead();
          assertCurrent(t.base,t.token);if(nonce!==savedMemoryReadingProbeNonce)return savedMemoryReadingAvailable;
          capabilities=base;
          if(!base.available||!base.server_owned_turns){savedMemoryProbeNonce++;savedMemorySpeechProbeNonce++;savedMemoryReaderProbeNonce++;savedMemoryFollowupProbeNonce++;savedMemoryAvailable=false;savedMemorySpeechAvailable=false;savedMemoryReaderAvailable=false;savedMemoryFollowupAvailable=false;savedMemoryReaderSource=null;clearMemorySpeechSource();}
          else if(base.reply_speech!==true){savedMemorySpeechProbeNonce++;savedMemorySpeechAvailable=false;clearMemorySpeechSource();}
          savedMemoryReadingAvailable=false;openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;abortSpeechCalls(source=>source?.savedMemoryOpening===true);publish();return false;
        }catch(recheckError){throw safeFailure(recheckError);}
      }
      if(safe.status===401)throw safe;
      if(nonce===savedMemoryReadingProbeNonce){savedMemoryReadingAvailable=false;openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;abortSpeechCalls(source=>source?.savedMemoryOpening===true);publish();}return false;}}
    async function savedMemorySegmentReadingCapabilitiesRead(){const t=begin(),nonce=++savedMemorySegmentReadingProbeNonce;savedMemorySegmentReadingAvailable=false;resetMemorySegmentSpeech();publish();if(!savedMemoryAvailable||!savedMemorySpeechAvailable||capabilities?.available!==true||capabilities?.server_owned_turns!==true||capabilities?.reply_speech!==true)return false;try{
      const raw=await callOptionalCapability(`${BASE}/saved-memory-segment-reading-capabilities?${new URLSearchParams({library_id:t.base.library})}`,t.base,t.token);
      assertCurrent(t.base,t.token);if(nonce!==savedMemorySegmentReadingProbeNonce)return savedMemorySegmentReadingAvailable;
      savedMemorySegmentReadingAvailable=exactKeys(raw,['version','available'])&&raw.version===1&&typeof raw.available==='boolean'&&raw.available&&savedMemoryAvailable&&savedMemorySpeechAvailable&&capabilities?.available===true&&capabilities?.server_owned_turns===true&&capabilities?.reply_speech===true;
      publish();return savedMemorySegmentReadingAvailable;
    }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed')throw safe;assertCurrent(t.base,t.token);
      if(safe.status===403){
        try{
          const base=await capabilitiesRead();
          assertCurrent(t.base,t.token);if(nonce!==savedMemorySegmentReadingProbeNonce)return savedMemorySegmentReadingAvailable;
          capabilities=base;
          if(!base.available||!base.server_owned_turns){savedMemoryProbeNonce++;savedMemorySpeechProbeNonce++;savedMemoryReaderProbeNonce++;savedMemoryFollowupProbeNonce++;savedMemoryReadingProbeNonce++;savedMemoryAvailable=false;savedMemorySpeechAvailable=false;savedMemoryReaderAvailable=false;savedMemoryFollowupAvailable=false;savedMemoryReadingAvailable=false;savedMemoryReaderSource=null;clearMemorySpeechSource();}
          else if(base.reply_speech!==true){savedMemorySpeechProbeNonce++;savedMemorySpeechAvailable=false;clearMemorySpeechSource();}
          savedMemorySegmentReadingProbeNonce++;savedMemorySegmentReadingAvailable=false;resetMemorySegmentSpeech();publish();return false;
        }catch(recheckError){throw safeFailure(recheckError);}
      }
      if(safe.status===401)throw safe;
      if(nonce===savedMemorySegmentReadingProbeNonce){savedMemorySegmentReadingAvailable=false;resetMemorySegmentSpeech();publish();}return false;}}
    async function savedMemoryReaderCapabilitiesRead(){const t=begin(),nonce=++savedMemoryReaderProbeNonce;savedMemoryReaderAvailable=false;publish();if(!savedMemoryAvailable||capabilities?.available!==true||capabilities?.server_owned_turns!==true)return false;try{
      const raw=await call(`${BASE}/saved-memory-reader-capabilities?${new URLSearchParams({library_id:t.base.library})}`,'GET',undefined,t.base,t.token);
      assertCurrent(t.base,t.token);if(nonce!==savedMemoryReaderProbeNonce)return savedMemoryReaderAvailable;
      savedMemoryReaderAvailable=exactKeys(raw,['version','available'])&&raw.version===1&&typeof raw.available==='boolean'&&raw.available&&savedMemoryAvailable&&capabilities?.available===true&&capabilities?.server_owned_turns===true;
      publish();return savedMemoryReaderAvailable;
    }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed'||safe.code==='access_denied')throw safe;
      assertCurrent(t.base,t.token);if(nonce===savedMemoryReaderProbeNonce){savedMemoryReaderAvailable=false;publish();}return false;}}
    async function savedMemoryFollowupCapabilitiesRead(){const t=begin(),nonce=++savedMemoryFollowupProbeNonce;savedMemoryFollowupAvailable=false;publish();if(!savedMemoryAvailable||capabilities?.available!==true||capabilities?.server_owned_turns!==true)return false;try{
      const raw=await callOptionalCapability(`${BASE}/saved-memory-followup-capabilities?${new URLSearchParams({library_id:t.base.library})}`,t.base,t.token);
      assertCurrent(t.base,t.token);if(nonce!==savedMemoryFollowupProbeNonce)return savedMemoryFollowupAvailable;
      savedMemoryFollowupAvailable=validateSavedMemoryFollowupCapabilities(raw).available&&savedMemoryAvailable&&capabilities?.available===true&&capabilities?.server_owned_turns===true;
      publish();return savedMemoryFollowupAvailable;
    }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed')throw safe;
      assertCurrent(t.base,t.token);
      if(safe.status===403){
        try{
          const base=await capabilitiesRead();
          assertCurrent(t.base,t.token);if(nonce!==savedMemoryFollowupProbeNonce)return savedMemoryFollowupAvailable;
          capabilities=base;
          if(!base.available||!base.server_owned_turns){savedMemoryProbeNonce++;savedMemorySpeechProbeNonce++;savedMemoryReaderProbeNonce++;savedMemoryAvailable=false;savedMemorySpeechAvailable=false;savedMemoryReaderAvailable=false;savedMemoryReaderSource=null;clearMemorySpeechSource();}
          else if(base.reply_speech!==true){savedMemorySpeechProbeNonce++;savedMemorySpeechAvailable=false;clearMemorySpeechSource();}
          savedMemoryFollowupAvailable=false;publish();return false;
        }catch(recheckError){const rechecked=safeFailure(recheckError);if(rechecked.code==='scope_changed'||rechecked.code==='closed'||rechecked.status===401||rechecked.status===403)throw rechecked;throw rechecked;}
      }
      if(safe.status===401)throw safe;
      if(nonce===savedMemoryFollowupProbeNonce){savedMemoryFollowupAvailable=false;publish();}return false;}}
    async function list(){const t=begin();const query=new URLSearchParams({library_id:t.base.library});const includeLabels=capabilities?.thread_labels===true;if(includeLabels)query.set('include_labels','true');const raw=await call(`${BASE}/threads?${query}`,'GET',undefined,t.base,t.token);if(!exactKeys(raw,['version','threads'])||raw.version!==1||!Array.isArray(raw.threads))fail('invalid_response');const values=raw.threads.map(x=>validateThread(x,t.base.library,includeLabels));threads=values;publish();return values;}
    const threadPath=id=>`${BASE}/threads/${encodeURIComponent(id)}`;
    function beginHistoryRead(id){historyNonce++;historyLoading=false;const sameThread=historyDetail?.thread.thread_id===id;historyDetail=sameThread?staleHistory(historyDetail):null;historyRefreshRequired=!!sameThread;}
    async function read(id,{hydrate=true,sceneReloadGuard=false,sceneReturn=false}={}){
      if(!uuid(id))fail('invalid_input');
      const t=begin();if(pendingTurn)fail('conflict');
      if(sceneReturn){scenePageLoading=true;scenePageResult=null;sceneRankingDigest=null;publish();}
      else{clearScenePage();sceneRankingDigest=null;sceneRequestId=null;}
      const reloadBase=sceneReloadGuard?{threadId:activeThread?.thread_id,revision}:null;
      if(reloadBase&&(!sceneRewordRequired||reloadBase.threadId!==id||!safeInt(reloadBase.revision)))fail('conflict');
      if(activeThread?.thread_id!==id)sceneRewordRequired=false;
      const hadRewordHint=sceneRewordRequired;
      clearSpeechSource();savedMemoryReaderSource=null;openingMemoryCard=false;publish();abortHydrations();
      const ticket=++readGeneration;beginHistoryRead(id);publish();
      const readVersion=sceneAvailable?4:negotiatedSearchVersion();
      // This is private input metadata, independent of whether v4 ranking is
      // currently available. Older servers ignore the unknown header and keep
      // their legacy response shape.
      const sceneProjection=true;
      const detailHeaders={extraHeaders:{'X-PhotoHouse-Scene-Reword-Version':'1'}};
      const raw=await call(`${threadPath(id)}?${new URLSearchParams({library_id:t.base.library})}`,'GET',undefined,t.base,t.token,detailHeaders);
      assertCurrent(t.base,t.token);if(ticket!==readGeneration)fail('scope_changed');
      let detail=validateThreadDetail(raw,t.base.library,id,sceneProjection);
      if(reloadBase&&(detail.thread.revision!==reloadBase.revision||detail.thread.thread_id!==reloadBase.threadId))fail('conflict');
      const rewordCue=Object.hasOwn(detail,'scene_reword')?detail.scene_reword:null;
      if(rewordCue&&!reloadBase){
        const confirm=validateThreadDetail(await call(`${threadPath(id)}?${new URLSearchParams({library_id:t.base.library})}`,'GET',undefined,t.base,t.token,detailHeaders),t.base.library,id,sceneProjection);
        assertCurrent(t.base,t.token);if(ticket!==readGeneration)fail('scope_changed');
        if(confirm.thread.revision!==detail.thread.revision||confirm.latest_request_id!==detail.latest_request_id||canonical(confirm.scene_reword??null)!==canonical(detail.scene_reword??null)){
          currentResult=null;contextState='requires_search';publish();fail('conflict');
        }
      }
      historyDetail=ownHistory(detail);historyRefreshRequired=false;publish();
      let latest=null,guardedResult=null;
      const suppressOldResult=!!(!reloadBase&&(rewordCue||(hadRewordHint&&!Object.hasOwn(detail,'scene_reword'))));
      if(sceneProjection&&!reloadBase&&Object.hasOwn(detail,'scene_reword')){
        sceneRewordRequired=!!rewordCue;
        if(rewordCue&&!sceneDraft)sceneDraft=rewordCue.query;
      }
      currentResult=null;contextState=suppressOldResult?'requires_search':detail.latest_request_id?'unloaded':'requires_search';
      if(!suppressOldResult&&detail.latest_request_id&&hydrate&&capabilities?.server_owned_turns!==false){try{latest=await getRequest(id,detail.latest_request_id,{_ticket:{base:t.base,token:t.token,readTicket:ticket},hydrate:false,searchVersion:readVersion});
          if(latest.status==='completed'&&latest.revision===detail.thread.revision){const hydrated=await hydrateResult(latest.result,t,{readTicket:ticket,threadId:id,revision:latest.revision});if(reloadBase)guardedResult=hydrated;else{currentResult=hydrated;contextState=resultContextState(currentResult);if(hydrated.version===4)sceneRequestId=latest.request_id;}}
          else if(latest.status==='completed')contextState='stale';
          else if(latest.status==='pending')contextState='pending';
          else contextState='requires_search';
          if(latest.status==='pending'){const saved=detail.exchanges.find(x=>x.request_id===latest.request_id);pendingTurn={thread_id:id,request_id:latest.request_id,expected_revision:latest.revision,text:saved?.input_text||'',status:'pending',search_version:readVersion};}
        }catch(e){const safe=safeFailure(e);if(safe.status===409||safe.status===404){latest=null;currentResult=null;contextState='requires_search';}else throw safe;}}
      if(reloadBase){const confirm=validateThreadDetail(await call(`${threadPath(id)}?${new URLSearchParams({library_id:t.base.library})}`,'GET',undefined,t.base,t.token,detailHeaders),t.base.library,id,sceneProjection);assertCurrent(t.base,t.token);if(ticket!==readGeneration)fail('scope_changed');if(confirm.thread.revision!==reloadBase.revision||confirm.latest_request_id!==detail.latest_request_id||canonical(confirm.scene_reword??null)!==canonical(detail.scene_reword??null)||activeThread?.thread_id!==reloadBase.threadId||revision!==reloadBase.revision){currentResult=null;contextState='requires_search';publish();fail('conflict');}}
      assertCurrent(t.base,t.token);if(ticket!==readGeneration)fail('scope_changed');activeThread=latest?.status==='completed'?Object.freeze({...detail.thread,revision:latest.revision}):detail.thread;revision=latest?.status==='completed'?latest.revision:detail.thread.revision;if(reloadBase){currentResult=guardedResult;if(guardedResult)contextState=resultContextState(guardedResult);}if(sceneAvailable&&activeThread.thread_id===id&&activeThread.revision===revision&&contextState==='ready'&&currentResult?.context)sceneRewordRequired=false;publish();
      const latestSummary=latest?Object.freeze({request_id:latest.request_id,status:latest.status,revision:latest.revision,error:latest.error}):null;
      return Object.freeze({...historyDetail,current_result:currentResult,context_state:contextState,...(latestSummary?{latest_request:latestSummary}:{})});}
    async function create({retry=false}={}){const t=begin();if(pendingTurn)fail('conflict');sceneRewordRequired=false;clearSpeechSource();savedMemoryReaderSource=null;openingMemoryCard=false;let id;if(pendingCreation){if(!retry)fail('conflict');id=pendingCreation.thread_id;}else{id=typeof newUUID==='function'?newUUID():null;if(!uuid(id))fail('invalid_input');pendingCreation={thread_id:id,library_id:t.base.library,account:t.base.account};}clearHistory();publish();abortHydrations();const ticket=++readGeneration;
      try{const raw=await call(`${BASE}/threads`,'POST',{library_id:t.base.library,thread_id:id},t.base,t.token);const created=validateCreation(raw,t.base.library,id);assertCurrent(t.base,t.token);pendingCreation=null;if(ticket!==readGeneration){threads=[created.thread,...threads.filter(x=>x.thread_id!==id)];publish();return created;}activeThread=created.thread;revision=created.thread.revision;currentResult=null;contextState='requires_search';publish();return created;}
      catch(e){const safe=safeFailure(e);if(safe.code==='scope_changed'||safe.code==='closed')throw safe; // retain ID and require explicit reconciliation or retry
        throw safe;}}
    async function recover(id,rid){if(!uuid(id)||!uuid(rid))fail('invalid_input');const t=begin();clearSpeechSource();savedMemoryReaderSource=null;openingMemoryCard=false;if(!pendingTurn||pendingTurn.thread_id!==id||pendingTurn.request_id!==rid)fail('conflict');const searchVersion=[2,3,4].includes(pendingTurn.search_version)?pendingTurn.search_version:1;const env=await getRequest(id,rid,{_ticket:t,hydrate:true,searchVersion});assertCurrent(t.base,t.token);if(env.status==='failed'&&env.error==='scene_query_unsupported'&&pendingTurn.mode==='scene'&&searchVersion===4&&env.revision!==pendingTurn.expected_revision)fail('invalid_response');if(pendingTurn?.thread_id===id&&pendingTurn.request_id===rid){if(env.status==='completed'||env.status==='failed'||env.status==='interrupted'){readGeneration++;abortHydrations();invalidateHistory();if(env.status==='completed'){activeThread=Object.freeze({...activeThread,revision:env.revision});revision=env.revision;const sentText=pendingTurn.text,scenePending=pendingTurn.mode==='scene'||env.result.version===4;pendingTurn=null;if(scenePending){if(sceneDraft===sentText)sceneDraft='';}else if(draft===sentText)draft='';currentResult=env.result;contextState=resultContextState(env.result);}else{if(pendingTurn.mode==='scene'){if(!sceneDraft)sceneDraft=pendingTurn.text;sceneRewordRequired=env.status==='failed'&&env.error==='scene_query_unsupported'&&searchVersion===4;}else if(!draft)draft=pendingTurn.text;pendingTurn=null;currentResult=null;contextState='requires_search';}}else pendingTurn={...pendingTurn,status:'pending'};publish();}return env;}
    function abandonPending(){begin();if(!pendingTurn)fail('invalid_input');clearSpeechSource();if(pendingTurn.mode==='scene'){if(!sceneDraft)sceneDraft=pendingTurn.text;}else if(!draft)draft=pendingTurn.text;pendingTurn=null;publish();return draft;}
    function discardSpeechSource(){
      // This is a local revocation path (Pause/End), so it must still wipe the
      // reference after a library lock, account switch, or controller close.
      clearSpeechSource();
      try{sync();}catch(_){}
      try{publish();}catch(_){}
    }
    async function reconcileCreation(){const t=begin();if(!pendingCreation||pendingTurn)fail('invalid_input');clearSpeechSource();const id=pendingCreation.thread_id;clearHistory();abortHydrations();const ticket=++readGeneration;const raw=await call(`${threadPath(id)}?${new URLSearchParams({library_id:t.base.library})}`,'GET',undefined,t.base,t.token);assertCurrent(t.base,t.token);if(ticket!==readGeneration)fail('scope_changed');const detail=validateThreadDetail(raw,t.base.library,id);pendingCreation=null;activeThread=detail.thread;revision=detail.thread.revision;currentResult=null;contextState='requires_search';historyDetail=ownHistory(detail);publish();return detail;}
    async function older(){
      const t=begin(),owned=historyDetail,threadId=activeThread?.thread_id;
      if(!capabilities?.history_paging||!owned||!threadId||owned.thread.thread_id!==threadId||owned.history_stale||!owned.has_older_exchanges||
        !safeInt(owned.snapshot_revision)||!safeInt(owned.before_revision)||owned.before_revision<1||historyLoading||pendingTurn)fail(historyLoading?'conflict':'invalid_input');
      const snapshotRevision=owned.snapshot_revision,beforeRevision=owned.before_revision,ticket=readGeneration,nonce=++historyNonce;
      const query=new URLSearchParams({library_id:t.base.library,before_revision:String(beforeRevision),snapshot_revision:String(snapshotRevision)});
      historyLoading=true;publish();
      try{
        const raw=await call(`${threadPath(threadId)}/history?${query}`,'GET',undefined,t.base,t.token);
        assertCurrent(t.base,t.token);
        if(ticket!==readGeneration||nonce!==historyNonce||historyDetail!==owned||activeThread?.thread_id!==threadId)fail('scope_changed');
        const page=validateHistoryPage(raw,threadId,t.base.library,snapshotRevision,beforeRevision);
        const ids=new Set(owned.exchanges.map(exchange=>exchange.exchange_id)),revisions=new Set(owned.exchanges.map(exchange=>exchange.revision));
        for(const exchange of page.exchanges){if(ids.has(exchange.exchange_id)||revisions.has(exchange.revision))fail('invalid_response');ids.add(exchange.exchange_id);revisions.add(exchange.revision);}
        const merged=[...page.exchanges,...owned.exchanges];
        for(let i=1;i<merged.length;i++)if(merged[i-1].revision>=merged[i].revision)fail('invalid_response');
        if(merged.length>200||(page.has_older_exchanges&&merged.length>=200))fail('invalid_response');
        const limitReached=false;
        const exchanges=Object.freeze(merged);
        historyDetail=Object.freeze({...owned,exchanges,has_older_exchanges:page.has_older_exchanges&&!limitReached,
          before_revision:page.has_older_exchanges&&!limitReached?page.next_before_revision:null,history_stale:false,history_limit_reached:limitReached});
        historyLoading=false;publish();return historyDetail;
      }catch(error){
        if(nonce===historyNonce&&ticket===readGeneration&&historyDetail===owned){
          historyLoading=false;
          if(error?.status===404||error?.status===409){historyDetail=staleHistory(owned);historyRefreshRequired=true;}
          publish();
        }
        throw error;
      }
    }
    async function getRequest(id,rid,{_ticket,hydrate=true,searchVersion=negotiatedSearchVersion()}={}){const t=_ticket||begin();const path=`${threadPath(id)}/requests/${encodeURIComponent(rid)}?${new URLSearchParams({library_id:t.base.library})}`;const options=searchVersion>=2?{extraHeaders:{'X-PhotoHouse-Search-Version':String(searchVersion)}}:{};const env=validateEnvelope(await call(path,'GET',undefined,t.base,t.token,options),id,rid,t.base.library,'GET',false,false,searchVersion);
      if(env.status==='completed'&&hydrate){const hydrated=await hydrateResult(env.result,t,{readTicket:t.readTicket,threadId:id,revision:env.revision});return Object.freeze({...env,result:hydrated});}return env;}
    async function sendScene(text=sceneDraft){
      const t=begin();if(scenePageActive||!sceneReady()||!validSceneQuery(text))fail('invalid_input');sceneRewordRequired=false;clearScenePage();sceneRankingDigest=null;
      const rid=typeof newUUID==='function'?newUUID():null;if(!uuid(rid))fail('invalid_input');
      clearSpeechSource();savedMemoryReaderSource=null;openingMemoryCard=false;readGeneration++;abortHydrations();invalidateHistory();
      const scopeAtSend=currentResult.version===4?currentResult.context.scene.scope:currentResult.context;
      const sent={thread_id:activeThread.thread_id,request_id:rid,expected_revision:revision,text,search_version:4,mode:'scene'};pendingTurn={...sent,status:'sending'};publish();
      try{const body={library_id:t.base.library,request_id:rid,expected_revision:sent.expected_revision,text,accepts:['scene_search_v1']};
        const v=validateEnvelope(await call(`${threadPath(sent.thread_id)}/turns`,'POST',body,t.base,t.token,{extraHeaders:{'X-PhotoHouse-Search-Version':'4'}}),sent.thread_id,rid,t.base.library,'POST',false,false,4);
        if(v.status==='completed'){if(v.revision!==sent.expected_revision+1||v.result.context.scene.query!==text||canonical(v.result.context.scene.scope)!==canonical(scopeAtSend))fail('invalid_response');const result=await hydrateResult(v.result,t,{threadId:sent.thread_id,revision:v.revision});assertCurrent(t.base,t.token);activeThread=Object.freeze({...activeThread,revision:v.revision});revision=v.revision;pendingTurn=null;currentResult=result;sceneRequestId=rid;contextState=resultContextState(result);if(sceneDraft===text)sceneDraft='';publish();return Object.freeze({...v,result});}
        if(v.status==='failed'||v.status==='interrupted'){if(v.status==='failed'&&v.error==='scene_query_unsupported'&&v.revision!==sent.expected_revision)fail('invalid_response');pendingTurn=null;currentResult=null;contextState='requires_search';sceneRewordRequired=v.status==='failed'&&v.error==='scene_query_unsupported';publish();return v;}
        pendingTurn={...sent,status:'uncertain'};publish();return v;
      }catch(error){const safe=safeFailure(error);if(safe.code==='scope_changed'||safe.code==='closed'||safe.status===401||safe.status===403)throw safe;if(safe.status===400||safe.status===409){pendingTurn=null;currentResult=null;contextState='requires_search';if(safe.code==='search_version_unsupported'){sceneProbeNonce++;sceneAvailable=false;}invalidateHistory();publish();throw safe;}pendingTurn={...sent,status:'uncertain'};currentResult=null;contextState='requires_search';publish();throw safe;}
    }
    async function send(text=draft){const t=begin();if(scenePageActive)fail('conflict');if(!activeThread||activeThread.library_id!==t.base.library)fail('invalid_input');if(typeof text!=='string'||!text.trim()||byteLength(text)>1024)fail('invalid_input');if(pendingTurn)fail('conflict');sceneRewordRequired=false;const rid=typeof newUUID==='function'?newUUID():null;if(!uuid(rid))fail('invalid_input');const searchVersion=negotiatedSearchVersion();const memoryOptIn=savedMemoryAvailable===true&&capabilities?.available===true&&capabilities?.server_owned_turns===true,memoryProbeNonce=savedMemoryProbeNonce,memorySpeechProbeNonce=savedMemorySpeechProbeNonce,memorySpeechAllowedAtSend=memoryOptIn&&savedMemorySpeechAvailable&&capabilities?.reply_speech===true;
      // Capture the current fresh display cohort before the send clears the result
      // and reader source. This anchor is independent of reply speech and survives
      // the voice End action until an explicit new turn or history/scope change.
      const source=savedMemoryReaderSource,memoryParentReady=stateValue().savedMemoryFollowupReady||stateValue().savedMemoryActionReady;
      const memoryParent=memoryParentReady&&memoryOptIn&&(savedMemoryFollowupAvailable||savedMemoryActionsAvailable)&&source&&source.result===currentResult&&source.thread_id===activeThread.thread_id&&activeThread.revision===revision&&source.revision===revision&&source.account===t.base.account&&source.library===t.base.library&&source.generation===t.base.generation&&CANONICAL_MEMORY_UUID.test(source.request_id)&&safeInt(source.revision)?{request_id:source.request_id,revision:source.revision}:null;
      clearSpeechSource();savedMemoryReaderSource=null;openingMemoryCard=false;readGeneration++;abortHydrations();invalidateHistory();const sent={thread_id:activeThread.thread_id,request_id:rid,expected_revision:revision,text,search_version:searchVersion};pendingTurn={...sent,status:'sending'};publish();
      const memoryActionsOptIn=memoryOptIn&&savedMemoryActionsAvailable===true,memoryActionsProbeNonce=savedMemoryActionsProbeNonce;
      try{const body={library_id:t.base.library,request_id:rid,expected_revision:sent.expected_revision,text};if(memoryOptIn)body.accepts=memoryActionsOptIn?['saved_memory_cards_v1','saved_memory_actions_v1']:['saved_memory_cards_v1'];if(memoryParent&&memoryOptIn&&(savedMemoryFollowupAvailable||savedMemoryActionsAvailable))body.memory_parent=memoryParent;
        const turnOptions=searchVersion>=2?{extraHeaders:{'X-PhotoHouse-Search-Version':String(searchVersion)}}:{};
        const v=validateEnvelope(await call(`${threadPath(sent.thread_id)}/turns`,'POST',body,t.base,t.token,turnOptions),sent.thread_id,rid,t.base.library,'POST',memoryOptIn,memoryActionsOptIn,searchVersion);
        if(memoryOptIn&&v.status==='completed'&&!v.recovered&&Object.hasOwn(v.result,'memory_cards')&&memoryProbeNonce!==savedMemoryProbeNonce){pendingTurn={...sent,status:'uncertain'};publish();fail('context_changed');}
        if(memoryActionsOptIn&&v.status==='completed'&&!v.recovered&&Object.hasOwn(v.result,'memory_action')&&memoryActionsProbeNonce!==savedMemoryActionsProbeNonce){pendingTurn={...sent,status:'uncertain'};publish();fail('context_changed');}
        if(v.status==='completed'){const memoryResult=Object.hasOwn(v.result,'memory_cards');const result=memoryResult?v.result:await hydrateResult(v.result,t,{threadId:sent.thread_id,revision:v.revision});assertCurrent(t.base,t.token);activeThread=Object.freeze({...activeThread,revision:v.revision});revision=v.revision;pendingTurn=null;currentResult=result;contextState=memoryResult?'requires_search':resultContextState(result);if(draft===text)draft='';if(!v.recovered&&memoryResult)savedMemoryReaderSource={thread_id:sent.thread_id,request_id:rid,revision:v.revision,account:t.base.account,library:t.base.library,generation:t.base.generation,result};if(!v.recovered&&memoryResult&&memorySpeechAllowedAtSend&&memorySpeechProbeNonce===savedMemorySpeechProbeNonce&&savedMemoryAvailable&&savedMemorySpeechAvailable&&capabilities?.reply_speech===true)speechSource={thread_id:sent.thread_id,request_id:rid,revision:v.revision,account:t.base.account,library:t.base.library,generation:t.base.generation,replyBytes:byteLength(result.reply),kind:result.kind,savedMemory:true,search_version:1};else if(!v.recovered&&!memoryResult)speechSource={thread_id:sent.thread_id,request_id:rid,revision:v.revision,account:t.base.account,library:t.base.library,generation:t.base.generation,replyBytes:byteLength(result.reply),kind:result.kind,search_version:result.version>=2?result.version:1};publish();return Object.freeze({...v,result});}
        if(v.status==='failed'||v.status==='interrupted'){if(!draft)draft=text;pendingTurn=null;contextState='requires_search';publish();return v;}
        pendingTurn={...sent,status:'uncertain'};publish();return v;
      }catch(e){const safe=safeFailure(e);if(safe.code==='scope_changed'||safe.code==='closed'||safe.status===401||safe.status===403)throw safe;pendingTurn={...sent,status:'uncertain'};publish();throw safe;}}
    async function openMemoryCard(ordinal,validateReader){
      const t=begin(),source=savedMemoryReaderSource,ready=stateValue();
      if(!Number.isSafeInteger(ordinal)||ordinal<0||typeof validateReader!=='function'||openingMemoryCard||!ready.savedMemoryReaderReady||!source||source.result!==currentResult||!Array.isArray(source.result.memory_cards)||ordinal>=source.result.memory_cards.length)fail('invalid_input');
      if(pendingTurn||pendingCreation)fail('conflict');
      const card=source.result.memory_cards[ordinal];if(!card||!['story','memoir'].includes(card.kind)||!uuid(card.id)||!(/^[1-9][0-9]{0,18}$/.test(card.revision)))fail('invalid_response');
      openingMemoryCard=true;publish();
      try{
        const query=new URLSearchParams({library_id:t.base.library,expected_revision:String(source.revision)});
        const raw=await call(`${threadPath(source.thread_id)}/requests/${encodeURIComponent(source.request_id)}/memory-cards/${ordinal}?${query}`,'GET',undefined,t.base,t.token,{maxJsonBytes:1024*1024});
        assertCurrent(t.base,t.token);
        if(savedMemoryReaderSource!==source||currentResult!==source.result||activeThread?.thread_id!==source.thread_id||revision!==source.revision||source.account!==t.base.account||source.library!==t.base.library||source.generation!==t.base.generation||!savedMemoryReaderAvailable||!savedMemoryAvailable)fail('scope_changed');
        if(!exactKeys(raw,['version','kind','reader'])||raw.version!==1||raw.kind!==card.kind||!isObject(raw.reader)||raw.reader.id!==card.id||raw.reader.revision!==card.revision)fail('invalid_response');
        let size;try{size=new TextEncoder().encode(JSON.stringify(raw.reader)).length;}catch(_){fail('invalid_response');}
        if(size>1024*1024||validateReader(card.kind,raw.reader)!==true)fail('invalid_response');
        return Object.freeze({kind:card.kind,reader:raw.reader,ordinal,card});
      }finally{openingMemoryCard=false;publish();}
    }
    async function speakReply({signal}={}){
      const t=begin(),source=speechSource;
      if(scenePageActive||scenePageLoading||capabilities?.reply_speech!==true||!source||source.kind==='open'||!activeThread||source.thread_id!==activeThread.thread_id||source.revision!==revision||source.account!==t.base.account||source.library!==t.base.library||source.generation!==t.base.generation||pendingTurn||pendingCreation||
        (source.savedMemory&&(!savedMemoryAvailable||!savedMemorySpeechAvailable)))fail('invalid_input');
      if(source.replyBytes>600)fail('invalid_input');
      const speechId=typeof newUUID==='function'?newUUID():null;if(!uuid(speechId)||speechId===source.request_id)fail('invalid_input');
      const audioController=new AbortController(),entry={controller:audioController,source},abort=()=>audioController.abort();
      if(signal?.aborted)audioController.abort();else signal?.addEventListener('abort',abort,{once:true});
      speechControllers.add(entry);
      try{
        if(audioController.signal.aborted)fail('aborted');
        let responseValidated=false;
        const raw=await call(`${threadPath(source.thread_id)}/requests/${encodeURIComponent(source.request_id)}/speech`, 'POST',
          {library_id:t.base.library,expected_revision:source.revision},t.base,t.token,{
            responseType:'blob',signal:audioController.signal,
            extraHeaders:{'X-PhotoHouse-Request-Id':speechId,'X-PhotoHouse-Parent-Request-Id':source.request_id,...(source.search_version>=2&&!source.savedMemory?{'X-PhotoHouse-Search-Version':String(source.search_version)}:{})},
            onResponse:response=>{
              const headers=response?.headers;
              if(!headers||typeof headers.get!=='function')return;
              const cache=(headers.get('Cache-Control')||'').split(',').map(x=>x.trim().toLowerCase());
              const encoding=headers.get('Content-Encoding');
              const mime=(headers.get('Content-Type')||'').split(';')[0].trim().toLowerCase();
              responseValidated=response.ok===true&&response.status===200&&headers.get('X-PhotoHouse-Request-Id')===speechId&&
                headers.get('X-PhotoHouse-Tracking')==='enabled'&&headers.get('X-PhotoHouse-Receipt-Status')==='succeeded'&&
                mime==='audio/wav'&&cache.includes('no-store')&&(!encoding||encoding.trim().toLowerCase()==='identity');
            }
          });
        assertCurrent(t.base,t.token);
        if(audioController.signal.aborted)fail('aborted');
        if(speechSource!==source||activeThread?.thread_id!==source.thread_id||revision!==source.revision||
          (source.savedMemory&&(!savedMemoryAvailable||!savedMemorySpeechAvailable)))fail('scope_changed');
        if(!responseValidated)fail('invalid_response');
        const audio=await validateSpeechBlob(raw);
        // Blob parsing is asynchronous; revoke bytes if Pause, scope change, or a
        // newer turn/capability probe occurred while the response was validated.
        assertCurrent(t.base,t.token);
        if(audioController.signal.aborted)fail('aborted');
        if(speechSource!==source||activeThread?.thread_id!==source.thread_id||revision!==source.revision||
          (source.savedMemory&&(!savedMemoryAvailable||!savedMemorySpeechAvailable)))fail('scope_changed');
        return audio;
      }finally{signal?.removeEventListener('abort',abort);speechControllers.delete(entry);}
    }
    async function speakMemoryOpening(ordinal,{signal}={}){
      const t=begin(),source=savedMemoryReaderSource,ready=stateValue();
      if(!Number.isSafeInteger(ordinal)||ordinal<0||ordinal>=MAX_MEMORY_CARDS||!ready.savedMemoryReadingReady||!source||source.result!==currentResult||!Array.isArray(source.result.memory_cards)||ordinal>=source.result.memory_cards.length||openingMemorySpeechOrdinal!==null||segmentMemorySpeechOrdinal!==null)fail('invalid_input');
      if(pendingTurn||pendingCreation||openingMemoryCard)fail('conflict');
      const card=source.result.memory_cards[ordinal];if(!card||!['story','memoir'].includes(card.kind)||!CANONICAL_MEMORY_UUID.test(card.id))fail('invalid_response');
      const probeNonce=savedMemoryReadingProbeNonce, speechId=typeof newUUID==='function'?newUUID():null;
      if(!uuid(speechId)||speechId===source.request_id)fail('invalid_input');
      const audioController=new AbortController(),entry={controller:audioController,source:{...source,savedMemory:true,savedMemoryOpening:true}},abort=()=>audioController.abort();
      if(signal?.aborted)audioController.abort();else signal?.addEventListener('abort',abort,{once:true});
      openingMemorySpeechOrdinal=ordinal;openingMemorySpeechEntry=entry;speechControllers.add(entry);publish();
      const current=()=>savedMemoryReaderSource===source&&currentResult===source.result&&activeThread?.thread_id===source.thread_id&&activeThread?.revision===source.revision&&revision===source.revision&&source.account===t.base.account&&source.library===t.base.library&&source.generation===t.base.generation&&savedMemoryAvailable&&savedMemorySpeechAvailable&&savedMemoryReadingAvailable&&probeNonce===savedMemoryReadingProbeNonce&&!pendingTurn&&!pendingCreation&&!openingMemoryCard;
      try{
        if(audioController.signal.aborted)fail('aborted');
        let responseValidated=false;
        const raw=await call(`${threadPath(source.thread_id)}/requests/${encodeURIComponent(source.request_id)}/memory-cards/${ordinal}/speech`,'POST',
          {library_id:t.base.library,expected_revision:source.revision},t.base,t.token,{
            responseType:'blob',signal:audioController.signal,
            extraHeaders:{'X-PhotoHouse-Request-Id':speechId,'X-PhotoHouse-Parent-Request-Id':source.request_id},
            onResponse:response=>{
              const headers=response?.headers;if(!headers||typeof headers.get!=='function')return;
              const cache=(headers.get('Cache-Control')||'').split(',').map(x=>x.trim().toLowerCase()),encoding=headers.get('Content-Encoding'),mime=(headers.get('Content-Type')||'').split(';')[0].trim().toLowerCase();
              responseValidated=response.ok===true&&response.status===200&&headers.get('X-PhotoHouse-Request-Id')===speechId&&headers.get('X-PhotoHouse-Tracking')==='enabled'&&headers.get('X-PhotoHouse-Receipt-Status')==='succeeded'&&mime==='audio/wav'&&cache.includes('no-store')&&(!encoding||encoding.trim().toLowerCase()==='identity');
            }
          });
        assertCurrent(t.base,t.token);if(audioController.signal.aborted)fail('aborted');if(!current())fail('scope_changed');if(!responseValidated)fail('invalid_response');
        const audio=await validateSpeechBlob(raw);
        assertCurrent(t.base,t.token);if(audioController.signal.aborted)fail('aborted');if(!current())fail('scope_changed');return audio;
      }finally{signal?.removeEventListener('abort',abort);speechControllers.delete(entry);if(openingMemorySpeechEntry===entry){openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;publish();}}
    }
    async function speakMemorySegment(ordinal,segment,{signal,expectedSegmentCount=null}={}){
      const t=begin(),source=savedMemoryReaderSource,ready=stateValue();
      if(!Number.isSafeInteger(ordinal)||ordinal<0||ordinal>=MAX_MEMORY_CARDS||!Number.isSafeInteger(segment)||segment<0||segment>127||
        !ready.savedMemorySegmentReadingReady||!source||source.result!==currentResult||!Array.isArray(source.result.memory_cards)||ordinal>=source.result.memory_cards.length||
        openingMemorySpeechOrdinal!==null||segmentMemorySpeechOrdinal!==null||openingMemoryCard||pendingTurn||pendingCreation)fail('invalid_input');
      if(segment===0){if(expectedSegmentCount!==null)fail('invalid_input');}
      else if(!Number.isSafeInteger(expectedSegmentCount)||expectedSegmentCount<1||expectedSegmentCount>128||expectedSegmentCount<=segment)fail('invalid_input');
      const card=source.result.memory_cards[ordinal];if(!card||!['story','memoir'].includes(card.kind)||!CANONICAL_MEMORY_UUID.test(card.id))fail('invalid_response');
      const probeNonce=savedMemorySegmentReadingProbeNonce,speechId=typeof newUUID==='function'?newUUID():null;
      if(!uuid(speechId)||speechId===source.request_id)fail('invalid_input');
      const audioController=new AbortController(),entry={controller:audioController,source:{...source,savedMemory:true,savedMemorySegment:true,segment}},abort=()=>audioController.abort();
      if(signal?.aborted)audioController.abort();else signal?.addEventListener('abort',abort,{once:true});
      segmentMemorySpeechOrdinal=ordinal;segmentMemorySpeechIndex=segment;segmentMemorySpeechEntry=entry;speechControllers.add(entry);publish();
      const current=()=>savedMemoryReaderSource===source&&currentResult===source.result&&activeThread?.thread_id===source.thread_id&&activeThread?.revision===source.revision&&revision===source.revision&&source.account===t.base.account&&source.library===t.base.library&&source.generation===t.base.generation&&savedMemoryAvailable&&savedMemorySpeechAvailable&&savedMemorySegmentReadingAvailable&&probeNonce===savedMemorySegmentReadingProbeNonce&&!pendingTurn&&!pendingCreation&&!openingMemoryCard;
      try{
        if(audioController.signal.aborted)fail('aborted');
        let responseValidated=false,responseCount=null;
        const raw=await call(`${threadPath(source.thread_id)}/requests/${encodeURIComponent(source.request_id)}/memory-cards/${ordinal}/segments/${segment}/speech`,'POST',
          {library_id:t.base.library,expected_revision:source.revision},t.base,t.token,{
            responseType:'blob',signal:audioController.signal,
            extraHeaders:{'X-PhotoHouse-Request-Id':speechId,'X-PhotoHouse-Parent-Request-Id':source.request_id},
            onResponse:response=>{
              const headers=response?.headers;if(!headers||typeof headers.get!=='function')return;
              const cache=(headers.get('Cache-Control')||'').split(',').map(x=>x.trim().toLowerCase()),encoding=headers.get('Content-Encoding'),mime=(headers.get('Content-Type')||'').split(';')[0].trim().toLowerCase();
              const segmentHeader=headers.get('X-PhotoHouse-Reading-Segment'),countHeader=headers.get('X-PhotoHouse-Reading-Segment-Count');
              const canonical=(value,min,max)=>typeof value==='string'&&/^(0|[1-9][0-9]*)$/.test(value)&&Number.isSafeInteger(Number(value))&&Number(value)>=min&&Number(value)<=max&&String(Number(value))===value;
              if(canonical(segmentHeader,0,127)&&Number(segmentHeader)===segment&&canonical(countHeader,1,128)&&Number(countHeader)>segment){responseCount=Number(countHeader);responseValidated=true;}
              responseValidated=responseValidated&&response.ok===true&&response.status===200&&headers.get('X-PhotoHouse-Request-Id')===speechId&&headers.get('X-PhotoHouse-Tracking')==='enabled'&&headers.get('X-PhotoHouse-Playback-Tracking')==='enabled'&&headers.get('X-PhotoHouse-Receipt-Status')==='succeeded'&&mime==='audio/wav'&&cache.includes('no-store')&&(!encoding||encoding.trim().toLowerCase()==='identity');
            }
          });
        assertCurrent(t.base,t.token);if(audioController.signal.aborted)fail('aborted');if(!current())fail('scope_changed');if(!responseValidated||responseCount===null||expectedSegmentCount!==null&&responseCount!==expectedSegmentCount)fail('invalid_response');
        const audio=await validateSpeechBlob(raw);
        assertCurrent(t.base,t.token);if(audioController.signal.aborted)fail('aborted');if(!current())fail('scope_changed');return Object.freeze({audio,segmentCount:responseCount});
      }finally{signal?.removeEventListener('abort',abort);speechControllers.delete(entry);if(segmentMemorySpeechEntry===entry){segmentMemorySpeechEntry=null;segmentMemorySpeechOrdinal=null;segmentMemorySpeechIndex=null;publish();}}
    }
    async function deleteThread(id=activeThread?.thread_id){if(!uuid(id))fail('invalid_input');const t=begin();const item=id===activeThread?.thread_id?activeThread:threads.find(x=>x.thread_id===id);if(!item)fail('invalid_input');if(pendingTurn?.thread_id===id)fail('conflict');if(activeThread?.thread_id===id){clearSpeechSource();savedMemoryReaderSource=null;openingMemoryCard=false;}const raw=await call(threadPath(id),'DELETE',{library_id:t.base.library,expected_revision:item.revision},t.base,t.token);if(!isObject(raw)||raw.deleted!==true||raw.thread_id!==id)fail('invalid_response');readGeneration++;historyNonce++;historyLoading=false;if(activeThread?.thread_id===id){abortHydrations();clearHistory();activeThread=null;revision=0;currentResult=null;contextState='unavailable';sceneRewordRequired=false;}threads=threads.filter(x=>x.thread_id!==id);publish();return Object.freeze({thread_id:id,deleted:true});}
    async function readPreferences(){const t=begin();preferences=validatePrefs(await call(`${BASE}/preferences?${new URLSearchParams({library_id:t.base.library})}`,'GET',undefined,t.base,t.token));publish();return preferences;}
    async function updatePreferences(changes){const t=begin();if(!isObject(changes)||!Object.keys(changes).length||Object.keys(changes).some(k=>!Object.hasOwn(PREFS,k)||!PREFS[k].includes(changes[k])))fail('invalid_input');const current=preferences||await readPreferences();assertCurrent(t.base,t.token);const body={library_id:t.base.library,expected_revision:current.revision,...changes};preferences=validatePrefs(await call(`${BASE}/preferences`,'PUT',body,t.base,t.token));publish();return preferences;}
    async function resetPreferences(){const t=begin(),current=preferences||await readPreferences();assertCurrent(t.base,t.token);preferences=validatePrefs(await call(`${BASE}/preferences/reset`,'POST',{library_id:t.base.library,expected_revision:current.revision},t.base,t.token));publish();return preferences;}
    function close(){if(closed)return;closed=true;sceneProbeNonce++;sceneAvailable=false;scenePageAvailable=false;sceneRequestId=null;sceneRankingDigest=null;clearScenePage();sceneDraft='';sceneRewordRequired=false;instance++;for(const c of controllers)c.abort();controllers.clear();abortHydrations();readGeneration++;savedMemoryProbeNonce++;savedMemorySpeechProbeNonce++;savedMemoryReaderProbeNonce++;savedMemoryFollowupProbeNonce++;savedMemoryReadingProbeNonce++;savedMemorySegmentReadingProbeNonce++;savedMemoryActionsProbeNonce++;savedMemoryAvailable=false;savedMemorySpeechAvailable=false;savedMemoryReaderAvailable=false;savedMemoryFollowupAvailable=false;savedMemoryReadingAvailable=false;savedMemorySegmentReadingAvailable=false;savedMemoryActionsAvailable=false;savedMemoryReaderSource=null;openingMemoryCard=false;openingMemorySpeechOrdinal=null;openingMemorySpeechEntry=null;resetMemorySegmentSpeech();clearHistory();clearSpeechSource();capabilities=null;threads=[];activeThread=null;draft='';pendingTurn=null;pendingCreation=null;preferences=null;revision=0;currentResult=null;contextState='unavailable';publish();}
    return Object.freeze({state,setDraft,setSceneDraft,sendScene,sceneCapabilities:sceneCapabilitiesRead,scenePageCapabilities:scenePageCapabilitiesRead,scenePage:scenePageRead,returnSceneResults,capabilities:capabilitiesRead,savedMemoryCapabilities:savedMemoryCapabilitiesRead,savedMemoryActionsCapabilities:savedMemoryActionsCapabilitiesRead,savedMemorySpeechCapabilities:savedMemorySpeechCapabilitiesRead,savedMemoryReaderCapabilities:savedMemoryReaderCapabilitiesRead,savedMemoryFollowupCapabilities:savedMemoryFollowupCapabilitiesRead,savedMemoryReadingCapabilities:savedMemoryReadingCapabilitiesRead,savedMemorySegmentReadingCapabilities:savedMemorySegmentReadingCapabilitiesRead,openMemoryCard,list,create,reconcileCreation,read,older,send,speakReply,speakMemoryOpening,speakMemorySegment,discardSpeechSource,recover,abandonPending,delete:deleteThread,readPreferences,updatePreferences,resetPreferences,close});
  }
  return Object.freeze({createController,PrivateAssistantError,validateThread,validateExchange,validateCapabilities,validateSavedMemoryFollowupCapabilities,validateSavedMemoryActionCapabilities,validateHistoryPage,validatePrefs,validateEnvelope,validateResult,validateSceneCapabilities,safeJson,uuid,validUtc});
});
