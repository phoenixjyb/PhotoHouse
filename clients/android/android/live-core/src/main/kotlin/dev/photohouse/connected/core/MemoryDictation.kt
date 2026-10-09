package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.UUID

enum class MemoryDictationFailure {
    INVALID_RECORDING,
    UNUSABLE_TRANSCRIPT,
    RECORDING_FAILED,
    OFFLINE,
    RATE_LIMITED,
    TRANSCRIPTION_FAILED,
}

data class MemoryDictationState(
    val loading: Boolean = false,
    val capabilities: AssistantCapabilities? = null,
    val recording: Boolean = false,
    val transcribing: Boolean = false,
    val transcript: String? = null,
    val failure: String? = null,
    val retryAtMillis: Long = 0,
    val requestReceipt: AssistantRequestReceipt? = null,
    /** Stable presentation-independent category; [failure] remains for existing callers. */
    val failureCode: MemoryDictationFailure? = null,
)

/** One-shot, in-memory voice transcription. The owner controls session and library validity. */
class MemoryDictationStore(
    private val scope: CoroutineScope,
    private val capabilities: suspend () -> AssistantCapabilities,
    private val transcribe: suspend (ByteArray, String) -> AssistantTranscript,
    private val onDenied: () -> Unit = {},
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val mutable = MutableStateFlow(MemoryDictationState())
    val state = mutable.asStateFlow()

    private var closed = false
    private var generation = 0L
    private var capabilitiesGeneration = 0L
    private var capabilitiesJob: Job? = null
    private var transcriptionJob: Job? = null
    private var ownedAudio: ByteArray? = null

    @Synchronized
    fun loadCapabilities() {
        if (closed || mutable.value.loading || mutable.value.recording || mutable.value.transcribing ||
            mutable.value.transcript != null || now() < mutable.value.retryAtMillis) return
        val token = ++capabilitiesGeneration
        mutable.value = mutable.value.copy(loading = true, failure = null)
        capabilitiesJob = scope.launch {
            try {
                val result = capabilities()
                synchronized(this@MemoryDictationStore) {
                    if (closed || token != capabilitiesGeneration) return@synchronized
                    mutable.value = mutable.value.copy(loading = false, capabilities = result, failure = null,
                        failureCode = null, retryAtMillis = 0)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                val denied = e is ApiFailure && e.status in setOf(401, 403)
                val current = synchronized(this@MemoryDictationStore) {
                    if (closed || token != capabilitiesGeneration) return@synchronized false
                    if (denied) {
                        clearPrivateState(clearCapabilities = true)
                    } else {
                        mutable.value = mutable.value.copy(loading = false, failure = failureMessage(e),
                            failureCode = failureCode(e), retryAtMillis = retryAt(e))
                    }
                    true
                }
                if (denied && current) onDenied()
            }
        }
    }

    /** Returns the bounded recording duration in seconds, or null when unavailable. */
    @Synchronized
    fun beginRecording(): Int? {
        val current = mutable.value
        val caps = current.capabilities ?: return null
        if (closed || current.loading || now() < current.retryAtMillis || current.recording || current.transcribing || current.transcript != null ||
            !caps.enabled || !caps.transcribe || caps.maxAudioSeconds !in 1..30) return null
        generation++
        mutable.value = current.copy(recording = true, failure = null, failureCode = null,
            retryAtMillis = 0, requestReceipt = null)
        return caps.maxAudioSeconds
    }

    /** Takes ownership via a copy; both caller and owned buffers are wiped on every exit. */
    @Synchronized
    fun stopRecording(wav: ByteArray) {
        if (closed || !mutable.value.recording) {
            wav.fill(0)
            return
        }
        val caps = mutable.value.capabilities
        val audio = wav.copyOf()
        wav.fill(0)
        mutable.value = mutable.value.copy(recording = false)
        // PCM byte length is authoritative. Microphone initialization and dispatcher
        // scheduling can make a valid full-length recording exceed a wall-clock cap.
        if (caps == null || !validWavWithin(audio, caps.maxAudioSeconds)) {
            audio.fill(0)
            mutable.value = mutable.value.copy(failure = "Recording was invalid or too long / 录音无效或过长",
                failureCode = MemoryDictationFailure.INVALID_RECORDING, retryAtMillis = 0)
            return
        }
        val token = ++generation
        ownedAudio = audio
        val requestId = UUID.randomUUID().toString()
        mutable.value = mutable.value.copy(transcribing = true, failure = null, failureCode = null,
            retryAtMillis = 0, requestReceipt = null)
        transcriptionJob = scope.launch {
            try {
                val result = transcribe(audio, requestId)
                synchronized(this@MemoryDictationStore) {
                    if (closed || token != generation) return@synchronized
                    if (!validTranscript(result.text) || result.receipt?.requestId?.let { it != requestId } == true) {
                        mutable.value = mutable.value.copy(transcribing = false, transcript = null,
                            failure = "Could not use this transcript / 无法使用这段转写",
                            failureCode = MemoryDictationFailure.UNUSABLE_TRANSCRIPT, retryAtMillis = 0)
                    } else {
                        mutable.value = mutable.value.copy(transcribing = false, transcript = result.text,
                            failure = null, failureCode = null, retryAtMillis = 0, requestReceipt = result.receipt)
                    }
                    wipeOwnedAudio()
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                val denied = e is ApiFailure && e.status in setOf(401, 403)
                val current = synchronized(this@MemoryDictationStore) {
                    if (closed || token != generation) return@synchronized false
                    wipeOwnedAudio()
                    if (denied) clearPrivateState(clearCapabilities = true)
                    else mutable.value = mutable.value.copy(transcribing = false, transcript = null,
                        failure = failureMessage(e), failureCode = failureCode(e),
                        retryAtMillis = retryAt(e), requestReceipt = null)
                    true
                }
                if (denied && current) onDenied()
            } finally {
                audio.fill(0)
            }
        }
    }

    @Synchronized
    fun recordingFailed() {
        if (closed || !mutable.value.recording) return
        generation++
        mutable.value = mutable.value.copy(recording = false, failure = "Recording failed; try again / 录音失败，请重试",
            failureCode = MemoryDictationFailure.RECORDING_FAILED, retryAtMillis = 0)
    }

    @Synchronized
    fun cancel() {
        if (closed) return
        generation++
        transcriptionJob?.cancel()
        transcriptionJob = null
        wipeOwnedAudio()
        mutable.value = mutable.value.copy(recording = false, transcribing = false, transcript = null,
            failure = null, failureCode = null, requestReceipt = null)
    }

    @Synchronized
    fun dismissTranscript() {
        if (closed || mutable.value.transcript == null) return
        mutable.value = mutable.value.copy(transcript = null, requestReceipt = null, failure = null,
            failureCode = null, retryAtMillis = 0)
    }

    @Synchronized
    fun updateTranscript(value: String) {
        if (closed || mutable.value.transcript == null || !validEditedTranscript(value)) return
        mutable.value = mutable.value.copy(transcript = value)
    }

    /** Explicitly extracts text for the caller to insert into its editor. */
    @Synchronized
    fun takeTranscript(): String? {
        if (closed) return null
        val text = mutable.value.transcript ?: return null
        mutable.value = mutable.value.copy(transcript = null, requestReceipt = null, failure = null,
            failureCode = null, retryAtMillis = 0)
        return text
    }

    @Synchronized
    fun close() {
        if (closed) return
        closed = true
        generation++
        capabilitiesGeneration++
        capabilitiesJob?.cancel()
        transcriptionJob?.cancel()
        capabilitiesJob = null
        transcriptionJob = null
        wipeOwnedAudio()
        mutable.value = MemoryDictationState()
    }

    private fun clearPrivateState(clearCapabilities: Boolean) {
        generation++
        capabilitiesGeneration++
        transcriptionJob?.cancel()
        wipeOwnedAudio()
        mutable.value = MemoryDictationState(capabilities = if (clearCapabilities) null else mutable.value.capabilities)
    }

    private fun wipeOwnedAudio() {
        ownedAudio?.fill(0)
        ownedAudio = null
    }

    private fun retryAt(error: Exception): Long {
        val delay = (error as? ApiFailure)?.takeIf { it.status == 429 }?.retryAfterMillis?.coerceAtLeast(0) ?: 0
        val at = now()
        return if (delay == 0L) 0 else if (delay > Long.MAX_VALUE - at) Long.MAX_VALUE else at + delay
    }

    private fun failureMessage(error: Exception): String = when {
        error is ApiFailure && error.kind == FailureKind.OFFLINE -> "Offline; try again when connected / 当前离线，请联网后重试"
        error is ApiFailure && error.status == 429 -> "Too many requests; wait before trying again / 请求过多，请稍后重试"
        else -> "Transcription failed; try again / 转写失败，请重试"
    }

    private fun failureCode(error: Exception): MemoryDictationFailure = when {
        error is ApiFailure && error.kind == FailureKind.OFFLINE -> MemoryDictationFailure.OFFLINE
        error is ApiFailure && error.status == 429 -> MemoryDictationFailure.RATE_LIMITED
        else -> MemoryDictationFailure.TRANSCRIPTION_FAILED
    }

    private fun validTranscript(value: String): Boolean {
        if (value.isBlank() || !validUnicodeText(value)) return false
        val encoded = runCatching {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value)).remaining()
        }.getOrNull() ?: return false
        return encoded <= 1024 && value.codePointCount(0, value.length) <= 2048
    }

    private fun validEditedTranscript(value: String): Boolean {
        if (!validUnicodeText(value)) return false
        val encoded = runCatching {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value)).remaining()
        }.getOrNull() ?: return false
        return encoded <= 64 * 1024
    }

    private fun validUnicodeText(value: String): Boolean =
        value.none { it.isISOControl() && it !in "\n\t" } && runCatching {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value))
        }.isSuccess

    private fun validWavWithin(bytes: ByteArray, maxSeconds: Int): Boolean {
        if (bytes.size !in 44..(44 + 16_000 * 2 * maxSeconds) || !bytes.hasAscii(0, "RIFF") || !bytes.hasAscii(8, "WAVE") ||
            !bytes.hasAscii(12, "fmt ") || !bytes.hasAscii(36, "data")) return false
        val dataSize = bytes.size - 44L
        if (u32(bytes, 4) != bytes.size - 8L || u32(bytes, 16) != 16L || u16(bytes, 20) != 1L ||
            u16(bytes, 22) != 1L || u32(bytes, 24) != 16_000L || u32(bytes, 28) != 32_000L ||
            u16(bytes, 32) != 2L || u16(bytes, 34) != 16L || u32(bytes, 40) != dataSize || dataSize <= 0 || dataSize % 2 != 0L) return false
        val durationMillis = dataSize * 1000L / 32_000L
        return durationMillis in 500..(maxSeconds * 1000L)
    }

    private fun ByteArray.hasAscii(offset: Int, value: String): Boolean =
        offset >= 0 && offset + value.length <= size && value.indices.all { this[offset + it] == value[it].code.toByte() }

    private fun u16(bytes: ByteArray, offset: Int): Long =
        (bytes[offset].toLong() and 0xff) or ((bytes[offset + 1].toLong() and 0xff) shl 8)

    private fun u32(bytes: ByteArray, offset: Int): Long? {
        if (offset < 0 || offset + 4 > bytes.size) return null
        return (bytes[offset].toLong() and 0xff) or ((bytes[offset + 1].toLong() and 0xff) shl 8) or
            ((bytes[offset + 2].toLong() and 0xff) shl 16) or ((bytes[offset + 3].toLong() and 0xff) shl 24)
    }
}
