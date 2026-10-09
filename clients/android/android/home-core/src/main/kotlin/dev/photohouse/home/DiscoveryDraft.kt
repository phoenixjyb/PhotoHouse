package dev.photohouse.home

import java.time.LocalDate

/** UI domain only. These types do not define an endpoint or change a frozen wire contract. */
enum class DiscoveryField { TEXT, PEOPLE, DATES, THEMES, TOPICS, TAGS, PLACES, MEDIA }
enum class MatchMode { ANY, ALL }
data class DiscoveryChoice(val id: String, val label: String, val aliases: List<String> = emptyList(),
    val assetCount: Int? = null, val provenance: Map<String, Int> = emptyMap())
data class DiscoveryCoverage(val withValues: Int, val withoutValues: Int)
data class DiscoveryOptions(
    val fields: Set<DiscoveryField>,
    val people: List<DiscoveryChoice> = emptyList(),
    val years: List<Int> = emptyList(),
    val themes: List<DiscoveryChoice> = emptyList(),
    val topics: List<DiscoveryChoice> = emptyList(),
    val tags: List<DiscoveryChoice> = emptyList(),
    val places: List<DiscoveryChoice> = emptyList(),
    val peopleAll: Boolean = false, val tagsAll: Boolean = false,
    val partialIndex: Boolean = false,
    val pinnedPeople: List<String> = people.map { it.id },
    val coverage: Map<DiscoveryField, DiscoveryCoverage> = emptyMap(),
    val dateFrom: String? = null, val dateThrough: String? = null
)
enum class DraftIssue { TOO_LONG, DATE_FORMAT, DATE_ORDER, UNKNOWN_CHOICE, UNSUPPORTED }

/** An unapplied memory-only form. No query is issued by editing or choosing a filter. */
data class DiscoveryDraft(
    val text: String = "", val people: Set<String> = emptySet(),
    val peopleMatch: MatchMode = MatchMode.ANY,
    val from: String = "", val through: String = "",
    val themes: Set<String> = emptySet(), val topics: Set<String> = emptySet(),
    val tags: Set<String> = emptySet(), val tagsMatch: MatchMode = MatchMode.ANY,
    val place: String? = null, val media: AssetKind? = null
) {
    val count: Int get() = listOf(text.isNotBlank(), people.isNotEmpty(), from.isNotEmpty() || through.isNotEmpty(),
        themes.isNotEmpty(), topics.isNotEmpty(), tags.isNotEmpty(), place != null, media != null).count { it }
    fun year(value: Int) = copy(from = "%04d-01-01".format(java.util.Locale.ROOT, value), through = "%04d-12-31".format(java.util.Locale.ROOT, value))
    fun normalized() = copy(text = text.trim(), from = from.trim(), through = through.trim())
    fun issue(options: DiscoveryOptions?): DraftIssue? {
        if (options == null) return DraftIssue.UNSUPPORTED
        val d = normalized()
        if (d.text.toByteArray(Charsets.UTF_8).size > 256 || d.text.any { it.isISOControl() } ||
            listOf(d.people, d.themes, d.topics, d.tags).any { it.size > 10 }) return DraftIssue.TOO_LONG
        fun date(s: String): LocalDate? = if (s.isEmpty()) null else {
            if (!s.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}"))) throw IllegalArgumentException()
            LocalDate.parse(s).also { require(it.year in 1..9999) }
        }
        val dates = try { date(d.from) to date(d.through) } catch (_: Exception) { return DraftIssue.DATE_FORMAT }
        if (dates.first != null && dates.second != null && dates.first!! > dates.second!!) return DraftIssue.DATE_ORDER
        val used = buildSet {
            if (d.text.isNotEmpty()) add(DiscoveryField.TEXT)
            if (d.people.isNotEmpty()) add(DiscoveryField.PEOPLE)
            if (d.from.isNotEmpty() || d.through.isNotEmpty()) add(DiscoveryField.DATES)
            if (d.themes.isNotEmpty()) add(DiscoveryField.THEMES)
            if (d.topics.isNotEmpty()) add(DiscoveryField.TOPICS)
            if (d.tags.isNotEmpty()) add(DiscoveryField.TAGS)
            if (d.place != null) add(DiscoveryField.PLACES)
            if (d.media != null) add(DiscoveryField.MEDIA)
        }
        if (!options.fields.containsAll(used) || d.people.isNotEmpty() && d.peopleMatch == MatchMode.ALL && !options.peopleAll ||
            d.tags.isNotEmpty() && d.tagsMatch == MatchMode.ALL && !options.tagsAll || d.media == AssetKind.UNSUPPORTED) return DraftIssue.UNSUPPORTED
        if (!options.people.map { it.id }.containsAll(d.people) || !options.themes.map { it.id }.containsAll(d.themes) ||
            !options.topics.map { it.id }.containsAll(d.topics) || !options.tags.map { it.id }.containsAll(d.tags) ||
            d.place != null && options.places.none { it.id == d.place }) return DraftIssue.UNKNOWN_CHOICE
        return null
    }
}
