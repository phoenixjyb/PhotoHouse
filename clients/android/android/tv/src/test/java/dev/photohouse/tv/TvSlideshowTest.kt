package dev.photohouse.tv

import dev.photohouse.home.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class TvSlideshowTest {
    private fun photo(id: Int, display: Boolean, original: Boolean = false) = HomeAsset(
        id = id, caption = "photo $id", grid = null,
        display = if (display) Preview(1, 1, 1, "0".repeat(64), "/$id") else null,
        original = if (original) HomeOriginal("image/jpeg", 1, 1, 1, "/original/$id") else null)

    private fun state(items: List<HomeAsset>, selected: Int): HomeState = HomeState(
        feed = HomeFeed(1, "page-1", "Synthetic page", 1, items.size, items.size, false, items),
        selected = selected, covered = false)

    @Test fun intervalsStaySmallAndDefaultToEightSeconds() {
        assertEquals(listOf(4, 8, 12), TV_SLIDESHOW_INTERVALS_SECONDS)
        assertEquals(8, TV_SLIDESHOW_DEFAULT_SECONDS)
    }

    @Test fun progressionSkipsVideosOriginalOnlyAndUnpreparedPhotos() {
        val video = HomeAsset(2, "video", null, null, AssetKind.VIDEO,
            video = HomeVideo(1, 1, 1, 1, "0".repeat(64), "/video", null))
        val items = listOf(photo(1, true), video, photo(3, false, original = true),
            photo(4, false), photo(5, true), photo(6, true))
        assertEquals(5, nextPreparedPagePhoto(state(items, selected = 1))?.id)
        assertEquals(6, nextPreparedPagePhoto(state(items, selected = 5))?.id)
    }

    @Test fun lastPreparedPhotoEndsWithinLoadedPage() {
        val items = listOf(photo(1, true), photo(2, false, original = true),
            photo(3, false), HomeAsset(4, "video", null, null, AssetKind.VIDEO))
        assertNull(nextPreparedPagePhoto(state(items, selected = 1)))
        assertNull(nextPreparedPagePhoto(state(items, selected = 99)))
        assertNull(nextPreparedPagePhoto(HomeState(selected = 1)))
    }
}
