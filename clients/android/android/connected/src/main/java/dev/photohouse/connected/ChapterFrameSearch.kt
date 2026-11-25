package dev.photohouse.connected

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import dev.photohouse.connected.core.StoryChapterFrameSearchState
import dev.photohouse.connected.core.StoryWorkspaceStore
import dev.photohouse.protocol.Asset

@Composable
internal fun ChapterFrameSearchDialog(
    store: StoryWorkspaceStore,
    search: StoryChapterFrameSearchState,
    chapterTitle: String,
    storyAssetIds: List<String>,
    zh: Boolean,
) {
    val words = remember(zh) { Words(zh) }
    var query by remember(store, search.chapterId) { mutableStateOf("") }
    val busy = search.searching || search.adding
    val existing = remember(storyAssetIds) { storyAssetIds.toSet() }
    val candidates = search.results.filterNot { it.id in existing }
    val selectionOrder = search.selectedAssetIds.withIndex().associate { (index, id) -> id to index + 1 }
    Dialog(
        onDismissRequest = store::closeChapterFrameSearch,
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnClickOutside = false),
    ) {
        val focus = LocalFocusManager.current
        val keyboard = LocalSoftwareKeyboardController.current
        fun submitSearch() {
            if (store.findChapterFrames(query)) {
                focus.clearFocus()
                keyboard?.hide()
            }
        }
        Surface(
            modifier = Modifier.fillMaxSize().safeDrawingPadding().imePadding()
                .testTag("chapter-frame-search"),
            color = MaterialTheme.colorScheme.background,
        ) {
            BoxWithConstraints(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 10.dp)) {
                val expanded = maxWidth >= 720.dp
                Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(words.t("Find frames for this chapter", "查找本篇画面"),
                                style = MaterialTheme.typography.titleLarge)
                            if (chapterTitle.isNotBlank()) Text(chapterTitle,
                                style = MaterialTheme.typography.bodySmall, maxLines = 2)
                        }
                        TextButton(
                            onClick = store::closeChapterFrameSearch,
                            modifier = Modifier.heightIn(min = 48.dp).testTag("chapter-frame-search-done"),
                        ) { Text(words.t("Back to story", "返回故事")) }
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(
                            value = query,
                            onValueChange = { if (it.length <= 512) query = it },
                            label = { Text(words.t("Search for a moment", "查找照片或视频")) },
                            singleLine = true,
                            enabled = !busy,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                            keyboardActions = KeyboardActions(onSearch = { submitSearch() }),
                            modifier = Modifier.weight(1f).testTag("chapter-frame-search-query"),
                        )
                        Button(onClick = ::submitSearch, enabled = !busy && query.isNotBlank(),
                            modifier = Modifier.heightIn(min = 48.dp).testTag("chapter-frame-search-submit")) {
                            Text(words.t("Search", "查找"))
                        }
                    }
                    if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                    if (search.error) Text(
                        words.t("The request could not be completed. You can try again.", "暂未完成这次请求，可以重试。"),
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                        color = MaterialTheme.colorScheme.error,
                    )
                    val emptyMessage = when {
                        !search.searched -> words.t("Try an event, date, or a description of what you remember.",
                            "可以用活动、日期或记得的画面来查找。")
                        search.results.isNotEmpty() -> words.t("These frames are already in your story.", "这些画面已在故事中。")
                        else -> search.reply ?: words.t("No matching photos or videos.", "没有匹配的照片或视频。")
                    }
                    if (expanded) {
                        Row(Modifier.weight(1f).fillMaxWidth().testTag("chapter-frame-search-expanded"),
                            horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                            ChapterFrameResults(store, candidates, selectionOrder, !busy, search.remaining, emptyMessage,
                                words, Modifier.weight(1f).fillMaxHeight())
                            Surface(Modifier.width(286.dp).fillMaxHeight(), shape = MaterialTheme.shapes.large) {
                                Column(Modifier.padding(16.dp)) {
                                    ChapterFrameSelection(store, search, words, expanded = true)
                                }
                            }
                        }
                    } else {
                        ChapterFrameResults(store, candidates, selectionOrder, !busy, search.remaining, emptyMessage,
                            words, Modifier.weight(1f).fillMaxWidth().testTag("chapter-frame-search-compact"))
                        ChapterFrameSelection(store, search, words, expanded = false)
                    }
                }
            }
        }
    }
}

