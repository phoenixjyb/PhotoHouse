package dev.photohouse.home

import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class VideoReadRecoveryTest {
    @Test fun twoInterruptionsRecoverWithBoundedBackoff() = runTest {
        var attempts = 0
        val bytes = readVideoRangeWithRecovery {
            if (++attempts < 3) throw HomeFailure(HomeError.OFFLINE)
            byteArrayOf(1, 2, 3)
        }
        assertArrayEquals(byteArrayOf(1, 2, 3), bytes)
        assertEquals(3, attempts); assertEquals(1000L, currentTime)
    }
    @Test fun persistentOfflineStopsAfterThreeAttempts() = runTest {
        var attempts = 0
        try { readVideoRangeWithRecovery { attempts++; throw HomeFailure(HomeError.OFFLINE) }; fail() }
        catch (e: HomeFailure) { assertEquals(HomeError.OFFLINE, e.kind) }
        assertEquals(3, attempts); assertEquals(1000L, currentTime)
    }
    @Test fun refusalIntegrityTlsAndAvailabilityErrorsNeverRetry() = runTest {
        for (kind in HomeError.entries.filter { it != HomeError.OFFLINE }) {
            var attempts = 0
            try { readVideoRangeWithRecovery { attempts++; throw HomeFailure(kind) }; fail() }
            catch (e: HomeFailure) { assertEquals(kind, e.kind) }
            assertEquals(1, attempts)
        }
        var attempts = 0
        try { readVideoRangeWithRecovery { attempts++; throw IOException("unclassified") }; fail() }
        catch (_: IOException) { }
        assertEquals(1, attempts); assertEquals(0L, currentTime)
    }
    @Test fun slowAttemptsShareOneTwentySecondDeadlineAndCancelLoader() = runTest {
        var attempts = 0; var cancelled = false
        try {
            readVideoRangeWithRecovery {
                if (++attempts == 1) { delay(19000); throw HomeFailure(HomeError.OFFLINE) }
                try { awaitCancellation() } finally { cancelled = true }
            }
            fail()
        } catch (e: HomeFailure) { assertEquals(HomeError.OFFLINE, e.kind) }
        assertEquals(2, attempts); assertEquals(20000L, currentTime); assertTrue(cancelled)
    }
    @Test fun closingDuringBackoffDoesNotStartAnotherRequest() = runTest {
        var attempts = 0
        val job = launch { readVideoRangeWithRecovery { attempts++; throw HomeFailure(HomeError.OFFLINE) } }
        runCurrent(); assertEquals(1, attempts)
        job.cancelAndJoin(); advanceUntilIdle()
        assertEquals(1, attempts)
    }
    @Test fun callerTimeoutRemainsCancellation() = runTest {
        var cancelled = false
        val result = withTimeoutOrNull(100) {
            readVideoRangeWithRecovery { try { awaitCancellation() } finally { cancelled = true } }
        }
        assertNull(result); assertTrue(cancelled); assertEquals(100L, currentTime)
    }
}
