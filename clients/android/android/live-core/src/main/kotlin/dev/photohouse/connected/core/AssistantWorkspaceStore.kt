package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.yield
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlin.coroutines.coroutineContext
import java.util.UUID
import kotlinx.serialization.json.*

/** The exact authenticated foreground owner for one private workspace operation. */
data class AssistantWorkspaceScope(
    val accountId: String,
    val bearer: Bearer,
    val libraryId: String,
    val generation: Long,
    val foregroundAllowed: Boolean,
)

/** Guards a delayed UI callback against an older card occupying the same ordinal. */
fun isCurrentFreshMemoryOpeningSelection(
    renderedTurn: AssistantWorkspaceTurn?,
    ordinal: Int,
    renderedCard: AssistantSavedMemoryCard?,
    liveTurn: AssistantWorkspaceTurn?,
    liveDetail: AssistantWorkspaceThreadDetail?,
): Boolean {
    val result = renderedTurn?.result ?: return false
    val card = result.memoryCards.getOrNull(ordinal) ?: return false
    val thread = liveDetail?.thread ?: return false
    return renderedTurn.status == AssistantWorkspaceRequestStatus.COMPLETED && !renderedTurn.recovered &&
        renderedTurn.version == 1 && ordinal in 0..11 && renderedCard == card &&
        result.kind == "memory_cards" && result.effect == null &&
        result.savedMemoryContext?.libraryId == thread.libraryId &&
        liveTurn == renderedTurn && renderedTurn.threadId == thread.threadId &&
        renderedTurn.revision > 0 && renderedTurn.revision == thread.revision
}

enum class AssistantWorkspaceError {
    UNAVAILABLE, ACCESS_DENIED, INVALID_REQUEST, CONTEXT_CHANGED,
    NETWORK, INVALID_RESPONSE, TURN_FAILED, TURN_INTERRUPTED, UNKNOWN,
}

data class AssistantWorkspacePendingTurn(
    val threadId: String,
    val requestId: String,
    val expectedRevision: Long,
    val text: String,
    val parentRequestId: String? = null,
    val memoryParent: AssistantSavedMemoryParent? = null,
    val searchVersion: Int = 1,
    val scene: Boolean = false,
    val sceneScope: JsonObject? = null,
)

data class AssistantWorkspaceState(
    val accountId: String? = null,
    val libraryId: String? = null,
    val generation: Long? = null,
    val capabilities: AssistantWorkspaceCapabilities? = null,
    val sceneSearchAvailable: Boolean = false,
    val sceneDraft: String = "",
    val savedMemoryCardsAvailable: Boolean = false,
    val savedMemoryActionsAvailable: Boolean = false,
    val savedMemoryReaderAvailable: Boolean = false,
    val savedMemorySpeechAvailable: Boolean = false,
    val savedMemoryReadingAvailable: Boolean = false,
    val savedMemorySegmentReadingAvailable: Boolean = false,
    val savedMemoryFollowupAvailable: Boolean = false,
    val memoryFollowupDraftParent: AssistantSavedMemoryParent? = null,
    val threads: AssistantWorkspaceThreadList? = null,
    val detail: AssistantWorkspaceThreadDetail? = null,
    val currentTurn: AssistantWorkspaceTurn? = null,
    val draft: String = "",
    val pendingCreationId: String? = null,
    val pendingTurn: AssistantWorkspacePendingTurn? = null,
    val uncertain: Boolean = false,
    val error: AssistantWorkspaceError? = null,
    val preferences: AssistantWorkspacePreferences? = null,
    val unsupportedPreferences: Set<AssistantWorkspacePreference> = setOf(
        AssistantWorkspacePreference.REPLY_LENGTH, AssistantWorkspacePreference.VOICE_PACE,
    ),
    val continuationEnabled: Boolean = false,
    val busy: Boolean = false,
    val historyRefreshRequired: Boolean = false,
    val memoryReaderHandoff: AssistantMemoryReaderHandoff? = null,
    val memoryReaderOrdinal: Int? = null,
    val memoryReaderError: AssistantWorkspaceError? = null,
    val memoryReaderErrorOrdinal: Int? = null,
) {
    /** Retained cards beneath a clarification never authorize a scene action. */
    val sceneReady: Boolean get() {
        val turn = currentTurn ?: return false
        val result = turn.result ?: return false
        val filters = result.filters ?: return false
        val thread = detail?.thread ?: return false
        val media = (filters["media"] as? JsonArray)?.map { (it as? JsonPrimitive)?.content }
        return sceneSearchAvailable && capabilities?.let { it.available && it.threads && it.serverOwnedTurns } == true &&
            thread.threadId == turn.threadId && thread.revision == turn.revision &&
            continuationEnabled && !busy && !uncertain && pendingTurn == null && pendingCreationId == null && !historyRefreshRequired &&
            turn.status == AssistantWorkspaceRequestStatus.COMPLETED && result.kind == "results" &&
            result.searchVersion in setOf(2, 3, 4) && result.context != null && result.effect == null &&
            "descriptive" !in filters && ("media" !in filters || media == listOf("image"))
    }
}

/**
 * In-memory coordinator for the opt-in private conversation API. It never persists text,
 * retries a POST automatically, or turns a recovered result into a navigation action.
 */
