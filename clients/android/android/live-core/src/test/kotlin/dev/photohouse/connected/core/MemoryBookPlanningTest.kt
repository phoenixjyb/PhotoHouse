package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test
import kotlinx.serialization.json.*

class MemoryBookPlanningTest {
    private val book = "44444444-4444-4444-8444-444444444444"
    private val story = "11111111-1111-4111-8111-111111111111"

    private fun response(
        editorial: Boolean = false,
        bookId: String = book,
        revision: String = "4",
        wholeState: String = "within_limits",
        contextBytes: String = if (wholeState == "within_limits") "2048" else "null",
        sourceCount: String = if (wholeState == "within_limits") "2" else "null",
        sourceKinds: String = if (wholeState == "within_limits") "{\"family\":1,\"metadata\":1}" else "null",
        sectionSourceCount: String = "2",
        sectionSourceKinds: String = "{\"family\":1,\"metadata\":1}",
        chapterCount: Int = 1,
        itemCount: Int = 2,
        distinctItemCount: Int = 2,
        contextProfile: String = "memoir_editorial_v1",
        title: String = "Garden day",
    ): String {
        val wholeContext = if (editorial) ",\"context_bytes\":$contextBytes" else ""
        val profile = if (editorial) ",\"context_profile\":\"$contextProfile\"" else ""
        return """{"version":1,"target_type":"book","target_id":"$bookId","revision":"$revision","can_edit":true,
            "kind":"saved_structure_plan","generated":false,"queued":false,"needs_review":true,
            "story_count":1,"chapter_count":$chapterCount,"item_count":$itemCount,"distinct_item_count":$distinctItemCount,
            "limits":{"chapters":24,"sources":96,"context_bytes":65536},
            "whole":{"state":"$wholeState","can_draft":${wholeState == "within_limits"},"source_count":$sourceCount,"source_kinds":$sourceKinds$wholeContext},
            "sections":[{"position":1,"id":"$story","revision":"7","title":"$title","item_count":2,"can_edit":true,
                "chapters":[{"id":"chapter-1","title":"Morning","item_count":2}],
                "state":"within_limits","can_draft":true,"source_count":$sectionSourceCount,"source_kinds":$sectionSourceKinds}]$profile}""".replace("\n", "").replace("            ", "")
    }

    private fun decode(raw: String, editorial: Boolean = false) =
        MemoryBookPlanWire.decode(raw.toByteArray(), book, 4, editorial)

    private fun reject(raw: String, editorial: Boolean = false, expectedBook: String = book, revision: Long = 4) {
        try {
            MemoryBookPlanWire.decode(raw.toByteArray(), expectedBook, revision, editorial)
            fail("invalid book planning response was accepted")
        } catch (failure: ApiFailure) {
            assertEquals(FailureKind.INVALID_RESPONSE, failure.kind)
        }
    }

    @Test fun parsesLegacyPlanWithoutEditorialOnlyFields() {
        val plan = decode(response())
        assertEquals("book", plan.targetType)
        assertEquals(book, plan.targetId)
        assertEquals(4L, plan.revision)
        assertEquals("saved_structure_plan", plan.kind)
        assertFalse(plan.generated)
        assertFalse(plan.queued)
        assertTrue(plan.needsReview)
        assertEquals(1, plan.storyCount)
        assertEquals(1, plan.chapterCount)
        assertEquals(2, plan.itemCount)
        assertEquals(2, plan.distinctItemCount)
        assertEquals("within_limits", plan.whole.state)
        assertNull(plan.whole.contextBytes)
        assertNull(plan.contextProfile)
        assertEquals("Garden day", plan.sections.single().title)
        assertEquals(7L, plan.sections.single().revision)
        assertEquals(1, plan.sections.single().chapters.size)
    }

    @Test fun editorialPlanRequiresProfileAndBoundedContextBytes() {
        val plan = decode(response(editorial = true), editorial = true)
        assertEquals("memoir_editorial_v1", plan.contextProfile)
        assertEquals(2048, plan.whole.contextBytes)
        assertEquals("within_limits", plan.whole.state)
        assertEquals(2, plan.whole.sourceCount)
        assertEquals(1, plan.whole.sourceKinds?.get("family"))

        val oversized = response(editorial = true, contextBytes = "65537")
        reject(oversized, editorial = true)
        reject(response(editorial = true, contextProfile = "memoir_editorial_v2"), editorial = true)
        reject(response(), editorial = true)
        reject(response(editorial = true), editorial = false)
    }

