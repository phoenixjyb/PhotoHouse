package dev.photohouse.connected

import androidx.activity.ComponentActivity
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import android.content.ContentValues
import android.provider.MediaStore
import dev.photohouse.connected.core.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic navigation journeys. They do not call the store, network, recorder, or providers. */
@RunWith(AndroidJUnit4::class)
class AssistantConversationNavigationUiTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()

    private fun turn(reply: String) = AssistantTurn("text", reply, null, null, emptyList(), 0, false, null)
    private fun exchange(id: String, question: String = "Question $id", reply: String = "Reply $id") =
        AssistantExchange(question, turn(reply), id)
    private fun baseState(generation: Long = 1, library: String = "synthetic-library", turns: List<AssistantExchange> = emptyList()) =
        AssistantClientState(library, generation, capabilities = AssistantCapabilities(true, true, true, false, 30), turns = turns)

    @Suppress("DEPRECATION")
    private fun show(state: androidx.compose.runtime.MutableState<AssistantClientState>, zh: Boolean, callbacks: Callbacks) {
        rule.activity.runOnUiThread {
            rule.activity.window.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        }
        rule.setContent {
            val current = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(current.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantScreen(state.value, zh, onBack = {}, previews = emptyMap(), onRetryCapabilities = {},
                        onSend = { callbacks.sent += it; true }, onClear = {}, onOpen = { _, _ -> }, onCheckReceipt = { callbacks.receiptChecks++ },
                        onRecord = { callbacks.records++ }, onStopRecording = {}, onCancelRecording = {}, recording = false,
                        recordError = false, onClearTranscript = {}, onPlaySpeech = {}, onStopSpeech = {})
                }
            }
        }
        rule.waitForIdle()
    }

    private class Callbacks {
        val sent = mutableListOf<String>()
        var records = 0
        var receiptChecks = 0
    }

    private fun seedTurns(count: Int = 14) = (1..count).map { exchange("request-$it") }

    private fun scrollToOlderHistory() {
        // The semantics scroll action mirrors a user selecting older conversation history.
        rule.onNodeWithTag("assistant-turns").performScrollToIndex(0)
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-request-1").assertIsDisplayed()
    }

    @Test fun englishManualHistoryStaysPutAcrossPendingReplyReceiptAndTranscriptThenExplicitJumpRevealsLatest() {
        val state = mutableStateOf(baseState(turns = seedTurns()))
        val callbacks = Callbacks()
        show(state, zh = false, callbacks)
        scrollToOlderHistory()

        val id = "123e4567-e89b-42d3-a456-426614174101"
        state.value = state.value.copy(busy = true, pendingTurn = AssistantPendingTurn(
            "synthetic-account", state.value.library, state.value.generation, "Next question", null, null, id),
            lastRequestReceipt = AssistantRequestReceipt(id, "unknown", null))
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-request-1").assertIsDisplayed()
        rule.onNodeWithTag("assistant-jump-to-latest").assertIsDisplayed()

        state.value = state.value.copy(receiptChecking = true,
            lastRequestReceipt = AssistantRequestReceipt(id, "enabled", "received"))
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-request-1").assertIsDisplayed()
        rule.onNodeWithTag("assistant-jump-to-latest").assertIsDisplayed()

        state.value = state.value.copy(busy = false, receiptChecking = false, pendingTurn = null,
            turns = state.value.turns + exchange(id, "Next question", "Identical reply"),
            lastRequestReceipt = AssistantRequestReceipt(id, "unknown", null))
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-request-1").assertIsDisplayed()
        rule.onNodeWithTag("assistant-jump-to-latest").assertIsDisplayed()

        val transcriptId = "123e4567-e89b-42d3-a456-426614174102"
        state.value = state.value.copy(transcript = AssistantTranscript("Reviewed words", "en",
            AssistantRequestReceipt(transcriptId, "enabled", "succeeded"), localRequestId = transcriptId))
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-request-1").assertIsDisplayed()
        rule.onNodeWithTag("assistant-jump-to-latest").performClick()
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-$id").assertExists()
        rule.onNodeWithTag("assistant-exchange-$id").assertIsDisplayed()
        rule.onNodeWithTag("assistant-transcript-review").assertIsDisplayed()
        capture("en-large-text-final-review")
        assertTrue(callbacks.sent.isEmpty())
        assertEquals(0, callbacks.records)
        assertEquals(0, callbacks.receiptChecks)
    }

    @Test fun chineseAtLargeTextShowsFullJumpControlAndKeepsManualPositionUntilTapped() {
        val state = mutableStateOf(baseState(turns = seedTurns()))
        val callbacks = Callbacks()
        show(state, zh = true, callbacks)
        scrollToOlderHistory()
        val id = "123e4567-e89b-42d3-a456-426614174103"
        state.value = state.value.copy(pendingTurn = AssistantPendingTurn(
            "synthetic-account", state.value.library, state.value.generation, "新问题", null, null, id))
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-jump-to-latest").assertIsDisplayed()
        rule.onNodeWithTag("assistant-jump-to-latest-label", useUnmergedTree = true).assertTextEquals("跳到最新")

        val root = rule.onRoot().getUnclippedBoundsInRoot()
        val button = rule.onNodeWithTag("assistant-jump-to-latest").getUnclippedBoundsInRoot()
        val visibleButton = rule.onNodeWithTag("assistant-jump-to-latest").getBoundsInRoot()
        val label = rule.onNodeWithTag("assistant-jump-to-latest-label", useUnmergedTree = true).getUnclippedBoundsInRoot()
        assertTrue("jump control must be at least 48dp", (button.bottom - button.top).value >= 48f)
        assertTrue("full jump control must be visible", button.top >= root.top && button.bottom <= root.bottom &&
            visibleButton.top >= root.top && visibleButton.bottom <= root.bottom &&
            visibleButton.top == button.top && visibleButton.bottom == button.bottom)
        assertTrue("jump label must fit inside the control", label.top >= button.top && label.bottom <= button.bottom &&
            label.left >= button.left && label.right <= button.right)

        capture("zh-large-text-final-review")
        rule.onNodeWithTag("assistant-jump-to-latest").performClick()
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-pending-turn").assertIsDisplayed()
        assertTrue(callbacks.sent.isEmpty())
        assertEquals(0, callbacks.records)
    }

    @Test fun tailFollowShowsLatestReplyAndScopeChangeDropsOldRowsAndJumpState() {
        val state = mutableStateOf(baseState(turns = seedTurns(40)))
        val callbacks = Callbacks()
        show(state, zh = false, callbacks)
        scrollToOlderHistory()
        val id = "123e4567-e89b-42d3-a456-426614174104"
        state.value = state.value.copy(busy = true, pendingTurn = AssistantPendingTurn(
            "synthetic-account", state.value.library, state.value.generation, "Latest", null, null, id))
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-request-1").assertIsDisplayed()
        rule.onNodeWithTag("assistant-jump-to-latest").assertIsDisplayed()
        rule.onNodeWithTag("assistant-jump-to-latest").performClick()
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-pending-turn").assertIsDisplayed()
        assertEquals(0, rule.onAllNodesWithTag("assistant-jump-to-latest").fetchSemanticsNodes().size)
        val longReply = "Long reply. ".repeat(70) + "LATEST_REPLY_END"
        state.value = state.value.copy(busy = false, pendingTurn = null,
            turns = (state.value.turns + exchange(id, "Latest", longReply)).takeLast(40))
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-$id").assertIsDisplayed()
        val viewport = rule.onNodeWithTag("assistant-turns").getBoundsInRoot()
        val finalReply = rule.onNode(hasTestTag("assistant-reply") and hasText("LATEST_REPLY_END", substring = true))
        val fullReplyBounds = finalReply.getUnclippedBoundsInRoot()
        val visibleReplyBounds = finalReply.getBoundsInRoot()
        assertTrue("long reply's final line must reach the visible tail; full=$fullReplyBounds visible=$visibleReplyBounds viewport=$viewport",
            fullReplyBounds.top < viewport.top &&
                kotlin.math.abs(fullReplyBounds.bottom.value - visibleReplyBounds.bottom.value) < 0.5f &&
                viewport.bottom.value - visibleReplyBounds.bottom.value <= 24f)
        assertEquals(0, rule.onAllNodesWithTag("assistant-jump-to-latest").fetchSemanticsNodes().size)

        rule.onNodeWithTag("assistant-turns").performScrollToIndex(0)
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-request-2").assertIsDisplayed()
        val firstTranscript = AssistantTranscript("new words", "en", localRequestId = "asr-local-1")
        state.value = state.value.copy(transcript = firstTranscript)
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-jump-to-latest").assertIsDisplayed()
        rule.onNodeWithTag("assistant-jump-to-latest").performClick()
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-transcript-review").assertIsDisplayed()
        rule.onNodeWithTag("assistant-turns").performScrollToIndex(0)
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-exchange-request-2").assertIsDisplayed()
        state.value = state.value.copy(transcript = null)
        rule.waitForIdle()
        state.value = state.value.copy(transcript = AssistantTranscript("new words", "en", localRequestId = "asr-local-2"))
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-jump-to-latest").assertIsDisplayed()
        state.value = baseState(generation = 2, library = "other-library")
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-intro").assertExists()
        rule.onNodeWithTag("assistant-jump-to-latest").assertDoesNotExist()
        rule.onNodeWithTag("assistant-exchange-$id").assertDoesNotExist()
        assertTrue(callbacks.sent.isEmpty())
        assertEquals(0, callbacks.records)
    }

    @Test fun userSwipeInterruptingAutomaticTailFollowKeepsManualHistoryOnReply() {
        val state = mutableStateOf(baseState(turns = seedTurns(24)))
        val callbacks = Callbacks()
        show(state, zh = false, callbacks)
        val list = rule.onNodeWithTag("assistant-turns")
        list.performScrollToIndex(18)
        rule.waitForIdle()
        val originalMarker = "assistant-exchange-request-19"
        rule.onNodeWithTag(originalMarker).assertIsDisplayed()

        val id = "123e4567-e89b-42d3-a456-426614174106"
        state.value = state.value.copy(busy = true, pendingTurn = AssistantPendingTurn(
            "synthetic-account", state.value.library, state.value.generation,
            "Submitted question", null, null, id))
        rule.waitForIdle()
        rule.onNodeWithTag(originalMarker).assertIsDisplayed()
        rule.onNodeWithTag("assistant-jump-to-latest").assertIsDisplayed()

        val initialBounds = (1..24).mapNotNull { number ->
            val tag = "assistant-exchange-request-$number"
            runCatching {
                rule.onNodeWithTag(tag).assertIsDisplayed()
                tag to rule.onNodeWithTag(tag).getBoundsInRoot()
            }.getOrNull()
        }.toMap()
        assertTrue("manual history must have visible exchange markers", initialBounds.isNotEmpty())
        rule.mainClock.autoAdvance = false
        rule.onNodeWithTag("assistant-jump-to-latest").performClick()
        rule.mainClock.advanceTimeByFrame()
        val frameOne = initialBounds.keys.mapNotNull { tag ->
            runCatching { tag to rule.onNodeWithTag(tag).getBoundsInRoot() }.getOrNull()
        }.toMap()
        rule.mainClock.advanceTimeByFrame()
        val frameTwo = initialBounds.keys.mapNotNull { tag ->
            runCatching { tag to rule.onNodeWithTag(tag).getBoundsInRoot() }.getOrNull()
        }.toMap()
        val movingMarker = initialBounds.entries.firstOrNull { (tag, before) ->
            val first = frameOne[tag]
            val second = frameTwo[tag]
            first != null && second != null &&
                (kotlin.math.abs(first.top.value - before.top.value) > 1f ||
                    kotlin.math.abs(second.top.value - first.top.value) > 1f)
        }
        assertNotNull("explicit Jump should move an on-screen exchange over consecutive animation frames; before=${initialBounds.keys} frame1=${frameOne.keys} frame2=${frameTwo.keys}", movingMarker)
        list.performTouchInput {
            swipeDown(startY = height * 0.25f, endY = height * 0.92f, durationMillis = 250)
        }
        rule.mainClock.advanceTimeBy(1_000)

        val viewport = list.getBoundsInRoot()
        val anchor = (1..22).firstOrNull { number ->
            val tag = "assistant-exchange-request-$number"
            runCatching {
                rule.onNodeWithTag(tag).assertIsDisplayed()
                val bounds = rule.onNodeWithTag(tag).getBoundsInRoot()
                bounds.bottom > viewport.top && bounds.top < viewport.bottom
            }.getOrDefault(false)
        } ?: error("user swipe during explicit Jump must leave an older conversation marker visible")
        val anchorTag = "assistant-exchange-request-$anchor"
        rule.onNodeWithTag(anchorTag).assertIsDisplayed()
        rule.mainClock.autoAdvance = true
        rule.waitForIdle()

        state.value = state.value.copy(busy = false, pendingTurn = null,
            turns = (state.value.turns + exchange(id, "Submitted", "Reply arrived while reading history")).takeLast(40))
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-jump-to-latest").assertIsDisplayed()
        rule.onNodeWithTag(anchorTag).assertIsDisplayed()
        rule.onNodeWithTag("assistant-exchange-$id").assertDoesNotExist()
        assertTrue("reply must not be inserted into a network action", callbacks.sent.isEmpty())
        assertEquals(0, callbacks.records)
    }

    @Test fun pendingRecoveryActionsStayFullyVisibleWithImeBeforeLongSubmittedQuestion() {
        val question = "找家庭聚会的照片" + "很长的问题内容".repeat(45)
        val id = "123e4567-e89b-42d3-a456-426614174105"
        val state = mutableStateOf(baseState().copy(
            pendingTurn = AssistantPendingTurn("synthetic-account", "synthetic-library", 1, question, null, null, id),
            lastRequestReceipt = AssistantRequestReceipt(id, "enabled", "received"),
        ))
        val callbacks = Callbacks()
        show(state, zh = true, callbacks)

        rule.onNodeWithTag("assistant-intro-description").assertIsDisplayed()
        rule.onNodeWithTag("assistant-usage-description").assertIsDisplayed()
        rule.onNodeWithTag("assistant-retention-notice").assertIsDisplayed()
        rule.onNodeWithTag("assistant-pending-status").assertIsDisplayed()
        rule.onNodeWithTag("assistant-check-receipt").assertIsDisplayed()
        rule.onNodeWithTag("assistant-close-pending").assertIsDisplayed()
        rule.onNodeWithTag("assistant-text").performClick()
        rule.waitUntil(5_000) {
            rule.activity.window.decorView.rootWindowInsets?.isVisible(android.view.WindowInsets.Type.ime()) == true
        }
        rule.waitForIdle()
        captureWindow("pending-recovery-ime-diagnostic.png")
        rule.onNodeWithTag("assistant-intro-description").assertDoesNotExist()
        rule.onNodeWithTag("assistant-usage-description").assertDoesNotExist()
        rule.onNodeWithTag("assistant-intro-title").assertIsDisplayed()
        rule.onNodeWithTag("assistant-retention-notice").assertIsDisplayed()
        rule.onNodeWithTag("assistant-pending-status").assertIsDisplayed()
        rule.onNodeWithTag("assistant-check-receipt").assertIsDisplayed()
        rule.onNodeWithTag("assistant-close-pending").assertIsDisplayed()

        val viewport = rule.onNodeWithTag("assistant-turns").getBoundsInRoot()
        listOf("assistant-pending-status", "assistant-check-receipt", "assistant-close-pending").forEach { tag ->
            val node = rule.onNodeWithTag(tag)
            val full = node.getUnclippedBoundsInRoot()
            val visible = node.getBoundsInRoot()
            assertTrue("$tag must be fully visible above the IME; full=$full visible=$visible viewport=$viewport",
                full.top >= viewport.top && full.bottom <= viewport.bottom &&
                    kotlin.math.abs(full.top.value - visible.top.value) < 0.5f &&
                    kotlin.math.abs(full.bottom.value - visible.bottom.value) < 0.5f)
        }
        rule.onNodeWithTag("assistant-text").assertIsDisplayed()
        val rootBounds = rule.onRoot().getBoundsInRoot()
        val composer = rule.onNodeWithTag("assistant-text")
        val composerFull = composer.getUnclippedBoundsInRoot()
        val composerVisible = composer.getBoundsInRoot()
        assertTrue("composer must remain fully visible above the IME; full=$composerFull visible=$composerVisible root=$rootBounds",
            composerFull.top >= rootBounds.top && composerFull.bottom <= rootBounds.bottom &&
                kotlin.math.abs(composerFull.top.value - composerVisible.top.value) < 0.5f &&
                kotlin.math.abs(composerFull.bottom.value - composerVisible.bottom.value) < 0.5f)
        captureWindow("pending-recovery-ime-zh-large.png")
        rule.onNodeWithTag("assistant-turns").performScrollToNode(hasTestTag("assistant-pending-text"))
        rule.onNodeWithTag("assistant-pending-text").assertTextEquals(question)
        assertTrue(callbacks.sent.isEmpty())
        assertEquals(0, callbacks.records)
        assertEquals(0, callbacks.receiptChecks)
    }

    private fun capture(name: String) {
        val image = rule.onRoot().captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val uri = requireNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, "$name.png")
                put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PhotoHouseAssistantNavigation")
            }))
        try {
            context.contentResolver.openOutputStream(uri).use { output ->
                requireNotNull(output)
                check(image.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output))
            }
        } finally {
            image.recycle()
        }
    }

    private fun captureWindow(name: String) {
        rule.waitForIdle()
        InstrumentationRegistry.getInstrumentation().waitForIdleSync()
        val bitmap = InstrumentationRegistry.getInstrumentation().uiAutomation.takeScreenshot()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val uri = requireNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, name)
                put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PhotoHouseAssistantNavigation")
            }))
        try {
            context.contentResolver.openOutputStream(uri).use { output ->
                requireNotNull(output)
                check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output))
            }
        } finally {
            bitmap.recycle()
        }
    }

}
