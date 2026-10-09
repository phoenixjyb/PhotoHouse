package dev.photohouse.connected

import androidx.compose.ui.test.*
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.content.ContentValues
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import java.io.File
import java.io.FileOutputStream
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SavedMemoryStoriesUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val id = "11111111-1111-1111-1111-111111111111"
    private val textContributionId = "33333333-3333-3333-3333-333333333333"
    private val audioContributionId = "44444444-4444-4444-4444-444444444444"
    @After fun close() { scope.cancel() }

    private fun asset(id: String) = Asset(id, "image", 800, 600, null, "2024-05-01", "/assets/$id/thumbnail?library=family",
        if (id == "1") DateHint("2024-05-01", "filename") else DateHint("2024-05-02", "received"))
    private val summary = SavedMemoryStorySummary(id, "Garden day", "everyday", "zh", 3, "1", 2, 2, 1720000000, false)

    private inner class Api(private val storyId: String, private val summary: SavedMemoryStorySummary) : PhotoHouseApi, MemoryCommunityApi {
        private val syntheticJpeg by lazy {
            val bitmap = Bitmap.createBitmap(480, 300, Bitmap.Config.RGB_565)
            val canvas = Canvas(bitmap)
            canvas.drawColor(Color.rgb(214, 226, 200))
            val paint = Paint(Paint.ANTI_ALIAS_FLAG)
            paint.color = Color.rgb(117, 153, 126); canvas.drawRect(0f, 150f, 480f, 300f, paint)
            paint.color = Color.rgb(80, 119, 98); canvas.drawCircle(95f, 125f, 76f, paint); canvas.drawCircle(360f, 145f, 95f, paint)
            paint.color = Color.rgb(242, 211, 147); canvas.drawCircle(250f, 94f, 42f, paint)
            paint.color = Color.rgb(246, 239, 215); paint.textSize = 28f; canvas.drawText("FAMILY GARDEN", 24f, 270f, paint)
            java.io.ByteArrayOutputStream().use { out -> bitmap.compress(Bitmap.CompressFormat.JPEG, 88, out); bitmap.recycle(); out.toByteArray() }
        }
        override val protectedNativeV2Enabled = true
        var detailError: Exception? = null
        var detailGate: CompletableDeferred<Unit>? = null
        var detailStarted = false
        var chapterTitles: List<String>? = null
        var detailReads = 0
        val listRequests = mutableListOf<Pair<Int, String?>>()
        var failTheme: String? = null
        var yearThemeGate: CompletableDeferred<Unit>? = null
        var contributionReferenceReads = 0
        val contributionDetailReads = mutableListOf<String>()
        private var savedRevision = summary.revision
        private var linkedText = true
        private var linkedAudio = true
        val longFamilyText = "奶奶说那天的风很轻，我们沿着花园小路慢慢走，看见各色花朵在阳光下摇曳。".repeat(24)
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int, theme: String?): SavedMemoryStoryPage {
            listRequests += page to theme
            if (theme == "year_in_review") {
                val gate = yearThemeGate
                yearThemeGate = null
                gate?.await()
            }
            if (theme != null && theme == failTheme) throw ApiFailure(FailureKind.HTTP, 400)
            val items = if (page == 1 && theme != "growing_up") listOf(summary.copy(theme = theme ?: summary.theme)) else emptyList()
            return SavedMemoryStoryPage(library, page, 8, page == 1, false, items)
        }
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("account", "+8612345678", listOf(Membership("family", "approved", if (summary.canEdit) "owner" else "viewer", 1, null, 0, true)))
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun capabilities(token: Bearer, library: String) =
            """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
        override suspend fun listContributions(token: Bearer, library: String, storyId: String, page: Int): ByteArray {
            val items = listOf(
                """{"id":"$textContributionId","story_id":"$storyId","author_id":"22222222-2222-2222-2222-222222222222","kind":"text","language":"zh","byline":"家人","sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","duration_ms":null,"chapter_id":null,"base_story_revision":"2","state":"accepted","created_at":1720000000,"text":"原始家人回忆","processing_consent":true}""",
                """{"id":"$audioContributionId","story_id":"$storyId","author_id":"22222222-2222-2222-2222-222222222222","kind":"audio","language":"zh","byline":"家人","sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","duration_ms":5000,"chapter_id":"chapter-1","base_story_revision":"2","state":"accepted","created_at":1720000000,"text":null,"processing_consent":true}""",
            ).joinToString(",")
            return """{"version":1,"story_id":"$storyId","page":$page,"page_size":16,"has_more":false,"can_review":false,"can_delete":false,"items":[$items]}""".toByteArray()
        }
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 2, false, listOf(asset("1"), asset("2")))
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, asset(assetId))
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = syntheticJpeg.copyOf()
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 1, byteArrayOf(0))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf(1)
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int) = SavedMemoryStoryPage(library, page, 8, false, false, if (page == 1) listOf(summary) else emptyList())
        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            detailStarted = true
            detailReads++
            detailGate?.await()
            detailError?.let { throw it }
            val familyEvidence = MemoryStoryEvidence("family-11111111-1111-1111-1111-111111111111", "family", "午后记忆", "<b>奶奶</b>带我们走进花园。", 1)
            val aiEvidence = MemoryStoryEvidence("caption-1", "ai", "", "画面里有一排黄色的花。")
            val siblingEvidence = MemoryStoryEvidence("caption-2", "family", "", "这条只属于第二章。")
            return SavedMemoryStory(
                storyId, library, savedRevision.coerceAtLeast(revision), 1710000000, 1720000000, summary.canEdit, "a".repeat(64), "Garden day", "everyday", "zh",
                listOf(MemoryStoryAsset(asset("1"), listOf(familyEvidence, aiEvidence)), MemoryStoryAsset(asset("2"), listOf(siblingEvidence))),
                listOf(SavedMemoryStoryChapter("chapter-1", chapterTitles?.getOrNull(0) ?: "The first visit", "奶奶带我们走进花园。", listOf("1"), listOf(aiEvidence.id, familyEvidence.id)),
                    SavedMemoryStoryChapter("chapter-2", chapterTitles?.getOrNull(1) ?: "After lunch", "我们在花园里继续聊天。", listOf("2"), listOf(siblingEvidence.id))), emptyList())
        }
        override suspend fun savedMemoryStoryContributionReferences(
            token: Bearer, library: String, storyId: String, revision: Long, chapterIds: List<String>,
        ) = SavedMemoryStoryContributionReferences(storyId, library, revision, listOf(
            SavedMemoryChapterContributionReferences("chapter-1", listOfNotNull(textContributionId.takeIf { linkedText }, audioContributionId.takeIf { linkedAudio })),
            SavedMemoryChapterContributionReferences("chapter-2", emptyList()),
        )).also { contributionReferenceReads++ }
        override suspend fun saveMemoryStoryContributionReferences(
            token: Bearer, library: String, mutation: SavedMemoryStoryContributionReferencesMutation,
        ): SavedMemoryStory {
            savedRevision = mutation.revision + 1
            linkedText = mutation.contributionRefsJson.contains(textContributionId)
            linkedAudio = mutation.contributionRefsJson.contains(audioContributionId)
            return savedMemoryStory(token, library, storyId, savedRevision)
        }
        override suspend fun savedMemoryContributionDetail(
            token: Bearer, library: String, storyId: String, contributionId: String,
        ): MemoryContributionDetail {
            contributionDetailReads += contributionId
            val audio = contributionId == audioContributionId
            val item = MemoryContribution(contributionId, storyId, "22222222-2222-2222-2222-222222222222",
                if (audio) "audio" else "text", "zh", if (audio) "录音署名乙" else "文本署名甲", "b".repeat(64), if (audio) 5000 else null,
                if (audio) "chapter-1" else null, if (audio) 1 else 2, "accepted", 1720000000,
                if (audio) null else longFamilyText, true)
            val derivation = if (audio) MemoryContributionDerivation(1, "ready", "这是已完成的家人录音转写。",
                "不应展示的润色稿", emptyList(), null, 1720000000, 1720000001) else null
            return MemoryContributionDetail(MemoryContributionReceipt(item, false, false), derivation)
        }
    }

    @Test fun chineseDraftReaderNavigatesAndReturnsThroughProtectedAssetDetail() {
        val api = Api(id, summary); val store = ConnectedStore(api, scope)
        rule.setContent { ConnectedApp(store, initialLanguage = "zh") }
        rule.runOnIdle { store.authenticate("+8612345678", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.covers?.isNotEmpty() == true }
        capture("saved-memory-stories", "saved-memory-shelf.png")
        rule.onNodeWithTag("saved-memory-draft-label").assertDoesNotExist()
        rule.onNodeWithText("已保存草稿 · 仍需检查").assertExists()
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail != null }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.frames?.containsKey("1") == true }
        rule.onNodeWithText("家人回忆").assertExists()
        rule.onNodeWithText("第 1/2 章").assertExists()
        rule.onNodeWithText("文件名日期 · 2024-05-01").assertExists()
        rule.onNodeWithText("查看本章素材来源").assertExists()
        rule.onNodeWithText("以下是本章引用的参考资料，不代表已核实事实。").assertDoesNotExist()
        rule.onNodeWithTag("saved-memory-sources-toggle").assertExists().performClick()
        rule.onNodeWithText("以下是本章引用的参考资料，不代表已核实事实。").assertExists()
        rule.onNodeWithTag("saved-memory-sources-text-caption-1").assertTextEquals("画面里有一排黄色的花。")
        rule.onNodeWithTag("saved-memory-sources-text-family-11111111-1111-1111-1111-111111111111").assertTextEquals("<b>奶奶</b>带我们走进花园。")
        rule.onNodeWithText("AI 观察 · 需核对").assertExists()
        rule.onNodeWithText("家人提供的文字").assertExists()
        captureToMediaStore("saved-memory-chapter-1-sources.png")
        rule.onNodeWithTag("saved-memory-next").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.selectedChapter == 1 }
        rule.onNodeWithTag("saved-memory-sources-toggle").assertExists()
        rule.onNodeWithTag("saved-memory-sources-text-caption-2").assertDoesNotExist()
        rule.onNodeWithTag("saved-memory-sources-toggle").performClick()
        rule.onNodeWithText("这条只属于第二章。").assertExists()
        captureToMediaStore("saved-memory-chapter-2-sources.png")
        rule.onNodeWithTag("saved-memory-back-list").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail == null }
        rule.onNodeWithTag("saved-memory-story-$id").assertExists()
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail != null }
        rule.onNodeWithTag("saved-memory-next").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.selectedChapter == 1 }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.frames?.containsKey("2") == true }
        rule.onNodeWithText("第 2/2 章").assertExists()
        rule.onNodeWithText("收到于 · 2024-05-02").assertExists()
        rule.onNodeWithTag("saved-memory-sources-toggle").assertExists()
        rule.onNodeWithTag("saved-memory-sources-text-caption-2").assertDoesNotExist()
        capture("saved-memory-stories", "saved-memory-chapter-2.png")
        rule.onNodeWithTag("saved-memory-frame-2").performScrollTo().performClick()
        rule.onNodeWithTag("saved-memory-open-2").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories == null && store.state.value.detail?.asset?.id == "2" }
        assertEquals("2", store.state.value.detail?.asset?.id)
        capture("connected-screen", "saved-memory-protected-asset.png")
        rule.onNodeWithText("返回照片").performClick()
        rule.waitUntil(5000) { store.state.value.detail == null && store.state.value.gallery != null }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-close").performClick()
        assertEquals(null, store.state.value.savedMemoryStories)
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail != null }
        rule.onNodeWithTag("saved-memory-sources-toggle").performClick()
        rule.onNodeWithTag("saved-memory-sources-text-family-11111111-1111-1111-1111-111111111111").assertExists()
        rule.runOnUiThread { store.logout() }
        rule.waitUntil(5000) { store.state.value.session == null && store.state.value.savedMemoryStories == null }
        rule.onNodeWithTag("saved-memory-sources-container").assertDoesNotExist()
    }

    @Test fun chapterDirectoryJumpsAndResetsInChineseAtLargeText() = chapterDirectoryJourney("zh")

    @Test fun chapterDirectoryJumpsAndResetsInEnglishAtLargeText() = chapterDirectoryJourney("en")

    private fun chapterDirectoryJourney(language: String) {
        val api = Api(id, summary)
        val titles = if (language == "zh") listOf("第一次和奶奶一起走进种满了不同颜色花朵的花园", "午饭后沿着小路慢慢散步并聊起以前一家人在这里留下的回忆")
            else listOf("Our first visit to the garden with grandmother and all the different flowers", "After lunch we walked along the garden path and remembered earlier family visits")
        api.chapterTitles = titles
        val store = ConnectedStore(api, scope)
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = language)
            }
        }
        rule.runOnIdle { store.authenticate("+8612345678", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.frames?.containsKey("1") == true }
        rule.onNodeWithTag("saved-memory-chapter-directory").assertDoesNotExist()
        rule.onNodeWithTag("saved-memory-chapter-directory-toggle").assertIsDisplayed().performClick()
        rule.onNodeWithTag("saved-memory-chapter-directory-0").performScrollTo().assertIsSelected().assertTextEquals("1. ${titles[0]}")
        captureToMediaStore("saved-memory-directory-$language-font150-${System.currentTimeMillis()}.png")
        rule.onNodeWithTag("saved-memory-chapter-directory-1").performScrollTo().assertIsNotSelected().assertTextEquals("2. ${titles[1]}").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.selectedChapter == 1 && store.state.value.savedMemoryStories?.frames?.containsKey("2") == true }
        rule.onNodeWithTag("saved-memory-chapter-directory").assertDoesNotExist()
        rule.onNodeWithTag("saved-memory-chapter-title").assertIsDisplayed().assertTextEquals(titles[1])
        assertEquals("A chapter jump uses the already authorized story", 1, api.detailReads)
        rule.onNodeWithTag("saved-memory-chapter-directory-toggle").performClick()
        rule.onNodeWithTag("saved-memory-chapter-directory-1").performScrollTo().assertIsSelected()
        rule.onNodeWithTag("saved-memory-chapter-directory-0").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.selectedChapter == 0 && store.state.value.savedMemoryStories?.frames?.containsKey("1") == true }
        rule.onNodeWithTag("saved-memory-chapter-directory").assertDoesNotExist()
        rule.onNodeWithTag("saved-memory-chapter-title").assertIsDisplayed().assertTextEquals(titles[0])
        rule.onNodeWithTag("saved-memory-chapter-directory-toggle").performClick()
        rule.onNodeWithTag("saved-memory-back-list").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail == null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail != null }
        rule.onNodeWithTag("saved-memory-chapter-directory").assertDoesNotExist()
        rule.onNodeWithTag("saved-memory-close").assertIsDisplayed().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories == null }
    }

    @Test fun themeShelfProvidesAllOnEmptyAndKeepsFilterAcrossPaginationAndRefresh() {
        val api = Api(id, summary); val store = ConnectedStore(api, scope)
        rule.setContent { ConnectedApp(store, initialLanguage = "zh") }
        rule.runOnIdle { store.authenticate("+8612345678", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-theme-all").assertIsSelected()
        rule.onNodeWithTag("saved-memory-theme-growing_up").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.theme == "growing_up" && !store.state.value.savedMemoryStories!!.busy }
        rule.onNodeWithTag("saved-memory-empty").assertExists()
        rule.onNodeWithTag("saved-memory-theme-empty-all").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.theme == null && !store.state.value.savedMemoryStories!!.busy }

        rule.onNodeWithTag("saved-memory-theme-trip").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.theme == "trip" && !store.state.value.savedMemoryStories!!.busy }
        assertEquals(1 to "trip", api.listRequests.last())
        captureToMediaStore("saved-memory-theme-normal.png")
        rule.waitForIdle()
        rule.onNodeWithTag("saved-memory-theme-trip").assertExists()
        captureToMediaStore("saved-memory-theme-font150.png")
        for (tag in listOf("saved-memory-theme-all", "saved-memory-theme-everyday", "saved-memory-theme-trip",
            "saved-memory-theme-growing_up", "saved-memory-theme-birthday", "saved-memory-theme-grandparents", "saved-memory-theme-year_in_review")) {
            rule.onNodeWithTag(tag).performScrollTo().assertExists()
        }

        rule.onNodeWithTag("saved-memory-next-page").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.page == 2 && !store.state.value.savedMemoryStories!!.busy }
        assertEquals(2 to "trip", api.listRequests.last())
        rule.onNodeWithTag("saved-memory-refresh").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.page == 1 && !store.state.value.savedMemoryStories!!.busy }
        assertEquals(1 to "trip", api.listRequests.last())
        api.failTheme = "trip"
        rule.onNodeWithTag("saved-memory-refresh").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.unavailable == true }
        assertEquals("trip", store.state.value.savedMemoryStories?.theme)
        rule.onNodeWithTag("saved-memory-theme-error-all").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.theme == null && !store.state.value.savedMemoryStories!!.busy }

        val yearThemeGate = CompletableDeferred<Unit>()
        api.yearThemeGate = yearThemeGate
        rule.onNodeWithTag("saved-memory-theme-year_in_review").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.theme == "year_in_review" && store.state.value.savedMemoryStories!!.busy }
        yearThemeGate.complete(Unit)
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.theme == "year_in_review" && !store.state.value.savedMemoryStories!!.busy }
        rule.onNodeWithTag("saved-memory-theme-year_in_review").assertIsDisplayed().assertIsSelected()
    }

    @Test fun longStoryShelfCardAdaptsAtLargeTextAndKeepsOpenAndCloseAvailable() {
        val longTitle = "我们第一次和奶奶一起在杭州西湖边的花园里种下了好多颜色不同的花"
        val longSummary = summary.copy(title = longTitle, itemCount = 12, chapterCount = 6)
        val api = Api(id, longSummary)
        val store = ConnectedStore(api, scope)
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val fontPercent = (android.provider.Settings.System.getFloat(context.contentResolver,
            android.provider.Settings.System.FONT_SCALE, 1f) * 100).toInt()
        rule.setContent { ConnectedApp(store, initialLanguage = "zh") }
        rule.runOnIdle { store.authenticate("+8612345678", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.covers?.isNotEmpty() == true }
        captureToMediaStore("saved-memory-story-shelf-long-title-font$fontPercent.png")
        val titleTag = "saved-memory-story-title-$id"
        val metaTag = "saved-memory-story-meta-$id"
        rule.onNodeWithTag("saved-memory-story-$id").performScrollTo().assertExists()
        rule.onNodeWithTag(titleTag, useUnmergedTree = true).assertIsDisplayed().assertTextEquals(longTitle)
        rule.onNodeWithTag(metaTag, useUnmergedTree = true).assertIsDisplayed().assertTextEquals("12 个片段 · 6 章")
        rule.onNodeWithTag("saved-memory-story-open-$id", useUnmergedTree = true).assertIsDisplayed()

        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail != null }
        rule.onNodeWithTag("saved-memory-close").assertIsDisplayed().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories == null }

        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.covers?.isNotEmpty() == true }
        rule.onNodeWithTag("saved-memory-story-$id").performScrollTo().assertExists()
        rule.onNodeWithTag(titleTag, useUnmergedTree = true).assertIsDisplayed().assertTextEquals(longTitle)
        rule.onNodeWithTag(metaTag, useUnmergedTree = true).assertIsDisplayed()
        rule.onNodeWithTag("saved-memory-story-open-$id", useUnmergedTree = true).assertIsDisplayed()
        rule.onNodeWithTag("saved-memory-close").assertIsDisplayed()
        captureToMediaStore("saved-memory-story-shelf-long-title-font$fontPercent-second-open.png")
    }

    @Test fun linkedChapterSourcesRequireExplicitReviewAndShowOnlyLargeTextOrReadyTranscriptAt150Percent() {
        val api = Api(id, summary); val store = ConnectedStore(api, scope)
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = "zh")
            }
        }
        rule.runOnIdle { store.authenticate("+8612345678", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail != null }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.contributionReferences != null }
        assertEquals("The reader-side source review must work with the default-off community panel gate.",
            false, store.memoryCommunityAvailable)
        assertEquals(1, api.contributionReferenceReads)
        assertEquals("linked text/transcript are not fetched before an explicit view action", emptyList<String>(), api.contributionDetailReads)

        rule.onNodeWithTag("saved-memory-contribution-source-0").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.contributionDetail != null }
        rule.onNodeWithTag("saved-memory-contribution-source-text").performScrollTo().assertIsDisplayed()
            .assertTextEquals(api.longFamilyText)
        rule.onNodeWithText("署名：文本署名甲", substring = false).performScrollTo().assertIsDisplayed()
        assertEquals(listOf(textContributionId), api.contributionDetailReads)
        captureToMediaStore("saved-memory-linked-text-byline-font150-${System.currentTimeMillis()}.png")
        rule.onNodeWithTag("saved-memory-contribution-source-0").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.contributionDetail == null }

        rule.onNodeWithTag("saved-memory-contribution-source-1").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.contributionDetail != null }
        rule.onNodeWithTag("saved-memory-contribution-source-transcript").performScrollTo().assertIsDisplayed()
            .assertTextEquals("这是已完成的家人录音转写。")
        rule.onNodeWithText("署名：录音署名乙", substring = false).performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("不应展示的润色稿").assertDoesNotExist()
        assertEquals(listOf(textContributionId, audioContributionId), api.contributionDetailReads)
        captureToMediaStore("saved-memory-linked-transcript-byline-font150-${System.currentTimeMillis()}.png")
    }

    @Test fun editableChapterContributionLinksSaveAndReopenAt150Percent() {
        val editableSummary = summary.copy(canEdit = true)
        val api = Api(id, editableSummary)
        val store = ConnectedStore(api, scope, memoryCommunityApi = api, memoryCommunityEnabled = true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = "zh")
            }
        }
        rule.runOnIdle { store.authenticate("+8612345678", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail != null }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.contributionReferences != null }
        rule.waitUntil(5000) {
            val community = store.state.value.savedMemoryStories?.community
            community?.contributions != null || community?.failure != null
        }
        assertEquals(null, store.state.value.savedMemoryStories?.community?.failure)
        val editor = "saved-memory-contribution-link-editor-chapter-1"
        val editorToggle = "saved-memory-contribution-link-toggle-chapter-1"
        rule.onNodeWithTag(editor).assertDoesNotExist()
        rule.onNodeWithTag(editorToggle).performScrollTo().assertIsDisplayed().assertIsEnabled()
            .assertTextEquals("管理本章回忆")
        rule.onNodeWithTag("saved-memory-contribution-source-0").performScrollTo().assertExists()
        assertEquals("Opening the reader does not fetch source details", emptyList<String>(), api.contributionDetailReads)
        captureToMediaStore("reader-source-controls-collapsed-150-v38.png")
        rule.onNodeWithTag(editorToggle).performClick()
        rule.onNodeWithTag(editor).performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("家人回忆 1 · 文字回忆").assertExists()
        rule.onNodeWithText("家人回忆 2 · 录音").assertExists()
        rule.onAllNodesWithText("署名：家人").assertCountEquals(2)
        rule.onNodeWithTag("saved-memory-contribution-link-chapter-1-0").assertTextContains("已选择")
        rule.onNodeWithTag("saved-memory-contribution-link-chapter-1-1").assertTextContains("已选择")
        rule.onNodeWithTag("saved-memory-contribution-link-chapter-1-0").assertTextContains("原始家人回忆")
        rule.onNodeWithTag("saved-memory-contribution-link-chapter-1-1").assertTextContains("录音时长 · 0:05")
        rule.onNodeWithText("这是已完成的家人录音转写。").assertDoesNotExist()
        rule.onNodeWithText(textContributionId).assertDoesNotExist()
        rule.onNodeWithText(audioContributionId).assertDoesNotExist()
        captureToMediaStore("editor-options-expanded-150-v38.png")
        rule.onNodeWithTag("saved-memory-next").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.selectedChapter == 1 }
        rule.onNodeWithTag("saved-memory-contribution-link-editor-chapter-2").assertDoesNotExist()
        rule.onNodeWithTag("saved-memory-contribution-link-toggle-chapter-2").assertTextEquals("管理本章回忆")
        rule.onNodeWithTag("saved-memory-previous").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.selectedChapter == 0 }
        rule.onNodeWithTag(editor).assertExists()
        val link = "saved-memory-contribution-link-chapter-1-0"
        rule.onNodeWithTag(link).performScrollTo().performClick()
        rule.waitUntil(3000) {
            store.state.value.savedMemoryStories?.contributionReferenceDraft?.get("chapter-1") == listOf(audioContributionId)
        }
        rule.onNodeWithTag(link).assertIsNotSelected()
        rule.onNodeWithTag("saved-memory-contribution-link-chapter-1-0").assertTextContains("未选择")
        rule.onNodeWithTag("saved-memory-contribution-link-chapter-1-1").assertTextContains("已选择")
        rule.onNodeWithTag(editorToggle).assertIsNotEnabled()
        rule.onNodeWithTag(editor).assertExists()
        rule.onNodeWithTag(link).performScrollTo().performClick()
        rule.waitUntil(3000) {
            store.state.value.savedMemoryStories?.contributionReferenceDraft?.get("chapter-1")
                ?.contains(textContributionId) == true
        }
        rule.onNodeWithTag(link).performScrollTo().performClick()
        rule.onNodeWithTag("saved-memory-contribution-link-save").performScrollTo().performClick()
        rule.waitUntil(10000) { store.state.value.savedMemoryStories?.detail?.revision == 4L &&
            store.state.value.savedMemoryStories?.contributionReferences?.revision == 4L }
        assertEquals(listOf(audioContributionId), store.state.value.savedMemoryStories!!.contributionReferences!!
            .chapters.first { it.chapterId == "chapter-1" }.contributionIds)
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.contributionReferencesBusy == false }
        rule.onNodeWithTag(editor).assertDoesNotExist()
        rule.onNodeWithTag(editorToggle).assertIsEnabled().assertTextEquals("管理本章回忆")
        rule.onNodeWithTag("saved-memory-back-list").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail == null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.detail?.revision == 4L }
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.contributionReferences?.revision == 4L }
        rule.onNodeWithTag(editor).assertDoesNotExist()
        rule.onNodeWithTag("saved-memory-contribution-source-0").performScrollTo().assertExists()
        rule.onNodeWithTag(editorToggle).assertIsEnabled().assertTextEquals("管理本章回忆")
        captureToMediaStore("links-saved-and-reopened-150-v38.png")
        rule.onNodeWithTag(editorToggle).performScrollTo().performClick()
        rule.onNodeWithTag(link).performScrollTo().assertIsNotSelected()
        val audioLink = "saved-memory-contribution-link-chapter-1-1"
        rule.onNodeWithTag(audioLink).performScrollTo().assertIsSelected().performClick()
        rule.waitUntil(3000) {
            store.state.value.savedMemoryStories?.contributionReferenceDraft?.get("chapter-1").orEmpty().isEmpty()
        }
        rule.onNodeWithTag(editorToggle).assertIsNotEnabled()
        rule.onNodeWithTag(editor).assertExists()
        rule.onNodeWithTag("saved-memory-contribution-link-save").assertIsEnabled()
        rule.onNodeWithTag("saved-memory-contribution-link-save").performScrollTo().performClick()
        rule.waitUntil(10000) {
            val state = store.state.value.savedMemoryStories
            state?.detail?.revision == 5L && state.contributionReferences?.revision == 5L ||
                state?.contributionReferenceSaveError == true || state?.contributionReferenceSaveConflict == true
        }
        assertEquals("The second removal save should not leave a stored error", false,
            store.state.value.savedMemoryStories?.contributionReferenceSaveError)
        assertEquals("The story revision should remain current during removal", false,
            store.state.value.savedMemoryStories?.contributionReferenceSaveConflict)
        assertEquals(emptyList<String>(), store.state.value.savedMemoryStories!!.contributionReferences!!
            .chapters.first { it.chapterId == "chapter-1" }.contributionIds)
        rule.onNodeWithTag(editor).assertDoesNotExist()
        rule.onNodeWithTag(editorToggle).assertIsEnabled().assertTextEquals("管理本章回忆")
        val original = runBlocking {
            api.savedMemoryContributionDetail(Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer")),
                "family", id, textContributionId)
        }
        assertEquals(api.longFamilyText, original.receipt.contribution.text)
        captureToMediaStore("links-removed-150-v38.png")
    }

    @Test fun deniedStoryReadClearsTheProtectedReader() {
        val api = Api(id, summary).apply { detailError = ApiFailure(FailureKind.HTTP, 403) }
        val store = ConnectedStore(api, scope)
        rule.setContent { ConnectedApp(store, initialLanguage = "zh") }
        rule.runOnIdle { store.authenticate("+8612345678", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories == null && store.state.value.problem?.message == Message.CLOSED }
        rule.onNodeWithTag("saved-memory-stories").assertDoesNotExist()
        assertEquals(null, store.state.value.savedMemoryStories)
    }

    @Test fun closingDuringStoryReadDiscardsTheLateProtectedReply() {
        val api = Api(id, summary).apply { detailGate = CompletableDeferred() }
        val store = ConnectedStore(api, scope)
        rule.setContent { ConnectedApp(store, initialLanguage = "zh") }
        rule.runOnIdle { store.authenticate("+8612345678", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == "family" }
        rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
        rule.waitUntil(5000) { store.state.value.savedMemoryStories?.result != null }
        rule.onNodeWithTag("saved-memory-story-$id").performClick()
        rule.waitUntil(5000) { api.detailStarted }
        rule.onNodeWithTag("saved-memory-close").performClick()
        assertEquals(null, store.state.value.savedMemoryStories)
        api.detailGate!!.complete(Unit)
        rule.waitForIdle()
        assertEquals(null, store.state.value.savedMemoryStories)
        assertEquals(null, store.state.value.detail)
    }

    private fun capture(tag: String, name: String) {
        rule.waitForIdle()
        val bitmap = rule.onNodeWithTag(tag).captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        FileOutputStream(File(context.filesDir, name)).use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }

    private fun captureToMediaStore(name: String) {
        rule.waitForIdle()
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name)
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/PhotoHouseSavedMemoryUi")
        }
        val uri = checkNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        context.contentResolver.openOutputStream(uri).use { out -> checkNotNull(out); check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)) }
        bitmap.recycle()
    }
}
