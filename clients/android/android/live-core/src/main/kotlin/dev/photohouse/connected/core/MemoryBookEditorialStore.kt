package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.UUID

/** Complete authorization and source context required for one editorial request. */
data class MemoryBookEditorialContext(
    val sessionId: String,
    val token: Bearer,
    val library: String,
    val bookId: String,
    val bookRevision: String,
    val children: List<EditorialChild>,
    val eligibleSources: Set<EditorialSourceIdentity>,
)

data class MemoryBookEditorialDraft(
    val introductionSourceRefs: List<EditorialSourceIdentity>,
    val transitions: List<EditorialTransition>,
)

enum class MemoryBookEditorialStoreStatus {
    NO_CONTEXT, LOADING, READY, SAVING, UNAVAILABLE, ACCESS_REVOKED, CONFLICT, INVALID, ERROR, SAVE_UNCERTAIN,
}

data class MemoryBookEditorialStoreState(
    val status: MemoryBookEditorialStoreStatus = MemoryBookEditorialStoreStatus.NO_CONTEXT,
    val revision: String? = null,
    val serverEditorial: MemoryBookEditorial? = null,
    val draft: MemoryBookEditorialDraft? = null,
    val dirty: Boolean = false,
    val errorStatus: Int? = null,
)

/**
 * Process-memory-only draft and request coordinator. It never retries by itself; callers must invoke
 * [retryUncertainSave] after an uncertain save result. No token or personal text is logged or persisted.
 */
