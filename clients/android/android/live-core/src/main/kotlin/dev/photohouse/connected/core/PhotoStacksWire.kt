package dev.photohouse.connected.core

import dev.photohouse.protocol.Gallery
import dev.photohouse.protocol.Wire
import kotlinx.serialization.json.*

data class PhotoStackGroup(
    val id: String,
    val coverAssetId: String,
    val assetIds: List<String>,
    val count: Int,
    val reason: String,
)

data class PhotoStackGallery(
    val gallery: Gallery,
    val groups: List<PhotoStackGroup>?,
    val scope: String? = groups?.let { "page" },
    val indexRevision: String? = null,
    val preferenceRevision: Long? = null,
)

data class PhotoStackPreferenceMutation(
    val indexRevision: String,
    val revision: Long,
    val groupId: String = "",
    val coverAssetId: String = "",
    val separateAssetId: String = "",
    val reset: Boolean = false,
)

data class PhotoStackPreferenceRevision(val indexRevision: String, val revision: Long)

/**
 * Additive gallery envelope parser. The normal gallery remains authoritative: invalid or
 * unsupported stack metadata always falls back to showing every gallery item.
 */
object PhotoStacksWire {
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) bad() }
    private fun JsonElement.obj(vararg keys: String): JsonObject =
        (this as? JsonObject ?: bad()).also { check(it.keys == keys.toSet()) }
    private fun JsonElement.string(): String {
        val p = this as? JsonPrimitive ?: bad()
        check(p.isString && p.content.isNotBlank() && p.content.none { it < ' ' || it == '\u007f' })
        return p.content
    }
    private fun JsonElement.int(min: Int = 0): Int {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it >= min } ?: bad()
    }
    private fun JsonElement.long(): Long {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull() ?: bad()
    }

    /** Malformed optional stack metadata yields a valid page with no grouping. */
    fun parse(bytes: ByteArray): PhotoStackGallery {
        val root = DiscoveryJson.parse(bytes) as? JsonObject ?: bad()
        val galleryObject = JsonObject(root.filterKeys { it != "photo_stacks" })
        val gallery = try {
            Wire.json.decodeFromString(Gallery.serializer(), galleryObject.toString())
        } catch (_: Exception) { bad() }
        if ("photo_stacks" !in root) return PhotoStackGallery(gallery, null)
        val parsed = runCatching { parseGroups(root.getValue("photo_stacks"), gallery) }.getOrNull()
        return PhotoStackGallery(gallery, parsed, "page")
    }

    /** Indexed gallery fields remain usable when the optional grouping envelope is malformed. */
    fun parseLibrary(bytes: ByteArray): PhotoStackGallery {
        val root = DiscoveryJson.parse(bytes) as? JsonObject ?: bad()
        val galleryKeys = setOf("library_id", "page", "page_size", "total", "originals_allowed", "items")
        check(root.keys == galleryKeys || root.keys == galleryKeys + "photo_stacks")
        val galleryObject = JsonObject(root.filterKeys { it != "photo_stacks" })
        val gallery = try { Wire.json.decodeFromString(Gallery.serializer(), galleryObject.toString()) }
        catch (_: Exception) { bad() }
        if ("photo_stacks" !in root) return PhotoStackGallery(gallery, null, "library")
        val parsed = runCatching {
            val envelope = root.getValue("photo_stacks").obj("version", "scope", "index_revision", "preference_revision", "groups")
            check(envelope.getValue("version").int() == 2)
            check(envelope.getValue("scope").string() == "library")
            val revision = envelope.getValue("index_revision").string()
            check(revision.matches(UUID_PATTERN) && revision == revision.lowercase())
            val preferenceRevision = envelope.getValue("preference_revision").long()
            val groups = parseLibraryGroups(envelope.getValue("groups"), gallery)
            PhotoStackGallery(gallery, groups, "library", revision.lowercase(), preferenceRevision)
        }.getOrNull()
        return parsed ?: PhotoStackGallery(gallery, null, "library")
    }

    private fun parseLibraryGroups(value: JsonElement, gallery: Gallery): List<PhotoStackGroup> {
        check(gallery.items.map { it.id }.distinct().size == gallery.items.size)
        val itemById = gallery.items.associateBy { it.id }
        val groups = (value as? JsonArray ?: bad()).also { check(it.size <= 12) }.map { element ->
            val o = element.obj("id", "cover_asset_id", "asset_ids", "count", "reason")
            val id = o.getValue("id").string()
            check(id.matches(Regex("[1-9][0-9]{0,18}")) && id.toLongOrNull() != null)
            val cover = o.getValue("cover_asset_id").string()
            val ids = (o.getValue("asset_ids") as? JsonArray ?: bad()).also { check(it.size in 2..24) }.map { it.string() }
            val count = o.getValue("count").int(2)
            val reason = o.getValue("reason").string()
            check(reason in setOf("near_capture", "same_upload"))
            check(count <= 24 && ids.size == count && ids.distinct().size == ids.size && cover in ids)
            check(ids.all { it.matches(Regex("[1-9][0-9]{0,18}")) && it.toLongOrNull() != null })
            check(ids.all { itemById[it]?.kind == "image" })
            check(id.toLong() <= ids.minOf { it.toLong() })
            val itemOrder = gallery.items.map { it.id }.withIndex().associate { it.value to it.index }
            check(ids == ids.sortedBy { itemOrder.getValue(it) })
            val ordered = ids
            PhotoStackGroup(id, cover, ordered, count, reason)
        }
        val members = groups.flatMap { it.assetIds }
        check(members.distinct().size == members.size && groups.map { it.id }.distinct().size == groups.size)
        check(groups.all { it.coverAssetId in it.assetIds && it.assetIds.size == it.count })
        val visiblePositions = gallery.items.size - groups.sumOf { it.count - 1 }
        val expectedPositions = minOf(12L, (gallery.total - (gallery.page - 1L) * 12).coerceAtLeast(0)).toInt()
        check(gallery.page_size == 12 && gallery.items.size <= 288 && visiblePositions == expectedPositions)
        return groups
    }

    fun parsePreferenceRevision(bytes: ByteArray, expectedIndexRevision: String): PhotoStackPreferenceRevision {
        val o = try { DiscoveryJson.parse(bytes).jsonObject } catch (_: Exception) { bad() }
        check(o.keys == setOf("index_revision", "preference_revision"))
        val rawIndexRevision = o.getValue("index_revision").string()
        val indexRevision = rawIndexRevision.lowercase()
        val preferenceRevision = o.getValue("preference_revision").long()
        check(rawIndexRevision == indexRevision && indexRevision.matches(UUID_PATTERN) && indexRevision == expectedIndexRevision.lowercase())
        return PhotoStackPreferenceRevision(indexRevision, preferenceRevision)
    }

    fun preferenceRequest(library: String, mutation: PhotoStackPreferenceMutation): String {
        require(PhoneDiscoveryWire.validLibrary(library) && mutation.indexRevision.matches(UUID_PATTERN) && mutation.revision >= 0)
        require(if (mutation.reset) mutation.groupId.isEmpty() && mutation.coverAssetId.isEmpty() && mutation.separateAssetId.isEmpty()
            else mutation.groupId.matches(Regex("[1-9][0-9]{0,18}")) && mutation.groupId.toLongOrNull() != null &&
                (mutation.coverAssetId.isNotEmpty() xor mutation.separateAssetId.isNotEmpty()) &&
                listOf(mutation.coverAssetId, mutation.separateAssetId).filter { it.isNotEmpty() }
                    .all { it.matches(Regex("[1-9][0-9]{0,18}")) && it.toLongOrNull() != null })
        return buildJsonObject {
            put("index_revision", mutation.indexRevision.lowercase())
            put("revision", mutation.revision.toString())
            put("group_id", mutation.groupId)
            put("cover_asset_id", mutation.coverAssetId)
            put("separate_asset_id", mutation.separateAssetId)
            put("reset", if (mutation.reset) "1" else "0")
        }.toString().also { require(it.toByteArray(Charsets.UTF_8).size <= 2048) }
    }

    private val UUID_PATTERN = Regex("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    private fun parseGroups(value: JsonElement, gallery: Gallery): List<PhotoStackGroup> {
        val envelope = value.obj("version", "scope", "groups")
        check(envelope.getValue("version").int() == 1)
        check(envelope.getValue("scope").string() == "page")
        val itemById = gallery.items.associateBy { it.id }
        val groups = (envelope.getValue("groups") as? JsonArray ?: bad()).map { element ->
            val o = element.obj("id", "cover_asset_id", "asset_ids", "count", "reason")
            val id = o.getValue("id").string()
            val cover = o.getValue("cover_asset_id").string()
            val ids = (o.getValue("asset_ids") as? JsonArray ?: bad()).map { it.string() }
            val count = o.getValue("count").int(2)
            val reason = o.getValue("reason").string()
            check(reason in setOf("near_capture", "same_upload"))
            check(ids.size == count && ids.size >= 2 && ids.distinct().size == ids.size)
            check(ids.all { it in itemById && itemById.getValue(it).kind == "image" })
            val galleryOrder = gallery.items.map { it.id }.withIndex().associate { it.value to it.index }
            check(ids == ids.sortedBy { galleryOrder.getValue(it) })
            check(id == ids.minBy { it.toLong() })
            check(cover == ids.first())
            PhotoStackGroup(id, cover, ids, count, reason)
        }
        val membership = groups.flatMap { it.assetIds }
        check(membership.distinct().size == membership.size)
        check(groups.map { it.id }.distinct().size == groups.size)
        return groups
    }
}

/** Current-page projection used by the phone grid; it never changes navigation IDs. */
object PhotoStackProjection {
    fun visibleAssetIds(
        gallery: Gallery,
        groups: List<PhotoStackGroup>?,
        showAllPhotos: Boolean,
        expandedGroupIds: Set<String>,
        separateGroupIds: Set<String> = emptySet(),
        coverOverrides: Map<String, String> = emptyMap(),
    ): List<String> {
        val activeGroups = groups.orEmpty().filterNot { it.id in separateGroupIds }
        if (showAllPhotos || activeGroups.isEmpty()) return gallery.items.map { it.id }
        val hidden = activeGroups.asSequence()
            .filter { it.id !in expandedGroupIds }
            .flatMap { group -> group.assetIds.filter { it != (coverOverrides[group.id] ?: group.coverAssetId) }.asSequence() }
            .toSet()
        return gallery.items.map { it.id }.filterNot { it in hidden }
    }
}
