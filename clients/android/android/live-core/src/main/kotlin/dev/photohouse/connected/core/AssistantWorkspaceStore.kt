package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.UUID

/** The exact authenticated foreground owner for one private workspace operation. */
data class AssistantWorkspaceScope(
    val accountId: String,
    val bearer: Bearer,
    val libraryId: String,
    val generation: Long,
    val foregroundAllowed: Boolean,
)

enum class AssistantWorkspaceError {
    UNAVAILABLE, ACCESS_DENIED, INVALID_REQUEST, CONTEXT_CHANGED,
    NETWORK, INVALID_RESPONSE, TURN_FAILED, TURN_INTERRUPTED, UNKNOWN,
}

data class AssistantWorkspacePendingTurn(
    val threadId: String,
    val requestId: String,
    val expectedRevision: Long,
    val text: String,
)

data class AssistantWorkspaceState(
    val accountId: String? = null,
    val libraryId: String? = null,
    val generation: Long? = null,
    val capabilities: AssistantWorkspaceCapabilities? = null,
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
)

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

    private var epoch = 0L
    private var scopeKey: AssistantWorkspaceScope? = null
    private var activeJob: Job? = null
    private var closed = false

    /** Called by the owner whenever account, library, generation, or foreground status changes. */
    fun onScopeChanged() {
        val next = usableScope()
        synchronized(guard) {
            if (closed || sameScope(scopeKey, next)) return
            epoch++
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
            if (!closed && usableScope() != null) mutableState.value = mutableState.value.copy(draft = text)
        }
    }

    fun refreshCapabilities(): Boolean = launchAction {
        val scope = requireScope()
        requireEnabled()
        val value = api.capabilities(scope.bearer, scope.libraryId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(
            capabilities = value,
            unsupportedPreferences = AssistantWorkspacePreference.entries.toSet() -
                if ("locale" in value.appliedPreferences) setOf(AssistantWorkspacePreference.LOCALE) else emptySet(),
            error = if (value.available && value.threads && value.serverOwnedTurns) null else AssistantWorkspaceError.UNAVAILABLE,
        )
    }

    fun refreshThreads(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val value = api.listThreads(scope.bearer, scope.libraryId)
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
                currentTurn = null, uncertain = false, continuationEnabled = true, error = null,
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

    private fun adoptCreatedThread(scope: AssistantWorkspaceScope, detail: AssistantWorkspaceThreadDetail) {
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(pendingCreationId = null, detail = detail,
            currentTurn = null, uncertain = false, continuationEnabled = detail.thread.revision == 0L,
            error = if (detail.thread.revision == 0L) null else AssistantWorkspaceError.CONTEXT_CHANGED)
    }

    fun openThread(threadId: String, acknowledgeUncertainTurnMayCommit: Boolean = false): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        prepareThreadSwitch(acknowledgeUncertainTurnMayCommit)
        if (!AssistantWorkspaceWire.validUuid4(threadId)) throw ApiFailure(FailureKind.INVALID_INPUT)
        val detail = api.readThread(scope.bearer, scope.libraryId, threadId)
        requireCurrent(scope)
        mutableState.value = mutableState.value.copy(
            detail = detail, currentTurn = null, pendingCreationId = null,
            uncertain = false, continuationEnabled = true, error = null,
        )
        val latest = detail.latestRequestId
        if (latest != null) {
            val savedInput = detail.exchanges.firstOrNull { it.requestId == latest }?.inputText.orEmpty()
            val pending = AssistantWorkspacePendingTurn(
                detail.thread.threadId, latest, (detail.thread.revision - 1).coerceAtLeast(0), savedInput,
            )
            mutableState.value = mutableState.value.copy(pendingTurn = pending, uncertain = true)
            recoverInternal(scope, pending, detail)
        }
    }

    fun sendTurn(): Boolean = launchAction {
        val scope = requireUsableCapabilities()
        val detail = mutableState.value.detail ?: throw ApiFailure(FailureKind.INVALID_INPUT)
        if (!mutableState.value.continuationEnabled || mutableState.value.pendingTurn != null ||
            mutableState.value.pendingCreationId != null) throw ApiFailure(FailureKind.INVALID_INPUT)
        val text = mutableState.value.draft
        if (text.isBlank() || text.toByteArray(Charsets.UTF_8).size !in 1..1024) throw ApiFailure(FailureKind.INVALID_INPUT)
        val pending = AssistantWorkspacePendingTurn(detail.thread.threadId, uuidFactory(), detail.thread.revision, text)
        if (!AssistantWorkspaceWire.validUuid4(pending.requestId)) throw ApiFailure(FailureKind.INVALID_INPUT)
        mutableState.value = mutableState.value.copy(pendingTurn = pending, uncertain = true, error = null)
        val turn = try {
            api.submitTurn(scope.bearer, scope.libraryId, pending.threadId, pending.requestId,
                pending.expectedRevision, pending.text)
        } catch (cancel: CancellationException) { throw cancel }
        catch (postFailure: Exception) {
            requireCurrent(scope)
            if (authorizationDenied(postFailure)) throw postFailure
            mutableState.value = mutableState.value.copy(uncertain = true, error = safeError(postFailure))
            // A failed/ambiguous POST is reconciled by GET only, with the exact immutable identity.
            recoverInternal(scope, pending, detail)
            return@launchAction
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
            return@launchAction
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
                detail = null, currentTurn = null, draft = "", pendingCreationId = null,
                pendingTurn = null, uncertain = false, continuationEnabled = false, error = null,
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
        val recovered = api.getTurn(scope.bearer, scope.libraryId, pending.threadId, pending.requestId)
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
                val keepDraft = mutableState.value.draft != pending.text || !revisionMatches
                mutableState.value = mutableState.value.copy(
                    detail = detail ?: oldDetail ?: mutableState.value.detail,
                    currentTurn = safeTurn,
                    pendingTurn = null,
                    uncertain = false,
                    draft = if (keepDraft) mutableState.value.draft else "",
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

    private fun launchAction(block: suspend () -> Unit): Boolean {
        onScopeChanged()
        val captured = usableScope() ?: return false
        synchronized(guard) {
            if (closed || mutableState.value.busy || !api.assistantWorkspaceEnabled) return false
            mutableState.value = mutableState.value.copy(busy = true, error = null)
            val ticket = epoch
            activeJob = coroutineScope.launch {
                try {
                    actionMutex.withLock {
                        requireCurrent(captured, ticket)
                        block()
                    }
                } catch (cancel: CancellationException) {
                    throw cancel
                } catch (error: Exception) {
                    if (isCurrent(captured, ticket)) {
                        mutableState.value = if (authorizationDenied(error))
                            AssistantWorkspaceState(error = AssistantWorkspaceError.ACCESS_DENIED)
                        else mutableState.value.copy(error = safeError(error))
                    }
                } finally {
                    synchronized(guard) {
                        if (ticket == epoch && !closed) {
                            mutableState.value = mutableState.value.copy(busy = false)
                            activeJob = null
                        }
                    }
                }
            }
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
        if (!caps.available || !caps.threads || !caps.serverOwnedTurns) throw ApiFailure(FailureKind.INVALID_INPUT)
        return requireScope()
    }

    private fun requireScope(): AssistantWorkspaceScope = usableScope() ?: throw CancellationException("Workspace scope changed")

    private fun usableScope(): AssistantWorkspaceScope? = runCatching(currentScope).getOrNull()?.takeIf {
        it.foregroundAllowed && it.accountId.isNotBlank() && it.libraryId.isNotBlank() && it.generation >= 0
    }

    private fun requireCurrent(scope: AssistantWorkspaceScope, ticket: Long = epoch) {
        if (!isCurrent(scope, ticket)) {
            onScopeChanged()
            throw CancellationException("Workspace scope changed")
        }
    }

    private fun isCurrent(scope: AssistantWorkspaceScope, ticket: Long = epoch): Boolean = synchronized(guard) {
        !closed && ticket == epoch && sameScope(scope, usableScope())
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
            epoch++
            activeJob?.cancel()
            activeJob = null
            mutableState.value = AssistantWorkspaceState()
        }
    }
}
