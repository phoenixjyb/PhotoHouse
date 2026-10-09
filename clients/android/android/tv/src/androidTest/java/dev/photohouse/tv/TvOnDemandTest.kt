package dev.photohouse.tv

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import dev.photohouse.home.*
import kotlinx.coroutines.*
import org.junit.*
import org.junit.Assert.*
import java.io.ByteArrayOutputStream
import java.io.File

class TvOnDemandTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun finish() { scope.cancel() }
    @Test fun originalQualityPhotoOpensWithRemoteControlsAndClearsOnBackground() {
        val bitmap = Bitmap.createBitmap(1200, 800, Bitmap.Config.ARGB_8888).apply { eraseColor(0xff607b66.toInt()) }
        fun encode(format: Bitmap.CompressFormat) = ByteArrayOutputStream().use { out -> bitmap.compress(format, 90, out); out.toByteArray() }
        val original = encode(Bitmap.CompressFormat.PNG); val preview = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets.open("home-8x8.jpg").use { it.readBytes() }; bitmap.recycle()
        val p = Preview(0, 0, Variant.DISPLAY.bytes, "", "/home/v3/assets/1/preview?variant=display&revision=1", true)
        val asset = HomeAsset(1, "A quiet afternoon / 午后时光", null, p, original = HomeOriginal("image/png", original.size, 1200, 800, "/home/v3/assets/1/original?revision=1"))
        val api = object : HomeApi {
            override val catalogVersion = 3
            override suspend fun feed(page: Int) = HomeFeed(1,"synthetic","Our home",1,50,1,false,listOf(asset),3)
            override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int) = preview
            override suspend fun original(asset: HomeAsset, revision: Int) = original
        }
        val store = HomeStore(api, scope)
        rule.runOnUiThread { rule.activity.setContent { TvApp(store) }; store.foreground() }
        rule.onNodeWithTag("asset-1").performClick()
        rule.waitUntil(10000) { rule.onAllNodesWithTag("tv-image").fetchSemanticsNodes().size == 1 }
        rule.onNodeWithTag("photo-original").performScrollTo().performClick()
        rule.waitUntil(10000) { store.state.value.originalQuality && !store.state.value.busy }
        rule.onNodeWithTag("photo-original").assertIsNotEnabled()
        rule.onNodeWithTag("photo-zoom").performScrollTo().performClick()
        rule.onNodeWithTag("immersive").assertExists()
        rule.waitForIdle()
        rule.runOnUiThread {
            val view=rule.activity.window.decorView;val image=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888)
            view.draw(Canvas(image));File(rule.activity.filesDir,"on-demand-tv.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG,100,it) };image.recycle()
            store.background()
        }
        rule.onNodeWithTag("covered").assertExists(); assertNull(store.state.value.display)
    }
    @Test fun originalDecoderRejectsCorruptionBoundsPixelsAndHandlesAllExifOrientations() {
        assertNull(decodeTvOriginal(byteArrayOf(1, 2, 3)))
        val large = Bitmap.createBitmap(4200, 2400, Bitmap.Config.ARGB_8888)
        large.eraseColor(android.graphics.Color.BLUE)
        val bytes = java.io.ByteArrayOutputStream().use { stream ->
            large.compress(Bitmap.CompressFormat.PNG, 100, stream); large.recycle(); stream.toByteArray()
        }
        val reduced = requireNotNull(decodeTvOriginal(bytes))
        assertTrue(reduced.downsampled); assertTrue(reduced.bitmap.width.toLong() * reduced.bitmap.height <= 8_847_360)
        reduced.bitmap.recycle()
        val landscape = Bitmap.createBitmap(200, 100, Bitmap.Config.ARGB_8888)
        val jpeg = java.io.ByteArrayOutputStream().use { stream ->
            landscape.compress(Bitmap.CompressFormat.JPEG, 90, stream); landscape.recycle(); stream.toByteArray()
        }
        // Generated EXIF APP1 segment: little-endian TIFF with orientation 6.
        val tiff = java.nio.ByteBuffer.allocate(26).order(java.nio.ByteOrder.LITTLE_ENDIAN)
            .put(0x49.toByte()).put(0x49.toByte()).putShort(42.toShort()).putInt(8).putShort(1.toShort())
            .putShort(0x112.toShort()).putShort(3.toShort()).putInt(1).putShort(6.toShort()).putShort(0.toShort()).putInt(0).array()
        val exif = byteArrayOf(0xff.toByte(), 0xe1.toByte(), 0, 34) + byteArrayOf(69, 120, 105, 102, 0, 0) + tiff
        val rotated = requireNotNull(decodeTvOriginal(jpeg.copyOfRange(0, 2) + exif + jpeg.copyOfRange(2, jpeg.size)))
        assertEquals(100, rotated.bitmap.width); assertEquals(200, rotated.bitmap.height); rotated.bitmap.recycle()
        val colors = intArrayOf(0xffff0000.toInt(), 0xff00ff00.toInt(), 0xff0000ff.toInt(), 0xffffffff.toInt(), 0xffffff00.toInt(), 0xff00ffff.toInt())
        val orders = listOf(listOf(0,1,2,3,4,5), listOf(2,1,0,5,4,3), listOf(5,4,3,2,1,0),
            listOf(3,4,5,0,1,2), listOf(0,3,1,4,2,5), listOf(3,0,4,1,5,2),
            listOf(5,2,4,1,3,0), listOf(2,5,1,4,0,3))
        for (orientation in 1..8) {
            val input = Bitmap.createBitmap(colors, 3, 2, Bitmap.Config.ARGB_8888)
            val output = orientTvOriginal(input, orientation)
            assertEquals(if (orientation < 5) 3 else 2, output.width)
            assertEquals(if (orientation < 5) 2 else 3, output.height)
            val actual = IntArray(6); output.getPixels(actual, 0, output.width, 0, 0, output.width, output.height)
            assertArrayEquals(orders[orientation - 1].map { colors[it] }.toIntArray(), actual)
            output.recycle()
        }
    }
}
