package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*

/** Metadata presentation only. Opening details never retries a task or resends a file. */
@Composable
internal fun UploadPreparationNotice(state: UploadPreparationState?, zh: Boolean) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val message = when (state?.status) {
        UploadPreparationStatus.LOADING -> t("Checking processing records…", "正在查询处理记录…")
        UploadPreparationStatus.AVAILABLE -> t("Processing records checked. File readiness is verified separately.",
            "已查询处理记录，文件是否可查看仍需单独验证。")
        UploadPreparationStatus.UNSUPPORTED -> t("This server does not provide processing progress. Upload records remain available.",
            "当前服务器暂不提供处理进度，上传记录仍可查看。")
        UploadPreparationStatus.UNAVAILABLE -> t("Processing progress is temporarily unavailable. Refresh to check again; received files do not need to be uploaded again.",
            "处理进度暂不可用，可刷新重查，无需重复上传已收到的文件。")
        null -> t("Processing progress has not been confirmed.", "处理进度尚未确认。")
    }
    Text(message, style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.testTag("upload-preparation-notice"))
}

@Composable
internal fun UploadPreparationDetails(item: UploadHistoryItem, state: UploadPreparationState?, zh: Boolean) {
    fun t(en: String, cn: String) = if (zh) cn else en
    // Keep the receipt binding at the UI boundary as well as in the store.
    val evidence = state?.takeIf { it.status == UploadPreparationStatus.AVAILABLE && item.state == "available" && item.libraryId != null }
        ?.items?.singleOrNull { it.receipt == item }?.processing
    var expanded by remember(item, evidence) { mutableStateOf(false) }
    if (evidence == null) {
        Text(t("Preview and playback readiness not confirmed", "预览与播放准备状态未确认"),
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.testTag("upload-preparation-unknown-${item.assetId}"))
        return
    }
    val stages = evidence.stages.values.filter { it != UploadPreparationStageState.NOT_APPLICABLE }
    val needsAttention = stages.any { it == UploadPreparationStageState.FAILED || it == UploadPreparationStageState.DEAD }
    val summary = when {
        needsAttention -> t("Some processing needs attention", "部分处理需检查")
        UploadPreparationStageState.RUNNING in stages -> t("Processing", "正在处理")
        UploadPreparationStageState.PENDING in stages -> t("Waiting for processing", "等待处理")
        UploadPreparationStageState.AWAITING_REVIEW in stages -> t("Awaiting processing approval", "等待处理放行")
        stages.isNotEmpty() && stages.all { it == UploadPreparationStageState.FINISHED } -> t("Processing tasks ended", "处理任务已结束")
        else -> t("Processing state not confirmed", "处理状态待确认")
    }
    Surface(color = MaterialTheme.colorScheme.surfaceContainerHigh, shape = RoundedCornerShape(12.dp)) {
        Column(Modifier.fillMaxWidth().padding(12.dp).testTag("upload-preparation-${item.assetId}"),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(summary, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f),
                    color = if (needsAttention) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
                TextButton(onClick = { expanded = !expanded }, modifier = Modifier.testTag("upload-preparation-toggle-${item.assetId}").semantics {
                    stateDescription = t(if (expanded) "Expanded" else "Collapsed", if (expanded) "已展开" else "已收起")
                }) { Text(if (expanded) t("Hide", "收起") else t("Processing details", "处理详情")) }
            }
            Text(t("Preview: not verified", "预览：尚未验证"), style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("upload-preview-unverified-${item.assetId}"))
            if (item.kind == "video") Text(t("Playback: not verified", "播放：尚未验证"),
                style = MaterialTheme.typography.bodySmall)
            if (needsAttention) Text(t("The server already has this file. Check again later or contact the library owner; do not upload it again.",
                "服务器已收到此文件，可稍后重查或联系相册主人，无需重复上传。"),
                style = MaterialTheme.typography.bodySmall)
            if (expanded) {
                HorizontalDivider()
                UploadPreparationStage.entries.forEach { stage ->
                    val value = evidence.stages[stage] ?: UploadPreparationStageState.UNKNOWN
                    Text("${preparationStageLabel(stage, zh)} · ${preparationStageStateLabel(value, zh)}",
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.testTag("upload-preparation-stage-${item.assetId}-${stage.name}"))
                }
                HorizontalDivider()
                fun record(label: String, present: Boolean) = "$label · ${if (present) t("Record present", "已有记录") else t("No record yet", "尚无记录")}"
                if (item.kind == "image") Text(record(t("Image search information", "图片检索信息"), evidence.records.imageVector), style = MaterialTheme.typography.bodySmall)
                Text(record(t("Description", "影像描述"), evidence.records.caption), style = MaterialTheme.typography.bodySmall)
                if (item.kind == "image") Text(record(t("Face detection information", "人脸检测信息"), evidence.records.faceDetections), style = MaterialTheme.typography.bodySmall)
                Text(t("Task results and record presence do not confirm that previews or playback can be opened.",
                    "任务状态和记录存在，不代表预览或播放已可打开。"), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

private fun preparationStageLabel(stage: UploadPreparationStage, zh: Boolean): String = when (stage) {
    UploadPreparationStage.PREVIEW -> if (zh) "预览任务" else "Preview task"
    UploadPreparationStage.INDEX -> if (zh) "检索任务" else "Search task"
    UploadPreparationStage.FACES -> if (zh) "人脸检测任务" else "Face detection task"
    UploadPreparationStage.CAPTION -> if (zh) "影像描述任务" else "Description task"
    UploadPreparationStage.VIDEO_PROBE -> if (zh) "视频检测任务" else "Video inspection task"
}

private fun preparationStageStateLabel(state: UploadPreparationStageState, zh: Boolean): String = when (state) {
    UploadPreparationStageState.AWAITING_REVIEW -> if (zh) "等待放行" else "Awaiting approval"
    UploadPreparationStageState.PENDING -> if (zh) "等待处理" else "Pending"
    UploadPreparationStageState.RUNNING -> if (zh) "处理中" else "Running"
    UploadPreparationStageState.FINISHED -> if (zh) "已结束" else "Ended"
    UploadPreparationStageState.FAILED -> if (zh) "处理失败" else "Failed"
    UploadPreparationStageState.DEAD -> if (zh) "未完成，需检查" else "Incomplete; needs attention"
    UploadPreparationStageState.UNKNOWN -> if (zh) "待确认" else "Not confirmed"
    UploadPreparationStageState.NOT_APPLICABLE -> if (zh) "不适用" else "Not applicable"
}
