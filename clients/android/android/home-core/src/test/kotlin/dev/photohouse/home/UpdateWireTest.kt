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

    @Test fun rejectsWrongChannelPackageOrSigner() {
        for (bytes in listOf(feed(channel = "tv"), feed(packageName = "dev.photohouse.connected.qa"),
            feed(cert = "c".repeat(64)))) {
            try { parse(bytes); fail("unsafe update metadata accepted") } catch (_: HomeFailure) { }
        }
    }

    @Test fun equalAndOlderFullyValidFeedsHaveTypedAlreadyCurrentResult() {
        for (version in listOf(25, 24)) {
            try {
                parse(feed(version = version))
                fail("non-newer feed accepted as an update")
            } catch (e: UpdateNotNewerException) {
                assertEquals(25L, e.installedVersionCode)
                assertEquals(version.toLong(), e.offeredVersionCode)
            }
        }
    }

    @Test fun oldVersionDoesNotMaskMalformedOrNonmatchingFeed() {
        val oldVersionWithWrongChannel = feed(channel = "tv", version = 24)
        val oldVersionWithWrongSigner = feed(version = 24, cert = "c".repeat(64))
        val oldVersionWithWrongUrl = feed(version = 24, url = "https://attacker.example/updates/v1/phone/$apkHash.apk")
        val malformedOldVersion = feed(version = 24).decodeToString().replace("\"version_name\":\"1.2.3\",", "\"version_name\":broken,").toByteArray()
        for (bytes in listOf(oldVersionWithWrongChannel, oldVersionWithWrongSigner, oldVersionWithWrongUrl, malformedOldVersion)) {
            try { parse(bytes); fail("invalid old feed accepted") } catch (_: HomeFailure) { }
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
