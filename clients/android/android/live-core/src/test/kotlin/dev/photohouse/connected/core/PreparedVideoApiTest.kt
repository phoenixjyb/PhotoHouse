package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.*
import okhttp3.tls.*
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class PreparedVideoApiTest {
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private val etag = "\"" + "a".repeat(64) + "\""
    private class Fixture : AutoCloseable {
        val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        val origin = TrustedOrigin.parse("https://localhost:${server.port}")
        val api = HttpsPhotoHouseApi(origin, client, protectedNativeV2Enabled = true, preparedVideoEnabled = true)
        override fun close() { server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll() }
    }
    private fun headers(response: MockResponse = MockResponse()) = response
        .setHeader("Content-Type", "video/mp4").setHeader("Cache-Control", "no-store")
        .setHeader("Accept-Ranges", "bytes").setHeader("ETag", etag)
    private fun head() = headers().setHeader("Content-Length", "10")
    private fun range(data: String = "abcd", value: String = "bytes 0-3/10") = headers().setResponseCode(206)
        .setBody(data).setHeader("Content-Range", value)
    private suspend fun failure(block: suspend () -> Unit): ApiFailure {
        try { block() } catch (e: ApiFailure) { return e }
        throw AssertionError("Expected failure")
    }
    @Test fun headAndEverySeekAuthenticateAndBindToPreparedRepresentation() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(head()); f.server.enqueue(range()); f.server.enqueue(range("ij", "bytes 8-9/10"))
            val info = f.api.preparedVideoInfo(token, "family", "102")
            assertEquals(PreparedVideoInfo(10, etag), info)
            assertArrayEquals("abcd".toByteArray(), f.api.preparedVideoRange(token, "family", "102", info, 0, 4).bytes)
            assertArrayEquals("ij".toByteArray(), f.api.preparedVideoRange(token, "family", "102", info, 8, 4).bytes)
            for (i in 0..2) {
                val request = f.server.takeRequest()
                assertEquals("/assets/102/playback?library=family", request.path)
                assertEquals(if (i == 0) "HEAD" else "GET", request.method)
                assertEquals("Bearer " + "T".repeat(43), request.getHeader("Authorization"))
                assertEquals("no-store", request.getHeader("Cache-Control"))
                assertNull(request.getHeader("Cookie"))
                assertEquals(if (i == 0) null else etag, request.getHeader("If-Range"))
                assertEquals(listOf(null,"bytes=0-3","bytes=8-11")[i],request.getHeader("Range"))
            }
        }
    }
    @Test fun readinessRejectsUnboundedAmbiguousOrWrongMediaMetadata() = runBlocking {
        Fixture().use { f ->
            val invalid = listOf(head().removeHeader("ETag"), head().setHeader("ETag", "W/$etag"),
                head().setHeader("Content-Length", "0"), head().setHeader("Content-Length", (HttpsPhotoHouseApi.VIDEO_FILE_LIMIT+1).toString()),
                head().setHeader("Content-Type", "video/webm"), head().setHeader("Cache-Control", "public"),
                head().addHeader("ETag",etag), head().setHeader("Content-Encoding", "gzip"), head().setResponseCode(206))
            for (response in invalid) {
                f.server.enqueue(response)
                failure { f.api.preparedVideoInfo(token,"family","102") }
            }
            assertEquals(invalid.size,f.server.requestCount)
        }
    }
    @Test fun changedEtagOrSizeAndIgnoredIfRangeNeverDeliverMixedBytes() = runBlocking {
        Fixture().use { f ->
            val info = PreparedVideoInfo(10,etag)
            for (response in listOf(range().setHeader("ETag","\""+"b".repeat(64)+"\""),
                range().setResponseCode(200),range(value="bytes 0-3/11"))) {
                f.server.enqueue(response)
                assertEquals(409,failure { f.api.preparedVideoRange(token,"family","102",info,0,4) }.status)
            }
        }
    }
    @Test fun readinessFailuresNeverRetryOrFallbackAndRespectBusyDelay() = runBlocking {
        Fixture().use { f ->
            for (code in listOf(401,403,404,409,429,503)) {
                f.server.enqueue(MockResponse().setResponseCode(code).setHeader("Retry-After","2"))
                val error = failure { f.api.preparedVideoInfo(token,"family","102") }
                assertEquals(code,error.status)
                if (code == 429) assertEquals(2000L,error.retryAfterMillis)
                assertEquals("HEAD",f.server.takeRequest().method)
            }
            assertEquals(6,f.server.requestCount)
        }
    }
    @Test fun redirectsDoNotFollowAndDefaultProfileMakesNoPlaybackRequest() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setResponseCode(302).setHeader("Location","https://other.invalid/media"))
            assertEquals(302,failure { f.api.preparedVideoInfo(token,"family","102") }.status)
            val disabled = HttpsPhotoHouseApi(f.origin,f.client,protectedNativeV2Enabled=true)
            assertTrue(runCatching { disabled.preparedVideoInfo(token,"family","102") }.exceptionOrNull() is IllegalArgumentException)
            assertEquals(1,f.server.requestCount)
        }
    }
}
