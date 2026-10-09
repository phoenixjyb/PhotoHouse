package dev.photohouse.connected

import android.graphics.BitmapFactory
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import dev.photohouse.connected.core.*

@OptIn(ExperimentalFoundationApi::class, ExperimentalLayoutApi::class)
@Composable
internal fun MemoryBooksDialog(
    reading: MemoryBooksReading, store: ConnectedStore, zh: Boolean, onPage: (Int) -> Unit, onBook: (String) -> Unit,
    onStory: (Int) -> Unit, onResume: () -> Unit, onChapter: (Int) -> Unit, onFramePage: (Int) -> Unit, onFrame: (String) -> Unit,
    onOpenAsset: (String) -> Unit, onBack: () -> Unit, onClose: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val density = LocalDensity.current
    val liveState by store.state.collectAsState()
    val editorial by store.memoryBookEditorialState.collectAsState()
    val editorialCatalog by store.memoryBookEditorialCatalogState.collectAsState()
    val edition by store.memoryBookEditionState.collectAsState()
    val narrative by store.memoryBookNarrativeState.collectAsState()
    val book = reading.selectedBook
    val index = reading.storyIndex
    val story = reading.story
    val chapter = story?.chapters?.getOrNull(reading.selectedChapter)
    val lifecycleOwner = LocalLifecycleOwner.current
    val readerAudio = remember(liveState.session?.account_id, reading.library, book?.id) { ReaderAudioCoordinator() }
    DisposableEffect(lifecycleOwner, store, reading.library, book?.id) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_PAUSE || event == Lifecycle.Event.ON_STOP) {
                store.closeMemoryBookEditorialSourceInspection()
                store.closeMemoryBookEditionShelfReading()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            store.closeMemoryBookEditorialSourceInspection()
        }
    }
    var sourcesExpanded by remember(liveState.session?.account_id, reading.library, book?.id, book?.revision, story?.id, story?.revision, chapter?.id) { mutableStateOf(false) }
    var companionExpanded by remember(book?.id) { mutableStateOf(false) }
    var narrativeExpanded by remember(liveState.session?.account_id, reading.library, book?.id, book?.revision) { mutableStateOf(false) }
    var confirmReaderExit by remember(book?.id, book?.revision) { mutableStateOf(false) }
    var deferredReaderExit by remember(book?.id, book?.revision) { mutableStateOf<(() -> Unit)?>(null) }
    var unresolvedEditionExit by remember(book?.id, book?.revision) { mutableStateOf(false) }
    var unresolvedEditorialExit by remember(book?.id, book?.revision) { mutableStateOf(false) }
    val emptyDictationState = remember { kotlinx.coroutines.flow.MutableStateFlow(MemoryDictationState()) }
    val dictationFlow = reading.companion?.dictation?.state ?: emptyDictationState
    val dictationState by dictationFlow.collectAsState()
    val narrativeDictationStore by store.memoryBookNarrativeDictationState.collectAsState()
    val emptyNarrativeDictationState = remember { kotlinx.coroutines.flow.MutableStateFlow(MemoryDictationState()) }
    val narrativeDictationFlow = narrativeDictationStore?.state ?: emptyNarrativeDictationState
    val narrativeDictationState by narrativeDictationFlow.collectAsState()
    val ownVoiceUnfinished = narrativeDictationState.loading || narrativeDictationState.recording ||
        narrativeDictationState.transcribing || narrativeDictationState.transcript != null
    val chat = reading.companion
    val hasUnsentCompanionWork = chat != null && (
        chat.draft.isNotBlank() || chat.threadDrafts.values.any(String::isNotBlank) ||
            chat.pendingConversation != null || chat.pendingTurn != null || chat.busy ||
            dictationState.loading || dictationState.recording || dictationState.transcribing ||
            dictationState.transcript?.isNotBlank() == true
        )
    val frozenEditorialSave = editorial.status in setOf(MemoryBookEditorialStoreStatus.SAVING, MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN)
    val hasUnsentEditorialWork = editorial.dirty || frozenEditorialSave || editorial.status == MemoryBookEditorialStoreStatus.CONFLICT
    fun exitReader(action: () -> Unit) {
        if (edition.status == MemoryBookEditionStatus.SAVING ||
            (edition.hasPendingSave && edition.status != MemoryBookEditionStatus.CONFLICT)) {
            unresolvedEditionExit = true
        } else if (frozenEditorialSave) {
            deferredReaderExit = action
            unresolvedEditorialExit = true
        } else if (hasUnsentCompanionWork || ownVoiceUnfinished || hasUnsentEditorialWork || edition.dirty || edition.composing || edition.busy ||
            edition.status == MemoryBookEditionStatus.CONFLICT || narrative.hasUnfinishedInput ||
            narrative.busy || narrative.pendingRequest != null || narrative.job?.state in setOf("queued", "running")) {
            deferredReaderExit = action
            confirmReaderExit = true
        } else action()
    }
    val memoirReaderScroll = key(liveState.session?.account_id, liveState.generation, reading.library,
        reading.selectedBook?.id, reading.selectedBook?.revision) { rememberScrollState() }
    val originalStart = remember(liveState.session?.account_id, liveState.generation,
        reading.library, book?.id, book?.revision) { BringIntoViewRequester() }
    LaunchedEffect(reading.readerScopeId, story?.id, story?.revision) {
        if (narrativeExpanded && story != null && !reading.readerBusy) {
            withFrameNanos { }
            originalStart.bringIntoView()
        }
    }
    val activeAsset = story?.items?.firstOrNull { it.asset.id == reading.selectedAssetId }?.asset
    val heroBytes = reading.hero.takeIf { reading.heroAssetId == reading.selectedAssetId }
        ?: reading.selectedAssetId?.let(reading.frames::get)
    val heroBitmap = remember(heroBytes) { heroBytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() } }
    // Let the dialog respect the window's available height when the keyboard opens.
    // ReaderDialogSystemBars expands the window without Compose's display-sized measurement.
    Dialog(onDismissRequest = { exitReader(onClose) }, properties = DialogProperties(usePlatformDefaultWidth = true, decorFitsSystemWindows = false)) {
        CompositionLocalProvider(LocalDensity provides density, LocalReaderAudioCoordinator provides readerAudio) {
            val fontScale = LocalDensity.current.fontScale
            PhotoHouseTheme {
                // A resized window may have zero overlap with a visible IME.
                // Its visibility, rather than inset height, controls compact UI.
                val keyboardVisible = WindowInsets.isImeVisible
                ReaderDialogSystemBars(keyboardVisible)
                Surface(Modifier.fillMaxSize().testTag("memory-books"), color = MaterialTheme.colorScheme.background) {
                    Column(Modifier.fillMaxSize().safeDrawingPadding().padding(horizontal = 20.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Box(Modifier.size(0.dp).testTag("memory-books-font-scale-$fontScale"))
                        if (keyboardVisible) Box(Modifier.size(0.dp).testTag("memory-books-ime-visible"))
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(t("Family memoir shelf", "家庭回忆册"), modifier = Modifier.weight(1f).testTag("memory-books-heading"),
                                style = if (keyboardVisible) MaterialTheme.typography.titleMedium else MaterialTheme.typography.headlineSmall,
                                fontFamily = FontFamily.Serif)
                            TextButton(onClick = { exitReader(onClose) }, modifier = Modifier.testTag("memory-books-close")) { Text(t("Close", "关闭")) }
                        }
                        when {
                            reading.busy -> { LinearProgressIndicator(Modifier.fillMaxWidth()); Text(t("Checking access and loading books…", "正在检查访问权限并加载回忆册…")) }
                            reading.problem != null -> Column {
                                Text(t("Books are temporarily unavailable.", "暂时无法读取回忆册。"), color = MaterialTheme.colorScheme.error)
                                OutlinedButton(onClick = { onPage(reading.page) }, modifier = Modifier.testTag("memory-books-retry")) { Text(t("Retry", "重试")) }
                            }
                            book != null -> {
                                if (!keyboardVisible) TextButton(onClick = { exitReader(onBack) }, modifier = Modifier.testTag("memory-books-back")) { Text(t("‹ All books", "‹ 所有回忆册")) }
                                Text(book.title, style = if (keyboardVisible) MaterialTheme.typography.titleSmall else MaterialTheme.typography.headlineMedium,
                                    fontFamily = FontFamily.Serif, maxLines = if (keyboardVisible) 1 else 2,
                                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                                Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(memoirReaderScroll)
                                    .testTag("memory-book-reader-scroll"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                    if (book.introduction.isNotBlank()) Text(book.introduction, style = MaterialTheme.typography.bodyLarge)
                                    MemoryBookEditionShelfPanel(store, reading, zh,
                                        speechEnabled = !ownVoiceUnfinished && !dictationState.loading &&
                                            !dictationState.recording && !dictationState.transcribing)
                                    if (book.canEdit) MemoryBookEditorialPanel(
                                        book = book, store = store, state = editorial, catalog = editorialCatalog, zh = zh,
                                        inspection = reading.sourceInspection,
                                        companionBusy = ownVoiceUnfinished || chat?.let { it.busy || it.pendingConversation != null || it.pendingTurn != null ||
                                            dictationState.loading || dictationState.recording || dictationState.transcribing || dictationState.transcript != null } == true ||
                                            narrative.busy || narrative.pendingRequest != null || narrative.job?.state in setOf("queued", "running"),
                                    )
                                    if (book.canEdit && reading.capabilities?.generationEnabled == true) {
                                        OutlinedButton(onClick = { narrativeExpanded = !narrativeExpanded },
                                            enabled = !ownVoiceUnfinished && !edition.composing && !edition.invalidInput,
                                            modifier = Modifier.fillMaxWidth().testTag("memory-book-narrative-disclosure")) {
                                            Text(if (narrativeExpanded) t("Hide memoir suggestions", "收起整本整理建议")
                                                else t("Arrange this memoir with AI", "整理整本回忆册"))
                                        }
                                        if (narrativeExpanded) MemoryBookNarrativePanel(store, reading, narrative, zh)
                                    }
                                    when {
                                        reading.readerBusy -> LinearProgressIndicator(Modifier.fillMaxWidth())
                                        reading.readerUnavailable -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                            Text(t("This story moved or changed in the book.", "故事在回忆册中的位置或内容已变化。"),
                                                color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("memory-book-story-unavailable"))
                                            OutlinedButton(onClick = { exitReader { onBack(); onPage(reading.page) } }, modifier = Modifier.testTag("memory-book-refresh")) { Text(t("Refresh shelf", "刷新回忆册")) }
                                        }
                                        story != null && chapter != null && index != null -> {
                                            Text(story.title, style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif, modifier = Modifier.bringIntoViewRequester(originalStart).testTag("memory-book-story-title"))
                                            Text(t("Story ${index + 1} of ${book.stories.size}", "故事 ${index + 1}/${book.stories.size}"))
                                            ChapterReadAloud("${story.title}. ${chapter.title}. ${chapter.narration}", story.language,
                                                listOf("memoir", liveState.session?.account_id, reading.library, book.id, book.revision, story.id, story.revision, chapter.id), zh,
                                                enabled = chapter.narration.isNotBlank())
                                            Box(Modifier.fillMaxWidth().aspectRatio(1.6f).testTag("memory-book-hero"), contentAlignment = Alignment.Center) {
                                                if (heroBitmap != null) Image(heroBitmap, null, Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
                                                else if (reading.heroBusy || reading.framesBusy) CircularProgressIndicator()
                                                else Text(if (reading.heroUnavailable) t("Preview unavailable", "预览不可用") else t("Select a moment", "选择一个片段"))
                                            }
                                            Text(chapter.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("memory-book-chapter-title"))
                                            Text(chapter.narration, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.testTag("memory-book-story-text"))
                                            ChapterSourceReferences(
                                                chapterSourceReferences(chapter, story), zh, sourcesExpanded,
                                                { sourcesExpanded = it }, "memory-book-sources",
                                            )
                                            OutlinedButton(onClick = { companionExpanded = !companionExpanded },
                                                modifier = Modifier.fillMaxWidth().testTag("memory-book-chat-disclosure")) {
                                                Text(if (companionExpanded) t("Hide memoir conversation", "收起回忆册对话")
                                                    else t("Talk about this memoir", "聊聊这本回忆册"))
                                            }
                                            if (companionExpanded) MemoryBookCompanionPanel(store, reading, zh)
                                            if (chapter.assetIds.isNotEmpty()) {
                                                Text(t("Moments", "故事片段"), style = MaterialTheme.typography.labelLarge)
                                                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("memory-book-frames")) {
                                                    val framePageIds = chapter.assetIds.drop(reading.framePage * 8).take(8)
                                                    items(framePageIds, key = { it }) { assetId ->
                                                        val bytes = reading.frames[assetId]
                                                        val bitmap = remember(bytes) { bytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() } }
                                                        Card(Modifier.width(104.dp).clickable(enabled = !reading.framesBusy) { onFrame(assetId) }.testTag("memory-book-frame-$assetId")) {
                                                            if (bitmap != null) Image(bitmap, null, Modifier.fillMaxWidth().height(68.dp), contentScale = ContentScale.Crop)
                                                            else Box(Modifier.fillMaxWidth().height(68.dp), contentAlignment = Alignment.Center) {
                                                                Text(when {
                                                                    reading.framesBusy -> t("Loading", "加载中")
                                                                    reading.framesUnavailable || assetId in reading.unavailableFrameIds -> t("Unavailable", "不可用")
                                                                    else -> t("Not loaded", "尚未加载")
                                                                })
                                                            }
                                                            Text(when (story.items.firstOrNull { it.asset.id == assetId }?.asset?.kind) {
                                                                "video" -> t("Video", "视频")
                                                                "image" -> t("Photo", "照片")
                                                                else -> t("Media", "媒体")
                                                            }, Modifier.padding(6.dp))
                                                        }
                                                    }
                                                }
                                                val pageCount = (chapter.assetIds.size + 7) / 8
                                                if (pageCount > 1) MemoirNavigation(
                                                    "${reading.framePage + 1} / $pageCount",
                                                    t("Previous moments", "上一组片段"), t("Next moments", "下一组片段"),
                                                    !reading.framesBusy && reading.framePage > 0,
                                                    !reading.framesBusy && reading.framePage < pageCount - 1,
                                                    { onFramePage(reading.framePage - 1) }, { onFramePage(reading.framePage + 1) },
                                                    "memory-book-previous-frame-page", "memory-book-next-frame-page")
                                                OutlinedButton(onClick = { exitReader { activeAsset?.id?.let(onOpenAsset) } }, enabled = activeAsset != null,
                                                    modifier = Modifier.fillMaxWidth().testTag("memory-book-open-media")) {
                                                    Text(if (activeAsset?.kind == "video") t("Open video", "打开视频") else t("Open photo", "打开照片"))
                                                }
                                            }
                                            if (narrativeExpanded) MemoryBookOriginalNavigation(reading, zh, onChapter, onStory)
                                        }
                                        else -> {
                                            if (reading.resumePosition != null) Button(onClick = onResume, modifier = Modifier.fillMaxWidth().testTag("memory-book-resume")) {
                                                Text(t("Continue last read", "继续上次阅读"))
                                            }
                                            book.stories.forEachIndexed { i, item ->
                                                Card(onClick = { onStory(i) }, modifier = Modifier.fillMaxWidth().testTag("memory-book-entry-$i")) {
                                                    Column(Modifier.padding(16.dp)) {
                                                        Text(item.title, style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif)
                                                        Text(t("${item.itemCount} moments", "${item.itemCount} 个片段"))
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                if (!narrativeExpanded && !keyboardVisible) MemoryBookOriginalNavigation(reading, zh, onChapter, onStory)
                            }
                            else -> {
                                Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                    val books = reading.result?.items.orEmpty()
                                    if (books.isEmpty()) Text(t("No books on this page.", "此页没有回忆册。"))
                                    books.forEach { item ->
                                        Card(onClick = { onBook(item.id) }, modifier = Modifier.fillMaxWidth().testTag("memory-book-${item.id}")) {
                                            Column(Modifier.padding(16.dp)) {
                                                Text(item.title, style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif)
                                                Text(t("${item.stories.size} stories", "${item.stories.size} 则故事"))
                                            }
                                        }
                                    }
                                }
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                    OutlinedButton(onClick = { onPage(reading.page - 1) }, enabled = reading.page > 1,
                                        modifier = Modifier.testTag("memory-books-previous-page")) { Text(t("Previous", "上一页")) }
                                    Text(t("Page ${reading.page}", "第 ${reading.page} 页"))
                                    Button(onClick = { onPage(reading.page + 1) }, enabled = reading.result?.hasMore == true,
                                        modifier = Modifier.testTag("memory-books-next-page")) { Text(t("Next", "下一页")) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    if (confirmReaderExit) AlertDialog(
        onDismissRequest = { confirmReaderExit = false; deferredReaderExit = null },
        title = { Text(t("Unsaved memoir work", "尚未保存的回忆内容")) },
        text = { Text(t("This memoir has unsent words, a recording, or unfinished work. Discard the local draft and leave? A submitted request may still be processing.",
            "回忆册中仍有未发送的内容、录音或待处理请求。放弃本地草稿并离开吗？已提交的请求可能仍在处理中。")) },
        confirmButton = {
            TextButton(onClick = {
                val action = deferredReaderExit
                confirmReaderExit = false
                deferredReaderExit = null
                action?.invoke()
            }, modifier = Modifier.testTag("memory-book-discard-confirm")) { Text(t("Discard and leave", "放弃草稿并离开")) }
        },
        dismissButton = {
            TextButton(onClick = { confirmReaderExit = false; deferredReaderExit = null },
                modifier = Modifier.testTag("memory-book-discard-cancel")) { Text(t("Keep editing", "继续编辑")) }
        },
        modifier = Modifier.testTag("memory-book-discard-dialog"),
    )
    if (unresolvedEditionExit) AlertDialog(onDismissRequest = { unresolvedEditionExit = false },
        title = { Text(t("Confirm the edition save", "先确认版本保存")) },
        text = { Text(t("Keep this manuscript until the save result is confirmed. Retry sends the same request.",
            "请保留这份稿件，先确认保存结果。重试会发送同一份请求。")) },
        confirmButton = { TextButton(onClick = { unresolvedEditionExit = false; store.retryMemoryBookEditionSave() },
            enabled = edition.status == MemoryBookEditionStatus.SAVE_UNCERTAIN,
            modifier = Modifier.testTag("memory-edition-exit-retry")) { Text(t("Retry the same save", "重试同一保存")) } },
        dismissButton = { TextButton(onClick = { unresolvedEditionExit = false }, modifier = Modifier.testTag("memory-edition-exit-stay")) { Text(t("Stay here", "留在此处")) } },
        modifier = Modifier.testTag("memory-edition-exit-dialog"))
    if (unresolvedEditorialExit) MemoryBookEditorialUncertainExitDialog(zh, editorial.status,
        onRetry = { unresolvedEditorialExit = false; store.retryMemoryBookEditorialSave() },
        onLeave = { val action = deferredReaderExit; unresolvedEditorialExit = false; deferredReaderExit = null; action?.invoke() },
        onStay = { unresolvedEditorialExit = false; deferredReaderExit = null })
}

@Composable
internal fun MemoryBookEditorialUncertainExitDialog(
    zh: Boolean, status: MemoryBookEditorialStoreStatus, onRetry: () -> Unit, onLeave: () -> Unit, onStay: () -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    AlertDialog(
        onDismissRequest = onStay,
        title = { Text(t("Save status needs review", "需要确认保存状态")) },
        text = { Text(t("The server may have accepted this save. You can retry the exact request, keep editing here, or leave and check the memoir later; leaving clears this local draft.",
            "服务端可能已接受此次保存。你可以重试同一请求、留在此处继续处理，或先离开稍后核对；离开会清除本地草稿。")) },
        confirmButton = {
            Row {
                TextButton(onClick = onRetry, enabled = status == MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN,
                    modifier = Modifier.testTag("memory-book-editorial-exit-retry")) { Text(t("Retry", "重试")) }
                TextButton(onClick = onLeave, enabled = status == MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN,
                    modifier = Modifier.testTag("memory-book-editorial-exit-later")) { Text(t("Leave and check later", "先离开，稍后核对")) }
            }
        },
        dismissButton = { TextButton(onClick = onStay, modifier = Modifier.testTag("memory-book-editorial-exit-stay")) { Text(t("Keep editing", "继续编辑")) } },
        modifier = Modifier.testTag("memory-book-editorial-exit-dialog"),
    )
}

@Composable
internal fun MemoryBookEditorialPanel(
    book: MemoryBook, store: ConnectedStore, state: MemoryBookEditorialStoreState,
    catalog: MemoryBookEditorialCatalogState, zh: Boolean, companionBusy: Boolean,
    inspection: MemoryBookEditorialSourceInspectionState = MemoryBookEditorialSourceInspectionState(),
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val liveState by store.state.collectAsState()
    val currentSession = liveState.session
    val currentLibrary = liveState.memoryBooks?.library.orEmpty()
    val panelScope = listOf(currentSession?.account_id.orEmpty(), currentLibrary, book.id).joinToString("/")
    var expanded by remember(panelScope) { mutableStateOf(false) }
    var introRefs by remember(panelScope) { mutableStateOf(emptyList<EditorialSourceIdentity>()) }
    var transitions by remember(panelScope) { mutableStateOf(book.stories.zipWithNext { left, right ->
        EditorialTransition(left.id, right.id, "", emptyList())
    }) }
    var openTransitions by remember(panelScope) { mutableStateOf(emptySet<Int>()) }
    var discardConfirmation by remember(panelScope) { mutableStateOf(false) }
    var reviewedDraftError by remember(panelScope) { mutableStateOf(false) }
    LaunchedEffect(panelScope, state.status, state.draft) {
        state.draft?.let {
            introRefs = it.introductionSourceRefs
            transitions = it.transitions.map { transition -> transition.copy(sourceRefs = transition.sourceRefs.toList()) }
        }
    }
    val titles = book.stories.associate { it.id to it.title }
    Card(Modifier.fillMaxWidth().testTag("memory-book-editorial-card")) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = {
                val opening = !expanded
                expanded = opening
                if (opening) store.openMemoryBookEditorial() else store.closeMemoryBookEditorialSourceInspection()
            }, modifier = Modifier.fillMaxWidth().testTag("memory-book-editorial-disclosure")) {
                Text(if (expanded) t("Hide memoir arrangement", "收起编排") else t("Arrange memoir", "编排回忆册"))
            }
            if (expanded) {
                when {
                    catalog.busy || state.status == MemoryBookEditorialStoreStatus.LOADING -> LinearProgressIndicator(Modifier.fillMaxWidth())
                    catalog.unavailable -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(t("Source labels are unavailable. The memoir reader is still available.", "暂时无法读取来源标签，仍可继续阅读回忆册。"),
                            color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("memory-book-editorial-catalog-unavailable"))
                        OutlinedButton(onClick = { store.openMemoryBookEditorial(forceReload = true) }, modifier = Modifier.fillMaxWidth().testTag("memory-book-editorial-catalog-retry")) {
                            Text(t("Retry source labels", "重试读取来源标签"))
                        }
                    }
                    state.status == MemoryBookEditorialStoreStatus.UNAVAILABLE -> Column {
                        Text(t("Memoir arrangement is unavailable for this library.", "此资料库暂不提供回忆编排。"), modifier = Modifier.testTag("memory-book-editorial-unavailable"))
                        OutlinedButton(onClick = { store.reloadMemoryBookEditorial() }, modifier = Modifier.fillMaxWidth().testTag("memory-book-editorial-retry-load")) {
                            Text(t("Retry memoir arrangement", "重试读取回忆编排"))
                        }
                    }
                    state.status == MemoryBookEditorialStoreStatus.ACCESS_REVOKED -> Text(t("Access changed. Close and reopen the memoir shelf.", "访问权限已变化，请关闭后重新打开回忆册。"),
                        color = MaterialTheme.colorScheme.error)
                    else -> {
                        Text(when (state.status) {
                            MemoryBookEditorialStoreStatus.CONFLICT -> t("This memoir changed. Review the current version before saving.", "回忆册已变化，请先检查当前版本再保存。")
                            MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN -> t("The save result is unknown. Retry sends the same saved request.", "保存结果尚未确认；重试会发送同一请求。")
                            MemoryBookEditorialStoreStatus.SAVING -> t("Saving…", "正在保存…")
                            MemoryBookEditorialStoreStatus.INVALID -> t("Review the selected sources and transition lengths.", "请检查所选来源和过渡文字长度。")
                            MemoryBookEditorialStoreStatus.ERROR -> t("Could not load or save memoir arrangement.", "无法读取或保存回忆编排。")
                            else -> t("Choose source labels for the introduction and add text between neighboring stories.", "为引言引用家人的回忆，再把相邻故事衔接起来。")
                        }, modifier = Modifier.testTag("memory-book-editorial-status"))
                        val eligible = catalog.sources
                        val chooserScope = listOf(
                            panelScope, state.revision,
                            book.stories.joinToString(";") { "${it.id}:${it.revision}" },
                        )
                            .joinToString("/")
                        val editorialControlsEnabled = !companionBusy && !frozenEditorialSave(state.status)
                        val referenceCount = introRefs.size + transitions.sumOf { it.sourceRefs.size }
                        Text(t("Selected references: $referenceCount/96", "已选来源：$referenceCount/96"), style = MaterialTheme.typography.labelMedium)
                        Text(t("Introduction sources", "引言来源"), style = MaterialTheme.typography.titleSmall)
                        EditorialSourceChooser(eligible, introRefs, titles, zh, "intro", chooserScope,
                            introRefs.size < 12 && referenceCount < 96, editorialControlsEnabled,
                            { refs ->
                                if (!editorialControlsEnabled) return@EditorialSourceChooser
                                introRefs = refs; reviewedDraftError = false; store.editMemoryBookEditorial(refs, transitions)
                            },
                            inspection.source, store::inspectMemoryBookEditorialSource)
                        transitions.forEachIndexed { index, transition ->
                            val left = titles[transition.leftStoryId] ?: t("Earlier story", "前一则故事")
                            val right = titles[transition.rightStoryId] ?: t("Next story", "后一则故事")
                            val isOpen = index in openTransitions
                            OutlinedButton(onClick = { openTransitions = if (isOpen) openTransitions - index else openTransitions + index },
                                modifier = Modifier.fillMaxWidth().testTag("memory-book-transition-$index")) {
                                Text("${if (isOpen) "⌄" else "›"} $left → $right")
                            }
                            if (isOpen) {
                                OutlinedTextField(value = transition.text, onValueChange = { value ->
                                    if (editorialControlsEnabled && value.toByteArray(Charsets.UTF_8).size <= 6000) {
                                        transitions = transitions.toMutableList().also { it[index] = transition.copy(text = value) }
                                        reviewedDraftError = false
                                        store.editMemoryBookEditorial(introRefs, transitions)
                                    }
                                }, enabled = editorialControlsEnabled,
                                    modifier = Modifier.fillMaxWidth().testTag("memory-book-transition-text-$index"),
                                    label = { Text(t("Transition text", "衔接文字")) }, minLines = 2,
                                    supportingText = {
                                        val count = transition.text.codePointCount(0, transition.text.length)
                                        val remaining = ((6000 - transition.text.toByteArray(Charsets.UTF_8).size) * 100 / 6000).coerceIn(0, 100)
                                        Text(t("$count characters · $remaining% remaining", "已写 $count 字 · 剩余 $remaining%"))
                                    })
                                if (transition.text.isNotBlank() && transition.sourceRefs.isEmpty()) Text(
                                    t("Add a source label for this transition.", "请为这段过渡文字添加来源标签。"), color = MaterialTheme.colorScheme.error)
                                val pairSources = eligible.filter { it.storyId == transition.leftStoryId || it.storyId == transition.rightStoryId }
                                EditorialSourceChooser(pairSources, transition.sourceRefs, titles, zh, "transition-$index", chooserScope,
                                    transition.sourceRefs.size < 12 && referenceCount < 96, editorialControlsEnabled, { refs ->
                                    if (!editorialControlsEnabled) return@EditorialSourceChooser
                                    val next = transitions.toMutableList().also { it[index] = transition.copy(sourceRefs = refs) }
                                    transitions = next
                                    reviewedDraftError = false
                                    store.editMemoryBookEditorial(introRefs, next)
                                }, inspection.source, store::inspectMemoryBookEditorialSource)
                            }
                        }
                        EditorialSourceInspector(inspection, store, zh)
                        if (state.status == MemoryBookEditorialStoreStatus.CONFLICT) {
                            OutlinedButton(onClick = store::refreshMemoryBookEditorialForReview, enabled = !companionBusy,
                                modifier = Modifier.fillMaxWidth().testTag("memory-book-editorial-refresh-conflict")) {
                                Text(t("Load current version for review", "读取当前版本以供检查"))
                            }
                            state.serverEditorial?.let { server ->
                                if (server.state == EditorialState.SOURCE_CHANGED) Text(
                                    t("Some saved sources changed. Recheck each section and choose current labels before applying your draft.",
                                        "部分已保存来源已变化。请逐项检查并选择当前来源，再应用草稿。"), color = MaterialTheme.colorScheme.error)
                                Button(onClick = { reviewedDraftError = !store.applyReviewedMemoryBookEditorial(introRefs, transitions) }, modifier = Modifier.fillMaxWidth().testTag("memory-book-editorial-apply-reviewed")) {
                                    Text(t("Keep my reviewed draft on this version", "在此版本上保留并检查我的草稿"))
                                }
                                if (reviewedDraftError) Text(t("Review source availability and section limits, then try again.",
                                    "请检查来源是否仍可用及各部分的数量限制，再重试。"), color = MaterialTheme.colorScheme.error)
                            }
                        }
                        if (state.status == MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN) {
                            Button(onClick = store::retryMemoryBookEditorialSave, enabled = !companionBusy, modifier = Modifier.fillMaxWidth().testTag("memory-book-editorial-retry")) {
                                Text(t("Retry exact save", "重试同一保存"))
                            }
                        } else if (state.status == MemoryBookEditorialStoreStatus.READY) {
                            Button(onClick = store::saveMemoryBookEditorial, enabled = state.dirty && !companionBusy,
                                modifier = Modifier.fillMaxWidth().testTag("memory-book-editorial-save")) {
                                Text(if (companionBusy) t("Finish the memoir conversation first", "请先处理回忆册对话") else t("Save arrangement", "保存编排"))
                            }
                        }
                        if (state.dirty && !frozenEditorialSave(state.status)) {
                            TextButton(onClick = { discardConfirmation = true }, modifier = Modifier.testTag("memory-book-editorial-discard")) {
                                Text(t("Discard draft", "放弃草稿"))
                            }
                        }
                    }
                }
            }
        }
    }
    if (discardConfirmation) AlertDialog(onDismissRequest = { discardConfirmation = false },
        title = { Text(t("Discard memoir draft?", "放弃回忆编排草稿？")) },
        text = { Text(t("This removes the unsaved local edits after your confirmation.", "确认后将清除尚未保存的本地修改。")) },
        confirmButton = { TextButton(onClick = { discardConfirmation = false; store.discardMemoryBookEditorialDraft() }, modifier = Modifier.testTag("memory-book-editorial-discard-confirm")) { Text(t("Discard draft", "放弃草稿")) } },
        dismissButton = { TextButton(onClick = { discardConfirmation = false }) { Text(t("Keep editing", "继续编辑")) } })
}

@Composable
private fun EditorialSourceChooser(
    available: List<EditorialSourceIdentity>, selected: List<EditorialSourceIdentity>, titles: Map<String, String>,
    zh: Boolean, key: String, scopeKey: String, canAdd: Boolean, controlsEnabled: Boolean,
    onChange: (List<EditorialSourceIdentity>) -> Unit,
    inspecting: EditorialSourceIdentity?, onInspect: (EditorialSourceIdentity) -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    var filter by remember(scopeKey, key, zh) { mutableStateOf("") }
    var page by remember(scopeKey, key, zh) { mutableStateOf(0) }
    var openGroups by remember(scopeKey, key, zh) { mutableStateOf(emptySet<String>()) }
    val distinctAvailable = available.distinct()
    val allGroups = distinctAvailable.groupBy { "${it.storyId}/${it.chapterId}" }
    val allowedKeys = available.toSet()
    val unavailable = selected.filter { it !in allowedKeys }.distinct()
    val locale = if (zh) java.util.Locale.SIMPLIFIED_CHINESE else java.util.Locale.ENGLISH
    val matches = distinctAvailable.filter { source ->
        if (filter.isBlank()) true else {
            val story = titles[source.storyId].orEmpty()
            val chapter = source.chapterId.removePrefix("chapter-")
            val ordinal = (allGroups["${source.storyId}/${source.chapterId}"].orEmpty().indexOf(source) + 1).toString()
            listOf(story, t("Chapter $chapter", "片段 $chapter"), t("Memory $ordinal", "回忆 $ordinal"), ordinal)
                .any { it.lowercase(locale).contains(filter.trim().lowercase(locale)) }
        }
    }
    val pageCount = maxOf(1, (matches.size + 11) / 12)
    val currentPage = page.coerceIn(0, pageCount - 1)
    val startIndex = currentPage * 12
    val pageSources = matches.drop(startIndex).take(12)
    val pageKeys = pageSources.toSet()
    val hiddenSelected = selected.count { it in allowedKeys && it !in pageKeys }
    val availableStart = if (matches.isEmpty()) 0 else startIndex + 1
    val availableEnd = (startIndex + pageSources.size).coerceAtMost(matches.size)
    OutlinedTextField(
        value = filter,
        onValueChange = { if (controlsEnabled) { filter = it.take(120); page = 0 } },
        enabled = controlsEnabled,
        singleLine = true,
        label = { Text(t("Search story, chapter or memory number", "搜索故事、片段或回忆编号")) },
        supportingText = { Text(t("Search uses source labels only; original text and recordings are not loaded.", "仅按来源标签搜索，不会读取原始文字或录音。")) },
        modifier = Modifier.fillMaxWidth().testTag("editorial-source-search-$key"),
    )
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            if (zh) "显示 $availableStart–$availableEnd / ${matches.size} 项；共 ${distinctAvailable.size} 项；已选 ${selected.size} 项；其他位置已选 $hiddenSelected 项"
            else "Showing $availableStart–$availableEnd of ${matches.size}; ${distinctAvailable.size} available; ${selected.size} selected; $hiddenSelected selected elsewhere",
            modifier = Modifier.weight(1f).testTag("editorial-source-counts-$key"),
        )
        TextButton(onClick = { if (controlsEnabled) { filter = ""; page = 0 } }, enabled = controlsEnabled && filter.isNotEmpty(),
            modifier = Modifier.testTag("editorial-source-clear-$key")) { Text(t("Clear", "清除")) }
    }
    if (matches.isEmpty()) Text(t("No source labels match this search.", "没有符合条件的来源标签。"),
        modifier = Modifier.testTag("editorial-source-no-matches-$key"))
    val visibleGroups = pageSources.groupBy { "${it.storyId}/${it.chapterId}" }
    visibleGroups.forEach { (groupKey, sources) ->
        val first = sources.first()
        val story = titles[first.storyId] ?: t("Earlier story", "此前故事")
        val chapter = first.chapterId.removePrefix("chapter-")
        val expanded = groupKey in openGroups
        TextButton(onClick = { if (controlsEnabled) openGroups = if (expanded) openGroups - groupKey else openGroups + groupKey },
            enabled = controlsEnabled,
            modifier = Modifier.fillMaxWidth().testTag("editorial-source-group-$key-$groupKey")) {
            Text("${if (expanded) "⌄" else "›"} $story · ${t("Chapter", "片段")} $chapter")
        }
        if (expanded) sources.forEach { source ->
            val index = allGroups[groupKey].orEmpty().indexOf(source)
            Column(Modifier.fillMaxWidth().testTag("editorial-source-row-$key-$groupKey-$index")) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = source in selected, onCheckedChange = { checked ->
                        if (controlsEnabled) {
                            val currentIndex = selected.indexOf(source)
                            onChange(when {
                                checked && currentIndex < 0 && canAdd -> selected + source
                                !checked && currentIndex >= 0 -> selected.filterIndexed { position, _ -> position != currentIndex }
                                else -> selected
                            })
                        }
                    }, enabled = controlsEnabled && (source in selected || canAdd), modifier = Modifier.testTag("editorial-source-check-$key-$groupKey-$index"))
                    Text("${t("Memory", "回忆")} ${index + 1}",
                        modifier = Modifier.weight(1f))
                }
                if (source in available) TextButton(onClick = { onInspect(source) },
                    modifier = Modifier.fillMaxWidth().testTag("editorial-source-inspect-$key-$groupKey-$index")) {
                    Text(if (source == inspecting) t("Reviewing original", "正在查看原始回忆") else t("Inspect original", "查看原始回忆"))
                }
            }
        }
    }
    if (unavailable.isNotEmpty()) {
        Text(t("Selected sources no longer available", "已选来源目前不可用"),
            modifier = Modifier.testTag("editorial-source-unavailable-heading-$key"), color = MaterialTheme.colorScheme.error)
        unavailable.forEachIndexed { index, source ->
            Row(Modifier.fillMaxWidth().testTag("editorial-source-unavailable-$key-$index"), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = true, onCheckedChange = { checked ->
                    if (!checked && controlsEnabled) onChange(selected.filterNot { it == source })
                }, enabled = controlsEnabled, modifier = Modifier.testTag("editorial-source-unavailable-check-$key-$index"))
                Text(t("Unavailable selected source · ${titles[source.storyId] ?: "Earlier story"} · chapter ${source.chapterId.removePrefix("chapter-")}",
                    "不可用的已选来源 · ${titles[source.storyId] ?: "此前故事"} · 片段 ${source.chapterId.removePrefix("chapter-")}"),
                    modifier = Modifier.weight(1f))
            }
        }
    }
    if (allGroups.isEmpty() && unavailable.isEmpty()) Text(t("No source labels are available for this section.", "此部分没有可选来源标签。"))
    if (pageCount > 1) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        OutlinedButton(onClick = { if (controlsEnabled) page = (currentPage - 1).coerceAtLeast(0) },
            enabled = controlsEnabled && currentPage > 0, modifier = Modifier.testTag("editorial-source-page-previous-$key")) {
            Text(t("Previous", "上一页"))
        }
        Text(t("Page ${currentPage + 1} of $pageCount", "第 ${currentPage + 1} / $pageCount 页"),
            modifier = Modifier.testTag("editorial-source-page-$key"))
        OutlinedButton(onClick = { if (controlsEnabled) page = (currentPage + 1).coerceAtMost(pageCount - 1) },
            enabled = controlsEnabled && currentPage < pageCount - 1, modifier = Modifier.testTag("editorial-source-page-next-$key")) {
            Text(t("Next", "下一页"))
        }
    }
}

