package dev.photohouse.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.ConnectedStore
import dev.photohouse.connected.core.SavedMemoryStoriesReading
import dev.photohouse.connected.core.SavedMemoryStory
import dev.photohouse.connected.core.savedStoryRefinementDraft

@Composable
internal fun SavedStoryRefinementReview(
    store: ConnectedStore,
    reading: SavedMemoryStoriesReading,
    story: SavedMemoryStory,
    zh: Boolean,
    canEdit: Boolean,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val job = story.autoRefinement
    val references = reading.contributionReferences
    val proposal = remember(story.id, story.revision, job, references) {
        references?.let { savedStoryRefinementDraft(story, it) }
    }
    var expanded by remember(story.id, story.revision, job?.id) { mutableStateOf(false) }
    var selected by remember(story.id, story.revision, job?.id, job?.result) { mutableIntStateOf(0) }
    var approvalBlocked by remember(story.id, story.revision, job?.id, job?.result) { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth().testTag("saved-story-refinement")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(t("Local AI story suggestion", "本地 AI 整理建议"), style = MaterialTheme.typography.titleMedium)
            if (reading.refinementBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (reading.refinementProblem != null) {
                Text(t("The suggestion could not be checked. Refresh it or reopen the story.",
                    "暂时无法核对建议，请刷新或重新打开故事。"), color = MaterialTheme.colorScheme.error)
            }
            when (job?.state) {
                null -> OutlinedButton(
                    onClick = { store.refreshSavedStoryRefinement(story.id, story.revision, requestNew = true) },
                    enabled = !reading.refinementBusy,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("saved-story-refinement-start"),
                ) { Text(t("Refine this story", "整理这个故事")) }
                "ready" -> {
                    if (!expanded) {
                        OutlinedButton(onClick = { selected = 0; expanded = true },
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("saved-story-refinement-review")) {
                            Text(t("Review suggestion", "核对建议"))
                        }
                    } else if (proposal == null) {
                        Text(if (references == null) t("Check the chapter memory links to review the suggestion.",
                            "请先核对篇章回忆关联。") else t("There are no verified wording changes to apply.",
                            "没有可带入的已核对文字更改。"))
                    } else {
                        val index = selected.coerceIn(proposal.chapters.indices)
                        val suggested = proposal.chapters[index]
                        val original = story.chapters.first { it.id == suggested.id }
                        val chapterNumber = story.chapters.indexOf(original) + 1
                        Text(t("Chapter $chapterNumber · ${original.title}", "第 $chapterNumber 章 · ${original.title}"),
                            style = MaterialTheme.typography.titleSmall)
                        BoxWithConstraints(Modifier.fillMaxWidth()) {
                            if (maxWidth >= 600.dp) {
                                Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                                    RefinementWording(t("Current wording", "当前原文"), original.narration, Modifier.weight(1f))
                                    RefinementWording(t("Suggested wording", "整理建议"), suggested.narration, Modifier.weight(1f))
                                }
                            } else {
                                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    RefinementWording(t("Current wording", "当前原文"), original.narration)
                                    RefinementWording(t("Suggested wording", "整理建议"), suggested.narration)
                                }
                            }
                        }
                        if (proposal.chapters.size > 1) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton(onClick = { selected = index - 1 }, enabled = index > 0,
                                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)) { Text(t("Previous", "上一章")) }
                                OutlinedButton(onClick = { selected = index + 1 }, enabled = index < proposal.chapters.lastIndex,
                                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)) { Text(t("Next", "下一章")) }
                            }
                        }
                        if (proposal.questions.isNotEmpty()) {
                            Text(t("Questions to review", "待核对问题"), style = MaterialTheme.typography.titleSmall)
                            proposal.questions.forEach { Text(it) }
                        }
                        if (proposal.unlinkedSourceCount > 0) {
                            Text(t(
                                "Some citations from this suggestion fall outside the saved chapter links. Check the wording carefully.",
                                "建议中的部分引用不在已保存的篇章关联里，请仔细核对文字。",
                            ), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text(t("Approval opens an editable draft. Use Save to library when ready.",
                            "审核通过后将打开可编辑草稿。核对后点击“保存到相册库”。"),
                            style = MaterialTheme.typography.bodySmall)
                        Button(onClick = {
                            approvalBlocked = !store.beginSavedStoryRefinementEdit(story.id, story.revision, job.id)
                        },
                            enabled = canEdit && reading.refinementProblem == null,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("saved-story-refinement-approve")) {
                            Text(t("Approve and edit", "审核通过，带入编辑"))
                        }
                        if (approvalBlocked) Text(t("Finish any open chapter edits, then refresh the suggestion and try again.",
                            "请先完成待处理的篇章编辑，再刷新建议并重试。"), color = MaterialTheme.colorScheme.error)
                        TextButton(onClick = { expanded = false }, modifier = Modifier.heightIn(min = 48.dp)) {
                            Text(t("Keep original", "保留原文"))
                        }
                    }
                }
                "queued", "running", "deferred" -> Text(t("Waiting for the local suggestion…", "正在等待本地建议…"))
                else -> Text(t("The local suggestion is unavailable.", "暂时无法读取本地建议。"))
            }
            if (job != null || reading.refinementProblem != null) {
                TextButton(onClick = { store.refreshSavedStoryRefinement(story.id, story.revision) },
                    enabled = !reading.refinementBusy,
                    modifier = Modifier.heightIn(min = 48.dp).testTag("saved-story-refinement-refresh")) {
                    Text(t("Refresh suggestion", "刷新建议"))
                }
            }
        }
    }
}

@Composable
private fun RefinementWording(label: String, wording: String, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
        Text(wording, style = MaterialTheme.typography.bodyLarge)
    }
}
