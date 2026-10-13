package dev.photohouse.connected

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic memory-opening control fixture; no account, network or saved family data. */
@RunWith(AndroidJUnit4::class)
class AssistantMemoryOpeningUiTest {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()

    private val threadId = "11111111-1111-4111-8111-111111111111"
    private val turnId = "22222222-2222-4222-8222-222222222222"
    private val card = AssistantSavedMemoryCard("story", "33333333-3333-4333-8333-333333333333",
        "2", "e".repeat(64), "Garden day", "A short excerpt.")

    private fun workspace(recovered: Boolean = false): AssistantWorkspaceState {
        val result = AssistantTurn("memory_cards", "Found one saved memory.", null, null, emptyList(), 1, false, null,
            memoryCards = listOf(card), savedMemoryContext = AssistantSavedMemoryContext("synthetic-library",
                "f".repeat(64), listOf(AssistantSavedMemoryReference(card.kind, card.id, card.revision, card.sourceRevision))))
        val turn = AssistantWorkspaceTurn(1, threadId, turnId, AssistantWorkspaceRequestStatus.COMPLETED,
            1, recovered, null, result)
        val summary = AssistantWorkspaceThreadSummary(threadId, "synthetic-library", "2026-10-14T00:00:00Z",
            "2026-10-14T00:00:00Z", "2026-11-13T00:00:00Z", 1)
        return AssistantWorkspaceState(
            accountId = "synthetic-account", libraryId = "synthetic-library", generation = 1,
            capabilities = AssistantWorkspaceCapabilities(1, true, true, true, true, true),
            savedMemoryCardsAvailable = true, savedMemoryReadingAvailable = true,
            detail = AssistantWorkspaceThreadDetail(1, summary, emptyList()), currentTurn = turn,
            continuationEnabled = true,
        )
    }

    @Test fun freshCardShowsExplicitReadOpeningAndPreparingStopInChinese() {
        var reads = 0
        var stops = 0
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
            PhotoHouseTheme {
                PrivateAssistantPanel(workspace(), true,
                    onNew = {}, onRefresh = {}, onOpenThread = { _, _ -> }, onDraft = {}, onSend = {}, onRecover = {},
                    onDelete = { _, _ -> }, onSetLocale = {}, onDismiss = {},
                    assistant = AssistantClientState("synthetic-library", 1, speechBusy = true,
                        speechMemoryOpeningOrdinal = 0),
                    onReadSavedMemoryOpening = { reads++ }, onStopMemoryOpening = { stops++ })
            }
            }
        }
        rule.onNodeWithTag("private-assistant-read-memory-opening-0").assertIsDisplayed()
            .assertTextEquals("正在准备开篇语音…")
        rule.onNodeWithTag("private-assistant-memory-opening-preparing").assertIsDisplayed()
        rule.onNodeWithTag("private-assistant-memory-opening-stop").assertIsDisplayed().performClick()
        assertEquals(1, stops)
        rule.onNodeWithTag("private-assistant-read-memory-opening-0").assertIsDisplayed()
        assertEquals(0, reads)
        saveRender("zh")
    }

    @Test fun recoveredMemoryCardDoesNotExposeOpeningAction() {
        rule.setContent {
            PhotoHouseTheme {
                PrivateAssistantPanel(workspace(recovered = true), false,
                    onNew = {}, onRefresh = {}, onOpenThread = { _, _ -> }, onDraft = {}, onSend = {}, onRecover = {},
                    onDelete = { _, _ -> }, onSetLocale = {}, onDismiss = {}, onReadSavedMemoryOpening = {})
            }
        }
        rule.onNodeWithTag("private-assistant-memory-cards").assertDoesNotExist()
        rule.onNodeWithTag("private-assistant-read-memory-opening-0").assertDoesNotExist()
    }

    @Test fun freshCardShowsEnglishOpeningAction() {
        var reads = 0
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
            PhotoHouseTheme {
                PrivateAssistantPanel(workspace(), false,
                    onNew = {}, onRefresh = {}, onOpenThread = { _, _ -> }, onDraft = {}, onSend = {}, onRecover = {},
                    onDelete = { _, _ -> }, onSetLocale = {}, onDismiss = {},
                    onReadSavedMemoryOpening = { reads++ })
            }
            }
        }
        rule.onNodeWithTag("private-assistant-read-memory-opening-0").assertTextContains("Read opening").performClick()
        assertEquals(1, reads)
        saveRender("en")
    }

    @Test fun privatePanelOwnsSingleOpeningPlayerWhileCentralAssistantHasSameAudio() {
        val constructor = ProtectedAnnotationAudio::class.java.getDeclaredConstructor(ByteArray::class.java)
        constructor.isAccessible = true
        val audio = constructor.newInstance(ByteArray(256))
        val assistant = AssistantClientState("synthetic-library", 1, speechAudio = audio,
            speechMemoryOpeningOrdinal = 0)
        rule.setContent {
            Box {
                AssistantScreen(assistant, false, onBack = {}, previews = emptyMap(),
                    onRetryCapabilities = {}, onSend = { true }, onClear = {}, onOpen = { _, _ -> },
                    onCheckReceipt = {}, onRecord = {}, onStopRecording = {}, onCancelRecording = {},
                    recording = false, recordError = false, onClearTranscript = {}, onPlaySpeech = {},
                    onStopSpeech = {}, savedMemoryWorkspace = workspace(), onReadSavedMemoryOpening = {},
                    showMemoryOpeningPlayback = false)
                PrivateAssistantPanel(workspace(), false,
                    onNew = {}, onRefresh = {}, onOpenThread = { _, _ -> }, onDraft = {}, onSend = {},
                    onRecover = {}, onDelete = { _, _ -> }, onSetLocale = {}, onDismiss = {},
                    assistant = assistant, onReadSavedMemoryOpening = {})
            }
        }

        rule.onAllNodesWithTag("assistant-speech-playback", useUnmergedTree = true).assertCountEquals(1)
        rule.onNodeWithTag("assistant-speech-playback", useUnmergedTree = true).assertIsDisplayed()
        audio.close()
    }

    private fun saveRender(language: String) {
        rule.waitForIdle()
        val bitmap = rule.onRoot().captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        File(context.filesDir, "memory-opening-$language-150.png").outputStream().use { output ->
            check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output))
        }
        bitmap.recycle()
    }
}
