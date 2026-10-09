package dev.photohouse.connected

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import dev.photohouse.connected.core.RememberedSession
import dev.photohouse.connected.core.SessionPersistence
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.FileNotFoundException
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class KeystoreSessionPersistence(
    context: Context,
    configuredOrigin: String,
) : SessionPersistence {
    private val appContext = context.applicationContext
    private val origin = configuredOrigin.also { require(it.isNotBlank() && it.length <= MAX_ORIGIN_BYTES && it.none(Char::isISOControl)) }
    private val originDigest = sha256(origin.toByteArray(StandardCharsets.UTF_8))
    private val alias = "photohouse.session.${hex(originDigest)}"
    private val file = AtomicFile(appContext.noBackupFilesDir.resolve("photohouse-session-${hex(originDigest)}"))

    @Synchronized
    override fun load(): RememberedSession? {
        return try {
            val record = readBounded()
            require(record.size in IV_BYTES + TAG_BYTES + 1..MAX_RECORD_BYTES)
            val iv = record.copyOfRange(0, IV_BYTES)
            val ciphertext = record.copyOfRange(IV_BYTES, record.size)
            val key = existingKey() ?: return failClosed()
            val cipher = Cipher.getInstance(CIPHER)
            cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, iv))
            cipher.updateAAD(aad())
            decode(cipher.doFinal(ciphertext)).also { session ->
                val now = System.currentTimeMillis()
                require(session.expiresAtMillis - session.issuedAtMillis == SESSION_LENGTH_MILLIS)
                require(session.issuedAtMillis >= 0 && session.issuedAtMillis <= now && now < session.expiresAtMillis)
            }
        } catch (_: FileNotFoundException) {
            null
        } catch (_: Exception) {
            failClosed()
        }
    }

    @Synchronized
    override fun save(value: RememberedSession) {
        val now = System.currentTimeMillis()
        validate(value, now)
        try {
            val key = existingKey() ?: createKey()
            val cipher = Cipher.getInstance(CIPHER)
            cipher.init(Cipher.ENCRYPT_MODE, key)
            val iv = cipher.iv
            require(iv.size == IV_BYTES)
            cipher.updateAAD(aad())
            val ciphertext = cipher.doFinal(encode(value))
            val record = iv + ciphertext
            require(record.size <= MAX_RECORD_BYTES)
            var stream: java.io.FileOutputStream? = null
            try {
                stream = file.startWrite()
                stream.write(record)
                stream.flush()
                file.finishWrite(stream)
                stream = null
            } finally {
                if (stream != null) file.failWrite(stream)
            }
        } catch (_: Exception) {
            failClosed()
            throw IllegalStateException("Unable to save session")
        }
    }

    @Synchronized
    override fun clear() {
        var failure = false
        try {
            file.delete()
        } catch (_: Exception) {
            failure = true
        }
        try {
            val keyStore = keyStore()
            if (keyStore.containsAlias(alias)) keyStore.deleteEntry(alias)
        } catch (_: Exception) {
            failure = true
        }
        if (failure) throw IllegalStateException("Unable to clear session")
    }

    private fun failClosed(): Nothing? {
        try {
            clear()
        } catch (_: Exception) {
            // A failed cleanup still returns no session; the next clear retries both targets.
        }
        return null
    }

    private fun existingKey(): SecretKey? {
        val entry = keyStore().getEntry(alias, null) ?: return null
        return (entry as? KeyStore.SecretKeyEntry)?.secretKey
    }

    private fun createKey(): SecretKey {
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            ).setKeySize(KEY_BITS)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build(),
        )
        return generator.generateKey()
    }

    private fun keyStore(): KeyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }

    private fun aad(): ByteArray = (AAD_PREFIX + origin).toByteArray(StandardCharsets.UTF_8)

    private fun readBounded(): ByteArray {
        val result = ByteArray(MAX_RECORD_BYTES + 1)
        var count = 0
        file.openRead().use { input ->
            while (count < result.size) {
                val read = input.read(result, count, result.size - count)
                if (read < 0) break
                if (read == 0) continue
                count += read
            }
        }
        require(count <= MAX_RECORD_BYTES)
        return result.copyOf(count)
    }

    private fun encode(value: RememberedSession): ByteArray {
        val token = value.accessToken.toByteArray(StandardCharsets.UTF_8)
        require(token.size == TOKEN_BYTES)
        return ByteArrayOutputStream(MAX_PLAINTEXT_BYTES).use { output ->
            DataOutputStream(output).use { data ->
                data.writeInt(FORMAT_MAGIC)
                data.writeByte(FORMAT_VERSION)
                data.writeLong(value.issuedAtMillis)
                data.writeLong(value.expiresAtMillis)
                data.writeInt(token.size)
                data.write(token)
            }
            output.toByteArray()
        }.also { require(it.size <= MAX_PLAINTEXT_BYTES) }
    }

    private fun decode(bytes: ByteArray): RememberedSession {
        require(bytes.size <= MAX_PLAINTEXT_BYTES)
        val input = DataInputStream(ByteArrayInputStream(bytes))
        require(input.readInt() == FORMAT_MAGIC)
        require(input.readUnsignedByte() == FORMAT_VERSION)
        val issuedAt = input.readLong()
        val expiresAt = input.readLong()
        val tokenLength = input.readInt()
        require(tokenLength == TOKEN_BYTES && input.available() == tokenLength)
        val tokenBytes = ByteArray(tokenLength)
        input.readFully(tokenBytes)
        val token = String(tokenBytes, StandardCharsets.UTF_8)
        require(token.toByteArray(StandardCharsets.UTF_8).contentEquals(tokenBytes) && TOKEN_PATTERN.matches(token))
        return RememberedSession(token, issuedAt, expiresAt)
    }

    private fun validate(value: RememberedSession, now: Long) {
        require(TOKEN_PATTERN.matches(value.accessToken))
        require(value.expiresAtMillis - value.issuedAtMillis == SESSION_LENGTH_MILLIS)
        require(value.issuedAtMillis >= 0 && value.issuedAtMillis <= now && now < value.expiresAtMillis)
    }

    private fun sha256(value: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").digest(value)

    private fun hex(value: ByteArray): String = value.joinToString("") { "%02x".format(it) }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val CIPHER = "AES/GCM/NoPadding"
        const val KEY_BITS = 256
        const val IV_BYTES = 12
        const val TAG_BYTES = 16
        const val TAG_BITS = TAG_BYTES * 8
        const val TOKEN_BYTES = 43
        const val MAX_ORIGIN_BYTES = 512
        const val MAX_PLAINTEXT_BYTES = 2 * 1024
        const val MAX_RECORD_BYTES = 4 * 1024
        const val SESSION_LENGTH_MILLIS = 86_400_000L
        const val FORMAT_MAGIC = 0x50485356
        const val FORMAT_VERSION = 1
        const val AAD_PREFIX = "PhotoHouse.SessionPersistence/v1\n"
        val TOKEN_PATTERN = Regex("[A-Za-z0-9_-]{43}")
    }
}
