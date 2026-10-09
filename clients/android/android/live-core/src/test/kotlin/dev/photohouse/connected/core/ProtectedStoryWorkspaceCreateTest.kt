package dev.photohouse.connected.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

class ProtectedStoryWorkspaceCreateTest {
    private val revision = "a".repeat(64)
    private val storyId = "11111111-1111-1111-1111-111111111111"
    private val evidence = (1..5).map { n ->
        """{"id":"caption-$n","source":"ai","title":"","text":"source $n"}"""
    }

    private fun item(id: Int) =
        """{"id":"$id","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":"2024-05-01","thumbnail_url":"/assets/$id/thumbnail?library=family","date_hint":null,"evidence":[${evidence[id - 1]}]}"""

    private fun chapter(number: Int, ids: List<Int>) =
        """{"id":"chapter-$number","title":"Section $number","narration":"Draft $number","asset_ids":[${ids.joinToString(",") { "\"$it\"" }}],"evidence_ids":["caption-${ids.first()}"]}"""

    private fun preview(ids: List<Int> = (1..5).toList(), revision: String = this.revision) =
        """{"version":1,"library_id":"family","selection_revision":"$revision","state":"draft","saved":false,"title":"Draft title","theme":"everyday","language":"zh","generator":"evidence_outline","needs_review":true,"items":[${ids.joinToString(",") { item(it) }}],"chapters":[${ids.chunked(4).mapIndexed { index, group -> chapter(index + 1, group) }.joinToString(",")}],"questions":[]}"""

    private fun draft(ids: List<Int> = (1..5).toList()) = ProtectedStoryWorkspaceWire.decodePreview(
        preview(ids).toByteArray(), "family", ids.map(Int::toString), "everyday", "zh")

    private fun edits(current: ProtectedStoryWorkspaceDraft, title: String = "手工标题") = current.chapters.map {
        it.copy(title = title, narration = "手工叙述 ${it.id}")
    }

