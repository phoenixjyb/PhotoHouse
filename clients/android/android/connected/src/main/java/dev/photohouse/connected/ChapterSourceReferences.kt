package dev.photohouse.connected

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.MemoryStoryEvidence
import dev.photohouse.connected.core.SavedMemoryStory
import dev.photohouse.connected.core.SavedMemoryStoryChapter

/** Select only evidence cited by this chapter and attached to one of its own assets. */
internal fun chapterSourceReferences(chapter: SavedMemoryStoryChapter, story: SavedMemoryStory): List<MemoryStoryEvidence> {
    val chapterAssets = chapter.assetIds.toSet()
    val citedIds = chapter.evidenceIds.toSet()
    val byId = LinkedHashMap<String, MemoryStoryEvidence>()
    story.items.asSequence().filter { it.asset.id in chapterAssets }.forEach { item ->
        item.evidence.forEach { evidence ->
            if (evidence.id in citedIds && evidence.id !in byId) byId[evidence.id] = evidence
        }
    }
    return chapter.evidenceIds.mapNotNull(byId::get).distinctBy { it.id }
}

@Composable
internal fun ChapterSourceReferences(
    references: List<MemoryStoryEvidence>,
    zh: Boolean,
    expanded: Boolean,
    onExpandedChange: (Boolean) -> Unit,
    tag: String,
) {
    if (references.isEmpty()) return
    fun t(en: String, cn: String) = if (zh) cn else en
    Column(Modifier.fillMaxWidth().testTag("$tag-container")) {
        OutlinedButton(onClick = { onExpandedChange(!expanded) }, modifier = Modifier.fillMaxWidth().testTag("$tag-toggle")) {
            Text(if (expanded) t("Hide chapter sources", "收起本章素材来源") else t("View sources for this chapter", "查看本章素材来源"))
        }
        if (expanded) {
            Text(
                t("These references relate to the chapter; they are not verified facts.", "以下是本章引用的参考资料，不代表已核实事实。"),
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 4.dp).testTag("$tag-disclaimer"),
            )
            references.forEachIndexed { index, evidence ->
                Column(Modifier.fillMaxWidth().padding(top = 8.dp).testTag("$tag-reference-$index")) {
                    Text(
                        when (evidence.source) {
                            "family" -> t("Family-provided wording", "家人提供的文字")
                            else -> t("AI observation · verify", "AI 观察 · 需核对")
                        },
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.testTag("$tag-source-${evidence.id}"),
                    )
                    if (evidence.title.isNotBlank()) Text(evidence.title, style = MaterialTheme.typography.labelLarge)
                    Text(evidence.text, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.testTag("$tag-text-${evidence.id}"))
                }
            }
        }
    }
}
