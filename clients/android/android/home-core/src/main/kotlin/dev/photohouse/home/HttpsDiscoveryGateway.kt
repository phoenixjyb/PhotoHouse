package dev.photohouse.home

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Same-origin discovery only. Synthetic TLS injection is restricted to the JVM friend test set. */
class HttpsDiscoveryGateway internal constructor(private val origin: HomeOrigin, client: OkHttpClient, private val discoveryVersion: Int = 1, override val calendarEnabled:Boolean = false) : DiscoveryGateway {
    constructor(origin: HomeOrigin, discoveryVersion: Int = 1, calendarEnabled:Boolean=false) : this(origin, OkHttpClient(), discoveryVersion,calendarEnabled)
    constructor(origin: HomeOrigin, address: HomeLanAddress, discoveryVersion: Int = 1, calendarEnabled:Boolean=false) : this(origin, homeLanClient(origin, address), discoveryVersion,calendarEnabled)
    init { require(discoveryVersion in 1..3 && (!calendarEnabled || discoveryVersion==3)) }
    private val mediaVersion = if (discoveryVersion >= 2) 3 else 2
    private val prefix = "/home/discovery/v$discoveryVersion/"
    private val client = client.newBuilder().followRedirects(false).followSslRedirects(false)
        .retryOnConnectionFailure(false).cookieJar(CookieJar.NO_COOKIES).cache(null)
        .authenticator(Authenticator.NONE).proxyAuthenticator(Authenticator.NONE)
        .connectionSpecs(listOf(ConnectionSpec.MODERN_TLS))
        .connectTimeout(10, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS).build()
    private val media = HttpsCatalogApi(origin, this.client, catalogVersion = mediaVersion)

