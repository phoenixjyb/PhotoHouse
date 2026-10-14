package dev.photohouse.connected

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import android.content.ContentValues
import android.provider.MediaStore
import android.os.Environment
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
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

    private fun syntheticWav(): ByteArray {
        val rate = 16_000
        val dataBytes = 30 * rate * 2
        return ByteArray(44 + dataBytes).also { bytes ->
            fun ascii(offset: Int, value: String) = value.toByteArray().copyInto(bytes, offset)
            fun u16(offset: Int, value: Int) { bytes[offset] = value.toByte(); bytes[offset + 1] = (value shr 8).toByte() }
            fun u32(offset: Int, value: Int) {
                for (i in 0..3) bytes[offset + i] = (value ushr (i * 8)).toByte()
            }
            ascii(0, "RIFF"); u32(4, bytes.size - 8); ascii(8, "WAVE")
            ascii(12, "fmt "); u32(16, 16); u16(20, 1); u16(22, 1)
            u32(24, rate); u32(28, rate * 2); u16(32, 2); u16(34, 16)
            ascii(36, "data"); u32(40, dataBytes)
        }
    }

    private fun workspace(recovered: Boolean = false, kind: String = "story"): AssistantWorkspaceState {
        val selectedCard = if (kind == card.kind) card else card.copy(kind = kind)
        val result = AssistantTurn("memory_cards", "Found one saved memory.", null, null, emptyList(), 1, false, null,
            memoryCards = listOf(selectedCard), savedMemoryContext = AssistantSavedMemoryContext("synthetic-library",
                "f".repeat(64), listOf(AssistantSavedMemoryReference(selectedCard.kind, selectedCard.id,
                    selectedCard.revision, selectedCard.sourceRevision))))
        val turn = AssistantWorkspaceTurn(1, threadId, turnId, AssistantWorkspaceRequestStatus.COMPLETED,
            1, recovered, null, result)
        val summary = AssistantWorkspaceThreadSummary(threadId, "synthetic-library", "2026-10-14T00:00:00Z",
            "2026-10-14T00:00:00Z", "2026-11-13T00:00:00Z", 1)
        return AssistantWorkspaceState(
            accountId = "synthetic-account", libraryId = "synthetic-library", generation = 1,
            capabilities = AssistantWorkspaceCapabilities(1, true, true, true, true, true),
            savedMemoryCardsAvailable = true, savedMemoryReadingAvailable = true, savedMemorySegmentReadingAvailable = true,
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

    @Test fun storySegmentStartsAtZeroAndContinueRequiresCompletedCurrentSegmentInChinese() {
        val reads = mutableListOf<Pair<Int, Int>>()
        val progress = AssistantMemorySegmentProgress(threadId, turnId, 1, 0, "story", 0, 2, 0)
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    PrivateAssistantPanel(workspace(), true,
                        onNew = {}, onRefresh = {}, onOpenThread = { _, _ -> }, onDraft = {}, onSend = {}, onRecover = {},
                        onDelete = { _, _ -> }, onSetLocale = {}, onDismiss = {},
                        assistant = AssistantClientState("synthetic-library", 1, speechMemorySegmentProgress = progress),
                        onReadSavedMemorySegment = { ordinal, segment -> reads += ordinal to segment })
                }
            }
        }
        rule.onNodeWithTag("private-assistant-read-memory-segment-0").assertIsDisplayed()
            .assertTextEquals("继续 · 第2/2段").performClick()
        rule.onNodeWithTag("private-assistant-memory-segment-guidance-0")
            .assertTextEquals("每次只朗读一段；播放结束后可继续，麦克风不会开启。")
        assertEquals(listOf(0 to 1), reads)
        saveRender("zh-segment")
    }

    @Test fun memoirSegmentStartsAtZeroInEnglishAndShowsExplicitContinuation() {
        val reads = mutableListOf<Pair<Int, Int>>()
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    PrivateAssistantPanel(workspace(kind = "memoir"), false,
                        onNew = {}, onRefresh = {}, onOpenThread = { _, _ -> }, onDraft = {}, onSend = {}, onRecover = {},
                        onDelete = { _, _ -> }, onSetLocale = {}, onDismiss = {},
                        assistant = AssistantClientState("synthetic-library", 1,
                            speechMemorySegmentProgress = AssistantMemorySegmentProgress(
                                threadId, turnId, 1, 0, "memoir", 0, 3, 0)),
                        onReadSavedMemorySegment = { ordinal, segment -> reads += ordinal to segment })
                }
            }
        }
        rule.onNodeWithTag("private-assistant-read-memory-segment-0").assertIsDisplayed()
            .assertTextEquals("Continue · Segment 2/3").performClick()
        rule.onNodeWithTag("private-assistant-memory-segment-guidance-0")
            .assertTextEquals("One segment at a time; continue after it finishes. The microphone stays off.")
        assertEquals(listOf(0 to 1), reads)
        saveRender("en-segment")
    }

    @Test fun centralAssistantShowsStoryChapterEntryAtLargeChineseText() {
        val reads = mutableListOf<Pair<Int, Int>>()
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantScreen(
                        AssistantClientState("synthetic-library", 1), true,
                        onBack = {}, previews = emptyMap(), onRetryCapabilities = {}, onSend = { true },
                        onClear = {}, onOpen = { _, _ -> }, onCheckReceipt = {}, onRecord = {},
                        onStopRecording = {}, onCancelRecording = {}, recording = false, recordError = false,
                        onClearTranscript = {}, onPlaySpeech = {}, onStopSpeech = {},
                        savedMemoryWorkspace = workspace(),
                        onReadSavedMemorySegment = { ordinal, segment -> reads += ordinal to segment },
                    )
                }
            }
        }
        rule.onNodeWithTag("assistant-read-memory-segment-0").assertIsDisplayed()
            .assertTextContains("朗读第一章").performClick()
        rule.onNodeWithTag("assistant-memory-segment-guidance-0")
            .assertTextEquals("每次只朗读一段；播放结束后可继续，麦克风不会开启。")
        assertEquals(listOf(0 to 0), reads)
        saveRender("zh-central-segment")
    }

    @Test fun stopRemainsAtTheActiveSavedSectionDuringPlayback() {
        val constructor = ProtectedAnnotationAudio::class.java.getDeclaredConstructor(ByteArray::class.java)
        constructor.isAccessible = true
        val audio = constructor.newInstance(syntheticWav())
        var stops = 0
        val progress = AssistantMemorySegmentProgress(threadId, turnId, 1, 0, "story", 0, 2, null)
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    PrivateAssistantPanel(workspace(), true,
                        onNew = {}, onRefresh = {}, onOpenThread = { _, _ -> }, onDraft = {}, onSend = {}, onRecover = {},
                        onDelete = { _, _ -> }, onSetLocale = {}, onDismiss = {},
                        assistant = AssistantClientState("synthetic-library", 1, speechAudio = audio,
                            speechMemorySegmentProgress = progress),
                        onReadSavedMemorySegment = { _, _ -> }, onStopMemoryOpening = { stops++ })
                }
            }
        }
        rule.onNodeWithTag("private-assistant-stop-memory-segment-0").performScrollTo()
            .assertIsDisplayed().assertTextEquals("停止").assertHasClickAction().performClick()
        rule.runOnIdle { assertEquals(1, stops) }
        saveRender("zh-segment-active-stop")
        audio.close()
    }

    @Test fun completedStoryCanBeExplicitlyReadAgainFromItsFirstSegment() {
        val reads = mutableListOf<Pair<Int, Int>>()
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    PrivateAssistantPanel(workspace(), true,
                        onNew = {}, onRefresh = {}, onOpenThread = { _, _ -> }, onDraft = {}, onSend = {}, onRecover = {},
                        onDelete = { _, _ -> }, onSetLocale = {}, onDismiss = {},
                        assistant = AssistantClientState("synthetic-library", 1,
                            speechMemorySegmentProgress = AssistantMemorySegmentProgress(
                                threadId, turnId, 1, 0, "story", 1, 2, 1)),
                        onReadSavedMemorySegment = { ordinal, segment -> reads += ordinal to segment })
                }
            }
        }
        rule.onNodeWithTag("private-assistant-read-memory-segment-0").assertIsDisplayed()
            .assertTextEquals("重新朗读第一章").performClick()
        assertEquals(listOf(0 to 0), reads)
        saveRender("zh-segment-restart")
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
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "photohouse-memory-segments-$language-150.png")
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/PhotoHouseMemorySegments")
        }
        val imageUri = requireNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        context.contentResolver.openOutputStream(imageUri)?.use { output ->
            check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output))
        } ?: error("could not write synthetic UI render")
        bitmap.recycle()
    }
}
