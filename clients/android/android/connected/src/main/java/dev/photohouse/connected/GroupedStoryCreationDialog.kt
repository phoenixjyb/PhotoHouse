package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import dev.photohouse.connected.core.*
import dev.photohouse.protocol.Asset

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun GroupedStoryCreationDialog(store: ConnectedStore, creation: GroupedStoryCreationState, zh: Boolean) {
    val words = remember(zh) { Words(zh) }
    val currentCreation by rememberUpdatedState(creation)
    var discard by remember(store) { mutableStateOf(false) }
    val editor = creation.editor
    val editorState by editor?.state?.collectAsState() ?: remember { mutableStateOf(StoryWorkspaceStoreState()) }
    var requestedPage by remember(editor) { mutableIntStateOf(creation.gallery?.page ?: 1) }

    fun t(en: String, cn: String) = if (zh) cn else en
    fun latestSelection(): GroupedStoryCreationState? {
        val live = store.state.value.groupedStoryCreation ?: return null
        if (editor == null || live.editor !== editor || live.canCreate != true) return null
        if (editor.state.value.status != StoryWorkspaceStoreStatus.SELECTION || live.pageBusy) return null
        return live
    }
    fun requestClose() {
        if (store.state.value.groupedStoryCreation !== currentCreation &&
            store.state.value.groupedStoryCreation?.editor !== editor) return
        if (!store.closeGroupedStoryCreation()) discard = true
    }

    Dialog(
        onDismissRequest = ::requestClose,
        properties = DialogProperties(usePlatformDefaultWidth = false, dismissOnBackPress = true, dismissOnClickOutside = false),
    ) {
        PhotoHouseTheme {
            Surface(
                Modifier.fillMaxSize().safeDrawingPadding().testTag("grouped-story-creation"),
                color = MaterialTheme.colorScheme.background,
            ) {
                when {
                    editor != null && editorState.status != StoryWorkspaceStoreStatus.SELECTION ->
                        GroupedStoryReview(
                            editor,
                            zh,
                            onClose = { store.closeGroupedStoryCreation(discard = true) },
                            onReadSaved = { store.readCreatedGroupedStory() },
                        )
                    creation.checking -> Column(
                        Modifier.fillMaxSize().padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Header(t("Create a family story", "创建家庭故事"), t("Close", "关闭"), ::requestClose)
                        LinearProgressIndicator(Modifier.fillMaxWidth())
                        Text(t("Checking library access…", "正在检查资料库访问权限…"))
                    }
                    creation.canCreate == false -> Column(
                        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Header(t("Create a family story", "创建家庭故事"), t("Close", "关闭"), ::requestClose)
                        Text(
                            t(
                                "Only a library owner or contributor can create a grouped story. Ask the library owner to grant contributor access.",
                                "只有资料库所有者或贡献者可以创建组合故事。请联系资料库所有者授予贡献者权限。",
                            ),
                            style = MaterialTheme.typography.bodyLarge,
                        )
                    }
                    editor == null -> Column(
                        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Header(t("Create a family story", "创建家庭故事"), t("Close", "关闭"), ::requestClose)
                        Text(creation.problem?.let { words.message(it.message) }
                            ?: t("Story creation is unavailable right now.", "暂时无法创建故事。"),
                            color = MaterialTheme.colorScheme.error)
                        Button(
                            onClick = { if (store.state.value.groupedStoryCreation === currentCreation) store.beginGroupedStoryCreation() },
                            enabled = !creation.checking,
                            modifier = Modifier.fillMaxWidth().testTag("grouped-story-creation-retry"),
                        ) { Text(t("Retry", "重试")) }
                    }
                    else -> SelectionScreen(
                        store = store,
                        creation = creation,
                        editor = editor,
                        editorState = editorState,
                        zh = zh,
                        words = words,
                        requestedPage = requestedPage,
                        onRequestPage = { page ->
                            if (latestSelection() != null && store.loadGroupedStorySelectionPage(page)) requestedPage = page
                        },
                        onClose = ::requestClose,
                    )
                }
            }
        }
    }

    if (discard) AlertDialog(
        onDismissRequest = { discard = false },
        title = { Text(t("Discard this story work?", "丢弃这次故事编辑？")) },
        text = {
            Text(t(
                "Your selection and unsaved edits will be discarded. A pending save may already exist on the server.",
                "所选内容和未保存的修改将被丢弃。已经发出的保存请求可能已在服务器生效。",
            ))
        },
        confirmButton = {
            TextButton(onClick = {
                if (store.state.value.groupedStoryCreation?.editor === editor) {
                    store.closeGroupedStoryCreation(discard = true)
                }
                discard = false
            }, modifier = Modifier.testTag("grouped-story-discard-confirm")) {
                Text(t("Discard and close", "丢弃并关闭"))
            }
        },
        dismissButton = {
            TextButton(onClick = { discard = false }, modifier = Modifier.testTag("grouped-story-discard-cancel")) {
                Text(t("Keep editing", "继续编辑"))
            }
        },
    )
}