@Composable
private fun EditorialSourceInspector(
    inspection: MemoryBookEditorialSourceInspectionState, store: ConnectedStore, zh: Boolean,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val source = inspection.source ?: return
    var playbackRequested by remember(source, inspection.audio) { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth().testTag("editorial-source-inspector")) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            val detail = inspection.detail
            val audio = inspection.audio
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(t("Original contribution", "原始回忆"), modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                TextButton(onClick = { playbackRequested = false; store.closeMemoryBookEditorialSourceInspection() },
                    modifier = Modifier.testTag("editorial-source-inspector-close")) { Text(t("Close", "关闭")) }
            }
            when {
                inspection.busy -> LinearProgressIndicator(Modifier.fillMaxWidth())
                inspection.unavailable || detail == null -> Text(t(
                    "This original is unavailable or no longer eligible. Refresh the memoir sources before using it.",
                    "此原始回忆已不可用或不再符合条件。请刷新回忆册来源后再使用。"),
                    color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("editorial-source-unavailable"))
                else -> {
                    val receipt = detail.receipt
                    val original = receipt.contribution
                    if (original.kind == "text") {
                        Text(t("Original text", "原始文字"), style = MaterialTheme.typography.labelLarge)
                        Text(original.text.orEmpty(), modifier = Modifier.testTag("editorial-source-original-text"))
                    } else {
                        Text(t("Original audio recording", "原始录音"), style = MaterialTheme.typography.labelLarge)
                        memoryAudioDurationText(original.durationMs, zh)?.let { Text(it) }
                    }
                    val derivation = detail.derivation
                    if (derivation == null) Text(t("No derived transcript or polished text is available.", "暂无转写或润色内容。"),
                        modifier = Modifier.testTag("editorial-source-no-derivation"))
                    else {
                        Text(t("Processing result (derived)", "处理结果（派生内容）"), style = MaterialTheme.typography.labelLarge)
                        derivation.transcript?.let { Text("${t("Transcript", "转写")}: $it", modifier = Modifier.testTag("editorial-source-transcript")) }
                        derivation.polishedText?.let { Text("${t("Polished text", "润色文字")}: $it", modifier = Modifier.testTag("editorial-source-polished")) }
                        if (derivation.transcript == null && derivation.polishedText == null) Text(
                            t("No transcript or polished text is available yet.", "暂时没有转写或润色文字。"),
                            modifier = Modifier.testTag("editorial-source-no-derivation"))
                    }
                    if (original.kind == "audio") when {
                        inspection.audioBusy -> LinearProgressIndicator(Modifier.fillMaxWidth())
                        inspection.audioUnavailable -> Text(t("The original recording could not be loaded.", "无法读取原始录音。"),
                            color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("editorial-source-audio-unavailable"))
                        audio == null -> OutlinedButton(onClick = { store.loadMemoryBookEditorialSourceAudio() },
                            modifier = Modifier.fillMaxWidth().testTag("editorial-source-load-audio")) {
                            Text(t("Load original recording", "读取原始录音"))
                        }
                        playbackRequested -> AnnotationAudioPlayback(audio, zh)
                        else -> OutlinedButton(onClick = { playbackRequested = true },
                            modifier = Modifier.fillMaxWidth().testTag("editorial-source-play-audio")) {
                            Text(t("Play original recording", "播放原始录音"))
                        }
                    }
                }
            }
        }
    }
}

