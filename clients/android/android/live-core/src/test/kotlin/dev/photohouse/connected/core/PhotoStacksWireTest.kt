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

    @Test fun libraryIndexKeepsStableGroupAndPreferenceRevisionsAndBoundsExpandedMembers() {
        val parsed = PhotoStacksWire.parseLibrary(libraryBody().toByteArray())
        assertEquals("library", parsed.scope)
        assertEquals("123e4567-e89b-42d3-a456-426614174000", parsed.indexRevision)
        assertEquals(7L, parsed.preferenceRevision)
        assertEquals(PhotoStackGroup("1", "20", listOf("40", "20", "30"), 3, "near_capture"), parsed.groups!!.single())
        assertEquals(listOf("20", "50"), PhotoStackProjection.visibleAssetIds(parsed.gallery, parsed.groups, false, emptySet()))
    }

    @Test fun libraryIndexRejectsUnboundedOrInconsistentGroupMetadata() {
        val good = libraryBody()
        val badCount = good.replace("\"count\":3", "\"count\":25")
        val extraRoot = good.replace("\"photo_stacks\":", "\"extra\":true,\"photo_stacks\":")
        val duplicateItem = good.replace("\"total\":2", "\"total\":3")
            .replace("\"id\":\"50\",\"kind\":\"video\"", "\"id\":\"40\",\"kind\":\"image\"")
        assertNull(PhotoStacksWire.parseLibrary(badCount.toByteArray()).groups)
        assertNull(PhotoStacksWire.parseLibrary(duplicateItem.toByteArray()).groups)
        assertThrows(ApiFailure::class.java) { PhotoStacksWire.parseLibrary(extraRoot.toByteArray()) }
    }

    @Test fun malformedLibraryEnvelopeRetainsOrdinaryGalleryWithoutGrouping() {
        val malformed = libraryBody().replace("\"preference_revision\":7", "\"preference_revision\":-1")
        val parsed = PhotoStacksWire.parseLibrary(malformed.toByteArray())
        assertEquals(gallery.items.map { it.id }, parsed.gallery.items.map { it.id })
        assertNull(parsed.groups)
        assertEquals("library", parsed.scope)

        val missingEnvelope = PhotoStacksWire.parseLibrary(baseBody().toByteArray())
        assertNull(missingEnvelope.groups)
        assertEquals(gallery.items.map { it.id }, missingEnvelope.gallery.items.map { it.id })
    }

    @Test fun preferenceWritesUseStrictRevisionedStringFieldsAndParseOnlyTheResult() {
        val mutation = PhotoStackPreferenceMutation(
            "123e4567-e89b-42d3-a456-426614174000", 7, groupId = "1", coverAssetId = "20")
        val request = PhotoStacksWire.preferenceRequest("family", mutation)
        assertTrue(request.contains("\"revision\":\"7\""))
        assertTrue(request.contains("\"reset\":\"0\""))
        val result = PhotoStacksWire.parsePreferenceRevision(
            """{"index_revision":"123e4567-e89b-42d3-a456-426614174000","preference_revision":8}""".toByteArray(),
            mutation.indexRevision)
        assertEquals(8L, result.revision)
        assertThrows(ApiFailure::class.java) {
            PhotoStacksWire.parsePreferenceRevision(
                """{"index_revision":"123e4567-e89b-42d3-a456-426614174001","preference_revision":8}""".toByteArray(),
                mutation.indexRevision)
        }
    }

    private fun baseBody() = """{"library_id":"family","page":1,"page_size":50,"total":4,"originals_allowed":false,"items":[{"id":"40","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/40"},{"id":"20","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/20"},{"id":"30","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/30"},{"id":"50","kind":"video","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/50"}]}"""

    private fun libraryBody() = """{"library_id":"family","page":1,"page_size":12,"total":2,"originals_allowed":false,"items":[{"id":"40","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/40/thumbnail?library=family"},{"id":"20","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/20/thumbnail?library=family"},{"id":"30","kind":"image","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/30/thumbnail?library=family"},{"id":"50","kind":"video","width":null,"height":null,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/50/thumbnail?library=family"}],"photo_stacks":{"version":2,"scope":"library","index_revision":"123e4567-e89b-42d3-a456-426614174000","preference_revision":7,"groups":[{"id":"1","cover_asset_id":"20","asset_ids":["40","20","30"],"count":3,"reason":"near_capture"}]}}"""

    private fun body(metadata: String): ByteArray {
        val base = baseBody().dropLast(1)
        return "$base,\"photo_stacks\":$metadata}".toByteArray()
    }
}
