'use strict';
/* Explicit, source-linked memory group editor. All state stays in this mount. */
window.PhotoHouseMemoryGroups = {
  create({scope, api, onStory}) {
    let generation = 0;
    let recentSequence = 0;
    let root = null;
    let mounted = null;
    const scopeNow = () => typeof scope === 'function' ? scope() : scope;
    const scopeKey = value => JSON.stringify([value?.account, value?.library, value?.epoch]);
    const strings = {
      zh: {
        title:'家庭回忆组', open:'家庭回忆组', loading:'正在载入…', unavailable:'家庭回忆组暂时不可用。',
        disabled:'此相册库尚未开启家庭回忆组。', failed:'暂时无法载入，请重试。', retry:'重试载入',
        recentEmpty:'暂无可查看的近期回忆组。', recentUnavailable:'此相册库暂时无法查看近期回忆组。',
        recentCount:n=>`${n} 项照片或视频`, browse:'查看组内照片和视频',
        create:'新建回忆组', edit:'编辑', save:'明确保存回忆组', cancel:'取消编辑',
        split:'拆分回忆组', splitHelp:'选择要移入新组的画面。关联的家人原话随对应画面移动。',
        splitCount:(moved, kept)=>`移入新组 ${moved} 张 · 原组保留 ${kept} 张`,
        splitItem:n=>`移动画面 ${n}`, splitSaved:'已将选定画面移入新回忆组。',
        startStory:'开始写故事', checkingStory:'正在核对回忆组…', storyChanged:'回忆组已变化或暂不可用，请刷新后重试。',
        theme:'主题', themes:{trip:'旅行',growing_up:'成长',birthday:'生日',grandparents:'祖辈',year_in_review:'年度回顾',everyday:'日常'},
        addMedia:'从当前相册选择画面', included:'组内顺序', remove:'移出此组',
        earlier:n=>`将第 ${n} 项前移`, later:n=>`将第 ${n} 项后移`,
        moved:(n,total)=>`已移动到第 ${n} 项，共 ${total} 项。`,
        sameDayHeading:date=>`${date}拍摄的画面`,
        sameDay:'查看同日照片和视频', sameDayMore:'更多同日画面', sameDayAdd:'加入回忆组',
        sameDayPhoto:'照片', sameDayVideo:'视频', sameDayEmpty:'本页没有可加入的同日画面。',
        sameDayFailed:'暂时无法查看同日画面。请重试。',
        suggestions:'查找相似画面', suggestionsHelp:'建议会参考记录的拍摄时间和图片相似度。结果可以逐项修改；不会自动保存。', coverMore:'覆盖更多已选画面',
        timeReason:{within_recorded_window:'拍摄时间接近',same_recorded_day:'记录在同一天'}, seed:'匹配画面', noSuggestions:'没有找到建议画面。',
        notes:'选择要关联的家人原话', noNotes:'没有可关联的家人原话。只会保存来源链接，不复制原文。',
        sources:'关联的家人原话', by:'作者', noSources:'尚未关联家人原话。',
        capture:'记录的拍摄时间', excluded:'已排除的画面', group:'回忆组', more:'查看关联的家人原话',
        failedSave:'保存状态不确定。请用同一份内容重试，或明确丢弃这次待处理保存。', retrySave:'用同一请求重试保存', discard:'丢弃待处理保存',
        confirmLeave:'离开将丢弃尚未保存的回忆组更改。仍要离开吗？',
        saved:'已保存。', saveError:'暂时无法确认保存结果。', invalid:'至少保留一张画面；每组最多 24 张。', sourceLimit:'每组最多关联 12 条家人原话。',
        locked:'请先解锁相册库。', review:'原话由家人提供，请查看作者和署名。',
        manualDisabled:'手动编辑已关闭。', suggestionsDisabled:'相似画面建议已关闭。',
        suggestionsError:'暂时无法生成建议。', groupsEmpty:'这张画面还没有所属回忆组。',
        sourceStory:'家人原话', count:(n,max)=>`${n} / ${max}`
      },
      en: {
        title:'Family memory groups', open:'Family memory groups', loading:'Loading…', unavailable:'Memory groups are temporarily unavailable.',
        disabled:'Memory groups are not enabled for this library.', failed:'Could not load this yet. Try again.', retry:'Retry loading',
        recentEmpty:'No recent memory groups are available.', recentUnavailable:'Recent groups are unavailable in this library.',
        recentCount:n=>n===1?'1 item':`${n} items`, browse:'View photos and videos',
        create:'Create a memory group', edit:'Edit', save:'Save this memory group', cancel:'Cancel editing',
        split:'Split group', splitHelp:'Select photos or videos for the new group. Linked notes move with their items.',
        splitCount:(moved, kept)=>`${moved} to the new group · ${kept} stay here`,
        splitItem:n=>`Move item ${n}`, splitSaved:'The selected items moved to a new memory group.',
        startStory:'Start a story', checkingStory:'Checking this memory group…', storyChanged:'This memory group changed or is unavailable. Refresh and try again.',
        theme:'Theme', themes:{trip:'Trip',growing_up:'Growing up',birthday:'Birthday',grandparents:'Grandparents',year_in_review:'Year in review',everyday:'Everyday'},
        addMedia:'Choose from this gallery', included:'Group order', remove:'Remove from group',
        earlier:n=>`Move item ${n} earlier`, later:n=>`Move item ${n} later`,
        moved:(n,total)=>`Moved to position ${n} of ${total}.`,
        sameDayHeading:date=>`From ${date}`,
        sameDay:'Find photos and videos from this day', sameDayMore:'More from this day', sameDayAdd:'Add to group',
        sameDayPhoto:'Photo', sameDayVideo:'Video', sameDayEmpty:'There are no items to add on this page.',
        sameDayFailed:'Could not load photos and videos from this day. Try again.',
        suggestions:'Find similar photos', suggestionsHelp:'Suggestions use recorded capture time and image similarity. Review and edit each result; nothing is saved automatically.', coverMore:'Cover more selected moments',
        timeReason:{within_recorded_window:'Recorded times are close',same_recorded_day:'Recorded on the same day'}, seed:'Matched photo', noSuggestions:'No suggested photos found.',
        notes:'Link family originals', noNotes:'No family originals can be linked. Only source links are saved; original text is not copied.',
        sources:'Linked family originals', by:'By', noSources:'No family originals are linked yet.',
        capture:'Recorded capture time', excluded:'Excluded photos', group:'Memory group', more:'View linked family originals',
        failedSave:'Save status is uncertain. Retry with the same content, or explicitly discard this pending save.', retrySave:'Retry the same save request', discard:'Discard pending save',
        confirmLeave:'Leaving discards unsaved memory group changes. Continue?',
        saved:'Saved.', saveError:'Could not confirm the save result.', invalid:'Keep at least one photo; each group holds at most 24.', sourceLimit:'Each group can link up to 12 family originals.',
        locked:'Unlock this library first.', review:'Family originals show their author and byline.',
        manualDisabled:'Manual editing is disabled.', suggestionsDisabled:'Similar photo suggestions are disabled.',
        suggestionsError:'Could not create suggestions yet.', groupsEmpty:'This photo is not in a memory group yet.',
        sourceStory:'Family original', count:(n,max)=>`${n} / ${max}`
      }
    };
    const t = key => (strings[scopeNow()?.language === 'en' ? 'en' : 'zh'][key]);
    const node = (tag, text='', cls='') => { const el=document.createElement(tag); if(text!==null&&text!==undefined)el.textContent=String(text); if(cls)el.className=cls; return el; };
    const button = (text, fn, cls='memory-group-button') => { const el=node('button',text,cls);el.type='button';el.addEventListener('click',fn);return el; };
    const idOk = value => typeof value==='string'&&/^[1-9][0-9]{0,18}$/.test(value);
    const uuidOk = value => typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
    const active = state => state===mounted && state.generation===generation && state.container?.isConnected!==false &&
      !scopeNow()?.locked && scopeKey(scopeNow())===state.scopeKey;
    const safeThumbnail = item => {
      if(!idOk(item?.id)||typeof item.thumbnail_url!=='string')return false;
      try{
        const base=new URL(window.location?.href||'https://photohouse.invalid/');
        const parsed=new URL(item.thumbnail_url,base);
        return parsed.origin===base.origin&&parsed.pathname===`/assets/${item.id}/thumbnail`&&
          parsed.searchParams.getAll('library').length===1&&parsed.searchParams.get('library')===String(scopeNow()?.library)&&[...parsed.searchParams.keys()].every(key=>key==='library');
      }catch(_){return false;}
    };
    const image = item => {
      const figure=node('figure','', 'memory-group-item');
      if(safeThumbnail(item)){
        const img=node('img');img.src=item.thumbnail_url;img.alt='';img.loading='lazy';figure.append(img);
      }
      const caption=node('figcaption',item?.taken_at?`${t('capture')}: ${formatCaptureTime(item.taken_at)}`:t(item?.kind==='video'?'sameDayVideo':'sameDayPhoto'));
      figure.append(caption);return figure;
    };
    function captureParts(value) {
      if(typeof value!=='string'||value.length>128)return null;
      const match=/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,6})?)?(Z|[+-]\d{2}:?\d{2})?)?$/.exec(value);
      if(!match)return null;
      const [,year,month,day,hour,minute,second,zone]=match;const y=Number(year),m=Number(month),d=Number(day);
      const check=new Date(0);check.setUTCFullYear(y,m-1,d);check.setUTCHours(0,0,0,0);if(y===0||check.getUTCFullYear()!==y||check.getUTCMonth()!==m-1||check.getUTCDate()!==d)return null;
      if(hour!==undefined&&(Number(hour)>23||Number(minute)>59||Number(second||0)>59))return null;
      if(zone&&zone!=='Z'){const digits=zone.slice(1).replace(':','');if(Number(digits.slice(0,2))>23||Number(digits.slice(2))>59)return null;}
      return match;
    }
    function formatCaptureTime(value) {
      const parts=captureParts(value);
      if(!parts)return typeof value==='string'?value:'';
      const [,year,month,day,hour,minute,,zone]=parts;
      let timezone='';if(zone==='Z')timezone=' UTC';else if(zone){const digits=zone.slice(1).replace(':','');timezone=` UTC${zone[0]}${digits.slice(0,2)}:${digits.slice(2)}`;}
      const date=scopeNow()?.language==='en'?`${year}-${month}-${day}`:`${year}年${Number(month)}月${Number(day)}日`;
      return hour===undefined?date:`${date} · ${hour}:${minute}${timezone}`;
    }
    const recordedDay = value => captureParts(value)?.slice(1,4).join('-')||null;
    function setStatus(state, text, bad=false) {
      if(!active(state)||!state.status)return;state.status.textContent=text;state.status.dataset.state=bad?'error':'ready';
    }
    function request(state,path,options={}) { return api(path,{...options,epoch:state.epoch}); }
    async function showRecent(panel,onOpen) {
      const binding=scopeNow();
      const serial=++recentSequence;
      const current=()=>serial===recentSequence&&panel.open&&!scopeNow()?.locked&&
        scopeKey(scopeNow())===scopeKey(binding);
      const status=panel.querySelector('#recent-groups-status');
      const list=panel.querySelector('#recent-group-list');
      const refresh=panel.querySelector('#recent-groups-refresh');
      let opening=false;
      list.replaceChildren();status.textContent=t('loading');refresh.disabled=true;
      try{
        const caps=await request(binding,'/memory-groups/capabilities');
        if(!current())return;
        if(caps?.version!==1||caps.enabled!==true||caps.recent!==true){
          status.textContent=t('recentUnavailable');refresh.hidden=true;return;
        }
        const result=await request(binding,'/memory-groups');
        if(!current())return;
        const items=result?.items;
        if(result?.version!==1||result.library_id!==binding.library||!Array.isArray(items)||items.length>8||
            new Set(items.map(group=>group?.id)).size!==items.length||
            items.some(group=>!uuidOk(group?.id)||typeof group.revision!=='string'||
              !/^[1-9][0-9]{0,18}$/.test(group.revision)||!Object.hasOwn(t('themes'),group.theme)||
              !Number.isInteger(group.count)||group.count<1||group.count>24||
              !safeThumbnail(group.cover)||!['image','video'].includes(group.cover.kind)))
          throw Error('Invalid recent memory groups');
        status.textContent=items.length?'':t('recentEmpty');
        for(const group of items){
          const label=t('themes')[group.theme];
          const card=node('li','', 'recent-group-card');
          card.append(node('strong',label),image(group.cover),node('p',t('recentCount')(group.count),'fine'));
          const open=button(t('browse'),async()=>{
            if(!current()||opening)return;
            opening=true;open.disabled=true;status.textContent=t('checkingStory');
            try{
              const latest=await request(binding,`/memory-groups/${encodeURIComponent(group.id)}`);
              if(!current())return;
              if(!validGroup(latest,binding)||latest.id!==group.id||latest.revision!==group.revision)
                throw Error('Memory group changed');
              status.textContent='';
              onOpen(latest.items);
            }catch{
              if(current())status.textContent=t('storyChanged');
            }finally{
              if(current()){opening=false;open.disabled=false;}
            }
          },'quiet recent-group-open');
          open.setAttribute('aria-label',`${t('browse')} · ${label}`);
          card.append(open);list.append(card);
        }
        refresh.hidden=false;
      }catch{
        if(current()){status.textContent=t('failed');refresh.hidden=false;}
      }finally{
        if(current())refresh.disabled=false;
      }
    }
    function validGroup(group,state) {
      const unique=(values,validate)=>Array.isArray(values)&&new Set(values).size===values.length&&values.every(validate);
      if(!group||group.version!==1||group.library_id!==String(state.library)||!uuidOk(group.id)||!/^([1-9][0-9]*)$/.test(String(group.revision))||
        !['trip','growing_up','birthday','grandparents','year_in_review','everyday'].includes(group.theme)||
        !unique(group.asset_ids,idOk)||group.asset_ids.length<1||group.asset_ids.length>24||
        !unique(group.excluded_asset_ids,idOk)||group.excluded_asset_ids.length>512||group.asset_ids.some(id=>group.excluded_asset_ids.includes(id))||
        !unique(group.source_story_ids,uuidOk)||group.source_story_ids.length>12||!Array.isArray(group.items)||group.items.length!==group.asset_ids.length||
        !Array.isArray(group.sources)||typeof group.can_edit!=='boolean')return false;
      const itemIds=group.items.map(item=>item?.id);
      if(!unique(itemIds,idOk)||itemIds.length!==group.asset_ids.length||group.asset_ids.some(id=>!itemIds.includes(id))||group.items.some(item=>!safeThumbnail(item)))return false;
      const sourceIds=group.sources.map(source=>source?.id);
      return unique(sourceIds,uuidOk)&&sourceIds.length<=12&&group.sources.every(source=>
        group.source_story_ids.includes(source.id)&&group.asset_ids.includes(String(source.asset_id))&&typeof source.text==='string');
    }
    function matchesSavedRequest(group,pending,state) {
      if(!validGroup(group,state))return false;
      return pending.body.revision==='0'||group.id===pending.path.split('/').at(-1);
    }
    function sameOrdered(left,right) {
      return Array.isArray(left)&&Array.isArray(right)&&left.length===right.length&&left.every((value,index)=>value===right[index]);
    }
    async function startStory(state,listed,control) {
      if(!active(state)||typeof onStory!=='function')return;
      if(state.storyHandoffs.has(listed.id))return state.storyHandoffs.get(listed.id);
      const handoff=(async()=>{
        control.disabled=true;setStatus(state,t('checkingStory'));
        try{
          const current=await request(state,`/memory-groups/${encodeURIComponent(listed.id)}`);
          if(!active(state)||!validGroup(current,state)||current.id!==listed.id||
              current.revision!==listed.revision||!sameOrdered(current.asset_ids,listed.asset_ids)||
              !sameOrdered(current.items.map(item=>item.id),current.asset_ids)||
              !sameOrdered(current.items.map(item=>item.id),listed.asset_ids))throw Error('Changed group');
          const assets=current.items.map(item=>({id:item.id,kind:item.kind,width:item.width,height:item.height,
            duration_sec:item.duration_sec,taken_at:item.taken_at,thumbnail_url:item.thumbnail_url}));
          const isCurrent=()=>active(state);
          if(isCurrent())await onStory({theme:current.theme,assets},isCurrent);
        }catch(_){if(active(state))setStatus(state,t('storyChanged'),true);}
        finally{if(active(state)){control.disabled=false;state.storyHandoffs.delete(listed.id);}}
      })();
      state.storyHandoffs.set(listed.id,handoff);
      return handoff;
    }
    function section(title, cls='') { const s=node('section','',`memory-group-section${cls?` ${cls}`:''}`);const h=node('h4',title);s.append(h);return s; }
    function renderSources(parent, sources, label=t('sources')) {
      const sec=section(label,'memory-group-sources');
      if(!Array.isArray(sources)||!sources.length)sec.append(node('p',t('noSources')));
      else for(const story of sources){
        if(!story||!uuidOk(story.id))continue;
        const article=node('article','', 'memory-group-source');
        const heading=node('h5',story.title||t('sourceStory'));
        const author=story.byline||story.author_name||story.author_id||t('by');
        const byline=node('p',`${t('by')}: ${author}`,'memory-group-byline');
        const prose=node('p',typeof story.text==='string'?story.text:'','memory-group-prose');
        article.append(heading,byline,prose);sec.append(article);
      }
      parent.append(sec);
    }
    function clearEditor(state) { state.readSequence++;state.editor?.remove();state.editor=null;state.editing=null;state.pendingSave=null;state.saving=false;state.dirty=false;state.refreshStoryChoices=null; }
    function markEditorChanged(state) { state.dirty=true;state.editorRevision++; }
    async function loadGroups(state) {
      const serial=++state.readSequence;
      state.groupsBox.replaceChildren(node('p',t('loading')));
      try {
        const result=await request(state,`/assets/${encodeURIComponent(state.asset.id)}/memory-groups`);
        if(!active(state)||serial!==state.readSequence)return;
        if(!result||result.version!==1||result.library_id!==String(state.library)||String(result.asset_id)!==state.asset.id||!Array.isArray(result.items)||result.items.length>8||result.items.some(group=>!validGroup(group,state)))throw Error('Invalid memory groups response');
        state.groups=result.items;renderGroups(state);setStatus(state,'');
      } catch(_) { if(active(state)&&serial===state.readSequence){state.groupsBox.replaceChildren(node('p',t('failed')));state.groupsBox.append(button(t('retry'),()=>loadGroups(state),'memory-group-retry'));} }
    }
    function renderGroups(state) {
      state.groupsBox.replaceChildren();
      if(!state.capabilities.manual)state.groupsBox.append(node('p',t('manualDisabled')));
      if(!state.capabilities.suggestions)state.groupsBox.append(node('p',t('suggestionsDisabled')));
      if(!state.groups.length)state.groupsBox.append(node('p',t('groupsEmpty')));
      for(const group of state.groups){
        if(!group||!uuidOk(group.id))continue;
        const card=section(t('group'),'memory-group-card');
        card.append(node('p',t(`themes`)?.[group.theme]||group.theme||''));
        const items=node('div','', 'memory-group-items');for(const item of group.items||[])items.append(image(item));card.append(items);
        renderSources(card,group.sources||[]);
        if(typeof onStory==='function'){let start;start=button(t('startStory'),()=>startStory(state,group,start),'memory-group-start-story');card.append(start);}
        if(group.can_edit&&state.capabilities.manual){
          card.append(button(t('edit'),()=>openEditor(state,group),'memory-group-edit'));
          if(state.capabilities.split&&group.asset_ids.length>1){
            card.append(button(t('split'),()=>openSplitEditor(state,group),'memory-group-split'));
          }
        }
        state.groupsBox.append(card);
      }
      if(state.capabilities.manual)state.groupsBox.append(button(t('create'),()=>openEditor(state,null),'memory-group-create'));
    }
    function storyAssetIds(story) {
      const values=[story?.asset_id,story?.asset?.id,...(Array.isArray(story?.asset_ids)?story.asset_ids:[])].filter(idOk);
      return [...new Set(values)];
    }
    function beginEditor(state, group) {
      if(!active(state)||state.pendingSave)return false;
      if(state.editor&&state.dirty&&(state.saving||!window.confirm(t('confirmLeave'))))return false;
      clearEditor(state);state.editing=group||null;
      return true;
    }
    function openSplitEditor(state,group) {
      if(!state.capabilities.split||!group.can_edit||group.asset_ids.length<2||!beginEditor(state,group))return;
      const editor=node('form','', 'memory-group-editor');
      const heading=node('h3',t('split'));
      heading.tabIndex=-1;
      const help=node('p',t('splitHelp'));
      const count=node('p','','memory-group-count');
      count.setAttribute('aria-live','polite');
      const selected=new Set();
      const save=button(t('split'),()=>{},'memory-group-split-save');
      save.type='submit';
      function updateSelection(){
        count.textContent=t('splitCount')(selected.size,group.asset_ids.length-selected.size);
        save.disabled=selected.size<1||selected.size>=group.asset_ids.length;
      }
      editor.append(heading,help,count);
      for(const [i,item] of group.items.entries()){
        const choice=node('label','', 'memory-group-gallery-choice memory-group-split-choice');
        const box=document.createElement('input');
        box.type='checkbox';
        box.setAttribute('aria-label',t('splitItem')(i+1));
        box.addEventListener('change',()=>{
          if(box.checked)selected.add(item.id);
          else selected.delete(item.id);
          state.dirty=selected.size>0;
          updateSelection();
        });
        choice.append(box,image(item));
        editor.append(choice);
      }
      editor.append(save,button(t('cancel'),()=>{
        if(state.dirty&&!window.confirm(t('confirmLeave')))return;
        clearEditor(state);setStatus(state,'');
      },'memory-group-cancel'));
      editor.addEventListener('submit',async event=>{
        event.preventDefault();
        if(!active(state)||state.pendingSave||save.disabled)return;
        const mutation=window.crypto?.randomUUID?.();
        if(!uuidOk(mutation)){setStatus(state,t('saveError'),true);return;}
        const body={asset_ids:group.asset_ids.filter(id=>selected.has(id)).join(','),
          revision:group.revision,mutation_id:mutation};
        state.pendingSave={body,path:`/memory-groups/${encodeURIComponent(group.id)}/split`,splitFrom:group.id};
        await sendPendingSave(state);
      });
      updateSelection();
      state.editor=editor;
      state.groupsBox.append(editor);
      heading.focus();
    }
    function sameDayPicker(state,editor,availableToAdd,add) {
      const day=recordedDay(state.asset.taken_at);
      if(!day)return ()=>{};
      const anchor=state.asset.id;
      const panel=section(t('sameDayHeading')(formatCaptureTime(day)),'memory-group-same-day');
      const heading=panel.querySelector('h4');heading.tabIndex=-1;
      const status=node('p','', 'memory-group-day-status');status.setAttribute('role','status');
      const rows=node('div','', 'memory-group-day-items');
      let before=null,items=null;
      const current=()=>active(state)&&state.editor===editor&&!state.pendingSave;
      function render() {
        if(items===null)return;
        rows.replaceChildren();
        for(const item of items.filter(availableToAdd)){
          const card=node('div','', 'memory-group-day-item');
          card.dataset.kind=item.kind;
          const kind=t(item.kind==='video'?'sameDayVideo':'sameDayPhoto');
          const action=button(t('sameDayAdd'),()=>{
            if(!current()||!availableToAdd(item))return;
            const index=[...rows.children].indexOf(card);
            add(item);
            if(!card.isConnected){
              const neighbor=rows.children[Math.min(index,rows.childElementCount-1)]?.querySelector('button');
              (neighbor||(!load.hidden?load:heading)).focus({preventScroll:true});
            }
          },'memory-group-day-add');
          action.setAttribute('aria-label',`${t('sameDayAdd')} · ${kind} · ${formatCaptureTime(item.taken_at)}`);
          const controls=node('div','', 'memory-group-day-controls');
          controls.append(node('span',kind),action);card.append(image(item),controls);rows.append(card);
        }
        status.textContent=rows.childElementCount?'':t('sameDayEmpty');
      }
      const load=button(t('sameDay'),async()=>{
        if(!current())return;
        load.disabled=true;status.textContent=t('loading');
        try{
          const result=await request(state,'/story-workspace/related-media',{method:'POST',
            body:{asset_ids:anchor,before_id:before||''}});
          if(!current())return;
          if(!result||result.version!==1||result.library_id!==String(state.library)||result.needs_review!==true||
              JSON.stringify(result.seed_asset_ids)!==JSON.stringify([anchor])||
              JSON.stringify(result.recorded_days)!==JSON.stringify([day])||typeof result.has_more!=='boolean'||
              !Array.isArray(result.items)||result.items.length>20)throw Error('Invalid same-day media page');
          let prior=before?BigInt(before):2n**63n;
          for(const item of result.items){
            if(!idOk(item?.id)||item.id===anchor||BigInt(item.id)>=prior||!['image','video'].includes(item.kind)||
                item.match_reason!=='same_recorded_capture_day'||recordedDay(item.taken_at)!==day||!safeThumbnail(item))
              throw Error('Invalid same-day media item');
            prior=BigInt(item.id);
          }
          if(result.has_more?(!idOk(result.next_before_id)||BigInt(result.next_before_id)>prior||
              BigInt(result.next_before_id)>=(before?BigInt(before):2n**63n)):result.next_before_id!==null)
            throw Error('Invalid same-day media cursor');
          before=result.next_before_id;items=result.items;
          load.textContent=t('sameDayMore');load.hidden=!result.has_more;render();
        }catch(_){if(current())status.textContent=t('sameDayFailed');}
        finally{if(current())load.disabled=false;}
      },'memory-group-day-load');
      panel.append(load,status,rows);editor.append(panel);
      return render;
    }
    function openEditor(state, group) {
      if(!beginEditor(state,group))return;
      const baseIds=group?(group.asset_ids||[]).filter(idOk):[state.asset.id];
      const selected=new Set(baseIds);const autoSuggestedIds=new Set();const exclusions=new Set((group?.excluded_asset_ids||[]).filter(idOk));
      state.editorRevision++;
      const sourceChoices=new Map();for(const story of [...state.stories,...(group?.sources||[])])if(story&&uuidOk(story.id)&&typeof story.text==='string')sourceChoices.set(story.id,story);
      const sourceIds=new Set((group?.source_story_ids||[]).filter(uuidOk));
      const proposalSeeds=new Set(baseIds.filter(id=>{
        const item=group?.items?.find(member=>member.id===id)||state.manualItems.find(member=>String(member.id)===id)||state.asset;
        return item?.kind==='image';
      }));
      const editor=node('form','', 'memory-group-editor');editor.noValidate=true;
      const title=node('h3',group?t('edit'):t('create'));editor.append(title);
      const themeLabel=node('label',t('theme'));themeLabel.htmlFor=`memory-group-theme-${state.generation}`;
      const theme=document.createElement('select');theme.id=themeLabel.htmlFor;theme.name='theme';theme.addEventListener('change',()=>markEditorChanged(state));
      for(const key of ['trip','growing_up','birthday','grandparents','year_in_review','everyday']){const option=node('option',t('themes')[key]);option.value=key;option.selected=(group?.theme||'everyday')===key;theme.append(option);}
      themeLabel.append(theme);editor.append(themeLabel);
      const count=node('p',t('count')(selected.size,24),'memory-group-count');editor.append(count);
      let excludedList=null,refreshDayChoices=()=>{};
      const members=section(t('included'),'memory-group-members');const memberRows=node('div','', 'memory-group-items');members.append(memberRows);editor.append(members);
      const manualPicker=section(t('addMedia'),'memory-group-gallery');
      const available=new Map();for(const item of [state.asset,...state.manualItems])if(idOk(item?.id)&&!available.has(item.id))available.set(item.id,item);
      const editable=()=>active(state)&&state.editor===editor&&!state.pendingSave;
      function moveMember(id,step) {
        if(!editable())return;
        const ordered=[...selected],from=ordered.indexOf(id),to=from+step;
        if(from<0||to<0||to>=ordered.length)return;
        [ordered[from],ordered[to]]=[ordered[to],ordered[from]];
        selected.clear();for(const ident of ordered)selected.add(ident);
        autoSuggestedIds.delete(id);markEditorChanged(state);renderMembers();
        const controls=memberRows.children[to];
        const preferred=controls.querySelector(step<0?'.memory-group-earlier':'.memory-group-later');
        (preferred.disabled?controls.querySelector('.memory-group-order button:enabled'):preferred)?.focus({preventScroll:true});
        setStatus(state,t('moved')(to+1,ordered.length));
      }
      const renderMembers=()=>{
        memberRows.replaceChildren();
        [...selected].forEach((id,index)=>{
          const item=available.get(id)||group?.items?.find(v=>v.id===id)||{id};
          const wrap=node('div','', 'memory-group-member');wrap.dataset.assetId=id;wrap.append(image(item));
          if(item.kind==='video')wrap.append(node('span',t('sameDayVideo'),'memory-group-member-kind'));
          if(selected.size>1){
            const controls=node('div','', 'memory-group-order');
            const earlier=button('↑',()=>moveMember(id,-1),'memory-group-earlier');
            const later=button('↓',()=>moveMember(id,1),'memory-group-later');
            earlier.title=t('earlier')(index+1);earlier.setAttribute('aria-label',earlier.title);earlier.disabled=index===0;
            later.title=t('later')(index+1);later.setAttribute('aria-label',later.title);later.disabled=index===selected.size-1;
            controls.append(earlier,later);wrap.append(controls);
          }
          if(id!==state.asset.id||group){const remove=button(t('remove'),()=>{if(!editable())return;markEditorChanged(state);selected.delete(id);autoSuggestedIds.delete(id);exclusions.add(id);for(const box of suggestionList.querySelectorAll('input'))if(box.value===id)box.checked=false;renderMembers();renderGallery();renderStoryChoices();},'memory-group-remove');wrap.append(remove);}
          memberRows.append(wrap);
        });
        count.textContent=t('count')(selected.size,24);
        if(excludedList)excludedList.textContent=exclusions.size?`${t('excluded')}: ${exclusions.size}`:'';
        refreshDayChoices();
      };
      const renderGallery=()=>{
        manualPicker.replaceChildren(node('h4',t('addMedia')));
        for(const [id,item] of available){if(id===state.asset.id||selected.has(id))continue;const label=node('label','', 'memory-group-gallery-choice');const box=document.createElement('input');box.type='checkbox';box.name='manual_asset_ids';box.value=id;box.addEventListener('change',()=>{if(box.checked&&selected.size<24){markEditorChanged(state);selected.add(id);exclusions.delete(id);renderMembers();renderGallery();renderStoryChoices();}else if(box.checked){box.checked=false;setStatus(state,t('invalid'),true);}else{markEditorChanged(state);selected.delete(id);exclusions.add(id);renderMembers();renderGallery();renderStoryChoices();}});label.append(box,image(item));manualPicker.append(label);}
      };
      const renderStoryChoices=()=>{
        for(const story of state.stories)if(story&&uuidOk(story.id)&&typeof story.text==='string')sourceChoices.set(story.id,story);
        const previous=editor.querySelector('.memory-group-story-choices');
        const sec=section(t('notes'),'memory-group-story-choices');sec.append(node('p',t('noNotes')));
        let has=false;for(const story of sourceChoices.values()){if(!story||!uuidOk(story.id)||typeof story.text!=='string')continue;
          const linked=storyAssetIds(story);if(!linked.some(id=>selected.has(id)))continue;has=true;
          const label=node('label','', 'memory-group-story-choice');const box=document.createElement('input');box.type='checkbox';box.name='source_story_ids';box.value=story.id;box.checked=sourceIds.has(story.id);box.addEventListener('change',()=>{if(box.checked&&!sourceIds.has(story.id)&&sourceIds.size>=12){box.checked=false;setStatus(state,t('sourceLimit'),true);return;}markEditorChanged(state);box.checked?sourceIds.add(story.id):sourceIds.delete(story.id);});
          const summary=node('span',`${story.title||t('sourceStory')} · ${story.byline||story.author_name||story.author_id||t('by')}`);label.append(box,summary);sec.append(label);
        }
        if(has)sec.querySelector('p')?.remove();if(previous)previous.replaceWith(sec);else editor.append(sec);
      };
      state.refreshStoryChoices=renderStoryChoices;
      renderMembers();renderGallery();editor.append(manualPicker);
      refreshDayChoices=sameDayPicker(state,editor,item=>!selected.has(item.id)&&!exclusions.has(item.id),item=>{
        if(selected.size>=24){setStatus(state,t('invalid'),true);return;}
        markEditorChanged(state);available.set(item.id,item);selected.add(item.id);
        renderMembers();renderGallery();renderStoryChoices();
      });
      renderStoryChoices();
      excludedList=node('p',exclusions.size?`${t('excluded')}: ${exclusions.size}`:'', 'memory-group-exclusions');editor.append(excludedList);
      const suggestionSection=section(t('suggestions'),'memory-group-suggestion-section');
      suggestionSection.append(node('p',t('suggestionsHelp')));
      const suggestionList=node('div','', 'memory-group-suggestions');suggestionSection.append(suggestionList);
      const requestSuggestions=async coverageMode=>{
        if(!active(state)||state.pendingSave)return;
        const seeds=[...proposalSeeds].filter(id=>!exclusions.has(id));if(!seeds.length){setStatus(state,t('invalid'),true);return;}
        suggestButton.disabled=true;coverageButton.disabled=true;setStatus(state,t('loading'));
        const ticket=++state.readSequence;const editorRevision=state.editorRevision;
        try{const body={asset_ids:seeds.join(','),excluded_asset_ids:[...exclusions].join(',')};if(coverageMode==='by_seed')body.coverage_mode='by_seed';
          const result=await request(state,'/memory-groups/proposals',{method:'POST',body});
          if(!active(state)||ticket!==state.readSequence||editorRevision!==state.editorRevision)return;
          suggestionList.replaceChildren();
          if(!result||result.version!==1||result.library_id!==String(state.library)||result.needs_review!==true||!Array.isArray(result.seed_asset_ids)||result.seed_asset_ids.length!==seeds.length||result.seed_asset_ids.some((id,index)=>id!==seeds[index])||!Array.isArray(result.items)||result.items.length>20||(result.cover_more_available!==undefined&&typeof result.cover_more_available!=='boolean')||(coverageMode==='by_seed'&&result.coverage_mode!=='by_seed'))throw Error('Invalid suggestions response');
          if(result.status==='unavailable'){coverageButton.hidden=true;suggestionList.append(node('p',t('suggestionsError')));return;}
          if(result.status!=='ready')throw Error('Unavailable suggestions');
          coverageButton.hidden=coverageMode==='by_seed'||seeds.length<2||result.cover_more_available!==true;
          if(!result.items.length)suggestionList.append(node('p',t('noSuggestions')));
          const returnedIds=new Set();
          for(const candidate of result.items){if(!idOk(candidate?.id)||returnedIds.has(candidate.id)||seeds.includes(candidate.id)||exclusions.has(candidate.id)||!seeds.includes(candidate.matched_seed_asset_id)||candidate.kind!=='image'||!['within_recorded_window','same_recorded_day'].includes(candidate.time_reason)||!safeThumbnail(candidate))throw Error('Invalid suggestion item');returnedIds.add(candidate.id);}
          for(const id of autoSuggestedIds)selected.delete(id);
          autoSuggestedIds.clear();
          for(const candidate of result.items){if(selected.has(candidate.id))continue;
            const label=node('label','', 'memory-group-suggestion');const box=document.createElement('input');box.type='checkbox';box.name='suggested_asset_ids';box.value=candidate.id;
            if(selected.size<24){box.checked=true;selected.add(candidate.id);autoSuggestedIds.add(candidate.id);available.set(candidate.id,candidate);}else{box.checked=false;box.disabled=true;}
            box.addEventListener('change',()=>{autoSuggestedIds.delete(candidate.id);markEditorChanged(state);if(box.checked){if(selected.size>=24){box.checked=false;setStatus(state,t('invalid'),true);return;}selected.add(candidate.id);exclusions.delete(candidate.id);}else{selected.delete(candidate.id);exclusions.add(candidate.id);}renderMembers();renderGallery();renderStoryChoices();});
            const matchingSeed=available.get(candidate.matched_seed_asset_id);label.append(box,image(candidate));label.append(node('span',t('timeReason')[candidate.time_reason]));if(matchingSeed){const match=node('span',t('seed'),'memory-group-match-seed');match.append(image(matchingSeed));label.append(match);}suggestionList.append(label);
          }
          if(result.items.length)state.dirty=true;renderMembers();renderGallery();renderStoryChoices();setStatus(state,'');
        }catch(_){if(active(state)&&ticket===state.readSequence){coverageButton.hidden=true;suggestionList.replaceChildren();setStatus(state,t('suggestionsError'),true);}}
        finally{if(active(state)){suggestButton.disabled=false;coverageButton.disabled=false;}}
      };
      const suggestButton=button(t('suggestions'),()=>{void requestSuggestions('default');},'memory-group-suggest');
      const coverageButton=button(t('coverMore'),()=>{void requestSuggestions('by_seed');},'memory-group-coverage');coverageButton.hidden=true;
      if(state.capabilities.suggestions)suggestionSection.append(suggestButton,coverageButton);else suggestionSection.append(node('p',t('suggestionsDisabled')));
      editor.append(suggestionSection);
      const save=button(t('save'),()=>{},'memory-group-save');save.type='submit';editor.append(save);
      editor.append(button(t('cancel'),()=>{if(state.dirty&&!window.confirm(t('confirmLeave')))return;clearEditor(state);setStatus(state,'');},'memory-group-cancel'));
      editor.addEventListener('submit',async event=>{event.preventDefault();if(!editable())return;
        const assets=[...selected];if(assets.length<1||assets.length>24){setStatus(state,t('invalid'),true);return;}
        const actualSourceIds=[...sourceIds].filter(id=>sourceChoices.has(id)&&storyAssetIds(sourceChoices.get(id)).some(assetId=>selected.has(assetId)));
        const body={asset_ids:assets.join(','),excluded_asset_ids:[...exclusions].filter(id=>!selected.has(id)).join(','),source_story_ids:actualSourceIds.join(','),theme:theme.value,revision:group?.revision||'0',mutation_id:window.crypto?.randomUUID?.()||null};
        if(!body.mutation_id||!uuidOk(body.mutation_id)){setStatus(state,t('saveError'),true);return;}
        state.pendingSave={body,path:group?`/memory-groups/${encodeURIComponent(group.id)}`:'/memory-groups'};
        lockEditor(state,true);await sendPendingSave(state);
      });
      state.editor=editor;state.groupsBox.append(editor);
    }
    function lockEditor(state,locked) {for(const control of state.editor?.querySelectorAll('input,select,button')||[])control.disabled=locked;}
    async function sendPendingSave(state) {
      const pending=state.pendingSave;if(!pending||!active(state))return;
      state.saving=true;lockEditor(state,true);setStatus(state,t('loading'));
      const isSplit=!!pending.splitFrom;
      const method=isSplit||pending.body.revision==='0'?'POST':'PUT';
      try{
        const result=await request(state,pending.path,{method,body:pending.body});
        if(!active(state)||state.pendingSave!==pending)return;
        const matches=isSplit?result?.version===1&&result.library_id===String(state.library)&&
          result.source_id===pending.splitFrom&&uuidOk(result.created_id)&&result.created_id!==result.source_id:
          matchesSavedRequest(result,pending,state);
        if(!matches)throw Error('Invalid saved group response');
        state.pendingSave=null;state.saving=false;clearEditor(state);await loadGroups(state);
        setStatus(state,t(isSplit?'splitSaved':'saved'));
      }catch(_){if(!active(state)||state.pendingSave!==pending)return;
        state.saving=false;setStatus(state,t('failedSave'),true);state.editor?.querySelector('.memory-group-save-recovery')?.remove();const actions=node('div','', 'memory-group-save-recovery');actions.append(button(t('retrySave'),()=>sendPendingSave(state),'memory-group-save-retry'),button(t('discard'),()=>{state.pendingSave=null;clearEditor(state);setStatus(state,'');},'memory-group-save-discard'));
        state.editor?.append(actions);
      }
    }
    async function expand(state) {
      if(!active(state)||state.capabilitiesLoading||state.capabilities)return;
      state.capabilitiesLoading=true;setStatus(state,t('loading'));
      const ticket=++state.readSequence;
      try{const caps=await request(state,'/memory-groups/capabilities');if(!active(state)||ticket!==state.readSequence)return;
        if(!caps||caps.version!==1||typeof caps.enabled!=='boolean'||(caps.library_id!==undefined&&caps.library_id!==String(state.library)))throw Error('Invalid capabilities');
        state.capabilities={enabled:caps.enabled,manual:Boolean(caps.manual),
          split:caps.split===true,suggestions:Boolean(caps.suggestions)};
        if(!caps.enabled){state.groupsBox.replaceChildren(node('p',t('disabled')));return;}
        state.groupsBox.replaceChildren();if(!caps.manual)state.groupsBox.append(node('p',t('manualDisabled')));if(!caps.suggestions)state.groupsBox.append(node('p',t('suggestionsDisabled')));
        await loadGroups(state);
      }catch(_){if(active(state)&&ticket===state.readSequence){state.capabilities=null;state.groupsBox.replaceChildren(node('p',t('unavailable')),button(t('retry'),()=>expand(state),'memory-group-retry'));}}
      finally{if(active(state))state.capabilitiesLoading=false;}
    }
    function clear() {
      generation++;mounted=null;
      if(root){root.remove();root=null;}
    }
    function mount(container, asset, stories=[], manualItems=[]) {
      const incomingScope=scopeNow();
      if(mounted&&mounted.container===container&&mounted.asset.id===String(asset?.id)&&mounted.scopeKey===scopeKey(incomingScope)&&mounted.container?.isConnected!==false){
        const state=mounted;state.stories=Array.isArray(stories)?stories:[];state.manualItems=Array.isArray(manualItems)?manualItems:[];state.refreshStoryChoices?.();
        return {clear:()=>{if(mounted===state)clear();},canLeave:()=>canLeave(state)};
      }
      clear();if(!container||!asset||!idOk(String(asset.id)))return;
      const s=incomingScope;const state={generation,container,asset:{...asset,id:String(asset.id)},stories:Array.isArray(stories)?stories:[],manualItems:Array.isArray(manualItems)?manualItems:[],
        scopeKey:scopeKey(s),library:String(s?.library||''),epoch:s?.epoch,readSequence:0,editorRevision:0,capabilities:null,capabilitiesLoading:false,groups:[],groupsBox:null,status:null,editor:null,editing:null,pendingSave:null,dirty:false,storyHandoffs:new Map()};
      mounted=state;root=node('details','', 'memory-group-root');
      const summary=node('summary',t('open'),'memory-group-summary');root.append(summary);
      const body=node('div','', 'memory-group-body');body.append(node('p',t('suggestionsHelp')));
      state.status=node('p','', 'memory-group-status');state.status.setAttribute('role','status');state.status.setAttribute('aria-live','polite');body.append(state.status);
      state.groupsBox=node('div','', 'memory-group-list');body.append(state.groupsBox);root.append(body);
      root.addEventListener('toggle',()=>{if(root.open)expand(state);else state.readSequence++;});
      container.append(root);
      return {clear:()=>{if(mounted===state)clear();},canLeave:()=>canLeave(state)};
    }
    function canLeave(state) {
      if(!state?.pendingSave&&!state?.dirty)return true;
      if(state.saving)return false;
      if(!window.confirm(t('confirmLeave')))return false;clearEditor(state);return true;
    }
    return {mount,clear,showRecent,isEditing:()=>Boolean(mounted?.editor),canLeave:()=>canLeave(mounted)};
  }
};
