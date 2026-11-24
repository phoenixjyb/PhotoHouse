package dev.photohouse.connected

import android.content.Context
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import org.json.JSONObject
import java.io.FileNotFoundException
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** One encrypted, account/origin-bound SAF shortcut. It never scans or starts an upload. */
internal data class RememberedBatchFolder(
    val accountId: String,
    val destinationLibraryId: String,
    val treeUri: String,
)

internal class KeystoreBatchFolderPersistence(context: Context, configuredOrigin: String) {
    private val appContext = context.applicationContext
    private val origin = configuredOrigin.also {
        require(it.isNotBlank() && it.length <= MAX_ORIGIN_BYTES && it.none(Char::isISOControl))
    }
    private val originHash = hex(digest(origin))
    private val alias = "photohouse.batch-folder.$originHash"

    fun load(accountId: String): RememberedBatchFolder? = synchronized(storageLock) {
        val file = file(accountId)
        try {
            val encrypted = ByteArray(MAX_RECORD_BYTES + 1)
            var count = 0
            file.openRead().use { input ->
                while (count < encrypted.size) {
                    val read = input.read(encrypted, count, encrypted.size - count)
                    if (read < 0) break
                    if (read > 0) count += read
                }
            }
            require(count in IV_BYTES + TAG_BYTES + 1..MAX_RECORD_BYTES)
            val key = existingKey() ?: error("Saved folder key unavailable")
            val cipher = Cipher.getInstance(CIPHER)
            cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, encrypted.copyOfRange(0, IV_BYTES)))
            cipher.updateAAD(aad(accountId))
            val plain = cipher.doFinal(encrypted, IV_BYTES, count - IV_BYTES)
            require(plain.size <= MAX_PLAINTEXT_BYTES)
            val value = JSONObject(String(plain, StandardCharsets.UTF_8))
            require(value.keys().asSequence().toSet() == setOf("account", "destination", "tree_uri"))
            RememberedBatchFolder(value.getString("account"), value.getString("destination"),
                value.getString("tree_uri")).also {
                require(it.accountId == accountId)
                validate(it)
            }
        } catch (_: FileNotFoundException) {
            null
        } catch (_: Exception) {
            null
        }
    }

    fun save(value: RememberedBatchFolder) = synchronized(storageLock) {
        validate(value)
        val plaintext = JSONObject().put("account", value.accountId)
            .put("destination", value.destinationLibraryId).put("tree_uri", value.treeUri)
            .toString().toByteArray(StandardCharsets.UTF_8)
        require(plaintext.size <= MAX_PLAINTEXT_BYTES)
        val cipher = Cipher.getInstance(CIPHER)
        cipher.init(Cipher.ENCRYPT_MODE, existingKey() ?: createKey())
        require(cipher.iv.size == IV_BYTES)
        cipher.updateAAD(aad(value.accountId))
        val record = cipher.iv + cipher.doFinal(plaintext)
        require(record.size <= MAX_RECORD_BYTES)
        val target = file(value.accountId)
        val stream = target.startWrite()
        try {
            stream.write(record)
            stream.flush()
            target.finishWrite(stream)
        } catch (error: Exception) {
            target.failWrite(stream)
            throw IllegalStateException("Unable to save folder shortcut")
        }
    }

    fun forget(accountId: String) = synchronized(storageLock) {
        val selected = file(accountId)
        selected.delete()
        try {
            selected.openRead().use { error("Unable to remove folder shortcut") }
        } catch (_: FileNotFoundException) {
            Unit
        }
    }

    private fun validate(value: RememberedBatchFolder) {
        require(validAccount(value.accountId))
        require(value.destinationLibraryId.matches(Regex("[a-z0-9][a-z0-9_-]{2,63}")))
        require(value.treeUri.length in 1..MAX_URI_BYTES && value.treeUri.none(Char::isISOControl))
        val uri = Uri.parse(value.treeUri)
        require(uri.scheme == "content" && uri.authority != null)
    }

    private fun validAccount(value: String) = value.isNotBlank() && value.length <= MAX_ACCOUNT_BYTES &&
        value.none(Char::isISOControl)

    private fun file(accountId: String): AtomicFile {
        require(validAccount(accountId))
        return AtomicFile(appContext.noBackupFilesDir.resolve(
            "photohouse-batch-folder-$originHash-${hex(digest(accountId))}"))
    }

    private fun aad(accountId: String) =
        ("PhotoHouse.BatchFolder/v1\n" + origin + "\n" + accountId).toByteArray(StandardCharsets.UTF_8)

    private fun existingKey(): SecretKey? = (keyStore().getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.secretKey

    private fun createKey(): SecretKey = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE).apply {
        init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
    }.generateKey()

    private fun keyStore(): KeyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
    private fun digest(value: String) = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(StandardCharsets.UTF_8))
    private fun hex(value: ByteArray) = value.joinToString("") { "%02x".format(it) }

    private companion object {
        val storageLock = Any()
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val CIPHER = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
        const val TAG_BITS = 128
        const val TAG_BYTES = 16
        const val MAX_ORIGIN_BYTES = 512
        const val MAX_ACCOUNT_BYTES = 256
        const val MAX_URI_BYTES = 4096
        const val MAX_PLAINTEXT_BYTES = 8192
        const val MAX_RECORD_BYTES = MAX_PLAINTEXT_BYTES + IV_BYTES + TAG_BYTES
    }
}
