package dev.photohouse.connected

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import dev.photohouse.connected.core.*

@Composable
internal fun SavedMemoryStoriesDialog(
    store: ConnectedStore?,
    reading: SavedMemoryStoriesReading,
    zh: Boolean,
    onClose: () -> Unit,
    onRetry: (Int) -> Unit,
    onSelectTheme: (String?) -> Unit,
    onOpenStory: (SavedMemoryStorySummary) -> Unit,
    onRetryDetail: () -> Unit,
    onCloseDetail: () -> Unit,
    onChapter: (Int) -> Unit,
    onSelectFrame: (String) -> Unit,
    onOpenAsset: (String) -> Unit,
) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val stateFlow = remember(store) { store?.state ?: kotlinx.coroutines.flow.MutableStateFlow(LiveState()) }
    val liveState by stateFlow.collectAsState()
    val latestCompositionState by rememberUpdatedState(liveState)
    val latestCompositionReading by rememberUpdatedState(reading)
    val story = reading.detail
    val readerAudio = remember(liveState.session?.account_id, reading.library, story?.id) { ReaderAudioCoordinator() }
    val themeScrollState = key(reading.library) { rememberScrollState() }
    val chapter = story?.chapters?.getOrNull(reading.selectedChapter)
    var selectedFrame by remember(story?.id, reading.selectedChapter) {
        mutableStateOf(chapter?.assetIds?.firstOrNull())
    }
    var sourcesExpanded by remember(liveState.session?.account_id, reading.library, story?.id, story?.revision, chapter?.id) { mutableStateOf(false) }
    var chaptersExpanded by remember(liveState.session?.account_id, reading.library, story?.id, story?.revision) { mutableStateOf(false) }
    val readerScrollState = key(liveState.session?.account_id, reading.library, story?.id, story?.revision) { rememberScrollState() }
    LaunchedEffect(chaptersExpanded, readerScrollState) {
        if (chaptersExpanded) readerScrollState.animateScrollTo(0)
    }
    LaunchedEffect(chapter?.id, readerScrollState) {
        readerScrollState.scrollTo(0)
    }
    val contributionEditorExpandedByChapter = remember(
        liveState.session?.account_id, reading.library, story?.id, story?.revision,
    ) { mutableStateMapOf<String, Boolean>() }
    var questionsExpanded by remember(story?.id) { mutableStateOf(false) }
    var confirmDiscard by remember(liveState.generation, liveState.session?.account_id, reading.library,
        story?.id, story?.revision, reading.selectedChapter) { mutableStateOf(false) }
    var discardAction by remember(liveState.generation, liveState.session?.account_id, reading.library,
        story?.id, story?.revision, reading.selectedChapter) { mutableStateOf<(() -> Unit)?>(null) }
    var discardDestination by remember(liveState.generation, liveState.session?.account_id, reading.library,
        story?.id, story?.revision, reading.selectedChapter) { mutableStateOf(SavedMemoryExitDestination.CLOSE) }
    fun currentReading(): SavedMemoryStoriesReading? {
        fun matchesReader(current: SavedMemoryStoriesReading): Boolean =
            current.library == reading.library && current.page == reading.page && current.theme == reading.theme &&
                current.selectedSummary?.let { it.id to it.revision } == reading.selectedSummary?.let { it.id to it.revision } &&
                current.detail?.let { it.id to it.revision } == reading.detail?.let { it.id to it.revision } &&
                current.selectedChapter == reading.selectedChapter &&
                current.community?.readerScopeId == reading.community?.readerScopeId
        val live = store?.state?.value
        if (live == null) {
            val current = latestCompositionReading
            val latest = latestCompositionState
            if (latest.covered || latest.generation != liveState.generation ||
                latest.session?.account_id != liveState.session?.account_id || latest.library != liveState.library ||
                !matchesReader(current)) return null
            return current
        }
        if (live.covered || live.generation != liveState.generation || live.session?.account_id != liveState.session?.account_id ||
            live.library != reading.library) return null
        val current = live.savedMemoryStories ?: return null
        if (!matchesReader(current)) return null
        return current
    }
    fun hasUnfinishedPrivateWork(current: SavedMemoryStoriesReading): Boolean {
        val community = current.community ?: return false
        val dictation = community.dictation?.state?.value
        return community.chatDraft.isNotBlank() || community.threadDrafts.values.any(String::isNotBlank) ||
            community.contributionDraft.isNotBlank() || community.contributionConsent || community.audioConsent ||
            community.chatTurnContributionSeeded || community.pendingText != null || community.pendingAudio != null ||
            community.pendingConversation != null || community.pendingTurn != null || community.pendingNarrative != null ||
            community.busy || community.contributionAudioBusy ||
            community.contributionAudioActivityId != null || community.job?.state in setOf("queued", "running") ||
            community.narrativeJob?.state in setOf("queued", "running") ||
            community.turns?.items?.any { it.state in setOf("queued", "running") } == true ||
            dictation?.let { it.loading || it.recording || it.transcribing || it.transcript != null } == true
    }
    fun completeExit(destination: SavedMemoryExitDestination, mediaId: String?) {
        val current = currentReading() ?: return
        when (destination) {
            SavedMemoryExitDestination.CLOSE -> onClose()
            SavedMemoryExitDestination.BACK_TO_LIST -> onCloseDetail()
            SavedMemoryExitDestination.OPEN_PHOTO,
            SavedMemoryExitDestination.OPEN_VIDEO,
            SavedMemoryExitDestination.OPEN_MOMENT -> {
                val target = mediaId ?: return
                if (selectedFrame != target || current.detail?.items?.any { it.asset.id == target } != true ||
                    current.detail?.chapters?.getOrNull(current.selectedChapter)?.assetIds?.contains(target) != true) return
                onOpenAsset(target)
            }
        }
    }
    fun requestExit(destination: SavedMemoryExitDestination, mediaId: String? = null) {
        val current = currentReading() ?: return
        if (destination in setOf(SavedMemoryExitDestination.OPEN_PHOTO, SavedMemoryExitDestination.OPEN_VIDEO,
                SavedMemoryExitDestination.OPEN_MOMENT)) {
            val target = mediaId ?: return
            if (current.detail?.items?.any { it.asset.id == target } != true ||
                current.detail?.chapters?.getOrNull(current.selectedChapter)?.assetIds?.contains(target) != true) return
        }
        val action = { completeExit(destination, mediaId) }
        if (hasUnfinishedPrivateWork(current)) {
            discardDestination = destination
            discardAction = action
            confirmDiscard = true
        } else action()
    }
    val selectedMedia = story?.items?.firstOrNull { it.asset.id == selectedFrame }
    val heroBytes = reading.hero.takeIf { reading.heroAssetId == selectedFrame }
        ?: selectedFrame?.let(reading.frames::get)
    val heroBitmap = remember(heroBytes) { heroBytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() } }

    Dialog(onDismissRequest = { requestExit(SavedMemoryExitDestination.CLOSE) }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        CompositionLocalProvider(LocalReaderAudioCoordinator provides readerAudio) { PhotoHouseTheme {
            Surface(Modifier.fillMaxSize().safeDrawingPadding().testTag("saved-memory-stories"), color = MaterialTheme.colorScheme.background) {
                Column(Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 12.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(if (story == null) t("Saved family stories", "已保存的家人故事") else t("Family memory", "家人回忆"),
                            modifier = Modifier.weight(1f).padding(end = 8.dp),
                            style = MaterialTheme.typography.headlineSmall, fontFamily = FontFamily.Serif, maxLines = 2)
                        TextButton(onClick = { requestExit(SavedMemoryExitDestination.CLOSE) }, modifier = Modifier.testTag("saved-memory-close")) { Text(t("Close", "关闭")) }
                    }
                    when {
                        reading.busy -> {
                            LinearProgressIndicator(Modifier.fillMaxWidth())
                            Text(t("Loading saved stories…", "正在加载已保存的故事…"))
                        }
                        reading.unavailable -> {
                            Text(t("Saved stories are unavailable right now. Retry to check again.", "已保存的故事暂时不可用，请重试。"), color = MaterialTheme.colorScheme.error)
                            OutlinedButton(onClick = { onRetry(reading.page) }, modifier = Modifier.testTag("saved-memory-retry")) { Text(t("Retry", "重试")) }
                            if (reading.theme != null) TextButton(onClick = { onSelectTheme(null) }, modifier = Modifier.testTag("saved-memory-theme-error-all")) {
                                Text(t("Return to all themes", "返回全部主题"))
                            }
                        }
                        reading.detailBusy -> {
                            LinearProgressIndicator(Modifier.fillMaxWidth())
                            Text(t("Opening saved memory…", "正在打开已保存的回忆…"))
                        }
                        reading.detailUnavailable -> {
                            TextButton(onClick = onCloseDetail, modifier = Modifier.testTag("saved-memory-back-list")) { Text(t("‹ All saved stories", "‹ 所有已保存故事")) }
                            val gone = reading.problem?.message == Message.MEDIA_UNAVAILABLE
                            Text(if (gone) t("This saved story or one of its photos is no longer available.", "此故事或其中一张照片已不可用。")
                                else t("This saved story is temporarily unavailable. Retry to check again.", "已保存的故事暂时无法读取，请重试。"), color = MaterialTheme.colorScheme.error)
                            OutlinedButton(onClick = { if (gone) { onCloseDetail(); onRetry(reading.page) } else onRetryDetail() },
                                modifier = Modifier.testTag("saved-memory-detail-retry")) {
                                Text(if (gone) t("Refresh saved stories", "刷新已保存故事") else t("Retry", "重试"))
                            }
                        }
                        story != null && chapter != null -> {
                            TextButton(onClick = { requestExit(SavedMemoryExitDestination.BACK_TO_LIST) }, modifier = Modifier.testTag("saved-memory-back-list")) {
                                Text(t("‹ All saved stories", "‹ 所有已保存故事"))
                            }
                            Text(t("Saved draft · Review needed", "已保存草稿 · 仍需检查"),
                                style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.testTag("saved-memory-draft-label"))
                            Text(story.title, style = MaterialTheme.typography.headlineMedium, fontFamily = FontFamily.Serif,
                                maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.testTag("saved-memory-title"))
                            ChapterReadAloud("${story.title}. ${chapter.narration}", story.language,
                                listOf("story", liveState.session?.account_id, reading.library, story.id, story.revision, chapter.id), zh,
                                enabled = chapter.narration.isNotBlank(),)
                            TextButton(onClick = { chaptersExpanded = !chaptersExpanded },
                                modifier = Modifier.testTag("saved-memory-chapter-directory-toggle")) {
                                Text(if (chaptersExpanded) t("Hide chapters", "收起目录") else t("Contents · ${story.chapters.size} chapters", "目录 · ${story.chapters.size} 章"))
                            }
                            HorizontalDivider(
                                Modifier.fillMaxWidth().padding(vertical = 6.dp).testTag("saved-memory-reader-scroll-divider"),
                                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.24f),
                            )
                            Box(Modifier.weight(1f).fillMaxWidth().clipToBounds().testTag("saved-memory-reader-scroll")) {
                                Column(Modifier.fillMaxSize().verticalScroll(readerScrollState), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                                    if (chaptersExpanded) {
                                        Column(Modifier.fillMaxWidth().testTag("saved-memory-chapter-directory"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                            story.chapters.forEachIndexed { index, item ->
                                                TextButton(onClick = {
                                                    if (currentReading() == null) return@TextButton
                                                    onChapter(index)
                                                    chaptersExpanded = false
                                                }, enabled = !reading.framesBusy,
                                                    colors = ButtonDefaults.textButtonColors(
                                                        containerColor = if (index == reading.selectedChapter) MaterialTheme.colorScheme.secondaryContainer else androidx.compose.ui.graphics.Color.Transparent,
                                                        contentColor = if (index == reading.selectedChapter) MaterialTheme.colorScheme.onSecondaryContainer else MaterialTheme.colorScheme.primary,
                                                    ),
                                                    modifier = Modifier.fillMaxWidth().semantics { selected = index == reading.selectedChapter }
                                                        .testTag("saved-memory-chapter-directory-$index")) {
                                                    Text("${index + 1}. ${item.title}", modifier = Modifier.fillMaxWidth(), style = MaterialTheme.typography.bodyLarge)
                                                }
                                            }
                                        }
                                    }
                                    Box(Modifier.fillMaxWidth().aspectRatio(1.6f).testTag("saved-memory-hero"), contentAlignment = Alignment.Center) {
                                        if (heroBitmap != null) Image(heroBitmap, null, Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
                                        else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                            if (reading.heroBusy) CircularProgressIndicator()
                                            else Text(if (selectedMedia?.asset?.kind == "video") t("Video frame unavailable", "视频画面暂不可用") else t("Photo unavailable", "照片暂不可用"),
                                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        }
                                    }
                                    Text(chapter.title, style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif,
                                        modifier = Modifier.testTag("saved-memory-chapter-title"))
                                    Text(chapter.narration, style = MaterialTheme.typography.bodyLarge.copy(lineHeight = 29.sp),
                                        modifier = Modifier.fillMaxWidth().testTag("saved-memory-narration"))
                                    ChapterSourceReferences(
                                        chapterSourceReferences(chapter, story), zh, sourcesExpanded,
                                        { sourcesExpanded = it }, "saved-memory-sources",
                                    )
                                    SavedMemoryChapterContributionReferences(store, reading, chapter, zh)
                                    if (story.canEdit) {
                                        val needsAttention = reading.contributionReferenceSaveBusy ||
                                            reading.contributionReferenceSaveError || reading.contributionReferenceSaveConflict ||
                                            reading.pendingContributionReferenceMutation != null ||
                                            savedMemoryContributionReferenceDraftChanged(reading, story)
                                        val editorExpanded = needsAttention || contributionEditorExpandedByChapter[chapter.id] == true
                                        TextButton(
                                            onClick = { contributionEditorExpandedByChapter[chapter.id] = !editorExpanded },
                                            enabled = !needsAttention,
                                            modifier = Modifier.fillMaxWidth().testTag("saved-memory-contribution-link-toggle-${chapter.id}"),
                                        ) {
                                            Text(when {
                                                reading.contributionReferenceSaveBusy -> t("Saving chapter memories…", "正在保存本章回忆…")
                                                reading.contributionReferenceSaveError || reading.contributionReferenceSaveConflict ||
                                                    reading.pendingContributionReferenceMutation != null -> t("Finish chapter memory save", "完成本章回忆保存")
                                                editorExpanded -> t("Hide chapter memory manager", "收起本章回忆管理")
                                                else -> t("Manage chapter memories", "管理本章回忆")
                                            })
                                        }
                                        if (editorExpanded) SavedMemoryChapterContributionLinkEditor(store, reading, chapter, zh)
                                    }
                                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(t("Moments", "故事片段"), style = MaterialTheme.typography.labelLarge)
                                        if (reading.framesBusy) LinearProgressIndicator(Modifier.width(72.dp))
                                    }
                                    LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.testTag("saved-memory-frames")) {
                                        items(chapter.assetIds, key = { it }) { assetId ->
                                            val media = story.items.firstOrNull { it.asset.id == assetId }
                                            val bytes = reading.frames[assetId]
                                            val bitmap = remember(bytes) { bytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() } }
                                            Card(Modifier.width(112.dp).clickable { selectedFrame = assetId; onSelectFrame(assetId) }
                                                .testTag("saved-memory-frame-$assetId"), colors = CardDefaults.cardColors(
                                                    containerColor = if (selectedFrame == assetId) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surfaceContainerLow)) {
                                                Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                                                    if (bitmap != null) Image(bitmap, null, Modifier.fillMaxWidth().height(68.dp), contentScale = ContentScale.Crop)
                                                    else Box(Modifier.fillMaxWidth().height(68.dp), contentAlignment = Alignment.Center) {
                                                        Text(if (media?.asset?.kind == "video") t("Video", "视频") else t("Photo", "照片"), style = MaterialTheme.typography.labelSmall)
                                                    }
                                                    Text(memoryStoryDate(media?.asset, t("Date unknown", "日期未知"), zh),
                                                        style = MaterialTheme.typography.labelSmall, maxLines = 2, overflow = TextOverflow.Ellipsis,
                                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
                                                }
                                            }
                                        }
                                    }
                                    OutlinedButton(onClick = {
                                        selectedFrame?.let { mediaId ->
                                            val destination = when (selectedMedia?.asset?.kind) {
                                                "image" -> SavedMemoryExitDestination.OPEN_PHOTO
                                                "video" -> SavedMemoryExitDestination.OPEN_VIDEO
                                                else -> SavedMemoryExitDestination.OPEN_MOMENT
                                            }
                                            requestExit(destination, mediaId)
                                        }
                                    }, enabled = selectedMedia != null,
                                        modifier = Modifier.fillMaxWidth().testTag("saved-memory-open-${selectedFrame ?: "none"}")) {
                                        Text(when (selectedMedia?.asset?.kind) {
                                            "video" -> t("Open video", "打开视频")
                                            "image" -> t("Open photo", "打开照片")
                                            else -> t("Open moment", "打开片段")
                                        })
                                    }
                                    if (story.questions.isNotEmpty()) {
                                        TextButton(onClick = { questionsExpanded = !questionsExpanded },
                                            modifier = Modifier.testTag("saved-memory-questions-toggle")) {
                                            Text(if (questionsExpanded) t("Hide family questions", "收起留给家人的问题") else t("Family questions · ${story.questions.size}", "留给家人的问题 · ${story.questions.size}"))
                                        }
                                        if (questionsExpanded) Column(verticalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.testTag("saved-memory-questions")) {
                                            story.questions.forEach { Text("•  $it", style = MaterialTheme.typography.bodyMedium) }
                                        }
                                    }
                                    if (store?.memoryCommunityAvailable == true) MemoryCommunityPanel(store, reading, zh)
                                }
                            }
                            Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                OutlinedButton(onClick = { onChapter(reading.selectedChapter - 1) }, enabled = reading.selectedChapter > 0,
                                    modifier = Modifier.testTag("saved-memory-previous")) { Text(t("Previous", "上一章")) }
                                Text(t("Chapter ${reading.selectedChapter + 1} of ${story.chapters.size}", "第 ${reading.selectedChapter + 1}/${story.chapters.size} 章"))
                                Button(onClick = { onChapter(reading.selectedChapter + 1) }, enabled = reading.selectedChapter < story.chapters.lastIndex,
                                    modifier = Modifier.testTag("saved-memory-next")) { Text(t("Next", "下一章")) }
                            }
                        }
                        else -> {
                            Text(t("Open a story and revisit the moments your family shared together.", "打开故事，慢慢回看家人共同留下的时光。"),
                                style = MaterialTheme.typography.bodySmall)
                            Row(Modifier.fillMaxWidth().horizontalScroll(themeScrollState).testTag("saved-memory-theme-row"), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                savedMemoryThemeChoices.forEach { choice ->
                                    FilterChip(selected = reading.theme == choice.wire,
                                        onClick = { onSelectTheme(choice.wire) },
                                        label = { Text(t(choice.en, choice.zh)) },
                                        modifier = Modifier.testTag("saved-memory-theme-${choice.wire ?: "all"}"))
                                }
                            }
                            val result = reading.result
                            if (result?.items.isNullOrEmpty()) {
                                Text(if (reading.theme == null) t("No saved stories on this page.", "此页没有已保存的故事。")
                                    else t("No saved stories for this theme.", "此主题下暂无已保存故事。"), modifier = Modifier.testTag("saved-memory-empty"))
                                if (reading.theme != null) TextButton(onClick = { onSelectTheme(null) },
                                    modifier = Modifier.testTag("saved-memory-theme-empty-all")) { Text(t("Show all themes", "查看全部主题")) }
                            }
                            BoxWithConstraints(Modifier.weight(1f).fillMaxWidth()) {
                                val stackedCards = LocalDensity.current.fontScale >= 1.4f || maxWidth < 340.dp
                                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                                    verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                    result?.items?.forEach { item ->
                                        val title = item.title.ifBlank { t("Untitled memory", "未命名回忆") }
                                        val meta = t("${item.itemCount} moments · ${item.chapterCount} chapters",
                                            "${item.itemCount} 个片段 · ${item.chapterCount} 章")
                                        val bytes = reading.covers[item.id]
                                        val bitmap = remember(bytes) { bytes?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() } }
                                        Card(onClick = { onOpenStory(item) }, modifier = Modifier.fillMaxWidth()
                                            .semantics(mergeDescendants = true) {
                                                role = Role.Button
                                                contentDescription = t("$title. Saved draft, review needed. $meta", "$title。已保存草稿，仍需检查。$meta")
                                                onClick(label = t("Open story", "阅读故事")) { onOpenStory(item); true }
                                            }
                                            .testTag("saved-memory-story-${item.id}"),
                                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
                                            if (stackedCards) {
                                                Column {
                                                    if (bitmap != null) Image(bitmap, null,
                                                        Modifier.fillMaxWidth().aspectRatio(16f / 9f).testTag("saved-memory-cover-${item.id}"),
                                                        contentScale = ContentScale.Crop)
                                                    else Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f), contentAlignment = Alignment.Center) {
                                                        Text(t("Memory", "回忆"), color = MaterialTheme.colorScheme.onSurfaceVariant)
                                                    }
                                                    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp),
                                                        verticalArrangement = Arrangement.spacedBy(7.dp)) {
                                                        Text(t("Saved draft · Review needed", "已保存草稿 · 仍需检查"),
                                                            style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                                                        Text(title, style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif,
                                                            modifier = Modifier.testTag("saved-memory-story-title-${item.id}"))
                                                        Text(meta, style = MaterialTheme.typography.bodySmall,
                                                            modifier = Modifier.testTag("saved-memory-story-meta-${item.id}"))
                                                        Text(t("Open story  ›", "阅读故事  ›"), style = MaterialTheme.typography.labelLarge,
                                                            color = MaterialTheme.colorScheme.primary,
                                                            modifier = Modifier.testTag("saved-memory-story-open-${item.id}"))
                                                    }
                                                }
                                            } else {
                                                Row(Modifier.fillMaxWidth().heightIn(min = 132.dp), verticalAlignment = Alignment.CenterVertically) {
                                                    if (bitmap != null) Image(bitmap, null, Modifier.width(132.dp).height(132.dp)
                                                        .testTag("saved-memory-cover-${item.id}"), contentScale = ContentScale.Crop)
                                                    else Box(Modifier.width(132.dp).height(132.dp), contentAlignment = Alignment.Center) {
                                                        Text(t("Memory", "回忆"), color = MaterialTheme.colorScheme.onSurfaceVariant)
                                                    }
                                                    Column(Modifier.weight(1f).padding(horizontal = 14.dp, vertical = 12.dp),
                                                        verticalArrangement = Arrangement.spacedBy(5.dp)) {
                                                        Text(t("Saved draft · Review needed", "已保存草稿 · 仍需检查"),
                                                            style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                                                        Text(title, style = MaterialTheme.typography.titleLarge, fontFamily = FontFamily.Serif,
                                                            modifier = Modifier.testTag("saved-memory-story-title-${item.id}"))
                                                        Text(meta, style = MaterialTheme.typography.bodySmall,
                                                            modifier = Modifier.testTag("saved-memory-story-meta-${item.id}"))
                                                        Text(t("Open story  ›", "阅读故事  ›"), style = MaterialTheme.typography.labelLarge,
                                                            color = MaterialTheme.colorScheme.primary,
                                                            modifier = Modifier.testTag("saved-memory-story-open-${item.id}"))
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                OutlinedButton(onClick = { onRetry(reading.page - 1) }, enabled = result != null && reading.page > 1,
                                    modifier = Modifier.testTag("saved-memory-previous-page")) { Text(t("Previous", "上一页")) }
                                Text(t("Page ${reading.page}", "第 ${reading.page} 页"), Modifier.align(Alignment.CenterVertically))
                                Button(onClick = { onRetry(reading.page + 1) }, enabled = result?.hasMore == true,
                                    modifier = Modifier.testTag("saved-memory-next-page")) { Text(t("Next", "下一页")) }
                            }
                            TextButton(onClick = { onRetry(1) }, modifier = Modifier.align(Alignment.End).testTag("saved-memory-refresh")) { Text(t("Refresh", "刷新")) }
                        }
                    }
                }
            }
        } }
    }
    if (confirmDiscard) AlertDialog(
        onDismissRequest = { confirmDiscard = false; discardAction = null },
        title = { Text(when (discardDestination) {
            SavedMemoryExitDestination.CLOSE -> t("Leave this story?", "离开这个故事？")
            SavedMemoryExitDestination.BACK_TO_LIST -> t("Return to saved stories?", "返回已保存的故事？")
            SavedMemoryExitDestination.OPEN_PHOTO -> t("Open this photo?", "打开这张照片？")
            SavedMemoryExitDestination.OPEN_VIDEO -> t("Open this video?", "打开这段视频？")
            SavedMemoryExitDestination.OPEN_MOMENT -> t("Open this moment?", "打开这个片段？")
        }) },
        text = { Text(t("Drafts and voice input on this screen will be cleared. A request already sent may still be processed.",
            "此页的草稿和语音输入会被清除。已发送的请求仍可能继续处理。")) },
        confirmButton = { TextButton(onClick = {
            val action = discardAction
            confirmDiscard = false
            discardAction = null
            action?.invoke()
        }, modifier = Modifier.testTag("memory-community-discard-confirm")) { Text(when (discardDestination) {
            SavedMemoryExitDestination.CLOSE -> t("Discard and close", "放弃并关闭")
            SavedMemoryExitDestination.BACK_TO_LIST -> t("Discard and return", "放弃并返回")
            SavedMemoryExitDestination.OPEN_PHOTO -> t("Discard and open photo", "放弃并打开照片")
            SavedMemoryExitDestination.OPEN_VIDEO -> t("Discard and open video", "放弃并打开视频")
            SavedMemoryExitDestination.OPEN_MOMENT -> t("Discard and open moment", "放弃并打开片段")
        }) } },
        dismissButton = { TextButton(onClick = { confirmDiscard = false; discardAction = null }, modifier = Modifier.testTag("memory-community-discard-cancel")) {
            Text(t("Keep reading", "继续阅读"))
        } },
    )
}

