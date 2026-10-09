package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test

class MemoryBookEditionTest {
    private val bookId = "11111111-1111-1111-1111-111111111111"
    private val childOne = "22222222-2222-2222-2222-222222222222"
    private val childTwo = "33333333-3333-3333-3333-333333333333"
    private val jobId = "44444444-4444-4444-4444-444444444444"
    private val editionId = "55555555-5555-5555-5555-555555555555"
    private val mutationId = "66666666-6666-6666-6666-666666666666"
    private val sourceOne = "caption-101"
    private val sourceTwo = "contribution-77777777-7777-7777-7777-777777777777"
    private val children = listOf(MemoryBookEditionChild(childOne, "2"),
        MemoryBookEditionChild(childTwo, "1"))
    private val chapterIds = listOf("$childOne-chapter-1", "$childTwo-chapter-1")

    private fun manuscript(title: String = "回忆", firstText: String = "我们一起度过的夏天") =
        """{"version":1,"title":${title.json()},"chapters":[{"id":"${chapterIds[0]}","narration":${firstText.json()},"source_ids":["$sourceOne"]},{"id":"${chapterIds[1]}","narration":"A remembered day","source_ids":["$sourceTwo"]}],"questions":[],"needs_review":true}"""

    private fun String.json(): String = kotlinx.serialization.json.JsonPrimitive(this).toString()

    private fun proposalJson(
        revision: String = "7",
        jobResultSha: String = "a".repeat(64),
        fingerprint: String = "b".repeat(64),
        childrenJson: String = """[{"id":"$childOne","revision":"2"},{"id":"$childTwo","revision":"1"}]""",
        manuscriptJson: String = manuscript(),
        needsReview: String = "true",
        extra: String = "",
    ) = """{"version":1,"book_id":"$bookId","revision":"$revision","job_id":"$jobId","job_result_sha256":"$jobResultSha","source_fingerprint":"$fingerprint","context_profile":"stories","children":$childrenJson,"manuscript":$manuscriptJson,"needs_review":$needsReview$extra}"""

    private fun proposal(): MemoryBookEditionProposal = MemoryBookEditionWire.decodeProposal(
        proposalJson().toByteArray(), bookId, 7, jobId, children, chapterIds)

    @Test fun capabilitiesAndProposalAreExactScopedAndReviewRequired() {
        assertEquals(MemoryBookEditionCapabilities(true, true),
            MemoryBookEditionWire.decodeCapabilities(
                """{"version":1,"enabled":true,"can_save":true}""".toByteArray()))
        assertEquals(MemoryBookEditionCapabilities(false, false),
            MemoryBookEditionWire.decodeCapabilities(
                """{"version":1,"enabled":false,"can_save":false}""".toByteArray()))
        assertBad { MemoryBookEditionWire.decodeCapabilities(
            """{"version":1,"enabled":false,"can_save":true}""".toByteArray()) }
        assertBad { MemoryBookEditionWire.decodeCapabilities(
            """{"version":1,"enabled":true,"can_save":true,"extra":0}""".toByteArray()) }

        val proposal = proposal()
        assertEquals(bookId, proposal.bookId)
        assertEquals(7L, proposal.revision.toLong())
        assertEquals(chapterIds, proposal.manuscript.chapters.map { it.id })
        assertTrue(proposal.needsReview && proposal.manuscript.needsReview)
        assertBad { MemoryBookEditionWire.decodeProposal(
            proposalJson().toByteArray(), childOne, 7, jobId, children, chapterIds) }
        assertBad { MemoryBookEditionWire.decodeProposal(
            proposalJson(revision="0").toByteArray(), bookId, 7, jobId, children, chapterIds) }
        assertBad { MemoryBookEditionWire.decodeProposal(
            proposalJson(revision="07").toByteArray(), bookId, 7, jobId, children, chapterIds) }
        assertBad { MemoryBookEditionWire.decodeProposal(
            proposalJson(jobResultSha="A".repeat(64)).toByteArray(), bookId, 7, jobId, children, chapterIds) }
        assertBad { MemoryBookEditionWire.decodeProposal(
            proposalJson(needsReview="false").toByteArray(), bookId, 7, jobId, children, chapterIds) }
        assertBad { MemoryBookEditionWire.decodeProposal(
            proposalJson(extra=",\"forged\":true").toByteArray(), bookId, 7, jobId, children, chapterIds) }
        assertBad { MemoryBookEditionWire.decodeProposal(
            proposalJson(childrenJson="""[{"id":"$childOne","revision":"2"},{"id":"$childOne","revision":"1"}]""").toByteArray(),
            bookId, 7, jobId, children, chapterIds) }
        assertBad { MemoryBookEditionWire.decodeProposal(
            proposalJson(manuscriptJson=manuscript().replace(chapterIds[1], chapterIds[0])).toByteArray(),
            bookId, 7, jobId, children, chapterIds) }
    }

