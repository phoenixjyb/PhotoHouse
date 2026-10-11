package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import kotlinx.serialization.json.*
import java.net.URLEncoder
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.time.format.ResolverStyle
import java.util.UUID

enum class MemoryGroupProposalStatus { READY, UNAVAILABLE }

data class MemoryGroupsCapabilities(
    val enabled: Boolean,
    val manual: Boolean,
    val suggestions: Boolean,
    val maxMembers: Int,
    val needsReview: Boolean,
)

data class MemoryGroup(
    val id: String,
    val libraryId: String,
    val revision: Long,
    val theme: String,
    val assetIds: List<String>,
    val excludedAssetIds: List<String>,
    val sourceStoryIds: List<String>,
    val items: List<Asset>,
    val sources: List<ProtectedStory>,
    val canEdit: Boolean,
)

data class MemoryGroupPage(
    val libraryId: String,
    val assetId: String,
    val hasMore: Boolean,
    val items: List<MemoryGroup>,
)

data class MemoryGroupCandidate(
    val asset: Asset,
    val matchedSeedAssetId: String,
    val timeReason: String,
)

data class MemoryGroupProposals(
    val libraryId: String,
    val seedAssetIds: List<String>,
    val needsReview: Boolean,
    val status: MemoryGroupProposalStatus,
    val items: List<MemoryGroupCandidate>,
)

/** Retain and retry this exact value after an uncertain save; never rebuild its mutation ID or body. */
data class MemoryGroupMutation(
    val groupId: String? = null,
    val revision: Long = 0,
    val theme: String,
    val assetIds: List<String>,
    val excludedAssetIds: List<String> = emptyList(),
    val sourceStoryIds: List<String> = emptyList(),
    val mutationId: String = UUID.randomUUID().toString(),
)

interface MemoryGroupsApi {
    val memoryGroupsEnabled: Boolean get() = false
    suspend fun capabilities(token: Bearer, library: String): MemoryGroupsCapabilities = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun list(token: Bearer, library: String, assetId: String): MemoryGroupPage = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun proposals(token: Bearer, library: String, seedIds: List<String>, excludedIds: List<String> = emptyList()): MemoryGroupProposals = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun save(token: Bearer, library: String, mutation: MemoryGroupMutation): MemoryGroup = throw ApiFailure(FailureKind.INVALID_INPUT)
}

