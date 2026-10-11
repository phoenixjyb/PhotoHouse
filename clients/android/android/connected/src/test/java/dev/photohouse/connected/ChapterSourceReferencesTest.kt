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
        val shared = MemoryStoryEvidence("family-33333333-3333-4333-8333-333333333333", "family", "shared", "Shared", 4, "99", "Grandma")
        fun asset(id: String) = Asset(id, "image", 10, 10, null, null, "/assets/$id/thumbnail?library=family", null)
        val story = SavedMemoryStory(
            "11111111-1111-1111-1111-111111111111", "family", 1, 1, 1, false, "a".repeat(64), "title", "everyday", "zh",
            listOf(MemoryStoryAsset(asset("1"), listOf(a, b, uncited, shared)),
                MemoryStoryAsset(asset("2"), listOf(shared)), MemoryStoryAsset(asset("99"), listOf(shared)),
                MemoryStoryAsset(asset("3"), listOf(outside))),
            listOf(SavedMemoryStoryChapter("chapter", "chapter", "narration", listOf("1", "2"),
                listOf(shared.id, "caption-2", "caption-1", "caption-4"))),
            emptyList(),
        )

        val sources = chapterSourceReferences(story.chapters.single(), story)
        assertEquals(listOf(shared, b, a), sources.map { it.evidence })
        assertEquals(listOf(true, false, false), sources.map { it.originOutsideChapter })
        val includesOrigin = chapterSourceReferences(story.chapters.single().copy(assetIds = listOf("1", "2", "99")), story)
        assertEquals(false, includesOrigin.first().originOutsideChapter)
        assertEquals(emptyList<ChapterEvidenceReference>(), chapterSourceReferences(story.chapters.single().copy(evidenceIds = emptyList()), story))
    }
}
