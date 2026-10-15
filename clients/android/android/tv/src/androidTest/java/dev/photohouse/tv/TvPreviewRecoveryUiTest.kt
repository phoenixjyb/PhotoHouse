package dev.photohouse.tv

import android.content.res.Configuration
import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.Canvas
import android.os.Environment
import android.provider.MediaStore
import android.view.KeyEvent
import androidx.activity.compose.setContent
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.home.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class TvPreviewRecoveryUiTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val previewBytes by lazy {
        InstrumentationRegistry.getInstrumentation().context.assets.open("home-8x8.jpg").use { it.readBytes() }
    }

    @After fun finish() { scope.cancel() }

    private class SyntheticApi(private val fixture: ByteArray) : HomeApi {
        override val catalogVersion = 3
        var feedReads = 0
        var gridReads = 0
        var displayReads = 0
        var originalReads = 0
        var retrySucceeds = false
        var failRetries = false

        private val assets = (1..2).map { id ->
            val grid = Preview(8, 8, fixture.size, "", "/home/v3/assets/$id/preview?variant=grid&revision=1", true)
            val display = Preview(8, 8, fixture.size, "", "/home/v3/assets/$id/preview?variant=display&revision=1", true)
            HomeAsset(id, "Synthetic memory $id", grid, display,
                original = HomeOriginal("image/jpeg", fixture.size, 8, 8, "/home/v3/assets/$id/original?revision=1"))
        }

        override suspend fun feed(page: Int): HomeFeed {
            feedReads++
            return HomeFeed(1, "synthetic-preview-recovery", "Synthetic album", page, 50, assets.size,
                hasMore = page == 1, items = if (page == 1) assets else emptyList(), version = 3)
        }

        override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray {
            when (variant) {
                Variant.GRID -> {
                    gridReads++
                    if (asset.id == 1 && (!retrySucceeds || failRetries)) throw HomeFailure(HomeError.OFFLINE)
                }
                Variant.DISPLAY -> displayReads++
            }
            return fixture
        }

        override suspend fun original(asset: HomeAsset, revision: Int): ByteArray {
            originalReads++
            return fixture
        }
    }

    private fun install(api: SyntheticApi, language: String): HomeStore {
        val store = HomeStore(api, scope)
        rule.runOnUiThread {
            rule.activity.setContent {
                val baseDensity = LocalDensity.current
                val largeLandscape = Configuration(LocalConfiguration.current).apply {
                    orientation = Configuration.ORIENTATION_LANDSCAPE
                    fontScale = 1.5f
                }
                CompositionLocalProvider(
                    LocalConfiguration provides largeLandscape,
                    LocalDensity provides Density(baseDensity.density, 1.5f),
                ) { TvApp(store, initialLanguage = language) }
            }
            store.foreground()
        }
        rule.waitUntil(10_000) { store.state.value.gridProblems.containsKey(1) && !store.state.value.busy }
        return store
    }

    private fun focusAndPressCenter(tag: String) {
        val node = rule.onNodeWithTag(tag)
        node.performSemanticsAction(SemanticsActions.RequestFocus)
        node.assertIsFocused()
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.waitForIdle()
    }

    private fun saveRender(name: String) {
        rule.waitForIdle()
        rule.runOnUiThread {
            val view = rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            val context = rule.activity
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, "$name.png")
                put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/PhotoHouseTvPreviewRecovery")
            }
            val uri = requireNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
            context.contentResolver.openOutputStream(uri).use { stream ->
                requireNotNull(stream).use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            }
            bitmap.recycle()
        }
    }

    @Test fun englishRemoteRetryRecoversCurrentPageAndKeepsReturnActionFocused() {
        val api = SyntheticApi(previewBytes)
        val store = install(api, "en")
        rule.onNodeWithTag("preview-recovery").assertIsDisplayed()
        rule.onNodeWithTag("preview-recovery-status").assertTextEquals("1 preview unavailable on this page.")
        rule.onNodeWithTag("preview-recovery-action").assertTextEquals("Retry previews")
        saveRender("tv-preview-recovery-en-150")

        val feedsBeforeRetry = api.feedReads
        api.retrySucceeds = true
        focusAndPressCenter("preview-recovery-action")
        rule.waitUntil(10_000) { store.state.value.grids.containsKey(1) && store.state.value.gridProblems.isEmpty() }
        rule.onNodeWithTag("preview-recovery-status").assertTextContains("Preview retry complete", substring = true)
        rule.onNodeWithTag("preview-recovery-action").assertTextEquals("Return to gallery").assertIsFocused()
        assertEquals("Retry does not reload the gallery feed", feedsBeforeRetry, api.feedReads)
        assertEquals("The retry reads only the missing page preview, not display or original bytes", 3, api.gridReads)
        assertEquals(0, api.displayReads)
        assertEquals(0, api.originalReads)
        saveRender("tv-preview-recovery-en-complete-150")

        focusAndPressCenter("preview-recovery-action")
        rule.onNodeWithTag("preview-recovery").assertDoesNotExist()
    }

    @Test fun chineseLargeTextKeepsFailedRetryVisibleAndRequiresAnotherExplicitTap() {
        val api = SyntheticApi(previewBytes).apply { failRetries = true }
        val store = install(api, "zh")
        rule.onNodeWithTag("preview-recovery").assertIsDisplayed()
        rule.onNodeWithTag("preview-recovery-status").assertTextEquals("本页有 1 个预览不可用。")
        rule.onNodeWithTag("preview-recovery-action").assertTextEquals("重试预览")
        saveRender("tv-preview-recovery-zh-150")

        focusAndPressCenter("preview-recovery-action")
        val actionAfterTap = rule.onNodeWithTag("preview-recovery-action").fetchSemanticsNode()
            .config[SemanticsProperties.Text].joinToString { it.text }
        assertTrue("Explicit retry is tapped and the recovery action remains visible", actionAfterTap != "重试预览")
        rule.waitUntil(10_000) { api.gridReads >= 3 && store.state.value.gridProblems.containsKey(1) }
        rule.onNodeWithTag("preview-recovery-action").assertTextEquals("重试剩余预览").assertIsFocused()
        val readsAfterExplicitRetry = api.gridReads
        Thread.sleep(250)
        rule.waitForIdle()
        assertEquals("A failed retry does not trigger another attempt automatically", readsAfterExplicitRetry, api.gridReads)
        assertEquals(HomeError.OFFLINE, store.state.value.gridProblems[1])

        focusAndPressCenter("preview-recovery-action")
        rule.waitUntil(10_000) { api.gridReads >= readsAfterExplicitRetry + 1 && store.state.value.gridProblems.containsKey(1) }
        rule.onNodeWithTag("preview-recovery-status").assertTextEquals("仍有 1 个预览不可用。")
        rule.onNodeWithTag("preview-recovery-action").assertTextEquals("重试剩余预览").assertIsFocused()
    }

    @Test fun pageChangeDropsTheOldPageRetryAction() {
        val api = SyntheticApi(previewBytes)
        val store = install(api, "en")
        rule.onNodeWithTag("preview-recovery-action").assertExists()
        rule.runOnUiThread { store.loadPage(2) }
        rule.waitUntil(10_000) { store.state.value.feed?.page == 2 && !store.state.value.busy }
        rule.onNodeWithTag("preview-recovery").assertDoesNotExist()
        rule.showAction("retry-previews")
        rule.onNodeWithTag("retry-previews").assertDoesNotExist()
    }
}
