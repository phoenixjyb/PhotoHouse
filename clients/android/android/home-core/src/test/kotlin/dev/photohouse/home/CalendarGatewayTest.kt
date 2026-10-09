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

class CalendarGatewayTest {
    private lateinit var server: MockWebServer
    private lateinit var gateway: HttpsDiscoveryGateway
    private val examples by lazy { Json.parseToJsonElement(javaClass.getResource("/discovery-tags-v3.json")!!.readText()).jsonObject }
    private val calendarExamples by lazy { Json.parseToJsonElement(javaClass.getResource("/calendar-v1.json")!!.readText()).jsonObject }
    @Before fun setup() {
        val cert = HeldCertificate.Builder().commonName("home.example").addSubjectAlternativeName("home.example").build()
        val tls = HandshakeCertificates.Builder().heldCertificate(cert).build()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        server = MockWebServer(); server.useHttps(tls.sslSocketFactory(), false); server.start(InetAddress.getLoopbackAddress(), 0)
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager)
            .dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress()) }).build()
        gateway = HttpsDiscoveryGateway(HomeOrigin.parse("https://home.example:${server.port}"), client, 3, calendarEnabled=true)
    }
    @After fun close() { server.shutdown() }
    private fun response(value: JsonElement) = MockResponse().setHeader("Content-Type", "application/json").setHeader("Cache-Control", "no-store").setBody(value.toString())
    private suspend fun snapshot(): DiscoverySnapshot {
        for (f in listOf("people", "tags", "locations")) server.enqueue(response(examples.getValue("facets_$f")))
        return gateway.load()
    }
    @Test fun actualProducerCalendarDrillsDownAndUsesExistingMedia() = runBlocking {
        val s=snapshot()
        server.enqueue(response(calendarExamples.getValue("years")));val years=gateway.calendar(s,CalendarRequest())
        assertEquals(listOf("2026","2025"),years.buckets.map { it.key });assertEquals(1,years.undated)
        server.enqueue(response(calendarExamples.getValue("months")));val months=gateway.calendar(s,years.buckets.first().child()!!)
        assertEquals(CalendarRequest(2026),months.request)
        server.enqueue(response(calendarExamples.getValue("days")));val days=gateway.calendar(s,CalendarRequest(2026,1))
        val day=days.buckets.single();assertEquals("2026-01-02",day.from);assertNull(day.child())
        val draft=DiscoveryDraft(people=setOf("202")).copy(from=day.from,through=day.through)
        assertNull(draft.issue(s.options))
        val api=gateway.calendarCovers(s,years);val feed=api.feed(1)
        val photo=feed.items.first();val bytes=javaClass.getResource("/discovery-delivery-photo.jpg")!!.readBytes()
        server.enqueue(MockResponse().setHeader("Content-Type","image/jpeg").setHeader("Cache-Control","no-store").setBody(Buffer().write(bytes)))
        assertArrayEquals(bytes,api.preview(photo,Variant.GRID,s.catalogRevision))
        val requests=(1..7).map { server.takeRequest() }
        assertEquals("2026",requests[5].requestUrl!!.queryParameter("year"));assertEquals("1",requests[5].requestUrl!!.queryParameter("month"))
        assertTrue(requests[6].path!!.startsWith("/home/v3/assets/"))
        assertTrue(requests.all { it.getHeader("Authorization")==null && it.getHeader("Cookie")==null })
    }
    @Test fun bindingDriftAndMalformedCountsAreRefused() = runBlocking {
        val s=snapshot();val v=calendarExamples.getValue("years").jsonObject
        for(change in listOf("binding" to JsonPrimitive("0".repeat(64)),"dated_assets" to JsonPrimitive(999),"year" to JsonPrimitive(2026))) {
            server.enqueue(response(JsonObject(v+change)))
            try {gateway.calendar(s,CalendarRequest());fail("Must reject metadata drift")}catch(e:HomeFailure) {assertEquals(HomeError.INVALID,e.kind)}
        }
    }
    @Test fun coversAndRequestsStayBoundedAndDateRangesHandleLeapYears() = runBlocking {
        val s=snapshot()
        for(r in listOf(CalendarRequest(month=2),CalendarRequest(2026,13),CalendarRequest(page=0))) {
            try {gateway.calendar(s,r);fail("Must reject invalid request")}catch(e:HomeFailure) {assertEquals(HomeError.INVALID,e.kind)}
        }
        assertEquals(3,server.requestCount)
        assertEquals("2024-02-29",CalendarRequest(2024,2).range()!!.second)
        assertEquals("2025-02-28",CalendarRequest(2025,2).range()!!.second)
        assertEquals(CalendarRequest(2024),CalendarRequest(2024,2).parent())
    }
}
