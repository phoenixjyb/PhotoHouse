package dev.photohouse.connected

import android.content.Context
import android.speech.tts.Voice
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.util.Locale

/** Explicit read-aloud actions must be current, enabled and foreground-bound. */
@RunWith(AndroidJUnit4::class)
class ChapterReadAloudActionLifetimeUiTest {
    @get:Rule val rule = createComposeRule()

    @Test fun staleStartCannotRestartWhilePausedOrDisabledAndActivePauseRemainsAvailable() {
        val owner = TestOwner()
        rule.runOnIdle { owner.lifecycle.currentState = Lifecycle.State.RESUMED }
        val coordinator = ReaderAudioCoordinator()
        val factory = SpeechFactory()
        rule.setContent {
            var enabled by remember { mutableStateOf(true) }
            CompositionLocalProvider(
                LocalLifecycleOwner provides owner,
                LocalReaderAudioCoordinator provides coordinator,
                LocalChapterSpeechAdapterFactory provides factory,
                LocalChapterAudioFocusFactory provides FocusFactory(),
            ) {
                Column {
                    ChapterReadAloud("An explicit short introduction.", "en", "current-story", false,
                        enabled = enabled, labels = ChapterReadAloudLabels(
                            read = "Read aloud", pause = "Pause reading", resume = "Resume reading",
                            stop = "Stop reading", tagPrefix = "action-lifetime"))
                    androidx.compose.material3.TextButton(onClick = { enabled = !enabled }, modifier = Modifier.testTag("toggle-enabled")) {
                        androidx.compose.material3.Text("Toggle enabled")
                    }
                }
            }
        }

        val capturedStart = captureAction()
        rule.runOnIdle { owner.lifecycle.currentState = Lifecycle.State.STARTED }
        rule.runOnIdle { capturedStart() }
        rule.waitForIdle()
        assertTrue("a captured start cannot allocate an engine while backgrounded", factory.engines.isEmpty())

        rule.runOnIdle { owner.lifecycle.currentState = Lifecycle.State.RESUMED }
        rule.waitForIdle()
        assertTrue("foregrounding does not automatically start narration", factory.engines.isEmpty())
        rule.onNodeWithTag("toggle-enabled").performClick()
        rule.runOnIdle { capturedStart() }
        rule.waitForIdle()
        assertTrue("a captured start cannot bypass the current disabled state", factory.engines.isEmpty())

        rule.onNodeWithTag("toggle-enabled").performClick()
        rule.onNodeWithTag("action-lifetime-toggle").performClick()
        rule.waitUntil(5_000) { factory.engines.size == 1 && factory.engines[0].initCallback != null }
        val first = factory.engines.single()
        first.initCallback!!.invoke(true, setOf(offlineEnglishVoice()))
        rule.waitUntil(5_000) { first.utterances.isNotEmpty() }
        val capturedPause = captureAction()
        rule.onNodeWithTag("toggle-enabled").performClick()
        rule.onNodeWithTag("action-lifetime-toggle").assertIsEnabled().performClick()
        rule.onNodeWithTag("action-lifetime-toggle").assertTextEquals("Resume reading")
        assertTrue("pause remains usable while an active utterance is disabled", first.stops > 0)

        rule.onNodeWithTag("toggle-enabled").performClick()
        rule.runOnIdle { capturedPause() }
        rule.waitForIdle()
        assertEquals("an old Pause must not become Resume after the phase changes", 1, factory.engines.size)
        val capturedResume = captureAction()
        rule.onNodeWithTag("toggle-enabled").performClick()
        rule.runOnIdle { capturedResume() }
        rule.waitForIdle()
        assertEquals("a stale resume is blocked while disabled", 1, factory.engines.size)

        rule.onNodeWithTag("toggle-enabled").performClick()
        rule.onNodeWithTag("action-lifetime-toggle").performClick()
        rule.waitUntil(5_000) { factory.engines.size == 2 && factory.engines[1].initCallback != null }
        val second = factory.engines[1]
        second.initCallback!!.invoke(true, setOf(offlineEnglishVoice()))
        rule.waitUntil(5_000) { second.utterances.isNotEmpty() }
        rule.onNodeWithTag("toggle-enabled").performClick()
        rule.onNodeWithTag("action-lifetime-stop").performClick()
        rule.onNodeWithTag("action-lifetime-toggle").assertTextEquals("Read aloud")
        assertTrue("explicit stop remains usable while disabled", second.stops > 0)
    }

    private fun captureAction(): () -> Boolean {
        val node = rule.onNodeWithTag("action-lifetime-toggle").fetchSemanticsNode()
        return checkNotNull(node.config[SemanticsActions.OnClick].action)
    }

    private class TestOwner : LifecycleOwner {
        override val lifecycle = LifecycleRegistry(this)
    }

    private class Speech : ChapterSpeechAdapter {
        data class Utterance(val text: String)
        var initCallback: ((Boolean, Set<Voice>) -> Unit)? = null
        var stops = 0
        val utterances = mutableListOf<Utterance>()
        override fun initialize(done: (Boolean, Set<Voice>) -> Unit) { initCallback = done }
        override fun setVoice(voice: Voice) = true
        override fun speak(text: String, id: String, done: (String) -> Unit, failed: (String) -> Unit) {
            utterances += Utterance(text)
        }
        override fun stop() { stops++ }
        override fun shutdown() = Unit
    }

    private class SpeechFactory : ChapterSpeechAdapterFactory {
        val engines = mutableListOf<Speech>()
        override fun create(context: Context) = Speech().also(engines::add)
    }

    private class FocusFactory : ChapterAudioFocusFactory {
        override fun create(context: Context) = object : ChapterAudioFocus {
            override fun request(onLost: () -> Unit) = true
            override fun abandon() = Unit
        }
    }

    private fun offlineEnglishVoice() = Voice("generated-offline-en", Locale.ENGLISH,
        Voice.QUALITY_NORMAL, Voice.LATENCY_NORMAL, false, emptySet())
}
