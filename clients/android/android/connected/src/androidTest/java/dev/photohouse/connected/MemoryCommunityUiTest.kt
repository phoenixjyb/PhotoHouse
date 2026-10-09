package dev.photohouse.connected

import android.graphics.Bitmap
import android.content.ContentValues
import android.provider.MediaStore
import android.os.Environment
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import androidx.test.platform.app.InstrumentationRegistry
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.setValue
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.security.MessageDigest
import java.util.Locale
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry

private fun syntheticMemoryAudioWav(durationMillis: Int): ByteArray {
    val pcm = ByteArray(16_000 * 2 * durationMillis / 1000)
    val wav = ByteArray(44 + pcm.size)
    val out = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
    out.put("RIFF".toByteArray()); out.putInt(wav.size - 8)
    out.put("WAVEfmt ".toByteArray()); out.putInt(16); out.putShort(1); out.putShort(1)
    out.putInt(16_000); out.putInt(32_000); out.putShort(2); out.putShort(16)
    out.put("data".toByteArray()); out.putInt(pcm.size); out.put(pcm)
    pcm.fill(0)
    return wav
}

@RunWith(AndroidJUnit4::class)
class MemoryCommunityUiTest {
    private val bookId = "66666666-6666-6666-6666-666666666666"
    private val bookStory2 = "77777777-7777-7777-7777-777777777777"
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val id = "11111111-1111-1111-1111-111111111111"
    private val contributor = "22222222-2222-2222-2222-222222222222"
    private val contributionId = "33333333-3333-3333-3333-333333333333"
    private val conversation = "44444444-4444-4444-4444-444444444444"
    private val jobId = "55555555-5555-5555-5555-555555555555"
    private val proposalNarration = "这是一段供阅读核对的故事建议，未写回保存内容。".repeat(12)
    private val photo = Asset("1", "image", 80, 60, null, null, "/assets/1/thumbnail?library=family")
    private val narrativeBookRevision = 1L
    private val narrativeStoryRevision = 3L
    private val narrativeStoryIds = listOf(
        id,
        bookStory2,
        "88888888-8888-8888-8888-888888888888",
        "99999999-9999-9999-9999-999999999999",
    )
    private fun narrativeStoryId(index: Int) = narrativeStoryIds[index]
    private fun narrativeStoryTitle(index: Int) = when (index) {
        0 -> "花园的一天"
        1 -> "野餐回忆"
        2 -> "家人整理旧照片"
        else -> "第四则家庭回忆：从花园、野餐到再次相聚的完整故事标题"
    }
    private fun narrativeChapterTitle(storyIndex: Int, chapterIndex: Int) =
        if (storyIndex == 3 && chapterIndex == 5)
            "第六章：家人一路回望后补充的最后一段细节与感受"
        else "${chapterIndex + 1} · 家人记得的片段"
    private fun narrativeChapterText(index: Int) = when (index) {
        0 -> "奶奶讲起那天的花园，大家各自补充记得的片段。"
        1, 6 -> "野餐的讲述接续另一段家人回忆，时间仍待确认。"
        23 -> "第二十四篇章的合成建议，保留家人说法并等待核对。"
        else -> "合成篇章 ${index + 1} 的待核对建议。"
    }
    private val summary = SavedMemoryStorySummary(id, "花园的一天", "everyday", "zh", 3, "1", 1, 1, 10, false)
    private val previewFontScale = mutableFloatStateOf(1f)
    private val screenshotRunId = System.currentTimeMillis()

    @Test fun replyQuestionReplacementRejectsTypedOrComposingComposer() {
        assertTrue(canReplaceComposerWithReplyQuestion(TextFieldValue("")))
        assertFalse(canReplaceComposerWithReplyQuestion(TextFieldValue("unfinished text")))
        assertFalse(canReplaceComposerWithReplyQuestion(TextFieldValue(
            text = "", selection = TextRange.Zero, composition = TextRange(0, 0))))
    }

    @Test fun conversationRestorationNoticeIsLocalizedWithoutAutomaticVoiceOrSend() {
        val communityApi = CommunityApi()
        val storyApi = StoryApi()
        val store = ConnectedStore(storyApi, scope, memoryCommunityApi = communityApi, memoryCommunityEnabled = true)
        val story = SavedMemoryStory(
            id, "family", 3, 1, 10, false, "a".repeat(64), "花园的一天", "everyday", "zh",
            listOf(MemoryStoryAsset(photo, emptyList())),
            listOf(SavedMemoryStoryChapter("chapter-1", "早晨", "奶奶带我们走进花园。", listOf("1"), emptyList())), emptyList(),
        )
        val restored = MemoryCommunityStoryState(
            id, capabilities = MemoryCommunityCapabilities(true, true, true, 30, "wav_pcm16_mono_16000", 30, 8192,
                "until_owner_deletes"),
            conversations = MemoryConversationPage(listOf(MemoryConversationSummary(conversation, 1_780_000_000, 4_102_444_800))),
            conversationId = conversation, tab = 1, conversationRestored = true,
        )
        var chinese by androidx.compose.runtime.mutableStateOf(true)
        rule.setContent {
            MaterialTheme {
                MemoryCommunityPanel(store, SavedMemoryStoriesReading("family", detail = story, community = restored), chinese)
            }
        }

        rule.onNodeWithTag("memory-chat-restored").assertTextEquals("已回到上次选择的对话。")
        rule.runOnIdle { chinese = false }
        rule.onNodeWithTag("memory-chat-restored").assertTextEquals("Back in the conversation you last selected.")
        assertEquals(0, communityApi.chatSent)
        assertEquals(0, storyApi.assistantTranscriptions)
    }

    @Test fun storyConversationRestoresZh150() = conversationReaderRestoration("zh", false)
    @Test fun storyConversationRestoresEn150() = conversationReaderRestoration("en", false)
    @Test fun memoirConversationRestoresZh150() = conversationReaderRestoration("zh", true)
    @Test fun memoirConversationRestoresEn150() = conversationReaderRestoration("en", true)