    @Test fun independentReaderDerivesChaptersWithinAllCurrentChildrenWithoutAJob() {
        val raw = detailJson("current", "7", manuscript()).toByteArray()
        assertEquals(chapterIds, MemoryBookEditionWire.decodeReadableDetail(raw, bookId, editionId, 7, children)
            .manuscript!!.chapters.map { it.id })
        listOf(
            manuscript().replace(chapterIds[0], "${childTwo}-chapter-2"),
            manuscript().replace(chapterIds[1], chapterIds[0]),
            manuscript().replace(childTwo, jobId),
            manuscript().replace("${childOne}-chapter-1", "${childOne}-chapter-2"),
        ).forEach { forged ->
            assertBad { MemoryBookEditionWire.decodeReadableDetail(
                detailJson("current", "7", forged).toByteArray(), bookId, editionId, 7, children) }
        }
        assertBad { MemoryBookEditionWire.decodeReadableDetail(raw, bookId, editionId, 7, children.reversed()) }
        assertBad { MemoryBookEditionWire.decodeReadableDetail(raw, bookId, editionId, 8, children) }
        assertBad { MemoryBookEditionWire.decodeReadableDetail(raw, bookId, editionId, 7, children + children.first()) }
        assertBad { MemoryBookEditionWire.decodeReadableDetail(raw, bookId, editionId, 7, emptyList()) }
        val changed = detailJson("source_changed", "6", "null").toByteArray()
        assertNull(MemoryBookEditionWire.decodeReadableDetail(changed, bookId, editionId, 7, emptyList()).manuscript)
        assertBad { MemoryBookEditionWire.decodeReadableDetail(
            detailJson("source_invalidated", "7", manuscript()).toByteArray(), bookId, editionId, 7, children) }
    }

