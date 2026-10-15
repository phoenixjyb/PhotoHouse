package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.Collections
import java.util.concurrent.atomic.AtomicLong
import java.util.UUID

enum class StoryWorkspaceStoreStatus {
    SELECTION, PREVIEWING, EDITING, SAVING, SAVE_UNCERTAIN, CONFLICT, SAVED, UNAVAILABLE,
}

enum class StoryGuideStep { FRAMES, WORDS, REVIEW }
enum class LocalStoryDraftStatus { UNAVAILABLE, UNKNOWN, EMPTY, AVAILABLE, SAVED, ERROR, SAVING, RESUMING }

/** Snapshot-bound local title choice derived only from wording a person authored. */
data class StoryChapterOpeningTitleCandidate internal constructor(
    val text: String,
    val chapterId: String,
    val chapterIndex: Int,
    val sourceNarration: String,
    val selectionRevision: String,
    val titleRevision: Long,
    val currentTitle: String,
    val selectedAssetIds: List<String>,
    val libraryId: String,
    val accountId: String?,
)

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
    val guideStep: StoryGuideStep? = null,
    val localDraftStatus: LocalStoryDraftStatus = LocalStoryDraftStatus.UNAVAILABLE,
    val localDraftRevision: Long? = null,
    val localDraftOccupiedSlots: Int? = null,
    val localDraftError: Boolean = false,
    val localDraftRequiresRecovery: Boolean = false,
    val localDraftCanDeleteUnreadable: Boolean = false,
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
    private val localDraftPersistence: StoryDraftPersistence? = null,
    private val now: () -> Long = System::currentTimeMillis,
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
    private var localDraftRecord: StoryDraftRecord? = null
    private var localDraftSlotOccupied = false
    private var localDraftAttached = false
    private var localDraftPublicationConfirmed = false
    private var localDraftUnreadableFingerprint: String? = null
    private var authoredTitle = false
    private val authoredChapterTitles = mutableSetOf<String>()
    private val authoredChapterNarrations = mutableSetOf<String>()
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
    private fun pendingRecoveryBlocksNewStory() = localDraftRecord?.pendingSave != null && !localDraftAttached

    /** Reads only this fresh account/library slot; errors remain visible and never erase bytes. */
    fun inspectLocalDraft(): Boolean {
        val persistence = localDraftPersistence ?: run {
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.UNAVAILABLE)
            return false
        }
        val scope = localDraftScope() ?: return false
        return try {
            val record = persistence.load(scope)
            localDraftRecord = record
            localDraftSlotOccupied = record != null
            localDraftUnreadableFingerprint = null
            localDraftPublicationConfirmed = false
            val slots = persistence.occupiedSlots()
            mutable.value = state.value.copy(localDraftStatus = if (record == null) LocalStoryDraftStatus.EMPTY else LocalStoryDraftStatus.AVAILABLE,
                localDraftRevision = record?.revision, localDraftOccupiedSlots = slots, localDraftError = false,
                localDraftCanDeleteUnreadable = false)
            mutable.value = state.value.copy(localDraftRequiresRecovery = record?.pendingSave != null)
            true
        } catch (_: Exception) {
            localDraftRecord = null
            localDraftSlotOccupied = true
            localDraftUnreadableFingerprint = runCatching { persistence.unreadableFingerprint(scope) }.getOrNull()
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true,
                localDraftCanDeleteUnreadable = localDraftUnreadableFingerprint != null)
            false
        }
    }

    /** Explicitly stores only authored text, selected IDs and grouping for a new story. */
    fun saveLocalDraft(replaceExisting: Boolean = false): Boolean {
        val persistence = localDraftPersistence ?: return false
        val live = state.value
        if (!ensureCurrent() || isSavedStoryEdit || live.status != StoryWorkspaceStoreStatus.EDITING || live.draft == null ||
            live.busy || live.composing || live.invalidInput || live.hasPendingSave || pending != null ||
            hasUnfinishedChapterDictation) return false
        closeChapterDictation()
        val scope = localDraftScope() ?: return false
        val previous = localDraftRecord ?: runCatching { persistence.load(scope) }.getOrNull()
        if (previous?.pendingSave != null && !localDraftAttached) {
            localDraftRecord = previous
            localDraftSlotOccupied = true
            mutable.value = live.copy(localDraftStatus = LocalStoryDraftStatus.AVAILABLE,
                localDraftRevision = previous.revision, localDraftRequiresRecovery = true, localDraftError = false)
            return false
        }
        val replacing = previous != null && !localDraftAttached
        if (replacing && !replaceExisting) {
            localDraftRecord = previous
            localDraftSlotOccupied = true
            mutable.value = live.copy(localDraftStatus = LocalStoryDraftStatus.AVAILABLE,
                localDraftRevision = requireNotNull(previous).revision, localDraftError = false)
            return false
        }
        val timestamp = now().coerceAtLeast(1L)
        val recordId = previous?.takeIf { !replacing }?.recordId ?: UUID.randomUUID().toString()
        val next = StoryDraftRecord(
            scope = scope, recordId = recordId, revision = (previous?.revision ?: 0L) + 1L,
            createdAtEpochMillis = previous?.takeIf { !replacing }?.createdAtEpochMillis ?: timestamp,
            updatedAtEpochMillis = timestamp,
            selectionRevision = live.draft.selectionRevision,
            selectedAssetIds = live.selectedAssetIds.toList(), theme = live.theme, language = live.language,
            title = if (authoredTitle) live.title else "", titleAuthored = authoredTitle,
            chapters = live.editableChapters.map { chapter -> StoryDraftChapter(chapter.id,
                if (chapter.id in authoredChapterTitles) chapter.title else "", chapter.id in authoredChapterTitles,
                if (chapter.id in authoredChapterNarrations) chapter.narration else "", chapter.id in authoredChapterNarrations,
                chapter.assetIds.toList(), if (live.sourceReviewEnabled) chapter.evidenceIds.toList() else emptyList()) },
            sourceReviewEnabled = live.sourceReviewEnabled, guideMode = live.guideStep != null,
            guideStep = live.guideStep?.name,
        )
        return try {
            mutable.value = live.copy(localDraftStatus = LocalStoryDraftStatus.SAVING, localDraftError = false)
            val written = persistence.write(next, previous?.revision, previous?.recordId)
            localDraftRecord = written
            localDraftSlotOccupied = true
            localDraftAttached = true
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.SAVED,
                localDraftRevision = written.revision, localDraftOccupiedSlots = runCatching { persistence.occupiedSlots() }.getOrNull(),
                localDraftError = false, localDraftRequiresRecovery = written.pendingSave != null)
            true
        } catch (_: Exception) {
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true)
            false
        }
    }

    /** Freshly previews every selected asset before any stored wording is restored to the editor. */
    fun resumeLocalDraft(): Boolean {
        val persistence = localDraftPersistence ?: return false
        if (!ensureCurrent() || isSavedStoryEdit || state.value.status != StoryWorkspaceStoreStatus.SELECTION ||
            state.value.busy || state.value.hasPendingSave || state.value.composing || hasUnfinishedChapterDictation) return false
        val scope = localDraftScope() ?: return false
        val record = try { persistence.load(scope) } catch (_: Exception) {
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true)
            return false
        } ?: run {
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.EMPTY, localDraftError = false)
            return false
        }
        if (!validSavedDraft(record, scope)) {
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true)
            return false
        }
        val expected = snapshotBinding() ?: return false
        val ticket = epoch + 1
        closeChapterDictation()
        operation?.cancel(); operation = null
        relatedOperation?.cancel(); relatedOperation = null
        epoch = ticket
        bound = expected
        localDraftRecord = record
        localDraftSlotOccupied = true
        pending = null
        val selected = immutable(record.selectedAssetIds)
        mutable.value = StoryWorkspaceStoreState(status = StoryWorkspaceStoreStatus.PREVIEWING,
            selectedAssetIds = selected, theme = record.theme, language = record.language, busy = true,
            dirty = true, localDraftStatus = LocalStoryDraftStatus.RESUMING, localDraftRevision = record.revision,
            localDraftRequiresRecovery = record.pendingSave != null)
        operation = scopeCoroutineLaunch(expected, ticket, record)
        return operation != null
    }

    /** Deletes a readable slot only by its observed record ID and revision. */
    fun deleteLocalDraft(): Boolean {
        val persistence = localDraftPersistence ?: return false
        val scope = localDraftScope() ?: return false
        return try {
            val observed = localDraftRecord ?: return false
            val record = persistence.load(scope) ?: run {
                localDraftPublicationConfirmed = false
                inspectLocalDraft()
                return false
            }
            if (observed.scope != scope || record.scope != scope ||
                observed.recordId != record.recordId || observed.revision != record.revision) {
                localDraftPublicationConfirmed = false
                inspectLocalDraft()
                return false
            }
            if (record.pendingSave != null && !localDraftPublicationConfirmed) return false
            val deleted = persistence.delete(scope, record.recordId, record.revision)
            if (deleted) {
                localDraftRecord = null
                localDraftSlotOccupied = false
                localDraftAttached = false
                localDraftPublicationConfirmed = false
                localDraftUnreadableFingerprint = null
                mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.EMPTY,
                    localDraftRevision = null, localDraftError = false, localDraftRequiresRecovery = false,
                    localDraftCanDeleteUnreadable = false)
            }
            deleted
        } catch (_: Exception) {
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true)
            false
        }
    }

    /** Explicit corrupt-slot removal, bound to the fingerprint seen during inspection. */
    fun deleteUnreadableLocalDraft(): Boolean {
        val persistence = localDraftPersistence ?: return false
        val scope = localDraftScope() ?: return false
        val fingerprint = localDraftUnreadableFingerprint ?: return false
        if (state.value.localDraftStatus != LocalStoryDraftStatus.ERROR) return false
        return try {
            val deleted = persistence.deleteUnreadable(scope, fingerprint)
            if (deleted) {
                localDraftRecord = null
                localDraftSlotOccupied = false
                localDraftAttached = false
                localDraftUnreadableFingerprint = null
                mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.EMPTY,
                    localDraftRevision = null, localDraftError = false, localDraftRequiresRecovery = false,
                    localDraftCanDeleteUnreadable = false)
            } else {
                inspectLocalDraft()
            }
            deleted
        } catch (_: Exception) {
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true,
                localDraftCanDeleteUnreadable = false)
            false
        }
    }

    private fun localDraftScope(): StoryDraftScope? {
        val account = currentAccount()?.takeIf { it.isNotBlank() } ?: return null
        val library = snapshotBinding()?.libraryId ?: return null
        return StoryDraftScope(account, library)
    }

    private fun validSavedDraft(record: StoryDraftRecord, expectedScope: StoryDraftScope): Boolean =
        record.scope == expectedScope && runCatching { StoryDraftRecordCodec.validate(record) }.isSuccess

    private fun PendingGroupedStorySave.bodyMutationId(): String =
        Json.parseToJsonElement(body).jsonObject.getValue("mutation_id").jsonPrimitive.content

    private fun scopeCoroutineLaunch(expected: MemoryCommunityBinding, ticket: Long, record: StoryDraftRecord): Job =
        scope.launch {
            try {
                val fresh = repository.preview(record.selectedAssetIds, record.theme, record.language, "") { current(expected, ticket) }
                val detached = detachDraft(fresh)
                if (record.sourceReviewEnabled) {
                    val capabilities = repository.sourceCapabilities { current(expected, ticket) }
                    if (capabilities?.sourcePolicy != ProtectedStoryWorkspaceWire.CHAPTER_SOURCES_V1)
                        throw ApiFailure(FailureKind.INVALID_RESPONSE)
                }
                if (!current(expected, ticket)) return@launch
                if (detached.items.map { it.asset.id } != record.selectedAssetIds ||
                    record.chapters.flatMap { it.assetIds } != record.selectedAssetIds ||
                    record.chapters.size > MAX_CHAPTERS ||
                    !record.sourceReviewEnabled && detached.chapters.map { it.id to it.assetIds } !=
                        record.chapters.map { it.id to it.assetIds }) throw ApiFailure(FailureKind.INVALID_RESPONSE)
                val freshByAsset = detached.items.associate { it.asset.id to it.evidence.map(MemoryStoryEvidence::id).toSet() }
                val restoredChapters = record.chapters.map { saved ->
                    val eligible = saved.assetIds.flatMap { freshByAsset[it].orEmpty() }.toSet()
                    saved.copy(sourceIds = saved.sourceIds.filter { it in eligible })
                }
                val sourceChanged = restoredChapters.zip(record.chapters).any { (freshChapter, old) -> freshChapter.sourceIds != old.sourceIds }
                val changed = detached.selectionRevision != record.selectionRevision || sourceChanged
                val restored = detached.copy(chapters = immutable(restoredChapters.map { chapter ->
                    val freshChapter = detached.chapters.firstOrNull { it.id == chapter.id }
                        ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                    val savedChapter = record.chapters.first { it.id == chapter.id }
                    freshChapter.copy(title = if (savedChapter.titleAuthored) chapter.title else freshChapter.title,
                        narration = when {
                            savedChapter.narrationAuthored -> chapter.narration
                            record.guideMode -> ""
                            else -> freshChapter.narration
                        },
                        assetIds = immutable(chapter.assetIds), evidenceIds = immutable(chapter.sourceIds))
                }))
                authoredTitle = record.titleAuthored
                authoredChapterTitles.clear(); authoredChapterTitles.addAll(record.chapters.filter { it.titleAuthored }.map { it.id })
                authoredChapterNarrations.clear(); authoredChapterNarrations.addAll(record.chapters.filter { it.narrationAuthored }.map { it.id })
                val restoredPending = record.pendingSave?.let { pendingSave ->
                    if (pendingSave.assetIds != record.selectedAssetIds)
                        throw ApiFailure(FailureKind.INVALID_RESPONSE)
                    PendingGroupedStorySave(expected, pendingSave.body, pendingSave.assetIds,
                        pendingSave.sourceReview, targetStoryId = null, baseRevision = 0, contributionReferences = false)
                }
                pending = restoredPending
                localDraftAttached = true
                mutable.value = StoryWorkspaceStoreState(
                    status = if (restoredPending == null) StoryWorkspaceStoreStatus.EDITING else StoryWorkspaceStoreStatus.SAVE_UNCERTAIN,
                    selectedAssetIds = immutable(record.selectedAssetIds), theme = record.theme, language = record.language,
                    title = if (record.titleAuthored) record.title else detached.title, draft = restored,
                    editableChapters = immutable(restored.chapters.map(::detachChapter)),
                    sourceReviewEnabled = record.sourceReviewEnabled, sourceCapabilitiesChecked = record.sourceReviewEnabled,
                    reviewed = false, sourcesReloaded = changed, dirty = true, hasPendingSave = restoredPending != null,
                    invalidInput = !validText(if (record.titleAuthored) record.title else detached.title, 640,
                        maxCodePoints = 160, allowNewline = false, allowBlank = false) || restored.chapters.any {
                        !validText(it.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) ||
                            !validText(it.narration, 6000, allowNewline = true)
                    },
                    guideStep = record.guideStep?.let { runCatching { StoryGuideStep.valueOf(it) }.getOrNull() }
                        ?.takeIf { record.guideMode },
                    localDraftStatus = LocalStoryDraftStatus.SAVED, localDraftRevision = record.revision,
                    localDraftRequiresRecovery = restoredPending != null,
                )
            } catch (_: CancellationException) { stale(ticket) }
            catch (_: Exception) {
                if (current(expected, ticket)) mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.UNAVAILABLE,
                    busy = false, localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true)
                else stale(ticket)
            } finally { if (ticket == epoch) operation = null }
        }

    /** Starts the optional first-story path for a fresh, currently bound selection. */
    fun startGuide(): Boolean {
        if (!ensureCurrent() || isSavedStoryEdit || state.value.status != StoryWorkspaceStoreStatus.SELECTION ||
            state.value.draft != null || state.value.busy || state.value.hasPendingSave || pending != null || state.value.composing ||
            hasUnfinishedChapterDictation || state.value.guideStep != null || pendingRecoveryBlocksNewStory()) return false
        val expected = snapshotBinding() ?: return false
        bound = expected
        mutable.value = state.value.copy(guideStep = StoryGuideStep.FRAMES)
        return true
    }

    /** Advances one guide step, requesting the existing outline preview only when needed. */
    fun continueGuide(): Boolean {
        if (!guideActionReady()) return false
        val live = state.value
        when (live.guideStep) {
            StoryGuideStep.FRAMES -> {
                if (live.status != StoryWorkspaceStoreStatus.SELECTION || live.selectedAssetIds.isEmpty() ||
                    live.selectedAssetIds.size > MAX_ASSETS) return false
                val draft = live.draft
                val matchingDraft = draft != null && draft.libraryId == snapshotBinding()?.libraryId &&
                    draft.items.map { it.asset.id } == live.selectedAssetIds && draft.theme == live.theme &&
                    draft.language == live.language && live.editableChapters.map { it.id to it.assetIds } ==
                    draft.chapters.map { it.id to it.assetIds }
                if (matchingDraft) {
                    mutable.value = live.copy(status = StoryWorkspaceStoreStatus.EDITING,
                        guideStep = StoryGuideStep.WORDS, reviewed = false, busy = false)
                    return true
                }
                return preview()
            }
            StoryGuideStep.WORDS -> {
                if (live.status != StoryWorkspaceStoreStatus.EDITING || live.draft == null ||
                    !guideWordsAreValid(live) || live.editableChapters.none { it.narration.isNotBlank() }) return false
                mutable.value = live.copy(guideStep = StoryGuideStep.REVIEW, reviewed = false)
                return true
            }
            else -> return false
        }
    }

    /** Moves back without dropping selected moments, outline data or edited wording. */
    fun backGuide(): Boolean {
        if (!guideActionReady()) return false
        val live = state.value
        when (live.guideStep) {
            StoryGuideStep.REVIEW -> {
                if (live.status != StoryWorkspaceStoreStatus.EDITING || live.draft == null) return false
                mutable.value = live.copy(guideStep = StoryGuideStep.WORDS, reviewed = false)
                return true
            }
            StoryGuideStep.WORDS -> {
                if (live.status != StoryWorkspaceStoreStatus.EDITING || live.draft == null) return false
                mutable.value = live.copy(status = StoryWorkspaceStoreStatus.SELECTION,
                    guideStep = StoryGuideStep.FRAMES, reviewed = false)
                return true
            }
            else -> return false
        }
    }

    /** Drops retained guide wording only after the caller's explicit change-moments confirmation. */
    fun discardGuideDraft(): Boolean {
        if (!guideActionReady()) return false
        val live = state.value
        if (isSavedStoryEdit || live.guideStep != StoryGuideStep.FRAMES ||
            live.status != StoryWorkspaceStoreStatus.SELECTION || live.draft == null) return false
        invalidatePreview()
        mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.SELECTION,
            draft = null, editableChapters = emptyList(), title = "", titleCandidates = emptyList(),
            reviewed = false, sourcesReloaded = false, composing = false, invalidInput = false,
            dirty = state.value.selectedAssetIds.isNotEmpty(), failureStatus = null,
            sourceCapabilities = null, sourceCapabilitiesChecked = false, sourceReviewEnabled = false,
            guideStep = StoryGuideStep.FRAMES)
        return true
    }

    /** Leaves the staged guide while preserving all current editor content. */
    fun exitGuide(): Boolean {
        if (!guideActionReady()) return false
        val live = state.value
        val nextStatus = if (live.status == StoryWorkspaceStoreStatus.SELECTION && live.draft != null)
            StoryWorkspaceStoreStatus.EDITING else live.status
        mutable.value = live.copy(status = nextStatus, guideStep = null)
        return true
    }

    private fun guideActionReady(): Boolean = ensureCurrent() && state.value.guideStep != null &&
        !state.value.busy && !state.value.hasPendingSave && pending == null && !state.value.composing &&
        !hasUnfinishedChapterDictation

    private fun guideWordsAreValid(value: StoryWorkspaceStoreState): Boolean =
        !value.invalidInput && validText(value.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) &&
            value.editableChapters.all { chapter ->
                validText(chapter.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) &&
                    validText(chapter.narration, 6000, allowNewline = true)
            }

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
        val inserted = helper.insertTranscript { transcript ->
            val chapter = state.value.editableChapters.getOrNull(index)?.takeIf { it.id == activeDictationChapterId }
                ?: return@insertTranscript false
            val joined = if (chapter.narration.isEmpty()) transcript else chapter.narration + "\n\n" + transcript
            if (!validText(joined, 6000, allowNewline = true)) return@insertTranscript false
            editChapterNarration(index, joined)
        }
        // The StateFlow collector may run later; the next explicit action must see
        // that the reviewed transcript has already been consumed.
        mutableDictationUnfinished.value = helper.hasUnfinishedInput
        return inserted
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
        if (!editable() || hasUnfinishedChapterDictation || isSavedStoryEdit || pendingRecoveryBlocksNewStory()) return false
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

    /** Atomically seeds an unsaved editor from one freshly revalidated album choice. */
    fun seedSelectionFromAlbum(
        assetIds: List<String>,
        albumTheme: String,
        expectedSelectedIds: List<String>,
        confirmedReplace: Boolean,
    ): Boolean {
        if (!editable() || isSavedStoryEdit || pendingRecoveryBlocksNewStory() || state.value.status != StoryWorkspaceStoreStatus.SELECTION ||
            state.value.draft != null || state.value.hasPendingSave || pending != null || state.value.composing ||
            hasUnfinishedChapterDictation || chapterDictationBinding != null) return false
        val currentIds = state.value.selectedAssetIds
        if (currentIds != expectedSelectedIds || currentIds.isNotEmpty() && !confirmedReplace) return false
        if (assetIds.isEmpty() || assetIds.size > 60 || assetIds.distinct().size != assetIds.size ||
            assetIds.any { id -> id.toLongOrNull()?.let { it > 0 && it.toString() == id } != true }) return false
        if (albumTheme !in ALBUM_THEMES) return false

        val chosen = immutable(assetIds.take(MAX_ASSETS))
        val theme = if (albumTheme in SAVED_MEMORY_STORY_THEMES && albumTheme != "custom") albumTheme else "everyday"
        invalidatePreview()
        mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.SELECTION,
            selectedAssetIds = chosen, theme = theme, draft = null, editableChapters = emptyList(), title = "",
            reviewed = false, sourcesReloaded = false, dirty = chosen.isNotEmpty(), titleCandidates = emptyList(),
            relatedCandidates = emptyList(), relatedBusy = false, relatedHasMore = false, relatedFailure = false,
            failureStatus = null, sourceReviewEnabled = false, sourceCapabilities = null, sourceCapabilitiesChecked = false)
        return true
    }

    fun setTheme(value: String, discardDraft: Boolean = false): Boolean {
        if (!editable() || hasUnfinishedChapterDictation || isSavedStoryEdit || pendingRecoveryBlocksNewStory() || value !in SAVED_MEMORY_STORY_THEMES) return false
        if (state.value.theme == value) return true
        if (state.value.draft != null && !discardDraft) return false
        invalidatePreview()
        mutable.value = state.value.copy(theme = value, status = StoryWorkspaceStoreStatus.SELECTION,
            draft = null, editableChapters = emptyList(), title = "", titleCandidates = emptyList(),
            reviewed = false, sourcesReloaded = false, dirty = true, failureStatus = null)
        return true
    }

    fun setLanguage(value: String, discardDraft: Boolean = false): Boolean {
        if (!editable() || hasUnfinishedChapterDictation || isSavedStoryEdit || pendingRecoveryBlocksNewStory() || value !in setOf("zh", "en")) return false
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
        if (!editable() || isSavedStoryEdit || pendingRecoveryBlocksNewStory() || hasUnfinishedChapterDictation ||
            state.value.selectedAssetIds.isEmpty() || state.value.selectedAssetIds.size > MAX_ASSETS) return false
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
        if (!reloadSources) {
            authoredTitle = false
            authoredChapterTitles.clear()
            authoredChapterNarrations.clear()
        }
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
                        val carryManualSourceLayout = previous.sourceReviewEnabled && savedEditStory == null
                        val carriedChapters = if (carryManualSourceLayout) {
                            val layout = oldChapters.map { it.id to it.assetIds }
                            if (before.chapters.map { it.id to it.assetIds } != layout ||
                                oldChapters.isEmpty() || oldChapters.size > MAX_CHAPTERS ||
                                oldChapters.map { it.id } != (1..oldChapters.size).map { "chapter-$it" } ||
                                oldChapters.any { it.assetIds.isEmpty() || it.assetIds.size > MAX_ASSETS_PER_CHAPTER } ||
                                oldChapters.flatMap { it.assetIds } != ids || detached.items.map { it.asset.id } != ids)
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            oldChapters.map { old ->
                                val available = old.assetIds.flatMap { id -> detached.items.find { it.asset.id == id }
                                    ?.evidence.orEmpty().map { it.id } }.toSet()
                                old.copy(evidenceIds = immutable(old.evidenceIds.filter { it in available }))
                            }
                        } else {
                            if (before.chapters.map { it.id to it.assetIds } != detached.chapters.map { it.id to it.assetIds } ||
                                oldChapters.map { it.id to it.assetIds } != detached.chapters.map { it.id to it.assetIds })
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val prose = oldChapters.associateBy { it.id }
                            detached.chapters.map { fresh ->
                                val old = prose[fresh.id] ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                val available = fresh.assetIds.flatMap { id -> detached.items.find { it.asset.id == id }
                                    ?.evidence.orEmpty().map { it.id } }.toSet()
                                val checked = old.evidenceIds.filter { it in available }
                                fresh.copy(title = old.title, narration = old.narration,
                                    evidenceIds = if (previous.sourceReviewEnabled) checked else fresh.evidenceIds)
                            }
                        }
                        val carried = detached.copy(title = previous.title, chapters = immutable(carriedChapters))
                        mutable.value = previous.copy(status = StoryWorkspaceStoreStatus.EDITING, busy = false,
                            draft = carried, editableChapters = immutable(carried.chapters.map(::detachChapter)),
                            guideStep = if (previous.guideStep != null) StoryGuideStep.WORDS else null,
                            reviewed = false, sourcesReloaded = true, titleCandidates = emptyList(), failureStatus = null)
                    } else {
                        val guideDraft = if (previous.guideStep == StoryGuideStep.FRAMES) detached.copy(
                            chapters = immutable(detached.chapters.map { it.copy(narration = "") })) else detached
                        mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.EDITING, busy = false,
                            guideStep = if (previous.guideStep == StoryGuideStep.FRAMES) StoryGuideStep.WORDS else previous.guideStep,
                            draft = guideDraft, editableChapters = immutable(guideDraft.chapters.map(::detachChapter)), title = guideDraft.title,
                            reviewed = false, dirty = false,
                            invalidInput = !validText(guideDraft.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) ||
                                guideDraft.chapters.any { !validText(it.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) ||
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

    /** Splits one unsaved reviewed-source chapter after the requested number of leading assets. */
    fun splitChapter(index: Int, firstPartAssetCount: Int, expectedAssetIds: List<String>): Boolean {
        if (!canRegroupNewReviewedDraft()) return false
        val current = state.value
        val draft = current.draft ?: return false
        val chapters = current.editableChapters
        val source = chapters.getOrNull(index) ?: return false
        val expected = expectedAssetIds.toList()
        if (expected != source.assetIds || chapters.size >= MAX_CHAPTERS || source.assetIds.size < 2 ||
            firstPartAssetCount !in 1 until source.assetIds.size) return false

        val firstAssets = source.assetIds.take(firstPartAssetCount)
        val secondAssets = source.assetIds.drop(firstPartAssetCount)
        val evidenceByAsset = draft.items.associate { it.asset.id to it.evidence.map { evidence -> evidence.id }.toSet() }
        val firstEligible = firstAssets.flatMap { evidenceByAsset[it].orEmpty() }.toSet()
        val secondEligible = secondAssets.flatMap { evidenceByAsset[it].orEmpty() }.toSet()
        val firstEvidence = source.evidenceIds.filter { it in firstEligible }
        val secondEvidence = source.evidenceIds.filter { it !in firstEligible && it in secondEligible }
        if (firstEvidence.size + secondEvidence.size != source.evidenceIds.size) return false

        val split = listOf(
            source.copy(assetIds = firstAssets, evidenceIds = firstEvidence),
            source.copy(assetIds = secondAssets, narration = "", evidenceIds = secondEvidence),
        )
        val updated = chapters.toMutableList().apply { removeAt(index); addAll(index, split) }
            .mapIndexed { chapterIndex, chapter -> chapter.copy(id = "chapter-" + (chapterIndex + 1)) }
        return commitRegroupedChapters(draft, updated, current.selectedAssetIds)
    }

    /** Merges one chapter with its next neighbor without discarding authored text or evidence. */
    fun mergeChapterWithNext(
        index: Int,
        expectedChapterAssetIds: List<String>,
        expectedNextAssetIds: List<String>,
    ): Boolean {
        if (!canRegroupNewReviewedDraft()) return false
        val current = state.value
        val draft = current.draft ?: return false
        val chapters = current.editableChapters
        if (index !in 0 until chapters.lastIndex) return false
        val first = chapters[index]
        val second = chapters[index + 1]
        if (expectedChapterAssetIds.toList() != first.assetIds ||
            expectedNextAssetIds.toList() != second.assetIds ||
            first.assetIds.size + second.assetIds.size !in 1..MAX_ASSETS_PER_CHAPTER) return false

        val title = if (first.title == second.title) first.title else first.title + " / " + second.title
        val narration = when {
            first.narration.isEmpty() -> second.narration
            second.narration.isEmpty() -> first.narration
            else -> first.narration + "\n\n" + second.narration
        }
        val evidence = (first.evidenceIds + second.evidenceIds).distinct()
        if (!validText(title, 640, maxCodePoints = 160, allowBlank = false) ||
            !validText(narration, 6000, allowNewline = true) || evidence.size > MAX_EVIDENCE_PER_CHAPTER) return false
        val mergedAssets = first.assetIds + second.assetIds
        val eligibleEvidence = mergedAssets.flatMap { assetId ->
            draft.items.find { it.asset.id == assetId }?.evidence.orEmpty().map { it.id }
        }.toSet()
        if (evidence.any { it !in eligibleEvidence }) return false

        val merged = first.copy(title = title, narration = narration, assetIds = mergedAssets, evidenceIds = evidence)
        val updated = chapters.toMutableList().apply { removeAt(index + 1); set(index, merged) }
            .mapIndexed { chapterIndex, chapter -> chapter.copy(id = "chapter-" + (chapterIndex + 1)) }
        return commitRegroupedChapters(draft, updated, current.selectedAssetIds)
    }

    private fun canRegroupNewReviewedDraft(): Boolean =
        editorReady() && state.value.sourceReviewEnabled && savedEditStory == null && !state.value.composing &&
            !state.value.invalidInput && !state.value.hasPendingSave && pending == null && !hasUnfinishedChapterDictation &&
            chapterDictationBinding == null

    private fun commitRegroupedChapters(
        originalDraft: ProtectedStoryWorkspaceDraft,
        chapters: List<SavedMemoryStoryChapter>,
        selectedAssetIds: List<String>,
    ): Boolean {
        if (chapters.isEmpty() || chapters.size > MAX_CHAPTERS ||
            chapters.map { it.id } != (1..chapters.size).map { "chapter-$it" } ||
            chapters.any { it.assetIds.isEmpty() || it.assetIds.size > MAX_ASSETS_PER_CHAPTER } ||
            chapters.flatMap { it.assetIds } != selectedAssetIds ||
            selectedAssetIds != originalDraft.items.map { it.asset.id } ||
            chapters.any { !validText(it.title, 640, maxCodePoints = 160, allowBlank = false) ||
                !validText(it.narration, 6000, allowNewline = true) ||
                it.evidenceIds.size > MAX_EVIDENCE_PER_CHAPTER || it.evidenceIds.distinct().size != it.evidenceIds.size }) return false

        closeChapterDictation()
        invalidateTitleWork()
        titleRevision++
        val prior = state.value.editableChapters
        val priorTitleIds = authoredChapterTitles.toSet()
        val priorNarrationIds = authoredChapterNarrations.toSet()
        val authoredTitles = prior.filter { it.id in priorTitleIds }.map { it.title }.toSet()
        val authoredWords = prior.filter { it.id in priorNarrationIds }.map { it.narration }.toSet()
        val frozen = immutable(chapters.map(::detachChapter))
        authoredChapterTitles.clear()
        authoredChapterNarrations.clear()
        frozen.forEach { chapter ->
            if (chapter.title in authoredTitles || prior.any { it.id == chapter.id && it.id in priorTitleIds })
                authoredChapterTitles.add(chapter.id)
            if (chapter.narration in authoredWords || prior.any { it.id == chapter.id && it.id in priorNarrationIds })
                authoredChapterNarrations.add(chapter.id)
        }
        val updatedDraft = detachDraft(originalDraft).copy(chapters = frozen)
        mutable.value = state.value.copy(draft = updatedDraft, editableChapters = frozen,
            reviewed = false, dirty = true, titleCandidates = emptyList(), invalidInput = false)
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
        authoredTitle = true
        val valid = validText(value, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false)
        mutable.value = state.value.copy(title = value, titleCandidates = emptyList(), reviewed = false,
            dirty = true, invalidInput = !valid || state.value.editableChapters.any { !validText(it.title, 640, maxCodePoints = 160, allowNewline = false, allowBlank = false) || !validText(it.narration, 6000, allowNewline = true) })
        return true
    }

    /** Returns a local, explicit option based on the first authored chapter narration. */
    fun chapterOpeningTitleCandidate(): StoryChapterOpeningTitleCandidate? {
        val live = state.value
        if (!editorReady() || savedEditStory != null || live.invalidInput || live.draft == null) return null
        val (index, chapter) = live.editableChapters.withIndex().firstOrNull { (_, item) ->
            item.id in authoredChapterNarrations && item.narration.isNotBlank()
        } ?: return null
        val openingLine = chapter.narration.split(Regex("\\r\\n|\\r|\\n")).firstOrNull { it.isNotBlank() }
            ?: return null
        if (openingLine.any { char ->
                char.isISOControl() || char == '\u2028' || char == '\u2029' ||
                    char in '\u202a'..'\u202e' || char in '\u2066'..'\u2069'
            }) return null
        val line = openingLine.trim().takeIf { it.isNotEmpty() } ?: return null
        val end = line.indices.firstOrNull { offset ->
            when (line[offset]) {
                '。', '！', '？', '!', '?' -> true
                '.' -> offset == line.lastIndex || line[offset + 1].isWhitespace()
                else -> false
            }
        }?.plus(1) ?: line.length
        val candidateText = line.substring(0, end).trim()
        if (!validText(candidateText, maxBytes = 640, maxCodePoints = 80,
                allowNewline = false, allowBlank = false)) return null
        val draft = live.draft
        return StoryChapterOpeningTitleCandidate(
            text = candidateText, chapterId = chapter.id, chapterIndex = index,
            sourceNarration = chapter.narration, selectionRevision = draft.selectionRevision,
            titleRevision = titleRevision, currentTitle = live.title,
            selectedAssetIds = immutable(live.selectedAssetIds), libraryId = draft.libraryId,
            accountId = currentAccount(),
        )
    }

    /** Applies only the exact currently displayed local suggestion, after all editor guards pass. */
    fun adoptChapterOpeningTitle(candidate: StoryChapterOpeningTitleCandidate): Boolean {
        if (!ensureCurrent() || !editorReady() || savedEditStory != null || state.value.savedStory != null ||
            state.value.composing || state.value.invalidInput || state.value.hasPendingSave || pending != null ||
            hasUnfinishedChapterDictation) return false
        if (chapterOpeningTitleCandidate() != candidate) return false
        return editTitle(candidate.text)
    }

    fun editChapterTitle(index: Int, value: String): Boolean {
        if (!editorReady() || hasUnfinishedChapterDictation) return false
        val chapters = state.value.editableChapters
        if (index !in chapters.indices) return false
        invalidateTitleWork()
        titleRevision++
        authoredChapterTitles.add(chapters[index].id)
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
        authoredChapterNarrations.add(chapters[index].id)
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
        authoredTitle = true
        mutable.value = state.value.copy(title = candidate.text, titleCandidates = emptyList(), reviewed = false, dirty = true)
        return true
    }

    fun confirmReviewed(value: Boolean): Boolean {
        if (!editorReady() || state.value.composing || state.value.invalidInput || hasUnfinishedChapterDictation) return false
        if (state.value.guideStep != null && state.value.guideStep != StoryGuideStep.REVIEW) return false
        mutable.value = state.value.copy(reviewed = value)
        return true
    }

    fun save(): Boolean {
        if (!editorReady() || state.value.composing || state.value.invalidInput || !state.value.reviewed || hasUnfinishedChapterDictation) return false
        if (localDraftRecord?.pendingSave != null && !localDraftAttached) return false
        if (state.value.guideStep != null && (state.value.guideStep != StoryGuideStep.REVIEW ||
                !guideWordsAreValid(state.value) || state.value.editableChapters.none { it.narration.isNotBlank() })) return false
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
        if (localDraftRecord != null && localDraftAttached) {
            val before = requireNotNull(localDraftRecord)
            val savedRequest = requireNotNull(pending)
            val currentState = state.value
            val currentDraft = requireNotNull(currentState.draft)
            val journal = before.copy(revision = before.revision + 1, updatedAtEpochMillis = now().coerceAtLeast(1L),
                selectionRevision = currentDraft.selectionRevision, selectedAssetIds = currentState.selectedAssetIds.toList(),
                theme = currentState.theme, language = currentState.language,
                title = if (authoredTitle) currentState.title else "", titleAuthored = authoredTitle,
                chapters = currentState.editableChapters.map { chapter -> StoryDraftChapter(chapter.id,
                    if (chapter.id in authoredChapterTitles) chapter.title else "", chapter.id in authoredChapterTitles,
                    if (chapter.id in authoredChapterNarrations) chapter.narration else "", chapter.id in authoredChapterNarrations,
                    chapter.assetIds.toList(), if (currentState.sourceReviewEnabled) chapter.evidenceIds.toList() else emptyList()) },
                sourceReviewEnabled = currentState.sourceReviewEnabled, guideMode = currentState.guideStep != null,
                guideStep = currentState.guideStep?.name,
                pendingSave = StoryDraftPendingSave(savedRequest.body, savedRequest.bodyMutationId(),
                    savedRequest.sourceReview, savedRequest.assetIds))
            try {
                localDraftRecord = requireNotNull(localDraftPersistence).write(journal, before.revision, before.recordId)
            } catch (_: Exception) {
                pending = null
                mutable.value = state.value.copy(status = StoryWorkspaceStoreStatus.EDITING, busy = false,
                    hasPendingSave = false, localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true)
                return false
            }
            mutable.value = state.value.copy(localDraftRevision = localDraftRecord?.revision,
                localDraftStatus = LocalStoryDraftStatus.SAVED, localDraftError = false, localDraftRequiresRecovery = true)
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
                    val draftRemoved = clearPublishedLocalDraft()
                    val editBaseRevision = savedEditStory?.revision
                    mutable.value = StoryWorkspaceStoreState(status = StoryWorkspaceStoreStatus.SAVED,
                        selectedAssetIds = immutable(state.value.selectedAssetIds), theme = state.value.theme,
                        language = state.value.language, savedStory = detachSavedStory(saved),
                        savedStoryIsNewerThanEditBase = editBaseRevision != null && saved.revision > editBaseRevision + 1,
                        localDraftStatus = when {
                            !draftRemoved -> LocalStoryDraftStatus.ERROR
                            localDraftRecord != null -> LocalStoryDraftStatus.AVAILABLE
                            else -> LocalStoryDraftStatus.EMPTY
                        },
                        localDraftRevision = localDraftRecord?.revision, localDraftError = !draftRemoved,
                        localDraftRequiresRecovery = !draftRemoved)
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
        localDraftRecord = null
        localDraftSlotOccupied = false
        localDraftAttached = false
        localDraftPublicationConfirmed = false
        localDraftUnreadableFingerprint = null
        authoredTitle = false
        authoredChapterTitles.clear()
        authoredChapterNarrations.clear()
        savedEditStory = null
        savedEditReferences = null
        titleRevision++
        clearRelated()
        mutable.value = StoryWorkspaceStoreState()
    }

    private fun clearPublishedLocalDraft(): Boolean {
        val record = localDraftRecord ?: return true
        if (record.pendingSave == null) return true
        localDraftPublicationConfirmed = true
        val persistence = localDraftPersistence ?: return false
        val scope = record.scope
        try {
            if (persistence.delete(scope, record.recordId, record.revision)) {
                localDraftRecord = null
                localDraftSlotOccupied = false
                mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.EMPTY,
                    localDraftRevision = null, localDraftError = false)
                return true
            } else {
                mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true)
                return false
            }
        } catch (_: Exception) {
            mutable.value = state.value.copy(localDraftStatus = LocalStoryDraftStatus.ERROR, localDraftError = true)
            return false
        }
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
        private val ALBUM_THEMES = setOf("birthday", "trip", "growing_up", "grandparents", "year_in_review", "seasonal", "custom")
        private val NEXT_DICTATION_SCOPE = AtomicLong(0)
        private const val MAX_ASSETS = 24
        private const val MAX_CHAPTERS = 6
        private const val MAX_ASSETS_PER_CHAPTER = 4
        private const val MAX_EVIDENCE_PER_CHAPTER = 12
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
