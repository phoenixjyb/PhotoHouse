package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.Captions
import dev.photohouse.protocol.Detail
import dev.photohouse.protocol.Gallery
import dev.photohouse.protocol.Membership
import dev.photohouse.protocol.Session
import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.advanceTimeBy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class GalleryMediaStoreTest {
    private val video = Asset("2", "video", 1920, 1080, 4.0, null, "/video")
    private val photo = Asset("3", "image", 640, 480, null, null, "/photo")
    private val photo40 = Asset("40", "image", 640, 480, null, null, "/photo40")
    private val photo20 = Asset("20", "image", 640, 480, null, null, "/photo20")
    private val photo30 = Asset("30", "image", 640, 480, null, null, "/photo30")
    private val photo10 = Asset("10", "image", 640, 480, null, null, "/photo10")

    @Test fun videoSelectionNextPageDetailAndBackRetainVideoFilter() = runTest {
        val api = Api().apply { mediaFilterEnabled = true }
        val store = open(api)
        store.selectMedia(GalleryMedia.VIDEOS); runCurrent()
        assertEquals(GalleryMedia.VIDEOS, api.calls.last().media)
        assertEquals(1, api.calls.last().page)
        store.navigatePage(2); runCurrent()
        assertEquals(GalleryMedia.VIDEOS, api.calls.last().media)
        assertEquals(2, api.calls.last().page)
        store.openAsset(video); runCurrent()
        assertEquals(GalleryMedia.VIDEOS, store.state.value.media)
        store.backToPhotos(); runCurrent()
        assertEquals(GalleryMedia.VIDEOS, api.calls.last().media)
        assertEquals(2, api.calls.last().page)
    }

    @Test fun selectingPhotosResetsToPageOne() = runTest {
        val api = Api().apply { mediaFilterEnabled = true }
        val store = open(api)
        store.selectMedia(GalleryMedia.VIDEOS); runCurrent(); store.navigatePage(4); runCurrent()
        store.selectMedia(GalleryMedia.PHOTOS); runCurrent()
        assertEquals(GalleryMedia.PHOTOS, api.calls.last().media)
        assertEquals(1, api.calls.last().page)
        assertEquals(GalleryMedia.PHOTOS, store.state.value.media)
    }

    @Test fun staleInflightGalleryCannotReplaceNewSelection() = runTest {
        val api = Api().apply { mediaFilterEnabled = true }
        val store = open(api)
        val gate = CompletableDeferred<Unit>()
        api.gate = gate
        store.loadPage(1, GalleryMedia.VIDEOS); runCurrent()
        store.loadPage(1, GalleryMedia.PHOTOS); runCurrent()
        assertEquals(GalleryMedia.PHOTOS, store.state.value.media)
        gate.complete(Unit); runCurrent()
        assertEquals(GalleryMedia.PHOTOS, store.state.value.media)
        assertEquals("3", store.state.value.gallery!!.items.single().id)
    }

    @Test fun disabledProfileUsesAllOnlyAndRejectsFilteredLoad() = runTest {
        val api = Api()
        val store = open(api)
        assertEquals(GalleryMedia.ALL, api.calls.last().media)
        val before = api.calls.size
        store.selectMedia(GalleryMedia.VIDEOS); runCurrent()
        assertEquals(before, api.calls.size)
        assertThrows(IllegalArgumentException::class.java) { store.loadPage(1, GalleryMedia.VIDEOS) }
        assertFalse(store.mediaFilterEnabled)
    }

    @Test fun supportedStacksCollapseOnlyCurrentPageAndKeepAllPhotosAvailable() = runTest {
        val api = Api().apply {
            stackResponse = PhotoStackGallery(Gallery("family", 1, 50, 5, false,
                listOf(photo40, photo20, photo30, photo10, video)), listOf(
                PhotoStackGroup("20", "40", listOf("40", "20"), 2, "near_capture"),
                PhotoStackGroup("10", "30", listOf("30", "10"), 2, "same_upload"),
            ))
        }
        val store = open(api)
        api.stackCalls = 0
        api.calls.clear()
        store.loadPage(1); runCurrent()
        assertEquals(1, api.stackCalls)
        assertEquals(listOf("20", "10"), store.state.value.photoStacks!!.map { it.id })
        fun visible() = PhotoStackProjection.visibleAssetIds(store.state.value.gallery!!, store.state.value.photoStacks,
            store.state.value.showAllPhotos, store.state.value.expandedPhotoStackIds,
            store.state.value.separatePhotoStackIds, store.state.value.photoStackCoverOverrides)
        assertEquals(listOf("40", "30", "2"), visible())
        store.togglePhotoStack("20")
        assertEquals(listOf("40", "20", "30", "2"), visible())
        store.selectPhotoStackCover("20", "20")
        store.togglePhotoStack("20")
        assertEquals(listOf("20", "30", "2"), visible())
        store.togglePhotoStack("20")
        store.toggleAllPhotos()
        assertEquals(5, visible().size)
        store.toggleAllPhotos()
        store.collapsePhotoStack("20")
        assertFalse("20" in store.state.value.expandedPhotoStackIds)
        assertEquals(listOf("20", "30", "2"), visible())
        store.togglePhotoStack("20")
        store.showPhotoStackSeparately("20")
        assertEquals(listOf("40", "20", "30", "2"), visible())
        assertTrue("20" in store.state.value.separatePhotoStackIds)
        store.toggleAllPhotos()
        assertTrue(store.state.value.showAllPhotos)
        assertEquals(listOf("40", "20", "30", "10", "2"), visible())
        api.stackResponse = null
        store.navigatePage(2); runCurrent()
        assertNull(store.state.value.photoStacks)
        assertTrue(store.state.value.expandedPhotoStackIds.isEmpty())
        assertFalse(store.state.value.showAllPhotos)
    }

    @Test fun onlyExplicitUnsupportedUsesOldGalleryAndOfflineStackReadGetsOneBoundedRetry() = runTest {
        val api = Api().apply { stackFailure = ApiFailure(FailureKind.HTTP, 404) }
        val store = open(api)
        api.stackCalls = 0
        api.calls.clear()
        store.loadPage(1); runCurrent()
        assertEquals(1, api.stackCalls)
        assertEquals(1, api.calls.size)
        assertNull(store.state.value.photoStacks)
        api.stackFailure = ApiFailure(FailureKind.HTTP, 400)
        store.loadPage(1); runCurrent()
        assertEquals(2, api.stackCalls)
        assertEquals(2, api.calls.size)
        api.stackFailure = ApiFailure(FailureKind.OFFLINE)
        val galleryReads = api.calls.size
        store.loadPage(1); runCurrent()
        assertEquals(3, api.stackCalls)
        assertEquals(galleryReads, api.calls.size)
        advanceTimeBy(351); runCurrent()
        assertEquals(4, api.stackCalls)
        assertEquals(galleryReads, api.calls.size)
    }

    @Test fun malformedStackProjectionDoesNotHideItems() = runTest {
        val api = Api().apply {
            stackResponse = PhotoStackGallery(Gallery("family", 1, 50, 3, false, listOf(photo40, photo20, photo30)),
                listOf(PhotoStackGroup("20", "20", listOf("40", "20"), 2, "near_capture")))
        }
        val store = open(api)
        assertNull(store.state.value.photoStacks)
        assertEquals(listOf("40", "20", "30"), PhotoStackProjection.visibleAssetIds(
            store.state.value.gallery!!, store.state.value.photoStacks, false, emptySet(),
            store.state.value.separatePhotoStackIds, store.state.value.photoStackCoverOverrides))
    }

    @Test fun preparedVideosAreOptInAndRetainSelectionAcrossNavigation() = runTest {
        val api = Api().apply { mediaFilterEnabled = true }
        val store = open(api)
        val before = api.calls.size
        store.selectMedia(GalleryMedia.PREPARED_VIDEOS); runCurrent()
        assertEquals(before, api.calls.size)
        assertThrows(IllegalArgumentException::class.java) { store.loadPage(1, GalleryMedia.PREPARED_VIDEOS) }
        api.preparedBrowseEnabled = true
        store.selectMedia(GalleryMedia.PREPARED_VIDEOS); runCurrent()
        assertEquals("video", store.state.value.gallery!!.items.single().kind)
        store.navigatePage(2); runCurrent()
        store.openAsset(video); runCurrent(); store.backToPhotos(); runCurrent()
        assertEquals(GalleryMedia.PREPARED_VIDEOS, api.calls.last().media)
        assertEquals(2, api.calls.last().page)
    }

    private fun TestScope.open(api: Api): ConnectedStore {
        val store = ConnectedStore(api, backgroundScope) { testScheduler.currentTime }
        store.authenticate("+12025550123", "12345678"); runCurrent()
        store.selectLibrary("family"); runCurrent()
        assertEquals(GalleryMedia.ALL, store.state.value.media)
        return store
    }

    private data class Call(val page: Int, val media: GalleryMedia?)

    private inner class Api : PhotoHouseApi {
        override val protectedNativeV2Enabled = true
        override var mediaFilterEnabled = false
        override var preparedBrowseEnabled = false
        var gate: CompletableDeferred<Unit>? = null
        var stackResponse: PhotoStackGallery? = null
        var stackFailure: ApiFailure? = null
        var stackCalls = 0
        val calls = mutableListOf<Call>()
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("synthetic-account", "+12025550123", listOf(Membership("family", "approved", "viewer", 1, null, 0, true)))
        override suspend fun logout(token: Bearer) {}
        override suspend fun gallery(token: Bearer, library: String, page: Int): Gallery {
            calls += Call(page, GalleryMedia.ALL)
            return Gallery(library, page, 50, 1, false, listOf(photo, video))
        }
        override suspend fun gallery(token: Bearer, library: String, page: Int, media: GalleryMedia): Gallery {
            calls += Call(page, media)
            gate?.let { withContext(NonCancellable) { it.await() } }
            val items = when (media) {
                GalleryMedia.VIDEOS, GalleryMedia.PREPARED_VIDEOS -> listOf(video)
                GalleryMedia.PHOTOS -> listOf(photo)
                GalleryMedia.ALL -> listOf(photo, video)
            }
            return Gallery(library, page, 50, 100, false, items)
        }
        override suspend fun galleryWithPhotoStacks(token: Bearer, library: String, page: Int, media: GalleryMedia): PhotoStackGallery {
            stackCalls++
            stackFailure?.let { throw it }
            return stackResponse ?: throw ApiFailure(FailureKind.HTTP, 404)
        }
        override suspend fun acceptInvitation(token: Bearer, code: String) {}
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, if (assetId == video.id) video else photo)
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 0, ByteArray(0))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = byteArrayOf(1)


    }
}
