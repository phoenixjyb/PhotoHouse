package dev.photohouse.connected.core

import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction

/** Identity of the authenticated foreground context that authorized a voice session. */
data class VoiceSessionScope(
    val accountId: String,
    val libraryId: String,
    val appGeneration: Long,
) {
    init {
        require(accountId.isNotBlank())
        require(libraryId.isNotBlank())
        require(appGeneration >= 0)
    }
}

enum class VoiceSessionPhase { IDLE, LISTENING, TRANSCRIBING, REQUESTING, SPEAKING, PAUSED, ENDED }

data class VoiceSessionBinding(
    val scope: VoiceSessionScope,
    val sessionGeneration: Long,
    val operationGeneration: Long,
)

data class VoiceSessionState(
    val phase: VoiceSessionPhase = VoiceSessionPhase.IDLE,
    val scope: VoiceSessionScope? = null,
    val sessionGeneration: Long = 0,
    val operationGeneration: Long = 0,
    val reason: VoiceSessionStopReason? = null,
    val replyText: String? = null,
    val reviewRequired: Boolean = false,
    /** Observation only: the platform confirmed AudioRecord.startRecording succeeded. */
    val captureStarted: Boolean = false,
    /** Observation only: the platform confirmed speech playback actually began. */
    val playbackStarted: Boolean = false,
    /** Latest completed client-observed turn timing in this foreground voice session. */
    val clientTiming: VoiceTurnTimingSummary? = null,
    /** Whether this opted-in session is reading a bounded saved-memory sequence. */
    val readingContinuation: Boolean = false,
    /** Zero-based segment currently completed or requested while reading. */
    val readingSegment: Int? = null,
    val readingSegmentCount: Int? = null,
) {
    val microphoneActive: Boolean get() = phase == VoiceSessionPhase.LISTENING
    val speechActive: Boolean get() = phase == VoiceSessionPhase.SPEAKING
}

enum class VoiceSessionStopReason {
    USER_PAUSED,
    USER_ENDED,
    BACKGROUNDED,
    AUDIO_FOCUS_LOST,
    CONTEXT_CHANGED,
    CAPTURE_FAILED,
    TRANSCRIPTION_FAILED,
    REQUEST_FAILED,
    UNCERTAIN_REQUEST,
    SPEECH_FAILED,
    EMPTY_TRANSCRIPT,
    TRANSCRIPT_TOO_LONG,
    INVALID_TRANSCRIPT,
    REVIEW_REQUIRED,
    READING_NEEDS_SELECTION,
    READING_UNAVAILABLE,
    READING_FINISHED,
}

enum class VoiceRequestReceipt { CONFIRMED_SUCCESS, CONFIRMED_FAILURE, UNCERTAIN }

enum class VoiceReplyDisposition { READ_ONLY, REVIEW_REQUIRED }

data class VoiceAssistantReply(
    val text: String,
    val receipt: VoiceRequestReceipt,
    val disposition: VoiceReplyDisposition = VoiceReplyDisposition.READ_ONLY,
    /** Opaque presentation identity for an unsaved review card; never an execution token. */
    val reviewCardId: String? = null,
)

sealed interface VoiceSessionEffect {
    data class StartCapture(val binding: VoiceSessionBinding) : VoiceSessionEffect
    data class StopCapture(val binding: VoiceSessionBinding?) : VoiceSessionEffect
    data class Transcribe(val binding: VoiceSessionBinding) : VoiceSessionEffect
    data class SubmitReadOnlyRequest(val binding: VoiceSessionBinding, val text: String) : VoiceSessionEffect
    data class ShowReviewCard(val binding: VoiceSessionBinding, val reviewCardId: String) : VoiceSessionEffect
    data class Speak(val binding: VoiceSessionBinding, val text: String) : VoiceSessionEffect
    data class ReadMemorySegment(
        val binding: VoiceSessionBinding,
        val segment: Int,
        val segmentCount: Int,
    ) : VoiceSessionEffect
    data class StopSpeech(val binding: VoiceSessionBinding?) : VoiceSessionEffect
    /** Cancels local waiting only. The caller must treat a sent request as uncertain. */
    data class CancelInFlight(val binding: VoiceSessionBinding) : VoiceSessionEffect
}

data class VoiceSessionTransition(
    val state: VoiceSessionState,
    val effects: List<VoiceSessionEffect> = emptyList(),
    val accepted: Boolean = true,
)

/**
 * Deterministic half-duplex listen → transcribe → read-only request → speak → listen loop.
 * Platform capture, networking, playback and UI remain effects owned by the caller.
 */
