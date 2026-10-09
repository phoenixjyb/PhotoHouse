package dev.photohouse.tv

import android.content.*
import android.graphics.SurfaceTexture
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.*
import android.view.Surface
import android.view.TextureView
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.ui.Alignment
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.platform.LocalView
import android.view.KeyEvent
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.VideoSize
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy
import androidx.media3.exoplayer.upstream.LoadErrorHandlingPolicy
import androidx.media3.datasource.BaseDataSource
import androidx.media3.datasource.DataSpec
import android.net.Uri
import java.io.IOException
import dev.photohouse.home.HomeVideoSource
import dev.photohouse.home.PlaybackWaitDeadline
import dev.photohouse.playback.PlaybackBookmark
import kotlinx.coroutines.delay
import java.util.concurrent.atomic.AtomicBoolean

/** Media3 sees an inert URI; all bytes still come from the authorized HomeVideoSource. */
@androidx.annotation.OptIn(UnstableApi::class)
internal class ProgressiveVideoDataSource(private val reader: HomeVideoSource) : BaseDataSource(true) {
    companion object { val PRIVATE_URI: Uri = Uri.parse("photohouse-memory:///video") }
    private var opened = false
    private var position = 0L
    private var remaining = 0L
    override fun open(dataSpec: DataSpec): Long {
        if (opened || dataSpec.uri != PRIVATE_URI || dataSpec.httpMethod != DataSpec.HTTP_METHOD_GET || dataSpec.httpBody != null) throw IOException("Invalid video request")
        transferInitializing(dataSpec)
        val size = reader.size()
        if (dataSpec.position > size) throw IOException("Invalid video position")
        position = dataSpec.position
        remaining = size - position
        if (dataSpec.length != C.LENGTH_UNSET.toLong()) remaining = minOf(remaining, dataSpec.length)
        opened = true; transferStarted(dataSpec); return remaining
    }
    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        if (!opened) throw IOException("Video source closed")
        require(offset >= 0 && length >= 0 && offset <= buffer.size && length <= buffer.size - offset)
        if (length == 0) return 0
        if (remaining == 0L) return C.RESULT_END_OF_INPUT
        val count = reader.readAt(position, buffer, offset, minOf(remaining, length.toLong()).toInt())
        if (count <= 0 || count > length || count > remaining) throw IOException("Incomplete video read")
        position += count; remaining -= count; bytesTransferred(count); return count
    }
    override fun getUri(): Uri? = if (opened) PRIVATE_URI else null
    override fun close() { if (opened) { opened = false; transferEnded() } }
}
internal data class Playback(val ready: Boolean = false, val playing: Boolean = false, val position: Int = 0,
    val duration: Int = 0, val width: Int = 16, val height: Int = 9, val seeking: Boolean = false,
    val buffering: Boolean = false, val audioFocusDenied: Boolean = false)

