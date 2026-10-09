package dev.photohouse.connected

import android.net.Uri
import androidx.media3.common.C
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DataSpec
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.IOException

@RunWith(AndroidJUnit4::class)
@androidx.annotation.OptIn(UnstableApi::class)
class ProgressiveVideoDataSourceTest {
    private class Source : PhonePlaybackSource {
        val bytes = ByteArray(100) { it.toByte() }
        val positions = mutableListOf<Long>()
        var closed = false
        var fail = false
        override fun size(): Long { if (closed) throw IOException(); return bytes.size.toLong() }
        override fun readAt(position: Long, buffer: ByteArray, offset: Int, size: Int): Int {
            if (closed || fail) throw IOException()
            positions += position
            val n = minOf(7, size, bytes.size - position.toInt()) // Partial reads are normal.
            bytes.copyInto(buffer, offset, position.toInt(), position.toInt() + n)
            return n
        }
        override fun onClose(listener: () -> Unit) { }
        override fun close() { closed = true }
    }
    private fun spec(position: Long = 0, length: Long = C.LENGTH_UNSET.toLong()) = DataSpec.Builder()
        .setUri(ProgressiveVideoDataSource.PRIVATE_URI).setPosition(position).setLength(length).build()

    @Test fun partialReadsAdvanceAndRespectRequestedWindow() {
        val source = Source(); val data = ProgressiveVideoDataSource(source)
        assertEquals(12L, data.open(spec(20, 12).buildUpon()
            .setHttpRequestHeaders(mapOf("Icy-MetaData" to "1")).build()))
        val output = ByteArray(20) { -1 }
        assertEquals(7, data.read(output, 2, 18))
        assertEquals(5, data.read(output, 9, 11))
        assertArrayEquals(source.bytes.copyOfRange(20, 32), output.copyOfRange(2, 14))
        assertEquals(C.RESULT_END_OF_INPUT, data.read(output, 0, 20))
        assertEquals(0, data.read(output, 0, 0))
        assertEquals(listOf(20L, 27L), source.positions)
    }
    @Test fun seekReopensCursorWithoutClosingOwnerAndOwnerCloseBlocksRead() {
        val source = Source(); val data = ProgressiveVideoDataSource(source)
        data.open(spec()); data.read(ByteArray(5), 0, 5); data.close()
        assertFalse(source.closed); assertNull(data.uri)
        assertEquals(10L, data.open(spec(90)))
        assertEquals(5, data.read(ByteArray(5), 0, 5))
        assertEquals(listOf(0L, 90L), source.positions)
        source.close()
        assertThrows(IOException::class.java) { data.read(ByteArray(1), 0, 1) }
        data.close()
        assertThrows(IOException::class.java) { data.open(spec()) }
    }
    @Test fun invalidRequestsNeverReachReader() {
        val source = Source(); val data = ProgressiveVideoDataSource(source)
        assertThrows(IOException::class.java) { data.open(DataSpec.Builder().setUri(Uri.parse("https://example.invalid/video")).build()) }
        assertThrows(IOException::class.java) { data.open(DataSpec.Builder().setUri(ProgressiveVideoDataSource.PRIVATE_URI).setHttpMethod(DataSpec.HTTP_METHOD_POST).build()) }
        assertThrows(IOException::class.java) { data.open(spec(101)) }
        assertThrows(IOException::class.java) { data.read(ByteArray(1), 0, 1) }
        assertTrue(source.positions.isEmpty())
    }
    @Test fun sourceFailurePropagatesWithoutRetryOrFallback() {
        val source = Source(); val data = ProgressiveVideoDataSource(source)
        data.open(spec()); source.fail = true
        assertThrows(IOException::class.java) { data.read(ByteArray(1), 0, 1) }
        assertTrue(source.positions.isEmpty())
    }
}
