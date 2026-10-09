package dev.photohouse.connected.core

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import java.io.IOException
import java.net.Proxy
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** HTTPS transport for the opt-in memory-community routes, rooted only at the configured origin. */
class HttpsMemoryCommunityApi internal constructor(origin: TrustedOrigin, client: OkHttpClient) : MemoryCommunityApi, MemoryBookEditorialApi, MemoryBookEditionApi, MemoryBookEditionSourceApi {
    constructor(origin: TrustedOrigin) : this(origin, OkHttpClient())

    private val origin = origin.url
    private val client = client.newBuilder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).cookieJar(CookieJar.NO_COOKIES).cache(null)
        .authenticator(Authenticator.NONE).proxyAuthenticator(Authenticator.NONE)
        .proxy(Proxy.NO_PROXY)
        .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS)).connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS).build()

    private fun target(path: String, library: String, query: Map<String, String> = emptyMap()): HttpUrl {
        require(path.startsWith('/') && !path.startsWith("//") && PhoneDiscoveryWire.validLibrary(library))
        return origin.newBuilder().encodedPath(path).addQueryParameter("library", library)
            .apply { query.forEach { (key, value) -> addQueryParameter(key, value) } }.build()
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    private suspend fun send(
        token: Bearer,
        path: String,
        library: String,
        method: String = "GET",
        json: String? = null,
        query: Map<String, String> = emptyMap(),
        audio: ByteArray? = null,
        metadata: String? = null,
        wavResponse: Boolean = false,
        jsonContentType: String = "application/json; charset=utf-8",
    ): ByteArray {
        require(method in setOf("GET", "POST", "PUT", "DELETE"))
        require(json == null || audio == null)
        val requestBytes = when {
            json != null -> json.toByteArray(Charsets.UTF_8)
            audio != null -> audio.copyOf()
            else -> null
        }
        val requestLimit = if (json != null) MemoryCommunityResponseLimits.JSON_BYTES else MemoryCommunityResponseLimits.WAV_BYTES
        if (requestBytes != null && requestBytes.size > requestLimit) {
            requestBytes.fill(0)
            throw ApiFailure(FailureKind.INVALID_INPUT)
        }
        val request = try {
            Request.Builder().url(target(path, library, query))
                .header("Authorization", token.header()).header("Accept", if (wavResponse) "audio/wav" else "application/json")
                .header("Cache-Control", "no-store").header("Accept-Encoding", "identity")
                .apply { metadata?.let { header("X-PhotoHouse-Memory-Metadata", it) } }
                .apply {
                    val body = requestBytes?.let {
                        OwnedRequestBody(it, if (json != null) jsonContentType.toMediaType() else "audio/wav".toMediaType())
                    }
                    if (body != null) method(method, body) else if (method != "GET") method(method, null)
                }.build()
        } catch (e: Exception) {
            requestBytes?.fill(0)
            throw e
        }
        return suspendCancellableCoroutine { continuation ->
            val call = client.newCall(request)
            val cleaned = AtomicBoolean(false)
            fun cleanupRequest() { if (cleaned.compareAndSet(false, true)) requestBytes?.fill(0) }
            continuation.invokeOnCancellation { call.cancel() }
            val callback = object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    try {
                        if (continuation.isActive) continuation.resumeWithException(
                            ApiFailure(if (e is SSLException) FailureKind.TLS else FailureKind.OFFLINE))
                    } finally { cleanupRequest() }
                }

                override fun onResponse(call: Call, response: Response) {
                    try {
                        val result = response.use { r ->
                            if (r.code !in 200..299) {
                                val delay = if (r.code == 429) retryAfter(r.header("Retry-After")) else 0L
                                throw ApiFailure(FailureKind.HTTP, r.code, delay)
                            }
                            val expectedType = if (wavResponse) "audio/wav" else "application/json"
                            if (r.headers.values("Content-Type").size != 1 ||
                                r.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != expectedType ||
                                r.header("Content-Encoding")?.lowercase() !in setOf(null, "identity"))
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val limit = if (wavResponse) MemoryCommunityResponseLimits.WAV_BYTES else MemoryCommunityResponseLimits.JSON_BYTES
                            val body = r.body ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (body.contentLength() > limit) throw ApiFailure(FailureKind.TOO_LARGE)
                            readBounded(body, limit, call)
                        }
                        if (continuation.isActive) continuation.resume(result) { result.fill(0) } else result.fill(0)
                    } catch (e: Exception) {
                        if (continuation.isActive) continuation.resumeWithException(e.toApiFailure())
                    } finally {
                        cleanupRequest()
                    }
                }
            }
            try { call.enqueue(callback) } catch (e: Exception) {
                cleanupRequest()
                if (continuation.isActive) continuation.resumeWithException(e.toApiFailure())
            }
        }
    }

    private class OwnedRequestBody(private val bytes: ByteArray, private val type: MediaType) : RequestBody() {
        override fun contentType() = type
        override fun contentLength() = bytes.size.toLong()
        override fun writeTo(sink: okio.BufferedSink) { sink.write(bytes) }
    }

    private class WipeableCollector(initialCapacity: Int, private val limit: Int) : AutoCloseable {
        private var buffer = ByteArray(initialCapacity.coerceIn(1, limit))
        var size: Int = 0
            private set
        fun append(source: ByteArray, length: Int) {
            if (size + length > limit) throw ApiFailure(FailureKind.TOO_LARGE)
            if (size + length > buffer.size) {
                var capacity = buffer.size
                while (capacity < size + length) capacity = minOf(limit, maxOf(capacity * 2, size + length))
                val replacement = buffer.copyOf(capacity)
                buffer.fill(0)
                buffer = replacement
            }
            source.copyInto(buffer, size, 0, length)
            size += length
        }
        fun result(): ByteArray = buffer.copyOf(size)
        override fun close() { buffer.fill(0); size = 0 }
    }

    private fun readBounded(body: ResponseBody, limit: Int, call: Call): ByteArray = body.byteStream().use { input ->
        val declared = body.contentLength()
        val out = WipeableCollector(minOf(declared.takeIf { it >= 0 }?.toInt() ?: 8192, limit), limit)
        val buffer = ByteArray(8192)
        try {
            while (true) {
                if (call.isCanceled()) throw IOException("request cancelled")
                val count = input.read(buffer)
                if (count < 0) break
                out.append(buffer, count)
            }
            if (out.size == 0) throw ApiFailure(FailureKind.INVALID_RESPONSE)
            out.result()
        } finally {
            buffer.fill(0)
            out.close()
        }
    }

    private fun retryAfter(raw: String?): Long = raw?.toLongOrNull()?.coerceIn(0, 86400)?.times(1000) ?: 0L
    private fun Exception.toApiFailure(): ApiFailure = when (this) {
        is ApiFailure -> this
        is SSLException -> ApiFailure(FailureKind.TLS)
        is IOException -> ApiFailure(FailureKind.OFFLINE)
        else -> ApiFailure(FailureKind.INVALID_RESPONSE)
    }
    private fun id(value: String): String {
        require(runCatching { java.util.UUID.fromString(value).toString() == value }.getOrDefault(false))
        return value
    }
    private fun p(story: String, suffix: String = "") = "/memory-community/v1/stories/${id(story)}/contributions$suffix"
    private fun q(page: Int) = mapOf("page" to page.toString())

    override suspend fun capabilities(token: Bearer, library: String) = send(token, "/memory-community/v1/capabilities", library)
    override suspend fun listContributions(token: Bearer, library: String, storyId: String, page: Int) =
        send(token, p(storyId), library, query = q(page))
    override suspend fun getContribution(token: Bearer, library: String, storyId: String, contributionId: String) =
        send(token, p(storyId, "/${id(contributionId)}"), library)
    override suspend fun createTextContribution(token: Bearer, library: String, storyId: String, json: String) =
        send(token, p(storyId, "/text"), library, "POST", json)
    override suspend fun createAudioContribution(token: Bearer, library: String, storyId: String, metadataBase64: String, wav: ByteArray) =
        send(token, p(storyId, "/audio"), library, "POST", audio = wav, metadata = metadataBase64)
    override suspend fun contributionAudio(token: Bearer, library: String, storyId: String, contributionId: String) =
        send(token, p(storyId, "/${id(contributionId)}/audio"), library, wavResponse = true)
    override suspend fun reviewContribution(token: Bearer, library: String, storyId: String, contributionId: String, json: String) =
        send(token, p(storyId, "/${id(contributionId)}/review"), library, "POST", json)
    override suspend fun deleteContribution(token: Bearer, library: String, storyId: String, contributionId: String) =
        send(token, p(storyId, "/${id(contributionId)}"), library, "DELETE")
    override suspend fun listBooks(token: Bearer, library: String, page: Int) =
        send(token, "/memory-community/v1/books", library, query = q(page))
    override suspend fun getBook(token: Bearer, library: String, bookId: String) =
        send(token, "/memory-community/v1/books/${id(bookId)}", library)
    override suspend fun getBookEditorial(token: Bearer, library: String, bookId: String) =
        send(token, "/memory-community/v1/books/${id(bookId)}/editorial", library)
    override suspend fun saveBookEditorial(token: Bearer, library: String, bookId: String, json: String): ByteArray {
        require(json.toByteArray(Charsets.UTF_8).size <= MemoryBookEditorialWire.MAX_BODY_BYTES)
        return send(token, "/memory-community/v1/books/${id(bookId)}/editorial", library, "PUT", json)
    }
    override suspend fun getBookEditorialSourceReferences(
        token: Bearer, library: String, storyId: String, revision: Long,
    ): SavedMemoryStoryContributionReferences {
        require(revision > 0)
        val bytes = send(token, "/memory-stories/${id(storyId)}/contribution-refs", library,
            query = mapOf("revision" to revision.toString()))
        return try { MemoryBookEditorialWire.decodeSourceCatalog(bytes, library, storyId, revision) } finally { bytes.fill(0) }
    }
    override suspend fun editionCapabilities(token: Bearer, library: String, bookId: String) =
        send(token, "/memory-community/v1/books/${id(bookId)}/edition-capabilities", library)
    override suspend fun editionProposal(token: Bearer, library: String, bookId: String, jobId: String) =
        send(token, "/memory-community/v1/books/${id(bookId)}/editions/proposals/${id(jobId)}", library)
    override suspend fun saveEdition(token: Bearer, library: String, bookId: String, json: String): ByteArray {
        require(json.toByteArray(Charsets.UTF_8).size <= MemoryBookEditionWire.MAX_REQUEST_BYTES)
        return send(token, "/memory-community/v1/books/${id(bookId)}/editions", library, "POST", json,
            jsonContentType = "application/json")
    }
    override suspend fun editionPage(token: Bearer, library: String, bookId: String, page: Int): ByteArray {
        require(page in 1..100000)
        return send(token, "/memory-community/v1/books/${id(bookId)}/editions", library, query = q(page))
    }
    override suspend fun editionDetail(token: Bearer, library: String, bookId: String, editionId: String) =
        send(token, "/memory-community/v1/books/${id(bookId)}/editions/${id(editionId)}", library)
    private fun sourcePath(bookId: String, editionId: String, sourceId: String? = null): String {
        require(sourceId == null || MemoryBookEditionSourceWire.validSourceId(sourceId))
        return "/memory-community/v1/books/${id(bookId)}/editions/${id(editionId)}/sources" +
            (sourceId?.let { "/$it" } ?: "")
    }
    override suspend fun editionSources(token: Bearer, library: String, bookId: String, editionId: String, page: Int): ByteArray {
        require(page in 1..100000)
        return send(token,sourcePath(bookId,editionId),library,query = q(page))
    }
    override suspend fun editionSource(token: Bearer, library: String, bookId: String, editionId: String, sourceId: String) =
        send(token,sourcePath(bookId,editionId,sourceId),library)
    override suspend fun editionSourceAudio(token: Bearer, library: String, bookId: String, editionId: String, sourceId: String) =
        send(token,sourcePath(bookId,editionId,sourceId) + "/audio",library,wavResponse = true)
    override suspend fun saveBook(token: Bearer, library: String, bookId: String?, json: String) =
        send(token, if (bookId == null) "/memory-community/v1/books" else "/memory-community/v1/books/${id(bookId)}",
            library, if (bookId == null) "POST" else "PUT", json)
    override suspend fun startConversation(token: Bearer, library: String, json: String) =
        send(token, "/memory-community/v1/conversations", library, "POST", json)
    override suspend fun listConversations(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
        require(targetType in setOf("story", "book"))
        return send(token, "/memory-community/v1/conversations", library,
            query = mapOf("target_type" to targetType, "target_id" to id(targetId)))
    }
    override suspend fun listConversationsWithPreview(token: Bearer, library: String, targetType: String, targetId: String): ByteArray {
        require(targetType in setOf("story", "book"))
        return send(token, "/memory-community/v1/conversations", library,
            query = mapOf("target_type" to targetType, "target_id" to id(targetId), "preview" to "1"))
    }
    override suspend fun conversationTurns(token: Bearer, library: String, conversationId: String, page: Int) =
        send(token, "/memory-community/v1/conversations/${id(conversationId)}/turns", library,
            query = mapOf("page" to page.toString(), "order" to "recent"))
    override suspend fun conversationTurnsWithReplyContext(token: Bearer, library: String, conversationId: String, page: Int) =
        send(token, "/memory-community/v1/conversations/${id(conversationId)}/turns", library,
            query = mapOf("page" to page.toString(), "order" to "recent", "reply_context" to "1"))
    override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String) =
        send(token, "/memory-community/v1/conversations/${id(conversationId)}/turns", library, "POST", json)
    override suspend fun sendTurn(token: Bearer, library: String, conversationId: String, json: String,
                                  editorialContext: Boolean) =
        send(token, "/memory-community/v1/conversations/${id(conversationId)}/turns", library, "POST", json,
            query = if (editorialContext) mapOf("editorial_context" to "1") else emptyMap())
    override suspend fun closeConversation(token: Bearer, library: String, conversationId: String) =
        send(token, "/memory-community/v1/conversations/${id(conversationId)}", library, "DELETE")
    override suspend fun queueNarrative(token: Bearer, library: String, json: String) =
        send(token, "/memory-community/v1/jobs", library, "POST", json)
    override suspend fun queueNarrative(token: Bearer, library: String, json: String,
                                        editorialContext: Boolean) =
        send(token, "/memory-community/v1/jobs", library, "POST", json,
            query = if (editorialContext) mapOf("editorial_context" to "1") else emptyMap())
    override suspend fun bookPlan(token: Bearer, library: String, bookId: String) =
        send(token, "/memory-community/v1/books/${id(bookId)}/plan", library)
    override suspend fun bookPlan(token: Bearer, library: String, bookId: String,
                                  editorialContext: Boolean) =
        send(token, "/memory-community/v1/books/${id(bookId)}/plan", library,
            query = if (editorialContext) mapOf("editorial_context" to "1") else emptyMap())
    override suspend fun getJob(token: Bearer, library: String, jobId: String) =
        send(token, "/memory-community/v1/jobs/${id(jobId)}", library)
    override suspend fun cancelJob(token: Bearer, library: String, jobId: String) =
        send(token, "/memory-community/v1/jobs/${id(jobId)}", library, "DELETE")
}
