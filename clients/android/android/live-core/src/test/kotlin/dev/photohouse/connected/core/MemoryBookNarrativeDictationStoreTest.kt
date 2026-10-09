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
class MemoryBookNarrativeDictationStoreTest {
    private val capabilities = AssistantCapabilities(true, true, true, false, 5)
    private val bookId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    private val childId = "11111111-1111-4111-8111-111111111111"
    private val defaultToken = bearer()

    private fun reader(account: String = "account", token: Bearer = defaultToken, revision: Long = 4, scopeId: Long = 9) =
        MemoryBookNarrativeScope(account, token, "family", 3, bookId, revision,
            listOf(EditorialChild(childId, "2")), scopeId)

    @Test fun constructionDoesNothingAndOpenNeedsAssistantGateAndCurrentScope() = runTest {
        val api = Api()
        var current: MemoryBookNarrativeScope? = reader()
        val helper = MemoryBookNarrativeDictationStore(api, backgroundScope, { current })
        assertNull(helper.state.value)
        assertEquals(0, api.capabilityRequests)
        assertEquals(0, api.transcriptions)

        api.enabled = false
        assertNull(helper.open())
        assertEquals(0, api.capabilityRequests)
        api.enabled = true
        current = null
        assertNull(helper.open())
        assertEquals(0, api.capabilityRequests)
        current = reader()
        val store = helper.open()
        assertNotNull(store)
        assertSame(store, helper.state.value)
        assertTrue(helper.hasUnfinishedInput)
        runCurrent()
        assertEquals(1, api.capabilityRequests)
        assertEquals(0, api.transcriptions)
        assertFalse(helper.hasUnfinishedInput)
    }

    @Test fun rejectedTranscriptRemainsAndAcceptedTranscriptIsConsumed() = runTest {
        val api = Api().apply { transcriptText = "  Read these memoir instructions  " }
        val helper = MemoryBookNarrativeDictationStore(api, backgroundScope, { reader() })
        val store = helper.open()!!
        runCurrent()
        assertEquals(5, store.beginRecording())
        store.stopRecording(wav(1))
        runCurrent()

        var inserted: String? = null
        assertFalse(helper.insertTranscript { inserted = it; false })
        assertEquals("  Read these memoir instructions  ", inserted)
        assertEquals(inserted, store.state.value.transcript)
        assertTrue(helper.hasUnfinishedInput)
        assertTrue(helper.insertTranscript { inserted = it; true })
        assertEquals("  Read these memoir instructions  ", inserted)
        assertNull(store.state.value.transcript)
        assertFalse(helper.hasUnfinishedInput)
        assertEquals(1, api.transcriptions)
        assertTrue(api.audioBuffers.single().all { it == 0.toByte() })
    }

