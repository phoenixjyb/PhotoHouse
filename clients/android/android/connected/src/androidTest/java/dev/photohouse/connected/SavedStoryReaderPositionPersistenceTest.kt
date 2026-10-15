package dev.photohouse.connected

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.SavedStoryReaderPosition
import dev.photohouse.connected.core.SavedStoryReaderPositions
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SavedStoryReaderPositionPersistenceTest {
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
    }

    @Test fun encryptedMetadataRoundTripsAcrossInstancesWithoutPlaintextOnDisk() {
        val expected = position(1, account)
        persistence(origin).save(account, expected)

        assertEquals(listOf(expected), persistence(origin).load(account))
        val bytes = positionFile(origin, account).readBytes()
        assertTrue(bytes.size in 12 + 16 + 1..16 * 1024 + 12 + 16)
        for (value in listOf(account, expected.libraryId, expected.storyId, expected.chapterId)) {
            assertFalse("unencrypted $value was found in the record", bytes.containsSubsequence(value.toByteArray()))
        }
    }

    @Test fun refactoredAdapterReadsRecordWrittenWithOriginalStoryEnvelope() {
        val expected = position(8, account)
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val alias = "photohouse.story-reader-positions.${hex(digest(origin))}"
        val key = (keyStore.getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.secretKey
            ?: run {
                // Create the historical key using the unchanged alias before writing the legacy bytes.
                persistence(origin).save(account, expected)
                (KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
                    .getEntry(alias, null) as KeyStore.SecretKeyEntry).secretKey
            }
        val plaintext = SavedStoryReaderPositions.encodeRecord(account, listOf(expected))
        var iv: ByteArray? = null
        var ciphertext: ByteArray? = null
        var record: ByteArray? = null
        var aad: ByteArray? = null
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key)
            val nonce = cipher.iv
            iv = nonce
            assertEquals(12, nonce.size)
            val aadBytes = ("PhotoHouse.SavedStoryReaderPositions/v1\n" + origin + "\n" + account)
                .toByteArray(Charsets.UTF_8)
            aad = aadBytes
            cipher.updateAAD(aadBytes)
            val encrypted = cipher.doFinal(plaintext)
            ciphertext = encrypted
            val legacyRecord = nonce + encrypted
            record = legacyRecord
            positionFile(origin, account).writeBytes(legacyRecord)

            assertEquals(listOf(expected), persistence(origin).load(account))
        } finally {
            plaintext.fill(0)
            iv?.fill(0)
            ciphertext?.fill(0)
            record?.fill(0)
            aad?.fill(0)
        }
    }

    @Test fun accountAndOriginAadPreventCopiedCiphertextFromLoading() {
        val expected = position(2, account)
        persistence(origin).save(account, expected)
        val source = positionFile(origin, account).readBytes()

        assertTrue(persistence(origin).load(otherAccount).isEmpty())
        assertTrue(persistence(otherOrigin).load(account).isEmpty())

        positionFile(origin, otherAccount).writeBytes(source)
        assertTrue(persistence(origin).load(otherAccount).isEmpty())
        assertFalse(positionFile(origin, otherAccount).exists())
        assertEquals(listOf(expected), persistence(origin).load(account))

        positionFile(otherOrigin, account).writeBytes(source)
        assertTrue(persistence(otherOrigin).load(account).isEmpty())
        assertFalse(positionFile(otherOrigin, account).exists())
        assertEquals(listOf(expected), persistence(origin).load(account))
    }

    @Test fun savesUseTwelveEntryMruAndRemoveAndClearAreScoped() {
        val store = persistence(origin)
        (1..13).forEach { store.save(account, position(it, account)) }
        val loaded = store.load(account)
        assertEquals(12, loaded.size)
        assertEquals(position(13, account), loaded.first())
        assertFalse(loaded.any { it.storyId == position(1, account).storyId })

        store.remove(account, "family-a", position(13, account).storyId)
        assertEquals(11, store.load(account).size)
        assertFalse(store.load(account).any { it.storyId == position(13, account).storyId })

        persistence(origin).save(otherAccount, position(1, otherAccount))
        store.clear(account)
        assertTrue(store.load(account).isEmpty())
        assertEquals(listOf(position(1, otherAccount)), store.load(otherAccount))
    }

    @Test fun corruptCiphertextFailsClosedAndDeletesOnlyThatAccountRecord() {
        val store = persistence(origin)
        store.save(account, position(3, account))
        persistence(origin).save(otherAccount, position(4, otherAccount))
        positionFile(origin, account).writeBytes(byteArrayOf(1, 2, 3, 4, 5))

        assertTrue(store.load(account).isEmpty())
        assertFalse(positionFile(origin, account).exists())
        assertEquals(listOf(position(4, otherAccount)), store.load(otherAccount))
    }

    @Test fun authenticatedUnsupportedCodecVersionFailsClosed() {
        val store = persistence(origin)
        store.save(account, position(5, account))
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val alias = "photohouse.story-reader-positions.${hex(digest(origin))}"
        val key = (keyStore.getEntry(alias, null) as KeyStore.SecretKeyEntry).secretKey
        val plaintext = """{"version":99,"account_id":"$account","positions":[]}""".toByteArray(Charsets.UTF_8)
        var iv: ByteArray? = null
        var ciphertext: ByteArray? = null
        var record: ByteArray? = null
        var aad: ByteArray? = null
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key)
            val nonce = cipher.iv
            iv = nonce
            val aadBytes = ("PhotoHouse.SavedStoryReaderPositions/v1\n" + origin + "\n" + account).toByteArray(Charsets.UTF_8)
            aad = aadBytes
            cipher.updateAAD(aadBytes)
            val encrypted = cipher.doFinal(plaintext)
            ciphertext = encrypted
            val encryptedRecord = nonce + encrypted
            record = encryptedRecord
            positionFile(origin, account).writeBytes(encryptedRecord)

            assertTrue(store.load(account).isEmpty())
            assertFalse(positionFile(origin, account).exists())
        } finally {
            plaintext.fill(0)
            iv?.fill(0)
            ciphertext?.fill(0)
            record?.fill(0)
            aad?.fill(0)
        }
    }

    private fun persistence(configuredOrigin: String) =
        KeystoreSavedStoryReaderPositionPersistence(context, configuredOrigin)

    private fun position(index: Int, accountId: String) = SavedStoryReaderPosition(
        accountId = accountId,
        libraryId = "family-a",
        storyId = UUID(0L, index.toLong()).toString(),
        storyRevision = index.toLong(),
        chapterId = "chapter-${(index - 1) % 6 + 1}",
        assetId = (100 + index).toString(),
    )

    private fun positionFile(configuredOrigin: String, accountId: String): File =
        context.noBackupFilesDir.resolve("photohouse-story-reader-positions-${hex(digest(configuredOrigin + "\n" + accountId))}")

    private fun digest(value: String): ByteArray = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))

    private fun hex(value: ByteArray): String = value.joinToString("") { "%02x".format(it) }
}

private fun ByteArray.containsSubsequence(needle: ByteArray): Boolean =
    needle.isNotEmpty() && size >= needle.size && (0..size - needle.size).any { start ->
        needle.indices.all { this[start + it] == needle[it] }
    }
