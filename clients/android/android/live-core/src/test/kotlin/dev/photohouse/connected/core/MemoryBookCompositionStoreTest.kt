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
    private val three = "33333333-3333-4333-8333-333333333333"
    private val newBook = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    private val editBook = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
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
    private fun parentResponse(id: String, revision: Long, canEdit: Boolean, ids: List<String>, title: String, intro: String, language: String,
                               storyTitleOverride: String? = null) =
        """{"version":1,"type":"memoir","id":"$id","revision":"$revision","can_edit":$canEdit,"title":"$title","introduction":"$intro","language":"$language","stories":[${ids.map { storyId -> """{"id":"$storyId","title":"${storyTitleOverride ?: "Story ${storyId.take(1)}"}","revision":"1","item_count":1,"cover_asset_id":"1"}""" }.joinToString(",")}] }""".toByteArray()
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
        var bookCanEdit = true
        var bookRevision = 5L
        var bookStories = listOf(one, two)
        var bookTitle = "Existing memoir"
        var bookIntroduction = "Original introduction"
        var bookLanguage = "en"
        var responseStoryTitleOverride: String? = null
        var bookFailure: Exception? = null
        var bookDetailStarted: CompletableDeferred<Unit>? = null
        var bookDetailGate: CompletableDeferred<Unit>? = null
        val bookDetailCalls = mutableListOf<String>()
        val saveTargets = mutableListOf<String?>()
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
        override suspend fun getBook(token: Bearer, library: String, bookId: String): ByteArray {
            bookDetailCalls += bookId
            bookDetailStarted?.complete(Unit)
            bookDetailGate?.let { withContext(NonCancellable) { it.await() } }
            bookFailure?.let { throw it }
            return parentResponse(bookId, bookRevision, bookCanEdit, bookStories,
                bookTitle, bookIntroduction, bookLanguage)
        }
        override suspend fun saveBook(token: Bearer, library: String, bookId: String?, json: String): ByteArray {
            saved += json
            saveTargets += bookId
            saveGate?.await()
            saveFailure?.let { saveFailure = null; throw it }
            val request = kotlinx.serialization.json.Json.parseToJsonElement(json).jsonObject
            val ids = request.getValue("story_ids").jsonPrimitive.content.split(',')
            val revision = request.getValue("revision").jsonPrimitive.content.toLong()
            return parentResponse(bookId ?: newBook, revision + 1, true, ids,
                request.getValue("title").jsonPrimitive.content,
                request.getValue("introduction").jsonPrimitive.content,
                request.getValue("language").jsonPrimitive.content, responseStoryTitleOverride)
        }
    }

    private fun makeScope(token: Bearer = bearer(), id: String = "account-a", generation: Long = 1,
                          library: String = "family-a", shelf: Long = 7, ownerCanCreate: Boolean = true,
                          editableBookId: String? = null, editableBookRevision: Long? = null,
                          editableReaderScopeId: Long? = null) =
        MemoryBookCompositionScope(id, token, generation, library, shelf, ownerCanCreate,
            editableBookId, editableBookRevision, editableReaderScopeId)

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

    @Test fun editReordersAddsRemovesAndSavesToSameParentAtNextRevisionWithoutCreatePermission() = runTest {
        val api = FakeApi()
        api.bookStories = listOf(one, two)
        api.candidateSummaries = listOf(summary(one), summary(two), summary(three))
        var current = makeScope(ownerCanCreate = false, editableBookId = editBook,
            editableBookRevision = 5, editableReaderScopeId = 91)
        val store = setup(api, this, { current })
        assertTrue(store.openEdit(editBook, 5)); runCurrent()
        val opened = store.state.value
        assertEquals(MemoryBookCompositionStatus.READY, opened.status)
        assertFalse(opened.canCreate)
        assertTrue(opened.canEdit)
        assertEquals(editBook, opened.editingBookId)
        assertEquals(5L, opened.editingBookRevision)
        assertEquals(91L, opened.editingReaderScopeId)
        assertFalse(opened.hasChanges)
        assertEquals("Existing memoir", opened.title)
        assertEquals(listOf(one, two), opened.selectedStories.map { it.summary.id })
        assertEquals(listOf(editBook), api.bookDetailCalls)

        assertTrue(store.toggleStory(two, 1, 7, opened.actionEpoch))
        assertEquals(listOf(one), store.state.value.selectedStories.map { it.summary.id })
        assertTrue(store.toggleStory(three, 1, 7, opened.actionEpoch)); runCurrent()
        assertTrue(store.reorderStories(listOf(one, three), listOf(three, one), 7, opened.actionEpoch))
        assertTrue(store.updateTitle("Updated memoir", 7, opened.actionEpoch))
        assertTrue(store.updateIntroduction("Revised family notes", 7, opened.actionEpoch))
        assertTrue(store.updateLanguage("zh", 7, opened.actionEpoch))
        assertTrue(store.save(7, opened.actionEpoch, store.state.value.draftRevision)); runCurrent()

        assertEquals(listOf(editBook), api.saveTargets)
        assertEquals(5L, kotlinx.serialization.json.Json.parseToJsonElement(api.saved.single())
            .jsonObject.getValue("revision").jsonPrimitive.content.toLong())
        assertEquals(MemoryBookCompositionStatus.SAVED, store.state.value.status)
        assertEquals(editBook, store.state.value.createdBook?.id)
        assertEquals(6L, store.state.value.createdBook?.revision)
        assertEquals(listOf(three, one), store.state.value.createdBook?.stories?.map { it.id })
        assertFalse(store.updateTitle("After save", 7, opened.actionEpoch))
        assertFalse(store.save(7, opened.actionEpoch, store.state.value.draftRevision))
        assertEquals(1, api.saved.size)
    }

    @Test fun changedOrRevokedParentAndChangedChildPreserveTheReviewedDraft() = runTest {
        suspend fun opened(api: FakeApi, current: () -> MemoryBookCompositionScope?) =
            setup(api, this, current).also { assertTrue(it.openEdit(editBook, 5)); runCurrent() }

        run {
            val api = FakeApi(); var current = makeScope(ownerCanCreate = false,
                editableBookId = editBook, editableBookRevision = 5, editableReaderScopeId = 91)
            val store = opened(api) { current }
            api.bookRevision = 6
            assertTrue(store.updateTitle("Keep this draft", 7, store.state.value.actionEpoch))
            assertTrue(store.save(7, store.state.value.actionEpoch, store.state.value.draftRevision)); runCurrent()
            assertEquals(MemoryBookCompositionFailure.BOOK_CHANGED, store.state.value.failure)
            assertEquals("Keep this draft", store.state.value.title)
            assertEquals(MemoryBookCompositionStatus.READY, store.state.value.status)
            assertTrue(api.saved.isEmpty())
        }
        run {
            val api = FakeApi(); var current = makeScope(ownerCanCreate = false,
                editableBookId = editBook, editableBookRevision = 5, editableReaderScopeId = 91)
            val store = opened(api) { current }
            api.bookCanEdit = false
            assertTrue(store.updateTitle("Revised after permission change", 7, store.state.value.actionEpoch))
            assertTrue(store.save(7, store.state.value.actionEpoch, store.state.value.draftRevision)); runCurrent()
            assertEquals(MemoryBookCompositionFailure.BOOK_CHANGED, store.state.value.failure)
            assertEquals(MemoryBookCompositionStatus.READY, store.state.value.status)
            assertTrue(store.state.value.canEdit)
            assertTrue(api.saved.isEmpty())
        }
        run {
            val api = FakeApi(); var current = makeScope(ownerCanCreate = false,
                editableBookId = editBook, editableBookRevision = 5, editableReaderScopeId = 91)
            val store = opened(api) { current }
            api.currentSelectionRevision = "f".repeat(64)
            assertTrue(store.updateTitle("Revised after story change", 7, store.state.value.actionEpoch))
            assertTrue(store.save(7, store.state.value.actionEpoch, store.state.value.draftRevision)); runCurrent()
            assertEquals(MemoryBookCompositionFailure.STORY_CHANGED, store.state.value.failure)
            assertEquals(MemoryBookCompositionStatus.READY, store.state.value.status)
            assertEquals("Revised after story change", store.state.value.title)
            assertTrue(api.saved.isEmpty())
        }
    }

    @Test fun editRetryReusesTheSameTargetRevisionAndMutation() = runTest {
        val api = FakeApi(); var current = makeScope(ownerCanCreate = false,
            editableBookId = editBook, editableBookRevision = 5, editableReaderScopeId = 91)
        val store = setup(api, this, { current })
        assertTrue(store.openEdit(editBook, 5)); runCurrent()
        val epoch = store.state.value.actionEpoch
        assertTrue(store.updateTitle("Retry this memoir", 7, epoch))
        api.saveFailure = ApiFailure(FailureKind.OFFLINE)
        assertTrue(store.save(7, epoch, store.state.value.draftRevision)); runCurrent()
        assertEquals(MemoryBookCompositionStatus.RETRY_REQUIRED, store.state.value.status)
        val body = api.saved.single()
        assertEquals(editBook, api.saveTargets.single())
        assertTrue(store.retry(7, epoch)); runCurrent()
        assertEquals(listOf(editBook, editBook), api.saveTargets)
        assertEquals(listOf(body, body), api.saved)
        assertEquals(MemoryBookCompositionStatus.SAVED, store.state.value.status)
    }

    @Test fun revertedEditHasNoChangesAndCannotAdvanceParentRevision() = runTest {
        val api = FakeApi(); var current = makeScope(ownerCanCreate = false,
            editableBookId = editBook, editableBookRevision = 5, editableReaderScopeId = 91)
        val store = setup(api, this, { current })
        assertTrue(store.openEdit(editBook, 5)); runCurrent()
        val epoch = store.state.value.actionEpoch
        assertTrue(store.updateTitle("Temporary title", 7, epoch))
        assertTrue(store.state.value.hasChanges)
        assertTrue(store.updateTitle("Existing memoir", 7, epoch))
        assertFalse(store.state.value.hasChanges)
        assertFalse(store.save(7, epoch, store.state.value.draftRevision))
        assertTrue(api.saved.isEmpty())
        assertEquals(5L, api.bookRevision)
        assertEquals(MemoryBookCompositionStatus.READY, store.state.value.status)
    }

    @Test fun childAuthorizationRevocationUsesExistingDenialCleanup() = runTest {
        val api = FakeApi(); var current = makeScope(ownerCanCreate = false,
            editableBookId = editBook, editableBookRevision = 5, editableReaderScopeId = 91)
        var denied = 0
        val store = setup(api, this, { current }, onDenied = { denied++ })
        assertTrue(store.openEdit(editBook, 5)); runCurrent()
        val epoch = store.state.value.actionEpoch
        assertTrue(store.updateTitle("Private draft", 7, epoch))
        api.detailFailure = ApiFailure(FailureKind.HTTP, 403)
        assertTrue(store.save(7, epoch, store.state.value.draftRevision)); runCurrent()
        assertEquals(MemoryBookCompositionStatus.CLOSED, store.state.value.status)
        assertEquals(MemoryBookCompositionFailure.ACCESS_DENIED, store.state.value.failure)
        assertEquals("", store.state.value.title)
        assertEquals(1, denied)
        assertTrue(api.saved.isEmpty())
    }

    @Test fun saveResponseMustMatchReviewedChildTitlesAndItemCounts() = runTest {
        val api = FakeApi(); var current = makeScope(ownerCanCreate = false,
            editableBookId = editBook, editableBookRevision = 5, editableReaderScopeId = 91)
        val store = setup(api, this, { current })
        assertTrue(store.openEdit(editBook, 5)); runCurrent()
        val epoch = store.state.value.actionEpoch
        assertTrue(store.updateTitle("Reviewed update", 7, epoch))
        api.responseStoryTitleOverride = "Different story title"
        assertTrue(store.save(7, epoch, store.state.value.draftRevision)); runCurrent()
        assertEquals(MemoryBookCompositionStatus.RETRY_REQUIRED, store.state.value.status)
        assertEquals(MemoryBookCompositionFailure.INVALID_RESPONSE, store.state.value.failure)
        assertEquals(editBook, api.saveTargets.single())
        assertEquals("5", kotlinx.serialization.json.Json.parseToJsonElement(api.saved.single())
            .jsonObject.getValue("revision").jsonPrimitive.content)
        assertTrue(store.state.value.pendingRetry)
    }

    @Test fun replacedReaderScopeCannotAcceptAnOldParentRead() = runTest {
        val api = FakeApi(); var current = makeScope(ownerCanCreate = false,
            editableBookId = editBook, editableBookRevision = 5, editableReaderScopeId = 91)
        val started = CompletableDeferred<Unit>(); val gate = CompletableDeferred<Unit>()
        api.bookDetailStarted = started; api.bookDetailGate = gate
        val store = setup(api, this, { current })
        assertTrue(store.openEdit(editBook, 5)); runCurrent(); started.await()
        current = current.copy(editableReaderScopeId = 92)
        gate.complete(Unit); runCurrent()
        assertEquals(MemoryBookCompositionStatus.LOADING, store.state.value.status)
        assertTrue(store.state.value.selectedStories.isEmpty())
        assertEquals("", store.state.value.title)
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
