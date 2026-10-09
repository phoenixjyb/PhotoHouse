package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.*
import okhttp3.tls.*
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class PhoneDiscoveryTransportTest {
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
        val api = HttpsPhotoHouseApi(origin, client, discoveryEnabled = true)
        fun enqueue(body: JsonObject, status: Int = 200) = server.enqueue(MockResponse().setResponseCode(status).setHeader("Content-Type", "application/json").setBody(body.toString()))
        override fun close() { server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll() }
    }
    @Test fun encodedLibraryFacetsUseBearerNoCookiesAndNoCache() = runBlocking {
        Fixture().use { f ->
            val library = "Family 家 / a?b"
            val body = JsonObject(DiscoveryExamples.body("tags") + ("library_id" to JsonPrimitive(library)))
            f.enqueue(body); f.api.facets(token, library, PhoneFacet.TAGS, 1, null)
            val request = f.server.takeRequest()
            assertEquals(listOf("libraries", library, "discovery", "v1", "facets"), request.requestUrl!!.pathSegments)
            assertEquals("GET", request.method); assertEquals("tags", request.requestUrl!!.queryParameter("facet"))
            assertEquals("50", request.requestUrl!!.queryParameter("page_size"))
            assertEquals("Bearer ${"T".repeat(43)}", request.getHeader("Authorization"))
            assertEquals("no-store", request.getHeader("Cache-Control")); assertNull(request.getHeader("Cookie")); assertNull(request.getHeader("Origin"))
        }
    }
    @Test fun placeQueryIsOnlySentForLocationFacetAndIsUtf8Bounded() = runBlocking {
        Fixture().use { f ->
            val library = "family-a"
            val body = JsonObject(DiscoveryExamples.body("locations") + ("library_id" to JsonPrimitive(library)))
            f.enqueue(body); f.api.placeFacets(token, library, 1, "北京 Beijing", null)
            val request = f.server.takeRequest()
            assertEquals("locations", request.requestUrl!!.queryParameter("facet"))
            assertEquals("北京 Beijing", request.requestUrl!!.queryParameter("q"))
            assertTrue(runCatching { f.api.placeFacets(token, library, 1, "界".repeat(43), null) }.isFailure)
        }
    }
    @Test fun discoveryPostBudgetDoesNotBroadenLoginAndNeverSendsFiltersInUrl() = runBlocking {
        Fixture().use { f ->
            val choices = (1..20).map { PhoneChoice((Long.MAX_VALUE - it).toString(), "Selection", 1) }
            val filters = PhoneFilters(people = choices, tags = choices, places = choices, caption = "\"".repeat(512))
            val original = DiscoveryExamples.body("all-media-first")
            f.enqueue(JsonObject(original + mapOf("page_size" to JsonPrimitive(50), "total" to JsonPrimitive(1), "has_more" to JsonPrimitive(false))))
            f.api.search(token, "family-a", DiscoveryExamples.binding, filters, 1, null)
            val r = f.server.takeRequest()
            assertEquals("/libraries/family-a/discovery/v1/search", r.path); assertEquals("POST", r.method)
            assertTrue(r.bodySize > 2048); assertTrue(r.bodySize <= 20480)
            val sent = Json.parseToJsonElement(r.body.readUtf8()).jsonObject
            assertEquals(JsonNull, sent.getValue("fingerprint")); assertEquals(filters.json(), sent.getValue("filters"))
            assertNull(r.getHeader("Cookie")); assertNull(r.getHeader("Origin")); assertEquals("no-store", r.getHeader("Cache-Control"))
            val failure = runCatching { f.api.register("+12025550123", "synthetic-password-only", "x".repeat(3000)) }.exceptionOrNull()
            assertTrue(failure is ApiFailure && failure.kind == FailureKind.INVALID_INPUT); assertEquals(1, f.server.requestCount)
        }
    }
    @Test fun defaultDisabledMakesNoRequestsAndDoesNotFollowRedirects() = runBlocking {
        Fixture().use { f ->
            val off = HttpsPhotoHouseApi(f.origin, f.client)
            assertTrue(runCatching { off.facets(token, "family-a", PhoneFacet.PEOPLE, 1, null) }.isFailure)
            assertTrue(runCatching { off.search(token, "family-a", DiscoveryExamples.binding, PhoneFilters(), 1, null) }.isFailure)
            assertEquals(0, f.server.requestCount)
            f.server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "https://other.invalid/"))
            val failure = runCatching { f.api.facets(token, "family-a", PhoneFacet.PEOPLE, 1, null) }.exceptionOrNull() as ApiFailure
            assertEquals(302, failure.status); assertEquals(1, f.server.requestCount)
        }
    }
    @Test fun denialBusyStaleAndOversizedBodiesStayClassified() = runBlocking {
        Fixture().use { f ->
            for (status in listOf(401, 403, 409, 429, 503)) {
                f.server.enqueue(MockResponse().setResponseCode(status).setHeader("Retry-After", "2").setBody("private body never displayed"))
                val failure = runCatching { f.api.facets(token, "family-a", PhoneFacet.PEOPLE, 1, null) }.exceptionOrNull() as ApiFailure
                assertEquals(status, failure.status); assertFalse(failure.toString().contains("private body"))
                if (status == 429) assertEquals(2000L, failure.retryAfterMillis)
            }
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setChunkedBody(" ".repeat(524289), 8192))
            val failure = runCatching { f.api.facets(token, "family-a", PhoneFacet.PEOPLE, 1, null) }.exceptionOrNull() as ApiFailure
            assertEquals(FailureKind.TOO_LARGE, failure.kind)
        }
    }
}
