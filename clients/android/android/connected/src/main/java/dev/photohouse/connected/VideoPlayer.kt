package dev.photohouse.connected

import android.content.*
import android.graphics.SurfaceTexture
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.VideoSize
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.analytics.AnalyticsListener
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy
import androidx.media3.exoplayer.upstream.LoadErrorHandlingPolicy
import android.os.*
import android.view.Surface
import android.view.TextureView
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import dev.photohouse.connected.core.VideoReader
import dev.photohouse.connected.core.MediaViewport
import dev.photohouse.connected.core.VideoPlaybackFailure
import dev.photohouse.home.PlaybackWaitDeadline
import dev.photohouse.playback.PlaybackBookmark
import kotlinx.coroutines.delay
import java.util.concurrent.atomic.AtomicBoolean

internal interface PhonePlaybackSource : java.io.Closeable {
    fun size(): Long
    fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int
    fun onClose(listener: () -> Unit)
}
private class AccountPlaybackSource(private val reader: VideoReader) : PhonePlaybackSource {
    override fun size() = reader.size()
    override fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int) = reader.readAt(position, buffer, offset, size)
    override fun onClose(listener: () -> Unit) = reader.onClose {
        reader.lastFailure?.let {
            if (BuildConfig.DEBUG) android.util.Log.d("PhotoHouseVideoIO", "readFailureKind=${it.kind} status=${it.status}")
        }
        listener()
    }
    override fun close() = reader.close()
}
internal data class Playback(val ready: Boolean = false, val playing: Boolean = false, val position: Int = 0,
    val duration: Int = 0, val width: Int = 16, val height: Int = 9, val seeking: Boolean = false, val buffering: Boolean = false, val audioFocusDenied: Boolean = false)

internal fun videoTime(milliseconds: Int): String {
    val seconds = milliseconds.coerceAtLeast(0) / 1000
    val minutes = seconds / 60
    return if (minutes < 60) "$minutes:${(seconds % 60).toString().padStart(2, '0')}"
    else "${minutes / 60}:${(minutes % 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}"
}

@androidx.annotation.OptIn(UnstableApi::class)
internal fun classifyPlaybackFailure(code: Int): VideoPlaybackFailure = when (code) {
    PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED,
    PlaybackException.ERROR_CODE_DECODING_FORMAT_EXCEEDS_CAPABILITIES,
    PlaybackException.ERROR_CODE_PARSING_CONTAINER_UNSUPPORTED,
    PlaybackException.ERROR_CODE_PARSING_MANIFEST_UNSUPPORTED -> VideoPlaybackFailure.UNSUPPORTED
    PlaybackException.ERROR_CODE_DECODER_INIT_FAILED,
    PlaybackException.ERROR_CODE_DECODER_QUERY_FAILED,
    PlaybackException.ERROR_CODE_DECODING_FAILED,
    PlaybackException.ERROR_CODE_AUDIO_TRACK_INIT_FAILED,
    PlaybackException.ERROR_CODE_AUDIO_TRACK_WRITE_FAILED -> VideoPlaybackFailure.DECODER
    PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED,
    PlaybackException.ERROR_CODE_PARSING_MANIFEST_MALFORMED -> VideoPlaybackFailure.INVALID_MEDIA
    PlaybackException.ERROR_CODE_IO_UNSPECIFIED,
    PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_FAILED,
    PlaybackException.ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT,
    PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS,
    PlaybackException.ERROR_CODE_IO_FILE_NOT_FOUND,
    PlaybackException.ERROR_CODE_IO_NO_PERMISSION -> VideoPlaybackFailure.READ
    else -> VideoPlaybackFailure.PLAYER
}

