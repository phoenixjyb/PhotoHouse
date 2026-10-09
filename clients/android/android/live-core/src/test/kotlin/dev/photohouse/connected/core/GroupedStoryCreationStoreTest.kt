package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class GroupedStoryCreationStoreTest {
    private val examples = javaClass.classLoader!!.getResourceAsStream("story-workspace-contract/examples.json")!!.use {
        Json.parseToJsonElement(it.readBytes().toString(Charsets.UTF_8)).jsonObject
    }
    private val storyId = "33333333-3333-4333-8333-333333333333"

    private fun fixtureBytes(name: String) = examples.getValue(name).toString().toByteArray(Charsets.UTF_8)

    private inner class FakeApi(
        var role: String = "viewer",
        var canCreate: Boolean = true,
    ) : PhotoHouseApi, StoryWorkspaceApi, MemoryCommunityApi {
        override val protectedNativeV2Enabled = true
        var listCalls = 0
        var galleryPages = mutableListOf<Int>()
        var freshStoryReads = 0
        var detailFailures = 0
        var thumbnailGate: CompletableDeferred<Unit>? = null
        var lateThumbnail: ByteArray? = null
        val thumbnailBuffers = mutableListOf<ByteArray>()
        var previewGate: CompletableDeferred<Unit>? = null
        var latePreview: ByteArray? = null
        var textGate: CompletableDeferred<Unit>? = null
        var audioGate: CompletableDeferred<Unit>? = null
        val textRequests = mutableListOf<String>()
        val audioMetadata = mutableListOf<String>()

        private val savedSummary by lazy {
            val story = ProtectedMemoryStoriesWire.detail(
                fixtureBytes("create_retry_after_edit"), "family-a", storyId, 2,
            )
            SavedMemoryStorySummary(story.id, story.title, story.theme, story.language, story.revision,
                story.items.first().asset.id, story.items.size, story.chapters.size, story.updatedAt, story.canEdit)
        }

        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("synthetic-account", "+12025550123", listOf(
            Membership("family-a", "approved", role, 1, null, 0, true),
        ))
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit

        override suspend fun gallery(token: Bearer, library: String, page: Int): Gallery {
            galleryPages += page
            val asset = if (page == 1) asset("102", "video") else asset("101", "image")
            return Gallery(library, page, 1, 2, false, listOf(asset))
        }

        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, asset(assetId))
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray {
            val bytes = ByteArray(12) { (it + 1).toByte() }
            thumbnailBuffers += bytes
            val gate = thumbnailGate
            if (gate != null && asset.id == "102") {
                lateThumbnail = bytes
                withContext(NonCancellable) { gate.await() }
            }
            return bytes
        }
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) =
            VideoChunk(start, 1, byteArrayOf(0))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf(1)

        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int): SavedMemoryStoryPage {
            listCalls++
            return SavedMemoryStoryPage(library, page, 8, false, canCreate,
                if (listCalls > 1) listOf(savedSummary) else emptyList())
        }
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int, theme: String?): SavedMemoryStoryPage =
            savedMemoryStories(token, library, page)

        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            freshStoryReads++
            if (detailFailures > 0) {
                detailFailures--
                throw ApiFailure(FailureKind.OFFLINE)
            }
            return ProtectedMemoryStoriesWire.detail(fixtureBytes("create_retry_after_edit"), library, storyId, revision)
        }

        override suspend fun storyPreview(token: Bearer, library: String, json: String): ByteArray {
            previewGate?.let { withContext(NonCancellable) { it.await() } }
            return fixtureBytes("preview").also { if (previewGate != null) latePreview = it }
        }
        override suspend fun storyTitleCapabilities(token: Bearer, library: String) = fixtureBytes("title_capabilities_off")
        override suspend fun storyTitles(token: Bearer, library: String, json: String) = fixtureBytes("titles")
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String) = fixtureBytes("created")

        override suspend fun capabilities(token: Bearer, library: String) =
            """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()

        override suspend fun listContributions(token: Bearer, library: String, storyId: String, page: Int) =
            """{"version":1,"story_id":"$storyId","page":$page,"page_size":16,"has_more":false,"can_review":false,"can_delete":false,"items":[]}""".toByteArray()

        override suspend fun createTextContribution(token: Bearer, library: String, storyId: String, json: String): ByteArray {
            textRequests += json
            textGate?.let { withContext(NonCancellable) { it.await() } }
            throw ApiFailure(FailureKind.OFFLINE)
        }

        override suspend fun createAudioContribution(
            token: Bearer, library: String, storyId: String, metadataBase64: String, wav: ByteArray,
        ): ByteArray {
            audioMetadata += metadataBase64
            audioGate?.let { withContext(NonCancellable) { it.await() } }
            throw ApiFailure(FailureKind.OFFLINE)
        }

        private fun asset(id: String, kind: String = "image") = Asset(
            id, kind, 640, 480, if (kind == "video") 2.0 else null, null,
            "/assets/$id/thumbnail?library=family-a",
        )
    }

    private fun TestScope.newStore(api: FakeApi, community: Boolean = false) = ConnectedStore(
        api, backgroundScope, memoryCommunityApi = api, memoryCommunityEnabled = community,
    ) { testScheduler.currentTime }

    private suspend fun TestScope.signIn(store: ConnectedStore) {
        store.authenticate("+12025550123", "synthetic-password-only")
        runCurrent()
        assertEquals("family-a", store.state.value.library)
    }

    private suspend fun TestScope.createReceiptAndOpenReader(store: ConnectedStore) {
        signIn(store)
        assertTrue(store.beginGroupedStoryCreation())
        runCurrent()
        val editor = store.state.value.groupedStoryCreation!!.editor!!
        assertEquals(listOf("102"), store.state.value.groupedStoryCreation!!.gallery!!.items.map { it.id })
        assertTrue(editor.selectAsset("102"))
        val firstPageThumb = store.state.value.groupedStoryCreation!!.previews.getValue("102")
        assertTrue(store.loadGroupedStorySelectionPage(2))
        assertTrue(firstPageThumb.all { it == 0.toByte() })
        runCurrent()
        assertEquals(listOf("102"), editor.state.value.selectedAssetIds)
        assertEquals(listOf("101"), store.state.value.groupedStoryCreation!!.gallery!!.items.map { it.id })
        assertTrue(editor.selectAsset("101"))
        assertEquals(listOf("102", "101"), editor.state.value.selectedAssetIds)
        assertTrue(editor.setTheme("trip"))
        assertTrue(editor.preview())
        runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.EDITING, editor.state.value.status)
        assertTrue(editor.confirmReviewed(true))
        assertTrue(editor.save())
        runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.SAVED, editor.state.value.status)
        assertTrue(store.readCreatedGroupedStory())
        runCurrent()
    }

    @Test fun serverCanCreateDeniesOwnersAndContributorsWhenCapabilityIsFalse() = runTest {
        for (role in listOf("owner", "contributor")) {
            val api = FakeApi(role = role, canCreate = false)
            val store = newStore(api)
            signIn(store)
            val galleriesBeforeProbe = api.galleryPages.size
            assertTrue(store.beginGroupedStoryCreation())
            runCurrent()
            val creation = store.state.value.groupedStoryCreation
            assertEquals(false, creation?.canCreate)
            assertNull(creation?.editor)
            assertNull(creation?.gallery)
            assertEquals("denied capability must not fetch a grouped selection page", galleriesBeforeProbe, api.galleryPages.size)
        }
    }

    @Test fun protectedPagingPreservesOrderedSelectionAndWipesPreviousPageThumbs() = runTest {
        val api = FakeApi()
        val store = newStore(api)
        signIn(store)
        assertTrue(store.beginGroupedStoryCreation())
        runCurrent()
        val creation = store.state.value.groupedStoryCreation!!
        val editor = creation.editor!!
        assertTrue(editor.selectAsset("102"))
        val oldThumb = creation.previews.getValue("102")
        assertTrue(store.loadGroupedStorySelectionPage(2))
        assertTrue(oldThumb.all { it == 0.toByte() })
        runCurrent()
        assertEquals(listOf("102"), editor.state.value.selectedAssetIds)
        assertEquals(2, store.state.value.groupedStoryCreation?.gallery?.page)
        assertTrue(editor.selectAsset("101"))
        assertEquals(listOf("102", "101"), editor.state.value.selectedAssetIds)
    }

    @Test fun backgroundAndLogoutFenceLateThumbnailResponsesAndWipeReturnedBytes() = runTest {
        for (boundary in listOf("background", "logout")) {
            val gate = CompletableDeferred<Unit>()
            val api = FakeApi()
            val store = newStore(api)
            signIn(store)
            api.thumbnailGate = gate
            assertTrue(store.beginGroupedStoryCreation())
            runCurrent()
            val late = api.lateThumbnail
            assertNotNull("$boundary should reach the delayed protected thumbnail", late)
            if (boundary == "background") store.background() else store.logout()
            runCurrent()
            gate.complete(Unit)
            runCurrent()
            assertTrue("$boundary must wipe the late response", late!!.all { it == 0.toByte() })
            assertNull(store.state.value.groupedStoryCreation)
        }
    }

    @Test fun backgroundDuringOutlinePreviewFencesAndWipesLateDraftResponse() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = FakeApi().apply { previewGate = gate }
        val store = newStore(api)
        signIn(store)
        assertTrue(store.beginGroupedStoryCreation())
        runCurrent()
        val editor = store.state.value.groupedStoryCreation!!.editor!!
        assertTrue(editor.selectAsset("102"))
        assertTrue(store.loadGroupedStorySelectionPage(2))
        runCurrent()
        assertTrue(editor.selectAsset("101"))
        assertTrue(editor.setTheme("trip"))
        assertTrue(editor.preview())
        runCurrent()
        assertEquals(StoryWorkspaceStoreStatus.PREVIEWING, editor.state.value.status)

        store.background()
        runCurrent()
        assertNull(store.state.value.groupedStoryCreation)
        gate.complete(Unit)
        runCurrent()
        assertTrue(api.latePreview!!.all { it == 0.toByte() })
        assertNull(store.state.value.groupedStoryCreation)
        assertNull(editor.state.value.draft)
    }

    @Test fun createdReceiptOpensFreshReaderRetriesTransientReadAndCloseReturnsToShelf() = runTest {
        val api = FakeApi().apply { detailFailures = 1 }
        val store = newStore(api, community = true)
        createReceiptAndOpenReader(store)

        val first = store.state.value.savedMemoryStories
        assertNotNull(first)
        assertNull("the receipt opens a reader without first loading a shelf", first?.result)
        assertNull(first?.detail)
        assertTrue(first?.detailUnavailable == true)
        assertEquals(1, api.freshStoryReads)
        assertEquals("creation checked capability but did not load a story shelf", 1, api.listCalls)

        store.retrySavedMemoryStory()
        runCurrent()
        val read = store.state.value.savedMemoryStories!!
        assertEquals(2, api.freshStoryReads)
        assertEquals(2L, read.detail?.revision)
        assertEquals("家人修改后的标题", read.detail?.title)
        assertEquals("我们一起种花，这是家人留下的回忆。", read.detail?.chapters?.single()?.narration)
        assertNull(read.result)
        assertTrue(read.community?.contributionWholeStory == true)

        store.closeSavedMemoryStoryDetail()
        runCurrent()
        val shelf = store.state.value.savedMemoryStories
        assertNotNull(shelf?.result)
        assertEquals(storyId, shelf?.result?.items?.single()?.id)
        assertEquals(2L, shelf?.result?.items?.single()?.revision)
        assertNull(shelf?.detail)
        assertEquals(2, api.listCalls)
    }

    @Test fun receiptReaderFreezesWholeStoryScopeForPendingTextAndAudioSubmissions() = runTest {
        val api = FakeApi()
        val store = newStore(api, community = true)
        createReceiptAndOpenReader(store)
        assertTrue(store.state.value.savedMemoryStories?.community?.contributionWholeStory == true)

        val textGate = CompletableDeferred<Unit>()
        api.textGate = textGate
        store.submitMemoryText("synthetic family words", "zh", "", consent = true)
        runCurrent()
        var community = store.state.value.savedMemoryStories!!.community!!
        assertEquals("text", community.pendingText?.kind)
        assertNull(community.pendingText?.chapterId)
        store.updateMemoryContributionWholeStory(false)
        assertTrue(store.state.value.savedMemoryStories?.community?.contributionWholeStory == true)
        assertEquals("", Json.parseToJsonElement(api.textRequests.single()).jsonObject.getValue("chapter_id").jsonPrimitive.content)

        store.closeSavedMemoryStories()
        runCurrent()
        textGate.complete(Unit)
        runCurrent()
        assertNull(store.state.value.savedMemoryStories)

        // A second receipt proves the audio request keeps the same whole-story binding.
        val audioApi = FakeApi()
        val audioStore = newStore(audioApi, community = true)
        createReceiptAndOpenReader(audioStore)
        val audioGate = CompletableDeferred<Unit>()
        audioApi.audioGate = audioGate
        audioStore.submitMemoryAudio(syntheticAnnotationWav(), "zh", "", consent = true)
        runCurrent()
        community = audioStore.state.value.savedMemoryStories!!.community!!
        assertEquals("audio", community.pendingAudio?.kind)
        assertNull(community.pendingAudio?.chapterId)
        audioStore.updateMemoryContributionWholeStory(false)
        assertTrue(audioStore.state.value.savedMemoryStories?.community?.contributionWholeStory == true)
        val audioRequest = Json.parseToJsonElement(
            String(java.util.Base64.getDecoder().decode(audioApi.audioMetadata.single()), Charsets.UTF_8),
        ).jsonObject
        assertEquals("", audioRequest.getValue("chapter_id").jsonPrimitive.content)

        audioStore.closeSavedMemoryStories()
        runCurrent()
        audioGate.complete(Unit)
        runCurrent()
        assertNull(audioStore.state.value.savedMemoryStories)
    }
}
