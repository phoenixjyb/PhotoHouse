package dev.photohouse.connected.core

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress
import java.util.UUID

class ProtectedStoryWriteTransportTest {
    private class Fixture : AutoCloseable {
        private val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        private val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        private val client = OkHttpClient.Builder()
            .protocols(listOf(okhttp3.Protocol.HTTP_1_1))
            .sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        val api = HttpsPhotoHouseApi(TrustedOrigin.parse("https://localhost:${server.port}"), client, protectedNativeV2Enabled = true, mediaFilterEnabled = true)
        val token = Bearer.from(dev.photohouse.protocol.SessionToken(86400, "T".repeat(43), "Bearer"))
        override fun close() { server.shutdown() }
    }

    private val story = ProtectedStory(
        "123e4567-e89b-12d3-a456-426614174001", "42", "Trip", "A literal memory", "mixed", "Mom", "account", 3, 10, 11, true, true,
    )

    private fun storyJson(story: ProtectedStory = this.story, assetId: String = story.assetId, revisionAsString: Boolean = false): String =
        """{"asset_id":"$assetId","author_id":"${story.authorId}","byline":"${story.byline}","can_edit":${story.canEdit},"can_view_history":${story.canViewHistory},"created_at":${story.createdAt},"deleted":false,"id":"${story.id}","language":"${story.language}","revision":${if (revisionAsString) "\"${story.revision}\"" else story.revision},"source":"family","text":"${story.text}","title":"${story.title}","updated_at":${story.updatedAt}}"""

    private fun response(story: ProtectedStory = this.story, assetId: String = story.assetId, revisionAsString: Boolean = false): String =
        """{"story":${storyJson(story, assetId, revisionAsString)},"page":1,"has_more":false,"items":[]}"""

    @Test fun createAndUpdateUseExactMethodScopeUuidAndRevision() = runBlocking {
        Fixture().use { f ->
            val createId = UUID.randomUUID()
            val create = StoryMutation("42", null, null, StoryDraft("Trip", "A literal memory", "mixed", "Mom"), createId)
            f.server.enqueue(MockResponse().setResponseCode(201).setHeader("Content-Type", "application/json").setBody(storyJson()))
            f.api.saveStory(f.token, "family-a", create)
            val post = f.server.takeRequest()
            assertEquals("POST", post.method)
            assertEquals("/assets/42/stories?library=family-a", post.path)
            assertEquals("Bearer " + "T".repeat(43), post.getHeader("Authorization"))
            val createBody = post.body.readUtf8().let { kotlinx.serialization.json.Json.parseToJsonElement(it).jsonObject }
            assertEquals(createId.toString(), createBody.getValue("mutation_id").jsonPrimitive.content)
            assertFalse(createBody.containsKey("revision"))

            val updateId = UUID.randomUUID()
            val update = create.copy(storyId = story.id, revision = 3, draft = create.draft.copy(text = "Updated"), mutationId = updateId)
            f.server.enqueue(MockResponse().setResponseCode(200).setHeader("Content-Type", "application/json").setBody(storyJson(story.copy(text = "Updated", revision = 4))))
            f.api.saveStory(f.token, "family-a", update)
            val put = f.server.takeRequest()
            assertEquals("PUT", put.method)
            assertEquals("/stories/${story.id}?library=family-a", put.path)
            val updateBody = put.body.readUtf8().let { kotlinx.serialization.json.Json.parseToJsonElement(it).jsonObject }
            assertEquals(updateId.toString(), updateBody.getValue("mutation_id").jsonPrimitive.content)
            assertEquals("3", updateBody.getValue("revision").jsonPrimitive.content)
            assertEquals("Updated", updateBody.getValue("text").jsonPrimitive.content)
        }
    }

    @Test fun currentStoryReadsHistoryAndRejectsWrongAssetOrMalformedRevision() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(response()))
            assertEquals(story.id, f.api.currentStory(f.token, "family", "42", story.id)!!.id)
            assertEquals("/stories/${story.id}/history?library=family&page=1", f.server.takeRequest().path)

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(response(assetId = "43")))
            assertEquals(FailureKind.INVALID_RESPONSE, failure { f.api.currentStory(f.token, "family", "42", story.id) }.kind)

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(response(story, revisionAsString = true)))
            assertEquals(FailureKind.INVALID_RESPONSE, failure { f.api.currentStory(f.token, "family", "42", story.id) }.kind)
        }
    }

    @Test fun boundsErrorsAreLocalAndResponsesNeverFollowRedirectsOrRetryMutation() = runBlocking {
        Fixture().use { f ->
            val tooLarge = StoryMutation("42", null, null, StoryDraft(text = "x".repeat(512 * 1024)), UUID.randomUUID())
            assertEquals(FailureKind.INVALID_INPUT, failure { f.api.saveStory(f.token, "family", tooLarge) }.kind)
            assertEquals(0, f.server.requestCount)

            f.server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "https://example.invalid/stories"))
            assertEquals(FailureKind.HTTP, failure { f.api.saveStory(f.token, "family", StoryMutation("42", null, null, StoryDraft(text = "x"), UUID.randomUUID())) }.kind)
            assertEquals(1, f.server.requestCount)

            f.server.enqueue(MockResponse().setResponseCode(503).setHeader("Retry-After", "7").setBody("private diagnostic"))
            val failure = failure { f.api.saveStory(f.token, "family", StoryMutation("42", null, null, StoryDraft(text = "x"), UUID.randomUUID())) }
            assertEquals(503, failure.status)
            assertEquals(2, f.server.requestCount)
        }
    }

    @Test fun oversizedStoryResponseAndHttpPermissionErrorsRemainFailClosed() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("x".repeat(HttpsPhotoHouseApi.STORIES_LIMIT + 1)))
            assertEquals(FailureKind.TOO_LARGE, failure { f.api.currentStory(f.token, "family", "42", story.id) }.kind)
            f.server.enqueue(MockResponse().setResponseCode(403).setHeader("Content-Type", "application/json").setBody("{}"))
            val denied = failure { f.api.saveStory(f.token, "family", StoryMutation("42", story.id, 3, StoryDraft(text = "x"), UUID.randomUUID())) }
            assertEquals(403, denied.status)
        }
    }

    @Test fun galleryFilterIsSentToServerAndDefaultWireStaysUnchanged() = runBlocking {
        Fixture().use { f ->
            val body = """{"library_id":"family","page":2,"page_size":50,"total":0,"originals_allowed":false,"items":[]}"""
            for (media in listOf(GalleryMedia.ALL, GalleryMedia.PHOTOS, GalleryMedia.VIDEOS)) {
                f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(body))
                f.api.gallery(f.token, "family", 2, media)
                val request = f.server.takeRequest()
                assertEquals("GET", request.method)
                assertEquals("family", request.requestUrl!!.queryParameter("library"))
                assertEquals("2", request.requestUrl!!.queryParameter("page"))
                assertEquals("50", request.requestUrl!!.queryParameter("page_size"))
                assertEquals(if (media == GalleryMedia.ALL) null else media.wire, request.requestUrl!!.queryParameter("media"))
            }
        }
    }

    private fun failure(block: suspend () -> Any?): ApiFailure =
        (runCatching { runBlocking { block() } }.exceptionOrNull() as? ApiFailure)
            ?: error("expected ApiFailure")
}
