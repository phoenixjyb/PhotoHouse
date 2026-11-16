package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test

class StoryChapterFrameSearchTest {
    @Test fun appendsWithinAnyChapterAndPreservesExistingChapterIdsAndOrder() {
        val chapters = listOf(
            SavedMemoryStoryChapter("chapter-1", "Opening", "First words", listOf("1"), listOf("caption-1")),
            SavedMemoryStoryChapter("chapter-2", "Later", "Later words", listOf("2", "3"), emptyList()),
        )
        val plan = StoryChapterFrameSearch.append(listOf("1", "2", "3"), chapters, "chapter-1", listOf("4"))

        assertNotNull(plan)
        assertEquals(listOf("chapter-1", "chapter-2"), plan?.chapters?.map { it.id })
        assertEquals(listOf("1", "4", "2", "3"), plan?.selectedAssetIds)
        assertEquals(listOf("1", "4"), plan?.chapters?.get(0)?.assetIds)
        assertEquals("First words", plan?.chapters?.get(0)?.narration)
        assertEquals(listOf("2", "3"), plan?.chapters?.get(1)?.assetIds)
        assertEquals(listOf("1", "2", "3").filter { it in plan!!.selectedAssetIds }, listOf("1", "2", "3"))
    }

    @Test fun remainingIsBoundedByBothChapterAndStoryLimits() {
        assertEquals(1, StoryChapterFrameSearch.remaining(assetCount = 23, chapterAssetCount = 2))
        assertEquals(1, StoryChapterFrameSearch.remaining(assetCount = 10, chapterAssetCount = 3))
        assertEquals(0, StoryChapterFrameSearch.remaining(assetCount = 24, chapterAssetCount = 1))
        assertEquals(0, StoryChapterFrameSearch.remaining(assetCount = 10, chapterAssetCount = 4))
    }

    @Test fun appendRejectsChapterOverflowDuplicateIdsAndReorderedBase() {
        val chapters = listOf(
            SavedMemoryStoryChapter("chapter-1", "Opening", "", listOf("1", "2", "3", "4"), emptyList()),
            SavedMemoryStoryChapter("chapter-2", "Later", "", listOf("5"), emptyList()),
        )
        assertNull(StoryChapterFrameSearch.append(listOf("1", "2", "3", "4", "5"), chapters, "chapter-1", listOf("6")))
        assertNull(StoryChapterFrameSearch.append(listOf("1", "2", "3", "4", "5"), chapters, "chapter-2", listOf("5")))
        assertNull(StoryChapterFrameSearch.append(listOf("2", "1", "3", "4", "5"), chapters, "chapter-2", listOf("6")))
    }
}
