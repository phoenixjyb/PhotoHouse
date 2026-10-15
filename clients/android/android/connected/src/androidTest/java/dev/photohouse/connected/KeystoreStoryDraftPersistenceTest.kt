package dev.photohouse.connected

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.StoryDraftChapter
import dev.photohouse.connected.core.StoryDraftRecord
import dev.photohouse.connected.core.StoryDraftScope
import dev.photohouse.connected.core.StoryDraftStorageException
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeystoreStoryDraftPersistenceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val origin = "https://story-draft.synthetic.example.test"
    private val originHash get() = digest(origin)
    private val prefix get() = "photohouse-story-draft-$originHash-"
    private val alias get() = "photohouse.story-draft.$originHash"
    private val persistence get() = KeystoreStoryDraftPersistence(context, origin)

    @After fun cleanSyntheticSlotsAndKey() {
        context.noBackupFilesDir.listFiles().orEmpty().filter { it.name.startsWith(prefix) }.forEach(File::delete)
        KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry(alias) }
    }

    @Test fun atomicBackupAndNewFilesCountOnceAndTwentySlotsCapTheWholeOrigin() {
        val first = baseFile(StoryDraftScope("member-a", "family-a"))
        File(first.absolutePath + ".bak").writeBytes(byteArrayOf(1))
        File(first.absolutePath + ".new").writeBytes(byteArrayOf(2))
        val second = baseFile(StoryDraftScope("member-b", "family-b"))
        File(second.absolutePath + ".bak").writeBytes(byteArrayOf(3))
        assertEquals(2, persistence.occupiedSlots())

        (1..18).forEach { index ->
            val path = baseFile(StoryDraftScope("member-$index", "family-$index"))
            File(path.absolutePath + ".bak").writeBytes(byteArrayOf(index.toByte()))
        }
        assertEquals(20, persistence.occupiedSlots())
        val overflow = StoryDraftScope("member-overflow", "family-overflow")
        assertThrows(StoryDraftStorageException::class.java) {
            persistence.write(record(overflow, "33333333-3333-4333-8333-333333333333"), null)
        }
    }

    @Test fun zeroByteExistingRecordIsCorruptRatherThanAnEmptySlot() {
        val path = baseFile(StoryDraftScope("member-a", "family-a"))
        path.writeBytes(byteArrayOf())
        assertThrows(StoryDraftStorageException::class.java) { persistence.load(StoryDraftScope("member-a", "family-a")) }
        assertTrue(path.exists())
        assertEquals(1, persistence.occupiedSlots())
    }

    @Test fun missingKeyWithAnyOriginSlotCannotOrphanOrOverwriteEncryptedData() {
        val scope = StoryDraftScope("member-a", "family-a")
        persistence.write(record(scope, "11111111-1111-4111-8111-111111111111"), null)
        val path = baseFile(scope)
        val encryptedBefore = path.readBytes()
        KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry(alias) }

        assertThrows(StoryDraftStorageException::class.java) { persistence.load(scope) }
        val otherScope = StoryDraftScope("member-b", "family-b")
        assertThrows(StoryDraftStorageException::class.java) {
            persistence.write(record(otherScope, "22222222-2222-4222-8222-222222222222"), null)
        }
        assertTrue(path.exists())
        assertTrue(encryptedBefore.contentEquals(path.readBytes()))
        assertEquals(1, persistence.occupiedSlots())
    }

    @Test fun deleteCompareAndSwapChecksRecordIdToAvoidDeleteRecreateAba() {
        val scope = StoryDraftScope("member-a", "family-a")
        val old = persistence.write(record(scope, "11111111-1111-4111-8111-111111111111"), null)
        assertTrue(persistence.delete(scope, old.recordId, old.revision))
        val replacement = persistence.write(record(scope, "22222222-2222-4222-8222-222222222222"), null)
        assertEquals(old.revision, replacement.revision)
        assertFalse(persistence.delete(scope, old.recordId, old.revision))
        assertEquals(replacement.recordId, persistence.load(scope)?.recordId)
    }

    @Test fun compareAndSwapIsSerializedAcrossPersistenceInstances() {
        val scope = StoryDraftScope("member-a", "family-a")
        val initial = persistence.write(record(scope, "11111111-1111-4111-8111-111111111111"), null)
        val secondAdapter = KeystoreStoryDraftPersistence(context, origin)
        val ready = CountDownLatch(2)
        val start = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(2)
        try {
            val outcomes = listOf(persistence, secondAdapter).mapIndexed { index, adapter ->
                pool.submit<Boolean> {
                    ready.countDown()
                    check(start.await(5, TimeUnit.SECONDS))
                    runCatching { adapter.write(initial.copy(title = "writer-$index"), initial.revision, initial.recordId) }.isSuccess
                }
            }
            assertTrue(ready.await(5, TimeUnit.SECONDS))
            start.countDown()
            assertEquals(1, outcomes.count { it.get(10, TimeUnit.SECONDS) })
            assertEquals(2L, persistence.load(scope)?.revision)
        } finally {
            pool.shutdownNow()
        }
    }

    @Test fun unreadableDeleteRequiresSameBytesAndStillUnreadableSlot() {
        val scope = StoryDraftScope("member-a", "family-a")
        val path = baseFile(scope)
        path.writeBytes(byteArrayOf(1, 2, 3))
        val fingerprint = requireNotNull(persistence.unreadableFingerprint(scope))
        path.writeBytes(byteArrayOf(4, 5, 6))
        assertFalse(persistence.deleteUnreadable(scope, fingerprint))
        assertTrue(path.exists())
        val newerFingerprint = requireNotNull(persistence.unreadableFingerprint(scope))
        assertTrue(persistence.deleteUnreadable(scope, newerFingerprint))
        assertFalse(path.exists())
    }

    private fun record(scope: StoryDraftScope, id: String) = StoryDraftRecord(
        scope = scope,
        recordId = id,
        revision = 0,
        createdAtEpochMillis = 1,
        updatedAtEpochMillis = 1,
        selectionRevision = "a".repeat(64),
        selectedAssetIds = listOf("1"),
        theme = "everyday",
        language = "zh",
        title = "",
        titleAuthored = false,
        chapters = listOf(StoryDraftChapter("chapter-1", "", false, "", false, listOf("1"), emptyList())),
        sourceReviewEnabled = false,
        guideMode = false,
        guideStep = null,
    )

    private fun baseFile(scope: StoryDraftScope): File = context.noBackupFilesDir.resolve(
        prefix + digest(scope.libraryId) + "-" + digest(scope.accountId))

    private fun digest(value: String) = MessageDigest.getInstance("SHA-256").digest(value.toByteArray())
        .joinToString("") { "%02x".format(it) }
}
