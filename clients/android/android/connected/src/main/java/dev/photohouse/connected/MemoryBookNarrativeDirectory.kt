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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.MemoryBookNarrativeChapter

/** Optional, local-only navigation through a reviewable draft's chapters. */
@Composable
internal fun MemoryBookNarrativeDirectory(
    chapters: List<MemoryBookNarrativeChapter>,
    selected: Int,
    scopeKey: Any,
    enabled: Boolean,
    zh: Boolean,
    onSelect: (Int) -> Unit,
) {
    var expanded by remember(scopeKey) { mutableStateOf(false) }
    val currentIndex = selected.takeIf { it in chapters.indices }

    Column(
        Modifier.fillMaxWidth().testTag("memory-book-narrative-directory"),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        OutlinedButton(
            onClick = { expanded = !expanded },
            enabled = enabled && chapters.isNotEmpty(),
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                .testTag("memory-book-narrative-directory-toggle"),
        ) {
            Text(if (expanded) {
                if (zh) "收起建议目录" else "Hide draft contents"
            } else {
                if (zh) "建议目录" else "Draft contents"
            })
        }

        if (expanded) {
            Column(
                Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                chapters.forEachIndexed { index, chapter ->
                    val isCurrent = index == currentIndex
                    Row(
                        Modifier.fillMaxWidth()
                            .heightIn(min = 48.dp)
                            .background(
                                if (isCurrent) MaterialTheme.colorScheme.secondaryContainer
                                else MaterialTheme.colorScheme.surface,
                            )
                            .selectable(
                                selected = isCurrent,
                                enabled = enabled,
                                role = Role.RadioButton,
                            ) {
                                onSelect(index)
                                expanded = false
                            }
                            .testTag("memory-book-narrative-directory-item-$index")
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                    ) {
                        Column(
                            Modifier.fillMaxWidth(),
                            verticalArrangement = Arrangement.spacedBy(2.dp),
                        ) {
                            if (isCurrent) {
                                Text(
                                    if (zh) "当前篇章 · ${index + 1}"
                                    else "Current chapter · ${index + 1}",
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.primary,
                                )
                            }
                            Text(
                                text = "${index + 1}. ${chapter.storyTitle}",
                                style = MaterialTheme.typography.titleSmall,
                            )
                            Text(
                                text = chapter.chapterTitle,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }
            }
        }
    }
}
