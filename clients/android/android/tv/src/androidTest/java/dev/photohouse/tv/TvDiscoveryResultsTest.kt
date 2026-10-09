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

/** Synthetic app-domain integration: result isolation, player reuse, explicit recovery and memory clearing. */
class TvDiscoveryResultsTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @Before fun remoteInput() { InstrumentationRegistry.getInstrumentation().setInTouchMode(false) }
    @After fun finish() { scope.cancel() }
    private fun fixture(name: String) = InstrumentationRegistry.getInstrumentation().context.assets.open(name).use { it.readBytes() }
    private inner class Api(var empty: Boolean = false, var failure: HomeError? = null) : HomeApi {
        override val catalogVersion = 2
        override val retryRevisionChanges = false
        var reads = 0
        val sources = mutableListOf<HomeVideoReader>()
        override suspend fun feed(page: Int): HomeFeed {
            reads++; failure?.let { throw HomeFailure(it) }
            val feed = CatalogWire.feed(fixture("catalog-v2.json"), 1)
            return if (empty) feed.copy(total = 0, items = emptyList()) else feed
        }
        override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int) = fixture("home-8x8.jpg")
        override fun video(asset: HomeAsset, revision: Int, failed: (Exception) -> Unit): HomeVideoSource {
            val bytes = fixture("catalog-video.mp4")
            return HomeVideoReader(bytes.size.toLong(), 65536, { p, n -> bytes.copyOfRange(p.toInt(), p.toInt() + n) }, failed).also { sources += it }
        }
    }
    private inner class Gateway(val api: Api) : DiscoveryGateway {
        var failure: HomeError? = null
        var loads = 0
        val queries = mutableListOf<DiscoveryDraft>()
        override suspend fun load(): DiscoverySnapshot {
            loads++; failure?.let { throw HomeFailure(it) }
            val f = CatalogWire.feed(fixture("catalog-v2.json"), 1)
            return DiscoverySnapshot(7, f.revision, f.id, f.title,
                DiscoveryOptions(setOf(DiscoveryField.PEOPLE, DiscoveryField.MEDIA),
                    people = listOf(DiscoveryChoice("1", "Sample person", listOf("示例家人")))))
        }
        override suspend fun more(snapshot: DiscoverySnapshot, field: DiscoveryField) = snapshot
        override fun results(snapshot: DiscoverySnapshot, draft: DiscoveryDraft): HomeApi { queries += draft; return api }
    }
    private fun install(base: Api, gateway: Gateway): Pair<HomeStore, DiscoveryController> {
        val browse = HomeStore(base, scope)
        val controller = DiscoveryController(gateway, browse, scope)
        rule.runOnUiThread { rule.activity.setContent { TvApp(browse, controller) }; browse.foreground() }
        rule.waitForIdle(); return browse to controller
    }
    private fun search() {
        rule.showAction("explore")
        rule.onNodeWithTag("explore").performClick()
        rule.waitUntil(10000) { rule.onAllNodesWithTag("quick-person-1").fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("quick-person-1").performClick(); rule.waitForIdle()
    }
    private fun key(code: Int) {
        rule.waitUntil(10000) { rule.activity.hasWindowFocus() }
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(code); rule.waitForIdle()
    }
    private fun capture(name: String) {
        rule.waitForIdle(); rule.runOnUiThread {
            val view = rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            File(rule.activity.filesDir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            bitmap.recycle()
        }
    }
    @Test fun filteredGalleryReusesPhotoAndVideoAndReturnsToSameSelection() {
        val base = Api(); val result = Api(); val gateway = Gateway(result)
        val (_, controller) = install(base, gateway); search()
        rule.onNodeWithTag("applied-search").assertExists()
        assertEquals(listOf(DiscoveryDraft(people = setOf("1"))), gateway.queries)
        assertEquals(1, base.reads); capture("discovery-results")
        rule.onNodeWithTag("asset-101").performClick()
        rule.waitUntil(10000) { rule.onAllNodesWithTag("tv-image").fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("photo-zoom").performScrollTo().performClick()
        rule.onNodeWithTag("immersive").assertExists()
        key(KeyEvent.KEYCODE_BACK); key(KeyEvent.KEYCODE_BACK); key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("asset-101").assertIsFocused()
        rule.onNodeWithTag("asset-102").performClick()
        rule.waitUntil(15000) { rule.onAllNodes(hasTestTag("video-play") and isEnabled()).fetchSemanticsNodes().size == 1 }
        key(KeyEvent.KEYCODE_BACK); assertTrue(result.sources.single().isClosed)
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("asset-102").assertIsFocused()
        assertEquals(setOf("1"), controller.state.value.query!!.people)
        rule.showAction("clear-results")
        rule.onNodeWithTag("clear-results").performScrollTo().performClick()
        rule.onNodeWithTag("applied-search").assertDoesNotExist(); assertEquals(2, base.reads)
    }
    @Test fun emptyAndChangedSearchNeverFallBackAndEditingRefreshesMetadata() {
        val base = Api(); val result = Api(empty = true); val gateway = Gateway(result)
        install(base, gateway); search()
        rule.onNodeWithText("No matching memories. Try fewer filters.").assertExists()
        rule.onNodeWithTag("asset-101").assertDoesNotExist(); capture("discovery-empty")
        result.failure = HomeError.CHANGED
        rule.showAction("explore"); rule.onNodeWithText("Refresh", substring = false).performClick()
        rule.onNodeWithText("The library changed. Edit filters to start a fresh search.").assertExists()
        assertEquals(1, base.reads)
        result.failure = null
        rule.showAction("edit-search")
        rule.onNodeWithTag("edit-search").performClick()
        rule.waitUntil(10000) { gateway.loads == 2 }
        rule.onNodeWithTag("quick-person-1").performClick()
        rule.onNodeWithText("No matching memories. Try fewer filters.").assertExists()
        assertEquals(2, gateway.queries.size)
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("applied-search").assertDoesNotExist()
        rule.waitUntil(10000) { rule.onAllNodes(hasTestTag("gallery-more") and isFocused()).fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("gallery-more").assertIsFocused(); assertEquals(2, base.reads)
    }
    @Test fun metadataRetryAndDeniedResultsClearPrivateStateWithoutFallback() {
        val base = Api(); val gateway = Gateway(Api(failure = HomeError.DENIED)).apply { failure = HomeError.OFFLINE }
        val (browse, controller) = install(base, gateway)
        rule.showAction("explore")
        rule.onNodeWithTag("explore").performClick()
        rule.onNodeWithTag("discovery-error").assertExists(); capture("discovery-error")
        assertTrue(gateway.queries.isEmpty()); gateway.failure = null
        rule.onNodeWithTag("retry-discovery").performClick()
        rule.waitUntil(10000) { rule.onAllNodesWithTag("quick-person-1").fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("quick-person-1").performClick()
        rule.waitUntil(10000) { browse.state.value.problem == HomeError.DENIED && controller.state.value.query == null }
        assertNull(controller.state.value.snapshot); assertNull(browse.state.value.feed)
        assertEquals(1, base.reads); rule.onNodeWithTag("asset-101").assertDoesNotExist()
    }
}
