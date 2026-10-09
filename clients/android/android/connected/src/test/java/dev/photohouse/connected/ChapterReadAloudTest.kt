package dev.photohouse.connected

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChapterReadAloudTest {
    @Test fun chunksRespectUnicodeCodePointBoundAndPreserveText() {
        val source = ("回忆🙂。 ").repeat(100)
        val chunks = narrationChunks(source, maxCodePoints = 17)
        assertTrue(chunks.size > 1)
        assertTrue(chunks.all { it.codePointCount(0, it.length) <= 17 })
        assertEquals(source.filterNot { it.isWhitespace() }, chunks.joinToString("").filterNot { it.isWhitespace() })
    }

    @Test fun audioLeasePreemptsOnlyCurrentOwnerAndStaleReleaseIsSafe() {
        val coordinator = ReaderAudioCoordinator()
        var firstStopped = 0
        val first = coordinator.acquire(ReaderAudioKind.SPEECH) { firstStopped++ }!!
        assertTrue(coordinator.isOwned(first))
        val second = coordinator.acquire(ReaderAudioKind.PLAYBACK) { }!!
        assertEquals(1, firstStopped)
        assertFalse(coordinator.isOwned(first))
        assertTrue(coordinator.isOwned(second))
        coordinator.release(first)
        assertTrue(coordinator.isOwned(second))
        coordinator.release(second)
        assertFalse(coordinator.isOwned(second))
    }

    @Test fun narrationAndPlaybackCannotPreemptRecording() {
        val coordinator = ReaderAudioCoordinator()
        var stopped = 0
        val capture = coordinator.acquire(ReaderAudioKind.RECORDING) { stopped++ }!!
        assertEquals(null, coordinator.acquire(ReaderAudioKind.SPEECH) { })
        assertEquals(null, coordinator.acquire(ReaderAudioKind.PLAYBACK) { })
        assertEquals(0, stopped)
        assertTrue(coordinator.isOwned(capture))
    }

    @Test fun textCapsRejectUnboundedInputAndChunkUtf8IsBounded() {
        val chunks = narrationChunks("🙂汉".repeat(100), maxCodePoints = 10, maxChunkBytes = 16)
        assertTrue(chunks.all { it.codePointCount(0, it.length) <= 10 && it.toByteArray().size <= 16 })
        assertTrue(narrationChunks("x".repeat(6000) + "t".repeat(160)).isNotEmpty())
        assertTrue(runCatching { narrationChunks("x".repeat(6401)) }.isFailure)
    }
}
