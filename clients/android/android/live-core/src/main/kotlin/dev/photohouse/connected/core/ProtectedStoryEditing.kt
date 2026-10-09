package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.nio.charset.CodingErrorAction
import java.util.UUID

private fun safeDefaultByline(value: String?): String {
    if (value == null || value.isBlank() || value.any { Character.isISOControl(it) }) return ""
    val encoded = runCatching {
        Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value))
    }.getOrNull() ?: return ""
    return if (encoded.remaining() <= 256) value else ""
}

data class StoryDraft(
    val title: String = "",
    val text: String = "",
    val language: String = "mixed",
    val byline: String = "",
)

data class StoryMutation(
    val assetId: String,
    val storyId: String?,
    val revision: Long?,
    val draft: StoryDraft,
    val mutationId: UUID = UUID.randomUUID(),
)

enum class StoryEditorPhase { EDITING, REVIEW, SAVING, UNCERTAIN, CONFLICT, SAVED, DENIED, CLOSED }

data class StoryEditorState(
    val phase: StoryEditorPhase = StoryEditorPhase.EDITING,
    val draft: StoryDraft = StoryDraft(),
    val mutation: StoryMutation? = null,
    val latest: ProtectedStory? = null,
    val message: String? = null,
    val retryAtMillis: Long = 0,
    val canUseLatest: Boolean = false,
)

