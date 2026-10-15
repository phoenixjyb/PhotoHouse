package dev.photohouse.connected

import android.content.Context
import dev.photohouse.connected.core.MemoryBookReaderPosition
import dev.photohouse.connected.core.MemoryBookReaderPositionPersistence
import dev.photohouse.connected.core.MemoryBookReaderPositions

/** Encrypted, app-private memoir reader location metadata. No memoir text or audio is persisted. */
internal class KeystoreMemoryBookReaderPositionPersistence(
    context: Context,
    configuredOrigin: String,
) : MemoryBookReaderPositionPersistence {
    private val records = EncryptedPositionRecordStore(context, configuredOrigin, PositionRecordDomain.MEMOIR)

    @Synchronized
    override fun load(accountId: String): List<MemoryBookReaderPosition> {
        MemoryBookReaderPositions.validated(accountId, emptyList())
        val plaintext = records.read(accountId) ?: return emptyList()
        return try {
            MemoryBookReaderPositions.validated(accountId, MemoryBookReaderPositions.decodeRecord(accountId, plaintext))
        } catch (_: Exception) {
            runCatching { records.clear(accountId) }
            emptyList()
        } finally {
            plaintext.fill(0)
        }
    }

    @Synchronized
    override fun save(accountId: String, position: MemoryBookReaderPosition) {
        savePositions(accountId, MemoryBookReaderPositions.upsert(accountId, load(accountId), position))
    }

    @Synchronized
    override fun remove(accountId: String, libraryId: String, bookId: String) {
        savePositions(accountId, MemoryBookReaderPositions.without(accountId, load(accountId), libraryId, bookId))
    }

    @Synchronized
    override fun clear(accountId: String) {
        MemoryBookReaderPositions.validated(accountId, emptyList())
        records.clear(accountId)
    }

    private fun savePositions(accountId: String, positions: List<MemoryBookReaderPosition>) {
        MemoryBookReaderPositions.validated(accountId, positions)
        if (positions.isEmpty()) {
            records.clear(accountId)
            return
        }
        val plaintext = MemoryBookReaderPositions.encodeRecord(accountId, positions)
        try {
            records.write(accountId, plaintext)
        } catch (failure: Exception) {
            throw IllegalStateException("Unable to save memoir reading positions", failure)
        } finally {
            plaintext.fill(0)
        }
    }
}
