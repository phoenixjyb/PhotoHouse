package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import kotlinx.serialization.json.*
import okhttp3.HttpUrl
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.time.format.ResolverStyle

data class StoryRelatedMediaPage(
    val libraryId: String,
    val seedAssetIds: List<String>,
    val recordedDays: List<String>,
    val hasMore: Boolean,
    val nextBeforeId: String?,
    val items: List<StoryRelatedMediaCandidate>,
)

data class StoryRelatedMediaCandidate(val asset: Asset, val matchReason: String)

internal object StoryRelatedMediaWireLimit {
    const val MAX_PREVIEWS = 20
    const val PREVIEW_BYTES = 2 * 1024 * 1024
}

/** Strict v1 decoder for same recorded capture day suggestions. */
internal object StoryRelatedMediaWire {
    private const val MAX_REQUEST_BYTES = 4096
    private const val MAX_RESPONSE_BYTES = 256 * 1024
    private const val MAX_SEEDS = 24
    private const val MAX_ITEMS = 20

    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun checkWire(ok: Boolean) { if (!ok) bad() }
    private fun obj(value: JsonElement?): JsonObject = value as? JsonObject ?: bad()
    private fun exact(value: JsonObject, vararg keys: String) = checkWire(value.keys == keys.toSet())
    private fun arr(value: JsonElement?, max: Int): JsonArray = (value as? JsonArray)?.also { checkWire(it.size <= max) } ?: bad()
    private fun string(value: JsonElement?, max: Int): String {
        val primitive = value as? JsonPrimitive ?: bad()
        checkWire(primitive.isString && primitive.content.codePointCount(0, primitive.content.length) <= max && '\u0000' !in primitive.content)
        return primitive.content
    }
    private fun bool(value: JsonElement?): Boolean {
        val p = value as? JsonPrimitive ?: bad()
        checkWire(!p.isString)
        return p.booleanOrNull ?: bad()
    }
    private fun int(value: JsonElement?, min: Int = 0, max: Int = Int.MAX_VALUE): Int {
        val p = value as? JsonPrimitive ?: bad()
        checkWire(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it in min..max } ?: bad()
    }
    private fun id(value: String): String = value.also {
        checkWire(it.matches(Regex("[1-9][0-9]{0,18}") ) && it.toLongOrNull()?.toString() == it)
    }

    fun encodeRequest(seedAssetIds: List<String>, beforeId: String?): String {
        require(seedAssetIds.size in 1..MAX_SEEDS && seedAssetIds.distinct().size == seedAssetIds.size)
        seedAssetIds.forEach { require(it.matches(Regex("[1-9][0-9]{0,18}")) && it.toLongOrNull()?.toString() == it) }
        if (beforeId != null) require(beforeId.matches(Regex("[1-9][0-9]{0,18}")) && beforeId.toLongOrNull()?.toString() == beforeId)
        val body = buildJsonObject {
            put("asset_ids", seedAssetIds.joinToString(",")); put("before_id", beforeId ?: "")
        }.toString()
        require(body.toByteArray(Charsets.UTF_8).size <= MAX_REQUEST_BYTES)
        return body
    }

