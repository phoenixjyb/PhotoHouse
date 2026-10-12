package dev.photohouse.connected.core

import kotlin.math.sqrt

enum class VoiceEndpointResult { CONTINUE, UTTERANCE_FINISHED, NO_SPEECH }

/** Sample-based endpoint settings for 16 kHz mono PCM16 input. */
data class VoiceEndpointConfig(
    val sampleRateHz: Int = 16_000,
    val frameDurationMillis: Int = 20,
    /** Frames below this RMS are treated as silence. */
    val rmsThreshold: Double = 350.0,
    /** Requires sustained voiced frames so short clicks do not start an utterance. */
    val minimumVoicedMillis: Int = 300,
    val trailingSilenceMillis: Int = 1_100,
    val noSpeechTimeoutMillis: Int = 8_000,
) {
    init {
        require(sampleRateHz == 16_000) { "Endpoint input must be 16 kHz" }
        require(frameDurationMillis in 10..100)
        require(rmsThreshold.isFinite() && rmsThreshold > 0.0 && rmsThreshold <= 32_768.0)
        require(minimumVoicedMillis in frameDurationMillis..30_000)
        require(trailingSilenceMillis in frameDurationMillis..30_000)
        require(noSpeechTimeoutMillis in minimumVoicedMillis..30_000)
    }
}

/**
 * Streaming energy endpoint detector for little-endian mono PCM16.
 *
 * It keeps only sample counts and frame energy, never audio. Arbitrary adjacent
 * chunks are accepted; internal frame accounting spans chunk boundaries. A
 * sustained 300 ms RMS gate is required both to establish speech and to reset a
 * trailing-silence timer, so isolated clicks do not extend a turn.
 */
class VoiceEndpointDetector(
    maxDurationSeconds: Int,
    private val config: VoiceEndpointConfig = VoiceEndpointConfig(),
) {
    init { require(maxDurationSeconds in 1..30) }

    private val frameSamples = samplesForMillis(config.frameDurationMillis).toInt()
    private val minimumVoicedSamples = samplesForMillis(config.minimumVoicedMillis).toInt()
    private val trailingSilenceLimitSamples = samplesForMillis(config.trailingSilenceMillis)
    private val noSpeechLimitSamples = samplesForMillis(config.noSpeechTimeoutMillis)
    private val hardLimitSamples = maxDurationSeconds.toLong() * config.sampleRateHz

    private var totalSamples = 0L
    private var frameSampleCount = 0
    private var frameSumSquares = 0L
    private var speechDetected = false
    private var initialVoicedSamples = 0
    private var trailingSilenceSamples = 0L
    private var resumedVoiceCandidateSamples = 0
    private var terminalResult: VoiceEndpointResult? = null

    /**
     * Processes one chunk. A bad offset, empty/odd byte count, or range throws
     * before any detector state changes.
     */
    @Synchronized
    fun accept(pcm16le: ByteArray, offset: Int = 0, length: Int = pcm16le.size): VoiceEndpointResult {
        require(offset >= 0 && length > 0 && length % 2 == 0 && offset <= pcm16le.size - length) {
            "PCM chunk must contain a non-empty, in-range whole number of samples"
        }
        terminalResult?.let { return it }

        val end = offset + length
        var index = offset
        while (index < end) {
            val sample = ((pcm16le[index + 1].toInt() shl 8) or (pcm16le[index].toInt() and 0xff)).toShort().toInt()
            index += 2
            totalSamples++
            frameSampleCount++
            frameSumSquares += sample.toLong() * sample

            if (frameSampleCount == frameSamples) {
                completeFrame()
                terminalResult?.let { return it }
            }
            if (totalSamples >= noSpeechLimitSamples || totalSamples >= hardLimitSamples) {
                if (frameSampleCount > 0) completeFrame()
                terminalResult?.let { return it }
                if (totalSamples >= hardLimitSamples) {
                    return finish(if (speechDetected) VoiceEndpointResult.UTTERANCE_FINISHED else VoiceEndpointResult.NO_SPEECH)
                }
                if (!speechDetected) return finish(VoiceEndpointResult.NO_SPEECH)
            }
        }
        return VoiceEndpointResult.CONTINUE
    }

    private fun classifyFrame() {
        val rms = sqrt(frameSumSquares.toDouble() / frameSampleCount)
        val classifiedSamples = frameSampleCount
        val voiced = rms >= config.rmsThreshold
        if (!speechDetected) {
            if (voiced) {
                initialVoicedSamples += classifiedSamples
                if (initialVoicedSamples >= minimumVoicedSamples) speechDetected = true
            } else {
                initialVoicedSamples = 0
            }
            return
        }

        if (voiced) {
            resumedVoiceCandidateSamples += classifiedSamples
            if (resumedVoiceCandidateSamples >= minimumVoicedSamples) {
                trailingSilenceSamples = 0
                resumedVoiceCandidateSamples = 0
            }
        } else {
            // A short loud click is counted as elapsed silence when its candidate
            // is rejected; only sustained voiced samples reset the endpoint timer.
            trailingSilenceSamples += resumedVoiceCandidateSamples.toLong() + classifiedSamples
            resumedVoiceCandidateSamples = 0
        }

        if (trailingSilenceSamples >= trailingSilenceLimitSamples) {
            finish(VoiceEndpointResult.UTTERANCE_FINISHED)
        }
    }

    private fun completeFrame() {
        classifyFrame()
        frameSampleCount = 0
        frameSumSquares = 0L
    }

    private fun finish(result: VoiceEndpointResult): VoiceEndpointResult {
        terminalResult = result
        return result
    }

    private companion object {
        fun samplesForMillis(millis: Int): Long = 16_000L * millis / 1_000
    }
}
