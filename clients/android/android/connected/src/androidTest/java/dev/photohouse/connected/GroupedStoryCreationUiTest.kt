package dev.photohouse.connected

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import java.io.ByteArrayOutputStream
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.serialization.json.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class GroupedStoryCreationUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun close() { scope.cancel() }

    @Test fun chineseGroupedStorySelectionReviewSaveAndFreshReaderAt150Percent() = journey(zh = true)

    @Test fun englishGroupedStorySelectionReviewSaveAndFreshReaderAt150Percent() = journey(zh = false)

    private fun journey(zh: Boolean) {
        val api = SyntheticGroupedStoryApi()
        val store = ConnectedStore(api, scope)
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = if (zh) "zh" else "en")
            }
        }
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == SyntheticGroupedStoryApi.LIBRARY }
        rule.onNodeWithTag("open-grouped-story-creation").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.state.value.groupedStoryCreation?.let { it.gallery != null && !it.pageBusy } == true
        }
        rule.onNodeWithTag("grouped-story-select-102").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.state.value.groupedStoryCreation?.editor?.state?.value?.selectedAssetIds == listOf("102")
        }
        rule.onNodeWithTag("grouped-story-select-101").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.state.value.groupedStoryCreation?.editor?.state?.value?.selectedAssetIds == listOf("102", "101")
        }
        rule.onNodeWithTag("grouped-story-selection-list").performScrollToIndex(0)
        rule.onNodeWithTag("grouped-story-related-toggle").performClick()
        rule.runOnIdle { assertEquals("opening the panel does not fetch", 0, api.relatedLookups) }
        rule.onNodeWithTag("grouped-story-related-lookup").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.state.value.groupedStoryCreation?.editor?.state?.value?.relatedCandidates?.map { it.asset.id } == listOf("103") &&
                store.state.value.groupedStoryCreation?.relatedPreviews?.containsKey("103") == true
        }
        rule.onNodeWithText(if (zh) "这只是日期匹配；文件名日期或上传日期不能证明同一次活动。" else "This is a date match only. Filename or upload date is not proof.")
            .performScrollTo().assertIsDisplayed()
        capture("grouped-story-creation", if (zh) "grouped-story-related-zh-150.png" else "grouped-story-related-en-150.png")
        rule.onNodeWithTag("grouped-story-related-add-103").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.state.value.groupedStoryCreation?.editor?.state?.value?.selectedAssetIds == listOf("102", "101", "103")
        }
        rule.runOnIdle {
            assertTrue("explicit inclusion clears candidate previews", store.state.value.groupedStoryCreation?.relatedPreviews?.isEmpty() == true)
            assertTrue("cleared preview buffer is zeroed", api.relatedThumbnailBuffer!!.all { it == 0.toByte() })
        }
        rule.onNodeWithTag("grouped-story-theme-trip").performClick()
        rule.onNodeWithTag(if (zh) "grouped-story-language-zh" else "grouped-story-language-en").performClick()
        rule.onNodeWithTag("grouped-story-select-102").performScrollTo()
        rule.onNodeWithText(if (zh) "选择顺序：1" else "Story order: 1").assertIsDisplayed()
        capture("grouped-story-creation", if (zh) "grouped-story-selection-zh-150.png" else "grouped-story-selection-en-150.png")
        rule.onNodeWithTag("grouped-story-selection-preview").performClick()
        rule.waitUntil(5000) {
            store.state.value.groupedStoryCreation?.editor?.state?.value?.status == StoryWorkspaceStoreStatus.EDITING
        }

        val title = if (zh) "家人的花园故事" else "Our family garden story"
        rule.onNodeWithTag("grouped-story-title").performScrollTo().performTextReplacement(title)
        rule.onNodeWithTag("grouped-story-reviewed").performScrollTo().performClick()
        rule.runOnIdle {
            val editor = store.state.value.groupedStoryCreation?.editor?.state?.value
            assertEquals(listOf("102", "101", "103"), editor?.selectedAssetIds)
            assertEquals(title, editor?.title)
            assertTrue(editor?.reviewed == true)
        }
        capture("grouped-story-review", if (zh) "grouped-story-review-zh-150.png" else "grouped-story-review-en-150.png")
        rule.onNodeWithTag("grouped-story-save").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.state.value.groupedStoryCreation?.editor?.state?.value?.status == StoryWorkspaceStoreStatus.SAVED
        }
        rule.runOnIdle {
            assertEquals(1, api.saveRequests)
            assertEquals(listOf("102", "101", "103"), api.savedStory?.items?.map { it.asset.id })
            assertEquals(title, api.savedStory?.title)
        }
        rule.onNodeWithTag("grouped-story-read").performScrollTo().performClick()
        rule.waitUntil(5000) {
            store.state.value.savedMemoryStories?.let { reading ->
                reading.detail?.id == SyntheticGroupedStoryApi.STORY_ID && !reading.detailBusy
            } == true
        }
        rule.runOnIdle {
            assertEquals("reader asks for a fresh protected story detail", 1, api.freshStoryReads)
            assertEquals(listOf("102", "101", "103"), store.state.value.savedMemoryStories?.detail?.items?.map { it.asset.id })
            assertEquals(title, store.state.value.savedMemoryStories?.detail?.title)
        }
        rule.onNodeWithTag("saved-memory-title").assertIsDisplayed().assertTextEquals(title)
        capture("saved-memory-stories", if (zh) "grouped-story-reader-zh-150.png" else "grouped-story-reader-en-150.png")
    }

    private fun capture(tag: String, name: String) {
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        val info = automation.serviceInfo
        val flags = info.flags
        info.flags = flags or android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
            android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
        automation.serviceInfo = info
        try {
            val deadline = android.os.SystemClock.uptimeMillis() + 2_000
            var roots = automation.windows.mapNotNull { it.root } + listOfNotNull(automation.rootInActiveWindow)
            while (roots.isEmpty() && android.os.SystemClock.uptimeMillis() < deadline) {
                android.os.SystemClock.sleep(50)
                roots = automation.windows.mapNotNull { it.root } + listOfNotNull(automation.rootInActiveWindow)
            }
            check(roots.isNotEmpty()) { "No accessible fixture window" }
            check(roots.none { root ->
                root.findAccessibilityNodeInfosByViewId("android:id/aerr_close").isNotEmpty() ||
                    root.findAccessibilityNodeInfosByViewId("android:id/aerr_wait").isNotEmpty()
            }) { "A system error dialog obscures the fixture display" }
        } finally { info.flags = flags; automation.serviceInfo = info }
        val image = rule.onNodeWithTag(tag).captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        File(context.filesDir, name).outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private class SyntheticGroupedStoryApi : PhotoHouseApi, StoryWorkspaceApi {
        override val protectedNativeV2Enabled = true
        var saveRequests = 0
        var freshStoryReads = 0
        var relatedLookups = 0
        var relatedThumbnailBuffer: ByteArray? = null
        var savedStory: SavedMemoryStory? = null
        private var preview: JsonObject? = null
        private val assets = linkedMapOf(
            "102" to Asset("102", "video", 640, 360, 3.5, null, "/assets/102/thumbnail?library=$LIBRARY"),
            "101" to Asset("101", "image", 800, 600, null, null, "/assets/101/thumbnail?library=$LIBRARY"),
            "103" to Asset("103", "video", 640, 360, 2.0, "2026-01-02T23:30:00-05:00", "/assets/103/thumbnail?library=$LIBRARY"),
        )
        private val evidence = mapOf(
            "102" to MemoryStoryEvidence("family-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "family", "Garden video", "We walked through the garden together.", 1),
            "101" to MemoryStoryEvidence("family-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "family", "Garden photo", "Grandma pointed out the flowers.", 1),
            "103" to MemoryStoryEvidence("family-cccccccc-cccc-4ccc-8ccc-cccccccccccc", "family", "Garden clip", "The family looked at flowers.", 1),
        )

        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("synthetic-account", "+12025550123",
            listOf(Membership(LIBRARY, "approved", "contributor", 1, null, 0, true)), "Synthetic contributor")
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) =
            Gallery(library, page, 2, 2, false, listOf(assets.getValue("102"), assets.getValue("101")))
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, assets.getValue(assetId))
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray {
            // A generated landscape, not a family photo. Each response owns its wipeable buffer.
            val bitmap = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            val paint = Paint(Paint.ANTI_ALIAS_FLAG)
            canvas.drawColor(Color.rgb(216, 230, 239))
            paint.color = Color.rgb(252, 211, 110); canvas.drawCircle(485f, 85f, 43f, paint)
            paint.color = Color.rgb(99, 145, 123); canvas.drawOval(-100f, 210f, 440f, 650f, paint)
            paint.color = Color.rgb(62, 111, 94); canvas.drawOval(220f, 255f, 850f, 720f, paint)
            paint.color = Color.rgb(225, 181, 165)
            repeat(6) { canvas.drawCircle(60f + it * 94f, 420f - (it % 2) * 25f, 11f, paint) }
            val bytes = ByteArrayOutputStream().use { output ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
                bitmap.recycle(); output.toByteArray()
            }
            if (asset.id == "103") relatedThumbnailBuffer = bytes
            return bytes
        }
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) =
            VideoChunk(start, 1, byteArrayOf(0))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf(0)
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int) =
            SavedMemoryStoryPage(library, page, 8, false, true, emptyList())
        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            freshStoryReads++
            return checkNotNull(savedStory).also {
                check(library == LIBRARY && storyId == STORY_ID && revision <= it.revision)
            }
        }

        override suspend fun savedMemoryStoryContributionReferences(
            token: Bearer, library: String, storyId: String, revision: Long, chapterIds: List<String>,
        ) = SavedMemoryStoryContributionReferences(storyId, library, revision,
            chapterIds.map { SavedMemoryChapterContributionReferences(it, emptyList()) })

        override suspend fun storyPreview(token: Bearer, library: String, json: String): ByteArray {
            check(library == LIBRARY)
            val request = Json.parseToJsonElement(json).jsonObject
            val ids = request.getValue("asset_ids").jsonPrimitive.content.split(',')
            check(ids == listOf("102", "101", "103")) { "preview preserves the selected mixed-media order" }
            val items = JsonArray(ids.map { id ->
                val itemAsset = assets.getValue(id)
                val itemEvidence = evidence.getValue(id)
                buildJsonObject {
                    put("id", id); put("kind", itemAsset.kind); put("width", itemAsset.width!!); put("height", itemAsset.height!!)
                    put("duration_sec", itemAsset.duration_sec?.let(::JsonPrimitive) ?: JsonNull)
                    put("taken_at", JsonNull); put("thumbnail_url", itemAsset.thumbnail_url); put("date_hint", JsonNull)
                    put("evidence", buildJsonArray {
                        add(buildJsonObject {
                            put("id", itemEvidence.id); put("source", itemEvidence.source); put("title", itemEvidence.title)
                            put("text", itemEvidence.text); put("revision", itemEvidence.revision!!)
                        })
                    })
                }
            })
            val chapter = buildJsonObject {
                put("id", "chapter-1"); put("title", if (request.getValue("language").jsonPrimitive.content == "zh") "花园时光" else "Garden moments")
                put("narration", "The family shared a walk among the flowers.")
                put("asset_ids", JsonArray(ids.map(::JsonPrimitive)))
                put("evidence_ids", JsonArray(ids.map { evidence.getValue(it).id }.map(::JsonPrimitive)))
            }
            val result = buildJsonObject {
                put("version", 1); put("library_id", library); put("selection_revision", REVISION)
                put("state", "draft"); put("saved", false)
                put("title", if (request.getValue("language").jsonPrimitive.content == "zh") "花园里的一天" else "A day in the garden")
                put("theme", request.getValue("theme").jsonPrimitive.content)
                put("language", request.getValue("language").jsonPrimitive.content)
                put("generator", "evidence_outline"); put("needs_review", true)
                put("items", items); put("chapters", JsonArray(listOf(chapter)))
                put("questions", JsonArray(listOf(JsonPrimitive("What else do you remember?"))))
            }
            preview = result
            return result.toString().encodeToByteArray()
        }

        override suspend fun storyTitleCapabilities(token: Bearer, library: String) =
            """{"version":1,"enabled":false,"max_suggestions":3,"needs_review":true}""".encodeToByteArray()
        override suspend fun storyTitles(token: Bearer, library: String, json: String): ByteArray = error("title suggestions are disabled in this fixture")

        override suspend fun relatedStoryMedia(token: Bearer, library: String, json: String): ByteArray {
            check(library == LIBRARY)
            relatedLookups++
            val request = Json.parseToJsonElement(json).jsonObject
            check(request.getValue("asset_ids").jsonPrimitive.content == "102,101")
            check(request.getValue("before_id").jsonPrimitive.content.isEmpty())
            val candidate = assets.getValue("103")
            return buildJsonObject {
                put("version", 1); put("library_id", library); put("seed_asset_ids", JsonArray(listOf("102", "101").map(::JsonPrimitive)))
                put("recorded_days", JsonArray(listOf(JsonPrimitive("2026-01-02"))))
                put("needs_review", true); put("has_more", false); put("next_before_id", JsonNull)
                put("items", JsonArray(listOf(buildJsonObject {
                    put("id", candidate.id); put("kind", candidate.kind); put("width", candidate.width!!); put("height", candidate.height!!)
                    put("duration_sec", candidate.duration_sec!!); put("taken_at", candidate.taken_at!!); put("thumbnail_url", candidate.thumbnail_url)
                    put("match_reason", "same_recorded_capture_day")
                })))
            }.toString().encodeToByteArray()
        }

        override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray {
            check(library == LIBRARY)
            saveRequests++
            val request = Json.parseToJsonElement(json).jsonObject
            val ids = request.getValue("asset_ids").jsonPrimitive.content.split(',')
            check(ids == listOf("102", "101", "103"))
            val chapters = Json.parseToJsonElement(request.getValue("chapters").jsonPrimitive.content).jsonArray
            val previewValue = checkNotNull(preview)
            val title = request.getValue("title").jsonPrimitive.content
            val language = request.getValue("language").jsonPrimitive.content
            val theme = request.getValue("theme").jsonPrimitive.content
            val finalChapter = chapters.single().jsonObject
            val savedJson = buildJsonObject {
                put("version", 1); put("library_id", library); put("id", STORY_ID); put("revision", "1")
                put("created_at", 1_800_000_000); put("updated_at", 1_800_000_000); put("can_edit", true)
                put("saved", true); put("state", "draft"); put("generator", "family_edited_outline"); put("needs_review", true)
                put("selection_revision", request.getValue("selection_revision").jsonPrimitive.content)
                put("title", title); put("theme", theme); put("language", language)
                put("items", previewValue.getValue("items")); put("chapters", JsonArray(chapters))
                put("questions", previewValue.getValue("questions"))
            }
            val storyItems = ids.map { id -> MemoryStoryAsset(assets.getValue(id), listOf(evidence.getValue(id))) }
            val storyChapters = listOf(SavedMemoryStoryChapter(
                finalChapter.getValue("id").jsonPrimitive.content,
                finalChapter.getValue("title").jsonPrimitive.content,
                finalChapter.getValue("narration").jsonPrimitive.content,
                finalChapter.getValue("asset_ids").jsonArray.map { it.jsonPrimitive.content },
                finalChapter.getValue("evidence_ids").jsonArray.map { it.jsonPrimitive.content },
            ))
            savedStory = SavedMemoryStory(STORY_ID, library, 1, 1_800_000_000, 1_800_000_000, true,
                request.getValue("selection_revision").jsonPrimitive.content, title, theme, language,
                storyItems, storyChapters, previewValue.getValue("questions").jsonArray.map { it.jsonPrimitive.content })
            return savedJson.toString().encodeToByteArray()
        }

        companion object {
            const val LIBRARY = "family-synthetic"
            const val STORY_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
            private const val REVISION = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
        }
    }
}
