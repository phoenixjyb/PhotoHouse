package dev.photohouse.connected

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Fixed capacity avoids leaving earlier PCM copies behind when an accumulator grows. */
private class RecordingPcmBuffer(capacity: Int) : ByteArrayOutputStream(capacity) {
    fun wipe() { buf.fill(0); reset() }
}

/** Owns at most one capture. Each returned capture is one-shot and can be stopped permanently. */
internal class AnnotationAudioRecorder {
    private var active: Capture? = null

    @Synchronized fun beginCapture(maxSeconds: Int = 60): Capture {
        check(active == null) { "A microphone capture is already active" }
        require(maxSeconds in 1..60)
        return Capture(maxSeconds) { completed -> synchronized(this) { if (active === completed) active = null } }
            .also { active = it }
    }

    @Synchronized fun stop() { active?.discard() }

    internal class Capture(private val maxSeconds: Int, private val onFinished: (Capture) -> Unit) {
        private val lifecycle = RecordingLifecycle()
        @Volatile private var recorder: AudioRecord? = null
        @Volatile var recordedMillis: Int = 0
            private set

        fun stop() {
            if (lifecycle.stop(discard = false) { runCatching { recorder?.stop() } }) onFinished(this)
        }

        fun discard() {
            if (lifecycle.stop(discard = true) { runCatching { recorder?.stop() } }) onFinished(this)
        }

        val wasDiscarded get() = lifecycle.wasDiscarded
        fun consumeForUpload(): Boolean = lifecycle.consumeForUpload()

        fun record(): ByteArray? {
            if (!lifecycle.claim()) return null
            val rate = 16_000
            val maxPcmBytes = rate * 2 * maxSeconds
            val pcm = RecordingPcmBuffer(maxPcmBytes)
            val buffer = ByteArray(4096)
            var audio: AudioRecord? = null
            try {
                try {
                    val minBuffer = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
                    require(minBuffer > 0) { "Microphone recording is unavailable" }
                    val created = AudioRecord(MediaRecorder.AudioSource.MIC, rate, AudioFormat.CHANNEL_IN_MONO,
                        AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuffer, 4096))
                    audio = created
                    recorder = created
                    require(created.state == AudioRecord.STATE_INITIALIZED) { "Microphone recording is unavailable" }
                    if (!lifecycle.start { created.startRecording() }) return null
                    while (lifecycle.isRunning && pcm.size() < maxPcmBytes) {
                        val count = created.read(buffer, 0, minOf(buffer.size, maxPcmBytes - pcm.size()))
                        if (count < 0) {
                            if (lifecycle.isRunning) throw IllegalStateException("Microphone recording failed")
                            break
                        }
                        if (count > 0) {
                            pcm.write(buffer, 0, count)
                            recordedMillis = pcm.size() * 1000 / (rate * 2)
                        }
                    }
                } catch (_: SecurityException) {
                    // Permission can be revoked after the UI check but before AudioRecord starts.
                    // Keep the capture empty and let the caller show its existing recording error.
                    return null
                } finally {
                    try {
                        audio?.let { runCatching { it.stop() }; it.release() }
                    } finally {
                        recorder = null
                        lifecycle.finish()
                        onFinished(this)
                    }
                }
                if (!lifecycle.wasStarted) return null
                val samples = pcm.toByteArray()
                try { return annotationWavFromPcm(samples, rate) }
                finally { samples.fill(0) }
            } finally {
                buffer.fill(0)
                pcm.wipe()
            }
        }
    }
}

/** Small synchronized state machine kept independent of Android audio APIs for lifecycle tests. */
internal class RecordingLifecycle {
    private enum class State { PENDING, RUNNING, STOPPED, FINISHED, CONSUMED }
    private var state = State.PENDING
    private var started = false
    private var discarded = false

    @Synchronized fun claim(): Boolean {
        if (state != State.PENDING) return false
        state = State.RUNNING
        return true
    }

    @Synchronized fun start(startAudio: () -> Unit): Boolean {
        if (state != State.RUNNING) return false
        started = true
        startAudio()
        return true
    }

    @Synchronized fun stop(discard: Boolean, stopAudio: () -> Unit): Boolean {
        if (state == State.FINISHED) {
            if (discard) discarded = true
            return false
        }
        if (state == State.STOPPED) {
            if (discard) discarded = true
            return false
        }
        if (state == State.PENDING || state == State.RUNNING) {
            val wasPending = state == State.PENDING
            state = State.STOPPED
            discarded = discard
            stopAudio()
            if (wasPending) state = State.FINISHED
            return wasPending
        }
        return false
    }

    @get:Synchronized val isRunning get() = state == State.RUNNING
    @get:Synchronized val wasStarted get() = started
    @get:Synchronized val wasDiscarded get() = discarded

    @Synchronized fun finish() { state = State.FINISHED }

    @Synchronized fun consumeForUpload(): Boolean {
        if (state != State.FINISHED || discarded) return false
        state = State.CONSUMED
        return true
    }
}

internal fun annotationWavFromPcm(pcm: ByteArray, sampleRate: Int): ByteArray {
    require(sampleRate == 16_000 || sampleRate == 48_000)
    require(pcm.size >= sampleRate && pcm.size <= sampleRate * 2 * 60 && pcm.size % 2 == 0)
    val result = ByteArray(44 + pcm.size)
    require(result.size <= 2 * 1024 * 1024)
    val out = ByteBuffer.wrap(result).order(ByteOrder.LITTLE_ENDIAN)
    out.put("RIFF".toByteArray(Charsets.US_ASCII)); out.putInt(result.size - 8)
    out.put("WAVEfmt ".toByteArray(Charsets.US_ASCII)); out.putInt(16); out.putShort(1)
    out.putShort(1); out.putInt(sampleRate); out.putInt(sampleRate * 2); out.putShort(2); out.putShort(16)
    out.put("data".toByteArray(Charsets.US_ASCII)); out.putInt(pcm.size); out.put(pcm)
    return result
}