    @Test fun changedScopeDuringCapabilitiesCancelsAndClearsOldStore() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        api.capabilityGate = gate
        api.nonCancellableCapabilities = true
        var current = reader()
        var denied = 0
        val helper = MemoryBookNarrativeDictationStore(api, backgroundScope, { current }, { denied++ })
        val old = helper.open()!!
        runCurrent()
        assertTrue(helper.hasUnfinishedInput)
        current = reader(revision = 5)
        gate.complete(Unit)
        runCurrent()
        assertNull(helper.state.value)
        assertEquals(MemoryDictationState(), old.state.value)
        assertEquals(0, denied)
        assertFalse(helper.hasUnfinishedInput)
        assertNotNull(helper.open())
        runCurrent()
        assertEquals(2, api.capabilityRequests)
    }

    @Test fun changedScopeDuringTranscriptionDiscardsLateTranscriptAndWipesAudio() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        api.transcriptionGate = gate
        api.nonCancellableTranscription = true
        var current = reader()
        val helper = MemoryBookNarrativeDictationStore(api, backgroundScope, { current })
        val store = helper.open()!!
        runCurrent()
        store.beginRecording()
        store.stopRecording(wav(1))
        runCurrent()
        assertTrue(store.state.value.transcribing)
        assertTrue(helper.hasUnfinishedInput)
        current = reader(scopeId = 10)
        gate.complete(Unit)
        runCurrent()
        assertNull(helper.state.value)
        assertNull(store.state.value.transcript)
        assertTrue(api.audioBuffers.single().all { it == 0.toByte() })
        assertFalse(helper.hasUnfinishedInput)
    }

    @Test fun scopeChangedByAcceptCallbackDoesNotConsumeOrClearNewStore() = runTest {
        val api = Api().apply { transcriptText = "Keep this transcript" }
        var current = reader()
        val helper = MemoryBookNarrativeDictationStore(api, backgroundScope, { current })
        val old = helper.open()!!
        runCurrent()
        old.beginRecording()
        old.stopRecording(wav(1))
        runCurrent()

        var accepted: String? = null
        assertFalse(helper.insertTranscript { value ->
            accepted = value
            current = reader(revision = 5)
            assertNotNull(helper.open())
            true
        })
        val newStore = helper.state.value
        assertNotNull(newStore)
        assertNotSame(old, newStore)
        assertEquals("Keep this transcript", accepted)
        assertEquals(MemoryDictationState(), old.state.value)
        assertTrue(newStore!!.state.value.loading)
        runCurrent()
        assertSame(newStore, helper.state.value)
    }

    @Test fun oldAccountDenialCannotRevokeNewBindingAndTokenRotationDoesNotReuseStore() = runTest {
        val api = Api()
        val firstGate = CompletableDeferred<Unit>()
        api.capabilityGate = firstGate
        api.nonCancellableCapabilities = true
        api.capabilityFailureAfterGate = ApiFailure(FailureKind.HTTP, 403)
        var current = reader()
        var denied = 0
        val helper = MemoryBookNarrativeDictationStore(api, backgroundScope, { current }, { denied++ })
        val old = helper.open()!!
        runCurrent()

        val rotated = bearer("R")
        current = reader(account = "other-account", token = rotated)
        val fresh = helper.open()!!
        assertNotSame(old, fresh)
        firstGate.complete(Unit)
        runCurrent()
        assertSame(fresh, helper.state.value)
        assertEquals(0, denied)
        assertEquals(2, api.capabilityRequests)
    }

    @Test fun currentAccountDenialClosesOnlyItsStoreAndNotifiesOwner() = runTest {
        val api = Api().apply { immediateCapabilityFailure = ApiFailure(FailureKind.HTTP, 401) }
        var denied = 0
        val helper = MemoryBookNarrativeDictationStore(api, backgroundScope, { reader() }, { denied++ })
        val store = helper.open()!!
        runCurrent()
        assertNull(helper.state.value)
        assertEquals(MemoryDictationState(), store.state.value)
        assertEquals(1, denied)
        assertFalse(helper.hasUnfinishedInput)
    }

    private class Api : PhotoHouseApi {
        var enabled = true
        override val assistantEnabled get() = enabled
        var capabilityRequests = 0
        var transcriptions = 0
        var transcriptText = "memoir instructions"
        var capabilityGate: CompletableDeferred<Unit>? = null
        var transcriptionGate: CompletableDeferred<Unit>? = null
        var nonCancellableCapabilities = false
        var nonCancellableTranscription = false
        var capabilityFailureAfterGate: ApiFailure? = null
        var immediateCapabilityFailure: ApiFailure? = null
        val audioBuffers = mutableListOf<ByteArray>()

        override suspend fun assistantCapabilities(token: Bearer, library: String): AssistantCapabilities {
            val requestNumber = ++capabilityRequests
            val gate = capabilityGate?.takeIf { requestNumber == 1 }
            gate?.let {
                if (nonCancellableCapabilities) withContext(NonCancellable) { it.await() } else it.await()
                if (requestNumber == 1) capabilityGate = null
                if (requestNumber == 1) capabilityFailureAfterGate?.let { failure ->
                    capabilityFailureAfterGate = null
                    throw failure
                }
            }
            immediateCapabilityFailure?.let { failure ->
                immediateCapabilityFailure = null
                throw failure
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
        override suspend fun session(token: Bearer) = Session("account", "+12025550123", emptyList())
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 0, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail = error("unused")
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")
    }

    private fun wav(seconds: Int): ByteArray {
        val pcmSize = 32_000 * seconds
        return ByteArray(44 + pcmSize).also { out ->
            fun tag(at: Int, text: String) = text.toByteArray(Charsets.US_ASCII).copyInto(out, at)
            fun u16(at: Int, value: Int) { out[at] = value.toByte(); out[at + 1] = (value shr 8).toByte() }
            fun u32(at: Int, value: Int) { repeat(4) { out[at + it] = (value shr (it * 8)).toByte() } }
            tag(0, "RIFF"); u32(4, out.size - 8); tag(8, "WAVE"); tag(12, "fmt ")
            u32(16, 16); u16(20, 1); u16(22, 1); u32(24, 16_000); u32(28, 32_000)
            u16(32, 2); u16(34, 16); tag(36, "data"); u32(40, pcmSize)
        }
    }

    companion object {
        private fun bearer(prefix: String = "T"): Bearer = Bearer.from(SessionToken(86400, prefix.repeat(43), "Bearer"))
    }
}
