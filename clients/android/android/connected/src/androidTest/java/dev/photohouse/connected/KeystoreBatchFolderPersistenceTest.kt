package dev.photohouse.connected

import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeystoreBatchFolderPersistenceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val origin = "https://batch-folder.synthetic.example.test"
    private val otherOrigin = "https://other-batch-folder.synthetic.example.test"
    private val record = RememberedBatchFolder("synthetic-account", "family-a",
        "content://com.android.externalstorage.documents/tree/primary%3ADCIM")

    @After fun clearSyntheticSlotsAndKeys() {
        listOf(origin, otherOrigin).forEach { selected ->
            val hash = digest(selected)
            context.noBackupFilesDir.listFiles().orEmpty().filter {
                it.name.startsWith("photohouse-batch-folder-$hash-")
            }.forEach(File::delete)
            KeyStore.getInstance("AndroidKeyStore").apply {
                load(null); deleteEntry("photohouse.batch-folder.$hash")
            }
        }
    }

    @Test fun encryptedRoundTripIsBoundToAccountAndOriginAndForgetRemovesTheShortcut() {
        val persistence = KeystoreBatchFolderPersistence(context, origin)
        persistence.save(record)
        assertEquals(record, KeystoreBatchFolderPersistence(context, origin).load(record.accountId))
        assertNull(persistence.load("other-account"))
        assertNull(KeystoreBatchFolderPersistence(context, otherOrigin).load(record.accountId))
        assertFalse(folderFile(origin, record.accountId).readBytes().containsBytes(record.treeUri.toByteArray()))
        assertFalse(folderFile(origin, record.accountId).readBytes().containsBytes(record.destinationLibraryId.toByteArray()))
        persistence.forget(record.accountId)
        assertNull(persistence.load(record.accountId))
    }

    @Test fun corruptEncryptedRecordFailsClosedAndCanBeReplacedExplicitly() {
        val persistence = KeystoreBatchFolderPersistence(context, origin)
        persistence.save(record)
        val file = folderFile(origin, record.accountId)
        val corrupt = byteArrayOf(1, 2, 3)
        file.writeBytes(corrupt)
        assertNull(persistence.load(record.accountId))
        org.junit.Assert.assertArrayEquals(corrupt, file.readBytes())
        persistence.save(record)
        assertEquals(record, persistence.load(record.accountId))
    }

    @Test fun aSyntheticTreeWithoutAReadGrantIsRejected() {
        assertFalse(hasPersistedTreeReadGrant(context,
            Uri.parse("content://uninstalled.synthetic.provider/tree/root")))
    }

    private fun folderFile(selectedOrigin: String, account: String): File =
        context.noBackupFilesDir.resolve("photohouse-batch-folder-${digest(selectedOrigin)}-${digest(account)}")

    private fun digest(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray()).joinToString("") { "%02x".format(it) }
}

private fun ByteArray.containsBytes(needle: ByteArray): Boolean =
    (0..size - needle.size).any { start -> needle.indices.all { this[start + it] == needle[it] } }
