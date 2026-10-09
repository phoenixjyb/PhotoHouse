package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryBookEditionShelfStoreTest {
    private val book = "11111111-1111-4111-8111-111111111111"
    private val story = "22222222-2222-4222-8222-222222222222"
    private val edition = "33333333-3333-4333-8333-333333333333"
    private val mutation = "44444444-4444-4444-8444-444444444444"
    private fun context() = MemoryBookNarrativeScope("synthetic-reader",
        Bearer.from(SessionToken(86400, "a".repeat(43), "Bearer")), "family-a", 1,
        book, 7, listOf(EditorialChild(story, "2")), 10)
    private fun receipt(state: String = "current", createdAt: Long = 100) =
        """{"version":1,"id":"$edition","book_id":"$book","book_revision":"7","created_at":$createdAt,"state":"$state","mutation_id":"$mutation"}"""
    private val manuscript get() =
        """{"version":1,"title":"家人核对的版本","chapters":[{"id":"$story-chapter-1","narration":"有来源的家庭讲述。","source_ids":["caption-101"]}],"questions":["是哪一年？"],"needs_review":true}"""
    private inner class Fake : MemoryBookEditionApi {
        var enabled = true
        var capabilitiesReads = 0
        val pages = mutableListOf<Int>()
        var detailReads = 0
        var detailState = "current"
        var detailCreatedAt = 100L
        var detailFailure: ApiFailure? = null
        var pageFailure: ApiFailure? = null
        var gate: CompletableDeferred<Unit>? = null
        var lastBytes: ByteArray? = null
        private fun bytes(text: String) = text.toByteArray().also { lastBytes = it }
        override suspend fun editionCapabilities(token: Bearer, library: String, bookId: String): ByteArray {
            capabilitiesReads++
            return bytes("""{"version":1,"enabled":$enabled,"can_save":false}""")
        }
        override suspend fun editionProposal(token: Bearer, library: String, bookId: String, jobId: String): ByteArray = error("reader never loads a proposal")
        override suspend fun saveEdition(token: Bearer, library: String, bookId: String, json: String): ByteArray = error("reader never saves")
        override suspend fun editionPage(token: Bearer, library: String, bookId: String, page: Int): ByteArray {
            pages += page; pageFailure?.let { throw it }
            return bytes("""{"version":1,"book_id":"$book","page":$page,"page_size":8,"has_more":false,"items":[${receipt().dropLast(1)},"manuscript":null}]}""")
        }
        override suspend fun editionDetail(token: Bearer, library: String, bookId: String, editionId: String): ByteArray {
            detailReads++
            // Deliberately return after cancellation to exercise late-response fences.
            gate?.let { withContext(NonCancellable) { it.await() } }
            detailFailure?.let { throw it }
            return bytes("""${receipt(detailState, detailCreatedAt).dropLast(1)},"manuscript":${if (detailState == "current") manuscript else "null"}}""")
        }
    }
    private fun repository(api: Fake, current: () -> MemoryBookNarrativeScope?, denied: () -> Unit = {}) =
        MemoryBookEditionRepository(api, { current()?.let { MemoryCommunityBinding(it.credential, it.library, it.generation) } }, denied)

    @Test fun readerOnlyCanExplicitlyListAndReadWithNoJobOrGenerationAndOwnedBytesAreWiped() = runTest {
        val current = context(); val api = Fake()
        val store = MemoryBookEditionShelfStore(repository(api, current = { current }), this) { current }
        assertEquals(0, api.capabilitiesReads); assertTrue(api.pages.isEmpty())
        assertTrue(store.loadPage()); runCurrent()
        assertEquals(MemoryBookEditionShelfStatus.LIST, store.state.value.status)
        assertNull(store.state.value.listing!!.items.single().manuscript)
        assertTrue(api.lastBytes!!.all { it == 0.toByte() })
        assertTrue(store.read(edition)); runCurrent()
        assertEquals("家人核对的版本", store.state.value.detail!!.manuscript!!.title)
        assertTrue(api.lastBytes!!.all { it == 0.toByte() })
        assertEquals(1, api.capabilitiesReads); assertEquals(1, api.detailReads)
        assertFalse(store.read(mutation)); assertFalse(store.loadPage(0)); assertFalse(store.loadPage(100001))
    }

    @Test fun defaultOffOrOlderCapabilityDoesNotFetchMetadataOrProse() = runTest {
        val current = context(); val api = Fake().apply { enabled = false }
        val store = MemoryBookEditionShelfStore(repository(api, current = { current }), this) { current }
        store.loadPage(); runCurrent()
        assertEquals(MemoryBookEditionShelfStatus.UNAVAILABLE, store.state.value.status)
        assertTrue(api.pages.isEmpty()); assertFalse(store.read(edition))
        api.enabled = true; store.loadPage(); runCurrent()
        assertEquals(MemoryBookEditionShelfStatus.LIST, store.state.value.status)
        assertEquals(2, api.capabilitiesReads)
    }

    @Test fun eachFreshReadClearsOldProseBeforeAwaitAndChangedInvalidatedOrFailedReadCannotRestoreIt() = runTest {
        val current = context(); val api = Fake()
        val store = MemoryBookEditionShelfStore(repository(api, current = { current }), this) { current }
        store.loadPage(); runCurrent(); store.read(edition); runCurrent()
        assertNotNull(store.state.value.detail!!.manuscript)
        api.gate = CompletableDeferred()
        store.read(edition); assertNull(store.state.value.detail); runCurrent()
        api.detailState = "source_changed"; api.gate!!.complete(Unit); runCurrent()
        assertEquals(MemoryBookEditionShelfStatus.SOURCE_CHANGED, store.state.value.status)
        assertNull(store.state.value.detail!!.manuscript)
        api.gate = null; api.detailState = "source_invalidated"; store.read(edition); runCurrent()
        assertNull(store.state.value.detail!!.manuscript)
        api.detailState = "current"; store.read(edition); runCurrent()
        api.detailFailure = ApiFailure(FailureKind.OFFLINE)
        store.read(edition); assertNull(store.state.value.detail); runCurrent()
        assertEquals(MemoryBookEditionShelfStatus.FAILED, store.state.value.status)
        assertNull(store.state.value.detail)
    }

    @Test fun pagingAndPageFailureClearProseAndRefreshCapabilities() = runTest {
        val current = context(); val api = Fake()
        val store = MemoryBookEditionShelfStore(repository(api, current = { current }), this) { current }
        store.loadPage(); runCurrent(); store.read(edition); runCurrent()
        store.loadPage(2); assertNull(store.state.value.detail); assertNull(store.state.value.listing); runCurrent()
        assertEquals(listOf(1, 2), api.pages); assertEquals(2, api.capabilitiesReads)
        api.pageFailure = ApiFailure(FailureKind.OFFLINE); store.loadPage(2); runCurrent()
        assertEquals(MemoryBookEditionShelfStatus.FAILED, store.state.value.status)
        assertNull(store.state.value.listing); assertNull(store.state.value.detail)
    }

    @Test fun closeOrAccountChangeCancelsLateReadAndStaleDeniedResultCannotLockNewSession() = runTest {
        var current: MemoryBookNarrativeScope? = context(); val api = Fake(); var denied = 0
        val store = MemoryBookEditionShelfStore(repository(api, { current }) { denied++ }, this) { current }
        store.loadPage(); runCurrent(); api.gate = CompletableDeferred(); store.read(edition); runCurrent()
        store.closeReading(); api.gate!!.complete(Unit); runCurrent()
        assertNull(store.state.value.detail); assertNull(store.state.value.selectedId)
        api.gate = CompletableDeferred(); store.read(edition); runCurrent()
        current = current!!.copy(accountId = "another-reader", generation = 2)
        store.clear(); api.detailFailure = ApiFailure(FailureKind.HTTP, 403); api.gate!!.complete(Unit); runCurrent()
        assertEquals(0, denied); assertEquals(MemoryBookEditionShelfStatus.CLOSED, store.state.value.status)
        assertNull(store.state.value.detail)
    }

    @Test fun detailMustKeepTheImmutableIdentityListedByTheSelectedMetadataReceipt() = runTest {
        val current = context(); val api = Fake()
        val store = MemoryBookEditionShelfStore(repository(api, current = { current }), this) { current }
        store.loadPage(); runCurrent(); store.read(edition); runCurrent()
        assertNotNull(store.state.value.detail!!.manuscript)
        api.detailCreatedAt = 101
        store.read(edition); runCurrent()
        assertEquals(MemoryBookEditionShelfStatus.FAILED, store.state.value.status)
        assertNull(store.state.value.detail)
        api.detailState = "source_invalidated"; store.read(edition); runCurrent()
        assertEquals(MemoryBookEditionShelfStatus.FAILED, store.state.value.status)
        assertNull(store.state.value.detail)
    }

    @Test fun childRevisionChangeClearsCurrentPrivateReadingAndRejectsFurtherRequests() = runTest {
        var current = context(); val api = Fake()
        val store = MemoryBookEditionShelfStore(repository(api, current = { current }), this) { current }
        store.loadPage(); runCurrent(); store.read(edition); runCurrent()
        current = current.copy(children = listOf(EditorialChild(story, "3")))
        assertFalse(store.read(edition)); assertNull(store.state.value.detail)
        assertEquals(MemoryBookEditionShelfStatus.CLOSED, store.state.value.status)
        assertEquals(1, api.detailReads)
    }
}
