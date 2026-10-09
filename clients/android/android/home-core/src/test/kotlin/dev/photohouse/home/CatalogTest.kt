package dev.photohouse.home

import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import kotlinx.serialization.json.*
import okhttp3.*
import okhttp3.mockwebserver.*
import okhttp3.tls.*
import okio.Buffer
import org.junit.*
import org.junit.Assert.*
import java.net.InetAddress
import java.io.IOException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

private fun catalogResource(name: String) = requireNotNull(CatalogWireTest::class.java.classLoader.getResourceAsStream(name)).use { it.readBytes() }
private fun catalogFixture() = CatalogWire.feed(catalogResource("catalog-v2.json"), 1)
class CatalogWireTest {
    @Test fun exactBackendFixturePreservesKindsAvailabilityAndVideoMetadata() {
        val f = catalogFixture()
        assertEquals(2, f.version); assertEquals(listOf(102, 101), f.items.map { it.id })
        assertEquals(AssetKind.VIDEO, f.items[0].kind); assertNull(f.items[0].grid)
        assertEquals(MediaUnavailable.NOT_PREPARED, f.items[0].gridUnavailable)
        assertEquals(24336L, f.items[0].video!!.bytes)
        HomeWire.verifyPreview(catalogResource("home-8x8.jpg"), requireNotNull(f.items[1].display), Variant.DISPLAY)
    }
    @Test fun rejectsMalformedUnknownDuplicateAndInvalidUtf8Json() {
        val s = catalogResource("catalog-v2.json").toString(Charsets.UTF_8)
        for (bytes in listOf(byteArrayOf(0xc3.toByte(), 0x28), (s + "{}").toByteArray(),
            s.replace("\"version\": 2", "\"version\": 2, \"version\": 2").toByteArray(),
            s.replace("\"version\": 2", "\"version\": 2, \"extra\": 1").toByteArray(),
            s.replace("Synthetic video", "\\ud800").toByteArray(), ByteArray(HomeLimits.JSON + 1))) {
            assertThrows(HomeFailure::class.java) { CatalogWire.feed(bytes, 1) }
        }
    }
    @Test fun rejectsPathEscapesProfilesBoundsAndUnavailableUrls() {
        val s = catalogResource("catalog-v2.json").toString(Charsets.UTF_8)
        for (bad in listOf(s.replace("/home/v2/assets", "https://other.example/home/v2/assets"),
            s.replace("revision=1", "revision=2"), s.replace("\"h264\"", "\"hevc\""),
            s.replace("\"bytes\": 24336", "\"bytes\": 34359738369"),
            s.replace("\"width\": 320", "\"width\": 8192"),
            s.replace("\"originals_allowed\": false", "\"originals_allowed\": true"),
            s.replace("\"reason\": \"not_prepared\"", "\"reason\": \"not_prepared\", \"url\": \"/media\""),
            s.replace("Synthetic video", "照".repeat(86)), s.replace("\"kind\": \"video\"", "\"kind\": \"photo\""))) {
            assertThrows(HomeFailure::class.java) { CatalogWire.feed(bad.toByteArray(), 1) }
        }
    }
    @Test fun revisionPageOrderingAndCountMustMatch() {
        val bytes = catalogResource("catalog-v2.json"); val s = bytes.toString(Charsets.UTF_8)
        assertThrows(HomeFailure::class.java) { CatalogWire.feed(bytes, 2) }
        assertThrows(HomeFailure::class.java) { CatalogWire.feed(bytes, 1, 2) }
        for (bad in listOf(s.replace("\"total\": 2", "\"total\": 100001"),
            s.replace("\"total\": 2", "\"total\": 3"), s.replace("\"has_more\": false", "\"has_more\": true"),
            s.replace("102", "100"), s.replace("\"page_size\": 50", "\"page_size\": 100"))) {
            assertThrows(HomeFailure::class.java) { CatalogWire.feed(bad.toByteArray(), 1) }
        }
    }
    @Test fun fullHundredThousandAssetCatalogCanReachMiddleAndLastPages() {
        val raw = Json.parseToJsonElement(catalogResource("catalog-v2.json").toString(Charsets.UTF_8)).jsonObject
        val photo = raw.getValue("items").jsonArray[1].jsonObject
        for (page in listOf(1, 558, 2000)) {
            val items = JsonArray((0 until 50).map { offset ->
                val id = 100000 - (page - 1) * 50 - offset
                val previews = JsonObject(photo.getValue("previews").jsonObject.mapValues { (variant, value) ->
                    JsonObject(value.jsonObject + ("url" to JsonPrimitive("/home/v2/assets/$id/preview?variant=$variant&revision=7")))
                })
                JsonObject(photo + mapOf("id" to JsonPrimitive(id), "previews" to previews))
            })
            val body = JsonObject(raw + mapOf("revision" to JsonPrimitive(7), "page" to JsonPrimitive(page),
                "total" to JsonPrimitive(100000), "has_more" to JsonPrimitive(page < 2000), "items" to items))
            val f = CatalogWire.feed(body.toString().toByteArray(), page, if (page == 1) null else 7)
            assertEquals(100000, f.total); assertEquals(50, f.items.size)
            assertEquals(page < 2000, f.hasMore)
            if (page == 2000) assertEquals(1, f.items.last().id)
        }
    }
    @Test fun explicitlyUnavailableVideoDoesNotInventAUrl() {
        val raw = Json.parseToJsonElement(catalogResource("catalog-v2.json").toString(Charsets.UTF_8)).jsonObject
        val item = raw.getValue("items").jsonArray[0].jsonObject
        val missing = buildJsonObject { put("state", "unavailable"); put("reason", "unsupported") }
        val items = JsonArray(listOf(JsonObject(item + ("video" to missing)), raw.getValue("items").jsonArray[1]))
        val parsed = CatalogWire.feed(JsonObject(raw + ("items" to items)).toString().toByteArray(), 1)
        assertNull(parsed.items[0].video); assertEquals(MediaUnavailable.UNSUPPORTED, parsed.items[0].videoUnavailable)
    }
}

