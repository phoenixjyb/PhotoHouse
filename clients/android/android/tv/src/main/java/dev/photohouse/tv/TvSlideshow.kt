package dev.photohouse.tv

import dev.photohouse.home.AssetKind
import dev.photohouse.home.HomeAsset
import dev.photohouse.home.HomeState

internal val TV_SLIDESHOW_INTERVALS_SECONDS = listOf(4, 8, 12)
internal const val TV_SLIDESHOW_DEFAULT_SECONDS = 8

/** Return the next prepared photo on this already loaded page. Never pick a video or original-only item. */
internal fun nextPreparedPagePhoto(state: HomeState): HomeAsset? {
    val feed = state.feed ?: return null
    val index = state.index
    if (index !in feed.items.indices) return null
    return feed.items.asSequence().drop(index + 1)
        .firstOrNull { it.kind == AssetKind.PHOTO && it.display != null }
}
