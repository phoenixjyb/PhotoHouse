package dev.photohouse.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.setValue
import dev.photohouse.connected.core.Message
import kotlinx.coroutines.delay
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.UploadState
import dev.photohouse.connected.core.UploadStore

/** The panel owns presentation only; the activity owns the SAF picker and URI permission. */
@Composable
internal fun UploadPanel(store: UploadStore, zh: Boolean, destinationLabel: String? = null, onPick: () -> Unit,
                        onClose: () -> Unit, onDescribe: (dev.photohouse.connected.core.UploadReceipt) -> Unit = {}) {
    val state by store.state.collectAsState()
    var now by remember(state) { mutableLongStateOf(System.currentTimeMillis()) }
    val retryAt = (state as? UploadState.Failed)?.problem?.retryAtMillis ?: 0
    LaunchedEffect(retryAt) { while (now < retryAt) { delay(500); now = System.currentTimeMillis() } }
    UploadPanelState(state, zh, onPick, onClose, { store.approveNetwork() }, { store.retry() }, store::cancel, now >= retryAt, destinationLabel, onDescribe)
}

@Composable
internal fun UploadPanelState(
    state: UploadState, zh: Boolean, onPick: () -> Unit, onClose: () -> Unit,
    onApproveNetwork: () -> Unit, onRetry: () -> Unit, onCancel: () -> Unit, retryReady: Boolean = true,
    destinationLabel: String? = null, onDescribe: (dev.photohouse.connected.core.UploadReceipt) -> Unit = {},
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    Card(Modifier.fillMaxWidth().testTag("upload-panel")) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(t("Add a photo", "添加照片"), style = MaterialTheme.typography.titleLarge)
            when (state) {
                UploadState.Idle, UploadState.Cancelled -> {
                    Text(destinationLabel?.let { t("Destination: $it", "目标资料库：$it") }
                        ?: t("Choose a destination library before selecting a photo.", "选择照片前，请先选择目标资料库。"), modifier = Modifier.testTag("upload-destination-label"))
                    Text(t("Choose one JPEG or PNG up to 25 MiB. Uploads follow the destination library's approval and processing settings.", "选择一张不超过 25 MiB 的 JPEG 或 PNG。上传内容将遵循目标资料库的审核和处理设置。"))
                    Text(t("Keep PhotoHouse open during upload. Leaving cancels this transfer; the server may already have received it.", "上传时请保持相册在前台。离开将取消本次传输；服务器可能已经收到照片。"), style = MaterialTheme.typography.bodySmall)
                    Text(t("Once your photo is approved for the family album, you can add a memory.", "照片审核后会加入家庭相册，届时可以添加回忆。"), style = MaterialTheme.typography.bodySmall)
                    Button(onClick = onPick, modifier = Modifier.testTag("upload-pick")) { Text(t("Choose photo", "选择照片")) }
                }
                is UploadState.AwaitingNetwork -> {
                    Text(if (state.network.name == "METERED") t("This connection may incur data charges. Continue?", "当前连接可能产生流量费用，是否继续？") else t("The network type is unknown. Continue only if you accept possible data charges.", "无法确认网络类型。继续前请确认可能产生流量费用。"), modifier = Modifier.testTag("upload-network-warning"))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = onApproveNetwork, modifier = Modifier.testTag("upload-network-approve")) { Text(t("Continue", "继续")) }
                        OutlinedButton(onClick = onClose) { Text(t("Later", "稍后")) }
                    }
                }
                is UploadState.Uploading -> {
                    Text(t("Uploading ${state.sent} of ${state.total} bytes", "正在上传 ${state.sent} / ${state.total} 字节"), modifier = Modifier.testTag("upload-progress"))
                    LinearProgressIndicator({ (state.sent.toFloat() / state.total.coerceAtLeast(1)).coerceIn(0f, 1f) }, Modifier.fillMaxWidth())
                    OutlinedButton(onClick = onCancel, modifier = Modifier.testTag("upload-cancel")) { Text(t("Cancel", "取消")) }
                }
                is UploadState.Failed -> {
                    if (state.problem.message == Message.TLS_ERROR) Text(t("Cannot verify the server's secure connection.", "无法验证服务器的安全连接。"), color = MaterialTheme.colorScheme.error)
                    if (state.problem.message == Message.INVALID_RESPONSE) Text(t("The server receipt could not be verified.", "无法验证服务器的接收凭据。"), color = MaterialTheme.colorScheme.error)
                    if (!retryReady) Text(t("Please wait before retrying.", "请稍候再重试。"))
                    Text(t("The upload was interrupted. The server may already have received it; retry only if needed.", "上传中断。服务器可能已经收到照片；确认后再手动重试。"), color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("upload-failed"))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (state.retryAvailable) Button(onClick = onRetry, enabled = retryReady, modifier = Modifier.testTag("upload-retry")) { Text(t("Retry", "重试")) }
                        OutlinedButton(onClick = onClose) { Text(t("Close", "关闭")) }
                    }
                }
                is UploadState.Succeeded -> {
                    val assigned = state.receipt.libraryId != null
                    Text(if (assigned && destinationLabel != null) t("Added to $destinationLabel", "已加入$destinationLabel")
                        else t("Received for review", "已收到，等待审核"),
                        modifier = Modifier.testTag("upload-received"))
                    Text(if (assigned && destinationLabel != null)
                        t("Photo ${state.receipt.assetId} was added to $destinationLabel. Processing may continue.", "照片 ${state.receipt.assetId} 已加入$destinationLabel，后台处理可能仍在进行。")
                        else t("Photo ${state.receipt.assetId} was received for review${destinationLabel?.let { " in $it" } ?: ""}.", "照片 ${state.receipt.assetId} 已收到，等待${destinationLabel?.let { "$it 的" } ?: ""}审核。"),
                        style = MaterialTheme.typography.bodySmall)
                    Text(t("You can add a memory once the photo appears in your album.", "照片出现在相册后，就可以添加回忆。"), style = MaterialTheme.typography.bodySmall)
                    if (state.receipt.destinationLibraryId != null) OutlinedButton(onClick = { onDescribe(state.receipt) },
                        modifier = Modifier.testTag("upload-add-description")) { Text(t("Add description", "添加描述")) }
                    Button(onClick = onClose, modifier = Modifier.testTag("upload-done")) { Text(t("Done", "完成")) }
                }
            }
        }
    }
}
