package dev.photohouse.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.UploadAnnotationReadState
import dev.photohouse.connected.core.UploadAnnotationWriteState
import dev.photohouse.connected.core.UploadAudioAnnotationWriteState
import dev.photohouse.connected.core.FailureKind
import dev.photohouse.connected.core.UploadAnnotationAudioState

internal data class UploadAnnotationTarget(
    val library: String, val batch: String, val assetId: String,
    val readAssetId: String = assetId,
)

@Composable
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
internal fun UploadAnnotationComposer(
    target: UploadAnnotationTarget, zh: Boolean, read: UploadAnnotationReadState?, write: UploadAnnotationWriteState?,
    audioWrite: UploadAudioAnnotationWriteState?, audioSelectionError: Boolean,
    recording: Boolean = false, recordingError: Boolean = false, microphonePermissionDenied: Boolean = false,
    audioPlayback: UploadAnnotationAudioState? = null,
    onDismiss: () -> Unit, onSave: (String, String, String) -> Unit, onRetry: () -> Unit,
    onPickAudio: (String, String) -> Unit, onRetryAudio: () -> Unit,
    onRecordAudio: (String, String) -> Unit = { _, _ -> }, onStopRecording: () -> Unit = {}, onDiscardRecording: () -> Unit = {},
    onPlayAudio: (dev.photohouse.connected.core.UploadAnnotation) -> Unit = {},
    onRetryAudioPlayback: (dev.photohouse.connected.core.UploadAnnotation) -> Unit = {},
    onRefresh: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    var text by remember(target) { mutableStateOf("") }
    var language by remember(target) { mutableStateOf("und") }
    var consent by remember(target) { mutableStateOf("no") }
    val writeMatches = write?.takeIf { it.library == target.library && it.request.batch == target.batch && it.request.assetId == target.assetId }
    val audioMatches = audioWrite?.takeIf { it.library == target.library && it.request.batch == target.batch && it.request.assetId == target.assetId }
    val readMatches = read?.takeIf { it.library == target.library && it.assetId == target.readAssetId }
    val bytes = text.toByteArray(Charsets.UTF_8).size
    AlertDialog(
        modifier = Modifier.testTag("upload-annotation-dialog"),
        onDismissRequest = onDismiss,
        title = { Text(if (target.assetId.isEmpty()) t("Describe this upload batch", "描述这批上传内容") else t("Describe this photo", "描述这张照片")) },
        text = {
            Column(Modifier.fillMaxWidth().heightIn(max = 560.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(t("Original text is retained. Local transcription or wording polish follows your consent and library policy.", "原始文字会保留。本地转写或润色遵循你的同意和资料库设置。"), style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(text, { text = it }, Modifier.fillMaxWidth().testTag("upload-annotation-text"),
                    label = { Text(t("Description", "描述")) }, minLines = 3, maxLines = 7)
                Text(t("$bytes / 16,384 UTF-8 bytes", "$bytes / 16,384 个 UTF-8 字节"), style = MaterialTheme.typography.bodySmall,
                    color = if (bytes > 16 * 1024) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
                Text(t("Language", "语言"), style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("en" to "English", "zh" to "中文", "mixed" to t("Mixed", "混合"), "und" to t("Unknown", "未知")).forEach { (code, label) ->
                        FilterChip(language == code, { language = code }, label = { Text(label) })
                    }
                }
                Text(t("Allow local transcription and wording polish?", "允许本地转写和文字润色吗？"), style = MaterialTheme.typography.labelLarge)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(consent == "yes", { consent = "yes" }, label = { Text(t("Yes", "允许")) })
                    FilterChip(consent == "no", { consent = "no" }, label = { Text(t("No", "不允许")) })
                }
                Text(t("WAV recording: mono 16-bit PCM, 16 or 48 kHz, 0.5–60 seconds, up to 2 MiB. The original is retained.",
                    "WAV 录音：单声道 16 位 PCM，16 或 48 kHz，0.5–60 秒，最大 2 MiB。原始录音会保留。"),
                    style = MaterialTheme.typography.bodySmall)
                OutlinedButton(onClick = { onPickAudio(language, consent) },
                    enabled = target.batch.matches(Regex("[0-9a-f]{32}")) && audioMatches?.busy != true && audioMatches?.result == null,
                    modifier = Modifier.testTag("upload-annotation-pick-audio")) {
                    Text(t("Choose and save WAV recording", "选择并保存 WAV 录音"))
                }
                if (!recording) OutlinedButton(onClick = { onRecordAudio(language, consent) },
                    enabled = target.batch.matches(Regex("[0-9a-f]{32}")) && audioMatches?.busy != true && audioMatches?.result == null,
                    modifier = Modifier.testTag("upload-annotation-record-audio")) {
                    Text(t("Record with microphone", "使用麦克风录音"))
                } else Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onStopRecording, modifier = Modifier.testTag("upload-annotation-stop-recording")) {
                        Text(t("Stop and save", "停止并保存"))
                    }
                    TextButton(onClick = onDiscardRecording, modifier = Modifier.testTag("upload-annotation-discard-recording")) {
                        Text(t("Discard", "丢弃"))
                    }
                }
                if (recording) Text(t("Recording… maximum 60 seconds. Stop to upload, or discard.", "正在录音…最长 60 秒。停止后上传，或丢弃。"))
                if (audioSelectionError || audioMatches?.failure?.kind == FailureKind.INVALID_INPUT)
                    Text(t("Choose a supported WAV recording up to 2 MiB.", "请选择不超过 2 MiB 的受支持 WAV 录音。"),
                        color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("upload-annotation-audio-error"))
                if (recordingError) Text(t("Recording was too short or the microphone was unavailable. Nothing was uploaded.", "录音过短或麦克风不可用，未上传任何内容。"),
                    color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("upload-annotation-recording-error"))
                if (microphonePermissionDenied) Text(t("Microphone access was not granted. You can still choose a WAV file or write text.", "未获麦克风权限。你仍可选择 WAV 文件或填写文字。"),
                    color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("upload-annotation-microphone-denied"))
                if (audioMatches?.busy == true) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator(); Text(t("Saving recording…", "正在保存录音…"))
                }
                if (audioMatches?.failure?.kind != null && audioMatches.failure?.kind != FailureKind.INVALID_INPUT) {
                    Text(t("Recording save could not be confirmed. Retry keeps the same mutation ID.",
                        "暂时无法确认录音是否保存。重试会沿用同一 mutation ID。"),
                        color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("upload-annotation-audio-error"))
                    OutlinedButton(onClick = onRetryAudio, modifier = Modifier.testTag("upload-annotation-audio-retry")) {
                        Text(t("Retry recording", "重试保存录音"))
                    }
                }
                if (audioMatches?.result != null)
                    Text(t("Recording saved. Its original remains available in this library.", "录音已保存，原始录音会保留在此资料库。"),
                        modifier = Modifier.testTag("upload-annotation-audio-saved"))
                if (writeMatches?.busy == true) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator()
                    Text(t("Saving description…", "正在保存描述…"))
                }
                writeMatches?.failure?.let {
                    Text(t("Save could not be confirmed. Retry uses the same mutation ID.", "无法确认是否保存成功。重试会沿用同一 mutation ID。"),
                        color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("upload-annotation-error"))
                    OutlinedButton(onClick = onRetry, modifier = Modifier.testTag("upload-annotation-retry")) { Text(t("Retry", "重试")) }
                }
                if (readMatches?.busy == true) CircularProgressIndicator(Modifier.testTag("upload-annotation-loading"))
                readMatches?.failure?.let {
                    Text(t("Saved descriptions are unavailable right now.", "暂时无法读取已保存的描述。"), color = MaterialTheme.colorScheme.error)
                    OutlinedButton(onClick = onRefresh, modifier = Modifier.testTag("upload-annotation-refresh")) { Text(t("Refresh", "刷新")) }
                }
                val annotations = (readMatches?.result?.items ?: listOfNotNull(writeMatches?.result, audioMatches?.result))
                    .filter { target.assetId.isNotEmpty() || it.scope == "folder" }
                if (readMatches?.result != null || writeMatches?.result != null || audioMatches?.result != null) {
                    Text(t("Original text and processing", "原始文字和处理状态"), style = MaterialTheme.typography.titleSmall)
                    if (annotations.isEmpty()) Text(t("No descriptions yet.", "还没有描述。"), style = MaterialTheme.typography.bodySmall)
                    annotations.forEach { item ->
                        Column(Modifier.fillMaxWidth().padding(start = 4.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            if (target.assetId.isNotEmpty() && item.scope == "folder")
                                Text(t("For the whole batch", "适用于整批内容"), style = MaterialTheme.typography.labelSmall)
                            Text(item.originalText ?: t("Original audio recording", "原始录音"),
                                modifier = Modifier.testTag("upload-annotation-original"))
                            val status = when (item.derivation.state) {
                                "held" -> t("Processing is on hold", "处理已暂缓")
                                "pending", "queued", "waiting" -> t("Waiting for processing", "等待处理")
                                "running" -> t("Processing locally", "正在本地处理")
                                "complete", "completed", "done" -> t("Processing complete", "处理完成")
                                "failed", "error" -> t("Processing failed", "处理失败")
                                "dead" -> t("Processing stopped after access changed", "访问权限变更后已停止处理")
                                else -> item.derivation.state
                            }
                            Text(t("Derivation: $status", "派生状态：$status"), style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.testTag("upload-annotation-derivation"))
                            item.derivation.polishedText?.takeIf { it.isNotBlank() }?.let { Text(t("Polished: $it", "润色后：$it"), style = MaterialTheme.typography.bodySmall) }
                            item.derivation.transcript?.takeIf { it.isNotBlank() }?.let { Text(t("Transcript: $it", "转写：$it"), style = MaterialTheme.typography.bodySmall) }
                            if (item.kind == "audio") {
                                val playback = audioPlayback?.takeIf { it.library == target.library && it.annotationId == item.id }
                                when {
                                    playback?.busy == true -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        CircularProgressIndicator(); Text(t("Loading original audio…", "正在加载原始录音…"))
                                    }
                                    playback?.audio != null -> AnnotationAudioPlayback(requireNotNull(playback.audio), zh)
                                    playback?.failure != null -> {
                                        Text(t("Original audio is unavailable.", "原始录音暂不可用。"), color = MaterialTheme.colorScheme.error)
                                        OutlinedButton(onClick = { onRetryAudioPlayback(item) }, modifier = Modifier.testTag("upload-annotation-audio-retry-playback")) {
                                            Text(t("Retry audio", "重试加载录音"))
                                        }
                                    }
                                    else -> OutlinedButton(onClick = { onPlayAudio(item) }, modifier = Modifier.testTag("upload-annotation-audio-load")) {
                                        Text(t("Play original audio", "播放原始录音"))
                                    }
                                }
                            }
                        }
                    }
                    if (target.readAssetId.isNotEmpty()) OutlinedButton(onClick = onRefresh, modifier = Modifier.testTag("upload-annotation-refresh")) { Text(t("Refresh", "刷新")) }
                }
            }
        },
        confirmButton = {
            Button(onClick = { onSave(text, language, consent) }, enabled = target.batch.matches(Regex("[0-9a-f]{32}") ) && bytes in 1..16 * 1024 && writeMatches?.busy != true && writeMatches?.result == null,
                modifier = Modifier.testTag("upload-annotation-save")) { Text(t("Save", "保存")) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(t("Close", "关闭")) } },
    )
}
