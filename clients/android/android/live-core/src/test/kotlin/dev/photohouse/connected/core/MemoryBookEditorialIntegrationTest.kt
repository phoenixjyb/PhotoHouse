package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class MemoryBookEditorialIntegrationTest {
    private val bookId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    private val child1 = "11111111-1111-4111-8111-111111111111"
    private val child2 = "22222222-2222-4222-8222-222222222222"
    private val source1 = "33333333-3333-4333-8333-333333333333"
    private val source2 = "44444444-4444-4444-8444-444444444444"

    private class Api(private val bookId: String, private val child1: String, private val child2: String,
                      private val source1: String, private val source2: String) : PhotoHouseApi, MemoryCommunityApi, MemoryBookEditorialApi {
        var bookRevision = 7L
        var editorialGets = 0
        var sourceGets = 0
        var editorialSaves = 0
        var saveFailure: ApiFailure? = null
        var sourceFailure: ApiFailure? = null
        var editorialReadFailure: ApiFailure? = null
        var sourceGate: CompletableDeferred<Unit>? = null
        val saveBodies = mutableListOf<String>()
        val children get() = listOf(EditorialChild(child1, "2"), EditorialChild(child2, "5"))
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("owner", "+8612345678", listOf(
            Membership("family", "approved", "owner", 1, null, 0, true), Membership("other", "approved", "owner", 1, null, 0, true)))
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail = error("unused")
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")
        override suspend fun capabilities(token: Bearer, library: String) =
            """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
        override suspend fun listBooks(token: Bearer, library: String, page: Int) = bookPage(library, page)
        override suspend fun getBook(token: Bearer, library: String, bookId: String) = bookJson().toByteArray()
        override suspend fun getBookEditorial(token: Bearer, library: String, bookId: String): ByteArray {
            editorialGets++; editorialReadFailure?.let { throw it }
            return editorialResponse(bookRevision).toByteArray()
        }
        override suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String): ByteArray {
            editorialSaves++; saveBodies += json
            saveFailure?.let { throw it }
            bookRevision++
            return editorialResponse(bookRevision).toByteArray()
        }
        override suspend fun getBookEditorialSourceReferences(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStoryContributionReferences {
            sourceGets++; sourceGate?.let { it.await(); sourceGate = null }; sourceFailure?.let { throw it }
            val count = if (storyId == child1) 1 else 2
            return SavedMemoryStoryContributionReferences(storyId, library, revision,
                (1..count).map { chapter -> SavedMemoryChapterContributionReferences("chapter-$chapter",
                    listOf(if (storyId == child1) source1 else source2)) })
        }
        private fun bookItem(revision: Long) = """{"version":1,"type":"memoir","id":"$bookId","revision":"$revision","can_edit":true,"title":"Family book","introduction":"","language":"en","stories":[{"id":"$child1","title":"Garden","revision":"2","item_count":1,"cover_asset_id":"1"},{"id":"$child2","title":"Walk","revision":"5","item_count":1,"cover_asset_id":"2"}]}"""
        private fun bookJson() = bookItem(bookRevision)
        private fun bookPage(library: String, page: Int) = """{"version":1,"library_id":"$library","page":$page,"page_size":8,"has_more":false,"can_create":false,"items":[${bookItem(bookRevision)}]}""".toByteArray()
        private fun editorialResponse(revision: Long) = """{"version":1,"id":"$bookId","revision":"$revision","children":[{"story_id":"$child1","revision":"2"},{"story_id":"$child2","revision":"5"}],"state":"current","introduction_source_refs":[],"transitions":[{"left_story_id":"$child1","right_story_id":"$child2","text":"","source_refs":[]}]}"""
    }

    private suspend fun TestScope.opened(api: Api): ConnectedStore {
        val store = ConnectedStore(api, backgroundScope, memoryCommunityApi = api, memoryCommunityEnabled = true)
        store.authenticate("+8612345678", "synthetic-password-only"); runCurrent()
        store.selectLibrary("family"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        return store
    }

    @Test fun explicitOwnerOpenLoadsMetadataOnlySourcesAndAckKeepsRevisionsCoherent() = runTest {
        val api = Api(bookId, child1, child2, source1, source2)
        val store = opened(api)
        assertEquals(0, api.sourceGets); assertEquals(0, api.editorialGets)
        store.openMemoryBookEditorial(); runCurrent()
        assertEquals(2, api.sourceGets)
        assertEquals(1, api.editorialGets)
        val intro = EditorialSourceIdentity(child2, "5", "chapter-2", source2)
        val transition = EditorialTransition(child1, child2, "We walked home together.", listOf(intro))
        store.editMemoryBookEditorial(listOf(intro), listOf(transition))
        store.saveMemoryBookEditorial(); runCurrent()
        assertEquals(1, api.editorialSaves)
        assertTrue(api.saveBodies.single().contains("We walked home together."))
        assertEquals(8L, store.state.value.memoryBooks?.selectedBook?.revision)
        assertEquals(8L, store.state.value.memoryBooks?.result?.items?.single()?.revision)
        store.closeMemoryBooks()
        assertEquals(MemoryBookEditorialStoreStatus.NO_CONTEXT, store.memoryBookEditorialState.value.status)
    }

    @Test fun acknowledgedEditorialSaveRetainsUnsentWholeMemoirInstructionsButInvalidatesPlan() = runTest {
        val api = Api(bookId, child1, child2, source1, source2)
        val store = opened(api)
        val instructions = "Keep the different family perspectives and ask about uncertain dates."
        assertTrue(store.updateMemoryBookNarrativeInstructions(instructions))
        assertTrue(store.chooseMemoryBookNarrativeForm(MemoryBookNarrativeForm.ESSAY))
        store.chooseMemoryBookNarrativeEditorialContext(true)
        assertTrue(store.memoryBookNarrativeState.value.editorialContext)
        store.openMemoryBookEditorial(); runCurrent()
        val reference = EditorialSourceIdentity(child1, "2", "chapter-1", source1)
        store.editMemoryBookEditorial(emptyList(), listOf(EditorialTransition(child1, child2, "The family remembers another walk.", listOf(reference))))
        store.saveMemoryBookEditorial(); runCurrent()
        assertEquals(8L, store.state.value.memoryBooks?.selectedBook?.revision)
        assertEquals(instructions, store.memoryBookNarrativeState.value.instructions)
        assertEquals(MemoryBookNarrativeForm.ESSAY, store.memoryBookNarrativeState.value.form)
        assertTrue(store.memoryBookNarrativeState.value.hasUnfinishedInput)
        assertFalse("a new book revision needs an explicit context check", store.memoryBookNarrativeState.value.editorialContext)
        assertNull(store.memoryBookNarrativeState.value.plan)
        assertNull(store.memoryBookNarrativeState.value.job)
        store.selectLibrary("other"); runCurrent()
        assertEquals("", store.memoryBookNarrativeState.value.instructions)
        assertEquals(MemoryBookNarrativeForm.EXISTING, store.memoryBookNarrativeState.value.form)
    }

    @Test fun sourceCatalogFailureStaysOptionalAndUncertainRetryReusesExactMutation() = runTest {
        val failedCatalogApi = Api(bookId, child1, child2, source1, source2).apply { sourceFailure = ApiFailure(FailureKind.HTTP, 503) }
        val unavailableStore = opened(failedCatalogApi)
        unavailableStore.openMemoryBookEditorial(); runCurrent()
        assertTrue(unavailableStore.memoryBookEditorialCatalogState.value.unavailable)
        assertEquals(0, failedCatalogApi.editorialGets)

        val api = Api(bookId, child1, child2, source1, source2).apply { saveFailure = ApiFailure(FailureKind.OFFLINE) }
        val store = opened(api)
        store.openMemoryBookEditorial(); runCurrent()
        val reference = EditorialSourceIdentity(child1, "2", "chapter-1", source1)
        store.editMemoryBookEditorial(listOf(reference), listOf(EditorialTransition(child1, child2, "A remembered walk", listOf(reference))))
        store.saveMemoryBookEditorial(); runCurrent()
        assertEquals(MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN, store.memoryBookEditorialState.value.status)
        val frozen = api.saveBodies.single()
        api.saveFailure = null
        store.retryMemoryBookEditorialSave(); runCurrent()
        assertEquals(listOf(frozen, frozen), api.saveBodies)
        assertEquals(8L, store.state.value.memoryBooks?.selectedBook?.revision)
    }

    @Test fun conflictRefreshRetainsDraftAgainstFreshBookRevision() = runTest {
        val api = Api(bookId, child1, child2, source1, source2)
        val store = opened(api)
        store.openMemoryBookEditorial(); runCurrent()
        val reference = EditorialSourceIdentity(child1, "2", "chapter-1", source1)
        val draft = listOf(EditorialTransition(child1, child2, "Keep this review", listOf(reference)))
        store.editMemoryBookEditorial(emptyList(), draft)
        api.bookRevision = 8
        // The next PUT is a compare-and-swap conflict; server shelf has advanced.
        api.saveFailure = ApiFailure(FailureKind.HTTP, 409)
        store.saveMemoryBookEditorial(); runCurrent()
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.memoryBookEditorialState.value.status)
        assertEquals("Keep this review", store.memoryBookEditorialState.value.draft?.transitions?.single()?.text)
        api.saveFailure = null
        api.editorialGets = 0
        store.refreshMemoryBookEditorialForReview(); runCurrent()
        assertEquals(8L, store.state.value.memoryBooks?.selectedBook?.revision)
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.memoryBookEditorialState.value.status)
        assertEquals("Keep this review", store.memoryBookEditorialState.value.draft?.transitions?.single()?.text)
    }

    @Test fun optionalEndpoint404AndLateCatalogAfterLibrarySwitchStayScoped() = runTest {
        val optionalApi = Api(bookId, child1, child2, source1, source2).apply { editorialReadFailure = ApiFailure(FailureKind.HTTP, 404) }
        val optionalStore = opened(optionalApi)
        optionalStore.openMemoryBookEditorial(); runCurrent()
        assertEquals(MemoryBookEditorialStoreStatus.UNAVAILABLE, optionalStore.memoryBookEditorialState.value.status)
        assertEquals(bookId, optionalStore.state.value.memoryBooks?.selectedBook?.id)

        val api = Api(bookId, child1, child2, source1, source2).apply { sourceGate = CompletableDeferred() }
        val store = opened(api)
        store.openMemoryBookEditorial(); runCurrent()
        store.selectLibrary("other"); runCurrent()
        api.sourceGate!!.complete(Unit); runCurrent()
        assertEquals(0, api.editorialGets)
        assertEquals(MemoryBookEditorialStoreStatus.NO_CONTEXT, store.memoryBookEditorialState.value.status)
        assertNull(store.state.value.memoryBooks)
    }
    @Test fun denialClearsReaderCatalogAndDraftAtEveryEditorialBoundary() = runTest {
        for (boundary in listOf("catalog", "read", "save")) {
            val api = Api(bookId, child1, child2, source1, source2)
            val store = opened(api)
            when (boundary) {
                "catalog" -> api.sourceFailure = ApiFailure(FailureKind.HTTP, 403)
                "read" -> api.editorialReadFailure = ApiFailure(FailureKind.HTTP, 403)
            }
            store.openMemoryBookEditorial(); runCurrent()
            if (boundary == "save") {
                val reference = EditorialSourceIdentity(child1, "2", "chapter-1", source1)
                store.editMemoryBookEditorial(listOf(reference), listOf(EditorialTransition(child1, child2, "Private synthetic draft", listOf(reference))))
                api.saveFailure = ApiFailure(FailureKind.HTTP, 403)
                store.saveMemoryBookEditorial(); runCurrent()
            }
            assertNull(boundary, store.state.value.memoryBooks)
            assertEquals(boundary, MemoryBookEditorialStoreStatus.NO_CONTEXT, store.memoryBookEditorialState.value.status)
            assertTrue(boundary, store.memoryBookEditorialCatalogState.value.sources.isEmpty())
            assertNull(boundary, store.memoryBookEditorialState.value.draft)
        }
    }

}
