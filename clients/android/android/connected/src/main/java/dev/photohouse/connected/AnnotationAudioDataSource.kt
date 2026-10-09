package dev.photohouse.connected

import android.net.Uri
import androidx.media3.common.C
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.DataSpec
import androidx.media3.datasource.TransferListener
import androidx.media3.common.util.UnstableApi
import dev.photohouse.connected.core.ProtectedAnnotationAudio
import java.io.IOException

/** Media3 reads only the in-memory bytes fetched by the authenticated API adapter. */
@androidx.annotation.OptIn(UnstableApi::class)
internal class AnnotationAudioDataSource(private val audio: ProtectedAnnotationAudio) : DataSource {
    private var uri: Uri? = null
    private var position = 0
    private var endPosition = 0

    override fun addTransferListener(transferListener: TransferListener) = Unit

    override fun open(dataSpec: DataSpec): Long {
        if (audio.isClosed) throw IOException("Audio is closed")
        if (dataSpec.uri.scheme != "photohouse-audio" || dataSpec.uri.host !in setOf("original", "assistant-speech"))
            throw IOException("Invalid audio source")
        val length = audio.size
        if (dataSpec.position !in 0L..length.toLong() ||
            dataSpec.length != C.LENGTH_UNSET.toLong() && dataSpec.length < 0)
            throw IOException("Invalid audio position")
        position = dataSpec.position.toInt()
        endPosition = if (dataSpec.length == C.LENGTH_UNSET.toLong()) length else
            position + minOf((length - position).toLong(), dataSpec.length).toInt()
        uri = dataSpec.uri
        return (endPosition - position).toLong()
    }

    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        if (length == 0) return 0
        if (position >= endPosition) return C.RESULT_END_OF_INPUT
        val count = audio.readAt(position, buffer, offset, minOf(length, endPosition - position))
        if (count <= 0) throw IOException("Audio is unavailable")
        position += count
        return count
    }

    override fun getUri(): Uri? = uri

    override fun close() { uri = null; position = 0; endPosition = 0 }

    internal class Factory(private val audio: ProtectedAnnotationAudio) : DataSource.Factory {
        override fun createDataSource(): DataSource = AnnotationAudioDataSource(audio)
    }
}
