package dev.photohouse.stories.fixture

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.KeyEvent
import androidx.activity.compose.setContent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.stories.*
import java.io.File
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

/** Shared synthetic phone/TV screen checks. No production networking or private fixtures. */
class StoryFixtureUiTest {
    @get:Rule val rule = createAndroidComposeRule<StoryFixtureActivity>()
    private val controller get() = rule.activity.controller
    private fun install(tv: Boolean = false, role: StoryRole = StoryRole.VIEWER, zh: Boolean = false) {
        InstrumentationRegistry.getInstrumentation().setInTouchMode(false)
        rule.runOnUiThread { controller.activate(role, tv); rule.activity.setContent { StoryFixtureScreen(controller, tv, zh) } }
        rule.waitForIdle()
        rule.waitUntil(10000) { rule.activity.hasWindowFocus() }
    }
    private fun reveal(tag: String): SemanticsNodeInteraction {
        rule.onNodeWithTag("story-list").performScrollToNode(hasTestTag(tag)); return rule.onNodeWithTag(tag)
    }
    private fun key(code: Int) { if (code == KeyEvent.KEYCODE_BACK) {
        rule.runOnUiThread { (rule.activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).hideSoftInputFromWindow(rule.activity.window.decorView.windowToken, 0) }
        rule.waitUntil(5000) { androidx.core.view.ViewCompat.getRootWindowInsets(rule.activity.window.decorView)?.isVisible(androidx.core.view.WindowInsetsCompat.Type.ime()) != true }
    }; rule.waitUntil(10000) { rule.activity.hasWindowFocus() }; InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(code); rule.waitForIdle() }
    private fun capture(name: String) {
        rule.waitForIdle(); rule.runOnUiThread {
            val view = rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            File(rule.activity.filesDir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            bitmap.recycle()
        }
    }
    @Test fun phoneViewerReadsLongLiteralTextAndCannotEdit() {
        install(zh = true); reveal("story-card-sample-story").performClick()
        reveal("story-body").assertTextContains("<b>This stays literal</b>", substring = true)
        rule.onNodeWithTag("story-edit").assertDoesNotExist(); capture("story-phone-long-zh")
        key(KeyEvent.KEYCODE_BACK); rule.onNodeWithTag("story-query").assertExists()
    }
    @Test fun phoneSearchFiltersSourcesMediaAndEmptyResults() {
        install(); reveal("story-query").performTextInput("blue train")
        reveal("story-source-AI").performClick(); reveal("story-card-sample-ai").assertExists()
        rule.onNodeWithTag("story-card-sample-story").assertDoesNotExist()
        reveal("story-media-IMAGE").performClick(); reveal("story-empty").assertExists()
        capture("story-phone-empty")
    }
    @Test fun contributorKeepsDraftAcrossLostReplyAndRetriesSameSave() {
        install(role = StoryRole.CONTRIBUTOR); reveal("story-card-sample-story").performClick(); reveal("story-edit").performClick()
        reveal("story-text-input").performTextReplacement("A new sample memory / 新的示例回忆")
        reveal("story-lost").performClick(); rule.onNodeWithTag("story-problem").assertExists()
        val id = controller.state.value.pending!!.id
        reveal("story-text-input").assertIsNotEnabled(); capture("story-phone-retry")
        assertEquals(id, controller.beginSave()!!.id)
        reveal("story-save").performClick(); reveal("story-saved").assertExists()
        assertEquals(2L, controller.state.value.selected!!.revision)
    }
    @Test fun conflictComparisonRequiresExplicitRebaseAndBackConfirmsDiscard() {
        install(role = StoryRole.CONTRIBUTOR, zh = true)
        reveal("story-card-sample-story").performClick(); reveal("story-edit").performClick()
        reveal("story-text-input").performTextReplacement("保留这段话")
        reveal("story-conflict").performClick(); reveal("story-save").assertIsNotEnabled()
        reveal("story-current-version").assertExists(); capture("story-phone-conflict-zh")
        reveal("story-rebase").performClick(); reveal("story-save").assertIsEnabled()
        key(KeyEvent.KEYCODE_BACK); rule.onNodeWithTag("story-keep").assertExists().performClick()
        assertEquals("保留这段话", controller.state.value.draft!!.content.text)
        key(KeyEvent.KEYCODE_BACK); rule.onNodeWithTag("story-discard").performClick(); assertNull(controller.state.value.draft)
    }
    @Test fun accessLossAndBackgroundRemovePrivateTextAndDrafts() {
        install(role = StoryRole.CONTRIBUTOR); reveal("story-card-sample-story").performClick(); reveal("story-edit").performClick()
        reveal("story-deny").performClick(); rule.onNodeWithTag("story-covered").assertExists()
        rule.onNodeWithTag("story-text-input").assertDoesNotExist()
        rule.onNodeWithTag("story-reopen").performClick(); reveal("story-card-sample-story").performClick()
        rule.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.CREATED)
        assertNull(controller.state.value.scope)
        rule.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.RESUMED)
        rule.onNodeWithTag("story-covered").assertExists()
    }
    @Test fun tvShowsPublishedOnlyAndRemoteReadsScrollsAndReturns() {
        install(tv = true, zh = true)
        rule.onNodeWithTag("story-role-OWNER").assertDoesNotExist(); rule.onNodeWithTag("story-create").assertDoesNotExist()
        rule.onNodeWithTag("story-card-sample-private").assertDoesNotExist()
        reveal("story-card-sample-story").performSemanticsAction(SemanticsActions.RequestFocus)
        key(KeyEvent.KEYCODE_DPAD_CENTER); reveal("story-read-focus").performClick()
        rule.onNodeWithTag("story-body").assertIsFocused()
        val before = rule.onNodeWithTag("story-list").fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange].value()
        key(KeyEvent.KEYCODE_DPAD_DOWN)
        val after = rule.onNodeWithTag("story-list").fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange].value()
        assertTrue("Remote scroll must move the long text", after > before)
        capture("story-tv-long-zh")
        key(KeyEvent.KEYCODE_DPAD_UP); key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("story-query").assertExists(); rule.onNodeWithTag("story-back").assertIsFocused()
        rule.runOnUiThread { controller.withdrawPublication() }
        rule.onNodeWithTag("story-covered").assertExists()
    }
}
