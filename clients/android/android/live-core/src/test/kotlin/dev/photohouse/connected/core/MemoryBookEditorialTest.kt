package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress

class MemoryBookEditorialTest {
    private val book = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    private val s1 = "11111111-1111-4111-8111-111111111111"
    private val s2 = "22222222-2222-4222-8222-222222222222"
    private val contribution = "33333333-3333-4333-8333-333333333333"
    private val mutationId = "abcdefab-cdef-4abc-8def-abcdefabcdef"
    private val children = listOf(EditorialChild(s1, "7"), EditorialChild(s2, "3"))
    private val ref = EditorialSourceIdentity(s1, "7", "chapter-a", contribution)
    private val eligible = setOf(ref)
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))

    private fun transition(text: String = "") = EditorialTransition(s1, s2, text, emptyList())
    private fun validMutation() = MemoryBookEditorialMutation("12", mutationId, children, listOf(ref), listOf(transition()))
    private fun response(state: String = "current", intro: String = """{"story_id":"$s1","story_revision":"7","chapter_id":"chapter-a","contribution_id":"$contribution"}""", transitions: String = """{"left_story_id":"$s1","right_story_id":"$s2","text":"","source_refs":[]}""") =
        """{"version":1,"id":"$book","revision":"12","children":[{"story_id":"$s1","revision":"7"},{"story_id":"$s2","revision":"3"}],"state":"$state","introduction_source_refs":${if (intro.isEmpty()) "[]" else "[$intro]"},"transitions":${if (transitions.isEmpty()) "[]" else "[$transitions]"}}""".toByteArray()

    @Test fun requestEncodingIsCanonicalOrderedAndBoundToAuthorizedChildrenAndRefs() {
        val json = MemoryBookEditorialWire.encodeMutation(validMutation(), children, eligible)
        assertEquals("""{"version":1,"revision":"12","mutation_id":"$mutationId","children":[{"story_id":"$s1","revision":"7"},{"story_id":"$s2","revision":"3"}],"introduction_source_refs":[{"story_id":"$s1","story_revision":"7","chapter_id":"chapter-a","contribution_id":"$contribution"}],"transitions":[{"left_story_id":"$s1","right_story_id":"$s2","text":"","source_refs":[]}]}""", json)
        assertTrue(json.toByteArray().size <= MemoryBookEditorialWire.MAX_BODY_BYTES)
        assertInvalid { MemoryBookEditorialWire.encodeMutation(validMutation().copy(children = children.reversed()), children, eligible) }
        assertInvalid { MemoryBookEditorialWire.encodeMutation(validMutation().copy(introductionSourceRefs = listOf(ref.copy(chapterId = "deleted"))), children, eligible) }
        assertInvalid { MemoryBookEditorialWire.encodeMutation(validMutation().copy(mutationId = mutationId.uppercase()), children, eligible) }
        assertInvalid { MemoryBookEditorialWire.encodeMutation(validMutation().copy(revision = "01"), children, eligible) }
        val maxRevisionJson = MemoryBookEditorialWire.encodeMutation(validMutation().copy(revision = Long.MAX_VALUE.toString()), children, eligible)
        assertTrue(maxRevisionJson.contains("\"revision\":\"${Long.MAX_VALUE}\""))
        assertInvalid { MemoryBookEditorialWire.encodeMutation(validMutation().copy(revision = "9223372036854775808"), children, eligible) }
        assertInvalid { MemoryBookEditorialWire.encodeMutation(validMutation().copy(transitions = listOf(transition("é".repeat(3001)))), children, eligible) }
        assertInvalid { MemoryBookEditorialWire.encodeMutation(validMutation().copy(transitions = listOf(transition("spoken").copy(sourceRefs = listOf(ref.copy(storyId = s2)))),), children, eligible) }
        val nelBlank = validMutation().copy(transitions = listOf(transition("\u0085")))
        val nelJson = MemoryBookEditorialWire.encodeMutation(nelBlank, children, eligible)
        assertTrue(nelJson.contains("\u0085") || nelJson.contains("\\u0085"))
        assertInvalid { MemoryBookEditorialWire.encodeMutation(nelBlank.copy(transitions = listOf(transition("\u0085").copy(sourceRefs = listOf(ref)))), children, eligible) }
        assertInvalid { MemoryBookEditorialWire.encodeMutation(validMutation().copy(introductionSourceRefs = listOf(ref.copy(chapterId = "é".repeat(65)))), children, eligible) }
        val manyChildren = (1..12).map { index ->
            val id = java.util.UUID.nameUUIDFromBytes("editorial-child-$index".toByteArray()).toString()
            EditorialChild(id, "1")
        }
        val refs = manyChildren.map { child -> EditorialSourceIdentity(child.storyId, "1", "chapter", java.util.UUID.nameUUIDFromBytes(child.storyId.toByteArray()).toString()) }
        val manyEligible = refs.toSet()
        val largeMutation = MemoryBookEditorialMutation("12", mutationId, manyChildren, emptyList(),
            manyChildren.zipWithNext().mapIndexed { index, pair -> EditorialTransition(pair.first.storyId, pair.second.storyId, "x".repeat(6000), listOf(refs[index])) })
        assertInvalid { MemoryBookEditorialWire.encodeMutation(largeMutation, manyChildren, manyEligible) }
    }

    @Test fun responseRequiresExactShapeVersionIdentityRevisionChildrenAndReferenceAdjacency() {
        val decoded = MemoryBookEditorialWire.decodeResponse(response(), book, "12", children, eligible)
        assertEquals(EditorialState.CURRENT, decoded.state)
        assertEquals(listOf(ref), decoded.introductionSourceRefs)
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response().decodeToString().replace("\"version\":1", "\"version\":2").toByteArray(), book, "12", children, eligible) }
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response().decodeToString().replace("\"state\":\"current\"", "\"state\":\"mystery\"").toByteArray(), book, "12", children, eligible) }
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response().decodeToString().replace("\"id\":\"$book\"", "\"id\":\"$s1\"").toByteArray(), book, "12", children, eligible) }
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response().decodeToString().replace("\"revision\":\"12\"", "\"revision\":\"13\"", true).toByteArray(), book, "12", children, eligible) }
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response().decodeToString().replace("\"revision\":\"3\"", "\"revision\":\"4\"").toByteArray(), book, "12", children, eligible) }
        val changedSource = response("source_changed", intro = "", transitions = "")
        val changed = MemoryBookEditorialWire.decodeResponse(changedSource, book, "12", children, eligible)
        assertEquals(EditorialState.SOURCE_CHANGED, changed.state)
        assertTrue(changed.introductionSourceRefs.isEmpty())
        assertTrue(changed.transitions.isEmpty())
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response(intro = """{"story_id":"$s1","story_revision":"7","chapter_id":"deleted","contribution_id":"$contribution"}"""), book, "12", children, eligible) }
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response(intro = "{}"), book, "12", children, eligible) }
        val duplicate = response().decodeToString().replace("\"version\":1,", "\"version\":1,\"version\":1,")
        assertInvalid { MemoryBookEditorialWire.decodeResponse(duplicate.toByteArray(), book, "12", children, eligible) }
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response().copyOf(MemoryBookEditorialWire.MAX_BODY_BYTES + 1), book, "12", children, eligible) }
    }

    @Test fun emptyAndCurrentResponsesEnforceTransitionCountAndCitationRules() {
        val empty = MemoryBookEditorialWire.decodeResponse(response("empty", intro = "", transitions = ""), book, "12", children, eligible)
        assertEquals(EditorialState.EMPTY, empty.state)
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response("empty", intro = "{}", transitions = ""), book, "12", children, eligible) }
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response(transitions = ""), book, "12", children, eligible) }
        val wrongAdjacent = """{"left_story_id":"$s2","right_story_id":"$s1","text":"","source_refs":[]}"""
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response(transitions = wrongAdjacent), book, "12", children, eligible) }
        val nelBlank = """{"left_story_id":"$s1","right_story_id":"$s2","text":"\u0085","source_refs":[]}"""
        val decodedNel = MemoryBookEditorialWire.decodeResponse(response(transitions = nelBlank), book, "12", children, eligible)
        assertEquals("\u0085", decodedNel.transitions.single().text)
        val nelWithCitation = nelBlank.replace("\"source_refs\":[]", "\"source_refs\":[{\"story_id\":\"$s1\",\"story_revision\":\"7\",\"chapter_id\":\"chapter-a\",\"contribution_id\":\"$contribution\"}]")
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response(transitions = nelWithCitation), book, "12", children, eligible) }
    }

    @Test fun currentResponseRejectsNinetySevenReferencesAcrossValidSections() {
        val manyChildren = (1..24).map { index ->
            EditorialChild(java.util.UUID.nameUUIDFromBytes("response-child-$index".toByteArray()).toString(), "1")
        }
        val refsByChild = manyChildren.map { child -> (1..2).map { refIndex ->
            EditorialSourceIdentity(child.storyId, "1", "chapter-$refIndex",
                java.util.UUID.nameUUIDFromBytes("${child.storyId}-contribution-$refIndex".toByteArray()).toString())
        } }
        val intro = refsByChild.take(6).flatMap { it }
        val transitions = manyChildren.zipWithNext().mapIndexed { index, pair ->
            val leftIndex = index
            val rightIndex = index + 1
            val refs = if (index < 16) refsByChild[leftIndex] + refsByChild[rightIndex]
                else refsByChild[leftIndex] + refsByChild[rightIndex].take(1)
            """{"left_story_id":"${pair.first.storyId}","right_story_id":"${pair.second.storyId}","text":"chapter bridge","source_refs":[${refs.joinToString(",") { sourceJson(it) }}]}"""
        }
        val childrenJson = manyChildren.joinToString(",") { """{"story_id":"${it.storyId}","revision":"${it.revision}"}""" }
        val response = """{"version":1,"id":"$book","revision":"12","children":[$childrenJson],"state":"current","introduction_source_refs":[${intro.joinToString(",") { sourceJson(it) }}],"transitions":[${transitions.joinToString(",") }]}""".toByteArray()
        assertInvalid { MemoryBookEditorialWire.decodeResponse(response, book, "12", manyChildren, (refsByChild.flatten()).toSet()) }
        val allowed = response.decodeToString().replaceFirst(sourceJson(intro.first()) + ",", "").toByteArray()
        val decoded = MemoryBookEditorialWire.decodeResponse(allowed, book, "12", manyChildren, refsByChild.flatten().toSet())
        assertEquals(96, decoded.introductionSourceRefs.size + decoded.transitions.sumOf { it.sourceRefs.size })
    }

    @Test fun sourceCatalogDerivesOrderedChapterMetadataAndRejectsMalformedOrMismatchedReferences() {
        val body = """{"version":1,"id":"$s1","library_id":"family","revision":"7","chapters":[{"id":"chapter-1","contribution_ids":["$contribution"]},{"id":"chapter-2","contribution_ids":[]}] }""".toByteArray()
        val decoded = MemoryBookEditorialWire.decodeSourceCatalog(body, "family", s1, 7)
        assertEquals(listOf("chapter-1", "chapter-2"), decoded.chapters.map { it.chapterId })
        assertEquals(listOf(contribution), decoded.chapters.first().contributionIds)
        assertInvalid { MemoryBookEditorialWire.decodeSourceCatalog(body, "other", s1, 7) }
        assertInvalid { MemoryBookEditorialWire.decodeSourceCatalog(body, "family", s1, 8) }
        assertInvalid { MemoryBookEditorialWire.decodeSourceCatalog(body.decodeToString().replace("chapter-1", "chapter-2").toByteArray(), "family", s1, 7) }
        assertInvalid { MemoryBookEditorialWire.decodeSourceCatalog(body.decodeToString().replace("\"contribution_ids\":[\"$contribution\"]", "\"contribution_ids\":[\"$contribution\",\"$contribution\"]").toByteArray(), "family", s1, 7) }
        assertInvalid { MemoryBookEditorialWire.decodeSourceCatalog(body.decodeToString().replace("\"version\":1,", "\"version\":1,\"version\":1,").toByteArray(), "family", s1, 7) }
    }

    @Test fun optionalRepositoryMapsOnlyNotFoundAndUnavailable() = runBlocking {
        val unavailable = object : MemoryBookEditorialApi {
            override suspend fun getBookEditorial(token: Bearer, library: String, bookId: String): ByteArray = throw ApiFailure(FailureKind.HTTP, 503)
            override suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String): ByteArray = throw ApiFailure(FailureKind.HTTP, 404)
        }
        val repository = MemoryBookEditorialRepository(unavailable)
        assertNull(repository.get(token, "family-a", book, "12", children, eligible))
        assertNull(repository.save(token, "family-a", book, validMutation(), children, eligible))
        for (status in listOf(401, 403)) {
            val denied = object : MemoryBookEditorialApi {
                override suspend fun getBookEditorial(token: Bearer, library: String, bookId: String): ByteArray = throw ApiFailure(FailureKind.HTTP, status)
                override suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String) = byteArrayOf()
            }
            try { MemoryBookEditorialRepository(denied).get(token, "family-a", book, "12", children, eligible); fail("auth failure was hidden") }
            catch (e: ApiFailure) { assertEquals(status, e.status) }
        }
    }

    @Test fun httpsTransportFreezesEditorialRequestsAndLibraryBinding() = runBlocking {
        val cert = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
        val server = MockWebServer().apply {
            useHttps(HandshakeCertificates.Builder().heldCertificate(cert).build().sslSocketFactory(), false)
            start(InetAddress.getByName("127.0.0.1"), 0)
        }
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager).build()
        try {
            val api = HttpsMemoryCommunityApi(TrustedOrigin.parse("https://localhost:${server.port}"), client)
            val frozen = MemoryBookEditorialWire.encodeMutation(validMutation(), children, eligible)
            server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(response().decodeToString()))
            api.getBookEditorial(token, "family-a", book)
            val get = server.takeRequest()
            assertEquals("GET", get.method)
            assertEquals("/memory-community/v1/books/$book/editorial?library=family-a", get.path)
            assertEquals(token.header(), get.getHeader("Authorization"))
            assertEquals("no-store", get.getHeader("Cache-Control"))
            assertEquals("identity", get.getHeader("Accept-Encoding"))
            assertNull(get.getHeader("Cookie"))
            server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody(response("current", transitions = """{"left_story_id":"$s1","right_story_id":"$s2","text":"","source_refs":[]}""").decodeToString()))
            api.saveBookEditorial(token, "family-a", book, frozen)
            val put = server.takeRequest()
            assertEquals("PUT", put.method)
            assertEquals("/memory-community/v1/books/$book/editorial?library=family-a", put.path)
            assertEquals("application/json; charset=utf-8", put.getHeader("Content-Type"))
            assertEquals(frozen, put.body.readUtf8())
        } finally {
            server.shutdown(); client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll()
        }
    }

    private fun assertInvalid(block: () -> Unit) {
        try { block(); fail("invalid editorial data was accepted") }
        catch (e: IllegalArgumentException) { }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }

    private fun sourceJson(ref: EditorialSourceIdentity) =
        """{"story_id":"${ref.storyId}","story_revision":"${ref.storyRevision}","chapter_id":"${ref.chapterId}","contribution_id":"${ref.contributionId}"}"""
}
