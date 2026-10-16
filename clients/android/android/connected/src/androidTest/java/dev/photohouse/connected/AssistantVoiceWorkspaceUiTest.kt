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
                        onStartVoiceSession = { starts++; voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.OPENING_MIC,
                            "The microphone is opening. Speak when Listening appears.") },
                        onPauseVoiceSession = { pauses++; voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.PAUSED) },
                        onResumeVoiceSession = { voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.LISTENING,
                            assistantVoiceListeningDetail(zh),
                            microphoneActive = true) },
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
        rule.onNodeWithTag("assistant-voice-session-status").assertTextEquals(if (zh) "正在开启麦克风" else "Opening microphone")
        rule.onNodeWithTag("assistant-voice-microphone-state").assertTextEquals(if (zh) "麦克风已关闭" else "MICROPHONE OFF")
        rule.onNodeWithTag("assistant-voice-activity-indicator")
            .assertContentDescriptionEquals(if (zh) "正在开启麦克风" else "Opening microphone")
        voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.LISTENING,
            assistantVoiceListeningDetail(zh),
            microphoneActive = true)
        rule.onNodeWithTag("assistant-voice-session-status").assertTextEquals(if (zh) "正在聆听" else "Listening")
        rule.onNodeWithTag("assistant-voice-microphone-state").assertTextEquals(if (zh) "麦克风已开启" else "MICROPHONE ON")
        rule.onNodeWithTag("assistant-voice-activity-indicator")
            .assertContentDescriptionEquals(if (zh) "正在聆听" else "Listening")
        voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.PREPARING_REPLY,
            if (zh) "麦克风已关闭，正在准备语音回复。" else "Microphone off. Preparing the spoken reply.")
        rule.onNodeWithTag("assistant-voice-session-status").assertTextEquals(if (zh) "正在准备回复" else "Preparing reply")
        rule.onNodeWithTag("assistant-voice-microphone-state").assertTextEquals(if (zh) "麦克风已关闭" else "MICROPHONE OFF")
        voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.SPEAKING)
        rule.onNodeWithTag("assistant-voice-session-status").assertTextEquals(if (zh) "正在回答" else "Speaking")
        rule.onNodeWithTag("assistant-voice-activity-indicator")
            .assertContentDescriptionEquals(if (zh) "正在回答" else "Speaking")
        voice.value = AssistantVoiceSessionUiState(AssistantVoiceSessionStage.LISTENING, microphoneActive = true)
        rule.onNodeWithTag("assistant-voice-finish-turn").assertIsDisplayed().performClick()
        rule.onNodeWithTag("assistant-voice-pause").performClick()
        rule.onNodeWithTag("assistant-voice-resume").assertIsDisplayed().performClick()
        rule.onNodeWithTag("assistant-voice-session-detail")
            .assertTextContains(if (zh) "暂停”或“结束语音" else "pause” or “end voice chat", substring = true)
        rule.onNodeWithTag("assistant-voice-pause").assertIsDisplayed()
        rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed()
        saveRender(if (zh) "assistant-voice-zh-150.png" else "assistant-voice-en-150.png")
        rule.onNodeWithTag("assistant-voice-end").performClick()
        rule.onNodeWithTag("assistant-voice-ready").assertIsDisplayed()
        rule.onNodeWithTag("assistant-voice-ready-microphone")
            .assertTextContains(if (zh) "麦克风关闭" else "Microphone off", substring = true)
        rule.onNodeWithTag("assistant-record").assertIsDisplayed()
        rule.onNodeWithTag("assistant-text").assertIsEnabled()
            .assertTextContains(if (zh) "保留这段草稿" else "Keep this unsent draft")
        saveRender(if (zh) "assistant-voice-ready-zh-150.png" else "assistant-voice-ready-en-150.png")
        rule.onNodeWithTag("assistant-retention-details-toggle").performClick()
        rule.onNodeWithTag("assistant-retention-details").assertIsDisplayed()
        assertEquals(1, starts); assertEquals(1, finishes); assertEquals(1, pauses); assertEquals(1, ends); assertEquals(0, sends)
    }

    @Test fun chineseVoiceControlsAndUnsentDraftAt150Percent() = journey(true)
    @Test fun englishVoiceControlsAndUnsentDraftAt150Percent() = journey(false)

    @Test fun chineseTurnTimingIsCollapsedAndKeepsPauseEndVisibleAt150Percent() = turnTimingRender(true)

    @Test fun englishTurnTimingIsCollapsedAndKeepsPauseEndVisibleAt150Percent() = turnTimingRender(false)

    @Test fun chineseVoiceFailureRecoveryAt150Percent() = voiceFailureRecoveryRender(true)

    @Test fun englishVoiceFailureRecoveryAt150Percent() = voiceFailureRecoveryRender(false)

    private fun voiceFailureRecoveryRender(zh: Boolean) {
        val failures = listOf(
            VoiceSessionStopReason.TRANSCRIPTION_FAILED to "recognition",
            VoiceSessionStopReason.REQUEST_FAILED to "request",
            VoiceSessionStopReason.SPEECH_FAILED to "playback",
        )
        val selectedReason = mutableStateOf(failures.first().first)
        var resumes = 0
        var ends = 0
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantVoiceSessionPanel(
                        AssistantVoiceSessionUiState(
                            AssistantVoiceSessionStage.PAUSED,
                            detail = requireNotNull(assistantVoiceFailureDetail(selectedReason.value, zh)),
                            canResume = true,
                            microphoneActive = false,
                            reason = selectedReason.value,
                        ), zh,
                        onPause = {}, onResume = { resumes++ }, onEnd = { ends++ },
                    )
                }
            }
        }
        for ((reason, stage) in failures) {
            rule.runOnIdle {
                resumes = 0
                ends = 0
                selectedReason.value = reason
            }
            val detail = requireNotNull(assistantVoiceFailureDetail(reason, zh))
            rule.onNodeWithTag("assistant-voice-session-status")
                .assertTextEquals(if (zh) "语音对话已暂停" else "Voice conversation paused")
            rule.onNodeWithTag("assistant-voice-session-detail").assertTextEquals(detail)
            rule.onNodeWithTag("assistant-voice-microphone-state")
                .assertTextEquals(if (zh) "麦克风已关闭" else "MICROPHONE OFF")
            rule.onNodeWithTag("assistant-voice-resume").assertIsDisplayed().assertIsEnabled()
            rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed().assertIsEnabled()
            rule.runOnIdle {
                assertEquals("Rendering a failure state must not invoke controls", 0, resumes)
                assertEquals("Rendering a failure state must not end the session", 0, ends)
            }
            saveRender("voice-failure-$stage-${if (zh) "zh" else "en"}-150.png")
            rule.onNodeWithTag("assistant-voice-resume").performClick()
            rule.runOnIdle { assertEquals(1, resumes) }
            rule.onNodeWithTag("assistant-voice-end").performClick()
            rule.runOnIdle { assertEquals(1, ends) }
        }
    }

    private fun turnTimingRender(zh: Boolean) {
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantVoiceSessionPanel(
                        AssistantVoiceSessionUiState(
                            AssistantVoiceSessionStage.SPEAKING,
                            microphoneActive = false,
                            clientTiming = VoiceTurnTimingSummary(1_250, 2_300, 780, 4_600),
                        ), zh,
                        onPause = {}, onResume = {}, onEnd = {},
                    )
                }
            }
        }
        rule.onNodeWithTag("assistant-voice-pause").assertIsDisplayed()
        rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed()
        rule.onNodeWithTag("assistant-voice-timing-details").assertDoesNotExist()
        rule.onNodeWithTag("assistant-voice-timing-toggle").assertTextEquals(if (zh) "上轮用时" else "Last turn timing")
        saveRender(if (zh) "assistant-voice-timing-collapsed-zh-150.png" else "assistant-voice-timing-collapsed-en-150.png")
        rule.onNodeWithTag("assistant-voice-timing-toggle").performClick()
        rule.onNodeWithTag("assistant-voice-timing-details").assertIsDisplayed()
        rule.onNodeWithText(if (zh) "语音识别" else "Recognition").assertIsDisplayed()
        rule.onNodeWithText(if (zh) "助手请求" else "Assistant request").assertIsDisplayed()
        rule.onNodeWithText(if (zh) "语音准备" else "Prepare speech").assertIsDisplayed()
        rule.onNodeWithText(if (zh) "语音播放" else "Playback").assertIsDisplayed()
        rule.onNodeWithTag("assistant-voice-timing-note").assertTextContains(
            if (zh) "客户端观测时间" else "Client-observed", substring = true)
        rule.onNodeWithTag("assistant-voice-pause").assertIsDisplayed()
        rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed()
        saveRender(if (zh) "assistant-voice-timing-expanded-zh-150.png" else "assistant-voice-timing-expanded-en-150.png")
    }

    @Test fun freshSavedMemoryCardHasExplicitReaderActionAtLargeTextZh() = freshMemoryCardRender(true,
        "saved-memory-card-zh-150.png")

    @Test fun freshSavedMemoryCardHasExplicitReaderActionAtLargeTextEn() = freshMemoryCardRender(false,
        "saved-memory-card-en-150.png")

    private fun freshMemoryCardRender(zh: Boolean, screenshotName: String) {
        val threadId = "123e4567-e89b-42d3-a456-426614174000"
        val turnId = "123e4567-e89b-42d3-a456-426614174001"
        val card = AssistantSavedMemoryCard("memoir", "123e4567-e89b-42d3-a456-426614174002", "2",
            "a".repeat(64), "Family year", "A short family excerpt.")
        val currentTurn = AssistantWorkspaceTurn(1, threadId, turnId, AssistantWorkspaceRequestStatus.COMPLETED,
            2, false, null, AssistantTurn("memory_cards", "Found a memoir.", null, null, emptyList(), 1, false, null,
                memoryCards = listOf(card), savedMemoryContext = AssistantSavedMemoryContext("synthetic-library",
                    "b".repeat(64), listOf(AssistantSavedMemoryReference(card.kind, card.id, card.revision, card.sourceRevision)))))
        val workspace = AssistantWorkspaceState(accountId = "synthetic-account", libraryId = "synthetic-library", generation = 1,
            savedMemoryCardsAvailable = true, savedMemoryReaderAvailable = true,
            detail = AssistantWorkspaceThreadDetail(1, AssistantWorkspaceThreadSummary(threadId, "synthetic-library",
                "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", "2026-11-01T00:00:00Z", 2), emptyList()),
            currentTurn = currentTurn)
        var opened = -1
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantScreen(AssistantClientState("synthetic-library", 1), zh, onBack = {}, previews = emptyMap(),
                        onRetryCapabilities = {}, onSend = { true }, onClear = {}, onOpen = { _, _ -> }, onCheckReceipt = {},
                        onRecord = {}, onStopRecording = {}, onCancelRecording = {}, recording = false, recordError = false,
                        onClearTranscript = {}, onPlaySpeech = {}, onStopSpeech = {}, savedMemoryWorkspace = workspace,
                        onOpenSavedMemoryCard = { opened = it })
                }
            }
        }
        rule.onNodeWithTag("assistant-saved-memory-cards").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Family year").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("assistant-open-saved-memory-0").performScrollTo()
            .assertTextContains(if (zh) "打开回忆录" else "Open memoir")
        saveMemoryReaderRender(screenshotName)
        rule.onNodeWithTag("assistant-open-saved-memory-0").performClick()
        assertEquals(0, opened)
    }

    private fun saveMemoryReaderRender(name: String) {
        rule.waitForIdle()
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.waitForIdleSync()
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        val folder = instrumentation.targetContext.externalCacheDir?.resolve("saved-memory-reader")
            ?: error("External app cache is unavailable")
        check(folder.exists() || folder.mkdirs())
        try {
            java.io.File(folder, name).outputStream().use { stream ->
                check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, stream))
            }
        } finally { bitmap.recycle() }
    }

    @Test fun uncertainTurnDoesNotOfferResume() {
        rule.setContent { PhotoHouseTheme {
            AssistantVoiceSessionPanel(AssistantVoiceSessionUiState(AssistantVoiceSessionStage.PAUSED,
                "Check the existing receipt before continuing.", canResume = false), false,
                onPause = {}, onResume = { error("An uncertain request must never resume automatically") }, onEnd = {})
        } }
        rule.onNodeWithTag("assistant-voice-resume").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed()
    }

    @Test fun uncertainVoiceSessionOffersReceiptCheckAt150PercentInBothLanguages() {
        val assistant = mutableStateOf(AssistantClientState(
            "synthetic-library", 1,
            capabilities = AssistantCapabilities(true, true, true, true, 30),
            pendingTurn = AssistantPendingTurn(
                accountId = "synthetic-account", library = "synthetic-library", generation = 1,
                text = "Find the vacation photos", context = null, parentRequestId = null,
                requestId = "synthetic-uncertain-request",
            ),
        ))
        val voice = mutableStateOf(AssistantVoiceSessionUiState(
            AssistantVoiceSessionStage.PAUSED,
            "请先查询现有回执，再继续；不会重新发送请求。",
            canResume = false,
        ))
        val zh = mutableStateOf(true)
        var receiptChecks = 0
        var resumed = 0
        rule.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                PhotoHouseTheme {
                    AssistantScreen(
                        assistant.value, zh.value, onBack = {}, previews = emptyMap(),
                        onRetryCapabilities = {}, onSend = { false }, onClear = {},
                        onOpen = { _, _ -> }, onCheckReceipt = {
                            receiptChecks++
                            assistant.value = assistant.value.copy(receiptChecking = true)
                        },
                        onRecord = {}, onStopRecording = {}, onCancelRecording = {}, recording = false,
                        recordError = false, onClearTranscript = {}, onPlaySpeech = {}, onStopSpeech = {},
                        voiceSessionState = voice.value,
                        onPauseVoiceSession = {}, onResumeVoiceSession = { resumed++ }, onEndVoiceSession = {},
                    )
                }
            }
        }

        rule.onNodeWithTag("assistant-voice-check-receipt").assertIsDisplayed().assertTextEquals("查询回执")
        rule.onNodeWithTag("assistant-voice-resume").assertIsDisplayed().assertIsNotEnabled()
        rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed()
        saveRender("assistant-voice-uncertain-receipt-zh-150.png")
        rule.onNodeWithTag("assistant-voice-check-receipt").performClick()
        assertEquals(1, receiptChecks)
        assertEquals("uncertain voice requests cannot be resumed", 0, resumed)
        rule.onNodeWithTag("assistant-voice-check-receipt").assertTextEquals("正在查询回执…")
        rule.onNodeWithTag("assistant-voice-check-receipt").assertIsNotEnabled()

        rule.runOnIdle {
            assistant.value = assistant.value.copy(receiptChecking = false)
            zh.value = false
        }
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-voice-check-receipt").assertIsDisplayed().assertTextEquals("Check receipt")
        rule.onNodeWithTag("assistant-voice-resume").assertIsNotEnabled()
        rule.onNodeWithTag("assistant-voice-end").assertIsDisplayed()
        saveRender("assistant-voice-uncertain-receipt-en-150.png")

        rule.runOnIdle { assistant.value = assistant.value.copy(pendingTurn = null) }
        rule.waitForIdle()
        rule.onNodeWithTag("assistant-voice-check-receipt").assertDoesNotExist()
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
        val values = android.content.ContentValues().apply {
            put(android.provider.MediaStore.Images.Media.DISPLAY_NAME, name)
            put(android.provider.MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(android.provider.MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PhotoHouseAssistantVoiceRecovery")
        }
        val uri = checkNotNull(context.contentResolver.insert(
            android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values))
        try {
            context.contentResolver.openOutputStream(uri).use { stream ->
                checkNotNull(stream)
                check(bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, stream))
            }
        } finally { bitmap.recycle() }
    }
}
