package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

@OptIn(ExperimentalCoroutinesApi::class)
class StoryFirstGuideStoreTest {
    private val mutation = UUID.fromString("55555555-5555-4555-8555-555555555555")
    private fun binding(library: String = "family-a", generation: Long = 1) = MemoryCommunityBinding(
        Bearer.from(SessionToken(86400, "a".repeat(43), "Bearer")), library, generation)

    private class Api : PhotoHouseApi, StoryWorkspaceApi {
        override val assistantEnabled = true
        override val protectedNativeV2Enabled = true
        var previewGate: CompletableDeferred<Unit>? = null
        var previewRequests = 0
        var previewFailure: ApiFailure? = null
        var saveFailure: ApiFailure? = ApiFailure(FailureKind.OFFLINE)
        var saveResponse: ByteArray? = null
        val saveBodies = mutableListOf<String>()

        private fun preview() = """
            {"version":1,"library_id":"family-a","selection_revision":"${"a".repeat(64)}",
            "state":"draft","saved":false,"title":"Draft title","theme":"everyday","language":"zh",
            "generator":"evidence_outline","needs_review":true,
            "items":[{"id":"1","kind":"image","width":800,"height":600,"duration_sec":null,
            "taken_at":null,"thumbnail_url":"/assets/1/thumbnail?library=family-a","date_hint":null,"evidence":[]}],
            "chapters":[{"id":"chapter-1","title":"Chapter 1","narration":"Scaffold narration",
            "asset_ids":["1"],"evidence_ids":[]}],"questions":[]}
        """.trimIndent().toByteArray()

        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("member", "+12025550123", emptyList())
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 0, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail = error("unused")
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")
        override suspend fun assistantCapabilities(token: Bearer, library: String) = AssistantCapabilities(true, true, true, false, 5)
        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String) =
            AssistantTranscript("ASR words", "en", AssistantRequestReceipt(requestId, "enabled", "succeeded"))

