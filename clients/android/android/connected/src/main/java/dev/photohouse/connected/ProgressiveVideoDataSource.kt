package dev.photohouse.connected

import android.net.Uri
import android.os.SystemClock
import androidx.media3.common.C
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.BaseDataSource
import androidx.media3.datasource.DataSpec
import java.io.IOException

/** A sequential view over the existing authenticated, bounded range reader.
 * The placeholder URI never reaches a network stack; no URL or bearer reaches Media3.
 * close() releases only this cursor: the owner cancels the reader on viewer exit.
 */
@androidx.annotation.OptIn(UnstableApi::class)
internal class ProgressiveVideoDataSource(private val reader: PhonePlaybackSource) : BaseDataSource(true) {
    companion object { val PRIVATE_URI: Uri = Uri.parse("photohouse-memory:///video") }
    private var opened = false
    private var position = 0L
    private var remaining = 0L
    private var reads = 0L
    private var delivered = 0L
    private val startedAt = SystemClock.elapsedRealtime()

    override fun open(dataSpec: DataSpec): Long {
        if (opened || dataSpec.uri != PRIVATE_URI || dataSpec.httpMethod != DataSpec.HTTP_METHOD_GET ||
            dataSpec.httpBody != null) throw IOException("Invalid video request")
        // Extractor hints (for example Icy-MetaData) are ignored, never forwarded.
        transferInitializing(dataSpec)
        val size = reader.size() // Rechecks reader lifetime even when reopening for a seek.
        if (dataSpec.position > size) throw IOException("Invalid video position")
        position = dataSpec.position
        remaining = size - position
        if (dataSpec.length != C.LENGTH_UNSET.toLong()) remaining = minOf(remaining, dataSpec.length)
        opened = true
        transferStarted(dataSpec)
        return remaining
    }

    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        if (!opened) throw IOException("Video source closed")
        require(offset >= 0 && length >= 0 && offset <= buffer.size && length <= buffer.size - offset)
        if (length == 0) return 0
        if (remaining == 0L) return C.RESULT_END_OF_INPUT
        val start = SystemClock.elapsedRealtime()
        val count = reader.readAt(position, buffer, offset, minOf(remaining, length.toLong()).toInt())
        if (count <= 0 || count > length || count > remaining) throw IOException("Incomplete video read")
        position += count; remaining -= count; delivered += count; reads++
        bytesTransferred(count)
        // Numeric diagnostics only, never asset identifiers, endpoints or credentials.
        if (BuildConfig.DEBUG && (reads <= 8 || reads % 64L == 0L)) android.util.Log.d("PhotoHouseVideoIO",
            "calls=$reads bytes=$delivered elapsedMs=${SystemClock.elapsedRealtime() - startedAt} requested=$length readMs=${SystemClock.elapsedRealtime() - start}")
        return count
    }

    override fun getUri(): Uri? = if (opened) PRIVATE_URI else null
    override fun close() {
        if (opened) { opened = false; remaining = 0; transferEnded() }
    }
}
