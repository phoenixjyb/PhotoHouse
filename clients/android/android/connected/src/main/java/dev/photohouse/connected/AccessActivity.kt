package dev.photohouse.connected

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import dev.photohouse.ota.PhotoHouseOtaControl

/** Home and account remain explicit destinations; OTA starts only after the user asks to check. */
class AccessActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(null)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        setContent { AccessChoices(
            home = { startActivity(Intent(this, HomeActivity::class.java)) },
            account = { startActivity(Intent(this, MainActivity::class.java)) }) }
    }
}

@Composable internal fun AccessChoices(home: () -> Unit, account: () -> Unit) {
    var zh by remember { mutableStateOf(true) }
    fun t(en: String, cn: String) = if (zh) cn else en
    PhotoHouseTheme { Surface(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = { zh = !zh }, modifier = Modifier.testTag("access-language")) { Text(if (zh) "English" else "简体中文") }
            }
            Text(t("PhotoHouse", "拾光相册"), style = MaterialTheme.typography.headlineLarge, fontFamily = FontFamily.Serif)
            Text(t("Your family's stories, wherever you are.", "家的故事，随时相伴。"), style = MaterialTheme.typography.titleMedium)
            PhotoHouseOtaControl("phone", BuildConfig.PHOTOHOUSE_ORIGIN, zh, Modifier.testTag("access-ota"))
            Spacer(Modifier.height(12.dp))
            Card(onClick = home, modifier = Modifier.fillMaxWidth().testTag("access-home")) {
                Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(t("At home", "在家浏览"), style = MaterialTheme.typography.headlineSmall)
                    Text(t("Open the home album on your home network. No sign-in.", "连接家庭网络，直接打开家庭相册，无需登录。"))
                    Text(t("Photos · Videos · Ready to play", "照片 · 视频 · 已就绪媒体"), color = MaterialTheme.colorScheme.primary)
                }
            }
            OutlinedCard(onClick = account, modifier = Modifier.fillMaxWidth().testTag("access-account")) {
                Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(t("Sign in", "账号登录"), style = MaterialTheme.typography.headlineSmall)
                    Text(t("Use your account to open the libraries shared with you.", "使用账号访问已授权给你的资料库。"))
                }
            }
            Text(t("Home access is approved by your server. Away from home, use your account connection.",
                "家庭访问由服务器授权。离家后请使用账号连接。"), style = MaterialTheme.typography.bodySmall)
        }
    } }
}
