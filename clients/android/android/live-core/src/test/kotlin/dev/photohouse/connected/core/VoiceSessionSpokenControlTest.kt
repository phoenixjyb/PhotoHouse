package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class VoiceSessionSpokenControlTest {
    @Test fun exactAllowlistAcceptsOuterSpaceCaseAndTerminalPunctuation() {
        listOf("暂停", "暂停聆听", "暂停语音", "pause", "pause listening", "pause voice chat", "pause voice search", "stop")
            .forEach { assertEquals(VoiceSessionSpokenControl.PAUSE, classifyVoiceSessionSpokenControl("  $it!?。  ")) }
        listOf("结束", "结束语音", "结束对话", "停止聆听", "end voice chat", "end voice search", "stop listening")
            .forEach { assertEquals(VoiceSessionSpokenControl.END, classifyVoiceSessionSpokenControl("  $it！？  ")) }
        assertEquals(VoiceSessionSpokenControl.PAUSE, classifyVoiceSessionSpokenControl("PAUSE."))
    }

    @Test fun extraWordsNegationQuotesAndInternalPunctuationRemainOrdinaryText() {
        listOf(
            "please pause", "pause please", "do not pause", "don't pause", "please end voice chat",
            "pause, please", "'pause'", "\"pause\"", "暂停一下", "不要暂停", "pause voice chat now",
        ).forEach { assertNull(it, classifyVoiceSessionSpokenControl(it)) }
    }

    @Test fun staleBindingIsRejectedBeforeSpokenControlClassification() {
        val controller = VoiceSessionController()
        val oldCapture = controller.start(VoiceSessionScope("account-a", "family", 1), true)
            .effects.filterIsInstance<VoiceSessionEffect.StartCapture>().single().binding
        val asr = controller.captureCompleted(oldCapture)
            .effects.filterIsInstance<VoiceSessionEffect.Transcribe>().single().binding
        controller.pause()
        controller.resume(oldCapture.scope, true)

        val stale = controller.transcriptReady(asr, "pause")
        assertEquals(false, stale.accepted)
        assertEquals(VoiceSessionPhase.LISTENING, controller.state.phase)
    }
}
