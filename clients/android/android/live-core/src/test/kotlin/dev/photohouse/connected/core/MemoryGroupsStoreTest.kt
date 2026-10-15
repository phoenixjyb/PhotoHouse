package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.withContext
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MemoryGroupsStoreTest {
    private val anchor = asset("101")
    private val other = asset("102")
    private val candidate = asset("103")
    private val storyAnchor = story("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", anchor.id)
    private val storyOther = story("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", other.id)
    private val groupId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"

    private inner class FakeApi : MemoryGroupsApi {
        var overrideEnabled = true
        override val memoryGroupsEnabled: Boolean get() = overrideEnabled
        var deny = false
        var groups = listOf<MemoryGroup>()
        var proposalGate: CompletableDeferred<Unit>? = null
        var lateProposal: MemoryGroupProposals? = null
        var proposalSeeds = mutableListOf<List<String>>()
        var proposalExclusions = mutableListOf<List<String>>()
        var mutations = mutableListOf<MemoryGroupMutation>()
        var saveFailure: Exception? = null
        var saveResults = mutableListOf<MemoryGroup>()
        var saveGate: CompletableDeferred<Unit>? = null
        var lateSave: MemoryGroup? = null
        var capabilityCalls = 0
        var wrongSeeds = false
        var capabilityFailure: Exception? = null
        var capabilitiesValue = MemoryGroupsCapabilities(true, true, true, 24, true)

        private fun auth() { if (deny) throw ApiFailure(FailureKind.HTTP, 401) }
        override suspend fun capabilities(token: Bearer, library: String): MemoryGroupsCapabilities {
            capabilityCalls++; auth(); capabilityFailure?.let { throw it }
            return capabilitiesValue
        }
        override suspend fun list(token: Bearer, library: String, assetId: String): MemoryGroupPage {
            auth(); return MemoryGroupPage(library, assetId, false, groups.filter { assetId in it.assetIds })
        }
        override suspend fun proposals(token: Bearer, library: String, seedIds: List<String>, excludedIds: List<String>): MemoryGroupProposals {
            auth(); proposalSeeds += seedIds.toList(); proposalExclusions += excludedIds.toList()
            val value = MemoryGroupProposals(library, if (wrongSeeds) listOf("999") else seedIds, true, MemoryGroupProposalStatus.READY,
                if (candidate.id in excludedIds) emptyList() else listOf(MemoryGroupCandidate(candidate, seedIds.first(), "within_recorded_window")))
            proposalGate?.let { withContext(NonCancellable) { it.await() } }
            if (proposalGate != null) lateProposal = value
            return value
        }
        override suspend fun save(token: Bearer, library: String, mutation: MemoryGroupMutation): MemoryGroup {
            auth(); mutations += mutation
            saveGate?.let { withContext(NonCancellable) { it.await() } }
            if (saveGate != null) lateSave = group(mutation)
            saveFailure?.let { throw it }
            if (saveResults.isNotEmpty()) return saveResults.removeAt(0)
            return group(mutation)
        }
    }

    private fun group(mutation: MemoryGroupMutation) = MemoryGroup(
        mutation.groupId ?: groupId, "family-a", mutation.revision + 1, mutation.theme,
        mutation.assetIds, mutation.excludedAssetIds, mutation.sourceStoryIds,
        mutation.assetIds.mapNotNull { id -> listOf(anchor, other, candidate).firstOrNull { it.id == id } },
        mutation.sourceStoryIds.mapNotNull { id -> listOf(storyAnchor, storyOther).firstOrNull { it.id == id } }, true,
    )

    private fun editableGroup() = MemoryGroup(
        groupId, "family-a", 4, "trip", listOf(anchor.id, other.id), emptyList(),
        listOf(storyAnchor.id, storyOther.id), listOf(anchor, other), listOf(storyAnchor, storyOther), true,
    )

    private fun kotlinx.coroutines.test.TestScope.store(
        api: FakeApi,
        gallery: List<Asset> = listOf(other),
        scopeValid: () -> Boolean = { true },
        denied: () -> Unit = {},
        preview: suspend (Asset) -> ByteArray? = { null },
    ) = MemoryGroupsStore(api, backgroundScope, Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer")), "family-a", anchor,
        gallery, listOf(storyAnchor), scopeValid, denied,
        now = { testScheduler.currentTime }, preview = preview)

    private suspend fun kotlinx.coroutines.test.TestScope.load(store: MemoryGroupsStore) {
        assertTrue(store.load()); runCurrent(); assertEquals(MemoryGroupsStorePhase.READY, store.state.value.phase)
    }

    @Test fun authExpiryClearsPrivateStateAndCallsOwner() = runTest {
        val api = FakeApi().apply { groups = listOf(editableGroup()); deny = true }
        var denied = 0
        val store = store(api, denied = { denied++ })
        assertTrue(store.load()); runCurrent()
        assertEquals(MemoryGroupsStorePhase.DENIED, store.state.value.phase)
        assertNull(store.state.value.page)
        assertTrue(store.state.value.availableAssets.isEmpty())
        assertEquals(1, denied)
    }

    @Test fun editCanSelectAnotherMembersSourceAndRemovalDropsItsLink() = runTest {
        val api = FakeApi().apply { groups = listOf(editableGroup()) }
        val store = store(api); load(store)
        val newer = editableGroup().copy(sources = listOf(storyAnchor, storyOther.copy(revision = 5)))
        api.groups = listOf(newer)
        assertTrue(store.load()); runCurrent()
        assertTrue(store.startEdit(newer))
        assertTrue(store.state.value.availableSources.any { it.id == storyOther.id })
        assertEquals(5L, store.state.value.availableSources.first { it.id == storyOther.id }.revision)
        assertTrue(store.selectSourceStory(storyOther.id, false))
        assertFalse(storyOther.id in store.state.value.sourceStoryIds)
        assertTrue(store.selectSourceStory(storyOther.id, true))
        assertTrue(store.removeAsset(other.id))
        assertFalse(storyOther.id in store.state.value.sourceStoryIds)
        assertFalse(store.addAsset("999"))
    }

    @Test fun manualSuggestionRemovalSticksAcrossRefreshAndSeedsNeverExpandTransitively() = runTest {
        val api = FakeApi()
        val store = store(api); load(store)
        assertTrue(store.startCreate())
        assertTrue(store.refreshSuggestions()); runCurrent()
        assertEquals(listOf(anchor.id), api.proposalSeeds.single())
        assertTrue(store.selectSuggestion(candidate.id, true))
        assertTrue(store.selectSuggestion(candidate.id, false))
        assertTrue(candidate.id in store.state.value.excludedAssetIds)
        assertTrue(store.refreshSuggestions()); runCurrent()
        assertEquals(listOf(anchor.id), api.proposalSeeds.last())
        assertEquals(listOf(candidate.id), api.proposalExclusions.last())
        assertTrue(store.state.value.proposals?.items.isNullOrEmpty())
    }

    @Test fun editFencesLateSuggestionsEvenWhenApiIgnoresCancellation() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = FakeApi().apply { proposalGate = gate }
        val store = store(api); load(store); assertTrue(store.startCreate())
        assertTrue(store.refreshSuggestions()); runCurrent()
        assertTrue(store.addAsset(other.id))
        gate.complete(Unit); runCurrent()
        assertNull(store.state.value.proposals)
        assertEquals(listOf(anchor.id, other.id), store.state.value.selectedAssetIds)
    }

    @Test fun uncertainSaveRetriesIdenticalMutationAndBody() = runTest {
        val api = FakeApi().apply { saveFailure = ApiFailure(FailureKind.OFFLINE) }
        val store = store(api); load(store); assertTrue(store.startCreate())
        assertTrue(store.addAsset(other.id)); assertTrue(store.setTheme("trip")); assertTrue(store.beginReview())
        val frozen = store.state.value.mutation
        assertTrue(store.confirmSave()); runCurrent()
        assertEquals(MemoryGroupsStorePhase.UNCERTAIN, store.state.value.phase)
        assertFalse(store.addAsset(candidate.id))
        api.saveFailure = null
        assertTrue(store.retryUncertain()); runCurrent()
        assertEquals(MemoryGroupsStorePhase.SAVED, store.state.value.phase)
        assertEquals(listOf(frozen, frozen), api.mutations)
    }

    @Test fun oversizedAndUnexpectedSaveFailuresKeepTheExactMutationForRetry() = runTest {
        for (failure in listOf(ApiFailure(FailureKind.TOO_LARGE), IllegalStateException("response lost"))) {
            val api = FakeApi().apply { saveFailure = failure }
            val store = store(api); load(store); assertTrue(store.startCreate())
            assertTrue(store.addAsset(other.id)); assertTrue(store.beginReview())
            val frozen = store.state.value.mutation
            assertTrue(store.confirmSave()); runCurrent()
            assertEquals(MemoryGroupsStorePhase.UNCERTAIN, store.state.value.phase)
            assertEquals(frozen, store.state.value.mutation)
            api.saveFailure = null
            assertTrue(store.retryUncertain()); runCurrent()
            assertEquals(MemoryGroupsStorePhase.SAVED, store.state.value.phase)
            assertEquals(listOf(frozen, frozen), api.mutations)
        }
    }

    @Test fun uncertainRetryAcceptsAndDisplaysNewerCanonicalServerGroup() = runTest {
        val api = FakeApi().apply { groups = listOf(editableGroup()) }
        val store = store(api); load(store)
        assertTrue(store.startEdit(editableGroup()))
        assertTrue(store.beginReview())
        val frozen = store.state.value.mutation
        api.saveFailure = ApiFailure(FailureKind.OFFLINE)
        assertTrue(store.confirmSave()); runCurrent()
        assertEquals(MemoryGroupsStorePhase.UNCERTAIN, store.state.value.phase)

        val current = editableGroup().copy(
            revision = 9, theme = "birthday", assetIds = listOf(anchor.id, candidate.id),
            sourceStoryIds = listOf(storyAnchor.id), items = listOf(anchor, candidate), sources = listOf(storyAnchor),
        )
        api.saveFailure = null
        api.saveResults += current
        assertTrue(store.retryUncertain()); runCurrent()
        assertEquals(listOf(frozen, frozen), api.mutations)
        assertEquals(MemoryGroupsStorePhase.SAVED, store.state.value.phase)
        assertEquals(current, store.state.value.saved)
        assertEquals(current.assetIds, store.state.value.selectedAssetIds)
        assertEquals(current.sourceStoryIds, store.state.value.sourceStoryIds)
    }

    @Test fun http408KeepsMutationAndHonorsRetryAfter() = runTest {
        val api = FakeApi().apply { saveFailure = ApiFailure(FailureKind.HTTP, 408, 5_000) }
        val store = store(api); load(store); assertTrue(store.startCreate()); assertTrue(store.beginReview())
        val frozen = store.state.value.mutation
        assertTrue(store.confirmSave()); runCurrent()
        assertEquals(MemoryGroupsStorePhase.UNCERTAIN, store.state.value.phase)
        assertEquals(frozen, store.state.value.mutation)
        assertFalse(store.retryUncertain())
        assertEquals(1, api.mutations.size)
        api.saveFailure = null
        advanceTimeBy(5_000)
        assertTrue(store.retryUncertain()); runCurrent()
        assertEquals(listOf(frozen, frozen), api.mutations)
        assertEquals(MemoryGroupsStorePhase.SAVED, store.state.value.phase)
    }

    @Test fun disabledFeatureDoesNotMakeAnyNetworkRequest() = runTest {
        val api = FakeApi().apply { overrideEnabled = false }
        val store = store(api)
        assertFalse(store.load())
        runCurrent()
        assertEquals(0, api.capabilityCalls)
    }

    @Test fun manualOnlyAndReadOnlyCapabilitiesAreValid() = runTest {
        for (capabilities in listOf(
            MemoryGroupsCapabilities(true, true, false, 24, true),
            MemoryGroupsCapabilities(true, false, false, 24, true),
        )) {
            val api = FakeApi().apply { capabilitiesValue = capabilities; groups = listOf(editableGroup()) }
            val store = store(api)
            assertTrue(store.load()); runCurrent()
            assertEquals(MemoryGroupsStorePhase.READY, store.state.value.phase)
            assertEquals(capabilities, store.state.value.capabilities)
            assertEquals(capabilities.manual, store.startEdit(editableGroup()))
        }
    }

    @Test fun loadWaitsForRetryAfterDelay() = runTest {
        val api = FakeApi().apply { capabilityFailure = ApiFailure(FailureKind.HTTP, 429, 5_000) }
        val store = store(api)
        assertTrue(store.load()); runCurrent()
        assertEquals(5_000L, store.state.value.retryAtMillis)
        assertFalse(store.load())
        api.capabilityFailure = null
        advanceTimeBy(5_000)
        assertTrue(store.load()); runCurrent()
        assertEquals(MemoryGroupsStorePhase.READY, store.state.value.phase)
    }

    @Test fun anchorCanBeRemovedAfterAnotherMemberIsAddedAndThenSuggestionsStop() = runTest {
        val api = FakeApi()
        val store = store(api); load(store); assertTrue(store.startCreate())
        assertTrue(store.addAsset(other.id))
        assertTrue(store.removeAsset(anchor.id))
        assertEquals(listOf(other.id), store.state.value.selectedAssetIds)
        assertFalse(store.refreshSuggestions())
        assertTrue(store.beginReview())
        assertEquals(listOf(other.id), store.state.value.mutation?.assetIds)
    }

    @Test fun proposalEnvelopeIsValidatedAtStoreBoundary() = runTest {
        val api = FakeApi().apply { wrongSeeds = true }
        val store = store(api); load(store); assertTrue(store.startCreate())
        assertTrue(store.refreshSuggestions()); runCurrent()
        assertNull(store.state.value.proposals)
        assertFalse(store.state.value.suggestionBusy)
    }

    @Test fun previewsQueueTwoAtATimeSurviveDraftEditsAndAreWipedOnClose() = runTest {
        val gate = CompletableDeferred<Unit>()
        val returned = mutableListOf<ByteArray>()
        var active = 0
        var peak = 0
        val store = store(FakeApi(), gallery = listOf(other, candidate), preview = { asset ->
            active++; peak = maxOf(peak, active)
            withContext(NonCancellable) { gate.await() }
            active--
            ByteArray(16) { asset.id.last().code.toByte() }.also { returned += it }
        })
        load(store); assertTrue(store.startCreate())
        assertTrue(store.loadPreview(anchor.id)); assertTrue(store.loadPreview(other.id)); assertTrue(store.loadPreview(candidate.id))
        runCurrent()
        assertEquals(2, peak)
        assertTrue(store.addAsset(other.id))
        gate.complete(Unit); runCurrent()
        assertEquals(3, store.state.value.previews.size)
        val cached = store.state.value.previews.values.toList()
        store.close()
        assertTrue(cached.all { it.all { byte -> byte == 0.toByte() } })
        assertTrue(returned.all { bytes -> bytes.all { it == 0.toByte() } })
    }

    @Test fun previewAuthenticationFailureDeniesAndWipesStore() = runTest {
        var denied = 0
        val store = store(FakeApi(), denied = { denied++ }, preview = { throw ApiFailure(FailureKind.HTTP, 401) })
        load(store); assertTrue(store.loadPreview(anchor.id)); runCurrent()
        assertEquals(MemoryGroupsStorePhase.DENIED, store.state.value.phase)
        assertTrue(store.state.value.previews.isEmpty())
        assertEquals(1, denied)
    }

    @Test fun withdrawnGroupCannotBeUsedAfterConflictReload() = runTest {
        val api = FakeApi().apply { groups = listOf(editableGroup()) }
        val store = store(api); load(store); assertTrue(store.startEdit(editableGroup()))
        assertTrue(store.setTheme("birthday")); assertTrue(store.beginReview())
        api.saveFailure = ApiFailure(FailureKind.HTTP, 409)
        assertTrue(store.confirmSave()); runCurrent()
        assertEquals(MemoryGroupsStorePhase.CONFLICT, store.state.value.phase)
        api.saveFailure = null; api.groups = emptyList()
        assertTrue(store.reloadConflict()); runCurrent()
        assertFalse(store.state.value.canUseReloadedRevision)
        assertFalse(store.canClose())
        assertTrue(store.discardConflict())
        assertEquals(MemoryGroupsStorePhase.READY, store.state.value.phase)
        assertFalse(store.state.value.availableSources.any { it.id == storyOther.id })
    }

    @Test fun scopeInvalidationWipesLateSaveResponse() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = FakeApi().apply { saveGate = gate }
        var valid = true
        val store = store(api, scopeValid = { valid })
        load(store); assertTrue(store.startCreate()); assertTrue(store.beginReview()); assertTrue(store.confirmSave()); runCurrent()
        valid = false; gate.complete(Unit); runCurrent()
        assertNotNull(api.lateSave)
        assertEquals(MemoryGroupsStorePhase.CLOSED, store.state.value.phase)
        assertNull(store.state.value.saved)
    }

    @Test fun synchronousEmptyPreviewCompletesBeforeAnotherRequestWithoutBlockingIt() = runTest {
        val immediateScope = CoroutineScope(backgroundScope.coroutineContext + UnconfinedTestDispatcher(testScheduler))
        val store = MemoryGroupsStore(FakeApi(), immediateScope,
            Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer")), "family-a", anchor,
            listOf(other), listOf(storyAnchor), { true }, {}, preview = { null })
        load(store)
        repeat(3) { assertTrue(store.loadPreview(anchor.id)) }
        store.close()
    }
    companion object {
        private fun asset(id: String) = Asset(id, "image", 640, 480, null, null, "/assets/$id/thumbnail?library=family-a")
        private fun story(id: String, assetId: String) = ProtectedStory(id, assetId, "Note", "Text", "en", "Byline", "author", 1, 1, 1, true, false)
    }
}
