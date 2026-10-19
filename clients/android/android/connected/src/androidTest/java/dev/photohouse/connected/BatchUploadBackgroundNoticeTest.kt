package dev.photohouse.connected

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class BatchUploadBackgroundNoticeTest {
    @get:Rule val compose = createComposeRule()
    @Test fun chineseAtLargeText() = render(true)
    @Test fun englishAtLargeText() = render(false)
    private fun render(zh: Boolean) {
        var prompts = 0
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme { Column(Modifier.padding(16.dp)) {
                    BatchUploadBackgroundNotice(zh, false) { prompts++ }
                } }
            }
        }
        compose.onNodeWithTag("batch-background-explanation").assertIsDisplayed()
        compose.onNodeWithTag("batch-enable-notifications").assertIsDisplayed().performClick()
        compose.runOnIdle { assertEquals(1,prompts) }
        val bitmap = compose.onRoot().captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        check(context.packageName == "dev.photohouse.connected.qa")
        context.getExternalFilesDir(null)!!.resolve("background-upload-${if (zh) "zh" else "en"}-150.png")
            .outputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG,100,it) }
    }
}
