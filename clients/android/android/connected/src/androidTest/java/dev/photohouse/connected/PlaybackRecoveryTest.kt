package dev.photohouse.connected

import android.graphics.SurfaceTexture
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.media3.common.PlaybackException
import dev.photohouse.connected.core.VideoPlaybackFailure
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class PlaybackRecoveryTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private class BlockedSource : PhonePlaybackSource {
        val entered = CountDownLatch(1)
        val released = CountDownLatch(1)
        val closes = AtomicInteger()
        override fun size(): Long { entered.countDown(); check(released.await(5, TimeUnit.SECONDS)); return 1024 }
        override fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int = -1
        override fun onClose(listener: () -> Unit) { }
        override fun close() { closes.incrementAndGet(); released.countDown() }
    }
    @Test fun blockedPreparationTimesOutAndCancelsBeforeReportingExactlyOnce() {
        val source=BlockedSource(); val reported=CountDownLatch(1); val calls=AtomicInteger()
        var diagnosis: VideoPlaybackFailure?=null
        var closedBeforeReport=false
        val texture=SurfaceTexture(0)
        val player=NativeVideoPlayer(rule.activity,source,{}, {
            diagnosis=it; closedBeforeReport=source.released.count==0L; calls.incrementAndGet(); reported.countDown()
        },waitTimeoutMs=500)
        try {
            player.attach(texture)
            assertTrue(source.entered.await(3,TimeUnit.SECONDS))
            assertTrue(reported.await(3,TimeUnit.SECONDS))
            assertEquals(VideoPlaybackFailure.PREPARE_TIMEOUT,diagnosis)
            assertTrue(closedBeforeReport); assertTrue(player.isClosed)
            player.close(); rule.waitForIdle()
            assertEquals(1,calls.get()); assertEquals(1,source.closes.get())
        } finally { player.close(); texture.release() }
    }
    @Test fun viewerCloseCancelsWaitWithoutReportingAnError() {
        val source=BlockedSource(); val reported=CountDownLatch(1)
        val texture=SurfaceTexture(0)
        val player=NativeVideoPlayer(rule.activity,source,{}, { reported.countDown() },waitTimeoutMs=1000)
        try {
            player.attach(texture); assertTrue(source.entered.await(3,TimeUnit.SECONDS))
            player.close()
            assertFalse(reported.await(1500,TimeUnit.MILLISECONDS))
            assertEquals(1,source.closes.get())
        } finally { player.close(); texture.release() }
    }
    @Test fun pausedSeekIntoBlockedReadTimesOutAndReleasesAttachedPlayer() {
        val data=androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().context.assets
            .open("synthetic-long-video.mp4").use { it.readBytes() }
        val block=java.util.concurrent.atomic.AtomicBoolean(false)
        val blocked=CountDownLatch(1); val released=CountDownLatch(1); val reported=CountDownLatch(1)
        val ready=CountDownLatch(1)
        var diagnosis: VideoPlaybackFailure?=null
        val source=object : PhonePlaybackSource {
            override fun size()=data.size.toLong()
            override fun readAt(position:Long,buffer:ByteArray,offset:Int,size:Int):Int {
                if(block.get()) {
                    blocked.countDown(); released.await(5,TimeUnit.SECONDS)
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
                    override fun onSurfaceTextureAvailable(t:SurfaceTexture,w:Int,h:Int) { player.attach(t) }
                    override fun onSurfaceTextureSizeChanged(t:SurfaceTexture,w:Int,h:Int) { }
                    override fun onSurfaceTextureUpdated(t:SurfaceTexture) { }
                    override fun onSurfaceTextureDestroyed(t:SurfaceTexture)=true
                }
                rule.activity.setContentView(view)
            }
            assertTrue(ready.await(5,TimeUnit.SECONDS))
            // Paused and ready must remain available beyond the configured wait deadline.
            assertFalse(reported.await(1700,TimeUnit.MILLISECONDS)); assertFalse(player.isClosed)
            block.set(true); player.seek(120000)
            assertTrue(blocked.await(3,TimeUnit.SECONDS))
            assertTrue(reported.await(4,TimeUnit.SECONDS))
            assertEquals(VideoPlaybackFailure.SEEK_TIMEOUT,diagnosis)
            assertTrue(player.isClosed); assertEquals(0L,released.count)
        } finally { player.close() }
    }

    @Test fun media3CodesYieldFixedBilingualDiagnosisWithoutExceptionText() {
        assertEquals(VideoPlaybackFailure.UNSUPPORTED,classifyPlaybackFailure(PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED))
        assertEquals(VideoPlaybackFailure.DECODER,classifyPlaybackFailure(PlaybackException.ERROR_CODE_DECODER_INIT_FAILED))
        assertEquals(VideoPlaybackFailure.INVALID_MEDIA,classifyPlaybackFailure(PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED))
        assertEquals(VideoPlaybackFailure.READ,classifyPlaybackFailure(PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT))
        assertEquals(VideoPlaybackFailure.PLAYER,classifyPlaybackFailure(Int.MAX_VALUE))
        for (value in VideoPlaybackFailure.entries) {
            assertTrue(value.message(false).contains(value.code))
            assertTrue(value.message(true).contains(value.code))
            assertNotEquals(value.message(false),value.message(true))
        }
    }
}
