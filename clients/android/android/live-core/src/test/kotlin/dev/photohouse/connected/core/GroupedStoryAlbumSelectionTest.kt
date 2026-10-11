package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class GroupedStoryAlbumSelectionTest {
    private fun album(theme: String = "custom", ids: List<String> = (1..30).map(Int::toString), revision: String = "a".repeat(64)) =
        ProtectedLibraryAlbum("7", "Family day", "家庭日", "", theme, ids, ids.firstOrNull().orEmpty(), revision, false)

    private class FakeApi : PhotoHouseApi, StoryWorkspaceApi {
        override val protectedNativeV2Enabled = true
        var album = GroupedStoryAlbumSelectionTest().album()
        var changeAlbumAfterFirstRead = false
        var albumReads = 0
        var detailReads = 0
        var thumbnails = 0
        var previews = 0
        var saves = 0
        var unsupportedId: String? = null
        var pauseDetailCall: Int? = null
        var detailGate: CompletableDeferred<Unit>? = null
        var detailGateEntered = CompletableDeferred<Unit>()
        var deniedDetailId: String? = null
        var albumGateRead: Int? = null
        var albumGate: CompletableDeferred<Unit>? = null
        var albumGateEntered = CompletableDeferred<Unit>()
        var albumFailureAfterGate: ApiFailure? = null
        var failThumbnailId: String? = null
        var pauseThumbnailId: String? = null
        var thumbnailGate: CompletableDeferred<Unit>? = null
        var thumbnailGateEntered = CompletableDeferred<Unit>()
        var albumPageThumbnailBytes: ByteArray? = null

        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("acct", "+12025550123", listOf(
            Membership("family-a", "active", "member", 1, null, 0, true)))
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) =
            Gallery(library, page, 100, 1, false, listOf(Asset("90", "image", 100, 100, null, null,
                "/assets/90/thumbnail?library=$library")))
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail {
            detailReads++
            if (detailReads == pauseDetailCall) {
                detailGateEntered.complete(Unit)
                detailGate?.let { withContext(NonCancellable) { it.await() } }
            }
            if (assetId == deniedDetailId) throw ApiFailure(FailureKind.HTTP, 403)
            return Detail(library, false, Asset(assetId, if (assetId == unsupportedId) "audio" else "image",
                100, 100, null, null, "/assets/$assetId/thumbnail?library=$library"))
        }
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? {
            thumbnails++
            if (asset.id == failThumbnailId) throw ApiFailure(FailureKind.TLS)
            val bytes = byteArrayOf(1, 2)
            if (asset.id == pauseThumbnailId) {
                albumPageThumbnailBytes = bytes
                thumbnailGateEntered.complete(Unit)
                thumbnailGate?.let { withContext(NonCancellable) { it.await() } }
            }
            if (asset.id == "1") albumPageThumbnailBytes = bytes
            return bytes
        }
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 1, byteArrayOf(0))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = error("album picker must not read originals")
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int) =
            SavedMemoryStoryPage(library, page, 8, false, true, emptyList())
        override suspend fun libraryAlbums(token: Bearer, library: String, page: Int): ProtectedLibraryAlbumPage {
            albumReads++
            if (albumReads == albumGateRead) {
                albumGateEntered.complete(Unit)
                albumGate?.let { withContext(NonCancellable) { it.await() } }
                albumFailureAfterGate?.let { throw it }
            }
            val row = if (changeAlbumAfterFirstRead && albumReads > 1) album.copy(revision = "b".repeat(64)) else album
            return ProtectedLibraryAlbumPage(library, page, 1, 10, false, listOf(row))
        }
        override suspend fun storyPreview(token: Bearer, library: String, json: String): ByteArray { previews++; return byteArrayOf() }
        override suspend fun storyTitleCapabilities(token: Bearer, library: String) = byteArrayOf()
        override suspend fun storyTitles(token: Bearer, library: String, json: String) = byteArrayOf()
        override suspend fun createGroupedStory(token: Bearer, library: String, json: String): ByteArray { saves++; return byteArrayOf() }
    }

    private suspend fun TestScope.signedIn(api: FakeApi): Pair<ConnectedStore, StoryWorkspaceStore> {
        val store = ConnectedStore(api, backgroundScope)
        store.authenticate("+12025550123", "synthetic-password-only", remember = false)
        runCurrent()
        assertEquals("family-a", store.state.value.library)
        assertTrue(store.beginGroupedStoryCreation())
        runCurrent()
        val editor = store.state.value.groupedStoryCreation!!.editor!!
        assertEquals(0, api.previews)
        return store to editor
    }

    @Test fun albumSelectionRefetchesAndRejectsChangedRevisionWithoutReplacingManualSelection() = runTest {
        val api = FakeApi().apply { changeAlbumAfterFirstRead = true }
        val (store, editor) = signedIn(api)
        assertTrue(editor.selectAsset("90"))
        assertTrue(store.loadGroupedStoryAlbums(1))
        runCurrent()
        val selectedAlbum = store.state.value.groupedStoryCreation!!.albumsPage!!.items.single()
        assertTrue(store.selectGroupedStoryAlbum(selectedAlbum, listOf("90"), confirmedReplace = true))
        runCurrent()
        assertTrue(store.state.value.groupedStoryCreation!!.albumChoiceFailure)
        assertEquals(listOf("90"), editor.state.value.selectedAssetIds)
        assertEquals(listOf("90"), store.state.value.groupedStoryCreation!!.gallery!!.items.map { it.id })
        assertEquals(0, api.previews)
        assertEquals(0, api.saves)
    }

    @Test fun successSeedsOrderedFirst24MapsCustomWithoutPreviewOrSave() = runTest {
        val api = FakeApi()
        val (store, editor) = signedIn(api)
        assertTrue(editor.selectAsset("90"))
        assertTrue(store.loadGroupedStoryAlbums(1))
        runCurrent()
        val album = store.state.value.groupedStoryCreation!!.albumsPage!!.items.single()
        val mutableSnapshot = mutableListOf("90")
        assertTrue(store.selectGroupedStoryAlbum(album, mutableSnapshot, confirmedReplace = true))
        mutableSnapshot.clear()
        runCurrent()
        assertEquals((1..24).map(Int::toString), editor.state.value.selectedAssetIds)
        assertEquals("everyday", editor.state.value.theme)
        assertSame(album, store.state.value.groupedStoryCreation!!.selectedAlbum)
        assertEquals(1, store.state.value.groupedStoryCreation!!.albumPage)
        assertEquals((1..8).map(Int::toString), store.state.value.groupedStoryCreation!!.albumAssets.map { it.id })
        assertEquals(8, store.state.value.groupedStoryCreation!!.albumPreviews.size)
        assertEquals(32, api.detailReads) // first 24 validated, then current 8-item browsing page
        assertEquals(10, api.thumbnails) // original gallery page, album page, then return to library
        assertEquals(0, api.previews)
        assertEquals(0, api.saves)

        assertTrue(store.returnToGroupedStoryLibrary())
        runCurrent()
        assertNull(store.state.value.groupedStoryCreation!!.selectedAlbum)
        assertEquals((1..24).map(Int::toString), editor.state.value.selectedAssetIds)
    }

    @Test fun seasonalAlbumMapsToSupportedEverydayTheme() = runTest {
        val api = FakeApi().apply { album = album.copy(theme = "seasonal") }
        val (store, editor) = signedIn(api)
        assertTrue(store.loadGroupedStoryAlbums(1))
        runCurrent()
        val album = store.state.value.groupedStoryCreation!!.albumsPage!!.items.single()
        assertTrue(store.selectGroupedStoryAlbum(album, emptyList(), confirmedReplace = false))
        runCurrent()
        assertEquals("everyday", editor.state.value.theme)
        assertEquals((1..24).map(Int::toString), editor.state.value.selectedAssetIds)
        assertEquals(0, api.previews)
        assertEquals(0, api.saves)
    }

    @Test fun unsupportedAssetInSeedWindowRefusesAtomically() = runTest {
        val api = FakeApi().apply { unsupportedId = "3" }
        val (store, editor) = signedIn(api)
        assertTrue(editor.selectAsset("90"))
        assertTrue(store.loadGroupedStoryAlbums(1))
        runCurrent()
        val album = store.state.value.groupedStoryCreation!!.albumsPage!!.items.single()
        assertTrue(store.selectGroupedStoryAlbum(album, listOf("90"), confirmedReplace = true))
        runCurrent()
        val state = store.state.value.groupedStoryCreation!!
        assertEquals(listOf("90"), editor.state.value.selectedAssetIds)
        assertEquals(listOf("90"), state.gallery!!.items.map { it.id })
        assertEquals(1, state.albumUnsupportedCount)
        assertNull(state.selectedAlbum)
        assertNotNull(state.albumsProblem)
        assertEquals(0, api.previews)
        assertEquals(0, api.saves)
    }

    @Test fun chooserHandoffLeavesBusyOwnedByBlockedAlbumPageUntilItFinishes() = runTest {
        val api = FakeApi().apply {
            pauseDetailCall = 25
            detailGate = CompletableDeferred()
        }
        val (store, editor) = signedIn(api)
        assertTrue(store.loadGroupedStoryAlbums(1))
        runCurrent()
        val album = store.state.value.groupedStoryCreation!!.albumsPage!!.items.single()
        assertTrue(store.selectGroupedStoryAlbum(album, emptyList(), confirmedReplace = false))
        runCurrent()
        assertTrue(api.detailGateEntered.isCompleted)
        assertTrue("album page owns the visible busy state while its detail is pending",
            store.state.value.groupedStoryCreation!!.albumBusy)
        api.detailGate!!.complete(Unit)
        runCurrent()
        assertFalse(store.state.value.groupedStoryCreation!!.albumBusy)
        assertEquals((1..24).map(Int::toString), editor.state.value.selectedAssetIds)
    }

    @Test fun current403ClosesAlbumEditorAndClearsPrivateSelection() = runTest {
        val api = FakeApi().apply { deniedDetailId = "1" }
        val (store, editor) = signedIn(api)
        assertTrue(editor.selectAsset("90"))
        assertTrue(store.loadGroupedStoryAlbums(1))
        runCurrent()
        val album = store.state.value.groupedStoryCreation!!.albumsPage!!.items.single()
        assertTrue(store.selectGroupedStoryAlbum(album, listOf("90"), confirmedReplace = true))
        runCurrent()
        assertNull(store.state.value.groupedStoryCreation)
        assertEquals("acct", store.state.value.session?.account_id)
        assertNull(store.state.value.gallery)
        assertEquals(StoryWorkspaceStoreStatus.SELECTION, editor.state.value.status)
        assertTrue(editor.state.value.selectedAssetIds.isEmpty())
    }

    @Test fun stale403FromOldEditorDoesNotCloseFreshLibraryScope() = runTest {
        val api = FakeApi().apply {
            albumGateRead = 2
            albumGate = CompletableDeferred()
            albumFailureAfterGate = ApiFailure(FailureKind.HTTP, 403)
        }
        val (store, _) = signedIn(api)
        assertTrue(store.loadGroupedStoryAlbums(1))
        runCurrent()
        val album = store.state.value.groupedStoryCreation!!.albumsPage!!.items.single()
        assertTrue(store.selectGroupedStoryAlbum(album, emptyList(), confirmedReplace = false))
        runCurrent()
        assertTrue(api.albumGateEntered.isCompleted)
        store.selectLibrary("family-a")
        runCurrent()
        assertNotNull(store.state.value.gallery)
        api.albumGate!!.complete(Unit)
        runCurrent()
        assertEquals("family-a", store.state.value.library)
        assertEquals("acct", store.state.value.session?.account_id)
        assertNotNull(store.state.value.gallery)
        assertNull(store.state.value.groupedStoryCreation)
    }

    @Test fun failedAlbumPageWipesPartialPreviewBuffersAndPreservesEditorChoices() = runTest {
        val api = FakeApi().apply { failThumbnailId = "2" }
        val (store, editor) = signedIn(api)
        assertTrue(store.loadGroupedStoryAlbums(1))
        runCurrent()
        val album = store.state.value.groupedStoryCreation!!.albumsPage!!.items.single()
        assertTrue(store.selectGroupedStoryAlbum(album, emptyList(), confirmedReplace = false))
        runCurrent()
        assertTrue(api.albumPageThumbnailBytes!!.all { it == 0.toByte() })
        val live = store.state.value.groupedStoryCreation!!
        assertSame(album, live.selectedAlbum)
        assertFalse(live.albumBusy)
        assertTrue(live.albumPreviews.isEmpty())
        assertEquals((1..24).map(Int::toString), editor.state.value.selectedAssetIds)
    }

    @Test fun lateThumbnailAfterAlbumDismissalIsWiped() = runTest {
        val api = FakeApi().apply {
            pauseThumbnailId = "1"
            thumbnailGate = CompletableDeferred()
        }
        val (store, _) = signedIn(api)
        assertTrue(store.loadGroupedStoryAlbums(1))
        runCurrent()
        val album = store.state.value.groupedStoryCreation!!.albumsPage!!.items.single()
        assertTrue(store.selectGroupedStoryAlbum(album, emptyList(), confirmedReplace = false))
        runCurrent()
        assertTrue(api.thumbnailGateEntered.isCompleted)
        val lateBytes = api.albumPageThumbnailBytes!!
        assertTrue(store.closeGroupedStoryCreation(discard = true))
        runCurrent()
        api.thumbnailGate!!.complete(Unit)
        runCurrent()
        assertNull(store.state.value.groupedStoryCreation)
        assertTrue(lateBytes.all { it == 0.toByte() })
    }
}
