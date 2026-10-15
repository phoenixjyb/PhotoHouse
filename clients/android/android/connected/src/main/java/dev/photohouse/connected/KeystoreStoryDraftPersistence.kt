package dev.photohouse.connected

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import dev.photohouse.connected.core.StoryDraftPersistence
import dev.photohouse.connected.core.StoryDraftRecord
import dev.photohouse.connected.core.StoryDraftRecordCodec
import dev.photohouse.connected.core.StoryDraftScope
import dev.photohouse.connected.core.StoryDraftStorageException
import java.io.File
import java.io.FileInputStream
import java.io.FileNotFoundException
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Encrypted, app-private authored story drafts; media and server preview data are never stored. */
internal class KeystoreStoryDraftPersistence(context: Context, configuredOrigin: String) : StoryDraftPersistence {
    private val directory = context.applicationContext.noBackupFilesDir
    private val origin = configuredOrigin.also {
        require(it.isNotBlank() && it.length <= MAX_ORIGIN_CHARS && it.none(Char::isISOControl))
    }
    private val originHash = hex(digest(origin))
    private val alias = "photohouse.story-draft.$originHash"
    private val filePrefix = "photohouse-story-draft-$originHash-"

    override fun load(scope: StoryDraftScope): StoryDraftRecord? = synchronized(STORAGE_LOCK) {
        loadLocked(scope)
    }

