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
    onReadSaved: (SavedMemoryStory) -> Unit, isSavedEdit: Boolean = store.isSavedStoryEdit,
    savedEditReloading: Boolean = false, savedEditReloadFailed: Boolean = false,
    onReloadSavedEdit: (() -> Unit)? = null) {
    val state by store.state.collectAsState()
    val dictationStore by store.chapterDictation.collectAsState()
    val dictationUnfinished by store.dictationUnfinished.collectAsState()
    fun t(en: String, cn: String) = if (zh) cn else en
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    fun finishTyping() { focus.clearFocus(); keyboard?.hide() }
    var discard by remember(store) { mutableStateOf(false) }
    var discardDictation by remember(store) { mutableStateOf(false) }
    var confirmSavedEditReload by remember(store) { mutableStateOf(false) }
    var chapterIndex by remember(store, store.savedEditStoryId, store.savedEditStoryRevision,
        state.draft?.selectionRevision) { mutableIntStateOf(0) }
    val reviewScrollState = rememberScrollState()
    val editable = state.status == StoryWorkspaceStoreStatus.EDITING && !state.busy && !state.hasPendingSave && !savedEditReloading
    Column(Modifier.fillMaxSize().verticalScroll(reviewScrollState).padding(20.dp)
        .testTag("grouped-story-review"), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(if (isSavedEdit) t("Edit saved story", "编辑已保存故事") else t("Turn moments into a story", "把这些瞬间写成故事"), style = MaterialTheme.typography.headlineSmall,
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
            Text(if (isSavedEdit) t("You are editing the saved chapters. The existing photos, chapter grouping, theme and language stay attached to this story.",
                "你正在编辑已保存的篇章。现有照片、篇章分组、主题和语言仍属于这份故事。")
                else t("This is an outline to review. Original family words and AI observations remain separate.",
                    "这是一份待核对的提纲。家人的原话与 AI 观察会分别保留。"), style = MaterialTheme.typography.bodySmall)
            var title by remember(draft.selectionRevision) { mutableStateOf(TextFieldValue(state.title)) }
            LaunchedEffect(state.title) {
                if (title.composition == null && title.text != state.title) title = TextFieldValue(state.title)
            }
            OutlinedTextField(title, { value -> title = value; store.editTitle(value.text)
                store.composition(value.composition != null) }, label = { Text(t("Story title", "故事标题")) },
                enabled = editable && !dictationUnfinished, isError = state.invalidInput, maxLines = 3,
                modifier = Modifier.fillMaxWidth().testTag("grouped-story-title"))
            OutlinedButton(onClick = { finishTyping(); store.loadTitleCapabilities() }, enabled = editable && !state.composing && !dictationUnfinished,
                modifier = Modifier.fillMaxWidth().testTag("grouped-story-title-check")) {
                Text(t("Title suggestions", "查看标题建议"))
            }
            if (state.titleCapabilities?.enabled == true) {
                OutlinedButton(onClick = { finishTyping(); store.suggestTitles() }, enabled = editable && !state.composing && !dictationUnfinished,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-suggest")) { Text(t("Suggest titles", "建议故事标题")) }
            } else if (state.titleCapabilities != null) Text(t("Title assistance is unavailable. You can keep editing.",
                "标题建议暂不可用，可以继续手动修改。"), style = MaterialTheme.typography.bodySmall)
            if (!state.sourceReviewEnabled && !state.sourceCapabilitiesChecked) {
                OutlinedButton(onClick = { finishTyping(); store.enableSourceReview() }, enabled = editable && !state.composing && !dictationUnfinished,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-source-review-enable")) {
                    Text(t("Choose evidence for each chapter", "选择每篇使用的素材证据"))
                }
            } else if (state.sourceReviewEnabled) {
                Text(t("These choices control which photo or video item evidence is used. Chapter text and accepted family contributions stay separate.",
                    "这些选择决定使用哪些照片或视频素材证据。篇章文字与已确认的家人贡献保持独立。"),
                    style = MaterialTheme.typography.bodySmall)
            } else if (!state.sourceReviewEnabled && state.sourceCapabilitiesChecked && state.sourceCapabilities == null) {
                Text(t("Per-chapter source choices are unavailable on this server.", "此服务器暂不支持按篇章选择素材证据。"),
                    style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("grouped-story-source-review-unavailable"))
            }
            state.titleCandidates.forEachIndexed { index, candidate ->
                OutlinedButton(onClick = { store.adoptTitleCandidate(index) }, enabled = editable && !state.composing && !dictationUnfinished,
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
            LaunchedEffect(store, store.savedEditStoryId, store.savedEditStoryRevision,
                draft.selectionRevision, chapter.id) {
                reviewScrollState.scrollTo(0)
            }
            Text(t("Chapter ${index + 1} / ${state.editableChapters.size}", "篇章 ${index + 1} / ${state.editableChapters.size}"),
                style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("grouped-story-chapter-position"))
            key(chapter.id) {
                var name by remember { mutableStateOf(TextFieldValue(chapter.title)) }
                var words by remember { mutableStateOf(TextFieldValue(chapter.narration)) }
                var insertRejected by remember(dictationStore) { mutableStateOf(false) }
                LaunchedEffect(chapter.title) {
                    if (name.composition == null && name.text != chapter.title) name = TextFieldValue(chapter.title)
                }
                LaunchedEffect(chapter.narration) {
                    if (words.composition == null && words.text != chapter.narration) words = TextFieldValue(chapter.narration)
                }
                OutlinedTextField(name, { value -> name = value; store.editChapterTitle(index, value.text)
                    store.composition(value.composition != null) }, enabled = editable && !dictationUnfinished,
                    label = { Text(t("Chapter title", "篇章标题")) }, maxLines = 3,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-chapter-title"))
                OutlinedTextField(words, { value -> words = value; store.editChapterNarration(index, value.text)
                    store.composition(value.composition != null) }, enabled = editable,
                    label = { Text(t("Tell this part in your own words", "用自己的话讲述这一段")) }, minLines = 4, maxLines = 9,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-chapter-words"))
                if (dictationStore == null && store.chapterDictationAvailable) {
                    OutlinedButton(onClick = { finishTyping(); store.openChapterDictation(index) },
                        enabled = editable && !state.composing && !dictationUnfinished,
                        modifier = Modifier.fillMaxWidth().testTag("grouped-story-dictate")) {
                        Text(t("Dictate this chapter", "口述本篇内容"))
                    }
                } else if (dictationStore == null) {
                    Text(t("Chapter dictation is unavailable here. You can keep writing.",
                        "此处暂不能口述本篇内容，可以继续手动填写。"), style = MaterialTheme.typography.bodySmall)
                } else {
                    MemoryDictationInput(
                        store = dictationStore!!, zh = zh,
                        onInsert = { insertRejected = !store.insertChapterTranscript(index, words.composition != null) },
                        purpose = MemoryDictationPurpose.CHAPTER_NARRATION,
                        insertRejected = insertRejected,
                        insertEnabled = words.composition == null,
                        onSessionEnded = { store.closeChapterDictationIfCurrent(dictationStore!!) },
                    )
                    TextButton(onClick = {
                        if (dictationUnfinished) discardDictation = true else store.closeChapterDictation()
                    }, modifier = Modifier.fillMaxWidth()
                        .testTag("grouped-story-dictation-close")) { Text(t("Close dictation", "关闭口述")) }
                }
            }
            if (state.sourceReviewEnabled) {
                Text(t("Evidence used for this chapter", "本篇使用的素材证据"), style = MaterialTheme.typography.titleSmall)
                val options = chapter.assetIds.flatMap { assetId ->
                    draft.items.find { it.asset.id == assetId }?.evidence.orEmpty().map { evidence -> assetId to evidence }
                }.distinctBy { it.second.id }
                if (options.isEmpty()) Text(t("No item evidence is available.", "没有可选的素材证据。"), style = MaterialTheme.typography.bodySmall)
                options.forEach { (assetId, evidence) ->
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(
                        value = evidence.id in chapter.evidenceIds,
                        enabled = editable && !state.composing && !dictationUnfinished,
                        role = Role.Checkbox,
                        onValueChange = { checked -> finishTyping(); store.toggleChapterEvidence(index, evidence.id, checked) }
                    ).testTag("grouped-story-evidence-${chapter.id}-${evidence.id}"), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(evidence.id in chapter.evidenceIds, onCheckedChange = null)
                        Column(Modifier.weight(1f)) {
                            Text(t("Photo/video $assetId · ${if (evidence.source == "family") "Family account" else "AI observation"}",
                                "素材 $assetId · ${if (evidence.source == "family") "家人讲述" else "AI 观察"}"), style = MaterialTheme.typography.labelLarge)
                            Text(evidence.text, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
            key(chapter.id) {
                var showSources by remember { mutableStateOf(false) }
                val sources = chapterSourceReferences(chapter.assetIds, chapter.evidenceIds, draft.items)
                if (sources.isNotEmpty()) {
                    TextButton(onClick = { showSources = !showSources }, modifier = Modifier.fillMaxWidth()) {
                        Text(t("Review sources (${sources.size})", "核对来源（${sources.size}）"))
                    }
                    if (showSources) sources.forEach { source ->
                        val evidence = source.evidence
                        Column(Modifier.fillMaxWidth().testTag("grouped-story-source-${evidence.id}")) {
                            Text(if (evidence.source == "family") t("Family account", "家人讲述") else t("AI observation", "AI 观察"),
                                style = MaterialTheme.typography.labelLarge)
                            if (evidence.title.isNotBlank()) Text(evidence.title, style = MaterialTheme.typography.titleSmall)
                            Text(evidence.text, style = MaterialTheme.typography.bodySmall)
                            ChapterSourceAttribution(evidence, source.originOutsideChapter, zh, "grouped-story-source")
                        }
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                OutlinedButton(onClick = { finishTyping(); store.closeChapterDictation(); chapterIndex-- }, enabled = editable && !state.composing && !dictationUnfinished && index > 0,
                    modifier = Modifier.testTag("grouped-story-previous-chapter")) {
                    Text(t("Previous", "上一篇")) }
                OutlinedButton(onClick = { finishTyping(); store.closeChapterDictation(); chapterIndex++ }, enabled = editable && !state.composing && !dictationUnfinished && index < state.editableChapters.lastIndex,
                    modifier = Modifier.testTag("grouped-story-next-chapter")) {
                    Text(t("Next", "下一篇")) }
            }
            draft.questions.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
            if (state.invalidInput) Text(t("Check the title and shorten any oversized text before saving.",
                "请核对标题并缩短超长文字，再保存。"), color = MaterialTheme.colorScheme.error)
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(state.reviewed,
                enabled = editable && !state.composing && !state.invalidInput && !dictationUnfinished, role = Role.Checkbox,
                onValueChange = { finishTyping(); store.confirmReviewed(it) }).testTag("grouped-story-reviewed"), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(state.reviewed, onCheckedChange = null)
                Text(t("I reviewed these words and sources", "我已核对这些文字与来源"), Modifier.weight(1f))
            }
            Button(onClick = { finishTyping(); store.save() }, enabled = editable && state.reviewed && !state.composing && !state.invalidInput && !dictationUnfinished,
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
                if (savedEditReloading) {
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                    Text(t("Checking the latest saved story and linked family memories. Your conflicted words are being kept until the replacement is verified.",
                        "正在核对最新已保存故事及关联的家人回忆。在替换内容通过核验前，会保留这次冲突中的文字。"),
                        style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("saved-edit-reload-progress"))
                }
                if (savedEditReloadFailed) {
                    Text(t("The latest story or complete chapter links could not be verified. Your conflicted words remain here; retry when ready.",
                        "无法核对最新故事或完整篇章关联。冲突中的文字仍保留在此处，可以重试。"),
                        color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.testTag("saved-edit-reload-error"))
                }
                Button(onClick = {
                    finishTyping()
                    if (isSavedEdit) confirmSavedEditReload = true else store.reloadPreview()
                },
                    enabled = !savedEditReloading && !state.busy && !state.composing && !state.hasPendingSave,
                    modifier = Modifier.fillMaxWidth().testTag("grouped-story-reload-sources")) {
                    Text(if (isSavedEdit && savedEditReloadFailed) t("Retry loading latest story", "重试加载最新故事")
                        else if (isSavedEdit) t("Reload latest saved story", "重新加载最新已保存故事")
                        else t("Reload sources and review", "重新加载来源并核对"))
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
            if (isSavedEdit && state.savedStoryIsNewerThanEditBase) {
                Text(t("The update was confirmed, and a newer family version is now available. Open the current story to review its latest saved chapters.",
                    "修改已确认，现在已有更新的家庭版本。请打开当前故事，核对最新保存的篇章。"),
                    style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("grouped-story-newer-version-notice"))
            }
            Button(onClick = { onReadSaved(saved) }, modifier = Modifier.fillMaxWidth().testTag("grouped-story-read")) {
                Text(if (isSavedEdit) t("Return to updated story", "返回更新后的故事") else t("Read the story", "阅读故事")) }
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
    if (discardDictation) AlertDialog(onDismissRequest = { discardDictation = false },
        title = { Text(t("Discard this dictation?", "丢弃这段口述？")) },
        text = { Text(t("Unadded recording or transcript will be cleared. Your chapter text stays unchanged.",
            "尚未加入的录音或转写将被清除，篇章文字保持不变。")) },
        confirmButton = { TextButton(onClick = { store.closeChapterDictation(); discardDictation = false }) {
            Text(t("Discard and close", "丢弃并关闭")) } },
        dismissButton = { TextButton(onClick = { discardDictation = false }) { Text(t("Keep dictation", "保留口述")) } })
    if (confirmSavedEditReload) AlertDialog(onDismissRequest = { confirmSavedEditReload = false },
        title = { Text(t("Discard these edits and reload?", "丢弃这些修改并重新加载？")) },
        text = { Text(t("Your unsaved words and source choices will be discarded. The latest saved chapters and family memory links will load for a fresh review.",
            "未保存的文字和素材选择将被丢弃。系统会加载最新已保存篇章和家人回忆关联，供你重新核对。")) },
        confirmButton = { TextButton(onClick = {
            confirmSavedEditReload = false
            onReloadSavedEdit?.invoke()
        }, modifier = Modifier.testTag("grouped-story-saved-edit-reload-confirm")) {
            Text(t("Discard and reload", "丢弃并重新加载")) } },
        dismissButton = { TextButton(onClick = { confirmSavedEditReload = false }) { Text(t("Keep editing", "继续编辑")) } })
}
