package dev.photohouse.tv

import android.view.KeyEvent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.home.*
import kotlinx.coroutines.runBlocking
import org.junit.*
import org.junit.Assume.assumeTrue
import org.junit.rules.RuleChain
import org.junit.rules.TestRule
import org.junit.runners.model.Statement

/** Excluded from ordinary component runs. No family-media screenshots or files are saved. */
@Retention(AnnotationRetention.RUNTIME)
@Target(AnnotationTarget.CLASS, AnnotationTarget.FUNCTION)
annotation class LiveCatalogOnly

@LiveCatalogOnly
class TvLiveCatalogTest {
    val rule = createAndroidComposeRule<MainActivity>()
    private val args get() = InstrumentationRegistry.getArguments()
    // Gate before the Activity rule launches networking, not in an after-launch @Before.
    @get:Rule val guarded: TestRule = RuleChain.outerRule(TestRule { base, _ ->
        object : Statement() {
            override fun evaluate() {
                assumeTrue("Explicit live approval required", args.getString("liveApproved") == "true")
                check(BuildConfig.PHOTOHOUSE_CATALOG_VERSION == 2 && BuildConfig.PHOTOHOUSE_ORIGIN.isNotEmpty())
                base.evaluate()
            }
        }
    }).around(rule)
    @Before fun connected() {
        rule.waitUntil(20000) { rule.onAllNodesWithTag("grid").fetchSemanticsNodes().size == 1 }
    }
    private fun open(kind: String) {
        val id = requireNotNull(args.getString("${kind}Id")).toInt()
        val index = requireNotNull(args.getString("${kind}Index")).toInt()
        rule.onNodeWithTag("grid").performScrollToIndex(index)
        rule.onNodeWithTag("asset-$id").performClick()
        if (kind == "photo") {
            rule.waitUntil(20000) { rule.onAllNodesWithTag("tv-image").fetchSemanticsNodes().size == 1 }
            rule.onNodeWithTag("tv-image").assertIsDisplayed()
        }
    }
    @Test fun livePreparedPreviewsDecode() = runBlocking {
        val origin = HomeOrigin.parse(BuildConfig.PHOTOHOUSE_ORIGIN)
        val api = if (BuildConfig.PHOTOHOUSE_LAN_ADDRESS.isEmpty()) HttpsCatalogApi(origin)
            else HttpsCatalogApi(origin, HomeLanAddress.parse(BuildConfig.PHOTOHOUSE_LAN_ADDRESS))
        val feed = api.feed(requireNotNull(args.getString("previewPage")).toInt())
        val prepared = feed.items.filter { it.grid != null && it.display != null }
        Assert.assertEquals(requireNotNull(args.getString("expectedPrepared")).toInt(), prepared.size)
        for (asset in prepared) for (variant in listOf(Variant.GRID, Variant.DISPLAY)) {
            val bytes = requireNotNull(api.preview(asset, variant, feed.revision)) { "Published preview missing" }
            val decoded = requireNotNull(decodeTvPhoto(bytes, if (variant == Variant.GRID) 262144 else 8847360)) { "Published preview did not decode" }
            decoded.bitmap.recycle()
        }
    }
    @Test fun livePhotoOpensAndZooms() {
        open("photo")
        rule.onNodeWithTag("photo-zoom").performScrollTo().performClick()
        rule.onNodeWithTag("immersive").assertExists()
        rule.waitUntil(10000) { runCatching { rule.onNodeWithTag("tv-image").assertIsDisplayed() }.isSuccess }
        rule.onNodeWithTag("tv-image").assertIsDisplayed()
    }
    @Test fun liveVideoPreparesAndPlays() {
        open("video")
        rule.waitUntil(30000) { rule.onAllNodes(hasTestTag("video-play") and isEnabled()).fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("video-play").performClick()
        rule.waitUntil(10000) {
            rule.onNodeWithTag("video-position").fetchSemanticsNode().config
                .getOrElse(androidx.compose.ui.semantics.SemanticsProperties.Text) { emptyList() }
                .any { !it.text.startsWith("0:00") }
        }
    }
    @Test fun livePageJumpAndPreviousPage() {
        rule.onNodeWithTag("page-jump").performClick()
        rule.waitUntil(10000) { rule.onAllNodes(hasTestTag("page-plus-one") and isFocused()).fetchSemanticsNodes().size == 1 }
        for (code in listOf(KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_CENTER)) {
            InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(code); rule.waitForIdle()
        }
        rule.waitUntil(20000) { rule.onAllNodesWithText("Page 2 of", substring = true).fetchSemanticsNodes().size == 1 }
        rule.onNodeWithText("Previous page", substring = false).performScrollTo().performClick()
        rule.waitUntil(20000) { rule.onAllNodesWithText("Page 1 of", substring = true).fetchSemanticsNodes().size == 1 }
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_BACK)
    }
}
