package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Binds transient memoir-instruction dictation to one exact reader, account and book scope.
 * Opening is explicit; construction never checks capabilities or starts microphone/ASR work.
 */
class MemoryBookNarrativeDictationStore(
    private val api: PhotoHouseApi,
    private val scope: CoroutineScope,
    private val currentScope: () -> MemoryBookNarrativeScope?,
    private val onDenied: () -> Unit = {},
) {
    private data class Binding(
        val accountId: String,
        val token: Bearer,
        val library: String,
        val generation: Long,
        val bookId: String,
        val bookRevision: Long,
        val children: List<EditorialChild>,
        val scopeId: Long,
    )

    private val mutableState = MutableStateFlow<MemoryDictationStore?>(null)
    val state: StateFlow<MemoryDictationStore?> = mutableState.asStateFlow()

    private var binding: Binding? = null

    /** Opens the explicitly requested dictation session, loading capabilities only after the gate passes. */
    @Synchronized
    fun open(): MemoryDictationStore? {
        val actual = validBinding(readScope())
        if (!api.assistantEnabled || actual == null) {
            invalidateCurrent()
            return null
        }
        val existing = binding
        val store = mutableState.value
        if (existing == actual && store != null) return store

        invalidateCurrent()
        binding = actual
        lateinit var created: MemoryDictationStore
        created = MemoryDictationStore(
            scope = scope,
            capabilities = {
                awaitWithinBinding(actual, created) {
                    api.assistantCapabilities(actual.token, actual.library)
                }
            },
            transcribe = { wav, requestId ->
                awaitWithinBinding(actual, created) {
                    api.assistantTranscribe(actual.token, actual.library, wav, requestId)
                }
            },
            onDenied = { handleDenied(actual) },
        )
        mutableState.value = created
        created.loadCapabilities()
        return created
    }

    /** Inserts only a current nonblank transcript; rejection leaves the complete transcript available. */
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
        val extracted = current.takeTranscript()
        return extracted == text
    }

    /** Clears and closes this binding, wiping any retained transcript and cancelling transient work. */
    @Synchronized
    fun clear() {
        invalidateCurrent()
    }

    /** Includes capability loading, recording, transcription and an unconsumed transcript. */
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
        throw CancellationException("Memoir dictation scope changed")
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

    private fun isStillCurrent(expected: Binding?, store: MemoryDictationStore): Boolean =
        api.assistantEnabled && expected != null && binding === expected && mutableState.value === store &&
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
    private fun invalidateIfMatching(expected: Binding?, store: MemoryDictationStore) {
        if (expected == null || binding !== expected || mutableState.value !== store) return
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

    private fun readScope(): MemoryBookNarrativeScope? = try {
        currentScope()
    } catch (_: Exception) {
        null
    }

    private fun validBinding(value: MemoryBookNarrativeScope?): Binding? {
        value ?: return null
        if (value.accountId.isBlank() || value.accountId.length > 256 ||
            !PhoneDiscoveryWire.validLibrary(value.library) || value.generation < 0 || value.scopeId < 0 ||
            value.bookRevision <= 0 || !canonicalUuid(value.bookId) || value.children.isEmpty() ||
            value.children.size > MAX_CHILDREN || value.children.map { it.storyId }.distinct().size != value.children.size ||
            value.children.any { !canonicalUuid(it.storyId) || !positiveRevision(it.revision) }) return null
        return Binding(value.accountId, value.credential, value.library, value.generation, value.bookId,
            value.bookRevision, value.children.toList(), value.scopeId)
    }

    private fun canonicalUuid(value: String): Boolean = runCatching {
        java.util.UUID.fromString(value).toString() == value
    }.getOrDefault(false)

    private fun positiveRevision(value: String): Boolean =
        value.matches(Regex("[1-9][0-9]{0,18}")) && value.toLongOrNull() != null

    private companion object {
        const val MAX_CHILDREN = 24
    }
}
