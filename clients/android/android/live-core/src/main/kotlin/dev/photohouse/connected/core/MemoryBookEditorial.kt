package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.charset.CodingErrorAction
import java.util.UUID

/** Separate optional contract: existing MemoryCommunityApi implementations remain source compatible. */
interface MemoryBookEditorialApi {
    suspend fun getBookEditorial(token: Bearer, library: String, bookId: String): ByteArray
    suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String): ByteArray
    /** Explicitly reads source reference labels without fetching chapter text or audio. */
    suspend fun getBookEditorialSourceReferences(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStoryContributionReferences =
        throw ApiFailure(FailureKind.INVALID_INPUT)
}

data class EditorialChild(val storyId: String, val revision: String)
data class EditorialSourceIdentity(
    val storyId: String, val storyRevision: String, val chapterId: String, val contributionId: String,
)
data class EditorialTransition(
    val leftStoryId: String, val rightStoryId: String, val text: String,
    val sourceRefs: List<EditorialSourceIdentity>,
)
enum class EditorialState { CURRENT, EMPTY, SOURCE_CHANGED }
data class MemoryBookEditorial(
    val bookId: String, val revision: String, val children: List<EditorialChild>, val state: EditorialState,
    val introductionSourceRefs: List<EditorialSourceIdentity>, val transitions: List<EditorialTransition>,
)
data class MemoryBookEditorialMutation(
    val revision: String, val mutationId: String, val children: List<EditorialChild>,
    val introductionSourceRefs: List<EditorialSourceIdentity>, val transitions: List<EditorialTransition>,
)

/** Repository boundary for an optional endpoint. Only a missing/unavailable feature maps to null. */
class MemoryBookEditorialRepository(private val api: MemoryBookEditorialApi) {
    suspend fun get(
        token: Bearer, library: String, bookId: String, expectedRevision: String,
        currentChildren: List<EditorialChild>, eligibleSources: Set<EditorialSourceIdentity>,
    ): MemoryBookEditorial? = optional { api.getBookEditorial(token, library, bookId) }
        ?.let { MemoryBookEditorialWire.decodeResponse(it, bookId, expectedRevision, currentChildren, eligibleSources) }

    suspend fun save(
        token: Bearer, library: String, bookId: String, mutation: MemoryBookEditorialMutation,
        currentChildren: List<EditorialChild>, eligibleSources: Set<EditorialSourceIdentity>,
    ): MemoryBookEditorial? {
        val json = MemoryBookEditorialWire.encodeMutation(mutation, currentChildren, eligibleSources)
        val expectedNext = try { MemoryBookEditorialWire.incrementRevision(mutation.revision) }
        catch (_: IllegalArgumentException) { throw ApiFailure(FailureKind.HTTP, 409) }
        val bytes = optional { api.saveBookEditorial(token, library, bookId, json) } ?: return null
        return MemoryBookEditorialWire.decodeResponse(bytes, bookId, expectedNext, currentChildren, eligibleSources)
    }

    private suspend fun optional(block: suspend () -> ByteArray): ByteArray? = try {
        block()
    } catch (e: ApiFailure) {
        if (e.status == 404 || e.status == 503) null else throw e
    }
}

internal object MemoryBookEditorialWire {
    const val MAX_BODY_BYTES = 65_536
    private const val MAX_RESPONSE_BYTES = MemoryCommunityResponseLimits.JSON_BYTES
    private const val MAX_CHILDREN = 24
    private const val MAX_REFS_PER_SECTION = 12
    private const val MAX_REFS_TOTAL = 96
    private const val MAX_TRANSITION_BYTES = 6_000
    private const val MAX_CHAPTER_BYTES = 128
    private const val MAX_REVISION = Long.MAX_VALUE

