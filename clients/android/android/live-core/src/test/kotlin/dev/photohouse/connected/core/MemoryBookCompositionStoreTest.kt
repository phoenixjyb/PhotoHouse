package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryBookCompositionStoreTest {
    private val one = "11111111-1111-4111-8111-111111111111"
    private val two = "22222222-2222-4222-8222-222222222222"
    private val newBook = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    private fun bearer(seed: Char = 'a') = Bearer.from(SessionToken(86400, seed.toString().repeat(43), "Bearer"))
    private fun asset(id: String) = Asset(id, "image", 800, 600, null, "2024-05-01", "/assets/$id/thumbnail?library=family-a")
    private fun story(id: String, revision: Long = 1, selectionRevision: String = id.take(1).repeat(64)) = SavedMemoryStory(
        id, "family-a", revision, 1710000000, 1720000000, true, selectionRevision, "Story ${id.take(1)}",
        "everyday", "zh", listOf(MemoryStoryAsset(asset("1"), emptyList())),
        listOf(SavedMemoryStoryChapter("chapter-1", "A moment", "First hand memory.", listOf("1"), emptyList())), emptyList())
    private fun summary(id: String, revision: Long = 1) = SavedMemoryStorySummary(
        id, "Story ${id.take(1)}", "everyday", "zh", revision, "1", 1, 1, 1720000000, true)
    private fun listPage(page: Int = 1) = SavedMemoryStoryPage("family-a", page, 8, false, false,
        if (page == 1) listOf(summary(one), summary(two)) else emptyList())
    private fun bookPage(canCreate: Boolean = true) = """{"version":1,"library_id":"family-a","page":1,"page_size":8,"has_more":false,"can_create":$canCreate,"items":[]}""".toByteArray()
    private fun bookResponse(ids: List<String>, title: String, intro: String, language: String) =
        """{"version":1,"type":"memoir","id":"$newBook","revision":"1","can_edit":true,"title":"$title","introduction":"$intro","language":"$language","stories":[${ids.mapIndexed { index, id -> """{"id":"$id","title":"Story ${id.take(1)}","revision":"1","item_count":1,"cover_asset_id":"1"}""" }.joinToString(",")}] }""".toByteArray()
    private fun capabilities() = """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()

    private inner class FakeApi : PhotoHouseApi, MemoryCommunityApi {
        var currentStoryRevision = 1L
        var currentSelectionRevision = one.take(1).repeat(64)
        val saved = mutableListOf<String>()
        var saveFailure: Exception? = null
        var saveGate: CompletableDeferred<Unit>? = null
        var detailGate: CompletableDeferred<Unit>? = null
        var detailFailure: Exception? = null
        var listFailure: Exception? = null
        var candidateSummaries: List<SavedMemoryStorySummary> = listOf(summary(one), summary(two))
        var bookCanCreate = true
        var detailStarted: CompletableDeferred<Unit>? = null
        var listCalls = mutableListOf<Int>()
        var detailCalls = mutableListOf<Pair<String, Long>>()
        var capabilityCalls = 0
        var capabilityStarted: MutableMap<Int, CompletableDeferred<Unit>> = mutableMapOf()
        var capabilityGates: MutableMap<Int, CompletableDeferred<Unit>> = mutableMapOf()
        var capabilityFailures: MutableMap<Int, Exception> = mutableMapOf()
        var bookPageCalls = 0
        var bookPageStarted: CompletableDeferred<Unit>? = null
        var bookPageGate: CompletableDeferred<Unit>? = null
        var bookPageFailure: Exception? = null

        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("account-a", "+86123456789", emptyList())
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 1, false, listOf(asset("1")))
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, asset(assetId))
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset) = byteArrayOf(1)
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 1, byteArrayOf(0))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf(1)

        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int): SavedMemoryStoryPage {
            listCalls += page
            listFailure?.let { throw it }
            return SavedMemoryStoryPage(library, page, 8, false, false,
                if (page == 1) candidateSummaries else emptyList())
        }
        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            detailCalls += storyId to revision
            detailStarted?.complete(Unit)
            detailGate?.await()
            detailFailure?.let { throw it }
            val value = if (storyId == one) story(storyId, currentStoryRevision, currentSelectionRevision) else story(storyId)
            return value
        }
        override suspend fun capabilities(token: Bearer, library: String): ByteArray {
            val call = ++capabilityCalls
            capabilityStarted[call]?.complete(Unit)
            capabilityGates[call]?.let { gate -> withContext(NonCancellable) { gate.await() } }
            capabilityFailures[call]?.let { throw it }
            return capabilities()
        }
        override suspend fun listBooks(token: Bearer, library: String, page: Int): ByteArray {
            bookPageCalls++
            bookPageStarted?.complete(Unit)
            bookPageGate?.let { withContext(NonCancellable) { it.await() } }
            bookPageFailure?.let { throw it }
            return bookPage(bookCanCreate)
        }
        override suspend fun saveBook(token: Bearer, library: String, bookId: String?, json: String): ByteArray {
            saved += json
            saveGate?.await()
            saveFailure?.let { saveFailure = null; throw it }
            val request = kotlinx.serialization.json.Json.parseToJsonElement(json).jsonObject
            val ids = request.getValue("story_ids").jsonPrimitive.content.split(',')
            return bookResponse(ids, request.getValue("title").jsonPrimitive.content,
                request.getValue("introduction").jsonPrimitive.content, request.getValue("language").jsonPrimitive.content)
        }
    }

    private fun makeScope(token: Bearer = bearer(), id: String = "account-a", generation: Long = 1,
                          library: String = "family-a", shelf: Long = 7, ownerCanCreate: Boolean = true) =
        MemoryBookCompositionScope(id, token, generation, library, shelf, ownerCanCreate)

    private suspend fun setup(api: FakeApi, scope: kotlinx.coroutines.CoroutineScope,
                              current: () -> MemoryBookCompositionScope?,
                              onDenied: () -> Unit = {},
                              repositoryDenied: () -> Unit = {},
                              hasUnfinishedInput: () -> Boolean = { false }): MemoryBookCompositionStore {
        val repository = MemoryCommunityRepository(api, {
            current()?.let { MemoryCommunityBinding(it.credential, it.library, it.generation) }
        }, repositoryDenied)
        return MemoryBookCompositionStore(api, repository, scope, current, onDenied, hasUnfinishedInput)
    }

    @Test fun staleCapabilityDenialAfterCloseAndReplacementCannotInvalidateCurrentComposer() = runTest {
        val api = FakeApi(); var current = makeScope(); var ownerDenied = 0; var repositoryDenied = 0
        val firstStarted = CompletableDeferred<Unit>()
        val firstGate = CompletableDeferred<Unit>()
        api.capabilityStarted[1] = firstStarted
        api.capabilityGates[1] = firstGate
        api.capabilityFailures[1] = ApiFailure(FailureKind.HTTP, 403)
        val store = setup(api, this, { current }, { ownerDenied++ }, { repositoryDenied++ })
        assertTrue(store.open("Old")); runCurrent(); firstStarted.await()
        val oldEpoch = store.state.value.actionEpoch
        store.close(7, oldEpoch)
        assertTrue(store.open("Replacement")); runCurrent()
        assertEquals(MemoryBookCompositionStatus.READY, store.state.value.status)
        firstGate.complete(Unit); runCurrent()
        assertEquals("Replacement", store.state.value.title)
        assertEquals(MemoryBookCompositionStatus.READY, store.state.value.status)
        assertEquals(0, ownerDenied)
        assertEquals(0, repositoryDenied)
        assertEquals(2, api.capabilityCalls)
    }

    @Test fun closingWhileCapabilitiesArePendingPreventsBooksRequest() = runTest {
        val api = FakeApi(); var current = makeScope()
        val started = CompletableDeferred<Unit>(); val gate = CompletableDeferred<Unit>()
        api.capabilityStarted[1] = started; api.capabilityGates[1] = gate
        val store = setup(api, this, { current })
        assertTrue(store.open()); runCurrent(); started.await()
        store.close(7, store.state.value.actionEpoch)
        gate.complete(Unit); runCurrent()
        assertEquals(0, api.bookPageCalls)
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.state.value.status)
    }

    @Test fun currentCapabilityAndBookPageDenialsWipeComposerAndNotifyOwner() = runTest {
        suspend fun verify(capabilityDenied: Boolean) {
            val api = FakeApi(); var current = makeScope(); var ownerDenied = 0; var repositoryDenied = 0
            if (capabilityDenied) api.capabilityFailures[1] = ApiFailure(FailureKind.HTTP, 403)
            else api.bookPageFailure = ApiFailure(FailureKind.HTTP, 403)
            val store = setup(api, this, { current }, { ownerDenied++ }, { repositoryDenied++ })
            assertTrue(store.open("Private title")); runCurrent()
            assertEquals(MemoryBookCompositionStatus.CLOSED, store.state.value.status)
            assertEquals(MemoryBookCompositionFailure.ACCESS_DENIED, store.state.value.failure)
            assertEquals("", store.state.value.title)
            assertEquals(1, ownerDenied)
            assertEquals(0, repositoryDenied)
            assertEquals(if (capabilityDenied) 0 else 1, api.bookPageCalls)
        }
        verify(capabilityDenied = true)
        verify(capabilityDenied = false)
    }

    @Test fun orderedSelectionAndValidatedCreate() = runTest {
        val api = FakeApi(); var current = makeScope()
        val store = setup(api, this, current = { current })
        assertTrue(store.open()); runCurrent()
        val opened = store.state.value
        assertTrue(opened.canCreate)
        assertTrue(store.toggleStory(one, 1, 7, opened.actionEpoch)); runCurrent()
        assertTrue(store.toggleStory(two, 1, 7, opened.actionEpoch)); runCurrent()
        val selected = store.state.value.selectedStories.map { it.summary.id }
        assertTrue(store.reorderStories(selected, listOf(two, one), 7, opened.actionEpoch))
        assertTrue(store.updateTitle("Family summer", 7, opened.actionEpoch))
        assertTrue(store.updateIntroduction("A few remembered moments.", 7, opened.actionEpoch))
        val revision = store.state.value.draftRevision
        assertTrue(store.save(7, opened.actionEpoch, revision)); runCurrent()
        assertEquals(MemoryBookCompositionStatus.CREATED, store.state.value.status)
        assertEquals(listOf(two, one), store.state.value.createdBook?.stories?.map { it.id })
        assertEquals(1, api.saved.size)
        val created = store.state.value.createdBook
        val ids = store.state.value.selectedStories.map { it.summary.id }
        assertFalse(store.updateTitle("Changed after create", 7, opened.actionEpoch))
        assertFalse(store.updateIntroduction("Changed after create", 7, opened.actionEpoch))
        assertFalse(store.updateLanguage("zh", 7, opened.actionEpoch))
        assertFalse(store.toggleStory(two, 1, 7, opened.actionEpoch))
        assertFalse(store.reorderStories(ids, ids.reversed(), 7, opened.actionEpoch))
        assertFalse(store.loadPage(2, 7, opened.actionEpoch))
        assertFalse(store.retryOpen(7, opened.actionEpoch))
        assertFalse(store.save(7, opened.actionEpoch, store.state.value.draftRevision))
        assertSame(created, store.state.value.createdBook)
        assertEquals(1, api.saved.size)
    }

    @Test fun emptySelectionAndChangedFreshSourceDoNotPost() = runTest {
        val api = FakeApi(); var current = makeScope()
        val store = setup(api, this, current = { current })
        assertTrue(store.open()); runCurrent(); val epoch = store.state.value.actionEpoch
        assertTrue(store.updateTitle("Family summer", 7, epoch))
        assertFalse(store.save(7, epoch, store.state.value.draftRevision)); runCurrent()
        assertTrue(api.saved.isEmpty())
        assertTrue(store.toggleStory(one, 1, 7, epoch)); runCurrent()
        assertFalse("a stale deselection callback cannot remove a different revision", store.toggleStory(one, 2, 7, epoch))
        assertEquals(1, store.state.value.selectedStories.size)
        api.currentSelectionRevision = "f".repeat(64)
        assertTrue(store.save(7, epoch, store.state.value.draftRevision)); runCurrent()
        assertEquals(MemoryBookCompositionFailure.STORY_CHANGED, store.state.value.failure)
        assertTrue(api.saved.isEmpty())
        assertFalse(store.state.value.pendingRetry)
    }

    @Test fun twentyFourStoryLimitAndReorderSnapshotAreEnforced() = runTest {
        val api = FakeApi()
        fun id(index: Int) = "00000000-0000-4000-8000-%012d".format(index)
        api.candidateSummaries = (1..25).map { summary(id(it)) }
        var current = makeScope()
        val store = setup(api, this, current = { current })
        assertTrue(store.open()); runCurrent(); val epoch = store.state.value.actionEpoch
        for (index in 1..24) {
            assertTrue(store.toggleStory(id(index), 1, 7, epoch))
            runCurrent()
        }
        assertEquals(24, store.state.value.selectedStories.size)
        assertFalse(store.toggleStory(id(25), 1, 7, epoch))
        val selected = store.state.value.selectedStories.map { it.summary.id }
        assertFalse(store.reorderStories(selected.drop(1), selected.reversed(), 7, epoch))
        assertEquals(selected, store.state.value.selectedStories.map { it.summary.id })
    }

    @Test fun immutableExplicitRetryReusesSameMutation() = runTest {
        val api = FakeApi(); var current = makeScope()
        val store = setup(api, this, current = { current })
        assertTrue(store.open()); runCurrent(); val epoch = store.state.value.actionEpoch
        store.toggleStory(one, 1, 7, epoch); runCurrent()
        store.updateTitle("Family summer", 7, epoch)
        api.saveFailure = ApiFailure(FailureKind.OFFLINE)
        store.save(7, epoch, store.state.value.draftRevision); runCurrent()
        assertEquals(MemoryBookCompositionStatus.RETRY_REQUIRED, store.state.value.status)
        val frozenBody = api.saved.single()
        assertFalse(store.updateTitle("Changed after timeout", 7, epoch))
        assertTrue(store.retry(7, epoch)); runCurrent()
        assertEquals(2, api.saved.size)
        assertEquals(frozenBody, api.saved.last())
        assertEquals(MemoryBookCompositionStatus.CREATED, store.state.value.status)
    }

    @Test fun scopeChangeBeforePostAndLateResponseAreInert() = runTest {
        val api = FakeApi(); var current: MemoryBookCompositionScope? = makeScope()
        val store = setup(api, this, current = { current })
        assertTrue(store.open()); runCurrent(); val epoch = store.state.value.actionEpoch
        store.toggleStory(one, 1, 7, epoch); runCurrent()
        api.currentStoryRevision = 2
        store.save(7, epoch, store.state.value.draftRevision); runCurrent()
        assertTrue(api.saved.isEmpty())
        api.currentStoryRevision = 1
        store.toggleStory(one, 1, 7, epoch); runCurrent()
        store.toggleStory(two, 1, 7, epoch); runCurrent()
        store.updateTitle("Family", 7, epoch)
        api.saveGate = CompletableDeferred()
        store.save(7, epoch, store.state.value.draftRevision); runCurrent()
        assertEquals(1, api.saved.size)
        current = makeScope(id = "account-b", shelf = 8)
        api.saveGate?.complete(Unit); runCurrent()
        assertEquals(MemoryBookCompositionStatus.SAVING, store.state.value.status)
        assertNull(store.state.value.createdBook)
    }

    @Test fun scopeChangeDuringFreshValidationPreventsPostAndReopeningWipesDraft() = runTest {
        val api = FakeApi(); var current: MemoryBookCompositionScope? = makeScope()
        val store = setup(api, this, current = { current })
        assertTrue(store.open()); runCurrent(); val epoch = store.state.value.actionEpoch
        assertTrue(store.toggleStory(one, 1, 7, epoch)); runCurrent()
        store.updateTitle("Private draft", 7, epoch)
        api.detailStarted = CompletableDeferred(); api.detailGate = CompletableDeferred()
        assertTrue(store.save(7, epoch, store.state.value.draftRevision)); runCurrent()
        api.detailStarted?.await()
        current = null
        assertFalse("opening with no current scope clears and refuses", store.open())
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.state.value.status)
        assertEquals("", store.state.value.title)
        assertTrue(store.state.value.selectedStories.isEmpty())
        api.detailGate?.complete(Unit); runCurrent()
        assertTrue(api.saved.isEmpty())
    }

    @Test fun openingWithNewNullOrDeniedBindingCancelsAndWipesOldSession() = runTest {
        val api = FakeApi(); var current: MemoryBookCompositionScope? = makeScope()
        val store = setup(api, this, current = { current })
        assertTrue(store.open("Old private title")); runCurrent()
        val oldEpoch = store.state.value.actionEpoch
        assertTrue(store.updateTitle("Old private title", 7, oldEpoch))
        current = null
        assertFalse(store.open())
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.state.value.status)
        assertEquals("", store.state.value.title)
        assertTrue(store.state.value.selectedStories.isEmpty())

        current = makeScope(shelf = 8)
        assertTrue(store.open("New private title")); runCurrent()
        val newEpoch = store.state.value.actionEpoch
        store.updateIntroduction("Draft for the new shelf", 8, newEpoch)
        current = makeScope(shelf = 8, ownerCanCreate = false)
        assertFalse(store.open())
        assertEquals(MemoryBookCompositionFailure.NOT_ALLOWED, store.state.value.failure)
        assertEquals("", store.state.value.title)
        assertEquals("", store.state.value.introduction)
    }

    @Test fun loadFailureKeepsDraftAndDenialClearsIt() = runTest {
        val api = FakeApi(); var current: MemoryBookCompositionScope? = makeScope()
        val store = setup(api, this, current = { current })
        assertTrue(store.open()); runCurrent(); val epoch = store.state.value.actionEpoch
        store.toggleStory(one, 1, 7, epoch); runCurrent()
        store.updateTitle("Keep this draft", 7, epoch)
        api.listFailure = ApiFailure(FailureKind.OFFLINE)
        assertTrue(store.loadPage(2, 7, epoch)); runCurrent()
        assertEquals("Keep this draft", store.state.value.title)
        assertEquals(1, store.state.value.selectedStories.size)
        api.detailFailure = ApiFailure(FailureKind.HTTP, 403)
        assertTrue(store.toggleStory(two, 1, 7, epoch)); runCurrent()
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.state.value.status)
        assertEquals(MemoryBookCompositionFailure.ACCESS_DENIED, store.state.value.failure)
        assertEquals("", store.state.value.title)
        assertTrue(store.state.value.selectedStories.isEmpty())
    }

    @Test fun retryInitialReadsRechecksCreateGateAndKeepsDraft() = runTest {
        val api = FakeApi(); var current = makeScope()
        val store = setup(api, this, current = { current })
        api.listFailure = ApiFailure(FailureKind.OFFLINE)
        assertTrue(store.open("Family memories")); runCurrent()
        val epoch = store.state.value.actionEpoch
        assertEquals("Family memories", store.state.value.title)
        assertEquals(MemoryBookCompositionFailure.NETWORK, store.state.value.failure)
        assertTrue(store.updateIntroduction("A private introduction", 7, epoch))
        api.listFailure = null
        api.bookCanCreate = false
        assertTrue(store.retryOpen(7, epoch)); runCurrent()
        assertEquals(MemoryBookCompositionFailure.NOT_ALLOWED, store.state.value.failure)
        assertEquals("A private introduction", store.state.value.introduction)
        assertFalse(store.state.value.canCreate)
        api.bookCanCreate = true
        assertTrue(store.retryOpen(7, epoch)); runCurrent()
        assertEquals(MemoryBookCompositionStatus.READY, store.state.value.status)
        assertEquals("Family memories", store.state.value.title)
        assertEquals("A private introduction", store.state.value.introduction)
    }

    @Test fun staleCloseFromOldEpochCannotCloseSameShelfReplacement() = runTest {
        val api = FakeApi(); var current = makeScope()
        val store = setup(api, this, current = { current })
        assertTrue(store.open("First")); runCurrent()
        val oldEpoch = store.state.value.actionEpoch
        store.close(7, oldEpoch)
        assertTrue(store.open("Second")); runCurrent()
        val newEpoch = store.state.value.actionEpoch
        assertNotEquals(oldEpoch, newEpoch)
        store.close(7, oldEpoch)
        assertEquals(MemoryBookCompositionStatus.READY, store.state.value.status)
        assertEquals("Second", store.state.value.title)
    }

    @Test fun unfinishedIntroductionVoiceBlocksCreateAndFrozenRetry() = runTest {
        val api = FakeApi().apply { saveFailure = ApiFailure(FailureKind.OFFLINE) }
        var current = makeScope()
        var voiceUnfinished = true
        val store = setup(api, this, { current }, hasUnfinishedInput = { voiceUnfinished })
        assertTrue(store.open()); runCurrent()
        val epoch = store.state.value.actionEpoch
        assertTrue(store.updateTitle("Family memoir", 7, epoch))
        assertTrue(store.toggleStory(one, 1, 7, epoch)); runCurrent()

        assertFalse(store.save(7, epoch, store.state.value.draftRevision))
        runCurrent()
        assertTrue("unfinished transcript must prevent any POST", api.saved.isEmpty())

        voiceUnfinished = false
        assertTrue(store.save(7, epoch, store.state.value.draftRevision)); runCurrent()
        assertEquals(MemoryBookCompositionStatus.RETRY_REQUIRED, store.state.value.status)
        assertEquals(1, api.saved.size)

        voiceUnfinished = true
        assertFalse("an unresolved voice review blocks uncertain retry", store.retry(7, epoch))
        runCurrent()
        assertEquals(1, api.saved.size)
        assertEquals(MemoryBookCompositionStatus.RETRY_REQUIRED, store.state.value.status)
    }
}