private fun frozenEditorialSave(status: MemoryBookEditorialStoreStatus) =
    status == MemoryBookEditorialStoreStatus.SAVING || status == MemoryBookEditorialStoreStatus.SAVE_UNCERTAIN

@Composable
private fun MemoirNavigation(
    position: String, previous: String, next: String, previousEnabled: Boolean, nextEnabled: Boolean,
    onPrevious: () -> Unit, onNext: () -> Unit, previousTag: String, nextTag: String,
) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(position, style = MaterialTheme.typography.labelLarge)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = onPrevious, enabled = previousEnabled,
                modifier = Modifier.weight(1f).testTag(previousTag)) { Text(previous) }
            Button(onClick = onNext, enabled = nextEnabled,
                modifier = Modifier.weight(1f).testTag(nextTag)) { Text(next) }
        }
    }
}

/** Keep saved-story controls beside saved prose while the AI review panel is open. */
@Composable
private fun MemoryBookOriginalNavigation(
    reading: MemoryBooksReading, zh: Boolean, onChapter: (Int) -> Unit, onStory: (Int) -> Unit,
) {
    val book = reading.selectedBook ?: return
    val story = reading.story
    val chapter = story?.chapters?.getOrNull(reading.selectedChapter)
    val index = reading.storyIndex
    fun t(en: String, cn: String) = if (zh) cn else en
    if (story != null && chapter != null) MemoirNavigation(
        t("Chapter ${reading.selectedChapter + 1} / ${story.chapters.size}", "第 ${reading.selectedChapter + 1} / ${story.chapters.size} 章"),
        t("Previous chapter", "上一章"), t("Next chapter", "下一章"),
        !reading.framesBusy && reading.selectedChapter > 0,
        !reading.framesBusy && reading.selectedChapter < story.chapters.lastIndex,
        { onChapter(reading.selectedChapter - 1) }, { onChapter(reading.selectedChapter + 1) },
        "memory-book-previous-chapter", "memory-book-next-chapter")
    if (index != null) MemoirNavigation(
        t("Story ${index + 1} / ${book.stories.size}", "故事 ${index + 1}/${book.stories.size}"),
        t("Previous story", "上一则故事"), t("Next story", "下一则故事"),
        !reading.readerBusy && index > 0, !reading.readerBusy && index < book.stories.lastIndex,
        { onStory(index - 1) }, { onStory(index + 1) },
        "memory-book-previous", "memory-book-next")
}
