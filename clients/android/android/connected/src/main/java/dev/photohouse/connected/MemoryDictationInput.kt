package dev.photohouse.connected

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.input.ImeAction
import dev.photohouse.connected.core.MemoryDictationFailure
import dev.photohouse.connected.core.MemoryDictationStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/** Speech is reviewed separately; only the parent's explicit insert action changes the draft. */
internal enum class MemoryDictationPurpose { MEMORY_EDITOR, CHAT_MESSAGE, MEMOIR_INSTRUCTIONS }

private fun memoryDictationFailureMessage(code: MemoryDictationFailure?, zh: Boolean): String = when (code) {
    MemoryDictationFailure.INVALID_RECORDING -> if (zh) "录音无效或过长。" else "The recording was invalid or too long."
    MemoryDictationFailure.UNUSABLE_TRANSCRIPT -> if (zh) "无法使用这段转写，请重试。" else "This transcript could not be used. Try again."
    MemoryDictationFailure.RECORDING_FAILED -> if (zh) "录音失败，请重试。" else "Recording failed. Try again."
    MemoryDictationFailure.OFFLINE -> if (zh) "当前离线，请联网后重试。" else "Offline. Reconnect and try again."
    MemoryDictationFailure.RATE_LIMITED -> if (zh) "请求过多，请稍后重试。" else "Too many requests. Wait before trying again."
    MemoryDictationFailure.TRANSCRIPTION_FAILED -> if (zh) "转写失败，请重试。" else "Transcription failed. Try again."
    null -> if (zh) "语音处理未能完成，请重试。" else "Voice processing could not finish. Try again."
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun MemoryDictationInput(
    store: MemoryDictationStore, zh: Boolean, onInsert: () -> Unit,
    purpose: MemoryDictationPurpose = MemoryDictationPurpose.MEMORY_EDITOR,
    insertRejected: Boolean = false,
    insertEnabled: Boolean = true,
) {
    val state by store.state.collectAsState()
    val context = LocalContext.current
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    val recorder = remember(store) { AnnotationAudioRecorder() }
    val audioCoordinator = LocalReaderAudioCoordinator.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var capture by remember(store) { mutableStateOf<AnnotationAudioRecorder.Capture?>(null) }
    var audioLease by remember(store) { mutableStateOf<ReaderAudioCoordinator.Lease?>(null) }
    var permissionWanted by remember(store) { mutableStateOf(false) }
    var audioBusy by remember(store) { mutableStateOf(false) }
    var permissionDenied by remember(store) { mutableStateOf(false) }
    var elapsed by remember(store) { mutableIntStateOf(0) }
    var clock by remember(store) { mutableLongStateOf(System.currentTimeMillis()) }
    fun t(en: String, cn: String) = if (zh) cn else en
    fun start() {
        if (audioCoordinator != null && audioLease == null) {
            val candidate = audioCoordinator.acquire(ReaderAudioKind.RECORDING) { capture?.discard(); capture = null; store.cancel() }
            if (candidate == null) { audioBusy = true; return }
            audioLease = candidate
        }
        if (audioCoordinator != null && audioLease == null) return
        audioBusy = false
        val seconds = store.beginRecording() ?: run { audioCoordinator?.release(audioLease); audioLease = null; return }
        permissionDenied = false
        runCatching { recorder.beginCapture(seconds) }
            .onSuccess { capture = it }
            .onFailure { store.recordingFailed(); audioCoordinator?.release(audioLease); audioLease = null }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (permissionWanted) {
            permissionWanted = false
            if (granted) start() else { permissionDenied = true; audioCoordinator?.release(audioLease); audioLease = null }
        }
    }
    DisposableEffect(store, recorder) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) {
                permissionWanted = false
                capture?.discard(); capture = null
                recorder.stop(); store.cancel()
                audioCoordinator?.release(audioLease); audioLease = null
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            permissionWanted = false
            recorder.stop()
            store.cancel()
            audioCoordinator?.release(audioLease)
            audioLease = null
        }
    }
    LaunchedEffect(store) { store.loadCapabilities() }
    LaunchedEffect(state.retryAtMillis) {
        clock = System.currentTimeMillis()
        while (clock < state.retryAtMillis) { delay(250); clock = System.currentTimeMillis() }
    }
    LaunchedEffect(capture) {
        val current = capture ?: return@LaunchedEffect
        val currentLease = audioLease
        var wav: ByteArray? = null
        try {
            withContext(Dispatchers.IO) { wav = runCatching { current.record() }.getOrNull() }
            // ON_STOP can detach this capture while a non-cooperative native
            // reader is still returning bytes on IO. Only its still-current
            // attempt may hand those bytes to the store.
            if (capture === current && !current.wasDiscarded && current.consumeForUpload()) {
                wav?.let(store::stopRecording) ?: store.recordingFailed()
            }
        } catch (cancelled: CancellationException) {
            current.discard()
            throw cancelled
        } finally {
            wav?.fill(0)
            current.stop()
            audioCoordinator?.release(currentLease)
            if (audioLease?.id == currentLease?.id) audioLease = null
            if (capture === current) capture = null
        }
    }
    LaunchedEffect(state.recording, capture) {
        elapsed = 0
        while (state.recording) {
            elapsed = capture?.recordedMillis ?: 0
            delay(100)
        }
    }
    val title = when (purpose) {
        MemoryDictationPurpose.CHAT_MESSAGE -> t("Voice input", "语音输入")
        MemoryDictationPurpose.MEMOIR_INSTRUCTIONS -> t("Memoir instructions", "口述整理要求")
        MemoryDictationPurpose.MEMORY_EDITOR -> t("Tell this memory", "说说这段回忆")
    }
    val help = if (purpose == MemoryDictationPurpose.CHAT_MESSAGE) t(
        "Record → review the words → add to your message draft → send it yourself. The recording is not kept; conversations and transcription records are kept for 30 days.",
        "录音→核对文字→加入消息草稿→由你发送。录音不会保留；对话和转写记录保留30天。",
    ) else if (purpose == MemoryDictationPurpose.MEMOIR_INSTRUCTIONS) t(
        "Describe how to arrange the memoir. Review the transcript before inserting it. Audio is not saved; transcription records last 30 days.",
        "说说希望怎样整理，核对转写后加入要求。录音不保存，转写记录保留 30 天。",
    ) else t(
        "Record → review the words → add to your memory. Only text is saved with the memory; the recording is not kept. Transcription records are kept for 30 days.",
        "录音 → 检查文字 → 加入回忆。回忆只保存文字，不保留录音；转写记录保留 30 天。",
    )
    val insertLabel = when (purpose) {
        MemoryDictationPurpose.CHAT_MESSAGE -> t("Add to message draft", "加入消息草稿")
        MemoryDictationPurpose.MEMOIR_INSTRUCTIONS -> t("Insert instructions", "插入整理要求")
        MemoryDictationPurpose.MEMORY_EDITOR -> t("Add to memory", "加入回忆")
    }
    val recordLabel = when (purpose) {
        MemoryDictationPurpose.CHAT_MESSAGE -> t("Record a message", "录音说消息")
        MemoryDictationPurpose.MEMOIR_INSTRUCTIONS -> t("Dictate instructions", "开始口述")
        MemoryDictationPurpose.MEMORY_EDITOR -> t("Record a memory", "录音讲回忆")
    }
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = MaterialTheme.shapes.large,
        modifier = Modifier.fillMaxWidth().testTag("memory-dictation")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(help, style = MaterialTheme.typography.bodySmall)
            when {
                state.loading -> {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                    Text(t("Checking voice availability…", "正在检查语音服务…"),
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
                }
                state.recording -> {
                    Text(if (elapsed < 500) t("Preparing microphone…", "正在准备麦克风…")
                        else t("Recording", "正在录音"),
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                            .testTag("memory-dictation-recording"))
                    if (elapsed >= 500) Text(
                        t("${elapsed / 1000} / ${state.capabilities?.maxAudioSeconds} seconds",
                            "${elapsed / 1000} / ${state.capabilities?.maxAudioSeconds} 秒"),
                        modifier = Modifier.testTag("memory-dictation-recording-time"))
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { capture?.stop() }, enabled = elapsed >= 500,
                            modifier = Modifier.testTag("memory-dictation-stop")) {
                            Text(t("Stop and transcribe", "停止并转写"))
                        }
                        TextButton(onClick = { capture?.discard(); capture = null; store.cancel() }) { Text(t("Discard", "放弃录音")) }
                    }
                }
                state.transcribing -> {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                    Text(t("Transcribing on your server…", "正在服务器上转写…"),
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                            .testTag("memory-dictation-transcribing"))
                    TextButton(onClick = store::cancel) { Text(t("Cancel transcription", "取消转写")) }
                }
                state.transcript != null -> {
                    Text(t("Transcript ready. Review the words before adding.", "转写已完成，请先核对文字再加入。"),
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                            .testTag("memory-dictation-transcript-ready"))
                    OutlinedTextField(value = state.transcript.orEmpty(), onValueChange = store::updateTranscript,
                        label = { Text(t("Check the recognized words", "检查识别的文字")) }, minLines = 3, maxLines = 5,
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { focus.clearFocus(); keyboard?.hide() }),
                        modifier = Modifier.fillMaxWidth().testTag("memory-dictation-transcript"))
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = onInsert, enabled = insertEnabled && !state.transcript.isNullOrBlank(), modifier = Modifier.testTag("memory-dictation-insert")) {
                            Text(insertLabel)
                        }
                        TextButton(onClick = store::dismissTranscript) { Text(t("Discard words", "放弃文字")) }
                    }
                    if (purpose == MemoryDictationPurpose.MEMOIR_INSTRUCTIONS && !insertEnabled) Text(
                        t("The instruction editor contains unconfirmed wording. Keep this transcript until that wording is resolved.",
                            "整理要求中还有未确认的文字。请保留这段转写，先处理原有文字。"),
                        modifier = Modifier.testTag("memory-dictation-insert-blocked")
                            .semantics { liveRegion = LiveRegionMode.Polite },
                    )
                    if (insertRejected) Text(
                        t("These instructions exceed the editor limit. The complete transcript is still here; shorten it before inserting.",
                            "整理要求超出编辑框限制。完整转写仍保留在这里，请缩短后再插入。"),
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.testTag("memory-dictation-insert-rejected")
                            .semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
                else -> {
                    val available = state.capabilities?.let { it.enabled && it.transcribe && it.maxAudioSeconds in 1..30 } == true
                    if (available) {
                        Button(onClick = {
                            if (audioCoordinator != null && audioLease == null) {
                                val candidate = audioCoordinator.acquire(ReaderAudioKind.RECORDING) { capture?.discard(); capture = null; store.cancel() }
                                if (candidate == null) { audioBusy = true; return@Button }
                                audioLease = candidate
                            }
                            audioBusy = false
                            if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) start()
                            else { permissionWanted = true; permission.launch(Manifest.permission.RECORD_AUDIO) }
                        }, enabled = !permissionWanted && clock >= state.retryAtMillis, modifier = Modifier.testTag("memory-dictation-record")) {
                            Text(recordLabel)
                        }
                        Text(t("Up to ${state.capabilities?.maxAudioSeconds} seconds each. You can add another recording afterward.",
                            "每段最多 ${state.capabilities?.maxAudioSeconds} 秒，可以分段追加。"), style = MaterialTheme.typography.bodySmall)
                    } else {
                        Text(t("Voice is unavailable. You can still write your memory below.", "语音暂不可用，仍可在下方填写回忆。"),
                            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
                        OutlinedButton(onClick = store::loadCapabilities, enabled = clock >= state.retryAtMillis,
                            modifier = Modifier.testTag("memory-dictation-recheck")) { Text(t("Check again", "重新检查")) }
                    }
                }
            }
            if (permissionDenied) Text(t("Microphone permission was denied. You can write below or enable it in Android settings.",
                "未获得麦克风权限，可继续输入文字，或在系统设置中开启权限。"),
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                    .testTag("memory-dictation-permission-denied"))
            if (audioBusy) Text(t("Finish other reader audio before recording.", "请先结束其他阅读音频，再开始录音。"),
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                    .testTag("memory-dictation-audio-busy"))
            state.failure?.let { Text(memoryDictationFailureMessage(state.failureCode, zh),
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }
                    .testTag("memory-dictation-failure")) }
        }
    }
}
