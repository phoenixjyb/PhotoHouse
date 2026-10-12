package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.MemoryBookCompositionFailure
import dev.photohouse.connected.core.MemoryBookCompositionDictationStore
import dev.photohouse.connected.core.MemoryBookCompositionStatus
import dev.photohouse.connected.core.MemoryBookCompositionStore
import dev.photohouse.connected.core.MemoryBookCompositionStoreState

/** Explicit collector for creating a memoir from saved story snapshots. */
@Composable
internal fun MemoryBookComposerPanel(
    compositionStore: MemoryBookCompositionStore,
    zh: Boolean,
    onClose: () -> Unit,
    onOpenSaved: (bookId: String) -> Unit,
    dictationCoordinator: MemoryBookCompositionDictationStore? = null,
) {
    val state by compositionStore.state.collectAsState()
    val dictationHelper = dictationCoordinator?.state?.collectAsState()?.value
    val dictationState = dictationHelper?.state?.collectAsState()?.value
    val t = { en: String, cn: String -> if (zh) cn else en }
    val scopeId = state.shelfScopeId
    val epoch = state.actionEpoch
    val accountId = state.accountId
    val library = state.library
    val panelAttached = remember(compositionStore, accountId, library, scopeId, epoch) { mutableStateOf(true) }
    val latestState = rememberUpdatedState(state)
    DisposableEffect(compositionStore, accountId, library, scopeId, epoch) {
        panelAttached.value = true
        onDispose { panelAttached.value = false }
    }

    fun actionCurrent(): Boolean {
        val current = latestState.value
        return panelAttached.value && scopeId != null && current.accountId == accountId &&
            current.library == library && current.shelfScopeId == scopeId && current.actionEpoch == epoch
    }

    fun editorCurrent(): Boolean {
        val current = latestState.value
        return actionCurrent() && (current.canCreate || current.canEdit) && !current.busy && !current.pendingRetry && current.status !in setOf(
            MemoryBookCompositionStatus.SAVING, MemoryBookCompositionStatus.RETRY_REQUIRED, MemoryBookCompositionStatus.CREATED, MemoryBookCompositionStatus.SAVED,
        )
    }

    val editingFrozen = state.busy || state.pendingRetry || state.status in setOf(
        MemoryBookCompositionStatus.SAVING, MemoryBookCompositionStatus.RETRY_REQUIRED, MemoryBookCompositionStatus.CREATED, MemoryBookCompositionStatus.SAVED,
    )
    val editingEnabled = (state.canCreate || state.canEdit) && !editingFrozen
    val dictationUnfinished = dictationCoordinator?.hasUnfinishedInput == true
    var introExpanded by remember(accountId, library, scopeId, epoch) { mutableStateOf(false) }
    var advancedExpanded by remember(accountId, library, scopeId, epoch) { mutableStateOf(false) }
    var titleRejected by remember(accountId, library, scopeId, epoch) { mutableStateOf(false) }
    var introRejected by remember(accountId, library, scopeId, epoch) { mutableStateOf(false) }
    var introVoiceNotice by remember(accountId, library, scopeId, epoch) { mutableStateOf<String?>(null) }
    var dictationInsertRejected by remember(accountId, library, scopeId, epoch, dictationHelper) { mutableStateOf(false) }
    var titleValue by remember(accountId, library, scopeId, epoch) {
        mutableStateOf(TextFieldValue(state.title, selection = TextRange(state.title.length)))
    }
    var introValue by remember(accountId, library, scopeId, epoch) {
        mutableStateOf(TextFieldValue(state.introduction, selection = TextRange(state.introduction.length)))
    }
    val latestIntroExpanded = rememberUpdatedState(introExpanded)
    val latestAdvancedExpanded = rememberUpdatedState(advancedExpanded)
    val latestTitleValue = rememberUpdatedState(titleValue)
    val latestIntroValue = rememberUpdatedState(introValue)
    val latestTitleRejected = rememberUpdatedState(titleRejected)
    val latestIntroRejected = rememberUpdatedState(introRejected)
    val latestDictationHelper = rememberUpdatedState(dictationHelper)
    val titleAccepted = titleValue.composition == null && titleValue.text.isNotBlank() &&
        titleValue.text == state.title && !titleRejected
    val introAccepted = introValue.composition == null && introValue.text == state.introduction && !introRejected
    LaunchedEffect(dictationHelper, dictationState?.transcript) {
        if (dictationState?.transcript == null) dictationInsertRejected = false
    }
    LaunchedEffect(state.title, epoch) {
        if (titleValue.composition == null && titleValue.text != state.title) {
            titleValue = TextFieldValue(state.title, selection = TextRange(state.title.length))
            titleRejected = false
        }
    }
    LaunchedEffect(state.introduction, epoch) {
        if (introValue.composition == null && introValue.text != state.introduction) {
            introValue = TextFieldValue(state.introduction, selection = TextRange(state.introduction.length))
            introRejected = false
        }
    }

    Surface(color = MaterialTheme.colorScheme.surface, shape = MaterialTheme.shapes.large,
        modifier = Modifier.fillMaxWidth().testTag("memory-book-compose")) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(if (state.editingBookId != null) t("Edit family memoir", "编辑家庭回忆册") else t("Create a family memoir", "创建家庭回忆册"), style = MaterialTheme.typography.headlineSmall)
                    Text(t("Choose saved stories to bring together.", "选择已保存的家庭故事，汇集成册。"),
                        style = MaterialTheme.typography.bodyMedium)
                }
                TextButton(onClick = attachedComposerAction({ if (actionCurrent()) onClose() }), modifier = Modifier.testTag("memory-book-compose-close")) {
                    Text(t("Close", "关闭"))
                }
            }
            Text(t(
                "This collects existing saved stories into a memoir. It does not rewrite those stories or generate new story content.",
                "这会把已保存的故事汇集成册，不会改写这些故事，也不会生成新的故事内容。",
            ), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

            if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(compositionStatus(state, zh), style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.fillMaxWidth().testTag("memory-book-compose-status")
                    .semantics { liveRegion = LiveRegionMode.Polite })
            state.failure?.let { failure ->
                Text(compositionFailure(failure, zh), color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.fillMaxWidth().testTag("memory-book-compose-failure")
                        .semantics { liveRegion = LiveRegionMode.Polite })
            }
            if (state.failure != null && state.failure != MemoryBookCompositionFailure.BOOK_CHANGED && !state.busy && !state.pendingRetry &&
                state.status !in setOf(MemoryBookCompositionStatus.CLOSED, MemoryBookCompositionStatus.CREATED, MemoryBookCompositionStatus.SAVED)) {
                val failedPage = state.candidatePage
                OutlinedButton(onClick = attachedComposerAction({
                    if (actionCurrent() && scopeId != null && !latestState.value.busy) {
                        if (failedPage == null) compositionStore.retryOpen(scopeId, epoch)
                        else if (latestState.value.candidatePage?.page == failedPage.page)
                            compositionStore.loadPage(failedPage.page, scopeId, epoch)
                    }
                }), enabled = !state.busy, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                    .testTag("memory-book-compose-retry-load")) {
                    Text(t("Retry loading saved stories", "重试读取已保存的故事"))
                }
            }

            OutlinedTextField(
                value = titleValue,
                onValueChange = { value ->
                    if (editorCurrent()) titleValue = value
                    if (editorCurrent() && scopeId != null) titleRejected = !compositionStore.updateTitle(value.text, scopeId, epoch)
                },
                enabled = editingEnabled,
                singleLine = true,
                label = { Text(t("Memoir title", "回忆册标题")) },
                supportingText = if (titleRejected) ({
                    Text(t("The title is too long. Shorten it before saving.", "标题过长，请缩短后再保存。"))
                }) else null,
                isError = titleRejected,
                modifier = Modifier.fillMaxWidth().testTag("memory-book-compose-title"),
            )

            OutlinedButton(onClick = attachedComposerAction({
                if (latestDictationHelper.value == null) introExpanded = !introExpanded
            }, enabled = editingEnabled && dictationHelper == null), enabled = editingEnabled && dictationHelper == null,
                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("memory-book-compose-intro-toggle")) {
                Text(if (introExpanded) t("Hide optional introduction", "收起可选简介")
                    else if (state.introduction.isNotBlank()) t("Edit introduction", "编辑简介")
                    else t("Add an optional introduction", "添加可选简介"))
            }
            if (introExpanded) {
                if (dictationCoordinator != null && dictationHelper == null) {
                    OutlinedButton(onClick = attachedComposerAction({
                        val current = latestState.value
                        val currentIntro = latestIntroValue.value
                        if (!editorCurrent() || currentIntro.composition != null ||
                            currentIntro.text != current.introduction || latestIntroRejected.value) {
                            introVoiceNotice = t(
                                "Finish applying your current introduction edits before opening voice input.",
                                "请先完成当前简介编辑，再打开语音输入。",
                            )
                        } else if (actionCurrent() && latestDictationHelper.value == null) {
                            introVoiceNotice = null
                            if (dictationCoordinator.open() == null) {
                                introVoiceNotice = t("Voice is unavailable for this memoir session.",
                                    "当前回忆册会话无法使用语音输入。")
                            }
                        }
                    }, enabled = editingEnabled), enabled = editingEnabled,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("memory-book-compose-intro-dictate")) {
                        Text(t("Dictate introduction", "口述简介"))
                    }
                }
                introVoiceNotice?.let { notice ->
                    Text(notice, color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.fillMaxWidth().testTag("memory-book-compose-intro-voice-notice")
                            .semantics { liveRegion = LiveRegionMode.Polite })
                }
                dictationHelper?.let { helper ->
                    val unfinished = dictationState?.let {
                        it.loading || it.recording || it.transcribing || it.transcript != null
                    } == true
                    MemoryDictationInput(
                        store = helper,
                        zh = zh,
                        purpose = MemoryDictationPurpose.MEMOIR_INTRODUCTION,
                        insertEnabled = introValue.composition == null && introValue.text == state.introduction && !introRejected,
                        insertRejected = dictationInsertRejected,
                        onInsert = {
                            if (scopeId != null) dictationCoordinator?.insertTranscript(helper) { transcript ->
                                val current = latestState.value
                                val currentIntro = latestIntroValue.value
                                if (!actionCurrent() || !editorCurrent() || latestDictationHelper.value !== helper ||
                                    currentIntro.composition != null || currentIntro.text != current.introduction ||
                                    latestIntroRejected.value) {
                                    false
                                } else {
                                    val combined = if (currentIntro.text.isEmpty()) transcript
                                        else currentIntro.text + "\n" + transcript
                                    if (!compositionStore.updateIntroduction(combined, scopeId, epoch)) {
                                        dictationInsertRejected = true
                                        false
                                    } else {
                                        introValue = TextFieldValue(combined, selection = TextRange(combined.length))
                                        introRejected = false
                                        dictationInsertRejected = false
                                        true
                                    }
                                }
                            }
                        },
                        onSessionEnded = { dictationCoordinator?.clearIfCurrent(helper) },
                    )
                    OutlinedButton(onClick = attachedComposerAction({
                        if (actionCurrent() && latestDictationHelper.value === helper) {
                            dictationCoordinator?.clearIfCurrent(helper)
                            dictationInsertRejected = false
                            introVoiceNotice = null
                        }
                    }),
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                            .testTag("memory-book-compose-intro-voice-close")) {
                        Text(if (unfinished) t("Discard voice input", "放弃语音输入")
                            else t("Close voice input", "关闭语音输入"))
                    }
                }
                OutlinedTextField(
                    value = introValue,
                    onValueChange = { value ->
                        if (latestIntroExpanded.value && editorCurrent()) introValue = value
                        if (latestIntroExpanded.value && editorCurrent() && scopeId != null)
                            introRejected = !compositionStore.updateIntroduction(value.text, scopeId, epoch)
                    },
                    enabled = editingEnabled,
                    minLines = 2,
                    maxLines = 5,
                    label = { Text(t("Introduction (optional)", "简介（可选）")) },
                    supportingText = if (introRejected) ({
                        Text(t("The introduction is too long. Shorten it before saving.", "简介过长，请缩短后再保存。"))
                    }) else null,
                    isError = introRejected,
                    modifier = Modifier.fillMaxWidth().testTag("memory-book-compose-intro"),
                )
            }

            OutlinedButton(onClick = attachedComposerAction({ advancedExpanded = !advancedExpanded }, enabled = editingEnabled), enabled = editingEnabled,
                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("memory-book-compose-advanced-toggle")) {
                Text(if (advancedExpanded) t("Hide language options", "收起语言选项") else t("Language options", "语言选项"))
            }
            if (advancedExpanded) {
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(t("Memoir language", "回忆册语言"), style = MaterialTheme.typography.titleSmall)
                    listOf("zh" to t("Chinese", "中文"), "en" to t("English", "英语")).forEach { (code, label) ->
                        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp)
                            .toggleable(value = state.language == code, role = Role.RadioButton, enabled = editingEnabled) {
                                if (latestAdvancedExpanded.value && actionCurrent() && scopeId != null)
                                    compositionStore.updateLanguage(code, scopeId, epoch)
                            }, verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = state.language == code, onClick = null, enabled = editingEnabled)
                            Text(label, style = MaterialTheme.typography.bodyLarge)
                        }
                    }
                }
            }

            HorizontalDivider()
            val selectedIds = state.selectedStories.map { it.summary.id }
            Text(t("Selected stories · ${selectedIds.size}/24", "已选故事 · ${selectedIds.size}/24"),
                style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("memory-book-compose-selected-count"))
            if (selectedIds.size >= MemoryBookCompositionStore.MAX_STORIES) Text(
                t("A memoir can include up to 24 saved stories.", "一本回忆册最多可汇集 24 个已保存故事。"),
                style = MaterialTheme.typography.bodySmall,
            )
            if (state.selectedStories.isEmpty()) Text(t("Choose at least one saved story to create a memoir.", "请至少选择一个已保存的故事。"),
                style = MaterialTheme.typography.bodySmall)
            state.selectedStories.forEachIndexed { index, selected ->
                val story = selected.summary
                val renderedIds = selectedIds.toList()
                val renderedRevision = state.draftRevision
                Column(Modifier.fillMaxWidth().testTag("memory-book-compose-selected-${story.id}"),
                    verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(t("${index + 1}. ${story.title}", "${index + 1}. ${story.title}"),
                        style = MaterialTheme.typography.titleSmall)
                    Text(t("${story.chapterCount} chapters · ${story.itemCount} moments", "${story.chapterCount} 篇章 · ${story.itemCount} 个片段"),
                        style = MaterialTheme.typography.bodySmall)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = attachedComposerAction({
                            if (actionCurrent() && scopeId != null && index > 0) {
                                compositionStore.reorderStories(renderedIds, renderedIds.toMutableList().also {
                                    val value = it.removeAt(index); it.add(index - 1, value)
                                }, scopeId, epoch)
                            }
                        }, enabled = editingEnabled && index > 0), enabled = editingEnabled && index > 0,
                            modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("memory-book-compose-up-${story.id}")
                                .semantics { contentDescription = t("Move ${story.title} up", "上移${story.title}") }) {
                            Text(t("Move up", "上移"))
                        }
                        OutlinedButton(onClick = attachedComposerAction({
                            if (actionCurrent() && scopeId != null && index < renderedIds.lastIndex) {
                                compositionStore.reorderStories(renderedIds, renderedIds.toMutableList().also {
                                    val value = it.removeAt(index); it.add(index + 1, value)
                                }, scopeId, epoch)
                            }
                        }, enabled = editingEnabled && index < renderedIds.lastIndex), enabled = editingEnabled && index < renderedIds.lastIndex,
                            modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("memory-book-compose-down-${story.id}")
                                .semantics { contentDescription = t("Move ${story.title} down", "下移${story.title}") }) {
                            Text(t("Move down", "下移"))
                        }
                    }
                    OutlinedButton(onClick = attachedComposerAction({
                        val current = latestState.value
                        if (actionCurrent() && scopeId != null && current.draftRevision == renderedRevision &&
                            current.selectedStories.map { it.summary.id } == renderedIds &&
                            current.selectedStories.getOrNull(index)?.let { it.summary.id == story.id && it.summary.revision == story.revision } == true) {
                            compositionStore.toggleStory(story.id, story.revision, scopeId, epoch)
                        }
                    }, enabled = editingEnabled), enabled = editingEnabled,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("memory-book-compose-remove-${story.id}")
                            .semantics { contentDescription = t("Remove ${story.title} from this memoir", "从本册移除${story.title}") }) {
                        Text(t("Remove from memoir", "从本册移除"))
                    }
                }
                HorizontalDivider()
            }

            val page = state.candidatePage
            if (page != null) {
                Text(t("Saved stories · page ${page.page}", "已保存的故事 · 第 ${page.page} 页"),
                    style = MaterialTheme.typography.titleMedium)
                if (page.items.isEmpty()) Text(t("No saved stories are available in this library yet.", "这个家庭库中还没有可选的已保存故事。"),
                    style = MaterialTheme.typography.bodySmall)
                page.items.forEach { story ->
                    val selected = story.id in selectedIds
                    val canSelect = selected || selectedIds.size < MemoryBookCompositionStore.MAX_STORIES
                    val renderedDraftRevision = state.draftRevision
                    val toggleAction = attachedComposerAction({
                        val current = latestState.value
                        val visibleStory = current.candidatePage?.items?.firstOrNull { it.id == story.id }
                        if (actionCurrent() && scopeId != null && !current.busy &&
                            current.draftRevision == renderedDraftRevision && current.candidatePage?.page == page.page &&
                            visibleStory?.revision == story.revision) {
                            compositionStore.toggleStory(story.id, story.revision, scopeId, epoch)
                        }
                    }, enabled = editingEnabled && canSelect)
                    Row(Modifier.fillMaxWidth().heightIn(min = 64.dp)
                        .toggleable(value = selected, role = Role.Checkbox, enabled = editingEnabled && canSelect) { toggleAction() }
                        .testTag("memory-book-compose-story-${story.id}"), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = selected, onCheckedChange = null, enabled = editingEnabled && canSelect)
                        Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
                            Text(story.title, style = MaterialTheme.typography.titleSmall)
                            Text(t("${story.chapterCount} chapters · ${story.itemCount} moments · ${story.language}",
                                "${story.chapterCount} 篇章 · ${story.itemCount} 个片段 · ${if (story.language == "zh") "中文" else "英语"}"),
                                style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = attachedComposerAction({
                        if (actionCurrent() && scopeId != null && !latestState.value.busy &&
                            latestState.value.candidatePage?.page == page.page && page.page > 1)
                            compositionStore.loadPage(page.page - 1, scopeId, epoch)
                    }, enabled = !editingFrozen && !state.busy && page.page > 1), enabled = !editingFrozen && !state.busy && page.page > 1,
                        modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("memory-book-compose-previous")) {
                        Text(t("Previous page", "上一页"))
                    }
                    OutlinedButton(onClick = attachedComposerAction({
                        if (actionCurrent() && scopeId != null && !latestState.value.busy &&
                            latestState.value.candidatePage?.page == page.page && page.hasMore && page.page < 100000)
                            compositionStore.loadPage(page.page + 1, scopeId, epoch)
                    }, enabled = !editingFrozen && !state.busy && page.hasMore && page.page < 100000),
                        enabled = !editingFrozen && !state.busy && page.hasMore && page.page < 100000,
                        modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("memory-book-compose-next")) {
                        Text(t("Next page", "下一页"))
                    }
                }
            }

            val renderedDraftRevision = state.draftRevision
            val canSaveText = titleAccepted && introAccepted && !dictationUnfinished &&
                (state.editingBookId == null || state.hasChanges)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = attachedComposerAction({
                    val current = latestState.value
                    val currentTitle = latestTitleValue.value
                    val currentIntro = latestIntroValue.value
                    val editorsAccepted = currentTitle.composition == null && currentTitle.text.isNotBlank() &&
                        currentTitle.text == current.title && currentIntro.composition == null &&
                        currentIntro.text == current.introduction && !latestTitleRejected.value && !latestIntroRejected.value
                    if (actionCurrent() && scopeId != null && (current.canCreate || current.canEdit) && !current.busy && !current.pendingRetry &&
                        dictationCoordinator?.hasUnfinishedInput != true &&
                        current.status == MemoryBookCompositionStatus.READY && current.selectedStories.isNotEmpty() && editorsAccepted &&
                        (current.editingBookId == null || current.hasChanges) &&
                        current.draftRevision == renderedDraftRevision)
                        compositionStore.save(scopeId, epoch, renderedDraftRevision)
                }, enabled = actionCurrent() && (state.canCreate || state.canEdit) && !state.busy && !state.pendingRetry && canSaveText &&
                    state.status == MemoryBookCompositionStatus.READY && state.selectedStories.isNotEmpty()),
                    enabled = actionCurrent() && (state.canCreate || state.canEdit) && !state.busy && !state.pendingRetry && canSaveText &&
                    state.status == MemoryBookCompositionStatus.READY && state.selectedStories.isNotEmpty(),
                    modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("memory-book-compose-save")) {
                    Text(if (state.editingBookId != null) t("Save changes", "保存修改") else t("Save memoir", "保存回忆册"))
                }
                if (state.pendingRetry || state.status == MemoryBookCompositionStatus.RETRY_REQUIRED) {
                    OutlinedButton(onClick = attachedComposerAction({
                        if (actionCurrent() && scopeId != null) compositionStore.retry(scopeId, epoch)
                    }, enabled = actionCurrent() && !state.busy && state.pendingRetry), enabled = actionCurrent() && !state.busy && state.pendingRetry,
                        modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("memory-book-compose-retry")) {
                        Text(t("Retry same save", "重试保存"))
                    }
                }
            }

            state.createdBook?.let { book ->
                Text(t("Your memoir is saved. Open it to read the collected stories.", "回忆册已保存。打开后即可阅读汇集的故事。"),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite })
                Button(onClick = attachedComposerAction({ if (actionCurrent()) onOpenSaved(book.id) }, enabled = actionCurrent()), enabled = actionCurrent(),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("memory-book-compose-open-saved")) {
                    Text(t("Open saved memoir", "打开已保存的回忆册"))
                }
            }
        }
    }
}

