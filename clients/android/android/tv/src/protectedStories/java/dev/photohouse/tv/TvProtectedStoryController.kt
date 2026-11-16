package dev.photohouse.tv

import androidx.compose.runtime.Composable
import dev.photohouse.connected.core.ApiFailure
import dev.photohouse.connected.core.Bearer
import dev.photohouse.connected.core.FailureKind
import dev.photohouse.connected.core.HttpsPhotoHouseApi
import dev.photohouse.connected.core.MemoryCommunityBinding
import dev.photohouse.connected.core.PhotoHouseApi
import dev.photohouse.connected.core.SavedMemoryStory
import dev.photohouse.connected.core.SavedMemoryStoryContributionReferences
import dev.photohouse.connected.core.SavedMemoryStorySummary
import dev.photohouse.connected.core.StoryWorkspaceApi
import dev.photohouse.connected.core.StoryWorkspaceRepository
import dev.photohouse.connected.core.StoryWorkspaceStore
import dev.photohouse.connected.core.StoryWorkspaceStoreStatus
import dev.photohouse.connected.core.TrustedOrigin
import dev.photohouse.connected.core.savedStoryRefinementDraft
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

fun createTvProtectedStories(scope: CoroutineScope): TvProtectedStories? {
    val origin = runCatching { TrustedOrigin.parse(BuildConfig.PHOTOHOUSE_TV_STORY_ORIGIN) }.getOrNull() ?: return null
    val api = HttpsPhotoHouseApi(origin, protectedNativeV2Enabled = true)
    val controller = ProtectedTvStoryController(api, api, scope)
    return object : TvProtectedStories {
        @Composable
        override fun Content(zh: Boolean, onClose: () -> Unit) = TvProtectedStoryContent(controller, zh, onClose)
        override fun background() = controller.dispatch(TvStoryApprovalAction.Cancel)
    }
}

