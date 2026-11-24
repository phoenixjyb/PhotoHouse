package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import java.util.Collections

/** Volatile UI state for one explicit, chapter-scoped assistant frame search. */
data class StoryChapterFrameSearchState(
    val chapterId: String,
    val remaining: Int,
    val results: List<Asset> = emptyList(),
    val selectedAssetIds: List<String> = emptyList(),
    val searched: Boolean = false,
    val searching: Boolean = false,
    val adding: Boolean = false,
    val added: Boolean = false,
    val error: Boolean = false,
    val hasMore: Boolean = false,
    val reply: String? = null,
)

internal data class StoryChapterFrameAppendPlan(
    val selectedAssetIds: List<String>,
    val chapters: List<SavedMemoryStoryChapter>,
)

/** Pure layout builder. Callers must supply fresh preview assets and an authorized profile. */
internal object StoryChapterFrameSearch {
    const val MAX_ASSETS = 24
    const val MAX_CHAPTERS = 6
    const val MAX_ASSETS_PER_CHAPTER = 4

    fun remaining(assetCount: Int): Int = (MAX_ASSETS - assetCount).coerceAtLeast(0)

    fun remaining(assetCount: Int, chapterAssetCount: Int): Int = minOf(
        remaining(assetCount), (MAX_ASSETS_PER_CHAPTER - chapterAssetCount).coerceAtLeast(0),
    )

    fun append(
        currentAssetIds: List<String>,
        chapters: List<SavedMemoryStoryChapter>,
        chapterId: String,
        addedAssetIds: List<String>,
    ): StoryChapterFrameAppendPlan? {
        if (currentAssetIds.isEmpty() || currentAssetIds.size > MAX_ASSETS ||
            currentAssetIds.distinct().size != currentAssetIds.size ||
            chapters.isEmpty() || chapters.size > MAX_CHAPTERS ||
            chapters.map { it.id } != (1..chapters.size).map { "chapter-$it" } ||
            chapters.any { it.assetIds.isEmpty() || it.assetIds.size > MAX_ASSETS_PER_CHAPTER } ||
            chapters.flatMap { it.assetIds } != currentAssetIds) return null

        val targetIndex = chapters.indexOfFirst { it.id == chapterId }
        if (targetIndex < 0 || addedAssetIds.isEmpty() ||
            addedAssetIds.distinct().size != addedAssetIds.size ||
            addedAssetIds.any { !it.matches(Regex("[1-9][0-9]{0,18}")) || it.toLongOrNull()?.toString() != it || it in currentAssetIds }) return null

        val target = chapters[targetIndex]
        val capacity = remaining(currentAssetIds.size, target.assetIds.size)
        if (addedAssetIds.size > capacity) return null

        val firstChapterAssets = addedAssetIds.size
        val nextChapters = chapters.toMutableList()
        nextChapters[targetIndex] = target.copy(
            assetIds = immutable(target.assetIds + addedAssetIds.take(firstChapterAssets)),
        )
        val insertAt = chapters.take(targetIndex + 1).sumOf { it.assetIds.size }
        val selected = immutable(currentAssetIds.take(insertAt) + addedAssetIds + currentAssetIds.drop(insertAt))
        if (nextChapters.flatMap { it.assetIds } != selected || nextChapters.size > MAX_CHAPTERS) return null
        return StoryChapterFrameAppendPlan(selected, immutable(nextChapters.map { it.copy(
            assetIds = immutable(it.assetIds), evidenceIds = immutable(it.evidenceIds),
        ) }))
    }

    private fun <T> immutable(values: List<T>): List<T> = Collections.unmodifiableList(ArrayList(values))
}
