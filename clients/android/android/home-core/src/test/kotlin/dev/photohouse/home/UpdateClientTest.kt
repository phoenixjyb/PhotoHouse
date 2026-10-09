package dev.photohouse.home

import kotlinx.coroutines.runBlocking
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import okio.Buffer
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.io.File
import java.net.InetAddress
import java.security.MessageDigest

class UpdateClientTest {
    private lateinit var server: MockWebServer
    private lateinit var api: HttpsUpdateClient
    private val signer = "a".repeat(64)
    private val apk = "synthetic-apk-bytes".toByteArray()
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    @Before fun setup() {
        val certificate = HeldCertificate.Builder().commonName("updates.example").addSubjectAlternativeName("updates.example").build()
        val serverTls = HandshakeCertificates.Builder().heldCertificate(certificate).build()
        val clientTls = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
        server = MockWebServer(); server.useHttps(serverTls.sslSocketFactory(), false); server.start(InetAddress.getLoopbackAddress(), 0)
        val client = OkHttpClient.Builder().sslSocketFactory(clientTls.sslSocketFactory(), clientTls.trustManager)
            .dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress()) }).build()
        api = HttpsUpdateClient(HomeOrigin.parse("https://updates.example:${server.port}"), client)
    }

    @After fun close() { server.shutdown() }

    private fun feed(data: ByteArray = apk): ByteArray {
        val digest = sha(data)
        return """{"schema_version":1,"channel":"phone","package_name":"dev.photohouse.connected","version_code":26,"version_name":"1.2.3","bytes":${data.size},"sha256":"$digest","apk_url":"/updates/v1/phone/$digest.apk","signing_cert_sha256":"$signer"}""".toByteArray()
    }

    @Test fun checksTrustedFeedAndDownloadsOnlyBytesMatchingDeclaredHash() = runBlocking {
        server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setHeader("Cache-Control", "no-store").setBody(Buffer().write(feed())))
        val offer = api.check("phone", "dev.photohouse.connected", 25, signer)
        assertEquals("/updates/v1/phone/${sha(apk)}.apk", offer.apkPath)
        val manifestRequest = server.takeRequest()
        assertEquals("/updates/v1/phone", manifestRequest.path)
        assertEquals("no-store", manifestRequest.getHeader("Cache-Control"))
        assertNull(manifestRequest.getHeader("Authorization")); assertNull(manifestRequest.getHeader("Cookie"))

        server.enqueue(MockResponse().setBody(Buffer().write(apk)))
        val destination = File.createTempFile("photohouse-update", ".apk").apply { delete() }
        try {
            api.download(offer, destination)
            assertArrayEquals(apk, destination.readBytes())
            assertEquals("/updates/v1/phone/${sha(apk)}.apk", server.takeRequest().path)
        } finally { destination.delete() }
    }

    @Test fun corruptArtifactIsDeletedAndRedirectsAreRejected() = runBlocking {
        server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setHeader("Cache-Control", "no-store").setBody(Buffer().write(feed())))
        val offer = api.check("phone", "dev.photohouse.connected", 25, signer)
        server.enqueue(MockResponse().setBody("tampered"))
        val destination = File.createTempFile("photohouse-update", ".apk").apply { delete() }
        try {
            try { api.download(offer, destination); fail("bad APK bytes accepted") } catch (_: HomeFailure) { }
            assertFalse(destination.exists())
            assertFalse(File(destination.parentFile, destination.name + ".part").exists())
        } finally { destination.delete() }

        server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "https://attacker.example/apk"))
        try { api.check("phone", "dev.photohouse.connected", 25, signer); fail("redirect accepted") } catch (_: HomeFailure) { }
    }
}