class CatalogHttpTest {
    private lateinit var server: MockWebServer
    private lateinit var api: HttpsCatalogApi
    @Before fun setup() {
        val cert = HeldCertificate.Builder().commonName("home.example").addSubjectAlternativeName("home.example").build()
        val tls = HandshakeCertificates.Builder().heldCertificate(cert).build()
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(cert.certificate).build()
        server = MockWebServer(); server.useHttps(tls.sslSocketFactory(), false); server.start(InetAddress.getLoopbackAddress(), 0)
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager)
            .dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress()) }).build()
        api = HttpsCatalogApi(HomeOrigin.parse("https://home.example:${server.port}"), client)
    }
    @After fun close() { server.shutdown() }
    private fun response(bytes: ByteArray, type: String) = MockResponse().setHeader("Content-Type", type).setHeader("Cache-Control", "no-store").setBody(Buffer().write(bytes))
    private fun range(bytes: ByteArray = ByteArray(24324) { (it % 251).toByte() }) = response(bytes, "video/mp4").setResponseCode(206).setHeader("Content-Range", "bytes 12-24335/24336")
    @Test fun exactCatalogPreviewAndVideoRequestsHaveNoCredentialsOrFallback() = runBlocking {
        server.enqueue(response(catalogResource("catalog-v2.json"), "application/json")); val feed = api.feed(1)
        assertNull(api.preview(feed.items[0], Variant.GRID, 1)); assertEquals(1, server.requestCount)
        server.enqueue(response(catalogResource("home-8x8.jpg"), "image/jpeg"))
        assertEquals(632, api.preview(feed.items[1], Variant.DISPLAY, 1)!!.size)
        val bytes = catalogResource("catalog-video.mp4").copyOfRange(12, 24336)
        server.enqueue(range(bytes))
        val reader = api.video(feed.items[0], 1) { fail("Unexpected transport error") }
        val buffer = ByteArray(4); assertEquals(4, reader.readAt(12, buffer, 0, 4)); assertArrayEquals(bytes.copyOfRange(0, 4), buffer)
        repeat(20) { position ->
            assertEquals(4, reader.readAt(12L + position, buffer, 0, 4))
            assertArrayEquals(bytes.copyOfRange(position, position + 4), buffer)
        }
        reader.close()
        val requests = (1..3).map { server.takeRequest() }
        assertEquals("/home/v2/catalog?page=1&page_size=50", requests[0].path)
        assertEquals("/home/v2/assets/101/preview?variant=display&revision=1", requests[1].path)
        assertEquals("/home/v2/assets/102/video?revision=1", requests[2].path)
        assertEquals("bytes=12-24335", requests[2].getHeader("Range"))
        for (r in requests) for (h in listOf("Authorization", "Cookie", "If-Range")) assertNull(r.getHeader(h))
    }
    @Test fun laterPageIncludesRevisionAndDoesNotFallBackToV1() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(409))
        try { api.feed(2, 7); fail("Expected change") } catch (e: HomeFailure) { assertEquals(HomeError.CHANGED, e.kind) }
        assertEquals("/home/v2/catalog?page=2&page_size=50&revision=7", server.takeRequest().path)
        assertEquals(1, server.requestCount)
    }
    @Test fun invalidPartialResponsesCloseReaderBeforeReturningBytes() {
        for (r in listOf(range().setResponseCode(200), range().setHeader("Content-Range", "bytes 11-14/24336"),
            range().setHeader("Content-Range", "bytes 12-15/24337"), range().addHeader("Content-Range", "bytes 12-15/24336"),
            range(byteArrayOf(1, 2, 3)), range().setHeader("Content-Type", "text/html"), range().removeHeader("Cache-Control"),
            range().setHeader("Content-Encoding", "gzip"), range().setResponseCode(416))) {
            server.enqueue(r)
            var error: Exception? = null
            val source = api.video(catalogFixture().items[0], 1) { error = it }
            val buffer = ByteArray(4) { 99 }
            assertThrows(IOException::class.java) { source.readAt(12, buffer, 0, 4) }
            assertEquals(HomeError.INVALID, (error as HomeFailure).kind)
            assertArrayEquals(ByteArray(4) { 99 }, buffer)
        }
    }
    @Test fun videoDenialRevisionBusyAndUnavailableArePropagated() {
        for ((code, kind) in listOf(403 to HomeError.DENIED, 409 to HomeError.CHANGED, 429 to HomeError.BUSY, 503 to HomeError.UNAVAILABLE, 302 to HomeError.INVALID)) {
            server.enqueue(MockResponse().setResponseCode(code).setHeader("Retry-After", "2").setHeader("Location", "https://other.example"))
            var failure: Exception? = null
            val source = api.video(catalogFixture().items[0], 1) { failure = it }
            assertThrows(IOException::class.java) { source.readAt(0, ByteArray(4), 0, 4) }
            assertEquals(kind, (failure as HomeFailure).kind)
            if (code == 429) assertEquals(2000L, (failure as HomeFailure).retryAfterMillis)
        }
    }
    @Test fun closingReaderCancelsAnActualHttpsRangeRequest() {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
        val source = api.video(catalogFixture().items[0], 1) { fail("Cancelled read reported an error") }
        val worker = Executors.newSingleThreadExecutor()
        try {
            val result = worker.submit<Boolean> { try { source.readAt(0, ByteArray(4), 0, 4); false } catch (_: IOException) { true } }
            assertNotNull(server.takeRequest(5, TimeUnit.SECONDS)); source.close()
            assertTrue(result.get(3, TimeUnit.SECONDS))
        } finally { source.close(); worker.shutdownNow() }
    }
    @Test fun untrustedTlsCertificateCannotReachCatalogBytes() = runBlocking {
        val client = OkHttpClient.Builder().dns(object : Dns {
            override fun lookup(hostname: String) = listOf(InetAddress.getLoopbackAddress())
        }).build()
        val untrusted = HttpsCatalogApi(HomeOrigin.parse("https://home.example:${server.port}"), client)
        try { untrusted.feed(1); fail("Untrusted TLS accepted") }
        catch (e: HomeFailure) { assertEquals(HomeError.TLS, e.kind) }
    }
    @Test fun interruptedHttpsRangeRecoversSameBytesWithoutClosingPlayerSource() {
        val bytes = catalogResource("catalog-video.mp4").copyOfRange(12, 24336)
        server.enqueue(range(bytes).setSocketPolicy(SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY))
        server.enqueue(range(bytes))
        var failures = 0
        val source = api.video(catalogFixture().items[0], 1) { failures++ }
        source.use {
            val buffer = ByteArray(4) { 99 }
            assertEquals(4, it.readAt(12, buffer, 0, 4))
            assertArrayEquals(bytes.copyOfRange(0, 4), buffer)
            assertEquals(0, failures)
            assertEquals(24336L, it.size())
            assertEquals(4, it.readAt(16, buffer, 0, 4)) // recovered window is reusable
            assertArrayEquals(bytes.copyOfRange(4, 8), buffer)
            assertEquals(2, server.requestCount)
            val first = server.takeRequest(); val retry = server.takeRequest()
            assertEquals(first.path, retry.path)
            assertEquals("bytes=12-24335", retry.getHeader("Range"))
            assertEquals(first.getHeader("Range"), retry.getHeader("Range"))
            assertNull(retry.getHeader("Authorization")); assertNull(retry.getHeader("Cookie"))
        }
    }
    @Test fun truncatedHttpsRangeCannotReturnPartOfTheRequestedBuffer() {
        val before = server.requestCount
        repeat(3) { server.enqueue(range().setSocketPolicy(SocketPolicy.DISCONNECT_DURING_RESPONSE_BODY)) }
        var failure: Exception? = null
        val source = api.video(catalogFixture().items[0], 1) { failure = it }
        val buffer = ByteArray(4) { 99 }
        assertThrows(IOException::class.java) { source.readAt(12, buffer, 0, 4) }
        assertEquals(HomeError.OFFLINE, (failure as HomeFailure).kind)
        assertEquals(3, server.requestCount - before)
        assertArrayEquals(ByteArray(4) { 99 }, buffer)
    }
    @Test fun unavailableAndChangedUrlsNeverRequestUnapprovedMedia() = runBlocking {
        val asset = catalogFixture().items[0]
        assertNull(api.preview(asset, Variant.DISPLAY, 1))
        assertThrows(HomeFailure::class.java) { api.video(asset.copy(video = asset.video!!.copy(url = "https://other.example/movie")), 1) {} }
        server.enqueue(MockResponse().setResponseCode(404))
        var failure: Exception? = null
        val source = api.video(asset, 1) { failure = it }
        assertThrows(IOException::class.java) { source.readAt(0, ByteArray(4), 0, 4) }
        assertTrue(failure is IOException); assertEquals(1, server.requestCount)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class CatalogStoreTest {
    private class Api(private val poster: Boolean = false) : HomeApi {
        override val catalogVersion = 2
        val calls = mutableListOf<Pair<Int, Int?>>()
        var error: HomeFailure? = null
        var callback: ((Exception) -> Unit)? = null
        val sources = mutableListOf<HomeVideoReader>()
        var displayGate: CompletableDeferred<Unit>? = null
        override suspend fun feed(page: Int): HomeFeed = error("Revision-aware method required")
        override suspend fun feed(page: Int, revision: Int?): HomeFeed {
            calls += page to revision; error?.let { throw it }
            val fixture = catalogFixture()
            return fixture.copy(page = page, total = 51, hasMore = page == 1,
                items = if (poster) fixture.items.map { if (it.kind == AssetKind.VIDEO) it.copy(display = fixture.items[1].display) else it } else fixture.items)
        }
        override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray {
            if (variant == Variant.DISPLAY) displayGate?.await()
            return catalogResource("home-8x8.jpg")
        }
        override fun video(asset: HomeAsset, revision: Int, failed: (Exception) -> Unit): HomeVideoSource {
            callback = failed
            return HomeVideoReader(4, 4, { _, n -> ByteArray(n) }, failed).also { sources += it }
        }
    }
    @Test fun adjacentMediaSkipsUnavailableCatalogEntriesInBothDirections() {
        val feed = catalogFixture()
        val video = feed.items[0]; val photo = feed.items[1]
        val unavailable = photo.copy(id = 999, display = null)
        val mixed = feed.copy(items = listOf(video, unavailable, photo))
        assertEquals(photo, HomeState(feed = mixed, selected = video.id).adjacentAsset(1))
        assertEquals(video, HomeState(feed = mixed, selected = photo.id).adjacentAsset(-1))
        assertNull(HomeState(feed = mixed, selected = photo.id).adjacentAsset(1))
        assertNull(HomeState(feed = mixed, selected = video.id).adjacentAsset(-1))
    }
    @Test fun directVideoOpenWaitsForSelectionAndCannotReopenAfterBackOrBackground() = runTest {
        val a = Api(poster = true); val s = HomeStore(a, backgroundScope)
        s.foreground(); runCurrent()
        val asset = s.state.value.feed!!.items[0]
        a.displayGate = CompletableDeferred()
        s.openAsset(asset, openPlayer = true); runCurrent()
        assertTrue(a.sources.isEmpty())
        s.backToPhotos(); a.displayGate!!.complete(Unit); runCurrent()
        assertTrue(a.sources.isEmpty()); assertNull(s.state.value.selected)
        a.displayGate = CompletableDeferred()
        s.openAsset(asset, openPlayer = true); runCurrent()
        s.background(); a.displayGate!!.complete(Unit); runCurrent()
        assertTrue(a.sources.isEmpty()); assertTrue(s.state.value.covered)
        s.foreground(); runCurrent()
        s.openAsset(s.state.value.feed!!.items[0], openPlayer = true); runCurrent()
        assertNotNull(s.state.value.video)
        s.backToPhotos(); assertTrue(a.sources.single().isClosed)
    }
    @Test fun pagingPinsRevisionAndForegroundStartsAgainAtPageOne() = runTest {
        val a = Api(); val s = HomeStore(a, backgroundScope, { testScheduler.currentTime }, { 0.0 })
        s.foreground(); runCurrent(); s.loadPage(2); runCurrent()
        assertEquals(listOf(1 to null, 2 to 1), a.calls)
        s.background(); s.foreground(); runCurrent()
        assertEquals(1 to null, a.calls.last())
    }
    @Test fun revisionOrDenialStopsVideoAndClearsAllOldMedia() = runTest {
        for (kind in listOf(HomeError.CHANGED, HomeError.DENIED)) {
            val a = Api(); val s = HomeStore(a, backgroundScope, { testScheduler.currentTime }, { 0.0 })
            s.foreground(); runCurrent(); s.loadPage(2); runCurrent()
            s.openAsset(s.state.value.feed!!.items[0]); runCurrent(); s.openVideo(); runCurrent()
            val source = a.sources.single(); assertNotNull(s.state.value.video)
            a.callback!!(HomeFailure(kind)); runCurrent()
            assertTrue(source.isClosed); assertNull(s.state.value.feed); assertNull(s.state.value.video)
            assertTrue(s.state.value.grids.isEmpty())
            if (kind == HomeError.CHANGED) { advanceTimeBy(2001); runCurrent(); assertEquals(1 to null, a.calls.last()) }
            s.background()
        }
    }
    @Test fun staleVideoCallbackCannotCloseAReopenedVideo() = runTest {
        val a = Api(); val s = HomeStore(a, backgroundScope)
        s.foreground(); runCurrent(); s.openAsset(s.state.value.feed!!.items[0]); runCurrent()
        s.openVideo(); val old = a.callback!!; s.closeVideo(); s.openVideo()
        old(HomeFailure(HomeError.DENIED)); runCurrent()
        assertTrue(a.sources[0].isClosed); assertFalse(a.sources[1].isClosed); assertNotNull(s.state.value.feed)
        s.background(); assertTrue(a.sources[1].isClosed); assertNull(s.state.value.video)
    }
    @Test fun decoderFailureStaysLocalAndDisconnectClosesSource() = runTest {
        val a = Api(); val s = HomeStore(a, backgroundScope)
        s.foreground(); runCurrent(); s.openAsset(s.state.value.feed!!.items[0]); runCurrent(); s.openVideo()
        s.videoPlaybackFailed(); assertTrue(s.state.value.videoFailed); assertNotNull(s.state.value.feed)
        assertTrue(a.sources[0].isClosed); s.openVideo(); s.disconnect()
        assertTrue(a.sources[1].isClosed); assertNull(s.state.value.feed)
    }
}
