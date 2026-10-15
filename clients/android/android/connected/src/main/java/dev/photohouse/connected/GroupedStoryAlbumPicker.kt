package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.*

/** Browses protected album metadata; choosing prepares selection, never a preview or save. */
@Composable
internal fun GroupedStoryAlbumPicker(
    store: ConnectedStore,
    creation: GroupedStoryCreationState,
    editor: StoryWorkspaceStore,
    zh: Boolean,
    canAct: Boolean,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    var expanded by remember(editor) { mutableStateOf(false) }
    var replacement by remember(editor) { mutableStateOf<Pair<ProtectedLibraryAlbum, List<String>>?>(null) }
    val selectedAlbum = creation.selectedAlbum
    val page = creation.albumsPage
    var helpExpanded by remember(editor, selectedAlbum?.id, selectedAlbum?.revision) { mutableStateOf(false) }
    LaunchedEffect(selectedAlbum) { if (selectedAlbum != null) expanded = false }
    fun currentSelection(): List<String>? {
        val live = store.state.value.groupedStoryCreation ?: return null
        if (live.editor !== editor || live.canCreate != true || live.pageBusy || live.albumBusy ||
            live.albumsPageBusy || editor.state.value.busy ||
            editor.state.value.status != StoryWorkspaceStoreStatus.SELECTION) return null
        return editor.state.value.selectedAssetIds.toList()
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = {
            if (currentSelection() != null) {
                expanded = !expanded
                if (expanded && store.state.value.groupedStoryCreation?.albumsPage == null)
                    store.loadGroupedStoryAlbums(1)
            }
        }, enabled = canAct, modifier = Modifier.fillMaxWidth().testTag("grouped-story-albums-toggle")) {
            Text(t("Start from an album", "从相册开始"))
        }
        if (selectedAlbum != null) {
            Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = MaterialTheme.shapes.medium) {
                Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(if (zh && selectedAlbum.titleZh.isNotBlank()) selectedAlbum.titleZh else selectedAlbum.title,
                        style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("grouped-story-album-current"))
                    if (selectedAlbum.assetIds.size > 24) Text(
                        t("${selectedAlbum.assetIds.size} moments · first 24 selected to start",
                            "${selectedAlbum.assetIds.size} 个瞬间 · 初始选前 24 个"),
                        modifier = Modifier.testTag("grouped-story-album-overflow"))
                    TextButton(onClick = { helpExpanded = !helpExpanded },
                        modifier = Modifier.testTag("grouped-story-album-help")) {
                        Text(t(if (helpExpanded) "Hide selection guidance" else "Selection guidance",
                            if (helpExpanded) "收起选择说明" else "选择说明"))
                    }
                    if (helpExpanded) Text(
                        t("Album order is your starting point. Review the moments before creating an outline. Every album page remains available; remove a selected moment to add another when you reach 24. Returning to the library keeps your selection.",
                            "先按相册顺序准备瞬间，请在创建提纲前核对。相册各页仍可查看；达到 24 个时，可移除一个再加入其他瞬间。返回资料库会保留现有选择。"),
                        modifier = Modifier.testTag("grouped-story-album-help-text"))
                    if (selectedAlbum.needsReview) Text(
                        t("Some album media are no longer available. Only currently authorized moments are shown; review this selection.",
                            "相册中部分内容已不可用。这里只显示当前可访问的瞬间，请重新核对。"),
                        modifier = Modifier.testTag("grouped-story-album-needs-review"))
                    if (creation.albumUnsupportedCount > 0) Text(
                        t("Some items on this page cannot be used in a photo/video story.", "此页有部分内容不适用于照片或视频故事。"))
                    OutlinedButton(onClick = { if (currentSelection() != null) store.returnToGroupedStoryLibrary() },
                        enabled = canAct, modifier = Modifier.fillMaxWidth().testTag("grouped-story-album-library")) {
                        Text(t("Back to library", "返回资料库"))
                    }
                    val total = ((selectedAlbum.assetIds.size + 7) / 8).coerceAtLeast(1)
                    Text(t("Album page ${creation.albumPage} of $total", "相册第 ${creation.albumPage} / $total 页"))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = {
                            if (currentSelection() != null) store.loadGroupedStorySelectionPage(creation.albumPage - 1)
                        }, enabled = canAct && creation.albumPage > 1,
                            modifier = Modifier.weight(1f).testTag("grouped-story-album-previous")) { Text(t("Previous", "上一页")) }
                        OutlinedButton(onClick = {
                            if (currentSelection() != null) store.loadGroupedStorySelectionPage(creation.albumPage + 1)
                        }, enabled = canAct && creation.albumPage < total,
                            modifier = Modifier.weight(1f).testTag("grouped-story-album-next")) { Text(t("Next", "下一页")) }
                    }
                }
            }
        }
        if (creation.albumBusy || creation.albumsPageBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (creation.albumChoiceFailure) Text(t("This album changed. Refresh the album list and choose it again; your selection is unchanged.",
            "相册已变化。请刷新列表后重新选择；现有选择保持不变。"), color = MaterialTheme.colorScheme.error,
            modifier = Modifier.testTag("grouped-story-album-changed"))
        creation.albumsProblem?.let {
            Text(Words(zh).message(it.message), color = MaterialTheme.colorScheme.error)
            if (selectedAlbum == null && creation.albumUnsupportedCount > 0) Text(
                t("This album contains items that cannot be used in a photo/video story. Your selection is unchanged.",
                    "此相册包含不适用于照片或视频故事的内容，现有选择保持不变。"),
                modifier = Modifier.testTag("grouped-story-album-unsupported"))
            if (selectedAlbum != null) TextButton(onClick = {
                if (currentSelection() != null) store.loadGroupedStorySelectionPage(creation.albumPage)
            }, enabled = canAct, modifier = Modifier.testTag("grouped-story-album-page-retry")) {
                Text(t("Retry album page", "重试相册此页"))
            }
        }
        if (expanded) {
            Text(t("An album prepares an ordered photo/video selection and its theme. Memories and chapter words stay yours to review.",
                "相册提供按顺序排列的照片、视频和主题。回忆来源与篇章文字仍需由你核对。"), style = MaterialTheme.typography.bodySmall)
            if (page != null && page.items.isEmpty() && !creation.albumsPageBusy) Text(t("No albums on this page.", "此页暂无相册。"))
            page?.items.orEmpty().forEach { album ->
                OutlinedButton(onClick = {
                    val snapshot = currentSelection() ?: return@OutlinedButton
                    if (snapshot.isEmpty()) store.selectGroupedStoryAlbum(album, snapshot, false)
                    else replacement = album to snapshot
                }, enabled = canAct && album.assetIds.isNotEmpty(), modifier = Modifier.fillMaxWidth().testTag("grouped-story-album-${album.id}")) {
                    Column(Modifier.fillMaxWidth()) {
                        Text(if (zh && album.titleZh.isNotBlank()) album.titleZh else album.title)
                        Text(t("${album.assetIds.size} moments", "${album.assetIds.size} 个瞬间"), style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { if (currentSelection() != null) store.loadGroupedStoryAlbums((page?.page ?: 1) - 1) },
                    enabled = canAct && (page?.page ?: 1) > 1, modifier = Modifier.weight(1f).testTag("grouped-story-albums-previous")) { Text(t("Previous", "上一页")) }
                OutlinedButton(onClick = { if (currentSelection() != null) store.loadGroupedStoryAlbums((page?.page ?: 1) + 1) },
                    enabled = canAct && page != null && page.page.toLong() * page.pageSize < page.total,
                    modifier = Modifier.weight(1f).testTag("grouped-story-albums-next")) { Text(t("Next", "下一页")) }
            }
            TextButton(onClick = { if (currentSelection() != null) store.loadGroupedStoryAlbums(page?.page ?: 1) },
                enabled = canAct, modifier = Modifier.testTag("grouped-story-albums-retry")) { Text(t("Refresh albums", "刷新相册")) }
        }
    }
    replacement?.let { (album, snapshot) ->
        AlertDialog(onDismissRequest = { replacement = null },
            title = { Text(t("Replace selected moments?", "替换所选瞬间？")) },
            text = { Text(t("Use this album's order and theme instead of the ${snapshot.size} moments you selected. You can adjust the new selection before previewing.",
                "用相册的顺序和主题替换当前选择的 ${snapshot.size} 个瞬间。预览前仍可调整。")) },
            confirmButton = { TextButton(onClick = {
                if (currentSelection() == snapshot) store.selectGroupedStoryAlbum(album, snapshot, true)
                replacement = null
            }, modifier = Modifier.testTag("grouped-story-album-replace-confirm")) { Text(t("Use album", "使用相册")) } },
            dismissButton = { TextButton(onClick = { replacement = null }, modifier = Modifier.testTag("grouped-story-album-replace-cancel")) { Text(t("Keep selection", "保留选择")) } },
            modifier = Modifier.testTag("grouped-story-album-replace-dialog"))
    }
}
