package dev.photohouse.home

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import okhttp3.*
import okhttp3.mockwebserver.*
import okhttp3.tls.*
import okio.Buffer
import org.junit.*
import org.junit.Assert.*
import java.net.InetAddress

class TagDiscoveryTest {
    private lateinit var server: MockWebServer
    private lateinit var gateway: HttpsDiscoveryGateway
    private val examples by lazy { Json.parseToJsonElement(javaClass.getResource("/discovery-tags-v3.json")!!.readText()).jsonObject }
    @Before fun setup() {
        val cert = HeldCertificate.Builder().commonName("home.example").addSubjectAlternativeName("home.example").build()
        val tls = HandshakeCertificates.Builder().heldCertificate(cert).build()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        server = MockWebServer(); server.useHttps(tls.sslSocketFactory(), false); server.start(InetAddress.getLoopbackAddress(), 0)
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager)
            .dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress()) }).build()
        gateway = HttpsDiscoveryGateway(HomeOrigin.parse("https://home.example:${server.port}"), client, 3)
    }
    @After fun close() { server.shutdown() }
    private fun response(value: JsonElement) = MockResponse().setHeader("Content-Type", "application/json").setHeader("Cache-Control", "no-store").setBody(value.toString())
    private suspend fun snapshot(): DiscoverySnapshot {
        for (f in listOf("people", "tags", "locations")) server.enqueue(response(examples.getValue("facets_$f")))
        return gateway.load()
    }
    @Test fun queryAcrossFullRosterKeepsSelectedTagsAndOpensExactProducerMedia() = runBlocking {
        var s=snapshot();assertTrue(s.facetTotals.getValue(DiscoveryField.TAGS)>5000)
        assertEquals(50,s.tagMatches.size);assertEquals(50,s.options.tags.size)
        server.enqueue(response(examples.getValue("tags_page2")));s=gateway.more(s,DiscoveryField.TAGS)
        assertEquals(100,s.tagMatches.size)
        server.enqueue(response(examples.getValue("tags_lake")));s=gateway.findTags(s,"湖",setOf("301"))
        assertEquals(setOf("301","8999"),s.options.tags.map { it.id }.toSet())
        assertEquals(setOf("8999"),s.tagMatches);assertEquals(1,s.facetTotals[DiscoveryField.TAGS])
        assertFalse(DiscoveryField.TAGS in s.nextPages)
        val api=gateway.results(s,DiscoveryDraft(tags=setOf("8999"),tagsMatch=MatchMode.ALL))
        server.enqueue(response(examples.getValue("search_response")))
        val feed=api.feed(1);assertEquals(listOf(103),feed.items.map { it.id });assertTrue(feed.items.single().grid!!.onDemand)
        val requests=(1..6).map { server.takeRequest() }
        assertEquals("湖",requests[4].requestUrl!!.queryParameter("q"))
        assertEquals("/home/discovery/v3/search",requests[5].path)
        assertEquals(examples.getValue("search_request"),Json.parseToJsonElement(requests[5].body.readUtf8()))
        assertTrue(requests.all { it.getHeader("Cookie")==null && it.getHeader("Authorization")==null })
        // Returning to all tags retains a selected high-ID choice without counting it as a loaded match.
        server.enqueue(response(examples.getValue("facets_tags")))
        val all=gateway.findTags(s,"",setOf("8999"))
        assertEquals(51,all.options.tags.size);assertEquals(50,all.tagMatches.size)
    }
    @Test fun wrongQueryEchoCannotReplaceTheCurrentPicker() = runBlocking {
        val s=snapshot()
        server.enqueue(response(examples.getValue("tags_lake")))
        try { gateway.findTags(s,"park",emptySet());fail("Must reject query drift") }
        catch(e:HomeFailure) { assertEquals(HomeError.INVALID,e.kind) }
    }
    @Test fun staleRevisionAndLegacyVersionNeverFallback() = runBlocking {
        val s=snapshot()
        for (change in listOf("revision" to JsonPrimitive(99),"version" to JsonPrimitive(2))) {
            server.enqueue(response(JsonObject(examples.getValue("tags_lake").jsonObject+change)))
            try { gateway.findTags(s,"湖",emptySet());fail("Must reject stale or older response") }
            catch(e:HomeFailure) { assertEquals(HomeError.INVALID,e.kind) }
        }
        assertEquals(5,server.requestCount)
    }
    @Test fun invalidSelectionsAndOversizeQueryDoNotMakeRequests() = runBlocking {
        val s=snapshot()
        for ((q,selected) in listOf("湖".repeat(43) to emptySet(),"park" to setOf("99999"))) {
            try { gateway.findTags(s,q,selected);fail("Must reject invalid input") }
            catch(e:HomeFailure) { assertEquals(HomeError.INVALID,e.kind) }
        }
        assertEquals(3,server.requestCount)
    }
    @Test fun rosterBeyondVersionedBoundIsRefused() = runBlocking {
        val v=examples.getValue("facets_tags").jsonObject
        try { DiscoveryWire.facets(JsonObject(v+("total" to JsonPrimitive(10001))).toString().toByteArray(),DiscoveryField.TAGS,1,version=3);fail("Must bound total") }
        catch(e:HomeFailure) { assertEquals(HomeError.INVALID,e.kind) }
    }
}
