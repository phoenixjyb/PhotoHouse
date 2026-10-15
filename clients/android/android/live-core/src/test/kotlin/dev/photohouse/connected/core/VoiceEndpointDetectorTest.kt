package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceEndpointDetectorTest {
    private fun pcm(samples: Int, amplitude: Int): ByteArray {
        val bytes = ByteArray(samples * 2)
        for (index in 0 until samples) {
            val sample = amplitude.toShort().toInt()
            bytes[index * 2] = sample.toByte()
            bytes[index * 2 + 1] = (sample shr 8).toByte()
        }
        return bytes
    }

    private fun feedInChunks(
        detector: VoiceEndpointDetector,
        input: ByteArray,
        chunkSizes: List<Int> = listOf(638, 1902, 74, 4096, 222),
    ): VoiceEndpointResult {
        var offset = 0
        var chunkIndex = 0
        var result = VoiceEndpointResult.CONTINUE
        while (offset < input.size && result == VoiceEndpointResult.CONTINUE) {
            val length = minOf(chunkSizes[chunkIndex++ % chunkSizes.size], input.size - offset)
            result = detector.accept(input, offset, length)
            offset += length
        }
        return result
    }

    private fun samples(vararg parts: Pair<Int, Int>): ByteArray {
        val total = parts.sumOf { it.first }
        val result = ByteArray(total * 2)
        var offset = 0
        for ((count, amplitude) in parts) {
            val chunk = pcm(count, amplitude)
            chunk.copyInto(result, offset)
            offset += chunk.size
        }
        return result
    }

    @Test
    fun silenceReturnsNoSpeechAtEightSecondSampleDeadline() {
        val detector = VoiceEndpointDetector(maxDurationSeconds = 30)
        val silence = pcm(16_000 * 9, 0)
        assertEquals(VoiceEndpointResult.NO_SPEECH, feedInChunks(detector, silence))
        assertEquals(VoiceEndpointResult.NO_SPEECH, detector.accept(pcm(320, 1000)))
    }

    @Test
    fun sustainedVoicedSamplesThenTrailingSilenceFinishAtAboutElevenHundredMilliseconds() {
        val detector = VoiceEndpointDetector(maxDurationSeconds = 30)
        val utterance = samples(
            4_800 to 900, // 300 ms actual voiced samples
            17_440 to 0, // 1090 ms trailing silence
            320 to 0, // trailing silence reaches 1100 ms
        )
        assertEquals(VoiceEndpointResult.UTTERANCE_FINISHED, feedInChunks(detector, utterance))
    }

    @Test
    fun subminimumFalseStartsAndClicksDoNotCreateAnUtterance() {
        val detector = VoiceEndpointDetector(maxDurationSeconds = 8)
        val falseStarts = samples(
            4_480 to 1_200, // 280 ms is below the sustained 300 ms gate
            1_600 to 0,
            320 to 4_000, // isolated click
            16_000 * 8 - 6_400 to 0,
        )
        assertEquals(VoiceEndpointResult.NO_SPEECH, feedInChunks(detector, falseStarts))
    }

    @Test
    fun shortClickDoesNotResetSilenceButSustainedSecondPhraseDoes() {
        val afterClick = VoiceEndpointDetector(maxDurationSeconds = 10)
        val clickDuringTail = samples(
            4_800 to 900,
            17_280 to 0, // 1080 ms
            320 to 4_000, // one 20 ms click
            320 to 0,
        )
        assertEquals(VoiceEndpointResult.UTTERANCE_FINISHED, feedInChunks(afterClick, clickDuringTail))

        val betweenPhrases = VoiceEndpointDetector(maxDurationSeconds = 10)
        val twoPhrases = samples(
            4_800 to 900,
            8_000 to 0, // 500 ms gap
            4_800 to 900, // sustained speech resumes and resets the silence timer
            17_440 to 0,
            320 to 0,
        )
        assertEquals(VoiceEndpointResult.UTTERANCE_FINISHED, feedInChunks(betweenPhrases, twoPhrases))
    }

    @Test
    fun hardDurationCapFinishesSpeechAndRejectsSilence() {
        val speechAtCap = VoiceEndpointDetector(maxDurationSeconds = 1)
        assertEquals(VoiceEndpointResult.UTTERANCE_FINISHED,
            feedInChunks(speechAtCap, pcm(16_000, 900)))

        val speechMeetingMinimumAtCap = VoiceEndpointDetector(maxDurationSeconds = 1)
        assertEquals(VoiceEndpointResult.UTTERANCE_FINISHED,
            feedInChunks(speechMeetingMinimumAtCap, samples(11_200 to 0, 4_800 to 900)))

        val silenceAtCap = VoiceEndpointDetector(maxDurationSeconds = 1)
        assertEquals(VoiceEndpointResult.NO_SPEECH,
            feedInChunks(silenceAtCap, pcm(16_000, 0)))
        assertTrue(runCatching { VoiceEndpointDetector(maxDurationSeconds = 0) }.isFailure)
        assertTrue(runCatching { VoiceEndpointDetector(maxDurationSeconds = 31) }.isFailure)
    }

    @Test
    fun malformedChunksAreRejectedWithoutChangingDetectorState() {
        val untouched = VoiceEndpointDetector(maxDurationSeconds = 3)
        val afterBadInputs = VoiceEndpointDetector(maxDurationSeconds = 3)
        assertTrue(runCatching { afterBadInputs.accept(byteArrayOf(1)) }.isFailure)
        assertTrue(runCatching { afterBadInputs.accept(byteArrayOf(), length = 0) }.isFailure)
        assertTrue(runCatching { afterBadInputs.accept(pcm(4, 0), offset = 8, length = 2) }.isFailure)
        assertTrue(runCatching { afterBadInputs.accept(pcm(4, 0), offset = -2, length = 2) }.isFailure)

        val sequence = samples(4_800 to 900, 17_600 to 0)
        assertEquals(feedInChunks(untouched, sequence), feedInChunks(afterBadInputs, sequence))
    }

    @Test
    fun configuredEnergyThresholdRejectsBelowGateAndAcceptsAtGate() {
        val below = VoiceEndpointDetector(maxDurationSeconds = 1)
        assertEquals(VoiceEndpointResult.NO_SPEECH, feedInChunks(below, pcm(16_000, 349)))

        val atGate = VoiceEndpointDetector(maxDurationSeconds = 1)
        assertEquals(VoiceEndpointResult.UTTERANCE_FINISHED, feedInChunks(atGate, pcm(16_000, 350)))
    }

    @Test
    fun configRejectsUnsupportedSampleRateAndInvalidThresholds() {
        assertFalse(runCatching { VoiceEndpointConfig(sampleRateHz = 48_000) }.isSuccess)
        assertFalse(runCatching { VoiceEndpointConfig(rmsThreshold = 0.0) }.isSuccess)
        assertFalse(runCatching { VoiceEndpointConfig(minimumVoicedMillis = 1) }.isSuccess)
    }
}