    fun decode(bytes: ByteArray, library: String, seeds: List<String>, beforeId: String?): StoryRelatedMediaPage = try {
        checkWire(bytes.size <= MAX_RESPONSE_BYTES && seeds.size in 1..MAX_SEEDS && seeds.distinct().size == seeds.size)
        checkWire(PhoneDiscoveryWire.validLibrary(library))
        val root = obj(DiscoveryJson.parse(bytes, MAX_RESPONSE_BYTES, MAX_SEEDS))
        exact(root, "version", "library_id", "seed_asset_ids", "recorded_days", "needs_review", "has_more", "next_before_id", "items")
        checkWire(int(root["version"], 1, 1) == 1 && string(root["library_id"], 128) == library && bool(root["needs_review"]))
        val returnedSeeds = arr(root["seed_asset_ids"], MAX_SEEDS).map { id(string(it, 19)) }
        checkWire(returnedSeeds == seeds)
        val days = arr(root["recorded_days"], MAX_SEEDS).map { day(string(it, 10)) }
        checkWire(days.distinct().size == days.size && days == days.sorted())
        val hasMore = bool(root["has_more"])
        val next = root["next_before_id"].let { if (it == JsonNull) null else id(string(it, 19)) }
        checkWire(hasMore == (next != null))
        if (beforeId != null) {
            checkWire(id(beforeId) == beforeId)
            if (next != null) checkWire(next.toLong() < beforeId.toLong())
        }
        val items = arr(root["items"], MAX_ITEMS).map { raw ->
            val item = obj(raw)
            exact(item, "id", "kind", "width", "height", "duration_sec", "taken_at", "thumbnail_url", "match_reason")
            val assetId = id(string(item["id"], 19))
            checkWire(assetId !in seeds)
            if (beforeId != null) checkWire(assetId.toLong() < beforeId.toLong())
            val kind = string(item["kind"], 8)
            checkWire(kind in setOf("image", "video"))
            fun dimension(key: String) = item[key].let { if (it == JsonNull) null else int(it, 1, 1_000_000) }
            val width = dimension("width"); val height = dimension("height")
            val duration = item["duration_sec"].let { if (it == JsonNull) null else {
                val p = it as? JsonPrimitive ?: bad(); checkWire(!p.isString)
                (p.doubleOrNull ?: bad()).also { v -> checkWire(v.isFinite() && v in 0.0..1e9) }
            } }
            val takenAt = item["taken_at"].let { if (it == JsonNull) null else string(it, 256).also(::validTimestamp) }
            checkWire(takenAt != null && takenAt.substring(0, 10) in days)
            val thumbnail = string(item["thumbnail_url"], 2048)
            checkWire(thumbnail.startsWith('/') && !thumbnail.startsWith("//") && '\\' !in thumbnail)
            val base = HttpUrl.Builder().scheme("https").host("contract.invalid").build()
            val expected = base.newBuilder().addPathSegment("assets").addPathSegment(assetId).addPathSegment("thumbnail")
                .addQueryParameter("library", library).build()
            checkWire(base.resolve(thumbnail) == expected)
            checkWire(string(item["match_reason"], 64) == "same_recorded_capture_day")
            StoryRelatedMediaCandidate(Asset(assetId, kind, width, height, duration, takenAt, thumbnail), "same_recorded_capture_day")
        }
        checkWire(items.map { it.asset.id }.distinct().size == items.size)
        checkWire(items.zipWithNext().all { (a, b) -> a.asset.id.toLong() > b.asset.id.toLong() })
        if (items.isNotEmpty() && next != null) checkWire(next.toLong() <= items.last().asset.id.toLong())
        if (days.isEmpty()) checkWire(items.isEmpty() && !hasMore && next == null)
        StoryRelatedMediaPage(library, returnedSeeds, days, hasMore, next, items)
    } catch (failure: ApiFailure) { throw failure }
    catch (_: Exception) { bad() }

    private fun day(value: String): String {
        checkWire(value.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}")))
        checkWire(!value.startsWith("0000-"))
        return try { LocalDate.parse(value, DateTimeFormatter.ISO_LOCAL_DATE.withResolverStyle(ResolverStyle.STRICT)).toString() }
        catch (_: Exception) { bad() }
    }

    private fun validTimestamp(value: String) {
        try {
            if (value.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}"))) day(value)
            else {
                checkWire(value.length in 16..64 && value[10] in setOf('T', ' ') && value.matches(Regex(
                    "[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\\.[0-9]{1,6})?)?(?:Z|[+-][0-9]{2}:?[0-9]{2})?")))
                val normalized = value.replace(' ', 'T').replace(Regex("([+-][0-9]{2})([0-9]{2})$"), "$1:$2")
                try { OffsetDateTime.parse(normalized, DateTimeFormatter.ISO_DATE_TIME.withResolverStyle(ResolverStyle.STRICT)) }
                catch (_: Exception) { LocalDateTime.parse(normalized, DateTimeFormatter.ISO_DATE_TIME.withResolverStyle(ResolverStyle.STRICT)) }
                day(value.substring(0, 10))
            }
        } catch (failure: ApiFailure) { throw failure }
        catch (_: Exception) { bad() }
    }
}
