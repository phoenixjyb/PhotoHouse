package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import okhttp3.*
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.junit.Assert.*
import org.junit.Test

/** Actual compiled adapter with an in-process interceptor, never a socket/TLS test. */
class ReadinessAdapterTest {
    private class WireHarness : AutoCloseable {
        val requests = mutableListOf<Request>()
        var status = 200
        var body = "{}"
        private val client = OkHttpClient.Builder().addInterceptor { chain ->
            requests += chain.request()
            Response.Builder().request(chain.request()).protocol(Protocol.HTTP_1_1)
                .code(status).message("Synthetic").header("Content-Type", "application/json")
                .body(body.toResponseBody()).build()
        }.build()
        val api = HttpsPhotoHouseApi(TrustedOrigin.parse("https://photohouse.test"), client)
        override fun close() { client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll() }
    }
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private fun Request.json() = Json.parseToJsonElement(Buffer().also { body!!.writeTo(it) }.readUtf8()).jsonObject

    @Test fun admissionUsesPhoneLoginAndOwnerInvitationWithoutIdentityProviderFields() = runBlocking {
        WireHarness().use { wire ->
            wire.body = """{"expires_in":86400,"access_token":"${"T".repeat(43)}","token_type":"Bearer"}"""
            wire.api.login("+1 (202) 555-0123", "synthetic-password-only")
            val login = wire.requests.single()
            assertEquals("/auth/login", login.url.encodedPath)
            assertEquals(setOf("phone", "password", "transport"), login.json().keys)
            assertEquals("+12025550123", login.json().getValue("phone").jsonPrimitive.content)
            assertEquals("native", login.json().getValue("transport").jsonPrimitive.content)
            assertNull(login.header("Authorization")); assertNull(login.header("Cookie"))
            wire.api.register("+12025550123", "synthetic-password-only", "synthetic-owner-invitation")
            val register = wire.requests.last()
            assertEquals("/auth/register", register.url.encodedPath)
            assertEquals(setOf("phone", "password", "transport", "code"), register.json().keys)
            assertEquals("synthetic-owner-invitation", register.json().getValue("code").jsonPrimitive.content)
        }
    }
    @Test fun invalidAndUsedInvitationResponsesAreGenericDenialWithoutReplay() = runBlocking {
        WireHarness().use { wire ->
            wire.status = 401
            for (code in listOf("synthetic-invalid", "synthetic-used")) {
                val error = runCatching { wire.api.register("+12025550123", "synthetic-password-only", code) }.exceptionOrNull()
                assertEquals(401, (error as ApiFailure).status)
            }
            assertEquals(2, wire.requests.size)
        }
    }
    @Test fun protectedReadAndLogoutUseOneBearerAndNoCookieOrQueryCredential() = runBlocking {
        WireHarness().use { wire ->
            wire.body = """{"account_id":"synthetic","phone_login":"+12025550123","memberships":[]}"""
            assertTrue(wire.api.session(token).memberships.isEmpty())
            wire.body = """{"ok":true}"""; wire.api.logout(token)
            assertEquals(listOf("/auth/session", "/auth/logout"), wire.requests.map { it.url.encodedPath })
            wire.requests.forEach {
                assertEquals(listOf(token.header()), it.headers.values("Authorization"))
                assertNull(it.header("Cookie")); assertNull(it.url.query)
                assertEquals("no-store", it.header("Cache-Control"))
            }
        }
    }
    @Test fun absentThumbnailDoesNotFetchOriginalAndUnavailableMembershipIsPreserved() = runBlocking {
        WireHarness().use { wire ->
            wire.status = 404
            val asset = Asset("1", "image", null, null, null, null, "/assets/1/thumbnail?library=synthetic")
            assertNull(wire.api.thumbnail(token, "synthetic", asset))
            assertEquals(listOf("/assets/1/thumbnail"), wire.requests.map { it.url.encodedPath })
            wire.status = 200
            wire.body = """{"account_id":"synthetic","phone_login":"+12025550123","memberships":[{"library_id":"synthetic","status":"approved","role":"viewer","revision":2,"expires_at":null,"originals":0,"available":false}]}"""
            assertFalse(wire.api.session(token).memberships.single().available)
        }
    }
    @Test fun unsetOrNonOriginConfigurationIsRejectedBeforeAdapterConstruction() {
        for (origin in listOf("", " ", "http://photohouse.test", "https://photohouse.test/path", "https://photohouse.test?token=x")) {
            assertTrue(runCatching { TrustedOrigin.parse(origin) }.isFailure)
        }
    }
}
