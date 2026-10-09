'use strict';
/* Library-private editorial workspace; saved drafts use protected APIs only. */
window.PhotoHouseStoryWorkspace = ({scope, request, mediaURL, openAsset, onError, openAssistant, savedRequest, community, titleRequest, relatedRequest}) => {
  const $ = id => document.getElementById(id);
  const themes = ['everyday','trip','growing_up','birthday','grandparents','year_in_review'];
  const labels = {
    zh: {everyday:'日常里的光',trip:'一起去远方',growing_up:'慢慢长大',birthday:'生日时光',grandparents:'与祖辈在一起',year_in_review:'这一年',
      navStories:'回忆',navMedia:'照片与视频',navAlbums:'相册',navAssistant:'助手',eyebrow:'把片段，连成回忆',homeTitle:'值得慢慢看的时光',homeText:'挑选一些画面，添上家人的话，让回忆有自己的起承转合。',
      create:'编排一个故事',assistant:'和助手聊聊',select:'选择画面',selected:'已选择',selectionHelp:'最多 24 项；满额后先取消一项，再换选其他画面。设为开头的画面也会作为故事封面。',
      title:'故事标题',titlePlaceholder:'为这段回忆起个名字',theme:'故事主题',outline:'整理章节',working:'正在整理画面与参考资料…',readerFrameGroup:'本章画面',readerPhoto:'照片',readerVideo:'视频',readerFrameLabel:(kind,position,total)=>`${kind} ${position} / ${total}`,readerFrameStatus:(kind,position,total)=>`当前画面：${kind} ${position} / ${total}`,
      draft:'故事草稿',draftHelp:'这是可编辑的章节提纲，尚未保存。参考资料不会自动变成事实；请补充自己的回忆。刷新、切换相册库或退出后草稿会清除。',
      chapters:'章节',chapterTitle:'章节标题',narration:'这一章的故事',references:'参考这章的资料',family:'家人写下的话',ai:'AI 观察 · 待核实',
      readerSources:'查看本章素材来源',sourceDisclaimer:'以下是本章引用的参考资料，不代表已核实事实。',sourceFamily:'家人提供的文字',sourceAI:'AI 观察 · 需核对',
      savedContributionRefs:'已保存的家人回忆来源',sourceContribution:'家人回忆来源',editorRefLabel:'家人回忆来源',viewRef:'查看家人回忆',hideRef:'收起家人回忆',removeSavedRef:'移除此来源',refsUnavailable:'来源链接暂时无法核实。当前使用兼容保存；服务器支持时会沿用未变更章节中仍有效的链接。',refsRefreshUnavailable:'来源链接刷新失败；仍显示上次核实的链接。请重新打开已保存故事后再核对。',
      refText:'家人提供的文字',refTranscript:'AI 转写 · ',refPending:'转写尚未就绪。',refMissing:'目前没有可用的原始文字。',refUnavailable:'来源详情暂不可用，请稍后重试。',refLoading:'正在读取已保存的来源链接…',
      bookRefsLoading:'正在核实本章已保存的家人回忆来源…',bookRefsUnavailable:'本章来源链接暂不可用；故事正文仍可阅读。',
      unknown:'拍摄时间待补充',filename:'文件名日期 · 非拍摄证明',received:'收到日期 · 非拍摄证明',capture:'记录的拍摄日期',
      read:'沉浸预览',export:'下载故事草稿',exported:'已下载草稿；这不会保存到相册库或发布到电视。',empty:'请先选择至少一个画面。',
      error:'暂时无法整理故事，请重试。',close:'返回',previous:'上一章',next:'下一章',video:'播放此视频',photo:'照片',choiceVideo:'视频',choiceFrame:'画面',
      onlyFirst:'默认选中前 24 个画面。取消一项后，可以换选这个相册里的其他画面。',selectionTotal:n=>`共 ${n} 个可选画面`,framesPrevious:'上一组画面',framesNext:'下一组画面',framesPage:(first,last,total)=>`画面 ${first}–${last} / ${total}`,clearFrames:'清空选择',startWithFrame:'设为开头',selectFirst:'选择前 24 个画面',selectionLimit:'每个故事最多 24 个画面；请先取消一项，再选择其他画面。',moveEarlier:'向前移动',moveLater:'向后移动',chooseTheme:'从一个主题开始',ready:'章节提纲已准备好，可以编辑、预览或下载。',questionTitle:'让故事更像你们',
      previewMissing:'这个画面的预览暂不可用',selectionEmpty:'这页还没有可用的照片或视频。',leave:'草稿尚未下载，确定清除草稿并离开？'},
    en: {everyday:'Everyday light',trip:'Somewhere together',growing_up:'Growing up',birthday:'Birthday moments',grandparents:'With grandparents',year_in_review:'A year together',
      navStories:'Memories',navMedia:'Photos & videos',navAlbums:'Albums',navAssistant:'Assistant',eyebrow:'MOMENTS, CONNECTED',homeTitle:'Memories worth slowing down for.',homeText:'Choose a few frames, add your family’s words, and give a memory a beginning, a middle and an ending.',
      create:'Shape a story',assistant:'Talk to the assistant',select:'Choose the frames',selected:'selected',selectionHelp:'Choose up to 24. Uncheck one to choose another when full. The opening frame also becomes the story cover.',
      title:'Story title',titlePlaceholder:'Give this memory a name',theme:'Story theme',outline:'Arrange chapters',working:'Gathering frames and references…',readerFrameGroup:'Frames in this chapter',readerPhoto:'Photo',readerVideo:'Video',readerFrameLabel:(kind,position,total)=>`${kind} ${position} of ${total}`,readerFrameStatus:(kind,position,total)=>`Current frame: ${kind} ${position} of ${total}`,
      draft:'Story draft',draftHelp:'This is an editable outline, not a saved story. References are not automatically facts. Add what you remember. Refreshing, switching libraries or signing out clears this draft.',
      chapters:'Chapters',chapterTitle:'Chapter title',narration:'The story in this chapter',references:'References for this chapter',family:'Family words',ai:'AI observation · verify',
      readerSources:'View sources for this chapter',sourceDisclaimer:'These are references cited for this chapter; they are not verified facts.',sourceFamily:'Family-provided wording',sourceAI:'AI observation · verify',
      savedContributionRefs:'Saved family-memory sources',sourceContribution:'Family memory source',editorRefLabel:'Family memory source',viewRef:'View family memory',hideRef:'Hide family memory',removeSavedRef:'Remove this source',refsUnavailable:'Source links could not be verified. Saving uses the compatible story request; a supporting server may carry forward valid links for unchanged chapters.',refsRefreshUnavailable:'The source-link refresh failed. Previously verified links remain visible; reopen the saved story to check them again.',
      refText:'Family-provided wording',refTranscript:'AI transcript · ',refPending:'The transcript is not ready yet.',refMissing:'No original wording is available.',refUnavailable:'Source details are unavailable. Try again later.',refLoading:'Loading saved source links…',
      bookRefsLoading:'Checking this chapter’s saved family-memory links…',bookRefsUnavailable:'Chapter source links are unavailable. You can still read the story.',
      unknown:'Capture date to add',filename:'Filename date · not proof of capture',received:'Received date · not proof of capture',capture:'Recorded capture date',
      read:'Immersive preview',export:'Download story draft',exported:'Draft downloaded; it was not saved to the library or published to TV.',empty:'Choose at least one frame first.',
      error:'The story could not be arranged. Please try again.',close:'Back',previous:'Previous chapter',next:'Next chapter',video:'Play this video',photo:'Photo',choiceVideo:'Video',choiceFrame:'Moment',
      onlyFirst:'The first 24 frames are selected. Uncheck one to choose another frame from this album.',selectionTotal:n=>`${n} available frames`,framesPrevious:'Previous frames',framesNext:'Next frames',framesPage:(first,last,total)=>`Frames ${first}–${last} / ${total}`,clearFrames:'Clear selection',startWithFrame:'Start here',selectFirst:'Select the first 24 frames',selectionLimit:'A story can contain up to 24 frames. Uncheck one before selecting another.',moveEarlier:'Move earlier',moveLater:'Move later',chooseTheme:'Start with a theme',ready:'Your outline is ready to edit, preview or download.',questionTitle:'Make the story yours',
      previewMissing:'This frame’s preview is unavailable',selectionEmpty:'There are no available photos or videos on this page.',leave:'This draft has not been downloaded. Clear it and leave?'}
  };
  Object.assign(labels.zh,{savedEyebrow:'家人共同留下的时光',savedHeading:'我们的故事',refresh:'刷新',moreStories:'更多故事',savedEmpty:'还没有保存的故事。选几个画面，写下你们的回忆。',savedThemeFilter:'按主题浏览已保存故事',savedThemeAll:'全部主题',savedThemeEmpty:'这个主题下还没有保存的故事。',savedThemeViewAll:'查看全部故事',savedThemeCreate:'编排一个故事',savedLoading:'正在打开故事…',savedUnavailable:'已保存故事暂不可用，请稍后重试。',saveMemory:'保存到相册库',savingMemory:'正在保存…',savedMemory:'已保存到这个相册库，可以随时回来继续。',saveFailed:'保存结果尚未确认。请重试相同保存；也可先下载保留草稿。',saveConflict:'故事或参考资料已有变化。你的文字已保留，请下载草稿或重新打开已保存版本。',reloadMemory:'重新打开已保存版本',playStory:'慢慢播放',pauseStory:'暂停播放',contribute:'补充这张照片的回忆',related:'和助手找更多片段',savedDraft:'已保存故事 · 待核实',privateHelp:'与这个相册库的家人分享，不会自动发布到电视。',savedHelp:'已保存到这个相册库。修改章节后请再次保存；家人的话和 AI 观察仍作为独立参考。',readOnly:'你可以阅读这个故事。只有作者或相册库主人可以修改。',savedMeta:'个画面',chaptersMeta:'章',retrySave:'重试相同保存',needsTitle:'请先为这段回忆起一个标题。',textTooLong:'这一章的文字超过 6000 字节，请缩短后再保存；原稿未改动。',readStory:'阅读故事',backStories:'返回故事列表',editStory:'编辑故事'});
  Object.assign(labels.en,{savedEyebrow:'MOMENTS YOUR FAMILY KEEPS',savedHeading:'Our stories',refresh:'Refresh',moreStories:'More stories',savedEmpty:'No saved stories yet. Choose a few frames and add what you remember.',savedThemeFilter:'Browse saved stories by theme',savedThemeAll:'All themes',savedThemeEmpty:'No saved stories under this theme yet.',savedThemeViewAll:'View all stories',savedThemeCreate:'Create a story',savedLoading:'Opening stories…',savedUnavailable:'Saved stories are unavailable. Please try again.',saveMemory:'Save to library',savingMemory:'Saving…',savedMemory:'Saved in this library. Come back whenever you like.',saveFailed:'The save is not confirmed. Retry the same save, or download a copy of your draft.',saveConflict:'The story or its references changed. Your words are kept; download your draft or reopen the saved version.',reloadMemory:'Reopen saved version',playStory:'Play slowly',pauseStory:'Pause',contribute:'Add a memory to this photo',related:'Find more moments with the assistant',savedDraft:'Saved story · review',privateHelp:'Shared with this library; not automatically published to TV.',savedHelp:'Saved in this library. Save again after changing chapters. Family words and AI observations remain separate references.',readOnly:'You can read this story. Only its author or a library owner can edit it.',savedMeta:'frames',chaptersMeta:'chapters',retrySave:'Retry same save',needsTitle:'Give this memory a title before saving.',textTooLong:'A chapter exceeds 6000 UTF-8 bytes. Shorten it before saving; your draft is kept.',readStory:'Read story',backStories:'Back to stories',editStory:'Edit story'});
  labels.zh.savedNewer='已保存到这个相册库。家人随后修改了故事，现已打开最新版本。';
  labels.en.savedNewer='Saved in this library. Your family changed the story afterward; the latest version is now open.';
  let shelf=[], shelfPage=1, shelfLoad=0, shelfBinding=null, shelfTheme=null, canCreate=false, pendingSave=null, playTimer=null, playing=false, bookReader=null, narrationEpoch=0, narrationState=null;
  // Session-only positions contain references, never family prose or audio.
  // Clearing protected scope clears every position; nothing goes to storage.
  const bookPositions=new Map();
  const savedStoryPositions=new Map();
  let galleryItems=[], items=[], selectionPage=0, selected=new Set(), draft=null, generation=0, busy=false, chapter=0, frame=0, dirty=false, downloaded=false, readerFromShelf=false,readerMountEpoch=0;
  // Proposal source IDs outside the per-asset evidence set and accepted
  // contribution-reference contract get a volatile review note beside this draft.
  let proposalReferenceWarnings=new Map();
  let titleView=null,titleEpoch=0,titleComposing=false;
  Object.assign(labels.zh,{titleAssist:'帮我起个标题',titleAssistHelp:'根据章节草稿与参考资料提出候选标题。选择后仍可修改，不会自动保存。',titleAssistWorking:'正在想几个标题…',titleAssistEmpty:'还没有合适的候选标题，可以补充回忆后再试。',titleAssistFailed:'标题建议暂不可用，你仍可修改标题并保存故事。',titleAssistReview:'AI 标题建议 · 请核对',titleAssistSources:'查看依据',titleAssistDraft:'章节草稿',titleAssistFrame:'画面'});
  Object.assign(labels.en,{titleAssist:'Suggest a title',titleAssistHelp:'Suggest titles from chapter drafts and references. Choose one, then edit it if needed. Nothing is saved automatically.',titleAssistWorking:'Thinking of a few titles…',titleAssistEmpty:'No suitable title yet. Add more context and try again.',titleAssistFailed:'Title suggestions are unavailable. You can still edit the title and save your story.',titleAssistReview:'AI title suggestions · review',titleAssistSources:'View references',titleAssistDraft:'Chapter draft',titleAssistFrame:'Frame'});
  function invalidateTitles(){titleEpoch++;if(titleView){titleView.busy=false;titleView.choices.replaceChildren();titleView.status.textContent='';titleView.action.disabled=frozen()||titleComposing;}}
  function titleSnapshot(){return JSON.stringify([draft?.selection_revision,draft?.theme,draft?.language,draft?.items.map(i=>i.id),draft?.chapters.map(c=>({id:c.id,narration:c.narration})),$('story-workspace-title').value]);}
  function mountTitleAssistance(root){
    invalidateTitles();titleView=null;
    if(!titleRequest||!draft||readOnly())return;
    const owner={...scope()},ticket=generation,story=draft,section=node('section',undefined,'story-title-assistance');section.hidden=true;
    const action=button(text('titleAssist'),()=>void suggestTitles()),help=node('p',text('titleAssistHelp'),'fine'),status=node('p'),choices=node('div');
    status.setAttribute('role','status');status.setAttribute('aria-live','polite');choices.className='story-title-choices';section.append(action,help,status,choices);root.append(section);
    const view={section,action,status,choices,busy:false};titleView=view;
    void titleRequest('/story-workspace/title-capabilities').then(value=>{
      if(!current(ticket,owner)||draft!==story||titleView!==view)return;
      if(value?.version!==1||typeof value.enabled!=='boolean'||value.max_suggestions!==3||value.needs_review!==true)return;
      section.hidden=!value.enabled;action.disabled=frozen()||titleComposing;
    }).catch(()=>{}); // An unavailable optional feature must not block writing.
  }
  async function suggestTitles(){
    const view=titleView;if(!view||view.section.hidden||view.busy||frozen()||titleComposing||scope().locked||!draft)return;
    const owner={...scope()},ticket=generation,story=draft,epoch=++titleEpoch,snapshot=titleSnapshot();
    const valid=()=>current(ticket,owner)&&draft===story&&titleView===view&&titleEpoch===epoch&&!frozen()&&!titleComposing&&titleSnapshot()===snapshot&&$('story-workspace').open;
    view.busy=true;view.action.disabled=true;view.choices.replaceChildren();view.status.textContent=text('titleAssistWorking');
    try{
      const result=await titleRequest('/story-workspace/title-suggestions',{method:'POST',body:{asset_ids:story.items.map(i=>i.id).join(','),theme:story.theme,language:story.language,selection_revision:story.selection_revision,chapters:JSON.stringify(story.chapters.map(c=>({id:c.id,narration:c.narration})))}});
      if(!valid())return;
      const refs=new Set([...story.items.flatMap(i=>i.evidence.filter(e=>e.text.trim()).map(e=>e.id)),...story.chapters.filter(c=>c.narration.trim()).map(c=>'draft-'+c.id)]);
      if(!result||Object.keys(result).sort().join(',')!=='needs_review,selection_revision,titles,version'||result.version!==1||result.selection_revision!==story.selection_revision||result.needs_review!==true||!Array.isArray(result.titles)||result.titles.length>3||new Set(result.titles.map(t=>t?.text)).size!==result.titles.length||result.titles.some(t=>!t||Object.keys(t).sort().join(',')!=='source_ids,text'||!validText(t.text,160)||!t.text.trim()||/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/u.test(t.text)||new TextEncoder().encode(t.text).length>640||!Array.isArray(t.source_ids)||!t.source_ids.length||new Set(t.source_ids).size!==t.source_ids.length||t.source_ids.some(id=>!refs.has(id))))throw new Error('Invalid title suggestions');
      view.status.textContent=text(result.titles.length?'titleAssistReview':'titleAssistEmpty');
      for(const candidate of result.titles){const row=node('div'),choose=button(candidate.text,()=>{
        if(!valid())return;$('story-workspace-title').value=candidate.text;story.title=candidate.text;dirty=true;downloaded=false;invalidateTitles();$('story-workspace-title').focus();
      });choose.className='quiet story-title-choice';const sources=node('details',undefined,'story-title-sources');sources.append(node('summary',text('titleAssistSources')));for(const id of candidate.source_ids){const draftChapter=story.chapters.find(c=>'draft-'+c.id===id),item=story.items.find(i=>i.evidence.some(e=>e.id===id)),evidence=item?.evidence.find(e=>e.id===id);const label=draftChapter?`${text('titleAssistDraft')} · ${story.chapters.indexOf(draftChapter)+1}`:`${text(evidence.source==='family'?'family':'ai')} · ${text('titleAssistFrame')} ${item.id}`;const entry=node('article');entry.dataset.titleSourceId=id;entry.append(node('small',label),node('p',Array.from(draftChapter?.narration||evidence.text).slice(0,180).join(''),'fine'));sources.append(entry);}row.append(choose,sources);view.choices.append(row);}
    }catch(error){if(valid())view.status.textContent=text('titleAssistFailed');}
    finally{if(titleView===view&&titleEpoch===epoch){view.busy=false;view.action.disabled=frozen()||titleComposing;}}
  }
  // Opaque contribution IDs only. This volatile sidecar never changes the exact
  // v1 story draft payload returned by the existing saved-story endpoint.
  let contributionRefs=null,refsLoadEpoch=0;
  const text = key => labels[scope().language==='en'?'en':'zh'][key] || key;
  const canDiscard = () => (!dirty&&!pendingSave) || downloaded || window.confirm(text(pendingSave?'saveFailed':'leave'));
  const readOnly = () => Boolean(draft?.saved && !draft.can_edit);
  const frozen = () => busy || Boolean(pendingSave) || readOnly();
  const node = (tag, value, cls) => {const el=document.createElement(tag);if(value!==undefined)el.textContent=value;if(cls)el.className=cls;return el;};
  const button = (label, action, cls='quiet') => {const el=node('button',label,cls);el.type='button';el.addEventListener('click',action);return el;};
  const current = (ticket, owner) => ticket===generation && scope().account===owner.account && scope().library===owner.library && !scope().locked;
  const narrationCopy = (key,lang) => ({zh:{start:'朗读本章',pause:'暂停朗读',resume:'继续朗读',stop:'停止朗读',unsupported:'此浏览器没有可用的本机中文或英文语音，文字阅读仍可继续。',recording:'请先结束录音，再朗读本章。',failed:'朗读暂时无法继续。',playing:'正在朗读本章。',complete:'本章朗读完毕。',stopped:'已停止朗读。'},en:{start:'Read this chapter aloud',pause:'Pause narration',resume:'Resume narration',stop:'Stop narration',unsupported:'No suitable on-device Chinese or English voice is available. You can keep reading the text.',recording:'Finish recording before reading this chapter aloud.',failed:'Narration could not continue.',playing:'Reading this chapter aloud.',complete:'Chapter narration complete.',stopped:'Narration stopped.'}})[lang==='en'?'en':'zh'][key];
  function stopNarration(keepProgress=false) {
    const retainProgress=keepProgress===true;
    narrationEpoch++;const active=narrationState;narrationState=retainProgress?active:null;if(active)active.active=false;
    try{if(active)active.synth.cancel();}catch{}
    if(active?.status?.isConnected)active.status.textContent='';
    if(!retainProgress&&active?.progress?.isConnected)active.progress.textContent='';
    if(active?.startButton?.isConnected)active.startButton.disabled=false;
    if(active?.pauseButton?.isConnected){active.pauseButton.disabled=true;active.pauseButton.hidden=true;active.pauseButton.textContent=narrationCopy('pause',active.lang);}
    if(active?.stopButton?.isConnected){active.stopButton.disabled=true;active.stopButton.hidden=true;}
  }
  function narrationChunks(value,max=180) {
    const chars=Array.from(value),chunks=[];
    while(chars.length){let end=Math.min(max,chars.length);if(end<chars.length){let boundary=-1;for(let i=end-1;i>=Math.floor(max*.55);i--)if(/[。！？；，、.!?;\s]/u.test(chars[i])){boundary=i+1;break;}if(boundary>0)end=boundary;}chunks.push(chars.splice(0,end).join(''));}
    return chunks;
  }
  const replySpeechCopy = (key,lang) => ({zh:{start:'朗读回复',pause:'暂停朗读',resume:'继续朗读',paused:'朗读已暂停。',stop:'停止朗读',unsupported:'此浏览器没有可用的本机中文或英文语音，文字回复仍可阅读。',tooLong:'这条回复较长，暂时无法朗读；文字回复仍可阅读。',recording:'请先结束录音，再朗读回复。',failed:'回复朗读暂时无法继续。',playing:'正在朗读回复。',complete:'回复朗读完毕。',stopped:'已停止朗读。'},en:{start:'Read reply aloud',pause:'Pause reading',resume:'Resume reading',paused:'Reading paused.',stop:'Stop reading',unsupported:'No suitable on-device Chinese or English voice is available. You can still read the reply.',tooLong:'This reply is too long to read aloud; the full text is still available.',recording:'Finish recording before reading the reply aloud.',failed:'Reply audio could not continue.',playing:'Reading the reply aloud.',complete:'Reply reading complete.',stopped:'Reading stopped.'}})[lang==='en'?'en':'zh'][key];
  function beginNarration({control,usableText,storyLanguage,authorized,lang,status,progress,startButton,pauseButton,stopButton,copy}) {
    if(!control.isConnected||!authorized())return;
    try{if(community?.isCapturing?.()){status.textContent=copy('recording',lang);return;}}catch{}
    try{community?.stopPlayback?.();}catch{}
    stopNarration();stopPlaying();const synth=window.speechSynthesis;
    if(!synth||typeof synth.getVoices!=='function'||typeof window.SpeechSynthesisUtterance!=='function'){status.textContent=copy('unsupported',lang);return;}
    const language=String(storyLanguage||'').toLowerCase();let wanted=language.startsWith('zh')?'zh':language.startsWith('en')?'en':null;
    if(!wanted&&(language==='und'||language==='mixed'||!language)){const ui=String(scope().language||'').toLowerCase();wanted=ui==='en'?'en':ui==='zh'?'zh':null;}
    const voice=synth.getVoices().find(v=>v?.localService===true&&wanted&&String(v.lang||'').toLowerCase().startsWith(wanted));
    if(!voice){status.textContent=copy('unsupported',lang);return;}
    if(!usableText.replace(/[.\s]/gu,'')){status.textContent=copy('unsupported',lang);return;}
    if(synth.paused)try{synth.resume();}catch{}
    const epoch=++narrationEpoch,chunks=narrationChunks(usableText);let index=0;
    const state={control,synth,status,progress,startButton,pauseButton,stopButton,epoch,valid:authorized,lang,currentUtterance:null,active:true};narrationState=state;startButton.disabled=true;if(pauseButton){pauseButton.disabled=false;pauseButton.hidden=false;pauseButton.textContent=copy('pause',lang);}stopButton.disabled=false;stopButton.hidden=false;status.textContent=copy('playing',lang);
    const speakNext=()=>{if(narrationState!==state||!state.active||epoch!==narrationEpoch||!state.valid())return;if(index>=chunks.length){state.active=false;startButton.disabled=false;if(pauseButton){pauseButton.disabled=true;pauseButton.hidden=true;}stopButton.disabled=true;stopButton.hidden=true;status.textContent=copy('complete',lang);return;}
      const utterance=new window.SpeechSynthesisUtterance(chunks[index]);utterance.voice=voice;utterance.lang=voice.lang;state.currentUtterance=utterance;let handled=false;
      if(progress)progress.textContent=`${lang==='en'?'Chunk':'片段'} ${index+1} / ${chunks.length}`;
      utterance.onend=()=>{if(handled||state.currentUtterance!==utterance||narrationState!==state||!state.active||epoch!==narrationEpoch||!state.valid())return;handled=true;state.currentUtterance=null;index++;speakNext();};
      utterance.onerror=()=>{if(handled||state.currentUtterance!==utterance||narrationState!==state||!state.active||epoch!==narrationEpoch||!state.valid())return;handled=true;state.currentUtterance=null;state.active=false;startButton.disabled=false;if(pauseButton){pauseButton.disabled=true;pauseButton.hidden=true;}stopButton.disabled=true;stopButton.hidden=true;status.textContent=copy('failed',lang);};
      try{synth.speak(utterance);}catch{utterance.onerror?.();}};
    state.speakNext=speakNext;speakNext();
  }
  function replySpeechFits(value) {
    return typeof value==='string'&&validText(value,6000)&&value.trim().length>0&&new TextEncoder().encode(value).length<=25600;
  }
  const draftSpeechCopy = (key,lang) => ({zh:{start:'朗读建议章节',unsupported:'此浏览器没有可用的本机中文或英文语音，建议文字仍可核对。',tooLong:'这段建议较长，暂时无法朗读；完整文字仍可核对。',recording:'请先结束录音，再朗读建议章节。',failed:'建议章节朗读暂时无法继续。',playing:'正在朗读建议章节；内容仍需核对。',complete:'建议章节朗读完毕。'},en:{start:'Read draft chapter aloud',unsupported:'No suitable on-device Chinese or English voice is available. You can still review the draft text.',tooLong:'This draft is too long to read aloud; the full text is still available for review.',recording:'Finish recording before reading the draft chapter aloud.',failed:'Draft chapter audio could not continue.',playing:'Reading the draft chapter aloud; review is still required.',complete:'Draft chapter reading complete.'}})[lang==='en'?'en':'zh'][key] || replySpeechCopy(key,lang);
  const editionSpeechCopy = (key,lang) => ({zh:{start:'朗读成稿篇章',unsupported:'此浏览器没有可用的本机中文或英文语音，仍可阅读成稿。',tooLong:'这个篇章较长，暂时无法朗读；完整成稿仍可阅读。',recording:'请先结束录音，再朗读成稿篇章。',failed:'成稿篇章朗读暂时无法继续。',playing:'正在朗读已保存的 AI 整理稿；事实仍需核对原始讲述。',complete:'成稿篇章朗读完毕。'},en:{start:'Read saved chapter aloud',unsupported:'No suitable on-device Chinese or English voice is available. The saved text is still readable.',tooLong:'This chapter is too long to read aloud; the complete saved text remains readable.',recording:'Finish recording before reading the saved chapter aloud.',failed:'Saved chapter audio could not continue.',playing:'Reading the saved AI manuscript; check the original accounts for facts.',complete:'Saved chapter reading complete.'}})[lang==='en'?'en':'zh'][key] || replySpeechCopy(key,lang);
  function mountReplySpeech(container,replyText,language,authorized=()=>true,kind='reply',uiLanguage=null) {
    if(kind!=='reply'&&kind!=='draft'&&kind!=='edition')throw new TypeError('Unknown speech content kind');
    if(uiLanguage!==null&&uiLanguage!=='zh'&&uiLanguage!=='en')throw new TypeError('Unknown speech UI language');
    const copy=kind==='draft'?draftSpeechCopy:kind==='edition'?editionSpeechCopy:replySpeechCopy;
    const lang=(uiLanguage??scope().language)==='en'?'en':'zh',wrap=node('section',undefined,'story-reply-speech-controls');wrap.setAttribute('aria-label',kind==='draft'?(lang==='en'?'AI draft chapter audio · review':'AI建议章节朗读 · 待核对'):kind==='edition'?(lang==='en'?'Saved AI manuscript audio · review':'AI 成稿篇章朗读 · 核对原话'):(lang==='en'?'Assistant reply audio':'助手回复朗读'));
    const startButton=button(copy('start',lang)),pauseButton=button(copy('pause',lang)),stopButton=button(copy('stop',lang));
    const status=node('p',undefined,'story-reply-speech-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    for(const control of [startButton,pauseButton,stopButton])control.style.minHeight='44px';
    pauseButton.disabled=true;pauseButton.hidden=true;stopButton.disabled=true;stopButton.hidden=true;
    wrap.style.display='flex';wrap.style.flexWrap='wrap';wrap.style.gap='.5rem';wrap.style.minWidth='0';for(const control of [startButton,pauseButton,stopButton]){control.style.whiteSpace='normal';control.style.minWidth='0';control.style.maxWidth='100%';}status.style.flexBasis='100%';status.style.overflowWrap='anywhere';
    wrap.append(startButton,pauseButton,stopButton,status);
    const fits=replySpeechFits(replyText);if(!fits){startButton.disabled=true;status.textContent=typeof replyText==='string'&&Array.from(replyText).length>6000||typeof replyText==='string'&&new TextEncoder().encode(replyText).length>25600?copy('tooLong',lang):copy('unsupported',lang);}
    else startButton.addEventListener('click',()=>beginNarration({control:wrap,usableText:replyText,storyLanguage:language,authorized,lang,status,progress:null,startButton,pauseButton,stopButton,copy}));
    pauseButton.addEventListener('click',()=>{
      const state=narrationState;
      if(!wrap.isConnected||!state||!state.active||state.control!==wrap||!state.valid())return;
      try{
        if(state.synth.paused){
          state.synth.resume();pauseButton.textContent=copy('pause',lang);
          status.textContent=copy('playing',lang);
        }else{
          state.synth.pause();pauseButton.textContent=copy('resume',lang);
          status.textContent=copy('paused',lang);
        }
      }catch{
        stopNarration(true);status.textContent=copy('failed',lang);
      }
    });
    stopButton.addEventListener('click',()=>{const state=narrationState;if(!wrap.isConnected||!state||!state.active||state.control!==wrap||!state.valid())return;stopNarration(true);status.textContent=copy('stopped',lang);});
    container.append(wrap);let disposed=false;
    return ()=>{if(disposed)return;disposed=true;if(narrationState?.control===wrap)stopNarration();wrap.remove();};
  }
  function mountNarration(container,title,prose,storyLanguage,authorized) {
    stopNarration();container.querySelector?.('.story-narration-controls')?.remove();const lang=scope().language==='en'?'en':'zh',wrap=node('section',undefined,'story-narration-controls');wrap.setAttribute('aria-label',lang==='en'?'Chapter narration':'章节朗读');
    const startButton=button(narrationCopy('start',lang)),pauseButton=button(narrationCopy('pause',lang)),stopButton=button(narrationCopy('stop',lang));
    wrap.style.display='flex';wrap.style.flexWrap='wrap';wrap.style.gap='.5rem';wrap.style.width='100%';wrap.style.minWidth='0';
    for(const control of [startButton,pauseButton,stopButton]){control.style.flex='1 1 8rem';control.style.minWidth='0';control.style.minHeight='44px';control.style.whiteSpace='normal';}
    const progress=node('p',undefined,'story-narration-progress');progress.setAttribute('aria-live','off');progress.style.flexBasis='100%';progress.style.margin='.1rem 0';progress.style.opacity='.75';progress.style.overflowWrap='anywhere';
    const status=node('p',undefined,'story-narration-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.style.flexBasis='100%';status.style.overflowWrap='anywhere';pauseButton.disabled=true;pauseButton.hidden=true;stopButton.disabled=true;stopButton.hidden=true;wrap.append(startButton,pauseButton,stopButton,progress,status);container.append(wrap);
    const usableText=`${Array.from(String(title||'')).slice(0,160).join('')}. ${Array.from(String(prose||'')).slice(0,6000).join('')}`.trim();
    startButton.addEventListener('click',()=>beginNarration({control:wrap,usableText,storyLanguage,authorized,lang,status,progress,startButton,pauseButton,stopButton,copy:narrationCopy}));
    pauseButton.addEventListener('click',()=>{const state=narrationState;if(!wrap.isConnected||!state||!state.active||state.startButton!==startButton||!state.valid())return;if(state.synth.paused){state.synth.resume();pauseButton.textContent=narrationCopy('pause',lang);}else{state.synth.pause();pauseButton.textContent=narrationCopy('resume',lang);}});
    stopButton.addEventListener('click',()=>{const state=narrationState;if(!wrap.isConnected||!state||!state.active||state.control!==wrap||!state.valid())return;stopNarration(true);status.textContent=narrationCopy('stopped',lang);});return wrap;
  }
  const message = key => {$('story-workspace-status').textContent=key?text(key):'';};
  const idOK = id => typeof id==='string' && /^[1-9][0-9]{0,18}$/.test(id);
  const validText = (s,max) => typeof s==='string' && Array.from(s).length<=max && !/[\u0000\uD800-\uDFFF]/u.test(s);
  Object.assign(labels.zh,{relatedDayHeading:'同一天的更多瞬间',relatedDayHelp:'按记录的拍摄日期查找，不代表属于同一个活动。由你选择要加入的画面。',relatedDayFind:'查找同一天的画面',relatedDayMore:'继续查找',relatedDayWorking:'正在查找同一天的画面…',relatedDayEmpty:'没有找到其他画面。没有拍摄日期时，不会使用文件名或上传日期推测。',relatedDayFailed:'暂时无法查找，现有选择和草稿仍保留。',relatedDayAdd:'加入故事',relatedDayAdded:'已加入',relatedDayMatch:'同一记录拍摄日 · 请核对'});
  Object.assign(labels.en,{relatedDayHeading:'More moments from the same day',relatedDayHelp:'Find by recorded capture date. Sharing a day does not establish a shared activity; choose which moments belong.',relatedDayFind:'Find moments from these days',relatedDayMore:'Keep looking',relatedDayWorking:'Finding moments from the same recorded days…',relatedDayEmpty:'No other moments found. Missing capture dates are never inferred from filenames or upload dates.',relatedDayFailed:'Could not find moments. Your selection and draft are kept.',relatedDayAdd:'Add to story',relatedDayAdded:'Added',relatedDayMatch:'Same recorded capture day · review'});
  let relatedEpoch=0,relatedView=null;
  function clearRelated(){relatedEpoch++;relatedView=null;$('story-related-items').replaceChildren();$('story-related-status').textContent='';$('story-related-more').hidden=true;}
  function relatedCurrent(view){return relatedView===view&&current(view.ticket,view.owner)&&$('story-workspace').open;}
  function relatedRecordedDay(value){
    if(typeof value!=='string'||value.length>128)return null;
    const parts=/^([0-9]{4}-[0-9]{2}-[0-9]{2})(?:[T ]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.[0-9]{1,6})?)?(?:Z|[+-]([0-9]{2}):?([0-9]{2}))?)?$/.exec(value);
    if(!parts)return null;
    const day=parts[1];
    if(day.startsWith('0000')||!Number.isFinite(Date.parse(day+'T00:00:00Z'))||new Date(day+'T00:00:00Z').toISOString().slice(0,10)!==day)return null;
    if(parts[2]!==undefined&&(Number(parts[2])>23||Number(parts[3])>59||Number(parts[4]||0)>59||Number(parts[5]||0)>23||Number(parts[6]||0)>59))return null;
    return day;
  }
  function validRelated(value,seeds,owner,before){
    if(!value||Object.keys(value).sort().join(',')!=='has_more,items,library_id,needs_review,next_before_id,recorded_days,seed_asset_ids,version'||value.version!==1||value.library_id!==owner.library||value.needs_review!==true||typeof value.has_more!=='boolean'||
      JSON.stringify(value.seed_asset_ids)!==JSON.stringify(seeds)||!Array.isArray(value.recorded_days)||value.recorded_days.length>24||
      !value.recorded_days.every(day=>typeof day==='string'&&day.length===10&&relatedRecordedDay(day)===day)||
      JSON.stringify(value.recorded_days)!==JSON.stringify([...new Set(value.recorded_days)].sort())||
      !Array.isArray(value.items)||value.items.length>20||new Set(value.items.map(item=>item?.id)).size!==value.items.length||
      !(value.has_more?idOK(value.next_before_id)&&BigInt(value.next_before_id)<2n**63n:value.next_before_id===null))return false;
    let prior=before?BigInt(before):2n**63n;
    for(const item of value.items){
      if(!item||!idOK(item.id)||seeds.includes(item.id)||BigInt(item.id)>=prior||!['image','video'].includes(item.kind)||
        item.match_reason!=='same_recorded_capture_day'||!relatedRecordedDay(item.taken_at)||
        !value.recorded_days.includes(relatedRecordedDay(item.taken_at))||item.thumbnail_url!==`/assets/${item.id}/thumbnail?library=${encodeURIComponent(owner.library)}`)return false;
      prior=BigInt(item.id);
    }
    return !value.has_more||(!before||BigInt(value.next_before_id)<BigInt(before))&&(!value.items.length||BigInt(value.next_before_id)<=prior);
  }
  function renderRelated(){
    const view=relatedView,root=$('story-related-items');root.replaceChildren();
    $('story-related-find').disabled=frozen()||!selected.size||Boolean(view?.busy);
    $('story-related-more').hidden=!view?.result?.has_more;
    $('story-related-more').disabled=frozen()||Boolean(view?.busy)||!view?.seeds.every(id=>selected.has(id));
    if(!view)return;
    $('story-related-status').textContent=text(view.busy?'relatedDayWorking':view.error?'relatedDayFailed':view.result?.items.length?'relatedDayMatch':'relatedDayEmpty');
    for(const item of view.result?.items||[]){
      const card=node('article',undefined,'story-related-card'),img=node('img');img.src=mediaURL(item.id,'thumbnail');img.alt='';img.loading='lazy';
      const label=node('p',`${item.kind==='video'?'▶ ':''}${item.id} · ${item.taken_at.slice(0,10)}`),add=button(text(selected.has(item.id)?'relatedDayAdded':'relatedDayAdd'),()=>{
        if(!relatedCurrent(view)||view.busy||frozen()||selected.has(item.id))return;
        if(selected.size>=24){message('selectionLimit');return;}
        if(!canDiscard())return;
        // Explicit inclusion changes only this volatile selection. The normal
        // preview will reload all current family/AI evidence before saving.
        items=items.filter(existing=>existing.id!==item.id);items.push(item);selected.add(item.id);selectionPage=Math.floor((items.length-1)/8);
        invalidateTitles();titleView=null;draft=null;contributionRefs=null;refsLoadEpoch++;dirty=false;downloaded=false;
        $('story-chapter-editor').replaceChildren();$('story-draft-actions').hidden=true;message('');renderSelection();
      });add.dataset.relatedId=item.id;add.disabled=frozen()||view.busy||selected.has(item.id)||selected.size>=24;
      card.append(img,label,add);root.append(card);
    }
  }
  async function findRelated(more=false){
    if(!relatedRequest||frozen()||scope().locked||!selected.size||relatedView?.busy)return;
    const owner={...scope()},ticket=generation,seeds=more?relatedView?.seeds:items.filter(item=>selected.has(item.id)).map(item=>item.id),before=more?relatedView?.result?.next_before_id:'';
    if(!seeds||more&&(!relatedView?.result?.has_more||!seeds.every(id=>selected.has(id))))return;
    const selection=JSON.stringify(items.filter(item=>selected.has(item.id)).map(item=>item.id)),epoch=++relatedEpoch;
    const view={owner,ticket,seeds,busy:true,result:more?relatedView.result:null,error:false};relatedView=view;renderRelated();
    try{
      const result=await relatedRequest({asset_ids:seeds.join(','),before_id:before});
      if(!relatedCurrent(view)||relatedEpoch!==epoch)return;
      if(selection!==JSON.stringify(items.filter(item=>selected.has(item.id)).map(item=>item.id))){clearRelated();renderRelated();return;}
      if(!validRelated(result,seeds,owner,before))throw new Error('Invalid related moment response');
      view.result=result;view.error=false;
    }catch(error){
      if(!relatedCurrent(view)||relatedEpoch!==epoch)return;
      view.error=true;if([401,403].includes(error?.status))onError(error);
    }finally{if(relatedCurrent(view)&&relatedEpoch===epoch){view.busy=false;renderRelated();}}
  }
  function dateLabel(item) {
    if(item.taken_at)return `${text('capture')} · ${String(item.taken_at).slice(0,10)}`;
    if(item.date_hint)return `${text(item.date_hint.source==='received'?'received':'filename')} · ${item.date_hint.value.slice(0,10)}`;
    return text('unknown');
  }
  function setSelectionCount() {
    $('story-selection-count').textContent=`${selected.size} / 24 · ${text('selected')} · ${text('selectionTotal')(items.length)}`;
    $('story-build').disabled=frozen() || !selected.size;
    $('story-workspace-title').disabled=frozen();$('story-workspace-theme').disabled=frozen();
    if(titleView)titleView.action.disabled=frozen()||titleComposing||titleView.busy;
    for(const el of $('story-chapter-editor').querySelectorAll('input,textarea'))el.disabled=frozen();
    $('story-save-memory').hidden=!canCreate && !draft?.can_edit;
    $('story-save-memory').disabled=busy||readOnly()||!draft;
    $('story-save-memory').textContent=text(busy?'savingMemory':pendingSave?'retrySave':'saveMemory');
    $('story-reload-memory').hidden=!draft?.id;
    for(const check of $('story-selection').querySelectorAll('input'))check.disabled=frozen()||(!check.checked&&selected.size>=24);
    for(const b of $('story-selection').querySelectorAll('button'))b.disabled=frozen()||b.dataset.edge==='true'||(b.dataset.startId&&(!selected.has(b.dataset.startId)||items.find(item=>selected.has(item.id))?.id===b.dataset.startId));
    $('story-selection-clear').disabled=frozen()||!selected.size;
    $('story-selection-first').disabled=frozen()||!items.length;
    $('story-selection-first').hidden=items.length<=24;
    $('story-selection-pages').hidden=items.length<=8;
    $('story-selection-previous').disabled=frozen()||selectionPage===0;
    $('story-selection-next').disabled=frozen()||(selectionPage+1)*8>=items.length;
    $('story-selection-page').textContent=items.length?text('framesPage')(selectionPage*8+1,Math.min((selectionPage+1)*8,items.length),items.length):'';
    renderRelated();
  }
  function replaceSelection(next) {
    if(frozen()||!canDiscard())return;
    clearRelated();selectionPage=0;selected=new Set(next);invalidateTitles();titleView=null;draft=null;contributionRefs=null;refsLoadEpoch++;dirty=false;downloaded=false;
    $('story-chapter-editor').replaceChildren();$('story-draft-actions').hidden=true;message('');renderSelection();
  }
  function renderSelection() {
    selectionPage=Math.max(0,Math.min(selectionPage,Math.ceil(items.length/8)-1));
    const pool=items,owner={...scope()},start=selectionPage*8,root=$('story-selection');
    root.replaceChildren();
    for(const [offset,item] of items.slice(start,start+8).entries()) {
      const position=start+offset;
      const card=node('div',undefined,'story-frame-choice'),label=node('label');
      const choiceCurrent=()=>items===pool&&card.parentNode===root&&scope().account===owner.account&&scope().library===owner.library&&!scope().locked;
      const check=node('input');check.type='checkbox';check.value=item.id;check.checked=selected.has(item.id);
      check.setAttribute('aria-label',`${text(item.kindKnown===false?'choiceFrame':item.kind==='video'?'choiceVideo':'photo')} ${item.id}`);
      const img=node('img');img.src=mediaURL(item.id,'thumbnail');img.alt='';img.loading='lazy';
      check.addEventListener('change',()=>{if(!choiceCurrent())return;if(frozen()||!canDiscard()){check.checked=selected.has(item.id);return;}if(check.checked&&!selected.has(item.id)&&selected.size>=24){check.checked=false;message('selectionLimit');setSelectionCount();return;}clearRelated();if(check.checked)selected.add(item.id);else selected.delete(item.id);invalidateTitles();titleView=null;draft=null;contributionRefs=null;refsLoadEpoch++;dirty=false;downloaded=false;$('story-chapter-editor').replaceChildren();$('story-draft-actions').hidden=true;message('');setSelectionCount();});
      label.append(check,img,node('span',`${item.kind==='video'?'▶ ':''}${item.id}`));
      const order=node('div',undefined,'story-frame-order');
      for(const [direction,word,symbol] of [[-1,'moveEarlier','←'],[1,'moveLater','→']]){const b=button(symbol,()=>{if(!choiceCurrent()||frozen()||position+direction<0||position+direction>=items.length)return;if(dirty&&!downloaded&&!window.confirm(text('leave')))return;[items[position],items[position+direction]]=[items[position+direction],items[position]];invalidateTitles();titleView=null;draft=null;contributionRefs=null;refsLoadEpoch++;dirty=false;$('story-chapter-editor').replaceChildren();$('story-draft-actions').hidden=true;renderSelection();});b.setAttribute('aria-label',text(word)+' '+item.id);b.dataset.edge=String(position+direction<0||position+direction>=items.length);b.disabled=frozen()||b.dataset.edge==='true';order.append(b);}
      const first=button(text('startWithFrame'),()=>{
        if(!choiceCurrent()||frozen()||!selected.has(item.id)||!canDiscard())return;
        items.splice(position,1);items.unshift(item);selectionPage=0;invalidateTitles();titleView=null;draft=null;contributionRefs=null;refsLoadEpoch++;dirty=false;downloaded=false;
        $('story-chapter-editor').replaceChildren();$('story-draft-actions').hidden=true;message('');renderSelection();
      });first.dataset.startId=item.id;first.setAttribute('aria-label',text('startWithFrame')+' '+item.id);first.className='story-frame-start';order.append(first);
      order.addEventListener('click',event=>{event.preventDefault();});card.append(label,order);$('story-selection').append(card);
    }
    setSelectionCount();
  }
  function validDraft(value, expected, owner) {
    if(value?.saved && (!uuidOK(value.id)||!/^[1-9][0-9]{0,18}$/.test(value.revision)||typeof value.can_edit!=='boolean'))return false;
    if(!value || value.version!==1 || value.library_id!==owner.library || ![true,false].includes(value.saved) || value.state!=='draft' ||
       value.generator!==(value.saved?'family_edited_outline':'evidence_outline') || value.needs_review!==true || !validText(value.title,160) ||
       !Array.isArray(value.items) || value.items.length<1 || value.items.length>24 || new Set(value.items.map(i=>i.id)).size!==value.items.length || JSON.stringify(value.items.map(i=>i.id))!==JSON.stringify(expected) ||
       !Array.isArray(value.chapters) || !value.chapters.length || value.chapters.length>6 || !themes.includes(value.theme) || !['zh','en'].includes(value.language) || !/^[0-9a-f]{64}$/.test(value.selection_revision) ||
       !Array.isArray(value.questions) || value.questions.length>3 || !value.questions.every(q=>validText(q,1000)))return false;
    for(const item of value.items) {
      if(!idOK(item.id) || !['image','video'].includes(item.kind) || !Array.isArray(item.evidence) || item.evidence.length>3)return false;
      if(item.date_hint && (!['filename','received'].includes(item.date_hint.source) || !validText(item.date_hint.value,128)))return false;
      if(item.taken_at!==null && !validText(item.taken_at,128))return false;
      for(const e of item.evidence)if(!validText(e.id,160) || !['family','ai'].includes(e.source) || !validText(e.text,1800))return false;
    }
    if(value.chapters.some(c=>!Array.isArray(c.asset_ids)||!c.asset_ids.length||c.asset_ids.length>4))return false;
    if(JSON.stringify(value.chapters.flatMap(c=>c.asset_ids))!==JSON.stringify(expected))return false;
    for(const c of value.chapters) {
      if(!validText(c.id,32)||!validText(c.title,160)||!validText(c.narration,6000)||!Array.isArray(c.evidence_ids))return false;
      const evidence=new Set(value.items.filter(i=>c.asset_ids.includes(i.id)).flatMap(i=>i.evidence.map(e=>e.id)));
      if(c.evidence_ids.some(e=>!evidence.has(e)))return false;
    }
    return true;
  }
  const contributionRefIdOK=id=>typeof id==='string'&&/^contribution-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id);
  function validContributionRefs(value,story,owner){
    if(!value||Object.keys(value).sort().join(',')!=='chapters,id,library_id,revision,version'||value.version!==1||value.id!==story.id||value.library_id!==owner.library||value.revision!==story.revision||!Array.isArray(value.chapters)||value.chapters.length!==story.chapters.length)return null;
    const groups=new Map();
    for(const [index,group] of value.chapters.entries()){
      if(story.chapters[index].id!==`chapter-${index+1}`||!group||Object.keys(group).sort().join(',')!=='contribution_ids,id'||group.id!==`chapter-${index+1}`||group.id!==story.chapters[index].id||!Array.isArray(group.contribution_ids)||group.contribution_ids.length>12||new Set(group.contribution_ids).size!==group.contribution_ids.length||!group.contribution_ids.every(uuidOK))return null;
      groups.set(group.id,group.contribution_ids.map(id=>`contribution-${id}`));
    }
    return groups;
  }
  function refsFor(story=draft){return contributionRefs?.storyId===story?.id&&contributionRefs?.revision===story?.revision?contributionRefs:null;}
  async function loadContributionRefs(story,owner,ticket){
    const epoch=++refsLoadEpoch,authorized=()=>current(ticket,owner)&&draft===story&&story?.saved===true&&story.id===draft.id&&story.revision===draft.revision;
    if(!authorized()||!savedRequest)return;
    try{
      const result=await savedRequest(`/memory-stories/${story.id}/contribution-refs?revision=${encodeURIComponent(story.revision)}`);
      if(!authorized()||epoch!==refsLoadEpoch)return;
      const groups=validContributionRefs(result,story,owner);if(!groups)throw new Error('Invalid contribution references');
      contributionRefs={storyId:story.id,revision:story.revision,groups,available:true};updateContributionRefViews(story,true);
    }catch(error){
      if(!authorized()||epoch!==refsLoadEpoch)return;
      const prior=refsFor(story);
      if(prior?.available){prior.refreshUnavailable=true;updateContributionRefViews(story,true);}
      else{contributionRefs={storyId:story.id,revision:story.revision,groups:null,available:false};updateContributionRefViews(story,true);}
      if(error?.status===401||error?.status===403)onError(error);
    }
  }
  function updateContributionRefViews(story,updateReader=false){
    const refs=refsFor(story);
    for(const card of $('story-chapter-editor').querySelectorAll('.story-contribution-references')){
      const id=card.dataset.chapterId,values=refs?.available?refs.groups.get(id)||[]:null;card.replaceChildren();
      if(values?.length){card.append(node('strong',text('savedContributionRefs')));for(const [index,ref] of values.entries()){const uuid=ref.slice('contribution-'.length),row=node('div',undefined,'story-contribution-reference'),label=node('span',`${text('editorRefLabel')} ${index+1}`),status=node('p','','story-contribution-source-status'),body=node('div',undefined,'story-contribution-source-detail');row.dataset.contributionId=uuid;status.setAttribute('role','status');body.hidden=true;const action=button(text('viewRef'),()=>void loadContributionDetail(row,story,story.chapters.find(section=>section.id===id),uuid,action,status,body,'editor'),'quiet');const remove=button(text('removeSavedRef'),()=>{const currentRefs=refsFor(story);if(frozen()||!currentRefs?.available||draft!==story||currentRefs.revision!==story.revision||!row.isConnected)return;refsLoadEpoch++;currentRefs.groups.set(id,(currentRefs.groups.get(id)||[]).filter(value=>value!==ref));dirty=true;downloaded=false;updateContributionRefViews(story);},'quiet');row.style.display='flex';row.style.flexWrap='wrap';row.style.alignItems='center';row.style.gap='.5rem';row.style.minWidth='0';label.style.overflowWrap='anywhere';for(const control of [action,remove]){control.disabled=frozen();control.style.whiteSpace='normal';control.style.maxWidth='100%';control.style.minHeight='44px';}row.append(label,action,remove,status,body);card.append(row);}}
      else if(!refs&&story.saved){const note=node('p',text('refLoading'),'story-contribution-refs-status fine');note.setAttribute('role','status');card.append(note);}
      if(refs?.refreshUnavailable||refs&&!refs.available){const note=node('p',text(refs.refreshUnavailable?'refsRefreshUnavailable':'refsUnavailable'),'story-contribution-refs-status fine');note.setAttribute('role','status');card.append(note);}
    }
    if(updateReader&&$('story-reader').open&&draft===story){
      const prose=$('story-reader-title').parentElement;prose.querySelectorAll(':scope > .story-reader-sources').forEach(source=>source.remove());appendChapterSources(prose,story,story.chapters[chapter]);
    }
  }
  async function build() {
    if(frozen() || !selected.size || selected.size>24 || scope().locked || !canDiscard())return;
    clearRelated();const owner={...scope()},ticket=++generation,expected=items.filter(i=>selected.has(i.id)).map(i=>i.id);
    busy=true;setSelectionCount();message('working');
    try {
      const result=await request({asset_ids:expected.join(','),theme:$('story-workspace-theme').value,
        language:owner.language,title:$('story-workspace-title').value});
      if(!current(ticket,owner))return;
      if(!validDraft(result,expected,owner))throw new Error('Invalid story draft');
      draft=result;proposalReferenceWarnings=new Map();contributionRefs=null;refsLoadEpoch++;dirty=false;downloaded=false;renderEditor();message('ready');
    } catch(error) {if(current(ticket,owner)){message('error');onError(error);}}
    finally {if(current(ticket,owner)){busy=false;setSelectionCount();}}
  }
  function renderEditor() {
    const root=$('story-chapter-editor');root.replaceChildren();$('story-draft-actions').hidden=!draft;
    if(!draft)return;
    document.querySelector('[data-story-word=draftHelp]').textContent=text(readOnly()?'readOnly':draft.saved?'savedHelp':'draftHelp');
    $('story-workspace-title').value=draft.title;
    mountTitleAssistance(root);
    const questions=node('section',undefined,'story-questions');questions.append(node('h3',text('questionTitle')));
    const list=node('ul');for(const q of draft.questions)list.append(node('li',q));questions.append(list);root.append(questions);
    for(const [index,c] of draft.chapters.entries()) {
      const section=node('section',undefined,'story-chapter-card');section.dataset.chapterId=c.id;
      section.append(node('span',String(index+1).padStart(2,'0'),'story-chapter-number'));
      const titleLabel=node('label',text('chapterTitle')),title=node('input');title.value=c.title;title.maxLength=160;
      title.addEventListener('input',()=>{c.title=title.value;dirty=true;downloaded=false;});titleLabel.append(title);section.append(titleLabel);
      const strip=node('div',undefined,'story-chapter-strip');
      for(const id of c.asset_ids){const img=node('img');img.src=mediaURL(id,'thumbnail');img.alt=id;img.loading='lazy';strip.append(img);}section.append(strip);
      const bodyLabel=node('label',text('narration')),body=node('textarea');body.value=c.narration;body.maxLength=6000;body.rows=5;
      body.addEventListener('input',()=>{c.narration=body.value;dirty=true;downloaded=false;invalidateTitles();});bodyLabel.append(body);section.append(bodyLabel);
      const sourceWarning=proposalReferenceWarnings.get(c.id);
      if(sourceWarning){const note=node('p',proposalWarningNote(sourceWarning),'story-proposal-reference-note');note.setAttribute('role','note');section.append(note);}
      const savedRefs=node('div',undefined,'story-contribution-references');savedRefs.dataset.chapterId=c.id;section.append(savedRefs);
      const references=node('details',undefined,'story-reference-list');references.append(node('summary',text('references')));
      for(const item of draft.items.filter(i=>c.asset_ids.includes(i.id))) {
        references.append(node('p',`${item.id} · ${dateLabel(item)}`,'fine'));
        for(const e of item.evidence){const article=node('article');article.append(node('small',text(e.source==='family'?'family':'ai')),node('p',e.text));references.append(article);}
      }
      section.append(references);root.append(section);
    }
    updateContributionRefViews(draft);
    setSelectionCount();
  }
  function read() {
    if(!draft||scope().locked)return;
    readerFromShelf=false;stopPlaying();stopNarration();chapter=0;frame=0;renderReader();readerMountEpoch++;$('story-reader').showModal();
  }
  function storyPositionKey(story) { return JSON.stringify([scope().account,scope().library,story.id,story.revision]); }
  function rememberStoryPosition(story,section,item) {
    if(!story?.saved||!story.id||!story.revision||scope().locked)return;
    const key=storyPositionKey(story);
    savedStoryPositions.delete(key);savedStoryPositions.set(key,{chapterId:section.id,frameAssetId:item.id});
    while(savedStoryPositions.size>12)savedStoryPositions.delete(savedStoryPositions.keys().next().value);
  }
  function appendChapterSources(container,story,section,sourceContext=null) {
    const byId=new Map();
    for(const assetId of section.asset_ids){
      const item=story.items.find(value=>value.id===assetId);if(!item)continue;
      for(const evidence of item.evidence)if(section.evidence_ids.includes(evidence.id)&&!byId.has(evidence.id))byId.set(evidence.id,evidence);
    }
    const memoir=sourceContext?.mode==='memoir',sources=section.evidence_ids.map(id=>byId.get(id)).filter(Boolean),refs=memoir?sourceContext.refs:refsFor(story),contributionIds=refs?.available?refs.groups.get(section.id)||[]:[],unknown=Boolean(refs&&(refs.loading||!refs.available||refs.refreshUnavailable));
    if(!sources.length&&!contributionIds.length&&!unknown)return;
    const details=node('details',undefined,'story-reader-sources');
    const summary=node('summary',text('readerSources'));summary.dataset.storyWord='readerSources';
    const disclaimer=node('p',text('sourceDisclaimer'),'story-reader-sources-note');disclaimer.dataset.storyWord='sourceDisclaimer';
    if(!memoir){const owner={...scope()},ticket=generation,readerCurrent=()=>current(ticket,owner)&&draft===story&&story.chapters[chapter]===section&&$('story-reader').open&&details.isConnected;summary.addEventListener('click',()=>{if(!details.open&&readerCurrent())stopPlaying();});details.addEventListener('toggle',()=>{if(details.open&&readerCurrent())stopPlaying();});}
    else{const memoirCurrent=()=>details.isConnected&&sourceContext?.isSectionCurrent?.(story,section);summary.addEventListener('click',()=>{if(!details.open&&memoirCurrent())stopNarration();});}
    details.append(summary,disclaimer);
    if(memoir&&refs?.loading){const note=node('p',text('bookRefsLoading'),'story-reader-sources-note');note.setAttribute('role','status');details.append(note);}
    else if(memoir&&refs&&!refs.available){const note=node('p',text('bookRefsUnavailable'),'story-reader-sources-note');note.setAttribute('role','status');details.append(note);}
    else if(!memoir&&refs&&!refs.available){const note=node('p',text('refsUnavailable'),'story-reader-sources-note');note.setAttribute('role','status');details.append(note);}
    else if(refs?.refreshUnavailable){const note=node('p',text('refsRefreshUnavailable'),'story-reader-sources-note');note.setAttribute('role','status');details.append(note);}
    else if(!refs&&story.saved&&story.id){const note=node('p',text('refLoading'),'story-reader-sources-note');note.setAttribute('role','status');details.append(note);}
    const list=node('ul');
    for(const evidence of sources){
      const row=node('li');row.dataset.evidenceId=evidence.id;
      const labelKey=evidence.source==='family'?'sourceFamily':'sourceAI',label=node('strong',text(labelKey));label.dataset.storyWord=labelKey;row.append(label);
      if(evidence.title)row.append(node('span',` · ${evidence.title}`));
      row.append(node('p',evidence.text));list.append(row);
    }
    for(const ref of contributionIds){
      const contributionId=ref.slice('contribution-'.length),row=node('li');row.dataset.contributionId=contributionId;row.style.display='flex';row.style.flexDirection='column';row.style.alignItems='flex-start';row.style.gap='.35rem';row.style.minWidth='0';
      row.append(node('strong',text('sourceContribution')));
      const status=node('p','','story-contribution-source-status');status.setAttribute('role','status');
      const body=node('div',undefined,'story-contribution-source-detail');body.hidden=true;
      const action=button(text('viewRef'),()=>void loadContributionDetail(row,story,section,contributionId,action,status,body,memoir?'memoir':'reader',sourceContext),'quiet');action.style.whiteSpace='normal';action.style.maxWidth='100%';action.style.minHeight='44px';
      row.append(action,status,body);list.append(row);
    }
    details.append(list);container.append(details);
  }
  async function loadContributionDetail(row,story,section,id,action,status,body,mode='reader',sourceContext=null){
    const owner={...scope()},ticket=generation,revision=story.revision,chapterId=section.id,renderedSection=section;
    const authorized=()=>{
      if(mode==='memoir')return Boolean(sourceContext?.isCurrent?.(row,story,renderedSection,id));
      if(!current(ticket,owner)||draft!==story||story.id!==draft.id||story.revision!==revision||!row.isConnected||row.dataset.contributionId!==id)return false;
      if(mode==='reader')return story.chapters[chapter]===renderedSection&&$('story-reader').open&&row.closest('.story-reader-sources');
      const refs=refsFor(story),card=row.closest('.story-chapter-card');return $('story-workspace').open&&card?.dataset.chapterId===chapterId&&story.chapters.includes(renderedSection)&&refs?.available===true&&refs.groups.get(chapterId)?.includes(`contribution-${id}`);
    };
    if(!authorized()||action.disabled||!contributionRefIdOK(`contribution-${id}`))return;
    if(mode==='reader')stopPlaying();else if(mode==='memoir')stopNarration();
    if(!body.hidden){body.hidden=true;action.textContent=text('viewRef');return;}
    action.disabled=true;status.textContent='';
    try{
      if(mode==='memoir'&&!await sourceContext.reauthorize())return;
      if(!authorized())return;
      const detail=await savedRequest(`/memory-community/v1/stories/${story.id}/contributions/${id}`);
      if(!authorized())return;
      if(!validStoryContributionDetail(detail,id,story.id,chapterId))throw new Error('Invalid contribution detail');
      if(detail.kind==='text'){
        if(!detail.text){status.textContent=text('refMissing');return;}
        body.replaceChildren(node('p',`${text('refText')} · ${detail.byline||''}`),node('p',detail.text));
      }else{
        const derivation=detail.derivation;
        if(!derivation||derivation.state!=='ready'){status.textContent=derivation&&derivation.state==='failed'?text('refMissing'):text('refPending');return;}
        if(!boundedContributionText(derivation.transcript,8192)){status.textContent=text('refMissing');return;}
        body.replaceChildren(node('p',`${text('refTranscript')}${detail.byline||''}`),node('p',derivation.transcript));
      }
      body.hidden=false;action.textContent=text('hideRef');
    }catch(error){if(!authorized())return;if(error?.status===401||error?.status===403)onError(error);else status.textContent=text('refUnavailable');}
    finally{if(authorized())action.disabled=false;}
  }
  function validStoryContributionDetail(value,id,storyId,chapterId){
    if(!value||value.version!==1||value.id!==id||value.story_id!==storyId||!uuidOK(value.author_id)||!['text','audio'].includes(value.kind)||value.state!=='accepted'||value.processing_consent!==true||typeof value.byline!=='string'||!boundedContributionText(value.byline,256)||(value.chapter_id!==null&&value.chapter_id!==chapterId)||!validContributionDerivation(value.derivation))return false;
    if(value.kind==='text')return boundedContributionText(value.text,8192);
    const d=value.derivation;
    return value.text===null&&(d===null||(d.state!=='ready'||boundedContributionText(d.transcript,8192)));
  }
  function boundedContributionText(value,max){return validText(value,max)&&new TextEncoder().encode(value).length<=max;}
  function validContributionDerivation(d){
    return d===null||(d&&typeof d==='object'&&Number.isInteger(d.revision)&&d.revision>0&&['waiting','running','ready','failed','cancelled'].includes(d.state)&&
      (d.transcript===null||boundedContributionText(d.transcript,8192))&&(d.polished_text===null||boundedContributionText(d.polished_text,8192))&&
      Array.isArray(d.tags)&&d.tags.length<=24&&d.tags.every(tag=>boundedContributionText(tag,256))&&(d.error_code===null||boundedContributionText(d.error_code,128))&&
      Number.isInteger(d.created_at)&&Number.isInteger(d.updated_at));
  }
  function readerFrameKind(item){return text(item?.kind==='video'?'readerVideo':'readerPhoto');}
  function updateReaderFrameLabels(){
    if(!draft)return;
    const host=$('story-reader-frames'),status=$('story-reader-frame-status'),section=draft.chapters[chapter];
    if(!host||!section)return;
    host.setAttribute('aria-label',text('readerFrameGroup'));
    const total=section.asset_ids.length;
    Array.from(host.children).forEach((control,index)=>{
      const item=draft.items.find(value=>value.id===section.asset_ids[index]);
      const kind=readerFrameKind(item);
      control.setAttribute('aria-label',text('readerFrameLabel')(kind,index+1,total));
      control.setAttribute('aria-pressed',String(index===frame));
    });
    if(status){const item=draft.items.find(value=>value.id===section.asset_ids[frame]);status.textContent=text('readerFrameStatus')(readerFrameKind(item),frame+1,total);}
  }
  function revealReaderFrame(host,control){
    if(!host||!control)return;
    const hostRect=host.getBoundingClientRect(),controlRect=control.getBoundingClientRect();
    if(controlRect.left<hostRect.left)host.scrollLeft-=hostRect.left-controlRect.left;
    else if(controlRect.right>hostRect.right)host.scrollLeft+=controlRect.right-hostRect.right;
  }
  function renderReader(revealSelected=false) {
    if(!draft)return;
    const c=draft.chapters[chapter],item=draft.items.find(i=>i.id===c.asset_ids[frame]);
    const renderedDraft=draft,renderedOwner={...scope()},renderedTicket=generation;
    const readerStillCurrent=()=>draft===renderedDraft&&draft.chapters[chapter]===c&&current(renderedTicket,renderedOwner)&&$('story-reader').open;
    if(readerFromShelf&&!dirty&&!pendingSave)rememberStoryPosition(draft,c,item);
    const frameHost=$('story-reader-frames'),priorScrollLeft=frameHost.scrollLeft;
    const stage=$('story-reader-stage');stage.replaceChildren();
    const img=node('img');img.alt=`${text(item.kind==='video'?'video':'photo')} ${item.id}`;img.src=mediaURL(item.id,'preview');
    const imageStillCurrent=()=>readerStillCurrent()&&img.isConnected&&stage.contains(img);
    img.addEventListener('error',()=>{if(!imageStillCurrent())return;img.src=mediaURL(item.id,'thumbnail');img.addEventListener('error',()=>{if(!imageStillCurrent())return;img.remove();stage.append(node('p',text('previewMissing')));},{once:true});},{once:true});stage.append(img);
    if(item.kind==='video'){
      const videoOpen=button(text('video'),()=>{if(!readerStillCurrent()||!videoOpen.isConnected||scope().locked||!confirmReaderLeave($('story-reader-community'),draft&&{...draft,type:'story'}))return;stopPlaying();stopNarration();$('story-reader').close();$('story-workspace').close();openAsset(item);},'story-video-open');
      stage.append(videoOpen);
    }
    $('story-reader-memory-title').textContent=draft.title;
    $('story-reader-close').textContent=text(readerFromShelf?'backStories':'close');
    $('story-reader-edit').hidden=!readerFromShelf||!draft.saved||!draft.can_edit;
    $('story-reader-eyebrow').textContent=`${text(draft.saved?'savedDraft':'draft')} · ${chapter+1} / ${draft.chapters.length}`;
    $('story-reader-title').textContent=c.title;$('story-reader-text').textContent=c.narration;
    const prose=$('story-reader-title').parentElement;prose.querySelectorAll(':scope > .story-reader-sources').forEach(node=>node.remove());appendChapterSources(prose,draft,c);
    mountNarration($('story-reader-title').parentElement,c.title,c.narration,draft.language,()=>Boolean(draft&&!scope().locked&&$('story-reader').open&&draft.chapters[chapter]===c&&draft.items.includes(item)));
    $('story-reader-date').textContent=dateLabel(item);
    frameHost.replaceChildren();
    c.asset_ids.forEach((id,index)=>{const media=draft.items.find(value=>value.id===id),b=button('',()=>{if(!readerStillCurrent()||!b.isConnected)return;stopPlaying();frame=index;renderReader(true);frameHost.children[index]?.focus({preventScroll:true});},'story-reader-frame');
      b.dataset.assetId=id;b.dataset.kind=media?.kind==='video'?'video':'photo';
      const thumbnail=node('img');thumbnail.src=mediaURL(id,'thumbnail');thumbnail.alt='';thumbnail.loading='lazy';thumbnail.decoding='async';thumbnail.setAttribute('aria-hidden','true');
      thumbnail.addEventListener('error',()=>{const fallback=node('span',String(index+1),'story-reader-frame-fallback');fallback.setAttribute('aria-hidden','true');thumbnail.replaceWith(fallback);},{once:true});
      const number=node('span',String(index+1),'story-reader-frame-number');number.setAttribute('aria-hidden','true');b.append(thumbnail,number);
      if(media?.kind==='video'){const videoMark=node('span','▶','story-reader-frame-video');videoMark.setAttribute('aria-hidden','true');b.append(videoMark);}
      b.setAttribute('aria-pressed',String(index===frame));frameHost.append(b);
    });
    const visual=stage.parentElement,status=node('p',undefined,'story-reader-frame-status');status.id='story-reader-frame-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');visual.querySelector('#story-reader-frame-status')?.remove();visual.append(status);
    updateReaderFrameLabels();
    if(revealSelected)revealReaderFrame(frameHost,frameHost.children[frame]);else frameHost.scrollLeft=priorScrollLeft;
    $('story-reader-chapters').replaceChildren();
    draft.chapters.forEach((section,index)=>{const b=button(`${String(index+1).padStart(2,'0')} · ${section.title}`,()=>{if(!readerStillCurrent()||!b.isConnected||draft.chapters[index]!==section)return;stopPlaying();chapter=index;frame=0;renderReader(true);$('story-reader-chapters').children[index]?.focus({preventScroll:true});});b.setAttribute('aria-current',index===chapter?'step':'false');$('story-reader-chapters').append(b);});
    $('story-reader-previous').disabled=chapter===0;$('story-reader-next').disabled=chapter===draft.chapters.length-1;
    const communityRoot=$('story-reader-community');
    communityRoot.hidden=!draft.saved;
    if(draft.saved&&community)void community.attach(communityRoot,{...structuredClone(draft),type:'story'});
  }
  function exportDraft() {
    if(!draft||scope().locked)return;
    draft.title=$('story-workspace-title').value;
    const url=URL.createObjectURL(new Blob([JSON.stringify({...draft,saved:Boolean(draft.saved&&!dirty)},null,2)+'\n'],{type:'application/json'}));
    const anchor=node('a');anchor.href=url;anchor.download='PhotoHouse-story-draft.json';anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);downloaded=true;message('exported');
  }
  function open(ids=null,theme='everyday') {
    if(scope().locked||!scope().account||!scope().library)return;
    // Keep every album choice, while the story API still receives at most 24.
    let nextItems=null;
    if(ids!==null){
      if(!Array.isArray(ids)||!ids.length||ids.length>60){message('selectionEmpty');return;}
      nextItems=ids.map(id=>typeof id==='string'?(galleryItems.find(item=>item.id===id)||{id,kind:'image',kindKnown:false}):id);
      if(nextItems.some(item=>!item||!idOK(item.id)||!['image','video'].includes(item.kind))||new Set(nextItems.map(item=>item.id)).size!==nextItems.length){message('error');return;}
    }
    if(!(nextItems||galleryItems).length){message('selectionEmpty');return;}
    if(dirty&&!downloaded&&!window.confirm(text('leave')))return;
    if($('story-reader').open&&!confirmReaderLeave($('story-reader-community'),draft&&{...draft,type:'story'}))return;
    if(bookReader?.open&&!confirmReaderLeave(bookReader.querySelector('.memory-book-companion'),bookReader.__photoHouseBookTarget))return;
    if($('story-reader').open){stopNarration();$('story-reader').close();}
    if(bookReader?.open){stopNarration();bookReader.close();}
    clearRelated();generation++;busy=false;pendingSave=null;stopPlaying();
    invalidateTitles();titleView=null;titleComposing=false;
    items=nextItems||galleryItems.slice();
    selectionPage=0;
    draft=null;proposalReferenceWarnings=new Map();contributionRefs=null;refsLoadEpoch++;dirty=false;downloaded=false;selected=new Set(items.slice(0,24).map(i=>i.id));
    $('story-workspace-theme').value=themes.includes(theme)?theme:'everyday';$('story-workspace-title').value='';
    $('story-chapter-editor').replaceChildren();$('story-draft-actions').hidden=true;message(ids&&ids.length>24?'onlyFirst':'');renderSelection();
    document.querySelector('[data-story-word=draftHelp]').textContent=text('draftHelp');$('story-workspace').showModal();
  }
  function translate() {
    stopNarration();
    void community?.translate();
    for(const el of document.querySelectorAll('[data-story-word]'))el.textContent=text(el.dataset.storyWord);
    if($('story-reader').open)$('story-reader-close').textContent=text(readerFromShelf?'backStories':'close');
    updateReaderFrameLabels();
    renderShelfFilters();
    $('story-workspace-title').placeholder=text('titlePlaceholder');
    const selectedTheme=$('story-workspace-theme').value;
    $('story-workspace-theme').replaceChildren();for(const theme of themes){const opt=node('option',text(theme));opt.value=theme;$('story-workspace-theme').append(opt);}
    if(themes.includes(selectedTheme))$('story-workspace-theme').value=selectedTheme;
    $('memory-themes').replaceChildren();for(const theme of themes){const b=button(text(theme),()=>open(null,theme),'memory-theme');b.dataset.theme=theme;$('memory-themes').append(b);}
    if(draft)renderEditor();
    setSelectionCount();
  }
  function clear({cancelCommunityJobs=true}={}) {
    clearRelated();
    invalidateTitles();titleView=null;titleComposing=false;
    stopNarration();
    bookPositions.clear();savedStoryPositions.clear();
    community?.clear({cancelJobs:cancelCommunityJobs});if(bookReader){bookReader.__photoHouseOpenBookStory=null;bookReader.close();bookReader.remove();bookReader=null;}
    $('story-reader-community').replaceChildren();$('memory-books').hidden=true;
    generation++;busy=false;pendingSave=null;readerFromShelf=false;refsLoadEpoch++;contributionRefs=null;stopPlaying();shelfLoad++;shelf=[];shelfPage=1;shelfTheme=null;shelfBinding=null;canCreate=false;$('saved-memory-list').replaceChildren();$('saved-memory-status').textContent='';$('saved-memory-more').hidden=true;renderShelfFilters();galleryItems=[];items=[];selectionPage=0;selected.clear();draft=null;proposalReferenceWarnings=new Map();dirty=false;downloaded=false;
    for(const id of ['story-workspace','story-reader'])if($(id).open)$(id).close();
    for(const id of ['story-selection','story-chapter-editor','story-reader-stage','story-reader-frames','story-reader-chapters'])$(id).replaceChildren();
    $('story-reader-frame-status')?.remove();
    $('story-reader-title').parentElement.querySelectorAll(':scope > .story-reader-sources').forEach(node=>node.remove());
    $('story-reader-title').textContent='';$('story-reader-text').textContent='';$('story-reader-date').textContent='';
    $('story-reader-memory-title').textContent='';$('story-workspace-title').value='';$('memory-home-image').removeAttribute('src');$('memory-home').hidden=true;
    $('story-draft-actions').hidden=true;message('');setSelectionCount();
  }
  const uuidOK = id => typeof id==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id);
  function renderShelfFilters() {
    const root=$('saved-memory-filters');if(!root)return;root.replaceChildren();
    const label=node('p',text('savedThemeFilter'),'saved-memory-filters-label');root.setAttribute('aria-label',text('savedThemeFilter'));root.append(label);
    const options=[null,...themes];for(const theme of options){const b=button(theme===null?text('savedThemeAll'):text(theme),()=>selectShelfTheme(theme),'saved-memory-filter');b.setAttribute('aria-pressed',String(shelfTheme===theme));b.dataset.theme=theme||'all';root.append(b);}
  }
  function selectShelfTheme(theme) {
    if(theme!==null&&!themes.includes(theme))return;
    if(theme===shelfTheme)return;
    shelfTheme=theme;shelfPage=1;shelf=[];$('saved-memory-list').replaceChildren();$('saved-memory-more').hidden=true;$('saved-memory-status').textContent=text('savedLoading');renderShelfFilters();void loadShelf();
  }
  function renderShelf() {
    const root=$('saved-memory-list');root.replaceChildren();
    if(!shelf.length&&shelfTheme){const empty=node('div',undefined,'saved-memory-empty');empty.append(node('p',text('savedThemeEmpty')));const actions=node('div',undefined,'saved-memory-empty-actions');actions.append(button(text('savedThemeViewAll'),()=>selectShelfTheme(null),'quiet'),button(text('savedThemeCreate'),()=>open(null,shelfTheme),'quiet'));empty.append(actions);root.append(empty);return;}
    for(const story of shelf){const card=node('article',undefined,'saved-memory-card');const cover=button('',()=>{void reopen(story.id);},'saved-memory-cover');cover.setAttribute('aria-label',`${text('readStory')}: ${story.title}`);const img=node('img');img.src=mediaURL(story.cover_asset_id,'thumbnail');img.alt='';img.loading='lazy';cover.append(img,node('span',text(story.theme),'saved-memory-theme'));card.append(cover);const copy=node('div',undefined,'saved-memory-copy');copy.append(node('h4',story.title),node('p',`${story.item_count} ${text('savedMeta')} · ${story.chapter_count} ${text('chaptersMeta')}`,'fine'),button(text('readStory'),()=>{void reopen(story.id);}));card.append(copy);root.append(card);}
  }
  async function loadShelf(append=false) {
    if(!savedRequest||scope().locked||!scope().account||!scope().library)return;
    const owner={...scope()},filter=shelfTheme,ticket=++shelfLoad,target=append?shelfPage+1:1;
    $('saved-memory-status').textContent=text('savedLoading');$('saved-memory-refresh').disabled=true;$('saved-memory-more').disabled=true;
    try{const result=await savedRequest(`/memory-stories?page=${target}${filter?`&theme=${encodeURIComponent(filter)}`:''}`);if(ticket!==shelfLoad||filter!==shelfTheme||scope().locked||owner.account!==scope().account||owner.library!==scope().library)return;
      if(result.library_id!==owner.library||result.page!==target||result.page_size!==8||typeof result.has_more!=='boolean'||typeof result.can_create!=='boolean'||!Array.isArray(result.items)||result.items.length>8||result.items.some(s=>!uuidOK(s.id)||!validText(s.title,160)||!idOK(s.cover_asset_id)||!themes.includes(s.theme)||(filter!==null&&s.theme!==filter)||!Number.isInteger(s.item_count)||s.item_count<1||s.item_count>24||!Number.isInteger(s.chapter_count)||s.chapter_count<1||s.chapter_count>6))throw new Error('Invalid saved stories');
      shelf=append?[...shelf,...result.items]:result.items;shelfPage=target;canCreate=result.can_create;shelfBinding=JSON.stringify([owner.account,owner.library]);renderShelf();$('saved-memory-more').hidden=!result.has_more;$('saved-memory-status').textContent=shelf.length?'':text('savedEmpty');setSelectionCount();
      if(!append&&community)void community.books($('memory-books'));
    }catch(error){if(ticket===shelfLoad&&filter===shelfTheme&&owner.account===scope().account&&owner.library===scope().library){$('saved-memory-status').textContent=text('savedUnavailable');onError(error);}}
    finally{if(ticket===shelfLoad&&filter===shelfTheme&&owner.account===scope().account&&owner.library===scope().library){$('saved-memory-refresh').disabled=false;$('saved-memory-more').disabled=false;}}
  }
  async function reopen(id) {
    if(!uuidOK(id)||scope().locked||busy||!canDiscard())return;
    if($('story-reader').open&&!confirmReaderLeave($('story-reader-community'),draft&&{...draft,type:'story'}))return;
    if(bookReader?.open&&!confirmReaderLeave(bookReader.querySelector('.memory-book-companion'),bookReader.__photoHouseBookTarget))return;
    const storyReaderWasOpen=$('story-reader').open,priorBookReader=bookReader?.open?bookReader:null;
    if(storyReaderWasOpen){stopNarration();$('story-reader').close();}
    if(priorBookReader){stopNarration();priorBookReader.close();}
    clearRelated();const priorRefs=contributionRefs?.storyId===id?contributionRefs:null;refsLoadEpoch++;stopNarration();const owner={...scope()},ticket=++generation,expectedReaderEpoch=readerMountEpoch;busy=true;setSelectionCount();$('saved-memory-status').textContent=text('savedLoading');
    try{const result=await savedRequest('/memory-stories/'+id);if(!current(ticket,owner))return;
      const expected=result.items?.map(i=>i.id);if(!Array.isArray(expected)||!validDraft(result,expected,owner)||result.saved!==true)throw new Error('Invalid saved story');
      if(readerMountEpoch!==expectedReaderEpoch||$('story-reader').open||bookReader?.open)return;
      draft=result;proposalReferenceWarnings=new Map();contributionRefs=priorRefs;if(contributionRefs?.revision!==result.revision)contributionRefs=null;items=result.items;selectionPage=0;selected=new Set(expected);pendingSave=null;dirty=false;downloaded=false;$('story-workspace-theme').value=result.theme;renderSelection();renderEditor();message('savedMemory');$('saved-memory-status').textContent='';
      chapter=0;frame=0;const position=savedStoryPositions.get(storyPositionKey(result));if(position){const chapterIndex=result.chapters.findIndex(section=>section.id===position.chapterId);if(chapterIndex>=0){const frameIndex=result.chapters[chapterIndex].asset_ids.indexOf(position.frameAssetId);if(frameIndex>=0){chapter=chapterIndex;frame=frameIndex;}}}
      if($('story-workspace').open)$('story-workspace').close();if($('story-reader').open)$('story-reader').close();readerFromShelf=true;renderReader();readerMountEpoch++;$('story-reader').showModal();void loadContributionRefs(result,owner,ticket);
    }catch(error){if(current(ticket,owner)){$('saved-memory-status').textContent=text('savedUnavailable');onError(error);}}
    finally{if(current(ticket,owner)){busy=false;setSelectionCount();}}
  }
  async function saveMemory() {
    if(!draft||busy||readOnly()||scope().locked||(!canCreate&&!draft.can_edit))return;
    const owner={...scope()},ticket=generation;
    if(!pendingSave){if(!$('story-workspace-title').value.trim()){message('needsTitle');return;}if(draft.chapters.some(c=>new TextEncoder().encode(c.narration).length>6000)){message('textTooLong');return;}if(!globalThis.crypto?.randomUUID){message('error');return;}
      const body={title:$('story-workspace-title').value,theme:draft.theme,language:draft.language,asset_ids:draft.items.map(i=>i.id).join(','),chapters:JSON.stringify(draft.chapters),selection_revision:draft.selection_revision,revision:draft.id?draft.revision:'0',mutation_id:crypto.randomUUID()};
      const knownRefs=refsFor(draft);let path='/memory-stories'+(draft.id?'/'+draft.id:'');
      if(draft.saved&&draft.id&&knownRefs?.available){body.contribution_refs=JSON.stringify(draft.chapters.map(section=>({chapter_id:section.id,contribution_ids:[...(knownRefs.groups.get(section.id)||[])].map(id=>id.slice('contribution-'.length))})));path+='?contribution_refs=1';}
      pendingSave={path,method:draft.id?'PUT':'POST',body};
    }
    const pending=pendingSave;busy=true;setSelectionCount();message('savingMemory');
    try{const result=await savedRequest(pending.path,{method:pending.method,body:pending.body});if(!current(ticket,owner))return;const expected=result.items?.map(i=>i.id);if(!Array.isArray(expected)||!validDraft(result,expected,owner)||!result.saved||(draft.id&&result.id!==draft.id))throw new Error('Invalid saved story');const newer=BigInt(result.revision)>BigInt(pending.body.revision)+1n;const savedWithRefs=Boolean(pending.body.contribution_refs);draft=result;proposalReferenceWarnings=new Map();items=result.items;selectionPage=0;selected=new Set(expected);$('story-workspace-theme').value=result.theme;pendingSave=null;dirty=false;downloaded=false;
      if(result.id){let groups=null;const exactRevision=!newer&&BigInt(result.revision)===BigInt(pending.body.revision)+1n;if(savedWithRefs&&exactRevision)groups=new Map(JSON.parse(pending.body.contribution_refs).map(group=>[group.chapter_id,group.contribution_ids.map(id=>`contribution-${id}`)]));contributionRefs={storyId:result.id,revision:result.revision,groups,available:Boolean(groups)};}
      else contributionRefs=null;
      renderSelection();renderEditor();message(newer?'savedNewer':'savedMemory');if(result.saved&&result.id)void loadContributionRefs(result,owner,ticket);void loadShelf();}
    catch(error){if(current(ticket,owner)){if(error.status&&error.status<500){pendingSave=null;message(error.status===409?'saveConflict':'error');}else message('saveFailed');onError(error);}}
    finally{if(current(ticket,owner)){busy=false;setSelectionCount();if(draft?.saved)updateContributionRefViews(draft);}}
  }
  async function acceptProposal(proposal){
    if(!draft?.saved||!draft.can_edit||busy||pendingSave||scope().locked||
       proposal.story_id!==draft.id||proposal.revision!==draft.revision||!uuidOK(proposal.job_id)||!canDiscard())return;
    const owner={...scope()},ticket=generation;
    try{
      const job=await savedRequest('/memory-community/v1/jobs/'+proposal.job_id);
      if(!current(ticket,owner)||!$('story-reader').open||job.state!=='ready'||job.base_revision!==draft.revision)return;
      const result=job.kind==='chat'?job.result?.proposal:job.result;
      if(!result||result.version!==1||result.needs_review!==true||!Array.isArray(result.chapters)||result.chapters.length!==draft.chapters.length)return;
      const candidate=structuredClone(draft),warnings=new Map(),knownRefs=refsFor(draft),proposedGroups=knownRefs?.available?new Map([...knownRefs.groups].map(([id,refs])=>[id,[...refs]])):null;let contributionReferences=false,unpersistedReferenceCount=0;
      for(const [index,section] of result.chapters.entries()){
        const before=candidate.chapters[index],refs=proposal.source_refs?.[index];
        if(section.id!==before.id||refs?.chapter_id!==section.id||JSON.stringify(refs.source_ids)!==JSON.stringify(section.source_ids)||
          proposal.chapters[index]?.narration!==section.narration||new TextEncoder().encode(section.narration).length>6000)return;
        before.narration=section.narration;
        const known=new Set(candidate.items.filter(i=>before.asset_ids.includes(i.id)).flatMap(i=>i.evidence.map(e=>e.id)));
        const unpersisted=section.source_ids.filter(id=>!known.has(id)),remaining=[];
        for(const sourceId of unpersisted){
          if(proposedGroups&&contributionRefIdOK(sourceId)){
            const values=proposedGroups.get(before.id)||[];
            if(!values.includes(sourceId)&&values.length<12){values.push(sourceId);proposedGroups.set(before.id,values);continue;}
            if(values.includes(sourceId))continue;
          }
          remaining.push(sourceId);
        }
        if(remaining.length){
          unpersistedReferenceCount+=remaining.length;
          const hasContribution=remaining.some(id=>id.startsWith('contribution-'));
          contributionReferences ||= hasContribution;
          warnings.set(before.id,{count:remaining.length,hasContribution});
        }
        before.evidence_ids=section.source_ids.filter(id=>known.has(id));
      }
      if(validText(result.title,160)&&result.title.trim())candidate.title=result.title;
      if(!validDraft(candidate,candidate.items.map(i=>i.id),owner))return;
      const prompt=warnings.size?proposalSourceWarningPrompt(warnings.size,unpersistedReferenceCount,contributionReferences):
        (owner.language==='en'?'Bring this AI draft into the editor for your review? It will be saved only when you choose Save.':'将这份 AI 建议带入编辑，供你核对？只有再次点击“保存到相册库”才会保存。');
      if(!window.confirm(prompt))return;
      if(!confirmReaderLeave($('story-reader-community'),{...draft,type:'story'})||!current(ticket,owner)||draft.id!==proposal.story_id||draft.revision!==proposal.revision||!$('story-reader').open)return;
      draft=candidate;proposalReferenceWarnings=warnings;if(proposedGroups){refsLoadEpoch++;contributionRefs={...knownRefs,groups:proposedGroups};}dirty=true;downloaded=false;readerFromShelf=false;stopPlaying();$('story-reader').close();renderEditor();
      message('ready');if(!$('story-workspace').open)$('story-workspace').showModal();$('story-chapter-editor').scrollIntoView({block:'start',behavior:'smooth'});
    }catch(error){if(current(ticket,owner))onError(error);}
  }
  function proposalSourceWarningPrompt(chapters,refs,hasContribution) {
    if(scope().language==='en')return `This suggestion cites ${refs} source reference${refs===1?'':'s'} outside the saved references for ${chapters} chapter${chapters===1?'':'s'}. The current story format cannot keep those citations. ${hasContribution?'The original family memories remain in the separate family voices list. ':''}Continue to open the text as an unsaved draft for review?`;
    return `这份建议有 ${chapters} 章引用了 ${refs} 项不属于本章已保存参考资料的来源；当前故事格式无法保留这些引用。${hasContribution?'家人提供的原始回忆仍留在单独的「家人的声音」列表中。':''}继续后只会打开待核对草稿，不会立即保存。确定继续吗？`;
  }
  function proposalWarningNote(warning) {
    if(scope().language==='en')return `This chapter cites ${warning.count} source reference${warning.count===1?'':'s'} outside its saved frame references. Saving cannot retain those citations. ${warning.hasContribution?'The original family memory remains in the separate family voices list. ':''}Please review the chapter text.`;
    return `本章有 ${warning.count} 项来源引用不属于本章画面的已保存参考，保存时无法保留这些引用。${warning.hasContribution?'家人提供的原始回忆仍在单独的「家人的声音」列表中。':''}请核对本章文字。`;
  }
  function openBook(book){
    if(scope().locked||book?.type!=='memoir'||!uuidOK(book.id)||!Array.isArray(book.stories)||!canDiscard())return;
    if($('story-reader').open&&!confirmReaderLeave($('story-reader-community'),draft&&{...draft,type:'story'}))return;
    if(bookReader?.open&&!confirmReaderLeave(bookReader.querySelector('.memory-book-companion'),bookReader.__photoHouseBookTarget))return;
    stopPlaying();stopNarration();if($('story-reader').open)$('story-reader').close();
    if(bookReader){bookReader.__photoHouseOpenBookStory=null;bookReader.close();bookReader.remove();}
    bookReader=node('dialog',undefined,'memory-book-reader');bookReader.id='memory-book-reader';
    const titleId='memory-book-reader-title';bookReader.setAttribute('aria-labelledby',titleId);
    let host=null;
    const mayLeave=()=>confirmReaderLeave(host,book);
    const header=node('header');header.append(node('span',scope().language==='en'?'FAMILY MEMOIR':'家庭回忆录','eyebrow'),button(text('close'),()=>{if(!mayLeave())return;stopNarration();bookReader.close();}));
    const heading=node('h2',book.title);heading.id=titleId;
    const introductionSources=node('div',undefined,'memory-book-introduction-sources');
    bookReader.append(header,heading,node('p',book.introduction,'memory-book-introduction'),introductionSources);
    const reader=bookReader,owner={...scope()};reader.__photoHouseBookTarget=book;let readingTicket=0,storyIndex=0,sectionIndex=0,readingStory=null,readingRefs=null,bookRefsEpoch=0,sourceHost=null,sourceSection=null,planStoryOpening=false;
    const positionKey=JSON.stringify([owner.account,owner.library,book.id,book.revision]);
    const resume=button(owner.language==='en'?'Continue where you left off':'继续上次阅读',()=>{const position=bookPositions.get(positionKey),index=position&&book.stories.findIndex(story=>story.id===position.storyId);if(Number.isInteger(index)&&index>=0)void readBookStory(index,false,position);},'memory-book-resume');
    resume.hidden=!bookPositions.has(positionKey);
    const pane=node('section',undefined,'memory-book-reading');pane.hidden=true;pane.setAttribute('aria-live','polite');
    const validReading=ticket=>reader.open&&ticket===readingTicket&&!scope().locked&&scope().account===owner.account&&scope().library===owner.library;
    reader.__photoHouseReadingContext=()=>{
      const child=book.stories[storyIndex],section=readingStory?.chapters[sectionIndex];
      if(bookReader!==reader||reader.__photoHouseBookTarget!==book||!validReading(readingTicket)||pane.hidden||!child||!section||readingStory.id!==child.id||readingStory.revision!==child.revision)return null;
      return {book_id:book.id,book_revision:String(book.revision),story_id:readingStory.id,story_revision:String(readingStory.revision),chapter_id:section.id,story_title:readingStory.title,chapter_title:section.title};
    };
    const reauthorizeBook=async ticket=>{
      const parent=await savedRequest('/memory-community/v1/books/'+book.id);if(!validReading(ticket))return false;
      if(parent.id!==book.id||parent.revision!==book.revision||!Array.isArray(parent.stories)||JSON.stringify(parent.stories.map(item=>[item.id,item.revision]))!==JSON.stringify(book.stories.map(item=>[item.id,item.revision])))throw new Error('Collection changed');
      return true;
    };
    const reauthorizeChild=async(story,ticket)=>{
      const result=await savedRequest('/memory-stories/'+story.id);if(!validReading(ticket))return false;
      const expected=result.items?.map(item=>item.id);if(result.id!==story.id||result.revision!==story.revision||!Array.isArray(expected)||!validDraft(result,expected,owner)||result.saved!==true)throw new Error('Collection story changed');return true;
    };
    let editorial=null,sourceJump=null;
    const editorialChildren=()=>book.stories.map(story=>({story_id:story.id,revision:String(story.revision)}));
    const validEditorial=value=>{
      const children=editorialChildren(),childMap=new Map(children.map(child=>[child.story_id,child.revision]));
      if(!value||Object.keys(value).sort().join(',')!=='children,id,introduction_source_refs,revision,state,transitions,version'||value.version!==1||value.id!==book.id||value.revision!==book.revision||!['empty','current','source_changed'].includes(value.state)||!Array.isArray(value.children)||!Array.isArray(value.introduction_source_refs)||!Array.isArray(value.transitions)||children.length>24||value.children.length!==children.length||value.children.some((child,index)=>!child||Object.keys(child).sort().join(',')!=='revision,story_id'||child.story_id!==children[index].story_id||child.revision!==children[index].revision))return false;
      if(value.state!=='current')return !value.transitions.length&&!value.introduction_source_refs.length;
      const validRefs=(refs,allowed)=>Array.isArray(refs)&&refs.length<=12&&new Set(refs.map(ref=>JSON.stringify([ref?.story_id,ref?.story_revision,ref?.chapter_id,ref?.contribution_id]))).size===refs.length&&refs.every(ref=>ref&&Object.keys(ref).sort().join(',')==='chapter_id,contribution_id,story_id,story_revision'&&allowed.has(ref.story_id)&&ref.story_revision===childMap.get(ref.story_id)&&/^chapter-[1-6]$/.test(ref.chapter_id)&&uuidOK(ref.contribution_id));
      if(!validRefs(value.introduction_source_refs,new Set(childMap.keys()))||value.transitions.length!==Math.max(0,children.length-1))return false;
      let total=value.introduction_source_refs.length;
      return value.transitions.every((item,index)=>{
        if(!item||Object.keys(item).sort().join(',')!=='left_story_id,right_story_id,source_refs,text'||item.left_story_id!==children[index].story_id||item.right_story_id!==children[index+1].story_id||typeof item.text!=='string'||item.text.includes('\0')||new TextEncoder().encode(item.text).length>6000||!validRefs(item.source_refs,new Set([item.left_story_id,item.right_story_id]))||Boolean(item.text.trim())!==Boolean(item.source_refs.length))return false;
        total+=item.source_refs.length;return total<=96;
      });
    };
    const appendEditorialSources=(container,refs,ticket)=>{
      if(!refs.length)return;
      const sources=node('details',undefined,'memory-book-editorial-reading-sources');
      sources.append(node('summary',owner.language==='en'?'Original memories behind this passage':'这段文字的回忆来源'));
      for(const ref of refs){const index=book.stories.findIndex(story=>story.id===ref.story_id),story=book.stories[index];if(!story)continue;
        const label=owner.language==='en'?`${story.title} · Chapter ${ref.chapter_id.slice(8)}`:`${story.title} · 第 ${ref.chapter_id.slice(8)} 章`;
        sources.append(button(label,()=>{if(!validReading(ticket))return;void readBookStory(index,false,{storyRevision:ref.story_revision,chapterId:ref.chapter_id,contributionId:ref.contribution_id});},'memory-book-editorial-source-jump'));
      }
      container.append(sources);
    };
    const loadEditorial=async ticket=>{
      editorial=null;introductionSources.replaceChildren();
      try{
        const value=await savedRequest('/memory-community/v1/books/'+book.id+'/editorial');if(!validReading(ticket))return;
        if(!validEditorial(value))throw new Error('Invalid memoir editorial');
        if(value.state==='source_changed'){introductionSources.append(node('p',owner.language==='en'?'Chapters or memory sources changed. Review the connecting passages before reading them.':'章节或回忆来源已变化，请重新整理故事之间的衔接。','memory-book-editorial-reading-status'));return;}
        if(value.state==='current'){editorial=value;appendEditorialSources(introductionSources,value.introduction_source_refs,ticket);}
      }catch(error){if(!validReading(ticket)||error?.name==='AbortError')return;if(error?.status===404||error?.status===503)return;
        introductionSources.append(node('p',owner.language==='en'?'Connecting passages are temporarily unavailable.':'故事衔接文字暂时无法载入。','memory-book-editorial-reading-status'));
        if(error?.status===401||error?.status===403)throw error;
      }
    };
    const sourceStateCurrent=(ticket,story,state)=>validReading(ticket)&&readingStory===story&&readingRefs===state&&state.bookId===book.id&&state.bookRevision===book.revision&&state.storyId===story.id&&state.storyRevision===story.revision&&state.ticket===ticket;
    const renderBookSources=()=>{
      const section=readingStory?.chapters[sectionIndex];if(!section||!sourceHost?.isConnected||sourceSection!==section)return;
      const ticket=readingTicket,story=readingStory,state=readingRefs;
      const active=sourceHost.contains(document.activeElement)?document.activeElement:null,keepOpen=sourceHost.querySelector('.story-reader-sources')?.open===true,focusId=active?.closest?.('[data-contribution-id]')?.dataset.contributionId,focusSummary=active?.matches?.('.story-reader-sources > summary')===true;
      sourceHost.replaceChildren();const context={mode:'memoir',refs:state,isSectionCurrent:(selectedStory,selectedSection)=>sourceStateCurrent(ticket,selectedStory,state)&&selectedStory===story&&readingStory.chapters[sectionIndex]===selectedSection&&sourceHost?.isConnected&&sourceSection===selectedSection,isCurrent:(row,selectedStory,selectedSection,id)=>sourceStateCurrent(ticket,selectedStory,state)&&selectedStory===story&&readingStory.chapters[sectionIndex]===selectedSection&&row.isConnected&&row.dataset.contributionId===id&&row.closest('.story-reader-sources')&&state?.available===true&&state.groups.get(selectedSection.id)?.includes(`contribution-${id}`),reauthorize:async()=>{if(!story||!state||!sourceStateCurrent(ticket,story,state))return false;if(!await reauthorizeBook(ticket)||!sourceStateCurrent(ticket,story,state))return false;return await reauthorizeChild(story,ticket)&&sourceStateCurrent(ticket,story,state);}};
      appendChapterSources(sourceHost,readingStory,section,context);
      const next=sourceHost.querySelector('.story-reader-sources');if(keepOpen&&next)next.open=true;
      if(active?.isConnected)return;
      if(focusSummary)next?.querySelector('summary')?.focus({preventScroll:true});
      else if(focusId)sourceHost.querySelector(`[data-contribution-id="${focusId}"] button`)?.focus({preventScroll:true});
    };
    const loadBookRefs=async(story,ticket)=>{
      const state=readingRefs,epoch=++bookRefsEpoch,isCurrent=()=>sourceStateCurrent(ticket,story,state)&&epoch===bookRefsEpoch;
      try{
        if(!await reauthorizeBook(ticket)||!isCurrent()||!await reauthorizeChild(story,ticket)||!isCurrent())return;
        const result=await savedRequest(`/memory-stories/${story.id}/contribution-refs?revision=${encodeURIComponent(story.revision)}`);if(!isCurrent())return;
        const groups=validContributionRefs(result,story,owner);if(!groups)throw new Error('Invalid memoir story source references');state.groups=groups;state.available=true;state.loading=false;renderBookSources();
        if(sourceJump&&sourceJump.storyRevision===story.revision&&sourceJump.chapterId===story.chapters[sectionIndex]?.id&&groups.get(sourceJump.chapterId)?.includes(`contribution-${sourceJump.contributionId}`)){
          const details=sourceHost?.querySelector('.story-reader-sources'),row=sourceHost?.querySelector(`[data-contribution-id="${sourceJump.contributionId}"]`);if(details)details.open=true;row?.querySelector('button')?.focus({preventScroll:true});sourceJump=null;
        }
      }catch(error){if(!isCurrent())return;state.groups=null;state.available=false;state.loading=false;renderBookSources();if(error?.status===401||error?.status===403)onError(error);}
    };
    const displaySection=()=>{
      if(!readingStory||!validReading(readingTicket))return;
      sourceHost=null;sourceSection=null;
      pane.replaceChildren();pane.hidden=false;const section=readingStory.chapters[sectionIndex];
      bookPositions.delete(positionKey);bookPositions.set(positionKey,{storyId:readingStory.id,storyRevision:readingStory.revision,chapterId:section.id});
      while(bookPositions.size>12)bookPositions.delete(bookPositions.keys().next().value);
      resume.hidden=true;
      if(sectionIndex===0&&storyIndex>0&&editorial){
        const transition=editorial.transitions[storyIndex-1];if(transition?.text.trim()){
          const passage=node('section',undefined,'memory-book-editorial-reading-transition');
          passage.append(node('p',owner.language==='en'?'BETWEEN STORIES':'故事之间','eyebrow'),node('p',transition.text,'memory-book-reading-prose'));
          appendEditorialSources(passage,transition.source_refs,readingTicket);pane.append(passage);
        }
      }
      const chapterHeading=node('h4',section.title);chapterHeading.tabIndex=-1;
      pane.append(node('p',`${owner.language==='en'?'Story':'故事'} ${storyIndex+1} / ${book.stories.length} · ${text('chapters')} ${sectionIndex+1} / ${readingStory.chapters.length}`,'eyebrow'),node('h3',readingStory.title),chapterHeading);
      const sectionTicket=readingTicket,frames=node('div',undefined,'memory-book-reading-frames');
      for(const id of section.asset_ids){const media=readingStory.items.find(item=>item.id===id),image=node('img');image.src=mediaURL(id,'preview');image.alt=`${text(media.kind==='video'?'video':'photo')} ${id}`;
        image.addEventListener('error',()=>{image.src=mediaURL(id,'thumbnail');image.addEventListener('error',()=>{image.replaceWith(node('p',text('previewMissing')));},{once:true});},{once:true});
        const label=owner.language==='en'?(media.kind==='video'?'Open video':'Open photo'):(media.kind==='video'?'打开视频':'打开照片');
        const open=button('',()=>{if(!validReading(sectionTicket)||!mayLeave())return;stopNarration();reader.close();openAsset(media);},'memory-book-media');open.setAttribute('aria-label',`${label} ${id}`);open.append(image);
        const item=node('figure');item.append(open,node('figcaption',dateLabel(media)));frames.append(item);}
      pane.append(frames,node('p',section.narration,'memory-book-reading-prose'));
      sourceHost=node('div',undefined,'memory-book-source-host');sourceSection=section;pane.append(sourceHost);renderBookSources();
      mountNarration(pane,section.title,section.narration,readingStory.language,()=>validReading(sectionTicket)&&readingStory?.id===book.stories[storyIndex]?.id&&readingStory?.chapters[sectionIndex]===section);
      const detailsStatus=node('p',undefined,'memory-book-story-status');detailsStatus.setAttribute('role','status');
      const details=button(owner.language==='en'?'Open this story and family memories':'打开故事与家人回忆',async()=>{
        if(!readingStory||busy||!validReading(readingTicket))return;
        const id=readingStory.id,ticket=readingTicket;details.disabled=true;
        try{if(!await reauthorizeBook(ticket)||!validReading(ticket))return;if(!mayLeave()||!validReading(ticket))return;readingTicket++;reader.close();void reopen(id);}
        catch(error){if(validReading(ticket)){detailsStatus.textContent=text('savedUnavailable');onError(error);}}
        finally{if(validReading(ticket))details.disabled=false;}
      },'memory-book-story-details');pane.append(details,detailsStatus);
      const controls=node('nav',undefined,'memory-book-reading-controls');controls.setAttribute('aria-label',owner.language==='en'?'Read across the collection':'连续阅读回忆集');
      const previous=button(text('previous'),()=>{stopNarration();if(sectionIndex>0){sectionIndex--;displaySection();}else if(storyIndex>0)void readBookStory(storyIndex-1,true);});previous.disabled=sectionIndex===0&&storyIndex===0;
      const next=button(text('next'),()=>{stopNarration();if(sectionIndex<readingStory.chapters.length-1){sectionIndex++;displaySection();}else if(storyIndex<book.stories.length-1)void readBookStory(storyIndex+1);});next.disabled=sectionIndex===readingStory.chapters.length-1&&storyIndex===book.stories.length-1;
      controls.append(previous,next,button(owner.language==='en'?'Back to contents':'返回目录',backToContents));pane.append(controls);
      // Explicit reading/navigation replaces its own controls. Move focus to
      // the newly loaded chapter instead of leaving it on a detached button.
      chapterHeading.focus({preventScroll:true});pane.style.scrollMarginTop=`${header.getBoundingClientRect().height+16}px`;pane.scrollIntoView({block:'start'});
    };
    const readBookStory=async(index,last=false,position=null)=>{
      if(index<0||index>=book.stories.length)return false;stopNarration();const ticket=++readingTicket;readingStory=null;pane.hidden=false;toc.hidden=true;resume.hidden=true;pane.replaceChildren(node('p',text('savedLoading'),'memory-book-reading-status'));
      try{
        // Recheck the parent before every child read; a stale book may no longer
        // authorize that story or keep the same order. Never use cached prose.
        if(!await reauthorizeBook(ticket))return false;
        await loadEditorial(ticket);if(!validReading(ticket))return false;
        // Editorial context can take another request. Recheck the parent at the
        // child-read boundary so an intervening revision cannot authorize stale prose.
        if(!await reauthorizeBook(ticket)||!validReading(ticket))return false;
        const result=await savedRequest('/memory-stories/'+book.stories[index].id);if(!validReading(ticket))return false;
        const expected=result.items?.map(item=>item.id);if(!Array.isArray(expected)||result.id!==book.stories[index].id||result.revision!==book.stories[index].revision||!validDraft(result,expected,owner)||result.saved!==true)throw new Error('Invalid collection story');
        readingStory=result;storyIndex=index;bookRefsEpoch++;readingRefs={bookId:book.id,bookRevision:book.revision,storyId:result.id,storyRevision:result.revision,ticket,groups:null,available:false,loading:true};const resumed=position?.storyRevision===result.revision?result.chapters.findIndex(section=>section.id===position.chapterId):-1;sourceJump=resumed>=0&&uuidOK(position?.contributionId)?position:null;sectionIndex=resumed>=0?resumed:last?result.chapters.length-1:0;displaySection();void loadBookRefs(result,ticket);return true;
      }catch(error){if(validReading(ticket)){editorial=null;introductionSources.replaceChildren();pane.replaceChildren(node('p',text('savedUnavailable'),'memory-book-reading-status'),button(owner.language==='en'?'Retry this story':'重试此故事',()=>void readBookStory(index,last,position)),button(owner.language==='en'?'Reopen this memoir':'重新打开回忆录',async()=>{if(!validReading(ticket))return;try{const fresh=await savedRequest('/memory-community/v1/books/'+book.id);if(validReading(ticket)&&mayLeave())openBook(fresh);}catch(next){if(validReading(ticket))onError(next);}},'memory-book-reopen'),button(owner.language==='en'?'Back to contents':'返回目录',backToContents));onError(error);}return false;}
    };
    const openBookStoryFromPlan=async context=>{
      if(!context||Object.keys(context).sort().join(',')!=='book_id,book_revision,story_id,story_revision'||!uuidOK(context.book_id)||!uuidOK(context.story_id)||typeof context.book_revision!=='string'||typeof context.story_revision!=='string')return false;
      if(!reader.open||bookReader!==reader||reader.__photoHouseBookTarget!==book||scope().locked||scope().account!==owner.account||scope().library!==owner.library||context.book_id!==book.id||context.book_revision!==String(book.revision))return false;
      const index=book.stories.findIndex(story=>story.id===context.story_id&&String(story.revision)===context.story_revision);
      if(index<0||planStoryOpening)return false;
      planStoryOpening=true;
      try{return await readBookStory(index)===true;}
      finally{if(reader===bookReader)planStoryOpening=false;}
    };
    reader.__photoHouseOpenBookStory=openBookStoryFromPlan;
    function backToContents(){stopNarration();readingTicket++;bookRefsEpoch++;readingStory=null;readingRefs=null;sourceHost=null;sourceSection=null;sourceJump=null;pane.hidden=true;toc.hidden=false;resume.hidden=!bookPositions.has(positionKey);toc.querySelector('button')?.focus();void loadEditorial(readingTicket).catch(onError);}
    const toc=node('ol',undefined,'memory-book-toc');
    for(const [index,story] of book.stories.entries()){const item=node('li');const open=button(story.title,()=>void readBookStory(index));
      if(idOK(story.cover_asset_id)){const img=node('img');img.src=mediaURL(story.cover_asset_id,'thumbnail');img.alt='';img.loading='lazy';open.prepend(img);}item.append(open);toc.append(item);}
    host=node('section',undefined,'memory-book-companion');reader.addEventListener('close',()=>{reader.__photoHouseOpenBookStory=null;reader.__photoHouseReadingContext=null;stopNarration();readingTicket++;bookRefsEpoch++;readingStory=null;readingRefs=null;sourceHost=null;sourceSection=null;pane.replaceChildren();community?.detach(host);});reader.addEventListener('cancel',event=>{if(!mayLeave()){event.preventDefault();return;}stopNarration();});reader.append(resume,toc,pane,host);document.body.append(reader);readerMountEpoch++;reader.showModal();
    if(community)void community.attach(host,book);
    void loadEditorial(readingTicket).catch(onError);
  }
  function confirmReaderLeave(container,expectedTarget=null){
    if(typeof community?.confirmLeave!=='function')return true;
    if(!container||container.hidden||!container.querySelector('.memory-community'))return true;
    const before=scope(),owner=JSON.stringify([before?.account,before?.library]),reader=container?.closest?.('dialog'),expected=expectedTarget&&JSON.stringify([expectedTarget.type,expectedTarget.id,expectedTarget.revision]);
    if(!community.confirmLeave(container,expectedTarget))return false;
    const after=scope();
    return owner===JSON.stringify([after?.account,after?.library])&&!after?.locked&&(!reader||reader.open)&&(!expectedTarget||JSON.stringify([expectedTarget.type,expectedTarget.id,expectedTarget.revision])===expected);
  }
  async function openBookStory(context){
    if(!context||Object.keys(context).sort().join(',')!=='book_id,book_revision,story_id,story_revision')return false;
    const reader=bookReader,handler=reader?.__photoHouseOpenBookStory;
    if(!reader?.open||typeof handler!=='function')return false;
    try{return await handler(context)===true;}catch{return false;}
  }
  function stopPlaying(){if(playTimer)clearInterval(playTimer);playTimer=null;playing=false;$('story-reader').dataset.playing='false';$('story-reader-play').textContent=text('playStory');$('story-reader-play').setAttribute('aria-pressed','false');}
  function togglePlaying(){if(playing){stopPlaying();return;}if(!draft||scope().locked)return;stopNarration();playing=true;$('story-reader').dataset.playing='true';$('story-reader-play').textContent=text('pauseStory');$('story-reader-play').setAttribute('aria-pressed','true');playTimer=setInterval(()=>{if(scope().locked||document.hidden||!$('story-reader').open){stopPlaying();return;}const c=draft.chapters[chapter];if(frame<c.asset_ids.length-1)frame++;else if(chapter<draft.chapters.length-1){chapter++;frame=0;}else{stopPlaying();return;}renderReader();},7000);}
  $('saved-memory-refresh').addEventListener('click',()=>{void loadShelf();});$('saved-memory-more').addEventListener('click',()=>{void loadShelf(true);});
  $('story-save-memory').addEventListener('click',()=>{void saveMemory();});$('story-reload-memory').addEventListener('click',()=>{if(draft?.id)void reopen(draft.id);});
  $('story-reader-play').addEventListener('click',togglePlaying);$('story-reader').addEventListener('close',()=>{stopPlaying();stopNarration();community?.detach($('story-reader-community'));if(readerFromShelf&&!$('story-workspace').open){contributionRefs=null;refsLoadEpoch++;}});$('story-reader').addEventListener('cancel',event=>{if(!confirmReaderLeave($('story-reader-community'),draft&&{...draft,type:'story'})){event.preventDefault();return;}stopNarration();});document.addEventListener('visibilitychange',()=>{if(document.hidden){stopPlaying();stopNarration();}});window.addEventListener('pagehide',stopNarration);window.addEventListener('photohouse-memory-audio-start',stopNarration);document.getElementById('view-play')?.addEventListener('click',stopNarration);
  $('story-reader-contribute').addEventListener('click',()=>{if(!draft||scope().locked||!confirmReaderLeave($('story-reader-community'),{...draft,type:'story'}))return;const item=draft.items.find(i=>i.id===draft.chapters[chapter].asset_ids[frame]);stopPlaying();stopNarration();$('story-reader').close();$('story-workspace').close();openAsset(item);});
  $('story-reader-related').addEventListener('click',()=>{if(!draft||scope().locked||!confirmReaderLeave($('story-reader-community'),{...draft,type:'story'}))return;stopPlaying();stopNarration();$('story-reader').close();$('story-workspace').close();openAssistant(draft.title);});
  $('story-workspace').addEventListener('close',clearRelated);
  $('story-related').hidden=!relatedRequest;
  $('story-related-find').addEventListener('click',()=>{void findRelated();});
  $('story-related-more').addEventListener('click',()=>{void findRelated(true);});
  $('story-selection-previous').addEventListener('click',()=>{if(!frozen()&&selectionPage>0){selectionPage--;renderSelection();}});
  $('story-selection-next').addEventListener('click',()=>{if(!frozen()&&(selectionPage+1)*8<items.length){selectionPage++;renderSelection();}});
  $('story-selection-clear').addEventListener('click',()=>replaceSelection([]));
  $('story-selection-first').addEventListener('click',()=>replaceSelection(items.slice(0,24).map(item=>item.id)));
  $('story-workspace-form').addEventListener('submit',event=>{event.preventDefault();void build();});
  $('story-workspace-title').addEventListener('input',()=>{invalidateTitles();if(draft){draft.title=$('story-workspace-title').value;dirty=true;downloaded=false;}});
  $('story-workspace-form').addEventListener('compositionstart',()=>{titleComposing=true;invalidateTitles();});
  $('story-workspace-form').addEventListener('compositionend',()=>{titleComposing=false;invalidateTitles();});
  $('story-workspace-theme').addEventListener('change',()=>{if(frozen()){if(draft)$('story-workspace-theme').value=draft.theme;return;}if(!canDiscard()){$('story-workspace-theme').value=draft.theme;return;}invalidateTitles();titleView=null;draft=null;contributionRefs=null;refsLoadEpoch++;dirty=false;downloaded=false;$('story-chapter-editor').replaceChildren();$('story-draft-actions').hidden=true;message('');});
  $('story-preview').addEventListener('click',read);$('story-export').addEventListener('click',exportDraft);
  $('story-reader-previous').addEventListener('click',()=>{if(chapter>0){stopPlaying();stopNarration();chapter--;frame=0;renderReader(true);}});
  $('story-reader-next').addEventListener('click',()=>{if(draft&&chapter<draft.chapters.length-1){stopPlaying();stopNarration();chapter++;frame=0;renderReader(true);}});
  $('story-reader-close').addEventListener('click',()=>{if(!confirmReaderLeave($('story-reader-community'),draft&&{...draft,type:'story'}))return;stopNarration();$('story-reader').close();});
  $('story-reader-edit').addEventListener('click',()=>{if(!readerFromShelf||!draft?.saved||!draft.can_edit||scope().locked||!$('story-reader').open||!confirmReaderLeave($('story-reader-community'),{...draft,type:'story'}))return;readerFromShelf=false;stopPlaying();stopNarration();$('story-reader').close();renderEditor();if(!$('story-workspace').open)$('story-workspace').showModal();});
  $('story-workspace-close').addEventListener('click',()=>$('story-workspace').close());
  $('story-workspace').addEventListener('close',()=>{invalidateTitles();if(!pendingSave&&!readerFromShelf){contributionRefs=null;refsLoadEpoch++;}});
  $('story-reader').addEventListener('keydown',event=>{
    if(!draft||event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey||!['ArrowRight','ArrowLeft'].includes(event.key))return;
    if(event.target?.closest?.('#story-reader-community,input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="tablist"],[role="tab"]'))return;
    const fromFrames=Boolean(event.target?.closest?.('#story-reader-frames')),fromChapters=Boolean(event.target?.closest?.('#story-reader-chapters'));
    const beforeChapter=chapter,beforeFrame=frame;
    if(event.key==='ArrowRight'){if(frame<draft.chapters[chapter].asset_ids.length-1)frame++;else if(chapter<draft.chapters.length-1){chapter++;frame=0;}}
    else if(frame>0)frame--;else if(chapter>0){chapter--;frame=draft.chapters[chapter].asset_ids.length-1;}
    if(chapter===beforeChapter&&frame===beforeFrame)return;
    stopPlaying();stopNarration();renderReader(true);event.preventDefault();
    if(fromFrames)$('story-reader-frames').children[frame]?.focus({preventScroll:true});
    else if(fromChapters)$('story-reader-chapters').children[chapter]?.focus({preventScroll:true});
  });
  $('memory-create').addEventListener('click',()=>open());$('memory-assistant').addEventListener('click',openAssistant);
  translate();
  return {clear,open,translate,reopen,openBook,openBookStory,acceptProposal,canLeave:canDiscard,mountReplySpeech,
    setItems(value){if(shelfBinding!==JSON.stringify([scope().account,scope().library]))void loadShelf();galleryItems=value.filter(i=>idOK(i.id)&&['image','video'].includes(i.kind)).slice(0,24);const first=galleryItems[0];$('memory-home').hidden=!first;for(const b of $('memory-themes').querySelectorAll('button'))b.disabled=!first;if(first){const image=$('memory-home-image');image.onerror=()=>{image.onerror=null;image.src=mediaURL(first.id,'thumbnail');};image.src=mediaURL(first.id,first.kind==='video'?'thumbnail':'preview');image.alt='';}},
    fromResults(value){open(value);}};
};
