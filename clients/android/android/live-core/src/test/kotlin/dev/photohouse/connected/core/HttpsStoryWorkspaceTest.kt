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
    @Test fun capability403IsLegacyOnlyAfterProtectedMembershipRecheck() = runBlocking {
        val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        server.useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
        server.start(InetAddress.getByName("127.0.0.1"), 0)
        try {
            val api = HttpsPhotoHouseApi(TrustedOrigin.parse("https://localhost:${server.port}"), client, protectedNativeV2Enabled = true)
            val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
            val active = """{"account_id":"acct","phone_login":"+12025550123","display_name":"Member","memberships":[{"library_id":"family-a","status":"active","role":"member","revision":1,"expires_at":null,"originals":1,"available":true}]}"""
            server.enqueue(MockResponse().setResponseCode(403))
            server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(active))
            try { api.sourceCapabilities(token, "family-a"); fail("Expected legacy-only result") }
            catch (failure: ApiFailure) { assertEquals(404, failure.status) }
            assertEquals("/story-workspace/source-capabilities?library=family-a", server.takeRequest().path)
            assertEquals("/auth/session", server.takeRequest().path)

            val revoked = active.replace("\"status\":\"active\"", "\"status\":\"revoked\"").replace("\"available\":true", "\"available\":false")
            server.enqueue(MockResponse().setResponseCode(403))
            server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(revoked))
            try { api.sourceCapabilities(token, "family-a"); fail("Membership denial must remain visible") }
            catch (failure: ApiFailure) { assertEquals(403, failure.status) }
            server.takeRequest(); server.takeRequest()
            Unit
        } finally {
            server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll()
        }
    }

    @Test fun sourceReviewCapabilityAndMutationUseExplicitProfileQuery() = runBlocking {
        val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        server.useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
        server.start(InetAddress.getByName("127.0.0.1"), 0)
        try {
            val api = HttpsPhotoHouseApi(TrustedOrigin.parse("https://localhost:${server.port}"), client, protectedNativeV2Enabled = true)
            val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
            val body = "{\"source_policy\":\"chapter_sources_v1\"}"
            server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            api.sourceCapabilities(token, "family-a")
            assertEquals("/story-workspace/source-capabilities?library=family-a", server.takeRequest().path)
            server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            api.storyTitles(token, "family-a", body, sourceReview = true)
            val titles = server.takeRequest()
            assertEquals("/story-workspace/title-suggestions?library=family-a&source_review=1", titles.path)
            assertEquals(body, titles.body.readUtf8())
            server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            api.createGroupedStory(token, "family-a", body, sourceReview = true)
            val save = server.takeRequest()
            assertEquals("/memory-stories?library=family-a&source_review=1", save.path)
            assertEquals(body, save.body.readUtf8())
        } finally {
            server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll()
        }
    }

    @Test fun savedStoryEditUsesExistingPutWithFrozenProfileFlagsAndExactBody() = runBlocking {
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
            val id = "33333333-3333-4333-8333-333333333333"
            val body = "{\"revision\":\"8\",\"mutation_id\":\"22222222-2222-4222-8222-222222222222\",\"contribution_refs\":\"[]\"}"
            server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            api.updateGroupedStory(token, "family-a", id, body, sourceReview = true, contributionReferences = true)
            val request = server.takeRequest()
            assertEquals("/memory-stories/$id?library=family-a&contribution_refs=1&source_review=1", request.path)
            assertEquals("PUT", request.method)
            assertEquals(token.header(), request.getHeader("Authorization"))
            assertEquals(body, request.body.readUtf8())
            try { api.updateGroupedStory(token, "family-a", "not-a-uuid", body, false, true); fail() }
            catch (_: IllegalArgumentException) { }
            assertEquals(1, server.requestCount)
        } finally {
            server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll()
        }
    }

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
