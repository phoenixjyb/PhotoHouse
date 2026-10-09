package dev.photohouse.home

import kotlinx.serialization.json.*
import org.junit.Test
import org.junit.Assert.*

internal fun discoveryJson(name: String): JsonObject = Json.parseToJsonElement(requireNotNull(DiscoveryWireTest::class.java.classLoader.getResourceAsStream("discovery-$name.json")).use { it.readBytes() }.toString(Charsets.UTF_8)).jsonObject
internal fun JsonElement.discoveryBytes() = toString().toByteArray(Charsets.UTF_8)
internal fun discoveryFacet(field: String): JsonObject {
    val raw = discoveryJson("facets-$field")
    val items = if (field == "people") JsonArray(raw.getValue("pinned_people").jsonArray.sortedBy { it.jsonObject.getValue("id").jsonPrimitive.int }) else raw.getValue("items")
    return JsonObject(raw + mapOf("page_size" to JsonPrimitive(50), "total" to JsonPrimitive(items.jsonArray.size), "has_more" to JsonPrimitive(false), "items" to items))
}
internal fun discoverySnapshot(): DiscoverySnapshot {
    var result: DiscoverySnapshot? = null
    for ((name, field) in listOf("people" to DiscoveryField.PEOPLE, "tags" to DiscoveryField.TAGS, "locations" to DiscoveryField.PLACES)) {
        result = DiscoveryWire.merge(result, DiscoveryWire.facets(discoveryFacet(name).discoveryBytes(), field, 1))
    }
    return requireNotNull(result)
}
class DiscoveryWireTest {
    @Test fun frozenOneItemFacetExamplesPreserveServerAliasesPinsAndCoverage() {
        for ((name, field) in listOf("people" to DiscoveryField.PEOPLE, "tags" to DiscoveryField.TAGS, "locations" to DiscoveryField.PLACES)) {
            val parsed = DiscoveryWire.facets(discoveryJson("facets-$name").discoveryBytes(), field, 1, 1)
            assertEquals(7, parsed.snapshot.revision); assertEquals(1, parsed.snapshot.catalogRevision)
            assertEquals(listOf("202", "201"), parsed.snapshot.options.pinnedPeople)
            assertEquals(listOf("Sample Child", "示例儿童"), parsed.snapshot.options.people[0].aliases)
            assertEquals(DiscoveryCoverage(3, 1), parsed.snapshot.options.coverage[DiscoveryField.PEOPLE])
            assertFalse(DiscoveryField.THEMES in parsed.snapshot.options.fields)
            assertEquals("2025-12-01", parsed.snapshot.options.dateFrom)
        }
    }
    @Test fun exactCombinedRequestUsesTypedIdsAndServerCaptionNormalization() {
        val snapshot = discoverySnapshot().let { it.copy(options = it.options.copy(tags = it.options.tags + DiscoveryChoice("302", "Synthetic tag"))) }
        val draft = DiscoveryDraft(text = " family ", people = setOf("202", "201"), peopleMatch = MatchMode.ALL,
            tags = setOf("302", "301"), tagsMatch = MatchMode.ALL, place = "401", from = "2025-01-01", through = "2026-12-31", media = AssetKind.PHOTO)
        assertEquals(discoveryJson("search-request"), HomeWire.parse(DiscoveryWire.request(snapshot, draft, 1)))
        val aliases = draft.copy(people = setOf("Sample Child"))
        assertThrows(HomeFailure::class.java) { DiscoveryWire.request(snapshot, aliases, 1) }
    }
    @Test fun draftsCannotSubmitBadDatesDisabledTaxonomyOrMalformedIds() {
        val s = discoverySnapshot()
        for (draft in listOf(DiscoveryDraft(from = "2026-02-30"), DiscoveryDraft(from = "2026-03-01", through = "2026-01-01"),
            DiscoveryDraft(themes = setOf("1")), DiscoveryDraft(people = setOf("0201")), DiscoveryDraft(text = "a".repeat(257)),
            DiscoveryDraft(place = "999"), DiscoveryDraft(text = "line\nnext"))) {
            assertThrows(HomeFailure::class.java) { DiscoveryWire.request(s, draft, 1) }
        }
        val unsupported = s.copy(options = s.options.copy(fields = setOf(DiscoveryField.MEDIA)))
        assertThrows(HomeFailure::class.java) { DiscoveryWire.request(unsupported, DiscoveryDraft(text = "family"), 1) }
        val malformed = s.copy(options = s.options.copy(people = listOf(DiscoveryChoice("2147483648", "Synthetic"))))
        assertThrows(HomeFailure::class.java) { DiscoveryWire.request(malformed, DiscoveryDraft(people = setOf("2147483648")), 1) }
    }
    @Test fun unsupportedCategoriesCannotSilentlyDisappearEvenFromSyntheticDomainOptions() {
        val s = discoverySnapshot().let { it.copy(options = it.options.copy(
            fields = it.options.fields + setOf(DiscoveryField.THEMES, DiscoveryField.TOPICS),
            themes = listOf(DiscoveryChoice("1", "Synthetic theme")), topics = listOf(DiscoveryChoice("2", "Synthetic topic")))) }
        for (draft in listOf(DiscoveryDraft(themes = setOf("1")), DiscoveryDraft(topics = setOf("2")))) {
            assertNull(draft.issue(s.options))
            assertThrows(HomeFailure::class.java) { DiscoveryWire.request(s, draft, 1) }
        }
    }
    @Test fun strictFacetParsingRejectsUnknownDuplicateKeysUtf8AndBounds() {
        val raw = discoveryJson("facets-people").toString()
        for (bytes in listOf(raw.replace("\"version\":1", "\"version\":1,\"version\":1").toByteArray(),
            raw.replace("\"version\":1", "\"version\":1,\"extra\":0").toByteArray(),
            raw.replace("\"total\":2", "\"total\":5001").toByteArray(),
            raw.replace("\"has_more\":true", "\"has_more\":false").toByteArray(),
            byteArrayOf(0xc3.toByte(), 0x28), ByteArray(HomeLimits.JSON + 1),
            raw.replace("Sample Adult", "\\ud800").toByteArray())) {
            assertThrows(HomeFailure::class.java) { DiscoveryWire.facets(bytes, DiscoveryField.PEOPLE, 1, 1) }
        }
    }
    @Test fun metadataCannotClaimInventedCoverageProvenanceOrTaxonomy() {
        val raw = discoveryJson("facets-people").toString()
        for (bad in listOf(raw.replace("\"indexed_assets\":4", "\"indexed_assets\":3"),
            raw.replace("\"assets_without_values\":1", "\"assets_without_values\":0"),
            raw.replace("reviewed_assignments", "caption_inference"),
            raw.replace("not_inferred", "complete"), raw.replace("no_reviewed_taxonomy", "not_published"),
            raw.replace("2025-12-01", "2026-06-01"))) {
            assertThrows(HomeFailure::class.java) { DiscoveryWire.facets(bad.toByteArray(), DiscoveryField.PEOPLE, 1, 1) }
        }
        val tag = discoveryJson("facets-tags").toString().replace("\"caption\":2", "\"caption\":1")
        assertThrows(HomeFailure::class.java) { DiscoveryWire.facets(tag.toByteArray(), DiscoveryField.TAGS, 1, 1) }
    }
    @Test fun changingMetadataOrPinRecordsCannotBeMergedUnderSameRevision() {
        val s = discoverySnapshot()
        for (bad in listOf(discoveryFacet("tags").toString().replace("Synthetic / 合成", "Other"),
            discoveryFacet("tags").toString().replace("Sample Child", "Other Child"),
            discoveryFacet("tags").toString().replace("\"revision\":7", "\"revision\":8"))) {
            val parsed = DiscoveryWire.facets(bad.toByteArray(), DiscoveryField.TAGS, 1)
            assertThrows(HomeFailure::class.java) { DiscoveryWire.merge(s, parsed) }
        }
    }
    @Test fun searchUsesFrozenV2AssetsAndRejectsRevisionFingerprintOrLibraryDrift() {
        val s = discoverySnapshot(); val raw = discoveryJson("search-response")
        val first = DiscoveryWire.search(raw.discoveryBytes(), s, 1)
        assertEquals(103, first.feed.items.single().id); assertEquals(2, first.feed.version)
        assertThrows(HomeFailure::class.java) { DiscoveryWire.search(raw.discoveryBytes(), s, 1, "0".repeat(64)) }
        assertThrows(HomeFailure::class.java) { DiscoveryWire.search(raw.discoveryBytes(), s, 1, total = 2) }
        for (bad in listOf(JsonObject(raw + ("revision" to JsonPrimitive(8))),
            JsonObject(raw + ("catalog_revision" to JsonPrimitive(2))),
            JsonObject(raw + ("page_size" to JsonPrimitive(1))),
            JsonObject(raw + ("unexpected" to JsonPrimitive(true))),
            JsonObject(raw + ("library" to buildJsonObject { put("id", "other"); put("title", s.libraryTitle) })))) {
            assertThrows(HomeFailure::class.java) { DiscoveryWire.search(bad.discoveryBytes(), s, 1) }
        }
    }
    @Test fun afterLastSearchPageIsEmptyAndRetainsMatchedTotal() {
        val s = discoverySnapshot(); val raw = discoveryJson("search-response")
        val after = JsonObject(raw + mapOf("page" to JsonPrimitive(2), "items" to JsonArray(emptyList())))
        val parsed = DiscoveryWire.search(after.discoveryBytes(), s, 2)
        assertEquals(1, parsed.feed.total); assertTrue(parsed.feed.items.isEmpty()); assertFalse(parsed.feed.hasMore)
    }
}
