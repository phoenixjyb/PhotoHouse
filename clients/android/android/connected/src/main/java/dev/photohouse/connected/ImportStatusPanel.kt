package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*
import java.text.DateFormat
import java.util.Date
import java.util.Locale

/** One presentation of the existing account-owned queue and history; never starts work on composition. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun ImportStatusPanel(
    queueItems: List<UploadQueueItem>, history: UploadHistoryState?, availableLibraries: Set<String>,
    zh: Boolean, actionsEnabled: Boolean, queueExpanded: Boolean, historyExpanded: Boolean,
    onToggleQueue: () -> Unit, onToggleHistory: () -> Unit, onCheckServer: () -> Unit,
    onHistoryPage: (Int) -> Unit, onCloseHistory: () -> Unit,
    onPause: () -> Unit, onResume: (String) -> Unit, onRetry: (String) -> Unit, onCancel: (String) -> Unit,
    onDescribeBatch: (String, String, String) -> Unit, onDescribeItem: (String, String, String) -> Unit,
    onOpenHistory: (UploadHistoryItem) -> Unit, onDescribeHistory: (UploadHistoryItem) -> Unit,
    workspaceExpanded: Boolean = true, onToggleWorkspace: () -> Unit = {},
    activity: UploadQueueActivity? = null, onRetryBatch: ((String) -> Unit)? = null,
) {
    if (queueItems.isEmpty() && history == null) return
    fun t(en: String, cn: String) = if (zh) cn else en
    val summary = uploadTransferSummary(queueItems)
    val usableHistory = history != null && !history.busy && !history.unavailable
    Card(Modifier.fillMaxWidth().testTag("import-status")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(t("Import progress", "导入进度"), style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                TextButton(onClick = onToggleWorkspace, modifier = Modifier.testTag("import-workspace-toggle").semantics {
                    stateDescription = t(if (workspaceExpanded) "Expanded" else "Collapsed", if (workspaceExpanded) "已展开" else "已收起")
                }) { Text(if (workspaceExpanded) t("Hide", "收起") else t("Details", "详情")) }
            }
            if (activity != null) {
                Text(uploadQueueActivityMessage(activity, zh), style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.testTag("import-active-stage").semantics {
                        liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite
                    })
                OutlinedButton(onClick = onPause, enabled = actionsEnabled,
                    modifier = Modifier.testTag("import-pause-run")) { Text(t("Pause uploads", "暂停上传")) }
            }
            if (!workspaceExpanded) {
                Text(if (queueItems.isNotEmpty()) t("${summary.total} items · ${summary.received} received · ${summary.failed} interrupted",
                    "${summary.total} 项 · 已上传 ${summary.received} · 中断 ${summary.failed}")
                    else t("Server records", "服务器记录"), style = MaterialTheme.typography.bodySmall)
                return@Column
            }
            Text(t("Uploading, joining a library and preparing previews are separate steps.",
                "上传、加入资料库与准备预览，是不同的步骤。"), style = MaterialTheme.typography.bodyMedium)
            Text(t("Library access does not confirm that photo previews or video playback are ready.",
                "已加入资料库不代表照片预览或视频播放已准备好。"),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testTag("import-readiness-explanation"))
            OutlinedButton(onClick = onCheckServer, enabled = actionsEnabled && history?.busy != true,
                modifier = Modifier.testTag("import-check-server")) {
                Text(t("Check server status", "检查服务器状态"))
            }
            if (queueItems.isNotEmpty()) {
                HorizontalDivider()
                Column(Modifier.fillMaxWidth().testTag("batch-queue"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(t("From this phone", "本机上传"), style = MaterialTheme.typography.titleMedium)
                    Text(t("${summary.total} ${if (summary.total == 1) "item" else "items"} · ${summary.uploading} uploading · ${summary.waiting} waiting · ${summary.received} received · ${summary.failed} interrupted",
                        "${summary.total} 项 · 上传中 ${summary.uploading} · 等待 ${summary.waiting} · 已上传 ${summary.received} · 中断 ${summary.failed}"),
                        style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("batch-queue-summary"))
                    if (summary.cancelled > 0) Text(t("${summary.cancelled} cancelled", "已取消 ${summary.cancelled} 项"), style = MaterialTheme.typography.bodySmall)
                    if (summary.totalBytes > 0) {
                        LinearProgressIndicator(progress = { (summary.transferredBytes.toFloat() / summary.totalBytes).coerceIn(0f, 1f) },
                            modifier = Modifier.fillMaxWidth().testTag("batch-queue-progress"))
                        Text("${importBytes(summary.transferredBytes, zh)} / ${importBytes(summary.totalBytes, zh)}",
                            style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("import-byte-progress"))
                        if (summary.transferredBytes == summary.totalBytes && summary.received + summary.cancelled < summary.total) {
                            Text(t("All bytes transferred does not yet confirm receipt of every file. Check the received and interrupted counts.",
                                "字节已传完不代表每个文件都已确认接收，请查看已上传与中断项数。"),
                                style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("import-confirmation-pending"))
                        }
                    }
                    Text(t("Received means the server has the file; approval and media preparation may still be pending.",
                        "已上传表示服务器已收到文件；审核和影像准备可能尚未完成。"), style = MaterialTheme.typography.bodySmall)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = onToggleQueue, modifier = Modifier.testTag("batch-queue-toggle").semantics {
                            stateDescription = t(if (queueExpanded) "Expanded" else "Collapsed", if (queueExpanded) "已展开" else "已收起")
                        }) { Text(if (queueExpanded) t("Hide", "收起") else t("Show", "展开")) }
                        if (!queueExpanded && summary.failed > 0) OutlinedButton(onClick = onToggleQueue,
                            modifier = Modifier.testTag("batch-review-failures")) { Text(t("Review interrupted uploads", "查看中断项")) }
                    }
                    if (queueExpanded) queueItems.groupBy { it.record.batch }.entries.forEachIndexed { index, (batch, items) ->
                        key(batch) {
                            var expanded by remember { mutableStateOf(items.size <= 3) }
                            val group = uploadTransferSummary(items)
                            Surface(color = MaterialTheme.colorScheme.surfaceContainerHigh, shape = RoundedCornerShape(12.dp)) {
                                Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(t("Batch ${index + 1} · ${items.size} ${if (items.size == 1) "item" else "items"}", "第 ${index + 1} 批 · ${items.size} 项"), style = MaterialTheme.typography.titleSmall)
                                    Text(t("${group.received} received · ${group.waiting} waiting · ${group.failed} interrupted",
                                        "已上传 ${group.received} · 等待 ${group.waiting} · 中断 ${group.failed}"), style = MaterialTheme.typography.bodySmall)
                                    if (group.failed > 0 && onRetryBatch != null) {
                                        OutlinedButton(onClick = { onRetryBatch(batch) }, enabled = actionsEnabled && activity == null,
                                            modifier = Modifier.testTag("import-retry-batch-$batch")) {
                                            Text(t("Retry interrupted files in this batch", "重试本批中断项"))
                                        }
                                    }
                                    TextButton(onClick = { expanded = !expanded }, modifier = Modifier.testTag("import-batch-toggle-$batch").semantics {
                                        stateDescription = t(if (expanded) "Expanded" else "Collapsed", if (expanded) "已展开" else "已收起")
                                    }) { Text(if (expanded) t("Hide files", "收起文件") else t("Show files", "展开文件")) }
                                    if (expanded) {
                                        items.filter { it.record.status == "complete" && it.record.destinationLibraryId in availableLibraries }
                                            .groupBy { it.record.destinationLibraryId!! }.forEach { (destination, completed) ->
                                                OutlinedButton(onClick = { onDescribeBatch(destination, batch, completed.firstNotNullOfOrNull { it.record.assetId }.orEmpty()) },
                                                    enabled = actionsEnabled, modifier = Modifier.testTag("batch-describe-$batch")) {
                                                    Text(t("Describe this batch", "描述这批上传内容"))
                                                }
                                            }
                                        items.forEach { item ->
                                            val record = item.record
                                            val received = receivedUploadStatus(record, history?.items.orEmpty(), usableHistory, availableLibraries)
                                            val status = when (record.status) {
                                                "needs_hash" -> t("Waiting for checksum", "等待校验")
                                                "queued" -> t("Waiting to upload", "等待上传")
                                                "uploading" -> t("Uploading", "上传中")
                                                "paused" -> t("Paused", "已暂停")
                                                "failed" -> t("Upload interrupted", "上传中断")
                                                "cancelling" -> t("Cancelling", "正在取消")
                                                "cancelled" -> t("Cancelled", "已取消")
                                                "complete" -> importStatusLabel(received ?: UploadImportStatus.RECEIVED, zh)
                                                else -> t("Status unknown", "状态未知")
                                            }
                                            Text(record.filename, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                            Text(status, style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("batch-status-${record.localId}"))
                                            if (activity?.localId == record.localId) Text(uploadQueueActivityMessage(activity, zh),
                                                style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("batch-stage-${record.localId}"))
                                            if (record.status == "failed") Text(uploadFailureMessage(record.error, zh),
                                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error,
                                                modifier = Modifier.testTag("batch-error-${record.localId}"))
                                            if (record.status == "complete") Text(t("Preview and playback readiness not confirmed", "预览与播放准备状态未确认"),
                                                style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("import-preparation-${record.localId}"))
                                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                                val destination = record.destinationLibraryId
                                                val asset = record.assetId
                                                if (record.status == "complete" && destination != null && destination in availableLibraries && asset != null)
                                                    OutlinedButton(onClick = { onDescribeItem(destination, record.batch, asset) }, enabled = actionsEnabled,
                                                        modifier = Modifier.testTag("batch-describe-item-${record.localId}")) { Text(t("Describe photo", "描述照片")) }
                                                if (record.status == "uploading") OutlinedButton(onClick = onPause, enabled = actionsEnabled, modifier = Modifier.testTag("batch-pause")) { Text(t("Pause", "暂停")) }
                                                if (record.status in setOf("paused", "queued", "needs_hash")) OutlinedButton(onClick = { onResume(record.localId) }, enabled = actionsEnabled && activity == null, modifier = Modifier.testTag("batch-resume")) { Text(t("Resume batch", "继续本批")) }
                                                if (record.status == "failed") OutlinedButton(onClick = { onRetry(record.localId) }, enabled = actionsEnabled && activity == null, modifier = Modifier.testTag("batch-retry")) { Text(t("Retry and continue batch", "重试并继续本批")) }
                                                if (record.status !in setOf("complete", "cancelled")) OutlinedButton(onClick = { onCancel(record.localId) }, enabled = actionsEnabled, modifier = Modifier.testTag("batch-cancel")) { Text(t("Cancel", "取消")) }
                                            }
                                            HorizontalDivider()
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            history?.let { current ->
                HorizontalDivider()
                Column(Modifier.fillMaxWidth().testTag("upload-history"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(t("Server records", "服务器记录"), style = MaterialTheme.typography.titleMedium)
                    val message = when {
                        current.busy -> t("Loading upload history", "正在加载上传记录")
                        current.unavailable -> t("History unavailable", "记录暂不可用")
                        else -> t("${current.total} uploads · page ${current.page}", "共 ${current.total} 条 · 第 ${current.page} 页")
                    }
                    Text(message, style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("upload-history-summary"))
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = onToggleHistory, modifier = Modifier.testTag("upload-history-toggle").semantics {
                            stateDescription = t(if (historyExpanded) "Expanded" else "Collapsed", if (historyExpanded) "已展开" else "已收起")
                        }) { Text(if (historyExpanded) t("Hide", "收起") else t("Show", "展开")) }
                        TextButton(onClick = onCloseHistory) { Text(t("Close records", "关闭记录")) }
                    }
                    if (current.busy) LinearProgressIndicator(Modifier.fillMaxWidth().testTag("upload-history-progress"))
                    if (current.unavailable) {
                        Text(t("Server status cannot be confirmed. Received files are not automatically resent.",
                            "暂时无法确认服务器状态，不会自动重传已收到的文件。"), color = MaterialTheme.colorScheme.error,
                            modifier = Modifier.testTag("import-server-unavailable"))
                        OutlinedButton(onClick = { onHistoryPage(current.page) }, enabled = actionsEnabled && !current.busy,
                            modifier = Modifier.testTag("upload-history-refresh-collapsed")) { Text(t("Retry", "重试")) }
                    }
                    if (historyExpanded && usableHistory) {
                        if (current.items.isEmpty()) Text(t("No uploads yet.", "还没有上传记录。"))
                        current.items.forEach { item ->
                            val status = uploadHistoryStatus(item, availableLibraries)
                            Text("#${item.assetId} · ${importStatusLabel(status, zh)}", style = MaterialTheme.typography.titleSmall,
                                modifier = Modifier.testTag("import-history-${item.assetId}"))
                            val locale = if (zh) Locale.SIMPLIFIED_CHINESE else Locale.ENGLISH
                            val date = DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT, locale).format(Date(item.createdAt * 1000))
                            Text("$date · ${importBytes(item.bytes, zh)}", style = MaterialTheme.typography.bodySmall)
                            if (status == UploadImportStatus.IN_LIBRARY) {
                                Text(t("Preview and playback readiness not confirmed", "预览与播放准备状态未确认"),
                                    style = MaterialTheme.typography.bodySmall)
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    TextButton(onClick = { onOpenHistory(item) }, enabled = actionsEnabled) { Text(t("Open", "打开")) }
                                    TextButton(onClick = { onDescribeHistory(item) }, enabled = actionsEnabled,
                                        modifier = Modifier.testTag("upload-history-descriptions-${item.assetId}")) { Text(t("Descriptions", "描述")) }
                                }
                            }
                            HorizontalDivider()
                        }
                        if (current.total > 0) Text(t("Page ${current.page} of ${(current.total + 9L) / 10}", "第 ${current.page} / ${(current.total + 9L) / 10} 页"), style = MaterialTheme.typography.bodySmall)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { onHistoryPage(current.page) }, enabled = actionsEnabled, modifier = Modifier.testTag("upload-history-refresh")) { Text(t("Refresh", "刷新")) }
                            OutlinedButton(onClick = { onHistoryPage(current.page - 1) }, enabled = actionsEnabled && current.page > 1, modifier = Modifier.testTag("upload-history-previous")) { Text(t("Previous", "上一页")) }
                            OutlinedButton(onClick = { onHistoryPage(current.page + 1) }, enabled = actionsEnabled && current.page * 10L < current.total, modifier = Modifier.testTag("upload-history-next")) { Text(t("Next", "下一页")) }
                        }
                    }
                }
            }
        }
    }
}

private fun importStatusLabel(status: UploadImportStatus, zh: Boolean): String = when (status) {
    UploadImportStatus.RECEIVED -> if (zh) "已上传，审核状态待确认" else "Received; approval not confirmed"
    UploadImportStatus.AWAITING_REVIEW -> if (zh) "等待主人审核" else "Awaiting owner review"
    UploadImportStatus.IN_LIBRARY -> if (zh) "已加入资料库" else "Added to library"
    UploadImportStatus.UNAVAILABLE -> if (zh) "当前不可用" else "Currently unavailable"
}

private fun importBytes(bytes: Long, zh: Boolean): String {
    val value = bytes.coerceAtLeast(0)
    val locale = if (zh) Locale.SIMPLIFIED_CHINESE else Locale.ENGLISH
    val (amount, unit) = when {
        value >= 1024L * 1024 * 1024 -> value.toDouble() / (1024L * 1024 * 1024) to "GiB"
        value >= 1024L * 1024 -> value.toDouble() / (1024L * 1024) to "MiB"
        value >= 1024L -> value.toDouble() / 1024 to "KiB"
        else -> value.toDouble() to if (zh) "字节" else "bytes"
    }
    return String.format(locale, "%.1f %s", amount, unit)
}
