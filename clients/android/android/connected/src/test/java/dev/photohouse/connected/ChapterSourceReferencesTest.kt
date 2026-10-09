package dev.photohouse.connected

import dev.photohouse.connected.core.MemoryStoryAsset
import dev.photohouse.connected.core.MemoryStoryEvidence
import dev.photohouse.connected.core.SavedMemoryStory
import dev.photohouse.connected.core.SavedMemoryStoryChapter
import dev.photohouse.protocol.Asset
import org.junit.Assert.assertEquals
import org.junit.Test

class ChapterSourceReferencesTest {
    @Test fun referencesAreChapterScopedCitationOrderedAndDeduplicated() {
        val a = MemoryStoryEvidence("caption-1", "family", "first", "A")
        val b = MemoryStoryEvidence("caption-2", "ai", "second", "B")
        val uncited = MemoryStoryEvidence("caption-3", "family", "third", "C")
        val outside = MemoryStoryEvidence("caption-4", "ai", "outside", "D")
        fun asset(id: String) = Asset(id, "image", 10, 10, null, null, "/assets/$id/thumbnail?library=family", null)
        val story = SavedMemoryStory(
            "11111111-1111-1111-1111-111111111111", "family", 1, 1, 1, false, "a".repeat(64), "title", "everyday", "zh",
            listOf(MemoryStoryAsset(asset("1"), listOf(a, b, uncited)), MemoryStoryAsset(asset("2"), listOf(outside))),
            listOf(SavedMemoryStoryChapter("chapter", "chapter", "narration", listOf("1"), listOf("caption-2", "caption-1", "caption-2", "caption-4"))),
            emptyList(),
        )

        assertEquals(listOf(b, a), chapterSourceReferences(story.chapters.single(), story))
        assertEquals(emptyList<MemoryStoryEvidence>(), chapterSourceReferences(story.chapters.single().copy(evidenceIds = emptyList()), story))
    }
}
