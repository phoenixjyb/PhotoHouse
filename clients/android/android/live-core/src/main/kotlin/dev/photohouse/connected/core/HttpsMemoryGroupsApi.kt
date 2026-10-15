package dev.photohouse.connected.core

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okio.BufferedSink
import java.io.IOException
import java.net.Proxy
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Protected HTTPS transport for memory groups. The feature flag is explicit and defaults off. */
class HttpsMemoryGroupsApi internal constructor(
    origin: TrustedOrigin,
    override val memoryGroupsEnabled: Boolean,
    client: OkHttpClient,
) : MemoryGroupsApi {
    constructor(origin: TrustedOrigin, memoryGroupsEnabled: Boolean = false) : this(origin, memoryGroupsEnabled, OkHttpClient())

    private val origin = origin.url
    private val client = client.newBuilder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).cookieJar(CookieJar.NO_COOKIES).cache(null)
        .authenticator(Authenticator.NONE).proxyAuthenticator(Authenticator.NONE).proxy(Proxy.NO_PROXY)
        .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS)).connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS).build()

    private fun target(path: String, library: String): HttpUrl {
        require(path.startsWith('/') && !path.startsWith("//") && PhoneDiscoveryWire.validLibrary(library))
        return origin.newBuilder().encodedPath(path).addQueryParameter("library", library).build()
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    private suspend fun send(token: Bearer, path: String, library: String, method: String = "GET", json: String? = null,
                             successCode: Int = 200): ByteArray {
        if (!memoryGroupsEnabled) throw ApiFailure(FailureKind.INVALID_INPUT)
        require(method in setOf("GET", "POST", "PUT"))
        val bytes = json?.toByteArray(Charsets.UTF_8)
        if (bytes != null && bytes.size > 24 * 1024) {
            bytes.fill(0); throw ApiFailure(FailureKind.INVALID_INPUT)
        }
        val request = try {
            Request.Builder().url(target(path, library)).header("Authorization", token.header())
                .header("Accept", "application/json").header("Cache-Control", "no-store")
                .header("Accept-Encoding", "identity")
                .apply {
                    val body = bytes?.let { ownedBody(it) }
                    if (body != null) method(method, body) else if (method != "GET") method(method, null)
                }.build()
        } catch (e: Exception) { bytes?.fill(0); throw e }

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
                            if (r.code != successCode) {
                                val delay = if (r.code == 429) retryAfter(r.header("Retry-After")) else 0L
                                throw ApiFailure(FailureKind.HTTP, r.code, delay)
                            }
                            if (r.headers.values("Content-Type").size != 1 ||
                                r.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "application/json" ||
                                r.header("Content-Encoding")?.lowercase() !in setOf(null, "identity"))
                                throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            val body = r.body ?: throw ApiFailure(FailureKind.INVALID_RESPONSE)
                            if (body.contentLength() > MemoryGroupsWire.RESPONSE_LIMIT) throw ApiFailure(FailureKind.TOO_LARGE)
                            readBounded(body, MemoryGroupsWire.RESPONSE_LIMIT, call)
                        }
                        if (continuation.isActive) continuation.resume(result)
                    } catch (e: Exception) {
                        if (continuation.isActive) continuation.resumeWithException(
                            e as? ApiFailure ?: ApiFailure(FailureKind.INVALID_RESPONSE))
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

    private fun readBounded(body: ResponseBody, limit: Int, call: Call): ByteArray = body.byteStream().use { input ->
        val out = java.io.ByteArrayOutputStream(minOf(body.contentLength().takeIf { it >= 0 }?.toInt() ?: 8192, limit))
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
        } finally { buffer.fill(0); out.toByteArray().fill(0) }
    }

    private fun retryAfter(raw: String?): Long = raw?.toLongOrNull()?.coerceIn(0, 86400)?.times(1000) ?: 0L
    private fun id(value: String): String {
        require(runCatching { java.util.UUID.fromString(value).toString() == value }.getOrDefault(false))
        return value
    }
    private fun csv(value: List<String>) = value.joinToString(",")

    override suspend fun capabilities(token: Bearer, library: String): MemoryGroupsCapabilities =
        MemoryGroupsWire.capabilities(send(token, "/memory-groups/capabilities", library))

    override suspend fun list(token: Bearer, library: String, assetId: String): MemoryGroupPage {
        require(assetId.matches(Regex("[1-9][0-9]{0,18}")) && assetId.toLongOrNull() != null)
        return MemoryGroupsWire.page(send(token, "/assets/$assetId/memory-groups", library), library, assetId)
    }

    override suspend fun proposals(token: Bearer, library: String, seedIds: List<String>, excludedIds: List<String>): MemoryGroupProposals {
        MemoryGroupsWire.validateProposalInput(seedIds, excludedIds)
        val body = buildJsonObject {
            put("asset_ids", csv(seedIds)); put("excluded_asset_ids", csv(excludedIds))
        }.toString()
        return MemoryGroupsWire.proposals(send(token, "/memory-groups/proposals", library, "POST", body), library, seedIds, excludedIds)
    }

    /** On timeout/offline, retry the same mutation value; actor-bound idempotency is enforced by the server. */
    override suspend fun save(token: Bearer, library: String, mutation: MemoryGroupMutation): MemoryGroup {
        val body = MemoryGroupsWire.mutation(mutation)
        val creating = mutation.groupId == null
        val path = if (creating) "/memory-groups" else "/memory-groups/${id(mutation.groupId!!)}"
        val bytes = send(token, path, library, if (creating) "POST" else "PUT", body, if (creating) 201 else 200)
        val group = try {
            // A successful idempotent replay can return the group's newer current revision.
            val parsed = MemoryGroupsWire.single(bytes, library)
            if (!creating) require(parsed.id == mutation.groupId)
            parsed
        } catch (e: ApiFailure) { throw e } catch (_: Exception) { throw ApiFailure(FailureKind.INVALID_RESPONSE) }
        return group
    }
}
