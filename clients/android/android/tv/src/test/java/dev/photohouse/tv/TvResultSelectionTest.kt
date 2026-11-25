package dev.photohouse.tv

import org.junit.Assert.assertEquals
import org.junit.Test

class TvResultSelectionTest {
    @Test fun keepsPickOrderSkipsDuplicatesAndMovesRemovedItemsToTheEnd() {
        var picked = emptyList<Int>()
        picked = toggleTvResultSelection(picked, 12, eligible = true)
        picked = toggleTvResultSelection(picked, 7, eligible = true)
        picked = toggleTvResultSelection(picked, 12, eligible = true)
        assertEquals(listOf(7), picked)
        picked = toggleTvResultSelection(picked, 12, eligible = true)
        assertEquals(listOf(7, 12), picked)
    }

    @Test fun rejectsIneligibleItemsAndCapsSelectionAtTwentyFour() {
        var picked = (1..TV_RESULT_SELECTION_LIMIT).toList()
        assertEquals(picked, toggleTvResultSelection(picked, 25, eligible = true))
        assertEquals(picked, toggleTvResultSelection(picked, 25, eligible = false))
        picked = toggleTvResultSelection(picked, 1, eligible = true)
        assertEquals((2..24).toList(), picked)
        picked = toggleTvResultSelection(picked, 25, eligible = true)
        assertEquals((2..24).toList() + 25, picked)
    }
}
