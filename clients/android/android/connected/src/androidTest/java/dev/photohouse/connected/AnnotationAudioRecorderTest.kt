package dev.photohouse.connected

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class AnnotationAudioRecorderTest {
    @Test fun syntheticPcmBecomesContractSizedMonoWav() {
        val wav = annotationWavFromPcm(ByteArray(16_000), 16_000)
        assertEquals(16_044, wav.size)
        assertEquals("RIFF", String(wav, 0, 4, Charsets.US_ASCII))
        assertEquals("WAVE", String(wav, 8, 4, Charsets.US_ASCII))
        val fields = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(16_000, fields.getInt(24))
        assertEquals(1, fields.getShort(22).toInt())
        assertEquals(16_000, fields.getInt(40))
    }

    @Test fun syntheticPcmRejectsOutOfContractDurations() {
        assertThrows(IllegalArgumentException::class.java) { annotationWavFromPcm(ByteArray(15_998), 16_000) }
        assertThrows(IllegalArgumentException::class.java) { annotationWavFromPcm(ByteArray(16_000 * 2 * 60 + 2), 16_000) }
    }
}
