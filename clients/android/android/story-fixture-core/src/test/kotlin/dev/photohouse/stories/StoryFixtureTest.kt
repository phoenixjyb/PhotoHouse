package dev.photohouse.stories

import org.junit.Assert.*
import org.junit.Test

class StoryFixtureTest {
    private fun editor() = StoryFixtureController().apply { activate(StoryRole.CONTRIBUTOR); open("sample-story"); edit() }
    @Test fun viewerCanReadButCannotCreateOrEdit() {
        val c = StoryFixtureController(); c.activate(); c.open("sample-story"); c.edit(); c.create()
        assertNotNull(c.state.value.selected); assertNull(c.state.value.draft); assertNull(c.beginSave())
    }
    @Test fun contributorCanEditOwnStoryButNotOtherAuthors() {
        val c = editor(); assertNotNull(c.state.value.draft); c.discard(); c.open("sample-private"); c.edit()
        assertNull(c.state.value.draft); assertFalse(c.state.value.selected!!.canViewHistory)
    }
    @Test fun ownerCanModerateOtherAuthors() {
        val c = StoryFixtureController(); c.activate(StoryRole.OWNER); c.open("sample-private"); c.edit()
        assertNotNull(c.state.value.draft)
    }
    @Test fun tvExcludesPrivateStoriesAndCannotWriteEvenWithOwnerRole() {
        val c = StoryFixtureController(); c.activate(StoryRole.OWNER, tv = true)
        assertEquals(3, c.state.value.cards.size); assertFalse(c.state.value.cards.any { it.id == "sample-private" })
        c.open("sample-story"); c.edit(); c.create(); assertNull(c.state.value.draft)
        assertTrue(c.state.value.cards.all { !it.canEdit && !it.canViewHistory })
    }
    @Test fun wrongPublicationRevisionAndWithdrawalCannotLeakIntoTv() {
        val c = StoryFixtureController(); c.activate(tv = true); val ticket = c.ticket()!!
        c.acceptCards(ticket, StoryFixtureController.examples().map { it.copy(publishedRevision = 2) }); assertTrue(c.state.value.cards.isEmpty())
        c.withdrawPublication(); c.acceptCards(ticket, StoryFixtureController.examples()); assertNull(c.state.value.scope)
    }
    @Test fun mixedChineseAndLiteralMarkupRemainWhole() {
        val c = editor(); val text = c.state.value.draft!!.content.text
        assertTrue(text.length > 4000); assertTrue(text.contains("我们坐着")); assertTrue(text.endsWith("<b>This stays literal</b>"))
        assertTrue(c.state.value.draft!!.content.valid())
    }
    @Test fun utf8LimitsDifferFromCharacterCountAndRejectMalformedText() {
        assertTrue(StoryText(text = "中".repeat(21845)).valid())
        assertFalse(StoryText(text = "中".repeat(21846)).valid())
        assertFalse(StoryText(text = "\uD800").valid()); assertFalse(StoryText(text = "text\u0000").valid())
        assertFalse(StoryText(text = " ").valid()); assertFalse(StoryText(title = "中".repeat(171), text = "ok").valid())
        assertTrue(StoryText(text = "😀".repeat(16384)).valid())
    }
    @Test fun familySearchIncludesLegacyButAiIsSeparate() {
        val c = StoryFixtureController(); c.activate(); c.search("blue train", StorySource.FAMILY)
        assertEquals(setOf("sample-story", "sample-legacy"), c.state.value.results.map { it.id }.toSet())
        c.search("blue train", StorySource.AI); assertEquals(listOf("sample-ai"), c.state.value.results.map { it.id })
    }
    @Test fun shortChineseAndMediaFilterWorkWithoutTranslating() {
        val c = StoryFixtureController(); c.activate(); c.search("湖边"); assertEquals(1, c.state.value.results.size)
        c.search("湖边", media = StoryMedia.VIDEO); assertTrue(c.state.value.results.isEmpty())
        c.search("%_"); assertTrue(c.state.value.results.isEmpty())
    }
    @Test fun oversizedSearchDoesNotReplaceExistingQuery() {
        val c = StoryFixtureController(); c.activate(); c.search("lake"); c.search("x".repeat(161))
        assertEquals("lake", c.state.value.query); assertEquals(StoryProblem.INVALID, c.state.value.problem)
    }
    @Test fun lostResponseRetainsIdenticalMutationAndBodyAndRetryCreatesOneRevision() {
        val c = editor(); c.update(StoryText(text = "My draft")); c.simulateSave(SaveSimulation.LOST_RESPONSE)
        val pending = c.state.value.pending!!; c.update(StoryText(text = "Must not alter pending request"))
        assertEquals(pending, c.beginSave()); assertEquals("My draft", c.state.value.draft!!.content.text)
        c.simulateSave(); assertEquals(2L, c.state.value.selected!!.revision); assertNull(c.state.value.draft)
        assertEquals(1, c.state.value.cards.count { it.id == "sample-story" })
    }
    @Test fun returnedNewerCurrentStoryIsDisplayedRatherThanOverwrittenByDraft() {
        val c = editor(); val m = c.beginSave()!!; val current = c.state.value.selected!!.copy(revision = 8, content = StoryText(text = "newer server text"))
        c.finishSave(m, current); assertEquals(current, c.state.value.selected); assertNull(c.state.value.draft)
    }
    @Test fun conflictPreservesDraftAndRequiresExplicitRevisionReview() {
        val c = editor(); c.update(StoryText(text = "Keep my words")); c.simulateSave(SaveSimulation.CONFLICT)
        assertEquals("Keep my words", c.state.value.draft!!.content.text); assertNull(c.beginSave())
        c.update(StoryText(text = "Refined draft")); assertEquals(StoryProblem.CONFLICT, c.state.value.problem); assertNull(c.beginSave())
        assertEquals(2L, c.state.value.latest!!.revision); c.useDraftAfterReview()
        assertEquals(2L, c.state.value.draft!!.revision); c.simulateSave(); assertEquals(3L, c.state.value.selected!!.revision)
    }
    @Test fun backRequiresDraftDiscardAndNeverPretendsToUndoUncertainSave() {
        val c = editor(); c.simulateSave(SaveSimulation.LOST_RESPONSE); val pending = c.state.value.pending!!
        assertTrue(c.back()); assertTrue(c.state.value.discardPrompt); c.keepEditing(); assertEquals(pending, c.state.value.pending)
        c.discard(); c.finishSave(pending, StoryFixtureController.examples().first()); assertNull(c.state.value.draft); assertFalse(c.state.value.saved)
    }
    @Test fun denialClearsDraftQueryAndLateSave() {
        val c = editor(); val m = c.beginSave()!!; c.deny(); c.finishSave(m, StoryFixtureController.examples().first())
        assertNull(c.state.value.scope); assertNull(c.state.value.pending); assertNull(c.state.value.draft); assertTrue(c.state.value.cards.isEmpty())
    }
    @Test fun librarySwitchAndBackgroundRejectOldReadAndSave() {
        val c = editor(); val read = c.ticket()!!; val write = c.beginSave()!!
        c.activate(library = "another-sample-library"); c.acceptCards(read, emptyList()); c.finishSave(write, StoryFixtureController.examples().first())
        assertEquals("another-sample-library", c.state.value.scope!!.library); assertNull(c.state.value.selected)
        val ticket = c.ticket()!!; c.clear(); c.acceptCards(ticket, StoryFixtureController.examples()); assertTrue(c.state.value.cards.isEmpty())
    }
}
