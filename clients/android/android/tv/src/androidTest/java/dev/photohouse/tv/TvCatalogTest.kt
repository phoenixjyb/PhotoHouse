package dev.photohouse.tv

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.KeyEvent
import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.home.*
import kotlinx.coroutines.*
import org.junit.*
import org.junit.Assert.*
import java.io.File

class TvCatalogTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun finish() { scope.cancel() }
    private fun fixture(name: String) = InstrumentationRegistry.getInstrumentation().context.assets.open(name).use { it.readBytes() }
    private inner class CatalogApi(private val missingVideo: Boolean = false, private val total: Int = 2, private val missingAll: Boolean = false, private val malformedFirst: Boolean = false) : HomeApi {
        override val catalogVersion = 2
        val sources = mutableListOf<HomeVideoReader>()
        val pages = mutableListOf<Int>()
        override suspend fun feed(page: Int): HomeFeed {
            pages += page
            val f = CatalogWire.feed(fixture("catalog-v2.json"), 1)
            if (total > 2) {
                val photo = f.items[1]
                val items = (0 until minOf(50, total - (page - 1) * 50)).map { offset ->
                    val id = total - (page - 1) * 50 - offset
                    photo.copy(id = id, caption = "Photo $id", grid = photo.grid!!.copy(url = CatalogWire.previewPath(id, Variant.GRID, 1)), display = photo.display!!.copy(url = CatalogWire.previewPath(id, Variant.DISPLAY, 1)))
                }
                return f.copy(page = page, total = total, hasMore = page * 50 < total, items = if (missingAll) items.map { it.copy(grid = null, display = null, gridUnavailable = MediaUnavailable.NOT_PREPARED, displayUnavailable = MediaUnavailable.NOT_PREPARED) } else items)
            }
            return if (!missingVideo) f else f.copy(items = f.items.map { if (it.kind == AssetKind.VIDEO) it.copy(video = null, videoUnavailable = MediaUnavailable.NOT_PREPARED) else it })
        }
        override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int) = fixture("home-8x8.jpg")
        override fun video(asset: HomeAsset, revision: Int, failed: (Exception) -> Unit): HomeVideoSource {
            val bytes = if (malformedFirst && sources.isEmpty()) byteArrayOf(1, 2, 3) else fixture("catalog-video.mp4")
            return HomeVideoReader(bytes.size.toLong(), 65536, { p, n -> bytes.copyOfRange(p.toInt(), p.toInt() + n) }, failed).also { sources += it }
        }
    }
    private fun install(api: CatalogApi): HomeStore {
        val store = HomeStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { TvApp(store) }; store.foreground() }
        rule.waitForIdle(); return store
    }
    private fun key(code: Int) {
        rule.waitUntil(10000) { rule.activity.hasWindowFocus() }
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(code); rule.waitForIdle()
    }
    private fun capture(name: String) {
        rule.waitForIdle()
        rule.runOnUiThread {
            val activityView = rule.activity.window.decorView
            // A Compose AlertDialog owns a separate same-process window. Drawing only the
            // Activity captures the gallery underneath it, not the dialog being verified.
            val view = if (name.startsWith("catalog-pages") && android.os.Build.VERSION.SDK_INT >= 29)
                android.view.inspector.WindowInspector.getGlobalWindowViews().last { it !== activityView && it.width > 0 && it.visibility == android.view.View.VISIBLE }
                else activityView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            File(rule.activity.filesDir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            bitmap.recycle()
        }
    }
    @Test fun mixedCatalogOpensNativeVideoThenReturnsFocusAndClearsOnBackground() {
        val api = CatalogApi(); val store = install(api)
        rule.onNodeWithTag("asset-102").assertIsFocused()
        rule.onNodeWithTag("asset-kind-102", useUnmergedTree = true).assertExists()
        rule.onNodeWithTag("gallery-summary").assertTextEquals("Page 1 of 1  ·  2 memories")
        rule.waitUntil(10000) { rule.onAllNodesWithTag("tv-image", useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        capture("catalog-grid")
        key(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitUntil(15000) { rule.onAllNodes(hasTestTag("video-play") and isEnabled()).fetchSemanticsNodes().size == 1 }
        rule.onNodeWithText("Play", substring = false).assertExists()
        assertEquals(1, api.sources.size)
        key(KeyEvent.KEYCODE_BACK)
        assertTrue(api.sources.single().isClosed)
        rule.onNodeWithText("Library", substring = false).assertIsFocused()
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("asset-102").assertIsFocused()
        rule.onNodeWithTag("asset-101").performClick()
        rule.waitUntil(10000) { rule.onAllNodesWithTag("tv-image").fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("photo-zoom").performScrollTo().performClick()
        rule.onNodeWithTag("immersive").assertExists()
        rule.runOnUiThread { store.background() }
        rule.onAllNodesWithTag("tv-image").assertCountEquals(0)
        rule.onNodeWithTag("covered").assertExists()
    }
    @Test fun nativeFailureShowsSafeCodeAndRetryReplacesClosedSource() {
        val api = CatalogApi(malformedFirst = true); val store = install(api)
        rule.onNodeWithTag("asset-102").performClick()
        rule.waitUntil(15000) { rule.onAllNodesWithTag("video-error").fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("video-error").assertTextContains("TV-", substring = true).assertIsDisplayed()
        assertTrue(api.sources.single().isClosed)
        assertNotNull(store.state.value.feed)
        capture("video-error")
        rule.showAction("language")
        rule.onNodeWithTag("language").performClick()
        rule.onNodeWithTag("video-error").assertTextContains("TV-", substring = true).assertIsDisplayed()
        capture("video-error-zh")
        rule.onNodeWithTag("open-video").assertIsDisplayed().performClick()
        rule.waitUntil(15000) { rule.onAllNodes(hasTestTag("video-play") and isEnabled()).fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("video-error").assertDoesNotExist()
        assertEquals(2, api.sources.size)
        assertFalse(api.sources.last().isClosed)
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("video-error").assertDoesNotExist()
        rule.runOnUiThread { store.background() }
        assertTrue(api.sources.all { it.isClosed })
    }
    @Test fun remotePageDialogReachesLastPageOfLargeCatalog() {
        val api = CatalogApi(total = 27842); install(api)
        rule.onNodeWithTag("page-jump").performClick()
        rule.onNodeWithTag("page-target").assertTextEquals("Page 1 of 557")
        rule.waitUntil(10000) { rule.onAllNodes(hasTestTag("page-plus-one") and isFocused()).fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("page-go").assertIsNotEnabled()
        // Real remote events, including movement in the separate dialog window.
        for (code in listOf(KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_CENTER)) {
            InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(code); rule.waitForIdle()
        }
        rule.onNodeWithTag("page-target").assertTextEquals("Page 557 of 557")
        capture("catalog-pages")
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_DOWN)
        rule.waitForIdle()
        rule.onNodeWithTag("page-go").assertIsFocused()
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitForIdle()
        rule.onNodeWithTag("gallery-summary").assertTextEquals("Page 557 of 557  ·  27842 memories")
        assertEquals(listOf(1, 557), api.pages)
        rule.onNodeWithTag("asset-42").assertIsFocused()
        rule.showAction("language")
        rule.onNodeWithTag("language").performClick()
        rule.onNodeWithTag("page-jump").performClick()
        rule.waitUntil(10000) { rule.onAllNodes(hasTestTag("page-step-2") and isFocused()).fetchSemanticsNodes().size == 1 }
        for (code in listOf(KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_CENTER)) {
            InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(code); rule.waitForIdle()
        }
        rule.onNodeWithTag("page-target").assertTextEquals("第 1 页，共 557 页")
        capture("catalog-pages-zh")
        for (code in listOf(KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_CENTER)) {
            InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(code); rule.waitForIdle()
        }
        rule.onNodeWithTag("gallery-summary").assertTextEquals("第 1 页，共 557 页  ·  27842 段回忆")
        assertEquals(listOf(1, 557, 1), api.pages)
    }
    @Test fun unpreparedPageKeepsNavigationFocusedAndDoesNotOpenBlankViewer() {
        val api = CatalogApi(total = 51, missingAll = true); install(api)
        rule.onNodeWithTag("gallery-more").assertIsFocused()
        rule.onNodeWithTag("asset-51").assertIsNotEnabled().performClick()
        rule.onNodeWithTag("viewer").assertDoesNotExist()
        rule.onNodeWithTag("page-availability").assertTextContains("0 of 50 ready on this page", substring = true)
        key(KeyEvent.KEYCODE_DPAD_LEFT)
        key(KeyEvent.KEYCODE_DPAD_LEFT)
        rule.onNodeWithText("Next page", substring = false).assertIsFocused()
        key(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.onNodeWithTag("gallery-summary").assertTextEquals("Page 2 of 2  ·  51 memories")
        rule.onNodeWithTag("gallery-more").assertIsFocused()
        assertEquals(listOf(1, 2), api.pages)
    }
    @Test fun unpreparedVideoHasAnHonestStateAndNoPlayableSource() {
        val api = CatalogApi(missingVideo = true); install(api)
        rule.onNodeWithTag("asset-102").assertIsNotEnabled().performClick()
        rule.onNodeWithTag("viewer").assertDoesNotExist()
        rule.onNodeWithTag("open-video").assertDoesNotExist()
        rule.onNodeWithTag("asset-kind-102", useUnmergedTree = true).assertTextEquals("Video · Not ready")
        assertTrue(api.sources.isEmpty())
        capture("catalog-unavailable")
    }
}
