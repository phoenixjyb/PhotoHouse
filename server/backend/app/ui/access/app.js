'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = {language:'zh', mode:'login', generation:0, controllers:new Set(), profile:null,
    csrf:null, library:null, catalogue:null, sessionCheckFailed:false, viewerGeneration:0, page:1, busy:false, locked:false, invite:null, memberPage:1, memberGeneration:0, memberTotal:0, total:0, videoRetryTimer:null, videoController:null};
  let storyWorkspace, memoryCommunity;
  const assistantState={context:null,binding:null,busy:false,items:[],turnTrail:[],controller:null,transcriptionController:null,transcriptionAttempt:null,speechController:null,speechUrl:null,speech:false,transcribe:false,capture:null,captureStarting:false,releaseRequested:false,cancelRequested:false,pressPointerId:null,ignoreMicClick:false,transcribing:false,transcriptRequestId:null,pendingTranscriptRequestId:null,transcriptReviewBinding:null,transcriptReviewPending:false,transcriptLanguage:null,turnRequestId:null,turnReceipt:null,receipt:null,pendingTurn:null,turnAttempt:null};
  const assistantRecoveryKey='photohouse.assistant.turn-recovery.v1',assistantRecoveryMaxChars=512;
  const words = {
    en: {manageMembers:'Review library members',revokeHelp:'Revoking access stops future requests to this library. Files already downloaded cannot be recalled.',revoke:'Revoke access',confirmRevoke:'Confirm revocation',cancel:'Cancel',confirmFor:'Revoke library access for',revoked:'Access revoked.',conflict:'Membership changed. Review the refreshed list before trying again.',owner:'Owner',viewer:'Viewer',contributor:'Contributor',approved:'Approved',requested:'Requested',rejected:'Rejected',unavailableMember:'Currently unavailable',memberRevoked:'Revoked',tagline:'A place for our memories',eyebrow:'YOUR FAMILY, TOGETHER',welcome:'The moments we keep close.',intro:'A private home for family photos. Sign in, or join with the invitation your library owner sent you.',signIn:'Sign in',join:'Join with an invitation',phone:'Phone number',phoneHelp:'Include the country code. Your phone number is your sign-in name.',password:'Password',passwordHelp:'Choose a passphrase of 8–128 characters.',invitation:'Invitation code',inviteHelp:'Use the code sent for this phone number. An accepted invitation opens that library.',help:'Need an invitation or help signing in? Contact your library owner.',yourLibrary:'YOUR FAMILY LIBRARY',gallery:'Little moments. Lasting memories.',signOut:'Sign out',libraryLabel:'Library',refresh:'Refresh',previous:'Previous',next:'Next',anotherInvite:'Have an invitation to another library?',accept:'Accept invitation',inviteSomeone:'Invite someone to this library',ownerHelp:'Create a code for their phone number, then send it privately. They join as a viewer. Original downloads are not included.',createInvite:'Create invitation',sendCode:'Send this code privately. It expires in 24 hours.',cancelInvite:'Cancel this invitation',close:'Close',download:'Download original',captionNote:'Generated descriptions may be inaccurate. Original downloads require separate permission.',footer:'PhotoHouse · Shared by invitation',checking:'Checking your session…',loading:'Loading your library…',denied:'Access could not be confirmed. Check your details or contact your library owner.',unavailable:'PhotoHouse is unavailable. Please try again later.',limited:'Too many attempts. Please wait before trying again.',changed:'Your access changed. Refresh or contact your library owner.',noLibrary:'No library is currently available. Ask your owner for an invitation.',noPhotos:'No photos are available in this library yet.',signedOut:'You are signed out.',logoutFailed:'Sign out could not be completed. Your photos are hidden; try Sign out again.',accepted:'Invitation accepted.',cancelled:'Invitation cancelled.',noCaptions:'No description is available yet.',edited:'Family description',generated:'Generated description',moreCaptions:'Only the first 20 descriptions are shown.',truncated:'Description shortened.',photo:'Photo',video:'Video',other:'Media',previewMissing:'Preview unavailable',working:'Please wait…',invalidPhone:'Include an explicit country code, for example +86.',invalidPassword:'Choose a passphrase of 8–128 characters.',page:'Page',of:'of',photos:'items'},
    zh: {manageMembers:'查看相册库成员',revokeHelp:'撤销权限后，对方的新请求将无法访问此相册库。已下载的文件无法收回。',revoke:'撤销访问权限',confirmRevoke:'确认撤销',cancel:'取消',confirmFor:'撤销以下成员的相册库访问权限：',revoked:'已撤销访问权限。',conflict:'成员信息已更新，请查看刷新后的列表再操作。',owner:'主人',viewer:'浏览者',contributor:'协作者',approved:'已批准',requested:'待批准',rejected:'已拒绝',unavailableMember:'当前不可访问',memberRevoked:'已撤销',tagline:'珍藏一家人的时光',eyebrow:'属于我们一家人的回忆',welcome:'把美好时光，留在身边。',intro:'一个私密的家庭相册。登录，或使用相册主人发给你的邀请码加入。',signIn:'登录',join:'使用邀请码加入',phone:'手机号码',phoneHelp:'请包含国家区号。手机号码用作登录名。',password:'密码',passwordHelp:'请设置 8–128 个字符的密码或短语。',invitation:'邀请码',inviteHelp:'请使用为此手机号码生成的邀请码。验证成功后即可访问对应相册。',help:'需要邀请码或登录帮助？请联系相册主人。',yourLibrary:'我们的家庭相册',gallery:'小小瞬间，长长回忆。',signOut:'退出登录',libraryLabel:'相册库',refresh:'刷新',previous:'上一页',next:'下一页',anotherInvite:'收到另一个相册库的邀请码？',accept:'接受邀请',inviteSomeone:'邀请家人加入这个相册库',ownerHelp:'为对方的手机号码生成邀请码，再私下发送。对方将以浏览者身份加入，不包含原文件下载权限。',createInvite:'生成邀请码',sendCode:'请私下发送此邀请码，有效期为 24 小时。',cancelInvite:'取消此邀请',close:'关闭',download:'下载原文件',captionNote:'自动生成的描述可能不准确。下载原文件需要单独授权。',footer:'PhotoHouse · 受邀共享的家庭相册',checking:'正在检查登录状态…',loading:'正在加载相册…',denied:'暂时无法确认访问权限。请检查信息或联系相册主人。',unavailable:'PhotoHouse 暂时不可用，请稍后重试。',limited:'尝试次数过多，请稍后再试。',changed:'访问权限已发生变化，请刷新或联系相册主人。',noLibrary:'目前没有可访问的相册库，请向相册主人索取邀请。',noPhotos:'这个相册库暂时没有可浏览的照片。',signedOut:'已退出登录。',logoutFailed:'暂时未能完成退出。照片已隐藏，请再次点击退出登录。',accepted:'已接受邀请。',cancelled:'已取消邀请。',noCaptions:'暂时没有描述。',edited:'家人描述',generated:'自动生成的描述',moreCaptions:'仅显示前 20 条描述。',truncated:'描述已缩短。',photo:'照片',video:'视频',other:'媒体',previewMissing:'预览暂不可用',working:'请稍候…',invalidPhone:'请包含国家区号，例如 +86。',invalidPassword:'请设置 8–128 个字符的密码或短语。',page:'第',of:'/',photos:'项'}
  };
  Object.assign(words.en,{assistantTrailTitle:'Recent turns on this page',assistantTrailYou:'You',assistantTrailAssistant:'Assistant'});
  Object.assign(words.zh,{assistantTrailTitle:'本页最近对话',assistantTrailYou:'你',assistantTrailAssistant:'助手'});
  const t = key => words[state.language][key] || key;
  Object.assign(words.en,{libraryTools:'Explore this library'});
  Object.assign(words.zh,{libraryTools:'浏览相册库'});
  Object.assign(words.en,{assistantTitle:'Find a memory in your words',assistantHelp:'Search this library only. Add details to refine; matching photos are shown before you open one. Recognized text, submitted commands, and processing status are kept for 30 days. Recordings are transient. This is separate from saved family notes.',assistantPrompt:'What would you like to find?',assistantSend:'Find',assistantClear:'Clear',assistantCancel:'Cancel request',assistantCancelled:'Request canceled.',assistantWorking:'Looking in this library…',assistantError:'The assistant could not complete that request. Try again.',assistantDenied:'Your access could not be confirmed. Sign in again or contact the library owner.',assistantConflict:'The library changed. Clear this search and try again.',assistantLimited:'Too many requests. Please wait and try again.',assistantUnavailable:'The assistant is temporarily unavailable. Please try again later.',assistantInvalid:'The reply could not be safely displayed. Please try again.',assistantNoResults:'No matching photos were found.',assistantOpen:'Open photo',assistantUnsupported:'This request is not supported yet.'});
  Object.assign(words.zh,{assistantTitle:'用一句话找回忆',assistantHelp:'仅在当前相册库中查找。你可以继续补充条件；打开照片前会显示匹配结果。识别文本、发送的命令和处理状态将保留 30 天。录音仅临时使用，与保存的家人故事分开。',assistantPrompt:'你想找什么？',assistantSend:'查找',assistantClear:'清空',assistantCancel:'取消请求',assistantCancelled:'已取消请求。',assistantWorking:'正在这个相册库中查找…',assistantError:'暂时无法完成查找，请重试。',assistantDenied:'无法确认你的访问权限，请重新登录或联系相册主人。',assistantConflict:'相册库信息已更新，请清空后重新查找。',assistantLimited:'请求过于频繁，请稍后再试。',assistantUnavailable:'助手暂时不可用，请稍后重试。',assistantInvalid:'无法安全显示这条回复，请重试。',assistantNoResults:'没有找到匹配的照片。',assistantOpen:'打开照片',assistantUnsupported:'暂不支持这个请求。'});
  Object.assign(words.en,{assistantMic:'Hold to talk',assistantStop:'Stop recording',assistantRecordingCancel:'Cancel recording',assistantRecording:'Recording. Up to 30 seconds.',assistantTranscribing:'Transcribing your recording…',assistantTranscriptTitle:'Review the transcript before using it',assistantTranscriptLanguage:'Detected language',assistantLangZh:'Chinese',assistantLangEn:'English',assistantLangMixed:'Chinese and English',assistantLangUnknown:'Unknown',assistantTranscriptReady:'Transcript ready. Review it, then choose Use transcript.',assistantTranscriptError:'Transcription failed. Try again.',assistantTranscriptTooLong:'The transcript and your typed text exceed 1,024 UTF-8 bytes. Edit either field; nothing was removed.',assistantUseTranscript:'Use transcript',assistantDiscardTranscript:'Discard transcript',assistantTextTooLong:'Keep the request under 1,024 UTF-8 bytes.'});
  Object.assign(words.zh,{assistantMic:'按住说话',assistantStop:'结束录音',assistantRecordingCancel:'取消录音',assistantRecording:'正在录音，最长 30 秒。',assistantTranscribing:'正在识别录音…',assistantTranscriptTitle:'请先检查识别文本，再使用',assistantTranscriptLanguage:'识别语言',assistantLangZh:'中文',assistantLangEn:'英文',assistantLangMixed:'中英混合',assistantLangUnknown:'无法判断',assistantTranscriptReady:'识别完成。请检查文本，再选择放入搜索框。',assistantTranscriptError:'语音识别失败，请重试。',assistantTranscriptTooLong:'识别文本与已输入内容合计超过 1,024 个 UTF-8 字节。请编辑任一文本；内容均未删除。',assistantUseTranscript:'放入搜索框',assistantDiscardTranscript:'丢弃识别文本',assistantTextTooLong:'请输入不超过 1,024 个 UTF-8 字节的内容。'});
  Object.assign(words.en,{assistantPlay:'Play spoken result count',assistantSpeechStop:'Stop playback',assistantSpeechError:'Spoken result count is unavailable. Try again.'});
  Object.assign(words.zh,{assistantPlay:'播放结果数量',assistantSpeechStop:'停止播放',assistantSpeechError:'暂时无法播放结果数量，请重试。'});
  Object.assign(words.en,{assistantReceiptUnknown:'The server receipt is unknown. Check again when the connection is available.',assistantReceiptDisabled:'Request tracking is disabled for this service.',assistantReceiptReceived:'Received by the server; still processing.',assistantReceiptSucceeded:'The server completed this request.',assistantReceiptFailed:'The server could not complete this request.',assistantReceiptInterrupted:'Processing stopped before completion.',assistantReceiptCheck:'Check server receipt',assistantReceiptChecking:'Checking the server receipt…',assistantReceiptUnavailable:'The receipt could not be checked.',assistantReceiptUnconfirmed:'The request was sent, but the server receipt is not confirmed.',assistantOutcomeDisplayed:'The result was shown in this tab.',assistantOutcomeFailed:'The result could not be shown in this tab.',assistantRequestIdLabel:'Request ID',assistantReceiptTrackingOff:'Tracking disabled',assistantRecoveryOffer:'A previous request may have reached the server. Check its receipt before starting again. Its reply and search context are not stored for recovery.',assistantRecoveryChecking:'Checking the earlier request…',assistantRecoveryReceived:'The server received this request and may still be processing it. Check again or acknowledge to start fresh.',assistantRecoverySucceeded:'The server completed this request, but its reply and search context are unavailable. Start a new search if you still need one.',assistantRecoveryFailed:'The server recorded a failure. The original reply is unavailable. Acknowledge before starting fresh.',assistantRecoveryInterrupted:'Server processing was interrupted. The reply is unavailable. Acknowledge before starting fresh.',assistantRecoveryUnknown:'The earlier request outcome is still unknown. Do not resend it automatically; check again or acknowledge to start fresh.',assistantRecoveryAcknowledge:'Acknowledge and start fresh'});
  Object.assign(words.zh,{assistantReceiptUnknown:'服务器是否收到请求尚未确认。网络恢复后可以再次查询。',assistantReceiptDisabled:'此服务未启用请求跟踪。',assistantReceiptReceived:'服务器已收到，仍在处理中。',assistantReceiptSucceeded:'服务器已完成此请求。',assistantReceiptFailed:'服务器未能完成此请求。',assistantReceiptInterrupted:'请求在完成前中断。',assistantReceiptCheck:'查询服务器回执',assistantReceiptChecking:'正在查询服务器回执…',assistantReceiptUnavailable:'暂时无法查询服务器回执。',assistantReceiptUnconfirmed:'请求已发送，但尚未确认服务器回执。',assistantOutcomeDisplayed:'此标签页已显示结果。',assistantOutcomeFailed:'此标签页未能显示结果。',assistantRequestIdLabel:'请求编号',assistantReceiptTrackingOff:'未启用跟踪',assistantRecoveryOffer:'之前的请求可能已到达服务器。开始新请求前，请先查询回执。回复和搜索上下文不会保存在此处供恢复。',assistantRecoveryChecking:'正在查询之前的请求…',assistantRecoveryReceived:'服务器已收到请求，可能仍在处理中。可以再次查询，或确认后重新开始。',assistantRecoverySucceeded:'服务器已完成请求，但无法恢复其回复和搜索上下文。如仍需查找，请开始新的搜索。',assistantRecoveryFailed:'服务器记录了失败，原回复无法恢复。确认后可以重新开始。',assistantRecoveryInterrupted:'服务器处理中断，回复无法恢复。确认后可以重新开始。',assistantRecoveryUnknown:'之前请求的结果仍不确定。系统不会自动重发；请再次查询，或确认后重新开始。',assistantRecoveryAcknowledge:'确认并重新开始'});
  Object.assign(words.en,{assistantPendingTitle:'Request awaiting confirmation',assistantPendingSending:'Sending this request…',assistantPendingCancelled:'Stopped waiting. The server may still process this request.',assistantPendingUnknown:'The outcome is unknown. The server may already have processed this request.',assistantPendingDisabled:'Request tracking is unavailable. This does not show whether the server processed the request.',assistantPendingReceived:'The server received this request and may still be processing it.',assistantPendingSucceeded:'The server completed this request, but its reply and updated context were not recovered.',assistantPendingFailed:'The server recorded a failure. Its reply is unavailable.',assistantPendingInterrupted:'Server processing was interrupted. Its reply is unavailable.',assistantPendingQuestion:'Submitted question',assistantPendingHelp:'Checking a receipt only reads its status; it never resends this request. Acknowledge to clear this conversation and start fresh. The server may still finish the original request.',assistantPendingCheckUnavailable:'The receipt could not be checked. The last known status is unchanged; this does not mean the request was not processed.',assistantPendingAcknowledge:'Acknowledge and start fresh',assistantPendingRestore:'Close and restore question',assistantPendingRestoreHelp:'The server recorded a failed or interrupted request. Restore its question as a draft only if the composer is empty; sending still requires your action.',assistantReceiptDetails:'Request tracking details'});
  Object.assign(words.zh,{assistantPendingTitle:'待确认的请求',assistantPendingSending:'正在提交这条请求…',assistantPendingCancelled:'已停止等待；服务器仍可能处理这条请求。',assistantPendingUnknown:'结果尚不确定；服务器可能已经处理了这条请求。',assistantPendingDisabled:'此服务未提供请求跟踪；这不能说明服务器是否已经处理请求。',assistantPendingReceived:'服务器已收到请求，可能仍在处理中。',assistantPendingSucceeded:'服务器已完成请求，但回复和更新后的上下文没有取回。',assistantPendingFailed:'服务器记录这条请求失败，回复不可用。',assistantPendingInterrupted:'服务器处理中断，回复不可用。',assistantPendingQuestion:'已提交的问题',assistantPendingHelp:'查询回执只读取状态，不会重新发送这条请求。确认后可清空此对话并重新开始。服务器仍可能完成原请求。',assistantPendingCheckUnavailable:'暂时无法查询回执；上次状态未改变。这不表示请求没有被处理。',assistantPendingAcknowledge:'确认并重新开始',assistantPendingRestore:'关闭并恢复问题',assistantPendingRestoreHelp:'服务器记录请求失败或中断。只有输入框为空时才可将原问题恢复为草稿；是否发送仍由你决定。',assistantReceiptDetails:'请求跟踪详情'});
  Object.assign(words.en,{paperEveryday:'OUR EVERYDAY',paperMemories:'memories'});
  Object.assign(words.zh,{paperEveryday:'我们的日常',paperMemories:'回忆'});
  Object.assign(words.en, {autoApprovalHelp:'Automatic approval applies only to future uploads from a member you select here, and only when their phone sends the upload to this library. Existing uploads still need review.',autoApprovalEnable:'Allow automatic approval',autoApprovalDisable:'Require owner review',autoApprovalOn:'Automatic approval is on for future uploads.',autoApprovalOff:'New uploads need owner review.',autoApprovalSavedOn:'Automatic approval enabled for future uploads.',autoApprovalSavedOff:'Future uploads will need owner review.',autoApprovalUncertain:'The setting could not be confirmed. Check the member row before trying again.',autoApprovalConflict:'The member or setting changed. Review the refreshed list before trying again.',autoApprovalUnavailable:'Approval settings are temporarily unavailable.',autoApprovalActionOn:'Allow automatic approval for',autoApprovalActionOff:'Require owner review for'});
  Object.assign(words.zh, {autoApprovalHelp:'自动批准仅适用于你在此选择的成员今后上传的内容，并且对方必须在手机上将上传目标选为此相册库。此前收到的上传仍需主人审核。',autoApprovalEnable:'允许自动批准',autoApprovalDisable:'改为由主人审核',autoApprovalOn:'已为今后的上传开启自动批准。',autoApprovalOff:'新上传仍需主人审核。',autoApprovalSavedOn:'已为今后上传开启自动批准。',autoApprovalSavedOff:'今后的上传将由主人审核。',autoApprovalUncertain:'暂时无法确认此设置，请查看成员行中的当前状态后再操作。',autoApprovalConflict:'成员或设置已更改，请查看刷新后的列表再操作。',autoApprovalUnavailable:'暂时无法读取自动批准设置。',autoApprovalActionOn:'为以下成员允许自动批准：',autoApprovalActionOff:'为以下成员改为由主人审核：'});
  Object.assign(words.en, {familyStories:'Family stories',storyEyebrow:'THE STORY BEHIND THE MOMENT',storyPrivacy:'Shared with this library, not automatically published to TV.',addStory:'Add your memory',storyTitle:'Title (optional)',storyByline:'Written by (display name)',storyLanguage:'Language of your story',otherLanguage:'Other / unspecified',storyText:'What would you like to remember?',storyLimit:'No word-count limit. Up to 64 KiB of text; longer entries are rejected, never shortened.',saveStory:'Save story',savedStory:'Story saved.',storyEmpty:'Every moment has a story. Add yours when you are ready.',storyLoading:'Loading family stories…',storyError:'Stories could not load. Reopen this moment to try again.',editStory:'Edit',history:'History',familyMember:'Family member',you:'You',revision:'Version',moreStories:'More stories',unsavedStory:'Discard your unsaved story?',storyConflict:'This story changed elsewhere. Your draft is still here. Compare the latest version before saving.',compareLatest:'Compare latest version',keepDraft:'Keep my draft as the next version',confirmDraft:'Save your draft over this latest version? Both versions will remain in history.',storySaveError:'Save not confirmed. Your draft is still here; retry the same save before changing it.',storyInvalid:'Nothing was saved. Check the language, title/byline length and the 64 KiB text limit.',deleteStory:'Remove story',confirmDelete:'Remove this story from the library and search? Owner/author history is retained; this is not permanent erasure.',removedStory:'Story removed.',historyTitle:'Story history',restoreDraft:'Use this version as a draft',searchMemories:'Find a memory',searchIn:'Search in',allDescriptions:'Stories and AI descriptions',aiDescriptions:'AI descriptions',aiAndLegacy:'AI descriptions and earlier caption edits',search:'Search',clearSearch:'Show all',matchedFamily:'Found in a family story',matchedAI:'Found in an AI description',matchedLegacy:'Found in an earlier caption edit',noMatches:'No matching memories. Try another word.',draftRecovered:'Your unsaved draft was restored in this tab.',writtenBy:'Written by',unverifiedByline:'Display name supplied by the author'});
  Object.assign(words.zh, {familyStories:'家人的故事',storyEyebrow:'照片背后的故事',storyPrivacy:'与此相册库的成员共享，不会自动发布到电视。',addStory:'写下这段回忆',storyTitle:'标题（可选）',storyByline:'署名（显示名称）',storyLanguage:'故事的语言',otherLanguage:'其他 / 未指定',storyText:'这一刻，有什么值得记住？',storyLimit:'不限制字数。文本最多 64 KiB，超出时明确提示，不会截断。',saveStory:'保存故事',savedStory:'故事已保存。',storyEmpty:'每个瞬间都有故事，准备好时，写下你的回忆。',storyLoading:'正在加载家人的故事…',storyError:'暂时无法加载故事，请重新打开此照片重试。',editStory:'编辑',history:'历史版本',familyMember:'家人',you:'你',revision:'版本',moreStories:'更多故事',unsavedStory:'放弃尚未保存的故事？',storyConflict:'故事已被其他人修改。你的草稿仍在，请先对比最新版本。',compareLatest:'对比最新版本',keepDraft:'将我的草稿作为下一版本',confirmDraft:'确认用你的草稿更新此最新版本？两个版本都会保存在历史记录中。',storySaveError:'尚未确认保存成功。草稿仍在，请先重试同一次保存，再修改内容。',storyInvalid:'未保存。请检查语言、标题和署名长度，以及 64 KiB 文本限制。',deleteStory:'移除故事',confirmDelete:'从相册和搜索中移除此故事？作者和主人仍可查看历史记录，此操作并非永久删除。',removedStory:'故事已移除。',historyTitle:'故事的历史版本',restoreDraft:'将此版本用作草稿',searchMemories:'寻找一段回忆',searchIn:'搜索范围',allDescriptions:'故事与 AI 描述',aiDescriptions:'AI 描述',aiAndLegacy:'AI 描述与早期编辑的描述',search:'搜索',clearSearch:'显示全部',matchedFamily:'来自家人的故事',matchedAI:'来自 AI 描述',matchedLegacy:'来自早期编辑的描述',noMatches:'没有找到匹配的回忆，请换个词试试。',draftRecovered:'已在此标签页恢复未保存的草稿。',writtenBy:'作者',unverifiedByline:'作者自行填写的显示名称'});
  Object.assign(words.en,{storyDeleteError:'Removal not confirmed. Retry Remove story to confirm the same request.',storyCurrent:'Your earlier save was confirmed. A newer version is now shown.'});
  Object.assign(words.zh,{storyDeleteError:'尚未确认移除成功。请再次点击“移除故事”，确认同一次请求。',storyCurrent:'已确认此前的保存。当前显示的是更新的版本。'});
  Object.assign(words.en,{myUploads:'My uploads',myUploadsHelp:'Photos and videos you sent from your phone. Only you can see this history. Refresh to check for an update.',myUploadsEmpty:'No uploads yet. Send photos or videos from the PhotoHouse phone app.',myUploadsUnavailable:'Upload history is unavailable. Please refresh later.',receiptAwaiting:'Received · awaiting owner review',receiptAvailable:'Added to a library',receiptUnavailable:'Currently unavailable',receiptOpen:'Open',receiptHelp:'Approval makes the upload available in its library. Previews and descriptions may take longer.',annotationTitle:'Family notes',annotationScope:'Where should this note appear?',annotationFolder:'This upload · all items',annotationItem:'This item only',annotationScopeHelp:'Choose all items in this upload or only the item shown here.',annotationOriginalHelp:'Your original text or recording stays visible with any transcript or polished suggestion.',annotationTextLabel:'Write a note',annotationLanguage:'Language',annotationConsent:'I agree to local processing for a transcript and suggestions',annotationSave:'Save note',annotationSaving:'Saving…',annotationSaved:'Note saved.',annotationSaveUncertain:'Save could not be confirmed. Your note is kept; retry to confirm the same save.',annotationUnavailable:'Notes are unavailable for this upload.',annotationOriginal:'Original note',annotationTranscript:'Transcript',annotationPolished:'Polished suggestion',annotationEmpty:'No notes yet.',annotationAudio:'Add a WAV recording (up to 2 MiB)',annotationAudioSave:'Save recording',annotationAudioError:'Recording could not be saved. Please check it and retry.',annotationAudioTooLarge:'Choose a WAV file no larger than 2 MiB.',annotationAudioSuccess:'Recording saved.',annotationConsentRequired:'Agree to local processing to save a recording.',annotationConsentShort:'Local processing consent',annotationNoRecordings:'No recording selected.',annotationLanguageEn:'English',annotationLanguageZh:'Chinese',annotationLanguageMixed:'Mixed',annotationLanguageUnknown:'Unknown',annotationTextTooLarge:'Keep the note within 16 KiB of text.'});
  Object.assign(words.zh,{myUploads:'我的上传',myUploadsHelp:'从手机上传的照片和视频。只有你能查看此记录，点击刷新查看最新状态。',myUploadsEmpty:'暂无上传记录。可以从 PhotoHouse 手机应用上传照片或视频。',myUploadsUnavailable:'暂时无法查看上传记录，请稍后刷新。',receiptAwaiting:'已收到 · 等待主人审核',receiptAvailable:'已加入相册库',receiptUnavailable:'当前不可用',receiptOpen:'打开',receiptHelp:'审核通过后可在相册库查看，预览和描述可能需要更长时间。',annotationTitle:'家庭留言',annotationScope:'这条留言显示在哪里？',annotationFolder:'此上传中的所有项目',annotationItem:'仅此项目',annotationScopeHelp:'选择应用于此次上传的所有项目，或仅应用于当前项目。',annotationOriginalHelp:'原始文字或录音会保留，并与转录文本或润色建议一同显示。',annotationTextLabel:'写一条留言',annotationLanguage:'语言',annotationConsent:'我同意在本地处理，以生成转录和建议',annotationSave:'保存留言',annotationSaving:'正在保存…',annotationSaved:'留言已保存。',annotationSaveUncertain:'暂时无法确认保存结果。留言已保留；重试将确认同一次保存。',annotationUnavailable:'暂时无法查看此上传的留言。',annotationOriginal:'原始留言',annotationTranscript:'转录文本',annotationPolished:'润色建议',annotationEmpty:'暂无留言。',annotationAudio:'添加 WAV 录音（最大 2 MiB）',annotationAudioSave:'保存录音',annotationAudioError:'录音未能保存，请检查后重试。',annotationAudioTooLarge:'请选择不超过 2 MiB 的 WAV 文件。',annotationAudioSuccess:'录音已保存。',annotationConsentRequired:'保存录音前请同意本地处理。',annotationConsentShort:'同意本地处理',annotationNoRecordings:'未选择录音。',annotationLanguageEn:'英语',annotationLanguageZh:'中文',annotationLanguageMixed:'中英混合',annotationLanguageUnknown:'未知',annotationTextTooLarge:'留言文字请勿超过 16 KiB。'});
  Object.assign(words.en,{annotationListTitle:'Saved notes',annotationAddTitle:'Add a note'});
  Object.assign(words.zh,{annotationListTitle:'已保存的留言',annotationAddTitle:'添加留言'});
  Object.assign(words.en,{tagReviewTitle:'Review suggested tags',tagReviewHelp:'Review suggestions for uploads already added to this library. The original and polished words stay visible; accepted tags can be found in memory search.',tagReviewEmpty:'No tags are waiting for review in this library.',tagReviewAccept:'Accept tag',tagReviewReject:'Reject tag',tagReviewSuggested:'Suggested tag',tagReviewSaved:'Tag decision saved.',tagReviewConflict:'This suggestion changed. Review the refreshed list.',tagReviewUncertain:'The decision could not be confirmed. Refresh before trying again.',tagReviewUnavailable:'Suggested tags could not load. Try Refresh.'});
  Object.assign(words.zh,{tagReviewTitle:'审核建议标签',tagReviewHelp:'审核已加入此相册库的上传内容所生成的标签建议。原文和润色文字仍可查看；接受的标签可在回忆搜索中找到。',tagReviewEmpty:'此相册库没有待审核的标签。',tagReviewAccept:'接受标签',tagReviewReject:'拒绝标签',tagReviewSuggested:'建议标签',tagReviewSaved:'标签审核结果已保存。',tagReviewConflict:'此建议已更新，请查看刷新的列表。',tagReviewUncertain:'暂时无法确认审核结果，请先刷新再重试。',tagReviewUnavailable:'暂时无法加载建议标签，请点击刷新。'});
  const myUploadsState={page:1,total:0,load:0,busy:false};
  Object.assign(words.en,{annotationRecord:'Record with microphone',annotationStop:'Stop recording',annotationRecording:'Recording… up to 60 seconds',annotationReady:'Recording ready. Save it to this batch or item.',annotationCaptureError:'Microphone recording is unavailable. You can choose a WAV file instead.'});
  Object.assign(words.zh,{annotationRecord:'使用麦克风录音',annotationStop:'结束录音',annotationRecording:'正在录音，最长 60 秒',annotationReady:'录音已就绪，可以保存到此批次或项目。',annotationCaptureError:'无法使用麦克风录音，可以选择 WAV 文件。'});
  Object.assign(words.en,{annotationOriginalAudio:'Original recording',annotationAcceptedTags:'Accepted tags',annotationMore:'More notes',annotationHeld:'Original saved. Local processing was not requested.',annotationQueued:'Original saved. Local processing is pending.',annotationProcessing:'Original saved. Local processing is underway.',annotationDerivationFailed:'Original saved. Local processing did not finish.'});
  Object.assign(words.zh,{annotationOriginalAudio:'原始录音',annotationAcceptedTags:'已接受标签',annotationMore:'更多留言',annotationHeld:'原始内容已保存，未申请本地处理。',annotationQueued:'原始内容已保存，等待本地处理。',annotationProcessing:'原始内容已保存，正在本地处理。',annotationDerivationFailed:'原始内容已保存，本地处理未完成。'});
  Object.assign(words.en,{annotationIntakeClosed:'New family notes are not available yet.',annotationDelete:'Delete note',annotationDeleteConfirm:'Delete this original note or recording and its suggestions from the active library? Existing backups may still contain a copy.',annotationDeleted:'Note deleted.',annotationDeleteError:'Deletion could not be confirmed. Refresh this photo before trying again.'});
  Object.assign(words.zh,{annotationIntakeClosed:'暂时无法添加新的家庭留言。',annotationDelete:'删除留言',annotationDeleteConfirm:'从当前相册库删除这条原始留言或录音及其建议？现有备份中可能仍有副本。',annotationDeleted:'留言已删除。',annotationDeleteError:'暂时无法确认删除结果，请刷新此照片后重试。'});
  const annotationState={pending:new Map(),capture:null};
  const viewerAnnotationState={page:1,total:0,load:0,batch:null};
  function annotationWav(chunks,total,rate){
    const outputRate=16000,frames=Math.min(60*outputRate,Math.floor(total*outputRate/rate));
    if(frames<1)return null;
    const samples=new Float32Array(total);let offset=0;for(const chunk of chunks){samples.set(chunk,offset);offset+=chunk.length;}
    const wav=new ArrayBuffer(44+frames*2),view=new DataView(wav);const label=(at,value)=>{for(let i=0;i<value.length;i++)view.setUint8(at+i,value.charCodeAt(i));};
    label(0,'RIFF');view.setUint32(4,36+frames*2,true);label(8,'WAVE');label(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,outputRate,true);view.setUint32(28,outputRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);label(36,'data');view.setUint32(40,frames*2,true);
    for(let i=0;i<frames;i++){const position=i*rate/outputRate,left=Math.floor(position),fraction=position-left;const value=Math.max(-1,Math.min(1,(samples[left]||0)*(1-fraction)+(samples[Math.min(left+1,total-1)]||0)*fraction));view.setInt16(44+i*2,value<0?value*32768:value*32767,true);}
    try{return new File([wav],'photohouse-memory.wav',{type:'audio/wav'});}
    finally{samples.fill(0);new Uint8Array(wav).fill(0);}
  }
  async function annotationCapture(onReady,maxSeconds=60){
    if(!navigator.mediaDevices?.getUserMedia)throw new Error('Microphone unavailable');
    const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
    let context;try{const AudioContextType=window.AudioContext||window.webkitAudioContext;context=new AudioContextType();const source=context.createMediaStreamSource(stream),processor=context.createScriptProcessor(4096,1,1),chunks=[];let total=0,stopped=false;
      const capture={stop:async keep=>{if(stopped)return;stopped=true;processor.onaudioprocess=null;source.disconnect();processor.disconnect();stream.getTracks().forEach(track=>track.stop());void context.close();if(annotationState.capture===capture)annotationState.capture=null;try{if(keep){const file=annotationWav(chunks,total,context.sampleRate);onReady(file);return file;}return null;}finally{for(const chunk of chunks)chunk.fill(0);chunks.length=0;total=0;}}};
      processor.onaudioprocess=event=>{if(stopped)return;const limit=Math.ceil(context.sampleRate*maxSeconds),remaining=limit-total;if(remaining<=0){void capture.stop(true);return;}const input=event.inputBuffer.getChannelData(0);chunks.push(new Float32Array(input.subarray(0,remaining)));total+=Math.min(input.length,remaining);if(total>=limit)void capture.stop(true);};
      source.connect(processor);processor.connect(context.destination);await context.resume();return capture;
    }catch(error){stream.getTracks().forEach(track=>track.stop());if(context)void context.close();throw error;}
  }
  function clearMyUploads(){
    if(annotationState.capture)void annotationState.capture.stop(false);
    $('my-uploads-list').querySelector('.annotation-dialog[open]')?.close();
    myUploadsState.load++;myUploadsState.page=1;myUploadsState.total=0;myUploadsState.busy=false;
    $('my-uploads-panel').open=false;$('my-uploads-list').replaceChildren();$('my-uploads-status').textContent='';$('my-uploads-pages').hidden=true;$('my-uploads-refresh').disabled=false;annotationState.pending.clear();
  }
  function receiptPageValid(data,page){
    const keys=(value,names)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')===names.split(',').sort().join(',');
    if(!keys(data,'page,page_size,total,items')||data.page!==page||data.page_size!==10||!Number.isInteger(data.total)||data.total<0||data.total>2147483647||!Array.isArray(data.items)||data.items.length!==Math.min(10,Math.max(0,data.total-(page-1)*10)))return false;
    const ids=new Set();return data.items.every(item=>{
      if(!keys(item,'asset_id,created_at,bytes,kind,state,library_id')||typeof item.asset_id!=='string'||!/^[1-9][0-9]{0,18}$/.test(item.asset_id)||BigInt(item.asset_id)>9223372036854775807n||ids.has(item.asset_id)||!['image','video'].includes(item.kind)||!Number.isInteger(item.created_at)||item.created_at<0||item.created_at>253402300799||!Number.isInteger(item.bytes)||item.bytes<1||item.bytes>(item.kind==='video'?17179869184:268435456))return false;
      ids.add(item.asset_id);return item.state==='available'?typeof item.library_id==='string'&&item.library_id.trim().length>0&&[...item.library_id].length<=128&&!/[\x00-\x1f\x7f]/.test(item.library_id)&&!['.','..'].includes(item.library_id):['awaiting_review','unavailable'].includes(item.state)&&item.library_id===null;
    });
  }
  const annotationLanguages=['en','zh','mixed','und'];
  function annotationNotesValid(data,item,page=1){
    if(!data||data.library_id!==item.library_id||data.asset_id!==item.asset_id||typeof data.batch!=='string'||!/^[0-9a-f]{32}$/.test(data.batch)||data.page!==page||data.page_size!==20||!Number.isInteger(data.total)||data.total<0||!Array.isArray(data.items)||data.items.length>20)return false;
    return data.items.every(note=>note&&typeof note.id==='string'&&/^[0-9a-f-]{36}$/.test(note.id)&&note.library_id===item.library_id&&note.batch===data.batch&&['text','audio'].includes(note.kind)&&['folder','item'].includes(note.scope)&&(note.scope==='folder'?note.asset_id===null:note.asset_id===item.asset_id)&&typeof note.created_at==='number'&&note.derivation!==null&&typeof note.derivation==='object');
  }
  function annotationMutationKey(batch,asset){return `${batch}\u0000${asset}`;}
  function addAnnotationText(host,value){const p=document.createElement('p');p.className='annotation-text';p.textContent=typeof value==='string'&&value?value:'—';host.append(p);}
  function renderAnnotationNote(list,note,selectedAsset){
    const entry=document.createElement('article');entry.className='annotation-note';
    const heading=document.createElement('h4');heading.textContent=`${t(note.kind==='audio'?'annotationOriginalAudio':'annotationOriginal')} · ${note.scope==='folder'?t('annotationFolder'):t('annotationItem')}`;entry.append(heading);
    if(note.kind==='text'){addAnnotationText(entry,note.original_text);}
    else if(typeof note.audio_url==='string'){const url=new URL(note.audio_url,location.origin);if(url.origin===location.origin&&url.pathname===`/upload-annotations/${note.id}/audio`&&url.searchParams.get('library')===state.library&&url.searchParams.get('asset_id')===selectedAsset){const player=document.createElement('audio');player.controls=true;player.preload='none';player.src=url.pathname+url.search;player.setAttribute('aria-label',t('annotationOriginalAudio'));entry.append(player);}}
    if(note.derivation){const d=note.derivation;if(d.transcript){const label=document.createElement('strong');label.textContent=t('annotationTranscript');entry.append(label);addAnnotationText(entry,d.transcript);}if(d.polished_text){const label=document.createElement('strong');label.textContent=t('annotationPolished');entry.append(label);addAnnotationText(entry,d.polished_text);}}
    if(note.derivation&&note.derivation.state!=='completed'){const stateLabel={held:'annotationHeld',waiting:'annotationQueued',running:'annotationProcessing',failed:'annotationDerivationFailed',dead:'annotationDerivationFailed'}[note.derivation.state];if(stateLabel){const status=document.createElement('p');status.className='fine';status.textContent=t(stateLabel);entry.append(status);}}
    const accepted=Array.isArray(note.tags)?note.tags.filter(tag=>tag&&tag.status==='accepted'&&typeof tag.tag==='string').map(tag=>tag.tag):[];
    if(accepted.length){const labels=document.createElement('p');labels.className='fine';labels.textContent=`${t('annotationAcceptedTags')}: ${accepted.join(' · ')}`;entry.append(labels);}
    if(state.profile?.memberships?.some(member=>member.library_id===state.library&&member.available&&member.role==='owner')&&/^[0-9a-f]{64}$/.test(note.sha256||'')){
      const remove=document.createElement('button');remove.type='button';remove.className='quiet';remove.textContent=t('annotationDelete');
      remove.addEventListener('click',async()=>{if(!window.confirm(t('annotationDeleteConfirm')))return;remove.disabled=true;try{
        const result=await request(`/admin/upload-annotations/delete?library=${encodeURIComponent(state.library)}`,{method:'POST',body:{asset_id:selectedAsset,annotation_id:note.id,sha256:note.sha256},epoch:state.generation});
        if(result.annotation_id!==note.id||result.deleted!==true)throw new Error('Invalid deletion receipt');
        entry.remove();if($('viewer').open&&String(storyState.asset?.id)===selectedAsset)void loadViewerAnnotations();
      }catch(error){if(error.name!=='AbortError')window.alert(t('annotationDeleteError'));}finally{remove.disabled=false;}});
      entry.append(remove);
    }
    list.append(entry);
  }
  function annotationComposer(host,item,batch,epoch,account){
    const box=document.createElement('section');box.className='annotation-composer';
    const heading=document.createElement('h4');heading.textContent=t('annotationAddTitle');box.append(heading);
    const scopeLabel=document.createElement('label');scopeLabel.textContent=t('annotationScope');
    const selector=document.createElement('select');selector.setAttribute('aria-describedby',`annotation-scope-help-${item.asset_id}`);
    for(const [value,key] of [['', 'annotationFolder'],[item.asset_id,'annotationItem']]){const option=document.createElement('option');option.value=value;option.textContent=t(key);selector.append(option);}
    scopeLabel.append(selector);box.append(scopeLabel);
    const scopeHelp=document.createElement('p');scopeHelp.className='fine annotation-help';scopeHelp.id=`annotation-scope-help-${item.asset_id}`;scopeHelp.textContent=t('annotationScopeHelp');box.append(scopeHelp);
    const originalHelp=document.createElement('p');originalHelp.className='fine annotation-help annotation-original-help';originalHelp.textContent=t('annotationOriginalHelp');box.append(originalHelp);
    const languageLabel=document.createElement('label');languageLabel.textContent=t('annotationLanguage');const language=document.createElement('select');
    for(const value of annotationLanguages){const option=document.createElement('option');option.value=value;option.textContent=t(({en:'annotationLanguageEn',zh:'annotationLanguageZh',mixed:'annotationLanguageMixed',und:'annotationLanguageUnknown'})[value]);language.append(option);}languageLabel.append(language);box.append(languageLabel);
    const consentLabel=document.createElement('label');const consent=document.createElement('input');consent.type='checkbox';consentLabel.append(consent,document.createTextNode(` ${t('annotationConsent')}`));box.append(consentLabel);
    const textLabel=document.createElement('label');textLabel.textContent=t('annotationTextLabel');const textarea=document.createElement('textarea');textarea.maxLength=16384;textarea.rows=3;textLabel.append(textarea);box.append(textLabel);
    const status=document.createElement('p');status.className='annotation-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');box.append(status);
    const save=document.createElement('button');save.type='button';save.className='quiet';save.textContent=t('annotationSave');box.append(save);
    const audioLabel=document.createElement('label');audioLabel.textContent=t('annotationAudio');const file=document.createElement('input');file.type='file';file.accept='.wav,audio/wav,audio/x-wav';audioLabel.append(file);box.append(audioLabel);
    let capturedRecording=null,captureStarting=false;
    const record=document.createElement('button');record.type='button';record.className='quiet';record.textContent=t('annotationRecord');box.append(record);
    const stop=document.createElement('button');stop.type='button';stop.className='quiet';stop.textContent=t('annotationStop');stop.hidden=true;box.append(stop);
    const audioSave=document.createElement('button');audioSave.type='button';audioSave.className='quiet';audioSave.textContent=t('annotationAudioSave');box.append(audioSave);
    const current=()=>!stale(epoch)&&state.profile?.account_id===account&&state.library===item.library_id&&$('my-uploads-panel').open&&host.closest('dialog')?.open;
    record.addEventListener('click',async()=>{if(!current()||captureStarting||annotationState.capture)return;captureStarting=true;record.disabled=true;try{const capture=await annotationCapture(recording=>{if(!current())return;capturedRecording=recording;file.value='';status.textContent=t('annotationReady');stop.hidden=true;record.disabled=false;});if(!current()){void capture.stop(false);return;}annotationState.capture=capture;stop.hidden=false;status.textContent=t('annotationRecording');}catch(error){if(current())status.textContent=t('annotationCaptureError');}finally{captureStarting=false;if(current()&&!annotationState.capture)record.disabled=false;}});
    stop.addEventListener('click',()=>{if(!current()||!annotationState.capture)return;void annotationState.capture.stop(true);});
    const mutationFor=()=>{const target=selector.value,key=annotationMutationKey(batch,target),old=annotationState.pending.get(key);if(old&&old.text===textarea.value&&old.language===language.value&&old.consent===(consent.checked?'yes':'no'))return old;const next={id:crypto.randomUUID(),text:textarea.value,language:language.value,consent:consent.checked?'yes':'no'};annotationState.pending.set(key,next);return next;};
    save.addEventListener('click',async()=>{if(!current()||!textarea.value.trim())return;if(new TextEncoder().encode(textarea.value).length>16384){status.textContent=t('annotationTextTooLarge');return;}const pending=mutationFor();save.disabled=true;status.textContent=t('annotationSaving');try{const result=await request(`/upload-annotations/text?library=${encodeURIComponent(item.library_id)}`,{method:'POST',body:{batch,asset_id:selector.value,language:pending.language,consent:pending.consent,mutation_id:pending.id,text:pending.text},epoch});if(!current())return;if(!annotationNotesValid({library_id:item.library_id,asset_id:item.asset_id,batch,page:1,page_size:20,total:1,items:[result]},item)||result.kind!=='text'||result.original_text!==pending.text||result.asset_id!==(selector.value||null))throw new Error('Invalid note receipt');const notes=host.querySelector('.annotation-notes');if(notes){notes.querySelector('.annotation-empty')?.remove();renderAnnotationNote(notes,result,item.asset_id);}textarea.value='';annotationState.pending.delete(annotationMutationKey(batch,selector.value));status.textContent=t('annotationSaved');}catch(error){if(!current()||error.name==='AbortError')return;status.textContent=t('annotationSaveUncertain');}finally{if(current())save.disabled=false;}});
    audioSave.addEventListener('click',async()=>{if(!current()||annotationState.capture)return;const recording=file.files?.[0]||capturedRecording;if(!recording){status.textContent=t('annotationNoRecordings');return;}if(!/\.wav$/i.test(recording.name)||recording.size>2*1024*1024){status.textContent=t('annotationAudioTooLarge');return;}const key=`audio:${annotationMutationKey(batch,selector.value)}`,old=annotationState.pending.get(key),choice=consent.checked?'yes':'no';const pending=old&&old.file===recording&&old.language===language.value&&old.consent===choice?old:{id:crypto.randomUUID(),file:recording,language:language.value,consent:choice};annotationState.pending.set(key,pending);audioSave.disabled=true;status.textContent=t('annotationSaving');const controller=new AbortController();state.controllers.add(controller);try{const headers={'Content-Type':'audio/wav','X-Annotation-Batch':batch,'X-Annotation-Language':pending.language,'X-Local-Processing-Consent':pending.consent,'X-Annotation-Mutation-Id':pending.id};if(selector.value)headers['X-Annotation-Asset-Id']=selector.value;if(state.csrf)headers['X-CSRF-Token']=state.csrf;const response=await fetch(`/upload-annotations/audio?library=${encodeURIComponent(item.library_id)}`,{method:'POST',headers,body:recording,credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});if(!current())return;if(!response.ok)throw new Error('Recording save failed');const result=await response.json();if(!current())return;if(!annotationNotesValid({library_id:item.library_id,asset_id:item.asset_id,batch,page:1,page_size:20,total:1,items:[result]},item)||result.kind!=='audio'||result.asset_id!==(selector.value||null))throw new Error('Invalid recording receipt');const notes=host.querySelector('.annotation-notes');if(notes){notes.querySelector('.annotation-empty')?.remove();renderAnnotationNote(notes,result,item.asset_id);}file.value='';capturedRecording=null;annotationState.pending.delete(key);status.textContent=t('annotationAudioSuccess');}catch(error){if(!current()||error.name==='AbortError')return;status.textContent=t('annotationAudioError');}finally{state.controllers.delete(controller);if(current())audioSave.disabled=false;}});
    host.append(box);return box;
  }
  async function loadAnnotations(host,item,epoch,account,current){
    const section=document.createElement('section');section.className='annotation-list';const heading=document.createElement('h4');heading.textContent=t('annotationListTitle');const notes=document.createElement('div');notes.className='annotation-notes';section.append(heading,notes);host.append(section);
    try{const data=await request(`/upload-annotations?library=${encodeURIComponent(item.library_id)}&asset_id=${encodeURIComponent(item.asset_id)}`,{epoch});if(!current())return;if(!annotationNotesValid(data,item))throw new Error('Invalid annotations');
      for(const note of data.items)renderAnnotationNote(notes,note,item.asset_id);
      if(!notes.childElementCount){const empty=document.createElement('p');empty.className='fine annotation-empty';empty.textContent=t('annotationEmpty');notes.append(empty);}
      if(data.intake_enabled===true)annotationComposer(host,item,data.batch,epoch,account);
      else{const unavailable=document.createElement('p');unavailable.className='fine';unavailable.textContent=t('annotationIntakeClosed');host.append(unavailable);}
    }catch(error){if(!current())return;section.remove();const unavailable=document.createElement('p');unavailable.className='fine';unavailable.textContent=t('annotationUnavailable');host.append(unavailable);}
  }
  function attachAnnotationDialog(card,item,epoch,account){
    const open=document.createElement('button');open.type='button';open.className='annotation-open quiet';open.textContent=t('annotationTitle');
    const dialog=document.createElement('dialog');dialog.className='annotation-dialog';
    const header=document.createElement('div');header.className='annotation-dialog-heading';
    const title=document.createElement('h3');title.id=`annotation-dialog-title-${item.asset_id}`;title.textContent=`${t('annotationTitle')} · ${t(item.kind==='image'?'photo':'video')} ${item.asset_id}`;dialog.setAttribute('aria-labelledby',title.id);
    const close=document.createElement('button');close.type='button';close.className='quiet';close.textContent=t('close');close.addEventListener('click',()=>dialog.close());
    const content=document.createElement('div');content.className='annotation-dialog-content';header.append(title,close);dialog.append(header,content);card.append(open,dialog);
    let load=0;
    open.addEventListener('click',()=>{
      if(stale(epoch)||account!==state.profile?.account_id||state.library!==item.library_id)return;
      dialog.showModal();const currentLoad=++load;content.replaceChildren();
      const current=()=>dialog.open&&load===currentLoad&&!stale(epoch)&&account===state.profile?.account_id&&state.library===item.library_id;
      void loadAnnotations(content,item,epoch,account,current);
    });
    dialog.addEventListener('close',()=>{load++;if(annotationState.capture)void annotationState.capture.stop(false);content.replaceChildren();});
  }
  async function loadViewerAnnotations(append=false){
    const asset=storyState.asset;if(!asset||!$('viewer').open)return;
    const epoch=state.generation,viewer=state.viewerGeneration,library=state.library;
    const selected={library_id:library,asset_id:String(asset.id)};
    const page=append?viewerAnnotationState.page+1:1,load=++viewerAnnotationState.load;
    const current=()=>!stale(epoch)&&viewer===state.viewerGeneration&&load===viewerAnnotationState.load&&library===state.library&&$('viewer').open;
    const section=$('viewer-annotations'),list=$('viewer-annotations-list'),more=$('viewer-annotations-more');
    more.disabled=true;
    if(!append){viewerAnnotationState.page=1;viewerAnnotationState.total=0;viewerAnnotationState.batch=null;list.replaceChildren();section.hidden=true;}
    try{
      const data=await request(`/upload-annotations?library=${encodeURIComponent(library)}&asset_id=${encodeURIComponent(selected.asset_id)}&page=${page}`,{epoch});
      if(!current())return;
      if(!annotationNotesValid(data,selected,page)||(append&&data.batch!==viewerAnnotationState.batch))throw new Error('Invalid annotations');
      viewerAnnotationState.page=page;viewerAnnotationState.total=data.total;viewerAnnotationState.batch=data.batch;
      if(data.total){section.hidden=false;for(const note of data.items)renderAnnotationNote(list,note,selected.asset_id);}
      $('viewer-annotations-status').textContent='';more.hidden=page*20>=data.total;
    }catch(error){
      if(!current()||error.name==='AbortError')return;
      if(error.status===401){section.hidden=true;more.hidden=true;return;}
      if(!append)section.hidden=false;
      $('viewer-annotations-status').textContent=t('annotationUnavailable');
    }finally{if(current())more.disabled=false;}
  }
  async function loadMyUploads(){
    if(state.locked||!state.profile||!$('my-uploads-panel').open)return;
    const epoch=state.generation,account=state.profile.account_id,load=++myUploadsState.load,page=myUploadsState.page;
    const current=()=>!stale(epoch)&&account===state.profile?.account_id&&load===myUploadsState.load&&$('my-uploads-panel').open;
    myUploadsState.busy=true;$('my-uploads-refresh').disabled=true;$('my-uploads-list').querySelector('.annotation-dialog[open]')?.close();$('my-uploads-list').replaceChildren();$('my-uploads-pages').hidden=true;$('my-uploads-status').textContent=t('loading');
    try{
      const data=await request(`/uploads?page=${page}`,{epoch});if(!current())return;
      if(!receiptPageValid(data,page))throw new Error('Invalid upload history');
      myUploadsState.total=data.total;
      for(const item of data.items){
        const card=document.createElement('article');card.className='receipt-card';card.dataset.asset=item.asset_id;
        const title=document.createElement('h3');title.textContent=`${t(item.kind==='image'?'photo':'video')} ${item.asset_id}`;
        const meta=document.createElement('p');meta.className='fine';meta.textContent=`${new Date(item.created_at*1000).toLocaleString(state.language==='zh'?'zh-CN':'en')} · ${(item.bytes/1024).toFixed(1)} KiB`;
        const label=document.createElement('p');label.className='receipt-state';label.textContent=t(item.state==='available'?'receiptAvailable':item.state==='awaiting_review'?'receiptAwaiting':'receiptUnavailable');card.append(title,meta,label);
        if(item.state==='available'&&availableLibraries(state.profile).some(m=>m.library_id===item.library_id)){
          const button=document.createElement('button');button.type='button';button.className='quiet';button.textContent=t('receiptOpen');button.addEventListener('click',async()=>{
            if(!current()||state.busy||!abandonStory())return;
            button.disabled=true;state.library=item.library_id;state.page=1;
            const openingEpoch=state.generation+1;await restore(false);
            if(stale(openingEpoch)||state.locked||state.profile?.account_id!==account||state.library!==item.library_id)return;
            const gallery=loadGallery(),galleryEpoch=state.generation;await gallery;
            if(stale(galleryEpoch)||state.locked||state.profile?.account_id!==account||state.library!==item.library_id)return;
            await openAsset({id:item.asset_id,kind:item.kind});
          });card.append(button);
        }
        if(state.library&&((item.state==='available'&&state.library===item.library_id)||item.state==='awaiting_review'))
          attachAnnotationDialog(card,{...item,library_id:state.library},epoch,account);
        $('my-uploads-list').append(card);
      }
      $('my-uploads-status').textContent=t(data.total?'receiptHelp':'myUploadsEmpty');$('my-uploads-pages').hidden=data.total===0;
      $('my-uploads-page-label').textContent=`${t('page')} ${page} ${t('of')} ${Math.max(1,Math.ceil(data.total/10))}`;
      $('my-uploads-previous').disabled=page<=1;$('my-uploads-next').disabled=page*10>=data.total;
    }catch(error){if(!current()||error.name==='AbortError')return;$('my-uploads-list').replaceChildren();$('my-uploads-status').textContent=t('myUploadsUnavailable');if(error.status===401)await failure(error,epoch);}
    finally{if(current()){myUploadsState.busy=false;$('my-uploads-refresh').disabled=false;}}
  }
  const storyState={asset:null,editing:null,dirty:false,busy:false,page:1,load:0,loading:false,history:0,deletes:new Map(),pending:null,search:null,suspended:null};
  const peopleState={page:1,total:0,load:0,query:'',named:'all'};
  const directoryState={page:1,total:0,load:0,query:'',person:null,assetLoad:0,assetPage:1,assetTotal:0};
  Object.assign(words.en,{familyTagsTitle:'Family note tags',familyTagsHelp:'Labels suggested from family notes and accepted by the library owner. Only photos in this library appear here.',findFamilyTag:'Find a family tag',familyTagsEmpty:'No accepted family note tags in this library yet.',familyTagAssets:'Photos with this family tag',clearFamilyTag:'Close'});
  Object.assign(words.zh,{familyTagsTitle:'家庭留言标签',familyTagsHelp:'从家庭留言生成、经相册库主人接受的标签。这里只显示此相册库的照片。',findFamilyTag:'查找家庭标签',familyTagsEmpty:'此相册库还没有已接受的家庭留言标签。',familyTagAssets:'带有此家庭标签的照片',clearFamilyTag:'关闭'});
  Object.assign(words.en,{allDescriptions:'Stories, accepted tags and AI descriptions',familySearchSources:'Family entries',matchedFamily:'Found in family content'});
  Object.assign(words.zh,{allDescriptions:'故事、已接受标签与 AI 描述',familySearchSources:'家人提供的内容',matchedFamily:'来自家人的内容'});
  const tagState={page:1,total:0,load:0,query:'',tag:null,tagLoad:0,tagPage:1,tagTotal:0,open:null};
  const familyTagState={page:1,total:0,load:0,query:'',tag:null,tagLoad:0,assetPage:1,assetTotal:0};
  const duplicateState={page:1,total:0,load:0};
  // Date/media narrowing. `binding` is issued by the facets route and must be echoed to
  // the search route; `fingerprint` chains a later page to the exact filter it paginates.
  const discoveryState={binding:null,owner:null,active:false,modeToken:0,page:1,total:0,facetLoad:0,searchLoad:0,fingerprint:null,applied:false,appliedFilters:null,appliedLocationLabels:new Map(),placePage:1,placeTotal:0,places:[],selectedPlaces:new Set(),selectedPlaceLabels:new Map(),placeQuery:'',placesAvailable:false};
  let galleryLoad=0;
  const unassignedState={page:1,total:0,load:0};
  const faceState={page:1,total:0,load:0};
  const albumState={page:1,total:0,load:0,draft:null,archivedLoad:0};
  const photoState={image:null,surface:null,mode:'fit',scale:1,drag:null};
  const sequenceState={items:[],index:0,origin:'single',playing:false,timer:null,busy:false};
  const transferState={selected:new Map(),source:null,destinations:[],review:null,busy:false,load:0,canMove:null};
  Object.assign(words.en,{viewPrevious:'Previous photo',viewNext:'Next photo',viewPlay:'Play slideshow',viewPause:'Pause slideshow',viewInterval:'Each preview',viewPage:'This page',viewAlbum:'This album',viewSequenceHelp:'Slideshow uses these previews only; videos are shown as still previews.'});
  Object.assign(words.zh,{viewPrevious:'上一张',viewNext:'下一张',viewPlay:'播放幻灯片',viewPause:'暂停幻灯片',viewInterval:'每张预览',viewPage:'当前页',viewAlbum:'当前相册',viewSequenceHelp:'幻灯片仅播放此组预览，视频显示为静态预览。'});
  Object.assign(words.en,{viewEditing:'Close the story editor or face review before playing a slideshow.'});
  Object.assign(words.zh,{viewEditing:'请先关闭故事编辑或人脸核对面板，再播放幻灯片。'});
  Object.assign(words.en,{viewFit:'Fit',viewWidth:'Fit width',viewHeight:'Fit height',viewActual:'Actual size',viewOut:'Zoom out',viewIn:'Zoom in',viewFullscreen:'Fullscreen',viewExitFullscreen:'Exit fullscreen',viewFullscreenFailed:'Fullscreen is unavailable in this browser.',viewHelp:'Scroll to zoom; drag to pan. Keyboard: + / − zoom, arrows pan, 0 fits.',viewQuality:'Thumbnail preview. Actual size means preview pixels, not the original photo.',assignmentRestricted:'This saved person cannot be assigned yet: their library ownership needs review. No changes were made.',assignmentChooseHelp:'Select a person, then review the face and press Confirm assignment.'});
  Object.assign(words.zh,{viewFit:'适合窗口',viewWidth:'适合宽度',viewHeight:'适合高度',viewActual:'实际大小',viewOut:'缩小',viewIn:'放大',viewFullscreen:'全屏',viewExitFullscreen:'退出全屏',viewFullscreenFailed:'此浏览器暂不支持全屏。',viewHelp:'滚轮缩放，拖动平移。键盘：+ / − 缩放，方向键平移，0 适合窗口。',viewQuality:'当前为缩略预览。“实际大小”指预览图像素，并非原始照片。',assignmentRestricted:'此人物暂不能分配：需先确认其家庭库归属。未作任何更改。',assignmentChooseHelp:'选择人物后，请核对人脸并点击“确认归属”。'});
  Object.assign(words.en,{preparedPlayback:'Prepared video',videoChecking:'Checking protected video…',videoUnavailable:'This prepared video is unavailable.',videoNotPrepared:'This video is not prepared yet.',videoChanged:'This video changed. Close it and refresh the library.',videoBusy:'The prepared video is busy. Wait before retrying.',videoRetry:'Retry video',videoRetryLater:'Retry later',videoUnauthorized:'Your access changed. The video was closed.',videoInterrupted:'Playback was interrupted. Retry the video.'});
  Object.assign(words.zh,{preparedPlayback:'已准备的视频',videoChecking:'正在检查受保护的视频…',videoUnavailable:'此准备好的视频暂不可用。',videoNotPrepared:'此视频尚未准备好。',videoChanged:'此视频已发生变化。请关闭后刷新相册库。',videoBusy:'准备好的视频当前繁忙，请稍后再试。',videoRetry:'重试视频',videoRetryLater:'稍后重试',videoUnauthorized:'访问权限已变化，视频已关闭。',videoInterrupted:'播放已中断，请重试视频。'});
  Object.assign(words.en,{newPerson:'Create a new person',createAssign:'Create and assign',unassignFace:'Remove this assignment',confirmUnassign:'Remove this face assignment? The saved person and photo will be kept.',albums:'Family albums',albumPrivacy:'Saved in this library, not automatically published to TV.',newAlbum:'Create album',editAlbum:'Edit album',albumTitle:'Album title',albumTitleZh:'Chinese title (optional)',albumDescription:'Description',albumTheme:'Theme',saveAlbum:'Save album',albumSaved:'Album saved.',noAlbums:'No library-owned albums yet. Earlier unowned albums need a reviewed import.',selectPhotos:'Choose photos/videos (up to 60)',selectedPhotos:'Selected order',moveUp:'Move earlier',moveDown:'Move later',remove:'Remove',setCover:'Use as cover',cover:'Cover',albumEmpty:'Empty album',albumChanged:'Album changed. Close this editor and reopen the current version before editing.',albumUncertain:'Save not confirmed. Retry this same save or close and review the saved albums.',discardAlbum:'Discard this unsaved album edit?',albumNeedsReview:'Some earlier selections are no longer available. Saving will remove unavailable entries.',newPersonHelp:'Use an existing saved person when possible. Creating a name does not merge duplicates.'});
  Object.assign(words.zh,{newPerson:'创建新人物',createAssign:'创建并分配',unassignFace:'取消此人脸归属',confirmUnassign:'取消此人脸归属？已保存的人物和照片将保留。',albums:'家庭主题相册',albumPrivacy:'保存在本家庭库，不会自动发布到电视。',newAlbum:'创建相册',editAlbum:'编辑相册',albumTitle:'相册标题',albumTitleZh:'中文标题（可选）',albumDescription:'描述',albumTheme:'主题',saveAlbum:'保存相册',albumSaved:'相册已保存。',noAlbums:'暂无属于本库的相册。旧的未归属相册需经确认后导入。',selectPhotos:'选择照片或视频（最多 60 项）',selectedPhotos:'已选顺序',moveUp:'向前移动',moveDown:'向后移动',remove:'移除',setCover:'设为封面',cover:'封面',albumEmpty:'空相册',albumChanged:'相册已更改，请关闭编辑器并打开最新版本后再编辑。',albumUncertain:'尚未确认保存成功。请重试同一次保存，或关闭并核对已保存相册。',discardAlbum:'放弃尚未保存的相册修改？',albumNeedsReview:'部分原选项已不可访问，保存将移除这些选项。',newPersonHelp:'请优先选择已有的人物。创建姓名不会自动合并重名人物。'});
  Object.assign(words.en,{moveMemories:'Move memories',moveMemoriesHelp:'Move up to 50 photos or videos to another family library. Stories move with them.',moveSelected:'Move selected',clearSelection:'Clear selection',moveThisMemory:'Move this memory',reviewMove:'Review move',confirmMove:'Confirm move',chooseDestination:'Choose a destination',sourceLibrary:'From',destinationLibrary:'To',moveSummary:'Move summary',moveStories:'Stories move with these memories.',moveAlbums:'Album links stay hidden in the source library.',moveFaces:'People names from the source library are not shared with the destination.',moveReaders:'Only members of the destination library can access the moved items. Existing TV publications are managed separately.',readersCount:'destination members',originalReadersCount:'with original downloads',moveSuccess:'Memories moved. This library has been refreshed.',moveRefreshFailed:'The move was completed. Refresh to see the latest library.',moveUncertain:'Move not confirmed. Retry this confirmation to check its result.',moveLimit:'Choose up to 50 memories.',moveNone:'Choose at least one memory.',moveUnavailable:'Moving is not available for this library.',moveFailed:'The move could not be completed. Refresh and try again.',assetsCount:'memories',storiesCount:'stories',albumsCount:'album links',facesCount:'saved faces'});
  Object.assign(words.zh,{moveMemories:'移动回忆',moveMemoriesHelp:'最多将 50 张照片或视频移动到另一个家庭相册库，故事也会一起移动。',moveSelected:'移动所选内容',clearSelection:'清除选择',moveThisMemory:'移动这段回忆',reviewMove:'确认移动',confirmMove:'确认移动',chooseDestination:'选择目标相册库',sourceLibrary:'来源',destinationLibrary:'目标',moveSummary:'移动内容',moveStories:'这些回忆里的故事会一起移动。',moveAlbums:'来源相册库中的相册关联会保留为隐藏状态。',moveFaces:'来源库中的人物姓名不会共享到目标库。',moveReaders:'移动后，仅目标库成员可访问这些内容。已发布到电视的内容需单独管理。',readersCount:'位目标库成员',originalReadersCount:'位可下载原文件',moveSuccess:'回忆已移动，当前相册库已刷新。',moveRefreshFailed:'移动已完成，请刷新以查看最新相册库。',moveUncertain:'尚未确认移动结果。请重试此次确认以核对结果。',moveLimit:'最多选择 50 段回忆。',moveNone:'请至少选择一段回忆。',moveUnavailable:'此相册库暂时不能移动回忆。',moveFailed:'移动未完成，请刷新后重试。',assetsCount:'段回忆',storiesCount:'个故事',albumsCount:'个相册关联',facesCount:'张已保存人脸'});
  Object.assign(words.en,{closeSelection:'Close selection'});
  Object.assign(words.zh,{closeSelection:'关闭选择面板'});
  Object.assign(words.en,{assignFaces:'Review face assignments · Owner',assignHelp:'Choose an existing person for one face. No automatic propagation or new person is created.',unassigned:'Unassigned',choosePerson:'Choose a person',confirmAssignment:'Confirm assignment',assignmentReview:'Assign this face to',assignmentSaved:'Assignment saved. Other faces were not changed.',assignmentConflict:'The face or person changed, or face processing is active. Refresh and review before trying again.',assignmentFailed:'Save not confirmed. Refresh and review this face before trying again.',assignmentUnavailable:'This assignment needs a separate ownership review.',noFaces:'No detected faces on this asset.',selectPerson:'Select this person'});
  Object.assign(words.zh,{assignFaces:'查看人脸归属 · 主人',assignHelp:'为一张人脸选择已保存的人物。不会自动传播标签或创建新人物。',unassigned:'未分配',choosePerson:'选择人物',confirmAssignment:'确认归属',assignmentReview:'将这张人脸分配给',assignmentSaved:'已保存归属，其他人脸未更改。',assignmentConflict:'人脸或人物已更改，或人脸处理正在进行。请刷新并重新确认。',assignmentFailed:'尚未确认保存成功，请刷新并核对此人脸后再试。',assignmentUnavailable:'此归属需要另行确认权限。',noFaces:'此照片暂无已检测的人脸。',selectPerson:'选择此人'});
  Object.assign(words.en,{managePeople:'Manage people · Owner',peopleHelp:'Review saved names and faces in this library. Renaming does not merge people or change face assignments.',findPerson:'Find a saved name',peopleEmpty:'No matching saved names. Unassigned faces and names not linked to this library are not included yet.',personName:'Display name',unnamedPerson:'Unnamed person',reviewFaces:'Review faces',saveName:'Save name',nameSaved:'Name saved.',nameConflict:'This person changed. Review the refreshed record before editing again.',nameUnavailable:'Name editing needs a separate ownership review for this record.',facesCount:'faces in this library',moreFaces:'More faces',nameShortened:'Long existing name: preview shortened.',nameSaveFailed:'Save not confirmed. Refresh the record before trying again.'});
  Object.assign(words.zh,{managePeople:'管理人物 · 主人',peopleHelp:'查看本家庭库中已保存的人名和人脸。修改姓名不会合并人物或更改人脸归属。',findPerson:'查找已保存的人名',peopleEmpty:'没有匹配的人名。暂不包含未分配的人脸或尚未关联到本家庭库的人名。',personName:'显示姓名',unnamedPerson:'未命名人物',reviewFaces:'查看人脸',saveName:'保存姓名',nameSaved:'姓名已保存。',nameConflict:'该人物已更改，请查看刷新后的记录再编辑。',nameUnavailable:'此记录需另行确认归属后才能修改姓名。',facesCount:'张本库人脸',moreFaces:'更多人脸',nameShortened:'原姓名较长，此处缩短显示。',nameSaveFailed:'尚未确认保存成功，请刷新记录后再试。'});
  Object.assign(words.en,{viewFilmstrip:'Photos in this view',viewFilmstripItem:'Photo',goToPage:'Go to page',go:'Go',pageRange:'Enter a page number between 1 and the last page.'});
  Object.assign(words.zh,{viewFilmstrip:'当前视图中的照片',viewFilmstripItem:'照片',goToPage:'跳转到页码',go:'前往',pageRange:'请输入有效范围内的页码。'});
  Object.assign(words.en,{displayName:'Your name',displayNameHelp:'How your family will see you, up to 64 characters.',invalidName:'Enter your name to join.',filterByDate:'Filter by date, places and media',discoveryHelp:'Narrow this library by when a photo was taken, a reviewed place, and whether it is a photo or a video. Read-only: nothing here changes or hides a photo.',places:'Places',placesHelp:'Choose a named place from reviewed library metadata. Places are shown only when this library has them.',placesNone:'No named places are available in this library.',placesUnavailable:'Named places are not available for this library.',placesLoading:'Loading named places…',placesRetry:'Retry places',placesCount:'items',placesLimit:'Choose up to 20 places at a time.',placeSelected:'Selected',mediaKind:'Media',mediaAll:'Photos and videos',mediaImage:'Photos only',mediaVideo:'Videos only',dateFrom:'From',dateTo:'To',applyFilter:'Apply',clearFilter:'Clear',discoveryHint:'Choose a date range, named place or media kind, then apply.',discoveryRange:'Enter a range whose first date is not after the second.',discoveryNone:'No item in this library matches that filter.',discoveryChanged:'The library changed after this filter was prepared. Refresh the filter snapshot, then retry.',discoveryResult:'Filtered item'});
  Object.assign(words.zh,{displayName:'您的名字',displayNameHelp:'家人将以此称呼您，最多 64 个字符。',invalidName:'请输入您的名字后再加入。',filterByDate:'按日期、地点和媒体筛选',discoveryHelp:'按拍摄时间、已审核的地点和媒体类型缩小本资料库范围。此处为只读：不会更改或隐藏任何照片。',places:'地点',placesHelp:'选择本家庭库已审核元数据中的命名地点。只有本库存在地点信息时才会显示。',placesNone:'本家庭库暂无可用的命名地点。',placesUnavailable:'本家庭库暂不提供命名地点。',placesLoading:'正在加载命名地点…',placesRetry:'重试地点',placesCount:'项',placesLimit:'一次最多选择 20 个地点。',placeSelected:'已选择',mediaKind:'媒体',mediaAll:'照片和视频',mediaImage:'仅照片',mediaVideo:'仅视频',dateFrom:'从',dateTo:'到',applyFilter:'应用',clearFilter:'清除',discoveryHint:'请选择日期范围、命名地点或媒体类型，然后应用。',discoveryRange:'请输入起始日期不晚于结束日期的范围。',discoveryNone:'本资料库中没有符合该筛选的内容。',discoveryChanged:'筛选准备完成后，相册库内容已发生变化。请刷新筛选依据后重试。',discoveryResult:'筛选出的内容'});
  Object.assign(words.en,{peopleFilter:'Show',peopleAll:'Named and unnamed',peopleNamed:'Named only',peopleUnnamed:'Unnamed only',unassignedFaces:'Unassigned faces · Owner worklist',unassignedHelp:'Faces that no saved person claims yet, across this library. Assigning one keeps the rest of the list.',noUnassignedFaces:'No unassigned faces in this library.',sourcePhoto:'Photo',openPhoto:'Open this photo'});
  Object.assign(words.zh,{peopleFilter:'显示',peopleAll:'已命名与未命名',peopleNamed:'仅已命名',peopleUnnamed:'仅未命名',unassignedFaces:'未分配人脸 · 主人工作清单',unassignedHelp:'本家庭库中尚未归属任何人的人脸。分配其中一张后，清单其余项保持不变。',noUnassignedFaces:'本家庭库中没有未分配的人脸。',sourcePhoto:'照片',openPhoto:'打开这张照片'});
  Object.assign(words.en,{personPhotos:'Photos of this person',noPersonPhotos:'No photo in this library is labelled with this person yet.',clearPerson:'Close',personPhotosHelp:'Read-only. A face label is a guess the library made; it can be wrong.'});
  Object.assign(words.en,{peopleInLibrary:'People in this library',peopleDirectoryHelp:'Names saved in this library, with one face photo each. Only the owner can change a name.',findPersonInLibrary:'Find a person',noPeopleInLibrary:'No saved person names in this library yet.'});
  Object.assign(words.en,{discoveryRetry:'Retry filters',discoveryError:'Filtered items could not load. Try again.',discoveryWorking:'Applying filters…',discoveryResults:n=>`${n} matching items`,discoveryFilters:'Active filters',discoveryUpdated:'The library changed. Refresh the filter snapshot, then retry.'});
  Object.assign(words.zh,{discoveryRetry:'重试筛选',discoveryError:'暂时无法加载筛选结果，请重试。',discoveryWorking:'正在应用筛选…',discoveryResults:n=>`${n} 个符合条件的画面`,discoveryFilters:'当前筛选条件',discoveryUpdated:'相册库内容已变化。请刷新筛选依据后重试。'});
  Object.assign(words.zh,{personPhotos:'此人的照片',noPersonPhotos:'本家庭库中还没有标记为此人的照片。',clearPerson:'关闭',personPhotosHelp:'只读。人脸标记是系统自动判断的结果，可能不准确。'});
  Object.assign(words.zh,{peopleInLibrary:'本家庭库的人物',peopleDirectoryHelp:'本家庭库中已保存的人名，每位配一张人脸照片。只有主人可以修改姓名。',findPersonInLibrary:'查找人物',noPeopleInLibrary:'本家庭库还没有保存的人名。'});
  Object.assign(words.en,{archivedAlbums:'Albums put away',archivedHelp:'Albums this library has put away. Nothing was deleted, so any of them can be brought back.',noArchivedAlbums:'No album has been put away.',archiveAlbum:'Put away',restoreAlbum:'Bring back',confirmArchive:'Put this album away? Nothing is deleted and you can bring it back.'});
  Object.assign(words.en,{describePhoto:'Describe this photo',saveCaption:'Save description',captionSaved:'Saved. Thank you.',captionConflict:'This photo already has a description.'});
  Object.assign(words.en,{duplicatesInLibrary:'Photos saved twice',duplicatesHelp:'Photos this library holds more than once, because the same picture was imported twice. Read-only: nothing here deletes, hides or merges a copy.',savedTimes:'Saved',noDuplicatesInLibrary:'No photo in this library is saved twice.'});
  Object.assign(words.en,{tagsInLibrary:'Tags in this library',tagsHelp:'Tags already attached to photos in this library. Read-only: no tag can be added or removed here.',findTag:'Find a tag',noTagsInLibrary:'No tags in this library yet.',assetsCount:'photos',tagAssets:'Photos with this tag',noTaggedAssets:'No photo in this library carries this tag.',clearTag:'Close'});
  Object.assign(words.zh,{archivedAlbums:'已收起的相册',archivedHelp:'本家庭库收起的相册。照片和相册都没有删除，随时可以恢复。',noArchivedAlbums:'还没有收起任何相册。',archiveAlbum:'收起',restoreAlbum:'恢复',confirmArchive:'确定收起这个相册吗？不会删除任何内容，之后可以恢复。'});
  Object.assign(words.zh,{describePhoto:'为这张照片写一句描述',saveCaption:'保存描述',captionSaved:'已保存，谢谢。',captionConflict:'这张照片已经有描述了。'});
  Object.assign(words.zh,{duplicatesInLibrary:'保存了两次的照片',duplicatesHelp:'本家庭库中保存了不止一次的相同照片，通常是因为同一批照片被导入过两次。只读：这里不会删除、隐藏或合并任何一份。',savedTimes:'保存份数',noDuplicatesInLibrary:'本家庭库中没有重复保存的照片。'});
  Object.assign(words.zh,{tagsInLibrary:'本家庭库的标签',tagsHelp:'本家庭库中照片已附带的标签，仅供查看：此页面不能添加或删除标签。',findTag:'查找标签',noTagsInLibrary:'本家庭库还没有标签。',assetsCount:'张照片',tagAssets:'带此标签的照片',noTaggedAssets:'本家庭库没有照片带此标签。',clearTag:'关闭'});
  Object.assign(words.en,{uploadReview:'Upload review',uploadReviewHelp:'Review private uploads before assigning them to this library. Only the library owner with admin authorization can approve an upload.',uploadLoading:'Loading upload inbox…',uploadEmpty:'No uploads are waiting for review.',uploadRestricted:'Upload review is unavailable for this account.',uploadReviewError:'Uploads could not load. Try again.',approveUpload:'Approve upload',uploadRetryApproval:'Retry approval',approveUploadHelp:'Approving will assign this upload to',approveVisibility:'It will become visible to this library’s members according to their existing access.',uploadReaders:'Current readers',uploadOriginalReaders:'Current original readers',uploadPreviewFailed:'Private preview unavailable. Retry the preview.',uploadApproved:'Upload approved.',uploadConflict:'This upload changed. Review it again before approving.',uploadUncertain:'Approval was not confirmed. The same approval can be retried.',uploadRetry:'Retry review',uploadBytes:'bytes',uploadDimensions:'dimensions',uploadBy:'Uploaded by'});
  Object.assign(words.zh,{uploadReview:'上传审核',uploadReviewHelp:'在将私密上传分配到本家庭库前先进行审核。只有拥有管理员授权的相册库主人可以批准上传。',uploadLoading:'正在加载上传审核…',uploadEmpty:'暂无等待审核的上传。',uploadRestricted:'此账号暂不能进行上传审核。',uploadReviewError:'暂时无法加载上传，请重试。',approveUpload:'批准上传',uploadRetryApproval:'重试批准',approveUploadHelp:'批准后，这张照片将分配到',approveVisibility:'按照现有权限，它将对本家庭库成员可见。',uploadReaders:'当前可读者',uploadOriginalReaders:'当前原文件可读者',uploadPreviewFailed:'私密预览暂不可用，请重试预览。',uploadApproved:'上传已批准。',uploadConflict:'上传内容已变化，请重新审核后再批准。',uploadUncertain:'尚未确认批准结果。可以使用同一确认再次重试。',uploadRetry:'重新审核',uploadBytes:'字节',uploadDimensions:'尺寸',uploadBy:'上传者'});
  Object.assign(words.en,{placeSearchLabel:'Search places',placeSearch:'Search',placeSearchHelp:'Search the local place catalogue in Chinese or English. Choose a result, then apply your filters.',placeSearchNone:'No matching place in this library’s local catalogue. Try another name.',placeSearchTooLong:'Keep the place name within 128 UTF-8 bytes.',placeRemove:'Remove place'});
  Object.assign(words.zh,{placeSearchLabel:'搜索地点',placeSearch:'搜索',placeSearchHelp:'支持中文、英文及常用别名。请先从本地地点目录选择结果，再应用筛选。',placeSearchNone:'本库的本地地点目录暂无匹配结果，请尝试其他名称。',placeSearchTooLong:'地点名称请勿超过 128 个 UTF-8 字节。',placeRemove:'移除地点'});
  const uploadState={page:1,total:0,load:0,items:[],plans:new Map(),dialogItem:null,dialogEpoch:0,previewQueue:{token:0,pending:[],active:false}};
  const tagReviewState={page:1,total:0,load:0,busy:false};
  function storyStatus(key){$('story-status').textContent=key?t(key):'';}
  function abandonStory(){return !storyState.busy&&(!storyState.dirty||window.confirm(t('unsavedStory')))&&(storyWorkspace?.canLeave()??true);}
  function resetStoryEditor(){
    storyState.editing=null;storyState.dirty=false;storyState.pending=null;
    $('story-form').reset();$('story-form').hidden=true;$('story-compare').hidden=true;$('story-conflict').replaceChildren();
    lockStoryInputs(false);
  }
  function lockStoryInputs(locked){for(const id of ['story-title','story-byline','story-language','story-text'])$(id).disabled=locked;}
  function suspendDraft(){
    if(storyState.dirty&&state.profile&&storyState.asset)storyState.suspended={account:state.profile.account_id,library:state.library,asset:storyState.asset,editing:storyState.editing,pending:storyState.pending,locked:$('story-text').disabled,content:Object.fromEntries(['title','byline','text','language'].map(key=>[key,$('story-'+key).value]))};
  }
  async function restoreWithDraft(){
    const restored=await restore();
    if(!restored||document.hidden)return;
    const draft=storyState.suspended;storyState.suspended=null;
    if(draft&&draft.account===state.profile?.account_id&&draft.library===state.library){
      const role=state.profile.memberships.find(member=>member.library_id===draft.library&&member.available)?.role;
      if(role!=='owner'&&(role!=='contributor'||(draft.editing&&draft.editing.author_id!==draft.account)))return;
      const authorized=await openAsset(draft.asset);
      if(authorized&&!document.hidden&&storyState.asset?.id===draft.asset.id&&state.profile?.account_id===draft.account&&state.library===draft.library){editStory(draft.editing,draft.content);storyState.pending=draft.pending;lockStoryInputs(draft.locked);storyStatus(draft.locked?'storySaveError':'draftRecovered');}
    }
  }
  let statusKey = '';
  function status(key) {
    statusKey = key;
    for (const id of ['status','auth-feedback']) $(id).textContent = key ? t(key) : '';
  }
  function translate() {
    document.documentElement.lang = state.language === 'zh' ? 'zh-CN' : 'en';
    document.querySelectorAll('[data-i18n]').forEach(node => {node.textContent=t(node.dataset.i18n);});
    $('language').textContent = state.language === 'en' ? '中文' : 'English';
    $('auth-submit').textContent=t(state.busy?'working':state.mode==='login'?'signIn':'join');
    status(statusKey);
    $('gallery-filter-chips').setAttribute('aria-label',t('discoveryFilters'));
    $('memory-navigation').setAttribute('aria-label',t('memoryNavigation'));
    $('grid').setAttribute('aria-label',t('memoryMediaRegion'));
    storyWorkspace?.translate();
    renderAssistantTrail();
    if(assistantState.transcriptReviewPending){renderAssistantTranscriptLanguage();$('assistant-status').textContent=t('assistantTranscriptReady');}
    syncAssistantControls();
  }
  function closeViewer({keepFrame=false}={}) {
    if(state.videoRetryTimer){clearTimeout(state.videoRetryTimer);state.videoRetryTimer=null;}
    if(state.videoController){state.videoController.abort();state.videoController=null;}
    stopSlideshow();sequenceState.items=[];sequenceState.index=0;sequenceState.busy=false;updateSequence();
    resetPhotoView(keepFrame);
    faceState.load++;faceState.page=1;$('face-list').replaceChildren();$('face-panel').hidden=true;$('face-panel').open=false;$('face-status').textContent='';$('face-pages').hidden=true;
    storyState.asset=null;storyState.load++;storyState.history++;storyState.loading=false;storyState.deletes.clear();resetStoryEditor();
    viewerAnnotationState.load++;viewerAnnotationState.page=1;viewerAnnotationState.total=0;viewerAnnotationState.batch=null;
    $('viewer-annotations').hidden=true;$('viewer-annotations-list').replaceChildren();$('viewer-annotations-status').textContent='';$('viewer-annotations-more').hidden=true;
    $('story-list').replaceChildren();$('story-history').replaceChildren();$('story-history').hidden=true;$('story-add').hidden=true;$('story-more').hidden=true;storyStatus('');
    state.viewerGeneration++;
    if (!keepFrame&&$('viewer').open) $('viewer').close();
    $('viewer-media').querySelectorAll('video').forEach(video => {video.pause();video.removeAttribute('src');video.load();});
    $('viewer-media').replaceChildren(); $('captions').replaceChildren(); $('viewer-title').textContent='';
    $('viewer-controls').hidden=false;$('viewer-sequence').hidden=true;$('view-help').hidden=false;$('viewer-move').hidden=true;
    $('original').removeAttribute('href'); $('original').hidden=true;
  }
  function clearPhotos({cancelMemoryJobs=true}={}) {
    storyWorkspace?.clear({cancelCommunityJobs:cancelMemoryJobs});
    transferState.selected.clear();transferState.review=null;transferState.source=null;transferState.destinations=[];transferState.busy=false;transferState.canMove=null;
    transferState.load++;if($('transfer-review').open)$('transfer-review').close();
    if($('transfer-status'))$('transfer-status').textContent='';
    albumState.load++;$('album-list').replaceChildren();$('album-pages').hidden=true;$('album-status').textContent='';$('album-create').hidden=true;
    if($('album-editor').open)$('album-editor').close();$('album-editor').replaceChildren();
    closeViewer(); $('grid').replaceChildren(); $('pagination').hidden=true; $('empty').hidden=true;
    $('created-code').value=''; $('invitation-result').hidden=true; state.invite=null;
    $('accept-code').value=''; $('invite-phone').value='';
    state.memberGeneration++;$('member-list').replaceChildren();$('member-pages').hidden=true;
    $('member-policy-status').textContent='';
    peopleState.load++;$('people-list').replaceChildren();$('people-pages').hidden=true;$('people-status').textContent='';
    clearUploadReview();clearMyUploads();
  }
  function clearUploadReview(){
    uploadState.load++;uploadState.page=1;uploadState.items=[];uploadState.total=0;uploadState.plans.clear();uploadState.dialogItem=null;uploadState.dialogEpoch=0;uploadState.previewQueue.token++;uploadState.previewQueue.pending=[];uploadState.previewQueue.cancel?.();
    $('uploads-count').textContent='';$('uploads-count').removeAttribute('aria-label');$('uploads-status').textContent='';$('uploads-list').replaceChildren();$('uploads-pages').hidden=true;
    clearProposedTags();
    const dialog=$('upload-review-dialog');if(dialog.open)dialog.close();$('upload-review-preview').replaceChildren();$('upload-review-copy').textContent='';$('upload-review-status').textContent='';$('upload-review-approve').textContent=t('approveUpload');
  }
  function invalidate({cancelMemoryJobs=true}={}) {
    state.generation++;
    if(assistantState.pendingTurn||assistantState.busy)resetAssistant();
    for (const controller of state.controllers) controller.abort();
    state.controllers.clear(); clearPhotos({cancelMemoryJobs});
    return state.generation;
  }
  function stale(epoch) {return epoch !== state.generation;}
  async function request(path, {method='GET',body,rawBody,responseType='json',epoch=state.generation,signal,extraHeaders,onResponse}={}) {
    if(body!==undefined&&rawBody!==undefined)throw new Error('Invalid request body');
    const controller=new AbortController(); state.controllers.add(controller);
    const abort=()=>controller.abort();if(signal){if(signal.aborted)controller.abort();else signal.addEventListener('abort',abort,{once:true});}
    const headers={Accept:responseType==='blob'?'audio/wav':'application/json'};
    if (body !== undefined) headers['Content-Type']='application/json';
    if (method!=='GET' && state.csrf) headers['X-CSRF-Token']=state.csrf;
    if(extraHeaders)Object.assign(headers,extraHeaders);
    try {
      const response=await fetch(path,{method,headers,body:rawBody!==undefined?rawBody:body===undefined?undefined:JSON.stringify(body),
        credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
      if(onResponse)onResponse(response);
      if(stale(epoch)) throw new DOMException('Stale request','AbortError');
      if(!response.ok) {const error=new Error('Request failed');error.status=response.status;throw error;}
      let result;
      if(responseType==='blob'){
        const reader=response.body.getReader(),parts=[];let size=0;
        try{while(true){const part=await reader.read();if(stale(epoch))throw new DOMException('Stale request','AbortError');if(part.done)break;size+=part.value.byteLength;if(size>2*1024*1024)throw new Error('Audio response too large');parts.push(part.value);}result=new Blob(parts,{type:'audio/wav'});}
        finally{await reader.cancel();for(const part of parts)part.fill(0);}
      }else result=await response.json();
      if(stale(epoch)) throw new DOMException('Stale request','AbortError');
      return result;
    } finally {state.controllers.delete(controller);if(signal)signal.removeEventListener('abort',abort);}
  }
  function resetAssistant({clearText=true}={}) {
    assistantState.controller?.abort();assistantState.transcriptionController?.abort();stopAssistantSpeech();
    if(assistantState.capture)void assistantState.capture.stop(false);
    assistantState.capture=null;assistantState.captureStarting=false;assistantState.releaseRequested=false;assistantState.cancelRequested=false;assistantState.pressPointerId=null;assistantState.transcribing=false;
    assistantState.context=null;assistantState.binding=null;assistantState.items=[];assistantState.turnTrail=[];assistantState.pendingTurn=null;assistantState.turnAttempt=null;assistantState.controller=null;assistantState.busy=false;
    assistantState.transcriptionAttempt=null;assistantState.transcriptionController=null;assistantState.transcriptRequestId=null;assistantState.pendingTranscriptRequestId=null;assistantState.transcriptReviewBinding=null;assistantState.transcriptReviewPending=false;assistantState.transcriptLanguage=null;assistantState.turnRequestId=null;assistantState.turnReceipt=null;assistantState.receipt=null;
    if($('assistant-receipt')){$('assistant-receipt').hidden=true;$('assistant-pending-turn').hidden=true;$('assistant-generic-receipt').hidden=false;$('assistant-pending-status').textContent='';$('assistant-pending-question').textContent='';$('assistant-pending-help').textContent='';$('assistant-receipt-status').textContent='';$('assistant-receipt-id').value='';$('assistant-receipt-check').disabled=false;$('assistant-pending-check').disabled=false;}
    if($('assistant-results'))$('assistant-results').replaceChildren();
    if($('assistant-reply'))$('assistant-reply').textContent='';
    renderAssistantTrail();
    if($('assistant-status'))$('assistant-status').textContent='';
    if(clearText&&$('assistant-text'))$('assistant-text').value='';
    if($('assistant-transcript'))$('assistant-transcript').value='';
    if($('assistant-transcript-review'))$('assistant-transcript-review').hidden=true;
    if($('assistant-voice'))$('assistant-voice').hidden=!assistantState.transcribe;
    if($('assistant-speech'))$('assistant-speech').hidden=true;
    if($('assistant-stop'))$('assistant-stop').hidden=true;
    if($('assistant-recording-cancel'))$('assistant-recording-cancel').hidden=true;
    if($('assistant-mic'))$('assistant-mic').setAttribute('aria-pressed','false');
    syncAssistantControls();
  }
  function assistantRequestId(){
    if(!globalThis.crypto?.randomUUID)throw new Error('Secure request IDs are unavailable');
    return crypto.randomUUID().toLowerCase();
  }
  function validAssistantRecoveryString(value){return typeof value==='string'&&value.length>0&&value.length<=128&&!/[\u0000-\u001f\u007f]/.test(value);}
  function clearAssistantRecoveryPointer(requestId=null){
    try{
      if(requestId!==null){const current=readAssistantRecoveryPointer();if(current?.request_id!==requestId)return;}
      sessionStorage.removeItem(assistantRecoveryKey);
    }catch{}
  }
  function readAssistantRecoveryPointer(){
    let raw;
    try{raw=sessionStorage.getItem(assistantRecoveryKey);}catch{return null;}
    if(raw===null)return null;
    if(typeof raw!=='string'||raw.length>assistantRecoveryMaxChars){clearAssistantRecoveryPointer();return null;}
    try{
      const value=JSON.parse(raw),keys=['account_id','library_id','request_id','version'];
      if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join(',')!==keys.join(','))throw new Error();
      if(value.version!==1||typeof value.request_id!=='string'||! /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value.request_id)
          ||!validAssistantRecoveryString(value.account_id)||!validAssistantRecoveryString(value.library_id))throw new Error();
      return value;
    }catch{clearAssistantRecoveryPointer();return null;}
  }
  function writeAssistantRecoveryPointer(requestId,binding){
    if(!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(requestId)
        ||!validAssistantRecoveryString(binding?.account)||!validAssistantRecoveryString(binding?.library))return false;
    const value={version:1,request_id:requestId,account_id:binding.account,library_id:binding.library};
    try{const raw=JSON.stringify(value);if(raw.length>assistantRecoveryMaxChars)return false;sessionStorage.setItem(assistantRecoveryKey,raw);return true;}catch{return false;}
  }
  function recoveryStatusKey(status){return ({received:'assistantRecoveryReceived',succeeded:'assistantRecoverySucceeded',failed:'assistantRecoveryFailed',interrupted:'assistantRecoveryInterrupted'})[status]||'assistantRecoveryUnknown';}
  function presentAssistantRecovery(epoch,available){
    if(stale(epoch)||state.locked||!state.profile||!state.library)return;
    const saved=readAssistantRecoveryPointer();if(!saved)return;
    if(saved.account_id!==state.profile.account_id||!available.some(item=>item.library_id===saved.library_id)||saved.library_id!==state.library){clearAssistantRecoveryPointer();return;}
    const binding={library:saved.library_id,account:saved.account_id,generation:epoch};
    const receipt={id:saved.request_id,operation:'turn',tracking:'unknown',status:null,binding,recovered:true,recoveryCleared:false};
    assistantState.context=null;assistantState.items=[];assistantState.turnTrail=[];assistantState.turnRequestId=null;assistantState.transcriptRequestId=null;
    assistantState.binding=binding;assistantState.receipt=receipt;assistantState.turnReceipt=null;
    $('assistant-results').replaceChildren();$('assistant-reply').textContent='';renderAssistantTrail();
    showAssistantReceipt(receipt,'assistantRecoveryOffer');
    $('assistant-panel').open=true;$('assistant-panel').scrollIntoView({block:'start'});
    $('assistant-receipt-check').focus({preventScroll:true});syncAssistantControls();
  }
  function assistantReceiptLabel(status){return ({received:'assistantReceiptReceived',succeeded:'assistantReceiptSucceeded',failed:'assistantReceiptFailed',interrupted:'assistantReceiptInterrupted'})[status]||'assistantReceiptUnknown';}
  function showAssistantReceipt(receipt,status){
    assistantState.receipt=receipt;
    const panel=$('assistant-receipt');if(!panel)return;
    const pending=assistantState.pendingTurn?.receipt===receipt?assistantState.pendingTurn:null;
    panel.hidden=false;$('assistant-pending-turn').hidden=!pending;$('assistant-generic-receipt').hidden=!!pending;
    $('assistant-receipt-id').value=receipt?.id||'';$('assistant-receipt-status').textContent=t(status);
    $('assistant-receipt-check').disabled=!receipt?.id||receipt.tracking==='disabled'||(receipt.recovered&&receipt.recoveryCleared);
    if(pending)renderAssistantPending(pending);
  }
  function assistantBindingCurrent(binding){return !!binding&&!state.locked&&!stale(binding.generation)&&state.library===binding.library&&state.profile?.account_id===binding.account;}
  function assistantTranscriptBindingCurrent(binding){return !!binding&&!state.locked&&state.library===binding.library&&state.profile?.account_id===binding.account;}
  function assistantRecoveryPending(){return assistantState.receipt?.recovered===true&&!assistantState.receipt.recoveryCleared;}
  function currentAssistantPending(pending=assistantState.pendingTurn){return !!pending&&assistantState.pendingTurn===pending&&assistantBindingCurrent(pending.binding);}
  function renderAssistantPending(pending=assistantState.pendingTurn){
    if(!pending||assistantState.pendingTurn!==pending)return;
    const receipt=pending.receipt,status=receipt.status;
    let key=assistantState.busy&&!receipt.cancelled?'assistantPendingSending':status==='received'?'assistantPendingReceived':status==='succeeded'?'assistantPendingSucceeded':status==='failed'?'assistantPendingFailed':status==='interrupted'?'assistantPendingInterrupted':receipt.cancelled?'assistantPendingCancelled':receipt.tracking==='disabled'?'assistantPendingDisabled':'assistantPendingUnknown';
    $('assistant-receipt').hidden=false;$('assistant-pending-turn').hidden=false;$('assistant-generic-receipt').hidden=true;
    $('assistant-pending-status').textContent=t(key);$('assistant-pending-question').textContent=pending.text;
    $('assistant-pending-help').textContent=receipt.checkFailed?t('assistantPendingCheckUnavailable'):
      (status==='failed'||status==='interrupted'?t('assistantPendingRestoreHelp'):t('assistantPendingHelp'));
    $('assistant-pending-check').disabled=assistantState.busy||receipt.checking===true||receipt.tracking==='disabled';
    $('assistant-pending-restore').hidden=assistantState.busy||!['failed','interrupted'].includes(status);
    $('assistant-pending-restore').disabled=!!$('assistant-text').value.trim();
    $('assistant-pending-ack').disabled=false;
  }
  function syncAssistantControls(){
    if(!$('assistant-send'))return;
    const recoveryPending=assistantRecoveryPending();
    const blocked=assistantState.busy||!!assistantState.pendingTurn||!!recoveryPending||state.locked||assistantState.captureStarting||!!assistantState.capture||assistantState.transcribing||assistantState.transcriptReviewPending;
    $('assistant-send').disabled=blocked||!$('assistant-text').value.trim();
    $('assistant-mic').disabled=blocked;
    $('assistant-clear').disabled=state.locked;
    $('assistant-clear').textContent=recoveryPending?t('assistantRecoveryAcknowledge'):assistantState.pendingTurn?(state.language==='en'?'Clear draft':'清空输入'):t('assistantClear');
    $('assistant-cancel').hidden=!assistantState.busy;
    if(assistantState.pendingTurn)renderAssistantPending();
  }
  function acknowledgeAssistantPending(restoreQuestion=false){
    const pending=assistantState.pendingTurn;if(!currentAssistantPending(pending))return;
    const textarea=$('assistant-text'),newerDraft=textarea.value;
    if(restoreQuestion&&newerDraft.trim()){syncAssistantControls();return;}
    const mayRestore=restoreQuestion&&!newerDraft.trim()&&!assistantState.busy&&['failed','interrupted'].includes(pending.receipt.status);
    clearAssistantRecoveryPointer(pending.receipt.id);
    resetAssistant({clearText:false});
    if(mayRestore)textarea.value=pending.text;
    syncAssistantControls();textarea.focus();
  }
  function acknowledgeAssistantRecovery(){
    const receipt=assistantState.receipt;if(!receipt?.recovered||receipt.recoveryCleared)return;
    clearAssistantRecoveryPointer(receipt.id);receipt.recoveryCleared=true;assistantState.receipt=null;
    $('assistant-receipt').hidden=true;$('assistant-receipt-status').textContent='';$('assistant-receipt-id').value='';
    syncAssistantControls();$('assistant-text').focus();
  }
  async function checkAssistantReceipt(){
    const receipt=assistantState.receipt;
    if(!receipt?.id||receipt.tracking==='disabled'||!receipt.binding||stale(receipt.binding.generation)||state.library!==receipt.binding.library||state.profile?.account_id!==receipt.binding.account)return;
    const pending=assistantState.pendingTurn?.receipt===receipt?assistantState.pendingTurn:null;
    if(pending&&!currentAssistantPending(pending))return;
    receipt.checking=true;receipt.checkFailed=false;
    if(pending)renderAssistantPending(pending);else{$('assistant-receipt-check').disabled=true;$('assistant-receipt-status').textContent=t('assistantReceiptChecking');}
    try{
      const data=await request(`/assistant/v1/receipts/${encodeURIComponent(receipt.id)}?${new URLSearchParams({library_id:receipt.binding.library})}`,{epoch:receipt.binding.generation});
      if(!data||data.version!==1||data.request_id!==receipt.id||!['turn','transcribe','speech'].includes(data.operation)||data.operation!==receipt.operation||!['received','succeeded','failed','interrupted'].includes(data.status))throw new Error('Invalid assistant receipt');
      if(assistantState.receipt!==receipt)return;
      receipt.tracking='enabled';receipt.status=data.status;receipt.checkFailed=false;
      if(data.status!=='received')clearAssistantRecoveryPointer(receipt.id);
      if(receipt.recovered&&data.status!=='received')receipt.recoveryCleared=true;
      showAssistantReceipt(receipt,receipt.recovered?recoveryStatusKey(data.status):assistantReceiptLabel(data.status));syncAssistantControls();
    }catch(error){if(error.name!=='AbortError'&&assistantState.receipt===receipt){receipt.checkFailed=true;if(pending&&currentAssistantPending(pending))renderAssistantPending(pending);else $('assistant-receipt-status').textContent=t(receipt.recovered?'assistantRecoveryUnknown':'assistantReceiptUnavailable');}}
    finally{receipt.checking=false;if(assistantState.receipt===receipt){if(assistantState.pendingTurn?.receipt===receipt)renderAssistantPending(assistantState.pendingTurn);else $('assistant-receipt-check').disabled=receipt.tracking==='disabled'||(receipt.recovered&&receipt.recoveryCleared);}}
  }
  function recordAssistantResponse(response,receipt){
    const metadata=assistantResponseMetadata(response,receipt);receipt.tracking=metadata.tracking;receipt.status=metadata.status;
    if(assistantState.receipt!==receipt||stale(receipt.binding.generation)||state.library!==receipt.binding.library||state.profile?.account_id!==receipt.binding.account)return;
    if(assistantState.pendingTurn?.receipt===receipt)renderAssistantPending(assistantState.pendingTurn);
    else showAssistantReceipt(receipt,receipt.status?assistantReceiptLabel(receipt.status):receipt.tracking==='disabled'?'assistantReceiptDisabled':'assistantReceiptUnconfirmed');
  }
  function assistantResponseMetadata(response,receipt){
    const tracking=response.headers.get('X-PhotoHouse-Tracking');const responseId=response.headers.get('X-PhotoHouse-Request-Id');const status=response.headers.get('X-PhotoHouse-Receipt-Status');
    const mode=tracking==='enabled'?'enabled':tracking==='disabled'?'disabled':'unknown';
    return {tracking:mode,status:mode==='enabled'&&responseId===receipt.id&&['received','succeeded','failed','interrupted'].includes(status)?status:null};
  }
  function reportAssistantOutcome(receipt,outcome){
    if(!receipt?.id||receipt.tracking!=='enabled'||!receipt.status||!['succeeded','failed','interrupted'].includes(receipt.status)||!receipt.binding||stale(receipt.binding.generation)||state.library!==receipt.binding.library||state.profile?.account_id!==receipt.binding.account)return;
    const send=()=>{if(stale(receipt.binding.generation)||state.library!==receipt.binding.library||state.profile?.account_id!==receipt.binding.account)return Promise.resolve();return request(`/assistant/v1/receipts/${encodeURIComponent(receipt.id)}/outcome`,{method:'POST',epoch:receipt.binding.generation,body:{library_id:receipt.binding.library,outcome}}).catch(()=>{});};
    receipt.outcomePromise=(receipt.outcomePromise||Promise.resolve()).then(send);
  }
  function stopAssistantSpeech(revoke=true) {
    assistantState.speechController?.abort();assistantState.speechController=null;
    const audio=$('assistant-speech-audio');audio.pause();try{audio.currentTime=0;}catch{}
    if(revoke){audio.removeAttribute('src');audio.load();if(assistantState.speechUrl)URL.revokeObjectURL(assistantState.speechUrl);assistantState.speechUrl=null;}
    $('assistant-play').disabled=false;$('assistant-speech-stop').hidden=true;
  }
  function assistantErrorKey(error) {
    return error.status===401||error.status===403?'assistantDenied':error.status===409?'assistantConflict':error.status===429?'assistantLimited':error.status===404||error.status===503||!error.status||error.status>=500?'assistantUnavailable':'assistantError';
  }
  function validAssistantTurn(value) {
    if(!value||typeof value!=='object'||Array.isArray(value)||value.version!==1||!['results','open','clarification','unsupported'].includes(value.kind)||typeof value.reply!=='string'||value.reply.length>4000||!(value.context===null||(value.context&&typeof value.context==='object'&&!Array.isArray(value.context)))||!(value.filters===null||(value.filters&&typeof value.filters==='object'&&!Array.isArray(value.filters)))||!Array.isArray(value.items)||value.items.length>100||!Number.isInteger(value.total)||value.total<0||typeof value.has_more!=='boolean')return false;
    const ids=new Set();for(const item of value.items){if(!item||typeof item!=='object'||Array.isArray(item)||typeof item.id!=='string'||!/^[1-9][0-9]{0,18}$/.test(item.id)||ids.has(item.id)||typeof item.kind!=='string'||item.kind.length>32)return false;ids.add(item.id);}
    if(value.effect!==null&&(!value.effect||typeof value.effect!=='object'||Array.isArray(value.effect)||value.effect.type!=='open_asset'||typeof value.effect.asset_id!=='string'||!/^[1-9][0-9]{0,18}$/.test(value.effect.asset_id)||!ids.has(value.effect.asset_id)))return false;
    return true;
  }
  async function loadAssistantCapabilities(epoch=state.generation) {
    assistantState.transcribe=false;assistantState.speech=false;
    resetAssistant();$('assistant-form').hidden=true;$('assistant-status').textContent=t('assistantWorking');
    try {
      const result=await request(`/assistant/v1/capabilities?${new URLSearchParams({library_id:state.library||''})}`,{epoch});
      if(stale(epoch))return;
      if(!result||result.version!==1||result.enabled!==true||result.text!==true){$('assistant-status').textContent=t('assistantUnavailable');return;}
      assistantState.transcribe=result.transcribe===true;assistantState.speech=result.speech===true;$('assistant-voice').hidden=!assistantState.transcribe;
      $('assistant-form').hidden=false;$('assistant-status').textContent='';syncAssistantControls();
    } catch(error) {
      if(error.name==='AbortError'||stale(epoch))return;
      $('assistant-form').hidden=true;$('assistant-status').textContent=t(assistantErrorKey(error));
    }
  }
  function assistantWavValid(file) {
    if(!file||file.size<44||file.size>960044||file.type!=='audio/wav')return false;
    return file.slice(0,44).arrayBuffer().then(buffer=>{const view=new DataView(buffer),label=(at,value)=>Array.from({length:value.length},(_,index)=>String.fromCharCode(view.getUint8(at+index))).join('')===value;return label(0,'RIFF')&&label(8,'WAVE')&&label(12,'fmt ')&&view.getUint32(16,true)===16&&view.getUint16(20,true)===1&&view.getUint16(22,true)===1&&view.getUint32(24,true)===16000&&view.getUint32(28,true)===32000&&view.getUint16(32,true)===2&&view.getUint16(34,true)===16&&label(36,'data')&&view.getUint32(40,true)===file.size-44;});
  }
  function currentAssistantTranscription(attempt){return assistantState.transcriptionAttempt===attempt&&assistantBindingCurrent(attempt?.binding);}
  function renderAssistantTranscriptLanguage(){
    const key=assistantState.transcriptLanguage==='zh'?'Zh':assistantState.transcriptLanguage==='en'?'En':assistantState.transcriptLanguage==='mixed'?'Mixed':'Unknown';
    $('assistant-transcript-language').textContent=`${t('assistantTranscriptLanguage')}: ${t(`assistantLang${key}`)}`;
  }
  async function requestAssistantTranscription(file,binding,attempt) {
    if(assistantState.pendingTurn||assistantRecoveryPending()||assistantState.busy||!currentAssistantTranscription(attempt))throw new DOMException('Assistant turn is pending','AbortError');
    if(!await assistantWavValid(file))throw new Error('Invalid assistant recording');
    if(assistantState.pendingTurn||assistantRecoveryPending()||assistantState.busy||!currentAssistantTranscription(attempt))throw new DOMException('Assistant turn is pending','AbortError');
    const requestId=assistantRequestId();const receipt={id:requestId,operation:'transcribe',tracking:'unknown',status:null,binding:{...binding}};assistantState.pendingTranscriptRequestId=null;assistantState.transcriptReviewBinding=null;assistantState.transcriptReviewPending=false;assistantState.transcriptLanguage=null;assistantState.receipt=receipt;showAssistantReceipt(receipt,'assistantReceiptUnknown');
    const controller=new AbortController();assistantState.transcriptionController=controller;state.controllers.add(controller);
    const headers={'Content-Type':'audio/wav','X-PhotoHouse-Library-Id':binding.library,'X-PhotoHouse-Request-Id':requestId};if(state.csrf)headers['X-CSRF-Token']=state.csrf;
    try {
      const response=await fetch('/assistant/v1/transcribe',{method:'POST',headers,body:file,credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
      recordAssistantResponse(response,receipt);
      if(!currentAssistantTranscription(attempt))throw new DOMException('Stale request','AbortError');
      if(!response.ok){const error=new Error('Transcription request failed');error.status=response.status;throw error;}
      const result=await response.json();
      if(!currentAssistantTranscription(attempt))throw new DOMException('Stale request','AbortError');
      if(!result||result.version!==1||typeof result.text!=='string'||result.text.length>1024||!['zh','en','mixed','unknown'].includes(result.language))throw new Error('Invalid transcription response');
      assistantState.pendingTranscriptRequestId=receipt.tracking==='enabled'&&receipt.status==='succeeded'?requestId:null;
      return result;
    } catch(error){
      if(error.name!=='AbortError'&&!receipt.status&&assistantState.receipt===receipt)showAssistantReceipt(receipt,receipt.tracking==='disabled'?'assistantReceiptDisabled':'assistantReceiptUnknown');
      throw error;
    } finally {state.controllers.delete(controller);if(assistantState.transcriptionController===controller)assistantState.transcriptionController=null;}
  }
  async function transcribeAssistantRecording(file,binding) {
    if(assistantState.pendingTurn||assistantRecoveryPending()||assistantState.busy||assistantState.transcriptReviewPending||!assistantBindingCurrent(binding))return;
    const attempt={binding};assistantState.transcriptionAttempt=attempt;assistantState.transcribing=true;syncAssistantControls();$('assistant-status').textContent=t('assistantTranscribing');
    try {
      const result=await requestAssistantTranscription(file,binding,attempt);
      if(!currentAssistantTranscription(attempt)||assistantState.pendingTurn||assistantRecoveryPending()||assistantState.busy)return;
      assistantState.transcriptReviewBinding={...binding};assistantState.transcriptReviewPending=true;assistantState.transcriptLanguage=result.language;
      $('assistant-transcript').value=result.text;$('assistant-transcript-review').hidden=false;renderAssistantTranscriptLanguage();$('assistant-status').textContent=t('assistantTranscriptReady');reportAssistantOutcome(assistantState.receipt,'displayed');
    } catch(error) {
      if(error.name==='AbortError'||!currentAssistantTranscription(attempt))return;
      $('assistant-status').textContent=error.message==='Invalid assistant recording'||error.message==='Invalid transcription response'?t('assistantTranscriptError'):t(assistantErrorKey(error));
    } finally {if(assistantState.transcriptionAttempt===attempt){assistantState.transcribing=false;assistantState.transcriptionAttempt=null;syncAssistantControls();}}
  }
  function acceptAssistantTranscript(){
    const binding=assistantState.transcriptReviewBinding;
    if(!assistantState.transcriptReviewPending||!assistantTranscriptBindingCurrent(binding)||assistantRecoveryPending()||assistantState.pendingTurn||assistantState.busy)return;
    const composer=$('assistant-text'),transcript=$('assistant-transcript').value,current=composer.value;
    if(!transcript.trim())return;
    const combined=current?`${current}${current.endsWith('\n')?'':'\n'}${transcript}`:transcript;
    if(new TextEncoder().encode(combined.trim()).length>1024){$('assistant-status').textContent=t('assistantTranscriptTooLong');return;}
    composer.value=combined;assistantState.transcriptRequestId=assistantState.pendingTranscriptRequestId;
    assistantState.pendingTranscriptRequestId=null;assistantState.transcriptReviewBinding=null;assistantState.transcriptReviewPending=false;assistantState.transcriptLanguage=null;
    $('assistant-transcript').value='';$('assistant-transcript-review').hidden=true;$('assistant-status').textContent='';syncAssistantControls();composer.focus();
  }
  function discardAssistantTranscript(){
    assistantState.transcriptRequestId=null;assistantState.pendingTranscriptRequestId=null;assistantState.transcriptReviewBinding=null;assistantState.transcriptReviewPending=false;assistantState.transcriptLanguage=null;
    $('assistant-transcript').value='';$('assistant-transcript-review').hidden=true;$('assistant-status').textContent='';syncAssistantControls();
  }
  async function playAssistantSpeech() {
    const binding=assistantState.binding,context=assistantState.context,audio=$('assistant-speech-audio');
    if(!assistantState.speech||assistantState.pendingTurn||assistantState.busy||assistantState.transcribing||assistantState.capture||!binding||!context||assistantState.speechController||!audio.paused||stale(binding.generation)||state.library!==binding.library||state.profile?.account_id!==binding.account)return;
    $('assistant-play').disabled=true;$('assistant-speech-stop').hidden=false;
    try {
      if(!assistantState.speechUrl){
        const requestId=assistantRequestId();const receipt={id:requestId,operation:'speech',tracking:'unknown',status:null,binding:{...binding}};assistantState.receipt=receipt;showAssistantReceipt(receipt,'assistantReceiptUnknown');
        const controller=new AbortController();assistantState.speechController=controller;state.controllers.add(controller);
        const headers={'Accept':'audio/wav','Content-Type':'application/json','X-PhotoHouse-Request-Id':requestId};if(assistantState.turnRequestId)headers['X-PhotoHouse-Parent-Request-Id']=assistantState.turnRequestId;if(state.csrf)headers['X-CSRF-Token']=state.csrf;
        try {
          const response=await fetch('/assistant/v1/speech',{method:'POST',headers,body:JSON.stringify({library_id:binding.library,context,language:state.language==='zh'?'zh':'en'}),credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
          recordAssistantResponse(response,receipt);
          if(stale(binding.generation)||state.library!==binding.library||state.profile?.account_id!==binding.account)throw new DOMException('Stale request','AbortError');
          if(!response.ok){const error=new Error('Speech request failed');error.status=response.status;throw error;}
          if((response.headers.get('Content-Type')||'').split(';')[0].trim().toLowerCase()!=='audio/wav')throw new Error('Invalid speech audio');
          const blob=await response.blob();if(blob.size<44||blob.size>2*1024*1024)throw new Error('Invalid speech audio');
          const signature=new Uint8Array(await blob.slice(0,12).arrayBuffer());
          if(String.fromCharCode(...signature.slice(0,4))!=='RIFF'||String.fromCharCode(...signature.slice(8,12))!=='WAVE')throw new Error('Invalid speech audio');
          if(stale(binding.generation)||state.library!==binding.library||state.profile?.account_id!==binding.account)throw new DOMException('Stale request','AbortError');
          assistantState.speechUrl=URL.createObjectURL(blob);audio.src=assistantState.speechUrl;
        } finally {state.controllers.delete(controller);assistantState.speechController=null;}
      }
      await audio.play();
    } catch(error) {
      $('assistant-speech-stop').hidden=true;
      if(error.name==='AbortError')return;
      if(assistantState.receipt?.operation==='speech'&&!assistantState.receipt.status)showAssistantReceipt(assistantState.receipt,assistantState.receipt.tracking==='disabled'?'assistantReceiptDisabled':'assistantReceiptUnknown');
      $('assistant-status').textContent=error.status?t(assistantErrorKey(error)):t('assistantSpeechError');
    } finally {$('assistant-play').disabled=!audio.paused&&!audio.ended;if(audio.paused)$('assistant-speech-stop').hidden=true;}
  }
  async function startAssistantCapture() {
    if(!assistantState.transcribe||assistantState.pendingTurn||assistantRecoveryPending()||assistantState.transcriptReviewPending||assistantState.captureStarting||assistantState.capture||annotationState.capture||assistantState.transcribing||assistantState.busy||state.locked||!state.profile||!state.library)return;
    const binding={library:String(state.library),account:String(state.profile.account_id),generation:state.generation};
    assistantState.transcriptRequestId=null;assistantState.pendingTranscriptRequestId=null;assistantState.transcriptReviewBinding=null;assistantState.transcriptReviewPending=false;assistantState.transcriptLanguage=null;assistantState.turnRequestId=null;assistantState.turnReceipt=null;assistantState.receipt=null;$('assistant-transcript').value='';$('assistant-transcript-review').hidden=true;$('assistant-receipt').hidden=true;$('assistant-receipt-id').value='';$('assistant-receipt-status').textContent='';
    assistantState.captureStarting=true;assistantState.releaseRequested=false;assistantState.cancelRequested=false;$('assistant-status').textContent=t('assistantRecording');syncAssistantControls();
    try {
      const capture=await annotationCapture(file=>{assistantState.capture=null;$('assistant-mic').setAttribute('aria-pressed','false');$('assistant-stop').hidden=true;$('assistant-recording-cancel').hidden=true;void transcribeAssistantRecording(file,binding);},30);
      if(assistantState.pendingTurn||assistantRecoveryPending()||!assistantBindingCurrent(binding)){void capture.stop(false);return;}
      assistantState.capture=capture;annotationState.capture=capture;$('assistant-mic').setAttribute('aria-pressed','true');$('assistant-stop').hidden=false;$('assistant-recording-cancel').hidden=false;
      if(assistantState.cancelRequested)finishAssistantCapture(false);else if(assistantState.releaseRequested)finishAssistantCapture(true);
    } catch(error) {if(!stale(binding.generation))$('assistant-status').textContent=t('annotationCaptureError');}
    finally {assistantState.captureStarting=false;syncAssistantControls();}
  }
  function finishAssistantCapture(keep) {
    if(!assistantState.capture){if(assistantState.captureStarting){assistantState.releaseRequested=keep;assistantState.cancelRequested=!keep;}return;}
    const capture=assistantState.capture;assistantState.capture=null;$('assistant-mic').setAttribute('aria-pressed','false');$('assistant-stop').hidden=true;$('assistant-recording-cancel').hidden=true;
    if(!keep)$('assistant-status').textContent=t('assistantCancelled');
    void capture.stop(keep);
  }
  function renderAssistantTrail(revealLatest=false){
    const section=$('assistant-turn-trail'),list=$('assistant-turn-trail-list');
    if(!section||!list)return;
    const previousScrollTop=list.scrollTop;
    list.tabIndex=0;list.setAttribute('aria-labelledby','assistant-turn-trail-title');
    if(list.dataset.keyboardScrollBound!=='true'){
      list.dataset.keyboardScrollBound='true';
      list.addEventListener('keydown',event=>{
        const step=Math.max(48,Math.floor(list.clientHeight*.8));
        if(event.key==='Home'){list.scrollTop=0;event.preventDefault();}
        else if(event.key==='End'){list.scrollTop=list.scrollHeight;event.preventDefault();}
        else if(event.key==='PageDown'||event.key==='ArrowDown'){list.scrollTop+=event.key==='PageDown'?step:48;event.preventDefault();}
        else if(event.key==='PageUp'||event.key==='ArrowUp'){list.scrollTop-=event.key==='PageUp'?step:48;event.preventDefault();}
      });
    }
    list.replaceChildren();
    for(const exchange of assistantState.turnTrail){
      const item=document.createElement('li');item.className='assistant-turn-trail-entry';
      const questionLabel=document.createElement('strong');questionLabel.className='assistant-turn-trail-role';questionLabel.textContent=t('assistantTrailYou');
      const question=document.createElement('p');question.className='assistant-turn-trail-text';question.textContent=exchange.question;
      const replyLabel=document.createElement('strong');replyLabel.className='assistant-turn-trail-role';replyLabel.textContent=t('assistantTrailAssistant');
      const reply=document.createElement('p');reply.className='assistant-turn-trail-text';reply.textContent=exchange.reply;
      item.append(questionLabel,question,replyLabel,reply);list.append(item);
    }
    section.hidden=assistantState.turnTrail.length===0;
    if(revealLatest&&assistantState.turnTrail.length)list.scrollTop=list.scrollHeight;
    else list.scrollTop=previousScrollTop;
  }
  function rememberAssistantTurn(question,turn){
    assistantState.turnTrail.push({question,reply:turn.reply});
    if(assistantState.turnTrail.length>8)assistantState.turnTrail.shift();
    renderAssistantTrail(true);
  }
  function renderAssistantTurn(turn,epoch) {
    stopAssistantSpeech();
    const root=$('assistant-results');root.replaceChildren();assistantState.items=turn.items;
    $('assistant-reply').textContent=turn.reply;
    $('assistant-speech').hidden=!(assistantState.speech&&turn.kind==='results'&&turn.context);
    if(turn.kind==='unsupported'&&!turn.reply)$('assistant-reply').textContent=t('assistantUnsupported');
    if(!turn.items.length&&turn.kind==='results'&&!turn.reply)$('assistant-reply').textContent=t('assistantNoResults');
    for(const item of turn.items) {
      const card=document.createElement('article');card.className='assistant-result';
      const image=document.createElement('img');image.className='assistant-thumbnail';image.loading='lazy';image.alt=assetLabel(item);image.src=safeMediaURL(item.id,'thumbnail');
      image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});card.append(image);
      const title=document.createElement('p');title.textContent=assetLabel(item);card.append(title);
      if(item.match&&typeof item.match.excerpt==='string'){const excerpt=document.createElement('p');excerpt.className='fine';excerpt.textContent=item.match.excerpt.slice(0,1200);card.append(excerpt);}
      const button=document.createElement('button');button.type='button';button.className='quiet';button.textContent=t('assistantOpen');button.addEventListener('click',()=>{if(stale(epoch)||state.locked||state.library!==assistantState.binding?.library)return;reportAssistantOutcome(assistantState.turnReceipt,'open_requested');void openAsset(item,{sequence:assistantState.items,origin:'assistant'});});card.append(button);root.append(card);
    }
    if(turn.kind==='results'&&turn.items.length){const button=storyButton('storyWorkspaceResults',()=>{if(!stale(epoch)&&!state.locked)storyWorkspace.fromResults(turn.items);});button.id='assistant-shape-story';button.classList.add('assistant-story-action');root.append(button);}
    if(turn.effect?.type==='open_asset') {
      const item=turn.items.find(candidate=>candidate.id===turn.effect.asset_id);
      if(item&&turn.kind==='open'&&!stale(epoch)&&!state.locked){reportAssistantOutcome(assistantState.turnReceipt,'open_requested');void openAsset(item,{sequence:turn.items,origin:'assistant'});}
    }
  }
  async function submitAssistant(event) {
    event.preventDefault();
    if(assistantState.busy||assistantState.pendingTurn||assistantRecoveryPending()||assistantState.transcriptReviewPending||assistantState.capture||assistantState.captureStarting||assistantState.transcribing||state.locked||!state.profile||!state.library)return;
    const text=$('assistant-text').value.trim();if(!text)return;
    if(new TextEncoder().encode(text).length>1024){$('assistant-status').textContent=t('assistantTextTooLong');return;}
    stopAssistantSpeech();
    const epoch=state.generation,binding=Object.freeze({library:String(state.library),account:String(state.profile.account_id),generation:epoch});
    const bindingKey=JSON.stringify(binding);
    if(JSON.stringify(assistantState.binding)!==bindingKey){assistantState.context=null;assistantState.items=[];assistantState.turnTrail=[];assistantState.binding=binding;$('assistant-results').replaceChildren();$('assistant-reply').textContent='';renderAssistantTrail();}
    const requestId=assistantRequestId(),receipt={id:requestId,operation:'turn',tracking:'unknown',status:null,binding};
    writeAssistantRecoveryPointer(requestId,binding);
    const context=assistantState.context===null?null:JSON.parse(JSON.stringify(assistantState.context));
    if(context){const freeze=value=>{if(value&&typeof value==='object'&&!Object.isFrozen(value)){Object.freeze(value);for(const child of Object.values(value))freeze(child);}return value;};freeze(context);}
    const pending=Object.freeze({text,context,parentRequestId:assistantState.transcriptRequestId,requestId,binding,receipt});
    const attempt={pending,controller:new AbortController()};
    assistantState.pendingTurn=pending;assistantState.receipt=receipt;assistantState.turnReceipt=receipt;assistantState.turnRequestId=null;
    assistantState.items=[];$('assistant-results').replaceChildren();$('assistant-reply').textContent='';
    assistantState.turnAttempt=attempt;assistantState.controller=attempt.controller;assistantState.busy=true;$('assistant-speech').hidden=true;$('assistant-status').textContent=t('assistantWorking');
    showAssistantReceipt(receipt,'assistantReceiptUnknown');syncAssistantControls();
    const parentRequestId=pending.parentRequestId,extraHeaders={'X-PhotoHouse-Request-Id':requestId};if(parentRequestId)extraHeaders['X-PhotoHouse-Parent-Request-Id']=parentRequestId;
    try {
      const turnPromise=request('/assistant/v1/turns',{method:'POST',body:{library_id:binding.library,text:pending.text,context:pending.context},epoch,signal:attempt.controller.signal,extraHeaders,onResponse:response=>recordAssistantResponse(response,receipt)});
      if($('assistant-text').value.trim()===text)$('assistant-text').value='';
      syncAssistantControls();
      const turn=await turnPromise;
      if(assistantState.turnAttempt!==attempt||!currentAssistantPending(pending))return;
      if(!validAssistantTurn(turn))throw new Error('Invalid assistant response');
      assistantState.pendingTurn=null;assistantState.context=turn.context;assistantState.binding=binding;
      rememberAssistantTurn(pending.text,turn);
      if(receipt.tracking==='enabled'&&receipt.status==='succeeded')assistantState.turnRequestId=requestId;
      assistantState.transcriptRequestId=null;
      showAssistantReceipt(receipt,receipt.status?assistantReceiptLabel(receipt.status):'assistantReceiptSucceeded');
      reportAssistantOutcome(receipt,'displayed');renderAssistantTurn(turn,epoch);clearAssistantRecoveryPointer(requestId);$('assistant-status').textContent='';
    } catch(error) {
      if(assistantState.turnAttempt!==attempt||!currentAssistantPending(pending))return;
      if(error.name==='AbortError'){$('assistant-status').textContent=t('assistantPendingUnknown');return;}
      if(receipt.status==='failed')reportAssistantOutcome(receipt,'failed');
      $('assistant-status').textContent=error.message==='Invalid assistant response'?t('assistantInvalid'):t(assistantErrorKey(error));
      renderAssistantPending(pending);
    } finally {
      if(assistantState.turnAttempt===attempt){assistantState.busy=false;assistantState.controller=null;assistantState.turnAttempt=null;syncAssistantControls();}
    }
  }
  function showAuth() {
    assistantState.transcribe=false;assistantState.speech=false;
    resetAssistant();$('assistant-form').hidden=true;
    albumState.draft=null;albumState.page=1;$('album-archived-panel').hidden=true;$('album-archived-panel').open=false;$('album-archived-list').replaceChildren();
    storyState.search=null;storyState.suspended=null;$('search-text').value='';$('search-source').value='all';
    clearMyUploads();$('my-uploads-open').hidden=true;$('my-uploads-panel').hidden=true;
    state.profile=null;state.csrf=null;state.library=null;state.catalogue=null;state.locked=false;clearUploadReview();$('uploads-panel').hidden=true;$('uploads-open').hidden=true;$('uploads-panel').open=false;$('tag-review-panel').hidden=true;$('tag-review-panel').open=false;updateTransferUI();
    $('account-label').textContent='';$('library-select').replaceChildren();$('owner-panel').hidden=true;$('members-panel').hidden=true;$('people-panel').hidden=true;
    peopleState.page=1;peopleState.query='';peopleState.named='all';$('people-query').value='';$('people-named').value='all';
    unassignedState.page=1;$('unassigned-list').replaceChildren();
    directoryState.page=1;directoryState.query='';directoryState.total=0;directoryState.person=null;directoryState.assetPage=1;directoryState.assetTotal=0;
    $('directory-query').value='';$('directory-list').replaceChildren();$('directory-status').textContent='';$('directory-pages').hidden=true;
    tagState.page=1;tagState.query='';tagState.total=0;tagState.tag=null;tagState.tagPage=1;tagState.tagTotal=0;tagState.open=null;
    $('tag-query').value='';$('tag-list').replaceChildren();$('tag-status').textContent='';$('tag-pages').hidden=true;$('tag-assets').replaceChildren();
    familyTagState.load++;familyTagState.tagLoad++;familyTagState.page=1;familyTagState.query='';familyTagState.total=0;familyTagState.tag=null;familyTagState.assetPage=1;familyTagState.assetTotal=0;
    $('family-tag-query').value='';$('family-tag-list').replaceChildren();$('family-tag-status').textContent='';$('family-tag-pages').hidden=true;$('family-tag-assets').replaceChildren();$('family-tag-asset-pages').hidden=true;
    discoveryState.binding=null;discoveryState.owner=null;discoveryState.active=false;discoveryState.modeToken++;discoveryState.page=1;discoveryState.total=0;discoveryState.facetLoad=0;discoveryState.searchLoad=0;discoveryState.fingerprint=null;discoveryState.applied=false;discoveryState.appliedFilters=null;discoveryState.appliedLocationLabels.clear();discoveryState.placePage=1;discoveryState.placeTotal=0;discoveryState.places=[];discoveryState.selectedPlaces.clear();discoveryState.selectedPlaceLabels.clear();discoveryState.placesAvailable=false;
    $('discovery-panel').hidden=true;$('discovery-panel').open=false;$('discovery-media').value='all';$('discovery-from').value='';$('discovery-to').value='';$('discovery-status').textContent='';$('discovery-facets-retry').hidden=true;$('gallery-filter-summary').hidden=true;$('gallery-filter-chips').replaceChildren();$('gallery-filter-actions').replaceChildren();$('gallery-filter-count').textContent='';$('gallery-filter-status').textContent='';$('discovery-place-list').replaceChildren();$('discovery-place-selected').replaceChildren();$('discovery-place-query').value='';discoveryState.placeQuery='';$('discovery-place-pages').hidden=true;$('discovery-places').hidden=true;$('discovery-places-status').textContent='';
    $('library').hidden=true;$('auth').hidden=false;$('password').value='';$('code').value='';$('name').value='';
  }
  function errorStatus(error) {return error.status===409?'conflict':error.status===429?'limited':error.status===401||error.status===403?'denied':'unavailable';}
  async function failure(error,epoch) {
    if(error.name==='AbortError'||stale(epoch))return;
    if(error.status===401||error.status===403) {
      invalidate(); status('changed');
      await restore(false);
    } else {status(errorStatus(error));}
  }
  function libraryPath(path,extra={}) {return path+'?'+new URLSearchParams({library:state.library,...extra});}
  function assetLabel(item) {return `${t(item.kind==='image'?'photo':item.kind)} ${item.id}${item.taken_at?' · '+String(item.taken_at).slice(0,10):''}`;}
  function safeMediaURL(id,variant,extra={}) {return libraryPath(`/assets/${id}/${variant}`,extra);}
  function resetPhotoView(keepFrame=false){
    if(!keepFrame&&document.fullscreenElement===$('photo-viewer'))void document.exitFullscreen().catch(()=>{});
    if(photoState.drag&&$('viewer-media').hasPointerCapture(photoState.drag.id))$('viewer-media').releasePointerCapture(photoState.drag.id);
    photoState.image=null;photoState.surface=null;photoState.drag=null;photoState.mode='fit';photoState.scale=1;
    $('viewer-media').classList.remove('dragging');$('photo-viewer').hidden=!keepFrame;
    $('view-scale').textContent='';$('view-quality').textContent='';
    for(const id of ['fit','width','height','actual','in','out'])$('view-'+id).disabled=true;
  }
  function photoButtons(){
    for(const mode of ['fit','width','height','actual'])$('view-'+mode).setAttribute('aria-pressed',String(photoState.mode===mode));
    $('view-scale').textContent=Math.round(photoState.scale*100)+'%';
    $('view-in').disabled=photoState.scale>=16;$('view-out').disabled=photoState.scale<=0.01;
  }
  function drawPhoto(scale,anchor){
    const img=photoState.image,stage=$('viewer-media'),surface=photoState.surface;
    if(!img?.naturalWidth||!stage.clientWidth||!surface)return;
    const oldScale=photoState.scale;
    // Anchor zoom to the image pixel under the pointer (or the viewport centre).
    const x=anchor?.x??stage.clientWidth/2,y=anchor?.y??stage.clientHeight/2;
    const px=(stage.scrollLeft+x-img.offsetLeft)/oldScale,py=(stage.scrollTop+y-img.offsetTop)/oldScale;
    photoState.scale=Math.max(0.01,Math.min(16,scale));
    const width=img.naturalWidth*photoState.scale,height=img.naturalHeight*photoState.scale;
    surface.style.width=Math.max(stage.clientWidth,width)+'px';surface.style.height=Math.max(stage.clientHeight,height)+'px';
    img.style.width=width+'px';img.style.height=height+'px';
    img.style.left=Math.max(0,(stage.clientWidth-width)/2)+'px';img.style.top=Math.max(0,(stage.clientHeight-height)/2)+'px';
    stage.scrollLeft=anchor?px*photoState.scale+img.offsetLeft-x:(surface.offsetWidth-stage.clientWidth)/2;
    stage.scrollTop=anchor?py*photoState.scale+img.offsetTop-y:(surface.offsetHeight-stage.clientHeight)/2;
    photoButtons();
  }
  function fitPhoto(mode=photoState.mode){
    const img=photoState.image,stage=$('viewer-media');
    if(!img?.naturalWidth)return;
    photoState.mode=mode;
    const width=stage.clientWidth/img.naturalWidth,height=stage.clientHeight/img.naturalHeight;
    drawPhoto(mode==='fit'?Math.min(width,height):mode==='width'?width:mode==='height'?height:mode==='actual'?1:photoState.scale);
  }
  function zoomPhoto(factor,anchor={}){if(!photoState.image?.naturalWidth)return;photoState.mode='custom';drawPhoto(photoState.scale*factor,anchor);}
  async function fullscreenPhoto(){
    try{
      if(document.fullscreenElement===$('photo-viewer'))await document.exitFullscreen();
      else if($('photo-viewer').requestFullscreen)await $('photo-viewer').requestFullscreen();
      else throw new Error('Fullscreen unavailable');
    }catch{if(!$('photo-viewer').hidden)$('view-quality').textContent=t('viewQuality')+' '+t('viewFullscreenFailed');}
  }
  async function previewURL(id,epoch){
    // Prefer an already prepared larger thumbnail. Probe metadata only; no
    // original/display fallback or runtime media generation is introduced.
    const url=safeMediaURL(id,'thumbnail',{size:'1024'}),controller=new AbortController();
    state.controllers.add(controller);
    try{
      const response=await fetch(url,{method:'HEAD',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
      if(stale(epoch))throw new DOMException('Stale request','AbortError');
      if(response.status===404)return safeMediaURL(id,'thumbnail');
      if(!response.ok){const error=new Error('Preview unavailable');error.status=response.status;throw error;}
      return url;
    }finally{state.controllers.delete(controller);}
  }
  function showPhoto(item,url){
    const image=document.createElement('img'),surface=document.createElement('div');surface.className='viewer-surface';
    image.alt=assetLabel(item);image.draggable=false;photoState.image=image;photoState.surface=surface;
    $('photo-viewer').hidden=false;$('view-quality').textContent=t('viewQuality');
    for(const id of ['fit','width','height','actual','in','out'])$('view-'+id).disabled=true;
    image.addEventListener('load',()=>{if(photoState.image!==image)return;for(const id of ['fit','width','height','actual'])$('view-'+id).disabled=false;fitPhoto('fit');updateSequence();scheduleSlideshow();});
    image.addEventListener('error',()=>{if(photoState.image!==image)return;stopSlideshow();$('view-quality').textContent=t('previewMissing');});
    image.src=url;surface.append(image);$('viewer-media').append(surface);
  }
  async function showPreparedVideo(item,epoch,viewerGeneration){
    const current=()=>!stale(epoch)&&viewerGeneration===state.viewerGeneration&&$('viewer').open;
    if(!current())return;
    const media=$('viewer-media');
    media.replaceChildren();
    $('viewer-controls').hidden=true;$('viewer-sequence').hidden=true;$('view-help').hidden=true;
    $('view-quality').textContent=t('videoChecking');
    function offerRetry(message,retryHeader=null,status=0){
      if(!current())return;
      if(state.videoRetryTimer){clearTimeout(state.videoRetryTimer);state.videoRetryTimer=null;}
      $('view-quality').textContent=t(message);
      const retry=document.createElement('button');retry.type='button';retry.className='quiet';retry.textContent=t('videoRetry');
      let wait=status===429?5000:0;
      if(retryHeader!==null){
        const value=retryHeader.trim();
        if(/^\d+$/.test(value)){
          const seconds=Number(value);wait=Number.isSafeInteger(seconds)&&seconds<=Number.MAX_SAFE_INTEGER/1000?seconds*1000:Infinity;
        }else{
          const date=Date.parse(value);wait=Number.isFinite(date)?Math.max(0,date-Date.now()):Infinity;
        }
      }
      const readyAt=Date.now()+wait;
      retry.disabled=wait>0;
      if(!Number.isFinite(readyAt))retry.textContent=t('videoRetryLater');
      function unlock(){
        state.videoRetryTimer=null;
        if(!current())return;
        const remaining=readyAt-Date.now();
        if(remaining<=0)retry.disabled=false;
        else state.videoRetryTimer=setTimeout(unlock,Math.min(remaining,60000));
      }
      if(wait>0&&Number.isFinite(readyAt))state.videoRetryTimer=setTimeout(unlock,Math.min(wait,60000));
      retry.addEventListener('click',()=>{if(retry.disabled||!current())return;retry.disabled=true;retry.remove();void showPreparedVideo(item,epoch,viewerGeneration);});
      media.replaceChildren(retry);
    }
    const controller=new AbortController();state.controllers.add(controller);state.videoController=controller;
    const path=safeMediaURL(item.id,'playback');
    let response;
    try{
      response=await fetch(path,{method:'HEAD',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal});
    }catch(error){
      if(error.name!=='AbortError')offerRetry('videoUnavailable');
      return;
    }finally{state.controllers.delete(controller);if(state.videoController===controller)state.videoController=null;}
    if(!current())return;
    const contentType=(response.headers.get('content-type')||'').split(';',1)[0].trim().toLowerCase();
    const lengthText=response.headers.get('content-length')||'';
    const length=Number(lengthText);
    const validHeaders=response.status===200&&contentType==='video/mp4'&&
      response.headers.get('cache-control')==='no-store'&&response.headers.get('accept-ranges')==='bytes'&&
      !response.headers.has('content-range')&&(response.headers.get('content-encoding')||'identity')==='identity'&&
      /^"[a-f0-9]{64}"$/.test(response.headers.get('etag')||'')&&/^\d+$/.test(lengthText)&&
      Number.isSafeInteger(length)&&length>0&&length<=32*1024*1024*1024;
    if(!validHeaders){
      if(response.status===401||response.status===403){
        const error=new Error('Prepared playback denied');error.status=response.status;
        await failure(error,epoch);return;
      }
      offerRetry(response.status===404?'videoNotPrepared':response.status===409?'videoChanged':response.status===429?'videoBusy':'videoUnavailable',response.headers.get('retry-after'),response.status);
      return;
    }
    const video=document.createElement('video');video.controls=true;video.preload='metadata';video.playsInline=true;video.setAttribute('aria-label',assetLabel(item));
    const failedPlayback=()=>{
      if(!current())return;
      video.removeEventListener('error',failedPlayback);video.removeEventListener('abort',failedPlayback);
      video.pause();video.removeAttribute('src');video.load();video.remove();
      offerRetry('videoInterrupted');
    };
    video.addEventListener('error',failedPlayback);video.addEventListener('abort',failedPlayback);
    video.src=path;media.append(video);$('view-quality').textContent=t('preparedPlayback');
  }
  function updateFilmstrip(s){
    const strip=$('viewer-filmstrip');strip.setAttribute('aria-label',t('viewFilmstrip'));
    if(s.items.length<2){strip.replaceChildren();return;}
    // Same bounded window as the legacy strip (at most 11 thumbnails, so a long
    // page never fetches every preview). start is clamped so the window keeps its
    // width at the tail of the list instead of shrinking to as few as 6.
    const start=Math.max(0,Math.min(s.index-5,s.items.length-11));
    const end=Math.min(s.items.length,start+11);
    strip.replaceChildren(...s.items.slice(start,end).map((item,offset)=>{
      const index=start+offset,button=document.createElement('button');
      button.type='button';button.className='quiet';button.dataset.viewerIndex=String(index);button.disabled=s.busy;
      button.setAttribute('aria-label',`${t('viewFilmstripItem')} ${index+1} / ${s.items.length}`);
      button.setAttribute('aria-current',String(index===s.index));
      const image=document.createElement('img');image.alt='';image.loading='lazy';
      // Same URL the gallery grid already requested, so the HTTP cache serves it.
      image.src=safeMediaURL(item.id,'thumbnail');
      button.append(image);return button;
    }));
    if(!s.busy)strip.querySelector('[aria-current="true"]')?.scrollIntoView({block:'nearest',inline:'nearest'});
  }
  function updateSequence(){
    const s=sequenceState;
    $('viewer-sequence').hidden=s.items.length<2;
    $('view-position').textContent=s.items.length?`${t(s.origin==='album'?'viewAlbum':'viewPage')} · ${s.index+1} / ${s.items.length}`:'';
    $('view-previous').disabled=s.busy||s.index<=0;$('view-next').disabled=s.busy||s.index>=s.items.length-1;
    $('view-play').disabled=s.busy||!photoState.image?.naturalWidth||s.items.length<2||(!s.playing&&s.index>=s.items.length-1);
    $('view-play').textContent=t(s.playing?'viewPause':'viewPlay');$('view-play').setAttribute('aria-pressed',String(s.playing));
    $('viewer-sequence').title=t('viewSequenceHelp');
    updateFilmstrip(s);
  }
  function stopSlideshow(){clearTimeout(sequenceState.timer);sequenceState.timer=null;sequenceState.playing=false;updateSequence();}
  function scheduleSlideshow(){
    const s=sequenceState;clearTimeout(s.timer);s.timer=null;
    if(!s.playing||s.busy||!photoState.image?.naturalWidth||!$('viewer').open)return;
    if(s.index>=s.items.length-1){stopSlideshow();return;}
    const epoch=state.generation,viewer=state.viewerGeneration;
    const interval=Number($('view-interval').value);
    s.timer=setTimeout(()=>{if(stale(epoch)||viewer!==state.viewerGeneration)return;void movePhoto(1,true);},[5000,10000,15000].includes(interval)?interval:5000);
  }
  async function movePhoto(delta,automatic=false){
    const s=sequenceState;
    if(s.busy||state.locked||!$('viewer').open)return;
    if(document.hidden||state.busy||storyState.busy||storyState.dirty||!$('story-form').hidden||$('face-panel').open){stopSlideshow();if(automatic||state.busy||storyState.busy)return;}
    if(!automatic&&!abandonStory())return;
    const next=s.index+delta;
    if(next<0||next>=s.items.length){stopSlideshow();return;}
    const {items,origin}=s;
    await openAsset(items[next],{sequence:items,origin,advance:true,play:automatic&&s.playing});
  }
  async function openAsset(item,{sequence=[item],origin='single',advance=false,play=false}={}) {
    if(state.locked)return;
    const epoch=state.generation;
    closeViewer({keepFrame:advance});storyState.asset=item;storyState.page=1;
    sequenceState.items=sequence.slice();sequenceState.index=Math.max(0,sequence.findIndex(asset=>asset.id===item.id));sequenceState.origin=origin;sequenceState.busy=true;sequenceState.playing=play;updateSequence();
    const viewerGeneration=state.viewerGeneration;if(!$('viewer').open)$('viewer').showModal();$('viewer-title').textContent=assetLabel(item);
    $('photo-viewer').hidden=false;$('view-quality').textContent=t('loading');
    void loadStories();
    $('face-panel').hidden=state.profile?.memberships.find(member=>member.library_id===state.library&&member.available)?.role!=='owner';
    $('viewer-move').hidden=!transferCanManage();
    try {
      const detail=await request(libraryPath(`/assets/detail/${item.id}`,{upload_notes:'1'}),{epoch});
      if(stale(epoch)||viewerGeneration!==state.viewerGeneration||!$('viewer').open)return;
      storyState.asset=detail.asset;
      if(detail.asset.upload_notes_available===true)void loadViewerAnnotations();
      const captions=await request(libraryPath(`/assets/${item.id}/captions`),{epoch});
      if(stale(epoch)||viewerGeneration!==state.viewerGeneration||!$('viewer').open)return;
      storyState.asset=detail.asset;$('viewer-title').textContent=assetLabel(detail.asset);
      if(detail.asset.kind==='video') {
        await showPreparedVideo(detail.asset,epoch,viewerGeneration);
        if(stale(epoch)||viewerGeneration!==state.viewerGeneration||!$('viewer').open)return;
      }
      else {
        const url=await previewURL(item.id,epoch);
        if(stale(epoch)||viewerGeneration!==state.viewerGeneration||!$('viewer').open)return;
        showPhoto(detail.asset,url);
      }
      if(detail.originals_allowed) { $('original').href=safeMediaURL(item.id,'media',{download:'true'});$('original').hidden=false; }
      if(!captions.items.length) {
        const p=document.createElement('p');p.textContent=t('noCaptions');$('captions').append(p);
        // A member may describe a photo that has none. The route refuses an asset that already
        // has a caption, so the control is offered only where it can actually succeed.
        const form=document.createElement('form');form.className='caption-form';
        const label=document.createElement('label');label.htmlFor='caption-text';label.textContent=t('describePhoto');
        const input=document.createElement('input');input.id='caption-text';input.maxLength=1024;input.autocomplete='off';
        const button=document.createElement('button');button.type='submit';button.className='primary';button.textContent=t('saveCaption');
        form.append(label,input,button);
        const status=document.createElement('p');status.className='fine';status.setAttribute('role','status');
        form.addEventListener('submit',async event=>{
          event.preventDefault();
          const text=input.value.trim();
          if(!text||state.busy||state.locked)return;
          state.busy=true;button.disabled=true;
          try{
            const saved=await request(libraryPath(`/assets/${item.id}/captions`),{method:'POST',epoch,body:{text}});
            if(stale(epoch)||viewerGeneration!==state.viewerGeneration)return;
            // Show what was saved without reopening the viewer: the route allows one write per
            // photo, so there is nothing left to submit and the form is replaced in place.
            const written=document.createElement('small');written.textContent=t('edited');
            const written_text=document.createElement('p');written_text.textContent=saved.caption.text;
            p.remove();
            form.replaceWith(written,written_text);
            status.textContent=t('captionSaved');
          }catch(error){status.textContent=t(errorStatus(error));}
          finally{state.busy=false;button.disabled=false;}
        });
        $('captions').append(form,status);
      }
      for(const caption of captions.items) {
        const label=document.createElement('small');label.textContent=t(caption.user_edited?'edited':'generated');
        const p=document.createElement('p');p.textContent=caption.text;
        $('captions').append(label,p);
        if(caption.truncated) {const small=document.createElement('small');small.textContent=t('truncated');$('captions').append(small);}
      }
      if(captions.has_more) {const p=document.createElement('p');p.textContent=t('moreCaptions');$('captions').append(p);}
      return true;
    } catch(error) {
      if(viewerGeneration===state.viewerGeneration&&!stale(epoch)){
        stopSlideshow();$('view-quality').textContent=t(errorStatus(error));
      }
      await failure(error,epoch);return false;
    }
    finally{if(!stale(epoch)&&viewerGeneration===state.viewerGeneration){sequenceState.busy=false;updateSequence();scheduleSlideshow();}}
  }
  function storyButton(label, action){const button=document.createElement('button');button.type='button';button.className='quiet';button.textContent=t(label);button.addEventListener('click',action);return button;}
  function storyText(container, title, text){
    if(title){const heading=document.createElement('h4');heading.textContent=title;container.append(heading);}
    const paragraph=document.createElement('p');paragraph.className='story-text';paragraph.textContent=text;container.append(paragraph);
  }
  function defaultStoryByline(){
    // Use the current chosen display name only. Server-bound author identity is separate.
    const name=state.profile?.display_name;
    if(typeof name!=='string'||!name.trim()||new TextEncoder().encode(name).length>256||
      /[\u0000-\u001f\u007f-\u009f\ud800-\udfff]/u.test(name))return '';
    return name;
  }
  function editStory(story=null, content=null){
    stopSlideshow();
    if(!abandonStory())return;
    resetStoryEditor();storyState.editing=story;
    const value=content||story||{title:'',byline:defaultStoryByline(),text:'',language:state.language};
    for(const key of ['title','byline','text','language'])$('story-'+key).value=value[key];
    $('story-form').hidden=false;storyState.dirty=Boolean(content);storyStatus('');$('story-text').focus();
  }
  async function loadStories(append=false){
    const asset=storyState.asset;if(!asset||(append&&storyState.loading))return;
    const page=append?storyState.page+1:storyState.page;
    const epoch=state.generation, viewer=state.viewerGeneration, load=++storyState.load;
    storyState.loading=true;$('story-more').disabled=true;storyStatus('storyLoading');
    try{
      const result=await request(libraryPath(`/assets/${asset.id}/stories`,{page:String(page)}),{epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration||load!==storyState.load)return;
      storyState.page=page;
      if(!append)$('story-list').replaceChildren();
      if(!result.items.length&&!append){const p=document.createElement('p');p.className='story-empty';p.textContent=t('storyEmpty');$('story-list').append(p);}
      for(const story of result.items){
        const article=document.createElement('article');article.className='story-card';
        storyText(article,story.title,story.text);
        const byline=document.createElement('small');byline.title=t('unverifiedByline');
        byline.textContent=`${story.byline||t('familyMember')} · ${story.author_id===state.profile.account_id?t('you'):story.author_id.slice(0,8)} · ${new Date(story.updated_at*1000).toLocaleString(state.language==='zh'?'zh-CN':'en')} · ${t('revision')} ${story.revision}`;article.append(byline);
        const actions=document.createElement('div');actions.className='story-actions';
        if(story.can_edit){actions.append(storyButton('editStory',()=>editStory(story)),storyButton('deleteStory',()=>{void removeStory(story);}));}
        if(story.can_view_history)actions.append(storyButton('history',()=>{void showStoryHistory(story);}));
        article.append(actions);$('story-list').append(article);
      }
      $('story-add').hidden=!result.can_create;$('story-more').hidden=!result.has_more;storyStatus('');
    }catch(error){if(stale(epoch)||viewer!==state.viewerGeneration||load!==storyState.load)return;storyStatus('storyError');if(error.status===401||error.status===403)await failure(error,epoch);}
    finally{if(!stale(epoch)&&viewer===state.viewerGeneration&&load===storyState.load){storyState.loading=false;$('story-more').disabled=false;}}
  }
  async function saveStory(event){
    event.preventDefault();if(storyState.busy||!storyState.asset)return;
    const epoch=state.generation,viewer=state.viewerGeneration;
    const body=Object.fromEntries(['title','byline','text','language'].map(key=>[key,$('story-'+key).value]));
    if(new TextEncoder().encode(body.text).length>65536||new TextEncoder().encode(body.title).length>512||new TextEncoder().encode(body.byline).length>256||!body.text.trim()){storyStatus('storyInvalid');return;}
    if(storyState.editing)body.revision=String(storyState.editing.revision);
    const fingerprint=JSON.stringify(body);
    if(!storyState.pending||storyState.pending.fingerprint!==fingerprint)storyState.pending={fingerprint,id:crypto.randomUUID()};
    body.mutation_id=storyState.pending.id;
    const path=storyState.editing?`/stories/${storyState.editing.id}`:`/assets/${storyState.asset.id}/stories`;
    storyState.busy=true;lockStoryInputs(true);$('story-save').disabled=true;$('story-cancel').disabled=true;storyStatus('working');
    try{
      const result=await request(libraryPath(path),{method:storyState.editing?'PUT':'POST',body,epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration)return;
      const newer=result.revision>(body.revision?Number(body.revision)+1:1);
      resetStoryEditor();storyState.page=1;await loadStories();storyStatus(newer?'storyCurrent':'savedStory');
    }catch(error){
      if(stale(epoch)||viewer!==state.viewerGeneration)return;
      if(error.status===401||error.status===403){await failure(error,epoch);return;}
      const conflict=error.status===409,invalid=error.status===400||error.status===413||error.status===422;
      storyStatus(conflict?'storyConflict':invalid?'storyInvalid':'storySaveError');
      $('story-compare').hidden=!conflict||!storyState.editing;
      // Ambiguous delivery: retain the mutation ID and freeze content for an exact retry.
      lockStoryInputs(!conflict&&!invalid);
    }finally{storyState.busy=false;$('story-save').disabled=false;$('story-cancel').disabled=false;}
  }
  async function showStoryHistory(story,page=1,append=false){
    const epoch=state.generation,viewer=state.viewerGeneration,history=++storyState.history;
    try{
      const result=await request(libraryPath(`/stories/${story.id}/history`,{page:String(page)}),{epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration||history!==storyState.history)return;
      const root=$('story-history');if(!append)root.replaceChildren();root.hidden=false;
      if(!append){const h=document.createElement('h4');h.textContent=t('historyTitle');root.append(h);}
      for(const version of result.items){const article=document.createElement('article');article.className='story-card';const label=document.createElement('small');label.textContent=`${t('revision')} ${version.revision} · ${new Date(version.occurred_at*1000).toLocaleString()}${version.deleted?' · '+t('removedStory'):''}`;article.append(label);storyText(article,version.title,version.text);
        if(!result.story.deleted)article.append(storyButton('restoreDraft',()=>editStory(result.story,version)));root.append(article);}
      if(result.has_more){const more=storyButton('moreStories',()=>{more.remove();void showStoryHistory(story,page+1,true);});root.append(more);}
    }catch(error){if(!stale(epoch)&&viewer===state.viewerGeneration&&history===storyState.history){storyStatus('storyError');await failure(error,epoch);}}
  }
  async function compareStory(){
    if(!storyState.editing||storyState.busy)return;
    const epoch=state.generation,viewer=state.viewerGeneration,id=storyState.editing.id;
    try{
      const result=await request(libraryPath(`/stories/${id}/history`),{epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration||storyState.editing?.id!==id)return;
      const root=$('story-conflict');root.replaceChildren();storyText(root,result.story.title,result.story.text);
      if(!result.story.deleted)root.append(storyButton('keepDraft',()=>{
        if(storyState.busy||storyState.editing?.id!==id||!window.confirm(t('confirmDraft')))return;
        storyState.editing=result.story;storyState.pending=null;root.replaceChildren();$('story-compare').hidden=true;lockStoryInputs(false);storyStatus('');
      }));
    }catch(error){await failure(error,epoch);}
  }
  async function removeStory(story){
    if(storyState.busy||!abandonStory()||!window.confirm(t('confirmDelete')))return;
    const epoch=state.generation,viewer=state.viewerGeneration;
    const key=`${story.id}:${story.revision}`;
    if(!storyState.deletes.has(key))storyState.deletes.set(key,{revision:String(story.revision),mutation_id:crypto.randomUUID()});
    storyState.busy=true;
    try{
      await request(libraryPath(`/stories/${story.id}`),{method:'DELETE',body:storyState.deletes.get(key),epoch});
      if(stale(epoch)||viewer!==state.viewerGeneration)return;
      storyState.deletes.delete(key);resetStoryEditor();storyState.page=1;await loadStories();storyStatus('removedStory');
      // Retain an explicit route to the restricted history until this viewer closes.
      $('story-history').replaceChildren(storyButton('history',()=>{void showStoryHistory(story);}));$('story-history').hidden=false;
    }catch(error){if(!stale(epoch)&&viewer===state.viewerGeneration){if(error.status===409)storyState.deletes.delete(key);storyStatus(error.status===409?'storyConflict':'storyDeleteError');await failure(error,epoch);}}
    finally{storyState.busy=false;}
  }
  function catalogueItem(id){return state.catalogue?.items?.find(item=>String(item.id)===String(id));}
  function availableLibraries(profile){
    // Stable ID, not translated title or alphabetical response order. This only
    // prioritizes memberships the server has already marked accessible.
    return profile.memberships.filter(m=>m.available===true)
      .sort((a,b)=>Number(b.library_id==='family')-Number(a.library_id==='family'));
  }
  function libraryTitle(id){const item=catalogueItem(id);return state.language==='zh'&&item?.title_zh?item.title_zh:(item?.title||String(id));}
  function transferCanManage(){return Boolean(catalogueItem(state.library)?.can_manage);}
  function updateTransferUI(){
    const count=transferState.selected.size, allowed=transferCanManage()&&transferState.canMove!==false;
    $('library-transfer').hidden=!allowed;
    $('transfer-count').textContent=count?`${count} / 50 ${t('assetsCount')}`:'';
    $('transfer-move').disabled=!count||count>50||transferState.busy;
    $('transfer-clear').disabled=!count||transferState.busy;
    document.querySelectorAll('[data-transfer-id]').forEach(input=>{input.checked=transferState.selected.has(String(input.dataset.transferId));input.disabled=transferState.busy;});
  }
  function addTransferCheckbox(card,item){
    if(!transferCanManage())return card;
    const container=document.createElement('div');container.className='asset-choice';container.append(card);
    const wrap=document.createElement('span');wrap.className='asset-select';
    const input=document.createElement('input');input.type='checkbox';input.dataset.transferId=String(item.id);input.checked=transferState.selected.has(String(item.id));input.setAttribute('aria-label',`${t('moveThisMemory')}: ${assetLabel(item)}`);
    input.addEventListener('click',event=>event.stopPropagation());
    input.addEventListener('change',event=>{event.stopPropagation();const id=String(item.id);if(input.checked){if(transferState.selected.size>=50){input.checked=false;$('transfer-status').textContent=t('moveLimit');return;}transferState.selected.set(id,item);}else transferState.selected.delete(id);updateTransferUI();});
    wrap.append(input);container.append(wrap);return container;
  }
  function clearTransferSelection(){transferState.selected.clear();updateTransferUI();}
  async function loadLibraryCatalogue(epoch=state.generation){
    try{
      const result=await request('/library-catalogue',{epoch});if(stale(epoch))return null;
      state.catalogue=result;
      $('library-select').replaceChildren();
      for(const member of availableLibraries(state.profile)){
        const option=document.createElement('option');option.value=member.library_id;option.textContent=libraryTitle(member.library_id);$('library-select').append(option);
      }
      $('library-select').value=state.library||'';updateTransferUI();return result;
    }catch(error){
      if(stale(epoch)||error.name==='AbortError'||error.status===401||error.status===403)throw error;
      state.catalogue=null;updateTransferUI();return null;
    }
  }
  async function loadTransferAvailability(epoch=state.generation){
    if(!state.library||!transferCanManage()){transferState.canMove=false;updateTransferUI();return;}
    const source=state.library,load=++transferState.load;transferState.canMove=null;
    try{const result=await request(`/admin/library-transfers?library=${encodeURIComponent(source)}`,{epoch});if(stale(epoch)||source!==state.library||load!==transferState.load)return;transferState.canMove=result.can_move!==false;updateTransferUI();}catch(error){if(!stale(epoch)&&source===state.library){transferState.canMove=error.status===403?false:null;updateTransferUI();}}
  }
  async function openTransferReview(ids=Array.from(transferState.selected.keys())){
    if(!transferCanManage()||transferState.busy||!abandonStory())return;
    if(!ids.length||ids.length>50){$('transfer-status').textContent=t(ids.length?'moveLimit':'moveNone');return;}
    const destinationOptions=(state.catalogue?.items||[]).filter(item=>item.can_manage&&String(item.id)!==String(state.library));
    if(!destinationOptions.length){$('transfer-status').textContent=t('moveUnavailable');return;}
    transferState.review=null;
    const epoch=state.generation,source=state.library;
    const choice=document.createElement('select');choice.id='transfer-destination';choice.setAttribute('aria-label',t('chooseDestination'));
    for(const item of destinationOptions){const option=document.createElement('option');option.value=item.id;option.textContent=libraryTitle(item.id);choice.append(option);}
    const form=document.createElement('label');form.className='transfer-destination';form.textContent=t('chooseDestination');form.append(choice);$('transfer-review-copy').replaceChildren(form);
    $('transfer-review-confirm').disabled=true;$('transfer-review').showModal();
    async function reviewDestination(){
      const load=++transferState.load,destination=String(choice.value);
      transferState.review=null;$('transfer-review-confirm').disabled=true;$('transfer-review-status').textContent=t('loading');
      $('transfer-review-summary').textContent=`${ids.length} ${t('assetsCount')} · ${libraryTitle(source)} → ${libraryTitle(destination)}`;
      const current=()=>!stale(epoch)&&source===state.library&&load===transferState.load&&$('transfer-review').open&&destination===String(choice.value);
      try{
        const result=await request(`/admin/library-transfers/review?library=${encodeURIComponent(source)}`,{method:'POST',body:{asset_ids:ids.join(','),destination},epoch});
        if(!current())return;
        transferState.review={...result,ids:ids.slice(),source,destination};
        const facts=document.createElement('p');facts.textContent=`${result.asset_count} ${t('assetsCount')} · ${result.story_count} ${t('storiesCount')} · ${result.affected_album_count} ${t('albumsCount')}`;
        const audience=document.createElement('p');audience.textContent=`${result.current_readers} ${t('readersCount')} · ${result.current_original_readers} ${t('originalReadersCount')}`;
        const notes=document.createElement('div');notes.className='transfer-notes';
        for(const key of ['moveStories','moveAlbums','moveFaces','moveReaders']){const p=document.createElement('p');p.textContent=t(key);notes.append(p);}
        $('transfer-review-summary').append(facts,audience,notes);$('transfer-review-status').textContent='';$('transfer-review-confirm').disabled=false;
      }catch(error){if(current()){$('transfer-review-status').textContent=t(error.status===401||error.status===403?'moveUnavailable':error.status===409?'conflict':(!error.status||error.status>=500)?'moveUncertain':'moveFailed')+(Number.isInteger(error.status)?` (HTTP ${error.status})`:'');}}
    }
    choice.addEventListener('change',()=>void reviewDestination());
    await reviewDestination();
  }
  async function confirmTransfer(){
    const review=transferState.review,choice=$('transfer-destination');
    if(!review||transferState.busy||review.source!==state.library||review.destination!==choice?.value)return;
    transferState.busy=true;choice.disabled=true;$('transfer-review-confirm').disabled=true;
    const epoch=state.generation,source=state.library;
    try{
      await request(`/admin/library-transfers/confirm?library=${encodeURIComponent(source)}`,{method:'POST',body:{plan:review.plan},epoch});
      if(stale(epoch)||source!==state.library)return;
      transferState.selected.clear();transferState.review=null;$('transfer-review').close();closeViewer();state.page=1;
      // The confirm response is the commit boundary. A later catalogue/gallery refresh may
      // fail because the session or a concurrent navigation changed, but must not turn a
      // completed move into a failure message.
      $('transfer-status').textContent=t('moveSuccess');
      discoveryState.binding=null;discoveryState.fingerprint=null;discoveryState.page=1;state.page=1;discoveryState.searchLoad++;discoveryState.facetLoad++;
      let refreshed=true;
      try{await loadLibraryCatalogue(epoch);if(state.library===source&&!state.locked)refreshed=await loadGallery()!==false;}catch(error){refreshed=false;}
      // loadGallery intentionally invalidates the request generation and clearPhotos clears
      // transient transfer text, so write the final post-commit status after the refresh.
      if(state.library===source&&!state.locked)$('transfer-status').textContent=t(refreshed?'moveSuccess':'moveRefreshFailed');
    }catch(error){
      if(!stale(epoch)){
        $('transfer-review-status').textContent=t(error.status===409?'conflict':error.status===401||error.status===403?'moveUnavailable':(!error.status||error.status>=500)?'moveUncertain':'moveFailed')+(Number.isInteger(error.status)?` (HTTP ${error.status})`:'');
        if(error.status===409||error.status===401||error.status===403)transferState.review=null;
        else $('transfer-review-confirm').disabled=false;
      }
    }finally{transferState.busy=false;if(choice)choice.disabled=false;updateTransferUI();}
  }
  function renderGalleryItems(items,isCurrent,origin='page') {
    storyWorkspace?.setItems(items);
    for(const item of items) {
      const card=document.createElement('button');card.type='button';card.className='asset';card.dataset.assetId=item.id;
      const image=document.createElement('img');image.loading='lazy';image.alt=assetLabel(item);
      image.src=safeMediaURL(item.id,'thumbnail');image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
      const label=document.createElement('span');label.textContent=assetLabel(item);card.append(image,label);
      if(item.match){const excerpt=document.createElement('span');excerpt.className='search-excerpt';excerpt.textContent=t(item.match.source==='family'?'matchedFamily':item.match.source==='ai'?'matchedAI':'matchedLegacy')+' · '+item.match.excerpt;card.append(excerpt);}
      card.addEventListener('click',()=>{if(!isCurrent()||state.locked||state.busy||(discoveryState.active&&!abandonStory()))return;void openAsset(item,{sequence:items,origin});});
      $('grid').append(addTransferCheckbox(card,item));
    }
  }
  function renderDiscoverySummary(message='',{retry=false}={}) {
    const active=discoveryState.active;$('gallery-filter-summary').hidden=!active;
    $('gallery-filter-chips').replaceChildren();$('gallery-filter-actions').replaceChildren();
    if(!active){$('gallery-filter-count').textContent='';$('gallery-filter-status').textContent='';return;}
    const token=discoveryState.modeToken,owner={account:String(state.profile?.account_id||''),library:String(state.library||'')},ticket=galleryLoad,page=discoveryState.page;
    const current=()=>discoveryState.active&&discoveryState.modeToken===token&&ticket===galleryLoad&&page===discoveryState.page&&page===state.page&&owner.account===String(state.profile?.account_id||'')&&owner.library===String(state.library||'');
    const clear=document.createElement('button');clear.type='button';clear.className='quiet';clear.textContent=t('clearFilter');clear.addEventListener('click',()=>{if(current())clearGalleryFilters();});$('gallery-filter-actions').append(clear);
    if(retry){const retryButton=document.createElement('button');retryButton.type='button';retryButton.className='quiet';retryButton.textContent=t('discoveryRetry');retryButton.addEventListener('click',()=>{if(!current()||!abandonStory())return;if(discoveryState.binding)void loadDiscovery();else void openDiscovery().then(ready=>{if(ready&&discoveryState.active&&discoveryState.modeToken===token&&owner.account===String(state.profile?.account_id||'')&&owner.library===String(state.library||''))void loadDiscovery();});});$('gallery-filter-actions').append(retryButton);}
    const filters=discoveryState.appliedFilters||{};
    const chips=[];
    for(const location of filters.locations||[])chips.push(discoveryState.appliedLocationLabels.get(String(location))||String(location));
    for(const media of filters.media||[])chips.push(t(media==='video'?'mediaVideo':'mediaImage'));
    if(filters.date?.from||filters.date?.to)chips.push(`${filters.date.from?`${t('dateFrom')} ${filters.date.from}`:''}${filters.date.from&&filters.date.to?' – ':''}${filters.date.to?`${t('dateTo')} ${filters.date.to}`:''}`);
    for(const value of chips){const chip=document.createElement('span');chip.className='gallery-filter-chip';chip.textContent=value;$('gallery-filter-chips').append(chip);}
    $('gallery-filter-count').textContent=Number.isInteger(discoveryState.total)?t('discoveryResults')(discoveryState.total):'';
    $('gallery-filter-status').textContent=message;
  }
  function clearDiscoveryMode({clearInputs=false,clearBinding=false}={}) {
    discoveryState.searchLoad++;galleryLoad++;discoveryState.modeToken++;discoveryState.active=false;discoveryState.applied=false;discoveryState.appliedFilters=null;
    discoveryState.appliedLocationLabels.clear();discoveryState.fingerprint=null;discoveryState.page=1;discoveryState.total=0;
    if(clearBinding){discoveryState.binding=null;discoveryState.owner=null;discoveryState.facetLoad++;}
    if(clearInputs){$('discovery-media').value='all';$('discovery-from').value='';$('discovery-to').value='';discoveryState.selectedPlaces.clear();discoveryState.selectedPlaceLabels.clear();renderSelectedPlaces();}
    $('discovery-status').textContent='';renderDiscoverySummary();
  }
  function clearGalleryFilters(){
    if(state.busy||state.locked||!abandonStory())return;
    clearDiscoveryMode({clearInputs:true});storyState.search=null;$('search-text').value='';state.page=1;void loadGallery();
  }
  async function loadGallery({refreshDiscovery=false}={}) {
    if(!state.library||state.locked)return;
    if(discoveryState.active&&(discoveryState.owner?.library!==String(state.library)||discoveryState.owner?.account!==String(state.profile?.account_id)))clearDiscoveryMode({clearInputs:true,clearBinding:true});
    if(discoveryState.active){
      if(refreshDiscovery||!discoveryState.binding){discoveryState.page=1;state.page=1;const ready=await openDiscovery();if(!ready||!discoveryState.binding){if(!discoveryState.active)return loadGallery();return false;}}
      return loadDiscovery();
    }
    const ticket=++galleryLoad,epoch=invalidate(),library=String(state.library);status('loading');
    try {
      const result=storyState.search ? await request(libraryPath('/library/search'),{method:'POST',body:{...storyState.search,page:String(state.page),media:'all'},epoch}) : await request(libraryPath('/assets',{page:String(state.page),page_size:'24'}),{epoch});
      if(stale(epoch)||ticket!==galleryLoad||discoveryState.active||library!==String(state.library))return false;
      state.total=result.total;$('grid').replaceChildren();renderGalleryItems(result.items,()=>!stale(epoch)&&ticket===galleryLoad&&!discoveryState.active&&library===String(state.library));
      $('empty').hidden=result.items.length>0;$('empty').textContent=t(storyState.search?'noMatches':'noPhotos');$('gallery-filter-summary').hidden=true;
      updateTransferUI();void loadTransferAvailability(epoch);
      const pages=Math.max(1,Math.ceil(result.total/24));$('pagination').hidden=result.total===0;$('previous').disabled=state.page===1;$('next').disabled=state.page>=pages;
      $('page-input').max=String(pages);$('page-input').value=String(state.page);$('page-label').textContent=`${t('page')} ${state.page} ${t('of')} ${pages} · ${result.total} ${t('photos')}`;status('');
      if(!$('members-panel').hidden&&$('members-panel').open)void loadMembers();if(!$('uploads-panel').hidden&&$('uploads-panel').open)void loadUploads();if(!$('tag-review-panel').hidden&&$('tag-review-panel').open)void loadProposedTags();
      if($('directory-panel').open)void loadDirectory();if($('tags-panel').open)void loadTags();if($('duplicates-panel').open)void loadDuplicates();if($('family-tags-panel').open)void loadFamilyTags();
      // Probe once per library; only an opted-in deployment exposes structured discovery.
      if(!discoveryState.binding)void openDiscovery();if(!$('people-panel').hidden&&$('people-panel').open)void loadPeople();
      $('album-create').hidden=state.profile?.memberships.find(m=>m.library_id===state.library&&m.available)?.role!=='owner';if($('albums-panel').open)void loadAlbums();
      if(albumState.draft){if(albumState.draft.library===state.library&&albumState.draft.account===state.profile?.account_id&&!$('album-create').hidden)editAlbum(null,albumState.draft);else albumState.draft=null;}
      return true;
    } catch(error) {if(ticket===galleryLoad&&!discoveryState.active)await failure(error,epoch);return false;}
  }
  async function restore(load=true) {
    const epoch=invalidate();
    try {
      const profile=await request('/auth/session',{epoch});
      if(stale(epoch))return;
      state.sessionCheckFailed=false;
      const previousAccount=state.profile?.account_id;
      if(previousAccount&&previousAccount!==profile.account_id)clearAssistantRecoveryPointer();
      let recovery=readAssistantRecoveryPointer();
      if(recovery&&recovery.account_id!==profile.account_id){clearAssistantRecoveryPointer(recovery.request_id);recovery=null;}
      if(previousAccount!==profile.account_id){assistantState.transcribe=false;assistantState.speech=false;resetAssistant();assistantState.binding=null;state.library=null;}
      if(state.profile?.account_id!==profile.account_id){peopleState.page=1;peopleState.query='';$('people-query').value='';directoryState.page=1;directoryState.query='';$('directory-query').value='';tagState.page=1;tagState.query='';tagState.tag=null;tagState.open=null;$('tag-query').value='';$('tag-assets').replaceChildren();familyTagState.page=1;familyTagState.query='';familyTagState.tag=null;$('family-tag-query').value='';$('family-tag-assets').replaceChildren();uploadState.page=1;}
      state.profile=profile;state.csrf=profile.csrf_token;state.locked=false;
      $('auth').hidden=true;$('library').hidden=false;$('account-label').textContent=profile.phone_login;
      const available=availableLibraries(profile);
      $('my-uploads-open').hidden=$('my-uploads-panel').hidden=!available.length;
      if(recovery&&!available.some(m=>m.library_id===recovery.library_id)){clearAssistantRecoveryPointer(recovery.request_id);recovery=null;}
      if(!available.some(m=>m.library_id===state.library)){state.library=recovery&&recovery.account_id===profile.account_id&&available.some(m=>m.library_id===recovery.library_id)?recovery.library_id:available[0]?.library_id||null;state.page=1;state.memberPage=1;}
      $('library-select').replaceChildren();for(const member of available){const option=document.createElement('option');option.value=member.library_id;option.textContent=member.library_id;$('library-select').append(option);}
      await loadLibraryCatalogue(epoch);
      if(state.catalogue?.items?.length&&!state.catalogue.items.some(item=>String(item.id)===String(state.library))){state.library=available.find(member=>state.catalogue.items.some(item=>String(item.id)===member.library_id))?.library_id||null;state.page=1;}
      $('library-select').value=state.library||'';
      const isOwner=available.some(m=>m.library_id===state.library&&m.role==='owner');
      $('owner-panel').hidden=!isOwner;$('uploads-panel').hidden=!isOwner;$('uploads-open').hidden=!isOwner;$('tag-review-panel').hidden=!isOwner;
      $('members-panel').hidden=$('owner-panel').hidden;
      $('people-panel').hidden=$('owner-panel').hidden;
      if(!state.library) {$('empty').hidden=false;$('empty').textContent=t('noLibrary');assistantState.transcribe=false;assistantState.speech=false;$('assistant-form').hidden=true;$('assistant-voice').hidden=true;$('assistant-status').textContent=t('assistantUnavailable');status('');}
      else {
        await loadAssistantCapabilities(epoch);if(stale(epoch))return;
        if(load)await loadGallery({refreshDiscovery:true});
        if(state.profile?.account_id!==profile.account_id)return;
        presentAssistantRecovery(state.generation,available);
      }
      return true;
    } catch(error) {
      if(error.name==='AbortError'||stale(epoch))return;
      state.sessionCheckFailed=error.status!==401;
      if(error.status===401) {showAuth();status('');}
      else {showAuth();status(errorStatus(error));}
    }
  }
  function setMode(mode) {
    if(state.busy)return;state.mode=mode;
    $('login-tab').setAttribute('aria-pressed',String(mode==='login'));
    $('register-tab').setAttribute('aria-pressed',String(mode==='register'));
    $('registration-fields').hidden=mode!=='register';$('code').required=mode==='register';$('name').required=mode==='register';
    $('password').autocomplete=mode==='register'?'new-password':'current-password';
    $('password').minLength=mode==='register'?8:1;$('password').value='';$('code').value='';status('');translate();
  }
  // UI convenience only: transport and stored identities remain explicit E.164.
  function phoneForRequest(value) {
    const compact=value.replace(/[ ()-]/g,'');
    if(/^\+[1-9][0-9]{7,14}$/.test(compact))return compact;
    if(/^[0-9]{11}$/.test(compact))return '+86'+compact;
    return null;
  }
  Object.assign(words.en, {phoneHelp:'China (+86) is the default. For another country, enter + and its country code.',invalidPhone:'Enter an 11-digit number, or a full international number starting with +.'});
  Object.assign(words.zh, {phoneHelp:'默认中国区号 +86，无需输入。其他国家请填写以 + 和国家区号开头的完整号码。',invalidPhone:'请输入 11 位号码，或以 + 和国家区号开头的完整号码。'});
  Object.assign(words.en, {invalidCode:'Enter the invitation code sent by your library owner.',enterPassword:'Enter your password.'});
  Object.assign(words.zh, {invalidCode:'请输入相册主人发给你的邀请码。',enterPassword:'请输入密码。'});
  async function signIn(event) {
    event.preventDefault();if(state.busy)return;
    status('');
    const phone=phoneForRequest($('phone').value),password=$('password').value;
    if(!phone) {status('invalidPhone');return;}
    if(state.mode==='register'&&(Array.from(password).length<8||Array.from(password).length>128)){status('invalidPassword');return;}
    // The name is required at registration: it is how the family recognises a member, and it
    // is the source of that member's incoming upload folder label.
    if(state.mode==='register'&&!$('name').value.trim()){status('invalidName');return;}
    state.busy=true;$('auth-submit').disabled=true;translate();const epoch=invalidate();
    const body={phone,password,transport:'web'};
    if(state.mode==='register'){body.code=$('code').value;body.name=$('name').value.trim();}
    try {
      // A failed session check may have left a valid HttpOnly cookie in the browser.
      // Confirm that state before sending a password: the server deliberately rejects
      // login requests which already carry a session cookie.
      if(state.sessionCheckFailed){
        try {await request('/auth/session',{epoch});$('password').value='';await restore();return;}
        catch(error){if(error.status!==401)throw error;state.sessionCheckFailed=false;}
      }
      await request('/auth/'+state.mode,{method:'POST',body,epoch});
      if(!stale(epoch)) {$('password').value='';$('code').value='';$('name').value='';await restore();}
    } catch(error) {if(error.name!=='AbortError'&&!stale(epoch))status(errorStatus(error));}
    finally {state.busy=false;$('auth-submit').disabled=false;translate();}
  }
  async function signOut() {
    if(!abandonStory())return;storyState.suspended=null;storyState.search=null;
    if(state.busy)return;clearAssistantRecoveryPointer();state.busy=true;state.locked=true;const epoch=invalidate();status('working');
    try {
      await request('/auth/logout',{method:'POST',epoch});
      if(!stale(epoch)){showAuth();status('signedOut');channel?.postMessage('session-changed');}
    } catch(error) {if(error.name!=='AbortError'&&!stale(epoch))status('logoutFailed');}
    finally {state.busy=false;}
  }
  async function invite(event) {
    event.preventDefault();if(state.busy||state.locked)return;
    const phone=phoneForRequest($('invite-phone').value);
    if(!phone){status('invalidPhone');return;}
    state.busy=true;const epoch=state.generation;
    const library=state.library;
    try {
      const result=await request(`/libraries/${encodeURIComponent(library)}/invitations`,{method:'POST',body:{phone},epoch});
      state.invite={code:result.code,library};$('created-code').value=result.code;$('invitation-result').hidden=false;status('');
    } catch(error){await failure(error,epoch);}finally{state.busy=false;}
  }
  async function cancelInvite() {
    if(state.busy||state.locked||!state.invite)return;state.busy=true;const epoch=state.generation;
    try {
      await request(`/libraries/${encodeURIComponent(state.invite.library)}/invitations/cancel`,{method:'POST',body:{code:state.invite.code},epoch});
      $('created-code').value='';$('invitation-result').hidden=true;state.invite=null;status('cancelled');
    } catch(error){await failure(error,epoch);}finally{state.busy=false;}
  }
  async function accept(event) {
    event.preventDefault();if(state.busy||state.locked)return;state.busy=true;const epoch=state.generation;
    try {await request('/auth/invitations/accept',{method:'POST',body:{code:$('accept-code').value},epoch});await restore();status('accepted');}
    catch(error){await failure(error,epoch);}finally{state.busy=false;}
  }
  function currentLibraryName(){
    const membership=state.profile?.memberships?.find(item=>item.library_id===state.library);
    return String(membership?.name||membership?.title||membership?.library_name||$('library-select').selectedOptions[0]?.textContent||state.library||'this library');
  }
  function uploadErrorKey(error){
    if(error?.status===503)return 'uploadRestricted';
    if(error?.status===401||error?.status===403)return 'denied';
    return 'uploadReviewError';
  }
  function safeUploadPreviewURL(value,itemId){
    if(typeof value!=='string'||!value)return null;
    try{const url=new URL(value,window.location.origin);const expected=`/admin/uploads/${encodeURIComponent(String(itemId))}/preview`;return url.origin===window.location.origin&&url.pathname===expected&&url.searchParams.get('library')===state.library?url.href:null;}catch{return null;}
  }
  function enqueueUploadPreview(container,image,url){
    const queue=uploadState.previewQueue,token=queue.token;
    // A page contains at most ten cards; keep one small confirmation slot and
    // refuse anything beyond that bounded surface rather than accumulating work.
    if(queue.pending.length>=11){image.dispatchEvent(new Event('error'));return;}
    queue.pending.push({container,image,url,token});
    queueMicrotask(()=>void drainUploadPreviewQueue());
  }
  async function drainUploadPreviewQueue(){
    const queue=uploadState.previewQueue;if(queue.active)return;queue.active=true;
    try{while(queue.pending.length){
      const job=queue.pending.shift();
      if(job.token!==queue.token||!job.container.isConnected||!job.image.isConnected)continue;
      await new Promise(resolve=>{
        let done=false;const finish=()=>{if(done)return;done=true;clearTimeout(timer);job.image.onload=null;job.image.onerror=null;queue.cancel=null;resolve();};
        const timer=setTimeout(()=>{job.image.dispatchEvent(new Event('error'));finish();},30000);
        queue.cancel=()=>{finish();job.image.removeAttribute('src');};
        job.image.onload=finish;job.image.onerror=finish;job.image.src=job.url;
      });
    }}finally{queue.active=false;if(queue.pending.length)void drainUploadPreviewQueue();}
  }
  function renderUploadPreview(container,item){
    container.replaceChildren();
    if(item.kind==='video'){container.replaceChildren();const note=document.createElement('div');note.className='upload-video-placeholder';const compact=container.classList.contains('upload-card-preview');note.textContent=compact?(state.language==='zh'?'▶ 视频':'▶ Video'):(state.language==='zh'?'视频预览暂不可用':'Video preview is not available yet');container.append(note);return;}
    const url=safeUploadPreviewURL(item.preview_url,item.id);
    const failed=()=>{container.replaceChildren();const note=document.createElement('p');note.className='upload-preview-error';note.textContent=t('uploadPreviewFailed');const retry=document.createElement('button');retry.type='button';retry.className='quiet';retry.textContent=t('uploadRetry');retry.addEventListener('click',()=>renderUploadPreview(container,item));container.append(note,retry);};
    if(!url){failed();return;}
    const image=document.createElement('img');image.className='upload-preview';image.alt=`${t('photo')} ${item.id}`;image.loading='eager';
    image.addEventListener('error',failed,{once:true});
    container.append(image);enqueueUploadPreview(container,image,url);
  }
  function openUploadDialog(item,review){
    if(state.locked||stale(uploadState.dialogEpoch))return;
    uploadState.dialogItem=item;uploadState.plans.set(item.id,String(review.plan));
    $('upload-review-copy').replaceChildren();
    const copy=document.createDocumentFragment(),line=document.createElement('span');line.textContent=`${t('approveUploadHelp')} ${currentLibraryName()}. `;copy.append(line);
    const warning=document.createElement('strong');warning.textContent=t('approveVisibility');copy.append(warning);
    const readers=document.createElement('span');readers.className='upload-reader-counts';readers.textContent=`${t('uploadReaders')}: ${Number(review.current_readers)||0} · ${t('uploadOriginalReaders')}: ${Number(review.current_original_readers)||0}`;copy.append(document.createElement('br'),readers);$('upload-review-copy').append(copy);
    $('upload-review-status').textContent='';$('upload-review-approve').textContent=t('approveUpload');
    renderUploadPreview($('upload-review-preview'),item);
    $('upload-review-dialog').showModal();$('upload-review-approve').focus();
  }
  async function reviewUpload(item){
    if(state.busy||state.locked||!item||!state.library)return;
    const epoch=state.generation;state.busy=true;$('uploads-status').textContent=t('working');
    try{
      const result=await request(libraryPath(`/admin/uploads/${encodeURIComponent(item.id)}/review`),{method:'POST',body:{},epoch});
      if(stale(epoch))return;uploadState.dialogEpoch=epoch;openUploadDialog(item,result);$('uploads-status').textContent='';
    }catch(error){if(!stale(epoch)){if(error.status===401||error.status===403)await failure(error,epoch);else $('uploads-status').textContent=t(uploadErrorKey(error));}}
    finally{state.busy=false;}
  }
  async function approveUpload(){
    const item=uploadState.dialogItem,epoch=uploadState.dialogEpoch,library=state.library,plan=item&&uploadState.plans.get(item.id);
    if(state.busy||state.locked||!item||!plan||stale(epoch))return;
    state.busy=true;$('upload-review-approve').disabled=true;$('upload-review-cancel').disabled=true;$('upload-review-close').disabled=true;
    try{
      await request(libraryPath(`/admin/uploads/${encodeURIComponent(item.id)}/approve`),{method:'POST',body:{plan},epoch});
      if(stale(epoch))return;closeUploadDialog();
      // The inbox disappearing alone leaves a stale gallery and makes approval
      // look like data loss. Return to an unfiltered first page immediately.
      storyState.search=null;$('search-text').value='';state.page=1;
      if(await loadGallery()&&library===state.library&&!state.locked){
        await loadUploads('uploadApproved');
        const card=[...$('grid').children].find(node=>node.dataset.assetId===String(item.id));
        if(card){card.scrollIntoView({block:'center'});card.focus({preventScroll:true});}
      }
    }catch(error){
      if(stale(epoch))return;
      if(error.status===409){closeUploadDialog();await loadUploads('uploadConflict');}
      else if(error.status===503||!error.status){$('upload-review-status').textContent=t('uploadUncertain');$('upload-review-approve').textContent=t('uploadRetryApproval');}
      else if(error.status===401||error.status===403)await failure(error,epoch);
      else {$('upload-review-status').textContent=t(uploadErrorKey(error));$('upload-review-approve').textContent=t('uploadRetryApproval');}
    }finally{state.busy=false;$('upload-review-approve').disabled=false;$('upload-review-cancel').disabled=false;$('upload-review-close').disabled=false;}
  }
  function closeUploadDialog(){
    const dialog=$('upload-review-dialog');if(dialog.open)dialog.close();uploadState.dialogItem=null;uploadState.dialogEpoch=0;$('upload-review-preview').replaceChildren();$('upload-review-copy').textContent='';$('upload-review-status').textContent='';$('upload-review-approve').textContent=t('approveUpload');
  }
  async function loadUploads(notice=null){
    if(state.locked||$('uploads-panel').hidden||!$('uploads-panel').open||!state.library)return;
    const epoch=state.generation,library=state.library,load=++uploadState.load;
    uploadState.dialogEpoch=epoch;$('uploads-list').replaceChildren();$('uploads-pages').hidden=true;$('uploads-status').textContent=t('uploadLoading');$('uploads-count').textContent='';
    try{
      const result=await request(libraryPath('/admin/uploads',{page:String(uploadState.page)}),{epoch});
      if(stale(epoch)||load!==uploadState.load||library!==state.library)return;
      uploadState.total=Number.isInteger(result.total)?result.total:0;uploadState.items=Array.isArray(result.items)?result.items:[];
      const pages=Math.max(1,Math.ceil(uploadState.total/10));
      if(uploadState.page>pages){uploadState.page=pages;return await loadUploads(notice);}
      $('uploads-count').textContent=result.can_review?`(${uploadState.total})`:'';if(result.can_review)$('uploads-count').setAttribute('aria-label',String(uploadState.total));
      if(!result.can_review){$('uploads-status').textContent=t('uploadRestricted');return;}
      $('uploads-status').textContent=notice?t(notice):(uploadState.total?'':t('uploadEmpty'));
      for(const item of uploadState.items){
        const card=document.createElement('article');card.className='upload-card';card.dataset.uploadId=item.id;
        const preview=document.createElement('div');preview.className='upload-card-preview';renderUploadPreview(preview,item);
        const details=document.createElement('div');details.className='upload-card-details';
        const title=document.createElement('h3');title.textContent=`${t('uploadBy')}: ${item.uploader}`;
        const meta=document.createElement('p');meta.className='fine';meta.textContent=`${String(item.created_at||'')} · ${item.kind==='video'?t('video'):`${item.width}×${item.height}`} · ${item.bytes} ${t('uploadBytes')}`;
        const button=document.createElement('button');button.type='button';button.className='primary';button.textContent=t('uploadReview');button.addEventListener('click',()=>void reviewUpload(item));
        details.append(title,meta,button);card.append(preview,details);$('uploads-list').append(card);
      }
      $('uploads-pages').hidden=uploadState.total===0;$('uploads-previous').disabled=uploadState.page===1;$('uploads-next').disabled=uploadState.page>=pages;$('uploads-page-label').textContent=`${t('page')} ${uploadState.page} ${t('of')} ${pages}`;
    }catch(error){if(!stale(epoch)&&load===uploadState.load){if(error.status===401||error.status===403)await failure(error,epoch);else {$('uploads-status').textContent=t(uploadErrorKey(error));$('uploads-count').textContent='';}}}
  }
  function clearProposedTags(){
    tagReviewState.load++;tagReviewState.page=1;tagReviewState.total=0;tagReviewState.busy=false;
    $('tag-review-list').replaceChildren();$('tag-review-pages').hidden=true;$('tag-review-status').textContent='';$('tag-review-refresh').disabled=false;
  }
  async function reviewProposedTag(item,decision,current){
    if(!current()||tagReviewState.busy)return;
    const epoch=state.generation,library=state.library;
    tagReviewState.busy=true;$('tag-review-refresh').disabled=true;$('tag-review-status').textContent=t('working');
    try{
      const result=await request(`/admin/upload-annotation-tags/review?library=${encodeURIComponent(library)}`,{
        method:'POST',body:{asset_id:item.asset_id,annotation_id:item.annotation_id,
          revision:String(item.revision),tag:item.tag,decision},epoch});
      if(!current())return;
      if(result.annotation_id!==item.annotation_id||result.revision!==item.revision||result.tag!==item.tag||result.status!==decision)throw new Error('Invalid tag review receipt');
      tagReviewState.busy=false;await loadProposedTags('tagReviewSaved');
    }catch(error){
      if(!current()||error.name==='AbortError')return;
      if(error.status===401||error.status===403)await failure(error,epoch);
      else if(error.status===409){tagReviewState.busy=false;await loadProposedTags('tagReviewConflict');}
      else $('tag-review-status').textContent=t('tagReviewUncertain');
    }finally{if(current()){tagReviewState.busy=false;$('tag-review-refresh').disabled=false;}}
  }
  async function loadProposedTags(notice=null){
    if(state.locked||$('tag-review-panel').hidden||!$('tag-review-panel').open||!state.library)return;
    const epoch=state.generation,library=state.library,load=++tagReviewState.load,page=tagReviewState.page;
    const current=()=>!stale(epoch)&&library===state.library&&load===tagReviewState.load&&$('tag-review-panel').open;
    tagReviewState.busy=true;$('tag-review-refresh').disabled=true;$('tag-review-list').replaceChildren();$('tag-review-pages').hidden=true;$('tag-review-status').textContent=t('loading');
    try{
      const result=await request(`/admin/upload-annotation-tags?library=${encodeURIComponent(library)}&page=${page}`,{epoch});
      if(!current())return;
      if(result.library_id!==library||result.page!==page||result.page_size!==10||!Number.isInteger(result.total)||result.total<0||!Array.isArray(result.items)||result.items.length>10)throw new Error('Invalid tag review list');
      tagReviewState.total=result.total;const pages=Math.max(1,Math.ceil(result.total/10));
      if(page>pages){tagReviewState.page=pages;tagReviewState.busy=false;return await loadProposedTags(notice);}
      $('tag-review-status').textContent=t(notice||(result.total?'':'tagReviewEmpty'));
      for(const item of result.items){
        if(!item||typeof item.annotation_id!=='string'||!/^[0-9a-f-]{36}$/.test(item.annotation_id)||typeof item.asset_id!=='string'||!/^[1-9][0-9]{0,18}$/.test(item.asset_id)||!Number.isInteger(item.revision)||item.revision<1||typeof item.tag!=='string'||!item.tag.trim()||!['folder','item'].includes(item.scope)||!['text','audio'].includes(item.kind))throw new Error('Invalid tag review item');
        const card=document.createElement('article');card.className='tag-review-card';
        const heading=document.createElement('h4');heading.textContent=`${t('tagReviewSuggested')}: ${item.tag}`;
        const scope=document.createElement('p');scope.className='fine';scope.textContent=`${t(item.scope==='folder'?'annotationFolder':'annotationItem')} · ${t('photo')} ${item.asset_id}`;
        card.append(heading,scope);
        if(item.kind==='text')addAnnotationText(card,item.original_text);
        else if(typeof item.audio_url==='string'){
          const url=new URL(item.audio_url,location.origin);
          if(url.origin===location.origin&&url.pathname===`/upload-annotations/${item.annotation_id}/audio`&&url.searchParams.get('library')===library&&url.searchParams.get('asset_id')===item.asset_id){const audio=document.createElement('audio');audio.controls=true;audio.preload='none';audio.src=url.pathname+url.search;audio.setAttribute('aria-label',t('annotationOriginal'));card.append(audio);}
        }
        if(item.transcript){const label=document.createElement('strong');label.textContent=t('annotationTranscript');card.append(label);addAnnotationText(card,item.transcript);}
        if(item.polished_text){const label=document.createElement('strong');label.textContent=t('annotationPolished');card.append(label);addAnnotationText(card,item.polished_text);}
        const actions=document.createElement('div');actions.className='tag-review-actions';
        for(const [decision,key] of [['accepted','tagReviewAccept'],['rejected','tagReviewReject']]){const button=document.createElement('button');button.type='button';button.className='quiet';button.textContent=t(key);button.setAttribute('aria-label',`${t(key)}: ${item.tag}`);button.addEventListener('click',()=>void reviewProposedTag(item,decision,current));actions.append(button);}
        card.append(actions);$('tag-review-list').append(card);
      }
      $('tag-review-pages').hidden=result.total===0;$('tag-review-previous').disabled=page===1;$('tag-review-next').disabled=page>=pages;$('tag-review-page-label').textContent=`${t('page')} ${page} ${t('of')} ${pages}`;
    }catch(error){if(current()){if(error.status===401||error.status===403)await failure(error,epoch);else $('tag-review-status').textContent=t('tagReviewUnavailable');}}
    finally{if(current()){tagReviewState.busy=false;$('tag-review-refresh').disabled=false;}}
  }
  async function loadMembers() {
    if(state.locked||$('members-panel').hidden)return;
    const epoch=state.generation,library=state.library,memberGeneration=++state.memberGeneration;
    $('member-list').replaceChildren();$('member-pages').hidden=true;$('member-policy-status').textContent=t('loading');
    try {
      const [result,policyOutcome]=await Promise.all([
        request(`/libraries/${encodeURIComponent(library)}/members?`+new URLSearchParams({page:String(state.memberPage),page_size:'25'}),{epoch}),
        request(`/admin/upload-auto-approval?library=${encodeURIComponent(library)}`,{epoch})
          .then(value=>({value}),error=>({error}))
      ]);
      if(stale(epoch)||memberGeneration!==state.memberGeneration)return;
      if(policyOutcome.error?.status===401||policyOutcome.error?.status===403)throw policyOutcome.error;
      const policyResult=policyOutcome.value;
      const policyAvailable=!!policyResult&&policyResult.library_id===library&&
        Array.isArray(policyResult.items)&&policyResult.items.every(item=>
          item&&typeof item.member_id==='string'&&typeof item.enabled==='boolean'&&
          Number.isSafeInteger(item.revision)&&item.revision>=1);
      const policies=new Map(policyAvailable?policyResult.items.map(item=>[item.member_id,item.enabled]):[]);
      $('member-policy-status').textContent=policyAvailable?'':t('autoApprovalUnavailable');
      state.memberTotal=result.total;
      for(const member of result.items) {
        const row=document.createElement('div');row.className='member-row';
        const info=document.createElement('div'),phone=document.createElement('span'),label=document.createElement('small');
        phone.textContent=member.phone_login;
        label.textContent=`${t(member.role)} · ${t(member.status==='revoked'?'memberRevoked':member.status)}${member.available?'':' · '+t('unavailableMember')}`;
        info.append(phone,label);row.append(info);
        if(policyAvailable&&member.status==='approved'&&member.available===true) {
          const enabled=policies.get(member.account_id)===true;
          const policyState=document.createElement('small');policyState.className='member-auto-state';
          policyState.textContent=t(enabled?'autoApprovalOn':'autoApprovalOff');info.append(policyState);
          const policyButton=document.createElement('button');policyButton.type='button';policyButton.className='quiet member-auto-toggle';
          policyButton.textContent=t(enabled?'autoApprovalDisable':'autoApprovalEnable');
          policyButton.setAttribute('aria-pressed',String(enabled));
          policyButton.setAttribute('aria-label',`${t(enabled?'autoApprovalActionOff':'autoApprovalActionOn')} ${member.phone_login}`);
          policyButton.addEventListener('click',async()=>{
            if(state.locked||stale(epoch)||state.busy)return;
            state.busy=true;policyButton.disabled=true;$('member-policy-status').textContent=t('working');
            const mode=enabled?'off':'on';
            try {
              const saved=await request(`/admin/upload-auto-approval/${encodeURIComponent(member.account_id)}?library=${encodeURIComponent(library)}`,{
                method:'PUT',body:{mode},epoch
              });
              if(stale(epoch)||library!==state.library)return;
              if(saved.library_id!==library||saved.member_id!==member.account_id||saved.enabled!==(mode==='on')||!Number.isSafeInteger(saved.revision)||saved.revision<1){
                const invalid=new Error('Invalid upload policy response');invalid.status=503;throw invalid;
              }
              state.busy=false;await loadMembers();
              if(!stale(epoch))$('member-policy-status').textContent=t(saved.enabled?'autoApprovalSavedOn':'autoApprovalSavedOff');
            } catch(error) {
              if(error.name==='AbortError'||stale(epoch))return;
              state.busy=false;
              if(error.status===401||error.status===403)await failure(error,epoch);
              else {
                await loadMembers();
                if(!stale(epoch))$('member-policy-status').textContent=t(error.status===409?'autoApprovalConflict':'autoApprovalUncertain');
              }
            } finally {state.busy=false;if(policyButton.isConnected)policyButton.disabled=false;}
          });
          row.append(policyButton);
        }
        if(member.role!=='owner'&&member.status!=='revoked') {
          const button=document.createElement('button');button.type='button';button.className='quiet';button.textContent=t('revoke');
          button.addEventListener('click',()=>{
            if(state.locked||stale(epoch)||state.busy)return;
            row.querySelector('.member-confirm')?.remove();
            const review=document.createElement('div');review.className='member-confirm';
            const text=document.createElement('p');text.textContent=`${t('confirmFor')} ${member.phone_login} · ${library}`;
            const confirm=document.createElement('button');confirm.type='button';confirm.className='primary';confirm.textContent=t('confirmRevoke');
            const cancel=document.createElement('button');cancel.type='button';cancel.className='quiet';cancel.textContent=t('cancel');
            cancel.addEventListener('click',()=>review.remove());
            confirm.addEventListener('click',async()=>{
              if(state.locked||state.busy||stale(epoch))return;
              state.busy=true;confirm.disabled=true;
              try {
                await request(`/libraries/${encodeURIComponent(library)}/members/${encodeURIComponent(member.account_id)}/revoke`,{method:'POST',body:{revision:member.revision},epoch});
                await loadMembers();status('revoked');
              } catch(error) {
                if(error.status===409&&!stale(epoch)){await loadMembers();status('conflict');}
                else await failure(error,epoch);
              } finally {state.busy=false;}
            });
            review.append(text,confirm,cancel);row.append(review);confirm.focus();
          });
          row.append(button);
        }
        $('member-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));
      $('member-pages').hidden=result.total===0;$('member-previous').disabled=state.memberPage===1;$('member-next').disabled=state.memberPage>=pages;
      $('member-page-label').textContent=`${t('page')} ${state.memberPage} ${t('of')} ${pages}`;
    } catch(error) {
      if(!stale(epoch))$('member-policy-status').textContent=t('autoApprovalUnavailable');
      await failure(error,epoch);
    }
  }
  // Albums this library has put away. Owner-only, and the only surface that shows them: an
  // archived album is excluded from every member-facing read, which is the point of archiving.
  // Restoring takes no revision, so there is nothing here to read back first.
  async function loadArchivedAlbums(){
    if(state.locked||$('album-archived-panel').hidden||!$('album-archived-panel').open)return;
    const epoch=state.generation,library=state.library,load=++albumState.archivedLoad;
    $('album-archived-list').replaceChildren();$('album-archived-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===albumState.archivedLoad&&library===state.library;
    try{
      const result=await request(libraryPath('/admin/albums/archived',{page:'1'}),{epoch});
      if(!current())return;
      $('album-archived-status').textContent=result.total?'':t('noArchivedAlbums');
      for(const album of result.items){
        const row=document.createElement('article');row.className='album-archived-card';row.dataset.albumId=album.id;
        const title=document.createElement('h3');title.textContent=album.title;
        row.append(title);
        row.append(storyButton('restoreAlbum',async()=>{
          if(state.busy||state.locked)return;
          try{
            await request(libraryPath(`/admin/albums/${album.id}/restore`),{method:'POST',epoch,body:{}});
            if(!current())return;
            await loadArchivedAlbums();await loadAlbums();
          }catch(error){if(current())await failure(error,epoch);}
        }));
        $('album-archived-list').append(row);
      }
    }catch(error){if(current()){$('album-archived-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  async function loadAlbums(){
    if(state.locked||!state.library)return;
    const epoch=state.generation,load=++albumState.load;
    $('album-list').replaceChildren();$('album-status').textContent=t('loading');
    try{
      const result=await request(libraryPath('/library-albums',{page:String(albumState.page)}),{epoch});
      if(stale(epoch)||load!==albumState.load)return;albumState.total=result.total;
      $('album-status').textContent=result.total?'':t('noAlbums');$('album-create').hidden=!result.can_manage;
      $('album-archived-panel').hidden=!result.can_manage;
      for(const album of result.items){
        const card=document.createElement('article');card.className='album-card';card.dataset.albumId=album.id;
        const title=document.createElement('h3');title.textContent=state.language==='zh'&&album.title_zh?album.title_zh:album.title;
        const description=document.createElement('p');description.textContent=album.description;card.append(title,description);
        if(album.needs_review){const note=document.createElement('p');note.textContent=t('albumNeedsReview');card.append(note);}
        const photos=document.createElement('div');photos.className='album-strip';
        for(const id of album.asset_ids){const button=document.createElement('button');button.type='button';button.className='quiet';const img=document.createElement('img');img.src=safeMediaURL(id,'thumbnail');img.alt=`${t('photo')} ${id}`;img.loading='lazy';button.append(img);button.addEventListener('click',async()=>{try{const detail=await request(libraryPath(`/assets/detail/${id}`),{epoch});if(!stale(epoch)&&card.isConnected)await openAsset(detail.asset,{sequence:album.asset_ids.map(id=>({id})),origin:'album'});}catch(error){await failure(error,epoch);}});photos.append(button);}
        card.append(photos);
        if(album.asset_ids.length)card.append(storyButton('storyWorkspaceAlbum',()=>storyWorkspace.open(album.asset_ids,album.theme==='custom'?'everyday':album.theme)));
        if(result.can_manage){
          card.append(storyButton('editAlbum',()=>editAlbum(album)));
          // Archive puts the album away without deleting anything, so a mistake is recoverable.
          card.append(storyButton('archiveAlbum',async()=>{
            if(state.busy||state.locked||!window.confirm(t('confirmArchive')))return;
            try{
              await request(libraryPath(`/admin/albums/${album.id}/archive`),{method:'POST',epoch,body:{revision:album.revision}});
              await loadAlbums();await loadArchivedAlbums();
            }catch(error){await failure(error,epoch);}
          }));
        }
        $('album-list').append(card);
      }
      $('album-pages').hidden=!result.total;$('album-previous').disabled=albumState.page===1;$('album-next').disabled=albumState.page*10>=result.total;
      $('album-page-label').textContent=`${t('page')} ${albumState.page} ${t('of')} ${Math.max(1,Math.ceil(result.total/10))}`;
    }catch(error){if(!stale(epoch)&&load===albumState.load){$('album-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  function editAlbum(album=null,restored=null){
    if(state.locked||state.busy||$('album-create').hidden)return;
    const epoch=state.generation,dialog=$('album-editor');
    const draft=restored||{account:state.profile.account_id,library:state.library,id:album?.id,revision:album?.revision,mutation_id:crypto.randomUUID(),title:album?.title||'',title_zh:album?.title_zh||'',description:album?.description||'',theme:album?.theme||'custom',ids:[...(album?.asset_ids||[])],cover_asset_id:album?.cover_asset_id||'',dirty:false,locked:false};
    albumState.draft=draft;dialog.replaceChildren();
    const current=()=>!stale(epoch)&&albumState.draft===draft&&dialog.open;
    const heading=document.createElement('h2');heading.textContent=t(draft.id?'editAlbum':'newAlbum');
    const form=document.createElement('form'),notice=document.createElement('p');notice.setAttribute('role','status');notice.id='album-editor-status';
    for(const [key,label,max] of [['title','albumTitle',160],['title_zh','albumTitleZh',160],['description','albumDescription',1000]]){
      const text=document.createElement('label');text.htmlFor='album-'+key;text.textContent=t(label);
      const input=document.createElement(key==='description'?'textarea':'input');input.id=text.htmlFor;input.value=draft[key];input.maxLength=max;input.required=key==='title';input.addEventListener('input',()=>{draft[key]=input.value;draft.dirty=true;});form.append(text,input);
    }
    const label=document.createElement('label');label.htmlFor='album-theme';label.textContent=t('albumTheme');const theme=document.createElement('select');theme.id='album-theme';
    for(const [value,en,zh] of [['custom','Our story','我们的故事'],['birthday','Birthday','生日'],['trip','Trip','旅行'],['growing_up','Growing up','成长'],['grandparents','Grandparents','祖辈时光'],['year_in_review','Year in review','年度回忆'],['seasonal','Seasonal','四季']]){const option=document.createElement('option');option.value=value;option.textContent=state.language==='zh'?zh:en;theme.append(option);}
    theme.value=draft.theme;theme.addEventListener('change',()=>{draft.theme=theme.value;draft.dirty=true;});form.append(label,theme);
    const selected=document.createElement('div');selected.id='album-selected';
    function selection(){selected.replaceChildren();for(const [index,id] of draft.ids.entries()){
      const row=document.createElement('div');row.className='album-selection';row.dataset.assetId=id;const image=document.createElement('img');image.src=safeMediaURL(id,'thumbnail');image.alt=`${t('photo')} ${id}`;row.append(image);
      const marker=document.createElement('span');marker.textContent=`${index+1} · ${id}${draft.cover_asset_id===id?' · '+t('cover'):''}`;row.append(marker);
      for(const [key,action,disabled] of [['moveUp',()=>{[draft.ids[index-1],draft.ids[index]]=[draft.ids[index],draft.ids[index-1]];},index===0],['moveDown',()=>{[draft.ids[index+1],draft.ids[index]]=[draft.ids[index],draft.ids[index+1]];},index===draft.ids.length-1],['setCover',()=>{draft.cover_asset_id=id;},draft.cover_asset_id===id],['remove',()=>{draft.ids=draft.ids.filter(value=>value!==id);if(draft.cover_asset_id===id)draft.cover_asset_id=draft.ids[0]||'';},false]]){const button=storyButton(key,()=>{if(!draft.locked&&current()){action();draft.dirty=true;selection();}});button.disabled=disabled||draft.locked;row.append(button);}selected.append(row);
    }}
    const selectedTitle=document.createElement('h3');selectedTitle.textContent=t('selectedPhotos');const pickTitle=document.createElement('h3');pickTitle.textContent=t('selectPhotos');
    const choices=document.createElement('div');choices.className='album-strip';choices.id='album-choices';const nav=document.createElement('nav');nav.className='pagination';let page=1,serial=0;
    async function pick(){const attempt=++serial;choices.replaceChildren();nav.replaceChildren();try{const result=await request(libraryPath('/assets',{page:String(page),page_size:'20'}),{epoch});if(!current()||attempt!==serial)return;
      for(const item of result.items){const button=document.createElement('button');button.type='button';button.className='quiet';button.dataset.assetId=item.id;button.setAttribute('aria-label',assetLabel(item));const img=document.createElement('img');img.src=safeMediaURL(item.id,'thumbnail');img.alt=assetLabel(item);img.loading='lazy';button.append(img);button.disabled=draft.locked;button.addEventListener('click',()=>{if(draft.locked||!current())return;if(!draft.ids.includes(item.id)&&draft.ids.length<60){draft.ids.push(item.id);draft.cover_asset_id=draft.cover_asset_id||item.id;draft.dirty=true;selection();}});choices.append(button);}
      const prev=storyButton('previous',()=>{page--;void pick();}),next=storyButton('next',()=>{page++;void pick();});prev.disabled=page===1||draft.locked;next.disabled=page*20>=result.total||draft.locked;nav.append(prev,next);
    }catch(error){if(current()){notice.textContent=t(errorStatus(error));await failure(error,epoch);}}}
    const save=document.createElement('button');save.id='album-save';save.type='submit';save.className='primary';save.textContent=t('saveAlbum');
    const close=storyButton('cancel',()=>{if(!state.busy&&(!draft.dirty||window.confirm(t('discardAlbum')))){albumState.draft=null;dialog.close();dialog.replaceChildren();}});
    form.append(selectedTitle,selected,pickTitle,choices,nav,notice,save,close);dialog.append(heading,form);if(!dialog.open)dialog.showModal();selection();void pick();
    function lock(){for(const input of form.querySelectorAll('input,textarea,select,button'))input.disabled=draft.locked;save.disabled=false;close.disabled=false;selection();}
    if(draft.locked){notice.textContent=t('albumUncertain');lock();}
    form.addEventListener('submit',async event=>{event.preventDefault();if(!current()||state.busy)return;state.busy=true;save.disabled=true;
      const body={title:draft.title,title_zh:draft.title_zh,description:draft.description,theme:draft.theme,asset_ids:draft.ids.join(','),cover_asset_id:draft.cover_asset_id,...(draft.id?{revision:draft.revision}:{mutation_id:draft.mutation_id})};
      draft.locked=true;lock();save.disabled=true;
      try{await request(libraryPath(draft.id?`/admin/albums/${draft.id}`:'/admin/albums'),{method:draft.id?'PUT':'POST',body,epoch});if(current()){albumState.draft=null;dialog.close();dialog.replaceChildren();await loadAlbums();$('album-status').textContent=t('albumSaved');}}
      catch(error){if(current()){draft.locked=![400,413,422].includes(error.status);lock();if(error.status===409){notice.textContent=t('albumChanged');save.disabled=true;}else notice.textContent=t(draft.locked?'albumUncertain':errorStatus(error));if(error.status===401||error.status===403)await failure(error,epoch);}}
      finally{state.busy=false;}
    });
  }
  $('album-editor').addEventListener('cancel',event=>{event.preventDefault();if(!state.busy&&(!albumState.draft?.dirty||window.confirm(t('discardAlbum')))){albumState.draft=null;$('album-editor').close();$('album-editor').replaceChildren();}});
  $('albums-panel').addEventListener('toggle',()=>{if($('albums-panel').open)void loadAlbums();});
  $('album-archived-panel').addEventListener('toggle',()=>{if($('album-archived-panel').open)void loadArchivedAlbums();});
  $('album-create').addEventListener('click',()=>editAlbum());
  $('album-previous').addEventListener('click',()=>{if(albumState.page>1){albumState.page--;void loadAlbums();}});
  $('album-next').addEventListener('click',()=>{if(albumState.page*10<albumState.total){albumState.page++;void loadAlbums();}});
  function personPicker({face,image,current,epoch,onSaved,status,container}){
    if(!current()||state.busy)return;
    // One picker per viewer; no previous person's selection survives opening another.
    container.querySelectorAll('.face-picker').forEach(node=>node.remove());
    const picker=document.createElement('section');picker.className='face-picker';
    const form=document.createElement('form');form.className='people-search';
    const label=document.createElement('label');label.htmlFor=`face-query-${face.id}`;label.textContent=t('findPerson');
    const input=document.createElement('input');input.id=label.htmlFor;input.type='search';input.maxLength=128;input.autocomplete='off';
    const search=document.createElement('button');search.type='submit';search.className='quiet';search.textContent=t('search');
    const results=document.createElement('div'),review=document.createElement('div'),notice=document.createElement('p');notice.setAttribute('role','status');review.className='assignment-review';
    const nav=document.createElement('nav');nav.className='pagination';
    let page=1,query='',serial=0;
    const active=()=>current()&&picker.isConnected;
    async function find(){
      const attempt=++serial;results.replaceChildren();review.replaceChildren();nav.replaceChildren();notice.textContent=t('loading');
      try{
        const found=await request(libraryPath('/admin/people',{q:query,page:String(page)}),{epoch});
        if(!active()||attempt!==serial)return;notice.textContent=found.total?t('assignmentChooseHelp'):t('peopleEmpty');
        for(const person of found.items){
          const choice=document.createElement('button');choice.type='button';choice.className='quiet person-choice';
          choice.textContent=`${person.display_name||t('unnamedPerson')} · ${person.id}`;choice.disabled=!person.can_rename;
          const option=document.createElement('div');option.className='person-choice-row';option.append(choice);
          if(!person.can_rename){const reason=document.createElement('p');reason.className='fine';reason.id=`assignment-restricted-${face.id}-${person.id}`;reason.textContent=t('assignmentRestricted');choice.setAttribute('aria-describedby',reason.id);option.append(reason);}
          choice.addEventListener('click',()=>{
            if(!active()||state.busy||attempt!==serial)return;
            const text=document.createElement('p');text.textContent=`${t('assignmentReview')}: ${person.display_name||t('unnamedPerson')} · ${person.id}?`;
            const confirm=storyButton('confirmAssignment',async()=>{
              if(!active()||state.busy||attempt!==serial)return;
              state.busy=true;confirm.disabled=true;
              try{
                await request(libraryPath(`/admin/faces/${face.id}/assignment`),{method:'POST',epoch,body:{person_id:person.id,revision:face.revision,person_revision:person.revision}});
                if(active()){await onSaved();if(!stale(epoch))status.textContent=t('assignmentSaved');}
              }catch(error){
                if(active()){
                  // Ambiguous writes require fresh server readback; never retry automatically.
                  serial++;review.replaceChildren();results.replaceChildren();nav.replaceChildren();
                  notice.textContent=t(error.status===409?'assignmentConflict':'assignmentFailed');
                  if(error.status===401||error.status===403)await failure(error,epoch);
                }
              }finally{state.busy=false;}
            });
            const preview=image.cloneNode();preview.loading='eager';
            const actions=document.createElement('div');actions.className='face-confirm';actions.append(confirm,storyButton('cancel',()=>review.replaceChildren()));
            review.replaceChildren(preview,text,actions);review.scrollIntoView({block:'nearest'});confirm.focus();
          });results.append(option);
        }
        const previous=storyButton('previous',()=>{if(!state.busy){page--;void find();}}),next=storyButton('next',()=>{if(!state.busy){page++;void find();}});
        previous.disabled=page===1;next.disabled=page*25>=found.total;
        const position=document.createElement('span');position.textContent=`${t('page')} ${page} ${t('of')} ${Math.max(1,Math.ceil(found.total/25))}`;
        nav.append(previous,position,next);
      }catch(error){if(active()&&attempt===serial){notice.textContent=t(errorStatus(error));await failure(error,epoch);}}
    }
    form.append(label,input,search);picker.append(form,notice,results,nav,review,storyButton('closeSelection',()=>picker.remove()));
    form.addEventListener('submit',event=>{event.preventDefault();if(!state.busy&&active()){query=input.value.trim();page=1;void find();}});
    void find();input.focus();
    return picker;
  }

  async function loadAssetFaces(){
    if(state.locked||$('face-panel').hidden||!storyState.asset)return;
    const epoch=state.generation,viewer=state.viewerGeneration,load=++faceState.load,asset=storyState.asset.id;
    const current=()=>!stale(epoch)&&viewer===state.viewerGeneration&&load===faceState.load&&$('viewer').open;
    $('face-list').replaceChildren();$('face-pages').hidden=true;$('face-status').textContent=t('loading');
    try{
      const result=await request(libraryPath(`/admin/assets/${asset}/faces`,{page:String(faceState.page)}),{epoch});
      if(!current())return;faceState.total=result.total;$('face-status').textContent=result.total?'':t('noFaces');
      for(const face of result.items){
        const row=document.createElement('article');row.className='face-label-card';row.dataset.faceId=face.id;
        const image=document.createElement('img');image.className='assignment-crop';image.alt=`${t('reviewFaces')} ${face.id}`;image.src=libraryPath(`/faces/${face.id}/crop`);image.loading='lazy';
        image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
        const name=document.createElement('h4');name.textContent=face.display_name||(face.person_id?`${t('unnamedPerson')} ${face.person_id}`:t('unassigned'));
        row.append(image,name);
        if(!face.can_assign){const note=document.createElement('p');note.textContent=t('assignmentUnavailable');row.append(note);}
        else row.append(storyButton('choosePerson',()=>{
          if(!current()||state.busy)return;
          // One picker per viewer; a previous selection never survives opening another.
          row.append(personPicker({face,image,current,epoch,onSaved:loadAssetFaces,status:$('face-status'),container:$('face-list')}));
        }));
        if(face.can_assign){
          const actionStatus=document.createElement('p');actionStatus.className='face-action-status';actionStatus.setAttribute('role','status');actionStatus.setAttribute('aria-live','polite');
          async function changeFace(action,body,button){
            if(!current()||state.busy)return;
            const actionEpoch=epoch;state.busy=true;state.faceActionEpoch=actionEpoch;if(button)button.disabled=true;actionStatus.textContent=t('working');
            try{
              await request(libraryPath(`/admin/faces/${face.id}/${action}`),{method:'POST',body:{revision:face.revision,...body},epoch});
              if(current()){await loadAssetFaces();if(!stale(actionEpoch)){$('face-status').textContent=t('assignmentSaved');actionStatus.textContent=t('assignmentSaved');}}
            }catch(error){
              if(current()){actionStatus.textContent=t(error.status===409?'assignmentConflict':'assignmentFailed');$('face-status').textContent=actionStatus.textContent;if(error.status===401||error.status===403)await failure(error,epoch);}
            }finally{if(state.faceActionEpoch===actionEpoch){state.faceActionEpoch=null;state.busy=false;if(button&&button.isConnected)button.disabled=false;}}
          }
          row.append(storyButton('newPerson',()=>{if(!current()||state.busy)return;row.querySelector('.new-person-form')?.remove();const form=document.createElement('form');form.className='new-person-form';const label=document.createElement('label');label.htmlFor=`new-person-${face.id}`;label.textContent=t('personName');const input=document.createElement('input');input.id=label.htmlFor;input.required=true;input.maxLength=128;const help=document.createElement('p');help.textContent=t('newPersonHelp');const save=document.createElement('button');save.type='submit';save.textContent=t('createAssign');form.append(label,input,help,save);form.addEventListener('submit',event=>{event.preventDefault();if(input.value.trim()&&window.confirm(`${t('createAssign')}: ${input.value.trim()}?`))void changeFace('new-person',{display_name:input.value.trim()},save);});row.append(form);input.focus();}));
          if(face.person_id){const unassign=storyButton('unassignFace',()=>{if(window.confirm(t('confirmUnassign')))void changeFace('unassign',{},unassign);});row.append(unassign);}
          row.append(actionStatus);
        }
        $('face-list').append(row);
      }
      $('face-pages').hidden=result.total===0;$('face-previous').disabled=faceState.page===1;$('face-next').disabled=faceState.page*25>=result.total;
      $('face-page-label').textContent=`${t('page')} ${faceState.page} ${t('of')} ${Math.max(1,Math.ceil(result.total/25))}`;
    }catch(error){if(current()){$('face-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  $('face-panel').addEventListener('toggle',()=>{if($('face-panel').open){stopSlideshow();void loadAssetFaces();}});
  $('face-refresh').addEventListener('click',()=>{if(!state.busy)void loadAssetFaces();});
  $('face-previous').addEventListener('click',()=>{if(!state.busy&&faceState.page>1){faceState.page--;void loadAssetFaces();}});
  $('face-next').addEventListener('click',()=>{if(!state.busy&&faceState.page*25<faceState.total){faceState.page++;void loadAssetFaces();}});
  async function loadPeople(){
    if(state.locked||$('people-panel').hidden)return;
    const epoch=state.generation,library=state.library,load=++peopleState.load;
    $('people-list').replaceChildren();$('people-pages').hidden=true;$('people-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===peopleState.load&&library===state.library;
    try{
      const result=await request(libraryPath('/admin/people',{page:String(peopleState.page),q:peopleState.query,named:peopleState.named}),{epoch});
      if(!current())return;
      peopleState.total=result.total;$('people-status').textContent=result.total?'':t('peopleEmpty');
      for(const person of result.items){
        const row=document.createElement('article');row.className='person-card';row.dataset.personId=person.id;
        const title=document.createElement('h3');title.textContent=person.display_name||`${t('unnamedPerson')} ${person.id}`;
        const count=document.createElement('small');count.textContent=`${person.face_count} ${t('facesCount')}`;row.append(title,count);
        if(person.name_truncated){const note=document.createElement('p');note.className='fine';note.textContent=t('nameShortened');row.append(note);}
        if(person.can_rename){
          const form=document.createElement('form');form.className='person-name-form';
          const label=document.createElement('label');label.htmlFor=`person-name-${person.id}`;label.textContent=t('personName');
          const input=document.createElement('input');input.id=label.htmlFor;input.value=person.name_truncated?'':person.display_name;input.maxLength=128;input.required=true;input.autocomplete='off';
          const save=document.createElement('button');save.type='submit';save.className='quiet';save.textContent=t('saveName');
          form.append(label,input,save);row.append(form);
          form.addEventListener('submit',async event=>{
            event.preventDefault();if(!current()||state.locked||state.busy||!row.isConnected)return;
            const name=input.value.trim();if(!name)return;
            state.busy=true;save.disabled=true;input.disabled=true;
            try{
              await request(libraryPath(`/admin/people/${person.id}`),{method:'PUT',body:{display_name:name,revision:person.revision},epoch});
              if(current()){await loadPeople();if(!stale(epoch))$('people-status').textContent=t('nameSaved');}
            }catch(error){
              if(!current())return;
              if(error.status===409){await loadPeople();if(!stale(epoch))$('people-status').textContent=t('nameConflict');}
              else if(error.status===401||error.status===403)await failure(error,epoch);
              else $('people-status').textContent=t('nameSaveFailed');
            }finally{state.busy=false;save.disabled=false;input.disabled=false;}
          });
        }else{const note=document.createElement('p');note.className='fine';note.textContent=t('nameUnavailable');row.append(note);}
        const faces=document.createElement('div');faces.className='person-faces';
        const review=document.createElement('button');review.type='button';review.className='quiet';review.textContent=t('reviewFaces');
        let facePage=0;
        review.addEventListener('click',async()=>{
          if(!current()||state.locked||!row.isConnected)return;review.disabled=true;
          try{
            const result=await request(libraryPath(`/admin/people/${person.id}/faces`,{page:String(facePage+1)}),{epoch});
            if(!current()||!row.isConnected)return;facePage=result.page;
            for(const face of result.items){
              const button=document.createElement('button');button.type='button';button.className='face-review';
              const image=document.createElement('img');image.alt=`${person.display_name||t('unnamedPerson')} · ${face.id}`;
              image.src=libraryPath(`/faces/${face.id}/crop`);image.loading='lazy';
              image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
              button.append(image);faces.append(button);
              button.addEventListener('click',async()=>{
                if(!current()||state.locked||!abandonStory())return;
                try{const detail=await request(libraryPath(`/assets/detail/${face.asset_id}`),{epoch});if(current())await openAsset(detail.asset);}
                catch(error){await failure(error,epoch);}
              });
            }
            review.hidden=facePage*25>=result.total;review.textContent=t('moreFaces');
          }catch(error){await failure(error,epoch);}finally{review.disabled=false;}
        });
        row.append(faces,review);$('people-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('people-pages').hidden=result.total===0;
      $('people-previous').disabled=peopleState.page===1;$('people-next').disabled=peopleState.page>=pages;
      $('people-page-label').textContent=`${t('page')} ${peopleState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('people-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  // Member-facing people directory. Read-only by construction: the route returns a
  // name, a count and one thumbnail, so there is nothing here to submit. The owner
  // panel below is where names are actually managed.
  async function loadDirectory(){
    if(state.locked||!$('directory-panel').open)return;
    const epoch=state.generation,library=state.library,load=++directoryState.load;
    $('directory-list').replaceChildren();$('directory-pages').hidden=true;$('directory-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===directoryState.load&&library===state.library&&$('directory-panel').open;
    try{
      const result=await request(libraryPath('/people',{page:String(directoryState.page),q:directoryState.query}),{epoch});
      if(!current())return;
      directoryState.total=result.total;$('directory-status').textContent=result.total?'':t('noPeopleInLibrary');
      for(const person of result.items){
        const row=document.createElement('article');row.className='directory-card';row.dataset.personId=person.id;
        if(directoryState.person===person.id)row.classList.add('tag-selected');
        // The name is the control that opens this person's photos. The route behind it is
        // member-scoped and read-only, so there is nothing on the card to submit.
        const button=document.createElement('button');button.type='button';button.className='quiet person-name';
        button.textContent=person.display_name;
        const count=document.createElement('small');count.textContent=`${person.face_count} ${t('facesCount')}`;
        row.append(button,count);
        button.addEventListener('click',()=>{
          if(state.busy||state.locked)return;
          directoryState.person=person.id;directoryState.assetPage=1;
          for(const other of $('directory-list').children)other.classList.remove('tag-selected');
          row.classList.add('tag-selected');
          void loadPersonAssets();
        });
        // The server supplies the crop URL so the client never reconstructs one; only
        // a same-origin path is accepted, so no unexpected origin can be loaded.
        if(typeof person.thumbnail_url==='string'&&person.thumbnail_url.startsWith('/faces/')){
          const image=document.createElement('img');image.className='directory-crop';image.loading='lazy';
          image.alt=`${person.display_name} · ${t('facesCount')}`;
          image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
          image.src=person.thumbnail_url;row.prepend(image);
        }
        $('directory-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('directory-pages').hidden=result.total===0;
      $('directory-previous').disabled=directoryState.page===1;$('directory-next').disabled=directoryState.page>=pages;
      $('directory-page-label').textContent=`${t('page')} ${directoryState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('directory-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  // Photos of one person, from the member-scoped route. Read-only by construction: the
  // route returns photos this library already maps and nothing about faces, so there is no
  // control here beyond opening one. An empty page keeps the total visible.
  async function loadPersonAssets(){
    if(state.locked||directoryState.person===null||!$('directory-panel').open)return;
    const epoch=state.generation,library=state.library,person=directoryState.person,load=++directoryState.assetLoad;
    $('person-assets').replaceChildren();$('person-pages').hidden=true;
    const current=()=>!stale(epoch)&&load===directoryState.assetLoad&&person===directoryState.person&&library===state.library;
    try{
      const result=await request(libraryPath(`/people/${person}/assets`,{page:String(directoryState.assetPage)}),{epoch});
      if(!current())return;
      directoryState.assetTotal=result.total;
      const heading=document.createElement('h4');heading.textContent=t('personPhotos');
      heading.append(' ',storyButton('clearPerson',()=>{
        directoryState.person=null;directoryState.assetTotal=0;$('person-assets').replaceChildren();
        $('person-pages').hidden=true;void loadDirectory();
      }));
      $('person-assets').append(heading);
      if(!result.total){const empty=document.createElement('p');empty.className='fine';empty.textContent=t('noPersonPhotos');$('person-assets').append(empty);}
      for(const asset of result.items){
        const row=document.createElement('article');row.className='person-asset-card';row.dataset.assetId=asset.id;
        // Only a same-origin thumbnail path is accepted, so no unexpected origin is loaded.
        if(typeof asset.thumbnail_url==='string'&&asset.thumbnail_url.startsWith('/assets/')){
          const image=document.createElement('img');image.className='person-asset-crop';image.loading='lazy';
          image.alt=`${t('personPhotos')} · ${asset.id}`;
          image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
          image.src=asset.thumbnail_url;row.append(image);
        }
        row.append(storyButton('openPhoto',async()=>{
          if(!current()||state.locked||state.busy||!abandonStory())return;
          try{const detail=await request(libraryPath(`/assets/detail/${asset.id}`),{epoch});if(current())await openAsset(detail.asset);}
          catch(error){await failure(error,epoch);}
        }));
        $('person-assets').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('person-pages').hidden=result.total===0;
      $('person-previous').disabled=directoryState.assetPage===1;
      $('person-next').disabled=directoryState.assetPage>=pages;
      $('person-page-label').textContent=`${t('page')} ${directoryState.assetPage} ${t('of')} ${pages}`;
    }catch(error){if(current())await failure(error,epoch);}
  }
  // Exact duplicate groups in this library. Read-only by construction: the route is GET-only
  // and returns no path, filename or content hash, so there is nothing here to submit and
  // nothing to act on. It explains a duplication the member can already see in the gallery.
  async function loadDuplicates(){
    if(state.locked||!$('duplicates-panel').open)return;
    const epoch=state.generation,library=state.library,load=++duplicateState.load;
    $('duplicate-list').replaceChildren();$('duplicate-pages').hidden=true;$('duplicate-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===duplicateState.load&&library===state.library&&$('duplicates-panel').open;
    try{
      const result=await request(libraryPath('/duplicates',{page:String(duplicateState.page)}),{epoch});
      if(!current())return;
      duplicateState.total=result.total;
      $('duplicate-status').textContent=result.total?'':t('noDuplicatesInLibrary');
      for(const group of result.items){
        const row=document.createElement('article');row.className='duplicate-group';row.dataset.groupId=group.group_id;
        const title=document.createElement('h4');title.textContent=`${t('savedTimes')} ${group.copy_count}`;
        const copies=document.createElement('div');copies.className='duplicate-copies';
        for(const copy of group.copies){
          const card=document.createElement('article');card.className='duplicate-copy';card.dataset.assetId=copy.id;
          // Only a same-origin thumbnail path is accepted, so no unexpected origin is loaded.
          if(typeof copy.thumbnail_url==='string'&&copy.thumbnail_url.startsWith('/assets/')){
            const image=document.createElement('img');image.className='duplicate-crop';image.loading='lazy';
            image.alt=`${t('duplicatesInLibrary')} · ${copy.id}`;
            image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
            image.src=copy.thumbnail_url;card.append(image);
          }
          card.append(storyButton('openPhoto',async()=>{
            if(!current()||state.locked||state.busy||!abandonStory())return;
            try{const detail=await request(libraryPath(`/assets/detail/${copy.id}`),{epoch});if(current())await openAsset(detail.asset);}
            catch(error){await failure(error,epoch);}
          }));
          copies.append(card);
        }
        row.append(title,copies);$('duplicate-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('duplicate-pages').hidden=result.total===0;
      $('duplicate-previous').disabled=duplicateState.page===1;$('duplicate-next').disabled=duplicateState.page>=pages;
      $('duplicate-page-label').textContent=`${t('page')} ${duplicateState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('duplicate-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  // Member-facing tag catalog. Read-only by construction: both routes are GET-only and
  // the server returns a name plus a count of this library's own photos, so there is no
  // add, rename or remove control here and nothing to submit.
  async function loadTags(){
    if(state.locked||!$('tags-panel').open)return;
    const epoch=state.generation,library=state.library,load=++tagState.load;
    $('tag-list').replaceChildren();$('tag-pages').hidden=true;$('tag-status').textContent=t('loading');
    const current=()=>!stale(epoch)&&load===tagState.load&&library===state.library&&$('tags-panel').open;
    try{
      const result=await request(libraryPath('/tags',{page:String(tagState.page),q:tagState.query}),{epoch});
      if(!current())return;
      tagState.total=result.total;$('tag-status').textContent=result.total?'':t('noTagsInLibrary');
      for(const tag of result.items){
        const row=document.createElement('article');row.className='tag-card';row.dataset.tagId=tag.id;
        if(tagState.open===tag.id)row.classList.add('tag-selected');
        const button=document.createElement('button');button.type='button';button.className='quiet tag-name';
        button.textContent=tag.name;
        const count=document.createElement('small');count.textContent=`${tag.asset_count} ${t('assetsCount')}`;
        row.append(button,count);
        button.addEventListener('click',()=>{
          if(state.busy||state.locked)return;
          tagState.tag=tag.id;tagState.tagPage=1;
          for(const other of $('tag-list').children)other.classList.remove('tag-selected');
          row.classList.add('tag-selected');
          void loadTagAssets();
        });
        $('tag-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('tag-pages').hidden=result.total===0;
      $('tag-previous').disabled=tagState.page===1;$('tag-next').disabled=tagState.page>=pages;
      $('tag-page-label').textContent=`${t('page')} ${tagState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('tag-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  async function loadTagAssets(){
    if(state.locked||tagState.tag===null||!$('tags-panel').open)return;
    const epoch=state.generation,library=state.library,tag=tagState.tag,load=++tagState.tagLoad;
    $('tag-assets').replaceChildren();
    const current=()=>!stale(epoch)&&load===tagState.tagLoad&&tag===tagState.tag&&library===state.library;
    try{
      const result=await request(libraryPath(`/tags/${tag}/assets`,{page:String(tagState.tagPage)}),{epoch});
      if(!current())return;
      tagState.tagTotal=result.total;
      const heading=document.createElement('h4');heading.textContent=t('tagAssets');
      heading.append(' ',storyButton('clearTag',()=>{
        tagState.tag=null;tagState.tagTotal=0;tagState.open=null;$('tag-assets').replaceChildren();void loadTags();
      }));
      $('tag-assets').append(heading);
      if(!result.total){const empty=document.createElement('p');empty.className='fine';empty.textContent=t('noTaggedAssets');$('tag-assets').append(empty);}
      for(const asset of result.items){
        const row=document.createElement('article');row.className='tag-asset-card';row.dataset.assetId=asset.id;
        // Only a same-origin thumbnail path is accepted, so no unexpected origin is loaded.
        if(typeof asset.thumbnail_url==='string'&&asset.thumbnail_url.startsWith('/assets/')){
          const image=document.createElement('img');image.className='tag-asset-crop';image.loading='lazy';
          image.alt=`${t('tagAssets')} · ${asset.id}`;
          image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
          image.src=asset.thumbnail_url;row.append(image);
        }
        row.append(storyButton('openPhoto',async()=>{
          if(!current()||state.locked||state.busy||!abandonStory())return;
          try{const detail=await request(libraryPath(`/assets/detail/${asset.id}`),{epoch});if(current())await openAsset(detail.asset);}
          catch(error){await failure(error,epoch);}
        }));
        $('tag-assets').append(row);
      }
    }catch(error){if(current())await failure(error,epoch);}
  }
  async function loadFamilyTags(){
    if(state.locked||!$('family-tags-panel').open)return;
    const epoch=state.generation,library=state.library,load=++familyTagState.load;
    const current=()=>!stale(epoch)&&load===familyTagState.load&&library===state.library&&$('family-tags-panel').open;
    $('family-tag-list').replaceChildren();$('family-tag-pages').hidden=true;$('family-tag-status').textContent=t('loading');
    try{
      const result=await request(libraryPath('/family-tags',{page:String(familyTagState.page),q:familyTagState.query}),{epoch});
      if(!current())return;
      if(result.library_id!==library||!Number.isInteger(result.total)||!Array.isArray(result.items))throw new Error('Invalid family tags');
      familyTagState.total=result.total;$('family-tag-status').textContent=result.total?'':t('familyTagsEmpty');
      for(const tag of result.items){
        if(typeof tag.name!=='string'||!tag.name.trim()||!Number.isInteger(tag.asset_count)||tag.asset_count<1)throw new Error('Invalid family tag');
        const row=document.createElement('article');row.className='tag-card';
        if(familyTagState.tag===tag.name)row.classList.add('tag-selected');
        const button=document.createElement('button');button.type='button';button.className='quiet tag-name';button.textContent=tag.name;
        const count=document.createElement('small');count.textContent=`${tag.asset_count} ${t('assetsCount')}`;
        button.addEventListener('click',()=>{if(state.busy||state.locked)return;familyTagState.tag=tag.name;familyTagState.assetPage=1;void loadFamilyTagAssets();for(const other of $('family-tag-list').children)other.classList.remove('tag-selected');row.classList.add('tag-selected');});
        row.append(button,count);$('family-tag-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('family-tag-pages').hidden=result.total===0;
      $('family-tag-previous').disabled=familyTagState.page===1;$('family-tag-next').disabled=familyTagState.page>=pages;
      $('family-tag-page-label').textContent=`${t('page')} ${familyTagState.page} ${t('of')} ${pages}`;
      if(familyTagState.tag!==null)void loadFamilyTagAssets();
    }catch(error){if(current()){$('family-tag-list').replaceChildren();$('family-tag-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  async function loadFamilyTagAssets(){
    if(state.locked||familyTagState.tag===null||!$('family-tags-panel').open)return;
    const epoch=state.generation,library=state.library,tag=familyTagState.tag,load=++familyTagState.tagLoad;
    const current=()=>!stale(epoch)&&load===familyTagState.tagLoad&&tag===familyTagState.tag&&library===state.library&&$('family-tags-panel').open;
    $('family-tag-assets').replaceChildren();$('family-tag-asset-pages').hidden=true;
    try{
      const result=await request(libraryPath('/family-tags/assets'),{method:'POST',body:{tag,page:String(familyTagState.assetPage)},epoch});
      if(!current())return;
      if(result.library_id!==library||result.tag!==tag||!Number.isInteger(result.total)||!Array.isArray(result.items))throw new Error('Invalid family tag assets');
      familyTagState.assetTotal=result.total;
      const heading=document.createElement('h4');heading.textContent=t('familyTagAssets');
      heading.append(' ',storyButton('clearFamilyTag',()=>{familyTagState.tag=null;familyTagState.assetTotal=0;$('family-tag-assets').replaceChildren();$('family-tag-asset-pages').hidden=true;void loadFamilyTags();}));
      $('family-tag-assets').append(heading);
      for(const asset of result.items){
        const row=document.createElement('article');row.className='tag-asset-card';row.dataset.assetId=asset.id;
        if(typeof asset.thumbnail_url==='string'&&asset.thumbnail_url.startsWith('/assets/')){
          const image=document.createElement('img');image.className='tag-asset-crop';image.loading='lazy';image.alt=`${t('familyTagAssets')} · ${asset.id}`;
          image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});image.src=asset.thumbnail_url;row.append(image);
        }
        row.append(storyButton('openPhoto',async()=>{if(!current()||state.locked||state.busy||!abandonStory())return;try{const detail=await request(libraryPath(`/assets/detail/${asset.id}`),{epoch});if(current())await openAsset(detail.asset);}catch(error){await failure(error,epoch);}}));
        $('family-tag-assets').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('family-tag-asset-pages').hidden=pages<=1;
      $('family-tag-asset-previous').disabled=familyTagState.assetPage===1;$('family-tag-asset-next').disabled=familyTagState.assetPage>=pages;
      $('family-tag-asset-page-label').textContent=`${t('page')} ${familyTagState.assetPage} ${t('of')} ${pages}`;
    }catch(error){if(current()){if(error.status===401){familyTagState.tag=null;familyTagState.assetTotal=0;$('family-tag-assets').replaceChildren();void loadFamilyTags();}else await failure(error,epoch);}}
  }
  // Named places and date/media narrowing share a reviewed snapshot. Reopening
  // refreshes its binding; failed refreshes offer an explicit retry.
  async function openDiscovery(){
    if(state.locked||!state.library)return false;
    const epoch=state.generation,library=String(state.library),account=String(state.profile?.account_id||'');
    const previousBinding=discoveryState.binding,previousOwner=discoveryState.owner;
    const sameOwner=previousOwner?.library===library&&previousOwner?.account===account;
    if(previousOwner&&!sameOwner)clearDiscoveryMode({clearInputs:true,clearBinding:true});
    const modeToken=discoveryState.modeToken;if(discoveryState.active){discoveryState.searchLoad++;galleryLoad++;}
    const load=++discoveryState.facetLoad;
    discoveryState.placeQuery='';$('discovery-place-query').value='';
    discoveryState.binding=null;$('discovery-place-list').replaceChildren();$('discovery-place-pages').hidden=true;
    $('discovery-facets-retry').hidden=true;$('discovery-status').textContent=t('loading');
    if(discoveryState.active){$('grid').replaceChildren();$('empty').hidden=true;$('pagination').hidden=true;state.total=0;discoveryState.total=null;renderDiscoverySummary(t('discoveryWorking'));}
    const current=()=>!stale(epoch)&&load===discoveryState.facetLoad&&modeToken===discoveryState.modeToken&&library===String(state.library)&&account===String(state.profile?.account_id||'');
    try{
      const result=await request(`/libraries/${encodeURIComponent(library)}/discovery/v1/facets?`+
      new URLSearchParams({facet:'locations',page:'1',page_size:'24'}),{epoch});
      if(!current())return false;
      if(!Array.isArray(result.enabled)||!result.enabled.includes('media')){$('discovery-panel').hidden=true;clearDiscoveryMode({clearInputs:true,clearBinding:true});return false;}
      discoveryState.binding=result.binding;discoveryState.owner={library,account};
      const bindingChanged=Boolean(previousBinding&&previousBinding!==result.binding&&sameOwner);
      if(bindingChanged){discoveryState.page=1;discoveryState.fingerprint=null;state.page=1;}
      const bounds=result.captured_date_bounds||{};
      // Facet bounds are a native hint. The bound search independently validates them.
      const low=typeof bounds.from==='string'?bounds.from:'',high=typeof bounds.to==='string'?bounds.to:'';
      for(const id of ['discovery-from','discovery-to']){$(id).min=low;$(id).max=high;}
      $('discovery-panel').hidden=false;discoveryState.placesAvailable=Array.isArray(result.enabled)&&result.enabled.includes('locations');
      if(discoveryState.placesAvailable){discoveryState.placeTotal=Number(result.total)||0;discoveryState.places=Array.isArray(result.items)?result.items:[];discoveryState.placePage=1;renderDiscoveryPlaces();}
      else{$('discovery-places').hidden=true;$('discovery-places-status').textContent=t('placesUnavailable');}
      $('discovery-status').textContent=!discoveryState.active?t('discoveryHint'):'';
      if(discoveryState.active&&discoveryState.applied&&previousBinding&&bindingChanged)renderDiscoverySummary(t('discoveryUpdated'));
      return true;
    }catch(error){
      if(!current())return false;
      if(error&&(error.status===401||error.status===403)){await failure(error,epoch);return false;}
      discoveryState.placesAvailable=false;discoveryState.binding=null;$('discovery-panel').hidden=false;$('discovery-places').hidden=true;
      $('discovery-status').textContent=t(error?.status===409?'discoveryChanged':'discoveryError');$('discovery-facets-retry').hidden=false;
      if(discoveryState.active)renderDiscoverySummary(t(error?.status===409?'discoveryUpdated':'discoveryError'),{retry:true});
      return false;
    }
  }
  function renderDiscoveryPlaces(){
    if(!discoveryState.placesAvailable)return;
    const list=$('discovery-place-list');list.replaceChildren();
    renderSelectedPlaces();
    if(!discoveryState.placeTotal){$('discovery-places').hidden=false;$('discovery-places-status').textContent=t(discoveryState.placeQuery?'placeSearchNone':'placesNone');$('discovery-place-pages').hidden=true;return;}
    $('discovery-places').hidden=false;$('discovery-places-status').textContent='';
    for(const place of discoveryState.places){
      const button=document.createElement('button');button.type='button';button.className='place-choice';button.dataset.placeId=String(place.id);button.setAttribute('aria-pressed',String(discoveryState.selectedPlaces.has(String(place.id))));
      const label=document.createElement('span');label.textContent=String(place.label||place.id);const count=document.createElement('small');count.textContent=`${Number(place.asset_count)||0} ${t('placesCount')}`;button.append(label,count);
      button.addEventListener('click',()=>{if(state.busy||state.locked)return;const id=String(place.id);if(discoveryState.selectedPlaces.has(id)){discoveryState.selectedPlaces.delete(id);discoveryState.selectedPlaceLabels.delete(id);}else if(discoveryState.selectedPlaces.size<20){discoveryState.selectedPlaces.add(id);discoveryState.selectedPlaceLabels.set(id,String(place.label||id));}else{$('discovery-status').textContent=t('placesLimit');return;}button.setAttribute('aria-pressed',String(discoveryState.selectedPlaces.has(id)));renderSelectedPlaces();});list.append(button);
    }
    const pages=Math.max(1,Math.ceil(discoveryState.placeTotal/24));$('discovery-place-pages').hidden=pages<=1;$('discovery-place-previous').disabled=discoveryState.placePage===1;$('discovery-place-next').disabled=discoveryState.placePage>=pages;$('discovery-place-page-label').textContent=`${t('page')} ${discoveryState.placePage} ${t('of')} ${pages}`;
  }
  function renderSelectedPlaces(){
    const list=$('discovery-place-selected');list.replaceChildren();
    for(const id of discoveryState.selectedPlaces){
      const button=document.createElement('button');button.type='button';button.className='quiet';
      const label=discoveryState.selectedPlaceLabels.get(id)||id;
      button.textContent=`${label} ×`;button.setAttribute('aria-label',`${t('placeRemove')}: ${label}`);
      button.addEventListener('click',()=>{if(state.busy||state.locked)return;discoveryState.selectedPlaces.delete(id);discoveryState.selectedPlaceLabels.delete(id);renderDiscoveryPlaces();});list.append(button);
    }
  }
  async function loadDiscoveryPlaces(){
    if(state.locked||!state.library||!discoveryState.placesAvailable||!discoveryState.binding)return;
    const epoch=state.generation,library=String(state.library),account=String(state.profile?.account_id||''),modeToken=discoveryState.modeToken,binding=discoveryState.binding,load=++discoveryState.facetLoad;const current=()=>!stale(epoch)&&load===discoveryState.facetLoad&&modeToken===discoveryState.modeToken&&binding===discoveryState.binding&&library===String(state.library)&&account===String(state.profile?.account_id||'');
    $('discovery-place-list').replaceChildren();$('discovery-place-pages').hidden=true;$('discovery-places-status').textContent=t('placesLoading');
    try{const result=await request(`/libraries/${encodeURIComponent(library)}/discovery/v1/facets?`+new URLSearchParams({facet:'locations',page:String(discoveryState.placePage),page_size:'24',binding:discoveryState.binding,...(discoveryState.placeQuery?{q:discoveryState.placeQuery}:{})}),{epoch});if(!current())return;discoveryState.placeTotal=Number(result.total)||0;discoveryState.places=Array.isArray(result.items)?result.items:[];renderDiscoveryPlaces();}
    catch(error){if(current()){if(error&&error.status===409){discoveryState.binding=null;discoveryState.placePage=1;void openDiscovery();return;}$('discovery-places-status').textContent=t('placesUnavailable');const retry=document.createElement('button');retry.type='button';retry.className='quiet';retry.textContent=t('placesRetry');retry.addEventListener('click',()=>void loadDiscoveryPlaces());$('discovery-places-status').append(' ',retry);}}
  }
  async function loadDiscovery(applyDraft=false){
    if(state.locked||!state.library)return false;
    if(applyDraft){
      const from=$('discovery-from').value,to=$('discovery-to').value;
      if(from&&to&&from>to){$('discovery-status').textContent=t('discoveryRange');return false;}
      const filters={};if($('discovery-media').value!=='all')filters.media=[$('discovery-media').value];
      if(discoveryState.selectedPlaces.size>20){$('discovery-status').textContent=t('placesLimit');return false;}
      if(discoveryState.selectedPlaces.size)filters.locations=[...discoveryState.selectedPlaces];
      if(from||to)filters.date={from:from||null,to:to||null};
      if(!Object.keys(filters).length){clearDiscoveryMode();state.page=1;return loadGallery();}
      discoveryState.modeToken++;discoveryState.appliedFilters=JSON.parse(JSON.stringify(filters));discoveryState.appliedLocationLabels=new Map(discoveryState.selectedPlaceLabels);
      discoveryState.applied=true;discoveryState.active=true;discoveryState.page=1;discoveryState.fingerprint=null;discoveryState.total=null;
      storyState.search=null;state.page=1;
    }
    if(!discoveryState.active||!discoveryState.appliedFilters)return false;
    if(!discoveryState.binding){$('grid').replaceChildren();$('empty').hidden=true;$('pagination').hidden=true;state.total=0;discoveryState.total=null;renderDiscoverySummary(t('discoveryUpdated'),{retry:true});return false;}
    const epoch=state.generation,library=String(state.library),account=String(state.profile?.account_id||''),load=++discoveryState.searchLoad,ticket=++galleryLoad;
    const current=()=>!stale(epoch)&&load===discoveryState.searchLoad&&ticket===galleryLoad&&discoveryState.active&&library===String(state.library)&&account===String(state.profile?.account_id||'');
    discoveryState.page=state.page;discoveryState.total=null;$('grid').replaceChildren();$('empty').hidden=true;$('pagination').hidden=true;
    $('discovery-status').textContent='';renderDiscoverySummary(t('discoveryWorking'));
    const body={binding:discoveryState.binding,filters:discoveryState.appliedFilters,page:discoveryState.page,page_size:24,fingerprint:discoveryState.page>1?discoveryState.fingerprint:null};
    try{
      const result=await request(`/libraries/${encodeURIComponent(library)}/discovery/v1/search`,{method:'POST',body,epoch});
      if(!current())return false;
      discoveryState.fingerprint=result.fingerprint;discoveryState.total=result.total;state.total=result.total;state.page=discoveryState.page;
      renderGalleryItems(result.items,current,'page');
      $('empty').hidden=result.items.length>0;$('empty').textContent=t('discoveryNone');
      const pages=Math.max(1,Math.ceil(result.total/24));$('pagination').hidden=result.total===0;$('previous').disabled=state.page===1;$('next').disabled=state.page>=pages;
      $('page-input').max=String(pages);$('page-input').value=String(state.page);$('page-label').textContent=`${t('page')} ${state.page} ${t('of')} ${pages} · ${result.total} ${t('photos')}`;
      renderDiscoverySummary(result.total?'':t('discoveryNone'));updateTransferUI();return true;
    }catch(error){
      if(!current())return false;
      $('grid').replaceChildren();$('pagination').hidden=true;state.total=0;discoveryState.total=null;
      if(error&&error.status===409){
        // Never render a page against a stale fingerprint or binding. Keep the
        // selected filters visible and require an explicit snapshot retry.
        discoveryState.binding=null;discoveryState.fingerprint=null;discoveryState.page=1;state.page=1;$('empty').hidden=true;
        renderDiscoverySummary(t('discoveryChanged'),{retry:true});$('discovery-status').textContent=t('discoveryChanged');return false;
      }
      if(error.status===401||error.status===403){await failure(error,epoch);return false;}
      $('empty').hidden=true;renderDiscoverySummary(t('discoveryError'),{retry:true});$('discovery-status').textContent=t('discoveryError');return false;
    }
  }
  async function loadUnassignedFaces(){
    if(state.locked||$('people-panel').hidden||!$('unassigned-section').open)return;
    const epoch=state.generation,library=state.library,load=++unassignedState.load;
    const current=()=>!stale(epoch)&&load===unassignedState.load&&library===state.library&&$('people-panel').open;
    $('unassigned-list').replaceChildren();$('unassigned-pages').hidden=true;$('unassigned-status').textContent=t('loading');
    try{
      const result=await request(libraryPath('/admin/faces',{page:String(unassignedState.page)}),{epoch});
      if(!current())return;
      unassignedState.total=result.total;$('unassigned-status').textContent=result.total?'':t('noUnassignedFaces');
      for(const face of result.items){
        const row=document.createElement('article');row.className='unassigned-card';row.dataset.faceId=face.id;
        const image=document.createElement('img');image.className='assignment-crop';image.alt=`${t('unassigned')} ${face.id}`;image.src=libraryPath(`/faces/${face.id}/crop`);image.loading='lazy';
        image.addEventListener('error',()=>{image.alt=t('previewMissing');},{once:true});
        const source=document.createElement('h4');source.textContent=`${t('unassigned')} · ${t('sourcePhoto')} ${face.asset_id}`;
        row.append(image,source);
        // Assigning here keeps one assignment path: the same picker, revision and
        // conflict rules as the per-photo review. The row leaves on the next load.
        row.append(storyButton('openPhoto',async()=>{
          if(!current()||state.locked||state.busy||!abandonStory())return;
          try{const detail=await request(libraryPath(`/assets/detail/${face.asset_id}`),{epoch});if(current())await openAsset(detail.asset);}
          catch(error){await failure(error,epoch);}
        }));
        row.append(storyButton('choosePerson',()=>{
          if(!current()||state.busy)return;
          row.append(personPicker({face,image,current,epoch,onSaved:loadUnassignedFaces,status:$('unassigned-status'),container:$('unassigned-list')}));
        }));
        $('unassigned-list').append(row);
      }
      const pages=Math.max(1,Math.ceil(result.total/25));$('unassigned-pages').hidden=result.total===0;
      $('unassigned-previous').disabled=unassignedState.page===1;$('unassigned-next').disabled=unassignedState.page>=pages;
      $('unassigned-page-label').textContent=`${t('page')} ${unassignedState.page} ${t('of')} ${pages}`;
    }catch(error){if(current()){$('unassigned-status').textContent=t(errorStatus(error));await failure(error,epoch);}}
  }
  $('directory-panel').addEventListener('toggle',()=>{if($('directory-panel').open)void loadDirectory();});
  $('directory-search').addEventListener('submit',event=>{event.preventDefault();if(state.busy||state.locked)return;directoryState.query=$('directory-query').value.trim();directoryState.page=1;void loadDirectory();});
  $('directory-previous').addEventListener('click',()=>{if(!state.busy&&directoryState.page>1){directoryState.page--;void loadDirectory();}});
  $('directory-next').addEventListener('click',()=>{if(!state.busy&&directoryState.page*25<directoryState.total){directoryState.page++;void loadDirectory();}});
  $('person-previous').addEventListener('click',()=>{if(!state.busy&&directoryState.assetPage>1){directoryState.assetPage--;void loadPersonAssets();}});
  $('person-next').addEventListener('click',()=>{if(!state.busy&&directoryState.assetPage*25<directoryState.assetTotal){directoryState.assetPage++;void loadPersonAssets();}});
  $('tags-panel').addEventListener('toggle',()=>{if($('tags-panel').open)void loadTags();});
  $('family-tags-panel').addEventListener('toggle',()=>{if($('family-tags-panel').open)void loadFamilyTags();});
  $('family-tag-search').addEventListener('submit',event=>{event.preventDefault();if(state.busy||state.locked)return;familyTagState.query=$('family-tag-query').value.trim();familyTagState.page=1;familyTagState.tag=null;$('family-tag-assets').replaceChildren();$('family-tag-asset-pages').hidden=true;void loadFamilyTags();});
  $('family-tag-previous').addEventListener('click',()=>{if(!state.busy&&familyTagState.page>1){familyTagState.page--;void loadFamilyTags();}});
  $('family-tag-next').addEventListener('click',()=>{if(!state.busy&&familyTagState.page*25<familyTagState.total){familyTagState.page++;void loadFamilyTags();}});
  $('family-tag-asset-previous').addEventListener('click',()=>{if(!state.busy&&familyTagState.assetPage>1){familyTagState.assetPage--;void loadFamilyTagAssets();}});
  $('family-tag-asset-next').addEventListener('click',()=>{if(!state.busy&&familyTagState.assetPage*25<familyTagState.assetTotal){familyTagState.assetPage++;void loadFamilyTagAssets();}});
  $('duplicates-panel').addEventListener('toggle',()=>{if($('duplicates-panel').open)void loadDuplicates();});
  $('duplicate-previous').addEventListener('click',()=>{if(!state.busy&&duplicateState.page>1){duplicateState.page--;void loadDuplicates();}});
  $('duplicate-next').addEventListener('click',()=>{if(!state.busy&&duplicateState.page*25<duplicateState.total){duplicateState.page++;void loadDuplicates();}});
  $('tag-search').addEventListener('submit',event=>{event.preventDefault();if(state.busy||state.locked)return;tagState.query=$('tag-query').value.trim();tagState.page=1;void loadTags();});
  $('tag-previous').addEventListener('click',()=>{if(!state.busy&&tagState.page>1){tagState.page--;void loadTags();}});
  $('tag-next').addEventListener('click',()=>{if(!state.busy&&tagState.page*25<tagState.total){tagState.page++;void loadTags();}});
  $('discovery-panel').addEventListener('toggle',async()=>{
    if(!$('discovery-panel').open)return;
    const ready=await openDiscovery();
    if(ready&&discoveryState.active)void loadDiscovery();
  });
  $('discovery-form').addEventListener('submit',event=>{event.preventDefault();if(state.busy||state.locked||!abandonStory())return;void loadDiscovery(true);});
  $('discovery-clear').addEventListener('click',clearGalleryFilters);
  $('discovery-facets-retry').addEventListener('click',()=>{if(state.busy||state.locked)return;void openDiscovery().then(ready=>{if(ready&&discoveryState.active)void loadDiscovery();});});
  $('discovery-place-search').addEventListener('submit',event=>{
    event.preventDefault();if(state.busy||state.locked)return;
    const query=$('discovery-place-query').value.trim();
    if(new TextEncoder().encode(query).length>128){$('discovery-places-status').textContent=t('placeSearchTooLong');return;}
    discoveryState.placeQuery=query;discoveryState.placePage=1;void loadDiscoveryPlaces();
  });
  $('discovery-place-previous').addEventListener('click',()=>{if(!state.busy&&discoveryState.placePage>1){discoveryState.placePage--;void loadDiscoveryPlaces();}});
  $('discovery-place-next').addEventListener('click',()=>{if(!state.busy&&discoveryState.placePage*24<discoveryState.placeTotal){discoveryState.placePage++;void loadDiscoveryPlaces();}});
  $('people-panel').addEventListener('toggle',()=>{if($('people-panel').open){void loadPeople();if($('unassigned-section').open)void loadUnassignedFaces();}});
  $('people-search').addEventListener('submit',event=>{event.preventDefault();if(state.busy||state.locked)return;peopleState.query=$('people-query').value.trim();peopleState.page=1;void loadPeople();});
  $('people-named').addEventListener('change',()=>{if(state.busy||state.locked)return;peopleState.named=$('people-named').value;peopleState.page=1;void loadPeople();});
  $('people-previous').addEventListener('click',()=>{if(!state.busy&&peopleState.page>1){peopleState.page--;void loadPeople();}});
  $('people-next').addEventListener('click',()=>{if(!state.busy&&peopleState.page*25<peopleState.total){peopleState.page++;void loadPeople();}});
  $('unassigned-section').addEventListener('toggle',()=>{if($('unassigned-section').open)void loadUnassignedFaces();});
  $('unassigned-previous').addEventListener('click',()=>{if(!state.busy&&unassignedState.page>1){unassignedState.page--;void loadUnassignedFaces();}});
  $('unassigned-next').addEventListener('click',()=>{if(!state.busy&&unassignedState.page*25<unassignedState.total){unassignedState.page++;void loadUnassignedFaces();}});
  const channel=typeof BroadcastChannel==='function'?new BroadcastChannel('photohouse-session'):null;
  if(channel)channel.onmessage=()=>{if(!state.locked&&!state.busy){suspendDraft();if(document.hidden)invalidate();else void restoreWithDraft();}};
  $('auth-form').addEventListener('submit',event=>{void signIn(event);});
  $('login-tab').addEventListener('click',()=>setMode('login'));
  $('register-tab').addEventListener('click',()=>setMode('register'));
  // Native validation can block submit entirely; mirror its first error near the button.
  $('auth-form').addEventListener('invalid',event=>{
    if(event.target!==$('auth-form').querySelector(':invalid'))return;
    const key={phone:'invalidPhone',password:state.mode==='register'?'invalidPassword':'enterPassword',name:'invalidName',code:'invalidCode'}[event.target.id];
    if(key)status(key);
  },true);
  Object.assign(words.zh,{assistantTitle:'PhotoHouse 助手',assistantFindPhotos:'找照片',assistantFindVideos:'找视频',assistantOpenFirst:'打开第一个',storyWorkspaceAlbum:'用这些画面编排故事',storyWorkspaceResults:'把这些结果编排成故事'});
  Object.assign(words.en,{assistantTitle:'Your PhotoHouse companion',assistantFindPhotos:'Find photos',assistantFindVideos:'Find videos',assistantOpenFirst:'Open the first result',storyWorkspaceAlbum:'Shape a story from these frames',storyWorkspaceResults:'Shape a story from these results'});
  const focusAssistant=()=>{$('assistant-panel').open=true;$('assistant-panel').scrollIntoView({behavior:'smooth',block:'start'});$('assistant-text').focus();};
  const memoryScope=()=>{const membership=state.profile?.memberships?.find(item=>item.library_id===state.library&&item.available===true),revision=membership?.revision;return {account:state.profile?.account_id,library:state.library,membership_revision:Number.isSafeInteger(revision)&&revision>0?revision:null,language:state.language,locked:state.locked};};
  const communityRequest=(path,options={})=>{
    if(!/^\/(?:memory-community\/v1\/|memory-stories(?:\/|\?|$))/.test(path))throw new Error('Invalid memory route');
    const [base,query]=path.split('?');
    return request(libraryPath(base,Object.fromEntries(new URLSearchParams(query||''))),
      {...options,extraHeaders:options.headers,epoch:state.generation});
  };
  memoryCommunity=window.PhotoHouseMemoryCommunity({scope:memoryScope,request:communityRequest,
    mediaURL:id=>safeMediaURL(id,'thumbnail'),capture:annotationCapture,
    voiceCapabilities:()=>request(`/assistant/v1/capabilities?${new URLSearchParams({library_id:state.library||''})}`,{epoch:state.generation}),
    transcribe:file=>request('/assistant/v1/transcribe',{method:'POST',rawBody:file,
      extraHeaders:{'Content-Type':'audio/wav','X-PhotoHouse-Library-Id':state.library,'X-PhotoHouse-Request-Id':crypto.randomUUID()}}),
    onError:error=>{void failure(error,state.generation);},
    mountReplySpeech:(...args)=>storyWorkspace?.mountReplySpeech?.(...args)??(()=>{}),
    onProposal:proposal=>{void storyWorkspace?.acceptProposal(proposal);},
    onOpenStory:value=>{if(typeof value==='string')void storyWorkspace?.reopen(value);else storyWorkspace?.openBook(value);},
    onOpenBookStory:context=>storyWorkspace?.openBookStory(context)??false});
  storyWorkspace=window.PhotoHouseStoryWorkspace({scope:()=>({account:state.profile?.account_id,library:state.library,language:state.language,locked:state.locked}),
    community:memoryCommunity,
    request:body=>request(libraryPath('/story-workspace/preview'),{method:'POST',body,epoch:state.generation}),
    relatedRequest:body=>request(libraryPath('/story-workspace/related-media'),{method:'POST',body,epoch:state.generation}),
    titleRequest:(path,options={})=>{
      if(!['/story-workspace/title-capabilities','/story-workspace/title-suggestions'].includes(path))throw new Error('Invalid title route');
      return request(libraryPath(path),{...options,epoch:state.generation});},
    mediaURL:(id,variant)=>safeMediaURL(id,'thumbnail',variant==='preview'?{size:'1024'}:{}),
    openAsset:item=>{void openAsset(item);},onError:error=>{void failure(error,state.generation);},openAssistant:title=>{if(title){$('assistant-text').value=(state.language==='en'?'find photos ':'找照片 ')+title;assistantState.context=null;}focusAssistant();},
    savedRequest:(path,options={})=>{const [base,query]=path.split('?');return request(libraryPath(base,Object.fromEntries(new URLSearchParams(query||''))),{...options,epoch:state.generation});}});
  $('assistant-prompts').addEventListener('click',event=>{const kind=event.target.dataset.assistantPrompt;if(!kind||state.locked||assistantState.busy)return;$('assistant-text').value=t({photos:'assistantFindPhotos',videos:'assistantFindVideos',open:'assistantOpenFirst'}[kind]);focusAssistant();});
  Object.assign(words.zh,{memoryNavigation:'回忆导航',memoryNavStories:'故事',memoryNavMemoirs:'回忆集',memoryMediaRegion:'照片与视频'});
  Object.assign(words.en,{memoryNavigation:'Memory navigation',memoryNavStories:'Stories',memoryNavMemoirs:'Memoirs',memoryMediaRegion:'Photos and videos'});
  const memoryNavigation=$('memory-navigation'),memoryLinks=[...memoryNavigation.querySelectorAll('a')];
  let memoryNavigationFrame=0;
  const visibleMemoryTargets=()=>memoryLinks.filter(link=>!link.hidden).map(link=>({link,target:$(link.hash.slice(1))})).filter(item=>item.target&&!item.target.hidden&&item.target.getClientRects().length);
  const updateMemoryNavigation=()=>{
    memoryNavigationFrame=0;$('memory-books-link').hidden=$('memory-books').hidden;
    document.documentElement.style.setProperty('--memory-navigation-offset',`${memoryNavigation.getBoundingClientRect().height+24}px`);
    for(const link of memoryLinks)link.removeAttribute('aria-current');
    if($('library').hidden||state.locked)return;
    const targets=visibleMemoryTargets().sort((a,b)=>a.target.getBoundingClientRect().top-b.target.getBoundingClientRect().top);
    const edge=memoryNavigation.getBoundingClientRect().bottom+24;
    const preceding=targets.filter(item=>item.target.getBoundingClientRect().top<=edge);
    const active=preceding.at(-1)||targets[0];active?.link.setAttribute('aria-current','location');
  };
  const scheduleMemoryNavigation=()=>{if(!memoryNavigationFrame)memoryNavigationFrame=requestAnimationFrame(updateMemoryNavigation);};
  window.addEventListener('scroll',scheduleMemoryNavigation,{passive:true});window.addEventListener('resize',scheduleMemoryNavigation);
  const memoryNavigationObserver=new MutationObserver(scheduleMemoryNavigation);
  for(const target of [$('library'),$('memory-books')])memoryNavigationObserver.observe(target,{attributes:true,attributeFilter:['hidden']});
  for(const link of memoryLinks)link.addEventListener('click',event=>{
    event.preventDefault();if(state.locked||$('library').hidden||link.hidden)return;
    const target=$(link.hash.slice(1));if(!target||target.hidden)return;
    if(target.id==='albums-panel'){target.open=true;void loadAlbums();}
    if(target.id==='assistant-panel')target.open=true;
    const focusTarget=target.id==='assistant-panel'&&!$('assistant-form').hidden?$('assistant-text'):target.querySelector('summary,h2,h3')||target;
    if(!focusTarget.hasAttribute('tabindex')&&!focusTarget.matches('input,textarea,button,a,summary'))focusTarget.tabIndex=-1;
    document.documentElement.style.setProperty('--memory-navigation-offset',`${memoryNavigation.getBoundingClientRect().height+24}px`);
    history.replaceState(null,'',link.hash);target.scrollIntoView({block:'start'});focusTarget.focus({preventScroll:true});scheduleMemoryNavigation();
  });
  scheduleMemoryNavigation();
  $('logout').addEventListener('click',()=>{void signOut();});
  $('refresh').addEventListener('click',()=>{if(!state.locked&&abandonStory()){state.page=1;discoveryState.page=1;void restore();}});
  $('library-select').addEventListener('change',()=>{if(state.locked||!abandonStory()){$('library-select').value=state.library||'';return;}clearAssistantRecoveryPointer();clearDiscoveryMode({clearInputs:true,clearBinding:true});assistantState.transcribe=false;assistantState.speech=false;resetAssistant();$('assistant-form').hidden=true;assistantState.binding=null;storyState.search=null;storyState.suspended=null;$('search-text').value='';peopleState.page=1;peopleState.query='';$('people-query').value='';familyTagState.page=1;familyTagState.query='';familyTagState.tag=null;familyTagState.assetPage=1;$('family-tag-query').value='';$('family-tag-assets').replaceChildren();$('family-tag-asset-pages').hidden=true;state.library=$('library-select').value;state.page=1;state.memberPage=1;uploadState.page=1;void restore();});
  $('previous').addEventListener('click',()=>{if(!state.busy&&state.page>1&&abandonStory()){state.page--;void loadGallery();}});
  $('next').addEventListener('click',()=>{if(!state.busy&&state.page*24<state.total&&abandonStory()){state.page++;void loadGallery();}});
  $('page-jump').addEventListener('submit',event=>{
    event.preventDefault();
    if(state.locked||!abandonStory())return;
    const pages=Math.max(1,Math.ceil(state.total/24)),value=Number($('page-input').value);
    if(!Number.isInteger(value)||value<1||value>pages){status('pageRange');return;}
    if(value===state.page){status('');return;}
    state.page=value;void loadGallery();
  });
  $('members-panel').addEventListener('toggle',()=>{if($('members-panel').open)void loadMembers();});
  $('member-previous').addEventListener('click',()=>{if(state.memberPage>1){state.memberPage--;void loadMembers();}});
  $('member-next').addEventListener('click',()=>{if(state.memberPage*25<state.memberTotal){state.memberPage++;void loadMembers();}});
  $('my-uploads-open').addEventListener('click',()=>{if(state.locked||state.busy)return;$('my-uploads-panel').open=true;$('my-uploads-panel').scrollIntoView({block:'start'});});
  $('my-uploads-panel').addEventListener('toggle',()=>{if($('my-uploads-panel').open)void loadMyUploads();else clearMyUploads();});
  $('my-uploads-refresh').addEventListener('click',()=>{if(!myUploadsState.busy){myUploadsState.page=1;void loadMyUploads();}});
  $('my-uploads-previous').addEventListener('click',()=>{if(!myUploadsState.busy&&myUploadsState.page>1){myUploadsState.page--;void loadMyUploads();}});
  $('my-uploads-next').addEventListener('click',()=>{if(!myUploadsState.busy&&myUploadsState.page*10<myUploadsState.total){myUploadsState.page++;void loadMyUploads();}});
  $('uploads-open').addEventListener('click',()=>{if(state.locked||state.busy)return;$('uploads-panel').open=true;$('uploads-panel').scrollIntoView({block:'start'});$('uploads-panel').querySelector('summary').focus();});
  $('uploads-panel').addEventListener('toggle',()=>{if($('uploads-panel').open)void loadUploads();});
  $('uploads-refresh').addEventListener('click',()=>{if(!state.busy&&!state.locked){uploadState.page=1;void loadUploads();}});
  $('uploads-previous').addEventListener('click',()=>{if(!state.busy&&uploadState.page>1){uploadState.page--;void loadUploads();}});
  $('uploads-next').addEventListener('click',()=>{if(!state.busy&&uploadState.page*10<uploadState.total){uploadState.page++;void loadUploads();}});
  $('tag-review-panel').addEventListener('toggle',()=>{if($('tag-review-panel').open)void loadProposedTags();else clearProposedTags();});
  $('tag-review-refresh').addEventListener('click',()=>{if(!tagReviewState.busy){tagReviewState.page=1;void loadProposedTags();}});
  $('tag-review-previous').addEventListener('click',()=>{if(!tagReviewState.busy&&tagReviewState.page>1){tagReviewState.page--;void loadProposedTags();}});
  $('tag-review-next').addEventListener('click',()=>{if(!tagReviewState.busy&&tagReviewState.page*10<tagReviewState.total){tagReviewState.page++;void loadProposedTags();}});
  $('upload-review-close').addEventListener('click',closeUploadDialog);
  $('upload-review-cancel').addEventListener('click',closeUploadDialog);
  $('upload-review-approve').addEventListener('click',()=>void approveUpload());
  $('upload-review-dialog').addEventListener('cancel',event=>{event.preventDefault();if(!state.busy)closeUploadDialog();});
  $('close-viewer').addEventListener('click',()=>{if(abandonStory())closeViewer();});
  $('view-previous').addEventListener('click',()=>void movePhoto(-1));$('view-next').addEventListener('click',()=>void movePhoto(1));
  $('view-play').addEventListener('click',()=>{if(sequenceState.playing){stopSlideshow();return;}if(state.busy||storyState.busy||storyState.dirty||!$('story-form').hidden||$('face-panel').open){$('view-quality').textContent=t('viewQuality')+' '+t('viewEditing');return;}sequenceState.playing=true;updateSequence();scheduleSlideshow();});
  $('view-interval').addEventListener('change',scheduleSlideshow);
  $('viewer-filmstrip').addEventListener('click',event=>{
    const button=event.target.closest('[data-viewer-index]');
    if(!button||state.locked||sequenceState.busy)return;
    const index=Number(button.dataset.viewerIndex);
    if(!Number.isInteger(index)||index===sequenceState.index)return;
    if(!abandonStory())return;
    stopSlideshow();
    const {items,origin}=sequenceState;
    if(index<0||index>=items.length)return;
    void openAsset(items[index],{sequence:items,origin,advance:true});
  });
  for(const mode of ['fit','width','height','actual'])$('view-'+mode).addEventListener('click',()=>fitPhoto(mode));
  $('view-in').addEventListener('click',()=>zoomPhoto(1.25));$('view-out').addEventListener('click',()=>zoomPhoto(0.8));
  $('view-fullscreen').addEventListener('click',()=>void fullscreenPhoto());
  document.addEventListener('fullscreenchange',()=>{
    const full=document.fullscreenElement===$('photo-viewer');
    $('view-fullscreen').textContent=t(full?'viewExitFullscreen':'viewFullscreen');
    if(full&&$('photo-viewer').hidden){void document.exitFullscreen().catch(()=>{});return;}
    if(photoState.image)fitPhoto();
  });
  const photoStage=$('viewer-media');
  new ResizeObserver(()=>{if(photoState.image)fitPhoto();}).observe(photoStage);
  photoStage.addEventListener('wheel',event=>{if(!photoState.image?.naturalWidth)return;event.preventDefault();const box=photoStage.getBoundingClientRect();const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?photoStage.clientHeight:1);zoomPhoto(Math.exp(-Math.max(-200,Math.min(200,delta))*0.003),{x:event.clientX-box.left,y:event.clientY-box.top});},{passive:false});
  photoStage.addEventListener('pointerdown',event=>{if(event.button!==0||!photoState.image?.naturalWidth||photoState.drag)return;event.preventDefault();photoStage.focus({preventScroll:true});photoStage.setPointerCapture(event.pointerId);photoState.drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:photoStage.scrollLeft,top:photoStage.scrollTop};photoStage.classList.add('dragging');});
  photoStage.addEventListener('pointermove',event=>{const drag=photoState.drag;if(drag?.id!==event.pointerId)return;photoStage.scrollLeft=drag.left+drag.x-event.clientX;photoStage.scrollTop=drag.top+drag.y-event.clientY;});
  function endPhotoDrag(event){if(photoState.drag?.id!==event.pointerId)return;photoState.drag=null;photoStage.classList.remove('dragging');if(photoStage.hasPointerCapture(event.pointerId))photoStage.releasePointerCapture(event.pointerId);}
  for(const event of ['pointerup','pointercancel','lostpointercapture'])photoStage.addEventListener(event,endPhotoDrag);
  photoStage.addEventListener('keydown',event=>{if(event.ctrlKey||event.metaKey||event.altKey)return;const actions={'+':()=>zoomPhoto(1.25),'=':()=>zoomPhoto(1.25),'-':()=>zoomPhoto(0.8),'0':()=>fitPhoto('fit'),'1':()=>fitPhoto('actual'),ArrowLeft:()=>{photoStage.scrollLeft-=60;},ArrowRight:()=>{photoStage.scrollLeft+=60;},ArrowUp:()=>{photoStage.scrollTop-=60;},ArrowDown:()=>{photoStage.scrollTop+=60;}};if(actions[event.key]){event.preventDefault();actions[event.key]();}});
  $('viewer').addEventListener('cancel',event=>{event.preventDefault();if(abandonStory())closeViewer();});
  $('story-add').addEventListener('click',()=>editStory());
  $('story-form').addEventListener('input',()=>{storyState.dirty=true;});
  $('story-form').addEventListener('submit',event=>{void saveStory(event);});
  $('story-cancel').addEventListener('click',()=>{if(abandonStory()){resetStoryEditor();storyStatus('');}});
  $('story-more').addEventListener('click',()=>{void loadStories(true);});
  $('viewer-annotations-more').addEventListener('click',()=>{if(!$('viewer-annotations-more').disabled)void loadViewerAnnotations(true);});
  $('story-compare').addEventListener('click',()=>{void compareStory();});
  $('story-search').addEventListener('submit',event=>{event.preventDefault();if(state.locked||!abandonStory())return;clearDiscoveryMode();const text=$('search-text').value.trim();storyState.search=text?{text,source:$('search-source').value}:null;state.page=1;void loadGallery();});
  $('assistant-form').addEventListener('submit',event=>{void submitAssistant(event);});
  $('assistant-receipt-check').addEventListener('click',()=>{void checkAssistantReceipt();});
  $('assistant-pending-check').addEventListener('click',()=>{void checkAssistantReceipt();});
  $('assistant-pending-ack').addEventListener('click',()=>acknowledgeAssistantPending(false));
  $('assistant-pending-restore').addEventListener('click',()=>acknowledgeAssistantPending(true));
  $('assistant-text').addEventListener('input',syncAssistantControls);
  $('assistant-clear').addEventListener('click',()=>{if(state.locked)return;if(assistantState.receipt?.recovered&&!assistantState.receipt.recoveryCleared){acknowledgeAssistantRecovery();return;}if(assistantState.pendingTurn){$('assistant-text').value='';syncAssistantControls();return;}clearAssistantRecoveryPointer();resetAssistant();});
  $('assistant-cancel').addEventListener('click',()=>{if(!assistantState.busy)return;if(assistantState.pendingTurn){assistantState.pendingTurn.receipt.cancelled=true;renderAssistantPending();}$('assistant-status').textContent=t('assistantPendingCancelled');assistantState.controller?.abort();});
  $('assistant-mic').addEventListener('pointerdown',event=>{if(!event.isPrimary||assistantState.capture||assistantState.captureStarting)return;event.preventDefault();assistantState.pressPointerId=event.pointerId;assistantState.ignoreMicClick=true;try{$('assistant-mic').setPointerCapture(event.pointerId);}catch{}void startAssistantCapture();});
  $('assistant-mic').addEventListener('pointerup',event=>{if(event.pointerId!==assistantState.pressPointerId)return;assistantState.pressPointerId=null;finishAssistantCapture(true);setTimeout(()=>{assistantState.ignoreMicClick=false;},0);});
  $('assistant-mic').addEventListener('pointercancel',event=>{if(event.pointerId!==assistantState.pressPointerId)return;assistantState.pressPointerId=null;finishAssistantCapture(false);setTimeout(()=>{assistantState.ignoreMicClick=false;},0);});
  $('assistant-mic').addEventListener('click',()=>{if(assistantState.ignoreMicClick){assistantState.ignoreMicClick=false;return;}if(assistantState.capture)finishAssistantCapture(true);else void startAssistantCapture();});
  $('assistant-stop').addEventListener('click',()=>finishAssistantCapture(true));
  $('assistant-recording-cancel').addEventListener('click',()=>finishAssistantCapture(false));
  $('assistant-use-transcript').addEventListener('click',acceptAssistantTranscript);
  $('assistant-discard-transcript').addEventListener('click',discardAssistantTranscript);
  $('assistant-play').addEventListener('click',()=>void playAssistantSpeech());
  $('assistant-speech-stop').addEventListener('click',()=>stopAssistantSpeech(false));
  $('assistant-speech-audio').addEventListener('ended',()=>{$('assistant-speech-stop').hidden=true;$('assistant-play').disabled=false;try{$('assistant-speech-audio').currentTime=0;}catch{}});
  $('clear-search').addEventListener('click',()=>{if(state.locked||!abandonStory())return;clearDiscoveryMode();storyState.search=null;$('search-text').value='';state.page=1;void loadGallery();});
  $('transfer-move').addEventListener('click',()=>void openTransferReview());
  $('transfer-clear').addEventListener('click',clearTransferSelection);
  $('viewer-move').addEventListener('click',()=>{if(storyState.asset)void openTransferReview([String(storyState.asset.id)]);});
  $('transfer-review-confirm').addEventListener('click',()=>void confirmTransfer());
  $('transfer-review-close').addEventListener('click',()=>{if(!transferState.busy)$('transfer-review').close();});
  $('transfer-review-cancel').addEventListener('click',()=>{if(!transferState.busy)$('transfer-review').close();});
  $('transfer-review').addEventListener('close',()=>{transferState.load++;transferState.review=null;});
  $('transfer-review').addEventListener('cancel',event=>{event.preventDefault();if(!transferState.busy)$('transfer-review').close();});
  $('invite-form').addEventListener('submit',event=>{void invite(event);});
  $('cancel-invite').addEventListener('click',()=>{void cancelInvite();});
  $('accept-form').addEventListener('submit',event=>{void accept(event);});
  $('language').addEventListener('click',()=>{if(!abandonStory())return;state.language=state.language==='en'?'zh':'en';translate();const keepWork=assistantState.pendingTurn||assistantState.busy||assistantState.transcribing||assistantState.transcriptReviewPending||assistantState.capture||assistantState.captureStarting||memoryCommunity?.isBookEditing?.();if(state.profile&&!state.locked&&!keepWork)void restore();});
  window.addEventListener('beforeunload',event=>{if(storyState.dirty||albumState.draft?.dirty){event.preventDefault();event.returnValue='';}});
  window.addEventListener('pagehide',()=>{invalidate();$('password').value='';$('code').value='';});
  window.addEventListener('pageshow',event=>{if(event.persisted&&!state.locked&&!state.busy)void restoreWithDraft();});
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){
      suspendDraft();
      // Hide protected material without cancelling an already-submitted reply.
      invalidate({cancelMemoryJobs:false});
    }else if(!state.busy&&!state.locked)void restoreWithDraft();
  });
  setMode('login');status('checking');void restore();
})();
