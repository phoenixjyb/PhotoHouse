package dev.photohouse.connected

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.DpRect
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.Color
import android.util.Log
import android.provider.MediaStore
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import java.io.ByteArrayOutputStream
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SavedMemoryReaderNavigationUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var api: ReaderApi
    private lateinit var store: ConnectedStore
    private val selectedFrames = mutableListOf<String>()
    private val selectedChapters = mutableListOf<Int>()
    private val openedAssets = mutableListOf<String>()

    @After fun close() { scope.cancel() }

    private inner class ReaderApi : PhotoHouseApi {
        override val protectedNativeV2Enabled = true
        var accountId = "reader-account-a"
        var revision = 4L
        var firstChapterAssetIds = listOf("1", "2")
        var videoRangeCalls = 0
        var originalPhotoCalls = 0
        var previewCalls = 0

        private val assets = (1..4).map { number ->
            val id = number.toString()
            Asset(id, "image", 800, 600, null, "2024-05-0$number", "/assets/$id/thumbnail?library=family",
                DateHint("2024-05-0$number", "filename"))
        }
        val summary: SavedMemoryStorySummary
            get() = SavedMemoryStorySummary(STORY_ID, "Garden day", "everyday", "en", revision, "1", 4, 4, 1720000000, false)

        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session(accountId, "+8612345678", listOf(
            Membership("library-a", "approved", "viewer", 1, null, 0, true),
            Membership("library-b", "approved", "viewer", 1, null, 0, true),
        ))
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, assets.first { it.id == assetId })
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk {
            videoRangeCalls++
            return VideoChunk(start, 1, byteArrayOf(0))
        }
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray {
            originalPhotoCalls++
            return byteArrayOf(0)
        }
        override suspend fun detailPreview(token: Bearer, library: String, asset: Asset): ByteArray? {
            previewCalls++
            return null
        }
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int) =
            SavedMemoryStoryPage(library, page, 8, false, false, if (page == 1) listOf(summary) else emptyList())

        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            val chapters = listOf(
                SavedMemoryStoryChapter("chapter-1", "The first visit", "A walk through the garden.", firstChapterAssetIds, emptyList()),
                SavedMemoryStoryChapter("chapter-2", "The sunny path", "The path was warm.", listOf("2"), emptyList()),
                SavedMemoryStoryChapter("chapter-3", "Yellow flowers", "Yellow flowers lined the path.", listOf("3"), emptyList()),
                SavedMemoryStoryChapter("chapter-4", "A quiet afternoon", "We sat together.", listOf("4"), emptyList()),
            )
            return SavedMemoryStory(storyId, library, revision, 1710000000, 1720000000, false, "a".repeat(64),
                "Garden day", "everyday", "en", assets.map { MemoryStoryAsset(it, emptyList()) }, chapters, emptyList())
        }

        override suspend fun savedMemoryStoryContributionReferences(
            token: Bearer, library: String, storyId: String, revision: Long, chapterIds: List<String>,
        ) = SavedMemoryStoryContributionReferences(storyId, library, revision,
            chapterIds.map { SavedMemoryChapterContributionReferences(it, emptyList()) })
    }

    private fun openReader(zh: Boolean) {
        api = ReaderApi()
        store = ConnectedStore(api, scope)
        rule.runOnUiThread { store.authenticate("+8612345678", "correct horse battery", remember = false) }
        rule.waitUntil(10_000) { store.state.value.library == "library-a" && !store.state.value.busy }
        rule.runOnUiThread { store.openSavedMemoryStories() }
        rule.waitUntil(10_000) { store.state.value.savedMemoryStories?.result?.items?.isNotEmpty() == true }
        rule.runOnUiThread { store.openSavedMemoryStory(api.summary) }
        rule.waitUntil(10_000) {
            val reading = store.state.value.savedMemoryStories
            reading?.detail != null && !reading.detailBusy && !reading.framesBusy
        }
        rule.setContent {
            val live by store.state.collectAsState()
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                live.savedMemoryStories?.let { reading ->
                    SavedMemoryStoriesDialog(
                        store = store, reading = reading, zh = zh,
                        onClose = {}, onRetry = {}, onSelectTheme = {},
                        onOpenStory = store::openSavedMemoryStory, onRetryDetail = {},
                        onCloseDetail = { store.openSavedMemoryStories() },
                        onChapter = { index -> selectedChapters += index; store.loadSavedMemoryChapter(index) },
                        onSelectFrame = { id -> selectedFrames += id; store.loadSavedMemoryHero(id) },
                        onOpenAsset = { openedAssets += it },
                    )
                }
            }
        }
        rule.waitUntil(10_000) { rule.onAllNodesWithTag("saved-memory-frame-position").fetchSemanticsNodes().isNotEmpty() }
    }

    private fun scrollReaderUntilFrameVisible(assetId: String) {
        repeat(6) {
            val frame = rule.onNodeWithTag("saved-memory-frame-$assetId")
            val fullBounds = frame.getUnclippedBoundsInRoot()
            val visibleBounds = frame.getBoundsInRoot()
            if (kotlin.math.abs((visibleBounds.right - visibleBounds.left).value - (fullBounds.right - fullBounds.left).value) < 0.5f &&
                kotlin.math.abs((visibleBounds.bottom - visibleBounds.top).value - (fullBounds.bottom - fullBounds.top).value) < 0.5f) return
            rule.onNodeWithTag("saved-memory-reader-scroll").performTouchInput { swipeUp() }
        }
        val frame = rule.onNodeWithTag("saved-memory-frame-$assetId")
        val fullBounds = frame.getUnclippedBoundsInRoot()
        val visibleBounds = frame.getBoundsInRoot()
        val fullWidth = (fullBounds.right - fullBounds.left).value
        val fullHeight = (fullBounds.bottom - fullBounds.top).value
        val visibleWidth = (visibleBounds.right - visibleBounds.left).value
        val visibleHeight = (visibleBounds.bottom - visibleBounds.top).value
        assertTrue("after scrolling, the complete frame card must be visible; full=${fullWidth}x${fullHeight}dp, visible=${visibleWidth}x${visibleHeight}dp",
            kotlin.math.abs(visibleWidth - fullWidth) < 0.5f && kotlin.math.abs(visibleHeight - fullHeight) < 0.5f)
        assertTrue("the frame card must provide at least a 44dp target; full size=${fullWidth}x${fullHeight}dp",
            fullWidth >= 44f && fullHeight >= 44f)
    }

    private fun capture(name: String) {
        rule.waitForIdle()
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name)
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PhotoHouseReaderReview")
        }
        val uri = context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
            ?: error("Could not create UI capture in emulator MediaStore")
        try {
            context.contentResolver.openOutputStream(uri)?.use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                ?: error("Could not open UI capture in emulator MediaStore")
        } catch (failure: Throwable) {
            context.contentResolver.delete(uri, null, null)
            throw failure
        } finally {
            bitmap.recycle()
        }
    }

    private fun assertFooterButtonFullyVisible(buttonTag: String, labelTag: String, expectedLabel: String) {
        val button = rule.onNodeWithTag(buttonTag)
        val fullButton = button.getUnclippedBoundsInRoot()
        val visibleButton = button.getBoundsInRoot()
        val label = rule.onNodeWithTag(labelTag, useUnmergedTree = true)
        label.assertTextEquals(expectedLabel)
        val fullLabel = label.getUnclippedBoundsInRoot()
        val visibleLabel = label.getBoundsInRoot()
        val dialogBounds = rule.onNode(isDialog()).getBoundsInRoot()

        fun sameRect(a: DpRect, b: DpRect) =
            kotlin.math.abs(a.left.value - b.left.value) < 0.5f && kotlin.math.abs(a.top.value - b.top.value) < 0.5f &&
                kotlin.math.abs(a.right.value - b.right.value) < 0.5f && kotlin.math.abs(a.bottom.value - b.bottom.value) < 0.5f
        Log.i("SavedMemoryFooter", "$buttonTag full=$fullButton visible=$visibleButton " +
            "fullHeightDp=${(fullButton.bottom - fullButton.top).value} visibleHeightDp=${(visibleButton.bottom - visibleButton.top).value}; " +
            "$labelTag full=$fullLabel visible=$visibleLabel; dialog=$dialogBounds")

        assertTrue("$buttonTag must be at least 48dp high; full bounds=$fullButton", (fullButton.bottom - fullButton.top).value >= 48f)
        assertTrue("$buttonTag must have at least 48dp of visible height; visible bounds=$visibleButton", (visibleButton.bottom - visibleButton.top).value >= 48f)
        assertTrue("$buttonTag must be fully visible; full=$fullButton visible=$visibleButton", sameRect(fullButton, visibleButton))
        assertTrue("$buttonTag must fit inside the actual dialog window; button=$visibleButton dialog=$dialogBounds",
            visibleButton.left >= dialogBounds.left && visibleButton.top >= dialogBounds.top &&
                visibleButton.right <= dialogBounds.right && visibleButton.bottom <= dialogBounds.bottom)
        assertTrue("$labelTag text must be fully visible; full=$fullLabel visible=$visibleLabel", sameRect(fullLabel, visibleLabel))
        assertTrue("$labelTag must stay inside $buttonTag; label=$visibleLabel button=$visibleButton",
            visibleLabel.left >= visibleButton.left && visibleLabel.top >= visibleButton.top &&
                visibleLabel.right <= visibleButton.right && visibleLabel.bottom <= visibleButton.bottom)
    }

    @Test fun englishReaderAtLargeTextKeepsFooterSeparatedAndNavigationExplicit() {
        openReader(zh = false)
        assertEquals("the store's initial read supplies the first chapter hero", 1, api.previewCalls)
        assertTrue("opening a story must not emit a frame-selection callback", selectedFrames.isEmpty())

        scrollReaderUntilFrameVisible("2")
        rule.onNodeWithTag("saved-memory-frame-2").performClick().assertIsSelected()
        rule.waitUntil(10_000) { store.state.value.savedMemoryStories?.heroAssetId == "2" && !store.state.value.savedMemoryStories!!.heroBusy }
        assertEquals("an explicit frame tap adds one hero preview read", 2, api.previewCalls)
        assertEquals(listOf("2"), selectedFrames)
        rule.onNodeWithTag("saved-memory-frame-position").assertTextContains("Moment 2 of 2")

        val statusNode = rule.onNodeWithTag("saved-memory-chapter-position")
        val status = statusNode.getBoundsInRoot()
        assertTrue("English chapter status must be fully visible", statusNode.getUnclippedBoundsInRoot() == status)
        assertFooterButtonFullyVisible("saved-memory-previous", "saved-memory-previous-label", "Previous")
        assertFooterButtonFullyVisible("saved-memory-next", "saved-memory-next-label", "Next")
        val previous = rule.onNodeWithTag("saved-memory-previous").getBoundsInRoot()
        val next = rule.onNodeWithTag("saved-memory-next").getBoundsInRoot()
        assertTrue("chapter status must sit above the footer buttons", status.bottom < previous.top && status.bottom < next.top)
        assertTrue("previous and next buttons must not overlap", previous.right <= next.left)
        assertEquals("footer buttons should have equal widths", (previous.right - previous.left).value, (next.right - next.left).value, 1.5f)
        assertEquals("opening the reader must not navigate chapters", emptyList<Int>(), selectedChapters)
        capture("saved-memory-reader-en-150-window.png")

        rule.onNodeWithTag("saved-memory-next").performClick()
        rule.waitUntil(10_000) { store.state.value.savedMemoryStories?.selectedChapter == 1 && !store.state.value.savedMemoryStories!!.framesBusy }
        assertEquals(listOf(1), selectedChapters)
        rule.onNodeWithTag("saved-memory-frame-2").assertIsSelected()
        assertEquals("chapter navigation reads its hero but does not emit a frame-selection callback", 3, api.previewCalls)
        rule.onNodeWithTag("saved-memory-previous").performClick()
        rule.waitUntil(10_000) { store.state.value.savedMemoryStories?.selectedChapter == 0 && !store.state.value.savedMemoryStories!!.framesBusy }
        assertEquals(listOf(1, 0), selectedChapters)
        assertEquals("returning reads that chapter hero without another frame-selection callback", 4, api.previewCalls)
        assertEquals(listOf("2"), selectedFrames)
        assertTrue(openedAssets.isEmpty())
        assertEquals(0, api.videoRangeCalls)
        assertEquals(0, api.originalPhotoCalls)
    }

    @Test fun chineseReaderAtLargeTextShowsChapterStatusAndFramePosition() {
        openReader(zh = true)
        scrollReaderUntilFrameVisible("1")
        rule.onNodeWithTag("saved-memory-chapter-position").assertTextContains("第 1/4 章")
        rule.onNodeWithTag("saved-memory-frame-position").assertTextContains("片段 1/2")
        val statusNode = rule.onNodeWithTag("saved-memory-chapter-position")
        val status = statusNode.getBoundsInRoot()
        assertTrue("Chinese chapter status must be fully visible", statusNode.getUnclippedBoundsInRoot() == status)
        assertFooterButtonFullyVisible("saved-memory-previous", "saved-memory-previous-label", "上一章")
        assertFooterButtonFullyVisible("saved-memory-next", "saved-memory-next-label", "下一章")
        val previous = rule.onNodeWithTag("saved-memory-previous").getBoundsInRoot()
        val next = rule.onNodeWithTag("saved-memory-next").getBoundsInRoot()
        assertTrue("Chinese chapter status must sit above the footer", status.bottom < previous.top && status.bottom < next.top)
        assertTrue("Chinese footer buttons must not overlap", previous.right <= next.left)
        assertEquals("Chinese footer buttons should have equal widths", (previous.right - previous.left).value, (next.right - next.left).value, 1.5f)
        capture("saved-memory-reader-zh-150-window.png")
        rule.onNodeWithTag("saved-memory-frame-1").assertIsSelected()
        assertTrue(selectedFrames.isEmpty())
        assertTrue(selectedChapters.isEmpty())
        assertTrue(openedAssets.isEmpty())
        assertEquals(0, api.videoRangeCalls)
        assertEquals(0, api.originalPhotoCalls)
    }

    @Test fun frameSelectionResetsWhenRevisionAssetOrderLibraryOrAccountChanges() {
        openReader(zh = false)
        scrollReaderUntilFrameVisible("2")
        rule.onNodeWithTag("saved-memory-frame-2").performClick().assertIsSelected()
        assertEquals(listOf("2"), selectedFrames)

        api.revision++
        api.firstChapterAssetIds = listOf("2", "1")
        reopenStory()
        rule.onNodeWithTag("saved-memory-frame-2").assertIsSelected()

        // Even if a server accidentally leaves revision unchanged, the ordered current chapter IDs are part of the UI key.
        api.firstChapterAssetIds = listOf("1", "2")
        reopenStory()
        rule.onNodeWithTag("saved-memory-frame-1").assertIsSelected()

        rule.runOnUiThread { store.selectLibrary("library-b") }
        rule.waitUntil(10_000) { store.state.value.library == "library-b" && !store.state.value.busy }
        reopenStory()
        rule.onNodeWithTag("saved-memory-frame-1").assertIsSelected()

        rule.runOnUiThread { store.logout() }
        rule.waitUntil(10_000) { store.state.value.session == null }
        api.accountId = "reader-account-b"
        rule.runOnUiThread { store.authenticate("+8612345678", "correct horse battery", remember = false) }
        rule.waitUntil(10_000) { store.state.value.session?.account_id == "reader-account-b" && !store.state.value.busy }
        rule.runOnUiThread { store.openSavedMemoryStories() }
        rule.waitUntil(10_000) { store.state.value.savedMemoryStories?.result?.items?.isNotEmpty() == true }
        rule.runOnUiThread { store.openSavedMemoryStory(api.summary) }
        rule.waitUntil(10_000) { store.state.value.savedMemoryStories?.detail != null && !store.state.value.savedMemoryStories!!.framesBusy }
        rule.onNodeWithTag("saved-memory-frame-1").assertIsSelected()
    }

    @Test fun missingCurrentStoryAssetCannotKeepAStaleSelectedFrameOrHero() {
        val story = SavedMemoryStory(
            STORY_ID, "library-a", 4, 1710000000, 1720000000, false, "a".repeat(64), "Garden day", "everyday", "en",
            listOf(
                MemoryStoryAsset(Asset("1", "image", 800, 600, null, "2024-05-01", "/assets/1/thumbnail?library=family"), emptyList()),
                MemoryStoryAsset(Asset("2", "image", 800, 600, null, "2024-05-02", "/assets/2/thumbnail?library=family"), emptyList()),
            ),
            listOf(SavedMemoryStoryChapter("chapter-1", "The first visit", "A walk through the garden.", listOf("2", "1"), emptyList())),
            emptyList(),
        )
        val summary = SavedMemoryStorySummary(STORY_ID, "Garden day", "everyday", "en", 4, "1", 1, 1, 1720000000, false)
        val heroBitmap = Bitmap.createBitmap(12, 12, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.RED) }
        val staleHeroBytes = ByteArrayOutputStream().use { output ->
            heroBitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
            heroBitmap.recycle()
            output.toByteArray()
        }
        val reading = SavedMemoryStoriesReading(
            library = "library-a", result = SavedMemoryStoryPage("library-a", 1, 8, false, false, listOf(summary)),
            detail = story, selectedSummary = summary, heroAssetId = "2", hero = staleHeroBytes,
            frames = mapOf("2" to staleHeroBytes),
        )
        val changingReading = mutableStateOf(reading)
        rule.setContent {
            val currentDensity = LocalDensity.current
            val currentReading by changingReading
            CompositionLocalProvider(LocalDensity provides Density(currentDensity.density, 1.5f)) {
                SavedMemoryStoriesDialog(
                    store = null, reading = currentReading, zh = false,
                    onClose = {}, onRetry = {}, onSelectTheme = {}, onOpenStory = {}, onRetryDetail = {},
                    onCloseDetail = {}, onChapter = {}, onSelectFrame = { selectedFrames += it }, onOpenAsset = { openedAssets += it },
                )
            }
        }
        scrollReaderUntilFrameVisible("2")
        rule.onNodeWithTag("saved-memory-frame-2").assertIsSelected().performClick()
        assertEquals(listOf("2"), selectedFrames)
        rule.runOnUiThread { changingReading.value = reading.copy(detail = story.copy(items = story.items.filter { it.asset.id != "2" })) }
        rule.onNodeWithTag("saved-memory-frame-1").assertIsSelected()
        rule.onNodeWithTag("saved-memory-frame-2").assertDoesNotExist()
        rule.onNodeWithTag("saved-memory-frame-position").assertTextContains("Moment 1 of 1")
        rule.onNodeWithText("Photo unavailable").assertExists()
        rule.onNodeWithTag("saved-memory-open-1").assertIsEnabled()
        rule.onNodeWithTag("saved-memory-previous").assertIsNotEnabled()
        rule.onNodeWithTag("saved-memory-next").assertIsNotEnabled()
        rule.onNodeWithTag("saved-memory-narration-toggle").assertTextContains("Read aloud")
        rule.onNodeWithText("Stop reading").assertDoesNotExist()
        scrollReaderUntilFrameVisible("1")
        val frameBounds = rule.onNodeWithTag("saved-memory-frame-1").fetchSemanticsNode().boundsInRoot
        val density = InstrumentationRegistry.getInstrumentation().targetContext.resources.displayMetrics.density
        assertTrue("frame tap bounds were ${frameBounds.width}x${frameBounds.height}px at density $density", frameBounds.width >= 44f * density && frameBounds.height >= 44f * density)
        assertEquals(listOf("2"), selectedFrames)
        assertTrue("the UI-only inconsistent fixture must not navigate chapters or open media", selectedChapters.isEmpty() && openedAssets.isEmpty())
    }

    private fun reopenStory() {
        rule.runOnUiThread { store.openSavedMemoryStories() }
        rule.waitUntil(10_000) { store.state.value.savedMemoryStories?.result?.items?.isNotEmpty() == true && store.state.value.savedMemoryStories?.detail == null }
        rule.runOnUiThread { store.openSavedMemoryStory(api.summary) }
        rule.waitUntil(10_000) { store.state.value.savedMemoryStories?.detail != null && !store.state.value.savedMemoryStories!!.framesBusy }
    }

    companion object { private const val STORY_ID = "11111111-1111-1111-1111-111111111111" }
}
