package dev.photohouse.connected

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.photohouse.connected.core.RememberedSession
import dev.photohouse.connected.core.UploadKind
import dev.photohouse.connected.core.UploadQueueRecord
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeystoreSessionPersistenceTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val origin = "https://synthetic.example.test"
    private val otherOrigin = "https://other.synthetic.example.test"
    private val now = System.currentTimeMillis()

    @Before @After fun clearSyntheticRecords() {
        KeystoreSessionPersistence(context, origin).clear()
        KeystoreSessionPersistence(context, otherOrigin).clear()
        KeystoreUploadQueuePersistence(context, origin).clear("synthetic-account")
    }

    @Test fun savesAndLoadsAcrossRecreatedInstancesWithoutDiskToken() {
        val value = session(now - 1000)
        KeystoreSessionPersistence(context, origin).save(value)
        val loaded = KeystoreSessionPersistence(context, origin).load()
        assertEquals(value.accessToken, loaded?.accessToken)
        assertEquals(value.issuedAtMillis, loaded?.issuedAtMillis)
        assertEquals(value.expiresAtMillis, loaded?.expiresAtMillis)
        assertFalse(allFilesContain(value.accessToken))
    }

    @Test fun corruptPayloadFailsClosedAndIsCleared() {
        val persistence = KeystoreSessionPersistence(context, origin)
        persistence.save(session(now - 1000))
        sessionFile().writeBytes(byteArrayOf(1, 2, 3))
        assertNull(persistence.load())
        assertFalse(sessionFile().exists())
    }

    @Test fun expiredAndFutureIssuedSessionsAreRejected() {
        val persistence = KeystoreSessionPersistence(context, origin)
        assertRejected { persistence.save(session(now - 86_401_000L)) }
        assertRejected { persistence.save(session(now + 1000L)) }
    }

    @Test fun clearRemovesRecordAndOtherOriginIsolated() {
        val first = KeystoreSessionPersistence(context, origin)
        val second = KeystoreSessionPersistence(context, otherOrigin)
        first.save(session(now - 1000L))
        second.save(session(now - 1000L))
        first.clear()
        assertNull(first.load())
        assertTrue(second.load() != null)
        second.clear()
        assertNull(second.load())
    }

    @Test fun queuedDestinationSurvivesEncryptedPersistenceRecreation() {
        val record = UploadQueueRecord("local", "1".repeat(32), "2".repeat(32), "photo.jpg", "content://photo",
            4, UploadKind.IMAGE, "3".repeat(64), destinationLibraryId = "family-a", assetId = "901")
        val legacy = record.copy(localId = "legacy", requestId = "4".repeat(32), destinationLibraryId = null)
        KeystoreUploadQueuePersistence(context, origin).save("synthetic-account", listOf(record, legacy))
        assertEquals(listOf(record, legacy), KeystoreUploadQueuePersistence(context, origin).load("synthetic-account"))
    }

    private fun session(issuedAt: Long) = RememberedSession(token, issuedAt, issuedAt + 86_400_000L)

    private fun assertRejected(action: () -> Unit) {
        try {
            action()
            fail("invalid session was accepted")
        } catch (_: IllegalArgumentException) {
            // Expected validation failure.
        }
    }

    private fun sessionFile(): File = context.noBackupFilesDir.resolve("photohouse-session-" + java.security.MessageDigest.getInstance("SHA-256").digest(origin.toByteArray()).joinToString("") { "%02x".format(it) })

    private fun allFilesContain(value: String): Boolean =
        listOf(sessionFile()).filter { it.isFile }.any {
            it.readBytes().containsSubsequence(value.toByteArray())
        }

    private companion object {
        const val token = "TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT"
    }
}

private fun ByteArray.containsSubsequence(needle: ByteArray): Boolean =
    (0..size - needle.size).any { start -> needle.indices.all { this[start + it] == needle[it] } }
