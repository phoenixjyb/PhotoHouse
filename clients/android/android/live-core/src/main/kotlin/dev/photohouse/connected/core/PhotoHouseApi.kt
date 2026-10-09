package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.io.InputStream

/** Bearer credentials never appear in state, URLs, logs or toString. */
class Bearer private constructor(private val value: String) {
    internal fun header() = "Bearer $value"
    override fun toString() = "Bearer([redacted])"
    companion object {
        fun from(response: SessionToken): Bearer {
            require(response.token_type == "Bearer" && response.expires_in == 86400L)
            require(response.access_token.matches(Regex("[A-Za-z0-9_-]{43}")))
            require(response.access_token != "F".repeat(43)) { "Fixture credentials are not accepted" }
            return Bearer(response.access_token)
        }
    }
}

enum class FailureKind { HTTP, OFFLINE, TLS, INVALID_RESPONSE, INVALID_INPUT, TOO_LARGE }
class ApiFailure(val kind: FailureKind, val status: Int? = null, val retryAfterMillis: Long = 0) : Exception("PhotoHouse request failed")

interface PhotoHouseApi {
    /** Protected family stories are opt-in until the integration owner enables the route. */
    val protectedNativeV2Enabled: Boolean get() = false
    /** Native whole-file photo contribution is separately opt-in and requires protected auth. */
    val uploadEnabled: Boolean get() = false
    suspend fun uploadPhoto(token: Bearer, source: UploadSource, batch: String, destinationLibraryId: String? = null,
                            onProgress: (Long) -> Unit = {}): UploadReceipt =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun uploadHistory(token: Bearer, page: Int = 1): UploadHistoryPage =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun postUploadTextAnnotation(token: Bearer, library: String, request: UploadTextAnnotationRequest): UploadAnnotation =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun postUploadAudioAnnotation(token: Bearer, library: String, request: UploadAudioAnnotationRequest): UploadAnnotation =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun uploadAnnotationAudio(token: Bearer, library: String, annotation: UploadAnnotation): ByteArray =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun uploadAnnotations(token: Bearer, library: String, assetId: String, page: Int = 1): UploadAnnotationPage =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun createUploadSession(token: Bearer, request: UploadSessionRequest): UploadSession =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun uploadSession(token: Bearer, uploadId: String): UploadSession =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun uploadChunk(token: Bearer, uploadId: String, offset: Long, chunk: ByteArray, sha256: String): UploadSession =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun completeUploadSession(token: Bearer, uploadId: String): UploadSession =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun cancelUploadSession(token: Bearer, uploadId: String): UploadSession =
        throw ApiFailure(FailureKind.INVALID_INPUT)
    val mediaFilterEnabled: Boolean get() = false
    val preparedBrowseEnabled: Boolean get() = false
    val preparedVideoEnabled: Boolean get() = false
    suspend fun preparedVideoInfo(token: Bearer, library: String, assetId: String): PreparedVideoInfo = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun preparedVideoRange(token: Bearer, library: String, assetId: String, info: PreparedVideoInfo, start: Long, length: Int): VideoChunk = throw ApiFailure(FailureKind.INVALID_INPUT)
    val photoDeliveryEnabled: Boolean get() = false
    suspend fun displayPhoto(token: Bearer, library: String, assetId: String): ByteArray = throw ApiFailure(FailureKind.INVALID_INPUT)
    val discoveryEnabled: Boolean get() = false
    /** Family note tag browsing is independently opt-in and requires protected native access. */
    val familyTagsEnabled: Boolean get() = false
    /** Protected read-only assistant capability is independently opt-in. */
    val assistantEnabled: Boolean get() = false
    suspend fun assistantCapabilities(token: Bearer, library: String): AssistantCapabilities = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun assistantTurn(token: Bearer, library: String, text: String, context: kotlinx.serialization.json.JsonObject?): AssistantTurn = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun assistantTurn(token: Bearer, library: String, text: String, context: kotlinx.serialization.json.JsonObject?, requestId: String, parentRequestId: String? = null): AssistantTurn = assistantTurn(token, library, text, context)
    suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray): AssistantTranscript = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript = assistantTranscribe(token, library, wav)
    suspend fun assistantSpeech(token: Bearer, library: String, context: kotlinx.serialization.json.JsonObject?, language: String): ByteArray = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun assistantSpeech(token: Bearer, library: String, context: kotlinx.serialization.json.JsonObject?, language: String, requestId: String, parentRequestId: String?): AssistantSpeechResult = AssistantSpeechResult(assistantSpeech(token, library, context, language), AssistantRequestReceipt(requestId, "unknown", null))
    suspend fun assistantReceipt(token: Bearer, library: String, requestId: String): AssistantReceipt = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun assistantOutcome(token: Bearer, library: String, requestId: String, outcome: String): Unit = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun facets(token: Bearer, library: String, facet: PhoneFacet, page: Int = 1, binding: String? = null): PhoneFacetPage = throw ApiFailure(FailureKind.INVALID_INPUT)
    /** Location-only facet query; legacy adapters may serve no-query pages but must reject unsupported queries. */
    suspend fun placeFacets(token: Bearer, library: String, page: Int = 1, query: String = "", binding: String? = null): PhoneFacetPage {
        if (query.isNotEmpty()) throw ApiFailure(FailureKind.INVALID_INPUT)
        return facets(token, library, PhoneFacet.PLACES, page, binding)
    }
    suspend fun search(token: Bearer, library: String, binding: String, filters: PhoneFilters, page: Int = 1, fingerprint: String? = null): PhoneSearchPage = throw ApiFailure(FailureKind.INVALID_INPUT)
    /** Separate protected, family-authored note tag catalog and asset lookup. */
    suspend fun familyTags(token: Bearer, library: String, page: Int = 1, query: String = ""): FamilyTagsPage = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun familyTagAssets(token: Bearer, library: String, tag: String, page: Int = 1): Gallery = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun login(phone: String, password: String): SessionToken
    suspend fun register(phone: String, password: String, code: String): SessionToken
    suspend fun registerNamed(phone: String, password: String, code: String, name: String): SessionToken = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun session(token: Bearer): Session
    suspend fun acceptInvitation(token: Bearer, code: String)
    suspend fun logout(token: Bearer)
    suspend fun gallery(token: Bearer, library: String, page: Int): Gallery
    suspend fun gallery(token: Bearer, library: String, page: Int, media: GalleryMedia): Gallery {
        require(media == GalleryMedia.ALL)
        return gallery(token, library, page)
    }
    suspend fun saveStory(token: Bearer, library: String, mutation: StoryMutation): ProtectedStory = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun currentStory(token: Bearer, library: String, assetId: String, storyId: String): ProtectedStory? = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun detail(token: Bearer, library: String, assetId: String): Detail
    suspend fun captions(token: Bearer, library: String, assetId: String): Captions
    suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray?
    /** Larger cached detail preview; default preserves existing phone and test adapters. */
    suspend fun detailPreview(token: Bearer, library: String, asset: Asset): ByteArray? = thumbnail(token, library, asset)
    suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk
    suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray
    suspend fun stories(token: Bearer, library: String, assetId: String, page: Int): ProtectedStoryPage = throw ApiFailure(FailureKind.INVALID_INPUT)
    /** Protected saved multi-asset family story drafts; kept separate from single-asset stories. */
    suspend fun savedMemoryStories(token: Bearer, library: String, page: Int = 1): SavedMemoryStoryPage = throw ApiFailure(FailureKind.INVALID_INPUT)
    /** Optional exact-theme filter. Legacy adapters continue to serve the unfiltered operation. */
    suspend fun savedMemoryStories(token: Bearer, library: String, page: Int, theme: String?): SavedMemoryStoryPage {
        if (theme == null) return savedMemoryStories(token, library, page)
        throw ApiFailure(FailureKind.INVALID_INPUT)
    }
    suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory = throw ApiFailure(FailureKind.INVALID_INPUT)
    /** Additive, read-only chapter source links; unsupported adapters keep saved-story v1 intact. */
    suspend fun savedMemoryStoryContributionReferences(
        token: Bearer, library: String, storyId: String, revision: Long, chapterIds: List<String>,
    ): SavedMemoryStoryContributionReferences = throw ApiFailure(FailureKind.INVALID_INPUT)
    suspend fun saveMemoryStoryContributionReferences(
        token: Bearer, library: String, mutation: SavedMemoryStoryContributionReferencesMutation,
    ): SavedMemoryStory = throw ApiFailure(FailureKind.INVALID_INPUT)
    /** Explicit source review uses the protected contribution detail route; audio has a separate operation. */
    suspend fun savedMemoryContributionDetail(
        token: Bearer, library: String, storyId: String, contributionId: String,
    ): MemoryContributionDetail = throw ApiFailure(FailureKind.INVALID_INPUT)
}

