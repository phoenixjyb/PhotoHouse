package dev.photohouse.home

import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class HomeOrigin private constructor(internal val url: HttpUrl) {
    override fun toString() = "HomeOrigin([configured])"
    companion object {
        fun parse(raw: String): HomeOrigin {
            val u = raw.toHttpUrl()
            require(raw == "https://${u.host}" + if (u.port == 443) "" else ":${u.port}")
            require(u.host.split('.').size >= 2 && !u.host.matches(Regex("[0-9.]+")))
            require(u.host.split('.').all { it.matches(Regex("[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")) })
            require(u.scheme == "https" && u.encodedPath == "/" && u.username.isEmpty() && u.password.isEmpty() && u.query == null && u.fragment == null)
            return HomeOrigin(u)
        }
    }
}

/** Only the JVM test friend source set may inject a synthetic TLS client. */
class HttpsHomeApi internal constructor(private val origin: HomeOrigin, client: OkHttpClient) : HomeApi {
    constructor(origin: HomeOrigin) : this(origin, OkHttpClient())
    constructor(origin: HomeOrigin, address: HomeLanAddress) : this(origin, homeLanClient(origin, address))
    private val client = client.newBuilder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).cookieJar(CookieJar.NO_COOKIES).cache(null)
        .authenticator(Authenticator.NONE).proxyAuthenticator(Authenticator.NONE)
        .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS))
        .connectTimeout(10, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS).build()

    private suspend fun get(path: String, limit: Int, type: String, missing: Boolean = false): ByteArray? {
        require(path.startsWith("/home/v1/") && !path.contains('\\'))
        val url = requireNotNull(origin.url.resolve(path))
        require(url.scheme == "https" && url.host == origin.url.host && url.port == origin.url.port)
        val request = Request.Builder().url(url).header("Accept", type)
            .header("Accept-Encoding", "identity").header("Cache-Control", "no-store").build()
        return suspendCancellableCoroutine { continuation ->
            val call = client.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(HomeFailure(if (e is SSLException) HomeError.TLS else HomeError.OFFLINE))
                }
                override fun onResponse(call: Call, response: Response) {
                    try {
                        val value = response.use { r ->
                            when (r.code) {
                                200 -> Unit
                                403 -> throw HomeFailure(HomeError.DENIED)
                                404 -> if (missing) return@use null else throw HomeFailure(HomeError.INVALID)
                                409 -> throw HomeFailure(HomeError.CHANGED)
                                429 -> throw HomeFailure(HomeError.BUSY, retryAfter(r.header("Retry-After")))
                                503 -> throw HomeFailure(HomeError.UNAVAILABLE)
                                else -> throw HomeFailure(HomeError.INVALID)
                            }
                            if (r.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != type ||
                                r.header("Content-Encoding")?.lowercase() !in listOf(null, "identity") ||
                                r.header("Cache-Control")?.split(',')?.none { it.trim().equals("no-store", true) } != false)
                                throw HomeFailure(HomeError.INVALID)
                            val body = r.body ?: throw HomeFailure(HomeError.INVALID)
                            if (body.contentLength() > limit) throw HomeFailure(HomeError.INVALID)
                            val out = ByteArrayOutputStream()
                            body.byteStream().use { stream ->
                                val buffer = ByteArray(8192)
                                while (true) {
                                    val n = stream.read(buffer); if (n < 0) break
                                    if (out.size() + n > limit) throw HomeFailure(HomeError.INVALID)
                                    out.write(buffer, 0, n)
                                }
                            }
                            out.toByteArray()
                        }
                        if (continuation.isActive) continuation.resume(value)
                    } catch (e: Exception) {
                        if (continuation.isActive) continuation.resumeWithException(when (e) {
                            is HomeFailure -> e
                            is SSLException -> HomeFailure(HomeError.TLS)
                            is IOException -> HomeFailure(HomeError.OFFLINE)
                            else -> HomeFailure(HomeError.INVALID)
                        })
                    }
                }
            })
        }
    }
    override suspend fun feed(page: Int): HomeFeed {
        require(page in 1..2000)
        val bytes = requireNotNull(get("/home/v1/feed?page=$page&page_size=50", HomeLimits.JSON, "application/json"))
        return withContext(Dispatchers.Default) { HomeWire.feed(bytes, page) }
    }
    override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray? {
        val p = asset.preview(variant) ?: throw HomeFailure(HomeError.INVALID); val path = HomeWire.path(asset.id, variant, revision)
        if (p.url != path || p.bytes !in 1..variant.bytes) throw HomeFailure(HomeError.INVALID)
        val bytes = get(path, p.bytes, "image/jpeg", missing = true) ?: return null
        return withContext(Dispatchers.Default) { HomeWire.verifyPreview(bytes, p, variant); bytes }
    }
    companion object {
        internal fun retryAfter(value: String?, now: Long = System.currentTimeMillis()): Long {
            val seconds = value?.toLongOrNull()?.takeIf { it >= 0 }
            if (seconds != null) return seconds.coerceAtMost(Long.MAX_VALUE / 1000) * 1000
            return runCatching {
                (ZonedDateTime.parse(value, DateTimeFormatter.RFC_1123_DATE_TIME).toInstant().toEpochMilli() - now).coerceAtLeast(0)
            }.getOrDefault(60000)
        }
    }
}
