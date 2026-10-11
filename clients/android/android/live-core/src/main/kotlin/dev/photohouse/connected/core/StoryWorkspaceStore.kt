package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.Collections
import java.util.concurrent.atomic.AtomicLong
import java.util.UUID

enum class StoryWorkspaceStoreStatus {
    SELECTION, PREVIEWING, EDITING, SAVING, SAVE_UNCERTAIN, CONFLICT, SAVED, UNAVAILABLE,
}

data class StoryWorkspaceStoreState(
    val status: StoryWorkspaceStoreStatus = StoryWorkspaceStoreStatus.SELECTION,
    val selectedAssetIds: List<String> = emptyList(),
    val theme: String = "everyday",
    val language: String = "zh",
    val title: String = "",
    val draft: ProtectedStoryWorkspaceDraft? = null,
    val editableChapters: List<SavedMemoryStoryChapter> = emptyList(),
    val savedStory: SavedMemoryStory? = null,
    val titleCapabilities: ProtectedStoryWorkspaceTitleCapabilities? = null,
    val sourceCapabilities: ProtectedStoryWorkspaceSourceCapabilities? = null,
    val sourceCapabilitiesChecked: Boolean = false,
    val sourceReviewEnabled: Boolean = false,
    val titleCandidates: List<ProtectedStoryWorkspaceTitle> = emptyList(),
    val relatedCandidates: List<StoryRelatedMediaCandidate> = emptyList(),
    val relatedBusy: Boolean = false,
    val relatedHasMore: Boolean = false,
    val relatedFailure: Boolean = false,
    val reviewed: Boolean = false,
    val sourcesReloaded: Boolean = false,
    val composing: Boolean = false,
    val invalidInput: Boolean = false,
    val dirty: Boolean = false,
    val busy: Boolean = false,
    val hasPendingSave: Boolean = false,
    val savedStoryIsNewerThanEditBase: Boolean = false,
    val failureStatus: Int? = null,
) {
    val hasUnfinishedWork: Boolean get() = dirty || composing || invalidInput || busy || hasPendingSave ||
        (draft != null && status != StoryWorkspaceStoreStatus.SAVED)
}

