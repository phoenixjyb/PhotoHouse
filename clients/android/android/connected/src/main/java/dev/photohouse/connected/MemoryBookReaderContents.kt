package dev.photohouse.connected

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.MemoryBooksReading

/** Original reader contents: loaded story summaries plus chapters for the loaded story only. */
@Composable
internal fun MemoryBookReaderContents(
    reading: MemoryBooksReading,
    scopeKey: Any,
    isCurrent: () -> Boolean,
    enabled: Boolean,
    zh: Boolean,
    onSelectStory: (Int) -> Unit,
    onSelectChapter: (Int) -> Unit,
) {
    val book = reading.selectedBook ?: return
    val stories = book.stories
    val selectedStoryIndex = reading.storyIndex?.takeIf { it in stories.indices }
    val summary = selectedStoryIndex?.let(stories::get)
    val story = reading.story?.takeIf { loaded ->
        summary?.let { it.id == loaded.id && it.revision == loaded.revision } == true
    }
    val selectedChapter = reading.selectedChapter.takeIf { story?.chapters?.indices?.contains(it) == true }
    var expanded by remember(scopeKey) { mutableStateOf(false) }
    fun t(en: String, cn: String) = if (zh) cn else en

    Column(
        Modifier.fillMaxWidth().testTag("memory-book-reader-contents"),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        OutlinedButton(
            onClick = { if (isCurrent()) expanded = !expanded },
            enabled = enabled && stories.isNotEmpty() && isCurrent(),
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                .testTag("memory-book-reader-contents-toggle"),
        ) {
            Text(if (expanded) t("Hide contents", "收起目录") else t("Contents", "目录"))
        }

        if (expanded) {
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(t("Stories", "故事"), style = MaterialTheme.typography.titleSmall)
                stories.forEachIndexed { index, item ->
                    val selected = index == selectedStoryIndex
                    Row(
                        Modifier.fillMaxWidth()
                            .heightIn(min = 48.dp)
                            .background(
                                if (selected) MaterialTheme.colorScheme.secondaryContainer
                                else MaterialTheme.colorScheme.surface,
                                shape = MaterialTheme.shapes.medium,
                            )
                            .selectable(
                                selected = selected,
                                enabled = enabled && !selected && isCurrent(),
                                role = Role.RadioButton,
                            ) {
                                if (!isCurrent()) return@selectable
                                expanded = false
                                onSelectStory(index)
                            }
                            .testTag("memory-book-reader-contents-story-$index")
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            if (selected) Text(
                                t("Current story · ${index + 1} of ${stories.size}", "当前故事 · ${index + 1}/${stories.size}"),
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.primary,
                            )
                            Text("${index + 1}. ${item.title}", style = MaterialTheme.typography.titleSmall)
                            Text(t("${item.itemCount} moments", "${item.itemCount} 个片段"),
                                style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }

                if (summary != null && story != null && story.chapters.isNotEmpty()) {
                    Text(t("Chapters", "章节"), style = MaterialTheme.typography.titleSmall)
                    story.chapters.forEachIndexed { index, chapter ->
                        val selected = index == selectedChapter
                        Row(
                            Modifier.fillMaxWidth()
                                .heightIn(min = 48.dp)
                                .background(
                                    if (selected) MaterialTheme.colorScheme.secondaryContainer
                                    else MaterialTheme.colorScheme.surface,
                                    shape = MaterialTheme.shapes.medium,
                                )
                                .selectable(
                                    selected = selected,
                                    enabled = enabled && !selected && isCurrent(),
                                    role = Role.RadioButton,
                                ) {
                                    if (!isCurrent()) return@selectable
                                    expanded = false
                                    onSelectChapter(index)
                                }
                                .testTag("memory-book-reader-contents-chapter-$index")
                                .padding(horizontal = 12.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                if (selected) Text(
                                    t("Current chapter · ${index + 1} of ${story.chapters.size}", "当前章节 · ${index + 1}/${story.chapters.size}"),
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.primary,
                                )
                                Text("${index + 1}. ${chapter.title}", style = MaterialTheme.typography.bodyLarge)
                            }
                        }
                    }
                }
            }
        }
    }
}
