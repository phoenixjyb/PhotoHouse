package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit

enum class MemoryGroupsStorePhase {
    IDLE, LOADING, READY, EDITING, REVIEW, SAVING, UNCERTAIN, CONFLICT, SAVED, DENIED, CLOSED
}

data class MemoryGroupsStoreState(
    val phase: MemoryGroupsStorePhase = MemoryGroupsStorePhase.IDLE,
    val capabilities: MemoryGroupsCapabilities? = null,
    val page: MemoryGroupPage? = null,
    val availableAssets: List<Asset> = emptyList(),
    val availableSources: List<ProtectedStory> = emptyList(),
    val selectedAssetIds: List<String> = emptyList(),
    val excludedAssetIds: List<String> = emptyList(),
    val sourceStoryIds: List<String> = emptyList(),
    val theme: String = "everyday",
    val proposals: MemoryGroupProposals? = null,
    val suggestionBusy: Boolean = false,
    val previews: Map<String, ByteArray> = emptyMap(),
    val hasUnsavedChanges: Boolean = false,
    val canUseReloadedRevision: Boolean = false,
    val message: String? = null,
    val retryAtMillis: Long = 0,
    val mutation: MemoryGroupMutation? = null,
    val saved: MemoryGroup? = null,
)

/** UI-dispatcher-confined protected group editor. It never persists drafts. */
class MemoryGroupsStore(
    private val api: MemoryGroupsApi,
    private val scope: CoroutineScope,
    private val token: Bearer,
    private val library: String,
    private val anchor: Asset,
    gallery: List<Asset>,
    stories: List<ProtectedStory>,
    private val valid: () -> Boolean,
    private val onDenied: () -> Unit,
    private val now: () -> Long = System::currentTimeMillis,
    private val preview: suspend (Asset) -> ByteArray? = { null },
) {
    private var initialGallery = gallery.toList()
    private var initialStories = stories.toList()
    private val mutable = MutableStateFlow(MemoryGroupsStoreState(
        availableAssets = mergeAssets(listOf(anchor) + initialGallery),
        availableSources = mergeSources(initialStories),
    ))
    val state = mutable.asStateFlow()

    private val fixedSeedIds = listOf(anchor.id).takeIf { anchor.kind == "image" }.orEmpty()
    private var job: Job? = null
    private val previewJobs = mutableMapOf<String, Job>()
    private val previewCache = LinkedHashMap<String, ByteArray>()
    private val previewSemaphore = Semaphore(MAX_PREVIEW_JOBS)
    private var generation = 0L
    private var previewGeneration = 0L
    private var closed = false
    private var editingGroup: MemoryGroup? = null
    private var reloadedGroup: MemoryGroup? = null
    val suggestionsAvailable get() = state.value.capabilities?.suggestions == true && fixedSeedIds.isNotEmpty() &&
        anchor.id in state.value.selectedAssetIds && anchor.id !in state.value.excludedAssetIds

    /** Explicitly fetch capabilities and complete groups for the anchor. */
    fun load(): Boolean {
        if (!usable() || state.value.phase !in setOf(MemoryGroupsStorePhase.IDLE, MemoryGroupsStorePhase.READY, MemoryGroupsStorePhase.SAVED)) return false
        if (!api.memoryGroupsEnabled || now() < state.value.retryAtMillis) return false
        val request = nextRequest()
        mutable.value = state.value.copy(phase = MemoryGroupsStorePhase.LOADING, message = null, retryAtMillis = 0)
        job = scope.launch {
            try {
                val capabilities = api.capabilities(token, library)
                if (!current(request)) return@launch
                validateCapabilities(capabilities)
                val page = if (capabilities.enabled) api.list(token, library, anchor.id) else null
                if (!current(request)) return@launch
                val loaded = page?.items.orEmpty()
                page?.let(::validatePage)
                val assets = mergeAssets(listOf(anchor) + initialGallery + loaded.flatMap { it.items })
                val sources = mergeSources(initialStories, loaded.flatMap { it.sources })
                mutable.value = state.value.copy(
                    phase = MemoryGroupsStorePhase.READY, capabilities = capabilities, page = page,
                    availableAssets = assets, availableSources = sources, message = null,
                )
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { if (current(request)) handleFailure(e, MemoryGroupsStorePhase.READY) }
        }
        return true
    }

    fun startCreate(): Boolean {
        if (!usable() || state.value.phase !in setOf(MemoryGroupsStorePhase.READY, MemoryGroupsStorePhase.SAVED)) return false
        if (state.value.capabilities?.let { it.enabled && it.manual } != true || !api.memoryGroupsEnabled) return false
        editingGroup = null; reloadedGroup = null
        val selected = listOf(anchor.id)
        mutable.value = state.value.copy(
            phase = MemoryGroupsStorePhase.EDITING, selectedAssetIds = selected,
            excludedAssetIds = emptyList(), sourceStoryIds = emptyList(), theme = "everyday",
            proposals = null, suggestionBusy = false, mutation = null, saved = null,
            hasUnsavedChanges = true, message = null, retryAtMillis = 0, canUseReloadedRevision = false,
        )
        return true
    }

    /** Starts an edit only from a clean loaded/saved state and for a current editable group. */
    fun startEdit(group: MemoryGroup): Boolean {
        if (!usable() || state.value.phase !in setOf(MemoryGroupsStorePhase.READY, MemoryGroupsStorePhase.SAVED)) return false
        if (state.value.capabilities?.let { it.enabled && it.manual } != true || !api.memoryGroupsEnabled) return false
        if (group.libraryId != library || !group.canEdit) return false
        val currentGroup = state.value.saved?.takeIf { it.id == group.id }
            ?: state.value.page?.items?.firstOrNull { it.id == group.id && anchor.id in it.assetIds }
            ?: return false
        if (currentGroup.revision != group.revision || currentGroup.libraryId != library || !currentGroup.canEdit) return false
        editingGroup = currentGroup; reloadedGroup = null
        val sources = mergeSources(state.value.availableSources, currentGroup.sources)
        mutable.value = state.value.copy(
            phase = MemoryGroupsStorePhase.EDITING,
            availableAssets = mergeAssets(state.value.availableAssets + currentGroup.items),
            availableSources = sources, selectedAssetIds = currentGroup.assetIds.toList(),
            excludedAssetIds = currentGroup.excludedAssetIds.toList(), sourceStoryIds = currentGroup.sourceStoryIds.toList(),
            theme = currentGroup.theme, proposals = null, suggestionBusy = false, mutation = null, saved = null,
            hasUnsavedChanges = false, message = null, retryAtMillis = 0, canUseReloadedRevision = false,
        )
        return true
    }

    fun addAsset(assetId: String): Boolean {
        if (!editable()) return false
        val current = state.value
        if (assetId !in current.availableAssets.map { it.id } || assetId in current.selectedAssetIds || current.selectedAssetIds.size >= maxMembers()) return false
        changed(current.copy(
            selectedAssetIds = current.selectedAssetIds + assetId,
            excludedAssetIds = current.excludedAssetIds.filterNot { it == assetId },
        ))
        return true
    }

    fun removeAsset(assetId: String): Boolean {
        if (!editable()) return false
        val current = state.value
        if (assetId !in current.selectedAssetIds || current.selectedAssetIds.size <= 1) return false
        val exclusions = if (assetId in (current.proposals?.items.orEmpty().map { it.asset.id }) || editingGroup != null) {
            (current.excludedAssetIds + assetId).distinct()
        } else current.excludedAssetIds
        if (exclusions.size > 512) return false
        changed(current.copy(
            selectedAssetIds = current.selectedAssetIds.filterNot { it == assetId },
            sourceStoryIds = current.sourceStoryIds.filterNot { id -> current.availableSources.firstOrNull { it.id == id }?.assetId == assetId },
            excludedAssetIds = exclusions,
            proposals = if (assetId == anchor.id) null else current.proposals,
        ))
        return true
    }

    fun setTheme(value: String): Boolean {
        if (!editable() || value !in THEMES) return false
        if (state.value.theme != value) changed(state.value.copy(theme = value))
        return true
    }

    fun selectSourceStory(id: String, selected: Boolean): Boolean {
        if (!editable()) return false
        val current = state.value
        val source = current.availableSources.firstOrNull { it.id == id } ?: return false
        if (source.assetId !in current.selectedAssetIds) return false
        val ids = if (selected) (current.sourceStoryIds + id).distinct() else current.sourceStoryIds.filterNot { it == id }
        if (ids.size > 12) return false
        if (ids != current.sourceStoryIds) changed(current.copy(sourceStoryIds = ids))
        return true
    }

    /** Suggestions always use the constructor's original explicit image anchor. */
    fun refreshSuggestions(): Boolean {
        if (!usable() || state.value.phase != MemoryGroupsStorePhase.EDITING || state.value.suggestionBusy) return false
        if (state.value.capabilities?.let { it.enabled && it.suggestions } != true || fixedSeedIds.isEmpty() || anchor.id !in state.value.selectedAssetIds || anchor.id in state.value.excludedAssetIds || now() < state.value.retryAtMillis) return false
        val request = nextRequest()
        val excluded = state.value.excludedAssetIds.toList()
        mutable.value = state.value.copy(suggestionBusy = true, message = null)
        job = scope.launch {
            try {
                val result = api.proposals(token, library, fixedSeedIds, excluded)
                if (!current(request) || state.value.phase != MemoryGroupsStorePhase.EDITING) return@launch
                validateProposals(result, fixedSeedIds, excluded)
                val assets = mergeAssets(state.value.availableAssets + result.items.map { it.asset })
                mutable.value = state.value.copy(availableAssets = assets, proposals = result, suggestionBusy = false, message = null)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { if (current(request)) handleFailure(e, MemoryGroupsStorePhase.EDITING) }
        }
        return true
    }

    fun selectSuggestion(assetId: String, selected: Boolean): Boolean {
        if (!editable()) return false
        val candidate = state.value.proposals?.items?.firstOrNull { it.asset.id == assetId } ?: return false
        return if (selected) addAsset(candidate.asset.id) else {
            if (candidate.asset.id !in state.value.selectedAssetIds) {
                addExclusion(candidate.asset.id)
            } else removeAsset(candidate.asset.id)
        }
    }

    fun beginReview(): Boolean {
        if (!editable()) return false
        val current = state.value
        if (current.selectedAssetIds.isEmpty() || current.selectedAssetIds.size > maxMembers()) return false
        if (current.sourceStoryIds.size > 12 || current.excludedAssetIds.size > 512) return false
        val mutation = MemoryGroupMutation(
            groupId = editingGroup?.id, revision = editingGroup?.revision ?: 0,
            theme = current.theme, assetIds = current.selectedAssetIds.toList(),
            excludedAssetIds = current.excludedAssetIds.toList(), sourceStoryIds = current.sourceStoryIds.toList(),
        )
        nextRequest()
        mutable.value = current.copy(phase = MemoryGroupsStorePhase.REVIEW, mutation = mutation, suggestionBusy = false, message = null, retryAtMillis = 0)
        return true
    }

    fun backToEdit(): Boolean {
        if (!usable() || state.value.phase != MemoryGroupsStorePhase.REVIEW) return false
        mutable.value = state.value.copy(phase = MemoryGroupsStorePhase.EDITING, mutation = null, message = null)
        return true
    }

    fun confirmSave(): Boolean {
        if (!usable() || state.value.phase != MemoryGroupsStorePhase.REVIEW) return false
        val mutation = state.value.mutation ?: return false
        val request = nextRequest()
        mutable.value = state.value.copy(phase = MemoryGroupsStorePhase.SAVING, message = null)
        job = scope.launch {
            try {
                val result = api.save(token, library, mutation)
                if (!current(request)) return@launch
                validateSaved(result, mutation)
                editingGroup = result
                mutable.value = savedState(result)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!current(request)) return@launch
                handleSaveFailure(e)
            }
        }
        return true
    }

    /** Replays the exact frozen mutation, including mutation ID and body. */
    fun retryUncertain(): Boolean {
        if (!usable() || state.value.phase != MemoryGroupsStorePhase.UNCERTAIN || now() < state.value.retryAtMillis) return false
        val mutation = state.value.mutation ?: return false
        val request = nextRequest()
        mutable.value = state.value.copy(phase = MemoryGroupsStorePhase.SAVING, message = null)
        job = scope.launch {
            try {
                val result = api.save(token, library, mutation)
                if (!current(request)) return@launch
                validateSaved(result, mutation)
                editingGroup = result
                mutable.value = savedState(result)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!current(request)) return@launch
                handleSaveFailure(e)
            }
        }
        return true
    }

    /** Reloads the conflicted group from the protected anchor listing; draft fields remain intact. */
    fun reloadConflict(): Boolean {
        if (!usable() || state.value.phase != MemoryGroupsStorePhase.CONFLICT || now() < state.value.retryAtMillis) return false
        val requestedId = state.value.mutation?.groupId ?: return false
        val request = nextRequest()
        mutable.value = state.value.copy(message = "Reloading current group…", canUseReloadedRevision = false)
        job = scope.launch {
            try {
                val refreshedPage = api.list(token, library, anchor.id)
                validatePage(refreshedPage)
                val latest = refreshedPage.items.firstOrNull { it.id == requestedId && it.libraryId == library && it.canEdit }
                if (!current(request)) return@launch
                reloadedGroup = latest
                val refreshedItems = refreshedPage.items.toMutableList().also { rows ->
                    val index = rows.indexOfFirst { it.id == requestedId }
                    if (index >= 0 && latest != null) rows[index] = latest
                    else if (index >= 0) rows.removeAt(index)
                }
                val page = refreshedPage.copy(items = refreshedItems)
                mutable.value = if (latest == null) state.value.copy(
                    page = page,
                    availableAssets = mergeAssets(listOf(anchor) + initialGallery + page.items.flatMap { it.items }),
                    availableSources = mergeSources(initialStories, page.items.flatMap { it.sources }),
                    message = "The current group is unavailable. Discard this draft to close.",
                ) else state.value.copy(
                    page = page,
                    availableAssets = mergeAssets(listOf(anchor) + initialGallery + page.items.flatMap { it.items }),
                    availableSources = mergeSources(initialStories, page.items.flatMap { it.sources }),
                    canUseReloadedRevision = true, message = "Current revision loaded. Confirm to use it with your draft.",
                )
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { if (current(request)) handleFailure(e, MemoryGroupsStorePhase.CONFLICT) }
        }
        return true
    }

    /** Explicitly adopts the latest revision, retaining the local draft but issuing a fresh mutation ID. */
    fun useReloadedRevision(): Boolean {
        if (!usable() || state.value.phase != MemoryGroupsStorePhase.CONFLICT || !state.value.canUseReloadedRevision) return false
        val latest = reloadedGroup ?: return false
        if (latest.id != editingGroup?.id || latest.libraryId != library || !latest.canEdit) return false
        editingGroup = latest
        reloadedGroup = null
        mutable.value = state.value.copy(phase = MemoryGroupsStorePhase.EDITING, mutation = null, canUseReloadedRevision = false, hasUnsavedChanges = true, message = null)
        return true
    }

    fun discardConflict(): Boolean {
        if (!usable() || state.value.phase != MemoryGroupsStorePhase.CONFLICT) return false
        val loaded = state.value.page
        val caps = state.value.capabilities
        editingGroup = null; reloadedGroup = null
        mutable.value = MemoryGroupsStoreState(
            phase = MemoryGroupsStorePhase.READY, capabilities = caps, page = loaded,
            availableAssets = mergeAssets(listOf(anchor) + initialGallery + loaded?.items.orEmpty().flatMap { it.items }),
            availableSources = mergeSources(initialStories, loaded?.items.orEmpty().flatMap { it.sources }),
        )
        return true
    }

    fun canClose(): Boolean = state.value.phase !in setOf(
        MemoryGroupsStorePhase.EDITING, MemoryGroupsStorePhase.REVIEW, MemoryGroupsStorePhase.SAVING,
        MemoryGroupsStorePhase.UNCERTAIN, MemoryGroupsStorePhase.CONFLICT,
    ) || (state.value.phase == MemoryGroupsStorePhase.EDITING && !state.value.hasUnsavedChanges)

    /** Explicit user discard; saving cannot be interrupted. */
    fun discardDraft(): Boolean {
        if (closed || state.value.phase == MemoryGroupsStorePhase.SAVING) return false
        close()
        return true
    }

    fun close() {
        if (closed) return
        closed = true; generation++; previewGeneration++
        job?.cancel(); job = null
        previewJobs.values.forEach { it.cancel() }; previewJobs.clear(); wipePreviewCache()
        editingGroup = null; reloadedGroup = null
        initialGallery = emptyList(); initialStories = emptyList()
        mutable.value = MemoryGroupsStoreState(phase = MemoryGroupsStorePhase.CLOSED)
    }

    private fun addExclusion(id: String): Boolean {
        val current = state.value
        if (id in current.excludedAssetIds) return true
        if (current.excludedAssetIds.size >= 512) return false
        changed(current.copy(excludedAssetIds = current.excludedAssetIds + id))
        return true
    }

    private fun editable() = usable() && state.value.phase == MemoryGroupsStorePhase.EDITING

    private fun changed(next: MemoryGroupsStoreState) {
        generation++
        job?.cancel(); job = null
        mutable.value = next.copy(
            proposals = next.proposals, suggestionBusy = false, hasUnsavedChanges = true,
            message = null, mutation = null,
        )
    }

    private fun maxMembers() = state.value.capabilities?.maxMembers?.coerceIn(1, 24) ?: 24

    private fun usable(): Boolean {
        if (closed) return false
        val scopeValid = try { valid() } catch (_: Exception) { false }
        if (!scopeValid) { close(); return false }
        return true
    }

    private fun nextRequest(): Long {
        generation++
        job?.cancel(); job = null
        return generation
    }

    private fun current(request: Long): Boolean {
        if (closed || request != generation) return false
        return usable()
    }

    private fun handleFailure(error: Exception, fallback: MemoryGroupsStorePhase) {
        if (error is ApiFailure && (error.status == 401 || error.status == 403)) { deny(); return }
        mutable.value = state.value.copy(phase = fallback, suggestionBusy = false, message = "Could not load memory groups.", retryAtMillis = retryAt(error))
    }

    private fun deny() {
        if (closed) return
        generation++; previewGeneration++; job?.cancel(); job = null
        previewJobs.values.forEach { it.cancel() }; previewJobs.clear(); wipePreviewCache()
        editingGroup = null; reloadedGroup = null
        initialGallery = emptyList(); initialStories = emptyList()
        mutable.value = MemoryGroupsStoreState(phase = MemoryGroupsStorePhase.DENIED, message = "Access is no longer available.")
        onDenied()
    }

    private fun handleSaveFailure(error: Exception) {
        when {
            error is ApiFailure && (error.status == 401 || error.status == 403) -> deny()
            error is ApiFailure && error.status == 409 -> {
                reloadedGroup = null
                mutable.value = state.value.copy(phase = MemoryGroupsStorePhase.CONFLICT, canUseReloadedRevision = false, message = "This group changed. Reload it or discard your draft.")
            }
            isDefinitiveSaveFailure(error) -> mutable.value = state.value.copy(phase = MemoryGroupsStorePhase.EDITING, mutation = null, hasUnsavedChanges = true, message = "Could not save this group.")
            else -> mutable.value = state.value.copy(phase = MemoryGroupsStorePhase.UNCERTAIN, message = "Save status is unknown. Retry the same save or discard.", retryAtMillis = retryAt(error))
        }
    }

    private fun savedState(group: MemoryGroup) = state.value.copy(
        phase = MemoryGroupsStorePhase.SAVED, saved = group, mutation = null, message = null,
        retryAtMillis = 0, hasUnsavedChanges = false,
        availableAssets = mergeAssets(state.value.availableAssets + group.items),
        availableSources = mergeSources(initialStories, group.sources),
        selectedAssetIds = group.assetIds.toList(), excludedAssetIds = group.excludedAssetIds.toList(),
        sourceStoryIds = group.sourceStoryIds.toList(), theme = group.theme,
    )

    private fun isDefinitiveSaveFailure(error: Exception): Boolean = when {
        error is ApiFailure && error.kind == FailureKind.INVALID_INPUT -> true
        error is ApiFailure && error.kind == FailureKind.HTTP && error.status in 400..499 && error.status !in setOf(408, 429) -> true
        else -> false
    }

    private fun retryAt(error: Exception): Long {
        val delay = (error as? ApiFailure)?.retryAfterMillis?.coerceAtLeast(0) ?: 0
        val at = now()
        return if (delay > Long.MAX_VALUE - at) Long.MAX_VALUE else at + delay
    }

    private fun mergeAssets(values: List<Asset>): List<Asset> = values.distinctBy { it.id }

    private fun mergeSources(vararg values: List<ProtectedStory>): List<ProtectedStory> {
        val byId = linkedMapOf<String, ProtectedStory>()
        values.asList().flatten().forEach { source ->
            val existing = byId[source.id]
            if (existing == null || source.revision >= existing.revision) byId[source.id] = source
        }
        return byId.values.toList()
    }

    private fun validateCapabilities(value: MemoryGroupsCapabilities) {
        requireResponse(value.maxMembers == 24 && (!value.manual || value.enabled) && (!value.suggestions || value.enabled) && value.needsReview)
    }

    private fun validatePage(value: MemoryGroupPage) {
        requireResponse(value.libraryId == library && value.assetId == anchor.id && value.items.size <= 8)
        requireResponse(value.items.map { it.id }.distinct().size == value.items.size)
        value.items.forEach { group ->
            requireResponse(group.libraryId == library && anchor.id in group.assetIds && group.assetIds.size in 1..24)
            requireResponse(group.assetIds.distinct().size == group.assetIds.size && group.excludedAssetIds.size <= 512)
            requireResponse(group.excludedAssetIds.distinct().size == group.excludedAssetIds.size && group.assetIds.toSet().intersect(group.excludedAssetIds.toSet()).isEmpty())
            requireResponse(group.sourceStoryIds.size <= 12 && group.sourceStoryIds.distinct().size == group.sourceStoryIds.size)
            requireResponse(group.items.map { it.id } == group.assetIds)
            requireResponse(group.sources.map { it.id } == group.sourceStoryIds && group.sources.all { it.assetId in group.assetIds })
        }
    }

    private fun validateProposals(value: MemoryGroupProposals, seeds: List<String>, excluded: List<String>) {
        requireResponse(value.libraryId == library && value.seedAssetIds == seeds && value.needsReview)
        requireResponse(value.items.size <= 20 && value.items.map { it.asset.id }.distinct().size == value.items.size)
        requireResponse(value.items.all { it.matchedSeedAssetId in seeds && it.asset.id !in seeds && it.asset.id !in excluded })
        requireResponse(value.status == MemoryGroupProposalStatus.READY || value.items.isEmpty())
    }

    private fun validateSaved(value: MemoryGroup, mutation: MemoryGroupMutation) {
        requireResponse(value.libraryId == library && isCanonicalUuid(value.id))
        requireResponse(mutation.revision < Long.MAX_VALUE && value.revision > mutation.revision)
        requireResponse(mutation.groupId == null || value.id == mutation.groupId)
        requireResponse(value.theme in THEMES && value.assetIds.size in 1..24 && value.assetIds.distinct().size == value.assetIds.size)
        requireResponse(value.assetIds.all(::isAssetId) && value.excludedAssetIds.size <= 512)
        requireResponse(value.excludedAssetIds.distinct().size == value.excludedAssetIds.size && value.excludedAssetIds.all(::isAssetId))
        requireResponse(value.assetIds.toSet().intersect(value.excludedAssetIds.toSet()).isEmpty())
        requireResponse(value.sourceStoryIds.size <= 12 && value.sourceStoryIds.distinct().size == value.sourceStoryIds.size)
        requireResponse(value.sourceStoryIds.all(::isCanonicalUuid) && value.items.size == value.assetIds.size)
        requireResponse(value.items.map { it.id } == value.assetIds)
        requireResponse(value.sources.map { it.id } == value.sourceStoryIds && value.sources.all { it.assetId in value.assetIds })
    }

    private fun requireResponse(valid: Boolean) {
        if (!valid) throw ApiFailure(FailureKind.INVALID_RESPONSE)
    }

    private fun isCanonicalUuid(value: String): Boolean =
        runCatching { java.util.UUID.fromString(value).toString() == value }.getOrDefault(false)

    private fun isAssetId(value: String): Boolean =
        value.matches(Regex("[1-9][0-9]{0,18}")) && value.toLongOrNull() != null

    /** Load a thumbnail only when its asset is currently exposed by this store. */
    fun loadPreview(assetId: String): Boolean {
        if (!usable() || assetId !in state.value.availableAssets.map { it.id } || assetId in previewJobs || assetId in previewCache) return false
        if (previewJobs.size >= MAX_PREVIEWS) return false
        val asset = state.value.availableAssets.firstOrNull { it.id == assetId } ?: return false
        val request = previewGeneration
        val task = scope.launch(start = CoroutineStart.LAZY) {
            var bytes: ByteArray? = null
            try {
                bytes = previewSemaphore.withPermit { preview(asset) }
                if (bytes == null) return@launch
                if (bytes.size !in 1..MAX_PREVIEW_BYTES || !usable() || request != previewGeneration) {
                    return@launch
                }
                while (previewCache.size >= MAX_PREVIEWS) {
                    val eldest = previewCache.keys.firstOrNull() ?: break
                    previewCache.remove(eldest)?.fill(0)
                }
                previewCache[assetId] = bytes
                mutable.value = state.value.copy(previews = previewCache.toMap())
                bytes = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (e is ApiFailure && (e.status == 401 || e.status == 403)) deny()
            } finally {
                bytes?.fill(0)
                previewJobs.remove(assetId)
            }
        }
        previewJobs[assetId] = task
        task.start()
        return true
    }

    private fun wipePreviewCache() {
        previewCache.values.forEach { it.fill(0) }
        previewCache.clear()
        state.value.previews.values.forEach { it.fill(0) }
    }

    companion object {
        val THEMES = setOf("trip", "growing_up", "birthday", "grandparents", "year_in_review", "everyday")
        const val MAX_PREVIEWS = 44
        const val MAX_PREVIEW_JOBS = 2
        const val MAX_PREVIEW_BYTES = 2 * 1024 * 1024
    }
}
