package dev.photohouse.connected.core

import org.junit.Test

import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import java.net.InetAddress
import kotlinx.serialization.json.*

class ProtectedNativeApiTest {
    @Test fun legacyAndProtectedAdmissionProfilesRemainDistinct() {
        assertThrows(IllegalArgumentException::class.java) { Admission.password("short") }
        Admission.password("short", protectedNativeV2 = true, registration = false)
        assertThrows(IllegalArgumentException::class.java) { Admission.password("short", protectedNativeV2 = true, registration = true) }
        Admission.password("12345678", protectedNativeV2 = true, registration = true)
        assertThrows(IllegalArgumentException::class.java) { Admission.password("\uD800", protectedNativeV2 = true) }
    }

    private class Fixture : AutoCloseable {
        private val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        private val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        private val client = OkHttpClient.Builder().protocols(listOf(okhttp3.Protocol.HTTP_1_1)).sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        val origin = TrustedOrigin.parse("https://localhost:${server.port}")
        val token = Bearer.from(dev.photohouse.protocol.SessionToken(86400, "T".repeat(43), "Bearer"))
        fun api(enabled: Boolean) = HttpsPhotoHouseApi(origin, client, protectedNativeV2Enabled = enabled)
        override fun close() { server.shutdown() }
    }

    private fun body(text: String, library: String = "family") = """{"asset_id":"42","library_id":"$library","page":1,"can_create":false,"has_more":false,"items":[{"asset_id":"42","author_id":"opaque-account","byline":"","can_edit":false,"can_view_history":false,"created_at":0,"deleted":false,"id":"123e4567-e89b-12d3-a456-426614174001","language":"und","revision":1,"source":"family","text":"$text","title":"","updated_at":0}]}"""

    @Test fun disabledStoryRouteFailsBeforeNetwork() = runBlocking {
        Fixture().use { f -> assertThrows(IllegalArgumentException::class.java) { runBlocking { f.api(false).stories(f.token, "family", "42", 1) } }; assertEquals(0, f.server.requestCount) }
    }

    @Test fun storyTransportUsesExactScopedQueryAndProtectedHeaders() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(body("literal", "family name")))
            f.api(true).stories(f.token, "family name", "42", 1)
            val request = f.server.takeRequest()
            assertEquals("/assets/42/stories?library=family%20name&page=1", request.path)
            assertEquals("Bearer " + "T".repeat(43), request.getHeader("Authorization"))
            assertNull(request.getHeader("Origin")); assertNull(request.getHeader("Cookie")); assertEquals("identity", request.getHeader("Accept-Encoding"))
        }
    }

    @Test fun escapedStoryAboveLegacyBudgetIsAcceptedAndStoryBudgetIsEnforced() = runBlocking {
        Fixture().use { f ->
            val escaped = "\\u0061".repeat(32768)
            val single = body(escaped)
            val item = single.substringAfter("\"items\":[").removeSuffix("]}")
            val many = single.substringBefore("\"items\":[") + "\"items\":[" + (1..5).joinToString(",") {
                item.replace("426614174001", "42661417400$it")
            } + "]}"
            assertTrue(many.toByteArray().size > HttpsPhotoHouseApi.JSON_LIMIT)
            assertEquals(5, ProtectedStoriesWire.parse(many.toByteArray(),"family","42",1).items.size)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setChunkedBody(many, 8192))
            val response = f.api(true).stories(f.token, "family", "42", 1)
            assertEquals(5, response.items.size); assertEquals(32768, response.items.first().text.length)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("x".repeat(HttpsPhotoHouseApi.STORIES_LIMIT + 1)))
            assertEquals(FailureKind.TOO_LARGE, runCatching { f.api(true).stories(f.token, "family", "42", 1) }.exceptionOrNull().let { (it as ApiFailure).kind })
        }
    }
    @Test fun nativeAuthSendsExactPasswordAndNativeTransportWithoutOriginOrCookie() = runBlocking {
        Fixture().use { f ->
            for ((password, register) in listOf("a" to false, " 123456 " to true)) {
                f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(
                    """{"expires_in":86400,"access_token":"${"T".repeat(43)}","token_type":"Bearer"}"""))
                if (register) f.api(true).registerNamed("+86 12345678", password, "synthetic-invitation", "  示例\u00a0 Member  ")
                else f.api(true).login("+86 12345678", password)
                val request = f.server.takeRequest()
                val payload = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
                assertEquals(password, payload["password"]!!.jsonPrimitive.content)
                if (register) {
                    assertEquals("示例 Member", payload["name"]!!.jsonPrimitive.content)
                    assertEquals(setOf("phone", "password", "code", "name", "transport"), payload.keys)
                } else assertFalse(payload.containsKey("name"))
                assertEquals("native", payload["transport"]!!.jsonPrimitive.content)
                assertEquals("+8612345678", payload["phone"]!!.jsonPrimitive.content)
                assertEquals(if(register) "/auth/register" else "/auth/login",request.path)
                assertNull(request.getHeader("Origin"));assertNull(request.getHeader("Cookie"))
            }
            assertThrows(IllegalArgumentException::class.java) { runBlocking { f.api(true).register("+8612345678","1234567","code") } }
            assertEquals(2,f.server.requestCount)
        }
    }
    @Test fun storyMimeRedirectMalformedDataAndLegacyBudgetFailClosed()=runBlocking {
        Fixture().use { f ->
            for(response in listOf(
                MockResponse().setHeader("Content-Type","text/html").setBody(body("text")),
                MockResponse().setResponseCode(302).setHeader("Location","https://example.invalid/stories"),
                MockResponse().setHeader("Content-Type","application/json").setBody(body("text").replace("\"revision\":1","\"revision\":{}")))) {
                f.server.enqueue(response)
                assertTrue(runCatching { f.api(true).stories(f.token,"family","42",1) }.exceptionOrNull() is ApiFailure)
            }
            f.server.enqueue(MockResponse().setHeader("Content-Type","application/json").setBody("x".repeat(HttpsPhotoHouseApi.JSON_LIMIT+1)))
            assertEquals(FailureKind.TOO_LARGE,(runCatching { f.api(true).session(f.token) }.exceptionOrNull() as ApiFailure).kind)
            assertEquals(4,f.server.requestCount)
        }
    }
    @Test fun admissionUsesCodepointsAndNeverTrims() {
        for(n in listOf(1,7,8,128)) Admission.password("😀".repeat(n),true)
        for(n in listOf(8,128)) Admission.password("😀".repeat(n),true,true)
        for(n in listOf(0,129)) assertThrows(IllegalArgumentException::class.java) {Admission.password("😀".repeat(n),true)}
        assertThrows(IllegalArgumentException::class.java) {Admission.password("😀".repeat(7),true,true)}
        Admission.password(" ".repeat(8),true,true)
        Admission.password("x".repeat(15));assertThrows(IllegalArgumentException::class.java) {Admission.password("x".repeat(14))}
    }

}