/** Progressive extraction and bounded buffering; all player operations share one looper. */
@androidx.annotation.OptIn(UnstableApi::class)
internal class NativeVideoPlayer(context: Context, private val reader: PhonePlaybackSource,
    private val changed: (Playback) -> Unit, private val failed: (VideoPlaybackFailure) -> Unit,
    private val waitTimeoutMs: Long = 30_000) {
    constructor(context: Context, reader: VideoReader, changed: (Playback) -> Unit, failed: (VideoPlaybackFailure) -> Unit) :
        this(context, AccountPlaybackSource(reader), changed, failed)
    val isClosed get() = closed.get()
    private val failureSent = AtomicBoolean(false)
    private val thread = HandlerThread("PhotoHouseVideo").apply { start() }
    private val handler = Handler(thread.looper)
    private val main = Handler(Looper.getMainLooper())
    private val closed = AtomicBoolean(false)
    private val audio = context.getSystemService(AudioManager::class.java)
    private val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MOVIE).build()
    private val focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN).setAudioAttributes(attributes)
        .setOnAudioFocusChangeListener({ if (it != AudioManager.AUDIOFOCUS_GAIN) pause() }, handler).build()
    private var player: ExoPlayer? = null
    private var lastDiagnosticAt = 0L
    private var surface: Surface? = null
    private var state = Playback()
    // Confined to main: the player/loader thread can be waiting on a network read.
    private val waitDeadline = PlaybackWaitDeadline(waitTimeoutMs)
    private var waiting: PlaybackWaitDeadline.Phase? = null
    private var monitoring = false
    private val waitWatchdog = object : Runnable {
        override fun run() {
            if (closed.get() || !monitoring) return
            checkWait()
            if (!closed.get()) main.postDelayed(this, 250)
        }
    }
    private fun checkWait() {
        waitDeadline.update(waiting, SystemClock.elapsedRealtime())?.let {
            error(when (it) {
                PlaybackWaitDeadline.Phase.PREPARING -> VideoPlaybackFailure.PREPARE_TIMEOUT
                PlaybackWaitDeadline.Phase.SEEKING -> VideoPlaybackFailure.SEEK_TIMEOUT
                PlaybackWaitDeadline.Phase.BUFFERING -> VideoPlaybackFailure.BUFFER_TIMEOUT
            })
        }
    }
    private val noisy = object : BroadcastReceiver() { override fun onReceive(context: Context?, intent: Intent?) { pause() } }
    private val app = context.applicationContext
    init {
        try {
            if (Build.VERSION.SDK_INT >= 33) app.registerReceiver(noisy, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY), Context.RECEIVER_NOT_EXPORTED)
            else @Suppress("UnspecifiedRegisterReceiverFlag") app.registerReceiver(noisy, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY))
        } catch (_: Exception) { error() }
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
                if (monitoring) checkWait()
                if (!closed.get()) changed(value)
            }
        }
    }
    private fun command(block: () -> Unit) { handler.post { if (!closed.get()) try { block() } catch (_: Exception) { error() } } }
    private fun error(reason: VideoPlaybackFailure = VideoPlaybackFailure.PLAYER) {
        if (!closed.get() && failureSent.compareAndSet(false, true)) {
            close()
            main.post { failed(reason) }
        }
    }
    fun attach(texture: SurfaceTexture) {
        main.post {
            if (!closed.get() && !monitoring) {
                monitoring = true
                waiting = PlaybackWaitDeadline.Phase.PREPARING
                waitWatchdog.run()
            }
        }
        command {
        if (player != null) return@command
        surface = Surface(texture)
        val loadControl = DefaultLoadControl.Builder()
            .setBufferDurationsMs(8000, 12000, 1500, 3000)
            .setTargetBufferBytes(12 * 1024 * 1024)
            .setPrioritizeTimeOverSizeThresholds(false)
            .setBackBuffer(0, false)
            .build()
        val p = ExoPlayer.Builder(app).setLooper(thread.looper).setLoadControl(loadControl).build()
        player = p
        p.setVideoSurface(surface)
        // Audio focus remains owned here, including noisy-device and background pause.
        p.setAudioAttributes(androidx.media3.common.AudioAttributes.Builder()
            .setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(), false)
        p.addListener(object : Player.Listener {
            override fun onVideoSizeChanged(videoSize: VideoSize) {
                if (videoSize.width > 0 && videoSize.height > 0) {
                    state = state.copy(width = videoSize.width, height = videoSize.height); publish()
                }
            }
            override fun onPlaybackStateChanged(playbackState: Int) {
                when (playbackState) {
                    Player.STATE_READY -> {
                        state = state.copy(ready = true, buffering = false, seeking = false,
                            duration = p.duration.coerceIn(0, Int.MAX_VALUE.toLong()).toInt())
                    }
                    Player.STATE_BUFFERING -> state = state.copy(buffering = true)
                    Player.STATE_ENDED -> {
                        p.pause()
                        state = state.copy(playing = false, buffering = false, seeking = false, position = state.duration)
                        audio.abandonAudioFocusRequest(focus)
                    }
                }
                publish()
            }
            override fun onPositionDiscontinuity(oldPosition: Player.PositionInfo, newPosition: Player.PositionInfo, reason: Int) {
                if (p.playbackState == Player.STATE_READY) {
                    state = state.copy(seeking = false, position = p.currentPosition.toInt()); publish()
                }
            }
            override fun onPlayerError(error: PlaybackException) {
                if (BuildConfig.DEBUG) android.util.Log.d("PhotoHouseVideoIO", "playerErrorCode=${error.errorCode}")
                error(classifyPlaybackFailure(error.errorCode))
            }
        })
        p.addAnalyticsListener(object : AnalyticsListener {
            override fun onVideoDecoderInitialized(eventTime: AnalyticsListener.EventTime, decoderName: String, initializedTimestampMs: Long, initializationDurationMs: Long) {
                if (BuildConfig.DEBUG) android.util.Log.d("PhotoHouseVideoIO", "decoder=$decoderName initMs=$initializationDurationMs")
            }
            override fun onDroppedVideoFrames(eventTime: AnalyticsListener.EventTime, droppedFrames: Int, elapsedMs: Long) {
                if (BuildConfig.DEBUG) android.util.Log.d("PhotoHouseVideoIO", "droppedFrames=$droppedFrames elapsedMs=$elapsedMs")
            }
        })
        val media = ProgressiveMediaSource.Factory { ProgressiveVideoDataSource(reader) }
            .setContinueLoadingCheckIntervalBytes(64 * 1024)
            // Reader/Store own authorization and cancellation. Never retry a closed reader.
            .setLoadErrorHandlingPolicy(object : DefaultLoadErrorHandlingPolicy(0) {
                override fun getRetryDelayMsFor(loadErrorInfo: LoadErrorHandlingPolicy.LoadErrorInfo) = C.TIME_UNSET
            })
            .createMediaSource(MediaItem.fromUri(ProgressiveVideoDataSource.PRIVATE_URI))
        p.setMediaSource(media)
        p.prepare() // Explicit Play; never autoplay audio after preparation.
        }
    }
    fun playPause() = command {
        if (!state.ready || state.seeking) return@command
        if (state.playing) pauseNow()
        else if (audio.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
            if (player?.playbackState == Player.STATE_ENDED) player?.seekTo(0)
            player?.play(); state = state.copy(playing = true, audioFocusDenied = false); publish()
        } else { state = state.copy(audioFocusDenied = true); publish() }
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
        if (state.ready && !state.seeking) { state = state.copy(position = (player?.currentPosition ?: 0).coerceIn(0, Int.MAX_VALUE.toLong()).toInt()); publish()
            val now = SystemClock.elapsedRealtime()
            if (BuildConfig.DEBUG && now - lastDiagnosticAt >= 10000) {
                lastDiagnosticAt = now
                android.util.Log.d("PhotoHouseVideoIO", "positionMs=${state.position} bufferedMs=${player?.totalBufferedDuration ?: 0} playing=${player?.isPlaying == true}")
            } }
    }
    fun close() {
        if (!closed.compareAndSet(false, true)) return
        main.removeCallbacks(waitWatchdog)
        reader.close()
        runCatching { app.unregisterReceiver(noisy) }
        handler.post {
            runCatching { player?.release() }; player = null
            surface?.release(); surface = null
            audio.abandonAudioFocusRequest(focus)
            // Drain Media3 release callbacks before stopping the application looper.
            handler.post { thread.quitSafely() }
        }
    }
}