@Composable
private fun Header(title: String, close: String, onClose: () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(title, Modifier.weight(1f), style = MaterialTheme.typography.headlineSmall)
        TextButton(onClick = onClose, modifier = Modifier.testTag("grouped-story-close")) { Text(close) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SelectionScreen(
    store: ConnectedStore,
    creation: GroupedStoryCreationState,
    editor: StoryWorkspaceStore,
    editorState: StoryWorkspaceStoreState,
    zh: Boolean,
    words: Words,
    requestedPage: Int,
    onRequestPage: (Int) -> Unit,
    onClose: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val gallery = creation.gallery
    val totalPages = gallery?.let { ((it.total + it.page_size - 1) / it.page_size).coerceAtLeast(1).coerceAtMost(Int.MAX_VALUE.toLong()).toInt() } ?: 1
    val items = gallery?.items.orEmpty().filter { it.kind == "image" || it.kind == "video" }
    val selected = editorState.selectedAssetIds
    val canAct = !creation.pageBusy && !editorState.busy && editorState.status == StoryWorkspaceStoreStatus.SELECTION
    var limitReached by remember(editor) { mutableStateOf(false) }
    var relatedExpanded by remember(editor) { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 12.dp)) {
        Header(t("Choose moments", "选择瞬间"), t("Close", "关闭"), onClose)
        Text(t("Choose 1–24 photos or videos in story order.", "按故事顺序选择 1–24 个照片或视频。"),
            style = MaterialTheme.typography.bodyMedium)
        Text(t("${selected.size} of 24 selected", "已选择 ${selected.size} / 24"),
            style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("grouped-story-selection-count"))
        if (creation.pageBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
        creation.problem?.let { problem ->
            Text(words.message(problem.message), color = MaterialTheme.colorScheme.error)
            TextButton(
                onClick = {
                    val live = store.state.value.groupedStoryCreation
                    if (live?.editor === editor && live.canCreate == true && !live.pageBusy) {
                        store.loadGroupedStorySelectionPage(gallery?.page ?: requestedPage)
                    }
                },
                enabled = !creation.pageBusy,
                modifier = Modifier.testTag("grouped-story-selection-retry"),
            ) { Text(t("Retry page", "重试此页")) }
        }
        if (limitReached) Text(
            t("You can select up to 24 moments. Remove one before adding another.", "最多可选择 24 个瞬间。请先移除一个，再添加其他内容。"),
            color = MaterialTheme.colorScheme.error,
            modifier = Modifier.testTag("grouped-story-selection-limit"),
        )
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = { onRequestPage((gallery?.page ?: requestedPage) - 1) },
                enabled = canAct && (gallery?.page ?: requestedPage) > 1,
                modifier = Modifier.weight(1f).testTag("grouped-story-selection-previous"),
            ) { Text(t("Previous", "上一页")) }
            Text(
                if (gallery != null) t("Page ${gallery.page} of $totalPages", "第 ${gallery.page} / $totalPages 页")
                else t("Page $requestedPage", "第 $requestedPage 页"),
                Modifier.align(Alignment.CenterVertically),
            )
            OutlinedButton(
                onClick = { onRequestPage((gallery?.page ?: requestedPage) + 1) },
                enabled = canAct && gallery != null && gallery.page < totalPages,
                modifier = Modifier.weight(1f).testTag("grouped-story-selection-next"),
            ) { Text(t("Next", "下一页")) }
        }
        if (gallery == null && !creation.pageBusy && creation.problem == null) {
            Text(t("No moments are available on this page.", "此页没有可用的瞬间。"))
        }
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth().testTag("grouped-story-selection-list"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(vertical = 8.dp),
        ) {
            item(key = "same-day-related-picker") {
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    OutlinedButton(onClick = { relatedExpanded = !relatedExpanded }, modifier = Modifier.fillMaxWidth()
                        .testTag("grouped-story-related-toggle")) {
                        Text(t("More moments from the same day", "同一天的更多瞬间"))
                    }
                    if (relatedExpanded) {
                        Text(t("Suggestions use only recorded capture dates. A shared day does not prove one activity; review each item and add it explicitly.",
                            "建议只依据记录的拍摄日期。同一天不代表同一次活动；请逐项核对并手动加入。"),
                            style = MaterialTheme.typography.bodySmall)
                        OutlinedButton(onClick = { editor.loadRelatedMedia(false) },
                            enabled = canAct && selected.isNotEmpty() && !editorState.relatedBusy,
                            modifier = Modifier.fillMaxWidth().testTag("grouped-story-related-lookup")) {
                            Text(if (editorState.relatedCandidates.isEmpty()) t("Find same-day moments", "查找同一天的瞬间") else t("Refresh suggestions", "刷新建议"))
                        }
                        if (editorState.relatedBusy || creation.relatedPreviewBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
                        if (selected.size >= 24) Text(t("You have reached the 24 moment limit. Remove one before adding another.",
                            "已达到 24 个瞬间上限。请先移除一个，再加入其他内容。"), color = MaterialTheme.colorScheme.error)
                        if (editorState.relatedFailure) {
                            Text(t("Suggestions are unavailable. Your selection is unchanged.", "暂时无法获取建议，所选内容保持不变。"),
                                color = MaterialTheme.colorScheme.error)
                            TextButton(onClick = { editor.retryRelatedMedia() },
                                enabled = canAct && !editorState.relatedBusy,
                                modifier = Modifier.testTag("grouped-story-related-retry")) { Text(t("Retry", "重试")) }
                        }
                        editorState.relatedCandidates.forEach { candidate ->
                            Surface(Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.surfaceVariant, shape = MaterialTheme.shapes.medium) {
                                Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Preview(candidate.asset, creation.relatedPreviews[candidate.asset.id], words,
                                        modifier = Modifier.testTag("grouped-story-related-thumbnail-${candidate.asset.id}"))
                                    Text(t("Recorded capture date: ${candidate.asset.taken_at?.take(10).orEmpty()}",
                                        "记录的拍摄日期：${candidate.asset.taken_at?.take(10).orEmpty()}"), style = MaterialTheme.typography.bodySmall)
                                    Text(t("This is a date match only. Filename or upload date is not proof.",
                                        "这只是日期匹配；文件名日期或上传日期不能证明同一次活动。"), style = MaterialTheme.typography.bodySmall)
                                    Button(onClick = {
                                        val live = editor.state.value
                                        if (latestEditorSelection(store, editor) && !live.relatedBusy &&
                                            live.relatedCandidates.any { it.asset.id == candidate.asset.id } && candidate.asset.id !in live.selectedAssetIds) {
                                            if (editor.selectAsset(candidate.asset.id)) limitReached = false else limitReached = true
                                        }
                                    }, enabled = canAct && candidate.asset.id !in selected && selected.size < 24,
                                        modifier = Modifier.fillMaxWidth().testTag("grouped-story-related-add-${candidate.asset.id}")) {
                                        Text(t("Add to story", "加入故事"))
                                    }
                                }
                            }
                        }
                        if (editorState.relatedHasMore) OutlinedButton(onClick = { editor.loadRelatedMedia(true) },
                            enabled = canAct && !editorState.relatedBusy, modifier = Modifier.fillMaxWidth().testTag("grouped-story-related-next")) {
                            Text(t("More suggestions", "更多建议"))
                        }
                    }
                }
            }
            items(items, key = { it.id }) { asset ->
                val position = selected.indexOf(asset.id)
                SelectionAsset(
                    asset = asset,
                    bytes = creation.previews[asset.id],
                    words = words,
                    selected = position >= 0,
                    ordinal = position + 1,
                    enabled = canAct && gallery != null,
                    tag = "grouped-story-select-${asset.id}",
                    onToggle = {
                        val live = store.state.value.groupedStoryCreation
                        if (live?.editor === editor && live.canCreate == true && !live.pageBusy &&
                            live.gallery?.page == gallery?.page && live.gallery?.items?.any { it.id == asset.id && it.kind in setOf("image", "video") } == true &&
                            editor.state.value.status == StoryWorkspaceStoreStatus.SELECTION && !editor.state.value.busy) {
                            val currentlySelected = editor.state.value.selectedAssetIds
                            if (asset.id in currentlySelected) {
                                limitReached = false
                                editor.selectAsset(asset.id, false)
                            } else if (currentlySelected.size < 24) {
                                limitReached = false
                                editor.selectAsset(asset.id, true)
                            } else limitReached = true
                        }
                    },
                )
            }
        }
        Text(t("Story theme", "故事主题"), style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            groupedStoryThemes.forEach { (theme, en, cn) ->
                FilterChip(
                    selected = editorState.theme == theme,
                    onClick = { if (canAct && latestEditorSelection(store, editor)) editor.setTheme(theme) },
                    enabled = canAct,
                    label = { Text(t(en, cn)) },
                    modifier = Modifier.testTag("grouped-story-theme-$theme"),
                )
            }
        }
        Text(t("Story language", "故事语言"), style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            listOf("zh" to t("Chinese", "中文"), "en" to t("English", "英文")).forEach { (language, label) ->
                FilterChip(
                    selected = editorState.language == language,
                    onClick = { if (canAct && latestEditorSelection(store, editor)) editor.setLanguage(language) },
                    enabled = canAct,
                    label = { Text(label) },
                    modifier = Modifier.testTag("grouped-story-language-$language"),
                )
            }
        }
        Button(
            onClick = {
                val live = store.state.value.groupedStoryCreation
                if (live?.editor === editor && live.canCreate == true && !live.pageBusy &&
                    editor.state.value.status == StoryWorkspaceStoreStatus.SELECTION &&
                    editor.state.value.selectedAssetIds.isNotEmpty() && !editor.state.value.busy) editor.preview()
            },
            enabled = canAct && selected.isNotEmpty() && !creation.pageBusy,
            modifier = Modifier.fillMaxWidth().testTag("grouped-story-selection-preview"),
        ) { Text(t("Create outline", "创建提纲")) }
    }
}

