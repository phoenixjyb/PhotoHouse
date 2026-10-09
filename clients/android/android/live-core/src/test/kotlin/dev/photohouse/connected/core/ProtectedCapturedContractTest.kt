package dev.photohouse.connected.core

import dev.photohouse.protocol.Captions
import dev.photohouse.protocol.Detail
import dev.photohouse.protocol.Gallery
import dev.photohouse.protocol.Session
import dev.photohouse.protocol.SessionToken
import dev.photohouse.protocol.Wire
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Compatibility checks over the named synthetic cases in the adopted snapshot. */
class ProtectedCapturedContractTest {
    private val cases by lazy {
        Wire.json.parseToJsonElement(resource("protected-native-contract/cases.json"))
            .jsonObject.getValue("cases").jsonArray
    }

    private fun resource(path: String): String =
        javaClass.classLoader!!.getResourceAsStream(path).use { stream ->
            requireNotNull(stream) { "missing contract resource: $path" }
                .reader(Charsets.UTF_8).readText()
        }

    private fun body(caseId: String): String = cases.single {
        it.jsonObject.getValue("id").jsonPrimitive.content == caseId
    }.jsonObject.getValue("response").jsonObject.getValue("body").toString()

    @Test
    fun capturedAuthAndSessionResponsesDecode() {
        val token = Wire.json.decodeFromString(SessionToken.serializer(), body("login_8"))
        assertEquals(86400L, token.expires_in)
        assertEquals("LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL", token.access_token)
        assertEquals("Bearer", token.token_type)

        val session = ProtectedAccountWire.session(body("invited_viewer_session"))
        assertEquals("00000000-0000-0000-0000-000000000004", session.account_id)
        assertTrue(session.memberships.single().available)
        assertEquals("Synthetic Member", session.displayName)
        assertEquals("family-a", session.memberships.single().library_id)

        val secondLibrary = ProtectedAccountWire.session(body("accepted_second_library_session"))
        assertEquals(setOf("family-a", "family-b"), secondLibrary.memberships.map { it.library_id }.toSet())
    }

    @Test
    fun capturedGalleryDetailAndCaptionsDecodeWithoutChangingPageSize() {
        val gallery = Wire.json.decodeFromString(Gallery.serializer(), body("gallery_page_one"))
        assertEquals(1, gallery.page)
        assertEquals(1, gallery.page_size)
        assertEquals("102", gallery.items.single().id)
        assertFalse(gallery.originals_allowed)

        val detail = Wire.json.decodeFromString(Detail.serializer(), body("asset_detail"))
        assertEquals("101", detail.asset.id)
        assertFalse(detail.originals_allowed)

        val captions = Wire.json.decodeFromString(Captions.serializer(), body("captions"))
        assertEquals("101", captions.asset_id)
        assertEquals("caption-101", captions.items.single().text)
    }

    @Test
    fun capturedStoriesDecodeAsReadOnlyBilingualFamilyText() {
        val page = ProtectedStoriesWire.parse(body("story_list_page_one").toByteArray(), "family-a", "101", 1)
        assertEquals(5, page.items.size)
        assertTrue(page.hasMore)
        assertFalse(page.canCreate)
        assertEquals("A family story. 奶奶的花园。", page.items.first().text)
        assertEquals("mixed", page.items.first().language)
        assertFalse(page.items.first().canEdit)
        assertFalse(page.items.first().canViewHistory)

        val next = ProtectedStoriesWire.parse(body("story_list_page_two").toByteArray(), "family-a", "101", 2)
        assertEquals(1, next.items.size)
        assertFalse(next.hasMore)
        assertEquals("00000000-0000-0000-0000-00000000006a", next.items.single().id)
    }

    @Test
    fun revokedSessionDecodesButEveryMembershipIsUnavailable() {
        val session = ProtectedAccountWire.session(body("revoked_session_still_authenticated"))
        assertEquals(2, session.memberships.size)
        assertTrue(session.memberships.all { it.status == "revoked" && !it.available })
    }
    @Test fun capturedStoryWritesAndConflictReloadUseServerCurrentRevision() {
        val created = ProtectedStoriesWire.single(body("story_create_1").toByteArray(), "101")
        assertTrue(created.canEdit)
        val updated = ProtectedStoriesWire.single(body("story_update").toByteArray(), "101", created.id)
        assertEquals(2L, updated.revision)
        val retried = ProtectedStoriesWire.single(body("story_exact_old_retry").toByteArray(), "101")
        assertEquals(updated, retried)
        val current = ProtectedStoriesWire.current(body("story_history").toByteArray(), "101", created.id)
        assertEquals(updated, current)
    }

    @Test fun capturedMediaPagesKeepFilteredTotalsAndOrdering() {
        fun gallery(id: String) = Wire.json.decodeFromString(Gallery.serializer(), body(id))
        assertEquals(gallery("gallery_media_default"), gallery("gallery_media_all"))
        val first = gallery("gallery_media_video_page_one")
        val next = gallery("gallery_media_video_page_two")
        assertEquals(2L, first.total); assertEquals(first.total, next.total)
        assertEquals("104", first.items.single().id); assertEquals("101", next.items.single().id)
        assertEquals(2, next.page)
        assertEquals("video", first.items.single().kind)
        assertEquals("image", gallery("gallery_media_image").items.single().kind)
    }

}
