package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.Collections

/** Private owner-supplied binding for one explicit new-book composition session. */
data class MemoryBookCompositionScope(
    val accountId: String,
    val credential: Bearer,
    val generation: Long,
    val library: String,
    val shelfScopeId: Long,
    val ownerCanCreate: Boolean,
)

data class MemoryBookCompositionSelection(
    val summary: SavedMemoryStorySummary,
    val selectionRevision: String,
    val sourcePolicy: String?,
)

enum class MemoryBookCompositionStatus { CLOSED, LOADING, READY, SAVING, RETRY_REQUIRED, CREATED }
enum class MemoryBookCompositionFailure {
    NETWORK, TLS, SERVICE_UNAVAILABLE, RATE_LIMITED, ACCESS_DENIED, SCOPE_CHANGED,
    NOT_ALLOWED, INVALID_STORY, STORY_CHANGED, INVALID_INPUT, INVALID_RESPONSE, UNKNOWN,
}

/** Transient state only. Credentials, server request bodies and private endpoint data are excluded. */
data class MemoryBookCompositionStoreState(
    val accountId: String? = null,
    val library: String? = null,
    val generation: Long? = null,
    val shelfScopeId: Long? = null,
    val candidatePage: SavedMemoryStoryPage? = null,
    val selectedStories: List<MemoryBookCompositionSelection> = emptyList(),
    val title: String = "",
    val introduction: String = "",
    val language: String = "zh",
    val actionEpoch: Long = 0,
    val draftRevision: Long = 0,
    val busy: Boolean = false,
    val status: MemoryBookCompositionStatus = MemoryBookCompositionStatus.CLOSED,
    val failure: MemoryBookCompositionFailure? = null,
    val canCreate: Boolean = false,
    val pendingRetry: Boolean = false,
    val createdBook: MemoryBook? = null,
)

