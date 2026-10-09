package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*

/** Current originals and derived transcripts are inspected explicitly, separately from the manuscript. */
@Composable
internal fun MemoryBookEditionSourcePanel(store: ConnectedStore, book: MemoryBook, editionId: String,
    chapter: MemoryBookEditionChapter, zh: Boolean, allowed: Boolean) {
    if (!store.memoryBookEditionSourceAvailable) return
    val live by store.state.collectAsState()
    val sources by store.memoryBookEditionSourceState.collectAsState()
    val identity = listOf(live.session?.account_id,live.generation,live.library,book.id,book.revision,editionId,
        book.stories.map { it.id to it.revision },chapter.id)
    var references by remember(identity) { mutableStateOf(false) }
    var catalog by remember(identity) { mutableStateOf(false) }
    var excerpt by remember(identity,sources.selectedId,sources.detail) { mutableStateOf(false) }
    DisposableEffect(identity) { onDispose { store.clearMemoryBookEditionSources() } }
    fun t(en: String, cn: String) = if (zh) cn else en
    fun label(meta: MemoryBookEditionSourceMetadata): String = when (meta.origin) {
        MemoryBookEditionSourceOrigin.CONTRIBUTION_TEXT -> t("Family's original words","家人的原始讲述")
        MemoryBookEditionSourceOrigin.CONTRIBUTION_AUDIO -> t("Family recording and AI transcript","家人录音与 AI 转写")
        MemoryBookEditionSourceOrigin.ASSET_NOTE -> t("Family note on a photo","照片上的家人备注")
        MemoryBookEditionSourceOrigin.CAPTION -> if (meta.kind == "ai") t("AI photo description","照片的 AI 说明") else t("Family photo description","家人填写的照片说明")
        MemoryBookEditionSourceOrigin.BOOK_INTRODUCTION -> t("Memoir introduction","整本回忆录的引言")
        MemoryBookEditionSourceOrigin.STORY_CHAPTER -> t("Existing chapter wording","现有篇章文字")
    }
    Surface(shape = MaterialTheme.shapes.medium,color = MaterialTheme.colorScheme.surface,
        modifier = Modifier.fillMaxWidth().testTag("memory-edition-source-panel")) {
        Column(Modifier.padding(12.dp),verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(t("Check the source materials","核对原始材料"),style = MaterialTheme.typography.titleMedium)
            Text(t("Family accounts, AI descriptions and editorial wording have different roles. Check originals before treating a story as fact.",
                "家人的讲述、AI 说明和篇章文字作用不同。请先核对原始材料，再确认故事里的事实。"),style = MaterialTheme.typography.bodySmall)
            if (chapter.sourceIds.isNotEmpty()) {
                TextButton(onClick = { references = !references },modifier = Modifier.testTag("memory-edition-source-references")) {
                    Text(if (references) t("Hide chapter references","收起本篇章引用") else t("Review this chapter's references","查看本篇章引用"))
                }
                if (references) chapter.sourceIds.forEachIndexed { index,id ->
                    OutlinedButton(onClick = { store.readMemoryBookEditionSource(id) },enabled = allowed && !sources.busy,
                        modifier = Modifier.fillMaxWidth().testTag("memory-edition-source-reference-$index")) {
                        Text(t("Inspect reference ${index + 1}","核对引用 ${index + 1}"))
                    }
                }
            }
            OutlinedButton(onClick = { catalog = true; store.loadMemoryBookEditionSources() },enabled = allowed && !sources.busy,
                modifier = Modifier.fillMaxWidth().testTag("memory-edition-source-catalog")) {
                Text(t("Review all materials used in this edition","查看本版使用的全部材料"))
            }
            if (sources.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            when (sources.status) {
                MemoryBookEditionSourceStatus.LOADING_LIST -> Text(t("Checking the edition and loading its materials…","正在核对成稿并读取材料目录…"))
                MemoryBookEditionSourceStatus.LOADING_DETAIL -> Text(t("Checking the current original material…","正在核对并读取当前原始材料…"))
                MemoryBookEditionSourceStatus.LOADING_AUDIO -> Text(t("Checking and loading the original recording. It will not play automatically.","正在核对并加载原始录音，加载后不会自动播放。"))
                MemoryBookEditionSourceStatus.FAILED, MemoryBookEditionSourceStatus.UNAVAILABLE -> Text(
                    t("This material cannot be confirmed now. Previously loaded material has been cleared; try again.","暂时无法确认这份材料，先前读取的内容已清除，请稍后重试。"),
                    color = MaterialTheme.colorScheme.error,modifier = Modifier.testTag("memory-edition-source-failed").semantics { liveRegion = LiveRegionMode.Polite })
                MemoryBookEditionSourceStatus.SOURCE_CHANGED -> Text(t("Sources changed or were deleted. The manuscript and materials are hidden.","来源已变化或被删除，成稿和材料已隐藏。"))
                else -> Unit
            }
            sources.detail?.source?.let { material ->
                Text(label(material.metadata),style = MaterialTheme.typography.titleMedium,modifier = Modifier.testTag("memory-edition-source-origin"))
                material.byline?.takeIf { it.isNotBlank() }?.let { Text(t("Shared by $it","讲述／署名：$it"),style = MaterialTheme.typography.bodySmall) }
                material.originalText?.let { text ->
                    if (material.metadata.kind in setOf("ai","editorial")) Text(
                        t("AI or editorial wording is not an independent account of the events.","AI 或编辑整理文字，不是事件的独立事实依据。"),style = MaterialTheme.typography.bodySmall)
                    Text(text,modifier = Modifier.testTag("memory-edition-source-original"))
                    if (material.originalTruncated) Text(t("This original is long; a bounded excerpt is shown.","原文较长，这里显示有限长度的节选。"),style = MaterialTheme.typography.bodySmall)
                }
                material.transcript?.let { text ->
                    Text(t("AI transcript · listen to the original to check it","AI 转写 · 请听原声核对"),style = MaterialTheme.typography.labelLarge)
                    Text(text,modifier = Modifier.testTag("memory-edition-source-transcript"))
                    if (material.transcriptTruncated) Text(t("A bounded excerpt of this transcript is shown.","这里显示转写内容的有限长度节选。"),style = MaterialTheme.typography.bodySmall)
                }
                TextButton(onClick = { excerpt = !excerpt },modifier = Modifier.testTag("memory-edition-source-excerpt-toggle")) {
                    Text(if (excerpt) t("Hide drafting excerpt","收起整理使用的节选") else t("See the excerpt used for drafting","查看整理使用的节选"))
                }
                if (excerpt) Text(material.promptExcerpt,style = MaterialTheme.typography.bodySmall,modifier = Modifier.testTag("memory-edition-source-excerpt"))
                if (material.audioAvailable) {
                    OutlinedButton(onClick = { store.loadMemoryBookEditionSourceAudio() },enabled = allowed && !sources.busy,
                        modifier = Modifier.fillMaxWidth().testTag("memory-edition-source-load-audio")) { Text(t("Load original recording","加载原始录音")) }
                    sources.audio?.let { audio ->
                        AnnotationAudioPlayback(audio,zh,autoPlay = false,testTagPrefix = "memory-edition-source-audio")
                        TextButton(onClick = { store.closeMemoryBookEditionSourceAudio() },modifier = Modifier.testTag("memory-edition-source-close-audio")) {
                            Text(t("Close original recording","关闭原始录音"))
                        }
                    }
                }
                OutlinedButton(onClick = { store.readMemoryBookEditionSource(sources.detail!!.sourceId) },enabled = allowed && !sources.busy,
                    modifier = Modifier.fillMaxWidth().testTag("memory-edition-source-recheck")) { Text(t("Check and read this material again","重新核对这份材料")) }
            }
            if (catalog) sources.listing?.let { page ->
                if (page.items.isEmpty()) Text(t("No material is available for this edition.","这个版本没有可读取的材料。"))
                page.items.forEachIndexed { index,meta ->
                    OutlinedButton(onClick = { store.readMemoryBookEditionSource(meta.sourceId) },enabled = allowed && !sources.busy,
                        modifier = Modifier.fillMaxWidth().testTag("memory-edition-source-item-$index")) {
                        Text("${(page.page - 1) * 16 + index + 1}. ${label(meta)}")
                    }
                }
                Row(Modifier.fillMaxWidth(),horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { store.loadMemoryBookEditionSources(page.page - 1) },enabled = allowed && !sources.busy && page.page > 1,
                        modifier = Modifier.weight(1f).testTag("memory-edition-source-previous-page")) { Text(t("Previous page","上一页")) }
                    OutlinedButton(onClick = { store.loadMemoryBookEditionSources(page.page + 1) },enabled = allowed && !sources.busy && page.hasMore,
                        modifier = Modifier.weight(1f).testTag("memory-edition-source-next-page")) { Text(t("Next page","下一页")) }
                }
            }
            if (sources.status != MemoryBookEditionSourceStatus.CLOSED) TextButton(onClick = {
                store.clearMemoryBookEditionSources(); catalog = false; references = false
            },modifier = Modifier.testTag("memory-edition-source-close")) { Text(t("Close source materials","收起原始材料")) }
        }
    }
}
