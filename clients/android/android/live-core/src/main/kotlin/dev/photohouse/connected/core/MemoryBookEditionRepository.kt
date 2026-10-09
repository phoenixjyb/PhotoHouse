package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

/** Optional, authenticated HTTPS seam; existing community adapters stay source compatible. */
interface MemoryBookEditionApi {
    suspend fun editionCapabilities(token: Bearer, library: String, bookId: String): ByteArray
    suspend fun editionProposal(token: Bearer, library: String, bookId: String, jobId: String): ByteArray
    suspend fun saveEdition(token: Bearer, library: String, bookId: String, json: String): ByteArray
    suspend fun editionPage(token: Bearer, library: String, bookId: String, page: Int): ByteArray
    suspend fun editionDetail(token: Bearer, library: String, bookId: String, editionId: String): ByteArray
}

/** One immutable request identity. Its body contains family prose and is never printed or persisted here. */
class PendingMemoryBookEditionSave internal constructor(
    val bookId: String,
    val bookRevision: Long,
    val mutationId: String,
    internal val binding: MemoryCommunityBinding,
    internal val body: String,
) {
    override fun toString() = "PendingMemoryBookEditionSave(content omitted)"
}

/** Ephemeral scope coordinator: no automatic adoption/retry, model request, recording or local storage. */
class MemoryBookEditionRepository(
    private val api: MemoryBookEditionApi,
    private val currentBinding: () -> MemoryCommunityBinding?,
    private val onDenied: () -> Unit = {},
) {
    private data class Capabilities(
        val binding: MemoryCommunityBinding, val bookId: String, val value: MemoryBookEditionCapabilities,
    )
    private var capabilities: Capabilities? = null

    fun clear() { capabilities = null }

    private fun binding(): MemoryCommunityBinding =
        (currentBinding() ?: throw CancellationException("Protected scope ended")).also {
            require(PhoneDiscoveryWire.validLibrary(it.libraryId) && it.generation >= 0)
        }

    private fun current(expected: MemoryCommunityBinding, readerCurrent: () -> Boolean) {
        val now = currentBinding()
        if (now == null || now.token !== expected.token || now.libraryId != expected.libraryId ||
            now.generation != expected.generation || !readerCurrent()) {
            throw CancellationException("Protected memoir scope changed")
        }
    }

    private suspend fun <T> inScope(
        readerCurrent: () -> Boolean, block: suspend (MemoryCommunityBinding) -> T,
    ): T {
        val expected = binding()
        current(expected, readerCurrent)
        return try {
            val value = block(expected)
            currentCoroutineContext().ensureActive()
            current(expected, readerCurrent)
            value
        } catch (failure: CancellationException) {
            throw failure
        } catch (failure: ApiFailure) {
            currentCoroutineContext().ensureActive()
            current(expected, readerCurrent)
            if (failure.status in setOf(401, 403)) onDenied()
            throw failure
        } catch (_: IllegalArgumentException) {
            current(expected, readerCurrent)
            throw ApiFailure(FailureKind.INVALID_INPUT)
        }
    }

    private suspend fun <T> parseOwned(request: suspend () -> ByteArray, decode: (ByteArray) -> T): T {
        val bytes = request()
        return try { decode(bytes) } finally { bytes.fill(0) }
    }

    private fun enabled(scope: MemoryCommunityBinding, bookId: String, save: Boolean = false) {
        val cached = capabilities
        if (cached == null || cached.binding.token !== scope.token ||
            cached.binding.libraryId != scope.libraryId || cached.binding.generation != scope.generation ||
            cached.bookId != bookId) throw ApiFailure(FailureKind.INVALID_INPUT)
        if (!cached.value.enabled || save && !cached.value.canSave) throw ApiFailure(FailureKind.HTTP, 503)
    }

    suspend fun loadCapabilities(bookId: String, readerCurrent: () -> Boolean): MemoryBookEditionCapabilities =
        inScope(readerCurrent) { scope ->
            // Older servers lack this optional route. No write fallback is provided.
            val value = try {
                parseOwned({ api.editionCapabilities(scope.token, scope.libraryId, bookId) },
                    MemoryBookEditionWire::decodeCapabilities)
            } catch (failure: ApiFailure) {
                if (failure.status in setOf(404, 503)) MemoryBookEditionCapabilities(false, false) else throw failure
            }
            current(scope, readerCurrent)
            capabilities = Capabilities(scope, bookId, value)
            value
        }

    suspend fun loadProposal(
        bookId: String, revision: Long, jobId: String, children: List<MemoryBookEditionChild>,
        chapterIds: List<String>, readerCurrent: () -> Boolean,
    ): MemoryBookEditionProposal {
        val childSnapshot = children.toList()
        val chapterSnapshot = chapterIds.toList()
        return inScope(readerCurrent) { scope ->
            enabled(scope, bookId, save = true)
            parseOwned({ api.editionProposal(scope.token, scope.libraryId, bookId, jobId) }) {
                MemoryBookEditionWire.decodeProposal(it, bookId, revision, jobId, childSnapshot, chapterSnapshot)
            }
        }
    }

    fun freeze(
        proposal: MemoryBookEditionProposal, mutationId: String,
        manuscript: MemoryBookEditionManuscript, reviewed: Boolean, readerCurrent: () -> Boolean,
    ): PendingMemoryBookEditionSave {
        val scope = binding()
        current(scope, readerCurrent)
        enabled(scope, proposal.bookId, save = true)
        val body = try { MemoryBookEditionWire.encodeSaveRequest(proposal, mutationId, manuscript, reviewed) }
        catch (_: IllegalArgumentException) { throw ApiFailure(FailureKind.INVALID_INPUT) }
        current(scope, readerCurrent)
        return PendingMemoryBookEditionSave(proposal.bookId, proposal.revision.toLong(), mutationId, scope, body)
    }

    suspend fun save(pending: PendingMemoryBookEditionSave, readerCurrent: () -> Boolean): MemoryBookEditionReceipt =
        inScope(readerCurrent) { scope ->
            current(pending.binding, readerCurrent)
            enabled(scope, pending.bookId, save = true)
            // Each call is explicit. A lost or invalid receipt leaves this exact pending body reusable.
            parseOwned({ api.saveEdition(scope.token, scope.libraryId, pending.bookId, pending.body) }) {
                MemoryBookEditionWire.decodeReceipt(it, pending.bookId, pending.mutationId, pending.bookRevision)
            }
        }

    suspend fun loadPage(bookId: String, page: Int, readerCurrent: () -> Boolean): MemoryBookEditionPage =
        inScope(readerCurrent) { scope ->
            enabled(scope, bookId)
            parseOwned({ api.editionPage(scope.token, scope.libraryId, bookId, page) }) {
                MemoryBookEditionWire.decodePage(it, bookId, page)
            }
        }

    suspend fun loadEdition(
        bookId: String, editionId: String, revision: Long, chapterIds: List<String>, readerCurrent: () -> Boolean,
    ): MemoryBookEditionDetail {
        val chapterSnapshot = chapterIds.toList()
        return inScope(readerCurrent) { scope ->
            enabled(scope, bookId)
            parseOwned({ api.editionDetail(scope.token, scope.libraryId, bookId, editionId) }) {
                MemoryBookEditionWire.decodeDetail(it, bookId, editionId, revision, chapterSnapshot)
            }
        }
    }

    /** Independent family reading checks enabled, never save permission or a private generation job. */
    suspend fun loadReadableEdition(
        bookId: String, editionId: String, revision: Long, children: List<MemoryBookEditionChild>,
        readerCurrent: () -> Boolean,
    ): MemoryBookEditionDetail {
        val childSnapshot = children.toList()
        return inScope(readerCurrent) { scope ->
            enabled(scope, bookId)
            parseOwned({ api.editionDetail(scope.token, scope.libraryId, bookId, editionId) }) {
                MemoryBookEditionWire.decodeReadableDetail(it, bookId, editionId, revision, childSnapshot)
            }
        }
    }
}
