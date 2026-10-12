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
    ): ByteArray {
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
                            if (body.contentLength() > AssistantWorkspaceWire.RESPONSE_LIMIT) throw ApiFailure(FailureKind.TOO_LARGE)
                            readBounded(body, call)
                        }
                        if (continuation.isActive) continuation.resume(result)
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

    private fun readBounded(body: ResponseBody, call: Call): ByteArray = body.byteStream().use { input ->
        val out = java.io.ByteArrayOutputStream(minOf(body.contentLength().takeIf { it >= 0 }?.toInt() ?: 8192, AssistantWorkspaceWire.RESPONSE_LIMIT))
        val buffer = ByteArray(8192)
        try {
            while (true) {
                if (call.isCanceled()) throw IOException("request cancelled")
                val count = input.read(buffer)
                if (count < 0) break
                if (out.size() + count > AssistantWorkspaceWire.RESPONSE_LIMIT) throw ApiFailure(FailureKind.TOO_LARGE)
                out.write(buffer, 0, count)
            }
            if (out.size() == 0) throw ApiFailure(FailureKind.INVALID_RESPONSE)
            out.toByteArray()
        } finally { buffer.fill(0) }
    }

    override suspend fun capabilities(token: Bearer, library: String): AssistantWorkspaceCapabilities =
        AssistantWorkspaceWire.capabilities(send(token, "/assistant/workspace/v1/capabilities", library))

    override suspend fun listThreads(token: Bearer, library: String): AssistantWorkspaceThreadList =
        AssistantWorkspaceWire.threadList(send(token, "/assistant/workspace/v1/threads", library, extraQuery = mapOf("limit" to "50")), library)

    override suspend fun createThread(token: Bearer, library: String, clientThreadId: String): AssistantWorkspaceCreatedThread {
        val body = AssistantWorkspaceWire.createThreadRequest(library, clientThreadId)
        return AssistantWorkspaceWire.createdThread(send(token, "/assistant/workspace/v1/threads", method = "POST", json = body,
            successCodes = setOf(200, 201)), library, clientThreadId)
    }

    override suspend fun readThread(token: Bearer, library: String, threadId: String): AssistantWorkspaceThreadDetail {
        require(AssistantWorkspaceWire.validUuid4(threadId))
        return AssistantWorkspaceWire.threadDetail(send(token, "/assistant/workspace/v1/threads/$threadId", library), library, threadId)
    }

    override suspend fun deleteThread(token: Bearer, library: String, threadId: String, expectedRevision: Long): AssistantWorkspaceDeletedThread {
        require(AssistantWorkspaceWire.validUuid4(threadId))
        val body = AssistantWorkspaceWire.deleteThreadRequest(library, expectedRevision)
        return AssistantWorkspaceWire.deletedThread(send(token, "/assistant/workspace/v1/threads/$threadId", method = "DELETE", json = body), threadId)
    }

    override suspend fun preferences(token: Bearer, library: String): AssistantWorkspacePreferences =
        AssistantWorkspaceWire.preferences(send(token, "/assistant/workspace/v1/preferences", library))

    override suspend fun updatePreferences(token: Bearer, library: String, expectedRevision: Long,
                                           updates: Map<AssistantWorkspacePreference, String?>): AssistantWorkspacePreferences {
        val body = AssistantWorkspaceWire.preferencesRequest(library, expectedRevision, updates)
        return AssistantWorkspaceWire.preferences(send(token, "/assistant/workspace/v1/preferences", method = "PUT", json = body))
    }

    override suspend fun resetPreferences(token: Bearer, library: String, expectedRevision: Long): AssistantWorkspacePreferences {
        val body = AssistantWorkspaceWire.resetPreferencesRequest(library, expectedRevision)
        return AssistantWorkspaceWire.preferences(send(token, "/assistant/workspace/v1/preferences/reset", method = "POST", json = body))
    }

    override suspend fun submitTurn(token: Bearer, library: String, threadId: String, requestId: String,
                                    expectedRevision: Long, text: String): AssistantWorkspaceTurn {
        require(AssistantWorkspaceWire.validUuid4(threadId))
        val body = AssistantWorkspaceWire.turnRequest(library, requestId, expectedRevision, text)
        return AssistantWorkspaceWire.turn(send(token, "/assistant/workspace/v1/threads/$threadId/turns", method = "POST", json = body),
            library, threadId, requestId, fromGet = false)
    }

    override suspend fun getTurn(token: Bearer, library: String, threadId: String, requestId: String): AssistantWorkspaceTurn {
        require(AssistantWorkspaceWire.validUuid4(threadId) && AssistantWorkspaceWire.validUuid4(requestId))
        return AssistantWorkspaceWire.turn(send(token, "/assistant/workspace/v1/threads/$threadId/requests/$requestId", library),
            library, threadId, requestId, fromGet = true)
    }
}
