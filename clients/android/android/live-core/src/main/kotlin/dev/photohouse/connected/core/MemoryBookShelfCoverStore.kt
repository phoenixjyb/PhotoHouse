package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.HttpUrl
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction
import java.util.Collections
import java.util.UUID

data class MemoryBookShelfCoverEntry(val bookId: String, val assetId: String)

/** Private owner binding for one explicit memoir shelf cover read. */
data class MemoryBookShelfCoverScope(
    val accountId: String,
    val credential: Bearer,
    val generation: Long,
    val library: String,
    val shelfScopeId: Long,
    val entries: List<MemoryBookShelfCoverEntry>,
)

/** Covers are transient thumbnail bytes. Credentials and URLs are never exposed. */
data class MemoryBookShelfCoverState(
    val accountId: String? = null,
    val generation: Long? = null,
    val library: String? = null,
    val shelfScopeId: Long? = null,
    val images: Map<String, ByteArray> = emptyMap(),
    val unavailableBookIds: Set<String> = emptySet(),
    val busy: Boolean = false,
)

/** Explicit, sequential, scope-bound thumbnail loader for a memoir shelf. */
class MemoryBookShelfCoverStore(
    private val api: PhotoHouseApi,
    private val scope: CoroutineScope,
    private val currentScope: () -> MemoryBookShelfCoverScope?,
    private val onDenied: () -> Unit = {},
) {
    private val mutable = MutableStateFlow(MemoryBookShelfCoverState())
    val state: StateFlow<MemoryBookShelfCoverState> = mutable.asStateFlow()

    private var bound: MemoryBookShelfCoverScope? = null
    private var action: Job? = null
    private var epoch = 0L
    /** Arrays here are the store-owned buffers also exposed in state. They are wiped before replacement. */
    private val images = linkedMapOf<String, ByteArray>()
    /** In-flight successful responses remain store-owned so close/scope replacement can wipe them immediately. */
    private var pendingImages: MutableMap<String, ByteArray>? = null

    private fun snapshot(): MemoryBookShelfCoverScope? = try {
        currentScope()?.let { it.copy(entries = it.entries.toList()) }?.takeIf(::validScope)
    } catch (_: Exception) { null }

    private fun validScope(value: MemoryBookShelfCoverScope): Boolean =
        validAccount(value.accountId) && value.generation >= 0 && value.shelfScopeId >= 0 &&
            PhoneDiscoveryWire.validLibrary(value.library) && value.entries.size <= MAX_COVERS &&
            value.entries.map { it.bookId }.distinct().size == value.entries.size &&
            value.entries.all { canonicalUuid(it.bookId) && PhoneDiscoveryWire.validId(it.assetId) }

    private fun current(expected: MemoryBookShelfCoverScope, ticket: Long): Boolean {
        val fresh = snapshot()
        return synchronized(this) { currentLocked(expected, ticket, fresh) }
    }

    private fun currentLocked(expected: MemoryBookShelfCoverScope, ticket: Long,
                              fresh: MemoryBookShelfCoverScope?): Boolean =
        epoch == ticket && bound === expected && fresh == expected

    /** Explicitly loads this shelf's covers once. Repeated calls do not duplicate successful or failed reads. */
    @Synchronized
    fun load(): Boolean {
        val fresh = snapshot() ?: run { close(); return false }
        val prior = bound
        val expected = prior?.takeIf { sameScope(it, fresh) } ?: fresh
        if (prior != null && prior !== expected) bind(expected)
        if (mutable.value.busy) return false
        if (bound == expected && (images.isNotEmpty() || mutable.value.unavailableBookIds.isNotEmpty() || expected.entries.isEmpty()))
            return false
        if (bound == null) bind(expected)
        return start(expected, expected.entries)
    }

    /** Explicitly retries only unavailable covers while retaining ready buffers. */
    @Synchronized
    fun retryUnavailable(): Boolean {
        if (mutable.value.busy) return false
        val fresh = snapshot() ?: run { close(); return false }
        val expected = bound ?: return false
        if (!sameScope(expected, fresh)) { close(); return false }
        val unavailable = mutable.value.unavailableBookIds
        if (unavailable.isEmpty()) return false
        val retry = expected.entries.filter { it.bookId in unavailable }
        if (retry.isEmpty()) return false
        return start(expected, retry)
    }

    /** Closes the transient shelf and wipes every currently owned image buffer. */
    @Synchronized
    fun close() {
        epoch++
        action?.cancel(); action = null
        wipe(images.values)
        images.clear()
        wipePending()
        bound = null
        mutable.value = MemoryBookShelfCoverState()
    }

    private fun bind(expected: MemoryBookShelfCoverScope) {
        epoch++
        action?.cancel(); action = null
        wipe(images.values)
        images.clear()
        wipePending()
        bound = expected
        mutable.value = publicState(expected, emptyMap(), emptySet(), busy = false)
    }

    private fun start(expected: MemoryBookShelfCoverScope, entries: List<MemoryBookShelfCoverEntry>): Boolean {
        if (!current(expected, epoch)) {
            clearIfStale(epoch)
            return false
        }
        val ticket = ++epoch
        val attempted = entries.map { it.bookId }.toSet()
        val pending = linkedMapOf<String, ByteArray>()
        pendingImages = pending
        val failed = linkedSetOf<String>()
        var transferred = false
        mutable.value = publicState(expected, images, mutable.value.unavailableBookIds, busy = true)
        action = scope.launch {
            var denied = false
            try {
                for (entry in entries) {
                    currentCoroutineContext().ensureActive()
                    if (!current(expected, ticket)) {
                        clearIfStale(ticket)
                        return@launch
                    }
                    var response: ByteArray? = null
                    try {
                        response = api.thumbnail(expected.credential, expected.library, thumbnailAsset(expected.library, entry.assetId))
                        currentCoroutineContext().ensureActive()
                        val bytes = response
                        val fresh = snapshot()
                        if (!synchronized(this@MemoryBookShelfCoverStore) {
                                currentLocked(expected, ticket, fresh)
                            }) {
                            bytes?.fill(0)
                            response = null
                            clearIfStale(ticket)
                            return@launch
                        }
                        when {
                            bytes == null -> failed += entry.bookId
                            bytes.size !in 1..MAX_COVER_BYTES || !isImage(bytes) -> {
                                bytes.fill(0)
                                response = null
                                failed += entry.bookId
                            }
                            else -> {
                                val staged = synchronized(this@MemoryBookShelfCoverStore) {
                                    if (currentLocked(expected, ticket, fresh) && pendingImages === pending) {
                                        pending[entry.bookId] = bytes
                                        true
                                    } else false
                                }
                                if (!staged) {
                                    bytes.fill(0)
                                    response = null
                                    clearIfStale(ticket)
                                    return@launch
                                }
                                response = null
                            }
                        }
                    } catch (failure: CancellationException) {
                        response?.fill(0)
                        throw failure
                    } catch (failure: ApiFailure) {
                        response?.fill(0)
                        if (failure.status in setOf(401, 403)) {
                            denied = clearDenied(expected, ticket)
                            if (!denied) clearIfStale(ticket)
                            return@launch
                        }
                        if (!current(expected, ticket)) {
                            clearIfStale(ticket)
                            return@launch
                        }
                        failed += entry.bookId
                    } catch (_: Exception) {
                        response?.fill(0)
                        if (!current(expected, ticket)) {
                            clearIfStale(ticket)
                            return@launch
                        }
                        failed += entry.bookId
                    }
                }
                currentCoroutineContext().ensureActive()
                val fresh = snapshot()
                val committed = synchronized(this@MemoryBookShelfCoverStore) {
                    if (currentLocked(expected, ticket, fresh) && pendingImages === pending) {
                        images.putAll(pending)
                        pending.clear()
                        pendingImages = null
                        transferred = true
                        val unavailable = (mutable.value.unavailableBookIds - attempted) + failed
                        mutable.value = publicState(expected, images, unavailable, busy = false)
                        true
                    } else false
                }
                if (!committed) {
                    clearIfStale(ticket)
                    return@launch
                }
            } catch (failure: CancellationException) {
                val fresh = snapshot()
                synchronized(this@MemoryBookShelfCoverStore) {
                    if (currentLocked(expected, ticket, fresh)) {
                        val unresolved = attempted - images.keys
                        mutable.value = publicState(expected, images,
                            mutable.value.unavailableBookIds + unresolved, busy = false)
                    }
                }
                throw failure
            } finally {
                val fresh = snapshot()
                synchronized(this@MemoryBookShelfCoverStore) {
                    if (!transferred) {
                        wipe(pending.values)
                        pending.clear()
                        if (pendingImages === pending) pendingImages = null
                    }
                    if (ticket == epoch && !denied && currentLocked(expected, ticket, fresh) && mutable.value.busy) {
                        mutable.value = mutable.value.copy(busy = false)
                    }
                    if (ticket == epoch) action = null
                }
            }
        }
        return true
    }

    private fun clearDenied(expected: MemoryBookShelfCoverScope, ticket: Long): Boolean {
        val fresh = snapshot()
        val callbackEpoch = synchronized(this) {
            if (!currentLocked(expected, ticket, fresh)) null else {
                epoch++
                action = null
                wipe(images.values); images.clear()
                wipePending()
                bound = null
                mutable.value = MemoryBookShelfCoverState()
                epoch
            }
        } ?: return false
        val stillCurrent = snapshot() == expected && synchronized(this) { epoch == callbackEpoch && bound == null }
        if (stillCurrent) runCatching(onDenied)
        return true
    }

    private fun clearIfStale(ticket: Long) {
        synchronized(this) {
            if (ticket != epoch) return
            epoch++
            action = null
            wipe(images.values); images.clear()
            wipePending()
            bound = null
            mutable.value = MemoryBookShelfCoverState()
        }
    }

    private fun wipePending() {
        pendingImages?.let { wipe(it.values); it.clear() }
        pendingImages = null
    }

    private fun publicState(
        expected: MemoryBookShelfCoverScope,
        values: Map<String, ByteArray>,
        unavailable: Set<String>,
        busy: Boolean,
    ) = MemoryBookShelfCoverState(expected.accountId, expected.generation, expected.library, expected.shelfScopeId,
        Collections.unmodifiableMap(LinkedHashMap(values)), Collections.unmodifiableSet(LinkedHashSet(unavailable)), busy)

    private fun thumbnailAsset(library: String, assetId: String): Asset {
        val path = HttpUrl.Builder().scheme("https").host("contract.invalid")
            .addPathSegment("assets").addPathSegment(assetId).addPathSegment("thumbnail")
            .addQueryParameter("library", library).build().let { it.encodedPath + "?" + it.encodedQuery }
        return Asset(assetId, "image", null, null, null, null, path)
    }

    private fun sameScope(left: MemoryBookShelfCoverScope?, right: MemoryBookShelfCoverScope) =
        left != null && left.accountId == right.accountId && left.credential === right.credential &&
            left.generation == right.generation && left.library == right.library &&
            left.shelfScopeId == right.shelfScopeId && left.entries == right.entries

    private fun validAccount(value: String): Boolean = runCatching {
        require(value.isNotBlank() && value.codePointCount(0, value.length) <= 256 && value.none { Character.isISOControl(it) })
        Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value))
        true
    }.getOrDefault(false)

    private fun canonicalUuid(value: String) = runCatching { UUID.fromString(value).toString() == value }.getOrDefault(false)

    private fun isImage(bytes: ByteArray): Boolean =
        (bytes.size >= 3 && bytes[0] == 0xff.toByte() && bytes[1] == 0xd8.toByte() && bytes[2] == 0xff.toByte()) ||
            (bytes.size >= 8 && bytes[0] == 0x89.toByte() && bytes[1] == 0x50.toByte() &&
                bytes[2] == 0x4e.toByte() && bytes[3] == 0x47.toByte() && bytes[4] == 0x0d.toByte() &&
                bytes[5] == 0x0a.toByte() && bytes[6] == 0x1a.toByte() && bytes[7] == 0x0a.toByte()) ||
            (bytes.size >= 12 && bytes[0] == 'R'.code.toByte() && bytes[1] == 'I'.code.toByte() &&
                bytes[2] == 'F'.code.toByte() && bytes[3] == 'F'.code.toByte() &&
                bytes[8] == 'W'.code.toByte() && bytes[9] == 'E'.code.toByte() &&
                bytes[10] == 'B'.code.toByte() && bytes[11] == 'P'.code.toByte())

    private fun wipe(values: Iterable<ByteArray>) { values.forEach { it.fill(0) } }

    private companion object {
        const val MAX_COVERS = 8
        const val MAX_COVER_BYTES = 512 * 1024
    }
}
