package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AssistantWorkspaceStoreTest {
    private val token = Bearer.from(SessionToken(86400, "A".repeat(43), "Bearer"))
    private fun scope(account: String = "account-a", library: String = "family-a", generation: Long = 1) =
        AssistantWorkspaceScope(account, token, library, generation, true)

    private val capabilities = AssistantWorkspaceCapabilities(
        version = 1, available = true, threads = true, preferences = true,
        preferencesApplied = true, serverOwnedTurns = true, appliedPreferences = setOf("locale"),
    )
    private fun thread(id: String = uuid(1), revision: Long = 0) = AssistantWorkspaceThreadSummary(
        id, "family-a", "2026-10-13T00:00:00Z", "2026-10-13T00:00:00Z", "2026-11-12T00:00:00Z", revision,
    )
    private fun detail(id: String = uuid(1), revision: Long = 0, latest: String? = null) =
        AssistantWorkspaceThreadDetail(1, thread(id, revision), emptyList(), latest)
    private fun uuid(n: Int) = "00000000-0000-4000-8000-${n.toString().padStart(12, '0')}"
    private fun completed(id: String, requestId: String, revision: Long, recovered: Boolean,
                         kind: String = "results", effect: AssistantEffect? = null) = AssistantWorkspaceTurn(
        1, id, requestId, AssistantWorkspaceRequestStatus.COMPLETED, revision, recovered, null,
        AssistantTurn(kind, "found", null, null, emptyList(), 0, false,
            effect ?: if (recovered) null else AssistantEffect("open", "asset-1")),
    )

    private inner class FakeApi : AssistantWorkspaceApi {
        override val assistantWorkspaceEnabled = true
        var capabilitiesCalls = 0
        var listCalls = 0
        var createCalls = 0
        var submitCalls = 0
        var getCalls = 0
        var readCalls = 0
        var deleteExpectedRevision: Long? = null
        var prefsUpdates: Map<AssistantWorkspacePreference, String?>? = null
        var listHandler: suspend () -> AssistantWorkspaceThreadList = { AssistantWorkspaceThreadList(1, emptyList()) }
        var createHandler: suspend (String) -> AssistantWorkspaceCreatedThread = { id -> AssistantWorkspaceCreatedThread(1, thread(id)) }
        var submitHandler: suspend (String, Long, String) -> AssistantWorkspaceTurn = { id, _, _ -> completed(id, uuid(9), 1, false) }
        var getHandler: suspend (String, String) -> AssistantWorkspaceTurn = { id, request ->
            AssistantWorkspaceTurn(1, id, request, AssistantWorkspaceRequestStatus.PENDING, 0, true, null, null)
        }
        var readHandler: suspend (String) -> AssistantWorkspaceThreadDetail = { detail(it) }
        var deleteHandler: suspend (String, Long) -> AssistantWorkspaceDeletedThread = { id, _ -> AssistantWorkspaceDeletedThread(id, true) }
        var preferencesValue = AssistantWorkspacePreferences(1, "zh", "standard", "normal", 0)

        override suspend fun capabilities(token: Bearer, library: String): AssistantWorkspaceCapabilities {
            capabilitiesCalls++; return capabilities
        }
        override suspend fun listThreads(token: Bearer, library: String): AssistantWorkspaceThreadList {
            listCalls++; return listHandler()
        }
        override suspend fun createThread(token: Bearer, library: String, clientThreadId: String): AssistantWorkspaceCreatedThread {
            createCalls++; return createHandler(clientThreadId)
        }
        override suspend fun readThread(token: Bearer, library: String, threadId: String): AssistantWorkspaceThreadDetail {
            readCalls++; return readHandler(threadId)
        }
        override suspend fun deleteThread(token: Bearer, library: String, threadId: String, expectedRevision: Long): AssistantWorkspaceDeletedThread {
            deleteExpectedRevision = expectedRevision; return deleteHandler(threadId, expectedRevision)
        }
        override suspend fun preferences(token: Bearer, library: String): AssistantWorkspacePreferences = preferencesValue
        override suspend fun updatePreferences(token: Bearer, library: String, expectedRevision: Long,
                                               updates: Map<AssistantWorkspacePreference, String?>): AssistantWorkspacePreferences {
            prefsUpdates = updates; return preferencesValue.copy(locale = updates[AssistantWorkspacePreference.LOCALE] ?: preferencesValue.locale,
                revision = expectedRevision + 1)
        }
        override suspend fun resetPreferences(token: Bearer, library: String, expectedRevision: Long): AssistantWorkspacePreferences =
            preferencesValue.copy(locale = null, revision = expectedRevision + 1)
        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                        expectedRevision: Long, text: String): AssistantWorkspaceTurn {
            submitCalls++; return submitHandler(threadId, expectedRevision, text)
        }
        override suspend fun getTurn(token: Bearer, library: String, threadId: String, requestId: String): AssistantWorkspaceTurn {
            getCalls++; return getHandler(threadId, requestId)
        }
    }

    @Test fun lostPostUsesGetOnlyAndRevisionConflictKeepsDraftAndSuppressesRecoveredEffect() = runTest {
        val api = FakeApi()
        var current = scope()
        val requestId = uuid(9)
        api.submitHandler = { _, _, _ -> throw ApiFailure(FailureKind.OFFLINE) }
        api.getHandler = { id, request -> completed(id, request, 1, true) }
        api.readHandler = { detail(it, revision = 2) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { current }, uuidFactory = { requestId })
        store.onScopeChanged()
        store.refreshCapabilities(); runCurrent()
        store.openThread(uuid(1)); runCurrent()
        store.setDraft("find the red kite")
        store.sendTurn(); runCurrent()

        assertEquals(1, api.submitCalls)
        assertEquals(1, api.getCalls)
        assertEquals("find the red kite", store.state.value.draft)
        assertFalse(store.state.value.continuationEnabled)
        assertEquals(AssistantWorkspaceError.CONTEXT_CHANGED, store.state.value.error)
        assertNull(store.state.value.currentTurn?.result?.effect)
        assertNull(store.state.value.pendingTurn)
    }

    @Test fun scopeChangeCancelsRequestAndClearsAllPrivateBuffers() = runTest {
        val api = FakeApi()
        val response = CompletableDeferred<AssistantWorkspaceThreadList>()
        api.listHandler = { response.await() }
        var current: AssistantWorkspaceScope? = scope()
        val store = AssistantWorkspaceStore(api, backgroundScope, { current })
        store.onScopeChanged()
        store.refreshCapabilities(); runCurrent()
        store.setDraft("private words")
        store.refreshThreads(); runCurrent()
        current = scope(account = "account-b", generation = 2)
        store.onScopeChanged()
        response.complete(AssistantWorkspaceThreadList(1, listOf(thread())))
        runCurrent()

        assertEquals("account-b", store.state.value.accountId)
        assertNull(store.state.value.threads)
        assertNull(store.state.value.capabilities)
        assertEquals("", store.state.value.draft)
        assertFalse(store.state.value.busy)
    }

    @Test fun failedRecoveryClearsBlockerAndPreservesDraftForExplicitNewTurn() = runTest {
        val api = FakeApi()
        val requestId = uuid(9)
        api.submitHandler = { _, _, _ -> throw ApiFailure(FailureKind.OFFLINE) }
        api.getHandler = { id, request -> AssistantWorkspaceTurn(
            1, id, request, AssistantWorkspaceRequestStatus.FAILED, 0, true, "assistant_unavailable", null,
        ) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() }, uuidFactory = { requestId })
        store.onScopeChanged(); store.refreshCapabilities(); runCurrent()
        store.openThread(uuid(1)); runCurrent()
        store.setDraft("keep this editable")
        store.sendTurn(); runCurrent()

        assertNull(store.state.value.pendingTurn)
        assertFalse(store.state.value.uncertain)
        assertEquals("keep this editable", store.state.value.draft)
        assertEquals(AssistantWorkspaceError.TURN_FAILED, store.state.value.error)
    }

    @Test fun uncertainThreadCreationReconcilesByOwnedIdAndNeverPostsAnotherId() = runTest {
        val api = FakeApi()
        api.createHandler = { throw ApiFailure(FailureKind.OFFLINE) }
        api.readHandler = { detail(it) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() }, uuidFactory = { uuid(2) })
        store.onScopeChanged(); store.refreshCapabilities(); runCurrent()
        store.createThread(); runCurrent()

        assertEquals(1, api.createCalls)
        assertEquals(0, api.listCalls)
        assertEquals(1, api.readCalls)
        assertNull(store.state.value.pendingCreationId)
        assertEquals(uuid(2), store.state.value.detail?.thread?.threadId)
    }

    @Test fun deleteUsesCurrentRevisionCasAndClearsOnlyTheDeletedCurrentThread() = runTest {
        val api = FakeApi()
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.onScopeChanged(); store.refreshCapabilities(); runCurrent()
        api.readHandler = { detail(it, revision = 7) }
        store.openThread(uuid(1)); runCurrent()
        store.deleteCurrentThread(); runCurrent()

        assertEquals(7L, api.deleteExpectedRevision)
        assertNull(store.state.value.detail)
        assertEquals("", store.state.value.draft)
    }

    @Test fun localeIsAppliedAndUnsupportedStoredPreferencesRemainVisible() = runTest {
        val api = FakeApi()
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.onScopeChanged(); store.refreshCapabilities(); runCurrent()
        store.refreshPreferences(); runCurrent()
        store.updatePreferences(mapOf(AssistantWorkspacePreference.LOCALE to "en")); runCurrent()

        assertEquals("en", store.state.value.preferences?.locale)
        assertEquals(setOf(AssistantWorkspacePreference.REPLY_LENGTH, AssistantWorkspacePreference.VOICE_PACE),
            store.state.value.unsupportedPreferences)
        assertEquals(mapOf(AssistantWorkspacePreference.LOCALE to "en"), api.prefsUpdates)
    }

    @Test fun eachExplicitReopenGetsTheLatestRequestAgain() = runTest {
        val api = FakeApi()
        val requestId = uuid(8)
        api.readHandler = { detail(it, revision = 1, latest = requestId) }
        api.getHandler = { id, request -> completed(id, request, 1, recovered = true) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.onScopeChanged(); store.refreshCapabilities(); runCurrent()

        store.openThread(uuid(1)); runCurrent()
        assertEquals(1, api.getCalls)
        assertNull(store.state.value.currentTurn?.result?.effect)
        store.openThread(uuid(1)); runCurrent()

        assertEquals(2, api.getCalls)
        assertEquals(1L, store.state.value.currentTurn?.revision)
        assertTrue(store.state.value.continuationEnabled)
    }

    @Test fun creationChecksExactIdAndPreservesTypedDraftAcrossReconciliation() = runTest {
        val api = FakeApi()
        api.createHandler = { throw ApiFailure(FailureKind.OFFLINE) }
        api.readHandler = { throw ApiFailure(FailureKind.HTTP, 404) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() }, uuidFactory = { uuid(2) })
        store.refreshCapabilities(); runCurrent(); store.setDraft("keep my question")
        store.createThread(); runCurrent()
        assertEquals(uuid(2), store.state.value.pendingCreationId)
        assertEquals("keep my question", store.state.value.draft)
        api.readHandler = { detail(it) }
        store.reconcileCreation(); runCurrent()
        assertEquals(1, api.createCalls)
        assertEquals(2, api.readCalls)
        assertEquals(0, api.listCalls)
        assertEquals("keep my question", store.state.value.draft)
        assertNull(store.state.value.pendingCreationId)
    }

    @Test fun deniedRequestClearsPrivateHistoryDraftAndContextWithoutRetrying() = runTest {
        val api = FakeApi()
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.refreshCapabilities(); runCurrent(); store.openThread(uuid(1)); runCurrent()
        store.setDraft("private text")
        api.submitHandler = { _, _, _ -> throw ApiFailure(FailureKind.HTTP, 401) }
        store.sendTurn(); runCurrent()
        assertEquals(1, api.submitCalls)
        assertEquals(0, api.getCalls)
        assertEquals("", store.state.value.draft)
        assertNull(store.state.value.detail)
        assertNull(store.state.value.currentTurn)
        assertNull(store.state.value.pendingTurn)
        assertEquals(AssistantWorkspaceError.ACCESS_DENIED, store.state.value.error)
    }

    @Test fun recoveredTurnsWithEffectsOrOpenKindAreRejectedAndRemainUncertain() = runTest {
        for ((kind, effect) in listOf("results" to AssistantEffect("open", "asset-1"), "open" to null)) {
            val api = FakeApi()
            val requestId = uuid(8)
            api.readHandler = { detail(it, revision = 1, latest = requestId) }
            api.getHandler = { id, request -> completed(id, request, 1, recovered = true, kind = kind, effect = effect) }
            val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
            store.onScopeChanged(); store.refreshCapabilities(); runCurrent()
            store.openThread(uuid(1)); runCurrent()

            assertEquals(AssistantWorkspaceError.INVALID_RESPONSE, store.state.value.error)
            assertTrue(store.state.value.uncertain)
            assertNotNull(store.state.value.pendingTurn)
            assertNull(store.state.value.currentTurn)
        }
    }
}