/** Every player operation runs on one looper; HomeVideoReader owns cancellation. */
@androidx.annotation.OptIn(UnstableApi::class)
internal class NativeVideoPlayer(context: Context, private val reader: HomeVideoSource,
    private val changed: (Playback) -> Unit, private val failed: (TvPlaybackFailure) -> Unit,
    private val waitTimeoutMs: Long = 30000) {
    private val thread = HandlerThread("PhotoHouseVideo").apply { start() }
    private val handler = Handler(thread.looper)
    private val main = Handler(Looper.getMainLooper())
    private val closed = AtomicBoolean(false)
    val isClosed get() = closed.get()
    private val audio = context.getSystemService(AudioManager::class.java)
    private val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MOVIE).build()
    private val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN).setAudioAttributes(attributes)
        .setOnAudioFocusChangeListener({ if (it != AudioManager.AUDIOFOCUS_GAIN) pause() }, handler).build()
    private var player: ExoPlayer? = null
    private var surface: Surface? = null
    private var state = Playback()
    private val noisy = object : BroadcastReceiver() { override fun onReceive(context: Context?, intent: Intent?) { pause() } }
    private val app = context.applicationContext
    private val failureSent = AtomicBoolean(false)
    private val waitDeadline = PlaybackWaitDeadline(waitTimeoutMs)
    // Confined to the main looper; publish() is the only state-to-watchdog bridge.
    private var waiting: PlaybackWaitDeadline.Phase? = null
    private var monitoring = false
    private val waitWatchdog = object : Runnable {
        override fun run() {
            if (closed.get() || !monitoring) return
            waitDeadline.update(waiting, SystemClock.elapsedRealtime())?.let { phase ->
                val stage = when (phase) {
                    PlaybackWaitDeadline.Phase.PREPARING -> TvPlaybackFailure.Stage.PREPARE_TIMEOUT
                    PlaybackWaitDeadline.Phase.SEEKING -> TvPlaybackFailure.Stage.SEEK_TIMEOUT
                    PlaybackWaitDeadline.Phase.BUFFERING -> TvPlaybackFailure.Stage.REBUFFER_TIMEOUT
                }
                error(TvPlaybackFailure(stage))
            }
            if (!closed.get()) main.postDelayed(this, 250)
        }
    }
    init {
        try {
            if (Build.VERSION.SDK_INT >= 33) app.registerReceiver(noisy, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY), Context.RECEIVER_NOT_EXPORTED)
            else @Suppress("UnspecifiedRegisterReceiverFlag") app.registerReceiver(noisy, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY))
        } catch (_: Exception) { error(TvPlaybackFailure(TvPlaybackFailure.Stage.SETUP)) }
        reader.onClose(::close)
    }
    private fun publish() {
        val value = state
        main.post {
            if (!closed.get()) {
                waiting = when {
                    !value.ready -> PlaybackWaitDeadline.Phase.PREPARING
                    value.seeking -> PlaybackWaitDeadline.Phase.SEEKING
                    value.buffering && value.playing -> PlaybackWaitDeadline.Phase.BUFFERING
                    else -> null
                }
                if (monitoring) waitDeadline.update(waiting, SystemClock.elapsedRealtime())
                    ?.let { phase ->
                        val stage = when (phase) {
                            PlaybackWaitDeadline.Phase.PREPARING -> TvPlaybackFailure.Stage.PREPARE_TIMEOUT
                            PlaybackWaitDeadline.Phase.SEEKING -> TvPlaybackFailure.Stage.SEEK_TIMEOUT
                            PlaybackWaitDeadline.Phase.BUFFERING -> TvPlaybackFailure.Stage.REBUFFER_TIMEOUT
                        }
                        error(TvPlaybackFailure(stage))
                    }
                if (!closed.get()) changed(value)
            }
        }
    }
    private fun command(stage: TvPlaybackFailure.Stage = TvPlaybackFailure.Stage.CONTROL, block: () -> Unit) {
        handler.post { if (!closed.get()) try { block() } catch (_: Exception) { error(TvPlaybackFailure(stage)) } }
    }
    private fun error(reason: TvPlaybackFailure) {
        if (!closed.get() && failureSent.compareAndSet(false, true)) {
            close() // Stop audio and cancel reads before publishing an error.
            main.post { failed(reason) }
        }
    }
    fun attach(texture: SurfaceTexture) {
        if (closed.get()) return
        main.post {
            if (!closed.get() && !monitoring) {
                monitoring = true
                waiting = PlaybackWaitDeadline.Phase.PREPARING
                waitWatchdog.run()
            }
        }
        command(TvPlaybackFailure.Stage.SETUP) {
        if (player != null) return@command
        surface = Surface(texture)
        val loadControl = DefaultLoadControl.Builder().setBufferDurationsMs(8000, 12000, 1500, 3000)
            .setTargetBufferBytes(12 * 1024 * 1024).setPrioritizeTimeOverSizeThresholds(false).setBackBuffer(0, false).build()
        val p = ExoPlayer.Builder(app).setLooper(thread.looper).setLoadControl(loadControl).build()
        player = p
        p.setVideoSurface(surface)
        p.setAudioAttributes(androidx.media3.common.AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(), false)
        p.addListener(object : Player.Listener {
            override fun onVideoSizeChanged(videoSize: VideoSize) { if (videoSize.width > 0 && videoSize.height > 0) { state = state.copy(width = videoSize.width, height = videoSize.height); publish() } }
            override fun onPlaybackStateChanged(playbackState: Int) { when (playbackState) {
                Player.STATE_READY -> { state = state.copy(ready = true, buffering = false, seeking = false, duration = p.duration.coerceIn(0, Int.MAX_VALUE.toLong()).toInt()) }
                Player.STATE_BUFFERING -> {
                    state = state.copy(buffering = true)
                }
                Player.STATE_ENDED -> { p.pause(); state = state.copy(playing = false, buffering = false, seeking = false, position = state.duration); audio.abandonAudioFocusRequest(focus) }
            }; publish() }
            override fun onPositionDiscontinuity(oldPosition: Player.PositionInfo, newPosition: Player.PositionInfo, reason: Int) { if (p.playbackState == Player.STATE_READY) { state = state.copy(seeking = false, position = p.currentPosition.toInt()); publish() } }
            override fun onPlayerError(ex: PlaybackException) { error(TvPlaybackFailure(TvPlaybackFailure.Stage.NATIVE, ex.errorCode, ex.errorCode)) }
        })
        val media = ProgressiveMediaSource.Factory { ProgressiveVideoDataSource(reader) }.setContinueLoadingCheckIntervalBytes(64 * 1024)
            .setLoadErrorHandlingPolicy(object : DefaultLoadErrorHandlingPolicy(0) { override fun getRetryDelayMsFor(loadErrorInfo: LoadErrorHandlingPolicy.LoadErrorInfo) = C.TIME_UNSET })
            .createMediaSource(MediaItem.fromUri(ProgressiveVideoDataSource.PRIVATE_URI))
        p.setMediaSource(media); p.prepare()
        }
    }
    fun playPause() = command {
        if (!state.ready || state.seeking) return@command
        if (state.playing) pauseNow()
        else if (audio.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
            if (player?.playbackState == Player.STATE_ENDED) player?.seekTo(0)
            player?.play(); state = state.copy(playing = true, audioFocusDenied = false); publish()
        } else {
            state = state.copy(audioFocusDenied = true); publish()
        }
    }
    private fun pauseNow() {
        if (state.ready && state.playing) player?.pause()
        state = state.copy(playing = false); audio.abandonAudioFocusRequest(focus); publish()
    }
    fun pause() = command { pauseNow() }
    fun seek(milliseconds: Int) = command {
        if (!state.ready || state.seeking) return@command
        state = state.copy(seeking = true); publish()
        player?.seekTo(milliseconds.coerceIn(0, state.duration).toLong())
    }
    fun resume(milliseconds: Int) = command {
        if (!state.ready || state.seeking) return@command
        if (audio.requestAudioFocus(focus) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
            state = state.copy(audioFocusDenied = true); publish(); return@command
        }
        player?.seekTo(milliseconds.coerceIn(0, state.duration).toLong())
        player?.play()
        state = state.copy(playing = true, seeking = true, audioFocusDenied = false); publish()
    }
    fun poll() = command {
        if (state.ready && !state.seeking) { state = state.copy(position = (player?.currentPosition ?: 0).coerceIn(0, Int.MAX_VALUE.toLong()).toInt()); publish() }
    }
    fun close() {
        if (!closed.compareAndSet(false, true)) return
        main.removeCallbacks(waitWatchdog)
        main.post { monitoring = false; waitDeadline.reset() }
        reader.close()
        runCatching { app.unregisterReceiver(noisy) }
        handler.post {
            runCatching { player?.release() }; player = null
            surface?.release(); surface = null
            audio.abandonAudioFocusRequest(focus)
            thread.quitSafely()
        }
    }
}

