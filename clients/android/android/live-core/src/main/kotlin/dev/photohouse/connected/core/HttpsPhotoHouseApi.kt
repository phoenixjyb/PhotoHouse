package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.*
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class TrustedOrigin private constructor(internal val url: HttpUrl) {
    override fun toString() = "TrustedOrigin([configured])"
    companion object {
        fun parse(raw: String): TrustedOrigin {
            require(raw == raw.trim() && raw.none { it.isWhitespace() || it == '\\' })
            val url = raw.toHttpUrl()
            require(url.scheme == "https" && url.username.isEmpty() && url.password.isEmpty())
            require(url.encodedPath == "/" && url.query == null && url.fragment == null) { "Configure an HTTPS origin without credentials, path, query or fragment" }
            return TrustedOrigin(url)
        }
    }
}

/** Application construction always uses platform trust and hostname validation.
 * The internal overload is visible only to this module's JVM test friend source set.
 */
class HttpsPhotoHouseApi internal constructor(private val origin: TrustedOrigin, client: OkHttpClient, private val detailPreviewSize: Int = 256, override val discoveryEnabled: Boolean = false, override val photoDeliveryEnabled: Boolean = false, override val protectedNativeV2Enabled: Boolean = false, override val preparedVideoEnabled: Boolean = false, override val mediaFilterEnabled: Boolean = false, override val preparedBrowseEnabled: Boolean = false, override val uploadEnabled: Boolean = false, override val familyTagsEnabled: Boolean = false, override val assistantEnabled: Boolean = false, private val dateHintsEnabled: Boolean = false) : PhotoHouseApi, StoryWorkspaceApi {
    constructor(origin: TrustedOrigin, detailPreviewSize: Int = 256, discoveryEnabled: Boolean = false, photoDeliveryEnabled: Boolean = false, protectedNativeV2Enabled: Boolean = false, preparedVideoEnabled: Boolean = false, mediaFilterEnabled: Boolean = false, preparedBrowseEnabled: Boolean = false, uploadEnabled: Boolean = false, familyTagsEnabled: Boolean = false, assistantEnabled: Boolean = false, dateHintsEnabled: Boolean = false) : this(origin, OkHttpClient(), detailPreviewSize, discoveryEnabled, photoDeliveryEnabled, protectedNativeV2Enabled, preparedVideoEnabled, mediaFilterEnabled, preparedBrowseEnabled, uploadEnabled, familyTagsEnabled, assistantEnabled, dateHintsEnabled)
    init { require(detailPreviewSize in 64..1024); require(!preparedVideoEnabled || protectedNativeV2Enabled); require(!mediaFilterEnabled || protectedNativeV2Enabled); require(!preparedBrowseEnabled || mediaFilterEnabled && preparedVideoEnabled); require(!uploadEnabled || protectedNativeV2Enabled); require(!familyTagsEnabled || protectedNativeV2Enabled) }
    private val client = client.newBuilder()
        .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
        .cookieJar(CookieJar.NO_COOKIES).cache(null)
        .authenticator(Authenticator.NONE).proxyAuthenticator(Authenticator.NONE)
        .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS))
        .connectTimeout(10, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS)
        .build()
    private val uploadClient = this.client.newBuilder().callTimeout(2, TimeUnit.MINUTES).writeTimeout(30, TimeUnit.SECONDS).build()
    private val assistantAsrClient = this.client.newBuilder().readTimeout(50, TimeUnit.SECONDS).callTimeout(55, TimeUnit.SECONDS).build()
    // Completion hashes the full original on the server. A lost reply is reconciled
    // by GET on explicit resume, using the same idempotent transfer ledger.
    private val completionClient = this.client.newBuilder()
        .callTimeout(10, TimeUnit.MINUTES).readTimeout(10, TimeUnit.MINUTES).build()
    private data class Packet(val code: Int, val contentType: String?, val bytes: ByteArray, val total: Long = 0,
                              val etag: String? = null, val cacheControl: String? = null, val contentEncoding: String? = null,
                              val assistantHeaders: Map<String, String> = emptyMap())
    @Volatile private var dateHintsAvailable: Boolean? = null
    private fun assistantResponseHeaders(headers: Headers): Map<String, String> {
        val names = listOf("X-PhotoHouse-Tracking", "X-PhotoHouse-Request-Id", "X-PhotoHouse-Receipt-Status")
        return names.mapNotNull { name ->
            val values = headers.values(name)
            if (values.size > 1) throw ApiFailure(FailureKind.INVALID_RESPONSE)
            values.singleOrNull()?.let { name to it }
        }.toMap()
    }

    override suspend fun uploadPhoto(token: Bearer, source: UploadSource, batch: String, destinationLibraryId: String?,
                                     onProgress: (Long) -> Unit): UploadReceipt {
        require(uploadEnabled && protectedNativeV2Enabled)
        require(batch.matches(Regex("[0-9a-f]{32}")))
        destinationLibraryId?.let(::requireDestinationLibraryId)
        require(source.bytes in 1..MAX_UPLOAD_BYTES)
        require(source.displayName.isNotEmpty() && source.displayName.length <= MAX_UPLOAD_NAME &&
            source.displayName.none { it == '\u0000' || it == '\r' || it == '\n' })
        val streamedDigest = AtomicReference<String?>(null)
        val requestBody = object : RequestBody() {
            override fun contentType() = "application/octet-stream".toMediaType()
            override fun contentLength() = source.bytes
            override fun isOneShot() = true
            override fun writeTo(sink: okio.BufferedSink) {
                var sent = 0L
                val digest = MessageDigest.getInstance("SHA-256")
                source.open().use { input ->
                    val buffer = ByteArray(32 * 1024)
                    while (true) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        if (n == 0) throw IOException("source did not advance")
                        sent += n
                        if (sent > source.bytes) throw IOException("source exceeded declared length")
                        sink.write(buffer, 0, n)
                        digest.update(buffer, 0, n)
                        onProgress(sent)
                    }
                }
                if (sent != source.bytes) throw IOException("source length changed")
                streamedDigest.set(digest.digest().joinToString("") { "%02x".format(it) })
            }
        }
        val request = Request.Builder().url(url("/uploads"))
            .header("Authorization", token.header()).header("Accept", "application/json")
            .header("Cache-Control", "no-store").header("Accept-Encoding", "identity")
            .header("X-Upload-Filename", source.displayName).header("X-Upload-Batch", batch)
            .apply { destinationLibraryId?.let { header("X-Upload-Destination-Library", it) } }
            .post(requestBody).build()
        return suspendCancellableCoroutine { continuation ->
            val call = uploadClient.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(if (e is SSLException) ApiFailure(FailureKind.TLS) else ApiFailure(FailureKind.OFFLINE))
                }
                override fun onResponse(call: Call, response: Response) {
                    try {
                        response.use {
                            if (it.code != 201) throw ApiFailure(FailureKind.HTTP, it.code,
                                if (it.code == 429 || it.code in 502..504) retryAfterMillis(it.header("Retry-After")) else 0)
                            if (it.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val body = it.body ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (body.contentLength() !in 1..UPLOAD_JSON_LIMIT) throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val bytes = readBody(body, UPLOAD_JSON_LIMIT)
                            val receipt = parseUploadReceipt(bytes)
                            if (receipt.destinationLibraryId != destinationLibraryId ||
                                (receipt.libraryId != null && receipt.libraryId != destinationLibraryId) ||
                                receipt.bytes != source.bytes || receipt.sha256 != streamedDigest.get())
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (continuation.isActive) continuation.resume(receipt)
                        }
                    } catch (e: Exception) {
                        if (continuation.isActive) continuation.resumeWithException(if (e is ApiFailure) e else ApiFailure(FailureKind.INVALID_RESPONSE))
                    }
                }
            })
        }
    }

    override suspend fun uploadHistory(token: Bearer, page: Int): UploadHistoryPage {
        require(uploadEnabled && protectedNativeV2Enabled && page in 1..100000)
        val requestUrl = origin.url.newBuilder().encodedPath("/uploads")
            .addQueryParameter("page", page.toString()).build()
        val response = packet(requestUrl, token, limit = 64 * 1024)
        if (response.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return UploadHistoryWire.parse(response.bytes, page)
    }

    override suspend fun postUploadTextAnnotation(token: Bearer, library: String, request: UploadTextAnnotationRequest): UploadAnnotation {
        require(uploadEnabled && protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library))
        val body = UploadAnnotationsWire.request(request)
        val response = packet(url("/upload-annotations/text", library), token, body,
            limit = UploadAnnotationsWire.ANNOTATION_ITEM_LIMIT, requestLimit = 6 * UploadAnnotationsWire.MAX_TEXT_BYTES + 1024)
        if (response.code != 201 || response.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        val annotation = UploadAnnotationsWire.parseItem(response.bytes)
        if (annotation.libraryId != library || annotation.batch != request.batch || annotation.assetId != request.assetId ||
            annotation.originalText != request.text || annotation.language != request.language ||
            annotation.localProcessingConsent != request.consent || annotation.kind != "text" ||
            annotation.scope != if (request.assetId.isEmpty()) "folder" else "item")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return annotation
    }

    override suspend fun postUploadAudioAnnotation(token: Bearer, library: String, request: UploadAudioAnnotationRequest): UploadAnnotation {
        require(uploadEnabled && protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library))
        val info = UploadAnnotationsWire.audioInfo(request)
        val networkRequest = Request.Builder().url(url("/upload-annotations/audio", library))
            .header("Authorization", token.header()).header("Accept", "application/json")
            .header("Cache-Control", "no-store").header("Accept-Encoding", "identity")
            .header("X-Annotation-Batch", request.batch)
            .header("X-Annotation-Language", request.language)
            .header("X-Local-Processing-Consent", request.consent)
            .header("X-Annotation-Mutation-Id", request.mutationId)
            .apply { if (request.assetId.isNotEmpty()) header("X-Annotation-Asset-Id", request.assetId) }
            .post(request.wav.toRequestBody("audio/wav".toMediaType())).build()
        return suspendCancellableCoroutine { continuation ->
            val call = uploadClient.newCall(networkRequest)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(
                        ApiFailure(if (e is SSLException) FailureKind.TLS else FailureKind.OFFLINE))
                }
                override fun onResponse(call: Call, response: Response) {
                    try {
                        response.use {
                            if (it.code != 201) throw ApiFailure(FailureKind.HTTP, it.code,
                                if (it.code == 429 || it.code in 502..504) retryAfterMillis(it.header("Retry-After")) else 0)
                            if (it.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "application/json")
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val body = it.body ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (body.contentLength() == 0L || body.contentLength() > UploadAnnotationsWire.ANNOTATION_ITEM_LIMIT)
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val annotation = UploadAnnotationsWire.parseItem(readBody(body, UploadAnnotationsWire.ANNOTATION_ITEM_LIMIT))
                            if (annotation.libraryId != library || annotation.batch != request.batch ||
                                annotation.assetId != request.assetId || annotation.language != request.language ||
                                annotation.localProcessingConsent != request.consent || annotation.kind != "audio" ||
                                annotation.scope != (if (request.assetId.isEmpty()) "folder" else "item") ||
                                annotation.sha256 != info.sha256 || annotation.durationMs != info.durationMs ||
                                annotation.mime != "audio/wav" || annotation.audioUrl == null)
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (continuation.isActive) continuation.resume(annotation)
                        }
                    } catch (e: Exception) {
                        if (continuation.isActive) continuation.resumeWithException(
                            if (e is ApiFailure) e else ApiFailure(FailureKind.INVALID_RESPONSE))
                    }
                }
            })
        }
    }

    override suspend fun uploadAnnotationAudio(token: Bearer, library: String, annotation: UploadAnnotation): ByteArray {
        require(uploadEnabled && protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library))
        require(annotation.libraryId == library && annotation.kind == "audio" && annotation.mime == "audio/wav" &&
            annotation.audioUrl != null && annotation.sha256?.matches(Regex("[0-9a-f]{64}")) == true &&
            annotation.durationMs != null && annotation.durationMs in 500..60_000)
        require(annotation.id.matches(Regex("[A-Za-z0-9_-]{1,128}")) &&
            (annotation.assetId.isEmpty() || assetId(annotation.assetId) == annotation.assetId))
        val target = url("/upload-annotations/${annotation.id}/audio", library).newBuilder()
            .addQueryParameter("asset_id", annotation.assetId).build()
        val expectedReference = target.encodedPath + "?" + target.encodedQuery
        if (annotation.audioUrl != expectedReference) throw ApiFailure(FailureKind.INVALID_INPUT)
        val response = packet(target, token, limit = UploadAnnotationsWire.MAX_AUDIO_BYTES,
            accept = "audio/wav", method = "GET")
        val responseDisablesCaching = response.cacheControl?.split(',')
            ?.any { it.trim().equals("no-store", ignoreCase = true) } == true
        if (response.code != 200 || response.bytes.isEmpty() ||
            response.contentType?.substringBefore(';')?.trim()?.lowercase() != "audio/wav" ||
            response.contentEncoding?.lowercase() !in listOf(null, "identity") ||
            !responseDisablesCaching) {
            response.bytes.fill(0)
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        }
        val info = try {
            UploadAnnotationsWire.audioInfo(UploadAudioAnnotationRequest(annotation.batch, annotation.assetId,
                annotation.language, annotation.localProcessingConsent, java.util.UUID.randomUUID().toString(), response.bytes))
        } catch (_: Exception) {
            response.bytes.fill(0)
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        }
        if (info.sha256 != annotation.sha256 || info.durationMs != annotation.durationMs) {
            response.bytes.fill(0)
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        }
        return response.bytes
    }

    override suspend fun uploadAnnotations(token: Bearer, library: String, assetId: String, page: Int): UploadAnnotationPage {
        require(uploadEnabled && protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library) &&
            assetId.matches(Regex("[1-9][0-9]{0,18}")) && assetId.toLongOrNull() != null && page in 1..100000)
        val target = url("/upload-annotations", library).newBuilder()
            .addQueryParameter("asset_id", assetId).addQueryParameter("page", page.toString()).build()
        val response = packet(target, token, limit = UploadAnnotationsWire.ANNOTATION_PAGE_LIMIT)
        if (response.code != 200 || response.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return UploadAnnotationsWire.parsePage(response.bytes, library, assetId, page)
    }

    override suspend fun createUploadSession(token: Bearer, request: UploadSessionRequest): UploadSession {
        require(uploadEnabled && protectedNativeV2Enabled)
        request.destinationLibraryId?.let(::requireDestinationLibraryId)
        val result = packet(url("/upload-sessions"), token, UploadSessionWire.request(request), limit = UPLOAD_JSON_LIMIT, requestLimit = 1024)
        if (result.code != 201 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return UploadSessionWire.parse(result.bytes)
    }

    private fun requireDestinationLibraryId(value: String) {
        require(value.isNotBlank() && value.length <= 128 && value.none(Char::isISOControl))
    }
    override suspend fun uploadSession(token: Bearer, uploadId: String): UploadSession {
        val result = packet(sessionUrl(uploadId), token, limit = UPLOAD_JSON_LIMIT)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return UploadSessionWire.parse(result.bytes)
    }
    override suspend fun uploadChunk(token: Bearer, uploadId: String, offset: Long, chunk: ByteArray, sha256: String): UploadSession {
        require(offset >= 0 && chunk.size in 1..(4 * 1024 * 1024) && sha256.matches(Regex("[0-9a-f]{64}")))
        val request = Request.Builder().url(sessionUrl(uploadId)).header("Authorization", token.header()).header("Accept", "application/json")
            .header("Content-Type", "application/octet-stream").header("Upload-Offset", offset.toString()).header("X-Chunk-SHA256", sha256)
            .put(chunk.toRequestBody("application/octet-stream".toMediaType())).build()
        return rawSession(request, 200)
    }
    override suspend fun completeUploadSession(token: Bearer, uploadId: String): UploadSession {
        val request = Request.Builder().url(completeUrl(uploadId))
            .header("Authorization", token.header()).header("Accept", "application/json")
            .post("{}".toRequestBody("application/json; charset=utf-8".toMediaType())).build()
        return rawSession(request, 200, completionClient)
    }
    override suspend fun cancelUploadSession(token: Bearer, uploadId: String): UploadSession {
        val result = packet(sessionUrl(uploadId), token, limit = UPLOAD_JSON_LIMIT, method = "DELETE")
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return UploadSessionWire.parse(result.bytes)
    }
    private fun sessionUrl(id: String): HttpUrl { require(id.matches(Regex("[0-9a-f]{32}"))); return origin.url.newBuilder().addPathSegments("upload-sessions/$id").build() }
    private fun completeUrl(id: String): HttpUrl { require(id.matches(Regex("[0-9a-f]{32}"))); return origin.url.newBuilder().addPathSegments("upload-sessions/$id/complete").build() }
    private suspend fun rawSession(request: Request, expected: Int, networkClient: OkHttpClient = uploadClient): UploadSession = suspendCancellableCoroutine { continuation ->
        val call = networkClient.newCall(request); continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { if (continuation.isActive) continuation.resumeWithException(if (e is SSLException) ApiFailure(FailureKind.TLS) else ApiFailure(FailureKind.OFFLINE)) }
            override fun onResponse(call: Call, response: Response) {
                try { response.use {
                    if (it.code != expected) throw ApiFailure(FailureKind.HTTP, it.code, if (it.code == 429) retryAfterMillis(it.header("Retry-After")) else 0)
                    if (it.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
                    val body = it.body ?: throw ApiFailure(FailureKind.INVALID_RESPONSE); val bytes = readBody(body, UPLOAD_JSON_LIMIT)
                    if (continuation.isActive) continuation.resume(UploadSessionWire.parse(bytes))
                } } catch (e: Exception) { if (continuation.isActive) continuation.resumeWithException(if (e is ApiFailure) e else ApiFailure(FailureKind.INVALID_RESPONSE)) }
            }
        })
    }

    private fun parseUploadReceipt(bytes: ByteArray): UploadReceipt {
        val obj = try { DiscoveryJson.parse(bytes, UPLOAD_JSON_LIMIT).jsonObject } catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_RESPONSE) }
        val expected = setOf("asset_id", "library_id", "incoming", "batch", "kind", "width", "height", "sha256", "bytes", "tasks_enqueued")
        val bound = expected + setOf("destination_library_id", "approval_state")
        if (obj.keys != expected && obj.keys != bound) throw ApiFailure(FailureKind.INVALID_RESPONSE)
        fun str(name: String) = (obj[name] as? JsonPrimitive)?.takeIf { it.isString }?.content ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
        fun number(name: String) = (obj[name] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toLongOrNull() ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
        val assetId = str("asset_id").also { require(it.matches(Regex("[1-9][0-9]{0,18}"))) }
        val library = obj["library_id"].let { if (it == JsonNull) null else str("library_id") }
        val destination = if (obj.keys == bound) str("destination_library_id") else null
        val approval = if (obj.keys == bound) str("approval_state") else null
        if (approval != null) require(approval in setOf("awaiting_review", "automatic", "manual") &&
            destination != null && destination.isNotBlank() &&
            ((approval == "awaiting_review") == (library == null)))
        val incoming = str("incoming"); val batch = str("batch"); val kind = str("kind"); val sha = str("sha256")
        val width = number("width").also { require(it in 1..64 * 1024 * 1024) }.toInt()
        val height = number("height").also { require(it in 1..64 * 1024 * 1024) }.toInt()
        val size = number("bytes").also { require(it in 1..MAX_UPLOAD_BYTES) }
        val tasks = number("tasks_enqueued").also { require(it in 0..16) }.toInt()
        require(width.toLong() * height <= 64L * 1024 * 1024)
        require(batch.matches(Regex("[0-9a-f]{32}")) && kind == "image" && sha.matches(Regex("[0-9a-f]{64}")))
        return UploadReceipt(assetId, library, incoming, batch, kind, width, height, sha, size, tasks,
            destination, approval)
    }

    private fun url(path: String, library: String? = null, page: Int? = null): HttpUrl {
        require(path.startsWith('/') && !path.startsWith("//"))
        return origin.url.newBuilder().encodedPath(path).apply {
            library?.let { require(it.isNotBlank() && it.length <= 256); addQueryParameter("library", it) }
            page?.let { require(it in 1..100000); addQueryParameter("page", it.toString()); addQueryParameter("page_size", "50") }
        }.build()
    }
    private fun storiesUrl(library: String, assetId: String, page: Int): HttpUrl {
        require(protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library) && page in 1..100000)
        return origin.url.newBuilder().addPathSegments("assets/${assetId(assetId)}/stories")
            .addQueryParameter("library", library).addQueryParameter("page", page.toString()).build()
    }
    private fun savedMemoryStoriesUrl(library: String, page: Int, theme: String?): HttpUrl {
        require(protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library) && page in 1..100000)
        require(theme == null || theme in SAVED_MEMORY_STORY_THEMES)
        return origin.url.newBuilder().addPathSegments("memory-stories")
            .addQueryParameter("library", library).addQueryParameter("page", page.toString()).apply {
                theme?.let { addQueryParameter("theme", it) }
            }.build()
    }
    private fun assetId(id: String): String {
        require(id.matches(Regex("[1-9][0-9]{0,18}")) && id.toLongOrNull() != null)
        return id
    }
    /** Known lengths allocate once; large originals never grow and copy a second full buffer. */
    private fun readBody(body: ResponseBody, limit: Int): ByteArray {
        val length = body.contentLength()
        if (length > limit || length < 0 && limit > DISPLAY_LIMIT) throw ApiFailure(FailureKind.TOO_LARGE)
        return body.byteStream().use { stream ->
            if (length >= 0) {
                val data = ByteArray(length.toInt()); var offset = 0
                while (offset < data.size) {
                    val n = stream.read(data, offset, data.size - offset)
                    if (n <= 0) throw ApiFailure(FailureKind.INVALID_RESPONSE)
                    offset += n
                }
                if (stream.read() != -1) throw ApiFailure(FailureKind.INVALID_RESPONSE)
                data
            } else {
                val out = ByteArrayOutputStream(); val buffer = ByteArray(8192)
                while (true) {
                    val n = stream.read(buffer); if (n < 0) break
                    if (out.size() + n > limit) throw ApiFailure(FailureKind.TOO_LARGE)
                    out.write(buffer, 0, n)
                }
                out.toByteArray()
            }
        }
    }
    private suspend fun packet(url: HttpUrl, token: Bearer?, body: String? = null, limit: Int = JSON_LIMIT, missingAllowed: Boolean = false, accept: String = "application/json", rangeStart: Long? = null, requestLimit: Int = 2048, prepared: Boolean = false, head: Boolean = false, preparedEtag: String? = null, method: String = "POST", extraHeaders: Map<String, String> = emptyMap()): Packet {
        require(url.scheme == "https" && url.host == origin.url.host && url.port == origin.url.port)
        val bytes = body?.toByteArray(Charsets.UTF_8)
        if (bytes != null && bytes.size > requestLimit) throw ApiFailure(FailureKind.INVALID_INPUT)
        val request = Request.Builder().url(url).header("Accept", accept)
            .header("Cache-Control", "no-store").header("Accept-Encoding", "identity")
            .apply { rangeStart?.let { header("Range", "bytes=$it-${it + limit - 1}"); header("Accept-Encoding", "identity") } }
            .apply { token?.let { header("Authorization", it.header()) } }
            .apply { extraHeaders.forEach { (name, value) -> header(name, value) } }
            .apply { if (head) head(); preparedEtag?.let { header("If-Range", it) } }
            .apply { if (bytes != null) { require(method in setOf("POST", "PUT")); method(method, bytes.toRequestBody("application/json; charset=utf-8".toMediaType())) } else if (method != "POST") method(method, null) }
            .build()
        return suspendCancellableCoroutine { continuation ->
            val call = client.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(ApiFailure(if (e is SSLException) FailureKind.TLS else FailureKind.OFFLINE))
                }
                override fun onResponse(call: Call, response: Response) {
                    try {
                        val result = response.use {
                            if (it.code !in 200..299 && !(missingAllowed && it.code == 404)) {
                                val retryAfter = it.header("Retry-After")
                                throw ApiFailure(FailureKind.HTTP, it.code,
                                    when {
                                        it.code == 429 -> retryAfterMillis(retryAfter)
                                        it.code in 502..504 && retryAfter != null -> retryAfterMillis(retryAfter)
                                        else -> 0
                                    })
                            }
                            if (it.code == 404) return@use Packet(404, null, byteArrayOf())
                            var total = 0L
                            var expectedBytes = -1L
                            if (prepared) {
                                for (name in listOf("Content-Type", "Content-Length", "Content-Range", "Content-Encoding", "ETag", "Accept-Ranges", "Cache-Control"))
                                    if (it.headers.values(name).size > 1) throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                if (it.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "video/mp4" ||
                                    it.header("Content-Encoding")?.lowercase() !in listOf(null, "identity") ||
                                    it.header("Cache-Control") != "no-store" || it.header("Accept-Ranges") != "bytes" ||
                                    !it.header("ETag").orEmpty().matches(Regex("\"[0-9a-f]{64}\""))) throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                if (preparedEtag != null && (it.header("ETag") != preparedEtag || it.code == 200))
                                    throw ApiFailure(FailureKind.HTTP, 409)
                                if (head) {
                                    val length = it.header("Content-Length")?.toLongOrNull() ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                    if (length > VIDEO_FILE_LIMIT) throw ApiFailure(FailureKind.TOO_LARGE)
                                    if (it.code != 200 || length < 1 || it.header("Content-Range") != null) throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                    return@use Packet(200, "video/mp4", byteArrayOf(), length, it.header("ETag"))
                                }
                            }
                            if (rangeStart != null) {
                                if (it.code != 206 || it.header("Content-Encoding")?.lowercase() !in listOf(null, "identity") ||
                                    it.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() !in setOf("video/mp4", "video/webm"))
                                    throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                val parts = Regex("bytes ([0-9]+)-([0-9]+)/([0-9]+)").matchEntire(it.header("Content-Range").orEmpty())
                                    ?.groupValues ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                val start = parts[1].toLongOrNull() ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                val end = parts[2].toLongOrNull() ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                total = parts[3].toLongOrNull() ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                if (total > VIDEO_FILE_LIMIT) throw ApiFailure(FailureKind.TOO_LARGE)
                                if (total <= 0 || start != rangeStart || end != minOf(start + limit - 1, total - 1) || end < start)
                                    throw ApiFailure(FailureKind.INVALID_RESPONSE)
                                expectedBytes = end - start + 1
                            }
                            val responseBody = it.body ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (responseBody.contentLength() > limit) throw ApiFailure(FailureKind.TOO_LARGE)
                            val data = readBody(responseBody, limit)
                            if (expectedBytes >= 0 && data.size.toLong() != expectedBytes) throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            Packet(it.code, it.header("Content-Type"), data, total, it.header("ETag"),
                                it.header("Cache-Control"), it.header("Content-Encoding"),
                                if (url.encodedPath == "/assistant/v1/turns") assistantResponseHeaders(it.headers) else emptyMap())
                        }
                        if (continuation.isActive) continuation.resume(result)
                    } catch (_: OutOfMemoryError) {
                        if (continuation.isActive) continuation.resumeWithException(ApiFailure(FailureKind.TOO_LARGE))
                    } catch (e: Exception) {
                        if (continuation.isActive) continuation.resumeWithException(when (e) {
                            is ApiFailure -> e
                            is SSLException -> ApiFailure(FailureKind.TLS)
                            is IOException -> ApiFailure(FailureKind.OFFLINE)
                            else -> ApiFailure(FailureKind.INVALID_RESPONSE)
                        })
                    }
                }
            })
        }
    }
    private suspend fun <T> json(url: HttpUrl, serializer: KSerializer<T>, token: Bearer? = null, body: String? = null): T {
        val packet = packet(url, token, body)
        if (packet.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return try { Wire.json.decodeFromString(serializer, packet.bytes.toString(Charsets.UTF_8)) }
        catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_RESPONSE) }
    }
    private suspend fun <T> datedJson(url: HttpUrl, serializer: KSerializer<T>, token: Bearer): T {
        if (!dateHintsEnabled) return json(url, serializer, token)
        if (dateHintsAvailable == false) return json(url, serializer, token)
        return try {
            json(url.newBuilder().addQueryParameter("date_hints", "1").build(), serializer, token).also {
                dateHintsAvailable = true
            }
        } catch (failure: ApiFailure) {
            if (failure.kind != FailureKind.HTTP || failure.status != 400) throw failure
            dateHintsAvailable = false
            json(url, serializer, token)
        }
    }
    private fun discoveryUrl(library: String, operation: String): HttpUrl {
        require(discoveryEnabled && PhoneDiscoveryWire.validLibrary(library))
        return origin.url.newBuilder().addPathSegment("libraries").addPathSegment(library)
            .addPathSegments("discovery/v1").addPathSegment(operation).build()
    }
    override suspend fun facets(token: Bearer, library: String, facet: PhoneFacet, page: Int, binding: String?): PhoneFacetPage {
        require(page in 1..5000 && (binding == null || PhoneDiscoveryWire.validHash(binding)) && (page == 1 || binding != null))
        val target = discoveryUrl(library, "facets").newBuilder().addQueryParameter("facet", facet.wire)
            .addQueryParameter("page", page.toString()).addQueryParameter("page_size", "50")
            .apply { binding?.let { addQueryParameter("binding", it) } }.build()
        val result = packet(target, token)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return PhoneDiscoveryWire.facets(result.bytes, library, facet, page, binding = binding)
    }
    override suspend fun placeFacets(token: Bearer, library: String, page: Int, query: String, binding: String?): PhoneFacetPage {
        require(PhoneDiscoveryWire.validPlaceQuery(query))
        require(page in 1..5000 && (binding == null || PhoneDiscoveryWire.validHash(binding)) && (page == 1 || binding != null))
        val target = discoveryUrl(library, "facets").newBuilder().addQueryParameter("facet", PhoneFacet.PLACES.wire)
            .addQueryParameter("page", page.toString()).addQueryParameter("page_size", "50")
            .apply { if (query.isNotEmpty()) addQueryParameter("q", query) }
            .apply { binding?.let { addQueryParameter("binding", it) } }.build()
        val result = packet(target, token)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return PhoneDiscoveryWire.facets(result.bytes, library, PhoneFacet.PLACES, page, binding = binding)
    }
    override suspend fun search(token: Bearer, library: String, binding: String, filters: PhoneFilters, page: Int, fingerprint: String?): PhoneSearchPage {
        val target = discoveryUrl(library, "search")
        val body = PhoneDiscoveryWire.request(binding, filters, page, fingerprint = fingerprint)
        val result = packet(target, token, body, requestLimit = 20 * 1024)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return PhoneDiscoveryWire.search(result.bytes, library, binding, page, fingerprint = fingerprint)
    }
    override suspend fun assistantCapabilities(token: Bearer, library: String): AssistantCapabilities {
        require(assistantEnabled && PhoneDiscoveryWire.validLibrary(library))
        val target = origin.url.newBuilder().addPathSegments("assistant/v1/capabilities")
            .addQueryParameter("library_id", library).build()
        val result = packet(target, token, limit = 4096)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return AssistantWire.capabilities(result.bytes)
    }
    override suspend fun assistantTurn(token: Bearer, library: String, text: String, context: JsonObject?): AssistantTurn {
        return assistantTurn(token, library, text, context, java.util.UUID.randomUUID().toString()).copy(receipt = null)
    }
    override suspend fun assistantTurn(token: Bearer, library: String, text: String, context: JsonObject?, requestId: String, parentRequestId: String?): AssistantTurn {
        require(assistantEnabled && PhoneDiscoveryWire.validLibrary(library))
        require(AssistantWire.validRequestId(requestId) && (parentRequestId == null || AssistantWire.validRequestId(parentRequestId)))
        val body = AssistantWire.request(library, text, context)
        val result = packet(origin.url.newBuilder().addPathSegments("assistant/v1/turns").build(), token, body,
            limit = 256 * 1024, requestLimit = 20 * 1024,
            extraHeaders = buildMap { put("X-PhotoHouse-Request-Id", requestId); parentRequestId?.let { put("X-PhotoHouse-Parent-Request-Id", it) } })
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return AssistantWire.response(result.bytes, library).copy(receipt = AssistantWire.requestReceipt(result.assistantHeaders, requestId))
    }
    override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray): AssistantTranscript {
        return assistantTranscribe(token, library, wav, java.util.UUID.randomUUID().toString()).copy(receipt = null)
    }
    override suspend fun assistantTranscribe(token: Bearer, library: String, wav: ByteArray, requestId: String): AssistantTranscript {
        require(assistantEnabled && PhoneDiscoveryWire.validLibrary(library))
        require(AssistantWire.validRequestId(requestId))
        require(wav.size in 46..(44 + 16_000 * 2 * 30) && wav.copyOfRange(0, 4).contentEquals("RIFF".toByteArray()) &&
            wav.copyOfRange(8, 12).contentEquals("WAVE".toByteArray()))
        val target = origin.url.newBuilder().addPathSegments("assistant/v1/transcribe").build()
        val request = Request.Builder().url(target).header("Accept", "application/json")
            .header("Cache-Control", "no-store").header("Accept-Encoding", "identity")
            .header("Authorization", token.header()).header("X-PhotoHouse-Library-Id", library)
            .header("X-PhotoHouse-Request-Id", requestId)
            .post(wav.toRequestBody("audio/wav".toMediaType())).build()
        val result = suspendCancellableCoroutine<Packet> { continuation ->
            val call = assistantAsrClient.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(ApiFailure(if (e is SSLException) FailureKind.TLS else FailureKind.OFFLINE))
                }
                override fun onResponse(call: Call, response: Response) {
                    try {
                        val p = response.use { r ->
                            if (r.code !in 200..299) throw ApiFailure(FailureKind.HTTP, r.code)
                            val type = r.header("Content-Type")
                            if (type?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            Packet(r.code, type, r.body?.byteStream()?.use { stream ->
                                val out = ByteArrayOutputStream(); val buffer = ByteArray(4096)
                                while (true) { val n = stream.read(buffer); if (n < 0) break; if (out.size() + n > 8192) throw ApiFailure(FailureKind.TOO_LARGE); out.write(buffer, 0, n) }
                                out.toByteArray()
                            } ?: throw ApiFailure(FailureKind.INVALID_RESPONSE), assistantHeaders = assistantResponseHeaders(r.headers))
                        }
                        if (continuation.isActive) continuation.resume(p)
                    } catch (e: Exception) { if (continuation.isActive) continuation.resumeWithException(e) }
                }
            })
        }
        return AssistantWire.transcript(result.bytes).copy(receipt = AssistantWire.requestReceipt(result.assistantHeaders, requestId))
    }
    override suspend fun assistantSpeech(token: Bearer, library: String, context: JsonObject?, language: String): ByteArray {
        return assistantSpeech(token, library, context, language, java.util.UUID.randomUUID().toString(), null).bytes
    }
    override suspend fun assistantSpeech(token: Bearer, library: String, context: JsonObject?, language: String, requestId: String, parentRequestId: String?): AssistantSpeechResult {
        require(assistantEnabled)
        require(AssistantWire.validRequestId(requestId) && (parentRequestId == null || AssistantWire.validRequestId(parentRequestId)))
        val body = AssistantWire.speechRequest(library, context, language)
        val target = origin.url.newBuilder().addPathSegments("assistant/v1/speech").build()
        val request = Request.Builder().url(target).header("Accept", "audio/wav")
            .header("Cache-Control", "no-store").header("Accept-Encoding", "identity")
            .header("Authorization", token.header())
            .header("X-PhotoHouse-Request-Id", requestId).apply { parentRequestId?.let { header("X-PhotoHouse-Parent-Request-Id", it) } }
            .post(body.toRequestBody("application/json; charset=utf-8".toMediaType())).build()
        val result = suspendCancellableCoroutine<Pair<ByteArray, Map<String, String>>> { continuation ->
            val call = client.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(ApiFailure(if (e is SSLException) FailureKind.TLS else FailureKind.OFFLINE))
                }
                override fun onResponse(call: Call, response: Response) {
                    try {
                        val audio = response.use { r ->
                            if (r.code !in 200..299) throw ApiFailure(FailureKind.HTTP, r.code)
                            val type = r.header("Content-Type")
                            val cache = r.header("Cache-Control").orEmpty().split(',').map { it.trim().lowercase() }.toSet()
                            if (type?.substringBefore(';')?.trim()?.lowercase() != "audio/wav" || "no-store" !in cache)
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val stream = r.body?.byteStream() ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val output = ByteArrayOutputStream(); val buffer = ByteArray(8192)
                            stream.use { input -> while (true) {
                                val count = input.read(buffer); if (count < 0) break
                                if (output.size() + count > 2 * 1024 * 1024) throw ApiFailure(FailureKind.TOO_LARGE)
                                output.write(buffer, 0, count)
                            } }
                            AssistantWire.speechAudio(output.toByteArray()) to assistantResponseHeaders(r.headers)
                        }
                        if (continuation.isActive) continuation.resume(audio)
                    } catch (e: Exception) { if (continuation.isActive) continuation.resumeWithException(e) }
                }
            })
        }
        return AssistantSpeechResult(result.first, AssistantWire.requestReceipt(result.second, requestId))
    }
    override suspend fun assistantReceipt(token: Bearer, library: String, requestId: String): AssistantReceipt {
        require(assistantEnabled && PhoneDiscoveryWire.validLibrary(library) && AssistantWire.validRequestId(requestId))
        val target = origin.url.newBuilder().addPathSegments("assistant/v1/receipts").addPathSegment(requestId)
            .addQueryParameter("library_id", library).build()
        val result = packet(target, token, limit = 16 * 1024, method = "GET")
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return AssistantWire.receipt(result.bytes, requestId)
    }
    override suspend fun assistantOutcome(token: Bearer, library: String, requestId: String, outcome: String) {
        require(assistantEnabled && PhoneDiscoveryWire.validLibrary(library) && AssistantWire.validRequestId(requestId) && outcome in setOf("displayed", "open_requested", "failed", "cancelled"))
        val body = buildJsonObject { put("library_id", library); put("outcome", outcome) }.toString()
        val target = origin.url.newBuilder().addPathSegments("assistant/v1/receipts").addPathSegment(requestId).addPathSegment("outcome").build()
        val result = packet(target, token, body, limit = 2048, requestLimit = 1024)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        val response = try { DiscoveryJson.parse(result.bytes, 2048).jsonObject } catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_RESPONSE) }
        if (response.keys != setOf("version", "request_id", "client_outcome") ||
            response["version"]?.jsonPrimitive?.intOrNull != 1 || response["request_id"]?.jsonPrimitive?.content != requestId ||
            response["client_outcome"]?.jsonPrimitive?.content != outcome) throw ApiFailure(FailureKind.INVALID_RESPONSE)
    }
    override suspend fun familyTags(token: Bearer, library: String, page: Int, query: String): FamilyTagsPage {
        require(familyTagsEnabled && protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library) && page in 1..100000 && FamilyTagsWire.validQuery(query))
        val target = origin.url.newBuilder().addPathSegment("family-tags")
            .addQueryParameter("library", library).addQueryParameter("page", page.toString())
            .addQueryParameter("q", query).build()
        val result = packet(target, token)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return FamilyTagsWire.catalog(result.bytes, library, page)
    }
    override suspend fun familyTagAssets(token: Bearer, library: String, tag: String, page: Int): Gallery {
        require(familyTagsEnabled && protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library) && FamilyTagsWire.validTag(tag) && page in 1..100000)
        val target = origin.url.newBuilder().addPathSegment("family-tags").addPathSegment("assets")
            .addQueryParameter("library", library).build()
        val body = FamilyTagsWire.assetsRequest(tag, page)
        val result = packet(target, token, body, requestLimit = 1024)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return FamilyTagsWire.assets(result.bytes, library, tag, page)
    }
    override suspend fun login(phone: String, password: String): SessionToken {
        Admission.password(password, protectedNativeV2Enabled, registration = false)
        return json(url("/auth/login"), SessionToken.serializer(), body = Wire.json.encodeToString(LoginRequest.serializer(), LoginRequest(Admission.phone(phone), password)))
    }
    override suspend fun register(phone: String, password: String, code: String): SessionToken {
        require(!protectedNativeV2Enabled) { "Protected registration requires a name" }
        Admission.password(password, protectedNativeV2Enabled, registration = true); require(code.isNotBlank())
        return json(url("/auth/register"), SessionToken.serializer(), body = Wire.json.encodeToString(RegisterRequest.serializer(), RegisterRequest(Admission.phone(phone), password, code)))
    }
    override suspend fun registerNamed(phone: String, password: String, code: String, name: String): SessionToken {
        require(protectedNativeV2Enabled)
        return json(url("/auth/register"), SessionToken.serializer(), body = ProtectedAccountWire.registration(phone, password, code, name))
    }
    override suspend fun session(token: Bearer): Session {
        if (!protectedNativeV2Enabled) return json(url("/auth/session"), Session.serializer(), token)
        val response = packet(url("/auth/session"), token)
        if (response.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return try { ProtectedAccountWire.session(response.bytes) }
        catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_RESPONSE) }
    }
    override suspend fun acceptInvitation(token: Bearer, code: String) {
        require(code.isNotBlank())
        if (!json(url("/auth/invitations/accept"), Ok.serializer(), token, Wire.json.encodeToString(AcceptRequest.serializer(), AcceptRequest(code))).ok) throw ApiFailure(FailureKind.INVALID_RESPONSE)
    }
    override suspend fun logout(token: Bearer) { if (!json(url("/auth/logout"), Ok.serializer(), token, "{}").ok) throw ApiFailure(FailureKind.INVALID_RESPONSE) }
    override suspend fun gallery(token: Bearer, library: String, page: Int) = datedJson(url("/assets", library, page), Gallery.serializer(), token)
    override suspend fun gallery(token: Bearer, library: String, page: Int, media: GalleryMedia): Gallery {
        if (media == GalleryMedia.ALL) return gallery(token, library, page)
        require(mediaFilterEnabled)
        require(media != GalleryMedia.PREPARED_VIDEOS || preparedBrowseEnabled)
        return datedJson(url("/assets", library, page).newBuilder().addQueryParameter("media", media.wire).build(), Gallery.serializer(), token)
    }
    override suspend fun detail(token: Bearer, library: String, assetId: String) = datedJson(url("/assets/detail/${assetId(assetId)}", library), Detail.serializer(), token)
    override suspend fun captions(token: Bearer, library: String, assetId: String) = json(url("/assets/${assetId(assetId)}/captions", library), Captions.serializer(), token)
    override suspend fun thumbnail(token: Bearer, library: String, asset: Asset): ByteArray? {
        return cachedPreview(token, library, asset, 256)
    }
    override suspend fun detailPreview(token: Bearer, library: String, asset: Asset): ByteArray? {
        val preview = cachedPreview(token, library, asset, detailPreviewSize)
        // Only a missing cached larger derivative can fall back to a cached thumbnail.
        // Denial, TLS, size and other failures propagate; originals are never a fallback.
        return if (preview == null && detailPreviewSize != 256) thumbnail(token, library, asset) else preview
    }
    private suspend fun cachedPreview(token: Bearer, library: String, asset: Asset, size: Int): ByteArray? {
        val expected = url("/assets/${assetId(asset.id)}/thumbnail", library)
        // A response cannot turn a bearer-protected thumbnail into an arbitrary URL.
        require(asset.thumbnail_url.startsWith('/') && !asset.thumbnail_url.startsWith("//") && '\\' !in asset.thumbnail_url)
        require(origin.url.resolve(asset.thumbnail_url) == expected) { "Unexpected scoped thumbnail reference" }
        val target = if (size == 256) expected else expected.newBuilder().addQueryParameter("size", size.toString()).build()
        val packet = packet(target, token, limit = IMAGE_LIMIT, missingAllowed = true, accept = "image/*")
        if (packet.code == 404) return null
        if (packet.contentType?.substringBefore(';')?.lowercase() !in setOf("image/jpeg", "image/png", "image/webp")) throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return packet.bytes
    }
    override suspend fun displayPhoto(token: Bearer, library: String, assetId: String): ByteArray {
        require(photoDeliveryEnabled)
        val packet = packet(url("/assets/${assetId(assetId)}/display", library), token,
            limit = DISPLAY_LIMIT, accept = "image/jpeg")
        if (packet.code != 200 || packet.bytes.isEmpty() || packet.contentType?.substringBefore(';')?.trim()?.lowercase() != "image/jpeg") throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return packet.bytes
    }
    override suspend fun originalPhoto(token: Bearer, library: String, assetId: String): ByteArray {
        // Construct the protected route; never accept a URL from metadata or UI.
        val packet = packet(url("/assets/${assetId(assetId)}/media", library), token,
            limit = ORIGINAL_LIMIT, accept = "image/jpeg, image/png, image/webp")
        if (packet.code != 200 || packet.bytes.isEmpty() || packet.contentType?.substringBefore(';')?.trim()?.lowercase()
            !in setOf("image/jpeg", "image/png", "image/webp")) throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return packet.bytes
    }
    override suspend fun videoRange(token: Bearer, library: String, assetId: String, start: Long, length: Int): VideoChunk {
        require(start in 0 until VIDEO_FILE_LIMIT && length in 1..VIDEO_CHUNK_LIMIT)
        val packet = packet(url("/assets/${assetId(assetId)}/media", library), token,
            limit = length, accept = "video/mp4, video/webm", rangeStart = start)
        return VideoChunk(start, packet.total, packet.bytes)
    }
    override suspend fun preparedVideoInfo(token: Bearer, library: String, assetId: String): PreparedVideoInfo {
        require(preparedVideoEnabled && PhoneDiscoveryWire.validLibrary(library))
        val result = packet(url("/assets/${assetId(assetId)}/playback", library), token,
            accept = "video/mp4", prepared = true, head = true)
        return PreparedVideoInfo(result.total, result.etag!!)
    }
    override suspend fun preparedVideoRange(token: Bearer, library: String, assetId: String, info: PreparedVideoInfo, start: Long, length: Int): VideoChunk {
        require(preparedVideoEnabled && PhoneDiscoveryWire.validLibrary(library) && start in 0 until info.bytes && length in 1..VIDEO_CHUNK_LIMIT)
        val result = packet(url("/assets/${assetId(assetId)}/playback", library), token,
            limit = length, accept = "video/mp4", rangeStart = start, prepared = true, preparedEtag = info.etag)
        if (result.total != info.bytes) throw ApiFailure(FailureKind.HTTP, 409)
        return VideoChunk(start, result.total, result.bytes)
    }
    override suspend fun stories(token: Bearer, library: String, assetId: String, page: Int): ProtectedStoryPage {
        val result = packet(storiesUrl(library, assetId, page), token, limit = STORIES_LIMIT)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return ProtectedStoriesWire.parse(result.bytes, library, assetId, page)
    }
    private suspend fun workspacePacket(token: Bearer, library: String, path: String,
        body: String? = null, requestLimit: Int = 4096, responseLimit: Int = 256 * 1024): ByteArray {
        require(protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library))
        val result = packet(url(path, library), token, body, limit = responseLimit,
            requestLimit = requestLimit, method = if (body == null) "GET" else "POST")
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") {
            result.bytes.fill(0)
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        }
        return result.bytes
    }
    override suspend fun storyPreview(token: Bearer, library: String, json: String) =
        workspacePacket(token, library, "/story-workspace/preview", json)
    override suspend fun storyTitleCapabilities(token: Bearer, library: String) =
        workspacePacket(token, library, "/story-workspace/title-capabilities")
    override suspend fun storyTitles(token: Bearer, library: String, json: String) =
        workspacePacket(token, library, "/story-workspace/title-suggestions", json, 64 * 1024)
    override suspend fun createGroupedStory(token: Bearer, library: String, json: String) =
        workspacePacket(token, library, "/memory-stories", json, 384 * 1024)

    override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int): SavedMemoryStoryPage {
        return savedMemoryStories(token, library, page, null)
    }
    override suspend fun savedMemoryStories(token: Bearer, library: String, page: Int, theme: String?): SavedMemoryStoryPage {
        val result = packet(savedMemoryStoriesUrl(library, page, theme), token, limit = MEMORY_STORIES_LIMIT, method = "GET")
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return ProtectedMemoryStoriesWire.page(result.bytes, library, page)
    }
    override suspend fun savedMemoryStory(token: Bearer, library: String, storyId: String, revision: Long): SavedMemoryStory {
        require(protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library) && revision > 0)
        val canonicalId = storyId.also { require(runCatching { java.util.UUID.fromString(it).toString() == it }.getOrDefault(false)) }
        val target = origin.url.newBuilder().addPathSegments("memory-stories").addPathSegment(canonicalId)
            .addQueryParameter("library", library).build()
        val result = packet(target, token, limit = MEMORY_STORIES_LIMIT, method = "GET")
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return ProtectedMemoryStoriesWire.detail(result.bytes, library, canonicalId, revision)
    }
    override suspend fun savedMemoryStoryContributionReferences(
        token: Bearer, library: String, storyId: String, revision: Long, chapterIds: List<String>,
    ): SavedMemoryStoryContributionReferences {
        require(protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library) && revision > 0)
        val canonicalId = storyId.also { require(runCatching { java.util.UUID.fromString(it).toString() == it }.getOrDefault(false)) }
        require(chapterIds.size in 1..6 && chapterIds.withIndex().all { (index, id) -> id == "chapter-${index + 1}" })
        val target = origin.url.newBuilder().addPathSegments("memory-stories").addPathSegment(canonicalId)
            .addPathSegment("contribution-refs").addQueryParameter("library", library)
            .addQueryParameter("revision", revision.toString()).build()
        val result = packet(target, token, limit = 16 * 1024, method = "GET")
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return try { ProtectedMemoryStoriesWire.contributionReferences(result.bytes, library, canonicalId, revision, chapterIds) }
        finally { result.bytes.fill(0) }
    }
    override suspend fun saveMemoryStoryContributionReferences(
        token: Bearer, library: String, mutation: SavedMemoryStoryContributionReferencesMutation,
    ): SavedMemoryStory {
        require(protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library))
        val canonicalId = mutation.storyId.also { require(runCatching { java.util.UUID.fromString(it).toString() == it }.getOrDefault(false)) }
        val body = ProtectedMemoryStoriesWire.contributionReferencesMutation(mutation)
        val target = origin.url.newBuilder().addPathSegments("memory-stories").addPathSegment(canonicalId)
            .addQueryParameter("library", library).addQueryParameter("contribution_refs", "1").build()
        val result = packet(target, token, String(body, Charsets.UTF_8), limit = MEMORY_STORIES_LIMIT, requestLimit = 384 * 1024, method = "PUT")
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json") {
            body.fill(0)
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        }
        return try { ProtectedMemoryStoriesWire.detail(result.bytes, library, canonicalId, mutation.revision + 1) }
        finally { result.bytes.fill(0); body.fill(0) }
    }
    override suspend fun savedMemoryContributionDetail(
        token: Bearer, library: String, storyId: String, contributionId: String,
    ): MemoryContributionDetail {
        require(protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library))
        val canonicalStoryId = storyId.also { require(runCatching { java.util.UUID.fromString(it).toString() == it }.getOrDefault(false)) }
        val canonicalContributionId = contributionId.also { require(runCatching { java.util.UUID.fromString(it).toString() == it }.getOrDefault(false)) }
        val target = origin.url.newBuilder().addPathSegments("memory-community/v1/stories")
            .addPathSegment(canonicalStoryId).addPathSegment("contributions").addPathSegment(canonicalContributionId)
            .addQueryParameter("library", library).build()
        val result = packet(target, token, limit = MemoryCommunityResponseLimits.JSON_BYTES, method = "GET")
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return try { ProtectedMemoryCommunityWire.contributionDetail(result.bytes, canonicalStoryId, canonicalContributionId) }
        finally { result.bytes.fill(0) }
    }
    private fun storyId(id: String): String {
        require(runCatching { java.util.UUID.fromString(id).toString() == id }.getOrDefault(false))
        return id
    }
    override suspend fun saveStory(token: Bearer, library: String, mutation: StoryMutation): ProtectedStory {
        require(protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library))
        assetId(mutation.assetId)
        val body = try { ProtectedStoriesWire.mutation(mutation) } catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_INPUT) }
        val creating = mutation.storyId == null
        val path = if (creating) "/assets/${mutation.assetId}/stories" else "/stories/${storyId(mutation.storyId!!)}"
        val result = packet(url(path, library), token, body, limit = STORIES_LIMIT,
            requestLimit = 512 * 1024, method = if (creating) "POST" else "PUT")
        if (result.code != (if (creating) 201 else 200) ||
            result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return ProtectedStoriesWire.single(result.bytes, mutation.assetId, mutation.storyId)
    }
    override suspend fun currentStory(token: Bearer, library: String, assetId: String, storyId: String): ProtectedStory? {
        require(protectedNativeV2Enabled && PhoneDiscoveryWire.validLibrary(library))
        assetId(assetId)
        val result = packet(url("/stories/${storyId(storyId)}/history", library).newBuilder().addQueryParameter("page", "1").build(), token, limit = STORIES_LIMIT)
        if (result.code != 200 || result.contentType?.substringBefore(';')?.trim()?.lowercase() != "application/json")
            throw ApiFailure(FailureKind.INVALID_RESPONSE)
        return ProtectedStoriesWire.current(result.bytes, assetId, storyId)
    }
    companion object {
        const val MAX_UPLOAD_BYTES = 25 * 1024 * 1024
        const val MAX_UPLOAD_NAME = 200
        const val UPLOAD_JSON_LIMIT = 16 * 1024
        const val VIDEO_CHUNK_LIMIT = 256 * 1024
        const val VIDEO_FILE_LIMIT = 32L * 1024 * 1024 * 1024
        const val JSON_LIMIT = 524288; const val STORIES_LIMIT = 3 * 1024 * 1024; const val MEMORY_STORIES_LIMIT = 3 * 1024 * 1024; const val IMAGE_LIMIT = 1048576; const val DISPLAY_LIMIT = 12 * 1024 * 1024; const val ORIGINAL_LIMIT = 64 * 1024 * 1024 }
}