    private fun conversationReaderRestoration(language: String, memoir: Boolean) {
        val community = CommunityApi()
        val storyApi = StoryApi()
        val store = ConnectedStore(storyApi, scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = language)
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        val prefix = if (memoir) "memory-book-chat" else "memory-chat"
        fun selected() = if (memoir) store.state.value.memoryBooks?.companion?.conversationId
            else store.state.value.savedMemoryStories?.community?.conversationId
        fun openReader() {
            if (memoir) {
                rule.onNodeWithTag("memory-book-$bookId").performScrollTo().performClick()
                rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
                rule.onNodeWithTag("memory-book-entry-0").performScrollTo().performClick()
                rule.waitUntil(5000) { store.state.value.memoryBooks?.story?.id == id && store.state.value.memoryBooks?.companion != null }
                rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
            } else {
                rule.onNodeWithTag("saved-memory-story-$id").performScrollTo().performClick()
                rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.capabilities != null }
                rule.onNodeWithTag("memory-community-tab-1").performScrollTo().performClick()
            }
        }
        rule.onNodeWithTag(if (memoir) "open-memory-books" else "open-saved-memory-stories")
            .performScrollTo().performClick()
        rule.waitUntil(5000) {
            if (memoir) store.state.value.memoryBooks?.result != null
            else store.state.value.savedMemoryStories?.result != null
        }
        openReader()
        rule.onNodeWithTag("$prefix-start").performScrollTo().performClick()
        rule.waitUntil(5000) { selected() != null }
        val first = selected()
        rule.onNodeWithTag("$prefix-new").performScrollTo().performClick()
        rule.waitUntil(5000) { selected() != null && selected() != first }
        rule.onNodeWithTag("$prefix-thread-1").performScrollTo().performClick()
        rule.waitUntil(5000) { selected() == first }
        rule.runOnIdle {
            if (memoir) store.updateMemoryBookChatDraft("private unsent memoir words")
            else store.updateMemoryChatDraft("private unsent story words")
        }
        val beforeReads = community.conversationDirectoryReads
        rule.onNodeWithTag(if (memoir) "memory-books-back" else "saved-memory-back-list")
            .performClick()
        rule.onNodeWithTag(if (memoir) "memory-book-discard-confirm" else "memory-community-discard-confirm").performClick()
        openReader()
        rule.waitUntil(5000) {
            if (memoir) store.state.value.memoryBooks?.companion?.conversationRestored == true
            else store.state.value.savedMemoryStories?.community?.conversationRestored == true
        }
        rule.onNodeWithTag("$prefix-restored").performScrollTo().assertIsDisplayed()
            .assertTextEquals(if (language == "zh") "已回到上次选择的对话。"
                else "Back in the conversation you last selected.")
        if (memoir) captureBooks("navigation-memoir-$language-150")
        else capture("navigation-story-$language-150")
        rule.onNodeWithTag("$prefix-input").performScrollTo()
        rule.runOnIdle {
            assertEquals(first, selected())
            assertEquals("", if (memoir) store.state.value.memoryBooks?.companion?.draft
                else store.state.value.savedMemoryStories?.community?.chatDraft)
            assertEquals(beforeReads + 1, community.conversationDirectoryReads)
            assertEquals(2, community.conversationStarted)
            assertEquals(0, community.chatSent)
            assertEquals(0, storyApi.assistantTranscriptions)
        }
        assertEquals("", rule.onNodeWithTag("$prefix-input").fetchSemanticsNode()
            .config[SemanticsProperties.EditableText].text)
    }

    private fun syntheticGardenPng(title: String, background: Int): ByteArray {
        val bitmap = Bitmap.createBitmap(480, 320, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(background)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        paint.color = Color.rgb(75, 105, 79)
        canvas.drawRect(0f, 250f, 480f, 320f, paint)
        paint.color = Color.rgb(112, 139, 91)
        canvas.drawCircle(100f, 172f, 72f, paint)
        canvas.drawCircle(215f, 145f, 84f, paint)
        canvas.drawCircle(350f, 182f, 65f, paint)
        paint.color = Color.rgb(231, 203, 143)
        canvas.drawCircle(123f, 177f, 12f, paint)
        canvas.drawCircle(236f, 141f, 13f, paint)
        canvas.drawCircle(331f, 184f, 11f, paint)
        paint.color = Color.rgb(39, 56, 44)
        paint.textSize = 26f
        canvas.drawText(title, 18f, 38f, paint)
        val out = ByteArrayOutputStream()
        check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out))
        bitmap.recycle()
        return out.toByteArray()
    }

    private inner class StoryApi(
        private val voiceEnabled: Boolean = false,
        private val largeNarrativeFixture: Boolean = false,
        private val bookStoryReadTrace: MutableList<String>? = null,
    ) : PhotoHouseApi {
        override val protectedNativeV2Enabled = true
        override val assistantEnabled get() = voiceEnabled
        var assistantSpeechRequests = 0
        var assistantTranscriptions = 0
        var storyCanEdit = true
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("account", "+12025550123", listOf(Membership("family", "approved", "owner", 1, null, 0, true)))
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun assistantCapabilities(token: Bearer, library: String) = AssistantCapabilities(true, true, true, false, 30)
        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray): AssistantTranscript {
            assistantTranscriptions++
            return AssistantTranscript("语音原稿", "zh")
        }
        override suspend fun assistantSpeech(token: Bearer, library: String, context: JsonObject?, language: String): ByteArray {
            assistantSpeechRequests++
            return ByteArray(0)
        }
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 8, 1, false, listOf(photo))
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, photo)
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset) =
            syntheticGardenPng("SYNTHETIC COVER", Color.rgb(231, 226, 204))
        override suspend fun detailPreview(token: Bearer, library: String, asset: Asset) =
            syntheticGardenPng("SYNTHETIC GARDEN", Color.rgb(219, 231, 217))
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 1, byteArrayOf(1))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf(1)
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int) = SavedMemoryStoryPage(library, page, 8, false, false, listOf(summary))
        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            bookStoryReadTrace?.add("child:$storyId:$revision")
            val storyIndex = narrativeStoryIds.indexOf(storyId)
            val largeStory = largeNarrativeFixture && storyIndex >= 0
            val title = if (largeStory) narrativeStoryTitle(storyIndex)
                else if (storyId == id) "花园的一天" else "野餐回忆"
            val items = if (largeStory) (0 until 6).map { chapterIndex ->
                val assetId = (chapterIndex + 1).toString()
                val familyEvidenceId = "family-00000000-0000-4000-8000-${assetId.padStart(12, '0')}"
                val captionEvidenceId = "caption-${chapterIndex + 1}"
                MemoryStoryAsset(
                    photo.copy(id = assetId, thumbnail_url = "/assets/$assetId/thumbnail?library=$library"),
                    listOf(
                        MemoryStoryEvidence(familyEvidenceId, "family", "家人回忆", "奶奶带我们走进花园。", 1),
                        MemoryStoryEvidence(captionEvidenceId, "ai", "", "画面中可以看到花朵。"),
                    ),
                )
            } else listOf(MemoryStoryAsset(photo, listOf(
                MemoryStoryEvidence("family-11111111-1111-1111-1111-111111111111", "family", "花园记忆", "<b>奶奶</b>带我们走进花园。", 1),
                MemoryStoryEvidence("caption-1", "ai", "", "画面中可以看到花朵。"),
            )))
            val chapters = if (largeStory) (0 until 6).map { chapterIndex ->
                val evidenceIds = items[chapterIndex].evidence.map { it.id }
                SavedMemoryStoryChapter(
                    "chapter-${chapterIndex + 1}",
                    narrativeChapterTitle(storyIndex, chapterIndex),
                    if (chapterIndex == 0) "奶奶带我们走进花园。"
                    else narrativeChapterText(storyIndex * 6 + chapterIndex),
                    listOf((chapterIndex + 1).toString()),
                    evidenceIds,
                )
            } else listOf(SavedMemoryStoryChapter("chapter-1", "早晨", "奶奶带我们走进花园。", listOf("1"),
                listOf("family-11111111-1111-1111-1111-111111111111", "caption-1")))
            return SavedMemoryStory(
                storyId, library, narrativeStoryRevision, 1, 10, storyCanEdit, "a".repeat(64), title,
                "everyday", "zh", items, chapters, emptyList(),
            )
        }
    }

    private inner class CommunityApi(
        private val bookStoryReadTrace: MutableList<String>? = null,
    ) : MemoryCommunityApi, MemoryBookEditionApi, MemoryBookEditionSourceApi {
        var contributionJson: String? = null
        var textSent = 0
        var lastTextRequest: JsonObject? = null
        var contributionText = "奶奶和我们一起种花。"
        var contributionState = "pending"
        var chatSent = 0
        var planReads = 0
        var planFailure: ApiFailure? = null
        val sentEditorialChoices = mutableListOf<Boolean>()
        var lastConversationTargetType: String? = null
        var lastConversationTargetId: String? = null
        var previewConversationLists = 0
        var conversationDirectoryReads = 0
        var conversationStarted = 0
        private val conversationIds = mutableListOf<String>()
        var sentChatText: String? = null
        private val conversationTurnTexts = mutableMapOf<String, String>()
        private val firstTurnTexts = mutableMapOf<String, String>()
        private fun previewForFirstTurn(text: String?): String {
            val collapsed = text.orEmpty().trim().replace(Regex("\\s+"), " ")
            val codePoints = collapsed.codePoints().limit(80).toArray()
            return String(codePoints, 0, codePoints.size)
        }
        var editionsEnabled = false
        var independentEditionFixture = false
        var editionDetailReads = 0
        val editionPages = mutableListOf<Int>()
        var failNextEditionRead = false
        private fun shelfId(index: Int) = "aaaaaaaa-aaaa-4aaa-8aaa-" + index.toString().padStart(12, '0')
        private fun shelfReceipt(index: Int): String = """{"version":1,"id":"${shelfId(index)}","book_id":"$bookId","book_revision":"$narrativeBookRevision","created_at":${1791014400L - index * 60},"state":"${if (editionInvalidated) "source_invalidated" else "current"}","mutation_id":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}"""
        var editionReads = 0
        var failNextEditionSave = false
        var editionInvalidated = false
        val editionBodies = mutableListOf<String>()
        private val editionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        private var editionSaved: JsonObject? = null
        override suspend fun editionCapabilities(token: Bearer, library: String, bookId: String) =
            """{"version":1,"enabled":$editionsEnabled,"can_save":${editionsEnabled && !independentEditionFixture}}""".toByteArray()
        private fun editionManuscript(): String {
            val chapters = (0 until narrativeStoryCount).flatMap { storyIndex ->
                (0 until narrativeChaptersPerStory).map { chapterIndex ->
                    val index = storyIndex * narrativeChaptersPerStory + chapterIndex
                    """{"id":"${narrativeStoryId(storyIndex)}-chapter-${chapterIndex + 1}","narration":${JsonPrimitive(narrativeChapterText(index))},"source_ids":["caption-1"]}"""
                }
            }.joinToString(",")
            return """{"version":1,"title":"家人的花园与野餐","chapters":[$chapters],"questions":["这几段回忆发生在哪一年？"],"needs_review":true}"""
        }
        override suspend fun editionProposal(token: Bearer, library: String, bookId: String, jobId: String): ByteArray {
            editionReads++
            val children = (0 until narrativeStoryCount).joinToString(",") {
                """{"id":"${narrativeStoryId(it)}","revision":"$narrativeStoryRevision"}"""
            }
            return """{"version":1,"book_id":"$bookId","revision":"$narrativeBookRevision","job_id":"$jobId","job_result_sha256":"${"a".repeat(64)}","source_fingerprint":"${"b".repeat(64)}","context_profile":"stories","children":[$children],"manuscript":${editionManuscript()},"needs_review":true}""".toByteArray()
        }
        private fun editionReceipt() = """{"version":1,"id":"$editionId","book_id":"$bookId","book_revision":"$narrativeBookRevision","created_at":100,"state":"${if (editionInvalidated) "source_invalidated" else "current"}","mutation_id":"${editionSaved!!.getValue("mutation_id").jsonPrimitive.content}"}"""
        override suspend fun saveEdition(token: Bearer, library: String, bookId: String, json: String): ByteArray {
            editionBodies += json
            editionSaved = Json.parseToJsonElement(json).jsonObject
            if (failNextEditionSave) { failNextEditionSave = false; throw ApiFailure(FailureKind.OFFLINE) }
            return editionReceipt().toByteArray()
        }
        override suspend fun editionPage(token: Bearer, library: String, bookId: String, page: Int): ByteArray {
            check(independentEditionFixture)
            editionPages += page
            val items = (if (page == 1) 0..7 else 8..8).joinToString(",") { "${shelfReceipt(it).dropLast(1)},\"manuscript\":null}" }
            return """{"version":1,"book_id":"$bookId","page":$page,"page_size":8,"has_more":${page == 1},"items":[$items]}""".toByteArray()
        }
        override suspend fun editionDetail(token: Bearer, library: String, bookId: String, editionId: String): ByteArray {
            editionDetailReads++
            if (failNextEditionRead) { failNextEditionRead = false; throw ApiFailure(FailureKind.OFFLINE) }
            if (independentEditionFixture) {
                val index = (0..8).first { shelfId(it) == editionId }
                return """${shelfReceipt(index).dropLast(1)},"manuscript":${if (editionInvalidated) "null" else editionManuscript()}}""".toByteArray()
            }
            return """${editionReceipt().dropLast(1)},"manuscript":${if (editionInvalidated) "null" else editionSaved!!.getValue("manuscript").toString()}}""".toByteArray()
        }
        val editionSourcePages = mutableListOf<Int>()
        val editionSourceReads = mutableListOf<String>()
        var editionSourceAudioReads = 0
        var failNextSourceRead = false
        var sourceInvalidated = false
        private val editionAudioSource = "contribution-$contributionId"
        private val editionSourceIds get() = listOf("caption-1",editionAudioSource,"family-$id",
            "editorial-book-$bookId","editorial-$id-chapter-1") + (2..13).map { "caption-$it" }
        private fun sourceMeta(source: String) = buildJsonObject {
            put("source_id",source)
            put("origin",when {
                source == editionAudioSource -> "contribution_audio"
                source.startsWith("family-") -> "asset_note"
                source.startsWith("editorial-book-") -> "book_introduction"
                source.startsWith("editorial-") -> "story_chapter"
                else -> "caption"
            })
            put("kind",when {
                source == editionAudioSource -> "transcript"
                source.startsWith("family-") -> "family"
                source.startsWith("editorial-") -> "editorial"
                else -> "ai"
            })
            put("asset_id",if (source.startsWith("caption-") || source.startsWith("family-")) JsonPrimitive("1") else JsonNull)
        }
        override suspend fun editionSources(token: Bearer, library: String, bookId: String, editionId: String, page: Int): ByteArray {
            editionSourcePages += page
            return buildJsonObject {
                put("version",1); put("book_id",bookId); put("edition_id",editionId); put("book_revision","$narrativeBookRevision")
                put("state",if (sourceInvalidated) "source_changed" else "current"); put("page",page); put("page_size",16)
                put("has_more",!sourceInvalidated && page * 16 < editionSourceIds.size)
                put("items",JsonArray(if (sourceInvalidated) emptyList() else editionSourceIds.drop((page-1)*16).take(16).map(::sourceMeta)))
            }.toString().toByteArray()
        }
        override suspend fun editionSource(token: Bearer, library: String, bookId: String, editionId: String, sourceId: String): ByteArray {
            editionSourceReads += sourceId
            if (failNextSourceRead) { failNextSourceRead=false; throw ApiFailure(FailureKind.OFFLINE) }
            return buildJsonObject {
                put("version",1); put("book_id",bookId); put("edition_id",editionId); put("book_revision","$narrativeBookRevision")
                put("source_id",sourceId); put("state",if (sourceInvalidated) "source_changed" else "current")
                put("source",if (sourceInvalidated) JsonNull else buildJsonObject {
                    sourceMeta(sourceId).forEach { (key,value) -> if (key != "source_id") put(key,value) }
                    put("story_id",if (sourceId == editionAudioSource || sourceId == "editorial-$id-chapter-1") JsonPrimitive(id) else JsonNull)
                    put("byline",if (sourceId == editionAudioSource) JsonPrimitive("奶奶") else JsonNull)
                    put("original_text",if (sourceId == editionAudioSource) JsonNull else JsonPrimitive("照片说明原文，与篇章整理文字分开展示。"))
                    put("original_truncated",false)
                    put("transcript",if (sourceId == editionAudioSource) JsonPrimitive("奶奶说：那天大家在花园里一起种花。请听原声核对这段 AI 转写。") else JsonNull)
                    put("transcript_truncated",false); put("prompt_excerpt","那天大家在花园里一起种花。")
                    put("audio_available",sourceId == editionAudioSource)
                })
            }.toString().toByteArray()
        }
        override suspend fun editionSourceAudio(token: Bearer, library: String, bookId: String, editionId: String, sourceId: String): ByteArray {
            check(sourceId == editionAudioSource); editionSourceAudioReads++
            return syntheticMemoryAudioWav(1000)
        }
        var narrativeSent = 0
        var lastNarrativeRequest: JsonObject? = null
        val narrativeEditorialChoices = mutableListOf<Boolean>()
        var largeNarrativeFixture = false
        var wholeOverCapacity = false
        var inspectOnlyNarrativeSection = false
        var audioSent = 0
        var audioRequest: JsonObject? = null
        var failNextAudio = false
        val audioMutations = mutableListOf<String>()
        private val narrativeStoryCount get() = if (largeNarrativeFixture) 4 else 2
        private val narrativeChaptersPerStory get() = if (largeNarrativeFixture) 6 else 1
        private fun proposalJson() = """{"version":1,"title":"花园草稿","chapters":[{"id":"chapter-1","narration":${JsonPrimitive(proposalNarration)},"source_ids":["family-11111111-1111-1111-1111-111111111111","caption-1","editorial-$id-chapter-1","contribution-$contributionId","unloaded-material"]}],"questions":["哪一年？"],"needs_review":true}"""
        private fun page(storyId: String, pageNumber: Int) = """{"version":1,"story_id":"$storyId","page":$pageNumber,"page_size":16,"has_more":${pageNumber == 1},"can_review":true,"can_delete":true,"items":[${contributionJson ?: ""}]}"""
        override suspend fun capabilities(token: Bearer, library: String) = """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":${!independentEditionFixture},"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
        private fun bookJson(): String {
            val stories = (0 until narrativeStoryCount).joinToString(",") { index ->
                """{"id":"${narrativeStoryId(index)}","title":${JsonPrimitive(narrativeStoryTitle(index))},"revision":"$narrativeStoryRevision","item_count":${narrativeChaptersPerStory},"cover_asset_id":"1"}"""
            }
            return """{"version":1,"type":"memoir","id":"$bookId","revision":"$narrativeBookRevision","can_edit":${!independentEditionFixture},"title":"家庭花园","introduction":"一家人的花园故事。","language":"zh","stories":[$stories]}"""
        }
        override suspend fun listBooks(token: Bearer, library: String, page: Int) =
            """{"version":1,"library_id":"$library","page":$page,"page_size":8,"has_more":false,"can_create":${!independentEditionFixture},"items":[${bookJson()}]}""".toByteArray()
        override suspend fun getBook(token: Bearer, library: String, bookId: String): ByteArray {
            bookStoryReadTrace?.add("parent:$bookId:$narrativeBookRevision")
            return bookJson().toByteArray()
        }
        override suspend fun bookPlan(token: Bearer, library: String, bookId: String, editorialContext: Boolean): ByteArray {
            planReads++
            planFailure?.let { throw it }
            val sections = (0 until narrativeStoryCount).map { index ->
                val chapters = (0 until narrativeChaptersPerStory).joinToString(",") { chapterIndex ->
                    """{"id":"chapter-${chapterIndex + 1}","title":${JsonPrimitive(narrativeChapterTitle(index, chapterIndex))},"item_count":1}"""
                }
                val sectionDraftable = !(inspectOnlyNarrativeSection && index == 1)
                """{"position":${index + 1},"id":"${narrativeStoryId(index)}","revision":"$narrativeStoryRevision","title":${JsonPrimitive(narrativeStoryTitle(index))},"item_count":$narrativeChaptersPerStory,"can_edit":true,"chapters":[$chapters],"state":"within_limits","can_draft":$sectionDraftable,"source_count":1,"source_kinds":{"editorial":1}}"""
            }
            val profile = if (editorialContext) ",\"context_profile\":\"memoir_editorial_v1\"" else ""
            val whole = if (wholeOverCapacity) {
                "\"state\":\"smaller_scope_required\",\"can_draft\":false,\"source_count\":null,\"source_kinds\":null" +
                    if (editorialContext) ",\"context_bytes\":null" else ""
            } else {
                "\"state\":\"within_limits\",\"can_draft\":true,\"source_count\":$narrativeStoryCount,\"source_kinds\":{\"editorial\":$narrativeStoryCount}" +
                    if (editorialContext) ",\"context_bytes\":3000" else ""
            }
            val chapterCount = narrativeStoryCount * narrativeChaptersPerStory
            val distinctItemCount = narrativeChaptersPerStory
            return """{"version":1,"target_type":"book","target_id":"$bookId","revision":"$narrativeBookRevision","can_edit":true,"kind":"saved_structure_plan","generated":false,"queued":false,"needs_review":true,"story_count":$narrativeStoryCount,"chapter_count":$chapterCount,"item_count":$chapterCount,"distinct_item_count":$distinctItemCount,"limits":{"chapters":24,"sources":96,"context_bytes":65536},"whole":{$whole},"sections":[${sections.joinToString(",")}]${profile}}""".toByteArray()
        }
        override suspend fun listContributions(token: Bearer, library: String, storyId: String, page: Int) = page(storyId, page).toByteArray()
        override suspend fun createTextContribution(token: Bearer, library: String, storyId: String, json: String): ByteArray {
            val request = Json.parseToJsonElement(json).jsonObject
            textSent++
            lastTextRequest = request
            val text = request.getValue("text").jsonPrimitive.content
            contributionText = text
            val lang = request.getValue("language").jsonPrimitive.content
            val byline = request.getValue("byline").jsonPrimitive.content
            val consent = request.getValue("consent").jsonPrimitive.content == "1"
            val chapter = request["chapter_id"]?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotEmpty() }
            val chapterJson = chapter?.let { JsonPrimitive(it).toString() } ?: "null"
            contributionJson = """{"id":"$contributionId","story_id":"$storyId","author_id":"$contributor","kind":"text","language":"$lang","byline":"$byline","sha256":"${"a".repeat(64)}","duration_ms":null,"chapter_id":$chapterJson,"base_story_revision":"3","state":"$contributionState","created_at":10,"text":${JsonPrimitive(text)},"processing_consent":$consent}"""
            return receipt(text, lang, byline, consent, chapter)
        }
        override suspend fun createAudioContribution(token: Bearer, library: String, storyId: String,
                                                     metadataBase64: String, wav: ByteArray): ByteArray {
            audioSent++
            audioRequest = Json.parseToJsonElement(String(java.util.Base64.getDecoder().decode(metadataBase64))).jsonObject
            audioMutations += audioRequest!!.getValue("mutation_id").jsonPrimitive.content
            if (failNextAudio) { failNextAudio = false; throw ApiFailure(FailureKind.OFFLINE) }
            val digest = MessageDigest.getInstance("SHA-256").digest(wav).joinToString("") { "%02x".format(it) }
            val chapter = audioRequest!!["chapter_id"]?.jsonPrimitive?.contentOrNull?.takeIf { it.isNotEmpty() }
            val chapterJson = chapter?.let { JsonPrimitive(it).toString() } ?: "null"
            return """{"version":1,"id":"$contributionId","story_id":"$storyId","author_id":"$contributor","kind":"audio","language":"${audioRequest!!.getValue("language").jsonPrimitive.content}","byline":"${audioRequest!!.getValue("byline").jsonPrimitive.content}","sha256":"$digest","duration_ms":1000,"chapter_id":$chapterJson,"base_story_revision":"3","state":"pending","created_at":10,"text":null,"processing_consent":${audioRequest!!.getValue("consent").jsonPrimitive.content == "1"},"can_review":true,"can_delete":true}""".toByteArray()
        }
        private fun receipt(text: String = "奶奶和我们一起种花。", lang: String = "zh", byline: String = "家人", consent: Boolean = true,
                            chapterId: String? = "chapter-1") =
            """{"version":1,"id":"$contributionId","story_id":"$id","author_id":"$contributor","kind":"text","language":"$lang","byline":"$byline","sha256":"${"a".repeat(64)}","duration_ms":null,"chapter_id":${chapterId?.let { JsonPrimitive(it).toString() } ?: "null"},"base_story_revision":"3","state":"$contributionState","created_at":10,"text":${JsonPrimitive(text)},"processing_consent":$consent,"can_review":true,"can_delete":true}""".toByteArray()
        override suspend fun getContribution(token: Bearer, library: String, storyId: String, contributionId: String) =
            receipt(text = contributionText).decodeToString().dropLast(1).plus(",\"derivation\":null}").toByteArray()
        override suspend fun reviewContribution(token: Bearer, library: String, storyId: String, contributionId: String, json: String): ByteArray {
            contributionState = Json.parseToJsonElement(json).jsonObject.getValue("state").jsonPrimitive.content
            return receipt()
        }
        override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
            conversationDirectoryReads++
            return """{"version":1,"items":[${conversationIds.mapIndexed { index, id -> """{"id":"$id","created_at":${1_780_000_000L - index},"expires_at":4102444800}""" }.joinToString(",")}] }""".toByteArray()
        }
        override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
            conversationDirectoryReads++
            previewConversationLists++
            return """{"version":1,"items":[${conversationIds.mapIndexed { index, id ->
                val preview = JsonPrimitive(previewForFirstTurn(firstTurnTexts[id])).toString()
                """{"id":"$id","created_at":${1_780_000_000L - index},"expires_at":4102444800,"first_message_preview":$preview}"""
            }.joinToString(",")}] }""".toByteArray()
        }
        override suspend fun startConversation(token: Bearer, library: String, json: String): ByteArray {
            conversationStarted++
            val request = Json.parseToJsonElement(json).jsonObject
            val targetType = request.getValue("target_type").jsonPrimitive.content
            val targetId = request.getValue("target_id").jsonPrimitive.content
            lastConversationTargetType = targetType
            lastConversationTargetId = targetId
            val conversationId = request.getValue("id").jsonPrimitive.content
            conversationIds.remove(conversationId)
            conversationIds.add(0, conversationId)
            return """{"version":1,"id":"$conversationId","target_type":"$targetType","target_id":"$targetId","expires_at":999}""".toByteArray()
        }
        override suspend fun conversationTurns(token: Bearer, library: String, conversationId: String, page: Int): ByteArray {
            val turn = conversationTurnTexts[conversationId]?.let { text ->
                val refs = if (lastConversationTargetType == "book") listOf(
                    "family-11111111-1111-1111-1111-111111111111", "caption-1", "editorial-$id-chapter-1", "editorial-book-$bookId", "contribution-$contributionId", "unloaded-material")
                else listOf("family-11111111-1111-1111-1111-111111111111", "caption-1", "editorial-$id-chapter-1", "contribution-$contributionId", "unloaded-material")
                """{"id":"77777777-7777-7777-7777-777777777777","sequence":1,"input_text":${JsonPrimitive(text)},"reply_text":"第一行\n第二行","reply_kind":"answer","job_id":"$jobId","state":"ready","reply_source_ids":${JsonArray(refs.map(::JsonPrimitive))},"reply_questions":["那天后来发生了什么？","花园里还种过什么？"]}"""
            }
            return """{"version":1,"id":"$conversationId","expires_at":999,"page":$page,"has_more":${page == 1},"items":[${turn ?: ""}]}""".toByteArray()
        }
        override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String): ByteArray {
            chatSent++
            val request = Json.parseToJsonElement(json).jsonObject
            sentChatText = request.getValue("text").jsonPrimitive.content
            val revision = request.getValue("revision").jsonPrimitive.content
            firstTurnTexts.putIfAbsent(conversationId, sentChatText.orEmpty())
            conversationTurnTexts[conversationId] = sentChatText.orEmpty()
            val proposal = if (sentChatText == "请给出分段建议") proposalJson() else "null"
            val kind = if (proposal == "null") "answer" else "proposal"
            val result = """{"version":1,"kind":"$kind","reply":"第一行\n第二行","source_ids":[],"questions":[],"proposal":$proposal}"""
            return """{"version":1,"id":"$jobId","kind":"chat","state":"ready","created_at":10,"updated_at":10,"expires_at":999,"error_code":null,"result":$result,"needs_review":true,"base_revision":"$revision"}""".toByteArray()
        }
        override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String, editorialContext: Boolean): ByteArray {
            sentEditorialChoices += editorialContext
            return sendTurn(token, library, conversationId, json)
        }
        override suspend fun queueNarrative(token: Bearer, library: String, json: String): ByteArray {
            narrativeSent++
            lastNarrativeRequest = Json.parseToJsonElement(json).jsonObject
            val isBook = lastNarrativeRequest!!.getValue("target_type").jsonPrimitive.content == "book"
            val result = if (isBook) {
                val chapters = (0 until narrativeStoryCount).flatMap { storyIndex ->
                    (0 until narrativeChaptersPerStory).map { chapterIndex ->
                        Triple(storyIndex, chapterIndex, storyIndex * narrativeChaptersPerStory + chapterIndex)
                    }
                }.joinToString(",") { (storyIndex, chapterIndex, index) ->
                    val sources = if (editionsEnabled) "[\"caption-1\"]" else if (index == 0) "[\"family-11111111-1111-1111-1111-111111111111\"]" else "[]"
                    """{"id":"${narrativeStoryId(storyIndex)}-chapter-${chapterIndex + 1}","narration":${JsonPrimitive(narrativeChapterText(index))},"source_ids":$sources}"""
                }
                """{"version":1,"title":"家人的花园与野餐","chapters":[$chapters],"questions":["这几段回忆发生在哪一年？"],"needs_review":true}"""
            } else proposalJson()
            val revision = if (isBook) narrativeBookRevision.toString() else narrativeStoryRevision.toString()
            return """{"version":1,"id":"$jobId","kind":"narrative","state":"ready","created_at":10,"updated_at":10,"expires_at":999,"error_code":null,"result":$result,"needs_review":true,"base_revision":"$revision"}""".toByteArray()
        }
        override suspend fun queueNarrative(token: Bearer, library: String, json: String, editorialContext: Boolean): ByteArray {
            narrativeEditorialChoices += editorialContext
            return queueNarrative(token, library, json)
        }

    }

    @After fun close() { scope.cancel() }

    private class SyntheticCapture(private val autoComplete: Boolean) : MemoryContributionCapture {
        private val stopped = CountDownLatch(1)
        @Volatile private var discarded = false
        override val recordedMillis = if (autoComplete) 30_000 else 1000
        override val wasDiscarded get() = discarded
        override fun record(): ByteArray? {
            if (!autoComplete && !stopped.await(5, TimeUnit.SECONDS) || discarded) return null
            return syntheticMemoryAudioWav(if (autoComplete) 30_000 else 1000)
        }
        override fun stop() { stopped.countDown() }
        override fun discard() { discarded = true; stopped.countDown() }
    }

    private class SyntheticCaptureFactory : MemoryContributionCaptureFactory {
        private var created = 0
        override fun begin(): MemoryContributionCapture = SyntheticCapture(autoComplete = created++ == 0)
    }

    private data class ReplyUtterance(val id: String, val text: String, val done: (String) -> Unit)
    private class ReplySpeechAdapter : ChapterSpeechAdapter {
        val utterances = mutableListOf<ReplyUtterance>()
        var stopped = 0
        var shutdowns = 0
        override fun initialize(done: (Boolean, Set<Voice>) -> Unit) = done(true, setOf(
            Voice("synthetic-offline-zh", Locale.SIMPLIFIED_CHINESE, Voice.QUALITY_NORMAL, Voice.LATENCY_NORMAL, false, emptySet()),
        ))
        override fun setVoice(voice: Voice) = true
        override fun speak(text: String, id: String, done: (String) -> Unit, failed: (String) -> Unit) {
            utterances += ReplyUtterance(id, text, done)
        }
        override fun stop() { stopped++ }
        override fun shutdown() { shutdowns++ }
    }
    private class ReplySpeechFactory : ChapterSpeechAdapterFactory {
        val engines = mutableListOf<ReplySpeechAdapter>()
        override fun create(context: android.content.Context): ChapterSpeechAdapter =
            ReplySpeechAdapter().also(engines::add)
    }
    private class SyntheticAudioFocusFactory : ChapterAudioFocusFactory {
        override fun create(context: android.content.Context) = object : ChapterAudioFocus {
            override fun request(onLost: () -> Unit) = true
            override fun abandon() = Unit
        }
    }

    private class DelayedCapture : MemoryContributionCapture {
        private val release = CountDownLatch(1)
        private val recordingStarted = CountDownLatch(1)
        @Volatile var returned: ByteArray? = null
        override val recordedMillis = 1000
        override val wasDiscarded = false
        override fun record(): ByteArray? {
            recordingStarted.countDown()
            val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(8)
            var ready = false
            var interrupted = false
            while (!ready) {
                val remaining = deadline - System.nanoTime()
                if (remaining <= 0) break
                try { ready = release.await(remaining, TimeUnit.NANOSECONDS) }
                catch (_: InterruptedException) { interrupted = true }
            }
            if (interrupted) Thread.currentThread().interrupt()
            if (!ready) return null
            return syntheticMemoryAudioWav(1000).also { returned = it }
        }
        override fun stop() = Unit
        override fun discard() = Unit // Simulates a late native result that ignores discard.
        fun awaitRecordingStarted() = recordingStarted.await(5, TimeUnit.SECONDS)
        fun completeLate() { release.countDown() }
    }

    private class DelayedCaptureFactory : MemoryContributionCaptureFactory {
        val captures = mutableListOf<DelayedCapture>()
        override fun begin(): MemoryContributionCapture = DelayedCapture().also(captures::add)
    }

    private class SyntheticLifecycleOwner : LifecycleOwner {
        override val lifecycle = LifecycleRegistry(this)
    }

    // Compose assertions can pass beneath a system ANR dialog. Such a display is not visual evidence.
    private fun assertNoSystemErrorOverlay() {
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        val info = automation.serviceInfo
        val originalFlags = info.flags
        info.flags = originalFlags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
            android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
        automation.serviceInfo = info
        try {
            // Updating service flags can briefly disconnect the accessibility snapshot.
            // Wait for a real window; never accept an empty snapshot as proof of no overlay.
            val deadline = android.os.SystemClock.uptimeMillis() + 2_000
            var roots = automation.windows.mapNotNull { it.root } + listOfNotNull(automation.rootInActiveWindow)
            while (roots.isEmpty() && android.os.SystemClock.uptimeMillis() < deadline) {
                android.os.SystemClock.sleep(50)
                roots = automation.windows.mapNotNull { it.root } + listOfNotNull(automation.rootInActiveWindow)
            }
            check(roots.isNotEmpty()) { "No accessible window is available for fixture display review" }
            check(roots.none { root ->
                root.findAccessibilityNodeInfosByViewId("android:id/aerr_close").isNotEmpty() ||
                    root.findAccessibilityNodeInfosByViewId("android:id/aerr_wait").isNotEmpty()
            }) { "An Android system error dialog obscures the fixture display" }
        } finally {
            info.flags = originalFlags
            automation.serviceInfo = info
        }
    }
    private fun capture(name: String) {
        assertNoSystemErrorOverlay()
        val bitmap = rule.onNodeWithTag("saved-memory-stories").captureToImage().asAndroidBitmap()
        saveScreenshot(bitmap, name)
    }
    private fun captureDialog(name: String) {
        assertNoSystemErrorOverlay()
        val matcher = isDialog() and hasAnyDescendant(hasText("打开这张照片？"))
        val bitmap = rule.onNode(matcher, useUnmergedTree = true).captureToImage().asAndroidBitmap()
        saveScreenshot(bitmap, name)
    }
    private fun saveScreenshot(bitmap: Bitmap, name: String) {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "memory-community-$name-$screenshotRunId.png")
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/PhotoHouseMemoryUi")
        }
        val uri = checkNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        context.contentResolver.openOutputStream(uri).use { out -> checkNotNull(out); check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)) }
        bitmap.recycle()
    }
    private fun captureBooks(name: String) {
        assertNoSystemErrorOverlay()
        val bitmap = rule.onNodeWithTag("memory-books").captureToImage().asAndroidBitmap()
        saveScreenshot(bitmap, name)
    }
    private fun captureSourceFrame(name: String) {
        assertNoSystemErrorOverlay()
        rule.waitForIdle()
        // Capture the Compose frame rather than a potentially older system compositor frame.
        saveScreenshot(rule.onNodeWithTag("memory-books").captureToImage().asAndroidBitmap(), name)
    }
    private fun captureDisplay(name: String) {
        assertNoSystemErrorOverlay()
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        saveScreenshot(bitmap, name)
    }
    @Test fun savedStoryCommunitySubmissionChatAndProposalStayReviewOnly() {
        val community = CommunityApi()
        val storyApi = StoryApi()
        val replySpeech = ReplySpeechFactory()
        val store = ConnectedStore(storyApi, scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, previewFontScale.floatValue)) {
                CompositionLocalProvider(LocalChapterSpeechAdapterFactory provides replySpeech,
                    LocalChapterAudioFocusFactory provides SyntheticAudioFocusFactory()) {
                    ConnectedApp(store, initialLanguage = "zh")
                }
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.capabilities != null }
        capture("story-reader")
        rule.onNodeWithTag("saved-memory-reader-scroll-divider").assertIsDisplayed()

        rule.onNodeWithText("共同讲述").performClick()
        val longChinese = "奶奶和我们一起种花，后来下起了细雨，我们把花盆搬到屋檐下继续聊天。".repeat(8)
        rule.onNodeWithTag("memory-contribution-text").performScrollTo().performTextInput(longChinese)
        capture("contribution-draft-before-submit")
        rule.onNodeWithTag("memory-contribution-consent").performScrollTo().performClick()
        rule.onNodeWithTag("memory-contribution-submit").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.contributions?.items?.isNotEmpty() == true }
        rule.onNodeWithTag("memory-original-text").assertTextEquals(longChinese)
        rule.onNodeWithTag("memory-contribution-$contributionId").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.selectedContribution != null }
        rule.onNodeWithTag("memory-original-text").performScrollTo()
        capture("contribution-detail-long-chinese")
        rule.onNodeWithTag("memory-contribution-accept").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.selectedContribution?.receipt?.contribution?.state == "accepted" }
        rule.onNodeWithTag("memory-contributions-next").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.contributions?.page == 2 }
        rule.onNodeWithTag("memory-contributions-previous").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.contributions?.page == 1 }
        rule.onNodeWithTag("memory-contribution-consent").performScrollTo().performClick()
        rule.runOnIdle {
            val community = store.state.value.savedMemoryStories?.community!!
            assertFalse(community.contributionConsent)
            assertFalse(community.audioConsent)
        }

        rule.onNodeWithTag("memory-community-tab-1").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.tab == 1 }
        rule.runOnIdle { previewFontScale.floatValue = 1.5f }
        rule.waitForIdle()
        rule.onNodeWithTag("saved-memory-narration-toggle").assertIsDisplayed()
        capture("saved-reader-scroll-clip-font150")
        rule.runOnIdle {
            assertTrue(store.state.value.savedMemoryStories?.community?.capabilities?.generationEnabled == true)
            assertNull(store.state.value.savedMemoryStories?.community?.conversationId)
        }
        rule.onNodeWithTag("memory-chat-start").performScrollTo().performClick()
        rule.onNodeWithTag("saved-memory-narration-toggle").assertIsDisplayed()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.conversationId != null }
        rule.runOnIdle {
            assertEquals("new conversation has no first-message preview before a user turn", "",
                store.state.value.savedMemoryStories?.community?.conversations?.items?.first()?.firstMessagePreview)
        }
        rule.onNodeWithText("Synthetic first user message", substring = true).assertDoesNotExist()
        rule.onNodeWithTag("memory-chat-page").performScrollTo().assertTextEquals("最新消息")
        capture("story-chat-latest-font150")
        rule.onNodeWithTag("memory-chat-next").performScrollTo().assertTextEquals("更早的消息").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.turns?.page == 2 }
        rule.onNodeWithTag("memory-chat-page").performScrollTo().assertTextEquals("更早的消息 · 第 2 页")
        capture("story-chat-older-font150")
        rule.onNodeWithTag("memory-chat-previous").performScrollTo().assertTextEquals("较新的消息").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.turns?.page == 1 }
        capture("story-chat-latest-return-font150")
        rule.runOnIdle { assertEquals("history navigation must not submit a chat turn", 0, community.chatSent) }
        val firstStoryPreview80 = "花".repeat(80)
        rule.onNodeWithTag("memory-chat-input").performScrollTo().performTextInput(firstStoryPreview80)
        capture("story-chat-draft-before-send")
        rule.runOnIdle { assertEquals(0, community.chatSent) }
        rule.onNodeWithTag("memory-chat-send").performScrollTo().performClick()
        rule.waitUntil(5000) { community.chatSent == 1 }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.job?.state == "ready" }
        rule.onNodeWithTag("memory-chat-reply").assertTextEquals("第一行\n第二行")
        val bubbleTurnId = "77777777-7777-7777-7777-777777777777"
        rule.onNodeWithTag("memory-chat-reply").assert(hasAnyAncestor(hasTestTag("memory-chat-assistant-bubble-$bubbleTurnId")))
        rule.onNodeWithTag("memory-chat-keep-turn-$bubbleTurnId").assert(hasAnyAncestor(hasTestTag("memory-chat-user-bubble-$bubbleTurnId")))
        rule.onNodeWithTag("memory-chat-user-bubble-$bubbleTurnId").performScrollTo()
        capture("story-chat-user-bubble-font150")
        rule.onNodeWithTag("memory-chat-assistant-bubble-$bubbleTurnId").performScrollTo()
        capture("story-chat-message-bubbles-font150")
        rule.onNodeWithTag("memory-chat-followup-1-question-0").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-chat-followup-1-sources-toggle").performScrollTo().performClick()
        rule.onNodeWithText("家人提供的文字", substring = true).assertExists()
        rule.onNodeWithText("家人提供的文字", substring = true).performScrollTo()
        rule.onNodeWithText("家人提供的回忆", substring = true).assertExists()
        rule.onNodeWithText("AI 观察 · 需核实", substring = true).assertExists()
        rule.onNodeWithText("故事整理文字", substring = true).assertExists()
        rule.onNodeWithText("来源尚未加载", substring = true).assertExists()
        rule.onNodeWithText(contributionId).assertDoesNotExist()
        capture("story-chat-followups-font150")
        val oversizedChatDraft = "字".repeat(1400)
        rule.onNodeWithTag("memory-chat-input").performScrollTo().performTextInput(oversizedChatDraft)
        rule.onNodeWithTag("memory-chat-draft-limit", useUnmergedTree = true).performScrollTo().assertExists()
        rule.onNodeWithTag("memory-chat-input").assert(SemanticsMatcher.keyIsDefined(SemanticsProperties.Error))
        rule.onNodeWithTag("memory-chat-draft-limit", useUnmergedTree = true).assert(SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite))
        rule.onNodeWithTag("memory-chat-input").assertTextContains(oversizedChatDraft)
        rule.onNodeWithTag("memory-chat-send").assertIsNotEnabled()
        rule.runOnIdle { assertEquals("over-limit draft input is not sent", 1, community.chatSent) }
        rule.onNodeWithTag("memory-chat-input").performScrollTo().performTextClearance()
        rule.onNodeWithTag("memory-chat-draft-limit", useUnmergedTree = true).assertDoesNotExist()
        rule.onNodeWithTag("memory-chat-input").assert(SemanticsMatcher.keyNotDefined(SemanticsProperties.Error))
        val storyFollowup = "那天后来发生了什么？"
        rule.onNodeWithTag("memory-chat-followup-1-question-0").performScrollTo().performClick()
        rule.onNodeWithTag("memory-chat-input").performScrollTo().assertTextContains(storyFollowup)
        rule.runOnIdle { assertEquals("choosing a story follow-up only fills the composer", 1, community.chatSent) }
        rule.onNodeWithTag("memory-chat-send").performScrollTo().performClick()
        rule.waitUntil(5000) { community.chatSent == 2 && community.sentChatText == storyFollowup }
        rule.onNodeWithTag("memory-chat-user-speaker-77777777-7777-7777-7777-777777777777").assertTextEquals("你")
        rule.onNodeWithTag("memory-chat-assistant-speaker-77777777-7777-7777-7777-777777777777").assertTextEquals("故事助手")
        assertTrue("reply playback must not autoplay", replySpeech.engines.isEmpty())
        val replySpeechTag = "memory-chat-reply-reading-77777777-7777-7777-7777-777777777777-toggle"
        rule.onNodeWithTag(replySpeechTag).performScrollTo().performClick()
        rule.waitUntil(5000) { replySpeech.engines.singleOrNull()?.utterances?.isNotEmpty() == true }
        val firstReplyEngine = replySpeech.engines.single()
        val exactReplyUtterance = firstReplyEngine.utterances.single()
        assertEquals("第一行\n第二行", exactReplyUtterance.text)
        assertEquals(0, storyApi.assistantSpeechRequests)
        rule.onNodeWithTag(replySpeechTag).assertTextEquals("暂停回复朗读")
        rule.onNodeWithTag(replySpeechTag.removeSuffix("-toggle") + "-stop").assertTextEquals("停止朗读").performClick()
        Thread { exactReplyUtterance.done(exactReplyUtterance.id) }.apply { start(); join() }
        rule.waitForIdle()
        assertEquals(1, firstReplyEngine.utterances.size)
        rule.onNodeWithTag(replySpeechTag).assertTextEquals("朗读回复")
        rule.onNodeWithTag(replySpeechTag).performClick()
        rule.waitUntil(5000) { replySpeech.engines.size == 2 && replySpeech.engines.last().utterances.isNotEmpty() }
        val rowDisposalUtterance = replySpeech.engines.last().utterances.single()
        rule.onNodeWithTag("memory-chat-reply").performScrollTo()
        capture("story-chat-ready-reply")
        val contributionPostsBeforeKeep = community.textSent
        rule.onNodeWithTag("memory-chat-keep-turn-77777777-7777-7777-7777-777777777777").performScrollTo().performClick()
        rule.waitForIdle()
        assertTrue("hiding the chat tab must stop its local reader", replySpeech.engines.last().stopped > 0)
        Thread { rowDisposalUtterance.done(rowDisposalUtterance.id) }.apply { start(); join() }
        rule.waitForIdle()
        rule.runOnIdle {
            val imported = store.state.value.savedMemoryStories!!.community!!
            assertEquals("tab=${imported.tab}, busy=${imported.busy}, contributionDraft=${imported.contributionDraft}, consent=${imported.contributionConsent}, audioConsent=${imported.audioConsent}, audioBusy=${imported.contributionAudioBusy}, pendingText=${imported.pendingText}, pendingAudio=${imported.pendingAudio}, pendingTurn=${imported.pendingTurn}, pendingConversation=${imported.pendingConversation}, chatDraft=${imported.chatDraft}, job=${imported.job?.state}, dictation=${imported.dictation?.state?.value}",
                0, imported.tab)
            assertEquals(community.sentChatText, imported.contributionDraft)
            assertFalse(imported.contributionConsent)
            assertTrue(imported.chatTurnContributionSeeded)
            assertTrue(imported.contributionWholeStory)
            assertEquals(contributionPostsBeforeKeep, community.textSent)
        }
        rule.onNodeWithTag("memory-contribution-text").assertIsFocused()
        rule.onNodeWithTag("memory-contribution-chat-scope").assertExists()
        rule.onNodeWithTag("memory-contribution-scope-whole-story").assertIsSelected().assertIsNotEnabled()
        rule.onNodeWithTag("memory-contribution-scope-current-chapter").assertIsNotSelected().assertIsNotEnabled()
        rule.onNodeWithTag("memory-contribution-consent").performScrollTo().performClick()
        rule.onNodeWithTag("memory-contribution-submit").performScrollTo().performClick()
        rule.waitUntil(5000) { community.textSent == contributionPostsBeforeKeep + 1 }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.pendingText == null }
        rule.runOnIdle {
            val request = community.lastTextRequest!!
            assertEquals(community.sentChatText, request.getValue("text").jsonPrimitive.content)
            assertEquals("", request.getValue("byline").jsonPrimitive.content)
            assertEquals("", request.getValue("chapter_id").jsonPrimitive.content)
            assertEquals("1", request.getValue("consent").jsonPrimitive.content)
        }
        rule.onNodeWithTag("memory-community-tab-1").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.tab == 1 }
        rule.waitForIdle()
        rule.runOnIdle { previewFontScale.floatValue = 1.5f }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-chat-reply").performScrollTo()
        rule.onNodeWithTag("memory-chat-reply").assertTextEquals("第一行\n第二行")
        capture("story-chat-ready-reply-font150")
        rule.onNodeWithTag(replySpeechTag).performScrollTo().assertIsDisplayed()
        capture("story-chat-reply-reading-font150")
        rule.runOnIdle { previewFontScale.floatValue = 1f }
        rule.waitForIdle()

        val oldThreadId = store.state.value.savedMemoryStories!!.community!!.conversationId!!
        val firstThreadDraft = "留给第一段对话的草稿"
        rule.onNodeWithTag("memory-chat-input").performScrollTo().performTextInput(firstThreadDraft)
        rule.onNodeWithTag(replySpeechTag).performScrollTo().performClick()
        rule.waitUntil(5000) { replySpeech.engines.size == 3 && replySpeech.engines.last().utterances.isNotEmpty() }
        val oldThreadEngine = replySpeech.engines.last()
        val oldThreadUtterance = oldThreadEngine.utterances.single()
        rule.onNodeWithTag("memory-chat-new").performScrollTo().performClick()
        rule.waitUntil(5000) {
            val chat = store.state.value.savedMemoryStories?.community
            chat?.conversationId != null && chat.conversationId != oldThreadId && !chat.busy
        }
        val secondStoryThreadId = store.state.value.savedMemoryStories!!.community!!.conversationId!!
        rule.onNodeWithTag("memory-chat-reply").assertDoesNotExist()
        assertTrue("switching the thread must stop its reply reader", oldThreadEngine.stopped > 0)
        rule.onNodeWithTag("memory-chat-input").performScrollTo().performTextInput("请给出分段建议")
        val chatSentBeforeNewThreadMessage = community.chatSent
        rule.onNodeWithTag("memory-chat-send").performScrollTo().performClick()
        rule.waitUntil(5000) { community.chatSent == chatSentBeforeNewThreadMessage + 1 && store.state.value.savedMemoryStories?.community?.job?.state == "ready" }
        rule.onNodeWithTag("memory-chat-reply").assertTextEquals("第一行\n第二行")
        val chatProposalPrefix = "memory-chat-proposal-$jobId"
        val storyBeforeChatProposalReview = store.state.value.savedMemoryStories!!.detail!!
        val chatJobBeforeReview = store.state.value.savedMemoryStories!!.community!!.job!!
        rule.onNodeWithTag("$chatProposalPrefix-review-badge").assertTextEquals("AI 建议 · 待核对")
        rule.onNodeWithTag("$chatProposalPrefix-chapter-title-0").assertTextEquals("早晨")
        rule.onNodeWithTag("$chatProposalPrefix-narration-0").assertTextEquals(proposalNarration)
        rule.onNodeWithTag("$chatProposalPrefix-original-toggle-0").assertTextEquals("查看当前阅读的章节")
        rule.onNodeWithTag("$chatProposalPrefix-original-text-0").assertDoesNotExist()
        rule.onNodeWithTag("$chatProposalPrefix-sources-toggle-0").performScrollTo().performClick()
        rule.onNodeWithText("家人提供的回忆", substring = true).assertExists()
        rule.onNodeWithText("AI 观察 · 需核实", substring = true).assertExists()
        rule.onNodeWithText("故事整理文字", substring = true).assertExists()
        rule.onNodeWithText("家人提供的文字", substring = true).assertExists()
        rule.onNodeWithText("来源尚未加载", substring = true).assertExists()
        rule.onNodeWithText("family-11111111-1111-1111-1111-111111111111", substring = true).assertDoesNotExist()
        rule.onNodeWithText(contributionId, substring = true).assertDoesNotExist()
        rule.onNodeWithTag("$chatProposalPrefix-original-toggle-0").performScrollTo().performClick()
        rule.onNodeWithText("当前阅读的章节 · 仅供对照").assertExists()
        rule.onNodeWithTag("$chatProposalPrefix-original-text-0").assertTextEquals("奶奶带我们走进花园。")
        rule.runOnIdle {
            assertSame("reading a nested proposal must not replace the saved story", storyBeforeChatProposalReview,
                store.state.value.savedMemoryStories?.detail)
            assertSame("review controls do not mutate the ready chat job", chatJobBeforeReview,
                store.state.value.savedMemoryStories?.community?.job)
            assertEquals(chatSentBeforeNewThreadMessage + 1, community.chatSent)
            assertEquals(0, community.narrativeSent)
        }
        rule.runOnIdle { previewFontScale.floatValue = 1.5f }
        rule.waitForIdle()
        rule.onNodeWithTag("$chatProposalPrefix-narration-0").performScrollTo()
        val pinnedReadAloudBounds = rule.onNodeWithTag("saved-memory-narration-toggle").fetchSemanticsNode().boundsInRoot
        val readerViewportBounds = rule.onNodeWithTag("saved-memory-reader-scroll").fetchSemanticsNode().boundsInRoot
        assertTrue("reader viewport $readerViewportBounds must begin below pinned chapter control $pinnedReadAloudBounds",
            readerViewportBounds.top >= pinnedReadAloudBounds.bottom)
        rule.onNodeWithTag("saved-memory-narration-toggle").assertIsDisplayed()
        capture("story-chat-proposal-review-font150")
        rule.runOnIdle { previewFontScale.floatValue = 1f }
        rule.waitForIdle()
        assertEquals("thread replies must not autoplay", 3, replySpeech.engines.size)
        rule.onNodeWithTag(replySpeechTag).performScrollTo().performClick()
        rule.waitUntil(5000) { replySpeech.engines.size == 4 && replySpeech.engines.last().utterances.isNotEmpty() }

        val newThreadEngine = replySpeech.engines.last()
        Thread { oldThreadUtterance.done(oldThreadUtterance.id) }.apply { start(); join() }
        rule.waitForIdle()
        assertEquals(1, newThreadEngine.utterances.size)
        rule.onNodeWithTag(replySpeechTag).assertTextEquals("暂停回复朗读")
        rule.onNodeWithTag(replySpeechTag.removeSuffix("-toggle") + "-stop").assertTextEquals("停止朗读").performClick()
        rule.waitForIdle()
        assertEquals(0, storyApi.assistantSpeechRequests)

        // A normal server list refresh happens when a third empty thread is created.
        // It exposes only the retained first user turn for the two existing threads.
        val secondThreadDraft = "留给第二段对话的草稿"
        rule.onNodeWithTag("memory-chat-input").performScrollTo().performTextInput(secondThreadDraft)
        rule.onNodeWithTag("memory-chat-new").performScrollTo().performClick()
        rule.waitUntil(5000) {
            val chat = store.state.value.savedMemoryStories?.community
            chat?.conversationId != null && chat.conversationId != secondStoryThreadId && !chat.busy &&
                chat.conversations?.items?.size == 3
        }
        val thirdStoryThreadId = store.state.value.savedMemoryStories!!.community!!.conversationId!!
        val previewRows = store.state.value.savedMemoryStories!!.community!!.conversations!!.items
        assertEquals(firstStoryPreview80, previewRows.first { it.id == oldThreadId }.firstMessagePreview)
        assertEquals("请给出分段建议", previewRows.first { it.id == secondStoryThreadId }.firstMessagePreview)
        assertEquals("", previewRows.first { it.id == thirdStoryThreadId }.firstMessagePreview)
        val thirdThreadDraft = "留给新对话的草稿"
        rule.onNodeWithTag("memory-chat-input").performScrollTo().performTextInput(thirdThreadDraft)
        rule.runOnIdle { previewFontScale.floatValue = 1.5f }
        rule.waitForIdle()
        val storyThreadRows = store.state.value.savedMemoryStories!!.community!!.conversations!!.items
        val firstStoryThreadIndex = storyThreadRows.indexOfFirst { it.id == oldThreadId }
        val secondStoryThreadIndex = storyThreadRows.indexOfFirst { it.id == secondStoryThreadId }
        assertTrue(firstStoryThreadIndex >= 0 && secondStoryThreadIndex >= 0)
        rule.onNodeWithTag("memory-chat-thread-$firstStoryThreadIndex").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.conversationId == oldThreadId }
        rule.runOnIdle {
            assertEquals("switching back restores the first thread's unsent draft", firstThreadDraft,
                store.state.value.savedMemoryStories?.community?.chatDraft)
        }
        rule.onNodeWithText(firstStoryPreview80.take(16), substring = true).assertExists()
        assertTrue("second conversation preview is visible in its thread chip",
            rule.onAllNodesWithText("请给出分段建议", substring = true).fetchSemanticsNodes().isNotEmpty())
        capture("story-thread-first-preview-font150")
        rule.onNodeWithTag("memory-chat-thread-$secondStoryThreadIndex").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.conversationId == secondStoryThreadId }
        rule.runOnIdle {
            assertEquals("switching back restores the second thread's unsent draft", secondThreadDraft,
                store.state.value.savedMemoryStories?.community?.chatDraft)
        }
        rule.onNodeWithText(firstStoryPreview80.take(16), substring = true).assertExists()
        assertTrue("second conversation preview is visible in its thread chip",
            rule.onAllNodesWithText("请给出分段建议", substring = true).fetchSemanticsNodes().isNotEmpty())
        capture("story-thread-second-preview-font150")
        rule.onNodeWithTag("memory-chat-thread-0").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.conversationId == thirdStoryThreadId }
        rule.runOnIdle {
            assertEquals("third thread keeps its own unsent draft", thirdThreadDraft,
                store.state.value.savedMemoryStories?.community?.chatDraft)
        }
        rule.runOnIdle { previewFontScale.floatValue = 1f }
        rule.waitForIdle()

        rule.onNodeWithTag("memory-community-tab-2").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.tab == 2 }
        assertTrue("leaving story chat must stop local reply reading", newThreadEngine.stopped > 0)
        capture("narrative-before-request")
        rule.onNodeWithTag("memory-narrative-request").performScrollTo().assertIsDisplayed().performClick()
        rule.waitUntil(5000) { community.narrativeSent == 1 }
        rule.waitUntil(5000) {
            val live = store.state.value
            val state = live.savedMemoryStories?.community
            state?.narrativeJob != null || state?.failure != null || state == null || live.covered
        }
        rule.runOnIdle {
            val live = store.state.value
            assertNotNull("community state lost or stuck (covered=${live.covered}, detail=${live.savedMemoryStories?.detail?.id}, community=${live.savedMemoryStories?.community})",
                live.savedMemoryStories?.community?.narrativeJob)
        }
        rule.onNodeWithTag("memory-narrative-state").assertExists()
        rule.onNodeWithTag("memory-narrative-title").assertTextEquals("花园草稿")
        rule.onNodeWithTag("memory-narrative-chapter-0").assertExists()
        rule.onNodeWithTag("memory-narrative-review-badge").assertTextEquals("AI 建议 · 待核对")
        rule.onNodeWithTag("memory-narrative-chapter-title-0").assertTextEquals("早晨")
        rule.onNodeWithTag("memory-narrative-narration-0").assertTextEquals(proposalNarration)
        rule.onNodeWithTag("memory-narrative-original-toggle-0").assertTextEquals("查看当前阅读的章节")
        rule.onNodeWithTag("memory-narrative-original-text-0").assertDoesNotExist()
        rule.onNodeWithTag("memory-narrative-question-0").assertTextEquals("• 哪一年？")
        rule.onNodeWithTag("memory-narrative-sources-toggle-0").performScrollTo().performClick()
        rule.onNodeWithText("家人提供的回忆", substring = true).assertExists()
        rule.onNodeWithText("AI 观察 · 需核实", substring = true).assertExists()
        rule.onNodeWithText("故事整理文字", substring = true).assertExists()
        rule.onNodeWithText("家人提供的文字", substring = true).assertExists()
        rule.onNodeWithText("来源尚未加载", substring = true).assertExists()
        rule.onNodeWithText("family-11111111-1111-1111-1111-111111111111", substring = true).assertDoesNotExist()
        rule.onNodeWithText(contributionId, substring = true).assertDoesNotExist()
        rule.onNodeWithTag("memory-narrative-original-toggle-0").performScrollTo().performClick()
        rule.onNodeWithText("当前阅读的章节 · 仅供对照").assertExists()
        rule.onNodeWithTag("memory-narrative-original-text-0").assertTextEquals("奶奶带我们走进花园。")
        rule.onNodeWithTag("memory-narrative-review-only").assertExists()
        rule.onNodeWithTag("memory-narrative-review-only").performScrollTo()
        val narrativeStoryBeforeReview = store.state.value.savedMemoryStories!!.detail!!
        val narrativeJobBeforeReview = store.state.value.savedMemoryStories!!.community!!.narrativeJob!!
        val narrativeRequestsBeforeReview = community.narrativeSent
        val chatRequestsBeforeReview = community.chatSent
        rule.runOnIdle {
            assertSame("reading a narrative proposal must not replace the saved story", narrativeStoryBeforeReview,
                store.state.value.savedMemoryStories?.detail)
            assertSame("review controls do not mutate the ready narrative job", narrativeJobBeforeReview,
                store.state.value.savedMemoryStories?.community?.narrativeJob)
            assertEquals(narrativeRequestsBeforeReview, community.narrativeSent)
            assertEquals(chatRequestsBeforeReview, community.chatSent)
        }
        capture("narrative-ready-review")
        rule.runOnIdle { previewFontScale.floatValue = 1.5f }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-narrative-review-only").performScrollTo()
        rule.onNodeWithTag("saved-memory-narration-toggle").assertIsDisplayed()
        rule.onNodeWithTag("saved-memory-stories").performTouchInput { swipeUp() }
        rule.onNodeWithTag("memory-narrative-review-only").assertExists()
        capture("narrative-ready-review-font150")
        rule.runOnIdle { previewFontScale.floatValue = 1f }
        rule.onNodeWithTag("saved-memory-close").performClick()
        rule.onNodeWithText("离开这个故事？").assertExists()
        rule.onNodeWithTag("memory-community-discard-confirm").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories == null }
    }

    @Test fun recordingWaitsForExplicitShareAndUsesCurrentConsentEvenWhenOff() {
        val community = CommunityApi()
        val store = ConnectedStore(StoryApi(), scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            CompositionLocalProvider(LocalMemoryContributionCaptureFactory provides SyntheticCaptureFactory()) {
                ConnectedApp(store, initialLanguage = "zh")
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.capabilities != null }
        rule.onNodeWithText("共同讲述").performClick()

        // A recorder that finishes at its 30 second cap only creates a draft. Discard never reaches transport.
        rule.onNodeWithTag("memory-audio-record").performScrollTo().performClick()
        rule.waitUntil(5000) { rule.onAllNodesWithTag("memory-audio-draft").fetchSemanticsNodes().isNotEmpty() }
        rule.runOnIdle { assertEquals(0, community.audioSent) }
        rule.onNodeWithTag("memory-audio-share").performScrollTo()
        capture("audio-recording-draft-before-share")
        rule.onNodeWithTag("memory-audio-discard").performClick()
        rule.runOnIdle {
            assertEquals(0, community.audioSent)
            assertNull(store.state.value.savedMemoryStories?.community?.pendingAudio)
            assertFalse(store.state.value.savedMemoryStories?.community?.audioConsent ?: true)
        }

        // Manual Stop creates the same draft. Original-only sharing works with consent off and current language.
        rule.onNodeWithTag("memory-audio-record").performScrollTo().performClick()
        rule.onNodeWithTag("memory-audio-stop").performClick()
        rule.onNodeWithTag("memory-audio-draft").assertExists()
        rule.onNodeWithText("English").performScrollTo().performClick()
        rule.runOnIdle { assertEquals(0, community.audioSent) }
        rule.runOnIdle { community.failNextAudio = true }
        rule.onNodeWithTag("memory-audio-share").performScrollTo().performClick()
        rule.waitUntil(5000) { community.audioSent == 1 }
        rule.waitUntil(5000) {
            val state = store.state.value.savedMemoryStories?.community
            state?.pendingAudio != null && state.failure != null
        }
        rule.onNodeWithTag("memory-audio-retry-needed").assertExists()
        rule.onNodeWithTag("memory-audio-record").assertIsNotEnabled()
        rule.onNodeWithTag("memory-audio-retry").performScrollTo().performClick()
        rule.waitUntil(5000) { community.audioSent == 2 && store.state.value.savedMemoryStories?.community?.pendingAudio == null }
        rule.runOnIdle {
            assertEquals("en", community.audioRequest?.getValue("language")?.jsonPrimitive?.content)
            assertEquals("0", community.audioRequest?.getValue("consent")?.jsonPrimitive?.content)
            assertEquals(2, community.audioSent)
            assertEquals(2, community.audioMutations.size)
            assertEquals(community.audioMutations[0], community.audioMutations[1])
        }
    }

    @Test fun wholeStoryContributionScopeCoversTextAndOriginalAudioChinese() = wholeStoryContributionScopeJourney("zh")

    @Test fun wholeStoryContributionScopeCoversTextAndOriginalAudioEnglish() = wholeStoryContributionScopeJourney("en")

    private fun wholeStoryContributionScopeJourney(language: String) {
        val zh = language == "zh"
        val community = CommunityApi()
        val store = ConnectedStore(StoryApi(), scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                CompositionLocalProvider(LocalMemoryContributionCaptureFactory provides SyntheticCaptureFactory()) {
                    ConnectedApp(store, initialLanguage = language)
                }
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.capabilities != null }
        rule.onNodeWithText(if (zh) "共同讲述" else "Memories").performScrollTo().performClick()

        val wholeLabel = if (zh) "整个故事" else "Entire story"
        val chapterLabel = if (zh) "当前篇章" else "Current chapter"
        rule.onNodeWithTag("memory-contribution-scope-description").performScrollTo()
            .assertTextContains(if (zh) "涵盖这个故事中的所有媒体" else "cover all media in this story", substring = true)
        rule.onNodeWithText(wholeLabel).performScrollTo().assertIsDisplayed()
        rule.onNodeWithText(chapterLabel).performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("memory-contribution-scope-current-chapter").performScrollTo().performClick()
        rule.runOnIdle {
            assertFalse(store.state.value.savedMemoryStories?.community?.contributionWholeStory ?: true)
        }
        rule.onNodeWithTag("memory-contribution-scope-whole-story").performScrollTo().performClick()
        rule.runOnIdle {
            assertTrue(store.state.value.savedMemoryStories?.community?.contributionWholeStory == true)
        }

        capture(if (zh) "whole-story-scope-zh150" else "whole-story-scope-en150")
        val words = if (zh) "奶奶记得这次完整的花园旅程。" else "Grandma remembers the whole garden visit."
        rule.onNodeWithTag("memory-contribution-text").performScrollTo().performTextInput(words)
        rule.onNodeWithTag("memory-contribution-consent").performScrollTo().performClick()
        rule.onNodeWithTag("memory-contribution-submit").performScrollTo().performClick()
        rule.waitUntil(5000) { community.textSent == 1 }
        rule.runOnIdle {
            assertEquals("whole story request uses the contract's empty chapter_id string", "",
                community.lastTextRequest?.get("chapter_id")?.jsonPrimitive?.content)
            assertTrue(store.state.value.savedMemoryStories?.community?.contributionWholeStory == true)
        }

        // Audio processing remains a separate explicit choice; the submitted bytes are the original recording.
        rule.onNodeWithTag("memory-audio-consent").performScrollTo().performClick()
        rule.onNodeWithTag("memory-audio-record").performScrollTo().performClick()
        rule.waitUntil(5000) { rule.onAllNodesWithTag("memory-audio-draft").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("memory-contribution-scope-whole-story").assertIsNotEnabled()
        rule.onNodeWithTag("memory-contribution-scope-current-chapter").assertIsNotEnabled()
        rule.onNodeWithTag("memory-audio-share").performScrollTo().performClick()
        rule.waitUntil(5000) { community.audioSent == 1 }
        rule.runOnIdle {
            assertEquals("", community.audioRequest?.get("chapter_id")?.jsonPrimitive?.content)
            assertEquals("1", community.audioRequest?.get("consent")?.jsonPrimitive?.content)
        }
    }

    @Test fun viewerCannotOpenNarrativeOrSendNarrativeRequest() {
        val community = CommunityApi()
        val store = ConnectedStore(StoryApi().apply { storyCanEdit = false }, scope,
            memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, previewFontScale.floatValue)) {
                ConnectedApp(store, initialLanguage = "zh")
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.capabilities != null }
        rule.onNodeWithTag("memory-community-tab-2").assertIsNotEnabled()
        rule.runOnIdle {
            store.selectMemoryCommunityTab(2)
            store.requestMemoryNarrative("No write request from a viewer")
            store.retryMemoryNarrative()
        }
        rule.onNodeWithTag("memory-narrative-viewer-only").assertExists()
        rule.onNodeWithTag("memory-narrative-request").assertDoesNotExist()
        rule.runOnIdle {
            assertEquals(0, community.narrativeSent)
            assertNull(store.state.value.savedMemoryStories?.community?.pendingNarrative)
            assertFalse(store.state.value.covered)
        }
    }

    @Test fun memoirShelfAndOrderedReaderRemainReadableAtLargeFontScale() {
        val store = ConnectedStore(StoryApi(), scope, memoryCommunityApi = CommunityApi(), memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, previewFontScale.floatValue)) {
                ConnectedApp(store, initialLanguage = "zh")
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null || store.state.value.memoryBooks?.problem != null }
        assertNotNull("book shelf error: " + store.state.value.memoryBooks?.problem, store.state.value.memoryBooks?.result)
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-entry-0").performClick()
        rule.waitUntil(5000) {
            val reading = store.state.value.memoryBooks
            reading?.story?.id == id && !reading.framesBusy && reading.hero != null
        }
        rule.onNodeWithTag("memory-book-story-text").assertExists()
        rule.onNodeWithTag("memory-book-hero").assertExists()
        rule.onNodeWithTag("memory-book-frame-1").assertExists()
        rule.onNodeWithText("查看本章素材来源").assertExists()
        rule.onNodeWithText("以下是本章引用的参考资料，不代表已核实事实。").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-sources-toggle").assertExists().performClick()
        rule.onNodeWithText("以下是本章引用的参考资料，不代表已核实事实。").assertExists()
        rule.onNodeWithTag("memory-book-sources-text-family-11111111-1111-1111-1111-111111111111").assertTextEquals("<b>奶奶</b>带我们走进花园。")
        rule.onNodeWithTag("memory-book-sources-text-family-11111111-1111-1111-1111-111111111111").performScrollTo()
        rule.onNodeWithText("AI 观察 · 需核对").assertExists()
        captureBooks("memoir-reader-sources-normal")
        rule.onNodeWithTag("memory-book-next").performClick()
        rule.waitUntil(5000) {
            val reading = store.state.value.memoryBooks
            reading?.storyIndex == 1 && reading.story?.id == bookStory2 && !reading.framesBusy && reading.hero != null
        }
        rule.runOnIdle { previewFontScale.floatValue = 1.5f }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-story-text").assertExists()
        rule.onNodeWithTag("memory-book-sources-toggle").assertExists()
        rule.onNodeWithTag("memory-book-sources-text-caption-1").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-sources-toggle").performScrollTo().performClick()
        rule.onNodeWithText("以下是本章引用的参考资料，不代表已核实事实。").assertExists()
        rule.onNodeWithTag("memory-book-sources-text-family-11111111-1111-1111-1111-111111111111").performScrollTo()
        rule.onNodeWithTag("memory-book-previous").assertExists()
        rule.onNodeWithTag("memory-books-font-scale-1.5").assertExists()
        rule.onNodeWithTag("memory-books-close").assertExists()
        captureBooks("memoir-reader-sources-font150")
        rule.onNodeWithTag("memory-books-back").performClick()
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-resume").assertExists()
        captureBooks("memoir-reader-resume-button")
        rule.onNodeWithTag("memory-book-resume").performClick()
        rule.waitUntil(5000) {
            val reading = store.state.value.memoryBooks
            reading?.storyIndex == 1 && reading.story?.id == bookStory2 && !reading.readerBusy
        }
        rule.onNodeWithTag("memory-book-open-media").assertIsEnabled()
        rule.onNodeWithTag("memory-book-open-media").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks == null }
        assertNull("protected asset open problem: ${store.state.value.problem}", store.state.value.problem)
        assertEquals("1", store.state.value.detail?.asset?.id)
    }

    @Test fun storyChatDictationPreservesOversizeTranscriptAndAddsOnlyToCurrentDraft() {
        val community = CommunityApi()
        val storyApi = StoryApi(voiceEnabled = true)
        val store = ConnectedStore(storyApi, scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = "zh")
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.capabilities != null }
        rule.onNodeWithTag("memory-community-tab-1").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.tab == 1 }
        rule.onNodeWithTag("memory-chat-start").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.community?.conversationId != null }
        rule.onNodeWithTag("memory-chat-enable-dictation").performScrollTo().performClick()
        val dictation = store.memoryCommunityDictation()!!
        rule.waitUntil(5000) { dictation.state.value.capabilities?.transcribe == true }
        rule.onNodeWithTag("memory-dictation-record").assertTextEquals("录音说消息")
        rule.onNodeWithText("录音→核对文字→加入消息草稿→由你发送。录音不会保留；对话和转写记录保留30天。")
            .assertExists()
        assertNotNull(dictation.beginRecording())
        dictation.stopRecording(syntheticMemoryAudioWav(1000))
        rule.waitUntil(5000) { dictation.state.value.transcript == "语音原稿" }
        rule.runOnIdle {
            val communityState = store.state.value.savedMemoryStories?.community
            assertSame("the reader state owns the visible dictation controller", dictation, communityState?.dictation)
            assertEquals("voice-only guard fixture has no active chat draft", "", communityState?.chatDraft)
            assertTrue("voice-only guard fixture has no retained thread drafts", communityState?.threadDrafts?.values?.none(String::isNotBlank) == true)
        }
        rule.onNodeWithTag("saved-memory-open-1").performScrollTo().performClick()
        rule.onNodeWithText("打开这张照片？").assertExists()
        captureDialog("story-media-exit-voice-warning-font150")
        rule.onNodeWithTag("memory-community-discard-cancel").performClick()
        rule.runOnIdle {
            val reading = store.state.value.savedMemoryStories!!
            assertEquals(id, reading.detail?.id)
            assertEquals(0, reading.selectedChapter)
            assertEquals("", reading.community?.chatDraft)
            assertTrue(reading.community?.threadDrafts?.values?.none(String::isNotBlank) == true)
            assertNull("Cancel does not open story media", store.state.value.detail)
            assertEquals("Cancel retains the reviewed transcription", "语音原稿", reading.community?.dictation?.state?.value?.transcript)
        }

        val oversizedDraft = "家".repeat(1336) // 4,008 UTF-8 bytes
        val editedTranscript = "语音转写".repeat(30)
        store.updateMemoryChatDraft(oversizedDraft)
        dictation.updateTranscript(editedTranscript)
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().assertTextEquals("加入消息草稿")
        rule.onNodeWithTag("memory-dictation-insert").performClick()
        rule.onNodeWithTag("memory-chat-dictation-limit").performScrollTo().assertExists()
        rule.runOnIdle {
            assertEquals(0, community.chatSent)
            assertEquals(oversizedDraft, store.state.value.savedMemoryStories?.community?.chatDraft)
            assertEquals(editedTranscript, dictation.state.value.transcript)
        }
        rule.onNodeWithTag("memory-chat-dictation-limit").performScrollTo()
        capture("story-chat-dictation-limit-font150")
        // The visible discard path leaves the scoped error until a new conversation opens.
        rule.onNodeWithText("放弃文字").performScrollTo().performClick()
        rule.onNodeWithTag("memory-chat-dictation-limit").assertExists()
        val oldConversation = store.state.value.savedMemoryStories!!.community!!.conversationId
        rule.onNodeWithTag("memory-chat-new").performScrollTo().performClick()
        rule.waitUntil(5000) {
            val chat = store.state.value.savedMemoryStories?.community
            chat?.conversationId != null && chat.conversationId != oldConversation && !chat.busy
        }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-chat-dictation-limit").assertDoesNotExist()
        rule.onNodeWithTag("memory-chat-context-window").performScrollTo().assertIsDisplayed()
        capture("story-chat-context-window-font150")
        rule.onNodeWithTag("memory-chat-input").performScrollTo().assertExists()
        rule.runOnIdle {
            val newChat = store.state.value.savedMemoryStories!!.community!!
            assertEquals("new conversation starts blank", "", newChat.chatDraft)
            assertEquals("old thread draft remains scoped", oversizedDraft, newChat.threadDrafts[oldConversation])
        }

        assertNotNull(dictation.beginRecording())
        dictation.stopRecording(syntheticMemoryAudioWav(1000))
        rule.waitUntil(5000) { dictation.state.value.transcript == "语音原稿" }
        val acceptedWords = "我们在花园里聊天。"
        dictation.updateTranscript(acceptedWords)
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().performClick()
        rule.waitForIdle()
        rule.onNodeWithTag("memory-chat-dictation-limit").assertDoesNotExist()
        rule.onNodeWithTag("memory-dictation-transcript").assertDoesNotExist()
        rule.runOnIdle {
            assertEquals(0, community.chatSent)
            assertEquals(acceptedWords, store.state.value.savedMemoryStories?.community?.chatDraft)
        }
        rule.onNodeWithTag("memory-chat-send").performScrollTo().performClick()
        rule.waitUntil(5000) { community.chatSent == 1 && store.state.value.savedMemoryStories?.community?.job?.state == "ready" }
        assertEquals("only the explicit Send submits the accepted words", acceptedWords, community.sentChatText)

        val exitDraft = "离开故事前仍要保留的消息草稿"
        store.updateMemoryChatDraft(exitDraft)
        rule.onNodeWithTag("saved-memory-open-1").performScrollTo().performClick()
        rule.onNodeWithText("打开这张照片？").assertExists()
        rule.onNodeWithText("此页的草稿和语音输入会被清除。已发送的请求仍可能继续处理。").assertExists()
        rule.onNodeWithTag("memory-community-discard-cancel").performClick()
        rule.runOnIdle {
            val reading = store.state.value.savedMemoryStories!!
            assertEquals(id, reading.detail?.id)
            assertEquals(0, reading.selectedChapter)
            assertEquals(exitDraft, reading.community?.chatDraft)
            assertNull("cancel keeps the reader open without opening media", store.state.value.detail)
        }
        rule.onNodeWithTag("saved-memory-open-1").performScrollTo().performClick()
        rule.onNodeWithText("打开这张照片？").assertExists()
        rule.onNodeWithTag("memory-community-discard-confirm").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories == null && store.state.value.detail?.asset?.id == "1" }
        assertEquals("explicit confirmation opens the selected story photo", "1", store.state.value.detail?.asset?.id)
    }

    @Test fun memoirExitProtectsAnActiveRecordingBeforeAnyTranscriptExists() {
        val store = ConnectedStore(StoryApi(voiceEnabled = true), scope, memoryCommunityApi = CommunityApi(), memoryCommunityEnabled = true)
        rule.setContent { ConnectedApp(store, initialLanguage = "zh") }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-entry-0").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.story?.id == id }
        val dictation = rule.runOnIdle { store.memoryBookChatDictation()!! }
        rule.runOnIdle { dictation.loadCapabilities() }
        rule.waitUntil(5000) { dictation.state.value.capabilities?.transcribe == true }
        rule.runOnIdle { assertNotNull(dictation.beginRecording()) }
        assertNull(dictation.state.value.transcript)
        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-book-discard-dialog").assertExists()
        rule.onNodeWithTag("memory-book-discard-cancel").performClick()
        assertTrue(dictation.state.value.recording)
        assertNotNull(store.state.value.memoryBooks?.selectedBook)
        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-book-discard-confirm").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks == null }
        assertFalse(dictation.state.value.recording)
    }

    @Test fun memoirNarrativeFormsRemainExplicitAndKeepOriginalWordsChinese() = memoirNarrativeFormJourney("zh")
    @Test fun memoirNarrativeFormsRemainExplicitAndKeepOriginalWordsEnglish() = memoirNarrativeFormJourney("en")

    private fun memoirNarrativeFormJourney(language: String) {
        val community = CommunityApi()
        val store = ConnectedStore(StoryApi(), scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = language)
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-narrative-disclosure").performScrollTo().performClick()
        assertEquals(MemoryBookNarrativeForm.EXISTING, store.memoryBookNarrativeState.value.form)
        rule.onNodeWithTag("memory-book-narrative-form-open").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-narrative-form-essay").performScrollTo().assertIsDisplayed()
        captureDisplay("memoir-narrative-form-$language-options-font150")
        rule.onNodeWithTag("memory-book-narrative-form-essay").performClick()
        assertEquals(MemoryBookNarrativeForm.ESSAY, store.memoryBookNarrativeState.value.form)
        assertEquals(0, community.planReads)
        assertEquals(0, community.narrativeSent)
        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-book-discard-dialog").assertExists()
        rule.onNodeWithTag("memory-book-discard-cancel").performClick()
        assertEquals(MemoryBookNarrativeForm.ESSAY, store.memoryBookNarrativeState.value.form)
        val words = "奶奶的讲述仍是原文，大家记不清的年份要先问。"
        rule.onNodeWithTag("memory-book-narrative-instructions").performScrollTo().performTextInput(words)
        rule.onNodeWithTag("memory-book-narrative-check").performScrollTo().performClick()
        try {
            rule.waitUntil(5000) { store.memoryBookNarrativeState.value.status == MemoryBookNarrativeStatus.PLAN_READY }
        } catch (failure: androidx.compose.ui.test.ComposeTimeoutException) {
            captureDisplay("memoir-narrative-form-$language-plan-timeout-font150")
            throw failure
        }
        assertEquals(words, store.memoryBookNarrativeState.value.instructions)
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().assertIsDisplayed()
        captureDisplay("memoir-narrative-form-$language-ready-font150")
        rule.onNodeWithTag("memory-book-narrative-request").performClick()
        rule.waitUntil(5000) { community.narrativeSent == 1 }
        val sent = community.lastNarrativeRequest!!["instructions"]!!.jsonPrimitive.content
        assertTrue(sent.startsWith(words))
        assertTrue(sent.contains("家庭散文"))
        assertEquals(words, store.memoryBookNarrativeState.value.instructions)
        assertEquals(0, community.textSent)
        assertEquals(0, community.chatSent)
    }

    @Test fun memoirVoiceInstructionsNeedExplicitInsertionAndRequestChinese() = memoirInstructionVoiceJourney("zh")
    @Test fun memoirVoiceInstructionsNeedExplicitInsertionAndRequestEnglish() = memoirInstructionVoiceJourney("en")

    private fun memoirInstructionVoiceJourney(language: String) {
        val community = CommunityApi()
        val api = StoryApi(voiceEnabled = true)
        val store = ConnectedStore(api, scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = language)
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-narrative-disclosure").performScrollTo().performClick()
        val typed = "按家人的讲述顺序。"
        rule.onNodeWithTag("memory-book-narrative-instructions").performScrollTo().performTextInput(typed)
        rule.onNodeWithTag("memory-book-narrative-voice-open").performScrollTo().performClick()
        try {
            rule.waitUntil(5000) { store.memoryBookNarrativeDictationState.value?.state?.value?.capabilities?.transcribe == true }
        } catch (failure: androidx.compose.ui.test.ComposeTimeoutException) {
            captureDisplay("memoir-instruction-voice-$language-open-timeout-font150")
            throw failure
        }
        val voice = store.memoryBookNarrativeDictationState.value!!
        assertEquals(0, api.assistantTranscriptions)
        assertEquals(0, community.narrativeSent)
        rule.runOnIdle { assertNotNull(voice.beginRecording()) }
        rule.onNodeWithTag("memory-book-narrative-disclosure").assertIsNotEnabled()
        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-book-discard-dialog").assertExists()
        rule.onNodeWithTag("memory-book-discard-cancel").performClick()
        assertTrue(voice.state.value.recording)
        rule.runOnIdle { voice.stopRecording(syntheticMemoryAudioWav(1000)) }
        rule.waitUntil(5000) { voice.state.value.transcript != null }
        rule.onNodeWithTag("memory-book-narrative-check").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().assertIsNotEnabled()
        val reviewed = "保留不同家人的说法，先询问不确定的年份。"
        rule.onNodeWithTag("memory-dictation-transcript").performScrollTo().performTextReplacement(reviewed)
        rule.onNodeWithTag("memory-dictation-transcript").performImeAction()
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().assertIsDisplayed()
        captureDisplay("memoir-instruction-voice-$language-review-font150")
        assertEquals(typed, store.memoryBookNarrativeState.value.instructions)
        rule.onNodeWithTag("memory-dictation-insert").performClick()
        rule.waitUntil(5000) { voice.state.value.transcript == null }
        rule.onNodeWithTag("memory-book-narrative-instructions").performScrollTo().assertTextContains("$typed\n$reviewed")
        assertEquals(0, community.narrativeSent)
        rule.onNodeWithTag("memory-book-narrative-check").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookNarrativeState.value.status == MemoryBookNarrativeStatus.PLAN_READY }
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().assertIsDisplayed()
        captureDisplay("memoir-instruction-voice-$language-inserted-font150")
        rule.onNodeWithTag("memory-book-narrative-request").performClick()
        rule.waitUntil(5000) { community.narrativeSent == 1 }
        assertEquals("$typed\n$reviewed", community.lastNarrativeRequest!!["instructions"]!!.jsonPrimitive.content)
        assertEquals(0, community.textSent)
        assertEquals(0, community.chatSent)
    }

    @Test fun independentFamilyEditionShelfChinese() = independentFamilyEditionShelf("zh")
    @Test fun independentFamilyEditionShelfEnglish() = independentFamilyEditionShelf("en")

    private fun independentFamilyEditionShelf(language: String) {
        val community = CommunityApi().apply {
            largeNarrativeFixture = true; editionsEnabled = true; independentEditionFixture = true
        }
        val speech = ReplySpeechFactory()
        val store = ConnectedStore(StoryApi(largeNarrativeFixture = true), scope,
            memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f),
                LocalChapterSpeechAdapterFactory provides speech,
                LocalChapterAudioFocusFactory provides SyntheticAudioFocusFactory()) {
                ConnectedApp(store, initialLanguage = language)
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        assertFalse(store.state.value.memoryBooks!!.selectedBook!!.canEdit)
        rule.onNodeWithTag("memory-book-narrative-disclosure").assertDoesNotExist()
        assertNull(store.memoryBookNarrativeState.value.job)
        assertTrue(community.editionPages.isEmpty())
        rule.onNodeWithTag("memory-edition-shelf-open").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.LIST }
        assertEquals(8, store.memoryBookEditionShelfState.value.listing!!.items.size)
        rule.onNodeWithTag("memory-edition-shelf-prose").assertDoesNotExist()
        rule.onNodeWithTag("memory-edition-shelf-version-0").performScrollTo().assertTextContains(if (language == "zh") "成稿 1" else "Edition 1", substring = true)
        captureDisplay("memoir-shelf-$language-list-font150")
        rule.onNodeWithTag("memory-edition-shelf-next-page").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.listing?.page == 2 }
        assertEquals(1, store.memoryBookEditionShelfState.value.listing!!.items.size)
        val viewport = rule.onNodeWithTag("memory-book-reader-scroll").fetchSemanticsNode().boundsInWindow
        listOf("memory-edition-shelf-previous-page", "memory-edition-shelf-next-page").forEach {
            rule.onNodeWithTag(it).performScrollTo().assertIsDisplayed()
            val bounds = rule.onNodeWithTag(it).fetchSemanticsNode().boundsInWindow
            assertTrue("$it $bounds fits the reader $viewport", bounds.left >= viewport.left - 1f && bounds.right <= viewport.right + 1f)
        }
        captureDisplay("memoir-shelf-$language-page2-font150")
        rule.onNodeWithTag("memory-edition-shelf-previous-page").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.listing?.page == 1 }
        rule.onNodeWithTag("memory-edition-shelf-version-0").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.READ }
        rule.onNodeWithTag("memory-edition-shelf-prose").performScrollTo().assertTextEquals(narrativeChapterText(0))
        assertTrue(speech.engines.all { it.utterances.isEmpty() })
        rule.onNodeWithTag("memory-edition-shelf-narration-toggle").performScrollTo().performClick()
        rule.waitUntil(5000) { speech.engines.lastOrNull()?.utterances?.isNotEmpty() == true }
        val firstSpeech = speech.engines.last()
        rule.onNodeWithTag("memory-edition-shelf-directory").performScrollTo().performClick()
        rule.onNodeWithTag("memory-edition-shelf-chapter-23").performScrollTo().assertTextContains(narrativeStoryTitle(3), substring = true)
        captureDisplay("memoir-shelf-$language-directory-font150")
        rule.onNodeWithTag("memory-edition-shelf-chapter-23").performClick()
        rule.waitUntil(5000) { firstSpeech.stopped > 0 }
        rule.onNodeWithTag("memory-edition-shelf-position").performScrollTo()
            .assertTextEquals(if (language == "zh") "篇章 24/24" else "Chapter 24 of 24")
        rule.onNodeWithTag("memory-edition-shelf-prose").performScrollTo().assertTextEquals(narrativeChapterText(23))
        captureDisplay("memoir-shelf-$language-read-font150")
        community.editionInvalidated = true
        rule.onNodeWithTag("memory-edition-shelf-recheck").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.SOURCE_CHANGED }
        rule.onNodeWithTag("memory-edition-shelf-prose").assertDoesNotExist()
        rule.onNodeWithTag("memory-edition-shelf-source-changed").performScrollTo().assertIsDisplayed()
        captureDisplay("memoir-shelf-$language-invalidated-font150")
        community.editionInvalidated = false
        rule.onNodeWithTag("memory-edition-shelf-recheck").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.READ }
        community.failNextEditionRead = true
        rule.onNodeWithTag("memory-edition-shelf-recheck").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.FAILED }
        rule.onNodeWithTag("memory-edition-shelf-prose").assertDoesNotExist()
        rule.onNodeWithTag("memory-edition-shelf-failed").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("memory-edition-shelf-close").performScrollTo().performClick()
        community.editionsEnabled = false
        rule.onNodeWithTag("memory-edition-shelf-open").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.UNAVAILABLE }
        assertEquals(listOf(1, 2, 1), community.editionPages)
        community.editionsEnabled = true
        rule.onNodeWithTag("memory-edition-shelf-refresh").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.LIST }
        assertEquals(listOf(1, 2, 1, 1), community.editionPages)
        assertEquals(0, community.editionReads)
        assertEquals(0, community.narrativeSent)
        assertEquals(0, community.chatSent)
        assertEquals(0, community.textSent)
        assertTrue(community.editionBodies.isEmpty())
        assertNull(store.memoryBookNarrativeState.value.job)
    }

    @Test fun editionOriginalInspectorChinese() = editionOriginalInspector("zh")
    @Test fun editionOriginalInspectorEnglish() = editionOriginalInspector("en")

    private fun editionOriginalInspector(language: String) {
        val community=CommunityApi().apply {
            largeNarrativeFixture=true; editionsEnabled=true; independentEditionFixture=true
        }
        val store=ConnectedStore(StoryApi(largeNarrativeFixture=true),scope,memoryCommunityApi=community,memoryCommunityEnabled=true)
        rule.setContent {
            val base=LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density,1.5f)) {
                ConnectedApp(store,initialLanguage=language)
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123","synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-edition-shelf-open").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.LIST }
        rule.onNodeWithTag("memory-edition-shelf-version-0").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.READ }
        assertTrue(community.editionSourcePages.isEmpty()); assertTrue(community.editionSourceReads.isEmpty())
        assertEquals(0,community.editionSourceAudioReads)
        rule.onNodeWithTag("memory-edition-source-references").performScrollTo().performClick()
        assertTrue(community.editionSourceReads.isEmpty())
        rule.onNodeWithTag("memory-edition-source-reference-0").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionSourceState.value.status == MemoryBookEditionSourceStatus.DETAIL }
        rule.onNodeWithTag("memory-edition-source-origin").performScrollTo().assertTextEquals(if (language == "zh") "照片的 AI 说明" else "AI photo description")
        rule.onNodeWithTag("memory-edition-source-original").performScrollTo().assertTextContains("照片说明原文",substring=true)
        captureSourceFrame("memoir-source-$language-original-font150")
        rule.onNodeWithTag("memory-edition-source-excerpt-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("memory-edition-source-excerpt").performScrollTo().assertTextEquals("那天大家在花园里一起种花。")
        assertEquals(listOf("caption-1"),community.editionSourceReads)
        rule.onNodeWithTag("memory-edition-source-catalog").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionSourceState.value.listing?.items?.size == 16 }
        assertNull(store.memoryBookEditionSourceState.value.detail)
        rule.onNodeWithTag("memory-edition-source-next-page").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionSourceState.value.listing?.page == 2 }
        assertEquals(1,store.memoryBookEditionSourceState.value.listing!!.items.size)
        captureSourceFrame("memoir-source-$language-page2-font150")
        rule.onNodeWithTag("memory-edition-source-previous-page").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionSourceState.value.listing?.page == 1 }
        rule.onNodeWithTag("memory-edition-source-item-1").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionSourceState.value.detail?.source?.audioAvailable == true }
        rule.onNodeWithTag("memory-edition-source-transcript").performScrollTo().assertTextContains("请听原声核对",substring=true)
        assertEquals(0,community.editionSourceAudioReads)
        rule.onNodeWithTag("memory-edition-source-load-audio").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionSourceState.value.audio != null }
        val audio=store.memoryBookEditionSourceState.value.audio!!
        rule.onNodeWithTag("memory-edition-source-audio-toggle").performScrollTo().assertTextContains(if (language == "zh") "播放原始录音" else "Play original audio")
        val viewport=rule.onNodeWithTag("memory-book-reader-scroll").fetchSemanticsNode().boundsInWindow
        val control=rule.onNodeWithTag("memory-edition-source-audio-toggle").fetchSemanticsNode().boundsInWindow
        assertTrue(control.left >= viewport.left-1f && control.right <= viewport.right+1f)
        captureSourceFrame("memoir-source-$language-audio-manual-font150")
        community.failNextSourceRead=true
        rule.onNodeWithTag("memory-edition-source-recheck").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionSourceState.value.status == MemoryBookEditionSourceStatus.FAILED }
        assertTrue(audio.isClosed); rule.onNodeWithTag("memory-edition-source-transcript").assertDoesNotExist()
        rule.onNodeWithTag("memory-edition-source-audio-toggle").assertDoesNotExist()
        rule.onNodeWithTag("memory-edition-source-failed").performScrollTo().assertIsDisplayed()
        captureSourceFrame("memoir-source-$language-failed-cleared-font150")
        rule.onNodeWithTag("memory-edition-source-item-1").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionSourceState.value.detail?.source?.audioAvailable == true }
        rule.onNodeWithTag("memory-edition-shelf-next-chapter").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionSourceState.value.status == MemoryBookEditionSourceStatus.CLOSED }
        assertNull(store.memoryBookEditionSourceState.value.detail)
        rule.onNodeWithTag("memory-edition-source-references").performScrollTo().performClick()
        community.sourceInvalidated=true
        rule.onNodeWithTag("memory-edition-source-reference-0").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionShelfState.value.status == MemoryBookEditionShelfStatus.SOURCE_CHANGED }
        rule.onNodeWithTag("memory-edition-shelf-prose").assertDoesNotExist()
        rule.onNodeWithTag("memory-edition-source-panel").assertDoesNotExist()
        rule.onNodeWithTag("memory-edition-shelf-source-changed").assertIsDisplayed()
        assertTrue(community.editionBodies.isEmpty()); assertEquals(0,community.narrativeSent)
        captureSourceFrame("memoir-source-$language-parent-invalidated-font150")
    }

    @Test fun reviewedMemoirEditionEditRetryAndFreshReadChinese() = reviewedMemoirEditionJourney("zh")
    @Test fun reviewedMemoirEditionEditRetryAndFreshReadEnglish() = reviewedMemoirEditionJourney("en")

    private fun reviewedMemoirEditionJourney(language: String) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val setting = "show_ime_with_hard_keyboard"
        val original = android.provider.Settings.Secure.getString(instrumentation.targetContext.contentResolver, setting)
        fun configureKeyboard(value: String?) {
            val command = if (value == null) "settings delete secure $setting" else "settings put secure $setting $value"
            instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
                android.os.ParcelFileDescriptor.AutoCloseInputStream(descriptor).use { it.readBytes() }
            }
        }
        configureKeyboard("1")
        try { reviewedMemoirEditionWithKeyboard(language) }
        finally { configureKeyboard(original) }
    }

    private fun reviewedMemoirEditionWithKeyboard(language: String) {
        val community = CommunityApi().apply { largeNarrativeFixture = true; editionsEnabled = true }
        val store = ConnectedStore(StoryApi(largeNarrativeFixture = true), scope,
            memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                CompositionLocalProvider(LocalChapterSpeechAdapterFactory provides ReplySpeechFactory(),
                    LocalChapterAudioFocusFactory provides SyntheticAudioFocusFactory()) {
                    ConnectedApp(store, initialLanguage = language)
                }
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-narrative-disclosure").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-narrative-check").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookNarrativeState.value.status == MemoryBookNarrativeStatus.PLAN_READY }
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookNarrativeState.value.status == MemoryBookNarrativeStatus.REVIEW_READY }
        assertEquals(0, community.editionReads)
        assertTrue(community.editionBodies.isEmpty())
        rule.onNodeWithTag("memory-edition-open").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionState.value.status == MemoryBookEditionStatus.REVIEW }
        assertEquals(24, store.memoryBookEditionState.value.manuscript!!.chapters.size)
        rule.onNodeWithTag("memory-edition-save").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-edition-next").performScrollTo().performClick()
        rule.onNodeWithTag("memory-edition-position").performScrollTo()
            .assertTextEquals(if (language == "zh") "篇章 2/24" else "Chapter 2 of 24")
        rule.onNodeWithTag("memory-edition-previous").performScrollTo().performClick()
        rule.onNodeWithTag("memory-edition-position").performScrollTo()
            .assertTextEquals(if (language == "zh") "篇章 1/24" else "Chapter 1 of 24")
        rule.onNodeWithTag("memory-edition-title").performScrollTo().performTextReplacement("x".repeat(513))
        assertTrue(store.memoryBookEditionState.value.invalidInput)
        assertTrue(store.memoryBookEditionState.value.dirty)
        rule.onNodeWithTag("memory-book-narrative-disclosure").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-edition-reviewed").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-edition-title").performScrollTo().performTextReplacement("家人一起核对的花园回忆")
        rule.onNodeWithTag("memory-edition-title").performScrollTo().performClick()
        rule.waitUntil(5000) { rule.onAllNodesWithTag("memory-books-ime-visible").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("memory-edition-title").assertIsDisplayed()
        rule.onNodeWithTag("memory-books-close").assertIsDisplayed()
        captureDisplay("memoir-edition-$language-keyboard-font150")
        rule.onNodeWithTag("memory-edition-chapter").performScrollTo().performTextReplacement("奶奶讲述花园的那一天，具体年份还要再问家人。")
        rule.onNodeWithTag("memory-edition-close").performScrollTo().performClick()
        rule.onNodeWithTag("memory-edition-discard-cancel").performClick()
        assertEquals("家人一起核对的花园回忆", store.memoryBookEditionState.value.manuscript!!.title)
        rule.onNodeWithTag("memory-edition-reviewed").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionState.value.reviewed }
        rule.onNodeWithTag("memory-edition-chapter").performScrollTo().performTextReplacement("奶奶讲述花园的那一天；年份仍待家人确认。")
        assertFalse(store.memoryBookEditionState.value.reviewed)
        rule.onNodeWithTag("memory-edition-save").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-edition-reviewed").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionState.value.reviewed }
        rule.onNodeWithTag("memory-edition-reviewed").assertIsOn()
        val viewport = rule.onNodeWithTag("memory-book-reader-scroll").fetchSemanticsNode().boundsInWindow
        listOf("memory-edition-reviewed", "memory-edition-save", "memory-edition-previous", "memory-edition-next").forEach { tag ->
            val bounds = rule.onNodeWithTag(tag).fetchSemanticsNode().boundsInWindow
            assertTrue("$tag must fit the reader width", bounds.left >= viewport.left - 1f && bounds.right <= viewport.right + 1f)
        }
        captureDisplay("memoir-edition-$language-reviewed-font150")
        community.failNextEditionSave = true
        rule.onNodeWithTag("memory-edition-save").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionState.value.status == MemoryBookEditionStatus.SAVE_UNCERTAIN }
        assertEquals(1, community.editionBodies.size)
        rule.onNodeWithTag("memory-edition-shelf-open").performScrollTo().assertIsNotEnabled()
        rule.runOnIdle {
            assertFalse(store.loadMemoryBookEditionShelf())
            assertFalse(store.readMemoryBookShelfEdition("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
            assertFalse(store.loadMemoryBookEditionSources())
            assertFalse(store.readMemoryBookEditionSource("caption-1"))
            assertFalse(store.loadMemoryBookEditionSourceAudio())
            assertTrue(community.editionSourcePages.isEmpty())
            assertTrue(community.editionSourceReads.isEmpty())
            assertEquals(0,community.editionSourceAudioReads)
            assertEquals(MemoryBookEditionShelfStatus.CLOSED, store.memoryBookEditionShelfState.value.status)
        }
        rule.onNodeWithTag("memory-edition-title").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-edition-exit-dialog").assertExists()
        rule.onNodeWithTag("memory-edition-exit-stay").performClick()
        rule.onNodeWithTag("memory-edition-retry").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionState.value.status == MemoryBookEditionStatus.SAVED }
        assertEquals(2, community.editionBodies.size)
        assertEquals(community.editionBodies[0], community.editionBodies[1])
        assertNull(store.memoryBookEditionState.value.manuscript)
        rule.onNodeWithTag("memory-edition-read").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionState.value.manuscript != null }
        rule.onNodeWithTag("memory-edition-prose").performScrollTo().assertTextEquals("奶奶讲述花园的那一天；年份仍待家人确认。")
        captureDisplay("memoir-edition-$language-saved-read-font150")
        community.editionInvalidated = true
        rule.onNodeWithTag("memory-edition-read").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookEditionState.value.status == MemoryBookEditionStatus.SOURCE_CHANGED }
        rule.onNodeWithTag("memory-edition-prose").assertDoesNotExist()
        assertNull(store.memoryBookEditionState.value.manuscript)
        assertEquals(1, community.narrativeSent)
        assertEquals(2, community.editionBodies.size)
        captureDisplay("memoir-edition-$language-source-invalidated-font150")
    }

    @Test fun wholeMemoirDraftCanBeReviewedWithoutApplyingItChinese() = wholeMemoirDraftJourney("zh")
    @Test fun wholeMemoirDraftCanBeReviewedWithoutApplyingItEnglish() = wholeMemoirDraftJourney("en")

    private fun wholeMemoirDraftJourney(language: String) {
        val community = CommunityApi().apply { largeNarrativeFixture = true }
        val replySpeech = ReplySpeechFactory()
        val storyApi = StoryApi(largeNarrativeFixture = true)
        val store = ConnectedStore(storyApi, scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                CompositionLocalProvider(LocalChapterSpeechAdapterFactory provides replySpeech,
                    LocalChapterAudioFocusFactory provides SyntheticAudioFocusFactory()) {
                    ConnectedApp(store, initialLanguage = language)
                }
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-narrative-disclosure").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-narrative-editorial-context").performScrollTo().assertIsOff()
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().assertIsNotEnabled()
        assertEquals(0, community.planReads)
        val instructions = "保留家人的不同讲述，不确定的年份先询问。"
        rule.onNodeWithTag("memory-book-narrative-instructions").performScrollTo().performTextInput(instructions)
        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-book-discard-cancel").performClick()
        rule.onNodeWithTag("memory-book-narrative-instructions").performScrollTo().assertTextContains(instructions)
        rule.onNodeWithTag("memory-book-narrative-editorial-context").performScrollTo().performClick()
        try {
            rule.onNodeWithTag("memory-book-narrative-editorial-context").assertIsOn()
            assertTrue("Editorial context toggle should be selected before checking the plan", store.memoryBookNarrativeState.value.editorialContext)
        } catch (failure: AssertionError) {
            captureDisplay("whole-memoir-$language-editorial-context-toggle-failed-font150")
            throw failure
        }
        captureDisplay("whole-memoir-$language-editorial-context-selected-font150")
        rule.onNodeWithTag("memory-book-narrative-check").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookNarrativeState.value.status == MemoryBookNarrativeStatus.PLAN_READY }
        assertEquals(0, community.narrativeSent)
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().assertIsDisplayed()
        captureDisplay("whole-memoir-$language-plan-font150")
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().assertIsEnabled().performClick()
        rule.waitUntil(5000) { store.memoryBookNarrativeState.value.status == MemoryBookNarrativeStatus.REVIEW_READY }
        assertEquals(24, store.memoryBookNarrativeState.value.proposal?.chapters?.size)
        rule.onNodeWithTag("memory-book-narrative-review-only").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-book-narrative-prose").performScrollTo().assertTextEquals("奶奶讲起那天的花园，大家各自补充记得的片段。")
        rule.onNodeWithTag("memory-book-narrative-prose").performScrollTo().assertIsDisplayed()
        captureDisplay("whole-memoir-$language-review-font150")

        val savedBookBeforeReview = store.state.value.memoryBooks!!.selectedBook!!
        val queuedJobBeforeReview = store.memoryBookNarrativeState.value.job!!
        val planReadsBeforeDirectory = community.planReads
        rule.onNodeWithTag("memory-book-narrative-directory-item-0").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-narrative-directory-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-narrative-directory-item-0").performScrollTo()
            .assertIsSelected().assertTextContains("1. 花园的一天")

        // Chapter identity changes must close the old speech controller.
        rule.onNodeWithTag("memory-book-narration-toggle").performScrollTo().performClick()
        rule.waitUntil(5000) { replySpeech.engines.lastOrNull()?.utterances?.isNotEmpty() == true }
        val firstChapterSpeech = replySpeech.engines.last()
        rule.onNodeWithTag("memory-book-narrative-next").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-narrative-prose").performScrollTo().assertTextEquals("野餐的讲述接续另一段家人回忆，时间仍待确认。")
        rule.waitUntil(5000) { firstChapterSpeech.stopped > 0 }
        rule.onNodeWithTag("memory-book-narrative-chapter-position").performScrollTo()
            .assertTextEquals(if (language == "zh") "篇章 2/24" else "Chapter 2 of 24")

        rule.onNodeWithTag("memory-book-narration-toggle").performScrollTo().performClick()
        rule.waitUntil(5000) {
            replySpeech.engines.size > 1 && replySpeech.engines.last().utterances.isNotEmpty()
        }
        val secondChapterSpeech = replySpeech.engines.last()
        rule.onNodeWithTag("memory-book-narrative-directory-item-6").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.memoryBookNarrativeState.value.proposal?.chapters?.getOrNull(6)?.storyId == bookStory2
        }
        rule.waitUntil(5000) { secondChapterSpeech.stopped > 0 }
        rule.onNodeWithTag("memory-book-narrative-directory-item-6").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-narrative-chapter-position").performScrollTo()
            .assertTextEquals(if (language == "zh") "篇章 7/24" else "Chapter 7 of 24")
        rule.onNodeWithTag("memory-book-narrative-story-label").performScrollTo().assertTextEquals("野餐回忆")
        rule.onNodeWithTag("memory-book-narrative-prose").performScrollTo()
            .assertTextEquals("野餐的讲述接续另一段家人回忆，时间仍待确认。")
        rule.onNodeWithTag("memory-book-narrative-citations").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-book-narrative-citations").performScrollTo().assertIsDisplayed()
        captureDisplay("whole-memoir-$language-no-citations-font150")
        rule.onNodeWithTag("memory-book-narration-toggle").performScrollTo().performClick()
        rule.waitUntil(5000) {
            replySpeech.engines.size > 2 && replySpeech.engines.last().utterances.isNotEmpty()
        }
        val chapterSevenSpeech = replySpeech.engines.last()
        rule.onNodeWithTag("memory-book-narrative-open-story").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.story?.id == bookStory2 }
        rule.waitUntil(5000) { store.state.value.memoryBooks?.readerBusy == false }
        rule.onNodeWithTag("memory-book-story-text").performScrollTo().assertTextEquals("奶奶带我们走进花园。")

        val originalStoryBeforeLastJump = store.state.value.memoryBooks!!.story!!
        val planReadsBeforeLastJump = community.planReads
        rule.onNodeWithTag("memory-book-narrative-directory-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-narrative-directory-item-23").performScrollTo()
            .assertIsNotSelected()
            .assertTextContains("24. 第四则家庭回忆：从花园、野餐到再次相聚的完整故事标题")
            .assertTextContains("第六章：家人一路回望后补充的最后一段细节与感受")
        captureDisplay("whole-memoir-$language-directory-font150")
        rule.onNodeWithTag("memory-book-narrative-directory-item-23").performClick()
        rule.waitForIdle()
        rule.waitUntil(5000) { chapterSevenSpeech.stopped > 0 }
        rule.onNodeWithTag("memory-book-narrative-directory-item-23").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-narrative-chapter-position").performScrollTo()
            .assertTextEquals(if (language == "zh") "篇章 24/24" else "Chapter 24 of 24")
        rule.onNodeWithTag("memory-book-narrative-story-label").performScrollTo()
            .assertTextEquals("第四则家庭回忆：从花园、野餐到再次相聚的完整故事标题")
        rule.onNodeWithTag("memory-book-narrative-chapter-label").performScrollTo()
            .assertTextEquals("第六章：家人一路回望后补充的最后一段细节与感受")
        rule.onNodeWithTag("memory-book-narrative-prose").performScrollTo()
            .assertTextEquals("第二十四篇章的合成建议，保留家人说法并等待核对。")
        captureDisplay("whole-memoir-$language-last-chapter-font150")
        rule.onNodeWithTag("memory-book-narrative-directory-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-narrative-directory-item-23").performScrollTo()
            .assertIsSelected()
        rule.onNodeWithTag("memory-book-narrative-directory-toggle").performClick()

        assertSame(savedBookBeforeReview, store.state.value.memoryBooks?.selectedBook)
        assertSame(originalStoryBeforeLastJump, store.state.value.memoryBooks?.story)
        assertSame(queuedJobBeforeReview, store.memoryBookNarrativeState.value.job)
        assertEquals(planReadsBeforeDirectory, community.planReads)
        assertEquals(planReadsBeforeLastJump, community.planReads)
        assertEquals(1, community.narrativeSent)
        assertEquals(0, community.chatSent)
        assertEquals(0, community.textSent)
        assertEquals(listOf(true), community.narrativeEditorialChoices)
        assertEquals("book", community.lastNarrativeRequest!!.getValue("target_type").jsonPrimitive.content)
        assertEquals(instructions, community.lastNarrativeRequest!!.getValue("instructions").jsonPrimitive.content)
    }

    @Test fun memoirPlanStoryReadingPreservesInstructionsChinese() = memoirPlanStoryReadingJourney("zh")
    @Test fun memoirPlanStoryReadingPreservesInstructionsEnglish() = memoirPlanStoryReadingJourney("en")

    private fun memoirPlanStoryReadingJourney(language: String) {
        val readTrace = mutableListOf<String>()
        val community = CommunityApi(readTrace).apply {
            largeNarrativeFixture = true
            wholeOverCapacity = true
            inspectOnlyNarrativeSection = true
        }
        val storyApi = StoryApi(largeNarrativeFixture = true, bookStoryReadTrace = readTrace)
        val store = ConnectedStore(storyApi, scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = language)
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-narrative-disclosure").performScrollTo().performClick()

        val instructions = "保留家人的原话，未知的年份先询问。"
        rule.onNodeWithTag("memory-book-narrative-instructions").performScrollTo().performTextInput(instructions)
        rule.onNodeWithTag("memory-book-narrative-form-open").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-narrative-form-essay").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-narrative-editorial-context").performScrollTo().performClick()
        assertEquals(instructions, store.memoryBookNarrativeState.value.instructions)
        assertEquals(MemoryBookNarrativeForm.ESSAY, store.memoryBookNarrativeState.value.form)
        assertEquals(0, community.planReads)
        assertEquals(0, community.narrativeSent)

        rule.onNodeWithTag("memory-book-narrative-check").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.memoryBookNarrativeState.value.status == MemoryBookNarrativeStatus.SMALLER_SCOPE
        }
        val plan = store.memoryBookNarrativeState.value.plan!!
        assertEquals(4, plan.sections.size)
        assertEquals(24, plan.chapterCount)
        assertEquals("smaller_scope_required", plan.whole.state)
        assertFalse(plan.whole.canDraft)
        assertNull(plan.whole.sourceCount)
        assertNull(plan.whole.sourceKinds)
        assertNull(plan.whole.contextBytes)
        val inspectOnlySection = plan.sections[1]
        assertEquals("within_limits", inspectOnlySection.capacity.state)
        assertFalse(inspectOnlySection.capacity.canDraft)
        assertEquals(1, inspectOnlySection.capacity.sourceCount)
        assertEquals(mapOf("editorial" to 1), inspectOnlySection.capacity.sourceKinds)
        rule.onNodeWithTag("memory-book-plan-whole-smaller").assertExists()
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-plan-sections-toggle").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-plan-section-1").performScrollTo().assertExists()
        rule.onNodeWithText(
            if (language == "zh") "可查看，暂不能整理" else "Available to inspect; drafting unavailable",
        ).assertExists()
        rule.onNodeWithText("2. 野餐回忆").assertExists()
        assertTrue(rule.onAllNodesWithText(
            if (language == "zh") "1. 1 · 家人记得的片段 · 1 个片段"
            else "1. 1 · 家人记得的片段 · 1 moment",
        ).fetchSemanticsNodes().isNotEmpty())
        assertTrue(rule.onAllNodesWithText(
            if (language == "zh") "1 条资料 · 整理资料 1" else "1 source · editorial 1",
        ).fetchSemanticsNodes().isNotEmpty())
        rule.onNodeWithTag("memory-book-plan-section-read-1").performScrollTo().assertIsEnabled()
        captureDisplay("memory-community-memoir-plan-$language-expanded-font150")

        val selectedBook = store.state.value.memoryBooks!!.selectedBook!!
        val planReads = community.planReads
        readTrace.clear()
        rule.onNodeWithTag("memory-book-plan-section-read-1").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.state.value.memoryBooks?.story?.id == bookStory2 &&
                store.state.value.memoryBooks?.readerBusy == false
        }
        assertEquals(listOf("parent:$bookId:$narrativeBookRevision", "child:$bookStory2:$narrativeStoryRevision"), readTrace)
        rule.onNodeWithTag("memory-book-plan-section-read-1").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-story-title").performScrollTo().assertTextEquals("野餐回忆")
        rule.onNodeWithTag("memory-book-chapter-title").performScrollTo().assertTextEquals("1 · 家人记得的片段")
        rule.onNodeWithTag("memory-book-story-text").performScrollTo().assertTextEquals("奶奶带我们走进花园。")
        captureDisplay("memory-community-memoir-plan-$language-story-font150")

        val retained = store.memoryBookNarrativeState.value
        assertSame(plan, retained.plan)
        assertEquals(instructions, retained.instructions)
        assertEquals(MemoryBookNarrativeForm.ESSAY, retained.form)
        assertSame(selectedBook, store.state.value.memoryBooks?.selectedBook)
        rule.onNodeWithTag("memory-book-narrative-instructions").performScrollTo().assertTextContains(instructions)
        rule.onNodeWithTag("memory-book-narrative-form-open").assertTextEquals(
            if (language == "zh") "讲述方式 · 家庭散文" else "Storytelling form · Reflective essay",
        )
        rule.onNodeWithTag("memory-book-narrative-request").performScrollTo().assertIsNotEnabled()
        assertEquals(planReads, community.planReads)
        assertEquals(0, community.narrativeSent)
        assertEquals(0, community.textSent)
        assertEquals(0, community.audioSent)
        assertEquals(0, community.chatSent)
        assertNull(retained.pendingRequest)
        assertNull(retained.job)
    }

    @Test fun memoirEditorialContextNeedsExplicitSelectionAndSendChinese() = memoirEditorialContextJourney("zh")
    @Test fun memoirEditorialContextNeedsExplicitSelectionAndSendEnglish() = memoirEditorialContextJourney("en")

    private fun memoirEditorialContextJourney(language: String) {
        val community = CommunityApi().apply { planFailure = ApiFailure(FailureKind.HTTP, 503) }
        val store = ConnectedStore(StoryApi(), scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = language)
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-entry-0").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.story?.id == id }
        rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-chat-start").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.conversationId != null }
        rule.onNodeWithTag("memory-book-chat-editorial-context").performScrollTo().assertIsOff()
        assertEquals(0, community.planReads)
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().performTextInput("请把开篇和这段家人回忆联系起来。")
        rule.onNodeWithTag("memory-book-chat-editorial-context").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.editorialContext == MemoryBookChatEditorialContext.UNAVAILABLE }
        rule.onNodeWithTag("memory-book-chat-editorial-context").assertIsOff()
        rule.onNodeWithTag("memory-book-chat-editorial-status").assert(SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite))
        rule.onNodeWithTag("memory-book-chat-send").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-chat-basic-context").performScrollTo().assertExists()
        captureDisplay("memoir-editorial-context-$language-unavailable-font150")
        rule.onNodeWithTag("memory-book-chat-basic-context").performClick()
        rule.onNodeWithTag("memory-book-chat-send").performScrollTo().assertIsEnabled()
        rule.runOnIdle { community.planFailure = null }
        rule.onNodeWithTag("memory-book-chat-editorial-context").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.editorialContext == MemoryBookChatEditorialContext.READY }
        rule.onNodeWithTag("memory-book-chat-editorial-context").assertIsOn()
        rule.onNodeWithTag("memory-book-chat-editorial-status").performScrollTo().assertExists()
        captureDisplay("memoir-editorial-context-$language-ready-font150")
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().assertTextContains("请把开篇和这段家人回忆联系起来。")
        assertEquals(0, community.chatSent)
        rule.onNodeWithTag("memory-book-chat-send").performScrollTo().performClick()
        rule.waitUntil(5000) { community.chatSent == 1 }
        assertEquals(listOf(true), community.sentEditorialChoices)
        assertEquals(2, community.planReads)
    }

    @Test fun currentMemoirChapterQuestionWaitsForExplicitSendChinese() = memoirChapterDiscussionJourney("zh")
    @Test fun currentMemoirChapterQuestionWaitsForExplicitSendEnglish() = memoirChapterDiscussionJourney("en")

    private fun memoirChapterDiscussionJourney(language: String) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val resolver = instrumentation.targetContext.contentResolver
        val setting = "show_ime_with_hard_keyboard"
        val original = android.provider.Settings.Secure.getString(resolver, setting)
        fun configureKeyboard(value: String?) {
            val command = if (value == null) "settings delete secure $setting"
                else "settings put secure $setting $value"
            instrumentation.uiAutomation.executeShellCommand(command).use { descriptor ->
                android.os.ParcelFileDescriptor.AutoCloseInputStream(descriptor).use { it.readBytes() }
            }
        }
        // The reused emulator has a hardware keyboard. Exercise touch-screen
        // keyboard layout deterministically, then restore its previous setting.
        configureKeyboard("1")
        try { memoirChapterDiscussionWithSoftwareKeyboard(language) }
        finally { configureKeyboard(original) }
    }

    private fun memoirChapterDiscussionWithSoftwareKeyboard(language: String) {
        val community = CommunityApi().apply { largeNarrativeFixture = true }
        val store = ConnectedStore(StoryApi(largeNarrativeFixture = true), scope,
            memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = language)
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-entry-0").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.story != null }
        rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-chat-start").performScrollTo().performClick()
        rule.waitUntil(5000) { store.memoryBookChapterDiscussionContext() != null }
        val initial = store.memoryBookChapterDiscussionContext()!!
        val action = rule.onNodeWithTag("memory-book-chat-discuss-chapter")
        action.performScrollTo().assertIsEnabled()
        action.assertTextEquals(if (language == "zh") "聊聊正在阅读的篇章" else "Discuss this chapter")
        captureDisplay("memoir-chapter-question-$language-action-font150")
        action.performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.draft?.isNotBlank() == true }
        val firstDraft = store.state.value.memoryBooks!!.companion!!.draft
        assertEquals(memoryBookChapterDiscussionQuestion(initial, language == "zh"), firstDraft)
        rule.onNodeWithTag("memory-book-chat-input").assertTextContains(firstDraft)
        // Touch editing explicitly opens the IME; programmatic draft insertion
        // may retain focus without opening a software keyboard on every device.
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().performClick()
        try {
            rule.waitUntil(5000) {
                rule.onAllNodesWithTag("memory-books-ime-visible").fetchSemanticsNodes().isNotEmpty()
            }
        } catch (failure: androidx.compose.ui.test.ComposeTimeoutException) {
            captureDisplay("memoir-chapter-question-$language-keyboard-timeout-font150")
            throw failure
        }
        captureDisplay("memoir-chapter-question-$language-keyboard-insets-font150")
        rule.waitUntil(5000) {
            rule.onNodeWithTag("memory-books-heading").isDisplayed() &&
                rule.onNodeWithTag("memory-books-close").isDisplayed()
        }
        rule.onNodeWithTag("memory-books-heading").assertIsDisplayed()
        rule.onNodeWithTag("memory-books-close").assertIsDisplayed()
        rule.waitUntil(5000) {
            val input = rule.onNodeWithTag("memory-book-chat-input").getUnclippedBoundsInRoot()
            val viewport = rule.onNodeWithTag("memory-book-reader-scroll").getUnclippedBoundsInRoot()
            input.top >= viewport.top && input.bottom <= viewport.bottom
        }
        rule.onNodeWithTag("memory-book-next-chapter").assertDoesNotExist()
        assertEquals(0, community.chatSent)
        action.performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().performTextReplacement("My unfinished memory")
        action.performScrollTo().assertIsNotEnabled()
        assertEquals("My unfinished memory", store.state.value.memoryBooks!!.companion!!.draft)
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().performTextClearance()
        rule.runOnIdle { store.loadMemoryBookChapter(1) }
        rule.waitUntil(5000) { store.memoryBookChapterDiscussionContext()?.chapterIndex == 1 }
        action.performScrollTo().assertIsEnabled().performClick()
        val second = store.memoryBookChapterDiscussionContext()!!
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.draft ==
            memoryBookChapterDiscussionQuestion(second, language == "zh") }
        assertEquals(initial.conversationId, second.conversationId)
        assertEquals(0, community.chatSent)
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo()
        captureDisplay("memoir-chapter-question-$language-draft-font150")
        InstrumentationRegistry.getInstrumentation().uiAutomation.performGlobalAction(
            android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        rule.waitUntil(5000) {
            rule.onAllNodesWithTag("memory-books-ime-visible").fetchSemanticsNodes().isEmpty()
        }
        rule.onNodeWithTag("memory-book-next-chapter").assertExists()
        rule.onNodeWithTag("memory-books-back").assertExists()
        rule.onNodeWithTag("memory-book-chat-send").performScrollTo().assertIsEnabled().performClick()
        rule.waitUntil(5000) { community.chatSent == 1 }
        assertEquals(memoryBookChapterDiscussionQuestion(second, language == "zh"), community.sentChatText)
        // The synthetic server returns a completed reply immediately; the empty composer is reusable.
        action.performScrollTo().assertIsEnabled()
        assertEquals(1, community.chatSent)
    }

    @Test fun memoirChatKeepsItsBookThreadAndEditableDraftAcrossStories() {
        val community = CommunityApi()
        val storyApi = StoryApi(voiceEnabled = true)
        val replySpeech = ReplySpeechFactory()
        val store = ConnectedStore(storyApi, scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, previewFontScale.floatValue)) {
                CompositionLocalProvider(LocalChapterSpeechAdapterFactory provides replySpeech,
                    LocalChapterAudioFocusFactory provides SyntheticAudioFocusFactory()) {
                    ConnectedApp(store, initialLanguage = "zh")
                }
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-entry-0").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.story?.id == id }
        rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.capabilities?.generationEnabled == true }
        rule.runOnIdle { previewFontScale.floatValue = 1.5f }
        rule.waitForIdle()
        rule.runOnIdle {
            val reading = store.state.value.memoryBooks
            assertTrue("memoir chat should be enabled: ${reading?.capabilities}", reading?.capabilities?.generationEnabled == true)
            assertNotNull("memoir chat state missing: $reading", reading?.companion)
            assertEquals(null, reading?.companion?.conversationId)
        }
        rule.onNodeWithTag("memory-book-companion").assertExists()
        rule.onNodeWithTag("memory-book-chat-start").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.conversationId != null }
        rule.runOnIdle {
            assertEquals("new book conversation has no first-message preview before a user turn", "",
                store.state.value.memoryBooks?.companion?.conversations?.items?.first()?.firstMessagePreview)
        }
        rule.onNodeWithText("Synthetic first user message", substring = true).assertDoesNotExist()
        rule.onNodeWithText("最新消息").assertExists()
        rule.onNodeWithTag("memory-book-chat-context-window").performScrollTo().assertIsDisplayed()
        captureBooks("memoir-chat-context-window-font150")
        captureBooks("memoir-chat-latest-font150")
        rule.onNodeWithTag("memory-book-chat-next").performScrollTo().assertTextEquals("更早的消息").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.turns?.page == 2 }
        rule.onNodeWithText("更早的消息 · 第 2 页").assertExists()
        captureBooks("memoir-chat-older-font150")
        rule.onNodeWithTag("memory-book-chat-previous").performScrollTo().assertTextEquals("较新的消息").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.turns?.page == 1 }
        captureBooks("memoir-chat-latest-return-font150")
        rule.runOnIdle { assertEquals("history navigation must not submit a chat turn", 0, community.chatSent) }
        rule.runOnIdle {
            assertEquals("book", community.lastConversationTargetType)
            assertEquals(bookId, community.lastConversationTargetId)
        }
        rule.onNodeWithTag("memory-book-chat-thread-0").assertExists()
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().performTextInput("请介绍一下这段回忆。")
        val memoirSendButton = rule.onNodeWithTag("memory-book-chat-send")
        memoirSendButton.performScrollTo().assertIsDisplayed().assertIsEnabled()
        rule.waitForIdle()
        captureBooks("memoir-chat-send-font150")
        memoirSendButton.performClick()
        try {
            rule.waitUntil(5000) { community.chatSent == 1 }
        } catch (e: androidx.compose.ui.test.ComposeTimeoutException) {
            val reading = store.state.value.memoryBooks
            val chat = reading?.companion
            throw AssertionError("memoir chat submission diagnostic: sent=${community.chatSent}, " +
                "busy=${chat?.busy}, draft=${chat?.draft}, pending=${chat?.pendingTurn}, " +
                "context=${chat?.editorialContext}, turns=${chat?.turns}, job=${chat?.job}, " +
                "readerBusy=${reading?.readerBusy}, failure=${chat?.failure}", e)
        }
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.job?.state == "ready" }
        val memoirBubbleTurnId = "77777777-7777-7777-7777-777777777777"
        rule.onNodeWithTag("memory-book-chat-turn-reply").assert(hasAnyAncestor(hasTestTag("memory-book-chat-assistant-bubble-$memoirBubbleTurnId")))
        rule.onNodeWithTag("memory-book-chat-user-bubble-$memoirBubbleTurnId").performScrollTo()
        captureBooks("memoir-chat-user-bubble-font150")
        rule.onNodeWithTag("memory-book-chat-assistant-bubble-$memoirBubbleTurnId").performScrollTo()
        captureBooks("memoir-chat-message-bubbles-font150")
        rule.onNodeWithTag("memory-book-chat-followup-1-question-0").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-book-chat-followup-1-sources-toggle").performScrollTo().performClick()
        rule.onNodeWithText("回忆册说明", substring = true).assertExists()
        rule.onNodeWithText("回忆册说明", substring = true).performScrollTo()
        rule.onNodeWithText("家人提供的回忆", substring = true).assertExists()
        rule.onNodeWithText("AI 观察 · 需核实", substring = true).assertExists()
        rule.onNodeWithText("故事整理文字", substring = true).assertExists()
        rule.onAllNodesWithText("来源尚未加载", substring = true).assertCountEquals(2)
        rule.onNodeWithText(contributionId).assertDoesNotExist()
        captureBooks("memoir-chat-followups-font150")
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().performTextInput("字".repeat(1400))
        rule.onNodeWithTag("memory-book-chat-draft-limit", useUnmergedTree = true).performScrollTo().assertExists()
        rule.onNodeWithTag("memory-book-chat-input").assert(SemanticsMatcher.keyIsDefined(SemanticsProperties.Error))
        rule.onNodeWithTag("memory-book-chat-draft-limit", useUnmergedTree = true).assert(SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite))
        rule.onNodeWithTag("memory-book-chat-send").assertIsNotEnabled()
        rule.runOnIdle { assertEquals("over-limit memoir words are not sent", 1, community.chatSent) }
        captureBooks("memoir-chat-field-error-font150")
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().performTextClearance()
        rule.onNodeWithTag("memory-book-chat-draft-limit", useUnmergedTree = true).assertDoesNotExist()
        rule.onNodeWithTag("memory-book-chat-input").assert(SemanticsMatcher.keyNotDefined(SemanticsProperties.Error))
        val memoirFollowup = "那天后来发生了什么？"
        rule.onNodeWithTag("memory-book-chat-followup-1-question-0").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().assertTextContains(memoirFollowup)
        rule.runOnIdle { assertEquals("choosing a memoir follow-up only fills the composer", 1, community.chatSent) }
        rule.onNodeWithTag("memory-book-chat-send").performScrollTo().performClick()
        rule.waitUntil(5000) { community.chatSent == 2 && community.sentChatText == memoirFollowup }
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().performTextInput("请继续讲这本回忆册")
        rule.onNodeWithTag("memory-book-chat-new").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.conversations?.items?.size == 2 }
        val bookConversationRows = store.state.value.memoryBooks!!.companion!!.conversations!!.items
        assertTrue("normal conversation-list refresh includes the retained first user turn",
            bookConversationRows.any { it.firstMessagePreview == "请介绍一下这段回忆。" })
        rule.onNodeWithText("请介绍一下这段回忆。").assertExists()
        rule.runOnIdle { assertEquals("", store.state.value.memoryBooks?.companion?.draft) }
        rule.onNodeWithTag("memory-book-chat-thread-1").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().assertTextContains("请继续讲这本回忆册")
        // Closing the composer clears focus/IME while leaving its draft in the memoir chat state.
        rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-next").assertIsDisplayed().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.story?.id == bookStory2 }
        rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().assertTextContains("请继续讲这本回忆册")
        rule.onNodeWithTag("memory-book-chat-enable-dictation").performScrollTo().performClick()
        rule.onNodeWithTag("memory-dictation-record").assertTextEquals("录音说消息")
        rule.onNodeWithText("录音→核对文字→加入消息草稿→由你发送。录音不会保留；对话和转写记录保留30天。")
            .assertExists()
        val dictation = store.memoryBookChatDictation()!!
        rule.waitUntil(5000) { dictation.state.value.capabilities?.transcribe == true }
        assertNotNull(dictation.beginRecording())
        rule.onNodeWithTag("memory-book-chat-new").performScrollTo().assertIsNotEnabled()
        dictation.stopRecording(syntheticMemoryAudioWav(1000))
        rule.waitUntil(5000) { dictation.state.value.transcript == "语音原稿" }
        rule.onNodeWithTag("memory-dictation-insert").assertTextEquals("加入消息草稿")
        rule.onNodeWithTag("memory-book-chat-new").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-dictation-transcript").performScrollTo().performTextReplacement("修改后的口述")
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().performClick()
        rule.runOnIdle { assertTrue("book draft=${store.state.value.memoryBooks?.companion?.draft}", store.state.value.memoryBooks?.companion?.draft.orEmpty().contains("修改后的口述")) }
        rule.onNodeWithTag("memory-book-chat-send").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.job?.state == "ready" }
        assertTrue(community.sentChatText.orEmpty().contains("修改后的口述"))
        rule.onNodeWithTag("memory-book-chat-turn-reply").performScrollTo().assertTextEquals("第一行\n第二行")
        rule.onNodeWithTag("memory-book-chat-reply").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-chat-user-speaker").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-book-chat-assistant-speaker").assertExists()
        assertTrue("memoir reply speech must not autoplay", replySpeech.engines.isEmpty())
        val memoirReadTag = "memory-book-chat-reply-reading-77777777-7777-7777-7777-777777777777-toggle"
        rule.onNodeWithTag(memoirReadTag).performScrollTo().performClick()
        rule.waitUntil(5000) { replySpeech.engines.singleOrNull()?.utterances?.isNotEmpty() == true }
        val firstMemoirEngine = replySpeech.engines.single()
        assertEquals("第一行\n第二行", firstMemoirEngine.utterances.single().text)
        assertEquals(0, storyApi.assistantSpeechRequests)
        rule.onNodeWithTag("memory-book-previous").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.story?.id == id }
        rule.waitForIdle()
        assertTrue("changing memoir story must stop its scoped reply reader", firstMemoirEngine.stopped > 0)
        val staleMemoirDone = firstMemoirEngine.utterances.single()
        Thread { staleMemoirDone.done(staleMemoirDone.id) }.apply { start(); join() }
        rule.waitForIdle()
        assertEquals("late callback after story switch must not start another chunk", 1, firstMemoirEngine.utterances.size)
        captureBooks("memoir-chat-normal")
        rule.runOnIdle { previewFontScale.floatValue = 1.5f }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-chat-title").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-book-chat-thread-0").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-book-chat-thread-1").performScrollTo().assertExists()
        captureBooks("memoir-chat-thread-selector-font150")
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-dictation-record").performScrollTo().assertExists()
        rule.onNodeWithTag("memory-book-chat-send").performScrollTo().assertExists()
        captureBooks("memoir-chat-font150")
        rule.onNodeWithTag(memoirReadTag).performScrollTo().assertExists()
        captureBooks("memoir-chat-reply-reading-font150")

        // The transcript must remain editable when adding it would exceed the wire limit.
        store.updateMemoryBookChatDraft("家".repeat(1300))
        val oversizedDictation = store.memoryBookChatDictation()!!
        rule.waitUntil(5000) { oversizedDictation.state.value.capabilities?.transcribe == true }
        assertNotNull(oversizedDictation.beginRecording())
        oversizedDictation.stopRecording(syntheticMemoryAudioWav(1000))
        rule.waitUntil(5000) { oversizedDictation.state.value.transcript == "语音原稿" }
        oversizedDictation.updateTranscript("字".repeat(100))
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().performClick()
        rule.onNodeWithTag("memory-book-chat-transcript-limit").performScrollTo().assertExists()
        rule.runOnIdle {
            assertEquals("字".repeat(100), oversizedDictation.state.value.transcript)
            assertEquals("家".repeat(1300), store.state.value.memoryBooks?.companion?.draft)
        }
        val latestMemoirDraft = "稍后补充的草稿"
        val latestEditedTranscript = "后来核对的口述"
        val sentBeforeAdd = community.chatSent
        store.updateMemoryBookChatDraft(latestMemoirDraft)
        oversizedDictation.updateTranscript(latestEditedTranscript)
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().performClick()
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-chat-transcript-limit").assertDoesNotExist()
        rule.runOnIdle {
            assertEquals("Add reads the current composer draft", "$latestMemoirDraft\n$latestEditedTranscript",
                store.state.value.memoryBooks?.companion?.draft)
            assertNull("successful Add consumes the reviewed transcript", oversizedDictation.state.value.transcript)
            assertEquals("Add does not submit a chat request", sentBeforeAdd, community.chatSent)
        }
        rule.onNodeWithTag(memoirReadTag).performScrollTo().performClick()
        rule.waitUntil(5000) { replySpeech.engines.size == 2 && replySpeech.engines.last().utterances.isNotEmpty() }
        assertEquals("第一行\n第二行", replySpeech.engines.last().utterances.single().text)
        assertEquals(0, storyApi.assistantSpeechRequests)
        val activeAtClose = replySpeech.engines.last()
        store.closeMemoryBook()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion == null }
        rule.waitForIdle()
        assertTrue("closing memoir reader must stop its scoped reply reader", activeAtClose.stopped > 0)
    }

    @Test fun explicitReaderCloseCanKeepOrDiscardUnsentMemoirDraft() {
        val community = CommunityApi()
        val store = ConnectedStore(StoryApi(), scope, memoryCommunityApi = community, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides androidx.compose.ui.unit.Density(base.density, previewFontScale.floatValue)) {
                ConnectedApp(store, initialLanguage = "zh")
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.onNodeWithTag("memory-book-$bookId").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedBook != null }
        rule.onNodeWithTag("memory-book-entry-0").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.story?.id == id }
        rule.waitUntil(5000) {
            val reading = store.state.value.memoryBooks
            reading?.capabilities?.generationEnabled == true && reading.companion != null
        }
        rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
        if (store.state.value.memoryBooks?.companion?.conversationId == null) {
            rule.onNodeWithTag("memory-book-companion").assertExists()
            rule.onNodeWithTag("memory-book-chat-start").assertExists()
            rule.onNodeWithTag("memory-book-chat-start").performScrollTo().performClick()
        }
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.conversationId != null }
        rule.runOnIdle { previewFontScale.floatValue = 1.5f }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().performTextInput("留给第一段对话的草稿")
        val firstConversation = store.state.value.memoryBooks!!.companion!!.conversationId!!
        rule.runOnIdle {
            assertEquals("留给第一段对话的草稿", store.state.value.memoryBooks?.companion?.threadDrafts?.get(firstConversation))
        }
        rule.onNodeWithTag("memory-book-chat-new").performScrollTo().performClick()
        rule.waitUntil(5000) {
            val chat = store.state.value.memoryBooks?.companion
            chat?.conversationId != null && chat.conversationId != firstConversation
        }
        rule.runOnIdle {
            val chat = store.state.value.memoryBooks?.companion
            assertEquals("a new thread starts with an empty composer", "", chat?.draft)
            assertEquals("the inactive thread keeps its volatile draft", "留给第一段对话的草稿", chat?.threadDrafts?.get(firstConversation))
        }

        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-book-discard-dialog").assertExists()
        captureDisplay("memoir-inactive-thread-draft-warning-font150")
        rule.onNodeWithTag("memory-book-discard-cancel").performClick()
        rule.onNodeWithTag("memory-book-discard-dialog").assertDoesNotExist()
        rule.runOnIdle {
            val chat = store.state.value.memoryBooks?.companion
            assertEquals("cancel keeps the blank thread selected", "", chat?.draft)
            assertEquals("cancel preserves the inactive draft", "留给第一段对话的草稿", chat?.threadDrafts?.get(firstConversation))
            assertEquals(bookId, store.state.value.memoryBooks?.selectedBook?.id)
        }
        val firstIndex = store.state.value.memoryBooks!!.companion!!.conversations!!.items.indexOfFirst { it.id == firstConversation }
        assertTrue("original conversation remains in recent thread list", firstIndex >= 0)
        rule.onNodeWithTag("memory-book-chat-thread-$firstIndex").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.companion?.conversationId == firstConversation }
        rule.runOnIdle {
            assertEquals("returning to A restores its draft", "留给第一段对话的草稿", store.state.value.memoryBooks?.companion?.draft)
        }
        rule.onNodeWithTag("memory-book-chat-input").performScrollTo().assertTextContains("留给第一段对话的草稿")
        captureBooks("memoir-inactive-thread-draft-restored-font150")

        rule.onNodeWithTag("memory-books-close").performClick()
        rule.onNodeWithTag("memory-book-discard-dialog").assertExists()
        rule.onNodeWithTag("memory-book-discard-confirm").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks == null }
        assertEquals("no chat message was sent during leave recovery", 0, community.chatSent)
    }

    @Test fun scopeChangeAndBackgroundDiscardLateRecordingResults() {
        val factory = DelayedCaptureFactory()
        val lifecycleOwner = SyntheticLifecycleOwner()
        var storyId by androidx.compose.runtime.mutableStateOf("story-one")
        var submissions = 0
        rule.setContent {
            CompositionLocalProvider(
                LocalMemoryContributionCaptureFactory provides factory,
                androidx.compose.ui.platform.LocalLifecycleOwner provides lifecycleOwner,
            ) {
                androidx.compose.foundation.layout.Column {
                    MemoryContributionAudioInput("family", storyId, true, "zh", false, "家人", true,
                        onActivityChanged = {}, onAudio = { wav, _, _, _ ->
                        submissions++
                        wav.fill(0)
                    })
                    androidx.compose.material3.TextButton(onClick = { storyId = "story-two" }) { androidx.compose.material3.Text("Switch story") }
                }
            }
        }
        rule.runOnIdle { lifecycleOwner.lifecycle.currentState = androidx.lifecycle.Lifecycle.State.RESUMED }

        rule.onNodeWithTag("memory-audio-record").performClick()
        rule.onNodeWithTag("memory-audio-recording").assertExists()
        val first = factory.captures.single()
        assertTrue("first capture worker did not start", first.awaitRecordingStarted())
        rule.runOnIdle { storyId = "story-two" }
        rule.onNodeWithTag("memory-audio-record").assertExists()
        first.completeLate()
        rule.waitUntil(5000) { first.returned?.all { it == 0.toByte() } == true }
        rule.onNodeWithTag("memory-audio-draft").assertDoesNotExist()
        assertEquals(0, submissions)

        rule.onNodeWithTag("memory-audio-record").performClick()
        rule.onNodeWithTag("memory-audio-recording").assertExists()
        val backgrounded = factory.captures.last()
        assertTrue("backgrounded capture worker did not start", backgrounded.awaitRecordingStarted())
        rule.runOnIdle { lifecycleOwner.lifecycle.currentState = androidx.lifecycle.Lifecycle.State.CREATED }
        backgrounded.completeLate()
        rule.runOnIdle { lifecycleOwner.lifecycle.currentState = androidx.lifecycle.Lifecycle.State.RESUMED }
        rule.waitUntil(5000) { backgrounded.returned?.all { it == 0.toByte() } == true }
        assertTrue("late backgrounded result was not zeroed", backgrounded.returned?.all { it == 0.toByte() } == true)
        rule.onNodeWithTag("memory-audio-draft").assertDoesNotExist()
        assertEquals(0, submissions)
    }
}
