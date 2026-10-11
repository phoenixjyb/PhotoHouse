package dev.photohouse.connected.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.*
import org.junit.Test

class ProtectedStoryWorkspaceTest {
    private val selectionRevision = "a".repeat(64)
    private val familyEvidence = """{"id":"family-11111111-1111-1111-1111-111111111111","source":"family","title":"Garden","text":"The family planted flowers.","revision":2}"""
    private val titleOnlyEvidence = """{"id":"family-22222222-2222-2222-2222-222222222222","source":"family","title":"Garden note","text":"","revision":2}"""
    private val captionEvidence = """{"id":"caption-101","source":"ai","title":"","text":"A garden in spring."}"""
    private val sharedEvidence = """{"id":"family-33333333-3333-4333-8333-333333333333","source":"family","title":"Grandma's note","text":"We shared this memory.","revision":4,"origin_asset_id":"99","byline":"<script>Grandma</script> & family"}"""

    private fun item(id: String, kind: String, evidence: String = "[]", library: String = "family") =
        """{"id":"$id","kind":"$kind","width":800,"height":600,"duration_sec":${if (kind == "video") "12.5" else "null"},"taken_at":"2024-05-01","thumbnail_url":"/assets/$id/thumbnail?library=$library","date_hint":null,"evidence":$evidence}"""

    private fun chapter(id: Int = 1, assetIds: String = "\"1\",\"2\"", evidenceIds: String = "\"caption-101\"") =
        """{"id":"chapter-$id","title":"Garden","narration":"A family day.","asset_ids":[$assetIds],"evidence_ids":[$evidenceIds]}"""

    private fun preview(
        library: String = "family",
        items: String = "${item("1", "image", "[$familyEvidence,$captionEvidence]")},${item("2", "video")} ",
        chapters: String = chapter(),
        questions: String = "[]",
        title: String = "Garden day",
    ) = """{"version":1,"library_id":"$library","selection_revision":"$selectionRevision","state":"draft","saved":false,"title":"$title","theme":"everyday","language":"en","generator":"evidence_outline","needs_review":true,"items":[$items],"chapters":[$chapters],"questions":$questions}"""

    private fun itemRows(ids: List<String>) = ids.mapIndexed { index, id ->
        item(id, if (index % 2 == 0) "image" else "video", if (id == "1") "[$familyEvidence,$captionEvidence]" else "[]")
    }.joinToString(",")

    private fun draftChapter(number: Int, assetIds: List<String>) =
        """{"id":"chapter-$number","title":"Section $number","narration":"","asset_ids":${kotlinx.serialization.json.JsonArray(assetIds.map { kotlinx.serialization.json.JsonPrimitive(it) })},"evidence_ids":[]}"""

