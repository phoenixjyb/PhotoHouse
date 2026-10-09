package dev.photohouse.home

import kotlinx.coroutines.runBlocking
import org.junit.Test
import org.junit.Assert.*

/** Explicit opt-in for the authorized synthetic LAN service. No credentials or real library. */
class HomeLanPilotTest {
    @Test fun mappedAdapterReadsExactSyntheticFeedAndPreparedImages() = runBlocking {
        val origin = HomeOrigin.parse(requireNotNull(System.getenv("PHOTOHOUSE_HOME_TEST_ORIGIN")))
        val address = HomeLanAddress.parse(requireNotNull(System.getenv("PHOTOHOUSE_HOME_TEST_ADDRESS")))
        val api = HttpsHomeApi(origin, address)
        val feed = api.feed(1)
        assertEquals("synthetic-home", feed.id)
        assertEquals(1, feed.total)
        val asset = feed.items.single()
        assertEquals(101, asset.id)
        val expected = fixture().items.single()
        assertEquals(expected.grid!!.sha256, asset.grid!!.sha256)
        assertEquals(expected.display!!.sha256, asset.display!!.sha256)
        assertArrayEquals(resource("home-8x8.jpg"), api.preview(asset, Variant.GRID, feed.revision))
        assertArrayEquals(resource("home-3840x2160.jpg"), api.preview(asset, Variant.DISPLAY, feed.revision))
        assertEquals(3840, asset.display!!.width); assertEquals(2160, asset.display!!.height)
        // The same in-app mapping serves metadata and image requests, with normal JVM trust.
        assertEquals(feed, api.feed(1))
    }
}
