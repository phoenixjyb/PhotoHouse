package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class MemoryBookEditionRepositoryTest {
    private val book = "11111111-1111-4111-8111-111111111111"
    private val story = "22222222-2222-4222-8222-222222222222"
    private val job = "33333333-3333-4333-8333-333333333333"
    private val edition = "44444444-4444-4444-8444-444444444444"
    private val mutation = "55555555-5555-4555-8555-555555555555"
    private val chapter = "$story-chapter-1"
    private fun token() = Bearer.from(SessionToken(86400, "a".repeat(43), "Bearer"))
    private val manuscript get() = """{"version":1,"title":"Family edition","chapters":[{"id":"$chapter","narration":"A remembered day","source_ids":["caption-101"]}],"questions":[],"needs_review":true}"""
    private fun receipt(state: String = "current", mutationId: String = mutation) =
        """{"version":1,"id":"$edition","book_id":"$book","book_revision":"7","created_at":100,"state":"$state","mutation_id":"$mutationId"}"""
    private fun proposal() = MemoryBookEditionProposal(book, "7", job, "a".repeat(64), "b".repeat(64), "stories",
        listOf(MemoryBookEditionChild(story, "2")), MemoryBookEditionManuscript("Family edition",
            listOf(MemoryBookEditionChapter(chapter, "A remembered day", listOf("caption-101"))), emptyList()), true)

    private inner class Fake : MemoryBookEditionApi {
        var caps = """{"version":1,"enabled":true,"can_save":true}"""
        var response = receipt()
        var detail = """${receipt().dropLast(1)},"manuscript":$manuscript}"""
        var page = """{"version":1,"book_id":"$book","page":1,"page_size":8,"has_more":false,"items":[${receipt().dropLast(1)},"manuscript":null}]}"""
        var error: ApiFailure? = null
        var afterResponse: (() -> Unit)? = null
        var buffer: ByteArray? = null
        val submissions = mutableListOf<String>()
        var reads = 0
        private fun bytes(value: String): ByteArray {
            afterResponse?.invoke()
            return value.toByteArray().also { buffer = it }
        }
        override suspend fun editionCapabilities(token: Bearer, library: String, bookId: String) = bytes(caps)
        override suspend fun editionProposal(token: Bearer, library: String, bookId: String, jobId: String): ByteArray {
            reads++
            return bytes("""{"version":1,"book_id":"$book","revision":"7","job_id":"$job","job_result_sha256":"${"a".repeat(64)}","source_fingerprint":"${"b".repeat(64)}","context_profile":"stories","children":[{"id":"$story","revision":"2"}],"manuscript":$manuscript,"needs_review":true}""")
        }
        override suspend fun saveEdition(token: Bearer, library: String, bookId: String, json: String): ByteArray {
            submissions += json
            error?.let { afterResponse?.invoke(); throw it }
            return bytes(response)
        }
        override suspend fun editionPage(token: Bearer, library: String, bookId: String, page: Int): ByteArray { reads++; return bytes(this.page) }
        override suspend fun editionDetail(token: Bearer, library: String, bookId: String, editionId: String): ByteArray { reads++; return bytes(detail) }
    }

    @Test fun defaultOffStopsProposalAndSaveAndWipesCapabilityBytes() = runBlocking {
        val api = Fake().apply { caps = """{"version":1,"enabled":false,"can_save":false}""" }
        val binding = MemoryCommunityBinding(token(), "family-a", 1)
        val repo = MemoryBookEditionRepository(api, { binding })
        assertFalse(repo.loadCapabilities(book) { true }.enabled)
        assertTrue(api.buffer!!.all { it == 0.toByte() })
        assertFailure(503) { repo.loadProposal(book, 7, job, proposal().children, listOf(chapter)) { true } }
        assertFailure(503) { repo.freeze(proposal(), mutation, proposal().manuscript, true) { true } }
        assertEquals(0, api.reads)
        assertTrue(api.submissions.isEmpty())
    }

    @Test fun reviewedRequestIsFrozenAndExplicitRetriesKeepIdenticalBytesEvenAfterInvalidation() = runBlocking {
        val api = Fake()
        val binding = MemoryCommunityBinding(token(), "family-a", 3)
        val repo = MemoryBookEditionRepository(api, { binding })
        repo.loadCapabilities(book) { true }
        val p = repo.loadProposal(book, 7, job, proposal().children, listOf(chapter)) { true }
        assertTrue(api.buffer!!.all { it == 0.toByte() })
        assertFailureKind(FailureKind.INVALID_INPUT) { repo.freeze(p, mutation, p.manuscript, false) { true } }
        val pending = repo.freeze(p, mutation, p.manuscript.copy(title = "Reviewed family words"), true) { true }
        assertFalse(pending.toString().contains("Reviewed family words"))
        api.error = ApiFailure(FailureKind.OFFLINE)
        assertFailureKind(FailureKind.OFFLINE) { repo.save(pending) { true } }
        api.error = null
        api.response = receipt("source_invalidated")
        assertEquals(MemoryBookEditionState.SOURCE_INVALIDATED, repo.save(pending) { true }.state)
        assertEquals(2, api.submissions.size)
        assertEquals(api.submissions[0], api.submissions[1])
        assertTrue(api.buffer!!.all { it == 0.toByte() })
    }

    @Test fun malformedReceiptNeverReplacesTheFrozenRequest() = runBlocking {
        val api = Fake()
        val binding = MemoryCommunityBinding(token(), "family-a", 1)
        val repo = MemoryBookEditionRepository(api, { binding })
        repo.loadCapabilities(book) { true }
        val pending = repo.freeze(proposal(), mutation, proposal().manuscript, true) { true }
        api.response = receipt(mutationId = job)
        assertFailureKind(FailureKind.INVALID_RESPONSE) { repo.save(pending) { true } }
        assertTrue(api.buffer!!.all { it == 0.toByte() })
        api.response = receipt()
        assertEquals(edition, repo.save(pending) { true }.id)
        assertEquals(api.submissions[0], api.submissions[1])
    }

    @Test fun changedAccountOrReaderDropsLateResponsesAndClearedCapabilitiesBlockWrites() = runBlocking {
        val api = Fake()
        var binding = MemoryCommunityBinding(token(), "family-a", 1)
        var reader = true
        val repo = MemoryBookEditionRepository(api, { binding })
        repo.loadCapabilities(book) { reader }
        val pending = repo.freeze(proposal(), mutation, proposal().manuscript, true) { reader }
        api.afterResponse = { reader = false }
        assertCancelled { repo.save(pending) { reader } }
        assertTrue(api.buffer!!.all { it == 0.toByte() })
        reader = true; api.afterResponse = null; binding = binding.copy(generation = 2)
        assertCancelled { repo.save(pending) { reader } }
        assertEquals(1, api.submissions.size)
        repo.loadCapabilities(book) { reader }; repo.clear()
        assertFailureKind(FailureKind.INVALID_INPUT) { repo.freeze(proposal(), mutation, proposal().manuscript, true) { reader } }
    }

    @Test fun deniedCurrentRequestNotifiesOnceButStaleDenialCannotLockNewSession() = runBlocking {
        val api = Fake()
        var binding = MemoryCommunityBinding(token(), "family-a", 1)
        var denied = 0
        val repo = MemoryBookEditionRepository(api, { binding }, { denied++ })
        repo.loadCapabilities(book) { true }
        val pending = repo.freeze(proposal(), mutation, proposal().manuscript, true) { true }
        api.error = ApiFailure(FailureKind.HTTP, 403)
        assertFailure(403) { repo.save(pending) { true } }
        assertEquals(1, denied)
        api.afterResponse = { binding = binding.copy(generation = 2) }
        assertCancelled { repo.save(pending) { true } }
        assertEquals(1, denied)
    }

    @Test fun approvedReaderCanReadWithoutSavePermissionAndInvalidatedDetailsRemainEmpty() = runBlocking {
        val api = Fake().apply { caps = """{"version":1,"enabled":true,"can_save":false}""" }
        val binding = MemoryCommunityBinding(token(), "family-a", 1)
        val repo = MemoryBookEditionRepository(api, { binding })
        repo.loadCapabilities(book) { true }
        assertEquals(edition, repo.loadPage(book, 1) { true }.items.single().receipt.id)
        assertEquals("Family edition", repo.loadEdition(book, edition, 7, listOf(chapter)) { true }.manuscript?.title)
        api.detail = """${receipt("source_invalidated").dropLast(1)},"manuscript":null}"""
        assertNull(repo.loadEdition(book, edition, 7, listOf(chapter)) { true }.manuscript)
        assertFailure(503) { repo.freeze(proposal(), mutation, proposal().manuscript, true) { true } }
        assertTrue(api.submissions.isEmpty())
    }

    private suspend fun assertFailure(status: Int, block: suspend () -> Unit) {
        try { block(); fail("expected HTTP failure") } catch (failure: ApiFailure) { assertEquals(status, failure.status) }
    }
    private suspend fun assertFailureKind(kind: FailureKind, block: suspend () -> Unit) {
        try { block(); fail("expected failure") } catch (failure: ApiFailure) { assertEquals(kind, failure.kind) }
    }
    private suspend fun assertCancelled(block: suspend () -> Unit) {
        try { block(); fail("expected stale scope cancellation") } catch (_: CancellationException) { }
    }
}
