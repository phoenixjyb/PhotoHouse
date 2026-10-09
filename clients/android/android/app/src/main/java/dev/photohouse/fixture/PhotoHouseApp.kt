package dev.photohouse.fixture

import dev.photohouse.protocol.*
import android.graphics.BitmapFactory
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import dev.photohouse.fixture.core.*
import kotlinx.coroutines.delay

private enum class Language { SYSTEM, EN, ZH }
private class Words(val zh: Boolean) {
    fun pick(en: String, cn: String) = if (zh) cn else en
    fun notice(notice: Notice) = when (notice) {
        Notice.INVALID_INVITATION -> pick("Invitation not accepted. You are still signed out.", "邀请无效，尚未登录。")
        Notice.DENIED -> pick("This content is unavailable to this session. Library access was checked once.", "此会话无法访问该内容。已重新检查一次资料库权限。")
        Notice.CLOSED -> pick("Access is closed. No alternate route is available.", "访问已关闭，无法使用其他路径。")
        Notice.UNAVAILABLE -> pick("Temporarily unavailable. Your access has not been marked revoked.", "暂时无法连接，这不表示权限已被撤销。")
        Notice.RATE_LIMITED -> pick("Too many attempts. Please wait before retrying.", "尝试过于频繁，请稍后重试。")
        Notice.INVALID_RESPONSE -> pick("This demo response could not be displayed safely.", "无法安全显示此演示响应。")
        Notice.LOCAL_LOGOUT -> pick("Signed out on this device. No live server was contacted.", "已在此设备退出，未联系真实服务器。")
        Notice.EXPIRED -> pick("Session ended. Sign in to the demo again.", "会话已结束，请重新登录演示。")
        Notice.NO_FIXTURE -> pick("This library is available, but the shared pack has no gallery for it.", "此资料库可访问，但共享演示包不含其相册内容。")
    }
    fun membership(m: Membership) = when {
        m.available -> pick("Available · ${m.role}", "可访问 · ${role(m.role)}")
        m.status == "requested" -> pick("Awaiting approval", "等待批准")
        m.status == "rejected" -> pick("Not approved", "未获批准")
        m.status == "revoked" -> pick("Access revoked", "权限已撤销")
        m.expires_at != null -> pick("Membership expired / unavailable", "成员资格已过期 / 不可访问")
        else -> pick("Library unavailable", "资料库不可访问")
    }
    private fun role(role: String) = when (role) { "viewer" -> "查看者"; "owner" -> "所有者"; "contributor" -> "贡献者"; else -> role }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PhotoHouseApp(store: PhotoHouseStore) {
    val state by store.state.collectAsState()
    var language by remember { mutableStateOf(Language.SYSTEM) }
    val configuration = LocalConfiguration.current
    val systemChinese = configuration.locales[0].language == "zh"
    val words = Words(language == Language.ZH || language == Language.SYSTEM && systemChinese)
    val w = words::pick
    MaterialTheme(colorScheme = lightColorScheme(
        primary = Color(0xFF48634D), onPrimary = Color.White,
        background = Color(0xFFFAF7F2), surface = Color(0xFFFAF7F2),
        surfaceVariant = Color(0xFFEDE8DE), onSurface = Color(0xFF272C27),
    )) {
        Surface(Modifier.fillMaxSize()) {
            BackHandler(state.library != null && !state.covered) {
                if (state.detail != null) store.loadGallery() else store.libraries()
            }
            LazyColumn(
                Modifier.fillMaxSize().safeDrawingPadding().testTag("screen"),
                contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                item {
                    Text(w("PhotoHouse", "拾光相册"), style = MaterialTheme.typography.headlineLarge,
                        modifier = Modifier.semantics { heading() })
                    Text(w("FIXTURE DEMO · No real connection", "演示数据 · 无真实连接"),
                        color = MaterialTheme.colorScheme.primary, modifier = Modifier.testTag("fixture-banner"))
                }
                item {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(selected = language == Language.SYSTEM, onClick = { language = Language.SYSTEM }, label = { Text(w("System", "系统")) })
                        FilterChip(selected = language == Language.EN, onClick = { language = Language.EN }, label = { Text("English") }, modifier = Modifier.testTag("language-en"))
                        FilterChip(selected = language == Language.ZH, onClick = { language = Language.ZH }, label = { Text("简体中文") }, modifier = Modifier.testTag("language-zh"))
                    }
                }
                if (state.busy) item { LinearProgressIndicator(Modifier.fillMaxWidth().testTag("loading")) }
                state.problem?.let { problem -> item {
                    Card(Modifier.fillMaxWidth().testTag("notice")) {
                        Column(Modifier.padding(16.dp)) {
                            Text(words.notice(problem.notice))
                            var clock by remember(problem) { mutableLongStateOf(System.currentTimeMillis()) }
                            LaunchedEffect(problem) {
                                while (clock < problem.retryAtMillis) { delay(250); clock = System.currentTimeMillis() }
                            }
                            if (problem.retryAtMillis > clock) Text(w("Wait a moment", "请稍候"))
                            if (store.canRetry(clock)) TextButton(onClick = store::retry, modifier = Modifier.testTag("retry")) { Text(w("Retry", "重试")) }
                        }
                    }
                } }
                if (state.covered) {
                    item { Text(w("Private content covered", "私人内容已遮盖"), modifier = Modifier.testTag("privacy-cover")) }
                    if (!state.busy) item { Action(w("Check session", "检查会话"), "check-session") { store.foreground() } }
                    item { Action(w("Sign out locally", "在本机退出"), "logout") { store.logout() } }
                } else if (state.session == null) {
                    item {
                        Text(w("A little space for shared memories", "给共同的回忆留个位置"), style = MaterialTheme.typography.headlineSmall)
                        Text(w("Explore with reserved demo accounts only. These controls never collect your phone, password or invitation.",
                            "仅使用预设演示账号。这里不会收集你的手机号、密码或邀请码。"))
                        Text(w("Demo phone: ${DemoInputs.PHONE} · unverified", "演示手机号：${DemoInputs.PHONE} · 未验证"))
                    }
                    item { Action(w("Sign in to demo", "登录演示"), "sign-in", !state.busy) { store.signIn() } }
                    item { Action(w("Register with demo invitation", "使用演示邀请注册"), "register", !state.busy) { store.signIn(invited = true) } }
                    item { Action(w("Try invalid invitation", "尝试无效邀请"), "invalid-invite", !state.busy) { store.signIn(invited = true, invalidInvitation = true) } }
                    item { ProfileDemos(store, words, state.busy) }
                } else {
                    item {
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = store::libraries, modifier = Modifier.testTag("libraries")) { Text(w("Libraries", "资料库")) }
                            OutlinedButton(onClick = { store.logout() }, modifier = Modifier.testTag("logout")) { Text(w("Sign out", "退出登录")) }
                        }
                    }
                    when {
                        state.library == null -> {
                            item {
                                Text(w("Your libraries", "你的资料库"), style = MaterialTheme.typography.headlineSmall)
                                Text(w("Phone is an unverified login label.", "手机号是未经验证的登录标识。"))
                                if (state.session!!.memberships.isEmpty()) Text(w("No library memberships", "尚未加入任何资料库"), modifier = Modifier.testTag("no-memberships"))
                            }
                            items(state.session!!.memberships, key = { it.library_id }) { membership ->
                                Card(Modifier.fillMaxWidth()) {
                                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Text(LibraryNames.display(membership.library_id, words.zh), style = MaterialTheme.typography.titleLarge)
                                        Text(words.membership(membership))
                                        Action(w("Open library", "打开资料库"), "library-${membership.library_id}", membership.available && !state.busy) {
                                            store.selectLibrary(membership.library_id)
                                        }
                                    }
                                }
                            }
                            if (state.session!!.account_id.endsWith("0001")) item {
                                Action(w("Accept second demo invitation", "接受第二个演示邀请"), "accept-invitation", !state.busy) { store.acceptDemoInvitation() }
                            }
                            item { Text(w("Only an available membership permits browsing.", "仅可访问的成员资格允许浏览。")) }
                        }
                        state.detail != null -> {
                            val detail = state.detail!!
                            item { TextButton(onClick = { store.loadGallery() }, modifier = Modifier.testTag("back-photos")) { Text(w("Back to Photos", "返回照片")) } }
                            item { Preview(detail.asset, state.previews[detail.asset.id], words) }
                            item {
                                Text(detail.asset.taken_at ?: w("Date unknown", "日期未知"), style = MaterialTheme.typography.titleLarge)
                                Text(w("Source date · shown as received", "原始日期 · 按原文显示"))
                                if (detail.asset.kind == "video") Text(w("Video unavailable · metadata only", "视频不可用 · 仅有元数据"), modifier = Modifier.testTag("video-unavailable"))
                                if (!detail.originals_allowed) Text(w("Original access is not permitted", "无原始文件访问权限"))
                                Text(w("Captions · AI unless marked edited", "描述 · 未标注编辑时为 AI 内容"), style = MaterialTheme.typography.titleMedium)
                                Text(w("Language information is not supplied. Text is shown as received.", "未提供语言信息，按原文显示。"))
                            }
                            if (state.captions?.items.isNullOrEmpty()) item { Text(w("No captions yet", "暂无描述"), modifier = Modifier.testTag("captions-empty")) }
                            items(state.captions?.items.orEmpty(), key = { it.id }) { caption ->
                                Card(Modifier.fillMaxWidth()) {
                                    Column(Modifier.padding(16.dp)) {
                                        // Compose Text displays markup literally; no HTML or translation parsing.
                                        Text(caption.text, modifier = Modifier.testTag("caption-${caption.id}"))
                                        if (caption.user_edited) Text(w("Edited", "已编辑"))
                                        if (caption.truncated) Text(w("Text truncated", "文本已截断"))
                                    }
                                }
                            }
                            if (state.captions?.has_more == true) item { Text(w("More captions exist", "还有更多描述")) }
                        }
                        else -> {
                            item {
                                Text(w("Photos", "照片"), style = MaterialTheme.typography.headlineMedium)
                                Text(LibraryNames.display(state.library!!, words.zh))
                            }
                            state.gallery?.let { gallery ->
                                if (gallery.items.isEmpty()) item { Text(w("This page has no photos", "此页没有照片"), modifier = Modifier.testTag("empty-gallery")) }
                                // Two columns when there is room; one at large font or narrow widths.
                                val columns = if (configuration.fontScale > 1.3f || configuration.screenWidthDp < 360) 1 else 2
                                items(gallery.items.chunked(columns)) { row ->
                                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                        row.forEach { asset ->
                                            Card(onClick = { store.openAsset(asset) }, modifier = Modifier.weight(1f).testTag("asset-${asset.id}")) {
                                                Preview(asset, state.previews[asset.id], words)
                                                Text(asset.taken_at ?: w("Date unknown", "日期未知"), modifier = Modifier.padding(12.dp))
                                            }
                                        }
                                        if (row.size < columns) Spacer(Modifier.weight(1f))
                                    }
                                }
                            }
                            if (state.library == "family-a") item { GalleryDemos(store, state, words) }
                        }
                    }
                }
            }
        }
    }
}