@Composable
private fun ChapterFrameResults(
    store: StoryWorkspaceStore,
    assets: List<Asset>,
    selected: Map<String, Int>,
    enabled: Boolean,
    remaining: Int,
    emptyMessage: String,
    words: Words,
    modifier: Modifier,
) {
    if (assets.isEmpty()) {
        Box(modifier, contentAlignment = Alignment.Center) {
            Text(emptyMessage, Modifier.padding(12.dp), style = MaterialTheme.typography.bodyLarge)
        }
        return
    }
    val largeText = LocalConfiguration.current.fontScale >= 1.5f
    LazyVerticalGrid(
        columns = GridCells.Adaptive(if (largeText) 174.dp else 140.dp),
        modifier = modifier.testTag("chapter-frame-search-results"),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(bottom = 6.dp),
    ) {
        items(assets, key = Asset::id) { asset ->
            val ordinal = selected[asset.id]
            val canChoose = enabled && (ordinal != null || selected.size < remaining)
            val bytes by produceState<ByteArray?>(null, store, asset) {
                value = store.chapterFrameThumbnail(asset.id)
            }
            bytes?.let { thumbnail ->
                DisposableEffect(thumbnail) { onDispose { thumbnail.fill(0) } }
            }
            Surface(
                modifier = Modifier.fillMaxWidth().testTag("chapter-frame-choice-${asset.id}")
                    .toggleable(value = ordinal != null, enabled = canChoose, role = Role.Checkbox) {
                        store.toggleChapterFrame(asset.id)
                    },
                shape = MaterialTheme.shapes.medium,
                color = if (ordinal != null) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
                border = BorderStroke(if (ordinal != null) 2.dp else 1.dp, MaterialTheme.colorScheme.outlineVariant),
            ) {
                Column {
                    Preview(asset, bytes, words, kindBadge = false)
                    Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(frameKind(asset, words), style = MaterialTheme.typography.labelLarge)
                        asset.taken_at?.take(10)?.let {
                            Text(it, style = MaterialTheme.typography.bodySmall)
                        }
                        if (ordinal != null) Text(words.t("Selected $ordinal", "已选第 $ordinal 项"),
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onPrimaryContainer)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChapterFrameSelection(
    store: StoryWorkspaceStore,
    search: StoryChapterFrameSearchState,
    words: Words,
    expanded: Boolean,
) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        val count = search.selectedAssetIds.size
        Text(
            if (search.remaining == 0) words.t("This chapter is full.", "本篇画面已满。")
            else words.t("$count / ${search.remaining} new frames", "已选 $count / ${search.remaining} 个新画面"),
            Modifier.testTag("chapter-frame-search-count").semantics { liveRegion = LiveRegionMode.Polite },
            style = MaterialTheme.typography.titleSmall,
        )
        if (search.added) Text(words.t("Added to this chapter.", "已添加到本篇。"),
            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
        if (search.hasMore && !search.searching && count == 0 && search.remaining > 0) {
            Text(words.t("Narrow your search to find more specific frames.", "缩小查找范围可找到更具体的画面。"),
                style = MaterialTheme.typography.bodySmall)
        }
        val byId = search.results.associateBy(Asset::id)
        val picks = search.selectedAssetIds.mapNotNull(byId::get)
        val canAdd = picks.isNotEmpty() && !search.searching && !search.adding
        if (picks.isNotEmpty()) {
            if (expanded) {
                picks.forEachIndexed { index, asset ->
                    TextButton(onClick = { store.toggleChapterFrame(asset.id) }, enabled = canAdd,
                        modifier = Modifier.fillMaxWidth().testTag("chapter-frame-remove-${asset.id}")) {
                        Text(words.t("Remove ${frameKind(asset, words)} ${index + 1}",
                            "移除第 ${index + 1} 项${frameKind(asset, words)}"))
                    }
                }
            } else {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    items(picks.size, key = { picks[it].id }) { index ->
                        val asset = picks[index]
                        TextButton(onClick = { store.toggleChapterFrame(asset.id) }, enabled = canAdd,
                            modifier = Modifier.testTag("chapter-frame-remove-${asset.id}")) {
                            Text(words.t("Remove ${frameKind(asset, words)} ${index + 1}",
                                "移除第 ${index + 1} 项${frameKind(asset, words)}"))
                        }
                    }
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Button(onClick = { store.appendChapterFrames(keepSearching = true) }, enabled = canAdd,
                    modifier = Modifier.heightIn(min = 48.dp).testTag("chapter-frame-add-continue")) {
                    Text(words.t("Add and keep searching", "添加并继续查找"))
                }
                OutlinedButton(onClick = { store.appendChapterFrames(keepSearching = false) }, enabled = canAdd,
                    modifier = Modifier.heightIn(min = 48.dp).testTag("chapter-frame-add-return")) {
                    Text(words.t("Add and return", "添加并返回"))
                }
            }
        }
    }
}

private fun frameKind(asset: Asset, words: Words) =
    if (asset.kind == "video") words.t("Video", "视频") else words.t("Photo", "照片")
