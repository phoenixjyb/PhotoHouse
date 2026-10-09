package dev.photohouse.stories

import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

// Local presentation models only. These are NOT adopted API DTOs or access control.
enum class StorySource { FAMILY, LEGACY_FAMILY, AI }
enum class StoryRole { VIEWER, CONTRIBUTOR, OWNER }
enum class StoryMedia { IMAGE, VIDEO }
enum class StoryProblem { UNAVAILABLE, CONFLICT, DENIED, INVALID }
enum class SaveSimulation { SUCCESS, LOST_RESPONSE, CONFLICT, DENIED }
data class StoryScope(val account: String, val library: String, val tv: Boolean = false, val publication: Int = 1)
data class StoryText(val title: String = "", val text: String = "", val byline: String = "", val language: String = "mixed") {
    fun valid() = text.isNotBlank() && language in setOf("en", "zh", "mixed", "und") &&
        listOf(title to 512, text to 65536, byline to 256).all { (value, max) -> '\u0000' !in value && value.toByteArray(Charsets.UTF_8).size <= max && wellFormed(value) }
    private fun wellFormed(s: String): Boolean {
        var i = 0
        while (i < s.length) {
            val c = s[i++]
            if (c.isHighSurrogate()) { if (i == s.length || !s[i++].isLowSurrogate()) return false }
            else if (c.isLowSurrogate()) return false
        }
        return true
    }
}
data class StoryCard(val id: String, val asset: String, val content: StoryText, val source: StorySource,
    val media: StoryMedia, val revision: Long = 1, val canEdit: Boolean = false,
    val canViewHistory: Boolean = false, val publishedRevision: Int? = null)
data class StoryDraft(val story: String?, val revision: Long, val content: StoryText)
data class StoryTicket(val generation: Long, val scope: StoryScope)
data class StoryMutation(val ticket: StoryTicket, val id: String, val draft: StoryDraft)
data class StoryLabState(val scope: StoryScope? = null, val role: StoryRole = StoryRole.VIEWER,
    val cards: List<StoryCard> = emptyList(), val selected: StoryCard? = null,
    val draft: StoryDraft? = null, val pending: StoryMutation? = null,
    val query: String = "", val source: StorySource? = null, val media: StoryMedia? = null,
    val problem: StoryProblem? = null, val latest: StoryCard? = null, val saved: Boolean = false,
    val discardPrompt: Boolean = false) {
    val canCreate get() = scope != null && !scope.tv && role != StoryRole.VIEWER
    // Fixture search operates on cards. Production search must adopt the server's asset grouping/ranking.
    val results get() = cards.filter { card ->
        (source == null || if (source == StorySource.FAMILY) card.source != StorySource.AI else card.source == source) &&
        (media == null || card.media == media) &&
        (query.isBlank() || (card.content.title + "\n" + card.content.text).contains(query, ignoreCase = true))
    }
}

