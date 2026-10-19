package dev.photohouse.connected.core

import kotlinx.serialization.json.*

enum class UploadPreparationStage { PREVIEW, INDEX, FACES, CAPTION, VIDEO_PROBE }
enum class UploadPreparationStageState { AWAITING_REVIEW, PENDING, RUNNING, FINISHED, FAILED, DEAD, UNKNOWN, NOT_APPLICABLE }
enum class UploadPreparationAvailability { UNKNOWN, NOT_APPLICABLE }

data class UploadPreparationRecords(
    val imageVector: Boolean,
    val caption: Boolean,
    val faceDetections: Boolean,
)

data class UploadProcessingEvidence(
    val stages: Map<UploadPreparationStage, UploadPreparationStageState>,
    val records: UploadPreparationRecords,
    val availability: Map<String, UploadPreparationAvailability>,
)

/** One server row with processing attached only after exact receipt identity matching. */
data class UploadPreparationItem(
    val receipt: UploadHistoryItem,
    val processing: UploadProcessingEvidence?,
)

data class UploadPreparationPage(
    val page: Int,
    val pageSize: Int,
    val total: Int,
    val items: List<UploadPreparationItem>,
)

/** Strict, bounded parser for the additive own-upload preparation endpoint. */
object UploadPreparationWire {
    private const val PAGE_SIZE = 10
    private const val BODY_LIMIT = 64 * 1024
    private val stageNames = mapOf(
        "preview" to UploadPreparationStage.PREVIEW,
        "index" to UploadPreparationStage.INDEX,
        "faces" to UploadPreparationStage.FACES,
        "caption" to UploadPreparationStage.CAPTION,
        "video_probe" to UploadPreparationStage.VIDEO_PROBE,
    )
    private val stageStates = mapOf(
        "awaiting_review" to UploadPreparationStageState.AWAITING_REVIEW,
        "pending" to UploadPreparationStageState.PENDING,
        "running" to UploadPreparationStageState.RUNNING,
        "finished" to UploadPreparationStageState.FINISHED,
        "failed" to UploadPreparationStageState.FAILED,
        "dead" to UploadPreparationStageState.DEAD,
        "unknown" to UploadPreparationStageState.UNKNOWN,
        "not_applicable" to UploadPreparationStageState.NOT_APPLICABLE,
    )

    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) bad() }
    private fun JsonElement.obj(vararg keys: String): JsonObject =
        (this as? JsonObject ?: bad()).also { check(it.keys == keys.toSet()) }
    private fun JsonElement.int(low: Int, high: Int): Int {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull()?.takeIf { it in low.toLong()..high.toLong() }?.toInt() ?: bad()
    }
    private fun JsonElement.long(low: Long, high: Long): Long {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toLongOrNull()?.takeIf { it in low..high } ?: bad()
    }
    private fun JsonElement.str(max: Int): String {
        val p = this as? JsonPrimitive ?: bad(); check(p.isString)
        check(p.content.isNotEmpty() && p.content.codePointCount(0, p.content.length) <= max &&
            p.content.none { it < ' ' || it == '\u007f' })
        return p.content
    }
    private fun JsonElement.bool(): Boolean {
        val p = this as? JsonPrimitive ?: bad()
        check(!p.isString && (p.content == "true" || p.content == "false"))
        return p.content == "true"
    }
    private fun JsonElement.library(): String? = if (this == JsonNull) null else str(128).also { check(PhoneDiscoveryWire.validLibrary(it)) }

    fun parse(bytes: ByteArray, requestedPage: Int): UploadPreparationPage {
        if (requestedPage !in 1..100000 || bytes.size !in 1..BODY_LIMIT) bad()
        return try {
            val root = DiscoveryJson.parse(bytes, BODY_LIMIT).obj("version", "page", "page_size", "total", "items")
            check(root.getValue("version").int(1, 1) == 1)
            val page = root.getValue("page").int(1, 100000)
            val pageSize = root.getValue("page_size").int(PAGE_SIZE, PAGE_SIZE)
            check(page == requestedPage)
            val total = root.getValue("total").int(0, Int.MAX_VALUE)
            val items = (root.getValue("items") as? JsonArray ?: bad()).also { check(it.size <= PAGE_SIZE) }.map { element ->
                val item = element.obj("asset_id", "created_at", "bytes", "kind", "state", "library_id", "processing")
                val state = item.getValue("state").str(32)
                check(state in setOf("awaiting_review", "available", "unavailable"))
                val library = item.getValue("library_id").library()
                check((state == "available") == (library != null))
                val receipt = UploadHistoryItem(
                    item.getValue("asset_id").str(19).also { check(PhoneDiscoveryWire.validId(it)) },
                    item.getValue("created_at").long(0, 253402300799),
                    item.getValue("bytes").long(1, 16L * 1024 * 1024 * 1024),
                    item.getValue("kind").str(8).also { check(it == "image" || it == "video") }, state, library,
                )
                val rawProcessing = item.getValue("processing")
                val processing = if (rawProcessing == JsonNull) null else parseProcessing(rawProcessing, receipt.kind)
                check((state == "available") == (processing != null))
                UploadPreparationItem(receipt, processing)
            }
            check(items.map { it.receipt.assetId }.distinct().size == items.size)
            check(items.size.toLong() == minOf(PAGE_SIZE.toLong(), maxOf(0L, total.toLong() - (page - 1L) * PAGE_SIZE)))
            UploadPreparationPage(page, pageSize, total, items)
        } catch (e: ApiFailure) { throw e } catch (_: Exception) { bad() }
    }

    private fun parseProcessing(element: JsonElement, kind: String): UploadProcessingEvidence {
        val value = element.obj("stages", "records", "availability")
        val stagesObject = value.getValue("stages").obj(*stageNames.keys.toTypedArray())
        val stages = stagesObject.map { (name, raw) ->
            val state = raw.str(32)
            stageNames.getValue(name) to (stageStates[state] ?: bad())
        }.toMap()
        val notApplicable = stages.filterValues { it == UploadPreparationStageState.NOT_APPLICABLE }.keys
        check(notApplicable == setOf(if (kind == "image") UploadPreparationStage.VIDEO_PROBE else UploadPreparationStage.FACES))
        val records = value.getValue("records").obj("image_vector", "caption", "face_detections")
        val availability = value.getValue("availability").obj("preview", "playback").mapValues { (_, raw) ->
            when (raw.str(32)) {
                "unknown" -> UploadPreparationAvailability.UNKNOWN
                "not_applicable" -> UploadPreparationAvailability.NOT_APPLICABLE
                else -> bad()
            }
        }
        check(availability["preview"] == UploadPreparationAvailability.UNKNOWN)
        check(availability["playback"] == if (kind == "image") UploadPreparationAvailability.NOT_APPLICABLE else UploadPreparationAvailability.UNKNOWN)
        return UploadProcessingEvidence(stages, UploadPreparationRecords(
            records.getValue("image_vector").bool(), records.getValue("caption").bool(), records.getValue("face_detections").bool()), availability)
    }
}
