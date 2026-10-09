package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withContext
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class MemoryBookEditorialSourceInspectionTest {
    private val bookId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    private val storyId = "11111111-1111-4111-8111-111111111111"
    private val contributionId = "33333333-3333-4333-8333-333333333333"

    private class Api(private val bookId: String, private val storyId: String, private val contributionId: String) :
        PhotoHouseApi, MemoryCommunityApi, MemoryBookEditorialApi {
        var accountId = "owner"
        var tokenValue = "T".repeat(43)
        var bookRevision = 7L
        var storyRevision = 2L
        var sourcePresent = true
        var bookCanEdit = true
        var detailFailure: ApiFailure? = null
        var audioFailure: ApiFailure? = null
        var detailKind = "audio"
        var detailChapter: String? = "chapter-1"
        var detailGate: CompletableDeferred<Unit>? = null
        var audioGate: CompletableDeferred<Unit>? = null
        var detailCalls = 0
        var audioCalls = 0
        var audioResponse: ByteArray? = null
        override val protectedNativeV2Enabled = true
        override suspend fun login(phone: String, password: String) = SessionToken(86400, tokenValue, "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session(accountId, "+8612345678", listOf(
            Membership("family", "approved", "owner", 1, null, 0, true), Membership("other", "approved", "owner", 1, null, 0, true)))
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail = error("unused")
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk = error("unused")
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray = error("unused")
        override suspend fun savedMemoryContributionDetail(token: Bearer, library: String, storyId: String, contributionId: String): MemoryContributionDetail {
            detailCalls++
            val response: suspend () -> MemoryContributionDetail = {
                detailFailure?.let { throw it }
                MemoryContributionDetail(
                MemoryContributionReceipt(MemoryContribution(contributionId, storyId, "member", detailKind, "en", "Member", "0".repeat(64),
                    1200, detailChapter, 1, "accepted", 1, if (detailKind == "text") "Original family words" else null, true), false, false),
                MemoryContributionDerivation(1, "ready", "Derived transcript", "Polished derived wording", emptyList(), null, 1, 1),
                )
            }
            return detailGate?.let { gate -> withContext(NonCancellable) { gate.await(); detailGate = null; response() } } ?: response()
        }
        override suspend fun capabilities(token: Bearer, library: String) =
            """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
        override suspend fun contributionAudio(token: Bearer, library: String, storyId: String, contributionId: String): ByteArray {
            audioCalls++
            val response: suspend () -> ByteArray = {
                audioFailure?.let { throw it }
                syntheticWav().also { audioResponse = it }
            }
            return audioGate?.let { gate -> withContext(NonCancellable) { gate.await(); audioGate = null; response() } } ?: response()
        }
        override suspend fun listBooks(token: Bearer, library: String, page: Int) =
            """{"version":1,"library_id":"$library","page":$page,"page_size":8,"has_more":false,"can_create":false,"items":[${bookJson()}]}""".toByteArray()
        override suspend fun getBook(token: Bearer, library: String, bookId: String) = bookJson().toByteArray()
        override suspend fun getBookEditorial(token: Bearer, library: String, bookId: String) =
            """{"version":1,"id":"$bookId","revision":"$bookRevision","state":"empty","children":[{"story_id":"$storyId","revision":"$storyRevision"}],"introduction_source_refs":[],"transitions":[]}""".toByteArray()
        override suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String): ByteArray = error("unused")
        override suspend fun getBookEditorialSourceReferences(token: Bearer, library: String, storyId: String, revision: Long) =
            SavedMemoryStoryContributionReferences(storyId, library, revision,
                listOf(SavedMemoryChapterContributionReferences("chapter-1", if (sourcePresent) listOf(contributionId) else emptyList())))
        private fun bookJson() = """{"version":1,"type":"memoir","id":"$bookId","revision":"$bookRevision","can_edit":$bookCanEdit,"title":"Family book","introduction":"","language":"en","stories":[{"id":"$storyId","title":"Garden","revision":"$storyRevision","item_count":1,"cover_asset_id":"1"}]}"""
    }

    private suspend fun TestScope.opened(api: Api): ConnectedStore {
        val store = ConnectedStore(api, backgroundScope, memoryCommunityApi = api, memoryCommunityEnabled = true)
        store.authenticate("+8612345678", "synthetic-password-only"); runCurrent()
        store.selectLibrary("family"); runCurrent()
        store.openMemoryBooks(); runCurrent()
        store.openMemoryBook(bookId); runCurrent()
        store.openMemoryBookEditorial(); runCurrent()
        return store
    }

    private fun source() = EditorialSourceIdentity(storyId, "2", "chapter-1", contributionId)

    @Test fun detailIsExplicitAndAudioRequiresSeparateVerifiedActionThenDismissWipesIt() = runTest {
        val api = Api(bookId, storyId, contributionId)
        val store = opened(api)
        assertEquals(0, api.detailCalls)
        assertEquals(0, api.audioCalls)
        store.inspectMemoryBookEditorialSource(source()); runCurrent()
        assertEquals(1, api.detailCalls)
        assertEquals("audio", store.state.value.memoryBooks?.sourceInspection?.detail?.receipt?.contribution?.kind)
        assertEquals(0, api.audioCalls)
        store.loadMemoryBookEditorialSourceAudio(); runCurrent()
        val audio = store.state.value.memoryBooks?.sourceInspection?.audio
        assertNotNull(audio)
        assertEquals(1, api.audioCalls)
        store.closeMemoryBookEditorialSourceInspection()
        assertTrue(audio!!.isClosed)
        assertNull(store.state.value.memoryBooks?.sourceInspection?.detail)
    }

    @Test fun acceptsEarlierBaseRevisionAndKeepsOriginalDistinctFromDerivation() = runTest {
        val api = Api(bookId, storyId, contributionId).apply { detailKind = "text"; detailChapter = null }
        val store = opened(api)
        store.inspectMemoryBookEditorialSource(source()); runCurrent()
        val detail = store.state.value.memoryBooks?.sourceInspection?.detail
        assertEquals("Original family words", detail?.receipt?.contribution?.text)
        assertEquals(1L, detail?.receipt?.contribution?.baseStoryRevision)
        assertEquals("Derived transcript", detail?.derivation?.transcript)
        assertEquals(0, api.audioCalls)
    }

    @Test fun deletedOrMismatchedSourceIsUnavailableAndNeverExposesStaleDetail() = runTest {
        val api = Api(bookId, storyId, contributionId).apply { detailKind = "text"; detailChapter = "chapter-2" }
        val store = opened(api)
        store.inspectMemoryBookEditorialSource(source()); runCurrent()
        val inspection = store.state.value.memoryBooks?.sourceInspection
        assertTrue(inspection?.unavailable == true)
        assertNull(inspection?.detail)
        assertNull(inspection?.audio)
        assertEquals(0, api.audioCalls)

        val deletedApi = Api(bookId, storyId, contributionId).apply { detailFailure = ApiFailure(FailureKind.HTTP, 404) }
        val deletedStore = opened(deletedApi)
        deletedStore.inspectMemoryBookEditorialSource(source()); runCurrent()
        assertTrue(deletedStore.state.value.memoryBooks?.sourceInspection?.unavailable == true)
        assertNull(deletedStore.state.value.memoryBooks?.sourceInspection?.detail)
        assertEquals(1, deletedApi.detailCalls)
        assertEquals(0, deletedApi.audioCalls)
    }

    @Test fun denialClearsMemoirAndLateDetailAfterCloseDoesNotRestoreIt() = runTest {
        val deniedApi = Api(bookId, storyId, contributionId).apply { detailFailure = ApiFailure(FailureKind.HTTP, 403) }
        val deniedStore = opened(deniedApi)
        deniedStore.inspectMemoryBookEditorialSource(source()); runCurrent()
        assertNull(deniedStore.state.value.memoryBooks)

        val lateApi = Api(bookId, storyId, contributionId).apply { detailGate = CompletableDeferred() }
        val lateStore = opened(lateApi)
        lateStore.inspectMemoryBookEditorialSource(source()); runCurrent()
        lateStore.closeMemoryBook()
        lateApi.detailGate!!.complete(Unit); runCurrent()
        assertNull(lateStore.state.value.memoryBooks?.sourceInspection?.detail)
        assertEquals(0, lateApi.audioCalls)

        val audioDeniedApi = Api(bookId, storyId, contributionId).apply { audioFailure = ApiFailure(FailureKind.HTTP, 403) }
        val audioDeniedStore = opened(audioDeniedApi)
        audioDeniedStore.inspectMemoryBookEditorialSource(source()); runCurrent()
        audioDeniedStore.loadMemoryBookEditorialSourceAudio(); runCurrent()
        assertNull(audioDeniedStore.state.value.memoryBooks)
        assertTrue(audioDeniedStore.state.value.covered)
    }

    @Test fun lateAudioResponseIsClosedAfterMemoirScopeCloses() = runTest {
        val api = Api(bookId, storyId, contributionId).apply { audioGate = CompletableDeferred() }
        val store = opened(api)
        store.inspectMemoryBookEditorialSource(source()); runCurrent()
        store.loadMemoryBookEditorialSourceAudio(); runCurrent()
        store.closeMemoryBook()
        api.audioGate!!.complete(Unit); runCurrent()
        assertNull(store.state.value.memoryBooks?.sourceInspection?.audio)
        assertTrue("Stale API response bytes are wiped by the repository", api.audioResponse!!.all { it == 0.toByte() })
    }

    @Test fun lateDetailAndAudioResponsesAreRejectedAfterBookAndChildRevisionRefresh() = runTest {
        val detailApi = Api(bookId, storyId, contributionId).apply { detailGate = CompletableDeferred() }
        val detailStore = opened(detailApi)
        detailStore.inspectMemoryBookEditorialSource(source()); runCurrent()
        detailApi.bookRevision = 8L
        detailApi.storyRevision = 3L
        detailStore.refreshMemoryBookEditorialForReview(); runCurrent()
        detailApi.detailGate!!.complete(Unit); runCurrent()
        assertEquals(8L, detailStore.state.value.memoryBooks?.selectedBook?.revision)
        assertEquals(3L, detailStore.state.value.memoryBooks?.selectedBook?.stories?.single()?.revision)
        assertNull(detailStore.state.value.memoryBooks?.sourceInspection?.detail)

        val audioApi = Api(bookId, storyId, contributionId).apply { audioGate = CompletableDeferred() }
        val audioStore = opened(audioApi)
        audioStore.inspectMemoryBookEditorialSource(source()); runCurrent()
        audioStore.loadMemoryBookEditorialSourceAudio(); runCurrent()
        audioApi.storyRevision = 3L
        audioStore.refreshMemoryBookEditorialForReview(); runCurrent()
        audioApi.audioGate!!.complete(Unit); runCurrent()
        assertEquals(3L, audioStore.state.value.memoryBooks?.selectedBook?.stories?.single()?.revision)
        assertNull(audioStore.state.value.memoryBooks?.sourceInspection?.audio)
        assertTrue("Revision-stale API bytes are wiped", audioApi.audioResponse!!.all { it == 0.toByte() })
    }

    @Test fun heldDetailResponseIsRejectedWhenSourceLeavesCurrentCatalog() = runTest {
        val api = Api(bookId, storyId, contributionId).apply { detailGate = CompletableDeferred() }
        val store = opened(api)
        store.inspectMemoryBookEditorialSource(source()); runCurrent()
        api.sourcePresent = false
        store.openMemoryBookEditorial(forceReload = true); runCurrent()
        api.detailGate!!.complete(Unit); runCurrent()
        assertTrue(store.memoryBookEditorialCatalogState.value.sources.isEmpty())
        assertNull(store.state.value.memoryBooks?.sourceInspection?.detail)
    }

    @Test fun heldDetailResponsesAreRejectedAfterLibraryAndAccountInvalidation() = runTest {
        val libraryApi = Api(bookId, storyId, contributionId).apply { detailGate = CompletableDeferred() }
        val libraryStore = opened(libraryApi)
        libraryStore.inspectMemoryBookEditorialSource(source()); runCurrent()
        libraryStore.selectLibrary("other"); runCurrent()
        libraryApi.detailGate!!.complete(Unit); runCurrent()
        assertEquals("other", libraryStore.state.value.library)
        assertNull(libraryStore.state.value.memoryBooks?.sourceInspection?.detail)

        val accountApi = Api(bookId, storyId, contributionId).apply { detailGate = CompletableDeferred() }
        val accountStore = opened(accountApi)
        accountStore.inspectMemoryBookEditorialSource(source()); runCurrent()
        accountStore.logout(); runCurrent()
        accountApi.accountId = "different-owner"
        accountApi.tokenValue = "N".repeat(43)
        accountStore.authenticate("+8612345678", "synthetic-password-only"); runCurrent()
        accountApi.detailGate!!.complete(Unit); runCurrent()
        assertEquals("different-owner", accountStore.state.value.session?.account_id)
        assertNull(accountStore.state.value.memoryBooks?.sourceInspection?.detail)
    }

    @Test fun missingAudioClearsDetailInsteadOfKeepingAStaleInspector() = runTest {
        val api = Api(bookId, storyId, contributionId).apply { audioFailure = ApiFailure(FailureKind.HTTP, 404) }
        val store = opened(api)
        store.inspectMemoryBookEditorialSource(source()); runCurrent()
        assertNotNull(store.state.value.memoryBooks?.sourceInspection?.detail)
        store.loadMemoryBookEditorialSourceAudio(); runCurrent()
        val inspection = store.state.value.memoryBooks?.sourceInspection
        assertTrue(inspection?.unavailable == true)
        assertNull(inspection?.detail)
        assertNull(inspection?.audio)
    }

}

private fun syntheticWav(): ByteArray = ByteArray(46).also { bytes ->
    fun ascii(offset: Int, value: String) = value.forEachIndexed { index, char -> bytes[offset + index] = char.code.toByte() }
    fun u16(offset: Int, value: Int) { bytes[offset] = value.toByte(); bytes[offset + 1] = (value shr 8).toByte() }
    fun u32(offset: Int, value: Int) { repeat(4) { bytes[offset + it] = (value ushr (8 * it)).toByte() } }
    ascii(0, "RIFF"); u32(4, 38); ascii(8, "WAVE"); ascii(12, "fmt "); u32(16, 16)
    u16(20, 1); u16(22, 1); u32(24, 16000); u32(28, 32000); u16(32, 2); u16(34, 16)
    ascii(36, "data"); u32(40, 2); u16(44, 0)
}