/** A caller-owned stream, normally backed by a persisted SAF URI. It is opened per attempt. */
data class UploadSource(val displayName: String, val bytes: Long, val open: () -> InputStream)

data class UploadReceipt(
    val assetId: String, val libraryId: String?, val incoming: String, val batch: String,
    val kind: String, val width: Int, val height: Int, val sha256: String,
    val bytes: Long, val tasksEnqueued: Int,
    val destinationLibraryId: String? = null, val approvalState: String? = null,
)

data class UploadHistoryItem(
    val assetId: String, val createdAt: Long, val bytes: Long,
    val kind: String, val state: String, val libraryId: String?
)

data class UploadHistoryPage(
    val page: Int, val pageSize: Int, val total: Int,
    val items: List<UploadHistoryItem>
)

data class UploadTextAnnotationRequest(
    val batch: String, val assetId: String, val language: String, val consent: String,
    val mutationId: String, val text: String,
)
class UploadAudioAnnotationRequest(
    val batch: String, val assetId: String, val language: String, val consent: String,
    val mutationId: String, val wav: ByteArray,
)
data class UploadAnnotationDerivation(
    val revision: Int, val state: String, val transcript: String?, val polishedText: String?,
    val provider: String?, val model: String?, val errorCode: String?,
)
data class UploadAnnotationTag(val tag: String, val status: String, val revision: Int)
data class UploadAnnotation(
    val id: String, val scope: String, val assetId: String, val batch: String, val libraryId: String,
    val authorId: String, val kind: String, val originalText: String?, val audioUrl: String?,
    val mime: String?, val durationMs: Long?, val sha256: String?, val language: String,
    val localProcessingConsent: String, val createdAt: Long, val derivation: UploadAnnotationDerivation,
    val tags: List<UploadAnnotationTag>,
)
data class UploadAnnotationPage(
    val libraryId: String, val assetId: String, val batch: String, val page: Int, val pageSize: Int,
    val total: Int, val items: List<UploadAnnotation>,
)

