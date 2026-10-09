package dev.photohouse.home

import dev.photohouse.home.PlaybackWaitDeadline.Phase.*
import org.junit.Assert.*
import org.junit.Test

class PlaybackWaitDeadlineTest {
    @Test fun continuousPhaseChangesCannotExtendWaitAndTimeoutFiresOnce() {
        val guard = PlaybackWaitDeadline(1000)
        assertNull(guard.update(PREPARING, 100))
        assertNull(guard.update(BUFFERING, 700))
        assertNull(guard.update(SEEKING, 1099))
        assertEquals(SEEKING, guard.update(SEEKING, 1100))
        assertNull(guard.update(BUFFERING, 5000))
    }
    @Test fun recoveryPauseAndEndClearTheDeadlineAndNextWaitStartsFresh() {
        val guard = PlaybackWaitDeadline(1000)
        guard.update(BUFFERING, 0)
        assertNull(guard.update(null, 900))
        assertNull(guard.update(null, 100000))
        assertNull(guard.update(SEEKING, 100001))
        assertNull(guard.update(SEEKING, 101000))
        assertEquals(SEEKING, guard.update(SEEKING, 101001))
        guard.reset()
        assertNull(guard.update(PREPARING, 200000))
    }
    @Test fun clockRegressionDoesNotProduceImmediateTimeout() {
        val guard = PlaybackWaitDeadline(1000)
        guard.update(PREPARING, 1000)
        assertNull(guard.update(PREPARING, 1))
        assertEquals(PREPARING, guard.update(PREPARING, 2000))
    }
}
