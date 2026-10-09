package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.util.UUID

data class MemoryBookPlanLimits(val chapters: Int, val sources: Int, val contextBytes: Int)

data class MemoryBookPlanCapacity(
    val state: String,
    val canDraft: Boolean,
    val sourceCount: Int?,
    val sourceKinds: Map<String, Int>?,
    val contextBytes: Int? = null,
)

data class MemoryBookPlanChapter(val id: String, val title: String, val itemCount: Int)

data class MemoryBookPlanSection(
    val position: Int,
    val id: String,
    val revision: Long,
    val title: String,
    val itemCount: Int,
    val canEdit: Boolean,
    val chapters: List<MemoryBookPlanChapter>,
    val capacity: MemoryBookPlanCapacity,
)

data class MemoryBookPlan(
    val targetType: String,
    val targetId: String,
    val revision: Long,
    val canEdit: Boolean,
    val kind: String,
    val generated: Boolean,
    val queued: Boolean,
    val needsReview: Boolean,
    val storyCount: Int,
    val chapterCount: Int,
    val itemCount: Int,
    val distinctItemCount: Int,
    val limits: MemoryBookPlanLimits,
    val whole: MemoryBookPlanCapacity,
    val sections: List<MemoryBookPlanSection>,
    val contextProfile: String?,
)

/** Strict, bounded decoder for the read-only saved memoir structure plan. */
internal object MemoryBookPlanWire {
    private const val MAX_BYTES = MemoryCommunityResponseLimits.JSON_BYTES
    private const val MAX_STORIES = 24
    private const val MAX_CHAPTERS = 24
    private const val MAX_SOURCES = 96
    private const val MAX_CONTEXT_BYTES = 65_536
    private const val MAX_COUNT = 1_000_000
    private const val EDITORIAL_PROFILE = "memoir_editorial_v1"
    private val sourceKinds = setOf("ai", "editorial", "family", "metadata", "transcript")

