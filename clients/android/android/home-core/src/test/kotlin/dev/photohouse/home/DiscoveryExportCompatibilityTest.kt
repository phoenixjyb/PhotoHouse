package dev.photohouse.home

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

/** Responses generated from the real pinned exporter and serving code, using fresh synthetic SQLite. */
class DiscoveryExportCompatibilityTest {
    private val fixture = Json.parseToJsonElement(requireNotNull(javaClass.classLoader.getResourceAsStream(
        "discovery-export-generated.json")).bufferedReader(Charsets.UTF_8).use { it.readText() }).jsonObject
    private val responses = fixture.getValue("responses").jsonObject
    private fun response(name: String) = responses.getValue(name).toString().toByteArray(Charsets.UTF_8)
    private fun snapshot(): DiscoverySnapshot {
        var snapshot: DiscoverySnapshot? = null
        for ((name, field) in listOf("people" to DiscoveryField.PEOPLE, "tags" to DiscoveryField.TAGS, "locations" to DiscoveryField.PLACES))
            snapshot = DiscoveryWire.merge(snapshot, DiscoveryWire.facets(response(name), field, 1))
        return requireNotNull(snapshot)
    }

    @Test fun exportedReviewedFacetsPreservePinsCoverageAndTagProvenance() {
        val options = snapshot().options
        assertTrue(fixture.getValue("synthetic_only").jsonPrimitive.boolean)
        assertFalse(fixture.getValue("final_enabled").jsonPrimitive.boolean)
        assertEquals(listOf("202", "201"), options.pinnedPeople)
        assertEquals(DiscoveryCoverage(2, 2), options.coverage[DiscoveryField.PEOPLE])
        assertEquals(DiscoveryCoverage(3, 1), options.coverage[DiscoveryField.TEXT])
        assertFalse(options.partialIndex) // All rows indexed, although some metadata is absent.
        assertEquals(1, options.people.single { it.id == "201" }.assetCount)
        assertEquals(mapOf("reviewed_assignments" to 1), options.people.single { it.id == "201" }.provenance)
        assertEquals(2, options.tags.single { it.id == "301" }.provenance["caption"])
        assertFalse(options.tags.any { it.id == "303" }) // Blocked tag excluded by exporter.
        assertFalse(DiscoveryField.THEMES in options.fields || DiscoveryField.TOPICS in options.fields)
    }

    @Test fun exportedSearchReusesV2AvailabilityWithoutTreatingCaptionAsIdentity() {
        val snapshot = snapshot()
        val combined = DiscoveryWire.search(response("combined"), snapshot, 1).feed
        assertEquals(listOf(103), combined.items.map { it.id })
        assertEquals(MediaUnavailable.NOT_PREPARED, combined.items.single().displayUnavailable)
        val videos = DiscoveryWire.search(response("videos"), snapshot, 1).feed
        assertEquals(listOf(104, 102), videos.items.map { it.id })
        assertNull(videos.items.first().video)
        assertNotNull(videos.items.last().video)
        assertEquals(0, DiscoveryWire.search(response("caption-is-not-identity"), snapshot, 1).feed.total)
    }
}
