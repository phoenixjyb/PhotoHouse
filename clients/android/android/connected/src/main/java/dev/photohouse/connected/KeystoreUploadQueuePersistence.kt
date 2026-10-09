package dev.photohouse.connected

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import dev.photohouse.connected.core.UploadKind
import dev.photohouse.connected.core.UploadQueuePersistence
import dev.photohouse.connected.core.UploadQueueRecord
import org.json.JSONArray
import org.json.JSONObject
import java.io.FileNotFoundException
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Encrypted app-private queue metadata; media bytes remain with the SAF provider. */
internal class KeystoreUploadQueuePersistence(context: Context, configuredOrigin: String) : UploadQueuePersistence {
    private val directory = context.applicationContext.noBackupFilesDir
    private val origin = configuredOrigin.also { require(it.isNotBlank() && it.length <= 512) }
    private val alias = "photohouse.queue.${hex(digest(origin))}"

    @Synchronized
    override fun load(account: String): List<UploadQueueRecord> {
        val file = file(account)
        return try {
            val record = ByteArray(MAX_RECORD_BYTES + 1)
            var count = 0
            file.openRead().use { input ->
                while (count < record.size) {
                    val read = input.read(record, count, record.size - count)
                    if (read < 0) break
                    if (read > 0) count += read
                }
            }
            require(count in IV_BYTES + TAG_BYTES + 1..MAX_RECORD_BYTES)
            val key = existingKey() ?: error("Queue key unavailable")
            val cipher = Cipher.getInstance(CIPHER)
            cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, record.copyOfRange(0, IV_BYTES)))
            cipher.updateAAD(aad(account))
            val plaintext = cipher.doFinal(record, IV_BYTES, count - IV_BYTES)
            require(plaintext.size <= MAX_PLAINTEXT_BYTES)
            JSONArray(String(plaintext, StandardCharsets.UTF_8)).let { array ->
                require(array.length() <= MAX_ITEMS)
                (0 until array.length()).map { i ->
                    val o = array.getJSONObject(i)
                    UploadQueueRecord(o.getString("local"), o.getString("request"), o.getString("batch"),
                        o.getString("filename"), o.optString("locator").takeIf { it.isNotEmpty() },
                        o.getLong("bytes"), UploadKind.valueOf(o.getString("kind")), o.getString("sha"),
                        o.optString("upload").takeIf { it.isNotEmpty() }, o.getLong("offset"),
                        o.getString("status"), o.optString("error").takeIf { it.isNotEmpty() },
                        o.optString("destination_library_id").takeIf { it.isNotEmpty() },
                        o.optString("asset_id").takeIf { it.isNotEmpty() })
                }
            }
        } catch (_: FileNotFoundException) {
            emptyList()
        } catch (_: Exception) {
            file.delete()
            emptyList()
        }
    }

    @Synchronized
    override fun save(account: String, records: List<UploadQueueRecord>) {
        require(records.size <= MAX_ITEMS)
        val file = file(account)
        if (records.isEmpty()) { file.delete(); return }
        val array = JSONArray()
        records.forEach { r -> array.put(JSONObject().apply {
            put("local", r.localId); put("request", r.requestId); put("batch", r.batch)
            put("filename", r.filename); put("locator", r.locator); put("bytes", r.bytes)
            put("kind", r.kind.name); put("sha", r.sha256); put("upload", r.uploadId)
            put("offset", r.offset); put("status", r.status); put("error", r.error)
            put("destination_library_id", r.destinationLibraryId)
            put("asset_id", r.assetId)
        }) }
        val plaintext = array.toString().toByteArray(StandardCharsets.UTF_8)
        require(plaintext.size <= MAX_PLAINTEXT_BYTES)
        val cipher = Cipher.getInstance(CIPHER)
        cipher.init(Cipher.ENCRYPT_MODE, existingKey() ?: createKey())
        require(cipher.iv.size == IV_BYTES)
        cipher.updateAAD(aad(account))
        val record = cipher.iv + cipher.doFinal(plaintext)
        require(record.size <= MAX_RECORD_BYTES)
        val stream = file.startWrite()
        try {
            stream.write(record)
            stream.flush()
            file.finishWrite(stream)
        } catch (error: Exception) {
            file.failWrite(stream)
            throw error
        }
    }

    private fun file(account: String): AtomicFile {
        require(account.isNotBlank() && account.length <= 256 && account.none(Char::isISOControl))
        return AtomicFile(directory.resolve("photohouse-upload-queue-${hex(digest(origin + "\n" + account))}"))
    }

    private fun aad(account: String) = ("PhotoHouse.UploadQueue/v1\n" + origin + "\n" + account).toByteArray(StandardCharsets.UTF_8)
    private fun digest(value: String) = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(StandardCharsets.UTF_8))
    private fun hex(value: ByteArray) = value.joinToString("") { "%02x".format(it) }
    private fun existingKey(): SecretKey? =
        (KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }.getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.secretKey

    private fun createKey(): SecretKey = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE).apply {
        init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
    }.generateKey()

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val CIPHER = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
        const val TAG_BITS = 128
        const val TAG_BYTES = 16
        const val MAX_ITEMS = 100
        const val MAX_PLAINTEXT_BYTES = 256 * 1024
        const val MAX_RECORD_BYTES = MAX_PLAINTEXT_BYTES + IV_BYTES + TAG_BYTES
    }
}
