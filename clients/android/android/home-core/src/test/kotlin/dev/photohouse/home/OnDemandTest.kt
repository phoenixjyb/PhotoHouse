package dev.photohouse.home

import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import okhttp3.*
import okhttp3.mockwebserver.*
import okhttp3.tls.*
import okio.Buffer
import org.junit.Test
import org.junit.Assert.*
import java.net.InetAddress

private fun demandResource(name: String) = requireNotNull(CatalogWire::class.java.classLoader.getResourceAsStream(name)).use { it.readBytes() }
private fun demandFeed() = CatalogWire.feed(demandResource("catalog-v3.json"), 1, version = 3)

@OptIn(ExperimentalCoroutinesApi::class)
class OnDemandTest {
    @Test fun backendFixtureHasLazyPhotosAndExplicitDirectVideoAndOriginalPolicy() {
        val f = demandFeed(); assertEquals(3, f.version)
        assertTrue(f.items[0].video!!.direct); assertTrue(f.items[1].grid!!.onDemand)
        assertNotNull(f.items[1].original)
        assertThrows(HomeFailure::class.java) { CatalogWire.feed(demandResource("catalog-v3.json"), 1) }
        val raw = demandResource("catalog-v3.json").toString(Charsets.UTF_8)
        for (bad in listOf(raw.replace("/home/v3/", "https://other.example/"),
            raw.replace("\"originals_allowed\":true", "\"originals_allowed\":false"),
            raw.replace("\"h264\"", "\"hevc\""), raw.replace("\"bytes\":631", "\"bytes\":67108865"))) {
            if (bad != raw) assertThrows(HomeFailure::class.java) { CatalogWire.feed(bad.toByteArray(), 1, version = 3) }
        }
    }
    @Test fun lazyPreviewAndOriginalUseStrictCredentialFreeHttpsAndBoundedBodies() = runBlocking {
        val certificate = HeldCertificate.Builder().addSubjectAlternativeName("home.photohouse.test").build()
        val server = MockWebServer()
        server.useHttps(HandshakeCertificates.Builder().heldCertificate(certificate).build().sslSocketFactory(), false)
        server.start(InetAddress.getByName("127.0.0.1"), 0)
        val trust = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
        val client = OkHttpClient.Builder().sslSocketFactory(trust.sslSocketFactory(), trust.trustManager)
            .dns(object : Dns { override fun lookup(hostname: String) = listOf(InetAddress.getByName("127.0.0.1")) }).build()
        try {
            val api = HttpsCatalogApi(HomeOrigin.parse("https://home.photohouse.test:${server.port}"), client, 3)
            val asset = demandFeed().items[1]; val jpeg = demandResource("home-8x8.jpg")
            fun response() = MockResponse().setHeader("Content-Type", "image/jpeg").setHeader("Cache-Control", "no-store").setBody(Buffer().write(jpeg))
            server.enqueue(response()); assertArrayEquals(jpeg, api.preview(asset, Variant.GRID, 9))
            server.enqueue(response()); assertArrayEquals(jpeg, api.original(asset, 9))
            for (path in listOf("/home/v3/assets/101/preview?variant=grid&revision=9", "/home/v3/assets/101/original?revision=9")) {
                val request = server.takeRequest(); assertEquals(path, request.path); assertNull(request.getHeader("Authorization")); assertNull(request.getHeader("Cookie"))
            }
            server.enqueue(MockResponse().setHeader("Content-Type", "image/jpeg").setHeader("Cache-Control", "no-store").setBody("bad"))
            try { api.preview(asset, Variant.GRID, 9); fail("Malformed image accepted") } catch (_: HomeFailure) { }
        } finally { server.shutdown(); client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown() }
    }
    @Test fun aBusyThumbnailDoesNotEraseThePageAndLateOriginalIsDiscarded() = runTest {
        val gate = CompletableDeferred<ByteArray>()
        val api = object : HomeApi {
            override val catalogVersion = 3
            override suspend fun feed(page: Int) = demandFeed()
            override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray? {
                if (variant == Variant.GRID) throw HomeFailure(HomeError.BUSY)
                return demandResource("home-8x8.jpg")
            }
            override suspend fun original(asset: HomeAsset, revision: Int) = withContext(NonCancellable) { gate.await() }
        }
        val store = HomeStore(api, backgroundScope)
        store.foreground(); runCurrent(); assertNotNull(store.state.value.feed); assertNull(store.state.value.problem)
        store.openAsset(store.state.value.feed!!.items[1]); runCurrent(); store.openOriginal(); runCurrent()
        store.background(); gate.complete(demandResource("home-8x8.jpg")); runCurrent()
        assertNull(store.state.value.display); assertTrue(store.state.value.covered)
    }
    @Test fun busyPreviewHonorsRetryAfterThenLoadsWithoutDiscardingThePage() = runTest {
        var attempts = 0
        val api = object : HomeApi {
            override val catalogVersion = 3
            override suspend fun feed(page: Int) = demandFeed().copy(items = listOf(demandFeed().items[1]))
            override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray {
                if (++attempts == 1) throw HomeFailure(HomeError.BUSY, 3000)
                return demandResource("home-8x8.jpg")
            }
        }
        val store = HomeStore(api, backgroundScope)
        store.foreground(); runCurrent(); assertEquals(1, attempts)
        advanceTimeBy(2999); runCurrent(); assertEquals(1, attempts)
        advanceTimeBy(1); runCurrent(); assertEquals(2, attempts)
        assertNotNull(store.state.value.grids[101]); assertTrue(store.state.value.gridProblems.isEmpty())
        store.background()
    }
    @Test fun failedThumbnailHasAnExplicitRetryAndDoesNotBecomePermanentlyUnavailable() = runTest {
        var offline = true
        val api = object : HomeApi {
            override val catalogVersion = 3
            override suspend fun feed(page: Int) = demandFeed().copy(items = listOf(demandFeed().items[1]))
            override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int): ByteArray {
                if (offline) throw HomeFailure(HomeError.OFFLINE)
                return demandResource("home-8x8.jpg")
            }
        }
        val store = HomeStore(api, backgroundScope)
        store.foreground(); runCurrent(); assertEquals(HomeError.OFFLINE, store.state.value.gridProblems[101])
        assertFalse(101 in store.state.value.missingGrids)
        offline = false; store.retryPreviews(); runCurrent()
        assertNotNull(store.state.value.grids[101]); assertTrue(store.state.value.gridProblems.isEmpty())
        store.background()
    }
    @Test fun videoReadFailureKeepsSelectionAndErrorUntilUserRetriesOrLeaves() = runTest {
        for (kind in listOf(HomeError.OFFLINE, HomeError.UNAVAILABLE, HomeError.BUSY, HomeError.INVALID)) {
            var callback: ((Exception) -> Unit)? = null
            val api = object : HomeApi {
                override val catalogVersion = 3
                override suspend fun feed(page: Int) = demandFeed().copy(page = page)
                override suspend fun preview(asset: HomeAsset, variant: Variant, revision: Int) = demandResource("home-8x8.jpg")
                override fun video(asset: HomeAsset, revision: Int, failed: (Exception) -> Unit): HomeVideoSource {
                    callback = failed; return HomeVideoReader(4, 4, { _, n -> ByteArray(n) }, failed)
                }
            }
            val store = HomeStore(api, backgroundScope)
            store.foreground(); runCurrent(); store.loadPage(2); runCurrent()
            store.openAsset(store.state.value.feed!!.items[0], openPlayer = true); runCurrent()
            callback!!(HomeFailure(kind)); runCurrent(); advanceTimeBy(10000); runCurrent()
            assertEquals(102, store.state.value.selected); assertEquals(2, store.state.value.feed!!.page)
            assertTrue(store.state.value.videoFailed); assertEquals(kind, store.state.value.mediaProblem)
            assertNull(store.state.value.video)
            store.openVideo(); assertNotNull(store.state.value.video); assertNull(store.state.value.mediaProblem)
            store.background()
        }
    }

}
