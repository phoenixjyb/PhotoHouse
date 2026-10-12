package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.*
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
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

    @Test fun turnPostCarriesOnlyUserInputAndGetRecoversWithoutResending() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(response(envelope("pending")))
            assertEquals(AssistantWorkspaceRequestStatus.PENDING,
                api.submitTurn(token, "family-a", thread, request, 0, "找照片").status)
            val post = f.server.takeRequest()
            assertEquals("POST", post.method); assertEquals("/assistant/workspace/v1/threads/$thread/turns", post.path); assertProtected(post)
            val body = Json.parseToJsonElement(post.body.readUtf8()).jsonObject
            assertEquals(setOf("library_id", "request_id", "expected_revision", "text"), body.keys)
            assertFalse(body.containsKey("context")); assertFalse(body.containsKey("reply")); assertFalse(body.containsKey("cards"))

            f.server.enqueue(response(envelope("completed", result(), recovered = true)))
            val recovered = api.getTurn(token, "family-a", thread, request)
            assertEquals(AssistantWorkspaceRequestStatus.COMPLETED, recovered.status)
            assertTrue(recovered.recovered); assertNull(recovered.result!!.effect)
            val get = f.server.takeRequest()
            assertEquals("GET", get.method)
            assertEquals("/assistant/workspace/v1/threads/$thread/requests/$request?library_id=family-a", get.path)
            assertProtected(get)
            assertEquals(2, f.server.requestCount)
        }
    }

    @Test fun refusesRecoveredOpenEffectAndBadCorrelation() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(response(envelope("completed", result("open", "{\"type\":\"open_asset\",\"asset_id\":\"123\"}"), recovered = true)))
            invalid { api.getTurn(token, "family-a", thread, request) }; f.server.takeRequest()
            f.server.enqueue(response(envelope("completed", result(), recovered = true).replace(thread, "33333333-3333-4333-8333-333333333333")))
            invalid { api.getTurn(token, "family-a", thread, request) }
            assertEquals(2, f.server.requestCount)
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
    private fun httpFailure(status: Int, block: suspend () -> Any?) = runBlocking {
        try { block(); fail("HTTP $status accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.HTTP, e.kind); assertEquals(status, e.status) }
    }
}
