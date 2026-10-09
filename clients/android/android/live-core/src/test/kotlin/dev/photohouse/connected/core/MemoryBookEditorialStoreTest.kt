package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class MemoryBookEditorialStoreTest {
    private val bookId = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    private val storyId = "11111111-1111-1111-1111-111111111111"
    private val secondStoryId = "22222222-2222-2222-2222-222222222222"
    private val contributionId = "33333333-3333-3333-3333-333333333333"
    private val child = EditorialChild(storyId, "2")
    private val source = EditorialSourceIdentity(storyId, "2", "chapter-1", contributionId)
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))

    private fun context(
        revision: String = "4",
        session: String = "session-1",
        library: String = "family",
        children: List<EditorialChild> = listOf(child),
        sources: Set<EditorialSourceIdentity> = setOf(source),
    ) = MemoryBookEditorialContext(session, token, library, bookId, revision, children, sources)

    private fun response(
        revision: String,
        state: String = "current",
        children: List<EditorialChild> = listOf(child),
    ): ByteArray {
        val childJson = children.joinToString(",") { """{"story_id":"${it.storyId}","revision":"${it.revision}"}""" }
        return """{"version":1,"id":"$bookId","revision":"$revision","children":[$childJson],"state":"$state","introduction_source_refs":[],"transitions":[]}""".toByteArray()
    }

    private class Api(private val bookId: String, private val storyId: String) : MemoryBookEditorialApi {
        var getError: Exception? = null
        var saveError: Exception? = null
        var getGate: CompletableDeferred<Unit>? = null
        var saveGate: CompletableDeferred<Unit>? = null
        var getResponse: ByteArray? = null
        var saveResponse: ByteArray? = null
        val gets = mutableListOf<Triple<String, String, String>>()
        val saves = mutableListOf<Triple<String, String, String>>()

        override suspend fun getBookEditorial(token: Bearer, library: String, bookId: String): ByteArray {
            gets += Triple(library, bookId, "get")
            getGate?.await()
            getError?.let { throw it }
            return getResponse ?: body("4")
        }

        override suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String): ByteArray {
            saves += Triple(library, bookId, json)
            saveGate?.await()
            saveError?.let { throw it }
            return saveResponse ?: body("5")
        }

        private fun body(revision: String) = """{"version":1,"id":"$bookId","revision":"$revision","children":[{"story_id":"$storyId","revision":"2"}],"state":"current","introduction_source_refs":[],"transitions":[]}""".toByteArray()
    }

    private fun newStore(api: Api, ids: MutableList<String> = mutableListOf("99999999-9999-9999-9999-999999999999")) =
        MemoryBookEditorialStore(MemoryBookEditorialRepository(api)) { ids.removeAt(0) }

    private suspend fun loaded(store: MemoryBookEditorialStore) {
        store.setContext(context())
        store.load()
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
    }

    @Test fun freezesMutationForExplicitRetryAndDoesNotSubmitTwiceWhilePending() = runTest {
        val api = Api(bookId, storyId).apply { saveError = ApiFailure(FailureKind.OFFLINE) }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.save()
        assertEquals(MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        assertEquals(1, api.saves.size)
        val frozenPayload = api.saves.single().third
        api.saveError = null
        api.saveGate = CompletableDeferred()
        val retry = async { store.retryUncertainSave() }
        runCurrent()
        assertEquals(2, api.saves.size)
        assertEquals(frozenPayload, api.saves.last().third)
        store.save()
        store.retryUncertainSave()
        assertEquals(2, api.saves.size)
        api.saveGate!!.complete(Unit)
        retry.await()
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
    }

    @Test fun uncertainSaveKeepsFrozenRequestAcrossNewerEditsUntilExplicitRetry() = runTest {
        val api = Api(bookId, storyId).apply { saveError = ApiFailure(FailureKind.OFFLINE) }
        val ids = mutableListOf("99999999-9999-9999-9999-999999999999", "88888888-8888-8888-8888-888888888888")
        val store = newStore(api, ids)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.save()
        val originalBody = api.saves.single().third
        store.edit(emptyList(), emptyList())
        assertEquals(MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        store.discardDraft()
        store.load()
        assertEquals(1, api.gets.size)
        assertTrue(store.state.value.dirty)
        store.save()
        assertEquals(1, api.saves.size)
        api.saveError = null
        store.retryUncertainSave()
        assertEquals(2, api.saves.size)
        assertEquals(originalBody, api.saves.last().third)
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
        assertTrue(store.state.value.dirty)
        assertTrue(store.state.value.draft!!.introductionSourceRefs.isEmpty())
        assertTrue("88888888-8888-8888-8888-888888888888" in ids)
    }

    @Test fun httpServerErrorKeepsFrozenRequestForExplicitRetry() = runTest {
        val api = Api(bookId, storyId).apply { saveError = ApiFailure(FailureKind.HTTP, 500) }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.save()
        val body = api.saves.single().third
        assertEquals(MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        api.saveError = null
        store.retryUncertainSave()
        assertEquals(body, api.saves.last().third)
        assertEquals(2, api.saves.size)
    }

    @Test fun invalidLocalMutationSendsNothingAndCanBeRepaired() = runTest {
        val api = Api(bookId, storyId)
        val store = newStore(api, mutableListOf(
            "99999999-9999-9999-9999-999999999999", "88888888-8888-8888-8888-888888888888",
        ))
        loaded(store)
        val invalid = source.copy(contributionId = "44444444-4444-4444-4444-444444444444")
        store.edit(listOf(invalid), emptyList())
        store.save()
        assertTrue(api.saves.isEmpty())
        assertEquals(MemoryBookEditorialStoreStatus.INVALID, store.state.value.status)
        assertEquals(listOf(invalid), store.state.value.draft!!.introductionSourceRefs)
        store.edit(listOf(source), emptyList())
        store.save()
        assertEquals(1, api.saves.size)
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
    }

    @Test fun deniedSaveClearsDraftServerAndRequestContext() = runTest {
        val api = Api(bookId, storyId).apply { saveError = ApiFailure(FailureKind.HTTP, 403) }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.save()
        assertEquals(MemoryBookEditorialStoreStatus.ACCESS_REVOKED, store.state.value.status)
        assertNull(store.state.value.draft)
        assertNull(store.state.value.serverEditorial)
        store.edit(emptyList(), emptyList())
        store.discardDraft()
        store.save()
        assertEquals(1, api.saves.size)
        assertEquals(MemoryBookEditorialStoreStatus.ACCESS_REVOKED, store.state.value.status)
    }

    @Test fun cancelledLoadResetsPendingWithoutInventingSuccess() = runTest {
        val api = Api(bookId, storyId).apply { getGate = CompletableDeferred() }
        val store = newStore(api)
        store.setContext(context())
        val loading = async { store.load() }
        runCurrent()
        loading.cancelAndJoin()
        assertEquals(MemoryBookEditorialStoreStatus.NO_CONTEXT, store.state.value.status)
        api.getGate = null
        store.load()
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
        assertEquals(2, api.gets.size)
    }

    @Test fun cancelledSaveRetainsUncertainFrozenRequestForExplicitRetry() = runTest {
        val api = Api(bookId, storyId).apply { saveGate = CompletableDeferred() }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        val saving = async { store.save() }
        runCurrent()
        val originalBody = api.saves.single().third
        saving.cancelAndJoin()
        assertEquals(MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        api.saveGate = null
        store.retryUncertainSave()
        assertEquals(originalBody, api.saves.last().third)
        assertEquals(2, api.saves.size)
    }

    @Test fun cancelledReloadKeepsEditsMadeWhileReading() = runTest {
        val api = Api(bookId, storyId)
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        api.getGate = CompletableDeferred()
        val loading = async { store.load() }
        runCurrent()
        store.edit(emptyList(), emptyList())
        loading.cancelAndJoin()
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
        assertTrue(store.state.value.dirty)
        assertTrue(store.state.value.draft!!.introductionSourceRefs.isEmpty())
    }

    @Test fun optionalSaveUnavailableRetainsTheExactUncertainRequest() = runTest {
        val api = Api(bookId, storyId).apply { saveError = ApiFailure(FailureKind.HTTP, 503) }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.save()
        val payload = api.saves.single().third
        assertEquals(MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN, store.state.value.status)
        store.edit(emptyList(), emptyList())
        store.save()
        assertEquals(1, api.saves.size)
        api.saveError = null
        store.retryUncertainSave()
        assertEquals(payload, api.saves.last().third)
        assertTrue(store.state.value.dirty)
        assertTrue(store.state.value.draft!!.introductionSourceRefs.isEmpty())
    }

    @Test fun discardingConflictDoesNotRestoreAStaleServerBasis() = runTest {
        val api = Api(bookId, storyId).apply { saveError = ApiFailure(FailureKind.HTTP, 409) }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.save()
        assertNull(store.state.value.serverEditorial)
        store.discardDraft()
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        store.save()
        assertEquals(1, api.saves.size)
    }

    @Test fun explicitlyReviewedDraftCanContinueAfterDirtyReadConflict() = runTest {
        val api = Api(bookId, storyId)
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.load()
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        assertTrue(store.applyReviewedDraft(listOf(source), emptyList()))
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
        assertTrue(store.state.value.dirty)
        assertTrue(api.saves.isEmpty())
        store.save()
        assertEquals(1, api.saves.size)
    }

    @Test fun reviewedDraftCannotCarryForeignSourcesOrUseStaleConflictSnapshot() = runTest {
        val api = Api(bookId, storyId)
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.load()
        val foreign = source.copy(contributionId = "44444444-4444-4444-4444-444444444444")
        assertFalse(store.applyReviewedDraft(listOf(foreign), emptyList()))
        assertEquals(listOf(source), store.state.value.draft!!.introductionSourceRefs)
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        store.discardDraft()
        store.edit(listOf(source), emptyList())
        api.saveError = ApiFailure(FailureKind.HTTP, 409)
        store.save()
        assertFalse(store.applyReviewedDraft(listOf(source), emptyList()))
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        assertEquals(1, api.saves.size)
    }

    @Test fun reviewedDraftRejectsMalformedUnicodeWithoutDroppingRetainedText() = runTest {
        val right = EditorialChild("22222222-2222-2222-2222-222222222222", "3")
        val children = listOf(child, right)
        val api = Api(bookId, storyId).apply { getResponse = response("4", "empty", children) }
        val store = newStore(api)
        store.setContext(context(children = children))
        store.load()
        val transition = EditorialTransition(child.storyId, right.storyId, "retained text", listOf(source))
        store.edit(emptyList(), listOf(transition))
        store.load()
        assertFalse(store.applyReviewedDraft(emptyList(), listOf(transition.copy(text = "\uD800"))))
        assertEquals("retained text", store.state.value.draft!!.transitions.single().text)
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        assertTrue(api.saves.isEmpty())
    }

    @Test fun contextSwitchRejectsLateSaveAndClearsOldDraft() = runTest {
        val api = Api(bookId, storyId).apply { saveGate = CompletableDeferred() }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        val saving = async { store.save() }
        runCurrent()
        store.setContext(context(session = "session-2"))
        assertNull(store.state.value.draft)
        api.saveGate!!.complete(Unit)
        saving.await()
        assertEquals(MemoryBookEditorialStoreStatus.NO_CONTEXT, store.state.value.status)
        assertEquals("session-2", context(session = "session-2").sessionId)
    }

    @Test fun contextSnapshotAndDraftDefensivelyCopyCollections() = runTest {
        val api = Api(bookId, storyId)
        val store = newStore(api)
        val children = mutableListOf(child)
        val sources = mutableSetOf(source)
        store.setContext(context(children = children, sources = sources))
        children.clear(); sources.clear()
        store.load()
        val refs = mutableListOf(source)
        val transitions = mutableListOf<EditorialTransition>()
        store.edit(refs, transitions)
        refs.clear(); transitions += EditorialTransition(storyId, storyId, "x", listOf(source))
        assertEquals(listOf(source), store.state.value.draft?.introductionSourceRefs)
        assertTrue(store.state.value.draft?.transitions!!.isEmpty())
        assertEquals(1, api.gets.size)
    }

    @Test fun editDuringSaveSurvivesAcknowledgement() = runTest {
        val api = Api(bookId, storyId).apply { saveGate = CompletableDeferred() }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        val saving = async { store.save() }
        runCurrent()
        store.edit(emptyList(), emptyList())
        api.saveGate!!.complete(Unit)
        saving.await()
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
        assertTrue(store.state.value.dirty)
        assertTrue(store.state.value.draft!!.introductionSourceRefs.isEmpty())
        assertEquals("5", store.state.value.revision)
    }

    @Test fun conflictKeepsDraftAndDoesNotOfferUncertainRetry() = runTest {
        val api = Api(bookId, storyId).apply { saveError = ApiFailure(FailureKind.HTTP, 409) }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.save()
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        assertEquals(listOf(source), store.state.value.draft!!.introductionSourceRefs)
        store.retryUncertainSave()
        assertEquals(1, api.saves.size)
    }

    @Test fun sourceChangedSaveResponseKeepsDraftAndReportsConflict() = runTest {
        val api = Api(bookId, storyId).apply {
            saveResponse = """{"version":1,"id":"$bookId","revision":"5","children":[{"story_id":"$storyId","revision":"2"}],"state":"source_changed","introduction_source_refs":[],"transitions":[]}""".toByteArray()
        }
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.save()
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        assertEquals(listOf(source), store.state.value.draft!!.introductionSourceRefs)
        assertTrue(store.state.value.dirty)
        assertNull(store.state.value.serverEditorial)
        store.discardDraft()
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        assertNull(store.state.value.draft)
        store.load()
        assertEquals(1, api.gets.size)

        api.getResponse = response("5", "source_changed")
        store.setContext(context(revision = "5", sources = emptySet()))
        store.load()
        assertEquals(2, api.gets.size)
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        assertEquals(EditorialState.SOURCE_CHANGED, store.state.value.serverEditorial?.state)
        store.acceptCurrentServerBasis()
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
        assertTrue(store.state.value.dirty)
    }

    @Test fun emptyTwoChildResponseCreatesBlankAdjacentTransition() = runTest {
        val children = listOf(child, EditorialChild(secondStoryId, "3"))
        val api = Api(bookId, storyId).apply { getResponse = response("4", "empty", children) }
        val store = newStore(api)
        store.setContext(context(children = children))
        store.load()
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
        assertEquals(listOf(EditorialTransition(storyId, secondStoryId, "", emptyList())), store.state.value.draft!!.transitions)
    }

    @Test fun sourceChangedTwoChildResponseRequiresExplicitReview() = runTest {
        val children = listOf(child, EditorialChild(secondStoryId, "3"))
        val api = Api(bookId, storyId).apply { getResponse = response("4", "source_changed", children) }
        val store = newStore(api)
        store.setContext(context(children = children))
        store.load()
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        assertEquals(listOf(EditorialTransition(storyId, secondStoryId, "", emptyList())), store.state.value.draft!!.transitions)
        store.acceptCurrentServerBasis()
        assertEquals(MemoryBookEditorialStoreStatus.READY, store.state.value.status)
        assertTrue(store.state.value.dirty)
    }

    @Test fun sourceEligibilityChangePreservesDraftAsConflictAndPreventsOldSave() = runTest {
        val api = Api(bookId, storyId)
        val store = newStore(api)
        loaded(store)
        store.edit(listOf(source), emptyList())
        store.setContext(context(revision = "5", sources = emptySet()))
        assertEquals(MemoryBookEditorialStoreStatus.CONFLICT, store.state.value.status)
        assertEquals(listOf(source), store.state.value.draft!!.introductionSourceRefs)
        store.save()
        assertTrue(api.saves.isEmpty())
    }

    @Test fun optionalEndpointAndAuthorizationFailuresHaveDistinctStates() = runTest {
        val absentApi = Api(bookId, storyId).apply { getError = ApiFailure(FailureKind.HTTP, 404) }
        val absent = newStore(absentApi)
        absent.setContext(context())
        absent.load()
        assertEquals(MemoryBookEditorialStoreStatus.UNAVAILABLE, absent.state.value.status)

        val deniedApi = Api(bookId, storyId).apply { getError = ApiFailure(FailureKind.HTTP, 403) }
        val denied = newStore(deniedApi)
        denied.setContext(context())
        denied.load()
        assertEquals(MemoryBookEditorialStoreStatus.ACCESS_REVOKED, denied.state.value.status)
    }

    @Test fun loadStartedBeforeClearCannotRestoreState() = runTest {
        val api = Api(bookId, storyId).apply { getGate = CompletableDeferred() }
        val store = newStore(api)
        store.setContext(context())
        val loading = async { store.load() }
        runCurrent()
        store.clear()
        api.getGate!!.complete(Unit)
        loading.await()
        assertEquals(MemoryBookEditorialStoreStatus.NO_CONTEXT, store.state.value.status)
        assertNull(store.state.value.serverEditorial)
    }
}
