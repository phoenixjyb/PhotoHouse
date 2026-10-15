package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
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

class HttpsMemoryGroupsApiTest {
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private val story = "123e4567-e89b-12d3-a456-426614174001"

    private class Fixture : AutoCloseable {
        private val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        private val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        private val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        val origin = TrustedOrigin.parse("https://localhost:${server.port}")
        fun api(enabled: Boolean = true) = HttpsMemoryGroupsApi(origin, enabled, client)
        override fun close() {
            server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll()
        }
    }

    private fun caps() = """{"version":1,"enabled":true,"manual":true,"suggestions":false,"max_members":24,"needs_review":true}"""
    private fun group(revision: Int = 1) = """{"version":1,"type":"memory_group","id":"$story","library_id":"family-a","revision":"$revision","theme":"trip","asset_ids":["42"],"excluded_asset_ids":[],"source_story_ids":[],"items":[{"id":"42","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/42/thumbnail?library=family-a"}],"sources":[],"can_edit":true}"""

    @Test fun disabledAdapterDoesNotMakeNetworkRequests() = runBlocking {
        Fixture().use { f ->
            val api = f.api(false)
            assertFalse(api.memoryGroupsEnabled)
            try { api.capabilities(token, "family-a"); fail("disabled route was used") }
            catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
            assertEquals(0, f.server.requestCount)
        }
    }

