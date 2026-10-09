package dev.photohouse.connected.core

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProtectedAnnotationAudioTest {
    @Test fun closeWipesMemoryBytesAndNotifiesPlaybackOwner() {
        val source = byteArrayOf(1, 2, 3, 4)
        val audio = ProtectedAnnotationAudio(source)
        var closed = false
        audio.onClose { closed = true }
        val copied = ByteArray(4)
        assertEquals(4, audio.readAt(0, copied, 0, copied.size))
        assertArrayEquals(byteArrayOf(1, 2, 3, 4), copied)

        audio.close()

        assertTrue(closed)
        assertTrue(audio.isClosed)
        assertEquals(0, audio.size)
        assertArrayEquals(ByteArray(4), source)
        assertFalse(audio.toString().contains("1, 2, 3"))
    }
}
