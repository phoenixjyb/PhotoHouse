package dev.photohouse.connected.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Exact owner scope for optional introduction dictation in one new memoir composition. */
data class MemoryBookCompositionDictationScope(
    val accountId: String,
    val credential: Bearer,
    val generation: Long,
    val library: String,
    val shelfScopeId: Long,
    val actionEpoch: Long,
    /** False outside READY/editable composer state, during a save, or after creation. */
    val editable: Boolean,
)

/** Explicit, transient ASR session fenced to one new-memoir composer action epoch. */
class MemoryBookCompositionDictationStore(
    private val api: PhotoHouseApi,
    private val scope: CoroutineScope,
    private val currentScope: () -> MemoryBookCompositionDictationScope?,
    private val onDenied: () -> Unit = {},
) {
    private data class Binding(
        val accountId: String,
        val credential: Bearer,
        val generation: Long,
        val library: String,
        val shelfScopeId: Long,
        val actionEpoch: Long,
    )

    private val mutableState = MutableStateFlow<MemoryDictationStore?>(null)
    val state: StateFlow<MemoryDictationStore?> = mutableState.asStateFlow()
    private var binding: Binding? = null

    /** Capability work and microphone access start only after this explicit call. */
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
            isCurrent = { isStillCurrent(actual, created) },
        )
        mutableState.value = created
        created.loadCapabilities()
        return created
    }

    /** Consume only the exact rendered helper's current transcript after the owner accepts insertion. */
    @Synchronized
    fun insertTranscript(expected: MemoryDictationStore, accept: (String) -> Boolean): Boolean {
        if (mutableState.value !== expected) return false
        val expectedBinding = binding ?: return false
        if (!isStillCurrent(expectedBinding, expected)) {
            invalidateIfMatching(expectedBinding, expected)
            return false
        }
        val transcript = expected.state.value.transcript?.takeIf(String::isNotBlank) ?: return false
        if (!accept(transcript)) return false
        if (!isStillCurrent(expectedBinding, expected)) {
            invalidateIfMatching(expectedBinding, expected)
            return false
        }
        return expected.takeTranscript() == transcript
    }

    /** Includes capability loading, recording, ASR and an unconsumed review transcript. */
    val hasUnfinishedInput: Boolean
        @Synchronized get() {
            val current = currentStore() ?: return false
            val state = current.state.value
            return state.loading || state.recording || state.transcribing || state.transcript != null
        }

    @Synchronized
    fun clear() = invalidateCurrent()

    /** An old composable disposal cannot close a replacement helper. */
    @Synchronized
    fun clearIfCurrent(expected: MemoryDictationStore): Boolean {
        if (mutableState.value !== expected) return false
        invalidateCurrent()
        return true
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
        throw CancellationException("Memoir composition dictation scope changed")
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

    private fun readScope(): MemoryBookCompositionDictationScope? = try {
        currentScope()
    } catch (_: Exception) {
        null
    }

    private fun validBinding(value: MemoryBookCompositionDictationScope?): Binding? {
        value ?: return null
        if (!api.assistantEnabled || !value.editable || value.accountId.isBlank() ||
            value.accountId.length > MAX_ACCOUNT_ID || value.accountId.any { it.isISOControl() } ||
            !PhoneDiscoveryWire.validLibrary(value.library) || value.generation < 0 || value.shelfScopeId < 0 ||
            value.actionEpoch <= 0) return null
        return Binding(value.accountId, value.credential, value.generation, value.library,
            value.shelfScopeId, value.actionEpoch)
    }

    private companion object {
        const val MAX_ACCOUNT_ID = 256
    }
}
