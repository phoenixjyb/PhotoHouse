package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

/** Transient original inspection, authenticated only through the exact selected edition. */
class MemoryBookEditionSourceRepository(
    private val api: MemoryBookEditionSourceApi,
    private val currentBinding: () -> MemoryCommunityBinding?,
    private val onDenied: () -> Unit = {},
) {
    private fun current(scope: MemoryBookEditionSourceScope, readerCurrent: () -> Boolean) {
        val binding = currentBinding()
        if (binding == null || binding.token !== scope.book.credential || binding.libraryId != scope.book.library ||
            binding.generation != scope.book.generation || !readerCurrent())
            throw CancellationException("Protected source scope changed")
    }
    private suspend fun <T> inScope(expected: MemoryBookEditionSourceScope, readerCurrent: () -> Boolean,
                                   block: suspend () -> T): T {
        current(expected,readerCurrent)
        return try {
            val value = block()
            try { currentCoroutineContext().ensureActive(); current(expected,readerCurrent) }
            catch (e: Exception) { (value as? ProtectedAnnotationAudio)?.close(); throw e }
            value
        } catch (e: CancellationException) { throw e }
        catch (e: ApiFailure) {
            currentCoroutineContext().ensureActive(); current(expected,readerCurrent)
            if (e.status in setOf(401,403)) onDenied()
            throw e
        }
    }
    private suspend fun <T> parseOwned(request: suspend () -> ByteArray, parse: (ByteArray) -> T): T {
        val bytes = request()
        return try { parse(bytes) } finally { bytes.fill(0) }
    }
    suspend fun page(expected: MemoryBookEditionSourceScope, page: Int, readerCurrent: () -> Boolean) =
        inScope(expected,readerCurrent) {
            parseOwned({ api.editionSources(expected.book.credential,expected.book.library,expected.book.bookId,expected.editionId,page) }) {
                MemoryBookEditionSourceWire.decodePage(it,expected.book.bookId,expected.editionId,expected.book.bookRevision,page,expected.book.children.map { child -> child.storyId })
            }
        }
    suspend fun detail(expected: MemoryBookEditionSourceScope, sourceId: String, readerCurrent: () -> Boolean) =
        inScope(expected,readerCurrent) {
            parseOwned({ api.editionSource(expected.book.credential,expected.book.library,expected.book.bookId,expected.editionId,sourceId) }) {
                MemoryBookEditionSourceWire.decodeDetail(it,expected.book.bookId,expected.editionId,expected.book.bookRevision,
                    sourceId,expected.book.children.map { child -> child.storyId })
            }
        }
    suspend fun audio(expected: MemoryBookEditionSourceScope, sourceId: String, readerCurrent: () -> Boolean) =
        inScope(expected,readerCurrent) {
            val bytes = api.editionSourceAudio(expected.book.credential,expected.book.library,expected.book.bookId,expected.editionId,sourceId)
            try {
                if (bytes.size > 2 * 1024 * 1024 || !ProtectedMemoryCommunityWire.validWav(bytes,30))
                    throw ApiFailure(FailureKind.INVALID_RESPONSE)
                ProtectedAnnotationAudio(bytes.copyOf())
            } finally { bytes.fill(0) }
        }
}
