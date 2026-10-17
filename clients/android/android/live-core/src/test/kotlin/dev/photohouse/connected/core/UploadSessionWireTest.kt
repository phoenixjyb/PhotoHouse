package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class UploadSessionWireTest {
    private val id = "a".repeat(32)
    private val body = """{"upload_id":"$id","bytes":8,"offset":0,"chunk_bytes":4194304,"state":"uploading","asset_id":null}"""
    private fun response(
        state: String = "uploading", offset: Int = 0, asset: String = "null", extras: String = "",
    ) = """{"upload_id":"$id","bytes":8,"offset":$offset,"chunk_bytes":4194304,"state":"$state","asset_id":$asset$extras}"""

    @Test fun parsesExactSessionAndEncodesExactRequest() {
        val parsed = UploadSessionWire.parse(body.toByteArray()); assertEquals(8, parsed.bytes); assertEquals(4194304, parsed.chunkBytes)
        assertNull(parsed.destinationLibraryId); assertNull(parsed.approvalState); assertNull(parsed.libraryId)
        val encoded = UploadSessionWire.request(UploadSessionRequest("1".repeat(32), "2".repeat(32), "x.mp4", 8, "3".repeat(64), UploadKind.VIDEO))
        assertEquals(setOf("request_id", "batch", "filename", "bytes", "sha256", "kind"), kotlinx.serialization.json.Json.parseToJsonElement(encoded).jsonObject.keys)
        val targeted = UploadSessionWire.request(UploadSessionRequest("1".repeat(32), "2".repeat(32), "x.mp4", 8, "3".repeat(64), UploadKind.VIDEO, "family-a"))
        val targetedObject = kotlinx.serialization.json.Json.parseToJsonElement(targeted).jsonObject
        assertEquals("family-a", targetedObject.getValue("destination_library_id").jsonPrimitive.content)
        assertEquals(setOf("request_id", "batch", "filename", "bytes", "sha256", "kind", "destination_library_id"), targetedObject.keys)
    }

    @Test fun parsesTargetedCreateChunkGetAndCancelResponses() {
        val destination = ",\"destination_library_id\":\"family-a\""
        val responses = listOf(
            response(extras = destination),
            response(offset = 8, extras = destination),
            response(offset = 4, extras = destination),
            response(state = "cancelled", extras = destination),
        )
        val parsed = responses.map { UploadSessionWire.parse(it.toByteArray()) }
        assertEquals(listOf("uploading", "uploading", "uploading", "cancelled"), parsed.map { it.state })
        assertEquals(listOf(0L, 8L, 4L, 0L), parsed.map { it.offset })
        assertEquals(List(4) { "family-a" }, parsed.map { it.destinationLibraryId })
    }

    @Test fun parsesCompletedTargetedResponsesForServerApprovalOutcomes() {
        val asset = "\"123\""
        val base = response(state = "complete", offset = 8, asset = asset)
        val completed = listOf(
            base.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"automatic\",\"library_id\":\"family-a\"}",
            base.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"manual\",\"library_id\":\"family-a\"}",
            base.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"awaiting_review\"}",
            base.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"unavailable\"}",
            base.dropLast(1) + ",\"destination_library_id\":\"family-a\"}",
        )
        val parsed = completed.map { UploadSessionWire.parse(it.toByteArray()) }
        assertEquals(listOf("automatic", "manual", "awaiting_review", "unavailable", null), parsed.map { it.approvalState })
        assertEquals(listOf("family-a", "family-a", null, null, null), parsed.map { it.libraryId })
        assertEquals(List(5) { "family-a" }, parsed.map { it.destinationLibraryId })
    }

    @Test fun rejectsInvalidTargetedResponseFieldsAndCombinations() {
        val destination = ",\"destination_library_id\":\"family-a\""
        val complete = response(state = "complete", offset = 8, asset = "\"123\"")
        val invalid = listOf(
            response(extras = ",\"destination_library_id\":\"ab\""),
            response(extras = ",\"destination_library_id\":42"),
            response(extras = destination + ",\"unknown\":true"),
            response(extras = destination + ",\"destination_library_id\":\"family-a\""),
            response(extras = destination + ",\"approval_state\":\"manual\",\"library_id\":\"family-a\""),
            complete.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"automatic\"}",
            complete.dropLast(1) + ",\"approval_state\":\"automatic\",\"library_id\":\"family-a\"}",
            complete.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"bogus\"}",
            complete.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":42}",
            complete.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"automatic\",\"library_id\":\"other-library\"}",
            complete.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"automatic\",\"library_id\":42}",
            complete.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"manual\"}",
            complete.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"approval_state\":\"awaiting_review\",\"library_id\":\"family-a\"}",
            complete.dropLast(1) + ",\"destination_library_id\":\"family-a\",\"library_id\":\"family-a\"}",
        )
        invalid.forEach { json -> assertThrows(ApiFailure::class.java) { UploadSessionWire.parse(json.toByteArray()) } }
    }

    @Test fun rejectsDuplicateKeysBoundsAndInvalidState() {
        assertThrows(ApiFailure::class.java) { UploadSessionWire.parse(body.replace("\"offset\":0", "\"offset\":0,\"offset\":1").toByteArray()) }
        assertThrows(ApiFailure::class.java) { UploadSessionWire.parse(body.replace("\"bytes\":8", "\"bytes\":0").toByteArray()) }
        assertThrows(ApiFailure::class.java) { UploadSessionWire.parse(body.replace("\"state\":\"uploading\"", "\"state\":\"complete\"").toByteArray()) }
    }
}
