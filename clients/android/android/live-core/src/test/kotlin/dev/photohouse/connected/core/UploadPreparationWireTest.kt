package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test

class UploadPreparationWireTest {
    private fun payload(
        version: Int = 1,
        stages: String = "\"preview\":\"unknown\",\"index\":\"finished\",\"faces\":\"unknown\",\"caption\":\"unknown\",\"video_probe\":\"not_applicable\"",
        records: String = "\"image_vector\":true,\"caption\":false,\"face_detections\":false",
        availability: String = "\"preview\":\"unknown\",\"playback\":\"not_applicable\"",
        state: String = "available",
        processing: String = "\"stages\":{$stages},\"records\":{$records},\"availability\":{$availability}",
    ) = """{"version":$version,"page":1,"page_size":10,"total":1,"items":[{"asset_id":"901","created_at":1760000000,"bytes":1234,"kind":"image","state":"$state","library_id":"family","processing":{$processing}}]}""".toByteArray()

    @Test fun parsesVersionOneAllowlistedEvidence() {
        val item = UploadPreparationWire.parse(payload(), 1).items.single()
        val evidence = requireNotNull(item.processing)
        assertEquals(UploadPreparationStageState.FINISHED, evidence.stages[UploadPreparationStage.INDEX])
        assertEquals(UploadPreparationAvailability.NOT_APPLICABLE, evidence.availability["playback"])
        assertTrue(evidence.records.imageVector)
    }

    @Test fun rejectsUnknownVersionMalformedEnvelopeAndUnknownStates() {
        assertEquals(FailureKind.INVALID_RESPONSE, runCatching { UploadPreparationWire.parse(payload(version = 2), 1) }.exceptionOrNull().let { (it as ApiFailure).kind })
        assertTrue(runCatching { UploadPreparationWire.parse("{".toByteArray(), 1) }.isFailure)
        assertTrue(runCatching { UploadPreparationWire.parse(payload(stages = "\"preview\":\"future_state\",\"index\":\"finished\",\"faces\":\"unknown\",\"caption\":\"unknown\",\"video_probe\":\"not_applicable\""), 1) }.isFailure)
        assertTrue(runCatching { UploadPreparationWire.parse(payload(stages = "\"preview\":\"unknown\",\"index\":\"finished\",\"faces\":\"unknown\",\"caption\":\"unknown\",\"surprise\":\"unknown\""), 1) }.isFailure)
    }

    @Test fun rejectsNonBooleanRecordAndReadinessClaims() {
        assertTrue(runCatching { UploadPreparationWire.parse(payload(records = "\"image_vector\":\"true\",\"caption\":false,\"face_detections\":false"), 1) }.isFailure)
        assertTrue(runCatching { UploadPreparationWire.parse(payload(availability = "\"preview\":\"ready\",\"playback\":\"not_applicable\""), 1) }.isFailure)
    }

    @Test fun rejectsProcessingOnUnavailableReceipt() {
        assertTrue(runCatching { UploadPreparationWire.parse(payload(state = "unavailable"), 1) }.isFailure)
        val noProcessing = """{"version":1,"page":1,"page_size":10,"total":1,"items":[{"asset_id":"901","created_at":1760000000,"bytes":1234,"kind":"image","state":"unavailable","library_id":null,"processing":null}]}""".toByteArray()
        assertNull(UploadPreparationWire.parse(noProcessing, 1).items.single().processing)
    }
}
