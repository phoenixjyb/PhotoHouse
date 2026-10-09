package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

internal object DiscoveryExamples {
    val all = Json.parseToJsonElement(checkNotNull(javaClass.getResourceAsStream("/examples.json")).bufferedReader().use { it.readText() }).jsonObject.getValue("examples").jsonArray
    fun body(name: String) = all.first { it.jsonObject.getValue("name").jsonPrimitive.content == name }.jsonObject.getValue("body").jsonObject
    fun bytes(name: String) = body(name).toString().toByteArray()
    val binding = body("people-first").getValue("binding").jsonPrimitive.content
}

class PhoneDiscoveryWireTest {
    private fun rejected(block: () -> Unit) { try { block(); fail("Invalid response accepted") } catch (e: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, e.kind) } }
    @Test fun placeQueryValidationUsesUtf8BytesAndRejectsControls() {
        assertTrue(PhoneDiscoveryWire.validPlaceQuery("北京 Beijing"))
        assertTrue(PhoneDiscoveryWire.validPlaceQuery(""))
        assertFalse(PhoneDiscoveryWire.validPlaceQuery("界".repeat(43)))
        assertFalse(PhoneDiscoveryWire.validPlaceQuery("北京\n"))
    }
    @Test fun parsesEverySuccessfulProducerExampleIncluding64BitIds() {
        var successes = 0
        for (e in DiscoveryExamples.all) {
            val example = e.jsonObject
            if (example.getValue("status").jsonPrimitive.int != 200) continue
            val b = example.getValue("body").jsonObject; val page = b.getValue("page").jsonPrimitive.int; val size = b.getValue("page_size").jsonPrimitive.int
            val bytes = b.toString().toByteArray(); val binding = b.getValue("binding").jsonPrimitive.content
            if ("facet" in b) {
                val facet = PhoneFacet.entries.single { it.wire == b.getValue("facet").jsonPrimitive.content }
                assertEquals(page, PhoneDiscoveryWire.facets(bytes, "family-a", facet, page, size, if (page > 1) binding else null).page)
            } else {
                val result = PhoneDiscoveryWire.search(bytes, "family-a", binding, page, size, if (page > 1) b.getValue("fingerprint").jsonPrimitive.content else null)
                assertEquals(page, result.gallery.page)
            }
            successes++
        }
        assertEquals(7, successes)
        assertEquals(Long.MAX_VALUE.toString(), PhoneDiscoveryWire.search(DiscoveryExamples.bytes("all-media-first"), "family-a", DiscoveryExamples.binding, 1, 1).gallery.items.single().id)
    }
    @Test fun malformedEnvelopeIdsHashesAndPagingAreRejected() {
        val original = DiscoveryExamples.body("people-first")
        fun parse(o: JsonObject) = PhoneDiscoveryWire.facets(o.toString().toByteArray(), "family-a", PhoneFacet.PEOPLE, 1, 1)
        for (bad in listOf("1\n", "1\r\n", "1\t", "1\u2028", "01", "0", "9223372036854775808", "1.0", "+1"))
            rejected { parse(JsonObject(original + ("revision" to JsonPrimitive(bad)))) }
        for (ending in listOf("\n", "\r\n", "\t", "\u2028")) rejected { parse(JsonObject(original + ("binding" to JsonPrimitive(DiscoveryExamples.binding + ending)))) }
        for ((key, value) in listOf("extra" to JsonPrimitive(true), "page" to JsonPrimitive(2), "page_size" to JsonPrimitive(50),
            "library_id" to JsonPrimitive("foreign"), "has_more" to JsonPrimitive(false), "index_complete" to JsonPrimitive(false)))
            rejected { parse(JsonObject(original + (key to value))) }
        rejected { parse(JsonObject(original - "coverage")) }
    }
    @Test fun duplicateKeysInvalidUtf8SurrogatesDepthAndSizeAreRejected() {
        val valid = DiscoveryExamples.bytes("people-first").toString(Charsets.UTF_8)
        for (text in listOf(valid.replaceFirst("{", "{\"version\":1,"), valid.replace("\"family-a\"", "\"\\ud800\""), "[".repeat(10) + "0" + "]".repeat(10)))
            rejected { PhoneDiscoveryWire.facets(text.toByteArray(), "family-a", PhoneFacet.PEOPLE, 1, 1) }
        rejected { PhoneDiscoveryWire.facets(byteArrayOf(0xc3.toByte(), 0x28), "family-a", PhoneFacet.PEOPLE, 1) }
        rejected { PhoneDiscoveryWire.facets(ByteArray(524289), "family-a", PhoneFacet.PEOPLE, 1) }
    }
    @Test fun searchCannotSubstituteScopeFingerprintOrderOrThumbnailEndpoint() {
        val b = DiscoveryExamples.body("all-media-first")
        fun parse(o: JsonObject) = PhoneDiscoveryWire.search(o.toString().toByteArray(), "family-a", DiscoveryExamples.binding, 1, 1, b.getValue("fingerprint").jsonPrimitive.content)
        rejected { parse(JsonObject(b + ("fingerprint" to JsonPrimitive("a".repeat(64))))) }
        rejected { parse(JsonObject(b + ("binding" to JsonPrimitive("a".repeat(64))))) }
        val asset = b.getValue("items").jsonArray.single().jsonObject
        for (url in listOf("https://evil.invalid/x", "//evil.invalid/x", "/assets/1/media?library=family-a", "/assets/${Long.MAX_VALUE}/thumbnail?library=foreign")) {
            val item = JsonObject(asset + ("thumbnail_url" to JsonPrimitive(url)))
            rejected { parse(JsonObject(b + ("items" to JsonArray(listOf(item))))) }
        }
    }
    @Test fun requestSerializationPreservesIdsAnyAllDatesAndNullFirstFingerprint() {
        val f = PhoneFilters(people = listOf(PhoneChoice(Long.MAX_VALUE.toString(), "Person", 1)), peopleAll = true,
            tags = listOf(PhoneChoice("4", "Tag", 1)), places = listOf(PhoneChoice("9", "Place", 1)),
            media = setOf("video"), from = "2026-01-01", caption = "生日 party")
        val body = Json.parseToJsonElement(PhoneDiscoveryWire.request(DiscoveryExamples.binding, f, 1)).jsonObject
        assertEquals(JsonNull, body.getValue("fingerprint"))
        assertEquals("all", body.getValue("filters").jsonObject.getValue("people").jsonObject.getValue("match").jsonPrimitive.content)
        assertTrue(body.toString().contains("\"${Long.MAX_VALUE}\""))
        assertEquals(JsonNull, body.getValue("filters").jsonObject.getValue("date").jsonObject.getValue("to"))
        for (bad in listOf(f.copy(from = "2026-02-30"), f.copy(from = "2026-03-01", to = "2026-02-01"),
            f.copy(caption = "溪".repeat(171)), f.copy(people = f.people + f.people))) assertTrue(runCatching { bad.json() }.isFailure)
        assertTrue(runCatching { PhoneDiscoveryWire.request(DiscoveryExamples.binding, f, 2) }.isFailure)
    }
}
