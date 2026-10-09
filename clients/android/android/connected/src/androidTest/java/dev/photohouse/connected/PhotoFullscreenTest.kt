package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import dev.photohouse.connected.core.PhotoNavigation
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File

/** No network or family media: verifies actual window bounds, not a fullscreen label. */
class PhotoFullscreenTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Test fun photoFillsWindowAndControlsNeverShrinkItDuringNavigation() {
        val bitmap = Bitmap.createBitmap(900, 1200, Bitmap.Config.ARGB_8888).apply { eraseColor(0xff607b66.toInt()) }
        val bytes = ByteArrayOutputStream().use { out -> bitmap.compress(Bitmap.CompressFormat.PNG, 100, out); out.toByteArray() }
        bitmap.recycle()
        var index by mutableIntStateOf(0)
        rule.runOnUiThread { rule.activity.setContent { PhotoHouseTheme {
            OriginalPhotoViewer(bytes, false, false, {}, PhotoNavigation(1, listOf("1", "2"), index),
                onAdjacent = { index += it })
        } } }
        rule.waitUntil(10000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("photo-controls").assertDoesNotExist()
        fun viewportMatchesWindow() {
            val bounds = rule.onNodeWithTag("photo-viewport").fetchSemanticsNode().boundsInWindow
            rule.runOnIdle {
                val window = rule.activity.window.decorView
                assertEquals(0f, bounds.left, 1f); assertEquals(0f, bounds.top, 1f)
                assertEquals(window.width.toFloat(), bounds.width, 1f)
                assertEquals(window.height.toFloat(), bounds.height, 1f)
            }
        }
        viewportMatchesWindow()
        rule.onNodeWithTag("photo-fullscreen-previous").assertIsNotEnabled()
        rule.onNodeWithTag("photo-fullscreen-next").performClick()
        rule.runOnIdle { assertEquals(1, index) }
        rule.onNodeWithTag("photo-fullscreen-next").assertIsNotEnabled()
        rule.onNodeWithTag("photo-fullscreen-previous").performClick()
        rule.onNodeWithTag("photo-exit-fullscreen").performClick()
        viewportMatchesWindow()
        rule.onNodeWithTag("photo-fit-width").performScrollTo().performClick()
        viewportMatchesWindow()
        rule.onNode(hasText("Full screen") and hasClickAction()).performScrollTo().performClick()
        val image = rule.onRoot().captureToImage().asAndroidBitmap()
        File(rule.activity.filesDir, "photo-full-window.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
        // Tap away from the overlaid navigation controls; a second tap restores immersion.
        rule.onNodeWithTag("photo-viewport").performTouchInput { click(center) }
        rule.mainClock.advanceTimeBy(400) // single tap waits for the double-tap gesture window
        rule.waitUntil(5000) { rule.onAllNodesWithTag("photo-controls").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("photo-controls").assertExists()
        viewportMatchesWindow()
        rule.onNodeWithTag("photo-viewport").performTouchInput { click(androidx.compose.ui.geometry.Offset(width / 2f, height / 4f)) }
        rule.mainClock.advanceTimeBy(400)
        rule.waitUntil(5000) { rule.onAllNodesWithTag("photo-controls").fetchSemanticsNodes().isEmpty() }
        rule.onNodeWithTag("photo-controls").assertDoesNotExist()
        viewportMatchesWindow()
    }
}