    @Test fun capabilitiesAndListUseExactProtectedGetRoutesAndScope() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json; charset=utf-8").setBody(caps()))
            assertTrue(api.capabilities(token, "family-a").manual)
            val capabilityRequest = f.server.takeRequest()
            assertEquals("GET", capabilityRequest.method)
            assertEquals("/memory-groups/capabilities?library=family-a", capabilityRequest.path)
            assertProtected(capabilityRequest)

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(
                """{"version":1,"library_id":"family-a","asset_id":"42","has_more":false,"items":[${group()}]}"""))
            assertEquals(story, api.list(token, "family-a", "42").items.single().id)
            val listRequest = f.server.takeRequest()
            assertEquals("GET", listRequest.method)
            assertEquals("/assets/42/memory-groups?library=family-a", listRequest.path)
            assertProtected(listRequest)
        }
    }

    @Test fun createAndUpdateSendExactStringMutationFieldsAndRevision() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            val mutation = MemoryGroupMutation(theme = "trip", assetIds = listOf("42"), mutationId = story)
            f.server.enqueue(MockResponse().setResponseCode(201).setHeader("Content-Type", "application/json").setBody(group()))
            assertEquals(1L, api.save(token, "family-a", mutation).revision)
            val create = f.server.takeRequest()
            assertEquals("POST", create.method); assertEquals("/memory-groups?library=family-a", create.path)
            assertProtected(create); assertEquals("application/json; charset=utf-8", create.getHeader("Content-Type"))
            val createBody = Json.parseToJsonElement(create.body.readUtf8()).jsonObject
            assertEquals(setOf("asset_ids", "excluded_asset_ids", "source_story_ids", "theme", "revision", "mutation_id"), createBody.keys)
            assertEquals(mapOf("asset_ids" to "42", "excluded_asset_ids" to "", "source_story_ids" to "", "theme" to "trip", "revision" to "0", "mutation_id" to story),
                createBody.mapValues { it.value.jsonPrimitive.content })
            assertFalse(createBody.values.any { it.toString().contains("text") })

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(group(2)))
            val update = mutation.copy(groupId = story, revision = 1, assetIds = listOf("42", "43"))
            assertEquals(2L, api.save(token, "family-a", update).revision)
            val edit = f.server.takeRequest()
            assertEquals("PUT", edit.method); assertEquals("/memory-groups/$story?library=family-a", edit.path)
            assertProtected(edit)
            val editBody = Json.parseToJsonElement(edit.body.readUtf8()).jsonObject
            assertEquals("42,43", editBody.getValue("asset_ids").jsonPrimitive.content)
            assertEquals("1", editBody.getValue("revision").jsonPrimitive.content)
            assertEquals(story, editBody.getValue("mutation_id").jsonPrimitive.content)
        }
    }

    @Test fun proposalPostPreservesSeedOrderAndCarriesExcludedIds() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            val candidate = { id: String ->
                """{"id":"$id","kind":"image","width":640,"height":480,"duration_sec":null,"taken_at":"2026-03-04T11:00:00Z","thumbnail_url":"/assets/$id/thumbnail?library=family-a","matched_seed_asset_id":"42","time_reason":"within_recorded_window"}"""
            }
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(
                """{"version":1,"status":"ready","library_id":"family-a","seed_asset_ids":["42","43"],"needs_review":true,"items":[${candidate("45")}] }"""))
            val result = api.proposals(token, "family-a", listOf("42", "43"), listOf("44"))
            assertEquals(listOf("45"), result.items.map { it.asset.id })
            assertEquals("42", result.items.single().matchedSeedAssetId)
            val request = f.server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/memory-groups/proposals?library=family-a", request.path)
            assertProtected(request)
            val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
            assertEquals(setOf("asset_ids", "excluded_asset_ids"), body.keys)
            assertEquals("42,43", body.getValue("asset_ids").jsonPrimitive.content)
            assertEquals("44", body.getValue("excluded_asset_ids").jsonPrimitive.content)
        }
    }

    @Test fun mapsAuthorizationConflictAndRateLimitWithoutReadingErrorBodies() = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            for ((status, delay) in listOf(401 to 0L, 409 to 0L, 429 to 2000L)) {
                f.server.enqueue(MockResponse().setResponseCode(status).setHeader("Retry-After", "2")
                    .setHeader("Content-Type", "text/plain").setBody("secret server detail ${"T".repeat(43)}"))
                try { api.capabilities(token, "family-a"); fail("HTTP $status accepted") }
                catch (e: ApiFailure) {
                    assertEquals(FailureKind.HTTP, e.kind); assertEquals(status, e.status); assertEquals(delay, e.retryAfterMillis)
                    assertFalse(e.toString().contains("secret server detail")); assertFalse(e.toString().contains("T".repeat(43)))
                }
                f.server.takeRequest()
            }
        }
    }

    @Test fun redirectIsReturnedAsHttpFailureAndNeverFollowed() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "/elsewhere?library=other"))
            try { f.api().capabilities(token, "family-a"); fail("redirect accepted") }
            catch (e: ApiFailure) { assertEquals(FailureKind.HTTP, e.kind); assertEquals(302, e.status) }
            assertEquals(1, f.server.requestCount)
            assertEquals("/memory-groups/capabilities?library=family-a", f.server.takeRequest().path)
        }
    }

    @Test fun rejectsWrongContentTypeCompressedAndOversizedResponses(): Unit = runBlocking {
        Fixture().use { f ->
            val api = f.api()
            f.server.enqueue(MockResponse().setHeader("Content-Type", "text/plain").setBody(caps()))
            invalidResponse { api.capabilities(token, "family-a") }; f.server.takeRequest()
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json")
                .setHeader("Content-Encoding", "gzip").setBody(caps()))
            invalidResponse { api.capabilities(token, "family-a") }; f.server.takeRequest()
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(" ".repeat(MemoryGroupsWire.RESPONSE_LIMIT + 1)))
            try { api.capabilities(token, "family-a"); fail("oversized response accepted") }
            catch (e: ApiFailure) { assertEquals(FailureKind.TOO_LARGE, e.kind) }
            f.server.takeRequest()
        }
    }

    private fun assertProtected(request: okhttp3.mockwebserver.RecordedRequest) {
        assertEquals("Bearer ${"T".repeat(43)}", request.getHeader("Authorization"))
        assertEquals("application/json", request.getHeader("Accept"))
        assertEquals("no-store", request.getHeader("Cache-Control"))
        assertEquals("identity", request.getHeader("Accept-Encoding"))
        assertNull(request.getHeader("Cookie"))
        assertNull(request.getHeader("Origin"))
    }

    private suspend fun invalidResponse(block: suspend () -> Unit) {
        try { block(); fail("invalid response accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }
}
