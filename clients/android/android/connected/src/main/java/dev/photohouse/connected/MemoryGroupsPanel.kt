package dev.photohouse.connected

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.Asset

/** Explicit, in-memory review of a shared original note; no background save or recording. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun MemoryGroupsDialog(store: MemoryGroupsStore, zh: Boolean, onClose: (Boolean) -> Boolean) {
    val state by store.state.collectAsState()
    var discard by remember(store) { mutableStateOf(false) }
    var showGallery by remember(store, state.phase) { mutableStateOf(false) }
    var clock by remember(store) { mutableLongStateOf(System.currentTimeMillis()) }
    val words = remember(zh) { Words(zh) }
    fun t(en: String, cn: String) = if (zh) cn else en
    fun requestClose() { if (!onClose(false) && state.phase != MemoryGroupsStorePhase.SAVING) discard = true }
    LaunchedEffect(state.retryAtMillis, state.phase) {
        while (clock < state.retryAtMillis) { kotlinx.coroutines.delay(250); clock = System.currentTimeMillis() }
    }
    val editing = state.phase == MemoryGroupsStorePhase.EDITING
    val draft = state.phase in setOf(MemoryGroupsStorePhase.EDITING, MemoryGroupsStorePhase.REVIEW,
        MemoryGroupsStorePhase.SAVING, MemoryGroupsStorePhase.UNCERTAIN, MemoryGroupsStorePhase.CONFLICT)
    Dialog(onDismissRequest = ::requestClose,
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnClickOutside = false)) {
        PhotoHouseTheme {
            Surface(Modifier.fillMaxSize().safeDrawingPadding().imePadding().testTag("memory-groups-dialog")) {
                Column {
                    Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Text(t("Family memory groups", "家庭回忆组"), Modifier.weight(1f), style = MaterialTheme.typography.headlineSmall)
                        TextButton(onClick = ::requestClose, enabled = state.phase != MemoryGroupsStorePhase.SAVING,
                            modifier = Modifier.testTag("memory-groups-close")) { Text(t("Close", "关闭")) }
                    }
                    HorizontalDivider()
                    LazyColumn(Modifier.fillMaxSize().testTag("memory-groups-content"),
                        contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        item {
                            Text(t("Tell a memory once and link it to related photos or videos. The original words and author stay with their source.",
                                "一段回忆，只需讲一次。把它关联到相关照片或视频，原话和署名仍属于最初的讲述。"),
                                style = MaterialTheme.typography.bodyLarge)
                        }
                        if (state.phase == MemoryGroupsStorePhase.LOADING) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                        if (state.phase == MemoryGroupsStorePhase.READY || state.phase == MemoryGroupsStorePhase.SAVED) {
                            if (state.saved != null) item {
                                Text(t("Group saved", "回忆组已保存"), Modifier.testTag("memory-group-saved"), color = MaterialTheme.colorScheme.primary)
                                MemoryGroupCard(state.saved!!, zh, onEdit = { store.startEdit(state.saved!!) })
                            }
                            if (state.capabilities?.enabled != true) item {
                                Text(t("Memory groups are not available in this library yet.", "此资料库暂未启用回忆组。"))
                            }
                            if (state.capabilities?.manual == true) item {
                                Button(onClick = { store.startCreate() }, modifier = Modifier.fillMaxWidth().testTag("memory-group-create")) {
                                    Text(t("Create a memory group", "创建回忆组"))
                                }
                            }
                            items(state.page?.items.orEmpty().filterNot { it.id == state.saved?.id }, key = { "group-${it.id}" }) { group ->
                                MemoryGroupCard(group, zh, onEdit = { store.startEdit(group) })
                            }
                            if (state.page?.items.isNullOrEmpty() && state.capabilities?.enabled == true && state.saved == null) item {
                                Text(t("No shared memories for this item yet.", "这项内容还没有共享的回忆。"), style = MaterialTheme.typography.bodyMedium)
                            }
                            if (state.page?.hasMore == true) item {
                                Text(t("More groups exist for this item. This view shows a limited set.", "这项内容还有其他回忆组，本页仅显示部分。"), style = MaterialTheme.typography.bodySmall)
                            }
                            item { OutlinedButton(onClick = { store.load() }, enabled = clock >= state.retryAtMillis,
                                modifier = Modifier.testTag("memory-groups-refresh")) { Text(t("Refresh", "刷新")) } }
                        }
                        if (draft) {
                            item {
                                Text(t("${state.selectedAssetIds.size} / 24 moments", "${state.selectedAssetIds.size} / 24 项内容"),
                                    Modifier.testTag("memory-group-count"), style = MaterialTheme.typography.titleMedium)
                                Text(t("${state.excludedAssetIds.size} excluded suggestions", "已排除 ${state.excludedAssetIds.size} 项建议"), style = MaterialTheme.typography.bodySmall)
                            }
                            if (editing) item {
                                Text(t("Theme", "主题"), style = MaterialTheme.typography.titleSmall)
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                    MemoryGroupsStore.THEMES.forEach { theme -> FilterChip(selected = state.theme == theme,
                                        onClick = { store.setTheme(theme) }, label = { Text(memoryGroupTheme(theme, zh)) },
                                        modifier = Modifier.testTag("memory-group-theme-$theme")) }
                                }
                            }
                            items(state.selectedAssetIds, key = { "selected-$it" }) { id ->
                                state.availableAssets.firstOrNull { it.id == id }?.let { asset ->
                                    MemoryGroupAssetRow(store, asset, state.previews[id], words, zh,
                                        action = if (editing) ({ store.removeAsset(id); Unit }) else null,
                                        actionText = t("Remove", "移除"), tag = "memory-group-member-$id")
                                }
                            }
                            item { Text(t("Original family memories", "家人的原话"), style = MaterialTheme.typography.titleMedium) }
                            val eligibleSources = state.availableSources.filter { it.assetId in state.selectedAssetIds }
                            if (eligibleSources.isEmpty()) item {
                                Text(t("Add a memory to a photo first, then link it here. You can still save this group without a note.",
                                    "可以先给照片添加回忆，再在这里关联。没有讲述时，也可以先保存这组内容。"), style = MaterialTheme.typography.bodyMedium)
                            }
                            items(eligibleSources, key = { "source-${it.id}" }) { source ->
                                if (editing || source.id in state.sourceStoryIds) Card(Modifier.fillMaxWidth()) {
                                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                        if (editing) Row(verticalAlignment = Alignment.CenterVertically) {
                                            Checkbox(source.id in state.sourceStoryIds, onCheckedChange = { store.selectSourceStory(source.id, it) },
                                                modifier = Modifier.testTag("memory-group-source-${source.id}"))
                                            Text(t("Share this memory", "共享这段回忆"), style = MaterialTheme.typography.titleSmall)
                                        }
                                        MemoryGroupOriginal(source, zh)
                                    }
                                }
                            }
                            if (editing) {
                                item {
                                    Text(t("Suggestions use recorded capture time and image similarity. Choose the matches before saving.",
                                        "建议会参考记录的拍摄时间和图片相似度。请先选择符合的内容，再保存。"), style = MaterialTheme.typography.bodySmall)
                                    OutlinedButton(onClick = { store.refreshSuggestions() }, enabled = store.suggestionsAvailable &&
                                        !state.suggestionBusy && clock >= state.retryAtMillis,
                                        modifier = Modifier.fillMaxWidth().testTag("memory-group-suggest")) {
                                        Text(t("Find related moments", "查找相关照片"))
                                    }
                                    if (state.capabilities?.suggestions != true) Text(t("Suggestions are unavailable; you can select items manually.",
                                        "暂时没有自动建议，可以手动选择内容。"), style = MaterialTheme.typography.bodySmall)
                                    else if (!store.suggestionsAvailable) Text(t("Include the original photo again to request suggestions, or continue manually.",
                                        "重新加入最初的照片后可查找建议，也可以继续手动选择。"), style = MaterialTheme.typography.bodySmall)
                                    if (state.suggestionBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
                                }
                                if (state.proposals?.status == MemoryGroupProposalStatus.UNAVAILABLE) item {
                                    Text(t("No reliable suggestions are available. Your selection is unchanged.", "暂时无法给出可靠建议，已选内容保持不变。"))
                                }
                                items(state.proposals?.items.orEmpty(), key = { "proposal-${it.asset.id}" }) { candidate ->
                                    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(12.dp)) {
                                        MemoryGroupAssetRow(store, candidate.asset, state.previews[candidate.asset.id], words, zh,
                                            action = null, actionText = "", tag = "memory-group-proposal-${candidate.asset.id}")
                                        Row(verticalAlignment = Alignment.CenterVertically) {
                                            Checkbox(candidate.asset.id in state.selectedAssetIds,
                                                onCheckedChange = { store.selectSuggestion(candidate.asset.id, it) },
                                                enabled = candidate.asset.id in state.selectedAssetIds || state.selectedAssetIds.size < 24,
                                                modifier = Modifier.testTag("memory-group-select-${candidate.asset.id}"))
                                            Text(t("Include this moment", "加入这项内容"))
                                        }
                                        TextButton(onClick = { store.selectSuggestion(candidate.asset.id, false) },
                                            modifier = Modifier.testTag("memory-group-exclude-${candidate.asset.id}")) { Text(t("Exclude suggestion", "排除此建议")) }
                                    } }
                                }
                                item { TextButton(onClick = { showGallery = !showGallery }, modifier = Modifier.testTag("memory-group-gallery-toggle")) {
                                    Text(if (showGallery) t("Collapse manual selection", "收起手动选择") else t("Choose from this page", "从当前页手动选择"))
                                } }
                                if (showGallery) items(state.availableAssets.filter { it.id !in state.selectedAssetIds }, key = { "manual-${it.id}" }) { asset ->
                                    MemoryGroupAssetRow(store, asset, state.previews[asset.id], words, zh,
                                        action = { store.addAsset(asset.id); Unit }, actionText = t("Add", "加入"), tag = "memory-group-add-${asset.id}")
                                }
                                item { Button(onClick = { store.beginReview() }, modifier = Modifier.fillMaxWidth().testTag("memory-group-review")) {
                                    Text(t("Review this group", "检查回忆组"))
                                } }
                            }
                            when (state.phase) {
                                MemoryGroupsStorePhase.REVIEW -> item {
                                    Text(t("Saving links these originals; it does not copy or rewrite them.", "保存只建立关联，不会复制或改写原话。"))
                                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        OutlinedButton(onClick = { store.backToEdit() }, modifier = Modifier.testTag("memory-group-back")) { Text(t("Edit", "返回编辑")) }
                                        Button(onClick = { store.confirmSave() }, modifier = Modifier.testTag("memory-group-save")) { Text(t("Confirm save", "确认保存")) }
                                    }
                                }
                                MemoryGroupsStorePhase.SAVING -> item { LinearProgressIndicator(Modifier.fillMaxWidth()); Text(t("Saving…", "正在保存…")) }
                                MemoryGroupsStorePhase.UNCERTAIN -> item {
                                    Text(t("The save may have succeeded. Retry the same save to confirm, without changing the group.", "保存可能已成功。请重试相同保存，先确认结果。"))
                                    Button(onClick = { store.retryUncertain() }, enabled = clock >= state.retryAtMillis,
                                        modifier = Modifier.testTag("memory-group-retry")) { Text(t("Retry same save", "重试相同保存")) }
                                }
                                MemoryGroupsStorePhase.CONFLICT -> item {
                                    Text(t("Someone changed this group. Reload the current revision before reviewing your changes again.", "回忆组已被更新。请先重新读取当前版本，再检查你的修改。"))
                                    OutlinedButton(onClick = { store.reloadConflict() }, enabled = clock >= state.retryAtMillis,
                                        modifier = Modifier.testTag("memory-group-conflict-reload")) { Text(t("Reload current group", "重新读取回忆组")) }
                                    if (state.canUseReloadedRevision) Button(onClick = { store.useReloadedRevision() },
                                        modifier = Modifier.testTag("memory-group-conflict-use")) { Text(t("Keep my changes for review", "保留我的修改并重新检查")) }
                                }
                                else -> Unit
                            }
                        }
                        if (state.message != null) item {
                            Text(t("This operation could not complete. Check your connection or refresh before trying again.",
                                "此操作暂未完成。请检查连接，或刷新后再试。"), color = MaterialTheme.colorScheme.error,
                                modifier = Modifier.testTag("memory-group-problem"))
                        }
                    }
                }
            }
        }
    }
    if (discard) AlertDialog(onDismissRequest = { discard = false },
        title = { Text(t("Leave this group?", "离开回忆组？")) },
        text = { Text(if (state.phase == MemoryGroupsStorePhase.UNCERTAIN)
            t("The save may already have succeeded. Leaving discards this retry request, not a saved group.", "保存可能已经成功。离开会丢弃此次重试请求，不会删除已保存的回忆组。")
            else t("Your unsaved changes will be discarded.", "未保存的修改将被丢弃。")) },
        confirmButton = { TextButton(onClick = { if (onClose(true)) discard = false }, modifier = Modifier.testTag("memory-group-discard")) { Text(t("Leave", "离开")) } },
        dismissButton = { TextButton(onClick = { discard = false }) { Text(t("Keep editing", "继续编辑")) } })
}

@Composable
private fun MemoryGroupAssetRow(store: MemoryGroupsStore, asset: Asset, bytes: ByteArray?, words: Words, zh: Boolean,
    action: (() -> Unit)?, actionText: String, tag: String) {
    LaunchedEffect(store, asset.id) { store.loadPreview(asset.id) }
    val bitmap = remember(bytes) { bytes?.let {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(it, 0, it.size, bounds)
        if (bounds.outWidth in 1..1024 && bounds.outHeight in 1..1024)
            BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() else null
    } }
    Card(Modifier.fillMaxWidth().testTag(tag)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (bitmap != null) Image(bitmap, contentDescription = null, Modifier.size(76.dp), contentScale = ContentScale.Crop)
                Column(Modifier.weight(1f)) {
                    Text(if (zh) "${if (asset.kind == "video") "视频" else "照片"} · ${asset.id}" else "${if (asset.kind == "video") "Video" else "Photo"} · ${asset.id}", style = MaterialTheme.typography.titleSmall)
                    val date = memoryGroupRecordedDate(asset.taken_at, zh)
                    Text(if (date != null) (if (zh) "拍摄时间 · " else "Recorded time · ") + date
                        else if (asset.taken_at == null) words.date(asset)
                        else if (zh) "拍摄时间未知" else "Capture time unknown", style = MaterialTheme.typography.bodySmall)
                }
            }
            if (action != null) TextButton(onClick = action, modifier = Modifier.testTag("$tag-action")) { Text(actionText) }
        }
    }
}

@Composable
private fun MemoryGroupCard(group: MemoryGroup, zh: Boolean, onEdit: () -> Unit) {
    Card(Modifier.fillMaxWidth().testTag("memory-group-${group.id}")) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(memoryGroupTheme(group.theme, zh), style = MaterialTheme.typography.titleLarge)
            Text(if (zh) "${group.assetIds.size} 项内容 · ${group.sources.size} 段讲述" else
                "${group.assetIds.size} ${if (group.assetIds.size == 1) "moment" else "moments"} · ${group.sources.size} ${if (group.sources.size == 1) "memory" else "memories"}")
            group.sources.forEach { MemoryGroupOriginal(it, zh) }
            if (group.canEdit) OutlinedButton(onClick = onEdit, modifier = Modifier.testTag("memory-group-edit-${group.id}")) { Text(if (zh) "调整回忆组" else "Edit group") }
        }
    }
}

@Composable
private fun MemoryGroupOriginal(source: ProtectedStory, zh: Boolean) {
    var expanded by remember(source.id, source.revision) { mutableStateOf(false) }
    if (source.title.isNotBlank()) Text(source.title, style = MaterialTheme.typography.titleSmall)
    Text(if (zh) "讲述人：${source.byline.ifBlank { "家人" }}" else "Told by: ${source.byline.ifBlank { "Family member" }}", style = MaterialTheme.typography.labelLarge)
    Text(source.text, maxLines = if (expanded) Int.MAX_VALUE else 4, overflow = TextOverflow.Ellipsis)
    TextButton(onClick = { expanded = !expanded }) { Text(if (expanded) { if (zh) "收起原话" else "Collapse original" } else { if (zh) "阅读原话" else "Read original" }) }
}

private fun memoryGroupTheme(theme: String, zh: Boolean) = when (theme) {
    "trip" -> if (zh) "旅途" else "Travel"
    "growing_up" -> if (zh) "成长" else "Growing up"
    "birthday" -> if (zh) "生日" else "Birthday"
    "grandparents" -> if (zh) "祖辈" else "Grandparents"
    "year_in_review" -> if (zh) "年度回忆" else "Year in review"
    else -> if (zh) "日常" else "Everyday"
}
