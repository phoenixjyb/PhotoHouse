package dev.photohouse.connected

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.MemoryBookPlanCapacity
import dev.photohouse.connected.core.MemoryBookPlanSection

/** Optional, collapsed view of each saved story's capacity and read-only route. */
@Composable
internal fun MemoryBookPlanSections(
    sections: List<MemoryBookPlanSection>,
    scopeKey: Any,
    enabled: Boolean,
    zh: Boolean,
    onOpen: (MemoryBookPlanSection) -> Unit,
) {
    var expanded by remember(scopeKey) { mutableStateOf(false) }
    fun t(en: String, cn: String) = if (zh) cn else en

    Column(
        Modifier.fillMaxWidth().testTag("memory-book-plan-sections"),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        OutlinedButton(
            onClick = { expanded = !expanded },
            enabled = enabled && sections.isNotEmpty(),
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                .testTag("memory-book-plan-sections-toggle"),
        ) {
            Text(if (expanded) t("Hide story availability", "收起各故事篇章容量")
                else t("Story chapter availability · ${sections.size}", "各故事篇章容量 · ${sections.size}"))
        }

        if (expanded) {
            sections.forEachIndexed { sectionIndex, section ->
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = MaterialTheme.shapes.medium,
                    modifier = Modifier.fillMaxWidth().testTag("memory-book-plan-section-$sectionIndex"),
                ) {
                    Column(
                        Modifier.fillMaxWidth().padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(
                            "${section.position}. ${section.title}",
                            style = MaterialTheme.typography.titleSmall,
                        )
                        Text(
                            t(
                                "${section.chapters.size} ${if (section.chapters.size == 1) "chapter" else "chapters"} · " +
                                    "${section.itemCount} ${if (section.itemCount == 1) "moment" else "moments"}",
                                "${section.chapters.size} 个篇章 · ${section.itemCount} 个片段",
                            ),
                            style = MaterialTheme.typography.bodySmall,
                        )
                        CapacitySummary(section.capacity, zh)

                        section.chapters.forEachIndexed { chapterIndex, chapter ->
                            Text(
                                t(
                                    "${chapterIndex + 1}. ${chapter.title} · ${chapter.itemCount} " +
                                        if (chapter.itemCount == 1) "moment" else "moments",
                                    "${chapterIndex + 1}. ${chapter.title} · ${chapter.itemCount} 个片段",
                                ),
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }

                        OutlinedButton(
                            onClick = { onOpen(section); expanded = false },
                            enabled = enabled,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)
                                .testTag("memory-book-plan-section-read-$sectionIndex"),
                        ) {
                            Text(t("Read in this memoir", "在回忆集中阅读"))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CapacitySummary(capacity: MemoryBookPlanCapacity, zh: Boolean) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val label = when {
        capacity.state == "smaller_scope_required" ->
            t("This story exceeds the drafting scope", "这个故事超出单篇整理范围")
        capacity.canDraft -> t("Available for a story draft", "可单独整理")
        else -> t("Available to inspect; drafting unavailable", "可查看，暂不能整理")
    }
    val sourceCount = capacity.sourceCount
    val kinds = capacity.sourceKinds.orEmpty()
    val breakdown = kinds.entries.sortedBy { it.key }.joinToString(" · ") { (kind, count) ->
        val kindLabel = when (kind) {
            "ai" -> t("AI captions", "AI 描述")
            "editorial" -> t("editorial", "整理资料")
            "family" -> t("family", "家人讲述")
            "metadata" -> t("metadata", "元数据")
            "transcript" -> t("transcripts", "转写")
            else -> kind
        }
        "$kindLabel $count"
    }
    val sources = sourceCount?.let { count ->
        val countLabel = t("$count ${if (count == 1) "source" else "sources"}", "$count 条资料")
        if (breakdown.isBlank()) countLabel else "$countLabel · $breakdown"
    }
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
        if (sources != null) Text(sources, style = MaterialTheme.typography.bodySmall)
    }
}