/** Only the opt-in TV workspace holds this process-memory account scope. */
internal class ProtectedTvStoryController(
    private val api: PhotoHouseApi,
    private val workspaceApi: StoryWorkspaceApi,
    private val scope: CoroutineScope,
) : TvStoryApprovalController {
    private data class Review(
        val story: SavedMemoryStory,
        val references: SavedMemoryStoryContributionReferences?,
    ) {
        val proposal = references?.let { savedStoryRefinementDraft(story, it) }
    }

    private val mutable = MutableStateFlow(TvStoryApprovalUiState())
    override val state = mutable.asStateFlow()
    private var credential: Bearer? = null
    private var accountId: String? = null
    private var libraryId: String? = null
    private var ticket = 0L
    private var request: Job? = null
    private var stories = emptyList<SavedMemoryStorySummary>()
    private var review: Review? = null
    private var editor: StoryWorkspaceStore? = null
    private var editorObserver: Job? = null

    override fun dispatch(action: TvStoryApprovalAction) {
        when (action) {
            TvStoryApprovalAction.Cancel, TvStoryApprovalAction.SignOut -> reset()
            else -> {
                if (state.value.busy) return
                when (action) {
                    is TvStoryApprovalAction.SignIn -> signIn(action.phone, action.password)
                    is TvStoryApprovalAction.ChooseLibrary -> chooseLibrary(action.id)
                    is TvStoryApprovalAction.LoadStories -> loadStories(action.page)
                    is TvStoryApprovalAction.OpenStory -> openStory(action.id)
                    TvStoryApprovalAction.RefreshCurrent -> refresh()
                    TvStoryApprovalAction.StartCurrent -> start()
                    TvStoryApprovalAction.ApplyProposal -> apply()
                    TvStoryApprovalAction.Save -> save(retry = false)
                    TvStoryApprovalAction.RetrySave -> save(retry = true)
                    TvStoryApprovalAction.DiscardApplied -> discard()
                    else -> Unit
                }
            }
        }
    }

    private fun signIn(phone: String, password: String) {
        if (state.value.stage != TvStoryApprovalStage.SIGN_IN || credential != null) return
        request(TvStoryApprovalIssue.SIGN_IN_FAILED) { expected ->
            val token = Bearer.from(api.login(phone, password))
            try {
                if (ticket != expected) return@request
                val session = api.session(token)
                if (ticket != expected) return@request
                val libraries = session.memberships.filter { it.status == "active" && it.available }
                    .map { TvStoryApprovalLibrary(it.library_id, it.library_id) }
                if (libraries.isEmpty()) throw ApiFailure(FailureKind.HTTP, 403)
                accountId = session.account_id
                credential = token
                mutable.value = TvStoryApprovalUiState(stage = TvStoryApprovalStage.LIBRARIES, libraries = libraries)
            } finally {
                if (credential !== token) revoke(token)
            }
        }
    }

    private fun chooseLibrary(id: String) {
        val shown = state.value
        if (shown.stage != TvStoryApprovalStage.LIBRARIES || shown.libraries.none { it.id == id }) return
        libraryId = id
        loadStories(1)
    }

    private fun loadStories(page: Int) {
        val shown = state.value
        if (shown.stage !in setOf(TvStoryApprovalStage.LIBRARIES, TvStoryApprovalStage.STORIES,
                TvStoryApprovalStage.REVIEW, TvStoryApprovalStage.SAVED, TvStoryApprovalStage.ERROR) ||
            page !in 1..100000 || page > shown.page && (!shown.hasMore || page != shown.page + 1)
        ) return
        val bound = binding() ?: return
        request(TvStoryApprovalIssue.LOAD_FAILED) { expected ->
            val result = api.savedMemoryStories(bound.token, bound.libraryId, page)
            if (ticket != expected) return@request
            requireResponse(result.libraryId == bound.libraryId && result.page == page)
            clearEditor()
            review = null
            stories = result.items
            mutable.value = TvStoryApprovalUiState(stage = TvStoryApprovalStage.STORIES, libraries = shown.libraries,
                stories = stories.map { TvStoryApprovalStory(it.id, it.title, it.revision, it.chapterCount) },
                page = page, hasMore = result.hasMore)
        }
    }

    private fun openStory(id: String) {
        if (state.value.stage != TvStoryApprovalStage.STORIES) return
        val summary = stories.singleOrNull { it.id == id } ?: return
        loadReview(summary.id, summary.revision)
    }

    private fun refresh() {
        if (state.value.stage != TvStoryApprovalStage.REVIEW || !state.value.canRefresh) return
        val story = review?.story ?: return
        loadReview(story.id, story.revision)
    }

    private fun loadReview(storyId: String, minimumRevision: Long) {
        val bound = binding() ?: return
        request(TvStoryApprovalIssue.LOAD_FAILED) { expected ->
            val next = read(bound, storyId, minimumRevision)
            if (ticket == expected) showReview(next)
        }
    }

    private fun start() {
        if (state.value.stage != TvStoryApprovalStage.REVIEW || !state.value.canStart) return
        val current = review ?: return
        val story = current.story
        val bound = binding() ?: return
        request(TvStoryApprovalIssue.LOAD_FAILED) { expected ->
            val job = api.requestSavedStoryRefinement(bound.token, bound.libraryId, story.id, story.revision)
            if (ticket != expected) return@request
            requireResponse(job.kind == "narrative" && job.baseRevision == story.revision && job.needsReview)
            showReview(Review(story.copy(autoRefinement = job), current.references))
        }
    }

    private fun apply() {
        if (state.value.stage != TvStoryApprovalStage.REVIEW || !state.value.canApply) return
        val prior = review ?: return
        val proposed = prior.proposal ?: return
        val bound = binding() ?: return
        request(TvStoryApprovalIssue.SUGGESTION_CHANGED) { expected ->
            val fresh = read(bound, prior.story.id, prior.story.revision)
            if (ticket != expected) return@request
            val links = fresh.references
            requireResponse(links != null && fresh.proposal == proposed &&
                fresh.story.autoRefinement?.result == prior.story.autoRefinement?.result)
            val repository = StoryWorkspaceRepository(workspaceApi, ::binding, onDenied = ::accessEnded)
            val nextEditor = StoryWorkspaceStore(repository, scope, ::binding, dictationApi = null, currentAccount = { accountId })
            if (!nextEditor.seedSavedStoryForEdit(fresh.story, requireNotNull(links)) ||
                !nextEditor.applyReviewedStoryProposal(proposed)) {
                nextEditor.clear()
                throw ApiFailure(FailureKind.INVALID_RESPONSE)
            }
            editor = nextEditor
            review = fresh
            mutable.value = state.value.copy(stage = TvStoryApprovalStage.APPLIED, dirty = true, writeStarted = false,
                currentChapters = chapters(fresh),
                focusedChapterId = nextEditor.state.value.proposalImportReview?.firstChangedChapterId)
            observe(nextEditor)
        }
    }

    private fun save(retry: Boolean) {
        val expectedStage = if (retry) TvStoryApprovalStage.UNCERTAIN else TvStoryApprovalStage.APPLIED
        if (state.value.stage != expectedStage) return
        val current = editor ?: return
        val started = if (retry) current.retrySave() else current.confirmReviewed(true) && current.save()
        if (editor !== current) return
        if (started) showEditorState(current) else mutable.value = state.value.copy(issue = TvStoryApprovalIssue.SAVE_FAILED)
    }

    private fun observe(current: StoryWorkspaceStore) {
        editorObserver = scope.launch {
            current.state.collect {
                if (editor === current) showEditorState(current)
            }
        }
    }

    private fun showEditorState(current: StoryWorkspaceStore) {
        val edit = current.state.value
        val shown = state.value
        val updated = when (edit.status) {
            StoryWorkspaceStoreStatus.SAVING -> shown.copy(busy = true, writeStarted = true, issue = null)
            StoryWorkspaceStoreStatus.SAVED -> shown.copy(stage = TvStoryApprovalStage.SAVED, busy = false,
                dirty = false, writeStarted = false, issue = null)
            StoryWorkspaceStoreStatus.SAVE_UNCERTAIN -> shown.copy(stage = TvStoryApprovalStage.UNCERTAIN,
                busy = false, dirty = true, writeStarted = true, issue = null)
            StoryWorkspaceStoreStatus.CONFLICT -> shown.copy(stage = TvStoryApprovalStage.ERROR,
                busy = false, writeStarted = false, issue = TvStoryApprovalIssue.CONFLICT)
            StoryWorkspaceStoreStatus.EDITING -> if (edit.failureStatus != null || edit.invalidInput) {
                shown.copy(stage = TvStoryApprovalStage.APPLIED, busy = false, writeStarted = false,
                    issue = TvStoryApprovalIssue.SAVE_FAILED)
            } else shown
            else -> shown
        }
        mutable.value = updated
    }

    private fun discard() {
        if (state.value.stage != TvStoryApprovalStage.APPLIED || state.value.writeStarted) return
        val current = review ?: return
        clearEditor()
        showReview(current)
    }

    private suspend fun read(bound: MemoryCommunityBinding, id: String, revision: Long): Review {
        val story = try {
            api.savedMemoryStory(bound.token, bound.libraryId, id, revision, sourceReview = true)
        } catch (failure: ApiFailure) {
            if (failure.status !in setOf(400, 404)) throw failure
            if (binding() != bound) throw CancellationException("TV story scope ended")
            api.savedMemoryStory(bound.token, bound.libraryId, id, revision)
        }
        if (binding() != bound) throw CancellationException("TV story scope ended")
        requireResponse(story.id == id && story.libraryId == bound.libraryId && story.revision >= revision)
        val references = if (story.canEdit && story.autoRefinement?.state == "ready") {
            try {
                api.savedMemoryStoryContributionReferences(bound.token, bound.libraryId,
                    id, story.revision, story.chapters.map { it.id })
            } catch (failure: ApiFailure) {
                if (failure.status in setOf(401, 403)) throw failure
                null
            }
        } else null
        return Review(story, references)
    }

    private fun showReview(current: Review) {
        review = current
        val story = current.story
        mutable.value = state.value.copy(stage = TvStoryApprovalStage.REVIEW, dirty = false, writeStarted = false,
            currentStory = TvStoryApprovalStory(story.id, story.title, story.revision, story.chapters.size),
            currentChapters = chapters(current), focusedChapterId = current.proposal?.chapters?.firstOrNull()?.id,
            canStart = story.canEdit && story.autoRefinementAvailable && story.autoRefinement == null,
            canRefresh = story.canEdit && story.autoRefinementAvailable,
            canApply = current.proposal != null, unlinkedSourceCount = current.proposal?.unlinkedSourceCount ?: 0,
            questions = current.proposal?.questions.orEmpty(),
            issue = if (story.autoRefinement?.state == "ready" && current.references == null)
                TvStoryApprovalIssue.LOAD_FAILED else null)
    }

    private fun chapters(current: Review): List<TvStoryApprovalChapter> {
        val proposed = current.proposal?.chapters.orEmpty().associateBy { it.id }
        return current.story.chapters.map { chapter ->
            TvStoryApprovalChapter(chapter.id, chapter.title, chapter.narration,
                proposed[chapter.id]?.narration, changed = chapter.id in proposed)
        }
    }

    private fun binding(): MemoryCommunityBinding? {
        val token = credential ?: return null
        val library = libraryId ?: return null
        return MemoryCommunityBinding(token, library, ticket)
    }

    private fun request(failureIssue: TvStoryApprovalIssue, operation: suspend (Long) -> Unit) {
        val expected = ticket
        mutable.value = state.value.copy(busy = true, issue = null)
        request = scope.launch {
            try {
                operation(expected)
            } catch (failure: CancellationException) { throw failure }
            catch (failure: Exception) {
                if (ticket != expected) return@launch
                if (credential != null && failure is ApiFailure && failure.status in setOf(401, 403)) {
                    accessEnded()
                } else {
                    mutable.value = state.value.copy(issue = failureIssue,
                        canApply = state.value.canApply && failureIssue != TvStoryApprovalIssue.SUGGESTION_CHANGED)
                }
            } finally {
                if (ticket == expected) mutable.value = state.value.copy(busy = false)
            }
        }
    }

    private fun requireResponse(valid: Boolean) {
        if (!valid) throw ApiFailure(FailureKind.INVALID_RESPONSE)
    }

    private fun accessEnded() = reset(TvStoryApprovalIssue.ACCESS_ENDED)

    private fun reset(issue: TvStoryApprovalIssue? = null) {
        ticket++
        request?.cancel()
        request = null
        clearEditor()
        val previous = credential
        credential = null
        accountId = null
        libraryId = null
        stories = emptyList()
        review = null
        mutable.value = TvStoryApprovalUiState(issue = issue)
        previous?.let(::revoke)
    }

    private fun clearEditor() {
        editorObserver?.cancel()
        editorObserver = null
        editor?.clear()
        editor = null
    }

    private fun revoke(old: Bearer) {
        scope.launch {
            try { api.logout(old) }
            catch (failure: CancellationException) { throw failure }
            catch (_: Exception) { /* The TV already cleared the local session. */ }
        }
    }
}