enum class UploadKind { IMAGE, VIDEO }
data class UploadSessionRequest(
    val requestId: String, val batch: String, val filename: String, val bytes: Long,
    val sha256: String, val kind: UploadKind, val destinationLibraryId: String? = null,
)
data class UploadSession(val uploadId: String, val bytes: Long, val offset: Long, val chunkBytes: Int, val state: String, val assetId: String?)
data class BatchUploadSource(val filename: String, val bytes: Long, val kind: UploadKind, val open: () -> InputStream, val locator: String? = null)

object Admission {
    /** Form convenience only; wire callers still require an explicit international number. */
    fun phoneFromForm(value: String, protectedNativeV2: Boolean): String {
        val compact = value.filterNot { it in " ()-" }
        val international = if (protectedNativeV2 && compact.matches(Regex("[0-9]{11}"))) "+86$compact" else compact
        return phone(international)
    }

    fun phone(value: String): String {
        val result = value.filterNot { it in " ()-" }
        require(result.matches(Regex("\\+[1-9][0-9]{7,14}"))) { "Use an international phone login" }
        return result
    }
    fun password(value: String, protectedNativeV2: Boolean = false, registration: Boolean = false) {
        require(value.toUtf8Strict()) { "Password contains malformed Unicode" }
        val points = value.codePointCount(0, value.length)
        val valid = if (!protectedNativeV2) points in 15..128 else points in (if (registration) 8..128 else 1..128)
        require(valid) { if (protectedNativeV2) "Password length is invalid" else "Password length must be 15 to 128 code points" }
    }

    /** Match Python str.split whitespace, counting Unicode code points after collapse. */
    fun displayName(value: String): String {
        require(value.toUtf8Strict())
        val collapsed = value.split(Regex("[\\u0009-\\u000D\\u001C-\\u0020\\u0085\\u00A0\\u1680\\u2000-\\u200A\\u2028\\u2029\\u202F\\u205F\\u3000]+"))
            .filter { it.isNotEmpty() }.joinToString(" ")
        require(collapsed.codePointCount(0, collapsed.length) in 1..64)
        require(collapsed.none { it < ' ' || it == '\u007f' })
        return collapsed
    }

    fun invitationCode(value: String): String {
        require(value.isNotBlank() && value.toUtf8Strict())
        return value
    }

    private fun String.toUtf8Strict(): Boolean = runCatching {
        Charsets.UTF_8.newEncoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
            .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(this))
    }.isSuccess
}

fun retryAfterMillis(value: String?, nowMillis: Long = System.currentTimeMillis()): Long {
    // Parse long server cooldowns without overflow; callers decide whether a
    // read may recover automatically or must wait for explicit retry.
    value?.toLongOrNull()?.let { return it.coerceIn(0, Long.MAX_VALUE / 1000) * 1000 }
    val date = runCatching { ZonedDateTime.parse(value, DateTimeFormatter.RFC_1123_DATE_TIME).toInstant().toEpochMilli() }.getOrNull()
    return if (date == null) 5000 else (date - nowMillis).coerceAtLeast(0)
}

/** Internal transport result, not a new wire DTO. */
data class VideoChunk(val start: Long, val total: Long, val bytes: ByteArray)

/** HEAD-derived identity, retained only for the current playback generation. */
data class PreparedVideoInfo(val bytes: Long, val etag: String) {
    init { require(bytes in 1..HttpsPhotoHouseApi.VIDEO_FILE_LIMIT && etag.matches(Regex("\"[0-9a-f]{64}\""))) }
}
