package dev.photohouse.tv

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.view.KeyEvent
import android.view.WindowManager
import androidx.activity.compose.setContent
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.home.*
import kotlinx.coroutines.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

@RunWith(AndroidJUnit4::class)
class TvUiTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun finish() { scope.cancel() }
    private fun fixture(name: String) = InstrumentationRegistry.getInstrumentation().context.assets.open(name).use { it.readBytes() }
    private inner class SyntheticApi : HomeApi {
        val base = HomeWire.feed(fixture("feed.json"), 1)
        val photos = (1..6).map { id -> base.items.single().copy(id = id,
            caption = "A quiet afternoon · 宁静的午后 <b>literal</b>",
            grid = base.items.single().grid!!.copy(url = HomeWire.path(id, Variant.GRID, 1)),
            display = base.items.single().display!!.copy(url = HomeWire.path(id, Variant.DISPLAY, 1))) }
        var feedItems: List<HomeAsset> = photos
        var displayReads = 0
        var feedReads = 0
        var originalReads = 0
        var videoReads = 0
        var failedDisplayId: Int? = null
        var denied = false
        var empty = false
        override suspend fun feed(page: Int): HomeFeed {
            feedReads++
            if (denied) throw HomeFailure(HomeError.DENIED)
            return base.copy(page = page, items = if (empty) emptyList() else feedItems, total = if (empty) 0 else feedItems.size)
        }
        override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray {
            if (variant == Variant.DISPLAY && asset.id == failedDisplayId) throw HomeFailure(HomeError.UNAVAILABLE)
            if (variant == Variant.DISPLAY) displayReads++
            return fixture(if (variant == Variant.GRID) "home-8x8.jpg" else "home-3840x2160.jpg")
        }
        override suspend fun original(asset: HomeAsset, revision: Int): ByteArray { originalReads++; return fixture("home-3840x2160.jpg") }
        override fun video(asset: HomeAsset, revision: Int, failed: (Exception) -> Unit): HomeVideoSource {
            videoReads++; throw HomeFailure(HomeError.INVALID)
        }
    }
    private fun install(api: SyntheticApi = SyntheticApi(), connect: Boolean = true): HomeStore {
        val store = HomeStore(api, scope)
        rule.runOnUiThread {
            rule.activity.setContent { TvApp(store) }
            if (connect) store.foreground() else store.disconnect()
        }
        rule.waitForIdle()
        return store
    }
    private fun key(code: Int) {
        rule.waitUntil(10000) { rule.activity.hasWindowFocus() }
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(code)
        rule.waitForIdle()
    }
    private fun click(text: String) {
        val node = rule.onNode(hasText(text) and hasClickAction())
        runCatching { node.performScrollTo() } // Dialog controls have no scroll ancestor.
        node.performClick(); rule.waitForIdle()
    }
    private fun gallery() { rule.onNodeWithTag("grid").assertExists() }
    private fun capture(name: String) {
        rule.waitForIdle()
        rule.runOnUiThread {
            val view = rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            File(rule.activity.filesDir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            bitmap.recycle()
        }
    }
    @Test fun setupIsClosedAndWindowRemainsSecure() {
        assertEquals("", BuildConfig.PHOTOHOUSE_ORIGIN)
        assertEquals("", BuildConfig.PHOTOHOUSE_LAN_ADDRESS)
        assertEquals("", BuildConfig.PHOTOHOUSE_UPDATE_ORIGIN)
        assertEquals("", BuildConfig.PHOTOHOUSE_UPDATE_LAN_ADDRESS)
        rule.onNodeWithTag("setup").assertIsDisplayed()
        rule.onAllNodes(hasSetTextAction()).assertCountEquals(0)
        assertTrue(rule.activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE != 0)
        capture("setup")
    }
    @Test fun galleryOpensTvUpdatesAndKeepsAnUnconfiguredFeedClosed() {
        install()
        gallery()
        rule.showAction("updates")
        rule.onNodeWithTag("updates").performClick()
        rule.onNodeWithTag("ota-check").assertIsDisplayed()
        rule.onNodeWithTag("ota-check").assertIsFocused()
        rule.onNodeWithTag("ota-install").assertDoesNotExist()
        val updateView = rule.onNode(isDialog()).captureToImage().asAndroidBitmap()
        File(rule.activity.filesDir, "gallery-updates-dialog.png").outputStream().use {
            updateView.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitForIdle()
        rule.waitUntil(5000) { rule.onAllNodesWithTag("ota-status").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("ota-install").assertDoesNotExist()
        rule.onNodeWithTag("updates-close").performClick()
        rule.onNodeWithTag("ota-check").assertDoesNotExist()
        gallery()
    }
    @Test fun remoteFocusOpensPhotoAndBackRestoresSelectedTile() {
        val store = install()
        rule.onNodeWithTag("gallery-heading").assertIsDisplayed()
        rule.onNodeWithTag("gallery-summary").assertExists()
        rule.onNodeWithTag("gallery-kicker").assertIsDisplayed()
        rule.onNodeWithTag("featured-asset-1").assertIsDisplayed().assertHasClickAction()
        rule.onNodeWithTag("featured-asset-1").performClick()
        rule.waitUntil(5000) { store.state.value.selected == 1 }
        rule.onNodeWithTag("viewer").assertExists()
        rule.onNodeWithTag("gallery-heading").assertDoesNotExist()
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("asset-1").assertIsFocused()
        key(KeyEvent.KEYCODE_DPAD_RIGHT)
        rule.onNodeWithTag("asset-2").assertIsFocused()
        rule.waitUntil(10000) { store.state.value.grids.size == 6 }
        capture("grid-en")
        key(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitUntil(5000) { store.state.value.selected == 2 }
        rule.waitUntil(10000) { rule.onAllNodesWithTag("tv-image").fetchSemanticsNodes().size == 1 }
        capture("detail-en")
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("asset-2").assertIsFocused()
        rule.showAction("language")
        rule.onNodeWithTag("language").performClick(); capture("grid-zh")
    }
    @Test fun fullScreenRemoteNavigationAndPrivacyClearImages() {
        val api = SyntheticApi(); val store = install(api); gallery()
        rule.onNodeWithTag("asset-1").performClick(); rule.waitForIdle()
        rule.onNodeWithTag("quality").assertDoesNotExist()
        rule.onNodeWithTag("fullscreen").performScrollTo().performClick(); rule.waitForIdle()
        rule.onNodeWithTag("immersive").assertIsFocused()
        rule.waitUntil(10000) { rule.onAllNodesWithTag("tv-image").fetchSemanticsNodes().size == 1 }
        capture("fullscreen")
        key(KeyEvent.KEYCODE_DPAD_RIGHT)
        rule.waitUntil(5000) { store.state.value.selected == 2 }
        key(KeyEvent.KEYCODE_DPAD_LEFT)
        rule.waitUntil(5000) { store.state.value.selected == 1 }
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("viewer").assertExists()
        rule.runOnUiThread { store.background() }; rule.waitForIdle()
        rule.onNodeWithTag("covered").assertIsDisplayed()
        rule.onAllNodesWithTag("tv-image").assertCountEquals(0)
        capture("covered")
    }
    @Test fun remoteZoomPanResetAndFitFillStayOnTheSamePhoto() {
        val store = install()
        rule.onNodeWithTag("asset-1").performClick()
        rule.waitUntil(10000) { store.state.value.display != null }
        rule.onNodeWithTag("photo-fit").performScrollTo().performClick()
        rule.onNodeWithText("Fit photo").assertExists()
        rule.onNodeWithTag("photo-zoom").performScrollTo().performClick()
        rule.onNodeWithText("2×", substring = true).assertExists()
        repeat(8) { key(KeyEvent.KEYCODE_DPAD_RIGHT) }
        key(KeyEvent.KEYCODE_DPAD_UP)
        assertEquals(1, store.state.value.selected)
        rule.waitUntil(10000) { rule.onAllNodesWithTag("tv-image").fetchSemanticsNodes().size == 1 }
        capture("photo-zoom")
        key(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.onNodeWithText("4×", substring = true).assertExists()
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("immersive").assertExists()
        key(KeyEvent.KEYCODE_DPAD_RIGHT)
        rule.waitUntil(5000) { store.state.value.selected == 2 }
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithText("Fill screen").assertExists()
        val bounded = PhotoTransform(zoom = 4f).pan(100f, -100f)
        assertEquals(1f, bounded.panX); assertEquals(-1f, bounded.panY)
        assertEquals(PhotoTransform(), PhotoTransform(zoom = 4f).nextZoom())
    }
    @Test fun prepared4kLoadsAutomaticallyAndDisconnectClearsIt() {
        val api = SyntheticApi(); val store = install(api); gallery()
        rule.onNodeWithTag("asset-1").performClick(); rule.waitForIdle()
        rule.waitUntil(10000) { store.state.value.display != null }
        assertEquals(1, api.displayReads)
        rule.onNodeWithTag("quality").assertDoesNotExist()
        rule.waitUntil(10000) { rule.onAllNodesWithTag("tv-image").fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("tv-image").assertIsDisplayed()
        rule.showAction("disconnect")
        rule.onNodeWithTag("disconnect").assertIsDisplayed()
        val imageBounds = rule.onNodeWithTag("tv-image").fetchSemanticsNode().boundsInRoot
        val viewerBounds = rule.onNodeWithTag("viewer").fetchSemanticsNode().boundsInRoot
        assertTrue(imageBounds.top >= viewerBounds.top && imageBounds.bottom <= viewerBounds.bottom)
        capture("display-caption")
        click("Captions"); rule.onNodeWithText("A quiet afternoon", substring = true).assertExists()
        rule.waitUntil(10000) { rule.onAllNodes(hasText("Close") and isFocused()).fetchSemanticsNodes().size == 1 }
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitForIdle()
        rule.showAction("disconnect")
        rule.onNodeWithTag("disconnect").performClick(); rule.waitForIdle()
        assertNull(store.state.value.feed); assertNull(store.state.value.display)
        assertTrue(store.state.value.grids.isEmpty())
        rule.onNodeWithTag("viewer").assertDoesNotExist()
    }
    @Test fun homeDisplayNeverShowsPersonalSignInFields() {
        install(SyntheticApi(), connect = false)
        rule.onNodeWithTag("home-access-needed").assertIsDisplayed()
        rule.onAllNodes(hasSetTextAction()).assertCountEquals(0)
        rule.onAllNodesWithText("Sign in").assertCountEquals(0)
        capture("connection-needed")
    }
    @Test fun slideshowAdvancesAndStopsWhenCovered() {
        val api = SyntheticApi(); val store = install(api); gallery()
        rule.onNodeWithTag("asset-1").performClick(); rule.waitForIdle()
        rule.mainClock.autoAdvance = false
        rule.onNodeWithTag("slideshow").performClick()
        rule.mainClock.advanceTimeBy(16)
        rule.mainClock.advanceTimeBy(8200); rule.waitForIdle()
        rule.waitUntil(10000) { store.state.value.selected == 2 }
        rule.runOnUiThread { store.background() }; rule.waitForIdle()
        val reads = api.displayReads
        rule.mainClock.advanceTimeBy(16000); rule.waitForIdle()
        assertEquals(reads, api.displayReads)
        rule.onAllNodesWithTag("tv-image").assertCountEquals(0)
    }
    @Test fun slideshowUsesSelectedIntervalAndManualPauseDoesNotComplete() {
        val store = install(); gallery()
        rule.onNodeWithTag("asset-1").performClick(); rule.waitUntil(10000) { store.state.value.display != null }
        rule.onNodeWithTag("slideshow-speed-status").assertTextContains("8秒", substring = true)
        rule.onNodeWithTag("slideshow-speed-4").performScrollTo()
            .performSemanticsAction(SemanticsActions.RequestFocus)
        rule.onNodeWithTag("slideshow-speed-4").assertIsDisplayed().assertIsFocused()
        key(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.onNodeWithTag("slideshow-speed-4").assertIsSelected()
        rule.onNodeWithTag("slideshow-speed-status").assertTextContains("4秒", substring = true)
        capture("slideshow-speed-controls")
        rule.mainClock.advanceTimeBy(6000); rule.waitForIdle()
        assertEquals(1, store.state.value.selected)
        rule.mainClock.autoAdvance = false
        rule.onNodeWithTag("slideshow").performClick()
        rule.mainClock.advanceTimeBy(16)
        rule.mainClock.advanceTimeBy(2500); rule.waitForIdle()
        rule.onNodeWithTag("slideshow-speed-12").performScrollTo()
            .performSemanticsAction(SemanticsActions.RequestFocus)
        rule.onNodeWithTag("slideshow-speed-12").assertIsDisplayed().assertIsFocused()
        key(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.mainClock.advanceTimeBy(16); rule.waitForIdle()
        rule.onNodeWithTag("slideshow-speed-12").assertIsSelected()
        rule.onNodeWithTag("slideshow-speed-status").assertTextContains("12秒", substring = true)
        rule.mainClock.advanceTimeBy(11900); rule.waitForIdle()
        assertEquals(1, store.state.value.selected)
        rule.mainClock.advanceTimeBy(400); rule.waitForIdle()
        rule.waitUntil(5000) { store.state.value.selected == 2 }
        rule.waitUntil(5000) { store.state.value.display != null && !store.state.value.busy }
        rule.onNodeWithTag("slideshow").performClick()
        rule.mainClock.advanceTimeBy(16000); rule.waitForIdle()
        assertNull(store.state.value.selected)
        rule.onNodeWithTag("slideshow-complete").assertDoesNotExist()
    }
    @Test fun slideshowSkipsNonPreparedAndVideoItemsThenEndsAndRestartsExplicitly() {
        val api = SyntheticApi()
        val video = HomeAsset(2, "video", null, null, AssetKind.VIDEO,
            video = HomeVideo(1, 1, 1000, 1, "0".repeat(64), "/video", null))
        val originalOnly = api.photos[2].copy(id = 3, display = null,
            original = HomeOriginal("image/jpeg", 1, 1, 1, "/original/3"))
        val unprepared = api.photos[3].copy(id = 4, display = null, original = null)
        val last = api.photos[4].copy(id = 5)
        api.feedItems = listOf(api.photos[0].copy(id = 1), video, originalOnly, unprepared, last)
        val store = install(api); gallery()
        rule.onNodeWithTag("asset-1").performClick(); rule.waitUntil(10000) { store.state.value.display != null }
        rule.onNodeWithTag("slideshow-speed-4").performClick()
        rule.mainClock.autoAdvance = false
        rule.onNodeWithTag("slideshow").performClick()
        rule.mainClock.advanceTimeBy(16)
        rule.mainClock.advanceTimeBy(4200); rule.waitForIdle()
        rule.waitUntil(5000) { store.state.value.selected == 5 && store.state.value.display != null }
        assertEquals(0, api.videoReads); assertEquals(0, api.originalReads)
        val readsAtLast = api.displayReads
        rule.mainClock.advanceTimeBy(4200); rule.waitForIdle()
        rule.onNodeWithTag("slideshow-complete").assertIsDisplayed()
        assertEquals(5, store.state.value.selected)
        rule.mainClock.advanceTimeBy(16000); rule.waitForIdle()
        assertEquals(readsAtLast, api.displayReads)
        rule.onNodeWithTag("slideshow-restart").performClick()
        rule.mainClock.advanceTimeBy(4200); rule.waitForIdle()
        rule.onNodeWithTag("slideshow-complete").assertIsDisplayed()
        assertEquals(5, store.state.value.selected)
        assertEquals(0, api.videoReads); assertEquals(0, api.originalReads)
    }
    @Test fun failedPhotoStopsWithoutShowingCompletion() {
        val api = SyntheticApi().apply { failedDisplayId = 2 }
        val store = install(api); gallery()
        rule.onNodeWithTag("asset-1").performClick(); rule.waitUntil(10000) { store.state.value.display != null }
        rule.onNodeWithTag("slideshow-speed-4").performClick()
        rule.mainClock.autoAdvance = false
        rule.onNodeWithTag("slideshow").performClick()
        rule.mainClock.advanceTimeBy(16)
        rule.mainClock.advanceTimeBy(4200); rule.waitForIdle()
        rule.waitUntil(5000) {
            store.state.value.mediaProblem != null || store.state.value.displayMissing || store.state.value.problem != null
        }
        // Catalog v1 surfaces a failed display as displayMissing; v2 keeps the selected asset and mediaProblem.
        assertTrue(store.state.value.displayMissing || store.state.value.mediaProblem != null || store.state.value.problem != null)
        rule.onNodeWithTag("slideshow-complete").assertDoesNotExist()
        rule.mainClock.advanceTimeBy(16000); rule.waitForIdle()
        assertNull(store.state.value.selected)
        rule.onNodeWithTag("slideshow-complete").assertDoesNotExist()
    }
    @Test fun pageChangeCancelsPlaybackWithoutResumingOnTheNewPage() {
        val api = SyntheticApi(); val store = install(api); gallery()
        rule.onNodeWithTag("asset-1").performClick(); rule.waitUntil(10000) { store.state.value.display != null }
        rule.onNodeWithTag("slideshow-speed-4").performClick()
        rule.mainClock.autoAdvance = false
        rule.onNodeWithTag("slideshow").performClick()
        rule.mainClock.advanceTimeBy(16)
        rule.mainClock.advanceTimeBy(3800); rule.waitForIdle()
        assertEquals(1, store.state.value.selected)
        rule.runOnUiThread { store.loadPage(2) }
        rule.waitUntil(10000) { store.state.value.feed?.page == 2 && !store.state.value.busy }
        val readsAfterPageChange = api.displayReads
        rule.mainClock.advanceTimeBy(20000); rule.waitForIdle()
        assertEquals(2, store.state.value.feed?.page)
        assertNull(store.state.value.selected)
        assertEquals(readsAfterPageChange, api.displayReads)
        rule.onNodeWithTag("slideshow-complete").assertDoesNotExist()
    }
    @Test fun openingDetailsWithRemotePausesAndClosingDoesNotResume() {
        val store = install(); gallery()
        rule.onNodeWithTag("asset-1").performClick()
        rule.waitUntil(10000) { store.state.value.display != null && !store.state.value.busy }
        rule.onNodeWithTag("slideshow-speed-4").performScrollTo()
        rule.onNodeWithTag("slideshow-speed-4").performClick()
        rule.mainClock.autoAdvance = false
        rule.onNodeWithTag("slideshow").performClick()
        rule.mainClock.advanceTimeBy(16)
        rule.mainClock.advanceTimeBy(1000); rule.waitForIdle()

        val details = rule.onNodeWithTag("captions")
        details.performScrollTo()
        details.assertIsDisplayed()
        details.performSemanticsAction(SemanticsActions.RequestFocus)
        rule.mainClock.advanceTimeBy(16); rule.waitForIdle()
        details.assertIsFocused()
        key(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.mainClock.advanceTimeBy(1000); rule.waitForIdle()
        rule.waitUntil(5000) { rule.onAllNodesWithTag("captions-close").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("slideshow").assertTextEquals("播放本页照片")
        rule.mainClock.advanceTimeBy(12000); rule.waitForIdle()
        assertEquals(1, store.state.value.selected)
        rule.onNodeWithTag("slideshow-complete").assertDoesNotExist()

        val close = rule.onNodeWithTag("captions-close")
        close.assertIsDisplayed()
        close.performClick()
        rule.mainClock.advanceTimeBy(1000); rule.waitForIdle()
        rule.waitUntil(5000) { rule.onAllNodesWithTag("captions-close").fetchSemanticsNodes().isEmpty() }
        rule.mainClock.advanceTimeBy(12000); rule.waitForIdle()
        assertEquals(1, store.state.value.selected)
        rule.onNodeWithTag("slideshow-complete").assertDoesNotExist()
    }
    @Test fun decoderPreservesExact4kAndRejectsMalformedOrOversizedInputs() {
        val full = requireNotNull(decodeTvPhoto(fixture("home-3840x2160.jpg")))
        assertEquals(3840, full.bitmap.width); assertEquals(2160, full.bitmap.height); assertFalse(full.downsampled)
        full.bitmap.recycle()
        assertNull(decodeTvPhoto(byteArrayOf(1, 2, 3)))
        assertNull(decodeTvPhoto(ByteArray(HomeLimits.DISPLAY_BYTES + 1)))
        assertNull(decodeTvPhoto(fixture("home-3840x2160.jpg") + byteArrayOf(1)))
        val grid = requireNotNull(decodeTvPhoto(fixture("home-8x8.jpg"), 262144))
        assertEquals(8, grid.bitmap.width); grid.bitmap.recycle()
    }
    @Test fun denialAndEmptyFeedStayClearWithoutSignIn() {
        val api = SyntheticApi().apply { denied = true }; val store = install(api)
        rule.onNodeWithText("Home feed is disabled", substring = true).assertExists()
        rule.onAllNodesWithTag("tv-image").assertCountEquals(0)
        rule.onAllNodes(hasSetTextAction()).assertCountEquals(0)
        capture("denied")
        api.denied = false; api.empty = true
        rule.runOnUiThread { store.retry() }; rule.waitForIdle()
        rule.waitUntil(5000) { store.state.value.feed?.items?.isEmpty() == true }
        rule.onNodeWithTag("gallery-empty-title").assertTextEquals("No photos here yet")
        rule.onNodeWithTag("empty-refresh").assertExists()
        capture("empty")
        val readsBeforeRefresh = api.feedReads
        rule.onNodeWithTag("empty-refresh").performClick(); rule.waitForIdle()
        assertTrue(api.feedReads > readsBeforeRefresh)
    }
}