private enum class SavedMemoryExitDestination { CLOSE, BACK_TO_LIST, OPEN_PHOTO, OPEN_VIDEO, OPEN_MOMENT }

private fun savedMemoryContributionReferenceDraftChanged(
    reading: SavedMemoryStoriesReading,
    story: SavedMemoryStory,
): Boolean {
    val references = reading.contributionReferences?.takeIf {
        it.id == story.id && it.libraryId == reading.library && it.revision == story.revision
    } ?: return false
    val draft = reading.contributionReferenceDraft ?: return false
    return story.chapters.any { chapter ->
        draft[chapter.id].orEmpty() != references.chapters.firstOrNull { it.chapterId == chapter.id }
            ?.contributionIds.orEmpty()
    }
}

@Composable
private fun SavedMemoryChapterContributionLinkEditor(
    store: ConnectedStore?, reading: SavedMemoryStoriesReading, chapter: SavedMemoryStoryChapter, zh: Boolean,
) {
    val story = reading.detail ?: return
    val refs = reading.contributionReferences?.takeIf { it.id == story.id && it.libraryId == reading.library && it.revision == story.revision }
    val draft = reading.contributionReferenceDraft?.get(chapter.id).orEmpty()
    val original = refs?.chapters?.firstOrNull { it.chapterId == chapter.id }?.contributionIds.orEmpty()
    val candidates = reading.community?.contributions?.items.orEmpty().filter { item ->
        item.storyId == story.id && item.state == "accepted" && item.processingConsent &&
            item.baseStoryRevision in 1..story.revision && (item.chapterId == null || item.chapterId == chapter.id)
    }
    fun t(en: String, cn: String) = if (zh) cn else en
    Column(Modifier.fillMaxWidth().testTag("saved-memory-contribution-link-editor-${chapter.id}"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(t("Choose family memories for this chapter", "选择要关联到本章的家人回忆"), style = MaterialTheme.typography.labelLarge)
        when {
            refs == null || reading.contributionReferencesBusy -> Text(t("Link list must finish loading before editing.", "关联来源加载完成后才能编辑。"))
            reading.contributionReferencesUnavailable -> Text(t("Link list is unavailable. Retry before editing.", "关联来源暂不可用，请重试后再编辑。"))
            else -> {
                val ids = (candidates.map { it.id } + draft).distinct()
                if (ids.isEmpty()) Text(t("No eligible family memories are available on this page.", "当前页没有可关联的家人回忆。"))
                ids.forEachIndexed { index, id ->
                    val candidate = candidates.firstOrNull { it.id == id }
                    val selected = id in draft
                    val eligible = candidate != null || id in original
                    val enabled = store != null && !reading.contributionReferenceSaveBusy &&
                        !reading.contributionReferenceSaveError && !reading.contributionReferenceSaveConflict && eligible
                    val ordinal = t("Family memory ${index + 1}", "家人回忆 ${index + 1}")
                    val kindLabel = when (candidate?.kind) {
                        "text" -> t("Written memory", "文字回忆")
                        "audio" -> t("Audio recording", "录音")
                        else -> t("Previously linked", "已有关联")
                    }
                    val byline = candidate?.byline?.takeIf(String::isNotBlank)
                        ?: t("Family member", "家人")
                    val excerpt = candidate?.takeIf { it.kind == "text" }?.text
                        ?.trim()?.replace(Regex("\\s+"), " ")?.take(120)?.takeIf(String::isNotBlank)
                    val duration = candidate?.durationMs?.takeIf { candidate.kind == "audio" && it > 0 }
                        ?.let { millis ->
                            val seconds = (millis + 999) / 1000
                            "${seconds / 60}:${(seconds % 60).toString().padStart(2, '0')}"
                        }
                    Card(
                        modifier = Modifier.fillMaxWidth()
                            .selectable(selected = selected, enabled = enabled, role = Role.Checkbox) {
                                store?.toggleSavedMemoryChapterContribution(chapter.id, id)
                            }
                            .testTag("saved-memory-contribution-link-${chapter.id}-$index"),
                        colors = CardDefaults.cardColors(containerColor = if (selected)
                            MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surfaceContainerLow),
                    ) {
                        Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 11.dp),
                            verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("$ordinal · $kindLabel", style = MaterialTheme.typography.titleSmall,
                                    modifier = Modifier.weight(1f))
                                Row(verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Text(if (selected) t("Selected", "已选择") else t("Not selected", "未选择"),
                                        style = MaterialTheme.typography.labelMedium)
                                    Box(
                                        modifier = Modifier.size(22.dp)
                                            .border(1.5.dp, if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
                                                RoundedCornerShape(4.dp))
                                            .background(if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface,
                                                RoundedCornerShape(4.dp)),
                                        contentAlignment = Alignment.Center,
                                    ) {
                                        if (selected) Text("✓", color = MaterialTheme.colorScheme.onPrimary,
                                            style = MaterialTheme.typography.labelMedium)
                                    }
                                }
                            }
                            Text(t("By $byline", "署名：$byline"), style = MaterialTheme.typography.bodyMedium)
                            if (excerpt != null) Text(excerpt, style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            if (duration != null) Text(t("Recording · $duration", "录音时长 · $duration"),
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                val changed = reading.contributionReferenceDraft?.let { map ->
                    story.chapters.any { ch -> map[ch.id].orEmpty() != refs.chapters.firstOrNull { it.chapterId == ch.id }?.contributionIds.orEmpty() }
                } == true
                if (reading.contributionReferenceSaveConflict) {
                    Text(t("Story revision changed. Reload it before editing these links.", "故事版本已变化，请重新加载后再编辑关联。"), color = MaterialTheme.colorScheme.error)
                    TextButton(onClick = { store?.retrySavedMemoryStory() }, modifier = Modifier.testTag("saved-memory-contribution-link-reload")) { Text(t("Reload story", "重新加载故事")) }
                } else if (reading.contributionReferenceSaveError) {
                    Text(t("Save did not finish. Retry the same link changes.", "保存未完成，请重试相同的关联更改。"), color = MaterialTheme.colorScheme.error)
                    OutlinedButton(onClick = { store?.retrySavedMemoryStoryContributionReferencesSave() }, enabled = !reading.contributionReferenceSaveBusy,
                        modifier = Modifier.testTag("saved-memory-contribution-link-retry")) { Text(t("Retry same save", "重试相同保存")) }
                } else {
                    Button(onClick = { store?.saveSavedMemoryStoryContributionReferences() }, enabled = changed && !reading.contributionReferenceSaveBusy,
                        modifier = Modifier.testTag("saved-memory-contribution-link-save")) {
                        Text(if (reading.contributionReferenceSaveBusy) t("Saving…", "正在保存…") else t("Save links", "保存关联"))
                    }
                }
            }
        }
    }
}

@Composable
private fun SavedMemoryChapterContributionReferences(
    store: ConnectedStore?, reading: SavedMemoryStoriesReading, chapter: SavedMemoryStoryChapter, zh: Boolean,
) {
    val story = reading.detail ?: return
    val references = reading.contributionReferences?.takeIf {
        it.id == story.id && it.libraryId == reading.library && it.revision == story.revision
    }
    val chapterReferences = references?.chapters?.firstOrNull { it.chapterId == chapter.id }
    fun t(en: String, cn: String) = if (zh) cn else en
    Column(Modifier.fillMaxWidth().testTag("saved-memory-contribution-sources"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(t("Family memories linked to this chapter", "本章关联的家人回忆"),
            style = MaterialTheme.typography.titleSmall)
        when {
            reading.contributionReferencesBusy -> {
                LinearProgressIndicator(Modifier.fillMaxWidth())
                Text(t("Checking linked sources…", "正在核对关联来源…"))
            }
            reading.contributionReferencesUnavailable || references == null -> {
                Text(t("Linked family sources are temporarily unavailable.", "家人回忆来源暂时无法核对。"),
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                store?.let { currentStore ->
                    TextButton(onClick = currentStore::retrySavedMemoryStoryContributionReferences,
                        modifier = Modifier.testTag("saved-memory-contribution-sources-retry")) {
                        Text(t("Retry", "重试"))
                    }
                }
            }
            chapterReferences == null || chapterReferences.contributionIds.isEmpty() ->
                Text(t("No linked family memories for this chapter.", "本章没有关联的家人回忆。"),
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            else -> {
                chapterReferences.contributionIds.forEachIndexed { index, contributionId ->
                    val selected = reading.contributionDetailChapterId == chapter.id &&
                        reading.contributionDetailId == contributionId
                    OutlinedButton(
                        onClick = {
                            if (selected) store?.closeSavedMemoryStoryContributionDetail()
                            else store?.loadSavedMemoryStoryContributionDetail(chapter.id, contributionId)
                        },
                        enabled = store != null && (!reading.contributionDetailBusy || selected),
                        modifier = Modifier.fillMaxWidth().testTag("saved-memory-contribution-source-$index"),
                    ) {
                        Text(if (selected) t("Hide source", "收起来源") else t("View family memory ${index + 1}", "查看家人回忆 ${index + 1}"))
                    }
                }
                if (reading.contributionDetailChapterId == chapter.id &&
                    reading.contributionDetailId?.let { it in chapterReferences.contributionIds } == true) {
                    val contributionDetail = reading.contributionDetail
                    when {
                        reading.contributionDetailBusy -> LinearProgressIndicator(Modifier.fillMaxWidth())
                        reading.contributionDetailUnavailable -> {
                            Text(t("This source is temporarily unavailable or no longer eligible.", "该来源暂时不可用或已不符合查看条件。"),
                                color = MaterialTheme.colorScheme.error)
                            TextButton(onClick = { store?.retrySavedMemoryStoryContributionDetail() },
                                modifier = Modifier.testTag("saved-memory-contribution-source-retry")) {
                                Text(t("Retry", "重试"))
                            }
                        }
                        contributionDetail != null -> {
                            val contribution = contributionDetail.receipt.contribution
                            val byline = contribution.byline.takeIf(String::isNotBlank)
                            if (contribution.kind == "text") {
                                Text(t("Family-provided memory", "家人提供的回忆"),
                                    style = MaterialTheme.typography.labelLarge)
                                byline?.let { Text(t("Byline: $it", "署名：$it"),
                                    style = MaterialTheme.typography.bodyMedium,
                                    modifier = Modifier.testTag("saved-memory-contribution-source-byline")) }
                                contribution.text?.takeIf(String::isNotBlank)?.let { sourceText ->
                                    Text(sourceText, style = MaterialTheme.typography.bodyLarge,
                                        modifier = Modifier.fillMaxWidth().testTag("saved-memory-contribution-source-text"))
                                }
                            } else {
                                val transcript = contributionDetail.derivation
                                    ?.takeIf { it.state == "ready" }?.transcript?.takeIf(String::isNotBlank)
                                Text(t("Family recording · AI transcript", "家人录音 · AI 转写"),
                                    style = MaterialTheme.typography.labelLarge)
                                byline?.let { Text(t("Byline: $it", "署名：$it"),
                                    style = MaterialTheme.typography.bodyMedium,
                                    modifier = Modifier.testTag("saved-memory-contribution-source-byline")) }
                                if (transcript == null) {
                                    Text(t("A ready transcript is not available.", "暂无可查看的已完成转写。"),
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                } else Text(transcript, style = MaterialTheme.typography.bodyLarge,
                                    modifier = Modifier.fillMaxWidth().testTag("saved-memory-contribution-source-transcript"))
                            }
                        }
                    }
                }
            }
        }
    }
}

private data class SavedMemoryThemeChoice(val wire: String?, val en: String, val zh: String)
private val savedMemoryThemeChoices = listOf(
    SavedMemoryThemeChoice(null, "All", "全部"),
    SavedMemoryThemeChoice("everyday", "Everyday", "日常"),
    SavedMemoryThemeChoice("trip", "Trips", "旅行"),
    SavedMemoryThemeChoice("growing_up", "Growing up", "成长"),
    SavedMemoryThemeChoice("birthday", "Birthdays", "生日"),
    SavedMemoryThemeChoice("grandparents", "Grandparents", "祖辈"),
    SavedMemoryThemeChoice("year_in_review", "Year in review", "年度回顾"),
)

private fun memoryStoryDate(asset: dev.photohouse.protocol.Asset?, unknown: String, zh: Boolean): String {
    if (asset == null) return unknown
    asset.date_hint?.let { hint ->
        val source = when (hint.source) {
            "filename" -> if (zh) "文件名日期" else "Filename date"
            "received" -> if (zh) "收到于" else "Received"
            else -> null
        }
        if (source != null) return "$source · ${hint.value}"
    }
    return asset.taken_at?.takeIf { it.isNotBlank() } ?: unknown
}
