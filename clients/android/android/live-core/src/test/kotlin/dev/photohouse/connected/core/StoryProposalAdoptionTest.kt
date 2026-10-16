package dev.photohouse.connected.core

import dev.photohouse.protocol.Asset
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class StoryProposalAdoptionTest {
    private val storyId = "11111111-1111-1111-1111-111111111111"
    private val jobId = "55555555-5555-5555-5555-555555555555"
    private val contributionOne = "33333333-3333-3333-3333-333333333333"
    private val contributionTwo = "44444444-4444-4444-4444-444444444444"

    private fun story(canEdit: Boolean = true, revision: Long = 8) = SavedMemoryStory(
        id = storyId,
        libraryId = "family-a",
        revision = revision,
        createdAt = 10,
        updatedAt = 20,
        canEdit = canEdit,
        selectionRevision = "a".repeat(64),
        title = "Current title",
        theme = "everyday",
        language = "en",
        items = listOf(
            MemoryStoryAsset(Asset("101", "image", 1, 1, null, null, "/101"), emptyList()),
            MemoryStoryAsset(Asset("102", "image", 1, 1, null, null, "/102"), emptyList()),
        ),
        chapters = listOf(
            SavedMemoryStoryChapter("chapter-1", "One", "Existing one", listOf("101"), listOf("evidence-one")),
            SavedMemoryStoryChapter("chapter-2", "Two", "Existing two", listOf("102"), listOf("evidence-two")),
        ),
        questions = emptyList(),
    )

    private fun references(story: SavedMemoryStory = story()) = SavedMemoryStoryContributionReferences(
        story.id, story.libraryId, story.revision,
        listOf(
            SavedMemoryChapterContributionReferences("chapter-1", listOf(contributionOne)),
            SavedMemoryChapterContributionReferences("chapter-2", listOf(contributionTwo)),
        ),
    )

    private fun narrative(
        title: String = "AI title",
        firstSources: List<String> = listOf("evidence-one", "contribution-$contributionOne", "editorial-$storyId-chapter-1"),
        secondSources: List<String> = listOf("evidence-two"),
        firstNarration: String = "Suggested first wording",
        questions: List<String> = listOf("Which year was it?"),
        extraTopLevelKey: Boolean = false,
    ) = buildJsonObject {
        put("version", 1)
        put("title", title)
        put("chapters", buildJsonArray {
            add(chapter("chapter-1", firstNarration, firstSources))
            add(chapter("chapter-2", "Suggested second wording", secondSources))
        })
        put("questions", JsonArray(questions.map(::JsonPrimitive)))
        put("needs_review", true)
        if (extraTopLevelKey) put("extra", true)
    }

    private fun chapter(id: String, narration: String, sourceIds: List<String>) = buildJsonObject {
        put("id", id)
        put("narration", narration)
        put("source_ids", JsonArray(sourceIds.map(::JsonPrimitive)))
    }

    private fun job(
        kind: String = "narrative",
        state: String = "ready",
        baseRevision: Long = 8,
        result: JsonObject? = if (kind == "chat") chatResult() else narrative(),
    ) = MemoryJob(jobId, kind, state, 10, 11, 100, null, result, true, baseRevision)

    private fun chatResult(proposal: JsonObject = narrative()) = buildJsonObject {
        put("version", 1)
        put("kind", "proposal")
        put("reply", "A proposal is ready for review.")
        put("source_ids", buildJsonArray { add("evidence-one") })
        put("questions", buildJsonArray { add("Which year was it?") })
        put("proposal", proposal)
    }

    @Test fun adoptionUsesCurrentChapterOrderAndPreservesReviewedKnownSources() {
        val result = storyProposalAdoptionDraft(
            story(), references(), job(), listOf("chapter-2", "chapter-1"), adoptTitle = true,
        )

        assertNotNull(result)
        assertEquals("AI title", result!!.title)
        assertEquals(listOf("chapter-1", "chapter-2"), result.chapters.map { it.id })
        assertEquals(
            listOf("evidence-one", "contribution-$contributionOne", "editorial-$storyId-chapter-1"),
            result.chapters.first().sourceIds,
        )
        assertEquals(listOf("Which year was it?"), result.questions)
        assertEquals(8L, result.revision)
        assertNull(storyProposalAdoptionDraft(story(), references(), job(), listOf("chapter-1"), adoptTitle = false)?.title)
    }

    @Test fun acceptsNarrativeAndChatProposalJobsOnly() {
        val current = story()
        val refs = references(current)
        val narrativeDraft = storyProposalAdoptionDraft(current, refs, job("narrative"), listOf("chapter-1"), false)
        val chatDraft = storyProposalAdoptionDraft(current, refs, job("chat"), listOf("chapter-1"), false)
        assertEquals("narrative", narrativeDraft?.jobKind)
        assertEquals("chat", chatDraft?.jobKind)
        assertNull(storyProposalAdoptionDraft(current, refs, job("chat", result = chatResult(narrative(extraTopLevelKey = true))), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(current, refs, job("chat", result = chatResult().let { JsonObject(it + ("kind" to JsonPrimitive("answer"))) }), listOf("chapter-1"), false))
    }

    @Test fun rejectsRevisionStateReadOnlyAndIncompleteReferenceMismatches() {
        val current = story()
        val refs = references(current)
        assertNull(storyProposalAdoptionDraft(current, refs, job(baseRevision = 7), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(current, refs, job(state = "stale"), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(story(canEdit = false), refs, job(), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(current, refs.copy(revision = 7), job(), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(current, refs.copy(chapters = refs.chapters.reversed()), job(), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(current, refs, job().copy(id = "not-a-job-id"), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(current, refs, job(), emptyList(), false))
        assertNull(storyProposalAdoptionDraft(current, refs, job(), listOf("chapter-1", "chapter-1"), false))
    }

    @Test fun refusesUnlinkedAndCrossChapterCitationsButIgnoresUnselectedBadChapterSources() {
        val current = story()
        val refs = references(current)
        val unselectedBadChapter = narrative(secondSources = listOf("evidence-one"))
        assertNotNull(storyProposalAdoptionDraft(current, refs, job(result = unselectedBadChapter), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(current, refs, job(result = unselectedBadChapter), listOf("chapter-2"), false))
        assertNull(storyProposalAdoptionDraft(current, refs, job(result = narrative(firstSources = listOf("foreign-source"))), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(current, refs, job(result = narrative(firstSources = listOf("contribution-$contributionTwo"))), listOf("chapter-1"), false))
    }

    @Test fun appliesUtf8ControlAndAdoptedTitleBounds() {
        val current = story()
        val refs = references(current)
        assertNull(storyProposalAdoptionDraft(current, refs, job(result = narrative(title = "x".repeat(161))), listOf("chapter-1"), true))
        assertNull(storyProposalAdoptionDraft(current, refs, job(result = narrative(title = "bad\ntitle")), listOf("chapter-1"), true))
        assertNull(storyProposalAdoptionDraft(current, refs, job(result = narrative(title = "bad\u2028title")), listOf("chapter-1"), true))
        assertNull(storyProposalAdoptionDraft(current, refs, job(result = narrative(firstNarration = "😀".repeat(1501))), listOf("chapter-1"), false))
        assertNotNull(storyProposalAdoptionDraft(current, refs, job(result = narrative(title = "x".repeat(161))), listOf("chapter-1"), false))
        assertNull(storyProposalAdoptionDraft(current, refs, job(result = narrative(firstNarration = "line\u0001break")), listOf("chapter-1"), false))
    }

    @Test fun detachesAndFreezesEveryReturnedCollection() {
        val mutableSources = mutableListOf("evidence-one")
        val mutableQuestions = mutableListOf("Who remembers?")
        val result = narrative().toMutableMap().also { map ->
            map["chapters"] = JsonArray(listOf(chapter("chapter-1", "Edited", mutableSources)))
            map["questions"] = JsonArray(mutableQuestions.map(::JsonPrimitive))
        }
        // Restore the full chapter sequence after setting up mutable input collections.
        result["chapters"] = JsonArray(listOf(
            chapter("chapter-1", "Edited", mutableSources), chapter("chapter-2", "Second", listOf("evidence-two")),
        ))
        val draft = storyProposalAdoptionDraft(story(), references(), job(result = JsonObject(result)), listOf("chapter-1"), false)!!
        mutableSources += "foreign-after-return"
        mutableQuestions += "Another question"

        assertEquals(listOf("evidence-one"), draft.chapters.first().sourceIds)
        assertEquals(listOf("Who remembers?"), draft.questions)
        assertThrows(UnsupportedOperationException::class.java) { (draft.chapters as MutableList).clear() }
        assertThrows(UnsupportedOperationException::class.java) { (draft.questions as MutableList).clear() }
        assertThrows(UnsupportedOperationException::class.java) { (draft.chapters.first().sourceIds as MutableList).clear() }
    }
}
