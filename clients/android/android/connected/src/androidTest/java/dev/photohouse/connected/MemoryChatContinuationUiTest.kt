package dev.photohouse.connected

import android.graphics.Bitmap
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.SoftwareKeyboardController
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.ApiErrorCode
import dev.photohouse.connected.core.ApiFailure
import dev.photohouse.connected.core.Bearer
import dev.photohouse.connected.core.ConnectedStore
import dev.photohouse.connected.core.FailureKind
import dev.photohouse.connected.core.MemoryCommunityApi
import dev.photohouse.connected.core.MemoryConversationRequest
import dev.photohouse.connected.core.Message
import dev.photohouse.connected.core.PhotoHouseApi
import dev.photohouse.connected.core.SavedMemoryStoryPage
import dev.photohouse.connected.core.SavedMemoryStorySummary
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class MemoryChatContinuationUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    @After fun close() { scope.cancel() }

    @Test fun englishStoryFullConversationContinuesOnlyAfterReviewAt150Percent() = journey("en", memoir = false)
    @Test fun chineseStoryFullConversationContinuesOnlyAfterReviewAt150Percent() = journey("zh", memoir = false)
    @Test fun englishMemoirFullConversationContinuesOnlyAfterReviewAt150Percent() = journey("en", memoir = true)
    @Test fun chineseMemoirFullConversationContinuesOnlyAfterReviewAt150Percent() = journey("zh", memoir = true)

    private fun journey(language: String, memoir: Boolean) {
        val api = ContinuationApi()
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
        openChat(store, memoir)

        val prefix = if (memoir) "memory-book-chat" else "memory-chat"
        val composeTag = "$prefix-input"
        val continueTag = "$prefix-continue"
        val retryTag = "$prefix-continue-retry"
        val failureTag = if (memoir) "$prefix-failure" else "memory-community-failure"
        val existingConversation = if (memoir) store.state.value.memoryBooks?.companion?.conversationId
            else store.state.value.savedMemoryStories?.community?.conversationId
        assertEquals("generated existing thread is selected", ContinuationApi.OLD_CONVERSATION, existingConversation)
        awaitTurns(store, memoir, ContinuationApi.OLD_CONVERSATION, page = 1)

        val rejectedQuestion = if (language == "zh") "那天后来发生了什么？" else "What happened after that day?"
        rule.onNodeWithTag(composeTag).performScrollTo().performTextInput(rejectedQuestion)
        rule.waitUntil(5_000) { draft(store, memoir) == rejectedQuestion }
        rule.onNodeWithTag("$prefix-send").performScrollTo().performClick()
        rule.waitUntil(5_000) {
            val state = snapshot(store, memoir)
            !state.busy && state.failure == Message.MEMORY_CONVERSATION_FULL
        }
        assertEquals("the refused turn stays attached to the old conversation", rejectedQuestion, snapshot(store, memoir).pendingTurnText)
        assertEquals("the refused request is held separately from the next editable draft", "", draft(store, memoir))
        rule.onNodeWithTag(failureTag).performScrollTo().assertExists()
        rule.onNodeWithTag("$prefix-user-bubble-${ContinuationApi.OLD_TURN}").performScrollTo().assertExists()
        rule.onNodeWithTag(continueTag).performScrollTo().assertExists()
        val detachedContinue = captureClick(continueTag)
        rule.runOnIdle { keyboardController?.hide() }
        rule.waitForIdle()
        capture("memory-chat-continuation-${if (memoir) "memoir" else "story"}-$language-150.png", memoir)
        assertEquals("the full response does not offer retrying the same turn", 1, api.sentTexts.size)

        // Leaving the conversation panel is not an implicit continuation action.
        if (memoir) {
            rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
            rule.waitForIdle()
        } else {
            rule.onNodeWithTag("memory-community-tab-0").performScrollTo().performClick()
            rule.waitForIdle()
        }
        rule.runOnIdle { assertEquals(true, detachedContinue()) }
        rule.waitForIdle()
        assertEquals("folding or changing tabs never creates a thread", 0, api.startRequests.size)
        if (memoir) rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
        else rule.onNodeWithTag("memory-community-tab-1").performScrollTo().performClick()
        rule.onNodeWithTag(continueTag).performScrollTo().assertExists()

        // Continue once. The first synthetic create is ambiguous/offline, so the rejected turn
        // and its editable draft remain attached to the pending request.
        rule.runOnIdle { api.failNextCreate = true }
        rule.onNodeWithTag(continueTag).performScrollTo().performClick()
        rule.waitUntil(5_000) {
            val state = snapshot(store, memoir)
            !state.busy && state.pendingConversation != null && state.hasFailure
        }
        assertEquals("the refusal remains available until a new thread is verified", rejectedQuestion, snapshot(store, memoir).pendingTurnText)
        val pendingRequest = checkNotNull(snapshot(store, memoir).pendingConversation)
        assertEquals("only one explicit create was attempted", 1, api.startRequests.size)
        assertEquals("the same question remains editable after create failure", rejectedQuestion, draft(store, memoir))
        val detachedRetry = captureClick(retryTag)

        val editedWhileFailed = if (language == "zh") "补充：请按时间顺序说明。" else "Add a short chronological explanation."
        val editedAfterRetryStarts = if (language == "zh") "再补充：记得核对照片里的细节。" else "Also check the details in the photos."
        val failedDraft = "$rejectedQuestion\n$editedWhileFailed"
        rule.onNodeWithTag(composeTag).performScrollTo().performTextReplacement(failedDraft)
        rule.waitUntil(5_000) { draft(store, memoir) == failedDraft }

        val retryGate = CompletableDeferred<Unit>()
        rule.runOnIdle { api.holdNextSuccessfulCreate = retryGate }
        rule.onNodeWithTag(retryTag).performScrollTo().performClick()
        rule.waitUntil(5_000) { api.startRequests.size == 2 && snapshot(store, memoir).busy }
        assertEquals("retry reuses the exact conversation request", listOf(pendingRequest.id, pendingRequest.id), api.startRequests.map { it.id })
        assertEquals("retry keeps the rejected turn while create is pending", rejectedQuestion, snapshot(store, memoir).pendingTurnText)

        // Continuation creation keeps the composer editable while pending. The user's latest edit
        // wins and is carried into the verified new thread without being sent automatically.
        val finalDraft = "$rejectedQuestion\n$editedAfterRetryStarts"
        rule.onNodeWithTag(composeTag).performScrollTo().performTextReplacement(finalDraft)
        rule.waitUntil(5_000) { draft(store, memoir) == finalDraft }
        rule.runOnIdle { retryGate.complete(Unit) }
        rule.waitUntil(5_000) {
            val state = snapshot(store, memoir)
            !state.busy && !state.continuation && state.conversationId == pendingRequest.id && state.turnsPage == 1
        }
        val completed = snapshot(store, memoir)
        assertEquals("verified directory retains old and new conversations",
            setOf(ContinuationApi.OLD_CONVERSATION, ContinuationApi.SECOND_CONVERSATION, pendingRequest.id), completed.conversationIds)
        assertEquals("new thread starts at verified latest page one", 1, completed.turnsPage)
        assertEquals("the reviewed draft stays in the composer", finalDraft, draft(store, memoir))
        assertNull("refusal is cleared only after new thread succeeds", completed.pendingTurnText)
        assertEquals("creation and navigation do not send another turn", 1, api.sentTexts.size)
        assertEquals("success removes both continuation actions", 0, rule.onAllNodesWithTag(continueTag).fetchSemanticsNodes().size)
        assertEquals("success removes retry action", 0, rule.onAllNodesWithTag(retryTag).fetchSemanticsNodes().size)
        assertEquals("continuation never starts transcription", 0, api.transcriptions)
        val startsAfterSuccess = api.startRequests.size
        rule.runOnIdle {
            assertEquals(true, detachedContinue())
            assertEquals(true, detachedRetry())
        }
        rule.waitForIdle()
        assertEquals("retained continuation controls cannot create another thread", startsAfterSuccess, api.startRequests.size)
        assertEquals("retained controls cannot send another turn", 1, api.sentTexts.size)
        rule.runOnIdle { keyboardController?.hide() }
        rule.waitForIdle()
        capture("memory-chat-continuation-${if (memoir) "memoir" else "story"}-$language-continued-150.png", memoir)
    }

    private fun openChat(store: ConnectedStore, memoir: Boolean) {
        if (memoir) {
            rule.onNodeWithTag("open-memory-books").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.result != null }
            rule.onNodeWithTag("memory-book-${GeneratedMemoirReaderApi.BOOK}").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.let { it.selectedBook != null && !it.readerBusy } == true }
            rule.onNodeWithTag("memory-book-entry-0").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.let { it.story != null && !it.readerBusy } == true }
            rule.onNodeWithTag("memory-book-chat-disclosure").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.memoryBooks?.companion?.turns != null }
        } else {
            rule.onNodeWithTag("open-saved-memory-stories").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.savedMemoryStories?.result != null }
            rule.onNodeWithTag("saved-memory-story-${GeneratedMemoirReaderApi.FIRST}").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.savedMemoryStories?.community?.let { it.capabilities != null && !it.busy } == true }
            rule.onNodeWithTag("memory-community-tab-1").performScrollTo().performClick()
            rule.waitUntil(5_000) { store.state.value.savedMemoryStories?.community?.let { it.conversationId != null && it.turns != null } == true }
        }
    }

    private fun awaitTurns(store: ConnectedStore, memoir: Boolean, conversation: String, page: Int) {
        rule.waitUntil(5_000) {
            val state = snapshot(store, memoir)
            state.conversationId == conversation && state.turnsPage == page && !state.busy
        }
    }

    private data class ChatSnapshot(
        val busy: Boolean,
        val failure: Message?,
        val hasFailure: Boolean,
        val pendingTurnText: String?,
        val pendingConversation: MemoryConversationRequest?,
        val continuation: Boolean,
        val conversationId: String?,
        val turnsPage: Int?,
        val conversationIds: Set<String>,
    )

    private fun snapshot(store: ConnectedStore, memoir: Boolean): ChatSnapshot = if (memoir) {
        val chat = checkNotNull(store.state.value.memoryBooks?.companion)
        ChatSnapshot(chat.busy, chat.failure?.message, chat.failure != null, chat.pendingTurn?.text,
            chat.pendingConversation, chat.continuation != null, chat.conversationId, chat.turns?.page,
            chat.conversations?.items?.map { it.id }?.toSet().orEmpty())
    } else {
        val chat = checkNotNull(store.state.value.savedMemoryStories?.community)
        ChatSnapshot(chat.busy, chat.failure?.message, chat.failure != null, chat.pendingTurn?.text,
            chat.pendingConversation, chat.continuation != null, chat.conversationId, chat.turns?.page,
            chat.conversations?.items?.map { it.id }?.toSet().orEmpty())
    }

    private fun draft(store: ConnectedStore, memoir: Boolean) = if (memoir)
        checkNotNull(store.state.value.memoryBooks?.companion).draft
    else checkNotNull(store.state.value.savedMemoryStories?.community).chatDraft

    private fun captureClick(tag: String): () -> Boolean {
        val node = rule.onNodeWithTag(tag).fetchSemanticsNode()
        val action = node.config[SemanticsActions.OnClick].action
        return checkNotNull(action) { "$tag must expose an accessible action" }
    }

    private fun capture(name: String, memoir: Boolean) {
        val tag = if (memoir) "memory-books" else "saved-memory-stories"
        val bitmap = rule.onNodeWithTag(tag).captureToImage().asAndroidBitmap()
        File(InstrumentationRegistry.getInstrumentation().targetContext.filesDir, name).outputStream().use {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
        }
    }

    private class ContinuationApi(
        private val reader: GeneratedMemoirReaderApi = GeneratedMemoirReaderApi(),
    ) : PhotoHouseApi by reader, MemoryCommunityApi by reader {
        override val protectedNativeV2Enabled = true

        private val directories = mutableListOf(OLD_CONVERSATION, SECOND_CONVERSATION)
        private val firstTexts = mutableMapOf(OLD_CONVERSATION to "An earlier family question")
        val sentTexts = mutableListOf<String>()
        val startRequests = mutableListOf<MemoryConversationRequest>()
        var failNextCreate = false
        var holdNextSuccessfulCreate: CompletableDeferred<Unit>? = null
        var transcriptions = 0

        private val summary = SavedMemoryStorySummary(
            GeneratedMemoirReaderApi.FIRST, "Garden day / 花园的一天", "everyday", "zh", 3,
            "1", 12, 3, 1_720_000_000, false,
        )

        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int) =
            SavedMemoryStoryPage(library, page, 8, false, false, listOf(summary))

        // Keep memoir library loading on the same explicit path as the latest-history fixture.
        override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int, theme: String?): SavedMemoryStoryPage =
            savedMemoryStories(token, library, page)

        override suspend fun capabilities(token: Bearer, library: String) = """
            {"version":1,"enabled":true,"contributions_enabled":false,"generation_enabled":true,
             "conversation_retention_days":30,"audio_format":"wav_pcm16_mono_16000","max_audio_seconds":30,
             "max_text_bytes":8192,"original_retention":"until_owner_deletes"}
        """.trimIndent().toByteArray()

        override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String) = directory().toByteArray()
        override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String) = directory().toByteArray()

        private fun directory() = """{"version":1,"items":[${directories.mapIndexed { index, id ->
            """{"id":"$id","created_at":${1_780_000_000L - index},"expires_at":4102444800,"first_message_preview":${JsonPrimitive(firstTexts[id] ?: "Continued question")}}"""
        }.joinToString(",")}] }"""

        override suspend fun startConversation(token: Bearer, library: String, json: String): ByteArray {
            val requestJson = Json.parseToJsonElement(json).jsonObject
            val request = MemoryConversationRequest(
                requestJson.getValue("id").jsonPrimitive.content,
                requestJson.getValue("target_type").jsonPrimitive.content,
                requestJson.getValue("target_id").jsonPrimitive.content,
            )
            startRequests += request
            if (failNextCreate) {
                failNextCreate = false
                throw ApiFailure(FailureKind.OFFLINE)
            }
            holdNextSuccessfulCreate?.let { gate ->
                holdNextSuccessfulCreate = null
                gate.await()
            }
            directories.remove(request.id)
            directories.add(0, request.id)
            return """{"version":1,"id":"${request.id}","target_type":"${request.targetType}","target_id":"${request.targetId}","expires_at":4102444800}""".toByteArray()
        }

        override suspend fun conversationTurns(token: Bearer, library: String, conversationId: String, page: Int): ByteArray {
            val oldTurn = if (conversationId == OLD_CONVERSATION) """
                {"id":"$OLD_TURN","sequence":1,"input_text":"An earlier family question",
                 "reply_text":"A generated earlier reply.","reply_kind":"answer","job_id":null,
                 "state":"ready","reply_source_ids":[],"reply_questions":[]}
            """.trimIndent() else ""
            return """{"version":1,"id":"$conversationId","expires_at":4102444800,"page":$page,"has_more":false,"items":[$oldTurn]}""".toByteArray()
        }

        override suspend fun conversationTurnsWithReplyContext(token: Bearer, library: String, conversationId: String, page: Int) =
            conversationTurns(token, library, conversationId, page)

        override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String): ByteArray {
            val text = Json.parseToJsonElement(json).jsonObject.getValue("text").jsonPrimitive.content
            sentTexts += text
            throw ApiFailure(FailureKind.HTTP, status = 429, errorCode = ApiErrorCode.MEMORY_CONVERSATION_FULL)
        }

        override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String, editorialContext: Boolean) =
            sendTurn(token, library, conversationId, json)

        override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray): dev.photohouse.connected.core.AssistantTranscript {
            transcriptions++
            error("Continuation fixture must not transcribe audio")
        }

        companion object {
            const val OLD_CONVERSATION = "00000000-0000-4000-8000-000000000101"
            const val SECOND_CONVERSATION = "00000000-0000-4000-8000-000000000102"
            const val OLD_TURN = "00000000-0000-4000-8000-000000000103"
        }
    }
}
