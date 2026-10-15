package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test

class ProtectedLibraryAlbumsTest {
    private fun body(assetIds: String = "[\"41\",\"42\"]", title: String = "\"Family day\"") =
        """{"items":[{"id":"7","title":$title,"title_zh":"","description":"Line 1\nLine 2","theme":"custom","asset_ids":$assetIds,"cover_asset_id":"41","revision":"${"a".repeat(64)}","needs_review":true}],"page":2,"total":11,"page_size":10,"can_manage":false}""".toByteArray()

    @Test fun decodesExactProtectedAlbumPageAndBindsExpectedScope() {
        val page = ProtectedLibraryAlbumsWire.decodePage(body(), "family-a", 2)
        assertEquals("family-a", page.libraryId)
        assertEquals(2, page.page)
        assertEquals(11L, page.total)
        assertEquals(listOf("41", "42"), page.items.single().assetIds)
        assertTrue(page.items.single().needsReview)
        try {
            (page.items.single().assetIds as MutableList<String>).add("43")
            fail("asset list must be immutable")
        } catch (_: UnsupportedOperationException) { }
    }

    @Test fun permitsEmptyAlbumsAndBackendTextLineBreaksButRejectsMalformedRows() {
        val empty = body(assetIds = "[]", title = "\"Family\\nDay\"")
            .toString(Charsets.UTF_8).replace("\"cover_asset_id\":\"41\"", "\"cover_asset_id\":\"\"").toByteArray()
        assertTrue(ProtectedLibraryAlbumsWire.decodePage(empty, "family-a", 2).items.single().assetIds.isEmpty())
        listOf(
            body(assetIds = "[\"41\",\"41\"]"),
            body(assetIds = "[\"01\"]"),
            body(assetIds = "[\"42\"]"),
            body().toString(Charsets.UTF_8).replace("\"revision\":\"${"a".repeat(64)}\"", "\"revision\":\"ABC\"").toByteArray(),
            body().toString(Charsets.UTF_8).replace("\"page_size\":10", "\"page_size\":50").toByteArray(),
        ).forEachIndexed { index, bytes -> invalid(bytes, description = "malformed case $index") }
        invalid(body(), "family-a", 1)
    }

    private fun invalid(bytes: ByteArray, library: String = "family-a", page: Int = 2, description: String = "malformed album response") {
        try { ProtectedLibraryAlbumsWire.decodePage(bytes, library, page); fail("$description accepted") }
        catch (failure: ApiFailure) { assertEquals(FailureKind.INVALID_RESPONSE, failure.kind) }
    }
}