class MemoryBookEditorialStore(
    private val repository: MemoryBookEditorialRepository,
    private val mutationId: () -> String = { UUID.randomUUID().toString() },
) {
    private data class ContextSnapshot(
        val sessionId: String,
        val token: Bearer,
        val library: String,
        val bookId: String,
        val bookRevision: String,
        val children: List<EditorialChild>,
        val eligibleSources: Set<EditorialSourceIdentity>,
    ) {
        fun withRevision(value: String) = copy(bookRevision = value)
    }

    private data class FrozenSave(
        val context: ContextSnapshot,
        val mutation: MemoryBookEditorialMutation,
        val draftVersion: Long,
        val generation: Long,
    )

    private val mutableState = MutableStateFlow(MemoryBookEditorialStoreState())
    val state: StateFlow<MemoryBookEditorialStoreState> = mutableState.asStateFlow()

    private var context: ContextSnapshot? = null
    private var generation = 0L
    private var draftVersion = 0L
    private var frozenSave: FrozenSave? = null
    private var requestPending = false

    /** Replaces the live request context. Child/source/revision changes preserve edits as a conflict. */
    @Synchronized
    fun setContext(value: MemoryBookEditorialContext?) {
        val next = value?.snapshot()
        if (context == next) return
        generation++
        requestPending = false
        frozenSave = null
        val old = context
        context = next
        if (next == null) {
            draftVersion++
            mutableState.value = MemoryBookEditorialStoreState()
            return
        }
        val sameScope = old != null && old.sessionId == next.sessionId && old.library == next.library &&
            old.bookId == next.bookId && old.token === next.token
        val sameEditorialBasis = sameScope && old!!.bookRevision == next.bookRevision &&
            old.children == next.children && old.eligibleSources == next.eligibleSources
        if (sameEditorialBasis) return
        if (!sameScope || mutableState.value.draft == null || !mutableState.value.dirty) {
            draftVersion++
            mutableState.value = MemoryBookEditorialStoreState()
        } else {
            draftVersion++
            mutableState.value = mutableState.value.copy(
                status = MemoryBookEditorialStoreStatus.CONFLICT,
                revision = next.bookRevision,
                serverEditorial = null,
                dirty = true,
                errorStatus = null,
            )
        }
    }

    /** Replaces editable sections with defensive copies. */
    @Synchronized
    fun edit(introductionSourceRefs: List<EditorialSourceIdentity>, transitions: List<EditorialTransition>) {
        val current = mutableState.value
        if (context == null || current.draft == null || current.status in setOf(
                MemoryBookEditorialStoreStatus.ACCESS_REVOKED,
                MemoryBookEditorialStoreStatus.CONFLICT,
                MemoryBookEditorialStoreStatus.UNAVAILABLE,
            )) return
        draftVersion++
        mutableState.value = current.copy(
            status = when {
                current.status == MemoryBookEditorialStoreStatus.SAVING -> MemoryBookEditorialStoreStatus.SAVING
                frozenSave != null -> MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN
                else -> MemoryBookEditorialStoreStatus.READY
            },
            draft = draftCopy(introductionSourceRefs, transitions),
            dirty = true,
            errorStatus = null,
        )
    }

    /** Loads explicitly. A dirty draft is kept and a successful read becomes a conflict for review. */
    suspend fun load() {
        val captured: ContextSnapshot
        val capturedGeneration: Long
        val dirtyAtStart: Boolean
        val draftVersionAtStart: Long
        val previousState: MemoryBookEditorialStoreState
        synchronized(this) {
            captured = context ?: return
            if (requestPending || frozenSave != null) return
            if (mutableState.value.status == MemoryBookEditorialStoreStatus.CONFLICT &&
                mutableState.value.revision != captured.bookRevision) return
            requestPending = true
            capturedGeneration = generation
            previousState = mutableState.value
            dirtyAtStart = mutableState.value.dirty
            draftVersionAtStart = draftVersion
            mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.LOADING, errorStatus = null)
        }
        try {
            val result = repository.get(captured.token, captured.library, captured.bookId, captured.bookRevision,
                captured.children, captured.eligibleSources)
            synchronized(this) {
                if (!isCurrent(capturedGeneration, captured)) return
                requestPending = false
                when {
                    result == null -> mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.UNAVAILABLE)
                    dirtyAtStart || draftVersion != draftVersionAtStart -> mutableState.value = mutableState.value.copy(
                        status = MemoryBookEditorialStoreStatus.CONFLICT,
                        serverEditorial = editorialCopy(result),
                        revision = result.revision,
                        dirty = true,
                    )
                    else -> {
                        val copy = editorialCopy(result)
                        mutableState.value = MemoryBookEditorialStoreState(
                            status = if (copy.state == EditorialState.SOURCE_CHANGED)
                                MemoryBookEditorialStoreStatus.CONFLICT else MemoryBookEditorialStoreStatus.READY,
                            revision = copy.revision,
                            serverEditorial = copy,
                            draft = editableDraft(copy),
                        )
                        draftVersion++
                    }
                }
            }
        } catch (cancelled: CancellationException) {
            synchronized(this) {
                if (isCurrent(capturedGeneration, captured)) {
                    requestPending = false
                    mutableState.value = if (draftVersion == draftVersionAtStart) previousState
                    else mutableState.value.copy(status = previousState.status)
                }
            }
            throw cancelled
        } catch (failure: Exception) {
            synchronized(this) {
                if (!isCurrent(capturedGeneration, captured)) return
                requestPending = false
                applyFailure(failure, preserveDraft = true)
            }
        }
    }

    /** Starts one new explicit mutation. Concurrent calls while a request is pending are ignored. */
    suspend fun save() {
        val frozen = synchronized(this) {
            val c = context ?: return
            val current = mutableState.value
            if (requestPending || frozenSave != null || current.draft == null || !current.dirty || current.revision == null ||
                current.status in setOf(MemoryBookEditorialStoreStatus.CONFLICT, MemoryBookEditorialStoreStatus.ACCESS_REVOKED,
                    MemoryBookEditorialStoreStatus.UNAVAILABLE, MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN)) return
            val mutation = MemoryBookEditorialMutation(
                current.revision,
                mutationId(),
                c.children.toList(),
                current.draft.introductionSourceRefs.toList(),
                current.draft.transitions.map(::transitionCopy),
            )
            FrozenSave(c, mutation, draftVersion, generation).also {
                frozenSave = it
                requestPending = true
                mutableState.value = current.copy(status = MemoryBookEditorialStoreStatus.SAVING, errorStatus = null)
            }
        }
        performSave(frozen)
    }

    /** Explicitly resends the exact frozen mutation after a caller has handled an uncertain result. */
    suspend fun retryUncertainSave() {
        val frozen = synchronized(this) {
            val c = context ?: return
            val request = frozenSave ?: return
            if (requestPending || mutableState.value.status != MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN ||
                !isSameRequestContext(request.context, c)) return
            requestPending = true
            mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.SAVING, errorStatus = null)
            request
        }
        performSave(frozen)
    }

    /** Clears sensitive read state and invalidates every outstanding response. */
    @Synchronized
    fun clear() {
        generation++
        context = null
        frozenSave = null
        requestPending = false
        draftVersion++
        mutableState.value = MemoryBookEditorialStoreState()
    }

    /** Explicitly drops local edits after the caller has presented the conflict to the user. */
    @Synchronized
    fun discardDraft() {
        val current = mutableState.value
        if (!current.dirty || current.status == MemoryBookEditorialStoreStatus.SAVING || frozenSave != null) return
        draftVersion++
        val server = current.serverEditorial
        mutableState.value = current.copy(
            status = when {
                server == null -> current.status
                server.state == EditorialState.SOURCE_CHANGED -> MemoryBookEditorialStoreStatus.CONFLICT
                else -> MemoryBookEditorialStoreStatus.READY
            },
            draft = server?.let(::editableDraft),
            dirty = false,
            errorStatus = null,
        )
    }

    /** Explicitly accepts a source_changed server basis after the caller has reviewed the warning. */
    @Synchronized
    fun acceptCurrentServerBasis() {
        val current = mutableState.value
        val server = current.serverEditorial ?: return
        if (frozenSave != null || requestPending || server.state != EditorialState.SOURCE_CHANGED ||
            current.status != MemoryBookEditorialStoreStatus.CONFLICT) return
        draftVersion++
        mutableState.value = current.copy(
            status = MemoryBookEditorialStoreStatus.READY,
            draft = editableDraft(server),
            dirty = true,
            errorStatus = null,
        )
    }

    /** Applies a user-reviewed draft only against an explicitly reloaded current basis. */
    @Synchronized
    fun applyReviewedDraft(
        introductionSourceRefs: List<EditorialSourceIdentity>, transitions: List<EditorialTransition>,
    ): Boolean {
        val captured = context ?: return false
        val current = mutableState.value
        val server = current.serverEditorial ?: return false
        if (requestPending || frozenSave != null || current.status != MemoryBookEditorialStoreStatus.CONFLICT ||
            server.bookId != captured.bookId || server.revision != captured.bookRevision ||
            server.children != captured.children) return false
        val draft = draftCopy(introductionSourceRefs, transitions)
        val validation = MemoryBookEditorialMutation(server.revision,
            "00000000-0000-0000-0000-000000000000", captured.children,
            draft.introductionSourceRefs, draft.transitions)
        try {
            MemoryBookEditorialWire.encodeMutation(validation, captured.children, captured.eligibleSources)
        } catch (_: Exception) {
            return false
        }
        draftVersion++
        mutableState.value = current.copy(status = MemoryBookEditorialStoreStatus.READY,
            revision = server.revision, draft = draft, dirty = true, errorStatus = null)
        return true
    }

    private suspend fun performSave(request: FrozenSave) {
        val requestGeneration = request.generation
        try {
            // Validate before entering the API call so local input errors are known not to have been sent.
            MemoryBookEditorialWire.encodeMutation(request.mutation, request.context.children, request.context.eligibleSources)
        } catch (_: Exception) {
            synchronized(this) {
                if (isCurrent(requestGeneration, request.context)) {
                    requestPending = false
                    frozenSave = null
                    mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.INVALID)
                }
            }
            return
        }
        try {
            val result = repository.save(request.context.token, request.context.library, request.context.bookId,
                request.mutation, request.context.children, request.context.eligibleSources)
            synchronized(this) {
                if (!isCurrent(requestGeneration, request.context)) return
                requestPending = false
                if (result == null) {
                    // An unavailable optional endpoint is not a mutation receipt. Keep the
                    // exact request until explicit retry or a refreshed context resolves it.
                    mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN)
                    return
                }
                val copy = editorialCopy(result)
                if (copy.state == EditorialState.SOURCE_CHANGED) {
                    frozenSave = null
                    mutableState.value = mutableState.value.copy(
                        status = MemoryBookEditorialStoreStatus.CONFLICT,
                        serverEditorial = null,
                        revision = copy.revision,
                        dirty = true,
                    )
                    return
                }
                context = context!!.withRevision(copy.revision)
                val stillSameDraft = draftVersion == request.draftVersion
                mutableState.value = mutableState.value.copy(
                    status = MemoryBookEditorialStoreStatus.READY,
                    revision = copy.revision,
                    serverEditorial = copy,
                    draft = mutableState.value.draft,
                    dirty = !stillSameDraft,
                    errorStatus = null,
                )
                if (stillSameDraft) {
                    mutableState.value = mutableState.value.copy(draft = editableDraft(copy))
                    draftVersion++
                }
                frozenSave = null
            }
        } catch (cancelled: CancellationException) {
            synchronized(this) {
                if (isCurrent(requestGeneration, request.context)) {
                    requestPending = false
                    mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN)
                }
            }
            throw cancelled
        } catch (failure: Exception) {
            synchronized(this) {
                if (!isCurrent(requestGeneration, request.context)) return
                requestPending = false
                when (failure) {
                    is ApiFailure -> when {
                        failure.status == 409 -> {
                            frozenSave = null
                            mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.CONFLICT,
                                serverEditorial = null, dirty = true, errorStatus = 409)
                        }
                        failure.status == 401 || failure.status == 403 -> {
                            revokeAccess(failure.status)
                        }
                        failure.kind == FailureKind.OFFLINE || failure.kind == FailureKind.TLS ||
                            failure.kind == FailureKind.INVALID_RESPONSE || failure.kind == FailureKind.TOO_LARGE -> {
                            mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN,
                                errorStatus = failure.status)
                        }
                        failure.kind == FailureKind.INVALID_INPUT -> {
                            frozenSave = null
                            mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.INVALID,
                                errorStatus = failure.status)
                        }
                        failure.status != null && failure.status >= 500 -> {
                            mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN,
                                errorStatus = failure.status)
                        }
                        else -> {
                            frozenSave = null
                            mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.ERROR,
                                errorStatus = failure.status)
                        }
                    }
                    else -> mutableState.value = mutableState.value.copy(status = MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN)
                }
            }
        }
    }

    private fun applyFailure(failure: Exception, preserveDraft: Boolean) {
        val status = (failure as? ApiFailure)?.status
        if (status == 401 || status == 403) {
            revokeAccess(status)
            return
        }
        val nextStatus = when {
            status == 409 -> MemoryBookEditorialStoreStatus.CONFLICT
            failure is ApiFailure && failure.kind == FailureKind.INVALID_INPUT -> MemoryBookEditorialStoreStatus.INVALID
            else -> MemoryBookEditorialStoreStatus.ERROR
        }
        mutableState.value = mutableState.value.copy(
            status = nextStatus,
            serverEditorial = if (status == 409) null else mutableState.value.serverEditorial,
            dirty = preserveDraft && mutableState.value.draft != null && mutableState.value.dirty,
            errorStatus = status,
        )
    }

    private fun revokeAccess(status: Int) {
        generation++
        context = null
        frozenSave = null
        requestPending = false
        draftVersion++
        mutableState.value = MemoryBookEditorialStoreState(
            status = MemoryBookEditorialStoreStatus.ACCESS_REVOKED,
            errorStatus = status,
        )
    }

    @Synchronized
    private fun isCurrent(requestGeneration: Long, captured: ContextSnapshot): Boolean =
        generation == requestGeneration && context?.let { isSameRequestContext(captured, it) } == true

    private fun isSameRequestContext(a: ContextSnapshot, b: ContextSnapshot): Boolean =
        a.sessionId == b.sessionId && a.token === b.token && a.library == b.library && a.bookId == b.bookId &&
            a.bookRevision == b.bookRevision && a.children == b.children && a.eligibleSources == b.eligibleSources

    private fun MemoryBookEditorialContext.snapshot() = ContextSnapshot(sessionId, token, library, bookId,
        bookRevision, children.toList(), eligibleSources.toSet())

    private fun draftCopy(intro: List<EditorialSourceIdentity>, transitions: List<EditorialTransition>) =
        MemoryBookEditorialDraft(intro.toList(), transitions.map(::transitionCopy))

    private fun editableDraft(value: MemoryBookEditorial): MemoryBookEditorialDraft {
        val transitions = if (value.state == EditorialState.CURRENT) value.transitions else
            value.children.zipWithNext { left, right -> EditorialTransition(left.storyId, right.storyId, "", emptyList()) }
        return draftCopy(value.introductionSourceRefs, transitions)
    }

    private fun transitionCopy(value: EditorialTransition) = value.copy(sourceRefs = value.sourceRefs.toList())

    private fun editorialCopy(value: MemoryBookEditorial) = value.copy(
        children = value.children.toList(),
        introductionSourceRefs = value.introductionSourceRefs.toList(),
        transitions = value.transitions.map(::transitionCopy),
    )
}
