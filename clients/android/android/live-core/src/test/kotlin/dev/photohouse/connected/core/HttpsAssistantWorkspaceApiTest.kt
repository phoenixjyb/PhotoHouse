package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.*
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class HttpsAssistantWorkspaceApiTest {
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private val thread = "22222222-2222-4222-8222-222222222222"
    private val request = "11111111-1111-4111-8111-111111111111"
    private val speechRequest = "55555555-5555-4555-8555-555555555555"

    private class Fixture : AutoCloseable {
        private val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        private val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        val origin = TrustedOrigin.parse("https://localhost:${server.port}")
        fun api(enabled: Boolean = true) = HttpsAssistantWorkspaceApi(origin, enabled, client)
        override fun close() {
            server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll()
        }
    }

    private fun response(body: String, status: Int = 200) = MockResponse().setResponseCode(status)
        .setHeader("Content-Type", "application/json; charset=utf-8")
        .setHeader("Cache-Control", "private, no-store").setBody(body)

    private fun wav(seconds: Int = 1): ByteArray {
        val rate = 16_000
        val dataBytes = seconds * rate * 2
        return ByteArray(44 + dataBytes).also { bytes ->
            fun ascii(offset: Int, value: String) = value.toByteArray().copyInto(bytes, offset)
            fun u16(offset: Int, value: Int) { bytes[offset] = value.toByte(); bytes[offset + 1] = (value shr 8).toByte() }
            fun u32(offset: Int, value: Int) {
                for (i in 0..3) bytes[offset + i] = (value ushr (i * 8)).toByte()
            }
            ascii(0, "RIFF"); u32(4, bytes.size - 8); ascii(8, "WAVE")
            ascii(12, "fmt "); u32(16, 16); u16(20, 1); u16(22, 1)
            u32(24, rate); u32(28, rate * 2); u16(32, 2); u16(34, 16)
            ascii(36, "data"); u32(40, dataBytes)
        }
    }

    private fun speechResponse(bytes: ByteArray, requestId: String = speechRequest) = MockResponse()
        .setHeader("Content-Type", "audio/wav")
        .setHeader("Cache-Control", "private, no-store")
        .setHeader("X-PhotoHouse-Tracking", "enabled")
        .setHeader("X-PhotoHouse-Request-Id", requestId)
        .setHeader("X-PhotoHouse-Receipt-Status", "succeeded")
        .setBody(okio.Buffer().write(bytes))

    private fun segmentSpeechResponse(bytes: ByteArray, segment: String = "0", count: String = "2",
                                      requestId: String = speechRequest) = speechResponse(bytes, requestId)
        .setHeader("X-PhotoHouse-Playback-Tracking", "enabled")
        .setHeader("X-PhotoHouse-Reading-Segment", segment)
        .setHeader("X-PhotoHouse-Reading-Segment-Count", count)

    private fun result(kind: String = "results", effect: String = "null") =
        """{"version":1,"kind":"$kind","reply":"Found one.","context":{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":{},"visible_ids":["123"],"total":1},"filters":{},"items":[{"id":"123","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/123/thumbnail?library=family-a"}],"total":1,"has_more":false,"effect":$effect}"""

    private fun envelope(status: String, result: String = "null", recovered: Boolean = false, error: String = "null") =
        """{"version":1,"thread_id":"$thread","request_id":"$request","status":"$status","revision":1,"recovered":$recovered,"error":$error,"result":$result}"""

    @Test fun disabledByDefaultAndProtectedReadsAndIdempotentCreateBody() = runBlocking {
        Fixture().use { f ->
            val disabled = f.api(false)
            assertFalse(disabled.assistantWorkspaceEnabled)
            try { disabled.capabilities(token, "family-a"); fail("disabled adapter sent request") }
            catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
            assertEquals(0, f.server.requestCount)

            val api = f.api()
            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":true,"preferences_applied":false,"server_owned_turns":true,"applied_preferences":[]}"""))
            assertTrue(api.capabilities(token, "family-a").available)
            val caps = f.server.takeRequest()
            assertEquals("GET", caps.method); assertEquals("/assistant/workspace/v1/capabilities?library_id=family-a", caps.path); assertProtected(caps)
            assertEquals("3", caps.getHeader("X-PhotoHouse-Search-Version"))

            val summary = """{"thread_id":"$thread","library_id":"family-a","created_at":"2026-10-13T00:00:00Z","updated_at":"2026-10-13T00:00:00Z","expires_at":"2026-11-12T00:00:00Z","revision":0,"exchange_count":0}"""
            f.server.enqueue(response("""{"version":1,"thread":$summary}""", 200))
            assertEquals(thread, api.createThread(token, "family-a", thread).thread.threadId)
            val create = f.server.takeRequest()
            assertEquals("POST", create.method); assertEquals("/assistant/workspace/v1/threads", create.path); assertProtected(create)
            val body = Json.parseToJsonElement(create.body.readUtf8()).jsonObject
            assertEquals(setOf("library_id", "thread_id"), body.keys)
            assertEquals("family-a", body.getValue("library_id").jsonPrimitive.content)
            assertEquals(thread, body.getValue("thread_id").jsonPrimitive.content)
        }
    }

    @Test fun capabilitiesRetriesLegacyOnlyForExplicitUnsupportedSearchVersion() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(response("""{"error":"invalid_request","detail":"Search version is not supported on this endpoint"}""", 400))
            f.server.enqueue(response("""{"error":"invalid_request","detail":"Search version is not supported on this endpoint"}""", 400))
            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":false,"preferences_applied":false,"server_owned_turns":true}"""))
            val value = f.api().capabilities(token, "family-a")
            assertEquals(1, value.searchVersion)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
            assertEquals("2", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
            assertNull(f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
            assertEquals(3, f.server.requestCount)
        }
        Fixture().use { f ->
            f.server.enqueue(response("""{"error":"invalid_request","detail":"Invalid workspace request"}""", 400))
            try {
                f.api().capabilities(token, "family-a")
                fail("generic invalid request was retried")
            } catch (failure: ApiFailure) { assertEquals(400, failure.status) }
            assertEquals(1, f.server.requestCount)
        }
    }

    @Test fun capabilityNegotiationStopsAtSupportedV2AndDoesNotTreatServiceUnavailableAsUnsupported() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(response("""{"error":"invalid_request","detail":"Search version is not supported on this endpoint"}""", 400))
            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":false,"preferences_applied":false,"server_owned_turns":true,"search":{"version":2,"date_basis":"capture","perspective":null}}"""))
            assertEquals(2, f.api().capabilities(token, "family-a").searchVersion)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
            assertEquals("2", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
            assertEquals(2, f.server.requestCount)
        }
        Fixture().use { f ->
            f.server.enqueue(response("{}", 503))
            try { f.api().capabilities(token, "family-a"); fail("503 was downgraded") }
            catch (failure: ApiFailure) { assertEquals(503, failure.status) }
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
            assertEquals(1, f.server.requestCount)
        }
    }

    @Test fun capabilityNegotiationAcceptsOnlyTheExplicitSearchUnsupportedCode() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(response("""{"error":"search_version_unsupported","detail":"Planner is disabled"}""", 400))
            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":false,"preferences_applied":false,"server_owned_turns":true,"search":{"version":2,"date_basis":"capture","perspective":null}}"""))
            assertEquals(2, f.api().capabilities(token, "family-a").searchVersion)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
            assertEquals("2", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
        }
        Fixture().use { f ->
            f.server.enqueue(response("""{"error":"invalid_request","detail":"Search unavailable"}""", 400))
            try { f.api().capabilities(token, "family-a"); fail("generic invalid_request was downgraded") }
            catch (failure: ApiFailure) { assertEquals(400, failure.status) }
            assertEquals(1, f.server.requestCount)
        }
    }

    @Test fun turnPostCarriesOnlyUserInputAndGetRecoversWithoutResending() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            val parent = "33333333-3333-4333-8333-333333333333"
            f.server.enqueue(response(envelope("pending"))
                .setHeader("X-PhotoHouse-Tracking", "enabled")
                .setHeader("X-PhotoHouse-Request-Id", request)
                .setHeader("X-PhotoHouse-Receipt-Status", "received"))
            val submitted = api.submitTurn(token, "family-a", thread, request, 0, "找照片", parent)
            assertEquals(AssistantWorkspaceRequestStatus.PENDING, submitted.status)
            assertEquals(AssistantRequestReceipt(request, "enabled", "received"), submitted.receipt)
            val post = f.server.takeRequest()
            assertEquals("POST", post.method); assertEquals("/assistant/workspace/v1/threads/$thread/turns", post.path); assertProtected(post)
            assertEquals(request, post.getHeader("X-PhotoHouse-Request-Id"))
            assertNull(post.getHeader("X-PhotoHouse-Search-Version"))
            assertEquals(parent, post.getHeader("X-PhotoHouse-Parent-Request-Id"))
            val body = Json.parseToJsonElement(post.body.readUtf8()).jsonObject
            assertEquals(setOf("library_id", "request_id", "expected_revision", "text"), body.keys)
            assertEquals(request, body.getValue("request_id").jsonPrimitive.content)
            assertFalse(body.containsKey("context")); assertFalse(body.containsKey("reply")); assertFalse(body.containsKey("cards"))

            f.server.enqueue(response(envelope("completed", result(), recovered = true)))
            val recovered = api.getTurn(token, "family-a", thread, request)
            assertEquals(AssistantWorkspaceRequestStatus.COMPLETED, recovered.status)
            assertTrue(recovered.recovered); assertNull(recovered.result!!.effect)
            assertEquals(AssistantRequestReceipt(request, "unknown", null), recovered.receipt)
            assertEquals(recovered.receipt, recovered.result!!.receipt)
            val get = f.server.takeRequest()
            assertEquals("GET", get.method)
            assertEquals("/assistant/workspace/v1/threads/$thread/requests/$request?library_id=family-a", get.path)
            assertProtected(get)
            assertNull(get.getHeader("X-PhotoHouse-Search-Version"))
            assertEquals(2, f.server.requestCount)
        }
    }

    @Test fun negotiatedSearchVersionStaysOnTurnRecoveryAndReplySpeechOnly() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            val interpretation = """{"date_basis":"capture","people":[],"tags":[],"locations":[],"perspective":null}"""
            val context = """{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":{},"visible_ids":["123"],"total":1,"search_version":2}"""
            val item = """{"id":"123","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/123/thumbnail?library=family-a","match_reasons":[{"source":"reviewed_person","source_id":"9"}]}"""
            val v2Result = """{"version":2,"kind":"results","reply":"Found one.","context":$context,"filters":{},"items":[$item],"total":1,"has_more":false,"effect":null,"interpretation":$interpretation}"""

            f.server.enqueue(response("""{"error":"invalid_request","detail":"Search version is not supported on this endpoint"}""", 400))
            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":true,"preferences_applied":false,"server_owned_turns":true,"search":{"version":2,"date_basis":"capture","perspective":null}}"""))
            assertEquals(2, api.capabilities(token, "family-a").searchVersion)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
            assertEquals("2", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))

            f.server.enqueue(response(envelope("completed", v2Result, recovered = false)))
            assertEquals(2, api.submitTurn(token, "family-a", thread, request, 0, "找妈妈", null,
                false, null, false, 2).result!!.searchVersion)
            val post = f.server.takeRequest()
            assertEquals("2", post.getHeader("X-PhotoHouse-Search-Version"))

            f.server.enqueue(response(envelope("completed", v2Result, recovered = true)))
            val recovered = api.getTurn(token, "family-a", thread, request, 2)
            assertTrue(recovered.recovered); assertEquals(2, recovered.result!!.searchVersion)
            assertEquals("2", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))

            f.server.enqueue(response("""{"version":1,"locale":null,"reply_length":null,"voice_pace":null,"revision":0}"""))
            api.preferences(token, "family-a")
            assertNull(f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))

            f.server.enqueue(speechResponse(wav()))
            api.speakTurn(token, "family-a", thread, request, 1, speechRequest, 2)
            assertEquals("2", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
        }
    }

    @Test fun v3SearchVersionStaysOnCapabilitiesTurnRecoveryAndReplySpeech() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            val interpretation = """{"date_basis":"capture","people":[],"tags":[],"locations":[],"perspective":null}"""
            val descriptive = """{"version":1,"concepts":[{"surface":"garden picnic","alternatives":["family picnic"]}]}"""
            val filters = """{"descriptive":$descriptive}"""
            val context = """{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":$filters,"visible_ids":["123"],"total":1,"search_version":3}"""
            val item = """{"id":"123","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/123/thumbnail?library=family-a"}"""
            val v3Result = """{"version":3,"kind":"results","reply":"Found one.","context":$context,"filters":$filters,"items":[$item],"total":1,"has_more":false,"effect":null,"interpretation":$interpretation}"""

            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":true,"preferences_applied":false,"server_owned_turns":true,"search":{"version":3,"date_basis":"capture","perspective":null}}"""))
            assertEquals(3, api.capabilities(token, "family-a").searchVersion)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))

            f.server.enqueue(response(envelope("completed", v3Result)))
            val submitted = api.submitTurn(token, "family-a", thread, request, 0, "find a garden picnic", null,
                false, null, false, 3)
            assertEquals(3, submitted.result!!.searchVersion)
            assertEquals("garden picnic", submitted.result!!.filters!!.getValue("descriptive")
                .jsonObject.getValue("concepts").jsonArray[0].jsonObject.getValue("surface").jsonPrimitive.content)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))

            f.server.enqueue(response(envelope("completed", v3Result, recovered = true)))
            val recovered = api.getTurn(token, "family-a", thread, request, 3)
            assertTrue(recovered.recovered)
            assertEquals(3, recovered.result!!.searchVersion)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))

            val v2Context = """{"library_id":"family-a","binding":"${"a".repeat(64)}","fingerprint":"${"b".repeat(64)}","filters":{},"visible_ids":["123"],"total":1,"search_version":2}"""
            val v2Result = """{"version":2,"kind":"results","reply":"Found one.","context":$v2Context,"filters":{},"items":[$item],"total":1,"has_more":false,"effect":null,"interpretation":$interpretation}"""
            f.server.enqueue(response(envelope("completed", v2Result, recovered = true)))
            val oldExchange = api.getTurn(token, "family-a", thread, request, 3)
            assertTrue(oldExchange.recovered)
            assertEquals(2, oldExchange.result!!.searchVersion)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))

            f.server.enqueue(response(envelope("completed", v2Result)))
            val downgraded = runCatching {
                api.submitTurn(token, "family-a", thread, request, 0, "fresh query", null, false, null, false, 3)
            }.exceptionOrNull() as? ApiFailure
            assertEquals(FailureKind.INVALID_RESPONSE, downgraded?.kind)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))

            f.server.enqueue(speechResponse(wav()))
            api.speakTurn(token, "family-a", thread, request, 1, speechRequest, 3)
            assertEquals("3", f.server.takeRequest().getHeader("X-PhotoHouse-Search-Version"))
        }
    }

    @Test fun savedMemoryNegotiationAndReaderRequestUseOptionalProtectedRoutes() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(response("""{"version":1,"available":true}"""))
            assertTrue(api.savedMemoryCardsCapabilities(token, "family-a").available)
            val cardsProbe = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/saved-memory-capabilities?library_id=family-a", cardsProbe.path)
            assertProtected(cardsProbe)

            f.server.enqueue(response("""{"version":1,"available":true}"""))
            assertTrue(api.savedMemoryActionCapabilities(token, "family-a").available)
            val actionsProbe = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/saved-memory-action-capabilities?library_id=family-a", actionsProbe.path)
            assertProtected(actionsProbe)

            f.server.enqueue(response("""{"version":1,"available":true}"""))
            assertTrue(api.savedMemoryFollowupCapabilities(token, "family-a").available)
            val followupProbe = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/saved-memory-followup-capabilities?library_id=family-a", followupProbe.path)
            assertProtected(followupProbe)
            f.server.enqueue(response("{}", 404))
            assertFalse(api.savedMemoryFollowupCapabilities(token, "family-a").available)
            f.server.takeRequest()

            f.server.enqueue(response("{}", 404))
            assertFalse(api.savedMemoryReaderCapabilities(token, "family-a").available)
            val readerProbe = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/saved-memory-reader-capabilities?library_id=family-a", readerProbe.path)
            assertProtected(readerProbe)

            f.server.enqueue(response("""{"version":1,"available":false}"""))
            assertFalse(api.savedMemorySpeechCapabilities(token, "family-a").available)
            assertEquals("/assistant/workspace/v1/saved-memory-speech-capabilities?library_id=family-a", f.server.takeRequest().path)

            f.server.enqueue(response("""{"version":1,"available":true}"""))
            assertTrue(api.savedMemoryReadingCapabilities(token, "family-a").available)
            val reading = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/saved-memory-reading-capabilities?library_id=family-a", reading.path)
            assertProtected(reading)

            f.server.enqueue(response(envelope("completed", result()), 200))
            api.submitTurn(token, "family-a", thread, request, 0, "find saved story lake", null, true,
                memoryParent = null, acceptSavedMemoryActions = true)
            val post = f.server.takeRequest()
            val body = Json.parseToJsonElement(post.body.readUtf8()).jsonObject
            assertEquals(setOf("library_id", "request_id", "expected_revision", "text", "accepts"), body.keys)
            assertEquals(listOf("saved_memory_cards_v1", "saved_memory_actions_v1"), body.getValue("accepts").jsonArray.map { it.jsonPrimitive.content })

            f.server.enqueue(response(envelope("completed", result()).replace(request, speechRequest)))
            api.submitTurn(token, "family-a", thread, speechRequest, 1, "what is the first saved memory about", request, true,
                AssistantSavedMemoryParent(request, 1))
            val followup = f.server.takeRequest()
            assertEquals("POST", followup.method)
            assertProtected(followup)
            assertEquals(request, followup.getHeader("X-PhotoHouse-Parent-Request-Id"))
            val followupBody = Json.parseToJsonElement(followup.body.readUtf8()).jsonObject
            assertEquals(setOf("library_id", "request_id", "expected_revision", "text", "accepts", "memory_parent"), followupBody.keys)
            assertEquals(setOf("request_id", "revision"), followupBody.getValue("memory_parent").jsonObject.keys)
            assertEquals(request, followupBody.getValue("memory_parent").jsonObject.getValue("request_id").jsonPrimitive.content)
            assertEquals("1", followupBody.getValue("memory_parent").jsonObject.getValue("revision").jsonPrimitive.content)

            f.server.enqueue(response("{}", 404))
            assertEquals(FailureKind.HTTP, runCatching {
                runBlocking { api.savedMemoryReader(token, "family-a", thread, request, 0, 1) }
            }.exceptionOrNull().let { (it as ApiFailure).kind })
            val reader = f.server.takeRequest()
            assertEquals("GET", reader.method)
            assertEquals("/assistant/workspace/v1/threads/$thread/requests/$request/memory-cards/0?library_id=family-a&expected_revision=1", reader.path)
            assertProtected(reader)
            assertNull(reader.requestUrl!!.queryParameter("source_revision"))
            assertNull(reader.requestUrl!!.queryParameter("id"))
        }
    }

    @Test fun legacyFollowup403RequiresSameScopeBaseCapabilityRevalidation() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(response("{}", 403))
            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":true,"preferences_applied":false,"server_owned_turns":true,"applied_preferences":[]}"""))
            assertFalse(api.savedMemoryFollowupCapabilities(token, "family-a").available)
            val followup = f.server.takeRequest()
            val base = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/saved-memory-followup-capabilities?library_id=family-a", followup.path)
            assertEquals("/assistant/workspace/v1/capabilities?library_id=family-a", base.path)
            assertProtected(followup); assertProtected(base)

            f.server.enqueue(response("{}", 403))
            f.server.enqueue(response("{}", 401))
            try {
                api.savedMemoryFollowupCapabilities(token, "family-a")
                fail("base authorization failure was hidden")
            } catch (failure: ApiFailure) {
                assertEquals(401, failure.status)
            }
            assertEquals("/assistant/workspace/v1/saved-memory-followup-capabilities?library_id=family-a", f.server.takeRequest().path)
            val deniedBase = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/capabilities?library_id=family-a", deniedBase.path)
            assertProtected(deniedBase)
        }
    }

    @Test fun legacyAction403RequiresSameScopeBaseCapabilityRevalidation() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(response("{}", 403))
            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":false,"preferences_applied":false,"server_owned_turns":true}"""))
            assertFalse(f.api().savedMemoryActionCapabilities(token, "family-a").available)
            val optional = f.server.takeRequest()
            val base = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/saved-memory-action-capabilities?library_id=family-a", optional.path)
            assertEquals("/assistant/workspace/v1/capabilities?library_id=family-a", base.path)
            assertProtected(optional); assertProtected(base)
        }
    }

    @Test fun privateReplySpeechUsesExactOwnedTurnAndDistinctJournalRequest() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            val audioBytes = wav()
            f.server.enqueue(speechResponse(audioBytes))
            val result = api.speakTurn(token, "family-a", thread, request, 7, speechRequest)
            assertEquals(speechRequest, result.receipt.requestId)
            assertEquals("enabled", result.receipt.tracking)
            assertEquals("succeeded", result.receipt.status)
            assertArrayEquals(audioBytes, result.bytes)
            result.bytes.fill(0)

            val sent = f.server.takeRequest()
            assertEquals("POST", sent.method)
            assertEquals("/assistant/workspace/v1/threads/$thread/requests/$request/speech", sent.path)
            assertEquals(token.header(), sent.getHeader("Authorization"))
            assertEquals("audio/wav", sent.getHeader("Accept"))
            assertEquals("no-store", sent.getHeader("Cache-Control"))
            assertEquals("identity", sent.getHeader("Accept-Encoding"))
            assertEquals(speechRequest, sent.getHeader("X-PhotoHouse-Request-Id"))
            assertEquals(request, sent.getHeader("X-PhotoHouse-Parent-Request-Id"))
            assertNull(sent.getHeader("X-PhotoHouse-Reading-Segment"))
            val body = Json.parseToJsonElement(sent.body.readUtf8()).jsonObject
            assertEquals(setOf("library_id", "expected_revision"), body.keys)
            assertEquals("family-a", body.getValue("library_id").jsonPrimitive.content)
            assertEquals("7", body.getValue("expected_revision").jsonPrimitive.content)
            assertEquals(1, f.server.requestCount)
        }
    }

    @Test fun savedMemoryOpeningSpeechUsesSeparateRouteAndExactBody() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            val audioBytes = wav()
            f.server.enqueue(speechResponse(audioBytes))
            val result = api.speakSavedMemoryOpening(token, "family-a", thread, request, 3, 7, speechRequest)
            assertEquals(speechRequest, result.receipt.requestId)
            assertArrayEquals(audioBytes, result.bytes)
            result.bytes.fill(0)
            val sent = f.server.takeRequest()
            assertEquals("POST", sent.method)
            assertEquals("/assistant/workspace/v1/threads/$thread/requests/$request/memory-cards/3/speech", sent.path)
            assertEquals(token.header(), sent.getHeader("Authorization"))
            assertEquals("audio/wav", sent.getHeader("Accept"))
            assertEquals("no-store", sent.getHeader("Cache-Control"))
            assertEquals("identity", sent.getHeader("Accept-Encoding"))
            assertEquals(speechRequest, sent.getHeader("X-PhotoHouse-Request-Id"))
            assertEquals(request, sent.getHeader("X-PhotoHouse-Parent-Request-Id"))
            val body = Json.parseToJsonElement(sent.body.readUtf8()).jsonObject
            assertEquals(setOf("library_id", "expected_revision"), body.keys)
            assertEquals("family-a", body.getValue("library_id").jsonPrimitive.content)
            assertEquals("7", body.getValue("expected_revision").jsonPrimitive.content)
        }
    }

    @Test fun savedMemorySegmentCapabilityIsIndependentAndOld403IsRevalidated() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(response("""{"version":1,"available":true}"""))
            assertTrue(api.savedMemorySegmentReadingCapabilities(token, "family-a").available)
            assertEquals("/assistant/workspace/v1/saved-memory-segment-reading-capabilities?library_id=family-a",
                f.server.takeRequest().path)

            f.server.enqueue(response("{}", 403))
            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":true,"preferences_applied":false,"server_owned_turns":true,"applied_preferences":[]}"""))
            assertFalse(api.savedMemorySegmentReadingCapabilities(token, "family-a").available)
            assertEquals("/assistant/workspace/v1/saved-memory-segment-reading-capabilities?library_id=family-a", f.server.takeRequest().path)
            assertEquals("/assistant/workspace/v1/capabilities?library_id=family-a", f.server.takeRequest().path)
        }
    }

    @Test fun savedMemorySegmentSpeechUsesExactRouteAndValidatesCanonicalResponseMetadata() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            val audioBytes = wav()
            f.server.enqueue(segmentSpeechResponse(audioBytes, segment = "1", count = "3"))
            val result = api.speakSavedMemorySegment(token, "family-a", thread, request, 3, 1, 7, speechRequest)
            assertEquals(1, result.segment)
            assertEquals(3, result.segmentCount)
            assertEquals(speechRequest, result.receipt.requestId)
            assertArrayEquals(audioBytes, result.bytes)
            result.bytes.fill(0)
            val sent = f.server.takeRequest()
            assertEquals("POST", sent.method)
            assertEquals("/assistant/workspace/v1/threads/$thread/requests/$request/memory-cards/3/segments/1/speech", sent.path)
            assertEquals(token.header(), sent.getHeader("Authorization"))
            assertEquals("audio/wav", sent.getHeader("Accept"))
            assertEquals("no-store", sent.getHeader("Cache-Control"))
            assertEquals("identity", sent.getHeader("Accept-Encoding"))
            assertEquals(speechRequest, sent.getHeader("X-PhotoHouse-Request-Id"))
            assertEquals(request, sent.getHeader("X-PhotoHouse-Parent-Request-Id"))
            val body = Json.parseToJsonElement(sent.body.readUtf8()).jsonObject
            assertEquals(setOf("library_id", "expected_revision"), body.keys)
            assertEquals("family-a", body.getValue("library_id").jsonPrimitive.content)
            assertEquals("7", body.getValue("expected_revision").jsonPrimitive.content)
        }
    }

    @Test fun savedMemorySegmentSpeechRejectsMismatchedOrNonCanonicalHeadersBeforeExposingAudio() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            listOf("1" to "3", "00" to "3", "0" to "01", "0" to "0", "0" to "129").forEach { (segment, count) ->
                f.server.enqueue(segmentSpeechResponse(wav(), segment, count))
                invalid { api.speakSavedMemorySegment(token, "family-a", thread, request, 3, 0, 7, speechRequest) }
                f.server.takeRequest()
            }
            f.server.enqueue(speechResponse(wav()).setHeader("X-PhotoHouse-Reading-Segment", "0"))
            invalid { api.speakSavedMemorySegment(token, "family-a", thread, request, 3, 0, 7, speechRequest) }
            f.server.takeRequest()
            f.server.enqueue(speechResponse(wav())
                .setHeader("X-PhotoHouse-Reading-Segment", "0")
                .setHeader("X-PhotoHouse-Reading-Segment-Count", "2"))
            invalid { api.speakSavedMemorySegment(token, "family-a", thread, request, 3, 0, 7, speechRequest) }
            f.server.takeRequest()
            assertEquals(7, f.server.requestCount)
        }
    }

    @Test fun legacyMemoryReading403NeedsValidSameScopeBaseAndRealDenialPropagates() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(response("{}", 403))
            f.server.enqueue(response("""{"version":1,"available":true,"threads":true,"preferences":true,"preferences_applied":false,"server_owned_turns":true,"applied_preferences":[],"reply_speech":true}"""))
            assertFalse(api.savedMemoryReadingCapabilities(token, "family-a").available)
            assertEquals("/assistant/workspace/v1/saved-memory-reading-capabilities?library_id=family-a", f.server.takeRequest().path)
            assertEquals("/assistant/workspace/v1/capabilities?library_id=family-a", f.server.takeRequest().path)

            f.server.enqueue(response("{}", 403))
            f.server.enqueue(response("{}", 403))
            try { api.savedMemoryReadingCapabilities(token, "family-a"); fail("base authorization denial was hidden") }
            catch (error: ApiFailure) { assertEquals(403, error.status) }
            assertEquals("/assistant/workspace/v1/saved-memory-reading-capabilities?library_id=family-a", f.server.takeRequest().path)
            assertEquals("/assistant/workspace/v1/capabilities?library_id=family-a", f.server.takeRequest().path)
            assertEquals(4, f.server.requestCount)
        }
    }

    @Test fun privateReplySpeechRejectsBadReceiptMIMEAndOversizedAudioWithoutRetry() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(speechResponse(wav(), requestId = "33333333-3333-4333-8333-333333333333"))
            invalid { api.speakTurn(token, "family-a", thread, request, 1, speechRequest) }
            assertEquals(1, f.server.requestCount); f.server.takeRequest()

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json")
                .setHeader("Cache-Control", "no-store"))
            invalid { api.speakTurn(token, "family-a", thread, request, 1, speechRequest) }
            f.server.takeRequest()

            f.server.enqueue(MockResponse().setHeader("Content-Type", "audio/wav").setBody(okio.Buffer().write(wav())))
            invalid { api.speakTurn(token, "family-a", thread, request, 1, speechRequest) }
            f.server.takeRequest()

            f.server.enqueue(speechResponse(wav()).setHeader("Content-Encoding", "gzip"))
            invalid { api.speakTurn(token, "family-a", thread, request, 1, speechRequest) }
            f.server.takeRequest()

            val oversized = ByteArray(2 * 1024 * 1024 + 1)
            f.server.enqueue(speechResponse(oversized))
            try { api.speakTurn(token, "family-a", thread, request, 1, speechRequest); fail("oversized audio accepted") }
            catch (e: ApiFailure) { assertEquals(FailureKind.TOO_LARGE, e.kind) }
            f.server.takeRequest()

            invalidInput { api.speakTurn(token, "family-a", thread, request, 1, request) }
            invalidInput { api.speakTurn(token, "family-a", "bad-thread", request, 1, speechRequest) }
            assertEquals(5, f.server.requestCount)
        }
    }

    @Test fun privateReplySpeechPostIsNotAutomaticallyRetried() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setSocketPolicy(okhttp3.mockwebserver.SocketPolicy.DISCONNECT_AFTER_REQUEST))
            try { f.api().speakTurn(token, "family-a", thread, request, 1, speechRequest); fail("disconnected speech POST succeeded") }
            catch (e: ApiFailure) { assertTrue(e.kind in setOf(FailureKind.OFFLINE, FailureKind.TLS)) }
            assertEquals("POST", f.server.takeRequest().method)
            assertEquals(1, f.server.requestCount)
        }
    }

    @Test fun privateReplySpeechCancellationStopsTheHttpsCall() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setHeader("Content-Type", "audio/wav")
                .setHeader("Cache-Control", "no-store")
                .setChunkedBody("x".repeat(64 * 1024), 1024)
                .throttleBody(1024, 100, java.util.concurrent.TimeUnit.MILLISECONDS))
            val pending = launch(Dispatchers.IO) {
                try { f.api().speakTurn(token, "family-a", thread, request, 1, speechRequest) }
                catch (_: CancellationException) { }
                catch (_: ApiFailure) { }
            }
            assertNotNull(f.server.takeRequest())
            delay(150)
            pending.cancelAndJoin()
            assertTrue(pending.isCancelled)
            assertEquals(1, f.server.requestCount)
        }
    }

    @Test fun labelsAreRequestedOnlyByOptInAndHistoryUsesExactSnapshotCursor() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            val summary = """{"thread_id":"$thread","library_id":"family-a","created_at":"2026-10-13T00:00:00Z","updated_at":"2026-10-13T00:00:00Z","expires_at":"2026-11-12T00:00:00Z","revision":5,"exchange_count":2"""

            f.server.enqueue(response("""{"version":1,"threads":[$summary}]}"""))
            assertNull(api.listThreads(token, "family-a").threads.single().label)
            val legacy = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/threads?library_id=family-a&limit=50", legacy.path)
            assertProtected(legacy)

            f.server.enqueue(response("""{"version":1,"threads":[$summary,"label":"旅行照片 · 北京"}]}"""))
            assertEquals("旅行照片 · 北京", api.listThreads(token, "family-a", includeLabels = true).threads.single().label)
            val labeled = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/threads?library_id=family-a&limit=50&include_labels=true", labeled.path)
            assertProtected(labeled)

            val row = """{"exchange_id":"33333333-3333-4333-8333-333333333333","revision":2,"created_at":"2026-10-13T00:00:00Z","expires_at":"2026-11-12T00:00:00Z","input_text":"older question","reply":"older answer","cards":[],"receipt_count":0}"""
            f.server.enqueue(response("""{"version":1,"thread_id":"$thread","snapshot_revision":5,"before_revision":5,"exchanges":[$row],"has_older_exchanges":true,"next_before_revision":2}"""))
            val page = api.readHistory(token, "family-a", thread, beforeRevision = 5, snapshotRevision = 5)
            assertEquals(thread, page.threadId)
            assertEquals(5L, page.snapshotRevision)
            assertEquals(5L, page.beforeRevision)
            assertEquals(listOf(2L), page.exchanges.map { it.revision })
            assertEquals(2L, page.nextBeforeRevision)
            val history = f.server.takeRequest()
            assertEquals("/assistant/workspace/v1/threads/$thread/history?library_id=family-a&before_revision=5&snapshot_revision=5", history.path)
            assertProtected(history)

            f.server.enqueue(response("""{"version":1,"thread_id":"$thread","snapshot_revision":5,"before_revision":4,"exchanges":[],"has_older_exchanges":false,"next_before_revision":null}"""))
            invalid { api.readHistory(token, "family-a", thread, beforeRevision = 5, snapshotRevision = 5) }
            assertEquals("GET", f.server.takeRequest().method)
            assertEquals(4, f.server.requestCount)
        }
    }

    @Test fun refusesRecoveredOpenEffectAndBadCorrelation() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(response(envelope("completed", result("open", "{\"type\":\"open_asset\",\"asset_id\":\"123\"}"), recovered = true)))
            invalid { api.getTurn(token, "family-a", thread, request) }; f.server.takeRequest()
            f.server.enqueue(response(envelope("completed", result(), recovered = true).replace(thread, "33333333-3333-4333-8333-333333333333")))
            invalid { api.getTurn(token, "family-a", thread, request) }
            assertEquals("GET", f.server.takeRequest().method)
            f.server.enqueue(response(envelope("pending")).setHeader("X-PhotoHouse-Tracking", "enabled")
                .setHeader("X-PhotoHouse-Request-Id", "33333333-3333-4333-8333-333333333333")
                .setHeader("X-PhotoHouse-Receipt-Status", "received"))
            invalid { api.submitTurn(token, "family-a", thread, request, 0, "Find", "33333333-3333-4333-8333-333333333334") }
            val mismatched = f.server.takeRequest()
            assertEquals("33333333-3333-4333-8333-333333333334", mismatched.getHeader("X-PhotoHouse-Parent-Request-Id"))
            assertEquals(3, f.server.requestCount)
        }
    }

    @Test fun redirectMimeEncodingNoStoreAndResponseSizeAreRejected(): Unit = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "/elsewhere"))
            httpFailure(302) { api.capabilities(token, "family-a") }; f.server.takeRequest()
            f.server.enqueue(MockResponse().setHeader("Content-Type", "text/plain").setBody("{}"))
            invalid { api.capabilities(token, "family-a") }; f.server.takeRequest()
            f.server.enqueue(response("{} ").setHeader("Content-Encoding", "gzip"))
            invalid { api.capabilities(token, "family-a") }; f.server.takeRequest()
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            invalid { api.capabilities(token, "family-a") }; f.server.takeRequest()
            f.server.enqueue(response(" ".repeat(AssistantWorkspaceWire.RESPONSE_LIMIT + 1)))
            try { api.capabilities(token, "family-a"); fail("oversized response accepted") }
            catch (e: ApiFailure) { assertEquals(FailureKind.TOO_LARGE, e.kind) }
            f.server.takeRequest()
            Unit
        }
    }

    @Test fun rejectsUntrustedCertificate() = runBlocking {
        val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
            enqueue(response("{}"))
        }
        try {
            val untrusted = HttpsAssistantWorkspaceApi(TrustedOrigin.parse("https://localhost:${server.port}"), true)
            try { untrusted.capabilities(token, "family-a"); fail("untrusted certificate accepted") }
            catch (e: ApiFailure) { assertEquals(FailureKind.TLS, e.kind) }
        } finally { server.shutdown() }
    }

    @Test fun failedPostIsNotRetriedAndCancellationStopsTheCall() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setSocketPolicy(okhttp3.mockwebserver.SocketPolicy.DISCONNECT_AFTER_REQUEST))
            try { f.api().submitTurn(token, "family-a", thread, request, 0, "Find photos"); fail("disconnected POST succeeded") }
            catch (e: ApiFailure) { assertTrue(e.kind in setOf(FailureKind.OFFLINE, FailureKind.TLS)) }
            assertEquals("POST", f.server.takeRequest().method)
            assertEquals(1, f.server.requestCount)

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json")
                .setHeader("Cache-Control", "no-store")
                .setChunkedBody(" ".repeat(64 * 1024), 1024).throttleBody(1024, 100, java.util.concurrent.TimeUnit.MILLISECONDS))
            val pending = launch(Dispatchers.IO) {
                try { f.api().capabilities(token, "family-a") }
                catch (_: CancellationException) { }
                catch (_: ApiFailure) { }
            }
            assertNotNull(f.server.takeRequest())
            delay(150)
            pending.cancelAndJoin()
            assertTrue(pending.isCancelled)
        }
    }

    private fun assertProtected(request: okhttp3.mockwebserver.RecordedRequest) {
        assertEquals(token.header(), request.getHeader("Authorization"))
        assertEquals("application/json", request.getHeader("Accept"))
        assertEquals("no-store", request.getHeader("Cache-Control"))
        assertEquals("identity", request.getHeader("Accept-Encoding"))
    }
    private fun invalid(block: suspend () -> Any?) = runBlocking {
        try { block(); fail("invalid workspace response accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }
    private fun invalidInput(block: suspend () -> Any?) = runBlocking {
        try { block(); fail("invalid workspace request accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
    }
    private fun httpFailure(status: Int, block: suspend () -> Any?) = runBlocking {
        try { block(); fail("HTTP $status accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.HTTP, e.kind); assertEquals(status, e.status) }
    }
}
