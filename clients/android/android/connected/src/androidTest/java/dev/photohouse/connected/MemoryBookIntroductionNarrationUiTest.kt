package dev.photohouse.connected

import android.content.Context
import android.graphics.Bitmap
import android.speech.tts.Voice
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.Locale

/** Generated local-speech journeys; these do not qualify an installed voice provider. */
@RunWith(AndroidJUnit4::class)
class MemoryBookIntroductionNarrationUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun close() { scope.cancel() }

    @Test fun englishUiUsesSavedBookLanguageAndReadsOnlyIntroductionAt150Percent() = journey(zh = false)
    @Test fun chineseUiUsesSavedBookLanguageAndReadsOnlyIntroductionAt150Percent() = journey(zh = true)

    @Test fun blankIntroductionHasNoNarrationControls() {
        val api = GeneratedMemoirReaderApi()
        val store = ConnectedStore(api, scope, memoryCommunityApi = BlankIntroductionApi(api), memoryCommunityEnabled = true)
        val voices = SpeechFactory()
        setReaderContent(store, false, voices, FocusFactory())
        openFirstStory(store)
        rule.onNodeWithTag("memory-book-introduction-section").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-introduction-narration").assertDoesNotExist()
        assertTrue("a blank note does not initialize speech", voices.engines.isEmpty())
    }

    @Test fun navigationStopsOldIntroductionAndLateCompletionCannotChangeReader() {
        val api = GeneratedMemoirReaderApi()
        val store = newStore(api)
        val voices = SpeechFactory()
        val focus = FocusFactory()
        setReaderContent(store, false, voices, focus)
        openFirstStory(store)
        rule.onNodeWithTag("memory-book-introduction-narration-toggle").performScrollTo().performClick()
        val speech = startSpeech(voices, 0)
        rule.runOnIdle { store.loadMemoryBookChapter(1) }
        rule.waitUntil(5_000) {
            store.state.value.memoryBooks?.selectedChapter == 1 && store.state.value.memoryBooks?.framesBusy == false
        }
        rule.waitForIdle()
        assertTrue("reader navigation stops the previous scoped speech", voices.engines.first().stops > 0)
        val navigatedPosition = store.state.value.memoryBooks!!.resumePosition
        speech.done(speech.id)
        rule.waitForIdle()
        assertEquals(1, store.state.value.memoryBooks?.selectedChapter)
        assertEquals("a late completion does not replace the reader resume point", navigatedPosition,
            store.state.value.memoryBooks?.resumePosition)
        rule.onNodeWithTag("memory-book-introduction-narration-done").assertDoesNotExist()
        assertEquals(1, voices.engines.size)
        rule.onNodeWithTag("memory-book-introduction-narration-toggle").performScrollTo().performClick()
        val logoutSpeech = startSpeech(voices, 1)
        rule.runOnIdle { store.logout() }
        rule.waitUntil(5_000) { store.state.value.session == null }
        rule.waitForIdle()
        assertTrue("logout stops speech owned by the old account", voices.engines[1].stops > 0)
        logoutSpeech.done(logoutSpeech.id)
        rule.waitForIdle()
        assertEquals(0, api.originalCalls)
        assertEquals(0, api.videoCalls)
    }

    private fun journey(zh: Boolean) {
        val api = GeneratedMemoirReaderApi()
        val store = newStore(api)
        val voices = SpeechFactory()
        setReaderContent(store, zh, voices, FocusFactory())
        openFirstStory(store)

        assertTrue("opening a memoir must not start speech", voices.engines.isEmpty())
        rule.onNodeWithTag("memory-book-introduction-section").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("memory-book-introduction-narration-toggle").assertTextEquals(
            if (zh) "朗读开篇" else "Read introduction aloud")
        capture(zh)
        val before = store.state.value.memoryBooks!!
        val childReadsBefore = api.childReads
        rule.onNodeWithTag("memory-book-introduction-narration-toggle").performScrollTo().performClick()
        val utterance = startSpeech(voices, 0)

        assertEquals("Only the saved introduction is spoken", "A generated reading fixture.", utterance.text)
        assertEquals("Voice selection follows the saved book language", "zh", voices.engines.single().selectedVoice?.locale?.language)
        rule.onNodeWithTag("memory-book-introduction-narration-toggle").assertTextEquals(
            if (zh) "暂停朗读" else "Pause introduction")
        rule.onNodeWithTag("memory-book-introduction-narration-toggle").performClick()
        rule.onNodeWithTag("memory-book-introduction-narration-toggle").assertTextEquals(
            if (zh) "继续朗读" else "Resume introduction")
        utterance.done(utterance.id)
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-introduction-narration-done").assertDoesNotExist()
        rule.onNodeWithTag("memory-book-introduction-narration-toggle").performClick()
        val replay = startSpeech(voices, 1)
        assertEquals(utterance.text, replay.text)
        replay.done(replay.id)
        rule.waitForIdle()
        rule.onNodeWithTag("memory-book-introduction-narration-done").assertExists()
        val after = store.state.value.memoryBooks!!
        assertEquals(before.storyIndex, after.storyIndex)
        assertEquals(before.selectedChapter, after.selectedChapter)
        assertEquals(before.framePage, after.framePage)
        assertEquals(before.selectedAssetId, after.selectedAssetId)
        assertEquals(before.resumePosition, after.resumePosition)
        assertEquals("speech completion does not reread a child story", childReadsBefore, api.childReads)
        assertEquals(0, api.originalCalls)
        assertEquals(0, api.videoCalls)
        assertEquals(2, voices.engines.size)
    }

    private fun newStore(api: GeneratedMemoirReaderApi) = ConnectedStore(api, scope,
        memoryCommunityApi = api, memoryCommunityEnabled = true)

    private fun setReaderContent(store: ConnectedStore, zh: Boolean, voices: SpeechFactory, focus: FocusFactory) {
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(
                LocalDensity provides Density(density.density, 1.5f),
                LocalChapterSpeechAdapterFactory provides voices,
                LocalChapterAudioFocusFactory provides focus,
            ) {
                val state by store.state.collectAsState()
                state.memoryBooks?.let { reading ->
                    MemoryBooksDialog(reading, store, zh, store::openMemoryBooks, store::openMemoryBook,
                        store::loadMemoryBookStory, store::resumeMemoryBookReading,
                        { store.loadMemoryBookChapter(it) }, store::loadMemoryBookFramePage,
                        store::selectMemoryBookAsset, {}, store::closeMemoryBook, store::closeMemoryBooks)
                }
            }
        }
    }

    private fun openFirstStory(store: ConnectedStore) {
        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5_000) { store.state.value.library == GeneratedMemoirReaderApi.LIBRARY }
        rule.runOnIdle { store.openMemoryBooks() }
        rule.waitUntil(5_000) { store.state.value.memoryBooks?.result != null }
        rule.runOnIdle { store.openMemoryBook(GeneratedMemoirReaderApi.BOOK) }
        rule.waitUntil(5_000) {
            store.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy } == true
        }
        rule.runOnIdle { store.loadMemoryBookStory(0) }
        rule.waitUntil(5_000) {
            store.state.value.memoryBooks?.let { it.story != null && !it.framesBusy } == true
        }
    }

    private fun startSpeech(factory: SpeechFactory, index: Int): Speech.Utterance {
        rule.waitUntil(5_000) { factory.engines.size > index && factory.engines[index].init != null }
        val engine = factory.engines[index]
        engine.init!!.invoke(true, setOf(
            Voice("generated-offline-en", Locale.ENGLISH, Voice.QUALITY_NORMAL, Voice.LATENCY_NORMAL, false, emptySet()),
            Voice("generated-offline-zh", Locale.SIMPLIFIED_CHINESE, Voice.QUALITY_NORMAL, Voice.LATENCY_NORMAL, false, emptySet()),
        ))
        rule.waitUntil(5_000) { engine.spoken.isNotEmpty() }
        return engine.spoken.single()
    }

    private fun capture(zh: Boolean) {
        val bitmap = rule.onNodeWithTag("memory-book-introduction-section").captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir,
            "memory-book-introduction-narration-${if (zh) "zh" else "en"}-150.png").outputStream().use {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
    }

    private class Speech : ChapterSpeechAdapter {
        data class Utterance(val id: String, val text: String, val done: (String) -> Unit)
        var init: ((Boolean, Set<Voice>) -> Unit)? = null
        var selectedVoice: Voice? = null
        var stops = 0
        val spoken = mutableListOf<Utterance>()
        override fun initialize(done: (Boolean, Set<Voice>) -> Unit) { init = done }
        override fun setVoice(voice: Voice): Boolean { selectedVoice = voice; return true }
        override fun speak(text: String, id: String, done: (String) -> Unit, failed: (String) -> Unit) {
            spoken += Utterance(id, text, done)
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

    private class BlankIntroductionApi(private val delegate: GeneratedMemoirReaderApi) :
        PhotoHouseApi by delegate, MemoryCommunityApi by delegate {
        override suspend fun getBook(token: Bearer, library: String, bookId: String): ByteArray =
            delegate.getBook(token, library, bookId).decodeToString()
                .replace("A generated reading fixture.", "").toByteArray()
    }
}
