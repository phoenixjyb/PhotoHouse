package dev.photohouse.connected

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.unit.Density
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Synthetic controls/layout only. No microphone, network, local provider or family data. */
@RunWith(AndroidJUnit4::class)
class AssistantVoiceWorkspaceUiTest {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()

    @Suppress("DEPRECATION")
    private fun journey(zh: Boolean) {
        rule.activity.runOnUiThread {
            // Match MainActivity; the generic test activity otherwise pans the
            // window during dictation-mode changes instead of resizing it.
            rule.activity.window.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        }
        val voice = mutableStateOf<AssistantVoiceSessionUiState?>(null)
        val assistant = mutableStateOf(AssistantClientState("synthetic-library", 1,
            capabilities = AssistantCapabilities(true, true, true, true, 30)))
        var starts = 0; var finishes = 0; var pauses = 0; var ends = 0; var sends = 0
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantScreen(assistant.value, zh, onBack = {}, previews = emptyMap(),
                        libraryLabel = if (zh) "合成旅行相册" else "Synthetic travel library",
                        accountLabel = if (zh) "当前账号" else "Current account",
                        onRetryCapabilities = {}, onSend = { sends++; true }, onClear = {},
                        onOpen = { _, _ -> }, onCheckReceipt = {}, onRecord = {},
                        onStopRecording = {}, onCancelRecording = {}, recording = false,
                        recordError = false, onClearTranscript = {}, onPlaySpeech = {}, onStopSpeech = {},
                        voiceSessionState = voice.value,
                        onStartVoiceSession = { starts++; voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.LISTENING) },
                        onPauseVoiceSession = { pauses++; voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.PAUSED) },
                        onResumeVoiceSession = { voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.LISTENING) },
                        onEndVoiceSession = { ends++; voice.value = null },
                        onFinishVoiceTurn = { finishes++; voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.TRANSCRIBING) })
                }
            }
        }
        rule.onNodeWithTag("assistant-library-context").assertIsDisplayed()
        rule.onNodeWithTag("assistant-text").performTextInput(if (zh) "保留这段草稿" else "Keep this unsent draft")
        rule.onNodeWithTag("assistant-start-voice-session").assertIsDisplayed().performClick()
        rule.onNodeWithTag("assistant-record").assertDoesNotExist()
        rule.onNodeWithTag("assistant-text").assertDoesNotExist()
        rule.onNodeWithTag("assistant-send").assertDoesNotExist()
        rule.onNodeWithTag("assistant-voice-pause").assertIsDisplayed()
        rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed()
        rule.onNodeWithTag("assistant-voice-finish-turn").assertIsDisplayed().performClick()
        rule.onNodeWithTag("assistant-voice-pause").performClick()
        rule.onNodeWithTag("assistant-voice-resume").assertIsDisplayed().performClick()
        saveRender(if (zh) "assistant-voice-zh-150.png" else "assistant-voice-en-150.png")
        rule.onNodeWithTag("assistant-voice-end").performClick()
        rule.onNodeWithTag("assistant-record").assertIsDisplayed()
        rule.onNodeWithTag("assistant-text").assertIsEnabled()
            .assertTextContains(if (zh) "保留这段草稿" else "Keep this unsent draft")
        rule.onNodeWithTag("assistant-retention-details-toggle").performClick()
        rule.onNodeWithTag("assistant-retention-details").assertIsDisplayed()
        assertEquals(1, starts); assertEquals(1, finishes); assertEquals(1, pauses); assertEquals(1, ends); assertEquals(0, sends)
    }

    @Test fun chineseVoiceControlsAndUnsentDraftAt150Percent() = journey(true)
    @Test fun englishVoiceControlsAndUnsentDraftAt150Percent() = journey(false)

    @Test fun uncertainTurnDoesNotOfferResume() {
        rule.setContent { PhotoHouseTheme {
            AssistantVoiceSessionPanel(AssistantVoiceSessionUiState(AssistantVoiceSessionStage.PAUSED,
                "Check the existing receipt before continuing.", canResume = false), false,
                onPause = {}, onResume = { error("An uncertain request must never resume automatically") }, onEnd = {})
        } }
        rule.onNodeWithTag("assistant-voice-resume").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed()
    }

    private fun saveRender(name: String) {
        rule.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        if (android.os.Build.VERSION.SDK_INT >= 29) {
            val committed = java.util.concurrent.CountDownLatch(1)
            instrumentation.runOnMainSync {
                val decor = rule.activity.window.decorView
                decor.viewTreeObserver.registerFrameCommitCallback { committed.countDown() }
                decor.invalidate()
            }
            check(committed.await(5, java.util.concurrent.TimeUnit.SECONDS)) { "The current UI frame did not commit" }
        }
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        val context = instrumentation.targetContext
        val folder = context.getExternalFilesDir("assistant-voice-qa")!!
        folder.mkdirs()
        try {
            java.io.File(folder, name).outputStream().use { stream ->
                check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, stream))
            }
        } finally { bitmap.recycle() }
    }
}