/** UI-dispatcher-confined state machine; the parent owns scope and permission gating. */
class ProtectedStoryEditorStore(
    private val scope: CoroutineScope,
    private val assetId: String,
    initialStory: ProtectedStory?,
    private val save: suspend (StoryMutation) -> ProtectedStory,
    private val reload: suspend () -> ProtectedStory?,
    private val onSaved: (ProtectedStory) -> Unit,
    private val onDenied: () -> Unit,
    private val now: () -> Long = System::currentTimeMillis,
    val dictation: MemoryDictationStore? = null,
    defaultByline: String? = null,
) {
    private val mutable = MutableStateFlow(StoryEditorState(
        draft = initialStory?.let { StoryDraft(it.title, it.text, it.language, it.byline) }
            ?: StoryDraft(byline = safeDefaultByline(defaultByline)),
        latest = initialStory,
    ))
    val state = mutable.asStateFlow()
    private val targetStoryId = initialStory?.id
    private var job: Job? = null
    private var generation = 0L
    private var closed = false
    private var reloadedForConflict = false

    fun updateTitle(value: String) = update { copy(title = value) }
    fun updateText(value: String) = update { copy(text = value) }
    fun updateLanguage(value: String) = update { copy(language = value) }
    fun updateByline(value: String) = update { copy(byline = value) }

    /** Explicitly append reviewed speech to the current draft, never overwrite typed words. */
    fun insertDictation(): Boolean {
        if (closed || state.value.phase != StoryEditorPhase.EDITING) return false
        val words = dictation?.state?.value?.transcript?.takeIf { it.isNotBlank() } ?: return false
        val text = state.value.draft.text.let { if (it.isBlank()) words else "$it\n\n$words" }
        val draft = state.value.draft.copy(text = text)
        val error = validate(draft)
        if (error != null) {
            mutable.value = state.value.copy(message = error)
            return false
        }
        if (dictation.takeTranscript() == null) return false
        update { draft }
        return true
    }

    private fun update(change: StoryDraft.() -> StoryDraft) {
        if (closed || state.value.phase != StoryEditorPhase.EDITING) return
        mutable.value = state.value.copy(draft = change(state.value.draft), message = null)
    }

    fun beginReview(): Boolean {
        if (closed || state.value.phase != StoryEditorPhase.EDITING) return false
        dictation?.state?.value?.let {
            if (it.recording || it.transcribing || it.transcript != null) return false
        }
        if (targetStoryId != null && (state.value.latest?.id != targetStoryId || state.value.latest?.canEdit != true)) return false
        val error = validate(state.value.draft)
        if (error != null) {
            mutable.value = state.value.copy(message = error)
            return false
        }
        val current = state.value.latest
        val mutation = StoryMutation(assetId, current?.id, current?.revision, state.value.draft)
        reloadedForConflict = false
        mutable.value = state.value.copy(phase = StoryEditorPhase.REVIEW, mutation = mutation, message = null, retryAtMillis = 0)
        return true
    }

    fun backToEdit() {
        if (!closed && state.value.phase == StoryEditorPhase.REVIEW) mutable.value = state.value.copy(phase = StoryEditorPhase.EDITING, message = null)
    }

    fun confirmSave() {
        if (closed || state.value.phase != StoryEditorPhase.REVIEW) return
        val mutation = state.value.mutation ?: return
        mutable.value = state.value.copy(phase = StoryEditorPhase.SAVING, message = null)
        val token = ++generation
        job?.cancel()
        job = scope.launch {
            try {
                val result = save(mutation)
                if (closed || token != generation) return@launch
                mutable.value = state.value.copy(phase = StoryEditorPhase.SAVED, latest = result, mutation = null, message = null, retryAtMillis = 0)
                onSaved(result)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (closed || token != generation) return@launch
                when {
                    e is ApiFailure && (e.status == 401 || e.status == 403) -> {
                        mutable.value = StoryEditorState(phase = StoryEditorPhase.DENIED, message = "Access denied / 无权保存")
                        onDenied()
                    }
                    e is ApiFailure && (e.kind == FailureKind.OFFLINE || e.status in 500..599) ->
                        mutable.value = state.value.copy(phase = StoryEditorPhase.UNCERTAIN, retryAtMillis = retryAt(e), message = "Save status is unknown; retry the exact save / 保存状态未知，可重试相同内容")
                    e is ApiFailure && e.status == 409 -> {
                        reloadedForConflict = false
                        mutable.value = state.value.copy(phase = StoryEditorPhase.CONFLICT, canUseLatest = false, message = "This memory changed; reload before saving / 内容已变化，请先重新加载")
                    }
                    e is ApiFailure && (e.kind == FailureKind.TLS || e.kind == FailureKind.INVALID_RESPONSE || e.status == 429) ->
                        mutable.value = state.value.copy(phase = StoryEditorPhase.UNCERTAIN, retryAtMillis = retryAt(e), message = "Save status is unknown; retry the exact save / 保存状态未知，可重试相同内容")
                    else -> mutable.value = state.value.copy(phase = StoryEditorPhase.EDITING, message = "Could not save / 保存失败")
                }
            }
        }
    }

    /** Manual retry only. The immutable mutation keeps both UUID and body unchanged. */
    fun retryUncertain() {
        if (!closed && state.value.phase == StoryEditorPhase.UNCERTAIN && now() >= state.value.retryAtMillis) {
            mutable.value = state.value.copy(phase = StoryEditorPhase.REVIEW, message = null)
            confirmSave()
        }
    }

    fun dismissUncertain() {
        if (!closed && state.value.phase == StoryEditorPhase.UNCERTAIN) close()
    }

    fun reloadCurrent() {
        if (closed || state.value.phase != StoryEditorPhase.CONFLICT) return
        reloadedForConflict = false
        val token = ++generation
        mutable.value = state.value.copy(phase = StoryEditorPhase.SAVING, canUseLatest = false, message = "Reloading current memory… / 正在重新加载…")
        job?.cancel()
        job = scope.launch {
            try {
                val current = reload()
                if (closed || token != generation) return@launch
                if (current == null || current.id != state.value.mutation?.storyId || current.assetId != assetId || !current.canEdit) {
                    mutable.value = state.value.copy(phase = StoryEditorPhase.CONFLICT, latest = current, message = "The current memory cannot be edited / 当前回忆不可编辑")
                    return@launch
                }
                reloadedForConflict = true
                mutable.value = state.value.copy(phase = StoryEditorPhase.CONFLICT, latest = current, canUseLatest = true, message = "Choose whether to use the latest revision / 请确认是否采用最新版本")
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (!closed && token == generation) {
                    if (e is ApiFailure && (e.status == 401 || e.status == 403)) {
                        mutable.value = StoryEditorState(phase = StoryEditorPhase.DENIED)
                        onDenied()
                    } else mutable.value = state.value.copy(phase = StoryEditorPhase.CONFLICT, message = "Could not reload; try again / 重新加载失败，请重试")
                }
            }
        }
    }

    /** Explicitly adopts only the reloaded revision; the user's draft remains unchanged. */
    fun useLatestRevision() {
        if (closed || state.value.phase != StoryEditorPhase.CONFLICT || !reloadedForConflict) return
        val latest = state.value.latest ?: return
        val mutation = state.value.mutation ?: return
        if (latest.id != mutation.storyId || latest.assetId != assetId || !latest.canEdit) return
        reloadedForConflict = false
        mutable.value = state.value.copy(
            phase = StoryEditorPhase.REVIEW, canUseLatest = false,
            mutation = mutation.copy(storyId = latest.id, revision = latest.revision, mutationId = UUID.randomUUID()),
            message = null,
        )
    }

    fun dismissConflict() {
        if (!closed && state.value.phase == StoryEditorPhase.CONFLICT) mutable.value = state.value.copy(phase = StoryEditorPhase.EDITING, message = null)
    }

    fun close() {
        if (closed) return
        closed = true
        ++generation
        job?.cancel(); job = null
        dictation?.close()
        mutable.value = StoryEditorState(phase = StoryEditorPhase.CLOSED)
    }

    private fun retryAt(e: Exception): Long {
        val delay = (e as? ApiFailure)?.retryAfterMillis ?: 0
        val at = now()
        return if (delay.coerceAtLeast(0) > Long.MAX_VALUE - at) Long.MAX_VALUE else at + delay.coerceAtLeast(0)
    }

    private fun validate(draft: StoryDraft): String? {
        fun utf8(value: String): Boolean = runCatching {
            Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value))
        }.isSuccess
        if (!utf8(draft.title) || !utf8(draft.text) || !utf8(draft.byline) || listOf(draft.title, draft.text, draft.byline).any { '\u0000' in it }) return "Invalid text / 文本无效"
        if (draft.text.isBlank()) return "Memory text is required / 请填写回忆内容"
        if (draft.title.toByteArray(Charsets.UTF_8).size > 512) return "Title is too long / 标题过长"
        if (draft.text.toByteArray(Charsets.UTF_8).size > 64 * 1024) return "Memory is too long / 回忆内容过长"
        if (draft.byline.toByteArray(Charsets.UTF_8).size > 256) return "Byline is too long / 署名过长"
        if (draft.language !in setOf("en", "zh", "mixed", "und")) return "Choose a supported language / 请选择支持的语言"
        return null
    }
}
