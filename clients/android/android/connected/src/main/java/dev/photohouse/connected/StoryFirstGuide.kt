package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*

/** Navigation describes progress; it never triggers outline generation or a save. */
@Composable
internal fun StoryGuideProgress(step: StoryGuideStep, zh: Boolean) {
    val labels = if (zh) listOf("挑选画面", "讲述回忆", "检查保存") else listOf("Choose", "Tell", "Review")
    Row(Modifier.fillMaxWidth().testTag("story-guide-progress"), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        StoryGuideStep.entries.forEachIndexed { index, item ->
            Column(Modifier.weight(1f).semantics {
                stateDescription = if (item == step) if (zh) "当前步骤" else "Current step" else ""
            }.testTag("story-guide-step-${item.name}"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("${index + 1}", style = MaterialTheme.typography.labelLarge,
                    color = if (item == step) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)
                Text(labels[index], style = MaterialTheme.typography.labelLarge)
                HorizontalDivider(color = if (item == step) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant)
            }
        }
    }
}

/** Literal, read-only preview of a draft. It does not pretend to be a saved story. */
@Composable
internal fun StoryGuideDraftReview(state: StoryWorkspaceStoreState, zh: Boolean, previews: Map<String, ByteArray>) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val draft = state.draft ?: return
    val words = Words(zh)
    Column(Modifier.fillMaxWidth().testTag("story-guide-draft-preview"), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(t("Unsaved story preview", "待保存的故事预览"), style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.primary)
        Text(state.title, style = MaterialTheme.typography.headlineMedium, fontFamily = FontFamily.Serif,
            modifier = Modifier.testTag("story-guide-preview-title"))
        Text(t("${draft.items.size} moments · ${state.editableChapters.size} chapters",
            "${draft.items.size} 个画面 · ${state.editableChapters.size} 篇"), style = MaterialTheme.typography.bodySmall)
        state.editableChapters.forEachIndexed { index, chapter ->
            OutlinedCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("${index + 1}. ${chapter.title}", style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif)
                    chapter.assetIds.forEach { id ->
                        draft.items.find { it.asset.id == id }?.let { item ->
                            Preview(item.asset, previews[id], words, modifier = Modifier.fillMaxWidth())
                        }
                    }
                    Text(chapter.narration.ifBlank { t("No wording in this chapter yet.", "这一篇暂时没有正文，可以返回补充。") },
                        style = MaterialTheme.typography.bodyLarge, modifier = Modifier.testTag("story-guide-preview-words-${chapter.id}"))
                }
            }
        }
        Text(t("Saving shares this story with this library's members. Original photo notes stay separate; these words are not copied to each photo. Review family sources and uncertain AI observations before saving.",
            "保存后，这个相册库的成员可以看到故事。照片原始回忆保持独立，正文不会复制到每张照片；保存前请核对家人原话和仍待确认的 AI 观察。"),
            style = MaterialTheme.typography.bodySmall)
    }
}
