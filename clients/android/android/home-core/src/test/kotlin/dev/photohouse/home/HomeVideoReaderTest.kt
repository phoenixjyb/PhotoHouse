package dev.photohouse.home

import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class HomeVideoReaderTest {
    @Test fun tinyHeaderProbesReuseOneBoundedWindowAndCloseInvalidatesIt() {
        var requests = 0
        val reader = HomeVideoReader(1000000, 65536, { start, count ->
            requests++; assertTrue(count <= 65536)
            ByteArray(count) { ((start + it) % 251).toByte() }
        }, { fail("Unexpected failure") })
        val buffer = ByteArray(8)
        repeat(1000) { position ->
            assertEquals(8, reader.readAt(position.toLong(), buffer, 0, 8))
            assertEquals((position % 251).toByte(), buffer[0])
        }
        assertEquals(1, requests)
        reader.readAt(900000, buffer, 0, 8)
        assertEquals(2, requests)
        reader.readAt(0, buffer, 0, 8)
        assertEquals(3, requests) // Only one window is retained after a seek.
        reader.close()
        assertThrows(IOException::class.java) { reader.readAt(0, buffer, 0, 8) }
        assertEquals(3, requests)
    }
    @Test fun multiGigabyteMovieSupportsTailAndBackwardReadsWithSmallBuffers() {
        val total = 8193114694L
        val requests = mutableListOf<Pair<Long, Int>>()
        val reader = HomeVideoReader(total, CatalogWire.READ_BYTES, { start, count ->
            requests += start to count
            ByteArray(count) { ((start + it) % 251).toByte() }
        }, { fail("Unexpected failure") })
        reader.use {
            val buffer = ByteArray(32) { 77 }
            assertEquals(total, it.size())
            assertEquals(32, it.readAt(4294967296L, buffer, 0, 32))
            assertEquals((4294967296L % 251).toByte(), buffer[0])
            assertEquals(4, it.readAt(total - 4, buffer, 2, 16))
            assertEquals(((total - 4) % 251).toByte(), buffer[2])
            assertEquals(16, it.readAt(0, buffer, 0, 16))
            assertEquals(-1, it.readAt(total, buffer, 0, 1))
            assertEquals(listOf(4294967296L to CatalogWire.READ_BYTES, total - 4 to 4, 0L to CatalogWire.READ_BYTES), requests)
        }
    }
    @Test fun boundedRandomReadsPreserveOffsetsAndReturnEofWithoutFetching() {
        val reads = mutableListOf<Pair<Long, Int>>()
        val reader = HomeVideoReader(20, 4, { start, size ->
            reads += start to size; ByteArray(size) { (start + it).toByte() }
        }, { fail("Unexpected failure") })
        val buffer = ByteArray(12) { 99 }
        assertEquals(20L, reader.size())
        assertEquals(4, reader.readAt(5, buffer, 2, 10))
        assertArrayEquals(byteArrayOf(99, 99, 5, 6, 7, 8, 99, 99, 99, 99, 99, 99), buffer)
        assertEquals(2, reader.readAt(18, buffer, 0, 12))
        assertEquals(-1, reader.readAt(Long.MAX_VALUE, buffer, 0, 1))
        assertEquals(0, reader.readAt(0, buffer, 12, 0))
        assertEquals(listOf(5L to 4, 18L to 2), reads)
        reader.close()
    }
    @Test fun closeCancelsAnInflightReadWithoutCopyingOrReportingAnError() {
        val entered = CountDownLatch(1); val cancelled = CountDownLatch(1)
        val failures = AtomicInteger()
        val reader = HomeVideoReader(20, 4, { _, _ ->
            entered.countDown()
            try { awaitCancellation() } finally { cancelled.countDown() }
        }, { failures.incrementAndGet() })
        val worker = Executors.newSingleThreadExecutor()
        try {
            val buffer = ByteArray(4) { 77 }
            val result = worker.submit<Boolean> { try { reader.readAt(0, buffer, 0, 4); false } catch (_: IOException) { true } }
            assertTrue(entered.await(3, TimeUnit.SECONDS))
            reader.close()
            assertTrue(result.get(3, TimeUnit.SECONDS)); assertTrue(cancelled.await(3, TimeUnit.SECONDS))
            assertArrayEquals(ByteArray(4) { 77 }, buffer); assertEquals(0, failures.get())
        } finally { reader.close(); worker.shutdownNow() }
    }

    @Test fun interruptedSeekCancelsOnlyTheFetchAndNextReadSucceeds() {
        val entered = CountDownLatch(1); val cancelled = CountDownLatch(1)
        val calls = AtomicInteger(); val failures = AtomicInteger()
        val reader = HomeVideoReader(1000, 256, { _, length ->
            if (calls.incrementAndGet() == 1) {
                entered.countDown()
                try { awaitCancellation() } finally { cancelled.countDown() }
            }
            ByteArray(length) { 6 }
        }, { failures.incrementAndGet() })
        val thrown = java.util.concurrent.atomic.AtomicReference<Throwable?>()
        val worker = Thread { try { reader.readAt(0, ByteArray(4), 0, 4) } catch (e: Throwable) { thrown.set(e) } }
        worker.start(); assertTrue(entered.await(3, TimeUnit.SECONDS)); worker.interrupt(); worker.join(3000)
        assertFalse(worker.isAlive); assertTrue(thrown.get() is java.io.InterruptedIOException)
        assertTrue(cancelled.await(3, TimeUnit.SECONDS)); assertFalse(reader.isClosed)
        val target = ByteArray(4); assertEquals(4, reader.readAt(500, target, 0, 4))
        assertArrayEquals(ByteArray(4) { 6 }, target); assertEquals(0, failures.get())
        reader.close()
    }

    @Test fun shortAndOversizedChunksCloseAndReportOnlyOnce() {
        for (returned in listOf(3, 5)) {
            var failures = 0; var closed = 0
            val reader = HomeVideoReader(20, 4, { _, _ -> ByteArray(returned) }, { failures++ })
            reader.onClose { closed++ }
            val buffer = ByteArray(4) { 55 }
            repeat(2) { assertThrows(IOException::class.java) { reader.readAt(0, buffer, 0, 4) } }
            reader.close(); reader.onClose { closed++ }
            assertEquals(1, failures); assertEquals(2, closed)
            assertTrue(reader.isClosed); assertArrayEquals(ByteArray(4) { 55 }, buffer)
        }
    }
    @Test fun concurrentNativeReadsAreSerialized() {
        val active = AtomicInteger(); val maxActive = AtomicInteger()
        val reader = HomeVideoReader(100, 4, { _, size ->
            maxActive.accumulateAndGet(active.incrementAndGet(), ::maxOf)
            delay(25); active.decrementAndGet(); ByteArray(size)
        }, { fail("Unexpected failure") })
        val workers = Executors.newFixedThreadPool(2)
        try {
            val results = (0..1).map { workers.submit<Int> { reader.readAt(it.toLong(), ByteArray(4), 0, 4) } }
            results.forEach { assertEquals(4, it.get(3, TimeUnit.SECONDS)) }
            assertEquals(1, maxActive.get())
        } finally { reader.close(); workers.shutdownNow() }
    }
    @Test fun invalidBufferArgumentsNeverFetchAndCloseTheSource() {
        var reads = 0
        val reader = HomeVideoReader(20, 4, { _, size -> reads++; ByteArray(size) }, {})
        assertThrows(IOException::class.java) { reader.readAt(0, ByteArray(4), Int.MAX_VALUE, 4) }
        assertEquals(0, reads); assertTrue(reader.isClosed)
        assertThrows(IOException::class.java) { reader.size() }
        assertThrows(IllegalArgumentException::class.java) { HomeVideoReader(1, 262145, { _, _ -> byteArrayOf() }, {}) }
    }
    @Test fun transportFailureReleasesAndRedactsTheNativeError() {
        var failures = 0
        val reader = HomeVideoReader(1, 1, { _, _ -> throw IOException("private transport detail") }, { failures++ })
        val error = assertThrows(IOException::class.java) { reader.readAt(0, ByteArray(1), 0, 1) }
        assertEquals("Video read unavailable", error.message); assertNull(error.cause)
        assertEquals(1, failures); assertTrue(reader.isClosed)
    }
}