internal object MemoryGroupsWire {
    const val RESPONSE_LIMIT = 1024 * 1024
    private val themes = setOf("trip", "growing_up", "birthday", "grandparents", "year_in_review", "everyday")
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(value: Boolean) { if (!value) bad() }
    private fun obj(value: JsonElement?, fields: Set<String>): JsonObject =
        (value as? JsonObject ?: bad()).also { check(it.keys == fields) }
    private fun primitive(value: JsonElement?): JsonPrimitive = value as? JsonPrimitive ?: bad()
    private fun str(value: JsonElement?, maxBytes: Int, allowBlank: Boolean = false): String {
        val p = primitive(value); check(p.isString)
        val result = p.content
        val encoded = try {
            Charsets.UTF_8.newEncoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT)
                .encode(java.nio.CharBuffer.wrap(result)).remaining()
        } catch (_: Exception) { bad() }
        check(encoded <= maxBytes && (allowBlank || result.isNotBlank()))
        check(result.none { it == '\u0000' || it.isISOControl() })
        return result
    }
    private fun bool(value: JsonElement?): Boolean = primitive(value).let { p ->
        check(!p.isString)
        p.booleanOrNull ?: bad()
    }
    private fun int(value: JsonElement?, min: Int = 0, max: Int = Int.MAX_VALUE): Int {
        val p = primitive(value); check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull()?.takeIf { it in min.toLong()..max.toLong() }?.toInt() ?: bad()
    }
    private fun decimal(value: JsonElement?, min: Long = 0): Long {
        val text = str(value, 19)
        check(text.matches(Regex("0|[1-9][0-9]{0,18}")))
        return text.toLongOrNull()?.takeIf { it >= min } ?: bad()
    }
    private fun arr(value: JsonElement?, maximum: Int): JsonArray = (value as? JsonArray ?: bad()).also { check(it.size <= maximum) }
    private fun uuid(value: String): String = value.also {
        check(runCatching { UUID.fromString(it).toString() == it }.getOrDefault(false))
    }
    private fun assetId(value: String): String = value.also {
        check(it.matches(Regex("[1-9][0-9]{0,18}")) && it.toLongOrNull() != null)
    }
    private fun ids(value: JsonElement?, max: Int, uuidIds: Boolean = false): List<String> {
        val result = arr(value, max).map { raw ->
            val item = str(raw, 36)
            if (uuidIds) uuid(item) else assetId(item)
        }
        check(result.distinct().size == result.size)
        return result
    }
    private fun root(bytes: ByteArray): JsonObject = try {
        check(bytes.size in 1..RESPONSE_LIMIT)
        DiscoveryJson.parse(bytes, RESPONSE_LIMIT, 512) as? JsonObject ?: bad()
    } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }

    private fun parseAsset(value: JsonElement?, library: String): Asset {
        val r = obj(value, setOf("id", "kind", "width", "height", "duration_sec", "taken_at", "thumbnail_url"))
        val id = assetId(str(r["id"], 19))
        val kind = str(r["kind"], 8).also { check(it in setOf("image", "video")) }
        fun nullableInt(field: String): Int? = if (r[field] == JsonNull) null else int(r[field], 1, 1_000_000)
        val width = nullableInt("width"); val height = nullableInt("height")
        val duration = if (r["duration_sec"] == JsonNull) null else {
            val p = primitive(r["duration_sec"]); check(!p.isString)
            p.doubleOrNull?.takeIf { it.isFinite() && it in 0.0..1e9 } ?: bad()
        }
        val taken = if (r["taken_at"] == JsonNull) null else str(r["taken_at"], 256)
        val thumbnail = str(r["thumbnail_url"], 2048)
        val expected = "/assets/$id/thumbnail?library=" + URLEncoder.encode(library, "UTF-8")
        check(thumbnail == expected)
        return Asset(id, kind, width, height, duration, taken, thumbnail)
    }

    fun capabilities(bytes: ByteArray): MemoryGroupsCapabilities = guarded {
        val r = root(bytes); obj(r, setOf("version", "enabled", "manual", "suggestions", "max_members", "needs_review"))
        check(int(r["version"], 1, 1) == 1)
        val enabled = bool(r["enabled"]); val manual = bool(r["manual"]); val suggestions = bool(r["suggestions"])
        check((!manual || enabled) && (!suggestions || enabled))
        MemoryGroupsCapabilities(enabled, manual, suggestions, int(r["max_members"], 24, 24), bool(r["needs_review"]).also { check(it) })
    }

    private fun group(value: JsonElement?, library: String): MemoryGroup {
        val r = obj(value, setOf("version", "type", "id", "library_id", "revision", "theme", "asset_ids", "excluded_asset_ids", "source_story_ids", "items", "sources", "can_edit"))
        check(int(r["version"], 1, 1) == 1 && str(r["type"], 32) == "memory_group")
        check(str(r["library_id"], 128) == library && PhoneDiscoveryWire.validLibrary(library))
        val id = uuid(str(r["id"], 36))
        val revision = decimal(r["revision"], 1)
        val theme = str(r["theme"], 32).also { check(it in themes) }
        val assetIds = ids(r["asset_ids"], 24).also { check(it.isNotEmpty()) }
        val excluded = ids(r["excluded_asset_ids"], 512)
        check(assetIds.toSet().intersect(excluded.toSet()).isEmpty())
        val sourceIds = ids(r["source_story_ids"], 12, uuidIds = true)
        val itemsJson = arr(r["items"], 24); check(itemsJson.size == assetIds.size)
        val items = itemsJson.map { parseAsset(it, library) }
        check(items.map { it.id } == assetIds)
        val sourcesJson = arr(r["sources"], 12)
        val sources = sourcesJson.map { raw ->
            val storyBytes = raw.toString().toByteArray(Charsets.UTF_8)
            ProtectedStoriesWire.single(storyBytes, (raw as? JsonObject)?.get("asset_id")?.let { str(it, 19) } ?: bad())
        }
        check(sources.map { it.id } == sourceIds && sources.all { it.assetId in assetIds })
        return MemoryGroup(id, library, revision, theme, assetIds, excluded, sourceIds, items, sources, bool(r["can_edit"]))
    }

    fun page(bytes: ByteArray, library: String, requestedAssetId: String): MemoryGroupPage = guarded {
        val asset = assetId(requestedAssetId)
        val r = root(bytes); obj(r, setOf("version", "library_id", "asset_id", "has_more", "items"))
        check(int(r["version"], 1, 1) == 1 && str(r["library_id"], 128) == library && str(r["asset_id"], 19) == asset)
        val items = arr(r["items"], 8).map { group(it, library) }
        check(items.map { it.id }.distinct().size == items.size && items.all { asset in it.assetIds })
        MemoryGroupPage(library, asset, bool(r["has_more"]), items)
    }

    fun single(bytes: ByteArray, library: String): MemoryGroup = guarded { group(root(bytes), library) }

    fun proposals(bytes: ByteArray, library: String, seedIds: List<String>, excludedIds: List<String> = emptyList()): MemoryGroupProposals = guarded {
        validateIds(seedIds, 24, required = true)
        validateIds(excludedIds, 512)
        check(seedIds.toSet().intersect(excludedIds.toSet()).isEmpty())
        check(PhoneDiscoveryWire.validLibrary(library))
        val r = root(bytes)
        val common = setOf("version", "status", "library_id", "seed_asset_ids", "needs_review", "items")
        obj(r, common)
        check(int(r["version"], 1, 1) == 1 && str(r["library_id"], 128) == library)
        val returnedSeeds = ids(r["seed_asset_ids"], 24)
        check(returnedSeeds == seedIds && bool(r["needs_review"]))
        val status = when (str(r["status"], 16)) {
            "ready" -> MemoryGroupProposalStatus.READY
            "unavailable" -> MemoryGroupProposalStatus.UNAVAILABLE
            else -> bad()
        }
        val items = arr(r["items"], 20).map { raw ->
            val candidate = obj(raw, setOf("id", "kind", "width", "height", "duration_sec", "taken_at", "thumbnail_url", "matched_seed_asset_id", "time_reason"))
            val asset = parseAsset(JsonObject(candidate.filterKeys { it !in setOf("matched_seed_asset_id", "time_reason") }), library)
            check(asset.kind == "image")
            validTimestamp(asset.taken_at ?: bad())
            val matched = assetId(str(candidate["matched_seed_asset_id"], 19)); check(matched in seedIds)
            val reason = str(candidate["time_reason"], 40).also { check(it in setOf("same_recorded_day", "within_recorded_window")) }
            MemoryGroupCandidate(asset, matched, reason)
        }
        check(items.map { it.asset.id }.distinct().size == items.size && items.none { it.asset.id in seedIds || it.asset.id in excludedIds })
        check(items.size <= minOf(20, 24 - seedIds.size))
        check(status == MemoryGroupProposalStatus.READY || items.isEmpty())
        MemoryGroupProposals(library, returnedSeeds, true, status, items)
    }

    fun mutation(value: MemoryGroupMutation): String {
        try {
            value.groupId?.let { require(uuid(it) == it) }
            require(value.revision >= 0 && ((value.groupId == null && value.revision == 0L) || (value.groupId != null && value.revision > 0)))
            require(value.theme in themes)
            validateIds(value.assetIds, 24, required = true)
            validateIds(value.excludedAssetIds, 512)
            validateIds(value.sourceStoryIds, 12, uuidIds = true)
            require(value.assetIds.toSet().intersect(value.excludedAssetIds.toSet()).isEmpty())
            uuid(value.mutationId)
            val encoded = buildJsonObject {
                put("asset_ids", value.assetIds.joinToString(",")); put("excluded_asset_ids", value.excludedAssetIds.joinToString(","))
                put("source_story_ids", value.sourceStoryIds.joinToString(",")); put("theme", value.theme)
                put("revision", value.revision.toString()); put("mutation_id", value.mutationId)
            }.toString()
            require(encoded.toByteArray(Charsets.UTF_8).size <= 24 * 1024)
            return encoded
        } catch (_: ApiFailure) { throw ApiFailure(FailureKind.INVALID_INPUT) }
        catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_INPUT) }
    }

    private fun validateIds(values: List<String>, max: Int, uuidIds: Boolean = false, required: Boolean = false) {
        require(values.size <= max && (!required || values.isNotEmpty()) && values.distinct().size == values.size)
        values.forEach { if (uuidIds) require(uuid(it) == it) else require(assetId(it) == it) }
    }

    fun validateProposalInput(seedIds: List<String>, excludedIds: List<String>) {
        try {
            validateIds(seedIds, 24, required = true)
            validateIds(excludedIds, 512)
            require(seedIds.toSet().intersect(excludedIds.toSet()).isEmpty())
        } catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_INPUT) }
    }

    private fun validTimestamp(value: String) {
        try {
            if (value.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}"))) {
                check(LocalDate.parse(value, DateTimeFormatter.ISO_LOCAL_DATE.withResolverStyle(ResolverStyle.STRICT)).toString() == value)
            } else {
                check(value.length in 16..128 && value[10] in setOf('T', ' ') && value.matches(Regex(
                    "[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\\.[0-9]{1,6})?)?(?:Z|[+-][0-9]{2}:?[0-9]{2})?")))
                val normalized = value.replace(' ', 'T').replace(Regex("([+-][0-9]{2})([0-9]{2})$"), "$1:$2")
                try { OffsetDateTime.parse(normalized, DateTimeFormatter.ISO_DATE_TIME.withResolverStyle(ResolverStyle.STRICT)) }
                catch (_: Exception) { LocalDateTime.parse(normalized, DateTimeFormatter.ISO_DATE_TIME.withResolverStyle(ResolverStyle.STRICT)) }
            }
        } catch (_: ApiFailure) { throw ApiFailure(FailureKind.INVALID_RESPONSE) }
        catch (_: Exception) { bad() }
    }
    private inline fun <T> guarded(block: () -> T): T = try { block() } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
}
