package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

enum class MemoryBookEditionShelfStatus { CLOSED, CHECKING, UNAVAILABLE, LIST, READING, READ, SOURCE_CHANGED, FAILED }

data class MemoryBookEditionShelfState(
    val status: MemoryBookEditionShelfStatus = MemoryBookEditionShelfStatus.CLOSED,
    val page: Int = 1,
    val listing: MemoryBookEditionPage? = null,
    val selectedId: String? = null,
    val detail: MemoryBookEditionDetail? = null,
    val busy: Boolean = false,
)

/** An independent read-only surface. No constructor request, private job, save or persistent prose cache. */
class MemoryBookEditionShelfStore(
    private val repository: MemoryBookEditionRepository,
    private val scope: CoroutineScope,
    private val currentScope: () -> MemoryBookNarrativeScope?,
    private val onReadingInvalidated: () -> Unit,
) {
    constructor(repository: MemoryBookEditionRepository, scope: CoroutineScope,
                currentScope: () -> MemoryBookNarrativeScope?) : this(repository,scope,currentScope,{})

    private val mutable = MutableStateFlow(MemoryBookEditionShelfState())
    val state = mutable.asStateFlow()
    private var bound: MemoryBookNarrativeScope? = null
    private var action: Job? = null
    private var epoch = 0L

    private fun snapshot() = currentScope()?.let { it.copy(children = it.children.toList()) }
    private fun current(expected: MemoryBookNarrativeScope, ticket: Long) =
        epoch == ticket && bound == expected && snapshot() == expected

    fun clear() {
        onReadingInvalidated()
        epoch++; action?.cancel(); action = null; bound = null
        repository.clear(); mutable.value = MemoryBookEditionShelfState()
    }

    /** Closing a GET can cancel freely, without disturbing the editor's pending POST identity. */
    fun closeReading() {
        if (state.value.selectedId == null) return
        onReadingInvalidated()
        epoch++; action?.cancel(); action = null
        mutable.value = state.value.copy(status = MemoryBookEditionShelfStatus.LIST,
            selectedId = null, detail = null, busy = false)
    }

    fun loadPage(page: Int = 1): Boolean {
        if (page !in 1..100000 || state.value.busy) return false
        val expected = snapshot() ?: return false
        if (bound != expected) { clear(); bound = expected }
        onReadingInvalidated()
        val ticket = ++epoch
        // Discard previous prose and metadata before a freshly checked request.
        mutable.value = MemoryBookEditionShelfState(MemoryBookEditionShelfStatus.CHECKING, page, busy = true)
        action = scope.launch {
            try {
                val capabilities = repository.loadCapabilities(expected.bookId) { current(expected, ticket) }
                if (!current(expected, ticket)) return@launch
                if (!capabilities.enabled) {
                    mutable.value = MemoryBookEditionShelfState(MemoryBookEditionShelfStatus.UNAVAILABLE, page)
                    return@launch
                }
                val result = repository.loadPage(expected.bookId, page) { current(expected, ticket) }
                if (current(expected, ticket)) mutable.value = MemoryBookEditionShelfState(
                    MemoryBookEditionShelfStatus.LIST, page, listing = result)
            } catch (_: CancellationException) { stale(ticket) }
            catch (_: ApiFailure) {
                if (current(expected, ticket)) mutable.value = MemoryBookEditionShelfState(MemoryBookEditionShelfStatus.FAILED, page)
                else stale(ticket)
            } finally { if (ticket == epoch) action = null }
        }
        return true
    }

    fun read(editionId: String): Boolean {
        val expected = bound ?: return false
        if (!current(expected, epoch)) { clear(); return false }
        if (state.value.busy) return false
        val selected = state.value.listing?.items?.firstOrNull { it.receipt.id == editionId }?.receipt ?: return false
        onReadingInvalidated()
        val ticket = ++epoch
        // A metadata receipt (even current) does not authorize displaying prior prose.
        mutable.value = state.value.copy(status = MemoryBookEditionShelfStatus.READING,
            selectedId = editionId, detail = null, busy = true)
        action = scope.launch {
            try {
                val result = repository.loadReadableEdition(expected.bookId, editionId, expected.bookRevision,
                    expected.children.map { MemoryBookEditionChild(it.storyId, it.revision) }) { current(expected, ticket) }
                if (result.receipt.bookRevision != selected.bookRevision ||
                    result.receipt.createdAt != selected.createdAt || result.receipt.mutationId != selected.mutationId)
                    throw ApiFailure(FailureKind.INVALID_RESPONSE)
                if (current(expected, ticket)) mutable.value = state.value.copy(
                    status = if (result.manuscript == null) MemoryBookEditionShelfStatus.SOURCE_CHANGED else MemoryBookEditionShelfStatus.READ,
                    detail = result, busy = false)
            } catch (_: CancellationException) { stale(ticket) }
            catch (_: ApiFailure) {
                if (current(expected, ticket)) mutable.value = state.value.copy(
                    status = MemoryBookEditionShelfStatus.FAILED, detail = null, busy = false)
                else stale(ticket)
            } finally { if (ticket == epoch) action = null }
        }
        return true
    }

    /** A bound source read confirmed this edition is stale; hide its manuscript immediately. */
    fun invalidateReading() {
        onReadingInvalidated()
        epoch++; action?.cancel(); action = null
        mutable.value = state.value.copy(status = MemoryBookEditionShelfStatus.SOURCE_CHANGED,
            detail = null,busy = false)
    }

    private fun stale(ticket: Long) { if (ticket == epoch && bound?.let { !current(it, ticket) } == true) clear() }
}
