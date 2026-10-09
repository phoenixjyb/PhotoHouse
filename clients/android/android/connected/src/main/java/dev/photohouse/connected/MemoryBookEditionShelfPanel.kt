package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** The family shelf remains separate from private AI drafting and its pending save. */
@Composable
@OptIn(ExperimentalFoundationApi::class)
internal fun MemoryBookEditionShelfPanel(
    store: ConnectedStore, reading: MemoryBooksReading, zh: Boolean, speechEnabled: Boolean,
) {
    if (!store.memoryBookEditionAvailable) return
    val book = reading.selectedBook ?: return
    val live by store.state.collectAsState()
    val shelf by store.memoryBookEditionShelfState.collectAsState()
    val editor by store.memoryBookEditionState.collectAsState()
    fun t(en: String, cn: String) = if (zh) cn else en
    val scopeKey = listOf(live.session?.account_id, live.generation, reading.library, book.id, book.revision,
        shelf.selectedId, shelf.detail?.receipt?.id, shelf.detail?.manuscript)
    var chapterIndex by remember(scopeKey) { mutableIntStateOf(0) }
    var directory by remember(scopeKey) { mutableStateOf(false) }
    val statusScope = listOf(live.session?.account_id,live.generation,reading.library,book.id,book.revision,shelf.selectedId)
    val latestStatusScope by rememberUpdatedState(statusScope)
    val latestStatus by rememberUpdatedState(shelf.status)
    val changedNotice = remember(statusScope) { BringIntoViewRequester() }
    LaunchedEffect(statusScope,shelf.status) {
        if (shelf.status == MemoryBookEditionShelfStatus.SOURCE_CHANGED) {
            withFrameNanos { }
            if (latestStatusScope == statusScope && latestStatus == MemoryBookEditionShelfStatus.SOURCE_CHANGED)
                changedNotice.bringIntoView()
        }
    }
    val readingAllowed = !editor.hasUnfinishedWork && !live.busy && !reading.readerBusy
    if (shelf.status == MemoryBookEditionShelfStatus.CLOSED) {
        OutlinedButton(onClick = { store.loadMemoryBookEditionShelf() }, enabled = readingAllowed,
            modifier = Modifier.fillMaxWidth().testTag("memory-edition-shelf-open")) {
            Text(t("Read saved family editions", "阅读已保存的家庭版本"))
        }
        return
    }
    Surface(color = MaterialTheme.colorScheme.surfaceVariant, shape = MaterialTheme.shapes.large,
        modifier = Modifier.fillMaxWidth().testTag("memory-edition-shelf")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(t("Family editions", "家庭成稿书架"), style = MaterialTheme.typography.titleLarge,
                fontFamily = FontFamily.Serif)
            Text(t("Saved manuscripts are separate from AI suggestions and original family accounts.",
                "已保存成稿、AI 整理建议和家人的原始讲述分别保留。"), style = MaterialTheme.typography.bodySmall)
            if (shelf.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            when (shelf.status) {
                MemoryBookEditionShelfStatus.CHECKING -> Text(t("Checking access and loading version metadata…", "正在核对权限并读取版本目录…"))
                MemoryBookEditionShelfStatus.UNAVAILABLE -> Text(t("Edition reading is not available here yet.", "这里暂未开放成稿阅读。"))
                MemoryBookEditionShelfStatus.READING -> Text(t("Checking the current sources before displaying text…", "正在核对当前来源，确认后才显示正文…"))
                MemoryBookEditionShelfStatus.SOURCE_CHANGED -> Text(t("Sources changed or were deleted. This manuscript is hidden.",
                    "来源已变化或被删除，这个版本的正文已隐藏。"), modifier = Modifier.bringIntoViewRequester(changedNotice).testTag("memory-edition-shelf-source-changed")
                        .semantics { liveRegion = LiveRegionMode.Polite })
                MemoryBookEditionShelfStatus.FAILED -> Text(t("This version cannot be confirmed now. Previous text has been cleared.",
                    "暂时无法确认这个版本，先前显示的正文已清除。"), color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.testTag("memory-edition-shelf-failed").semantics { liveRegion = LiveRegionMode.Polite })
                else -> Unit
            }
            val manuscript = shelf.detail?.manuscript
            if (manuscript != null) {
                val index = chapterIndex.coerceIn(manuscript.chapters.indices)
                val chapter = manuscript.chapters[index]
                val parent = book.stories.find { chapter.id.startsWith(it.id + "-chapter-") }
                Text(manuscript.title, fontFamily = FontFamily.Serif, style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.testTag("memory-edition-shelf-title"))
                Text(t("A reviewed AI manuscript · check the original accounts for facts", "已核对的 AI 整理稿 · 事实请以原始讲述为依据"),
                    style = MaterialTheme.typography.bodySmall)
                OutlinedButton(onClick = { directory = !directory }, modifier = Modifier.fillMaxWidth().testTag("memory-edition-shelf-directory")) {
                    Text(if (directory) t("Hide chapter directory", "收起篇章目录") else t("Choose a chapter", "选择篇章"))
                }
                if (directory) manuscript.chapters.forEachIndexed { position, item ->
                    val story = book.stories.find { item.id.startsWith(it.id + "-chapter-") }
                    val chapterNumber = item.id.substringAfterLast("-chapter-")
                    OutlinedButton(onClick = { store.clearMemoryBookEditionSources(); chapterIndex = position; directory = false },
                        modifier = Modifier.fillMaxWidth().testTag("memory-edition-shelf-chapter-$position")) {
                        Text(t("${position + 1}. ${story?.title.orEmpty()} · chapter $chapterNumber",
                            "${position + 1}. ${story?.title.orEmpty()} · 第 $chapterNumber 篇章"))
                    }
                }
                Text(t("Chapter ${index + 1} of ${manuscript.chapters.size}", "篇章 ${index + 1}/${manuscript.chapters.size}"),
                    style = MaterialTheme.typography.labelLarge, modifier = Modifier.testTag("memory-edition-shelf-position"))
                Text(parent?.title.orEmpty(), style = MaterialTheme.typography.titleMedium)
                Text(chapter.narration, style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.testTag("memory-edition-shelf-prose"))
                Text(t(if (chapter.sourceIds.size == 1) "1 source reference" else "${chapter.sourceIds.size} source references", "${chapter.sourceIds.size} 条来源引用"),
                    style = MaterialTheme.typography.bodySmall)
                ChapterReadAloud(chapter.narration, book.language,
                    listOf("edition-shelf", live.session?.account_id, live.generation, reading.library, book.id,
                        book.revision, shelf.selectedId, chapter.id, chapter.narration), zh,
                    enabled = speechEnabled && !shelf.busy && readingAllowed,
                    labels = ChapterReadAloudLabels(t("Read this chapter aloud", "朗读这一篇章"),
                        t("Stop reading", "停止朗读"), "memory-edition-shelf-narration"))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    TextButton(onClick = { store.clearMemoryBookEditionSources(); chapterIndex-- }, enabled = index > 0,
                        modifier = Modifier.testTag("memory-edition-shelf-previous-chapter")) { Text(t("Previous", "上一篇")) }
                    TextButton(onClick = { store.clearMemoryBookEditionSources(); chapterIndex++ }, enabled = index < manuscript.chapters.lastIndex,
                        modifier = Modifier.testTag("memory-edition-shelf-next-chapter")) { Text(t("Next", "下一篇")) }
                }
                MemoryBookEditionSourcePanel(store,book,shelf.detail!!.receipt.id,chapter,zh,readingAllowed && !shelf.busy)
                manuscript.questions.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
            }
            shelf.selectedId?.let { id ->
                OutlinedButton(onClick = { store.readMemoryBookShelfEdition(id) }, enabled = !shelf.busy && readingAllowed,
                    modifier = Modifier.fillMaxWidth().testTag("memory-edition-shelf-recheck")) {
                    Text(t("Check and read this edition again", "重新核对并读取这个版本"))
                }
                TextButton(onClick = { store.closeMemoryBookEditionShelfReading() }, modifier = Modifier.testTag("memory-edition-shelf-back")) {
                    Text(t("Back to version list", "返回版本目录"))
                }
            }
            val listing = shelf.listing
            if (listing != null && shelf.selectedId == null) {
                if (listing.items.isEmpty()) Text(t("No family edition has been saved yet.", "还没有保存家庭成稿。"))
                listing.items.forEachIndexed { index, item ->
                    val status = when (item.receipt.state) {
                        MemoryBookEditionState.CURRENT -> t("Check sources and read", "核对来源并阅读")
                        MemoryBookEditionState.SOURCE_CHANGED -> t("Sources changed · check again", "来源有变化 · 重新核对")
                        MemoryBookEditionState.SOURCE_INVALIDATED -> t("Sources deleted · manuscript hidden", "来源已删除 · 正文已隐藏")
                    }
                    val savedAt = Instant.ofEpochSecond(item.receipt.createdAt).atZone(ZoneId.systemDefault())
                        .format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"))
                    val number = (listing.page - 1) * 8 + index + 1
                    OutlinedButton(onClick = { store.readMemoryBookShelfEdition(item.receipt.id) }, enabled = !shelf.busy && readingAllowed,
                        shape = MaterialTheme.shapes.medium,
                        modifier = Modifier.fillMaxWidth().testTag("memory-edition-shelf-version-$index")) {
                        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp),
                            horizontalAlignment = Alignment.Start) {
                            Text(t("Edition $number", "成稿 $number"), style = MaterialTheme.typography.titleMedium)
                            Text(t("Saved $savedAt", "保存于 $savedAt"), style = MaterialTheme.typography.bodySmall)
                            Text(status, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                Text(t("Page ${listing.page}", "第 ${listing.page} 页"), modifier = Modifier.testTag("memory-edition-shelf-page"))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { store.loadMemoryBookEditionShelf(listing.page - 1) },
                        enabled = !shelf.busy && readingAllowed && listing.page > 1,
                        modifier = Modifier.weight(1f).testTag("memory-edition-shelf-previous-page")) { Text(t("Previous page", "上一页")) }
                    OutlinedButton(onClick = { store.loadMemoryBookEditionShelf(listing.page + 1) },
                        enabled = !shelf.busy && readingAllowed && listing.hasMore && listing.page < 100000,
                        modifier = Modifier.weight(1f).testTag("memory-edition-shelf-next-page")) { Text(t("Next page", "下一页")) }
                }
            }
            OutlinedButton(onClick = { store.loadMemoryBookEditionShelf(shelf.page) }, enabled = !shelf.busy && readingAllowed,
                modifier = Modifier.fillMaxWidth().testTag("memory-edition-shelf-refresh")) { Text(t("Refresh version list", "刷新版本目录")) }
            TextButton(onClick = { store.closeMemoryBookEditionShelf() }, modifier = Modifier.testTag("memory-edition-shelf-close")) {
                Text(t("Close family editions", "收起家庭成稿"))
            }
        }
    }
}
