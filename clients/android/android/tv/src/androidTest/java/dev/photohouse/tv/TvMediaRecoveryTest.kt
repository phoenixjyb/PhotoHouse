package dev.photohouse.tv

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.home.*
import kotlinx.coroutines.*
import org.junit.*
import org.junit.Assert.*
import java.io.File

class TvMediaRecoveryTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun finish() { scope.cancel() }
    @Test fun nativeReadFailureStaysInViewerWithDiagnosticAndRetryControls() {
        val asset = HomeAsset(1, "Synthetic video", null, null, AssetKind.VIDEO,
            HomeVideo(320, 180, 1000, 1024, "0".repeat(64), "/home/v3/assets/1/video?revision=1", "aac"))
        val api = object : HomeApi {
            override val catalogVersion = 3
            override suspend fun feed(page: Int) = HomeFeed(1,"synthetic","Our home",1,50,1,false,listOf(asset),3)
            override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray? = null
            override fun video(asset: HomeAsset, revision: Int, failed: (Exception) -> Unit): HomeVideoSource =
                HomeVideoReader(1024, 1024, { _, _ -> throw HomeFailure(HomeError.OFFLINE) }, failed)
        }
        val store = HomeStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { TvApp(store) }; store.foreground() }
        rule.onNodeWithTag("asset-1").performClick()
        rule.waitUntil(15000) { rule.onAllNodesWithTag("video-error").fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("video-error").assertTextContains("TV-READ-OFFLINE", substring = true)
        rule.onNodeWithTag("open-video").assertExists()
        rule.onNodeWithTag("grid").assertDoesNotExist()
        assertEquals(1, store.state.value.selected); assertNotNull(store.state.value.feed)
        rule.showAction("language")
        rule.onNodeWithTag("language").performClick()
        rule.onNodeWithTag("video-error").assertTextContains("TV-READ-OFFLINE", substring = true)
        rule.runOnUiThread {
            val view = rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            File(rule.activity.filesDir, "media-recovery.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
            bitmap.recycle()
        }
    }
    @Test fun failedPreviewCanBeRetriedWithoutReloadingCatalog() {
        val bytes = InstrumentationRegistry.getInstrumentation().context.assets.open("home-8x8.jpg").use { it.readBytes() }
        val p = Preview(0,0,Variant.GRID.bytes,"","/home/v3/assets/1/preview?variant=grid&revision=1",true)
        val asset = HomeAsset(1,"Synthetic photo",p,p)
        var offline = true; var feeds = 0
        val api = object : HomeApi {
            override val catalogVersion = 3
            override suspend fun feed(page: Int): HomeFeed { feeds++; return HomeFeed(1,"synthetic","Our home",1,50,1,false,listOf(asset),3) }
            override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray {
                if (offline) throw HomeFailure(HomeError.OFFLINE)
                return bytes
            }
        }
        val store = HomeStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { TvApp(store) }; store.foreground() }
        rule.showAction("retry-previews")
        rule.onNodeWithTag("retry-previews").assertExists()
        rule.runOnUiThread { offline = false }
        rule.showAction("retry-previews")
        rule.onNodeWithTag("retry-previews").performClick()
        rule.waitUntil(10000) { rule.onAllNodesWithTag("tv-image", useUnmergedTree = true).fetchSemanticsNodes().size == 1 }
        assertNotNull(store.state.value.grids[1])
        assertTrue(store.state.value.gridProblems.isEmpty())
        rule.onNodeWithTag("retry-previews").assertDoesNotExist(); assertEquals(1,feeds)
    }
}
