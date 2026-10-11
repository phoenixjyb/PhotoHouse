package dev.photohouse.connected

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.MemoryBookReaderPosition
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.Cipher
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MemoryBookReaderPositionPersistenceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val origin = "https://synthetic.example.test"
    private val otherOrigin = "https://other.synthetic.example.test"
    private val account = "synthetic-family-account"
    private val otherAccount = "other-synthetic-family-account"

    @Before @After fun clearSyntheticRecords() {
        for (scope in listOf(origin to account, origin to otherAccount, otherOrigin to account)) {
            runCatching { persistence(scope.first).clear(scope.second) }
            positionFile(scope.first, scope.second).delete()
        }
        // Also clean the story-domain account record used by the domain-separation test.
        runCatching { KeystoreSavedStoryReaderPositionPersistence(context, origin).clear(account) }
        storyPositionFile(origin, account).delete()
    }

    @Test fun encryptedMetadataRoundTripsAcrossInstancesWithoutPlaintextOnDisk() {
        val expected = position(1, account)
        persistence(origin).save(account, expected)

        assertEquals(listOf(expected), persistence(origin).load(account))
        val bytes = positionFile(origin, account).readBytes()
        assertTrue(bytes.size in 12 + 16 + 1..16 * 1024 + 12 + 16)
        for (value in listOf(
            account, expected.libraryId, expected.bookId, expected.storyId, expected.chapterId, expected.assetId,
        )) {
            assertFalse("unencrypted $value was found in the record", bytes.containsSubsequence(value.toByteArray()))
        }
    }

    @Test fun accountAndOriginAreBoundAndCleanupDoesNotTouchOtherRecords() {
        val expected = position(2, account)
        persistence(origin).save(account, expected)
        val source = positionFile(origin, account).readBytes()
        persistence(origin).save(otherAccount, position(3, otherAccount))

        assertTrue(persistence(otherOrigin).load(account).isEmpty())
        assertTrue(persistence(origin).load(otherAccount).isNotEmpty())

        positionFile(origin, otherAccount).writeBytes(source)
        assertTrue(persistence(origin).load(otherAccount).isEmpty())
        assertFalse(positionFile(origin, otherAccount).exists())
        assertEquals(listOf(position(2, account)), persistence(origin).load(account))

        positionFile(otherOrigin, account).writeBytes(source)
        assertTrue(persistence(otherOrigin).load(account).isEmpty())
        assertFalse(positionFile(otherOrigin, account).exists())
        assertEquals(listOf(position(2, account)), persistence(origin).load(account))
    }

    @Test fun memoirAndSavedStoryDomainsCannotReadEachOthersCiphertext() {
        val memoir = persistence(origin)
        val expected = position(4, account)
        memoir.save(account, expected)
        val memoirBytes = positionFile(origin, account).readBytes()

        val story = KeystoreSavedStoryReaderPositionPersistence(context, origin)
        story.save(account, dev.photohouse.connected.core.SavedStoryReaderPosition(
            accountId = account,
            libraryId = "family-a",
            storyId = uuid(40),
            storyRevision = 1,
            chapterId = "chapter-1",
            assetId = "140",
        ))
        storyPositionFile(origin, account).writeBytes(memoirBytes)

        assertTrue(story.load(account).isEmpty())
        assertFalse(storyPositionFile(origin, account).exists())
        assertEquals(listOf(expected), memoir.load(account))
    }

    @Test fun savesUseTwelveEntryMruAndRemovalIsScoped() {
        val store = persistence(origin)
        (1..13).forEach { store.save(account, position(it, account)) }

        val loaded = store.load(account)
        assertEquals(12, loaded.size)
        assertEquals(position(13, account), loaded.first())
        assertFalse(loaded.any { it.bookId == position(1, account).bookId })

        store.remove(account, "family-a", position(13, account).bookId)
        assertEquals(11, store.load(account).size)
        assertFalse(store.load(account).any { it.bookId == position(13, account).bookId })

        persistence(origin).save(otherAccount, position(1, otherAccount))
        store.clear(account)
        assertTrue(store.load(account).isEmpty())
        assertEquals(listOf(position(1, otherAccount)), store.load(otherAccount))
    }

    @Test fun invalidAccountIsRejectedBySharedHelperBeforeRecordOperations() {
        val store = EncryptedPositionRecordStore(context, origin, PositionRecordDomain.MEMOIR)
        val before = readerPositionFiles().map { it.name }.sorted()
        var rejected = false
        try {
            store.read("bad\u0001account")
        } catch (_: IllegalArgumentException) {
            rejected = true
        }
        assertTrue(rejected)
        assertEquals(before, readerPositionFiles().map { it.name }.sorted())
    }

    @Test fun tamperedAndAuthenticatedMalformedRecordsFailClosedForOnlyThatAccount() {
        val store = persistence(origin)
        store.save(account, position(5, account))
        store.save(otherAccount, position(6, otherAccount))
        val record = positionFile(origin, account).readBytes()
        record[record.lastIndex] = (record.last().toInt() xor 0x01).toByte()
        positionFile(origin, account).writeBytes(record)

        assertTrue(store.load(account).isEmpty())
        assertFalse(positionFile(origin, account).exists())
        assertEquals(listOf(position(6, otherAccount)), store.load(otherAccount))

        // Authenticate malformed JSON with the test-only key handle to exercise strict codec cleanup.
        val malformed = encrypt(origin, account, "{}".toByteArray(Charsets.UTF_8))
        positionFile(origin, account).writeBytes(malformed)
        assertTrue(store.load(account).isEmpty())
        assertFalse(positionFile(origin, account).exists())
        assertEquals(listOf(position(6, otherAccount)), store.load(otherAccount))
    }

    private fun persistence(configuredOrigin: String) =
        KeystoreMemoryBookReaderPositionPersistence(context, configuredOrigin)

    private fun position(index: Int, accountId: String) = MemoryBookReaderPosition(
        accountId = accountId,
        libraryId = "family-a",
        bookId = uuid(index),
        bookRevision = index.toLong(),
        storyId = uuid(index + 100),
        storyRevision = (index + 1).toLong(),
        chapterId = "chapter-${(index - 1) % 6 + 1}",
        assetId = (100 + index).toString(),
    )

    private fun uuid(index: Int): String = UUID(0L, index.toLong()).toString()

    private fun positionFile(configuredOrigin: String, accountId: String): File =
        context.noBackupFilesDir.resolve("photohouse-memory-book-reader-positions-${hex(digest(configuredOrigin + "\n" + accountId))}")

    private fun storyPositionFile(configuredOrigin: String, accountId: String): File =
        context.noBackupFilesDir.resolve("photohouse-story-reader-positions-${hex(digest(configuredOrigin + "\n" + accountId))}")

    private fun readerPositionFiles(): List<File> = context.noBackupFilesDir.listFiles()
        ?.filter { it.name.startsWith("photohouse-memory-book-reader-positions-") || it.name.startsWith("photohouse-story-reader-positions-") }
        .orEmpty()

    private fun encrypt(configuredOrigin: String, accountId: String, plaintext: ByteArray): ByteArray {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val alias = "photohouse.memory-book-reader-positions.${hex(digest(configuredOrigin))}"
        val key = (keyStore.getEntry(alias, null) as KeyStore.SecretKeyEntry).secretKey
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val iv = cipher.iv
        val aad = ("PhotoHouse.MemoryBookReaderPositions/v1\n" + configuredOrigin + "\n" + accountId).toByteArray(Charsets.UTF_8)
        return try {
            cipher.updateAAD(aad)
            iv + cipher.doFinal(plaintext)
        } finally {
            plaintext.fill(0)
            iv.fill(0)
            aad.fill(0)
        }
    }

    private fun digest(value: String): ByteArray = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))

    private fun hex(value: ByteArray): String = value.joinToString("") { "%02x".format(it) }
}

private fun ByteArray.containsSubsequence(needle: ByteArray): Boolean =
    needle.isNotEmpty() && size >= needle.size && (0..size - needle.size).any { start ->
        needle.indices.all { this[start + it] == needle[it] }
    }