    private fun badResponse(block: () -> Unit) {
        try { block(); fail("invalid workspace response was accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }

    private fun badInput(block: () -> Unit) {
        try { block(); fail("invalid workspace request was accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
    }

    @Test fun decodesUnsavedMixedMediaDraftWithOrderedChapterCoverage() {
        val draft = ProtectedStoryWorkspaceWire.decodePreview(preview().toByteArray(), "family", listOf("1", "2"), "everyday", "en")
        assertEquals("family", draft.libraryId)
        assertEquals(selectionRevision, draft.selectionRevision)
        assertEquals(listOf("image", "video"), draft.items.map { it.asset.kind })
        assertEquals(listOf("1", "2"), draft.chapters.single().assetIds)
        assertEquals(listOf("caption-101"), draft.chapters.single().evidenceIds)
        assertEquals("Garden day", draft.title)
        assertFalse("saved drafts must not look like saved stories", preview().contains("\"saved\":true"))
    }

    @Test fun previewRequestPreservesManualTitleExactlyAndValidatesSelection() {
        val request = ProtectedStoryWorkspaceWire.encodePreviewRequest(listOf("1", "2"), "trip", "zh", " 手写标题 ")
        val json = Json.parseToJsonElement(request).jsonObject
        assertEquals(setOf("asset_ids", "theme", "language", "title"), json.keys)
        assertEquals("1,2", json.getValue("asset_ids").jsonPrimitive.content)
        assertEquals(" 手写标题 ", json.getValue("title").jsonPrimitive.content)
        val maxTitle = "😀".repeat(160)
        assertEquals(maxTitle, Json.parseToJsonElement(ProtectedStoryWorkspaceWire
            .encodePreviewRequest(listOf("1"), "trip", "zh", maxTitle)).jsonObject.getValue("title").jsonPrimitive.content)
        badInput { ProtectedStoryWorkspaceWire.encodePreviewRequest(listOf("01"), "trip", "zh", "title") }
        badInput { ProtectedStoryWorkspaceWire.encodePreviewRequest(listOf("1", "1"), "trip", "zh", "title") }
        badInput { ProtectedStoryWorkspaceWire.encodePreviewRequest(emptyList(), "trip", "zh", "title") }
        badInput { ProtectedStoryWorkspaceWire.encodePreviewRequest(listOf("1"), "unknown", "zh", "title") }
        badInput { ProtectedStoryWorkspaceWire.encodePreviewRequest(listOf("1"), "trip", "fr", "title") }
        badInput { ProtectedStoryWorkspaceWire.encodePreviewRequest(listOf("1"), "trip", "zh", "bad\nline") }
    }

    @Test fun previewRejectsDuplicateKeysWrongLibraryAndChangedSelectionOrder() {
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview().replace("\"version\":1", "\"version\":1,\"version\":1").toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview(library = "other").toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview().toByteArray(), "family", listOf("2", "1")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview().replace("\"saved\":false", "\"saved\":true").toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview().replace("\"selection_revision\":\"$selectionRevision\"", "\"selection_revision\":\"${"A".repeat(64)}\"").toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview().toByteArray(), "family", listOf("1", "2"), "trip", "en") }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview().toByteArray(), "family", listOf("1", "2"), "everyday", "zh") }
    }

    @Test fun previewRequiresExactOrderedChaptersOneTimeCoverageAndKnownEvidence() {
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview(chapters = chapter(assetIds = "\"2\",\"1\"", evidenceIds = "")).toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview(chapters = chapter(assetIds = "\"1\"", evidenceIds = "")).toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview(chapters = "${chapter()},${chapter(2, "\"2\"", "")}").toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview(chapters = chapter(evidenceIds = "\"caption-999\"")).toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview(chapters = chapter(id = 2)).toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(preview(chapters = chapter(assetIds = "\"1\",\"2\",\"1\"")).toByteArray(), "family", listOf("1", "2")) }
    }

    @Test fun fiveSelectedAssetsRequireExactFourThenOneChapterGrouping() {
        val ids = listOf("1", "2", "3", "4", "5")
        val validChapters = listOf(draftChapter(1, ids.take(4)), draftChapter(2, ids.drop(4))).joinToString(",")
        val valid = ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = itemRows(ids), chapters = validChapters).toByteArray(), "family", ids)
        assertEquals(listOf(ids.take(4), ids.drop(4)), valid.chapters.map { it.assetIds })

        val wrongSplit = listOf(draftChapter(1, ids.take(2)), draftChapter(2, ids.drop(2))).joinToString(",")
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = itemRows(ids), chapters = wrongSplit).toByteArray(), "family", ids) }
    }

    @Test fun acceptsConsistentSharedEvidenceAndRejectsConflictsOrInvalidAttribution() {
        val sharedItems = "${item("1", "image", "[$sharedEvidence]")},${item("2", "video", "[$sharedEvidence]")}"
        val accepted = ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = sharedItems, chapters = chapter(evidenceIds = "\"family-33333333-3333-4333-8333-333333333333\"")).toByteArray(),
            "family", listOf("1", "2"))
        val first = accepted.items.first().evidence.single()
        assertEquals("99", first.originAssetId)
        assertEquals("<script>Grandma</script> & family", first.byline)
        assertEquals(first, accepted.items.last().evidence.single())

        val conflict = sharedEvidence.replace("We shared this memory.", "Different payload")
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = "${item("1", "image", "[$sharedEvidence]")},${item("2", "video", "[$conflict]")}",
                chapters = chapter(evidenceIds = "\"family-33333333-3333-4333-8333-333333333333\"")).toByteArray(),
            "family", listOf("1", "2")) }
        val repeatedCaption = """{"id":"caption-101","source":"ai","title":"","text":"A garden in spring."}"""
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = "${item("1", "image", "[$repeatedCaption]")},${item("2", "video", "[$repeatedCaption]")}",
                chapters = chapter(assetIds = "\"1\",\"2\"", evidenceIds = "\"caption-101\"")).toByteArray(),
            "family", listOf("1", "2")) }
        val legacyFamily = sharedEvidence.substringBefore(",\"origin_asset_id\"") + "}"
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = "${item("1", "image", "[$legacyFamily]")},${item("2", "video", "[$legacyFamily]")}",
                chapters = chapter(assetIds = "\"1\",\"2\"", evidenceIds = "\"family-33333333-3333-4333-8333-333333333333\"")).toByteArray(),
            "family", listOf("1", "2")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = item("1", "image", "[$sharedEvidence,$sharedEvidence]"), chapters = chapter(assetIds = "\"1\"", evidenceIds = "")).toByteArray(),
            "family", listOf("1")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = item("1", "image", "[${sharedEvidence.replace(",\"byline\":\"<script>Grandma</script> & family\"", "")}]"),
                chapters = chapter(assetIds = "\"1\"", evidenceIds = "")).toByteArray(),
            "family", listOf("1")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = item("1", "image", "[${sharedEvidence.replace("\"origin_asset_id\":\"99\"", "\"origin_asset_id\":\"01\"")}]"), chapters = chapter(assetIds = "\"1\"", evidenceIds = "")).toByteArray(),
            "family", listOf("1")) }
        badResponse { ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = item("1", "image", "[${sharedEvidence.replace("<script>Grandma</script> & family", "你".repeat(86))}]"), chapters = chapter(assetIds = "\"1\"", evidenceIds = "")).toByteArray(),
            "family", listOf("1")) }
    }

    @Test fun acceptsTwelveEvidenceEntriesOnOneItem() {
        val evidence = (1..12).joinToString(",") { index ->
            """{"id":"caption-$index","source":"ai","title":"","text":"Observation $index"}"""
        }
        val result = ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = item("1", "image", "[$evidence]"), chapters = chapter(assetIds = "\"1\"", evidenceIds = "")).toByteArray(),
            "family", listOf("1"))
        assertEquals(12, result.items.single().evidence.size)
    }

    @Test fun titleCapabilitiesAndCandidatesAreBoundedReviewedAndSourceScoped() {
        assertEquals(ProtectedStoryWorkspaceTitleCapabilities(true, 3),
            ProtectedStoryWorkspaceWire.decodeTitleCapabilities(
                """{"version":1,"enabled":true,"max_suggestions":3,"needs_review":true}""".toByteArray()))
        badResponse { ProtectedStoryWorkspaceWire.decodeTitleCapabilities(
            """{"version":1,"enabled":true,"max_suggestions":2,"needs_review":true}""".toByteArray()) }
        val draft = ProtectedStoryWorkspaceWire.decodePreview(preview().toByteArray(), "family", listOf("1", "2"))
        val titles = ProtectedStoryWorkspaceWire.decodeTitles(
            """{"version":1,"selection_revision":"$selectionRevision","titles":[{"text":"Garden memories","source_ids":["caption-101","draft-chapter-1"]},{"text":"Spring together","source_ids":["family-11111111-1111-1111-1111-111111111111"]}],"needs_review":true}""".toByteArray(), draft)
        assertEquals(listOf("Garden memories", "Spring together"), titles.map { it.text })
        badResponse { ProtectedStoryWorkspaceWire.decodeTitles(
            """{"version":1,"selection_revision":"${"b".repeat(64)}","titles":[],"needs_review":true}""".toByteArray(), draft) }
        badResponse { ProtectedStoryWorkspaceWire.decodeTitles(
            """{"version":1,"selection_revision":"$selectionRevision","titles":[{"text":"Other source","source_ids":["foreign-101"]}],"needs_review":true}""".toByteArray(), draft) }
        badResponse { ProtectedStoryWorkspaceWire.decodeTitles(
            """{"version":1,"selection_revision":"$selectionRevision","titles":[{"text":"Line\nbreak","source_ids":["caption-101"]}],"needs_review":true}""".toByteArray(), draft) }
        badResponse { ProtectedStoryWorkspaceWire.decodeTitles(
            """{"version":1,"selection_revision":"$selectionRevision","titles":[{"text":"bad\u0085title","source_ids":["caption-101"]}],"needs_review":true}""".toByteArray(), draft) }
        badResponse { ProtectedStoryWorkspaceWire.decodeTitles(
            """{"version":1,"selection_revision":"$selectionRevision","titles":[{"text":"bad\u2028title","source_ids":["caption-101"]}],"needs_review":true}""".toByteArray(), draft) }
        val titleOnlyDraft = ProtectedStoryWorkspaceWire.decodePreview(
            preview(items = "${item("1", "image", "[$titleOnlyEvidence]")},${item("2", "video")}", chapters = chapter(evidenceIds = "")).toByteArray(),
            "family", listOf("1", "2"))
        badResponse { ProtectedStoryWorkspaceWire.decodeTitles(
            """{"version":1,"selection_revision":"$selectionRevision","titles":[{"text":"Garden note","source_ids":["family-22222222-2222-2222-2222-222222222222"]}],"needs_review":true}""".toByteArray(), titleOnlyDraft) }
        badResponse { ProtectedStoryWorkspaceWire.decodeTitles(
            """{"version":1,"selection_revision":"$selectionRevision","titles":[{"text":"${"你".repeat(161)}","source_ids":["caption-101"]}],"needs_review":true}""".toByteArray(), draft) }
    }

    @Test fun titleRequestRetainsExactEditedNarrationAndRejectsOversizeOrWrongChapterOrder() {
        val narration = "Manual narration. 手工叙述。"
        val request = ProtectedStoryWorkspaceWire.encodeTitleRequest(
            listOf("1", "2"), "everyday", "zh", selectionRevision,
            listOf(ProtectedStoryWorkspaceChapterInput("chapter-1", narration)),
        )
        val body = Json.parseToJsonElement(request).jsonObject
        assertEquals(setOf("asset_ids", "theme", "language", "selection_revision", "chapters"), body.keys)
        assertEquals(narration, Json.parseToJsonElement(body.getValue("chapters").jsonPrimitive.content)
            .jsonArray.single().jsonObject.getValue("narration").jsonPrimitive.content)
        badInput { ProtectedStoryWorkspaceWire.encodeTitleRequest(listOf("1"), "everyday", "zh", selectionRevision,
            listOf(ProtectedStoryWorkspaceChapterInput("chapter-2", "text"))) }
        badInput { ProtectedStoryWorkspaceWire.encodeTitleRequest(listOf("1"), "everyday", "zh", selectionRevision,
            listOf(ProtectedStoryWorkspaceChapterInput("chapter-1", "x".repeat(6001)))) }
        badInput { ProtectedStoryWorkspaceWire.encodeTitleRequest(listOf("1", "2", "3", "4", "5"), "everyday", "zh", selectionRevision,
            listOf(ProtectedStoryWorkspaceChapterInput("chapter-1", narration))) }
        val groupedRequest = ProtectedStoryWorkspaceWire.encodeTitleRequest(listOf("1", "2", "3", "4", "5"), "everyday", "zh", selectionRevision,
            listOf(ProtectedStoryWorkspaceChapterInput("chapter-1", narration), ProtectedStoryWorkspaceChapterInput("chapter-2", "")))
        assertEquals("1,2,3,4,5", Json.parseToJsonElement(groupedRequest).jsonObject.getValue("asset_ids").jsonPrimitive.content)
        val reviewedRequest = ProtectedStoryWorkspaceWire.encodeTitleRequest(listOf("1", "2"), "everyday", "zh", selectionRevision,
            listOf(ProtectedStoryWorkspaceChapterInput("chapter-1", narration, emptyList())), "chapter_sources_v1")
        val reviewed = Json.parseToJsonElement(reviewedRequest).jsonObject
        assertEquals("chapter_sources_v1", reviewed.getValue("source_policy").jsonPrimitive.content)
        assertEquals(emptyList<String>(), Json.parseToJsonElement(reviewed.getValue("chapters").jsonPrimitive.content)
            .jsonArray.single().jsonObject.getValue("evidence_ids").jsonArray.map { it.jsonPrimitive.content })
        assertEquals(ProtectedStoryWorkspaceSourceCapabilities("chapter_sources_v1", 12),
            ProtectedStoryWorkspaceWire.decodeSourceCapabilities("""{"version":1,"source_policy":"chapter_sources_v1","max_sources_per_chapter":12,"needs_review":true}""".toByteArray()))
        badResponse { ProtectedStoryWorkspaceWire.decodeSourceCapabilities("""{"version":1,"source_policy":"chapter_sources_v1","max_sources_per_chapter":11,"needs_review":true}""".toByteArray()) }
        badInput { ProtectedStoryWorkspaceWire.encodeTitleRequest(listOf("1"), "everyday", "zh", "bad", emptyList()) }
    }
}
