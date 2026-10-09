package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import dev.photohouse.playback.PlaybackProgress
import dev.photohouse.playback.PlaybackBookmark
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.*

private const val MEMORY_BOOK_CHAPTER_ASSET_LIMIT = 8

enum class GalleryMedia(val wire: String) { ALL("all"), PHOTOS("image"), VIDEOS("video"), PREPARED_VIDEOS("prepared_video");
    val assetKind get() = if (this == PREPARED_VIDEOS) "video" else wire
}
enum class Message { SESSION_STORAGE_UNAVAILABLE, SIGNED_OUT_LOCAL, SIGNED_OUT_CONFIRMED, SESSION_ENDED, ACCESS_DENIED, UNAVAILABLE, NETWORK_UNAVAILABLE, TLS_ERROR, CLOSED, RATE_LIMITED, INVALID_INPUT, INVALID_RESPONSE, TOO_LARGE, MEDIA_UNAVAILABLE, DISCOVERY_CHANGED, DISCOVERY_INPUT, VIDEO_NOT_READY, VIDEO_CHANGED, VIDEO_BUSY, PLAYBACK_UNAVAILABLE }
data class LiveProblem(val message: Message, val retryAtMillis: Long = 0, val playbackFailure: VideoPlaybackFailure? = null)
/** Only the current page's IDs, never a persistent or cross-library history. */
data class PhotoNavigation(val page: Int, val assetIds: List<String>, val index: Int, val discovery: PhoneDiscoveryState? = null, val media: GalleryMedia = GalleryMedia.ALL, val videoIds: Set<String> = emptySet())
data class StoryReading(val page: Int = 1, val result: ProtectedStoryPage? = null, val busy: Boolean = false, val problem: LiveProblem? = null)
data class SavedMemoryStoriesReading(
    val library: String, val page: Int = 1, val result: SavedMemoryStoryPage? = null,
    val busy: Boolean = false, val unavailable: Boolean = false, val problem: LiveProblem? = null,
    val detail: SavedMemoryStory? = null, val detailBusy: Boolean = false, val detailUnavailable: Boolean = false,
    val selectedSummary: SavedMemoryStorySummary? = null, val selectedChapter: Int = 0,
    val frames: Map<String, ByteArray> = emptyMap(), val heroAssetId: String? = null, val hero: ByteArray? = null,
    val heroBusy: Boolean = false, val covers: Map<String, ByteArray> = emptyMap(), val framesBusy: Boolean = false,
    val community: MemoryCommunityStoryState? = null, val theme: String? = null,
    val contributionReferences: SavedMemoryStoryContributionReferences? = null,
    val contributionReferencesBusy: Boolean = false, val contributionReferencesUnavailable: Boolean = false,
    val contributionDetailChapterId: String? = null, val contributionDetailId: String? = null,
    val contributionDetail: MemoryContributionDetail? = null,
    val contributionDetailBusy: Boolean = false, val contributionDetailUnavailable: Boolean = false,
    val contributionReferenceDraft: Map<String, List<String>>? = null,
    val contributionReferenceSaveBusy: Boolean = false, val contributionReferenceSaveError: Boolean = false,
    val contributionReferenceSaveConflict: Boolean = false,
    val pendingContributionReferenceMutation: SavedMemoryStoryContributionReferencesMutation? = null,
)
data class MemoryBooksReading(
    val library: String, val page: Int = 1, val busy: Boolean = false,
    val capabilities: MemoryCommunityCapabilities? = null, val result: MemoryBookPage? = null,
    val problem: LiveProblem? = null, val selectedBook: MemoryBook? = null,
    val storyIndex: Int? = null, val story: SavedMemoryStory? = null,
    val readerBusy: Boolean = false, val readerUnavailable: Boolean = false,
    val selectedChapter: Int = 0, val selectedAssetId: String? = null,
    val framePage: Int = 0,
    val frames: Map<String, ByteArray> = emptyMap(), val framesBusy: Boolean = false,
    val unavailableFrameIds: Set<String> = emptySet(), val framesUnavailable: Boolean = false,
    val heroAssetId: String? = null, val hero: ByteArray? = null, val heroBusy: Boolean = false,
    val heroUnavailable: Boolean = false,
    val resumePosition: MemoryBookResumePosition? = null,
    /** Changes when this reader opens, closes, or switches to another memoir story. */
    val readerScopeId: Long = 0,
    val sourceInspection: MemoryBookEditorialSourceInspectionState = MemoryBookEditorialSourceInspectionState(),
    val companion: MemoryBookChatState? = null,
)
data class MemoryBookEditorialSourceInspectionState(
    val source: EditorialSourceIdentity? = null,
    val detail: MemoryContributionDetail? = null,
    val busy: Boolean = false,
    val unavailable: Boolean = false,
    val audio: ProtectedAnnotationAudio? = null,
    val audioBusy: Boolean = false,
    val audioUnavailable: Boolean = false,
)
data class MemoryBookChatState(
    val bookId: String, val bookRevision: Long,
    val conversations: MemoryConversationPage? = null, val conversationId: String? = null,
    val turns: MemoryTurnPage? = null, val job: MemoryJob? = null,
    val pendingConversation: MemoryConversationRequest? = null, val pendingTurn: MemoryTurnRequest? = null,
    val pendingTurnConversationId: String? = null,
    /** Composer text stays in memory and is partitioned by conversation ID. */
    val threadDrafts: Map<String, String> = emptyMap(),
    val chatDraftFocusRequestId: Int = 0,
    val draft: String = "", val dictation: MemoryDictationStore? = null,
    val busy: Boolean = false, val failure: LiveProblem? = null,
    /** Selected only after an explicit, scope-bound read of the saved editorial plan. */
    val editorialContext: MemoryBookChatEditorialContext = MemoryBookChatEditorialContext.BASIC,
)
enum class MemoryBookChatEditorialContext { BASIC, CHECKING, READY, UNAVAILABLE, CHANGED, SMALLER_SCOPE, FAILED }
data class MemoryBookResumePosition(val storyId: String, val storyRevision: Long, val chapterId: String)
data class MemoryBookEditorialCatalogState(
    val busy: Boolean = false, val unavailable: Boolean = false,
    val sources: List<EditorialSourceIdentity> = emptyList(),
)
private data class MemoryBookResumeKey(val accountId: String, val library: String, val bookId: String, val bookRevision: Long)
data class MemoryCommunityStoryState(
    val storyId: String, val readerScopeId: Long = 0, val capabilities: MemoryCommunityCapabilities? = null,
    val capabilitiesBusy: Boolean = false, val contributions: MemoryContributionPage? = null,
    val conversations: MemoryConversationPage? = null, val conversationId: String? = null,
    val turns: MemoryTurnPage? = null, val selectedContribution: MemoryContributionDetail? = null,
    val audio: ProtectedAnnotationAudio? = null, val job: MemoryJob? = null,
    val narrativeJob: MemoryJob? = null, val tab: Int = 0,
    val pendingText: MemoryContributionRequest? = null, val pendingAudio: MemoryContributionRequest? = null,
    val pendingConversation: MemoryConversationRequest? = null, val pendingTurn: MemoryTurnRequest? = null,
    val pendingNarrative: MemoryNarrativeRequest? = null,
    /** Composer text stays in memory and is partitioned by conversation ID. */
    val threadDrafts: Map<String, String> = emptyMap(),
    val contributionDraft: String = "", val contributionConsent: Boolean = false, val audioConsent: Boolean = false,
    val contributionWholeStory: Boolean = false,
    val contributionAudioBusy: Boolean = false,
    val contributionAudioActivityId: String? = null,
    val chatTurnContributionSeeded: Boolean = false, val contributionFocusRequestId: Int = 0,
    val contributionLanguage: String = "zh", val chatDraft: String = "", val chatDraftFocusRequestId: Int = 0,
    val dictation: MemoryDictationStore? = null,
    val busy: Boolean = false,
    val failure: LiveProblem? = null,
)

enum class MemoryChatTurnSeedResult { SEEDED, BLOCKED, STALE }
enum class MemoryChatFollowupResult { SELECTED, BLOCKED, STALE }

private fun conversationJobActive(job: MemoryJob?, turns: MemoryTurnPage?): Boolean =
    job?.state in setOf("queued", "running") || turns?.items?.any { it.state in setOf("queued", "running") } == true

private suspend fun fetchBoundChatJob(
    repository: MemoryCommunityRepository, jobId: String, revision: Long, valid: () -> Boolean,
): MemoryJob? = try {
    repository.job(jobId, currentRequest = valid).takeIf { valid() && it.id == jobId && it.kind == "chat" && it.baseRevision == revision }
} catch (e: CancellationException) { throw e }
catch (e: ApiFailure) {
    if (e.status in listOf(401, 403) && valid()) throw e
    null
}
catch (_: Exception) { null }

private suspend fun recoverPendingChatJob(
    repository: MemoryCommunityRepository, turns: MemoryTurnPage, revision: Long, valid: () -> Boolean,
): MemoryJob? {
    val pending = turns.items.filter { it.state in setOf("queued", "running") && it.jobId != null }
    if (pending.size != 1 || !valid()) return null
    return fetchBoundChatJob(repository, pending.single().jobId!!, revision, valid)
}

private fun dictationHasUnfinishedInput(dictation: MemoryDictationStore?): Boolean =
    dictation?.state?.value?.let { it.loading || it.recording || it.transcribing || it.transcript != null } == true

private fun nextRequestId(current: Int): Int = if (current == Int.MAX_VALUE) 1 else current + 1

private fun rememberThreadDraft(
    existing: Map<String, String>, activeId: String?, draft: String, conversations: MemoryConversationPage?,
): Map<String, String> {
    if (activeId == null) return existing
    val ids = conversations?.items?.map { it.id }?.take(8).orEmpty().toMutableList()
    if (activeId !in ids) {
        if (ids.size == 8) ids.removeAt(ids.lastIndex)
        ids += activeId
    }
    val allowed = ids.toSet()
    val updated = existing + (activeId to draft)
    return updated.filterKeys { it in allowed }
}

private fun mergeThreadDraftChanges(
    result: Map<String, String>, before: Map<String, String>, live: Map<String, String>,
    sourceId: String?, sourceBeforeDraft: String, sourceLiveDraft: String,
    targetId: String?, targetDraft: String, conversations: MemoryConversationPage?,
): Map<String, String> {
    val merged = result.toMutableMap()
    (before.keys + live.keys).forEach { id ->
        if (before[id] != live[id]) {
            if (id in live) merged[id] = live.getValue(id) else merged.remove(id)
        }
    }
    if (sourceId != null && sourceBeforeDraft != sourceLiveDraft) merged[sourceId] = sourceLiveDraft
    return rememberThreadDraft(merged, targetId, targetDraft, conversations)
}
data class FamilyTagsBrowsing(
    val query: String = "", val page: Int = 1, val result: FamilyTagsPage? = null,
    val selectedTag: String? = null, val assetPage: Int = 1, val busy: Boolean = false, val problem: LiveProblem? = null,
)
data class UploadHistoryState(val page: Int = 1, val total: Int = 0, val items: List<UploadHistoryItem> = emptyList(), val busy: Boolean = false, val unavailable: Boolean = false)
data class UploadAnnotationWriteState(
    val library: String, val request: UploadTextAnnotationRequest, val busy: Boolean = false,
    val result: UploadAnnotation? = null, val failure: ApiFailure? = null,
)
data class UploadAudioAnnotationWriteState(
    val library: String, val request: UploadAudioAnnotationRequest, val busy: Boolean = false,
    val result: UploadAnnotation? = null, val failure: ApiFailure? = null,
)
data class UploadAnnotationReadState(
    val library: String, val assetId: String, val page: Int = 1, val result: UploadAnnotationPage? = null,
    val busy: Boolean = false, val failure: ApiFailure? = null,
)
data class UploadAnnotationAudioState(
    val library: String, val annotationId: String, val assetId: String, val busy: Boolean = false,
    val audio: ProtectedAnnotationAudio? = null, val failure: ApiFailure? = null,
)
data class AssistantExchange(val text: String, val turn: AssistantTurn)
/** Immutable request details retained only in the active assistant scope if the POST outcome is uncertain. */
data class AssistantPendingTurn(
    val accountId: String, val library: String, val generation: Long,
    val text: String, val context: kotlinx.serialization.json.JsonObject?,
    val parentRequestId: String?, val requestId: String,
)
data class AssistantClientState(
    val library: String, val generation: Long, val capabilities: AssistantCapabilities? = null,
    val loadingCapabilities: Boolean = false, val turns: List<AssistantExchange> = emptyList(),
    val context: kotlinx.serialization.json.JsonObject? = null, val busy: Boolean = false,
    val transcribing: Boolean = false, val transcript: AssistantTranscript? = null,
    val speechBusy: Boolean = false, val speechAudio: ProtectedAnnotationAudio? = null,
    val pendingTurn: AssistantPendingTurn? = null,
    val lastRequestReceipt: AssistantRequestReceipt? = null, val receiptDetail: AssistantReceipt? = null,
    val confirmedTranscriptRequestId: String? = null,
    val receiptChecking: Boolean = false, val receiptCheckFailed: Boolean = false,
    val failure: LiveProblem? = null,
)
data class GroupedStoryCreationState(
    val checking: Boolean = false, val canCreate: Boolean? = null,
    val editor: StoryWorkspaceStore? = null, val gallery: Gallery? = null,
    val previews: Map<String, ByteArray> = emptyMap(), val pageBusy: Boolean = false,
    val problem: LiveProblem? = null,
)
data class LiveState(
    val generation: Long = 0, val session: Session? = null, val library: String? = null,
    val gallery: Gallery? = null, val detail: Detail? = null, val captions: Captions? = null,
    val previews: Map<String, ByteArray> = emptyMap(), val busy: Boolean = false,
    val covered: Boolean = false, val problem: LiveProblem? = null,
    val photoNavigation: PhotoNavigation? = null,
    val video: VideoReader? = null,
    val videoBookmark: PlaybackBookmark? = null,
    val viewingOriginal: Boolean = false, val originalPhoto: ByteArray? = null,
    val photoSlideshow: Boolean = false, val photoOriginalQuality: Boolean = false,
    val photoPreviewOnly: Boolean = false,
    val discovery: PhoneDiscoveryState? = null,
    val stories: StoryReading? = null,
    val savedMemoryStories: SavedMemoryStoriesReading? = null,
    val groupedStoryCreation: GroupedStoryCreationState? = null,
    val memoryBooks: MemoryBooksReading? = null,
    val familyTags: FamilyTagsBrowsing? = null,
    val media: GalleryMedia = GalleryMedia.ALL,
    val storyEditor: ProtectedStoryEditorStore? = null,
    val upload: UploadStore? = null,
    val uploadHistory: UploadHistoryState? = null,
    val uploadAnnotationWrite: UploadAnnotationWriteState? = null,
    val uploadAudioAnnotationWrite: UploadAudioAnnotationWriteState? = null,
    val uploadAnnotationRead: UploadAnnotationReadState? = null,
    val uploadAnnotationAudio: UploadAnnotationAudioState? = null,
    val assistant: AssistantClientState? = null,
)

