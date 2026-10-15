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
class StoryChapterDictationStoreTest {
    private val caps = AssistantCapabilities(true, true, true, false, 5)
    private val token = bearer()
    private val selection = "a".repeat(64)
    private val savedId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    private fun editor(
        account: String = "account",
        credential: Bearer = token,
        library: String = "family-a",
        generation: Long = 3,
        scopeId: Long = 9,
        selectionRevision: String = selection,
        savedStoryId: String? = null,
        savedStoryRevision: Long? = null,
        chapterId: String = "chapter-1",
        chapterAssetIds: List<String> = listOf("101", "102"),
        editable: Boolean = true,
    ) = StoryChapterDictationScope(account, credential, library, generation, scopeId,
        selectionRevision, savedStoryId, savedStoryRevision, chapterId, chapterAssetIds, editable)

    @Test fun constructionIsInertAndOpenRequiresAnEditableValidScope() = runTest {
        val api = Api()
        var current: StoryChapterDictationScope? = editor()
        val helper = StoryChapterDictationStore(api, backgroundScope, { current })
        assertNull(helper.state.value)
        assertEquals(0, api.capabilityRequests)
        assertEquals(0, api.transcriptions)

        api.enabled = false
        assertNull(helper.open())
        assertEquals(0, api.capabilityRequests)
        api.enabled = true
        current = editor(editable = false)
        assertNull(helper.open())
        current = editor(savedStoryId = savedId)
        assertNull(helper.open()) // Saved identity and revision must be supplied together.
        current = editor(savedStoryId = "not-a-uuid", savedStoryRevision = 2)
        assertNull(helper.open())
        current = editor(savedStoryId = savedId, savedStoryRevision = 0)
        assertNull(helper.open())
        current = editor(selectionRevision = "not-a-hash")
        assertNull(helper.open())
        current = editor(account = " ".repeat(257))
        assertNull(helper.open())
        current = editor(library = ".")
        assertNull(helper.open())
        current = editor(generation = -1)
        assertNull(helper.open())
        current = editor(scopeId = -1)
        assertNull(helper.open())
        current = editor(chapterId = "chapter-7")
        assertNull(helper.open())
        current = editor(chapterAssetIds = listOf("101", "101"))
        assertNull(helper.open())
        current = editor(chapterAssetIds = listOf("0"))
        assertNull(helper.open())
        current = editor(chapterAssetIds = listOf("101", "102", "103", "104", "105"))
        assertNull(helper.open())
        current = editor(chapterAssetIds = listOf("9223372036854775808"))
        assertNull(helper.open())
        assertEquals(0, api.capabilityRequests)

        current = editor(savedStoryId = savedId, savedStoryRevision = 4)
        val store = helper.open()
        assertNotNull(store)
        assertSame(store, helper.state.value)
        assertTrue(helper.hasUnfinishedInput)
        runCurrent()
        assertEquals(1, api.capabilityRequests)
        assertFalse(helper.hasUnfinishedInput)
    }

    @Test fun transcriptIsReviewedAndRejectedInsertRetainsItWhileTypedTextCanChange() = runTest {
        val api = Api().apply { transcriptText = "Dictated chapter words" }
        val helper = StoryChapterDictationStore(api, backgroundScope, { editor() })
        val store = helper.open()!!
        runCurrent()
        assertEquals(5, store.beginRecording())
        store.stopRecording(wav(1))
        runCurrent()
        assertEquals("Dictated chapter words", store.state.value.transcript)
        assertTrue(helper.hasUnfinishedInput)

        var typed = "Words typed before recording"
        assertFalse(helper.insertTranscript { transcript ->
            typed += "\n\n$transcript"
            false // Caller rejects an over-limit append; the whole transcript remains reviewable.
        })
        assertEquals("Words typed before recording\n\nDictated chapter words", typed)
        assertEquals("Dictated chapter words", store.state.value.transcript)
        assertTrue(helper.hasUnfinishedInput)

        assertTrue(helper.insertTranscript { transcript ->
            // The stable binding deliberately excludes narration text, so current typed edits survive.
            typed = "Words typed while reviewing\n\n$transcript"
            true
        })
        assertEquals("Words typed while reviewing\n\nDictated chapter words", typed)
        assertNull(store.state.value.transcript)
        assertFalse(helper.hasUnfinishedInput)
        assertEquals(1, api.transcriptions)
        assertTrue(api.audioBuffers.single().all { it == 0.toByte() })
    }