private fun compositionStatus(state: MemoryBookCompositionStoreState, zh: Boolean): String {
    val t = { en: String, cn: String -> if (zh) cn else en }
    if (state.busy && state.status == MemoryBookCompositionStatus.LOADING)
        return t("Loading saved stories…", "正在读取已保存的故事…")
    if (state.busy && state.status == MemoryBookCompositionStatus.SAVING)
        return t("Checking selected stories and saving this memoir…", "正在核对所选故事并保存回忆册…")
    return when (state.status) {
        MemoryBookCompositionStatus.CLOSED -> t("Composer is unavailable for this account or library.", "当前账户或家庭库无法创建回忆册。")
        MemoryBookCompositionStatus.LOADING -> t("Loading saved stories…", "正在读取已保存的故事…")
        MemoryBookCompositionStatus.READY -> t("Review the selected order, title, and language before saving.", "保存前请核对故事顺序、标题和语言。")
        MemoryBookCompositionStatus.SAVING -> t("Checking selected stories and saving this memoir…", "正在核对所选故事并保存回忆册…")
        MemoryBookCompositionStatus.RETRY_REQUIRED -> t("The save result is uncertain. Retry the same save to check it safely.", "保存结果尚不确定。请重试同一项保存以安全核对。")
        MemoryBookCompositionStatus.CREATED -> t("Memoir saved.", "回忆册已保存。")
        MemoryBookCompositionStatus.SAVED -> t("Memoir changes saved.", "回忆册修改已保存。")
    }
}

