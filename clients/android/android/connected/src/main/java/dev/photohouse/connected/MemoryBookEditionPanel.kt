package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*

/** Review is a separate surface: completing a suggestion never saves an edition. */
@Composable
internal fun MemoryBookEditionPanel(store: ConnectedStore, reading: MemoryBooksReading, zh: Boolean, enabled: Boolean) {
    if (!store.memoryBookEditionAvailable) return
    val book = reading.selectedBook ?: return
    val live by store.state.collectAsState()
    val state by store.memoryBookEditionState.collectAsState()
    val narrative by store.memoryBookNarrativeState.collectAsState()
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    fun t(en: String, cn: String) = if (zh) cn else en
    fun finishTyping() { focus.clearFocus(); keyboard?.hide() }
    val reviewScope = listOf(live.session?.account_id, live.generation, reading.library, book.id, book.revision,
        state.proposal?.jobId, state.receipt?.id)
    var discard by remember(reviewScope) { mutableStateOf(false) }
    var reload by remember(reviewScope) { mutableStateOf(false) }
    var selected by remember(reviewScope) { mutableIntStateOf(0) }
    if (state.status == MemoryBookEditionStatus.IDLE) {
        if (book.canEdit && narrative.job?.state == "ready" && narrative.proposal != null) {
            OutlinedButton(onClick = { finishTyping(); store.openMemoryBookEditionReview() }, enabled = enabled,
                modifier = Modifier.fillMaxWidth().testTag("memory-edition-open")) {
                Text(t("Review and save this memoir", "审阅并保存整本回忆录"))
            }
        }
        return
    }
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = MaterialTheme.shapes.large,
        modifier = Modifier.fillMaxWidth().testTag("memory-edition-panel")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(t("A family-reviewed edition", "家人核对的回忆录版本"), style = MaterialTheme.typography.titleLarge,
                fontFamily = FontFamily.Serif)
            Text(editionStatus(state.status, zh), modifier = Modifier.testTag("memory-edition-status")
                .semantics { liveRegion = LiveRegionMode.Polite })
            if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            val draft = state.manuscript
            val editable = !state.busy && !state.hasPendingSave && state.receipt == null &&
                state.status in setOf(MemoryBookEditionStatus.REVIEW, MemoryBookEditionStatus.INVALID)
            if (draft != null && state.receipt == null) {
                Text(t("Check each chapter and its sources. Stories, original words and recordings stay separate.",
                    "逐章核对文字与来源。原故事、原话和录音会分别保留。"), style = MaterialTheme.typography.bodySmall)
                var title by remember(reviewScope) { mutableStateOf(TextFieldValue(draft.title)) }
                var titleRejected by remember(reviewScope) { mutableStateOf(false) }
                var chapterRejected by remember(reviewScope) { mutableStateOf(false) }
                LaunchedEffect(draft.title) {
                    if (!titleRejected && title.composition == null && title.text != draft.title) title = TextFieldValue(draft.title)
                }
                OutlinedTextField(title, { value ->
                    title = value
                    titleRejected = !store.editMemoryBookEditionTitle(value.text)
                    store.markMemoryBookEditionInvalidInput(titleRejected || chapterRejected)
                    store.composeMemoryBookEdition(value.composition != null)
                }, enabled = editable, label = { Text(t("Edition title", "版本标题")) }, maxLines = 3, isError = titleRejected,
                    modifier = Modifier.fillMaxWidth().testTag("memory-edition-title"))
                val index = selected.coerceIn(draft.chapters.indices)
                val chapter = draft.chapters[index]
                Text(t("Chapter ${index + 1} of ${draft.chapters.size}", "篇章 ${index + 1}/${draft.chapters.size}"),
                    style = MaterialTheme.typography.labelLarge, modifier = Modifier.testTag("memory-edition-position"))
                val story = book.stories.find { chapter.id.startsWith(it.id + "-chapter-") }
                Text(story?.title.orEmpty(), style = MaterialTheme.typography.titleMedium)
                key(chapter.id) {
                    var words by remember { mutableStateOf(TextFieldValue(chapter.narration, selection = TextRange(chapter.narration.length))) }
                    LaunchedEffect(chapter.narration) {
                        if (!chapterRejected && words.composition == null && words.text != chapter.narration) words = TextFieldValue(chapter.narration)
                    }
                    OutlinedTextField(words, { value ->
                        words = value
                        chapterRejected = !store.editMemoryBookEditionChapter(index, value.text)
                        store.markMemoryBookEditionInvalidInput(titleRejected || chapterRejected)
                        store.composeMemoryBookEdition(value.composition != null)
                    }, enabled = editable, label = { Text(t("Review chapter text", "核对篇章文字")) }, minLines = 3, maxLines = 8,
                        isError = chapterRejected, modifier = Modifier.fillMaxWidth().testTag("memory-edition-chapter"))
                    if (chapterRejected || titleRejected) Text(t("Shorten the text or correct the input before saving.",
                        "请缩短文字或修正输入后再保存。"), color = MaterialTheme.colorScheme.error)
                    Text(t("${chapter.sourceIds.size} references · check the original accounts before saving.",
                        "${chapter.sourceIds.size} 条引用 · 保存前请核对原始讲述。"), style = MaterialTheme.typography.bodySmall)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        OutlinedButton(onClick = { finishTyping(); selected-- },
                            enabled = !state.busy && !state.composing && !state.invalidInput && !chapterRejected && !titleRejected && index > 0,
                            modifier = Modifier.testTag("memory-edition-previous")) { Text(t("Previous", "上一篇")) }
                        OutlinedButton(onClick = { finishTyping(); selected++ },
                            enabled = !state.busy && !state.composing && !state.invalidInput && !chapterRejected && !titleRejected && index < draft.chapters.lastIndex,
                            modifier = Modifier.testTag("memory-edition-next")) { Text(t("Next", "下一篇")) }
                    }
                    draft.questions.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(state.reviewed,
                        enabled = editable && !state.composing && !state.invalidInput && !chapterRejected && !titleRejected, role = Role.Checkbox,
                        onValueChange = { finishTyping(); store.reviewMemoryBookEdition(it) })
                        .testTag("memory-edition-reviewed"), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Checkbox(state.reviewed, null)
                        Text(t("I have checked the chapters, sources and uncertain details", "我已核对各篇章、来源和不确定之处"))
                    }
                    if (state.status == MemoryBookEditionStatus.SAVE_UNCERTAIN) {
                        Button(onClick = { store.retryMemoryBookEditionSave() }, enabled = !state.busy,
                            modifier = Modifier.fillMaxWidth().testTag("memory-edition-retry")) {
                            Text(t("Retry the same manuscript save", "用同一份稿件重试保存"))
                        }
                    } else if (!state.hasPendingSave) {
                        Button(onClick = { finishTyping(); store.saveMemoryBookEdition() },
                            enabled = editable && state.reviewed && !state.composing && !state.invalidInput && !chapterRejected && !titleRejected,
                            modifier = Modifier.fillMaxWidth().testTag("memory-edition-save")) {
                            Text(t("Explicitly save this edition", "明确保存这个版本"))
                        }
                    }
                }
            }
            if (state.receipt != null) {
                OutlinedButton(onClick = { store.readMemoryBookEdition() }, enabled = !state.busy,
                    modifier = Modifier.fillMaxWidth().testTag("memory-edition-read")) {
                    Text(t("Read the saved edition again", "重新读取已保存版本"))
                }
                draft?.let { manuscript ->
                    Text(manuscript.title, fontFamily = FontFamily.Serif, style = MaterialTheme.typography.titleLarge)
                    val index = selected.coerceIn(manuscript.chapters.indices)
                    val chapter = manuscript.chapters[index]
                    Text(t("Chapter ${index + 1} of ${manuscript.chapters.size}", "篇章 ${index + 1}/${manuscript.chapters.size}"))
                    Text(chapter.narration, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.testTag("memory-edition-prose"))
                    ChapterReadAloud(chapter.narration, book.language,
                        listOf("saved-edition", live.session?.account_id, live.generation, reading.library, book.id,
                            book.revision, state.receipt?.id, chapter.id, chapter.narration), zh, enabled = !state.busy)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        TextButton(onClick = { selected-- }, enabled = index > 0) { Text(t("Previous", "上一篇")) }
                        TextButton(onClick = { selected++ }, enabled = index < manuscript.chapters.lastIndex) { Text(t("Next", "下一篇")) }
                    }
                }
            }
            if (state.status == MemoryBookEditionStatus.UNAVAILABLE || state.status == MemoryBookEditionStatus.CONFLICT) {
                OutlinedButton(onClick = { if (state.hasUnfinishedWork) { reload = true; discard = true }
                    else store.openMemoryBookEditionReview() }, enabled = !state.busy && !state.composing,
                    modifier = Modifier.fillMaxWidth().testTag("memory-edition-reload")) {
                    Text(t("Check the current proposal again", "重新核对当前整理稿"))
                }
            }
            TextButton(onClick = { finishTyping(); if (!store.closeMemoryBookEditionReview()) { reload = false; discard = true } },
                enabled = !state.busy && !state.composing && (!state.hasPendingSave || state.status == MemoryBookEditionStatus.CONFLICT),
                modifier = Modifier.testTag("memory-edition-close")) { Text(t("Close review", "关闭版本核对")) }
        }
    }
    if (discard) AlertDialog(onDismissRequest = { discard = false },
        title = { Text(t("Unsaved edition edits", "尚未保存的版本改动")) },
        text = { Text(t("Discard these local edits? Family originals stay unchanged.", "放弃这些本地改动吗？家人的原始记录保持原样。")) },
        confirmButton = { TextButton(onClick = { discard = false; if (store.closeMemoryBookEditionReview(true) && reload)
            store.openMemoryBookEditionReview() }, modifier = Modifier.testTag("memory-edition-discard-confirm")) { Text(t("Discard", "放弃改动")) } },
        dismissButton = { TextButton(onClick = { discard = false }, modifier = Modifier.testTag("memory-edition-discard-cancel")) { Text(t("Keep editing", "继续编辑")) } })
}

