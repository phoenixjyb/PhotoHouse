package dev.photohouse.connected

import android.graphics.Bitmap
import dev.photohouse.protocol.*
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.*
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder

@RunWith(AndroidJUnit4::class)
class GroupedStoryReviewUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun stop() { scope.cancel() }

    private class DraftPersistenceFixture : StoryDraftPersistence {
        var record: StoryDraftRecord? = null
        override fun load(scope: StoryDraftScope) = record?.takeIf { it.scope == scope }
        override fun write(record: StoryDraftRecord, expectedRevision: Long?, expectedRecordId: String?): StoryDraftRecord {
            val current = load(record.scope)
            if (expectedRevision == null) require(current == null)
            else require(current?.revision == expectedRevision && current.recordId == expectedRecordId)
            return record.copy(revision = (expectedRevision ?: 0L) + 1L).also { this.record = it }
        }
        override fun delete(scope: StoryDraftScope, expectedRecordId: String, expectedRevision: Long): Boolean {
            if (record?.scope != scope || record?.recordId != expectedRecordId || record?.revision != expectedRevision) return false
            record = null
            return true
        }
        override fun unreadableFingerprint(scope: StoryDraftScope): String? = null
        override fun deleteUnreadable(scope: StoryDraftScope, expectedFingerprint: String) = false
        override fun occupiedSlots() = if (record == null) 0 else 1
    }

    @Test fun explicitSaveDraftButtonStoresOnlyTheWordsTheUserEdited() {
        val bound = MemoryCommunityBinding(Bearer.from(SessionToken(86400, "D".repeat(43), "Bearer")), "family-a", 3)
        val api = object : StoryWorkspaceApi {
            override suspend fun storyPreview(token: Bearer, library: String, json: String) =
                """{"version":1,"library_id":"family-a","selection_revision":"${"d".repeat(64)}","state":"draft","saved":false,"title":"Generated title","theme":"everyday","language":"zh","generator":"evidence_outline","needs_review":true,"items":[{"id":"1","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/1/thumbnail?library=family-a","date_hint":null,"evidence":[]}],"chapters":[{"id":"chapter-1","title":"Generated chapter","narration":"Generated outline scaffold","asset_ids":["1"],"evidence_ids":[]}],"questions":[]}""".toByteArray()
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) =
                """{"version":1,"enabled":false,"max_suggestions":3,"needs_review":true}""".toByteArray()
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String) = error("unused")
        }
        val persistence = DraftPersistenceFixture()
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(api, { bound }), scope, { bound }, dictationApi = null,
            currentAccount = { "synthetic-member" }, localDraftPersistence = persistence)
        assertTrue(store.selectAsset("1"))
        var zh by mutableStateOf(true)
        rule.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f)) {
                PhotoHouseTheme { GroupedStoryReview(store, zh, {}, {}) }
            }
        }
        rule.onNodeWithTag("grouped-story-preview").performClick()
        rule.waitUntil(5000) { store.state.value.status == StoryWorkspaceStoreStatus.EDITING }
        rule.onNodeWithTag("grouped-story-chapter-words").performScrollTo().performTextReplacement("We planted basil together.")
        rule.onNodeWithTag("grouped-story-opening-title").performScrollTo().assertExists()
        rule.onNodeWithTag("grouped-story-opening-title-preview").assertTextEquals("We planted basil together.")
        rule.onNodeWithTag("grouped-story-opening-title-use").performScrollTo().assertIsEnabled()
        capture("chapter-opening-title-zh150.png")
        rule.runOnIdle { zh = false }
        rule.onNodeWithText("Title from a chapter opening").performScrollTo().assertExists()
        rule.onNodeWithTag("grouped-story-opening-title-use").performScrollTo().assertIsEnabled()
        capture("chapter-opening-title-en150.png")
        rule.onNodeWithTag("grouped-story-opening-title-use").performClick()
        rule.onNodeWithTag("grouped-story-title").performScrollTo().assertTextContains("We planted basil together.")
        rule.onNodeWithTag("local-story-draft-save").performScrollTo().assertIsEnabled().performClick()

        val saved = requireNotNull(persistence.record)
        assertTrue(saved.titleAuthored)
        assertEquals("We planted basil together.", saved.title)
        assertTrue(saved.chapters.single().narrationAuthored)
        assertEquals("We planted basil together.", saved.chapters.single().narration)
        assertFalse(saved.chapters.single().sourceIds.isNotEmpty())
        rule.onNodeWithTag("local-story-draft-saved").assertExists()
    }
    @Test fun bilingualLargeTextReviewAndUncertainRetryRemainReachable() {
        val bound = MemoryCommunityBinding(Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer")), "family-a", 1)
        val personal = """{"id":"family-11111111-1111-4111-8111-111111111111","source":"family","title":"合成个人讲述","text":"这是家人的原话，保留原本的语气。","revision":1}"""
        val shared = """{"id":"family-22222222-2222-4222-8222-222222222222","source":"family","title":"合成共享回忆","text":"两张照片共同留下的回忆。","revision":2,"origin_asset_id":"99","byline":"奶奶"}"""
        val sharedId = "family-22222222-2222-4222-8222-222222222222"
        val fake = object : StoryWorkspaceApi {
            override suspend fun storyPreview(token: Bearer, library: String, json: String) = """{"version":1,"library_id":"family-a","selection_revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","state":"draft","saved":false,"title":"花园里的一天","theme":"everyday","language":"zh","generator":"evidence_outline","needs_review":true,"items":[{"id":"1","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/1/thumbnail?library=family-a","date_hint":null,"evidence":[$personal,$shared]},{"id":"2","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/2/thumbnail?library=family-a","date_hint":null,"evidence":[$shared]}],"chapters":[{"id":"chapter-1","title":"一起种花","narration":"我们在花园里一起种花。","asset_ids":["1","2"],"evidence_ids":["family-11111111-1111-4111-8111-111111111111","$sharedId"]}],"questions":["那一天，还有什么想留下的回忆？"]}""".toByteArray()
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) =
                """{"version":1,"enabled":false,"max_suggestions":3,"needs_review":true}""".toByteArray()
            override suspend fun storySourceCapabilities(token: Bearer, library: String) =
                """{"version":1,"source_policy":"chapter_sources_v1","max_sources_per_chapter":12,"needs_review":true}""".toByteArray()
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("disabled")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray =
                throw ApiFailure(FailureKind.OFFLINE)
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String, sourceReview: Boolean): ByteArray =
                throw ApiFailure(FailureKind.OFFLINE)
        }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(fake, { bound }), scope, { bound })
        store.selectAsset("1")
        store.selectAsset("2")
        var zh by mutableStateOf(true)
        rule.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f)) {
                PhotoHouseTheme { GroupedStoryReview(store, zh, {}, {}) }
            }
        }
        rule.onNodeWithTag("grouped-story-preview").performClick()
        rule.waitUntil(5000) { store.state.value.status == StoryWorkspaceStoreStatus.EDITING }
        rule.onNodeWithTag("grouped-story-title").performScrollTo().assertTextContains("花园里的一天")
        capture("grouped-story-review-zh150.png")
        rule.onNodeWithText("核对来源（2）").performScrollTo().performClick()
        rule.onAllNodesWithText("家人讲述").assertCountEquals(2)
        rule.onNodeWithText("这是家人的原话，保留原本的语气。").assertExists()
        rule.onNodeWithText("family-11111111-1111-4111-8111-111111111111").assertDoesNotExist()
        rule.onAllNodesWithTag("grouped-story-source-$sharedId").assertCountEquals(1)
        rule.onNodeWithTag("grouped-story-source-origin-$sharedId").assertTextEquals("来源素材 99")
        rule.onNodeWithTag("grouped-story-source-byline-$sharedId").assertTextEquals("原记录署名：奶奶")
        capture("grouped-story-sources-zh150.png")
        rule.onNodeWithTag("grouped-story-source-review-enable").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.sourceReviewEnabled }
        val selectedEvidence = rule.onNodeWithTag("grouped-story-evidence-chapter-1-$sharedId").performScrollTo()
        selectedEvidence.assertIsOn()
        rule.onNodeWithTag("grouped-story-reviewed").performScrollTo().performClick()
        selectedEvidence.performClick().assertIsOff()
        rule.onNodeWithTag("grouped-story-reviewed").assertIsOff()
        rule.onNodeWithTag("grouped-story-evidence-chapter-1-$sharedId").performClick().assertIsOn()
        capture("grouped-story-source-choices-zh150.png")
        rule.onNodeWithTag("grouped-story-save").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("grouped-story-reviewed").performScrollTo().performClick()
        rule.onNodeWithTag("grouped-story-save").performScrollTo().assertIsEnabled()
        rule.onNodeWithTag("grouped-story-title").performScrollTo().performTextReplacement("家人讲述的花园故事")
        rule.onNodeWithTag("grouped-story-save").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("grouped-story-reviewed").performScrollTo().assertIsOff().performClick()
        rule.onNodeWithTag("grouped-story-save").performScrollTo().assertIsEnabled()
        rule.runOnIdle { zh = false }
        rule.onNodeWithTag("grouped-story-title").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("grouped-story-source-origin-$sharedId").assertTextEquals("Source item 99")
        rule.onNodeWithTag("grouped-story-source-byline-$sharedId").assertTextEquals("Original byline: 奶奶")
        capture("grouped-story-sources-en150.png")
        capture("grouped-story-review-en150.png")
        rule.onNodeWithTag("grouped-story-save").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.status == StoryWorkspaceStoreStatus.SAVE_UNCERTAIN }
        rule.onNodeWithTag("grouped-story-retry").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("grouped-story-close").performScrollTo().performClick()
        rule.onNodeWithText("Leave this draft?").assertIsDisplayed()
        rule.onNodeWithText("Keep editing").performClick()
        Assert.assertTrue(store.state.value.hasPendingSave)
    }

    @Test fun chapterNarrationDictationReviewChineseAt150Percent() = chapterDictationJourney("zh")
    @Test fun chapterNarrationDictationReviewEnglishAt150Percent() = chapterDictationJourney("en")

    @Test fun chapterArrangementChineseAt150Percent() = chapterArrangementJourney("zh")
    @Test fun chapterArrangementEnglishAt150Percent() = chapterArrangementJourney("en")

    private fun chapterArrangementJourney(language: String) {
        val bound = MemoryCommunityBinding(Bearer.from(SessionToken(86400, "A".repeat(43), "Bearer")), "family-a", 8)
        val sharedId = "family-33333333-3333-4333-8333-333333333333"
        val evidence = """{"id":"$sharedId","source":"family","title":"Activity","text":"Shared original words","revision":1,"origin_asset_id":"1","byline":"Synthetic author"}"""
        val items = (1..2).joinToString(",") { id ->
            """{"id":"$id","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/$id/thumbnail?library=family-a","date_hint":null,"evidence":[$evidence]}"""
        }
        val fake = object : StoryWorkspaceApi {
            override suspend fun storyPreview(token: Bearer, library: String, json: String) =
                """{"version":1,"library_id":"family-a","selection_revision":"${"c".repeat(64)}","state":"draft","saved":false,"title":"Garden day","theme":"everyday","language":"$language","generator":"evidence_outline","needs_review":true,"items":[$items],"chapters":[{"id":"chapter-1","title":"Together","narration":"Original chapter words","asset_ids":["1","2"],"evidence_ids":["$sharedId"]}],"questions":[]}""".toByteArray()
            override suspend fun storySourceCapabilities(token: Bearer, library: String) =
                """{"version":1,"source_policy":"chapter_sources_v1","max_sources_per_chapter":12,"needs_review":true}""".toByteArray()
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) =
                """{"version":1,"enabled":false,"max_suggestions":3,"needs_review":true}""".toByteArray()
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray = error("legacy unused")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String, sourceReview: Boolean): ByteArray =
                throw ApiFailure(FailureKind.OFFLINE)
        }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(fake, { bound }), scope, { bound })
        assertTrue(store.selectAsset("1")); assertTrue(store.selectAsset("2")); assertTrue(store.setLanguage(language))
        rule.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f)) {
                PhotoHouseTheme { GroupedStoryReview(store, language == "zh", {}, {}) }
            }
        }
        rule.onNodeWithTag("grouped-story-preview").performClick()
        rule.waitUntil(5000) { store.state.value.status == StoryWorkspaceStoreStatus.EDITING }
        rule.onNodeWithTag("grouped-story-arrange-toggle").assertDoesNotExist()
        rule.onNodeWithTag("grouped-story-source-review-enable").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.sourceReviewEnabled }
        rule.onNodeWithTag("grouped-story-reviewed").performScrollTo().performClick()
        rule.onNodeWithTag("grouped-story-arrange-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("grouped-story-split-1").performScrollTo().assertIsEnabled()
        capture("grouped-story-arrange-$language-150.png")
        rule.onNodeWithTag("grouped-story-split-1").performClick()
        rule.waitUntil(5000) { store.state.value.editableChapters.size == 2 }
        assertFalse(store.state.value.reviewed)
        assertEquals(listOf(listOf("1"), listOf("2")), store.state.value.editableChapters.map { it.assetIds })
        assertEquals("Original chapter words", store.state.value.editableChapters[0].narration)
        assertEquals("", store.state.value.editableChapters[1].narration)
        assertEquals(listOf(sharedId), store.state.value.editableChapters[0].evidenceIds)
        assertTrue(store.state.value.editableChapters[1].evidenceIds.isEmpty())
        rule.onNodeWithTag("grouped-story-arrange-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("grouped-story-merge-next").performScrollTo().assertIsEnabled().performClick()
        rule.waitUntil(5000) { store.state.value.editableChapters.size == 1 }
        assertEquals(listOf("1", "2"), store.state.value.editableChapters.single().assetIds)
        assertEquals("Original chapter words", store.state.value.editableChapters.single().narration)
        assertEquals(listOf(sharedId), store.state.value.editableChapters.single().evidenceIds)
        rule.onNodeWithTag("grouped-story-reviewed").performScrollTo().performClick()
        rule.onNodeWithTag("grouped-story-save").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.hasPendingSave }
        rule.onNodeWithTag("grouped-story-arrange-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("grouped-story-split-1").performScrollTo().assertIsNotEnabled()
    }

    private fun chapterDictationJourney(language: String) {
        val bound = MemoryCommunityBinding(Bearer.from(SessionToken(86400, "R".repeat(43), "Bearer")), "family-a", 5)
        val storyApi = object : StoryWorkspaceApi {
            override suspend fun storyPreview(token: Bearer, library: String, json: String) =
                """{"version":1,"library_id":"family-a","selection_revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","state":"draft","saved":false,"title":"Draft","theme":"everyday","language":"$language","generator":"evidence_outline","needs_review":true,"items":[{"id":"1","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/1/thumbnail?library=family-a","date_hint":null,"evidence":[]}],"chapters":[{"id":"chapter-1","title":"A day","narration":"Typed before dictation","asset_ids":["1"],"evidence_ids":[]}],"questions":[]}""".toByteArray()
            override suspend fun storyTitleCapabilities(token: Bearer, library: String) =
                """{"version":1,"enabled":false,"max_suggestions":3,"needs_review":true}""".toByteArray()
            override suspend fun storyTitles(token: Bearer, library: String, json: String) = error("unused")
            override suspend fun createGroupedStory(token: Bearer, library: String, json: String) = error("unused")
        }
        val voiceApi = object : PhotoHouseApi {
            override val assistantEnabled = true
            var capabilityRequests = 0
            override suspend fun assistantCapabilities(token: Bearer, library: String): AssistantCapabilities {
                capabilityRequests++
                return AssistantCapabilities(true, true, true, false, 5)
            }
            override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String) =
                AssistantTranscript(if (language == "zh") "口述补充" else "Spoken addition", language,
                    AssistantRequestReceipt(requestId, "enabled", "succeeded"))
            override suspend fun login(phone: String, password: String) = SessionToken(86400, "R".repeat(43), "Bearer")
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
        }
        val store = StoryWorkspaceStore(StoryWorkspaceRepository(storyApi, { bound }), scope, { bound },
            dictationApi = voiceApi, currentAccount = { "member" })
        assertTrue(store.selectAsset("1"))
        assertTrue(store.setLanguage(language))
        val zh = language == "zh"
        rule.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f)) {
                PhotoHouseTheme { GroupedStoryReview(store, zh, {}, {}) }
            }
        }
        rule.onNodeWithTag("grouped-story-preview").performClick()
        rule.waitUntil(5000) { store.state.value.status == StoryWorkspaceStoreStatus.EDITING }
        assertEquals(0, voiceApi.capabilityRequests)
        rule.onNodeWithTag("grouped-story-dictate").performScrollTo().performClick()
        rule.waitUntil(5000) { store.chapterDictation.value?.state?.value?.capabilities?.transcribe == true }
        assertEquals(1, voiceApi.capabilityRequests)
        val session = store.chapterDictation.value!!
        rule.runOnIdle { assertNotNull(session.beginRecording()); session.stopRecording(uiSyntheticWav()) }
        rule.waitUntil(5000) { session.state.value.transcript != null }
        rule.onNodeWithTag("memory-dictation-transcript-ready").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-dictation-insert").assertTextEquals(if (zh) "加入本篇" else "Add to chapter")
        rule.onNodeWithTag("grouped-story-dictation-close").performScrollTo().performClick()
        rule.onNodeWithText(if (zh) "丢弃这段口述？" else "Discard this dictation?").assertExists()
        rule.onNodeWithText(if (zh) "保留口述" else "Keep dictation").performClick()
        rule.onNodeWithTag("memory-dictation-transcript-ready").performScrollTo().assertExists()
        val help = if (zh) "转写回执会保留识别文字和处理状态 30 天" else "Transcription receipts keep recognized text and processing status for 30 days"
        rule.onNodeWithText(help, substring = true).performScrollTo().assertExists()
        val saveCopy = if (zh) "准备好后请手动保存故事" else "Save the story yourself when ready"
        rule.onNodeWithText(saveCopy, substring = true).performScrollTo().assertExists()
        rule.onNodeWithTag("grouped-story-save").performScrollTo().assertIsNotEnabled()
        capture("grouped-story-dictation-${language}-150.png")
        rule.onNodeWithTag("grouped-story-chapter-words").performScrollTo().performTextReplacement(if (zh) "核对时补写" else "Typed during review")
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().performClick()
        val addition = if (zh) "口述补充" else "Spoken addition"
        val typed = if (zh) "核对时补写" else "Typed during review"
        rule.waitUntil(5000) { store.state.value.editableChapters.singleOrNull()?.narration == "$typed\n\n$addition" }
        assertEquals("$typed\n\n$addition", store.state.value.editableChapters.single().narration)
        rule.onNodeWithTag("grouped-story-reviewed").performScrollTo().assertIsEnabled()
    }

    private fun uiSyntheticWav(): ByteArray {
        val pcm = ByteArray(16_000 * 2)
        return ByteArray(44 + pcm.size).also { wav ->
            val out = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
            out.put("RIFF".toByteArray()); out.putInt(wav.size - 8)
            out.put("WAVEfmt ".toByteArray()); out.putInt(16); out.putShort(1); out.putShort(1)
            out.putInt(16_000); out.putInt(32_000); out.putShort(2); out.putShort(16)
            out.put("data".toByteArray()); out.putInt(pcm.size); out.put(pcm)
            pcm.fill(0)
        }
    }
    private fun capture(name: String) {
        val image = rule.onNodeWithTag("grouped-story-review").captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        File(context.filesDir, name).outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
}