        override suspend fun storyPreview(token: Bearer, library: String, json: String): ByteArray {
            previewRequests++
            previewGate?.await()
            previewFailure?.let { throw it }
            return preview()
        }
        override suspend fun storyTitleCapabilities(token: Bearer, library: String) =
            """{"version":1,"enabled":false,"max_suggestions":3,"needs_review":true}""".toByteArray()
        override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray {
            saveBodies += json
            saveFailure?.let { throw it }
            return saveResponse ?: throw ApiFailure(FailureKind.OFFLINE)
        }
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String, sourceReview: Boolean) =
            createGroupedStory(token, library, json)
    }

    private fun draft(api: Api, current: () -> MemoryCommunityBinding?, scope: kotlinx.coroutines.CoroutineScope): StoryWorkspaceStore {
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, current), scope, current,
            dictationApi = api, currentAccount = { "member" }, uuidSupplier = { mutation })
        assertTrue(store.startGuide())
        assertEquals(StoryGuideStep.FRAMES, store.state.value.guideStep)
        assertTrue(store.selectAsset("1"))
        assertTrue(store.continueGuide())
        return store
    }

    @Test fun guideRequiresOwnWordsAndReviewBeforeExplicitSave() = runTest {
        var current = binding()
        val api = Api()
        val store = draft(api, { current }, this)
        runCurrent()
        assertEquals(StoryGuideStep.WORDS, store.state.value.guideStep)
        assertEquals("", store.state.value.editableChapters.single().narration)
        assertEquals(0, api.saveBodies.size)
        assertFalse(store.confirmReviewed(true))
        assertFalse(store.save())
        assertFalse(store.continueGuide())

        assertTrue(store.editTitle("A remembered day"))
        assertFalse(store.continueGuide())
        assertTrue(store.editChapterNarration(0, "We picked flowers together."))
        assertTrue(store.continueGuide())
        assertEquals(StoryGuideStep.REVIEW, store.state.value.guideStep)
        assertFalse(store.state.value.reviewed)
        assertEquals(0, api.saveBodies.size)
        assertTrue(store.confirmReviewed(true))
        assertTrue(store.save())
        runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        assertEquals(StoryGuideStep.REVIEW, store.state.value.guideStep)
        assertEquals(1, api.saveBodies.size)
    }

    @Test fun backAndContinueReuseTheSameDraftAndPreserveWords() = runTest {
        var current = binding()
        val api = Api()
        val store = draft(api, { current }, this)
        runCurrent()
        val originalDraft = store.state.value.draft
        assertEquals(1, api.previewRequests)
        assertTrue(store.editTitle("Garden day"))
        assertTrue(store.editChapterNarration(0, "Grandma showed us the flowers."))
        assertTrue(store.continueGuide())
        assertTrue(store.backGuide())
        assertEquals(StoryGuideStep.WORDS, store.state.value.guideStep)
        assertTrue(store.backGuide())
        assertEquals(StoryWorkspaceStoreStatus.SELECTION, store.state.value.status)
        assertEquals(StoryGuideStep.FRAMES, store.state.value.guideStep)
        assertEquals(listOf("1"), store.state.value.selectedAssetIds)
        assertEquals("Grandma showed us the flowers.", store.state.value.editableChapters.single().narration)

        assertTrue(store.continueGuide())
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
        assertEquals(StoryGuideStep.WORDS, store.state.value.guideStep)
        assertSame(originalDraft, store.state.value.draft)
        assertEquals("Grandma showed us the flowers.", store.state.value.editableChapters.single().narration)
        assertEquals(1, api.previewRequests)
    }

    @Test fun changeMomentsRequiresEligibleExplicitDraftDiscardAndKeepsSelectionOptions() = runTest {
        var current = binding()
        val api = Api()
        val store = draft(api, { current }, this)
        runCurrent()
        assertTrue(store.editTitle("Garden day"))
        assertTrue(store.editChapterNarration(0, "Grandma showed us the flowers."))
        assertFalse(store.discardGuideDraft())
        assertTrue(store.continueGuide())
        assertFalse(store.discardGuideDraft())
        assertTrue(store.backGuide())
        assertTrue(store.backGuide())
        assertEquals(StoryGuideStep.FRAMES, store.state.value.guideStep)
        assertEquals(listOf("1"), store.state.value.selectedAssetIds)
        assertEquals("Garden day", store.state.value.title)
        assertEquals("Grandma showed us the flowers.", store.state.value.editableChapters.single().narration)

        assertTrue("the explicit change-moments action discards only the draft", store.discardGuideDraft())
        assertEquals(StoryWorkspaceStoreStatus.SELECTION, store.state.value.status)
        assertEquals(StoryGuideStep.FRAMES, store.state.value.guideStep)
        assertEquals(listOf("1"), store.state.value.selectedAssetIds)
        assertEquals("everyday", store.state.value.theme)
        assertEquals("zh", store.state.value.language)
        assertNull(store.state.value.draft)
        assertTrue(store.state.value.editableChapters.isEmpty())
        assertEquals("", store.state.value.title)
        assertEquals(1, api.previewRequests)

        assertTrue(store.continueGuide())
        runCurrent()
        assertEquals(2, api.previewRequests)
        assertEquals(StoryGuideStep.WORDS, store.state.value.guideStep)
        assertEquals("", store.state.value.editableChapters.single().narration)
    }

    @Test fun composingAndUnfinishedDictationFenceGuideNavigationAndSave() = runTest {
        var current = binding()
        val api = Api()
        val store = draft(api, { current }, this)
        runCurrent()
        store.composition(true)
        assertFalse(store.continueGuide())
        assertFalse(store.backGuide())
        store.composition(false)

        assertTrue(store.openChapterDictation(0))
        runCurrent()
        val dictation = store.chapterDictation.value!!
        assertEquals(5, dictation.beginRecording())
        assertFalse(store.continueGuide())
        assertFalse(store.backGuide())
        assertFalse(store.save())
        store.closeChapterDictation()
        assertFalse(store.hasUnfinishedChapterDictation)
    }

    @Test fun stalePreviewAfterLibraryChangeClearsGuideAndDraft() = runTest {
        var current = binding()
        val gate = CompletableDeferred<Unit>()
        val api = Api().apply { previewGate = gate }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, currentBinding = { current }), this, { current },
            dictationApi = api, currentAccount = { "member" })
        assertTrue(store.startGuide())
        assertTrue(store.selectAsset("1"))
        assertTrue(store.continueGuide())
        runCurrent()
        assertEquals(1, api.previewRequests)
        current = binding(library = "family-b", generation = 2)
        gate.complete(Unit)
        runCurrent()
        assertNull(store.state.value.guideStep)
        assertNull(store.state.value.draft)
        assertTrue(store.state.value.selectedAssetIds.isEmpty())
    }

    @Test fun sourceReloadKeepsWordsAndReturnsGuideToWordsForReview() = runTest {
        var current = binding()
        val api = Api()
        val store = draft(api, { current }, this)
        runCurrent()
        assertTrue(store.editTitle("Garden day"))
        assertTrue(store.editChapterNarration(0, "Grandma showed us the flowers."))
        assertTrue(store.continueGuide())
        assertEquals(StoryGuideStep.REVIEW, store.state.value.guideStep)
        api.saveFailure = ApiFailure(FailureKind.HTTP, 409)
        assertTrue(store.confirmReviewed(true))
        assertTrue(store.save())
        runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.CONFLICT, store.state.value.status)

        api.previewFailure = ApiFailure(FailureKind.HTTP, 409)
        assertTrue(store.reloadPreview())
        runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.CONFLICT, store.state.value.status)
        assertEquals(StoryGuideStep.REVIEW, store.state.value.guideStep)
        api.previewFailure = null
        assertTrue(store.reloadPreview())
        runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.EDITING, store.state.value.status)
        assertEquals(StoryGuideStep.WORDS, store.state.value.guideStep)
        assertEquals("Grandma showed us the flowers.", store.state.value.editableChapters.single().narration)
        assertFalse(store.state.value.reviewed)
    }

    @Test fun uncertainGuideSaveRetriesTheExactFrozenRequestAndManualModeStaysDefault() = runTest {
        var current = binding()
        val api = Api()
        val store = draft(api, { current }, this)
        runCurrent()
        assertTrue(store.editTitle("Garden day"))
        assertTrue(store.editChapterNarration(0, "We met in the garden."))
        assertTrue(store.continueGuide())
        assertTrue(store.confirmReviewed(true))
        assertTrue(store.save())
        runCurrent()
        val frozen = api.saveBodies.single()
        assertEquals(StoryWorkspaceStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        assertTrue(store.retrySave())
        runCurrent()
        assertEquals(listOf(frozen, frozen), api.saveBodies)

        val manualApi = Api()
        val manual = StoryWorkspaceStore(StoryWorkspaceRepository(manualApi, currentBinding = { current }), this, { current })
        assertNull(manual.state.value.guideStep)
        assertTrue(manual.selectAsset("1"))
        assertTrue(manual.preview())
        runCurrent()
        assertNull(manual.state.value.guideStep)
        assertTrue(manual.editTitle("Manual story"))
        assertTrue(manual.confirmReviewed(true))
        assertTrue(manual.save())
        runCurrent()
        assertEquals(1, manualApi.saveBodies.size)
        assertNull(manual.state.value.guideStep)
    }
}
