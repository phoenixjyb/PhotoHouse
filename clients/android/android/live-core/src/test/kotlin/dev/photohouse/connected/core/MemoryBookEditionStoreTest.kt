package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryBookEditionStoreTest {
    private val book = "11111111-1111-4111-8111-111111111111"
    private val story = "22222222-2222-4222-8222-222222222222"
    private val job = "33333333-3333-4333-8333-333333333333"
    private val edition = "44444444-4444-4444-8444-444444444444"
    private val mutation = "55555555-5555-4555-8555-555555555555"
    private val chapter = "$story-chapter-1"
    private fun context() = MemoryBookNarrativeScope("synthetic-owner",
        Bearer.from(SessionToken(86400, "a".repeat(43), "Bearer")), "family-a", 1, book, 7,
        listOf(EditorialChild(story, "2")), 10)
    private val manuscript get() = """{"version":1,"title":"原建议","chapters":[{"id":"$chapter","narration":"家人的讲述仍需核对。","source_ids":["caption-101"]}],"questions":["是哪一年？"],"needs_review":true}"""
    private fun receipt(state: String = "current") = """{"version":1,"id":"$edition","book_id":"$book","book_revision":"7","created_at":100,"state":"$state","mutation_id":"$mutation"}"""
    private inner class Fake : MemoryBookEditionApi {
        var calls = 0
        var enabled = true
        var saveFailure: ApiFailure? = null
        var receiptState = "current"
        var readState = "current"
        var readProse = true
        var saveGate: CompletableDeferred<Unit>? = null
        val bodies = mutableListOf<String>()
        override suspend fun editionCapabilities(token: Bearer, library: String, bookId: String): ByteArray {
            calls++; return """{"version":1,"enabled":$enabled,"can_save":$enabled}""".toByteArray()
        }
        override suspend fun editionProposal(token: Bearer, library: String, bookId: String, jobId: String): ByteArray {
            calls++; return """{"version":1,"book_id":"$book","revision":"7","job_id":"$job","job_result_sha256":"${"a".repeat(64)}","source_fingerprint":"${"b".repeat(64)}","context_profile":"stories","children":[{"id":"$story","revision":"2"}],"manuscript":$manuscript,"needs_review":true}""".toByteArray()
        }
        override suspend fun saveEdition(token: Bearer, library: String, bookId: String, json: String): ByteArray {
            calls++; bodies += json; saveGate?.await(); saveFailure?.let { throw it }
            return receipt(receiptState).toByteArray()
        }
        override suspend fun editionPage(token: Bearer, library: String, bookId: String, page: Int): ByteArray = error("not used")
        override suspend fun editionDetail(token: Bearer, library: String, bookId: String, editionId: String): ByteArray {
            calls++; return """${receipt(readState).dropLast(1)},"manuscript":${if (readProse) manuscript else "null"}}""".toByteArray()
        }
    }
    private fun repository(api: Fake, current: () -> MemoryBookNarrativeScope?) = MemoryBookEditionRepository(api, {
        current()?.let { MemoryCommunityBinding(it.credential, it.library, it.generation) }
    })

    @Test fun noAutomaticRequestsAndDefaultOffCannotExposeAnEditor() = runTest {
        val context = context(); val api = Fake().apply { enabled = false }
        val store = MemoryBookEditionStore(repository(api) { context }, this, { context }) { mutation }
        assertEquals(0, api.calls)
        assertFalse(store.save())
        assertTrue(store.open(job, listOf(chapter))); runCurrent()
        assertEquals(MemoryBookEditionStatus.UNAVAILABLE, store.state.value.status)
        assertNull(store.state.value.manuscript)
        assertEquals(1, api.calls)
        assertTrue(api.bodies.isEmpty())
    }

    @Test fun editsAndImeClearReviewAndOnlyExplicitSaveMakesOneContentFreeReceipt() = runTest {
        val context = context(); val api = Fake()
        val store = MemoryBookEditionStore(repository(api) { context }, this, { context }) { mutation }
        store.open(job, listOf(chapter)); runCurrent()
        assertFalse(store.save())
        assertTrue(store.editTitle("家人核对后的版本"))
        store.confirmReviewed(true)
        store.editChapter(0, "先保留不同说法，再问问家人。")
        assertFalse(store.state.value.reviewed)
        store.composition(true)
        assertFalse(store.confirmReviewed(true)); assertFalse(store.save())
        store.composition(false); store.confirmReviewed(true)
        assertTrue(store.save()); runCurrent()
        assertEquals(1, api.bodies.size)
        assertTrue(api.bodies.single().contains("家人核对后的版本"))
        assertTrue(api.bodies.single().contains("先保留不同说法"))
        assertEquals(MemoryBookEditionStatus.SAVED, store.state.value.status)
        assertNull(store.state.value.manuscript)
        assertNull(store.state.value.proposal)
        assertFalse(store.state.value.hasUnfinishedWork)
        assertFalse(store.save())
    }

    @Test fun uncertainSaveFreezesEditsAndRequiresAnIdenticalExplicitRetry() = runTest {
        val context = context(); val api = Fake()
        val store = MemoryBookEditionStore(repository(api) { context }, this, { context }) { mutation }
        store.open(job, listOf(chapter)); runCurrent()
        store.editTitle("冻结的稿件"); store.confirmReviewed(true)
        api.saveFailure = ApiFailure(FailureKind.OFFLINE)
        store.save(); runCurrent()
        assertEquals(MemoryBookEditionStatus.SAVE_UNCERTAIN, store.state.value.status)
        assertFalse(store.editTitle("不能替换")); assertFalse(store.close(true)); assertFalse(store.open(job, listOf(chapter)))
        assertEquals(1, api.bodies.size)
        api.saveFailure = null; api.receiptState = "source_invalidated"
        assertTrue(store.retrySave()); runCurrent()
        assertEquals(api.bodies[0], api.bodies[1])
        assertEquals(MemoryBookEditionState.SOURCE_INVALIDATED, store.state.value.receipt!!.state)
        assertNull(store.state.value.manuscript)
    }

    @Test fun everyReadClearsPreviousProseBeforeRequestAndChangedOrMalformedProseStaysHidden() = runTest {
        val context = context(); val api = Fake()
        val store = MemoryBookEditionStore(repository(api) { context }, this, { context }) { mutation }
        store.open(job, listOf(chapter)); runCurrent(); store.confirmReviewed(true); store.save(); runCurrent()
        store.readSaved(); runCurrent(); assertNotNull(store.state.value.manuscript)
        api.readState = "source_changed"
        assertTrue(store.readSaved()); assertNull(store.state.value.manuscript)
        runCurrent()
        assertEquals(MemoryBookEditionStatus.READ_UNAVAILABLE, store.state.value.status)
        assertNull(store.state.value.manuscript)
        api.readProse = false
        store.readSaved(); runCurrent()
        assertEquals(MemoryBookEditionStatus.SOURCE_CHANGED, store.state.value.status)
        assertNull(store.state.value.manuscript)
    }

    @Test fun lateSaveAndChangedBookCannotRepopulateClearedPrivateText() = runTest {
        var context: MemoryBookNarrativeScope? = context(); val api = Fake()
        val store = MemoryBookEditionStore(repository(api) { context }, this, { context }) { mutation }
        store.open(job, listOf(chapter)); runCurrent(); store.editTitle("私有草稿"); store.confirmReviewed(true)
        api.saveGate = CompletableDeferred()
        store.save(); runCurrent()
        context = context!!.copy(generation = 2)
        store.clear(); api.saveGate!!.complete(Unit); runCurrent()
        assertEquals(MemoryBookEditionStatus.IDLE, store.state.value.status)
        assertNull(store.state.value.receipt); assertNull(store.state.value.manuscript)
        api.saveGate = null
        store.open(job, listOf(chapter)); runCurrent()
        context = context!!.copy(bookRevision = 8)
        assertFalse(store.editTitle("旧版本不能编辑"))
        assertEquals(MemoryBookEditionStatus.IDLE, store.state.value.status)
        assertNull(store.state.value.manuscript)
    }

    @Test fun rejectedUiInputCannotSilentlySaveTheLastAcceptedTextOrLeaveWithoutDiscard() = runTest {
        val context = context(); val api = Fake()
        val store = MemoryBookEditionStore(repository(api) { context }, this, { context }) { mutation }
        store.open(job, listOf(chapter)); runCurrent(); store.confirmReviewed(true)
        assertFalse(store.editTitle("x".repeat(513)))
        store.invalidInput(true)
        assertTrue(store.state.value.dirty); assertFalse(store.state.value.reviewed)
        assertFalse(store.confirmReviewed(true)); assertFalse(store.save()); assertFalse(store.close(false))
        assertTrue(api.bodies.isEmpty())
        assertTrue(store.editTitle("修正后的版本")); store.invalidInput(false)
        assertTrue(store.confirmReviewed(true)); assertTrue(store.save()); runCurrent()
        assertTrue(api.bodies.single().contains("修正后的版本"))
    }

    @Test fun dirtyDraftNeedsDiscardAndKnownInputRejectionCanBeCorrectedWithoutRetryIdentity() = runTest {
        val context = context(); val api = Fake()
        val store = MemoryBookEditionStore(repository(api) { context }, this, { context }) { mutation }
        store.open(job, listOf(chapter)); runCurrent(); store.editTitle("保留的草稿")
        assertFalse(store.close(false)); assertFalse(store.open(job, listOf(chapter)))
        assertEquals("保留的草稿", store.state.value.manuscript!!.title)
        store.confirmReviewed(true); api.saveFailure = ApiFailure(FailureKind.HTTP, 400)
        store.save(); runCurrent()
        assertEquals(MemoryBookEditionStatus.INVALID, store.state.value.status)
        assertFalse(store.state.value.hasPendingSave)
        assertTrue(store.editTitle("修改后的草稿"))
        assertTrue(store.close(true)); assertNull(store.state.value.manuscript)
    }
}