/** Process-memory grouped story editor. Preview and save are always explicit user actions. */
class StoryWorkspaceStore(
    private val repository: StoryWorkspaceRepository,
    private val scope: CoroutineScope,
    private val currentBinding: () -> MemoryCommunityBinding?,
    private val dictationApi: PhotoHouseApi?,
    private val currentAccount: () -> String? = { null },
    private val onDictationDenied: () -> Unit = {},
    private val uuidSupplier: () -> UUID = UUID::randomUUID,
) {
    /** Preserves the historical trailing/positional UUID supplier constructor. */
    constructor(
        repository: StoryWorkspaceRepository,
        scope: CoroutineScope,
        currentBinding: () -> MemoryCommunityBinding?,
        uuidSupplier: () -> UUID = UUID::randomUUID,
    ) : this(repository, scope, currentBinding, dictationApi = null, uuidSupplier = uuidSupplier)

    private val mutable = MutableStateFlow(StoryWorkspaceStoreState())
    val state = mutable.asStateFlow()

    private var epoch = 0L
    private var bound: MemoryCommunityBinding? = null
    private var operation: Job? = null
    private var pending: PendingGroupedStorySave? = null
    private var savedEditStory: SavedMemoryStory? = null
    private var savedEditReferences: SavedMemoryStoryContributionReferences? = null
    private var titleRevision = 0L
    private var relatedOperation: Job? = null
    private var relatedRequestRevision = 0L
    private var relatedCursor: String? = null
    private var relatedSeedIds: List<String> = emptyList()
    private var relatedCandidatesChanged: (List<StoryRelatedMediaCandidate>) -> Unit = {}
    private val dictationScopeId = NEXT_DICTATION_SCOPE.incrementAndGet()
    private val mutableChapterDictation = MutableStateFlow<MemoryDictationStore?>(null)
    val chapterDictation: StateFlow<MemoryDictationStore?> = mutableChapterDictation.asStateFlow()
    private val mutableDictationUnfinished = MutableStateFlow(false)
    val dictationUnfinished: StateFlow<Boolean> = mutableDictationUnfinished.asStateFlow()
    private var chapterDictationBinding: StoryChapterDictationStore? = null
    private var chapterDictationObserver: Job? = null
    private var activeDictationChapterId: String? = null
    private var activeDictationChapterIndex: Int? = null

    val hasUnfinishedChapterDictation: Boolean
        get() = mutableDictationUnfinished.value || chapterDictationBinding?.hasUnfinishedInput == true
    val chapterDictationAvailable: Boolean
        get() = dictationApi?.assistantEnabled == true && currentAccount()?.isNotBlank() == true
    val isSavedStoryEdit: Boolean get() = savedEditStory != null
    val savedEditStoryId: String? get() = savedEditStory?.id
    val savedEditStoryRevision: Long? get() = savedEditStory?.revision

    /** Explicitly opens voice input for one editable, currently bound chapter. */
    fun openChapterDictation(index: Int): Boolean {
        val api = dictationApi ?: return false
        if (!editorReady() || state.value.composing || state.value.hasPendingSave || pending != null) return false
        val chapter = state.value.editableChapters.getOrNull(index)
        if (state.value.draft == null || chapter == null || bound == null ||
            currentAccount()?.isNotBlank() != true) return false
        if (chapterDictationBinding != null && (activeDictationChapterIndex != index || activeDictationChapterId != chapter.id)) {
            if (hasUnfinishedChapterDictation) return false
            closeChapterDictation()
        }
        val chapterId = chapter.id
        val chapterIndex = index
        val helper = chapterDictationBinding ?: StoryChapterDictationStore(api, scope, {
            val liveDraft = state.value.draft
            val liveChapter = state.value.editableChapters.getOrNull(chapterIndex)
            val liveBinding = bound
            val liveAccount = currentAccount()
            if (liveDraft == null || liveChapter == null || liveBinding == null || liveAccount == null ||
                liveChapter.id != chapterId ||
                !sameBinding(snapshotBinding(), liveBinding) ||
                state.value.status != StoryWorkspaceStoreStatus.EDITING || state.value.busy ||
                state.value.hasPendingSave || pending != null) null
            else StoryChapterDictationScope(
                accountId = liveAccount, credential = liveBinding.token, library = liveBinding.libraryId,
                generation = liveBinding.generation, scopeId = dictationScopeId,
                selectionRevision = liveDraft.selectionRevision,
                savedStoryId = savedEditStory?.id, savedStoryRevision = savedEditStory?.revision,
                chapterId = liveChapter.id, chapterAssetIds = liveChapter.assetIds.toList(), editable = true,
            )
        }, onDenied = onDictationDenied).also {
            chapterDictationBinding = it
            activeDictationChapterId = chapterId
            activeDictationChapterIndex = chapterIndex
        }
        val opened = helper.open() ?: return false
        if (mutableChapterDictation.value !== opened) {
            chapterDictationObserver?.cancel()
            mutableChapterDictation.value = opened
            chapterDictationObserver = scope.launch {
                opened.state.collect { value ->
                    mutableDictationUnfinished.value = value.loading || value.recording || value.transcribing || value.transcript != null
                }
            }
        }
        return true
    }

    /** Closes capture/review and wipes any unconsumed transient transcript. */
    fun closeChapterDictation() {
        chapterDictationObserver?.cancel(); chapterDictationObserver = null
        chapterDictationBinding?.clear(); chapterDictationBinding = null
        activeDictationChapterId = null
        activeDictationChapterIndex = null
        mutableChapterDictation.value = null
        mutableDictationUnfinished.value = false
    }

    /** Ignores disposal from an older rendered input after a newer chapter helper has opened. */
    fun closeChapterDictationIfCurrent(expected: MemoryDictationStore): Boolean {
        if (mutableChapterDictation.value !== expected) return false
        closeChapterDictation()
        return true
    }

    /** Seeds a freshly read saved story only after its complete same-revision link map is available. */
    fun seedSavedStoryForEdit(
        story: SavedMemoryStory,
        references: SavedMemoryStoryContributionReferences,
    ): Boolean {
        if (!allowedSavedEditInput(story, references)) return false
        val prior = savedEditStory
        if (prior != null && (state.value.status !in setOf(StoryWorkspaceStoreStatus.CONFLICT, StoryWorkspaceStoreStatus.UNAVAILABLE) ||
                prior.id != story.id || pending != null || state.value.hasPendingSave)) return false
        if (prior == null && (state.value.status != StoryWorkspaceStoreStatus.SELECTION || state.value.draft != null)) return false
        val expected = snapshotBinding() ?: return false
        if (expected.libraryId != story.libraryId || !sameBinding(bound, expected) && bound != null) return false
        closeChapterDictation()
        clearOperationOnly()
        clearRelated()
        bound = expected
        pending = null
        savedEditStory = detachSavedStory(story)
        savedEditReferences = detachContributionReferences(references)
        val draft = detachDraft(ProtectedStoryWorkspaceDraft(story.libraryId, story.selectionRevision, story.title,
            story.theme, story.language, story.items, story.chapters, story.questions))
        val valid = validText(story.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) &&
            story.chapters.all { validText(it.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) &&
                validText(it.narration, 6000, allowNewline = true) }
        mutable.value = StoryWorkspaceStoreState(
            status = StoryWorkspaceStoreStatus.EDITING,
            selectedAssetIds = immutable(story.chapters.flatMap { it.assetIds }), theme = story.theme,
            language = story.language, title = story.title, draft = draft,
            editableChapters = immutable(story.chapters.map(::detachChapter)),
            sourceCapabilities = if (story.sourcePolicy != null) ProtectedStoryWorkspaceSourceCapabilities(story.sourcePolicy, 12) else null,
            sourceCapabilitiesChecked = story.sourcePolicy != null,
            sourceReviewEnabled = story.sourcePolicy == ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1,
            dirty = false, invalidInput = !valid,
        )
        epoch++
        return true
    }

    private fun allowedSavedEditInput(story: SavedMemoryStory, references: SavedMemoryStoryContributionReferences): Boolean {
        val ids = story.chapters.map { it.id }
        return story.canEdit && story.libraryId == snapshotBinding()?.libraryId && story.revision in 1 until Long.MAX_VALUE &&
            story.id == runCatching { UUID.fromString(story.id).toString() }.getOrNull() &&
            story.selectionRevision.matches(Regex("[0-9a-fA-F]{64}")) &&
            story.sourcePolicy in setOf(null, ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1) &&
            story.items.isNotEmpty() && story.items.size <= MAX_ASSETS && story.items.map { it.asset.id }.distinct().size == story.items.size &&
            story.chapters.isNotEmpty() && story.chapters.size <= 6 &&
            ids == (1..ids.size).map { "chapter-$it" } && story.chapters.flatMap { it.assetIds } == story.items.map { it.asset.id } &&
            references.id == story.id && references.libraryId == story.libraryId && references.revision == story.revision &&
            references.chapters.map { it.chapterId } == ids && references.chapters.all { it.contributionIds.size <= 12 &&
                it.contributionIds.distinct().size == it.contributionIds.size && it.contributionIds.all { id ->
                    runCatching { UUID.fromString(id).toString() == id }.getOrDefault(false)
                } }
    }

    private fun detachContributionReferences(value: SavedMemoryStoryContributionReferences) = value.copy(
        chapters = immutable(value.chapters.map { it.copy(contributionIds = immutable(it.contributionIds)) }))

    /** Adds the currently reviewed words to the latest chapter text, or keeps the transcript on rejection. */
    fun insertChapterTranscript(index: Int, composing: Boolean): Boolean {
        if (composing || !editorReady()) return false
        if (index != activeDictationChapterIndex) return false
        val target = state.value.editableChapters.getOrNull(index) ?: return false
        if (target.id != activeDictationChapterId) return false
        val helper = chapterDictationBinding ?: return false
        return helper.insertTranscript { transcript ->
            val chapter = state.value.editableChapters.getOrNull(index)?.takeIf { it.id == activeDictationChapterId }
                ?: return@insertTranscript false
            val joined = if (chapter.narration.isEmpty()) transcript else chapter.narration + "\n\n" + transcript
            if (!validText(joined, 6000, allowNewline = true)) return@insertTranscript false
            editChapterNarration(index, joined)
        }
    }

    /** Set by the owning connected editor without changing its UUID supplier API. */
    internal fun observeRelatedCandidates(listener: (List<StoryRelatedMediaCandidate>) -> Unit) {
        relatedCandidatesChanged = listener
    }

    private fun sameBinding(left: MemoryCommunityBinding?, right: MemoryCommunityBinding?): Boolean =
        left != null && right != null && left.token === right.token && left.libraryId == right.libraryId &&
            left.generation == right.generation

    private fun snapshotBinding() = currentBinding()?.let { MemoryCommunityBinding(it.token, it.libraryId, it.generation) }

    private fun current(expected: MemoryCommunityBinding, ticket: Long = epoch): Boolean =
        ticket == epoch && sameBinding(bound, expected) && sameBinding(snapshotBinding(), expected)

    private fun ensureCurrent(): Boolean {
        val expected = bound ?: return true
        if (current(expected)) return true
        clear()
        return false
    }

    private fun editable(): Boolean {
        if (!ensureCurrent()) return false
        return state.value.status in setOf(StoryWorkspaceStoreStatus.SELECTION, StoryWorkspaceStoreStatus.EDITING) &&
            !state.value.busy && pending == null
    }

    /** Selection order is preserved. A 25th item is rejected without dropping an existing choice. */
    fun selectAsset(assetId: String, selected: Boolean = true, discardDraft: Boolean = false): Boolean {
        if (!editable() || hasUnfinishedChapterDictation || isSavedStoryEdit) return false
        val numericId = assetId.toLongOrNull() ?: return false
        if (numericId.toString() != assetId || numericId <= 0) return false
        val ids = state.value.selectedAssetIds
        if (selected == (assetId in ids)) return true
        if (state.value.draft != null && !discardDraft) return false
        if (selected && ids.size >= MAX_ASSETS) return false
        invalidatePreview()
        val updated = immutable(ids.let { if (selected) it + assetId else it - assetId })
        mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.SELECTION,
            selectedAssetIds = updated, draft = null, editableChapters = emptyList(), title = "",
            reviewed = false, sourcesReloaded = false, dirty = updated.isNotEmpty(), titleCandidates = emptyList(), failureStatus = null)
        return true
    }

    fun setTheme(value: String, discardDraft: Boolean = false): Boolean {
        if (!editable() || hasUnfinishedChapterDictation || isSavedStoryEdit || value !in SAVED_MEMORY_STORY_THEMES) return false
        if (state.value.theme == value) return true
        if (state.value.draft != null && !discardDraft) return false
        invalidatePreview()
        mutable.value = state.value.copy(theme = value, status = StoryWorkspaceStoreStatus.SELECTION,
            draft = null, editableChapters = emptyList(), title = "", titleCandidates = emptyList(),
            reviewed = false, sourcesReloaded = false, dirty = true, failureStatus = null)
        return true
    }

    fun setLanguage(value: String, discardDraft: Boolean = false): Boolean {
        if (!editable() || hasUnfinishedChapterDictation || isSavedStoryEdit || value !in setOf("zh", "en")) return false
        if (state.value.language == value) return true
        if (state.value.draft != null && !discardDraft) return false
        invalidatePreview()
        mutable.value = state.value.copy(language = value, status = StoryWorkspaceStoreStatus.SELECTION,
            draft = null, editableChapters = emptyList(), title = "", titleCandidates = emptyList(),
            reviewed = false, sourcesReloaded = false, dirty = true, failureStatus = null)
        return true
    }

    private fun invalidatePreview() {
        closeChapterDictation()
        epoch++
        operation?.cancel(); operation = null
        bound = null
        titleRevision++
        clearRelated()
    }

    /** Explicit same-recorded-day lookup. Opening the picker never calls this automatically. */
    fun loadRelatedMedia(nextPage: Boolean = false): Boolean {
        if (!ensureCurrent() || state.value.status != StoryWorkspaceStoreStatus.SELECTION || state.value.busy || state.value.composing) return false
        val seeds = state.value.selectedAssetIds.toList()
        if (seeds.isEmpty() || seeds.size > MAX_ASSETS || state.value.relatedBusy ||
            (nextPage && !state.value.relatedHasMore)) return false
        val expected = snapshotBinding() ?: return false
        bound = expected
        val cursor = if (nextPage && relatedSeedIds == seeds) relatedCursor else null
        if (!nextPage || relatedSeedIds != seeds) {
            relatedSeedIds = seeds
            relatedCursor = null
            relatedCandidatesChanged(emptyList())
            mutable.value = state.value.copy(relatedCandidates = emptyList(), relatedHasMore = false, relatedFailure = false)
        }
        relatedOperation?.cancel()
        val relatedTicket = ++relatedRequestRevision
        val ticket = epoch
        mutable.value = state.value.copy(relatedBusy = true, relatedFailure = false)
        relatedOperation = scope.launch {
            try {
                val page = repository.relatedMedia(seeds, cursor) { current(expected, ticket) }
                if (relatedTicket == relatedRequestRevision && current(expected, ticket) && state.value.selectedAssetIds == seeds) {
                    relatedCursor = page.nextBeforeId
                    val unique = page.items
                    mutable.value = state.value.copy(relatedCandidates = immutable(unique), relatedBusy = false,
                        relatedHasMore = page.hasMore, relatedFailure = false)
                    relatedCandidatesChanged(unique)
                }
            } catch (_: CancellationException) {
                if (relatedTicket == relatedRequestRevision && ticket == epoch) {
                    stale(ticket)
                    if (state.value.status == StoryWorkspaceStoreStatus.SELECTION) mutable.value = state.value.copy(relatedBusy = false)
                }
            } catch (failure: ApiFailure) {
                if (relatedTicket == relatedRequestRevision && current(expected, ticket)) {
                    mutable.value = state.value.copy(relatedBusy = false, relatedFailure = true)
                }
            } catch (_: Exception) {
                if (relatedTicket == relatedRequestRevision && current(expected, ticket)) mutable.value = state.value.copy(relatedBusy = false, relatedFailure = true)
            } finally { if (relatedTicket == relatedRequestRevision && ticket == epoch) relatedOperation = null }
        }
        return true
    }

    /** Retries the same page cursor that failed, including an empty intermediate page. */
    fun retryRelatedMedia(): Boolean = if (!state.value.relatedFailure) false else loadRelatedMedia(nextPage = relatedCursor != null)

    private fun clearRelated() {
        relatedRequestRevision++
        relatedOperation?.cancel(); relatedOperation = null
        relatedCursor = null; relatedSeedIds = emptyList()
        relatedCandidatesChanged(emptyList())
        if (state.value.relatedCandidates.isNotEmpty() || state.value.relatedBusy || state.value.relatedHasMore || state.value.relatedFailure)
            mutable.value = state.value.copy(relatedCandidates = emptyList(), relatedBusy = false, relatedHasMore = false, relatedFailure = false)
    }

    /** Makes one explicit protected preview request for the current ordered selection. */
    fun preview(): Boolean {
        if (!editable() || isSavedStoryEdit || hasUnfinishedChapterDictation || state.value.selectedAssetIds.isEmpty() || state.value.selectedAssetIds.size > MAX_ASSETS) return false
        return startPreview(reloadSources = false)
    }

    /** Retries the first protected preview after an unavailable response, keeping the selection. */
    fun retryPreview(): Boolean {
        if (!ensureCurrent() || state.value.status != StoryWorkspaceStoreStatus.UNAVAILABLE || state.value.draft != null ||
            state.value.selectedAssetIds.isEmpty() || state.value.busy || state.value.composing ||
            state.value.hasPendingSave || pending != null || hasUnfinishedChapterDictation) return false
        return startPreview(reloadSources = false)
    }

    /** Reloads current source evidence while carrying forward prose for explicit re-review. */
    fun reloadPreview(): Boolean {
        if (isSavedStoryEdit) return false
        if (!ensureCurrent() || state.value.status !in setOf(StoryWorkspaceStoreStatus.CONFLICT, StoryWorkspaceStoreStatus.UNAVAILABLE) ||
            state.value.draft == null || state.value.selectedAssetIds.isEmpty() || state.value.busy ||
            state.value.composing || state.value.hasPendingSave || pending != null || hasUnfinishedChapterDictation) return false
        return startPreview(reloadSources = true)
    }

    private fun startPreview(reloadSources: Boolean): Boolean {
        if (hasUnfinishedChapterDictation) return false
        closeChapterDictation()
        val previous = state.value
        val expected = snapshotBinding() ?: return false
        val ids = previous.selectedAssetIds.toList()
        val theme = previous.theme
        val language = previous.language
        val oldDraft = previous.draft?.let(::detachDraft)
        val oldChapters = previous.editableChapters.map(::detachChapter)
        if (reloadSources && (oldDraft == null || oldDraft.items.map { it.asset.id } != ids)) return false
        clearRelated()
        clearOperationOnly()
        bound = expected
        val ticket = epoch
        mutable.value = if (reloadSources) previous.copy(status = StoryWorkspaceStoreStatus.PREVIEWING, busy = true,
            reviewed = false, titleCandidates = emptyList(), failureStatus = null)
        else previous.copy(status = StoryWorkspaceStoreStatus.PREVIEWING, busy = true,
            draft = null, editableChapters = emptyList(), title = "", reviewed = false, composing = false,
            invalidInput = false, sourcesReloaded = false, titleCandidates = emptyList(), failureStatus = null,
            sourceReviewEnabled = false, sourceCapabilities = null, sourceCapabilitiesChecked = false)
        operation = scope.launch {
            try {
                val result = repository.preview(ids, theme, language, "") { current(expected, ticket) }
                if (current(expected, ticket)) {
                    val detached = detachDraft(result)
                    if (reloadSources) {
                        val before = requireNotNull(oldDraft)
                        if (before.chapters.map { it.id to it.assetIds } != detached.chapters.map { it.id to it.assetIds } ||
                            oldChapters.map { it.id to it.assetIds } != detached.chapters.map { it.id to it.assetIds })
                            throw ApiFailure(FailureKind.INVALID_RESPONSE)
                        val prose = oldChapters.associateBy { it.id }
                        val carried = detached.copy(title = previous.title,
                            chapters = immutable(detached.chapters.map { fresh ->
                                val old = prose[fresh.id] ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                val available = fresh.assetIds.flatMap { id -> detached.items.find { it.asset.id == id }
                                    ?.evidence.orEmpty().map { it.id } }.toSet()
                                val checked = old.evidenceIds.filter { it in available }
                                fresh.copy(title = old.title, narration = old.narration,
                                    evidenceIds = if (previous.sourceReviewEnabled) checked else fresh.evidenceIds)
                            }))
                        mutable.value = previous.copy(status = StoryWorkspaceStoreStatus.EDITING, busy = false,
                            draft = carried, editableChapters = immutable(carried.chapters.map(::detachChapter)),
                            reviewed = false, sourcesReloaded = true, titleCandidates = emptyList(), failureStatus = null)
                    } else {
                        mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.EDITING, busy = false,
                            draft = detached, editableChapters = immutable(detached.chapters.map(::detachChapter)), title = detached.title,
                            reviewed = false, dirty = false,
                            invalidInput = !validText(detached.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) ||
                                detached.chapters.any { !validText(it.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) ||
                                    !validText(it.narration, 6000, allowNewline = true) }, failureStatus = null)
                    }
                }
            } catch (_: CancellationException) { stale(ticket) }
            catch (failure: ApiFailure) {
                if (current(expected, ticket)) mutable.value = state.value.copy(
                    status = if (failure.status == 409) StoryWorkspaceStoreStatus.CONFLICT else StoryWorkspaceStoreStatus.UNAVAILABLE,
                    busy = false, failureStatus = failure.status)
                else stale(ticket)
            } catch (_: Exception) {
                if (current(expected, ticket)) mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.UNAVAILABLE,
                    busy = false)
                else stale(ticket)
            } finally { if (ticket == epoch) operation = null }
        }
        return true
    }

    /** Optional capability probe; it is always initiated by the caller. */
    fun loadTitleCapabilities(): Boolean {
        if (!ensureCurrent() || state.value.status != StoryWorkspaceStoreStatus.EDITING || state.value.busy || hasUnfinishedChapterDictation) return false
        val expected = bound ?: return false
        clearOperationOnly()
        val ticket = epoch
        operation = scope.launch {
            try {
                val result = repository.titleCapabilities { current(expected, ticket) }
                if (current(expected, ticket)) mutable.value = state.value.copy(titleCapabilities = result)
            } catch (_: CancellationException) { stale(ticket) }
            catch (_: Exception) {
                if (current(expected, ticket)) mutable.value = state.value.copy(
                    titleCapabilities = ProtectedStoryWorkspaceTitleCapabilities(false, 3)) else stale(ticket)
            } finally { if (ticket == epoch) operation = null }
        }
        return true
    }

    /** Explicit opt-in. Unsupported closed-boundary APIs leave source selection unavailable. */
    fun enableSourceReview(): Boolean {
        if (!ensureCurrent() || state.value.status != StoryWorkspaceStoreStatus.EDITING || state.value.busy || state.value.sourceReviewEnabled || hasUnfinishedChapterDictation) return false
        val expected = bound ?: return false
        closeChapterDictation()
        clearOperationOnly()
        val ticket = epoch
        mutable.value = state.value.copy(busy = true, sourceCapabilities = null, sourceCapabilitiesChecked = false)
        operation = scope.launch {
            try {
                val result = repository.sourceCapabilities { current(expected, ticket) }
                if (current(expected, ticket)) mutable.value = state.value.copy(busy = false,
                    sourceCapabilities = result, sourceCapabilitiesChecked = true,
                    sourceReviewEnabled = result?.sourcePolicy == ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1)
            } catch (_: CancellationException) { stale(ticket) }
            catch (_: Exception) { if (current(expected, ticket)) mutable.value = state.value.copy(busy = false,
                sourceCapabilities = null, sourceCapabilitiesChecked = true) else stale(ticket) }
            finally { if (ticket == epoch) operation = null }
        }
        return true
    }

    /** Checked source IDs apply only to asset evidence; chapter prose and accepted contributions remain separate. */
    fun toggleChapterEvidence(index: Int, evidenceId: String, checked: Boolean): Boolean {
        if (!editorReady() || !state.value.sourceReviewEnabled || state.value.composing || hasUnfinishedChapterDictation) return false
        val chapter = state.value.editableChapters.getOrNull(index) ?: return false
        val eligible = chapter.assetIds.flatMap { assetId ->
            state.value.draft?.items?.find { it.asset.id == assetId }?.evidence.orEmpty().map { it.id }
        }.toSet()
        if (evidenceId !in eligible) return false
        val currentIds = chapter.evidenceIds
        if ((evidenceId in currentIds) == checked) return true
        if (checked && currentIds.size >= 12) return false
        closeChapterDictation()
        invalidateTitleWork()
        titleRevision++
        val revised = if (checked) currentIds + evidenceId else currentIds - evidenceId
        val updated = immutable(state.value.editableChapters.mapIndexed { i, value ->
            if (i == index) value.copy(evidenceIds = immutable(revised)) else detachChapter(value)
        })
        mutable.value = state.value.copy(editableChapters = updated, reviewed = false, dirty = true,
            titleCandidates = emptyList())
        return true
    }

    /** Optional suggestion request. Results are discarded after any manual title edit or IME composition. */
    fun suggestTitles(): Boolean {
        if (!ensureCurrent() || state.value.status != StoryWorkspaceStoreStatus.EDITING || state.value.busy ||
            state.value.composing || state.value.titleCapabilities?.enabled != true || hasUnfinishedChapterDictation) return false
        val expected = bound ?: return false
        val draft = state.value.draft ?: return false
        val editedDraft = detachDraft(draft).copy(title = state.value.title,
            chapters = immutable(state.value.editableChapters.map(::detachChapter)))
        val capturedTitleRevision = titleRevision
        clearOperationOnly()
        val ticket = epoch
        operation = scope.launch {
            try {
                val candidates = repository.suggestTitles(editedDraft, state.value.sourceReviewEnabled) { current(expected, ticket) }
                if (current(expected, ticket) && capturedTitleRevision == titleRevision && !state.value.composing)
                    mutable.value = state.value.copy(titleCandidates = candidates.map(::detachTitle))
            } catch (_: CancellationException) { stale(ticket) }
            catch (_: Exception) {
                if (!current(expected, ticket)) stale(ticket)
            } finally { if (ticket == epoch) operation = null }
        }
        return true
    }

    fun editTitle(value: String): Boolean {
        if (!editorReady() || hasUnfinishedChapterDictation) return false
        invalidateTitleWork()
        titleRevision++
        val valid = validText(value, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false)
        mutable.value = state.value.copy(title = value, titleCandidates = emptyList(), reviewed = false,
            dirty = true, invalidInput = !valid || state.value.editableChapters.any { !validText(it.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) || !validText(it.narration, 6000, allowNewline = true) })
        return true
    }

    fun editChapterTitle(index: Int, value: String): Boolean {
        if (!editorReady() || hasUnfinishedChapterDictation) return false
        val chapters = state.value.editableChapters
        if (index !in chapters.indices) return false
        invalidateTitleWork()
        titleRevision++
        val updated = immutable(chapters.mapIndexed { i, chapter ->
            if (i == index) chapter.copy(title = value) else chapter
        }.map(::detachChapter))
        mutable.value = state.value.copy(editableChapters = updated, reviewed = false, dirty = true,
            titleCandidates = emptyList(), invalidInput = !validText(state.value.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) ||
                updated.any { !validText(it.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) || !validText(it.narration, 6000, allowNewline = true) })
        return true
    }

    fun editChapterNarration(index: Int, value: String): Boolean {
        if (!editorReady()) return false
        val chapters = state.value.editableChapters
        if (index !in chapters.indices) return false
        invalidateTitleWork()
        titleRevision++
        val updated = immutable(chapters.mapIndexed { i, chapter ->
            if (i == index) chapter.copy(narration = value) else chapter
        }.map(::detachChapter))
        mutable.value = state.value.copy(editableChapters = updated, reviewed = false, dirty = true,
            titleCandidates = emptyList(), invalidInput = !validText(state.value.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) ||
                updated.any { !validText(it.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) || !validText(it.narration, 6000, allowNewline = true) })
        return true
    }

    private fun editorReady() = editable() && state.value.status == StoryWorkspaceStoreStatus.EDITING && state.value.draft != null

    fun composition(active: Boolean) {
        if (!editorReady()) return
        if (active) invalidateTitleWork()
        mutable.value = state.value.copy(composing = active, reviewed = if (active) false else state.value.reviewed,
            titleCandidates = if (active) emptyList() else state.value.titleCandidates)
    }

    /** The UI uses this when it cannot commit a rejected field value into an edit callback. */
    fun invalidInput(active: Boolean) {
        if (!editorReady()) return
        mutable.value = state.value.copy(invalidInput = active, dirty = state.value.dirty || active,
            reviewed = if (active) false else state.value.reviewed)
    }

    fun adoptTitleCandidate(index: Int): Boolean {
        if (!editorReady() || state.value.composing || state.value.invalidInput) return false
        val candidate = state.value.titleCandidates.getOrNull(index) ?: return false
        invalidateTitleWork()
        titleRevision++
        mutable.value = state.value.copy(title = candidate.text, titleCandidates = emptyList(), reviewed = false, dirty = true)
        return true
    }

    fun confirmReviewed(value: Boolean): Boolean {
        if (!editorReady() || state.value.composing || state.value.invalidInput || hasUnfinishedChapterDictation) return false
        mutable.value = state.value.copy(reviewed = value)
        return true
    }

    fun save(): Boolean {
        if (!editorReady() || state.value.composing || state.value.invalidInput || !state.value.reviewed || hasUnfinishedChapterDictation) return false
        closeChapterDictation()
        val expected = bound ?: return false
        val draft = state.value.draft ?: return false
        pending = try {
            val chapters = immutable(state.value.editableChapters.map(::detachChapter))
            val mutationId = uuidSupplier().toString()
            val base = savedEditStory
            if (base == null) repository.freeze(detachDraft(draft), state.value.title, chapters, mutationId, true,
                state.value.sourceReviewEnabled) { current(expected) }
            else repository.freezeUpdate(base, savedEditReferences ?: return false, state.value.title, chapters,
                mutationId, true, state.value.sourceReviewEnabled,
                if (state.value.sourceReviewEnabled) ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1 else null) { current(expected) }
        }
        catch (_: CancellationException) { stale(epoch); return false }
        catch (failure: ApiFailure) {
            mutable.value = state.value.copy(invalidInput = failure.kind == FailureKind.INVALID_INPUT,
                reviewed = false, failureStatus = failure.status)
            return false
        }
        return submitPending()
    }

    fun retrySave(): Boolean = if (state.value.status == StoryWorkspaceStoreStatus.SAVE_UNCERTAIN) submitPending() else false

    private fun submitPending(): Boolean {
        val frozen = pending ?: return false
        val expected = bound ?: return false
        if (!current(expected) || state.value.busy || state.value.status !in
            setOf(StoryWorkspaceStoreStatus.EDITING, StoryWorkspaceStoreStatus.SAVE_UNCERTAIN)) return false
        clearOperationOnly()
        val ticket = epoch
        mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.SAVING, busy = true, hasPendingSave = true)
        operation = scope.launch {
            try {
                val saved = repository.save(frozen) { current(expected, ticket) }
                if (current(expected, ticket)) {
                    pending = null
                    val editBaseRevision = savedEditStory?.revision
                    mutable.value = StoryWorkspaceStoreState(status = StoryWorkspaceStoreStatus.SAVED,
                        selectedAssetIds = immutable(state.value.selectedAssetIds), theme = state.value.theme,
                        language = state.value.language, savedStory = detachSavedStory(saved),
                        savedStoryIsNewerThanEditBase = editBaseRevision != null && saved.revision > editBaseRevision + 1)
                }
            } catch (_: CancellationException) { stale(ticket) }
            catch (failure: ApiFailure) {
                if (!current(expected, ticket)) { stale(ticket); return@launch }
                val status = failure.status
                when {
                    status == 409 -> {
                        pending = null
                        mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.CONFLICT, busy = false,
                            hasPendingSave = false, failureStatus = status)
                    }
                    failure.kind in setOf(FailureKind.OFFLINE, FailureKind.TLS, FailureKind.INVALID_RESPONSE, FailureKind.TOO_LARGE) || status in 500..599 ->
                        mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, busy = false,
                            hasPendingSave = true, failureStatus = status)
                    else -> {
                        pending = null
                        mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.EDITING, busy = false,
                            hasPendingSave = false, reviewed = false, failureStatus = status,
                            invalidInput = failure.kind == FailureKind.INVALID_INPUT)
                    }
                }
            } catch (_: Exception) {
                if (current(expected, ticket)) mutable.value = state.value.copy(
                    status = StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, busy = false, hasPendingSave = true)
                else stale(ticket)
            } finally { if (ticket == epoch) operation = null }
        }
        return true
    }

    /** Dirty or pending work needs an explicit discard decision. Pending writes may already exist. */
    fun close(discard: Boolean = false): Boolean {
        if (hasUnfinishedChapterDictation && !discard) return false
        if (state.value.busy && !discard || state.value.hasUnfinishedWork && !discard) return false
        clear()
        return true
    }

    fun clear() {
        closeChapterDictation()
        epoch++
        operation?.cancel(); operation = null
        bound = null
        pending = null
        savedEditStory = null
        savedEditReferences = null
        titleRevision++
        clearRelated()
        mutable.value = StoryWorkspaceStoreState()
    }

    private fun clearOperationOnly() { epoch++; operation?.cancel(); operation = null }

    private fun stale(ticket: Long) {
        if (ticket == epoch) {
            val expected = bound
            if (expected != null && !sameBinding(snapshotBinding(), expected)) clear()
        }
    }

    private fun validText(value: String, maxBytes: Int, maxCodePoints: Int = Int.MAX_VALUE,
                          allowNewline: Boolean = false, allowBlank: Boolean = true): Boolean = try {
        val bytes = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value)).remaining()
        bytes <= maxBytes && value.codePointCount(0, value.length) <= maxCodePoints && (allowBlank || value.isNotBlank()) &&
            value.none { it == '\u0000' || it.isISOControl() && !(allowNewline && it in "\n\t") }
    } catch (_: Exception) { false }

    companion object {
        private val NEXT_DICTATION_SCOPE = AtomicLong(0)
        private const val MAX_ASSETS = 24
    }

    private fun detachDraft(value: ProtectedStoryWorkspaceDraft) = value.copy(
        items = immutable(value.items.map { item -> item.copy(asset = item.asset.copy(date_hint = item.asset.date_hint?.copy()),
            evidence = immutable(item.evidence.map { it.copy() })) }),
        chapters = immutable(value.chapters.map(::detachChapter)), questions = immutable(value.questions))

    private fun detachChapter(value: SavedMemoryStoryChapter) = value.copy(
        assetIds = immutable(value.assetIds), evidenceIds = immutable(value.evidenceIds))

    private fun detachTitle(value: ProtectedStoryWorkspaceTitle) = value.copy(sourceIds = immutable(value.sourceIds))

    private fun detachSavedStory(value: SavedMemoryStory) = value.copy(
        items = immutable(value.items.map { item -> item.copy(asset = item.asset.copy(date_hint = item.asset.date_hint?.copy()), evidence = immutable(item.evidence.map { it.copy() })) }),
        chapters = immutable(value.chapters.map(::detachChapter)), questions = immutable(value.questions))

    private fun invalidateTitleWork() {
        titleRevision++
        epoch++
        operation?.cancel(); operation = null
    }

    private fun <T> immutable(values: List<T>): List<T> = Collections.unmodifiableList(ArrayList(values))

}
