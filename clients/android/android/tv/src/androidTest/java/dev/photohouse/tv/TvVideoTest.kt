package dev.photohouse.tv

import android.view.KeyEvent
import android.view.TextureView
import android.view.View
import android.view.ViewGroup
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.Lifecycle
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.*
import org.junit.Assert.*
import java.io.IOException
import dev.photohouse.home.HomeVideoReader
import android.graphics.Bitmap
import android.graphics.Canvas
import java.io.File

class TvVideoTest {
    @Test fun blockedExtractorSetupTimesOutOutsidePlayerLooperAndCancelsRead() {
        val entered = java.util.concurrent.CountDownLatch(1)
        val released = java.util.concurrent.CountDownLatch(1)
        val reported = java.util.concurrent.CountDownLatch(1)
        val failureCount = java.util.concurrent.atomic.AtomicInteger()
        val closedBeforeFailure = java.util.concurrent.atomic.AtomicBoolean()
        var failure: TvPlaybackFailure? = null
        val source = object : dev.photohouse.home.HomeVideoSource {
            override fun size(): Long { entered.countDown(); released.await(5, java.util.concurrent.TimeUnit.SECONDS); return 1024 }
            override fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int = -1
            override fun onClose(listener: () -> Unit) { }
            override fun close() { closedBeforeFailure.set(true); released.countDown() }
        }
        val texture = android.graphics.SurfaceTexture(0)
        val player = NativeVideoPlayer(rule.activity, source, {}, { failure = it; failureCount.incrementAndGet(); reported.countDown() }, 500)
        try {
            player.attach(texture)
            assertTrue(entered.await(3, java.util.concurrent.TimeUnit.SECONDS))
            assertTrue(reported.await(3, java.util.concurrent.TimeUnit.SECONDS))
            assertEquals(TvPlaybackFailure.Stage.PREPARE_TIMEOUT, failure?.stage)
            assertEquals(0L, released.count)
            assertTrue(closedBeforeFailure.get())
            assertEquals(1, failureCount.get())
            assertTrue(player.isClosed)
        } finally { player.close(); texture.release() }
    }
    @Test fun pausedSeekIntoBlockedReadTimesOutAndReleasesAttachedPlayer() {
        val data=androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets
            .open("synthetic-video.mp4").use { it.readBytes() }
        val block=java.util.concurrent.atomic.AtomicBoolean(false)
        val blocked=java.util.concurrent.CountDownLatch(1); val released=java.util.concurrent.CountDownLatch(1); val reported=java.util.concurrent.CountDownLatch(1)
        val ready=java.util.concurrent.CountDownLatch(1)
        var diagnosis: TvPlaybackFailure?=null
        val source=object : dev.photohouse.home.HomeVideoSource {
            override fun size()=data.size.toLong()
            override fun readAt(position:Long,buffer:ByteArray,offset:Int,size:Int):Int {
                if(block.get()) {
                    blocked.countDown(); released.await(5,java.util.concurrent.TimeUnit.SECONDS)
                    throw java.io.IOException("synthetic blocked read")
                }
                val count=minOf(size,data.size-position.toInt())
                data.copyInto(buffer,offset,position.toInt(),position.toInt()+count);return count
            }
            override fun onClose(listener:()->Unit) { }
            override fun close() { released.countDown() }
        }
        val player=NativeVideoPlayer(rule.activity,source,{ if(it.ready) ready.countDown() },{
            diagnosis=it;reported.countDown()
        },waitTimeoutMs=1500)
        try {
            rule.runOnUiThread {
                val view=android.view.TextureView(rule.activity)
                view.surfaceTextureListener=object : android.view.TextureView.SurfaceTextureListener {
                    override fun onSurfaceTextureAvailable(t:android.graphics.SurfaceTexture,w:Int,h:Int) { player.attach(t) }
                    override fun onSurfaceTextureSizeChanged(t:android.graphics.SurfaceTexture,w:Int,h:Int) { }
                    override fun onSurfaceTextureUpdated(t:android.graphics.SurfaceTexture) { }
                    override fun onSurfaceTextureDestroyed(t:android.graphics.SurfaceTexture)=true
                }
                rule.activity.setContentView(view)
            }
            assertTrue(ready.await(5,java.util.concurrent.TimeUnit.SECONDS))
            // Paused and ready must remain available beyond the configured wait deadline.
            assertFalse(reported.await(1700,java.util.concurrent.TimeUnit.MILLISECONDS)); assertFalse(player.isClosed)
            block.set(true); player.seek(19000)
            assertTrue(blocked.await(3,java.util.concurrent.TimeUnit.SECONDS))
            assertTrue(reported.await(4,java.util.concurrent.TimeUnit.SECONDS))
            assertEquals(TvPlaybackFailure.Stage.SEEK_TIMEOUT,diagnosis?.stage)
            assertTrue(player.isClosed); assertEquals(0L,released.count)
        } finally { player.close() }
    }

    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private fun install(bytes: ByteArray? = null, bookmark: dev.photohouse.playback.PlaybackBookmark? = null, next: (() -> Unit)? = null): HomeVideoReader {
        val data = bytes ?: InstrumentationRegistry.getInstrumentation().context.assets.open("synthetic-video.mp4").use { it.readBytes() }
        val source = HomeVideoReader(data.size.toLong(), 65536, { position, count ->
            data.copyOfRange(position.toInt(), position.toInt() + count)
        }, { })
        rule.runOnUiThread { rule.activity.setContent {
            var visible by remember { mutableStateOf(true) }
            var failed by remember { mutableStateOf(false) }
            MaterialTheme {
                if (visible) TvVideoPlayer(source, false, { visible = false }, { failed = true; visible = false }, bookmark, next = next)
                else Text(if (failed) "Playback unavailable" else "Video closed")
            }
        } }
        return source
    }
    private fun key(code: Int) {
        rule.waitUntil(10000) { rule.activity.hasWindowFocus() }
        InstrumentationRegistry.getInstrumentation().sendKeyDownUpSync(code); rule.waitForIdle()
    }
    private fun ready() { rule.waitUntil(15000) { rule.onAllNodes(hasTestTag("video-play") and isEnabled()).fetchSemanticsNodes().size == 1 } }
    private fun texture(view: View): TextureView? {
        if (view is TextureView) return view
        if (view is ViewGroup) for (i in 0 until view.childCount) texture(view.getChildAt(i))?.let { return it }
        return null
    }
    @Test fun explicitResumeStartsAtBookmarkAndNextIsAnExplicitAction() {
        val progress = dev.photohouse.playback.PlaybackProgress()
        progress.open("synthetic").record(8000, 20000)
        var navigated = 0
        val source = install(bookmark = progress.open("synthetic"), next = { navigated++ })
        ready()
        rule.onNodeWithText("Play", substring=false).assertExists()
        rule.onNodeWithTag("video-resume").performScrollTo().performClick()
        rule.waitUntil(15000) {
            val text = rule.onNodeWithTag("video-position").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.Text].first().text
            text.startsWith("0:08") || text.startsWith("0:09") || text.startsWith("0:1")
        }
        rule.onNodeWithText("Pause", substring=false).assertExists()
        rule.onNodeWithTag("video-previous").performScrollTo().assertIsNotEnabled()
        assertEquals(0, navigated)
        rule.onNodeWithTag("video-next").performScrollTo().performClick()
        assertEquals(1, navigated)
        source.close()
    }
    @Test fun nativeVideoPreparesPlaysSeeksFitsFullscreenAndCloses() {
        val source = install(); ready()
        rule.onNodeWithText("Play", substring = false).assertExists() // no autoplay
        rule.onNodeWithTag("video-play").assertIsFocused()
        key(KeyEvent.KEYCODE_DPAD_CENTER)
        rule.onNodeWithText("Pause", substring = false).assertExists()
        rule.waitUntil(10000) {
            rule.onAllNodes(hasTestTag("video-position") and hasText("0:00 / 0:20")).fetchSemanticsNodes().isEmpty()
        }
        // The decoder delivered a non-uniform synthetic frame, not merely onPrepared.
        rule.runOnUiThread {
            val bitmap = requireNotNull(texture(rule.activity.window.decorView)?.bitmap)
            val samples = (1..8).map { bitmap.getPixel(it * bitmap.width / 10, bitmap.height / 2) }.toSet()
            assertTrue("Native video frame must contain the test pattern", samples.size > 2)
            bitmap.recycle()
        }
        rule.onNodeWithTag("video-play").performClick()
        rule.onNodeWithText("Play", substring = false).assertExists()
        rule.onNodeWithTag("video-forward").performScrollTo().performClick()
        rule.waitUntil(10000) { rule.onAllNodes(hasTestTag("video-play") and isEnabled()).fetchSemanticsNodes().size == 1 }
        // A fast Media3 seek may finish before Compose observes the disabled
        // button frame. Wait for the visible position, not an old enabled node.
        rule.waitUntil(10000) {
            rule.onNodeWithTag("video-position").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.Text].first().text.startsWith("0:1")
        }
        val position = rule.onNodeWithTag("video-position").fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.Text].first().text
        assertTrue(position, position.startsWith("0:1"))
        rule.runOnUiThread {
            val root = rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap); root.draw(canvas)
            // Test-only capture of our synthetic TextureView frame; FLAG_SECURE remains enabled.
            val tv = requireNotNull(texture(root)); val frame = requireNotNull(tv.bitmap)
            val location = IntArray(2); tv.getLocationInWindow(location)
            val origin = IntArray(2); root.getLocationInWindow(origin)
            canvas.drawBitmap(frame, (location[0] - origin[0]).toFloat(), (location[1] - origin[1]).toFloat(), null)
            File(rule.activity.filesDir, "video-paused.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            frame.recycle(); bitmap.recycle()
        }
        rule.onNodeWithTag("video-fullscreen").performScrollTo().performClick()
        rule.onNodeWithTag("video-immersive").assertIsFocused()
        val surface = rule.onNodeWithTag("video-surface").fetchSemanticsNode().boundsInRoot
        val viewport = rule.onNodeWithTag("video-viewport").fetchSemanticsNode().boundsInRoot
        assertTrue(surface.left >= viewport.left && surface.right <= viewport.right && surface.top >= viewport.top && surface.bottom <= viewport.bottom)
        key(KeyEvent.KEYCODE_DPAD_LEFT)
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithTag("video-player").assertExists()
        assertFalse(source.isClosed)
        key(KeyEvent.KEYCODE_BACK)
        rule.onNodeWithText("Video closed").assertExists(); assertTrue(source.isClosed)
    }
    @Test fun activityBackgroundClosesVideoAndDoesNotResumeAudio() {
        val source = install(); ready()
        rule.onNodeWithTag("video-play").performClick()
        rule.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
        assertTrue(source.isClosed)
        rule.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
        rule.onNodeWithText("Video closed").assertExists()
        rule.onNodeWithTag("video-player").assertDoesNotExist()
    }
    @Test fun replacingSourceClosesOldPlayerAndPreparesNewWithoutAutoplay() {
        val data = InstrumentationRegistry.getInstrumentation().context.assets.open("synthetic-video.mp4").use { it.readBytes() }
        fun source() = HomeVideoReader(data.size.toLong(), 65536, { p, n -> data.copyOfRange(p.toInt(), p.toInt() + n) }, {})
        val old = source(); val next = source()
        val selected = mutableStateOf(old)
        var unwantedClose = 0
        rule.runOnUiThread { rule.activity.setContent {
            MaterialTheme { TvVideoPlayer(selected.value, false, { unwantedClose++ }, { unwantedClose++ }) }
        } }
        ready(); rule.onNodeWithTag("video-play").performClick()
        rule.runOnUiThread { selected.value = next }
        rule.waitUntil(5000) { old.isClosed }
        ready()
        rule.onNodeWithText("Play", substring = false).assertExists()
        assertFalse(next.isClosed); assertEquals(0, unwantedClose)
    }
    @Test fun malformedVideoClosesSourceAndReportsFailure() {
        val source = install(byteArrayOf(1, 2, 3))
        rule.waitUntil(15000) { rule.onAllNodesWithText("Playback unavailable").fetchSemanticsNodes().size == 1 }
        assertTrue(source.isClosed)
    }

    @Test fun media3CompletionUpdatesStateAndReplayStartsAtZero() {
        // Use the real TextureView consumer: an unattached SurfaceTexture fills its
        // buffer queue and stalls decoding, which is not a playback completion test.
        val source = install(); ready()
        rule.onNodeWithTag("video-forward").performScrollTo().performClick()
        ready()
        rule.onNodeWithTag("video-play").performScrollTo().performClick()
        rule.waitUntil(20000) {
            rule.onAllNodes(hasTestTag("video-position") and hasText("0:20 / 0:20")).fetchSemanticsNodes().size == 1 &&
                rule.onAllNodesWithText("Play", substring = false).fetchSemanticsNodes().size == 1
        }
        rule.onNodeWithTag("video-play").performClick()
        rule.onNodeWithText("Pause", substring = false).assertExists()
        rule.waitUntil(5000) {
            rule.onAllNodes(hasTestTag("video-position") and hasText("0:20 / 0:20")).fetchSemanticsNodes().isEmpty()
        }
        key(KeyEvent.KEYCODE_BACK)
        assertTrue(source.isClosed)
    }
}
