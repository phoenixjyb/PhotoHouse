'use strict';
/* Protected, ephemeral family contributions and review-only memory assistance. */
let memoryCommunityInstanceSequence=0;
window.PhotoHouseMemoryCommunity = ({scope, request, onError=()=>{}, onProposal=()=>{},
  onOpenStory=()=>{}, onOpenBookStory=null, capture=null, transcribe=null, voiceCapabilities=()=>({transcribe:false}), mediaURL=()=>'',mountReplySpeech=null}) => {
  const API = '/memory-community/v1';
  const MAX_AUDIO = 2 * 1024 * 1024;
  const uuid = () => globalThis.crypto?.randomUUID?.() || null;
  const instanceId=uuid()||String(++memoryCommunityInstanceSequence);
  let attachmentSequence=0,attachmentId=String(++attachmentSequence);
  const tabId=key=>`memory-community-${instanceId}-${attachmentId}-tab-${key}`;
  let panelId=`memory-community-${instanceId}-${attachmentId}-panel`;
  const uuidOK = value => typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
  const idOK = value => typeof value==='string'&&/^[1-9][0-9]{0,18}$/.test(value);
  const scopeNow = () => typeof scope === 'function' ? scope() : scope;
  const targetKey = value => JSON.stringify([value?.type, value?.id, value?.revision]);
  const targetScopeFingerprint=(owner,value)=>JSON.stringify(value?.type==='memoir'?[owner,targetKey(value),Array.isArray(value.stories)?value.stories.map(story=>[story.id,String(story.revision)]):null]:[owner,targetKey(value)]);
  const accountKey = value => JSON.stringify([value?.account, value?.library]);
  const membershipRevision = value => Number.isSafeInteger(value?.membership_revision)&&value.membership_revision>0?value.membership_revision:null;
  const conversationHintScope = () => {
    const s=scopeNow(),revision=membershipRevision(s);
    if(!s||s.locked||!uuidOK(s.account)||typeof s.library!=='string'||!s.library.trim()||s.library.length>128||/[\x00-\x1f\x7f]/.test(s.library)||['.','..'].includes(s.library)||revision===null||!target)return null;
    return JSON.stringify([s.account,s.library,revision,targetScopeFingerprint(accountKey(s),target)]);
  };
  const pruneConversationHints = (account,library,revision) => {
    for(const key of conversationHints.keys()){
      let parts;try{parts=JSON.parse(key);}catch(_){conversationHints.delete(key);continue;}
      if(parts[0]!==account||parts[1]!==library||parts[2]!==revision)conversationHints.delete(key);
    }
  };
  const rememberConversation = id => {
    if(!uuidOK(id))return;
    const key=conversationHintScope();if(!key)return;
    conversationHints.delete(key);conversationHints.set(key,id);
    while(conversationHints.size>conversationHintLimit)conversationHints.delete(conversationHints.keys().next().value);
  };
  const forgetConversation = id => {for(const [key,value] of conversationHints)if(value===id)conversationHints.delete(key);};
  const forgetConversationScope = (account,library,revision) => {for(const key of conversationHints.keys()){let parts;try{parts=JSON.parse(key);}catch(_){conversationHints.delete(key);continue;}if(parts[0]===account&&parts[1]===library&&parts[2]===revision)conversationHints.delete(key);}};
  const labels = {
    zh: {
      voice:'家人的声音', chat:'一起聊回忆', ideas:'整理建议', books:'家庭回忆录',
      unavailable:'家庭回忆暂时不可用，请稍后重试。', disabled:'此相册库暂未开启家庭回忆。',
      memoirScope:'当前范围：整本回忆录',draftChapter:'草稿章节',readingChapterPrompt:'聊聊正在阅读的篇章',readingChapterHelp:'先打开篇章，再把问题填入空白消息草稿。核对后发送；讨论仍属于整本回忆录。',readingChapterUnavailable:'请先打开这本回忆录中的一个篇章，再试一次。',target:'回忆对象', voiceHelp:'家人留下的原话会保留在这个相册库，直到主人删除。删除原话不会更改已经采纳到故事中的文字。',
      voiceRetention:'录音和原话仅供本相册库成员查看；只有主人可以删除。', text:'写下这段回忆', byline:'署名（可留空）', chapter:'关联章节', whole:'整个故事',
      consent:'我同意在本地使用这段文字或录音生成整理建议。', record:'录音（最长 30 秒）', stop:'结束并保留录音', cancelRecord:'丢弃录音', file:'选择 WAV 录音', recordingReady:'录音已准备好。点击“明确保存这段回忆”后才会上传；AI 整理可不勾选。',
      save:'明确保存这段回忆', retry:'用同一份内容重试', saved:'已保存，等待故事主人查看。', moreBooks:'更多回忆集',
      moreContributions:'查看更多家人回忆', moreTurns:'更早的消息', refreshTurns:'刷新已浏览的对话', moreStories:'加载更多已保存的故事',
      pending:'等待主人查看', accepted:'已接受', declined:'未采用', noVoices:'还没有家人留下的回忆。',
      confirmLeave:'离开后，未发送的消息和草稿会被丢弃；录音会停止，正在处理的请求可能会取消。仍要离开吗？',
      status:'状态',
      mine:'我的回忆', familyMember:'家人', viewDerivation:'查看转写与整理', hideDerivation:'收起整理详情', noDerivation:'暂时没有转写或整理结果。', transcript:'转写', polished:'整理后的文字', tags:'主题标签', consented:'同意本地整理', noConsent:'未同意本地整理',
      accept:'接受', decline:'暂不采用', review:'主人审核', audio:'播放原始录音', deleteOriginal:'删除原始回忆', confirmDelete:'删除这段原话或录音？已采纳到故事中的文字不会更改。',
      listeningHelp:'依次聆听当前列表的前 16 段已认可录音。', listenFamily:'听家人的回忆', stopListening:'停止聆听', nextRecording:'下一段', listeningPosition:(index,total,byline)=>`${index}/${total} · ${byline}`, listeningStopped:'已停止聆听。', listeningComplete:'已经听完这些家人的回忆。', listeningFailed:'这段录音无法播放，聆听已停止。', playbackBlocked:'请点播放器上的播放键开始聆听。', composeMemory:'补充我的回忆',
      conversationHelp:'对话会在 30 天后清除。每条消息都由你明确发送；助手不会替你修改故事。', conversationContextHelp:'回复会结合当前材料、当前问题和最多 7 轮之前的对话。更早的消息仍可查看，但不会自动带入这次回复；重要背景可以补充在新问题中。', returnToChapter:'回到正在阅读的章节',
      chatRecovering:'正在核对这段对话中尚未完成的回复…',chatRecoveryFailed:'暂时无法确认这条待处理回复。对话记录已保留；请重试检查后再发送或取消。',chatRecoveryRetry:'重试检查待处理回复',chatPendingSendBlocked:'这段对话已有一条待处理回复。请刷新状态或取消该任务后再发送。',
      chatFollowups:'继续聊聊',chatFollowupHelp:'选择一个问题填入空白消息草稿。检查后，再决定是否发送。',chatFollowupReview:'问题已填入消息草稿。请检查内容，再由你选择发送。',chatFollowupDraftBlocked:'请先发送或清空现有消息草稿，再使用这个问题。',chatFollowupDictationBlocked:'请先结束录音，并加入或丢弃待处理的识别结果。',chatFollowupSendBlocked:'请先完成或重试当前发送。',chatFollowupJobBlocked:'请等待或取消当前回复任务。',chatFollowupImeBlocked:'请先完成正在输入的文字。',chatFollowupSourcesNote:'这些来源说明回复引用了哪些材料，并不能证明其中内容属实。',chatClarificationCue:'AI 想再了解一点',chatClarificationHelp:'可以用自己的话补充；如有建议问题，它只会填入草稿。',chatLatest:'查看最新消息',chatWriteNext:'写下一条',sourceViewTranscript:'查看转写原话',sourceHideTranscript:'收起转写原话',sourceTranscriptAI:'AI 转写 · ',sourceTranscriptPending:'这段录音的转写尚未准备好。',sourceTranscriptMissing:'这段录音目前没有可用转写。',sourceTranscriptRetry:'转写暂时无法载入，请重试。',
      startChat:'新建讨论', closeChat:'结束并删除这段对话', confirmClose:'删除这段对话和其中的问答？', message:'想和家人一起回想什么？', send:'发送这条消息', retrySend:'重试同一条消息',
      conversationSelect:'选择一段对话',conversationNumber:n=>`第 ${n} 段对话`,conversationCreated:'刚创建',conversationRestored:'已回到上次选择的对话。',conversationListHelp:'显示最近 8 段对话。',threadBusy:'当前对话仍有任务处理中，完成或取消后再切换或新建。',threadDraftBlocked:'请先结束录音、核对并加入或丢弃识别结果，或处理待重试消息，再切换对话。',threadLoading:'正在载入这段对话…',
      chatStarters:'可以从这里聊起', chatStarterHelp:'选择后可继续修改，确认后再发送。', starterDetails:'补全回忆', starterDetailsText:'这段回忆有哪些细节还需要问问家人？请先说说已有资料，再提出一个值得追问的问题。', starterSequence:'梳理时间线', starterSequenceText:'请梳理这段回忆的已知顺序，标出日期或先后关系还不确定的地方。', starterChapters:'连接章节', starterChaptersText:'请参考家人的原话，建议如何连接已有章节。保留不同人的说法，不要补造经历。',
      memoirStarterDetails:'找出共同线索', memoirStarterDetailsText:'这些已保存的故事有哪些共同线索？请根据现有资料概括，并提出一个值得问问家人的问题。', memoirStarterSequence:'梳理故事顺序', memoirStarterSequenceText:'请梳理这些故事中已知的先后顺序，并明确标出不确定的日期或顺序。', memoirStarterChapters:'连接不同故事', memoirStarterChaptersText:'请建议如何连接这些已保存的故事，保留不同家人的说法，不要补造经历或事实。',
      chatRecord:'录一段口述（不会保留录音）', chatContinueRecord:'继续口述下一条（不会保留录音）',chatRetryDictation:'重新录一段口述', chatRecordStop:'结束录音并识别文字',chatCaptureWaiting:'正在等待麦克风…',chatTranscribing:'正在识别口述…', chatTranscript:'识别结果（可编辑）', addTranscript:'加入消息', discardTranscript:'丢弃识别结果', transcriptHelp:'口述录音仅用于本次转写，不会保存到对话中。识别文字不会自动发送。', transcriptNeedsReview:'请先把这段识别结果加入消息或丢弃，再录下一段；这样不会覆盖你正在核对的文字。', voiceNextTurnHelp:'助手已回复。可以继续录下一条口述，核对识别文字、加入消息，再由你明确发送。',voiceAsrFailed:'这段口述没有识别成功。录音不会保留；可重新录一段，已输入的消息草稿仍在。',voicePermissionFailed:'无法使用麦克风。请检查浏览器麦克风权限，再重新录音；消息草稿仍在。',voiceCaptureFailed:'录音没有开始或完成。请检查麦克风后重新录音；消息草稿仍在。',
      keepChatTurn:'把这句话留作回忆',chatTurnKeepBlocked:'请先完成或丢弃现有回忆草稿、录音或待保存内容，并等待当前对话任务结束，再试一次。',
      refresh:'检查回复', cancel:'取消当前任务', noTurns:'你们的对话会显示在这里。',you:'你',assistant:'助手',pendingReply:'等待回复',pendingQueued:'消息已排队，等待回复。',pendingRunning:'助手正在准备回复。',chatQueued:'消息已排队，等待回复。',chatRunning:'正在准备回复。',chatReady:'助手已回复。',chatFailed:'回复暂未完成。',chatCancelled:'回复已取消。',
      ideasHelp:'整理建议会作为待核实内容展示。请阅读家人的原话和资料，再决定如何修改故事。',
      memoirForm:'回忆录整理方式',memoirFormPrompt:'选一种整理方式',memoirFormExisting:'按现有文字整理',memoirFormChronicle:'忠实纪事',memoirFormEssay:'家庭散文',memoirFormLong:'长篇回忆录',
      editorialContextLabel:'结合已保存的开篇与衔接',editorialContextHelp:'先检查已保存的内容，再由你确认发送或生成建议。',editorialContextChecking:'正在检查已保存的开篇、章节过渡和整本内容范围…',editorialContextReady:'已核对当前开篇与章节过渡。本轮将使用整本已保存内容。',editorialContextUnavailable:'当前无法核对已保存的开篇与章节过渡，请稍后重试。',editorialContextChanged:'已保存的开篇、章节过渡或故事版本已变化。请刷新后再试。',editorialContextSmaller:'内容超过本次处理范围，请缩小回忆册范围或明确选择仅使用故事。',editorialContextContinueBasic:'继续使用现有回忆上下文',editorialContextBasicConfirmed:'本轮将使用现有回忆上下文，不加入已保存的开篇与章节过渡。',editorialContextChoose:'请先重新检查已保存内容，或明确选择继续使用现有回忆上下文。',
      ideaVoice:'口述整理要求',ideaVoiceHelp:'停止后核对转写，再加入上方要求。录音不保存，转写记录保留30天；加入后再明确生成建议。',ideaVoiceRecord:'录一段说明',ideaVoiceStop:'结束录音并识别',ideaVoiceWaiting:'正在等待麦克风…',ideaVoiceTranscribing:'正在识别说明…',ideaVoiceTranscript:'识别结果（可编辑）',ideaVoiceInsert:'加入整理说明',ideaVoiceDiscard:'丢弃识别结果',ideaVoiceInserted:'已加入上方说明。检查后再明确生成建议。',ideaVoiceConfirmLeave:'离开整理建议会停止录音并丢弃尚未加入的识别结果。整理说明会保留在此阅读器中。仍要离开吗？',ideaVoiceOverflow:'说明过长；两部分已保留，请缩短后再加入。',ideaVoiceInvalid:'部分字符无法使用，请检查文字。两份草稿仍保留。',ideaVoiceCaptureFailed:'录音没有开始或完成。说明草稿仍保留。',ideaVoiceAsrFailed:'识别未完成。说明草稿仍保留；可重新录音。',ideaVoicePermissionFailed:'无法使用麦克风。请检查浏览器权限后重试。',ideaVoiceReviewRequired:'请先加入或丢弃待处理的识别结果，再生成建议。',ideaVoiceTooLong:'整理说明过长。请缩短后重试；当前内容仍保留。',
      instruction:'你希望整理什么？（可留空）',generate:'生成待核实建议', retryJob:'重试同一份建议请求',
      queued:'已排队', running:'正在整理', ready:'已收到回复', failed:'整理暂未完成', cancelled:'已取消', stale:'故事或资料已更新，请重新打开故事再试。',
      proposal:'整理建议 · 待核实', proposalReview:'AI建议 · 待核对', savedProposalReview:'已保存的 AI 整理稿 · 待核对', savedChapter:'已保存章节', savedMemoirDirectory:'已保存整理稿章节目录', savedMemoirCurrent:n=>`当前查看的已保存章节：${n}`, compareChapter:'查看章节对照', currentChapter:'当前阅读的章节', unchangedChapter:'与当前阅读的章节文字相同', memoirDraftDirectory:'回忆录草稿章节目录', memoirDraftCurrent:n=>`当前待核对草稿章节：${n}`, questions:'还可以问问家人', refs:'参考来源', adopt:'将建议带入编辑',
      chapterNumber:'章节', sourceCount:'条参考资料', sourceFamily:'家人提供的回忆', sourceTranscript:'家人口述的转写', sourceEditorial:'已保存的故事正文', sourceBookOpening:'回忆录开场 · 编辑文字', sourceAI:'AI 观察 · 需核实', sourceMetadata:'资料中的记录', sourceOther:'参考资料', sourceNotLoaded:'可在原始回忆或资料中核对',
      answer:'助手回复', clarification:'需要补充一些信息', pollManual:'自动检查已暂停，请手动查看回复。', expires:'这段对话将于',expiresSuffix:'到期并清除。',
      error:'刚才的操作没有完成，请检查后重试。', tooLarge:'这一轮范围太大。请分批整理，每轮最多 24 个章节和 96 个来源。', conflict:'这个故事已有更新。请重新打开最新版本后继续；输入内容仍保留。',
      bookTitle:'回忆集名称', introduction:'开场的话（可留空）', chooseStories:'按顺序选择已保存的故事（1–24 个）',
      createBook:'保存回忆集', updateBook:'保存修改', retryBook:'重试同一次保存', noBooks:'还没有回忆集。把几段已经保存的故事编排在一起，留作一本温暖的回忆。', composeBook:'编排一本回忆集', continueBook:'继续保存回忆集', continueEditBook:'继续编辑回忆集', collapseBookEditor:'收起编排面板',
      chooseStory:'打开这个故事', openBook:'继续阅读这本回忆集', bookSaved:'回忆集已保存。',
      editorialHeading:'开场与篇章衔接 · 家人撰写',editorialHelp:'上方保存回忆录名称和开场。这里为开场选择回忆来源，并保存相邻故事之间的衔接文字；查看原话或录音需另行打开来源。',editorialIntroSources:'开场引用',editorialTransition:'衔接文字',editorialSelectSources:'选择来源',editorialNoSources:'当前故事没有可引用的已采纳来源。',editorialSearch:'搜索来源',editorialSearchHelp:'按故事标题、章节或回忆编号筛选；筛选不会读取原话。',editorialClearSearch:'清除筛选',editorialNoMatches:'没有匹配的来源。',editorialChooserCounts:(start,end,matched,total,selected,hidden)=>`显示 ${start}–${end} 条，共 ${matched} 条匹配、${total} 条可用；已选 ${selected} 条，其中 ${hidden} 条当前未显示。`,editorialPage:(page,pages)=>`第 ${page} 页，共 ${pages} 页`,editorialPrevious:'上一页',editorialNext:'下一页',editorialUnavailableSelected:'已选但当前不可用的来源',editorialUnavailableRemove:'此来源当前不可用；取消勾选可移除。',editorialInspect:'查看来源',editorialInspectClose:'关闭来源',editorialInspectLoading:'正在读取已采纳的家人原话…',editorialInspectUnavailable:'来源当前无法查看；已清除上次显示的内容。',editorialOriginalText:'家人原话',editorialOriginalAudio:'家人录音',editorialByline:'署名（提交时填写）',editorialLoadAudio:'加载原始录音',editorialAudioLoaded:'录音已加载。请使用播放器的播放键收听。',editorialAudioBlocked:'请先结束录音，再加载家人录音。',editorialConsent:'已同意在本地使用此来源生成整理建议。',editorialTranscript:'转写（整理内容）',editorialPolished:'整理草稿（非原话）',editorialDerivationAbsent:'没有整理记录。',editorialDerivationPending:'整理仍在等待或处理中；尚无可显示的整理内容。',editorialDerivationFailed:'整理未完成；原始来源仍单独显示。',editorialSaved:'开场与衔接已保存。',editorialSave:'保存引用与衔接',editorialRetry:'重试同一保存',editorialConflict:'内容已变化。你的草稿仍保留；请先重新读取当前内容，再明确保存。',editorialReload:'重新读取当前内容',editorialStartFresh:'以当前故事开始新草稿',editorialDraftKept:'保留的未保存衔接文字',editorialChanged:'来源或故事版本已变化。为避免覆盖，当前内容未显示；请重新读取。',editorialWaitBookSave:'请先确认回忆录名称和开场的保存结果。',editorialLimit:'每段最多选 12 个来源，合计最多 96 个。有衔接文字时须选择来源；空白段落请取消来源。',editorialUnavailable:'引用编辑暂不可用。现有回忆集标题和开场编辑仍可继续。',editorialChapter:n=>`第 ${n} 章`,editorialRecall:n=>`第 ${n} 条回忆`,
      bookStoryCount:n=>`${n} 段故事`, bookMediaCount:n=>`${n} 个素材条目`, bookOpening:'开场',shelfSubtitle:'打开回忆集，从已保存的故事继续阅读。',
      bookHelp:'回忆集按此顺序整理已保存的故事。打开回忆集后，可以把整本回忆集作为聊天或整理建议的上下文。',
      selectedOrder:'回忆集顺序（可调整）', moveUp:'上移', moveDown:'下移',
      untitled:'未命名', processingOff:'此相册库暂未开启本地整理功能。仍可留下文字回忆。',
      memoirSummary:'这本回忆集收录了以下已保存的故事。当前相册库暂未开启对话和整理建议。',
      viewPlan:'查看整理计划',hidePlan:'收起整理计划',refreshPlan:'重新检查计划',planLoading:'正在读取已保存的结构与整理范围…',planUnavailable:'整理计划暂时无法读取，请稍后重试。',planIntro:'按已保存的故事查看顺序与整理范围。尚未生成或修改正文。',planWhole:'整本回忆录',planWithin:'当前上下文范围内',planSmaller:'需要缩小范围',planEligible:'可纳入整理',planNotEligible:'当前不可纳入整理',planLargeHelp:'整本回忆集超出单次上下文范围。可逐篇打开已保存的故事，分别查看和整理。',planCountsUnavailable:'此范围超过当前上限，未提供内容分类计数。',planStories:(n)=>`${n} 段故事`,planChapters:(n)=>`${n} 章`,planItems:(n)=>`${n} 个素材条目`,planKind_family:'家人原话',planKind_transcript:'转写',planKind_editorial:'已保存文字',planKind_ai:'AI 观察',planKind_metadata:'记录资料',planOpenStory:'在回忆集中阅读',planOpeningStory:'正在核对并打开已保存的故事…',planOpenUnavailable:'无法打开此故事。请重新打开当前回忆集后再试。',planEmptyKinds:'没有符合范围的内容分类。',
      fileInvalid:'请选择有效的 WAV 录音（16 kHz、单声道、16 位、最长 30 秒，且不超过 2 MiB）。',
      textRequired:'请先写下回忆内容。', consentRequired:'请先确认是否同意本地录音整理。',
      audioDuringRecording:'请先结束录音，再播放家人的声音。', recording:'正在录音…', textTab:'文字回忆', audioTab:'录音回忆'
    },
    en: {
      memoirScope:'Current scope: the whole memoir',draftChapter:'Draft chapter',readingChapterPrompt:'Discuss the chapter you are reading',readingChapterHelp:'Open a chapter, then place its question in an empty message draft. Review before sending; the conversation stays with the whole memoir.',readingChapterUnavailable:'Open a chapter in this memoir, then try again.',
      voice:'Family voices', chat:'Talk about memories', ideas:'Draft suggestions', books:'Family memoirs',
      unavailable:'Family memories are temporarily unavailable. Please try again.', disabled:'Family memories are not enabled for this library.',
      target:'Memory', voiceHelp:'Family words stay in this library until its owner deletes them. Deleting an original does not change words already adopted into a story.',
      voiceRetention:'Recordings and original words are visible only to library members; only the owner can delete them.',
      text:'Write down a memory', byline:'Byline (optional)', chapter:'Connect to a chapter', whole:'Whole story',
      consent:'I agree to use this text or recording for local drafting.', record:'Record (up to 30 seconds)', stop:'Finish and keep recording', cancelRecord:'Discard recording', file:'Choose a WAV recording', recordingReady:'Recording ready. It uploads only when you choose Save this memory; local AI processing is optional.',
      save:'Save this memory', retry:'Retry the same submission', saved:'Saved and waiting for the story owner to review.', moreBooks:'More collections',
      moreContributions:'Load more family memories', moreTurns:'Earlier messages', refreshTurns:'Refresh viewed conversation', moreStories:'Load more saved stories',
      pending:'Waiting for review', accepted:'Accepted', declined:'Not adopted', noVoices:'No family memories yet.',
      confirmLeave:'Leaving will discard unsent messages and drafts, stop recording, and may cancel a request in progress. Leave anyway?',
      status:'Status',
      mine:'My memory', familyMember:'Family member', viewDerivation:'View transcript and draft', hideDerivation:'Hide draft details', noDerivation:'No transcript or draft is available yet.', transcript:'Transcript', polished:'Draft text', tags:'Topics', consented:'Local drafting consented', noConsent:'Local drafting not consented',
      accept:'Accept', decline:'Decline', review:'Owner review', audio:'Play original recording', deleteOriginal:'Delete original memory', confirmDelete:'Delete this original text or recording? Words already adopted into a story will stay unchanged.',
      listeningHelp:'Listen in order to the first 16 accepted recordings in the current list.', listenFamily:'Listen to family memories', stopListening:'Stop listening', nextRecording:'Next recording', listeningPosition:(index,total,byline)=>`${index}/${total} · ${byline}`, listeningStopped:'Listening stopped.', listeningComplete:'You have heard all these family memories.', listeningFailed:'This recording could not be played. Listening has stopped.', playbackBlocked:'Press play on the player to begin listening.', composeMemory:'Add my memory',
      conversationHelp:'Conversations are removed after 30 days. You send each message yourself; the assistant never changes the story for you.', conversationContextHelp:'Replies use current material, your current question and up to 7 preceding exchanges. Earlier messages remain readable but are not automatically included in this reply; add important context to your new question.', returnToChapter:'Return to current chapter',
      chatRecovering:'Checking the unfinished reply in this conversation…',chatRecoveryFailed:'This pending reply could not be confirmed. Conversation history is preserved; retry the check before sending or cancelling.',chatRecoveryRetry:'Retry checking pending reply',chatPendingSendBlocked:'This conversation already has a pending reply. Refresh its status or cancel the task before sending.',
      chatFollowups:'Keep chatting',chatFollowupHelp:'Choose a question to place it in an empty message draft. Review it before deciding whether to send.',chatFollowupReview:'The question is in your message draft. Review it, then choose Send if you want.',chatFollowupDraftBlocked:'Send or clear your existing message draft before using this question.',chatFollowupDictationBlocked:'Finish recording and add or discard the pending transcript first.',chatFollowupSendBlocked:'Finish or retry the current send first.',chatFollowupJobBlocked:'Wait for or cancel the current reply task first.',chatFollowupImeBlocked:'Finish composing your message first.',chatFollowupSourcesNote:'These references show which material informed the reply; they do not verify that it is true.',chatClarificationCue:'AI would like to know more',chatClarificationHelp:'Add detail in your own words; any suggested question goes into a draft only.',chatLatest:'Latest message',chatWriteNext:'Write next message',sourceViewTranscript:'View transcript',sourceHideTranscript:'Hide transcript',sourceTranscriptAI:'AI transcript · ',sourceTranscriptPending:'The transcript is not ready yet.',sourceTranscriptMissing:'No transcript is available for this recording.',sourceTranscriptRetry:'Transcript could not be loaded. Try again.',
      startChat:'New conversation', closeChat:'End and delete this conversation', confirmClose:'Delete this conversation and its messages?', message:'What would you like to remember together?', send:'Send this message', retrySend:'Retry the same message',
      conversationSelect:'Choose a conversation',conversationNumber:n=>`Conversation ${n}`,conversationCreated:'Just created',conversationRestored:'Returned to the conversation you last selected.',conversationListHelp:'Showing the 8 most recent conversations.',threadBusy:'This conversation still has a task in progress. Finish or cancel it before switching or starting another.',threadDraftBlocked:'Finish recording, review and add or discard the transcript, or resolve the retry message before switching conversations.',threadLoading:'Loading this conversation…',
      chatStarters:'A place to begin', chatStarterHelp:'Choose a prompt, edit it, then send when ready.', starterDetails:'Fill in a memory', starterDetailsText:'Which details in this memory could we ask the family about? Summarize what the sources say, then suggest one useful follow-up question.', starterSequence:'Arrange the timeline', starterSequenceText:'Arrange the known sequence of this memory and point out any uncertain dates or ordering.', starterChapters:'Connect the chapters', starterChaptersText:'Suggest connections between the existing chapters using family words. Keep different perspectives and do not invent experiences.',
      memoirStarterDetails:'Find shared threads', memoirStarterDetailsText:'What threads connect these saved stories? Summarize only what the sources say, then suggest one useful question for the family.', memoirStarterSequence:'Arrange the stories', memoirStarterSequenceText:'Arrange the known order across these stories and clearly mark any dates or ordering that remain uncertain.', memoirStarterChapters:'Connect the stories', memoirStarterChaptersText:'Suggest a transition between these saved stories. Preserve different family accounts and do not invent experiences or facts.',
      chatRecord:'Dictate a message (audio is not retained)', chatContinueRecord:'Dictate the next message (audio is not retained)',chatRetryDictation:'Record another message', chatRecordStop:'Finish and transcribe',chatCaptureWaiting:'Waiting for microphone…',chatTranscribing:'Transcribing the recording…', chatTranscript:'Transcript (editable)', addTranscript:'Add to message', discardTranscript:'Discard transcript', transcriptHelp:'Audio is used only for this transcription and is not kept in the conversation. The transcript is never sent automatically.', transcriptNeedsReview:'Add this transcript to your message or discard it before recording again, so your wording is not replaced.', voiceNextTurnHelp:'The assistant has replied. You can continue by dictating the next message, reviewing the transcript, adding it, then choosing Send.',voiceAsrFailed:'This dictation was not transcribed. Audio is not retained; record again to retry. Your typed message draft is still here.',voicePermissionFailed:'Microphone access failed. Check browser microphone permission and record again; your typed message draft is still here.',voiceCaptureFailed:'Recording did not start or finish. Check the microphone and try again; your typed message draft is still here.',
      keepChatTurn:'Keep my words as a memory',chatTurnKeepBlocked:'Finish or discard any existing memory draft, recording, or pending save, then wait for the current conversation task to finish and try again.',
      refresh:'Check for a reply', cancel:'Cancel current task', noTurns:'Your conversation will appear here.',you:'You',assistant:'Assistant',pendingReply:'Waiting for a reply',pendingQueued:'Your message is queued for a reply.',pendingRunning:'The assistant is preparing a reply.',chatQueued:'Your message is queued for a reply.',chatRunning:'A reply is being prepared.',chatReady:'The assistant has replied.',chatFailed:'The reply could not be completed.',chatCancelled:'The reply was cancelled.',
      ideasHelp:'Suggestions appear as drafts that need review. Read family words and sources before deciding how to change a story.',
      ideaVoice:'Voice instructions',ideaVoiceHelp:'Stop to review the transcript, then add it above and explicitly request a draft. Audio is not saved; transcript records remain for 30 days.',ideaVoiceRecord:'Record instructions',ideaVoiceStop:'Stop and transcribe',ideaVoiceWaiting:'Waiting for microphone…',ideaVoiceTranscribing:'Transcribing instructions…',ideaVoiceTranscript:'Transcript (editable)',ideaVoiceInsert:'Add to instructions',ideaVoiceDiscard:'Discard transcript',ideaVoiceInserted:'Added to the instructions above. Review them before explicitly generating suggestions.',ideaVoiceConfirmLeave:'Leaving Draft suggestions will stop recording and discard the transcript if it has not been added. Your instructions will stay in this reader. Leave anyway?',ideaVoiceOverflow:'The instructions are too long. Both parts are kept; shorten them before adding the transcript.',ideaVoiceInvalid:'Some characters cannot be used. Check the text; both drafts are kept.',ideaVoiceCaptureFailed:'Recording did not start or finish. Your instruction draft is still here.',ideaVoiceAsrFailed:'Transcription did not finish. Your instruction draft is still here; you can record again.',ideaVoicePermissionFailed:'Microphone access failed. Check browser permission and try again.',ideaVoiceReviewRequired:'Add or discard the pending transcript before generating suggestions.',ideaVoiceTooLong:'Instructions are too long. Shorten them and try again; your text is still here.',
      memoirForm:'Memoir form',memoirFormPrompt:'Choose a form',memoirFormExisting:'Existing voice',memoirFormChronicle:'Chronicle',memoirFormEssay:'Family essay',memoirFormLong:'Memoir',
      editorialContextLabel:'Use saved opening and links',editorialContextHelp:'Check saved content first; you decide when to send or create a suggestion.',editorialContextChecking:'Checking the saved opening, transitions, and whole-book scope…',editorialContextReady:'The current opening and transitions are checked. This request will use the saved whole-book content.',editorialContextUnavailable:'The saved opening and transitions cannot be checked right now. Try again later.',editorialContextChanged:'The saved opening, transitions, or story versions changed. Refresh before trying again.',editorialContextSmaller:'This content exceeds the current scope. Narrow the memoir or explicitly continue with the existing story context.',editorialContextContinueBasic:'Continue with the existing memoir context',editorialContextBasicConfirmed:'This request will use the existing memoir context without the saved opening and transitions.',editorialContextChoose:'Recheck saved content or explicitly choose the existing memoir context before sending.',
      instruction:'What would you like help arranging? (optional)',generate:'Create a reviewable suggestion', retryJob:'Retry the same suggestion request',
      queued:'Queued', running:'Arranging', ready:'Reply received', failed:'The draft could not be completed', cancelled:'Cancelled', stale:'The story or its sources changed. Reopen the story before trying again.',
      proposal:'Draft suggestion · review', proposalReview:'AI suggestion · review', savedProposalReview:'Saved AI manuscript · review', savedChapter:'Saved chapter', savedMemoirDirectory:'Saved manuscript chapter directory', savedMemoirCurrent:n=>`Current saved manuscript chapter: ${n}`, compareChapter:'Compare chapter wording', currentChapter:'Current chapter in this reader', unchangedChapter:'Matches the wording in this reader', memoirDraftDirectory:'Memoir draft chapter directory', memoirDraftCurrent:n=>`Current draft chapter to review: ${n}`, questions:'Questions for your family', refs:'Sources', adopt:'Bring suggestion into editor',
      chapterNumber:'Chapter', sourceCount:'sources to review', sourceFamily:'Family memory', sourceTranscript:'Transcript of a family voice', sourceEditorial:'Saved editorial story', sourceBookOpening:'Memoir opening · editorial wording', sourceAI:'AI observation · review', sourceMetadata:'Recorded metadata', sourceOther:'Source', sourceNotLoaded:'Check this in the original memory or media details',
      answer:'Assistant reply', clarification:'A little more context may help', pollManual:'Automatic checks paused. Check for the reply manually.', expires:'This conversation expires and will be deleted on',expiresSuffix:'.',
      error:'That action did not finish. Check and try again.', tooLarge:'This drafting pass is too large. Split it into smaller passes of up to 24 chapters and 96 sources each.', conflict:'This story has changed. Reopen its latest version to continue; your text is kept.',
      bookTitle:'Collection title', introduction:'Opening note (optional)', chooseStories:'Choose saved stories in order (1–24)',
      createBook:'Save collection', updateBook:'Save changes', retryBook:'Retry the same save', noBooks:'No collections yet. Bring a few saved family stories together in one place.', composeBook:'Arrange a memory collection', continueBook:'Continue saving collection', continueEditBook:'Continue editing collection', collapseBookEditor:'Collapse editor',
      chooseStory:'Open this story', openBook:'Continue reading this collection', bookSaved:'Collection saved.',
      editorialHeading:'Opening and story transitions · family writing',editorialHelp:'Save the memoir title and opening in the form above. Here, choose sources for that opening and save connecting passages between stories. Open a source separately to read the original or hear its recording.',editorialIntroSources:'Opening references',editorialTransition:'Transition text',editorialSelectSources:'Choose sources',editorialNoSources:'These stories have no currently linked, accepted sources to cite.',editorialSearch:'Search sources',editorialSearchHelp:'Filter by story title, chapter, or recall label. Filtering does not read original words.',editorialClearSearch:'Clear filter',editorialNoMatches:'No sources match this filter.',editorialChooserCounts:(start,end,matched,total,selected,hidden)=>`Showing ${start}–${end} of ${matched} matches; ${total} available; ${selected} selected (${hidden} selected outside this view).`,editorialPage:(page,pages)=>`Page ${page} of ${pages}`,editorialPrevious:'Previous page',editorialNext:'Next page',editorialUnavailableSelected:'Selected sources no longer available',editorialUnavailableRemove:'This source is no longer available. Uncheck it to remove the reference.',editorialInspect:'Inspect source',editorialInspectClose:'Close source',editorialInspectLoading:'Reading the accepted family contribution…',editorialInspectUnavailable:'This source is unavailable. The previously displayed content has been cleared.',editorialOriginalText:'Original family words',editorialOriginalAudio:'Original family recording',editorialByline:'Byline (as submitted)',editorialLoadAudio:'Load original recording',editorialAudioLoaded:'Recording loaded. Press play on the player when you are ready.',editorialAudioBlocked:'Finish recording before loading the family recording.',editorialConsent:'Local drafting consent was recorded for this source.',editorialTranscript:'Transcript (derived content)',editorialPolished:'Draft text (not the original)',editorialDerivationAbsent:'No processing record is available.',editorialDerivationPending:'Processing is waiting or in progress; no derived text is available yet.',editorialDerivationFailed:'Processing did not finish; the original source remains separate.',editorialSaved:'Opening references and transitions saved.',editorialSave:'Save references and transitions',editorialRetry:'Retry the same save',editorialConflict:'The collection changed. Your draft is kept; reload the current version before explicitly saving again.',editorialReload:'Reload current version',editorialStartFresh:'Start a fresh draft from current stories',editorialDraftKept:'Unsaved transition text kept',editorialChanged:'A source or story revision changed. Current editorial text is hidden to avoid overwriting; reload before continuing.',editorialWaitBookSave:'Confirm the title and opening save before saving their references.',editorialLimit:'Choose up to 12 sources per section and 96 total. A passage needs a source; an empty passage must have no sources.',editorialUnavailable:'Citation editing is unavailable. The existing collection title and opening editor still work.',editorialChapter:n=>`Chapter ${n}`,editorialRecall:n=>`Recall ${n}`,
      bookStoryCount:n=>`${n} ${n===1?'story':'stories'}`, bookMediaCount:n=>`${n} media ${n===1?'entry':'entries'}`, bookOpening:'Opening note',
      bookHelp:'A collection keeps saved stories in this order. Open a collection to use it as context for a conversation or draft.',
      selectedOrder:'Collection order (adjustable)', moveUp:'Move up', moveDown:'Move down',
      untitled:'Untitled', processingOff:'Local drafting is disabled for this library. You can still leave a text memory.',
      memoirSummary:'This collection contains the saved stories below. Conversations and draft suggestions are not enabled for this library.',
      viewPlan:'View drafting plan',hidePlan:'Hide drafting plan',refreshPlan:'Recheck plan',planLoading:'Reading the saved structure and drafting scope…',planUnavailable:'The drafting plan is temporarily unavailable. Please try again.',planIntro:'Review saved-story order and drafting scope. No story text is generated or changed.',planWhole:'Whole memoir',planWithin:'Within current context limits',planSmaller:'Smaller scope required',planEligible:'Eligible for drafting',planNotEligible:'Not eligible for drafting now',planLargeHelp:'The collection is larger than one context pass. Open a saved story to inspect and draft one essay at a time.',planCountsUnavailable:'This scope exceeds current limits; category counts are unavailable.',planStories:n=>`${n} ${n===1?'story':'stories'}`,planChapters:n=>`${n} ${n===1?'chapter':'chapters'}`,planItems:n=>`${n} media ${n===1?'entry':'entries'}`,planKind_family:'Family words',planKind_transcript:'Transcripts',planKind_editorial:'Saved editorial text',planKind_ai:'AI observations',planKind_metadata:'Recorded metadata',planOpenStory:'Read this story',planOpeningStory:'Checking and opening the saved story…',planOpenUnavailable:'This story could not be opened. Reopen the current memoir and try again.',planEmptyKinds:'No eligible content categories.',shelfSubtitle:'Open a collection to continue reading its saved stories.',
      fileInvalid:'Choose a valid WAV recording (16 kHz, mono, 16-bit, up to 30 seconds and 2 MiB).',
      textRequired:'Write a memory first.', consentRequired:'Choose whether you agree to local recording processing.',
      audioDuringRecording:'Finish recording before playing family voices.', recording:'Recording…', textTab:'Written memory', audioTab:'Voice recording'
    }
  };
  let epoch=0, panelRenderEpoch=0, chatAnnouncementKey='', chatComposition=null, chatRenderDeferred=null, bookEpoch=0, currentScope=null, target=null, targetFingerprint='', activeTab='voice';
  let caps=null, capsIdentity='', contributionList=[], contributionDetails=new Map(), canReview=false, canDelete=false, contributionPage=1, contributionsHasMore=false, contributionsBusy=false;
  let conversation=null,conversationList=[],conversationDrafts=new Map(),conversationSelectionEpoch=0,conversationLoading=false,conversationCreating=false,conversationDeleting=false,conversationCreateToken=null,conversationDeleteToken=null,conversationLoadToken=null, turns=[], turnPage=1, turnsHasMore=false, turnsBusyToken=null, assistantInflightToken=null, recentTurn=null, messageDraft=null, chatTextDraft='', activeJob=null, pendingJob=null;
  const conversationHints=new Map(),conversationHintLimit=16;
  let editorialContextChoice=null,editorialContextPreflight=null,editorialContextGeneration=0,editorialContextNeedsDecisionKey='',editorialContextBasicConfirmedKey='',editorialContextDecisionStatusKey='';
  let chatRecoveryGeneration=0,pendingChatRecovery=null,activeChatJobFence=null,jobVisibilityEpoch=0;
  let pendingContribution=null, recording=null, captureHandle=null, captureTimer=null,captureStarting=false,captureGeneration=0,captureForm=null;
  let voiceCapabilitiesOwner='',voiceCapabilitiesValue=null,voiceCapabilitiesPending=null;
  let chatCaptureHandle=null,chatCaptureTimer=null,chatCaptureReady=null,chatRecordingBusy=false,chatCaptureStarting=false,chatTranscribing=false,chatTranscript='',chatVoiceError='',chatVoiceEpoch=0,chatCaptureVoiceTicket=0;
  let ideaCaptureHandle=null,ideaCaptureTimer=null,ideaCaptureReady=null,ideaCaptureStarting=false,ideaTranscribing=false,ideaTranscript='',ideaVoiceError='',ideaVoiceEpoch=0,ideaVoiceTicket=0;
  let ideaComposition=null,ideaRenderDeferred=false,ideaRecordButton=null;
  let contributionDraft={mode:'text',text:'',byline:'',chapter_id:'',consent:false},ideaDraft='',memoirFormChoice='existing',bookTitleDraft='',bookIntroDraft='',pendingBook=null,bookSubmittingOwner='', selectedBook=null, bookEditorOpen=false, booksList=[], storyOptions=[], storyPage=0, storyOptionsHasMore=false,bookStorySelection=new Set(),bookPage=1;
  let editorialModel=null,editorialPending=null,editorialBusyOwner='',editorialGeneration=0,bookEditSequence=0,editorialInspection=null,editorialInspectionEpoch=0;
  let booksHasMore=false, pollTimer=null, pollCount=0, controllers=new Set(), bookControllers=new Set(), objectUrls=new Set(), individualPlayers=new Map(), individualAttempts=new Map(), individualPlaybackEpoch=0, roots=new Set(), bookContainers=new Set();
  let mount=null, statusNode=null, panelNode=null, planPanelNode=null, planButton=null, planData=null, visibilityHandler=null, familyListening=null, familyListenEpoch=0;
  let conversationRestorationNotice=false;
  const replySpeechDisposers=new Set();
  const lang=()=>scopeNow()?.language==='en'?'en':'zh';
  const t=key=>labels[lang()][key]||key;
  const editionLabels={zh:{open:'审阅并保存整本回忆录',heading:'核对整本回忆录',help:'逐章核对并修改整理稿，再明确保存为家庭版本。原故事、原话和录音会分别保留。关联回忆被删除后，这个版本的整理文字将不再可读。',title:'版本标题',chapter:'篇章',review:'我已核对各篇章、来源和不确定之处',save:'明确保存这个版本',retry:'用同一份稿件重试保存',saved:'家庭版本已保存。',read:'重新读取已保存版本',unavailable:'此相册库暂未开放回忆录版本保存。整理稿仍可在这里核对。',loading:'正在检查当前稿件与来源…',error:'暂时无法确认保存结果。稿件已保留；重试会使用完全相同的内容。',conflict:'稿件、篇章或来源已变化。文字已保留，请重新核对当前资料后再保存。',invalid:'请检查标题和篇章文字的长度，并完成核对确认。',changed:'这个版本的来源已变化或被删除，整理文字已隐藏。',discard:'重新载入会放弃当前版本的未保存改动。继续吗？',reload:'重新载入当前整理稿',original:'查看生成时的原稿与来源',scope:(chapters,sources)=>`本次版本 · ${chapters} 篇章 · ${sources} 条引用`,checkAgain:'重新检查保存是否可用',finish:'请先确认当前版本的保存结果，再切换或生成新稿。',shelf:'已保存的家庭版本',shelfHelp:'版本列表只显示序号、保存日期和状态；打开后会重新核对当前来源。',shelfLoading:'正在读取已保存版本…',shelfUnavailable:'已保存版本暂时无法读取，请稍后重试。',shelfDetailUnavailable:'暂时无法核对这个版本；整理文字已隐藏，请重新读取。',shelfEmpty:'还没有已保存的家庭版本。',shelfMore:'下一页',shelfPrevious:'上一页',shelfNext:'下一页',shelfRead:'打开版本',shelfChanged:'来源已变化或已删除，整理文字已隐藏。',shelfRetry:'重新读取版本列表',shelfRefresh:'刷新版本列表',shelfReadAgain:'重新核对此版本',shelfVersion:n=>`第 ${n} 个版本`,shelfDate:n=>new Intl.DateTimeFormat('zh-CN',{dateStyle:'medium',timeStyle:'short'}).format(new Date(n*1000)),shelfState_current:'当前可读',shelfState_source_invalidated:'来源已删除',shelfState_source_changed:'来源已变化',shelfSources:'查看本版本的来源材料',shelfSourcesLoading:'正在核对本版本的来源…',shelfSourcesUnavailable:'来源目录暂时无法读取；未载入原话或录音。',shelfSourcesChanged:'来源或版本已变化，整理文字与来源材料均已隐藏。',shelfSourcesEmpty:'当前版本没有可显示的来源材料。',shelfSourceMore:'下一页来源',shelfSourcePrevious:'上一页来源',shelfSourceInspect:'核对材料',shelfSourceLoading:'正在重新读取当前来源…',shelfSourceUnavailable:'当前无法读取此来源；已清除先前显示的材料。',shelfSourceChanged:'来源或版本已变化，材料已隐藏。',shelfOrigin_contribution_text:'家人原话',shelfOrigin_contribution_audio:'家人录音',shelfOrigin_asset_note:'素材留言',shelfOrigin_caption:'图片描述',shelfOrigin_book_introduction:'回忆录开场文字',shelfOrigin_story_chapter:'已保存的篇章文字',shelfKind_family:'家人提供',shelfKind_transcript:'AI 转写',shelfKind_ai:'AI 描述 · 需核实',shelfKind_editorial:'编辑文字',shelfOriginal:'当前保存的家人原话',shelfCurrentCaption:'当前 AI 图片描述 · 需核实',shelfFamilyCaption:'当前由家人编辑的图片描述',shelfSavedEditorial:'当前保存的编辑文字',shelfTranscript:'当前转写文字 · AI 识别',shelfPromptExcerpt:'本版本实际使用的文字节选',shelfTruncated:'此处仅显示文字的有限部分；不是完整原文。',shelfAudioLoad:'明确加载原始录音',shelfAudioReload:'重新加载原始录音',shelfAudioLoading:'正在加载录音…',shelfAudioReady:'录音已加载；请点播放器上的播放键开始。',shelfAudioUnavailable:'录音暂时无法加载；已清除先前显示的材料。',shelfAudioGate:'原始录音暂不可用。'},en:{open:'Review and save this memoir',heading:'Review the whole memoir',help:'Review and edit each chapter, then explicitly save as a family edition. Original stories, words and recordings remain separate. Deleting a linked family contribution makes this edition unavailable.',title:'Edition title',chapter:'Chapter',review:'I have checked the chapters, sources and uncertain details',save:'Explicitly save this edition',retry:'Retry the same manuscript save',saved:'Family edition saved.',read:'Read the saved edition again',unavailable:'Edition saving is not enabled for this library. You can still review the draft here.',loading:'Checking the current draft and sources…',error:'The save result could not be confirmed. Your manuscript is kept; retry uses exactly the same content.',conflict:'The draft, chapters or sources changed. Your words are kept; review current sources before saving again.',invalid:'Check title and chapter length, then confirm your review.',changed:'This edition’s sources changed or were deleted. Its manuscript is hidden.',discard:'Reloading discards unsaved changes to this edition. Continue?',reload:'Reload the current draft',original:'View the generated draft and its sources',scope:(chapters,sources)=>`This edition · ${chapters} chapters · ${sources} references`,checkAgain:'Check edition availability again',finish:'Confirm the current edition save result before switching or drafting again.',shelf:'Saved family editions',shelfHelp:'The list shows an ordinal, saved date and status. Opening an edition checks its sources again.',shelfLoading:'Loading saved editions…',shelfUnavailable:'Saved editions are temporarily unavailable. Try again later.',shelfDetailUnavailable:'This edition could not be verified. Its manuscript is hidden; refresh and try again.',shelfEmpty:'No family editions have been saved yet.',shelfMore:'Next page',shelfPrevious:'Previous page',shelfNext:'Next page',shelfRead:'Open edition',shelfChanged:'Sources changed or were deleted. The manuscript is hidden.',shelfRetry:'Reload saved editions',shelfRefresh:'Refresh edition list',shelfReadAgain:'Check this edition again',shelfVersion:n=>`Edition ${n}`,shelfDate:n=>new Intl.DateTimeFormat('en',{dateStyle:'medium',timeStyle:'short'}).format(new Date(n*1000)),shelfState_current:'Readable now',shelfState_source_invalidated:'Source deleted',shelfState_source_changed:'Source changed',shelfSources:'Review this edition’s source materials',shelfSourcesLoading:'Checking this edition’s sources…',shelfSourcesUnavailable:'The source list is unavailable. No original text or audio was loaded.',shelfSourcesChanged:'Sources or edition changed. The manuscript and source materials are hidden.',shelfSourcesEmpty:'This edition has no available source materials.',shelfSourceMore:'Next source page',shelfSourcePrevious:'Previous source page',shelfSourceInspect:'Inspect material',shelfSourceLoading:'Rechecking this current source…',shelfSourceUnavailable:'This source is unavailable. Previously displayed material has been cleared.',shelfSourceChanged:'Sources or edition changed. Material is hidden.',shelfOrigin_contribution_text:'Family original',shelfOrigin_contribution_audio:'Family recording',shelfOrigin_asset_note:'Asset note',shelfOrigin_caption:'Caption',shelfOrigin_book_introduction:'Memoir introduction',shelfOrigin_story_chapter:'Saved chapter wording',shelfKind_family:'Family supplied',shelfKind_transcript:'AI transcript',shelfKind_ai:'AI caption · verify',shelfKind_editorial:'Editorial text',shelfOriginal:'Current saved family original',shelfCurrentCaption:'Current AI caption · verify',shelfFamilyCaption:'Current family edited caption',shelfSavedEditorial:'Current saved editorial wording',shelfTranscript:'Current transcript · AI derived',shelfPromptExcerpt:'Exact text excerpt used in this edition',shelfTruncated:'Only a bounded part of this text is shown; it is not the complete original.',shelfAudioLoad:'Explicitly load original recording',shelfAudioReload:'Load original recording again',shelfAudioLoading:'Loading recording…',shelfAudioReady:'Recording loaded. Press the player’s play button to listen.',shelfAudioUnavailable:'Recording is unavailable. Previously displayed material has been cleared.',shelfAudioGate:'Original audio is not available right now.'}};
  const et=key=>editionLabels[lang()][key];
  let editionReview=null,editionGeneration=0,savedEditionGeneration=0,savedEditionState=null;
  const clearEditionReview=()=>{editionGeneration++;editionReview=null;};
  function clearSavedEditionSpeech(state=savedEditionState){if(!state?.speechDisposers)return;const disposers=[...state.speechDisposers];state.speechDisposers.clear();for(const dispose of disposers){replySpeechDisposers.delete(dispose);try{dispose();}catch(_){}}}
  const clearSavedEditions=()=>{clearSavedEditionSpeech();if(savedEditionState)clearSavedEditionSource(savedEditionState,{resetList:true,status:'idle'});savedEditionGeneration++;savedEditionState=null;};
  function leaveEditionForNextAction(){
    if(!editionReview)return true;
    if(editionReview.composing){showStatus(t('chatFollowupImeBlocked'),'pending');return false;}
    if(editionReview.busy||editionReview.pending){showStatus(et('finish'),'pending');return false;}
    if(editionReview.dirty&&!window.confirm(et('discard')))return false;
    clearEditionReview();return true;
  }
  const el=(tag,text='',className='')=>{const node=document.createElement(tag);if(text!==undefined&&text!==null)node.textContent=String(text);if(className)node.className=className;return node;};
  const btn=(text,fn,className='memory-community-button')=>{const node=el('button',text,className);node.type='button';node.addEventListener('click',fn);return node;};
  const wellFormed=value=>{for(let i=0;i<value.length;i++){const code=value.charCodeAt(i);if(code>=0xd800&&code<=0xdbff){if(i+1>=value.length||value.charCodeAt(i+1)<0xdc00||value.charCodeAt(i+1)>0xdfff)return false;i++;}else if(code>=0xdc00&&code<=0xdfff)return false;}return true;};
  const boundedText=(value,maxBytes)=>typeof value==='string'&&wellFormed(value)&&new TextEncoder().encode(value).length<=maxBytes&&!/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/u.test(value);
  const safeText=(value,maxBytes=8192)=>boundedText(value,maxBytes)&&value.trim().length>0;
  const memoirFormRecipes={
    chronicle:'按已有时间线整理为忠实纪事。保留不同家人的说法，未知日期先提问，不编造事件。',
    essay:'把已有回忆整理成温暖的家庭散文。保留真实讲述与不确定之处，不补写没有来源的经历。',
    long_memoir:'把已有篇章连成有开篇、衔接和回望的长篇回忆录。保留原篇章顺序与家人的不同声音，不编造对白、人物或事件。'
  };
  const frozenIdeaInstructions=(base,choice)=>{const recipe=target?.type==='memoir'?memoirFormRecipes[choice]||'':'';return recipe?(base?`${base}\n${recipe}`:recipe):base;};
  const current=(ticket,owner)=>ticket===epoch&&!scopeNow()?.locked&&JSON.stringify([scopeNow()?.account,scopeNow()?.library])===owner;
  function clearReplySpeech(){const disposers=[...replySpeechDisposers];replySpeechDisposers.clear();for(const dispose of disposers)try{dispose();}catch(_){}}
  const bookCurrent=(ticket,owner)=>ticket===bookEpoch&&!scopeNow()?.locked&&JSON.stringify([scopeNow()?.account,scopeNow()?.library])===owner;
  const clearPlayer=player=>{if(!player)return;try{player.pause?.();}catch(_){}try{player.removeAttribute?.('src');}catch(_){}try{player.src='';player.load?.();}catch(_){}player.remove?.();};
  const forgetUrls=()=>{clearEditorialInspection();individualPlaybackEpoch++;for(const button of individualAttempts.keys())if(button?.parentNode)button.disabled=false;individualAttempts.clear();for(const url of objectUrls)URL.revokeObjectURL(url);objectUrls.clear();for(const [player,button] of individualPlayers){clearPlayer(player);if(button?.parentNode)button.disabled=false;}individualPlayers.clear();};
  function stopFamilyListening(message){
    familyListenEpoch++;const session=familyListening;familyListening=null;if(!session)return;
    const url=session.url;session.url=null;clearPlayer(session.player);session.player=null;
    if(url){objectUrls.delete(url);URL.revokeObjectURL(url);}
    if(session.status&&session.status.parentNode)session.status.textContent=message||t('listeningStopped');
    if(session.playerBox?.parentNode)session.playerBox.replaceChildren();
    if(session.controls?.parentNode){session.controls.replaceChildren(session.startButton);}
  }
  const ideaVoicePending=()=>Boolean(ideaCaptureStarting||ideaCaptureHandle||ideaTranscribing||ideaTranscript);
  const isCapturing=()=>Boolean(captureStarting||captureHandle||chatRecordingBusy||chatCaptureHandle||ideaCaptureStarting||ideaCaptureHandle||ideaTranscribing);
  function stopPlayback(){stopFamilyListening();forgetUrls();}
  function notifyAudioStart(){if(typeof window.dispatchEvent==='function'&&typeof window.CustomEvent==='function')window.dispatchEvent(new window.CustomEvent('photohouse-memory-audio-start'));}
  const stopPoll=(reset=true)=>{if(pollTimer)clearTimeout(pollTimer);pollTimer=null;if(reset)pollCount=0;};
  function invalidateChatRecovery(){chatRecoveryGeneration++;pendingChatRecovery=null;activeChatJobFence=null;}
  function clearChatComposition(){if(chatComposition?.timer)clearTimeout(chatComposition.timer);chatComposition=null;chatRenderDeferred=null;}
  function compositionCurrent(state){return state===chatComposition&&state?.composing&&state.ticket===epoch&&current(state.ticket,state.owner)&&state.target===target&&state.fingerprint===targetFingerprint&&state.conversation===conversation&&state.selection===conversationSelectionEpoch&&state.tab==='chat'&&state.renderId===panelRenderEpoch&&state.root?.parentNode===panelNode&&state.input?.isConnected!==false;}
  function assignComposedChatValue(state){
    if(state.field==='transcript')chatTranscript=state.input.value;
    else {chatTextDraft=state.input.value;if(conversation)conversationDrafts.set(conversation.id,chatTextDraft);}
  }
  function flushDeferredChatRender(state){
    if(!state||state!==chatComposition||state.composing||!state.endSeen||!state.finalInput||!chatRenderDeferred||
      chatRenderDeferred.ticket!==state.ticket||chatRenderDeferred.owner!==state.owner||chatRenderDeferred.target!==state.target||chatRenderDeferred.fingerprint!==state.fingerprint||
      activeTab!=='chat'||!current(state.ticket,state.owner)||target!==state.target||targetFingerprint!==state.fingerprint||state.conversation!==conversation||state.selection!==conversationSelectionEpoch||state.root?.parentNode!==panelNode||state.input?.isConnected===false)return;
    assignComposedChatValue(state);clearChatComposition();void renderPanel();
  }
  const clearCapture=async keep=>{if(!keep){captureGeneration++;captureStarting=false;recording=null;}if(captureTimer)clearTimeout(captureTimer);captureTimer=null;const handle=captureHandle;captureHandle=null;syncContributionCaptureForm();if(handle)await handle.stop(Boolean(keep));syncContributionCaptureForm();};
  const clearChatCapture=async()=>{chatVoiceEpoch++;chatCaptureVoiceTicket=0;if(chatCaptureTimer)clearTimeout(chatCaptureTimer);chatCaptureTimer=null;const handle=chatCaptureHandle;chatCaptureHandle=null;chatCaptureReady=null;chatRecordingBusy=false;chatCaptureStarting=false;chatTranscribing=false;if(handle)await handle.stop(false);};
  const clearIdeaVoice=async(clearTranscript=true)=>{ideaVoiceEpoch++;ideaVoiceTicket=0;if(ideaCaptureTimer)clearTimeout(ideaCaptureTimer);ideaCaptureTimer=null;const handle=ideaCaptureHandle;ideaCaptureHandle=null;ideaCaptureReady=null;ideaCaptureStarting=false;ideaTranscribing=false;if(clearTranscript)ideaTranscript='';ideaVoiceError='';if(handle)await handle.stop(false);};
  const stopRequests=(includeBooks=false)=>{for(const controller of controllers)controller.abort();controllers.clear();if(includeBooks){for(const controller of bookControllers)controller.abort();bookControllers.clear();}};
  const withLibrary=path=>path;
  async function api(path,options={},bookRequest=false) {
    const snapshot=scopeNow(),owner=JSON.stringify([snapshot?.account,snapshot?.library]),revision=membershipRevision(snapshot),attachedRevision=bookRequest?null:membershipRevision(currentScope),ticket=bookRequest?bookEpoch:epoch;
    if(!snapshot?.account||!snapshot?.library||snapshot?.locked)throw new DOMException('Memory scope closed','AbortError');
    if(!bookRequest&&currentScope&&revision!==attachedRevision)throw new DOMException('Stale memory scope','AbortError');
    const controller=new AbortController(),bucket=bookRequest?bookControllers:controllers;bucket.add(controller);
    const externalSignal=options.signal,abortExternal=()=>controller.abort();
    if(externalSignal?.aborted)controller.abort();else externalSignal?.addEventListener('abort',abortExternal,{once:true});
    try {
      const result=await request(withLibrary(path),{...options,signal:controller.signal});
      if(!(bookRequest?bookCurrent(ticket,owner):current(ticket,owner))||membershipRevision(scopeNow())!==revision||!bookRequest&&currentScope&&membershipRevision(currentScope)!==attachedRevision)throw new DOMException('Stale memory response','AbortError');
      return result;
    } catch(error) {
      const active=bookRequest?bookCurrent(ticket,owner):current(ticket,owner);
      if((error?.status===401||error?.status===403)&&active&&membershipRevision(scopeNow())===revision&&(bookRequest||!currentScope||membershipRevision(currentScope)===attachedRevision))forgetConversationScope(snapshot.account,snapshot.library,revision);
      throw error;
    } finally {externalSignal?.removeEventListener('abort',abortExternal);bucket.delete(controller);}
  }
  const bookApi=(path,options={})=>api(path,options,true);
  const showStatus=(text,kind='')=>{if(text!==t('conversationRestored'))conversationRestorationNotice=false;if(statusNode){statusNode.textContent=text||'';statusNode.dataset.state=kind;}};
  const notifyError=error=>{if(error?.name==='AbortError')return;if(!error?.status||error.status===401||error.status===403||error.status>=500)onError(error);};
  const report=(error,owner,ticket)=>{if(error?.name==='AbortError')return;if(current(ticket,owner)){showStatus(error?.status===409?t('conflict'):error?.status===422?t('tooLarge'):t('error'),'error');notifyError(error);}};
  const reportBook=(error,owner,ticket)=>{if(error?.name==='AbortError')return;if(bookCurrent(ticket,owner)){showStatus(error?.status===409?t('conflict'):error?.status===422?t('tooLarge'):t('error'),'error');notifyError(error);}};
  const appendStatus=(root,text)=>{const node=el('p',text,'memory-community-status');node.setAttribute('role','status');root.append(node);return node;};
  const validStoryTarget=value=>value&&value.type==='story'&&uuidOK(value.id)&&/^[1-9][0-9]*$/.test(String(value.revision))&&typeof value.title==='string'&&Array.isArray(value.chapters)&&value.chapters.length>=1&&value.chapters.length<=6&&['zh','en'].includes(value.language)&&/^[0-9a-f]{64}$/.test(value.selection_revision||'')&&value.chapters.every(chapter=>chapter&&/^chapter-[1-6]$/.test(chapter.id)&&typeof chapter.title==='string'&&Array.isArray(chapter.asset_ids)&&chapter.asset_ids.length>=1&&chapter.asset_ids.length<=4&&chapter.asset_ids.every(idOK)&&Array.isArray(chapter.evidence_ids)&&chapter.evidence_ids.length<=12&&chapter.evidence_ids.every(id=>typeof id==='string'));
  const validBookTarget=value=>value&&value.type==='memoir'&&uuidOK(value.id)&&/^[1-9][0-9]*$/.test(String(value.revision))&&typeof value.title==='string'&&Array.isArray(value.stories);
  const canEdit=()=>Boolean(target?.can_edit);
  const targetType=()=>target?.type==='memoir'?'book':'story';
  const pathStory=()=>`${API}/stories/${target.id}/contributions`;
  const chapterOptions=()=>target?.type==='story'?target.chapters.filter(ch=>/^chapter-[1-6]$/.test(ch.id)):[];
  function targetLabel(){return target?.title||t('untitled');}
  async function resolveVoiceCapabilities(ticket,owner){
    if(voiceCapabilitiesOwner!==owner){voiceCapabilitiesOwner=owner;voiceCapabilitiesValue=null;voiceCapabilitiesPending=null;}
    if(voiceCapabilitiesValue)return voiceCapabilitiesValue;
    let pending=voiceCapabilitiesPending;
    if(!pending){pending=Promise.resolve().then(()=>voiceCapabilities?.()??{});voiceCapabilitiesPending=pending;}
    try{const result=await pending;if(!current(ticket,owner))return null;if(voiceCapabilitiesPending!==pending)return voiceCapabilitiesValue;
      voiceCapabilitiesValue={transcribe:result?.transcribe===true,max_audio_seconds:Number.isFinite(Number(result?.max_audio_seconds))?Math.min(30,Math.max(1,Number(result.max_audio_seconds))):30};return voiceCapabilitiesValue;
    }catch(_){if(current(ticket,owner)&&voiceCapabilitiesPending===pending)voiceCapabilitiesValue={transcribe:false,max_audio_seconds:30};return voiceCapabilitiesValue;}
    finally{if(voiceCapabilitiesPending===pending)voiceCapabilitiesPending=null;}
  }
  function renderShell(container) {
    const root=el('section','','memory-community');
    root.dataset.state='loading';
    const heading=el('h2',target?.type==='memoir'?(lang()==='zh'?'聊聊这本回忆录':'Talk about this memoir'):targetLabel(),'memory-community-heading');
    const tabs=el('nav','','memory-community-tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label',lang()==='zh'?'家庭回忆':'Family memories');
    const content=el('div','','memory-community-content');content.id=panelId;content.setAttribute('role','tabpanel');content.tabIndex=0;
    const status=el('p','','memory-community-status');status.setAttribute('role','status');
    root.prepend(heading);
    if(target?.type==='memoir'){const context=el('p',`${t('memoirScope')} · ${targetLabel()}`,'memory-community-memoir-context memory-community-meta');context.setAttribute('role','note');context.style.overflowWrap='anywhere';root.append(context);}
    if(target?.type==='memoir'){
      planButton=btn(t('viewPlan'),()=>void toggleBookPlan(),'memory-book-plan-toggle');planButton.id=`memory-book-plan-toggle-${instanceId}-${attachmentId}`;planButton.setAttribute('aria-expanded','false');root.append(planButton);
    }else planButton=null;
    root.append(tabs,content,status);
    if(target?.type==='memoir'){const shelf=el('section','','memory-edition-shelf-host');shelf.setAttribute('aria-live','polite');root.append(shelf);}
    planPanelNode=target?.type==='memoir'?el('section','','memory-book-plan-panel'):null;
    if(planPanelNode){planPanelNode.hidden=true;planPanelNode.id=`memory-book-plan-${instanceId}-${attachmentId}`;planPanelNode.setAttribute('role','region');planPanelNode.setAttribute('aria-labelledby',planButton.id);root.append(planPanelNode);planButton.setAttribute('aria-controls',planPanelNode.id);}
    container.replaceChildren(root);mount=root;statusNode=status;panelNode=content;return root;
  }
  function visibleTabs(){const list=[];if(target?.type==='story'&&caps?.contributions_enabled)list.push('voice');if(caps?.generation_enabled){list.push('chat');if(canEdit())list.push('ideas');}return list;}
  function selectTab(key){if(activeTab===key)return;if(activeTab==='ideas'&&!leaveEditionForNextAction())return;if(activeTab==='ideas'&&editionReview?.composing){showStatus(t('chatFollowupImeBlocked'),'pending');return;}if(activeTab==='ideas'&&key!=='ideas'&&ideaVoicePending()&&!window.confirm(t('ideaVoiceConfirmLeave')))return;invalidateEditorialContextPreflight();clearChatComposition();clearIdeaComposition();stopFamilyListening();if(activeTab==='chat'&&key!=='chat'){void clearChatCapture();chatTranscript='';chatVoiceError='';}if(activeTab==='voice'&&key!=='voice'){void clearCapture(false);}if(activeTab==='ideas'&&key!=='ideas')void clearIdeaVoice(true);activeTab=key;renderTabs();void renderPanel();}
  function renderTabs(){
    if(!mount)return;const tabs=mount.querySelector('.memory-community-tabs');if(!tabs)return;tabs.replaceChildren();
    if(!visibleTabs().includes(activeTab))activeTab=visibleTabs()[0]||'voice';
    for(const key of visibleTabs()){
      const item=btn(t(key),()=>selectTab(key),'memory-community-tab');
      item.id=tabId(key);item.tabIndex=activeTab===key?0:-1;item.setAttribute('role','tab');item.setAttribute('aria-selected',String(activeTab===key));item.setAttribute('aria-controls',panelId);tabs.append(item);
    }
    const active=tabs.querySelector(`#${tabId(activeTab)}`);panelNode?.setAttribute('aria-labelledby',active?.id||'');
    if(!tabs.dataset.keyboardBound){tabs.dataset.keyboardBound='true';tabs.addEventListener('keydown',event=>{const keys=visibleTabs(),index=keys.indexOf(activeTab);if(index<0||!keys.length)return;let next=index;if(event.key==='ArrowRight')next=(index+1)%keys.length;else if(event.key==='ArrowLeft')next=(index+keys.length-1)%keys.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=keys.length-1;else return;event.preventDefault();selectTab(keys[next]);tabs.querySelector(`#${tabId(keys[next])}`)?.focus?.();});}
  }
  async function ensureCapabilities(){
    const s=scopeNow(),identity=JSON.stringify([s?.account,s?.library,membershipRevision(s)]);
    if(caps&&capsIdentity===identity)return caps;
    const data=await api(`${API}/capabilities`);
    if(!data||data.version!==1||typeof data.enabled!=='boolean'||typeof data.contributions_enabled!=='boolean'||typeof data.generation_enabled!=='boolean')throw new Error('Invalid family memory capabilities');
    caps=data;capsIdentity=identity;return data;
  }
  async function ensureBookCapabilities(){
    const s=scopeNow(),identity=JSON.stringify([s?.account,s?.library,membershipRevision(s)]);if(caps&&capsIdentity===identity)return caps;
    const data=await bookApi(`${API}/capabilities`);
    if(!data||data.version!==1||typeof data.enabled!=='boolean'||typeof data.contributions_enabled!=='boolean'||typeof data.generation_enabled!=='boolean')throw new Error('Invalid family memory capabilities');
    caps=data;capsIdentity=identity;return data;
  }
  async function attach(container,nextTarget){
    if(!container||!nextTarget)return;
    const s=scopeNow();if(!s?.account||!s?.library||s.locked){clear();return;}
    pruneConversationHints(s.account,s.library,membershipRevision(s));
    if(!(validStoryTarget(nextTarget)||validBookTarget(nextTarget)))throw new TypeError('Invalid family memory target');
    const fingerprint=targetScopeFingerprint(accountKey(s),nextTarget);
    roots.add(container);
    if(fingerprint===targetFingerprint&&mount?.parentNode===container&&membershipRevision(currentScope)===membershipRevision(s))return;
    resetEditorialContextChoice();
    clearEditionReview();clearSavedEditions();
    if(planPanelNode){planPanelNode.replaceChildren();planPanelNode.hidden=true;}planData=null;planPanelNode=null;planButton=null;
    attachmentId=String(++attachmentSequence);panelId=`memory-community-${instanceId}-${attachmentId}-panel`;
    const priorJob=activeJob?.id,priorJobState=activeJob?.state,priorScope=currentScope,priorLibraryChanged=priorScope&&accountKey(priorScope)!==accountKey(s);
    if(priorLibraryChanged){bookEpoch++;editorialGeneration++;bookEditSequence++;editorialModel=null;editorialPending=null;editorialBusyOwner='';for(const controller of bookControllers)controller.abort();bookControllers.clear();for(const shelf of bookContainers){shelf.hidden=true;shelf.replaceChildren();}booksList=[];storyOptions=[];storyPage=0;storyOptionsHasMore=false;bookStorySelection=new Set();bookTitleDraft='';bookIntroDraft='';bookEditorOpen=false;bookPage=1;booksHasMore=false;pendingBook=null;bookSubmittingOwner='';selectedBook=null;caps=null;capsIdentity='';voiceCapabilitiesOwner='';voiceCapabilitiesValue=null;voiceCapabilitiesPending=null;}
    clearReplySpeech();clearChatComposition();clearIdeaComposition();epoch++;stopFamilyListening();stopRequests();stopPoll();void clearCapture(false);void clearChatCapture();void clearIdeaVoice(true);chatTranscript='';chatVoiceError='';conversationRestorationNotice=false;forgetUrls();
    targetFingerprint=fingerprint;currentScope={account:s.account,library:s.library,membership_revision:membershipRevision(s)};target={...nextTarget};conversationRestorationNotice=false;memoirFormChoice='existing';
    planData=null;planPanelNode=null;planButton=null;
    invalidateChatRecovery();contributionList=[];contributionDetails.clear();canReview=false;canDelete=false;contributionPage=1;contributionsHasMore=false;conversation=null;conversationList=[];conversationDrafts.clear();conversationSelectionEpoch++;conversationLoading=false;conversationCreating=false;conversationDeleting=false;conversationCreateToken=null;conversationDeleteToken=null;conversationLoadToken=null;turns=[];turnPage=1;turnsHasMore=false;turnsBusyToken=null;assistantInflightToken=null;recentTurn=null;messageDraft=null;chatTextDraft='';contributionDraft={mode:'text',text:'',byline:'',chapter_id:'',consent:false};ideaDraft='';memoirFormChoice='existing';activeJob=null;pendingJob=null;pendingContribution=null;recording=null;
    renderShell(container);
    if(priorJob&&['queued','running'].includes(priorJobState)&&priorScope&&accountKey(s)===JSON.stringify([priorScope.account,priorScope.library]))void request(`${API}/jobs/${priorJob}`,{method:'DELETE'}).catch(()=>{});
    const ticket=epoch,owner=accountKey(s);
    try {
      const capability=await ensureCapabilities();if(!current(ticket,owner))return;
      if(!capability.enabled){mount.dataset.state='disabled';panelNode.replaceChildren(el('p',t('disabled')));return;}
      if(target.type==='memoir')void loadSavedEditions(ticket,owner);
      if(target.type==='memoir'&&!capability.generation_enabled){mount.dataset.state='readonly';mount.querySelector('.memory-community-heading')?.remove();mount.querySelector('.memory-community-tabs')?.remove();panelNode.setAttribute('role','region');panelNode.setAttribute('aria-label',lang()==='zh'?'回忆录阅读提示':'Memoir reading information');renderMemoirSummary(panelNode,target);return;}
      if(!visibleTabs().length){mount.dataset.state='disabled';panelNode.replaceChildren(el('p',t('disabled')));return;}
      mount.dataset.state='ready';renderTabs();
      let restoredConversation=false;if(capability.generation_enabled)restoredConversation=await resumeConversation(ticket,owner);
      if(!current(ticket,owner))return;
      await renderPanel();
      if(restoredConversation&&current(ticket,owner)){conversationRestorationNotice=true;showStatus(t('conversationRestored'),'success');}
    } catch(error){if(current(ticket,owner)){mount.dataset.state='unavailable';panelNode.replaceChildren(el('p',t('unavailable')));notifyError(error);}}
    listenVisibility();
  }
  function listenVisibility(){
    if(visibilityHandler)return;
    visibilityHandler=()=>{
      jobVisibilityEpoch++;
      if(document.hidden){
        clearReplySpeech();clearChatComposition();clearIdeaComposition();stopFamilyListening();
        if(savedEditionState){const state=savedEditionState;clearSavedEditionSource(state,{resetList:true,status:'idle'});renderSavedEditionShelf(state,epoch,accountKey(scopeNow()));}
        forgetUrls();stopPoll();stopRequests(true);void clearCapture(false);void clearChatCapture();void clearIdeaVoice(true);chatTranscript='';chatVoiceError='';
        // Leaving the foreground ends local audio and checks, not submitted work.
        // Explicit cancellation and reader/scope disposal retain their own rules.
      }else if(!scopeNow()?.locked){
        if(target)void resumeVisibleWork();
        for(const shelf of bookContainers)void books(shelf);
      }
    };
    document.addEventListener('visibilitychange',visibilityHandler);
  }
  async function resumeVisibleWork(){
    const ticket=epoch,owner=accountKey(scopeNow()),visibility=jobVisibilityEpoch;
    await renderPanel();
    if(document.hidden||visibility!==jobVisibilityEpoch||!current(ticket,owner))return;
    if(activeJob?.id&&['queued','running'].includes(activeJob.state))await pollJob(ticket,owner,true);
    else if(conversation&&pendingChatTurns().length)await recoverPendingChatJob(ticket,owner);
  }
  function unloadVisibility(){if(visibilityHandler){document.removeEventListener('visibilitychange',visibilityHandler);visibilityHandler=null;}}
  async function renderPanel(){
    if(!panelNode||!target)return;if(scopeNow()?.locked){clearReplySpeech();return;}
    stopFamilyListening();forgetUrls();
    // Translation/visibility refresh must preserve negotiated feature gates.
    // A read-only memoir never becomes a story-specific contribution form.
    if(!caps?.enabled){clearReplySpeech();panelNode.replaceChildren(el('p',t('disabled')));return;}
    if(target.type==='memoir'&&!caps.generation_enabled){clearReplySpeech();renderMemoirSummary(panelNode,target);return;}
    if(!visibleTabs().length){clearReplySpeech();panelNode.replaceChildren(el('p',t('disabled')));return;}
    if(!visibleTabs().includes(activeTab))activeTab=visibleTabs()[0];
    const ticket=epoch,owner=accountKey(scopeNow());
    if(activeTab==='ideas'&&editionReview?.composing){editionReview.renderDeferred=true;return;}
    if(activeTab==='ideas'&&ideaCompositionCurrent(ideaComposition)&&(!ideaComposition.endSeen||!ideaComposition.finalInput)){ideaRenderDeferred=true;return;}
    if(activeTab==='chat'&&compositionCurrent(chatComposition)){
      assignComposedChatValue(chatComposition);
      chatRenderDeferred={ticket,owner,target,fingerprint:targetFingerprint,tab:activeTab,renderId:panelRenderEpoch};
      announceChatJob();return;
    }
    invalidateEditorialContextPreflight();
    const host=panelNode,renderId=++panelRenderEpoch,renderTarget=target,renderFingerprint=targetFingerprint,renderTab=activeTab,root=el('section','','memory-community-panel');
    const reader=renderTab==='chat'?mount?.closest?.('dialog'):null;
    const oldInput=renderTab==='chat'&&host.contains?.(document.activeElement)&&document.activeElement.matches?.('.memory-community-form textarea[name="message"]')?document.activeElement:null;
    const focusSnapshot=oldInput?{input:oldInput,start:oldInput.selectionStart,end:oldInput.selectionEnd,direction:oldInput.selectionDirection}:null;
    const oldIdeaInput=renderTab==='ideas'&&host.contains?.(document.activeElement)&&(document.activeElement.matches?.('.memory-community-ideas-instructions')||document.activeElement.matches?.('.memory-community-ideas-transcript'))?document.activeElement:null;
    const ideaFocusSnapshot=oldIdeaInput?{input:oldIdeaInput,start:oldIdeaInput.selectionStart,end:oldIdeaInput.selectionEnd,direction:oldIdeaInput.selectionDirection}:null;
    let userMovedReader=false;const noteReaderInput=event=>{if(event?.type==='keydown'&&event.target===oldInput)return;userMovedReader=true;};
    const readerScroll=focusSnapshot&&reader?reader.scrollTop:null;
    if(focusSnapshot&&reader)for(const type of ['wheel','touchmove','pointerdown','keydown'])reader.addEventListener(type,noteReaderInput,{capture:true,passive:true});
    clearReplySpeech();panelNode.replaceChildren(root);if(focusSnapshot&&reader&&readerScroll!==null)reader.scrollTop=readerScroll;
    if(renderTab!=='chat'){chatAnnouncementKey='';showStatus('');}else announceChatJob();
    try{
      if(renderTab==='voice')await renderVoices(root,ticket,owner);
      else if(renderTab==='chat')await renderChat(root,ticket,owner,renderId);
      else if(renderTab==='ideas')await renderIdeas(root,ticket,owner);
    }finally{
      if(focusSnapshot&&reader)for(const type of ['wheel','touchmove','pointerdown','keydown'])reader.removeEventListener(type,noteReaderInput,true);
    }
    if(!current(ticket,owner)||panelRenderEpoch!==renderId||target!==renderTarget||targetFingerprint!==renderFingerprint||activeTab!==renderTab||panelNode!==host||root.parentNode!==host)return;
    if(ideaFocusSnapshot){const next=root.querySelector(ideaFocusSnapshot.input.className.split(/\s+/).includes('memory-community-ideas-transcript')?'.memory-community-ideas-transcript':'.memory-community-ideas-instructions');if(next&&(document.activeElement===document.body||document.activeElement===oldIdeaInput)){next.focus({preventScroll:true});try{next.setSelectionRange(Math.min(ideaFocusSnapshot.start,next.value.length),Math.min(ideaFocusSnapshot.end,next.value.length),ideaFocusSnapshot.direction);}catch(_){}}return;}
    if(!focusSnapshot||activeTab!=='chat')return;
    const nextInput=root.querySelector('.memory-community-form textarea[name="message"]');
    if(reader&&reader.isConnected&&!userMovedReader)reader.scrollTop=readerScroll;
    if(!nextInput||!(document.activeElement===document.body||document.activeElement===oldInput))return;
    nextInput.focus({preventScroll:true});
    try{nextInput.setSelectionRange(Math.min(focusSnapshot.start,nextInput.value.length),Math.min(focusSnapshot.end,nextInput.value.length),focusSnapshot.direction);}catch(_){}
  }
  function renderMemoirSummary(container,_book){const box=el('section','','memory-community-memoir-summary');box.append(el('p',t('memoirSummary'),'memory-community-help'));container.replaceChildren(box);}
  function announceChatJob(){
    const job=activeTab==='chat'&&activeJob?.kind==='chat'?activeJob:null;
    if(!job){if(chatAnnouncementKey){chatAnnouncementKey='';showStatus('');}return;}
    const key=`${job.id}:${job.state}:${lang()}`;if(key===chatAnnouncementKey)return;chatAnnouncementKey=key;
    const message={queued:'chatQueued',running:'chatRunning',ready:'chatReady',failed:'chatFailed',cancelled:'chatCancelled',stale:'stale'}[job.state];
    if(message)showStatus(t(message),['failed','stale'].includes(job.state)?'error':'');
  }
  const planCount=value=>Number.isSafeInteger(value)&&value>=0;
  const EDITORIAL_CONTEXT_PROFILE='memoir_editorial_v1';
  const safePlanTitle=value=>safeText(value,640)&&[...value].length<=160;
  function validPlanCapacity(value){
    if(!value||!['within_limits','smaller_scope_required'].includes(value.state)||typeof value.can_draft!=='boolean')return false;
    if(value.state==='smaller_scope_required')return value.can_draft===false&&value.source_count===null&&value.source_kinds===null;
    if(!planCount(value.source_count)||value.source_count>96||!value.source_kinds||typeof value.source_kinds!=='object'||Array.isArray(value.source_kinds))return false;
    const kinds=['family','transcript','editorial','ai','metadata'];let total=0;
    for(const [kind,count] of Object.entries(value.source_kinds)){if(!kinds.includes(kind)||!Number.isSafeInteger(count)||count<1||count>96)return false;total+=count;}
    return total===value.source_count;
  }
  function validBookPlan(value,bookId,revision,stories,editorialContext=false){
    if(!value||value.version!==1||value.target_type!=='book'||value.target_id!==bookId||String(value.revision)!==String(revision)||
      typeof value.can_edit!=='boolean'||value.kind!=='saved_structure_plan'||value.generated!==false||value.queued!==false||value.needs_review!==true||
      !Number.isSafeInteger(value.story_count)||value.story_count<1||value.story_count>24||!Number.isSafeInteger(value.chapter_count)||value.chapter_count<1||value.chapter_count>144||
      !Number.isSafeInteger(value.item_count)||value.item_count<1||value.item_count>576||!value.limits||value.limits.chapters!==24||value.limits.sources!==96||value.limits.context_bytes!==65536||
      !validPlanCapacity(value.whole)||!Array.isArray(value.sections)||value.sections.length!==value.story_count||!Array.isArray(stories)||stories.length!==value.story_count)return false;
    if(editorialContext&&(value.context_profile!==EDITORIAL_CONTEXT_PROFILE||
      value.whole.state==='within_limits'&&(!Number.isSafeInteger(value.whole.context_bytes)||value.whole.context_bytes<1||value.whole.context_bytes>65536)||
      value.whole.state==='smaller_scope_required'&&value.whole.context_bytes!==null))return false;
    let chapters=0,items=0;const seen=new Set();
    for(let index=0;index<value.sections.length;index++){
      const section=value.sections[index];
      const currentStory=stories[index];
      if(!section||section.position!==index+1||!uuidOK(section.id)||section.id!==currentStory?.id||seen.has(section.id)||String(section.revision)!==String(currentStory?.revision)||!/^([1-9][0-9]*)$/.test(String(section.revision))||!safePlanTitle(section.title)||
        !planCount(section.item_count)||section.item_count>24||typeof section.can_edit!=='boolean'||!validPlanCapacity(section)||!Array.isArray(section.chapters)||section.chapters.length<1||section.chapters.length>6)return false;
      seen.add(section.id);items+=section.item_count;chapters+=section.chapters.length;
      for(let chapterIndex=0;chapterIndex<section.chapters.length;chapterIndex++){const chapter=section.chapters[chapterIndex];if(!chapter||chapter.id!==`chapter-${chapterIndex+1}`||!safePlanTitle(chapter.title)||!planCount(chapter.item_count)||chapter.item_count>4)return false;}
    }
    return chapters===value.chapter_count&&items===value.item_count;
  }
  function renderPlanCapacity(root,capacity){
    root.append(el('p',`${t(capacity.state==='within_limits'?'planWithin':'planSmaller')} · ${t(capacity.can_draft?'planEligible':'planNotEligible')}`,'memory-book-plan-capacity'));
    renderPlanKinds(root,capacity);
  }
  function renderPlanKinds(root,capacity){
    if(capacity.source_count===null){root.append(el('p',t('planCountsUnavailable'),'memory-community-help'));return;}
    const rows=Object.entries(capacity.source_kinds).map(([kind,count])=>`${t(`planKind_${kind}`)} ${count}`);
    root.append(el('p',rows.length?rows.join(' · '):t('planEmptyKinds'),'memory-book-plan-kinds'));
  }
  function renderBookPlan(data,bookId,revision,ticket,owner){
    if(!planPanelNode||!current(ticket,owner)||target?.type!=='memoir'||target.id!==bookId||String(target.revision)!==String(revision))return;
    const view=el('div','','memory-book-plan-document'),storyOpenButtons=[];let openingStory=false;view.append(el('p',t('planIntro'),'memory-community-help'));
    view.append(el('p',`${t('planStories')(data.story_count)} · ${t('planChapters')(data.chapter_count)} · ${t('planItems')(data.item_count)}`,'memory-book-plan-totals'));
    const overall=el('section','','memory-book-plan-overall');overall.append(el('h3',t('planWhole')));renderPlanCapacity(overall,data.whole);
    if(data.whole.state==='smaller_scope_required')overall.append(el('p',t('planLargeHelp'),'memory-book-plan-large-help'));
    view.append(overall);
    const sections=el('ol','','memory-book-plan-sections');
    for(const section of data.sections){
      const row=el('li','','memory-book-plan-story');row.append(el('h3',`${section.position}. ${section.title}`));
      row.append(el('p',`${t('planItems')(section.item_count)} · ${t(section.state==='within_limits'?'planWithin':'planSmaller')} · ${t(section.can_draft?'planEligible':'planNotEligible')}`,'memory-book-plan-story-meta'));
      const chapters=el('ol','','memory-book-plan-chapters');for(const chapter of section.chapters)chapters.append(el('li',`${chapter.title} · ${t('planItems')(chapter.item_count)}`));row.append(chapters);
      renderPlanKinds(row,section);
      const status=el('p','','memory-book-plan-open-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
      const open=btn(t('planOpenStory'),async()=>{
        const isCurrent=()=>current(ticket,owner)&&target?.type==='memoir'&&target.id===bookId&&String(target.revision)===String(revision);
        if(!isCurrent())return;
        if(openingStory)return;
        if(typeof onOpenBookStory!=='function'){status.textContent=t('planOpenUnavailable');return;}
        openingStory=true;for(const control of storyOpenButtons)control.disabled=true;status.textContent=t('planOpeningStory');
        const context={book_id:bookId,book_revision:String(revision),story_id:section.id,story_revision:String(section.revision)};
        try{const opened=await onOpenBookStory(context);if(isCurrent()&&opened!==true)status.textContent=t('planOpenUnavailable');else if(isCurrent())status.textContent='';}
        catch{if(isCurrent())status.textContent=t('planOpenUnavailable');}
        finally{openingStory=false;if(isCurrent())for(const control of storyOpenButtons)control.disabled=false;}
      },'memory-book-plan-open-story');storyOpenButtons.push(open);row.append(open,status);
      sections.append(row);
    }
    view.append(sections);
    const refresh=btn(t('refreshPlan'),()=>void fetchBookPlan(),'memory-book-plan-refresh');view.prepend(refresh);planPanelNode.replaceChildren(view);
  }
  async function fetchBookPlan(){
    if(target?.type!=='memoir'||!planPanelNode||planPanelNode.hidden||scopeNow()?.locked)return;
    const bookId=target.id,revision=String(target.revision),ticket=epoch,owner=accountKey(scopeNow()),library=scopeNow().library;
    planData=null;planPanelNode.replaceChildren(el('p',t('planLoading'),'memory-book-plan-loading'));showPlan(true);
    const panel=planPanelNode,button=planButton;
    try{
      const result=await api(`${API}/books/${encodeURIComponent(bookId)}/plan?library=${encodeURIComponent(library)}`);
      if(!current(ticket,owner)||target?.type!=='memoir'||target.id!==bookId||String(target.revision)!==revision){if(planPanelNode===panel&&planButton===button&&accountKey(scopeNow())!==owner)invalidateBookPlan(panel,button);return;}
      if(!validBookPlan(result,bookId,revision,target.stories))throw new Error('Invalid or stale memoir plan');
      planData={bookId,revision,owner,data:result};renderBookPlan(result,bookId,revision,ticket,owner);
    }catch(error){
      if(!current(ticket,owner)||target?.type!=='memoir'||target.id!==bookId||String(target.revision)!==revision){if(accountKey(scopeNow())!==owner)invalidateBookPlan(panel,button);return;}
      planPanelNode.replaceChildren(el('p',t('planUnavailable'),'memory-book-plan-error'),btn(t('refreshPlan'),()=>void fetchBookPlan(),'memory-book-plan-refresh'));notifyError(error);
    }
  }
  function invalidateBookPlan(panel,button){if(panel&&button&&panel===planPanelNode){planData=null;panel.replaceChildren();panel.hidden=true;button.disabled=true;button.hidden=true;}}
  function showPlan(open){if(!planPanelNode||!planButton)return;planPanelNode.hidden=!open;planButton.setAttribute('aria-expanded',String(open));planButton.textContent=t(open?'hidePlan':'viewPlan');}
  async function toggleBookPlan(){
    if(!planPanelNode||target?.type!=='memoir'||scopeNow()?.locked)return;
    if(accountKey(scopeNow())!==JSON.stringify([currentScope?.account,currentScope?.library])){invalidateBookPlan(planPanelNode,planButton);return;}
    if(!planPanelNode.hidden){showPlan(false);return;}
    showPlan(true);const bookId=target.id,revision=String(target.revision);
    if(planData?.bookId===bookId&&planData.revision===revision&&planData.owner===accountKey(scopeNow())){renderBookPlan(planData.data,bookId,revision,epoch,accountKey(scopeNow()));return;}
    await fetchBookPlan();
  }
  function editorialContextKey(){return target?.type==='memoir'?JSON.stringify([accountKey(scopeNow()),target.id,String(target.revision)]):'';}
  function editorialContextSelected(){return Boolean(editorialContextChoice?.enabled===true&&editorialContextChoice.profile===EDITORIAL_CONTEXT_PROFILE&&editorialContextChoice.key===editorialContextKey());}
  function resetEditorialContextChoice(){editorialContextGeneration++;editorialContextChoice=null;editorialContextPreflight=null;editorialContextNeedsDecisionKey='';editorialContextBasicConfirmedKey='';editorialContextDecisionStatusKey='';}
  const editorialContextNeedsDecision=()=>Boolean(editorialContextNeedsDecisionKey&&editorialContextNeedsDecisionKey===editorialContextKey()&&editorialContextBasicConfirmedKey!==editorialContextKey());
  function requireEditorialContextDecision(statusKey='editorialContextChoose'){
    editorialContextGeneration++;editorialContextChoice=null;editorialContextPreflight=null;
    editorialContextNeedsDecisionKey=editorialContextKey();editorialContextBasicConfirmedKey='';editorialContextDecisionStatusKey=statusKey;
  }
  function invalidateEditorialContextPreflight(){
    if(!editorialContextPreflight)return;
    requireEditorialContextDecision('editorialContextChoose');
  }
  function editorialContextUiBusy(kind){
    if(editorialContextPreflight||assistantInflightToken||pendingJob||messageDraft||chatRecordingBusy||chatCaptureStarting||chatCaptureHandle||chatTranscribing||chatTranscript||ideaVoicePending())return true;
    if(kind==='chat'&&(conversationLoading||conversationCreating||conversationDeleting||activeJob?.kind==='chat'&&['queued','running'].includes(activeJob.state)||hasPendingChatWork()))return true;
    if(kind==='ideas'&&activeJob?.kind==='narrative'&&['queued','running'].includes(activeJob.state))return true;
    return false;
  }
  function renderEditorialContextChoice(form,kind,ticket,owner){
    if(target?.type!=='memoir')return null;
    const frozen=kind==='chat'?messageDraft?.editorialContext:pendingJob?.editorialContext;
    const selected=typeof frozen==='boolean'?frozen:editorialContextSelected();
    const fieldset=el('fieldset','','memory-editorial-context-choice');
    const label=el('label','','memory-editorial-context-label'),checkbox=el('input');
    checkbox.type='checkbox';checkbox.className='memory-editorial-context-toggle';checkbox.name='editorial_context';checkbox.checked=selected;
    const statusText=selected?t('editorialContextReady'):editorialContextBasicConfirmedKey===editorialContextKey()?t('editorialContextBasicConfirmed'):editorialContextNeedsDecision()?t(editorialContextDecisionStatusKey||'editorialContextChoose'):'';
    const status=el('p',statusText,'memory-editorial-context-status');status.id=`memory-editorial-context-status-${instanceId}-${attachmentId}-${panelRenderEpoch}-${kind}`;status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    const help=el('p',t('editorialContextHelp'),'memory-community-help');help.id=`memory-editorial-context-help-${instanceId}-${attachmentId}-${panelRenderEpoch}-${kind}`;
    const basicButton=btn(t('editorialContextContinueBasic'),()=>{if(!editorPanelCurrent()||!editorialContextNeedsDecision())return;editorialContextBasicConfirmedKey=editorialContextKey();status.textContent=t('editorialContextBasicConfirmed');basicButton.hidden=true;sync();},'memory-community-button memory-editorial-context-basic');basicButton.type='button';basicButton.hidden=!editorialContextNeedsDecision();
    const control={checkbox,status,sync:null,recordButton:null};
    label.append(checkbox,el('span',t('editorialContextLabel')));
    checkbox.setAttribute('aria-describedby',`${help.id} ${status.id}`);
    fieldset.append(label,help,status,basicButton);form.append(fieldset);
    const sync=()=>{
      checkbox.disabled=editorialContextUiBusy(kind)||Boolean(frozen!==undefined);
      basicButton.hidden=!editorialContextNeedsDecision()||Boolean(frozen!==undefined);
      const submit=form.querySelector('button[type="submit"]');
      if(submit){const choiceChecking=Boolean(editorialContextPreflight);submit.disabled=choiceChecking||editorialContextNeedsDecision()||Boolean(assistantInflightToken)||kind==='chat'&&Boolean(conversationLoading||conversationCreating||conversationDeleting||!messageDraft&&hasPendingChatWork())||kind==='ideas'&&(!canEdit()||ideaVoicePending());}
    };
    checkbox.disabled=editorialContextUiBusy(kind)||Boolean(frozen!==undefined);
    checkbox.addEventListener('change',()=>{
      if(!editorPanelCurrent())return;
      if(checkbox.disabled){checkbox.checked=selected;return;}
      if(!checkbox.checked){const wasSelected=editorialContextSelected();resetEditorialContextChoice();if(wasSelected){editorialContextNeedsDecisionKey=editorialContextKey();editorialContextBasicConfirmedKey=editorialContextKey();status.textContent=t('editorialContextBasicConfirmed');}else status.textContent='';sync();return;}
      void preflightEditorialContext({checkbox,status,basicButton,recordButton:control.recordButton,form,kind,ticket,owner,targetAtRender:target,
        fingerprint:targetFingerprint,conversationAtRender:conversation,selectionAtRender:conversationSelectionEpoch,
        tabAtRender:activeTab,root:panelNode?.querySelector('.memory-community-panel')});
    });
    function editorPanelCurrent(){return current(ticket,owner)&&target?.type==='memoir'&&fieldset.isConnected!==false&&activeTab===kindTab(kind);}
    sync();control.sync=sync;return control;
  }
  function kindTab(kind){return kind==='chat'?'chat':'ideas';}
  function preflightCurrent(state){return editorialContextPreflight===state&&state.generation===editorialContextGeneration&&current(state.ticket,state.owner)&&target===state.targetAtRender&&targetFingerprint===state.fingerprint&&conversation===state.conversationAtRender&&conversationSelectionEpoch===state.selectionAtRender&&activeTab===state.tabAtRender&&state.checkbox.isConnected!==false&&state.form.isConnected!==false&&state.root?.parentNode===panelNode;}
  async function preflightEditorialContext(state){
    const generation=++editorialContextGeneration;state.generation=generation;editorialContextPreflight=state;state.checkbox.checked=false;state.status.textContent=t('editorialContextChecking');state.checkbox.disabled=true;
    const submit=state.form.querySelector('button[type="submit"]');if(submit)submit.disabled=true;const instructions=state.kind==='ideas'?state.form.querySelector('.memory-community-ideas-instructions'):null,formSelect=state.kind==='ideas'?state.form.querySelector('select[name="memoir_form"]'):null;if(instructions)instructions.disabled=true;if(formSelect)formSelect.disabled=true;
    if(state.recordButton)state.recordButton.disabled=true;
    try{
      const library=scopeNow()?.library;
      const path=`${API}/books/${encodeURIComponent(state.targetAtRender.id)}/plan?library=${encodeURIComponent(library)}&editorial_context=1`;
      const result=await api(path);
      if(!preflightCurrent(state))return;
      if(!validBookPlan(result,state.targetAtRender.id,String(state.targetAtRender.revision),state.targetAtRender.stories,true))throw Object.assign(new Error('Invalid memoir editorial context plan'),{contextInvalid:true});
      if(result.whole.state!=='within_limits'||!Number.isSafeInteger(result.whole.context_bytes)||result.whole.context_bytes<1||result.whole.context_bytes>65536){state.checkbox.checked=false;editorialContextNeedsDecisionKey=editorialContextKey();editorialContextBasicConfirmedKey='';editorialContextDecisionStatusKey='editorialContextSmaller';state.status.textContent=t('editorialContextSmaller');state.basicButton.hidden=false;return;}
      editorialContextChoice={key:editorialContextKey(),profile:EDITORIAL_CONTEXT_PROFILE,enabled:true};editorialContextNeedsDecisionKey='';editorialContextBasicConfirmedKey='';editorialContextDecisionStatusKey='';state.checkbox.checked=true;state.status.textContent=t('editorialContextReady');state.basicButton.hidden=true;
    }catch(error){
      if(!preflightCurrent(state))return;
      state.checkbox.checked=false;editorialContextNeedsDecisionKey=editorialContextKey();editorialContextBasicConfirmedKey='';editorialContextDecisionStatusKey=error?.status===409?'editorialContextChanged':error?.status===422?'editorialContextSmaller':'editorialContextUnavailable';state.basicButton.hidden=false;
      state.status.textContent=t(editorialContextDecisionStatusKey);
      notifyError(error);
    }finally{
      if(editorialContextPreflight===state){editorialContextPreflight=null;if(state.checkbox.isConnected!==false){state.checkbox.disabled=editorialContextUiBusy(state.kind)||Boolean(state.kind==='chat'?messageDraft:pendingJob);const button=state.form.querySelector('button[type="submit"]');if(button)button.disabled=Boolean(editorialContextNeedsDecision()||assistantInflightToken||state.kind==='chat'&&(conversationLoading||conversationCreating||conversationDeleting||!messageDraft&&hasPendingChatWork())||state.kind==='ideas'&&ideaVoicePending());state.basicButton.hidden=!editorialContextNeedsDecision();if(state.recordButton)state.recordButton.disabled=chatCaptureStartBlocked();if(state.kind==='ideas'){if(instructions)instructions.disabled=Boolean(pendingJob||ideaCaptureStarting||ideaCaptureHandle||ideaTranscribing);if(formSelect)formSelect.disabled=Boolean(pendingJob||ideaVoicePending());if(ideaRecordButton&&ideaRecordButton.isConnected!==false)ideaRecordButton.disabled=chatCaptureStartBlocked()||Boolean(ideaTranscript||ideaTranscribing||pendingJob);}}}
    }
  }
  function renderVoices(root,ticket,owner){
    root.append(el('p',t('voiceHelp'),'memory-community-help'),el('p',t('voiceRetention'),'memory-community-retention'));
    const composer=el('details','','memory-community-composer'),summary=el('summary',t('composeMemory'),'memory-community-composer-summary');
    composer.open=Boolean(pendingContribution||recording||captureHandle||captureStarting||contributionDraft.text||contributionDraft.byline||contributionDraft.chapter_id||contributionDraft.consent);
    composer.append(summary);composer.addEventListener('toggle',()=>{if(!current(ticket,owner)||panelNode?.querySelector('.memory-community-composer')!==composer)return;if(composer.open)return;if(recording||pendingContribution){composer.open=true;return;}if(captureStarting||captureHandle)void clearCapture(false);});
    const tabs=el('div','','memory-community-subtabs');
    const written=btn(t('textTab'),()=>{tabs.dataset.mode='text';form.dataset.mode='text';contributionDraft.mode='text';textLabel.hidden=false;fileLabel.hidden=true;void clearCapture(false);save.textContent=t('save');},'memory-community-subtab');
    const audio=btn(t('audioTab'),()=>{tabs.dataset.mode='audio';form.dataset.mode='audio';contributionDraft.mode='audio';textLabel.hidden=true;fileLabel.hidden=false;save.textContent=t('save');syncContributionCaptureForm();},'memory-community-subtab');
    tabs.append(written,audio);tabs.dataset.mode=contributionDraft.mode||'text';composer.append(tabs);
    const form=el('form','','memory-community-form');captureForm=form;form.dataset.mode=contributionDraft.mode||'text';form.addEventListener('submit',event=>{event.preventDefault();void saveContribution(form,ticket,owner);});
    const chapterLabel=el('label',t('chapter'));const chapter=el('select');chapter.name='chapter_id';const whole=el('option',t('whole'));whole.value='';chapter.append(whole);for(const item of chapterOptions()){const option=el('option',item.title||item.id);option.value=item.id;chapter.append(option);}chapter.value=contributionDraft.chapter_id;chapter.addEventListener('change',()=>contributionDraft.chapter_id=chapter.value);chapterLabel.append(chapter);
    const textLabel=el('label',t('text'));const text=el('textarea');text.name='text';text.maxLength=8192;text.rows=4;text.value=contributionDraft.text;text.addEventListener('input',()=>contributionDraft.text=text.value);textLabel.append(text);
    const bylineLabel=el('label',t('byline'));const byline=el('input');byline.name='byline';byline.maxLength=256;byline.value=contributionDraft.byline;byline.addEventListener('input',()=>contributionDraft.byline=byline.value);bylineLabel.append(byline);
    const consentLabel=el('label');const consent=el('input');consent.type='checkbox';consent.name='consent';consent.value='1';consent.checked=contributionDraft.consent;consent.addEventListener('change',()=>contributionDraft.consent=consent.checked);consentLabel.append(consent,el('span',t('consent')));
    const fileLabel=el('label',t('file'));const file=el('input');file.type='file';file.name='file';file.accept='.wav,audio/wav';fileLabel.append(file);
    const recordButton=btn(t('record'),()=>void beginCapture(ticket,owner,form),'memory-community-button');recordButton.dataset.captureRecord='true';
    const keepButton=btn(t('stop'),()=>void clearCapture(true),'memory-community-button');keepButton.dataset.captureStop='true';keepButton.hidden=true;
    const cancelButton=btn(t('cancelRecord'),()=>void clearCapture(false),'memory-community-button');cancelButton.dataset.captureCancel='true';cancelButton.hidden=true;
    const processing=el('p',caps?.generation_enabled?t('voiceRetention'):t('processingOff'),'memory-community-help');
    const save=el('button',t('save'));save.type='submit';save.className='memory-community-primary';
    const retry=btn(t('retry'),()=>void retryContribution(form,ticket,owner),'memory-contribution-retry');retry.hidden=true;
    fileLabel.hidden=true;recordButton.hidden=true;
    const recordingStatus=el('p','','memory-recording-status');recordingStatus.setAttribute('role','status');recordingStatus.hidden=true;
    form.append(chapterLabel,textLabel,bylineLabel,consentLabel,fileLabel,recordButton,keepButton,cancelButton,recordingStatus,processing,save,retry);composer.append(form);root.append(composer);
    const feed=el('div','','memory-community-contributions');root.append(feed);
    textLabel.hidden=form.dataset.mode==='audio';fileLabel.hidden=form.dataset.mode!=='audio';recordButton.hidden=form.dataset.mode!=='audio'||!capture;
    if(pendingContribution)setContributionPendingUI(form,true);
    if(pendingContribution){text.value=pendingContribution.body.text;byline.value=pendingContribution.body.byline;chapter.value=pendingContribution.body.chapter_id;consent.checked=pendingContribution.body.consent==='1';form.dataset.mode=pendingContribution.body.kind==='audio'?'audio':'text';textLabel.hidden=form.dataset.mode==='audio';fileLabel.hidden=form.dataset.mode!=='audio';recordButton.hidden=true;}
    if(!caps?.generation_enabled)processing.hidden=false;else processing.hidden=true;
    syncContributionCaptureForm();
    renderContributions(feed,ticket,owner);
    return loadContributions(feed,ticket,owner);
  }
  function renderFamilyListening(feed,ticket,owner){
    const queue=contributionList.filter(item=>item?.kind==='audio'&&item.state==='accepted'&&uuidOK(item.id)).slice(0,16);
    if(!queue.length)return;
    const section=el('section','','memory-family-listening'),status=el('p','','memory-family-listening-status'),playerBox=el('div','','memory-family-listening-player'),controls=el('div','','memory-family-listening-controls');
    const startButton=btn(t('listenFamily'),()=>{
      if(familyListening||document.hidden||!current(ticket,owner)||!section.parentNode)return;
      if(isCapturing()){showStatus(t('audioDuringRecording'));return;}
      stopPlayback();notifyAudioStart();
      const session={token:++familyListenEpoch,ticket,owner,queue,section,status,playerBox,controls,startButton,player:null,url:null,index:-1,started:true,loading:false};familyListening=session;void loadFamilyTrack(session,0);
    });
    status.setAttribute('role','status');section.setAttribute('aria-label',t('listenFamily'));section.append(el('p',t('listeningHelp'),'memory-family-listening-help'),status,playerBox,controls);controls.append(startButton);feed.append(section);
  }
  function listeningCurrent(session){return familyListening===session&&session.token===familyListenEpoch&&session.started&&!document.hidden&&current(session.ticket,session.owner)&&Boolean(session.section?.parentNode);}
  function clearListeningTrack(session){clearPlayer(session.player);session.player=null;if(session.url){objectUrls.delete(session.url);URL.revokeObjectURL(session.url);session.url=null;}session.playerBox.replaceChildren();}
  async function loadFamilyTrack(session,index){
    if(!listeningCurrent(session)||session.loading||index<0||index>=session.queue.length)return;
    clearListeningTrack(session);session.index=index;session.loading=true;const item=session.queue[index];
    session.status.textContent=t('listeningPosition')(index+1,session.queue.length,item.byline||t('familyMember'));
    session.controls.replaceChildren(btn(t('stopListening'),()=>stopFamilyListening()));
    try{
      const blob=await api(`${pathStory()}/${item.id}/audio`,{responseType:'blob'});
      if(!listeningCurrent(session))return;
      if(!await validWav(blob)||!listeningCurrent(session))throw new Error('Invalid protected family recording');
      const url=URL.createObjectURL(blob);if(!listeningCurrent(session)){URL.revokeObjectURL(url);return;}
      objectUrls.add(url);session.url=url;
      const player=el('audio');player.controls=true;player.src=url;session.player=player;session.playerBox.replaceChildren(player);
      player.addEventListener('play',()=>{if(listeningCurrent(session)&&session.player===player)notifyAudioStart();});
      player.addEventListener('ended',()=>{if(!listeningCurrent(session)||session.player!==player)return;if(index+1<session.queue.length)void loadFamilyTrack(session,index+1);else stopFamilyListening(t('listeningComplete'));});
      player.addEventListener('error',()=>{if(listeningCurrent(session)&&session.player===player)stopFamilyListening(t('listeningFailed'));});
      const next=btn(t('nextRecording'),()=>{if(listeningCurrent(session)&&index+1<session.queue.length)void loadFamilyTrack(session,index+1);});next.disabled=index+1>=session.queue.length;
      session.controls.replaceChildren(btn(t('stopListening'),()=>stopFamilyListening()),next);
      const playResult=player.play?.();
      if(playResult&&typeof playResult.then==='function')playResult.then(()=>{if(!listeningCurrent(session)||session.player!==player)clearPlayer(player);}).catch(error=>{if(!listeningCurrent(session)||session.player!==player)return;if(error?.name==='NotAllowedError')session.status.textContent=t('playbackBlocked');else stopFamilyListening(t('listeningFailed'));});
    }catch(error){
      if(listeningCurrent(session)){stopFamilyListening(t('listeningFailed'));notifyError(error);}
    }finally{if(familyListening===session)session.loading=false;}
  }
  function renderContributions(feed,ticket,owner){stopFamilyListening();forgetUrls();feed.replaceChildren();renderFamilyListening(feed,ticket,owner);if(!contributionList.length)feed.append(el('p',t('noVoices')));else for(const item of contributionList)renderContribution(feed,item,ticket,owner);if(contributionsHasMore)feed.append(btn(t('moreContributions'),()=>void loadMoreContributions(feed,ticket,owner),'memory-contribution-more'));}
  async function loadContributions(feed,ticket,owner){
    try{
      const result=await api(`${pathStory()}?page=1`);if(!current(ticket,owner))return;
      if(result.version!==1||result.story_id!==target.id||result.page!==1||result.page_size!==16||!Array.isArray(result.items)||result.items.length>16||typeof result.can_review!=='boolean'||typeof result.can_delete!=='boolean'||typeof result.has_more!=='boolean')throw new Error('Invalid contribution list');
      canReview=result.can_review;canDelete=result.can_delete;contributionList=result.items;contributionDetails.clear();contributionPage=1;contributionsHasMore=result.has_more;renderContributions(feed,ticket,owner);
    }catch(error){if(current(ticket,owner)){feed.replaceChildren(el('p',t('unavailable')));notifyError(error);}}
  }
  async function loadMoreContributions(feed,ticket,owner){if(contributionsBusy)return;contributionsBusy=true;try{const page=contributionPage+1,result=await api(`${pathStory()}?page=${page}`);if(!current(ticket,owner))return;if(result.version!==1||result.story_id!==target.id||result.page!==page||result.page_size!==16||!Array.isArray(result.items)||result.items.length>16||typeof result.has_more!=='boolean')throw new Error('Invalid contribution page');contributionPage=page;contributionsHasMore=result.has_more;contributionList.push(...result.items);renderContributions(feed,ticket,owner);}catch(error){report(error,owner,ticket);}finally{contributionsBusy=false;}}
  function renderContribution(root,item,ticket,owner){
    if(!item||!uuidOK(item.id)||!['text','audio'].includes(item.kind)||!['pending','accepted','declined'].includes(item.state))return;
    const card=el('article','','memory-contribution');card.dataset.state=item.state;
    const status=item.state==='pending'?t('pending'):item.state==='accepted'?t('accepted'):t('declined');
    const author=item.author_id===scopeNow()?.account?t('mine'):t('familyMember');card.append(el('p',item.byline?`${author} · ${item.byline} · ${status}`:`${author} · ${status}`,'memory-contribution-meta'));
    card.append(el('p',item.processing_consent?t('consented'):t('noConsent'),'memory-contribution-meta'));
    if(item.kind==='text')card.append(el('blockquote',item.text||''));
    else {const audioButton=btn(t('audio'),()=>{if(audioButton.disabled||card.querySelector('audio'))return;audioButton.disabled=true;void playContributionAudio(card,item,ticket,owner,audioButton);});card.append(audioButton);}
    const detailBox=el('div','','memory-contribution-detail');const renderDetail=detail=>{detailBox.replaceChildren();if(!detail?.derivation){detailBox.append(el('p',t('noDerivation')));return;}const derived=detail.derivation;detailBox.append(el('p',`${t('status')}: ${derived.state}`));if(derived.transcript)detailBox.append(el('h4',t('transcript')),el('p',derived.transcript));if(derived.polished_text)detailBox.append(el('h4',t('polished')),el('p',derived.polished_text));if(derived.tags.length){detailBox.append(el('h4',t('tags')));const tags=el('ul');for(const tag of derived.tags)tags.append(el('li',tag));detailBox.append(tags);}};
    const detailsButton=btn(contributionDetails.has(item.id)?t('hideDerivation'):t('viewDerivation'),()=>{if(detailsButton.disabled)return;void toggleContributionDetail(item,detailBox,detailsButton,renderDetail,ticket,owner);},'memory-contribution-detail-toggle');card.append(detailsButton,detailBox);detailBox.hidden=!contributionDetails.has(item.id);
    if(canReview&&item.state==='pending'){
      const actions=el('div','','memory-contribution-review');
      actions.append(el('span',t('review')),btn(t('accept'),()=>void reviewContribution(item,'accepted',ticket,owner)),btn(t('decline'),()=>void reviewContribution(item,'declined',ticket,owner)));
      card.append(actions);
    }
    if(canDelete)card.append(btn(t('deleteOriginal'),()=>void deleteContribution(item,card,ticket,owner),'memory-community-delete'));
    root.append(card);
  }
  async function toggleContributionDetail(item,box,button,renderDetail,ticket,owner){
    if(contributionDetails.has(item.id)){const expanded=box.hidden;box.hidden=!expanded;button.textContent=expanded?t('hideDerivation'):t('viewDerivation');return;}
    if(button.disabled)return;button.disabled=true;
    try{const detail=await api(`${pathStory()}/${item.id}`);if(!current(ticket,owner)||!box.parentNode)return;if(!validContributionDetail(detail,item,target?.id))throw new Error('Invalid contribution detail');contributionDetails.set(item.id,detail);renderDetail(detail);box.hidden=false;button.textContent=t('hideDerivation');}
    catch(error){report(error,owner,ticket);}
    finally{if(current(ticket,owner)&&box.parentNode)button.disabled=false;}
  }
  function validContributionDetail(detail,item,storyId){
    const d=detail?.derivation;
    return detail?.version===1&&detail.id===item?.id&&detail.story_id===storyId&&detail.kind===item?.kind&&detail.state===item?.state&&
      (d===null||(d&&typeof d==='object'&&Number.isInteger(d.revision)&&d.revision>0&&typeof d.state==='string'&&
        (d.transcript===null||boundedText(d.transcript,8192))&&(d.polished_text===null||boundedText(d.polished_text,8192))&&
        Array.isArray(d.tags)&&d.tags.length<=24&&d.tags.every(tag=>safeText(tag,256))&&(d.error_code===null||typeof d.error_code==='string')&&
        Number.isInteger(d.created_at)&&Number.isInteger(d.updated_at)));
  }
  async function deleteContribution(item,card,ticket,owner){
    if(!canDelete||!window.confirm(t('confirmDelete')))return;
    try{await api(`${pathStory()}/${item.id}`,{method:'DELETE'});if(!current(ticket,owner))return;contributionList=contributionList.filter(entry=>entry.id!==item.id);renderContributions(panelNode.querySelector('.memory-community-contributions'),ticket,owner);}
    catch(error){report(error,owner,ticket);}
  }
  async function playContributionAudio(card,item,ticket,owner,button){
    if(!current(ticket,owner)||document.hidden||!card.parentNode)return;
    if(isCapturing()){showStatus(t('audioDuringRecording'));return;}
    stopPlayback();notifyAudioStart();
    const attempt={epoch:individualPlaybackEpoch};individualAttempts.set(button,attempt);
    try{const blob=await api(`${pathStory()}/${item.id}/audio`,{responseType:'blob'});if(!current(ticket,owner)||document.hidden||attempt.epoch!==individualPlaybackEpoch||individualAttempts.get(button)!==attempt||!card.parentNode)return;const url=URL.createObjectURL(blob);objectUrls.add(url);const player=el('audio');player.controls=true;player.src=url;individualPlayers.set(player,button);player.addEventListener('play',()=>{if(current(ticket,owner)&&!document.hidden&&individualPlayers.has(player)&&card.parentNode)notifyAudioStart();});card.append(player);}
    catch(error){if(individualAttempts.get(button)===attempt)report(error,owner,ticket);}
    finally{if(individualAttempts.get(button)===attempt){individualAttempts.delete(button);if(current(ticket,owner)&&card.parentNode&&!card.querySelector('audio'))button.disabled=false;}}
  }
  async function reviewContribution(item,state,ticket,owner){
    try{await api(`${pathStory()}/${item.id}/review`,{method:'POST',body:{state,revision:String(target.revision)}});if(!current(ticket,owner))return;await loadContributions(panelNode.querySelector('.memory-community-contributions'),ticket,owner);}
    catch(error){report(error,owner,ticket);}
  }
  function contributionBody(form,kind){
    const text=form.elements.text.value,consent=form.elements.consent.checked?'1':'0';
    if(kind==='text'&&!safeText(text,8192)){showStatus(t('textRequired'),'error');return null;}
    const byline=form.elements.byline.value;if(!boundedText(byline,256)){showStatus(t('error'),'error');return null;}
    const language=['zh','en','mixed','und'].includes(target.language)?target.language:'und';
    return {kind,text:kind==='text'?text:'',language,byline,
      consent,chapter_id:form.elements.chapter_id.value,revision:String(target.revision),mutation_id:uuid()};
  }
  function syncContributionCaptureForm(){
    const form=captureForm;if(!form)return;const audio=form.dataset.mode==='audio',busy=captureStarting||Boolean(captureHandle);
    const record=form.querySelector('button[data-capture-record]'),stop=form.querySelector('button[data-capture-stop]'),cancel=form.querySelector('button[data-capture-cancel]'),status=form.querySelector('.memory-recording-status'),save=form.querySelector('.memory-community-primary');
    if(record){record.hidden=!audio||!capture||busy||Boolean(recording);record.disabled=Boolean(pendingContribution);}
    if(stop)stop.hidden=!audio||!captureHandle;if(cancel){cancel.hidden=!audio||(!busy&&!recording);cancel.disabled=Boolean(pendingContribution);}
    if(status){status.hidden=!audio||(!busy&&!recording);status.textContent=recording?t('recordingReady'):busy?t('recording'):'';}
    if(save)save.disabled=busy||Boolean(pendingContribution);
  }
  async function beginCapture(ticket,owner,form){
    if(!capture||captureStarting||captureHandle||pendingContribution||ideaVoicePending()||chatRecordingBusy||!current(ticket,owner)||document.hidden||!form.parentNode)return;
    stopPlayback();notifyAudioStart();void clearCapture(false);const generation=captureGeneration;captureStarting=true;syncContributionCaptureForm();
    try{const handle=await capture(file=>{if(generation===captureGeneration&&current(ticket,owner)&&!document.hidden){recording=file;captureHandle=null;captureStarting=false;if(captureTimer)clearTimeout(captureTimer);captureTimer=null;showStatus('');syncContributionCaptureForm();}},30);
      if(generation!==captureGeneration||!current(ticket,owner)||document.hidden){await handle.stop(false);return;}
      captureStarting=false;if(!recording){captureHandle=handle;captureTimer=setTimeout(()=>{void clearCapture(true);},31000);}syncContributionCaptureForm();
    }catch(error){if(generation===captureGeneration){captureStarting=false;syncContributionCaptureForm();report(error,owner,ticket);}}
  }
  async function validWav(file){
    if(!file||typeof file.size!=='number'||file.size<46||file.size>MAX_AUDIO||file.type&&file.type!=='audio/wav')return false;
    try{const bytes=new DataView(await file.slice(0).arrayBuffer());if(bytes.getUint32(0,false)!==0x52494646||bytes.getUint32(8,false)!==0x57415645||bytes.getUint32(4,true)+8!==bytes.byteLength)return false;
      let offset=12,format=null,channels=0,rate=0,bits=0,frames=0;
      while(offset+8<=bytes.byteLength){const tag=bytes.getUint32(offset,false),size=bytes.getUint32(offset+4,true),start=offset+8;if(start+size>bytes.byteLength)return false;
        if(tag===0x666d7420&&size>=16){format=bytes.getUint16(start,true);channels=bytes.getUint16(start+2,true);rate=bytes.getUint32(start+4,true);bits=bytes.getUint16(start+14,true);}
        if(tag===0x64617461)frames=size/2;
        offset=start+size+(size&1);
      }
      return format===1&&channels===1&&rate===16000&&bits===16&&Number.isInteger(frames)&&frames>0&&frames<=30*16000;
    }catch(_){return false;}
  }
  async function saveContribution(form,ticket,owner){
    if(captureStarting||captureHandle)return;
    const mode=form.dataset.mode||'text';
    const kind=mode==='audio'?'audio':'text';
    if(!pendingContribution){
      const body=contributionBody(form,kind);if(!body)return;
      if(!body.mutation_id){showStatus(t('error'),'error');return;}
      const file=kind==='audio'?(recording||form.elements.file.files?.[0]):null;
      if(kind==='audio'&&!await validWav(file)){showStatus(t('fileInvalid'),'error');return;}if(!current(ticket,owner))return;
      pendingContribution={body,file};
      setContributionPendingUI(form,true);
    }
    return retryContribution(form,ticket,owner);
  }
  function base64Utf8(value){const bytes=new TextEncoder().encode(value);let binary='';for(let i=0;i<bytes.length;i+=0x6000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x6000));return btoa(binary);}
  function setContributionPendingUI(form,pending){
    const retry=form.querySelector('.memory-contribution-retry'),save=form.querySelector('.memory-community-primary');
    if(retry){retry.hidden=!pending;retry.disabled=false;}
    if(save)save.disabled=pending;
    for(const field of form.querySelectorAll('input,textarea,select'))field.disabled=pending;
  }
  function resetContributionForm(form){
    form.reset?.();form.dataset.mode='text';
    for(const field of form.querySelectorAll('input,textarea,select')){field.disabled=false;if(field.type==='file')field.value='';if(field.type==='checkbox')field.checked=false;if(field.name==='text'||field.name==='byline'||field.name==='chapter_id')field.value='';}
    const tabs=panelNode?.querySelector('.memory-community-subtabs');if(tabs)tabs.dataset.mode='text';
    const textLabel=form.querySelector('textarea[name="text"]')?.parentNode,fileLabel=form.querySelector('input[name="file"]')?.parentNode;
    if(textLabel)textLabel.hidden=false;if(fileLabel)fileLabel.hidden=true;
    const record=form.querySelector('button[data-capture-record]'),keep=form.querySelector('button[data-capture-stop]'),cancel=form.querySelector('button[data-capture-cancel]');
    if(record)record.hidden=true;if(keep)keep.hidden=true;if(cancel)cancel.hidden=true;
    const save=form.querySelector('.memory-community-primary');if(save){save.disabled=false;save.textContent=t('save');}
    setContributionPendingUI(form,false);
    syncContributionCaptureForm();
  }
  async function retryContribution(form,ticket,owner){
    if(!pendingContribution||form.dataset.submitting==='true')return;form.dataset.submitting='true';const retry=form.querySelector('.memory-contribution-retry');if(retry)retry.disabled=true;const pending=pendingContribution;showStatus(t('retry'),'pending');
    try{
      if(pending.body.kind==='audio')await api(`${pathStory()}/audio`,{method:'POST',rawBody:pending.file,headers:{'Content-Type':'audio/wav','X-PhotoHouse-Memory-Metadata':base64Utf8(JSON.stringify(pending.body))}});
      else await api(`${pathStory()}/text`,{method:'POST',body:pending.body});
      if(!current(ticket,owner))return;pendingContribution=null;recording=null;contributionDraft={mode:'text',text:'',byline:'',chapter_id:'',consent:false};resetContributionForm(form);showStatus(t('saved'),'success');
      await loadContributions(panelNode.querySelector('.memory-community-contributions'),ticket,owner);
    }catch(error){if(current(ticket,owner)){if(error?.status===409){pendingContribution=null;showStatus(t('conflict'),'error');setContributionPendingUI(form,false);}else {showStatus(t('retry'),'pending');setContributionPendingUI(form,true);if(retry)retry.textContent=t('retry');}notifyError(error);}}
    finally{form.dataset.submitting='false';if(current(ticket,owner)&&pendingContribution&&retry)retry.disabled=false;}
  }

  async function renderChat(root,ticket,owner,renderId){
    const editorTarget=target,editorFingerprint=targetFingerprint,editorConversation=conversation,editorSelection=conversationSelectionEpoch;
    const editorCurrent=input=>current(ticket,owner)&&activeTab==='chat'&&target===editorTarget&&targetFingerprint===editorFingerprint&&conversation===editorConversation&&conversationSelectionEpoch===editorSelection&&panelRenderEpoch===renderId&&root.parentNode===panelNode&&input.isConnected!==false;
    root.append(el('p',t('conversationHelp'),'memory-community-help'),el('p',t('conversationContextHelp'),'memory-community-help memory-chat-context-help'));
    renderConversationControls(root,ticket,owner);
    if(target?.type==='memoir'){
      const component=mount,memoir=target,reader=component?.closest?.('.memory-book-reader');
      if(reader){const jump=btn(t('returnToChapter'),()=>{
        if(!current(ticket,owner)||target!==memoir||target?.type!=='memoir'||mount!==component||mount?.closest?.('.memory-book-reader')!==reader||!reader.open||!reader.contains(component))return;
        const pane=reader.querySelector('.memory-book-reading:not([hidden])'),chapter=pane?.querySelector('h4');
        const contents=reader.querySelector('.memory-book-toc:not([hidden])'),destination=chapter?.isConnected?chapter:contents?.querySelector('button');
        if(!destination?.isConnected)return;
        const behavior=window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'auto':'smooth';
        destination.scrollIntoView({block:'center',behavior});destination.focus({preventScroll:true});
      },'memory-book-return-current');root.append(jump);}
    }
    if(!conversation)return;
    if(conversation.expires_at){const date=new Date(conversation.expires_at*1000);root.append(el('p',`${t('expires')} ${date.toLocaleDateString(lang()==='zh'?'zh-CN':'en-US')} ${t('expiresSuffix')}`,'memory-community-meta'));}
    const history=el('div','','memory-chat-history');root.append(history);
    if(activeJob?.kind==='chat'&&activeJob.result?.reply&&recentTurn?.job_id===activeJob.id&&!recentTurn.reply_text)recentTurn={...recentTurn,reply_text:activeJob.result.reply,reply_kind:activeJob.result.kind,state:'ready'};
    const visibleTurns=[...turns];
    if(recentTurn&&!turns.some(turn=>turn.job_id===recentTurn.job_id))visibleTurns.push(recentTurn);
    visibleTurns.sort((a,b)=>(Number.isSafeInteger(a.sequence)?a.sequence:Number.MAX_SAFE_INTEGER)-(Number.isSafeInteger(b.sequence)?b.sequence:Number.MAX_SAFE_INTEGER));
    const replyFollowups=[];let latestTurnCard=null;
    if(!visibleTurns.length)history.append(el('p',t('noTurns')));else for(const turn of visibleTurns){
      const card=el('article','','memory-chat-turn'),userBubble=el('div','','memory-chat-bubble memory-chat-user-bubble'),assistantBubble=el('div','','memory-chat-bubble memory-chat-assistant-bubble'),hasAssistantContent=Boolean(turn.reply_text)||['queued','running','stale','failed','cancelled'].includes(turn.state);card.tabIndex=-1;
      userBubble.append(el('p',t('you'),'memory-chat-turn-role'),el('p',turn.input_text||'','memory-chat-turn-user'));
      if(target?.type==='story'&&caps?.contributions_enabled&&typeof turn.input_text==='string'&&turn.input_text){
        const keep=btn(t('keepChatTurn'),()=>void keepChatTurnAsMemory(turn,keep,card,ticket,owner,editorTarget,editorFingerprint,editorConversation,editorSelection,renderId,root),'memory-community-button memory-chat-memory-button');userBubble.append(keep);
      }
      if(hasAssistantContent)assistantBubble.append(el('p',t('assistant'),'memory-chat-turn-role'));
      if(turn.reply_text){const replyMetadata=chatReplyMetadata(turn,ticket,owner,editorTarget,editorFingerprint,editorConversation,editorSelection);if(isValidatedClarification(turn,replyMetadata)){assistantBubble.append(el('strong',t('chatClarificationCue'),'memory-chat-clarification-cue'));assistantBubble.append(el('p',t('chatClarificationHelp'),'memory-community-help memory-chat-clarification-help'));}assistantBubble.append(el('p',turn.reply_text,'memory-chat-turn-assistant'));if(typeof mountReplySpeech==='function'){const speechControls=el('div','','memory-chat-reply-speech');assistantBubble.append(speechControls);try{const dispose=mountReplySpeech(speechControls,turn.reply_text,editorTarget?.language,()=>editorCurrent(speechControls));if(typeof dispose==='function')replySpeechDisposers.add(dispose);}catch(_){speechControls.remove();}}renderChatReplySources(assistantBubble,replyMetadata,node=>editorCurrent(node));replyFollowups.push({card:assistantBubble,turn,metadata:replyMetadata});}
      else if(['queued','running'].includes(turn.state))assistantBubble.append(el('p',t(turn.state==='queued'?'pendingQueued':'pendingRunning'),'memory-chat-turn-pending'));
      else if(turn.state==='stale')assistantBubble.append(el('p',t('stale'),'memory-chat-turn-pending'));
      else if(turn.state==='failed')assistantBubble.append(el('p',t('failed'),'memory-chat-turn-pending'));
      else if(turn.state==='cancelled')assistantBubble.append(el('p',t('cancelled'),'memory-chat-turn-pending'));
      card.append(userBubble);if(hasAssistantContent)card.append(assistantBubble);
      history.append(card);latestTurnCard=card;
    }
    const lastVisibleTurn=visibleTurns.at(-1);
    if(lastVisibleTurn?.reply_text&&!(activeJob?.kind==='chat'&&['queued','running'].includes(activeJob.state)))root.append(el('p',t('voiceNextTurnHelp'),'memory-chat-next-turn'));
    if(turnsHasMore&&turnPage<8)root.append(btn(t('moreTurns'),()=>void loadMoreTurns(ticket,owner),'memory-chat-more'));
    if(turnPage>1)root.append(btn(t('refreshTurns'),()=>void refreshViewedTurns(ticket,owner),'memory-chat-refresh'));
    const form=el('form','','memory-community-form');const label=el('label',t('message'));const input=el('textarea');input.name='message';input.rows=3;input.value=chatTextDraft;input.maxLength=4096;
    const navigation=el('div','','memory-chat-followup-actions memory-chat-navigation');
    const navigateTo=(destination,focusTarget)=>{
      if(!editorCurrent(focusTarget)||!destination?.isConnected)return;
      const behavior=window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'auto':'smooth';
      destination.scrollIntoView?.({block:'center',behavior});destination.focus?.({preventScroll:true});
    };
    let latestButton=null;if(latestTurnCard){latestButton=btn(t('chatLatest'),()=>{if(!editorCurrent(latestButton))return;navigateTo(latestTurnCard,latestButton);},'memory-community-button memory-chat-navigation-latest');navigation.append(latestButton);}
    const writeNext=btn(t('chatWriteNext'),()=>{if(!editorCurrent(writeNext))return;navigateTo(input,writeNext);},'memory-community-button memory-chat-navigation-compose');navigation.append(writeNext);
    input.addEventListener('input',()=>{
      if(!editorCurrent(input))return;
      chatTextDraft=input.value;if(conversation)conversationDrafts.set(conversation.id,chatTextDraft);const state=chatComposition;if(state?.input===input&&state.endSeen){state.finalInput=true;if(state.timer)clearTimeout(state.timer);state.timer=setTimeout(()=>flushDeferredChatRender(state),0);}
    });
    input.addEventListener('compositionstart',()=>{
      if(!editorCurrent(input))return;
      clearChatComposition();chatComposition={input,field:'message',ticket,owner,target:editorTarget,fingerprint:editorFingerprint,conversation:editorConversation,selection:editorSelection,tab:'chat',renderId,root,composing:true,endSeen:false,finalInput:false,timer:null};
    });
    input.addEventListener('compositionend',()=>{
      const state=chatComposition;if(!compositionCurrent(state)||state.input!==input)return;
      state.composing=false;state.endSeen=true;state.timer=setTimeout(()=>{if(state===chatComposition&&!state.finalInput){assignComposedChatValue(state);state.finalInput=true;}flushDeferredChatRender(state);},50);
    });
    label.append(input);form.append(label);const editorialChoiceControl=renderEditorialContextChoice(form,'chat',ticket,owner);root.prepend(navigation);
    replyFollowups.forEach(({card,turn,metadata})=>renderChatFollowups(card,turn,input,ticket,owner,editorCurrent,metadata));
    renderReadingChapterPrompt(form,input,editorCurrent,editorTarget);
    if(!visibleTurns.length&&!chatTextDraft&&!messageDraft){
      const starters=el('section','','memory-chat-starters'),status=el('p','','memory-chat-starter-status');status.setAttribute('role','status');
      starters.append(el('h3',t('chatStarters')),el('p',t('chatStarterHelp'),'memory-community-help'));
      for(const key of ['starterDetails','starterSequence','starterChapters']){
        const memoirKey=target?.type==='memoir'?`memoir${key[0].toUpperCase()}${key.slice(1)}`:key;
        const starter=btn(t(memoirKey),()=>{
          if(!editorCurrent(starter)||document.hidden)return;
          const reason=chatDraftInsertionBlocked(input);if(reason){status.textContent=reason;return;}
          chatTextDraft=t(memoirKey+'Text');conversationDrafts.set(editorConversation.id,chatTextDraft);input.value=chatTextDraft;
          input.focus();try{input.setSelectionRange(input.value.length,input.value.length);}catch(_){}starters.remove();
        },'memory-chat-starter');starters.append(starter);
      }
      starters.append(status);form.prepend(starters);
    }
    const voice=await resolveVoiceCapabilities(ticket,owner);if(!current(ticket,owner)||root.parentNode!==panelNode)return;
    if(voice.transcribe&&capture&&transcribe){
      form.append(el('p',t('transcriptHelp'),'memory-community-help'));
      const recordLabel=chatVoiceError?t('chatRetryDictation'):lastVisibleTurn?.reply_text?t('chatContinueRecord'):t('chatRecord');
      const record=btn(recordLabel,()=>{if(!editorCurrent(record)||chatCaptureStartBlocked())return;void beginChatCapture(ticket,owner);},'memory-community-button memory-chat-record-button');record.disabled=chatCaptureStartBlocked();form.append(record);if(editorialChoiceControl)editorialChoiceControl.recordButton=record;
      if(chatCaptureHandle){const stopVoiceTicket=chatCaptureVoiceTicket,stop=btn(t('chatRecordStop'),()=>{if(!editorCurrent(stop))return;void finishChatCapture(ticket,owner,stopVoiceTicket);},'memory-community-primary');form.append(stop);}
      else if(chatCaptureStarting){const waiting=el('p',t('chatCaptureWaiting'),'memory-community-status');waiting.setAttribute('role','status');waiting.setAttribute('aria-live','polite');form.append(waiting);}
      else if(chatTranscribing){const transcribing=el('p',t('chatTranscribing'),'memory-community-status');transcribing.setAttribute('role','status');transcribing.setAttribute('aria-live','polite');form.append(transcribing);}
      if(chatVoiceError){const recovery=el('p',t(chatVoiceError),'memory-chat-voice-recovery');recovery.setAttribute('role','status');form.append(recovery);}
      if(chatTranscript){const transcriptLabel=el('label',t('chatTranscript'));const transcript=el('textarea');transcript.value=chatTranscript;transcript.maxLength=1024;
        transcript.addEventListener('input',()=>{
          if(!editorCurrent(transcript))return;
          chatTranscript=transcript.value;const state=chatComposition;if(state?.input===transcript&&state.endSeen){state.finalInput=true;if(state.timer)clearTimeout(state.timer);state.timer=setTimeout(()=>flushDeferredChatRender(state),0);}
        });
        transcript.addEventListener('compositionstart',()=>{
          if(!editorCurrent(transcript))return;
          clearChatComposition();chatComposition={input:transcript,field:'transcript',ticket,owner,target:editorTarget,fingerprint:editorFingerprint,conversation:editorConversation,selection:editorSelection,tab:'chat',renderId,root,composing:true,endSeen:false,finalInput:false,timer:null};
        });
        transcript.addEventListener('compositionend',()=>{
          const state=chatComposition;if(!compositionCurrent(state)||state.input!==transcript)return;
          state.composing=false;state.endSeen=true;state.timer=setTimeout(()=>{if(state===chatComposition&&!state.finalInput){assignComposedChatValue(state);state.finalInput=true;}flushDeferredChatRender(state);},50);
        });
        transcriptLabel.append(transcript);form.append(transcriptLabel);
        const review=el('p',t('transcriptNeedsReview'),'memory-chat-voice-recovery');review.setAttribute('role','status');form.append(review);
        form.append(btn(t('addTranscript'),()=>{if(!editorCurrent(transcript))return;const combined=input.value?(input.value+'\n'+transcript.value):transcript.value;if(new TextEncoder().encode(combined).length<=4096){chatTextDraft=combined;if(conversation)conversationDrafts.set(conversation.id,chatTextDraft);chatTranscript='';chatVoiceError='';renderPanel();}else showStatus(t('error'),'error');},'memory-community-button'));
        form.append(btn(t('discardTranscript'),()=>{if(!editorCurrent(transcript))return;chatTranscript='';chatVoiceError='';renderPanel();},'memory-community-button'));
      }
    }
    const send=el('button',messageDraft?t('retrySend'):t('send'));send.type='submit';send.className='memory-community-primary';send.disabled=Boolean(editorialContextPreflight||assistantInflightToken||conversationLoading||conversationCreating||conversationDeleting||!messageDraft&&hasPendingChatWork());form.append(send);editorialChoiceControl?.sync();
    form.addEventListener('submit',event=>{event.preventDefault();if(!editorCurrent(input)||chatComposition?.composing)return;void sendMessage(input,ticket,owner);});root.append(form);
    if(pendingChatRecovery?.conversation===conversation){const note=el('p',t(pendingChatRecovery.loading?'chatRecovering':'chatRecoveryFailed'),'memory-community-status memory-chat-recovery-status');note.setAttribute('role','status');root.append(note);if(!pendingChatRecovery.loading)root.append(btn(t('chatRecoveryRetry'),()=>void (pendingChatRecovery.reason==='missing-id'?refreshViewedTurns(ticket,owner):recoverPendingChatJob(ticket,owner,conversation,conversationSelectionEpoch)),'memory-community-button'));}
    if(activeJob?.id){root.append(btn(t('refresh'),()=>void pollJob(ticket,owner),'memory-community-button'),btn(t('cancel'),()=>void cancelJob(activeJob.id,true),'memory-community-button'));}
    if(pollTimer===null&&activeJob&&pollCount>=30)root.append(el('p',t('pollManual')));
    if(activeJob?.result?.kind==='proposal')renderCompanionProposal(root,activeJob.result,ticket,owner);
    const close=btn(t('closeChat'),()=>void closeConversation(ticket,owner),'memory-community-button');close.disabled=Boolean(conversationDeleting||conversationCreating||conversationLoading||assistantInflightToken||activeJob?.id&&['queued','running'].includes(activeJob.state));root.append(close);
  }
  async function keepChatTurnAsMemory(turn,button,card,ticket,owner,editorTarget,editorFingerprint,editorConversation,editorSelection,renderId,root){
    const editorCurrent=input=>current(ticket,owner)&&activeTab==='chat'&&target===editorTarget&&targetFingerprint===editorFingerprint&&conversation===editorConversation&&conversationSelectionEpoch===editorSelection&&panelRenderEpoch===renderId&&root.parentNode===panelNode&&input.isConnected!==false;
    if(!editorCurrent(button)||editorTarget?.type!=='story'||!caps?.contributions_enabled||typeof turn?.input_text!=='string'||!turn.input_text)return;
    const file=captureForm?.querySelector('input[name="file"]');
    const contributionBusy=Boolean(pendingContribution||recording||captureStarting||captureHandle||captureForm?.dataset.submitting==='true'||file?.files?.length||contributionDraft.mode!=='text'||contributionDraft.text||contributionDraft.byline||contributionDraft.chapter_id||contributionDraft.consent);
    const chatBusy=Boolean(conversationLoading||conversationCreating||conversationDeleting||assistantInflightToken||activeJob?.id&&['queued','running'].includes(activeJob.state)||pendingChatTurns().length||chatRecordingBusy||chatCaptureStarting||chatTranscribing||chatCaptureHandle||chatTranscript||messageDraft||chatComposition?.composing);
    let note=card.querySelector('.memory-chat-memory-status');
    if(contributionBusy||chatBusy){
      if(!note){note=el('p','','memory-chat-memory-status');note.setAttribute('role','status');card.append(note);}
      note.textContent=t('chatTurnKeepBlocked');return;
    }
    contributionDraft={mode:'text',text:turn.input_text,byline:'',chapter_id:'',consent:false};
    const selectedConversation=editorConversation,selectedTarget=editorTarget,selectedFingerprint=editorFingerprint,selectedSelection=editorSelection,selectedMount=mount;
    activeTab='voice';renderTabs();await renderPanel();
    if(!current(ticket,owner)||target!==selectedTarget||targetFingerprint!==selectedFingerprint||conversation!==selectedConversation||conversationSelectionEpoch!==selectedSelection||mount!==selectedMount||activeTab!=='voice'||!caps?.contributions_enabled)return;
    const text=panelNode?.querySelector('textarea[name="text"]');if(text?.isConnected)text.focus();
  }
  function conversationBusyReason(){
    if(editorialContextPreflight)return t('threadBusy');
    if(conversationLoading||conversationCreating||conversationDeleting)return t('threadBusy');
    if(chatComposition?.composing)return t('threadDraftBlocked');
    if(assistantInflightToken||activeJob?.id&&['queued','running'].includes(activeJob.state)||pendingChatTurns().length)return t('threadBusy');
    if(chatRecordingBusy||chatCaptureHandle||chatTranscript||messageDraft)return t('threadDraftBlocked');
    return '';
  }
  function renderConversationControls(root,ticket,owner){
    const controls=el('div','','memory-chat-conversations');
    const label=el('label',t('conversationSelect'),'memory-chat-conversation-label');
    const select=el('select');select.className='memory-chat-conversation-select';select.name='conversation';
    const canSwitch=!conversationBusyReason();
    for(const [index,item] of conversationList.entries()){
      const option=el('option');option.value=item.id;const date=Number.isInteger(item.created_at)?new Date(item.created_at*1000).toLocaleDateString(lang()==='en'?'en-US':'zh-CN'):t('conversationCreated');const preview=conversationPreview(item.first_message_preview);option.textContent=preview?`“${preview}” · ${date}`:`${t('conversationNumber')(index+1)} · ${date}`;option.selected=item.id===conversation?.id;select.append(option);
    }
    select.disabled=!canSwitch||conversationList.length<2;
    select.addEventListener('change',()=>{if(!current(ticket,owner))return;void switchConversation(select.value,ticket,owner);});label.append(select);controls.append(label);
    const start=btn(t('startChat'),()=>void startChat(ticket,owner),'memory-community-primary');start.disabled=!canSwitch;controls.append(start);
    controls.append(el('p',t('conversationListHelp'),'memory-community-help'));
    if(conversationLoading)controls.append(el('p',t('threadLoading'),'memory-community-help'));
    const blocked=conversationBusyReason();if(blocked){const note=el('p',blocked,'memory-community-help');note.setAttribute('role','status');controls.append(note);}
    root.append(controls);
  }
  function conversationPreview(value){
    return typeof value==='string'&&wellFormed(value)&&new TextEncoder().encode(value).length<=320&&Array.from(value).length<=80&&!/[\u0000-\u001f\u007f-\u009f]/u.test(value)&&normalizeConversationPreview(value)===value?value:'';
  }
  function normalizeConversationPreview(value){
    return Array.from(value.replace(/\p{White_Space}+/gu,' ').replace(/^ +| +$/g,'')).slice(0,80).join('').replace(/ +$/g,'');
  }
  function chatCaptureStartBlocked(){return Boolean(editorialContextPreflight||chatRecordingBusy||chatTranscript||ideaCaptureStarting||ideaCaptureHandle||ideaTranscribing||assistantInflightToken||activeJob?.id&&['queued','running'].includes(activeJob.state)||conversationLoading||conversationCreating||conversationDeleting);}
  async function beginChatCapture(ticket,owner){
    if(!voiceCapabilitiesValue?.transcribe||!capture||!transcribe||chatCaptureStartBlocked()||!conversation||!current(ticket,owner)||document.hidden)return;
    stopPlayback();notifyAudioStart();chatVoiceError='';chatRecordingBusy=true;chatCaptureStarting=true;const voiceTicket=++chatVoiceEpoch;chatCaptureVoiceTicket=voiceTicket;await renderPanel();
    try{if(!current(ticket,owner)||voiceTicket!==chatVoiceEpoch||document.hidden)return;let resolveCaptured;const ready=new Promise(resolve=>{resolveCaptured=resolve;});const handle=await capture(file=>resolveCaptured(file),voiceCapabilitiesValue.max_audio_seconds);
      // A delayed permission result owns only its local handle. It must never
      // overwrite or clear a capture that belongs to a newer reader/scope.
      if(!current(ticket,owner)||voiceTicket!==chatVoiceEpoch||document.hidden){await handle.stop(false);return;}
      chatCaptureHandle=handle;chatCaptureReady=ready;chatCaptureStarting=false;
      chatCaptureTimer=setTimeout(()=>void finishChatCapture(ticket,owner,voiceTicket),31000);await renderPanel();
    }catch(error){if(current(ticket,owner)&&voiceTicket===chatVoiceEpoch){chatRecordingBusy=false;chatCaptureStarting=false;chatCaptureHandle=null;chatCaptureReady=null;chatVoiceError=error?.name==='NotAllowedError'||error?.name==='SecurityError'?'voicePermissionFailed':'voiceCaptureFailed';notifyError(error);await renderPanel();}}
  }
  async function finishChatCapture(ticket,owner,voiceTicket=chatCaptureVoiceTicket){
    const handle=chatCaptureHandle;if(!handle||!current(ticket,owner)||voiceTicket!==chatVoiceEpoch)return;
    if(chatCaptureTimer)clearTimeout(chatCaptureTimer);chatCaptureTimer=null;chatCaptureHandle=null;
    try{const ready=chatCaptureReady;chatCaptureReady=null;const stopped=await handle.stop(true);const file=stopped||await ready;if(!current(ticket,owner)||voiceTicket!==chatVoiceEpoch||document.hidden)return;
      if(!file){chatRecordingBusy=false;chatCaptureStarting=false;chatVoiceError='voiceCaptureFailed';await renderPanel();return;}
      if(!voiceCapabilitiesValue?.transcribe){chatRecordingBusy=false;chatCaptureStarting=false;await renderPanel();return;}chatCaptureStarting=false;chatTranscribing=true;chatVoiceError='';await renderPanel();if(!current(ticket,owner)||voiceTicket!==chatVoiceEpoch||document.hidden)return;const result=await transcribe(file);if(!current(ticket,owner)||voiceTicket!==chatVoiceEpoch||document.hidden)return;
      chatRecordingBusy=false;chatTranscribing=false;
      if(!result||result.version!==1||typeof result.text!=='string'||!wellFormed(result.text)||result.text.length>1024||!result.text.trim()){chatVoiceError='voiceAsrFailed';await renderPanel();return;}
      chatTranscript=result.text;chatVoiceError='';showStatus('');await renderPanel();
    }catch(error){if(current(ticket,owner)&&voiceTicket===chatVoiceEpoch){const wasTranscribing=chatTranscribing;chatRecordingBusy=false;chatCaptureStarting=false;chatTranscribing=false;chatVoiceError=error?.name==='AbortError'?'':wasTranscribing?'voiceAsrFailed':'voiceCaptureFailed';if(error?.name!=='AbortError')notifyError(error);await renderPanel();}}
  }
  async function startChat(ticket,owner){
    if(!current(ticket,owner)||conversationBusyReason())return;
    if(chatComposition?.composing)return;
    const id=uuid(),selectedTarget={...target},selectedType=target?.type==='memoir'?'book':'story',selectedFingerprint=targetFingerprint,selection=++conversationSelectionEpoch,operation={ticket,owner,selection};if(!id){showStatus(t('error'),'error');return;}
    conversationCreating=true;conversationCreateToken=operation;await renderPanel();
    try{
      if(!current(ticket,owner)||conversationSelectionEpoch!==selection||targetFingerprint!==selectedFingerprint)return;
      const result=await api(`${API}/conversations`,{method:'POST',body:{id,target_type:selectedType,target_id:selectedTarget.id}});
      if(!current(ticket,owner)||conversationSelectionEpoch!==selection||targetFingerprint!==selectedFingerprint)return;
      if(!result||result.version!==1||result.id!==id||!Number.isInteger(result.expires_at)||(result.target_type!==undefined&&result.target_type!==selectedType)||(result.target_id!==undefined&&result.target_id!==selectedTarget.id))throw new Error('Invalid conversation response');
      const createdAt=Number.isInteger(result.created_at)?result.created_at:null;
      const item={id,created_at:createdAt,expires_at:result.expires_at,target_type:selectedType,target_id:selectedTarget.id};
      resetEditorialContextChoice();
      const nextList=[item,...conversationList.filter(entry=>entry.id!==id)].slice(0,8),kept=new Set(nextList.map(entry=>entry.id));for(const previous of conversationList)if(!kept.has(previous.id))conversationDrafts.delete(previous.id);conversationList=nextList;
      stopPoll();invalidateChatRecovery();conversation=item;turns=[];turnPage=1;turnsHasMore=false;recentTurn=null;messageDraft=null;chatTextDraft='';chatTranscript='';chatVoiceError='';activeJob=null;pollCount=0;
      conversationDrafts.set(id,'');conversationCreating=false;conversationSelectionEpoch++;
      rememberConversation(id);
      renderTabs();await renderPanel();
    }catch(error){if(conversationSelectionEpoch===selection)report(error,owner,ticket);}
    finally{if(conversationCreateToken===operation){conversationCreateToken=null;conversationCreating=false;if(current(ticket,owner))await renderPanel();}}
  }
  async function resumeConversation(ticket,owner){
    const hintScopeAtStart=conversationHintScope();
    try{const base=`${API}/conversations?target_type=${targetType()}&target_id=${encodeURIComponent(target.id)}`;let result;
      try{result=await api(`${base}&preview=1`);}catch(error){if(error?.status!==400)throw error;if(!current(ticket,owner))return;result=await api(base);}
      if(!current(ticket,owner))return;
      if(result.version!==1||!Array.isArray(result.items)||result.items.length>8)return;
      const seen=new Set();for(const value of result.items){const hasPreview=Object.hasOwn(value||{},'first_message_preview');if(!value||!uuidOK(value.id)||seen.has(value.id)||!Number.isInteger(value.created_at)||!Number.isInteger(value.expires_at)||hasPreview&&(typeof value.first_message_preview!=='string'||conversationPreview(value.first_message_preview)!==value.first_message_preview))return;seen.add(value.id);}
      conversationList=result.items.map(item=>({...item,target_type:targetType(),target_id:target.id}));
      const key=hintScopeAtStart&&conversationHintScope()===hintScopeAtStart?hintScopeAtStart:null,hint=key?conversationHints.get(key):null;
      const item=(hint&&conversationList.find(value=>value.id===hint))||conversationList[0];if(hint&&!conversationList.some(value=>value.id===hint))conversationHints.delete(key);if(!item)return false;
      invalidateChatRecovery();conversation=item;conversationDrafts.set(item.id,'');const selection=++conversationSelectionEpoch;const history=await loadTurns(ticket,owner,item,selection);
      if(!current(ticket,owner)||conversationSelectionEpoch!==selection||conversation!==item)return;
      if(!history||!Array.isArray(history.items)||hintScopeAtStart!==conversationHintScope())return false;
      rememberConversation(item.id);
      resetEditorialContextChoice();
      await recoverPendingChatJob(ticket,owner,item,selection);
      return Boolean(hint&&item.id===hint);
    }catch(error){if(error?.name!=='AbortError')report(error,owner,ticket);return false;}
  }
  async function switchConversation(id,ticket,owner){
    if(!current(ticket,owner))return;
    const item=conversationList.find(value=>value.id===id),blocked=conversationBusyReason();
    if(!item||!target||item.target_type!==targetType()||item.target_id!==target.id||blocked){await renderPanel();if(blocked)showStatus(blocked,'pending');return;}
    const input=panelNode?.querySelector('.memory-community-form textarea[name="message"]');if(conversation&&input){chatTextDraft=input.value;conversationDrafts.set(conversation.id,chatTextDraft);}
    const selectedTarget=target,selectedFingerprint=targetFingerprint,selection=++conversationSelectionEpoch,operation={ticket,owner,selection};
    const previous={conversation,turns,turnPage,turnsHasMore,messageDraft,chatTextDraft,recentTurn,activeJob,pollCount};
    stopPoll();invalidateChatRecovery();conversation=item;conversationLoading=true;conversationLoadToken=operation;turns=[];turnPage=1;turnsHasMore=false;turnsBusyToken=null;messageDraft=null;chatTextDraft=conversationDrafts.get(item.id)||'';recentTurn=null;activeJob=null;pollCount=0;chatTranscript='';chatVoiceError='';await renderPanel();
    try{
      const history=await loadTurns(ticket,owner,item,selection);
      if(!current(ticket,owner)||conversationSelectionEpoch!==selection||conversation!==item||target!==selectedTarget||targetFingerprint!==selectedFingerprint)return;
      if(!history||!Array.isArray(history.items))throw new Error('Conversation history unavailable');
      rememberConversation(item.id);
      resetEditorialContextChoice();conversationLoading=false;conversationLoadToken=null;
      await recoverPendingChatJob(ticket,owner,item,selection);
      await renderPanel();
    }catch(error){if(error?.name!=='AbortError'&&current(ticket,owner)&&conversationSelectionEpoch===selection&&conversation===item){conversation=previous.conversation;turns=previous.turns;turnPage=previous.turnPage;turnsHasMore=previous.turnsHasMore;messageDraft=previous.messageDraft;chatTextDraft=previous.chatTextDraft;recentTurn=previous.recentTurn;activeJob=previous.activeJob;pollCount=previous.pollCount;conversationLoading=false;conversationLoadToken=null;if(activeJob?.id&&['queued','running'].includes(activeJob.state))schedulePoll(ticket,owner);report(error,owner,ticket);await renderPanel();}}
    finally{if(conversationLoadToken===operation){conversationLoadToken=null;conversationLoading=false;}}
  }
  async function closeConversation(ticket,owner){
    if(!current(ticket,owner)||!conversation||conversationDeleting||conversationCreating||conversationLoading||assistantInflightToken||activeJob?.id&&['queued','running'].includes(activeJob.state)||!window.confirm(t('confirmClose')))return;
    const prior=conversation,selectedTarget=target,selectedFingerprint=targetFingerprint,selection=++conversationSelectionEpoch,operation={ticket,owner,selection};conversationDeleting=true;conversationDeleteToken=operation;
    try{
      await renderPanel();
      if(!current(ticket,owner)||conversationSelectionEpoch!==selection||conversation!==prior||target!==selectedTarget||targetFingerprint!==selectedFingerprint)return;
      chatTranscript='';chatVoiceError='';await clearChatCapture();
      if(!current(ticket,owner)||conversationSelectionEpoch!==selection||conversation!==prior||target!==selectedTarget||targetFingerprint!==selectedFingerprint)return;
      const result=await api(`${API}/conversations/${prior.id}`,{method:'DELETE'});if(!current(ticket,owner)||conversationSelectionEpoch!==selection||conversation!==prior||target!==selectedTarget||targetFingerprint!==selectedFingerprint)return;
      if(!result||result.version!==1||result.deleted!==true)throw new Error('Invalid conversation delete response');
      resetEditorialContextChoice();stopPoll();invalidateChatRecovery();conversationDeleting=false;conversationDeleteToken=null;conversationList=conversationList.filter(item=>item.id!==prior.id);conversationDrafts.delete(prior.id);forgetConversation(prior.id);conversation=null;turns=[];turnPage=1;turnsHasMore=false;recentTurn=null;activeJob=null;messageDraft=null;chatTextDraft='';
      const next=conversationList[0];if(next){conversation=next;chatTextDraft=conversationDrafts.get(next.id)||'';const nextSelection=++conversationSelectionEpoch,nextOperation={ticket,owner,selection:nextSelection};conversationLoading=true;conversationLoadToken=nextOperation;turns=[];turnPage=1;turnsHasMore=false;await renderPanel();
        try{const history=await loadTurns(ticket,owner,next,nextSelection);if(!current(ticket,owner)||conversationSelectionEpoch!==nextSelection||conversation!==next)return;if(history&&Array.isArray(history.items))rememberConversation(next.id);await recoverPendingChatJob(ticket,owner,next,nextSelection);}
        catch(error){if(error?.name!=='AbortError'&&current(ticket,owner)&&conversationSelectionEpoch===nextSelection&&conversation===next)report(error,owner,ticket);}
        finally{if(conversationLoadToken===nextOperation){conversationLoadToken=null;conversationLoading=false;}}
      }else conversationSelectionEpoch++;
      if(current(ticket,owner)){renderTabs();await renderPanel();}
    }catch(error){if(error?.name!=='AbortError'&&current(ticket,owner)&&conversationSelectionEpoch===selection&&conversation===prior)report(error,owner,ticket);}
    finally{if(conversationDeleteToken===operation){conversationDeleteToken=null;conversationDeleting=false;if(current(ticket,owner))await renderPanel();}}
  }
  async function loadTurns(ticket,owner,selected=conversation,selection=conversationSelectionEpoch){
    if(!selected)return;
    if(turnsBusyToken)return;const requestToken={ticket,owner};turnsBusyToken=requestToken;
    try{
      const keepPage=Math.min(8,Math.max(1,turnPage)),loaded=[];let hasMore=false,lastPage=1;
      for(let page=1;page<=keepPage;page++){
        const data=await api(`${API}/conversations/${selected.id}/turns?page=${page}&order=recent&reply_context=1`);
        if(!current(ticket,owner)||conversation!==selected||conversationSelectionEpoch!==selection)return;
        if(data.version!==1||data.id!==selected.id||data.page!==page||!Array.isArray(data.items)||data.items.length>16||typeof data.has_more!=='boolean'||!validTurnPage(data.items))throw new Error('Invalid conversation history');
        loaded.push(...data.items);lastPage=page;hasMore=data.has_more;if(!hasMore)break;
      }
      if(!current(ticket,owner)||conversation!==selected||conversationSelectionEpoch!==selection)return;
      turns=mergeTurns([],loaded).slice(-128);turnPage=lastPage;turnsHasMore=hasMore;
      if(!conversationPreview(selected.first_message_preview)){const first=turns.find(turn=>turn.sequence===1&&typeof turn.input_text==='string'&&boundedText(turn.input_text,4096));if(first)selected.first_message_preview=normalizeConversationPreview(first.input_text);}
      if(recentTurn&&turns.some(turn=>turn.job_id===recentTurn.job_id))recentTurn=null;
      return {items:turns,has_more:turnsHasMore,page:turnPage};
    }finally{if(turnsBusyToken===requestToken)turnsBusyToken=null;}
  }
  function validTurnPage(items){const ids=new Set(),sequences=new Set();for(const turn of items){if(!turn||typeof turn.id!=='string'||!turn.id||!Number.isSafeInteger(turn.sequence)||turn.sequence<1||ids.has(turn.id)||sequences.has(turn.sequence))return false;ids.add(turn.id);sequences.add(turn.sequence);}return true;}
  function mergeTurns(existing,incoming){const byId=new Map();for(const turn of [...existing,...incoming])byId.set(turn.id,turn);return [...byId.values()].sort((a,b)=>a.sequence-b.sequence);}
  function pendingChatTurns(){return [...turns,...(recentTurn?[recentTurn]:[])].filter(turn=>turn&&['queued','running'].includes(turn.state));}
  function hasPendingChatWork(){return pendingChatTurns().length>0||Boolean(activeJob?.kind==='chat'&&['queued','running'].includes(activeJob.state));}
  function recoveryCurrent(state,generation=state?.generation){return Boolean(!document.hidden&&state&&pendingChatRecovery===state&&state.generation===generation&&current(state.ticket,state.owner)&&target===state.target&&targetFingerprint===state.fingerprint&&conversation===state.conversation&&conversationSelectionEpoch===state.selection&&pendingChatTurns().some(turn=>turn.job_id===state.jobId));}
  function chatJobFenceCurrent(state){return Boolean(state&&current(state.ticket,state.owner)&&target===state.target&&targetFingerprint===state.fingerprint&&conversation===state.conversation&&conversationSelectionEpoch===state.selection&&activeChatJobFence===state);}
  async function recoverPendingChatJob(ticket,owner,selected=conversation,selection=conversationSelectionEpoch){
    if(!current(ticket,owner)||!selected||conversation!==selected||conversationSelectionEpoch!==selection||!target)return;
    const candidates=pendingChatTurns(),ids=[...new Set(candidates.map(turn=>turn.job_id).filter(id=>typeof id==='string'&&uuidOK(id)))];
    if(!candidates.length){if(pendingChatRecovery?.conversation===selected)pendingChatRecovery=null;return;}
    const state={ticket,owner,target,fingerprint:targetFingerprint,conversation:selected,selection,jobId:ids.length===1?ids[0]:'',generation:++chatRecoveryGeneration,loading:false,error:false};
    if(activeJob){
      if(activeJob.kind==='chat'&&ids.length===1&&activeJob.id===ids[0]&&['queued','running'].includes(activeJob.state)){pendingChatRecovery=null;if(pollTimer===null)schedulePoll(ticket,owner);return;}
      pendingChatRecovery={...state,error:true,reason:'owned-job'};await renderPanel();return;
    }
    pendingChatRecovery=state;
    if(ids.length!==1){state.error=true;state.reason=ids.length?'multiple-jobs':'missing-id';await renderPanel();return;}
    await fetchRecoveredChatJob(state);
  }
  async function fetchRecoveredChatJob(state){
    if(!recoveryCurrent(state))return;
    const generation=++chatRecoveryGeneration;state.generation=generation;state.loading=true;state.error=false;await renderPanel();
    if(!recoveryCurrent(state,generation))return;
    let result;
    try{result=await api(`${API}/jobs/${state.jobId}`);}
    catch(error){if(error?.name==='AbortError'||!recoveryCurrent(state,generation))return;state.loading=false;state.error=true;state.reason='lookup';await renderPanel();if(error?.status===401||error?.status===403)report(error,state.owner,state.ticket);return;}
    if(!recoveryCurrent(state,generation))return;
    if(!result||result.version!==1||result.id!==state.jobId||result.kind!=='chat'||!['queued','running','ready','failed','stale','cancelled'].includes(result.state)){
      state.loading=false;state.error=true;state.reason='mismatch';await renderPanel();return;
    }
    state.loading=false;pendingChatRecovery=null;stopPoll();
    if(['queued','running'].includes(result.state)){activeJob=result;activeChatJobFence=state;pollCount=0;schedulePoll(state.ticket,state.owner);}
    else {activeJob=null;activeChatJobFence=null;try{await loadTurns(state.ticket,state.owner,state.conversation,state.selection);}catch(error){if(current(state.ticket,state.owner)&&target===state.target&&targetFingerprint===state.fingerprint&&conversation===state.conversation&&conversationSelectionEpoch===state.selection)report(error,state.owner,state.ticket);}}
    if(current(state.ticket,state.owner)&&target===state.target&&targetFingerprint===state.fingerprint&&conversation===state.conversation&&conversationSelectionEpoch===state.selection&&(!activeJob||activeJob===result))await renderPanel();
  }
  async function refreshViewedTurns(ticket,owner){if(!current(ticket,owner))return;const selected=conversation,selection=conversationSelectionEpoch;await loadTurns(ticket,owner,selected,selection);if(current(ticket,owner)&&conversation===selected&&conversationSelectionEpoch===selection){await recoverPendingChatJob(ticket,owner,selected,selection);if(activeTab==='chat')await renderPanel();}}
  async function loadMoreTurns(ticket,owner){if(!current(ticket,owner)||turnsBusyToken||!conversation||turnPage>=8||turns.length>=128)return;const selected=conversation,selection=conversationSelectionEpoch,requestToken={ticket,owner};turnsBusyToken=requestToken;try{const page=turnPage+1,data=await api(`${API}/conversations/${selected.id}/turns?page=${page}&order=recent&reply_context=1`);if(!current(ticket,owner)||conversation!==selected||conversationSelectionEpoch!==selection)return;if(data.version!==1||data.id!==selected.id||data.page!==page||!Array.isArray(data.items)||data.items.length>16||typeof data.has_more!=='boolean'||!validTurnPage(data.items))throw new Error('Invalid conversation page');turnPage=page;turnsHasMore=data.has_more;turns=mergeTurns(turns,data.items).slice(-128);if(recentTurn&&turns.some(turn=>turn.job_id===recentTurn.job_id))recentTurn=null;await renderPanel();}catch(error){if(current(ticket,owner)&&conversation===selected&&conversationSelectionEpoch===selection)report(error,owner,ticket);}finally{if(turnsBusyToken===requestToken)turnsBusyToken=null;}}
  async function sendMessage(input,ticket,owner){
    if(!current(ticket,owner)||!conversation||assistantInflightToken||conversationLoading||conversationCreating||conversationDeleting)return;
    if(editorialContextPreflight){showStatus(t('editorialContextChecking'),'pending');return;}
    if(editorialContextNeedsDecision()){showStatus(t('editorialContextChoose'),'pending');return;}
    if(!messageDraft&&hasPendingChatWork()){showStatus(t('chatPendingSendBlocked'),'pending');await renderPanel();return;}
    if(!messageDraft){const text=input.value;if(!safeText(text,4096)){showStatus(t('textRequired'),'error');return;}messageDraft={id:uuid(),text,editorialContext:editorialContextSelected()};if(!messageDraft.id)return;}
    const selected=conversation,selection=conversationSelectionEpoch,draft=messageDraft,form=input.parentNode?.parentNode,submit=form?.querySelector('button[type="submit"]'),inflightToken={ticket,owner};assistantInflightToken=inflightToken;if(submit)submit.disabled=true;const contextToggle=form?.querySelector('.memory-editorial-context-toggle');if(contextToggle)contextToggle.disabled=true;
    try{const job=await api(`${API}/conversations/${selected.id}/turns${draft.editorialContext?'?editorial_context=1':''}`,{method:'POST',body:{revision:String(target.revision),mutation_id:draft.id,text:draft.text}});if(!current(ticket,owner)||conversation!==selected||conversationSelectionEpoch!==selection)return;
      messageDraft=null;if(chatTextDraft===draft.text){chatTextDraft='';conversationDrafts.set(selected.id,'');}activeJob=job;activeChatJobFence={ticket,owner,target,fingerprint:targetFingerprint,conversation:selected,selection,generation:++chatRecoveryGeneration};recentTurn={job_id:job.id,input_text:draft.text,reply_text:job.result?.reply||null,reply_kind:job.result?.kind||null,state:job.state};pollCount=0;if(assistantInflightToken===inflightToken)assistantInflightToken=null;await loadTurns(ticket,owner,selected,selection);if(!current(ticket,owner)||conversation!==selected||conversationSelectionEpoch!==selection)return;await renderPanel();if(['queued','running'].includes(job.state))schedulePoll(ticket,owner);
    }catch(error){if(assistantInflightToken===inflightToken)assistantInflightToken=null;if(current(ticket,owner)&&conversation===selected&&conversationSelectionEpoch===selection){if(error?.status===409){messageDraft=null;if(draft.editorialContext){if(!chatTextDraft)chatTextDraft=draft.text;requireEditorialContextDecision('editorialContextChanged');}}await renderPanel();report(error,owner,ticket);}}
    finally{if(assistantInflightToken===inflightToken)assistantInflightToken=null;if(submit)submit.disabled=false;}
  }
  function schedulePoll(ticket,owner){
    if(document.hidden||pollCount>=30)return;stopPoll(false);pollTimer=setTimeout(()=>{pollTimer=null;pollCount++;void pollJob(ticket,owner,true);},1000);
  }
  async function pollJob(ticket,owner,automatic=false){
    const requestedJob=activeJob,visibility=jobVisibilityEpoch;if(document.hidden||!requestedJob?.id)return;
    const chatFence=requestedJob.kind==='chat'?activeChatJobFence:null;if(chatFence&&!chatJobFenceCurrent(chatFence))return;
    let result;
    try{result=await api(`${API}/jobs/${requestedJob.id}`);}
    catch(error){if(error?.name==='AbortError'||document.hidden||visibility!==jobVisibilityEpoch||!current(ticket,owner)||activeJob!==requestedJob||chatFence&&!chatJobFenceCurrent(chatFence))return;stopPoll();report(error,owner,ticket);return;}
    if(document.hidden||visibility!==jobVisibilityEpoch||!current(ticket,owner)||activeJob!==requestedJob||chatFence&&!chatJobFenceCurrent(chatFence)||result?.id!==requestedJob.id||result?.kind!==requestedJob.kind)return;
    activeJob=result;
    if(['queued','running'].includes(result.state)){if(automatic)schedulePoll(ticket,owner);}
    else {stopPoll();if(conversation){try{await loadTurns(ticket,owner);}catch(error){if(activeJob===result&&current(ticket,owner))report(error,owner,ticket);}}}
    const visibleTab=requestedJob.kind==='chat'?'chat':requestedJob.kind==='narrative'?'ideas':null;
    if(current(ticket,owner)&&activeJob===result&&(!automatic||activeTab===visibleTab))await renderPanel();
  }
  async function cancelJob(id,reportError=true){
    const ticket=epoch,owner=accountKey(scopeNow()),prior=activeJob?.id===id?activeJob:null,chatFence=prior?.kind==='chat'?activeChatJobFence:null;
    if(!current(ticket,owner)||!prior)return;
    if(chatFence&&!chatJobFenceCurrent(chatFence))return;
    stopPoll();const cancelFence={...prior};activeJob=cancelFence;
    let result;
    try{result=await api(`${API}/jobs/${id}`,{method:'DELETE'});}
    catch(error){if(!current(ticket,owner)||activeJob!==cancelFence||chatFence&&!chatJobFenceCurrent(chatFence))return;
      activeJob=prior;
      if(!document.hidden&&['queued','running'].includes(prior.state))schedulePoll(ticket,owner);
      if(reportError)report(error,owner,ticket);
      return;
    }
    if(!current(ticket,owner)||activeJob!==cancelFence||chatFence&&!chatJobFenceCurrent(chatFence)||result?.id!==prior.id||result?.kind!==prior.kind)return;
    activeJob=result;
    if(conversation){try{await loadTurns(ticket,owner);}catch(error){if(current(ticket,owner)&&activeJob===result&&reportError)report(error,owner,ticket);}}
    if(!current(ticket,owner)||activeJob!==result)return;
    if(reportError)await renderPanel();
  }
  function renderCompanionProposal(root,result,ticket,owner){
    if(!result||result.kind!=='proposal'||!result.proposal)return;
    const box=el('section','','memory-community-proposal');box.append(el('h3',t('proposal')),el('p',result.proposal.title||''));
    box.append(el('p',result.reply||''));
    const renderId=panelRenderEpoch,renderTarget=target,renderFingerprint=targetFingerprint;
    renderProposalChapters(box,result.proposal.chapters||[],node=>current(ticket,owner)&&activeTab==='chat'&&target===renderTarget&&targetFingerprint===renderFingerprint&&panelRenderEpoch===renderId&&root.parentNode===panelNode&&node.isConnected!==false);
    renderQuestions(box,result.proposal.questions||result.questions||[]);
    if(target.type==='story'&&canEdit())box.append(btn(t('adopt'),()=>emitProposal(result.proposal,ticket,owner),'memory-community-primary'));
    root.append(box);
  }
  function renderQuestions(root,questions){if(!Array.isArray(questions)||!questions.length)return;root.append(el('h4',t('questions')));const list=el('ul');for(const item of questions)list.append(el('li',item));root.append(list);}
  function proposalChapterTitle(id,index){
    if(target?.type==='story'){const chapter=target.chapters?.find(item=>item.id===id);return chapter?.title||`${t('chapterNumber')} ${index+1}`;}
    const match=typeof id==='string'&&id.match(/^([0-9a-f-]{36})-chapter-([1-6])$/);const story=match&&target?.stories?.find(item=>item.id===match[1]);
    return story?`${story.title} · ${t('chapterNumber')} ${match[2]}`:`${t('chapterNumber')} ${index+1}`;
  }
  function proposalSource(id,index){
    if(typeof id!=='string')return {label:`${t('sourceOther')} ${index+1}`,text:t('sourceNotLoaded')};
    if(id.startsWith('contribution-')){const value=contributionList.find(item=>'contribution-'+item.id===id);if(!value)return {label:`${t('sourceOther')} ${index+1}`,text:t('sourceNotLoaded')};const label=value.kind==='audio'?t('sourceTranscript'):value.kind==='text'?t('sourceFamily'):t('sourceOther');return {label:label+(value.byline?` · ${value.byline}`:''),text:value.kind==='text'?value.text||t('sourceNotLoaded'):t('sourceNotLoaded'),contribution:value.kind==='audio'&&value.state==='accepted'&&target?.type==='story'?value:null};}
    if(target?.type==='memoir'&&id==='editorial-book-'+target.id)return {label:t('sourceBookOpening'),text:target.introduction||t('sourceNotLoaded')};
    if(id.startsWith('editorial-'))return {label:t('sourceEditorial'),text:t('sourceNotLoaded')};
    for(const item of target?.items||[]){const evidence=item.evidence?.find(value=>value.id===id);if(evidence)return {label:['ai','caption','ai_caption'].includes(evidence.source)?t('sourceAI'):evidence.source==='family'?t('sourceFamily'):evidence.source==='metadata'?t('sourceMetadata'):t('sourceOther'),text:evidence.text||t('sourceNotLoaded')};}
    return {label:`${t('sourceOther')} ${index+1}`,text:t('sourceNotLoaded')};
  }
  function isValidReplyQuestions(value){return Array.isArray(value)&&value.length<=3&&value.every(question=>safeText(question,512));}
  function validatedReplyQuestions(value){return isValidReplyQuestions(value)?value:[];}
  function isValidReplySourceIds(value){return Array.isArray(value)&&value.length<=96&&value.every(id=>typeof id==='string'&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(id))&&new Set(value).size===value.length;}
  function validatedReplySourceIds(value){return isValidReplySourceIds(value)?value:[];}
  function chatReplyMetadata(turn,ticket,owner,editorTarget,editorFingerprint,editorConversation,editorSelection){
    const sameRenderScope=current(ticket,owner)&&target===editorTarget&&targetFingerprint===editorFingerprint&&conversation===editorConversation&&
      conversationSelectionEpoch===editorSelection&&activeTab==='chat'&&conversation?.id===editorConversation?.id;
    const job=activeJob;
    const matchingReadyJob=sameRenderScope&&turn?.state==='ready'&&job?.kind==='chat'&&job.state==='ready'&&job.id===turn.job_id&&
      job.result?.reply===turn.reply_text&&job.result?.kind===turn.reply_kind;
    const hasQuestions=Object.prototype.hasOwnProperty.call(turn||{},'reply_questions');
    const hasSources=Object.prototype.hasOwnProperty.call(turn||{},'reply_source_ids');
    const hasHistoryMetadata=hasQuestions||hasSources;
    const historyMetadataValid=sameRenderScope&&hasQuestions&&hasSources&&isValidReplyQuestions(turn.reply_questions)&&isValidReplySourceIds(turn.reply_source_ids);
    const jobMetadataValid=sameRenderScope&&!hasHistoryMetadata&&matchingReadyJob&&isValidReplyQuestions(job.result?.questions)&&isValidReplySourceIds(job.result?.source_ids);
    if(historyMetadataValid)return {questions:turn.reply_questions,sourceIds:turn.reply_source_ids,validated:true};
    if(jobMetadataValid)return {questions:job.result.questions,sourceIds:job.result.source_ids,validated:true};
    return {questions:[],sourceIds:[],validated:false};
  }
  function isValidatedClarification(turn,metadata){return turn?.state==='ready'&&turn.reply_kind==='clarification'&&safeText(turn.reply_text,4000)&&metadata?.validated===true;}
  function renderSourceTranscript(row,source,authorized){
    const contribution=source.contribution;if(!contribution||target?.type!=='story')return;
    const action=btn(t('sourceViewTranscript'),()=>void loadSourceTranscript(row,contribution,action,status,body,authorized),'memory-community-button memory-source-transcript-action');
    const status=el('p','','memory-source-transcript-status');status.setAttribute('role','status');
    const body=el('div','','memory-source-transcript-body');body.hidden=true;
    row.append(action,status,body);
  }
  async function loadSourceTranscript(row,item,button,status,body,authorized){
    const permitted=()=>target?.type==='story'&&contributionList.includes(item)&&authorized(button);
    if(!permitted()||button.disabled)return;
    if(!body.hidden){body.hidden=true;button.textContent=t('sourceViewTranscript');return;}
    button.disabled=true;status.textContent='';
    try{
      const detail=await api(`${pathStory()}/${item.id}`);
      if(!permitted()||!row.isConnected)return;
      if(!validContributionDetail(detail,item,target.id))throw new Error('Invalid contribution detail');
      const derivation=detail.derivation;
      if(!derivation||derivation.state!=='ready'){
        status.textContent=derivation?t('sourceTranscriptPending'):t('sourceTranscriptMissing');return;
      }
      if(typeof derivation.transcript!=='string'||!safeText(derivation.transcript,8192)){
        status.textContent=t('sourceTranscriptMissing');return;
      }
      body.replaceChildren(el('p',`${t('sourceTranscriptAI')}${detail.byline||item.byline||''}`,'memory-community-meta'),el('p',derivation.transcript));
      body.hidden=false;button.textContent=t('sourceHideTranscript');
    }catch(error){
      if(!permitted())return;
      if(error?.status===401||error?.status===403)report(error,accountKey(scopeNow()),epoch);
      else status.textContent=t('sourceTranscriptRetry');
    }finally{if(permitted())button.disabled=false;}
  }
  function renderChatReplySources(card,metadata,authorized){
    if(!metadata.sourceIds.length)return;
    const details=el('details','','memory-proposal-sources memory-chat-reply-sources');
    details.append(el('summary',`${t('refs')} · ${metadata.sourceIds.length} ${t('sourceCount')}`));
    details.append(el('p',t('chatFollowupSourcesNote'),'memory-community-help'));
    const list=el('ol');metadata.sourceIds.forEach((id,index)=>{const source=proposalSource(id,index),row=el('li');row.append(el('strong',source.label),el('p',source.text));renderSourceTranscript(row,source,authorized);list.append(row);});
    details.append(list);card.append(details);
  }
  function renderReadingChapterPrompt(form,input,editorCurrent,editorTarget){
    const component=mount,reader=component?.closest?.('.memory-book-reader');
    if(editorTarget?.type!=='memoir'||!reader||typeof reader.__photoHouseReadingContext!=='function')return;
    const section=el('section','','memory-chat-reading-context'),status=el('p','','memory-chat-reading-status');status.setAttribute('role','status');
    const button=btn(t('readingChapterPrompt'),()=>{
      const authorized=()=>editorCurrent(button)&&!document.hidden&&mount===component&&mount?.closest?.('.memory-book-reader')===reader&&reader.open&&reader.contains(component);
      if(!authorized())return;
      const reason=chatDraftInsertionBlocked(input);if(reason){status.textContent=reason;return;}
      let context;try{context=reader.__photoHouseReadingContext();}catch(_){context=null;}
      if(!authorized())return;
      const child=editorTarget.stories.find(item=>item.id===context?.story_id&&String(item.revision)===context?.story_revision);
      if(!context||Object.keys(context).sort().join(',')!=='book_id,book_revision,chapter_id,chapter_title,story_id,story_revision,story_title'||context.book_id!==editorTarget.id||context.book_revision!==String(editorTarget.revision)||!child||!/^chapter-[1-6]$/.test(context.chapter_id)||!safeText(context.story_title,512)||!safeText(context.chapter_title,512)){status.textContent=t('readingChapterUnavailable');return;}
      const number=context.chapter_id.slice(8),question=lang()==='en'?`I am reading "${context.story_title}", chapter ${number}: "${context.chapter_title}". What do the existing sources tell us about this chapter, and what is one useful question to ask the family? Keep uncertainties and do not invent experiences.`:`我正在读《${context.story_title}》的第 ${number} 章《${context.chapter_title}》。请先说明已有来源讲了什么，再提出一个值得问问家人的问题。保留不确定之处，不要补造经历。`;
      if(!safeText(question,4096)){status.textContent=t('readingChapterUnavailable');return;}
      chatTextDraft=question;conversationDrafts.set(conversation.id,question);input.value=question;form.querySelector('.memory-chat-starters')?.remove();
      input.focus();try{input.setSelectionRange(input.value.length,input.value.length);}catch(_){}status.textContent=t('chatFollowupReview');
    },'memory-community-button memory-chat-reading-prompt');
    section.append(button,el('p',t('readingChapterHelp'),'memory-community-help'),status);form.prepend(section);
  }
  function chatDraftInsertionBlocked(input){
    if(chatComposition?.composing||chatComposition?.endSeen&&!chatComposition.finalInput||chatRenderDeferred)return t('chatFollowupImeBlocked');
    if(chatTextDraft.length>0||input.value.length>0)return t('chatFollowupDraftBlocked');
    if(messageDraft||assistantInflightToken)return t('chatFollowupSendBlocked');
    if(chatRecordingBusy||chatCaptureStarting||chatCaptureHandle||chatCaptureReady||chatTranscribing||chatTranscript)return t('chatFollowupDictationBlocked');
    if(conversationLoading||conversationCreating||conversationDeleting)return t('chatFollowupSendBlocked');
    if(activeJob?.kind==='chat'&&['queued','running'].includes(activeJob.state)||turns.some(turn=>['queued','running'].includes(turn.state))||['queued','running'].includes(recentTurn?.state))return t('chatFollowupJobBlocked');
    return '';
  }
  function renderChatFollowups(card,turn,input,ticket,owner,editorCurrent,metadata){
    if(!metadata.questions.length)return;
    const section=el('section','','memory-chat-followups');section.append(el('h4',t('chatFollowups')));section.append(el('p',t('chatFollowupHelp'),'memory-community-help'));
    const actions=el('div','','memory-chat-followup-actions'),status=el('p','','memory-chat-followup-status');status.setAttribute('role','status');
    metadata.questions.forEach(question=>{
      const button=btn(question,()=>{
        if(!editorCurrent(button)||!current(ticket,owner)||target!==targetAtRender||conversation!==conversationAtRender||conversationSelectionEpoch!==selectionAtRender)return;
        const reason=chatDraftInsertionBlocked(input);if(reason){status.textContent=reason;return;}
        chatTextDraft=question;conversationDrafts.set(turnConversationId,question);input.value=question;
        input.focus();try{input.setSelectionRange(input.value.length,input.value.length);}catch(_){}
        status.textContent=t('chatFollowupReview');
      },'memory-community-button memory-chat-followup-question');
      const targetAtRender=target,conversationAtRender=conversation,selectionAtRender=conversationSelectionEpoch,turnConversationId=conversation?.id;
      actions.append(button);
    });
    section.append(actions,status);card.append(section);
  }
  function renderProposalChapters(box,chapters,authorized,options={}){
    const savedEdition=options.savedEdition===true,chapterLabel=savedEdition?t('savedChapter'):t('draftChapter'),reviewLabel=savedEdition?t('savedProposalReview'):t('proposalReview'),directoryLabel=savedEdition?t('savedMemoirDirectory'):t('memoirDraftDirectory'),currentLabel=savedEdition?t('savedMemoirCurrent'):t('memoirDraftCurrent'),speechDisposers=options.speechDisposers;
    const rendered=[];
    chapters.forEach((chapter,index)=>{const title=proposalChapterTitle(chapter.id,index),item=el('article','','memory-community-proposal-chapter'),heading=el('h4',title);heading.tabIndex=-1;heading.id=`${savedEdition?'memory-saved-edition':'memory-proposal'}-chapter-${instanceId}-${panelRenderEpoch}-${index}`;if(target?.type==='memoir'){heading.style.overflowWrap='anywhere';item.style.scrollMarginTop='6rem';item.append(el('p',`${chapterLabel} · ${index+1}/${chapters.length}`,'memory-proposal-position memory-community-meta'));}item.append(heading,el('strong',reviewLabel,'memory-proposal-review-label'),el('p',chapter.narration||''));
      if(typeof mountReplySpeech==='function'&&typeof chapter.narration==='string'&&chapter.narration.trim()){const speechControls=el('div','','memory-proposal-chapter-speech');item.append(speechControls);try{const dispose=mountReplySpeech(speechControls,chapter.narration,target?.language,()=>authorized(speechControls)&&authorized(item)&&!isCapturing(),savedEdition?'edition':'draft',lang());if(typeof dispose==='function'){replySpeechDisposers.add(dispose);speechDisposers?.add(dispose);}}catch(_){speechControls.remove();}}
      const current=target?.type==='story'&&Array.isArray(target.chapters)?target.chapters.find(candidate=>candidate?.id===chapter.id):null;
      const original=safeText(current?.narration,6000)?current.narration:null;
      if(original!==null){if(original===chapter.narration)item.append(el('p',t('unchangedChapter'),'memory-proposal-unchanged'));const comparison=el('details','','memory-proposal-comparison');comparison.append(el('summary',t('compareChapter')));const content=el('div','','memory-proposal-comparison-content');content.append(el('strong',t('currentChapter')),el('p',original));comparison.append(content);item.append(comparison);}
      const ids=Array.isArray(chapter.source_ids)?chapter.source_ids:[];if(ids.length){const sources=el('details','','memory-proposal-sources');sources.append(el('summary',`${t('refs')} · ${ids.length} ${t('sourceCount')}`));const list=el('ol');ids.forEach((id,sourceIndex)=>{const row=el('li');if(savedEdition&&typeof options.onSourceReference==='function'){const select=btn(`${et('shelfSourceInspect')} ${sourceIndex+1}`,()=>options.onSourceReference(id),'memory-edition-source-reference');row.append(select);}else{const source=proposalSource(id,sourceIndex);row.append(el('strong',source.label),el('p',source.text));renderSourceTranscript(row,source,authorized);}list.append(row);});sources.append(list);item.append(sources);}rendered.push({chapter,index,title,item,heading});});
    if(target?.type==='memoir'&&rendered.length>0&&rendered.length<=24){
      const directory=el('details','','memory-memoir-proposal-directory'),summary=el('summary',directoryLabel),nav=el('nav'),list=el('ol'),status=el('p','','memory-memoir-proposal-current');
      directory.style.minWidth='0';summary.style.display='list-item';summary.style.listStylePosition='inside';summary.style.maxWidth='100%';summary.style.whiteSpace='normal';summary.style.overflowWrap='anywhere';nav.style.minWidth='0';list.style.minWidth='0';nav.setAttribute('aria-label',directoryLabel);status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.hidden=true;
      let currentButton=null;
      for(const entry of rendered){
        const row=el('li'),jump=btn(entry.title,()=>{
          if(!authorized(jump)||!authorized(entry.item)||!entry.item.isConnected||!entry.heading.isConnected||!box.contains(entry.item)||entry.chapter.id!==chapters[entry.index]?.id||entry.heading.textContent!==entry.title)return;
          if(isCapturing())return;
          notifyAudioStart();
          if(!authorized(jump)||!authorized(entry.item)||!entry.item.isConnected||!entry.heading.isConnected||!box.contains(entry.item)||entry.chapter.id!==chapters[entry.index]?.id||entry.heading.textContent!==entry.title)return;
          if(currentButton)currentButton.removeAttribute('aria-current');
          currentButton=jump;jump.setAttribute('aria-current','location');status.textContent=currentLabel(entry.title);status.hidden=false;directory.open=false;
          entry.heading.focus?.({preventScroll:true});entry.item.scrollIntoView?.({block:'start',behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'auto':'smooth'});
        },'memory-memoir-proposal-jump');row.style.minWidth='0';jump.style.display='block';jump.style.width='100%';jump.style.maxWidth='100%';jump.style.margin='0 0 .5rem';jump.style.whiteSpace='normal';jump.style.overflowWrap='anywhere';jump.style.textAlign='left';
        jump.setAttribute('aria-controls',entry.heading.id);row.append(jump);list.append(row);
      }
      nav.append(list);directory.append(summary,nav);box.append(directory,status);
    }
    rendered.forEach(entry=>box.append(entry.item));
  }
  async function renderIdeas(root,ticket,owner){
    ideaRecordButton=null;
    root.append(el('p',t('ideasHelp'),'memory-community-help'));
    const frozen=pendingJob,formChoice=frozen?.formChoice??memoirFormChoice,baseInstructions=ideaDraft;
    const busy=Boolean(frozen||assistantInflightToken||editorialContextPreflight||ideaCaptureStarting||ideaCaptureHandle||ideaTranscribing||ideaTranscript);
    const form=el('form','','memory-community-form');
    if(target?.type==='memoir'){
      const formDetails=el('details','','memory-memoir-form-choice'),summary=el('summary',t('memoirForm'));
      const formLabel=el('label',t('memoirFormPrompt'));const formSelect=el('select');formSelect.name='memoir_form';formSelect.className='memory-memoir-form-select';formSelect.setAttribute('aria-label',t('memoirForm'));formSelect.disabled=busy;
      for(const [value,key] of [['existing','memoirFormExisting'],['chronicle','memoirFormChronicle'],['essay','memoirFormEssay'],['long_memoir','memoirFormLong']]){const option=el('option',t(key));option.value=value;formSelect.append(option);}
      formSelect.value=formChoice;formSelect.addEventListener('change',()=>{if(!ideaEditorCurrent(formSelect,ticket,owner,root)||pendingJob||assistantInflightToken||editorialContextPreflight||ideaVoicePending()||!['existing','chronicle','essay','long_memoir'].includes(formSelect.value)){formSelect.value=formChoice;return;}memoirFormChoice=formSelect.value;});formLabel.append(formSelect);formDetails.append(summary,formLabel);form.append(formDetails);
    }
    const label=el('label',t('instruction'));const input=el('textarea');input.name='instructions';input.rows=3;input.value=baseInstructions;input.className='memory-community-ideas-instructions';input.setAttribute('aria-label',t('instruction'));input.disabled=Boolean(assistantInflightToken||editorialContextPreflight);input.addEventListener('input',()=>ideaDraft=input.value);bindIdeaComposition(input,'instructions',ticket,owner,root);label.append(input);form.append(label);const voiceSlot=el('div','','memory-community-ideas-voice-slot');form.append(voiceSlot);
    const editorialChoiceControl=renderEditorialContextChoice(form,'ideas',ticket,owner);
    const submit=el('button',pendingJob?t('retryJob'):t('generate'));submit.type='submit';submit.className='memory-community-primary';submit.disabled=!canEdit()||Boolean(editorialContextPreflight||assistantInflightToken||ideaVoicePending());form.append(submit);editorialChoiceControl?.sync();
    form.addEventListener('submit',event=>{event.preventDefault();void generateSuggestion(input,ticket,owner);});root.append(form);const recordButton=await renderIdeaVoiceControls(voiceSlot,ticket,owner,root,input);if(editorialChoiceControl)editorialChoiceControl.recordButton=recordButton;
    if(activeJob?.kind==='narrative')renderNarrativeJob(root,activeJob,ticket,owner);
  }
  function ideaEditorCurrent(node,ticket,owner,root){return current(ticket,owner)&&target&&activeTab==='ideas'&&root.parentNode===panelNode&&node.isConnected!==false;}
  function ideaCompositionCurrent(state){return Boolean(state&&state===ideaComposition&&state.ticket===epoch&&current(state.ticket,state.owner)&&target===state.target&&targetFingerprint===state.fingerprint&&activeTab==='ideas'&&state.renderId===panelRenderEpoch&&state.root?.parentNode===panelNode&&state.input?.isConnected!==false);}
  function clearIdeaComposition(){if(ideaComposition?.timer)clearTimeout(ideaComposition.timer);ideaComposition=null;ideaRenderDeferred=false;}
  function assignIdeaCompositionValue(state){if(state.field==='instructions')ideaDraft=state.input.value;else ideaTranscript=state.input.value;}
  function flushDeferredIdeaRender(state){if(!ideaCompositionCurrent(state)||state.composing||!state.endSeen||!state.finalInput||!ideaRenderDeferred)return;if(state.timer)clearTimeout(state.timer);ideaComposition=null;ideaRenderDeferred=false;void renderPanel();}
  function bindIdeaComposition(input,field,ticket,owner,root){
    input.addEventListener('input',()=>{const state=ideaComposition;if(!ideaEditorCurrent(input,ticket,owner,root)&&!(state?.input===input&&ideaCompositionCurrent(state)))return;ideaDraft=field==='instructions'?input.value:ideaDraft;if(field==='transcript')ideaTranscript=input.value;if(state?.input===input&&state.endSeen){assignIdeaCompositionValue(state);state.finalInput=true;if(state.timer)clearTimeout(state.timer);flushDeferredIdeaRender(state);}});
    input.addEventListener('compositionstart',()=>{if(!ideaEditorCurrent(input,ticket,owner,root))return;clearIdeaComposition();ideaComposition={input,field,ticket,owner,target,fingerprint:targetFingerprint,tab:'ideas',renderId:panelRenderEpoch,root,composing:true,endSeen:false,finalInput:false,timer:null};});
    input.addEventListener('compositionend',()=>{const state=ideaComposition;if(state?.input!==input||!ideaCompositionCurrent(state))return;state.composing=false;state.endSeen=true;state.timer=setTimeout(()=>{if(!ideaCompositionCurrent(state))return;if(!state.finalInput){assignIdeaCompositionValue(state);state.finalInput=true;}flushDeferredIdeaRender(state);},50);});
  }
  async function renderIdeaVoiceControls(slot,ticket,owner,root,input){
    const voice=await resolveVoiceCapabilities(ticket,owner);if(!current(ticket,owner)||activeTab!=='ideas'||root.parentNode!==panelNode)return;
    if(!voice?.transcribe||!capture||!transcribe)return null;
    const section=el('section','','memory-community-ideas-voice');section.append(el('h3',t('ideaVoice')),el('p',t('ideaVoiceHelp'),'memory-community-help'));
    const record=btn(t('ideaVoiceRecord'),()=>{if(!ideaEditorCurrent(record,ticket,owner,root)||ideaVoicePending()||editorialContextPreflight||pendingJob||isCapturing()||chatTranscribing)return;void beginIdeaCapture(ticket,owner,root);},'memory-community-button');record.disabled=ideaVoicePending()||Boolean(editorialContextPreflight||pendingJob||captureStarting||captureHandle||chatRecordingBusy||chatCaptureHandle||chatTranscribing);
    ideaRecordButton=record;
    section.append(record);
    if(ideaCaptureHandle){const stop=btn(t('ideaVoiceStop'),()=>{if(!ideaEditorCurrent(stop,ticket,owner,root))return;void finishIdeaCapture(ticket,owner,ideaVoiceTicket);},'memory-community-primary');section.append(stop);}
    else if(ideaCaptureStarting){const waiting=el('p',t('ideaVoiceWaiting'),'memory-community-status');waiting.setAttribute('role','status');waiting.setAttribute('aria-live','polite');section.append(waiting);}
    else if(ideaTranscribing){const waiting=el('p',t('ideaVoiceTranscribing'),'memory-community-status');waiting.setAttribute('role','status');waiting.setAttribute('aria-live','polite');section.append(waiting);}
    if(ideaVoiceError){const error=el('p',t(ideaVoiceError),'memory-community-status');error.setAttribute('role','status');error.setAttribute('aria-live','polite');section.append(error);}
    if(ideaTranscript){const transcriptLabel=el('label',t('ideaVoiceTranscript'));const transcript=el('textarea');transcript.rows=3;transcript.value=ideaTranscript;transcript.className='memory-community-ideas-transcript';transcript.setAttribute('aria-label',t('ideaVoiceTranscript'));transcript.addEventListener('input',()=>{if(ideaEditorCurrent(transcript,ticket,owner,root))ideaTranscript=transcript.value;});bindIdeaComposition(transcript,'transcript',ticket,owner,root);transcriptLabel.append(transcript);section.append(transcriptLabel);
      const insert=btn(t('ideaVoiceInsert'),()=>{if(!ideaEditorCurrent(insert,ticket,owner,root))return;const instructions=input.value,transcriptText=transcript.value,combined=instructions&&transcriptText?`${instructions}\n${transcriptText}`:instructions+transcriptText,freezing=frozenIdeaInstructions(combined,memoirFormChoice);if(!boundedText(freezing,4096)){const invalid=!wellFormed(freezing)||/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/u.test(freezing);showStatus(t(invalid?'ideaVoiceInvalid':'ideaVoiceOverflow'),'error');return;}ideaDraft=combined;ideaTranscript='';const inserted=t('ideaVoiceInserted');void renderPanel().then(()=>showStatus(inserted,'success'));},'memory-community-button');const discard=btn(t('ideaVoiceDiscard'),()=>{if(!ideaEditorCurrent(discard,ticket,owner,root))return;ideaTranscript='';ideaVoiceError='';void renderPanel();},'memory-community-button');section.append(insert,discard);}
    slot.append(section);
    return record;
  }
  async function beginIdeaCapture(ticket,owner,root){
    if(!capture||!transcribe||!voiceCapabilitiesValue?.transcribe||ideaVoicePending()||editorialContextPreflight||pendingJob||isCapturing()||chatTranscribing||!ideaEditorCurrent(root,ticket,owner,root)||document.hidden)return;
    stopPlayback();notifyAudioStart();const voiceTicket=++ideaVoiceEpoch;ideaVoiceTicket=voiceTicket;ideaVoiceError='';ideaCaptureStarting=true;
    try{if(!current(ticket,owner)||voiceTicket!==ideaVoiceEpoch||targetFingerprint!==targetScopeFingerprint(owner,target)||document.hidden)return;let resolveCaptured;const ready=new Promise(resolve=>{resolveCaptured=resolve;});const captureRequest=capture(file=>resolveCaptured(file),voiceCapabilitiesValue.max_audio_seconds);void renderPanel();const handle=await captureRequest;
      if(!current(ticket,owner)||voiceTicket!==ideaVoiceEpoch||targetFingerprint!==targetScopeFingerprint(owner,target)||document.hidden||activeTab!=='ideas'){await handle.stop(false);return;}
      ideaCaptureHandle=handle;ideaCaptureReady=ready;ideaCaptureStarting=false;ideaCaptureTimer=setTimeout(()=>void finishIdeaCapture(ticket,owner,voiceTicket),31000);await renderPanel();
    }catch(error){if(current(ticket,owner)&&voiceTicket===ideaVoiceEpoch){ideaCaptureStarting=false;ideaVoiceError=error?.name==='NotAllowedError'||error?.name==='SecurityError'?'ideaVoicePermissionFailed':'ideaVoiceCaptureFailed';notifyError(error);await renderPanel();}}
  }
  async function finishIdeaCapture(ticket,owner,voiceTicket=ideaVoiceTicket){
    const handle=ideaCaptureHandle;if(!handle||!current(ticket,owner)||voiceTicket!==ideaVoiceEpoch||activeTab!=='ideas')return;if(ideaCaptureTimer)clearTimeout(ideaCaptureTimer);ideaCaptureTimer=null;ideaCaptureHandle=null;
    ideaTranscribing=true;void renderPanel();
    try{const ready=ideaCaptureReady;ideaCaptureReady=null;const stopped=await handle.stop(true),file=stopped||await ready;if(!ideaCaptureCurrent(ticket,owner,voiceTicket)||document.hidden)return;if(!file)throw new Error('Captured audio unavailable');if(!ideaCaptureCurrent(ticket,owner,voiceTicket)||document.hidden)return;const result=await transcribe(file);if(!ideaCaptureCurrent(ticket,owner,voiceTicket)||document.hidden)return;if(!result||result.version!==1||typeof result.text!=='string'||!wellFormed(result.text)||!result.text.trim())throw new Error('Transcript unavailable');ideaTranscript=result.text;ideaVoiceError='';ideaTranscribing=false;await renderPanel();}
    catch(error){if(ideaCaptureCurrent(ticket,owner,voiceTicket)){ideaTranscribing=false;ideaVoiceError=error?.name==='AbortError'?'':'ideaVoiceAsrFailed';if(error?.name!=='AbortError')notifyError(error);await renderPanel();}}
  }
  function ideaCaptureCurrent(ticket,owner,voiceTicket){return current(ticket,owner)&&voiceTicket===ideaVoiceEpoch&&activeTab==='ideas'&&targetFingerprint===targetScopeFingerprint(owner,target);}
  async function generateSuggestion(input,ticket,owner){
    if(!canEdit()||assistantInflightToken)return;
    if(ideaCaptureStarting||ideaCaptureHandle||ideaTranscribing||ideaTranscript){showStatus(t('ideaVoiceReviewRequired'),'error');return;}
    if(editorialContextPreflight){showStatus(t('editorialContextChecking'),'pending');return;}
    if(editorialContextNeedsDecision()){showStatus(t('editorialContextChoose'),'pending');return;}
    if(!leaveEditionForNextAction())return;
    if(!pendingJob){const baseInstructions=input.value,formChoice=target?.type==='memoir'?memoirFormChoice:'existing',instructions=frozenIdeaInstructions(baseInstructions,formChoice);if(!boundedText(instructions,4096)){const invalid=!wellFormed(instructions)||/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/u.test(instructions);showStatus(t(invalid?'ideaVoiceInvalid':'ideaVoiceTooLong'),'error');return;}pendingJob={id:uuid(),baseInstructions,formChoice,instructions,editorialContext:editorialContextSelected()};if(!pendingJob.id)return;}
    const pending=pendingJob,form=input.parentNode?.parentNode,submit=form?.querySelector('button[type="submit"]'),inflightToken={ticket,owner};assistantInflightToken=inflightToken;if(submit)submit.disabled=true;const contextToggle=form?.querySelector('.memory-editorial-context-toggle');if(contextToggle)contextToggle.disabled=true;const formSelect=form?.querySelector('select[name="memoir_form"]');if(formSelect)formSelect.disabled=true;input.disabled=true;if(ideaRecordButton)ideaRecordButton.disabled=true;
    try{const job=await api(`${API}/jobs${pending.editorialContext?'?editorial_context=1':''}`,{method:'POST',body:{target_type:targetType(),target_id:target.id,revision:String(target.revision),mutation_id:pending.id,instructions:pending.instructions}});if(!current(ticket,owner))return;activeJob=job;pendingJob=null;if(ideaDraft===pending.baseInstructions){ideaDraft='';memoirFormChoice='existing';}pollCount=0;if(assistantInflightToken===inflightToken)assistantInflightToken=null;await renderPanel();if(['queued','running'].includes(job.state))schedulePoll(ticket,owner);}
    catch(error){if(assistantInflightToken===inflightToken)assistantInflightToken=null;if(current(ticket,owner)){if(error?.status===409||error?.status===422){pendingJob=null;if(error?.status===409&&pending.editorialContext)requireEditorialContextDecision('editorialContextChanged');}await renderPanel();report(error,owner,ticket);}}
    finally{if(assistantInflightToken===inflightToken)assistantInflightToken=null;if(submit)submit.disabled=false;}
  }
  function renderNarrativeJob(root,job,ticket,owner){
    const status=['queued','running','ready','failed','stale','cancelled'].includes(job.state)?t(job.state):t('error');
    root.append(el('p',status,'memory-community-job-status'));
    if(job.result){const result=job.result;const box=el('section','','memory-community-proposal'),proposalTitle=el('h4',result.title||'');if(target?.type==='memoir')proposalTitle.style.overflowWrap='anywhere';const proposalHeading=el('h3',t('proposal'));if(target?.type==='memoir'){proposalHeading.style.whiteSpace='normal';proposalHeading.style.overflowWrap='anywhere';}box.append(proposalHeading,proposalTitle);
      const renderId=panelRenderEpoch,renderTarget=target,renderFingerprint=targetFingerprint;
      renderProposalChapters(box,result.chapters||[],node=>current(ticket,owner)&&activeTab==='ideas'&&target===renderTarget&&targetFingerprint===renderFingerprint&&activeJob===job&&panelRenderEpoch===renderId&&root.parentNode===panelNode&&node.isConnected!==false);
      renderQuestions(box,result.questions||[]);if(target.type==='story'&&canEdit())box.append(btn(t('adopt'),()=>emitProposal(result,ticket,owner),'memory-community-primary'));if(target?.type==='memoir'&&editionReview?.jobId===job.id){const original=el('details','','memory-edition-original-draft');original.append(el('summary',et('original')),box);root.append(original);}else root.append(box);}
    if(target?.type==='memoir'&&job.state==='ready'&&job.result&&canEdit()){
      const state=editionReview;
      if(state&&state.bookId===target.id&&state.revision===String(target.revision)&&state.jobId===job.id)renderEditionReview(root,state,ticket,owner);
      else root.append(btn(et('open'),()=>void openEditionReview(job,ticket,owner),'memory-edition-open'));
    }
    if(['queued','running'].includes(job.state)){root.append(btn(t('refresh'),()=>void pollJob(ticket,owner),'memory-community-button'),btn(t('cancel'),()=>void cancelJob(job.id,true),'memory-community-button'));}
  }
  const exactKeys=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
  const editionRevisionOK=value=>typeof value==='string'&&/^[1-9][0-9]{0,18}$/.test(value)&&BigInt(value)<=9223372036854775807n;
  function editionManuscriptOK(value,expected=null){
    if(!exactKeys(value,['version','title','chapters','questions','needs_review'])||value.version!==1||value.needs_review!==true||!safeText(value.title,512)||!Array.isArray(value.chapters)||value.chapters.length<1||value.chapters.length>24||!Array.isArray(value.questions)||value.questions.length>6||value.questions.some(word=>!boundedText(word,512)))return false;
    if(expected&&(value.chapters.length!==expected.chapters.length||JSON.stringify(value.questions)!==JSON.stringify(expected.questions)))return false;
    const ids=new Set();let total=new TextEncoder().encode(value.title).length;
    for(let index=0;index<value.chapters.length;index++){
      const chapter=value.chapters[index],original=expected?.chapters[index];
      if(!exactKeys(chapter,['id','narration','source_ids'])||!/^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-chapter-[1-6]$/.test(chapter.id||'')||ids.has(chapter.id)||!boundedText(chapter.narration,6000)||!Array.isArray(chapter.source_ids)||chapter.source_ids.length>96||new Set(chapter.source_ids).size!==chapter.source_ids.length||chapter.source_ids.some(id=>typeof id!=='string'||!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(id)))return false;
      if(original&&(chapter.id!==original.id||JSON.stringify(chapter.source_ids)!==JSON.stringify(original.source_ids)))return false;
      if(chapter.narration.trim()&&chapter.source_ids.length===0)return false;
      ids.add(chapter.id);total+=new TextEncoder().encode(chapter.narration).length;
    }
    return total+value.questions.reduce((sum,word)=>sum+new TextEncoder().encode(word).length,0)<=65536&&new TextEncoder().encode(JSON.stringify(value)).length<=65536;
  }
  function savedEditionChaptersOK(manuscript){
    const children=target?.stories;
    if(!Array.isArray(children)||children.length<1||children.length>24||!children.every(child=>uuidOK(child?.id)&&editionRevisionOK(String(child.revision)))||new Set(children.map(child=>child.id)).size!==children.length)return false;
    const ordered=children.map(child=>child.id);let childIndex=0,chapterIndex=1,seen=new Set();
    for(const chapter of manuscript.chapters){
      const match=/^([0-9a-f-]{36})-chapter-([1-6])$/.exec(chapter.id||'');if(!match)return false;
      if(match[1]!==ordered[childIndex]){
        if(chapterIndex===1)return false;
        seen.add(ordered[childIndex]);childIndex++;chapterIndex=1;
        if(childIndex>=ordered.length||match[1]!==ordered[childIndex])return false;
      }
      if(Number(match[2])!==chapterIndex++)return false;
    }
    seen.add(ordered[childIndex]);
    return childIndex===ordered.length-1&&seen.size===ordered.length;
  }
  const memoirChildrenFingerprint=()=>JSON.stringify(target?.type==='memoir'&&Array.isArray(target.stories)?target.stories.map(story=>[story.id,String(story.revision)]):[]);
  const savedEditionCurrent=(state,ticket,owner)=>savedEditionState===state&&state.generation===savedEditionGeneration&&current(ticket,owner)&&target?.type==='memoir'&&target.id===state.bookId&&String(target.revision)===state.revision&&targetFingerprint===state.fingerprint&&memoirChildrenFingerprint()===state.childrenFingerprint;
  const editionSourceIdOK=value=>typeof value==='string'&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value);
  const editionSourceOrigins=new Set(['contribution_text','contribution_audio','asset_note','caption','book_introduction','story_chapter']);
  const editionSourceStates=new Set(['current','source_changed','source_invalidated']);
  const savedEditionSourceRevision=state=>state.items.find(item=>item.id===state.selectedId)?.book_revision;
  function editionSourceKindOK(origin,kind){return origin==='caption'?['family','ai'].includes(kind):({contribution_text:'family',contribution_audio:'transcript',asset_note:'family',book_introduction:'editorial',story_chapter:'editorial'})[origin]===kind;}
  function editionSourceIdentityOK(origin,sourceId,assetId,storyId,bookId=target?.id){
    const contribution=/^contribution-([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/.exec(sourceId||'');
    const caption=/^caption-([1-9][0-9]{0,18})$/.exec(sourceId||'');const note=/^family-([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/.exec(sourceId||'');
    const intro=`editorial-book-${bookId}`;const chapter=/^editorial-([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})-chapter-([1-6])$/.exec(sourceId||'');
    if(origin==='contribution_text'||origin==='contribution_audio')return Boolean(contribution);
    if(origin==='caption')return Boolean(caption&&idOK(caption[1]));
    if(origin==='asset_note')return Boolean(note&&uuidOK(note[1]));
    if(origin==='book_introduction')return sourceId===intro;
    if(origin==='story_chapter')return Boolean(chapter&&(storyId===null||storyId===chapter[1])&&target?.stories?.some(child=>child.id===chapter[1]));
    return false;
  }
  function editionSourcePageOK(value,state,page){
    if(!exactKeys(value,['version','book_id','edition_id','book_revision','state','page','page_size','has_more','items'])||value.version!==1||value.book_id!==state.bookId||value.edition_id!==state.selectedId||!editionRevisionOK(value.book_revision)||value.book_revision!==savedEditionSourceRevision(state)||!editionSourceStates.has(value.state)||value.state==='current'&&value.book_revision!==state.revision||value.page!==page||value.page_size!==16||typeof value.has_more!=='boolean'||!Array.isArray(value.items)||value.items.length>16)return false;
    if(value.state!=='current')return value.items.length===0&&!value.has_more;
    if(value.has_more&&(page>=6||value.items.length!==16)||value.items.length&&(page-1)*16+value.items.length>96)return false;
    const ids=new Set();for(const item of value.items){if(!exactKeys(item,['source_id','origin','kind','asset_id'])||!editionSourceIdOK(item.source_id)||ids.has(item.source_id)||!editionSourceOrigins.has(item.origin)||!editionSourceKindOK(item.origin,item.kind))return false;ids.add(item.source_id);if(['caption','asset_note'].includes(item.origin)?!idOK(item.asset_id):item.asset_id!==null)return false;if(!editionSourceIdentityOK(item.origin,item.source_id,item.asset_id,null,state.bookId))return false;}
    return true;
  }
  function editionSourceDetailOK(value,state,sourceId){
    if(!exactKeys(value,['version','book_id','edition_id','book_revision','source_id','state','source'])||value.version!==1||value.book_id!==state.bookId||value.edition_id!==state.selectedId||!editionRevisionOK(value.book_revision)||value.book_revision!==savedEditionSourceRevision(state)||value.state==='current'&&value.book_revision!==state.revision||value.source_id!==sourceId||!editionSourceStates.has(value.state))return false;
    if(value.state!=='current')return value.source===null;
    const source=value.source,keys=['origin','kind','asset_id','story_id','byline','original_text','original_truncated','transcript','transcript_truncated','prompt_excerpt','audio_available'];
    if(!exactKeys(source,keys)||!editionSourceOrigins.has(source.origin)||!editionSourceKindOK(source.origin,source.kind)||!editionSourceIdOK(sourceId)||
      (['caption','asset_note'].includes(source.origin)?!idOK(source.asset_id):source.asset_id!==null)||
      (['contribution_text','contribution_audio','story_chapter'].includes(source.origin)?!uuidOK(source.story_id)||!target?.stories?.some(child=>child.id===source.story_id):source.story_id!==null)||!editionSourceIdentityOK(source.origin,sourceId,source.asset_id,source.story_id,state.bookId)||
      !(source.byline===null||boundedText(source.byline,256))||source.origin==='story_chapter'&&source.byline!==null||
      !(source.original_text===null||boundedText(source.original_text,8192))||typeof source.original_truncated!=='boolean'||source.original_text===null&&source.original_truncated||
      !(source.transcript===null||boundedText(source.transcript,8192))||typeof source.transcript_truncated!=='boolean'||source.transcript===null&&source.transcript_truncated||
      !boundedText(source.prompt_excerpt,8192)||typeof source.audio_available!=='boolean')return false;
    if(source.origin==='contribution_audio')return source.original_text===null&&typeof source.transcript==='string'&&source.audio_available;
    return source.transcript===null&&!source.audio_available&&typeof source.original_text==='string';
  }
  function clearSavedEditionSourceAudio(state){
    const sources=state?.sources;if(!sources)return;
    try{sources.audioController?.abort();}catch(_){}sources.audioController=null;
    clearPlayer(sources.player);if(sources.player)individualPlayers.delete(sources.player);sources.player=null;
    if(sources.url){objectUrls.delete(sources.url);try{URL.revokeObjectURL(sources.url);}catch(_){}sources.url=null;}
    sources.audioBusy=false;sources.audioError=false;
  }
  function releaseSavedEditionSourceFocus(sources,intent=sources?.focusIntent){
    if(intent?.focusListener)document.removeEventListener('focusin',intent.focusListener,true);
    if(sources?.focusIntent===intent)sources.focusIntent=null;
  }
  function clearSavedEditionSource(state,{resetList=false,status='idle'}={}){
    const sources=state?.sources;if(!sources)return;
    releaseSavedEditionSourceFocus(sources);
    sources.epoch++;for(const key of ['listController','detailController']){try{sources[key]?.abort();}catch(_){}sources[key]=null;}
    clearSavedEditionSourceAudio(state);sources.detail=null;sources.selectedSourceId=null;sources.busy=false;
    if(resetList){sources.items=[];sources.page=1;sources.hasMore=false;sources.pagesSeen=new Map();sources.status=status;}
  }
  function markSavedEditionSourceChanged(state,focusIntent=null){clearSavedEditionSource(state,{resetList:true,status:'changed'});if(focusIntent){focusIntent.sourceEpoch=state.sources.epoch;state.sources.focusIntent=focusIntent;if(focusIntent.focusListener)document.addEventListener('focusin',focusIntent.focusListener,true);}state.detail=null;state.status='changed';}
  function savedEditionSourceFocusBlocked(){
    const active=document.activeElement;
    return Boolean(active?.isConnected&&(active.matches?.('input,textarea,select,[contenteditable="true"]')||active.closest?.('.memory-edition-form,.memory-community-form,.memory-community-book-editor,.memory-book-editorial-panel'))||chatComposition?.composing||ideaComposition?.composing||isCapturing()||chatRecordingBusy||chatCaptureStarting||chatCaptureHandle||chatCaptureReady||chatTranscribing||ideaCaptureStarting||ideaCaptureHandle||ideaTranscribing);
  }
  function focusSavedEditionSourceResult(state,ticket,owner,box){
    const sources=state.sources,intent=sources?.focusIntent;
    if(!intent?.complete)return;
    releaseSavedEditionSourceFocus(sources,intent);
    if(intent.moved||intent.protectedAtStart||intent.sourceEpoch!==sources.epoch||intent.sourceId!==sources.selectedSourceId&&state.status!=='changed'||savedEditionSourceFocusBlocked()||!savedEditionCurrent(state,ticket,owner))return;
    const destination=sources.detail?.state==='current'?box.querySelector('.memory-edition-source-detail .memory-edition-source-origin'):state.status==='changed'?box.querySelector('.memory-edition-shelf-status'):sources.status==='unavailable'?box.querySelector('.memory-edition-source-status'):null;
    if(!destination)return;
    destination.scrollIntoView?.({block:'center',behavior:'auto'});destination.focus?.({preventScroll:true});
  }
  function renderSavedEditionSourceDetail(parent,state){
    const sourceState=state.sources,detail=sourceState.detail?.source;if(!detail)return;
    const panel=el('section','','memory-edition-source-detail'),origin=el('h5',et(`shelfOrigin_${detail.origin}`),'memory-edition-source-origin');origin.tabIndex=-1;origin.style.scrollMarginTop='1rem';panel.append(origin);
    if(detail.byline)panel.append(el('p',`${t('editorialByline')}: ${detail.byline}`,'memory-community-meta'));
    if(detail.original_text!==null){const block=el('section','','memory-edition-source-material'),originalLabel=detail.origin==='caption'?(detail.kind==='ai'?et('shelfCurrentCaption'):et('shelfFamilyCaption')):detail.origin==='story_chapter'?et('shelfSavedEditorial'):et('shelfOriginal');block.append(el('h6',originalLabel));const text=el('p',detail.original_text);text.lang=target?.language||lang();block.append(text);if(detail.original_truncated)block.append(el('p',et('shelfTruncated'),'memory-edition-source-truncated'));panel.append(block);}
    if(detail.transcript!==null){const block=el('section','','memory-edition-source-material');block.append(el('h6',et('shelfTranscript')));const text=el('p',detail.transcript);text.lang=target?.language||lang();block.append(text);if(detail.transcript_truncated)block.append(el('p',et('shelfTruncated'),'memory-edition-source-truncated'));panel.append(block);}
    const excerpt=el('section','','memory-edition-source-excerpt');excerpt.append(el('h6',et('shelfPromptExcerpt')),el('p',detail.prompt_excerpt));panel.append(excerpt);
    if(detail.audio_available){const button=btn(sourceState.audioBusy?et('shelfAudioLoading'):sourceState.url?et('shelfAudioReload'):et('shelfAudioLoad'),()=>void loadSavedEditionSourceAudio(state,detail), 'memory-edition-source-audio-load');button.disabled=Boolean(sourceState.audioBusy);sourceState.audioButton=button;panel.append(button);const audioBox=el('div','','memory-edition-source-audio');sourceState.audioBox=audioBox;if(sourceState.player)audioBox.append(sourceState.player);if(sourceState.url&&!sourceState.audioBusy)audioBox.append(el('p',et('shelfAudioReady'),'memory-edition-source-audio-status'));panel.append(audioBox);}
    parent.append(panel);
  }
  function renderSavedEditionSourceInspector(parent,state,ticket,owner){
    const sources=state.sources,section=el('section','','memory-edition-source-inspector'),button=btn(et('shelfSources'),()=>void loadSavedEditionSourcesPage(state,1,ticket,owner),'memory-edition-sources-open');button.disabled=Boolean(state.busy||sources.busy);section.append(button);
    const statusText=sources.audioError?et('shelfAudioUnavailable'):sources.status==='loading'?sources.selectedSourceId?et('shelfSourceLoading'):et('shelfSourcesLoading'):sources.status==='unavailable'?sources.selectedSourceId?et('shelfSourceUnavailable'):et('shelfSourcesUnavailable'):sources.status==='changed'?et('shelfSourcesChanged'):'';
    const status=el('p',statusText,'memory-edition-source-status');status.setAttribute('role','status');status.tabIndex=-1;status.style.scrollMarginTop='1rem';section.append(status);
    if(sources.status==='ready'){
      if(sources.items.length){const list=el('ol','','memory-edition-source-list');sources.items.forEach((item,index)=>{const row=el('li','','memory-edition-source-item'),label=`${et(`shelfOrigin_${item.origin}`)} · ${et(`shelfKind_${item.kind}`)}`,inspect=btn(`${label} · ${et('shelfSourceInspect')} ${((sources.page-1)*16)+index+1}`,()=>void inspectSavedEditionSource(state,item.source_id,ticket,owner),'memory-edition-source-open');inspect.disabled=Boolean(sources.busy||state.busy);row.append(inspect);list.append(row);});section.append(list);}
      else if(sources.page===1)section.append(el('p',et('shelfSourcesEmpty')));
      const controls=el('div','','memory-edition-source-pages');if(sources.page>1){const previous=btn(et('shelfSourcePrevious'),()=>void loadSavedEditionSourcesPage(state,sources.page-1,ticket,owner),'memory-community-button');previous.disabled=Boolean(sources.busy||state.busy);controls.append(previous);}if(sources.hasMore){const next=btn(et('shelfSourceMore'),()=>void loadSavedEditionSourcesPage(state,sources.page+1,ticket,owner),'memory-community-button');next.disabled=Boolean(sources.busy||state.busy);controls.append(next);}if(controls.childElementCount)section.append(controls);
    }
    if(sources.status==='unavailable')section.append(btn(et('shelfSources'),()=>void loadSavedEditionSourcesPage(state,1,ticket,owner),'memory-community-button'));
    if(sources.detail?.state==='current')renderSavedEditionSourceDetail(section,state);
    parent.append(section);
  }
  function savedEditionSourceScope(state,ticket,owner,sourceEpoch){return savedEditionCurrent(state,ticket,owner)&&state.sources?.epoch===sourceEpoch&&state.detail?.state==='current'&&state.selectedId===state.detail.id;}
  async function loadSavedEditionSourcesPage(state,page,ticket,owner){
    if(!savedEditionCurrent(state,ticket,owner)||state.detail?.state!=='current'||state.busy||state.sources.busy)return;
    clearSavedEditionSource(state,{resetList:page===1,status:'loading'});const sources=state.sources,epochAtRequest=sources.epoch;sources.busy=true;sources.page=page;sources.status='loading';const controller=new AbortController();sources.listController=controller;renderSavedEditionShelf(state,ticket,owner);
    try{const value=await bookApi(`${API}/books/${state.bookId}/editions/${state.selectedId}/sources?page=${page}`,{signal:controller.signal});if(!savedEditionSourceScope(state,ticket,owner,epochAtRequest))return;
      if(!editionSourcePageOK(value,state,page))throw new Error('Invalid edition source page');
      if(value.state!=='current'){markSavedEditionSourceChanged(state);renderSavedEditionShelf(state,ticket,owner);return;}
      const prior=new Set([...sources.pagesSeen].filter(([priorPage])=>priorPage!==page).flatMap(([,ids])=>ids));if(value.items.some(item=>prior.has(item.source_id)))throw new Error('Duplicate edition source');
      const pageIds=value.items.map(item=>item.source_id),all=new Set([...prior,...pageIds]);if(all.size>96)throw new Error('Edition source closure exceeded bound');sources.pagesSeen.set(page,pageIds);sources.items=value.items;sources.page=page;sources.hasMore=value.has_more;sources.status='ready';
    }catch(error){if(savedEditionSourceScope(state,ticket,owner,epochAtRequest)){sources.items=[];sources.hasMore=false;sources.status='unavailable';if(error?.status===409){markSavedEditionSourceChanged(state);renderSavedEditionShelf(state,ticket,owner);}}}
    finally{if(savedEditionCurrent(state,ticket,owner)&&sources.epoch===epochAtRequest){sources.busy=false;sources.listController=null;renderSavedEditionShelf(state,ticket,owner);}}
  }
  async function inspectSavedEditionSource(state,sourceId,ticket,owner){
    if(!savedEditionCurrent(state,ticket,owner)||state.detail?.state!=='current'||state.busy||state.sources.busy||!editionSourceIdOK(sourceId))return;
    const protectedAtStart=savedEditionSourceFocusBlocked();clearSavedEditionSource(state);const sources=state.sources,epochAtRequest=sources.epoch,focusIntent={sourceId,sourceEpoch:epochAtRequest,protectedAtStart,moved:false,complete:false,focusListener:null};focusIntent.focusListener=()=>{focusIntent.moved=true;};sources.focusIntent=focusIntent;document.addEventListener('focusin',focusIntent.focusListener,true);sources.selectedSourceId=sourceId;sources.status='loading';sources.busy=true;const controller=new AbortController();sources.detailController=controller;renderSavedEditionShelf(state,ticket,owner);
    try{const value=await bookApi(`${API}/books/${state.bookId}/editions/${state.selectedId}/sources/${encodeURIComponent(sourceId)}`,{signal:controller.signal});if(!savedEditionSourceScope(state,ticket,owner,epochAtRequest))return;
      if(!editionSourceDetailOK(value,state,sourceId))throw new Error('Invalid edition source detail');
      if(value.state!=='current'){markSavedEditionSourceChanged(state,focusIntent);renderSavedEditionShelf(state,ticket,owner);return;}
      sources.detail=value;sources.status='ready';
    }catch(error){if(savedEditionSourceScope(state,ticket,owner,epochAtRequest)){sources.detail=null;sources.status='unavailable';if(error?.status===409){markSavedEditionSourceChanged(state,focusIntent);renderSavedEditionShelf(state,ticket,owner);}}}
    finally{if(savedEditionCurrent(state,ticket,owner)&&sources.focusIntent===focusIntent&&sources.epoch===focusIntent.sourceEpoch){sources.busy=false;sources.detailController=null;focusIntent.complete=true;renderSavedEditionShelf(state,ticket,owner);}}
  }
  async function loadSavedEditionSourceAudio(state,detail){
    const sources=state?.sources,ticket=epoch,owner=accountKey(scopeNow()),sourceEpoch=sources?.epoch;
    if(!sources||!savedEditionSourceScope(state,ticket,owner,sourceEpoch)||!detail.audio_available||sources.audioBusy||isCapturing())return;
    clearSavedEditionSourceAudio(state);
    const controller=new AbortController();sources.audioController=controller;sources.audioBusy=true;renderSavedEditionShelf(state,ticket,owner);
    try{const blob=await bookApi(`${API}/books/${state.bookId}/editions/${state.selectedId}/sources/${encodeURIComponent(sources.selectedSourceId)}/audio`,{responseType:'blob',signal:controller.signal});
      if(!savedEditionSourceScope(state,ticket,owner,sourceEpoch)||controller.signal.aborted||document.hidden)return;
      if(!(blob instanceof Blob)||blob.size<46||blob.size>MAX_AUDIO||blob.type!=='audio/wav'||!await validWav(blob))throw new Error('Invalid edition source audio');
      if(!savedEditionSourceScope(state,ticket,owner,sourceEpoch)||controller.signal.aborted||document.hidden)return;
      const url=URL.createObjectURL(blob);if(!savedEditionSourceScope(state,ticket,owner,sourceEpoch)||controller.signal.aborted||document.hidden){URL.revokeObjectURL(url);return;}
      sources.url=url;objectUrls.add(url);const player=el('audio');player.controls=true;player.autoplay=false;player.preload='none';player.src=url;sources.player=player;individualPlayers.set(player,sources.audioButton||null);
      player.addEventListener('play',()=>{if(!savedEditionSourceScope(state,ticket,owner,sourceEpoch)||document.hidden||isCapturing()){try{player.pause();}catch(_){}return;}notifyAudioStart();});
    }catch(error){if(savedEditionCurrent(state,ticket,owner)&&sources.epoch===sourceEpoch){sources.status=error?.status===409?'changed':'unavailable';if(sources.status==='changed'){markSavedEditionSourceChanged(state);renderSavedEditionShelf(state,ticket,owner);}else{sources.detail=null;sources.audioError=true;}}}
    finally{if(savedEditionCurrent(state,ticket,owner)&&sources.epoch===sourceEpoch){sources.audioBusy=false;sources.audioController=null;renderSavedEditionShelf(state,ticket,owner);}}
  }
  function renderSavedEditionShelf(state,ticket,owner){
    const host=mount?.querySelector('.memory-edition-shelf-host');if(!host||!savedEditionCurrent(state,ticket,owner))return;
    clearSavedEditionSpeech(state);
    const box=el('section','','memory-edition-shelf'),heading=el('h3',et('shelf'),'memory-edition-shelf-heading');box.append(heading,el('p',et('shelfHelp'),'memory-community-help'));
    const statusText=state.status==='loading'?et('shelfLoading'):state.status==='unavailable'?(state.selectedId?et('shelfDetailUnavailable'):et('shelfUnavailable')):state.status==='changed'?et('shelfChanged'):'';
    const status=el('p',statusText,'memory-edition-shelf-status');status.setAttribute('role','status');status.tabIndex=-1;status.style.scrollMarginTop='1rem';box.append(status);
    if(state.status==='unavailable'&&!state.selectedId){const retry=btn(et('shelfRetry'),()=>void loadSavedEditions(ticket,owner),'memory-edition-shelf-retry');retry.disabled=Boolean(state.busy);box.append(retry);}
    if(state.status==='unavailable'&&state.selectedId){const retry=btn(et('shelfReadAgain'),()=>{const item=state.items.find(value=>value.id===state.selectedId);if(item)void readSavedEditionForShelf(state,item,ticket,owner);},'memory-edition-shelf-detail-retry');retry.disabled=Boolean(state.busy);box.append(retry);}
    if(state.status==='ready'||state.status==='changed'||state.status==='unavailable'&&state.selectedId){const refresh=btn(et('shelfRefresh'),()=>void loadSavedEditionPage(state,1,ticket,owner),'memory-edition-shelf-refresh');refresh.disabled=Boolean(state.busy);box.append(refresh);}
    if(state.detail){const detail=state.detail;if(detail.state==='current'&&detail.manuscript){box.append(el('h4',detail.manuscript.title));renderProposalChapters(box,detail.manuscript.chapters,()=>savedEditionCurrent(state,ticket,owner)&&host.contains(box),{savedEdition:true,speechDisposers:state.speechDisposers,onSourceReference:sourceId=>void inspectSavedEditionSource(state,sourceId,ticket,owner)});renderQuestions(box,detail.manuscript.questions);renderSavedEditionSourceInspector(box,state,ticket,owner);} }
    if(state.items.length){const list=el('ol','','memory-edition-shelf-list');state.items.forEach((item,index)=>{const row=el('li','','memory-edition-shelf-item'),meta=el('p',`${et('shelfVersion')((state.page-1)*8+index+1)} · ${et('shelfDate')(item.created_at)} · ${et('shelfState_'+item.state)||et('shelfState_source_changed')}`,'memory-community-meta'),open=btn(et('shelfRead'),()=>void readSavedEditionForShelf(state,item,ticket,owner),'memory-edition-shelf-read');open.disabled=Boolean(state.busy);row.append(meta,open);list.append(row);});box.append(list);}
    else if(state.status==='ready')box.append(el('p',et('shelfEmpty')));
    if(state.status==='ready'||state.status==='changed'){const controls=el('div','','memory-edition-shelf-pages');if(state.page>1){const previous=btn(et('shelfPrevious'),()=>void loadSavedEditionPage(state,state.page-1,ticket,owner),'memory-community-button');previous.disabled=Boolean(state.busy);controls.append(previous);}if(state.hasMore){const next=btn(et('shelfMore'),()=>void loadSavedEditionPage(state,state.page+1,ticket,owner),'memory-community-button');next.disabled=Boolean(state.busy);controls.append(next);}if(controls.childElementCount)box.append(controls);}
    host.replaceChildren(box);focusSavedEditionSourceResult(state,ticket,owner,box);
  }
  async function loadSavedEditions(ticket,owner){
    if(!current(ticket,owner)||target?.type!=='memoir')return;
    const state={generation:++savedEditionGeneration,bookId:target.id,revision:String(target.revision),fingerprint:targetFingerprint,childrenFingerprint:memoirChildrenFingerprint(),page:1,items:[],hasMore:false,status:'loading',detail:null,speechDisposers:new Set(),sources:{epoch:0,status:'idle',page:1,items:[],hasMore:false,pagesSeen:new Map(),detail:null,selectedSourceId:null,busy:false,audioBusy:false,audioError:false,listController:null,detailController:null,audioController:null,url:null,player:null}};savedEditionState=state;renderSavedEditionShelf(state,ticket,owner);
    try{const caps=await api(`${API}/books/${state.bookId}/edition-capabilities`);if(!savedEditionCurrent(state,ticket,owner))return;
      if(!exactKeys(caps,['version','enabled','can_save'])||caps.version!==1||typeof caps.enabled!=='boolean'||typeof caps.can_save!=='boolean'||!caps.enabled&&caps.can_save)throw new Error('Invalid edition capability');
      if(!caps.enabled){state.status='unavailable';return;}
      await loadSavedEditionPage(state,1,ticket,owner);
    }catch(error){if(savedEditionCurrent(state,ticket,owner)){state.status='unavailable';notifyError(error);}}
    finally{if(savedEditionCurrent(state,ticket,owner))renderSavedEditionShelf(state,ticket,owner);}
  }
  async function loadSavedEditionPage(state,page,ticket,owner){
    if(!savedEditionCurrent(state,ticket,owner)||state.busy)return;clearSavedEditionSource(state,{resetList:true,status:'idle'});if(state.detail)clearSavedEditionSpeech(state);state.busy=true;state.status='loading';state.detail=null;state.selectedId=null;if(page===1){state.items=[];state.hasMore=false;}renderSavedEditionShelf(state,ticket,owner);
    try{const value=await api(`${API}/books/${state.bookId}/editions?page=${page}`);if(!savedEditionCurrent(state,ticket,owner))return;
      if(!exactKeys(value,['version','book_id','page','page_size','has_more','items'])||value.version!==1||value.book_id!==state.bookId||value.page!==page||value.page_size!==8||typeof value.has_more!=='boolean'||!Array.isArray(value.items)||value.items.length>8||value.has_more&&value.items.length!==8||value.items.some(item=>!exactKeys(item,['version','id','book_id','book_revision','created_at','state','mutation_id','manuscript'])||item.version!==1||item.book_id!==state.bookId||!uuidOK(item.id)||!editionRevisionOK(item.book_revision)||!Number.isSafeInteger(item.created_at)||item.created_at<0||item.created_at>253402300799||!uuidOK(item.mutation_id)||!['current','source_invalidated','source_changed'].includes(item.state)||item.manuscript!==null)||new Set(value.items.map(item=>item.id)).size!==value.items.length||!value.items.every((item,index)=>index===0||value.items[index-1].created_at>item.created_at||value.items[index-1].created_at===item.created_at&&value.items[index-1].id>item.id))throw new Error('Invalid saved editions page');
      state.items=value.items;state.page=page;state.hasMore=value.has_more;state.status='ready';
    }catch(error){if(savedEditionCurrent(state,ticket,owner)){state.items=[];state.hasMore=false;state.detail=null;state.selectedId=null;state.status='unavailable';notifyError(error);}}
    finally{if(savedEditionCurrent(state,ticket,owner)){state.busy=false;renderSavedEditionShelf(state,ticket,owner);}}
  }
  async function readSavedEditionForShelf(state,item,ticket,owner){
    if(!savedEditionCurrent(state,ticket,owner)||state.busy)return;clearSavedEditionSource(state,{resetList:true,status:'idle'});clearSavedEditionSpeech(state);state.busy=true;state.status='loading';state.detail=null;state.selectedId=item.id;renderSavedEditionShelf(state,ticket,owner);
    try{const value=await api(`${API}/books/${state.bookId}/editions/${item.id}`);if(!savedEditionCurrent(state,ticket,owner))return;
      if(!exactKeys(value,['version','id','book_id','book_revision','created_at','state','mutation_id','manuscript'])||value.version!==1||value.id!==item.id||value.book_id!==state.bookId||!editionRevisionOK(value.book_revision)||value.book_revision!==item.book_revision||!Number.isSafeInteger(value.created_at)||value.created_at<0||value.created_at>253402300799||value.created_at!==item.created_at||value.mutation_id!==item.mutation_id||!['current','source_invalidated','source_changed'].includes(value.state))throw new Error('Invalid saved edition detail');
      if(value.state==='current'){
        if(value.book_revision!==state.revision||!editionManuscriptOK(value.manuscript)||!savedEditionChaptersOK(value.manuscript))throw new Error('Invalid current saved edition');
        state.detail=value;state.status='ready';
      }else{if(value.manuscript!==null)throw new Error('Stale saved edition content');state.detail=value;state.status='changed';}
    }catch(error){if(savedEditionCurrent(state,ticket,owner)){state.detail=null;state.status='unavailable';notifyError(error);}}
    finally{if(savedEditionCurrent(state,ticket,owner)){state.busy=false;renderSavedEditionShelf(state,ticket,owner);}}
  }
  function editionProposalOK(value,state){
    if(!exactKeys(value,['version','book_id','revision','job_id','job_result_sha256','source_fingerprint','context_profile','children','manuscript','needs_review'])||value.version!==1||value.needs_review!==true||value.book_id!==state.bookId||value.revision!==state.revision||value.job_id!==state.jobId||!editionRevisionOK(value.revision)||!['stories','memoir_editorial_v1'].includes(value.context_profile)||!(/^[0-9a-f]{64}$/.test(value.job_result_sha256||'')&&/^[0-9a-f]{64}$/.test(value.source_fingerprint||''))||!Array.isArray(value.children)||value.children.length<1||value.children.length>24||!editionManuscriptOK(value.manuscript))return false;
    const children=target?.stories||[];
    if(value.children.length!==children.length)return false;
    if(!value.children.every((child,index)=>exactKeys(child,['id','revision'])&&uuidOK(child.id)&&editionRevisionOK(child.revision)&&child.id===children[index].id&&child.revision===String(children[index].revision))||new Set(value.children.map(child=>child.id)).size!==value.children.length)return false;
    let childIndex=0,chapterIndex=1;
    for(const chapter of value.manuscript.chapters){
      if(!chapter.id.startsWith(value.children[childIndex].id+'-chapter-')){if(chapterIndex===1)return false;childIndex++;chapterIndex=1;if(childIndex>=value.children.length)return false;}
      if(chapter.id!==`${value.children[childIndex].id}-chapter-${chapterIndex++}`)return false;
    }
    return childIndex===value.children.length-1;
  }
  const editionCurrent=(state,ticket,owner)=>editionReview===state&&state.generation===editionGeneration&&current(ticket,owner)&&target?.type==='memoir'&&target.id===state.bookId&&String(target.revision)===state.revision&&activeJob?.id===state.jobId;
  async function openEditionReview(job,ticket,owner){
    if(!current(ticket,owner)||target?.type!=='memoir'||!canEdit()||job!==activeJob||job.state!=='ready')return;
    if(editionReview?.busy||editionReview?.pending&&editionReview.status!=='conflict')return;
    if((editionReview?.dirty||editionReview?.pending)&&!window.confirm(et('discard')))return;
    const state={generation:++editionGeneration,bookId:target.id,revision:String(target.revision),jobId:job.id,busy:true,status:'loading',proposal:null,manuscript:null,reviewed:false,dirty:false,pending:null,receipt:null,composing:false,chapterOpen:[]};editionReview=state;await renderPanel();
    try{
      const caps=await api(`${API}/books/${state.bookId}/edition-capabilities`);
      if(!editionCurrent(state,ticket,owner))return;
      if(!exactKeys(caps,['version','enabled','can_save'])||caps.version!==1||typeof caps.enabled!=='boolean'||typeof caps.can_save!=='boolean'||!caps.enabled&&caps.can_save)throw new Error('Invalid edition capability');
      if(!caps.enabled||!caps.can_save){state.status='unavailable';return;}
      const proposal=await api(`${API}/books/${state.bookId}/editions/proposals/${state.jobId}`);
      if(!editionCurrent(state,ticket,owner))return;
      if(!editionProposalOK(proposal,state))throw new Error('Invalid reviewed memoir proposal');
      state.proposal=proposal;state.manuscript=JSON.parse(JSON.stringify(proposal.manuscript));state.status='review';
    }catch(error){if(editionCurrent(state,ticket,owner)){state.status=error?.status===409?'conflict':'unavailable';notifyError(error);}}
    finally{if(editionCurrent(state,ticket,owner)){state.busy=false;await renderPanel();focusEditionReview(state,ticket,owner);}}
  }
  function focusEditionReview(state,ticket,owner){if(!editionCurrent(state,ticket,owner)||activeTab!=='ideas')return;const heading=panelNode?.querySelector('.memory-edition-heading');heading?.focus({preventScroll:true});heading?.scrollIntoView({block:'start',behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'auto':'smooth'});}
  function editionReceiptOK(value,state,mutation=state.pending?.mutation_id,states=['current','source_invalidated']){return exactKeys(value,['version','id','book_id','book_revision','created_at','state','mutation_id'])&&value.version===1&&uuidOK(value.id)&&value.book_id===state.bookId&&value.book_revision===state.revision&&Number.isSafeInteger(value.created_at)&&value.created_at>=0&&states.includes(value.state)&&value.mutation_id===mutation;}
  async function saveEdition(state,ticket,owner){
    if(!editionCurrent(state,ticket,owner)||state.busy||state.composing||!canEdit()||!state.proposal||state.receipt)return;
    if(!state.pending){
      if(!state.reviewed||!editionManuscriptOK(state.manuscript,state.proposal.manuscript)){state.status='invalid';await renderPanel();return;}
      const mutation=uuid();if(!uuidOK(mutation)){state.status='unavailable';await renderPanel();return;}
      const proposal=state.proposal;
      state.pending=JSON.parse(JSON.stringify({version:1,revision:state.revision,mutation_id:mutation,job_id:state.jobId,job_result_sha256:proposal.job_result_sha256,source_fingerprint:proposal.source_fingerprint,children:proposal.children,manuscript:state.manuscript,reviewed:true}));
    }
    state.busy=true;state.status='loading';await renderPanel();
    try{
      const receipt=await api(`${API}/books/${state.bookId}/editions`,{method:'POST',body:state.pending});
      if(!editionCurrent(state,ticket,owner))return;
      if(!editionReceiptOK(receipt,state))throw new Error('Invalid edition save receipt');
      state.receipt=receipt;state.pending=null;state.dirty=false;state.reviewed=false;state.manuscript=null;state.status='saved';
    }catch(error){if(editionCurrent(state,ticket,owner)){if(error?.status===400||error?.status===413){state.pending=null;state.reviewed=false;state.status='invalid';}else state.status=error?.status===409?'conflict':'error';notifyError(error);}}
    finally{if(editionCurrent(state,ticket,owner)){state.busy=false;await renderPanel();}}
  }
  async function readSavedEdition(state,ticket,owner){
    if(!editionCurrent(state,ticket,owner)||state.busy||!state.receipt)return;
    state.busy=true;state.manuscript=null;state.status='loading';await renderPanel();
    try{
      const value=await api(`${API}/books/${state.bookId}/editions/${state.receipt.id}`);
      if(!editionCurrent(state,ticket,owner))return;
      if(!exactKeys(value,['version','id','book_id','book_revision','created_at','state','mutation_id','manuscript']))throw new Error('Invalid edition read');
      const receipt={...value};delete receipt.manuscript;
      if(value.id!==state.receipt.id||!editionReceiptOK(receipt,state,state.receipt.mutation_id,['current','source_invalidated','source_changed']))throw new Error('Invalid edition read');
      if(value.state!=='current'){if(value.manuscript!==null)throw new Error('Stale edition content');state.status='changed';}
      else {if(!editionManuscriptOK(value.manuscript,state.proposal.manuscript))throw new Error('Invalid edition manuscript');state.manuscript=value.manuscript;state.status='saved';}
    }catch(error){if(editionCurrent(state,ticket,owner)){state.status='changed';notifyError(error);}}
    finally{if(editionCurrent(state,ticket,owner)){state.busy=false;await renderPanel();}}
  }
  function renderEditionReview(root,state,ticket,owner){
    const box=el('section','','memory-edition-review'),heading=el('h3',et('heading'),'memory-edition-heading');heading.tabIndex=-1;box.append(heading,el('p',et('help')));if(state.proposal)box.append(el('p',editionLabels[lang()].scope(state.proposal.manuscript.chapters.length,new Set(state.proposal.manuscript.chapters.flatMap(chapter=>chapter.source_ids)).size),'memory-community-meta'));
    const status=el('p',state.status==='review'?'':et(state.status),'memory-edition-status');status.setAttribute('role','status');box.append(status);root.append(box);
    if(state.busy)return;
    if(state.receipt){box.append(btn(et('read'),()=>void readSavedEdition(state,ticket,owner),'memory-edition-read'));if(state.manuscript){box.append(el('h4',state.manuscript.title));renderProposalChapters(box,state.manuscript.chapters,()=>editionCurrent(state,ticket,owner)&&box.parentNode===root);renderQuestions(box,state.manuscript.questions);}return;}
    if(!state.proposal||!state.manuscript){box.append(btn(et('checkAgain'),()=>void openEditionReview(activeJob,ticket,owner),'memory-edition-check-again'));return;}
    const form=el('form','','memory-edition-form'),frozen=Boolean(state.pending);box.append(form);
    const save=el('button',et(frozen?'retry':'save'));save.type='submit';save.className='memory-edition-save memory-community-primary';save.disabled=frozen?state.status==='conflict':!state.reviewed;
    const currentEditor=node=>editionCurrent(state,ticket,owner)&&activeTab==='ideas'&&box.parentNode===root&&root.parentNode===panelNode&&node.isConnected!==false&&!state.pending&&!state.busy;
    const bind=(input,apply)=>{input.addEventListener('compositionstart',()=>{if(currentEditor(input)){state.composing=true;save.disabled=true;}});input.addEventListener('compositionend',()=>{if(currentEditor(input)){apply(input.value);state.composing=false;state.reviewed=false;state.dirty=true;review.checked=false;save.disabled=true;if(state.renderDeferred){state.renderDeferred=false;void renderPanel();}}});input.addEventListener('input',()=>{if(currentEditor(input)){apply(input.value);state.dirty=true;state.reviewed=false;review.checked=false;save.disabled=true;}});};
    const titleLabel=el('label',et('title')),title=el('input');title.name='edition_title';title.value=state.manuscript.title;title.disabled=frozen;titleLabel.append(title);form.append(titleLabel);bind(title,value=>state.manuscript.title=value);
    state.manuscript.chapters.forEach((chapter,index)=>{const details=el('details','','memory-edition-chapter'),summary=el('summary',proposalChapterTitle(chapter.id,index)),label=el('label',`${et('chapter')} ${index+1}`),input=el('textarea');input.name='edition_chapter_'+index;input.rows=5;input.value=chapter.narration;input.disabled=frozen;label.append(input);details.open=state.chapterOpen.includes(chapter.id);details.addEventListener('toggle',()=>{if(editionCurrent(state,ticket,owner)&&details.isConnected){state.chapterOpen=state.chapterOpen.filter(id=>id!==chapter.id);if(details.open)state.chapterOpen.push(chapter.id);}});details.append(summary,label,el('p',`${chapter.source_ids.length} ${lang()==='zh'?'条引用':'references'}`,'memory-community-meta'));form.append(details);bind(input,value=>chapter.narration=value);});
    renderQuestions(form,state.manuscript.questions);
    const reviewLabel=el('label',et('review')),review=el('input');review.type='checkbox';review.name='edition_reviewed';review.checked=state.reviewed;review.disabled=frozen;review.addEventListener('change',()=>{if(currentEditor(review)&&!state.composing){state.reviewed=review.checked;save.disabled=!state.reviewed;}else review.checked=state.reviewed;});reviewLabel.prepend(review);form.append(reviewLabel,save);
    form.addEventListener('submit',event=>{event.preventDefault();if(editionCurrent(state,ticket,owner)&&root.parentNode===panelNode&&box.parentNode===root)void saveEdition(state,ticket,owner);});
    if(state.status==='conflict')box.append(btn(et('reload'),()=>void openEditionReview(activeJob,ticket,owner),'memory-edition-reload'));
  }
  function validNarrative(result){
    if(!result||result.version!==1||result.needs_review!==true||!safeText(result.title,512)||!Array.isArray(result.chapters)||!Array.isArray(result.questions)||result.questions.length>6)return false;
    if(result.questions.some(question=>!boundedText(question,512)))return false;
    if(target.type!=='story'||result.chapters.length!==target.chapters.length)return false;
    return result.chapters.every((chapter,index)=>chapter&&chapter.id===target.chapters[index].id&&boundedText(chapter.narration,6000)&&Array.isArray(chapter.source_ids)&&chapter.source_ids.length<=96&&new Set(chapter.source_ids).size===chapter.source_ids.length&&chapter.source_ids.every(id=>typeof id==='string'&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(id)));
  }
  function emitProposal(result,ticket,owner){
    if(!current(ticket,owner)||!canEdit()||!validNarrative(result))return;
    const chapters=result.chapters.map((chapter,index)=>({id:chapter.id,title:target.chapters[index].title,narration:chapter.narration,asset_ids:[...target.chapters[index].asset_ids],evidence_ids:chapter.source_ids.filter(id=>target.chapters[index].evidence_ids?.includes(id))}));
    const source_refs=result.chapters.map(chapter=>({chapter_id:chapter.id,source_ids:[...chapter.source_ids]}));
    onProposal({job_id:activeJob?.id||null,story_id:target.id,revision:String(target.revision),selection_revision:target.selection_revision,title:result.title,chapters,source_refs});
  }
  function renderNarrativeProposal(root,result,ticket,owner){
    if(!validNarrative(result))return;
    const box=el('section','','memory-community-proposal');box.append(el('h3',t('proposal')),el('h4',result.title));
    const renderId=panelRenderEpoch,renderTarget=target,renderFingerprint=targetFingerprint;
    renderProposalChapters(box,result.chapters,node=>current(ticket,owner)&&activeTab==='ideas'&&target===renderTarget&&targetFingerprint===renderFingerprint&&panelRenderEpoch===renderId&&root.parentNode===panelNode&&node.isConnected!==false);
    renderQuestions(box,result.questions);if(target.type==='story'&&canEdit())box.append(btn(t('adopt'),()=>emitProposal(result,ticket,owner),'memory-community-primary'));root.append(box);
  }

  async function books(container){
    if(!container)return;clearEditorialInspection();listenVisibility();roots.add(container);bookContainers.add(container);container.hidden=true;const s=scopeNow();if(!s?.account||!s?.library||s.locked){container.replaceChildren();return;}
    if(currentScope&&JSON.stringify([currentScope.account,currentScope.library])!==accountKey(s)){bookEpoch++;editorialGeneration++;bookEditSequence++;editorialModel=null;editorialPending=null;editorialBusyOwner='';for(const controller of bookControllers)controller.abort();bookControllers.clear();for(const shelf of bookContainers){shelf.hidden=true;shelf.replaceChildren();}booksList=[];storyOptions=[];storyPage=0;storyOptionsHasMore=false;bookStorySelection=new Set();bookTitleDraft='';bookIntroDraft='';bookEditorOpen=false;bookPage=1;booksHasMore=false;pendingBook=null;bookSubmittingOwner='';selectedBook=null;}
    currentScope={account:s.account,library:s.library,membership_revision:membershipRevision(s)};const ticket=bookEpoch,owner=accountKey(s),lastPage=Math.max(1,bookPage);container.replaceChildren(el('section','','memory-community-books'));const root=container.firstChild;
    try{const capability=await ensureBookCapabilities();if(!bookCurrent(ticket,owner))return;if(!capability.enabled){container.replaceChildren();return;}
      container.hidden=false;
      root.append(el('h2',t('books'),'memory-community-books-heading'),el('p',t('shelfSubtitle'),'memory-community-help'));
      const result=await bookApi(`${API}/books?page=1`);if(!bookCurrent(ticket,owner))return;
      if(result.version!==1||result.library_id!==s.library||result.page!==1||result.page_size!==8||typeof result.has_more!=='boolean'||typeof result.can_create!=='boolean'||!Array.isArray(result.items)||result.items.length>8)throw new Error('Invalid family collections');
      booksList=result.items;bookPage=1;booksHasMore=Boolean(result.has_more);
      for(let page=2;page<=lastPage&&booksHasMore;page++){const next=await bookApi(`${API}/books?page=${page}`);if(!bookCurrent(ticket,owner))return;if(next.version!==1||next.page!==page||next.page_size!==8||typeof next.has_more!=='boolean'||!Array.isArray(next.items)||next.items.length>8)throw new Error('Invalid family collections');booksList.push(...next.items);bookPage=page;booksHasMore=next.has_more;}
      const listRegion=el('section','','memory-book-list-region');root.append(listRegion);renderBookList(listRegion,owner,ticket,root);
      if(booksHasMore)listRegion.append(btn(t('moreBooks'),()=>void loadMoreBooks(listRegion,owner,ticket,root),'memory-book-more'));
      if(result.can_create){await loadStoryOptions(ticket,owner);if(!bookCurrent(ticket,owner))return;
        const toggle=btn('',()=>{bookEditorOpen=!bookEditorOpen;if(!bookEditorOpen)clearEditorialInspection();toggle.textContent=t(bookEditorOpen?'collapseBookEditor':pendingBook?'continueBook':selectedBook?'continueEditBook':'composeBook');toggle.setAttribute('aria-expanded',String(bookEditorOpen));const editor=root.querySelector('.memory-community-book-editor');if(editor)editor.hidden=!bookEditorOpen;if(bookEditorOpen)renderBookForm(root,selectedBook,ticket,owner);},'memory-book-compose-cta');toggle.setAttribute('aria-controls','memory-community-book-editor');toggle.textContent=t(bookEditorOpen?'collapseBookEditor':pendingBook?'continueBook':selectedBook?'continueEditBook':'composeBook');toggle.setAttribute('aria-expanded',String(bookEditorOpen));root.append(toggle);
        renderBookForm(root,selectedBook,ticket,owner);
      }
    }catch(error){if(bookCurrent(ticket,owner)){container.hidden=true;root.append(el('p',t('unavailable')));notifyError(error);}}
  }
  async function loadMoreBooks(root,owner,ticket,host=root){
    try{const page=bookPage+1,result=await bookApi(`${API}/books?page=${page}`);if(!bookCurrent(ticket,owner))return;
      if(result.version!==1||result.page!==page||result.page_size!==8||typeof result.has_more!=='boolean'||!Array.isArray(result.items)||result.items.length>8)throw new Error('Invalid family collections');
      bookPage=page;booksHasMore=Boolean(result.has_more);booksList.push(...result.items);root.querySelector('.memory-book-more')?.remove();renderBookList(root,owner,ticket,host);
      if(booksHasMore)root.append(btn(t('moreBooks'),()=>void loadMoreBooks(root,owner,ticket,host),'memory-book-more'));
    }catch(error){reportBook(error,owner,ticket);}
  }
  function renderBookList(root,owner,ticket,host=root){
    root.querySelector('.memory-book-list')?.remove();const list=el('div','','memory-book-list');if(!booksList.length)list.append(el('p',t('noBooks')));
    for(const book of booksList){if(!uuidOK(book.id)||!Array.isArray(book.stories))continue;
      const card=el('article','','memory-book-card');
      const coverStory=book.stories.find(story=>idOK(story.cover_asset_id));
      const cover=el('div','','memory-book-cover');
      if(coverStory){const image=el('img');image.src=mediaURL(coverStory.cover_asset_id,'thumbnail');image.alt='';image.loading='lazy';image.addEventListener('error',()=>{image.hidden=true;cover.dataset.imageFailed='true';});cover.append(image);}
      else cover.dataset.imageFailed='true';
      const coverLabel=el('span',book.title||t('untitled'),'memory-book-cover-title');cover.append(coverLabel);
      card.append(cover);
      const content=el('div','','memory-book-card-content');
      content.append(el('h3',book.title||t('untitled')));
      const mediaCount=book.stories.reduce((sum,story)=>sum+(Number.isSafeInteger(story.item_count)&&story.item_count>0?story.item_count:0),0);
      const counts=el('p',`${t('bookStoryCount')(book.stories.length)} · ${t('bookMediaCount')(mediaCount)}`,'memory-book-counts');
      content.append(counts);
      const opening=String(book.introduction||'').trim().slice(0,240);
      if(opening)content.append(el('p',opening,'memory-book-opening'));
      const actions=el('div','','memory-book-actions');
      actions.append(btn(t('openBook'),()=>void openBookTarget(book.id,owner,ticket),'memory-community-primary memory-book-read'));
      if(book.can_edit)actions.append(btn(t('updateBook'),()=>void loadBookForEdit(book.id,host,owner,ticket),'memory-book-edit'));
      content.append(actions);
      const stories=el('div','','memory-book-stories');
      for(const story of book.stories)stories.append(btn(`${t('chooseStory')}: ${story.title}`,()=>onOpenStory(story.id),'memory-book-story'));
      content.append(stories);card.append(content);list.append(card);
    }
    root.append(list);
  }
  async function loadStoryOptions(ticket,owner){
    const lastPage=Math.max(1,storyPage);storyOptions=[];storyPage=0;storyOptionsHasMore=false;
    for(let page=1;page<=lastPage;page++){await loadStoryOptionsPage(ticket,owner,page,page>1);if(!bookCurrent(ticket,owner)||!storyOptionsHasMore)break;}
  }
  async function loadStoryOptionsPage(ticket,owner,page,append){
    const result=await bookApi(`/memory-stories?page=${page}`);if(!bookCurrent(ticket,owner))return;
    if(result.library_id!==scopeNow().library||result.page!==page||result.page_size!==8||!Array.isArray(result.items)||result.items.length>8||typeof result.has_more!=='boolean')throw new Error('Invalid saved stories');
    if(!append)storyOptions=[];storyOptions.push(...result.items);storyPage=page;storyOptionsHasMore=result.has_more;
  }
  function renderBookSelectionOrder(orderBox,selected,book,renderOrder){
    orderBox.replaceChildren(el('h4',t('selectedOrder')));const list=el('ol');const knownStories=[...storyOptions,...(book?.stories||[])];const storiesById=new Map(knownStories.map(story=>[story.id,story]));
    [...selected].forEach((id,index)=>{const story=storiesById.get(id);const row=el('li',story?.title||id);if(index>0)row.append(btn(t('moveUp'),()=>{const ids=[...selected];[ids[index-1],ids[index]]=[ids[index],ids[index-1]];selected.clear();ids.forEach(value=>selected.add(value));renderOrder();},'memory-book-order-up'));if(index<selected.size-1)row.append(btn(t('moveDown'),()=>{const ids=[...selected];[ids[index],ids[index+1]]=[ids[index+1],ids[index]];selected.clear();ids.forEach(value=>selected.add(value));renderOrder();},'memory-book-order-down'));list.append(row);});orderBox.append(list);
  }
  function appendStoryOptions(fieldset,selected,ticket,owner,items,selectionChanged){
    const known=new Set([...fieldset.querySelectorAll('input[name="story_ids"]')].map(input=>input.value));
    for(const story of items){if(!uuidOK(story.id)||known.has(story.id))continue;const label=el('label');const input=el('input');input.type='checkbox';input.value=story.id;input.checked=selected.has(story.id);input.name='story_ids';input.addEventListener('change',()=>{if(input.checked){if(selected.size>=24){input.checked=false;showStatus(t('error'),'error');return;}selected.add(input.value);}else selected.delete(input.value);selectionChanged();});label.append(input,el('span',story.title));fieldset.append(label);known.add(story.id);}
    fieldset.querySelector('.memory-more-stories')?.remove();if(storyOptionsHasMore)fieldset.append(btn(t('moreStories'),()=>void loadMoreStoryOptions(fieldset,selected,ticket,owner,selectionChanged),'memory-more-stories'));
  }
  async function loadMoreStoryOptions(fieldset,selected,ticket,owner,selectionChanged){
    try{if(!storyOptionsHasMore)return;const page=storyPage+1;await loadStoryOptionsPage(ticket,owner,page,true);if(!bookCurrent(ticket,owner))return;appendStoryOptions(fieldset,selected,ticket,owner,storyOptions.slice(-8),selectionChanged);}
    catch(error){reportBook(error,owner,ticket);}
  }
  const editorialSourceKey=ref=>JSON.stringify([ref.story_id,ref.story_revision,ref.chapter_id,ref.contribution_id]);
  const editorialChildren=book=>(book.stories||[]).map(story=>({story_id:story.id,revision:String(story.revision)}));
  function validEditorial(value,book){
    if(!value||Object.keys(value).sort().join(',')!=='children,id,introduction_source_refs,revision,state,transitions,version'||value.version!==1||value.id!==book.id||String(value.revision)!==String(book.revision)||!['empty','current','source_changed'].includes(value.state)||!Array.isArray(value.children)||!Array.isArray(value.introduction_source_refs)||!Array.isArray(value.transitions))return false;
    const children=editorialChildren(book);if(value.children.length!==children.length||value.children.some((item,index)=>!item||Object.keys(item).sort().join(',')!=='revision,story_id'||item.story_id!==children[index].story_id||String(item.revision)!==children[index].revision))return false;
    if(value.state==='source_changed')return value.transitions.length===0&&value.introduction_source_refs.length===0;
    if(value.introduction_source_refs.length>12)return false;
    if(value.state==='empty')return value.transitions.length===0&&value.introduction_source_refs.length===0;
    if(value.transitions.length!==Math.max(0,children.length-1))return false;
    const validRef=ref=>ref&&Object.keys(ref).sort().join(',')==='chapter_id,contribution_id,story_id,story_revision'&&uuidOK(ref.story_id)&&uuidOK(ref.contribution_id)&&typeof ref.story_revision==='string'&&/^[1-9][0-9]*$/.test(ref.story_revision)&&typeof ref.chapter_id==='string'&&/^chapter-[1-6]$/.test(ref.chapter_id);
    if(value.introduction_source_refs.some(ref=>!validRef(ref)))return false;
    return value.transitions.every((item,index)=>item&&Object.keys(item).sort().join(',')==='left_story_id,right_story_id,source_refs,text'&&item.left_story_id===children[index].story_id&&item.right_story_id===children[index+1].story_id&&boundedText(item.text,6000)&&Array.isArray(item.source_refs)&&item.source_refs.length<=12&&item.source_refs.every(validRef));
  }
  const editorialCurrent=(ticket,owner,book,editor,sequence)=>bookCurrent(ticket,owner)&&editorialGeneration===sequence&&selectedBook?.id===book.id&&editor?.isConnected!==false;
  async function editorialCatalog(book,ticket,owner,editor,sequence){
    const options=[];
    for(const item of book.stories){
      const refs=await bookApi(`/memory-stories/${item.id}/contribution-refs?revision=${encodeURIComponent(item.revision)}`);if(!editorialCurrent(ticket,owner,book,editor,sequence))return null;
      if(refs?.version!==1||refs.id!==item.id||String(refs.revision)!==String(item.revision)||!Array.isArray(refs.chapters))throw new Error('Invalid editorial source metadata');
      for(const group of refs.chapters){if(!/^chapter-[1-6]$/.test(group?.id)||!Array.isArray(group.contribution_ids)||group.contribution_ids.length>12)throw new Error('Invalid editorial source metadata');
        group.contribution_ids.forEach((id,index)=>{if(!uuidOK(id))throw new Error('Invalid editorial source metadata');options.push({story_id:item.id,story_revision:String(item.revision),chapter_id:group.id,contribution_id:id,storyTitle:item.title,ordinal:index+1,label:`${item.title} · ${t('editorialChapter')(Number(group.id.slice(8)))} · ${t('editorialRecall')(index+1)}`});});
      }
    }
    return options;
  }
  async function loadEditorialForEdit(book,root,owner,ticket,{preserveDraft=false}={}){
    clearEditorialInspection();const editor=root.querySelector('.memory-community-book-editor'),sequence=++editorialGeneration,prior=preserveDraft?editorialModel:null;
    if(!preserveDraft){editorialModel=null;editorialPending=null;}
    try{
      const dto=await bookApi(`${API}/books/${book.id}/editorial`);if(!bookCurrent(ticket,owner)||editorialGeneration!==sequence||selectedBook?.id!==book.id)return;
      if(!validEditorial(dto,book))throw new Error('Invalid memoir editorial response');
      const options=await editorialCatalog(book,ticket,owner,editor,sequence);if(!options||!editorialCurrent(ticket,owner,book,editor,sequence))return;
      if(dto.state==='source_changed'){
        editorialModel={state:'source_changed',revision:String(book.revision),children:editorialChildren(book),transitions:[],introductionRefs:[],options,needsReload:false};
      }else{
        editorialModel={state:dto.state,revision:String(book.revision),children:editorialChildren(book),
          introductionRefs:dto.introduction_source_refs.map(ref=>({...ref})),
          transitions:dto.state==='empty'?editorialChildren(book).slice(1).map((child,index)=>({left_story_id:editorialChildren(book)[index].story_id,right_story_id:child.story_id,text:'',source_refs:[]})):dto.transitions.map(item=>({left_story_id:item.left_story_id,right_story_id:item.right_story_id,text:item.text,source_refs:item.source_refs.map(ref=>({...ref}))})),
          options,needsReload:false};
      }
      if(prior&&prior.bookId===book.id){editorialModel.introductionRefs=prior.introductionRefs;editorialModel.transitions=prior.transitions;editorialModel.needsReload=false;editorialModel.state='current';}
      editorialModel.bookId=book.id;renderBookForm(root,book,ticket,owner);
    }catch(error){if(!bookCurrent(ticket,owner)||editorialGeneration!==sequence)return;
      if(error?.status===503||error?.name==='AbortError'){editorialModel={state:'unavailable',bookId:book.id};renderBookForm(root,book,ticket,owner);return;}
      editorialModel={state:'unavailable',bookId:book.id};renderBookForm(root,book,ticket,owner);notifyError(error);
    }
  }
  function clearEditorialInspection(expected=null){
    const active=editorialInspection;if(expected&&active!==expected)return;
    editorialInspection=null;editorialInspectionEpoch++;
    if(!active)return;
    active.detailController?.abort();active.audioController?.abort();
    if(active.player){individualPlayers.delete(active.player);clearPlayer(active.player);active.player=null;}
    if(active.url){objectUrls.delete(active.url);try{URL.revokeObjectURL(active.url);}catch(_){}active.url=null;}
    active.panel?.remove();if(active.button?.isConnected){active.button.textContent=t('editorialInspect');active.button.setAttribute('aria-expanded','false');}
  }
  const editorialOptionCurrent=(model,option)=>model===editorialModel&&Array.isArray(model?.options)&&model.options.some(item=>editorialSourceKey(item)===editorialSourceKey(option));
  function editorialInspectionCurrent(session){
    const s=scopeNow(),book=session.book,editor=session.editor,panel=session.panel;
    return editorialInspection===session&&session.epoch===editorialInspectionEpoch&&bookCurrent(session.ticket,session.owner)&&
      !document.hidden&&!s?.locked&&accountKey(s)===session.owner&&selectedBook?.id===session.bookId&&String(selectedBook?.revision)===session.bookRevision&&
      JSON.stringify(editorialChildren(selectedBook))===session.children&&editorialGeneration===session.generation&&editorialModel===session.model&&
      editorialOptionCurrent(session.model,session.option)&&session.option.story_id===session.identity.story_id&&session.option.story_revision===session.identity.story_revision&&
      session.option.contribution_id===session.identity.contribution_id&&session.option.chapter_id===session.identity.chapter_id&&
      editor?.isConnected===true&&session.choice?.isConnected===true&&panel?.isConnected===true&&session.editorialPanel?.isConnected===true&&session.editorialPanel.open===true&&
      !bookContainerFor(editor)?.hidden;
  }
  const strictKeys=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')===keys.slice().sort().join(',');
  const boundedTimestamp=value=>typeof value==='string'?value.length>0&&value.length<=64:Number.isSafeInteger(value)&&value>=0;
  function validEditorialContribution(value,option){
    const keys=['author_id','base_story_revision','byline','can_delete','can_review','chapter_id','created_at','derivation','duration_ms','id','kind','language','processing_consent','sha256','state','story_id','text','version'];
    if(!strictKeys(value,keys)||value.version!==1||value.id!==option.contribution_id||value.story_id!==option.story_id||!uuidOK(value.author_id)||
      !['text','audio'].includes(value.kind)||value.state!=='accepted'||value.processing_consent!==true||typeof value.can_review!=='boolean'||typeof value.can_delete!=='boolean'||
      typeof value.base_story_revision!=='string'||value.base_story_revision.length>19||!/^[1-9][0-9]*$/.test(value.base_story_revision)||
      BigInt(value.base_story_revision)>BigInt(option.story_revision)||
      !(value.chapter_id===null||value.chapter_id===option.chapter_id)||!/^([0-9a-f]{64})$/.test(value.sha256)||
      typeof value.language!=='string'||!['zh','en','mixed','und'].includes(value.language)||!boundedText(value.byline,256)||
      !boundedTimestamp(value.created_at)||
      (value.kind==='text'&&(!safeText(value.text,8192)||value.duration_ms!==null))||
      (value.kind==='audio'&&(value.text!==null||!Number.isSafeInteger(value.duration_ms)||value.duration_ms<1||value.duration_ms>30000)))return false;
    const d=value.derivation;if(d===null)return true;
    if(!strictKeys(d,['revision','state','transcript','polished_text','tags','error_code','created_at','updated_at'])||
      !Number.isSafeInteger(d.revision)||d.revision<1||!['waiting','running','ready','failed','cancelled'].includes(d.state)||
      !(d.transcript===null||boundedText(d.transcript,8192))||!(d.polished_text===null||boundedText(d.polished_text,8192))||
      !Array.isArray(d.tags)||d.tags.length>24||d.tags.some(tag=>!safeText(tag,256))||
      !(d.error_code===null||typeof d.error_code==='string'&&/^[a-z0-9_]{1,64}$/.test(d.error_code))||
      !boundedTimestamp(d.created_at)||!boundedTimestamp(d.updated_at))return false;
    return true;
  }
  function inspectionFailure(session,error){
    if(editorialInspection!==session)return;
    const choice=session.choice;clearEditorialInspection(session);
    if(error?.name==='AbortError')return;
    if(error?.status===401||error?.status===403)reportBook(error,session.owner,session.ticket);
    if(choice?.isConnected){const note=el('p',t('editorialInspectUnavailable'),'memory-book-editorial-inspection-status');note.setAttribute('role','status');choice.append(note);}
  }
  async function loadEditorialSourceAudio(session,detail){
    if(!editorialInspectionCurrent(session)||session.audioBusy||session.audioLoaded)return;
    if(isCapturing()){appendStatus(session.panel,t('editorialAudioBlocked'));return;}
    if(detail.kind!=='audio'||detail.id!==session.identity.contribution_id||detail.story_id!==session.identity.story_id||detail.sha256!==session.detail?.sha256)return;
    const controller=new AbortController();session.audioController=controller;session.audioBusy=true;session.audioButton.disabled=true;
    try{
      const blob=await bookApi(`${API}/stories/${session.identity.story_id}/contributions/${session.identity.contribution_id}/audio`,{responseType:'blob',signal:controller.signal});
      if(!editorialInspectionCurrent(session)||controller.signal.aborted)return;
      if(!(blob instanceof Blob)||blob.size<46||blob.size>MAX_AUDIO||blob.type!=='audio/wav'||!await validWav(blob))throw new Error('Invalid source audio');
      const bytes=await blob.arrayBuffer();if(!editorialInspectionCurrent(session)||controller.signal.aborted)return;
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),byte=>byte.toString(16).padStart(2,'0')).join('');
      if(!editorialInspectionCurrent(session)||controller.signal.aborted)return;
      if(digest!==detail.sha256)throw new Error('Source audio identity mismatch');
      const url=URL.createObjectURL(blob);if(!editorialInspectionCurrent(session)||controller.signal.aborted){URL.revokeObjectURL(url);return;}
      session.url=url;objectUrls.add(url);const player=el('audio');player.controls=true;player.autoplay=false;player.preload='none';player.src=url;session.player=player;individualPlayers.set(player,session.audioButton);
      player.addEventListener('play',()=>{if(!editorialInspectionCurrent(session)||!individualPlayers.has(player)||isCapturing()){try{player.pause();}catch(_){}return;}notifyAudioStart();});
      session.audioBox.replaceChildren(player);const status=el('p',t('editorialAudioLoaded'),'memory-book-editorial-inspection-status');status.setAttribute('role','status');session.audioBox.append(status);session.audioLoaded=true;
    }catch(error){inspectionFailure(session,error);}
    finally{session.audioBusy=false;if(editorialInspection===session&&session.audioButton?.isConnected)session.audioButton.disabled=Boolean(session.audioLoaded);}
  }
  async function inspectEditorialSource(button,option,book,ticket,owner,model,editor,choice,editorialPanel){
    clearEditorialInspection();choice.querySelector('.memory-book-editorial-inspection-status')?.remove();
    if(!editorialOptionCurrent(model,option)||selectedBook?.id!==book.id||editorialPanel?.open!==true||document.hidden||scopeNow()?.locked)return;
    const session={epoch:editorialInspectionEpoch,ticket,owner,book,bookId:book.id,bookRevision:String(book.revision),children:JSON.stringify(editorialChildren(book)),generation:editorialGeneration,model,editor,choice,editorialPanel,button,option,identity:{story_id:option.story_id,story_revision:option.story_revision,chapter_id:option.chapter_id,contribution_id:option.contribution_id},panel:null,detailController:null,audioController:null,player:null,url:null};
    editorialInspection=session;button.textContent=t('editorialInspectClose');button.setAttribute('aria-expanded','true');
    const panel=el('section','','memory-book-editorial-inspection');panel.setAttribute('role','region');panel.setAttribute('aria-label',option.label);session.panel=panel;const heading=el('h4',option.label);const status=el('p',t('editorialInspectLoading'),'memory-book-editorial-inspection-status');status.setAttribute('role','status');panel.append(heading,status);choice.append(panel);
    const controller=new AbortController();session.detailController=controller;
    try{
      const detail=await bookApi(`${API}/stories/${option.story_id}/contributions/${option.contribution_id}`,{signal:controller.signal});
      if(!editorialInspectionCurrent(session)||controller.signal.aborted)return;
      if(!validEditorialContribution(detail,option))throw new Error('Invalid source detail');session.detail=detail;panel.replaceChildren(heading);
      const original=el('section','','memory-book-editorial-original');original.append(el('h5',detail.kind==='text'?t('editorialOriginalText'):t('editorialOriginalAudio')));if(typeof detail.byline==='string'&&detail.byline.trim())original.append(el('p',`${t('editorialByline')}: ${detail.byline}`,'memory-book-editorial-byline'));
      if(detail.kind==='text'){const words=el('p',detail.text,'memory-book-editorial-original-text');words.lang=detail.language;original.append(words);}
      else{const audioButton=btn(t('editorialLoadAudio'),()=>void loadEditorialSourceAudio(session,detail),'memory-book-editorial-audio-load');session.audioButton=audioButton;session.audioBox=el('div','','memory-book-editorial-audio-box');original.append(audioButton,session.audioBox);}
      original.append(el('p',t('editorialConsent'),'memory-book-editorial-consent'));panel.append(original);
      const derived=el('section','','memory-book-editorial-derived');
      if(detail.derivation===null){derived.append(el('h5',t('editorialTranscript')),el('p',t('editorialDerivationAbsent')));}
      else if(['waiting','running'].includes(detail.derivation.state))derived.append(el('h5',t('editorialTranscript')),el('p',t('editorialDerivationPending')));
      else if(['failed','cancelled'].includes(detail.derivation.state))derived.append(el('h5',t('editorialTranscript')),el('p',t('editorialDerivationFailed')));
      else{
        if(detail.derivation.transcript!==null){const transcript=el('p',detail.derivation.transcript,'memory-book-editorial-derived-text');transcript.lang=detail.language;derived.append(el('h5',t('editorialTranscript')),transcript);}
        if(detail.derivation.polished_text!==null){const polished=el('p',detail.derivation.polished_text,'memory-book-editorial-derived-text');polished.lang=detail.language;derived.append(el('h5',t('editorialPolished')),polished);}
        if(detail.derivation.transcript===null&&detail.derivation.polished_text===null)derived.append(el('h5',t('editorialTranscript')),el('p',t('editorialDerivationAbsent')));
      }
      panel.append(derived);
    }catch(error){inspectionFailure(session,error);}
  }
  function renderEditorialSourceChoices(host,refs,allowedStories,model,sectionKey,book,ticket,owner,editorialPanel){
    const fieldset=el('fieldset','', 'memory-book-editorial-sources');fieldset.append(el('legend',t(sectionKey==='introduction'?'editorialIntroSources':'editorialSelectSources')));
    const choicesFrozen=()=>editorialPending?.owner===owner||editorialBusyOwner===owner;
    if(!(model.chooserState instanceof Map))model.chooserState=new Map();
    let state=model.chooserState.get(sectionKey);if(!state||state.language!==lang()){state={language:lang(),filter:'',page:0};model.chooserState.set(sectionKey,state);}
    const allowed=model.options.filter(item=>allowedStories.has(item.story_id)),allowedKeys=new Set(allowed.map(editorialSourceKey));
    const unavailable=()=>refs.filter(ref=>!allowedKeys.has(editorialSourceKey(ref)));
    const searchLabel=el('label',t('editorialSearch'),'memory-book-editorial-search-label');const search=el('input');search.type='search';search.maxLength=120;search.value=state.filter;search.className='memory-book-editorial-search';searchLabel.append(search);
    const searchHelp=el('p',t('editorialSearchHelp'),'memory-book-editorial-search-help');
    const clear=btn(t('editorialClearSearch'),()=>{state.filter='';state.page=0;search.value='';renderRows();search.focus();},'memory-book-editorial-clear-filter');
    const counts=el('p','','memory-book-editorial-counts');counts.setAttribute('role','status');counts.setAttribute('aria-live','polite');
    const rows=el('div','','memory-book-editorial-choice-list'),unavailableBox=el('div','','memory-book-editorial-unavailable-list');
    const navigation=el('nav','','memory-book-editorial-pages');navigation.setAttribute('aria-label',t('editorialSelectSources'));
    const previous=btn(t('editorialPrevious'),()=>{if(state.page>0){clearEditorialInspection();state.page--;renderRows();}},'memory-book-editorial-page-previous');
    const pageLabel=el('span','','memory-book-editorial-page-label');pageLabel.setAttribute('aria-live','polite');
    const next=btn(t('editorialNext'),()=>{if(state.page<pageCount-1){clearEditorialInspection();state.page++;renderRows();}},'memory-book-editorial-page-next');
    navigation.append(previous,pageLabel,next);fieldset.append(searchLabel,searchHelp,clear,counts,rows,unavailableBox,navigation);host.append(fieldset);
    let pageCount=1;
    const optionLabel=option=>`${option.storyTitle||t('untitled')} · ${t('editorialChapter')(Number(option.chapter_id.slice(8)))} · ${t('editorialRecall')(option.ordinal)}`;
    const matchesForFilter=()=>{
      const query=state.filter.trim().toLocaleLowerCase(lang());
      if(!query)return allowed;
      return allowed.filter(option=>[option.storyTitle||'',t('editorialChapter')(Number(option.chapter_id.slice(8))),t('editorialRecall')(option.ordinal),String(option.ordinal)].some(value=>String(value).toLocaleLowerCase(lang()).includes(query)));
    };
    function renderRows(focusRefKey=null,focusFirstRemaining=false){
      clearEditorialInspection();rows.replaceChildren();unavailableBox.replaceChildren();
      const matches=matchesForFilter();pageCount=Math.max(1,Math.ceil(matches.length/12));state.page=Math.min(Math.max(0,state.page),pageCount-1);
      const start=matches.length?state.page*12:0,end=Math.min(matches.length,start+12),visible=matches.slice(start,end),visibleKeys=new Set(visible.map(editorialSourceKey));
      const hiddenSelected=refs.filter(ref=>allowedKeys.has(editorialSourceKey(ref))&&!visibleKeys.has(editorialSourceKey(ref))).length;
      counts.textContent=t('editorialChooserCounts')(matches.length?start+1:0,end,matches.length,allowed.length,refs.length,hiddenSelected);
      clear.disabled=!state.filter;previous.disabled=state.page===0;next.disabled=state.page>=pageCount-1;navigation.hidden=pageCount<=1;pageLabel.textContent=t('editorialPage')(state.page+1,pageCount);
      if(!allowed.length)rows.append(el('p',t('editorialNoSources')));
      else if(!matches.length)rows.append(el('p',t('editorialNoMatches')));
      for(const option of visible){
        const choice=el('div','','memory-book-editorial-choice'),label=el('label'),input=el('input');input.type='checkbox';input.checked=refs.some(ref=>editorialSourceKey(ref)===editorialSourceKey(option));input.disabled=choicesFrozen();input.dataset.refKey=editorialSourceKey(option);
        input.addEventListener('change',()=>{
          if(choicesFrozen()){input.checked=refs.some(ref=>editorialSourceKey(ref)===editorialSourceKey(option));return;}
          clearEditorialInspection();const transitionIndex=sectionKey.startsWith('transition-')?Number(sectionKey.slice(11)):null;
          if(input.checked&&transitionIndex!==null&&!model.transitions[transitionIndex]?.text.trim()){input.checked=false;appendStatus(host,t('editorialLimit'));return;}
          const existing=refs.findIndex(ref=>editorialSourceKey(ref)===editorialSourceKey(option));if(input.checked&&existing<0){const total=model.introductionRefs.length+model.transitions.reduce((sum,transition)=>sum+transition.source_refs.length,0);if(refs.length>=12||total>=96){input.checked=false;appendStatus(host,t('editorialLimit'));return;}refs.push({story_id:option.story_id,story_revision:option.story_revision,chapter_id:option.chapter_id,contribution_id:option.contribution_id});}
          else if(!input.checked&&existing>=0)refs.splice(existing,1);renderRows(input.dataset.refKey);
        });label.append(input,el('span',optionLabel(option)));
        const inspect=btn(t('editorialInspect'),()=>{if(editorialInspection?.button===inspect)clearEditorialInspection(editorialInspection);else void inspectEditorialSource(inspect,option,book,ticket,owner,model,host.closest('.memory-community-book-editor'),choice,editorialPanel);},'memory-book-editorial-inspect');inspect.dataset.sourceId=option.contribution_id;inspect.setAttribute('aria-expanded','false');choice.append(label,inspect);rows.append(choice);
      }
      const stale=unavailable();if(stale.length){unavailableBox.append(el('h4',t('editorialUnavailableSelected')));for(const ref of stale){const label=el('label'),remove=el('input');remove.type='checkbox';remove.checked=true;remove.disabled=choicesFrozen();remove.addEventListener('change',()=>{if(choicesFrozen()){remove.checked=refs.some(item=>editorialSourceKey(item)===editorialSourceKey(ref));return;}if(!remove.checked){clearEditorialInspection();const index=refs.findIndex(item=>editorialSourceKey(item)===editorialSourceKey(ref));if(index>=0)refs.splice(index,1);renderRows(null,true);}});label.append(remove,el('span',t('editorialUnavailableRemove')));unavailableBox.append(label);}}
      if(focusRefKey){const matching=[...rows.querySelectorAll('input[data-ref-key]')].find(input=>input.dataset.refKey===focusRefKey);matching?.focus({preventScroll:true});}
      else if(focusFirstRemaining){const remaining=unavailableBox.querySelector('input[type="checkbox"]')||rows.querySelector('input[data-ref-key]')||search;remaining.focus({preventScroll:true});}
    }
    search.addEventListener('input',()=>{state.filter=search.value;state.page=0;renderRows();});renderRows();
  }
  function saveEditorialPanel(host,book,ticket,owner){
    const model=editorialModel;if(!model||!['current','empty'].includes(model.state)||model.needsReload)return;
    if(pendingBook||bookSubmittingOwner===owner){appendStatus(host,t('editorialWaitBookSave'));return;}
    const makeBody=()=>({version:1,revision:model.revision,mutation_id:uuid(),children:model.children.map(item=>({...item})),introduction_source_refs:model.introductionRefs.map(ref=>({...ref})),transitions:model.transitions.map(item=>({left_story_id:item.left_story_id,right_story_id:item.right_story_id,text:item.text,source_refs:item.source_refs.map(ref=>({...ref}))}))});
    const serialized=JSON.stringify(makeBody()),body=JSON.parse(serialized);if(!body.mutation_id)return;
    const eligible=new Set(model.options.map(editorialSourceKey)),refsFit=(refs,stories)=>refs.every(ref=>eligible.has(editorialSourceKey(ref))&&stories.has(ref.story_id));
    if(body.introduction_source_refs.length>12||!refsFit(body.introduction_source_refs,new Set(model.children.map(item=>item.story_id)))||body.transitions.some((item,index)=>item.source_refs.length>12||!boundedText(item.text,6000)||Boolean(item.text.trim())!==Boolean(item.source_refs.length)||!refsFit(item.source_refs,new Set([model.children[index].story_id,model.children[index+1].story_id])))||body.introduction_source_refs.length+body.transitions.reduce((sum,item)=>sum+item.source_refs.length,0)>96){appendStatus(host,t('editorialLimit'));return;}
    editorialPending={bookId:book.id,owner,body,serialized};for(const field of host.querySelectorAll('textarea,input,select'))field.disabled=true;const bookSave=host.closest('.memory-community-book-editor')?.querySelector('.memory-community-book-form button[type="submit"]');if(bookSave)bookSave.disabled=true;void submitEditorial(host,book,ticket,owner);
  }
  async function submitEditorial(host,book,ticket,owner){
    if(editorialBusyOwner===owner||!editorialPending||editorialPending.bookId!==book.id||editorialPending.owner!==owner)return;
    const root=bookContainerFor(host);if(!root)return;
    editorialBusyOwner=owner;const pending=editorialPending,button=host.querySelector('.memory-book-editorial-save');if(button)button.disabled=true;
    try{
      const result=await bookApi(`${API}/books/${book.id}/editorial`,{method:'PUT',rawBody:pending.serialized,headers:{'Content-Type':'application/json'}});
      if(!bookCurrent(ticket,owner)||selectedBook?.id!==book.id||editorialPending!==pending)return;
      if(!validEditorial(result,{...book,revision:result.revision})||result.state!=='current')throw new Error('Invalid memoir editorial save response');
      editorialPending=null;await loadBookForEdit(book.id,root,owner,ticket,{preserveBookDraft:true});showStatus(t('editorialSaved'),'success');
    }catch(error){if(!bookCurrent(ticket,owner)||selectedBook?.id!==book.id||editorialPending!==pending)return;
      if(error?.status===409){editorialPending=null;if(editorialModel)editorialModel.needsReload=true;appendStatus(host,t('editorialConflict'));renderBookForm(root,book,ticket,owner);}
      else {if(button){button.disabled=false;button.textContent=t('editorialRetry');}if(error?.status!==503)notifyError(error);}
    }finally{if(editorialBusyOwner===owner){editorialBusyOwner='';if(bookCurrent(ticket,owner)&&selectedBook?.id===book.id){const currentSave=root.querySelector('.memory-book-editorial-save');if(currentSave){currentSave.disabled=Boolean(editorialModel?.needsReload);currentSave.textContent=t(editorialPending?'editorialRetry':'editorialSave');}const bookSave=root.querySelector('.memory-community-book-form button[type="submit"]');if(bookSave)bookSave.disabled=bookSubmittingOwner===owner||Boolean(editorialPending);}}}
  }
  async function reloadEditorial(host,book,ticket,owner){
    clearEditorialInspection();const draft=editorialModel;if(!draft)return;const fresh=await bookApi(`${API}/books/${book.id}`);if(!bookCurrent(ticket,owner)||selectedBook?.id!==book.id)return;
    if(!validBookTarget(fresh))throw new Error('Invalid current memoir');selectedBook=fresh;
    const oldChildren=JSON.stringify(draft.children),newChildren=JSON.stringify(editorialChildren(fresh));
    if(oldChildren!==newChildren){
      const sequence=++editorialGeneration,root=bookContainerFor(host),options=await editorialCatalog(fresh,ticket,owner,root.querySelector('.memory-community-book-editor'),sequence);
      if(!options||!bookCurrent(ticket,owner)||selectedBook?.id!==fresh.id)return;
      draft.state='source_changed';draft.needsReload=true;draft.message=t('editorialChanged');draft.currentRevision=String(fresh.revision);draft.currentChildren=editorialChildren(fresh);draft.currentOptions=options;
      renderBookForm(root,fresh,ticket,owner);return;
    }
    await loadEditorialForEdit(fresh,bookContainerFor(host),owner,ticket,{preserveDraft:true});
  }
  function renderEditorialPanel(root,book,ticket,owner){
    const model=editorialModel;if(!model||model.bookId!==book.id||model.state==='unavailable')return null;
    const section=el('details','','memory-book-editorial-panel');section.addEventListener('toggle',()=>{if(!section.open)clearEditorialInspection();});const summary=el('summary',t('editorialHeading'));section.append(summary,el('p',t('editorialHelp'),'memory-community-help'));
    if(model.state==='source_changed'){
      section.append(appendStatus(section,model.message||t('editorialChanged')));
      if(model.transitions.some(item=>item.text)){const saved=el('details','','memory-book-editorial-draft');saved.append(el('summary',t('editorialDraftKept')));for(const item of model.transitions)if(item.text)saved.append(el('p',item.text));section.append(saved);}
      section.append(btn(t('editorialReload'),()=>void loadBookForEdit(book.id,bookContainerFor(root)||root,owner,ticket),'memory-book-editorial-reload'),btn(t('editorialStartFresh'),()=>{
        const children=model.currentChildren||editorialChildren(book),priorText=new Map(model.transitions.map(item=>[`${item.left_story_id}:${item.right_story_id}`,item.text]));
        model.state='empty';model.revision=model.currentRevision||String(book.revision);model.children=children;model.options=model.currentOptions||model.options;model.introductionRefs=[];model.transitions=children.slice(1).map((child,index)=>({left_story_id:children[index].story_id,right_story_id:child.story_id,text:priorText.get(`${children[index].story_id}:${child.story_id}`)||'',source_refs:[]}));model.needsReload=false;model.message='';renderBookForm(bookContainerFor(root)||root,book,ticket,owner);
      },'memory-book-editorial-reload'));root.append(section);return section;
    }
    const introRefs=model.introductionRefs,allStories=new Set(model.children.map(item=>item.story_id));
    renderEditorialSourceChoices(section,introRefs,allStories,model,'introduction',book,ticket,owner,section);
    for(let index=0;index<model.transitions.length;index++){
      const transition=model.transitions[index],left=book.stories[index]?.title||t('untitled'),right=book.stories[index+1]?.title||t('untitled'),part=el('section','','memory-book-editorial-transition');
      const label=el('label',`${t('editorialTransition')}: ${left} → ${right}`),textarea=el('textarea');textarea.maxLength=6000;textarea.value=transition.text;textarea.addEventListener('input',()=>{transition.text=textarea.value;});label.append(textarea);part.append(label);
      renderEditorialSourceChoices(part,transition.source_refs,new Set([transition.left_story_id,transition.right_story_id]),model,`transition-${index}`,book,ticket,owner,section);section.append(part);
    }
    const status=appendStatus(section,'');if(model.needsReload){status.textContent=model.message||t('editorialConflict');section.append(btn(t('editorialReload'),()=>{void reloadEditorial(section,book,ticket,owner).catch(error=>notifyError(error));},'memory-book-editorial-reload'));}
    const frozen=editorialPending?.bookId===book.id;
    if(frozen)for(const field of section.querySelectorAll('textarea,input,select'))field.disabled=true;
    const save=btn(frozen?t('editorialRetry'):t('editorialSave'),()=>{
      if(editorialPending?.bookId===book.id)void submitEditorial(section,book,ticket,owner);else saveEditorialPanel(section,book,ticket,owner);
    },'memory-community-primary memory-book-editorial-save');save.disabled=model.needsReload||Boolean(pendingBook)||bookSubmittingOwner===owner||editorialBusyOwner===owner;section.append(save);root.append(section);return section;
  }
  function renderBookForm(root,book,ticket,owner){
    clearEditorialInspection();let editor=root.querySelector('.memory-community-book-editor');if(!editor){editor=el('section','','memory-community-book-editor');editor.id='memory-community-book-editor';root.append(editor);}editor.hidden=!bookEditorOpen;editor.replaceChildren();if(!bookEditorOpen)return editor;
    const form=el('form','','memory-community-book-form');const titleLabel=el('label',t('bookTitle'));const title=el('input');title.name='title';title.maxLength=512;title.value=pendingBook?.body.title??bookTitleDraft??book?.title??'';title.addEventListener('input',()=>bookTitleDraft=title.value);titleLabel.append(title);
    const introLabel=el('label',t('introduction'));const intro=el('textarea');intro.name='introduction';intro.maxLength=6000;intro.value=pendingBook?.body.introduction??bookIntroDraft??book?.introduction??'';intro.addEventListener('input',()=>bookIntroDraft=intro.value);introLabel.append(intro);
    const choose=el('fieldset','','memory-book-story-options');choose.append(el('legend',t('chooseStories')));const selected=new Set(bookStorySelection);bookStorySelection=selected;const order=el('section','','memory-book-order');const renderOrder=()=>renderBookSelectionOrder(order,selected,book,renderOrder);
    appendStoryOptions(choose,selected,ticket,owner,storyOptions,renderOrder);renderOrder();
    const submit=el('button',pendingBook?t('retryBook'):book?t('updateBook'):t('createBook'));submit.type='submit';submit.className='memory-community-primary';submit.disabled=bookSubmittingOwner===owner||Boolean(editorialPending)||editorialBusyOwner===owner;form.append(titleLabel,introLabel,choose,order,submit);
    if(pendingBook)for(const field of form.querySelectorAll('input,textarea,select'))field.disabled=true;
    form.addEventListener('submit',event=>{event.preventDefault();void saveBook(form,book,ticket,owner);});editor.append(form);if(book)renderEditorialPanel(editor,book,ticket,owner);return editor;
  }
  function updateBookEditorToggle(root){const toggle=root?.querySelector('.memory-book-compose-cta');if(!toggle)return;toggle.textContent=t(bookEditorOpen?'collapseBookEditor':pendingBook?'continueBook':selectedBook?'continueEditBook':'composeBook');toggle.setAttribute('aria-expanded',String(bookEditorOpen));}
  function bookContainerFor(node){while(node&&!bookContainers.has(node))node=node.parentNode;return node;}
  async function loadBookForEdit(id,root,owner,ticket,{preserveEditorial=false,preserveBookDraft=false}={}){
    clearEditorialInspection();const editSequence=++bookEditSequence;editorialGeneration++;
    try{const book=await bookApi(`${API}/books/${id}`);if(!bookCurrent(ticket,owner)||bookEditSequence!==editSequence)return;
      selectedBook=book;if(!preserveEditorial){editorialModel=null;editorialPending=null;}if(!preserveBookDraft){bookTitleDraft=book.title;bookIntroDraft=book.introduction;bookStorySelection=new Set(book.stories.map(story=>story.id));}bookEditorOpen=true;updateBookEditorToggle(root);renderBookForm(root,book,ticket,owner);await loadEditorialForEdit(book,root,owner,ticket,{preserveDraft:preserveEditorial});
    }catch(error){reportBook(error,owner,ticket);}
  }
  async function openBookTarget(id,owner,ticket){
    try{const book=await bookApi(`${API}/books/${id}`);if(!bookCurrent(ticket,owner))return;
      if(!validBookTarget(book))throw new Error('Invalid saved collection');onOpenStory(book);
    }catch(error){reportBook(error,owner,ticket);}
  }
  async function saveBook(form,book,ticket,owner){
    if(bookSubmittingOwner===owner||editorialPending||editorialBusyOwner===owner)return;
    if(!pendingBook){const ids=[...bookStorySelection];
      if(!form.elements.title.value.trim()||ids.length<1||ids.length>24||new Set(ids).size!==ids.length){showStatus(t('error'),'error');return;}
      pendingBook={path:book?`${API}/books/${book.id}`:`${API}/books`,method:book?'PUT':'POST',body:{title:form.elements.title.value,language:lang(),introduction:form.elements.introduction.value,story_ids:ids.join(','),revision:book?.revision||'0',mutation_id:uuid()}};if(!pendingBook.body.mutation_id)return;}
    bookSubmittingOwner=owner;const submit=form.querySelector('button[type="submit"]');if(submit)submit.disabled=true;for(const field of form.querySelectorAll('input,textarea,select'))field.disabled=true;
    try{await bookApi(pendingBook.path,{method:pendingBook.method,body:pendingBook.body});if(!bookCurrent(ticket,owner))return;pendingBook=null;selectedBook=null;bookEditorOpen=false;bookStorySelection=new Set();bookTitleDraft='';bookIntroDraft='';showStatus(t('bookSaved'),'success');await books(bookContainerFor(form));}
    catch(error){if(bookCurrent(ticket,owner)){if(error?.status===409){pendingBook=null;for(const field of form.querySelectorAll('input,textarea,select'))field.disabled=false;if(submit){submit.disabled=false;submit.textContent=book?t('updateBook'):t('createBook');}}else if(submit){submit.textContent=t('retryBook');}updateBookEditorToggle(bookContainerFor(form)?.firstChild);reportBook(error,owner,ticket);}}
    finally{if(bookSubmittingOwner===owner){bookSubmittingOwner='';if(bookCurrent(ticket,owner)){if(submit)submit.disabled=false;if(pendingBook)for(const field of form.querySelectorAll('input,textarea,select'))field.disabled=true;}}}
  }
  function suspend({cancelJobs=true}={}){
    clearEditionReview();clearSavedEditions();
    const oldJob=activeJob?.id,jobState=activeJob?.state;
    const oldScope=currentScope,s=scopeNow(),readerContainer=mount?.parentNode;if(s&&!s.locked)pruneConversationHints(s.account,s.library,membershipRevision(s));
    resetEditorialContextChoice();clearReplySpeech();clearChatComposition();clearIdeaComposition();epoch++;stopFamilyListening();stopRequests(false);stopPoll();invalidateChatRecovery();void clearCapture(false);void clearChatCapture();void clearIdeaVoice(true);chatTranscript='';chatVoiceError='';forgetUrls();
    if(cancelJobs&&oldJob&&['queued','running'].includes(jobState)&&oldScope&&accountKey(s)===JSON.stringify([oldScope.account,oldScope.library])&&!s?.locked)void request(`${API}/jobs/${oldJob}`,{method:'DELETE'}).catch(()=>{});
    if(readerContainer&&!bookContainers.has(readerContainer)){readerContainer.replaceChildren();roots.delete(readerContainer);}conversationRestorationNotice=false;
    if(planPanelNode){planPanelNode.replaceChildren();planPanelNode.hidden=true;}planData=null;planPanelNode=null;planButton=null;
    mount=null;panelNode=null;statusNode=null;target=null;targetFingerprint='';currentScope=oldScope;
    contributionList=[];contributionDetails.clear();canReview=false;canDelete=false;contributionPage=1;contributionsHasMore=false;contributionsBusy=false;
    conversation=null;conversationList=[];conversationDrafts.clear();conversationSelectionEpoch++;conversationLoading=false;conversationCreating=false;conversationDeleting=false;conversationCreateToken=null;conversationDeleteToken=null;conversationLoadToken=null;turns=[];turnPage=1;turnsHasMore=false;turnsBusyToken=null;assistantInflightToken=null;recentTurn=null;messageDraft=null;chatTextDraft='';activeJob=null;pendingJob=null;pendingContribution=null;recording=null;
    contributionDraft={mode:'text',text:'',byline:'',chapter_id:'',consent:false};ideaDraft='';memoirFormChoice='existing';activeTab='voice';
  }
  function clear({cancelJobs=true}={}){
    suspend({cancelJobs});conversationHints.clear();bookEpoch++;stopRequests(true);unloadVisibility();
    for(const root of roots){root.replaceChildren();if(bookContainers.has(root))root.hidden=true;}
    roots.clear();for(const container of bookContainers)container.hidden=true;bookContainers.clear();mount=null;panelNode=null;statusNode=null;currentScope=null;caps=null;capsIdentity='';voiceCapabilitiesOwner='';voiceCapabilitiesValue=null;voiceCapabilitiesPending=null;
    pendingBook=null;bookSubmittingOwner='';selectedBook=null;bookEditorOpen=false;booksList=[];storyOptions=[];storyPage=0;storyOptionsHasMore=false;bookStorySelection=new Set();bookTitleDraft='';bookIntroDraft='';bookPage=1;booksHasMore=false;editorialModel=null;editorialPending=null;editorialBusyOwner='';editorialGeneration++;bookEditSequence++;
  }
  function confirmLeave(container,expectedTarget=null){
    // Only the exact mounted reader target can ask. A detached reader must not
    // guard or prompt on behalf of a newer target or library scope.
    const s=scopeNow(),owner=accountKey(s);
    if(!container)return true;
    if(mount?.parentNode!==container)return expectedTarget?false:true;
    if(!target||!currentScope)return expectedTarget?false:true;
    if(owner!==accountKey(currentScope)||s?.locked||targetFingerprint!==targetScopeFingerprint(owner,target))return false;
    if(expectedTarget&&targetKey(expectedTarget)!==targetKey(target))return false;
    const currentFile=panelNode?.querySelector('input[type="file"]')?.files?.length>0;
    const hasDraft=Boolean(chatTextDraft||chatTranscript||ideaDraft||
      [...conversationDrafts.values()].some(value=>typeof value==='string'&&value.length>0)||
      contributionDraft.text||contributionDraft.byline||contributionDraft.chapter_id||contributionDraft.consent||currentFile||
      pendingContribution||recording||captureStarting||captureHandle||chatCaptureStarting||chatCaptureHandle||chatCaptureReady||chatRecordingBusy||chatTranscribing||ideaCaptureStarting||ideaCaptureHandle||ideaTranscribing||ideaTranscript||memoirFormChoice!=='existing'||
      editionReview&&(editionReview.dirty||editionReview.pending||editionReview.busy||editionReview.composing)||
      chatComposition||messageDraft||pendingJob||assistantInflightToken||conversationCreating||conversationDeleting||
      activeJob&&['queued','running'].includes(activeJob.state));
    return !hasDraft||window.confirm(t('confirmLeave'));
  }
  function detach(container){if(container&&mount?.parentNode!==container)return false;suspend();return true;}
  async function translate(){
    if(savedEditionState)clearSavedEditionSource(savedEditionState,{resetList:true,status:'idle'});
    const saved=[];
    for(const field of panelNode?.querySelectorAll('input,textarea,select')||[]){if(field.type==='file')continue;saved.push({type:field.type,value:field.value,checked:field.checked,selectedIndex:field.selectedIndex});}
    if(mount&&target){const heading=mount.querySelector('.memory-community-heading');if(heading)heading.textContent=target?.type==='memoir'?(lang()==='zh'?'聊聊这本回忆录':'Talk about this memoir'):targetLabel();const context=mount.querySelector('.memory-community-memoir-context');if(context)context.textContent=`${t('memoirScope')} · ${targetLabel()}`;renderTabs();await renderPanel();if(conversationRestorationNotice)showStatus(t('conversationRestored'),'success');if(savedEditionState)renderSavedEditionShelf(savedEditionState,epoch,accountKey(scopeNow()));
      const fields=panelNode?.querySelectorAll('input,textarea,select')||[];let index=0;for(const field of fields){if(field.type==='file')continue;const prior=saved[index++];if(!prior)continue;field.value=prior.value;if(prior.type==='checkbox'||prior.type==='radio')field.checked=prior.checked;if(prior.selectedIndex!==undefined)field.selectedIndex=prior.selectedIndex;}}
    const outsideEditorialSources=field=>!field.closest('.memory-book-editorial-sources');
    for(const container of bookContainers){const savedFields=[...(container.querySelectorAll?.('input,textarea,select')||[])].filter(field=>field.type!=='file'&&outsideEditorialSources(field)).map(field=>({type:field.type,value:field.value,checked:field.checked}));await books(container);const fields=[...(container.querySelectorAll?.('input,textarea,select')||[])].filter(field=>field.type!=='file'&&outsideEditorialSources(field));let index=0;for(const field of fields){const prior=savedFields[index++];if(!prior)continue;field.value=prior.value;if(prior.type==='checkbox'||prior.type==='radio')field.checked=prior.checked;}}
  }
  return {attach,clear,suspend,detach,confirmLeave,translate,books,stopPlayback,isCapturing,isBookEditing:()=>bookEditorOpen||Boolean(pendingBook)||Boolean(editorialPending)};
};
