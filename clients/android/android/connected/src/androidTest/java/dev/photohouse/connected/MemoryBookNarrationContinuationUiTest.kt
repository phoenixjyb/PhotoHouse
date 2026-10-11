package dev.photohouse.connected

import android.content.Context
import android.graphics.Bitmap
import android.speech.tts.Voice
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import kotlinx.coroutines.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import java.io.File
import java.util.Locale

/** Synthetic speech completion, not installed engine or audible voice qualification. */
class MemoryBookNarrationContinuationUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun close() { scope.cancel() }

    @Test fun chineseExplicitNextChapterNarrationAt150Percent() = journey(true)
    @Test fun englishExplicitNextChapterNarrationAt150Percent() = journey(false)

    private fun journey(zh: Boolean) {
        val api = GeneratedMemoirReaderApi()
        val store = newStore(api)
        val voices = SpeechFactory()
        val focus = FocusFactory()
        rule.setContent {
            CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density, 1.5f),
                LocalChapterSpeechAdapterFactory provides voices, LocalChapterAudioFocusFactory provides focus) {
                val state by store.state.collectAsState()
                state.memoryBooks?.let { reading ->
                    MemoryBooksDialog(reading, store, zh, store::openMemoryBooks, store::openMemoryBook,
                        store::loadMemoryBookStory, store::resumeMemoryBookReading, { store.loadMemoryBookChapter(it) },
                        store::loadMemoryBookFramePage, store::selectMemoryBookAsset, {},
                        store::closeMemoryBook, store::closeMemoryBooks)
                }
            }
        }
        openFirstStory(store)
        assertTrue("opening a story never starts speech", voices.engines.isEmpty())
        rule.onNodeWithTag("memory-book-continue-narration").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-narration-toggle").performScrollTo().performClick()
        finish(voices, 0)
        rule.onNodeWithTag("memory-book-continue-narration").performScrollTo().assertIsDisplayed()
        capture(zh)
        assertEquals("completion alone does not advance", 0, store.state.value.memoryBooks!!.selectedChapter)
        assertEquals(1, voices.engines.size)
        val oldUtterance = voices.engines.first().spoken.single()

        rule.onNodeWithTag("memory-book-continue-narration").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedChapter == 1 && voices.engines.size == 2 }
        initialize(voices.engines[1])
        assertTrue(voices.engines[1].spoken.single().text.contains("Chapter 2"))
        oldUtterance.done(oldUtterance.id)
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-continue-narration").assertDoesNotExist()
        assertEquals("late old completion cannot advance or start another engine", 2, voices.engines.size)

        rule.onNodeWithTag("memory-book-narration-stop").performClick()
        rule.onNodeWithTag("memory-book-continue-narration").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-narration-toggle").performClick()
        finish(voices, 2)
        rule.onNodeWithTag("memory-book-continue-narration").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedChapter == 2 && voices.engines.size == 4 }
        finish(voices, 3)
        rule.onNodeWithTag("memory-book-continue-narration").assertDoesNotExist()
        rule.runOnIdle {
            assertEquals("last chapter never crosses to another story", 0, store.state.value.memoryBooks!!.storyIndex)
            assertEquals(2, store.state.value.memoryBooks!!.selectedChapter)
            assertEquals(1, api.childReads)
            assertEquals(0, api.originalCalls); assertEquals(0, api.videoCalls)
            assertEquals(4, voices.engines.size)
        }
    }

    @Test fun nextChapterRequestBlockedByRecordingNeedsAnotherExplicitStart() {
        val api = GeneratedMemoirReaderApi()
        val store = newStore(api)
        val voices = SpeechFactory()
        val coordinator = ReaderAudioCoordinator()
        val focus = FocusFactory()
        rule.setContent {
            CompositionLocalProvider(LocalReaderAudioCoordinator provides coordinator,
                LocalChapterSpeechAdapterFactory provides voices, LocalChapterAudioFocusFactory provides focus) {
                PhotoHouseTheme {
                    val state by store.state.collectAsState()
                    if (state.memoryBooks?.story != null) Column { MemoryBookChapterNarration(store, true) }
                }
            }
        }
        openFirstStory(store)
        rule.onNodeWithTag("memory-book-narration-toggle").performClick()
        finish(voices, 0)
        lateinit var recording: ReaderAudioCoordinator.Lease
        rule.runOnIdle { recording = coordinator.acquire(ReaderAudioKind.RECORDING) {}!! }
        rule.onNodeWithTag("memory-book-continue-narration").performClick()
        rule.waitUntil(5000) { store.state.value.memoryBooks?.selectedChapter == 1 }
        rule.onNodeWithTag("memory-book-narration-busy").assertExists()
        assertEquals(1, voices.engines.size)
        rule.runOnIdle { coordinator.release(recording) }
        rule.waitForIdle()
        assertEquals("ending a recording does not retry the consumed request", 1, voices.engines.size)
        rule.onNodeWithTag("memory-book-narration-toggle").performClick()
        rule.waitUntil(5000) { voices.engines.size == 2 }
        initialize(voices.engines.last())
        val pendingUtterance = voices.engines.last().spoken.single()
        rule.runOnIdle { store.logout() }
        pendingUtterance.done(pendingUtterance.id)
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-continue-narration").assertDoesNotExist()
        assertEquals(2, voices.engines.size)
    }

    private fun newStore(api: GeneratedMemoirReaderApi) = ConnectedStore(api, scope,
        memoryCommunityApi = api, memoryCommunityEnabled = true)

    private fun openFirstStory(store: ConnectedStore) {
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5000) { store.state.value.library == GeneratedMemoirReaderApi.LIBRARY }
        rule.runOnIdle { store.openMemoryBooks() }
        rule.waitUntil(5000) { store.state.value.memoryBooks?.result != null }
        rule.runOnIdle { store.openMemoryBook(GeneratedMemoirReaderApi.BOOK) }
        rule.waitUntil(5000) { store.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy } == true }
        rule.runOnIdle { store.loadMemoryBookStory(0) }
        rule.waitUntil(5000) { store.state.value.memoryBooks?.let { it.story != null && !it.framesBusy } == true }
    }

    private fun initialize(engine: Speech) {
        rule.waitUntil(5000) { engine.init != null }
        engine.init!!.invoke(true, setOf(Voice("generated-offline-zh", Locale.SIMPLIFIED_CHINESE,
            Voice.QUALITY_NORMAL, Voice.LATENCY_NORMAL, false, emptySet())))
        rule.waitUntil(5000) { engine.spoken.isNotEmpty() }
    }

    private fun finish(factory: SpeechFactory, index: Int) {
        rule.waitUntil(5000) { factory.engines.size > index }
        val engine = factory.engines[index]
        initialize(engine)
        val utterance = engine.spoken.single()
        utterance.done(utterance.id)
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-narration-done").assertExists()
    }

    private fun capture(zh: Boolean) {
        val bitmap = rule.onNodeWithTag("memory-book-chapter-narration").captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,
            "memoir-next-narration-${if (zh) "zh" else "en"}-150.png").outputStream().use {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
    }

    private class Speech : ChapterSpeechAdapter {
        data class Utterance(val id: String, val text: String, val done: (String) -> Unit)
        var init: ((Boolean, Set<Voice>) -> Unit)? = null
        val spoken = mutableListOf<Utterance>()
        override fun initialize(done: (Boolean, Set<Voice>) -> Unit) { init = done }
        override fun setVoice(voice: Voice) = true
        override fun speak(text: String, id: String, done: (String) -> Unit, failed: (String) -> Unit) {
            spoken += Utterance(id, text, done)
        }
        override fun stop() = Unit
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
}
