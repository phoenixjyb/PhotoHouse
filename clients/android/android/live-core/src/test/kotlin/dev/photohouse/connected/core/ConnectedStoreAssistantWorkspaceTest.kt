package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.withContext
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ConnectedStoreAssistantWorkspaceTest {
    private fun membership(library: String, available: Boolean = true) =
        Membership(library, "approved", "viewer", 1, null, 0, available)

    private fun session(account: String = "account-a", familyAvailable: Boolean = true) = Session(
        account, "+12025550123", listOf(membership("family", familyAvailable), membership("second")),
    )

    private fun storeScope(testScope: kotlinx.coroutines.test.TestScope) =
        CoroutineScope(SupervisorJob() + UnconfinedTestDispatcher(testScope.testScheduler))

    private class PhotoApi(var currentSession: Session = Session(
        "account-a", "+12025550123", listOf(
            Membership("family", "approved", "viewer", 1, null, 0, true),
            Membership("second", "approved", "viewer", 1, null, 0, true),
        ),
    )) : PhotoHouseApi {
        override var assistantEnabled = true
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = currentSession
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) =
            Gallery(library, page, 50, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String): Detail =
            throw ApiFailure(FailureKind.INVALID_INPUT)
        override suspend fun captions(token: Bearer, library: String, assetId: String) =
            Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk =
            throw ApiFailure(FailureKind.INVALID_INPUT)
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray =
            throw ApiFailure(FailureKind.INVALID_INPUT)
    }

    private class WorkspaceApi : AssistantWorkspaceApi {
        override val assistantWorkspaceEnabled = true
        private val threadId = "11111111-1111-4111-8111-111111111111"
        private val turnId = "22222222-2222-4222-8222-222222222222"
        private val cardId = "33333333-3333-4333-8333-333333333333"
        private var revision = 0L
        private val memoryCard = AssistantSavedMemoryCard("memoir", cardId, "2", "a".repeat(64),
            "Family memoir", "A saved family story.")
        var capabilitiesCalls = 0
        var listCalls = 0
        var listGate: CompletableDeferred<Unit>? = null
        var listNonCancellable = false
        var listCancelled = false
        var capabilityScopes = mutableListOf<Pair<String, String>>()
        var listScopes = mutableListOf<Pair<String, String>>()

        override suspend fun capabilities(token: Bearer, library: String): AssistantWorkspaceCapabilities {
            capabilitiesCalls++
            capabilityScopes += token.header() to library
            return AssistantWorkspaceCapabilities(
                version = 1, available = true, threads = true, preferences = true,
                preferencesApplied = true, serverOwnedTurns = true, appliedPreferences = setOf("locale"),
            )
        }

        override suspend fun listThreads(token: Bearer, library: String): AssistantWorkspaceThreadList {
            listCalls++
            listScopes += token.header() to library
            try {
                listGate?.let { gate ->
                    if (listNonCancellable) withContext(NonCancellable) { gate.await() } else gate.await()
                }
            } catch (cancel: CancellationException) {
                listCancelled = true
                throw cancel
            }
            return AssistantWorkspaceThreadList(1, emptyList())
        }

        override suspend fun savedMemoryCardsCapabilities(token: Bearer, library: String) = SavedMemoryReaderCapabilities(1, true)
        override suspend fun savedMemoryReaderCapabilities(token: Bearer, library: String) = SavedMemoryReaderCapabilities(1, true)
        override suspend fun readThread(token: Bearer, library: String, threadId: String) = detail(library, revision)
        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                        expectedRevision: Long, text: String, parentRequestId: String?,
                                        acceptSavedMemoryCards: Boolean): AssistantWorkspaceTurn {
            revision = expectedRevision + 1
            return AssistantWorkspaceTurn(1, threadId, requestId, AssistantWorkspaceRequestStatus.COMPLETED, revision,
                false, null, AssistantTurn("memory_cards", "Found a saved memory.", null, null, emptyList(), 1, false, null,
                    memoryCards = listOf(memoryCard), savedMemoryContext = AssistantSavedMemoryContext(library,
                        "b".repeat(64), listOf(AssistantSavedMemoryReference(memoryCard.kind, memoryCard.id,
                            memoryCard.revision, memoryCard.sourceRevision)))))
        }
        override suspend fun savedMemoryReader(token: Bearer, library: String, threadId: String, turnId: String,
                                               ordinal: Int, expectedRevision: Long): SavedMemoryReaderPayload =
            SavedMemoryReaderPayload.Memoir(MemoryBook(cardId, 2, false, "Family memoir", "", "en",
                listOf(MemoryBookStorySummary("44444444-4444-4444-8444-444444444444", "A chapter", 3, 1, "1"))))

        private fun detail(library: String, revision: Long): AssistantWorkspaceThreadDetail {
            val thread = AssistantWorkspaceThreadSummary(threadId, library, "2026-10-01T00:00:00Z",
                "2026-10-02T00:00:00Z", "2026-11-01T00:00:00Z", revision)
            return AssistantWorkspaceThreadDetail(1, thread, emptyList())
        }
    }

    private suspend fun kotlinx.coroutines.test.TestScope.authenticatedStore(
        api: PhotoApi = PhotoApi(), workspace: WorkspaceApi? = WorkspaceApi(),
    ): Triple<ConnectedStore, PhotoApi, WorkspaceApi?> {
        val store = ConnectedStore(api, storeScope(this), now = { testScheduler.currentTime }, assistantWorkspaceApi = workspace)
        store.authenticate("+12025550123", "synthetic-password-only")
        runCurrent()
        return Triple(store, api, workspace)
    }

    @Test fun missingOrDisabledOptionalApiStaysInert() = runTest {
        val disabledWorkspace = WorkspaceApi()
        val disabledPhoto = PhotoApi().apply { assistantEnabled = false }
        val disabled = ConnectedStore(disabledPhoto, storeScope(this), now = { testScheduler.currentTime }, assistantWorkspaceApi = disabledWorkspace)
        assertNull(disabled.assistantWorkspaceCoordinator)
        assertEquals(AssistantWorkspaceState(), disabled.assistantWorkspaceState.value)
        disabled.authenticate("+12025550123", "synthetic-password-only")
        runCurrent()
        disabled.selectLibrary("family")
        runCurrent()
        assertNull(disabled.assistantWorkspaceCoordinator)
        assertEquals(0, disabledWorkspace.capabilitiesCalls)
        assertEquals(0, disabledWorkspace.listCalls)

        val enabledPhoto = PhotoApi()
        val withoutOptionalApi = ConnectedStore(enabledPhoto, storeScope(this), now = { testScheduler.currentTime })
        assertNull(withoutOptionalApi.assistantWorkspaceCoordinator)
        assertEquals(AssistantWorkspaceState(), withoutOptionalApi.assistantWorkspaceState.value)
        withoutOptionalApi.authenticate("+12025550123", "synthetic-password-only")
        runCurrent()
        withoutOptionalApi.selectLibrary("family")
        runCurrent()
        assertNull(withoutOptionalApi.assistantWorkspaceCoordinator)
        assertEquals(AssistantWorkspaceState(), withoutOptionalApi.assistantWorkspaceState.value)
    }

    @Test fun coordinatorScopesCapabilitiesAndDraftToTheCurrentAccountLibraryAndGeneration() = runTest {
        val (store, api, workspace) = authenticatedStore()
        val coordinator = requireNotNull(store.assistantWorkspaceCoordinator)
        store.selectLibrary("family")
        runCurrent()

        assertTrue(coordinator.refreshCapabilities())
        runCurrent()
        coordinator.setDraft("private family draft")
        val familyState = store.assistantWorkspaceState.value
        assertEquals("account-a", familyState.accountId)
        assertEquals("family", familyState.libraryId)
        assertEquals(store.state.value.generation, familyState.generation)
        assertEquals("private family draft", familyState.draft)
        assertEquals(1, workspace!!.capabilitiesCalls)
        assertEquals("Bearer ${"T".repeat(43)}" to "family", workspace.capabilityScopes.single())

        store.selectLibrary("second")
        runCurrent()
        val secondState = store.assistantWorkspaceState.value
        assertEquals("account-a", secondState.accountId)
        assertEquals("second", secondState.libraryId)
        assertEquals(store.state.value.generation, secondState.generation)
        assertNull(secondState.capabilities)
        assertEquals("", secondState.draft)
        assertEquals("family", workspace.capabilityScopes.single().second)
        assertEquals("account-a", api.currentSession.account_id)
    }

    @Test fun assistantReaderHandoffOpensMemoirWithoutLoadingTheShelf() = runTest {
        val (store) = authenticatedStore()
        store.selectLibrary("family"); runCurrent()
        val coordinator = requireNotNull(store.assistantWorkspaceCoordinator)
        assertNull(store.state.value.memoryBooks)
        assertNull(store.state.value.savedMemoryStories)
        coordinator.refreshCapabilities(); runCurrent()
        coordinator.refreshSavedMemoryCardsCapabilities(); runCurrent()
        coordinator.refreshSavedMemoryReaderCapabilities(); runCurrent()
        coordinator.openThread("11111111-1111-4111-8111-111111111111"); runCurrent()
        coordinator.setDraft("Find a saved memoir")
        coordinator.sendTurn(); runCurrent()
        coordinator.openSavedMemoryCard(0); runCurrent()
        val handoff = requireNotNull(coordinator.state.value.memoryReaderHandoff)

        assertTrue(store.openAssistantMemoryReader(handoff, "account-a", "family", store.state.value.generation))
        assertNull(store.state.value.savedMemoryStories)
        assertEquals("33333333-3333-4333-8333-333333333333", store.state.value.memoryBooks?.selectedBook?.id)
    }

    @Test fun backgroundForegroundErasesPrivateStateAndCancelsLateWorkspaceGet() = runTest {
        val (store, api, workspace) = authenticatedStore()
        store.selectLibrary("family")
        runCurrent()
        val coordinator = requireNotNull(store.assistantWorkspaceCoordinator)
        coordinator.refreshCapabilities()
        runCurrent()
        coordinator.setDraft("erase on lifecycle interruption")

        val gate = CompletableDeferred<Unit>()
        workspace!!.listGate = gate
        assertTrue(coordinator.refreshThreads())
        runCurrent()
        assertEquals(1, workspace.listCalls)
        assertTrue(store.assistantWorkspaceState.value.busy)

        store.background()
        runCurrent()
        assertEquals(AssistantWorkspaceState(), store.assistantWorkspaceState.value)
        assertTrue(workspace.listCancelled)
        gate.complete(Unit)
        runCurrent()
        assertEquals(AssistantWorkspaceState(), store.assistantWorkspaceState.value)

        store.foreground()
        runCurrent()
        val resumed = store.assistantWorkspaceState.value
        assertEquals("account-a", resumed.accountId)
        assertEquals("family", resumed.libraryId)
        assertEquals(store.state.value.generation, resumed.generation)
        assertNull(resumed.capabilities)
        assertEquals("", resumed.draft)
        assertNull(resumed.threads)
        assertEquals("account-a", api.currentSession.account_id)
    }

    @Test fun revokedMembershipAndAccountChangeFenceNonCancellableLateGet() = runTest {
        val (store, api, workspace) = authenticatedStore()
        store.selectLibrary("family")
        runCurrent()
        val coordinator = requireNotNull(store.assistantWorkspaceCoordinator)
        coordinator.refreshCapabilities()
        runCurrent()
        coordinator.setDraft("account-a private text")

        val gate = CompletableDeferred<Unit>()
        workspace!!.listGate = gate
        workspace.listNonCancellable = true
        assertTrue(coordinator.refreshThreads())
        runCurrent()
        assertEquals(1, workspace.listCalls)
        val oldGeneration = store.state.value.generation

        store.logout()
        runCurrent()
        api.currentSession = session("account-b", familyAvailable = false)
        store.authenticate("+12025550123", "synthetic-password-only")
        runCurrent()
        assertNotEquals(oldGeneration, store.state.value.generation)
        assertEquals("second", store.state.value.library)
        assertEquals("account-b", store.assistantWorkspaceState.value.accountId)
        assertEquals("second", store.assistantWorkspaceState.value.libraryId)
        assertEquals(store.state.value.generation, store.assistantWorkspaceState.value.generation)
        assertEquals("", store.assistantWorkspaceState.value.draft)

        // The adapter deliberately ignores cancellation to model a transport that completes late.
        gate.complete(Unit)
        runCurrent()
        assertEquals("", store.assistantWorkspaceState.value.draft)
        assertNull(store.assistantWorkspaceState.value.threads)
        assertEquals("account-b", store.assistantWorkspaceState.value.accountId)
        assertEquals("second", store.assistantWorkspaceState.value.libraryId)
        assertEquals(listOf("family"), workspace.listScopes.map { it.second })
        assertEquals(1, workspace.capabilitiesCalls)
        assertEquals("account-b", api.currentSession.account_id)
    }
}