@Composable internal fun VideoPlayer(reader: VideoReader, zh: Boolean, close: () -> Unit, failure: (VideoPlaybackFailure) -> Unit, bookmark: PlaybackBookmark? = null, previous: (() -> Unit)? = null, next: (() -> Unit)? = null) {
    val source = remember(reader) { AccountPlaybackSource(reader) }
    PhoneVideoPlayer(source, zh, close, failure, bookmark, previous, next)
}

@Composable internal fun PhoneVideoPlayer(reader: PhonePlaybackSource, zh: Boolean, close: () -> Unit, failure: (VideoPlaybackFailure) -> Unit, bookmark: PlaybackBookmark? = null, previous: (() -> Unit)? = null, next: (() -> Unit)? = null) {
    val current by rememberUpdatedState(reader)
    val onClose by rememberUpdatedState(close)
    val onFailure by rememberUpdatedState(failure)
    key(reader) { PhoneVideoContent(reader, zh, { if (current === reader) onClose() }, { reason -> if (current === reader) onFailure(reason) }, bookmark, previous, next) }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable private fun PhoneVideoContent(reader: PhonePlaybackSource, zh: Boolean, close: () -> Unit, failure: (VideoPlaybackFailure) -> Unit, bookmark: PlaybackBookmark? = null, previous: (() -> Unit)? = null, next: (() -> Unit)? = null) {
    fun t(en: String, cn: String) = if (zh) cn else en
    var state by remember(reader) { mutableStateOf(Playback()) }
    var fill by remember(reader) { mutableStateOf(false) }
    var fullScreen by remember(reader) { mutableStateOf(false) }
    val context = LocalContext.current
    val onFailure by rememberUpdatedState(failure)
    var offerResume by remember(reader) { mutableStateOf((bookmark?.positionMillis ?: 0) >= 3000) }
    val player = remember(reader) { NativeVideoPlayer(context, reader, {
        state = it
        if (!offerResume && it.ready && !it.seeking) bookmark?.record(it.position, it.duration)
    }, { onFailure(it) }) }
    DisposableEffect(player) { onDispose { player.close() } }
    MediaWindow(fullScreen, state.playing)
    BackHandler(fullScreen) { fullScreen = false }
    LaunchedEffect(player) { while (true) { delay(250); player.poll() } }
    BoxWithConstraints(Modifier.fillMaxSize().testTag("video-player")) {
    val panelLimit = maxHeight * 0.5f
    Column(Modifier.fillMaxSize().then(if (fullScreen) Modifier else Modifier.safeDrawingPadding().padding(16.dp)), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        BoxWithConstraints(Modifier.weight(1f).fillMaxWidth().background(Color.Black).clipToBounds().testTag("video-viewport"), contentAlignment = Alignment.Center) {
            val fitted = MediaViewport.measure(state.width.toFloat(), state.height.toFloat(), maxWidth.value, maxHeight.value, fill)
            AndroidView(factory = { ctx -> TextureView(ctx).apply {
                surfaceTextureListener = object : TextureView.SurfaceTextureListener {
                    override fun onSurfaceTextureAvailable(texture: SurfaceTexture, width: Int, height: Int) { player.attach(texture) }
                    override fun onSurfaceTextureSizeChanged(texture: SurfaceTexture, width: Int, height: Int) { }
                    override fun onSurfaceTextureUpdated(texture: SurfaceTexture) { }
                    override fun onSurfaceTextureDestroyed(texture: SurfaceTexture): Boolean {
                        val expected = player.isClosed
                        player.close()
                        if (!expected) onFailure(VideoPlaybackFailure.SURFACE)
                        return true
                    }
                }
            } }, modifier = Modifier.requiredSize(fitted.width.dp, fitted.height.dp).testTag("video-surface"))
        }
        if (!fullScreen) Column(Modifier.fillMaxWidth().heightIn(max = panelLimit).verticalScroll(rememberScrollState()).testTag("video-controls"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = close) { Text(t("Close video", "关闭视频")) }
            TextButton(onClick = { fullScreen = true }, enabled = state.ready) { Text(t("Full screen", "全屏")) }
            TextButton(onClick = { fill = !fill }) { Text(if (fill) t("Fit video", "完整视频") else t("Fill screen", "填满屏幕")) }
        }
        Text(if (fill) t("Fill · edges cropped", "填满 · 边缘已裁切") else t("Fit · whole video", "适合 · 完整视频"), Modifier.testTag("video-fit-mode"), style = MaterialTheme.typography.labelMedium)
        if (!state.ready || state.seeking || state.buffering) {
            LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(when { !state.ready -> t("Loading video…", "正在加载视频…"); state.seeking -> t("Seeking…", "正在跳转…"); else -> t("Buffering…", "正在缓冲…") })
        }
        if (state.audioFocusDenied) Text(t("Audio is busy. Pause other audio and try Play again.", "音频被占用，请暂停其他音频后再播放。"), Modifier.testTag("video-audio-focus"))
        if (offerResume && state.ready) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { offerResume = false; player.resume(bookmark!!.positionMillis) },
                modifier = Modifier.testTag("video-resume"), enabled = !state.seeking) {
                Text(t("Continue from ${videoTime(bookmark!!.positionMillis)}", "从 ${videoTime(bookmark!!.positionMillis)} 继续"))
            }
            TextButton(onClick = { offerResume = false; bookmark?.record(0, state.duration) }, modifier = Modifier.testTag("video-start-over")) { Text(t("Start over", "从头开始")) }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { previous?.invoke() }, enabled = previous != null, modifier = Modifier.testTag("video-previous")) { Text(t("Previous video", "上一个视频")) }
            OutlinedButton(onClick = { next?.invoke() }, enabled = next != null, modifier = Modifier.testTag("video-next")) { Text(t("Next video", "下一个视频")) }
        }
        Text("${videoTime(state.position)} / ${videoTime(state.duration)}", Modifier.testTag("video-position"))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { offerResume = false; player.playPause() }, enabled = state.ready && !state.seeking) { Text(if (state.playing) t("Pause", "暂停") else t("Play", "播放")) }
            OutlinedButton(onClick = { player.seek(state.position - 10000) }, enabled = state.ready && !state.seeking) { Text(t("Back 10s", "后退 10 秒")) }
            OutlinedButton(onClick = { player.seek(state.position + 10000) }, enabled = state.ready && !state.seeking) { Text(t("Forward 10s", "前进 10 秒")) }
        }
        var scrub by remember(reader) { mutableStateOf<Float?>(null) }
        Slider(value = scrub ?: state.position.toFloat().coerceIn(0f, state.duration.coerceAtLeast(1).toFloat()),
            onValueChange = { scrub = it }, onValueChangeFinished = { scrub?.let { player.seek(it.toInt()) }; scrub = null },
            valueRange = 0f..state.duration.coerceAtLeast(1).toFloat(), enabled = state.ready && !state.seeking,
            modifier = Modifier.testTag("video-seek"))
        }
    }
    if (fullScreen) FilledTonalButton(onClick = { fullScreen = false },
        modifier = Modifier.align(Alignment.TopEnd).safeDrawingPadding().padding(12.dp).testTag("video-exit-fullscreen")) {
        Text(t("Show controls", "显示控制"))
    }
    if (fullScreen && (state.seeking || state.buffering)) Surface(Modifier.align(Alignment.BottomCenter).safeDrawingPadding().padding(16.dp)) {
        Text(if (state.seeking) t("Seeking…", "正在跳转…") else t("Buffering…", "正在缓冲…"), Modifier.padding(12.dp))
    }
    }
}