/** Native TV player: explicit Play, remote seeking, aspect-fit surface and owned teardown. */
@Composable internal fun TvVideoPlayer(source: HomeVideoSource, zh: Boolean, close: () -> Unit, failure: (TvPlaybackFailure) -> Unit, bookmark: PlaybackBookmark? = null, previous: (() -> Unit)? = null, next: (() -> Unit)? = null) {
    val current by rememberUpdatedState(source)
    val onClose by rememberUpdatedState(close)
    val onFailure by rememberUpdatedState(failure)
    key(source) { TvVideoContent(source, zh, { if (current === source) onClose() }, { if (current === source) onFailure(it) }, bookmark, previous, next) }
}

@Composable private fun TvVideoContent(source: HomeVideoSource, zh: Boolean, close: () -> Unit, failure: (TvPlaybackFailure) -> Unit, bookmark: PlaybackBookmark? = null, previous: (() -> Unit)? = null, next: (() -> Unit)? = null) {
    fun t(en: String, cn: String) = if (zh) cn else en
    var state by remember(source) { mutableStateOf(Playback()) }
    var immersive by remember(source) { mutableStateOf(false) }
    var hintTick by remember { mutableStateOf(0) }
    var showHint by remember { mutableStateOf(true) }
    val context = LocalContext.current
    val view = LocalView.current
    val onFailure by rememberUpdatedState(failure)
    val onClose by rememberUpdatedState(close)
    var offerResume by remember(source) { mutableStateOf((bookmark?.positionMillis ?: 0) >= 3000) }
    val player = remember(source) { NativeVideoPlayer(context, source, {
        state = it
        if (!offerResume && it.ready && !it.seeking) bookmark?.record(it.position, it.duration)
    }, { onFailure(it) }) }
    val first = remember { FocusRequester() }
    DisposableEffect(player) { onDispose { player.close() } }
    DisposableEffect(state.playing, view) {
        view.keepScreenOn = state.playing
        onDispose { view.keepScreenOn = false }
    }
    // Surface teardown is not the only pause path: cover immediately when the Activity pauses.
    DisposableEffect(player, context) {
        val activity = context as? android.app.Activity
        val callbacks = object : android.app.Application.ActivityLifecycleCallbacks {
            override fun onActivityPaused(a: android.app.Activity) { if (a === activity) { player.close(); onClose() } }
            override fun onActivityCreated(a: android.app.Activity, b: Bundle?) { }
            override fun onActivityStarted(a: android.app.Activity) { }
            override fun onActivityResumed(a: android.app.Activity) { }
            override fun onActivityStopped(a: android.app.Activity) { }
            override fun onActivitySaveInstanceState(a: android.app.Activity, b: Bundle) { }
            override fun onActivityDestroyed(a: android.app.Activity) { }
        }
        activity?.application?.registerActivityLifecycleCallbacks(callbacks)
        onDispose { activity?.application?.unregisterActivityLifecycleCallbacks(callbacks) }
    }
    LaunchedEffect(player) { while (true) { delay(250); player.poll() } }
    LaunchedEffect(immersive, hintTick) { showHint = true; if (immersive) { delay(4000); showHint = false } }
    LaunchedEffect(immersive, state.ready) { withFrameNanos { }; runCatching { first.requestFocus() } }
    BackHandler { if (immersive) immersive = false else { player.close(); onClose() } }
    Column(Modifier.fillMaxSize().background(Color.Black).testTag("video-player")
        .onPreviewKeyEvent {
            if (it.nativeKeyEvent.action != KeyEvent.ACTION_DOWN) false
            else {
                hintTick++
                when (it.nativeKeyEvent.keyCode) {
                    KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> { offerResume = false; player.playPause(); true }
                    KeyEvent.KEYCODE_MEDIA_PAUSE -> { player.pause(); true }
                    KeyEvent.KEYCODE_MEDIA_REWIND -> { player.seek(state.position - 10000); true }
                    KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> { player.seek(state.position + 10000); true }
                    KeyEvent.KEYCODE_DPAD_LEFT -> if (immersive) { player.seek(state.position - 10000); true } else false
                    KeyEvent.KEYCODE_DPAD_RIGHT -> if (immersive) { player.seek(state.position + 10000); true } else false
                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> if (immersive) { offerResume = false; player.playPause(); true } else false
                    else -> false
                }
            }
        }) {
        // Keep the same TextureView instance when controls are hidden: toggling full screen must
        // never destroy the surface or restart audio. Both portrait and landscape fit the viewport.
        BoxWithConstraints(Modifier.weight(1f).fillMaxWidth().clipToBounds().testTag("video-viewport"), contentAlignment = Alignment.Center) {
            val ratio = state.width.toFloat() / state.height.coerceAtLeast(1)
            val width = minOf(maxWidth, maxHeight * ratio)
            val height = width / ratio
            AndroidView(factory = { ctx -> TextureView(ctx).apply {
                surfaceTextureListener = object : TextureView.SurfaceTextureListener {
                    override fun onSurfaceTextureAvailable(texture: SurfaceTexture, width: Int, height: Int) { player.attach(texture) }
                    override fun onSurfaceTextureSizeChanged(texture: SurfaceTexture, width: Int, height: Int) { }
                    override fun onSurfaceTextureUpdated(texture: SurfaceTexture) { }
                    override fun onSurfaceTextureDestroyed(texture: SurfaceTexture): Boolean {
                        val wasClosed = player.isClosed
                        player.close()
                        if (!wasClosed) onFailure(TvPlaybackFailure(TvPlaybackFailure.Stage.SURFACE))
                        return true
                    }
                }
            } }, modifier = Modifier.size(width, height).testTag("video-surface"))
            if (immersive) Box(Modifier.matchParentSize().testTag("video-immersive").focusRequester(first).focusable())
            if (!state.ready) Text(t("Loading video…", "正在加载视频…"), color = Color.White)
            if (state.audioFocusDenied) Text(t("Audio is busy. Close other playback and press Play again. [TV-AUDIO-FOCUS]", "音频被占用。请关闭其他播放后，再按播放。[TV-AUDIO-FOCUS]"),
                Modifier.align(Alignment.Center).background(Color.Black.copy(alpha = 0.85f)).padding(16.dp).testTag("video-audio-focus"), color = Color.White)
            if (immersive && showHint) Text(t("← → Seek 10s · OK Play/Pause · Back Controls", "← → 快进/后退 10 秒 · 确定 播放/暂停 · 返回 控制栏"),
                Modifier.align(Alignment.BottomCenter).background(Color.Black.copy(alpha = 0.7f)).padding(8.dp), color = Color.White)
        }
        if (!immersive) Column(Modifier.safeDrawingPadding().padding(horizontal = 24.dp, vertical = 8.dp)) {
            LinearProgressIndicator(progress = if (state.duration > 0) state.position.toFloat() / state.duration else 0f, modifier = Modifier.fillMaxWidth())
            Text("${videoTime(state.position)} / ${videoTime(state.duration)}", Modifier.testTag("video-position"), color = Color.White)
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (offerResume && state.ready) TvButton(t("Continue ${videoTime(bookmark!!.positionMillis)}", "继续 ${videoTime(bookmark!!.positionMillis)}"), Modifier.testTag("video-resume"), !state.seeking) {
                    offerResume = false; player.resume(bookmark.positionMillis)
                }
                TvButton(t("Previous video", "上一个视频"), Modifier.testTag("video-previous"), previous != null) { previous?.invoke() }
                TvButton(t("Next video", "下一个视频"), Modifier.testTag("video-next"), next != null) { next?.invoke() }
                TvButton(t("Close video", "关闭视频"), Modifier.then(if (!state.ready) Modifier.focusRequester(first) else Modifier)) { player.close(); onClose() }
                TvButton(if (state.playing) t("Pause", "暂停") else t("Play", "播放"), Modifier.testTag("video-play").then(if (state.ready) Modifier.focusRequester(first) else Modifier), state.ready && !state.seeking) { offerResume = false; player.playPause() }
                TvButton(t("Back 10s", "后退 10 秒"), Modifier.testTag("video-rewind"), state.ready && !state.seeking) { player.seek(state.position - 10000) }
                TvButton(t("Forward 10s", "前进 10 秒"), Modifier.testTag("video-forward"), state.ready && !state.seeking) { player.seek(state.position + 10000) }
                TvButton(t("Full screen", "全屏"), Modifier.testTag("video-fullscreen")) { immersive = true }
            }
        }
    }
}

internal fun videoTime(milliseconds: Int): String {
    val seconds = milliseconds.coerceAtLeast(0) / 1000
    return "%d:%02d".format(java.util.Locale.ROOT, seconds / 60, seconds % 60)
}
