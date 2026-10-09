package dev.photohouse.home

import org.junit.Assert.*
import org.junit.Test

class DiscoveryDraftTest {
    private val options = DiscoveryOptions(DiscoveryField.entries.toSet(),
        people = listOf(DiscoveryChoice("person-a", "Sample A", listOf("示例甲")), DiscoveryChoice("person-b", "Sample B")),
        themes = listOf(DiscoveryChoice("theme-a", "Celebrations")), topics = listOf(DiscoveryChoice("topic-a", "Outdoors")),
        tags = listOf(DiscoveryChoice("tag-a", "Picnic")), places = listOf(DiscoveryChoice("place-a", "Sample garden")),
        peopleAll = true, tagsAll = true)
    @Test fun aliasesAreLabelsAndStableIdsFormCombinedCriteria() {
        val draft = DiscoveryDraft(text = " picnic ", people = setOf("person-a", "person-b"), peopleMatch = MatchMode.ALL,
            from = "2024-02-29", through = "2025-01-01", tags = setOf("tag-a"), tagsMatch = MatchMode.ALL,
            place = "place-a", media = AssetKind.PHOTO)
        assertNull(draft.issue(options)); assertEquals("picnic", draft.normalized().text); assertEquals(6, draft.count)
        assertEquals(DraftIssue.UNKNOWN_CHOICE, draft.copy(people = setOf("示例甲")).issue(options))
    }
    @Test fun strictDatesRejectImpossibleAndInvertedRangesWithoutGuessing() {
        for (value in listOf("2023-02-29", "2024-2-1", "0000-01-01", "yesterday", "2024-13-01"))
            assertEquals(value, DraftIssue.DATE_FORMAT, DiscoveryDraft(from = value).issue(options))
        assertEquals(DraftIssue.DATE_ORDER, DiscoveryDraft(from = "2025-01-01", through = "2024-01-01").issue(options))
        assertNull(DiscoveryDraft().year(2024).issue(options))
    }
    @Test fun unsupportedAndStaleFacetsAreNeverSilentlyDropped() {
        assertEquals(DraftIssue.UNSUPPORTED, DiscoveryDraft().issue(null))
        assertEquals(DraftIssue.UNSUPPORTED, DiscoveryDraft(people = setOf("person-a"), peopleMatch = MatchMode.ALL).issue(options.copy(peopleAll = false)))
        assertEquals(DraftIssue.UNSUPPORTED, DiscoveryDraft(place = "place-a").issue(options.copy(fields = setOf(DiscoveryField.TEXT))))
        assertEquals(DraftIssue.UNKNOWN_CHOICE, DiscoveryDraft(tags = setOf("deleted")).issue(options))
    }
    @Test fun utf8AndSelectionLimitsAreBounded() {
        assertEquals(DraftIssue.TOO_LONG, DiscoveryDraft(text = "字".repeat(86)).issue(options))
        assertNull(DiscoveryDraft(text = "字".repeat(85)).issue(options))
        assertEquals(DraftIssue.TOO_LONG, DiscoveryDraft(text = "a\nb").issue(options))
        assertEquals(DraftIssue.TOO_LONG, DiscoveryDraft(people = (1..11).map { "person-$it" }.toSet()).issue(options))
    }
    @Test fun draftEditsAndClearDoNotMutateAppliedCriteria() {
        val applied = DiscoveryDraft(people = setOf("person-a"))
        val edit = applied.copy(tags = setOf("tag-a")); assertEquals(2, edit.count)
        assertEquals(1, applied.count); assertEquals(0, DiscoveryDraft().count)
    }
}