class VoiceSessionController {
    var state: VoiceSessionState = VoiceSessionState()
        private set

    private var nextSessionGeneration = 0L
    private var nextOperationGeneration = 0L
    private var activeBinding: VoiceSessionBinding? = null

    /** Only this explicit call can grant a new foreground microphone session. */
    @Synchronized
    fun start(scope: VoiceSessionScope, foreground: Boolean): VoiceSessionTransition {
        if (!foreground || state.phase !in setOf(VoiceSessionPhase.IDLE, VoiceSessionPhase.ENDED)) return rejected()
        return beginSession(scope)
    }

    /** Starts a foreground voice session attached to a bounded saved-memory reading selection. */
    @Synchronized
    fun startMemoryReading(
        scope: VoiceSessionScope,
        foreground: Boolean,
        segment: Int,
        segmentCount: Int,
    ): VoiceSessionTransition {
        if (!foreground || state.phase !in setOf(VoiceSessionPhase.IDLE, VoiceSessionPhase.ENDED) ||
            segment < 0 || segmentCount !in 1..MAX_READING_SEGMENTS || segment >= segmentCount - 1) return rejected()
        return beginSession(scope, readingSegment = segment, readingSegmentCount = segmentCount)
    }

    /** Resuming a paused loop is explicit and cannot switch account, library or app generation. */
    @Synchronized
    fun resume(scope: VoiceSessionScope, foreground: Boolean): VoiceSessionTransition {
        if (!foreground || state.phase != VoiceSessionPhase.PAUSED || state.scope != scope) return rejected()
        return beginSession(scope)
    }

    private fun beginSession(
        scope: VoiceSessionScope,
        readingSegment: Int? = null,
        readingSegmentCount: Int? = null,
    ): VoiceSessionTransition {
        nextSessionGeneration++
        activeBinding = newBinding(scope)
        state = VoiceSessionState(
            phase = VoiceSessionPhase.LISTENING,
            scope = scope,
            sessionGeneration = nextSessionGeneration,
            operationGeneration = activeBinding!!.operationGeneration,
            readingContinuation = readingSegment != null,
            readingSegment = readingSegment,
            readingSegmentCount = readingSegmentCount,
        )
        return accepted(VoiceSessionEffect.StartCapture(activeBinding!!))
    }

    @Synchronized
    fun captureCompleted(binding: VoiceSessionBinding): VoiceSessionTransition {
        if (!matches(binding, VoiceSessionPhase.LISTENING)) return rejected()
        val next = rotateBinding()
        state = state.copy(phase = VoiceSessionPhase.TRANSCRIBING, operationGeneration = next.operationGeneration,
            captureStarted = false, playbackStarted = false)
        return accepted(VoiceSessionEffect.StopCapture(binding), VoiceSessionEffect.Transcribe(next))
    }