    @Test fun callerOwnedAssetListIsSnapshottedAndAssetChangesInvalidateSession() = runTest {
        val api = Api()
        val mutableAssets = mutableListOf("101", "102")
        var current = editor(chapterAssetIds = mutableAssets)
        val helper = StoryChapterDictationStore(api, backgroundScope, { current })
        val old = helper.open()!!
        runCurrent()
        mutableAssets[0] = "103"
        assertNotSame(old, helper.open())
        assertNotSame(old, helper.state.value)
        assertEquals(MemoryDictationState(), old.state.value)

        runCurrent()
        assertEquals(2, api.capabilityRequests)
    }

    @Test fun changedChapterOrRevisionCancelsLateCapabilityResponse() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        api.capabilityGate = gate
        api.nonCancellableCapabilities = true
        var current = editor(savedStoryId = savedId, savedStoryRevision = 4)
        var denied = 0
        val helper = StoryChapterDictationStore(api, backgroundScope, { current }, { denied++ })
        val old = helper.open()!!
        runCurrent()
        current = editor(savedStoryId = savedId, savedStoryRevision = 5, chapterId = "chapter-2")
        gate.complete(Unit)
        runCurrent()
        assertNull(helper.state.value)
        assertEquals(MemoryDictationState(), old.state.value)
        assertEquals(0, denied)
        assertNotNull(helper.open())
        runCurrent()
        assertEquals(2, api.capabilityRequests)
    }

    @Test fun changedAccountOrLibraryDiscardsLateAsrAndWipesAudio() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        api.transcriptionGate = gate
        api.nonCancellableTranscription = true
        var current = editor()
        val helper = StoryChapterDictationStore(api, backgroundScope, { current })
        val old = helper.open()!!
        runCurrent()
        assertEquals(5, old.beginRecording())
        old.stopRecording(wav(1))
        runCurrent()
        assertTrue(old.state.value.transcribing)

        current = editor(account = "another-account", credential = bearer("R"), library = "family-b")
        val fresh = helper.open()!!
        assertNotSame(old, fresh)
        gate.complete(Unit)
        runCurrent()
        assertSame(fresh, helper.state.value)
        assertNull(old.state.value.transcript)
        assertEquals(MemoryDictationState(), old.state.value)
        assertTrue(api.audioBuffers.single().all { it == 0.toByte() })
    }

    @Test fun clearCancelsLateAsrAndDropsTranscript() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        api.transcriptionGate = gate
        api.nonCancellableTranscription = true
        val helper = StoryChapterDictationStore(api, backgroundScope, { editor() })
        val store = helper.open()!!
        runCurrent()
        store.beginRecording()
        store.stopRecording(wav(1))
        runCurrent()
        assertTrue(store.state.value.transcribing)
        helper.clear()
        gate.complete(Unit)
        runCurrent()
        assertNull(helper.state.value)
        assertEquals(MemoryDictationState(), store.state.value)
        assertFalse(helper.hasUnfinishedInput)
    }

    @Test fun currentDenialClearsAndNotifiesButStaleDenialCannotClearNewSession() = runTest {
        val api = Api()
        val gate = CompletableDeferred<Unit>()
        api.capabilityGate = gate
        api.nonCancellableCapabilities = true
        api.capabilityFailureAfterGate = ApiFailure(FailureKind.HTTP, 403)
        var current = editor()
        var denied = 0
        val helper = StoryChapterDictationStore(api, backgroundScope, { current }, { denied++ })
        val old = helper.open()!!
        runCurrent()
        current = editor(chapterId = "chapter-2")
        val fresh = helper.open()!!
        assertNotSame(old, fresh)
        gate.complete(Unit)
        runCurrent()
        assertSame(fresh, helper.state.value)
        assertEquals(MemoryDictationState(), old.state.value)
        assertEquals(0, denied)

        api.immediateCapabilityFailure = ApiFailure(FailureKind.HTTP, 401)
        current = editor(chapterId = "chapter-3")
        val deniedStore = helper.open()!!
        assertNotSame(fresh, deniedStore)
        runCurrent()
        assertNull(helper.state.value)
        assertEquals(MemoryDictationState(), deniedStore.state.value)
        assertEquals(1, denied)
    }

    private class Api : PhotoHouseApi {
        var enabled = true
        override val assistantEnabled get() = enabled
        var capabilityRequests = 0
        var transcriptions = 0
        var transcriptText = "Chapter recollection"
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

        override suspend fun assistantTranscribe(
            token: Bearer, library: String, wav: ByteArray, requestId: String,
        ): AssistantTranscript {
            transcriptions++
            audioBuffers += wav
            transcriptionGate?.let { gate ->
                if (nonCancellableTranscription) withContext(NonCancellable) { gate.await() } else gate.await()
                transcriptionGate = null
            }
            return AssistantTranscript(transcriptText, "en",
                AssistantRequestReceipt(requestId, "enabled", "succeeded"))
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

    private fun bearer(prefix: String = "T"): Bearer =
        Bearer.from(SessionToken(86400, prefix.repeat(43), "Bearer"))
}
