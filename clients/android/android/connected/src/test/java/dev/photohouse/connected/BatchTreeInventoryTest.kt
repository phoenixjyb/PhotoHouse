package dev.photohouse.connected

import dev.photohouse.connected.core.BatchUploadSource
import dev.photohouse.connected.core.UploadKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.CancellationException

class BatchTreeInventoryTest {
    private fun file(id: String, size: Long) = BatchTreeEntry(id, "image/jpeg", size, "$id.jpg", false)
    private fun folder(id: String) = BatchTreeEntry(id, null, null, null, true)
    private fun source(entry: BatchTreeEntry, bytes: Long = requireNotNull(entry.size)) =
        BatchUploadSource(requireNotNull(entry.name), bytes, UploadKind.IMAGE,
            { throw AssertionError("Review must not open file bytes") }, entry.id)

    @Test fun budgetUsesPreparedSizesAndKeepsLaterFilesThatFit() {
        val scan = inventoryBatchTree("root", 10, 100,
            readDirectory = { _, _ -> BatchTreePage(listOf(file("first", 40),
                file("changed", 15), file("last", 60)), false) },
            prepareSource = { entry -> source(entry, if (entry.id == "changed") 80L else requireNotNull(entry.size)) })
        assertEquals(listOf("first", "last"), scan.sources.map { it.locator })
        assertEquals(100L, scan.bytes)
        assertEquals(0, scan.skipped)
        assertTrue(scan.scanLimited)
    }

    @Test fun folderCyclesAndRepeatedDocumentsAreReadOnlyOnce() {
        val visited = mutableListOf<String>()
        val scan = inventoryBatchTree("root", 100, 4096,
            readDirectory = { directory, _ ->
                visited.add(directory)
                when (directory) {
                    "root" -> BatchTreePage(listOf(folder("root"), folder("sub"), file("image", 25)), false)
                    "sub" -> BatchTreePage(listOf(folder("root"), folder("sub"), file("image", 25),
                        file("other", 50)), false)
                    else -> error("Unexpected directory")
                }
            },
            prepareSource = { source(it) })
        assertEquals(listOf("root", "sub"), visited)
        assertEquals(listOf("image", "other"), scan.sources.map { it.locator })
        assertEquals(75L, scan.bytes)
        assertFalse(scan.scanLimited)
    }

    @Test fun sharedRowAndFileLimitsReportPartialReviewWithoutInflatingSkipped() {
        val visited = mutableListOf<Pair<String, Int>>()
        val scan = inventoryBatchTree("root", 10, 4096,
            readDirectory = { directory, remaining ->
                visited.add(directory to remaining)
                when (directory) {
                    "root" -> BatchTreePage(listOf(folder("sub"), folder("unvisited")), false)
                    "sub" -> BatchTreePage(listOf(file("first", 50), file("second", 60)), true)
                    else -> error("Scanned beyond the bounded window")
                }
            },
            prepareSource = { source(it) }, maxRows = 4)
        assertEquals(listOf("root" to 4, "sub" to 2), visited)
        assertEquals(110L, scan.bytes)
        assertEquals(0, scan.skipped)
        assertTrue(scan.scanLimited)

        val atCapacity = inventoryBatchTree("root", 1, 4096,
            readDirectory = { _, _ -> BatchTreePage(listOf(file("one", 50)), false) },
            prepareSource = { source(it) })
        assertFalse(atCapacity.scanLimited)
        val more = inventoryBatchTree("root", 1, 4096,
            readDirectory = { _, _ -> BatchTreePage(listOf(file("one", 50), file("two", 60)), false) },
            prepareSource = { source(it) })
        assertTrue(more.scanLimited)
        assertEquals(0, more.skipped)
    }

    @Test fun cancellationAfterDirectoryReadDiscardsPartialResults() {
        var active = true
        assertThrows(CancellationException::class.java) {
            inventoryBatchTree("root", 10, 4096,
                readDirectory = { _, _ ->
                    active = false
                    BatchTreePage(listOf(file("one", 25)), false)
                },
                prepareSource = { throw AssertionError("Candidate prepared after cancellation") },
                checkActive = { if (!active) throw CancellationException() })
        }
    }
}
