package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class MemoryGroupsWireTest {
    private val library = "family-a"
    private fun bytes(json: String) = json.toByteArray(Charsets.UTF_8)
    private fun rejected(block: () -> Unit) {
        try { block(); fail("Invalid memory group response accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }

    @Test fun decodesCapabilitiesAndUnavailableProposals() {
        val caps = MemoryGroupsWire.capabilities(bytes("""{"version":1,"enabled":true,"manual":true,"suggestions":false,"max_members":24,"needs_review":true}"""))
        assertTrue(caps.enabled); assertTrue(caps.manual); assertFalse(caps.suggestions)
        rejected { MemoryGroupsWire.capabilities(bytes("""{"version":1,"enabled":true,"manual":"true","suggestions":false,"max_members":24,"needs_review":true}""")) }
        val proposal = MemoryGroupsWire.proposals(bytes("""{"version":1,"status":"unavailable","library_id":"family-a","seed_asset_ids":["42"],"needs_review":true,"items":[]}"""), library, listOf("42"))
        assertEquals(MemoryGroupProposalStatus.UNAVAILABLE, proposal.status)
        assertTrue(proposal.items.isEmpty())
        rejected { MemoryGroupsWire.proposals(bytes("""{"version":1,"status":"unavailable","library_id":"family-a","seed_asset_ids":["43"],"needs_review":true,"items":[]}"""), library, listOf("42")) }
    }

    @Test fun decodesCompleteGroupWithDynamicallyHydratedOriginalNote() {
        val storyId = "123e4567-e89b-12d3-a456-426614174001"
        val original = """{"asset_id":"42","author_id":"123e4567-e89b-12d3-a456-426614174000","byline":"Grandma","can_edit":false,"can_view_history":false,"created_at":10,"deleted":false,"id":"$storyId","language":"en","revision":3,"source":"family","text":"The original note stays here.","title":"First trip","updated_at":11}"""
        val group = """{"version":1,"type":"memory_group","id":"123e4567-e89b-12d3-a456-426614174002","library_id":"family-a","revision":"2","theme":"trip","asset_ids":["42"],"excluded_asset_ids":["43"],"source_story_ids":["$storyId"],"items":[{"id":"42","kind":"image","width":1000000,"height":480,"duration_sec":0,"taken_at":"not an ISO timestamp","thumbnail_url":"/assets/42/thumbnail?library=family-a"}],"sources":[$original],"can_edit":true}"""
        val decoded = MemoryGroupsWire.single(bytes(group), library)
        assertEquals(listOf("42"), decoded.assetIds)
        assertEquals(listOf("43"), decoded.excludedAssetIds)
        assertEquals(storyId, decoded.sources.single().id)
        assertEquals("The original note stays here.", decoded.sources.single().text)
        assertEquals("First trip", decoded.sources.single().title)
        assertEquals(0.0, decoded.items.single().duration_sec!!, 0.0)
    }

    @Test fun readyProposalsPreserveServerOrderAndRejectExcludedVideoOrUndatedItems() {
        fun candidate(id: String, kind: String = "image", takenAt: String? = "2026-03-04T11:00:00Z"): String {
            val taken = takenAt?.let { "\"$it\"" } ?: "null"
            return """{"id":"$id","kind":"$kind","width":640,"height":480,"duration_sec":null,"taken_at":$taken,"thumbnail_url":"/assets/$id/thumbnail?library=family-a","matched_seed_asset_id":"42","time_reason":"within_recorded_window"}"""
        }
        val good = """{"version":1,"status":"ready","library_id":"family-a","seed_asset_ids":["42"],"needs_review":true,"items":[${candidate("44")},${candidate("43")}] }"""
        val decoded = MemoryGroupsWire.proposals(bytes(good), library, listOf("42"), listOf("45"))
        assertEquals(listOf("44", "43"), decoded.items.map { it.asset.id })
        assertEquals(listOf("42", "42"), decoded.items.map { it.matchedSeedAssetId })
        for (item in listOf(candidate("45"), candidate("44", kind = "video"), candidate("44", takenAt = null))) {
            val invalid = good.replace("${candidate("44")},${candidate("43")}", item)
            rejected { MemoryGroupsWire.proposals(bytes(invalid), library, listOf("42"), listOf("45")) }
        }
        val tooMany = """{"version":1,"status":"ready","library_id":"family-a","seed_asset_ids":["42"],"needs_review":true,"items":[${(1..24).joinToString(",") { candidate((100 + it).toString()) }}]}"""
        rejected { MemoryGroupsWire.proposals(bytes(tooMany), library, listOf("42")) }
    }

    @Test fun rejectsWrongScopeShapeAndNonCanonicalThumbnail() {
        val page = """{"version":1,"library_id":"family-a","asset_id":"42","has_more":false,"items":[]}"""
        assertEquals("42", MemoryGroupsWire.page(bytes(page), library, "42").assetId)
        rejected { MemoryGroupsWire.page(bytes(page.replace("family-a", "family-b")), library, "42") }
        val candidate = """{"id":"43","kind":"image","width":20,"height":10,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/43/thumbnail?library=evil","matched_seed_asset_id":"42","time_reason":"same_recorded_day"}"""
        val proposals = """{"version":1,"status":"ready","library_id":"family-a","seed_asset_ids":["42"],"needs_review":true,"items":[$candidate]}"""
        rejected { MemoryGroupsWire.proposals(bytes(proposals), library, listOf("42")) }
    }

    @Test fun mutationContainsOnlyCanonicalIdsAndRetryIdentity() {
        val mutation = MemoryGroupMutation(theme = "trip", assetIds = listOf("42", "43"), mutationId = "123e4567-e89b-12d3-a456-426614174001")
        val wire = Json.parseToJsonElement(MemoryGroupsWire.mutation(mutation)).jsonObject
        assertEquals(setOf("asset_ids", "excluded_asset_ids", "source_story_ids", "theme", "revision", "mutation_id"), wire.keys)
        assertEquals("42,43", wire.getValue("asset_ids").jsonPrimitive.content)
        assertEquals("123e4567-e89b-12d3-a456-426614174001", wire.getValue("mutation_id").jsonPrimitive.content)
        assertFalse(wire.values.any { it.toString().contains("family prose") })
        assertEquals(MemoryGroupsWire.mutation(mutation), MemoryGroupsWire.mutation(mutation))
        assertTrue(runCatching { MemoryGroupsWire.mutation(mutation.copy(assetIds = listOf("042"))) }.isFailure)
    }
}
