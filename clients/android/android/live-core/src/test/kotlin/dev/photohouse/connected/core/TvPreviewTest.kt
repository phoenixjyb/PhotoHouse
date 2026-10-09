package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.runBlocking
import okhttp3.*
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.*
import org.junit.Test

class TvPreviewTest {
    private val token = Bearer.from(SessionToken(86400, "T".repeat(43), "Bearer"))
    private val asset = Asset("1", "image", null, null, null, null, "/assets/1/thumbnail?library=synthetic")
    private fun exercise(size: Int = 1024, statuses: List<Int>, run: suspend (HttpsPhotoHouseApi, MutableList<Request>) -> Unit) = runBlocking {
        val requests = mutableListOf<Request>()
        val client = OkHttpClient.Builder().addInterceptor { chain ->
            requests += chain.request()
            Response.Builder().request(chain.request()).protocol(Protocol.HTTP_1_1)
                .code(statuses[minOf(requests.lastIndex, statuses.lastIndex)]).message("Synthetic")
                .header("Content-Type", "image/jpeg").body(byteArrayOf(1, 2, 3).toResponseBody()).build()
        }.build()
        try { run(HttpsPhotoHouseApi(TrustedOrigin.parse("https://photohouse.test"), client, size), requests) }
        finally { client.dispatcher.executorService.shutdown(); client.connectionPool.evictAll() }
    }
    @Test fun largeDetailPreviewIsScopedAuthenticatedAndGridStaysSmall() = exercise(statuses = listOf(200)) { api, requests ->
        api.thumbnail(token, "synthetic", asset)
        assertNull(requests.single().url.queryParameter("size"))
        assertArrayEquals(byteArrayOf(1, 2, 3), api.detailPreview(token, "synthetic", asset))
        val request = requests.last()
        assertEquals("1024", request.url.queryParameter("size"))
        assertEquals("synthetic", request.url.queryParameter("library"))
        assertEquals(token.header(), request.header("Authorization"))
        assertEquals("no-store", request.header("Cache-Control"))
        assertEquals("/assets/1/thumbnail", request.url.encodedPath)
    }
    @Test fun missingLargePreviewFallsBackOnlyToCachedDefault() = exercise(statuses = listOf(404, 200)) { api, requests ->
        assertNotNull(api.detailPreview(token, "synthetic", asset))
        assertEquals(listOf("1024", null), requests.map { it.url.queryParameter("size") })
        assertTrue(requests.all { it.url.encodedPath == "/assets/1/thumbnail" })
    }
    @Test fun missingBothSizesNeverRequestsOriginal() = exercise(statuses = listOf(404)) { api, requests ->
        assertNull(api.detailPreview(token, "synthetic", asset))
        assertEquals(2, requests.size)
        assertTrue(requests.none { it.url.encodedPath.endsWith("/media") })
    }
    @Test fun deniedOrBusyLargePreviewNeverRetriesOrFallsBack() {
        for (status in listOf(401, 403, 429, 503)) exercise(statuses = listOf(status)) { api, requests ->
            val failure = runCatching { api.detailPreview(token, "synthetic", asset) }.exceptionOrNull() as ApiFailure
            assertEquals(status, failure.status)
            assertEquals(1, requests.size)
        }
    }
    @Test fun defaultPhoneDetailStillUsesOneDefaultThumbnail() = exercise(size = 256, statuses = listOf(404)) { api, requests ->
        assertNull(api.detailPreview(token, "synthetic", asset))
        assertEquals(1, requests.size); assertNull(requests.single().url.queryParameter("size"))
    }
    @Test fun foreignMetadataIsRefusedBeforeARequest() = exercise(statuses = listOf(200)) { api, requests ->
        assertTrue(runCatching { api.detailPreview(token, "synthetic", asset.copy(thumbnail_url = "https://foreign.test/image")) }.isFailure)
        assertTrue(requests.isEmpty())
    }
}
