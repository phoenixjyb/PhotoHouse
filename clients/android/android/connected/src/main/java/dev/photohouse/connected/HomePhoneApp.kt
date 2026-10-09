package dev.photohouse.connected

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import dev.photohouse.home.*
import dev.photohouse.connected.core.PhotoNavigation
import dev.photohouse.connected.core.VideoPlaybackFailure
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@OptIn(ExperimentalLayoutApi::class)
@Composable internal fun HomePhoneApp(browseStore: HomeStore?, discovery: DiscoveryController? = null, initialZh: Boolean = true, exit: () -> Unit) {
    var zh by remember { mutableStateOf(initialZh) }
    fun t(en: String, cn: String) = if (zh) cn else en
    val discoveryState = discovery?.state?.collectAsState()?.value ?: DiscoveryState()
    val store = discoveryState.results ?: browseStore
    var exploring by remember(discovery) { mutableStateOf(false) }
    val state = store?.state?.collectAsState()?.value ?: HomeState()
    val feed = state.feed
    val asset = state.asset
    var playbackFailure by remember(store, asset?.id, feed?.revision, state.covered) { mutableStateOf<VideoPlaybackFailure?>(null) }
    var selection by remember(store) { mutableStateOf(store?.selection ?: BrowseSelection()) }
    var jump by remember(feed?.revision, feed?.page) { mutableStateOf(false) }
    var caption by remember(feed?.revision, feed?.page, state.covered) { mutableStateOf<HomeAsset?>(null) }
    var slideshow by remember(store) { mutableStateOf(false) }
    val grid = rememberLazyGridState()
    LaunchedEffect(feed?.revision, feed?.page, selection) { grid.scrollToItem(0) }
    LaunchedEffect(state.covered, state.problem, state.mediaProblem, asset?.kind) {
        if (state.covered || state.problem != null || state.mediaProblem != null || asset?.kind != AssetKind.PHOTO) slideshow = false
    }
    LaunchedEffect(state.covered, state.problem) {
        if (state.covered) exploring = false
        state.problem?.let { discovery?.invalidateResults(it) }
    }
    fun leave() { slideshow = false; discovery?.background(); browseStore?.disconnect(); exit() }
    fun back() { slideshow = false; when { exploring -> { exploring = false; discovery?.close() }; state.video != null -> store?.closeVideo(); asset != null -> store?.backToPhotos(); discoveryState.results != null -> discovery?.clearResults(); else -> leave() } }
    BackHandler { back() }
    PhotoHouseTheme { Surface(Modifier.fillMaxSize()) {
        when {
            state.covered && store != null -> Box(Modifier.fillMaxSize().testTag("home-covered"), contentAlignment = Alignment.Center) {
                Text(t("Your album is covered.", "相册内容已隐藏。"))
            }
            exploring -> HomeDiscoveryEditor(discoveryState, zh, { exploring = false; discovery?.close() },
                { discovery?.open() }, { discovery?.more(it) }, { discovery?.search(it); exploring = false }, { text, selected -> discovery?.findTags(text,selected) }, calendarEnabled=discovery?.calendarEnabled==true, onCalendar={discovery?.calendar(it)})
            state.video != null -> {
                val video = requireNotNull(state.video)
                val source = remember(video) { HomePlaybackSource(video) }
                PhoneVideoPlayer(source, zh, { if (store?.state?.value?.video === video) store.closeVideo() },
                    { reason -> if (store?.state?.value?.video === video) { playbackFailure = reason; store.videoPlaybackFailed() } }, state.videoBookmark,
                    previous = if (state.adjacentVideo(-1) != null) ({ store?.adjacentVideo(-1) }) else null,
                    next = if (state.adjacentVideo(1) != null) ({ store?.adjacentVideo(1) }) else null)
            }
            asset?.kind == AssetKind.PHOTO && (state.display != null || state.busy) && state.mediaProblem == null -> {
                val items = feed?.items.orEmpty()
                fun adjacent(delta: Int) {
                    slideshow = false
                    items.getOrNull(state.index + delta)?.let { store?.openAsset(it, openPlayer = it.kind == AssetKind.VIDEO) }
                }
                OriginalPhotoViewer(state.display, state.busy, zh, { slideshow = false; store?.backToPhotos() },
                    navigation = PhotoNavigation(feed?.page ?: 1, items.map { it.id.toString() }, state.index),
                    slideshow = slideshow, onAdjacent = ::adjacent,
                    onToggleSlideshow = { slideshow = !slideshow }, onStopSlideshow = { slideshow = false },
                    onAdvanceSlideshow = {
                        val next = items.getOrNull(state.index + 1)
                        if (next?.kind == AssetKind.PHOTO && next.display != null) store?.openAsset(next) else slideshow = false
                    }, originalQuality = state.originalQuality,
                    onOriginal = if (asset.original != null) ({ slideshow = false; store?.openOriginal() }) else null)
            }
            asset != null -> Column(Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                TextButton(onClick = { store?.backToPhotos() }) { Text(t("Back to album", "返回相册")) }
                Text(if (asset.kind == AssetKind.VIDEO) t("Video", "视频") else t("Photo", "照片"), style = MaterialTheme.typography.headlineMedium)
                Text(asset.caption.ifEmpty { t("A family memory", "一段家的回忆") })
                if (state.videoFailed || state.mediaProblem != null) {
                    Text(state.mediaProblem?.let { homeProblem(it, zh) } ?: playbackFailure?.message(zh) ?: t("Video could not play. Retry or return to the album. [HOME-VIDEO]", "视频无法播放，请重试或返回相册。[HOME-VIDEO]"), Modifier.testTag("home-media-error"))
                } else if (asset.kind == AssetKind.VIDEO && asset.video == null || asset.kind != AssetKind.VIDEO && asset.display == null) {
                    Text(t("This media is not ready yet.", "此媒体尚未就绪。"))
                }
                if (asset.video != null) Button(onClick = { playbackFailure = null; store?.openVideo() }, enabled = !state.busy, modifier = Modifier.testTag("home-video-retry")) { Text(t("Open video", "打开视频")) }
                if (asset.display != null && asset.kind == AssetKind.PHOTO) Button(onClick = { store?.openAsset(asset) }, enabled = !state.busy) { Text(t("Retry photo", "重试照片")) }
                if (asset.original != null) OutlinedButton(onClick = { store?.openOriginal() }, enabled = !state.busy) { Text(t("Original quality", "原图画质")) }
            }
            else -> LazyVerticalGrid(columns = GridCells.Adaptive(if (LocalConfiguration.current.fontScale >= 1.5f) 260.dp else 150.dp), state = grid,
                modifier = Modifier.fillMaxSize().safeDrawingPadding().testTag("home-gallery"),
                contentPadding = PaddingValues(16.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item(span = { GridItemSpan(maxLineSpan) }) { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = ::leave, modifier = Modifier.testTag("home-exit")) { Text(t("Access modes", "访问方式")) }
                        TextButton(onClick = { zh = !zh }, modifier = Modifier.testTag("home-language")) { Text(if (zh) "English" else "简体中文") }
                    }
                    Text(if (discoveryState.query != null) t("Search results", "搜索结果") else t("At home", "家的相册"), style = MaterialTheme.typography.headlineLarge, fontFamily = FontFamily.Serif)
                    Text(t("A little closer to your memories.", "让回忆，离我们再近一点。"), style = MaterialTheme.typography.bodyMedium)
                    if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                    if (store == null) Text(t("This build needs your home server configuration.", "此版本需要配置家庭服务器。"), Modifier.testTag("home-setup"))
                    state.problem?.let { Text(homeProblem(it, zh), Modifier.testTag("home-error")) }
                    if (store != null) OutlinedButton(onClick = { if (state.disconnected) store.reconnect() else store.loadPage() }, enabled = !state.busy,
                        modifier = Modifier.testTag("home-refresh")) { Text(t("Refresh album", "刷新相册")) }
                    if (discovery != null && feed != null && !state.disconnected) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { discovery.open(); exploring = true }, enabled = !state.busy, modifier = Modifier.testTag("home-explore")) { Text(if (discoveryState.query == null) t("Find memories", "查找回忆") else t("Edit filters", "修改条件")) }
                        if (discoveryState.query != null) TextButton(onClick = { discovery.clearResults() }, modifier = Modifier.testTag("home-clear-search")) { Text(t("Clear search", "清除搜索")) }
                    }
                    discoveryState.query?.let { Text(t("${it.count} filters applied", "已应用 ${it.count} 类条件"), modifier = Modifier.testTag("home-search-summary")) }
                    if (store?.browseEnabled == true) {
                        fun choose(value: BrowseSelection) { selection = value; store.selectBrowse(value) }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            FilterChip(selection.order == BrowseOrder.READY_FIRST, { choose(selection.copy(order = if (selection.order == BrowseOrder.READY_FIRST) BrowseOrder.CATALOG else BrowseOrder.READY_FIRST)) },
                                label = { Text(t("Ready first", "优先显示已就绪")) }, modifier = Modifier.testTag("home-ready-first"))
                            FilterChip(selection.availability == Availability.READY, { choose(selection.copy(availability = if (selection.availability == Availability.READY) Availability.ALL else Availability.READY)) },
                                label = { Text(t("Ready only", "仅显示已就绪")) }, modifier = Modifier.testTag("home-ready-only"))
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            BrowseMedia.entries.forEach { media -> FilterChip(selection.media == media, { choose(selection.copy(media = media)) },
                                label = { Text(when (media) { BrowseMedia.ALL -> t("All", "全部"); BrowseMedia.PHOTOS -> t("Photos", "照片"); BrowseMedia.VIDEOS -> t("Videos", "视频") }) },
                                modifier = Modifier.testTag("home-media-${media.wire}")) }
                        }
                    }
                    feed?.browseCounts?.let { Text(t("${it.ready} ready · ${it.matching} matching", "${it.ready} 项已就绪 · 共 ${it.matching} 项"), style = MaterialTheme.typography.labelLarge) }
                    if (state.gridProblems.isNotEmpty() || state.missingGrids.isNotEmpty()) TextButton(onClick = { store?.retryPreviews() }, modifier = Modifier.testTag("home-retry-previews")) { Text(t("Retry missing previews", "重试缺失预览")) }
                    if (feed != null) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { store?.loadPage(feed.page - 1) }, enabled = feed.page > 1 && !state.busy) { Text(t("Previous", "上一页")) }
                        TextButton(onClick = { jump = true }, enabled = !state.busy, modifier = Modifier.testTag("home-page")) { Text(t("Page ${feed.page} · Jump", "第 ${feed.page} 页 · 跳转")) }
                        OutlinedButton(onClick = { store?.loadPage(feed.page + 1) }, enabled = feed.hasMore && !state.busy, modifier = Modifier.testTag("home-next")) { Text(t("Next", "下一页")) }
                    }
                    if (feed != null && feed.items.isEmpty()) Text(t("No matching memories yet. Change filters or refresh after more media is published.", "暂无匹配的回忆。请调整筛选，或在更多媒体发布后刷新。"), Modifier.testTag("home-empty"))
                } }
                items(feed?.items.orEmpty(), key = { it.id }) { item ->
                    Card(onClick = { store?.openAsset(item, openPlayer = item.kind == AssetKind.VIDEO) }, modifier = Modifier.fillMaxWidth().testTag("home-asset-${item.id}")) {
                        HomeThumbnail(state.grids[item.id], item.caption, if (item.id in state.gridProblems || item.id in state.missingGrids || item.grid == null)
                            t("Preview unavailable", "预览不可用") else t("Loading preview…", "加载预览…"))
                        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(if (item.kind == AssetKind.VIDEO) t("Video", "视频") else t("Photo", "照片"), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary)
                            Text(item.caption.ifEmpty { t("A family memory", "一段家的回忆") }, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            TextButton(onClick = { caption = item }, contentPadding = PaddingValues(0.dp)) { Text(t("Details", "详情")) }
                        }
                    }
                }
            }
        }
        if (jump && feed != null && !state.covered) PhonePageJump(feed.page, feed.pageSize, feed.total.toLong(), zh, { jump = false }) { jump = false; store?.loadPage(it) }
        caption?.takeIf { !state.covered }?.let { item -> AlertDialog(onDismissRequest = { caption = null },
            title = { Text(t("Memory ${item.id}", "回忆 ${item.id}")) },
            text = { Text(item.caption.ifEmpty { t("No caption yet.", "暂无描述。") }, Modifier.verticalScroll(rememberScrollState())) },
            confirmButton = { TextButton(onClick = { caption = null }) { Text(t("Close", "关闭")) } }) }
    } }
}