    private fun loadLocked(scope: StoryDraftScope): StoryDraftRecord? {
        validateScope(scope)
        val file = file(scope)
        var record: ByteArray? = null
        var plaintext: ByteArray? = null
        var aad: ByteArray? = null
        try {
            record = readBounded(file)
            if (record.isEmpty()) {
                if (file.baseFile.exists()) throw StoryDraftStorageException("Saved story draft is empty")
                return null
            }
            require(record.size in IV_BYTES + TAG_BYTES + 1..MAX_RECORD_BYTES + IV_BYTES + TAG_BYTES)
            val key = existingKey() ?: throw StoryDraftStorageException("Saved story draft key is unavailable")
            val iv = record.copyOfRange(0, IV_BYTES)
            val cipher = Cipher.getInstance(CIPHER)
            cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, iv))
            aad = associatedData(scope)
            cipher.updateAAD(aad)
            plaintext = cipher.doFinal(record, IV_BYTES, record.size - IV_BYTES)
            val decoded = StoryDraftRecordCodec.decode(scope, plaintext)
            return decoded
        } catch (missing: FileNotFoundException) {
            if (hasSlotFiles(file)) throw StoryDraftStorageException("Saved story draft file is unreadable", missing)
            return null
        } catch (failure: StoryDraftStorageException) {
            throw failure
        } catch (failure: Exception) {
            // Fail closed but retain the encrypted bytes for explicit recovery or deletion.
            throw StoryDraftStorageException("Saved story draft could not be read", failure)
        } finally {
            record?.fill(0)
            plaintext?.fill(0)
            aad?.fill(0)
        }
    }

    override fun write(record: StoryDraftRecord, expectedRevision: Long?, expectedRecordId: String?): StoryDraftRecord =
        synchronized(STORAGE_LOCK) { writeLocked(record, expectedRevision, expectedRecordId) }

    private fun writeLocked(record: StoryDraftRecord, expectedRevision: Long?, expectedRecordId: String?): StoryDraftRecord {
        validateScope(record.scope)
        try {
            val current = load(record.scope)
            if (expectedRevision == null) {
                if (current != null) throw StoryDraftStorageException("A story draft already occupies this scope")
                if (occupiedSlots() >= StoryDraftRecordCodec.MAX_SLOTS)
                    throw StoryDraftStorageException("The local story draft limit is full")
            } else if (current?.revision != expectedRevision || current.recordId != expectedRecordId) {
                throw StoryDraftStorageException("The local story draft changed; reload it before saving")
            }
            val nextRevision = (expectedRevision ?: 0L) + 1L
            val next = record.copy(revision = nextRevision)
            val plaintext = StoryDraftRecordCodec.encode(next)
            var iv: ByteArray? = null
            var encrypted: ByteArray? = null
            var output: ByteArray? = null
            var aad: ByteArray? = null
            try {
                val cipher = Cipher.getInstance(CIPHER)
                cipher.init(Cipher.ENCRYPT_MODE, writeKey())
                iv = cipher.iv
                require(iv.size == IV_BYTES)
                aad = associatedData(record.scope)
                cipher.updateAAD(aad)
                encrypted = cipher.doFinal(plaintext)
                output = iv + encrypted
                require(output.size <= MAX_RECORD_BYTES + IV_BYTES + TAG_BYTES)
                writeAtomically(file(record.scope), output)
            } finally {
                plaintext.fill(0)
                iv?.fill(0)
                encrypted?.fill(0)
                output?.fill(0)
                aad?.fill(0)
            }
            return next
        } catch (failure: StoryDraftStorageException) {
            throw failure
        } catch (failure: Exception) {
            throw StoryDraftStorageException("Unable to save local story draft", failure)
        }
    }

    override fun delete(scope: StoryDraftScope, expectedRecordId: String, expectedRevision: Long): Boolean =
        synchronized(STORAGE_LOCK) { deleteLocked(scope, expectedRecordId, expectedRevision) }

    private fun deleteLocked(scope: StoryDraftScope, expectedRecordId: String, expectedRevision: Long): Boolean {
        validateScope(scope)
        return try {
            val current = load(scope) ?: return false
            if (current.revision != expectedRevision || current.recordId != expectedRecordId) return false
            file(scope).delete()
            true
        } catch (failure: StoryDraftStorageException) {
            throw failure
        } catch (failure: Exception) {
            throw StoryDraftStorageException("Unable to delete local story draft", failure)
        }
    }

    override fun unreadableFingerprint(scope: StoryDraftScope): String? = synchronized(STORAGE_LOCK) {
        validateScope(scope)
        try { slotFingerprint(file(scope)) } catch (failure: Exception) {
            throw StoryDraftStorageException("Unable to inspect unreadable local story draft", failure)
        }
    }

    override fun deleteUnreadable(scope: StoryDraftScope, expectedFingerprint: String): Boolean =
        synchronized(STORAGE_LOCK) { deleteUnreadableLocked(scope, expectedFingerprint) }

    private fun deleteUnreadableLocked(scope: StoryDraftScope, expectedFingerprint: String): Boolean {
        validateScope(scope)
        return try {
            val target = file(scope)
            if (slotFingerprint(target) != expectedFingerprint) return false
            val stillReadable = try { loadLocked(scope); true } catch (_: StoryDraftStorageException) { false }
            if (stillReadable || slotFingerprint(target) != expectedFingerprint) return false
            val existed = hasSlotFiles(target)
            target.delete()
            existed
        } catch (failure: Exception) {
            throw StoryDraftStorageException("Unable to delete unreadable local story draft", failure)
        }
    }

    override fun occupiedSlots(): Int = synchronized(STORAGE_LOCK) {
        occupiedSlotsLocked()
    }

    private fun occupiedSlotsLocked(): Int {
        val slots = directory.listFiles().orEmpty().mapNotNull { file ->
            if (!file.name.startsWith(filePrefix)) null
            else normalizeAtomicName(file.name)
        }.toSet()
        return slots.size.coerceAtMost(StoryDraftRecordCodec.MAX_SLOTS + 1)
    }

    private fun validateScope(scope: StoryDraftScope) {
        validateAccount(scope.accountId)
        require(scope.libraryId.isNotBlank() && scope.libraryId.length <= 128 && scope.libraryId.none(Char::isISOControl))
    }

    private fun validateAccount(account: String) {
        require(account.isNotBlank() && account.codePointCount(0, account.length) <= MAX_ACCOUNT_CODE_POINTS &&
            account.none(Char::isISOControl))
        require(runCatching {
            Charsets.UTF_8.newEncoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(account))
        }.isSuccess)
    }

    private fun file(scope: StoryDraftScope): AtomicFile = AtomicFile(directory.resolve(
        filePrefix + hex(digest(scope.libraryId)) + "-" + hex(digest(scope.accountId))))

    private fun hasSlotFiles(file: AtomicFile): Boolean {
        val base = file.baseFile
        return base.exists() || base.resolveSibling(base.name + ".bak").exists() ||
            base.resolveSibling(base.name + ".new").exists()
    }

    private fun normalizeAtomicName(raw: String): String {
        var name = raw
        while (name.endsWith(".bak") || name.endsWith(".new")) {
            name = name.removeSuffix(".bak").removeSuffix(".new")
        }
        return name
    }

    private fun slotFingerprint(file: AtomicFile): String? {
        val base = file.baseFile
        val parts = listOf(base, base.resolveSibling(base.name + ".bak"), base.resolveSibling(base.name + ".new"))
            .filter(File::exists)
        if (parts.isEmpty()) return null
        val digest = MessageDigest.getInstance("SHA-256")
        parts.sortedBy(File::getName).forEach { part ->
            digest.update(part.name.toByteArray(StandardCharsets.UTF_8))
            digest.update(byteArrayOf(0))
            digest.update(part.length().toString().toByteArray(StandardCharsets.US_ASCII))
            digest.update(byteArrayOf(0))
            FileInputStream(part).use { input ->
                val buffer = ByteArray(8192)
                try {
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        if (read > 0) digest.update(buffer, 0, read)
                    }
                } finally { buffer.fill(0) }
            }
        }
        return hex(digest.digest())
    }

    private fun associatedData(scope: StoryDraftScope) =
        ("PhotoHouse.LocalStoryDraft/v1\n" + origin + "\n" + scope.accountId + "\n" + scope.libraryId)
            .toByteArray(StandardCharsets.UTF_8)

    private fun readBounded(file: AtomicFile): ByteArray {
        val buffer = ByteArray(MAX_RECORD_BYTES + IV_BYTES + TAG_BYTES + 1)
        try {
            var count = 0
            file.openRead().use { input ->
                while (count < buffer.size) {
                    val read = input.read(buffer, count, buffer.size - count)
                    if (read < 0) break
                    if (read > 0) count += read
                }
            }
            require(count <= MAX_RECORD_BYTES + IV_BYTES + TAG_BYTES)
            return buffer.copyOf(count)
        } finally {
            buffer.fill(0)
        }
    }

    private fun writeAtomically(file: AtomicFile, bytes: ByteArray) {
        val stream = file.startWrite()
        try {
            stream.write(bytes)
            stream.flush()
            file.finishWrite(stream)
        } catch (failure: Exception) {
            try { file.failWrite(stream) } catch (cleanup: Exception) { failure.addSuppressed(cleanup) }
            throw failure
        }
    }

    private fun existingKey(): SecretKey? = (KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        .getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.secretKey

    private fun writeKey(): SecretKey = existingKey() ?: run {
        if (occupiedSlotsLocked() > 0) throw StoryDraftStorageException("Saved story draft key is unavailable")
        createKey()
    }

    private fun createKey(): SecretKey = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE).apply {
        init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
    }.generateKey()

    private fun digest(value: String): ByteArray = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(StandardCharsets.UTF_8))
    private fun hex(value: ByteArray) = value.joinToString("") { "%02x".format(it) }

    private companion object {
        val STORAGE_LOCK = Any()
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val CIPHER = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
        const val TAG_BITS = 128
        const val TAG_BYTES = 16
        const val MAX_ORIGIN_CHARS = 512
        const val MAX_ACCOUNT_CODE_POINTS = 256
        const val MAX_RECORD_BYTES = StoryDraftRecordCodec.MAX_RECORD_BYTES
    }
}
