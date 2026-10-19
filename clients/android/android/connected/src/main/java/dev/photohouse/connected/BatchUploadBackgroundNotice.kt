package dev.photohouse.connected

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable internal fun BatchUploadBackgroundNotice(zh: Boolean, notificationsAllowed: Boolean, onAllow: () -> Unit) {
    fun t(en: String, cn: String) = if (zh) cn else en
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(t("Batch uploads can continue with the screen locked. Use the upload notification to pause. If Android ends the task, open PhotoHouse and resume from the saved server progress.",
            "批量上传可在锁屏后继续，可在上传通知中暂停。若系统结束任务，请打开相册继续，已接收的进度会保留。"),
            style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("batch-background-explanation"))
        if (!notificationsAllowed) {
            Text(t("Notifications are off. Reopen PhotoHouse to pause, or stop it from Android's active-app controls. Allow notifications for a quick Pause button.",
                "未开启通知时，请重新打开相册暂停上传，也可使用 Android 的运行中应用控制停止任务。开启通知后可直接点暂停。"),
                style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = onAllow, modifier = Modifier.testTag("batch-enable-notifications")) {
                Text(t("Allow upload progress notifications", "允许显示上传进度通知"))
            }
        }
    }
}
