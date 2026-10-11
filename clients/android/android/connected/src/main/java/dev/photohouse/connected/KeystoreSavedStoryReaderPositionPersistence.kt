package dev.photohouse.connected

import android.content.Context
import dev.photohouse.connected.core.SavedStoryReaderPosition
import dev.photohouse.connected.core.SavedStoryReaderPositionPersistence
import dev.photohouse.connected.core.SavedStoryReaderPositions

/** Encrypted, app-private saved-story location metadata. No story content is persisted. */
internal class KeystoreSavedStoryReaderPositionPersistence(
    context: Context,
    configuredOrigin: String,
) : SavedStoryReaderPositionPersistence {
    private val records = EncryptedPositionRecordStore(context, configuredOrigin, PositionRecordDomain.STORY)

    @Synchronized
    override fun load(accountId: String): List<SavedStoryReaderPosition> {
        SavedStoryReaderPositions.validated(accountId, emptyList())
        val plaintext = records.read(accountId) ?: return emptyList()
        return try {
            SavedStoryReaderPositions.validated(accountId, SavedStoryReaderPositions.decodeRecord(accountId, plaintext))
        } catch (_: Exception) {
            runCatching { records.clear(accountId) }
            emptyList()
        } finally {
            plaintext.fill(0)
        }
    }

    @Synchronized
    override fun save(accountId: String, position: SavedStoryReaderPosition) {
        savePositions(accountId, SavedStoryReaderPositions.upsert(accountId, load(accountId), position))
    }

    @Synchronized
    override fun remove(accountId: String, libraryId: String, storyId: String) {
        savePositions(accountId, SavedStoryReaderPositions.without(accountId, load(accountId), libraryId, storyId))
    }

    @Synchronized
    override fun clear(accountId: String) {
        SavedStoryReaderPositions.validated(accountId, emptyList())
        records.clear(accountId)
    }

    private fun savePositions(accountId: String, positions: List<SavedStoryReaderPosition>) {
        SavedStoryReaderPositions.validated(accountId, positions)
        if (positions.isEmpty()) {
            records.clear(accountId)
            return
        }
        val plaintext = SavedStoryReaderPositions.encodeRecord(accountId, positions)
        try {
            records.write(accountId, plaintext)
        } catch (failure: Exception) {
            throw IllegalStateException("Unable to save saved-story reading positions", failure)
        } finally {
            plaintext.fill(0)
        }
    }
}