class AssistantWorkspaceStore(
    private val api: AssistantWorkspaceApi,
    private val coroutineScope: CoroutineScope,
    private val currentScope: () -> AssistantWorkspaceScope?,
    private val uuidFactory: () -> String = { UUID.randomUUID().toString() },
) : AutoCloseable {
    private val guard = Any()
    private val actionMutex = Mutex()
    private val mutableState = MutableStateFlow(AssistantWorkspaceState())
    val state: StateFlow<AssistantWorkspaceState> = mutableState.asStateFlow()

    private var operationNonce = 0L
    private var activeOperationNonce = 0L
    private var scopeKey: AssistantWorkspaceScope? = null
    private var activeJob: Job? = null
    private var closed = false

    /** Called by the owner whenever account, library, generation, or foreground status changes. */
    fun onScopeChanged() {
        val next = usableScope()
        synchronized(guard) {
            if (closed || sameScope(scopeKey, next)) return
            operationNonce++
            scopeKey = next
            activeJob?.cancel()
            activeJob = null
            mutableState.value = if (next == null) AssistantWorkspaceState() else AssistantWorkspaceState(
                accountId = next.accountId, libraryId = next.libraryId, generation = next.generation,
            )
        }
    }

    fun setDraft(text: String) {
        onScopeChanged()
        synchronized(guard) {
            if (!closed && usableScope() != null) mutableState.value = mutableState.value.copy(draft = text, memoryFollowupDraftParent = null)
        }
    }

    fun setSceneDraft(text: String) {
        onScopeChanged()
        synchronized(guard) {
            if (!closed && usableScope() != null && text.toByteArray(Charsets.UTF_8).size <= 4096)
                mutableState.value = mutableState.value.copy(sceneDraft = text)
        }
    }

    fun refreshSceneSearchCapabilities(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        mutableState.value = mutableState.value.copy(sceneSearchAvailable = false)
        if (mutableState.value.capabilities?.serverOwnedTurns != true) return@launchAction
        val value = api.sceneSearchCapabilities(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(sceneSearchAvailable = value.version == 1 && value.available &&
            value.searchVersion == 4 && value.media == listOf("image"))
    }

    /** Inserts a suggestion and binds its exact current completed card result for the next explicit send. */
    fun setSavedMemoryFollowupDraft(text: String): Boolean {
        onScopeChanged()
        synchronized(guard) {
            val scope = usableScope() ?: return false
            val current = mutableState.value
            val detail = current.detail
            val turn = current.currentTurn
            val result = turn?.result
            val valid = !closed && current.savedMemoryCardsAvailable && current.savedMemoryFollowupAvailable &&
                current.accountId == scope.accountId && current.libraryId == scope.libraryId && current.generation == scope.generation &&
                current.pendingTurn == null && !current.busy && detail != null && turn != null && result != null &&
                turn.status == AssistantWorkspaceRequestStatus.COMPLETED && !turn.recovered && result.kind == "memory_cards" &&
                result.memoryCards.isNotEmpty() && turn.threadId == detail.thread.threadId && turn.revision == detail.thread.revision &&
                turn.revision > 0 && AssistantWorkspaceWire.validUuid4(turn.requestId) &&
                result.savedMemoryContext?.libraryId == scope.libraryId && text.isNotBlank()
            if (!valid) return false
            mutableState.value = current.copy(draft = text,
                memoryFollowupDraftParent = AssistantSavedMemoryParent(turn!!.requestId, turn.revision))
            return true
        }
    }

    fun refreshCapabilities(): Boolean = launchAction {
        val scope = requireScope()
        requireEnabled()
        mutableState.value = mutableState.value.copy(sceneSearchAvailable = false, savedMemoryCardsAvailable = false, savedMemoryReaderAvailable = false,
            savedMemorySpeechAvailable = false, savedMemoryReadingAvailable = false,
            savedMemorySegmentReadingAvailable = false, savedMemoryFollowupAvailable = false,
            savedMemoryActionsAvailable = false, memoryFollowupDraftParent = null)
        val value = api.capabilities(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(
            capabilities = value,
            unsupportedPreferences = AssistantWorkspacePreference.entries.toSet() -
                if ("locale" in value.appliedPreferences) setOf(AssistantWorkspacePreference.LOCALE) else emptySet(),
            error = if (value.available && value.threads) null else AssistantWorkspaceError.UNAVAILABLE,
            savedMemoryCardsAvailable = if (value.available && value.threads) mutableState.value.savedMemoryCardsAvailable else false,
            savedMemoryReaderAvailable = if (value.available && value.threads) mutableState.value.savedMemoryReaderAvailable else false,
            savedMemoryActionsAvailable = if (value.available && value.threads) mutableState.value.savedMemoryActionsAvailable else false,
        )
    }

    /** Capability probe controls whether new searches may negotiate fresh saved-memory cards. */
    fun refreshSavedMemoryCardsCapabilities(): Boolean = launchAction {
        val scope = requireScope()
        requireEnabled()
        mutableState.value = mutableState.value.copy(savedMemoryFollowupAvailable = false, savedMemoryActionsAvailable = false,
            savedMemoryReadingAvailable = false, savedMemorySegmentReadingAvailable = false, memoryFollowupDraftParent = null)
        val value = api.savedMemoryCardsCapabilities(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        val cardsAvailable = value.version == 1 && value.available
        val actions = if (cardsAvailable) api.savedMemoryActionCapabilities(scope.bearer, scope.libraryId)
            else SavedMemoryReaderCapabilities(1, false)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(savedMemoryCardsAvailable = cardsAvailable,
            savedMemoryActionsAvailable = cardsAvailable && actions.version == 1 && actions.available)
    }

    fun refreshSavedMemoryFollowupCapabilities(): Boolean = launchAction {
        val scope = requireScope()
        requireEnabled()
        mutableState.value = mutableState.value.copy(savedMemoryFollowupAvailable = false, memoryFollowupDraftParent = null)
        val value = api.savedMemoryFollowupCapabilities(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(savedMemoryFollowupAvailable = value.version == 1 && value.available)
    }

    /** Separate reader probe controls only explicit Open actions. */
    fun refreshSavedMemoryReaderCapabilities(): Boolean = launchAction {
        val scope = requireScope()
        requireEnabled()
        mutableState.value = mutableState.value.copy(savedMemoryReadingAvailable = false)
        val value = api.savedMemoryReaderCapabilities(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(savedMemoryReaderAvailable = value.available)
    }

    fun refreshSavedMemorySpeechCapabilities(): Boolean = launchAction {
        val scope = requireScope()
        requireEnabled()
        mutableState.value = mutableState.value.copy(savedMemoryReadingAvailable = false)
        val value = api.savedMemorySpeechCapabilities(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(savedMemorySpeechAvailable = value.available)
    }

    fun refreshSavedMemoryReadingCapabilities(): Boolean = launchAction {
        val scope = requireScope()
        requireEnabled()
        mutableState.value = mutableState.value.copy(savedMemoryReadingAvailable = false)
        val value = api.savedMemoryReadingCapabilities(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(savedMemoryReadingAvailable = value.version == 1 && value.available)
    }

    /** Independent optional capability for explicitly requested bounded source segments. */
    fun refreshSavedMemorySegmentReadingCapabilities(): Boolean = launchAction {
        val scope = requireScope()
        requireEnabled()
        mutableState.value = mutableState.value.copy(savedMemorySegmentReadingAvailable = false)
        val value = api.savedMemorySegmentReadingCapabilities(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(
            savedMemorySegmentReadingAvailable = value.version == 1 && value.available)
    }

    /** Explicit open from the latest fresh, negotiated card result only. */
    fun openSavedMemoryCard(ordinal: Int): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val current = mutableState.value
        val detail = current.detail ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        val turn = current.currentTurn ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        val result = turn.result ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        if (!current.savedMemoryCardsAvailable || !current.savedMemoryReaderAvailable || turn.status != AssistantWorkspaceRequestStatus.COMPLETED || turn.recovered ||
            result.kind != "memory_cards" || turn.threadId != detail.thread.threadId || turn.revision != detail.thread.revision ||
            ordinal !in result.memoryCards.indices || result.savedMemoryContext?.libraryId != scope.libraryId)
            throw ApiFailure(FailureKind.INVALID_INPUT)
        val request = ordinal to result.memoryCards[ordinal]
        mutableState.value = current.copy(memoryReaderHandoff = null, memoryReaderOrdinal = ordinal,
            memoryReaderError = null, memoryReaderErrorOrdinal = null)
        val payload = try {
            api.savedMemoryReader(scope.bearer, scope.libraryId, turn.threadId, turn.requestId, ordinal, turn.revision)
        } catch (cancel: CancellationException) { throw cancel }
        catch (error: Exception) {
            if (isCurrent(scope)) mutableState.value = mutableState.value.copy(
                memoryReaderOrdinal = null, memoryReaderError = safeError(error), memoryReaderErrorOrdinal = ordinal,
            )
            return@launchAction
        }
        requireCurrent(scope)
        val latest = mutableState.value
        val latestTurn = latest.currentTurn
        val latestCard = latestTurn?.result?.memoryCards?.getOrNull(ordinal)
        if (latest.memoryReaderOrdinal != ordinal || latest.detail?.thread?.threadId != turn.threadId ||
            latestTurn?.requestId != turn.requestId || latestTurn.revision != turn.revision ||
            latestCard != request.second || latestTurn.recovered || latestTurn.status != AssistantWorkspaceRequestStatus.COMPLETED)
            throw CancellationException("Saved memory card scope changed")
        val matches = when (payload) {
            is SavedMemoryReaderPayload.Story -> request.second.kind == "story" && payload.value.id == request.second.id &&
                payload.value.revision.toString() == request.second.revision
            is SavedMemoryReaderPayload.Memoir -> request.second.kind == "memoir" && payload.value.id == request.second.id &&
                payload.value.revision.toString() == request.second.revision
        }
        if (!matches) {
            mutableState.value = latest.copy(memoryReaderOrdinal = null,
                memoryReaderError = AssistantWorkspaceError.INVALID_RESPONSE, memoryReaderErrorOrdinal = ordinal)
            return@launchAction
        }
        mutableState.value = latest.copy(memoryReaderHandoff = AssistantMemoryReaderHandoff(
            turn.threadId, turn.requestId, turn.revision, ordinal, request.second, payload),
            memoryReaderOrdinal = null, memoryReaderError = null, memoryReaderErrorOrdinal = null)
    }

    /** Screen dismissal fences a pending GET without touching the conversation draft or turn request. */
    fun invalidateSavedMemoryReader() {
        synchronized(guard) {
            val current = mutableState.value
            if (current.memoryReaderOrdinal == null && current.memoryReaderHandoff == null) return
            operationNonce++
            activeJob?.cancel(CancellationException("Saved memory reader screen closed"))
            activeJob = null
            mutableState.value = current.copy(busy = false, memoryReaderHandoff = null,
                memoryReaderOrdinal = null, memoryReaderError = null, memoryReaderErrorOrdinal = null)
        }
    }

    /** Atomically consumes only the handoff still owned by the latest fresh completed turn. */
    fun consumeMemoryReaderHandoff(handoff: AssistantMemoryReaderHandoff): Boolean = synchronized(guard) {
        val current = mutableState.value
        val scope = usableScope()
        val turn = current.currentTurn
        val card = turn?.result?.memoryCards?.getOrNull(handoff.ordinal)
        val reference = turn?.result?.savedMemoryContext?.references?.getOrNull(handoff.ordinal)
        val valid = !closed && scope?.foregroundAllowed == true && sameScope(scopeKey, scope) &&
            current.accountId == scope.accountId && current.libraryId == scope.libraryId && current.generation == scope.generation &&
            current.memoryReaderHandoff == handoff && current.savedMemoryCardsAvailable &&
            current.savedMemoryReaderAvailable && current.pendingTurn == null && !current.busy &&
            current.detail?.thread?.let { it.threadId == handoff.threadId && it.revision == handoff.completionRevision } == true &&
            turn?.let { it.threadId == handoff.threadId && it.requestId == handoff.turnId &&
                it.revision == handoff.completionRevision && it.status == AssistantWorkspaceRequestStatus.COMPLETED &&
                !it.recovered && it.result?.kind == "memory_cards" } == true && card == handoff.card &&
            current.libraryId == turn?.result?.savedMemoryContext?.libraryId && reference?.let {
                it.kind == handoff.card.kind && it.id == handoff.card.id && it.revision == handoff.card.revision &&
                    it.sourceRevision == handoff.card.sourceRevision
            } == true
        if (valid) mutableState.value = current.copy(memoryReaderHandoff = null)
        valid
    }

    fun refreshThreads(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val value = api.listThreads(scope.bearer, scope.libraryId, mutableState.value.capabilities?.threadLabels == true)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(threads = value, error = null)
    }

    /** Reuses an uncertain creation ID; absence from the GET list never triggers another POST. */
    fun createThread(acknowledgeUncertainTurnMayCommit: Boolean = false): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        prepareThreadSwitch(acknowledgeUncertainTurnMayCommit)
        // An explicit retry first checks the exact owned identity. A paged
        // list cannot prove that a previously submitted creation is absent.
        mutableState.value.pendingCreationId?.let { existing ->
            try {
                adoptCreatedThread(scope, api.readThread(scope.bearer, scope.libraryId, existing))
                return@launchAction
            } catch (cancel: CancellationException) { throw cancel }
            catch (failure: ApiFailure) { if (failure.status != 404) throw failure }
        }
        val clientId = mutableState.value.pendingCreationId ?: uuidFactory().also {
            if (!AssistantWorkspaceWire.validUuid4(it)) throw ApiFailure(FailureKind.INVALID_INPUT)
            mutableState.value = mutableState.value.copy(pendingCreationId = it)
        }
        try {
            val created = api.createThread(scope.bearer, scope.libraryId, clientId)
            requireCurrent(scope)
            mutableState.value = mutableState.value.copy(
                pendingCreationId = null,
                detail = AssistantWorkspaceThreadDetail(1, created.thread, emptyList()),
                currentTurn = null, uncertain = false, continuationEnabled = true, error = null, historyRefreshRequired = false,
                memoryFollowupDraftParent = null,
                memoryReaderHandoff = null, memoryReaderOrdinal = null, memoryReaderError = null, memoryReaderErrorOrdinal = null,
                threads = mutableState.value.threads?.let { list ->
                    list.copy(threads = (list.threads.filterNot { it.threadId == clientId } + created.thread).sortedByDescending { it.updatedAt })
                },
            )
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (postFailure: Exception) {
            requireCurrent(scope)
            if (authorizationDenied(postFailure)) throw postFailure
            // Creation may have committed. Reconcile by GET using the same client ID.
            try {
                adoptCreatedThread(scope, api.readThread(scope.bearer, scope.libraryId, clientId))
            } catch (cancel: CancellationException) { throw cancel }
            catch (getFailure: Exception) {
                requireCurrent(scope)
                if (authorizationDenied(getFailure)) throw getFailure
                mutableState.value = mutableState.value.copy(error = safeError(getFailure))
            }
        }
    }

    /** Explicit GET-only reconciliation; does not retry creation on a missing response. */
    fun reconcileCreation(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val id = mutableState.value.pendingCreationId ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        adoptCreatedThread(scope, api.readThread(scope.bearer, scope.libraryId, id))
    }

    private suspend fun adoptCreatedThread(scope: AssistantWorkspaceScope, detail: AssistantWorkspaceThreadDetail) {
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(pendingCreationId = null, detail = detail,
            currentTurn = null, memoryFollowupDraftParent = null, uncertain = false, continuationEnabled = detail.thread.revision == 0L,
            memoryReaderHandoff = null, memoryReaderOrdinal = null, memoryReaderError = null, memoryReaderErrorOrdinal = null,
            historyRefreshRequired = false,
            error = if (detail.thread.revision == 0L) null else AssistantWorkspaceError.CONTEXT_CHANGED)
    }

    fun openThread(threadId: String, acknowledgeUncertainTurnMayCommit: Boolean = false): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        prepareThreadSwitch(acknowledgeUncertainTurnMayCommit)
        if (!AssistantWorkspaceWire.validUuid4(threadId)) throw ApiFailure(FailureKind.INVALID_INPUT)
        mutableState.value = mutableState.value.copy(currentTurn = null, continuationEnabled = false,
            historyRefreshRequired = true, memoryReaderHandoff = null, memoryReaderOrdinal = null)
        val detail = api.readThread(scope.bearer, scope.libraryId, threadId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(
            detail = detail, currentTurn = null, pendingCreationId = null, memoryFollowupDraftParent = null,
            uncertain = false, continuationEnabled = mutableState.value.capabilities?.serverOwnedTurns == true, error = null,
            historyRefreshRequired = false,
            memoryReaderHandoff = null, memoryReaderOrdinal = null, memoryReaderError = null, memoryReaderErrorOrdinal = null,
        )
        val latest = detail.latestRequestId
        if (latest != null && mutableState.value.capabilities?.serverOwnedTurns == true) {
            val savedInput = detail.exchanges.firstOrNull { it.requestId == latest }?.inputText.orEmpty()
            val pending = AssistantWorkspacePendingTurn(
                detail.thread.threadId, latest, (detail.thread.revision - 1).coerceAtLeast(0), savedInput,
                searchVersion = if (mutableState.value.sceneSearchAvailable) 4 else mutableState.value.capabilities?.searchVersion ?: 1,
            )
            mutableState.value = mutableState.value.copy(pendingTurn = pending, uncertain = true)
            try { recoverInternal(scope, pending, detail) }
            catch (cancel: CancellationException) { throw cancel }
            catch (failure: ApiFailure) {
                requireCurrent(scope)
                if (authorizationDenied(failure) || failure.kind != FailureKind.HTTP || failure.status !in setOf(400, 404, 409, 503)) throw failure
                // A saved result that cannot be revalidated is not a new uncertain POST.
                mutableState.value = mutableState.value.copy(currentTurn = null, pendingTurn = null,
                    uncertain = false, continuationEnabled = true, error = AssistantWorkspaceError.CONTEXT_CHANGED)
            }
        }
    }

    /** Explicit text-only paging, anchored to the selected owned revision and cursor. */
    fun loadOlderHistory(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val snapshot = mutableState.value
        val detail = snapshot.detail ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        val before = detail.exchanges.firstOrNull()?.revision ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        if (snapshot.capabilities?.historyPaging != true || !detail.hasOlderExchanges ||
            snapshot.pendingTurn != null || snapshot.pendingCreationId != null || snapshot.historyRefreshRequired)
            throw ApiFailure(FailureKind.INVALID_INPUT)
        val page = try {
            api.readHistory(scope.bearer, scope.libraryId, detail.thread.threadId, before, detail.thread.revision)
        } catch (cancel: CancellationException) { throw cancel }
        catch (error: ApiFailure) {
            requireCurrent(scope)
            if (error.status == 409) mutableState.value = mutableState.value.copy(
                historyRefreshRequired = true, continuationEnabled = false)
            throw error
        }
        requireCurrent(scope)
        val latest = mutableState.value.detail ?: throw CancellationException("History selection changed")
        if (latest.thread.threadId != detail.thread.threadId || latest.thread.revision != detail.thread.revision ||
            latest.exchanges.firstOrNull()?.revision != before) throw CancellationException("History cursor changed")
        if (page.threadId != detail.thread.threadId || page.snapshotRevision != detail.thread.revision ||
            page.beforeRevision != before || page.exchanges.size > 20 ||
            page.exchanges.any { it.revision >= before } ||
            page.hasOlderExchanges && (page.exchanges.isEmpty() || page.nextBeforeRevision != page.exchanges.first().revision) ||
            !page.hasOlderExchanges && page.nextBeforeRevision != null)
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        val combined = page.exchanges + latest.exchanges
        if (combined.size > 200 || page.hasOlderExchanges && combined.size >= 200 || combined.map { it.exchangeId }.distinct().size != combined.size ||
            !combined.zipWithNext().all { (a, b) -> a.revision < b.revision }) throw ApiFailure(FailureKind.INVALID_RESPONSE)
        mutableState.value = mutableState.value.copy(detail = latest.copy(exchanges = combined,
            hasOlderExchanges = page.hasOlderExchanges), error = null)
    }

    fun sendTurn(requestId: String? = null, parentRequestId: String? = null): Boolean {
        onScopeChanged()
        val scope = usableScope() ?: return false
        synchronized(guard) {
            val current = mutableState.value
            val caps = current.capabilities
            val detail = current.detail
            if (closed || !api.assistantWorkspaceEnabled || current.busy || current.pendingTurn != null ||
                current.pendingCreationId != null || !current.continuationEnabled ||
                caps?.let { it.available && it.threads && it.serverOwnedTurns } != true || detail == null ||
                current.accountId != scope.accountId || current.libraryId != scope.libraryId ||
                current.generation != scope.generation || detail.thread.libraryId != scope.libraryId) return false
            val text = current.draft
            val request = requestId ?: runCatching(uuidFactory).getOrNull() ?: return false
            if (!AssistantWorkspaceWire.validUuid4(request) ||
                parentRequestId != null && !AssistantWorkspaceWire.validUuid4(parentRequestId)) return false
            val acceptMemoryCards = current.savedMemoryCardsAvailable
            val acceptMemoryActions = current.savedMemoryCardsAvailable && current.savedMemoryActionsAvailable
            // The parent is the latest fresh saved-memory result, not a property of
            // how the user populated the draft. This also covers typed and spoken
            // followups and drafts edited after a chip was tapped.
            val latestMemoryParent = current.currentTurn?.let { AssistantSavedMemoryParent(it.requestId, it.revision) }
                ?.takeIf { validCurrentMemoryParent(current, detail.thread, it) }
            val memoryParent = latestMemoryParent.takeIf {
                current.savedMemoryFollowupAvailable || current.savedMemoryActionsAvailable
            }
            try { AssistantWorkspaceWire.turnRequest(scope.libraryId, request, detail.thread.revision, text,
                acceptMemoryCards, memoryParent, acceptMemoryActions) }
            catch (_: ApiFailure) { return false }
            val pending = AssistantWorkspacePendingTurn(
                detail.thread.threadId, request, detail.thread.revision, text, parentRequestId, memoryParent,
                current.capabilities?.searchVersion ?: 1,
            )
            mutableState.value = current.copy(pendingTurn = pending, uncertain = true, busy = true, error = null,
                memoryFollowupDraftParent = null,
                memoryReaderHandoff = null, memoryReaderOrdinal = null, memoryReaderError = null, memoryReaderErrorOrdinal = null)
            launchReservedTurn(scope, pending, detail, acceptMemoryCards, acceptMemoryActions)
            return true
        }
    }

    /** Reserves visual wording against the current reviewed server-owned scope. */
    fun sendSceneTurn(): Boolean {
        onScopeChanged()
        val scope = usableScope() ?: return false
        synchronized(guard) {
            val current = mutableState.value
            if (closed || !api.assistantWorkspaceEnabled || !current.sceneReady ||
                current.accountId != scope.accountId || current.libraryId != scope.libraryId || current.generation != scope.generation ||
                !AssistantWorkspaceWire.validSceneQuery(current.sceneDraft)) return false
            val detail = current.detail ?: return false
            val result = current.currentTurn?.result ?: return false
            val original = if (result.searchVersion == 4) (result.context?.get("scene") as? JsonObject)?.get("scope") as? JsonObject else result.context
            if (original == null) return false
            val request = runCatching(uuidFactory).getOrNull() ?: return false
            if (!AssistantWorkspaceWire.validUuid4(request)) return false
            val pending = AssistantWorkspacePendingTurn(detail.thread.threadId, request, detail.thread.revision,
                current.sceneDraft, searchVersion = 4, scene = true, sceneScope = original)
            mutableState.value = current.copy(pendingTurn = pending, currentTurn = null, uncertain = true, busy = true,
                error = null, historyRefreshRequired = true, memoryFollowupDraftParent = null,
                memoryReaderHandoff = null, memoryReaderOrdinal = null, memoryReaderError = null, memoryReaderErrorOrdinal = null)
            launchReservedTurn(scope, pending, detail)
            return true
        }
    }

    /** Cancels only the local wait. It deliberately leaves the request identity recoverable by GET. */
    fun cancelWaitingForTurn(requestId: String): Boolean {
        onScopeChanged()
        synchronized(guard) {
            val pending = mutableState.value.pendingTurn
            val job = activeJob
            if (closed || pending?.requestId != requestId || job == null || !mutableState.value.busy) return false
            operationNonce++
            activeJob = null
            job.cancel(CancellationException("Local wait cancelled; server request may still commit"))
            mutableState.value = mutableState.value.copy(busy = false, uncertain = true)
            return true
        }
    }

    private fun launchReservedTurn(
        scope: AssistantWorkspaceScope,
        pending: AssistantWorkspacePendingTurn,
        detail: AssistantWorkspaceThreadDetail,
        acceptSavedMemoryCards: Boolean = false,
        acceptSavedMemoryActions: Boolean = false,
    ) {
        operationNonce++
        activeOperationNonce = operationNonce
        val operation = operationNonce
        val job = coroutineScope.launch(start = CoroutineStart.LAZY) {
            try {
                // Let the caller observe and bind the reserved request identity before I/O starts.
                yield()
                actionMutex.withLock {
                    requireCurrent(scope)
                    submitReservedTurn(scope, pending, detail, acceptSavedMemoryCards, acceptSavedMemoryActions)
                }
            } catch (cancel: CancellationException) { throw cancel }
            catch (error: Exception) {
                if (isCurrent(scope)) mutableState.value = if (authorizationDenied(error))
                    AssistantWorkspaceState(error = AssistantWorkspaceError.ACCESS_DENIED)
                else mutableState.value.copy(error = safeError(error))
            } finally {
                synchronized(guard) {
                    if (activeJob === coroutineContext[Job] && operation == operationNonce && !closed) {
                        mutableState.value = mutableState.value.copy(busy = false)
                        activeJob = null
                    }
                }
            }
        }
        activeJob = job
        job.start()
    }

    private suspend fun submitReservedTurn(
        scope: AssistantWorkspaceScope,
        pending: AssistantWorkspacePendingTurn,
        detail: AssistantWorkspaceThreadDetail,
        acceptSavedMemoryCards: Boolean,
        acceptSavedMemoryActions: Boolean,
    ) {
        val turn = try {
            if (pending.scene) api.submitSceneTurn(scope.bearer, scope.libraryId, pending.threadId, pending.requestId,
                pending.expectedRevision, pending.text)
            else api.submitTurn(scope.bearer, scope.libraryId, pending.threadId, pending.requestId,
                pending.expectedRevision, pending.text, pending.parentRequestId, acceptSavedMemoryCards, pending.memoryParent,
                acceptSavedMemoryActions, searchVersion = pending.searchVersion)
        } catch (cancel: CancellationException) { throw cancel }
        catch (postFailure: Exception) {
            requireCurrent(scope)
            if (authorizationDenied(postFailure)) throw postFailure
            if (pending.scene && postFailure is ApiFailure && postFailure.kind == FailureKind.HTTP && postFailure.status in setOf(400, 409)) {
                mutableState.value = mutableState.value.copy(pendingTurn = null, currentTurn = null, uncertain = false,
                    continuationEnabled = false, historyRefreshRequired = true, error = AssistantWorkspaceError.CONTEXT_CHANGED)
                return
            }
            mutableState.value = mutableState.value.copy(uncertain = true, error = safeError(postFailure))
            // A failed/ambiguous POST is reconciled by GET only, with the exact immutable identity.
            recoverInternal(scope, pending, detail)
            return
        }
        requireCurrent(scope)
        if (turn.status == AssistantWorkspaceRequestStatus.PENDING) {
            applyTurn(scope, pending, turn, detail)
            try {
                recoverInternal(scope, pending, detail)
            } catch (cancel: CancellationException) { throw cancel }
            catch (recoveryFailure: Exception) {
                requireCurrent(scope)
                mutableState.value = mutableState.value.copy(pendingTurn = pending, uncertain = true, error = safeError(recoveryFailure))
            }
            return
        }
        val latestDetail = if (turn.status == AssistantWorkspaceRequestStatus.COMPLETED) {
            try { api.readThread(scope.bearer, scope.libraryId, pending.threadId).also { requireCurrent(scope) } }
            catch (cancel: CancellationException) { throw cancel }
            catch (_: Exception) { detail }
        } else detail
        applyTurn(scope, pending, turn, latestDetail)
    }

    /** Explicit GET-only recovery for the exact pending immutable turn. */
    fun recoverPendingTurn(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val pending = mutableState.value.pendingTurn ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        recoverInternal(scope, pending, mutableState.value.detail)
    }

    /** Clears local blocking state only after the user acknowledges that the server may still commit. */
    fun abandonPendingTurn(acknowledgeServerMayCommit: Boolean): Boolean {
        onScopeChanged()
        synchronized(guard) {
            if (closed || mutableState.value.busy || mutableState.value.pendingTurn == null || !acknowledgeServerMayCommit) return false
            mutableState.value = mutableState.value.copy(pendingTurn = null, uncertain = false,
                continuationEnabled = false, error = AssistantWorkspaceError.CONTEXT_CHANGED)
            return true
        }
    }

    fun deleteCurrentThread(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        if (mutableState.value.pendingTurn != null) throw ApiFailure(FailureKind.INVALID_INPUT)
        val detail = mutableState.value.detail ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        val deleted = api.deleteThread(scope.bearer, scope.libraryId, detail.thread.threadId, detail.thread.revision)
        requireCurrent(scope)
        if (deleted.deleted && mutableState.value.detail?.thread?.threadId == detail.thread.threadId) {
            mutableState.value = mutableState.value.copy(
                detail = null, currentTurn = null, draft = "", sceneDraft = "", pendingCreationId = null, historyRefreshRequired = false,
                memoryFollowupDraftParent = null,
                pendingTurn = null, uncertain = false, continuationEnabled = false, error = null,
                memoryReaderHandoff = null, memoryReaderOrdinal = null, memoryReaderError = null, memoryReaderErrorOrdinal = null,
                threads = mutableState.value.threads?.let { list -> list.copy(threads = list.threads.filterNot { it.threadId == deleted.threadId }) },
            )
        }
    }

    fun refreshPreferences(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val caps = mutableState.value.capabilities ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        if (!caps.preferences) throw ApiFailure(FailureKind.INVALID_INPUT)
        val value = api.preferences(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(preferences = value, error = null)
    }

    fun updatePreferences(updates: Map<AssistantWorkspacePreference, String?>): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val caps = mutableState.value.capabilities ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        val current = mutableState.value.preferences ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        if (!caps.preferences || updates.isEmpty()) throw ApiFailure(FailureKind.INVALID_INPUT)
        val value = api.updatePreferences(scope.bearer, scope.libraryId, current.revision, updates.toMap())
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(preferences = value, error = null)
    }

    fun resetPreferences(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val caps = mutableState.value.capabilities ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        val current = mutableState.value.preferences ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        if (!caps.preferences) throw ApiFailure(FailureKind.INVALID_INPUT)
        val value = api.resetPreferences(scope.bearer, scope.libraryId, current.revision)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(preferences = value, error = null)
    }

    private suspend fun recoverInternal(
        scope: AssistantWorkspaceScope,
        pending: AssistantWorkspacePendingTurn,
        previousDetail: AssistantWorkspaceThreadDetail?,
    ) {
        val recovered = api.getTurn(scope.bearer, scope.libraryId, pending.threadId, pending.requestId,
            searchVersion = pending.searchVersion)
        requireCurrent(scope)
        if (!recovered.recovered) throw ApiFailure(FailureKind.INVALID_RESPONSE)
        if (recovered.status == AssistantWorkspaceRequestStatus.COMPLETED) {
            val fresh = api.readThread(scope.bearer, scope.libraryId, pending.threadId)
            requireCurrent(scope)
            applyTurn(scope, pending, recovered, fresh, previousDetail)
        } else {
            applyTurn(scope, pending, recovered, previousDetail ?: mutableState.value.detail)
        }
    }

    private suspend fun applyTurn(
        scope: AssistantWorkspaceScope,
        pending: AssistantWorkspacePendingTurn,
        turn: AssistantWorkspaceTurn,
        detail: AssistantWorkspaceThreadDetail?,
        oldDetail: AssistantWorkspaceThreadDetail? = null,
    ) {
        requireCurrent(scope)
        if (turn.recovered && (turn.result?.effect != null || turn.result?.kind == "open")) {
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        }
        if (pending.scene && turn.status == AssistantWorkspaceRequestStatus.COMPLETED) {
            val result = turn.result ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
            val scene = result.context?.get("scene") as? JsonObject
            if (result.searchVersion != 4 || result.sceneRanking?.query != pending.text ||
                turn.revision != pending.expectedRevision + 1 || scene?.get("scope") != pending.sceneScope)
                throw ApiFailure(FailureKind.INVALID_RESPONSE)
        }
        if (!pending.scene && pending.searchVersion == 4 && pending.text.isNotEmpty() &&
            turn.status == AssistantWorkspaceRequestStatus.COMPLETED && turn.result?.searchVersion == 4 &&
            (turn.result.sceneRanking?.query != pending.text || turn.revision != pending.expectedRevision + 1))
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        val safeTurn = turn
        when (safeTurn.status) {
            AssistantWorkspaceRequestStatus.PENDING -> mutableState.value = mutableState.value.copy(
                pendingTurn = pending, currentTurn = safeTurn, uncertain = true,
                error = AssistantWorkspaceError.NETWORK,
            )
            AssistantWorkspaceRequestStatus.FAILED -> mutableState.value = mutableState.value.copy(
                pendingTurn = null, currentTurn = safeTurn, uncertain = false,
                continuationEnabled = detail?.thread?.revision == safeTurn.revision,
                error = AssistantWorkspaceError.TURN_FAILED,
            )
            AssistantWorkspaceRequestStatus.INTERRUPTED -> mutableState.value = mutableState.value.copy(
                pendingTurn = null, currentTurn = safeTurn, uncertain = false,
                continuationEnabled = detail?.thread?.revision == safeTurn.revision,
                error = AssistantWorkspaceError.TURN_INTERRUPTED,
            )
            AssistantWorkspaceRequestStatus.COMPLETED -> {
                val revisionMatches = detail?.thread?.revision == safeTurn.revision
                val sceneResult = pending.scene || safeTurn.result?.searchVersion == 4
                val keepDraft = sceneResult || mutableState.value.draft != pending.text || !revisionMatches
                mutableState.value = mutableState.value.copy(
                    detail = detail ?: oldDetail ?: mutableState.value.detail,
                    historyRefreshRequired = false,
                    currentTurn = safeTurn,
                    pendingTurn = null,
                    uncertain = false,
                    draft = if (keepDraft) mutableState.value.draft else "",
                    sceneDraft = if (sceneResult && revisionMatches && mutableState.value.sceneDraft == pending.text) "" else mutableState.value.sceneDraft,
                    continuationEnabled = revisionMatches,
                    error = if (revisionMatches) null else AssistantWorkspaceError.CONTEXT_CHANGED,
                )
            }
        }
    }

    private fun prepareThreadSwitch(acknowledge: Boolean) {
        if (mutableState.value.pendingTurn != null) {
            if (!acknowledge) throw ApiFailure(FailureKind.INVALID_INPUT)
            mutableState.value = mutableState.value.copy(pendingTurn = null, uncertain = false,
                continuationEnabled = false, error = AssistantWorkspaceError.CONTEXT_CHANGED)
        }
    }

    private fun validCurrentMemoryParent(
        current: AssistantWorkspaceState,
        thread: AssistantWorkspaceThreadSummary,
        parent: AssistantSavedMemoryParent,
    ): Boolean {
        val turn = current.currentTurn ?: return false
        val result = turn.result ?: return false
        return turn.requestId == parent.requestId && turn.revision == parent.revision &&
            AssistantWorkspaceWire.validUuid4(parent.requestId) && parent.revision > 0 &&
            turn.threadId == thread.threadId && turn.status == AssistantWorkspaceRequestStatus.COMPLETED && !turn.recovered &&
            result.kind == "memory_cards" && result.memoryCards.isNotEmpty() &&
            result.savedMemoryContext?.libraryId == current.libraryId && thread.revision == turn.revision
    }

    private fun launchAction(block: suspend () -> Unit): Boolean {
        onScopeChanged()
        val captured = usableScope() ?: return false
        synchronized(guard) {
            if (closed || mutableState.value.busy || !api.assistantWorkspaceEnabled) return false
            mutableState.value = mutableState.value.copy(busy = true, error = null)
            operationNonce++
            activeOperationNonce = operationNonce
            val operation = operationNonce
            val job = coroutineScope.launch(start = CoroutineStart.LAZY) {
                try {
                    actionMutex.withLock {
                        requireCurrent(captured)
                        block()
                    }
                } catch (cancel: CancellationException) {
                    throw cancel
                } catch (error: Exception) {
                    if (isCurrent(captured)) {
                        mutableState.value = if (authorizationDenied(error))
                            AssistantWorkspaceState(error = AssistantWorkspaceError.ACCESS_DENIED)
                        else mutableState.value.copy(error = safeError(error))
                    }
                } finally {
                    synchronized(guard) {
                        if (activeJob === coroutineContext[Job] && operation == operationNonce && !closed) {
                            mutableState.value = mutableState.value.copy(busy = false)
                            activeJob = null
                        }
                    }
                }
            }
            activeJob = job
            job.start()
            return true
        }
    }

    private fun requireEnabled() {
        if (!api.assistantWorkspaceEnabled) throw ApiFailure(FailureKind.INVALID_INPUT)
    }

    private fun authorizationDenied(error: Exception) = error is ApiFailure &&
        error.kind == FailureKind.HTTP && error.status in setOf(401, 403)

    private fun requireUsableCapabilities(): AssistantWorkspaceScope {
        requireEnabled()
        val caps = mutableState.value.capabilities ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        if (!caps.available || !caps.threads) throw ApiFailure(FailureKind.INVALID_INPUT)
        return requireScope()
    }

    private fun requireScope(): AssistantWorkspaceScope = usableScope() ?: throw CancellationException("Workspace scope changed")

    private fun usableScope(): AssistantWorkspaceScope? = runCatching(currentScope).getOrNull()?.takeIf {
        it.foregroundAllowed && it.accountId.isNotBlank() && it.libraryId.isNotBlank() && it.generation >= 0
    }

    private suspend fun requireCurrent(scope: AssistantWorkspaceScope) {
        if (!scopeMatchesCurrent(scope)) {
            onScopeChanged()
            throw CancellationException("Workspace scope changed")
        }
        val job = coroutineContext[Job]
        val owned = synchronized(guard) {
            !closed && job != null && activeJob === job && activeOperationNonce == operationNonce
        }
        if (!owned) throw CancellationException("Workspace operation invalidated")
    }

    private suspend fun isCurrent(scope: AssistantWorkspaceScope): Boolean {
        if (!scopeMatchesCurrent(scope)) return false
        val job = coroutineContext[Job]
        return synchronized(guard) {
            !closed && job != null && activeJob === job && activeOperationNonce == operationNonce
        }
    }

    private fun scopeMatchesCurrent(scope: AssistantWorkspaceScope): Boolean = synchronized(guard) {
        !closed && sameScope(scopeKey, scope) && sameScope(scope, usableScope())
    }

    private fun sameScope(left: AssistantWorkspaceScope?, right: AssistantWorkspaceScope?): Boolean =
        left === right || left != null && right != null && left.accountId == right.accountId &&
            left.libraryId == right.libraryId && left.generation == right.generation &&
            left.foregroundAllowed == right.foregroundAllowed && left.bearer.header() == right.bearer.header()

    private fun safeError(error: Exception): AssistantWorkspaceError = when (error) {
        is ApiFailure -> when (error.kind) {
            FailureKind.OFFLINE, FailureKind.TLS -> AssistantWorkspaceError.NETWORK
            FailureKind.INVALID_RESPONSE, FailureKind.TOO_LARGE -> AssistantWorkspaceError.INVALID_RESPONSE
            FailureKind.INVALID_INPUT -> AssistantWorkspaceError.INVALID_REQUEST
            FailureKind.HTTP -> when (error.status) {
                401, 403, 404 -> AssistantWorkspaceError.ACCESS_DENIED
                409 -> AssistantWorkspaceError.CONTEXT_CHANGED
                429, 500, 502, 503, 504 -> AssistantWorkspaceError.UNAVAILABLE
                else -> AssistantWorkspaceError.UNKNOWN
            }
        }
        else -> AssistantWorkspaceError.UNKNOWN
    }

    override fun close() {
        synchronized(guard) {
            if (closed) return
            closed = true
            operationNonce++
            activeJob?.cancel()
            activeJob = null
            mutableState.value = AssistantWorkspaceState()
        }
    }
}
