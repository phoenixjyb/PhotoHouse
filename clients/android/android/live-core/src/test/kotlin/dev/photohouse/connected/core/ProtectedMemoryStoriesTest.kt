package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test

class ProtectedMemoryStoriesTest {
    private val id = "11111111-1111-1111-1111-111111111111"
    private val familyEvidence = """{"id":"family-22222222-2222-2222-2222-222222222222","source":"family","title":"Grandma","text":"line 1\r\nline 2","revision":2}"""
    private val captionEvidence = """{"id":"caption-42","source":"family","title":"","text":""}"""
    private fun item(id: String, library: String = "family", evidence: String = "[]") =
        """{"id":"$id","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":"2024-05-01","thumbnail_url":"/assets/$id/thumbnail?library=$library","date_hint":null,"evidence":$evidence}"""
    private fun summary(id: String = this.id) =
        """{"id":"$id","title":"Garden day","theme":"everyday","language":"zh","revision":"3","cover_asset_id":"1","item_count":2,"chapter_count":1,"updated_at":1720000000,"can_edit":false}"""
    private fun page(items: String = summary()) =
        """{"library_id":"family","page":1,"page_size":8,"has_more":false,"can_create":false,"items":[$items]}"""
    private fun chapter(assetIds: String = "\"1\",\"2\"", evidenceIds: String = "\"family-22222222-2222-2222-2222-222222222222\"") =
        """{"id":"chapter-1","title":"The garden","narration":"A quiet afternoon. 奶奶在花园里。","asset_ids":[$assetIds],"evidence_ids":[$evidenceIds]}"""
    private fun detail(library: String = "family", items: String = "${item("1", evidence = "[$familyEvidence,$captionEvidence]")},${item("2")}", chapters: String = chapter()) =
        """{"version":1,"library_id":"$library","id":"$id","revision":"3","created_at":1710000000,"updated_at":1720000000,"can_edit":false,"saved":true,"state":"draft","generator":"family_edited_outline","needs_review":true,"selection_revision":"${"a".repeat(64)}","title":"Garden day","theme":"everyday","language":"zh","items":[$items],"chapters":[$chapters],"questions":[]}"""
    private fun contributionReferences(
        revision: String = "3", library: String = "family", chapterGroups: String =
            """{"id":"chapter-1","contribution_ids":["33333333-3333-3333-3333-333333333333"]},{"id":"chapter-2","contribution_ids":[]}""",
    ) = """{"version":1,"id":"$id","library_id":"$library","revision":"$revision","chapters":[$chapterGroups]}"""
    private fun invalid(block: () -> Unit) {
        try { block(); fail("invalid memory story was accepted") } catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }

    @Test fun parsesSavedSummaryAndDraftWithBothEvidenceKinds() {
        val parsedPage = ProtectedMemoryStoriesWire.page(page().toByteArray(), "family", 1)
        assertEquals(8, parsedPage.pageSize)
        assertEquals(id, parsedPage.items.single().id)
        val parsed = ProtectedMemoryStoriesWire.detail(detail().toByteArray(), "family", id, 3)
        assertEquals(listOf("1", "2"), parsed.chapters.single().assetIds)
        assertEquals("family", parsed.items.first().evidence.first().source)
        assertEquals("family", parsed.items.first().evidence.last().source)
        assertEquals("line 1\r\nline 2", parsed.items.first().evidence.first().text)
        assertEquals("", parsed.items.first().evidence.last().text)
        assertEquals("Garden day", parsed.title)
    }

    @Test fun acceptsLatestRevisionAndMaximumAsciiEvidenceText() {
        val longEvidence = """{"id":"family-22222222-2222-2222-2222-222222222222","source":"family","title":"${"t".repeat(160)}","text":"${"x".repeat(1800)}","revision":2}"""
        val raw = detail(items = "${item("1", evidence = "[$longEvidence]")},${item("2")}")
        val parsed = ProtectedMemoryStoriesWire.detail(raw.replace("\"revision\":\"3\"", "\"revision\":\"4\"", false).toByteArray(), "family", id, 3)
        assertEquals(4, parsed.revision)
        assertEquals(1800, parsed.items.first().evidence.single().text.length)
    }