    private fun invalid(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) invalid() }
    private fun obj(value: JsonElement?, vararg keys: String): JsonObject =
        (value as? JsonObject ?: invalid()).also { check(it.keys == keys.toSet()) }
    private fun string(value: JsonElement?, maximumBytes: Int, blank: Boolean = false): String {
        val primitive = value as? JsonPrimitive ?: invalid()
        check(primitive.isString)
        val result = primitive.content
        val size = try { ProtectedMemoryCommunityWire.strictUtf8(result).size } catch (_: Exception) { invalid() }
        check(size <= maximumBytes && (blank || result.isNotBlank()))
        check(result.none { it == '\u0000' || it.isISOControl() })
        return result
    }
    private fun integer(value: JsonElement?, minimum: Int, maximum: Int): Int {
        val primitive = value as? JsonPrimitive ?: invalid()
        check(!primitive.isString && primitive.content.matches(Regex("0|[1-9][0-9]*")))
        return primitive.content.toLongOrNull()?.takeIf { it in minimum.toLong()..maximum.toLong() }?.toInt()
            ?: invalid()
    }
    private fun boolean(value: JsonElement?): Boolean {
        val primitive = value as? JsonPrimitive ?: invalid()
        check(!primitive.isString)
        return primitive.booleanOrNull ?: invalid()
    }
    private fun array(value: JsonElement?, maximum: Int): JsonArray =
        (value as? JsonArray ?: invalid()).also { check(it.size <= maximum) }
    private fun uuid(value: String): String = value.also {
        check(runCatching { UUID.fromString(it).toString() == it }.getOrDefault(false))
    }
    private fun revision(value: JsonElement?): Long {
        val text = string(value, 19)
        check(text.matches(Regex("[1-9][0-9]{0,18}")))
        return text.toLongOrNull() ?: invalid()
    }

    fun decode(bytes: ByteArray, expectedBookId: String, expectedRevision: Long,
               editorialContext: Boolean): MemoryBookPlan {
        check(bytes.size in 1..MAX_BYTES && expectedRevision > 0)
        check(runCatching { UUID.fromString(expectedBookId).toString() == expectedBookId }.getOrDefault(false))
        try {
            val root = DiscoveryJson.parse(bytes, MAX_BYTES, 100) as? JsonObject ?: invalid()
            val baseKeys = setOf("version", "target_type", "target_id", "revision", "can_edit",
                "kind", "generated", "queued", "needs_review", "story_count", "chapter_count",
                "item_count", "distinct_item_count", "limits", "whole", "sections")
            check(root.keys == if (editorialContext) baseKeys + "context_profile" else baseKeys)
            check(integer(root["version"], 1, 1) == 1)
            val targetType = string(root["target_type"], 16)
            check(targetType == "book")
            val targetId = uuid(string(root["target_id"], 36))
            check(targetId == expectedBookId)
            val bookRevision = revision(root["revision"])
            check(bookRevision == expectedRevision)
            val canEdit = boolean(root["can_edit"])
            val kind = string(root["kind"], 32)
            check(kind == "saved_structure_plan")
            val generated = boolean(root["generated"])
            val queued = boolean(root["queued"])
            val needsReview = boolean(root["needs_review"])
            check(!generated && !queued && needsReview)
            val storyCount = integer(root["story_count"], 1, MAX_STORIES)
            val chapterCount = integer(root["chapter_count"], 1, MAX_STORIES * 6)
            val itemCount = integer(root["item_count"], 0, MAX_COUNT)
            val distinctItemCount = integer(root["distinct_item_count"], 0, itemCount)

            val limitsJson = obj(root["limits"], "chapters", "sources", "context_bytes")
            val limits = MemoryBookPlanLimits(
                integer(limitsJson["chapters"], MAX_CHAPTERS, MAX_CHAPTERS),
                integer(limitsJson["sources"], MAX_SOURCES, MAX_SOURCES),
                integer(limitsJson["context_bytes"], MAX_CONTEXT_BYTES, MAX_CONTEXT_BYTES),
            )

            val wholeKeys = if (editorialContext)
                arrayOf("state", "can_draft", "source_count", "source_kinds", "context_bytes")
            else arrayOf("state", "can_draft", "source_count", "source_kinds")
            val whole = capacity(obj(root["whole"], *wholeKeys), editorialContext)
            check(!whole.canDraft || canEdit)
            if (whole.state == "within_limits") check(chapterCount <= MAX_CHAPTERS)
            if (editorialContext) {
                check(string(root["context_profile"], 32) == EDITORIAL_PROFILE)
            }

            val sections = array(root["sections"], MAX_STORIES).mapIndexed { index, value ->
                val section = obj(value, "position", "id", "revision", "title", "item_count", "can_edit",
                    "chapters", "state", "can_draft", "source_count", "source_kinds")
                val position = integer(section["position"], 1, MAX_STORIES)
                check(position == index + 1)
                val id = uuid(string(section["id"], 36))
                val sectionRevision = revision(section["revision"])
                val title = title(section["title"])
                val sectionItems = integer(section["item_count"], 0, MAX_COUNT)
                val sectionCanEdit = boolean(section["can_edit"])
                val chapterJson = array(section["chapters"], 6)
                check(chapterJson.isNotEmpty())
                val chapters = chapterJson.mapIndexed { chapterIndex, chapterValue ->
                    val chapter = obj(chapterValue, "id", "title", "item_count")
                    val chapterId = string(chapter["id"], 16)
                    check(chapterId == "chapter-${chapterIndex + 1}")
                    MemoryBookPlanChapter(chapterId,
                        title(chapter["title"]),
                        integer(chapter["item_count"], 0, MAX_COUNT))
                }
                val capacityValue = capacity(JsonObject(
                    listOf("state", "can_draft", "source_count", "source_kinds")
                        .associateWith { section[it] ?: invalid() }), false)
                check(!capacityValue.canDraft || sectionCanEdit)
                MemoryBookPlanSection(position, id, sectionRevision, title, sectionItems, sectionCanEdit,
                    chapters, capacityValue)
            }
            check(sections.size == storyCount)
            check(sections.map { it.id }.distinct().size == sections.size)
            check(sections.sumOf { it.chapters.size } == chapterCount)
            check(sections.sumOf { it.itemCount } == itemCount)
            check(distinctItemCount <= itemCount)
            return MemoryBookPlan(targetType, targetId, bookRevision, canEdit, kind, generated, queued,
                needsReview, storyCount, chapterCount, itemCount, distinctItemCount, limits, whole,
                sections, if (editorialContext) EDITORIAL_PROFILE else null)
        } catch (failure: ApiFailure) {
            throw failure
        } catch (_: Exception) {
            invalid()
        }
    }

    private fun capacity(value: JsonObject, editorialContext: Boolean): MemoryBookPlanCapacity {
        val state = string(value["state"], 32)
        check(state in setOf("within_limits", "smaller_scope_required"))
        val canDraft = boolean(value["can_draft"])
        val sourceCountValue = value["source_count"]
        val sourceKindsValue = value["source_kinds"]
        val sourceCount: Int?
        val kinds: Map<String, Int>?
        if (state == "within_limits") {
            sourceCount = integer(sourceCountValue, 0, MAX_SOURCES)
            val sourceKindsJson = sourceKindsValue as? JsonObject ?: invalid()
            val parsed = linkedMapOf<String, Int>()
            for ((key, item) in sourceKindsJson) {
                check(key in sourceKinds)
                parsed[key] = integer(item, 1, MAX_SOURCES)
            }
            check(parsed.values.sum() == sourceCount)
            kinds = parsed
        } else {
            check(!canDraft && sourceCountValue == JsonNull && sourceKindsValue == JsonNull)
            sourceCount = null
            kinds = null
        }
        val contextBytes = if (editorialContext) {
            val raw = value["context_bytes"] ?: invalid()
            if (raw == JsonNull) {
                check(state == "smaller_scope_required")
                null
            } else {
                check(state == "within_limits")
                integer(raw, 1, MAX_CONTEXT_BYTES)
            }
        } else {
            check("context_bytes" !in value)
            null
        }
        return MemoryBookPlanCapacity(state, canDraft, sourceCount, kinds, contextBytes)
    }

    private fun title(value: JsonElement?): String = string(value, 640, blank = true).also {
        check(it.codePointCount(0, it.length) <= 160)
    }
}
