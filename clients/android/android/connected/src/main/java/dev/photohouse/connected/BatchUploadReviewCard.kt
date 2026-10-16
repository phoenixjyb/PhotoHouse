package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.BatchUploadEnqueueIssue

@Composable
internal fun BatchUploadReviewCard(
    selectedCount: Int,
    selectedBytes: Long,
    skippedCount: Int,
    availableSlots: Int,
    destinationLabel: String?,
    issue: BatchUploadEnqueueIssue?,
    needsNetworkConfirmation: Boolean,
    zh: Boolean,
    onStart: () -> Unit,
    onDiscard: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val explanation = when (issue) {
        BatchUploadEnqueueIssue.EMPTY_SELECTION -> t(
            "No uploadable files were selected. Choose supported files whose size can be read.",
            "没有可上传的文件。请选择支持的格式，并确认手机能读取文件大小。")
        BatchUploadEnqueueIssue.QUEUE_LIMIT -> t(
            "The queue can hold 100 unfinished files. There is room for $availableSlots more; finish or cancel queued uploads, or choose fewer files.",
            "队列最多保留 100 个未完成文件，目前还能加入 $availableSlots 个。请先完成或取消部分上传，或减少本次选择。")
        BatchUploadEnqueueIssue.INVALID_SOURCE -> t(
            "Some files have an unsupported size or name. Choose those files again.",
            "部分文件的大小或名称不可用，请重新选择。")
        BatchUploadEnqueueIssue.BATCH_TOO_LARGE -> t(
            "This selection exceeds 64 GiB. Split it into smaller batches.",
            "本次选择超过 64 GiB，请分成较小的批次上传。")
        BatchUploadEnqueueIssue.DESTINATION_UNAVAILABLE -> t(
            "The destination library is no longer available. Choose it again from an available library.",
            "目标资料库已不可用，请从可用资料库重新选择文件。")
        BatchUploadEnqueueIssue.ACCOUNT_UNAVAILABLE -> t(
            "The upload session is no longer available. Sign in again before choosing files.",
            "上传会话已不可用，请重新登录后再选择文件。")
        null -> null
    }
    Card(Modifier.fillMaxWidth().testTag("batch-review")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(t("Review uploads", "检查上传"), style = MaterialTheme.typography.titleMedium)
            Text(t("$selectedCount files · $selectedBytes bytes", "$selectedCount 个文件 · $selectedBytes 字节"))
            Text(destinationLabel?.let { t("Destination: $it", "目标资料库：$it") }
                ?: t("Choose a destination library before starting.", "开始前请选择目标资料库。"),
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("batch-destination-summary"))
            Text(t("JPEG/PNG up to 256 MiB; MP4/MOV up to 16 GiB per file.",
                "支持 JPEG/PNG 照片（每个最多 256 MiB）及 MP4/MOV 视频（每个最多 16 GiB）。"),
                style = MaterialTheme.typography.bodySmall)
            if (skippedCount > 0) Text(t("$skippedCount unsupported or unknown-size files were skipped.",
                "已跳过 $skippedCount 个不支持或大小未知的文件。"), color = MaterialTheme.colorScheme.error)
            if (explanation != null) Text(explanation, color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag("batch-review-problem"))
            if (needsNetworkConfirmation) Text(t("This connection may incur data charges. Continue only after review.",
                "当前网络可能产生流量费用，请确认后继续。"), modifier = Modifier.testTag("batch-network-review"))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onStart, enabled = selectedCount > 0 && issue == null,
                    modifier = Modifier.testTag("batch-start")) {
                    Text(if (needsNetworkConfirmation) t("Continue", "继续") else t("Start", "开始"))
                }
                OutlinedButton(onClick = onDiscard, modifier = Modifier.testTag("batch-discard")) {
                    Text(t("Discard", "放弃"))
                }
            }
        }
    }
}
