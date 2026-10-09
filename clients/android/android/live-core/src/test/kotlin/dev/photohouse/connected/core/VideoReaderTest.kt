package dev.photohouse.connected.core

import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class VideoReaderTest {
    @Test fun largeFileSeeksAndEofKeepAllocationsBoundedAndReauthorizeRepeatReads() {
        val total = 8193114694L
        val calls = mutableListOf<Pair<Long, Int>>()
        var deny = false
        val reader = VideoReader({ start, count ->
            calls += start to count
            if (deny) throw ApiFailure(FailureKind.HTTP, 403)
            VideoChunk(start, total, ByteArray(minOf(count.toLong(), total - start).toInt()) { ((start + it) % 251).toByte() })
        }, Long.MAX_VALUE, { 0 }) { }
        reader.use {
            val buffer = ByteArray(16) { 77 }
            assertEquals(16, it.readAt(4294967296L, buffer, 0, 16))
            assertEquals((4294967296L % 251).toByte(), buffer[0])
            assertEquals(4, it.readAt(total - 4, buffer, 3, 12))
            assertEquals(-1, it.readAt(total, buffer, 0, 1))
            assertEquals(3, calls.size)
            deny = true; buffer.fill(77)
            assertTrue(runCatching { it.readAt(4294967296L, buffer, 0, 16) }.isFailure)
            assertArrayEquals(ByteArray(16) { 77 }, buffer)
            assertTrue(it.isClosed)
            assertEquals(4, calls.size)
        }
    }
    @Test fun randomReadsAreBoundedAndEofAndZeroLengthDoNotFetch() {
        val calls = mutableListOf<Pair<Long, Int>>()
        val reader = VideoReader({ start, length -> calls += start to length; VideoChunk(start, 800000, ByteArray(length) { ((start + it) % 251).toByte() }) }, Long.MAX_VALUE, { 0 }) { fail("Unexpected failure") }
        reader.use {
            assertEquals(0, it.readAt(0, byteArrayOf(), 0, 0)); assertTrue(calls.isEmpty())
            assertEquals(800000L, it.size())
            val buffer = ByteArray(400000)
            assertEquals(262144, it.readAt(0, buffer, 0, buffer.size))
            assertEquals(5, it.readAt(799995, buffer, 10, 20))
            assertEquals((799995 % 251).toByte(), buffer[10])
            val before = calls.size; assertEquals(-1, it.readAt(800000, buffer, 0, 1)); assertEquals(before, calls.size)
            assertEquals(20, it.readAt(123, buffer, 0, 20)); assertEquals(20, it.readAt(123, buffer, 0, 20))
            assertEquals(5, calls.size) // Repeated ranges reauthorize, no chunk cache.
        }
        assertTrue(reader.isClosed)
        assertTrue(runCatching { reader.size() }.exceptionOrNull() is IOException)
    }
    @Test fun readAheadServesOnlyContiguousUnconsumedBytesAndRefetchesConsumedRanges() {
        val calls = mutableListOf<Pair<Long, Int>>()
        val reader = VideoReader({ start, length ->
            calls += start to length
            VideoChunk(start, 800000, ByteArray(length) { ((start + it) % 251).toByte() })
        }, Long.MAX_VALUE, { 0 }, initialSize = 800000, readAhead = true) { fail("Unexpected failure") }
        reader.use {
            val buffer = ByteArray(2048)
            repeat(128) { index ->
                val position = index * buffer.size.toLong()
                assertEquals(buffer.size, it.readAt(position, buffer, 0, buffer.size))
                assertEquals((position % 251).toByte(), buffer[0])
                assertEquals(((position + buffer.lastIndex) % 251).toByte(), buffer.last())
            }
            assertEquals(listOf(0L to HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT), calls)
            assertEquals(buffer.size, it.readAt(262144, buffer, 0, buffer.size))
            assertEquals(listOf(0L to HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT, 262144L to HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT), calls)
            assertEquals(8, it.readAt(0, buffer, 0, 8))
            assertEquals(0, buffer[0].toInt())
            assertEquals(listOf(0L to HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT, 262144L to HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT, 0L to HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT), calls)
        }
    }
    @Test fun readAheadCloseAndEofSeekEraseUnconsumedBytes() {
        for (seekEof in listOf(false, true)) {
            val owned = mutableListOf<ByteArray>()
            val reader = VideoReader({ start, length ->
                val bytes = ByteArray(length) { 7 }; owned += bytes
                VideoChunk(start, 1000, bytes)
            }, Long.MAX_VALUE, { 0 }, initialSize = 1000, readAhead = true) { fail("Unexpected failure") }
            val target = ByteArray(8)
            assertEquals(8, reader.readAt(0, target, 0, 8))
            assertTrue(owned.single().take(8).all { it == 0.toByte() })
            assertEquals(7.toByte(), owned.single()[8])
            if (seekEof) {
                assertEquals(-1, reader.readAt(1000, target, 0, 8))
                assertEquals(1, owned.size)
                assertTrue(owned.first().all { it == 0.toByte() })
                assertEquals(8, reader.readAt(8, target, 0, 8))
                assertEquals(2, owned.size) // Returning after EOF is a fresh request.
            }
            reader.close()
            assertTrue(owned.all { bytes -> bytes.all { it == 0.toByte() } })
        }
    }

    @Test fun readAheadGapDiscardsSuffixAndFreshDenialClosesReader() {
        var deny = false
        val calls = mutableListOf<Pair<Long, Int>>()
        val reader = VideoReader({ start, length ->
            calls += start to length
            if (deny) throw ApiFailure(FailureKind.HTTP, 403)
            VideoChunk(start, 800000, ByteArray(length))
        }, Long.MAX_VALUE, { 0 }, initialSize = 800000, readAhead = true) { }
        reader.use {
            val buffer = ByteArray(4)
            assertEquals(4, it.readAt(0, buffer, 0, 4))
            deny = true
            assertTrue(runCatching { it.readAt(100, buffer, 0, 4) }.isFailure)
            assertTrue(it.isClosed)
            assertEquals(listOf(0L to HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT, 100L to HttpsPhotoHouseApi.VIDEO_CHUNK_LIMIT), calls)
        }
    }
    @Test fun readAheadCloseAndExpiryClearSuffixAndNearEofNeverOverfetches() {
        var clock = 0L
        val returned = mutableListOf<ByteArray>()
        val reader = VideoReader({ start, length -> ByteArray(length) { 7 }.also { returned += it }.let { VideoChunk(start, 1000, it) } }, 1000, { clock }, initialSize = 1000, readAhead = true) { }
        val buffer = ByteArray(200)
        assertEquals(100, reader.readAt(900, buffer, 0, buffer.size))
        assertEquals(7.toByte(), buffer[0])
        assertEquals(1, returned.size)
        assertEquals(100, returned.single().size)
        reader.close()
        assertTrue(returned.single().all { it == 0.toByte() })

        val expiringBytes = mutableListOf<ByteArray>()
        val expiring = VideoReader({ start, length -> ByteArray(length) { 9 }.also { expiringBytes += it }.let { VideoChunk(start, 1000, it) } }, 1000, { clock }, initialSize = 1000, readAhead = true) { }
        assertEquals(10, expiring.readAt(0, buffer, 0, 10))
        assertTrue(expiringBytes.single().any { it != 0.toByte() })
        clock = 1000
        assertTrue(runCatching { expiring.readAt(10, buffer, 0, 10) }.isFailure)
        assertTrue(expiringBytes.single().all { it == 0.toByte() })
    }

    @Test fun enabledTransientReadRetriesOneOfflineFetchWithTheSameRange() {
        val calls = mutableListOf<Pair<Long, Int>>()
        var failures = 0
        val reader = VideoReader({ start, length ->
            calls += start to length
            if (failures++ == 0) throw ApiFailure(FailureKind.OFFLINE)
            VideoChunk(start, 1000, ByteArray(length) { 7 })
        }, Long.MAX_VALUE, { 0 }, initialSize = 1000, retryTransientRead = true) { fail("Unexpected failure") }
        reader.use {
            val target = ByteArray(16)
            assertEquals(16, it.readAt(123, target, 0, target.size))
            assertEquals(listOf(123L to 16, 123L to 16), calls)
            assertTrue(target.all { value -> value == 7.toByte() })
        }
    }

    @Test fun enabledTransientReadStopsAfterOneOfflineRetry() {
        var calls = 0
        val reader = VideoReader({ _, _ ->
            calls++
            throw ApiFailure(FailureKind.OFFLINE)
        }, Long.MAX_VALUE, { 0 }, initialSize = 1000, retryTransientRead = true) { }
        assertTrue(runCatching { reader.readAt(0, ByteArray(4), 0, 4) }.isFailure)
        assertEquals(2, calls)
        assertTrue(reader.isClosed)
    }

    @Test fun transientRetryExcludesTlsHttpAndInvalidPayload() {
        val scenarios = listOf<suspend (Long, Int) -> VideoChunk>(
            { _, _ -> throw ApiFailure(FailureKind.TLS) },
            { _, _ -> throw ApiFailure(FailureKind.HTTP, 503) },
            { _, _ -> throw ApiFailure(FailureKind.HTTP, 401) },
            { _, _ -> throw ApiFailure(FailureKind.HTTP, 403) },
            { _, _ -> throw ApiFailure(FailureKind.HTTP, 429) },
            { _, _ -> throw ApiFailure(FailureKind.INVALID_RESPONSE) },
            { start, _ -> VideoChunk(start + 1, 1000, ByteArray(4)) },
        )
        scenarios.forEach { fetch ->
            var calls = 0
            val reader = VideoReader({ start, length -> calls++; fetch(start, length) }, Long.MAX_VALUE, { 0 }, initialSize = 1000, retryTransientRead = true) { }
            assertTrue(runCatching { reader.readAt(0, ByteArray(4), 0, 4) }.isFailure)
            assertEquals(1, calls)
        }
    }

    @Test fun cancellationDuringTransientRetryDelayDoesNotIssueSecondFetch() = runBlocking {
        val firstFailure = CompletableDeferred<Unit>()
        var calls = 0
        val reader = VideoReader({ _, _ ->
            calls++
            firstFailure.complete(Unit)
            throw ApiFailure(FailureKind.OFFLINE)
        }, Long.MAX_VALUE, { 0 }, initialSize = 1000, retryTransientRead = true) { fail("Cancellation is not a read failure") }
        val worker = async(Dispatchers.IO) { runCatching { reader.readAt(0, ByteArray(4), 0, 4) }.exceptionOrNull() }
        firstFailure.await()
        reader.close()
        assertTrue(withTimeout(2000) { worker.await() } is IOException)
        assertEquals(1, calls)
    }

    @Test fun expiryBeforeTransientRetryPreventsSecondFetch() {
        var clock = 0L
        var calls = 0
        val reader = VideoReader({ _, _ ->
            calls++
            clock = 1000
            throw ApiFailure(FailureKind.OFFLINE)
        }, 1000, { clock }, initialSize = 1000, retryTransientRead = true) { }
        assertTrue(runCatching { reader.readAt(0, ByteArray(4), 0, 4) }.isFailure)
        assertEquals(1, calls)
        assertEquals(VideoReadFailure(FailureKind.HTTP, 401), reader.lastFailure)
    }

    @Test fun interruptedSeekCancelsOnlyTheFetchAndNextReadSucceeds() {
        val entered = CountDownLatch(1); val cancelled = CountDownLatch(1)
        val calls = AtomicInteger(); val failures = AtomicInteger()
        val reader = VideoReader({ start, length ->
            if (calls.incrementAndGet() == 1) {
                entered.countDown()
                try { awaitCancellation() } finally { cancelled.countDown() }
            }
            VideoChunk(start, 1000, ByteArray(length) { 6 })
        }, Long.MAX_VALUE, { 0 }, initialSize = 1000, readAhead = true, retryTransientRead = true) { failures.incrementAndGet() }
        val thrown = java.util.concurrent.atomic.AtomicReference<Throwable?>()
        val worker = Thread { try { reader.readAt(0, ByteArray(4), 0, 4) } catch (e: Throwable) { thrown.set(e) } }
        worker.start(); assertTrue(entered.await(3, TimeUnit.SECONDS)); worker.interrupt(); worker.join(3000)
        assertFalse(worker.isAlive); assertTrue(thrown.get() is java.io.InterruptedIOException)
        assertTrue(cancelled.await(3, TimeUnit.SECONDS)); assertFalse(reader.isClosed)
        val target = ByteArray(4); assertEquals(4, reader.readAt(500, target, 0, 4))
        assertArrayEquals(ByteArray(4) { 6 }, target); assertEquals(0, failures.get())
        reader.close()
    }

    @Test fun closeCancelsInflightReadAndNeverCopiesLateBytes() = runBlocking {
        val entered = CountDownLatch(1); val cancelled = CountDownLatch(1); val errors = AtomicInteger()
        val reader = VideoReader({ _, _ -> entered.countDown(); try { awaitCancellation() } finally { cancelled.countDown() } }, Long.MAX_VALUE, { 0 }, initialSize = 1000, readAhead = true) { errors.incrementAndGet() }
        val buffer = ByteArray(10) { 9 }
        val worker = async(Dispatchers.IO) { runCatching { reader.readAt(0, buffer, 0, 10) }.exceptionOrNull() }
        assertTrue(entered.await(5, TimeUnit.SECONDS))
        reader.close(); reader.close()
        assertTrue(withTimeout(2000) { worker.await() } is IOException)
        assertTrue(cancelled.await(2, TimeUnit.SECONDS)); assertEquals(0, errors.get())
        assertArrayEquals(ByteArray(10) { 9 }, buffer)
    }

    @Test fun changedSizeMalformedChunkExpiryAndDenialFailClosedOnlyOnce() {
        for (scenario in listOf("size", "bytes", "expiry", "denial")) {
            var clock = 0L; var count = 0; val failures = mutableListOf<Exception>(); var closes = 0
            val reader = VideoReader({ start, length ->
                count++
                if (count > 1 && scenario == "denial") throw ApiFailure(FailureKind.HTTP, 401)
                VideoChunk(start, if (count > 1 && scenario == "size") 99 else 100,
                    ByteArray(if (count > 1 && scenario == "bytes") length - 1 else length))
            }, 1000, { clock }) { failures += it }
            reader.onClose { closes++ }; assertEquals(100L, reader.size())
            if (scenario == "expiry") clock = 1000
            assertTrue(runCatching { reader.readAt(0, ByteArray(10), 0, 10) }.isFailure)
            assertTrue(reader.isClosed); assertEquals(1, failures.size); assertEquals(1, closes)
            runCatching { reader.size() }; assertEquals(1, failures.size)
            reader.onClose { closes++ }; assertEquals(2, closes)
        }
    }
}