    private fun badInput(block: () -> Unit) {
        try { block(); fail("invalid create input was accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_INPUT, e.kind) }
    }

    private fun badResponse(block: () -> Unit) {
        try { block(); fail("invalid create response was accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }

    @Test fun emitsExactEightStringFieldsAndPreservesChapterAndSelectionOrder() {
        val current = draft()
        val mutation = UUID.fromString("22222222-2222-2222-2222-222222222222")
        val bodyString = ProtectedStoryWorkspaceCreateWire.encode(current, "手工标题", edits(current), mutation.toString())
        val body = Json.parseToJsonElement(bodyString).jsonObject
        assertEquals(setOf("title", "theme", "language", "asset_ids", "chapters", "selection_revision", "revision", "mutation_id"), body.keys)
        assertTrue(body.values.all { it.jsonPrimitive.isString })
        assertEquals("1,2,3,4,5", body.getValue("asset_ids").jsonPrimitive.content)
        assertEquals("手工标题", body.getValue("title").jsonPrimitive.content)
        assertEquals("0", body.getValue("revision").jsonPrimitive.content)
        assertEquals(mutation.toString(), body.getValue("mutation_id").jsonPrimitive.content)
        assertEquals(revision, body.getValue("selection_revision").jsonPrimitive.content)
        val chapters = Json.parseToJsonElement(body.getValue("chapters").jsonPrimitive.content).jsonArray
        assertEquals(listOf("chapter-1", "chapter-2"), chapters.map { it.jsonObject.getValue("id").jsonPrimitive.content })
        assertEquals(listOf("1", "2", "3", "4"), chapters.first().jsonObject.getValue("asset_ids").jsonArray.map { it.jsonPrimitive.content })
        assertEquals(listOf("5"), chapters.last().jsonObject.getValue("asset_ids").jsonArray.map { it.jsonPrimitive.content })
        assertEquals(listOf("caption-1", "caption-5"), chapters.map { it.jsonObject.getValue("evidence_ids").jsonArray.single().jsonPrimitive.content })
        assertEquals("手工叙述 chapter-1", chapters.first().jsonObject.getValue("narration").jsonPrimitive.content)
        assertFalse(bodyString.contains("author"))
    }

    @Test fun acceptsUnicodeAtCodePointAndUtf8LimitsAndKeepsSnapshotPrivateAndImmutable() {
        val current = draft(listOf(1))
        val maxTitle = "😀".repeat(160)
        val maxNarration = "你".repeat(2000)
        val edit = listOf(current.chapters.single().copy(title = maxTitle, narration = maxNarration))
        val body = ProtectedStoryWorkspaceCreateWire.encode(current, maxTitle, edit,
            "22222222-2222-2222-2222-222222222222")
        assertTrue(body.contains("\\ud83d\\ude00") || body.contains("😀"))
        val create = ProtectedStoryWorkspaceCreate.create(current.selectionRevision, maxTitle,
            current.theme, current.language, edit, UUID.fromString("22222222-2222-2222-2222-222222222222"))
        assertEquals(160, create.title.codePointCount(0, create.title.length))
        assertTrue(create.toString().contains("content=[redacted]"))
        assertFalse(create.toString().contains(maxTitle))
        @Suppress("UNCHECKED_CAST")
        try { (create.chapters as MutableList<SavedMemoryStoryChapter>).clear(); fail("chapter snapshot was mutable") }
        catch (_: UnsupportedOperationException) { }
        @Suppress("UNCHECKED_CAST")
        try { (create.chapters.single().assetIds as MutableList<String>).clear(); fail("nested snapshot was mutable") }
        catch (_: UnsupportedOperationException) { }
        assertEquals("1", create.assetIds.single())
        badInput { ProtectedStoryWorkspaceCreateWire.encode(current, "😀".repeat(161), edit, UUID.randomUUID().toString()) }
        badInput { ProtectedStoryWorkspaceCreateWire.encode(current, "title", listOf(edit.single().copy(narration = "你".repeat(2001))), UUID.randomUUID().toString()) }
    }

    @Test fun rejectsWrongEditOrderInvalidCurrentCitationsAndMalformedIds() {
        val current = draft()
        badInput { ProtectedStoryWorkspaceCreateWire.encode(current, "title", edits(current).reversed(), UUID.randomUUID().toString()) }
        val badCitation = current.copy(chapters = current.chapters.mapIndexed { index, chapter ->
            if (index == 0) chapter.copy(evidenceIds = listOf("caption-5")) else chapter
        })
        badInput { ProtectedStoryWorkspaceCreateWire.encode(badCitation, "title", edits(badCitation), UUID.randomUUID().toString()) }
        val malformedId = current.copy(chapters = current.chapters.mapIndexed { index, chapter ->
            if (index == 0) chapter.copy(assetIds = listOf("01", "2", "3", "4")) else chapter
        })
        badInput { ProtectedStoryWorkspaceCreateWire.encode(malformedId, "title", edits(current), UUID.randomUUID().toString()) }
        val staleRevision = current.copy(selectionRevision = "A".repeat(64))
        badInput { ProtectedStoryWorkspaceCreateWire.encode(staleRevision, "title", edits(current), UUID.randomUUID().toString()) }
    }

    private fun savedResponse(revision: String = "4", library: String = "family") =
        """{"version":1,"library_id":"$library","id":"$storyId","revision":"$revision","created_at":1710000000,"updated_at":1720000000,"can_edit":true,"saved":true,"state":"draft","generator":"family_edited_outline","needs_review":true,"selection_revision":"${"b".repeat(64)}","title":"Garden day","theme":"everyday","language":"zh","items":[{"id":"1","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":"2024-05-01","thumbnail_url":"/assets/1/thumbnail?library=family","date_hint":null,"evidence":[]},{"id":"2","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":"2024-05-01","thumbnail_url":"/assets/2/thumbnail?library=family","date_hint":null,"evidence":[]}],"chapters":[{"id":"chapter-1","title":"Garden","narration":"A family day.","asset_ids":["1","2"],"evidence_ids":[]}],"questions":[]}"""
    @Test fun createResponseAcceptsCurrentNewerRetryRevisionAndChecksLibraryAndOrderedSelection() {
        badResponse { ProtectedMemoryStoriesWire.decode((savedResponse() + " ".repeat(256 * 1024)).toByteArray(), "family", listOf("1", "2")) }
        val parsed = ProtectedMemoryStoriesWire.decode(savedResponse().toByteArray(), "family", listOf("1", "2"))
        assertEquals(storyId, parsed.id)
        assertEquals(4L, parsed.revision)
        badResponse { ProtectedMemoryStoriesWire.decode(savedResponse(library = "other").toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedMemoryStoriesWire.decode(savedResponse().toByteArray(), "family", listOf("2", "1")) }
        badResponse { ProtectedMemoryStoriesWire.decode(savedResponse(revision = "0").toByteArray(), "family", listOf("1", "2")) }
        badResponse { ProtectedMemoryStoriesWire.decode(savedResponse().replace("\"questions\":[]", "\"questions\":[],\"extra\":true").toByteArray(), "family", listOf("1", "2")) }
    }
}
