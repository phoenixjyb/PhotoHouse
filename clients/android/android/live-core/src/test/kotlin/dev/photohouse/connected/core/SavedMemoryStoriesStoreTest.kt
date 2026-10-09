package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SavedMemoryStoriesStoreTest {
    private val storyId = "11111111-1111-1111-1111-111111111111"
    private val contributionId = "33333333-3333-3333-3333-333333333333"
    private fun asset(id: String) = Asset(id, "image", 800, 600, null, "2024-05-01", "/assets/$id/thumbnail?library=family")
    private val summary = SavedMemoryStorySummary(storyId, "Garden day", "everyday", "zh", 3, "2", 2, 2, 1720000000, false)
    private fun savedStory(revision: Long = 4, title: String = "Garden day revised", canEdit: Boolean = false) = SavedMemoryStory(storyId, "family", revision, 1710000000, 1720000000, canEdit, "a".repeat(64), title, "everyday", "zh",
        listOf(MemoryStoryAsset(asset("1"), emptyList()), MemoryStoryAsset(asset("2"), emptyList())),
        listOf(SavedMemoryStoryChapter("chapter-1", "Before lunch", "A quiet start.", listOf("1"), emptyList()),
            SavedMemoryStoryChapter("chapter-2", "After lunch", "Then the garden.", listOf("2"), emptyList())), emptyList())

    private fun refs(revision: Long = 4, ids: List<String> = listOf(contributionId)) =
        SavedMemoryStoryContributionReferences(storyId, "family", revision, listOf(
            SavedMemoryChapterContributionReferences("chapter-1", ids),
            SavedMemoryChapterContributionReferences("chapter-2", emptyList()),
        ))

    private fun sourceDetail(
        id: String = contributionId, kind: String = "text", baseRevision: Long = 2,
        chapterId: String? = null, state: String = "accepted", consent: Boolean = true,
    ): MemoryContributionDetail {
        val audio = kind == "audio"
        val contribution = MemoryContribution(id, storyId, "22222222-2222-2222-2222-222222222222", kind,
            "zh", "家人", "a".repeat(64), if (audio) 4500 else null, chapterId, baseRevision,
            state, 1720000000, if (audio) null else "这是家人提供的一段较早文字。", consent)
        val derivation = if (audio) MemoryContributionDerivation(1, "ready", "这是家人录音的转写内容。", "不展示润色文本", emptyList(), null, 1720000000, 1720000001) else null
        return MemoryContributionDetail(MemoryContributionReceipt(contribution, false, false), derivation)
    }

    private inner class Api : PhotoHouseApi, MemoryCommunityApi {
        override val protectedNativeV2Enabled = true
        var listError: Exception? = null
        var detailError: Exception? = null
        var listGate: CompletableDeferred<Unit>? = null
        var detailGate: CompletableDeferred<Unit>? = null
        var referencesError: Exception? = null
        val referencesGates = mutableMapOf<Int, CompletableDeferred<Unit>>()
        val referencesErrors = mutableMapOf<Int, Exception>()
        val referenceResults = mutableMapOf<Int, SavedMemoryStoryContributionReferences>()
        val referencesCalls = mutableListOf<Pair<Long, List<String>>>()
        var contributionDetailError: Exception? = null
        var contributionDetailGate: CompletableDeferred<Unit>? = null
        val contributionDetailGates = mutableMapOf<Int, CompletableDeferred<Unit>>()
        val contributionDetailErrors = mutableMapOf<Int, Exception>()
        var contributionDetailResult: MemoryContributionDetail = sourceDetail()
        val contributionDetailReads = mutableListOf<String>()
        var previewError: Exception? = null
        var coverGate: CompletableDeferred<Unit>? = null
        var coverStarted = false
        var listReads = 0
        var editMode = false
        var saveError: Exception? = null
        var saveGate: CompletableDeferred<Unit>? = null
        var originalDeleteCalls = 0
        var secondLibraryAvailable = false
        var nextRevision = 4L
        var savedRefs: SavedMemoryStoryContributionReferences? = null
        var availableContributions = listOf(contributionId)
        val savedReferenceMutations = mutableListOf<SavedMemoryStoryContributionReferencesMutation>()
        val listRequests = mutableListOf<Pair<Int, String?>>()
        val themeGates = mutableMapOf<String, CompletableDeferred<Unit>>()
        var mismatchThemeResponse = false
        val detailReads = mutableListOf<String>()
        val thumbnailReads = mutableListOf<String>()
        val previewReads = mutableListOf<String>()
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("account", "+8612345678",
            listOf(Membership("family", "approved", if (editMode) "owner" else "viewer", 1, null, 0, true)) +
                if (secondLibraryAvailable) listOf(Membership("family-2", "approved", "owner", 1, null, 0, true)) else emptyList())
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun capabilities(token: Bearer, library: String) = """{"version":1,"enabled":true,"contributions_enabled":true,"generation_enabled":false,"conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,"max_text_bytes":8192,"original_retention":"until_owner_deletes"}""".toByteArray()
        override suspend fun listContributions(token: Bearer, library: String, storyId: String, page: Int): ByteArray {
            val items = availableContributions.joinToString(",") { id ->
                """{"id":"$id","story_id":"$storyId","author_id":"22222222-2222-2222-2222-222222222222","kind":"text","language":"zh","byline":"家人","sha256":"${"a".repeat(64)}","duration_ms":null,"chapter_id":null,"base_story_revision":"2","state":"accepted","created_at":1720000000,"text":"synthetic family memory","processing_consent":true}"""
            }
            return """{"version":1,"story_id":"$storyId","page":$page,"page_size":16,"has_more":false,"can_review":false,"can_delete":false,"items":[$items]}""".toByteArray()
        }
        override suspend fun deleteContribution(token: Bearer, library: String, storyId: String, contributionId: String): ByteArray {
            originalDeleteCalls++
            return byteArrayOf()
        }
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 2, false, listOf(asset("1"), asset("2")))
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, asset(assetId))
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray {
            thumbnailReads += asset.id
            if (asset.id == summary.coverAssetId && coverGate != null) {
                coverStarted = true
                withContext(NonCancellable) { coverGate!!.await() }
            }
            return byteArrayOf(1, 2, 3)
        }
        override suspend fun detailPreview(token: Bearer, library: String, asset: Asset): ByteArray {
            previewReads += asset.id
            previewError?.let { throw it }
            return byteArrayOf(4, 5, 6)
        }
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 1, byteArrayOf(0))
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf(1)
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int, theme: String?): SavedMemoryStoryPage {
            listReads++
            listRequests += page to theme
            listGate?.let { withContext(NonCancellable) { it.await() } }
            themeGates[theme]?.let { withContext(NonCancellable) { it.await() } }
            listError?.let { throw it }
            val itemTheme = if (theme == null || mismatchThemeResponse) "everyday" else theme
            return SavedMemoryStoryPage(library, page, 8, false, false,
                if (page == 1) listOf(summary.copy(theme = itemTheme, canEdit = editMode,
                    revision = if (editMode) nextRevision else summary.revision)) else emptyList())
        }
        override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
            detailReads += storyId
            detailGate?.let { withContext(NonCancellable) { it.await() } }
            detailError?.let { throw it }
            return savedStory(revision = nextRevision, canEdit = editMode)
        }
        override suspend fun savedMemoryStoryContributionReferences(
            token: Bearer, library: String, storyId: String, revision: Long, chapterIds: List<String>,
        ): SavedMemoryStoryContributionReferences {
            referencesCalls += revision to chapterIds
            val call = referencesCalls.size
            referencesGates[call]?.let { withContext(NonCancellable) { it.await() } }
            referencesErrors[call]?.let { throw it }
            referencesError?.let { throw it }
            return referenceResults[call] ?: savedRefs?.takeIf { it.revision == revision } ?: refs(revision)
        }
        override suspend fun saveMemoryStoryContributionReferences(
            token: Bearer, library: String, mutation: SavedMemoryStoryContributionReferencesMutation,
        ): SavedMemoryStory {
            savedReferenceMutations += mutation
            saveGate?.let { withContext(NonCancellable) { it.await() } }
            saveError?.let { throw it }
            nextRevision = mutation.revision + 1
            savedRefs = refs(nextRevision, if (mutation.contributionRefsJson.contains("\"chapter_id\":\"chapter-1\",\"contribution_ids\":[]")) emptyList() else listOf(contributionId))
            return savedStory(revision = nextRevision, canEdit = true)
        }
        override suspend fun savedMemoryContributionDetail(
            token: Bearer, library: String, storyId: String, contributionId: String,
        ): MemoryContributionDetail {
            contributionDetailReads += contributionId
            val call = contributionDetailReads.size
            contributionDetailGates[call]?.let { withContext(NonCancellable) { it.await() } }
            contributionDetailErrors[call]?.let { throw it }
            contributionDetailGate?.let { withContext(NonCancellable) { it.await() } }
            contributionDetailError?.let { throw it }
            return contributionDetailResult
        }
    }

    private fun TestScope.newStore(api: Api, community: Boolean = false): ConnectedStore = ConnectedStore(
        api, backgroundScope, memoryCommunityApi = api, memoryCommunityEnabled = community,
    ) { testScheduler.currentTime }
    private fun TestScope.signIn(store: ConnectedStore) {
        store.authenticate("+8612345678", "synthetic-password")
        runCurrent()
        assertEquals("family", store.state.value.library)
    }

    @Test fun opensDraftLoadsProtectedFramesAndChapterNavigation() = runTest {
        val api = Api(); val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        assertEquals(summary, store.state.value.savedMemoryStories?.result?.items?.single())
        assertEquals(setOf(storyId), store.state.value.savedMemoryStories?.covers?.keys)
        val protectedCover = store.state.value.savedMemoryStories!!.covers.getValue(storyId)
        api.thumbnailReads.clear()
        store.openSavedMemoryStory(summary); runCurrent()
        assertEquals(storyId, store.state.value.savedMemoryStories?.detail?.id)
        assertEquals(4L, store.state.value.savedMemoryStories?.detail?.revision)
        assertEquals("Garden day revised", store.state.value.savedMemoryStories?.selectedSummary?.title)
        assertEquals(4L, store.state.value.savedMemoryStories?.result?.items?.single()?.revision)
        assertEquals("1", store.state.value.savedMemoryStories?.selectedSummary?.coverAssetId)
        assertTrue(store.state.value.savedMemoryStories?.covers?.containsKey(storyId) == false)
        assertEquals(setOf("1"), store.state.value.savedMemoryStories?.frames?.keys)
        assertEquals("1", store.state.value.savedMemoryStories?.heroAssetId)
        assertEquals(listOf("1"), api.previewReads)
        store.loadSavedMemoryChapter(1); runCurrent()
        assertEquals(1, store.state.value.savedMemoryStories?.selectedChapter)
        assertEquals(setOf("2"), store.state.value.savedMemoryStories?.frames?.keys)
        assertEquals("2", store.state.value.savedMemoryStories?.heroAssetId)
        assertEquals(listOf("1", "2"), api.previewReads)
        assertEquals(listOf("1", "2"), api.thumbnailReads)
        store.closeSavedMemoryStories()
        assertTrue(protectedCover.all { it == 0.toByte() })
        assertNull(store.state.value.savedMemoryStories)
    }

    @Test fun chapterReferencesUseFetchedCurrentRevisionAndRevealOnlyExplicitEligibleTextOrReadyTranscript() = runTest {
        val api = Api(); val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(summary); runCurrent()
        assertEquals(listOf(4L to listOf("chapter-1", "chapter-2")), api.referencesCalls)
        assertEquals(listOf(contributionId), store.state.value.savedMemoryStories?.contributionReferences
            ?.chapters?.first()?.contributionIds)
        assertTrue("opening a story fetches only the opaque link graph", api.contributionDetailReads.isEmpty())
        assertNull(store.state.value.savedMemoryStories?.contributionDetail)

        store.loadSavedMemoryStoryContributionDetail("chapter-1", contributionId); runCurrent()
        val oldLinkedText = store.state.value.savedMemoryStories?.contributionDetail?.receipt?.contribution
        assertEquals("这是家人提供的一段较早文字。", oldLinkedText?.text)
        assertEquals(2L, oldLinkedText?.baseStoryRevision)
        assertEquals(listOf(contributionId), api.contributionDetailReads)

        store.closeSavedMemoryStoryContributionDetail()
        api.contributionDetailResult = sourceDetail(kind = "audio", baseRevision = 1, chapterId = "chapter-1")
        store.loadSavedMemoryStoryContributionDetail("chapter-1", contributionId); runCurrent()
        val audio = store.state.value.savedMemoryStories?.contributionDetail
        assertEquals("ready", audio?.derivation?.state)
        assertEquals("这是家人录音的转写内容。", audio?.derivation?.transcript)
        assertEquals("不展示润色文本", audio?.derivation?.polishedText)
        assertEquals(2, api.contributionDetailReads.size)

        store.loadSavedMemoryChapter(1); runCurrent()
        assertNull("chapter navigation clears reviewed source text", store.state.value.savedMemoryStories?.contributionDetail)
        assertEquals(1, store.state.value.savedMemoryStories?.selectedChapter)
    }

    @Test fun sourceRead503LeavesStoryAvailableAndBadDetailEligibilityFailsClosed() = runTest {
        val api = Api().apply { referencesError = ApiFailure(FailureKind.HTTP, 503) }
        val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent(); store.openSavedMemoryStory(summary); runCurrent()
        assertNotNull(store.state.value.savedMemoryStories?.detail)
        assertFalse(store.state.value.savedMemoryStories?.detailUnavailable ?: true)
        assertTrue(store.state.value.savedMemoryStories?.contributionReferencesUnavailable == true)
        assertEquals("Garden day revised", store.state.value.savedMemoryStories?.detail?.title)

        api.referencesError = null
        store.retrySavedMemoryStoryContributionReferences(); runCurrent()
        assertFalse(store.state.value.savedMemoryStories?.contributionReferencesUnavailable ?: true)
        api.contributionDetailResult = sourceDetail(baseRevision = 5)
        store.loadSavedMemoryStoryContributionDetail("chapter-1", contributionId); runCurrent()
        assertNull(store.state.value.savedMemoryStories?.contributionDetail)
        assertTrue(store.state.value.savedMemoryStories?.contributionDetailUnavailable == true)
    }

    @Test fun staleReferenceDenialAfterCloseAndReopenCannotInvalidateCurrentReader() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = Api().apply {
            referencesGates[1] = gate
            referencesErrors[1] = ApiFailure(FailureKind.HTTP, 403)
        }
        val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(summary); runCurrent()
        assertEquals(1, api.referencesCalls.size)
        store.closeSavedMemoryStoryDetail(); runCurrent()
        val refreshedSummary = store.state.value.savedMemoryStories!!.result!!.items.single()
        store.openSavedMemoryStory(refreshedSummary); runCurrent()
        assertEquals(2, api.referencesCalls.size)
        assertNotNull(store.state.value.savedMemoryStories?.contributionReferences)
        gate.complete(Unit); runCurrent()
        assertEquals("account", store.state.value.session?.account_id)
        assertEquals(storyId, store.state.value.savedMemoryStories?.detail?.id)
        assertNotNull(store.state.value.savedMemoryStories?.contributionReferences)
        assertNull(store.state.value.problem)
    }

    @Test fun referenceRefreshRemovingLinkMakesHeldContribution403StaleAndKeepsReader() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = Api().apply {
            contributionDetailGates[1] = gate
            contributionDetailErrors[1] = ApiFailure(FailureKind.HTTP, 403)
            referenceResults[2] = refs(ids = emptyList())
        }
        val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent(); store.openSavedMemoryStory(summary); runCurrent()
        store.loadSavedMemoryStoryContributionDetail("chapter-1", contributionId); runCurrent()
        assertEquals(listOf(contributionId), api.contributionDetailReads)
        assertTrue(store.state.value.savedMemoryStories?.contributionDetailBusy == true)

        store.retrySavedMemoryStoryContributionReferences(); runCurrent()
        assertTrue(store.state.value.savedMemoryStories?.contributionReferences?.chapters?.first()?.contributionIds?.isEmpty() == true)
        assertNull(store.state.value.savedMemoryStories?.contributionDetail)
        assertFalse(store.state.value.savedMemoryStories?.contributionDetailBusy ?: true)
        gate.complete(Unit); runCurrent()
        assertEquals("account", store.state.value.session?.account_id)
        assertEquals(storyId, store.state.value.savedMemoryStories?.detail?.id)
        assertNull(store.state.value.problem)
        assertNull(store.state.value.savedMemoryStories?.contributionDetail)
    }

    @Test fun contributionDetailStartedForAnOldChapterCannotReappearAfterNavigation() = runTest {
        val api = Api().apply { contributionDetailGate = CompletableDeferred() }
        val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent(); store.openSavedMemoryStory(summary); runCurrent()
        store.loadSavedMemoryStoryContributionDetail("chapter-1", contributionId); runCurrent()
        assertEquals(listOf(contributionId), api.contributionDetailReads)
        store.loadSavedMemoryChapter(1); runCurrent()
        api.contributionDetailGate!!.complete(Unit); runCurrent()
        assertEquals(1, store.state.value.savedMemoryStories?.selectedChapter)
        assertNull(store.state.value.savedMemoryStories?.contributionDetail)
        assertFalse(store.state.value.savedMemoryStories?.contributionDetailBusy ?: true)
    }

    @Test fun linkRemovalUsesFrozenRetryAndReopensNewRevisionWithoutDeletingOriginal() = runTest {
        val api = Api().apply { editMode = true; saveError = ApiFailure(FailureKind.OFFLINE) }
        val store = newStore(api, community = true); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        val editable = store.state.value.savedMemoryStories!!.result!!.items.single()
        store.openSavedMemoryStory(editable); runCurrent()
        store.toggleSavedMemoryChapterContribution("chapter-1", contributionId)
        assertTrue(store.state.value.savedMemoryStories!!.contributionReferenceDraft!!["chapter-1"].orEmpty().isEmpty())
        store.toggleSavedMemoryChapterContribution("chapter-1", contributionId)
        assertEquals(listOf(contributionId), store.state.value.savedMemoryStories!!.contributionReferenceDraft!!["chapter-1"])
        store.toggleSavedMemoryChapterContribution("chapter-1", contributionId)
        store.saveSavedMemoryStoryContributionReferences(); runCurrent()
        val frozen = api.savedReferenceMutations.single()
        assertTrue(frozen.contributionRefsJson.contains("\"contribution_ids\":[]"))
        assertTrue(store.state.value.savedMemoryStories!!.contributionReferenceSaveError)
        api.saveError = null
        store.retrySavedMemoryStoryContributionReferencesSave(); runCurrent()
        assertEquals(frozen, api.savedReferenceMutations.last())
        assertEquals(frozen.mutationId, api.savedReferenceMutations.last().mutationId)
        assertEquals(5L, store.state.value.savedMemoryStories?.detail?.revision)
        assertTrue(store.state.value.savedMemoryStories!!.contributionReferences!!.chapters.first().contributionIds.isEmpty())
        assertEquals("Removing a reference never deletes its contribution original", 0, api.originalDeleteCalls)
    }

    @Test fun staleLinkSaveReplyAfterLogoutCannotReopenStoryOrExposePreviousAccountState() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = Api().apply { editMode = true; saveGate = gate }
        val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.single()); runCurrent()
        store.toggleSavedMemoryChapterContribution("chapter-1", contributionId)
        store.saveSavedMemoryStoryContributionReferences(); runCurrent()
        assertTrue(store.state.value.savedMemoryStories!!.contributionReferenceSaveBusy)
        store.logout(); runCurrent()
        gate.complete(Unit); runCurrent()
        assertNull(store.state.value.session)
        assertNull(store.state.value.savedMemoryStories)
        assertEquals(1, api.savedReferenceMutations.size)
    }

    @Test fun staleLinkSaveReplyAfterLibrarySwitchCannotReopenOldLibraryStory() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = Api().apply { editMode = true; secondLibraryAvailable = true; saveGate = gate }
        val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.single()); runCurrent()
        store.toggleSavedMemoryChapterContribution("chapter-1", contributionId)
        store.saveSavedMemoryStoryContributionReferences(); runCurrent()
        store.selectLibrary("family-2"); runCurrent()
        assertEquals("family-2", store.state.value.library)
        gate.complete(Unit); runCurrent()
        assertEquals("family-2", store.state.value.library)
        assertNull(store.state.value.savedMemoryStories)
        assertEquals(1, api.savedReferenceMutations.size)
    }

    @Test fun referenceRevisionConflictOffersReloadAndDoesNotRetryAsNewMutation() = runTest {
        val api = Api().apply { editMode = true; saveError = ApiFailure(FailureKind.HTTP, 409) }
        val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.single()); runCurrent()
        store.toggleSavedMemoryChapterContribution("chapter-1", contributionId)
        store.saveSavedMemoryStoryContributionReferences(); runCurrent()
        assertTrue(store.state.value.savedMemoryStories!!.contributionReferenceSaveConflict)
        val frozenId = api.savedReferenceMutations.single().mutationId
        store.retrySavedMemoryStoryContributionReferencesSave(); runCurrent()
        assertEquals(frozenId, api.savedReferenceMutations.last().mutationId)
        assertEquals(2, api.savedReferenceMutations.size)
    }

    @Test fun themeFilterResetsPagePreservesRefreshAndRejectsStaleOrMismatchedResults() = runTest {
        val api = Api(); val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        assertEquals(1 to null, api.listRequests.last())

        val tripGate = CompletableDeferred<Unit>()
        api.themeGates["trip"] = tripGate
        store.openSavedMemoryStories(1, "trip"); runCurrent()
        assertEquals("trip", store.state.value.savedMemoryStories?.theme)
        store.openSavedMemoryStories(1, "birthday"); runCurrent()
        assertEquals("birthday", store.state.value.savedMemoryStories?.theme)
        assertEquals("birthday", store.state.value.savedMemoryStories?.result?.items?.single()?.theme)
        tripGate.complete(Unit); runCurrent()
        assertEquals("birthday", store.state.value.savedMemoryStories?.theme)
        assertEquals("birthday", store.state.value.savedMemoryStories?.result?.items?.single()?.theme)

        store.openSavedMemoryStories(2); runCurrent()
        assertEquals(2 to "birthday", api.listRequests.last())
        store.openSavedMemoryStories(1); runCurrent()
        assertEquals(1 to "birthday", api.listRequests.last())

        api.mismatchThemeResponse = true
        store.openSavedMemoryStories(1, "trip"); runCurrent()
        assertEquals("trip", store.state.value.savedMemoryStories?.theme)
        assertTrue(store.state.value.savedMemoryStories?.unavailable == true)

        store.openSavedMemoryStories(1, null); runCurrent()
        assertNull(store.state.value.savedMemoryStories?.theme)
        assertFalse(store.state.value.savedMemoryStories?.unavailable ?: true)
        store.openSavedMemoryStories(1, "trip"); runCurrent()
        store.logout(); runCurrent()
        assertNull(store.state.value.savedMemoryStories)
        signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        assertNull(store.state.value.savedMemoryStories?.theme)
    }

    @Test fun staleListReplyAfterCloseCannotReopenPrivateBrowser() = runTest {
        val api = Api().apply { listGate = CompletableDeferred() }; val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        store.closeSavedMemoryStories()
        api.listGate!!.complete(Unit); runCurrent()
        assertNull(store.state.value.savedMemoryStories)
    }

    @Test fun lateShelfCoverCannotReturnAfterClose() = runTest {
        val api = Api().apply { coverGate = CompletableDeferred() }; val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        assertTrue(api.coverStarted)
        store.closeSavedMemoryStories()
        api.coverGate!!.complete(Unit); runCurrent()
        assertNull(store.state.value.savedMemoryStories)
    }

    @Test fun refreshDiscardsStoryDetailStartedFromThePreviousShelf() = runTest {
        val api = Api().apply { detailGate = CompletableDeferred() }; val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.single()); runCurrent()
        assertEquals(listOf(storyId), api.detailReads)
        store.openSavedMemoryStories(); runCurrent()
        assertNotNull(store.state.value.savedMemoryStories?.result)
        api.detailGate!!.complete(Unit); runCurrent()
        assertNull(store.state.value.savedMemoryStories?.detail)
        assertNull(store.state.value.savedMemoryStories?.selectedSummary)
    }

    @Test fun failedLargeHeroPreviewKeepsTheProtectedThumbnailFallback() = runTest {
        val api = Api().apply { previewError = ApiFailure(FailureKind.HTTP, 503) }; val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        store.openSavedMemoryStory(store.state.value.savedMemoryStories!!.result!!.items.single()); runCurrent()
        assertEquals(setOf("1"), store.state.value.savedMemoryStories?.frames?.keys)
        assertArrayEquals(byteArrayOf(1, 2, 3), store.state.value.savedMemoryStories?.frames?.get("1"))
        assertEquals("1", store.state.value.savedMemoryStories?.heroAssetId)
        assertNull(store.state.value.savedMemoryStories?.hero)
        assertFalse(store.state.value.savedMemoryStories?.framesBusy ?: true)
    }

    @Test fun temporaryDetailFailureOffersStoryRetryInsteadOfSayingThereAreNoStories() = runTest {
        val api = Api().apply { detailError = ApiFailure(FailureKind.HTTP, 503) }; val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent(); store.openSavedMemoryStory(summary); runCurrent()
        assertTrue(store.state.value.savedMemoryStories?.detailUnavailable == true)
        assertEquals(Message.UNAVAILABLE, store.state.value.savedMemoryStories?.problem?.message)
        assertNotNull(store.state.value.savedMemoryStories?.result)
        api.detailError = null
        store.retrySavedMemoryStory(); runCurrent()
        assertEquals(storyId, store.state.value.savedMemoryStories?.detail?.id)
    }

    @Test fun unavailableServerDoesNotRenderAnEmptyLibraryAndMediaHandoffReauthorizes() = runTest {
        val api = Api().apply { listError = ApiFailure(FailureKind.HTTP, 503) }; val store = newStore(api); signIn(store)
        store.openSavedMemoryStories(); runCurrent()
        assertTrue(store.state.value.savedMemoryStories?.unavailable == true)
        assertNull(store.state.value.savedMemoryStories?.result)
        api.listError = null
        store.openSavedMemoryStories(); runCurrent(); store.openSavedMemoryStory(summary); runCurrent()
        store.closeSavedMemoryStories(); store.openAssetById("2"); runCurrent()
        assertEquals("2", store.state.value.detail?.asset?.id)
    }
}
