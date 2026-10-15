'use strict';
/* Explicit, source-linked memory group editor. All state stays in this mount. */
window.PhotoHouseMemoryGroups = {
  create({scope, api}) {
    let generation = 0;
    let root = null;
    let mounted = null;
    const scopeNow = () => typeof scope === 'function' ? scope() : scope;
    const scopeKey = value => JSON.stringify([value?.account, value?.library, value?.epoch]);
    const strings = {
      zh: {
        title:'家庭回忆组', open:'家庭回忆组', loading:'正在载入…', unavailable:'家庭回忆组暂时不可用。',
        disabled:'此相册库尚未开启家庭回忆组。', failed:'暂时无法载入，请重试。', retry:'重试载入',
        create:'新建回忆组', edit:'编辑', save:'明确保存回忆组', cancel:'取消编辑',
        theme:'主题', themes:{trip:'旅行',growing_up:'成长',birthday:'生日',grandparents:'祖辈',year_in_review:'年度回顾',everyday:'日常'},
        addMedia:'从当前相册选择画面', included:'组内画面', remove:'移出此组',
        suggestions:'查找相似画面', suggestionsHelp:'建议会参考记录的拍摄时间和图片相似度。结果可以逐项修改；不会自动保存。',
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
        create:'Create a memory group', edit:'Edit', save:'Save this memory group', cancel:'Cancel editing',
        theme:'Theme', themes:{trip:'Trip',growing_up:'Growing up',birthday:'Birthday',grandparents:'Grandparents',year_in_review:'Year in review',everyday:'Everyday'},
        addMedia:'Choose from this gallery', included:'Group photos', remove:'Remove from group',
        suggestions:'Find similar photos', suggestionsHelp:'Suggestions use recorded capture time and image similarity. Review and edit each result; nothing is saved automatically.',
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
      const caption=node('figcaption',item?.taken_at?`${t('capture')}: ${formatCaptureTime(item.taken_at)}`:`${item?.kind==='video'?'Video':'Photo'}`);
      figure.append(caption);return figure;
    };
    function formatCaptureTime(value) {
      if(typeof value!=='string')return '';
      const match=/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,6})?)?(Z|[+-]\d{2}:?\d{2})?)?$/.exec(value);
      if(!match)return value;
      const [,year,month,day,hour,minute,,zone]=match;const y=Number(year),m=Number(month),d=Number(day);
      const check=new Date(0);check.setUTCFullYear(y,m-1,d);check.setUTCHours(0,0,0,0);if(check.getUTCFullYear()!==y||check.getUTCMonth()!==m-1||check.getUTCDate()!==d)return value;
      if(hour!==undefined&&(Number(hour)>23||Number(minute)>59))return value;
      if(zone&&zone!=='Z'){const digits=zone.slice(1).replace(':','');if(Number(digits.slice(0,2))>23||Number(digits.slice(2))>59)return value;}
      let timezone='';if(zone==='Z')timezone=' UTC';else if(zone){const digits=zone.slice(1).replace(':','');timezone=` UTC${zone[0]}${digits.slice(0,2)}:${digits.slice(2)}`;}
      const date=scopeNow()?.language==='en'?`${year}-${month}-${day}`:`${year}年${Number(month)}月${Number(day)}日`;
      return hour===undefined?date:`${date} · ${hour}:${minute}${timezone}`;
    }
    function setStatus(state, text, bad=false) {
      if(!active(state)||!state.status)return;state.status.textContent=text;state.status.dataset.state=bad?'error':'ready';
    }
    function request(state,path,options={}) { return api(path,{...options,epoch:state.epoch}); }
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
        if(group.can_edit&&state.capabilities.manual){const edit=button(t('edit'),()=>openEditor(state,group),'memory-group-edit');card.append(edit);}
        state.groupsBox.append(card);
      }
      if(state.capabilities.manual)state.groupsBox.append(button(t('create'),()=>openEditor(state,null),'memory-group-create'));
    }
    function storyAssetIds(story) {
      const values=[story?.asset_id,story?.asset?.id,...(Array.isArray(story?.asset_ids)?story.asset_ids:[])].filter(idOk);
      return [...new Set(values)];
    }
    function openEditor(state, group) {
      if(!active(state)||state.pendingSave)return;
      if(state.editor&&state.dirty){if(state.saving||!window.confirm(t('confirmLeave')))return;clearEditor(state);}
      clearEditor(state);state.editing=group||null;
      const baseIds=group?(group.asset_ids||[]).filter(idOk):[state.asset.id];
      const selected=new Set(baseIds);const exclusions=new Set((group?.excluded_asset_ids||[]).filter(idOk));
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
      let excludedList=null;
      const members=section(t('included'),'memory-group-members');const memberRows=node('div','', 'memory-group-items');members.append(memberRows);editor.append(members);
      const manualPicker=section(t('addMedia'),'memory-group-gallery');
      const available=new Map();for(const item of [state.asset,...state.manualItems])if(idOk(item?.id)&&!available.has(item.id))available.set(item.id,item);
      const renderMembers=()=>{
        memberRows.replaceChildren();for(const id of selected){const item=available.get(id)||group?.items?.find(v=>v.id===id)||{id};const wrap=node('div','', 'memory-group-member');wrap.append(image(item));
          if(id!==state.asset.id||group){const remove=button(t('remove'),()=>{markEditorChanged(state);selected.delete(id);exclusions.add(id);for(const box of suggestionList.querySelectorAll('input'))if(box.value===id)box.checked=false;renderMembers();renderGallery();renderStoryChoices();},'memory-group-remove');wrap.append(remove);}memberRows.append(wrap);}
        count.textContent=t('count')(selected.size,24);
        if(excludedList)excludedList.textContent=exclusions.size?`${t('excluded')}: ${exclusions.size}`:'';
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
      renderMembers();renderGallery();editor.append(manualPicker);renderStoryChoices();
      excludedList=node('p',exclusions.size?`${t('excluded')}: ${exclusions.size}`:'', 'memory-group-exclusions');editor.append(excludedList);
      const suggestionSection=section(t('suggestions'),'memory-group-suggestion-section');
      suggestionSection.append(node('p',t('suggestionsHelp')));
      const suggestionList=node('div','', 'memory-group-suggestions');suggestionSection.append(suggestionList);
      const suggestButton=button(t('suggestions'),async()=>{
        if(!active(state)||state.pendingSave)return;
        const seeds=[...proposalSeeds].filter(id=>!exclusions.has(id));if(!seeds.length){setStatus(state,t('invalid'),true);return;}
        suggestButton.disabled=true;setStatus(state,t('loading'));
        const ticket=++state.readSequence;const editorRevision=state.editorRevision;
        try{const result=await request(state,'/memory-groups/proposals',{method:'POST',body:{asset_ids:seeds.join(','),excluded_asset_ids:[...exclusions].join(',')}});
          if(!active(state)||ticket!==state.readSequence||editorRevision!==state.editorRevision)return;
          suggestionList.replaceChildren();
          if(!result||result.version!==1||result.library_id!==String(state.library)||result.needs_review!==true||!Array.isArray(result.seed_asset_ids)||result.seed_asset_ids.length!==seeds.length||result.seed_asset_ids.some((id,index)=>id!==seeds[index])||!Array.isArray(result.items)||result.items.length>20)throw Error('Invalid suggestions response');
          if(result.status==='unavailable'){suggestionList.append(node('p',t('suggestionsError')));return;}
          if(result.status!=='ready')throw Error('Unavailable suggestions');
          if(!result.items.length)suggestionList.append(node('p',t('noSuggestions')));
          const returnedIds=new Set();
          for(const candidate of result.items){if(!idOk(candidate?.id)||returnedIds.has(candidate.id)||seeds.includes(candidate.id)||exclusions.has(candidate.id)||!seeds.includes(candidate.matched_seed_asset_id)||candidate.kind!=='image'||!['within_recorded_window','same_recorded_day'].includes(candidate.time_reason)||!safeThumbnail(candidate))throw Error('Invalid suggestion item');returnedIds.add(candidate.id);if(selected.has(candidate.id))continue;
            const label=node('label','', 'memory-group-suggestion');const box=document.createElement('input');box.type='checkbox';box.name='suggested_asset_ids';box.value=candidate.id;
            if(selected.size<24){box.checked=true;selected.add(candidate.id);available.set(candidate.id,candidate);}else{box.checked=false;box.disabled=true;}
            box.addEventListener('change',()=>{markEditorChanged(state);if(box.checked){if(selected.size>=24){box.checked=false;setStatus(state,t('invalid'),true);return;}selected.add(candidate.id);exclusions.delete(candidate.id);}else{selected.delete(candidate.id);exclusions.add(candidate.id);}renderMembers();renderGallery();renderStoryChoices();});
            const matchingSeed=available.get(candidate.matched_seed_asset_id);label.append(box,image(candidate));label.append(node('span',t('timeReason')[candidate.time_reason]));if(matchingSeed){const match=node('span',t('seed'),'memory-group-match-seed');match.append(image(matchingSeed));label.append(match);}suggestionList.append(label);
          }
          if(result.items.length)state.dirty=true;renderMembers();renderGallery();renderStoryChoices();setStatus(state,'');
        }catch(_){if(active(state)&&ticket===state.readSequence){suggestionList.replaceChildren();setStatus(state,t('suggestionsError'),true);}}
        finally{if(active(state))suggestButton.disabled=false;}
      },'memory-group-suggest');
      if(state.capabilities.suggestions)suggestionSection.append(suggestButton);else suggestionSection.append(node('p',t('suggestionsDisabled')));
      editor.append(suggestionSection);
      const save=button(t('save'),()=>{},'memory-group-save');save.type='submit';editor.append(save);
      editor.append(button(t('cancel'),()=>{if(state.dirty&&!window.confirm(t('confirmLeave')))return;clearEditor(state);setStatus(state,'');},'memory-group-cancel'));
      editor.addEventListener('submit',async event=>{event.preventDefault();if(!active(state)||state.pendingSave)return;
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
      try{const result=await request(state,pending.path,{method:pending.body.revision==='0'?'POST':'PUT',body:pending.body});
        if(!active(state)||state.pendingSave!==pending)return;
        if(!matchesSavedRequest(result,pending,state))throw Error('Invalid saved group response');
        state.pendingSave=null;state.saving=false;setStatus(state,t('saved'));clearEditor(state);await loadGroups(state);
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
        state.capabilities={enabled:caps.enabled,manual:Boolean(caps.manual),suggestions:Boolean(caps.suggestions)};
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
        scopeKey:scopeKey(s),library:String(s?.library||''),epoch:s?.epoch,readSequence:0,editorRevision:0,capabilities:null,capabilitiesLoading:false,groups:[],groupsBox:null,status:null,editor:null,editing:null,pendingSave:null,dirty:false};
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
    return {mount,clear,isEditing:()=>Boolean(mounted?.editor),canLeave:()=>canLeave(mounted)};
  }
};
