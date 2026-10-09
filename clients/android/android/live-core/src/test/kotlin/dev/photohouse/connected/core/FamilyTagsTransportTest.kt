package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.*
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class FamilyTagsTransportTest {
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
        val api = HttpsPhotoHouseApi(origin, client, protectedNativeV2Enabled = true, familyTagsEnabled = true)
        fun enqueue(body: JsonObject, status: Int = 200) = server.enqueue(MockResponse().setResponseCode(status).setHeader("Content-Type", "application/json; charset=utf-8").setBody(body.toString()))
        override fun close() { server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll() }
    }
    private fun catalog(library: String) = buildJsonObject {
        put("library_id", library); put("page", 2); put("page_size", 25); put("total", 26)
        put("items", buildJsonArray { add(buildJsonObject { put("name", "生日 party"); put("asset_count", 4) }) })
    }
    private fun assets(library: String) = buildJsonObject {
        put("library_id", library); put("tag", "生日 party"); put("page", 3); put("page_size", 25); put("total", 51)
        put("originals_allowed", true); put("items", buildJsonArray { add(buildJsonObject {
            put("id", "42"); put("kind", "image"); put("width", 640); put("height", 480)
            put("duration_sec", JsonNull); put("taken_at", JsonNull)
            put("thumbnail_url", "/assets/42/thumbnail?library=${library.replace(" ", "%20")}")
        }) })
    }
    @Test fun catalogUsesProtectedBearerLiteralQueryAndBindsPage() = runBlocking {
        Fixture().use { f ->
            val library = "Family 家"
            f.enqueue(catalog(library)); val response = f.api.familyTags(token, library, 2, "生日 party")
            assertEquals(listOf(FamilyTagChoice("生日 party", 4)), response.items)
            val request = f.server.takeRequest()
            assertEquals("/family-tags", request.requestUrl!!.encodedPath)
            assertEquals(library, request.requestUrl!!.queryParameter("library")); assertEquals("2", request.requestUrl!!.queryParameter("page"))
            assertEquals("生日 party", request.requestUrl!!.queryParameter("q")); assertEquals("GET", request.method)
            assertEquals("Bearer ${"T".repeat(43)}", request.getHeader("Authorization"))
            assertEquals("no-store", request.getHeader("Cache-Control")); assertNull(request.getHeader("Cookie")); assertNull(request.getHeader("Origin"))
        }
    }
    @Test fun assetLookupPostsExactTagAndPageToProtectedPath() = runBlocking {
        Fixture().use { f ->
            val library = "family-a"
            f.enqueue(assets(library)); val response = f.api.familyTagAssets(token, library, "生日 party", 3)
            assertEquals("42", response.items.single().id)
            val request = f.server.takeRequest()
            assertEquals("/family-tags/assets?library=family-a", request.path); assertEquals("POST", request.method)
            assertEquals("Bearer ${"T".repeat(43)}", request.getHeader("Authorization"))
            val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
            assertEquals(setOf("tag", "page"), body.keys); assertEquals("生日 party", body.getValue("tag").jsonPrimitive.content)
            assertEquals(3, body.getValue("page").jsonPrimitive.int)
            assertEquals("no-store", request.getHeader("Cache-Control")); assertNull(request.getHeader("Cookie"))
        }
    }
    @Test fun disabledOrUnprotectedCapabilityMakesNoRequests() = runBlocking {
        Fixture().use { f ->
            val off = HttpsPhotoHouseApi(f.origin, f.client)
            assertFalse(off.familyTagsEnabled)
            assertTrue(runCatching { off.familyTags(token, "family-a") }.isFailure)
            assertTrue(runCatching { HttpsPhotoHouseApi(f.origin, f.client, familyTagsEnabled = true) }.isFailure)
            assertEquals(0, f.server.requestCount)
        }
    }
    @Test fun mismatchedScopeAndInvalidQueriesAreRejectedWithoutFollowingAlternateRoutes() = runBlocking {
        Fixture().use { f ->
            f.enqueue(catalog("other"))
            assertTrue(runCatching { f.api.familyTags(token, "family-a", 2) }.isFailure)
            assertEquals(1, f.server.requestCount)
            assertTrue(runCatching { f.api.familyTags(token, "family-a", query = "界".repeat(171)) }.isFailure)
            assertTrue(runCatching { f.api.familyTagAssets(token, "family-a", "  ") }.isFailure)
            assertEquals(1, f.server.requestCount)
        }
    }
}
