package dev.photohouse.home

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean

/** Opt-in only. Private inputs come from the operator; media stays in memory, never test reports. */
class CatalogLanPilotTest {
    private fun input(name: String): String = requireNotNull(System.getenv(name)) { "Missing private canary input" }
    private fun number(name: String): Int = input(name).toInt().also { require(it > 0) }

    @Test fun approvedPhotoAndVideoUseMappedTlsAndRevisionBoundBytes() = runBlocking {
        require(input("PHOTOHOUSE_CATALOG_LIVE_APPROVED") == "true")
        val api = HttpsCatalogApi(
            HomeOrigin.parse(input("PHOTOHOUSE_CATALOG_TEST_ORIGIN")),
            HomeLanAddress.parse(input("PHOTOHOUSE_CATALOG_TEST_ADDRESS")),
        )
        val first = api.feed(1)
        assertTrue("Catalog is empty", first.total > 0)
        assertEquals(2, first.version)
        suspend fun selected(pageKey: String, idKey: String, kind: AssetKind): HomeAsset {
            val page = number(pageKey)
            require(page <= (first.total + 49) / 50)
            val feed = if (page == 1) first else api.feed(page, first.revision)
            assertEquals(first.total, feed.total)
            val id = number(idKey)
            val asset = requireNotNull(feed.items.singleOrNull { it.id == id }) { "Canary missing from reviewed page" }
            assertTrue("Wrong canary media kind", asset.kind == kind)
            return asset
        }
        val photo = selected("PHOTOHOUSE_CATALOG_PHOTO_PAGE", "PHOTOHOUSE_CATALOG_PHOTO_ID", AssetKind.PHOTO)
        val video = selected("PHOTOHOUSE_CATALOG_VIDEO_PAGE", "PHOTOHOUSE_CATALOG_VIDEO_ID", AssetKind.VIDEO)
        for (asset in listOf(photo, video)) {
            for (variant in Variant.entries) {
                // The production adapter verifies SHA-256, framing, dimensions and revision URLs.
                assertNotNull("Canary preview unavailable", api.preview(asset, variant, first.revision))
            }
        }
        val metadata = requireNotNull(video.video) { "Canary video unavailable" }
        require(metadata.bytes <= 64L * 1024 * 1024) { "Canary exceeds approved read budget" }
        val failed = AtomicBoolean(false)
        api.video(video, first.revision) { failed.set(true) }.use { source ->
            assertEquals(metadata.bytes, source.size())
            val buffer = ByteArray(CatalogWire.READ_BYTES)
            val digest = MessageDigest.getInstance("SHA-256")
            var position = 0L
            while (position < source.size()) {
                val count = source.readAt(position, buffer, 0, buffer.size)
                assertTrue("Video read made no progress", count > 0)
                digest.update(buffer, 0, count)
                position += count
            }
            assertEquals(metadata.bytes, position)
            assertEquals(-1, source.readAt(position, buffer, 0, 1))
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            assertTrue("Video integrity mismatch", actual == metadata.sha256)
            // Exercise a backward seek through the exact reader handed to Android MediaPlayer.
            val head = ByteArray(32)
            assertEquals(head.size, source.readAt(0, head, 0, head.size))
            assertFalse("Video reader reported a failure", failed.get())
        }
        val repeated = api.feed(1, first.revision)
        assertTrue("Catalog changed during canary verification", first == repeated)
    }
}
