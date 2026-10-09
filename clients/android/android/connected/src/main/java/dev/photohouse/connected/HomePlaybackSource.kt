package dev.photohouse.connected

import dev.photohouse.home.HomeVideoSource

/** Delegates cancellation/byte checks to the home transport; owns no network state. */
internal class HomePlaybackSource(private val source: HomeVideoSource) : PhonePlaybackSource {
    override fun size() = source.size()
    override fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int) = source.readAt(position, buffer, offset, size)
    override fun onClose(listener: () -> Unit) = source.onClose(listener)
    override fun close() = source.close()
}
