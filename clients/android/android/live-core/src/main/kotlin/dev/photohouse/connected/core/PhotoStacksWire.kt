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

data class PhotoStackGallery(val gallery: Gallery, val groups: List<PhotoStackGroup>?)

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

    /** Malformed optional stack metadata yields a valid page with no grouping. */
    fun parse(bytes: ByteArray): PhotoStackGallery {
        val root = DiscoveryJson.parse(bytes) as? JsonObject ?: bad()
        val galleryObject = JsonObject(root.filterKeys { it != "photo_stacks" })
        val gallery = try {
            Wire.json.decodeFromString(Gallery.serializer(), galleryObject.toString())
        } catch (_: Exception) { bad() }
        if ("photo_stacks" !in root) return PhotoStackGallery(gallery, null)
        val parsed = runCatching { parseGroups(root.getValue("photo_stacks"), gallery) }.getOrNull()
        return PhotoStackGallery(gallery, parsed)
    }

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
