package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class HttpsMemoryCommunityApiTest {
    private class Fixture : AutoCloseable {
        private val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        private val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        private val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        val api = HttpsMemoryCommunityApi(TrustedOrigin.parse("https://localhost:${server.port}"), client)
        override fun close() {
            server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll()
        }
    }
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private val story = "11111111-1111-1111-1111-111111111111"

    @Test fun configuredOriginAuthenticatedRoutesAndRawAudioHeaders() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.listContributions(token, "family-a", story, 3)
            val list = f.server.takeRequest()
            assertEquals("/memory-community/v1/stories/$story/contributions?library=family-a&page=3", list.path)
            assertEquals(token.header(), list.getHeader("Authorization"))
            assertEquals("no-store", list.getHeader("Cache-Control"))
            assertEquals("identity", list.getHeader("Accept-Encoding"))

            val wav = byteArrayOf(1, 2, 3, 4)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.createAudioContribution(token, "family-a", story, "eyJmb28iOiJiYXIifQ==", wav)
            val upload = f.server.takeRequest()
            assertEquals("POST", upload.method)
            assertEquals("audio/wav", upload.getHeader("Content-Type"))
            assertEquals("eyJmb28iOiJiYXIifQ==", upload.getHeader("X-PhotoHouse-Memory-Metadata"))
            assertArrayEquals(wav, upload.body.readByteArray())

            f.server.enqueue(MockResponse().setHeader("Content-Type", "audio/wav").setBody("riff"))
            assertArrayEquals("riff".toByteArray(), f.api.contributionAudio(token, "family-a", story,
                "22222222-2222-2222-2222-222222222222"))
        }
    }

    @Test fun reviewedEditionRoutesUseProtectedOriginAndExactJsonContentType() = runBlocking {
        Fixture().use { f ->
            val job = "22222222-2222-4222-8222-222222222222"
            val edition = "33333333-3333-4333-8333-333333333333"
            val operations: List<Pair<String, suspend () -> ByteArray>> = listOf(
                "/edition-capabilities?library=family-a" to { f.api.editionCapabilities(token, "family-a", story) },
                "/editions/proposals/$job?library=family-a" to { f.api.editionProposal(token, "family-a", story, job) },
                "/editions?library=family-a" to { f.api.saveEdition(token, "family-a", story, "{\"reviewed\":true}") },
                "/editions?library=family-a&page=2" to { f.api.editionPage(token, "family-a", story, 2) },
                "/editions/$edition?library=family-a" to { f.api.editionDetail(token, "family-a", story, edition) },
            )
            for ((suffix, operation) in operations) {
                f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
                operation()
                val request = f.server.takeRequest()
                assertEquals("/memory-community/v1/books/$story$suffix", request.path)
                assertEquals(token.header(), request.getHeader("Authorization"))
                assertEquals("no-store", request.getHeader("Cache-Control"))
                if (request.method == "POST") {
                    assertEquals("application/json", request.getHeader("Content-Type"))
                    assertEquals("{\"reviewed\":true}", request.body.readUtf8())
                }
            }
            try { f.api.saveEdition(token, "family-a", story, "x".repeat(128 * 1024 + 1)); fail("oversized edition") }
            catch (_: IllegalArgumentException) { }
            assertEquals(5, f.server.requestCount)
        }
    }

    @Test fun editionOriginalReadsAreExplicitBoundedProtectedGetRoutes() = runBlocking {
        Fixture().use { f ->
            val edition = "33333333-3333-4333-8333-333333333333"
            val source = "contribution-44444444-4444-4444-8444-444444444444"
            assertEquals(0, f.server.requestCount)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.editionSources(token, "family-a", story, edition, 2)
            val list = f.server.takeRequest()
            assertEquals("/memory-community/v1/books/$story/editions/$edition/sources?library=family-a&page=2", list.path)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.editionSource(token, "family-a", story, edition, source)
            val detail = f.server.takeRequest()
            assertEquals("/memory-community/v1/books/$story/editions/$edition/sources/$source?library=family-a", detail.path)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "audio/wav").setBody("riff"))
            assertArrayEquals("riff".toByteArray(), f.api.editionSourceAudio(token, "family-a", story, edition, source))
            val audio = f.server.takeRequest()
            assertEquals("/memory-community/v1/books/$story/editions/$edition/sources/$source/audio?library=family-a", audio.path)
            listOf(list, detail, audio).forEach {
                assertEquals("GET", it.method); assertEquals(token.header(), it.getHeader("Authorization"))
                assertEquals("no-store", it.getHeader("Cache-Control")); assertEquals("identity", it.getHeader("Accept-Encoding"))
            }
            for (bad in listOf("../audio", "caption-1%2Faudio", "录音", "x".repeat(129))) {
                try { f.api.editionSource(token, "family-a", story, edition, bad); fail("invalid selector requested") }
                catch (_: IllegalArgumentException) { }
            }
            assertEquals(3, f.server.requestCount)
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            try { f.api.editionSourceAudio(token, "family-a", story, edition, source); fail("JSON passed as WAV") }
            catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE,e.kind) }
            f.server.takeRequest()
            Unit
        }
    }

    @Test fun conversationPreviewIsAnExplicitOptInAndLegacyRouteRemainsUnchanged() = runBlocking {
        Fixture().use { f ->
            val book = "44444444-4444-4444-4444-444444444444"
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.listConversations(token, "family-a", "book", book)
            val legacy = f.server.takeRequest()
            assertEquals("/memory-community/v1/conversations", legacy.requestUrl!!.encodedPath)
            assertEquals("family-a", legacy.requestUrl!!.queryParameter("library"))
            assertEquals("book", legacy.requestUrl!!.queryParameter("target_type"))
            assertEquals(book, legacy.requestUrl!!.queryParameter("target_id"))
            assertEquals(setOf("library", "target_type", "target_id"), legacy.requestUrl!!.queryParameterNames)

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.listConversationsWithPreview(token, "family-a", "book", book)
            val preview = f.server.takeRequest()
            assertEquals("/memory-community/v1/conversations", preview.requestUrl!!.encodedPath)
            assertEquals("family-a", preview.requestUrl!!.queryParameter("library"))
            assertEquals("book", preview.requestUrl!!.queryParameter("target_type"))
            assertEquals(book, preview.requestUrl!!.queryParameter("target_id"))
            assertEquals("1", preview.requestUrl!!.queryParameter("preview"))
            assertEquals(setOf("library", "target_type", "target_id", "preview"), preview.requestUrl!!.queryParameterNames)
        }
    }

    @Test fun conversationTurnsRequestRecentOrderedBoundedPageAndAcceptsAscendingSeventeenAndThirtyFiveFixtures() = runBlocking {
        Fixture().use { f ->
            val conversation = "44444444-4444-4444-4444-444444444444"
            val pages = listOf(
                Triple(1, 2..17, true), Triple(2, 1..1, false), // 17 turns: latest 16, then the oldest one
                Triple(1, 20..35, true), Triple(2, 4..19, true), // 35 turns: latest and preceding 16
            )
            for ((page, sequences, hasMore) in pages) {
                val rows = sequences.map { sequence ->
                    val turnId = "00000000-0000-4000-8000-${sequence.toString().padStart(12, '0')}"
                    """{"id":"$turnId","sequence":$sequence,"input_text":"message $sequence","reply_text":null,"reply_kind":null,"job_id":null,"state":"ready"}"""
                }
                f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(
                    """{"version":1,"id":"$conversation","expires_at":999,"page":$page,"has_more":$hasMore,"items":[${rows.joinToString(",")}] }"""))
                val bytes = f.api.conversationTurns(token, "family-a", conversation, page)
                val request = f.server.takeRequest()
                assertEquals("GET", request.method)
                assertEquals("/memory-community/v1/conversations/$conversation/turns", request.requestUrl!!.encodedPath)
                assertEquals("family-a", request.requestUrl!!.queryParameter("library"))
                assertEquals(page.toString(), request.requestUrl!!.queryParameter("page"))
                assertEquals("recent", request.requestUrl!!.queryParameter("order"))
                assertEquals(setOf("library", "page", "order"), request.requestUrl!!.queryParameterNames)
                val decoded = ProtectedMemoryCommunityWire.turns(bytes, conversation, page)
                assertEquals(sequences.toList(), decoded.items.map { it.sequence })
                assertEquals("message ${sequences.last}", decoded.items.last().inputText)
                assertEquals(hasMore, decoded.hasMore)
            }
        }
    }

    @Test fun editorialContextIsAnExplicitQueryAndNeverChangesPostBodies() = runBlocking {
        Fixture().use { f ->
            val conversation = "44444444-4444-4444-4444-444444444444"
            val jobBody = "{\"opaque\":\"same request body\"}"
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.sendTurn(token, "family-a", conversation, jobBody, editorialContext = false)
            val legacy = f.server.takeRequest()
            assertEquals("POST", legacy.method)
            assertEquals("/memory-community/v1/conversations/$conversation/turns", legacy.requestUrl!!.encodedPath)
            assertEquals(setOf("library"), legacy.requestUrl!!.queryParameterNames)
            assertEquals(jobBody, legacy.body.readUtf8())

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.sendTurn(token, "family-a", conversation, jobBody, editorialContext = true)
            val editorialChat = f.server.takeRequest()
            assertEquals("1", editorialChat.requestUrl!!.queryParameter("editorial_context"))
            assertEquals(setOf("library", "editorial_context"), editorialChat.requestUrl!!.queryParameterNames)
            assertEquals(jobBody, editorialChat.body.readUtf8())

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.queueNarrative(token, "family-a", jobBody, editorialContext = false)
            val legacyNarrative = f.server.takeRequest()
            assertEquals("/memory-community/v1/jobs", legacyNarrative.requestUrl!!.encodedPath)
            assertEquals(setOf("library"), legacyNarrative.requestUrl!!.queryParameterNames)
            assertEquals(jobBody, legacyNarrative.body.readUtf8())

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.queueNarrative(token, "family-a", jobBody, editorialContext = true)
            val editorialNarrative = f.server.takeRequest()
            assertEquals("1", editorialNarrative.requestUrl!!.queryParameter("editorial_context"))
            assertEquals(setOf("library", "editorial_context"), editorialNarrative.requestUrl!!.queryParameterNames)
            assertEquals(jobBody, editorialNarrative.body.readUtf8())
        }
    }

    @Test fun bookPlanQueryIsReadOnlyAndOptIn() = runBlocking {
        Fixture().use { f ->
            val book = "44444444-4444-4444-4444-444444444444"
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.bookPlan(token, "family-a", book, editorialContext = false)
            val ordinary = f.server.takeRequest()
            assertEquals("GET", ordinary.method)
            assertEquals("/memory-community/v1/books/$book/plan", ordinary.requestUrl!!.encodedPath)
            assertEquals(setOf("library"), ordinary.requestUrl!!.queryParameterNames)

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("{}"))
            f.api.bookPlan(token, "family-a", book, editorialContext = true)
            val editorial = f.server.takeRequest()
            assertEquals("GET", editorial.method)
            assertEquals("/memory-community/v1/books/$book/plan", editorial.requestUrl!!.encodedPath)
            assertEquals("1", editorial.requestUrl!!.queryParameter("editorial_context"))
            assertEquals(setOf("library", "editorial_context"), editorial.requestUrl!!.queryParameterNames)
        }
    }

    @Test fun replyContextQueryIsExplicitAndAddsOnlyTheOptInParameter() = runBlocking {
        Fixture().use { f ->
            val conversation = "44444444-4444-4444-4444-444444444444"
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(
                """{"version":1,"id":"$conversation","expires_at":999,"page":1,"has_more":false,"items":[{"id":"88888888-8888-8888-8888-888888888888","sequence":16,"input_text":"Question","reply_text":"Answer","reply_kind":"answer","job_id":null,"state":"ready","reply_source_ids":["caption-101"],"reply_questions":["More?"]}]}"""))
            val bytes = f.api.conversationTurnsWithReplyContext(token, "family-a", conversation, 1)
            val request = f.server.takeRequest()
            assertEquals("GET", request.method)
            assertEquals("recent", request.requestUrl!!.queryParameter("order"))
            assertEquals("1", request.requestUrl!!.queryParameter("reply_context"))
            assertEquals(setOf("library", "page", "order", "reply_context"), request.requestUrl!!.queryParameterNames)
            val turn = ProtectedMemoryCommunityWire.turns(bytes, conversation, 1).items.single()
            assertEquals(listOf("caption-101"), turn.replySourceIds)
            assertEquals(listOf("More?"), turn.replyQuestions)
        }
    }

    @Test fun redirectsAndOversizedUnknownLengthBodiesAreRejected() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "https://elsewhere.invalid/"))
            try {
                f.api.capabilities(token, "family-a")
                fail("redirect was followed or accepted")
            } catch (e: ApiFailure) { assertEquals(302, e.status) }
            assertEquals(1, f.server.requestCount)

            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json")
                .setChunkedBody("x".repeat(MemoryCommunityResponseLimits.JSON_BYTES + 1), 8192))
            try {
                f.api.capabilities(token, "family-a")
                fail("oversized stream was accepted")
            } catch (e: ApiFailure) { assertEquals(FailureKind.TOO_LARGE, e.kind) }
        }
    }

    @Test fun cancellationInterruptsAThrottledResponseRead() = runBlocking {
        Fixture().use { f ->
            f.server.enqueue(MockResponse().setHeader("Content-Type", "application/json")
                .setChunkedBody("x".repeat(256 * 1024), 1024).throttleBody(1024, 100, java.util.concurrent.TimeUnit.MILLISECONDS))
            val request = launch(Dispatchers.IO) {
                try { f.api.capabilities(token, "family-a") } catch (_: CancellationException) { }
                catch (_: ApiFailure) { }
            }
            assertNotNull(f.server.takeRequest())
            delay(150)
            request.cancelAndJoin()
            assertTrue(request.isCancelled)
        }
    }
}