private fun editionStatus(status: MemoryBookEditionStatus, zh: Boolean): String {
    val words = when (status) {
        MemoryBookEditionStatus.IDLE -> "" to ""
        MemoryBookEditionStatus.CHECKING -> "Checking the proposal and current sources…" to "正在核对整理稿与当前来源…"
        MemoryBookEditionStatus.REVIEW -> "AI draft · review before saving" to "AI 整理稿 · 核对后再保存"
        MemoryBookEditionStatus.INVALID -> "Check the title, text length and review confirmation." to "请检查标题、文字长度和核对确认。"
        MemoryBookEditionStatus.SAVING -> "Saving this reviewed edition…" to "正在保存已核对的版本…"
        MemoryBookEditionStatus.SAVE_UNCERTAIN -> "The result is uncertain. Your manuscript is frozen; retry uses the same content." to "保存结果尚未确认。稿件已保留，重试使用同一份内容。"
        MemoryBookEditionStatus.CONFLICT -> "The proposal or its sources changed. Your words are kept; review again." to "整理稿或来源已变化。文字已保留，请重新核对。"
        MemoryBookEditionStatus.SAVED -> "The family edition is saved." to "家庭版本已保存。"
        MemoryBookEditionStatus.READING -> "Reading the currently authorized edition…" to "正在重新读取当前可访问的版本…"
        MemoryBookEditionStatus.SOURCE_CHANGED -> "The sources changed or were deleted. Manuscript text is hidden." to "来源已变化或被删除，整理文字已隐藏。"
        MemoryBookEditionStatus.READ_UNAVAILABLE -> "The edition cannot be confirmed now. Previous text has been cleared." to "暂时无法确认此版本，已清除先前显示的文字。"
        MemoryBookEditionStatus.UNAVAILABLE -> "Edition saving is not available here. Original stories remain readable." to "此处暂未开放版本保存，原故事仍可阅读。"
    }
    return if (zh) words.second else words.first
}
