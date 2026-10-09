package dev.photohouse.fixture

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.WindowManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.Lifecycle
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.fixture.core.Notice
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class FixtureUiTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val store get() = rule.activity.store
    private fun click(tag: String) {
        rule.onNodeWithTag("screen").performScrollToNode(hasTestTag(tag))
        rule.onNodeWithTag(tag).performClick()
    }
    private fun settled() { rule.waitUntil(10000) { !store.state.value.busy }; rule.waitForIdle() }
    private fun signIn() { click("sign-in"); settled(); assertNotNull(store.state.value.session) }
    private fun gallery() { signIn(); click("library-family-a"); settled(); assertEquals(2, store.state.value.gallery!!.items.size) }
    private fun capture(name: String) {
        rule.waitForIdle()
        rule.runOnUiThread {
            val view = rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            // Synthetic-only test rendering of our own View; FLAG_SECURE stays set.
            val suffix = if (rule.activity.resources.configuration.fontScale > 1.3f) "large" else "normal"
            File(rule.activity.filesDir, "$name-$suffix.png").outputStream().use {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            }
            bitmap.recycle()
        }
    }
    @Test fun approvedFlowLanguagesAndLiteralCaptions() {
        rule.onNodeWithTag("fixture-banner").assertIsDisplayed()
        capture("signin-en")
        gallery()
        rule.onNodeWithContentDescription("Synthetic photo 101").assertExists()
        capture("gallery-en")
        click("asset-101"); settled()
        rule.onNodeWithTag("screen").performScrollToNode(hasTestTag("caption-101"))
        rule.onNodeWithText("Synthetic hillside. 合成山景。").assertIsDisplayed()
        capture("caption-en")
        click("language-zh")
        rule.onNodeWithTag("screen").performScrollToNode(hasTestTag("caption-101"))
        rule.onNodeWithText("Synthetic hillside. 合成山景。").assertIsDisplayed()
        capture("caption-zh")
        click("back-photos"); settled(); capture("gallery-zh")
        click("logout"); settled(); assertNull(store.state.value.session)
        rule.onNodeWithTag("sign-in").assertExists()
        capture("signedout-zh")
    }
    @Test fun invitedAndInvalidAdmission() {
        click("invalid-invite"); settled()
        assertFalse(store.hasToken); assertEquals(Notice.INVALID_INVITATION, store.state.value.problem!!.notice)
        click("register"); settled()
        assertEquals("viewer", store.state.value.session!!.memberships.single().role)
        click("library-family-a"); settled(); assertNotNull(store.state.value.gallery)
    }
    @Test fun unavailableMembershipHasDisabledBrowseControl() {
        click("profile-demos"); click("profile-membership-expired"); settled()
        rule.onNodeWithTag("library-family-a").assertIsNotEnabled()
        assertNull(store.state.value.gallery); assertEquals(0, store.cacheEntries)
    }
    @Test fun videoAndMarkupUseLiteralTextAndNoOriginalFallback() {
        gallery(); click("asset-102"); settled()
        rule.onNodeWithTag("screen").performScrollToNode(hasTestTag("video-unavailable"))
        rule.onNodeWithTag("video-unavailable").assertIsDisplayed()
        rule.onNodeWithTag("screen").performScrollToNode(hasTestTag("caption-102"))
        rule.onNodeWithText("<script>synthetic text only</script>").assertIsDisplayed()
        capture("video-literal-caption")
    }
    @Test fun lifecycleCoversAndClearsThenRevalidatesBeforeBrowsing() {
        gallery()
        assertTrue(rule.activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE != 0)
        rule.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
        assertTrue(store.state.value.covered); assertNull(store.state.value.session)
        assertEquals(0, store.cacheEntries); assertNull(store.state.value.gallery)
        rule.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
        settled()
        assertFalse(store.state.value.covered); assertNotNull(store.state.value.session)
        assertNull(store.state.value.gallery)
        click("library-family-a"); settled()
        rule.runOnUiThread { store.background(); store.foreground("unavailable") }
        settled()
        rule.onNodeWithTag("privacy-cover").assertExists(); assertTrue(store.hasToken)
        capture("covered-unavailable")
        click("logout"); settled(); assertFalse(store.hasToken)
    }
    @Test fun emptyAndMissingPreviewAreDistinctRenderedStates() {
        gallery(); click("gallery-demos"); click("missing-preview"); settled()
        rule.onNodeWithTag("screen").performScrollToNode(hasTestTag("asset-101"))
        rule.onNodeWithTag("preview-missing-101", useUnmergedTree = true).assertExists()
        assertEquals(0, store.cacheEntries)
        capture("missing-previews")
        click("gallery-demos"); click("empty-page"); settled()
        rule.onNodeWithTag("empty-gallery").assertExists(); assertNull(store.state.value.problem)
        capture("empty-page")
    }
}
