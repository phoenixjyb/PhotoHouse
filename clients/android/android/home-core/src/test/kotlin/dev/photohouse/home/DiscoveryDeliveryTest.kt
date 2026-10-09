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

class DiscoveryDeliveryTest {
    private lateinit var server: MockWebServer
    private lateinit var gateway: HttpsDiscoveryGateway
    private val examples by lazy { Json.parseToJsonElement(javaClass.getResource("/discovery-delivery-v2.json")!!.readText()).jsonObject }
    @Before fun setup() {
        val cert = HeldCertificate.Builder().commonName("home.example").addSubjectAlternativeName("home.example").build()
        val tls = HandshakeCertificates.Builder().heldCertificate(cert).build()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        server = MockWebServer(); server.useHttps(tls.sslSocketFactory(), false); server.start(InetAddress.getLoopbackAddress(), 0)
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager)
            .dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress()) }).build()
        gateway = HttpsDiscoveryGateway(HomeOrigin.parse("https://home.example:${server.port}"), client, 2)
    }
    @After fun close() { server.shutdown() }
    private fun response(value: JsonElement) = MockResponse().setHeader("Content-Type", "application/json").setHeader("Cache-Control", "no-store").setBody(value.toString())
    private suspend fun snapshot(): DiscoverySnapshot {
        for (f in listOf("people", "tags", "locations")) server.enqueue(response(examples.getValue("facets_$f")))
        return gateway.load()
    }
    @Test fun actualProducerResultsKeepOnDemandOriginalAndBothVideoKinds() = runBlocking {
        val snapshot = snapshot();val api = gateway.results(snapshot, DiscoveryDraft())
        server.enqueue(response(examples.getValue("search_response")))
        val feed = api.feed(1);assertEquals(3, feed.version);assertEquals(3, api.catalogVersion)
        assertFalse(api.browseEnabled);assertFalse(api.retryRevisionChanges)
        val photo = feed.items.single { it.id == 103 };assertTrue(photo.grid!!.onDemand);assertNotNull(photo.original)
        assertTrue(feed.items.single { it.id == 104 }.video!!.direct)
        assertFalse(feed.items.single { it.id == 102 }.video!!.direct)
        val bytes = javaClass.getResource("/discovery-delivery-photo.jpg")!!.readBytes()
        repeat(2) { server.enqueue(MockResponse().setHeader("Content-Type", "image/jpeg").setHeader("Cache-Control", "no-store").setBody(Buffer().write(bytes))) }
        assertArrayEquals(bytes, api.preview(photo, Variant.GRID, feed.revision))
        assertArrayEquals(bytes, api.original(photo, feed.revision))
        val requests=(1..6).map { server.takeRequest() }
        assertTrue(requests.take(3).all { it.path!!.startsWith("/home/discovery/v2/facets") })
        assertEquals("/home/discovery/v2/search", requests[3].path)
        assertEquals("/home/v3/assets/103/preview?variant=grid&revision=1", requests[4].path)
        assertEquals("/home/v3/assets/103/original?revision=1", requests[5].path)
        assertTrue(requests.all { it.getHeader("Authorization")==null && it.getHeader("Cookie")==null })
    }
    @Test fun oldVersionNeverSilentlyFallsBack() = runBlocking {
        val old=examples.getValue("facets_people").jsonObject.let { JsonObject(it+("version" to JsonPrimitive(1))) }
        server.enqueue(response(old))
        try { gateway.load();fail("Must reject old version") } catch(e:HomeFailure) { assertEquals(HomeError.INVALID,e.kind) }
        assertEquals(1,server.requestCount)
    }
    @Test fun changedRevisionOrV2MediaInV3SearchIsRejected() = runBlocking {
        val snapshot=snapshot();val api=gateway.results(snapshot,DiscoveryDraft())
        val value=examples.getValue("search_response").jsonObject
        server.enqueue(response(JsonObject(value+("catalog_revision" to JsonPrimitive(99)))))
        try { api.feed(1);fail("Must reject drift") } catch(e:HomeFailure) { assertEquals(HomeError.INVALID,e.kind) }
        server.enqueue(response(Json.parseToJsonElement(value.toString().replace("/home/v3/","/home/v2/"))))
        try { api.feed(1);fail("Must reject older media route") } catch(e:HomeFailure) { assertEquals(HomeError.INVALID,e.kind) }
    }
}
