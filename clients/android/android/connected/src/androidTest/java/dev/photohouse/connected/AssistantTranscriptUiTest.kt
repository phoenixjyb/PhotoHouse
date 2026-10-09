package dev.photohouse.connected

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.photohouse.connected.core.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic transcript review journeys; no recording, API request, or provider is used. */
@RunWith(AndroidJUnit4::class)
class AssistantTranscriptUiTest {
    @get:Rule val rule = createComposeRule()

    private fun showAt150(state: androidx.compose.runtime.MutableState<AssistantClientState>, zh: Boolean,
        recording: androidx.compose.runtime.MutableState<Boolean>, onSend: (String) -> Boolean,
        onUseTranscript: (AssistantTranscript) -> String?, onClearTranscript: () -> Unit,
        onRecord: () -> Unit = {}) {
        rule.setContent {
            val currentDensity = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(currentDensity.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantScreen(state.value, zh, onBack = {}, previews = emptyMap(), onRetryCapabilities = {},
                        onSend = onSend, onClear = {}, onOpen = { _, _ -> }, onCheckReceipt = {},
                        onRecord = onRecord, onStopRecording = {}, onCancelRecording = {}, recording = recording.value,
                        recordError = false, onClearTranscript = onClearTranscript,
                        onUseTranscript = onUseTranscript, onPlaySpeech = {}, onStopSpeech = {})
                }
            }
        }
        rule.waitForIdle()
    }

    private fun state(transcribing: Boolean = false, transcript: AssistantTranscript? = null) =
        mutableStateOf(AssistantClientState("synthetic-library", 1,
            capabilities = AssistantCapabilities(true, true, true, false, 30),
            transcribing = transcribing, transcript = transcript,
            lastRequestReceipt = transcript?.receipt))

    private fun accept(state: androidx.compose.runtime.MutableState<AssistantClientState>): (AssistantTranscript) -> String? = { expected ->
        val current = state.value
        if (current.transcript !== expected || current.confirmedTranscriptRequestId != null || current.busy || current.transcribing || current.pendingTurn != null) null
        else {
            state.value = current.copy(transcript = null, confirmedTranscriptRequestId = expected.receipt?.requestId)
            expected.text
        }
    }

    private fun assertReviewCardFullyVisible() {
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-transcript-review"))
        rule.onNodeWithTag("assistant-transcript-review").assertIsDisplayed()
        var stableSince = 0L
        rule.waitUntil(5_000) {
            val card = rule.onNodeWithTag("assistant-transcript-review").getUnclippedBoundsInRoot()
            val viewport = rule.onNodeWithTag("assistant-turns").getUnclippedBoundsInRoot()
            val inside = card.left >= viewport.left && card.top >= viewport.top &&
                card.right <= viewport.right && card.bottom <= viewport.bottom
            val now = android.os.SystemClock.uptimeMillis()
            if (!inside) stableSince = 0L
            else if (stableSince == 0L) stableSince = now
            inside && now - stableSince >= 250L
        }
    }

    private fun capture(name: String) {
        rule.waitForIdle()
        val bitmap = rule.onRoot().captureToImage().asAndroidBitmap()
        val context = androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().targetContext
        val uri = requireNotNull(context.contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            android.content.ContentValues().apply {
                put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, "assistant-transcript-$name.png")
                put(android.provider.MediaStore.MediaColumns.MIME_TYPE, "image/png")
                put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH, "Pictures/PhotoHouseAssistantTranscriptUi")
            }))
        context.contentResolver.openOutputStream(uri).use { output ->
            requireNotNull(output).use { bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        }
        bitmap.recycle()
    }

    private fun acceptedTranscriptJourney(zh: Boolean, draft: String, words: String, requestId: String) {
        val transcript = AssistantTranscript(words, if (zh) "zh" else "en",
            AssistantRequestReceipt(requestId, "enabled", "succeeded"))
        val client = state(transcribing = true)
        val recording = mutableStateOf(false)
        var sends = 0
        var records = 0
        var submittedText: String? = null
        var submittedParent: String? = null
        showAt150(client, zh, recording, onSend = { text ->
            sends++
            submittedText = text
            submittedParent = client.value.confirmedTranscriptRequestId
            true
        }, onUseTranscript = accept(client), onClearTranscript = {
            client.value = client.value.copy(transcript = null, confirmedTranscriptRequestId = null)
        }, onRecord = { records++ })

        rule.onNodeWithTag("assistant-text").performTextInput(draft)
        rule.onNodeWithTag("assistant-text").assertTextContains(draft)
        rule.onNodeWithTag("assistant-send").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-record").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-text").performImeAction()
        assertEquals(0, sends)
        assertEquals(0, records)
        assertNull(client.value.confirmedTranscriptRequestId)

        rule.runOnIdle { client.value = client.value.copy(transcribing = false, transcript = transcript,
            lastRequestReceipt = transcript.receipt) }
        rule.onNodeWithTag("assistant-text").assertTextContains(draft)
        rule.onNodeWithTag("assistant-send").assertIsNotEnabled()
        assertEquals("ASR arrival does not accept or send text", 0, sends)
        assertNull(client.value.confirmedTranscriptRequestId)
        assertReviewCardFullyVisible()
        rule.onNodeWithTag("assistant-transcript-original").assertTextEquals(words)
        rule.onNodeWithTag("assistant-insert-transcript").assertIsEnabled()
        rule.onNodeWithTag("assistant-discard-transcript").assertIsEnabled()
        capture(if (zh) "zh-review-150" else "en-review-150")

        rule.onNodeWithTag("assistant-insert-transcript").performClick()
        rule.onNodeWithTag("assistant-text").assertTextContains("$draft\n$words")
        assertNull(client.value.transcript)
        assertEquals(requestId, client.value.confirmedTranscriptRequestId)
        assertEquals(0, sends)
        rule.onNodeWithTag("assistant-text").performImeAction()
        assertEquals(1, sends)
        assertEquals("$draft\n$words", submittedText)
        assertEquals("The explicit accepted ASR request is linked as parent", requestId, submittedParent)
    }

    @Test fun englishTranscriptArrivingDuringTypingRequiresAddThenExplicitSend() =
        acceptedTranscriptJourney(false, "Find my typed note", "The garden by the sea.",
            "123e4567-e89b-42d3-a456-426614174020")

    @Test fun chineseTranscriptArrivingDuringTypingRequiresAddThenExplicitSend() =
        acceptedTranscriptJourney(true, "保留我写的问题", "海边花园里的那一天。",
            "123e4567-e89b-42d3-a456-426614174021")

    @Test fun discardKeepsDraftAndDoesNotAttachTranscriptRequest() {
        val transcript = AssistantTranscript("Recognized but not accepted", "en",
            AssistantRequestReceipt("123e4567-e89b-42d3-a456-426614174030", "enabled", "succeeded"))
        val client = state(transcript = transcript)
        val recording = mutableStateOf(false)
        var sends = 0
        var submittedParent: String? = "unset"
        showAt150(client, false, recording, onSend = {
            sends++
            submittedParent = client.value.confirmedTranscriptRequestId
            true
        }, onUseTranscript = accept(client),
            onClearTranscript = { client.value = client.value.copy(transcript = null, confirmedTranscriptRequestId = null) })
        rule.onNodeWithTag("assistant-text").performTextInput("Keep my independent draft")
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-transcript-review"))
        rule.onNodeWithTag("assistant-discard-transcript").performClick()
        rule.onNodeWithTag("assistant-text").assertTextContains("Keep my independent draft")
        assertNull(client.value.transcript)
        assertNull(client.value.confirmedTranscriptRequestId)
        assertEquals(0, sends)
        rule.onNodeWithTag("assistant-text").performImeAction()
        assertEquals("The kept draft sends only after an explicit action", 1, sends)
        assertNull("Discard leaves the new turn unlinked from ASR", submittedParent)
    }

    @Test fun unicodeOverflowDisablesAddWithoutReplacingEitherText() {
        val face = String(Character.toChars(0x1f642))
        val draft = face.repeat(500)
        val words = face.repeat(12)
        val transcript = AssistantTranscript(words, "zh",
            AssistantRequestReceipt("123e4567-e89b-42d3-a456-426614174031", "enabled", "succeeded"))
        val client = state(transcript = transcript)
        val recording = mutableStateOf(false)
        var sends = 0
        showAt150(client, true, recording, onSend = { sends++; true }, onUseTranscript = accept(client),
            onClearTranscript = { client.value = client.value.copy(transcript = null, confirmedTranscriptRequestId = null) })
        rule.onNodeWithTag("assistant-text").performTextInput(draft)
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-transcript-review"))
        rule.onNodeWithTag("assistant-transcript-overflow").assertTextContains("超过消息长度限制", substring = true)
        rule.onNodeWithTag("assistant-insert-transcript").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-message-overflow").assertTextContains("这条消息超出长度限制", substring = true)
        assertEquals(draft, rule.onNodeWithTag("assistant-text").fetchSemanticsNode().config[
            androidx.compose.ui.semantics.SemanticsProperties.EditableText].text)
        rule.onNodeWithTag("assistant-transcript-original").assertTextEquals(words)
        assertNull(client.value.confirmedTranscriptRequestId)
        assertEquals(0, sends)
        rule.onNodeWithTag("assistant-text").performImeAction()
        assertEquals("An unaccepted oversized transcript cannot be submitted", 0, sends)
        assertEquals(transcript, client.value.transcript)
        rule.onNodeWithTag("assistant-discard-transcript").performClick()
        assertNull(client.value.transcript)
        assertNull(client.value.confirmedTranscriptRequestId)
        assertEquals(draft, rule.onNodeWithTag("assistant-text").fetchSemanticsNode().config[
            androidx.compose.ui.semantics.SemanticsProperties.EditableText].text)
        rule.onNodeWithTag("assistant-message-overflow").assertTextContains("这条消息超出长度限制", substring = true)
        rule.onNodeWithTag("assistant-send").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-text").performImeAction()
        assertEquals("Discarded oversized draft still cannot send by IME", 0, sends)
    }

    @Test fun oversizedChineseDraftWithoutTranscriptShowsHelpAndCannotSend() {
        val draft = "中".repeat(342) // 342 codepoints, 1026 UTF-8 bytes
        val client = state()
        val recording = mutableStateOf(false)
        var sends = 0
        showAt150(client, true, recording, onSend = { sends++; true }, onUseTranscript = accept(client),
            onClearTranscript = { client.value = client.value.copy(transcript = null, confirmedTranscriptRequestId = null) })
        rule.onNodeWithTag("assistant-text").performTextInput(draft)
        assertEquals(draft, rule.onNodeWithTag("assistant-text").fetchSemanticsNode().config[
            androidx.compose.ui.semantics.SemanticsProperties.EditableText].text)
        rule.onNodeWithTag("assistant-message-overflow").assertTextContains("这条消息超出长度限制", substring = true)
        rule.onNodeWithTag("assistant-send").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-text").performImeAction()
        assertEquals(0, sends)
        assertNull(client.value.confirmedTranscriptRequestId)
        assertNull(client.value.transcript)
        capture("zh-oversized-draft-150")
    }

    @Test fun recordingBlocksTranscriptActionsAndSending() {
        val transcript = AssistantTranscript("Words awaiting review", "en",
            AssistantRequestReceipt("123e4567-e89b-42d3-a456-426614174032", "enabled", "succeeded"))
        val client = state(transcript = transcript)
        val recording = mutableStateOf(false)
        var sends = 0
        var records = 0
        showAt150(client, false, recording, onSend = { sends++; true }, onUseTranscript = accept(client),
            onClearTranscript = { client.value = client.value.copy(transcript = null, confirmedTranscriptRequestId = null) },
            onRecord = { records++ })
        rule.onNodeWithTag("assistant-text").performTextInput("My typed words")
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-transcript-review"))
        rule.onNodeWithTag("assistant-send").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-record").assertIsNotEnabled()
        assertEquals(0, records)
        rule.runOnIdle { recording.value = true }
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-transcript-review"))
        rule.onNodeWithTag("assistant-stop-recording").assertIsEnabled()
        rule.onNodeWithTag("assistant-insert-transcript").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-discard-transcript").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-send").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-text").performImeAction()
        assertEquals(0, sends)
        assertEquals(transcript, client.value.transcript)
        assertNull(client.value.confirmedTranscriptRequestId)
        rule.runOnIdle { recording.value = false }
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-transcript-review"))
        rule.onNodeWithTag("assistant-discard-transcript").performClick()
        rule.onNodeWithTag("assistant-text").assertTextContains("My typed words")
        assertNull(client.value.confirmedTranscriptRequestId)
        assertEquals(0, sends)
    }
}
