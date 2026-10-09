package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.serialization.json.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import java.time.LocalDate
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction

/** Separate opt-in protected contract. Decimal IDs never pass through Int or Double. */
object PhoneDiscoveryWire {
    val fields = setOf("people", "date", "caption", "tags", "locations", "media")
    fun validId(s: String) = s.matches(Regex("[1-9][0-9]{0,18}")) && s.toLongOrNull() != null
    fun validHash(s: String) = s.matches(Regex("[0-9a-f]{64}"))
    fun validPlaceQuery(s: String): Boolean = runCatching {
        require(s.none { it < ' ' || it == '\u007f' })
        val bytes = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(s)).remaining()
        require(bytes <= 128)
    }.isSuccess
    fun validLibrary(s: String) = s.isNotBlank() && s.codePointCount(0, s.length) <= 128 && s.none { it < ' ' || it == '\u007f' } && s !in setOf(".", "..")
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) bad() }
    private inline fun <T> guarded(block: () -> T): T = try { block() } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
    private fun JsonElement.obj(vararg keys: String): JsonObject = (this as? JsonObject ?: bad()).also { check(it.keys == keys.toSet()) }
    private fun JsonElement.str(max: Int): String {
        val p = this as? JsonPrimitive ?: bad(); check(p.isString)
        check(p.content.codePointCount(0, p.content.length) <= max && p.content.none { it < ' ' && it !in "\n\t" })
        return p.content
    }
    private fun JsonElement.int(low: Int = 0, high: Int = 100000): Int {
        val p = this as? JsonPrimitive ?: bad(); check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it in low..high } ?: bad()
    }
    private fun JsonElement.bool(): Boolean { val p = this as? JsonPrimitive ?: bad(); check(!p.isString); return p.booleanOrNull ?: bad() }
    private fun JsonElement.array(max: Int): JsonArray = (this as? JsonArray ?: bad()).also { check(it.size <= max) }
    private fun JsonElement.id() = str(19).also { check(validId(it)) }
    private fun JsonElement.hash() = str(64).also { check(validHash(it)) }
    private fun date(e: JsonElement): String? = if (e == JsonNull) null else e.str(10).also {
        check(it.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}")) && LocalDate.parse(it).year in 1..9999)
    }
    private fun choice(e: JsonElement, facet: PhoneFacet, assets: Int): PhoneChoice {
        val o = when (facet) {
            PhoneFacet.PEOPLE -> e.obj("id", "label", "asset_count", "aliases", "provenance")
            PhoneFacet.TAGS -> e.obj("id", "label", "asset_count", "kind", "provenance_counts")
            PhoneFacet.PLACES -> e.obj("id", "label", "asset_count", "provenance")
        }
        val count = o.getValue("asset_count").int(0, assets)
        val aliases = if (facet == PhoneFacet.PEOPLE) o.getValue("aliases").array(8).map { it.str(128) } else emptyList()
        check(aliases.distinct().size == aliases.size && aliases.all { it.isNotBlank() && it.toByteArray(Charsets.UTF_8).size <= 128 })
        when (facet) {
            PhoneFacet.PEOPLE -> check(o.getValue("provenance").str(32) == "reviewed_assignments")
            PhoneFacet.PLACES -> check(o.getValue("provenance").str(32) == "reviewed_region")
            PhoneFacet.TAGS -> {
                check(o.getValue("kind").str(16) in setOf("date", "location", "person", "scene", "custom", "unknown"))
                val counts = o.getValue("provenance_counts") as? JsonObject ?: bad()
                check(counts.keys.all { it in setOf("manual", "caption", "image", "caption_image", "rule", "unknown") })
                check(counts.values.sumOf { it.int(1, assets) } == count)
            }
        }
        val label = o.getValue("label").str(256); check(label.isNotBlank() && label.toByteArray(Charsets.UTF_8).size <= 256)
        return PhoneChoice(o.getValue("id").id(), label, count, aliases)
    }
    private fun paging(o: JsonObject, page: Int, size: Int, count: Int) {
        check(o.getValue("page").int(1) == page && o.getValue("page_size").int(1, 100) == size)
        val total = o.getValue("total").int()
        check(o.getValue("has_more").bool() == (page.toLong() * size < total))
        check(count.toLong() == minOf(size.toLong(), maxOf(0L, total.toLong() - (page - 1L) * size)))
    }
    fun facets(bytes: ByteArray, library: String, facet: PhoneFacet, page: Int, size: Int = 50, binding: String? = null): PhoneFacetPage = guarded {
        check(validLibrary(library) && page in 1..5000 && size in 1..100 && (page == 1 || binding != null))
        val o = DiscoveryJson.parse(bytes).obj("version", "library_id", "binding", "revision", "enabled", "unavailable",
            "catalog_assets", "indexed_assets", "index_complete", "metadata_completeness", "tag_generation_completeness",
            "coverage", "captured_date_bounds", "pinned_person_ids", "pinned_people", "facet", "page", "page_size", "total", "has_more", "items")
        check(o.getValue("version").int() == 1 && o.getValue("library_id").str(128) == library && o.getValue("facet").str(16) == facet.wire)
        val received = o.getValue("binding").hash(); check(binding == null || received == binding)
        val enabled = o.getValue("enabled").array(6).map { it.str(16) }; check(enabled.toSet().size == enabled.size && enabled.all { it in fields } && "media" in enabled)
        val unavailable = o.getValue("unavailable").obj("themes", "topics"); check(unavailable.values.all { it.str(32) == "no_reviewed_taxonomy" })
        val assets = o.getValue("catalog_assets").int(); val indexed = o.getValue("indexed_assets").int(0, assets)
        check(o.getValue("index_complete").bool() == (assets == indexed))
        check(o.getValue("metadata_completeness").str(32) == "not_inferred" && o.getValue("tag_generation_completeness").str(32) == "unknown")
        val coverage = o.getValue("coverage").obj(*fields.toTypedArray()).mapValues { (field, e) ->
            val v = e.obj("with_values", "without_values")
            val with = v.getValue("with_values").int(0, assets); val without = v.getValue("without_values").int(0, assets)
            check(with + without == assets && (field in enabled || with == 0))
            check(if (field == "media") with == assets else with <= indexed)
            PhoneCoverage(with, without)
        }
        val bounds = o.getValue("captured_date_bounds").obj("from", "to")
        val from = date(bounds.getValue("from")); val to = date(bounds.getValue("to"))
        check((from == null) == (to == null) && (from == null || from <= to!!))
        check((from != null) == (coverage.getValue("date").withValues > 0))
        val pins = o.getValue("pinned_person_ids").array(32).map { it.id() }
        val people = o.getValue("pinned_people").array(32).map { choice(it, PhoneFacet.PEOPLE, assets) }
        check(pins.distinct().size == pins.size && pins == people.map { it.id } && ("people" in enabled || pins.isEmpty()))
        val items = o.getValue("items").array(size).map { choice(it, facet, assets) }
        check(items.zipWithNext().all { (a, b) -> a.id.toLong() < b.id.toLong() })
        check(facet.wire in enabled || o.getValue("total").int() == 0)
        if (facet == PhoneFacet.PEOPLE) {
            check(pins.size <= o.getValue("total").int())
            for (item in items) people.find { it.id == item.id }?.let { check(it == item) }
        }
        paging(o, page, size, items.size)
        PhoneFacetPage(PhoneSnapshot(library, received, o.getValue("revision").id(), enabled.toSet(), assets, indexed, coverage, from, to, people),
            facet, page, size, o.getValue("total").int(), o.getValue("has_more").bool(), items)
    }
    fun request(binding: String, filters: PhoneFilters, page: Int, size: Int = 50, fingerprint: String? = null): String {
        require(validHash(binding) && page in 1..100000 && size in 1..100)
        require(if (page == 1) fingerprint == null else fingerprint != null && validHash(fingerprint))
        return buildJsonObject { put("binding", binding); put("filters", filters.json()); put("page", page); put("page_size", size)
            put("fingerprint", fingerprint?.let { JsonPrimitive(it) } ?: JsonNull)
        }.toString().also { require(it.toByteArray(Charsets.UTF_8).size <= 20 * 1024) }
    }
    fun search(bytes: ByteArray, library: String, binding: String, page: Int, size: Int = 50, fingerprint: String? = null): PhoneSearchPage = guarded {
        check(validLibrary(library) && validHash(binding) && page in 1..100000 && size in 1..100)
        val o = DiscoveryJson.parse(bytes).obj("version", "library_id", "binding", "fingerprint", "page", "page_size", "total", "has_more", "originals_allowed", "items")
        check(o.getValue("version").int() == 1 && o.getValue("library_id").str(128) == library && o.getValue("binding").hash() == binding)
        val received = o.getValue("fingerprint").hash(); check(fingerprint == null || received == fingerprint)
        val items = o.getValue("items").array(size).map { e ->
            val a = e.obj("id", "kind", "width", "height", "duration_sec", "taken_at", "thumbnail_url")
            val id = a.getValue("id").id(); val kind = a.getValue("kind").str(8); check(kind in setOf("image", "video", "other"))
            fun dimension(k: String) = a.getValue(k).let { if (it == JsonNull) null else it.int(1, 1000000) }
            val duration = a.getValue("duration_sec").let { if (it == JsonNull) null else {
                val v = it as? JsonPrimitive ?: bad(); check(!v.isString)
                (v.doubleOrNull ?: bad()).also { check(it.isFinite() && it in 0.0..1e9) }
            } }
            val taken = a.getValue("taken_at").let { if (it == JsonNull) null else it.str(64) }
            val thumbnail = a.getValue("thumbnail_url").str(2048)
            val base = "https://contract.invalid/".toHttpUrl()
            val expected = base.newBuilder().addPathSegment("assets").addPathSegment(id).addPathSegment("thumbnail").addQueryParameter("library", library).build()
            check(thumbnail.startsWith('/') && !thumbnail.startsWith("//") && '\\' !in thumbnail && base.resolve(thumbnail) == expected)
            Asset(id, kind, dimension("width"), dimension("height"), duration, taken, thumbnail)
        }
        check(items.zipWithNext().all { (a, b) -> a.id.toLong() > b.id.toLong() })
        paging(o, page, size, items.size)
        PhoneSearchPage(Gallery(library, page, size, o.getValue("total").int().toLong(), o.getValue("originals_allowed").bool(), items), binding, received, o.getValue("has_more").bool())
    }
}
