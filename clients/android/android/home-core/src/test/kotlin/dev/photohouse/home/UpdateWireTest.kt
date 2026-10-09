package dev.photohouse.home

import org.junit.Assert.*
import org.junit.Test

class UpdateWireTest {
    private val origin = HomeOrigin.parse("https://updates.example")
    private val signer = "a".repeat(64)
    private val apkHash = "b".repeat(64)

    private fun feed(channel: String = "phone", packageName: String = "dev.photohouse.connected",
                    version: Int = 26, cert: String = signer, url: String = "/updates/v1/$channel/$apkHash.apk") =
        """{"schema_version":1,"channel":"$channel","package_name":"$packageName","version_code":$version,"version_name":"1.2.3","bytes":2048,"sha256":"$apkHash","apk_url":"$url","signing_cert_sha256":"$cert"}""".toByteArray()

    private fun parse(bytes: ByteArray = feed()) = UpdateWire.parse(bytes, origin, "phone", "dev.photohouse.connected", 25, signer)

    @Test fun acceptsExactHigherVersionAndExpectedSameOriginArtifact() {
        val offer = parse()
        assertEquals(26, offer.versionCode)
        assertEquals("/updates/v1/phone/$apkHash.apk", offer.apkPath)
        assertEquals(2048, offer.bytes)
    }

    @Test fun rejectsWrongChannelPackageNonIncreasingVersionOrSigner() {
        for (bytes in listOf(feed(channel = "tv"), feed(packageName = "dev.photohouse.connected.qa"),
            feed(version = 25), feed(cert = "c".repeat(64)))) {
            try { parse(bytes); fail("unsafe update metadata accepted") } catch (_: HomeFailure) { }
        }
    }

    @Test fun rejectsCrossOriginWrongPathAndUnknownFields() {
        for (bytes in listOf(feed(url = "https://attacker.example/updates/v1/phone/$apkHash.apk"),
            feed(url = "/updates/v1/phone/${"c".repeat(64)}.apk"),
            feed().decodeToString().replace("\"schema_version\":1,", "\"extra\":true,\"schema_version\":1,").toByteArray(),
            feed().decodeToString().replace("\"channel\":\"phone\",", "\"channel\":\"tv\",\"channel\":\"phone\",").toByteArray())) {
            try { parse(bytes); fail("unsafe update metadata accepted") } catch (_: HomeFailure) { }
        }
    }
}
