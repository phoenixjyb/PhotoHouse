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

    private suspend fun TestScope.completedSection(fixture: Fixture, count: Int = 3): AssistantMemoryVoiceSelection {
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemorySegmentReadingAvailable = true
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        fixture.workspaceApi.memorySegmentHandler = { _, _, _, _, segment, _, request ->
            AssistantMemorySegmentSpeechResult(syntheticAnnotationWav(),
                AssistantRequestReceipt(request, "enabled", "succeeded", playbackTracking = true), segment, count)
        }
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemorySegmentReadingCapabilities()); runCurrent()
        assertTrue(fixture.store.sendAssistantText("find saved memories")); runCurrent()
        assertNull(fixture.store.assistantMemoryVoiceSelection(0))
        assertTrue(fixture.store.loadAssistantMemorySegment(0, 0)); runCurrent()
        assertNull(fixture.store.assistantMemoryVoiceSelection(0))
        val audio = requireNotNull(fixture.store.state.value.assistant?.speechAudio)
        assertTrue(fixture.store.reportAssistantPlaybackOutcome(audio, "completed"))
        return requireNotNull(fixture.store.assistantMemoryVoiceSelection(0))
    }

    @Test fun explicitReadingVoiceRequestsOneNextSegmentAndRelistensOnlyAfterActualCompletion() = runTest {
        val f = fixture(activatePrivate = true)
        val selection = completedSection(f)
        assertTrue(f.driver.canStartMemoryReading(selection))
        assertEquals(0, f.platform.captureCalls)
        assertTrue(f.driver.startMemoryReading(selection)); runCurrent()
        assertEquals(1, f.platform.captureCalls)
        assertEquals(listOf(0), f.workspaceApi.memorySegmentIndices)
        assertEquals(1, f.workspaceApi.submitCalls)
        assertEquals(VoiceSessionPhase.LISTENING, f.driver.state.value.phase)
        assertTrue(f.driver.state.value.readingContinuation)

        f.photoApi.transcriptText = "继续朗读。"
        f.platform.captures.send(wav()); runCurrent()
        assertEquals(listOf(0, 1), f.workspaceApi.memorySegmentIndices)
        assertEquals(VoiceSessionPhase.SPEAKING, f.driver.state.value.phase)
        assertEquals(1, f.platform.captureCalls)
        assertEquals(1, f.platform.speechCalls)
        assertEquals(1, f.workspaceApi.submitCalls)
        assertEquals(0, f.workspaceApi.speechCalls)
        assertEquals(0, f.workspaceApi.memoryOpeningSpeechCalls)
        assertEquals(0, f.photoApi.v1TurnCalls)
        assertNull(f.store.state.value.assistant?.transcript)
        assertNull(f.store.state.value.assistant?.confirmedTranscriptRequestId)
        assertEquals(listOf<String?>(null), f.workspaceApi.parentIds)

        f.platform.speechResults.send(true); runCurrent()
        assertEquals(VoiceSessionPhase.LISTENING, f.driver.state.value.phase)
        assertEquals(2, f.platform.captureCalls)
        f.photoApi.transcriptText = "READ THE NEXT PART!"
        f.platform.captures.send(wav()); runCurrent()
        assertEquals(listOf(0, 1, 2), f.workspaceApi.memorySegmentIndices)
        assertEquals(2, f.platform.captureCalls)
        f.platform.speechResults.send(true); runCurrent()
        assertEquals(VoiceSessionPhase.PAUSED, f.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.READING_FINISHED, f.driver.state.value.reason)
        assertFalse(f.driver.state.value.readingContinuation)
        assertNull(f.store.state.value.assistant?.speechMemorySegmentProgress)
        assertEquals(2, f.platform.captureCalls)
        assertEquals(1, f.workspaceApi.submitCalls)

        assertTrue(f.driver.resume()); runCurrent()
        f.photoApi.transcriptText = "continue reading"
        f.platform.captures.send(wav()); runCurrent()
        assertEquals(VoiceSessionStopReason.READING_NEEDS_SELECTION, f.driver.state.value.reason)
        assertEquals(listOf(0, 1, 2), f.workspaceApi.memorySegmentIndices)
        assertEquals(1, f.workspaceApi.submitCalls)
        f.driver.close()
    }

    @Test fun permissionSelectionCannotFollowAnOtherwiseIdenticalManualReplay() = runTest {
        val f = fixture(activatePrivate = true)
        val old = completedSection(f)
        f.store.clearAssistantSpeech()
        assertTrue(f.store.loadAssistantMemorySegment(0, 0)); runCurrent()
        assertTrue(f.store.reportAssistantPlaybackOutcome(requireNotNull(f.store.state.value.assistant?.speechAudio), "completed"))
        val replacement = requireNotNull(f.store.assistantMemoryVoiceSelection(0))
        assertEquals(old.progress, replacement.progress)
        assertFalse(f.driver.canStartMemoryReading(old))
        assertFalse(f.driver.startMemoryReading(old))
        assertEquals(0, f.platform.captureCalls)
        assertTrue(f.driver.startMemoryReading(replacement)); runCurrent()
        assertEquals(1, f.platform.captureCalls)
        f.driver.end(); f.driver.close()
    }

    @Test fun readingPauseFencesLateAsrAndResumeNeverRestoresReadingIntent() = runTest {
        val f = fixture(activatePrivate = true)
        val selection = completedSection(f)
        val gate = CompletableDeferred<Unit>()
        f.photoApi.transcriptionGate = gate
        f.photoApi.transcriptText = "继续读"
        assertTrue(f.driver.startMemoryReading(selection)); runCurrent()
        f.platform.captures.send(wav()); runCurrent()
        assertEquals(VoiceSessionPhase.TRANSCRIBING, f.driver.state.value.phase)
        assertTrue(f.driver.pause()); runCurrent()
        assertNull(f.store.state.value.assistant?.speechMemorySegmentProgress)
        gate.complete(Unit); runCurrent()
        assertEquals(listOf(0), f.workspaceApi.memorySegmentIndices)
        assertEquals(1, f.workspaceApi.submitCalls)
        assertNull(f.store.state.value.assistant?.transcript)
        assertTrue(f.driver.resume()); runCurrent()
        f.photoApi.transcriptionGate = null
        f.photoApi.transcriptText = "continue reading"
        f.platform.captures.send(wav()); runCurrent()
        assertEquals(VoiceSessionStopReason.READING_NEEDS_SELECTION, f.driver.state.value.reason)
        assertEquals(2, f.platform.captureCalls)
        assertEquals(1, f.workspaceApi.submitCalls)
        f.driver.close()
    }

    @Test fun readingEndFencesLateSynthesisWithoutClearingANewerManualOwner() = runTest {
        val f = fixture(activatePrivate = true)
        val selection = completedSection(f)
        val gate = CompletableDeferred<Unit>()
        var lateBytes: ByteArray? = null
        f.workspaceApi.memorySegmentHandler = { _, _, _, _, segment, _, request ->
            withContext(NonCancellable) { gate.await() }
            val bytes = syntheticAnnotationWav().also { lateBytes = it }
            AssistantMemorySegmentSpeechResult(bytes,
                AssistantRequestReceipt(request, "enabled", "succeeded", playbackTracking = true), segment, 3)
        }
        f.photoApi.transcriptText = "继续朗读"
        assertTrue(f.driver.startMemoryReading(selection)); runCurrent()
        f.platform.captures.send(wav()); runCurrent()
        assertEquals(VoiceSessionPhase.SPEAKING, f.driver.state.value.phase)
        assertTrue(f.driver.end()); runCurrent()
        assertNull(f.store.state.value.assistant?.speechMemorySegmentProgress)
        f.workspaceApi.memorySegmentHandler = { _, _, _, _, segment, _, request ->
            AssistantMemorySegmentSpeechResult(syntheticAnnotationWav(),
                AssistantRequestReceipt(request, "enabled", "succeeded", playbackTracking = true), segment, 3)
        }
        assertTrue(f.store.loadAssistantMemorySegment(0, 0)); runCurrent()
        val newAudio = requireNotNull(f.store.state.value.assistant?.speechAudio)
        gate.complete(Unit); runCurrent()
        assertSame(newAudio, f.store.state.value.assistant?.speechAudio)
        assertTrue(requireNotNull(lateBytes).all { it == 0.toByte() })
        assertEquals(VoiceSessionPhase.ENDED, f.driver.state.value.phase)
        assertEquals(0, f.platform.speechCalls)
        assertEquals(1, f.platform.captureCalls)
        f.store.clearAssistantSpeech(); f.driver.close()
    }

    @Test fun lateEndedReadingPlayerCannotRecaptureOrStopANewerGeneralSession() = runTest {
        val f = fixture(activatePrivate = true)
        val selection = completedSection(f)
        f.platform.ignoreSpeechCancellation = true
        f.photoApi.transcriptText = "continue reading"
        assertTrue(f.driver.startMemoryReading(selection)); runCurrent()
        f.platform.captures.send(wav()); runCurrent()
        assertEquals(VoiceSessionPhase.SPEAKING, f.driver.state.value.phase)
        assertTrue(f.driver.end()); runCurrent()
        assertTrue(f.driver.start()); runCurrent()
        val stopCalls = f.platform.stopAudioCalls
        assertEquals(2, f.platform.captureCalls)
        f.platform.speechResults.send(true); runCurrent()
        assertEquals(VoiceSessionPhase.LISTENING, f.driver.state.value.phase)
        assertFalse(f.driver.state.value.readingContinuation)
        assertEquals(2, f.platform.captureCalls)
        assertEquals(stopCalls, f.platform.stopAudioCalls)
        assertEquals(listOf(0, 1), f.workspaceApi.memorySegmentIndices)
        assertEquals(1, f.workspaceApi.submitCalls)
        f.driver.close()
    }

    @Test fun readingCapabilityLossAndSourceReplacementStopListening() = runTest {
        for (replace in listOf(false, true)) {
            val f = fixture(activatePrivate = true)
            val selection = completedSection(f)
            assertTrue(f.driver.startMemoryReading(selection)); runCurrent()
            if (replace) {
                assertTrue(f.store.sendAssistantText("another source")); runCurrent()
            } else {
                f.workspaceApi.savedMemorySegmentReadingAvailable = false
                assertTrue(requireNotNull(f.store.assistantWorkspaceCoordinator).refreshSavedMemorySegmentReadingCapabilities()); runCurrent()
            }
            assertEquals(VoiceSessionPhase.PAUSED, f.driver.state.value.phase)
            assertEquals(VoiceSessionStopReason.READING_UNAVAILABLE, f.driver.state.value.reason)
            assertFalse(f.driver.state.value.microphoneActive)
            assertEquals(1, f.platform.captureCalls)
            assertNull(f.store.state.value.assistant?.speechMemorySegmentProgress)
            assertFalse(f.driver.startMemoryReading(selection))
            f.driver.close()
        }
    }

    @Test fun ordinaryReadingQuestionClearsTheAnchorAndUsesOnlyItsOwnAsrParent() = runTest {
        val f = fixture(activatePrivate = true)
        val selection = completedSection(f)
        assertTrue(f.driver.startMemoryReading(selection)); runCurrent()
        f.photoApi.transcriptText = "find garden photos"
        f.platform.captures.send(wav()); runCurrent()
        assertEquals(2, f.workspaceApi.submitCalls)
        assertEquals("find garden photos", f.workspaceApi.texts.last())
        assertEquals(f.photoApi.transcriptionIds.single(), f.workspaceApi.parentIds.last())
        assertFalse(f.driver.state.value.readingContinuation)
        assertNull(f.store.state.value.assistant?.speechMemorySegmentProgress)
        assertEquals(listOf(0), f.workspaceApi.memorySegmentIndices)
        assertEquals(1, f.platform.captureCalls)
        f.driver.close()
    }

    @Test fun changedCountAndPlaybackFailureCannotRestartReadingCapture() = runTest {
        for (badCount in listOf(true, false)) {
            val f = fixture(activatePrivate = true)
            val selection = completedSection(f)
            if (badCount) f.workspaceApi.memorySegmentHandler = { _, _, _, _, segment, _, request ->
                AssistantMemorySegmentSpeechResult(syntheticAnnotationWav(),
                    AssistantRequestReceipt(request, "enabled", "succeeded", playbackTracking = true), segment, 4)
            }
            f.photoApi.transcriptText = "continue reading"
            assertTrue(f.driver.startMemoryReading(selection)); runCurrent()
            f.platform.captures.send(wav()); runCurrent()
            if (!badCount) { f.platform.speechResults.send(false); runCurrent() }
            assertEquals(if (badCount) VoiceSessionStopReason.READING_UNAVAILABLE else VoiceSessionStopReason.SPEECH_FAILED,
                f.driver.state.value.reason)
            assertEquals(VoiceSessionPhase.PAUSED, f.driver.state.value.phase)
            assertNull(f.store.state.value.assistant?.speechAudio)
            assertNull(f.store.state.value.assistant?.speechMemorySegmentProgress)
            assertEquals(1, f.platform.captureCalls)
            assertEquals(1, f.workspaceApi.submitCalls)
            f.driver.close()
        }
    }

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

    @Test fun spokenFollowupAfterFreshSavedMemorySearchCarriesMemoryParent() = runTest {
        val fixture = fixture(activatePrivate = true)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryFollowupAvailable = true
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemoryFollowupCapabilities()); runCurrent()
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        assertTrue(fixture.store.sendAssistantText("Find saved memories")); runCurrent()
        val memoryRequest = fixture.workspaceApi.requestIds.last()
        val memoryRevision = fixture.workspaceApi.revision

        fixture.photoApi.transcriptText = "what is the first saved memory about"
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(2, fixture.workspaceApi.submitCalls)
        assertEquals(memoryRequest, fixture.workspaceApi.memoryParents.last()?.requestId)
        assertEquals(memoryRevision, fixture.workspaceApi.memoryParents.last()?.revision)
        assertEquals(fixture.photoApi.transcriptionIds.single(), fixture.workspaceApi.parentIds.last())
        assertEquals(fixture.photoApi.transcriptionTexts.single(), fixture.workspaceApi.texts.last())
        fixture.driver.close()
    }

    @Test fun freshReadOpeningActionUsesSavedMemorySpeechAndRelistensOnlyAfterPlaybackCompletes() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryActionsAvailable = true
        fixture.workspaceApi.savedMemoryReadingAvailable = true
        fixture.workspaceApi.resultFactory = { request -> savedMemoryResult(request).copy(
            memoryAction = AssistantSavedMemoryAction("read_opening", 0)) }
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.state.value.savedMemoryActionsAvailable)
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start()); runCurrent()
        fixture.platform.speechStarted.receive()
        assertEquals(1, fixture.workspaceApi.memoryOpeningSpeechCalls)
        assertEquals(0, fixture.workspaceApi.speechCalls)
        assertEquals(VoiceSessionPhase.SPEAKING, fixture.driver.state.value.phase)
        assertEquals(1, fixture.platform.captureCalls)
        fixture.platform.speechResults.send(true)
        runCurrent()
        assertEquals(VoiceSessionPhase.LISTENING, fixture.driver.state.value.phase)
        assertEquals(2, fixture.platform.captureCalls)
        fixture.driver.end()
        fixture.driver.close()
    }

    @Test fun pausingDuringPendingOpeningFetchCancelsOwnedSpeechRequest() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryActionsAvailable = true
        fixture.workspaceApi.savedMemoryReadingAvailable = true
        fixture.workspaceApi.resultFactory = { request -> savedMemoryResult(request).copy(
            memoryAction = AssistantSavedMemoryAction("read_opening", 0)) }
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
        val speechStarted = CompletableDeferred<Unit>()
        val pendingSpeech = CompletableDeferred<AssistantSpeechResult>()
        fixture.workspaceApi.memoryOpeningHandler = { _, _, _, _, _, _ ->
            speechStarted.complete(Unit)
            pendingSpeech.await()
        }
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start()); runCurrent()
        speechStarted.await()
        assertTrue(fixture.store.state.value.assistant!!.speechBusy)
        assertEquals(VoiceSessionPhase.SPEAKING, fixture.driver.state.value.phase)
        assertTrue(fixture.driver.pause())
        runCurrent()

        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertFalse("Pause cancels the in-flight workspace opening request", fixture.store.state.value.assistant!!.speechBusy)
        assertNull(fixture.store.state.value.assistant?.speechAudio)
        assertEquals(0, fixture.platform.speechCalls)
        assertEquals(1, fixture.platform.captureCalls)
        fixture.driver.close()
    }

    @Test fun freshOpenActionInstallsSourceBoundHandoffThenEndsVoice() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        val card = savedMemoryResult("33333333-3333-4333-8333-333333333333").memoryCards.single()
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryActionsAvailable = true
        fixture.workspaceApi.savedMemoryReaderAvailable = true
        fixture.workspaceApi.readerPayload = SavedMemoryReaderPayload.Story(SavedMemoryStory(
            id = card.id, libraryId = "family", revision = 2, createdAt = 0, updatedAt = 0, canEdit = false,
            selectionRevision = "a".repeat(64), title = card.title, theme = "family", language = "en",
            items = listOf(MemoryStoryAsset(testAsset(), emptyList())),
            chapters = listOf(SavedMemoryStoryChapter("chapter-1", "Garden", "A day together.", listOf("1"), emptyList())),
            questions = emptyList(),
        ))
        fixture.workspaceApi.resultFactory = { request -> savedMemoryResult(request).copy(
            memoryAction = AssistantSavedMemoryAction("open", 0)) }
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemoryReaderCapabilities()); runCurrent()
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start()); runCurrent()
        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.USER_ENDED, fixture.driver.state.value.reason)
        val handoff = requireNotNull(coordinator.state.value.memoryReaderHandoff)
        assertEquals(0, handoff.ordinal)
        assertEquals(coordinator.state.value.currentTurn?.requestId, handoff.turnId)
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(0, fixture.platform.speechCalls)
        fixture.driver.close()
    }

    @Test fun losingReadingCapabilityDuringActionPlaybackCancelsWithoutRelistening() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryActionsAvailable = true
        fixture.workspaceApi.savedMemoryReadingAvailable = true
        fixture.workspaceApi.resultFactory = { request -> savedMemoryResult(request).copy(
            memoryAction = AssistantSavedMemoryAction("read_opening", 0)) }
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
        fixture.platform.captures.send(wav())
        assertTrue(fixture.driver.start()); runCurrent()
        fixture.platform.speechStarted.receive()
        assertEquals(VoiceSessionPhase.SPEAKING, fixture.driver.state.value.phase)
        assertEquals(0, fixture.store.state.value.assistant?.speechMemoryOpeningOrdinal)
        val audio = requireNotNull(fixture.platform.lastSpeechAudio)

        fixture.workspaceApi.savedMemoryReadingAvailable = false
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
        assertFalse(coordinator.state.value.savedMemoryReadingAvailable)
        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertTrue(audio.isClosed)
        assertEquals(1, fixture.platform.captureCalls)
        fixture.driver.close()
    }

    @Test fun savedMemoryOpeningEndsVoiceBeforePostAndStopCancelsPlaybackWithoutRelistening() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryReadingAvailable = true
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
        assertTrue(fixture.store.sendAssistantText("find saved memories")); runCurrent()
        assertTrue(fixture.driver.start()); runCurrent()
        assertEquals(VoiceSessionPhase.LISTENING, fixture.driver.state.value.phase)
        assertTrue(fixture.store.canReadAssistantMemoryOpening(0))
        fixture.workspaceApi.memoryOpeningHandler = { _, _, _, _, _, speechRequestId ->
            assertEquals("voice must end before opening speech POST", VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
            AssistantSpeechResult(syntheticAnnotationWav(), AssistantRequestReceipt(speechRequestId, "enabled", "succeeded"))
        }
        fixture.driver.end()
        assertTrue(fixture.store.loadAssistantMemoryOpening(0))
        runCurrent()
        assertEquals(1, fixture.workspaceApi.memoryOpeningSpeechCalls)
        assertEquals(0, fixture.workspaceApi.speechCalls)
        assertEquals("ending voice does not relisten", 1, fixture.platform.captureCalls)
        assertEquals(0, fixture.platform.speechCalls)
        assertNotNull(fixture.store.state.value.assistant?.speechAudio)
        fixture.store.clearAssistantSpeech()
        assertNull(fixture.store.state.value.assistant?.speechAudio)
        assertNull(fixture.store.state.value.assistant?.speechMemoryOpeningOrdinal)
        assertEquals("memory speech does not relisten", 1, fixture.platform.captureCalls)
        fixture.driver.close()
    }

    @Test fun memorySegmentContinuationWaitsForPlaybackCompletionAndStopClearsEphemeralProgress() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemorySegmentReadingAvailable = true
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemorySegmentReadingCapabilities()); runCurrent()
        assertTrue(fixture.store.sendAssistantText("find saved memories")); runCurrent()

        assertTrue(fixture.store.canReadAssistantMemorySegment(0, 0))
        assertTrue(fixture.store.loadAssistantMemorySegment(0, 0))
        runCurrent()
        val firstAudio = requireNotNull(fixture.store.state.value.assistant?.speechAudio)
        assertEquals(listOf(0), fixture.workspaceApi.memorySegmentIndices)
        assertEquals(2, fixture.store.state.value.assistant?.speechMemorySegmentProgress?.segmentCount)
        assertNull(fixture.store.state.value.assistant?.speechMemorySegmentProgress?.completedSegmentIndex)
        assertFalse("the next explicit tap stays locked until player completion", fixture.store.canReadAssistantMemorySegment(0, 1))

        assertTrue(fixture.store.reportAssistantPlaybackOutcome(firstAudio, "completed"))
        assertEquals(0, fixture.store.state.value.assistant?.speechMemorySegmentProgress?.completedSegmentIndex)
        assertTrue(fixture.store.canReadAssistantMemorySegment(0, 1))
        assertTrue(fixture.store.loadAssistantMemorySegment(0, 1))
        runCurrent()
        val secondAudio = requireNotNull(fixture.store.state.value.assistant?.speechAudio)
        assertEquals(listOf(0, 1), fixture.workspaceApi.memorySegmentIndices)
        assertFalse("server count caps continuation", fixture.store.canReadAssistantMemorySegment(0, 2))
        assertTrue(fixture.store.reportAssistantPlaybackOutcome(secondAudio, "completed"))
        assertEquals(1, fixture.store.state.value.assistant?.speechMemorySegmentProgress?.completedSegmentIndex)
        assertTrue("completed source can be explicitly restarted from its first segment",
            fixture.store.canReadAssistantMemorySegment(0, 0))
        assertTrue(fixture.store.loadAssistantMemorySegment(0, 0))
        runCurrent()
        assertEquals(listOf(0, 1, 0), fixture.workspaceApi.memorySegmentIndices)
        assertEquals(0, fixture.store.state.value.assistant?.speechMemorySegmentProgress?.segmentIndex)
        fixture.store.clearAssistantSpeech()
        assertNull(fixture.store.state.value.assistant?.speechMemorySegmentProgress)
        assertTrue("Stop resets this ephemeral reader to its first explicit segment",
            fixture.store.canReadAssistantMemorySegment(0, 0))
        fixture.driver.close()
    }

    @Test fun changedSegmentCapabilityCancelsPendingAudioAndClearsProgress() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemorySegmentReadingAvailable = true
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemorySegmentReadingCapabilities()); runCurrent()
        assertTrue(fixture.store.sendAssistantText("find saved memories")); runCurrent()
        val pendingSpeech = CompletableDeferred<AssistantMemorySegmentSpeechResult>()
        fixture.workspaceApi.memorySegmentHandler = { _, _, _, _, _, _, speechRequestId ->
            pendingSpeech.await().also { assertEquals(speechRequestId, it.receipt.requestId) }
        }
        assertTrue(fixture.store.loadAssistantMemorySegment(0, 0)); runCurrent()
        assertNotNull(fixture.store.state.value.assistant?.speechMemorySegmentProgress)
        fixture.workspaceApi.savedMemorySegmentReadingAvailable = false
        assertTrue(coordinator.refreshSavedMemorySegmentReadingCapabilities()); runCurrent()
        assertFalse(coordinator.state.value.savedMemorySegmentReadingAvailable)
        assertNull(fixture.store.state.value.assistant?.speechMemorySegmentProgress)
        assertNull(fixture.store.state.value.assistant?.speechAudio)
        fixture.driver.close()
    }

    @Test fun continuationRefusesChangedCountForTheFrozenSourceBinding() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemorySegmentReadingAvailable = true
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        fixture.workspaceApi.memorySegmentHandler = { _, _, _, _, segment, _, request ->
            AssistantMemorySegmentSpeechResult(syntheticAnnotationWav(),
                AssistantRequestReceipt(request, "enabled", "succeeded", playbackTracking = true),
                segment, if (segment == 0) 2 else 3)
        }
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemorySegmentReadingCapabilities()); runCurrent()
        assertTrue(fixture.store.sendAssistantText("find saved memories")); runCurrent()
        assertTrue(fixture.store.loadAssistantMemorySegment(0, 0)); runCurrent()
        val firstAudio = requireNotNull(fixture.store.state.value.assistant?.speechAudio)
        assertTrue(fixture.store.reportAssistantPlaybackOutcome(firstAudio, "completed"))
        assertTrue(fixture.store.loadAssistantMemorySegment(0, 1)); runCurrent()
        assertNull("changed count is refused before audio is exposed", fixture.store.state.value.assistant?.speechAudio)
        assertNull(fixture.store.state.value.assistant?.speechMemorySegmentProgress)
        assertEquals(listOf(0, 1), fixture.workspaceApi.memorySegmentIndices)
        assertEquals(0, fixture.workspaceApi.memoryOpeningSpeechCalls)
        fixture.driver.close()
    }

    @Test fun savedMemoryOpeningDiscardsLateAudioAfterNewTurnAndHidesRecoveredOrHistoryTurns() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryReadingAvailable = true
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
        assertTrue(fixture.store.sendAssistantText("first memory search")); runCurrent()
        assertTrue(fixture.store.canReadAssistantMemoryOpening(0))
        val late = CompletableDeferred<AssistantSpeechResult>()
        fixture.workspaceApi.memoryOpeningHandler = { _, _, _, _, _, _ -> late.await() }
        assertTrue(fixture.store.loadAssistantMemoryOpening(0)); runCurrent()
        assertEquals(1, fixture.workspaceApi.memoryOpeningSpeechCalls)
        fixture.workspaceApi.resultFactory = ::result
        assertTrue(fixture.store.sendAssistantText("new search")); runCurrent()
        late.complete(AssistantSpeechResult(syntheticAnnotationWav(), AssistantRequestReceipt(
            "55555555-5555-4555-8555-555555555555", "enabled", "succeeded")))
        runCurrent()
        assertNull(fixture.store.state.value.assistant?.speechAudio)
        assertFalse(fixture.store.canReadAssistantMemoryOpening(0))

        fixture.workspaceApi.submitHandler = { id, request, _, _ ->
            fixture.workspaceApi.latestRequestId = request
            fixture.workspaceApi.completed(id, request, fixture.workspaceApi.revision, recovered = true)
        }
        assertTrue(fixture.store.sendAssistantText("recovered search")); runCurrent()
        assertFalse(fixture.store.canReadAssistantMemoryOpening(0))
        val calls = fixture.workspaceApi.memoryOpeningSpeechCalls
        fixture.workspaceApi.latestRequestId = null
        assertTrue(coordinator.openThread(threadId)); runCurrent()
        assertNull(coordinator.state.value.currentTurn)
        assertFalse(fixture.store.canReadAssistantMemoryOpening(0))
        assertEquals(calls, fixture.workspaceApi.memoryOpeningSpeechCalls)
        fixture.driver.close()
    }

    @Test fun duplicateSavedMemoryOpeningTapDoesNotCancelOrRepeatInFlightRequest() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryReadingAvailable = true
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
        assertTrue(fixture.store.sendAssistantText("find saved memories")); runCurrent()
        val pendingSpeech = CompletableDeferred<AssistantSpeechResult>()
        fixture.workspaceApi.memoryOpeningHandler = { _, _, _, _, _, _ -> pendingSpeech.await() }

        assertTrue(fixture.store.loadAssistantMemoryOpening(0))
        assertFalse(fixture.store.loadAssistantMemoryOpening(0))
        runCurrent()
        assertEquals(1, fixture.workspaceApi.memoryOpeningSpeechCalls)
        assertTrue(fixture.store.state.value.assistant!!.speechBusy)
        fixture.store.clearAssistantMemoryOpeningSpeech()
        runCurrent()
        assertEquals(1, fixture.workspaceApi.memoryOpeningSpeechCalls)
        assertFalse(fixture.store.state.value.assistant!!.speechBusy)
        fixture.driver.close()
    }

    @Test fun lateSavedMemoryOpeningCallbackCannotRetargetNewTurnAtSameOrdinal() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryReadingAvailable = true
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
        assertTrue(fixture.store.sendAssistantText("first memory search")); runCurrent()
        val oldTurn = requireNotNull(coordinator.state.value.currentTurn)
        val oldCard = requireNotNull(oldTurn.result).memoryCards.single()
        val oldDetail = requireNotNull(coordinator.state.value.detail)
        assertTrue(isCurrentFreshMemoryOpeningSelection(oldTurn, 0, oldCard, oldTurn, oldDetail))

        assertTrue(fixture.store.sendAssistantText("new memory search")); runCurrent()
        val live = coordinator.state.value
        assertFalse(isCurrentFreshMemoryOpeningSelection(oldTurn, 0, oldCard, live.currentTurn, live.detail))
        assertFalse(fixture.store.loadAssistantMemoryOpening(0, oldTurn.requestId, oldTurn.revision))
        assertEquals(0, fixture.workspaceApi.memoryOpeningSpeechCalls)
        fixture.driver.close()
    }

    @Test fun losingSavedMemoryReadingCapabilityDuringPlaybackStopsAndWipesAudio() = runTest {
        val fixture = fixture(activatePrivate = true)
        val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
        val playbackBytes = syntheticAnnotationWav()
        fixture.workspaceApi.savedMemoryCardsAvailable = true
        fixture.workspaceApi.savedMemoryReadingAvailable = true
        fixture.workspaceApi.resultFactory = ::savedMemoryResult
        assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
        assertTrue(fixture.store.sendAssistantText("find saved memories")); runCurrent()
        fixture.workspaceApi.memoryOpeningHandler = { _, _, _, _, _, requestId ->
            AssistantSpeechResult(playbackBytes, AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        }

        assertTrue(fixture.store.loadAssistantMemoryOpening(0)); runCurrent()
        val audio = requireNotNull(fixture.store.state.value.assistant?.speechAudio)
        assertFalse(audio.isClosed)
        assertEquals(0, fixture.platform.speechCalls)
        fixture.workspaceApi.savedMemoryReadingAvailable = false
        assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()

        assertTrue(audio.isClosed)
        assertTrue(playbackBytes.all { it == 0.toByte() })
        assertNull(fixture.store.state.value.assistant?.speechAudio)
        assertNull(fixture.store.state.value.assistant?.speechMemoryOpeningOrdinal)
        assertFalse(fixture.store.state.value.assistant?.speechBusy ?: true)
        assertEquals(0, fixture.platform.captureCalls)
        assertEquals(0, fixture.platform.speechCalls)
        fixture.driver.close()
    }

    @Test fun refreshingOpeningDependenciesStopsAudioUntilReadingIsRequalified() = runTest {
        for (probe in listOf("workspace", "cards", "reader", "speech")) {
            val fixture = fixture(activatePrivate = true)
            val coordinator = requireNotNull(fixture.store.assistantWorkspaceCoordinator)
            fixture.workspaceApi.savedMemoryCardsAvailable = true
            fixture.workspaceApi.savedMemoryReadingAvailable = true
            fixture.workspaceApi.resultFactory = ::savedMemoryResult
            assertTrue(coordinator.refreshSavedMemoryCardsCapabilities()); runCurrent()
            assertTrue(coordinator.refreshSavedMemoryReadingCapabilities()); runCurrent()
            assertTrue(fixture.store.sendAssistantText("find saved memories")); runCurrent()
            assertTrue(fixture.store.loadAssistantMemoryOpening(0)); runCurrent()
            val audio = requireNotNull(fixture.store.state.value.assistant?.speechAudio)
            val started = when (probe) {
                "workspace" -> coordinator.refreshCapabilities()
                "cards" -> coordinator.refreshSavedMemoryCardsCapabilities()
                "reader" -> coordinator.refreshSavedMemoryReaderCapabilities()
                else -> coordinator.refreshSavedMemorySpeechCapabilities()
            }
            assertTrue(started); runCurrent()
            assertTrue("$probe must stop an existing player while availability is rechecked", audio.isClosed)
            assertNull(fixture.store.state.value.assistant?.speechAudio)
            assertFalse(coordinator.state.value.savedMemoryReadingAvailable)
            assertFalse(fixture.store.canReadAssistantMemoryOpening(0))
            assertEquals(0, fixture.platform.captureCalls)
            fixture.driver.close()
        }
    }

    @Test fun recoveredPrivateTurnPausesBeforeSpeechNavigationOrRelistening() = runTest {
        val fixture = fixture(activatePrivate = true, replySpeech = true)
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
        assertEquals(0, fixture.workspaceApi.speechCalls)
        assertEquals(0, opened)
        assertTrue(fixture.store.state.value.assistant!!.turns.last().turn.recovered)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        fixture.driver.close()
    }

    @Test fun privateClarificationAndZeroResultsSpeakOnceThenRelisten() = runTest {
        val replyCases = listOf(
            "clarification" to "Which beach do you mean?",
            "results" to "No photos matched. Try another date.",
        )
        for ((kind, reply) in replyCases) {
            val fixture = fixture(activatePrivate = true, replySpeech = true)
            fixture.workspaceApi.resultFactory = { request ->
                if (kind == "clarification") serverReply(request, kind, reply)
                else serverReply(request, kind, reply, noResults = true)
            }
            fixture.platform.captures.send(wav())

            assertTrue(fixture.driver.start())
            runCurrent()
            fixture.platform.speechStarted.receive()

            assertEquals(1, fixture.workspaceApi.speechCalls)
            assertEquals(0, fixture.photoApi.speechCalls)
            assertEquals(1, fixture.workspaceApi.speechTurnIds.size)
            assertEquals(fixture.workspaceApi.requestIds.single(), fixture.workspaceApi.speechTurnIds.single())
            assertEquals(threadId, fixture.workspaceApi.speechThreadIds.single())
            assertEquals(fixture.workspaceApi.revision, fixture.workspaceApi.speechRevisions.single())
            assertEquals(VoiceSessionPhase.SPEAKING, fixture.driver.state.value.phase)
            assertEquals(reply, fixture.driver.state.value.replyText)

            fixture.platform.speechResults.send(true)
            runCurrent()
            assertEquals(VoiceSessionPhase.LISTENING, fixture.driver.state.value.phase)
            assertEquals(2, fixture.platform.captureCalls)
            assertEquals(1, fixture.workspaceApi.submitCalls)
            fixture.driver.end()
            fixture.driver.close()
        }
    }

    @Test fun privateUnsupportedReplySpeaksOnceThenPauses() = runTest {
        val fixture = fixture(activatePrivate = true, replySpeech = true)
        fixture.workspaceApi.resultFactory = { request ->
            serverReply(request, "unsupported", "I can only help search photos right now.")
        }
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start())
        runCurrent()
        fixture.platform.speechStarted.receive()
        assertEquals(1, fixture.workspaceApi.speechCalls)
        assertEquals("I can only help search photos right now.", fixture.driver.state.value.replyText)
        assertEquals(VoiceSessionPhase.SPEAKING, fixture.driver.state.value.phase)

        fixture.platform.speechResults.send(true)
        runCurrent()
        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.REVIEW_REQUIRED, fixture.driver.state.value.reason)
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(1, fixture.workspaceApi.submitCalls)
        assertEquals(0, fixture.photoApi.speechCalls)
        fixture.driver.close()
    }

    @Test fun overLimitPrivateReplyStaysVisibleAndNeverFallsBackToCountSpeech() = runTest {
        val fixture = fixture(activatePrivate = true, replySpeech = true)
        fixture.workspaceApi.resultFactory = { request -> serverReply(request, "clarification", "x".repeat(601)) }
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.REVIEW_REQUIRED, fixture.driver.state.value.reason)
        assertEquals(601, fixture.store.state.value.assistant!!.turns.last().turn.reply.length)
        assertEquals(0, fixture.workspaceApi.speechCalls)
        assertEquals(0, fixture.photoApi.speechCalls)
        assertEquals(1, fixture.platform.captureCalls)
        fixture.driver.close()
    }

    @Test fun freshPrivateMultiResultOpenUsesOnlyExactServerSelectedAsset() = runTest {
        val fixture = fixture(activatePrivate = true)
        fixture.workspaceApi.resultFactory = { request -> multiResultOpen(request) }
        fixture.platform.captures.send(wav())
        fixture.driver.close()
        val opened = mutableListOf<Pair<String, String?>>()
        fixture.driver = AssistantVoiceSessionStore(
            fixture.store, voiceScope(fixture.store), backgroundScope, fixture.platform, "en", { true },
        ) { id, request ->
            val workspace = fixture.store.assistantWorkspaceState.value
            assertEquals(workspace.detail!!.thread.revision, workspace.currentTurn!!.revision)
            assertEquals(fixture.workspaceApi.requestIds.single(), workspace.currentTurn!!.requestId)
            opened += id to request
        }

        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(listOf("2" to fixture.workspaceApi.requestIds.single()), opened)
        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertEquals(0, fixture.workspaceApi.speechCalls)
        assertEquals(0, fixture.photoApi.speechCalls)
        assertEquals(1, fixture.workspaceApi.submitCalls)
        fixture.driver.close()
    }

    @Test fun recoveredPrivateOpenEffectNeverNavigates() = runTest {
        val fixture = fixture(activatePrivate = true)
        fixture.workspaceApi.submitHandler = { _, _, _, _ -> throw ApiFailure(FailureKind.OFFLINE) }
        fixture.workspaceApi.getHandler = { id, request, expectedRevision ->
            fixture.workspaceApi.revision = expectedRevision + 1
            fixture.workspaceApi.latestRequestId = request
            fixture.workspaceApi.completed(id, request, fixture.workspaceApi.revision, recovered = true)
                .copy(result = multiResultOpen(request).copy(recovered = true))
        }
        fixture.platform.captures.send(wav())
        fixture.driver.close()
        var opened = 0
        fixture.driver = AssistantVoiceSessionStore(
            fixture.store, voiceScope(fixture.store), backgroundScope, fixture.platform, "en", { true },
        ) { _, _ -> opened++ }

        assertTrue(fixture.driver.start())
        runCurrent()

        assertEquals(0, opened)
        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        assertEquals(0, fixture.workspaceApi.speechCalls)
        assertEquals(0, fixture.platform.speechCalls)
        fixture.driver.close()
    }

    @Test fun pausingWhilePrivateSpeechIsInFlightCancelsLateAudioAndNeverPlaysIt() = runTest {
        val fixture = fixture(activatePrivate = true, replySpeech = true)
        val ttsStarted = CompletableDeferred<Unit>()
        val releaseTts = CompletableDeferred<Unit>()
        var lateBytes = ByteArray(256) { 0x55.toByte() }
        fixture.workspaceApi.speechHandler = { _, _, _, _, request ->
            ttsStarted.complete(Unit)
            withContext(NonCancellable) { releaseTts.await() }
            AssistantSpeechResult(lateBytes, AssistantRequestReceipt(request, "enabled", "succeeded"))
        }
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start())
        runCurrent()
        assertEquals(VoiceSessionPhase.SPEAKING, fixture.driver.state.value.phase)
        assertEquals(1, fixture.workspaceApi.speechCalls)
        ttsStarted.await()
        assertTrue(fixture.driver.pause())
        runCurrent()
        releaseTts.complete(Unit)
        runCurrent()

        assertTrue(lateBytes.all { it == 0.toByte() })
        assertEquals(0, fixture.platform.speechCalls)
        assertEquals(VoiceSessionPhase.PAUSED, fixture.driver.state.value.phase)
        fixture.driver.close()
    }

    @Test fun losingReplySpeechCapabilityCancelsHeldPrivateAudioAndEndsVoiceSession() = runTest {
        val fixture = fixture(activatePrivate = true, replySpeech = true)
        val ttsStarted = CompletableDeferred<Unit>()
        val releaseTts = CompletableDeferred<Unit>()
        val lateBytes = ByteArray(256) { 0x44.toByte() }
        fixture.workspaceApi.speechHandler = { _, _, _, _, request ->
            ttsStarted.complete(Unit)
            withContext(NonCancellable) { releaseTts.await() }
            AssistantSpeechResult(lateBytes, AssistantRequestReceipt(request, "enabled", "succeeded"))
        }
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start())
        runCurrent()
        ttsStarted.await()
        assertEquals(VoiceSessionPhase.SPEAKING, fixture.driver.state.value.phase)
        assertTrue(fixture.store.state.value.assistant!!.speechBusy)

        fixture.workspaceApi.capabilitiesResponse = fixture.workspaceApi.capabilitiesResponse.copy(replySpeech = false)
        assertTrue(requireNotNull(fixture.store.assistantWorkspaceCoordinator).refreshCapabilities())
        runCurrent()

        val assistant = requireNotNull(fixture.store.state.value.assistant)
        assertFalse(assistant.speechBusy)
        assertNull(assistant.speechAudio)
        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.CONTEXT_CHANGED, fixture.driver.state.value.reason)
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(0, fixture.platform.speechCalls)
        assertEquals(1, fixture.workspaceApi.speechCalls)

        releaseTts.complete(Unit)
        runCurrent()
        assertTrue(lateBytes.all { it == 0.toByte() })
        assertNull(fixture.store.state.value.assistant!!.speechAudio)
        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(0, fixture.platform.speechCalls)
        assertEquals(1, fixture.workspaceApi.speechCalls)
        fixture.driver.close()
    }

    @Test fun newerManualPrivateTurnCancelsHeldReplySpeechWithoutLosingLatestResult() = runTest {
        val fixture = fixture(activatePrivate = true, replySpeech = true)
        val replies = listOf("Earlier answer", "Latest answer")
        var nextReply = 0
        fixture.workspaceApi.resultFactory = { request ->
            serverReply(request, "clarification", replies[nextReply++])
        }
        assertTrue(fixture.store.sendAssistantText("first private question"))
        runCurrent()
        assertEquals("Earlier answer", fixture.store.state.value.assistant!!.turns.last().turn.reply)

        val ttsStarted = CompletableDeferred<Unit>()
        val releaseTts = CompletableDeferred<Unit>()
        val lateBytes = ByteArray(256) { 0x66.toByte() }
        fixture.workspaceApi.speechHandler = { _, _, _, _, request ->
            ttsStarted.complete(Unit)
            withContext(NonCancellable) { releaseTts.await() }
            AssistantSpeechResult(lateBytes, AssistantRequestReceipt(request, "enabled", "succeeded"))
        }
        assertTrue(fixture.store.loadAssistantSpeech("en"))
        runCurrent()
        ttsStarted.await()
        assertTrue(fixture.store.state.value.assistant!!.speechBusy)

        assertTrue(fixture.store.sendAssistantText("new private question"))
        assertFalse(fixture.store.state.value.assistant!!.speechBusy)
        runCurrent()
        assertEquals(2, fixture.workspaceApi.submitCalls)
        assertEquals("Latest answer", fixture.store.state.value.assistant!!.turns.last().turn.reply)
        assertFalse(fixture.store.state.value.assistant!!.busy)

        releaseTts.complete(Unit)
        runCurrent()
        val assistant = requireNotNull(fixture.store.state.value.assistant)
        assertTrue(lateBytes.all { it == 0.toByte() })
        assertEquals("Latest answer", assistant.turns.last().turn.reply)
        assertFalse(assistant.speechBusy)
        assertNull(assistant.speechAudio)
        assertEquals(0, fixture.platform.speechCalls)
        assertEquals(1, fixture.workspaceApi.speechCalls)
        assertEquals(0, fixture.photoApi.v1TurnCalls)
        fixture.driver.close()
    }

    @Test fun losingReplySpeechCapabilityDuringPlaybackStopsAndWipesAudioWithoutRelistening() = runTest {
        val fixture = fixture(activatePrivate = true, replySpeech = true)
        val playbackBytes = ByteArray(256) { 0x35.toByte() }
        fixture.workspaceApi.speechHandler = { _, _, _, _, request ->
            AssistantSpeechResult(playbackBytes, AssistantRequestReceipt(request, "enabled", "succeeded"))
        }
        fixture.platform.captures.send(wav())

        assertTrue(fixture.driver.start())
        runCurrent()
        fixture.platform.speechStarted.receive()
        assertEquals(VoiceSessionPhase.SPEAKING, fixture.driver.state.value.phase)
        assertEquals(1, fixture.platform.speechCalls)
        val playingAudio = requireNotNull(fixture.platform.lastSpeechAudio)
        assertFalse(playingAudio.isClosed)

        fixture.workspaceApi.capabilitiesResponse = fixture.workspaceApi.capabilitiesResponse.copy(replySpeech = false)
        assertTrue(requireNotNull(fixture.store.assistantWorkspaceCoordinator).refreshCapabilities())
        runCurrent()

        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.CONTEXT_CHANGED, fixture.driver.state.value.reason)
        assertTrue(playingAudio.isClosed)
        assertTrue(playbackBytes.all { it == 0.toByte() })
        assertTrue(fixture.platform.stopAudioCalls > 0)
        assertEquals(1, fixture.platform.captureCalls)
        assertEquals(1, fixture.platform.speechCalls)
        assertNull(fixture.store.state.value.assistant!!.speechAudio)
        assertFalse(fixture.store.state.value.assistant!!.speechBusy)
        fixture.driver.close()
    }

    @Test fun losingReplySpeechCapabilityWhileListeningEndsBeforeSubmittingCapture() = runTest {
        val fixture = fixture(activatePrivate = true, replySpeech = true)
        assertTrue(fixture.driver.start())
        runCurrent()
        assertEquals(VoiceSessionPhase.LISTENING, fixture.driver.state.value.phase)
        assertEquals(1, fixture.platform.captureCalls)

        fixture.workspaceApi.capabilitiesResponse = fixture.workspaceApi.capabilitiesResponse.copy(replySpeech = false)
        assertTrue(requireNotNull(fixture.store.assistantWorkspaceCoordinator).refreshCapabilities())
        runCurrent()

        assertEquals(VoiceSessionPhase.ENDED, fixture.driver.state.value.phase)
        assertEquals(VoiceSessionStopReason.CONTEXT_CHANGED, fixture.driver.state.value.reason)
        assertTrue(fixture.platform.stopAudioCalls > 0)
        assertEquals(1, fixture.platform.captureCalls)
        assertTrue(fixture.photoApi.transcriptionIds.isEmpty())
        assertEquals(0, fixture.workspaceApi.submitCalls)
        assertEquals(0, fixture.workspaceApi.speechCalls)
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

    private suspend fun TestScope.fixture(activatePrivate: Boolean, replySpeech: Boolean = false): Fixture {
        val photoApi = PhotoApi()
        val workspaceApi = WorkspaceApi(threadId, replySpeech)
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
        var stopAudioCalls = 0
        var lastSpeechAudio: ProtectedAnnotationAudio? = null
        var ignoreSpeechCancellation = false
        override suspend fun capture(maxSeconds: Int): ByteArray? {
            captureCalls++
            return captures.receive()
        }
        override suspend fun playSpeech(audio: ProtectedAnnotationAudio): Boolean {
            speechCalls++
            lastSpeechAudio = audio
            speechStarted.send(Unit)
            return if (ignoreSpeechCancellation) withContext(NonCancellable) { speechResults.receive() }
                else speechResults.receive()
        }
        override fun stopAudio() { stopAudioCalls++ }
        override fun finishCapture() { captures.trySend(null) }
    }

    private class PhotoApi : PhotoHouseApi {
        override val assistantEnabled = true
        var v1TurnCalls = 0
        var speechCalls = 0
        val transcriptionIds = mutableListOf<String>()
        val transcriptionTexts = mutableListOf<String>()
        var transcriptText = "find the beach"
        var transcriptionGate: CompletableDeferred<Unit>? = null
        override suspend fun assistantCapabilities(token: Bearer, library: String) = AssistantCapabilities(true, true, true, true, 30)
        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript {
            transcriptionIds += requestId
            val transcript = transcriptText
            transcriptionTexts += transcript
            transcriptionGate?.let { withContext(NonCancellable) { it.await() } }
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

    private class WorkspaceApi(private val threadId: String, replySpeech: Boolean = false) : AssistantWorkspaceApi {
        override val assistantWorkspaceEnabled = true
        var capabilitiesResponse = AssistantWorkspaceCapabilities(
            1, true, true, true, true, true, setOf("locale"), replySpeech = replySpeech,
        )
        var revision = 0L
        var latestRequestId: String? = null
        var submitCalls = 0
        var getCalls = 0
        var speechCalls = 0
        val requestIds = mutableListOf<String>()
        val parentIds = mutableListOf<String?>()
        val texts = mutableListOf<String>()
        val memoryParents = mutableListOf<AssistantSavedMemoryParent?>()
        val speechThreadIds = mutableListOf<String>()
        val speechTurnIds = mutableListOf<String>()
        val speechRevisions = mutableListOf<Long>()
        val speechRequestIds = mutableListOf<String>()
        var resultFactory: (String) -> AssistantTurn = ::result
        var savedMemoryCardsAvailable = false
        var savedMemoryActionsAvailable = false
        var savedMemoryFollowupAvailable = false
        var savedMemoryReaderAvailable = false
        var savedMemoryReadingAvailable = false
        var savedMemorySegmentReadingAvailable = false
        var readerPayload: SavedMemoryReaderPayload = SavedMemoryReaderPayload.Story(SavedMemoryStory(
            id = "33333333-3333-4333-8333-333333333333", libraryId = "family", revision = 2,
            createdAt = 0, updatedAt = 0, canEdit = false, selectionRevision = "a".repeat(64),
            title = "Garden day", theme = "family", language = "en",
            items = listOf(MemoryStoryAsset(testAsset(), emptyList())),
            chapters = listOf(SavedMemoryStoryChapter("chapter-1", "Garden", "A day together.", listOf("1"), emptyList())),
            questions = emptyList(),
        ))
        var memoryOpeningSpeechCalls = 0
        val memorySegmentIndices = mutableListOf<Int>()
        var memorySegmentHandler: suspend (String, String, String, Int, Int, Long, String) -> AssistantMemorySegmentSpeechResult =
            { _, _, _, _, segment, _, request -> AssistantMemorySegmentSpeechResult(syntheticAnnotationWav(),
                AssistantRequestReceipt(request, "enabled", "succeeded", playbackTracking = true), segment, 2) }
        var speechHandler: suspend (String, String, String, Long, String) -> AssistantSpeechResult =
            { _, _, _, _, request -> AssistantSpeechResult(syntheticAnnotationWav(), AssistantRequestReceipt(request, "enabled", "succeeded")) }
        var memoryOpeningHandler: suspend (String, String, String, Int, Long, String) -> AssistantSpeechResult =
            { _, _, _, _, _, request -> AssistantSpeechResult(syntheticAnnotationWav(), AssistantRequestReceipt(request, "enabled", "succeeded")) }
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
            return submitTurn(token, library, threadId, requestId, expectedRevision, text, parentRequestId, false, null)
        }
        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                        expectedRevision: Long, text: String, parentRequestId: String?,
                                        acceptSavedMemoryCards: Boolean,
                                        memoryParent: AssistantSavedMemoryParent?): AssistantWorkspaceTurn {
            submitCalls++
            requestIds += requestId
            parentIds += parentRequestId
            memoryParents += memoryParent
            texts += text
            return submitHandler(threadId, requestId, expectedRevision, text)
        }
        override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                        expectedRevision: Long, text: String, parentRequestId: String?,
                                        acceptSavedMemoryCards: Boolean, memoryParent: AssistantSavedMemoryParent?,
                                        acceptSavedMemoryActions: Boolean): AssistantWorkspaceTurn =
            submitTurn(token, library, threadId, requestId, expectedRevision, text, parentRequestId,
                acceptSavedMemoryCards, memoryParent)
        override suspend fun getTurn(token: Bearer, library: String, threadId: String, requestId: String): AssistantWorkspaceTurn {
            getCalls++
            return getHandler(threadId, requestId, revision)
        }

        override suspend fun speakTurn(token: Bearer, library: String, threadId: String, turnId: String,
                                       expectedRevision: Long, speechRequestId: String): AssistantSpeechResult {
            speechCalls++
            speechThreadIds += threadId
            speechTurnIds += turnId
            speechRevisions += expectedRevision
            speechRequestIds += speechRequestId
            return speechHandler(library, threadId, turnId, expectedRevision, speechRequestId)
        }
        override suspend fun savedMemoryReadingCapabilities(token: Bearer, library: String) =
            SavedMemoryReaderCapabilities(1, savedMemoryReadingAvailable)
        override suspend fun savedMemorySegmentReadingCapabilities(token: Bearer, library: String) =
            SavedMemoryReaderCapabilities(1, savedMemorySegmentReadingAvailable)
        override suspend fun savedMemoryReaderCapabilities(token: Bearer, library: String) =
            SavedMemoryReaderCapabilities(1, savedMemoryReaderAvailable)
        override suspend fun savedMemoryReader(token: Bearer, library: String, threadId: String, turnId: String,
                                               ordinal: Int, expectedRevision: Long): SavedMemoryReaderPayload = readerPayload
        override suspend fun speakSavedMemoryOpening(token: Bearer, library: String, threadId: String, turnId: String,
                                                     ordinal: Int, expectedRevision: Long,
                                                     speechRequestId: String): AssistantSpeechResult {
            memoryOpeningSpeechCalls++
            return memoryOpeningHandler(library, threadId, turnId, ordinal, expectedRevision, speechRequestId)
        }
        override suspend fun speakSavedMemorySegment(token: Bearer, library: String, threadId: String, turnId: String,
                                                     ordinal: Int, segment: Int, expectedRevision: Long,
                                                     speechRequestId: String): AssistantMemorySegmentSpeechResult {
            memorySegmentIndices += segment
            return memorySegmentHandler(library, threadId, turnId, ordinal, segment, expectedRevision, speechRequestId)
        }
        override suspend fun savedMemoryCardsCapabilities(token: Bearer, library: String) =
            SavedMemoryReaderCapabilities(1, savedMemoryCardsAvailable)
        override suspend fun savedMemoryActionCapabilities(token: Bearer, library: String) =
            SavedMemoryReaderCapabilities(1, savedMemoryActionsAvailable)
        override suspend fun savedMemoryFollowupCapabilities(token: Bearer, library: String) =
            SavedMemoryReaderCapabilities(1, savedMemoryFollowupAvailable)

        fun completed(id: String, request: String, resultRevision: Long, recovered: Boolean) = AssistantWorkspaceTurn(
            version = 1, threadId = id, requestId = request, status = AssistantWorkspaceRequestStatus.COMPLETED,
            revision = resultRevision, recovered = recovered, error = null,
            result = resultFactory(request), receipt = AssistantRequestReceipt(request, "enabled", "succeeded"),
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

        private fun savedMemoryResult(requestId: String): AssistantTurn {
            val card = AssistantSavedMemoryCard("story", "33333333-3333-4333-8333-333333333333", "2",
                "e".repeat(64), "Garden day", "A short excerpt.")
            return AssistantTurn("memory_cards", "Found a memory.", null, null, emptyList(), 1, false, null,
                receipt = AssistantRequestReceipt(requestId, "enabled", "succeeded"), memoryCards = listOf(card),
                savedMemoryContext = AssistantSavedMemoryContext("family", "f".repeat(64), listOf(
                    AssistantSavedMemoryReference(card.kind, card.id, card.revision, card.sourceRevision))))
        }

        private fun serverReply(requestId: String, kind: String, reply: String,
                                noResults: Boolean = false) = AssistantTurn(
            kind = kind, reply = reply, context = null, filters = null, items = emptyList(), total = 0,
            hasMore = false, effect = null,
            receipt = AssistantRequestReceipt(requestId, "enabled", "succeeded"),
        ).also { check(!noResults || it.kind == "results") }

        private fun multiResultOpen(requestId: String): AssistantTurn {
            val items = listOf(testAsset(), testAsset("2"), testAsset("3"))
            val ids = items.map { it.id }
            return AssistantTurn(
                kind = "open", reply = "Opening the second photo.",
                context = buildJsonObject {
                    put("visible_ids", buildJsonArray { ids.forEach { add(JsonPrimitive(it)) } })
                    put("total", JsonPrimitive(ids.size))
                },
                filters = buildJsonObject { }, items = items, total = ids.size, hasMore = false,
                effect = AssistantEffect("open_asset", "2"),
                receipt = AssistantRequestReceipt(requestId, "enabled", "succeeded"),
            )
        }

        private fun visibleContext(): JsonObject = buildJsonObject {
            put("visible_ids", buildJsonArray { add(JsonPrimitive("1")) })
        }

        private fun testAsset(id: String = "1") = Asset(id, "image", 640, 480, null, null, "/assets/$id/thumbnail?library=family")

        private fun wav() = ByteArray(16_046).also { bytes ->
            "RIFF".toByteArray().copyInto(bytes)
            "WAVE".toByteArray().copyInto(bytes, 8)
        }
    }
}
