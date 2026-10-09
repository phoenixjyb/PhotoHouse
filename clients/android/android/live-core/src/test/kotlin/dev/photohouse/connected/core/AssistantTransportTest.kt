package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class AssistantTransportTest {
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private class Fixture : AutoCloseable {
        val certificate = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(certificate).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        val origin = TrustedOrigin.parse("https://localhost:${server.port}")
        val api = HttpsPhotoHouseApi(origin, client, assistantEnabled = true)
        override fun close() { server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll() }
        fun enqueue(body: String, status: Int = 200) = server.enqueue(MockResponse().setResponseCode(status)
            .setHeader("Content-Type", "application/json").setBody(body))
    }

    @Test fun capabilityProbeUsesProtectedQueryAndNoCache() = runBlocking {
        Fixture().use { f ->
            f.enqueue("""{"version":1,"enabled":true,"text":true,"transcribe":false,"speech":false,"max_audio_seconds":0}""")
            assertEquals(AssistantCapabilities(true, true, false, false, 0), f.api.assistantCapabilities(token, "family-a"))
            val request = f.server.takeRequest()
            assertEquals("GET", request.method)
            assertEquals("/assistant/v1/capabilities?library_id=family-a", request.path)
            assertEquals("Bearer ${"T".repeat(43)}", request.getHeader("Authorization"))
            assertEquals("no-store", request.getHeader("Cache-Control")); assertNull(request.getHeader("Cookie"))
        }
    }

    @Test fun turnPostsJsonWithoutLibraryOrContextInUrlAndSurfacesUnavailable() = runBlocking {
        Fixture().use { f ->
            f.enqueue("""{"version":1,"kind":"clarification","reply":"Which summer?","context":{"revision":"opaque"},"filters":null,"items":[],"total":0,"has_more":false,"effect":null}""")
            val result = f.api.assistantTurn(token, "family-a", "找夏天的照片", null)
            assertEquals("clarification", result.kind)
            val request = f.server.takeRequest()
            assertEquals("POST", request.method); assertEquals("/assistant/v1/turns", request.path)
            val json = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
            assertEquals("family-a", json.getValue("library_id").jsonPrimitive.content)
            assertEquals("找夏天的照片", json.getValue("text").jsonPrimitive.content)
            assertEquals(JsonNull, json.getValue("context")); assertNull(request.requestUrl?.query)
            assertEquals("no-store", request.getHeader("Cache-Control")); assertEquals("Bearer ${"T".repeat(43)}", request.getHeader("Authorization"))

            f.enqueue("{}", 503)
            val failure = runCatching { f.api.assistantTurn(token, "family-a", "再缩小范围", result.context) }.exceptionOrNull() as ApiFailure
            assertEquals(503, failure.status)
        }
    }

    @Test fun trackedTurnSendsParentAndValidatesReceiptHeaders() = runBlocking {
        Fixture().use { f ->
            val id = "123e4567-e89b-42d3-a456-426614174000"
            val parent = "123e4567-e89b-42d3-a456-426614174001"
            f.server.enqueue(MockResponse().setResponseCode(200).setHeader("Content-Type", "application/json")
                .setHeader("X-PhotoHouse-Tracking", "enabled").setHeader("X-PhotoHouse-Request-Id", id)
                .setHeader("X-PhotoHouse-Receipt-Status", "succeeded")
                .setBody("""{"version":1,"kind":"clarification","reply":"Which summer?","context":null,"filters":null,"items":[],"total":0,"has_more":false,"effect":null}"""))
            val turn = f.api.assistantTurn(token, "family-a", "Find summer", null, id, parent)
            assertEquals(AssistantRequestReceipt(id, "enabled", "succeeded"), turn.receipt)
            val req = f.server.takeRequest()
            assertEquals(id, req.getHeader("X-PhotoHouse-Request-Id")); assertEquals(parent, req.getHeader("X-PhotoHouse-Parent-Request-Id"))
        }
    }

    @Test fun receiptReadUsesBearerAndSelectedLibraryAndParsesStrictEnvelope() = runBlocking {
        Fixture().use { f ->
            val id = "123e4567-e89b-42d3-a456-426614174000"
            f.enqueue("""{"version":1,"request_id":"$id","operation":"turn","parent_request_id":null,"status":"succeeded","created_at":"2026-09-30T00:00:00Z","updated_at":"2026-09-30T00:00:01Z","expires_at":"2026-10-30T00:00:00Z","http_status":200,"error_code":null,"input_text":"Find summer","recognized_text":null,"result_kind":"results","result_total":12,"client_outcome":null}""")
            val receipt = f.api.assistantReceipt(token, "family-a", id)
            assertEquals("succeeded", receipt.status); assertEquals(12, receipt.resultTotal)
            val req = f.server.takeRequest()
            assertEquals("GET", req.method); assertEquals("/assistant/v1/receipts/$id?library_id=family-a", req.path)
            assertEquals("Bearer ${"T".repeat(43)}", req.getHeader("Authorization")); assertNull(req.requestUrl?.encodedFragment)
        }
    }

    @Test fun assistantCallsAreDisabledUnlessExplicitlyConfigured() = runBlocking {
        Fixture().use { f ->
            val disabled = HttpsPhotoHouseApi(f.origin, f.client)
            assertTrue(runCatching { disabled.assistantCapabilities(token, "family-a") }.isFailure)
            assertTrue(runCatching { disabled.assistantTurn(token, "family-a", "hello", null) }.isFailure)
            assertEquals(0, f.server.requestCount)
        }
    }

    @Test fun transcriptionPostsRawWavWithLibraryHeaderAndNoTurnSubmission() = runBlocking {
        Fixture().use { f ->
            f.enqueue("""{"version":1,"text":"海边的照片","language":"zh"}""")
            val wav = ByteArray(16046).also { "RIFF".toByteArray().copyInto(it); "WAVE".toByteArray().copyInto(it, 8) }
            assertEquals(AssistantTranscript("海边的照片", "zh"), f.api.assistantTranscribe(token, "family-a", wav))
            val req = f.server.takeRequest()
            assertEquals("POST", req.method); assertEquals("/assistant/v1/transcribe", req.path)
            assertEquals("audio/wav", req.getHeader("Content-Type")); assertEquals("family-a", req.getHeader("X-PhotoHouse-Library-Id"))
            assertEquals(wav.toList(), req.body.readByteArray().toList())
            assertEquals("no-store", req.getHeader("Cache-Control")); assertEquals("Bearer ${"T".repeat(43)}", req.getHeader("Authorization"))
        }
    }

    @Test fun transcriptionCarriesCallerIdAndConsumesTrackingHeaders() = runBlocking {
        Fixture().use { f ->
            val id = "123e4567-e89b-42d3-a456-426614174000"
            f.server.enqueue(MockResponse().setResponseCode(200).setHeader("Content-Type", "application/json")
                .setHeader("X-PhotoHouse-Tracking", "enabled").setHeader("X-PhotoHouse-Request-Id", id)
                .setHeader("X-PhotoHouse-Receipt-Status", "succeeded")
                .setBody("""{"version":1,"text":"beach","language":"en"}"""))
            val wav = ByteArray(16046).also { "RIFF".toByteArray().copyInto(it); "WAVE".toByteArray().copyInto(it, 8) }
            val result = f.api.assistantTranscribe(token, "family-a", wav, id)
            assertEquals(AssistantRequestReceipt(id, "enabled", "succeeded"), result.receipt)
            assertEquals(id, f.server.takeRequest().getHeader("X-PhotoHouse-Request-Id"))
        }
    }

    @Test fun speechPostsResultContextAndReturnsProtectedRawWav() = runBlocking {
        Fixture().use { f ->
            val wav = ByteArray(46).also { "RIFF".toByteArray().copyInto(it); "WAVE".toByteArray().copyInto(it, 8) }
            f.server.enqueue(MockResponse().setResponseCode(200).setHeader("Content-Type", "audio/wav")
                .setHeader("Cache-Control", "no-store").setBody(okio.Buffer().write(wav)))
            val context = JsonObject(mapOf("revision" to JsonPrimitive("opaque")))
            assertEquals(wav.toList(), f.api.assistantSpeech(token, "family-a", context, "zh").toList())
            val req = f.server.takeRequest()
            assertEquals("POST", req.method); assertEquals("/assistant/v1/speech", req.path)
            assertEquals("application/json; charset=utf-8", req.getHeader("Content-Type"))
            val json = Json.parseToJsonElement(req.body.readUtf8()).jsonObject
            assertEquals(setOf("library_id", "context", "language"), json.keys)
            assertEquals("family-a", json.getValue("library_id").jsonPrimitive.content)
            assertEquals(context, json.getValue("context")); assertEquals("zh", json.getValue("language").jsonPrimitive.content)
            assertNull(req.getHeader("X-PhotoHouse-Library-Id")); assertEquals("no-store", req.getHeader("Cache-Control"))
        }
    }
}
