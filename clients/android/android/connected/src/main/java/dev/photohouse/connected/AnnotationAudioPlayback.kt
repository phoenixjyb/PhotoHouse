package dev.photohouse.connected

import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.common.AudioAttributes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import dev.photohouse.connected.core.ProtectedAnnotationAudio

@Composable
@androidx.annotation.OptIn(UnstableApi::class)
internal fun AnnotationAudioPlayback(audio: ProtectedAnnotationAudio, zh: Boolean,
    autoPlay: Boolean = true, testTagPrefix: String = "upload-annotation-audio") {
    fun t(en: String, cn: String) = if (zh) cn else en
    val context = LocalContext.current
    val coordinator = LocalReaderAudioCoordinator.current
    val player = remember(audio) { ExoPlayer.Builder(context).build() }
    var playing by remember(audio) { mutableStateOf(false) }
    var failed by remember(audio) { mutableStateOf(false) }
    var recordingBusy by remember(audio) { mutableStateOf(false) }
    var lease by remember(audio) { mutableStateOf<ReaderAudioCoordinator.Lease?>(null) }
    DisposableEffect(audio, player) {
        var attached = true
        val listener = object : Player.Listener {
            override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) {
                if (attached) {
                    playing = playWhenReady
                    if (!playWhenReady && !player.playWhenReady) {
                        val stoppedLease = lease
                        coordinator?.release(stoppedLease)
                        if (lease?.id == stoppedLease?.id) lease = null
                    }
                }
            }
            override fun onPlayerError(error: PlaybackException) { if (attached) failed = true }
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (attached && player.playbackState == Player.STATE_ENDED) {
                    val endedLease = lease
                    coordinator?.release(endedLease)
                    if (lease?.id == endedLease?.id) lease = null
                }
            }
        }
        val closeListener: () -> Unit = {
            val closingLease = lease
            Handler(Looper.getMainLooper()).post {
                if (attached) {
                    runCatching { player.stop() }
                    playing = false
                    coordinator?.release(closingLease)
                    if (lease?.id == closingLease?.id) lease = null
                }
            }
        }
        player.addListener(listener)
        player.setAudioAttributes(AudioAttributes.DEFAULT, true)
        player.setMediaSource(ProgressiveMediaSource.Factory(AnnotationAudioDataSource.Factory(audio))
            .createMediaSource(MediaItem.fromUri(Uri.parse("photohouse-audio://original"))))
        lease = if (autoPlay) coordinator?.acquire(ReaderAudioKind.PLAYBACK) { player.pause(); coordinator.release(lease); lease = null } else null
        recordingBusy = autoPlay && coordinator != null && lease == null
        player.playWhenReady = autoPlay && (coordinator == null || lease != null)
        player.prepare()
        audio.onClose(closeListener)
        onDispose {
            attached = false
            audio.removeOnClose(closeListener)
            player.removeListener(listener)
            player.release()
            coordinator?.release(lease)
            lease = null
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("$testTagPrefix-playback")) {
        Button(onClick = {
            if (playing) { player.pause(); coordinator?.release(lease); lease = null } else {
                if (coordinator != null) lease = coordinator.acquire(ReaderAudioKind.PLAYBACK) { player.pause(); coordinator.release(lease); lease = null }
                if (coordinator != null && lease == null) { recordingBusy = true; return@Button }
                recordingBusy = false
                if (player.playbackState == Player.STATE_ENDED) player.seekTo(0)
                player.play()
            }
        }, enabled = !audio.isClosed,
            modifier = Modifier.testTag("$testTagPrefix-toggle")) {
            Text(if (playing) t("Pause original audio", "暂停原始录音") else t("Play original audio", "播放原始录音"))
        }
        if (failed) Text(t("Audio could not play.", "录音无法播放。"), color = MaterialTheme.colorScheme.error)
        if (recordingBusy) Text(t("Finish recording before playing audio.", "请先结束录音再播放。"),
            color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("annotation-audio-busy"))
    }
}
