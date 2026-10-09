package dev.photohouse.tv

import android.view.KeyEvent as AndroidKey
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.style.TextOverflow
import dev.photohouse.home.*
import dev.photohouse.ota.PhotoHouseOtaControl
import kotlinx.coroutines.delay

internal val Ink = Color(0xFF10231F)
internal val Cream = Color(0xFFF6ECD9)
internal val Gold = Color(0xFFEBC384)
internal val Moss = Color(0xFF233C32)
internal val Muted = Color(0xFFC0C8BE)
internal val Edge = Color(0xFF496258)

@Composable internal fun TvButton(label: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    // TV focus must survive a touch/air-mouse interaction and return to the remote.
    Button(onClick, modifier.heightIn(min = 40.dp).focusProperties { canFocus = enabled }.onFocusChanged { focused = it.isFocused }, enabled = enabled,
        shape = RoundedCornerShape(10.dp), contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
        border = BorderStroke(if (focused) 3.dp else 1.dp, if (focused) Gold else Edge),
        colors = ButtonDefaults.buttonColors(containerColor = if (focused) Gold else Moss,
            contentColor = if (focused) Ink else Cream)) { Text(label, maxLines = 1, style = MaterialTheme.typography.labelMedium) }
}

@Composable fun TvApp(browseStore: HomeStore?, discovery: DiscoveryController? = null, initialLanguage: String = "zh") {
    val discoveryState = discovery?.state?.collectAsState()?.value ?: DiscoveryState()
    val store = discoveryState.results ?: browseStore
    var language by remember { mutableStateOf(initialLanguage) }
    val zh = language == "zh" || language == "system" && LocalConfiguration.current.locales[0].language == "zh"
    fun t(en: String, cn: String) = if (zh) cn else en
    // A result store is replaced on each query. Do not briefly reuse its covered/error
    // state while Compose subscribes to the browse store after clearing the search.
    val state = key(store) { store?.state?.collectAsState()?.value ?: HomeState() }
    val viewer = state.asset != null
    var exploring by remember { mutableStateOf(false) }
    var restoreExplore by remember { mutableStateOf(false) }
    val exploreFocus = remember { FocusRequester() }
    var playing by remember(store, state.feed?.id, state.feed?.page, state.feed?.revision,
        store?.selection?.collectionId) { mutableStateOf(false) }
    var slideSeconds by remember { mutableIntStateOf(TV_SLIDESHOW_DEFAULT_SECONDS) }
    var slideshowComplete by remember(store, state.feed?.id, state.feed?.page, state.feed?.revision,
        store?.selection?.collectionId, state.selected) { mutableStateOf(false) }
    var immersive by remember { mutableStateOf(false) }
    var transform by remember(state.selected, state.feed?.revision, state.covered) { mutableStateOf(PhotoTransform()) }
    var playbackFailure by remember(store, state.selected, state.feed?.revision, state.covered) { mutableStateOf<TvPlaybackFailure?>(null) }
    var hintTick by remember { mutableStateOf(0) }
    var showHint by remember { mutableStateOf(true) }
    LaunchedEffect(immersive, hintTick) { showHint = true; if (immersive) { delay(4000); showHint = false } }
    var pages by remember(state.feed?.id, state.feed?.revision) { mutableStateOf(false) }
    var captions by remember { mutableStateOf(false) }
    var updates by remember { mutableStateOf(false) }
    var lastAsset by remember(state.feed?.id) { mutableStateOf<Int?>(null) }
    val first = remember { FocusRequester() }
    val selectedLibraryFocus = remember { FocusRequester() }
    val retryLibrariesFocus = remember { FocusRequester() }
    val galleryToolbarScroll = key(browseStore) { rememberScrollState() }
    var pendingLibraryFocus by remember(browseStore) { mutableStateOf<LibraryFocusIntent?>(null) }
    var pendingLibraryRetryFocus by remember(browseStore) { mutableStateOf(false) }
    val route = when { state.covered -> "covered"; store == null -> "setup"; exploring -> "explore"; state.feed == null -> "connection"; state.video != null -> "video"; viewer -> "viewer"; else -> "grid" }
    var galleryGridHasFocus by remember(store, store?.selection, route) { mutableStateOf(false) }
    LaunchedEffect(route) {
        if (route != "grid") updates = false
        if (route == "viewer" || route == "video") {
            restoreExplore = false
            pendingLibraryFocus = null
        }
    }
    val grid = rememberLazyGridState()
    val focusAsset = state.feed?.items?.firstOrNull { it.id == lastAsset && it.canOpen() }
        ?: state.feed?.items?.firstOrNull { it.canOpen() }
    val view = LocalView.current
    val focusedWindow = LocalWindowInfo.current.isWindowFocused
    DisposableEffect(playing, state.covered, view) {
        view.keepScreenOn = playing && !state.covered
        onDispose { view.keepScreenOn = false }
    }
    LaunchedEffect(route, state.feed?.page, state.busy, state.collectionsProblem, state.problem,
        state.covered, state.disconnected, store, focusedWindow, restoreExplore) {
        if (!focusedWindow) return@LaunchedEffect
        // Re-request after a remote navigation transition, but not on every thumbnail update.
        // An empty gallery has no LazyVerticalGrid layout; scrolling its state would
        // suspend forever and leave the remote without focus after Explore closes.
        if (route == "grid" && state.feed?.items?.isNotEmpty() == true) {
            val index = state.feed?.items?.indexOfFirst { it.id == focusAsset?.id } ?: -1
            grid.scrollToItem(index.coerceAtLeast(0))
        }
        withFrameNanos { }
        if (pendingLibraryRetryFocus) {
            if (route != "grid" || state.busy || state.feed == null) {
                if (state.problem != null || state.covered || state.disconnected) pendingLibraryRetryFocus = false
                return@LaunchedEffect
            }
            if (store == null || store !== browseStore) {
                pendingLibraryRetryFocus = false
                return@LaunchedEffect
            }
            val latest = store.state.value
            val latestFeed = latest.feed
            val latestCollections = latest.collections
            if (latest.busy || latestFeed == null || latest.covered || latest.disconnected) return@LaunchedEffect
            pendingLibraryRetryFocus = false
            if (latest.collectionsProblem != null) {
                runCatching { retryLibrariesFocus.requestFocus() }
            } else if (latestCollections != null && latestCollections.revision == latestFeed.revision) {
                pendingLibraryFocus = LibraryFocusIntent(store.selection.collectionId)
                withFrameNanos { }
                val current = store.state.value
                val selectedStillValid = store.selection.collectionId?.let { id ->
                    current.collections?.collections?.any { it.id == id } == true
                } ?: true
                if (current.collectionsProblem == null && !current.busy && current.feed?.revision == current.collections?.revision &&
                    selectedStillValid) {
                    runCatching { selectedLibraryFocus.requestFocus() }
                }
                pendingLibraryFocus = null
            }
            return@LaunchedEffect
        }
        val libraryFocus = pendingLibraryFocus
        if (libraryFocus != null) {
            if (route == "grid" && !state.busy && state.problem == null && !state.covered &&
                !state.disconnected && store === browseStore && !exploring &&
                store?.selection?.collectionId == libraryFocus.collectionId) {
                runCatching { selectedLibraryFocus.requestFocus() }
                pendingLibraryFocus = null
            }
            return@LaunchedEffect
        }
        if (route != "explore") runCatching {
            if (route == "grid" && restoreExplore) {
                (if (focusAsset == null) first else exploreFocus).requestFocus()
                // Keep the return target through a result-store switch and its
                // asynchronous browse reload. Entering a viewer clears it.
            } else first.requestFocus()
        }
    }
    LaunchedEffect(state.covered, state.disconnected, state.problem, store, store?.selection?.collectionId, browseStore, exploring) {
        if (pendingLibraryFocus != null && (state.covered || state.disconnected || state.problem != null ||
                store !== browseStore || store?.selection?.collectionId != pendingLibraryFocus?.collectionId || exploring))
            pendingLibraryFocus = null
    }
    LaunchedEffect(state.covered, state.problem, viewer, state.disconnected, state.asset?.kind) {
        if (state.covered || state.disconnected || state.problem == HomeError.DENIED) { exploring = false; restoreExplore = false }
        if (discoveryState.results != null) state.problem?.let { discovery?.invalidateResults(it) }
        if (state.covered || state.problem != null || !viewer || state.disconnected || state.asset?.kind != AssetKind.PHOTO) {
            playing = false; immersive = false; captions = false
        }
    }
    LaunchedEffect(focusedWindow, route, store, store?.selection?.collectionId,
        state.covered, state.disconnected, state.problem, state.mediaProblem,
        state.displayMissing, state.asset?.kind) {
        // Focus loss is a real stop. Regaining focus never starts playback again.
        if (!focusedWindow || route != "viewer" || state.covered || state.disconnected ||
            state.problem != null || state.mediaProblem != null || state.displayMissing ||
            state.asset?.kind != AssetKind.PHOTO) {
            playing = false
            slideshowComplete = false
        }
    }
    LaunchedEffect(playing, slideSeconds, store, store?.selection?.collectionId,
        state.feed?.id, state.feed?.page, state.feed?.revision, state.selected,
        state.busy, state.problem, state.covered, state.disconnected,
        state.mediaProblem, state.displayMissing, state.asset?.kind, focusedWindow) {
        if (playing && !state.busy && viewer && focusedWindow && state.problem == null &&
            !state.covered && !state.disconnected && state.mediaProblem == null &&
            !state.displayMissing && state.display != null && state.asset?.kind == AssetKind.PHOTO) {
            val expectedStore = store
            val expectedCollection = store?.selection?.collectionId
            val expectedFeedId = state.feed?.id
            val expectedPage = state.feed?.page
            val expectedRevision = state.feed?.revision
            val expectedSelected = state.selected
            delay(slideSeconds * 1000L)
            val latest = expectedStore?.state?.value ?: return@LaunchedEffect
            val currentStore = discovery?.state?.value?.results ?: browseStore
            val scopeStillMatches = currentStore === expectedStore &&
                currentStore.selection.collectionId == expectedCollection &&
                expectedStore.selection.collectionId == expectedCollection
            val pageStillMatches = latest.feed?.id == expectedFeedId && latest.feed?.page == expectedPage &&
                latest.feed?.revision == expectedRevision && latest.selected == expectedSelected
            if (!scopeStillMatches || !pageStillMatches) {
                playing = false
                slideshowComplete = false
                return@LaunchedEffect
            }
            if (latest.busy || latest.covered || latest.disconnected || latest.problem != null || latest.display == null ||
                latest.mediaProblem != null || latest.displayMissing || latest.asset?.kind != AssetKind.PHOTO ||
                !focusedWindow) {
                playing = false
            } else {
                val next = nextPreparedPagePhoto(latest)
                if (next == null) {
                    playing = false
                    slideshowComplete = true
                } else {
                    // openAsset uses the prepared display variant; it does not enter video playback
                    // or request an original. The candidate came from this loaded feed page.
                    store.openAsset(next)
                }
            }
        }
    }
    fun back() { playing = false; store?.backToPhotos() }
    BackHandler(viewer && !state.covered) { if (transform.zoom > 1f) transform = PhotoTransform() else if (immersive) immersive = false else back() }
    BackHandler(!viewer && !exploring && !state.covered && discoveryState.query != null) {
        restoreExplore = true; discovery?.clearResults()
    }
    MaterialTheme(colorScheme = darkColorScheme(primary = Gold, background = Ink, surface = Ink, onBackground = Cream, onSurface = Cream)) {
        if (pages && state.feed != null && !state.covered && !viewer) {
            PageJump(state.feed!!.page, state.feed!!.total, zh, { pages = false }, { pages = false; store?.loadPage(it) })
        }
        if (captions && viewer && !state.covered) {
            val closeFocus = remember { FocusRequester() }
            AlertDialog(onDismissRequest = { captions = false },
                title = { Text(if ((state.feed?.version ?: 1) >= 2) t("Asset details", "内容信息") else t("Photo captions", "照片说明")) },
                text = { Column(Modifier.heightIn(max = 260.dp).verticalScroll(rememberScrollState())) {
                    Text(state.asset?.caption?.ifEmpty { t("No captions yet.", "暂无说明。") }.orEmpty())
                } },
                confirmButton = {
                    TvButton(t("Close", "关闭"), Modifier.testTag("captions-close").focusRequester(closeFocus)) { captions = false }
                    val focusedWindow = LocalWindowInfo.current.isWindowFocused
                    LaunchedEffect(focusedWindow) {
                        if (focusedWindow) { withFrameNanos { }; closeFocus.requestFocus() }
                    }
                })
        }
        if (updates && route == "grid" && !state.covered) {
            val updateFocus = remember { FocusRequester() }
            AlertDialog(onDismissRequest = { updates = false },
                title = { Text(t("App updates", "应用更新")) },
                text = {
                    LaunchedEffect(Unit) { withFrameNanos { }; updateFocus.requestFocus() }
                    PhotoHouseOtaControl("tv", BuildConfig.PHOTOHOUSE_UPDATE_ORIGIN, zh,
                        Modifier.testTag("ota-control"),
                        lanAddress = BuildConfig.PHOTOHOUSE_UPDATE_LAN_ADDRESS,
                        checkModifier = Modifier.focusRequester(updateFocus)) { label, modifier, enabled, onClick ->
                        TvButton(label, modifier, enabled, onClick)
                    }
                },
                confirmButton = { TvButton(t("Close", "关闭"), Modifier.testTag("updates-close")) { updates = false } })
        }
        Surface(Modifier.fillMaxSize(), color = Ink) {
            val video = state.video
            if (video != null && !state.covered && state.problem == null) {
                TvVideoPlayer(video, zh, { if (store?.state?.value?.video === video) store.closeVideo() },
                    { reason -> if (store?.state?.value?.video === video) { playbackFailure = reason; store.videoPlaybackFailed() } }, state.videoBookmark,
                    previous = if (state.adjacentVideo(-1) != null) ({ store?.adjacentVideo(-1) }) else null,
                    next = if (state.adjacentVideo(1) != null) ({ store?.adjacentVideo(1) }) else null)
                return@Surface
            }
            if (immersive && viewer && !state.covered && state.feed != null) {
                val remote = remember { FocusRequester() }
                LaunchedEffect(Unit) { remote.requestFocus() }
                Box(Modifier.fillMaxSize().background(Color.Black).testTag("immersive")
                    .focusRequester(remote).onPreviewKeyEvent {
                        if (it.nativeKeyEvent.action != AndroidKey.ACTION_DOWN) false
                        else { hintTick++; when (it.nativeKeyEvent.keyCode) {
                            AndroidKey.KEYCODE_DPAD_LEFT -> { playing = false; if (transform.zoom > 1f) transform = transform.pan(0.2f, 0f) else store?.adjacentPhoto(-1); true }
                            AndroidKey.KEYCODE_DPAD_RIGHT -> { playing = false; if (transform.zoom > 1f) transform = transform.pan(-0.2f, 0f) else store?.adjacentPhoto(1); true }
                            AndroidKey.KEYCODE_DPAD_UP -> { transform = transform.pan(0f, 0.2f); true }
                            AndroidKey.KEYCODE_DPAD_DOWN -> { transform = transform.pan(0f, -0.2f); true }
                            AndroidKey.KEYCODE_DPAD_CENTER, AndroidKey.KEYCODE_ENTER -> {
                                playing = false; transform = transform.nextZoom(); true
                            }
                            AndroidKey.KEYCODE_MEDIA_PLAY_PAUSE -> {
                                transform = PhotoTransform()
                                if (!state.busy && state.problem == null && state.mediaProblem == null &&
                                    !state.displayMissing && state.display != null && state.asset?.kind == AssetKind.PHOTO) {
                                    if (playing) { playing = false; slideshowComplete = false }
                                    else { slideshowComplete = false; playing = true }
                                }
                                true
                            }
                            else -> false
                        }
                    } }.focusable()) {
                    val bytes = state.display
                    TvImage(bytes, t("Photo", "照片") + " ${state.selected ?: ""}", Modifier.fillMaxSize(), if (state.asset?.kind == AssetKind.VIDEO) t("Video", "视频") else unavailableText(state.asset?.displayUnavailable, zh), transform = transform, loading = state.busy, original = state.originalQuality)
                    if (showHint) Text("${transform.zoom.toInt()}× · " + if (transform.zoom > 1f)
                        t("Arrows Pan · OK Zoom · Back Reset", "方向键 移动 · 确定 缩放 · 返回 还原") else
                        t("← → Photos · OK Zoom · Back Controls", "← → 切换照片 · 确定 缩放 · 返回 控制栏"),
                        Modifier.align(Alignment.BottomCenter).background(Color.Black.copy(alpha = 0.65f)).padding(8.dp), style = MaterialTheme.typography.labelSmall)
                }
                return@Surface
            }
            Column(Modifier.fillMaxSize().safeDrawingPadding().padding(horizontal = 28.dp, vertical = 12.dp).testTag("tv-screen")) {
                if (route != "grid") {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(t("PhotoHouse", "拾光相册"), fontFamily = FontFamily.Serif, style = MaterialTheme.typography.titleLarge)
                        Text(t("A little closer to home", "把回忆带回家") + " · v${BuildConfig.VERSION_CODE}", style = MaterialTheme.typography.bodySmall, color = Muted)
                    }
                    TvButton(if (zh) "English" else "简体中文", Modifier.testTag("language")) { language = if (zh) "en" else "zh" }
                    if (state.feed != null && !state.covered) TvButton(t("Disconnect", "断开连接"), Modifier.testTag("disconnect")) { playing = false; discovery?.background(); browseStore?.disconnect() }
                }
                Spacer(Modifier.height(8.dp))
                PhotoHouseOtaControl("tv", BuildConfig.PHOTOHOUSE_UPDATE_ORIGIN, zh,
                    Modifier.testTag("ota-control").then(
                        if (store == null || state.feed == null) Modifier.focusRequester(first) else Modifier
                    ), lanAddress = BuildConfig.PHOTOHOUSE_UPDATE_LAN_ADDRESS) { label, modifier, enabled, onClick ->
                    TvButton(label, modifier, enabled, onClick)
                }
                }
                if (state.busy) {
                    Surface(Modifier.fillMaxWidth().testTag("tv-loading-status"), color = Moss,
                        shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Edge)) {
                        Column(Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(t("Updating your photos…", "正在更新照片…"),
                                style = MaterialTheme.typography.labelLarge, color = Gold)
                            LinearProgressIndicator(Modifier.fillMaxWidth())
                        }
                    }
                }
                state.problem?.let { problem ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(if (problem == HomeError.CHANGED && discoveryState.query != null)
                            t("The library changed. Edit filters to start a fresh search.", "媒体库已更新，请修改条件后重新搜索。") else problemText(problem, zh),
                            Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                    }
                }
                when {
                    store == null -> Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.Center) {
                        Text(t("Your family album, on the big screen.", "在大屏幕上，重温家里的故事。"), style = MaterialTheme.typography.headlineLarge)
                        Spacer(Modifier.height(16.dp))
                        Text(t("Server setup needed. Ask for a TV build configured for your home photo feed.", "需要配置服务器。请获取已配置家庭照片源的电视版本。"), Modifier.testTag("setup"))
                        TvButton(if (zh) "English" else "简体中文") { language = if (zh) "en" else "zh" }
                    }
                    state.covered -> Column {
                        Text(t("Private content is covered.", "私人内容已隐藏。"), Modifier.testTag("covered"))
                    }
                    exploring -> TvDiscovery(discoveryState.snapshot?.options, zh, discoveryState.query ?: DiscoveryDraft(),
                        onClose = { discovery?.close(); exploring = false; restoreExplore = true },
                        onApply = if (discoveryState.snapshot != null && !discoveryState.loading && discoveryState.problem == null) {
                            { query -> discovery?.search(query); exploring = false }
                        } else null,
                        loading = discoveryState.loading, problem = discoveryState.problem,
                        onRetry = { discovery?.open() }, more = discoveryState.snapshot?.nextPages?.keys.orEmpty(),
                        onMore = { discovery?.more(it) }, tagQuery=discoveryState.snapshot?.tagQuery,
                        tagMatches=discoveryState.snapshot?.tagMatches?.size ?: 0, tagTotal=discoveryState.snapshot?.facetTotals?.get(DiscoveryField.TAGS) ?: 0,
                        onFindTags={ text, selected -> discovery?.findTags(text,selected) },calendarEnabled=discovery?.calendarEnabled==true,calendar=discoveryState.calendar,onCalendar={discovery?.calendar(it)})
                    state.feed == null -> Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.Center) {
                        Text(if (state.disconnected) t("Display disconnected", "屏幕已断开") else if (state.problem != null) t("Home photos unavailable", "暂时无法查看家庭照片") else t("Connecting to your home photos…", "正在连接家庭照片…"),
                            style = MaterialTheme.typography.headlineLarge, modifier = Modifier.testTag("home-access-needed"))
                        Spacer(Modifier.height(16.dp))
                        Text(t("No personal sign-in is needed on this screen.", "此屏幕无需个人登录。"))
                        if (state.disconnected) TvButton(t("Reconnect", "重新连接")) { store.reconnect() }
                        else TvButton(t("Retry", "重试"), enabled = !state.busy) { store.retry() }
                        if (discoveryState.query != null) {
                            TvButton(t("Edit filters", "修改条件"), Modifier.testTag("edit-search")) { exploring = true; discovery?.open() }
                            TvButton(t("Clear search", "清除搜索"), Modifier.testTag("clear-results")) { discovery?.clearResults() }
                        }
                    }
                    viewer -> {
                        val slideshowAvailable = state.asset?.kind == AssetKind.PHOTO && !state.busy &&
                            state.problem == null && state.mediaProblem == null && !state.displayMissing && state.display != null
                        val bytes = state.display
                        Box(Modifier.fillMaxWidth().weight(1f).background(Color.Black).testTag("viewer")) {
                            if (state.videoFailed) Box(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).focusable().padding(horizontal = 16.dp, vertical = 4.dp)) {
                                Text(state.mediaProblem?.let { mediaProblemText(it, zh) } ?: playbackFailure?.message(zh) ?: t("Playback unavailable. Retry or choose another video. [TV-READ]", "暂时无法播放。请重试或选择其他视频。[TV-READ]"), Modifier.testTag("video-error"))
                            } else TvImage(bytes, t("Photo", "照片") + " ${state.selected ?: ""}", Modifier.fillMaxSize(), if (state.asset?.kind == AssetKind.VIDEO) t("Video", "视频") else unavailableText(state.asset?.displayUnavailable, zh), transform = transform, loading = state.busy, original = state.originalQuality)
                        }
                        if (state.mediaProblem != null && state.asset?.kind != AssetKind.VIDEO) {
                            Text(mediaProblemText(state.mediaProblem!!, zh), Modifier.testTag("media-error"))
                            TvButton(t("Retry photo", "重试照片"), Modifier.testTag("retry-photo"), !state.busy) { state.asset?.let { store.openAsset(it) } }
                        }
                        if (state.asset?.kind == AssetKind.VIDEO) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                if (state.asset?.video != null) TvButton(t("Open video", "打开视频"), Modifier.testTag("open-video"), enabled = !state.busy) { playing = false; playbackFailure = null; store.openVideo() }
                                if (state.asset?.video == null) Text(unavailableText(state.asset?.videoUnavailable, zh), Modifier.testTag("video-unavailable"))
                                else if (!state.videoFailed) Text(t("Video · Press Play after opening", "视频 · 打开后按播放"))
                            }
                        }
                        // Keep the control surface scrollable when the TV uses large system text.
                        Column(Modifier.fillMaxWidth().heightIn(max = 260.dp).verticalScroll(rememberScrollState())) {
                        // Toolbar arrows move focus; immersive mode maps arrows to photos.
                        Row(Modifier.fillMaxWidth().padding(top = 10.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            TvButton(if ((state.feed?.version ?: 1) >= 2) t("Library", "媒体库") else t("Photos", "照片"), Modifier.focusRequester(first)) { back() }
                            TvButton(t("Previous", "上一张"), enabled = !state.busy && state.adjacentAsset(-1) != null) { playing = false; store.adjacentPhoto(-1) }
                            if (state.asset?.kind == AssetKind.PHOTO) TvButton(if (playing) t("Pause", "暂停") else t("Play page photos", "播放本页照片"), Modifier.testTag("slideshow").onPreviewKeyEvent {
                                if (it.nativeKeyEvent.action != AndroidKey.ACTION_DOWN) false
                                else when (it.nativeKeyEvent.keyCode) {
                                    AndroidKey.KEYCODE_MEDIA_PLAY_PAUSE -> {
                                        if (!slideshowAvailable) false else {
                                            transform = PhotoTransform()
                                            if (playing) { playing = false; slideshowComplete = false }
                                            else { slideshowComplete = false; playing = true }
                                            true
                                        }
                                    }
                                    else -> false
                                }
                            }, enabled = slideshowAvailable) {
                                transform = PhotoTransform()
                                if (playing) { playing = false; slideshowComplete = false }
                                else { slideshowComplete = false; playing = true }
                            }
                            TvButton(t("Next", "下一张"), enabled = !state.busy && state.adjacentAsset(1) != null) { playing = false; store.adjacentPhoto(1) }
                            if (state.asset?.kind == AssetKind.PHOTO) {
                            TvButton(t("Full screen", "全屏"), Modifier.testTag("fullscreen"), enabled = !state.busy && state.display != null) { immersive = true }
                            TvButton(if (transform.fill) t("Fit photo", "完整显示") else t("Fill screen", "填满画面"), Modifier.testTag("photo-fit"), enabled = !state.busy && state.display != null) {
                                playing = false; transform = PhotoTransform(fill = !transform.fill)
                            }
                            if (state.asset?.original != null) TvButton(
                                if (state.originalQuality) t("Original loaded", "已加载原图") else t("Original quality", "原图画质"),
                                Modifier.testTag("photo-original"), enabled = !state.busy && !state.originalQuality) {
                                playing = false; store.openOriginal()
                            }
                            TvButton(t("Zoom", "放大"), Modifier.testTag("photo-zoom"), enabled = state.display != null) {
                                playing = false; transform = transform.nextZoom(); immersive = true
                            }
                            }
                            TvButton(if ((state.feed?.version ?: 1) >= 2) t("Details", "信息") else t("Captions", "说明"), Modifier.testTag("captions")) {
                                if (!captions && playing) { playing = false; slideshowComplete = false }
                                captions = !captions
                            }
                        }
                        if (state.asset?.kind == AssetKind.PHOTO) {
                            Row(Modifier.fillMaxWidth().padding(top = 6.dp).horizontalScroll(rememberScrollState()),
                                horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text(t("Slide duration · ${slideSeconds}s", "播放间隔 · ${slideSeconds}秒"), Modifier.testTag("slideshow-speed-status"),
                                    style = MaterialTheme.typography.labelMedium, color = Gold)
                                TV_SLIDESHOW_INTERVALS_SECONDS.forEach { seconds ->
                                    TvButton(t("${if (slideSeconds == seconds) "✓ " else ""}${seconds}s",
                                        "${if (slideSeconds == seconds) "✓ " else ""}${seconds}秒"), Modifier.testTag("slideshow-speed-$seconds")
                                        .semantics { selected = slideSeconds == seconds }) {
                                        // Changing this key cancels the previous deadline and starts a fresh interval.
                                        slideSeconds = seconds
                                    }
                                }
                            }
                            if (slideshowComplete && !playing && state.mediaProblem == null &&
                                !state.displayMissing && state.problem == null && focusedWindow) {
                                Column(Modifier.fillMaxWidth().padding(top = 4.dp),
                                    verticalArrangement = Arrangement.spacedBy(6.dp), horizontalAlignment = Alignment.Start) {
                                    Text(t("This page’s prepared photos have finished.", "本页可播放照片已结束。"),
                                        Modifier.testTag("slideshow-complete"),
                                        style = MaterialTheme.typography.bodyMedium, color = Gold)
                                    TvButton(t("Play this photo again", "重播这张照片"), Modifier.testTag("slideshow-restart")) {
                                        slideshowComplete = false
                                        playing = true
                                    }
                                }
                            }
                        }
                        if (!state.videoFailed) Text("${state.index + 1} / ${state.feed!!.items.size}  ·  " +
                            if (state.asset?.kind == AssetKind.PHOTO) if (state.originalQuality) t("Original file · slide duration ${slideSeconds}s", "原始文件 · 播放间隔 ${slideSeconds}秒") else t("Display image · slide duration ${slideSeconds}s", "高清展示图 · 播放间隔 ${slideSeconds}秒") else if (state.asset?.video?.direct == true) t("Original video · streaming", "原始视频 · 流式播放") else t("Compatible video · streaming", "兼容视频 · 流式播放"), style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    else -> {
                        val gallery = state.feed
                        var menu by remember { mutableStateOf(false) }
                        val selection = store.selection
                        val previewRetry = state.gridProblems.isNotEmpty() || state.missingGrids.any { id -> gallery?.items?.any { it.id == id && it.grid != null } == true }
                        val compactGallery = LocalConfiguration.current.screenHeightDp <= 650
                        val galleryFontScale = LocalConfiguration.current.fontScale
                        val featured = gallery?.items?.firstOrNull { it.kind == AssetKind.PHOTO && it.canOpen() }
                            ?: gallery?.items?.firstOrNull { it.canOpen() }
                        val showFeatured = featured != null && !(compactGallery && galleryFontScale >= 1.5f)
                        if (store.browseEnabled && state.collectionsProblem != null) {
                            Surface(Modifier.fillMaxWidth().testTag("collections-recovery"),
                                color = Moss, shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Edge)) {
                                Row(Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                                    horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Text(t("Libraries could not be loaded", "无法加载媒体库"), Modifier.weight(1f).testTag("collections-error"),
                                        color = Cream, maxLines = 2)
                                    TvButton(t("Retry libraries", "重试媒体库"), Modifier.testTag("retry-libraries")
                                        .focusRequester(retryLibrariesFocus), !state.busy) {
                                        val latest = store.state.value
                                        val latestFeed = latest.feed
                                        if (store === browseStore && latestFeed != null && !latest.busy &&
                                            !latest.covered && !latest.disconnected && latest.collectionsProblem != null) {
                                            pendingLibraryRetryFocus = true
                                            store.loadPage(latestFeed.page)
                                        }
                                    }
                                }
                            }
                        }
                        Column(Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (!compactGallery || !galleryGridHasFocus) {
                                Column(Modifier.testTag("gallery-overview"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                                        if (galleryFontScale < 1.5f) Text(if (discoveryState.query != null) t("SEARCH RESULTS", "搜索结果") else t("YOUR SELECTED LIBRARY", "已选家庭媒体库"),
                                            style = MaterialTheme.typography.labelMedium, color = Gold, modifier = Modifier.testTag("gallery-kicker"))
                                        Text(if (discoveryState.query != null) t("Search results", "搜索结果") else gallery?.title?.takeIf { it.isNotBlank() } ?: t("PhotoHouse", "拾光相册"),
                                            style = if (galleryFontScale >= 1.5f) MaterialTheme.typography.titleLarge else MaterialTheme.typography.headlineLarge, color = Cream,
                                            modifier = Modifier.testTag("gallery-heading"))
                                        Text(t("Page ${gallery?.page ?: 1} of ${(gallery?.total ?: 0).let { (it + 49) / 50 }.coerceAtLeast(1)}  ·  ${gallery?.total ?: 0} memories",
                                            "第 ${gallery?.page ?: 1} 页，共 ${(gallery?.total ?: 0).let { (it + 49) / 50 }.coerceAtLeast(1)} 页  ·  ${gallery?.total ?: 0} 段回忆"),
                                            style = if (galleryFontScale >= 1.5f) MaterialTheme.typography.labelSmall else MaterialTheme.typography.bodyMedium, color = Muted,
                                            modifier = Modifier.testTag("gallery-summary"))
                                    }
                                    if (showFeatured && featured != null) {
                                        var featuredFocus by remember(featured.id) { mutableStateOf(false) }
                                        OutlinedButton(
                                            onClick = { lastAsset = featured.id; store.openAsset(featured, openPlayer = featured.kind == AssetKind.VIDEO && featured.video != null) },
                                            modifier = Modifier.fillMaxWidth().height(when {
                                                galleryFontScale >= 2f -> 120.dp
                                                galleryFontScale >= 1.5f -> 184.dp
                                                compactGallery -> 128.dp
                                                else -> 166.dp
                                            }).onFocusChanged { featuredFocus = it.isFocused }
                                                .focusProperties { canFocus = featured.canOpen() }.testTag("featured-asset-${featured.id}"),
                                            enabled = featured.canOpen(), shape = RoundedCornerShape(20.dp),
                                            contentPadding = PaddingValues(0.dp),
                                            colors = ButtonDefaults.outlinedButtonColors(containerColor = Moss, contentColor = Cream),
                                            border = BorderStroke(if (featuredFocus) 4.dp else 1.dp, if (featuredFocus) Gold else Edge)
                                        ) {
                                            Row(Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically) {
                                                TvImage(state.grids[featured.id], t("Featured photo", "精选照片"), Modifier.fillMaxHeight().weight(1.25f),
                                                    if (featured.id in state.gridProblems) t("Preview unavailable · Retry from More", "预览不可用 · 请在更多中重试") else t("Loading preview…", "正在加载预览…"),
                                                    maxPixels = 1_048_576, loading = featured.grid != null && state.grids[featured.id] == null && featured.id !in state.missingGrids && featured.id !in state.gridProblems)
                                                Column(Modifier.weight(1f).padding(horizontal = 22.dp, vertical = if (galleryFontScale >= 2f) 4.dp else 12.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                                                    if (galleryFontScale < 1.5f) {
                                                        Text(t("FEATURED", "精选内容"), style = MaterialTheme.typography.labelMedium, color = Gold)
                                                    }
                                                    Text(featured.caption.ifEmpty { t("A moment from your library", "来自家庭媒体库的一刻") },
                                                        maxLines = if (galleryFontScale >= 1.5f) 1 else 2, overflow = TextOverflow.Ellipsis,
                                                        style = MaterialTheme.typography.titleLarge, color = Cream)
                                                    Text(if (featured.kind == AssetKind.VIDEO) t("Video · Open to watch", "视频 · 打开观看") else t("Open photo", "打开照片"),
                                                        style = MaterialTheme.typography.bodyMedium, color = Muted)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        // Keep primary browsing controls together; secondary actions stay in More.
                        Row(Modifier.fillMaxWidth().background(Moss.copy(alpha = 0.72f), RoundedCornerShape(16.dp)).padding(horizontal = 8.dp, vertical = 4.dp).testTag("gallery-toolbar").horizontalScroll(galleryToolbarScroll),
                            horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            val collections = state.collections
                            if (store.browseEnabled && collections != null) {
                                val selectedCollection = selection.collectionId
                                TvButton((if (selectedCollection == null) "✓ " else "") + t("All libraries", "全部媒体库"),
                                    Modifier.then(if (pendingLibraryFocus?.collectionId == null && pendingLibraryFocus != null) Modifier.focusRequester(selectedLibraryFocus) else Modifier)
                                        .testTag("collection-all").semantics { selected = selectedCollection == null }, !state.busy && state.collectionsProblem == null) {
                                    val latest = store.state.value
                                    if (store === browseStore && !latest.busy && !latest.covered && !latest.disconnected &&
                                        latest.collectionsProblem == null && latest.collections != null && latest.feed != null) {
                                        val activeSelection = store.selection
                                        pendingLibraryFocus = if (activeSelection.collectionId != null) LibraryFocusIntent(null) else null
                                        store.selectBrowse(activeSelection.copy(collectionId = null))
                                    }
                                }
                                for (collection in collections.collections) {
                                    val label = "${collection.title} · ${collection.mediaCount}"
                                    TvButton((if (selectedCollection == collection.id) "✓ " else "") + label,
                                        Modifier.then(if (pendingLibraryFocus?.collectionId == collection.id) Modifier.focusRequester(selectedLibraryFocus) else Modifier)
                                            .testTag("collection-${collection.id}").semantics { selected = selectedCollection == collection.id }, !state.busy && state.collectionsProblem == null) {
                                        val latest = store.state.value
                                        val currentCollections = latest.collections
                                        if (store === browseStore && !latest.busy && !latest.covered && !latest.disconnected &&
                                            latest.collectionsProblem == null && currentCollections != null && latest.feed != null &&
                                            currentCollections.collections.any { it.id == collection.id }) {
                                            val activeSelection = store.selection
                                            pendingLibraryFocus = if (activeSelection.collectionId != collection.id) LibraryFocusIntent(collection.id) else null
                                            store.selectBrowse(activeSelection.copy(collectionId = collection.id))
                                        }
                                    }
                                }
                            }
                            if (store.browseEnabled) {
                                for (media in BrowseMedia.entries) {
                                    val label = when (media) { BrowseMedia.ALL -> t("All", "全部"); BrowseMedia.PHOTOS -> t("Photos", "照片"); BrowseMedia.VIDEOS -> t("Videos", "视频") }
                                    TvButton((if (selection.media == media) "✓ " else "") + label,
                                        Modifier.testTag("browse-${media.wire}").semantics { selected = selection.media == media }, !state.busy) { store.selectBrowse(selection.copy(media = media)) }
                                }
                                TvButton((if (selection.availability == Availability.READY) "✓ " else "") + t("Ready only", "仅已就绪"),
                                    Modifier.testTag("ready-only").semantics { selected = selection.availability == Availability.READY }, !state.busy) {
                                    store.selectBrowse(selection.copy(availability = if (selection.availability == Availability.READY) Availability.ALL else Availability.READY))
                                }
                                TvButton((if (selection.order == BrowseOrder.READY_FIRST) "✓ " else "") + t("Ready first", "就绪优先"),
                                    Modifier.testTag("ready-first").semantics { selected = selection.order == BrowseOrder.READY_FIRST }, !state.busy) {
                                    store.selectBrowse(selection.copy(order = if (selection.order == BrowseOrder.READY_FIRST) BrowseOrder.CATALOG else BrowseOrder.READY_FIRST))
                                }
                            }
                            if (gallery != null && gallery.page > 1) TvButton(t("Previous page", "上一页"), enabled = !state.busy) { store.loadPage(gallery.page - 1) }
                            if (gallery != null && gallery.hasMore && gallery.page < 2000) TvButton(t("Next page", "下一页"), enabled = !state.busy) { store.loadPage(gallery.page + 1) }
                            if (gallery != null && gallery.total > 50) TvButton(t("Page ${gallery.page}…", "第 ${gallery.page} 页…"), Modifier.testTag("page-jump"), !state.busy) { pages = true }
                            Box {
                                TvButton(t("More", "更多"), Modifier.testTag("gallery-more")
                                    .focusRequester(if (focusAsset == null) first else exploreFocus)) { menu = true }
                                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                                    DropdownMenuItem(text = { Text(t("Explore", "探索")) }, modifier = Modifier.testTag("explore"), onClick = { menu = false; exploring = true; discovery?.open() })
                                    DropdownMenuItem(text = { Text(t("Refresh", "刷新")) }, enabled = !state.busy, onClick = { menu = false; store.loadPage(gallery?.page ?: 1) })
                                    if (discoveryState.query != null) {
                                        DropdownMenuItem(text = { Text(t("Edit filters", "修改条件")) }, modifier = Modifier.testTag("edit-search"), onClick = { menu = false; exploring = true; discovery?.open() })
                                        DropdownMenuItem(text = { Text(t("Clear search", "清除搜索")) }, modifier = Modifier.testTag("clear-results"), onClick = { menu = false; discovery?.clearResults() })
                                    }
                                    if (previewRetry) DropdownMenuItem(text = { Text(t("Retry missing previews", "重试未加载的预览")) }, modifier = Modifier.testTag("retry-previews"), onClick = { menu = false; store.retryPreviews() })
                                    DropdownMenuItem(text = { Text(t("App updates", "应用更新")) }, modifier = Modifier.testTag("updates"), onClick = { menu = false; updates = true })
                                    DropdownMenuItem(text = { Text(if (zh) "English" else "简体中文") }, modifier = Modifier.testTag("language"), onClick = { menu = false; language = if (zh) "en" else "zh" })
                                    DropdownMenuItem(text = { Text(t("Disconnect", "断开连接")) }, modifier = Modifier.testTag("disconnect"), onClick = { menu = false; playing = false; discovery?.background(); browseStore?.disconnect() })
                                }
                            }
                        }
                        if (discoveryState.query != null) Text(t("${discoveryState.query!!.count} filters applied", "已应用 ${discoveryState.query!!.count} 类条件"), Modifier.testTag("applied-search").padding(top = 4.dp), style = MaterialTheme.typography.bodySmall, color = Muted)
                        gallery?.browseCounts?.let { counts ->
                            Text(t("${counts.ready} of ${counts.matching} available", "${counts.matching} 项中 ${counts.ready} 项已就绪"), Modifier.testTag("browse-counts"), color = Muted, style = MaterialTheme.typography.labelSmall)
                        }
                        if (gallery != null && !store.browseEnabled && gallery.version >= 2 && gallery.items.any { !it.mediaReady() }) {
                            val ready = gallery.items.count { it.mediaReady() }
                            Text(t("$ready of ${gallery.items.size} ready on this page", "本页 ${gallery.items.size} 项中有 $ready 项可观看"), Modifier.testTag("page-availability"), color = Muted, style = MaterialTheme.typography.labelSmall)
                        }
                        if (gallery != null && gallery.items.isEmpty()) {
                            val title = when {
                                discoveryState.query != null -> t("No matching memories", "没有匹配的回忆")
                                store.browseEnabled && store.selection.availability == Availability.READY -> t("Nothing is ready yet", "暂无已就绪内容")
                                else -> t("No photos here yet", "这里还没有照片")
                            }
                            val message = when {
                                discoveryState.query != null -> t("No matching memories. Try fewer filters.", "没有匹配的回忆，试试减少筛选条件。")
                                store.browseEnabled && store.selection.availability == Availability.READY -> t("Nothing ready here yet. Show all or refresh after more media is published.", "暂无已就绪内容。可显示全部，或在发布更多媒体后刷新。")
                                else -> t("Choose another filter or refresh the library.", "可更换筛选条件或刷新媒体库。")
                            }
                            Box(Modifier.fillMaxWidth().weight(1f).testTag("gallery-empty"), contentAlignment = Alignment.Center) {
                                Surface(color = Moss, shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, Edge)) {
                                    Column(Modifier.fillMaxWidth(0.78f).padding(horizontal = 28.dp, vertical = 24.dp),
                                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                        Text(title, style = MaterialTheme.typography.headlineSmall, color = Gold,
                                            modifier = Modifier.testTag("gallery-empty-title"))
                                        Text(message, style = MaterialTheme.typography.bodyMedium, color = Cream)
                                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                            if (discoveryState.query != null) {
                                                TvButton(t("Edit filters", "修改条件"), Modifier.testTag("empty-edit-search")) { exploring = true; discovery?.open() }
                                                TvButton(t("Clear search", "清除搜索"), Modifier.testTag("empty-clear-search")) { discovery?.clearResults() }
                                            } else if (store.browseEnabled && store.selection.availability == Availability.READY) {
                                                TvButton(t("Show all", "显示全部"), Modifier.testTag("empty-show-all")) {
                                                    store.selectBrowse(store.selection.copy(availability = Availability.ALL))
                                                }
                                            } else {
                                                TvButton(t("Refresh", "刷新"), Modifier.testTag("empty-refresh"), !state.busy) { store.loadPage(gallery.page) }
                                            }
                                        }
                                    }
                                }
                            }
                        } else BoxWithConstraints(Modifier.weight(1f).fillMaxWidth().testTag("grid-viewport")) {
                            val gridVerticalPadding = if (compactGallery) 4.dp else 12.dp
                            val gridItemHeight = (maxHeight - gridVerticalPadding * 2).coerceAtLeast(1.dp)
                            LazyVerticalGrid(GridCells.Adaptive(if (LocalConfiguration.current.fontScale >= 1.5f) 280.dp else 260.dp),
                                Modifier.fillMaxSize().onFocusChanged { galleryGridHasFocus = it.hasFocus }.testTag("grid"), state = grid,
                                contentPadding = PaddingValues(vertical = gridVerticalPadding), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                items(gallery?.items.orEmpty(), key = { it.id }) { asset ->
                                    val target = focusAsset?.id
                                    var focused by remember { mutableStateOf(false) }
                                    OutlinedButton({ lastAsset = asset.id; store.openAsset(asset, openPlayer = asset.kind == AssetKind.VIDEO && asset.video != null) },
                                        Modifier.fillMaxWidth().height(if (compactGallery) gridItemHeight else if (LocalConfiguration.current.fontScale >= 1.5f) 280.dp else 250.dp).then(if (asset.id == target) Modifier.focusRequester(first) else Modifier)
                                            .focusProperties { canFocus = asset.canOpen() }.onFocusChanged { focused = it.isFocused }.testTag("asset-${asset.id}"),
                                        enabled = asset.canOpen(), shape = RoundedCornerShape(14.dp), contentPadding = PaddingValues(6.dp),
                                        colors = ButtonDefaults.outlinedButtonColors(containerColor = Moss, contentColor = Cream),
                                        border = BorderStroke(if (focused) 3.dp else 1.dp, if (focused) Gold else Moss)) {
                                        Column(Modifier.fillMaxSize()) {
                                            TvImage(state.grids[asset.id], t("Photo", "照片") + " ${asset.id}", Modifier.fillMaxWidth().weight(1f), if (asset.id in state.gridProblems) t("Preview load failed · Retry", "预览加载失败 · 可重试") else if (asset.kind == AssetKind.VIDEO && asset.video != null) t("Ready to play", "可以播放") else unavailableText(asset.gridUnavailable, zh), maxPixels = 262144, loading = asset.grid != null && state.grids[asset.id] == null && asset.id !in state.missingGrids && asset.id !in state.gridProblems)
                                            if (asset.kind != AssetKind.PHOTO) Text(if (asset.kind == AssetKind.VIDEO) (if (asset.video != null) t("Video · Play", "视频 · 播放") else t("Video · Not ready", "视频 · 尚未就绪")) else t("Unsupported format", "不支持的格式"), Modifier.testTag("asset-kind-${asset.id}"), style = MaterialTheme.typography.labelSmall)
                                            Text(asset.caption.ifEmpty { t("Photo", "照片") + " ${asset.id}" }, maxLines = 2,
                                                style = if (LocalConfiguration.current.fontScale >= 1.5f) MaterialTheme.typography.bodyMedium else MaterialTheme.typography.labelLarge)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private data class LibraryFocusIntent(val collectionId: String?)

private fun problemText(problem: HomeError, zh: Boolean): String {
    fun t(en: String, cn: String) = if (zh) cn else en
    return when (problem) {
        HomeError.DENIED -> t("Home feed is disabled or unavailable to this display.", "家庭照片源已停用或此屏幕无法访问。")
        HomeError.CHANGED -> t("Photo selection changed. Reloading…", "照片选择已更改，正在重新加载…")
        HomeError.BUSY -> t("Server is busy. Waiting before retrying…", "服务器繁忙，正在等待重试…")
        HomeError.TLS -> t("Cannot verify the secure server connection.", "无法验证服务器的安全连接。")
        HomeError.INVALID -> t("The server response could not be displayed safely.", "无法安全显示服务器响应。")
        HomeError.UNAVAILABLE, HomeError.OFFLINE -> t("Connection unavailable. Retrying automatically…", "连接不可用，正在自动重试…")
    }
}

private fun unavailableText(reason: MediaUnavailable?, zh: Boolean): String {
    fun t(en: String, cn: String) = if (zh) cn else en
    return when (reason) {
        MediaUnavailable.NOT_PREPARED -> t("Not prepared yet", "尚未准备好")
        MediaUnavailable.SOURCE_MISSING -> t("Source unavailable", "源文件不可用")
        MediaUnavailable.UNSUPPORTED -> t("Unsupported format", "不支持的格式")
        MediaUnavailable.PREPARATION_FAILED -> t("Preparation failed", "准备失败")
        null -> t("Preview unavailable", "预览不可用")
    }
}

/** Catalog entries remain visible, but unavailable media never opens an empty viewer. */
private fun HomeAsset.canOpen() = display != null || original != null || kind == AssetKind.VIDEO && video != null
private fun HomeAsset.mediaReady() = if (kind == AssetKind.VIDEO) video != null else kind == AssetKind.PHOTO && (display != null || original != null)

private fun mediaProblemText(problem: HomeError, zh: Boolean): String {
    val message = when (problem) {
        HomeError.OFFLINE -> if (zh) "媒体连接中断，请重试。" else "The media connection was interrupted. Please retry."
        HomeError.BUSY -> if (zh) "服务器繁忙，请稍后重试。" else "The server is busy. Retry shortly."
        HomeError.UNAVAILABLE -> if (zh) "服务器暂时无法提供此媒体，请重试。" else "The server could not provide this media. Please retry."
        else -> if (zh) "无法读取媒体响应，请反馈此错误码。" else "The media response could not be read. Please report this code."
    }
    return "$message [TV-READ-${problem.name}]"
}
