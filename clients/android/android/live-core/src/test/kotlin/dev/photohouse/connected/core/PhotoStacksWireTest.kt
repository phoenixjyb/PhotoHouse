package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.Gallery
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class PhotoStacksWireTest {
    private val gallery = Gallery("family", 1, 50, 4, false, listOf(
        Asset("40", "image", null, null, null, null, "/40"),
        Asset("20", "image", null, null, null, null, "/20"),
        Asset("30", "image", null, null, null, null, "/30"),
        Asset("50", "video", null, null, null, null, "/50"),
    ))

    @Test fun parsesDisjointPageGroupsAndUsesGalleryOrderedCover() {
        val parsed = PhotoStacksWire.parse(body("""{"version":1,"scope":"page","groups":[{"id":"20","cover_asset_id":"40","asset_ids":["40","20"],"count":2,"reason":"near_capture"}]}"""))
        assertEquals(gallery.items.map { it.id }, parsed.gallery.items.map { it.id })
        assertEquals(PhotoStackGroup("20", "40", listOf("40", "20"), 2, "near_capture"), parsed.groups!!.single())
        assertEquals(listOf("40", "30", "50"), PhotoStackProjection.visibleAssetIds(parsed.gallery, parsed.groups, false, emptySet()))
        assertEquals(listOf("20", "30", "50"), PhotoStackProjection.visibleAssetIds(
            parsed.gallery, parsed.groups, false, emptySet(), coverOverrides = mapOf("20" to "20")))
        assertEquals(gallery.items.map { it.id }, PhotoStackProjection.visibleAssetIds(parsed.gallery, parsed.groups, false, setOf("20")))
        assertEquals(gallery.items.map { it.id }, PhotoStackProjection.visibleAssetIds(parsed.gallery, parsed.groups, false,
            emptySet(), separateGroupIds = setOf("20")))
        assertEquals(gallery.items.map { it.id }, PhotoStackProjection.visibleAssetIds(parsed.gallery, parsed.groups, true, emptySet()))
    }

    @Test fun legacyEnvelopeKeepsEveryPhotoVisible() {
        val parsed = PhotoStacksWire.parse(baseBody().toByteArray())
        assertNull(parsed.groups)
        assertEquals(gallery.items.map { it.id }, PhotoStackProjection.visibleAssetIds(parsed.gallery, parsed.groups, false, emptySet()))
    }

    @Test fun malformedOptionalMetadataFallsBackToAllItems() {
        val overlap = """{"version":1,"scope":"page","groups":[{"id":"20","cover_asset_id":"40","asset_ids":["40","20"],"count":2,"reason":"near_capture"},{"id":"30","cover_asset_id":"30","asset_ids":["30","20"],"count":2,"reason":"same_upload"}]}"""
        val badCover = """{"version":1,"scope":"page","groups":[{"id":"20","cover_asset_id":"20","asset_ids":["40","20"],"count":2,"reason":"near_capture"}]}"""
        for (metadata in listOf(overlap, badCover)) {
            val parsed = PhotoStacksWire.parse(body(metadata))
            assertNull(parsed.groups)
            assertEquals(gallery.items.map { it.id }, PhotoStackProjection.visibleAssetIds(parsed.gallery, parsed.groups, false, emptySet()))
        }
    }

    @Test fun invalidGalleryStillFailsClosed() {
        assertThrows(ApiFailure::class.java) { PhotoStacksWire.parse("{}".toByteArray()) }
        assertTrue(PhotoStacksWire.parse(body("null")).groups == null)
    }

    private fun baseBody() = """{"library_id":"family","page":1,"page_size":50,"total":4,"originals_allowed":false,"items":[{"id":"40","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/40"},{"id":"20","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/20"},{"id":"30","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/30"},{"id":"50","kind":"video","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/50"}]}"""

    private fun body(metadata: String): ByteArray {
        val base = baseBody().dropLast(1)
        return "$base,\"photo_stacks\":$metadata}".toByteArray()
    }
}