/** In-memory synthetic lab. No transport, disk cache, credentials or production entry point. */
class StoryFixtureController {
    private val mutable = MutableStateFlow(StoryLabState())
    val state = mutable.asStateFlow()
    private var generation = 0L
    private val receipts = mutableMapOf<String, StoryCard>()
    fun activate(role: StoryRole = StoryRole.VIEWER, tv: Boolean = false, library: String = "sample-library") {
        clear()
        val scope = StoryScope("sample-account", library, tv)
        val cards = examples().map { card -> card.copy(canEdit = !tv && card.source == StorySource.FAMILY && (role == StoryRole.OWNER || role == StoryRole.CONTRIBUTOR && card.id == "sample-story"),
            canViewHistory = !tv && card.source == StorySource.FAMILY && (role == StoryRole.OWNER || role == StoryRole.CONTRIBUTOR && card.id == "sample-story")) }
        mutable.value = StoryLabState(scope, role, visible(scope, cards))
    }
    private fun visible(scope: StoryScope, cards: List<StoryCard>) = if (scope.tv)
        cards.filter { it.publishedRevision == scope.publication }.map { it.copy(canEdit = false, canViewHistory = false) } else cards
    fun ticket(): StoryTicket? = state.value.scope?.let { StoryTicket(generation, it) }
    private fun accepts(ticket: StoryTicket) = ticket.generation == generation && ticket.scope == state.value.scope
    fun acceptCards(ticket: StoryTicket, cards: List<StoryCard>) {
        if (accepts(ticket)) mutable.value = state.value.copy(cards = visible(ticket.scope, cards), selected = null, draft = null,
            pending = null, latest = null, problem = null)
    }
    fun clear() { generation++; receipts.clear(); mutable.value = StoryLabState() }
    fun deny() { clear(); mutable.value = state.value.copy(problem = StoryProblem.DENIED) }
    fun withdrawPublication() { clear() }
    fun search(query: String, source: StorySource? = state.value.source, media: StoryMedia? = state.value.media) {
        if (state.value.scope == null || state.value.draft != null) return
        if (query.codePointCount(0, query.length) > 160 || '\u0000' in query) {
            mutable.value = state.value.copy(problem = StoryProblem.INVALID); return
        }
        mutable.value = state.value.copy(query = query, source = source, media = media, selected = null, problem = null, saved = false)
    }
    fun open(id: String) {
        if (state.value.draft != null) return
        mutable.value = state.value.copy(selected = state.value.cards.find { it.id == id }, problem = null, saved = false)
    }
    fun edit() {
        val card = state.value.selected ?: return
        if (!card.canEdit || state.value.scope?.tv != false) return
        mutable.value = state.value.copy(draft = StoryDraft(card.id, card.revision, card.content), saved = false)
    }
    fun create() {
        if (!state.value.canCreate) return
        mutable.value = state.value.copy(selected = null, draft = StoryDraft(null, 0, StoryText()), saved = false, problem = null)
    }
    fun update(content: StoryText) {
        val draft = state.value.draft ?: return
        if (state.value.pending != null) return // uncertain save retries retain the identical body and UUID
        mutable.value = state.value.copy(draft = draft.copy(content = content), problem = if (state.value.latest != null) StoryProblem.CONFLICT else null)
    }
    fun back(): Boolean {
        val s = state.value
        if (s.draft != null) { mutable.value = s.copy(discardPrompt = true); return true }
        if (s.selected != null) { mutable.value = s.copy(selected = null, problem = null, saved = false); return true }
        return false
    }
    fun keepEditing() { mutable.value = state.value.copy(discardPrompt = false) }
    fun discard() { mutable.value = state.value.copy(draft = null, pending = null, latest = null, discardPrompt = false, problem = null) }
    fun beginSave(): StoryMutation? {
        val s = state.value
        if (s.pending != null) return s.pending
        val draft = s.draft ?: return null
        if (!s.canCreate || (draft.story != null && s.selected?.canEdit != true) || s.problem == StoryProblem.CONFLICT) return null
        if (!draft.content.valid()) { mutable.value = s.copy(problem = StoryProblem.INVALID); return null }
        val mutation = StoryMutation(ticket() ?: return null, UUID.randomUUID().toString(), draft)
        mutable.value = s.copy(pending = mutation, problem = null)
        return mutation
    }
    fun finishSave(mutation: StoryMutation, card: StoryCard?, problem: StoryProblem? = null) {
        if (!accepts(mutation.ticket) || state.value.pending != mutation) return
        if (problem == StoryProblem.DENIED) { deny(); return }
        if (problem == StoryProblem.UNAVAILABLE) { mutable.value = state.value.copy(problem = problem); return }
        if (problem != null || card == null) {
            mutable.value = state.value.copy(pending = null, problem = problem ?: StoryProblem.INVALID, latest = card); return
        }
        mutable.value = state.value.copy(cards = state.value.cards.filterNot { it.id == card.id } + card,
            selected = card, pending = null, draft = null, latest = null, saved = true, problem = null)
    }
    fun useDraftAfterReview() {
        val s = state.value
        val latest = s.latest ?: return
        val draft = s.draft ?: return
        if (!latest.canEdit) { deny(); return }
        mutable.value = s.copy(selected = latest, draft = draft.copy(revision = latest.revision), latest = null, problem = null)
    }
    fun simulateSave(outcome: SaveSimulation = SaveSimulation.SUCCESS) {
        val mutation = beginSave() ?: return
        if (outcome == SaveSimulation.DENIED) { finishSave(mutation, null, StoryProblem.DENIED); return }
        if (outcome == SaveSimulation.CONFLICT) {
            val latest = state.value.selected?.copy(revision = mutation.draft.revision + 1,
                content = StoryText("A newer memory / 新的回忆", "Someone else has edited this story.\n另一位家人补充了这段回忆。"))
            finishSave(mutation, latest, StoryProblem.CONFLICT); return
        }
        val saved = receipts.getOrPut(mutation.id) {
            StoryCard(mutation.draft.story ?: UUID.randomUUID().toString(), "101", mutation.draft.content, StorySource.FAMILY,
                state.value.selected?.media ?: StoryMedia.IMAGE, mutation.draft.revision + 1, canEdit = true, canViewHistory = true)
        }
        finishSave(mutation, if (outcome == SaveSimulation.LOST_RESPONSE) null else saved,
            if (outcome == SaveSimulation.LOST_RESPONSE) StoryProblem.UNAVAILABLE else null)
    }
    companion object {
        fun examples(): List<StoryCard> {
            val long = (1..24).joinToString("\n\n") { n ->
                "$n. We took the little blue train to the lake. The rain stopped, and we shared warm bread beside the water. This is a made-up family memory for layout testing.\n" +
                "我们坐着蓝色的小火车来到湖边。雨停了，一家人分着热乎乎的面包，慢慢聊起那天的故事。这是一段用于界面测试的虚构回忆。"
            } + "\n\nEnd of the story / 故事结束。 <b>This stays literal</b>"
            return listOf(
                StoryCard("sample-story", "101", StoryText("The afternoon by the lake / 湖边的午后", long, "Sample writer / 示例作者"), StorySource.FAMILY, StoryMedia.IMAGE, publishedRevision = 1),
                StoryCard("sample-private", "102", StoryText("A private memory / 私人回忆", "A private story, deliberately excluded from the TV fixture."), StorySource.FAMILY, StoryMedia.VIDEO),
                StoryCard("sample-legacy", "103", StoryText("Earlier family note / 旧家庭说明", "Blue train, warm bread. This older edit has no verified account author."), StorySource.LEGACY_FAMILY, StoryMedia.IMAGE, publishedRevision = 1),
                StoryCard("sample-ai", "104", StoryText("AI description / AI 描述", "A blue train beside a lake. Model-generated sample description."), StorySource.AI, StoryMedia.VIDEO, publishedRevision = 1))
        }
    }
}
