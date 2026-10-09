package dev.photohouse.tv

import dev.photohouse.home.DiscoveryChoice
import dev.photohouse.home.DiscoveryCoverage
import dev.photohouse.home.DiscoveryField
import dev.photohouse.home.DiscoveryOptions
import org.junit.Assert.assertEquals
import org.junit.Test

/** Checks the actual text consumed by ChoiceRow, including provenance, aliases and counts. */
class DiscoveryLabelsTest {
    @Test fun placeEntryKeepsCoverageAndUnavailableMeaning() {
        val available = DiscoveryOptions(setOf(DiscoveryField.PLACES), coverage = mapOf(
            DiscoveryField.PLACES to DiscoveryCoverage(withValues = 7, withoutValues = 3)))
        assertEquals("7 with named places · 3 without a named place", placeEntryHint(available, false))
        assertEquals("7 条有命名地点 · 3 条无命名地点", placeEntryHint(available, true))
        assertEquals("Places are not available yet", placeEntryHint(DiscoveryOptions(emptySet()), false))
    }

    @Test fun reviewedPeopleAndRegionsKeepTheirMeaningInBothLanguages() {
        val person = DiscoveryChoice("1", "Sample person", listOf("示例人物"), 3,
            mapOf("reviewed_assignments" to 3))
        val place = DiscoveryChoice("2", "Sample region", assetCount = 4,
            provenance = mapOf("reviewed_region" to 4))
        assertEquals("示例人物\n3 items\nReviewed people · 3", choiceHint(person, false))
        assertEquals("示例人物\n3 项\n已确认人物 · 3", choiceHint(person, true))
        assertEquals("4 items\nReviewed region · 4", choiceHint(place, false))
        assertEquals("4 项\n已确认地区 · 4", choiceHint(place, true))
    }

    @Test fun unknownAndUnrecognizedProvenanceRemainUnknownAndDoNotImplyReview() {
        for (source in listOf("unknown", "future_source")) {
            val choice = DiscoveryChoice("3", "Sample tag", provenance = mapOf(source to 2, "reviewed_assignments" to 0))
            assertEquals("Unknown source · 2", choiceHint(choice, false))
            assertEquals("来源未知 · 2", choiceHint(choice, true))
        }
        val caption = DiscoveryChoice("4", "Sample caption tag", provenance = mapOf("caption" to 1))
        assertEquals("Caption-derived · 1", choiceHint(caption, false))
        assertEquals("来自说明 · 1", choiceHint(caption, true))
    }
}
