package dev.photohouse.home

import dev.photohouse.playback.PlaybackBookmark
import dev.photohouse.playback.PlaybackProgress

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlin.random.Random

/** All operations are confined to the supplied UI scope. Bytes exist only in memory. */
data class HomeState(
    val feed: HomeFeed? = null, val grids: Map<Int, ByteArray> = emptyMap(),
    val selected: Int? = null, val display: ByteArray? = null,
    val busy: Boolean = false, val covered: Boolean = true, val disconnected: Boolean = false,
    val problem: HomeError? = null, val retryAtMillis: Long = 0,
    val missingGrids: Set<Int> = emptySet(), val displayMissing: Boolean = false,
    val originalQuality: Boolean = false,
    val mediaProblem: HomeError? = null, val gridProblems: Map<Int, HomeError> = emptyMap(),
    val video: HomeVideoSource? = null, val videoFailed: Boolean = false,
    val videoBookmark: PlaybackBookmark? = null,
    val collections: HomeCollections? = null, val collectionsProblem: HomeError? = null
) {
    val asset: HomeAsset? get() = feed?.items?.firstOrNull { it.id == selected }
    val index: Int get() = feed?.items?.indexOfFirst { it.id == selected } ?: -1
    fun adjacentVideo(delta: Int): HomeAsset? {
        val items = feed?.items ?: return null
        if (index < 0 || delta !in listOf(-1, 1)) return null
        return generateSequence(index + delta) { it + delta }.takeWhile { it in items.indices }
            .map { items[it] }.firstOrNull { it.kind == AssetKind.VIDEO && it.video != null }
    }
    fun adjacentAsset(delta: Int): HomeAsset? {
        val gallery = feed ?: return null
        if (index < 0 || delta !in listOf(-1, 1)) return null
        return generateSequence(index + delta) { it + delta }
            .takeWhile { it in gallery.items.indices }.map { gallery.items[it] }
            .firstOrNull { gallery.version < 2 || it.display != null || it.original != null || it.kind == AssetKind.VIDEO && it.video != null }
    }
}
class HomeStore(private val api: HomeApi, private val scope: CoroutineScope,
                private val now: () -> Long = { System.nanoTime() / 1_000_000 },
                private val jitter: () -> Double = { Random.nextDouble() }) {
    private val playbackProgress = PlaybackProgress()
    private val mutable = MutableStateFlow(HomeState())
    val state = mutable.asStateFlow()
    private var visible = false
    private var paused = false
    private var generation = 0L
    private var work: Job? = null
    private var timer: Job? = null
    private var failures = 0
    private var notBefore = 0L
    val browseEnabled get() = api.browseEnabled
    var selection: BrowseSelection = BrowseSelection()
        private set
    fun selectBrowse(value: BrowseSelection) {
        if (!api.browseEnabled || !visible || paused || value == selection) return
        selection = value; revision = null; loadPage(1)
    }
    private var page = 1
    private var revision: Int? = null
    private val previewMutex = Mutex()
    private var detailJob: Job? = null
    private var detailGeneration = 0L
    private var videoGeneration = 0L
    private fun current(g: Long) = visible && !paused && g == generation
    private fun invalidate() { state.value.videoBookmark?.close(); videoGeneration++; state.value.video?.close(); generation++; work?.cancel(); timer?.cancel(); detailJob?.cancel(); detailGeneration++ }
    fun foreground() {
        if (visible || paused) return
        visible = true; if (api.catalogVersion >= 2) { page = 1; revision = null }; loadPage(page)
    }
    fun background() {
        visible = false; invalidate(); mutable.value = HomeState(disconnected = paused)
    }
    fun disconnect() {
        paused = true; playbackProgress.clear(); invalidate(); mutable.value = HomeState(covered = false, disconnected = true)
    }
    fun reconnect() {
        paused = false; visible = true; if (api.catalogVersion >= 2) { page = 1; revision = null }; loadPage(page)
    }
    fun canRetry() = visible && !paused && !state.value.busy && now() >= notBefore
    fun retry() { if (canRetry()) loadPage(page) }
    fun loadPage(target: Int = page) {
        if (!visible || paused || target !in 1..2000) return
        page = target; invalidate()
        val g = generation
        mutable.value = HomeState(busy = now() >= notBefore, covered = false, collections = state.value.collections)
        work = scope.launch {
            delay((notBefore - now()).coerceAtLeast(0))
            if (!current(g)) return@launch
            mutable.value = HomeState(busy = true, covered = false, collections = state.value.collections)
            try {
                var currentCollections = state.value.collections
                var collectionProblem: HomeError? = null
                if (api.catalogVersion == 3 && api.browseEnabled) {
                    try {
                        currentCollections = api.collections()
                        if (!current(g)) return@launch
                    } catch (e: CancellationException) { throw e }
                      catch (e: HomeFailure) { collectionProblem = e.kind }
                }
                val feed = api.feed(page, if (page == 1) null else revision, selection)
                if (!current(g)) return@launch
                if (currentCollections != null && currentCollections.revision != feed.revision) throw HomeFailure(HomeError.CHANGED)
                if (selection.collectionId != null && currentCollections != null && currentCollections.collections.none { it.id == selection.collectionId }) {
                    throw HomeFailure(HomeError.INVALID)
                }
                revision = feed.revision
                mutable.value = HomeState(feed = feed, covered = false, collections = currentCollections, collectionsProblem = collectionProblem)
                scheduleRefresh(g)
                loadGrids(feed, g)
                failures = 0
            } catch (e: CancellationException) { throw e }
              catch (e: HomeFailure) { if (current(g)) failed(e) }
        }
    }
    private suspend fun readPreview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray? = previewMutex.withLock {
        var attempt = 0
        while (true) {
            try { return@withLock api.preview(asset, variant, revision) }
            catch (e: HomeFailure) {
                if (api.catalogVersion != 3 || e.kind !in listOf(HomeError.BUSY, HomeError.UNAVAILABLE) || attempt++ >= 2) throw e
                delay(maxOf(1000L, e.retryAfterMillis))
            }
        }
        @Suppress("UNREACHABLE_CODE") null
    }
    private suspend fun loadGrids(feed: HomeFeed, g: Long) {
        for (asset in feed.items) {
            if (!current(g) || state.value.selected != null) return
            if (asset.id in state.value.grids || asset.grid == null) continue
            val bytes = try { readPreview(asset, Variant.GRID, feed.revision) }
            catch (e: HomeFailure) {
                if (api.catalogVersion != 3 || e.kind !in listOf(HomeError.BUSY, HomeError.UNAVAILABLE, HomeError.OFFLINE)) throw e
                if (current(g)) mutable.value = state.value.copy(gridProblems = state.value.gridProblems + (asset.id to e.kind))
                continue
            }
            if (!current(g)) return
            val s = state.value
            // Retain a bounded page cache; a temporary failure remains explicitly retryable.
            mutable.value = if (bytes != null && s.grids.values.sumOf { it.size } + bytes.size <= GRID_CACHE_BYTES)
                s.copy(grids = s.grids + (asset.id to bytes), missingGrids = s.missingGrids - asset.id, gridProblems = s.gridProblems - asset.id)
            else s.copy(missingGrids = s.missingGrids + asset.id, gridProblems = s.gridProblems - asset.id)
        }
    }
    fun retryPreviews() {
        val feed = state.value.feed ?: return
        if (!visible || paused || state.value.selected != null) return
        work?.cancel(); val g = generation
        mutable.value = state.value.copy(gridProblems = emptyMap(), missingGrids = emptySet())
        work = scope.launch {
            try { loadGrids(feed, g) }
            catch (e: CancellationException) { throw e }
            catch (e: HomeFailure) { if (current(g)) failed(e) }
        }
    }
    private fun mediaFailed(e: HomeFailure) {
        if (api.catalogVersion < 2 || e.kind in listOf(HomeError.DENIED, HomeError.CHANGED, HomeError.TLS)) { failed(e); return }
        closeVideo()
        mutable.value = state.value.copy(busy = false, videoFailed = state.value.asset?.kind == AssetKind.VIDEO,
            displayMissing = state.value.display == null, mediaProblem = e.kind)
    }
    private fun scheduleRefresh(g: Long) {
        timer?.cancel()
        timer = scope.launch {
            delay(60000)
            if (!current(g)) return@launch
            try {
                val freshCollections = if (api.catalogVersion == 3 && api.browseEnabled) api.collections() else state.value.collections
                if (!current(g)) return@launch
                val fresh = api.feed(page, revision, selection)
                if (!current(g)) return@launch
                if (freshCollections != null && freshCollections.revision != fresh.revision) throw HomeFailure(HomeError.CHANGED)
                val old = state.value.feed
                if (fresh != old || freshCollections != state.value.collections) {
                    if (api.catalogVersion >= 2) { page = 1; revision = null }
                    loadPage(page); return@launch
                }
                scheduleRefresh(g)
            } catch (e: CancellationException) { throw e }
              catch (e: HomeFailure) { if (current(g)) failed(e) }
        }
    }
    private fun failed(e: HomeFailure) {
        if (e.kind in listOf(HomeError.DENIED, HomeError.CHANGED, HomeError.TLS)) playbackProgress.clear()
        invalidate()
        if (api.catalogVersion >= 2) { page = 1; revision = null }
        val retryable = e.kind in setOf(HomeError.OFFLINE, HomeError.UNAVAILABLE, HomeError.BUSY) || e.kind == HomeError.CHANGED && api.retryRevisionChanges
        val delays = longArrayOf(2000, 5000, 15000, 30000, 60000)
        val base = delays[failures.coerceAtMost(4)]
        val wait = (base + (base * .2 * jitter().coerceIn(0.0, 1.0)).toLong()).coerceAtMost(60000)
        failures++
        val floor = e.retryAfterMillis.coerceAtMost(Long.MAX_VALUE - now())
        if (e.kind == HomeError.BUSY) notBefore = maxOf(notBefore, now() + floor)
        val retryAt = maxOf(now() + wait, notBefore)
        mutable.value = HomeState(covered = false, problem = e.kind, retryAtMillis = retryAt)
        if (retryable) {
            val g = generation
            timer = scope.launch {
                delay((retryAt - now()).coerceAtLeast(0))
                if (current(g)) loadPage(page)
            }
        }
    }
    internal fun failDiscovery(e: HomeFailure) { failed(e) }
    fun openAsset(asset: HomeAsset, openPlayer: Boolean = false) {
        val s = state.value; val feed = s.feed ?: return
        if (!visible || paused || s.covered || asset !in feed.items) return
        state.value.videoBookmark?.close(); videoGeneration++; state.value.video?.close()
        detailJob?.cancel(); val d = ++detailGeneration; val g = generation
        mutable.value = s.copy(selected = asset.id, display = null, busy = true, displayMissing = false, originalQuality = false, video = null, videoFailed = false, mediaProblem = null)
        detailJob = scope.launch {
            try {
                val bytes = if (asset.display == null) null else readPreview(asset, Variant.DISPLAY, feed.revision)
                if (current(g) && d == detailGeneration) {
                    mutable.value = state.value.copy(display = bytes, busy = false, displayMissing = bytes == null)
                    if (openPlayer && asset.kind == AssetKind.VIDEO && asset.video != null) openVideo()
                }
            } catch (e: CancellationException) { throw e }
              catch (e: HomeFailure) { if (current(g) && d == detailGeneration) {
                  mediaFailed(e)
                  if (openPlayer && state.value.asset?.id == asset.id && e.kind !in listOf(HomeError.DENIED, HomeError.CHANGED, HomeError.TLS)) openVideo()
              } }
        }
    }
    fun openOriginal() {
        val s = state.value; val asset = s.asset ?: return; val feed = s.feed ?: return
        if (!visible || paused || s.covered || s.busy || asset.original == null) return
        detailJob?.cancel(); val d = ++detailGeneration; val g = generation
        mutable.value = s.copy(busy = true, mediaProblem = null)
        detailJob = scope.launch {
            try {
                val bytes = api.original(asset, feed.revision)
                if (current(g) && d == detailGeneration) mutable.value = state.value.copy(display = bytes, busy = false, displayMissing = false, originalQuality = true)
            } catch (e: CancellationException) { throw e }
              catch (e: HomeFailure) { if (current(g) && d == detailGeneration) mediaFailed(e) }
        }
    }
    fun openVideo() {
        val s = state.value; val asset = s.asset ?: return; val feed = s.feed ?: return
        if (!visible || paused || s.covered || s.busy || asset.video == null || asset.kind != AssetKind.VIDEO) return
        s.videoBookmark?.close()
        s.video?.close()
        val g = generation; val d = detailGeneration; val v = ++videoGeneration
        try {
            val source = api.video(asset, feed.revision) { error -> scope.launch {
                if (current(g) && d == detailGeneration && v == videoGeneration) {
                    if (error is HomeFailure) mediaFailed(error) else videoPlaybackFailed()
                }
            } }
            mutable.value = s.copy(video = source, videoFailed = false, mediaProblem = null,
                videoBookmark = playbackProgress.open("${feed.id}:${feed.revision}:${asset.id}:${asset.video.sha256}"))
        } catch (e: HomeFailure) { mediaFailed(e) }
    }
    fun closeVideo() {
        state.value.videoBookmark?.close()
        videoGeneration++
        state.value.video?.close()
        mutable.value = state.value.copy(video = null, videoBookmark = null)
    }
    fun videoPlaybackFailed() {
        closeVideo(); mutable.value = state.value.copy(videoFailed = true)
    }
    fun adjacentVideo(delta: Int) {
        if (state.value.busy || state.value.video == null) return
        state.value.adjacentVideo(delta)?.let { openAsset(it, openPlayer = true) }
    }
    fun adjacentPhoto(delta: Int) {
        val s = state.value
        if (s.busy) return
        s.adjacentAsset(delta)?.let { openAsset(it) }
    }
    fun backToPhotos() {
        state.value.videoBookmark?.close(); videoGeneration++; state.value.video?.close()
        detailJob?.cancel(); detailGeneration++
        mutable.value = state.value.copy(selected = null, display = null, busy = false, displayMissing = false, originalQuality = false, video = null, videoFailed = false, mediaProblem = null)
        retryPreviews()
    }
    companion object { const val GRID_CACHE_BYTES = 16 * 1024 * 1024 }
}
