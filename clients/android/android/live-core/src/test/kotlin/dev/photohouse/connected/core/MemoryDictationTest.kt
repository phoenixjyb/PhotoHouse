package dev.photohouse.connected.core

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.withContext
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryDictationTest {
    private val enabled = AssistantCapabilities(true, true, true, false, 5)

    @Test fun successNeedsExplicitExtractionAndWipesInputAndOwnedAudio() = runTest {
        var sentAudio: ByteArray? = null
        var sentId: String? = null
        val store = MemoryDictationStore(this, { enabled }, { bytes, id ->
            sentAudio = bytes; sentId = id
            AssistantTranscript("海边的照片", "zh", AssistantRequestReceipt(id, "enabled", "succeeded"))
        })
        store.loadCapabilities(); advanceUntilIdle()
        assertEquals(5, store.beginRecording())
        assertNull(store.beginRecording())
        val source = wav(seconds = 1)
        store.stopRecording(source); advanceUntilIdle()
        assertTrue(source.all { it == 0.toByte() })
        assertNotNull(sentAudio)
        assertTrue(sentAudio!!.all { it == 0.toByte() })
        assertTrue(AssistantWire.validRequestId(sentId!!))
        assertEquals("海边的照片", store.state.value.transcript)
        assertEquals(sentId, store.state.value.requestReceipt?.requestId)
        store.updateTranscript("编辑后的文本")
        assertEquals("编辑后的文本", store.takeTranscript())
        assertNull(store.state.value.transcript)
        assertNull(store.takeTranscript())
    }

    @Test fun cancelDropsTranscriptAndIgnoresNonCancellableLateResponse() = runTest {
        val gate = CompletableDeferred<Unit>()
        val store = MemoryDictationStore(this, { enabled }, { _, _ ->
            withContext(NonCancellable) { gate.await() }
            AssistantTranscript("late", "en")
        })
        store.loadCapabilities(); advanceUntilIdle()
        assertNotNull(store.beginRecording())
        store.stopRecording(wav(1))
        runCurrent()
        assertTrue(store.state.value.transcribing)
        store.cancel()
        assertFalse(store.state.value.transcribing)
        assertNull(store.state.value.transcript)
        assertEquals(enabled, store.state.value.capabilities)
        gate.complete(Unit); advanceUntilIdle()
        assertNull(store.state.value.transcript)
        assertNotNull(store.beginRecording())
    }

    @Test fun denialClearsCapabilitiesAndCallsOwner() = runTest {
        var denied = 0
        val store = MemoryDictationStore(this, { enabled }, { _, _ -> throw ApiFailure(FailureKind.HTTP, 403) }, { denied++ })
        store.loadCapabilities(); advanceUntilIdle()
        store.beginRecording(); store.stopRecording(wav(1)); advanceUntilIdle()
        assertEquals(1, denied)
        assertNull(store.state.value.capabilities)
        assertFalse(store.state.value.transcribing)
        assertNull(store.state.value.transcript)
    }

    @Test fun malformedAndOverDurationAudioAreRejectedAndWiped() = runTest {
        var requests = 0
        var clock = 0L
        val store = MemoryDictationStore(this, { enabled }, { _, _ -> requests++; AssistantTranscript("ok", "en") }, now = { clock })
        store.loadCapabilities(); advanceUntilIdle()
        store.beginRecording()
        val bad = wav(1).also { it[24] = 0x40 }
        store.stopRecording(bad)
        assertTrue(bad.all { it == 0.toByte() })
        assertFalse(store.state.value.transcribing)
        assertEquals(MemoryDictationFailure.INVALID_RECORDING, store.state.value.failureCode)
        store.beginRecording()
        clock = 5_001
        val tooLong = wav(6)
        store.stopRecording(tooLong)
        assertTrue(tooLong.all { it == 0.toByte() })
        assertEquals(0, requests)
    }

    @Test fun invalidTranscriptAndReceiptMismatchAreNotExposed() = runTest {
        var answer = AssistantTranscript("bad\u0000text", "en")
        val store = MemoryDictationStore(this, { enabled }, { _, _ -> answer })
        store.loadCapabilities(); advanceUntilIdle()
        store.beginRecording(); store.stopRecording(wav(1)); advanceUntilIdle()
        assertNull(store.state.value.transcript)
        assertFalse(store.state.value.failure.isNullOrBlank())
        assertEquals(MemoryDictationFailure.UNUSABLE_TRANSCRIPT, store.state.value.failureCode)
        answer = AssistantTranscript("ok", "en", AssistantRequestReceipt("123e4567-e89b-42d3-a456-426614174001", "enabled", "succeeded"))
        store.dismissTranscript()
        store.beginRecording(); store.stopRecording(wav(1)); advanceUntilIdle()
        assertNull(store.state.value.transcript)
    }

    @Test fun rateLimitHasExplicitCooldownAndNoAutomaticRetry() = runTest {
        var clock = 1_000L
        var requests = 0
        val store = MemoryDictationStore(this, { enabled }, { _, _ ->
            requests++
            throw ApiFailure(FailureKind.HTTP, 429, 4_000)
        }, now = { clock })
        store.loadCapabilities(); advanceUntilIdle()
        store.beginRecording(); store.stopRecording(wav(1)); advanceUntilIdle()
        assertEquals(1, requests)
        assertEquals(5_000L, store.state.value.retryAtMillis)
        assertFalse(store.state.value.failure.isNullOrBlank())
        assertEquals(MemoryDictationFailure.RATE_LIMITED, store.state.value.failureCode)
        assertEquals("Too many requests; wait before trying again / 请求过多，请稍后重试", store.state.value.failure)
        assertNull(store.beginRecording())
        store.cancel(); store.loadCapabilities(); advanceUntilIdle()
        assertEquals(5_000L, store.state.value.retryAtMillis)
        assertNull(store.beginRecording())
        clock = 5_001
        assertNotNull(store.beginRecording())
        store.cancel()
        assertEquals(1, requests)
    }

    @Test fun recordingFailureHasStableCodeAndKeepsLegacyMessage() = runTest {
        val store = MemoryDictationStore(this, { enabled }, { _, _ -> error("unused") })
        store.loadCapabilities(); advanceUntilIdle()
        assertNotNull(store.beginRecording())
        store.recordingFailed()
        assertEquals(MemoryDictationFailure.RECORDING_FAILED, store.state.value.failureCode)
        assertEquals("Recording failed; try again / 录音失败，请重试", store.state.value.failure)
    }

    @Test fun fullLengthAudioAndMultilineTextSurviveSlowInitialization() = runTest {
        var clock = 0L
        val store = MemoryDictationStore(this, { enabled }, { _, _ -> AssistantTranscript("第一天\n第二天", "zh") }, now = { clock })
        store.loadCapabilities(); advanceUntilIdle(); store.beginRecording()
        clock = 7_000
        store.stopRecording(wav(5)); advanceUntilIdle()
        assertEquals("第一天\n第二天", store.takeTranscript())
    }

    private fun wav(seconds: Int): ByteArray {
        val pcmSize = 32_000 * seconds
        return ByteArray(44 + pcmSize).also { out ->
            fun tag(at: Int, text: String) = text.toByteArray(Charsets.US_ASCII).copyInto(out, at)
            fun u16(at: Int, value: Int) { out[at] = value.toByte(); out[at + 1] = (value shr 8).toByte() }
            fun u32(at: Int, value: Int) {
                repeat(4) { out[at + it] = (value shr (it * 8)).toByte() }
            }
            tag(0, "RIFF"); u32(4, out.size - 8); tag(8, "WAVE"); tag(12, "fmt ")
            u32(16, 16); u16(20, 1); u16(22, 1); u32(24, 16_000); u32(28, 32_000)
            u16(32, 2); u16(34, 16); tag(36, "data"); u32(40, pcmSize)
        }
    }
}