@Composable private fun Action(label: String, tag: String, enabled: Boolean = true, action: () -> Unit) {
    Button(onClick = action, enabled = enabled, modifier = Modifier.fillMaxWidth().testTag(tag)) { Text(label) }
}

@Composable private fun Preview(asset: Asset, bytes: ByteArray?, words: Words) {
    val bitmap = remember(bytes) { bytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() } }
    if (bitmap == null) {
        Box(Modifier.fillMaxWidth().heightIn(min = 120.dp).background(MaterialTheme.colorScheme.surfaceVariant).padding(16.dp)) {
            Text(words.pick("Preview unavailable", "预览不可用"), modifier = Modifier.testTag("preview-missing-${asset.id}"))
        }
    } else Image(bitmap, contentDescription = words.pick("Synthetic photo ${asset.id}", "合成照片 ${asset.id}"),
        contentScale = ContentScale.Crop, modifier = Modifier.fillMaxWidth().aspectRatio(4f / 3).clip(RoundedCornerShape(12.dp)))
}

@Composable private fun ProfileDemos(store: PhotoHouseStore, words: Words, busy: Boolean) {
    var expanded by remember { mutableStateOf(false) }
    TextButton(onClick = { expanded = !expanded }, modifier = Modifier.testTag("profile-demos")) { Text(words.pick("Explore demo access states", "体验演示权限状态")) }
    if (expanded) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf("requested" to ("Awaiting approval" to "等待批准"), "rejected" to ("Rejected" to "已拒绝"),
            "revoked" to ("Revoked" to "已撤销"), "membership-expired" to ("Expired membership" to "成员资格过期"),
            "no-memberships" to ("No libraries" to "没有资料库"), "two-libraries" to ("Two libraries" to "两个资料库")).forEach { (id, names) ->
            Action(words.pick(names.first, names.second), "profile-$id", !busy) { store.signIn(profile = id) }
        }
        Action(words.pick("Rate limited sign-in", "登录频率限制"), "rate-limited", !busy) { store.signIn(admission = "rate-limited") }
        Action(words.pick("Unavailable session", "会话暂不可用"), "unavailable", !busy) { store.signIn(profile = "unavailable") }
    }
}

