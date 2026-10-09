package dev.photohouse.home

import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import okhttp3.*
import okhttp3.mockwebserver.*
import okhttp3.tls.*
import org.junit.*
import org.junit.Assert.*
import java.net.InetAddress
import java.util.concurrent.TimeUnit

class DiscoveryHttpTest {
    private lateinit var server: MockWebServer
    private lateinit var gateway: HttpsDiscoveryGateway
    @Before fun setup() {
        val certificate = HeldCertificate.Builder().commonName("home.example").addSubjectAlternativeName("home.example").build()
        val tls = HandshakeCertificates.Builder().heldCertificate(certificate).build()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
        server = MockWebServer(); server.useHttps(tls.sslSocketFactory(), false); server.start(InetAddress.getLoopbackAddress(), 0)
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager)
            .dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress()) }).build()
        gateway = HttpsDiscoveryGateway(HomeOrigin.parse("https://home.example:${server.port}"), client)
    }
    @After fun close() { server.shutdown() }
    private fun response(value: JsonElement) = MockResponse().setHeader("Content-Type", "application/json")
        .setHeader("Cache-Control", "no-store").setBody(value.toString())
    private fun enqueueFacets(people: JsonObject = discoveryFacet("people")) {
        for (v in listOf(people, discoveryFacet("tags"), discoveryFacet("locations"))) server.enqueue(response(v).setHeader("Set-Cookie", "ignored=1"))
    }
    private suspend fun failure(kind: HomeError, action: suspend () -> Unit): HomeFailure {
        try { action(); fail("Expected failure") } catch (e: HomeFailure) { assertEquals(kind, e.kind); return e }
        error("Expected failure")
    }
    @Test fun facetsAndPostSearchBindRevisionsAndNeverSendNamesCookiesOrCredentialsInUrl() = runBlocking {
        enqueueFacets(); val snapshot = gateway.load()
        assertEquals(listOf("202", "201"), snapshot.options.pinnedPeople)
        val api = gateway.results(snapshot, DiscoveryDraft(people = setOf("202"), text = " family "))
        assertEquals(2, api.catalogVersion); assertFalse(api.retryRevisionChanges)
        server.enqueue(response(discoveryJson("search-response")))
        assertEquals(103, api.feed(1).items.single().id)
        val requests = (1..4).map { server.takeRequest() }
        assertEquals("/home/discovery/v1/facets?facet=people&page=1&page_size=50", requests[0].path)
        assertEquals("/home/discovery/v1/facets?facet=tags&page=1&page_size=50&revision=7", requests[1].path)
        assertEquals("/home/discovery/v1/facets?facet=locations&page=1&page_size=50&revision=7", requests[2].path)
        assertEquals("/home/discovery/v1/search", requests[3].path); assertEquals("POST", requests[3].method)
        assertEquals("application/json", requests[3].getHeader("Content-Type"))
        val body = Json.parseToJsonElement(requests[3].body.readUtf8()).jsonObject
        assertEquals(JsonPrimitive(7), body["revision"])
        assertEquals(JsonPrimitive("family"), body.getValue("filters").jsonObject["caption"])
        assertEquals(JsonArray(listOf(JsonPrimitive(202))), body.getValue("filters").jsonObject.getValue("people").jsonObject["ids"])
        for (r in requests) {
            for (h in listOf("Cookie", "Authorization")) assertNull(r.getHeader(h))
            assertEquals("identity", r.getHeader("Accept-Encoding")); assertEquals("no-store", r.getHeader("Cache-Control"))
        }
    }
    @Test fun morePreservesPinnedOrderAndRejectsTotalOrderingAndBindingDrift() = runBlocking {
        val base = discoveryFacet("people")
        val adult = base.getValue("items").jsonArray[0].jsonObject
        val firstItems = (1..49).map { JsonObject(adult + ("id" to JsonPrimitive(it))) } + adult
        val first = JsonObject(base + mapOf("total" to JsonPrimitive(51), "has_more" to JsonPrimitive(true), "items" to JsonArray(firstItems)))
        enqueueFacets(first); val snapshot = gateway.load()
        assertEquals(2, snapshot.nextPages[DiscoveryField.PEOPLE]); assertEquals(51, snapshot.options.people.size)
        val last = JsonObject(base + mapOf("page" to JsonPrimitive(2), "total" to JsonPrimitive(51),
            "items" to JsonArray(listOf(base.getValue("items").jsonArray[1]))))
        server.enqueue(response(last)); val completed = gateway.more(snapshot, DiscoveryField.PEOPLE)
        assertFalse(DiscoveryField.PEOPLE in completed.nextPages); assertEquals(51, completed.options.people.size)
        assertEquals(listOf("202", "201"), completed.options.pinnedPeople)
        val requests = (1..4).map { server.takeRequest() }
        assertEquals("/home/discovery/v1/facets?facet=people&page=2&page_size=50&revision=7", requests.last().path)
        server.enqueue(response(JsonObject(last + ("items" to JsonArray(listOf(adult))))))
        failure(HomeError.INVALID) { gateway.more(snapshot, DiscoveryField.PEOPLE) }
        server.enqueue(response(JsonObject(last + mapOf("total" to JsonPrimitive(50), "items" to JsonArray(emptyList())))))
        failure(HomeError.INVALID) { gateway.more(snapshot, DiscoveryField.PEOPLE) }; Unit
    }
    @Test fun searchFingerprintTotalAndRevisionAreStableAcrossPagesAndRefresh() = runBlocking {
        val api = gateway.results(discoverySnapshot(), DiscoveryDraft())
        failure(HomeError.INVALID) { api.feed(2, 1) }; assertEquals(0, server.requestCount)
        val raw = discoveryJson("search-response")
        server.enqueue(response(raw)); api.feed(1)
        val after = JsonObject(raw + mapOf("page" to JsonPrimitive(2), "items" to JsonArray(emptyList())))
        server.enqueue(response(after)); assertTrue(api.feed(2, 1).items.isEmpty())
        server.enqueue(response(JsonObject(raw + ("filter_fingerprint" to JsonPrimitive("0".repeat(64))))))
        failure(HomeError.INVALID) { api.feed(1) }
        server.enqueue(response(JsonObject(raw + mapOf("total" to JsonPrimitive(0), "items" to JsonArray(emptyList())))))
        failure(HomeError.INVALID) { api.feed(1) }
        server.enqueue(response(JsonObject(raw + ("revision" to JsonPrimitive(8)))))
        failure(HomeError.INVALID) { api.feed(1) }
        assertEquals(5, server.requestCount)
    }
    @Test fun denialChangedBusyUnavailableAndRedirectDoNotFallback() = runBlocking {
        for ((code, kind) in listOf(403 to HomeError.DENIED, 409 to HomeError.CHANGED, 429 to HomeError.BUSY,
            503 to HomeError.UNAVAILABLE, 302 to HomeError.INVALID, 422 to HomeError.INVALID)) {
            server.enqueue(MockResponse().setResponseCode(code).setHeader("Retry-After", "2").setHeader("Location", "https://other.example"))
            val e = failure(kind) { gateway.load() }
            if (code == 429) assertEquals(2000L, e.retryAfterMillis)
        }
        assertEquals(6, server.requestCount)
    }
    @Test fun missingNoStoreEncodingWrongTypeAndOversizedBodiesAreRejected() = runBlocking {
        val raw = discoveryFacet("people")
        for (r in listOf(response(raw).removeHeader("Cache-Control"), response(raw).setHeader("Content-Encoding", "gzip"),
            response(raw).setHeader("Content-Type", "text/html"), response(raw).addHeader("Content-Type", "application/json"),
            response(raw).setBody(" ".repeat(HomeLimits.JSON + 1)), response(raw).setChunkedBody(" ".repeat(HomeLimits.JSON + 1), 8192))) {
            server.enqueue(r); failure(HomeError.INVALID) { gateway.load() }
        }
    }
    @Test fun cancellationStopsFacetSequenceAndSearchWithoutPublishingLateResponse() = runBlocking {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
        val load = async(Dispatchers.Default) { gateway.load() }
        assertNotNull(withContext(Dispatchers.IO) { server.takeRequest(5, TimeUnit.SECONDS) })
        load.cancelAndJoin(); assertTrue(load.isCancelled); assertEquals(1, server.requestCount)
        val api = gateway.results(discoverySnapshot(), DiscoveryDraft())
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
        val search = async(Dispatchers.Default) { api.feed(1) }
        assertNotNull(withContext(Dispatchers.IO) { server.takeRequest(5, TimeUnit.SECONDS) })
        search.cancelAndJoin(); assertTrue(search.isCancelled); assertEquals(2, server.requestCount)
    }
    @Test fun untrustedTlsCannotReachDiscoveryResponse() = runBlocking {
        val client = OkHttpClient.Builder().dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress()) }).build()
        val untrusted = HttpsDiscoveryGateway(HomeOrigin.parse("https://home.example:${server.port}"), client)
        failure(HomeError.TLS) { untrusted.load() }; Unit
    }
}
