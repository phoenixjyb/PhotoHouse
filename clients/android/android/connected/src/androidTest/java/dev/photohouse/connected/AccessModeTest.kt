package dev.photohouse.connected

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import android.accessibilityservice.AccessibilityService
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.io.File

class AccessModeTest {
    @get:Rule val rule=createAndroidComposeRule<AccessActivity>()
    private fun awaitTag(tag: String) {
        rule.waitUntil(10000) {
            // The activity being closed may briefly leave no Compose root during Back.
            try { rule.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }
            catch (_: IllegalStateException) { false }
        }
    }
    private fun backFrom(type: Class<out android.app.Activity>) {
        rule.waitUntil(10000) {
            var focused = false
            rule.runOnUiThread { focused = ActivityLifecycleMonitorRegistry.getInstance()
                .getActivitiesInStage(Stage.RESUMED).any { type.isInstance(it) && it.hasWindowFocus() } }
            focused
        }
        assertTrue(InstrumentationRegistry.getInstrumentation().uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
    }
    @Test fun explicitHomeAndSignInRoutesReturnToChooser() {
        rule.onNodeWithTag("access-home").assertExists()
        rule.runOnUiThread { val view=rule.activity.window.decorView;val b=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888)
            view.draw(Canvas(b));File(rule.activity.filesDir,"phone-access.png").outputStream().use { b.compress(Bitmap.CompressFormat.PNG,100,it) };b.recycle() }
        rule.onNodeWithTag("access-home").performScrollTo().performClick()
        rule.onNodeWithTag("home-setup").assertExists()
        backFrom(HomeActivity::class.java)
        awaitTag("access-account")
        rule.onNodeWithTag("access-account").performScrollTo().performClick()
        rule.onNodeWithTag("home-gallery").assertDoesNotExist()
        backFrom(MainActivity::class.java)
        awaitTag("access-home")
        rule.onNodeWithTag("access-home").assertExists()
    }
}