    @Synchronized
    fun transcriptReady(binding: VoiceSessionBinding, text: String): VoiceSessionTransition {
        if (!matches(binding, VoiceSessionPhase.TRANSCRIBING)) return rejected()
        if (text.isBlank()) return pauseInternal(VoiceSessionStopReason.EMPTY_TRANSCRIPT)
        val utf8Bytes = runCatching {
            Charsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(text)).remaining()
        }.getOrNull()
        if (utf8Bytes == null) return pauseInternal(VoiceSessionStopReason.INVALID_TRANSCRIPT)
        if (text.codePointCount(0, text.length) > MAX_TRANSCRIPT_CODE_POINTS || utf8Bytes > MAX_TRANSCRIPT_UTF8_BYTES) {
            return pauseInternal(VoiceSessionStopReason.TRANSCRIPT_TOO_LONG)
        }
        val spokenControl = classifyVoiceSessionSpokenControl(text)
        when (spokenControl) {
            VoiceSessionSpokenControl.PAUSE -> return pauseInternal(VoiceSessionStopReason.USER_PAUSED)
            VoiceSessionSpokenControl.END -> return stopInternal(VoiceSessionPhase.ENDED, VoiceSessionStopReason.USER_ENDED)
            VoiceSessionSpokenControl.CONTINUE_READING -> Unit
            null -> Unit
        }
        if (spokenControl == VoiceSessionSpokenControl.CONTINUE_READING) {
            if (!state.readingContinuation) return pauseInternal(VoiceSessionStopReason.READING_NEEDS_SELECTION)
            val segment = requireNotNull(state.readingSegment) + 1
            val segmentCount = requireNotNull(state.readingSegmentCount)
            val next = rotateBinding()
            state = state.copy(
                phase = VoiceSessionPhase.SPEAKING,
                operationGeneration = next.operationGeneration,
                readingSegment = segment,
                captureStarted = false,
                playbackStarted = false,
            )
            return accepted(VoiceSessionEffect.ReadMemorySegment(next, segment, segmentCount))
        }
        state = state.copy(readingContinuation = false, readingSegment = null, readingSegmentCount = null)
        val next = rotateBinding()
        state = state.copy(phase = VoiceSessionPhase.REQUESTING, operationGeneration = next.operationGeneration,
            captureStarted = false, playbackStarted = false)
        return accepted(VoiceSessionEffect.SubmitReadOnlyRequest(next, text))
    }

    @Synchronized
    fun requestCompleted(binding: VoiceSessionBinding, reply: VoiceAssistantReply): VoiceSessionTransition {
        if (!matches(binding, VoiceSessionPhase.REQUESTING)) return rejected()
        if (reply.receipt == VoiceRequestReceipt.UNCERTAIN) {
            return pauseInternal(VoiceSessionStopReason.UNCERTAIN_REQUEST)
        }
        if (reply.receipt == VoiceRequestReceipt.CONFIRMED_FAILURE) {
            return pauseInternal(VoiceSessionStopReason.REQUEST_FAILED)
        }
        if (reply.text.isBlank()) return pauseInternal(VoiceSessionStopReason.REQUEST_FAILED)
        if (reply.disposition == VoiceReplyDisposition.REVIEW_REQUIRED && reply.reviewCardId.isNullOrBlank()) {
            return pauseInternal(VoiceSessionStopReason.REQUEST_FAILED)
        }
        val next = rotateBinding()
        state = state.copy(
            phase = VoiceSessionPhase.SPEAKING,
            operationGeneration = next.operationGeneration,
            replyText = reply.text,
            reviewRequired = reply.disposition == VoiceReplyDisposition.REVIEW_REQUIRED,
            captureStarted = false,
            playbackStarted = false,
        )
        val effects = buildList {
            if (reply.disposition == VoiceReplyDisposition.REVIEW_REQUIRED) {
                add(VoiceSessionEffect.ShowReviewCard(next, requireNotNull(reply.reviewCardId)))
            }
            add(VoiceSessionEffect.Speak(next, reply.text))
        }
        return VoiceSessionTransition(state, effects)
    }

    /** The next capture starts only after the playback owner reports actual completion. */
    @Synchronized
    fun speechCompleted(binding: VoiceSessionBinding, success: Boolean): VoiceSessionTransition {
        if (!matches(binding, VoiceSessionPhase.SPEAKING)) return rejected()
        if (!success) return pauseInternal(VoiceSessionStopReason.SPEECH_FAILED)
        if (state.readingContinuation) {
            val segment = requireNotNull(state.readingSegment)
            val segmentCount = requireNotNull(state.readingSegmentCount)
            if (segment + 1 >= segmentCount) {
                return pauseInternal(VoiceSessionStopReason.READING_FINISHED)
            }
        }
        if (state.reviewRequired) return pauseAfterReviewSpeech()
        val next = rotateBinding()
        state = state.copy(
            phase = VoiceSessionPhase.LISTENING,
            operationGeneration = next.operationGeneration,
            replyText = null,
            reviewRequired = false,
            captureStarted = false,
            playbackStarted = false,
        )
        return accepted(VoiceSessionEffect.StartCapture(next))
    }

    /** Pauses a clarification or review turn without submitting or confirming a mutation. */
    @Synchronized
    fun suspendForReview(binding: VoiceSessionBinding): VoiceSessionTransition {
        if (state.phase !in setOf(VoiceSessionPhase.REQUESTING, VoiceSessionPhase.SPEAKING) ||
            activeBinding != binding || state.scope != binding.scope ||
            state.sessionGeneration != binding.sessionGeneration) return rejected()
        return stopInternal(VoiceSessionPhase.PAUSED, VoiceSessionStopReason.REVIEW_REQUIRED, preserveReview = true)
    }

    /** Capture, ASR or local adapter failure pauses the loop without an automatic retry. */
    @Synchronized
    fun operationFailed(binding: VoiceSessionBinding): VoiceSessionTransition {
        if (activeBinding != binding || state.scope != binding.scope ||
            state.sessionGeneration != binding.sessionGeneration) return rejected()
        val reason = when (state.phase) {
            VoiceSessionPhase.LISTENING -> VoiceSessionStopReason.CAPTURE_FAILED
            VoiceSessionPhase.TRANSCRIBING -> VoiceSessionStopReason.TRANSCRIPTION_FAILED
            VoiceSessionPhase.REQUESTING -> VoiceSessionStopReason.REQUEST_FAILED
            VoiceSessionPhase.SPEAKING -> VoiceSessionStopReason.SPEECH_FAILED
            else -> return rejected()
        }
        return pauseInternal(reason)
    }

    @Synchronized
    fun pause(): VoiceSessionTransition = pauseInternal(VoiceSessionStopReason.USER_PAUSED)

    @Synchronized
    fun end(): VoiceSessionTransition = stopInternal(VoiceSessionPhase.ENDED, VoiceSessionStopReason.USER_ENDED)

    @Synchronized
    fun backgrounded(): VoiceSessionTransition = pauseInternal(VoiceSessionStopReason.BACKGROUNDED)

    @Synchronized
    fun audioFocusLost(): VoiceSessionTransition = pauseInternal(VoiceSessionStopReason.AUDIO_FOCUS_LOST)

    @Synchronized
    fun contextChanged(scope: VoiceSessionScope?): VoiceSessionTransition {
        if (scope == state.scope) return rejected()
        return stopInternal(VoiceSessionPhase.ENDED, VoiceSessionStopReason.CONTEXT_CHANGED)
    }

    /** Pauses the opted-in loop if its caller can no longer resolve the selected memory source. */
    @Synchronized
    fun readingUnavailable(): VoiceSessionTransition {
        if (!state.readingContinuation || state.phase in setOf(VoiceSessionPhase.IDLE, VoiceSessionPhase.PAUSED, VoiceSessionPhase.ENDED)) {
            return rejected()
        }
        return pauseInternal(VoiceSessionStopReason.READING_UNAVAILABLE)
    }

    private fun pauseInternal(reason: VoiceSessionStopReason): VoiceSessionTransition =
        stopInternal(VoiceSessionPhase.PAUSED, reason)

    private fun pauseAfterReviewSpeech(): VoiceSessionTransition {
        activeBinding = null
        nextOperationGeneration++
        state = state.copy(
            phase = VoiceSessionPhase.PAUSED,
            operationGeneration = nextOperationGeneration,
            reason = VoiceSessionStopReason.REVIEW_REQUIRED,
            replyText = null,
            reviewRequired = true,
            captureStarted = false,
            playbackStarted = false,
            readingContinuation = false,
            readingSegment = null,
            readingSegmentCount = null,
        )
        return VoiceSessionTransition(state)
    }

    private fun stopInternal(
        phase: VoiceSessionPhase,
        reason: VoiceSessionStopReason,
        preserveReview: Boolean = false,
    ): VoiceSessionTransition {
        val old = activeBinding
        val oldPhase = state.phase
        val wasCapturing = oldPhase == VoiceSessionPhase.LISTENING
        val wasSpeaking = oldPhase == VoiceSessionPhase.SPEAKING
        activeBinding = null
        nextOperationGeneration++ // Invalidates every callback from the stopped operation.
        state = state.copy(
            phase = phase,
            operationGeneration = nextOperationGeneration,
            reason = reason,
            replyText = null,
            reviewRequired = state.reviewRequired && preserveReview,
            captureStarted = false,
            playbackStarted = false,
            readingContinuation = false,
            readingSegment = null,
            readingSegmentCount = null,
        )
        val effects = buildList {
            if (wasCapturing) add(VoiceSessionEffect.StopCapture(old))
            if (wasSpeaking) add(VoiceSessionEffect.StopSpeech(old))
            if (old != null && oldPhase in setOf(VoiceSessionPhase.TRANSCRIBING, VoiceSessionPhase.REQUESTING)) {
                add(VoiceSessionEffect.CancelInFlight(requireNotNull(old)))
            }
        }
        return VoiceSessionTransition(state, effects)
    }

    private fun matches(binding: VoiceSessionBinding, phase: VoiceSessionPhase): Boolean =
        state.phase == phase && activeBinding == binding && state.scope == binding.scope &&
            state.sessionGeneration == binding.sessionGeneration

    private fun rotateBinding(): VoiceSessionBinding = newBinding(requireNotNull(state.scope)).also { activeBinding = it }

    private fun newBinding(scope: VoiceSessionScope): VoiceSessionBinding =
        VoiceSessionBinding(scope, nextSessionGeneration, ++nextOperationGeneration)

    private fun accepted(vararg effects: VoiceSessionEffect) = VoiceSessionTransition(state, effects.toList())
    private fun rejected() = VoiceSessionTransition(state, accepted = false)

    private companion object {
        const val MAX_TRANSCRIPT_CODE_POINTS = 512
        const val MAX_TRANSCRIPT_UTF8_BYTES = 1024
        const val MAX_READING_SEGMENTS = 128
    }
}