    private suspend fun json(path: String, body: ByteArray? = null): ByteArray {
        if (!path.startsWith(prefix) || path.contains('\\')) throw HomeFailure(HomeError.INVALID)
        val url = origin.url.resolve(path) ?: throw HomeFailure(HomeError.INVALID)
        if (url.scheme != "https" || url.host != origin.url.host || url.port != origin.url.port) throw HomeFailure(HomeError.INVALID)
        val request = Request.Builder().url(url).header("Accept", "application/json")
            .header("Accept-Encoding", "identity").header("Cache-Control", "no-store")
            .apply { if (body != null) post(body.toRequestBody("application/json".toMediaType())) }.build()
        return suspendCancellableCoroutine { continuation ->
            val call = client.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(HomeFailure(if (e is SSLException) HomeError.TLS else HomeError.OFFLINE))
                }
                override fun onResponse(call: Call, response: Response) {
                    try {
                        val bytes = response.use { r ->
                            when (r.code) {
                                200 -> Unit
                                403 -> throw HomeFailure(HomeError.DENIED)
                                409 -> throw HomeFailure(HomeError.CHANGED)
                                429 -> throw HomeFailure(HomeError.BUSY, HttpsHomeApi.retryAfter(r.header("Retry-After")))
                                503 -> throw HomeFailure(HomeError.UNAVAILABLE)
                                else -> throw HomeFailure(HomeError.INVALID)
                            }
                            if (r.headers.values("Content-Type").size != 1 ||
                                r.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase() != "application/json" ||
                                r.headers.values("Content-Encoding").let { it.isNotEmpty() && (it.size != 1 || !it.single().equals("identity", true)) } ||
                                r.headers.values("Cache-Control").flatMap { it.split(',') }.none { it.trim().equals("no-store", true) })
                                throw HomeFailure(HomeError.INVALID)
                            val responseBody = r.body ?: throw HomeFailure(HomeError.INVALID)
                            if (responseBody.contentLength() > HomeLimits.JSON) throw HomeFailure(HomeError.INVALID)
                            val out = ByteArrayOutputStream()
                            responseBody.byteStream().use { stream ->
                                val buffer = ByteArray(8192)
                                while (true) {
                                    val count = stream.read(buffer); if (count < 0) break
                                    if (out.size() + count > HomeLimits.JSON) throw HomeFailure(HomeError.INVALID)
                                    out.write(buffer, 0, count)
                                }
                            }
                            out.toByteArray()
                        }
                        if (continuation.isActive) continuation.resume(bytes)
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
    override suspend fun calendar(snapshot:DiscoverySnapshot,request:CalendarRequest):CalendarPage {
        if(!calendarEnabled || !request.valid() || DiscoveryField.DATES !in snapshot.options.fields) throw HomeFailure(HomeError.INVALID)
        val path="${prefix}calendar?revision=${snapshot.revision}&page=${request.page}&page_size=12"+(request.year?.let { "&year=$it" } ?: "")+(request.month?.let { "&month=$it" } ?: "")
        val bytes=json(path)
        return withContext(Dispatchers.Default) { CalendarWire.parse(bytes,snapshot,request) }
    }
    override fun calendarCovers(snapshot:DiscoverySnapshot,page:CalendarPage):HomeApi = object:HomeApi {
        override val catalogVersion=3
        override val retryRevisionChanges=false
        override suspend fun feed(pageNumber:Int):HomeFeed {
            if(pageNumber!=1) throw HomeFailure(HomeError.INVALID)
            val covers=page.buckets.mapNotNull { it.cover }
            return HomeFeed(snapshot.catalogRevision,snapshot.libraryId,snapshot.libraryTitle,1,50,covers.size,false,covers,3)
        }
        override suspend fun preview(asset:HomeAsset,variant:Variant,revision:Int):ByteArray? {
            if(variant!=Variant.GRID || revision!=snapshot.catalogRevision || asset !in page.buckets.mapNotNull { it.cover }) throw HomeFailure(HomeError.INVALID)
            return media.preview(asset,variant,revision)
        }
    }
    private suspend fun facet(field: DiscoveryField, page: Int, revision: Int?, query: String = ""): DiscoveryWire.Facets {
        if (page !in 1..5000 || revision != null && revision <= 0 || page > 1 && revision == null) throw HomeFailure(HomeError.INVALID)
        val path = "${prefix}facets?facet=${DiscoveryWire.facetName(field)}&page=$page&page_size=50" + (revision?.let { "&revision=$it" } ?: "")
        val requestPath = if (discoveryVersion == 3) {
            origin.url.resolve(path)!!.newBuilder().addQueryParameter("q",query).build().let { it.encodedPath + "?" + it.encodedQuery }
        } else path
        val bytes = json(requestPath)
        return withContext(Dispatchers.Default) { DiscoveryWire.facets(bytes, field, page, version = discoveryVersion, query = query).also {
            if (revision != null && it.snapshot.revision != revision) throw HomeFailure(HomeError.INVALID)
        } }
    }
    override suspend fun load(): DiscoverySnapshot {
        var snapshot: DiscoverySnapshot? = null
        for (field in listOf(DiscoveryField.PEOPLE, DiscoveryField.TAGS, DiscoveryField.PLACES)) {
            val response = facet(field, 1, snapshot?.revision)
            snapshot = DiscoveryWire.merge(snapshot, response)
        }
        return requireNotNull(snapshot)
    }
    override suspend fun more(snapshot: DiscoverySnapshot, field: DiscoveryField): DiscoverySnapshot {
        val page = snapshot.nextPages[field] ?: throw HomeFailure(HomeError.INVALID)
        if (snapshot.binding == null || page <= 1 || field !in snapshot.facetTotals) throw HomeFailure(HomeError.INVALID)
        return DiscoveryWire.merge(snapshot, facet(field, page, snapshot.revision, if (field == DiscoveryField.TAGS) snapshot.tagQuery.orEmpty() else ""))
    }
    override suspend fun findTags(snapshot: DiscoverySnapshot, query: String, selected: Set<String>): DiscoverySnapshot {
        if (discoveryVersion != 3 || query != query.trim() || query.toByteArray(Charsets.UTF_8).size > 128 || query.any { it < ' ' } || selected.size > 20 || !snapshot.options.tags.map { it.id }.containsAll(selected)) throw HomeFailure(HomeError.INVALID)
        val base=snapshot.copy(options=snapshot.options.copy(tags=snapshot.options.tags.filter { it.id in selected }),
            nextPages=snapshot.nextPages - DiscoveryField.TAGS, facetTotals=snapshot.facetTotals - DiscoveryField.TAGS,
            facetLastIds=snapshot.facetLastIds - DiscoveryField.TAGS, tagQuery=query, tagMatches=emptySet())
        return DiscoveryWire.merge(base,facet(DiscoveryField.TAGS,1,snapshot.revision,query))
    }
    override fun results(snapshot: DiscoverySnapshot, draft: DiscoveryDraft): HomeApi {
        // Validate before constructing a result store, and copy the exact immutable request selection.
        val normalized = draft.normalized().copy(people = draft.people.toSet(), tags = draft.tags.toSet(),
            themes = draft.themes.toSet(), topics = draft.topics.toSet())
        DiscoveryWire.request(snapshot, normalized, 1)
        return object : HomeApi {
            override val catalogVersion = mediaVersion
            override val retryRevisionChanges = false
            private val lock = Mutex()
            private var fingerprint: String? = null
            private var total: Int? = null
            override suspend fun feed(page: Int): HomeFeed = feed(page, null)
            override suspend fun feed(page: Int, revision: Int?): HomeFeed = lock.withLock {
                if (revision != null && revision != snapshot.catalogRevision || page > 1 && (revision == null || fingerprint == null)) throw HomeFailure(HomeError.INVALID)
                val request = DiscoveryWire.request(snapshot, normalized, page)
                val bytes = json("${prefix}search", request)
                val parsed = withContext(Dispatchers.Default) { DiscoveryWire.search(bytes, snapshot, page, fingerprint, total, version = discoveryVersion) }
                fingerprint = parsed.fingerprint; total = parsed.feed.total
                parsed.feed
            }
            override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray? {
                if (revision != snapshot.catalogRevision) throw HomeFailure(HomeError.INVALID)
                return media.preview(asset, variant, revision)
            }
            override suspend fun original(asset: HomeAsset, revision: Int): ByteArray {
                if (revision != snapshot.catalogRevision || mediaVersion != 3) throw HomeFailure(HomeError.INVALID)
                return media.original(asset, revision)
            }
            override fun video(asset: HomeAsset, revision: Int, failed: (Exception) -> Unit): HomeVideoSource {
                if (revision != snapshot.catalogRevision) throw HomeFailure(HomeError.INVALID)
                return media.video(asset, revision, failed)
            }
        }
    }
}
