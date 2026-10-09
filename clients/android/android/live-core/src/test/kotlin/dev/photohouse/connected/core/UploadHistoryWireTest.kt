package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlinx.serialization.json.*

class UploadHistoryWireTest {
    private fun body(item: String = """{"asset_id":"901","created_at":1760000000,"bytes":1234,"kind":"image","state":"available","library_id":"family"}""") =
        """{"page":1,"page_size":10,"total":1,"items":[$item]}""".toByteArray()

    @Test fun replaysBackendCandidate24SuccessBodies() {
        val bytes = javaClass.getResourceAsStream("/upload-history-candidate24.json")!!.use { it.readBytes() }
        val cases = Json.parseToJsonElement(bytes.decodeToString()).jsonObject.getValue("cases").jsonArray
        assertEquals(9, cases.size)
        var parsed = 0
        for (case in cases) {
            val response = case.jsonObject.getValue("response").jsonObject
            if (response.getValue("status").jsonPrimitive.int != 200) continue
            val body = response.getValue("body").jsonObject
            val page = UploadHistoryWire.parse(body.toString().toByteArray(), 1)
            assertEquals(body.getValue("total").jsonPrimitive.int, page.total)
            parsed++
        }
        assertEquals(4, parsed)
    }

    @Test fun parsesAvailableItemAndRequiresExactShape() {
        val page = UploadHistoryWire.parse(body(), 1)
        assertEquals(1, page.total)
        assertEquals("901", page.items.single().assetId)
        assertEquals("family", page.items.single().libraryId)
        assertEquals("available", page.items.single().state)
        assertTrue(runCatching { UploadHistoryWire.parse(body().decodeToString().replace("\"items\"", "\"extra\":1,\"items\"").toByteArray(), 1) }.isFailure)
    }

    @Test fun rejectsBadBoundsStatesAndAvailabilityBinding() {
        val badBytes = body().decodeToString().replace("1234", "0")
        val badState = body().decodeToString().replace("available", "awaiting_review")
        val badLibrary = body().decodeToString().replace("\"library_id\":\"family\"", "\"library_id\":null")
        assertTrue(runCatching { UploadHistoryWire.parse(badBytes.toByteArray(), 1) }.isFailure)
        assertTrue(runCatching { UploadHistoryWire.parse(badState.toByteArray(), 1) }.isFailure)
        assertTrue(runCatching { UploadHistoryWire.parse(badLibrary.toByteArray(), 1) }.isFailure)
    }

    @Test fun rejectsWrongPageSizeAndInconsistentCounts() {
        val wrongSize = body().decodeToString().replace("\"page_size\":10", "\"page_size\":50")
        val wrongCount = body().decodeToString().replace("\"total\":1", "\"total\":2")
        val item = body().decodeToString().substringAfter("\"items\":[").substringBeforeLast("]")
        val duplicate = """{"page":1,"page_size":10,"total":2,"items":[$item,$item]}"""
        assertTrue(runCatching { UploadHistoryWire.parse(wrongSize.toByteArray(), 1) }.isFailure)
        assertTrue(runCatching { UploadHistoryWire.parse(wrongCount.toByteArray(), 1) }.isFailure)
        assertTrue(runCatching { UploadHistoryWire.parse(duplicate.toByteArray(), 1) }.isFailure)
    }
}
