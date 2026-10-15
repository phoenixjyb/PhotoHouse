package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryGroupsConnectedStoreTest {
    private val first = Asset("101", "image", 800, 600, null, "2026-01-01T10:00:00", "/assets/101/thumbnail?library=family")
    private val second = first.copy(id = "102", thumbnail_url = "/assets/102/thumbnail?library=family")
    private val note = ProtectedStory("11111111-1111-4111-8111-111111111111", "101", "原话", "我们在湖边散步。", "zh", "家人", "synthetic", 1, 1, 1, true, true)
    private inner class PhotoApi : PhotoHouseApi {
        override val protectedNativeV2Enabled = true
        var noteReads = 0
        var noteGate: CompletableDeferred<Unit>? = null
        var noteError: Exception? = null
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("synthetic", "+12025550100", listOf(Membership("family", "approved", "owner", 1, null, 0, true)))
        override suspend fun acceptInvitation(token: Bearer, code: String) {}
        override suspend fun logout(token: Bearer) {}
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 2, false, listOf(first, second))
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, if (assetId == first.id) first else second)
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")
        override suspend fun stories(token: Bearer, library: String, assetId: String, page: Int): ProtectedStoryPage {
            noteReads++; noteGate?.let { withContext(NonCancellable) { it.await() } }; noteError?.let { throw it }
            return ProtectedStoryPage(library, assetId, page, true, false, if (assetId == first.id) listOf(note) else emptyList())
        }
    }
    private class GroupsApi : MemoryGroupsApi {
        override val memoryGroupsEnabled = true
        var reads = 0
        var failure: Exception? = null
        override suspend fun capabilities(token: Bearer, library: String): MemoryGroupsCapabilities {
            reads++; failure?.let { throw it }; return MemoryGroupsCapabilities(true, true, false, 24, true)
        }
        override suspend fun list(token: Bearer, library: String, assetId: String) = MemoryGroupPage(library, assetId, false, emptyList())
    }
    private fun TestScope.open(photo: PhotoApi, groups: GroupsApi, enabled: Boolean = true): ConnectedStore {
        val store = ConnectedStore(photo, backgroundScope, memoryGroupsApi = groups, memoryGroupsEnabled = enabled)
        store.authenticate("+12025550100", "synthetic-passphrase"); runCurrent()
        store.selectLibrary("family"); runCurrent(); store.openAsset(first); runCurrent()
        return store
    }
    @Test fun explicitOpenRefreshesNotesAndKeepsOnlyThisLibraryPage() = runTest {
        val photo = PhotoApi(); val groups = GroupsApi(); val store = open(photo, groups)
        assertEquals(0, groups.reads); assertEquals(0, photo.noteReads)
        assertEquals(listOf("101", "102"), store.state.value.memoryGroupGallery.map { it.id })
        assertTrue(store.openMemoryGroups()); runCurrent()
        val editor = store.state.value.memoryGroups!!
        assertEquals(1, groups.reads); assertEquals(1, photo.noteReads)
        assertTrue(editor.startCreate()); assertTrue(editor.selectSourceStory(note.id, true)); assertTrue(editor.addAsset("102"))
        assertFalse(store.closeMemoryGroups()); assertTrue(store.closeMemoryGroups(discard = true))
        assertNull(store.state.value.memoryGroups); assertTrue(editor.state.value.availableSources.isEmpty())
    }
    @Test fun disabledProfileMakesNoGroupOrNoteRequestsAndRetainsNoGallery() = runTest {
        val photo = PhotoApi(); val groups = GroupsApi(); val store = open(photo, groups, false)
        assertFalse(store.openMemoryGroups()); runCurrent()
        assertEquals(0, photo.noteReads); assertEquals(0, groups.reads); assertTrue(store.state.value.memoryGroupGallery.isEmpty())
    }
    @Test fun backgroundAndLogoutClearOpenEditorAndRejectLateInitialReads() = runTest {
        for (action in listOf("background", "logout", "photo")) {
            val photo = PhotoApi(); val groups = GroupsApi(); val store = open(photo, groups)
            photo.noteGate = CompletableDeferred(); store.openMemoryGroups(); runCurrent()
            when (action) { "background" -> store.background(); "logout" -> store.logout(); else -> store.openAsset(second) }
            runCurrent(); photo.noteGate!!.complete(Unit); runCurrent()
            assertNull(store.state.value.memoryGroups); assertEquals(0, groups.reads)
        }
        val photo = PhotoApi(); val store = open(photo, GroupsApi()); store.openMemoryGroups(); runCurrent()
        val editor = store.state.value.memoryGroups!!; editor.startCreate(); store.background(); runCurrent()
        assertNull(store.state.value.memoryGroups); assertTrue(store.state.value.memoryGroupGallery.isEmpty())
        assertEquals(MemoryGroupsStorePhase.CLOSED, editor.state.value.phase)
    }
    @Test fun deniedOriginalNoteReadCoversAllPrivateState() = runTest {
        val photo = PhotoApi(); val groups = GroupsApi(); val store = open(photo, groups)
        photo.noteError = ApiFailure(FailureKind.HTTP, 403); store.openMemoryGroups(); runCurrent()
        assertTrue(store.state.value.covered); assertNull(store.state.value.memoryGroups)
        assertNull(store.state.value.detail); assertTrue(store.state.value.memoryGroupGallery.isEmpty()); assertEquals(0, groups.reads)
    }
    @Test fun groupDenialClearsParentEvenWhenMemoryCommunityIsDisabled() = runTest {
        val photo = PhotoApi(); val groups = GroupsApi(); val store = open(photo, groups)
        groups.failure = ApiFailure(FailureKind.HTTP, 401); store.openMemoryGroups(); runCurrent()
        assertTrue(store.state.value.covered); assertNull(store.state.value.memoryGroups)
        assertNull(store.state.value.detail); assertNull(store.state.value.stories)
        assertTrue(store.state.value.memoryGroupGallery.isEmpty())
    }
}
