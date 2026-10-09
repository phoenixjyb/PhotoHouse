package dev.photohouse.home

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.*
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Only the JVM test friend source set may inject a synthetic TLS client. */
class HttpsCatalogApi internal constructor(private val origin: HomeOrigin, client: OkHttpClient, override val catalogVersion: Int = 2, override val browseEnabled: Boolean = false) : HomeApi {
    constructor(origin: HomeOrigin, version: Int = 2, browseEnabled: Boolean = false) : this(origin, OkHttpClient(), version, browseEnabled)
    constructor(origin: HomeOrigin, address: HomeLanAddress, version: Int = 2, browseEnabled: Boolean = false) : this(origin, homeLanClient(origin, address), version, browseEnabled)
    init { require(catalogVersion in 2..3 && (!browseEnabled || catalogVersion == 3)) }
    private val client = client.newBuilder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).cookieJar(CookieJar.NO_COOKIES).cache(null)
        .authenticator(Authenticator.NONE).proxyAuthenticator(Authenticator.NONE)
        .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS))
        .connectTimeout(10, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS).build()

    /** Known lengths allocate once; large originals never grow and copy a second full buffer. */
    private fun readBody(body: ResponseBody, limit: Int): ByteArray {
        val length = body.contentLength()
        if (length > limit || length < 0 && limit > HomeLimits.DISPLAY_BYTES) throw HomeFailure(HomeError.UNAVAILABLE)
        return body.byteStream().use { stream ->
            if (length >= 0) {
                val data = ByteArray(length.toInt()); var offset = 0
                while (offset < data.size) {
                    val n = stream.read(data, offset, data.size - offset)
                    if (n <= 0) throw HomeFailure(HomeError.INVALID)
                    offset += n
                }
                if (stream.read() != -1) throw HomeFailure(HomeError.INVALID)
                data
            } else {
                val out = ByteArrayOutputStream(); val buffer = ByteArray(8192)
                while (true) {
                    val n = stream.read(buffer); if (n < 0) break
                    if (out.size() + n > limit) throw HomeFailure(HomeError.UNAVAILABLE)
                    out.write(buffer, 0, n)
                }
                out.toByteArray()
            }
        }
    }
    private suspend fun get(path: String, limit: Int, type: String, missing: Boolean = false, range: LongRange? = null, total: Long? = null): ByteArray? {
        require(path.startsWith("/home/v$catalogVersion/") && !path.contains('\\'))
        val url = requireNotNull(origin.url.resolve(path))
        require(url.scheme == "https" && url.host == origin.url.host && url.port == origin.url.port)
        val request = Request.Builder().url(url).header("Accept", type)
            .header("Accept-Encoding", "identity").header("Cache-Control", "no-store")
            .apply { if (range != null) header("Range", "bytes=${range.first}-${range.last}") }.build()
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
                                200 -> if (range != null) throw HomeFailure(HomeError.INVALID)
                                206 -> if (range == null) throw HomeFailure(HomeError.INVALID)
                                403 -> throw HomeFailure(HomeError.DENIED)
                                404 -> if (missing) return@use null else throw HomeFailure(HomeError.INVALID)
                                409 -> throw HomeFailure(HomeError.CHANGED)
                                429 -> throw HomeFailure(HomeError.BUSY, HttpsHomeApi.retryAfter(r.header("Retry-After")))
                                503 -> throw HomeFailure(HomeError.UNAVAILABLE)
                                else -> throw HomeFailure(HomeError.INVALID)
                            }
                            if (r.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != type ||
                                r.header("Content-Encoding")?.lowercase() !in listOf(null, "identity") ||
                                r.header("Cache-Control")?.split(',')?.none { it.trim().equals("no-store", true) } != false)
                                throw HomeFailure(HomeError.INVALID)
                            if (range != null && (r.headers.values("Content-Range") != listOf("bytes ${range.first}-${range.last}/$total") ||
                                r.headers.values("Content-Length") != listOf(limit.toString()))) throw HomeFailure(HomeError.INVALID)
                            val body = r.body ?: throw HomeFailure(HomeError.INVALID)
                            if (body.contentLength() > limit) throw HomeFailure(HomeError.INVALID)
                            val data = readBody(body, limit)
                            if (range != null && data.size != limit) throw HomeFailure(HomeError.INVALID)
                            data
                        }
                        if (continuation.isActive) continuation.resume(value)
                    } catch (_: OutOfMemoryError) {
                        if (continuation.isActive) continuation.resumeWithException(HomeFailure(HomeError.UNAVAILABLE))
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
    override suspend fun collections(): HomeCollections {
        if (catalogVersion != 3 || !browseEnabled) throw HomeFailure(HomeError.INVALID)
        val bytes = requireNotNull(get("/home/v3/collections", HomeLimits.JSON, "application/json"))
        return withContext(Dispatchers.Default) { HomeWire.collections(bytes) }
    }
    override suspend fun feed(page: Int): HomeFeed = feed(page, null)
    override suspend fun feed(page: Int, revision: Int?): HomeFeed = feed(page, revision, BrowseSelection())
    override suspend fun feed(page: Int, revision: Int?, selection: BrowseSelection): HomeFeed {
        require(browseEnabled || selection == BrowseSelection())
        require(page in 1..100000 && (revision == null || revision > 0) && (page == 1 || revision != null))
        val path = "/home/v$catalogVersion/catalog?page=$page&page_size=50" + (revision?.let { "&revision=$it" } ?: "") + if (browseEnabled) selection.query() else ""
        val bytes = requireNotNull(get(path, HomeLimits.JSON, "application/json"))
        return withContext(Dispatchers.Default) { CatalogWire.feed(bytes, page, revision, catalogVersion, if (browseEnabled) selection else null) }
    }
    override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray? {
        val p = asset.preview(variant) ?: return null
        val path = CatalogWire.previewPath(asset.id, variant, revision, catalogVersion)
        if (asset.id <= 0 || revision <= 0 || p.url != path || p.bytes !in 1..variant.bytes) throw HomeFailure(HomeError.INVALID)
        val bytes = get(path, p.bytes, "image/jpeg", missing = true) ?: return null
        return withContext(Dispatchers.Default) { if (p.onDemand) {
            if (catalogVersion != 3) throw HomeFailure(HomeError.INVALID)
            val (w, h) = HomeWire.jpegDimensions(bytes)
            if (bytes.isEmpty() || bytes.size > variant.bytes || w !in 1..variant.edge || h !in 1..variant.edge || w.toLong() * h > variant.pixels) throw HomeFailure(HomeError.INVALID)
        } else HomeWire.verifyPreview(bytes, p, variant)
        bytes }
    }
    override suspend fun original(asset: HomeAsset, revision: Int): ByteArray {
        val meta = asset.original ?: throw HomeFailure(HomeError.INVALID)
        val path = "/home/v3/assets/${asset.id}/original?revision=$revision"
        if (catalogVersion != 3 || asset.kind != AssetKind.PHOTO || asset.id <= 0 || revision <= 0 || meta.url != path || meta.bytes !in 1..CatalogWire.ORIGINAL_MAX_BYTES || meta.mime !in listOf("image/jpeg", "image/png")) throw HomeFailure(HomeError.INVALID)
        val bytes = get(path, meta.bytes, meta.mime, missing = true) ?: throw HomeFailure(HomeError.UNAVAILABLE)
        if (bytes.size != meta.bytes) throw HomeFailure(HomeError.INVALID)
        return bytes
    }
    override fun video(asset: HomeAsset, revision: Int, failed: (Exception) -> Unit): HomeVideoSource {
        val v = asset.video ?: throw HomeFailure(HomeError.INVALID)
        val path = CatalogWire.videoPath(asset.id, revision, catalogVersion)
        if (asset.kind != AssetKind.VIDEO || asset.id <= 0 || revision <= 0 || v.url != path || v.bytes !in 1..CatalogWire.VIDEO_MAX_BYTES) throw HomeFailure(HomeError.INVALID)
        return HomeVideoReader(v.bytes, CatalogWire.READ_BYTES, { start, count ->
            if (start < 0 || count !in 1..CatalogWire.READ_BYTES || start >= v.bytes || count > v.bytes - start) throw HomeFailure(HomeError.INVALID)
            readVideoRangeWithRecovery {
                get(path, count, "video/mp4", missing = true, range = start..(start + count - 1), total = v.bytes)
                    ?: throw IOException("Video unavailable")
            }
        }, failed)
    }
}