private class ComposerActionLease(var attached: Boolean = false)

@Composable
private fun attachedComposerAction(action: () -> Unit, enabled: Boolean = true): () -> Unit {
    val currentlyEnabled by rememberUpdatedState(enabled)
    val lease = remember(action) { ComposerActionLease() }
    DisposableEffect(lease) {
        lease.attached = true
        onDispose { lease.attached = false }
    }
    return remember(lease, action) { { if (lease.attached && currentlyEnabled) action() } }
}

private fun compositionFailure(failure: MemoryBookCompositionFailure, zh: Boolean): String = when (failure) {
    MemoryBookCompositionFailure.NETWORK -> if (zh) "网络暂时不可用。你的选择仍已保留。" else "The network is unavailable. Your selections are kept."
    MemoryBookCompositionFailure.TLS -> if (zh) "无法验证服务器的安全连接。你的选择仍已保留。" else "The server’s secure connection could not be verified. Your selections are kept."
    MemoryBookCompositionFailure.SERVICE_UNAVAILABLE -> if (zh) "服务暂时不可用。你的选择仍已保留。" else "The service is temporarily unavailable. Your selections are kept."
    MemoryBookCompositionFailure.RATE_LIMITED -> if (zh) "操作过于频繁，请稍后再试。你的选择仍已保留。" else "Too many attempts. Wait before trying again. Your selections are kept."
    MemoryBookCompositionFailure.ACCESS_DENIED -> if (zh) "此家庭库的访问权限已变化。" else "Access to this family library has changed."
    MemoryBookCompositionFailure.SCOPE_CHANGED -> if (zh) "账户或家庭库已变化，请重新打开回忆册创建器。" else "The account or library changed. Reopen the memoir composer."
    MemoryBookCompositionFailure.NOT_ALLOWED -> if (zh) "当前账户没有保存此回忆册的权限。" else "This account cannot save this memoir."
    MemoryBookCompositionFailure.INVALID_STORY -> if (zh) "所选故事已不可用。你的其他选择仍已保留。" else "A selected story is no longer available. Your other choices are kept."
    MemoryBookCompositionFailure.STORY_CHANGED -> if (zh) "故事内容或来源已变化。请重新选择并核对。" else "A story or its sources changed. Select it again and review the list."
    MemoryBookCompositionFailure.BOOK_CHANGED -> if (zh) "回忆册或编辑权限已变化。你的草稿仍已保留；关闭后重新打开，核对最新内容。" else "This memoir or its edit permission changed. Your draft is kept; close and reopen to review the latest version."
    MemoryBookCompositionFailure.INVALID_INPUT -> if (zh) "请检查标题、简介和所选故事。" else "Check the title, introduction, and selected stories."
    MemoryBookCompositionFailure.INVALID_RESPONSE -> if (zh) "服务器返回的回忆册无法确认。" else "The saved memoir could not be confirmed from the server response."
    MemoryBookCompositionFailure.UNKNOWN -> if (zh) "无法完成此操作。你的内容仍已保留。" else "This action could not be completed. Your content is kept."
}