    @Test fun smallerScopeHasOnlyNullCapacityCountsAndBytes() {
        val plan = decode(response(editorial = true, wholeState = "smaller_scope_required",
            contextBytes = "null", sourceCount = "null", sourceKinds = "null"), editorial = true)
        assertEquals("smaller_scope_required", plan.whole.state)
        assertFalse(plan.whole.canDraft)
        assertNull(plan.whole.sourceCount)
        assertNull(plan.whole.sourceKinds)
        assertNull(plan.whole.contextBytes)
    }

    @Test fun requiresExactScopeRevisionCountsLimitsAndSourceKindTotals() {
        reject(response(bookId = story))
        reject(response(revision = "5"))
        reject(response(chapterCount = 2))
        reject(response(itemCount = 3))
        reject(response(distinctItemCount = 3))
        reject(response().replace("\"chapters\":24", "\"chapters\":23"))
        reject(response().replace("\"metadata\":1", "\"metadata\":2"))
        reject(response().replace("\"source_count\":2", "\"source_count\":\"2\""))
        reject(response().replace("\"id\":\"$story\"", "\"id\":\"not-a-uuid\""))
        reject(response().replace("\"revision\":\"7\"", "\"revision\":7"))
        reject(response().replace("\"position\":1", "\"position\":2"))
        reject(response().replace("\"can_draft\":true", "\"can_draft\":\"true\""))
    }

    @Test fun acceptsServerMaximumUnicodeTitlesAndRejectsPermissionOrStructureContradictions() {
        val longTitle = "😀".repeat(128) + "中".repeat(32)
        assertEquals(160, longTitle.codePointCount(0, longTitle.length))
        assertTrue(longTitle.toByteArray(Charsets.UTF_8).size > 512)
        assertEquals(longTitle, decode(response(title = longTitle)).sections.single().title)
        reject(response(title = longTitle + "中"))
        reject(response(chapterCount = 25))
        reject(response().replace("\"can_edit\":true", "\"can_edit\":false"))
        reject(response().replace("\"item_count\":2,\"can_edit\":true", "\"item_count\":2,\"can_edit\":false"))

        val parsed = Json.parseToJsonElement(response()).jsonObject
        val section = parsed.getValue("sections").jsonArray.single()
        val repeated = buildJsonObject {
            parsed.forEach { (key, value) -> put(key, value) }
            put("story_count", 2)
            put("chapter_count", 2)
            put("item_count", 4)
            put("distinct_item_count", 4)
            put("sections", JsonArray(listOf(section, section)))
        }
        reject(repeated.toString())
    }

    @Test fun viewerPlanMayBeWithinLimitsWithoutDraftPermission() {
        val viewerResponse = response()
            .replace("\"can_edit\":true", "\"can_edit\":false")
            .replace("\"can_draft\":true", "\"can_draft\":false")
        val plan = decode(viewerResponse)
        assertFalse(plan.canEdit)
        assertFalse(plan.whole.canDraft)
        assertFalse(plan.sections.single().canEdit)
        assertFalse(plan.sections.single().capacity.canDraft)
    }

    @Test fun rejectsDuplicateNamesAndInvalidModeShape() {
        reject(response().replace("\"version\":1", "\"version\":1,\"version\":1"))
        reject(response(editorial = true).replace("\"context_profile\":\"memoir_editorial_v1\"",
            "\"context_profile\":\"memoir_editorial_v1\",\"context_profile\":\"memoir_editorial_v1\""),
            editorial = true)
        reject(response(editorial = true, wholeState = "smaller_scope_required",
            contextBytes = "22", sourceCount = "null", sourceKinds = "null"), editorial = true)
        reject(response(wholeState = "smaller_scope_required", sourceCount = "2", sourceKinds = "{}"))
    }
}
