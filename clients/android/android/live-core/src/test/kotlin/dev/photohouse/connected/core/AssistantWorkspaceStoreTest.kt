package dev.photohouse.connected.core

import dev.photohouse.protocol.SessionToken
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
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
    private fun exchange(revision: Long, exchangeId: String = uuid((revision + 100).toInt())) = AssistantWorkspaceExchange(
        exchangeId, revision, "2026-10-13T00:00:00Z", "2026-11-12T00:00:00Z",
        "Question $revision", "Answer $revision", emptyList(), 0, uuid((revision + 200).toInt()),
    )
    private fun thread(id: String = uuid(1), revision: Long = 0) = AssistantWorkspaceThreadSummary(
        id, "family-a", "2026-10-13T00:00:00Z", "2026-10-13T00:00:00Z", "2026-11-12T00:00:00Z", revision,
    )
    private fun detail(id: String = uuid(1), revision: Long = 0, latest: String? = null,
                       exchanges: List<AssistantWorkspaceExchange> = emptyList(), hasOlder: Boolean = false) =
        AssistantWorkspaceThreadDetail(1, thread(id, revision), exchanges, latest, hasOlder)
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
        var submittedRequestId: String? = null
        var submittedParentRequestId: String? = null
        var submittedText: String? = null
        var getCalls = 0
        var readCalls = 0
        var deleteExpectedRevision: Long? = null
        var prefsUpdates: Map<AssistantWorkspacePreference, String?>? = null
        var capabilityValue = capabilities
        var listIncludedLabels: Boolean? = null
        var historyCalls = 0
        var savedMemoryReaderAvailable = false
        var savedMemoryCardsAvailable = false
        var readerCalls = 0
        var acceptSavedMemoryCardsSent = false
        var readerHandler: suspend () -> SavedMemoryReaderPayload = { error("reader not configured") }
        val historyRequests = mutableListOf<Triple<String, Long, Long>>()
        var listHandler: suspend () -> AssistantWorkspaceThreadList = { AssistantWorkspaceThreadList(1, emptyList()) }
        var createHandler: suspend (String) -> AssistantWorkspaceCreatedThread = { id -> AssistantWorkspaceCreatedThread(1, thread(id)) }
        var submitHandler: suspend (String, Long, String) -> AssistantWorkspaceTurn = { id, _, _ -> completed(id, uuid(9), 1, false) }
        var getHandler: suspend (String, String) -> AssistantWorkspaceTurn = { id, request ->
            AssistantWorkspaceTurn(1, id, request, AssistantWorkspaceRequestStatus.PENDING, 0, true, null, null)
        }
        var readHandler: suspend (String) -> AssistantWorkspaceThreadDetail = { detail(it) }
        var historyHandler: suspend (String, Long, Long) -> AssistantWorkspaceHistoryPage = { id, before, snapshot ->
            AssistantWorkspaceHistoryPage(1, id, snapshot, before, emptyList(), false, null)
        }
        var deleteHandler: suspend (String, Long) -> AssistantWorkspaceDeletedThread = { id, _ -> AssistantWorkspaceDeletedThread(id, true) }
        var preferencesValue = AssistantWorkspacePreferences(1, "zh", "standard", "normal", 0)

        override suspend fun capabilities(token: Bearer, library: String): AssistantWorkspaceCapabilities {
            capabilitiesCalls++; return capabilityValue
        }
        override suspend fun savedMemoryReaderCapabilities(token: Bearer, library: String) =
            SavedMemoryReaderCapabilities(1, savedMemoryReaderAvailable)
        override suspend fun savedMemoryCardsCapabilities(token: Bearer, library: String) =
            SavedMemoryReaderCapabilities(1, savedMemoryCardsAvailable)
        override suspend fun savedMemoryReader(token: Bearer, library: String, threadId: String, turnId: String,
                                               ordinal: Int, expectedRevision: Long): SavedMemoryReaderPayload {
            readerCalls++; return readerHandler()
        }
        override suspend fun listThreads(token: Bearer, library: String): AssistantWorkspaceThreadList {
            listCalls++; return listHandler()
        }
        override suspend fun listThreads(token: Bearer, library: String, includeLabels: Boolean): AssistantWorkspaceThreadList {
            listCalls++; listIncludedLabels = includeLabels; return listHandler()
        }
        override suspend fun readHistory(token: Bearer, library: String, threadId: String,
                                         beforeRevision: Long, snapshotRevision: Long): AssistantWorkspaceHistoryPage {
            historyCalls++
            historyRequests += Triple(threadId, beforeRevision, snapshotRevision)
            return historyHandler(threadId, beforeRevision, snapshotRevision)
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
            submitCalls++; submittedRequestId = requestId; return submitHandler(threadId, expectedRevision, text)
        }
        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                        expectedRevision: Long, text: String, parentRequestId: String?): AssistantWorkspaceTurn {
            submitCalls++
            submittedRequestId = requestId
            submittedParentRequestId = parentRequestId
            submittedText = text
            return submitHandler(threadId, expectedRevision, text)
        }
        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                        expectedRevision: Long, text: String, parentRequestId: String?,
                                        acceptSavedMemoryCards: Boolean): AssistantWorkspaceTurn {
            acceptSavedMemoryCardsSent = acceptSavedMemoryCards
            return submitTurn(token, library, threadId, requestId, expectedRevision, text, parentRequestId)
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

    @Test fun sendReservesSuppliedIdentitySynchronouslyAndForwardsParentRequestId() = runTest {
        val api = FakeApi()
        val response = CompletableDeferred<AssistantWorkspaceTurn>()
        api.submitHandler = { id, _, _ -> response.await().copy(threadId = id) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.refreshCapabilities(); runCurrent(); store.openThread(uuid(1)); runCurrent()
        store.setDraft("voice transcript")

        assertTrue(store.sendTurn(uuid(7), uuid(6)))
        val reserved = store.state.value.pendingTurn
        assertEquals(uuid(7), reserved?.requestId)
        assertEquals(uuid(6), reserved?.parentRequestId)
        assertEquals("voice transcript", reserved?.text)
        assertEquals(0, api.submitCalls)
        assertFalse(store.sendTurn(uuid(5)))
        store.setDraft("later edit")
        assertEquals("voice transcript", store.state.value.pendingTurn?.text)
        runCurrent()

        assertEquals(uuid(7), api.submittedRequestId)
        assertEquals(uuid(6), api.submittedParentRequestId)
        assertEquals("voice transcript", api.submittedText)
        assertEquals("later edit", store.state.value.draft)
        response.complete(AssistantWorkspaceTurn(1, uuid(1), uuid(7), AssistantWorkspaceRequestStatus.PENDING,
            0, false, null, null))
        runCurrent()
    }

    @Test fun cancelWaitingRetainsPendingIdentityAndDraftAndLateCompletionIsInertUntilGetRecovery() = runTest {
        val api = FakeApi()
        val response = CompletableDeferred<AssistantWorkspaceTurn>()
        api.submitHandler = { id, _, _ -> withContext(NonCancellable) { response.await().copy(threadId = id) } }
        api.getHandler = { id, request -> AssistantWorkspaceTurn(
            1, id, request, AssistantWorkspaceRequestStatus.PENDING, 0, true, null, null,
        ) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.refreshCapabilities(); runCurrent(); store.openThread(uuid(1)); runCurrent()
        store.setDraft("hold this text")
        assertTrue(store.sendTurn(uuid(7)))
        val reserved = store.state.value.pendingTurn
        runCurrent()
        assertTrue(store.state.value.busy)

        assertTrue(store.cancelWaitingForTurn(uuid(7)))
        assertFalse(store.state.value.busy)
        assertTrue(store.state.value.uncertain)
        assertEquals(reserved, store.state.value.pendingTurn)
        assertEquals("hold this text", store.state.value.draft)
        response.complete(completed(uuid(1), uuid(7), 1, recovered = false))
        runCurrent()

        assertEquals(1, api.submitCalls)
        assertEquals(0, api.getCalls)
        assertEquals(reserved, store.state.value.pendingTurn)
        assertNull(store.state.value.currentTurn)
        assertEquals("hold this text", store.state.value.draft)

        assertTrue(store.recoverPendingTurn())
        runCurrent()
        assertEquals(1, api.submitCalls)
        assertEquals(1, api.getCalls)
        assertEquals(reserved, store.state.value.pendingTurn)
        assertTrue(store.state.value.uncertain)
    }

    @Test fun invalidSendDoesNotReserveOrStartNetworkWork() = runTest {
        val api = FakeApi()
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.refreshCapabilities(); runCurrent(); store.openThread(uuid(1)); runCurrent()
        store.setDraft("x".repeat(1025))

        assertFalse(store.sendTurn(uuid(7), uuid(6)))
        assertNull(store.state.value.pendingTurn)
        assertFalse(store.state.value.busy)
        assertEquals(0, api.submitCalls)
    }

    @Test fun cardCapabilityIsIndependentFromOptionalReaderCapability() = runTest {
        val api = FakeApi().apply { savedMemoryCardsAvailable = true; savedMemoryReaderAvailable = false }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.refreshCapabilities(); runCurrent()
        store.refreshSavedMemoryCardsCapabilities(); runCurrent()
        store.refreshSavedMemoryReaderCapabilities(); runCurrent()

        assertTrue(store.state.value.savedMemoryCardsAvailable)
        assertFalse(store.state.value.savedMemoryReaderAvailable)
    }

    @Test fun readerHandoffMustStillBeCurrentAndCanOnlyBeConsumedOnce() = runTest {
        val api = FakeApi().apply { savedMemoryReaderAvailable = true; savedMemoryCardsAvailable = true }
        var completionRevision = 0L
        val card = AssistantSavedMemoryCard("memoir", uuid(11), "2", "e".repeat(64), "Family year", "A short excerpt.")
        api.submitHandler = { threadId, _, requestId -> completionRevision++
            AssistantWorkspaceTurn(1, threadId, requestId,
            AssistantWorkspaceRequestStatus.COMPLETED, completionRevision, false, null,
            AssistantTurn("memory_cards", "Found a memory.", null, null, emptyList(), 1, false, null,
                memoryCards = listOf(card), savedMemoryContext = AssistantSavedMemoryContext("family-a", "f".repeat(64),
                    listOf(AssistantSavedMemoryReference(card.kind, card.id, card.revision, card.sourceRevision))))) }
        api.readHandler = { detail(it, revision = completionRevision) }
        api.readerHandler = { SavedMemoryReaderPayload.Memoir(MemoryBook(card.id, 2, false, card.title, "", "en",
            listOf(MemoryBookStorySummary(uuid(12), "Chapter", 3, 1, "1")))) }
        var nextRequestId = 9
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() }, uuidFactory = { uuid(nextRequestId++) })
        store.refreshCapabilities(); runCurrent()
        store.refreshSavedMemoryCardsCapabilities(); runCurrent()
        store.refreshSavedMemoryReaderCapabilities(); runCurrent()
        store.openThread(uuid(1)); runCurrent()
        store.setDraft("Find a saved memoir")
        store.sendTurn(); runCurrent()
        assertTrue(store.openSavedMemoryCard(0)); runCurrent()
        val handoff = store.state.value.memoryReaderHandoff
        assertNotNull(handoff)
        assertTrue(store.consumeMemoryReaderHandoff(handoff!!))
        assertFalse(store.consumeMemoryReaderHandoff(handoff))

        store.setDraft("Find another memoir")
        store.sendTurn(); runCurrent()
        assertEquals(2L, store.state.value.currentTurn?.revision)
        assertFalse(store.consumeMemoryReaderHandoff(handoff))
    }

    @Test fun freshMemoryReaderHandoffIsNegotiatedAndLateScopeResultsAreDropped() = runTest {
        val api = FakeApi().apply { savedMemoryReaderAvailable = true; savedMemoryCardsAvailable = true }
        var current: AssistantWorkspaceScope? = scope()
        val card = AssistantSavedMemoryCard("memoir", uuid(11), "2", "b".repeat(64), "Family year", "A short excerpt.")
        api.submitHandler = { id, _, _ -> AssistantWorkspaceTurn(1, id, uuid(9),
            AssistantWorkspaceRequestStatus.COMPLETED, 1, false, null,
            AssistantTurn("memory_cards", "Found a memory.", null, null, emptyList(), 1, false, null,
                memoryCards = listOf(card), savedMemoryContext = AssistantSavedMemoryContext("family-a", "a".repeat(64),
                    listOf(AssistantSavedMemoryReference(card.kind, card.id, card.revision, card.sourceRevision))))) }
        api.readHandler = { detail(it, revision = 1) }
        val payload = SavedMemoryReaderPayload.Memoir(MemoryBook(card.id, 2, false, card.title, "", "en",
            listOf(MemoryBookStorySummary(uuid(12), "Chapter", 3, 1, "1"))))
        val response = CompletableDeferred<SavedMemoryReaderPayload>()
        api.readerHandler = { withContext(NonCancellable) { response.await() } }
        val store = AssistantWorkspaceStore(api, backgroundScope, { current }, uuidFactory = { uuid(9) })
        store.refreshCapabilities(); runCurrent()
        store.refreshSavedMemoryCardsCapabilities(); runCurrent()
        store.refreshSavedMemoryReaderCapabilities(); runCurrent()
        store.openThread(uuid(1)); runCurrent()
        store.setDraft("Find a saved memoir")
        store.sendTurn(); runCurrent()
        assertTrue(api.acceptSavedMemoryCardsSent)
        assertEquals("memory_cards", store.state.value.currentTurn?.result?.kind)
        store.setDraft("Unsent follow-up")

        assertTrue(store.openSavedMemoryCard(0))
        runCurrent()
        assertEquals(1, api.readerCalls)
        assertEquals(0, store.state.value.memoryReaderOrdinal)
        assertEquals("Unsent follow-up", store.state.value.draft)

        current = scope(generation = 2)
        store.onScopeChanged()
        response.complete(payload)
        runCurrent()
        assertNull(store.state.value.memoryReaderHandoff)
        assertNull(store.state.value.currentTurn)
        assertEquals("", store.state.value.draft)
    }

    @Test fun staleReaderFailureKeepsDraftAndDoesNotResubmitTheTurn() = runTest {
        val api = FakeApi().apply { savedMemoryReaderAvailable = true; savedMemoryCardsAvailable = true }
        val card = AssistantSavedMemoryCard("story", uuid(11), "2", "c".repeat(64), "Garden", "A family walk.")
        api.submitHandler = { id, _, _ -> AssistantWorkspaceTurn(1, id, uuid(9),
            AssistantWorkspaceRequestStatus.COMPLETED, 1, false, null,
            AssistantTurn("memory_cards", "Found a memory.", null, null, emptyList(), 1, false, null,
                memoryCards = listOf(card), savedMemoryContext = AssistantSavedMemoryContext("family-a", "d".repeat(64),
                    listOf(AssistantSavedMemoryReference(card.kind, card.id, card.revision, card.sourceRevision))))) }
        api.readHandler = { detail(it, revision = 1) }
        api.readerHandler = { throw ApiFailure(FailureKind.HTTP, 409) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() }, uuidFactory = { uuid(9) })
        store.refreshCapabilities(); runCurrent()
        store.refreshSavedMemoryCardsCapabilities(); runCurrent()
        store.refreshSavedMemoryReaderCapabilities(); runCurrent()
        store.openThread(uuid(1)); runCurrent()
        store.setDraft("Find a saved story")
        store.sendTurn(); runCurrent()
        store.setDraft("Keep this follow-up")

        assertTrue(store.openSavedMemoryCard(0))
        runCurrent()
        assertEquals(1, api.submitCalls)
        assertEquals(1, api.readerCalls)
        assertEquals("Keep this follow-up", store.state.value.draft)
        assertEquals(AssistantWorkspaceError.CONTEXT_CHANGED, store.state.value.memoryReaderError)
        assertEquals(0, store.state.value.memoryReaderErrorOrdinal)
        assertNull(store.state.value.memoryReaderHandoff)
    }

    @Test fun olderHistoryLoadsTwoPagesWithoutChangingCurrentTurnDraftOrContext() = runTest {
        val api = FakeApi()
        val recent = (36L..55L).map(::exchange)
        api.historyHandler = { id, before, snapshot ->
            when (before) {
                36L -> AssistantWorkspaceHistoryPage(1, id, snapshot, before,
                    (16L..35L).map(::exchange), true, 16L)
                16L -> AssistantWorkspaceHistoryPage(1, id, snapshot, before,
                    (1L..15L).map(::exchange), false, null)
                else -> error("unexpected cursor $before")
            }
        }
        val store = openHistoryStore(api, recent, uuid(8))
        store.setDraft("unsent editable draft")
        val initial = store.state.value
        val currentTurn = initial.currentTurn
        val currentResult = currentTurn?.result
        val currentContext = currentResult?.context
        assertNotNull(currentTurn)
        assertTrue(initial.detail!!.hasOlderExchanges)
        assertEquals(1, api.getCalls)

        assertTrue(store.loadOlderHistory())
        runCurrent()
        assertEquals((16L..55L).toList(), store.state.value.detail!!.exchanges.map { it.revision })
        assertTrue(store.state.value.detail!!.hasOlderExchanges)
        assertEquals(Triple(uuid(1), 36L, 55L), api.historyRequests[0])
        assertSame(currentTurn, store.state.value.currentTurn)
        assertSame(currentResult, store.state.value.currentTurn?.result)
        assertSame(currentContext, store.state.value.currentTurn?.result?.context)
        assertEquals("unsent editable draft", store.state.value.draft)

        assertTrue(store.loadOlderHistory())
        runCurrent()
        assertEquals((1L..55L).toList(), store.state.value.detail!!.exchanges.map { it.revision })
        assertFalse(store.state.value.detail!!.hasOlderExchanges)
        assertEquals(Triple(uuid(1), 16L, 55L), api.historyRequests[1])
        assertSame(currentTurn, store.state.value.currentTurn)
        assertSame(currentResult, store.state.value.currentTurn?.result)
        assertSame(currentContext, store.state.value.currentTurn?.result?.context)
        assertEquals("unsent editable draft", store.state.value.draft)
        assertEquals(1, api.getCalls)
        assertEquals(0, api.submitCalls)
    }

    @Test fun malformedHistorySnapshotCursorAndDuplicateRowsAreRejectedWithoutAppend() = runTest {
        val recent = (36L..55L).map(::exchange)
        val api = FakeApi()
        val store = openHistoryStore(api, recent, uuid(8))
        val original = store.state.value.detail
        val validRows = (16L..35L).map(::exchange)
        api.historyHandler = { id, before, _ -> AssistantWorkspaceHistoryPage(
            1, id, snapshotRevision = 54, beforeRevision = before,
            exchanges = validRows, hasOlderExchanges = true, nextBeforeRevision = 16,
        ) }
        assertTrue(store.loadOlderHistory())
        runCurrent()
        assertEquals(AssistantWorkspaceError.INVALID_RESPONSE, store.state.value.error)
        assertEquals(original, store.state.value.detail)

        api.historyHandler = { id, before, snapshot -> AssistantWorkspaceHistoryPage(
            1, id, snapshot, before,
            validRows.mapIndexed { index, row -> if (index == 0) row.copy(exchangeId = recent.first().exchangeId) else row },
            true, 16,
        ) }
        assertTrue(store.loadOlderHistory())
        runCurrent()
        assertEquals(AssistantWorkspaceError.INVALID_RESPONSE, store.state.value.error)
        assertEquals(original, store.state.value.detail)
        assertEquals(2, api.historyCalls)
    }

    @Test fun historyConflictFreezesPagingUntilExplicitThreadRefresh() = runTest {
        val api = FakeApi()
        val store = openHistoryStore(api, (36L..55L).map(::exchange), latest = null)
        api.historyHandler = { _, _, _ -> throw ApiFailure(FailureKind.HTTP, status = 409) }

        assertTrue(store.loadOlderHistory())
        runCurrent()
        assertTrue(store.state.value.historyRefreshRequired)
        assertFalse(store.state.value.continuationEnabled)
        assertEquals(1, api.historyCalls)

        api.readHandler = { detail(it, revision = 56, exchanges = (37L..56L).map(::exchange), hasOlder = true) }
        assertTrue(store.openThread(uuid(1)))
        runCurrent()
        assertFalse(store.state.value.historyRefreshRequired)
        assertEquals(56L, store.state.value.detail?.thread?.revision)
        assertEquals(1, api.historyCalls)
    }

    @Test fun lateNonCancellableHistoryPageCannotRestoreTextAfterScopeWipe() = runTest {
        val api = FakeApi()
        val gate = CompletableDeferred<Unit>()
        api.historyHandler = { id, before, snapshot ->
            withContext(NonCancellable) { gate.await() }
            AssistantWorkspaceHistoryPage(1, id, snapshot, before, (16L..35L).map(::exchange), true, 16L)
        }
        var current: AssistantWorkspaceScope? = scope()
        api.capabilityValue = capabilities.copy(historyPaging = true)
        api.readHandler = { detail(it, revision = 55, exchanges = (36L..55L).map(::exchange), hasOlder = true) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { current })
        store.onScopeChanged(); store.refreshCapabilities(); runCurrent()
        store.openThread(uuid(1)); runCurrent()
        store.setDraft("private draft before scope switch")

        assertTrue(store.loadOlderHistory())
        runCurrent()
        assertTrue(store.state.value.busy)
        assertEquals(1, api.historyCalls)
        current = scope(account = "account-b", generation = 2)
        store.onScopeChanged()
        assertEquals("account-b", store.state.value.accountId)
        assertNull(store.state.value.detail)
        assertEquals("", store.state.value.draft)

        gate.complete(Unit)
        runCurrent()
        assertEquals("account-b", store.state.value.accountId)
        assertNull(store.state.value.detail)
        assertNull(store.state.value.currentTurn)
        assertEquals("", store.state.value.draft)
        assertFalse(store.state.value.busy)
    }

    @Test fun historyAndLabelsStayAvailableWhenServerOwnedTurnsAreOffline() = runTest {
        val api = FakeApi()
        api.capabilityValue = capabilities.copy(serverOwnedTurns = false, historyPaging = true, threadLabels = true)
        api.readHandler = { detail(it, revision = 55, latest = uuid(8),
            exchanges = (36L..55L).map(::exchange), hasOlder = true) }
        api.historyHandler = { id, before, snapshot -> AssistantWorkspaceHistoryPage(
            1, id, snapshot, before, (16L..35L).map(::exchange), true, 16,
        ) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.onScopeChanged(); store.refreshCapabilities(); runCurrent()
        assertTrue(store.refreshThreads()); runCurrent()
        assertEquals(true, api.listIncludedLabels)
        assertTrue(store.openThread(uuid(1))); runCurrent()

        assertEquals(0, api.getCalls)
        assertFalse(store.state.value.continuationEnabled)
        assertTrue(store.loadOlderHistory()); runCurrent()
        assertEquals((16L..55L).toList(), store.state.value.detail!!.exchanges.map { it.revision })
        assertFalse(store.sendTurn(uuid(7)))
        assertEquals(0, api.submitCalls)
        assertEquals(1, api.historyCalls)
    }

    private suspend fun TestScope.openHistoryStore(
        api: FakeApi,
        exchanges: List<AssistantWorkspaceExchange>,
        latest: String?,
    ): AssistantWorkspaceStore {
        api.capabilityValue = capabilities.copy(historyPaging = true, threadLabels = true)
        api.readHandler = { detail(it, revision = 55, latest = latest,
            exchanges = exchanges, hasOlder = true) }
        api.getHandler = { id, request -> AssistantWorkspaceTurn(
            1, id, request, AssistantWorkspaceRequestStatus.COMPLETED, 55, true, null,
            AssistantTurn("results", "current result", buildJsonObject { put("visible", JsonPrimitive(true)) },
                buildJsonObject { put("filter", JsonPrimitive("original")) }, emptyList(), 0, false, null),
        ) }
        val store = AssistantWorkspaceStore(api, backgroundScope, { scope() })
        store.onScopeChanged(); store.refreshCapabilities(); runCurrent()
        store.openThread(uuid(1)); runCurrent()
        return store
    }
}