/** UI-dispatcher-confined; only the wire DTO module is shared with fixture code. */
class ConnectedStore(private val api: PhotoHouseApi, private val scope: CoroutineScope, private val persistence: SessionPersistence? = null, private val uploadNetwork: () -> UploadNetwork = { UploadNetwork.UNKNOWN }, batchPersistence: UploadQueuePersistence? = null, batchSource: ((UploadQueueRecord) -> BatchUploadSource?)? = null, memoryCommunityApi: MemoryCommunityApi? = null, private val memoryCommunityEnabled: Boolean = false, private val now: () -> Long = System::currentTimeMillis) {
    private var assistantSpeechRequest = 0L
    private var assistantTurnRequest = 0L
    private var assistantTranscriptRequest = 0L
    private val mutable = MutableStateFlow(LiveState())
    val state = mutable.asStateFlow()
    private val playbackProgress = PlaybackProgress()
    private var restorationAttempted = false
    private var resumeLibrary: String? = null
    private var token: Bearer? = null
    private var identity: Session? = null
    private var deadline = 0L
    private var cooldownUntil = 0L
    private fun coolingDown() = now() < cooldownUntil
    private var expiryJob: Job? = null
    private val requests = mutableSetOf<Job>()
    private var retry: (() -> Unit)? = null
    private var uploadHistoryRequest = 0L
    private var uploadAnnotationAudioRequest = 0L
    private var uploadAnnotationAudioJob: Job? = null
    private var groupedStoryRequest = 0L
    private var groupedStoryPageRequest = 0L
    private var savedMemoryListRequest = 0L
    private var savedMemoryDetailRequest = 0L
    private var savedMemoryReaderEpoch = 0L
    private var savedMemoryContributionReferencesRequest = 0L
    private var savedMemoryContributionDetailRequest = 0L
    private var savedMemoryContributionChapterEpoch = 0L
    private var savedMemoryContributionReferenceSaveRequest = 0L
    private var savedMemoryFramesRequest = 0L
    private var savedMemoryCoversRequest = 0L
    private var savedMemoryHeroRequest = 0L
    private var memoryBooksRequest = 0L
    private var memoryBooksReaderRequest = 0L
    private var memoryBookEditorialRequest = 0L
    private var memoryBookSourceInspectionRequest = 0L
    private var memoryBookSourceInspectionJob: Job? = null
    private val memoryBookEditorialApi = (memoryCommunityApi as? MemoryBookEditorialApi) ?: object : MemoryBookEditorialApi {
        override suspend fun getBookEditorial(token: Bearer, library: String, bookId: String): ByteArray = throw ApiFailure(FailureKind.HTTP, 503)
        override suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String): ByteArray = throw ApiFailure(FailureKind.HTTP, 503)
    }
    private val editorialStore = MemoryBookEditorialStore(MemoryBookEditorialRepository(memoryBookEditorialApi))
    private var memoryBookEditorialLoadedKey: String? = null
    val memoryBookEditorialState get() = editorialStore.state
    private val memoryBookEditorialCatalog = MutableStateFlow(MemoryBookEditorialCatalogState())
    val memoryBookEditorialCatalogState = memoryBookEditorialCatalog.asStateFlow()
    private var memoryBooksMediaRequest = 0L
    private val memoryBookResume = LinkedHashMap<MemoryBookResumeKey, MemoryBookResumePosition>()
    private var communityEpoch = 0L
    private var bookChatEpoch = 0L
    private val bookChatJobs = mutableSetOf<Job>()
    private val communityJobs = mutableSetOf<Job>()
    private var communityPendingAudio: ByteArray? = null
    private val memoryCommunity = memoryCommunityApi?.takeIf { memoryCommunityEnabled }?.let { communityApi ->
        MemoryCommunityRepository(communityApi, currentBinding = {
            val currentToken = token
            val currentLibrary = state.value.library
            if (currentToken != null && currentLibrary != null && usable())
                MemoryCommunityBinding(currentToken, currentLibrary, state.value.generation) else null
        }, onDenied = ::memoryCommunityDenied)
    }
    private val bookNarrativeStore = memoryCommunity?.let {
        MemoryBookNarrativeStore(it, scope, ::currentMemoryBookNarrativeScope)
    }
    private val emptyBookNarrativeState = MutableStateFlow(MemoryBookNarrativeStoreState())
    val memoryBookNarrativeState get() = bookNarrativeStore?.state ?: emptyBookNarrativeState.asStateFlow()
    private val bookEditionStore = (memoryCommunityApi as? MemoryBookEditionApi)?.takeIf { memoryCommunityEnabled }?.let { editionApi ->
        val repository = MemoryBookEditionRepository(editionApi, currentBinding = {
            val credential = token
            val library = state.value.library
            if (credential != null && library != null && usable())
                MemoryCommunityBinding(credential, library, state.value.generation) else null
        }, onDenied = ::memoryCommunityDenied)
        MemoryBookEditionStore(repository, scope, ::currentMemoryBookNarrativeScope)
    }
    private val emptyBookEditionState = MutableStateFlow(MemoryBookEditionStoreState())
    val memoryBookEditionState get() = bookEditionStore?.state ?: emptyBookEditionState.asStateFlow()
    val memoryBookEditionAvailable get() = bookEditionStore != null
    private val bookEditionShelfStore = (memoryCommunityApi as? MemoryBookEditionApi)?.takeIf { memoryCommunityEnabled }?.let { editionApi ->
        val repository = MemoryBookEditionRepository(editionApi, currentBinding = {
            val credential = token
            val library = state.value.library
            if (credential != null && library != null && usable())
                MemoryCommunityBinding(credential, library, state.value.generation) else null
        }, onDenied = ::memoryCommunityDenied)
        MemoryBookEditionShelfStore(repository, scope, ::currentMemoryBookNarrativeScope, ::clearMemoryBookEditionSources)
    }
    private val emptyBookEditionShelfState = MutableStateFlow(MemoryBookEditionShelfState())
    val memoryBookEditionShelfState get() = bookEditionShelfStore?.state ?: emptyBookEditionShelfState.asStateFlow()
    private val bookEditionSourceStore = (memoryCommunityApi as? MemoryBookEditionSourceApi)?.takeIf { memoryCommunityEnabled }?.let { sourceApi ->
        val repository = MemoryBookEditionSourceRepository(sourceApi,currentBinding = {
            val credential = token
            val library = state.value.library
            if (credential != null && library != null && usable())
                MemoryCommunityBinding(credential,library,state.value.generation) else null
        },onDenied = ::memoryCommunityDenied)
        MemoryBookEditionSourceStore(repository,scope,::currentMemoryBookEditionSourceScope,
            onEditionInvalidated = { bookEditionShelfStore?.invalidateReading() })
    }
    private val emptyBookEditionSourceState = MutableStateFlow(MemoryBookEditionSourceState())
    val memoryBookEditionSourceState get() = bookEditionSourceStore?.state ?: emptyBookEditionSourceState.asStateFlow()
    val memoryBookEditionSourceAvailable get() = bookEditionSourceStore != null
    private val bookNarrativeDictation = MemoryBookNarrativeDictationStore(
        api, scope, ::currentMemoryBookNarrativeScope, ::memoryCommunityDenied)
    val memoryBookNarrativeDictationState get() = bookNarrativeDictation.state
    private val batchQueue = if (batchPersistence != null && batchSource != null) BatchUploadQueue(api, scope, batchPersistence, batchSource,
        valid = { usable() }, token = { token ?: throw ApiFailure(FailureKind.HTTP, 401) },
        destinationAllowed = { library -> identity?.memberships?.any { it.library_id == library && it.available } == true }) else null
    val batchUploads get() = batchQueue
    val groupedStoryCreationAvailable get() = api.protectedNativeV2Enabled && api is StoryWorkspaceApi
    val protectedNativeV2Enabled get() = api.protectedNativeV2Enabled
    val mediaFilterEnabled get() = api.mediaFilterEnabled
    val preparedBrowseEnabled get() = api.preparedBrowseEnabled
    val canRememberSession get() = persistence != null
    val preparedVideoEnabled get() = api.preparedVideoEnabled
    val photoDeliveryEnabled get() = api.photoDeliveryEnabled
    val discoveryEnabled get() = api.discoveryEnabled
    val familyTagsEnabled get() = api.familyTagsEnabled
    val assistantEnabled get() = api.assistantEnabled
    val memoryCommunityAvailable get() = memoryCommunityEnabled && memoryCommunity != null
    val uploadEnabled get() = api.uploadEnabled
    val hasSession get() = token != null
    val cachedBytes get() = state.value.previews.values.sumOf { it.size }

    private fun invalidate(keepIdentity: Boolean, cover: Boolean = false) {
        clearMemoryBookEditorial()
        val previous = state.value
        groupedStoryRequest++; groupedStoryPageRequest++
        previous.groupedStoryCreation?.editor?.clear()
        previous.groupedStoryCreation?.previews?.values?.forEach { it.fill(0) }
        previous.savedMemoryStories?.frames?.values?.forEach { it.fill(0) }
        previous.savedMemoryStories?.hero?.fill(0)
        previous.savedMemoryStories?.covers?.values?.forEach { it.fill(0) }
        previous.memoryBooks?.frames?.values?.forEach { it.fill(0) }
        previous.memoryBooks?.hero?.fill(0)
        invalidateBookChatRequests()
        previous.memoryBooks?.companion?.dictation?.close()
        clearMemoryCommunity(clearState = false)
        memoryBooksRequest++; memoryBooksReaderRequest++
        memoryBooksMediaRequest++
        memoryBookResume.clear()
        savedMemoryListRequest++; savedMemoryDetailRequest++; savedMemoryFramesRequest++; savedMemoryCoversRequest++; savedMemoryHeroRequest++
        savedMemoryReaderEpoch++; savedMemoryContributionReferencesRequest++; savedMemoryContributionDetailRequest++
        savedMemoryContributionChapterEpoch++
        assistantSpeechRequest++
        assistantTurnRequest++
        assistantTranscriptRequest++
        val nextGeneration = previous.generation + 1
        state.value.videoBookmark?.close()
        state.value.video?.close()
        state.value.storyEditor?.close()
        state.value.upload?.close()
        state.value.uploadAnnotationAudio?.audio?.close()
        state.value.assistant?.speechAudio?.close()
        uploadAnnotationAudioRequest++
        uploadAnnotationAudioJob = null
        requests.toList().forEach { it.cancel() }; requests.clear(); retry = null
        var storageFailed = false
        if (!keepIdentity) {
            batchQueue?.detach()
            resumeLibrary = null
            playbackProgress.clear()
            storageFailed = runCatching { persistence?.clear() }.isFailure
            token = null; identity = null; deadline = 0; expiryJob?.cancel(); expiryJob = null }
        val assistant = previous.assistant?.takeIf { keepIdentity && !cover && previous.library == it.library }
            ?.copy(generation = nextGeneration, loadingCapabilities = false, busy = false, speechBusy = false, speechAudio = null, pendingTurn = null)
        mutable.value = LiveState(generation = nextGeneration, session = if (cover) null else identity, covered = cover,
            assistant = assistant,
            problem = if (storageFailed) LiveProblem(Message.SESSION_STORAGE_UNAVAILABLE) else if (coolingDown()) LiveProblem(Message.RATE_LIMITED, cooldownUntil) else null)
    }
    private fun active(generation: Long): Boolean {
        if (state.value.generation != generation) return false
        if (token != null && now() >= deadline) { expire(); return false }
        return true
    }
    private fun usable(): Boolean = !state.value.covered && token != null && active(state.value.generation)
    private fun allowed(): Boolean = usable() && identity?.memberships?.any { it.library_id == state.value.library && it.available } == true
    private fun launch(block: suspend (Long) -> Unit) {
        val generation = state.value.generation
        val job = scope.launch {
            try { block(generation) }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (active(generation)) mutable.value = state.value.copy(busy = false, problem = problem(e))
            }
        }
        requests += job
        job.invokeOnCompletion { requests.remove(job) }
    }
    /** Restore only a still-valid credential, then reauthorize before showing any private data. */
    fun restoreSession() {
        if (restorationAttempted || token != null || state.value.busy) return
        restorationAttempted = true
        val saved = runCatching { persistence?.load() }.getOrElse {
            mutable.value = state.value.copy(problem = LiveProblem(Message.SESSION_STORAGE_UNAVAILABLE)); return
        } ?: return
        val credential = runCatching {
            require(saved.issuedAtMillis >= 0 && saved.issuedAtMillis <= now() &&
                saved.expiresAtMillis > now() && saved.expiresAtMillis - saved.issuedAtMillis == 86400000L)
            Bearer.from(SessionToken(86400, saved.accessToken, "Bearer"))
        }.getOrElse { invalidate(keepIdentity = false); return }
        token = credential; deadline = saved.expiresAtMillis
        armExpiry(credential)
        mutable.value = state.value.copy(covered = true)
        foreground()
    }
    private fun armExpiry(credential: Bearer) {
        expiryJob?.cancel()
        expiryJob = scope.launch {
            delay((deadline - now()).coerceAtLeast(0))
            if (token === credential) expire()
        }
    }
    fun authenticate(phone: String, password: String, invitation: String? = null, name: String? = null, remember: Boolean = true) {
        if (state.value.busy || coolingDown()) return
        restorationAttempted = true
        invalidate(keepIdentity = false)
        if (state.value.problem?.message == Message.SESSION_STORAGE_UNAVAILABLE) return
        mutable.value = state.value.copy(busy = true)
        launch { generation ->
            Admission.phone(phone); Admission.password(password, protectedNativeV2 = api.protectedNativeV2Enabled, registration = invitation != null)
            val issuedAt = now()
            val response = when {
                invitation == null -> api.login(phone, password)
                api.protectedNativeV2Enabled -> api.registerNamed(phone, password, invitation, Admission.displayName(name.orEmpty()))
                else -> api.register(phone, password, invitation)
            }
            if (!active(generation)) return@launch
            val credential = runCatching { Bearer.from(response) }.getOrElse { throw ApiFailure(FailureKind.INVALID_RESPONSE) }
            val session = api.session(credential)
            if (!active(generation)) return@launch
            validateSession(session)
            val expiresAt = issuedAt + response.expires_in * 1000
            if (now() >= expiresAt) { expire(); return@launch }
            token = credential; identity = session; deadline = expiresAt
            batchQueue?.attach(session.account_id)
            armExpiry(credential)
            val saved = !remember || runCatching {
                persistence?.save(RememberedSession(response.access_token, issuedAt, expiresAt))
            }.isSuccess
            mutable.value = state.value.copy(session = session, busy = false,
                problem = if (!saved) LiveProblem(Message.SESSION_STORAGE_UNAVAILABLE) else state.value.problem)
            openPreferredLibrary(session)
        }
    }
    /** Stories stay scoped to this visible detail and never enter Home/TV state. */
    fun loadStories(page: Int = 1) {
        if (!api.protectedNativeV2Enabled || !allowed() || state.value.busy ||
            state.value.stories?.busy == true || state.value.viewingOriginal || state.value.video != null ||
            coolingDown() || state.value.storyEditor != null || page !in 1..100000) return
        val detail = state.value.detail ?: return
        val library = state.value.library!!; val credential = token!!
        mutable.value = state.value.copy(stories = StoryReading(page, busy = true))
        launch { generation ->
            try {
                val result = api.stories(credential, library, detail.asset.id, page)
                if (!active(generation)) return@launch
                validResponse(result.libraryId == library && result.assetId == detail.asset.id && result.page == page &&
                    result.items.size <= 5 && result.items.all { it.assetId == detail.asset.id } &&
                    result.items.map { it.id }.distinct().size == result.items.size)
                mutable.value = state.value.copy(stories = StoryReading(page, result))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation)) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) {
                    readFailure(e, generation, credential) { openPhoto(detail.asset.id, null) }
                } else mutable.value = state.value.copy(stories = StoryReading(page, problem = problem(e)))
            }
        }
    }

    /** Explicit creation entry. Actual protected can_create, not a UI role label, grants this editor. */
    fun beginGroupedStoryCreation(): Boolean {
        val workspace = api as? StoryWorkspaceApi ?: return false
        if (!groupedStoryCreationAvailable || !allowed() || state.value.busy || coolingDown() ||
            state.value.detail != null || state.value.savedMemoryStories != null || state.value.memoryBooks != null ||
            state.value.groupedStoryCreation?.checking == true) return false
        if (state.value.groupedStoryCreation?.editor != null) return true
        val library = state.value.library ?: return false
        val credential = token ?: return false
        val request = ++groupedStoryRequest
        mutable.value = state.value.copy(groupedStoryCreation = GroupedStoryCreationState(checking = true))
        launch { generation ->
            try {
                val capability = api.savedMemoryStories(credential, library, 1)
                if (!active(generation) || token !== credential || state.value.library != library || request != groupedStoryRequest) return@launch
                validResponse(capability.libraryId == library && capability.page == 1 && capability.pageSize == 8 && capability.items.size <= 8)
                if (!capability.canCreate) {
                    mutable.value = state.value.copy(groupedStoryCreation = GroupedStoryCreationState(canCreate = false))
                    return@launch
                }
                val binding = {
                    val current = token
                    val selectedLibrary = state.value.library
                    if (current != null && selectedLibrary != null && allowed())
                        MemoryCommunityBinding(current, selectedLibrary, state.value.generation) else null
                }
                val repository = StoryWorkspaceRepository(workspace, binding, onDenied = {
                    if (token != null) {
                        invalidate(keepIdentity = true, cover = true)
                        mutable.value = state.value.copy(problem = LiveProblem(Message.ACCESS_DENIED))
                        retry = { foreground() }
                    }
                })
                val editor = StoryWorkspaceStore(repository, scope, binding)
                mutable.value = state.value.copy(groupedStoryCreation = GroupedStoryCreationState(canCreate = true, editor = editor))
                loadGroupedStorySelectionPage(1)
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) {
                if (!active(generation) || token !== credential || state.value.library != library || request != groupedStoryRequest) return@launch
                if (failure is ApiFailure && failure.status in setOf(401, 403))
                    readFailure(failure, generation, credential) { beginGroupedStoryCreation() }
                else mutable.value = state.value.copy(groupedStoryCreation = GroupedStoryCreationState(problem = problem(failure)))
            }
        }
        return true
    }

    /** Selection has its own protected pages; browsing never invalidates the editor's ordered choices. */
    fun loadGroupedStorySelectionPage(page: Int): Boolean {
        val current = state.value.groupedStoryCreation ?: return false
        val editor = current.editor ?: return false
        if (!allowed() || current.pageBusy || current.canCreate != true || page !in 1..100000 ||
            editor.state.value.status != StoryWorkspaceStoreStatus.SELECTION) return false
        val credential = token ?: return false; val library = state.value.library ?: return false
        val request = ++groupedStoryPageRequest
        current.previews.values.forEach { it.fill(0) }
        mutable.value = state.value.copy(groupedStoryCreation = current.copy(gallery = null, previews = emptyMap(), pageBusy = true, problem = null))
        launch { generation ->
            fun valid() = active(generation) && token === credential && state.value.library == library &&
                request == groupedStoryPageRequest && state.value.groupedStoryCreation?.editor === editor
            try {
                val gallery = api.gallery(credential, library, page)
                if (!valid()) return@launch
                validResponse(gallery.library_id == library && gallery.page == page && gallery.page_size in 1..100 &&
                    gallery.items.size <= gallery.page_size && gallery.total >= 0 && gallery.items.map { it.id }.distinct().size == gallery.items.size)
                mutable.value = state.value.copy(groupedStoryCreation = state.value.groupedStoryCreation!!.copy(gallery = gallery, pageBusy = false))
                var total = 0
                for (asset in gallery.items.filter { it.kind in setOf("image", "video") }) {
                    if (!valid()) return@launch
                    val bytes = try { api.thumbnail(credential, library, asset) }
                    catch (failure: ApiFailure) {
                        if (failure.status in setOf(401, 403) || failure.kind == FailureKind.TLS) throw failure else null
                    } ?: continue
                    if (!valid()) { bytes.fill(0); return@launch }
                    if (bytes.size > HttpsPhotoHouseApi.IMAGE_LIMIT || total + bytes.size > CACHE_LIMIT) { bytes.fill(0); continue }
                    total += bytes.size
                    val live = state.value.groupedStoryCreation ?: run { bytes.fill(0); return@launch }
                    mutable.value = state.value.copy(groupedStoryCreation = live.copy(previews = live.previews + (asset.id to bytes)))
                }
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) {
                if (!valid()) return@launch
                if (failure is ApiFailure && failure.status in setOf(401, 403))
                    readFailure(failure, generation, credential) { loadGroupedStorySelectionPage(page) }
                else mutable.value = state.value.copy(groupedStoryCreation = state.value.groupedStoryCreation?.copy(pageBusy = false, problem = problem(failure)))
            }
        }
        return true
    }

    fun closeGroupedStoryCreation(discard: Boolean = false): Boolean {
        val current = state.value.groupedStoryCreation ?: return true
        if (current.editor?.close(discard) == false) return false
        groupedStoryRequest++; groupedStoryPageRequest++
        current.previews.values.forEach { it.fill(0) }
        mutable.value = state.value.copy(groupedStoryCreation = null)
        return true
    }

    /** Only the saved receipt held by the current editor can hand off to a fresh protected reader. */
    fun readCreatedGroupedStory(): Boolean {
        if (!allowed() || state.value.busy || coolingDown()) return false
        val creation = state.value.groupedStoryCreation ?: return false
        val editor = creation.editor ?: return false
        val saved = editor.state.value.savedStory ?: return false
        if (editor.state.value.status != StoryWorkspaceStoreStatus.SAVED || saved.libraryId != state.value.library) return false
        val summary = SavedMemoryStorySummary(saved.id, saved.title, saved.theme, saved.language, saved.revision,
            saved.items.first().asset.id, saved.items.size, saved.chapters.size, saved.updatedAt, saved.canEdit)
        closeGroupedStoryCreation(discard = true)
        mutable.value = state.value.copy(savedMemoryStories = SavedMemoryStoriesReading(saved.libraryId))
        readAuthorizedSavedMemoryStory(summary, wholeStoryContribution = true)
        return true
    }

    fun openSavedMemoryStories(page: Int = 1,
        theme: String? = state.value.savedMemoryStories?.takeIf { it.library == state.value.library }?.theme) {
        if (!api.protectedNativeV2Enabled || !allowed() || state.value.busy || coolingDown() || page !in 1..100000) return
        if (theme != null && theme !in SAVED_MEMORY_STORY_THEMES) return
        val library = state.value.library!!
        val current = state.value.savedMemoryStories?.takeIf { it.library == library }
        if (current?.busy == true && current.page == page && current.theme == theme) return
        clearMemoryCommunity(clearState = true)
        val request = ++savedMemoryListRequest
        savedMemoryDetailRequest++; savedMemoryFramesRequest++; savedMemoryHeroRequest++
        savedMemoryReaderEpoch++; savedMemoryContributionReferencesRequest++; savedMemoryContributionDetailRequest++
        savedMemoryContributionChapterEpoch++
        savedMemoryCoversRequest++
        current?.frames?.values?.forEach { it.fill(0) }
        current?.hero?.fill(0)
        current?.covers?.values?.forEach { it.fill(0) }
        mutable.value = state.value.copy(savedMemoryStories = SavedMemoryStoriesReading(library, page, busy = true, theme = theme))
        val credential = token!!
        launch { generation ->
            try {
                val result = api.savedMemoryStories(credential, library, page, theme)
                if (!active(generation) || request != savedMemoryListRequest || state.value.library != library) return@launch
                validResponse(result.libraryId == library && result.page == page && result.pageSize == 8 && result.items.size <= 8 &&
                    result.items.map { it.id }.distinct().size == result.items.size &&
                    (theme == null || result.items.all { it.theme == theme }))
                mutable.value = state.value.copy(savedMemoryStories = SavedMemoryStoriesReading(library, page, result, theme = theme))
                loadSavedMemoryStoryCovers(result.items)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation) || request != savedMemoryListRequest || state.value.library != library) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403))
                    readFailure(e, generation, credential) { closeSavedMemoryStories() }
                else mutable.value = state.value.copy(savedMemoryStories = SavedMemoryStoriesReading(
                    library, page, unavailable = true, problem = problem(e), theme = theme))
            }
        }
    }

    fun openSavedMemoryStory(summary: SavedMemoryStorySummary) {
        val initial = state.value.savedMemoryStories ?: return
        if (!api.protectedNativeV2Enabled || !allowed() || state.value.busy || coolingDown() || initial.library != state.value.library ||
            initial.busy || initial.unavailable || initial.result?.items?.contains(summary) != true || initial.detailBusy) return
        readAuthorizedSavedMemoryStory(summary)
    }

    private fun readAuthorizedSavedMemoryStory(summary: SavedMemoryStorySummary, wholeStoryContribution: Boolean = false) {
        clearMemoryCommunity(clearState = true)
        val reading = state.value.savedMemoryStories ?: return
        val request = ++savedMemoryDetailRequest
        savedMemoryContributionReferenceSaveRequest++
        val readerEpoch = ++savedMemoryReaderEpoch
        savedMemoryContributionReferencesRequest++; savedMemoryContributionDetailRequest++
        savedMemoryContributionChapterEpoch++
        reading.frames.values.forEach { it.fill(0) }
        reading.hero?.fill(0)
        savedMemoryFramesRequest++; savedMemoryHeroRequest++
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(detail = null, detailBusy = true, detailUnavailable = false,
            selectedSummary = summary, selectedChapter = 0, frames = emptyMap(), heroAssetId = null, hero = null, heroBusy = false,
            contributionReferences = null, contributionReferencesBusy = false, contributionReferencesUnavailable = false,
            contributionDetailChapterId = null, contributionDetailId = null, contributionDetail = null,
            contributionDetailBusy = false, contributionDetailUnavailable = false, problem = null))
        val credential = token!!; val library = reading.library
        launch { activeGeneration ->
            try {
                val result = api.savedMemoryStory(credential, library, summary.id, summary.revision)
                if (!active(activeGeneration) || request != savedMemoryDetailRequest || readerEpoch != savedMemoryReaderEpoch ||
                    token !== credential || state.value.library != library) return@launch
                validResponse(result.libraryId == library && result.id == summary.id && result.revision >= summary.revision && result.items.isNotEmpty())
                val latestSummary = summary.copy(
                    title = result.title, theme = result.theme, language = result.language, revision = result.revision,
                    coverAssetId = result.items.first().asset.id,
                    itemCount = result.items.size, chapterCount = result.chapters.size, updatedAt = result.updatedAt, canEdit = result.canEdit,
                )
                val current = state.value.savedMemoryStories!!
                val refreshedPage = current.result?.copy(items = current.result.items.map { if (it.id == result.id) latestSummary else it })
                val covers = if (latestSummary.coverAssetId != summary.coverAssetId) {
                    current.covers[result.id]?.fill(0)
                    current.covers - result.id
                } else current.covers
                mutable.value = state.value.copy(savedMemoryStories = current.copy(result = refreshedPage, covers = covers,
                    detail = result, detailBusy = false, selectedSummary = latestSummary, selectedChapter = 0))
                loadSavedMemoryChapterFrames(0)
                initializeMemoryCommunity(result.id, wholeStoryContribution)
                loadSavedMemoryStoryContributionReferences(result, credential, activeGeneration, request, readerEpoch)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(activeGeneration) || request != savedMemoryDetailRequest || readerEpoch != savedMemoryReaderEpoch ||
                    token !== credential || state.value.library != library) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403))
                    readFailure(e, activeGeneration, credential) { closeSavedMemoryStories() }
                else mutable.value = state.value.copy(savedMemoryStories = state.value.savedMemoryStories!!.copy(detailBusy = false, detailUnavailable = true, problem = problem(e)))
            }
        }
    }

    private fun savedMemorySourceReaderCurrent(
        accountId: String, credential: Bearer, library: String, storyId: String, revision: Long,
        generation: Long, detailRequest: Long, readerEpoch: Long,
    ): Boolean {
        val live = state.value
        val reading = live.savedMemoryStories
        return active(generation) && token === credential && identity?.account_id == accountId &&
            live.session?.account_id == accountId && live.library == library && allowed() &&
            detailRequest == savedMemoryDetailRequest && readerEpoch == savedMemoryReaderEpoch &&
            reading?.let { it.library == library && it.detail?.id == storyId && it.detail?.revision == revision } == true
    }

    private fun savedMemoryContributionLinkCurrent(
        reading: SavedMemoryStoriesReading, storyId: String, library: String, revision: Long,
        chapterId: String, contributionId: String,
    ): Boolean {
        val story = reading.detail ?: return false
        val references = reading.contributionReferences ?: return false
        return reading.library == library && story.id == storyId && story.libraryId == library && story.revision == revision &&
            references.id == storyId && references.libraryId == library && references.revision == revision &&
            reading.contributionDetailChapterId == chapterId && reading.contributionDetailId == contributionId &&
            references.chapters.firstOrNull { it.chapterId == chapterId }?.contributionIds?.contains(contributionId) == true
    }

    private fun loadSavedMemoryStoryContributionReferences(
        story: SavedMemoryStory, credential: Bearer, generation: Long, detailRequest: Long, readerEpoch: Long,
    ) {
        val reading = state.value.savedMemoryStories ?: return
        if (reading.detail?.id != story.id || reading.detail.revision != story.revision || reading.library != story.libraryId) return
        val accountId = identity?.account_id ?: return
        val request = ++savedMemoryContributionReferencesRequest
        savedMemoryContributionDetailRequest++
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(
            contributionReferences = null, contributionReferencesBusy = true, contributionReferencesUnavailable = false,
            contributionDetailChapterId = null, contributionDetailId = null, contributionDetail = null,
            contributionDetailBusy = false, contributionDetailUnavailable = false,
        ))
        val job = scope.launch {
            try {
                val references = api.savedMemoryStoryContributionReferences(
                    credential, story.libraryId, story.id, story.revision, story.chapters.map { it.id },
                )
                if (!savedMemorySourceReaderCurrent(accountId, credential, story.libraryId, story.id, story.revision,
                        generation, detailRequest, readerEpoch) || request != savedMemoryContributionReferencesRequest) return@launch
                val current = state.value.savedMemoryStories ?: return@launch
                mutable.value = state.value.copy(savedMemoryStories = current.copy(
                    contributionReferences = references, contributionReferencesBusy = false, contributionReferencesUnavailable = false,
                    contributionReferenceDraft = references.chapters.associate { it.chapterId to it.contributionIds },
                    pendingContributionReferenceMutation = null, contributionReferenceSaveError = false,
                    contributionReferenceSaveConflict = false,
                ))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!savedMemorySourceReaderCurrent(accountId, credential, story.libraryId, story.id, story.revision,
                        generation, detailRequest, readerEpoch) || request != savedMemoryContributionReferencesRequest) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) {
                    readFailure(e, generation, credential) { closeSavedMemoryStories() }
                } else {
                    val current = state.value.savedMemoryStories ?: return@launch
                    mutable.value = state.value.copy(savedMemoryStories = current.copy(
                        contributionReferencesBusy = false, contributionReferencesUnavailable = true,
                    ))
                }
            }
        }
        requests += job
        job.invokeOnCompletion { requests.remove(job) }
    }

    fun retrySavedMemoryStoryContributionReferences() {
        val reading = state.value.savedMemoryStories ?: return
        val story = reading.detail ?: return
        if (!api.protectedNativeV2Enabled || !allowed() || reading.contributionReferencesBusy) return
        val credential = token ?: return
        loadSavedMemoryStoryContributionReferences(story, credential, state.value.generation,
            savedMemoryDetailRequest, savedMemoryReaderEpoch)
    }

    fun toggleSavedMemoryChapterContribution(chapterId: String, contributionId: String) {
        val live = state.value
        val reading = live.savedMemoryStories ?: return
        val story = reading.detail ?: return
        if (story.chapters.none { it.id == chapterId }) return
        val draft = reading.contributionReferenceDraft ?: return
        if (!story.canEdit || !api.protectedNativeV2Enabled || !allowed() || reading.contributionReferencesBusy ||
            reading.contributionReferenceSaveBusy || reading.contributionReferences?.revision != story.revision) return
        val selected = draft[chapterId].orEmpty()
        val next = if (contributionId in selected) selected - contributionId else {
            val known = reading.community?.contributions?.items?.firstOrNull { it.id == contributionId }
            if (known == null || known.storyId != story.id || known.state != "accepted" || !known.processingConsent ||
                known.baseStoryRevision !in 1..story.revision || known.chapterId != null && known.chapterId != chapterId ||
                nextSize(selected) >= 12) return
            selected + contributionId
        }
        mutable.value = live.copy(savedMemoryStories = reading.copy(contributionReferenceDraft = draft + (chapterId to next)))
    }

    private fun nextSize(ids: List<String>) = ids.size

    fun saveSavedMemoryStoryContributionReferences() = saveSavedMemoryStoryContributionReferences(retry = false)

    fun retrySavedMemoryStoryContributionReferencesSave() = saveSavedMemoryStoryContributionReferences(retry = true)

    private fun saveSavedMemoryStoryContributionReferences(retry: Boolean) {
        val live = state.value
        val reading = live.savedMemoryStories ?: return
        val story = reading.detail ?: return
        val accountId = identity?.account_id ?: return
        if (!api.protectedNativeV2Enabled || !allowed() || !story.canEdit || reading.library != live.library ||
            reading.contributionReferenceSaveBusy || reading.contributionReferencesBusy) return
        val frozen = reading.pendingContributionReferenceMutation
        val mutation = if (retry) frozen ?: return else {
            if (reading.contributionReferences?.let { it.id == story.id && it.libraryId == reading.library && it.revision == story.revision } != true) return
            val draft = reading.contributionReferenceDraft ?: return
            val pages = reading.community?.contributions?.items.orEmpty().associateBy { it.id }
            val currentRefs = reading.contributionReferences.chapters.associate { it.chapterId to it.contributionIds }
            if (draft.any { (chapterId, ids) ->
                ids.size > 12 || ids.distinct().size != ids.size || ids.any { id ->
                    if (id in currentRefs[chapterId].orEmpty()) false else pages[id]?.let { item ->
                        item.storyId != story.id || item.state != "accepted" || !item.processingConsent ||
                            item.baseStoryRevision !in 1..story.revision || item.chapterId != null && item.chapterId != chapterId
                    } != false
                }
            }) return
            val groups = story.chapters.map { chapter -> JsonObject(mapOf(
                "chapter_id" to JsonPrimitive(chapter.id),
                "contribution_ids" to JsonArray(draft[chapter.id].orEmpty().map(::JsonPrimitive)),
            )) }
            val json = JsonArray(groups).toString()
            SavedMemoryStoryContributionReferencesMutation(story.id, story.revision, story.selectionRevision,
                story.title, story.theme, story.language, story.chapters.toList(), json)
        }
        if (mutation.storyId != story.id || mutation.revision != story.revision || mutation.selectionRevision != story.selectionRevision) return
        val credential = token ?: return
        val generation = live.generation; val detailRequest = savedMemoryDetailRequest; val readerEpoch = savedMemoryReaderEpoch
        val request = if (retry) savedMemoryContributionReferenceSaveRequest else ++savedMemoryContributionReferenceSaveRequest
        mutable.value = live.copy(savedMemoryStories = reading.copy(contributionReferenceSaveBusy = true,
            contributionReferenceSaveError = false, contributionReferenceSaveConflict = false,
            pendingContributionReferenceMutation = mutation))
        val job = scope.launch {
            try {
                val saved = api.saveMemoryStoryContributionReferences(credential, reading.library, mutation)
                val current = state.value.savedMemoryStories ?: return@launch
                if (!active(generation) || token !== credential || identity?.account_id != accountId || state.value.session?.account_id != accountId ||
                    state.value.library != reading.library || request != savedMemoryContributionReferenceSaveRequest ||
                    savedMemoryDetailRequest != detailRequest || savedMemoryReaderEpoch != readerEpoch ||
                    current.detail?.id != story.id || current.detail.revision != story.revision || saved.revision != story.revision + 1) return@launch
                val updatedSummary = current.selectedSummary?.copy(revision = saved.revision, title = saved.title, updatedAt = saved.updatedAt,
                    theme = saved.theme, language = saved.language, itemCount = saved.items.size, chapterCount = saved.chapters.size)
                val page = current.result?.copy(items = current.result.items.map { if (it.id == story.id && updatedSummary != null) updatedSummary else it })
                mutable.value = state.value.copy(savedMemoryStories = current.copy(result = page, selectedSummary = updatedSummary,
                    detail = null, contributionReferenceSaveBusy = false, contributionReferenceSaveError = false,
                    pendingContributionReferenceMutation = null, contributionReferences = null, contributionReferenceDraft = null))
                if (updatedSummary != null) openSavedMemoryStory(updatedSummary)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                val currentLive = state.value
                val current = currentLive.savedMemoryStories ?: return@launch
                if (!active(generation) || token !== credential || identity?.account_id != accountId || currentLive.library != reading.library ||
                    request != savedMemoryContributionReferenceSaveRequest || savedMemoryDetailRequest != detailRequest ||
                    savedMemoryReaderEpoch != readerEpoch || current.detail?.let { it.id == story.id && it.revision == story.revision } != true) return@launch
                val conflict = e is ApiFailure && e.status == 409
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, generation, credential) { closeSavedMemoryStories() }
                else mutable.value = currentLive.copy(savedMemoryStories = current.copy(contributionReferenceSaveBusy = false,
                    contributionReferenceSaveError = true, contributionReferenceSaveConflict = conflict,
                    pendingContributionReferenceMutation = mutation))
            }
        }
        requests += job
        job.invokeOnCompletion { requests.remove(job) }
    }

    fun loadSavedMemoryStoryContributionDetail(chapterId: String, contributionId: String) {
        val live = state.value
        val reading = live.savedMemoryStories ?: return
        val story = reading.detail ?: return
        val chapter = story.chapters.getOrNull(reading.selectedChapter) ?: return
        val references = reading.contributionReferences ?: return
        if (!api.protectedNativeV2Enabled || !allowed() || reading.contributionReferencesBusy ||
            references.id != story.id || references.libraryId != reading.library || references.revision != story.revision ||
            chapter.id != chapterId || references.chapters.firstOrNull { it.chapterId == chapterId }
                ?.contributionIds?.contains(contributionId) != true) return
        val credential = token ?: return
        val accountId = identity?.account_id ?: return
        val generation = live.generation
        val detailRequest = savedMemoryDetailRequest
        val readerEpoch = savedMemoryReaderEpoch
        val chapterEpoch = savedMemoryContributionChapterEpoch
        val request = ++savedMemoryContributionDetailRequest
        mutable.value = live.copy(savedMemoryStories = reading.copy(
            contributionDetailChapterId = chapterId, contributionDetailId = contributionId,
            contributionDetail = null, contributionDetailBusy = true, contributionDetailUnavailable = false,
        ))
        val job = scope.launch {
            try {
                val result = api.savedMemoryContributionDetail(credential, reading.library, story.id, contributionId)
                val currentReading = state.value.savedMemoryStories ?: return@launch
                if (!savedMemorySourceReaderCurrent(accountId, credential, reading.library, story.id, story.revision,
                        generation, detailRequest, readerEpoch) || chapterEpoch != savedMemoryContributionChapterEpoch ||
                    request != savedMemoryContributionDetailRequest ||
                    currentReading.detail?.chapters?.getOrNull(currentReading.selectedChapter)?.id != chapterId ||
                    !savedMemoryContributionLinkCurrent(currentReading, story.id, reading.library, story.revision,
                        chapterId, contributionId)) return@launch
                val contribution = result.receipt.contribution
                val eligible = contribution.id == contributionId && contribution.storyId == story.id &&
                    contribution.state == "accepted" && contribution.processingConsent &&
                    contribution.baseStoryRevision in 1..story.revision &&
                    (contribution.chapterId == null || contribution.chapterId == chapterId)
                val current = state.value.savedMemoryStories ?: return@launch
                mutable.value = state.value.copy(savedMemoryStories = current.copy(
                    contributionDetail = result.takeIf { eligible }, contributionDetailBusy = false,
                    contributionDetailUnavailable = !eligible,
                ))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!savedMemorySourceReaderCurrent(accountId, credential, reading.library, story.id, story.revision,
                        generation, detailRequest, readerEpoch) || chapterEpoch != savedMemoryContributionChapterEpoch ||
                    request != savedMemoryContributionDetailRequest ||
                    state.value.savedMemoryStories?.let { currentReading ->
                        savedMemoryContributionLinkCurrent(currentReading, story.id, reading.library, story.revision,
                            chapterId, contributionId)
                    } != true) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) {
                    readFailure(e, generation, credential) { closeSavedMemoryStories() }
                } else {
                    val current = state.value.savedMemoryStories ?: return@launch
                    mutable.value = state.value.copy(savedMemoryStories = current.copy(
                        contributionDetailBusy = false, contributionDetailUnavailable = true,
                    ))
                }
            }
        }
        requests += job
        job.invokeOnCompletion { requests.remove(job) }
    }

    fun closeSavedMemoryStoryContributionDetail() {
        savedMemoryContributionDetailRequest++
        val reading = state.value.savedMemoryStories ?: return
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(
            contributionDetailChapterId = null, contributionDetailId = null, contributionDetail = null,
            contributionDetailBusy = false, contributionDetailUnavailable = false,
        ))
    }

    fun retrySavedMemoryStoryContributionDetail() {
        val reading = state.value.savedMemoryStories ?: return
        val chapterId = reading.contributionDetailChapterId ?: return
        val contributionId = reading.contributionDetailId ?: return
        loadSavedMemoryStoryContributionDetail(chapterId, contributionId)
    }

    fun retrySavedMemoryStory() {
        val reading = state.value.savedMemoryStories ?: return
        val summary = reading.selectedSummary ?: return
        if (!api.protectedNativeV2Enabled || !allowed() || state.value.busy || coolingDown() ||
            reading.library != state.value.library || reading.detailBusy || !reading.detailUnavailable) return
        if (reading.result == null) readAuthorizedSavedMemoryStory(summary, wholeStoryContribution = true)
        else openSavedMemoryStory(summary)
    }

    fun loadSavedMemoryChapter(index: Int) {
        val reading = state.value.savedMemoryStories ?: return
        if (reading.detail == null || index !in reading.detail.chapters.indices || reading.framesBusy) return
        if (reading.selectedChapter == index && reading.frames.isNotEmpty()) return
        savedMemoryContributionChapterEpoch++; savedMemoryContributionDetailRequest++
        savedMemoryContributionReferencesRequest++
        reading.frames.values.forEach { it.fill(0) }
        reading.hero?.fill(0); savedMemoryHeroRequest++
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(selectedChapter = index, frames = emptyMap(),
            heroAssetId = null, hero = null, heroBusy = false, framesBusy = true,
            contributionReferences = null, contributionReferencesBusy = true, contributionReferencesUnavailable = false,
            contributionDetailChapterId = null, contributionDetailId = null, contributionDetail = null,
            contributionDetailBusy = false, contributionDetailUnavailable = false))
        loadSavedMemoryChapterFrames(index)
        val current = state.value.savedMemoryStories ?: return
        val currentStory = current.detail ?: return
        val credential = token ?: return
        loadSavedMemoryStoryContributionReferences(currentStory, credential, state.value.generation,
            savedMemoryDetailRequest, savedMemoryReaderEpoch)
    }

    fun loadSavedMemoryHero(assetId: String) {
        val reading = state.value.savedMemoryStories ?: return
        val detail = reading.detail ?: return
        if (reading.framesBusy || reading.selectedChapter !in detail.chapters.indices ||
            assetId !in detail.chapters[reading.selectedChapter].assetIds || reading.library != state.value.library || !allowed()) return
        if (reading.heroAssetId == assetId && (reading.hero != null || reading.heroBusy)) return
        val asset = detail.items.firstOrNull { it.asset.id == assetId }?.asset ?: return
        val request = ++savedMemoryHeroRequest; val generation = state.value.generation
        val library = reading.library; val storyId = detail.id; val chapterIndex = reading.selectedChapter; val credential = token!!
        reading.hero?.fill(0)
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(heroAssetId = assetId, hero = null, heroBusy = true))
        launch { activeGeneration ->
            var bytes: ByteArray? = null
            try {
                bytes = api.detailPreview(credential, library, asset)
                if (bytes != null) validResponse(bytes.size <= HttpsPhotoHouseApi.IMAGE_LIMIT)
                if (!active(activeGeneration) || activeGeneration != generation || request != savedMemoryHeroRequest || state.value.library != library ||
                    state.value.savedMemoryStories?.detail?.id != storyId || state.value.savedMemoryStories?.selectedChapter != chapterIndex ||
                    state.value.savedMemoryStories?.heroAssetId != assetId) {
                    bytes?.fill(0); return@launch
                }
                mutable.value = state.value.copy(savedMemoryStories = state.value.savedMemoryStories!!.copy(hero = bytes, heroBusy = false))
            } catch (e: CancellationException) { bytes?.fill(0); throw e }
            catch (e: Exception) {
                bytes?.fill(0)
                if (!active(activeGeneration) || request != savedMemoryHeroRequest || state.value.library != library) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, activeGeneration, credential) { closeSavedMemoryStories() }
                else mutable.value = state.value.copy(savedMemoryStories = state.value.savedMemoryStories?.copy(heroBusy = false))
            }
        }
    }

    private fun loadSavedMemoryChapterFrames(index: Int) {
        val reading = state.value.savedMemoryStories ?: return
        val detail = reading.detail ?: return
        if (index !in detail.chapters.indices || !allowed() || reading.library != state.value.library) return
        val request = ++savedMemoryFramesRequest
        val heroRequest = ++savedMemoryHeroRequest
        val library = reading.library; val storyId = detail.id
        val assets = detail.chapters[index].assetIds.mapNotNull { id -> detail.items.firstOrNull { it.asset.id == id }?.asset }
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(selectedChapter = index, framesBusy = true))
        val credential = token!!
        launch { activeGeneration ->
            val frames = linkedMapOf<String, ByteArray>()
            var hero: ByteArray? = null
            try {
                for (asset in assets) {
                    if (!active(activeGeneration) || request != savedMemoryFramesRequest) {
                        frames.values.forEach { it.fill(0) }; return@launch
                    }
                    val bytes = api.thumbnail(credential, library, asset)
                    if (bytes != null) {
                        validResponse(bytes.size <= HttpsPhotoHouseApi.IMAGE_LIMIT)
                        frames[asset.id] = bytes
                    }
                }
                val heroAsset = assets.firstOrNull()
                if (heroAsset != null) {
                    try {
                        hero = api.detailPreview(credential, library, heroAsset)
                        if (hero != null) validResponse(hero.size <= HttpsPhotoHouseApi.IMAGE_LIMIT)
                    } catch (e: CancellationException) { throw e }
                    catch (e: Exception) {
                        hero?.fill(0); hero = null
                        if (e is ApiFailure && e.status in listOf(401, 403)) throw e
                    }
                }
                if (!active(activeGeneration) || request != savedMemoryFramesRequest || state.value.library != library ||
                    state.value.savedMemoryStories?.detail?.id != storyId || state.value.savedMemoryStories?.selectedChapter != index) {
                    frames.values.forEach { it.fill(0) }; hero?.fill(0); return@launch
                }
                if (heroRequest != savedMemoryHeroRequest) { hero?.fill(0); hero = null }
                mutable.value = state.value.copy(savedMemoryStories = state.value.savedMemoryStories!!.copy(frames = frames,
                    heroAssetId = heroAsset?.id, hero = hero, heroBusy = false, framesBusy = false))
            } catch (e: CancellationException) { frames.values.forEach { it.fill(0) }; hero?.fill(0); throw e }
            catch (e: Exception) {
                frames.values.forEach { it.fill(0) }; hero?.fill(0)
                if (!active(activeGeneration) || request != savedMemoryFramesRequest || state.value.library != library) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, activeGeneration, credential) { closeSavedMemoryStories() }
                else mutable.value = state.value.copy(savedMemoryStories = state.value.savedMemoryStories?.copy(framesBusy = false))
            }
        }
    }

    fun closeSavedMemoryStories() {
        clearMemoryCommunity(clearState = true)
        savedMemoryListRequest++; savedMemoryDetailRequest++; savedMemoryFramesRequest++; savedMemoryCoversRequest++; savedMemoryHeroRequest++
        savedMemoryReaderEpoch++; savedMemoryContributionReferencesRequest++; savedMemoryContributionDetailRequest++
        savedMemoryContributionReferenceSaveRequest++
        savedMemoryContributionChapterEpoch++
        state.value.savedMemoryStories?.frames?.values?.forEach { it.fill(0) }
        state.value.savedMemoryStories?.hero?.fill(0)
        state.value.savedMemoryStories?.covers?.values?.forEach { it.fill(0) }
        mutable.value = state.value.copy(savedMemoryStories = null)
    }

    /** Protected read-only book shelf. Capability negotiation precedes every list request. */
    fun openMemoryBooks(page: Int = 1) {
        if (!memoryCommunityAvailable || !allowed() || state.value.busy || coolingDown() || page !in 1..100000) return
        clearMemoryBookEditorial()
        val library = state.value.library ?: return
        val previous = state.value.memoryBooks
        invalidateBookChatRequests()
        previous?.companion?.dictation?.close()
        wipeMemoryBookMedia(state.value.memoryBooks)
        val request = ++memoryBooksRequest
        memoryBooksReaderRequest++
        mutable.value = state.value.copy(memoryBooks = MemoryBooksReading(library, page, busy = true))
        launch { generation ->
            val credential = token ?: return@launch
            try {
                val repository = memoryCommunity ?: return@launch
                val capabilities = repository.loadCapabilities()
                if (!active(generation) || request != memoryBooksRequest || state.value.library != library) return@launch
                validResponse(capabilities.enabled)
                val result = repository.books(page)
                if (!active(generation) || request != memoryBooksRequest || state.value.library != library) return@launch
                validResponse(result.libraryId == library && result.page == page && result.items.size <= 8)
                mutable.value = state.value.copy(memoryBooks = MemoryBooksReading(library, page, capabilities = capabilities, result = result))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation) || request != memoryBooksRequest || state.value.library != library) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, generation, credential) { closeMemoryBooks() }
                else mutable.value = state.value.copy(memoryBooks = MemoryBooksReading(library, page, problem = problem(e)))
            }
        }
    }

    fun openMemoryBook(bookId: String) {
        val reading = state.value.memoryBooks ?: return
        val summary = reading.result?.items?.firstOrNull { it.id == bookId } ?: return
        if (reading.busy || reading.readerBusy || reading.library != state.value.library || !allowed()) return
        clearMemoryBookEditorial()
        val request = ++memoryBooksReaderRequest
        invalidateBookChatRequests()
        val epoch = bookChatEpoch
        reading.companion?.dictation?.close()
        memoryBooksMediaRequest++
        wipeMemoryBookMedia(reading)
        mutable.value = state.value.copy(memoryBooks = reading.copy(selectedBook = null, storyIndex = null,
            story = null, readerBusy = true, readerUnavailable = false, problem = null,
            selectedChapter = 0, selectedAssetId = null, framePage = 0, frames = emptyMap(), framesBusy = false,
            unavailableFrameIds = emptySet(), framesUnavailable = false, heroAssetId = null, hero = null,
            heroBusy = false, heroUnavailable = false, resumePosition = null, readerScopeId = request, companion = null,
            sourceInspection = MemoryBookEditorialSourceInspectionState()))
        launch { generation ->
            val credential = token ?: return@launch
            val library = reading.library
            fun current() = active(generation) && request == memoryBooksReaderRequest && state.value.library == library &&
                token === credential && state.value.memoryBooks?.library == library && bookChatEpoch == epoch
            try {
                val repository = memoryCommunity ?: return@launch
                val book = repository.book(summary.id, summary.revision)
                if (!current()) return@launch
                validResponse(book.id == summary.id && book.revision == summary.revision && book.stories == summary.stories)
                val conversations = if (reading.capabilities?.generationEnabled == true) try {
                    repository.conversations("book", book.id, withPreview = true, currentRequest = ::current)
                } catch (e: CancellationException) { throw e }
                catch (e: ApiFailure) {
                    if (e.status in listOf(401, 403)) throw e
                    null
                } catch (_: Exception) { null } else null
                if (!current()) return@launch
                val selected = conversations?.items?.firstOrNull()
                val turns = selected?.let { selectedConversation ->
                    try { repository.turns(selectedConversation.id, replyContext = true) }
                    catch (e: CancellationException) { throw e }
                    catch (_: Exception) { null }
                }
                if (!current()) return@launch
                val activeJob = turns?.let { recoverPendingChatJob(repository, it, book.revision, ::current) }
                if (!current()) return@launch
                mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(selectedBook = book,
                    readerBusy = false, readerUnavailable = false, resumePosition = findMemoryBookResume(reading.library, book),
                    companion = if (reading.capabilities?.generationEnabled == true)
                        MemoryBookChatState(book.id, book.revision, conversations, selected?.id, turns, activeJob) else null))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!current()) return@launch
                if (e is ApiFailure && e.status == 403) memoryCommunityDenied()
                else if (e is ApiFailure && e.status == 401) readFailure(e, generation, credential) { closeMemoryBooks() }
                else mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(readerBusy = false,
                    readerUnavailable = true, problem = problem(e)))
            }
        }
    }

    /** Refetch the parent on every child transition and fail closed if the ordered entry changed. */
    fun loadMemoryBookStory(index: Int) = loadMemoryBookStoryAt(index, null)

    fun resumeMemoryBookReading() {
        val reading = state.value.memoryBooks ?: return
        val book = reading.selectedBook ?: return
        val position = reading.resumePosition ?: return
        val index = book.stories.indexOfFirst { it.id == position.storyId && it.revision == position.storyRevision }
        if (index < 0) {
            removeMemoryBookResume(reading.library, book)
            mutable.value = state.value.copy(memoryBooks = reading.copy(resumePosition = null))
            return
        }
        loadMemoryBookStoryAt(index, position.chapterId)
    }

    private fun loadMemoryBookStoryAt(index: Int, resumeChapterId: String?) {
        val reading = state.value.memoryBooks ?: return
        val selected = reading.selectedBook ?: return
        val entry = selected.stories.getOrNull(index) ?: return
        if (reading.readerBusy || reading.library != state.value.library || !allowed()) return
        clearMemoryBookEditorialSourceInspection()
        val request = ++memoryBooksReaderRequest
        memoryBooksMediaRequest++
        wipeMemoryBookMedia(reading)
        mutable.value = state.value.copy(memoryBooks = reading.copy(storyIndex = index, story = null,
            selectedChapter = 0, selectedAssetId = null, framePage = 0, frames = emptyMap(), framesBusy = false,
            unavailableFrameIds = emptySet(), framesUnavailable = false, heroAssetId = null, hero = null,
            heroBusy = false, heroUnavailable = false, readerBusy = true, readerUnavailable = false, problem = null,
            readerScopeId = request, sourceInspection = MemoryBookEditorialSourceInspectionState()))
        launch { generation ->
            val credential = token ?: return@launch
            try {
                val repo = memoryCommunity ?: return@launch
                val fresh = repo.book(selected.id, selected.revision)
                if (!active(generation) || request != memoryBooksReaderRequest || state.value.library != reading.library) return@launch
                validResponse(fresh.id == selected.id && fresh.revision == selected.revision && fresh.stories == selected.stories &&
                    fresh.stories.getOrNull(index) == entry)
                val child = api.savedMemoryStory(credential, reading.library, entry.id, entry.revision)
                if (!active(generation) || request != memoryBooksReaderRequest || state.value.library != reading.library) return@launch
                validResponse(child.id == entry.id && child.libraryId == reading.library && child.revision == entry.revision &&
                    child.items.size == entry.itemCount && child.items.isNotEmpty())
                val chapterIndex = resumeChapterId?.let { id -> child.chapters.indexOfFirst { it.id == id }.takeIf { it >= 0 } } ?: 0
                mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(storyIndex = index,
                    story = child, selectedChapter = chapterIndex, selectedAssetId = null, readerBusy = false, readerUnavailable = false))
                loadMemoryBookChapter(chapterIndex)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation) || request != memoryBooksReaderRequest || state.value.library != reading.library) return@launch
                if (resumeChapterId != null) {
                    selected.let { removeMemoryBookResume(reading.library, it) }
                    mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(resumePosition = null))
                }
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, generation, credential) { closeMemoryBooks() }
                else mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(readerBusy = false,
                    readerUnavailable = true, problem = problem(e)))
            }
        }
    }

    fun closeMemoryBook() {
        clearMemoryBookEditorial()
        invalidateBookChatRequests()
        memoryBooksReaderRequest++
        memoryBooksMediaRequest++
        val reading = state.value.memoryBooks ?: return
        reading.companion?.dictation?.close()
        wipeMemoryBookMedia(reading)
        mutable.value = state.value.copy(memoryBooks = reading.copy(selectedBook = null, storyIndex = null,
            story = null, readerBusy = false, readerUnavailable = false, problem = null,
            selectedChapter = 0, selectedAssetId = null, framePage = 0, frames = emptyMap(), framesBusy = false,
            unavailableFrameIds = emptySet(), framesUnavailable = false,
            heroAssetId = null, hero = null, heroBusy = false, heroUnavailable = false,
            resumePosition = reading.selectedBook?.let { findMemoryBookResume(reading.library, it) },
            readerScopeId = memoryBooksReaderRequest, companion = null))
    }

    fun closeMemoryBooks() {
        clearMemoryBookEditorial()
        invalidateBookChatRequests()
        memoryBooksRequest++; memoryBooksReaderRequest++
        memoryBooksMediaRequest++
        state.value.memoryBooks?.companion?.dictation?.close()
        wipeMemoryBookMedia(state.value.memoryBooks)
        mutable.value = state.value.copy(memoryBooks = null)
    }

    /** Opens the optional editor only on an explicit owner action. Source calls return references only. */
    fun openMemoryBookEditorial(forceReload: Boolean = false) {
        val reading = state.value.memoryBooks ?: return
        val book = reading.selectedBook ?: return
        if (!book.canEdit || reading.library != state.value.library || !allowed() || reading.readerBusy) return
        val credential = token ?: return
        val account = identity?.account_id ?: return
        val loadedKey = editorialKey(account, reading.library, book)
        if (!forceReload && memoryBookEditorialLoadedKey == loadedKey && !memoryBookEditorialCatalog.value.unavailable) return
        clearMemoryBookEditorialSourceInspection()
        val request = ++memoryBookEditorialRequest
        memoryBookEditorialCatalog.value = MemoryBookEditorialCatalogState(busy = true)
        launch { generation ->
            try {
                val sources = linkedSetOf<EditorialSourceIdentity>()
                book.stories.forEach { child ->
                    val refs = memoryBookEditorialApi.getBookEditorialSourceReferences(credential, reading.library, child.id,
                        child.revision)
                    if (!active(generation) || request != memoryBookEditorialRequest || token !== credential ||
                        identity?.account_id != account || state.value.library != reading.library ||
                        state.value.memoryBooks?.selectedBook?.let { it.id == book.id && it.revision == book.revision } != true) return@launch
                    if (refs.id != child.id || refs.libraryId != reading.library || refs.revision != child.revision ||
                        refs.chapters.size !in 1..6 || refs.chapters.map { it.chapterId } != (1..refs.chapters.size).map { "chapter-$it" })
                        throw ApiFailure(FailureKind.INVALID_RESPONSE)
                    refs.chapters.forEach { group ->
                        if (group.contributionIds.size > 12 || group.contributionIds.distinct().size != group.contributionIds.size) throw ApiFailure(FailureKind.INVALID_RESPONSE)
                        group.contributionIds.forEach { id ->
                            if (runCatching { java.util.UUID.fromString(id).toString() == id }.getOrDefault(false))
                                sources += EditorialSourceIdentity(child.id, child.revision.toString(), group.chapterId, id)
                            else throw ApiFailure(FailureKind.INVALID_RESPONSE)
                        }
                    }
                }
                if (!active(generation) || request != memoryBookEditorialRequest || token !== credential ||
                    identity?.account_id != account || state.value.library != reading.library) return@launch
                memoryBookEditorialLoadedKey = loadedKey
                memoryBookEditorialCatalog.value = MemoryBookEditorialCatalogState(sources = sources.toList())
                editorialStore.setContext(MemoryBookEditorialContext(account, credential, reading.library, book.id,
                    book.revision.toString(), book.stories.map { EditorialChild(it.id, it.revision.toString()) }, sources))
                editorialStore.load()
                if (editorialStore.state.value.status == MemoryBookEditorialStoreStatus.ACCESS_REVOKED) {
                    val failure = ApiFailure(FailureKind.HTTP, editorialStore.state.value.errorStatus)
                    denyMemoryBookEditorial(failure, generation, credential)
                }
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation) || request != memoryBookEditorialRequest || token !== credential || state.value.library != reading.library) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) denyMemoryBookEditorial(e, generation, credential)
                else memoryBookEditorialCatalog.value = memoryBookEditorialCatalog.value.copy(busy = false, unavailable = true)
            }
        }
    }

    /** Opens one currently eligible citation. This reads protected detail only; audio requires a second explicit action. */
    fun inspectMemoryBookEditorialSource(source: EditorialSourceIdentity) {
        val live = state.value
        val reading = live.memoryBooks ?: return
        val book = reading.selectedBook ?: return
        val child = book.stories.firstOrNull { it.id == source.storyId } ?: return
        val childRevision = child.revision
        if (!api.protectedNativeV2Enabled || !allowed() || reading.library != live.library || reading.readerBusy ||
            !book.canEdit || source.storyRevision != child.revision.toString() || source !in memoryBookEditorialCatalog.value.sources) return
        val credential = token ?: return
        val account = identity?.account_id ?: return
        clearMemoryBookEditorialSourceInspection()
        val request = ++memoryBookSourceInspectionRequest
        val library = reading.library
        val generation = live.generation
        val readerScope = reading.readerScopeId
        val children = book.stories.map { EditorialChild(it.id, it.revision.toString()) }
        val sourceScope = EditorialSourceInspectionScope(account, credential, library, book.id, book.revision,
            children, source, generation, readerScope)
        fun current(): Boolean = memoryBookSourceInspectionCurrent(sourceScope)
        mutable.value = state.value.copy(memoryBooks = reading.copy(sourceInspection =
            MemoryBookEditorialSourceInspectionState(source = source, busy = true)))
        val job = scope.launch {
            try {
                val result = api.savedMemoryContributionDetail(credential, library, source.storyId, source.contributionId)
                if (!current() || request != memoryBookSourceInspectionRequest) return@launch
                val contribution = result.receipt.contribution
                val eligible = contribution.id == source.contributionId && contribution.storyId == source.storyId &&
                    contribution.state == "accepted" && contribution.processingConsent &&
                    contribution.baseStoryRevision in 1..childRevision &&
                    (contribution.chapterId == null || contribution.chapterId == source.chapterId) &&
                    contribution.kind in setOf("text", "audio")
                val currentReading = state.value.memoryBooks ?: return@launch
                mutable.value = state.value.copy(memoryBooks = currentReading.copy(sourceInspection =
                    MemoryBookEditorialSourceInspectionState(source, result.takeIf { eligible }, unavailable = !eligible)))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!current() || request != memoryBookSourceInspectionRequest) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) {
                    denyMemoryBookEditorial(e, generation, credential)
                } else {
                    val currentReading = state.value.memoryBooks ?: return@launch
                    mutable.value = state.value.copy(memoryBooks = currentReading.copy(sourceInspection =
                        MemoryBookEditorialSourceInspectionState(source, unavailable = true)))
                }
            }
        }
        memoryBookSourceInspectionJob = job
        requests += job
        job.invokeOnCompletion { requests.remove(job) }
    }

    /** Fetches raw audio only after the accepted audio contribution detail has been inspected. */
    fun loadMemoryBookEditorialSourceAudio() {
        val live = state.value
        val reading = live.memoryBooks ?: return
        val book = reading.selectedBook ?: return
        val inspection = reading.sourceInspection
        val source = inspection.source ?: return
        val contribution = inspection.detail?.receipt?.contribution ?: return
        val repository = memoryCommunity ?: return
        if (contribution.kind != "audio" || reading.capabilities?.contributionsEnabled != true ||
            !allowed() || reading.readerBusy || reading.library != live.library || source !in memoryBookEditorialCatalog.value.sources) return
        val credential = token ?: return
        val account = identity?.account_id ?: return
        val child = book.stories.firstOrNull { it.id == source.storyId } ?: return
        if (source.storyRevision != child.revision.toString()) return
        val request = ++memoryBookSourceInspectionRequest
        memoryBookSourceInspectionJob?.cancel()
        memoryBookSourceInspectionJob = null
        inspection.audio?.close()
        val library = reading.library
        val generation = live.generation
        val readerScope = reading.readerScopeId
        val children = book.stories.map { EditorialChild(it.id, it.revision.toString()) }
        val sourceScope = EditorialSourceInspectionScope(account, credential, library, book.id, book.revision,
            children, source, generation, readerScope)
        fun current(): Boolean = memoryBookSourceInspectionCurrent(sourceScope) &&
            state.value.memoryBooks?.sourceInspection?.detail?.receipt?.contribution?.let {
                it.id == contribution.id && it.kind == "audio" && it.state == "accepted" && it.processingConsent
            } == true
        mutable.value = state.value.copy(memoryBooks = reading.copy(sourceInspection = inspection.copy(
            audio = null, audioBusy = true, audioUnavailable = false)))
        val job = scope.launch {
            try {
                val audio = repository.contributionAudio(source.storyId, source.contributionId)
                if (!current() || request != memoryBookSourceInspectionRequest) {
                    audio.close()
                    return@launch
                }
                val currentReading = state.value.memoryBooks ?: run { audio.close(); return@launch }
                currentReading.sourceInspection.audio?.close()
                mutable.value = state.value.copy(memoryBooks = currentReading.copy(sourceInspection =
                    currentReading.sourceInspection.copy(audio = audio, audioBusy = false, audioUnavailable = false)))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!current() || request != memoryBookSourceInspectionRequest) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) {
                    // MemoryCommunityRepository invokes memoryCommunityDenied for protected access failures.
                    if (state.value.memoryBooks != null) denyMemoryBookEditorial(e, generation, credential)
                } else {
                    val currentReading = state.value.memoryBooks ?: return@launch
                    val currentInspection = currentReading.sourceInspection
                    val sourceDeleted = e is ApiFailure && e.status == 404
                    mutable.value = state.value.copy(memoryBooks = currentReading.copy(sourceInspection =
                        currentInspection.copy(detail = currentInspection.detail.takeUnless { sourceDeleted },
                            audio = null, audioBusy = false, unavailable = sourceDeleted,
                            audioUnavailable = true)))
                }
            }
        }
        memoryBookSourceInspectionJob = job
        requests += job
        job.invokeOnCompletion { requests.remove(job) }
    }

    fun closeMemoryBookEditorialSourceInspection() = clearMemoryBookEditorialSourceInspection()

    private data class EditorialSourceInspectionScope(
        val accountId: String, val credential: Bearer, val library: String, val bookId: String, val bookRevision: Long,
        val children: List<EditorialChild>, val source: EditorialSourceIdentity, val generation: Long, val readerScope: Long,
    )

    private fun memoryBookSourceInspectionCurrent(scope: EditorialSourceInspectionScope): Boolean {
        val live = state.value
        val reading = live.memoryBooks ?: return false
        val book = reading.selectedBook ?: return false
        return active(scope.generation) && allowed() && token === scope.credential && identity?.account_id == scope.accountId &&
            live.library == scope.library && reading.library == scope.library && !reading.readerBusy &&
            book.id == scope.bookId && book.revision == scope.bookRevision && book.canEdit &&
            book.stories.map { EditorialChild(it.id, it.revision.toString()) } == scope.children &&
            reading.readerScopeId == scope.readerScope &&
            scope.source.storyRevision == book.stories.firstOrNull { it.id == scope.source.storyId }?.revision?.toString() &&
            scope.source in memoryBookEditorialCatalog.value.sources
    }

    private fun clearMemoryBookEditorialSourceInspection() {
        memoryBookSourceInspectionRequest++
        memoryBookSourceInspectionJob?.cancel()
        memoryBookSourceInspectionJob = null
        val reading = state.value.memoryBooks ?: return
        reading.sourceInspection.audio?.close()
        mutable.value = state.value.copy(memoryBooks = reading.copy(sourceInspection = MemoryBookEditorialSourceInspectionState()))
    }


    fun editMemoryBookEditorial(introduction: List<EditorialSourceIdentity>, transitions: List<EditorialTransition>) =
        editorialStore.edit(introduction, transitions)
    fun saveMemoryBookEditorial() { launch { _ ->
        if (bookChatOperationActive()) return@launch
        val before = editorialStore.state.value.revision
        editorialStore.save()
        syncMemoryBookRevisionAfterEditorialAck(before)
        handleEditorialAuthFailure()
    } }
    fun retryMemoryBookEditorialSave() { launch { _ ->
        if (bookChatOperationActive()) return@launch
        val before = editorialStore.state.value.revision
        editorialStore.retryUncertainSave()
        syncMemoryBookRevisionAfterEditorialAck(before)
        handleEditorialAuthFailure()
    } }
    fun reloadMemoryBookEditorial() { openMemoryBookEditorial(forceReload = true) }
    /** Explicitly fetches the current shelf revision before loading a conflict basis. */
    fun refreshMemoryBookEditorialForReview() {
        val reading = state.value.memoryBooks ?: return
        val oldBook = reading.selectedBook ?: return
        val credential = token ?: return
        if (!allowed() || reading.library != state.value.library || reading.busy || reading.readerBusy || bookChatOperationActive() ||
            editorialStore.state.value.status in setOf(MemoryBookEditorialStoreStatus.SAVING, MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN)) return
        val request = ++memoryBookEditorialRequest
        memoryBookEditorialCatalog.value = MemoryBookEditorialCatalogState(busy = true)
        launch { generation ->
            try {
                val repo = memoryCommunity ?: return@launch
                val page = repo.books(reading.page)
                if (!active(generation) || request != memoryBookEditorialRequest || token !== credential || state.value.library != reading.library) return@launch
                val summary = page.items.firstOrNull { it.id == oldBook.id } ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                val fresh = repo.book(summary.id, summary.revision)
                if (!active(generation) || request != memoryBookEditorialRequest || token !== credential || state.value.library != reading.library) return@launch
                if (fresh.id != oldBook.id || fresh.revision != summary.revision || fresh.stories != summary.stories || !fresh.canEdit)
                    throw ApiFailure(FailureKind.INVALID_RESPONSE)
                val latest = state.value.memoryBooks ?: return@launch
                val unsentNarrative = memoryBookNarrativeState.value.takeIf { it.hasUnfinishedInput }
                invalidateBookChatRequests()
                val storyIndex = latest.story?.let { child -> fresh.stories.indexOfFirst { it.id == child.id && it.revision == child.revision } }
                val keepStory = latest.story != null && storyIndex != null && storyIndex >= 0
                if (!keepStory) {
                    memoryBooksReaderRequest++; memoryBooksMediaRequest++
                    wipeMemoryBookMedia(latest)
                }
                val companion = latest.companion?.copy(bookRevision = fresh.revision, conversations = null, conversationId = null,
                    turns = null, job = null, pendingConversation = null, pendingTurn = null,
                    pendingTurnConversationId = null, busy = false, failure = null,
                    editorialContext = MemoryBookChatEditorialContext.BASIC)
                mutable.value = state.value.copy(memoryBooks = latest.copy(result = page, selectedBook = fresh, companion = companion,
                    storyIndex = if (keepStory) storyIndex else null, story = latest.story.takeIf { keepStory },
                    readerBusy = false, readerUnavailable = false, selectedChapter = if (keepStory) latest.selectedChapter else 0,
                    selectedAssetId = if (keepStory) latest.selectedAssetId else null, frames = if (keepStory) latest.frames else emptyMap(),
                    framesBusy = if (keepStory) latest.framesBusy else false, framesUnavailable = if (keepStory) latest.framesUnavailable else false,
                    unavailableFrameIds = if (keepStory) latest.unavailableFrameIds else emptySet(),
                    heroAssetId = if (keepStory) latest.heroAssetId else null, hero = if (keepStory) latest.hero else null,
                    heroBusy = if (keepStory) latest.heroBusy else false, heroUnavailable = if (keepStory) latest.heroUnavailable else false,
                    readerScopeId = if (keepStory) latest.readerScopeId else memoryBooksReaderRequest))
                unsentNarrative?.let {
                    bookNarrativeStore?.chooseForm(it.form)
                    bookNarrativeStore?.updateInstructions(it.instructions)
                }
                openMemoryBookEditorial(forceReload = true)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation) || request != memoryBookEditorialRequest || token !== credential || state.value.library != reading.library) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) denyMemoryBookEditorial(e, generation, credential)
                else memoryBookEditorialCatalog.value = memoryBookEditorialCatalog.value.copy(busy = false, unavailable = true)
            }
        }
    }
    fun discardMemoryBookEditorialDraft() = editorialStore.discardDraft()
    fun acceptMemoryBookEditorialServerBasis() = editorialStore.acceptCurrentServerBasis()
    fun applyReviewedMemoryBookEditorial(introduction: List<EditorialSourceIdentity>, transitions: List<EditorialTransition>) =
        editorialStore.applyReviewedDraft(introduction, transitions)

    private suspend fun handleEditorialAuthFailure() {
        val status = editorialStore.state.value.takeIf { it.status == MemoryBookEditorialStoreStatus.ACCESS_REVOKED }?.errorStatus ?: return
        val generation = state.value.generation
        val credential = token ?: return
        denyMemoryBookEditorial(ApiFailure(FailureKind.HTTP, status), generation, credential)
    }

    private suspend fun denyMemoryBookEditorial(failure: ApiFailure, generation: Long, credential: Bearer) {
        // A denied metadata/read/save response must cover the reader and clear its sources immediately.
        closeMemoryBooks()
        readFailure(failure, generation, credential) { closeMemoryBooks() }
    }

    private fun syncMemoryBookRevisionAfterEditorialAck(before: String?) {
        val current = editorialStore.state.value
        val next = current.revision?.toLongOrNull() ?: return
        if (before == current.revision || current.status != MemoryBookEditorialStoreStatus.READY) return
        val reading = state.value.memoryBooks ?: return
        val book = reading.selectedBook ?: return
        if (book.revision.toString() != before) return
        // Book chat is revision-bound; retain every local draft while clearing its old remote context.
        val unsentNarrative = memoryBookNarrativeState.value.takeIf { it.hasUnfinishedInput }
        invalidateBookChatRequests()
        val companion = reading.companion?.copy(bookRevision = next, conversations = null, conversationId = null,
            turns = null, job = null, pendingConversation = null, pendingTurn = null,
            pendingTurnConversationId = null, busy = false, failure = null,
            editorialContext = MemoryBookChatEditorialContext.BASIC)
        val updated = book.copy(revision = next)
        clearMemoryBookEditorialSourceInspection()
        val result = reading.result?.let { page -> page.copy(items = page.items.map { if (it.id == book.id) updated else it }) }
        mutable.value = state.value.copy(memoryBooks = reading.copy(selectedBook = updated, result = result, companion = companion,
            sourceInspection = MemoryBookEditorialSourceInspectionState()))
        unsentNarrative?.let {
            bookNarrativeStore?.chooseForm(it.form)
            bookNarrativeStore?.updateInstructions(it.instructions)
        }
        memoryBookEditorialLoadedKey = editorialKey(identity?.account_id ?: return, reading.library, updated)
    }

    private fun bookChatInteractionActive(): Boolean {
        val chat = state.value.memoryBooks?.companion ?: return false
        val dictation = chat.dictation?.state?.value
        return chat.busy || chat.pendingConversation != null || chat.pendingTurn != null ||
            conversationJobActive(chat.job, chat.turns) || dictation?.let { it.loading || it.recording || it.transcribing } == true
    }

    private fun bookChatOperationActive(): Boolean {
        val narrative = memoryBookNarrativeState.value
        return memoryBookEditionState.value.hasUnfinishedWork || bookChatInteractionActive() || bookNarrativeDictation.hasUnfinishedInput || narrative.busy || narrative.pendingRequest != null ||
            narrative.job?.state in setOf("queued", "running")
    }

    private fun currentMemoryBookNarrativeScope(): MemoryBookNarrativeScope? {
        val reading = state.value.memoryBooks ?: return null
        val book = reading.selectedBook ?: return null
        val credential = token ?: return null
        val accountId = identity?.account_id ?: return null
        if (!memoryCommunityAvailable || !allowed() || reading.library != state.value.library) return null
        return MemoryBookNarrativeScope(accountId, credential, reading.library, state.value.generation,
            book.id, book.revision, book.stories.map { EditorialChild(it.id, it.revision.toString()) }, bookChatEpoch)
    }

    private fun canOperateMemoryBookNarrative(allowInstructionTranscript: Boolean = false): Boolean {
        val reading = state.value.memoryBooks ?: return false
        return currentMemoryBookNarrativeScope() != null && !state.value.busy && !reading.readerBusy &&
            !coolingDown() && !bookChatInteractionActive() && !memoryBookEditionState.value.hasUnfinishedWork &&
            (allowInstructionTranscript || !bookNarrativeDictation.hasUnfinishedInput) && editorialStore.state.value.status !in
            setOf(MemoryBookEditorialStoreStatus.SAVING, MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN)
    }

    /** Opens a transient instruction editor; recording and generation need their own user actions. */
    fun openMemoryBookNarrativeDictation(): Boolean {
        val narrative = memoryBookNarrativeState.value
        if (!canOperateMemoryBookNarrative(allowInstructionTranscript = true) || narrative.busy ||
            narrative.pendingRequest != null || narrative.job?.state in setOf("queued", "running")) return false
        return bookNarrativeDictation.open() != null
    }

    fun insertMemoryBookNarrativeDictation(): Boolean {
        if (!canOperateMemoryBookNarrative(allowInstructionTranscript = true)) return false
        return bookNarrativeDictation.insertTranscript { words ->
            val existing = memoryBookNarrativeState.value.instructions
            val combined = if (existing.isEmpty()) words else "$existing\n$words"
            bookNarrativeStore?.updateInstructions(combined) == true
        }
    }

    fun clearMemoryBookNarrativeDictation() = bookNarrativeDictation.clear()

    fun updateMemoryBookNarrativeInstructions(text: String): Boolean =
        canOperateMemoryBookNarrative() && bookNarrativeStore?.updateInstructions(text) == true
    fun chooseMemoryBookNarrativeEditorialContext(selected: Boolean) {
        if (canOperateMemoryBookNarrative()) bookNarrativeStore?.chooseEditorialContext(selected)
    }
    fun chooseMemoryBookNarrativeForm(form: MemoryBookNarrativeForm): Boolean =
        canOperateMemoryBookNarrative() && bookNarrativeStore?.chooseForm(form) == true
    fun checkMemoryBookNarrativePlan() {
        if (!canOperateMemoryBookNarrative()) return
        launch { _ -> bookNarrativeStore?.checkPlan() }
    }
    fun requestMemoryBookNarrative() {
        if (!canOperateMemoryBookNarrative() || state.value.memoryBooks?.capabilities?.generationEnabled != true) return
        launch { _ -> bookNarrativeStore?.queue() }
    }
    fun retryMemoryBookNarrative() {
        if (!canOperateMemoryBookNarrative() || state.value.memoryBooks?.capabilities?.generationEnabled != true) return
        launch { _ -> bookNarrativeStore?.retry() }
    }
    fun refreshMemoryBookNarrative() {
        if (canOperateMemoryBookNarrative()) launch { _ -> bookNarrativeStore?.refresh() }
    }
    fun cancelMemoryBookNarrative() {
        if (canOperateMemoryBookNarrative()) launch { _ -> bookNarrativeStore?.cancelKnownJob() }
    }

    /** Opens only the current ready proposal; neither completion nor reading triggers adoption. */
    fun openMemoryBookEditionReview(): Boolean {
        val book = state.value.memoryBooks?.selectedBook ?: return false
        val narrative = memoryBookNarrativeState.value
        val job = narrative.job ?: return false
        val proposal = narrative.proposal ?: return false
        if (!book.canEdit || !canOperateMemoryBookNarrative() || narrative.busy ||
            job.state != "ready" || job.baseRevision != book.revision || proposal.chapters.isEmpty()) return false
        return bookEditionStore?.open(job.id, proposal.chapters.map { it.id }) == true
    }
    fun editMemoryBookEditionTitle(text: String) = bookEditionStore?.editTitle(text) == true
    fun editMemoryBookEditionChapter(index: Int, text: String) = bookEditionStore?.editChapter(index, text) == true
    fun composeMemoryBookEdition(active: Boolean) { bookEditionStore?.composition(active) }
    fun markMemoryBookEditionInvalidInput(active: Boolean) { bookEditionStore?.invalidInput(active) }
    fun reviewMemoryBookEdition(reviewed: Boolean) = bookEditionStore?.confirmReviewed(reviewed) == true
    fun saveMemoryBookEdition() = bookEditionStore?.save() == true
    fun retryMemoryBookEditionSave() = bookEditionStore?.retrySave() == true
    fun readMemoryBookEdition() = bookEditionStore?.readSaved() == true
    fun closeMemoryBookEditionReview(confirmed: Boolean = false) = bookEditionStore?.close(confirmed) == true

    /** Library readers need neither editorial permission nor a retained generation job. */
    fun loadMemoryBookEditionShelf(page: Int = 1): Boolean {
        val reading = state.value.memoryBooks ?: return false
        if (currentMemoryBookNarrativeScope() == null || state.value.busy || reading.readerBusy ||
            coolingDown() || memoryBookEditionState.value.hasUnfinishedWork) return false
        return bookEditionShelfStore?.loadPage(page) == true
    }
    fun readMemoryBookShelfEdition(id: String): Boolean {
        val reading = state.value.memoryBooks ?: return false
        if (state.value.busy || reading.readerBusy || coolingDown() || memoryBookEditionState.value.hasUnfinishedWork) return false
        return bookEditionShelfStore?.read(id) == true
    }
    fun closeMemoryBookEditionShelfReading() { bookEditionShelfStore?.closeReading() }
    fun closeMemoryBookEditionShelf() { bookEditionShelfStore?.clear() }

    private fun currentMemoryBookEditionSourceScope(): MemoryBookEditionSourceScope? {
        val book = currentMemoryBookNarrativeScope() ?: return null
        val reader = bookEditionShelfStore?.state?.value ?: return null
        val detail = reader.detail ?: return null
        if (reader.busy || reader.status != MemoryBookEditionShelfStatus.READ ||
            detail.receipt.state != MemoryBookEditionState.CURRENT || detail.receipt.bookId != book.bookId ||
            detail.receipt.bookRevision != book.bookRevision.toString() || reader.selectedId != detail.receipt.id) return null
        val manuscript = detail.manuscript ?: return null
        return MemoryBookEditionSourceScope(book,detail.receipt.id,manuscript.chapters.flatMap { it.sourceIds }.distinct())
    }
    private fun memoryBookSourceActionAllowed(): Boolean {
        val reading = state.value.memoryBooks ?: return false
        return !state.value.busy && !reading.readerBusy && !coolingDown() &&
            !memoryBookEditionState.value.hasUnfinishedWork && currentMemoryBookEditionSourceScope() != null
    }
    fun loadMemoryBookEditionSources(page: Int = 1): Boolean =
        memoryBookSourceActionAllowed() && bookEditionSourceStore?.loadPage(page) == true
    fun readMemoryBookEditionSource(id: String): Boolean =
        memoryBookSourceActionAllowed() && bookEditionSourceStore?.read(id) == true
    fun loadMemoryBookEditionSourceAudio(): Boolean =
        memoryBookSourceActionAllowed() && bookEditionSourceStore?.loadAudio() == true
    fun closeMemoryBookEditionSourceAudio() { bookEditionSourceStore?.closeAudio() }
    fun clearMemoryBookEditionSources() { bookEditionSourceStore?.clear() }

    private fun clearMemoryBookEditorial() {
        clearMemoryBookEditorialSourceInspection()
        memoryBookEditorialRequest++
        memoryBookEditorialLoadedKey = null
        editorialStore.clear()
        memoryBookEditorialCatalog.value = MemoryBookEditorialCatalogState()
    }

    private fun editorialKey(accountId: String, library: String, book: MemoryBook): String =
        listOf(accountId, library, book.id, book.revision, book.stories.joinToString("|") { "${it.id}:${it.revision}" }).joinToString("/")

    private fun invalidateBookChatRequests() {
        bookEditionStore?.clear()
        bookEditionShelfStore?.clear()
        bookNarrativeDictation.clear()
        bookNarrativeStore?.clear()
        bookChatEpoch++
        bookChatJobs.toList().forEach { it.cancel() }
        bookChatJobs.clear()
    }

    private fun bookChatCurrent(bookId: String, revision: Long, expectedToken: Bearer, library: String,
                                generation: Long, epoch: Long): Boolean {
        val reading = state.value.memoryBooks ?: return false
        val book = reading.selectedBook
        val chat = reading.companion
        return memoryCommunityAvailable && active(generation) && token === expectedToken && allowed() &&
            state.value.library == library && reading.library == library &&
            book?.id == bookId && book.revision == revision && chat?.bookId == bookId && chat.bookRevision == revision &&
            bookChatEpoch == epoch
    }

    private fun launchBookChat(action: suspend (MemoryCommunityRepository, MemoryBookChatState, () -> Boolean) -> MemoryBookChatState) {
        val beforeReading = state.value.memoryBooks ?: return
        val before = beforeReading.companion ?: return
        if (before.busy || beforeReading.story == null || !allowed() || bookNarrativeDictation.hasUnfinishedInput) return
        val repository = memoryCommunity ?: return
        val expectedToken = token ?: return
        val library = beforeReading.library; val generation = state.value.generation; val epoch = bookChatEpoch
        val valid = { bookChatCurrent(before.bookId, before.bookRevision, expectedToken, library, generation, epoch) }
        mutable.value = state.value.copy(memoryBooks = beforeReading.copy(companion = before.copy(busy = true, failure = null)))
        val job = scope.launch {
            try {
                if (!valid()) return@launch
                val result = action(repository, before, valid)
                if (!valid()) return@launch
                val live = state.value.memoryBooks?.companion ?: return@launch
                val sameThread = result.conversationId == before.conversationId
                val mergedDraft = if (sameThread && live.draft != before.draft) live.draft else result.draft
                val merged = result.copy(draft = mergedDraft,
                    threadDrafts = mergeThreadDraftChanges(result.threadDrafts, before.threadDrafts, live.threadDrafts,
                        before.conversationId, before.draft, live.draft, result.conversationId, mergedDraft, result.conversations),
                    dictation = if (live.dictation !== before.dictation) live.dictation else result.dictation)
                mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(companion = merged.copy(busy = false, failure = null)))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (valid()) {
                    if (e is ApiFailure && e.status in listOf(401, 403)) {
                        val current = state.value.memoryBooks?.companion
                        if (current != null) mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(
                            companion = current.copy(busy = false, failure = null)))
                        readFailure(e, generation, expectedToken) { closeMemoryBooks() }
                    } else {
                        val live = state.value.memoryBooks?.companion ?: return@launch
                        mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(companion = live.copy(busy = false, failure = problem(e))))
                    }
                }
            }
        }
        bookChatJobs += job
        job.invokeOnCompletion { bookChatJobs.remove(job) }
    }

    fun queueMemoryBookConversation() {
        val reading = state.value.memoryBooks ?: return
        val chat = reading.companion ?: return
        if (!canMutateMemoryBookChat(reading, chat) || !canChangeMemoryBookThread(chat)) return
        if (chat.pendingConversation == null) {
            val request = MemoryConversationRequest(targetType = "book", targetId = chat.bookId)
            val drafts = chat.conversationId?.let { rememberThreadDraft(chat.threadDrafts, chat.conversationId, chat.draft, chat.conversations) }
                ?: chat.threadDrafts
            val draft = if (chat.conversationId == null) chat.draft else ""
            mutable.value = state.value.copy(memoryBooks = reading.copy(companion = chat.copy(
                pendingConversation = request, threadDrafts = drafts, draft = draft,
                editorialContext = MemoryBookChatEditorialContext.BASIC)))
        }
        retryStartMemoryBookConversation()
    }

    fun retryStartMemoryBookConversation() = launchBookChat { repository, before, valid ->
        if (before.pendingTurn != null) return@launchBookChat before
        val request = before.pendingConversation ?: return@launchBookChat before
        val conversation = repository.startConversation(request)
        if (!valid()) return@launchBookChat before
        val conversations = repository.conversations("book", before.bookId, withPreview = true, currentRequest = valid)
        if (!valid()) return@launchBookChat before
        val turns = repository.turns(conversation.id, 1, replyContext = true)
        if (!valid()) return@launchBookChat before
        val job = recoverPendingChatJob(repository, turns, before.bookRevision, valid)
        val drafts = before.threadDrafts
        val newDraft = if (before.conversationId == null) before.draft else drafts[conversation.id].orEmpty()
        val boundedDrafts = rememberThreadDraft(drafts, conversation.id, newDraft, conversations)
        before.copy(conversations = conversations, conversationId = conversation.id, turns = turns, job = job,
            threadDrafts = boundedDrafts, draft = newDraft,
            pendingConversation = null, pendingTurn = null, pendingTurnConversationId = null)
    }

    fun selectMemoryBookConversation(id: String) = launchBookChat { repository, before, valid ->
        if (!canChangeMemoryBookThread(before)) return@launchBookChat before
        if (before.conversations?.items?.none { it.id == id } != false) return@launchBookChat before
        val turns = repository.turns(id, 1, replyContext = true)
        if (!valid()) return@launchBookChat before
        val job = recoverPendingChatJob(repository, turns, before.bookRevision, valid)
        val drafts = rememberThreadDraft(before.threadDrafts, before.conversationId, before.draft, before.conversations)
        before.copy(conversationId = id, turns = turns, job = job, threadDrafts = drafts,
            draft = drafts[id].orEmpty(), pendingTurn = null, pendingTurnConversationId = null,
            editorialContext = if (id == before.conversationId) before.editorialContext else MemoryBookChatEditorialContext.BASIC)
    }

    fun loadMemoryBookTurnsPage(page: Int) = launchBookChat { repository, before, valid ->
        if (page !in 1..8) return@launchBookChat before
        val id = before.conversationId ?: return@launchBookChat before
        if (!valid()) return@launchBookChat before
        val turns = repository.turns(id, page, replyContext = true)
        if (!valid()) return@launchBookChat before
        before.copy(turns = turns)
    }

    fun updateMemoryBookChatDraft(text: String): Boolean {
        if (text.toByteArray(Charsets.UTF_8).size > 4096 || text.any { it == '\u0000' }) return false
        val reading = state.value.memoryBooks ?: return false
        val chat = reading.companion ?: return false
        val drafts = chat.conversationId?.let { rememberThreadDraft(chat.threadDrafts, it, text, chat.conversations) }
            ?: chat.threadDrafts
        mutable.value = state.value.copy(memoryBooks = reading.copy(companion = chat.copy(draft = text, threadDrafts = drafts)))
        return true
    }

    fun chooseMemoryBookChatFollowup(
        accountId: String, generation: Long, library: String, readerScopeId: Long,
        bookId: String, bookRevision: Long, storyId: String, storyRevision: Long,
        conversationId: String, page: Int, turnId: String, question: String,
    ): MemoryChatFollowupResult {
        val live = state.value
        val reading = live.memoryBooks ?: return MemoryChatFollowupResult.STALE
        val book = reading.selectedBook ?: return MemoryChatFollowupResult.STALE
        val story = reading.story ?: return MemoryChatFollowupResult.STALE
        val chat = reading.companion ?: return MemoryChatFollowupResult.STALE
        val turns = chat.turns ?: return MemoryChatFollowupResult.STALE
        if (live.session?.account_id != accountId || live.generation != generation || live.library != library ||
            reading.library != library || reading.readerScopeId != readerScopeId || memoryBooksReaderRequest != readerScopeId ||
            book.id != bookId || book.revision != bookRevision || chat.bookId != bookId || chat.bookRevision != bookRevision ||
            story.id != storyId || story.revision != storyRevision || chat.conversationId != conversationId ||
            turns.conversationId != conversationId || turns.page != page ||
            !memoryCommunityAvailable || memoryCommunity == null || !allowed()) return MemoryChatFollowupResult.STALE
        val turn = turns.items.firstOrNull { it.id == turnId } ?: return MemoryChatFollowupResult.STALE
        val context = memoryReplyContext(turn, chat.job, bookRevision)
        if (turn.state != "ready" || context?.questions?.contains(question) != true)
            return MemoryChatFollowupResult.STALE
        if (live.busy || reading.busy || reading.readerBusy || chat.busy || chat.pendingConversation != null ||
            chat.pendingTurn != null || conversationJobActive(chat.job, chat.turns) ||
            dictationHasUnfinishedInput(chat.dictation) || chat.draft.isNotBlank()) return MemoryChatFollowupResult.BLOCKED
        val drafts = rememberThreadDraft(chat.threadDrafts, conversationId, question, chat.conversations)
        val nextFocus = nextRequestId(chat.chatDraftFocusRequestId)
        mutable.value = live.copy(memoryBooks = reading.copy(companion = chat.copy(
            draft = question, threadDrafts = drafts, chatDraftFocusRequestId = nextFocus)))
        return MemoryChatFollowupResult.SELECTED
    }

    /** Only the visible authorized chapter in an already selected memoir thread is eligible. */
    fun memoryBookChapterDiscussionContext(): MemoryBookChapterDiscussionContext? {
        val live = state.value
        val account = live.session?.account_id ?: return null
        val reading = live.memoryBooks ?: return null
        val book = reading.selectedBook ?: return null
        val story = reading.story ?: return null
        val chat = reading.companion ?: return null
        val conversation = chat.conversationId ?: return null
        val turns = chat.turns ?: return null
        val child = book.stories.getOrNull(reading.storyIndex ?: return null) ?: return null
        val chapter = story.chapters.getOrNull(reading.selectedChapter) ?: return null
        if (!memoryCommunityAvailable || memoryCommunity == null || token == null || !allowed() ||
            reading.capabilities?.generationEnabled != true || reading.library != live.library ||
            reading.readerScopeId != memoryBooksReaderRequest || reading.busy || reading.readerBusy || reading.readerUnavailable ||
            chat.bookId != book.id || chat.bookRevision != book.revision || turns.conversationId != conversation ||
            child.id != story.id || child.revision != story.revision || story.libraryId != reading.library) return null
        return MemoryBookChapterDiscussionContext(account, live.generation, reading.library, reading.readerScopeId,
            book.id, book.revision, story.id, story.revision, chapter.id, reading.selectedChapter,
            story.title, chapter.title, conversation).takeIf { memoryBookChapterDiscussionQuestion(it, true) != null }
    }

    /** Insert a bounded editable question, without creating a thread, fetching context or sending. */
    fun chooseMemoryBookChapterDiscussion(
        expected: MemoryBookChapterDiscussionContext, zh: Boolean,
    ): MemoryChatFollowupResult {
        if (memoryBookChapterDiscussionContext() != expected) return MemoryChatFollowupResult.STALE
        val live = state.value
        val reading = live.memoryBooks ?: return MemoryChatFollowupResult.STALE
        val chat = reading.companion ?: return MemoryChatFollowupResult.STALE
        if (!canMutateMemoryBookChat(reading, chat) || !canChangeMemoryBookThread(chat) || chat.draft.isNotBlank())
            return MemoryChatFollowupResult.BLOCKED
        val question = memoryBookChapterDiscussionQuestion(expected, zh) ?: return MemoryChatFollowupResult.STALE
        val drafts = rememberThreadDraft(chat.threadDrafts, expected.conversationId, question, chat.conversations)
        mutable.value = live.copy(memoryBooks = reading.copy(companion = chat.copy(
            draft = question, threadDrafts = drafts, chatDraftFocusRequestId = nextRequestId(chat.chatDraftFocusRequestId))))
        return MemoryChatFollowupResult.SELECTED
    }

    private fun canChangeMemoryBookThread(chat: MemoryBookChatState): Boolean =
        !chat.busy && chat.pendingTurn == null && chat.pendingConversation == null &&
            !conversationJobActive(chat.job, chat.turns) && !dictationHasUnfinishedInput(chat.dictation)

    private fun canMutateMemoryBookChat(reading: MemoryBooksReading, chat: MemoryBookChatState): Boolean {
        val book = reading.selectedBook ?: return false
        return memoryCommunityAvailable && memoryCommunity != null && token != null && allowed() &&
            !state.value.busy && !coolingDown() && !chat.busy && reading.story != null &&
            !bookNarrativeDictation.hasUnfinishedInput && !memoryBookEditionState.value.hasUnfinishedWork &&
            editorialStore.state.value.status !in setOf(MemoryBookEditorialStoreStatus.SAVING, MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN) &&
            reading.library == state.value.library && chat.bookId == book.id && chat.bookRevision == book.revision
    }

    /** This reads saved structure only. It never records, transcribes, queues or sends a message. */
    fun chooseMemoryBookChatEditorialContext(selected: Boolean) {
        val reading = state.value.memoryBooks ?: return
        val chat = reading.companion ?: return
        if (!canMutateMemoryBookChat(reading, chat) || !canChangeMemoryBookThread(chat)) return
        if (!selected) {
            mutable.value = state.value.copy(memoryBooks = reading.copy(companion = chat.copy(
                editorialContext = MemoryBookChatEditorialContext.BASIC)))
            return
        }
        mutable.value = state.value.copy(memoryBooks = reading.copy(companion = chat.copy(
            editorialContext = MemoryBookChatEditorialContext.CHECKING)))
        launchBookChat { repository, before, valid ->
            val choice = try {
                val plan = repository.bookPlan(before.bookId, before.bookRevision, editorialContext = true, currentRequest = valid)
                if (!valid()) return@launchBookChat before
                when (plan.whole.state) {
                    "within_limits" -> MemoryBookChatEditorialContext.READY
                    "smaller_scope_required" -> MemoryBookChatEditorialContext.SMALLER_SCOPE
                    else -> throw ApiFailure(FailureKind.INVALID_RESPONSE)
                }
            } catch (e: CancellationException) { throw e }
            catch (e: ApiFailure) {
                if (e.status in setOf(401, 403)) throw e
                when (e.status) {
                    503 -> MemoryBookChatEditorialContext.UNAVAILABLE
                    409 -> MemoryBookChatEditorialContext.CHANGED
                    422 -> MemoryBookChatEditorialContext.SMALLER_SCOPE
                    else -> MemoryBookChatEditorialContext.FAILED
                }
            }
            before.copy(editorialContext = choice)
        }
    }

    fun sendMemoryBookChat() {
        val reading = state.value.memoryBooks ?: return
        val chat = reading.companion ?: return
        val book = reading.selectedBook ?: return
        if (!canMutateMemoryBookChat(reading, chat) || chat.editorialContext !in setOf(MemoryBookChatEditorialContext.BASIC, MemoryBookChatEditorialContext.READY) ||
            (chat.conversationId != null && chat.turns == null) || chat.pendingTurn != null || conversationJobActive(chat.job, chat.turns) ||
            dictationHasUnfinishedInput(chat.dictation)) return
        if (chat.conversationId == null) { queueMemoryBookConversation(); return }
        if (chat.draft.isBlank()) return
        val conversationId = chat.conversationId
        val request = MemoryTurnRequest(book.revision, chat.draft,
            editorialContext = chat.editorialContext == MemoryBookChatEditorialContext.READY)
        val remainingDraft = ""
        val drafts = rememberThreadDraft(chat.threadDrafts, conversationId, remainingDraft, chat.conversations)
        mutable.value = state.value.copy(memoryBooks = reading.copy(companion = chat.copy(
            pendingTurn = request, pendingTurnConversationId = conversationId, draft = remainingDraft, threadDrafts = drafts)))
        retryMemoryBookChatTurn()
    }

    fun retryMemoryBookChatTurn() = launchBookChat { repository, before, valid ->
        val id = before.pendingTurnConversationId ?: return@launchBookChat before
        val request = before.pendingTurn ?: return@launchBookChat before
        val job = repository.sendTurn(id, request)
        if (!valid()) return@launchBookChat before
        val turns = repository.turns(id, 1, replyContext = true)
        if (!valid()) return@launchBookChat before
        before.copy(job = job, pendingTurn = null, pendingTurnConversationId = null, turns = turns)
    }

    fun refreshMemoryBookChat() = launchBookChat { repository, before, valid ->
        val id = before.conversationId ?: return@launchBookChat before
        val turns = repository.turns(id, before.turns?.page ?: 1, replyContext = true)
        if (!valid()) return@launchBookChat before
        val pendingRows = turns.items.filter { it.state in setOf("queued", "running") && it.jobId != null }
        val pendingJob = recoverPendingChatJob(repository, turns, before.bookRevision, valid)
        val job = when {
            pendingRows.size == 1 -> pendingJob ?: before.job?.takeIf {
                it.id == pendingRows.single().jobId && it.kind == "chat" && it.baseRevision == before.bookRevision
            }
            pendingRows.isNotEmpty() -> null
            else -> before.job?.takeIf { it.kind == "chat" && it.baseRevision == before.bookRevision }
                ?.let { fetchBoundChatJob(repository, it.id, before.bookRevision, valid) }
        }
        if (!valid()) return@launchBookChat before
        val activeJob = if (pendingRows.isEmpty()) job ?: before.job?.takeIf {
            it.kind == "chat" && it.baseRevision == before.bookRevision
        } else job
        before.copy(job = activeJob, turns = turns)
    }

    fun memoryBookChatDictation(): MemoryDictationStore? {
        if (!api.assistantEnabled || !memoryCommunityAvailable || bookNarrativeDictation.hasUnfinishedInput) return null
        val reading = state.value.memoryBooks ?: return null
        val chat = reading.companion ?: return null
        chat.dictation?.let { return it }
        val expectedToken = token ?: return null
        val library = reading.library; val id = chat.bookId; val revision = chat.bookRevision
        val generation = state.value.generation; val epoch = bookChatEpoch
        fun check() {
            if (!bookChatCurrent(id, revision, expectedToken, library, generation, epoch)) throw CancellationException("Memoir scope changed")
        }
        val dictation = MemoryDictationStore(scope, capabilities = {
            check(); val value = api.assistantCapabilities(expectedToken, library); check(); value
        }, transcribe = { wav, requestId ->
            check(); val value = api.assistantTranscribe(expectedToken, library, wav, requestId); check(); value
        }, onDenied = ::memoryCommunityDenied, now = now)
        mutable.value = state.value.copy(memoryBooks = reading.copy(companion = chat.copy(dictation = dictation)))
        return dictation
    }

    private fun wipeMemoryBookMedia(reading: MemoryBooksReading?) {
        reading?.frames?.values?.forEach { it.fill(0) }
        reading?.hero?.fill(0)
    }

    private fun memoryBookResumeKey(library: String, book: MemoryBook): MemoryBookResumeKey? =
        identity?.account_id?.let { MemoryBookResumeKey(it, library, book.id, book.revision) }

    private fun findMemoryBookResume(library: String, book: MemoryBook): MemoryBookResumePosition? {
        val key = memoryBookResumeKey(library, book) ?: return null
        val position = memoryBookResume[key] ?: return null
        if (book.stories.any { it.id == position.storyId && it.revision == position.storyRevision }) return position
        memoryBookResume.remove(key)
        return null
    }

    private fun saveMemoryBookResume(reading: MemoryBooksReading, chapterId: String) {
        val accountBook = reading.selectedBook ?: return
        val story = reading.story ?: return
        val account = identity?.account_id ?: return
        val key = MemoryBookResumeKey(account, reading.library, accountBook.id, accountBook.revision)
        memoryBookResume.remove(key)
        memoryBookResume[key] = MemoryBookResumePosition(story.id, story.revision, chapterId)
        while (memoryBookResume.size > 12) memoryBookResume.remove(memoryBookResume.keys.first())
    }

    private fun removeMemoryBookResume(library: String, book: MemoryBook) {
        memoryBookResumeKey(library, book)?.let(memoryBookResume::remove)
    }

    fun loadMemoryBookChapter(index: Int, framePage: Int = 0) {
        val reading = state.value.memoryBooks ?: return
        val story = reading.story ?: return
        val selectedBook = reading.selectedBook ?: return
        val pageCount = ((story.chapters.getOrNull(index)?.assetIds?.size ?: return) + MEMORY_BOOK_CHAPTER_ASSET_LIMIT - 1) / MEMORY_BOOK_CHAPTER_ASSET_LIMIT
        if (index !in story.chapters.indices || framePage !in 0 until pageCount.coerceAtLeast(1) || reading.readerBusy || !allowed() || reading.library != state.value.library) return
        if (index != reading.selectedChapter) clearMemoryBookEditorialSourceInspection()
        memoryBooksMediaRequest++
        val request = memoryBooksMediaRequest
        wipeMemoryBookMedia(reading)
        val assets = story.chapters[index].assetIds.drop(framePage * MEMORY_BOOK_CHAPTER_ASSET_LIMIT).take(MEMORY_BOOK_CHAPTER_ASSET_LIMIT)
            .mapNotNull { assetId -> story.items.firstOrNull { it.asset.id == assetId }?.asset }
        val library = reading.library
        val generation = state.value.generation
        mutable.value = state.value.copy(memoryBooks = reading.copy(selectedChapter = index,
            framePage = framePage, selectedAssetId = assets.firstOrNull()?.id, frames = emptyMap(), framesBusy = true,
            unavailableFrameIds = emptySet(), framesUnavailable = false, heroAssetId = null, hero = null,
            heroBusy = assets.isNotEmpty(), heroUnavailable = false,
            sourceInspection = if (index != reading.selectedChapter) MemoryBookEditorialSourceInspectionState() else reading.sourceInspection))
        story.chapters.getOrNull(index)?.id?.let { saveMemoryBookResume(reading, it) }
        val credential = token ?: return
        launch { activeGeneration ->
            val frames = linkedMapOf<String, ByteArray>()
            val unavailable = linkedSetOf<String>()
            var hero: ByteArray? = null
            try {
                for (asset in assets) {
                    if (!active(activeGeneration) || activeGeneration != generation || request != memoryBooksMediaRequest) {
                        frames.values.forEach { it.fill(0) }; return@launch
                    }
                    val bytes = api.thumbnail(credential, library, asset)
                    if (!active(activeGeneration) || activeGeneration != generation || request != memoryBooksMediaRequest) {
                        bytes?.fill(0); frames.values.forEach { it.fill(0) }; return@launch
                    }
                    if (bytes != null) {
                        if (bytes.size > HttpsPhotoHouseApi.IMAGE_LIMIT) { bytes.fill(0); throw ApiFailure(FailureKind.TOO_LARGE) }
                        frames[asset.id] = bytes
                    } else unavailable += asset.id
                }
                val heroAsset = assets.firstOrNull()
                if (heroAsset != null) {
                    val preview = api.detailPreview(credential, library, heroAsset)
                    if (!active(activeGeneration) || activeGeneration != generation || request != memoryBooksMediaRequest) {
                        frames.values.forEach { it.fill(0) }; preview?.fill(0); return@launch
                    }
                    if (preview != null && preview.size > HttpsPhotoHouseApi.IMAGE_LIMIT) {
                        preview.fill(0); throw ApiFailure(FailureKind.TOO_LARGE)
                    }
                    hero = preview
                }
                val current = state.value.memoryBooks
                if (!active(activeGeneration) || activeGeneration != generation || request != memoryBooksMediaRequest ||
                    state.value.library != library || current?.selectedBook?.id != selectedBook.id || current.story?.id != story.id ||
                    current.selectedChapter != index) {
                    frames.values.forEach { it.fill(0) }; hero?.fill(0); return@launch
                }
                mutable.value = state.value.copy(memoryBooks = current.copy(frames = frames, framesBusy = false,
                    unavailableFrameIds = unavailable, heroAssetId = heroAsset?.id, hero = hero, heroBusy = false, heroUnavailable = hero == null))
            } catch (e: CancellationException) { frames.values.forEach { it.fill(0) }; hero?.fill(0); throw e }
            catch (e: Exception) {
                frames.values.forEach { it.fill(0) }; hero?.fill(0)
                if (!active(activeGeneration) || activeGeneration != generation || request != memoryBooksMediaRequest) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, activeGeneration, credential) { closeMemoryBooks() }
                else mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(framesBusy = false,
                    framesUnavailable = true, heroBusy = false, heroUnavailable = true))
            }
        }
    }

    fun selectMemoryBookAsset(assetId: String) {
        val reading = state.value.memoryBooks ?: return
        val story = reading.story ?: return
        val chapter = story.chapters.getOrNull(reading.selectedChapter) ?: return
        val visibleAssetIds = chapter.assetIds.drop(reading.framePage * MEMORY_BOOK_CHAPTER_ASSET_LIMIT).take(MEMORY_BOOK_CHAPTER_ASSET_LIMIT)
        if (assetId !in visibleAssetIds || reading.readerBusy || reading.framesBusy || !allowed()) return
        val asset = story.items.firstOrNull { it.asset.id == assetId }?.asset ?: return
        memoryBooksMediaRequest++
        val request = memoryBooksMediaRequest
        val generation = state.value.generation
        val library = reading.library
        reading.hero?.fill(0)
        mutable.value = state.value.copy(memoryBooks = reading.copy(selectedAssetId = assetId,
            heroAssetId = null, hero = null, heroBusy = true, heroUnavailable = false))
        val credential = token ?: return
        launch { activeGeneration ->
            var bytes: ByteArray? = null
            try {
                val preview = api.detailPreview(credential, library, asset)
                if (preview != null && preview.size > HttpsPhotoHouseApi.IMAGE_LIMIT) {
                    preview.fill(0); throw ApiFailure(FailureKind.TOO_LARGE)
                }
                bytes = preview
                val current = state.value.memoryBooks
                if (!active(activeGeneration) || activeGeneration != generation || request != memoryBooksMediaRequest ||
                    state.value.library != library || current?.story?.id != story.id || current.selectedChapter != reading.selectedChapter ||
                    current.selectedAssetId != assetId) { bytes?.fill(0); return@launch }
                mutable.value = state.value.copy(memoryBooks = current.copy(heroAssetId = assetId, hero = bytes, heroBusy = false, heroUnavailable = bytes == null))
            } catch (e: CancellationException) { bytes?.fill(0); throw e }
            catch (e: Exception) {
                bytes?.fill(0)
                if (!active(activeGeneration) || activeGeneration != generation || request != memoryBooksMediaRequest) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, activeGeneration, credential) { closeMemoryBooks() }
                else mutable.value = state.value.copy(memoryBooks = state.value.memoryBooks?.copy(heroBusy = false, heroUnavailable = true))
            }
        }
    }

    fun loadMemoryBookFramePage(page: Int) {
        val reading = state.value.memoryBooks ?: return
        loadMemoryBookChapter(reading.selectedChapter, page)
    }

    private fun loadSavedMemoryStoryCovers(summaries: List<SavedMemoryStorySummary>) {
        val reading = state.value.savedMemoryStories ?: return
        if (summaries.isEmpty() || reading.library != state.value.library || !allowed()) return
        val request = ++savedMemoryCoversRequest
        val library = reading.library; val credential = token!!
        launch { generation ->
            val covers = linkedMapOf<String, ByteArray>()
            try {
                for (summary in summaries) {
                    if (!active(generation) || request != savedMemoryCoversRequest) {
                        covers.values.forEach { it.fill(0) }; return@launch
                    }
                    val assetId = summary.coverAssetId
                    val scopedPath = okhttp3.HttpUrl.Builder().scheme("https").host("contract.invalid")
                        .addPathSegment("assets").addPathSegment(assetId).addPathSegment("thumbnail")
                        .addQueryParameter("library", library).build().let { it.encodedPath + "?" + it.encodedQuery }
                    val asset = Asset(assetId, "image", null, null, null, null, scopedPath)
                    api.thumbnail(credential, library, asset)?.let { bytes ->
                        validResponse(bytes.size <= HttpsPhotoHouseApi.IMAGE_LIMIT)
                        covers[summary.id] = bytes
                    }
                }
                if (!active(generation) || request != savedMemoryCoversRequest || state.value.library != library ||
                    state.value.savedMemoryStories?.library != library || state.value.savedMemoryStories?.page != reading.page) {
                    covers.values.forEach { it.fill(0) }; return@launch
                }
                mutable.value = state.value.copy(savedMemoryStories = state.value.savedMemoryStories!!.copy(covers = covers))
            } catch (e: CancellationException) { covers.values.forEach { it.fill(0) }; throw e }
            catch (e: Exception) {
                covers.values.forEach { it.fill(0) }
                if (!active(generation) || request != savedMemoryCoversRequest || state.value.library != library) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, generation, credential) { closeSavedMemoryStories() }
            }
        }
    }

    fun closeSavedMemoryStoryDetail() {
        clearMemoryCommunity(clearState = true)
        savedMemoryDetailRequest++; savedMemoryFramesRequest++; savedMemoryHeroRequest++
        savedMemoryReaderEpoch++; savedMemoryContributionReferencesRequest++; savedMemoryContributionDetailRequest++
        savedMemoryContributionReferenceSaveRequest++
        savedMemoryContributionChapterEpoch++
        val reading = state.value.savedMemoryStories ?: return
        if (reading.result == null) { openSavedMemoryStories(1); return }
        reading.frames.values.forEach { it.fill(0) }
        reading.hero?.fill(0)
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(detail = null, detailBusy = false,
            detailUnavailable = false, selectedSummary = null, selectedChapter = 0, frames = emptyMap(), heroAssetId = null,
            hero = null, heroBusy = false, framesBusy = false, contributionReferences = null,
            contributionReferencesBusy = false, contributionReferencesUnavailable = false,
            contributionReferenceDraft = null, contributionReferenceSaveBusy = false, contributionReferenceSaveError = false,
            contributionReferenceSaveConflict = false, pendingContributionReferenceMutation = null,
            contributionDetailChapterId = null, contributionDetailId = null, contributionDetail = null,
            contributionDetailBusy = false, contributionDetailUnavailable = false, problem = null))
    }

    private fun clearMemoryCommunity(clearState: Boolean = true) {
        communityEpoch++
        communityJobs.toList().forEach { it.cancel() }; communityJobs.clear()
        communityPendingAudio?.fill(0); communityPendingAudio = null
        val reading = state.value.savedMemoryStories
        reading?.community?.audio?.close()
        reading?.community?.dictation?.close()
        memoryCommunity?.clear()
        if (clearState && reading?.community != null)
            mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = null))
    }

    private fun memoryCommunityDenied() {
        if (!memoryCommunityAvailable || token == null) return
        invalidate(keepIdentity = true, cover = true)
        mutable.value = state.value.copy(problem = LiveProblem(Message.ACCESS_DENIED))
        retry = { foreground() }
    }

    private fun communityCurrent(storyId: String, expectedToken: Bearer, library: String,
                                 generation: Long, epoch: Long): Boolean =
        memoryCommunityAvailable && active(generation) && token === expectedToken &&
            state.value.library == library && state.value.savedMemoryStories?.detail?.id == storyId &&
            communityEpoch == epoch && allowed()

    private fun launchMemoryCommunity(
        storyId: String,
        busy: Boolean = true,
        action: suspend (MemoryCommunityRepository, MemoryCommunityStoryState, () -> Boolean) -> MemoryCommunityStoryState,
    ) {
        val repository = memoryCommunity ?: return
        val reading = state.value.savedMemoryStories ?: return
        val before = reading.community?.takeIf { it.storyId == storyId } ?: return
        if (!allowed() || reading.library != state.value.library || reading.detail?.id != storyId || before.busy) return
        val expectedToken = token ?: return
        val library = reading.library
        val generation = state.value.generation
        val epoch = communityEpoch
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = before.copy(busy = busy, failure = null)))
        val job = scope.launch {
            try {
                val result = action(repository, before, { communityCurrent(storyId, expectedToken, library, generation, epoch) })
                if (communityCurrent(storyId, expectedToken, library, generation, epoch)) {
                    val currentReading = state.value.savedMemoryStories ?: return@launch
                    val live = currentReading.community ?: return@launch
                    // An in-flight read/write may complete after the user has edited a local
                    // field or switched tabs. Keep those newer local choices while applying
                    // the response-owned fields from the request snapshot.
                    val sameThread = result.conversationId == before.conversationId
                    val mergedChatDraft = if (sameThread && live.chatDraft != before.chatDraft) live.chatDraft else result.chatDraft
                    val merged = result.copy(
                        tab = if (live.tab != before.tab) live.tab else result.tab,
                        contributionDraft = if (live.contributionDraft != before.contributionDraft) live.contributionDraft else result.contributionDraft,
                        contributionConsent = if (live.contributionConsent != before.contributionConsent) live.contributionConsent else result.contributionConsent,
                        audioConsent = if (live.audioConsent != before.audioConsent) live.audioConsent else result.audioConsent,
                        contributionWholeStory = if (live.contributionWholeStory != before.contributionWholeStory) live.contributionWholeStory else result.contributionWholeStory,
                        contributionLanguage = if (live.contributionLanguage != before.contributionLanguage) live.contributionLanguage else result.contributionLanguage,
                        chatDraft = mergedChatDraft,
                        threadDrafts = mergeThreadDraftChanges(result.threadDrafts, before.threadDrafts, live.threadDrafts,
                            before.conversationId, before.chatDraft, live.chatDraft, result.conversationId, mergedChatDraft, result.conversations),
                        dictation = if (live.dictation !== before.dictation) live.dictation else result.dictation,
                    )
                    mutable.value = state.value.copy(savedMemoryStories = currentReading.copy(community = merged.copy(busy = false, failure = null)))
                } else result.audio?.close()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (communityCurrent(storyId, expectedToken, library, generation, epoch)) {
                    if (e is ApiFailure && e.status in listOf(401, 403)) {
                        readFailure(e, generation, expectedToken) { closeSavedMemoryStories() }
                    } else {
                        val currentReading = state.value.savedMemoryStories ?: return@launch
                        val current = currentReading.community ?: return@launch
                        mutable.value = state.value.copy(savedMemoryStories = currentReading.copy(community = current.copy(busy = false, failure = problem(e))))
                    }
                }
            }
        }
        communityJobs += job
        job.invokeOnCompletion { communityJobs.remove(job) }
    }

    private fun initializeMemoryCommunity(storyId: String, wholeStory: Boolean = false) {
        if (!memoryCommunityAvailable || !allowed()) return
        val reading = state.value.savedMemoryStories ?: return
        if (reading.detail?.id != storyId || reading.community?.storyId == storyId) return
        clearMemoryCommunity(clearState = false)
        val refreshed = state.value.savedMemoryStories ?: return
        mutable.value = state.value.copy(savedMemoryStories = refreshed.copy(
            community = MemoryCommunityStoryState(storyId, readerScopeId = communityEpoch, contributionWholeStory = wholeStory)))
        launchMemoryCommunity(storyId) { repository, initial, current ->
            val caps = repository.loadCapabilities()
            if (!current()) return@launchMemoryCommunity initial
            if (!caps.enabled) return@launchMemoryCommunity initial.copy(capabilities = caps)
            val contributions = if (caps.contributionsEnabled) repository.contributions(storyId) else null
            if (!current()) return@launchMemoryCommunity initial.copy(capabilities = caps)
            val conversations = if (caps.generationEnabled) repository.conversations(
                "story", storyId, withPreview = true, currentRequest = current,
            ) else null
            if (!current()) return@launchMemoryCommunity initial
            val selected = conversations?.items?.firstOrNull()
            val turns = selected?.let {
                try { repository.turns(it.id, replyContext = true) }
                catch (e: CancellationException) { throw e }
                catch (_: Exception) { null }
            }
            if (!current()) return@launchMemoryCommunity initial
            val revision = state.value.savedMemoryStories?.detail?.revision ?: return@launchMemoryCommunity initial
            val job = turns?.let { recoverPendingChatJob(repository, it, revision, current) }
            initial.copy(capabilities = caps, contributions = contributions, conversations = conversations,
                conversationId = selected?.id, turns = turns, job = job)
        }
    }

    fun reloadMemoryContributions() {
        val current = state.value.savedMemoryStories?.community ?: return
        val pageNumber = current.contributions?.page ?: 1
        loadMemoryContributionPage(pageNumber)
    }

    fun loadMemoryContributionPage(pageNumber: Int) {
        if (pageNumber !in 1..100000) return
        val current = state.value.savedMemoryStories?.community ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val page = repository.contributions(current.storyId, pageNumber)
            if (!valid()) return@launchMemoryCommunity before
            before.copy(contributions = page)
        }
    }

    fun selectMemoryCommunityTab(tab: Int) {
        if (tab !in 0..2) return
        val reading = state.value.savedMemoryStories ?: return
        val community = reading.community ?: return
        if (community.contributionAudioBusy && tab != community.tab) return
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = community.copy(tab = tab)))
    }

    fun setMemoryContributionAudioBusy(
        library: String, storyId: String, revision: Long, expectedGeneration: Long, readerScopeId: Long,
        activityId: String, busy: Boolean,
    ) {
        val live = state.value
        val reading = live.savedMemoryStories ?: return
        val detail = reading.detail ?: return
        val community = reading.community ?: return
        if (live.generation != expectedGeneration || reading.library != library || detail.id != storyId ||
            detail.revision != revision || community.storyId != storyId || community.readerScopeId != readerScopeId) return
        if (busy) {
            if (community.contributionAudioActivityId != null && community.contributionAudioActivityId != activityId) return
            if (community.contributionAudioBusy && community.contributionAudioActivityId == activityId) return
            mutable.value = live.copy(savedMemoryStories = reading.copy(community = community.copy(
                contributionAudioBusy = true, contributionAudioActivityId = activityId)))
        } else {
            if (community.contributionAudioActivityId != activityId) return
            mutable.value = live.copy(savedMemoryStories = reading.copy(community = community.copy(
                contributionAudioBusy = false, contributionAudioActivityId = null)))
        }
    }

    fun keepMemoryChatTurnAsContribution(
        library: String, storyId: String, revision: Long, expectedGeneration: Long, readerScopeId: Long,
        conversationId: String, turnId: String,
    ): MemoryChatTurnSeedResult {
        val live = state.value
        val reading = live.savedMemoryStories ?: return MemoryChatTurnSeedResult.STALE
        val community = reading.community ?: return MemoryChatTurnSeedResult.STALE
        val detail = reading.detail ?: return MemoryChatTurnSeedResult.STALE
        val turns = community.turns ?: return MemoryChatTurnSeedResult.STALE
        if (live.generation != expectedGeneration || reading.library != library || detail.id != storyId || detail.revision != revision ||
            community.storyId != storyId || community.readerScopeId != readerScopeId || community.conversationId != conversationId ||
            community.tab != 1 || turns.conversationId != conversationId) return MemoryChatTurnSeedResult.STALE
        val turn = turns.items.firstOrNull { it.id == turnId && it.inputText.isNotBlank() }
            ?: return MemoryChatTurnSeedResult.STALE
        val caps = community.capabilities
        if (!memoryCommunityAvailable || token == null || !allowed() || caps?.enabled != true || !caps.contributionsEnabled)
            return MemoryChatTurnSeedResult.BLOCKED
        if (community.busy || community.pendingText != null || community.pendingAudio != null ||
            community.contributionDraft.isNotEmpty() || community.contributionConsent || community.audioConsent || community.contributionAudioBusy ||
            community.pendingTurn != null || community.pendingConversation != null || community.chatDraft.isNotEmpty() ||
            conversationJobActive(community.job, community.turns) || dictationHasUnfinishedInput(community.dictation))
            return MemoryChatTurnSeedResult.BLOCKED
        mutable.value = live.copy(savedMemoryStories = reading.copy(community = community.copy(
            tab = 0, contributionDraft = turn.inputText, contributionConsent = false,
            chatTurnContributionSeeded = true, contributionWholeStory = true,
            contributionFocusRequestId = community.contributionFocusRequestId + 1)))
        return MemoryChatTurnSeedResult.SEEDED
    }

    fun updateMemoryContributionDraft(text: String) {
        val reading = state.value.savedMemoryStories ?: return
        val community = reading.community ?: return
        if (text.toByteArray(Charsets.UTF_8).size <= 8192 && text.none { it == '\u0000' })
            mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = community.copy(contributionDraft = text)))
    }

    fun updateMemoryContributionConsent(textConsent: Boolean? = null, audioConsent: Boolean? = null) {
        val reading = state.value.savedMemoryStories ?: return
        val community = reading.community ?: return
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = community.copy(
            contributionConsent = textConsent ?: community.contributionConsent,
            audioConsent = audioConsent ?: community.audioConsent)))
    }

    fun updateMemoryContributionLanguage(language: String) {
        if (language !in setOf("zh", "en", "mixed")) return
        val reading = state.value.savedMemoryStories ?: return
        val community = reading.community ?: return
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = community.copy(contributionLanguage = language)))
    }

    fun loadMemoryContribution(contributionId: String) {
        val current = state.value.savedMemoryStories?.community ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            before.audio?.close()
            val item = repository.contribution(current.storyId, contributionId)
            if (!valid()) return@launchMemoryCommunity before
            before.copy(selectedContribution = item, audio = null)
        }
    }

    fun playMemoryContributionAudio() {
        val current = state.value.savedMemoryStories?.community ?: return
        val item = current.selectedContribution?.receipt?.contribution ?: return
        if (item.kind != "audio") return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            before.audio?.close()
            val audio = repository.contributionAudio(current.storyId, item.id)
            if (!valid()) { audio.close(); return@launchMemoryCommunity before }
            before.copy(audio = audio)
        }
    }

    fun reviewMemoryContribution(accepted: Boolean) {
        val reading = state.value.savedMemoryStories ?: return
        val community = reading.community ?: return
        val story = reading.detail ?: return
        val receipt = community.selectedContribution?.receipt ?: return
        if (!receipt.canReview || receipt.contribution.state != "pending") return
        launchMemoryCommunity(community.storyId) { repository, before, valid ->
            repository.reviewContribution(community.storyId, receipt.contribution.id, accepted, story.revision)
            if (!valid()) return@launchMemoryCommunity before
            val detail = repository.contribution(community.storyId, receipt.contribution.id)
            if (!valid()) return@launchMemoryCommunity before
            val page = repository.contributions(community.storyId, before.contributions?.page ?: 1)
            before.copy(selectedContribution = detail, contributions = page)
        }
    }

    fun submitMemoryText(text: String, language: String, byline: String, consent: Boolean) {
        val reading = state.value.savedMemoryStories ?: return
        val current = reading.community ?: return
        val story = reading.detail ?: return
        if (current.pendingText != null) return
        val request = MemoryContributionRequest("text", text, language,
            if (current.chatTurnContributionSeeded) "" else byline, consent,
            if (current.chatTurnContributionSeeded || current.contributionWholeStory) null else story.chapters.getOrNull(reading.selectedChapter)?.id, story.revision)
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = current.copy(pendingText = request)))
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val receipt = repository.submitText(current.storyId, request)
            if (!valid()) return@launchMemoryCommunity before
            val page = repository.contributions(current.storyId, 1)
            if (!valid()) return@launchMemoryCommunity before
            before.copy(pendingText = null, contributionDraft = if (before.contributionDraft == text) "" else before.contributionDraft,
                chatTurnContributionSeeded = if (before.contributionDraft == text) false else before.chatTurnContributionSeeded,
                contributions = page,
                selectedContribution = MemoryContributionDetail(receipt, null))
        }
    }

    fun retryMemoryText() {
        val current = state.value.savedMemoryStories?.community ?: return
        val request = current.pendingText ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val receipt = repository.submitText(current.storyId, request)
            if (!valid()) return@launchMemoryCommunity before
            val page = repository.contributions(current.storyId, 1)
            if (!valid()) return@launchMemoryCommunity before
            before.copy(pendingText = null, contributionDraft = if (before.contributionDraft == request.text) "" else before.contributionDraft,
                chatTurnContributionSeeded = if (before.contributionDraft == request.text) false else before.chatTurnContributionSeeded,
                contributions = page,
                selectedContribution = MemoryContributionDetail(receipt, null))
        }
    }

    fun updateMemoryContributionWholeStory(wholeStory: Boolean) {
        if (!allowed()) return
        val reading = state.value.savedMemoryStories ?: return
        val current = reading.community ?: return
        if (current.busy || current.contributionAudioBusy || current.chatTurnContributionSeeded ||
            current.pendingText != null || current.pendingAudio != null) return
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = current.copy(contributionWholeStory = wholeStory)))
    }

    fun submitMemoryAudio(wav: ByteArray, language: String, byline: String, consent: Boolean) {
        val reading = state.value.savedMemoryStories
        val current = reading?.community
        val story = reading?.detail
        if (current == null || story == null || current.pendingAudio != null) { wav.fill(0); return }
        val request = MemoryContributionRequest("audio", "", language, byline, consent,
            if (current.contributionWholeStory) null else story.chapters.getOrNull(reading.selectedChapter)?.id, story.revision)
        communityPendingAudio?.fill(0); communityPendingAudio = wav.copyOf(); wav.fill(0)
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = current.copy(pendingAudio = request)))
        retryMemoryAudio()
    }

    fun retryMemoryAudio() {
        val current = state.value.savedMemoryStories?.community ?: return
        val request = current.pendingAudio ?: return
        if (current.busy) return
        val held = communityPendingAudio?.copyOf() ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            try {
                val receipt = repository.submitAudio(current.storyId, request, held)
                if (!valid()) return@launchMemoryCommunity before
                val page = repository.contributions(current.storyId, 1)
                if (!valid()) return@launchMemoryCommunity before
                communityPendingAudio?.fill(0); communityPendingAudio = null
                return@launchMemoryCommunity before.copy(pendingAudio = null, contributions = page,
                    selectedContribution = MemoryContributionDetail(receipt, null))
            } finally { held.fill(0) }
        }
    }

    fun startMemoryConversation() {
        val current = state.value.savedMemoryStories?.community ?: return
        if (!canChangeMemoryStoryThread(current)) return
        if (current.pendingConversation == null) {
            val request = MemoryConversationRequest(targetType = "story", targetId = current.storyId)
            val drafts = current.conversationId?.let { rememberThreadDraft(current.threadDrafts, it, current.chatDraft, current.conversations) }
                ?: current.threadDrafts
            val draft = if (current.conversationId == null) current.chatDraft else ""
            mutable.value = state.value.copy(savedMemoryStories = state.value.savedMemoryStories?.copy(
                community = current.copy(pendingConversation = request, threadDrafts = drafts, chatDraft = draft)))
        }
        retryStartMemoryConversation()
    }

    fun retryStartMemoryConversation() {
        val current = state.value.savedMemoryStories?.community ?: return
        val request = current.pendingConversation ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val conversation = repository.startConversation(request)
            if (!valid()) return@launchMemoryCommunity before
            val turns = repository.turns(conversation.id, 1, replyContext = true)
            if (!valid()) return@launchMemoryCommunity before
            val conversations = repository.conversations("story", current.storyId, withPreview = true, currentRequest = valid)
            if (!valid()) return@launchMemoryCommunity before
            val revision = state.value.savedMemoryStories?.detail?.revision ?: return@launchMemoryCommunity before
            val job = recoverPendingChatJob(repository, turns, revision, valid)
            val drafts = before.threadDrafts
            val newDraft = if (before.conversationId == null) before.chatDraft else drafts[conversation.id].orEmpty()
            val boundedDrafts = rememberThreadDraft(drafts, conversation.id, newDraft, conversations)
            before.copy(conversations = conversations, conversationId = conversation.id, turns = turns, job = job,
                threadDrafts = boundedDrafts, chatDraft = newDraft, pendingConversation = null)
        }
    }

    fun selectMemoryConversation(conversationId: String) {
        val current = state.value.savedMemoryStories?.community ?: return
        if (!canChangeMemoryStoryThread(current)) return
        if (current.conversations?.items?.any { it.id == conversationId } != true) return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val turns = repository.turns(conversationId, 1, replyContext = true)
            if (!valid()) return@launchMemoryCommunity before
            val revision = state.value.savedMemoryStories?.detail?.revision ?: return@launchMemoryCommunity before
            val job = recoverPendingChatJob(repository, turns, revision, valid)
            if (!valid()) return@launchMemoryCommunity before
            val drafts = rememberThreadDraft(before.threadDrafts, before.conversationId, before.chatDraft, before.conversations)
            before.copy(conversationId = conversationId, turns = turns, job = job, pendingTurn = null,
                threadDrafts = drafts, chatDraft = drafts[conversationId].orEmpty())
        }
    }

    fun loadMemoryTurnsPage(pageNumber: Int) {
        if (pageNumber !in 1..8) return
        val current = state.value.savedMemoryStories?.community ?: return
        val conversationId = current.conversationId ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val turns = repository.turns(conversationId, pageNumber, replyContext = true)
            if (!valid()) return@launchMemoryCommunity before
            before.copy(turns = turns)
        }
    }

    fun updateMemoryChatDraft(text: String): Boolean {
        val reading = state.value.savedMemoryStories ?: return false
        val current = reading.community ?: return false
        if (text.toByteArray(Charsets.UTF_8).size > 4096 || text.any { it == '\u0000' }) return false
        val drafts = current.conversationId?.let { rememberThreadDraft(current.threadDrafts, it, text, current.conversations) }
            ?: current.threadDrafts
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = current.copy(chatDraft = text, threadDrafts = drafts)))
        return true
    }

    fun chooseMemoryChatFollowup(
        accountId: String, generation: Long, library: String, readerScopeId: Long,
        storyId: String, storyRevision: Long, conversationId: String, page: Int,
        turnId: String, question: String,
    ): MemoryChatFollowupResult {
        val live = state.value
        val reading = live.savedMemoryStories ?: return MemoryChatFollowupResult.STALE
        val story = reading.detail ?: return MemoryChatFollowupResult.STALE
        val chat = reading.community ?: return MemoryChatFollowupResult.STALE
        val turns = chat.turns ?: return MemoryChatFollowupResult.STALE
        if (live.session?.account_id != accountId || live.generation != generation || live.library != library ||
            reading.library != library || story.id != storyId || story.revision != storyRevision ||
            chat.storyId != storyId || chat.readerScopeId != readerScopeId || chat.conversationId != conversationId ||
            turns.conversationId != conversationId || turns.page != page ||
            !memoryCommunityAvailable || memoryCommunity == null || !allowed()) return MemoryChatFollowupResult.STALE
        val turn = turns.items.firstOrNull { it.id == turnId } ?: return MemoryChatFollowupResult.STALE
        val context = memoryReplyContext(turn, chat.job, storyRevision)
        if (turn.state != "ready" || context?.questions?.contains(question) != true)
            return MemoryChatFollowupResult.STALE
        if (live.busy || reading.busy || reading.detailBusy || chat.busy || chat.pendingText != null ||
            chat.pendingAudio != null || chat.pendingConversation != null || chat.pendingTurn != null ||
            chat.pendingNarrative != null || chat.contributionAudioBusy || conversationJobActive(chat.job, chat.turns) ||
            dictationHasUnfinishedInput(chat.dictation) || chat.chatDraft.isNotBlank()) return MemoryChatFollowupResult.BLOCKED
        val drafts = rememberThreadDraft(chat.threadDrafts, conversationId, question, chat.conversations)
        val nextFocus = nextRequestId(chat.chatDraftFocusRequestId)
        mutable.value = live.copy(savedMemoryStories = reading.copy(community = chat.copy(
            chatDraft = question, threadDrafts = drafts, chatDraftFocusRequestId = nextFocus)))
        return MemoryChatFollowupResult.SELECTED
    }

    private fun canChangeMemoryStoryThread(chat: MemoryCommunityStoryState): Boolean =
        !chat.busy && chat.pendingTurn == null && chat.pendingConversation == null &&
            !conversationJobActive(chat.job, chat.turns) && !dictationHasUnfinishedInput(chat.dictation)

    fun sendMemoryChat() {
        val current = state.value.savedMemoryStories?.community ?: return
        if (current.busy || (current.conversationId != null && current.turns == null) || current.pendingTurn != null || conversationJobActive(current.job, current.turns) ||
            dictationHasUnfinishedInput(current.dictation)) return
        if (current.conversationId == null) { startMemoryConversation(); return }
        if (current.chatDraft.isBlank()) return
        val conversationId = current.conversationId
        val request = MemoryTurnRequest(state.value.savedMemoryStories?.detail?.revision ?: return, current.chatDraft)
        val remainingDraft = ""
        val drafts = rememberThreadDraft(current.threadDrafts, conversationId, remainingDraft, current.conversations)
        mutable.value = state.value.copy(savedMemoryStories = state.value.savedMemoryStories?.copy(
            community = current.copy(pendingTurn = request, chatDraft = remainingDraft, threadDrafts = drafts)))
        retryMemoryChatTurn()
    }

    fun retryMemoryChatTurn() {
        val current = state.value.savedMemoryStories?.community ?: return
        val conversation = current.conversationId ?: return
        val request = current.pendingTurn ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val job = repository.sendTurn(conversation, request)
            if (!valid()) return@launchMemoryCommunity before
            val turns = repository.turns(conversation, 1, replyContext = true)
            if (!valid()) return@launchMemoryCommunity before
            before.copy(job = job, pendingTurn = null, turns = turns)
        }
    }

    fun refreshMemoryChat() {
        val current = state.value.savedMemoryStories?.community ?: return
        val conversation = current.conversationId ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val turns = repository.turns(conversation, before.turns?.page ?: 1, replyContext = true)
            if (!valid()) return@launchMemoryCommunity before
            val revision = state.value.savedMemoryStories?.detail?.revision ?: return@launchMemoryCommunity before
            val pendingRows = turns.items.filter { it.state in setOf("queued", "running") && it.jobId != null }
            val pendingJob = recoverPendingChatJob(repository, turns, revision, valid)
            val updatedJob = when {
                pendingRows.size == 1 -> pendingJob ?: before.job?.takeIf {
                    it.id == pendingRows.single().jobId && it.kind == "chat" && it.baseRevision == revision
                }
                pendingRows.isNotEmpty() -> null
                else -> before.job?.takeIf { it.kind == "chat" && it.baseRevision == revision }
                    ?.let { fetchBoundChatJob(repository, it.id, revision, valid) ?: it }
            }
            if (!valid()) return@launchMemoryCommunity before
            before.copy(job = updatedJob, turns = turns)
        }
    }

    fun requestMemoryNarrative(instructions: String) {
        val reading = state.value.savedMemoryStories ?: return
        val current = reading.community ?: return
        val story = reading.detail?.takeIf { it.canEdit } ?: return
        if (current.pendingNarrative != null) return
        val request = MemoryNarrativeRequest("story", current.storyId, story.revision, instructions)
        mutable.value = state.value.copy(savedMemoryStories = state.value.savedMemoryStories?.copy(
            community = current.copy(pendingNarrative = request)))
        retryMemoryNarrative()
    }

    fun retryMemoryNarrative() {
        val reading = state.value.savedMemoryStories ?: return
        if (reading.detail?.canEdit != true) return
        val current = reading.community ?: return
        val request = current.pendingNarrative ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val job = repository.queueNarrative(request)
            if (!valid()) return@launchMemoryCommunity before
            before.copy(pendingNarrative = null, narrativeJob = job)
        }
    }

    fun refreshMemoryNarrative() {
        val current = state.value.savedMemoryStories?.community ?: return
        val job = current.narrativeJob ?: return
        launchMemoryCommunity(current.storyId) { repository, before, valid ->
            val updated = repository.job(job.id)
            if (!valid()) return@launchMemoryCommunity before
            before.copy(narrativeJob = updated)
        }
    }

    fun memoryCommunityDictation(): MemoryDictationStore? {
        if (!api.assistantEnabled || !memoryCommunityAvailable) return null
        val reading = state.value.savedMemoryStories ?: return null
        val current = reading.community ?: return null
        val existing = current.dictation
        if (existing != null) return existing
        val expectedToken = token ?: return null
        val library = reading.library; val storyId = current.storyId; val generation = state.value.generation
        val epoch = communityEpoch
        fun check() {
            if (!communityCurrent(storyId, expectedToken, library, generation, epoch)) throw CancellationException("Memory scope changed")
        }
        val dictation = MemoryDictationStore(scope, capabilities = {
            check(); val result = api.assistantCapabilities(expectedToken, library); check(); result
        }, transcribe = { wav, requestId ->
            check(); val result = api.assistantTranscribe(expectedToken, library, wav, requestId); check(); result
        }, onDenied = ::memoryCommunityDenied, now = now)
        mutable.value = state.value.copy(savedMemoryStories = reading.copy(community = current.copy(dictation = dictation)))
        return dictation
    }
    fun editStory(storyId: String? = null) {
        if (!api.protectedNativeV2Enabled || !allowed() || state.value.busy || coolingDown() ||
            state.value.storyEditor != null || state.value.viewingOriginal || state.value.video != null) return
        val reading = state.value.stories?.takeIf { !it.busy }?.result ?: return
        val detail = state.value.detail ?: return
        if (reading.assetId != detail.asset.id || reading.libraryId != state.value.library) return
        val initial = if (storyId == null) null else reading.items.firstOrNull { it.id == storyId && it.canEdit } ?: return
        if (initial == null && !reading.canCreate) return
        val generation = state.value.generation
        val credential = token!!; val authorizedSession = identity!!
        val library = state.value.library!!; val assetId = detail.asset.id
        lateinit var editor: ProtectedStoryEditorStore
        fun checkScope() {
            if (!active(generation) || !allowed() || state.value.library != library || token !== credential ||
                state.value.detail?.asset?.id != assetId || state.value.storyEditor !== editor)
                throw CancellationException("Story editor closed")
        }
        fun deny() {
            if (active(generation)) {
                invalidate(keepIdentity = true, cover = true)
                mutable.value = state.value.copy(problem = LiveProblem(Message.ACCESS_DENIED))
                retry = { foreground() }
            }
        }
        val dictation = if (api.assistantEnabled) MemoryDictationStore(scope,
            capabilities = {
                checkScope()
                val result = api.assistantCapabilities(credential, library)
                checkScope(); result
            },
            transcribe = { wav, requestId ->
                checkScope()
                val result = api.assistantTranscribe(credential, library, wav, requestId)
                checkScope(); result
            }, onDenied = ::deny, now = now) else null
        editor = ProtectedStoryEditorStore(scope, assetId, initial,
            save = { mutation ->
                checkScope()
                val result = api.saveStory(credential, library, mutation)
                checkScope()
                validResponse(result.assetId == assetId && (mutation.storyId == null || result.id == mutation.storyId))
                result
            },
            reload = {
                checkScope()
                val result = initial?.let { api.currentStory(credential, library, assetId, it.id) }
                checkScope(); result
            },
            onSaved = { _ ->
                if (active(generation)) {
                    // Show the server's current revision, including an exact retry whose result was edited later.
                    // The dialog displays the returned story; refresh page metadata after closing.
                    mutable.value = state.value.copy(stories = null)
                }
            },
            onDenied = ::deny, now = now, dictation = dictation,
            defaultByline = authorizedSession.displayName)
        mutable.value = state.value.copy(storyEditor = editor)
    }
    fun closeStoryEditor() {
        state.value.storyEditor?.close()
        mutable.value = state.value.copy(storyEditor = null)
        loadStories(1)
    }
    /** Incoming contribution is account scoped and never grants library visibility. */
    fun openUpload(): UploadStore? {
        if (!api.uploadEnabled || !api.protectedNativeV2Enabled || !usable() || state.value.busy ||
            identity?.memberships?.none { it.available } != false) return null
        state.value.upload?.let { return it }
        val generation = state.value.generation
        val account = identity?.account_id
        val destinationLibraryId = state.value.library?.takeIf { library ->
            identity?.memberships?.any { it.library_id == library && it.available } == true
        }
        val upload = UploadStore(api, token!!, scope, valid = {
            active(generation) && !state.value.covered && identity?.account_id == account &&
                identity?.memberships?.any { it.available } == true
        }, network = uploadNetwork, now = now, onDenied = {
            invalidate(keepIdentity = false)
            mutable.value = state.value.copy(problem = LiveProblem(Message.ACCESS_DENIED))
        }, destinationLibraryId = destinationLibraryId,
            destinationAllowed = { library ->
                active(generation) && !state.value.covered && identity?.account_id == account &&
                    identity?.memberships?.any { it.library_id == library && it.available } == true
            })
        mutable.value = state.value.copy(upload = upload)
        return upload
    }

    fun loadUploadHistory(page: Int = 1) {
        if (!api.uploadEnabled || !api.protectedNativeV2Enabled || !usable() || state.value.busy ||
            page !in 1..100000 || state.value.uploadHistory?.busy == true) return
        val credential = token!!
        val request = ++uploadHistoryRequest
        mutable.value = state.value.copy(uploadHistory = UploadHistoryState(page = page, busy = true))
        launch { generation ->
            try {
                val result = api.uploadHistory(credential, page)
                if (!active(generation) || request != uploadHistoryRequest) return@launch
                mutable.value = state.value.copy(uploadHistory = UploadHistoryState(result.page, result.total, result.items))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation) || request != uploadHistoryRequest) return@launch
                if (e is ApiFailure && e.status == 401) {
                    readFailure(e, generation, credential) { background(); foreground() }
                } else if (e is ApiFailure && e.status in listOf(403, 404, 503)) {
                    mutable.value = state.value.copy(uploadHistory = UploadHistoryState(page = page, busy = false, unavailable = true))
                } else {
                    mutable.value = state.value.copy(uploadHistory = UploadHistoryState(page = page, unavailable = true), problem = problem(e))
                }
            }
        }
    }

    fun openUploadHistory(item: UploadHistoryItem) {
        if (item.state != "available" || item.libraryId == null || !usable() ||
            state.value.uploadHistory?.items?.any { it == item } != true ||
            identity?.memberships?.any { it.library_id == item.libraryId && it.available } != true) return
        val target = item.libraryId
        if (state.value.library == target) { openAssetById(item.assetId); return }
        selectLibrary(target) { openAssetById(item.assetId) }
    }
    fun closeUploadHistory() { uploadHistoryRequest++; mutable.value = state.value.copy(uploadHistory = null) }
    fun saveUploadTextAnnotation(library: String, batch: String, assetId: String, language: String, consent: String, text: String) {
        val previous = state.value.uploadAnnotationWrite
        val stableMutation = previous?.takeIf { it.library == library && it.request.batch == batch && it.request.assetId == assetId &&
            it.request.language == language && it.request.consent == consent && it.request.text == text }?.request?.mutationId
        val request = UploadTextAnnotationRequest(batch, assetId, language, consent,
            stableMutation ?: java.util.UUID.randomUUID().toString(), text)
        postUploadTextAnnotation(library, request)
    }
    fun retryUploadTextAnnotation() {
        val previous = state.value.uploadAnnotationWrite ?: return
        if (!previous.busy && previous.result == null && previous.failure != null) postUploadTextAnnotation(previous.library, previous.request)
    }
    fun saveUploadAudioAnnotation(library: String, batch: String, assetId: String,
                                  language: String, consent: String, wav: ByteArray) {
        val previous = state.value.uploadAudioAnnotationWrite
        val stableMutation = previous?.takeIf { it.library == library && it.request.batch == batch &&
            it.request.assetId == assetId && it.request.language == language && it.request.consent == consent &&
            it.request.wav.contentEquals(wav) }?.request?.mutationId
        val request = UploadAudioAnnotationRequest(batch, assetId, language, consent,
            stableMutation ?: java.util.UUID.randomUUID().toString(), wav.copyOf())
        postUploadAudioAnnotation(library, request)
    }
    fun retryUploadAudioAnnotation() {
        val previous = state.value.uploadAudioAnnotationWrite ?: return
        if (!previous.busy && previous.result == null && previous.failure != null)
            postUploadAudioAnnotation(previous.library, previous.request)
    }
    private fun postUploadAudioAnnotation(library: String, request: UploadAudioAnnotationRequest) {
        if (!api.uploadEnabled || !api.protectedNativeV2Enabled || !usable() || state.value.busy ||
            identity?.memberships?.none { it.library_id == library && it.available } != false) return
        try { UploadAnnotationsWire.audioInfo(request) }
        catch (_: IllegalArgumentException) {
            mutable.value = state.value.copy(uploadAudioAnnotationWrite = UploadAudioAnnotationWriteState(
                library, request, failure = ApiFailure(FailureKind.INVALID_INPUT)))
            return
        }
        val credential = token!!; val generation = state.value.generation
        mutable.value = state.value.copy(uploadAudioAnnotationWrite = UploadAudioAnnotationWriteState(library, request, busy = true))
        val job = scope.launch {
            try {
                val result = api.postUploadAudioAnnotation(credential, library, request)
                if (!active(generation)) return@launch
                mutable.value = state.value.copy(uploadAudioAnnotationWrite = UploadAudioAnnotationWriteState(library, request, result = result))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation)) return@launch
                val failure = (e as? ApiFailure) ?: ApiFailure(FailureKind.INVALID_RESPONSE)
                if (failure.status == 401) readFailure(failure, generation, credential) { background(); foreground() }
                else mutable.value = state.value.copy(uploadAudioAnnotationWrite = UploadAudioAnnotationWriteState(library, request, failure = failure))
            }
        }
        requests += job; job.invokeOnCompletion { requests.remove(job) }
    }
    private fun postUploadTextAnnotation(library: String, request: UploadTextAnnotationRequest) {
        if (!api.uploadEnabled || !api.protectedNativeV2Enabled || !usable() || state.value.busy ||
            identity?.memberships?.none { it.library_id == library && it.available } != false) return
        val credential = token!!
        val generation = state.value.generation
        mutable.value = state.value.copy(uploadAnnotationWrite = UploadAnnotationWriteState(library, request, busy = true))
        val job = scope.launch {
            try {
                val result = api.postUploadTextAnnotation(credential, library, request)
                if (!active(generation)) return@launch
                mutable.value = state.value.copy(uploadAnnotationWrite = UploadAnnotationWriteState(library, request, result = result))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation)) return@launch
                val failure = (e as? ApiFailure) ?: ApiFailure(FailureKind.INVALID_RESPONSE)
                if (failure.status == 401) readFailure(failure, generation, credential) { background(); foreground() }
                else mutable.value = state.value.copy(uploadAnnotationWrite = UploadAnnotationWriteState(library, request, failure = failure))
            }
        }
        requests += job; job.invokeOnCompletion { requests.remove(job) }
    }
    fun loadUploadAnnotations(library: String, assetId: String, page: Int = 1) {
        if (!api.uploadEnabled || !api.protectedNativeV2Enabled || !usable() || state.value.busy || page !in 1..100000 ||
            identity?.memberships?.none { it.library_id == library && it.available } != false ||
            !assetId.matches(Regex("[1-9][0-9]{0,18}")) || assetId.toLongOrNull() == null) return
        val credential = token!!; val generation = state.value.generation
        mutable.value = state.value.copy(uploadAnnotationRead = UploadAnnotationReadState(library, assetId, page, busy = true))
        val job = scope.launch {
            try {
                val result = api.uploadAnnotations(credential, library, assetId, page)
                if (!active(generation)) return@launch
                mutable.value = state.value.copy(uploadAnnotationRead = UploadAnnotationReadState(library, assetId, page, result))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation)) return@launch
                val failure = (e as? ApiFailure) ?: ApiFailure(FailureKind.INVALID_RESPONSE)
                if (failure.status == 401) readFailure(failure, generation, credential) { background(); foreground() }
                else mutable.value = state.value.copy(uploadAnnotationRead = UploadAnnotationReadState(library, assetId, page, failure = failure))
            }
        }
        requests += job; job.invokeOnCompletion { requests.remove(job) }
    }
    fun clearUploadAnnotationRead() { mutable.value = state.value.copy(uploadAnnotationRead = null) }
    fun clearUploadAnnotationWrite() { mutable.value = state.value.copy(uploadAnnotationWrite = null) }
    fun clearUploadAudioAnnotationWrite() { mutable.value = state.value.copy(uploadAudioAnnotationWrite = null) }
    fun loadUploadAnnotationAudio(library: String, annotation: UploadAnnotation) {
        if (!api.uploadEnabled || !api.protectedNativeV2Enabled || !usable() || annotation.kind != "audio" ||
            annotation.libraryId != library || identity?.memberships?.none { it.library_id == library && it.available } != false)
            return
        val readHasAnnotation = state.value.uploadAnnotationRead?.let { read ->
            read.library == library && read.result?.items?.any { it == annotation } == true
        } == true
        val writtenHere = state.value.uploadAudioAnnotationWrite?.let { write ->
            write.library == library && write.result == annotation
        } == true
        if (!readHasAnnotation && !writtenHere) return

        clearUploadAnnotationAudio()
        val request = ++uploadAnnotationAudioRequest
        val credential = token ?: return
        val generation = state.value.generation
        mutable.value = state.value.copy(uploadAnnotationAudio = UploadAnnotationAudioState(
            library, annotation.id, annotation.assetId, busy = true))
        val job = scope.launch {
            var bytes: ByteArray? = null
            try {
                bytes = api.uploadAnnotationAudio(credential, library, annotation)
                if (!active(generation) || request != uploadAnnotationAudioRequest) {
                    bytes.fill(0)
                    return@launch
                }
                val audio = ProtectedAnnotationAudio(bytes)
                bytes = null
                mutable.value = state.value.copy(uploadAnnotationAudio = UploadAnnotationAudioState(
                    library, annotation.id, annotation.assetId, audio = audio))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                bytes?.fill(0)
                if (!active(generation) || request != uploadAnnotationAudioRequest) return@launch
                val failure = (e as? ApiFailure) ?: ApiFailure(FailureKind.INVALID_RESPONSE)
                if (failure.status == 401) readFailure(failure, generation, credential) { }
                else mutable.value = state.value.copy(uploadAnnotationAudio = UploadAnnotationAudioState(
                    library, annotation.id, annotation.assetId, failure = failure))
            } finally {
                bytes?.fill(0)
            }
        }
        uploadAnnotationAudioJob = job
        requests += job
        job.invokeOnCompletion {
            requests.remove(job)
            if (uploadAnnotationAudioJob === job) uploadAnnotationAudioJob = null
        }
    }
    fun clearUploadAnnotationAudio() {
        uploadAnnotationAudioRequest++
        uploadAnnotationAudioJob?.cancel()
        uploadAnnotationAudioJob = null
        state.value.uploadAnnotationAudio?.audio?.close()
        mutable.value = state.value.copy(uploadAnnotationAudio = null)
    }
    fun closeUpload() {
        state.value.upload?.close()
        mutable.value = state.value.copy(upload = null)
    }
    fun libraries() { if (usable()) { playbackProgress.clear(); invalidate(keepIdentity = true); mutable.value = state.value.copy(assistant = null) } }
    fun selectLibrary(library: String, afterLoaded: (() -> Unit)? = null) {
        val previousLibrary = state.value.library
        if (previousLibrary != null && previousLibrary != library) playbackProgress.clear()
        if (!usable() || coolingDown()) return
        invalidate(keepIdentity = true)
        if (identity?.memberships?.none { it.library_id == library && it.available } != false) {
            mutable.value = state.value.copy(assistant = null, problem = LiveProblem(Message.ACCESS_DENIED)); return
        }
        mutable.value = state.value.copy(library = library, assistant = if (previousLibrary == library) state.value.assistant else null)
        loadPage(1, GalleryMedia.ALL, afterLoaded)
    }
    fun selectMedia(media: GalleryMedia) {
        if (!mediaFilterEnabled || media == GalleryMedia.PREPARED_VIDEOS && !preparedBrowseEnabled) return
        loadPage(1, media)
    }
    /** Capability probing is protected and scoped to the selected available library. */
    fun loadAssistantCapabilities() {
        if (!api.assistantEnabled || !allowed() || coolingDown()) return
        val library = state.value.library!!; val credential = token!!; val generation = state.value.generation
        val existing = state.value.assistant?.takeIf { it.library == library && it.generation == generation }
        if (existing?.loadingCapabilities == true || existing?.capabilities != null) return
        mutable.value = state.value.copy(assistant = (existing ?: AssistantClientState(library, generation)).copy(
            loadingCapabilities = true, failure = null))
        launch { activeGeneration ->
            try {
                val capabilities = api.assistantCapabilities(credential, library)
                if (!active(activeGeneration) || state.value.library != library) return@launch
                mutable.value = state.value.copy(assistant = (state.value.assistant ?: AssistantClientState(library, generation)).copy(
                    capabilities = capabilities, loadingCapabilities = false, failure = null))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(activeGeneration) || state.value.library != library) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, activeGeneration, credential) { loadAssistantCapabilities() }
                else mutable.value = state.value.copy(assistant = (state.value.assistant ?: AssistantClientState(library, generation)).copy(
                    loadingCapabilities = false, failure = problem(e)))
            }
        }
    }
    fun clearAssistant() {
        val current = state.value.assistant ?: return
        if (current.library != state.value.library || current.generation != state.value.generation) return
        current.speechAudio?.close()
        assistantSpeechRequest++
        assistantTurnRequest++
        assistantTranscriptRequest++
        mutable.value = state.value.copy(assistant = current.copy(turns = emptyList(), context = null, failure = null, busy = false,
            speechAudio = null, speechBusy = false, transcribing = false, transcript = null, lastRequestReceipt = null, receiptDetail = null,
            receiptChecking = false, receiptCheckFailed = false, confirmedTranscriptRequestId = null, pendingTurn = null))
    }
    fun clearAssistantSpeech() {
        val current = state.value.assistant ?: return
        if (current.library != state.value.library || current.generation != state.value.generation) return
        current.speechAudio?.close()
        assistantSpeechRequest++
        mutable.value = state.value.copy(assistant = current.copy(speechAudio = null, speechBusy = false))
    }
    fun loadAssistantSpeech(language: String) {
        val current = state.value.assistant ?: return
        val latest = current.turns.lastOrNull()?.turn
        if (!api.assistantEnabled || current.library != state.value.library || current.generation != state.value.generation ||
            current.capabilities?.let { it.enabled && it.speech } != true || current.speechBusy || current.context == null ||
            latest?.kind != "results" || latest.items.isEmpty() || language !in setOf("zh", "en") || !allowed() || coolingDown()) return
        val library = current.library; val generation = current.generation; val credential = token!!; val context = current.context
        val parentId = current.turns.lastOrNull()?.turn?.receipt?.takeIf { it.tracking == "enabled" && it.status == "succeeded" }?.requestId
        val requestId = java.util.UUID.randomUUID().toString()
        val request = ++assistantSpeechRequest
        current.speechAudio?.close()
        mutable.value = state.value.copy(assistant = current.copy(speechBusy = true, speechAudio = null, lastRequestReceipt = AssistantRequestReceipt(requestId, "unknown", null), receiptDetail = null, receiptChecking = false, receiptCheckFailed = false, failure = null))
        launch { activeGeneration ->
            var bytes: ByteArray? = null
            try {
                val speech = api.assistantSpeech(credential, library, context, language, requestId, parentId)
                bytes = speech.bytes
                val received = speech.bytes
                if (!active(activeGeneration) || generation != activeGeneration || state.value.library != library || request != assistantSpeechRequest) { received.fill(0); return@launch }
                val latestState = state.value.assistant?.takeIf { it.library == library && it.generation == generation } ?: run { received.fill(0); return@launch }
                val audio = ProtectedAnnotationAudio(received); bytes = null
                mutable.value = state.value.copy(assistant = latestState.copy(speechBusy = false, speechAudio = audio, lastRequestReceipt = speech.receipt, failure = null))
                if (speech.receipt.tracking == "enabled" && speech.receipt.status == "succeeded") reportAssistantOutcome(library, generation, credential, requestId, "displayed")
            } catch (e: CancellationException) { bytes?.fill(0); throw e }
            catch (e: Exception) {
                bytes?.fill(0)
                if (!active(activeGeneration) || state.value.library != library || request != assistantSpeechRequest) return@launch
                val latestState = state.value.assistant?.takeIf { it.library == library && it.generation == generation } ?: return@launch
                mutable.value = state.value.copy(assistant = latestState.copy(speechBusy = false, lastRequestReceipt = AssistantRequestReceipt(requestId, "unknown", null), failure = problem(e)))
            }
        }
    }
    fun clearAssistantTranscript() {
        val current = state.value.assistant ?: return
        if (current.library == state.value.library && current.generation == state.value.generation)
            mutable.value = state.value.copy(assistant = current.copy(transcript = null, confirmedTranscriptRequestId = null,
                lastRequestReceipt = current.lastRequestReceipt?.takeUnless { it.requestId == current.transcript?.receipt?.requestId },
                receiptDetail = current.receiptDetail?.takeUnless { it.requestId == current.transcript?.receipt?.requestId }, failure = null))
    }
    fun checkAssistantReceipt() {
        val current = state.value.assistant ?: return
        val receipt = current.lastRequestReceipt ?: return
        if (!api.assistantEnabled || current.library != state.value.library || current.generation != state.value.generation || current.receiptChecking || receipt.tracking == "disabled" || !allowed()) return
        val credential = token ?: return; val library = current.library; val generation = current.generation
        mutable.value = state.value.copy(assistant = current.copy(receiptChecking = true, receiptCheckFailed = false))
        launch { activeGeneration ->
            try {
                if (!active(activeGeneration) || generation != activeGeneration || state.value.library != library || token !== credential) return@launch
                val detail = api.assistantReceipt(credential, library, receipt.requestId)
                if (!active(activeGeneration) || generation != activeGeneration || state.value.library != library) return@launch
                val latest = state.value.assistant?.takeIf { it.library == library && it.generation == generation && it.lastRequestReceipt?.requestId == receipt.requestId } ?: return@launch
                mutable.value = state.value.copy(assistant = latest.copy(receiptDetail = detail, lastRequestReceipt = AssistantRequestReceipt(detail.requestId, "enabled", detail.status), receiptChecking = false, receiptCheckFailed = false))
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) {
                if (!active(activeGeneration) || generation != activeGeneration || state.value.library != library) return@launch
                val latest = state.value.assistant?.takeIf { it.generation == generation && it.lastRequestReceipt?.requestId == receipt.requestId } ?: return@launch
                mutable.value = state.value.copy(assistant = latest.copy(receiptChecking = false, receiptCheckFailed = true))
            }
        }
    }
    fun reportAssistantOpenRequested(requestId: String?) {
        val current = state.value.assistant ?: return
        if (current.library != state.value.library || current.generation != state.value.generation) return
        if (!allowed()) return
        val receipt = current.turns.mapNotNull { it.turn.receipt }.firstOrNull { it.requestId == requestId && it.tracking == "enabled" && it.status == "succeeded" } ?: return
        val credential = token ?: return; val library = current.library; val generation = current.generation
        reportAssistantOutcome(library, generation, credential, receipt.requestId, "open_requested")
    }
    private fun reportAssistantOutcome(library: String, generation: Long, credential: Bearer, requestId: String, outcome: String) {
        scope.launch {
            val current = state.value.assistant
            if (state.value.generation == generation && state.value.library == library && !state.value.covered &&
                current?.library == library && current.generation == generation && token === credential)
                runCatching { api.assistantOutcome(credential, library, requestId, outcome) }
        }
    }
    fun transcribeAssistant(wav: ByteArray) {
        val current = state.value.assistant ?: return
        if (!api.assistantEnabled || current.library != state.value.library || current.generation != state.value.generation ||
            current.capabilities?.let { it.enabled && it.transcribe && it.maxAudioSeconds in 1..30 } != true ||
            current.transcribing || current.busy || current.pendingTurn != null || !allowed() || coolingDown()) return
        val library = current.library; val generation = current.generation; val credential = token!!
        val requestId = java.util.UUID.randomUUID().toString()
        if (wav.size !in 16046..(44 + 16_000 * 2 * 30) ||
            !wav.copyOfRange(0, 4).contentEquals("RIFF".toByteArray()) || !wav.copyOfRange(8, 12).contentEquals("WAVE".toByteArray())) return
        val request = ++assistantTranscriptRequest
        mutable.value = state.value.copy(assistant = current.copy(transcribing = true, transcript = null, lastRequestReceipt = AssistantRequestReceipt(requestId, "unknown", null), receiptDetail = null, receiptChecking = false, receiptCheckFailed = false, confirmedTranscriptRequestId = null, failure = null))
        launch { activeGeneration ->
            try {
                val result = api.assistantTranscribe(credential, library, wav, requestId)
                if (!active(activeGeneration) || generation != activeGeneration || state.value.library != library || request != assistantTranscriptRequest) return@launch
                val latest = state.value.assistant?.takeIf { it.library == library && it.generation == generation } ?: return@launch
                mutable.value = state.value.copy(assistant = latest.copy(transcribing = false, transcript = result, lastRequestReceipt = result.receipt ?: AssistantRequestReceipt(requestId, "unknown", null), confirmedTranscriptRequestId = result.receipt?.takeIf { it.tracking == "enabled" && it.status == "succeeded" }?.requestId, failure = null))
                result.receipt?.takeIf { it.tracking == "enabled" && it.status == "succeeded" }?.let { reportAssistantOutcome(library, generation, credential, requestId, "displayed") }
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(activeGeneration) || state.value.library != library || request != assistantTranscriptRequest) return@launch
                val latest = state.value.assistant?.takeIf { it.library == library && it.generation == generation } ?: return@launch
                mutable.value = state.value.copy(assistant = latest.copy(transcribing = false, lastRequestReceipt = AssistantRequestReceipt(requestId, "unknown", null), failure = problem(e)))
            }
        }
    }
    fun sendAssistantText(text: String): Boolean {
        val current = state.value.assistant ?: return false
        if (!api.assistantEnabled || current.library != state.value.library || current.generation != state.value.generation ||
            current.capabilities?.let { it.enabled && it.text } != true || current.busy || current.transcribing || current.pendingTurn != null || !allowed() || coolingDown()) return false
        val library = current.library; val generation = current.generation; val credential = token ?: return false; val context = current.context
        val requestId = java.util.UUID.randomUUID().toString()
        val parentId = current.confirmedTranscriptRequestId
        val pending = AssistantPendingTurn(identity?.account_id ?: return false, library, generation, text, context, parentId, requestId)
        val request = ++assistantTurnRequest
        // Validate before changing state so malformed text does not become a visible pending turn.
        try { AssistantWire.request(library, text, context) }
        catch (e: Exception) {
            mutable.value = state.value.copy(assistant = current.copy(failure = problem(e)))
            return false
        }
        current.speechAudio?.close()
        assistantSpeechRequest++
        mutable.value = state.value.copy(assistant = current.copy(busy = true, pendingTurn = pending, lastRequestReceipt = AssistantRequestReceipt(requestId, "unknown", null), receiptDetail = null, receiptChecking = false, receiptCheckFailed = false, confirmedTranscriptRequestId = null, failure = null, speechAudio = null, speechBusy = false))
        launch { activeGeneration ->
            try {
                val result = api.assistantTurn(credential, library, text, context, requestId, parentId)
                if (!active(activeGeneration) || generation != activeGeneration || state.value.library != library || request != assistantTurnRequest) return@launch
                val latest = state.value.assistant?.takeIf { it.library == library && it.generation == generation } ?: return@launch
                val updated = latest.copy(turns = (latest.turns + AssistantExchange(text, result)).takeLast(40),
                    context = result.context, busy = false, failure = null, pendingTurn = null,
                    transcript = null,
                    lastRequestReceipt = result.receipt ?: AssistantRequestReceipt(requestId, "unknown", null))
                mutable.value = state.value.copy(assistant = updated)
                result.receipt?.takeIf { it.tracking == "enabled" && it.status == "succeeded" }?.let { reportAssistantOutcome(library, generation, credential, requestId, "displayed") }
                result.items.forEach { loadAssistantPreview(library, generation, it) }
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(activeGeneration) || state.value.library != library || request != assistantTurnRequest) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) readFailure(e, activeGeneration, credential) { }
                else {
                    val latest = state.value.assistant?.takeIf { it.library == library && it.generation == generation } ?: return@launch
                    mutable.value = state.value.copy(assistant = latest.copy(busy = false, pendingTurn = pending, lastRequestReceipt = AssistantRequestReceipt(requestId, "unknown", null), failure = problem(e)))
                }
            }
        }
        return true
    }
    private fun loadAssistantPreview(library: String, generation: Long, asset: Asset) {
        if (!api.assistantEnabled || !PhoneDiscoveryWire.validLibrary(library) || !PhoneDiscoveryWire.validId(asset.id) ||
            state.value.library != library || state.value.generation != generation || state.value.previews.containsKey(asset.id) ||
            !allowed() || coolingDown()) return
        val credential = token ?: return
        launch { activeGeneration ->
            try {
                val bytes = api.thumbnail(credential, library, asset) ?: return@launch
                if (!active(activeGeneration) || generation != activeGeneration || state.value.library != library) { bytes.fill(0); return@launch }
                if (bytes.size > HttpsPhotoHouseApi.IMAGE_LIMIT) { bytes.fill(0); return@launch }
                val total = state.value.previews.values.sumOf { it.size }
                if (total + bytes.size > CACHE_LIMIT) { bytes.fill(0); return@launch }
                mutable.value = state.value.copy(previews = state.value.previews + (asset.id to bytes))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (e is ApiFailure && e.status in listOf(401, 403))
                    readFailure(e, generation, credential) { loadAssistantPreview(library, generation, asset) }
            }
        }
    }
    /** Protected family-authored note labels; this never uses the anonymous discovery catalog. */
    fun openFamilyTags(query: String = "", page: Int = 1) {
        if (!api.familyTagsEnabled || !allowed() || coolingDown() || !FamilyTagsWire.validQuery(query) || page !in 1..100000) return
        val library = state.value.library!!; val credential = token!!
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(library = library, busy = true, familyTags = FamilyTagsBrowsing(query, page, busy = true))
        launch { generation ->
            try {
                val result = api.familyTags(credential, library, page, query)
                if (!active(generation)) return@launch
                validResponse(result.libraryId == library && result.page == page && result.pageSize == FamilyTagsWire.PAGE_SIZE &&
                    result.total >= 0 && result.items.size <= result.pageSize && result.items.map { it.name }.distinct().size == result.items.size &&
                    result.items.all { FamilyTagsWire.validTag(it.name) && it.assetCount > 0 })
                mutable.value = state.value.copy(busy = false, familyTags = FamilyTagsBrowsing(query, page, result))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation)) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) {
                    readFailure(e, generation, credential) { openFamilyTags(query, page) }
                } else mutable.value = state.value.copy(busy = false,
                    familyTags = FamilyTagsBrowsing(query, page, problem = problem(e)))
            }
        }
    }
    fun openFamilyTag(tag: String, page: Int = 1) {
        val current = state.value.familyTags ?: return
        if (!api.familyTagsEnabled || !allowed() || coolingDown() || !FamilyTagsWire.validTag(tag) || page !in 1..100000) return
        val library = state.value.library!!; val credential = token!!
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(library = library, busy = true,
            familyTags = current.copy(selectedTag = tag, assetPage = page, busy = true, problem = null))
        launch { generation ->
            try {
                val result = api.familyTagAssets(credential, library, tag, page)
                if (!active(generation)) return@launch
                validResponse(result.library_id == library && result.page == page && result.page_size == FamilyTagsWire.PAGE_SIZE &&
                    result.total >= 0 && result.items.size <= result.page_size && result.items.map { it.id }.distinct().size == result.items.size)
                mutable.value = state.value.copy(gallery = result, busy = true)
                var byteCount = 0
                val images = mutableMapOf<String, ByteArray>()
                for (asset in result.items) {
                    val bytes = try { api.thumbnail(credential, library, asset) }
                    catch (e: ApiFailure) {
                        if (e.kind == FailureKind.OFFLINE || e.kind == FailureKind.HTTP && e.status in 502..504 && e.retryAfterMillis == 0L) null else throw e
                    }
                    if (!active(generation)) return@launch
                    if (bytes != null && bytes.size <= HttpsPhotoHouseApi.IMAGE_LIMIT && byteCount + bytes.size <= CACHE_LIMIT) {
                        images[asset.id] = bytes; byteCount += bytes.size
                        mutable.value = state.value.copy(previews = images.toMap())
                    }
                }
                if (active(generation)) mutable.value = state.value.copy(busy = false)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation)) return@launch
                if (e is ApiFailure && e.status in listOf(401, 403)) {
                    readFailure(e, generation, credential) { openFamilyTag(tag, page) }
                } else mutable.value = state.value.copy(gallery = null, previews = emptyMap(), busy = false,
                    familyTags = current.copy(selectedTag = tag, assetPage = page, busy = false, problem = problem(e)))
            }
        }
    }
    fun backToFamilyTags() {
        val current = state.value.familyTags ?: return
        if (current.selectedTag != null) openFamilyTags(current.query, current.page)
    }
    fun loadPage(page: Int = 1, media: GalleryMedia = state.value.media, afterLoaded: (() -> Unit)? = null) {
        if (!allowed() || coolingDown()) return
        require(page in 1..100000 && (media == GalleryMedia.ALL || mediaFilterEnabled))
        require(media != GalleryMedia.PREPARED_VIDEOS || preparedBrowseEnabled)
        val library = state.value.library!!; val credential = token!!
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(library = library, busy = true, media = media)
        launch { generation ->
            try {
                // The first gallery read can lose a freshly established connection. Retry
                // exactly once, only for a transport-level OFFLINE result. The retry stays
                // inside this generation so logout/background/expiry cancellation wins.
                val gallery = galleryReadWithOfflineRecovery(credential, library, page, media, generation)
                if (!active(generation)) return@launch
                validResponse(gallery.library_id == library && gallery.page == page && gallery.page_size in 1..100 && gallery.total >= 0 && gallery.items.size <= gallery.page_size)
                validResponse(media == GalleryMedia.ALL || gallery.items.all { it.kind == media.assetKind })
                val unique = gallery.copy(items = gallery.items.distinctBy { it.id })
                mutable.value = state.value.copy(gallery = unique)
                var byteCount = 0
                val images = mutableMapOf<String, ByteArray>()
                for (asset in unique.items) {
                    val bytes = try { api.thumbnail(credential, library, asset) }
                    catch (e: ApiFailure) {
                        // A missing preview must not discard an already authorized page.
                        // Denials, TLS, invalid data and rate limits still close the view.
                        if (e.kind == FailureKind.OFFLINE || e.kind == FailureKind.HTTP &&
                            e.status in 502..504 && e.retryAfterMillis == 0L) null else throw e
                    }
                    if (!active(generation)) return@launch
                    if (bytes != null && bytes.size <= HttpsPhotoHouseApi.IMAGE_LIMIT && byteCount + bytes.size <= CACHE_LIMIT) {
                        images[asset.id] = bytes; byteCount += bytes.size
                        mutable.value = state.value.copy(previews = images.toMap())
                    }
                }
                mutable.value = state.value.copy(busy = false)
                afterLoaded?.invoke()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { readFailure(e, generation, credential) { loadPage(page, media) } }
        }
    }
    private suspend fun galleryReadWithOfflineRecovery(
        credential: Bearer,
        library: String,
        page: Int,
        media: GalleryMedia,
        generation: Long,
    ): Gallery {
        try {
            return api.gallery(credential, library, page, media)
        } catch (e: ApiFailure) {
            if (e.kind != FailureKind.OFFLINE) throw e
            delay(GALLERY_RECOVERY_DELAY_MILLIS)
            if (!active(generation)) throw CancellationException("Gallery read is no longer active")
            return api.gallery(credential, library, page, media)
        }
    }
    fun navigatePage(page: Int) {
        val family = state.value.familyTags
        if (family != null) {
            if (family.selectedTag != null) openFamilyTag(family.selectedTag, page) else openFamilyTags(family.query, page)
        } else if (state.value.discovery != null) searchDiscoveryPage(page) else loadPage(page)
    }
    fun openDiscovery() {
        if (!api.discoveryEnabled || !allowed() || coolingDown()) return
        loadDiscoveryFacet(PhoneFacet.PEOPLE, 1, PhoneDiscoveryState())
    }
    fun editDiscovery() {
        if (!allowed() || state.value.busy) return
        val current = state.value.discovery ?: return
        val library = state.value.library
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(library = library, discovery = current.copy(editing = true, result = null))
    }
    fun updatePlaceQuery(query: String) {
        if (!allowed() || state.value.discovery == null || !PhoneDiscoveryWire.validPlaceQuery(query)) return
        val current = state.value.discovery ?: return
        if (current.placeQuery == query) return
        val library = state.value.library
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(library = library, busy = false,
            discovery = current.copy(placeQuery = query, facetPage = null, editing = true, result = null, inputInvalid = false))
    }
    fun searchPlaces() {
        val current = state.value.discovery ?: return
        loadDiscoveryFacet(PhoneFacet.PLACES, 1, current)
    }
    fun updateDiscoveryFilters(filters: PhoneFilters) {
        if (!allowed() || state.value.busy) return
        val current = state.value.discovery ?: return
        if (!current.editing || current.snapshot == null) return
        // Only records actually shown in this scope can become selected IDs.
        for ((next, previous, field) in listOf(Triple(filters.people, current.filters.people, PhoneFacet.PEOPLE),
            Triple(filters.tags, current.filters.tags, PhoneFacet.TAGS), Triple(filters.places, current.filters.places, PhoneFacet.PLACES))) {
            val known = previous + (current.facetPage?.takeIf { it.facet == field }?.items ?: emptyList()) +
                (if (field == PhoneFacet.PEOPLE) current.snapshot.pins else emptyList())
            if (next.size > 20 || next.any { choice -> choice !in known } || next.map { it.id }.distinct().size != next.size) return
        }
        mutable.value = state.value.copy(discovery = current.copy(filters = filters, inputInvalid = false))
    }
    fun loadDiscoveryFacet(facet: PhoneFacet, page: Int = 1, context: PhoneDiscoveryState? = state.value.discovery) {
        if (!api.discoveryEnabled || !allowed() || coolingDown() || page !in 1..5000) return
        val previous = context ?: PhoneDiscoveryState()
        val snapshot = previous.snapshot
        if (page > 1 && snapshot == null) return
        val library = state.value.library!!; val credential = token!!
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(library = library, busy = true, discovery = previous.copy(editing = true, facetPage = null))
        launch { generation ->
            try {
                val response = if (facet == PhoneFacet.PLACES) {
                    api.placeFacets(credential, library, page, previous.placeQuery, snapshot?.binding)
                } else api.facets(credential, library, facet, page, snapshot?.binding)
                if (!active(generation)) return@launch
                validResponse(response.snapshot.library == library && response.facet == facet && response.page == page && response.size == 50)
                validResponse(snapshot == null || response.snapshot == snapshot)
                mutable.value = state.value.copy(busy = false, discovery = previous.copy(snapshot = response.snapshot,
                    facetPage = response, editing = true, changed = false, inputInvalid = false))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { discoveryFailure(e, generation, credential, library) }
        }
    }
    fun applyDiscovery() {
        val context = state.value.discovery ?: return
        if (state.value.busy || context.snapshot == null) return
        if (runCatching { context.filters.json().keys.all { it in context.snapshot.enabled } }.getOrDefault(false)) {
            searchDiscoveryPage(1, context.copy(result = null))
        } else mutable.value = state.value.copy(discovery = context.copy(inputInvalid = true))
    }
    fun searchDiscoveryPage(page: Int, context: PhoneDiscoveryState? = state.value.discovery) {
        if (!api.discoveryEnabled || !allowed() || coolingDown() || page !in 1..100000) return
        val previous = context ?: return; val snapshot = previous.snapshot ?: return
        val fingerprint = if (page == 1) null else previous.result?.fingerprint ?: return
        val library = state.value.library!!; val credential = token!!
        if (snapshot.library != library) return
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(library = library, busy = true, discovery = previous.copy(editing = false))
        launch { generation ->
            try {
                val result = api.search(credential, library, snapshot.binding, previous.filters, page, fingerprint)
                if (!active(generation)) return@launch
                validResponse(result.gallery.library_id == library && result.gallery.page == page && result.gallery.page_size == 50 &&
                    result.binding == snapshot.binding && (fingerprint == null || result.fingerprint == fingerprint))
                mutable.value = state.value.copy(gallery = result.gallery, discovery = previous.copy(result = result, editing = false))
                val images = mutableMapOf<String, ByteArray>(); var byteCount = 0
                for (asset in result.gallery.items) {
                    val bytes = try { api.thumbnail(credential, library, asset) }
                    catch (e: ApiFailure) {
                        // A missing preview must not discard an already authorized page.
                        // Denials, TLS, invalid data and rate limits still close the view.
                        if (e.kind == FailureKind.OFFLINE || e.kind == FailureKind.HTTP &&
                            e.status in 502..504 && e.retryAfterMillis == 0L) null else throw e
                    }
                    if (!active(generation)) return@launch
                    if (bytes != null && bytes.size <= HttpsPhotoHouseApi.IMAGE_LIMIT && byteCount + bytes.size <= CACHE_LIMIT) {
                        images[asset.id] = bytes; byteCount += bytes.size
                        mutable.value = state.value.copy(previews = images.toMap())
                    }
                }
                mutable.value = state.value.copy(busy = false)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { discoveryFailure(e, generation, credential, library) }
        }
    }
    private suspend fun discoveryFailure(error: Exception, generation: Long, credential: Bearer, library: String) {
        if (!active(generation)) return
        if (error is ApiFailure && error.status == 409) {
            invalidate(keepIdentity = true)
            mutable.value = state.value.copy(library = library, discovery = PhoneDiscoveryState(changed = true), problem = LiveProblem(Message.DISCOVERY_CHANGED))
            // The user obtains fresh facets, then explicitly applies a new query.
        } else {
            readFailure(error, generation, credential) { openDiscovery() }
            if (active(generation) && error is ApiFailure && error.status == 400)
                mutable.value = state.value.copy(problem = LiveProblem(Message.DISCOVERY_INPUT))
        }
    }
    fun openAssetById(input: String) {
        val id = input.trim()
        if (!validAssetLookupId(id) || !allowed() || coolingDown()) return
        val current = state.value
        val navigation = current.gallery?.let { PhotoNavigation(it.page, listOf(id), 0, current.discovery, current.media) }
        // Detail, captions and media keep the same library/session authorization as a card tap.
        openPhoto(id, navigation)
    }
    fun openMedia(asset: Asset) = openAsset(asset, viewMedia = true)
    fun openAsset(asset: Asset, viewMedia: Boolean = false) {
        val gallery = state.value.gallery
        val ids = gallery?.items?.map { it.id }.orEmpty()
        val index = ids.indexOf(asset.id)
        val navigation = if (gallery != null && index >= 0) PhotoNavigation(gallery.page, ids, index, state.value.discovery, state.value.media, gallery.items.filter { it.kind == "video" }.map { it.id }.toSet()) else null
        openPhoto(asset.id, navigation, mediaAfterLoad = viewMedia)
    }
    fun adjacentPhoto(direction: Int) {
        if (state.value.busy || direction !in listOf(-1, 1)) return
        val navigation = state.value.photoNavigation ?: return
        val index = navigation.index + direction
        if (index !in navigation.assetIds.indices) return
        openPhoto(navigation.assetIds[index], navigation.copy(index = index))
    }
    fun backToPhotos() {
        state.value.familyTags?.let { family ->
            if (family.selectedTag != null) { openFamilyTag(family.selectedTag, family.assetPage); return }
            openFamilyTags(family.query, family.page); return
        }
        val navigation = state.value.photoNavigation
        val context = navigation?.discovery
        if (context != null) searchDiscoveryPage(navigation.page, context)
        else loadPage(navigation?.page ?: state.value.gallery?.page ?: 1, navigation?.media ?: state.value.media)
    }
    fun adjacentVideoId(direction: Int): String? {
        if (direction !in listOf(-1, 1)) return null
        val navigation = state.value.photoNavigation ?: return null
        return generateSequence(navigation.index + direction) { it + direction }
            .takeWhile { it in navigation.assetIds.indices }
            .map { navigation.assetIds[it] }.firstOrNull { it in navigation.videoIds }
    }
    fun adjacentVideo(direction: Int) {
        if (!allowed() || state.value.busy || state.value.video == null) return
        val id = adjacentVideoId(direction) ?: return
        val navigation = state.value.photoNavigation ?: return
        openPhoto(id, navigation.copy(index = navigation.assetIds.indexOf(id)), mediaAfterLoad = true)
    }
    fun openVideo() = startVideo(prepared = api.preparedVideoEnabled)
    fun openOriginalVideo() = startVideo(prepared = false)
    private fun startVideo(prepared: Boolean) {
        if (!allowed() || state.value.busy || state.value.video != null || coolingDown()) return
        val detail = state.value.detail ?: return
        if (detail.asset.kind != "video" || (!prepared && !detail.originals_allowed)) return
        val credential = token!!
        val navigation = state.value.photoNavigation
        retainDetail(viewingOriginal = false, busy = prepared)
        val generation = state.value.generation
        fun attach(info: PreparedVideoInfo?) {
            if (!active(generation)) return
            val reader = VideoReader({ start, length ->
                if (info != null) api.preparedVideoRange(credential, detail.library_id, detail.asset.id, info, start, length)
                else api.videoRange(credential, detail.library_id, detail.asset.id, start, length)
            }, deadline, now, initialSize = info?.bytes ?: -1L, readAhead = prepared, retryTransientRead = prepared) { error ->
                scope.launch {
                    if (active(generation)) {
                        if (prepared) preparedPlaybackFailure(error, generation, credential)
                        else readFailure(error, generation, credential) { openPhoto(detail.asset.id, navigation) }
                    }
                }
            }
            val key = listOf(identity?.account_id, detail.library_id, detail.asset.id, info?.etag).joinToString("\u0000")
            // Original playback has no representation identity, so never reuse a bookmark.
            mutable.value = state.value.copy(video = reader, busy = false,
                videoBookmark = if (info != null) playbackProgress.open(key) else null)
        }
        if (!prepared) attach(null)
        else launch {
            try {
                val info = api.preparedVideoInfo(credential, detail.library_id, detail.asset.id)
                attach(info)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { preparedPlaybackFailure(e, generation, credential) }
        }
    }
    private suspend fun preparedPlaybackFailure(error: Exception, generation: Long, credential: Bearer) {
        if (!active(generation)) return
        if (error is ApiFailure && error.status in listOf(401, 403)) {
            readFailure(error, generation, credential) { } // Privacy handling owns denial; never fall back.
            return
        }
        retainDetail(viewingOriginal = false, busy = false)
        val generic = problem(error)
        val message = when ((error as? ApiFailure)?.status) {
            404 -> Message.VIDEO_NOT_READY
            409 -> Message.VIDEO_CHANGED
            429 -> Message.VIDEO_BUSY
            503 -> Message.PLAYBACK_UNAVAILABLE
            else -> generic.message
        }
        mutable.value = state.value.copy(problem = generic.copy(message = message))
        if (error is ApiFailure && (error.status in listOf(404, 409, 429, 503) || error.kind == FailureKind.OFFLINE))
            retry = { openVideo() } // Explicit retry repeats HEAD; no automatic loop or original fallback.
    }
    fun closeVideo(reader: VideoReader? = state.value.video) {
        if (state.value.video !== reader) return
        if (usable() && state.value.video != null) retainDetail(viewingOriginal = false, busy = false)
    }
    fun videoPlaybackFailed(reader: VideoReader, nativeFailure: Boolean = false, reason: VideoPlaybackFailure? = null) {
        if (state.value.video !== reader || !usable()) return
        // Transport failure owns its classified error and any session recheck. A native
        // failure may already have closed its source to stop reads/audio immediately.
        if (reader.hasReadFailure || reader.isClosed && !nativeFailure) return
        reader.close()
        retainDetail(viewingOriginal = false, busy = false)
        mutable.value = state.value.copy(problem = LiveProblem(Message.MEDIA_UNAVAILABLE, playbackFailure = reason))
        if (reason?.canRetry == true) retry = { openVideo() }
    }
    fun openDisplayPhoto() {
        val detail = state.value.detail ?: return
        if (!api.photoDeliveryEnabled || detail.asset.kind != "image") return
        openPhoto(detail.asset.id, state.value.photoNavigation, mediaAfterLoad = true)
    }
    /** Open only the already-authorized preview route; never infer original access. */
    fun openPreviewPhoto() {
        val detail = state.value.detail ?: return
        if (!api.protectedNativeV2Enabled || api.photoDeliveryEnabled || detail.asset.kind != "image") return
        openPhoto(detail.asset.id, state.value.photoNavigation, mediaAfterLoad = true)
    }
    fun openOriginalPhoto() {
        if (!allowed() || state.value.busy || (state.value.viewingOriginal && state.value.photoOriginalQuality) || coolingDown()) return
        val detail = state.value.detail ?: return
        if (!detail.originals_allowed || detail.asset.kind != "image") return
        val credential = token!!
        val navigation = state.value.photoNavigation
        retainDetail(viewingOriginal = true, busy = true)
        launch { generation ->
            try {
                val bytes = api.originalPhoto(credential, detail.library_id, detail.asset.id)
                if (!active(generation)) return@launch
                if (bytes.size > HttpsPhotoHouseApi.ORIGINAL_LIMIT) throw ApiFailure(FailureKind.TOO_LARGE)
                validResponse(bytes.isNotEmpty())
                mutable.value = state.value.copy(originalPhoto = bytes, busy = false, photoOriginalQuality = true, photoPreviewOnly = false)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                // Retry reloads metadata/permission first; original access remains explicit.
                readFailure(e, generation, credential) { openPhoto(detail.asset.id, navigation) }
            }
        }
    }
    fun closeOriginalPhoto() {
        if (!usable()) return
        if (state.value.viewingOriginal) retainDetail(viewingOriginal = false, busy = false)
    }
    fun togglePhotoSlideshow() {
        if (state.value.photoSlideshow) { stopPhotoSlideshow(); return }
        val current = state.value
        val navigation = current.photoNavigation ?: return
        if (!allowed() || current.busy || !current.viewingOriginal || current.originalPhoto == null ||
            navigation.index >= navigation.assetIds.lastIndex || coolingDown()) return
        mutable.value = current.copy(photoSlideshow = true)
    }
    fun stopPhotoSlideshow() { mutable.value = state.value.copy(photoSlideshow = false) }
    /** A slideshow never wraps, crosses pages, skips denied items, or starts video audio. */
    fun advancePhotoSlideshow() {
        if (!state.value.photoSlideshow) return
        adjacentOriginalPhoto(1, fromSlideshow = true)
    }
    fun adjacentOriginalPhoto(direction: Int, fromSlideshow: Boolean = false) {
        val current = state.value
        if (!allowed() || current.busy || !current.viewingOriginal || direction !in listOf(-1, 1) ||
            (fromSlideshow && (!current.photoSlideshow || direction != 1))) return
        val navigation = current.photoNavigation ?: return
        val index = navigation.index + direction
        if (index !in navigation.assetIds.indices) { stopPhotoSlideshow(); return }
        openPhoto(navigation.assetIds[index], navigation.copy(index = index), originalAfterLoad = true, slideshow = fromSlideshow, originalQuality = current.photoOriginalQuality)
    }
    private fun retainDetail(viewingOriginal: Boolean, busy: Boolean) {
        val previous = state.value
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(library = previous.library, detail = previous.detail,
            captions = previous.captions, previews = previous.previews, photoNavigation = previous.photoNavigation, media = previous.media,
            familyTags = previous.familyTags,
            viewingOriginal = viewingOriginal, busy = busy)
    }
    private fun openPhoto(assetId: String, navigation: PhotoNavigation?, originalAfterLoad: Boolean = false, slideshow: Boolean = false, mediaAfterLoad: Boolean = false, originalQuality: Boolean = false, allowTransientRetry: Boolean = true) {
        if (!allowed() || coolingDown()) return
        val library = state.value.library!!; val credential = token!!
        val familyTags = state.value.familyTags
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(library = library, busy = true, photoNavigation = navigation,
            familyTags = familyTags, viewingOriginal = originalAfterLoad, photoSlideshow = slideshow, media = navigation?.media ?: GalleryMedia.ALL)
        launch { generation ->
            try {
                val detail = api.detail(credential, library, assetId)
                if (!active(generation)) return@launch
                validResponse(detail.library_id == library && detail.asset.id == assetId)
                val captions = api.captions(credential, library, assetId)
                if (!active(generation)) return@launch
                validResponse(captions.library_id == library && captions.asset_id == assetId && captions.items.size <= 20 && captions.items.map { it.id }.distinct().size == captions.items.size)
                val bytes = api.detailPreview(credential, library, detail.asset)
                if (!active(generation)) return@launch
                validResponse(bytes == null || bytes.size <= HttpsPhotoHouseApi.IMAGE_LIMIT)
                val usePreview = api.protectedNativeV2Enabled && !api.photoDeliveryEnabled && !originalQuality
                val useOriginal = originalQuality || (!api.photoDeliveryEnabled && !usePreview)
                val requestedPhoto = (originalAfterLoad || mediaAfterLoad) && detail.asset.kind == "image"
                val openOriginal = requestedPhoto && (!useOriginal || detail.originals_allowed) &&
                    (!usePreview || bytes?.isNotEmpty() == true)
                mutable.value = state.value.copy(detail = detail, captions = captions, busy = openOriginal,
                    viewingOriginal = openOriginal, photoOriginalQuality = useOriginal, photoSlideshow = state.value.photoSlideshow && openOriginal,
                    photoPreviewOnly = usePreview && openOriginal,
                    problem = if (requestedPhoto && usePreview && !openOriginal) LiveProblem(Message.MEDIA_UNAVAILABLE) else null,
                    previews = if (bytes == null) emptyMap() else mapOf(assetId to bytes))
                if (openOriginal) {
                    val original = when {
                        usePreview -> bytes!!
                        useOriginal -> api.originalPhoto(credential, library, assetId)
                        else -> api.displayPhoto(credential, library, assetId)
                    }
                    if (!active(generation)) return@launch
                    if (original.size > HttpsPhotoHouseApi.ORIGINAL_LIMIT) throw ApiFailure(FailureKind.TOO_LARGE)
                    validResponse(original.isNotEmpty())
                    mutable.value = state.value.copy(originalPhoto = original, busy = false,
                        photoSlideshow = state.value.photoSlideshow && navigation != null && navigation.index < navigation.assetIds.lastIndex)
                }
                // The gallery tap requests viewing; returned detail and each byte read
                // still authorize access. Preparing a player never starts its audio.
                if (mediaAfterLoad && (api.preparedVideoEnabled || detail.originals_allowed) && detail.asset.kind == "video") openVideo()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                readFailure(e, generation, credential, allowTransientRetry = allowTransientRetry) {
                    openPhoto(assetId, navigation, originalAfterLoad, slideshow && state.value.photoSlideshow,
                        mediaAfterLoad, originalQuality, allowTransientRetry = false)
                }
            }
        }
    }
    private suspend fun readFailure(error: Exception, generation: Long, credential: Bearer, allowTransientRetry: Boolean = false, retryRead: () -> Unit) {
        if (!active(generation)) return
        if (error is ApiFailure && error.status in listOf(401, 403)) {
            playbackProgress.clear()
            closeGroupedStoryCreation(discard = true)
        }
        // A protected photo transition is a read-only operation. Give a single
        // short-lived transport/5xx failure a bounded recovery attempt while
        // retaining the current generation and cancellation boundary. Auth
        // denial, rate limiting, malformed responses and writes remain explicit.
        if (allowTransientRetry && error is ApiFailure &&
            (error.kind == FailureKind.OFFLINE ||
                error.kind == FailureKind.HTTP && error.status in 502..504 && error.retryAfterMillis == 0L)) {
            delay(350)
            if (active(generation)) retryRead()
            return
        }
        state.value.savedMemoryStories?.frames?.values?.forEach { it.fill(0) }
        state.value.savedMemoryStories?.hero?.fill(0)
        state.value.savedMemoryStories?.covers?.values?.forEach { it.fill(0) }
        savedMemoryListRequest++; savedMemoryDetailRequest++; savedMemoryFramesRequest++; savedMemoryCoversRequest++; savedMemoryHeroRequest++
        state.value.video?.close()
        mutable.value = state.value.copy(video = null, gallery = null, detail = null, captions = null, previews = emptyMap(), photoNavigation = null, originalPhoto = null, viewingOriginal = false, photoSlideshow = false, photoPreviewOnly = false, photoOriginalQuality = false, discovery = null, stories = null, savedMemoryStories = null, familyTags = null, busy = false, problem = problem(error))
        if (error is ApiFailure && error.status == 401) {
            mutable.value = state.value.copy(busy = true)
            try {
                val session = api.session(credential)
                if (!active(generation)) return
                validateSession(session, identity?.account_id)
                identity = session
                invalidate(keepIdentity = true)
                mutable.value = state.value.copy(problem = LiveProblem(Message.ACCESS_DENIED), busy = false)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation)) return
                if (e is ApiFailure && e.status == 401) expire()
                else {
                    invalidate(keepIdentity = true, cover = true)
                    mutable.value = state.value.copy(problem = problem(e))
                    retry = { foreground() }
                }
            }
        } else if (error is ApiFailure && (error.status == 429 || error.status in 500..599 || error.kind == FailureKind.OFFLINE)) retry = retryRead
    }
    fun acceptInvitation(code: String) {
        if (!usable() || state.value.busy || coolingDown()) return
        val credential = token!!
        val previousLibrary = state.value.library
        invalidate(keepIdentity = true)
        mutable.value = state.value.copy(busy = true)
        launch { generation ->
            try {
                api.acceptInvitation(credential, code)
                if (!active(generation)) return@launch
                val session = api.session(credential)
                if (!active(generation)) return@launch
                validateSession(session, identity?.account_id)
                identity = session
                mutable.value = state.value.copy(session = session, busy = false)
                openPreferredLibrary(session, previousLibrary)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { readFailure(e, generation, credential) { background(); foreground() } }
        }
    }
    fun background() {
        // Retain only an internal selection hint; clear all private UI state.
        if (!state.value.covered) resumeLibrary = state.value.library
        batchQueue?.pause(); invalidate(keepIdentity = true, cover = true)
    }
    fun foreground() {
        if (!state.value.covered || state.value.busy || coolingDown()) return
        val credential = token
        val previousLibrary = resumeLibrary
        if (credential == null) { invalidate(keepIdentity = false); return }
        if (now() >= deadline) { expire(); return }
        invalidate(keepIdentity = true, cover = true)
        mutable.value = state.value.copy(busy = true)
        launch { generation ->
            try {
                val session = api.session(credential)
                if (!active(generation)) return@launch
                validateSession(session, identity?.account_id)
                identity = session
                batchQueue?.attach(session.account_id)
                mutable.value = state.value.copy(session = session, covered = false, busy = false)
                resumeLibrary = null
                openPreferredLibrary(session, previousLibrary)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!active(generation)) return@launch
                if (e is ApiFailure && e.status == 401) expire()
                else { mutable.value = state.value.copy(busy = false, problem = problem(e)); retry = { foreground() } }
            }
        }
    }
    fun logout() {
        val credential = token
        invalidate(keepIdentity = false)
        mutable.value = state.value.copy(problem = state.value.problem?.takeIf { it.message == Message.SESSION_STORAGE_UNAVAILABLE }
            ?: LiveProblem(Message.SIGNED_OUT_LOCAL, cooldownUntil))
        if (credential == null) return
        launch { generation ->
            try {
                api.logout(credential)
                if (active(generation)) mutable.value = state.value.copy(problem = LiveProblem(Message.SIGNED_OUT_CONFIRMED, cooldownUntil))
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { /* Local logout remains final even when server acknowledgement fails. */ }
        }
    }
    private fun expire() { invalidate(keepIdentity = false); mutable.value = state.value.copy(problem = state.value.problem?.takeIf { it.message == Message.SESSION_STORAGE_UNAVAILABLE } ?: LiveProblem(Message.SESSION_ENDED)) }
    fun canRetry(at: Long = now()) = retry != null && at >= cooldownUntil
    fun retry() { if (canRetry()) { val action = retry; retry = null; action?.invoke() } }
    private fun problem(error: Exception): LiveProblem {
        if (error is IllegalArgumentException) return LiveProblem(Message.INVALID_INPUT)
        if (error !is ApiFailure) return LiveProblem(Message.INVALID_RESPONSE)
        val message = when {
            error.kind == FailureKind.TOO_LARGE -> Message.TOO_LARGE
            error.status == 404 -> Message.MEDIA_UNAVAILABLE
            error.kind == FailureKind.TLS -> Message.TLS_ERROR
            error.kind == FailureKind.OFFLINE -> Message.NETWORK_UNAVAILABLE
            error.status in 500..599 -> Message.UNAVAILABLE
            error.status == 401 -> Message.ACCESS_DENIED
            error.status == 403 || error.status in 300..399 -> Message.CLOSED
            error.status == 429 -> Message.RATE_LIMITED
            error.kind == FailureKind.INVALID_INPUT || error.status == 400 || error.status == 409 -> Message.INVALID_INPUT
            else -> Message.INVALID_RESPONSE
        }
        val wait = error.retryAfterMillis.coerceAtLeast(0)
        val at = if (Long.MAX_VALUE - now() < wait) Long.MAX_VALUE else now() + wait
        val retryAfterCooldown = error.status in 502..504 && wait > 0
        if (message == Message.RATE_LIMITED || retryAfterCooldown) cooldownUntil = maxOf(cooldownUntil, at)
        return LiveProblem(message, if (message == Message.RATE_LIMITED || retryAfterCooldown) cooldownUntil else 0)
    }
    private fun validateSession(session: Session, account: String? = null) {
        validResponse(session.account_id.isNotBlank() && (account == null || session.account_id == account))
        validResponse(session.memberships.all { it.revision >= 1 && it.originals in 0..1 })
        validResponse(session.memberships.map { it.library_id }.distinct().size == session.memberships.size)
    }
    /**
     * Select the protected Family library by stable wire ID when it is available.
     * A currently open accessible library wins during revalidation; otherwise the
     * first accessible membership remains the existing fallback. Display names
     * never participate in authorization or selection.
     */
    private fun preferredLibrary(session: Session, current: String? = null): String? {
        val available = session.memberships.filter { it.available }
        return available.firstOrNull { it.library_id == current }?.library_id
            ?: available.firstOrNull { it.library_id == "family" }?.library_id
            ?: available.firstOrNull()?.library_id
    }
    private fun openPreferredLibrary(session: Session, current: String? = state.value.library) {
        val library = preferredLibrary(session, current) ?: return
        val storageWarning = state.value.problem?.takeIf { it.message == Message.SESSION_STORAGE_UNAVAILABLE }
        selectLibrary(library)
        if (storageWarning != null) mutable.value = state.value.copy(problem = storageWarning)
    }
    private fun validResponse(condition: Boolean) { if (!condition) throw ApiFailure(FailureKind.INVALID_RESPONSE) }
    companion object {
        const val CACHE_LIMIT = 8 * 1024 * 1024
        private const val GALLERY_RECOVERY_DELAY_MILLIS = 350L
    }
}

fun validAssetLookupId(value: String): Boolean = value.matches(Regex("[1-9][0-9]{0,18}")) && value.toLongOrNull() != null
