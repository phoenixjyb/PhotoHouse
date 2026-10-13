package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AssistantVoiceSessionStoreTest {
    @Test fun playbackCompletionGatesTheNextCaptureAndRunsTwoTurns() = runTest {
        val fixture = fixture()
        val firstWav = wav()
        val secondWav = wav()
        fixture.platform.captures.send(firstWav)
        fixture.platform.captures.send(secondWav)

        assertTrue(fixture.driver.start())
        runCurrent()
        fixture.platform.speechStarted.receive()
        assertFalse(fixture.driver.canUseManualControls())
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(1, fixture.api.assistantTurnCalls)
        assertEquals(fixture.api.transcriptionIds.single(), fixture.api.turnParentIds.single())

        fixture.platform.speechResults.send(true)
        runCurrent()
        assertEquals("completed", fixture.api.playbackOutcomes.single().second)
        assertEquals(2, fixture.platform.captureCalls)
        fixture.platform.speechStarted.receive()
        assertEquals(2, fixture.api.assistantTurnCalls)
        assertEquals(0, firstWav.sumOf { it.toInt() and 0xff })
        assertEquals(0, secondWav.sumOf { it.toInt() and 0xff })

        fixture.driver.end()
        fixture.driver.close()
        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
    }

    @Test fun actualPlatformStartFactsAreOverlaidAndLateCaptureCallbackIsIgnored() = runTest {
        val fixture = fixture()
        fixture.platform.autoCaptureStarted = false
        assertTrue(fixture.driver.start())
        runCurrent()
        val lateCaptureStarted = fixture.platform.captureStartedCallbacks.single()
        assertEquals(VoiceSessionPhase.LISTENING, fixture.driver.state.value.phase)
        assertFalse(fixture.driver.state.value.captureStarted)
        assertFalse(fixture.driver.state.value.playbackStarted)

        lateCaptureStarted()
        assertTrue(fixture.driver.state.value.captureStarted)
        assertFalse(fixture.driver.state.value.playbackStarted)
        assertTrue(fixture.driver.pause())
        assertFalse(fixture.driver.state.value.captureStarted)
        lateCaptureStarted()
        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertFalse(fixture.driver.state.value.captureStarted)
        assertFalse(fixture.driver.state.value.playbackStarted)

        assertTrue(fixture.driver.resume())
        runCurrent()
        val resumedCaptureStarted = fixture.platform.captureStartedCallbacks.last()
        lateCaptureStarted()
        assertEquals(VoiceSessionPhase.LISTENING, fixture.driver.state.value.phase)
        assertFalse(fixture.driver.state.value.captureStarted)
        resumedCaptureStarted()
        assertTrue(fixture.driver.state.value.captureStarted)
        fixture.driver.close()
    }

    @Test fun platformStartCallbackIsIgnoredAfterForegroundOrVoiceScopeChanges() = runTest {
        val backgrounded = fixture()
        backgrounded.platform.autoCaptureStarted = false
        assertTrue(backgrounded.driver.start())
        runCurrent()
        val startedAfterBackground = backgrounded.platform.captureStartedCallbacks.single()
        backgrounded.platform.foreground = false
        startedAfterBackground()
        assertFalse(backgrounded.driver.state.value.captureStarted)
        backgrounded.driver.close()

        val changedScope = fixture()
        changedScope.platform.autoCaptureStarted = false
        assertTrue(changedScope.driver.start())
        runCurrent()
        val startedAfterScopeChange = changedScope.platform.captureStartedCallbacks.single()
        changedScope.store.selectLibrary("second")
        runCurrent()
        startedAfterScopeChange()
        assertEquals(VoiceSessionPhase.ENDED, changedScope.driver.state.value.phase)
        assertFalse(changedScope.driver.state.value.captureStarted)
        changedScope.driver.close()
    }

    @Test fun playbackPreparationAndLatePlaybackCallbackRemainTruthful() = runTest {
        val fixture = fixture()
        fixture.platform.autoPlaybackStarted = false
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start())
        runCurrent()
        fixture.platform.speechStarted.receive()
        val latePlaybackStarted = fixture.platform.playbackStartedCallbacks.single()
        assertEquals(VoiceSessionPhase.SPEAKING, fixture.driver.state.value.phase)
        assertFalse(fixture.driver.state.value.playbackStarted)
        assertFalse(fixture.driver.state.value.captureStarted)

        latePlaybackStarted()
        assertTrue(fixture.driver.state.value.playbackStarted)
        assertTrue(fixture.driver.end())
        assertFalse(fixture.driver.state.value.playbackStarted)
        latePlaybackStarted()
        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertFalse(fixture.driver.state.value.playbackStarted)
        fixture.driver.close()
    }

    @Test fun pausingDuringTranscriptionFencesLateTranscriptAndDoesNotStartAnotherCapture() = runTest {
        val fixture = fixture()
        val gate = CompletableDeferred<Unit>()
        fixture.api.transcriptionGate = gate
        val wav = wav()
        fixture.platform.captures.send(wav)
        assertTrue(fixture.driver.start())
        runCurrent()
        assertEquals(1, fixture.api.transcriptionCalls)
        assertTrue(fixture.store.state.value.assistant!!.transcribing)
        assertEquals(VoiceSessionPhase.TRANSCRIBING, fixture.driver.state.value.phase)
        assertFalse(fixture.driver.state.value.captureStarted)
        assertFalse(fixture.driver.state.value.playbackStarted)

        assertTrue(fixture.driver.pause())
        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertFalse(fixture.store.state.value.assistant!!.transcribing)
        gate.complete(Unit)
        runCurrent()
        assertNull(fixture.store.state.value.assistant!!.transcript)
        assertEquals(0, fixture.api.assistantTurnCalls)
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(0, wav.sumOf { it.toInt() and 0xff })
    }

    @Test fun uncertainSubmittedTurnCannotBeResubmittedOnResume() = runTest {
        val fixture = fixture()
        fixture.api.turnFailure = ApiFailure(FailureKind.OFFLINE)
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.UNCERTAIN_REQUEST, fixture.driver.state.value.reason)
        assertNotNull(fixture.store.state.value.assistant!!.pendingTurn)
        assertEquals(1, fixture.api.assistantTurnCalls)
        assertFalse(fixture.driver.resume())
        assertEquals(1, fixture.api.assistantTurnCalls)
        assertEquals(1, fixture.platform.captureCalls)
    }

    @Test fun forbiddenTranscriptionStopsWithoutASecondCaptureOrPrivateTranscript() = runTest {
        val fixture = fixture()
        fixture.api.transcriptionFailure = ApiFailure(FailureKind.HTTP, status = 403)
        val captured = wav()
        fixture.platform.captures.send(captured)

        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(1, fixture.api.transcriptionCalls)
        assertEquals(0, fixture.api.assistantTurnCalls)
        assertFalse(fixture.driver.state.value.phase == VoiceSessionPhase.LISTENING)
        assertNull(fixture.store.state.value.assistant?.transcript)
        assertNull(fixture.store.state.value.assistant?.speechAudio)
        assertEquals(0, captured.sumOf { it.toInt() and 0xff })
    }

    @Test fun recognizedAsrNoInputStopsTheVoiceTurnWithoutSubmittingAnEmptyQuery() = runTest {
        val fixture = fixture()
        fixture.api.transcriptionFailure = ApiFailure(FailureKind.HTTP, 422, assistantErrorCode = "speech_no_input")
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(Message.ASSISTANT_ASR_NO_INPUT, fixture.store.state.value.assistant?.failure?.message)
        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertEquals(0, fixture.api.assistantTurnCalls)
        assertNull(fixture.store.state.value.assistant?.transcript)
    }

    @Test fun forbiddenSpeechStopsWithoutPlaybackOrRelisteningAndClearsAudioState() = runTest {
        val fixture = fixture()
        fixture.api.speechFailure = ApiFailure(FailureKind.HTTP, status = 403)
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(1, fixture.api.assistantTurnCalls)
        assertEquals(1, fixture.api.speechCalls)
        assertEquals(0, fixture.platform.speechCalls)
        assertFalse(fixture.driver.state.value.phase == VoiceSessionPhase.LISTENING)
        assertNull(fixture.store.state.value.assistant?.transcript)
        assertNull(fixture.store.state.value.assistant?.speechAudio)
    }

    @Test fun failedPlaybackPausesInsteadOfOpeningTheMicrophoneAgain() = runTest {
        val fixture = fixture()
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start())
        runCurrent()
        fixture.platform.speechStarted.receive()

        fixture.platform.speechResults.send(false)
        runCurrent()

        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.SPEECH_FAILED, fixture.driver.state.value.reason)
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(1, fixture.api.assistantTurnCalls)
        assertEquals(1, fixture.platform.speechCalls)
        assertEquals("failed", fixture.api.playbackOutcomes.single().second)
    }

    @Test fun endingDuringPlaybackReportsCancellationOnlyForTheOwnedSpeech() = runTest {
        val fixture = fixture()
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start())
        runCurrent()
        fixture.platform.speechStarted.receive()
        val requestId = fixture.store.state.value.assistant!!.lastRequestReceipt!!.requestId

        assertTrue(fixture.driver.end())
        runCurrent()

        assertEquals(listOf(requestId to "cancelled"), fixture.api.playbackOutcomes)
        assertNull(fixture.store.state.value.assistant!!.speechAudio)
    }

    @Test fun staleAudioCallbackAfterLibraryChangeDoesNotReportPlayback() = runTest {
        val fixture = fixture()
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start())
        runCurrent()
        fixture.platform.speechStarted.receive()
        val audio = fixture.store.state.value.assistant!!.speechAudio!!

        fixture.store.selectLibrary("second")
        runCurrent()
        assertFalse(fixture.store.reportAssistantPlaybackOutcome(audio, "completed"))
        assertTrue(fixture.api.playbackOutcomes.isEmpty())
    }

    @Test fun manualPlaybackReportsOnceAndDoesNothingWithoutServerCapability() = runTest {
        val fixture = fixture()
        assertTrue(fixture.store.sendAssistantText("find the beach"))
        runCurrent()
        assertTrue(fixture.store.loadAssistantSpeech("en"))
        runCurrent()
        val audio = fixture.store.state.value.assistant!!.speechAudio!!
        val requestId = fixture.store.state.value.assistant!!.lastRequestReceipt!!.requestId
        assertTrue(fixture.store.reportAssistantPlaybackOutcome(audio, "completed"))
        assertFalse(fixture.store.reportAssistantPlaybackOutcome(audio, "failed"))
        runCurrent()
        assertEquals(listOf(requestId to "completed"), fixture.api.playbackOutcomes)

        fixture.store.clearAssistantSpeech()
        fixture.api.playbackTracking = false
        assertTrue(fixture.store.sendAssistantText("find the beach"))
        runCurrent()
        assertTrue(fixture.store.loadAssistantSpeech("en"))
        runCurrent()
        val unsupportedAudio = fixture.store.state.value.assistant!!.speechAudio!!
        assertFalse(fixture.store.reportAssistantPlaybackOutcome(unsupportedAudio, "completed"))
        runCurrent()
        assertEquals(1, fixture.api.playbackOutcomes.size)
    }

    @Test fun alreadyCompletedApiCallsAreBoundByTheirNewRequestIds() = runTest {
        val api = VoiceApi()
        val fastScope = CoroutineScope(SupervisorJob() + UnconfinedTestDispatcher(testScheduler))
        val store = ConnectedStore(api, fastScope) { testScheduler.currentTime }
        store.authenticate("+12025550123", "synthetic-password-only")
        runCurrent()
        store.selectLibrary("family")
        runCurrent()
        store.loadAssistantCapabilities()
        runCurrent()
        val live = store.state.value
        val voiceScope = VoiceSessionScope(checkNotNull(live.session).account_id, checkNotNull(live.library), live.generation)
        val platform = FakePlatform()
        platform.captures.send(wav())
        val driver = AssistantVoiceSessionStore(store, voiceScope, fastScope, platform, "en", { true })

        assertTrue(driver.start())
        runCurrent()
        platform.speechStarted.receive()
        assertEquals(1, api.transcriptionCalls)
        assertEquals(1, api.assistantTurnCalls)
        assertEquals(1, api.speechCalls)
        assertEquals(VoiceSessionPhase.SPEAKING, driver.state.value.phase)
        driver.end()
        driver.close()
    }

    @Test fun reviewPauseAllowsOnlyAnExplicitSameScopeContinue() = runTest {
        val fixture = fixture()
        fixture.api.responseKind = "clarification"
        fixture.api.responseItems = emptyList()
        fixture.platform.captures.send(wav())
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start())
        runCurrent()
        assertEquals(VoiceSessionStopReason.REVIEW_REQUIRED, fixture.driver.state.value.reason)
        assertEquals(1, fixture.platform.captureCalls)
        assertTrue(fixture.driver.resume())
        runCurrent()
        assertEquals(2, fixture.platform.captureCalls)
        fixture.driver.end()
        fixture.driver.close()
    }

    @Test fun idleClosePreservesManualTranscriptAndContextChangeStopsWithoutOpeningAudio() = runTest {
        val fixture = fixture()
        val manualWav = wav()
        assertTrue(fixture.store.transcribeAssistant(manualWav))
        runCurrent()
        val manualTranscript = fixture.store.state.value.assistant!!.transcript
        assertNotNull(manualTranscript)

        val idle = AssistantVoiceSessionStore(
            fixture.store, fixture.scope, backgroundScope, fixture.platform, "zh", { true },
        )
        assertTrue(idle.canUseManualControls())
        idle.close()
        assertFalse(idle.canUseManualControls())
        assertSame(manualTranscript, fixture.store.state.value.assistant!!.transcript)

        // Clear the reviewed transcript, then begin a voice session whose first request
        // deliberately returns no context. Protected TTS must remain unavailable.
        fixture.store.clearAssistantTranscript()
        fixture.api.responseContext = null
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start())
        runCurrent()
        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.SPEECH_FAILED, fixture.driver.state.value.reason)
        assertEquals(0, fixture.api.speechCalls)
        assertEquals(0, fixture.platform.speechCalls)

        fixture.store.selectLibrary("second")
        runCurrent()
        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.CONTEXT_CHANGED, fixture.driver.state.value.reason)
        assertEquals(0, fixture.platform.speechCalls)
        fixture.driver.close()
    }

    private suspend fun TestScope.fixture(): Fixture {
        val api = VoiceApi()
        val store = ConnectedStore(api, backgroundScope) { testScheduler.currentTime }
        store.authenticate("+12025550123", "synthetic-password-only")
        runCurrent()
        store.selectLibrary("family")
        runCurrent()
        store.loadAssistantCapabilities()
        runCurrent()
        val live = store.state.value
        val scope = VoiceSessionScope(checkNotNull(live.session).account_id, checkNotNull(live.library), live.generation)
        val platform = FakePlatform()
        val driver = AssistantVoiceSessionStore(store, scope, backgroundScope, platform, "en", { platform.foreground })
        return Fixture(api, store, scope, platform, driver)
    }

    private data class Fixture(
        val api: VoiceApi,
        val store: ConnectedStore,
        val scope: VoiceSessionScope,
        val platform: FakePlatform,
        val driver: AssistantVoiceSessionStore,
    )

    private class FakePlatform : AssistantVoiceSessionPlatform {
        val captures = Channel<ByteArray?>(Channel.UNLIMITED)
        val speechStarted = Channel<Unit>(Channel.UNLIMITED)
        val speechResults = Channel<Boolean>(Channel.UNLIMITED)
        var captureCalls = 0
        var speechCalls = 0
        var stopCalls = 0
        var autoCaptureStarted = true
        var autoPlaybackStarted = true
        var foreground = true
        val captureStartedCallbacks = mutableListOf<() -> Unit>()
        val playbackStartedCallbacks = mutableListOf<() -> Unit>()
        override suspend fun capture(maxSeconds: Int): ByteArray? {
            captureCalls++
            return captures.receive()
        }
        override suspend fun capture(maxSeconds: Int, onStarted: () -> Unit): ByteArray? {
            captureCalls++
            captureStartedCallbacks += onStarted
            if (autoCaptureStarted) onStarted()
            return captures.receive()
        }
        override suspend fun playSpeech(audio: ProtectedAnnotationAudio): Boolean {
            speechCalls++
            speechStarted.send(Unit)
            return speechResults.receive()
        }
        override suspend fun playSpeech(audio: ProtectedAnnotationAudio, onStarted: () -> Unit): Boolean {
            speechCalls++
            playbackStartedCallbacks += onStarted
            if (autoPlaybackStarted) onStarted()
            speechStarted.send(Unit)
            return speechResults.receive()
        }
        override fun stopAudio() { stopCalls++ }
        override fun finishCapture() { captures.trySend(null) }
    }

    private class VoiceApi : PhotoHouseApi {
        override val assistantEnabled = true
        var transcriptionCalls = 0
        var assistantTurnCalls = 0
        var speechCalls = 0
        var playbackTracking = true
        val playbackOutcomes = mutableListOf<Pair<String, String>>()
        var responseKind = "results"
        var responseItems = listOf(testAsset())
        val transcriptionIds = mutableListOf<String>()
        val turnParentIds = mutableListOf<String?>()
        var transcriptionGate: CompletableDeferred<Unit>? = null
        var transcriptionFailure: ApiFailure? = null
        var turnFailure: ApiFailure? = null
        var speechFailure: ApiFailure? = null
        var responseContext: kotlinx.serialization.json.JsonObject? = visibleContext()
        override suspend fun assistantCapabilities(token: Bearer, library: String) = AssistantCapabilities(true, true, true, true, 30)
        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript {
            transcriptionCalls++
            transcriptionGate?.await()
            transcriptionIds += requestId
            transcriptionFailure?.let { throw it }
            return AssistantTranscript("find the beach", "en", AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        }
        override suspend fun assistantTurn(
            token: Bearer, library: String, text: String, context: kotlinx.serialization.json.JsonObject?, requestId: String,
            parentRequestId: String?,
        ): AssistantTurn {
            assistantTurnCalls++
            turnParentIds += parentRequestId
            turnFailure?.let { throw it }
            return AssistantTurn(
                responseKind, "Found one beach photo.", responseContext,
                kotlinx.serialization.json.buildJsonObject { }, responseItems, responseItems.size, false, null,
                AssistantRequestReceipt(requestId, "enabled", "succeeded"),
            )
        }
        override suspend fun assistantSpeech(
            token: Bearer, library: String, context: kotlinx.serialization.json.JsonObject?, language: String,
            requestId: String, parentRequestId: String?,
        ): AssistantSpeechResult {
            speechCalls++
            speechFailure?.let { throw it }
            val data = syntheticAnnotationWav()
            return AssistantSpeechResult(data, AssistantRequestReceipt(requestId, "enabled", "succeeded", playbackTracking = playbackTracking))
        }
        override suspend fun assistantPlaybackOutcome(token: Bearer, library: String, requestId: String, outcome: String) {
            playbackOutcomes += requestId to outcome
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

    companion object {
        private fun visibleContext() = buildJsonObject {
            put("visible_ids", buildJsonArray { add(kotlinx.serialization.json.JsonPrimitive("1")) })
        }

        private fun testAsset() = Asset("1", "image", 640, 480, null, null, "/assets/1/thumbnail?library=family")

        private fun wav(): ByteArray = ByteArray(16_046).also { bytes ->
            "RIFF".toByteArray().copyInto(bytes)
            "WAVE".toByteArray().copyInto(bytes, 8)
        }
    }
}
