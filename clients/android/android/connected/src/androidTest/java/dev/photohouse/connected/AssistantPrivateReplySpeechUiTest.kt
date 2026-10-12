package dev.photohouse.connected

import android.content.ContentValues
import android.provider.MediaStore
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.Asset
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic private reply speech controls only. No microphone, network, or family data. */
@RunWith(AndroidJUnit4::class)
class AssistantPrivateReplySpeechUiTest {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()

    private val clarification = AssistantTurn(
        "clarification", "你想找的是哪一次家庭旅行？", null, null, emptyList(), 0, false, null,
    )

    private fun show(
        turn: AssistantTurn = clarification,
        speechBusy: Boolean = false,
        speechAvailable: Boolean = true,
        voice: AssistantVoiceSessionUiState? = null,
        onPlay: () -> Unit = {},
        onStartVoice: () -> Unit = {},
        onRecord: () -> Unit = {},
        onPauseVoice: () -> Unit = {},
        onEndVoice: () -> Unit = {},
    ) {
        val state = AssistantClientState(
            "synthetic-library", 1,
            capabilities = AssistantCapabilities(true, true, true, true, 30),
            turns = listOf(AssistantExchange("帮我找找", turn, "synthetic-private-turn")),
            speechBusy = speechBusy,
            privateThreadId = "00000000-0000-4000-8000-000000000001",
        )
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantScreen(state, true, onBack = {}, previews = emptyMap(),
                        libraryLabel = "合成家庭相册", accountLabel = "当前账号",
                        onRetryCapabilities = {}, onSend = { true }, onClear = {},
                        onOpen = { _, _ -> }, onCheckReceipt = {}, onRecord = onRecord,
                        onStopRecording = {}, onCancelRecording = {}, recording = false,
                        recordError = false, onClearTranscript = {}, onPlaySpeech = onPlay,
                        onStopSpeech = {}, voiceSessionState = voice,
                        onStartVoiceSession = onStartVoice,
                        onPauseVoiceSession = onPauseVoice,
                        onResumeVoiceSession = {}, onEndVoiceSession = onEndVoice,
                        onFinishVoiceTurn = {}, privateReplySpeechEnabled = true,
                        privateReplySpeechAvailable = speechAvailable)
                }
            }
        }
    }

    @Test fun freshClarificationOffersExplicitReadWithoutStartingMicrophoneAt150Percent() {
        var plays = 0
        var voiceStarts = 0
        var recordings = 0
        show(onPlay = { plays++ }, onStartVoice = { voiceStarts++ }, onRecord = { recordings++ })

        rule.onNodeWithTag("assistant-reply").assertTextEquals("你想找的是哪一次家庭旅行？")
        rule.onNodeWithTag("assistant-play-speech").assertIsDisplayed()
        rule.onNodeWithTag("assistant-play-speech").performClick()
        assertEquals(1, plays)
        assertEquals(0, voiceStarts)
        assertEquals(0, recordings)
        saveScreenshot("private-reply-speech-fresh-zh-150.png")
    }

    @Test fun loadingPrivateReplyKeepsProgressAndDisablesReadButtonAt150Percent() {
        show(speechBusy = true, speechAvailable = true)

        rule.onNodeWithTag("assistant-speech-loading").assertIsDisplayed()
        rule.onNodeWithTag("assistant-play-speech").assertIsNotEnabled()
        rule.onNodeWithText("朗读助手回复", substring = false).assertIsDisplayed()
        saveScreenshot("private-reply-speech-loading-zh-150.png")
    }

    @Test fun unavailableOverLimitReplyDoesNotFallBackToResultCountSpeech() {
        val asset = Asset("17", "image", 800, 600, null, null, "/assets/17/thumbnail?library=synthetic-library")
        val overLimit = AssistantTurn("results", "词".repeat(601), null, null, listOf(asset), 1, false, null)
        show(turn = overLimit, speechAvailable = false)

        rule.onNodeWithTag("assistant-play-speech").assertDoesNotExist()
        rule.onNodeWithTag("assistant-reply-speech-unavailable").assertIsDisplayed()
        rule.onNodeWithText("播放结果数量语音", substring = false).assertDoesNotExist()
        saveScreenshot("private-reply-speech-unavailable-zh-150.png")
    }

    @Test fun speakingSessionShowsPauseAndEndAlongsideReplyTextAt150Percent() {
        var pauses = 0
        var ends = 0
        show(voice = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.SPEAKING, "正在朗读助手回复"),
            onPauseVoice = { pauses++ }, onEndVoice = { ends++ })

        rule.onNodeWithTag("assistant-voice-session-status").assertTextEquals("正在回答")
        rule.onNodeWithTag("assistant-reply").assertTextEquals("你想找的是哪一次家庭旅行？")
        rule.onNodeWithTag("assistant-voice-pause").assertIsDisplayed().performClick()
        rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed().performClick()
        assertEquals(1, pauses)
        assertEquals(1, ends)
        rule.onNodeWithText("播放结果数量语音", substring = false).assertDoesNotExist()
        saveScreenshot("private-reply-speech-speaking-zh-150.png")
    }

    private fun saveScreenshot(name: String) {
        rule.waitForIdle()
        val image = rule.onRoot().captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val uri = requireNotNull(context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, name)
                put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PhotoHousePrivateAssistantSpeech")
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
}
