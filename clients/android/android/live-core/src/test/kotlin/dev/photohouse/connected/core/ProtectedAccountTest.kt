package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class ProtectedAccountTest {
    private val nullProfile = """{"account_id":"synthetic-account","phone_login":"+12025550123","display_name":null,"memberships":[]}"""

    @Test fun protectedFormDefaultsChinaButLeavesWireAndLegacyAdmissionStrict() {
        assertEquals("+8613800138000", Admission.phoneFromForm("138 0013 8000", true))
        assertEquals("+8613800138000", Admission.phoneFromForm("+86 (138) 0013-8000", true))
        assertEquals("+12025550123", Admission.phoneFromForm("+1 (202) 555-0123", true))
        assertEquals("+12025550123", Admission.phoneFromForm("+12025550123", false))
        for (phone in listOf("", "+86", "123", "138001380000", "1380013800a", "１３８００１３８０００"))
            assertThrows(IllegalArgumentException::class.java) { Admission.phoneFromForm(phone, true) }
        assertThrows(IllegalArgumentException::class.java) { Admission.phoneFromForm("13800138000", false) }
        assertThrows(IllegalArgumentException::class.java) { Admission.phone("13800138000") }
        val phone = Admission.phoneFromForm("13800138000", true)
        val wire = Json.parseToJsonElement(ProtectedAccountWire.registration(phone, "synthetic password", "synthetic-invite", "Synthetic member")).jsonObject
        assertEquals("+8613800138000", wire.getValue("phone").jsonPrimitive.content)
        assertEquals("native", wire.getValue("transport").jsonPrimitive.content)
    }

    @Test fun namesMatchBackendWhitespaceAndCodepointRulesWithoutPasswordChanges() {
        assertEquals("小溪 Jane", Admission.displayName(" \t小溪\u00a0\u0085Jane\n "))
        for (space in listOf('\u001c', '\u1680', '\u2007', '\u2028', '\u202f', '\u3000'))
            assertEquals("A B", Admission.displayName("A${space}B"))
        assertEquals("😀".repeat(64), Admission.displayName("😀".repeat(64)))
        for (name in listOf("", " \u00a0\t", "x".repeat(65), "😀".repeat(65), "a\u0000b", "a\u007fb", "\uD800"))
            assertThrows(IllegalArgumentException::class.java) { Admission.displayName(name) }
        val request = Json.parseToJsonElement(ProtectedAccountWire.registration("+1 (202) 555-0123", " 123456 ", "invite", " A  B ")).jsonObject
        assertEquals(" 123456 ", request.getValue("password").jsonPrimitive.content)
        assertEquals("A B", request.getValue("name").jsonPrimitive.content)
        assertEquals("+12025550123", request.getValue("phone").jsonPrimitive.content)
    }

    @Test fun migratedNullNameWorksWithoutRelaxingProfileShapeOrFrozenWire() {
        val session = ProtectedAccountWire.session(nullProfile)
        assertNull(session.displayName)
        val named = ProtectedAccountWire.session(nullProfile.replace("null", "\"Jane\""))
        assertEquals("Jane", named.displayName)
        assertEquals("synthetic-account", named.account_id)
        val legacy = nullProfile.replace("\"display_name\":null,", "")
        assertEquals(session, Wire.json.decodeFromString(Session.serializer(), legacy))
        assertFalse(Wire.json.encodeToString(Session.serializer(), named).contains("Jane"))
        assertThrows(IllegalArgumentException::class.java) { ProtectedAccountWire.session(legacy) }
        for (value in listOf("12", "{}", "true", "\" \"", "\" Jane \"", "\"" + "x".repeat(65) + "\""))
            assertThrows(IllegalArgumentException::class.java) { ProtectedAccountWire.session(nullProfile.replace("null", value)) }
        assertThrows(IllegalArgumentException::class.java) { ProtectedAccountWire.session(nullProfile.replace("\"memberships\":[]", "\"memberships\":[],\"extra\":true")) }
    }

    @Test fun duplicateKeysAndInvalidUnicodeAreRefused() {
        val duplicate = nullProfile.replace("\"display_name\":null", "\"display_name\":\"Jane\",\"display_name\":null")
        assertTrue(runCatching { ProtectedAccountWire.session(duplicate) }.isFailure)
        val escapedDuplicate = nullProfile.replace("\"display_name\":null", "\"display_name\":null,\"display_\\u006eame\":null")
        assertTrue(runCatching { ProtectedAccountWire.session(escapedDuplicate) }.isFailure)
        assertTrue(runCatching { ProtectedAccountWire.session(byteArrayOf(0xC3.toByte(), 0x28)) }.isFailure)
        assertTrue(runCatching { ProtectedAccountWire.session(nullProfile.replace("null", "\"\\uD800\"")) }.isFailure)
        assertThrows(IllegalArgumentException::class.java) { ProtectedAccountWire.registration("+12025550123", "12345678", "\uD800", "Jane") }
    }

    @Test fun sessionMembershipsAreNotLimitedToDiscoveryPageSize() {
        val memberships = (1..101).map { Membership("library-$it", "approved", "viewer", 1, null, 0, true) }
        val legacy = Wire.json.encodeToJsonElement(Session.serializer(), Session("account", "+12025550123", memberships)).jsonObject
        val current = JsonObject(legacy + ("display_name" to JsonNull))
        assertEquals(101, ProtectedAccountWire.session(current.toString()).memberships.size)
    }

    private class Fixture : AutoCloseable {
        private val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        private val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        private val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        val api = HttpsPhotoHouseApi(TrustedOrigin.parse("https://localhost:${server.port}"), client, protectedNativeV2Enabled = true)
        override fun close() { server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll() }
    }

    @Test fun capturedRegistrationAndNamedSessionsReplayThroughActualHttpsAdapter() = runBlocking {
        val cases = javaClass.classLoader!!.getResourceAsStream("protected-native-contract/cases.json")!!.use {
            Json.parseToJsonElement(it.reader().readText()).jsonObject.getValue("cases").jsonArray
        }
        Fixture().use { f ->
            val registration = cases.single { it.jsonObject.getValue("id").jsonPrimitive.content == "invited_registration_8" }.jsonObject
            val request = registration.getValue("request").jsonObject.getValue("json").jsonObject
            val response = registration.getValue("response").jsonObject
            f.server.enqueue(MockResponse().setResponseCode(response.getValue("status").jsonPrimitive.content.toInt())
                .setHeader("Content-Type", "application/json").setBody(response.getValue("body").toString()))
            fun field(name: String) = request.getValue(name).jsonPrimitive.content
            val token = Bearer.from(f.api.registerNamed(field("phone"), field("password"), field("code"), field("name")))
            val sent = f.server.takeRequest()
            assertEquals("/auth/register", sent.path)
            assertEquals(request, Json.parseToJsonElement(sent.body.readUtf8()))
            assertNull(sent.getHeader("Cookie")); assertNull(sent.getHeader("Origin")); assertNull(sent.getHeader("Authorization"))
            for (id in listOf("invited_viewer_session", "accepted_second_library_session", "revoked_session_still_authenticated")) {
                val body = cases.single { it.jsonObject.getValue("id").jsonPrimitive.content == id }.jsonObject
                    .getValue("response").jsonObject.getValue("body").toString()
                f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(body))
                val profile = f.api.session(token)
                assertEquals("Synthetic Member", profile.displayName)
                if (id.startsWith("revoked")) assertTrue(profile.memberships.all { !it.available })
                val read = f.server.takeRequest()
                assertEquals("/auth/session", read.path); assertEquals(token.header(), read.getHeader("Authorization"))
            }
        }
    }

    @Test fun nullNameSessionIsAcceptedAndMalformedOrUnauthorizedSessionsFailClosed() = runBlocking {
        Fixture().use { f ->
            val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(nullProfile))
            assertNull(f.api.session(token).displayName)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(nullProfile.replace("null", "false")))
            assertEquals(FailureKind.INVALID_RESPONSE, (runCatching { f.api.session(token) }.exceptionOrNull() as ApiFailure).kind)
            for (status in listOf(401,403,429,503)) {
                f.server.enqueue(MockResponse().setResponseCode(status).setHeader("Retry-After", "9"))
                val failure = runCatching { f.api.session(token) }.exceptionOrNull() as ApiFailure
                assertEquals(status, failure.status)
                if (status == 429) assertEquals(9000L, failure.retryAfterMillis)
            }
            assertEquals(6, f.server.requestCount)
            assertTrue(runCatching { f.api.registerNamed("+12025550123", "12345678", "\uD800", "Jane") }.isFailure)
            for (name in listOf("", "x".repeat(65), "a\u0000b"))
                assertTrue(runCatching { f.api.registerNamed("+12025550123", "12345678", "invite", name) }.isFailure)
            assertTrue(runCatching { f.api.register("+12025550123", "12345678", "invite") }.isFailure)
            assertEquals(6, f.server.requestCount)
        }
    }
}
