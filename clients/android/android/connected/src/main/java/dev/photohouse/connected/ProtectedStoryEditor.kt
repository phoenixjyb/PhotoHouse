package dev.photohouse.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.ProtectedStoryEditorStore
import dev.photohouse.connected.core.StoryEditorPhase

/** Full-window, review-before-save editor. The parent supplies all authorization and scope. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun ProtectedStoryEditorDialog(
    store: ProtectedStoryEditorStore,
    onDismiss: () -> Unit,
    zh: Boolean = false,
) {
    val state by store.state.collectAsState()
    val speech = store.dictation?.state?.collectAsState()?.value
    val speechPending = speech?.let { it.recording || it.transcribing || it.transcript != null } == true
    val editable = state.phase == StoryEditorPhase.EDITING
    fun label(en: String, cn: String) = if (zh) cn else en
    var clock by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(state.phase, state.retryAtMillis) {
        while (state.phase == StoryEditorPhase.UNCERTAIN && clock < state.retryAtMillis) {
            kotlinx.coroutines.delay(250)
            clock = System.currentTimeMillis()
        }
    }
    Dialog(
        onDismissRequest = { store.close(); onDismiss() },
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnBackPress = true, dismissOnClickOutside = false),
    ) {
        PhotoHouseTheme {
            Surface(Modifier.fillMaxSize().safeDrawingPadding().imePadding().testTag("protected-story-editor")) {
                Column(
                    Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text(
                        if (state.phase == StoryEditorPhase.REVIEW || state.phase == StoryEditorPhase.SAVING) label("Review memory", "检查回忆")
                        else label("Family memory", "家人回忆"),
                        style = MaterialTheme.typography.headlineSmall,
                    )
                    Text(label("Attached to this photo or video", "已附加到此照片或视频"), style = MaterialTheme.typography.bodyMedium)
                    HorizontalDivider()
                    if (editable) {
                    Text(label("Your draft stays here until you confirm. Leaving the app discards unsaved text.", "确认后才会保存，离开应用将清除未保存的文字。"), style = MaterialTheme.typography.bodySmall)
                    store.dictation?.let { dictation ->
                        MemoryDictationInput(dictation, zh, onInsert = { store.insertDictation() })
                    }
                    OutlinedTextField(
                        value = state.draft.title,
                        onValueChange = store::updateTitle,
                        enabled = editable,
                        label = { Text(label("Title (optional)", "标题（可选）")) },
                        modifier = Modifier.fillMaxWidth().testTag("story-editor-title"),
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                    )
                    OutlinedTextField(
                        value = state.draft.byline,
                        onValueChange = store::updateByline,
                        enabled = editable,
                        label = { Text(label("Byline (optional)", "署名（可选）")) },
                        modifier = Modifier.fillMaxWidth().testTag("story-editor-byline"),
                        singleLine = true,
                    )
                    Text(label("Language", "语言"), style = MaterialTheme.typography.labelLarge)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf("en" to label("English", "英语"), "zh" to label("Chinese", "中文"), "mixed" to label("Mixed", "中英混合"), "und" to label("Unspecified", "未指定")).forEach { (wire, languageLabel) ->
                            FilterChip(selected = state.draft.language == wire, onClick = { store.updateLanguage(wire) }, enabled = editable, label = { Text(languageLabel) })
                        }
                    }
                    OutlinedTextField(
                        value = state.draft.text,
                        onValueChange = store::updateText,
                        enabled = editable,
                        label = { Text(label("Memory", "回忆")) },
                        minLines = 8,
                        maxLines = 8,
                        modifier = Modifier.fillMaxWidth().testTag("story-editor-text"),
                    )
                    } else if (state.phase != StoryEditorPhase.SAVED && state.phase != StoryEditorPhase.DENIED && state.phase != StoryEditorPhase.CLOSED) {
                        Text(state.draft.title, style = MaterialTheme.typography.titleLarge)
                        Text(state.draft.byline, style = MaterialTheme.typography.labelLarge)
                        MemoryParagraphs(state.draft.text)
                    }
                    state.message?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("story-editor-status")) }
                    when (state.phase) {
                        StoryEditorPhase.EDITING -> FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { store.close(); onDismiss() }, modifier = Modifier.testTag("story-editor-cancel")) { Text(label("Cancel", "取消")) }
                            Button(onClick = { store.beginReview() }, enabled = !speechPending,
                                modifier = Modifier.testTag("story-editor-review")) { Text(label("Review", "检查")) }
                        }
                        StoryEditorPhase.REVIEW -> FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = store::backToEdit, modifier = Modifier.testTag("story-editor-back")) { Text(label("Back to edit", "返回编辑")) }
                            Button(onClick = store::confirmSave, modifier = Modifier.testTag("story-editor-confirm")) { Text(label("Confirm save", "确认保存")) }
                        }
                        StoryEditorPhase.SAVING -> Text("Saving… / 正在保存…", modifier = Modifier.testTag("story-editor-pending"))
                        StoryEditorPhase.UNCERTAIN -> FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(label("The save may already have succeeded. Do not edit until you know.", "保存可能已经成功，请先确认。"), color = MaterialTheme.colorScheme.error)
                            Button(onClick = store::retryUncertain, enabled = clock >= state.retryAtMillis, modifier = Modifier.testTag("story-editor-retry")) { Text(label("Retry same save", "重试相同保存")) }
                            TextButton(onClick = { store.close(); onDismiss() }, modifier = Modifier.testTag("story-editor-dismiss-uncertain")) { Text(label("Close", "关闭")) }
                        }
                        StoryEditorPhase.CONFLICT -> FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            state.latest?.takeIf { state.canUseLatest }?.let { latest ->
                                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    Text(label("Current server version", "服务器当前版本"), style = MaterialTheme.typography.labelLarge)
                                    Text(latest.title, style = MaterialTheme.typography.titleMedium)
                                    MemoryParagraphs(latest.text)
                                }
                            }
                            Button(onClick = store::reloadCurrent, modifier = Modifier.testTag("story-editor-reload")) { Text(label("Reload current", "重新加载")) }
                            Button(onClick = store::useLatestRevision, enabled = state.canUseLatest, modifier = Modifier.testTag("story-editor-use-latest")) { Text(label("Use latest revision", "使用最新版本")) }
                            TextButton(onClick = store::dismissConflict, modifier = Modifier.testTag("story-editor-dismiss-conflict")) { Text(label("Keep draft", "保留草稿")) }
                        }
                        StoryEditorPhase.SAVED -> {
                            state.latest?.let { saved ->
                                Text(label("Saved revision ${saved.revision}", "已保存版本 ${saved.revision}"), modifier = Modifier.testTag("story-editor-saved"))
                                Text(saved.title, style = MaterialTheme.typography.titleMedium)
                                MemoryParagraphs(saved.text)
                            }
                            Button(onClick = { store.close(); onDismiss() }, modifier = Modifier.testTag("story-editor-done")) { Text(label("Done", "完成")) }
                        }
                        StoryEditorPhase.DENIED -> TextButton(onClick = { store.close(); onDismiss() }, modifier = Modifier.testTag("story-editor-close-denied")) { Text("Close / 关闭") }
                        StoryEditorPhase.CLOSED -> Unit
                    }
                }
            }
        }
    }
}

@Composable private fun MemoryParagraphs(text: String) {
    val pieces = remember(text) {
        buildList {
            var offset = 0
            while (offset < text.length) {
                var end = minOf(offset + 96, text.length)
                if (end < text.length && text[end - 1].isHighSurrogate()) end--
                add(text.substring(offset, end)); offset = end
            }
        }
    }
    for (piece in pieces) Text(piece, style = MaterialTheme.typography.bodyLarge)
}
