package dev.photohouse.connected.core

/** Navigation only: no credential, content, draft, recording, request or result. */
internal data class MemoryConversationNavigationScope(
    val accountId: String,
    val library: String,
    val membershipRevision: Long,
    val targetType: String,
    val targetId: String,
    val revision: Long,
    val children: List<Pair<String, Long>> = emptyList(),
)

internal data class MemoryConversationSelection(val id: String?, val restored: Boolean = false)

/** Bounded process-memory hints; fresh authorized lists are the only lookup gate. */
internal class MemoryConversationNavigation(private val limit: Int = 16) {
    init { require(limit in 1..16) }

    private val hints = LinkedHashMap<MemoryConversationNavigationScope, String>()

    fun choose(key: MemoryConversationNavigationScope?, page: MemoryConversationPage?): MemoryConversationSelection {
        val rows = page?.items.orEmpty()
        val hint = key?.let(hints::get)
        val selected = rows.firstOrNull { it.id == hint }
        if (selected != null) return MemoryConversationSelection(selected.id, restored = true)
        if (key != null && page != null) hints.remove(key)
        return MemoryConversationSelection(rows.firstOrNull()?.id)
    }

    fun remember(key: MemoryConversationNavigationScope?, id: String?, page: MemoryConversationPage?) {
        if (key == null || id == null || page?.items?.none { it.id == id } != false) return
        hints.remove(key)
        hints[key] = id
        while (hints.size > limit) hints.remove(hints.keys.first())
    }

    fun clear() { hints.clear() }
}
