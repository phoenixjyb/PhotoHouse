package dev.photohouse.connected.core

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okio.BufferedSink
import java.io.IOException
import java.net.Proxy
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** HTTPS adapter for private assistant history. Construction is opt-in and defaults off. */
class HttpsAssistantWorkspaceApi internal constructor(
    origin: TrustedOrigin,
    override val assistantWorkspaceEnabled: Boolean,
    client: OkHttpClient,
) : AssistantWorkspaceApi {
    constructor(origin: TrustedOrigin, assistantWorkspaceEnabled: Boolean = false) :
        this(origin, assistantWorkspaceEnabled, OkHttpClient())

    private val origin = origin.url
    private val client = client.newBuilder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).cookieJar(CookieJar.NO_COOKIES).cache(null)
        .authenticator(Authenticator.NONE).proxyAuthenticator(Authenticator.NONE).proxy(Proxy.NO_PROXY)
        .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS)).connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS).build()
    /** TTS can take up to 60 seconds; this timeout is isolated from all JSON workspace calls. */
    private val speechClient = this.client.newBuilder()
        .readTimeout(60, TimeUnit.SECONDS).callTimeout(60, TimeUnit.SECONDS).build()

    private data class Packet(val bytes: ByteArray, val assistantHeaders: Map<String, String>)

    private class WipingByteArrayOutputStream(initialSize: Int) : java.io.ByteArrayOutputStream(initialSize) {
        fun wipe() { buf.fill(0); reset() }
    }

    private fun assistantResponseHeaders(headers: Headers): Map<String, String> {
        val names = listOf("X-PhotoHouse-Tracking", "X-PhotoHouse-Request-Id", "X-PhotoHouse-Receipt-Status",
            "X-PhotoHouse-Playback-Tracking")
        return names.mapNotNull { name ->
            val values = headers.values(name)
            if (values.size > 1) throw ApiFailure(FailureKind.INVALID_RESPONSE)
            values.singleOrNull()?.let { name to it }
        }.toMap()
    }

    private inline fun <T> decoded(packet: Packet, parse: (ByteArray) -> T): T =
        try { parse(packet.bytes) } finally { packet.bytes.fill(0) }

    private fun url(path: String, library: String? = null, extraQuery: Map<String, String> = emptyMap()): HttpUrl {
        require(path.startsWith('/') && !path.startsWith("//"))
        val result = origin.newBuilder().encodedPath(path)
        library?.let {
            require(PhoneDiscoveryWire.validLibrary(it))
            result.addQueryParameter("library_id", it)
        }
        extraQuery.forEach { (name, value) -> result.addQueryParameter(name, value) }
        return result.build()
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    private suspend fun send(
        token: Bearer,
        path: String,
        library: String? = null,
        method: String = "GET",
        json: String? = null,
        successCodes: Set<Int> = setOf(200),
        extraQuery: Map<String, String> = emptyMap(),
        extraHeaders: Map<String, String> = emptyMap(),
        responseLimit: Int = AssistantWorkspaceWire.RESPONSE_LIMIT,
    ): Packet {
        if (!assistantWorkspaceEnabled) throw ApiFailure(FailureKind.INVALID_INPUT)
        require(method in setOf("GET", "POST", "PUT", "DELETE"))
        val bytes = json?.toByteArray(Charsets.UTF_8)
        if (bytes != null && bytes.size > 20 * 1024) {
            bytes.fill(0); throw ApiFailure(FailureKind.INVALID_INPUT)
        }
        val request = try {
            Request.Builder().url(url(path, library, extraQuery)).header("Authorization", token.header())
                .header("Accept", "application/json").header("Cache-Control", "no-store")
                .header("Accept-Encoding", "identity")
                .apply { extraHeaders.forEach { (name, value) -> header(name, value) } }
                .apply {
                    val body = bytes?.let(::ownedBody)
                    if (body != null) method(method, body) else if (method != "GET") method(method, null)
                }.build()
        } catch (e: Exception) {
            bytes?.fill(0)
            if (e is ApiFailure) throw e
            throw ApiFailure(FailureKind.INVALID_INPUT)
        }

        return suspendCancellableCoroutine { continuation ->
            val call = client.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    bytes?.fill(0)
                    if (continuation.isActive) continuation.resumeWithException(
                        ApiFailure(if (e is SSLException) FailureKind.TLS else FailureKind.OFFLINE))
                }

                override fun onResponse(call: Call, response: Response) {
                    try {
                        val result = response.use { r ->
                            if (r.code !in successCodes) throw ApiFailure(FailureKind.HTTP, r.code,
                                if (r.code == 429 || r.code in 502..504) retryAfterMillis(r.header("Retry-After")) else 0)
                            val noStore = r.header("Cache-Control")?.split(',')?.map { it.trim().lowercase() }?.contains("no-store") == true
                            if (r.headers.values("Content-Type").size != 1 ||
                                r.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "application/json" ||
                                r.header("Content-Encoding")?.lowercase() !in setOf(null, "identity") ||
                                !noStore)
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val body = r.body ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (body.contentLength() > responseLimit) throw ApiFailure(FailureKind.TOO_LARGE)
                            val responseBytes = readBounded(body, call, responseLimit)
                            try { Packet(responseBytes, assistantResponseHeaders(r.headers)) }
                            catch (e: Exception) { responseBytes.fill(0); throw e }
                        }
                        if (continuation.isActive) continuation.resume(result) { result.bytes.fill(0) } else result.bytes.fill(0)
                    } catch (e: Exception) {
                        if (continuation.isActive) continuation.resumeWithException(e as? ApiFailure ?: ApiFailure(FailureKind.INVALID_RESPONSE))
                    } finally { bytes?.fill(0) }
                }
            })
        }
    }

    private fun ownedBody(bytes: ByteArray): RequestBody = object : RequestBody() {
        override fun contentType() = "application/json; charset=utf-8".toMediaType()
        override fun contentLength() = bytes.size.toLong()
        override fun writeTo(sink: BufferedSink) { sink.write(bytes) }
    }

    private fun readBounded(body: ResponseBody, call: Call,
                            limit: Int = AssistantWorkspaceWire.RESPONSE_LIMIT): ByteArray = body.byteStream().use { input ->
        val out = WipingByteArrayOutputStream(minOf(body.contentLength().takeIf { it >= 0 }?.toInt() ?: 8192, limit))
        val buffer = ByteArray(8192)
        try {
            while (true) {
                if (call.isCanceled()) throw IOException("request cancelled")
                val count = input.read(buffer)
                if (count < 0) break
                if (out.size() + count > limit) throw ApiFailure(FailureKind.TOO_LARGE)
                out.write(buffer, 0, count)
            }
            if (out.size() == 0) throw ApiFailure(FailureKind.INVALID_RESPONSE)
            out.toByteArray()
        } finally { buffer.fill(0); out.wipe() }
    }

    override suspend fun capabilities(token: Bearer, library: String): AssistantWorkspaceCapabilities =
        decoded(send(token, "/assistant/workspace/v1/capabilities", library), AssistantWorkspaceWire::capabilities)

    override suspend fun listThreads(token: Bearer, library: String): AssistantWorkspaceThreadList =
        listThreads(token, library, includeLabels = false)

    override suspend fun listThreads(token: Bearer, library: String, includeLabels: Boolean): AssistantWorkspaceThreadList =
        decoded(send(token, "/assistant/workspace/v1/threads", library, extraQuery = buildMap {
            put("limit", "50")
            if (includeLabels) put("include_labels", "true")
        })) { AssistantWorkspaceWire.threadList(it, library, includeLabels) }

    override suspend fun readHistory(token: Bearer, library: String, threadId: String,
                                     beforeRevision: Long, snapshotRevision: Long): AssistantWorkspaceHistoryPage {
        if (!PhoneDiscoveryWire.validLibrary(library) || !AssistantWorkspaceWire.validUuid4(threadId) ||
            beforeRevision <= 0 || snapshotRevision < 0 || beforeRevision > snapshotRevision ||
            beforeRevision >= Long.MAX_VALUE || snapshotRevision >= Long.MAX_VALUE) {
            throw ApiFailure(FailureKind.INVALID_INPUT)
        }
        return decoded(send(token, "/assistant/workspace/v1/threads/$threadId/history", library,
            extraQuery = mapOf("before_revision" to beforeRevision.toString(),
                "snapshot_revision" to snapshotRevision.toString()))) {
            AssistantWorkspaceWire.historyPage(it, library, threadId, beforeRevision, snapshotRevision)
        }
    }

    override suspend fun createThread(token: Bearer, library: String, clientThreadId: String): AssistantWorkspaceCreatedThread {
        val body = AssistantWorkspaceWire.createThreadRequest(library, clientThreadId)
        return decoded(send(token, "/assistant/workspace/v1/threads", method = "POST", json = body,
            successCodes = setOf(200, 201))) { AssistantWorkspaceWire.createdThread(it, library, clientThreadId) }
    }

    override suspend fun readThread(token: Bearer, library: String, threadId: String): AssistantWorkspaceThreadDetail {
        require(AssistantWorkspaceWire.validUuid4(threadId))
        return decoded(send(token, "/assistant/workspace/v1/threads/$threadId", library)) {
            AssistantWorkspaceWire.threadDetail(it, library, threadId)
        }
    }

    override suspend fun deleteThread(token: Bearer, library: String, threadId: String, expectedRevision: Long): AssistantWorkspaceDeletedThread {
        require(AssistantWorkspaceWire.validUuid4(threadId))
        val body = AssistantWorkspaceWire.deleteThreadRequest(library, expectedRevision)
        return decoded(send(token, "/assistant/workspace/v1/threads/$threadId", method = "DELETE", json = body)) {
            AssistantWorkspaceWire.deletedThread(it, threadId)
        }
    }

    override suspend fun preferences(token: Bearer, library: String): AssistantWorkspacePreferences =
        decoded(send(token, "/assistant/workspace/v1/preferences", library), AssistantWorkspaceWire::preferences)

    override suspend fun updatePreferences(token: Bearer, library: String, expectedRevision: Long,
                                           updates: Map<AssistantWorkspacePreference, String?>): AssistantWorkspacePreferences {
        val body = AssistantWorkspaceWire.preferencesRequest(library, expectedRevision, updates)
        return decoded(send(token, "/assistant/workspace/v1/preferences", method = "PUT", json = body), AssistantWorkspaceWire::preferences)
    }

    override suspend fun resetPreferences(token: Bearer, library: String, expectedRevision: Long): AssistantWorkspacePreferences {
        val body = AssistantWorkspaceWire.resetPreferencesRequest(library, expectedRevision)
        return decoded(send(token, "/assistant/workspace/v1/preferences/reset", method = "POST", json = body), AssistantWorkspaceWire::preferences)
    }

    override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                    expectedRevision: Long, text: String): AssistantWorkspaceTurn {
        return submitTurn(token, library, threadId, requestId, expectedRevision, text, parentRequestId = null)
    }

    override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                    expectedRevision: Long, text: String, parentRequestId: String?): AssistantWorkspaceTurn {
        return submitTurn(token, library, threadId, requestId, expectedRevision, text, parentRequestId,
            acceptSavedMemoryCards = false)
    }

    override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                    expectedRevision: Long, text: String, parentRequestId: String?,
                                    acceptSavedMemoryCards: Boolean): AssistantWorkspaceTurn {
        require(AssistantWorkspaceWire.validUuid4(threadId))
        require(parentRequestId == null || AssistantWire.validRequestId(parentRequestId))
        val body = AssistantWorkspaceWire.turnRequest(library, requestId, expectedRevision, text, acceptSavedMemoryCards)
        val packet = send(token, "/assistant/workspace/v1/threads/$threadId/turns", method = "POST", json = body,
            extraHeaders = buildMap {
                put("X-PhotoHouse-Request-Id", requestId)
                parentRequestId?.let { put("X-PhotoHouse-Parent-Request-Id", it) }
            })
        val turn = decoded(packet) { AssistantWorkspaceWire.turn(it, library, threadId, requestId, fromGet = false,
            acceptSavedMemoryCards = acceptSavedMemoryCards) }
        val receipt = AssistantWire.requestReceipt(packet.assistantHeaders, requestId)
        return turn.copy(receipt = receipt, result = turn.result?.copy(receipt = receipt))
    }

    override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                    expectedRevision: Long, text: String, parentRequestId: String?, acceptSavedMemoryCards: Boolean,
                                    memoryParent: AssistantSavedMemoryParent?): AssistantWorkspaceTurn {
        require(AssistantWorkspaceWire.validUuid4(threadId))
        require(parentRequestId == null || AssistantWire.validRequestId(parentRequestId))
        val body = AssistantWorkspaceWire.turnRequest(library, requestId, expectedRevision, text,
            acceptSavedMemoryCards, memoryParent)
        val packet = send(token, "/assistant/workspace/v1/threads/$threadId/turns", method = "POST", json = body,
            extraHeaders = buildMap {
                put("X-PhotoHouse-Request-Id", requestId)
                parentRequestId?.let { put("X-PhotoHouse-Parent-Request-Id", it) }
            })
        val turn = decoded(packet) { AssistantWorkspaceWire.turn(it, library, threadId, requestId, fromGet = false,
            acceptSavedMemoryCards = acceptSavedMemoryCards) }
        val receipt = AssistantWire.requestReceipt(packet.assistantHeaders, requestId)
        return turn.copy(receipt = receipt, result = turn.result?.copy(receipt = receipt))
    }

    override suspend fun getTurn(token: Bearer, library: String, threadId: String, requestId: String): AssistantWorkspaceTurn {
        require(AssistantWorkspaceWire.validUuid4(threadId) && AssistantWorkspaceWire.validUuid4(requestId))
        val packet = send(token, "/assistant/workspace/v1/threads/$threadId/requests/$requestId", library)
        val turn = decoded(packet) { AssistantWorkspaceWire.turn(it, library, threadId, requestId, fromGet = true) }
        val receipt = AssistantWire.requestReceipt(packet.assistantHeaders, requestId)
        return turn.copy(receipt = receipt, result = turn.result?.copy(receipt = receipt))
    }

    override suspend fun savedMemoryReaderCapabilities(token: Bearer, library: String): SavedMemoryReaderCapabilities {
        return try {
            decoded(send(token, "/assistant/workspace/v1/saved-memory-reader-capabilities", library),
                AssistantWorkspaceWire::savedMemoryReaderCapabilities)
        } catch (failure: ApiFailure) {
            if (failure.status == 404 || failure.status == 503) SavedMemoryReaderCapabilities(1, false)
            else throw failure
        }
    }

    override suspend fun savedMemoryCardsCapabilities(token: Bearer, library: String): SavedMemoryReaderCapabilities {
        return try {
            decoded(send(token, "/assistant/workspace/v1/saved-memory-capabilities", library),
                AssistantWorkspaceWire::savedMemoryReaderCapabilities)
        } catch (failure: ApiFailure) {
            if (failure.status == 404 || failure.status == 503) SavedMemoryReaderCapabilities(1, false)
            else throw failure
        }
    }

    override suspend fun savedMemoryFollowupCapabilities(token: Bearer, library: String): SavedMemoryReaderCapabilities {
        return try {
            decoded(send(token, "/assistant/workspace/v1/saved-memory-followup-capabilities", library),
                AssistantWorkspaceWire::savedMemoryReaderCapabilities)
        } catch (failure: ApiFailure) {
            when (failure.status) {
                404, 503 -> SavedMemoryReaderCapabilities(1, false)
                403 -> {
                    // Older deployments can deny an unknown optional route. Confirm
                    // the same actor/library still has base workspace access before
                    // treating that denial as feature absence.
                    capabilities(token, library)
                    SavedMemoryReaderCapabilities(1, false)
                }
                else -> throw failure
            }
        }
    }

    override suspend fun savedMemorySpeechCapabilities(token: Bearer, library: String): SavedMemoryReaderCapabilities {
        return try {
            decoded(send(token, "/assistant/workspace/v1/saved-memory-speech-capabilities", library),
                AssistantWorkspaceWire::savedMemoryReaderCapabilities)
        } catch (failure: ApiFailure) {
            if (failure.status == 404 || failure.status == 503) SavedMemoryReaderCapabilities(1, false)
            else throw failure
        }
    }

    override suspend fun savedMemoryReadingCapabilities(token: Bearer, library: String): SavedMemoryReaderCapabilities {
        return try {
            decoded(send(token, "/assistant/workspace/v1/saved-memory-reading-capabilities", library),
                AssistantWorkspaceWire::savedMemoryReaderCapabilities)
        } catch (failure: ApiFailure) {
            when (failure.status) {
                404, 503 -> SavedMemoryReaderCapabilities(1, false)
                403 -> {
                    // Only a valid base response for the same scope proves legacy absence.
                    capabilities(token, library)
                    SavedMemoryReaderCapabilities(1, false)
                }
                else -> throw failure
            }
        }
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    override suspend fun speakSavedMemoryOpening(token: Bearer, library: String, threadId: String, turnId: String,
                                                ordinal: Int, expectedRevision: Long,
                                                speechRequestId: String): AssistantSpeechResult {
        if (!assistantWorkspaceEnabled || !AssistantWorkspaceWire.validUuid4(threadId) ||
            !AssistantWorkspaceWire.validUuid4(turnId) || ordinal !in 0..11 || expectedRevision !in 1 until Long.MAX_VALUE ||
            !AssistantWorkspaceWire.validUuid4(speechRequestId) || speechRequestId == turnId)
            throw ApiFailure(FailureKind.INVALID_INPUT)
        val bodyText = AssistantWorkspaceWire.replySpeechRequest(library, expectedRevision, turnId, speechRequestId)
        val requestBytes = bodyText.toByteArray(Charsets.UTF_8)
        val path = "/assistant/workspace/v1/threads/$threadId/requests/$turnId/memory-cards/$ordinal/speech"
        val request = try {
            Request.Builder().url(url(path)).header("Authorization", token.header()).header("Accept", "audio/wav")
                .header("Cache-Control", "no-store").header("Accept-Encoding", "identity")
                .header("X-PhotoHouse-Request-Id", speechRequestId)
                .header("X-PhotoHouse-Parent-Request-Id", turnId)
                .post(ownedBody(requestBytes)).build()
        } catch (e: Exception) {
            requestBytes.fill(0)
            if (e is ApiFailure) throw e
            throw ApiFailure(FailureKind.INVALID_INPUT)
        }
        return suspendCancellableCoroutine { continuation ->
            val call = speechClient.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    requestBytes.fill(0)
                    if (continuation.isActive) continuation.resumeWithException(
                        ApiFailure(if (e is SSLException) FailureKind.TLS else FailureKind.OFFLINE))
                }

                override fun onResponse(call: Call, response: Response) {
                    var audioBytes: ByteArray? = null
                    var transferred = false
                    try {
                        val packet = response.use { r ->
                            if (r.code != 200) throw ApiFailure(FailureKind.HTTP, r.code,
                                if (r.code == 429 || r.code in 502..504) retryAfterMillis(r.header("Retry-After")) else 0)
                            val noStore = r.headers.values("Cache-Control").singleOrNull()?.split(',')?.map { it.trim().lowercase() }
                                ?.contains("no-store") == true
                            if (r.headers.values("Content-Type").size != 1 || r.headers.values("Content-Encoding").size > 1 ||
                                r.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "audio/wav" ||
                                r.header("Content-Encoding")?.lowercase() !in setOf(null, "identity") || !noStore)
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val responseBody = r.body ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (responseBody.contentLength() > 2 * 1024 * 1024) throw ApiFailure(FailureKind.TOO_LARGE)
                            Packet(readBounded(responseBody, call, 2 * 1024 * 1024), assistantResponseHeaders(r.headers))
                        }
                        audioBytes = packet.bytes
                        val receipt = AssistantWire.speechRequestReceipt(packet.assistantHeaders, speechRequestId)
                        if (receipt.tracking != "enabled" || receipt.status != "succeeded") throw ApiFailure(FailureKind.INVALID_RESPONSE)
                        AssistantWorkspaceWire.replySpeechAudio(packet.bytes)
                        if (continuation.isActive) {
                            val audio = AssistantSpeechResult(packet.bytes, receipt)
                            transferred = true
                            continuation.resume(audio) { audio.bytes.fill(0) }
                        }
                    } catch (e: Exception) {
                        if (continuation.isActive) continuation.resumeWithException(
                            e as? ApiFailure ?: ApiFailure(FailureKind.INVALID_RESPONSE))
                    } finally {
                        if (!transferred) audioBytes?.fill(0)
                        requestBytes.fill(0)
                    }
                }
            })
        }
    }

    override suspend fun savedMemoryReader(
        token: Bearer, library: String, threadId: String, turnId: String, ordinal: Int,
        expectedRevision: Long,
    ): SavedMemoryReaderPayload {
        if (!AssistantWorkspaceWire.validUuid4(threadId) || !AssistantWorkspaceWire.validUuid4(turnId) ||
            ordinal !in 0..11 || expectedRevision !in 1 until Long.MAX_VALUE) throw ApiFailure(FailureKind.INVALID_INPUT)
        val path = "/assistant/workspace/v1/threads/$threadId/requests/$turnId/memory-cards/$ordinal"
        return decoded(send(token, path, library, extraQuery = mapOf("expected_revision" to expectedRevision.toString()),
            responseLimit = 1024 * 1024)) {
            AssistantWorkspaceWire.savedMemoryReader(it, library)
        }
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    override suspend fun speakTurn(token: Bearer, library: String, threadId: String, turnId: String,
                                   expectedRevision: Long, speechRequestId: String): AssistantSpeechResult {
        if (!assistantWorkspaceEnabled) throw ApiFailure(FailureKind.INVALID_INPUT)
        if (!AssistantWorkspaceWire.validUuid4(threadId)) throw ApiFailure(FailureKind.INVALID_INPUT)
        val bodyText = AssistantWorkspaceWire.replySpeechRequest(library, expectedRevision, turnId, speechRequestId)
        val requestBytes = bodyText.toByteArray(Charsets.UTF_8)
        val request = try {
            Request.Builder().url(url("/assistant/workspace/v1/threads/$threadId/requests/$turnId/speech"))
                .header("Authorization", token.header()).header("Accept", "audio/wav")
                .header("Cache-Control", "no-store").header("Accept-Encoding", "identity")
                .header("X-PhotoHouse-Request-Id", speechRequestId)
                .header("X-PhotoHouse-Parent-Request-Id", turnId)
                .post(ownedBody(requestBytes)).build()
        } catch (e: Exception) {
            requestBytes.fill(0)
            if (e is ApiFailure) throw e
            throw ApiFailure(FailureKind.INVALID_INPUT)
        }
        return suspendCancellableCoroutine { continuation ->
            val call = speechClient.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    requestBytes.fill(0)
                    if (continuation.isActive) continuation.resumeWithException(
                        ApiFailure(if (e is SSLException) FailureKind.TLS else FailureKind.OFFLINE))
                }

                override fun onResponse(call: Call, response: Response) {
                    var replyBytes: ByteArray? = null
                    var transferred = false
                    try {
                        val packet = response.use { r ->
                            if (r.code != 200) throw ApiFailure(FailureKind.HTTP, r.code,
                                if (r.code == 429 || r.code in 502..504) retryAfterMillis(r.header("Retry-After")) else 0)
                            val noStore = r.headers.values("Cache-Control").singleOrNull()?.split(',')?.map { it.trim().lowercase() }
                                ?.contains("no-store") == true
                            if (r.headers.values("Content-Type").size != 1 ||
                                r.headers.values("Content-Encoding").size > 1 ||
                                r.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "audio/wav" ||
                                r.header("Content-Encoding")?.lowercase() !in setOf(null, "identity") || !noStore) {
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            }
                            val responseBody = r.body ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (responseBody.contentLength() > 2 * 1024 * 1024) throw ApiFailure(FailureKind.TOO_LARGE)
                            val headers = assistantResponseHeaders(r.headers)
                            Packet(readBounded(responseBody, call, 2 * 1024 * 1024), headers)
                        }
                        replyBytes = packet.bytes
                        val receipt = AssistantWire.speechRequestReceipt(packet.assistantHeaders, speechRequestId)
                        if (receipt.tracking != "enabled" || receipt.status != "succeeded") {
                            throw ApiFailure(FailureKind.INVALID_RESPONSE)
                        }
                        AssistantWorkspaceWire.replySpeechAudio(packet.bytes)
                        if (continuation.isActive) {
                            val audio = AssistantSpeechResult(packet.bytes, receipt)
                            transferred = true
                            continuation.resume(audio) { audio.bytes.fill(0) }
                        }
                    } catch (e: Exception) {
                        if (continuation.isActive) continuation.resumeWithException(
                            e as? ApiFailure ?: ApiFailure(FailureKind.INVALID_RESPONSE))
                    } finally {
                        if (!transferred) replyBytes?.fill(0)
                        requestBytes.fill(0)
                    }
                }
            })
        }
    }
}
