package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Private request identity; its credential and material are never published or persisted. */
data class MemoryBookEditionSourceScope(
    val book: MemoryBookNarrativeScope, val editionId: String, val citedSources: List<String>,
) { override fun toString() = "MemoryBookEditionSourceScope(private)" }

enum class MemoryBookEditionSourceStatus { CLOSED, LOADING_LIST, LIST, LOADING_DETAIL, DETAIL, LOADING_AUDIO, AUDIO_READY, FAILED, UNAVAILABLE, SOURCE_CHANGED }
data class MemoryBookEditionSourceState(
    val status: MemoryBookEditionSourceStatus = MemoryBookEditionSourceStatus.CLOSED,
    val page: Int = 1, val listing: MemoryBookEditionSourcePage? = null, val selectedId: String? = null,
    val detail: MemoryBookEditionSourceDetail? = null, val audio: ProtectedAnnotationAudio? = null,
    val busy: Boolean = false,
)

/** Explicit GET-only coordinator. Parent reader calls clear before changing edition or reading scope. */
class MemoryBookEditionSourceStore(
    private val repository: MemoryBookEditionSourceRepository,
    private val scope: CoroutineScope,
    private val currentScope: () -> MemoryBookEditionSourceScope?,
    private val onEditionInvalidated: () -> Unit = {},
) {
    private val mutable = MutableStateFlow(MemoryBookEditionSourceState())
    val state = mutable.asStateFlow()
    private var bound: MemoryBookEditionSourceScope? = null
    private var action: Job? = null
    private var epoch = 0L
    private fun snapshot() = currentScope()?.let { it.copy(book = it.book.copy(children = it.book.children.toList()), citedSources = it.citedSources.toList()) }
    private fun current(expected: MemoryBookEditionSourceScope, ticket: Long) = ticket == epoch && bound == expected && snapshot() == expected
    fun clear() {
        epoch++; action?.cancel(); action = null; bound = null
        state.value.audio?.close(); mutable.value = MemoryBookEditionSourceState()
    }
    private fun bind(): MemoryBookEditionSourceScope? {
        val expected = snapshot() ?: run { clear(); return null }
        if (bound != expected) { clear(); bound = expected }
        return expected
    }
    private fun changed() {
        state.value.audio?.close()
        mutable.value = MemoryBookEditionSourceState(MemoryBookEditionSourceStatus.SOURCE_CHANGED)
        onEditionInvalidated()
    }
    private fun failure(expected: MemoryBookEditionSourceScope, ticket: Long, error: ApiFailure) {
        if (!current(expected,ticket)) { stale(ticket); return }
        state.value.audio?.close()
        if (error.status == 409) { changed(); return }
        mutable.value = state.value.copy(status = if (error.status in setOf(404,503))
            MemoryBookEditionSourceStatus.UNAVAILABLE else MemoryBookEditionSourceStatus.FAILED,
            detail = null,audio = null,busy = false)
    }
    private fun stale(ticket: Long) { if (ticket == epoch && bound?.let { !current(it,ticket) } == true) clear() }
    fun loadPage(page: Int = 1): Boolean {
        if (page !in 1..100000 || state.value.busy) return false
        val expected = bind() ?: return false; val ticket = ++epoch
        state.value.audio?.close()
        mutable.value = MemoryBookEditionSourceState(MemoryBookEditionSourceStatus.LOADING_LIST,page,busy = true)
        action = scope.launch {
            try {
                val listing = repository.page(expected,page) { current(expected,ticket) }
                if (!current(expected,ticket)) return@launch
                if (listing.state != MemoryBookEditionState.CURRENT) changed()
                else mutable.value = MemoryBookEditionSourceState(MemoryBookEditionSourceStatus.LIST,page,listing)
            } catch (_: CancellationException) { stale(ticket) }
            catch (error: ApiFailure) { failure(expected,ticket,error) }
            finally { if (ticket == epoch) action = null }
        }
        return true
    }
    fun read(sourceId: String): Boolean {
        if (!MemoryBookEditionSourceWire.validSourceId(sourceId) || state.value.busy) return false
        val expected = bind() ?: return false
        val listed = state.value.listing?.items?.any { it.sourceId == sourceId } == true
        if (!listed && sourceId !in expected.citedSources) return false
        val ticket = ++epoch; state.value.audio?.close()
        mutable.value = state.value.copy(status = MemoryBookEditionSourceStatus.LOADING_DETAIL,
            selectedId = sourceId,detail = null,audio = null,busy = true)
        action = scope.launch {
            try {
                val detail = repository.detail(expected,sourceId) { current(expected,ticket) }
                if (!current(expected,ticket)) return@launch
                if (detail.state != MemoryBookEditionState.CURRENT) changed()
                else mutable.value = state.value.copy(status = MemoryBookEditionSourceStatus.DETAIL,detail = detail,busy = false)
            } catch (_: CancellationException) { stale(ticket) }
            catch (error: ApiFailure) { failure(expected,ticket,error) }
            finally { if (ticket == epoch) action = null }
        }
        return true
    }
    fun loadAudio(): Boolean {
        if (state.value.busy) return false
        val expected = bound ?: return false
        if (!current(expected,epoch)) { clear(); return false }
        val detail = state.value.detail?.takeIf { it.state == MemoryBookEditionState.CURRENT } ?: return false
        if (detail.source?.audioAvailable != true) return false
        val sourceId = detail.sourceId; val ticket = ++epoch
        state.value.audio?.close()
        mutable.value = state.value.copy(status = MemoryBookEditionSourceStatus.LOADING_AUDIO,audio = null,busy = true)
        action = scope.launch {
            var owned: ProtectedAnnotationAudio? = null
            try {
                owned = repository.audio(expected,sourceId) { current(expected,ticket) }
                if (!current(expected,ticket)) return@launch
                mutable.value = state.value.copy(status = MemoryBookEditionSourceStatus.AUDIO_READY,audio = owned,busy = false)
                owned = null
            } catch (_: CancellationException) { stale(ticket) }
            catch (error: ApiFailure) { failure(expected,ticket,error) }
            finally { owned?.close(); if (ticket == epoch) action = null }
        }
        return true
    }
    fun closeAudio() {
        epoch++; action?.cancel(); action = null; state.value.audio?.close()
        mutable.value = state.value.copy(status = if (state.value.detail != null) MemoryBookEditionSourceStatus.DETAIL
            else if (state.value.listing != null) MemoryBookEditionSourceStatus.LIST else MemoryBookEditionSourceStatus.CLOSED,
            audio = null,busy = false)
    }
}
