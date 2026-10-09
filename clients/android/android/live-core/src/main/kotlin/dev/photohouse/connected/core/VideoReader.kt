package dev.photohouse.connected.core

import kotlinx.coroutines.*
import java.io.Closeable
import java.io.IOException
import java.io.InterruptedIOException
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicBoolean

data class VideoReadFailure(val kind: FailureKind?, val status: Int?)

/** Memory-only, serialized random reads. The player never receives a URL or bearer.
 * The default has no reusable chunk cache; optional read-ahead is one-use only.
 */
class VideoReader internal constructor(
    fetch: suspend (Long, Int) -> VideoChunk,
    private val expiresAt: Long,
    private val now: () -> Long,
    initialSize: Long = -1L,
    private val readAhead: Boolean = false,
    private val retryTransientRead: Boolean = false,
    failed: (Exception) -> Unit,
) : Closeable {
    @Volatile private var loader: (suspend (Long, Int) -> VideoChunk)? = fetch
    @Volatile private var failureCallback: ((Exception) -> Unit)? = failed
    private val lifetimeLock = Any()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val closed = AtomicBoolean(false)
    private val notified = AtomicBoolean(false)
    private val listeners = CopyOnWriteArrayList<() -> Unit>()
    private val readLock = Any()
    private var total = initialSize
    private var readAheadStart = -1L
    private var readAheadBytes: ByteArray? = null
    private var readAheadOffset = 0
    init { require(initialSize == -1L || initialSize in 1..HttpsPhotoHouseApi.VIDEO_FILE_LIMIT) }
    @Volatile var lastFailure: VideoReadFailure? = null
        private set
    val isClosed get() = closed.get()
    val hasReadFailure get() = notified.get()
    override fun toString() = "VideoReader([private])"
    fun onClose(listener: () -> Unit) {
        listeners += listener
        if (closed.get() && listeners.remove(listener)) listener()
    }
    override fun close() {
        val first = synchronized(lifetimeLock) {
            if (!closed.compareAndSet(false, true)) false
            else { loader = null; failureCallback = null; clearReadAheadLocked(); true }
        }
        if (first) {
            scope.cancel()
            listeners.toList().forEach { if (listeners.remove(it)) it() }
        }
    }
    private fun checkOpen() {
        if (closed.get()) throw IOException("Video closed")
        if (now() >= expiresAt) throw ApiFailure(FailureKind.HTTP, 401)
    }
    private fun clearReadAheadLocked() {
        readAheadBytes?.fill(0)
        readAheadBytes = null
        readAheadStart = -1L
        readAheadOffset = 0
    }
    private fun chunk(start: Long, length: Int): VideoChunk {
        checkOpen()
        val task = scope.async {
            try {
                (loader ?: throw CancellationException())(start, length)
            } catch (e: ApiFailure) {
                if (!retryTransientRead || e.kind != FailureKind.OFFLINE) throw e
                checkOpen()
                currentCoroutineContext().ensureActive()
                delay(100)
                checkOpen()
                currentCoroutineContext().ensureActive()
                // One identical authorized GET, never a retry loop or mutation.
                (loader ?: throw CancellationException())(start, length)
            }
        }
        val part = try { runBlocking { task.await() } }
        catch (_: InterruptedException) {
            // Media3 interrupts its loader during seek. Cancel this fetch, not the owner.
            task.cancel()
            throw InterruptedIOException("Video read interrupted")
        }
        return try {
            checkOpen()
            if (part.total > HttpsPhotoHouseApi.VIDEO_FILE_LIMIT) throw ApiFailure(FailureKind.TOO_LARGE)
            if (part.start != start || part.total <= start || (total >= 0 && total != part.total) ||
                part.bytes.size.toLong() != minOf(length.toLong(), part.total - start)) throw ApiFailure(FailureKind.INVALID_RESPONSE)
            total = part.total
            part
        } catch (e: Exception) {
            part.bytes.fill(0)
            throw e
        }
    }
    private fun <T> read(action: () -> T): T = synchronized(readLock) {
        try { checkOpen(); action() }
        catch (e: InterruptedIOException) { throw e }
        catch (e: Exception) {
            val report = !closed.get() && e !is CancellationException
            val callback = failureCallback
            val notify = report && notified.compareAndSet(false, true)
            if (notify) lastFailure = VideoReadFailure((e as? ApiFailure)?.kind, (e as? ApiFailure)?.status)
            close()
            if (notify) callback?.invoke(e)
            throw IOException("Video read unavailable")
        }
    }
    fun size(): Long = read {
        if (total < 0) chunk(0, 1)
        total
    }
    fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int = read {
        require(position >= 0 && offset >= 0 && size >= 0 && offset <= buffer.size && size <= buffer.size - offset)
        if (size == 0) return@read 0
        if (total < 0) chunk(0, 1)
        if (position >= total) {
            if (readAhead) synchronized(lifetimeLock) { clearReadAheadLocked() }
            return@read -1
        }
        val length = minOf(size.toLong(), HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT.toLong(), total - position).toInt()
        if (!readAhead) {
            val part = chunk(position, length)
            try {
                synchronized(lifetimeLock) { checkOpen(); part.bytes.copyInto(buffer, offset) }
                return@read part.bytes.size
            } catch (e: Exception) {
                part.bytes.fill(0)
                throw e
            }
        }
        synchronized(lifetimeLock) {
            if (readAheadStart != position) clearReadAheadLocked()
            val cached = readAheadBytes
            if (cached != null) {
                val remaining = cached.size - readAheadOffset
                val count = minOf(size, remaining)
                checkOpen()
                cached.copyInto(buffer, offset, readAheadOffset, readAheadOffset + count)
                cached.fill(0, readAheadOffset, readAheadOffset + count)
                readAheadOffset += count
                readAheadStart += count
                if (readAheadOffset == cached.size) clearReadAheadLocked()
                return@read count
            }
        }
        val part = chunk(position, minOf(total - position, HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT.toLong()).toInt())
        try {
            synchronized(lifetimeLock) {
                checkOpen()
                readAheadStart = position
                readAheadOffset = 0
                readAheadBytes = part.bytes
                val cached = readAheadBytes!!
                val count = minOf(size, cached.size)
                cached.copyInto(buffer, offset, 0, count)
                cached.fill(0, 0, count)
                readAheadOffset = count
                readAheadStart += count
                if (readAheadOffset == cached.size) clearReadAheadLocked()
                return@read count
            }
        } catch (e: Exception) {
            part.bytes.fill(0)
            throw e
        }
    }
}
