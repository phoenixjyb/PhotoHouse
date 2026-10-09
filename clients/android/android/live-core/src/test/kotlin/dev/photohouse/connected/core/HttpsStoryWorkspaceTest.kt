package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class HttpsStoryWorkspaceTest {
    @Test fun protectedRoutesKeepExactBodyAndHaveNoRedirectOrLegacyFallback() = runBlocking {
        val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        server.useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
        server.start(InetAddress.getByName("127.0.0.1"), 0)
        try {
            val api = HttpsPhotoHouseApi(TrustedOrigin.parse("https://localhost:${server.port}"), client,
                protectedNativeV2Enabled = true)
            val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
            val body = "{\"text\":\"合成文字\"}"
            val relatedBody = "{\"asset_ids\":\"102,101\",\"before_id\":\"204\"}"
            val calls: List<Pair<String, suspend () -> ByteArray>> = listOf(
                "story-workspace/preview" to { api.storyPreview(token, "family-a", body) },
                "story-workspace/title-capabilities" to { api.storyTitleCapabilities(token, "family-a") },
                "story-workspace/title-suggestions" to { api.storyTitles(token, "family-a", body) },
                "story-workspace/related-media" to { api.relatedStoryMedia(token, "family-a", relatedBody) },
                "memory-stories" to { api.createGroupedStory(token, "family-a", body) },
            )
            for ((path, call) in calls) {
                server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
                call()
                val request = server.takeRequest()
                assertEquals("/$path?library=family-a", request.path)
                assertEquals(token.header(), request.getHeader("Authorization"))
                assertEquals("no-store", request.getHeader("Cache-Control"))
                assertEquals("identity", request.getHeader("Accept-Encoding"))
                if (path.endsWith("capabilities")) assertEquals("GET", request.method)
                else {
                    assertEquals("POST", request.method)
                    assertEquals(if (path.endsWith("related-media")) relatedBody else body, request.body.readUtf8())
                }
            }
            server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "/legacy"))
            try { api.createGroupedStory(token, "family-a", body); fail() }
            catch (e: ApiFailure) { assertEquals(302, e.status) }
            assertEquals(6, server.requestCount)
            try { api.storyPreview(token, "family-a", "x".repeat(4097)); fail() }
            catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
            val disabled = HttpsPhotoHouseApi(TrustedOrigin.parse("https://localhost:${server.port}"), client)
            try { disabled.storyTitleCapabilities(token, "family-a"); fail() }
            catch (_: IllegalArgumentException) { }
            assertEquals(6, server.requestCount)
        } finally {
            server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll()
        }
    }
}
