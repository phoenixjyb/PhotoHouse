package dev.photohouse.stories.fixture

import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.focusable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import dev.photohouse.stories.*
import kotlinx.coroutines.launch

private val Warm = Color(0xFFF6ECD9)
private val Pine = Color(0xFF19382D)
private val Honey = Color(0xFFF0CC8E)

@Composable private fun LabButton(text: String, tag: String, modifier: Modifier = Modifier, enabled: Boolean = true, action: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    OutlinedButton(action, modifier.testTag(tag).onFocusChanged { focused = it.isFocused }, enabled = enabled,
        shape = RoundedCornerShape(12.dp), border = BorderStroke(if (focused) 3.dp else 1.dp, if (focused) Honey else Color(0xFF7B897B)),
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)) { Text(text, maxLines = 1) }
}

@Composable fun StoryFixtureScreen(controller: StoryFixtureController, tv: Boolean = false, initialChinese: Boolean = false) {
    val state by controller.state.collectAsState()
    var zh by remember { mutableStateOf(initialChinese) }
    fun t(en: String, cn: String) = if (zh) cn else en
    val first = remember { FocusRequester() }
    val readFocus = remember { FocusRequester() }
    val list = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val window = LocalWindowInfo.current.isWindowFocused
    val route = when { state.scope == null -> "covered"; state.draft != null -> "draft"; state.selected != null -> "read"; else -> "list" }
    LaunchedEffect(route, window) {
        if (window) { list.scrollToItem(0); withFrameNanos { }; runCatching { first.requestFocus() } }
    }
    BackHandler(state.selected != null || state.draft != null) { controller.back() }
    MaterialTheme(colorScheme = if (tv) darkColorScheme(primary = Honey, background = Pine, surface = Pine, onSurface = Warm)
        else lightColorScheme(primary = Pine, background = Warm, surface = Warm, secondaryContainer = Color(0xFFE3E8D9))) {
        Surface(Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().safeDrawingPadding().padding(if (tv) 24.dp else 16.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column(Modifier.weight(1f)) {
                        Text(t("Family stories", "家人的故事"), fontFamily = FontFamily.Serif, style = MaterialTheme.typography.headlineSmall)
                        Text(t("Synthetic preview · offline", "虚构示例 · 离线预览"), style = MaterialTheme.typography.labelSmall)
                    }
                    LabButton(if (zh) "EN" else "中文", "story-language") { zh = !zh }
                }
                if (state.scope == null) {
                    Spacer(Modifier.height(24.dp))
                    Text(t("Private text and drafts have been cleared.", "私人文字和草稿已清除。"), Modifier.testTag("story-covered"))
                    LabButton(t("Reopen sample", "重新打开示例"), "story-reopen", Modifier.focusRequester(first)) { controller.activate(tv = tv) }
                    return@Column
                }
                if (state.discardPrompt) AlertDialog(onDismissRequest = controller::keepEditing,
                    title = { Text(t("Discard this draft?", "放弃这份草稿？")) },
                    text = { Text(if (state.pending != null) t("The save may have succeeded. This only clears your local draft; it cannot undo a save.", "保存可能已成功。此操作只清除本地草稿，不能撤销保存。")
                        else t("This sample draft is kept only in memory.", "此示例草稿仅保存在内存中。")) },
                    confirmButton = { LabButton(t("Discard draft", "放弃草稿"), "story-discard") { controller.discard() } },
                    dismissButton = { LabButton(t("Keep editing", "继续编辑"), "story-keep") { controller.keepEditing() } })
                if (tv) Text(t("Only sample stories explicitly published for this TV are shown.", "仅显示明确发布给此电视的示例故事。"), style = MaterialTheme.typography.bodySmall)
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LabButton(t("Back", "返回"), "story-back", Modifier.focusRequester(first)) { controller.back() }
                    if (state.selected == null && state.draft == null && !tv) {
                        for (role in StoryRole.entries) LabButton(when(role) {
                            StoryRole.VIEWER -> t("Viewer", "浏览者")
                            StoryRole.CONTRIBUTOR -> t("Contributor", "撰写者")
                            StoryRole.OWNER -> t("Owner", "所有者")
                        } + if (state.role == role) " ✓" else "", "story-role-$role") { controller.activate(role) }
                    }
                    LabButton(t("Hide preview", "隐藏预览"), "story-hide") { controller.clear() }
                }
                if (state.problem != null) Text(when(state.problem) {
                    StoryProblem.UNAVAILABLE -> t("Response lost. Retry uses the same save. Your draft is retained.", "响应丢失。重试会使用同一次保存，草稿已保留。")
                    StoryProblem.CONFLICT -> t("A newer version exists. Compare before saving your draft again.", "已有更新版本，请对照后再保存草稿。")
                    StoryProblem.DENIED -> t("Access lost. Private content was cleared.", "访问权限已失效，私人内容已清除。")
                    else -> t("Check text limits: title 512, byline 256, story 65,536 UTF-8 bytes.", "请检查文字长度：标题 512、署名 256、正文 65,536 个 UTF-8 字节。")
                }, Modifier.testTag("story-problem"), color = MaterialTheme.colorScheme.error)
                val draft = state.draft
                val card = state.selected
                LazyColumn(state = list, modifier = Modifier.weight(1f).fillMaxWidth().testTag("story-list"),
                    verticalArrangement = Arrangement.spacedBy(12.dp), contentPadding = PaddingValues(vertical = 12.dp)) {
                    if (draft != null) {
                        item { Text(t("Your words, separate from AI", "家人亲笔，独立于 AI 描述"), style = MaterialTheme.typography.titleMedium) }
                        item { OutlinedTextField(draft.content.title, { controller.update(draft.content.copy(title = it)) }, Modifier.fillMaxWidth().testTag("story-title-input"), enabled = state.pending == null, label = { Text(t("Title", "标题")) }) }
                        item { OutlinedTextField(draft.content.byline, { controller.update(draft.content.copy(byline = it)) }, Modifier.fillMaxWidth().testTag("story-byline-input"), enabled = state.pending == null, label = { Text(t("Byline (self supplied)", "署名（自行填写）")) }) }
                        item { OutlinedTextField(draft.content.text, { controller.update(draft.content.copy(text = it)) }, Modifier.fillMaxWidth().testTag("story-text-input"), enabled = state.pending == null, minLines = 6, maxLines = 12, label = { Text(t("Story", "故事正文")) }) }
                        state.latest?.let { latest ->
                            item { Text(t("Current version", "当前版本") + " ${latest.revision}", Modifier.testTag("story-current-version"), style = MaterialTheme.typography.titleMedium) }
                            item { Text(latest.content.text) }
                            item { LabButton(t("Keep my draft with this revision", "对照后保留草稿"), "story-rebase") { controller.useDraftAfterReview() } }
                        }
                        item {
                            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                LabButton(if (state.pending != null) t("Retry same save", "重试同次保存") else t("Save sample", "保存示例"), "story-save", enabled = draft.content.valid() && state.problem != StoryProblem.CONFLICT) { controller.simulateSave() }
                                if (state.pending == null) {
                                    LabButton(t("Simulate lost reply", "模拟响应丢失"), "story-lost", enabled = draft.content.valid() && state.problem != StoryProblem.CONFLICT) { controller.simulateSave(SaveSimulation.LOST_RESPONSE) }
                                    if (draft.story != null) LabButton(t("Simulate conflict", "模拟冲突"), "story-conflict", enabled = state.problem != StoryProblem.CONFLICT) { controller.simulateSave(SaveSimulation.CONFLICT) }
                                }
                                LabButton(t("Simulate access loss", "模拟权限失效"), "story-deny") { controller.deny() }
                            }
                        }
                    } else if (card != null) {
                        item { Text(sourceLabel(card.source, zh), Modifier.testTag("story-source"), style = MaterialTheme.typography.labelLarge) }
                        item { Text(card.content.title.ifBlank { t("Untitled memory", "无标题回忆") }, style = MaterialTheme.typography.headlineSmall, fontFamily = FontFamily.Serif) }
                        item { Text(card.content.byline.ifBlank { t("No byline", "未署名") } + " · " + t("Version", "版本") + " ${card.revision}", style = MaterialTheme.typography.bodySmall) }
                        if (state.saved) item { Text(t("Current version returned by the save. Review the text below.", "已返回保存后的当前版本，请查看下方正文。"), Modifier.testTag("story-saved")) }
                        if (card.canEdit && !tv) item { LabButton(t("Edit story", "编辑故事"), "story-edit") { controller.edit() } }
                        if (tv) item { LabButton(t("Read · ↑ ↓ scroll", "阅读 · ↑ ↓ 滚动"), "story-read-focus") { readFocus.requestFocus() } }
                        item {
                            Column(Modifier.fillMaxWidth().focusRequester(readFocus).onPreviewKeyEvent {
                                if (!tv || it.nativeKeyEvent.action != KeyEvent.ACTION_DOWN) false
                                else when(it.nativeKeyEvent.keyCode) {
                                    KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_UP -> {
                                        val forward = it.nativeKeyEvent.keyCode == KeyEvent.KEYCODE_DPAD_DOWN
                                        scope.launch { list.scrollBy(list.layoutInfo.viewportSize.height * if (forward) 0.65f else -0.65f) }; true
                                    }
                                    else -> false
                                }
                            }.focusable().semantics(mergeDescendants = true) {}.testTag("story-body")) {
                                Text(card.content.text, style = if (tv) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyLarge)
                            }
                        }
                    } else {
                        item { Text(t("Find the words behind a memory", "在文字中，找回那些回忆"), style = MaterialTheme.typography.titleMedium) }
                        item { OutlinedTextField(state.query, { controller.search(it) }, Modifier.fillMaxWidth().testTag("story-query"), singleLine = true, label = { Text(t("Search sample stories", "搜索示例故事")) }) }
                        item { Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            for (source in listOf(null, StorySource.FAMILY, StorySource.AI)) LabButton((source?.let { sourceLabel(it, zh) } ?: t("All sources", "全部来源")) + if (state.source == source) " ✓" else "", "story-source-$source") { controller.search(state.query, source) }
                        } }
                        item { Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            for (media in listOf(null, StoryMedia.IMAGE, StoryMedia.VIDEO)) LabButton(when(media) { null -> t("All media", "全部媒体"); StoryMedia.IMAGE -> t("Photos", "照片"); else -> t("Videos", "视频") } + if (state.media == media) " ✓" else "", "story-media-$media") { controller.search(state.query, media = media) }
                        } }
                        if (state.canCreate) item { LabButton(t("Write a sample memory", "写一段示例回忆"), "story-create") { controller.create() } }
                        if (state.results.isEmpty()) item { Text(t("No sample matches. Try another word or filter.", "没有匹配的示例，试试其他文字或筛选条件。"), Modifier.testTag("story-empty")) }
                        itemsIndexed(state.results, key = { _, value -> value.id }) { _, result ->
                            var focused by remember { mutableStateOf(false) }
                            OutlinedCard(onClick = { controller.open(result.id) }, Modifier.fillMaxWidth().testTag("story-card-${result.id}").onFocusChanged { focused = it.isFocused },
                                border = BorderStroke(if (focused) 3.dp else 1.dp, if (focused) Honey else MaterialTheme.colorScheme.outline)) {
                                Column(Modifier.padding(16.dp)) {
                                    Text(sourceLabel(result.source, zh), style = MaterialTheme.typography.labelMedium)
                                    Text(result.content.title, style = MaterialTheme.typography.titleMedium, fontFamily = FontFamily.Serif)
                                    Text(result.content.text.take(140), maxLines = 2, style = MaterialTheme.typography.bodyMedium)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun sourceLabel(source: StorySource, zh: Boolean) = when(source) {
    StorySource.FAMILY -> if (zh) "家人故事" else "Family story"
    StorySource.LEGACY_FAMILY -> if (zh) "旧家庭说明 · 作者未确认" else "Earlier family note · author unverified"
    StorySource.AI -> if (zh) "AI 描述" else "AI description"
}
