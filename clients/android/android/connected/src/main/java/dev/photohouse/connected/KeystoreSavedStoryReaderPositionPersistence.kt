package dev.photohouse.connected

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import dev.photohouse.connected.core.SavedStoryReaderPosition
import dev.photohouse.connected.core.SavedStoryReaderPositionPersistence
import dev.photohouse.connected.core.SavedStoryReaderPositions
import java.io.FileNotFoundException
import java.security.KeyStore
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Encrypted, app-private saved-story location metadata. No story content is persisted. */
internal class KeystoreSavedStoryReaderPositionPersistence(
    context: Context,
    configuredOrigin: String,
) : SavedStoryReaderPositionPersistence {
    private val directory = context.applicationContext.noBackupFilesDir
    private val origin = configuredOrigin.also {
        require(it.isNotBlank() && it.length <= MAX_ORIGIN_CHARS && it.none(Char::isISOControl))
    }
    private val alias = "photohouse.story-reader-positions.${hex(digest(origin))}"

    @Synchronized
    override fun load(accountId: String): List<SavedStoryReaderPosition> {
        SavedStoryReaderPositions.validated(accountId, emptyList())
        val file = file(accountId)
        var record: ByteArray? = null
        var iv: ByteArray? = null
        var ciphertext: ByteArray? = null
        var plaintext: ByteArray? = null
        var associatedData: ByteArray? = null
        try {
            record = readBounded(file)
            require(record.size in IV_BYTES + TAG_BYTES + 1..MAX_RECORD_BYTES)
            val key = existingKey() ?: return failClosed(file)
            val nonce = record.copyOfRange(0, IV_BYTES)
            iv = nonce
            val encrypted = record.copyOfRange(IV_BYTES, record.size)
            ciphertext = encrypted
            val cipher = Cipher.getInstance(CIPHER)
            cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, nonce))
            val aadBytes = aad(accountId)
            associatedData = aadBytes
            cipher.updateAAD(aadBytes)
            val decoded = cipher.doFinal(encrypted)
            plaintext = decoded
            require(decoded.size <= MAX_PLAINTEXT_BYTES)
            return SavedStoryReaderPositions.decodeRecord(accountId, decoded)
        } catch (_: FileNotFoundException) {
            return emptyList()
        } catch (_: Exception) {
            return failClosed(file)
        } finally {
            record?.fill(0)
            iv?.fill(0)
            ciphertext?.fill(0)
            plaintext?.fill(0)
            associatedData?.fill(0)
        }
    }

    @Synchronized
    override fun save(accountId: String, position: SavedStoryReaderPosition) {
        savePositions(accountId, SavedStoryReaderPositions.upsert(accountId, load(accountId), position))
    }

    @Synchronized
    override fun remove(accountId: String, libraryId: String, storyId: String) {
        val remaining = SavedStoryReaderPositions.without(accountId, load(accountId), libraryId, storyId)
        savePositions(accountId, remaining)
    }

    @Synchronized
    override fun clear(accountId: String) {
        SavedStoryReaderPositions.validated(accountId, emptyList())
        file(accountId).delete()
    }

    private fun savePositions(accountId: String, positions: List<SavedStoryReaderPosition>) {
        SavedStoryReaderPositions.validated(accountId, positions)
        val file = file(accountId)
        if (positions.isEmpty()) {
            file.delete()
            return
        }

        var plaintext: ByteArray? = null
        var iv: ByteArray? = null
        var ciphertext: ByteArray? = null
        var record: ByteArray? = null
        var associatedData: ByteArray? = null
        try {
            val encoded = SavedStoryReaderPositions.encodeRecord(accountId, positions)
            plaintext = encoded
            require(encoded.size <= MAX_PLAINTEXT_BYTES)
            val cipher = Cipher.getInstance(CIPHER)
            cipher.init(Cipher.ENCRYPT_MODE, existingKey() ?: createKey())
            val nonce = cipher.iv
            iv = nonce
            require(nonce.size == IV_BYTES)
            val aadBytes = aad(accountId)
            associatedData = aadBytes
            cipher.updateAAD(aadBytes)
            val encrypted = cipher.doFinal(encoded)
            ciphertext = encrypted
            require(encrypted.size <= MAX_PLAINTEXT_BYTES + TAG_BYTES)
            val encryptedRecord = nonce + encrypted
            record = encryptedRecord
            require(encryptedRecord.size <= MAX_RECORD_BYTES)
            writeAtomically(file, encryptedRecord)
        } catch (failure: Exception) {
            throw IllegalStateException("Unable to save saved-story reading positions", failure)
        } finally {
            plaintext?.fill(0)
            iv?.fill(0)
            ciphertext?.fill(0)
            record?.fill(0)
            associatedData?.fill(0)
        }
    }

    private fun writeAtomically(file: AtomicFile, record: ByteArray) {
        val stream = file.startWrite()
        try {
            stream.write(record)
            stream.flush()
            file.finishWrite(stream)
        } catch (failure: Exception) {
            try {
                file.failWrite(stream)
            } catch (cleanupFailure: Exception) {
                failure.addSuppressed(cleanupFailure)
            }
            throw failure
        }
    }

    private fun readBounded(file: AtomicFile): ByteArray {
        val buffer = ByteArray(MAX_RECORD_BYTES + 1)
        try {
            var count = 0
            file.openRead().use { input ->
                while (count < buffer.size) {
                    val read = input.read(buffer, count, buffer.size - count)
                    if (read < 0) break
                    if (read > 0) count += read
                }
            }
            require(count <= MAX_RECORD_BYTES)
            return buffer.copyOf(count)
        } finally {
            buffer.fill(0)
        }
    }

    private fun failClosed(file: AtomicFile): List<SavedStoryReaderPosition> {
        try {
            file.delete()
        } catch (_: Exception) {
            // The caller still receives no pointer; a later load retries cleanup.
        }
        return emptyList()
    }

    private fun file(accountId: String): AtomicFile = AtomicFile(
        directory.resolve("photohouse-story-reader-positions-${hex(digest(origin + "\n" + accountId))}"),
    )

    private fun aad(accountId: String): ByteArray =
        (AAD_PREFIX + origin + "\n" + accountId).toByteArray(Charsets.UTF_8)

    private fun existingKey(): SecretKey? =
        (KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
            .getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.secretKey

    private fun createKey(): SecretKey = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE).apply {
        init(KeyGenParameterSpec.Builder(
            alias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        ).setKeySize(KEY_BITS)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build())
    }.generateKey()

    private fun digest(value: String): ByteArray = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))

    private fun hex(value: ByteArray): String = value.joinToString("") { "%02x".format(it) }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val CIPHER = "AES/GCM/NoPadding"
        const val KEY_BITS = 256
        const val IV_BYTES = 12
        const val TAG_BYTES = 16
        const val TAG_BITS = TAG_BYTES * 8
        const val MAX_ORIGIN_CHARS = 512
        const val MAX_PLAINTEXT_BYTES = 16 * 1024
        const val MAX_RECORD_BYTES = MAX_PLAINTEXT_BYTES + IV_BYTES + TAG_BYTES
        const val AAD_PREFIX = "PhotoHouse.SavedStoryReaderPositions/v1\n"
    }
}