    @Test fun rejectsCrossLibraryReferencesUnknownKeysWrongOrderingAndMismatchedRevision() {
        invalid { ProtectedMemoryStoriesWire.page(page().replace("\"family\"", "\"other\"", false).toByteArray(), "family", 1) }
        invalid { ProtectedMemoryStoriesWire.page(page(summary() + "," + summary()).toByteArray(), "family", 1) }
        invalid { ProtectedMemoryStoriesWire.detail(detail(library = "other").toByteArray(), "family", id, 3) }
        invalid { ProtectedMemoryStoriesWire.detail(detail(chapters = chapter("\"2\",\"1\"", "")).toByteArray(), "family", id, 3) }
        invalid { ProtectedMemoryStoriesWire.detail(detail(chapters = chapter("\"1\",\"3\"", "")).toByteArray(), "family", id, 3) }
        invalid { ProtectedMemoryStoriesWire.detail(detail().replace("\"revision\":\"3\"", "\"revision\":\"03\"", false).toByteArray(), "family", id, 3) }
        invalid { ProtectedMemoryStoriesWire.detail(detail().replace("\"can_edit\":false", "\"can_edit\":\"false\"", false).toByteArray(), "family", id, 3) }
        invalid { ProtectedMemoryStoriesWire.detail(detail(chapters = chapter("\"1\",\"2\"", "\"caption-99\"")).toByteArray(), "family", id, 3) }
        invalid { ProtectedMemoryStoriesWire.detail(detail().replace("\"questions\":[]", "\"questions\":[],\"extra\":true").toByteArray(), "family", id, 3) }
    }

    @Test fun enforcesThumbnailScopeAndUtf8NarrationLimit() {
        invalid { ProtectedMemoryStoriesWire.detail(detail(items = item("1", library = "other") + ",${item("2")}").toByteArray(), "family", id, 3) }
        val tooManyBytes = "你".repeat(2001)
        invalid { ProtectedMemoryStoriesWire.detail(detail(chapters = chapter().replace("A quiet afternoon. 奶奶在花园里。", tooManyBytes)).toByteArray(), "family", id, 3) }
        invalid { ProtectedMemoryStoriesWire.detail(detail(chapters = chapter().replace("A quiet afternoon. 奶奶在花园里。", "\\uD800")).toByteArray(), "family", id, 3) }
    }

    @Test fun parsesAdditiveCurrentRevisionContributionReferenceSidecarWithoutChangingLegacyStoryShape() {
        val parsed = ProtectedMemoryStoriesWire.contributionReferences(contributionReferences().toByteArray(),
            "family", id, 3, listOf("chapter-1", "chapter-2"))
        assertEquals(id, parsed.id)
        assertEquals("family", parsed.libraryId)
        assertEquals(3L, parsed.revision)
        assertEquals(listOf("33333333-3333-3333-3333-333333333333"), parsed.chapters.first().contributionIds)
        assertTrue(parsed.chapters.last().contributionIds.isEmpty())
        // The base v1 response continues to be decoded only by its unchanged exact-key parser.
        assertEquals("Garden day", ProtectedMemoryStoriesWire.detail(detail().toByteArray(), "family", id, 3).title)
    }

    @Test fun rejectsMalformedContributionReferenceSidecarShapeScopeRevisionOrderAndIds() {
        val expected = listOf("chapter-1", "chapter-2")
        invalid { ProtectedMemoryStoriesWire.contributionReferences(contributionReferences().replace("\"version\":1,", "\"version\":1,\"extra\":true,").toByteArray(), "family", id, 3, expected) }
        invalid { ProtectedMemoryStoriesWire.contributionReferences(contributionReferences(revision = "2").toByteArray(), "family", id, 3, expected) }
        invalid { ProtectedMemoryStoriesWire.contributionReferences(contributionReferences(library = "other").toByteArray(), "family", id, 3, expected) }
        invalid { ProtectedMemoryStoriesWire.contributionReferences(contributionReferences(chapterGroups = """{"id":"chapter-2","contribution_ids":[]},{"id":"chapter-1","contribution_ids":[]}""").toByteArray(), "family", id, 3, expected) }
        invalid { ProtectedMemoryStoriesWire.contributionReferences(contributionReferences(chapterGroups = """{"id":"chapter-1","contribution_ids":["33333333-3333-3333-3333-333333333333","33333333-3333-3333-3333-333333333333"]},{"id":"chapter-2","contribution_ids":[]}""").toByteArray(), "family", id, 3, expected) }
        invalid { ProtectedMemoryStoriesWire.contributionReferences(contributionReferences(chapterGroups = """{"id":"chapter-1","contribution_ids":["contribution-33333333-3333-3333-3333-333333333333"]},{"id":"chapter-2","contribution_ids":[]}""").toByteArray(), "family", id, 3, expected) }
        invalid { ProtectedMemoryStoriesWire.contributionReferences(contributionReferences(chapterGroups = """{"id":"chapter-1","contribution_ids":[]},{"id":"chapter-3","contribution_ids":[]}""").toByteArray(), "family", id, 3, expected) }
    }
}
