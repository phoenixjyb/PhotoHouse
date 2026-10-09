package dev.photohouse.ota

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** Shared update/check/install UI so all launch surfaces use the same guarded flow. */
@Composable
fun PhotoHouseOtaControl(
    channel: String,
    origin: String,
    zh: Boolean,
    modifier: Modifier = Modifier,
    lanAddress: String = "",
    checkModifier: Modifier = Modifier,
    actionButton: (@Composable (String, Modifier, Boolean, () -> Unit) -> Unit)? = null,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember(channel, origin, lanAddress) { mutableStateOf(false) }
    var status by remember(channel, origin, lanAddress) { mutableStateOf<String?>(null) }
    var prepared by remember(channel, origin, lanAddress) { mutableStateOf<PreparedPhotoHouseUpdate?>(null) }
    fun t(en: String, cn: String) = if (zh) cn else en
    @Composable fun action(label: String, tag: String, enabled: Boolean, onClick: () -> Unit) {
        val buttonModifier = Modifier.testTag(tag).then(if (tag == "ota-check") checkModifier else Modifier)
        if (actionButton != null) actionButton(label, buttonModifier, enabled, onClick)
        else TextButton(onClick = onClick, enabled = enabled, modifier = buttonModifier) { Text(label) }
    }

    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        action(t(if (busy) "Checking…" else "Check for updates", if (busy) "检查中…" else "检查更新"), "ota-check", !busy) {
            scope.launch {
                busy = true
                prepared = null
                status = t("Checking for updates…", "正在检查更新…")
                try {
                    val update = PhotoHouseOta.prepare(context, origin, channel, lanAddress)
                    prepared = update
                    status = t("Version ${update.offer.versionName} is ready.", "版本 ${update.offer.versionName} 已准备就绪。")
                } catch (e: CancellationException) {
                    throw e
                } catch (_: Exception) {
                    status = t("No newer update is available, or the update service could not be reached.", "没有可用的新版本，或暂时无法连接更新服务。")
                } finally { busy = false }
            }
        }
        status?.let { Text(it, Modifier.testTag("ota-status"), style = MaterialTheme.typography.bodySmall) }
        prepared?.let { update ->
            action(t("Continue to install", "继续安装"), "ota-install", true) {
                try {
                    if (PhotoHouseOta.canInstall(context)) context.startActivity(PhotoHouseOta.installerIntent(context, update))
                    else {
                        status = t("Allow PhotoHouse to install apps in Android settings, then return and continue.", "请在系统设置中允许拾光相册安装应用，返回后继续。")
                        context.startActivity(PhotoHouseOta.unknownSourcesSettings(context))
                    }
                } catch (_: Exception) {
                    status = t("Android could not open the installer. Try again from this screen.", "无法打开系统安装程序，请返回此页面重试。")
                }
            }
        }
    }
}
