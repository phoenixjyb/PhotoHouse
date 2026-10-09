package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test

class MemoryConversationNavigationTest {
    private val key = MemoryConversationNavigationScope("account", "family", 1, "story", "story", 3)
    private fun page(vararg ids: String) = MemoryConversationPage(ids.map { MemoryConversationSummary(it, 1, 999) })

    @Test fun freshDirectoryIsRequiredAndMissingThreadFallsBackWithoutRestoring() {
        val hints = MemoryConversationNavigation()
        hints.remember(key, "second", page("first", "second"))
        assertEquals(MemoryConversationSelection(null), hints.choose(key, null))
        assertEquals(MemoryConversationSelection("second", true), hints.choose(key, page("first", "second")))
        assertEquals(MemoryConversationSelection("first"), hints.choose(key, page("first")))
        assertEquals(MemoryConversationSelection("first"), hints.choose(key, page("first", "second")))
    }

    @Test fun accountLibraryMembershipTargetAndRevisionAreIndependent() {
        val hints = MemoryConversationNavigation()
        val rows = page("first", "second")
        hints.remember(key, "second", rows)
        listOf(key.copy(accountId = "another"), key.copy(library = "another"),
            key.copy(membershipRevision = 2), key.copy(targetType = "book"),
            key.copy(targetId = "another"), key.copy(revision = 4)).forEach {
            assertEquals(MemoryConversationSelection("first"), hints.choose(it, rows))
        }
        assertEquals(MemoryConversationSelection("second", true), hints.choose(key, rows))
    }

    @Test fun memoirChildOrderAndRevisionsMustMatch() {
        val hints = MemoryConversationNavigation()
        val book = key.copy(targetType = "book", children = listOf("one" to 1L, "two" to 2L))
        val rows = page("first", "second")
        hints.remember(book, "second", rows)
        assertFalse(hints.choose(book.copy(children = book.children.reversed()), rows).restored)
        assertFalse(hints.choose(book.copy(children = listOf("one" to 2L, "two" to 2L)), rows).restored)
        assertTrue(hints.choose(book, rows).restored)
    }

    @Test fun onlyListedSelectionsAreRememberedAndHintsAreBoundedAndClearable() {
        val hints = MemoryConversationNavigation(2)
        val rows = page("first", "second")
        hints.remember(key, "not-listed", rows)
        assertFalse(hints.choose(key, rows).restored)
        hints.remember(key, "second", rows)
        hints.remember(key.copy(targetId = "two"), "second", rows)
        hints.remember(key, "second", rows)
        hints.remember(key.copy(targetId = "three"), "second", rows)
        assertFalse(hints.choose(key.copy(targetId = "two"), rows).restored)
        assertTrue(hints.choose(key, rows).restored)
        hints.clear()
        assertFalse(hints.choose(key, rows).restored)
    }
}
