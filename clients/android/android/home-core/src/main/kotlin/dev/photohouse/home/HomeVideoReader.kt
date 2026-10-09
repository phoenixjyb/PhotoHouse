package dev.photohouse.home

import kotlinx.coroutines.*
import java.io.Closeable
import java.io.IOException
import java.io.InterruptedIOException
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicBoolean

/** Owned random-access bytes, independent of any server schema or Android player. */
interface HomeVideoSource : Closeable {
    fun size(): Long
    fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int
    fun onClose(listener: () -> Unit)
}

/** Serial memory-only reads. The future catalog adapter must verify revision, Content-Range,
 * content type and the advertised total before returning bytes. No URL reaches the decoder.
 * Caller supplies its frozen contract's total/chunk limits; this reader additionally caps
 * each allocation at 256 KiB. Closing cancels the loader before notifying the native player.
 */
class HomeVideoReader(
    private val totalBytes: Long,
    private val chunkBytes: Int,
    fetch: suspend (Long, Int) -> ByteArray,
    failed: (Exception) -> Unit,
) : HomeVideoSource {
    init { require(totalBytes > 0 && chunkBytes in 1..262144) }
    @Volatile private var loader: (suspend (Long, Int) -> ByteArray)? = fetch
    @Volatile private var failureCallback: ((Exception) -> Unit)? = failed
    private val lifetimeLock = Any()
    private val readLock = Any()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val closed = AtomicBoolean(false)
    private val notified = AtomicBoolean(false)
    // Native extractors probe MP4 headers in tiny reads. Keep one bounded,
    // generation-owned window instead of an HTTP request per probe.
    private var windowStart = 0L
    private var window: ByteArray? = null
    private val listeners = CopyOnWriteArrayList<() -> Unit>()
    val isClosed get() = closed.get()
    override fun toString() = "HomeVideoReader([private])"
    override fun onClose(listener: () -> Unit) {
        listeners += listener
        if (closed.get() && listeners.remove(listener)) listener()
    }
    override fun close() {
        val first = synchronized(lifetimeLock) {
            if (!closed.compareAndSet(false, true)) false
            else { loader = null; failureCallback = null; window = null; true }
        }
        if (first) {
            scope.cancel()
            listeners.toList().forEach { if (listeners.remove(it)) it() }
        }
    }
    private fun checkOpen() { if (closed.get()) throw IOException("Video closed") }
    private fun <T> read(action: () -> T): T = synchronized(readLock) {
        try { checkOpen(); action() }
        catch (e: InterruptedIOException) { throw e }
        catch (e: Exception) {
            val report = !closed.get() && e !is CancellationException
            val callback = failureCallback
            close()
            if (report && notified.compareAndSet(false, true)) callback?.invoke(e)
            throw IOException("Video read unavailable")
        }
    }
    override fun size(): Long = read { totalBytes }
    override fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int = read {
        require(position >= 0 && offset >= 0 && size >= 0 && offset <= buffer.size && size <= buffer.size - offset)
        if (size == 0) return@read 0
        if (position >= totalBytes) return@read -1
        val length = minOf(size.toLong(), chunkBytes.toLong(), totalBytes - position).toInt()
        val cached = synchronized(lifetimeLock) {
            checkOpen()
            window?.takeIf { position >= windowStart && position - windowStart <= it.size - length }?.let {
                val start = (position - windowStart).toInt()
                it.copyInto(buffer, offset, start, start + length)
                true
            } ?: false
        }
        if (cached) return@read length
        val fetchLength = minOf(chunkBytes.toLong(), totalBytes - position).toInt()
        val task = scope.async { (loader ?: throw CancellationException())(position, fetchLength) }
        val bytes = try { runBlocking { task.await() } }
        catch (_: InterruptedException) {
            // Media3 interrupts its loader during seek. Cancel this fetch, not the owner.
            task.cancel()
            throw InterruptedIOException("Video read interrupted")
        }
        checkOpen()
        if (bytes.size != fetchLength) throw IOException("Invalid video chunk")
        synchronized(lifetimeLock) {
            checkOpen(); windowStart = position; window = bytes
            bytes.copyInto(buffer, offset, 0, length)
        }
        length
    }
}