    @Test fun saveRequestFreezesReviewIdentityAndRejectsNewOrDuplicateCitations() {
        val proposal = proposal()
        val revised = proposal.manuscript.copy(title = "一段新的回忆", chapters =
            proposal.manuscript.chapters.mapIndexed { i, chapter ->
                if (i == 0) chapter.copy(narration = "后来我们一起回到那里。") else chapter
            })
        val bodyOne = MemoryBookEditionWire.encodeSaveRequest(proposal, mutationId, revised, reviewed = true)
        val bodyTwo = MemoryBookEditionWire.encodeSaveRequest(proposal, mutationId, revised, reviewed = true)
        assertEquals(bodyOne, bodyTwo)
        assertTrue(bodyOne.toByteArray().size <= MemoryBookEditionWire.MAX_REQUEST_BYTES)
        val decoded = MemoryBookEditionWire.decodeSaveRequest(bodyOne.toByteArray(), proposal)
        assertTrue(decoded.reviewed)
        assertTrue(decoded.manuscript.needsReview)
        assertEquals(mutationId, decoded.mutationId)
        assertEquals("一段新的回忆", decoded.manuscript.title)
        assertEquals(revised.chapters, decoded.manuscript.chapters)

        val forgedSource = revised.copy(chapters = revised.chapters.mapIndexed { i, chapter ->
            if (i == 0) chapter.copy(sourceIds = listOf(sourceTwo)) else chapter
        })
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(proposal, mutationId, forgedSource, reviewed = true) }
        val duplicateSource = revised.copy(chapters = revised.chapters.mapIndexed { i, chapter ->
            if (i == 0) chapter.copy(sourceIds = listOf(sourceOne, sourceOne)) else chapter
        })
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(proposal, mutationId, duplicateSource, reviewed = true) }
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(proposal, "bad-id", revised, reviewed = true) }
    }

    @Test fun detailAndPageNeverExposeStaleOrInvalidatedText() {
        val current = detailJson(state = "current", revision = "7", manuscriptValue = manuscript())
        val decoded = MemoryBookEditionWire.decodeDetail(current.toByteArray(), bookId, editionId,
            currentBookRevision = 7, expectedChapterIds = chapterIds)
        assertEquals("回忆", decoded.manuscript?.title)
        val stale = MemoryBookEditionWire.decodeDetail(
            detailJson(state="source_changed", revision="6", manuscriptValue="null").toByteArray(),
            bookId, editionId, currentBookRevision = 7, expectedChapterIds = chapterIds)
        assertEquals(MemoryBookEditionState.SOURCE_CHANGED, stale.receipt.state)
        assertNull(stale.manuscript)
        val invalidated = MemoryBookEditionWire.decodeDetail(
            detailJson(state="source_invalidated", revision="7", manuscriptValue="null").toByteArray(),
            bookId, editionId, currentBookRevision = 7, expectedChapterIds = chapterIds)
        assertEquals(MemoryBookEditionState.SOURCE_INVALIDATED, invalidated.receipt.state)
        assertNull(invalidated.manuscript)
        assertBad { MemoryBookEditionWire.decodeDetail(
            detailJson(state="source_changed", revision="6", manuscriptValue=manuscript()).toByteArray(),
            bookId, editionId, currentBookRevision = 7, expectedChapterIds = chapterIds) }
        assertBad { MemoryBookEditionWire.decodeDetail(current.toByteArray(), childOne, editionId,
            currentBookRevision = 7, expectedChapterIds = chapterIds) }

        val row = """{"version":1,"id":"$editionId","book_id":"$bookId","book_revision":"7","created_at":100,"state":"source_invalidated","mutation_id":"$mutationId","manuscript":null}"""
        val page = """{"version":1,"book_id":"$bookId","page":1,"page_size":8,"has_more":false,"items":[$row]}"""
        val decodedPage = MemoryBookEditionWire.decodePage(page.toByteArray(), bookId, 1)
        assertNull(decodedPage.items.single().manuscript)
        assertEquals(MemoryBookEditionState.SOURCE_INVALIDATED, decodedPage.items.single().receipt.state)
        assertBad { MemoryBookEditionWire.decodePage(page.toByteArray(), childOne, 1) }
    }

    @Test fun parserRejectsDuplicateKeysMalformedUtf8AndOversize() {
        assertBad { MemoryBookEditionWire.decodeCapabilities(
            """{"version":1,"version":1,"enabled":true,"can_save":true}""".toByteArray()) }
        assertBad { MemoryBookEditionWire.decodeCapabilities(byteArrayOf(0xc3.toByte())) }
        assertBad { MemoryBookEditionWire.decodeProposal(ByteArray(512 * 1024 + 1),
            bookId, 7, jobId, children, chapterIds) }
    }

    @Test fun reviewIsIndependentAndConstructedProposalsCannotBypassValidation() {
        val p = proposal()
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(p, mutationId, reviewed = false) }
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(p.copy(children = listOf(children[0], children[0])), mutationId, reviewed = true) }
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(p.copy(children = children.map { it.copy(revision = "01") }), mutationId, reviewed = true) }
        val missingFirstChild = p.manuscript.copy(chapters = p.manuscript.chapters.drop(1))
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(p.copy(manuscript = missingFirstChild), mutationId, reviewed = true) }
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(p, mutationId, p.manuscript.copy(needsReview = false), reviewed = true) }
        val reordered = p.manuscript.copy(chapters = p.manuscript.chapters.reversed())
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(p.copy(manuscript = reordered), mutationId, reviewed = true) }
        val loneSurrogate = p.manuscript.copy(title = "\uD800")
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(p, mutationId, loneSurrogate, reviewed = true) }
        val alteredQuestions = p.manuscript.copy(questions = listOf("A newly invented question?"))
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(p, mutationId, alteredQuestions, reviewed = true) }
    }

    @Test fun invalidatedRetryReceiptIsContentFreeAndStillMatchesMutation() {
        val json = """{"version":1,"id":"$editionId","book_id":"$bookId","book_revision":"7","created_at":100,"state":"source_invalidated","mutation_id":"$mutationId"}"""
        val receipt = MemoryBookEditionWire.decodeReceipt(json.toByteArray(), bookId, mutationId, 7)
        assertEquals(MemoryBookEditionState.SOURCE_INVALIDATED, receipt.state)
        assertBad { MemoryBookEditionWire.decodeReceipt(json.replace("source_invalidated", "source_changed").toByteArray(), bookId, mutationId, 7) }
        assertBad { MemoryBookEditionWire.decodeReceipt(json.toByteArray(), bookId, jobId, 7) }
    }

    @Test fun aggregateManuscriptLimitIncludesJsonEscapesAndStructure() {
        val child = children[0]
        val ids = (1..6).map { "${child.id}-chapter-$it" }
        val chapters = ids.map { MemoryBookEditionChapter(it, "\t".repeat(5900), listOf(sourceOne)) }
        val p = proposal().copy(children = listOf(child), manuscript = MemoryBookEditionManuscript("Bounded", chapters, emptyList()))
        // Each narration meets 6000 bytes, but JSON escaping makes the whole manuscript exceed 64 KiB.
        assertInputRejected { MemoryBookEditionWire.encodeSaveRequest(p, mutationId, reviewed = true) }
    }

    private fun detailJson(state: String, revision: String, manuscriptValue: String) =
        """{"version":1,"id":"$editionId","book_id":"$bookId","book_revision":"$revision","created_at":100,"state":"$state","mutation_id":"$mutationId","manuscript":$manuscriptValue}"""

    private fun assertBad(block: () -> Unit) {
        try { block(); fail("expected invalid response") }
        catch (failure: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, failure.kind) }
    }

    private fun assertInputRejected(block: () -> Unit) {
        try { block(); fail("expected invalid input") }
        catch (_: IllegalArgumentException) { }
    }
}
