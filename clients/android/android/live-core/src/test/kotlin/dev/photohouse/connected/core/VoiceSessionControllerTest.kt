package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceSessionControllerTest {
    private val scope = VoiceSessionScope("account-a", "family-library", 12)

    private inline fun <reified T : VoiceSessionEffect> effect(transition: VoiceSessionTransition): T =
        transition.effects.filterIsInstance<T>().single()

    private fun beginRequest(controller: VoiceSessionController): VoiceSessionBinding {
        val asr = beginTranscription(controller)
        return effect<VoiceSessionEffect.SubmitReadOnlyRequest>(controller.transcriptReady(asr, "找去年春天的照片")).binding
    }

    private fun beginTranscription(controller: VoiceSessionController): VoiceSessionBinding {
        val capture = effect<VoiceSessionEffect.StartCapture>(controller.start(scope, foreground = true)).binding
        return effect<VoiceSessionEffect.Transcribe>(controller.captureCompleted(capture)).binding
    }

    @Test
    fun explicitStartAndCompletedReplyFormHalfDuplexLoop() {
        val controller = VoiceSessionController()
        assertFalse(controller.start(scope, foreground = false).accepted)
        assertEquals(VoiceSessionPhase.IDLE, controller.state.phase)

        val capture = effect<VoiceSessionEffect.StartCapture>(controller.start(scope, foreground = true)).binding
        assertEquals(scope, capture.scope)
        assertTrue(controller.state.microphoneActive)
        assertFalse(controller.state.speechActive)

        val transcribe = controller.captureCompleted(capture)
        assertEquals(VoiceSessionPhase.TRANSCRIBING, transcribe.state.phase)
        assertEquals(capture, effect<VoiceSessionEffect.StopCapture>(transcribe).binding)
        val asrBinding = effect<VoiceSessionEffect.Transcribe>(transcribe).binding
        val request = controller.transcriptReady(asrBinding, "找去年春天的照片")
        assertEquals(VoiceSessionPhase.REQUESTING, request.state.phase)
        assertEquals("找去年春天的照片", effect<VoiceSessionEffect.SubmitReadOnlyRequest>(request).text)
        val requestBinding = effect<VoiceSessionEffect.SubmitReadOnlyRequest>(request).binding

        val reply = controller.requestCompleted(requestBinding, VoiceAssistantReply(
            text = "我找到了三张照片。", receipt = VoiceRequestReceipt.CONFIRMED_SUCCESS,
        ))
        assertEquals(VoiceSessionPhase.SPEAKING, reply.state.phase)
        assertFalse(reply.state.microphoneActive)
        val speechBinding = effect<VoiceSessionEffect.Speak>(reply).binding
        assertFalse(controller.speechCompleted(requestBinding, success = true).accepted)
        assertEquals(VoiceSessionPhase.SPEAKING, controller.state.phase)

        val completed = controller.speechCompleted(speechBinding, success = true)
        assertEquals(VoiceSessionPhase.LISTENING, completed.state.phase)
        assertTrue(completed.state.microphoneActive)
        assertEquals(speechBinding.scope, effect<VoiceSessionEffect.StartCapture>(completed).binding.scope)
    }

    @Test
    fun memoryReadingAdmissionRequiresForegroundBoundedSequenceWithAnotherSegment() {
        val controller = VoiceSessionController()
        assertFalse(controller.startMemoryReading(scope, false, segment = 0, segmentCount = 2).accepted)
        assertFalse(controller.startMemoryReading(scope, true, segment = -1, segmentCount = 2).accepted)
        assertFalse(controller.startMemoryReading(scope, true, segment = 0, segmentCount = 0).accepted)
        assertFalse(controller.startMemoryReading(scope, true, segment = 0, segmentCount = 129).accepted)
        assertFalse(controller.startMemoryReading(scope, true, segment = 1, segmentCount = 2).accepted)
        assertEquals(VoiceSessionPhase.IDLE, controller.state.phase)

        val started = controller.startMemoryReading(scope, true, segment = 0, segmentCount = 2)
        assertEquals(VoiceSessionPhase.LISTENING, started.state.phase)
        assertTrue(started.state.readingContinuation)
        assertEquals(0, started.state.readingSegment)
        assertEquals(2, started.state.readingSegmentCount)
        assertFalse(controller.startMemoryReading(scope, true, segment = 0, segmentCount = 2).accepted)
    }

    @Test
    fun readingContinuationRequestsNextSegmentAndPausesAtFinalCompletion() {
        val controller = VoiceSessionController()
        val firstCapture = effect<VoiceSessionEffect.StartCapture>(
            controller.startMemoryReading(scope, true, segment = 0, segmentCount = 3),
        ).binding
        val firstAsr = effect<VoiceSessionEffect.Transcribe>(controller.captureCompleted(firstCapture)).binding
        val continuation = controller.transcriptReady(firstAsr, "继续朗读")
        val firstRead = effect<VoiceSessionEffect.ReadMemorySegment>(continuation)
        assertEquals(1, firstRead.segment)
        assertEquals(3, firstRead.segmentCount)
        assertEquals(VoiceSessionPhase.SPEAKING, continuation.state.phase)
        assertEquals(1, continuation.state.readingSegment)
        assertTrue(continuation.effects.none { it is VoiceSessionEffect.SubmitReadOnlyRequest })

        val nextCapture = effect<VoiceSessionEffect.StartCapture>(controller.speechCompleted(firstRead.binding, true)).binding
        assertTrue(controller.state.readingContinuation)
        assertEquals(1, controller.state.readingSegment)
        val nextAsr = effect<VoiceSessionEffect.Transcribe>(controller.captureCompleted(nextCapture)).binding
        val finalRead = effect<VoiceSessionEffect.ReadMemorySegment>(controller.transcriptReady(nextAsr, "read the next segment"))
        assertEquals(2, finalRead.segment)

        val finished = controller.speechCompleted(finalRead.binding, success = true)
        assertEquals(VoiceSessionPhase.PAUSED, finished.state.phase)
        assertEquals(VoiceSessionStopReason.READING_FINISHED, finished.state.reason)
        assertFalse(finished.effects.any {
            it is VoiceSessionEffect.StartCapture || it is VoiceSessionEffect.SubmitReadOnlyRequest ||
                it is VoiceSessionEffect.ReadMemorySegment || it is VoiceSessionEffect.Speak
        })
        assertFalse(finished.state.readingContinuation)
        assertEquals(null, finished.state.readingSegment)
        assertEquals(null, finished.state.readingSegmentCount)
        assertFalse(controller.speechCompleted(finalRead.binding, success = true).accepted)
    }

    @Test
    fun continuationWithoutSelectionPausesAndDoesNotSubmit() {
        val controller = VoiceSessionController()
        val asr = beginTranscription(controller)
        val result = controller.transcriptReady(asr, "读下一段")
        assertEquals(VoiceSessionPhase.PAUSED, result.state.phase)
        assertEquals(VoiceSessionStopReason.READING_NEEDS_SELECTION, result.state.reason)
        assertFalse(result.effects.any {
            it is VoiceSessionEffect.StartCapture || it is VoiceSessionEffect.SubmitReadOnlyRequest ||
                it is VoiceSessionEffect.ReadMemorySegment || it is VoiceSessionEffect.Speak
        })
        assertFalse(result.state.readingContinuation)
    }

    @Test
    fun pauseEndUnavailableAndStaleCallbacksClearOrPreserveReadingAsSpecified() {
        val paused = VoiceSessionController()
        assertFalse(paused.readingUnavailable().accepted)
        val pausedCapture = effect<VoiceSessionEffect.StartCapture>(
            paused.startMemoryReading(scope, true, segment = 0, segmentCount = 2),
        ).binding
        val pause = paused.pause()
        assertEquals(VoiceSessionStopReason.USER_PAUSED, pause.state.reason)
        assertFalse(pause.state.readingContinuation)
        assertFalse(paused.captureCompleted(pausedCapture).accepted)
        assertFalse(paused.readingUnavailable().accepted)
        val resumed = paused.resume(scope, true)
        assertFalse(resumed.state.readingContinuation)
        assertEquals(null, resumed.state.readingSegment)
        assertEquals(null, resumed.state.readingSegmentCount)

        val ended = VoiceSessionController()
        val endCapture = effect<VoiceSessionEffect.StartCapture>(
            ended.startMemoryReading(scope, true, segment = 0, segmentCount = 2),
        ).binding
        val endAsr = effect<VoiceSessionEffect.Transcribe>(ended.captureCompleted(endCapture)).binding
        val end = ended.transcriptReady(endAsr, "结束")
        assertEquals(VoiceSessionPhase.ENDED, end.state.phase)
        assertFalse(end.state.readingContinuation)
        assertFalse(ended.transcriptReady(endAsr, "继续朗读").accepted)

        val unavailable = VoiceSessionController()
        val unavailableCapture = effect<VoiceSessionEffect.StartCapture>(
            unavailable.startMemoryReading(scope, true, segment = 0, segmentCount = 2),
        ).binding
        val stopped = unavailable.readingUnavailable()
        assertEquals(VoiceSessionStopReason.READING_UNAVAILABLE, stopped.state.reason)
        assertFalse(stopped.state.readingContinuation)
        assertFalse(unavailable.captureCompleted(unavailableCapture).accepted)

        val failedSpeech = VoiceSessionController()
        val failCapture = effect<VoiceSessionEffect.StartCapture>(
            failedSpeech.startMemoryReading(scope, true, segment = 0, segmentCount = 2),
        ).binding
        val failAsr = effect<VoiceSessionEffect.Transcribe>(failedSpeech.captureCompleted(failCapture)).binding
        val read = effect<VoiceSessionEffect.ReadMemorySegment>(failedSpeech.transcriptReady(failAsr, "继续读"))
        val failure = failedSpeech.speechCompleted(read.binding, success = false)
        assertEquals(VoiceSessionStopReason.SPEECH_FAILED, failure.state.reason)
        assertFalse(failure.state.readingContinuation)
        assertEquals(null, failure.state.readingSegment)
        assertEquals(null, failure.state.readingSegmentCount)
    }

    @Test
    fun ordinaryQueryClearsReadingModeAndKeepsGenericRequestBehavior() {
        val controller = VoiceSessionController()
        val capture = effect<VoiceSessionEffect.StartCapture>(
            controller.startMemoryReading(scope, true, segment = 0, segmentCount = 2),
        ).binding
        val asr = effect<VoiceSessionEffect.Transcribe>(controller.captureCompleted(capture)).binding
        val request = controller.transcriptReady(asr, "找去年春天的照片")
        assertEquals(VoiceSessionPhase.REQUESTING, request.state.phase)
        assertTrue(request.effects.single() is VoiceSessionEffect.SubmitReadOnlyRequest)
        assertFalse(request.state.readingContinuation)
        assertEquals(null, request.state.readingSegment)
        assertEquals(null, request.state.readingSegmentCount)
    }

    @Test
    fun everyAsyncCallbackIsFencedBySessionOperationAndContext() {
        val controller = VoiceSessionController()
        val oldCapture = effect<VoiceSessionEffect.StartCapture>(controller.start(scope, true)).binding
        val transcribe = controller.captureCompleted(oldCapture)
        val oldAsr = effect<VoiceSessionEffect.Transcribe>(transcribe).binding
        val currentRequest = effect<VoiceSessionEffect.SubmitReadOnlyRequest>(controller.transcriptReady(oldAsr, "找照片")).binding

        val differentAccount = scope.copy(accountId = "account-b")
        controller.contextChanged(differentAccount)
        assertEquals(VoiceSessionPhase.ENDED, controller.state.phase)
        assertEquals(VoiceSessionStopReason.CONTEXT_CHANGED, controller.state.reason)
        assertFalse(controller.requestCompleted(currentRequest, VoiceAssistantReply(
            "过期回答", VoiceRequestReceipt.CONFIRMED_SUCCESS,
        )).accepted)
        assertFalse(controller.captureCompleted(oldCapture).accepted)

        val newCapture = effect<VoiceSessionEffect.StartCapture>(controller.start(differentAccount, true)).binding
        assertNotEquals(oldCapture.sessionGeneration, newCapture.sessionGeneration)
        assertFalse(controller.captureCompleted(oldCapture).accepted)
    }

    @Test
    fun pauseBackgroundAndAudioFocusInvalidateCallbacksAndDoNotResumeAutomatically() {
        for (stop in listOf<(VoiceSessionController) -> VoiceSessionTransition>(
            { it.pause() }, { it.backgrounded() }, { it.audioFocusLost() },
        )) {
            val controller = VoiceSessionController()
            val binding = effect<VoiceSessionEffect.StartCapture>(controller.start(scope, true)).binding
            stop(controller)
            assertEquals(VoiceSessionPhase.PAUSED, controller.state.phase)
            assertFalse(controller.state.microphoneActive)
            assertFalse(controller.captureCompleted(binding).accepted)
            assertTrue(controller.start(scope, foreground = false).effects.isEmpty())
            assertEquals(VoiceSessionPhase.PAUSED, controller.state.phase)
            assertFalse(controller.start(scope, foreground = true).accepted)
        }
    }

    @Test
    fun explicitResumeRequiresForegroundAndTheSamePausedScope() {
        val controller = VoiceSessionController()
        val oldCapture = effect<VoiceSessionEffect.StartCapture>(controller.start(scope, true)).binding
        controller.pause()
        assertFalse(controller.start(scope, foreground = true).accepted)
        assertFalse(controller.resume(scope, foreground = false).accepted)
        assertFalse(controller.resume(scope.copy(libraryId = "other-library"), foreground = true).accepted)
        assertEquals(VoiceSessionPhase.PAUSED, controller.state.phase)

        val resumed = controller.resume(scope, foreground = true)
        val newCapture = effect<VoiceSessionEffect.StartCapture>(resumed).binding
        assertEquals(VoiceSessionPhase.LISTENING, resumed.state.phase)
        assertEquals(scope, newCapture.scope)
        assertNotEquals(oldCapture.sessionGeneration, newCapture.sessionGeneration)
        assertFalse(controller.captureCompleted(oldCapture).accepted)
    }

    @Test
    fun uncertainOrFailedRequestPausesWithoutRetry() {
        for ((receipt, reason) in listOf(
            VoiceRequestReceipt.UNCERTAIN to VoiceSessionStopReason.UNCERTAIN_REQUEST,
            VoiceRequestReceipt.CONFIRMED_FAILURE to VoiceSessionStopReason.REQUEST_FAILED,
        )) {
            val controller = VoiceSessionController()
            val request = beginRequest(controller)
            val result = controller.requestCompleted(request, VoiceAssistantReply("", receipt))
            assertEquals(VoiceSessionPhase.PAUSED, result.state.phase)
            assertEquals(reason, result.state.reason)
            assertFalse(result.effects.any { it is VoiceSessionEffect.SubmitReadOnlyRequest })
            assertFalse(controller.requestCompleted(request, VoiceAssistantReply(
                "duplicate", VoiceRequestReceipt.CONFIRMED_SUCCESS,
            )).accepted)
        }
    }

    @Test
    fun captureAndTranscriptionFailuresPauseAndNeverStartAnotherCapture() {
        val captureFailure = VoiceSessionController()
        val capture = effect<VoiceSessionEffect.StartCapture>(captureFailure.start(scope, true)).binding
        val stoppedCapture = captureFailure.operationFailed(capture)
        assertEquals(VoiceSessionStopReason.CAPTURE_FAILED, stoppedCapture.state.reason)
        assertFalse(stoppedCapture.effects.any { it is VoiceSessionEffect.StartCapture })

        val asrFailure = VoiceSessionController()
        val activeCapture = effect<VoiceSessionEffect.StartCapture>(asrFailure.start(scope, true)).binding
        val asr = effect<VoiceSessionEffect.Transcribe>(asrFailure.captureCompleted(activeCapture)).binding
        val stoppedAsr = asrFailure.operationFailed(asr)
        assertEquals(VoiceSessionStopReason.TRANSCRIPTION_FAILED, stoppedAsr.state.reason)
        assertFalse(stoppedAsr.effects.any { it is VoiceSessionEffect.StartCapture })
    }

    @Test
    fun reviewRequiredReplyOnlyShowsReviewAndSpeechAndWaitsForPlaybackCompletion() {
        val controller = VoiceSessionController()
        val request = beginRequest(controller)
        val transition = controller.requestCompleted(request, VoiceAssistantReply(
            text = "我整理了一份草稿，请先检查。",
            receipt = VoiceRequestReceipt.CONFIRMED_SUCCESS,
            disposition = VoiceReplyDisposition.REVIEW_REQUIRED,
            reviewCardId = "draft-card-1",
        ))
        assertEquals(VoiceSessionPhase.SPEAKING, transition.state.phase)
        assertTrue(transition.state.reviewRequired)
        assertEquals(listOf(
            VoiceSessionEffect.ShowReviewCard(effect<VoiceSessionEffect.Speak>(transition).binding, "draft-card-1"),
            effect<VoiceSessionEffect.Speak>(transition),
        ), transition.effects)
        assertFalse(transition.state.microphoneActive)

        val speech = effect<VoiceSessionEffect.Speak>(transition).binding
        val done = controller.speechCompleted(speech, success = true)
        assertEquals(VoiceSessionPhase.PAUSED, done.state.phase)
        assertEquals(VoiceSessionStopReason.REVIEW_REQUIRED, done.state.reason)
        assertTrue(done.state.reviewRequired)
        assertTrue(done.effects.isEmpty())
        assertFalse(done.effects.any { it is VoiceSessionEffect.StartCapture })
    }

    @Test
    fun clarificationCanSuspendRequestOrSpeechForReview() {
        val requesting = VoiceSessionController()
        val request = beginRequest(requesting)
        val requestPause = requesting.suspendForReview(request)
        assertEquals(VoiceSessionPhase.PAUSED, requestPause.state.phase)
        assertEquals(VoiceSessionStopReason.REVIEW_REQUIRED, requestPause.state.reason)
        assertEquals(request, effect<VoiceSessionEffect.CancelInFlight>(requestPause).binding)
        assertFalse(requestPause.effects.any { it is VoiceSessionEffect.SubmitReadOnlyRequest })
        assertFalse(requesting.suspendForReview(request).accepted)

        val speaking = VoiceSessionController()
        val speakRequest = beginRequest(speaking)
        val reply = speaking.requestCompleted(speakRequest, VoiceAssistantReply(
            "请补充日期。", VoiceRequestReceipt.CONFIRMED_SUCCESS,
        ))
        val speech = effect<VoiceSessionEffect.Speak>(reply).binding
        val speechPause = speaking.suspendForReview(speech)
        assertEquals(VoiceSessionStopReason.REVIEW_REQUIRED, speechPause.state.reason)
        assertEquals(speech, effect<VoiceSessionEffect.StopSpeech>(speechPause).binding)
        assertFalse(speechPause.effects.any { it is VoiceSessionEffect.StartCapture })
        assertFalse(speechPause.effects.any { it is VoiceSessionEffect.SubmitReadOnlyRequest })
    }

    @Test
    fun transcriptMustFitCodePointAndUtf8RequestCeilings() {
        val withinCodePoints = VoiceSessionController()
        val accepted = withinCodePoints.transcriptReady(
            beginTranscription(withinCodePoints), "a".repeat(512),
        )
        assertEquals(VoiceSessionPhase.REQUESTING, accepted.state.phase)
        assertTrue(accepted.effects.single() is VoiceSessionEffect.SubmitReadOnlyRequest)

        val tooManyCodePoints = VoiceSessionController()
        val tooLongByCodePoints = tooManyCodePoints.transcriptReady(
            beginTranscription(tooManyCodePoints), "a".repeat(513),
        )
        assertEquals(VoiceSessionStopReason.TRANSCRIPT_TOO_LONG, tooLongByCodePoints.state.reason)
        assertFalse(tooLongByCodePoints.effects.any { it is VoiceSessionEffect.SubmitReadOnlyRequest })

        val tooManyBytes = VoiceSessionController()
        val tooLongByUtf8 = tooManyBytes.transcriptReady(
            beginTranscription(tooManyBytes), "你".repeat(342),
        )
        assertEquals(VoiceSessionStopReason.TRANSCRIPT_TOO_LONG, tooLongByUtf8.state.reason)
        assertFalse(tooLongByUtf8.effects.any { it is VoiceSessionEffect.SubmitReadOnlyRequest })
    }

    @Test
    fun malformedAndOversizedSpokenCommandsFailValidationBeforeClassification() {
        val malformed = VoiceSessionController()
        val invalidUtf8 = malformed.transcriptReady(beginTranscription(malformed), "pause\uD800")
        assertEquals(VoiceSessionStopReason.INVALID_TRANSCRIPT, invalidUtf8.state.reason)
        assertFalse(invalidUtf8.effects.any { it is VoiceSessionEffect.SubmitReadOnlyRequest })

        val oversized = VoiceSessionController()
        val overLimit = oversized.transcriptReady(beginTranscription(oversized), " ".repeat(508) + "pause")
        assertEquals(VoiceSessionStopReason.TRANSCRIPT_TOO_LONG, overLimit.state.reason)
        assertFalse(overLimit.effects.any { it is VoiceSessionEffect.SubmitReadOnlyRequest })
    }

    @Test
    fun missingReviewCardAndEmptyTranscriptFailClosed() {
        val controller = VoiceSessionController()
        val capture = effect<VoiceSessionEffect.StartCapture>(controller.start(scope, true)).binding
        val asr = effect<VoiceSessionEffect.Transcribe>(controller.captureCompleted(capture)).binding
        assertEquals(VoiceSessionStopReason.EMPTY_TRANSCRIPT, controller.transcriptReady(asr, "  ").state.reason)

        val another = VoiceSessionController()
        val request = beginRequest(another)
        val result = another.requestCompleted(request, VoiceAssistantReply(
            "需要检查", VoiceRequestReceipt.CONFIRMED_SUCCESS,
            disposition = VoiceReplyDisposition.REVIEW_REQUIRED,
        ))
        assertEquals(VoiceSessionPhase.PAUSED, result.state.phase)
    }

    @Test
    fun stoppingEachActiveStageEmitsOnlyMatchingStopEffects() {
        val listening = VoiceSessionController()
        val capture = effect<VoiceSessionEffect.StartCapture>(listening.start(scope, true)).binding
        assertTrue(listening.pause().effects.contains(VoiceSessionEffect.StopCapture(capture)))

        val speaking = VoiceSessionController()
        val request = beginRequest(speaking)
        val reply = speaking.requestCompleted(request, VoiceAssistantReply("答复", VoiceRequestReceipt.CONFIRMED_SUCCESS))
        val speech = effect<VoiceSessionEffect.Speak>(reply).binding
        val stopped = speaking.end()
        assertEquals(VoiceSessionPhase.ENDED, stopped.state.phase)
        assertTrue(stopped.effects.contains(VoiceSessionEffect.StopSpeech(speech)))

        val requesting = VoiceSessionController()
        val req = beginRequest(requesting)
        val canceled = requesting.pause()
        val cancel = effect<VoiceSessionEffect.CancelInFlight>(canceled)
        assertEquals(req, cancel.binding)
        assertFalse(requesting.requestCompleted(req, VoiceAssistantReply("late", VoiceRequestReceipt.CONFIRMED_SUCCESS)).accepted)
    }
}