    private fun invalid(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun requireInput(ok: Boolean) { require(ok) { "invalid memoir editorial input" } }
    private fun utf8(value: String): ByteArray = Charsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
        .encode(java.nio.CharBuffer.wrap(value)).let { out -> ByteArray(out.remaining()).also(out::get) }

    private fun canonicalUuid(value: String): Boolean = runCatching { UUID.fromString(value).toString() == value }.getOrDefault(false)
    private fun validRevision(value: String): Boolean = value.matches(Regex("[1-9][0-9]{0,18}")) &&
        runCatching { value.toLong() in 1..MAX_REVISION }.getOrDefault(false)
    fun decodeSourceCatalog(bytes: ByteArray, library: String, storyId: String, revision: Long): SavedMemoryStoryContributionReferences {
        if (bytes.size > 16 * 1024 || !canonicalUuid(storyId) || revision <= 0) invalid()
        try {
            val root = StrictJson.parse(bytes).objectExact("version", "id", "library_id", "revision", "chapters")
            if (root.int("version") != 1 || root.string("id") != storyId || root.string("library_id") != library ||
                root.string("revision") != revision.toString()) invalid()
            val chapters = root.array("chapters").map { (it as? JsonObject ?: invalid()).also { obj ->
                if (obj.keys != setOf("id", "contribution_ids")) invalid()
            }.string("id") }
            if (chapters.size !in 1..6 || chapters != (1..chapters.size).map { "chapter-$it" }) invalid()
            return ProtectedMemoryStoriesWire.contributionReferences(bytes, library, storyId, revision, chapters)
        } catch (e: ApiFailure) { throw e }
        catch (_: Exception) { invalid() }
    }
    internal fun incrementRevision(value: String): String {
        requireInput(validRevision(value) && value.toLong() < MAX_REVISION)
        return (value.toLong() + 1).toString()
    }

    fun encodeMutation(
        mutation: MemoryBookEditorialMutation, currentChildren: List<EditorialChild>,
        eligibleSources: Set<EditorialSourceIdentity>,
    ): String {
        requireInput(validRevision(mutation.revision) && canonicalUuid(mutation.mutationId))
        validateChildren(currentChildren)
        requireInput(mutation.children == currentChildren)
        validateSections(mutation.children, mutation.introductionSourceRefs, mutation.transitions, eligibleSources)
        val payload = buildJsonObject {
            put("version", 1); put("revision", mutation.revision); put("mutation_id", mutation.mutationId)
            put("children", JsonArray(mutation.children.map { child -> buildJsonObject {
                put("story_id", child.storyId); put("revision", child.revision)
            } }))
            put("introduction_source_refs", refsJson(mutation.introductionSourceRefs))
            put("transitions", JsonArray(mutation.transitions.map { transition -> buildJsonObject {
                put("left_story_id", transition.leftStoryId); put("right_story_id", transition.rightStoryId)
                put("text", transition.text); put("source_refs", refsJson(transition.sourceRefs))
            } }))
        }.toString()
        requireInput(utf8(payload).size <= MAX_BODY_BYTES)
        return payload
    }

    fun decodeResponse(
        bytes: ByteArray, expectedBookId: String, expectedRevision: String,
        expectedChildren: List<EditorialChild>, eligibleSources: Set<EditorialSourceIdentity>,
    ): MemoryBookEditorial {
        if (bytes.size > MAX_RESPONSE_BYTES || !canonicalUuid(expectedBookId) || !validRevision(expectedRevision)) invalid()
        try {
            validateChildren(expectedChildren)
            val root = StrictJson.parse(bytes).objectExact("version", "id", "revision", "children", "state", "introduction_source_refs", "transitions")
            if (root.int("version") != 1 || root.string("id") != expectedBookId || root.string("revision") != expectedRevision) invalid()
            val children = root.array("children").map { item ->
                val obj = item.objectExact("story_id", "revision")
                EditorialChild(obj.string("story_id"), obj.string("revision"))
            }
            if (children != expectedChildren) invalid()
            val state = when (root.string("state")) {
                "current" -> EditorialState.CURRENT
                "empty" -> EditorialState.EMPTY
                "source_changed" -> EditorialState.SOURCE_CHANGED
                else -> invalid()
            }
            val intro = root.array("introduction_source_refs").map(::source)
            val transitions = root.array("transitions").map { item ->
                val obj = item.objectExact("left_story_id", "right_story_id", "text", "source_refs")
                EditorialTransition(obj.string("left_story_id"), obj.string("right_story_id"), obj.string("text"),
                    obj.array("source_refs").map(::source))
            }
            if (state != EditorialState.CURRENT && (intro.isNotEmpty() || transitions.isNotEmpty())) invalid()
            if (state == EditorialState.CURRENT) validateSections(children, intro, transitions, eligibleSources)
            else if (transitions.isNotEmpty()) invalid()
            return MemoryBookEditorial(expectedBookId, expectedRevision, children, state, intro, transitions)
        } catch (e: ApiFailure) { throw e }
        catch (_: Exception) { invalid() }
    }

    private fun validateChildren(children: List<EditorialChild>) {
        requireInput(children.size in 1..MAX_CHILDREN && children.map { it.storyId }.distinct().size == children.size)
        children.forEach { requireInput(canonicalUuid(it.storyId) && validRevision(it.revision)) }
    }

    private fun validateSections(
        children: List<EditorialChild>, intro: List<EditorialSourceIdentity>, transitions: List<EditorialTransition>,
        eligible: Set<EditorialSourceIdentity>,
    ) {
        validateChildren(children)
        val childRevisions = children.associate { it.storyId to it.revision }
        validateRefs(intro, childRevisions, eligible, null)
        requireInput(transitions.size == children.size - 1)
        transitions.forEachIndexed { index, transition ->
            val left = children[index].storyId; val right = children[index + 1].storyId
            requireInput(transition.leftStoryId == left && transition.rightStoryId == right)
            val textBytes = utf8(transition.text).size
            requireInput('\u0000' !in transition.text && textBytes <= MAX_TRANSITION_BYTES)
            requireInput(if (pythonStripBlank(transition.text)) transition.sourceRefs.isEmpty() else transition.sourceRefs.isNotEmpty())
            validateRefs(transition.sourceRefs, childRevisions, eligible, setOf(left, right))
        }
        val totalRefs = intro.size + transitions.sumOf { it.sourceRefs.size }
        requireInput(totalRefs <= MAX_REFS_TOTAL)
    }

    /** Mirrors Python str.strip() whitespace semantics used by the immutable server contract. */
    private fun pythonStripBlank(value: String): Boolean = value.all { c ->
        c in '\u0009'..'\u000d' || c in '\u001c'..'\u0020' || c == '\u0085' || c == '\u00a0' ||
            c == '\u1680' || c in '\u2000'..'\u200a' || c == '\u2028' || c == '\u2029' ||
            c == '\u202f' || c == '\u205f' || c == '\u3000'
    }

    private fun validateRefs(
        refs: List<EditorialSourceIdentity>, revisions: Map<String, String>, eligible: Set<EditorialSourceIdentity>, allowed: Set<String>?,
    ) {
        requireInput(refs.size <= MAX_REFS_PER_SECTION && refs.distinct().size == refs.size)
        refs.forEach { ref ->
            requireInput(canonicalUuid(ref.storyId) && validRevision(ref.storyRevision) && canonicalUuid(ref.contributionId))
            requireInput(ref.chapterId.isNotEmpty() && '\u0000' !in ref.chapterId && utf8(ref.chapterId).size <= MAX_CHAPTER_BYTES)
            requireInput(revisions[ref.storyId] == ref.storyRevision && (allowed == null || ref.storyId in allowed))
            requireInput(ref in eligible)
        }
    }

    private fun source(item: JsonElement): EditorialSourceIdentity {
        val obj = item.objectExact("story_id", "story_revision", "chapter_id", "contribution_id")
        return EditorialSourceIdentity(obj.string("story_id"), obj.string("story_revision"), obj.string("chapter_id"), obj.string("contribution_id"))
    }

    private fun refsJson(refs: List<EditorialSourceIdentity>) = JsonArray(refs.map { ref -> buildJsonObject {
        put("story_id", ref.storyId); put("story_revision", ref.storyRevision); put("chapter_id", ref.chapterId)
        put("contribution_id", ref.contributionId)
    } })

    private fun JsonElement.objectExact(vararg keys: String): JsonObject = (this as? JsonObject)?.also {
        if (it.keys != keys.toSet()) invalid()
    } ?: invalid()
    private fun JsonObject.string(key: String): String = this[key]?.jsonPrimitive?.takeIf(JsonPrimitive::isString)?.content ?: invalid()
    private fun JsonObject.int(key: String): Int = this[key]?.jsonPrimitive?.takeIf { it.isString.not() }?.intOrNull ?: invalid()
    private fun JsonObject.array(key: String): JsonArray = this[key] as? JsonArray ?: invalid()

    /** Small bounded JSON parser that rejects duplicate names before JsonObject can collapse them. */
    private object StrictJson {
        fun parse(bytes: ByteArray): JsonElement {
            val text = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(bytes)).toString()
            return Parser(text).parse()
        }
        private class Parser(private val s: String) {
            private var p = 0
            fun parse(): JsonElement { ws(); val value = value(0); ws(); if (p != s.length) invalid(); return value }
            private fun value(depth: Int): JsonElement {
                if (depth > 32 || p >= s.length) invalid()
                return when (s[p]) {
                    '{' -> obj(depth + 1); '[' -> array(depth + 1); '"' -> JsonPrimitive(string())
                    't' -> literal("true", JsonPrimitive(true)); 'f' -> literal("false", JsonPrimitive(false));
                    'n' -> literal("null", JsonNull); '-', in '0'..'9' -> number(); else -> invalid()
                }
            }
            private fun obj(depth: Int): JsonObject {
                p++; ws(); val map = linkedMapOf<String, JsonElement>(); if (take('}')) return JsonObject(map)
                while (true) {
                    ws(); if (p >= s.length || s[p] != '"') invalid(); val key = string(); if (key in map) invalid()
                    ws(); expect(':'); ws(); map[key] = value(depth); ws()
                    if (take('}')) break; expect(',')
                }
                return JsonObject(map)
            }
            private fun array(depth: Int): JsonArray {
                p++; ws(); val values = mutableListOf<JsonElement>(); if (take(']')) return JsonArray(values)
                while (true) { ws(); values += value(depth); ws(); if (take(']')) break; expect(',') }
                return JsonArray(values)
            }
            private fun string(): String {
                expect('"'); val out = StringBuilder()
                while (p < s.length) {
                    val c = s[p++]
                    when {
                        c == '"' -> return out.toString()
                        c == '\\' -> {
                            if (p >= s.length) invalid()
                            when (val escaped = s[p++]) {
                                '"', '\\', '/' -> out.append(escaped); 'b' -> out.append('\b'); 'f' -> out.append('\u000c')
                                'n' -> out.append('\n'); 'r' -> out.append('\r'); 't' -> out.append('\t')
                                'u' -> { if (p + 4 > s.length) invalid(); val code = s.substring(p, p + 4).toIntOrNull(16) ?: invalid(); out.append(code.toChar()); p += 4 }
                                else -> invalid()
                            }
                        }
                        c < ' ' -> invalid()
                        else -> out.append(c)
                    }
                }
                invalid()
            }
            private fun number(): JsonPrimitive {
                val start = p; if (take('-') && p >= s.length) invalid()
                if (!take('0')) { if (p >= s.length || s[p] !in '1'..'9') invalid(); while (p < s.length && s[p].isDigit()) p++ }
                if (take('.')) { if (p >= s.length || !s[p].isDigit()) invalid(); while (p < s.length && s[p].isDigit()) p++ }
                if (p < s.length && s[p] in "eE") { p++; if (p < s.length && s[p] in "+-") p++; if (p >= s.length || !s[p].isDigit()) invalid(); while (p < s.length && s[p].isDigit()) p++ }
                val raw = s.substring(start, p)
                return JsonPrimitive(raw.toLongOrNull() ?: raw.toDoubleOrNull() ?: invalid())
            }
            private fun <T : JsonElement> literal(text: String, element: T): T { if (!s.startsWith(text, p)) invalid(); p += text.length; return element }
            private fun ws() { while (p < s.length && s[p] in " \t\r\n") p++ }
            private fun expect(c: Char) { if (!take(c)) invalid() }
            private fun take(c: Char): Boolean = if (p < s.length && s[p] == c) { p++; true } else false
        }
    }
}
