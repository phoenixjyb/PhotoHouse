package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.platform.LocalContext
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.media3.common.AudioAttributes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import dev.photohouse.connected.core.*

@Composable
internal fun AssistantScreen(
    state: AssistantClientState?, zh: Boolean, onBack: () -> Unit,
    previews: Map<String, ByteArray>,
    onRetryCapabilities: () -> Unit, onSend: (String) -> Boolean,
    onClear: () -> Unit, onOpen: (String, String?) -> Unit, onCheckReceipt: () -> Unit,
    onRecord: () -> Unit, onStopRecording: () -> Unit, onCancelRecording: () -> Unit,
    recording: Boolean, recordError: Boolean, onClearTranscript: () -> Unit,
    onPlaySpeech: () -> Unit, onStopSpeech: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    var draft by remember(state?.generation, state?.library) { mutableStateOf("") }
    LaunchedEffect(state?.transcript) { state?.transcript?.let { draft = it.text } }
    val keyboard = LocalSoftwareKeyboardController.current
    val focusManager = LocalFocusManager.current
    val submit: () -> Unit = {
        val text = draft.trim()
        if (text.isNotEmpty() && state?.pendingTurn == null && state?.busy != true) {
            keyboard?.hide(); focusManager.clearFocus()
            if (onSend(text) && draft.trim() == text) draft = ""
        }
    }
    val exchanges = state?.turns.orEmpty()
    val pending = state?.pendingTurn
    val pendingReceiptStatus = state?.receiptDetail?.status ?: state?.lastRequestReceipt?.status
    val pendingFailed = pendingReceiptStatus in setOf("failed", "interrupted")
    Column(Modifier.fillMaxSize().safeDrawingPadding().padding(horizontal = 20.dp, vertical = 12.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack, modifier = Modifier.testTag("assistant-back")) { Text(t("Back to album", "返回相册")) }
            if (pending == null && exchanges.isNotEmpty()) TextButton(onClick = onClear, modifier = Modifier.testTag("assistant-clear")) { Text(t("Clear", "清空对话")) }
        }
        Text(t("PhotoHouse assistant", "拾光相册助手"), style = MaterialTheme.typography.headlineMedium, fontFamily = FontFamily.Serif)
        Text(t("A calm way to find a moment in this library.", "陪你在这座资料库里，慢慢找回一个瞬间。"),
            style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(t("Ask about photos and videos, then open a result to view it.", "可以询问照片和视频，再打开结果查看。"),
            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 2.dp))
        Text(t("Recognized text, requests and status are kept for 30 days. Recordings are transient.", "识别文本、提交的指令和处理状态保留 30 天；录音仅临时处理。"),
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 2.dp))
        val assistant = state
        assistant?.takeIf { it.pendingTurn == null }?.lastRequestReceipt?.let { receipt ->
            val receiptStatus = assistant.receiptDetail?.status ?: receipt.status ?: receipt.tracking
            val statusLabel = when (receiptStatus) {
                "succeeded" -> t("Server completed", "服务器已完成")
                "received" -> t("Received; processing", "已收到，正在处理")
                "failed" -> t("Server processing failed", "服务器处理失败")
                "interrupted" -> t("Processing interrupted", "处理中断")
                "disabled" -> t("Tracking disabled", "未启用请求跟踪")
                else -> t("Server receipt not confirmed", "尚未确认服务器回执")
            }
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SelectionContainer(Modifier.weight(1f)) {
                    Text(t("Request ${receipt.requestId} · ${statusLabel}", "请求 ${receipt.requestId} · ${statusLabel}"), Modifier.testTag("assistant-receipt"), style = MaterialTheme.typography.labelSmall)
                }
                TextButton(onClick = onCheckReceipt, enabled = !assistant.receiptChecking && receipt.tracking != "disabled", modifier = Modifier.testTag("assistant-check-receipt")) { Text(if (assistant.receiptChecking) t("Checking…", "查询中…") else t("Check", "查询")) }
            }
        }
        if (assistant?.pendingTurn == null && assistant?.receiptCheckFailed == true) Text(t("Receipt check unavailable. The previous status is unchanged.", "暂时无法查询回执，上次确认的状态未改变。"), style = MaterialTheme.typography.bodySmall)
        when {
            assistant == null || assistant.loadingCapabilities -> {
                LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 12.dp).testTag("assistant-capabilities-loading"))
                Text(t("Checking what is available…", "正在查看当前可用功能…"), Modifier.padding(top = 8.dp))
            }
            assistant.failure != null && assistant.capabilities == null -> {
                Card(Modifier.fillMaxWidth().padding(top = 12.dp)) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(t("Assistant is temporarily unavailable. Your library access is unchanged.", "助手暂时不可用，资料库权限状态未改变。"), modifier = Modifier.testTag("assistant-unavailable"))
                    TextButton(onClick = onRetryCapabilities, modifier = Modifier.testTag("assistant-retry-capabilities")) { Text(t("Retry", "重试")) }
                } }
            }
            assistant.capabilities?.let { !it.enabled || !it.text } == true ->
                Text(t("The assistant is not enabled for this library.", "此资料库尚未启用助手。"), Modifier.padding(top = 12.dp).testTag("assistant-disabled"))
            else -> {
                LazyColumn(Modifier.weight(1f).fillMaxWidth().padding(top = 12.dp).testTag("assistant-turns"), verticalArrangement = Arrangement.spacedBy(10.dp),
                    contentPadding = PaddingValues(bottom = 12.dp)) {
                    pending?.let { pendingTurn -> item(key = "assistant-pending") {
                        val statusLabel = when {
                            assistant.busy -> t("Sending this request…", "正在提交这条请求…")
                            pendingReceiptStatus == "received" -> t("The server received this request and may still be processing it.", "服务器已收到请求，可能仍在处理中。")
                            pendingReceiptStatus == "succeeded" -> t("The server completed this request, but its reply and updated context were not recovered.", "服务器已完成请求，但回复和更新后的上下文没有取回。")
                            pendingReceiptStatus == "failed" -> t("The server recorded a failed request; its reply is unavailable.", "服务器记录这条请求失败，回复不可用。")
                            pendingReceiptStatus == "interrupted" -> t("Server processing was interrupted; its reply is unavailable.", "服务器处理中断，回复不可用。")
                            else -> t("The outcome is unknown. The server may already have processed this request.", "结果尚不确定；服务器可能已经处理了这条请求。")
                        }
                        val recoveryActionText = if (pendingFailed)
                            t("Close this conversation to edit the original question, or keep your newer draft. Review it and press Ask to send.",
                                "关闭后可编辑原问题；若已输入新问题，则保留新草稿。检查后点击发送才会提交。")
                        else
                            t("Checking the receipt never resends the request. Starting fresh clears this conversation and keeps a newer unsent draft; the original server request may still finish.",
                                "查询回执不会重新发送请求。重新开始会清除当前对话，保留你新写的草稿；服务器仍可能完成原请求。")
                        Card(Modifier.fillMaxWidth().testTag("assistant-pending-turn")) {
                            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(t("Pending request", "待确认请求"), style = MaterialTheme.typography.labelLarge)
                                Text(statusLabel, style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("assistant-pending-status"))
                                TextButton(onClick = onCheckReceipt, enabled = !assistant.receiptChecking && assistant.lastRequestReceipt?.tracking != "disabled",
                                    modifier = Modifier.testTag("assistant-check-receipt")) {
                                    Text(if (assistant.receiptChecking) t("Checking receipt…", "正在查询回执…") else t("Check receipt", "查询回执"))
                                }
                                TextButton(onClick = {
                                    if (pendingFailed && draft.isBlank()) draft = pendingTurn.text
                                    onClear()
                                }, modifier = Modifier.testTag("assistant-close-pending")) {
                                    Text(if (pendingFailed) t("Close & restore question", "关闭并恢复问题") else t("Acknowledge & start fresh", "确认并重新开始"))
                                }
                                if (assistant.receiptCheckFailed) Text(t("Receipt check unavailable. The previous status is unchanged.", "暂时无法查询回执，上次确认的状态未改变。"),
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error,
                                    modifier = Modifier.testTag("assistant-receipt-check-failed"))
                                Text(t("Submitted question", "已提交的问题"), style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(pendingTurn.text, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("assistant-pending-text"))
                                Text(recoveryActionText,
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.testTag("assistant-pending-explanation"))
                            }
                        }
                    } }
                    if (exchanges.isEmpty()) item {
                        Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(t("Start with a simple request", "从一句简单的话开始"), style = MaterialTheme.typography.titleMedium,
                                    fontFamily = FontFamily.Serif, color = MaterialTheme.colorScheme.onSecondaryContainer)
                                Text(t("Choose a suggestion to edit it before sending.", "选一句示例后，可以先修改，再发送。"),
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSecondaryContainer)
                                listOf(
                                    t("Find videos from last year", "找去年的视频"),
                                    t("Find photos from last September", "找去年九月的照片"),
                                    t("Open the first result", "打开第一个结果"),
                                ).forEachIndexed { index, suggestion ->
                                    OutlinedButton(onClick = { draft = suggestion }, modifier = Modifier.fillMaxWidth().testTag("assistant-suggestion-$index")) {
                                        Text(suggestion, modifier = Modifier.fillMaxWidth())
                                    }
                                }
                            }
                        }
                    }
                    items(exchanges) { exchange ->
                        Card(Modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp)) { Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(t("YOU ASKED", "你的问题"), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(exchange.text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.testTag("assistant-user-turn"))
                            HorizontalDivider()
                            Text(t("PHOTOHOUSE", "拾光相册"), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                            Text(exchange.turn.reply, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.testTag("assistant-reply"))
                            if (exchange.turn.kind == "results" && exchange.turn.total == 0) {
                                Text(t("No matching memories were found in this library.", "在这座资料库中没有找到匹配的回忆。"),
                                    style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.testTag("assistant-empty-results"))
                            }
                            if (exchange.turn.items.isNotEmpty()) {
                                Text(t("${exchange.turn.total} matching memories", "找到 ${exchange.turn.total} 条相关回忆"), style = MaterialTheme.typography.labelMedium)
                                exchange.turn.items.forEach { asset ->
                                    OutlinedCard(Modifier.fillMaxWidth().testTag("assistant-result-${asset.id}")) {
                                            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp),
                                            horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                            Preview(asset, previews[asset.id], Words(zh), modifier = Modifier.width(76.dp).height(56.dp))
                                            Column(Modifier.weight(1f)) {
                                                Text(t("${if (asset.kind == "video") "Video" else "Photo"} · No. ${asset.id}", "${if (asset.kind == "video") "视频" else "照片"} · 编号 ${asset.id}"), style = MaterialTheme.typography.titleSmall)
                                                Text(asset.taken_at ?: asset.date_hint?.value ?: t("Date unknown", "日期未知"), style = MaterialTheme.typography.bodySmall)
                                            }
                                            TextButton(onClick = { onOpen(asset.id, exchange.turn.receipt?.requestId) }, modifier = Modifier.testTag("assistant-open-${asset.id}")) {
                                                Text(t("Open", "打开"))
                                            }
                                        }
                                    }
                                }
                                if (exchange.turn.hasMore) Text(t("More results are available. Refine your request to narrow the list.", "还有更多结果。可以继续描述来缩小范围。"), style = MaterialTheme.typography.bodySmall)
                            }
                        } }
                    }
                    if (assistant.busy) item {
                        Column(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            LinearProgressIndicator(Modifier.fillMaxWidth().testTag("assistant-sending"))
                            Text(t("Looking through this library…", "正在资料库中查找…"), style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    assistant.failure?.let { _ -> item {
                        Text(t("This request could not be completed. Try again when the service is available.", "暂时无法完成这次请求，服务恢复后可以重试。"),
                            color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("assistant-turn-error"))
                    } }
                }
                Column(Modifier.fillMaxWidth().padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    val latest = exchanges.lastOrNull()?.turn
                    if (assistant.capabilities?.speech == true && latest?.kind == "results" && latest.items.isNotEmpty()) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
                            if (assistant.speechBusy) LinearProgressIndicator(Modifier.weight(1f).testTag("assistant-speech-loading"))
                            Button(onClick = onPlaySpeech, enabled = !assistant.speechBusy,
                                modifier = Modifier.testTag("assistant-play-speech")) { Text(t("Play spoken result count", "播放结果数量语音")) }
                        }
                        assistant.speechAudio?.let { AssistantSpeechPlayback(it, zh, onStopSpeech) }
                    }
                    OutlinedTextField(value = draft, onValueChange = { if (it.codePointCount(0, it.length) <= 512) draft = it },
                        modifier = Modifier.fillMaxWidth().testTag("assistant-text"), enabled = !assistant.busy,
                        label = { Text(t("Ask about your photos", "询问相册内容")) },
                        placeholder = { Text(t("For example: find videos from last year", "例如：找去年9月的照片")) },
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = { submit() }), maxLines = 4)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                        val canTranscribe = assistant.capabilities?.let { it.enabled && it.transcribe && it.maxAudioSeconds in 1..30 } == true
                        if (canTranscribe) {
                            if (recording) {
                                Text(t("Listening…", "正在聆听…"), Modifier.align(Alignment.CenterVertically).testTag("assistant-listening"),
                                    style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                                TextButton(onClick = onCancelRecording, modifier = Modifier.testTag("assistant-cancel-recording")) { Text(t("Cancel", "取消")) }
                                Button(onClick = onStopRecording, modifier = Modifier.testTag("assistant-stop-recording")) { Text(t("Stop and review", "停止并查看转写")) }
                            } else {
                                OutlinedButton(onClick = onRecord, enabled = !assistant.busy && assistant.pendingTurn == null && !assistant.transcribing,
                                    modifier = Modifier.testTag("assistant-record")) { Text(t("Record speech", "录音转文字")) }
                            }
                        }
                        Button(onClick = submit,
                            enabled = !assistant.busy && assistant.pendingTurn == null && !assistant.transcribing && draft.isNotBlank(), modifier = Modifier.testTag("assistant-send")) {
                            Text(if (assistant.busy) t("Thinking…", "正在整理…") else t("Ask", "发送"))
                        }
                    }
                    if (assistant.transcribing) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        LinearProgressIndicator(Modifier.fillMaxWidth().testTag("assistant-transcribing"))
                        Text(t("Preparing a transcript for your review…", "正在整理转写内容，稍后请先检查…"), style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    if (recordError) Text(t("Microphone recording could not start.", "无法开始录音。"), color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("assistant-record-error"))
                    assistant.transcript?.takeIf { assistant.pendingTurn == null }?.let { transcript ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(t("Review the transcript before sending (${transcript.language})${transcript.receipt?.let { " · ${it.requestId}" } ?: ""}.", "发送前请检查转写内容（${transcript.language}）${transcript.receipt?.let { " · ${it.requestId}" } ?: ""}。"), Modifier.weight(1f), style = MaterialTheme.typography.labelMedium)
                            TextButton(onClick = onClearTranscript, modifier = Modifier.testTag("assistant-discard-transcript")) { Text(t("Discard", "丢弃")) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
@androidx.annotation.OptIn(UnstableApi::class)
private fun AssistantSpeechPlayback(audio: ProtectedAnnotationAudio, zh: Boolean, onStop: () -> Unit) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val context = LocalContext.current
    val player = remember(audio) { ExoPlayer.Builder(context).build() }
    var playing by remember(audio) { mutableStateOf(false) }
    var failed by remember(audio) { mutableStateOf(false) }
    DisposableEffect(audio, player) {
        var attached = true
        val listener = object : Player.Listener {
            override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) { if (attached) playing = playWhenReady }
            override fun onPlayerError(error: PlaybackException) { if (attached) failed = true }
        }
        val closeListener: () -> Unit = { Handler(Looper.getMainLooper()).post { if (attached) { runCatching { player.stop() }; playing = false } } }
        player.addListener(listener)
        player.setAudioAttributes(AudioAttributes.DEFAULT, true)
        player.setMediaSource(ProgressiveMediaSource.Factory(AnnotationAudioDataSource.Factory(audio))
            .createMediaSource(MediaItem.fromUri(Uri.parse("photohouse-audio://assistant-speech"))))
        player.playWhenReady = true
        player.prepare()
        audio.onClose(closeListener)
        onDispose { attached = false; audio.removeOnClose(closeListener); player.removeListener(listener); player.release() }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.testTag("assistant-speech-playback")) {
        TextButton(onClick = { player.stop(); onStop() }, modifier = Modifier.testTag("assistant-stop-speech")) { Text(t("Stop", "停止")) }
        if (playing) Text(t("Speaking the result count…", "正在播报结果数量…"), style = MaterialTheme.typography.bodySmall)
        if (failed) Text(t("Speech could not play.", "语音无法播放。"), color = MaterialTheme.colorScheme.error)
    }
}