/** Explicit, process-only composer for creating a memoir book from saved stories. */
class MemoryBookCompositionStore(
    private val api: PhotoHouseApi,
    private val repository: MemoryCommunityRepository,
    private val scope: CoroutineScope,
    private val currentScope: () -> MemoryBookCompositionScope?,
    private val onDenied: () -> Unit = {},
    /** Current transient intro voice input; default preserves existing callers. */
    private val hasUnfinishedInput: () -> Boolean = { false },
) {
    private data class Fence(
        val accountId: String,
        val credential: Bearer,
        val generation: Long,
        val library: String,
        val shelfScopeId: Long,
        val ownerCanCreate: Boolean,
        val actionEpoch: Long,
    )

    private data class Frozen(
        val fence: Fence,
        val selections: List<MemoryBookCompositionSelection>,
        val mutation: MemoryBookMutation,
    )

    private val mutableState = MutableStateFlow(MemoryBookCompositionStoreState())
    val state: StateFlow<MemoryBookCompositionStoreState> = mutableState.asStateFlow()
    private var epoch = 0L
    private var draftRevision = 0L
    private var requestId = 0L
    private var operation: Job? = null
    private var fence: Fence? = null
    private var frozen: Frozen? = null
    private var serverCanCreate = false

    /** Opening is explicit and is the only way this store starts collection reads. */
    @Synchronized
    fun open(defaultTitle: String = "", language: String = "zh"): Boolean {
        val binding = snapshot() ?: run { close(); return false }
        if (!validText(defaultTitle, TITLE_BYTES, allowBlank = true) || language !in LANGUAGES) return false
        closeOperation()
        epoch++
        requestId++
        draftRevision = 0
        frozen = null
        fence = null
        serverCanCreate = false
        if (!binding.ownerCanCreate) {
            mutableState.value = cleanState(binding.copy(actionEpoch = epoch), status = MemoryBookCompositionStatus.CLOSED,
                failure = MemoryBookCompositionFailure.NOT_ALLOWED)
            return false
        }
        val expected = binding.copy(actionEpoch = epoch)
        fence = expected
        mutableState.value = cleanState(expected, status = MemoryBookCompositionStatus.LOADING,
            busy = true).copy(title = defaultTitle, language = language)
        val request = ++requestId
        operation = scope.launch { openReads(expected, request) }
        return true
    }

    @Synchronized
    fun loadPage(page: Int, expectedScopeId: Long, expectedEpoch: Long): Boolean {
        val expected = activeFence(expectedScopeId, expectedEpoch) ?: return false
        if (mutableState.value.busy || frozen != null || mutableState.value.status != MemoryBookCompositionStatus.READY ||
            page !in 1..100000) return false
        val request = ++requestId
        mutableState.value = mutableState.value.copy(busy = true, failure = null)
        operation = scope.launch { loadCandidates(expected, request, page) }
        return true
    }

    /** Retries the initial permission/candidate read without replacing the private draft. */
    @Synchronized
    fun retryOpen(expectedScopeId: Long, expectedEpoch: Long): Boolean {
        val expected = activeFence(expectedScopeId, expectedEpoch) ?: return false
        if (mutableState.value.busy || frozen != null || mutableState.value.status != MemoryBookCompositionStatus.READY) return false
        mutableState.value = mutableState.value.copy(busy = true, failure = null, status = MemoryBookCompositionStatus.LOADING)
        val request = ++requestId
        operation = scope.launch { openReads(expected, request) }
        return true
    }

    /** Candidate callbacks include the exact visible revision; details are freshly reauthorized. */
    @Synchronized
    fun toggleStory(storyId: String, revision: Long, expectedScopeId: Long, expectedEpoch: Long): Boolean {
        val expected = activeFence(expectedScopeId, expectedEpoch) ?: return false
        val current = mutableState.value
        if (current.busy || frozen != null || !canMutate(expected)) return false
        val existing = current.selectedStories.indexOfFirst { it.summary.id == storyId }
        if (existing >= 0) {
            if (current.selectedStories[existing].summary.revision != revision) return false
            val next = current.selectedStories.toMutableList().also { it.removeAt(existing) }
            commitDraft(expected, current.copy(selectedStories = immutableSelections(next)))
            return true
        }
        val candidate = current.candidatePage?.items?.firstOrNull { it.id == storyId && it.revision == revision }
            ?: return false
        if (current.selectedStories.size >= MAX_STORIES) return false
        mutableState.value = current.copy(busy = true, failure = null)
        val request = ++requestId
        operation = scope.launch {
            try {
                requireCurrent(expected, request)
                val fresh = api.savedMemoryStory(expected.credential, expected.library, candidate.id, candidate.revision)
                requireCurrent(expected, request)
                if (!matchesCandidate(fresh, expected, candidate)) {
                    fail(expected, request, MemoryBookCompositionFailure.STORY_CHANGED)
                    return@launch
                }
                val latest = mutableState.value
                if (latest.selectedStories.size >= MAX_STORIES || latest.selectedStories.any { it.summary.id == fresh.id }) {
                    finishBusy(expected, request)
                    return@launch
                }
                val selected = latest.selectedStories + selection(fresh)
                commitDraft(expected, latest.copy(selectedStories = immutableSelections(selected), busy = false))
            } catch (failure: Throwable) {
                handleFailure(expected, request, failure)
            }
        }
        return true
    }

    /** Accepts a new order only when it was based on the exact currently visible selection order. */
    @Synchronized
    fun reorderStories(
        expectedIds: List<String>, orderedIds: List<String>, expectedScopeId: Long, expectedEpoch: Long,
    ): Boolean {
        val expected = activeFence(expectedScopeId, expectedEpoch) ?: return false
        val current = mutableState.value
        if (current.busy || frozen != null || !canMutate(expected) || current.selectedStories.map { it.summary.id } != expectedIds)
            return false
        if (orderedIds.size != expectedIds.size || orderedIds.toSet() != expectedIds.toSet() ||
            orderedIds.distinct().size != orderedIds.size) return false
        val byId = current.selectedStories.associateBy { it.summary.id }
        commitDraft(expected, current.copy(selectedStories = immutableSelections(orderedIds.map { byId.getValue(it) })))
        return true
    }

    /** Text updates are keyed to the attached composition scope, not per-keystroke revisions. */
    @Synchronized
    fun updateTitle(value: String, expectedScopeId: Long, expectedEpoch: Long): Boolean {
        val expected = activeFence(expectedScopeId, expectedEpoch) ?: return false
        if (!canMutate(expected) || frozen != null || !validText(value, TITLE_BYTES, allowBlank = true)) return false
        commitDraft(expected, mutableState.value.copy(title = value))
        return true
    }

    @Synchronized
    fun updateIntroduction(value: String, expectedScopeId: Long, expectedEpoch: Long): Boolean {
        val expected = activeFence(expectedScopeId, expectedEpoch) ?: return false
        if (!canMutate(expected) || frozen != null || !validText(value, INTRODUCTION_BYTES, allowBlank = true, allowNewline = true)) return false
        commitDraft(expected, mutableState.value.copy(introduction = value))
        return true
    }

    @Synchronized
    fun updateLanguage(value: String, expectedScopeId: Long, expectedEpoch: Long): Boolean {
        val expected = activeFence(expectedScopeId, expectedEpoch) ?: return false
        if (!canMutate(expected) || frozen != null || value !in LANGUAGES) return false
        commitDraft(expected, mutableState.value.copy(language = value))
        return true
    }

    @Synchronized
    fun save(expectedScopeId: Long, expectedEpoch: Long, expectedDraftRevision: Long): Boolean {
        val expected = activeFence(expectedScopeId, expectedEpoch) ?: return false
        val current = mutableState.value
        if (current.busy || frozen != null || !canMutate(expected) || current.draftRevision != expectedDraftRevision ||
            hasUnfinishedInputSafely() || !validMutationFields(current)) return false
        mutableState.value = current.copy(busy = true, failure = null, status = MemoryBookCompositionStatus.SAVING)
        val request = ++requestId
        operation = scope.launch { validateAndSave(expected, request, current) }
        return true
    }

    @Synchronized
    fun retry(expectedScopeId: Long, expectedEpoch: Long): Boolean {
        val expected = activeFence(expectedScopeId, expectedEpoch) ?: return false
        val pending = frozen ?: return false
        if (mutableState.value.busy || hasUnfinishedInputSafely() || !sameFence(expected, pending.fence) || !canCreate(expected)) return false
        mutableState.value = mutableState.value.copy(busy = true, failure = null, status = MemoryBookCompositionStatus.SAVING)
        val request = ++requestId
        operation = scope.launch { postFrozen(pending, request) }
        return true
    }

    @Synchronized
    fun close(expectedScopeId: Long? = null, expectedEpoch: Long? = null) {
        val currentFence = fence
        if (expectedScopeId != null && currentFence?.shelfScopeId != expectedScopeId) return
        if (expectedEpoch != null && currentFence?.actionEpoch != expectedEpoch) return
        closeOperation()
        epoch++
        requestId++
        frozen = null
        fence = null
        serverCanCreate = false
        mutableState.value = MemoryBookCompositionStoreState(actionEpoch = epoch)
    }

    private suspend fun openReads(expected: Fence, request: Long) {
        try {
            requireCurrent(expected, request)
            repository.loadCapabilities { isCurrent(expected, request) }
            requireCurrent(expected, request)
            val books = repository.books(1) { isCurrent(expected, request) }
            requireCurrent(expected, request)
            if (books.libraryId != expected.library) throw ApiFailure(FailureKind.INVALID_RESPONSE)
            serverCanCreate = books.canCreate
            if (!serverCanCreate) {
                fail(expected, request, MemoryBookCompositionFailure.NOT_ALLOWED)
                return
            }
            val page = api.savedMemoryStories(expected.credential, expected.library, 1)
            requireCurrent(expected, request)
            if (page.libraryId != expected.library || page.page != 1) throw ApiFailure(FailureKind.INVALID_RESPONSE)
            mutableState.value = mutableState.value.copy(candidatePage = page, busy = false,
                canCreate = canCreate(expected), status = MemoryBookCompositionStatus.READY, failure = null)
        } catch (failure: Throwable) { handleFailure(expected, request, failure) }
    }

    private suspend fun loadCandidates(expected: Fence, request: Long, pageNumber: Int) {
        try {
            requireCurrent(expected, request)
            val page = api.savedMemoryStories(expected.credential, expected.library, pageNumber)
            requireCurrent(expected, request)
            if (page.libraryId != expected.library || page.page != pageNumber) throw ApiFailure(FailureKind.INVALID_RESPONSE)
            mutableState.value = mutableState.value.copy(candidatePage = page, busy = false,
                status = MemoryBookCompositionStatus.READY, failure = null)
        } catch (failure: Throwable) { handleFailure(expected, request, failure) }
    }

    private suspend fun validateAndSave(expected: Fence, request: Long, draft: MemoryBookCompositionStoreState) {
        try {
            val selected = draft.selectedStories.toList()
            if (selected.isEmpty() || selected.size > MAX_STORIES) {
                fail(expected, request, MemoryBookCompositionFailure.INVALID_INPUT)
                return
            }
            for (entry in selected) {
                requireCurrent(expected, request)
                val fresh = api.savedMemoryStory(expected.credential, expected.library,
                    entry.summary.id, entry.summary.revision)
                requireCurrent(expected, request)
                if (!matchesSelection(fresh, expected, entry)) {
                    fail(expected, request, MemoryBookCompositionFailure.STORY_CHANGED)
                    return
                }
            }
            requireCurrent(expected, request)
            val mutation = MemoryBookMutation(draft.title, draft.language, draft.introduction,
                immutableIds(selected.map { it.summary.id }), revision = 0L)
            val frozenRequest = Frozen(expected, immutableSelections(selected), mutation)
            frozen = frozenRequest
            mutableState.value = mutableState.value.copy(pendingRetry = true, busy = true,
                status = MemoryBookCompositionStatus.SAVING)
            postFrozen(frozenRequest, request)
        } catch (failure: Throwable) { handleFailure(expected, request, failure) }
    }

    private suspend fun postFrozen(pending: Frozen, request: Long) {
        try {
            requireCurrent(pending.fence, request)
            val result = repository.saveBook(null, pending.mutation) { isCurrent(pending.fence, request) }
            requireCurrent(pending.fence, request)
            val actualStories = result.stories.map { it.id to it.revision }
            val expectedStories = pending.selections.map { it.summary.id to it.summary.revision }
            if (result.id != runCatching { java.util.UUID.fromString(result.id).toString() }.getOrNull() ||
                !result.canEdit || result.revision != 1L || result.title != pending.mutation.title ||
                result.introduction != pending.mutation.introduction || result.language != pending.mutation.language ||
                result.stories.map { it.id } != pending.mutation.storyIds || actualStories != expectedStories) {
                fail(pending.fence, request, MemoryBookCompositionFailure.INVALID_RESPONSE, retry = true)
                return
            }
            if (frozen !== pending) return
            frozen = null
            mutableState.value = mutableState.value.copy(busy = false, pendingRetry = false,
                status = MemoryBookCompositionStatus.CREATED, failure = null, createdBook = result)
        } catch (failure: Throwable) {
            handleFailure(pending.fence, request, failure, retry = true)
        }
    }

    private fun selection(story: SavedMemoryStory) = MemoryBookCompositionSelection(
        summary = SavedMemoryStorySummary(story.id, story.title, story.theme, story.language, story.revision,
            story.items.firstOrNull()?.asset?.id.orEmpty(), story.items.size, story.chapters.size, story.updatedAt, story.canEdit),
        selectionRevision = story.selectionRevision,
        sourcePolicy = story.sourcePolicy,
    )

    private fun matchesCandidate(story: SavedMemoryStory, expected: Fence, summary: SavedMemoryStorySummary): Boolean =
        story.id == summary.id && story.revision == summary.revision && story.libraryId == expected.library &&
            story.title == summary.title && story.theme == summary.theme && story.language == summary.language &&
            story.items.size == summary.itemCount && story.chapters.size == summary.chapterCount &&
            story.selectionRevision.matches(Regex("[0-9a-fA-F]{64}"))

    private fun matchesSelection(story: SavedMemoryStory, expected: Fence, selected: MemoryBookCompositionSelection): Boolean =
        story.id == selected.summary.id && story.revision == selected.summary.revision &&
            story.libraryId == expected.library && story.selectionRevision == selected.selectionRevision &&
            story.sourcePolicy == selected.sourcePolicy && story.title == selected.summary.title &&
            story.theme == selected.summary.theme && story.language == selected.summary.language &&
            story.items.size == selected.summary.itemCount && story.chapters.size == selected.summary.chapterCount

    private fun commitDraft(expected: Fence, next: MemoryBookCompositionStoreState) {
        if (!isCurrent(expected, null) || frozen != null) return
        draftRevision++
        mutableState.value = next.copy(actionEpoch = expected.actionEpoch, draftRevision = draftRevision,
            failure = null, status = MemoryBookCompositionStatus.READY, canCreate = canCreate(expected))
    }

    private fun validMutationFields(value: MemoryBookCompositionStoreState): Boolean =
        validText(value.title, TITLE_BYTES, allowBlank = false) &&
            validText(value.introduction, INTRODUCTION_BYTES, allowBlank = true, allowNewline = true) &&
            value.language in LANGUAGES && value.selectedStories.size in 1..MAX_STORIES &&
            value.selectedStories.map { it.summary.id }.distinct().size == value.selectedStories.size

    private fun validText(value: String, maxBytes: Int, allowBlank: Boolean, allowNewline: Boolean = false): Boolean {
        if (!allowBlank && value.isBlank()) return false
        if (value.any { it == '\u0000' || it < ' ' && !(allowNewline && it in "\n\t") }) return false
        return try {
            val bytes = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value))
            bytes.remaining() <= maxBytes
        } catch (_: Exception) { false }
    }

    private fun canMutate(expected: Fence) = canCreate(expected) &&
        mutableState.value.status == MemoryBookCompositionStatus.READY

    private fun hasUnfinishedInputSafely(): Boolean = runCatching(hasUnfinishedInput).getOrDefault(true)

    private fun canCreate(expected: Fence) = expected.ownerCanCreate && serverCanCreate && isCurrent(expected, null)

    private fun snapshot(): Fence? {
        val value = currentScope() ?: return null
        if (value.accountId.isBlank() || value.accountId.length > 256 || value.generation < 0 ||
            value.shelfScopeId < 0 || !PhoneDiscoveryWire.validLibrary(value.library)) return null
        return Fence(value.accountId, value.credential, value.generation, value.library,
            value.shelfScopeId, value.ownerCanCreate, epoch)
    }

    private fun activeFence(scopeId: Long, expectedEpoch: Long): Fence? = fence?.takeIf {
        it.shelfScopeId == scopeId && it.actionEpoch == expectedEpoch && isCurrent(it, null)
    }

    private fun isCurrent(expected: Fence, request: Long?): Boolean {
        if (request != null && request != requestId) return false
        val actual = currentScope() ?: return false
        return fence === expected && expected.actionEpoch == epoch && actual.accountId == expected.accountId &&
            actual.credential === expected.credential && actual.generation == expected.generation &&
            actual.library == expected.library && actual.shelfScopeId == expected.shelfScopeId &&
            actual.ownerCanCreate && expected.ownerCanCreate
    }

    private fun sameFence(left: Fence, right: Fence) = left.accountId == right.accountId &&
        left.credential === right.credential && left.generation == right.generation &&
        left.library == right.library && left.shelfScopeId == right.shelfScopeId &&
        left.actionEpoch == right.actionEpoch

    private fun requireCurrent(expected: Fence, request: Long) {
        if (!isCurrent(expected, request)) throw CancellationException("Book composition scope changed")
    }

    private fun cleanState(expected: Fence, status: MemoryBookCompositionStatus,
                           busy: Boolean = false, failure: MemoryBookCompositionFailure? = null) =
        MemoryBookCompositionStoreState(accountId = expected.accountId, library = expected.library,
            generation = expected.generation, shelfScopeId = expected.shelfScopeId,
            actionEpoch = expected.actionEpoch, status = status, busy = busy, failure = failure)

    private fun finishBusy(expected: Fence, request: Long) {
        if (isCurrent(expected, request)) mutableState.value = mutableState.value.copy(busy = false)
    }

    private fun fail(expected: Fence, request: Long, failure: MemoryBookCompositionFailure, retry: Boolean = false) {
        if (!isCurrent(expected, request)) return
        mutableState.value = mutableState.value.copy(busy = false, failure = failure,
            status = if (retry && frozen != null) MemoryBookCompositionStatus.RETRY_REQUIRED else MemoryBookCompositionStatus.READY,
            pendingRetry = frozen != null, canCreate = canCreate(expected))
    }

    private fun handleFailure(expected: Fence, request: Long, failure: Throwable, retry: Boolean = false) {
        if (failure is CancellationException || !isCurrent(expected, request)) return
        val code = when (failure) {
            is ApiFailure -> when {
                failure.status in setOf(401, 403) -> MemoryBookCompositionFailure.ACCESS_DENIED
                failure.status == 429 -> MemoryBookCompositionFailure.RATE_LIMITED
                failure.status == 503 -> MemoryBookCompositionFailure.SERVICE_UNAVAILABLE
                failure.kind == FailureKind.TLS -> MemoryBookCompositionFailure.TLS
                failure.kind == FailureKind.OFFLINE -> MemoryBookCompositionFailure.NETWORK
                failure.kind == FailureKind.INVALID_INPUT -> MemoryBookCompositionFailure.INVALID_INPUT
                failure.kind == FailureKind.INVALID_RESPONSE -> MemoryBookCompositionFailure.INVALID_RESPONSE
                else -> MemoryBookCompositionFailure.UNKNOWN
            }
            else -> when (failure) {
                is java.io.IOException -> MemoryBookCompositionFailure.NETWORK
                else -> MemoryBookCompositionFailure.UNKNOWN
            }
        }
        if (code == MemoryBookCompositionFailure.ACCESS_DENIED) {
            closeOperation()
            frozen = null
            serverCanCreate = false
            val prior = mutableState.value
            mutableState.value = cleanState(expected, MemoryBookCompositionStatus.CLOSED,
                failure = code).copy(actionEpoch = expected.actionEpoch, draftRevision = prior.draftRevision)
            onDenied()
            return
        }
        mutableState.value = mutableState.value.copy(busy = false, failure = code,
            status = if (retry && frozen != null) MemoryBookCompositionStatus.RETRY_REQUIRED else MemoryBookCompositionStatus.READY,
            pendingRetry = frozen != null, canCreate = canCreate(expected))
    }

    @Synchronized
    private fun closeOperation() {
        operation?.cancel()
        operation = null
    }

    private fun immutableSelections(values: List<MemoryBookCompositionSelection>) =
        Collections.unmodifiableList(ArrayList(values))
    private fun immutableIds(values: List<String>) = Collections.unmodifiableList(ArrayList(values))

    companion object {
        const val MAX_STORIES = 24
        const val TITLE_BYTES = 512
        const val INTRODUCTION_BYTES = 6000
        private val LANGUAGES = setOf("zh", "en")
    }
}
