package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Exact editor/chapter scope for a transient narration dictation session. */
data class StoryChapterDictationScope(
    val accountId: String,
    val credential: Bearer,
    val library: String,
    val generation: Long,
    /** Stable for one editor session; ordinary text edits must not change it. */
    val scopeId: Long,
    val selectionRevision: String,
    val savedStoryId: String? = null,
    val savedStoryRevision: Long? = null,
    val chapterId: String,
    val chapterAssetIds: List<String>,
    /** False while read-only, busy, or a save is pending/uncertain. */
    val editable: Boolean,
)

/**
 * Binds reusable protected ASR to one editable grouped-story chapter.
 * Construction is inert; microphone and capability work begin only after [open].
 */
class StoryChapterDictationStore(
    private val api: PhotoHouseApi,
    private val scope: CoroutineScope,
    private val currentScope: () -> StoryChapterDictationScope?,
    private val onDenied: () -> Unit = {},
) {
    private data class Binding(
        val accountId: String,
        val credential: Bearer,
        val library: String,
        val generation: Long,
        val scopeId: Long,
        val selectionRevision: String,
        val savedStoryId: String?,
        val savedStoryRevision: Long?,
        val chapterId: String,
        val chapterAssetIds: List<String>,
    )

    private val mutableState = MutableStateFlow<MemoryDictationStore?>(null)
    val state: StateFlow<MemoryDictationStore?> = mutableState.asStateFlow()

    private var binding: Binding? = null

    /** Starts a new explicit session, or returns the existing session for the same binding. */
    @Synchronized
    fun open(): MemoryDictationStore? {
        val actual = validBinding(readScope())
        if (!api.assistantEnabled || actual == null) {
            invalidateCurrent()
            return null
        }
        if (binding == actual) return mutableState.value

        invalidateCurrent()
        binding = actual
        lateinit var created: MemoryDictationStore
        created = MemoryDictationStore(
            scope = scope,
            capabilities = {
                awaitWithinBinding(actual, created) {
                    api.assistantCapabilities(actual.credential, actual.library)
                }
            },
            transcribe = { wav, requestId ->
                awaitWithinBinding(actual, created) {
                    api.assistantTranscribe(actual.credential, actual.library, wav, requestId)
                }
            },
            onDenied = { handleDenied(actual) },
        )
        mutableState.value = created
        created.loadCapabilities()
        return created
    }

    /** Inserts only a still-current transcript; a rejected callback keeps it available for review. */
    @Synchronized
    fun insertTranscript(accept: (String) -> Boolean): Boolean {
        val expected = binding ?: return false
        val current = currentStore() ?: return false
        if (binding !== expected) return false
        val text = current.state.value.transcript?.takeIf { it.isNotBlank() } ?: return false
        if (!accept(text)) return false
        if (!isStillCurrent(expected, current)) {
            invalidateIfMatching(expected, current)
            return false
        }
        return current.takeTranscript() == text
    }

    /** Drops an in-progress capture/transcription or an unconsumed transcript and closes this binding. */
    @Synchronized
    fun clear() = invalidateCurrent()

    /** Includes capability loading, recording, transcription, and an unconsumed transcript. */
    val hasUnfinishedInput: Boolean
        @Synchronized get() {
            val current = currentStore() ?: return false
            val value = current.state.value
            return value.loading || value.recording || value.transcribing || value.transcript != null
        }

    @Synchronized
    private fun currentStore(): MemoryDictationStore? {
        val expected = binding ?: return null
        val store = mutableState.value ?: return null
        if (!isStillCurrent(expected, store)) {
            invalidateIfMatching(expected, store)
            return null
        }
        return store
    }

    private fun requireCurrent(expected: Binding, store: MemoryDictationStore) {
        synchronized(this) {
            if (isStillCurrent(expected, store)) return
            invalidateIfMatching(expected, store)
        }
        throw CancellationException("Story chapter dictation scope changed")
    }

    private suspend fun <T> awaitWithinBinding(
        expected: Binding,
        store: MemoryDictationStore,
        operation: suspend () -> T,
    ): T {
        requireCurrent(expected, store)
        val result = try {
            operation()
        } catch (cancelled: CancellationException) {
            synchronized(this) {
                if (!isStillCurrent(expected, store)) invalidateIfMatching(expected, store)
            }
            throw cancelled
        } catch (failure: Exception) {
            requireCurrent(expected, store)
            throw failure
        }
        requireCurrent(expected, store)
        return result
    }

    private fun isStillCurrent(expected: Binding, store: MemoryDictationStore): Boolean =
        api.assistantEnabled && binding === expected && mutableState.value === store &&
            validBinding(readScope()) == expected

    @Synchronized
    private fun handleDenied(expected: Binding) {
        val store = mutableState.value ?: return
        if (binding !== expected) return
        if (!isStillCurrent(expected, store)) {
            invalidateIfMatching(expected, store)
            return
        }
        store.close()
        binding = null
        mutableState.value = null
        onDenied()
    }

    @Synchronized
    private fun invalidateIfMatching(expected: Binding, store: MemoryDictationStore) {
        if (binding !== expected || mutableState.value !== store) return
        store.close()
        binding = null
        mutableState.value = null
    }

    @Synchronized
    private fun invalidateCurrent() {
        mutableState.value?.close()
        mutableState.value = null
        binding = null
    }

    private fun readScope(): StoryChapterDictationScope? = try {
        currentScope()
    } catch (_: Exception) {
        null
    }

    private fun validBinding(value: StoryChapterDictationScope?): Binding? {
        value ?: return null
        if (!api.assistantEnabled || !value.editable || value.accountId.isBlank() ||
            value.accountId.length > MAX_ACCOUNT_ID || value.accountId.any { it.isISOControl() } ||
            !PhoneDiscoveryWire.validLibrary(value.library) || value.generation < 0 || value.scopeId < 0 ||
            !SELECTION_REVISION.matches(value.selectionRevision) ||
            !pairedSavedStory(value.savedStoryId, value.savedStoryRevision) ||
            !CHAPTER_ID.matches(value.chapterId) || value.chapterAssetIds.size !in 1..MAX_CHAPTER_ASSETS ||
            value.chapterAssetIds.distinct().size != value.chapterAssetIds.size ||
            value.chapterAssetIds.any { !canonicalAssetId(it) }) return null
        return Binding(
            accountId = value.accountId,
            credential = value.credential,
            library = value.library,
            generation = value.generation,
            scopeId = value.scopeId,
            selectionRevision = value.selectionRevision,
            savedStoryId = value.savedStoryId,
            savedStoryRevision = value.savedStoryRevision,
            chapterId = value.chapterId,
            // Do not retain a caller-owned mutable list in the fence.
            chapterAssetIds = value.chapterAssetIds.toList(),
        )
    }

    private fun pairedSavedStory(id: String?, revision: Long?): Boolean = when {
        id == null && revision == null -> true
        id == null || revision == null -> false
        revision <= 0 -> false
        else -> canonicalUuid(id)
    }

    private fun canonicalUuid(value: String): Boolean = runCatching {
        java.util.UUID.fromString(value).toString() == value
    }.getOrDefault(false)

    private fun canonicalAssetId(value: String): Boolean =
        ASSET_ID.matches(value) && value.toLongOrNull() != null

    private companion object {
        const val MAX_ACCOUNT_ID = 256
        const val MAX_CHAPTER_ASSETS = 4
        val SELECTION_REVISION = Regex("[0-9a-f]{64}")
        val CHAPTER_ID = Regex("chapter-[1-6]")
        val ASSET_ID = Regex("[1-9][0-9]{0,18}")
    }
}