@Composable internal fun HomeThumbnail(bytes: ByteArray?, caption: String, unavailable: String) {
    val photo by produceState<DecodedPhoto?>(null, bytes) {
        value = if (bytes == null) null else withContext(Dispatchers.Default) { decodeOriginalPhoto(bytes) }
    }
    Box(Modifier.fillMaxWidth().aspectRatio(1.25f), contentAlignment = Alignment.Center) {
        photo?.let { Image(it.bitmap.asImageBitmap(), caption, Modifier.fillMaxSize().testTag("home-thumbnail"), contentScale = ContentScale.Crop) }
            ?: Text(unavailable, Modifier.padding(16.dp), style = MaterialTheme.typography.bodySmall)
    }
}

internal fun homeProblem(error: HomeError, zh: Boolean): String = if (zh) when (error) {
    HomeError.DENIED -> "服务器未允许此设备。请连接家庭网络，并请家庭管理员授权此手机。"
    HomeError.TLS -> "无法验证家庭服务器的安全连接，请检查服务器证书。"
    HomeError.OFFLINE -> "无法连接家庭服务器。请检查家庭网络；离家后请返回账号登录。"
    HomeError.CHANGED -> "相册已更新，请刷新后重新浏览。"
    HomeError.BUSY -> "服务器正忙，请稍候再试。"
    HomeError.UNAVAILABLE -> "家庭相册暂不可用，请稍后刷新。"
    HomeError.INVALID -> "此版本无法读取服务器响应，请检查应用与服务器版本。"
} else when (error) {
    HomeError.DENIED -> "The server has not approved this device. Join your home network and ask the owner to allow this phone."
    HomeError.TLS -> "The home server's secure connection could not be verified. Check its certificate."
    HomeError.OFFLINE -> "Cannot reach your home server. Check the home network; away from home, return to Sign in."
    HomeError.CHANGED -> "The album changed. Refresh to browse again."
    HomeError.BUSY -> "The server is busy. Please wait before retrying."
    HomeError.UNAVAILABLE -> "The home album is temporarily unavailable. Refresh later."
    HomeError.INVALID -> "This app could not read the response. Check the app and server versions."
}
