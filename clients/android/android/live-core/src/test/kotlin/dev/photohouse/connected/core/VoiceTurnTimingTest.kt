package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceTurnTimingTest {
    private class FakeClock(var now: Long = 0L) : () -> Long {
        var throwsOnRead = false
        override fun invoke(): Long {
            if (throwsOnRead) throw IllegalStateException("clock unavailable")
            return now
        }
    }

    private val scope = VoiceSessionScope("account-secret", "library-secret", 7)

    private inline fun <reified T : VoiceSessionEffect> effect(transition: VoiceSessionTransition): T =
        transition.effects.filterIsInstance<T>().single()

    private data class TurnObservations(
        val oldListening: VoiceSessionState,
        val speakingAfterPlayback: VoiceSessionState,
        val completedListening: VoiceSessionState,
    )

    private inner class Harness {
        val clock = FakeClock()
        val tracker = VoiceTurnTimingTracker(clock)
        val controller = VoiceSessionController()

        fun completeTurn(
            scope: VoiceSessionScope,
            confirmPlayback: Boolean = true,
            confirmCapture: Boolean = true,
            startSession: Boolean = true,
            times: List<Long> = listOf(20, 30, 40, 45, 75),
        ): TurnObservations {
            val oldListening: VoiceSessionState
            val captureBinding: VoiceSessionBinding
            if (startSession) {
                clock.now = 0
                val started = controller.start(scope, foreground = true)
                captureBinding = effect<VoiceSessionEffect.StartCapture>(started).binding
                oldListening = started.state
            } else {
                oldListening = controller.state
                captureBinding = VoiceSessionBinding(
                    requireNotNull(oldListening.scope),
                    oldListening.sessionGeneration,
                    oldListening.operationGeneration,
                )
            }
            tracker.observe(oldListening)

            clock.now = times[0] - 1
            if (confirmCapture) tracker.observe(oldListening.copy(captureStarted = true))
            clock.now = times[0]
            val transcribing = controller.captureCompleted(captureBinding)
            val asrBinding = effect<VoiceSessionEffect.Transcribe>(transcribing).binding
            tracker.observe(transcribing.state)

            clock.now = times[1]
            val requesting = controller.transcriptReady(asrBinding, "private transcript")
            val requestBinding = effect<VoiceSessionEffect.SubmitReadOnlyRequest>(requesting).binding
            tracker.observe(requesting.state)

            clock.now = times[2]
            val speaking = controller.requestCompleted(requestBinding,
                VoiceAssistantReply("private reply", VoiceRequestReceipt.CONFIRMED_SUCCESS))
            val speechBinding = effect<VoiceSessionEffect.Speak>(speaking).binding
            tracker.observe(speaking.state)
            clock.now = times[3]
            val speakingAfterPlayback = speaking.state.copy(playbackStarted = true)
            if (confirmPlayback) tracker.observe(speakingAfterPlayback)
            clock.now = times[4]
            val completed = controller.speechCompleted(speechBinding, success = true)
            tracker.observe(completed.state)
            return TurnObservations(oldListening, speakingAfterPlayback, completed.state)
        }
    }

    @Test
    fun publishesOnlyACompleteClientObservedTurnAndIgnoresRepeatedSnapshots() {
        val harness = Harness()
        val observations = harness.completeTurn(scope)
        assertEquals(VoiceTurnTimingSummary(
            transcriptionMillis = 10,
            requestMillis = 10,
            speechPreparationMillis = 5,
            playbackMillis = 30,
        ), harness.tracker.latestSummary)

        // A repeat is not a second turn and must not sample or alter timings.
        harness.clock.now = 900
        harness.tracker.observe(observations.completedListening)
        harness.tracker.observe(observations.speakingAfterPlayback)
        assertEquals(VoiceTurnTimingSummary(10, 10, 5, 30), harness.tracker.latestSummary)
    }

    @Test
    fun skippedPhasesAndUnconfirmedPlaybackNeverPublish() {
        val harness = Harness()
        val started = harness.controller.start(scope, foreground = true)
        val capture = effect<VoiceSessionEffect.StartCapture>(started).binding
        harness.tracker.observe(started.state)

        harness.clock.now = 10
        val transcribing = harness.controller.captureCompleted(capture)
        val asr = effect<VoiceSessionEffect.Transcribe>(transcribing).binding
        // Skip observing TRANSCRIBING, then attempt the remainder of the loop.
        harness.clock.now = 20
        val requesting = harness.controller.transcriptReady(asr, "private transcript")
        val request = effect<VoiceSessionEffect.SubmitReadOnlyRequest>(requesting).binding
        harness.tracker.observe(requesting.state)
        val speaking = harness.controller.requestCompleted(request,
            VoiceAssistantReply("private reply", VoiceRequestReceipt.CONFIRMED_SUCCESS))
        val speech = effect<VoiceSessionEffect.Speak>(speaking).binding
        harness.tracker.observe(speaking.state)
        harness.clock.now = 25
        harness.tracker.observe(speaking.state.copy(playbackStarted = true))
        val completed = harness.controller.speechCompleted(speech, success = true)
        harness.clock.now = 50
        harness.tracker.observe(completed.state)
        assertNull(harness.tracker.latestSummary)

        val unconfirmed = Harness()
        unconfirmed.completeTurn(scope, confirmPlayback = false)
        assertNull(unconfirmed.tracker.latestSummary)

        val captureNotConfirmed = Harness()
        captureNotConfirmed.completeTurn(scope, confirmCapture = false)
        assertNull(captureNotConfirmed.tracker.latestSummary)
    }

    @Test
    fun pauseEndScopeReplacementAndNewSessionClearAndFenceOldSnapshots() {
        val harness = Harness()
        val first = harness.completeTurn(scope)
        assertTrue(harness.tracker.latestSummary != null)

        harness.tracker.observe(harness.controller.pause().state)
        assertNull(harness.tracker.latestSummary)
        val resumed = harness.controller.resume(scope, foreground = true)
        harness.tracker.observe(resumed.state)
        assertNull(harness.tracker.latestSummary)
        // A delayed old operation cannot replace current observations.
        harness.tracker.observe(first.speakingAfterPlayback)
        assertNull(harness.tracker.latestSummary)

        harness.controller.end().also { harness.tracker.observe(it.state) }
        assertNull(harness.tracker.latestSummary)

        val switched = scope.copy(accountId = "other-account", appGeneration = 8)
        harness.controller.start(switched, foreground = true).also { harness.tracker.observe(it.state) }
        harness.tracker.observe(first.completedListening)
        assertNull(harness.tracker.latestSummary)
    }

    @Test
    fun staleOperationAndSessionGenerationsCannotClearOrPublishOverCurrentSession() {
        val harness = Harness()
        val first = harness.completeTurn(scope)
        val completedSummary = harness.tracker.latestSummary
        assertTrue(completedSummary != null)
        // Same session, older operation: ignore without disturbing the latest result.
        harness.tracker.observe(first.oldListening)
        assertEquals(completedSummary, harness.tracker.latestSummary)

        harness.controller.pause().also { harness.tracker.observe(it.state) }
        assertNull(harness.tracker.latestSummary)
        val resumed = harness.controller.resume(scope, foreground = true)
        harness.tracker.observe(resumed.state)
        harness.tracker.observe(first.speakingAfterPlayback)
        assertNull(harness.tracker.latestSummary)

        val replacement = scope.copy(accountId = "replacement-account", appGeneration = 8)
        harness.tracker.observe(VoiceSessionState(
            phase = VoiceSessionPhase.LISTENING,
            scope = replacement,
            sessionGeneration = 1,
            operationGeneration = 1,
        ))
        assertNull(harness.tracker.latestSummary)
        harness.tracker.observe(first.completedListening)
        assertNull(harness.tracker.latestSummary)
    }

    @Test
    fun endClearsMostRecentSummary() {
        val harness = Harness()
        harness.completeTurn(scope)
        assertTrue(harness.tracker.latestSummary != null)
        harness.tracker.observe(harness.controller.end().state)
        assertNull(harness.tracker.latestSummary)
    }

    @Test
    fun backwardAndOverflowingClockReadingsRefuseTimingSummaries() {
        val backwards = Harness()
        val started = backwards.controller.start(scope, foreground = true)
        val capture = effect<VoiceSessionEffect.StartCapture>(started).binding
        backwards.tracker.observe(started.state)
        backwards.tracker.observe(started.state.copy(captureStarted = true))
        backwards.clock.now = 100
        val transcribing = backwards.controller.captureCompleted(capture)
        backwards.tracker.observe(transcribing.state)
        backwards.clock.now = 90
        val requesting = backwards.controller.transcriptReady(
            effect<VoiceSessionEffect.Transcribe>(transcribing).binding, "private transcript")
        backwards.tracker.observe(requesting.state)
        val speech = backwards.controller.requestCompleted(
            effect<VoiceSessionEffect.SubmitReadOnlyRequest>(requesting).binding,
            VoiceAssistantReply("private reply", VoiceRequestReceipt.CONFIRMED_SUCCESS))
        backwards.tracker.observe(speech.state)
        backwards.clock.now = 120
        backwards.tracker.observe(speech.state.copy(playbackStarted = true))
        val completed = backwards.controller.speechCompleted(
            effect<VoiceSessionEffect.Speak>(speech).binding, success = true)
        backwards.clock.now = 150
        backwards.tracker.observe(completed.state)
        assertNull(backwards.tracker.latestSummary)

        val overflow = Harness()
        val listening = overflow.controller.start(scope, foreground = true)
        overflow.tracker.observe(listening.state)
        overflow.tracker.observe(listening.state.copy(captureStarted = true))
        val asr = overflow.controller.captureCompleted(effect<VoiceSessionEffect.StartCapture>(listening).binding)
        overflow.clock.now = Long.MIN_VALUE
        overflow.tracker.observe(asr.state)
        val request = overflow.controller.transcriptReady(
            effect<VoiceSessionEffect.Transcribe>(asr).binding, "private transcript")
        overflow.clock.now = Long.MAX_VALUE
        overflow.tracker.observe(request.state)
        val speaking = overflow.controller.requestCompleted(
            effect<VoiceSessionEffect.SubmitReadOnlyRequest>(request).binding,
            VoiceAssistantReply("private reply", VoiceRequestReceipt.CONFIRMED_SUCCESS))
        overflow.tracker.observe(speaking.state)
        overflow.tracker.observe(speaking.state.copy(playbackStarted = true))
        val done = overflow.controller.speechCompleted(
            effect<VoiceSessionEffect.Speak>(speaking).binding, success = true)
        overflow.tracker.observe(done.state)
        assertNull(overflow.tracker.latestSummary)
    }

    @Test
    fun clockRegressionAcrossTurnsClearsPublishedSummaryAndDisablesSessionTiming() {
        val harness = Harness()
        harness.completeTurn(scope)
        assertTrue(harness.tracker.latestSummary != null)

        // Each interval would be locally positive, but the new ASR boundary
        // precedes the prior turn's playback completion boundary.
        harness.completeTurn(scope, startSession = false, times = listOf(74, 80, 90, 95, 100))
        assertNull(harness.tracker.latestSummary)

        // A later plausible clock value cannot revive a clock that regressed.
        harness.completeTurn(scope, startSession = false, times = listOf(110, 120, 130, 135, 150))
        assertNull(harness.tracker.latestSummary)
    }

    @Test
    fun throwingClockClearsSummaryAndOwnerClearResetsTracker() {
        val harness = Harness()
        harness.completeTurn(scope)
        assertTrue(harness.tracker.latestSummary != null)

        harness.clock.throwsOnRead = true
        harness.completeTurn(scope, startSession = false)
        assertNull(harness.tracker.latestSummary)

        harness.tracker.clear()
        assertNull(harness.tracker.latestSummary)
    }
}
