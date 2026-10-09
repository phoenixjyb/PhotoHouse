package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test

class MemoryBookChapterDiscussionTest {
    private val context = MemoryBookChapterDiscussionContext("account", 1, "family", 1,
        "book", 1, "story", 3, "chapter-1", 0, "Garden", "Morning", "conversation")

    @Test fun boundedMetadataGeneratesAnEditableQuestionInEitherLanguage() {
        for (zh in listOf(true, false)) {
            val question = memoryBookChapterDiscussionQuestion(context.copy(
                storyTitle = "中".repeat(170), chapterTitle = "a".repeat(512)), zh)!!
            assertTrue(question.toByteArray(Charsets.UTF_8).size <= 4096)
            assertTrue(question.contains("a".repeat(512)))
        }
    }

    @Test fun invalidTitlesAndChapterBoundsDoNotProduceAQuestion() {
        for (title in listOf("", "  ", "bad\u0000title", "中".repeat(171), "a".repeat(513))) {
            assertNull(memoryBookChapterDiscussionQuestion(context.copy(storyTitle = title), true))
            assertNull(memoryBookChapterDiscussionQuestion(context.copy(chapterTitle = title), false))
        }
        for (index in listOf(-1, 6, Int.MAX_VALUE)) {
            assertNull(memoryBookChapterDiscussionQuestion(context.copy(chapterIndex = index), true))
        }
        assertNotNull(memoryBookChapterDiscussionQuestion(context.copy(chapterIndex = 5), false))
    }
}
