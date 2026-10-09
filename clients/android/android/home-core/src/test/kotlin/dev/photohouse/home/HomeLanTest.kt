package dev.photohouse.home

import kotlinx.coroutines.runBlocking
import okhttp3.*
import okhttp3.mockwebserver.*
import okhttp3.tls.*
import org.junit.Test
import org.junit.Assert.*
import java.net.InetAddress
import java.net.Proxy
import java.net.UnknownHostException

class HomeLanTest {
    @Test fun canonicalPrivateAddressesOnlyWithoutResolution() {
        for (value in listOf("10.1.2.3", "172.16.2.3", "172.31.255.254", "192.168.40.10"))
            assertEquals(value, HomeLanAddress.parse(value).address.hostAddress)
        for (value in listOf("", " 192.168.40.10", "192.168.40.10 ", "192.168.040.10", "192.168.40.256", "192.168.40", "192.168.40.10:443",
            "home.example", "127.0.0.1", "0.0.0.0", "169.254.1.1", "8.8.8.8", "172.15.1.1", "172.32.1.1", "::1", "::ffff:192.168.40.10")) {
            try { HomeLanAddress.parse(value); fail("Invalid address accepted: $value") } catch (_: IllegalArgumentException) { }
        }
    }
    @Test fun mappingIsExactAndNeverFallsBackToAnotherHost() {
        val address = HomeLanAddress.parse("192.168.40.10")
        val dns = HomeLanDns("home.example", address.address)
        assertEquals(listOf(address.address), dns.lookup("home.example"))
        try { dns.lookup("other.example"); fail("Unexpected host resolved") } catch (_: UnknownHostException) { }
        assertFalse(dns.toString().contains("192.168")); assertFalse(address.toString().contains("192.168"))
    }
    @Test fun mappedClientUsesDirectRoutingAndDefaultTrustChecks() {
        val client = homeLanClient(HomeOrigin.parse("https://home.example"), HomeLanAddress.parse("192.168.40.10"))
        val defaults = OkHttpClient()
        assertEquals(Proxy.NO_PROXY, client.proxy)
        assertEquals(defaults.hostnameVerifier, client.hostnameVerifier)
        assertEquals(defaults.x509TrustManager?.acceptedIssuers?.toList(), client.x509TrustManager?.acceptedIssuers?.toList())
        assertEquals("192.168.40.10", client.dns.lookup("home.example").single().hostAddress)
    }
    private fun tlsRequest(certificateHost: String, trustFixture: Boolean, success: Boolean) = runBlocking {
        val cert = HeldCertificate.Builder().commonName(certificateHost).addSubjectAlternativeName(certificateHost).build()
        val serverTls = HandshakeCertificates.Builder().heldCertificate(cert).build()
        val server = MockWebServer()
        server.useHttps(serverTls.sslSocketFactory(), false)
        server.start(InetAddress.getLoopbackAddress(), 0)
        try {
            server.enqueue(MockResponse().setHeader("Cache-Control", "no-store").setHeader("Content-Type", "application/json").setBody(String(resource("feed.json"))))
            // Friend-only test mapping targets the loopback fixture. Production parse rejects loopback.
            val builder = OkHttpClient.Builder().dns(HomeLanDns("home.example", InetAddress.getLoopbackAddress())).proxy(Proxy.NO_PROXY)
            if (trustFixture) {
                val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
                builder.sslSocketFactory(trust.sslSocketFactory(), trust.trustManager)
            }
            val api = HttpsHomeApi(HomeOrigin.parse("https://home.example:${server.port}"), builder.build())
            if (success) {
                assertEquals(101, api.feed(1).items.single().id)
                val request = server.takeRequest()
                assertEquals("home.example:${server.port}", (request.getHeader("Host") ?: request.getHeader(":authority")))
                assertNotNull(request.handshake)
                assertNull(request.getHeader("Authorization")); assertNull(request.getHeader("Cookie"))
            } else {
                try { api.feed(1); fail("TLS failure accepted") } catch (e: HomeFailure) { assertEquals(HomeError.TLS, e.kind) }
                assertEquals(0, server.requestCount)
            }
        } finally { server.shutdown() }
    }
    @Test fun mappedConnectionRetainsHttpsHostname() = tlsRequest("home.example", true, true)
    @Test fun mappedConnectionRejectsWrongCertificateHostname() = tlsRequest("other.example", true, false)
    @Test fun mappedConnectionRejectsUntrustedCertificate() = tlsRequest("home.example", false, false)
}