@Composable private fun GalleryDemos(store: PhotoHouseStore, state: PhotoState, words: Words) {
    var expanded by remember(state.generation) { mutableStateOf(false) }
    TextButton(onClick = { expanded = !expanded }, modifier = Modifier.testTag("gallery-demos")) { Text(words.pick("Explore demo photo states", "体验演示照片状态")) }
    if (expanded) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Action(words.pick("Refresh photos", "刷新照片"), "refresh") { store.loadGallery() }
        Action(words.pick("Empty page", "空白页"), "empty-page") { store.loadGallery("empty-page") }
        Action(words.pick("Missing previews", "缺失预览"), "missing-preview") { store.loadGallery(missingPreview = true) }
        Action(words.pick("Delayed photos (3 seconds)", "延迟照片（3 秒）"), "delayed-gallery") { store.loadGallery(delayed = true) }
        val asset = state.gallery?.items?.firstOrNull()
        if (asset != null) {
            Action(words.pick("Content denied; session valid", "内容拒绝；会话有效"), "foreign-valid") { store.openAsset(asset, denied = true) }
            Action(words.pick("Content denied; session ended", "内容拒绝；会话结束"), "foreign-expired") { store.openAsset(asset, denied = true, recheck = "expired") }
            if (asset.id == "102") Action(words.pick("No captions", "没有描述"), "missing-captions") { store.openAsset(asset, missingCaptions = true) }
        }
        Action(words.pick("End session on next check", "检查时结束会话"), "expire-session") { store.background(); store.foreground("expired") }
        Action(words.pick("Unavailable foreground check", "前台检查暂不可用"), "offline-session") { store.background(); store.foreground("unavailable") }
        Action(words.pick("Sign out with unavailable server", "服务器不可用时退出"), "offline-logout") { store.logout(serverUnavailable = true) }
    }
}
