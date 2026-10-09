package dev.photohouse.connected

import android.content.Context
import android.content.ContentValues
import android.graphics.Bitmap
import android.os.Environment
import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.width
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class ChapterReadAloudUiTest {
    @get:Rule val rule = createComposeRule()

    private fun capture(name: String) {
        val bitmap = rule.onRoot().captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val values = ContentValues().apply {
            put(android.provider.MediaStore.Images.Media.DISPLAY_NAME, "chapter-readaloud-$name.png")
            put(android.provider.MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(android.provider.MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/PhotoHouseChapterReadAloud")
        }
        val uri = checkNotNull(context.contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        context.contentResolver.openOutputStream(uri).use { out -> checkNotNull(out); check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)) }
        bitmap.recycle()
    }

    private class FakeSpeech : ChapterSpeechAdapter {
        data class Utterance(val id: String, val text: String, val done: (String) -> Unit)
        var init: ((Boolean, Set<Voice>) -> Unit)? = null
        val spoken = mutableListOf<Utterance>()
        var stops = 0
        var shutdowns = 0
        var throwOnSpeak = false
        var throwOnStop = false
        override fun initialize(done: (Boolean, Set<Voice>) -> Unit) { init = done }
        override fun setVoice(voice: Voice) = true
        override fun speak(text: String, id: String, done: (String) -> Unit, failed: (String) -> Unit) {
            if (throwOnSpeak) error("synthetic TTS failure")
            spoken += Utterance(id, text, done)
        }
        override fun stop() { stops++; if (throwOnStop) error("synthetic stop failure") }
        override fun shutdown() { shutdowns++ }
    }
    private class FakeFactory(private val throwOnCreate: Boolean = false, private val throwOnSpeak: Boolean = false, private val throwOnStop: Boolean = false) : ChapterSpeechAdapterFactory {
        val engines = mutableListOf<FakeSpeech>()
        override fun create(context: Context): ChapterSpeechAdapter {
            if (throwOnCreate) error("synthetic TTS creation failure")
            return FakeSpeech().also { it.throwOnSpeak = throwOnSpeak; it.throwOnStop = throwOnStop }.also(engines::add)
        }
    }
    private class FakeFocusFactory(private val grant: Boolean = true) : ChapterAudioFocusFactory {
        var abandoned = 0
        override fun create(context: Context) = object : ChapterAudioFocus {
            override fun request(onLost: () -> Unit) = grant
            override fun abandon() { abandoned++ }
        }
    }

    @Test fun stopAndScopeChangeIgnoreLateInitializationAndUtteranceCallbacks() {
        val engines = FakeFactory()
        val coordinator = ReaderAudioCoordinator()
        rule.setContent {
            var scope by remember { mutableStateOf<Any>(listOf("story", "one")) }
            CompositionLocalProvider(LocalReaderAudioCoordinator provides coordinator,
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                Column {
                    ChapterReadAloud("A short chapter. ${"More words. ".repeat(30)}", "en", scope, false)
                    Button(onClick = { scope = listOf("story", "two") }, modifier = Modifier.testTag("scope-change")) { Text("Next") }
                }
            }
        }
        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        val first = engines.engines.single()
        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        first.init?.invoke(true, setOf(offlineVoice("en")))
        rule.runOnIdle { assertTrue(first.spoken.isEmpty()) }

        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        val second = engines.engines.last()
        second.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        assertEquals(1, second.spoken.size)
        val firstUtterance = second.spoken.first()
        Thread { firstUtterance.done(firstUtterance.id); firstUtterance.done(firstUtterance.id) }.apply { start(); join() }
        rule.waitForIdle()
        assertEquals(2, second.spoken.size)
        firstUtterance.done(firstUtterance.id)
        rule.runOnIdle { assertEquals(2, second.spoken.size) }
        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        val late = second.spoken.last()
        late.done(late.id)
        rule.runOnIdle { assertEquals(2, second.spoken.size) }

        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        val third = engines.engines.last()
        rule.onNodeWithTag("scope-change").performClick()
        rule.waitForIdle()
        third.init?.invoke(true, setOf(offlineVoice("en")))
        rule.runOnIdle { assertTrue(third.spoken.isEmpty()); assertTrue(third.shutdowns > 0) }
    }

    @Test fun refusesNetworkOrNotInstalledVoices() {
        val engines = FakeFactory()
        rule.setContent {
            CompositionLocalProvider(LocalReaderAudioCoordinator provides ReaderAudioCoordinator(),
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                ChapterReadAloud("本章内容。", "zh", "story-test", true)
            }
        }
        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        val engine = engines.engines.single()
        val network = Voice("network-zh", Locale.SIMPLIFIED_CHINESE, Voice.QUALITY_NORMAL, Voice.LATENCY_NORMAL, true, emptySet())
        val missing = Voice("missing-zh", Locale.SIMPLIFIED_CHINESE, Voice.QUALITY_NORMAL, Voice.LATENCY_NORMAL, false,
            setOf(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED))
        engine.init?.invoke(true, setOf(network, missing))
        rule.onNodeWithTag("saved-memory-narration-unavailable").assertExists()
        capture("offline-voice-unavailable")
        assertTrue(engine.spoken.isEmpty())
    }

    @Test fun pauseResumeReplaysOnlyCurrentBoundedChunkAndIgnoresLateCallbacks() {
        val engines = FakeFactory()
        val coordinator = ReaderAudioCoordinator()
        val reply = "First bounded segment. ${"More reply text. ".repeat(32)}"
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalReaderAudioCoordinator provides coordinator,
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                CompositionLocalProvider(LocalDensity provides Density(base.density, 1.5f)) {
                    PhotoHouseTheme { ChapterReadAloud(reply, "en", listOf("story", "conversation", "turn", reply), false,
                        labels = ChapterReadAloudLabels("Read reply", "Stop reading", "reply-reading", pause = "Pause reply", resume = "Resume reply")) }
                }
            }
        }
        rule.onNodeWithTag("reply-reading-toggle").assertTextEquals("Read reply")
        assertTrue("reply speech must not autoplay", engines.engines.isEmpty())
        rule.onNodeWithTag("reply-reading-toggle").performClick()
        val firstEngine = engines.engines.single()
        firstEngine.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        val chunks = narrationChunks(reply)
        assertEquals(chunks.first(), firstEngine.spoken.single().text)
        val firstUtterance = firstEngine.spoken.single()
        firstUtterance.done(firstUtterance.id)
        rule.waitForIdle()
        val secondUtterance = firstEngine.spoken[1]
        assertEquals(chunks[1], secondUtterance.text)
        rule.onNodeWithTag("reply-reading-toggle").performClick()
        rule.onNodeWithTag("reply-reading-toggle").assertTextEquals("Resume reply")
        rule.onNodeWithTag("reply-reading-paused-notice").assertExists()
        rule.onNodeWithTag("reply-reading-stop").assertIsEnabled()
        assertTrue(firstEngine.shutdowns > 0)
        secondUtterance.done(secondUtterance.id)
        secondUtterance.done(secondUtterance.id)
        rule.waitForIdle()
        assertEquals("stale/duplicate callbacks after pause are ignored", 2, firstEngine.spoken.size)
        capture("reply-paused-en-150")
        val recording = coordinator.acquire(ReaderAudioKind.RECORDING) {}!!
        coordinator.release(recording)
        rule.onNodeWithTag("reply-reading-toggle").performClick()
        val resumedEngine = engines.engines.last()
        resumedEngine.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        assertEquals("resume replays the current short chunk, not the whole reply", chunks[1], resumedEngine.spoken.single().text)
        val resumedText = resumedEngine.spoken.single().text
        assertTrue(resumedText.codePointCount(0, resumedText.length) <= 180)
        assertTrue(resumedText.toByteArray(Charsets.UTF_8).size <= 720)
        resumedEngine.spoken.single().done(resumedEngine.spoken.single().id)
        rule.waitForIdle()
        assertEquals("following chunk continues in order", chunks[2], resumedEngine.spoken.last().text)
        capture("reply-pause-resume-en-150")
        rule.onNodeWithTag("reply-reading-stop").performClick()
        rule.onNodeWithTag("reply-reading-toggle").assertTextEquals("Read reply")
    }

    @Test fun pausedResumeWaitsForRecordingAndStopRemainsAvailableWhenReplyIsBusy() {
        val engines = FakeFactory()
        val coordinator = ReaderAudioCoordinator()
        var enabled by mutableStateOf(true)
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalReaderAudioCoordinator provides coordinator,
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                CompositionLocalProvider(LocalDensity provides Density(base.density, 1.5f)) {
                    PhotoHouseTheme { Column {
                        ChapterReadAloud("A reply with several bounded chunks. ${"More words. ".repeat(25)}", "en", "recording-pause", true,
                            enabled = enabled, labels = ChapterReadAloudLabels("朗读回复", "停止朗读", "recording-reply",
                                pause = "暂停回复朗读", resume = "继续回复朗读"))
                    } }
                }
            }
        }
        rule.onNodeWithTag("recording-reply-toggle").performClick()
        val speech = engines.engines.single()
        speech.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        rule.onNodeWithTag("recording-reply-toggle").performClick()
        val recording = coordinator.acquire(ReaderAudioKind.RECORDING) {}!!
        rule.onNodeWithTag("recording-reply-toggle").performClick()
        rule.onNodeWithTag("recording-reply-paused-busy").assertExists()
        rule.onNodeWithTag("recording-reply-toggle").assertTextEquals("继续回复朗读")
        rule.onNodeWithTag("recording-reply-stop").assertIsEnabled()
        assertEquals("resume while recording does not allocate another TTS engine", 1, engines.engines.size)
        assertTrue(coordinator.isOwned(recording))
        rule.runOnIdle { enabled = false }
        rule.onNodeWithTag("recording-reply-toggle").assertIsNotEnabled()
        rule.onNodeWithTag("recording-reply-stop").assertIsEnabled()
        capture("reply-paused-recording-zh-150")
        coordinator.release(recording)
        rule.runOnIdle { enabled = true }
        rule.onNodeWithTag("recording-reply-toggle").performClick()
        val resumed = engines.engines.last()
        resumed.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        assertEquals(2, engines.engines.size)
        rule.runOnIdle { enabled = false }
        rule.onNodeWithTag("recording-reply-stop").assertIsEnabled().performClick()
        rule.onNodeWithTag("recording-reply-paused-notice").assertDoesNotExist()
        rule.onNodeWithTag("recording-reply-toggle").assertIsNotEnabled()
    }

    @Test fun disposingOldReplyCannotStopNewerSpeechLease() {
        val engines = FakeFactory()
        val coordinator = ReaderAudioCoordinator()
        rule.setContent {
            var showOld by remember { mutableStateOf(true) }
            CompositionLocalProvider(LocalReaderAudioCoordinator provides coordinator,
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                PhotoHouseTheme { Column {
                    if (showOld) ChapterReadAloud("Old reply", "en", "old-reply", false,
                        labels = ChapterReadAloudLabels("Read old", "Stop old", "old-reply"))
                    ChapterReadAloud("New reply", "en", "new-reply", false,
                        labels = ChapterReadAloudLabels("Read new", "Stop new", "new-reply"))
                    Button(onClick = { showOld = false }, modifier = Modifier.testTag("dispose-old-reply")) { Text("Hide old") }
                } }
            }
        }
        rule.onNodeWithTag("old-reply-toggle").performClick()
        val oldEngine = engines.engines.single()
        oldEngine.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        rule.onNodeWithTag("new-reply-toggle").performClick()
        val newEngine = engines.engines.last()
        newEngine.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        assertTrue("new lease stops prior reply", oldEngine.stops > 0)
        rule.onNodeWithTag("dispose-old-reply").performClick()
        rule.waitForIdle()
        assertEquals("old row disposal must not stop newer speech", 0, newEngine.stops)
        rule.onNodeWithTag("new-reply-toggle").assertTextEquals("Pause reading")
        rule.onNodeWithTag("new-reply-stop").assertIsDisplayed()
        assertTrue(newEngine.spoken.isNotEmpty())
        val oldCallback = oldEngine.spoken.firstOrNull()
        oldCallback?.done?.invoke(oldCallback.id)
        rule.waitForIdle()
        assertEquals(0, newEngine.stops)
    }

    @Test fun changedReplyScopeCannotInheritPausedChunkCursor() {
        val engines = FakeFactory()
        val coordinator = ReaderAudioCoordinator()
        val oldReply = "Old reply chunk. ${"Old words. ".repeat(24)}"
        rule.setContent {
            var showNew by remember { mutableStateOf(false) }
            CompositionLocalProvider(LocalReaderAudioCoordinator provides coordinator,
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                PhotoHouseTheme { Column {
                    val text = if (showNew) "New reply begins from its first word." else oldReply
                    ChapterReadAloud(text, "en", listOf("reply", if (showNew) "new-turn" else "old-turn", text), false,
                        labels = ChapterReadAloudLabels("Read reply", "Stop reading", "scope-reply"))
                    Button(onClick = { showNew = true }, modifier = Modifier.testTag("reply-scope-next")) { Text("Next reply") }
                } }
            }
        }
        rule.onNodeWithTag("scope-reply-toggle").performClick()
        val oldEngine = engines.engines.single()
        oldEngine.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        oldEngine.spoken.first().done(oldEngine.spoken.first().id)
        rule.waitForIdle()
        rule.onNodeWithTag("scope-reply-toggle").performClick()
        rule.onNodeWithTag("scope-reply-paused-notice").assertExists()
        rule.onNodeWithTag("reply-scope-next").performClick()
        rule.waitForIdle()
        assertTrue(oldEngine.shutdowns > 0)
        rule.onNodeWithTag("scope-reply-toggle").assertTextEquals("Read reply")
        rule.onNodeWithTag("scope-reply-toggle").performClick()
        val newEngine = engines.engines.last()
        newEngine.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        assertEquals("New reply begins from its first word.", newEngine.spoken.single().text)
    }

    @Test fun unsupportedReplyLanguageKeepsTextAndReportsNoLocalVoice() {
        val engines = FakeFactory()
        val source = "保留显示的完整回复"
        rule.setContent {
            CompositionLocalProvider(LocalReaderAudioCoordinator provides ReaderAudioCoordinator(),
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                PhotoHouseTheme {
                    Column {
                        Text(source, modifier = Modifier.testTag("reply-source-text"))
                        ChapterReadAloud(source, "fr", "unsupported-reply", true,
                            labels = ChapterReadAloudLabels("朗读回复", "停止朗读", "unsupported-reply"))
                    }
                }
            }
        }
        assertEquals("fr" to false, replySpeechLanguage("fr-FR", true))
        assertEquals("zh" to true, replySpeechLanguage("mixed", true))
        assertEquals("en" to true, replySpeechLanguage("und", false))
        rule.onNodeWithTag("reply-source-text").assertTextEquals(source)
        assertTrue(engines.engines.isEmpty())
        rule.onNodeWithTag("unsupported-reply-toggle").performClick()
        val engine = engines.engines.single()
        engine.init?.invoke(true, setOf(offlineVoice("zh"), offlineVoice("en")))
        rule.onNodeWithTag("unsupported-reply-unavailable").assertExists()
        rule.onNodeWithTag("reply-source-text").assertTextEquals(source)
        assertTrue("unsupported language must not synthesize via a fallback voice", engine.spoken.isEmpty())
    }

    @Test fun replyCompletionUsesReplySpecificStatus() {
        val engines = FakeFactory()
        rule.setContent {
            CompositionLocalProvider(LocalReaderAudioCoordinator provides ReaderAudioCoordinator(),
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                PhotoHouseTheme {
                    ChapterReadAloud("A reply.", "en", "reply-completion", false,
                        labels = ChapterReadAloudLabels("Read reply", "Stop reading", "reply-completion",
                            done = "Finished reading this reply."))
                }
            }
        }
        rule.onNodeWithTag("reply-completion-toggle").performClick()
        val engine = engines.engines.single()
        engine.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        val utterance = engine.spoken.single()
        utterance.done(utterance.id)
        rule.waitForIdle()
        rule.onNodeWithTag("reply-completion-done").assertTextEquals("Finished reading this reply.")
    }

    @Test fun narrationReportsBusyWithoutPreemptingRecording() {
        val engines = FakeFactory()
        val coordinator = ReaderAudioCoordinator()
        var recordingStopped = false
        val recording = coordinator.acquire(ReaderAudioKind.RECORDING) { recordingStopped = true }!!
        rule.setContent {
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(base.density, 1.5f),
                LocalReaderAudioCoordinator provides coordinator,
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                Column { ChapterReadAloud("Chapter text", "en", "story-busy", false) }
            }
        }
        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        rule.onNodeWithTag("saved-memory-narration-busy").assertExists()
        capture("busy-recording")
        assertTrue(engines.engines.isEmpty())
        assertTrue(coordinator.isOwned(recording))
        assertTrue(!recordingStopped)
    }

    @Test fun lifecyclePauseStopsAndInvalidatesPendingChunkCallback() {
        val engines = FakeFactory()
        val lifecycleOwner = object : LifecycleOwner { override val lifecycle = LifecycleRegistry(this) }
        rule.runOnIdle { lifecycleOwner.lifecycle.currentState = Lifecycle.State.RESUMED }
        rule.setContent {
            CompositionLocalProvider(LocalLifecycleOwner provides lifecycleOwner,
                LocalReaderAudioCoordinator provides ReaderAudioCoordinator(),
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                ChapterReadAloud("${"Many words. ".repeat(40)}", "en", "story-background", false)
            }
        }
        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        val engine = engines.engines.single()
        engine.init?.invoke(true, setOf(offlineVoice("en")))
        rule.waitForIdle()
        assertEquals(1, engine.spoken.size)
        rule.runOnIdle { lifecycleOwner.lifecycle.currentState = Lifecycle.State.STARTED }
        val stale = engine.spoken.first()
        Thread { stale.done(stale.id) }.apply { start(); join() }
        rule.waitForIdle()
        assertEquals(1, engine.spoken.size)
        assertTrue(engine.shutdowns > 0)
        rule.runOnIdle { lifecycleOwner.lifecycle.currentState = Lifecycle.State.RESUMED }
        rule.waitForIdle()
        assertEquals("returning to foreground never auto-resumes narration", 1, engine.spoken.size)
        rule.onNodeWithTag("saved-memory-narration-toggle").assertTextEquals("Read aloud")
    }

    @Test fun focusFailureReleasesSpeechLeaseAndDoesNotAllocateTts() {
        val engines = FakeFactory()
        val focus = FakeFocusFactory(grant = false)
        val coordinator = ReaderAudioCoordinator()
        rule.setContent {
            CompositionLocalProvider(LocalReaderAudioCoordinator provides coordinator,
                LocalChapterSpeechAdapterFactory provides engines,
                LocalChapterAudioFocusFactory provides focus) {
                ChapterReadAloud("A reply.", "en", "focus-denied", false)
            }
        }
        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        rule.onNodeWithTag("saved-memory-narration-focus").assertExists()
        assertTrue(engines.engines.isEmpty())
        assertEquals(1, focus.abandoned)
        val recording = coordinator.acquire(ReaderAudioKind.RECORDING) {}
        assertTrue("failed focus request must release the speech lease", recording != null)
        coordinator.release(recording)
    }

    @Test fun throwingProviderAndUtteranceFailuresReleaseAudioOwnership() {
        val coordinator = ReaderAudioCoordinator()
        val factory = FakeFactory(throwOnCreate = true)
        val secondCoordinator = ReaderAudioCoordinator()
        val speakingFactory = FakeFactory(throwOnSpeak = true, throwOnStop = true)
        rule.setContent {
            var switch by remember { mutableStateOf(false) }
            val activeCoordinator = if (switch) secondCoordinator else coordinator
            val activeFactory = if (switch) speakingFactory else factory
            CompositionLocalProvider(LocalReaderAudioCoordinator provides activeCoordinator,
                LocalChapterSpeechAdapterFactory provides activeFactory,
                LocalChapterAudioFocusFactory provides FakeFocusFactory()) {
                Column {
                    ChapterReadAloud("Text", "en", if (switch) "story-throws-speak" else "story-throws-create", false)
                    Button(onClick = { switch = true }, modifier = Modifier.testTag("throwing-switch")) { Text("Next") }
                }
            }
        }
        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        rule.onNodeWithText("Reading stopped after an audio error.").assertExists()
        capture("provider-error")
        val firstCapture = coordinator.acquire(ReaderAudioKind.RECORDING) { }!!
        coordinator.release(firstCapture)

        rule.onNodeWithTag("throwing-switch").performClick()
        rule.onNodeWithTag("saved-memory-narration-toggle").performClick()
        val engine = speakingFactory.engines.single()
        engine.init?.invoke(true, setOf(offlineVoice("en")))
        rule.onNodeWithText("Reading stopped after an audio error.").assertExists()
        assertTrue(engine.shutdowns > 0)
        assertTrue(secondCoordinator.acquire(ReaderAudioKind.RECORDING) { } != null)
    }

    @Test fun installedEngineVoiceInventoryIsMetadataOnly() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val initialized = CountDownLatch(1)
        var initStatus = TextToSpeech.ERROR
        val engine = TextToSpeech(context) { status -> initStatus = status; initialized.countDown() }
        try {
            assertTrue("TTS engine initialization timed out", initialized.await(15, TimeUnit.SECONDS))
            assertEquals(TextToSpeech.SUCCESS, initStatus)
            val voices = engine.voices.orEmpty()
            val zhCount = voices.count { it.locale.language == "zh" && selectOfflineVoice(setOf(it), "zh") != null }
            val enCount = voices.count { it.locale.language == "en" && selectOfflineVoice(setOf(it), "en") != null }
            android.util.Log.i("ChapterReadAloudVoiceInventory", "metadata-only eligibleOfflineZh=$zhCount eligibleOfflineEn=$enCount voices=${voices.size}; no speak/install requested")
            assertEquals("selector must reject network and uninstalled voices", zhCount,
                voices.count { it.locale.language == "zh" && !it.isNetworkConnectionRequired && TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED !in it.features.orEmpty() })
            assertEquals("selector must reject network and uninstalled voices", enCount,
                voices.count { it.locale.language == "en" && !it.isNetworkConnectionRequired && TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED !in it.features.orEmpty() })
        } finally {
            runCatching { engine.stop() }
            engine.shutdown()
        }
    }

    private fun offlineVoice(language: String) = Voice("installed-$language", if (language == "zh") Locale.SIMPLIFIED_CHINESE else Locale.US,
        Voice.QUALITY_NORMAL, Voice.LATENCY_NORMAL, false, emptySet())
}
