package dev.photohouse.home

import kotlinx.serialization.json.*
import java.security.MessageDigest
import java.time.LocalDate

/** Frozen discovery v1; labels/aliases are server records, never identity inference. */
object DiscoveryWire {
    internal data class Facets(val snapshot: DiscoverySnapshot, val field: DiscoveryField,
        val page: Int, val total: Int, val more: Boolean, val items: List<DiscoveryChoice>, val lastId: Int?)
    internal data class Search(val feed: HomeFeed, val fingerprint: String)
    private fun bad(): Nothing = throw HomeFailure(HomeError.INVALID)
    private fun check(value: Boolean) { if (!value) bad() }
    private inline fun <T> guarded(action: () -> T): T = try { action() } catch (e: HomeFailure) { throw e } catch (_: Exception) { bad() }
    private fun JsonElement.obj(vararg keys: String): JsonObject = (this as? JsonObject ?: bad()).also { check(it.keys == keys.toSet()) }
    private fun JsonElement.int(low: Int = 1, high: Int = Int.MAX_VALUE): Int {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it in low..high } ?: bad()
    }
    private fun JsonElement.str(max: Int, nonempty: Boolean = false): String {
        val p = this as? JsonPrimitive ?: bad(); check(p.isString)
        check(p.content.toByteArray(Charsets.UTF_8).size <= max && p.content.none { it < ' ' && it != '\n' && it != '\t' })
        check(!nonempty || p.content.isNotBlank()); return p.content
    }
    private fun JsonElement.bool(): Boolean {
        val p = this as? JsonPrimitive ?: bad(); check(!p.isString); return p.booleanOrNull ?: bad()
    }
    private fun JsonElement.array(max: Int): JsonArray = (this as? JsonArray ?: bad()).also { check(it.size <= max) }
    private fun date(e: JsonElement): String? = if (e == JsonNull) null else e.str(10).also {
        check(it.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}"))); check(LocalDate.parse(it).year in 1..9999)
    }
    internal fun facetName(field: DiscoveryField) = when (field) {
        DiscoveryField.PEOPLE -> "people"; DiscoveryField.TAGS -> "tags"; DiscoveryField.PLACES -> "locations"; else -> bad()
    }
    private val fields = linkedMapOf("people" to DiscoveryField.PEOPLE, "date" to DiscoveryField.DATES,
        "locations" to DiscoveryField.PLACES, "media" to DiscoveryField.MEDIA, "tags" to DiscoveryField.TAGS,
        "caption" to DiscoveryField.TEXT, "themes" to DiscoveryField.THEMES, "topics" to DiscoveryField.TOPICS)
    private val sources = arrayOf("manual", "caption", "image", "caption_image", "rule", "unknown")
    private fun choice(e: JsonElement, field: DiscoveryField, assets: Int): DiscoveryChoice {
        val o = when (field) {
            DiscoveryField.PEOPLE -> e.obj("id", "label", "aliases", "asset_count", "provenance")
            DiscoveryField.TAGS -> e.obj("id", "label", "kind", "asset_count", "provenance_counts")
            DiscoveryField.PLACES -> e.obj("id", "label", "asset_count", "provenance")
            else -> bad()
        }
        val count = o.getValue("asset_count").int(0, assets)
        val aliases = if (field == DiscoveryField.PEOPLE) o.getValue("aliases").array(8).map { it.str(128, true) } else emptyList()
        check(aliases.distinct().size == aliases.size)
        val provenance = if (field == DiscoveryField.TAGS) {
            check(o.getValue("kind").str(16) in setOf("date", "location", "person", "scene", "custom", "unknown"))
            o.getValue("provenance_counts").obj(*sources).mapValues { it.value.int(0, count) }.also { check(it.values.sum() == count) }
        } else {
            val expected = if (field == DiscoveryField.PEOPLE) "reviewed_assignments" else "reviewed_region"
            check(o.getValue("provenance").str(32) == expected); mapOf(expected to count)
        }
        return DiscoveryChoice(o.getValue("id").int().toString(), o.getValue("label").str(256, true), aliases, count, provenance)
    }
    private fun canonical(e: JsonElement): JsonElement = when (e) {
        is JsonObject -> JsonObject(e.toSortedMap().mapValues { canonical(it.value) })
        is JsonArray -> JsonArray(e.map { canonical(it) })
        else -> e
    }
    internal fun facets(bytes: ByteArray, field: DiscoveryField, page: Int, size: Int = 50, version: Int = 1, query: String = ""): Facets = guarded {
        check(page in 1..5000 && size in 1..100)
        val parsed = HomeWire.parse(bytes)
        val keys = arrayOf("version", "revision", "catalog_revision", "library", "capabilities", "pinned_person_ids", "pinned_people", "facet", "page", "page_size", "total", "has_more", "items")
        val o = parsed.obj(*(keys + if (version == 3) arrayOf("query") else emptyArray()))
        if (version == 3) check(o.getValue("query").str(128) == query && (field == DiscoveryField.TAGS || query.isEmpty()))
        check(version in 1..3 && o.getValue("version").int() == version && o.getValue("facet").str(16) == facetName(field))
        check(o.getValue("page").int() == page && o.getValue("page_size").int() == size)
        val revision = o.getValue("revision").int(); val catalogRevision = o.getValue("catalog_revision").int()
        val lib = o.getValue("library").obj("id", "title")
        val id = lib.getValue("id").str(64).also { check(it.matches(Regex("[a-z0-9-]{1,64}"))) }
        val title = lib.getValue("title").str(256)
        val c = o.getValue("capabilities").obj("filters", "catalog_assets", "indexed_assets", "index_complete", "metadata_completeness", "tag_generation_completeness", "date_basis", "location_basis", "people_basis", "caption_match", "filter_join", "people_modes", "tag_modes", "captured_date_bounds")
        val assets = c.getValue("catalog_assets").int(0, 100000)
        val indexed = c.getValue("indexed_assets").int(0, assets)
        val complete = c.getValue("index_complete").bool(); check(complete == (assets == indexed))
        for ((key, expected) in mapOf("metadata_completeness" to "not_inferred", "tag_generation_completeness" to "unknown", "date_basis" to "recorded_taken_at_calendar_date", "location_basis" to "reviewed_coarse_region", "people_basis" to "reviewed_assignments", "caption_match" to "nfkc_casefold_literal_phrase", "filter_join" to "and")) check(c.getValue(key).str(64) == expected)
        for (key in listOf("people_modes", "tag_modes")) check(c.getValue(key).array(2).map { it.str(3) } == listOf("any", "all"))
        val filters = c.getValue("filters").obj(*fields.keys.toTypedArray())
        val enabled = mutableSetOf<DiscoveryField>(); val coverage = mutableMapOf<DiscoveryField, DiscoveryCoverage>()
        for ((key, f) in fields) {
            val v = filters.getValue(key).obj("enabled", "reason", "assets_with_values", "assets_without_values")
            val on = v.getValue("enabled").bool(); val with = v.getValue("assets_with_values").int(0, assets)
            val without = v.getValue("assets_without_values").int(0, assets); check(with + without == assets)
            val taxonomy = f in setOf(DiscoveryField.THEMES, DiscoveryField.TOPICS)
            check(if (taxonomy) !on && v.getValue("reason") == JsonPrimitive("no_reviewed_taxonomy") else if (on) v.getValue("reason") == JsonNull else v.getValue("reason") == JsonPrimitive("not_published"))
            check(on || with == 0); if (on) enabled += f
            check(f == DiscoveryField.MEDIA || with <= indexed)
            coverage[f] = DiscoveryCoverage(with, without)
        }
        check(DiscoveryField.MEDIA in enabled && coverage.getValue(DiscoveryField.MEDIA).withValues == assets)
        val bounds = c.getValue("captured_date_bounds").obj("from", "to")
        val from = date(bounds.getValue("from")); val to = date(bounds.getValue("to"))
        check((from == null) == (to == null) && (from == null || from <= to!!))
        check((from != null) == (coverage.getValue(DiscoveryField.DATES).withValues > 0))
        val pins = o.getValue("pinned_person_ids").array(32).map { it.int().toString() }; check(pins.distinct().size == pins.size)
        val pinned = o.getValue("pinned_people").array(32).map { choice(it, DiscoveryField.PEOPLE, assets) }
        check(pinned.map { it.id } == pins && (DiscoveryField.PEOPLE in enabled || pins.isEmpty()))
        val total = o.getValue("total").int(0, if (version == 3 && field == DiscoveryField.TAGS) 10000 else 5000); val more = o.getValue("has_more").bool()
        check(more == (page * size < total) && (field in enabled || total == 0))
        val items = o.getValue("items").array(size).map { choice(it, field, assets) }
        check(items.size == minOf(size, maxOf(0, total - (page - 1) * size)))
        check(items.zipWithNext().all { (a, b) -> a.id.toInt() < b.id.toInt() })
        if (field == DiscoveryField.PEOPLE) {
            check(pins.size <= total)
            for (item in items) pinned.find { it.id == item.id }?.let { check(it == item) }
        }
        val binding = JsonObject(o.filterKeys { it in setOf("revision", "catalog_revision", "library", "capabilities", "pinned_person_ids", "pinned_people") })
        val hash = MessageDigest.getInstance("SHA-256").digest(canonical(binding).toString().toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
        val options = DiscoveryOptions(enabled, people = pinned, peopleAll = true, tagsAll = true,
            partialIndex = !complete, pinnedPeople = pins, coverage = coverage, dateFrom = from, dateThrough = to)
        Facets(DiscoverySnapshot(revision, catalogRevision, id, title, options, binding = hash, tagQuery = if (version == 3) query else null), field, page, total, more, items, items.lastOrNull()?.id?.toInt())
    }
    internal fun merge(snapshot: DiscoverySnapshot?, response: Facets): DiscoverySnapshot = guarded {
        val base = snapshot ?: response.snapshot
        check(base.binding != null && base.binding == response.snapshot.binding)
        check(response.page == (base.nextPages[response.field] ?: 1))
        base.facetTotals[response.field]?.let { check(it == response.total) }
        val queriedTags = response.field == DiscoveryField.TAGS && response.snapshot.tagQuery != null
        if (queriedTags) check(base.tagQuery == response.snapshot.tagQuery)
        val previousLast = base.facetLastIds[response.field]
        if (previousLast != null && response.items.isNotEmpty()) check(response.items.first().id.toInt() > previousLast)
        fun combined(old: List<DiscoveryChoice>): List<DiscoveryChoice> {
            val records = old.associateBy { it.id }.toMutableMap()
            for (item in response.items) {
                records[item.id]?.let { check(it == item && (response.field == DiscoveryField.PEOPLE && item.id in base.options.pinnedPeople || queriedTags && item.id !in base.tagMatches)) }
                records[item.id] = item
            }
            val matched = if (queriedTags) (base.tagMatches + response.items.map { it.id }).size else records.size
            check(matched <= response.total && (response.more || matched == response.total))
            check(records.size <= if (queriedTags) 10020 else 5000)
            return records.values.sortedBy { it.id.toInt() }
        }
        val options = when (response.field) {
            DiscoveryField.PEOPLE -> base.options.copy(people = combined(base.options.people))
            DiscoveryField.TAGS -> base.options.copy(tags = combined(base.options.tags))
            DiscoveryField.PLACES -> base.options.copy(places = combined(base.options.places))
            else -> bad()
        }
        base.copy(options = options, nextPages = (base.nextPages - response.field) + if (response.more) mapOf(response.field to response.page + 1) else emptyMap(),
            facetTotals = base.facetTotals + (response.field to response.total),
            facetLastIds = base.facetLastIds + (response.lastId?.let { mapOf(response.field to it) } ?: emptyMap()),
            tagMatches = if (queriedTags) base.tagMatches + response.items.map { it.id } else base.tagMatches)
    }
    internal fun request(snapshot: DiscoverySnapshot, draft: DiscoveryDraft, page: Int): ByteArray = guarded {
        check(snapshot.revision > 0 && snapshot.catalogRevision > 0 && page in 1..100000 && draft.issue(snapshot.options) == null)
        val d = draft.normalized()
        check(d.themes.isEmpty() && d.topics.isEmpty())
        fun ids(values: Set<String>): JsonArray = JsonArray(values.map { value ->
            check(value.matches(Regex("[1-9][0-9]*"))); JsonPrimitive(value.toIntOrNull()?.takeIf { it > 0 } ?: bad())
        }.sortedBy { it.int })
        val filters = buildJsonObject {
            if (d.people.isNotEmpty()) put("people", buildJsonObject { put("ids", ids(d.people)); put("match", d.peopleMatch.name.lowercase()) })
            if (d.tags.isNotEmpty()) put("tags", buildJsonObject { put("ids", ids(d.tags)); put("match", d.tagsMatch.name.lowercase()) })
            if (d.place != null) put("locations", ids(setOf(d.place)))
            if (d.from.isNotEmpty() || d.through.isNotEmpty()) put("date", buildJsonObject { put("from", d.from.takeIf { it.isNotEmpty() }?.let(::JsonPrimitive) ?: JsonNull); put("to", d.through.takeIf { it.isNotEmpty() }?.let(::JsonPrimitive) ?: JsonNull) })
            if (d.media != null) put("media", JsonArray(listOf(JsonPrimitive(d.media.name.lowercase()))))
            if (d.text.isNotEmpty()) put("caption", d.text)
        }
        buildJsonObject { put("revision", snapshot.revision); put("page", page); put("page_size", 50); put("filters", filters) }.toString().toByteArray(Charsets.UTF_8).also { check(it.size <= 16384) }
    }
    internal fun search(bytes: ByteArray, snapshot: DiscoverySnapshot, page: Int, fingerprint: String? = null, total: Int? = null, version: Int = 1): Search = guarded {
        val o = HomeWire.parse(bytes).obj("version", "revision", "catalog_revision", "library", "filter_fingerprint", "page", "page_size", "total", "has_more", "items")
        check(version in 1..3 && o.getValue("version").int() == version && o.getValue("revision").int() == snapshot.revision && o.getValue("catalog_revision").int() == snapshot.catalogRevision)
        val lib = o.getValue("library").obj("id", "title")
        check(lib.getValue("id").str(64) == snapshot.libraryId && lib.getValue("title").str(256) == snapshot.libraryTitle)
        val hash = o.getValue("filter_fingerprint").str(64).also { check(it.matches(Regex("[0-9a-f]{64}"))) }
        check(fingerprint == null || hash == fingerprint); check(total == null || o.getValue("total").int(0, 100000) == total)
        val translated = JsonObject((o - setOf("catalog_revision", "filter_fingerprint")) + mapOf("version" to JsonPrimitive(if (version >= 2) 3 else 2), "revision" to JsonPrimitive(snapshot.catalogRevision)))
        Search(CatalogWire.feed(translated.toString().toByteArray(Charsets.UTF_8), page, snapshot.catalogRevision, version = if (version >= 2) 3 else 2), hash)
    }
}
