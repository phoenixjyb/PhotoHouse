package dev.photohouse.connected

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.*
import kotlinx.coroutines.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Synthetic ASR responses use no family account or server; one test captures on an emulator microphone. */
@RunWith(AndroidJUnit4::class)
class MemoryDictationUiTest {
    @get:Rule val rule = createComposeRule()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    @After fun close() { scope.cancel() }

    private fun shellOutput(command: String): String {
        val pfd = InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand(command)
        return android.os.ParcelFileDescriptor.AutoCloseInputStream(pfd).bufferedReader().use { it.readText() }
    }

    private fun editor(speech: MemoryDictationStore, save: (StoryMutation) -> Unit = {}) =
        ProtectedStoryEditorStore(scope, "42", null, { mutation ->
            save(mutation)
            ProtectedStory("10000000-0000-0000-0000-000000000001", "42", mutation.draft.title,
                mutation.draft.text, mutation.draft.language, mutation.draft.byline, "synthetic-account", 1, 100, 100, true, true)
        }, { null }, {}, {}, dictation = speech)

    @Test fun reviewedChineseSpeechIsAppendedThenExplicitlySaved() {
        var saves = 0
        var saved: StoryMutation? = null
        val speech = MemoryDictationStore(scope, { AssistantCapabilities(true, true, true, false, 30) }, { _, id ->
            AssistantTranscript("我们一起种花。", "zh", AssistantRequestReceipt(id, "enabled", "succeeded"))
        })
        val editor = editor(speech) { saves++; saved = it }
        rule.setContent { ProtectedStoryEditorDialog(editor, onDismiss = {}, zh = true) }
        rule.waitUntil(5000) { speech.state.value.capabilities != null }
        rule.onNodeWithTag("memory-dictation-record").assertTextContains("录音讲回忆")
        rule.onNodeWithText("说说这段回忆").assertExists()
        rule.onNodeWithText("录音 → 检查文字 → 加入回忆。回忆只保存文字，不保留录音；转写记录保留 30 天。")
            .assertExists()
        rule.onNodeWithTag("story-editor-title").performScrollTo().performTextInput("花园里的下午")
        rule.onNodeWithTag("story-editor-byline").performScrollTo().performTextInput("奶奶")
        rule.onNodeWithTag("story-editor-text").performScrollTo().performTextInput("原有文字。")
        rule.runOnIdle { speech.beginRecording(); speech.stopRecording(wav()) }
        rule.waitUntil(5000) { speech.state.value.transcript != null }
        rule.onNodeWithTag("memory-dictation-transcript-ready", useUnmergedTree = true)
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite))
        assertEquals("原有文字。", editor.state.value.draft.text)
        assertEquals(0, saves)
        rule.onNodeWithTag("story-editor-review").performScrollTo().assertIsNotEnabled()
        rule.onNodeWithTag("memory-dictation-transcript").performScrollTo().performTextReplacement("奶奶和我们一起种花。")
        rule.onNodeWithTag("memory-dictation-insert").assertTextEquals("加入回忆")
        capture("memory-dictation-preview.png")
        rule.onNodeWithTag("memory-dictation-insert").performScrollTo().performClick()
        assertEquals("原有文字。\n\n奶奶和我们一起种花。", editor.state.value.draft.text)
        assertEquals(0, saves)
        rule.onNodeWithTag("story-editor-review").performScrollTo().performClick()
        rule.onNodeWithTag("story-editor-confirm").performScrollTo().performClick()
        rule.waitUntil(5000) { editor.state.value.phase == StoryEditorPhase.SAVED }
        assertEquals(1, saves)
        assertEquals("原有文字。\n\n奶奶和我们一起种花。", saved!!.draft.text)
        rule.onNodeWithTag("story-editor-saved").assertExists()
        capture("memory-dictation-saved.png")
    }

    @Test fun cancellingTranscriptionDropsLateWordsAndKeepsTypedDraft() {
        val gate = CompletableDeferred<Unit>()
        val speech = MemoryDictationStore(scope, { AssistantCapabilities(true, true, true, false, 30) }, { _, _ ->
            withContext(NonCancellable) { gate.await() }
            AssistantTranscript("不应出现的文字", "zh")
        })
        val editor = editor(speech)
        rule.setContent { ProtectedStoryEditorDialog(editor, onDismiss = {}, zh = true) }
        rule.waitUntil(5000) { speech.state.value.capabilities != null }
        rule.runOnIdle { editor.updateText("保留这段文字"); speech.beginRecording(); speech.stopRecording(wav()) }
        rule.onNodeWithTag("memory-dictation-transcribing").performScrollTo().assertExists()
        rule.onNodeWithText("取消转写").performScrollTo().performClick()
        rule.runOnIdle { gate.complete(Unit) }
        rule.waitForIdle()
        rule.onNodeWithTag("memory-dictation-transcript").assertDoesNotExist()
        assertEquals("保留这段文字", editor.state.value.draft.text)
        rule.runOnIdle { editor.close() }
    }

    @Test fun recordingAndTranscriptionStatusesArePoliteAndErrorsFollowUiLanguage() {
        var gate = CompletableDeferred<Unit>()
        var zh by androidx.compose.runtime.mutableStateOf(false)
        var insertions = 0
        val speech = MemoryDictationStore(scope, { AssistantCapabilities(true, true, true, false, 30) }, { _, _ ->
            withContext(NonCancellable) { gate.await() }
            throw ApiFailure(FailureKind.OFFLINE)
        })
        rule.setContent {
            MemoryDictationInput(speech, zh, onInsert = { insertions++ },
                purpose = MemoryDictationPurpose.CHAT_MESSAGE)
        }
        rule.waitUntil(5000) { speech.state.value.capabilities != null }

        rule.runOnIdle {
            assertNotNull(speech.beginRecording())
        }
        rule.onNodeWithTag("memory-dictation-recording", useUnmergedTree = true)
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite))
        rule.runOnIdle { speech.stopRecording(wav()) }
        rule.waitUntil(5000) { speech.state.value.transcribing }
        rule.onNodeWithTag("memory-dictation-transcribing", useUnmergedTree = true)
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite))
        rule.runOnIdle { gate.complete(Unit) }
        rule.waitUntil(5000) { speech.state.value.failureCode == MemoryDictationFailure.OFFLINE }
        rule.onNodeWithTag("memory-dictation-failure", useUnmergedTree = true)
            .assertTextEquals("Offline. Reconnect and try again.")
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite))
        assertEquals(0, insertions)

        rule.runOnIdle {
            zh = true
            speech.cancel()
            gate = CompletableDeferred()
            assertNotNull(speech.beginRecording())
            speech.stopRecording(wav())
            gate.complete(Unit)
        }
        rule.waitUntil(5000) { speech.state.value.failureCode == MemoryDictationFailure.OFFLINE }
        rule.onNodeWithTag("memory-dictation-failure", useUnmergedTree = true)
            .assertTextEquals("当前离线，请联网后重试。")
        assertEquals(0, insertions)
        speech.close()
    }

    @Test fun unavailableVoiceLeavesTextEditingAvailable() {
        val speech = MemoryDictationStore(scope, { AssistantCapabilities(true, true, false, false, 0) }, { _, _ -> error("No ASR request allowed") })
        val editor = editor(speech)
        rule.setContent { ProtectedStoryEditorDialog(editor, onDismiss = {}, zh = true) }
        rule.waitUntil(5000) { speech.state.value.capabilities != null }
        rule.onNodeWithText("语音暂不可用，仍可在下方填写回忆。").performScrollTo().assertIsDisplayed()
        rule.onNodeWithTag("memory-dictation-record").assertDoesNotExist()
        rule.onNodeWithTag("story-editor-text").performScrollTo().performTextInput("手写的回忆")
        rule.onNodeWithTag("story-editor-review").performScrollTo().performClick()
        rule.onNodeWithTag("story-editor-confirm").performScrollTo().assertIsEnabled()
        rule.runOnIdle { editor.close() }
    }

    @Test fun emulatorMicrophoneStopsAndPassesWavToSyntheticAsr() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val pkg = instrumentation.targetContext.packageName
        val grant = shellOutput("pm grant $pkg android.permission.RECORD_AUDIO")
        assertEquals("pm grant output=$grant",
            PackageManager.PERMISSION_GRANTED,
            instrumentation.targetContext.checkSelfPermission(Manifest.permission.RECORD_AUDIO))
        var requests = 0
        var bytesSent = 0
        val speech = MemoryDictationStore(scope, { AssistantCapabilities(true, true, true, false, 30) }, { bytes, _ ->
            requests++; bytesSent = bytes.size
            AssistantTranscript("模拟器录音后的示例文字", "zh")
        })
        val editor = editor(speech)
        rule.setContent { ProtectedStoryEditorDialog(editor, onDismiss = {}, zh = true) }
        rule.waitUntil(5000) { speech.state.value.capabilities != null }
        rule.onNodeWithTag("memory-dictation-record").performScrollTo().performClick()
        rule.waitUntil(5000) { speech.state.value.recording }
        // AudioRecord is exercised on the emulator; the transcript is explicitly synthetic.
        val stopError = runCatching {
            rule.waitUntil(10000) { runCatching { rule.onNodeWithTag("memory-dictation-stop").assertIsEnabled() }.isSuccess }
        }.exceptionOrNull()
        if (stopError != null) {
            val permission = instrumentation.targetContext.checkSelfPermission(Manifest.permission.RECORD_AUDIO)
            val semantics = runCatching { rule.onRoot(useUnmergedTree = true).printToString() }
                .getOrDefault("semantics dump unavailable").lineSequence().take(80).joinToString("\n")
            val audioDump = runCatching { shellOutput("dumpsys audio | grep -i -E 'record|input|active' | tail -30") }
                .getOrDefault("audio service dump unavailable").takeLast(3000)
            val audioLog = runCatching { shellOutput("logcat -d -t 400 -s AudioRecord AudioFlinger AudioPolicyManager") }
                .getOrDefault("audio log unavailable").takeLast(3000)
            throw AssertionError("AudioRecord did not enable Stop within 10 s; permission=$permission; " +
                "dictationState=${speech.state.value}; semantics:\n$semantics\naudio dump:\n$audioDump\naudio log:\n$audioLog", stopError)
        }
        rule.onNodeWithTag("memory-dictation-stop").performScrollTo().performClick()
        rule.waitUntil(5000) { speech.state.value.transcript != null || speech.state.value.failure != null }
        assertNull(speech.state.value.failure)
        assertEquals(1, requests)
        assertTrue(bytesSent >= 16044)
        rule.onNodeWithTag("memory-dictation-transcript").assertTextContains("模拟器录音后的示例文字")
        assertEquals("", editor.state.value.draft.text)
        rule.runOnIdle { editor.close() }
    }

    private fun wav(): ByteArray = java.nio.ByteBuffer.allocate(32044).order(java.nio.ByteOrder.LITTLE_ENDIAN).apply {
        put("RIFF".toByteArray()); putInt(32036); put("WAVEfmt ".toByteArray()); putInt(16)
        putShort(1); putShort(1); putInt(16000); putInt(32000); putShort(2); putShort(16)
        put("data".toByteArray()); putInt(32000)
    }.array()

    private fun capture(name: String) {
        rule.waitForIdle()
        val bitmap = rule.onNodeWithTag("protected-story-editor").captureToImage().asAndroidBitmap()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        File(context.filesDir, name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
}
