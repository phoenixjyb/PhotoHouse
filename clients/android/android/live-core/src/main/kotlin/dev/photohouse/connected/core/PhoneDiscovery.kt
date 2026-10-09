package dev.photohouse.connected.core

import dev.photohouse.protocol.Gallery
import kotlinx.serialization.json.*
import java.time.LocalDate
import java.nio.CharBuffer
import java.nio.charset.CodingErrorAction

enum class PhoneFacet(val wire: String) { PEOPLE("people"), TAGS("tags"), PLACES("locations") }
data class PhoneChoice(val id: String, val label: String, val count: Int, val aliases: List<String> = emptyList())
data class PhoneCoverage(val withValues: Int, val withoutValues: Int)
data class PhoneSnapshot(val library: String, val binding: String, val revision: String,
    val enabled: Set<String>, val assets: Int, val indexed: Int, val coverage: Map<String, PhoneCoverage>,
    val from: String?, val to: String?, val pins: List<PhoneChoice>)
data class PhoneFacetPage(val snapshot: PhoneSnapshot, val facet: PhoneFacet, val page: Int,
    val size: Int, val total: Int, val more: Boolean, val items: List<PhoneChoice>)
data class PhoneSearchPage(val gallery: Gallery, val binding: String, val fingerprint: String, val more: Boolean)

/** Selected records are retained separately from the current facet page. No inferred identities. */
data class PhoneFilters(val people: List<PhoneChoice> = emptyList(), val peopleAll: Boolean = false,
    val tags: List<PhoneChoice> = emptyList(), val tagsAll: Boolean = false,
    val places: List<PhoneChoice> = emptyList(), val media: Set<String> = emptySet(),
    val from: String = "", val to: String = "", val caption: String = "") {
    fun json(): JsonObject {
        fun selected(choices: List<PhoneChoice>): JsonArray {
            require(choices.size in 1..20 && choices.map { it.id }.distinct().size == choices.size)
            choices.forEach { require(PhoneDiscoveryWire.validId(it.id)) }
            return JsonArray(choices.map { JsonPrimitive(it.id) })
        }
        require(media.all { it in setOf("image", "video", "other") })
        for (d in listOf(from, to).filter { it.isNotEmpty() }) {
            require(d.matches(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}")) && LocalDate.parse(d).year in 1..9999)
        }
        require(from.isEmpty() || to.isEmpty() || from <= to)
        val textBytes = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).encode(CharBuffer.wrap(caption))
        require(textBytes.remaining() <= 512 && caption.none { it < ' ' && it !in "\n\t" })
        return buildJsonObject {
            if (people.isNotEmpty()) put("people", buildJsonObject { put("ids", selected(people)); put("match", if (peopleAll) "all" else "any") })
            if (tags.isNotEmpty()) put("tags", buildJsonObject { put("ids", selected(tags)); put("match", if (tagsAll) "all" else "any") })
            if (places.isNotEmpty()) put("locations", selected(places))
            if (media.isNotEmpty()) put("media", JsonArray(media.sorted().map { JsonPrimitive(it) }))
            if (from.isNotEmpty() || to.isNotEmpty()) put("date", buildJsonObject {
                put("from", from.takeIf { it.isNotEmpty() }?.let { JsonPrimitive(it) } ?: JsonNull)
                put("to", to.takeIf { it.isNotEmpty() }?.let { JsonPrimitive(it) } ?: JsonNull)
            })
            if (caption.isNotBlank()) put("caption", caption)
        }.also { require(it.toString().toByteArray(Charsets.UTF_8).size <= 16 * 1024) }
    }
}

data class PhoneDiscoveryState(val snapshot: PhoneSnapshot? = null,
    val facetPage: PhoneFacetPage? = null, val filters: PhoneFilters = PhoneFilters(),
    val result: PhoneSearchPage? = null, val editing: Boolean = true, val changed: Boolean = false,
    val inputInvalid: Boolean = false, val placeQuery: String = "")
