package dev.photohouse.connected

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import org.junit.*
import java.io.ByteArrayOutputStream
import java.io.File

class OnDemandPhotoTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    @Test fun optimizedPhotoOffersExplicitOriginalUpgradeInBothLanguages() {
        val bitmap=Bitmap.createBitmap(900,1200,Bitmap.Config.ARGB_8888).apply { eraseColor(0xff607b66.toInt()) }
        val bytes=ByteArrayOutputStream().use { out -> bitmap.compress(Bitmap.CompressFormat.JPEG,90,out);out.toByteArray() };bitmap.recycle()
        var zh by mutableStateOf(false)
        var original by mutableStateOf(false)
        rule.runOnUiThread { rule.activity.setContent { PhotoHouseTheme {
            OriginalPhotoViewer(bytes,false,zh,{}, originalQuality=original,onOriginal={original=true})
        } } }
        for (chinese in listOf(false,true)) {
            rule.runOnUiThread { zh=chinese;original=false }
            rule.waitUntil(10000) { rule.onAllNodesWithTag("original-image").fetchSemanticsNodes().size==1 }
            if (rule.onAllNodesWithTag("photo-exit-fullscreen").fetchSemanticsNodes().isNotEmpty()) rule.onNodeWithTag("photo-exit-fullscreen").performClick()
            rule.onNodeWithText(if(chinese) "原图画质" else "Original quality").performScrollTo().performClick()
            rule.onNodeWithText(if(chinese) "原始文件" else "Original file").performScrollTo().assertIsDisplayed()
            rule.onNodeWithText(if(chinese) "全屏" else "Full screen").performScrollTo().performClick()
            rule.onNodeWithTag("photo-exit-fullscreen").assertIsDisplayed().performClick()
            rule.waitForIdle()
            rule.runOnUiThread {
                val view=rule.activity.window.decorView;val image=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888)
                view.draw(Canvas(image));File(rule.activity.filesDir,"on-demand-phone-${if(chinese) "zh" else "en"}.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG,100,it) };image.recycle()
            }
        }
    }
}
