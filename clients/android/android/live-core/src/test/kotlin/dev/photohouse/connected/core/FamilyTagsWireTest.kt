package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class FamilyTagsWireTest {
    private fun rejected(block: () -> Unit) {
        try { block(); fail("Invalid family tag response accepted") }
        catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) }
    }
    private fun catalog(page: Int = 1, library: String = "family-a") = buildJsonObject {
        put("library_id", library); put("page", page); put("page_size", 25); put("total", 1)
        put("items", buildJsonArray { add(buildJsonObject { put("name", "Birthday"); put("asset_count", 3) }) })
    }
    private fun assets(page: Int = 1, library: String = "family-a", tag: String = "Birthday") = buildJsonObject {
        put("library_id", library); put("tag", tag); put("page", page); put("page_size", 25); put("total", 1)
        put("originals_allowed", false)
        put("items", buildJsonArray { add(buildJsonObject {
            put("id", "42"); put("kind", "image"); put("width", 640); put("height", 480)
            put("duration_sec", JsonNull); put("taken_at", "2026-03-04T12:00:00Z")
            put("thumbnail_url", "/assets/42/thumbnail?library=family-a")
        }) })
    }
    @Test fun parsesExactCatalogAndAssetContracts() {
        val page = FamilyTagsWire.catalog(catalog().toString().toByteArray(), "family-a", 1)
        assertEquals(listOf(FamilyTagChoice("Birthday", 3)), page.items)
        val gallery = FamilyTagsWire.assets(assets().toString().toByteArray(), "family-a", "Birthday", 1)
        assertEquals("42", gallery.items.single().id); assertFalse(gallery.originals_allowed)
        val request = Json.parseToJsonElement(FamilyTagsWire.assetsRequest("Birthday", 2)).jsonObject
        assertEquals(setOf("tag", "page"), request.keys)
        assertEquals("Birthday", request.getValue("tag").jsonPrimitive.content)
        assertEquals(2, request.getValue("page").jsonPrimitive.int)
    }
    @Test fun rejectsScopePageShapeAndMalformedCatalogValues() {
        rejected { FamilyTagsWire.catalog(catalog(library = "other").toString().toByteArray(), "family-a", 1) }
        rejected { FamilyTagsWire.catalog(catalog(page = 2).toString().toByteArray(), "family-a", 1) }
        rejected { FamilyTagsWire.catalog((catalog() + ("extra" to JsonPrimitive(true))).toString().toByteArray(), "family-a", 1) }
        rejected { FamilyTagsWire.catalog((catalog() + ("page_size" to JsonPrimitive(50))).toString().toByteArray(), "family-a", 1) }
        rejected { FamilyTagsWire.catalog((catalog() + ("items" to buildJsonArray { add(buildJsonObject { put("name", "\nprivate"); put("asset_count", 1) }) })).toString().toByteArray(), "family-a", 1) }
    }
    @Test fun rejectsWrongTagScopeAndUnsafeAssetPreview() {
        rejected { FamilyTagsWire.assets(assets(tag = "Other").toString().toByteArray(), "family-a", "Birthday", 1) }
        rejected { FamilyTagsWire.assets(assets(library = "other").toString().toByteArray(), "family-a", "Birthday", 1) }
        val body = assets(); val original = body.getValue("items").jsonArray.single().jsonObject
        for (url in listOf("https://evil.invalid/x", "//evil.invalid/x", "/assets/42/media?library=family-a", "/assets/42/thumbnail?library=other")) {
            val item = JsonObject(original + ("thumbnail_url" to JsonPrimitive(url)))
            rejected { FamilyTagsWire.assets(JsonObject(body + ("items" to JsonArray(listOf(item)))).toString().toByteArray(), "family-a", "Birthday", 1) }
        }
    }
    @Test fun requestAndResponseTextLimitsAreUtf8Bounded() {
        assertTrue(FamilyTagsWire.validQuery("生日"))
        assertTrue(FamilyTagsWire.validQuery("界".repeat(43)))
        assertFalse(FamilyTagsWire.validQuery("界".repeat(171)))
        assertFalse(FamilyTagsWire.validTag("  "))
        val longChineseTag = "界".repeat(128)
        assertTrue(FamilyTagsWire.validQuery(longChineseTag))
        assertTrue(FamilyTagsWire.validTag(longChineseTag))
        assertTrue(runCatching { FamilyTagsWire.assetsRequest(longChineseTag, 1) }.isSuccess)
        assertFalse(FamilyTagsWire.validQuery(longChineseTag + "界"))
        assertFalse(FamilyTagsWire.validTag("界".repeat(171)))
        val longCatalog = JsonObject(catalog() + ("items" to buildJsonArray {
            add(buildJsonObject { put("name", longChineseTag); put("asset_count", 1) })
        }))
        assertEquals(longChineseTag, FamilyTagsWire.catalog(longCatalog.toString().toByteArray(), "family-a", 1).items.single().name)
        val longAsset = assets(tag = longChineseTag)
        assertEquals("42", FamilyTagsWire.assets(longAsset.toString().toByteArray(), "family-a", longChineseTag, 1).items.single().id)
        assertTrue(runCatching { FamilyTagsWire.assetsRequest("\uD800", 1) }.isFailure)
        assertTrue(runCatching { FamilyTagsWire.assetsRequest("x".repeat(129), 1) }.isFailure)
    }
}