@Composable
private fun SelectionAsset(
    asset: Asset,
    bytes: ByteArray?,
    words: Words,
    selected: Boolean,
    ordinal: Int,
    enabled: Boolean,
    tag: String,
    onToggle: () -> Unit,
) {
    Surface(Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.surface, shape = MaterialTheme.shapes.medium,
        tonalElevation = if (selected) 2.dp else 0.dp) {
        Column(
            Modifier.fillMaxWidth().toggleable(value = selected, enabled = enabled, role = Role.Checkbox, onValueChange = { onToggle() })
                .testTag(tag).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Preview(asset, bytes, words, modifier = Modifier.testTag("grouped-story-selection-thumbnail-${asset.id}"))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = selected, onCheckedChange = null, enabled = enabled)
                Text(
                    if (selected) words.t("Story order: $ordinal", "选择顺序：$ordinal")
                    else words.t("Select this ${if (asset.kind == "video") "video" else "photo"}", "选择此${if (asset.kind == "video") "视频" else "照片"}"),
                    Modifier.weight(1f),
                )
                if (selected) Text("#$ordinal", style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}

private fun latestEditorSelection(store: ConnectedStore, editor: StoryWorkspaceStore): Boolean {
    val live = store.state.value.groupedStoryCreation ?: return false
    return live.editor === editor && live.canCreate == true && !live.pageBusy &&
        editor.state.value.status == StoryWorkspaceStoreStatus.SELECTION && !editor.state.value.busy
}

private val groupedStoryThemes = listOf(
    Triple("everyday", "Everyday", "日常"),
    Triple("trip", "Trips", "旅行"),
    Triple("growing_up", "Growing up", "成长"),
    Triple("birthday", "Birthdays", "生日"),
    Triple("grandparents", "Grandparents", "祖辈"),
    Triple("year_in_review", "Year in review", "年度回顾"),
)
