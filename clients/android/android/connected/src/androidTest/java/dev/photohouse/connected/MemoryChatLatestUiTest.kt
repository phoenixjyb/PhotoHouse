package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.SoftwareKeyboardController
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.unit.Density
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.ConnectedStore
import dev.photohouse.connected.core.Bearer
import dev.photohouse.connected.core.MemoryCommunityApi
import dev.photohouse.connected.core.PhotoHouseApi
import dev.photohouse.connected.core.SavedMemoryStoryPage
import dev.photohouse.connected.core.SavedMemoryStorySummary
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class MemoryChatLatestUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun close() { scope.cancel() }

    @Test fun englishStoryLatestPagePreservesComposerAndRejectsDetachedThreadActionAt150Percent() =
        journey("en", memoir = false)

    @Test fun chineseStoryLatestPagePreservesComposerAndRejectsDetachedThreadActionAt150Percent() =
        journey("zh", memoir = false)

    @Test fun englishMemoirLatestPagePreservesComposerAndRejectsDetachedReaderActionAt150Percent() =
        journey("en", memoir = true)

    @Test fun chineseMemoirLatestPagePreservesComposerAndRejectsDetachedReaderActionAt150Percent() =
        journey("zh", memoir = true)

    private fun journey(language: String, memoir: Boolean) {
        val api = FixtureApi()
        val store = ConnectedStore(api, scope, memoryCommunityApi = api, memoryCommunityEnabled = true)
        var keyboardController: SoftwareKeyboardController? = null
        rule.setContent {
            val keyboard = LocalSoftwareKeyboardController.current
            SideEffect { keyboardController = keyboard }
            val base = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(base.density, 1.5f)) {
                ConnectedApp(store, initialLanguage = language)
            }
        }

        rule.runOnIdle { store.authenticate("+12025550123", "synthetic-password") }
        rule.waitUntil(5_000) { store.state.value.library == GeneratedMemoirReaderApi.LIBRARY }
        openConversation(store, memoir)
        awaitPage(store, memoir, 1)

        val prefix = if (memoir) "memory-book-chat" else "memory-chat"
        val pageTag = "$prefix-page"
        val latestTag = "$prefix-latest"
        val draftTag = "$prefix-input"
        val renderedTarget = if (memoir) store.state.value.memoryBooks?.companion?.conversationId
            else store.state.value.savedMemoryStories?.community?.conversationId
        assertNotNull("a generated conversation is selected", renderedTarget)

        rule.onNodeWithTag(draftTag).performScrollTo().performTextInput("Unsent follow-up draft")
        rule.waitUntil(5_000) {
            if (memoir) store.state.value.memoryBooks?.companion?.draft == "Unsent follow-up draft"
            else store.state.value.savedMemoryStories?.community?.chatDraft == "Unsent follow-up draft"
        }
        rule.runOnIdle { keyboardController?.hide() }

        rule.onNodeWithTag("$prefix-next").performScrollTo().performClick()
        awaitPage(store, memoir, 2)
        rule.onNodeWithTag("$prefix-next").performScrollTo().performClick()
        awaitPage(store, memoir, 3)
        rule.onNodeWithTag(latestTag).performScrollTo().assertExists()
        rule.onNodeWithTag(pageTag).performScrollTo().assertTextEquals(
            if (language == "zh") "更早的消息 · 第 3 页" else "Earlier messages · page 3")
        captureLatestHistory("memory-chat-latest-${if (memoir) "memoir" else "story"}-$language-150.png", memoir)

        val requestsBeforeLatest = api.turnRequests.size
        rule.onNodeWithTag(latestTag).performScrollTo().performClick()
        awaitPage(store, memoir, 1)
        assertEquals("the action requests only the latest page", requestsBeforeLatest + 1, api.turnRequests.size)
        assertEquals("the direct action requests page one", 1, api.turnRequests.last().second)
        rule.onNodeWithTag(pageTag).performScrollTo().assertTextEquals(if (language == "zh") "最新消息" else "Latest messages")
        rule.onNodeWithTag(latestTag).assertDoesNotExist()
        rule.onNodeWithTag(draftTag).performScrollTo()
        val visibleDraft = rule.onNodeWithTag(draftTag).fetchSemanticsNode().config[SemanticsProperties.EditableText].text
        assertEquals("the composer remains unchanged", "Unsent follow-up draft", visibleDraft)
        assertEquals("story and memoir history navigation never submits", 0, api.sentTurns)
        assertEquals("story and memoir history navigation never starts a conversation", 0, api.startedConversations)
        assertEquals("story and memoir history navigation never transcribes audio", 0, api.transcriptions)
        assertNull("history navigation leaves voice dictation unstarted", if (memoir)
            store.state.value.memoryBooks?.companion?.dictation
            else store.state.value.savedMemoryStories?.community?.dictation)

        // Capture a real rendered callback on an older page, then replace its scope. The retained
        // action must not load page one for the new conversation or reader.
        rule.onNodeWithTag("$prefix-next").performScrollTo().performClick()
        awaitPage(store, memoir, 2)
        rule.onNodeWithTag("$prefix-next").performScrollTo().performClick()
        awaitPage(store, memoir, 3)
        val hiddenAction = captureClick(latestTag)
        val hiddenNewerAction = captureClick("$prefix-previous")
        val hiddenOlderAction = captureClick("$prefix-next")
        val requestsBeforeHiding = api.turnRequests.size
        if (memoir) rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
        else rule.onNodeWithTag("memory-community-tab-0").performScrollTo().performClick()
        rule.waitForIdle()
        rule.onNodeWithTag(latestTag).assertDoesNotExist()
        rule.runOnIdle {
            assertEquals(true, hiddenAction())
            assertEquals(true, hiddenNewerAction())
            assertEquals(true, hiddenOlderAction())
        }
        rule.waitForIdle()
        assertEquals("a hidden chat control cannot fetch or change the retained history page",
            requestsBeforeHiding, api.turnRequests.size)
        assertEquals(3, if (memoir) store.state.value.memoryBooks?.companion?.turns?.page
            else store.state.value.savedMemoryStories?.community?.turns?.page)
        if (memoir) rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
        else rule.onNodeWithTag("memory-community-tab-1").performScrollTo().performClick()
        awaitPage(store, memoir, 3)
        val staleAction = captureClick(latestTag)
        val staleNewerAction = captureClick("$prefix-previous")
        if (memoir) {
            rule.runOnIdle { store.closeMemoryBook() }
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.selectedBook == null }
            rule.onNodeWithTag("memory-book-${GeneratedMemoirReaderApi.BOOK}").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy } == true }
            rule.onNodeWithTag("memory-book-entry-0").performScrollTo().performClick()
            rule.waitUntil(5_000) {
                store.state.value.memoryBooks?.let {
                    it.selectedBook?.id == GeneratedMemoirReaderApi.BOOK && it.storyIndex == 0 &&
                        it.story?.id == GeneratedMemoirReaderApi.FIRST && !it.readerBusy
                } == true
            }
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.companion?.turns != null }
            awaitPage(store, memoir, 1)
        } else {
            rule.runOnIdle { store.selectMemoryConversation(FixtureApi.SECOND_CONVERSATION) }
            rule.waitUntil(5_000) {
                store.state.value.savedMemoryStories?.community?.let {
                    it.conversationId == FixtureApi.SECOND_CONVERSATION && !it.busy
                } == true
            }
            awaitPage(store, memoir, 1)
        }
        val requestsBeforeStaleAction = api.turnRequests.size
        rule.runOnIdle {
            assertEquals("a retained rendered click is still dispatchable", true, staleAction())
            assertEquals(true, staleNewerAction())
        }
        rule.waitForIdle()
        assertEquals("a detached action cannot request history in a replacement scope", requestsBeforeStaleAction,
            api.turnRequests.size)
        assertEquals("the replacement remains on its own latest page", 1,
            if (memoir) store.state.value.memoryBooks?.companion?.turns?.page
            else store.state.value.savedMemoryStories?.community?.turns?.page)
    }

    private fun openConversation(store: ConnectedStore, memoir: Boolean) {
        if (memoir) {
            rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.result != null }
            rule.onNodeWithTag("memory-book-${GeneratedMemoirReaderApi.BOOK}").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy } == true }
            rule.onNodeWithTag("memory-book-entry-0").performScrollTo().performClick()
            rule.waitUntil(5_000) {
                store.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy && it.story != null } == true
            }
            rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.companion?.turns != null }
        } else {
            rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.savedMemoryStories?.result != null }
            rule.onNodeWithTag("saved-memory-story-${GeneratedMemoirReaderApi.FIRST}").performScrollTo().performClick()
            rule.waitUntil(5_000) {
                store.state.value.savedMemoryStories?.community?.let { it.capabilities != null && !it.busy } == true
            }
            rule.onNodeWithTag("memory-community-tab-1").performScrollTo().performClick()
            rule.waitUntil(5_000) {
                store.state.value.savedMemoryStories?.community?.let { it.conversationId != null && it.turns != null } == true
            }
        }
    }

    private fun awaitPage(store: ConnectedStore, memoir: Boolean, page: Int) {
        rule.waitUntil(5_000) {
            if (memoir) store.state.value.memoryBooks?.companion?.let { it.turns?.page == page && !it.busy } == true
            else store.state.value.savedMemoryStories?.community?.let { it.turns?.page == page && !it.busy } == true
        }
    }

    private fun captureClick(tag: String): () -> Boolean {
        val node = rule.onNodeWithTag(tag).fetchSemanticsNode()
        val action = node.config[SemanticsActions.OnClick].action
        assertNotNull("$tag exposes an accessible click action", action)
        return checkNotNull(action)
    }

    private fun captureLatestHistory(name: String, memoir: Boolean) {
        val bitmap = rule.onNodeWithTag(if (memoir) "memory-books" else "saved-memory-stories")
            .captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, name)
            .outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private class FixtureApi(
        private val reader: GeneratedMemoirReaderApi = GeneratedMemoirReaderApi(),
    ) : PhotoHouseApi by reader, MemoryCommunityApi by reader {
        override val protectedNativeV2Enabled = true

        var sentTurns = 0
        var startedConversations = 0
        var transcriptions = 0
        val turnRequests = mutableListOf<Pair<String, Int>>()

        private val storySummary = SavedMemoryStorySummary(
            GeneratedMemoirReaderApi.FIRST, "Garden day / 花园的一天", "everyday", "zh", 3,
            "1", 12, 3, 1_720_000_000, false,
        )

        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int) =
            SavedMemoryStoryPage(library, page, 8, false, false, listOf(storySummary))

        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int, theme: String?) =
            savedMemoryStories(token, library, page)

        override suspend fun capabilities(token: Bearer, library: String) = """
            {"version":1,"enabled":true,"contributions_enabled":false,"generation_enabled":true,
             "conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,
             "max_text_bytes":8192,"original_retention":"until_owner_deletes"}
        """.trimIndent().toByteArray()

        override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String) =
            conversationList().toByteArray()

        override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String) =
            conversationList().toByteArray()

        private fun conversationList() = """
            {"version":1,"items":[
              {"id":"$FIRST_CONVERSATION","created_at":1780000000,"expires_at":4102444800,"first_message_preview":"First thread"},
              {"id":"$SECOND_CONVERSATION","created_at":1779999999,"expires_at":4102444800,"first_message_preview":"Second thread"}
            ]}
        """.trimIndent()

        override suspend fun startConversation(token: Bearer, library: String, json: String): ByteArray {
            startedConversations++
            error("Conversation creation is outside this navigation fixture")
        }

        override suspend fun conversationTurns(token: Bearer, library: String, conversationId: String, page: Int): ByteArray {
            turnRequests += conversationId to page
            val newestSequence = (4 - page).coerceAtLeast(1)
            return """
                {"version":1,"id":"$conversationId","expires_at":4102444800,"page":$page,
                 "has_more":${page < 3},"items":[
                   {"id":"$TURN_ID","sequence":$newestSequence,"input_text":"message page $page",
                    "reply_text":"Generated reply for page $page","reply_kind":"answer","job_id":null,
                    "state":"ready","reply_source_ids":[],"reply_questions":[]}
                 ]}
            """.trimIndent().toByteArray()
        }

        override suspend fun conversationTurnsWithReplyContext(token: Bearer, library: String, conversationId: String, page: Int) =
            conversationTurns(token, library, conversationId, page)

        override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String): ByteArray {
            sentTurns++
            error("Sending is outside this navigation fixture")
        }

        override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String, editorialContext: Boolean) =
            sendTurn(token, library, conversationId, json)

        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray): dev.photohouse.connected.core.AssistantTranscript {
            transcriptions++
            error("Transcription is outside this navigation fixture")
        }

        companion object {
            const val FIRST_CONVERSATION = "00000000-0000-4000-8000-000000000101"
            const val SECOND_CONVERSATION = "00000000-0000-4000-8000-000000000102"
            const val TURN_ID = "00000000-0000-4000-8000-000000000103"
        }
    }
}
