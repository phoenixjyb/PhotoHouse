package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryBookCompositionDictationStoreTest {
    private fun token(seed: Char = 'a') = Bearer.from(SessionToken(86400, seed.toString().repeat(43), "Bearer"))
    private fun scope(editable: Boolean = true, actionEpoch: Long = 1) =
        MemoryBookCompositionDictationScope("account-a", token(), 3, "family-a", 7, actionEpoch, editable)

    @Test fun constructionAndUnavailableScopesDoNotLoadCapabilities() = runTest {
        val api = Api()
        var current: MemoryBookCompositionDictationScope? = scope(editable = false)
        val helper = MemoryBookCompositionDictationStore(api, backgroundScope, { current })
        assertNull(helper.state.value)
        assertEquals(0, api.capabilityRequests)
        assertNull(helper.open())
        assertEquals(0, api.capabilityRequests)

        current = scope()
        api.enabled = false
        assertNull(helper.open())
        assertEquals(0, api.capabilityRequests)
        api.enabled = true
        val voice = helper.open()
        assertNotNull(voice)
        assertSame(voice, helper.state.value)
        runCurrent()
        assertEquals(1, api.capabilityRequests)
        assertEquals(0, api.transcriptions)
    }

    @Test fun typedIntroductionChangesDoNotStaleASRAndRejectedInsertKeepsTranscript() = runTest {
        val api = Api().apply { transcriptText = " Spoken words " }
        val scope = scope()
        val helper = MemoryBookCompositionDictationStore(api, backgroundScope, { scope })
        val voice = helper.open()!!
        runCurrent()
        voice.beginRecording()
        voice.stopRecording(wav())
        runCurrent()
        assertEquals(" Spoken words ", voice.state.value.transcript)

        var typedIntroduction = "Typed before dictation"
        assertFalse(helper.insertTranscript(voice) { false })
        assertEquals("Typed before dictation", typedIntroduction)
        assertEquals(" Spoken words ", voice.state.value.transcript)

        typedIntroduction = "Typed after dictation"
        assertTrue(helper.insertTranscript(voice) { transcript ->
            typedIntroduction = "$typedIntroduction\n\n$transcript"
            true
        })
        assertEquals("Typed after dictation\n\n Spoken words ", typedIntroduction)
        assertNull(voice.state.value.transcript)
        assertFalse(helper.hasUnfinishedInput)
        assertEquals(1, api.transcriptions)
        assertTrue(api.audioBuffers.single().all { it == 0.toByte() })
    }

    @Test fun oversizedIntroductionAppendRetainsTranscriptForReview() = runTest {
        val api = Api().apply { transcriptText = "A" }
        val stableScope = scope()
        val helper = MemoryBookCompositionDictationStore(api, backgroundScope, { stableScope })
        val voice = helper.open()!!
        runCurrent()
        voice.beginRecording()
        voice.stopRecording(wav())
        runCurrent()

        val typed = "家".repeat(2000) // Exactly 6,000 UTF-8 bytes.
        var currentIntroduction = typed
        assertFalse(helper.insertTranscript(voice) { transcript ->
            val joined = "$currentIntroduction\n\n$transcript"
            if (joined.toByteArray(Charsets.UTF_8).size > MemoryBookCompositionStore.INTRODUCTION_BYTES) false
            else { currentIntroduction = joined; true }
        })
        assertEquals(typed, currentIntroduction)
        assertEquals("A", voice.state.value.transcript)
        assertTrue(helper.hasUnfinishedInput)
    }

    @Test fun lateAsrFromClosedSameScopeCannotWriteOrClearReplacementHelper() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        api.transcriptionGate = gate
        api.nonCancellableTranscription = true
        val stableScope = scope()
        val helper = MemoryBookCompositionDictationStore(api, backgroundScope, { stableScope })
        val old = helper.open()!!
        runCurrent()
        old.beginRecording()
        old.stopRecording(wav())
        runCurrent()
        assertTrue(old.state.value.transcribing)

        assertTrue(helper.clearIfCurrent(old))
        assertEquals(MemoryDictationState(), old.state.value)
        val replacement = helper.open()!!
        assertNotSame(old, replacement)
        runCurrent()

        gate.complete(Unit)
        runCurrent()
        assertSame(replacement, helper.state.value)
        assertNull(old.state.value.transcript)
        assertFalse(helper.clearIfCurrent(old))
        assertSame(replacement, helper.state.value)
        assertEquals(2, api.capabilityRequests)

        api.transcriptText = "replacement transcript"
        replacement.beginRecording()
        replacement.stopRecording(wav())
        runCurrent()
        assertEquals("replacement transcript", replacement.state.value.transcript)
        old.updateTranscript("stale edit")
        assertNull(old.takeTranscript())
        assertEquals("replacement transcript", replacement.state.value.transcript)
    }

    @Test fun changedComposerEpochInvalidatesLateCapabilityResult() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        api.capabilityGate = gate
        api.nonCancellableCapabilities = true
        var current = scope(actionEpoch = 1)
        val helper = MemoryBookCompositionDictationStore(api, backgroundScope, { current })
        val old = helper.open()!!
        runCurrent()
        current = scope(actionEpoch = 2)
        val replacement = helper.open()!!
        assertNotSame(old, replacement)
        gate.complete(Unit)
        runCurrent()
        assertEquals(MemoryDictationState(), old.state.value)
        assertSame(replacement, helper.state.value)
        assertFalse(replacement.state.value.loading)
        assertEquals(0, api.transcriptions)
        assertEquals(2, api.capabilityRequests)
    }

    private class Api : PhotoHouseApi {
        var enabled = true
        override val assistantEnabled get() = enabled
        var capabilityRequests = 0
        var transcriptions = 0
        var transcriptText = "Introduction transcript"
        var capabilityGate: CompletableDeferred<Unit>? = null
        var transcriptionGate: CompletableDeferred<Unit>? = null
        var nonCancellableCapabilities = false
        var nonCancellableTranscription = false
        val audioBuffers = mutableListOf<ByteArray>()

        override suspend fun assistantCapabilities(token: Bearer, library: String): AssistantCapabilities {
            capabilityRequests++
            capabilityGate?.takeIf { capabilityRequests == 1 }?.let { gate ->
                if (nonCancellableCapabilities) withContext(NonCancellable) { gate.await() } else gate.await()
            }
            return AssistantCapabilities(true, true, true, false, 5)
        }

        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript {
            transcriptions++
            audioBuffers += wav
            transcriptionGate?.let { gate ->
                if (nonCancellableTranscription) withContext(NonCancellable) { gate.await() } else gate.await()
                transcriptionGate = null
            }
            return AssistantTranscript(transcriptText, "en", AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        }

        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("account-a", "+12025550123", emptyList())
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 0, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail = error("unused")
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")
    }

    private fun wav(): ByteArray {
        val dataSize = 16_000 * 2
        return ByteArray(44 + dataSize).also { out ->
            fun tag(offset: Int, value: String) = value.toByteArray(Charsets.US_ASCII).copyInto(out, offset)
            fun u16(offset: Int, value: Int) { out[offset] = value.toByte(); out[offset + 1] = (value shr 8).toByte() }
            fun u32(offset: Int, value: Int) { repeat(4) { out[offset + it] = (value shr (it * 8)).toByte() } }
            tag(0, "RIFF"); u32(4, out.size - 8); tag(8, "WAVE"); tag(12, "fmt ")
            u32(16, 16); u16(20, 1); u16(22, 1); u32(24, 16_000); u32(28, 32_000)
            u16(32, 2); u16(34, 16); tag(36, "data"); u32(40, dataSize)
        }
    }
}
