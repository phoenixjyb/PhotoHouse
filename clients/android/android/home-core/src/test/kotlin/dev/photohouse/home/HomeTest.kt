package dev.photohouse.home

import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import okhttp3.*
import okhttp3.mockwebserver.*
import okhttp3.tls.*
import okio.Buffer
import org.junit.*
import org.junit.Assert.*
import java.net.InetAddress
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

internal fun resource(name: String) = requireNotNull(HomeTest::class.java.getResourceAsStream("/$name")).use { it.readBytes() }
internal fun fixture() = HomeWire.feed(resource("feed.json"), 1)
class HomeTest {
    private fun invalid(block: () -> Unit) {
        try { block(); fail("Accepted invalid input") } catch (e: HomeFailure) { assertEquals(HomeError.INVALID, e.kind) }
    }
    @Test fun frozenFeedAndBothExactJpegs() {
        val f = fixture(); assertEquals("synthetic-home", f.id); assertEquals(1, f.items.size)
        for ((v, name) in listOf(Variant.GRID to "home-8x8.jpg", Variant.DISPLAY to "home-3840x2160.jpg")) {
            HomeWire.verifyPreview(resource(name), requireNotNull(f.items.single().preview(v)), v)
        }
        assertEquals(3840 to 2160, HomeWire.jpegDimensions(resource("home-3840x2160.jpg")))
    }
    @Test fun strictJsonRejectsDuplicateUnknownWrongTypeAndDepth() {
        val s = resource("feed.json").toString(Charsets.UTF_8)
        for (bad in listOf(s.replaceFirst("{", "{\"version\":1,"), s.replaceFirst("{", "{\"extra\":1,"),
            s.replace("\"version\": 1", "\"version\": \"1\""), "[".repeat(20) + "0" + "]".repeat(20),
            s.replace("\"version\": 1", "\"version\": true"))) invalid { HomeWire.feed(bad.toByteArray(), 1) }
        invalid { HomeWire.feed(byteArrayOf(0xc3.toByte(), 0x28), 1) }
        invalid { HomeWire.feed(ByteArray(HomeLimits.JSON + 1), 1) }
    }
    @Test fun metadataCannotEscapeRevisionOrEnableOriginals() {
        val s = resource("feed.json").toString(Charsets.UTF_8)
        for (bad in listOf(s.replace("revision=1", "revision=2"), s.replace("/home/v1/assets", "https://evil.example/home/v1/assets"),
            s.replace("\"originals_allowed\": false", "\"originals_allowed\": true"), s.replace("\"width\": 3840", "\"width\": 8192"),
            s.replace("\"has_more\": false", "\"has_more\": true"), s.replace("\"total\": 1", "\"total\": 2"),
            s.replace("Synthetic TV", "x".repeat(257)))) invalid { HomeWire.feed(bad.toByteArray(), 1) }
    }
    @Test fun previewRejectsHashDimensionsMetadataAndTrailingPayload() {
        val data = resource("home-3840x2160.jpg"); val meta = requireNotNull(fixture().items.single().display)
        invalid { HomeWire.verifyPreview(data.copyOf().apply { this[500] = 0 }, meta, Variant.DISPLAY) }
        invalid { HomeWire.verifyPreview(data, meta.copy(width = 3839), Variant.DISPLAY) }
        invalid { HomeWire.verifyPreview(data, meta, Variant.GRID) }
        invalid { HomeWire.jpegDimensions(data + byteArrayOf(1)) }
        invalid { HomeWire.jpegDimensions(data.copyOf().apply { this[3] = 0xe1.toByte() }) }
    }
    @Test fun canonicalOriginRejectsCredentialsCleartextPathsAndIp() {
        assertNotNull(HomeOrigin.parse("https://home.example"))
        for (s in listOf("http://home.example", "https://home.example/", "https://home.example:443", "https://HOME.example",
            "https://127.0.0.1", "https://user:pass@home.example", "https://home.example/path", "https://home.example?x=1")) {
            try { HomeOrigin.parse(s); fail(s) } catch (_: IllegalArgumentException) { }
        }
    }
    @Test fun retryAfterSecondsDateAndOverflow() {
        assertEquals(2000, HttpsHomeApi.retryAfter("2"))
        assertEquals(10000, HttpsHomeApi.retryAfter("Thu, 01 Jan 1970 00:00:10 GMT", 0))
        assertTrue(HttpsHomeApi.retryAfter(Long.MAX_VALUE.toString()) > 60000)
        assertEquals(60000, HttpsHomeApi.retryAfter("invalid"))
    }
}
class HomeHttpTest {
    private lateinit var server: MockWebServer
    private lateinit var api: HttpsHomeApi
    @Before fun setup() {
        val cert = HeldCertificate.Builder().commonName("home.example").addSubjectAlternativeName("home.example").build()
        val tls = HandshakeCertificates.Builder().heldCertificate(cert).build()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        server = MockWebServer(); server.useHttps(tls.sslSocketFactory(), false); server.start(InetAddress.getLoopbackAddress(), 0)
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager)
            .dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress()) }).build()
        api = HttpsHomeApi(HomeOrigin.parse("https://home.example:${server.port}"), client)
    }
    @After fun close() { server.shutdown() }
    private fun response(bytes: ByteArray = resource("feed.json"), type: String = "application/json") = MockResponse()
        .setHeader("Content-Type", type).setHeader("Cache-Control", "no-store").setBody(Buffer().write(bytes))
    @Test fun exactRequestsCarryNoCredentialsAndDecode4k() = runBlocking {
        server.enqueue(response()); val f = api.feed(1)
        server.enqueue(response(resource("home-3840x2160.jpg"), "image/jpeg"))
        assertEquals(523448, api.preview(f.items.single(), Variant.DISPLAY, f.revision)!!.size)
        val feed = server.takeRequest(); val preview = server.takeRequest()
        assertEquals("/home/v1/feed?page=1&page_size=50", feed.path)
        assertEquals(f.items.single().display!!.url, preview.path)
        for (r in listOf(feed, preview)) {
            assertEquals("GET", r.method)
            for (h in listOf("Authorization", "Cookie", "Range", "If-Range")) assertNull(r.getHeader(h))
        }
    }
    @Test fun missingDisplayIsNullWithoutFallback() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(404))
        assertNull(api.preview(fixture().items.single(), Variant.DISPLAY, 1))
        assertEquals(1, server.requestCount)
    }
    @Test fun redirectsDenialRevisionAndBusyAreClassified() = runBlocking {
        for ((code, kind) in listOf(302 to HomeError.INVALID, 403 to HomeError.DENIED, 409 to HomeError.CHANGED, 429 to HomeError.BUSY, 503 to HomeError.UNAVAILABLE, 400 to HomeError.INVALID)) {
            server.enqueue(MockResponse().setResponseCode(code).setHeader("Location", "https://other.example").setHeader("Retry-After", "2"))
            try { api.feed(1); fail("$code") } catch (e: HomeFailure) { assertEquals(kind, e.kind); if (code == 429) assertEquals(2000, e.retryAfterMillis) }
        }
        assertEquals(6, server.requestCount)
    }
    @Test fun rejectsWrongTypeCachingAndChunkedOverflow() = runBlocking {
        for (r in listOf(response(type = "text/html"), response().removeHeader("Cache-Control"),
            response().setChunkedBody(" ".repeat(HomeLimits.JSON + 1), 8192))) {
            server.enqueue(r)
            try { api.feed(1); fail("invalid response") } catch (e: HomeFailure) { assertEquals(HomeError.INVALID, e.kind) }
        }
    }
    @Test fun platformTrustRejectsSyntheticCertificate() = runBlocking {
        val normal = OkHttpClient.Builder().dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress()) }).build()
        val untrusted = HttpsHomeApi(HomeOrigin.parse("https://home.example:${server.port}"), normal)
        try { untrusted.feed(1); fail("Untrusted certificate accepted") }
        catch (e: HomeFailure) { assertEquals(HomeError.TLS, e.kind) }
    }
    @Test fun changedPreviewUrlNeverSendsARequest() = runBlocking {
        val asset = fixture().items.single()
        try { api.preview(asset.copy(display = asset.display!!.copy(url = "https://evil.example/media")), Variant.DISPLAY, 1); fail("Escaped origin") }
        catch (e: HomeFailure) { assertEquals(HomeError.INVALID, e.kind) }
        assertEquals(0, server.requestCount)
    }
    @Test fun cancellationStopsDelayedRead() = runBlocking {
        server.enqueue(response().setBodyDelay(1, TimeUnit.SECONDS))
        val job = launch { api.feed(1); fail("cancelled response returned") }
        withContext(Dispatchers.IO) { server.takeRequest() }
        job.cancelAndJoin(); assertTrue(job.isCancelled)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class HomeStoreTest {
    private class Api : HomeApi {
        var result = fixture(); var error: HomeFailure? = null; var previewError: HomeFailure? = null
        var feeds = 0; var displays = 0; var missing = false
        var slow: CompletableDeferred<Unit>? = null
        var slowDisplay: CompletableDeferred<Unit>? = null
        override suspend fun feed(page: Int): HomeFeed { feeds++; slow?.let { withContext(NonCancellable) { it.await() } }; error?.let { throw it }; return result.copy(page = page) }
        override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray? {
            if (variant == Variant.DISPLAY) { displays++; slowDisplay?.let { withContext(NonCancellable) { it.await() } } }
            previewError?.let { throw it }
            return if (missing) null else resource(if (variant == Variant.GRID) "home-8x8.jpg" else "home-3840x2160.jpg")
        }
    }
    private fun TestScope.store(api: Api) = HomeStore(api, backgroundScope, { testScheduler.currentTime }, { 0.0 })
    @Test fun coldStartForegroundAndDisconnectAreAnonymousAndClear() = runTest {
        val a = Api(); val s = store(a); s.foreground(); runCurrent()
        assertEquals(1, a.feeds); assertNotNull(s.state.value.feed)
        s.openAsset(a.result.items.single()); runCurrent(); assertEquals(523448, s.state.value.display!!.size)
        s.background(); assertNull(s.state.value.feed); assertNull(s.state.value.display); assertTrue(s.state.value.covered)
        advanceTimeBy(120000); runCurrent(); assertEquals(1, a.feeds)
        s.foreground(); runCurrent(); assertEquals(2, a.feeds)
        s.disconnect(); s.background(); s.foreground(); runCurrent(); assertEquals(2, a.feeds)
        s.reconnect(); runCurrent(); assertEquals(3, a.feeds)
    }
    @Test fun staleNonCancellableFeedCannotRestoreAfterBackground() = runTest {
        val a = Api().apply { slow = CompletableDeferred() }; val s = store(a)
        s.foreground(); runCurrent(); s.background(); a.slow!!.complete(Unit); runCurrent()
        assertNull(s.state.value.feed); assertTrue(s.state.value.grids.isEmpty())
    }
    @Test fun staleDisplayCannotReturnAfterBackOrReconnect() = runTest {
        val a = Api(); val s = store(a); s.foreground(); runCurrent()
        a.slowDisplay = CompletableDeferred(); s.openAsset(a.result.items.single()); runCurrent()
        s.backToPhotos(); a.slowDisplay!!.complete(Unit); runCurrent()
        assertNull(s.state.value.display); assertNull(s.state.value.selected)
        a.slowDisplay = CompletableDeferred(); s.openAsset(a.result.items.single()); runCurrent()
        s.disconnect(); s.reconnect(); runCurrent(); a.slowDisplay!!.complete(Unit); runCurrent()
        assertNull(s.state.value.display); assertNull(s.state.value.selected)
    }
    @Test fun jitterNeverExceedsMinuteAndServerFloorSurvivesReconnect() = runTest {
        val a = Api().apply { error = HomeFailure(HomeError.BUSY, 90000) }
        val s = HomeStore(a, backgroundScope, { testScheduler.currentTime }, { 1.0 })
        s.foreground(); runCurrent(); assertEquals(90000, s.state.value.retryAtMillis)
        s.disconnect(); s.reconnect(); runCurrent(); assertEquals(1, a.feeds)
        advanceTimeBy(90000); runCurrent(); assertEquals(2, a.feeds)
        a.error = HomeFailure(HomeError.OFFLINE)
        advanceTimeBy(90000); runCurrent()
        assertTrue(s.state.value.retryAtMillis - testScheduler.currentTime in 2000..60000)
    }
    @Test fun unchangedMinuteRefreshKeepsDisplayAndChangedRevisionClears() = runTest {
        val a = Api(); val s = store(a); s.foreground(); runCurrent(); s.openAsset(a.result.items.single()); runCurrent()
        advanceTimeBy(60000); runCurrent(); assertEquals(2, a.feeds); assertNotNull(s.state.value.display)
        a.result = a.result.copy(revision = 2, items = emptyList(), total = 0)
        advanceTimeBy(60000); runCurrent(); assertNull(s.state.value.display); assertEquals(2, s.state.value.feed!!.revision)
    }
    @Test fun denialClearsAndDoesNotAutomaticallyRetry() = runTest {
        val a = Api(); val s = store(a); s.foreground(); runCurrent()
        a.error = HomeFailure(HomeError.DENIED); advanceTimeBy(60000); runCurrent()
        assertEquals(HomeError.DENIED, s.state.value.problem); assertNull(s.state.value.feed); assertTrue(s.state.value.grids.isEmpty())
        advanceTimeBy(120000); runCurrent(); assertEquals(2, a.feeds)
    }
    @Test fun revisionConflictClearsAndRefetchesWithoutBusyLoop() = runTest {
        val a = Api(); val s = store(a); s.foreground(); runCurrent()
        a.previewError = HomeFailure(HomeError.CHANGED); s.openAsset(a.result.items.single()); runCurrent()
        assertNull(s.state.value.feed); assertEquals(HomeError.CHANGED, s.state.value.problem)
        a.previewError = null; advanceTimeBy(1999); runCurrent(); assertEquals(1, a.feeds)
        advanceTimeBy(1); runCurrent(); assertEquals(2, a.feeds); assertNotNull(s.state.value.feed)
    }
    @Test fun retryScheduleUsesAllFiveDelaysAndHonorsServerFloorAcrossForeground() = runTest {
        val a = Api().apply { error = HomeFailure(HomeError.OFFLINE) }; val s = store(a); s.foreground(); runCurrent()
        var reads = 1
        for (d in listOf(2000L, 5000L, 15000L, 30000L, 60000L, 60000L)) {
            advanceTimeBy(d - 1); runCurrent(); assertEquals(reads, a.feeds)
            advanceTimeBy(1); runCurrent(); assertEquals(++reads, a.feeds)
        }
        a.error = HomeFailure(HomeError.BUSY, 120000); s.retry(); runCurrent(); reads = a.feeds
        s.background(); s.foreground(); runCurrent(); s.retry(); runCurrent(); assertEquals(reads, a.feeds)
        advanceTimeBy(119999); runCurrent(); assertEquals(reads, a.feeds)
        a.error = null; advanceTimeBy(1); runCurrent(); assertEquals(reads + 1, a.feeds)
    }
    @Test fun missingDisplayRetainsFeedWithoutAnyOriginalFallback() = runTest {
        val a = Api(); val s = store(a); s.foreground(); runCurrent(); a.missing = true
        s.openAsset(a.result.items.single()); runCurrent()
        assertTrue(s.state.value.displayMissing); assertNotNull(s.state.value.feed); assertEquals(1, a.displays)
        s.backToPhotos(); assertNull(s.state.value.selected)
    }
    @Test fun unavailableStopsMediaAndAutomaticallyRecovers() = runTest {
        val a = Api(); val s = store(a); s.foreground(); runCurrent()
        a.previewError = HomeFailure(HomeError.UNAVAILABLE); s.openAsset(a.result.items.single()); runCurrent()
        assertNull(s.state.value.display); assertTrue(s.state.value.grids.isEmpty())
        a.previewError = null; advanceTimeBy(2000); runCurrent(); assertNotNull(s.state.value.feed)
    }
}
