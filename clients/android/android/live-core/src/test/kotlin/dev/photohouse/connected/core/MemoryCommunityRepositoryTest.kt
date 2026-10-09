package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.cancel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class MemoryCommunityRepositoryTest {
    private val story = "11111111-1111-1111-1111-111111111111"
    private val contribution = "33333333-3333-3333-3333-333333333333"
    private val account = "22222222-2222-2222-2222-222222222222"
    private val receipt = """{"version":1,"id":"$contribution","story_id":"$story","author_id":"$account","kind":"text","language":"en","byline":"Member","sha256":"${"a".repeat(64)}","duration_ms":null,"chapter_id":null,"base_story_revision":"1","state":"pending","created_at":1720000000,"text":"Original wording","processing_consent":false,"can_review":false,"can_delete":false}"""
    private val capabilities = """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":true,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}"""
    private val jobJson = """{"version":1,"id":"55555555-5555-5555-5555-555555555555","kind":"chat","state":"queued","created_at":1720000000,"updated_at":1720000000,"expires_at":1721000000,"error_code":null,"result":null,"needs_review":true,"base_revision":"1"}"""

    private inner open class FakeApi : MemoryCommunityApi {
        var caps = """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":true,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}"""
        var createCalls = mutableListOf<String>()
        var textFailure: ApiFailure? = null
        var afterText: (() -> Unit)? = null
        var audioBytes: ByteArray? = null
        var lastResponse: ByteArray? = null
        var textReceipt = receipt
        override suspend fun capabilities(token: Bearer, library: String) = caps.toByteArray().also { lastResponse = it }
        override suspend fun createTextContribution(token: Bearer, library: String, storyId: String, json: String): ByteArray {
            createCalls += json
            textFailure?.let { textFailure = null; throw it }
            afterText?.invoke()
            return textReceipt.toByteArray().also { lastResponse = it }
        }
        override suspend fun createAudioContribution(token: Bearer, library: String, storyId: String,
                                                      metadataBase64: String, wav: ByteArray): ByteArray {
            audioBytes = wav
            val digest = java.security.MessageDigest.getInstance("SHA-256").digest(wav).joinToString("") { "%02x".format(it) }
            return audioReceipt.replace("${"a".repeat(64)}", digest).toByteArray().also { lastResponse = it }
        }
    }

    private val receiptJson get() = receipt
    private val audioReceipt get() = receipt.replace("\"kind\":\"text\"", "\"kind\":\"audio\"")
        .replace("\"duration_ms\":null", "\"duration_ms\":500")
        .replace("\"processing_consent\":false", "\"processing_consent\":true")
        .replace("\"text\":\"Original wording\"", "\"text\":null")

    private fun token() = Bearer.from(SessionToken(86400, "a".repeat(43), "Bearer"))
    private fun wav(): ByteArray {
        val data = 8000 * 2
        val bytes = ByteArray(44 + data)
        val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        b.put("RIFF".toByteArray()); b.putInt(bytes.size - 8); b.put("WAVEfmt ".toByteArray())
        b.putInt(16); b.putShort(1); b.putShort(1); b.putInt(16000); b.putInt(32000)
        b.putShort(2); b.putShort(16); b.put("data".toByteArray()); b.putInt(data)
        return bytes
    }

    @Test fun retriesReuseExactMutationAndBody() = runBlocking {
        val api = FakeApi().apply { textFailure = ApiFailure(FailureKind.OFFLINE) }
        val binding = MemoryCommunityBinding(token(), "family-a", 7)
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        assertTrue("capability response bytes must be wiped", api.lastResponse!!.all { it == 0.toByte() })
        val request = MemoryContributionRequest("text", "Original wording", "en", "Member", false,
            null, 1, "55555555-5555-5555-5555-555555555555")
        try { store.submitText(story, request); fail("expected offline") }
        catch (e: ApiFailure) { assertEquals(FailureKind.OFFLINE, e.kind) }
        assertEquals(contribution, store.submitText(story, request).contribution.id)
        assertTrue("receipt response bytes must be wiped", api.lastResponse!!.all { it == 0.toByte() })
        assertEquals(2, api.createCalls.size)
        assertEquals(api.createCalls[0], api.createCalls[1])
        assertTrue(api.createCalls[0].contains(request.mutationId))
    }

    @Test fun disabledContributionCapabilityPreventsAnySubmit() = runBlocking {
        val api = FakeApi().apply {
            caps = capabilities.replace("\"contributions_enabled\":true", "\"contributions_enabled\":false")
        }
        val binding = MemoryCommunityBinding(token(), "family-a", 2)
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        try {
            store.submitText(story, MemoryContributionRequest("text", "Original wording", "en", "Member", false, null, 1))
            fail("disabled contribution unexpectedly submitted")
        } catch (e: ApiFailure) { assertEquals(503, e.status) }
        assertTrue(api.createCalls.isEmpty())
    }

    @Test fun scopeChangeDropsLateResponseAndDenialCallsOnlyCurrentSession() = runBlocking {
        val api = FakeApi()
        var binding = MemoryCommunityBinding(token(), "family-a", 3)
        var denied = 0
        val store = MemoryCommunityRepository(api, { binding }, { denied++ })
        store.loadCapabilities()
        api.afterText = { binding = binding.copy(generation = 4) }
        try {
            store.submitText(story, MemoryContributionRequest("text", "Original wording", "en", "Member", false, null, 1))
            fail("stale response escaped")
        } catch (_: CancellationException) { }
        assertEquals(0, denied)

        val deniedApi = object : FakeApi() {
            override suspend fun createTextContribution(token: Bearer, library: String, storyId: String, json: String): ByteArray {
                throw ApiFailure(FailureKind.HTTP, 403)
            }
        }
        binding = MemoryCommunityBinding(token(), "family-a", 5)
        val guarded = MemoryCommunityRepository(deniedApi, { binding }, { denied++ })
        guarded.loadCapabilities()
        try {
            guarded.submitText(story, MemoryContributionRequest("text", "Original wording", "en", "Member", false, null, 1))
            fail("expected denial")
        } catch (e: ApiFailure) { assertEquals(403, e.status) }
        assertEquals(1, denied)
    }

    @Test fun turnDenialCallbackIsFencedByTheOriginatingReaderRequest() = runBlocking {
        val id = "44444444-4444-4444-4444-444444444444"
        val binding = MemoryCommunityBinding(token(), "family-a", 8)
        val started = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        var denied = 0
        val api = object : FakeApi() {
            override suspend fun conversationTurnsWithReplyContext(
                token: Bearer, library: String, conversationId: String, page: Int,
            ): ByteArray {
                started.complete(Unit)
                release.await()
                throw ApiFailure(FailureKind.HTTP, 403)
            }
        }
        val store = MemoryCommunityRepository(api, { binding }, { denied++ })
        store.loadCapabilities()
        var requestCurrent = true
        val oldRequest = launch {
            try {
                store.turns(id, replyContext = true, currentRequest = { requestCurrent })
                fail("expected stale request cancellation")
            } catch (_: CancellationException) { }
        }
        started.await()
        requestCurrent = false
        release.complete(Unit)
        oldRequest.join()
        assertEquals("stale reader denial must not invalidate its replacement", 0, denied)

        val currentApi = object : FakeApi() {
            override suspend fun conversationTurnsWithReplyContext(
                token: Bearer, library: String, conversationId: String, page: Int,
            ): ByteArray = throw ApiFailure(FailureKind.HTTP, 401)
        }
        val currentStore = MemoryCommunityRepository(currentApi, { binding }, { denied++ })
        currentStore.loadCapabilities()
        try {
            currentStore.turns(id, replyContext = true, currentRequest = { true })
            fail("expected current reader denial")
        } catch (e: ApiFailure) { assertEquals(401, e.status) }
        assertEquals("current reader owns auth denial handling", 0, denied)
    }

    @Test fun preview400FallsBackOnceToLegacyOnlyWhileReaderAndBindingRemainCurrent() = runBlocking {
        val id = "66666666-6666-6666-6666-666666666666"
        val legacyBody = """{"version":1,"items":[{"id":"$id","created_at":1720000000,"expires_at":1721000000}]}"""
        val binding = MemoryCommunityBinding(token(), "family-a", 12)
        var previewCalls = 0
        var legacyCalls = 0
        val api = object : FakeApi() {
            override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                previewCalls++
                throw ApiFailure(FailureKind.HTTP, 400)
            }
            override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                legacyCalls++
                return legacyBody.toByteArray()
            }
        }
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        var current = true
        val result = store.conversations("story", story, withPreview = true, currentRequest = { current })
        assertEquals(id, result.items.single().id)
        assertNull(result.items.single().firstMessagePreview)
        assertEquals(1, previewCalls)
        assertEquals(1, legacyCalls)
    }

    @Test fun staleReaderDoesNotStartInitialConversationListRequest() = runBlocking {
        val binding = MemoryCommunityBinding(token(), "family-a", 12)
        var previewCalls = 0
        var legacyCalls = 0
        val api = object : FakeApi() {
            override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                previewCalls++
                return """{"version":1,"items":[]}""".toByteArray()
            }
            override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                legacyCalls++
                return """{"version":1,"items":[]}""".toByteArray()
            }
        }
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        val stale = { false }
        for (withPreview in listOf(false, true)) {
            try {
                store.conversations("story", story, withPreview = withPreview, currentRequest = stale)
                fail("stale reader started a conversation list request")
            } catch (_: CancellationException) { }
        }
        assertEquals(0, previewCalls)
        assertEquals(0, legacyCalls)
    }

    @Test fun readerBecomingStaleDuringPreview400DoesNotStartLegacyFallback() = runBlocking {
        val binding = MemoryCommunityBinding(token(), "family-a", 12)
        var current = true
        var previewCalls = 0
        var legacyCalls = 0
        val api = object : FakeApi() {
            override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                previewCalls++
                current = false
                throw ApiFailure(FailureKind.HTTP, 400)
            }
            override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                legacyCalls++
                return """{"version":1,"items":[]}""".toByteArray()
            }
        }
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        try {
            store.conversations("story", story, withPreview = true, currentRequest = { current })
            fail("stale reader received a legacy fallback")
        } catch (_: CancellationException) { }
        assertEquals(1, previewCalls)
        assertEquals(0, legacyCalls)
    }

    @Test fun preview400DoesNotFallbackWithoutCurrentPredicateOrWhenBindingChanges() = runBlocking {
        val binding = MemoryCommunityBinding(token(), "family-a", 13)
        var previewCalls = 0
        var legacyCalls = 0
        lateinit var liveBinding: MemoryCommunityBinding
        val api = object : FakeApi() {
            override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                previewCalls++
                if (previewCalls == 2) liveBinding = liveBinding.copy(generation = liveBinding.generation + 1)
                throw ApiFailure(FailureKind.HTTP, 400)
            }
            override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                legacyCalls++
                return """{"version":1,"items":[]}""".toByteArray()
            }
        }
        liveBinding = binding
        val store = MemoryCommunityRepository(api, { liveBinding })
        store.loadCapabilities()
        try {
            store.conversations("story", story, withPreview = true)
            fail("fallback without a reader predicate was allowed")
        } catch (e: ApiFailure) { assertEquals(400, e.status) }
        assertEquals(0, legacyCalls)

        try {
            store.conversations("story", story, withPreview = true, currentRequest = { true })
            fail("fallback crossed a binding generation change")
        } catch (_: CancellationException) { }
        assertEquals(0, legacyCalls)
        assertEquals(2, previewCalls)
    }

    @Test fun previewFallbackIsOnlyForHttp400() = runBlocking {
        val binding = MemoryCommunityBinding(token(), "family-a", 14)
        var legacyCalls = 0
        val api = object : FakeApi() {
            override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String): ByteArray =
                throw ApiFailure(FailureKind.HTTP, 503)
            override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                legacyCalls++
                return """{"version":1,"items":[]}""".toByteArray()
            }
        }
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        try {
            store.conversations("story", story, withPreview = true, currentRequest = { true })
            fail("non-400 preview failure was ignored")
        } catch (e: ApiFailure) { assertEquals(503, e.status) }
        assertEquals(0, legacyCalls)
    }

    @Test fun cancelledPreviewRequestDoesNotStartLegacyFallback() = runBlocking {
        val binding = MemoryCommunityBinding(token(), "family-a", 15)
        var legacyCalls = 0
        val api = object : FakeApi() {
            override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                currentCoroutineContext().cancel(CancellationException("reader cancelled"))
                throw ApiFailure(FailureKind.HTTP, 400)
            }
            override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
                legacyCalls++
                return """{"version":1,"items":[]}""".toByteArray()
            }
        }
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        val reader = launch {
            try {
                store.conversations("story", story, withPreview = true, currentRequest = { true })
                fail("cancelled reader unexpectedly returned")
            } catch (_: CancellationException) { }
        }
        reader.join()
        assertEquals(0, legacyCalls)
    }

    @Test fun audioBuffersAreWipedAfterSubmissionAndReceiptIsValidated() = runBlocking {
        val api = FakeApi()
        val binding = MemoryCommunityBinding(token(), "family-a", 1)
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        val wav = wav()
        store.submitAudio(story, MemoryContributionRequest("audio", "", "en", "Member", true, null, 1), wav)
        assertTrue(wav.all { it == 0.toByte() })
        assertTrue(api.audioBytes!!.all { it == 0.toByte() })
    }

    @Test fun originalTextReceiptMustEchoTheSubmittedContribution() = runBlocking {
        val api = FakeApi().apply { textReceipt = receipt.replace("Original wording", "different returned words") }
        val binding = MemoryCommunityBinding(token(), "family-a", 9)
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        try {
            store.submitText(story, MemoryContributionRequest("text", "Original wording", "en", "Member", false,
                null, 1, "55555555-5555-5555-5555-555555555555"))
            fail("mismatched receipt was accepted")
        } catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
        assertTrue(api.lastResponse!!.all { it == 0.toByte() })
    }

    @Test fun editorialRequestChoiceReachesTransportAndLegacyOverloadsRemainOptIn() = runBlocking {
        val binding = MemoryCommunityBinding(token(), "family-a", 13)
        var legacyTurnCalls = 0
        var legacyNarrativeCalls = 0
        val legacy = object : FakeApi() {
            override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String): ByteArray {
                legacyTurnCalls++
                return jobJson.toByteArray()
            }
            override suspend fun queueNarrative(token: Bearer, library: String, json: String): ByteArray {
                legacyNarrativeCalls++
                return jobJson.replace("\"kind\":\"chat\"", "\"kind\":\"narrative\"").toByteArray()
            }
        }
        val legacyStore = MemoryCommunityRepository(legacy, { binding })
        legacyStore.loadCapabilities()
        legacyStore.sendTurn("44444444-4444-4444-4444-444444444444", MemoryTurnRequest(1, "Question"))
        legacyStore.queueNarrative(MemoryNarrativeRequest("story", story, 1, "Draft"))
        assertEquals(1, legacyTurnCalls)
        assertEquals(1, legacyNarrativeCalls)
        try {
            legacyStore.sendTurn("44444444-4444-4444-4444-444444444444", MemoryTurnRequest(1, "Question", editorialContext = true))
            fail("legacy adapter silently accepted editorial context")
        } catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
        try {
            legacyStore.queueNarrative(MemoryNarrativeRequest("book", "66666666-6666-6666-6666-666666666666", 1,
                "Draft", editorialContext = true))
            fail("legacy adapter silently accepted editorial context")
        } catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
        assertEquals(1, legacyTurnCalls)
        assertEquals(1, legacyNarrativeCalls)

        val choices = mutableListOf<Boolean>()
        val modern = object : FakeApi() {
            override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String,
                                          editorialContext: Boolean): ByteArray {
                choices += editorialContext
                return jobJson.toByteArray()
            }
            override suspend fun queueNarrative(token: Bearer, library: String, json: String,
                                                editorialContext: Boolean): ByteArray {
                choices += editorialContext
                return jobJson.replace("\"kind\":\"chat\"", "\"kind\":\"narrative\"").toByteArray()
            }
        }
        val modernStore = MemoryCommunityRepository(modern, { binding })
        modernStore.loadCapabilities()
        modernStore.sendTurn("44444444-4444-4444-4444-444444444444", MemoryTurnRequest(1, "Question", editorialContext = false))
        modernStore.sendTurn("44444444-4444-4444-4444-444444444444", MemoryTurnRequest(1, "Question", editorialContext = true))
        modernStore.queueNarrative(MemoryNarrativeRequest("story", story, 1, "Draft", editorialContext = false))
        modernStore.queueNarrative(MemoryNarrativeRequest("book", "66666666-6666-6666-6666-666666666666", 1, "Draft", editorialContext = true))
        try {
            modernStore.queueNarrative(MemoryNarrativeRequest("story", story, 1, "Draft", editorialContext = true))
            fail("story narrative unexpectedly accepted memoir context")
        } catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
        assertEquals(listOf(false, true, false, true), choices)
    }

    @Test fun bookPlanIsReadOnlyExplicitlyProfiledAndRequestScoped() = runBlocking {
        val bookId = "66666666-6666-6666-6666-666666666666"
        val plan = """{"version":1,"target_type":"book","target_id":"$bookId","revision":"2","can_edit":true,"kind":"saved_structure_plan","generated":false,"queued":false,"needs_review":true,"story_count":1,"chapter_count":1,"item_count":1,"distinct_item_count":1,"limits":{"chapters":24,"sources":96,"context_bytes":65536},"whole":{"state":"within_limits","can_draft":true,"source_count":1,"source_kinds":{"family":1},"context_bytes":1024},"sections":[{"position":1,"id":"11111111-1111-1111-1111-111111111111","revision":"1","title":"Saved chapter","item_count":1,"can_edit":true,"chapters":[{"id":"chapter-1","title":"Opening","item_count":1}],"state":"within_limits","can_draft":true,"source_count":1,"source_kinds":{"family":1}}],"context_profile":"memoir_editorial_v1"}"""
        var requests = 0
        var editorial = false
        var response: ByteArray? = null
        val binding = MemoryCommunityBinding(token(), "family-a", 14)
        val api = object : FakeApi() {
            override suspend fun bookPlan(token: Bearer, library: String, id: String,
                                          editorialContext: Boolean): ByteArray {
                requests++
                editorial = editorialContext
                assertEquals("family-a", library)
                assertEquals(bookId, id)
                return plan.toByteArray().also { response = it }
            }
        }
        val store = MemoryCommunityRepository(api, { binding })
        store.loadCapabilities()
        var current = false
        try {
            store.bookPlan(bookId, 2, editorialContext = true, currentRequest = { current })
            fail("stale plan request started")
        } catch (_: CancellationException) { }
        assertEquals(0, requests)
        current = true
        val result = store.bookPlan(bookId, 2, editorialContext = true, currentRequest = { current })
        assertEquals(bookId, result.targetId)
        assertEquals(2L, result.revision)
        assertEquals("memoir_editorial_v1", result.contextProfile)
        assertEquals("within_limits", result.whole.state)
        assertEquals(1024, result.whole.contextBytes)
        assertEquals(1, requests)
        assertTrue(editorial)
        assertTrue("plan response bytes must be wiped", response!!.all { it == 0.toByte() })
    }
}
