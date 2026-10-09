package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.UUID

enum class MemoryBookEditionStatus {
    IDLE, CHECKING, REVIEW, INVALID, SAVING, SAVE_UNCERTAIN, CONFLICT,
    SAVED, READING, SOURCE_CHANGED, READ_UNAVAILABLE, UNAVAILABLE,
}

data class MemoryBookEditionStoreState(
    val status: MemoryBookEditionStatus = MemoryBookEditionStatus.IDLE,
    val proposal: MemoryBookEditionProposal? = null,
    val manuscript: MemoryBookEditionManuscript? = null,
    val receipt: MemoryBookEditionReceipt? = null,
    val dirty: Boolean = false,
    val reviewed: Boolean = false,
    val composing: Boolean = false,
    val invalidInput: Boolean = false,
    val busy: Boolean = false,
    val hasPendingSave: Boolean = false,
) {
    val hasUnfinishedWork get() = dirty || composing || invalidInput || busy || hasPendingSave
}

/** A process-memory editor. Every transition to durable text requires explicit review and save. */
class MemoryBookEditionStore(
    private val repository: MemoryBookEditionRepository,
    private val scope: CoroutineScope,
    private val currentScope: () -> MemoryBookNarrativeScope?,
    private val mutationId: () -> String = { UUID.randomUUID().toString() },
) {
    private val mutable = MutableStateFlow(MemoryBookEditionStoreState())
    val state = mutable.asStateFlow()
    private var bound: MemoryBookNarrativeScope? = null
    private var chapterIds: List<String> = emptyList()
    private var pending: PendingMemoryBookEditionSave? = null
    private var action: Job? = null
    private var epoch = 0L

    fun clear() {
        epoch++
        action?.cancel(); action = null
        bound = null; chapterIds = emptyList(); pending = null
        repository.clear()
        mutable.value = MemoryBookEditionStoreState()
    }

    private fun snapshot() = currentScope()?.let { it.copy(children = it.children.toList()) }
    private fun current(expected: MemoryBookNarrativeScope, ticket: Long = epoch) =
        ticket == epoch && bound == expected && snapshot() == expected

    private fun readyForEdit(): Boolean {
        val expected = bound ?: return false
        if (!current(expected)) { clear(); return false }
        return !state.value.busy && pending == null && state.value.receipt == null &&
            state.value.status in setOf(MemoryBookEditionStatus.REVIEW, MemoryBookEditionStatus.INVALID)
    }

    /** Explicitly opens a private proposal. A completed model job never calls this method itself. */
    fun open(jobId: String, expectedChapterIds: List<String>): Boolean {
        if (state.value.hasUnfinishedWork) return false
        val expected = snapshot() ?: return false
        clear()
        bound = expected
        chapterIds = expectedChapterIds.toList()
        val ids = chapterIds
        val ticket = epoch
        mutable.value = MemoryBookEditionStoreState(status = MemoryBookEditionStatus.CHECKING, busy = true)
        action = scope.launch {
            try {
                val capability = repository.loadCapabilities(expected.bookId) { current(expected, ticket) }
                if (!current(expected, ticket)) return@launch
                if (!capability.enabled || !capability.canSave) {
                    mutable.value = MemoryBookEditionStoreState(status = MemoryBookEditionStatus.UNAVAILABLE)
                    return@launch
                }
                val proposal = repository.loadProposal(expected.bookId, expected.bookRevision, jobId,
                    expected.children.map { MemoryBookEditionChild(it.storyId, it.revision) }, ids) { current(expected, ticket) }
                if (current(expected, ticket)) mutable.value = MemoryBookEditionStoreState(
                    status = MemoryBookEditionStatus.REVIEW, proposal = proposal, manuscript = detached(proposal.manuscript))
            } catch (failure: CancellationException) { stale(ticket) }
            catch (failure: ApiFailure) {
                if (current(expected, ticket)) mutable.value = MemoryBookEditionStoreState(status =
                    if (failure.status == 409) MemoryBookEditionStatus.CONFLICT else MemoryBookEditionStatus.UNAVAILABLE)
                else stale(ticket)
            } finally { if (ticket == epoch) action = null }
        }
        return true
    }

    private fun validText(text: String, maxBytes: Int, nonblank: Boolean = false): Boolean = try {
        val bytes = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(text)).remaining()
        bytes <= maxBytes && (!nonblank || text.isNotBlank()) &&
            text.none { it == '\u0000' || it.isISOControl() && it !in "\n\t" }
    } catch (_: Exception) { false }

    fun editTitle(text: String): Boolean {
        if (!readyForEdit() || !validText(text, 512)) return false
        val draft = state.value.manuscript ?: return false
        edited(draft.copy(title = text)); return true
    }

    fun editChapter(index: Int, text: String): Boolean {
        if (!readyForEdit() || !validText(text, 6000)) return false
        val draft = state.value.manuscript ?: return false
        if (index !in draft.chapters.indices) return false
        edited(draft.copy(chapters = draft.chapters.mapIndexed { i, chapter ->
            if (i == index) chapter.copy(narration = text) else chapter
        })); return true
    }

    private fun edited(manuscript: MemoryBookEditionManuscript) {
        mutable.value = state.value.copy(status = MemoryBookEditionStatus.REVIEW, manuscript = detached(manuscript),
            dirty = true, reviewed = false)
    }

    fun composition(active: Boolean) {
        if (readyForEdit()) mutable.value = state.value.copy(composing = active,
            reviewed = if (active) false else state.value.reviewed)
    }

    /** A rejected field remains visible in Compose; it must not save the last accepted text. */
    fun invalidInput(active: Boolean) {
        if (readyForEdit()) mutable.value = state.value.copy(invalidInput = active,
            dirty = state.value.dirty || active, reviewed = if (active) false else state.value.reviewed)
    }

    fun confirmReviewed(value: Boolean): Boolean {
        if (!readyForEdit() || state.value.composing || state.value.invalidInput) return false
        mutable.value = state.value.copy(reviewed = value); return true
    }

    fun save(): Boolean {
        if (!readyForEdit() || state.value.composing || state.value.invalidInput || !state.value.reviewed) return false
        val expected = bound ?: return false
        val proposal = state.value.proposal ?: return false
        val manuscript = state.value.manuscript ?: return false
        pending = try {
            repository.freeze(proposal, mutationId(), manuscript, true) { current(expected) }
        } catch (_: CancellationException) { clear(); return false }
        catch (_: ApiFailure) {
            mutable.value = state.value.copy(status = MemoryBookEditionStatus.INVALID, reviewed = false)
            return false
        }
        return submitPending()
    }

    fun retrySave(): Boolean = if (state.value.status == MemoryBookEditionStatus.SAVE_UNCERTAIN) submitPending() else false

    private fun submitPending(): Boolean {
        val frozen = pending ?: return false
        val expected = bound ?: return false
        if (!current(expected) || state.value.busy) return false
        val ticket = epoch
        mutable.value = state.value.copy(status = MemoryBookEditionStatus.SAVING, busy = true, hasPendingSave = true)
        action = scope.launch {
            try {
                val receipt = repository.save(frozen) { current(expected, ticket) }
                if (current(expected, ticket)) {
                    pending = null
                    mutable.value = MemoryBookEditionStoreState(status = MemoryBookEditionStatus.SAVED, receipt = receipt)
                }
            } catch (_: CancellationException) { stale(ticket) }
            catch (failure: ApiFailure) {
                if (!current(expected, ticket)) { stale(ticket); return@launch }
                val knownRejection = failure.status in setOf(400, 413)
                if (knownRejection) pending = null
                mutable.value = state.value.copy(status = when {
                    failure.status == 409 -> MemoryBookEditionStatus.CONFLICT
                    knownRejection -> MemoryBookEditionStatus.INVALID
                    else -> MemoryBookEditionStatus.SAVE_UNCERTAIN
                }, busy = false, hasPendingSave = !knownRejection,
                    reviewed = if (knownRejection) false else state.value.reviewed)
            } finally { if (ticket == epoch) action = null }
        }
        return true
    }

    /** Discard needs an explicit decision; an uncertain save must first be resolved with the same request. */
    fun close(confirmed: Boolean): Boolean {
        if (state.value.busy || pending != null && state.value.status != MemoryBookEditionStatus.CONFLICT ||
            state.value.composing || state.value.dirty && !confirmed) return false
        clear(); return true
    }

    /** Content-free save success is separate from this explicitly requested, freshly checked read. */
    fun readSaved(): Boolean {
        val receipt = state.value.receipt ?: return false
        val expected = bound ?: return false
        if (!current(expected) || state.value.busy || pending != null) return false
        val ids = chapterIds.toList()
        val ticket = epoch
        mutable.value = state.value.copy(status = MemoryBookEditionStatus.READING, manuscript = null, busy = true)
        action = scope.launch {
            try {
                val detail = repository.loadEdition(expected.bookId, receipt.id, expected.bookRevision, ids) { current(expected, ticket) }
                if (current(expected, ticket)) mutable.value = MemoryBookEditionStoreState(
                    status = if (detail.manuscript == null) MemoryBookEditionStatus.SOURCE_CHANGED else MemoryBookEditionStatus.SAVED,
                    receipt = detail.receipt, manuscript = detail.manuscript?.let(::detached))
            } catch (_: CancellationException) { stale(ticket) }
            catch (_: ApiFailure) {
                if (current(expected, ticket)) mutable.value = state.value.copy(
                    status = MemoryBookEditionStatus.READ_UNAVAILABLE, manuscript = null, busy = false)
                else stale(ticket)
            } finally { if (ticket == epoch) action = null }
        }
        return true
    }

    private fun stale(ticket: Long) { if (ticket == epoch && bound?.let { !current(it, ticket) } == true) clear() }
    private fun detached(value: MemoryBookEditionManuscript) = value.copy(
        chapters = value.chapters.map { it.copy(sourceIds = it.sourceIds.toList()) }, questions = value.questions.toList())
}
