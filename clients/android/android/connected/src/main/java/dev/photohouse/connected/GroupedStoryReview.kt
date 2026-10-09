package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*

/** Review surface for the optional grouped-story store. Gallery entry is integrated separately. */
@Composable
internal fun GroupedStoryReview(store: StoryWorkspaceStore, zh: Boolean, onClose: () -> Unit,
    onReadSaved: (SavedMemoryStory) -> Unit) {
    val state by store.state.collectAsState()
    fun t(en: String, cn: String) = if (zh) cn else en
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    fun finishTyping() { focus.clearFocus(); keyboard?.hide() }
    var discard by remember(store) { mutableStateOf(false) }
    var chapterIndex by remember(state.draft?.selectionRevision) { mutableIntStateOf(0) }
    val editable = state.status == StoryWorkspaceStoreStatus.EDITING && !state.busy && !state.hasPendingSave
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp)
        .testTag("grouped-story-review"), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(t("Turn moments into a story", "把这些瞬间写成故事"), style = MaterialTheme.typography.headlineSmall,
            fontFamily = FontFamily.Serif)
        Text(t("${state.selectedAssetIds.size} selected · photos and videos in your chosen order",
            "${state.selectedAssetIds.size} 个瞬间 · 照片与视频按所选顺序排列"), style = MaterialTheme.typography.bodyMedium)
        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (state.status == StoryWorkspaceStoreStatus.SELECTION) {
            Text(t("Choose the moments for one event, then create an editable outline.",
                "选择同一次活动的瞬间，再创建可修改的提纲。"))
            Button(onClick = { store.preview() }, enabled = state.selectedAssetIds.isNotEmpty(),
                modifier = Modifier.fillMaxWidth().testTag("grouped-story-preview")) {
                Text(t("Create outline", "创建提纲"))
            }
        }
        val draft = state.draft
        if (draft != null && state.savedStory == null) {
            if (state.sourcesReloaded && state.status == StoryWorkspaceStoreStatus.EDITING) {
                Text(t("Current sources were loaded. Your title and chapter text were kept; review the sources again before saving.",
                    "已加载当前来源。故事标题与篇章文字已保留；保存前请重新核对来源。"),
                    color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.testTag("grouped-story-sources-reloaded"))
            }
            Text(t("This is an outline to review. Original family words and AI observations remain separate.",
                "这是一份待核对的提纲。家人的原话与 AI 观察会分别保留。"), style = MaterialTheme.typography.bodySmall)
            var title by remember(draft.selectionRevision) { mutableStateOf(TextFieldValue(state.title)) }
            LaunchedEffect(state.title) {
                if (title.composition == null && title.text != state.title) title = TextFieldValue(state.title)
            }
            OutlinedTextField(title, { value -> title = value; store.editTitle(value.text)
                store.composition(value.composition != null) }, label = { Text(t("Story title", "故事标题")) },
                enabled = editable, isError = state.invalidInput, maxLines = 3,
                modifier = Modifier.fillMaxWidth().testTag("grouped-story-title"))
            OutlinedButton(onClick = { finishTyping(); store.loadTitleCapabilities() }, enabled = editable && !state.composing,
                modifier = Modifier.fillMaxWidth().testTag("grouped-story-title-check")) {
                Text(t("Title suggestions", "查看标题建议"))
            }
            if (state.titleCapabilities?.enabled == true) {
                OutlinedButton(onClick = { finishTyping(); store.suggestTitles() }, enabled = editable && !state.composing,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-suggest")) { Text(t("Suggest titles", "建议故事标题")) }
            } else if (state.titleCapabilities != null) Text(t("Title assistance is unavailable. You can keep editing.",
                "标题建议暂不可用，可以继续手动修改。"), style = MaterialTheme.typography.bodySmall)
            state.titleCandidates.forEachIndexed { index, candidate ->
                OutlinedButton(onClick = { store.adoptTitleCandidate(index) }, enabled = editable && !state.composing,
                    modifier = Modifier.fillMaxWidth()) { Text(candidate.text) }
                candidate.sourceIds.forEach { id ->
                    val evidence = draft.items.flatMap { it.evidence }.find { it.id == id }
                    val words = evidence?.text ?: state.editableChapters.find { "draft-${it.id}" == id }?.narration
                    val label = when (evidence?.source) {
                        "family" -> t("Family account: ", "家人讲述：")
                        "ai" -> t("AI observation: ", "AI 观察：")
                        else -> t("Edited draft: ", "已修改草稿：")
                    }
                    if (!words.isNullOrBlank()) Text(label + words,
                        style = MaterialTheme.typography.bodySmall)
                }
            }
            val index = chapterIndex.coerceIn(state.editableChapters.indices)
            val chapter = state.editableChapters[index]
            Text(t("Chapter ${index + 1} / ${state.editableChapters.size}", "篇章 ${index + 1} / ${state.editableChapters.size}"),
                style = MaterialTheme.typography.titleMedium)
            key(chapter.id) {
                var name by remember { mutableStateOf(TextFieldValue(chapter.title)) }
                var words by remember { mutableStateOf(TextFieldValue(chapter.narration)) }
                OutlinedTextField(name, { value -> name = value; store.editChapterTitle(index, value.text)
                    store.composition(value.composition != null) }, enabled = editable,
                    label = { Text(t("Chapter title", "篇章标题")) }, maxLines = 3,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-chapter-title"))
                OutlinedTextField(words, { value -> words = value; store.editChapterNarration(index, value.text)
                    store.composition(value.composition != null) }, enabled = editable,
                    label = { Text(t("Tell this part in your own words", "用自己的话讲述这一段")) }, minLines = 4, maxLines = 9,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-chapter-words"))
            }
            key(chapter.id) {
                var showSources by remember { mutableStateOf(false) }
                val sources = draft.items.filter { it.asset.id in chapter.assetIds }.flatMap { it.evidence }
                    .filter { it.id in chapter.evidenceIds }
                if (sources.isNotEmpty()) {
                    TextButton(onClick = { showSources = !showSources }, modifier = Modifier.fillMaxWidth()) {
                        Text(t("Review sources (${sources.size})", "核对来源（${sources.size}）"))
                    }
                    if (showSources) sources.forEach { source ->
                        Text(if (source.source == "family") t("Family account", "家人讲述") else t("AI observation", "AI 观察"),
                            style = MaterialTheme.typography.labelLarge)
                        if (source.title.isNotBlank()) Text(source.title, style = MaterialTheme.typography.titleSmall)
                        Text(source.text, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                OutlinedButton(onClick = { finishTyping(); chapterIndex-- }, enabled = editable && !state.composing && index > 0) {
                    Text(t("Previous", "上一篇")) }
                OutlinedButton(onClick = { finishTyping(); chapterIndex++ }, enabled = editable && !state.composing && index < state.editableChapters.lastIndex) {
                    Text(t("Next", "下一篇")) }
            }
            draft.questions.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
            if (state.invalidInput) Text(t("Check the title and shorten any oversized text before saving.",
                "请核对标题并缩短超长文字，再保存。"), color = MaterialTheme.colorScheme.error)
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(state.reviewed,
                enabled = editable && !state.composing && !state.invalidInput, role = Role.Checkbox,
                onValueChange = { finishTyping(); store.confirmReviewed(it) }).testTag("grouped-story-reviewed"), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(state.reviewed, onCheckedChange = null)
                Text(t("I reviewed these words and sources", "我已核对这些文字与来源"), Modifier.weight(1f))
            }
            Button(onClick = { finishTyping(); store.save() }, enabled = editable && state.reviewed && !state.composing && !state.invalidInput,
                modifier = Modifier.fillMaxWidth().testTag("grouped-story-save")) { Text(t("Save story", "保存故事")) }
        }
        if (state.status == StoryWorkspaceStoreStatus.SAVE_UNCERTAIN) {
            Text(t("The story may already be saved. Check again using the same request to avoid a duplicate.",
                "故事可能已经保存。使用同一次请求再次确认，避免重复创建。"))
            Button(onClick = { store.retrySave() }, modifier = Modifier.fillMaxWidth().testTag("grouped-story-retry")) {
                Text(t("Confirm this save", "再次确认这次保存")) }
        }
        if (state.status in setOf(StoryWorkspaceStoreStatus.CONFLICT, StoryWorkspaceStoreStatus.UNAVAILABLE)) {
            Text(if (draft != null) t("The story could not be confirmed. Your text remains here. Reload current sources to review this draft again.",
                "暂时无法确认故事。文字仍保留在这里。请重新加载当前来源，再次核对草稿。")
                else t("The preview could not be loaded. Your selection remains here; retry when access is available.",
                    "暂时无法加载预览。所选内容仍保留；访问恢复后可以重试。"))
            if (draft != null && state.status in setOf(StoryWorkspaceStoreStatus.CONFLICT, StoryWorkspaceStoreStatus.UNAVAILABLE)) {
                Button(onClick = { finishTyping(); store.reloadPreview() },
                    enabled = !state.busy && !state.composing && !state.hasPendingSave,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-reload-sources")) {
                    Text(t("Reload sources and review", "重新加载来源并核对"))
                }
            } else if (draft == null && state.status == StoryWorkspaceStoreStatus.UNAVAILABLE && state.selectedAssetIds.isNotEmpty()) {
                Button(onClick = { store.retryPreview() },
                    enabled = !state.busy && !state.composing && !state.hasPendingSave,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-retry-preview")) {
                    Text(t("Retry preview", "重试预览"))
                }
            }
        }
        state.savedStory?.let { saved ->
            Text(t("Story saved", "故事已保存"), style = MaterialTheme.typography.titleLarge)
            Button(onClick = { onReadSaved(saved) }, modifier = Modifier.fillMaxWidth().testTag("grouped-story-read")) {
                Text(t("Read the story", "阅读故事")) }
        }
        OutlinedButton(onClick = { finishTyping(); if (store.close()) onClose() else discard = true },
            modifier = Modifier.fillMaxWidth().testTag("grouped-story-close")) { Text(t("Close", "关闭")) }
    }
    if (discard) AlertDialog(onDismissRequest = { discard = false },
        title = { Text(t("Leave this draft?", "离开这份草稿？")) },
        text = { Text(t("Unsaved edits will be discarded. A pending save may already exist on the server.",
            "未保存的修改将丢弃。已经发出的保存请求可能已在服务器生效。")) },
        confirmButton = { TextButton(onClick = { store.close(discard = true); discard = false; onClose() }) {
            Text(t("Discard and close", "丢弃并关闭")) } },
        dismissButton = { TextButton(onClick = { discard = false }) { Text(t("Keep editing", "继续编辑")) } })
}
