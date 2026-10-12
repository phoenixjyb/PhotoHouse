package dev.photohouse.connected

import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.media3.common.AudioAttributes
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import dev.photohouse.connected.core.AssistantVoiceSessionPlatform
import dev.photohouse.connected.core.ProtectedAnnotationAudio
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume

internal fun interface AssistantVoicePlatformFactory {
    fun create(context: Context, onFocusLost: () -> Unit): AssistantVoiceSessionPlatform
}

/** Test injection changes only audio hardware; it never grants server access or session consent. */
internal val LocalAssistantVoicePlatformFactory = staticCompositionLocalOf<AssistantVoicePlatformFactory> {
    AssistantVoicePlatformFactory { context, onLost -> AndroidAssistantVoicePlatform(context, onLost) }
}

/** One foreground audio owner. Capture and playback never overlap. */
@androidx.annotation.OptIn(UnstableApi::class)
private class AndroidAssistantVoicePlatform(context: Context, private val onFocusLost: () -> Unit) : AssistantVoiceSessionPlatform {
    private val context = context.applicationContext
    private val handler = Handler(Looper.getMainLooper())
    private val recorder = AnnotationAudioRecorder()
    private val focus = LocalFocus(context)
    private var capture: AnnotationAudioRecorder.Capture? = null
    private var captureFinished: CompletableDeferred<Unit>? = null
    private var player: ExoPlayer? = null
    private var waiter: CancellableContinuation<Boolean>? = null
    private var audio: ProtectedAnnotationAudio? = null
    private var audioClosed: (() -> Unit)? = null

    override suspend fun capture(maxSeconds: Int): ByteArray? = withContext(Dispatchers.Main.immediate) {
        // Pause can finish a blocking AudioRecord read asynchronously. An
        // immediate explicit Resume must wait for that owner to release focus.
        captureFinished?.await()
        check(player == null && capture == null)
        if (!focus.request(onFocusLost)) return@withContext null
        val current = try { recorder.beginCapture(maxSeconds, endpointSpeech = true) }
        catch (error: Exception) { focus.abandon(); throw error }
        capture = current
        val finished = CompletableDeferred<Unit>()
        captureFinished = finished
        try {
            val wav = withContext(Dispatchers.IO) { current.record() }
            if (wav != null && current.consumeForUpload()) wav
            else { wav?.fill(0); null }
        } finally {
            current.stop()
            if (capture === current) capture = null
            focus.abandon()
            finished.complete(Unit)
            if (captureFinished === finished) captureFinished = null
        }
    }

    override fun finishCapture() { capture?.stop() }

    override suspend fun playSpeech(audio: ProtectedAnnotationAudio): Boolean = withContext(Dispatchers.Main.immediate) {
        check(capture == null && player == null)
        suspendCancellableCoroutine { continuation ->
            val current = ExoPlayer.Builder(context).build()
            player = current
            waiter = continuation
            this@AndroidAssistantVoicePlatform.audio = audio
            val closed: () -> Unit = { handler.post { if (player === current) finishPlayback(false) } }
            audioClosed = closed
            audio.onClose(closed)
            current.addListener(object : Player.Listener {
                override fun onPlaybackStateChanged(playbackState: Int) {
                    if (player === current && playbackState == Player.STATE_ENDED) finishPlayback(true)
                }
                override fun onPlayerError(error: PlaybackException) { if (player === current) finishPlayback(false) }
                override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) {
                    if (player === current && reason == Player.PLAY_WHEN_READY_CHANGE_REASON_AUDIO_FOCUS_LOSS) onFocusLost()
                }
            })
            continuation.invokeOnCancellation { handler.post { if (player === current) finishPlayback(false) } }
            try {
                current.setAudioAttributes(AudioAttributes.DEFAULT, true)
                current.setMediaSource(ProgressiveMediaSource.Factory(AnnotationAudioDataSource.Factory(audio))
                    .createMediaSource(MediaItem.fromUri(Uri.parse("photohouse-audio://assistant-session"))))
                current.playWhenReady = true
                current.prepare()
            } catch (_: Exception) { finishPlayback(false) }
        }
    }

    override fun stopAudio() {
        capture?.discard()
        recorder.stop()
        focus.abandon()
        finishPlayback(false)
    }

    private fun finishPlayback(success: Boolean) {
        val completion = waiter
        waiter = null
        val current = player
        player = null
        audioClosed?.let { audio?.removeOnClose(it) }
        audioClosed = null
        audio = null
        current?.let { runCatching { it.stop() }; it.release() }
        if (completion?.isActive == true) completion.resume(success)
    }

    private class LocalFocus(context: Context) : ChapterAudioFocus {
        private val manager = context.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
        private var request: android.media.AudioFocusRequest? = null
        override fun request(onLost: () -> Unit): Boolean {
            val candidate = android.media.AudioFocusRequest.Builder(android.media.AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
                .setAudioAttributes(android.media.AudioAttributes.Builder()
                    .setUsage(android.media.AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setWillPauseWhenDucked(true)
                .setOnAudioFocusChangeListener({ change -> if (change < 0) onLost() }, Handler(Looper.getMainLooper())).build()
            request = candidate
            val granted = manager.requestAudioFocus(candidate) == android.media.AudioManager.AUDIOFOCUS_REQUEST_GRANTED
            if (!granted) abandon()
            return granted
        }
        override fun abandon() { request?.let(manager::abandonAudioFocusRequest); request = null }
    }
}
