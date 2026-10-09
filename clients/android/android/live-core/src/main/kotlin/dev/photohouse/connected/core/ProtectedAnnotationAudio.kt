package dev.photohouse.connected.core

import java.io.Closeable
import java.io.IOException

/** Ephemeral protected audio bytes. Closing wipes the backing array. */
class ProtectedAnnotationAudio internal constructor(bytes: ByteArray) : Closeable {
    private val lock = Any()
    private var content: ByteArray? = bytes
    private val closeListeners = mutableListOf<() -> Unit>()

    val size: Int get() = synchronized(lock) { content?.size ?: 0 }
    val isClosed: Boolean get() = synchronized(lock) { content == null }
    override fun toString() = "ProtectedAnnotationAudio([private])"

    fun readAt(position: Int, buffer: ByteArray, offset: Int, length: Int): Int = synchronized(lock) {
        val bytes = content ?: throw IOException("Audio is closed")
        if (position < 0 || offset < 0 || length < 0 || offset > buffer.size || length > buffer.size - offset)
            throw IOException("Invalid audio read")
        if (position >= bytes.size) return@synchronized -1
        val count = minOf(length, bytes.size - position)
        bytes.copyInto(buffer, offset, position, position + count)
        count
    }

    fun onClose(listener: () -> Unit) {
        val runNow = synchronized(lock) {
            if (content == null) true else { closeListeners += listener; false }
        }
        if (runNow) listener()
    }

    fun removeOnClose(listener: () -> Unit) { synchronized(lock) { closeListeners.remove(listener) } }

    override fun close() {
        val listeners = synchronized(lock) {
            val bytes = content ?: return
            bytes.fill(0)
            content = null
            closeListeners.toList().also { closeListeners.clear() }
        }
        listeners.forEach { runCatching(it) }
    }
}
