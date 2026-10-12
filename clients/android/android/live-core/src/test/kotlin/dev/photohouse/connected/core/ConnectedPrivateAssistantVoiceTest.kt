package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ConnectedPrivateAssistantVoiceTest {
    private val threadId = "11111111-1111-4111-8111-111111111111"
    private val secondThreadId = "22222222-2222-4222-8222-222222222222"

    @Test fun noSelectedPrivateThreadKeepsTheExistingV1Route() = runTest {
        val fixture = fixture(activatePrivate = false)

        assertTrue(fixture.store.privateAssistantConversationAvailable())
        assertTrue(fixture.store.sendAssistantText("find family photos"))
        runCurrent()

        assertEquals(1, fixture.photoApi.v1TurnCalls)
        assertEquals(0, fixture.workspaceApi.submitCalls)
        assertNull(fixture.store.state.value.assistant?.privateThreadId)
    }

    @Test fun twoPrivateVoiceTurnsLinkAsrParentsAndWaitForPlaybackBeforeRelistening() = runTest {
        val fixture = fixture(activatePrivate = true)
        fixture.platform.captures.send(wav())
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start())
        runCurrent()
        fixture.platform.speechStarted.receive()
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(1, fixture.workspaceApi.submitCalls)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        assertEquals(fixture.photoApi.transcriptionIds.single(), fixture.workspaceApi.parentIds.single())
        assertEquals(fixture.photoApi.transcriptionTexts.single(), fixture.workspaceApi.texts.single())

        fixture.platform.speechResults.send(true)
        runCurrent()
        fixture.platform.speechStarted.receive()

        assertEquals(2, fixture.platform.captureCalls)
        assertEquals(2, fixture.photoApi.transcriptionIds.size)
        assertEquals(2, fixture.workspaceApi.submitCalls)
        assertEquals(fixture.photoApi.transcriptionIds, fixture.workspaceApi.parentIds)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        fixture.driver.end()
        fixture.driver.close()
    }

    @Test fun recoveredPrivateTurnPausesBeforeSpeechNavigationOrRelistening() = runTest {
        val fixture = fixture(activatePrivate = true)
        fixture.workspaceApi.submitHandler = { _, _, _, _ -> throw ApiFailure(FailureKind.OFFLINE) }
        fixture.workspaceApi.getHandler = { id, request, expectedRevision ->
            fixture.workspaceApi.revision = expectedRevision + 1
            fixture.workspaceApi.latestRequestId = request
            fixture.workspaceApi.completed(id, request, fixture.workspaceApi.revision, recovered = true)
        }
        fixture.platform.captures.send(wav())
        var opened = 0
        fixture.driver.close()
        val voiceScope = voiceScope(fixture.store)
        fixture.driver = AssistantVoiceSessionStore(
            fixture.store, voiceScope, backgroundScope, fixture.platform, "en", { true },
        ) { _, _ -> opened++ }

        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.REVIEW_REQUIRED, fixture.driver.state.value.reason)
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(1, fixture.workspaceApi.submitCalls)
        assertEquals(1, fixture.workspaceApi.getCalls)
        assertEquals(0, fixture.photoApi.speechCalls)
        assertEquals(0, fixture.platform.speechCalls)
        assertEquals(0, opened)
        assertTrue(fixture.store.state.value.assistant!!.turns.last().turn.recovered)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        fixture.driver.close()
    }

    @Test fun cancelledPrivateWaitKeepsImmutableRequestUntilExplicitGetRecovery() = runTest {
        val fixture = fixture(activatePrivate = true)
        val gate = CompletableDeferred<Unit>()
        fixture.workspaceApi.submitHandler = { id, request, revision, _ ->
            withContext(NonCancellable) { gate.await() }
            fixture.workspaceApi.revision = revision + 1
            fixture.workspaceApi.latestRequestId = request
            fixture.workspaceApi.completed(id, request, revision + 1, recovered = false)
        }
        fixture.workspaceApi.getHandler = { id, request, revision ->
            fixture.workspaceApi.revision = revision + 1
            fixture.workspaceApi.latestRequestId = request
            fixture.workspaceApi.completed(id, request, revision + 1, recovered = true)
        }
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start())
        runCurrent()

        val pending = requireNotNull(fixture.store.state.value.assistant?.pendingTurn)
        val workspacePending = requireNotNull(fixture.store.assistantWorkspaceState.value.pendingTurn)
        assertEquals(pending.requestId, workspacePending.requestId)
        assertEquals(pending.parentRequestId, workspacePending.parentRequestId)
        assertEquals("find the beach", workspacePending.text)
        assertTrue(fixture.driver.pause())
        val cancelledState = fixture.store.assistantWorkspaceState.value
        assertFalse(cancelledState.busy)
        assertTrue(cancelledState.uncertain)
        assertEquals(workspacePending, cancelledState.pendingTurn)
        assertEquals("find the beach", cancelledState.draft)

        gate.complete(Unit)
        runCurrent()
        assertEquals(1, fixture.workspaceApi.submitCalls)
        assertEquals(0, fixture.workspaceApi.getCalls)
        assertNull(fixture.store.assistantWorkspaceState.value.currentTurn)
        assertEquals(workspacePending, fixture.store.assistantWorkspaceState.value.pendingTurn)
        assertEquals(workspacePending.requestId, fixture.store.state.value.assistant?.pendingTurn?.requestId)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        assertEquals(0, fixture.photoApi.speechCalls)

        fixture.store.checkAssistantReceipt()
        runCurrent()
        assertEquals(1, fixture.workspaceApi.submitCalls)
        assertEquals(1, fixture.workspaceApi.getCalls)
        assertTrue(fixture.store.state.value.assistant!!.turns.last().turn.recovered)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        assertEquals(0, fixture.photoApi.speechCalls)
        fixture.driver.close()
    }

    @Test fun backgroundWipesPrivateConversationAndDoesNotFallBackToV1() = runTest {
        val fixture = fixture(activatePrivate = true)
        assertTrue(fixture.store.privateAssistantConversationAvailable())

        fixture.store.background()
        runCurrent()

        assertEquals(AssistantWorkspaceState(), fixture.store.assistantWorkspaceState.value)
        assertFalse(fixture.store.privateAssistantConversationAvailable())
        assertFalse(fixture.store.sendAssistantText("must not fall back after background"))
        assertEquals(0, fixture.workspaceApi.submitCalls)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        assertNull(fixture.store.state.value.assistant)
    }

    @Test fun terminalPrivateTurnsPauseVoiceKeepDraftAndNeedExplicitReactivationBeforeNextRequest() = runTest {
        for (terminal in listOf(AssistantWorkspaceRequestStatus.FAILED, AssistantWorkspaceRequestStatus.INTERRUPTED)) {
            val fixture = fixture(activatePrivate = true)
            fixture.workspaceApi.submitHandler = { id, request, revision, _ ->
                fixture.workspaceApi.revision = revision
                AssistantWorkspaceTurn(1, id, request, terminal, revision, false,
                    terminal.name.lowercase(), null)
            }
            fixture.platform.captures.send(wav())

            assertTrue(fixture.driver.start())
            runCurrent()

            val assistant = requireNotNull(fixture.store.state.value.assistant)
            assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
            assertEquals(VoiceSessionStopReason.REQUEST_FAILED, fixture.driver.state.value.reason)
            assertEquals(1, fixture.platform.captureCalls)
            assertEquals(0, fixture.platform.speechCalls)
            assertEquals(0, fixture.photoApi.speechCalls)
            assertEquals(0, fixture.photoApi.v1TurnCalls)
            assertEquals(terminal.name.lowercase(), assistant.privateRequestStatus)
            assertNotNull("central request stays available for explicit review", assistant.pendingTurn)
            assertNull(fixture.store.assistantWorkspaceState.value.pendingTurn)
            assertEquals("find the beach", fixture.store.assistantWorkspaceState.value.draft)
            assertEquals(1, fixture.workspaceApi.submitCalls)

            val revision = fixture.store.assistantWorkspaceState.value.detail!!.thread.revision
            assertTrue(fixture.store.activatePrivateAssistantConversation(threadId, revision))
            assertNull(fixture.store.state.value.assistant!!.pendingTurn)
            assertTrue(fixture.store.sendAssistantText("ask again explicitly"))
            runCurrent()
            assertEquals(2, fixture.workspaceApi.submitCalls)
            assertEquals("ask again explicitly", fixture.workspaceApi.texts.last())
            assertEquals(0, fixture.photoApi.v1TurnCalls)
            fixture.driver.close()
        }
    }

    @Test fun switchingAndDeletingSelectedThreadClearsPrivatePresentationUntilExplicitActivation() = runTest {
        val fixture = fixture(activatePrivate = true)
        assertTrue(fixture.store.sendAssistantText("private result to clear"))
        runCurrent()
        assertNotNull(fixture.store.state.value.assistant!!.turns.last())
        assertTrue(fixture.store.loadAssistantSpeech("en"))
        runCurrent()
        assertNotNull(fixture.store.state.value.assistant!!.speechAudio)

        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        assertTrue(coordinator.openThread(secondThreadId))
        runCurrent()
        var assistant = requireNotNull(fixture.store.state.value.assistant)
        assertTrue(assistant.turns.isEmpty())
        assertNull(assistant.context)
        assertNull(assistant.speechAudio)
        assertFalse(fixture.store.privateAssistantConversationAvailable())

        assertTrue(fixture.store.activatePrivateAssistantConversation(secondThreadId, 0))
        assertTrue(fixture.store.privateAssistantConversationAvailable())
        assertEquals(secondThreadId, fixture.store.state.value.assistant!!.privateThreadId)
        assertTrue(fixture.store.sendAssistantText("new selected thread"))
        runCurrent()
        assertEquals(2, fixture.workspaceApi.submitCalls)

        assertTrue(fixture.store.loadAssistantSpeech("en"))
        runCurrent()
        assertNotNull(fixture.store.state.value.assistant!!.speechAudio)
        assertTrue(coordinator.deleteCurrentThread())
        runCurrent()
        assistant = requireNotNull(fixture.store.state.value.assistant)
        assertTrue(assistant.turns.isEmpty())
        assertNull(assistant.context)
        assertNull(assistant.speechAudio)
        assertFalse(fixture.store.privateAssistantConversationAvailable())
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        fixture.driver.close()
    }

    @Test fun disablingWorkspaceCapabilitiesWhileCapturingStopsVoiceAndKeepsPrivateRouteSelected() = runTest {
        val fixture = fixture(activatePrivate = true)
        assertTrue(fixture.driver.start())
        runCurrent()
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(VoiceSessionPhase.LISTENING, fixture.driver.state.value.phase)

        fixture.workspaceApi.capabilitiesResponse = AssistantWorkspaceCapabilities(
            1, available = false, threads = false, preferences = false, preferencesApplied = false,
            serverOwnedTurns = false,
        )
        assertTrue(requireNotNull(fixture.store.assistantWorkspaceCoordinator).refreshCapabilities())
        runCurrent()

        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.CONTEXT_CHANGED, fixture.driver.state.value.reason)
        assertNull(fixture.store.state.value.assistant!!.speechAudio)
        assertTrue(fixture.store.state.value.assistant!!.turns.isEmpty())
        assertFalse(fixture.store.privateAssistantConversationAvailable())
        assertFalse(fixture.store.sendAssistantText("must remain private"))
        assertEquals(0, fixture.workspaceApi.submitCalls)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        fixture.driver.close()
    }

    @Test fun workspaceSubmitAccessDeniedClearsAssistantAndNeverFallsBackToV1() = runTest {
        val fixture = fixture(activatePrivate = true)
        fixture.workspaceApi.submitHandler = { _, _, _, _ -> throw ApiFailure(FailureKind.HTTP, status = 403) }
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(1, fixture.workspaceApi.submitCalls)
        assertEquals(0, fixture.workspaceApi.getCalls)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        assertEquals(0, fixture.photoApi.speechCalls)
        assertNull(fixture.store.state.value.assistant)
        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.CONTEXT_CHANGED, fixture.driver.state.value.reason)
        fixture.driver.close()
    }

    private suspend fun TestScope.fixture(activatePrivate: Boolean): Fixture {
        val photoApi = PhotoApi()
        val workspaceApi = WorkspaceApi(threadId)
        val store = ConnectedStore(
            photoApi, backgroundScope, now = { testScheduler.currentTime }, assistantWorkspaceApi = workspaceApi,
        )
        store.authenticate("+12025550123", "synthetic-password-only")
        runCurrent()
        store.selectLibrary("family")
        runCurrent()
        store.loadAssistantCapabilities()
        runCurrent()
        val coordinator = requireNotNull(store.assistantWorkspaceCoordinator)
        assertTrue(coordinator.refreshCapabilities())
        runCurrent()
        assertTrue(coordinator.openThread(threadId))
        runCurrent()
        if (activatePrivate) assertTrue(store.activatePrivateAssistantConversation(threadId, 0))
        val platform = FakePlatform()
        val driver = AssistantVoiceSessionStore(store, voiceScope(store), backgroundScope, platform, "en", { true })
        return Fixture(store, photoApi, workspaceApi, platform, driver)
    }

    private fun voiceScope(store: ConnectedStore): VoiceSessionScope {
        val live = store.state.value
        return VoiceSessionScope(checkNotNull(live.session).account_id, checkNotNull(live.library), live.generation)
    }

    private data class Fixture(
        val store: ConnectedStore,
        val photoApi: PhotoApi,
        val workspaceApi: WorkspaceApi,
        val platform: FakePlatform,
        var driver: AssistantVoiceSessionStore,
    )

    private class FakePlatform : AssistantVoiceSessionPlatform {
        val captures = Channel<ByteArray?>(Channel.UNLIMITED)
        val speechStarted = Channel<Unit>(Channel.UNLIMITED)
        val speechResults = Channel<Boolean>(Channel.UNLIMITED)
        var captureCalls = 0
        var speechCalls = 0
        override suspend fun capture(maxSeconds: Int): ByteArray? {
            captureCalls++
            return captures.receive()
        }
        override suspend fun playSpeech(audio: ProtectedAnnotationAudio): Boolean {
            speechCalls++
            speechStarted.send(Unit)
            return speechResults.receive()
        }
        override fun stopAudio() = Unit
        override fun finishCapture() { captures.trySend(null) }
    }

    private class PhotoApi : PhotoHouseApi {
        override val assistantEnabled = true
        var v1TurnCalls = 0
        var speechCalls = 0
        val transcriptionIds = mutableListOf<String>()
        val transcriptionTexts = mutableListOf<String>()
        override suspend fun assistantCapabilities(token: Bearer, library: String) = AssistantCapabilities(true, true, true, true, 30)
        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript {
            transcriptionIds += requestId
            val transcript = "find the beach"
            transcriptionTexts += transcript
            return AssistantTranscript(transcript, "en", AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        }
        override suspend fun assistantTurn(token: Bearer, library: String, text: String,
                                           context: JsonObject?, requestId: String, parentRequestId: String?): AssistantTurn {
            v1TurnCalls++
            return result(requestId)
        }
        override suspend fun assistantSpeech(token: Bearer, library: String, context: JsonObject?, language: String,
                                             requestId: String, parentRequestId: String?): AssistantSpeechResult {
            speechCalls++
            return AssistantSpeechResult(syntheticAnnotationWav(), AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        }
        override suspend fun login(phone: String, password: String) = SessionToken(86400, "T".repeat(43), "Bearer")
        override suspend fun register(phone: String, password: String, code: String) = login(phone, password)
        override suspend fun session(token: Bearer) = Session("account-a", "+12025550123", listOf(
            Membership("family", "approved", "viewer", 1, null, 0, true),
            Membership("second", "approved", "viewer", 1, null, 0, true),
        ))
        override suspend fun acceptInvitation(token: Bearer, code: String) = Unit
        override suspend fun logout(token: Bearer) = Unit
        override suspend fun gallery(token: Bearer, library: String, page: Int) = Gallery(library, page, 50, 0, false, emptyList())
        override suspend fun detail(token: Bearer, library: String, assetId: String) = Detail(library, false, testAsset())
        override suspend fun captions(token: Bearer, library: String, assetId: String) = Captions(library, assetId, false, emptyList())
        override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? = null
        override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int) = VideoChunk(start, 0, byteArrayOf())
        override suspend fun originalPhoto(token: Bearer, library: String, assetId: String) = byteArrayOf()
    }

    private class WorkspaceApi(private val threadId: String) : AssistantWorkspaceApi {
        override val assistantWorkspaceEnabled = true
        var capabilitiesResponse = AssistantWorkspaceCapabilities(
            1, true, true, true, true, true, setOf("locale"),
        )
        var revision = 0L
        var latestRequestId: String? = null
        var submitCalls = 0
        var getCalls = 0
        val requestIds = mutableListOf<String>()
        val parentIds = mutableListOf<String?>()
        val texts = mutableListOf<String>()
        var submitHandler: suspend (String, String, Long, String) -> AssistantWorkspaceTurn = { id, request, expected, _ ->
            revision = expected + 1
            latestRequestId = request
            completed(id, request, revision, recovered = false)
        }
        var getHandler: suspend (String, String, Long) -> AssistantWorkspaceTurn = { id, request, _ ->
            AssistantWorkspaceTurn(1, id, request, AssistantWorkspaceRequestStatus.PENDING, revision, true, null, null)
        }

        override suspend fun capabilities(token: Bearer, library: String) = capabilitiesResponse
        override suspend fun readThread(token: Bearer, library: String, threadId: String) =
            AssistantWorkspaceThreadDetail(1, summary(threadId), emptyList(), latestRequestId.takeIf { threadId == this.threadId })
        override suspend fun deleteThread(token: Bearer, library: String, threadId: String, expectedRevision: Long) =
            AssistantWorkspaceDeletedThread(threadId, true)
        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                        expectedRevision: Long, text: String): AssistantWorkspaceTurn =
            submitTurn(token, library, threadId, requestId, expectedRevision, text, null)
        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                        expectedRevision: Long, text: String, parentRequestId: String?): AssistantWorkspaceTurn {
            submitCalls++
            requestIds += requestId
            parentIds += parentRequestId
            texts += text
            return submitHandler(threadId, requestId, expectedRevision, text)
        }
        override suspend fun getTurn(token: Bearer, library: String, threadId: String, requestId: String): AssistantWorkspaceTurn {
            getCalls++
            return getHandler(threadId, requestId, revision)
        }

        fun completed(id: String, request: String, resultRevision: Long, recovered: Boolean) = AssistantWorkspaceTurn(
            version = 1, threadId = id, requestId = request, status = AssistantWorkspaceRequestStatus.COMPLETED,
            revision = resultRevision, recovered = recovered, error = null,
            result = result(request), receipt = AssistantRequestReceipt(request, "enabled", "succeeded"),
        )

        private fun summary(id: String = threadId) = AssistantWorkspaceThreadSummary(
            id, "family", "2026-10-13T00:00:00Z", "2026-10-13T00:00:00Z",
            "2026-11-12T00:00:00Z", if (id == threadId) revision else 0L, if (id == threadId) revision.toInt() else 0,
        )
    }

    companion object {
        private fun result(requestId: String) = AssistantTurn(
            kind = "results", reply = "Found one beach photo.", context = visibleContext(), filters = buildJsonObject { },
            items = listOf(testAsset()), total = 1, hasMore = false, effect = null,
            receipt = AssistantRequestReceipt(requestId, "enabled", "succeeded"),
        )

        private fun visibleContext(): JsonObject = buildJsonObject {
            put("visible_ids", buildJsonArray { add(JsonPrimitive("1")) })
        }

        private fun testAsset() = Asset("1", "image", 640, 480, null, null, "/assets/1/thumbnail?library=family")

        private fun wav() = ByteArray(16_046).also { bytes ->
            "RIFF".toByteArray().copyInto(bytes)
            "WAVE".toByteArray().copyInto(bytes, 8)
        }
    }
}
