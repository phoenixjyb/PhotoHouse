package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class AssistantWireTest {
    @Test fun trackingHeadersAreStrictAndRequestIdMustEchoClientId() {
        val id = "123e4567-e89b-42d3-a456-426614174000"
        assertEquals(AssistantRequestReceipt(id, "enabled", "succeeded"), AssistantWire.requestReceipt(mapOf(
            "X-PhotoHouse-Tracking" to "enabled", "X-PhotoHouse-Request-Id" to id, "X-PhotoHouse-Receipt-Status" to "succeeded"), id))
        assertEquals("disabled", AssistantWire.requestReceipt(mapOf("X-PhotoHouse-Tracking" to "disabled"), id).tracking)
        assertTrue(runCatching { AssistantWire.requestReceipt(mapOf("X-PhotoHouse-Tracking" to "enabled", "X-PhotoHouse-Request-Id" to "123e4567-e89b-12d3-a456-426614174000", "X-PhotoHouse-Receipt-Status" to "succeeded"), id) }.isFailure)
        assertTrue(runCatching { AssistantWire.requestReceipt(mapOf("X-PhotoHouse-Tracking" to "enabled", "X-PhotoHouse-Request-Id" to id, "X-PhotoHouse-Receipt-Status" to "unknown"), id) }.isFailure)
    }
    @Test fun playbackCapabilityIsSpeechOnlyAndStrictWhenPresent() {
        val id = "123e4567-e89b-42d3-a456-426614174000"
        assertFalse(AssistantWire.speechRequestReceipt(emptyMap(), id).playbackTracking)
        assertTrue(AssistantWire.speechRequestReceipt(mapOf("X-PhotoHouse-Playback-Tracking" to "enabled"), id).playbackTracking)
        assertFalse(AssistantWire.speechRequestReceipt(mapOf("X-PhotoHouse-Playback-Tracking" to "disabled"), id).playbackTracking)
        assertTrue(runCatching { AssistantWire.speechRequestReceipt(mapOf("X-PhotoHouse-Playback-Tracking" to "true"), id) }.isFailure)
        assertFalse(AssistantWire.requestReceipt(mapOf("X-PhotoHouse-Playback-Tracking" to "enabled"), id).playbackTracking)
    }
    @Test fun playbackOutcomeResponseIsStrictAndBoundToTheExpectedRequestAndOutcome() {
        val id = "123e4567-e89b-42d3-a456-426614174000"
        AssistantWire.playbackOutcome("""{"version":1,"request_id":"$id","playback_outcome":"completed"}""".toByteArray(), id, "completed")
        assertTrue(runCatching { AssistantWire.playbackOutcome("""{"version":1,"request_id":"$id","playback_outcome":"failed","extra":1}""".toByteArray(), id, "failed") }.isFailure)
        assertTrue(runCatching { AssistantWire.playbackOutcome("""{"version":1,"request_id":"123e4567-e89b-42d3-a456-426614174001","playback_outcome":"failed"}""".toByteArray(), id, "failed") }.isFailure)
    }
    @Test fun asrErrorsExposeOnlyKnownCodesWithTheirExpectedStatus() {
        val errors = mapOf("speech_no_input" to 422, "speech_busy" to 503,
            "speech_timeout" to 504, "speech_invalid_response" to 502)
        errors.forEach { (code, status) ->
            val body = """{"error":"$code","detail":"Local transcription could not complete"}""".toByteArray()
            assertEquals(code, AssistantWire.asrErrorCode(body, status))
            assertNull(AssistantWire.asrErrorCode(body, status + 1))
        }
        assertNull(AssistantWire.asrErrorCode("""{"error":"speech_no_input","detail":"x","provider":"private"}""".toByteArray(), 422))
        assertNull(AssistantWire.asrErrorCode("""{"error":"speech_no_input","detail":"x"}""".toByteArray(), 400))
    }
    @Test fun pendingAndInterruptedReceiptsAcceptNullHttpStatusWithoutClaimingCompletion() {
        val id = "123e4567-e89b-42d3-a456-426614174000"
        val body = """{"version":1,"request_id":"$id","operation":"transcribe","parent_request_id":null,"status":"received","created_at":"2026-09-30T00:00:00Z","updated_at":"2026-09-30T00:00:00Z","expires_at":"2026-10-30T00:00:00Z","http_status":null,"error_code":null,"input_text":null,"recognized_text":null,"result_kind":null,"result_total":null,"client_outcome":null}"""
        assertNull(AssistantWire.receipt(body.toByteArray(), id).httpStatus)
        assertEquals("interrupted", AssistantWire.receipt(body.replace("received", "interrupted").toByteArray(), id).status)
        assertTrue(runCatching { AssistantWire.receipt(body.replace("received", "succeeded").toByteArray(), id) }.isFailure)
    }
    @Test fun requestIsTypedBoundedAndCarriesOnlyServerContext() {
        val context = buildJsonObject { put("revision", "opaque"); put("visible_ids", buildJsonArray { add("101") }) }
        val request = Json.parseToJsonElement(AssistantWire.request("family-a", "找去年夏天的照片", context)).jsonObject
        assertEquals("family-a", request.getValue("library_id").jsonPrimitive.content)
        assertEquals("找去年夏天的照片", request.getValue("text").jsonPrimitive.content)
        assertEquals(context, request.getValue("context"))
        assertTrue(runCatching { AssistantWire.request("family-a", "界".repeat(2049), null) }.isFailure)
        assertTrue(runCatching { AssistantWire.request("family-a", "界".repeat(342), null) }.isFailure)
        assertTrue(runCatching { AssistantWire.request("family-a", "\n\r", null) }.isFailure)
    }

    @Test fun capabilitiesRespectExplicitSpeechAndAudioFields() {
        val enabled = """{"version":1,"enabled":true,"text":true,"transcribe":false,"speech":false,"max_audio_seconds":0}""".toByteArray()
        assertEquals(AssistantCapabilities(true, true, false, false, 0), AssistantWire.capabilities(enabled))
        val invalid = enabled.toString(Charsets.UTF_8).replace("\"max_audio_seconds\":0", "\"max_audio_seconds\":60").toByteArray()
        assertTrue(runCatching { AssistantWire.capabilities(invalid) }.isFailure)
    }

    @Test fun transcriptContractIsBoundedAndLanguageEnumerated() {
        assertEquals(AssistantTranscript("海边的照片", "zh"), AssistantWire.transcript("""{"version":1,"text":"海边的照片","language":"zh"}""".toByteArray()))
        assertTrue(runCatching { AssistantWire.transcript("""{"version":1,"text":"hello","language":"fr"}""".toByteArray()) }.isFailure)
        assertTrue(runCatching { AssistantWire.transcript("""{"version":1,"text":"x","language":"en","extra":true}""".toByteArray()) }.isFailure)
    }

    @Test fun speechRequestRequiresOpaqueResultContextAndSupportedLanguage() {
        val context = buildJsonObject { put("revision", "opaque") }
        val request = Json.parseToJsonElement(AssistantWire.speechRequest("family-a", context, "zh")).jsonObject
        assertEquals(setOf("library_id", "context", "language"), request.keys)
        assertEquals(context, request.getValue("context")); assertEquals("zh", request.getValue("language").jsonPrimitive.content)
        assertTrue(runCatching { AssistantWire.speechRequest("family-a", null, "en") }.isFailure)
        assertTrue(runCatching { AssistantWire.speechRequest("family-a", context, "fr") }.isFailure)
    }

    @Test fun speechWavMustBeBoundedRiffWave() {
        val wav = ByteArray(46).also { "RIFF".toByteArray().copyInto(it); "WAVE".toByteArray().copyInto(it, 8) }
        assertEquals(wav.toList(), AssistantWire.speechAudio(wav).toList())
        assertTrue(runCatching { AssistantWire.speechAudio(ByteArray(46)) }.isFailure)
    }

    @Test fun resultItemsAreBoundToTheLibraryAndOpenEffectUsesDecimalId() {
        val reply = """{"version":1,"kind":"open","reply":"正在打开这张照片。","context":{"visible_ids":["101"]},"filters":null,"items":[{"id":"101","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/101/thumbnail?library=family-a","date_hint":null}],"total":1,"has_more":false,"effect":{"type":"open_asset","asset_id":"101"}}""".toByteArray()
        val parsed = AssistantWire.response(reply, "family-a")
        assertEquals("open", parsed.kind); assertEquals("101", parsed.effect?.assetId)
        val bad = reply.toString(Charsets.UTF_8).replace("\"101\"}}", "\"0\"}}" )
        assertTrue(runCatching { AssistantWire.response(bad.toByteArray(), "family-a") }.isFailure)
    }

    @Test fun ordinaryResultShapeUsesProtectedThumbnailPathAndStrictId() {
        val body = """{"version":1,"kind":"results","reply":"找到了。","context":null,"filters":{"media":["image"]},"items":[{"id":"101","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/101/thumbnail?library=family-a","date_hint":null}],"total":1,"has_more":false,"effect":null}""".toByteArray()
        val parsed = AssistantWire.response(body, "family-a")
        assertEquals("101", parsed.items.single().id)
        assertTrue(runCatching { AssistantWire.response(body, "family-b") }.isFailure)
        assertTrue(runCatching { AssistantWire.response(body.toString(Charsets.UTF_8).replace("\"101\"", "\"01\"", true).toByteArray(), "family-a") }.isFailure)
    }

    @Test fun legacySevenKeyAssetsAreAcceptedForResultsAndOpenWithUnknownDateProvenance() {
        val item = """{"id":"101","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":"2024-05-01","thumbnail_url":"/assets/101/thumbnail?library=family-a"}"""
        val results = """{"version":1,"kind":"results","reply":"Found one.","context":null,"filters":null,"items":[$item],"total":1,"has_more":false,"effect":null}""".toByteArray()
        val parsedResults = AssistantWire.response(results, "family-a")
        assertEquals("101", parsedResults.items.single().id)
        assertNull(parsedResults.items.single().date_hint)

        val opened = """{"version":1,"kind":"open","reply":"Opening.","context":{"visible_ids":["101"]},"filters":null,"items":[$item],"total":1,"has_more":false,"effect":{"type":"open_asset","asset_id":"101"}}""".toByteArray()
        val parsedOpen = AssistantWire.response(opened, "family-a")
        assertEquals("101", parsedOpen.effect?.assetId)
        assertNull(parsedOpen.items.single().date_hint)
    }

    @Test fun assistantHintsPreserveFilenameAndReceivedSourcesAndRejectMalformedAssetKeys() {
        val filename = """{"id":"101","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/101/thumbnail?library=family-a","date_hint":{"value":"2024-05-01","source":"filename"}}"""
        val received = """{"id":"102","kind":"image","width":800,"height":600,"duration_sec":null,"taken_at":null,"thumbnail_url":"/assets/102/thumbnail?library=family-a","date_hint":{"value":"2024-05-02","source":"received"}}"""
        val body = """{"version":1,"kind":"results","reply":"Found two.","context":null,"filters":null,"items":[$filename,$received],"total":2,"has_more":false,"effect":null}""".toByteArray()
        val parsed = AssistantWire.response(body, "family-a")
        assertEquals("filename", parsed.items[0].date_hint?.source)
        assertEquals("received", parsed.items[1].date_hint?.source)

        val extraKey = body.toString(Charsets.UTF_8).replace("\"kind\":\"image\"", "\"kind\":\"image\",\"unexpected\":true")
        assertTrue(runCatching { AssistantWire.response(extraKey.toByteArray(), "family-a") }.isFailure)
        val invalidSource = body.toString(Charsets.UTF_8).replace("\"source\":\"filename\"", "\"source\":\"capture\"")
        assertTrue(runCatching { AssistantWire.response(invalidSource.toByteArray(), "family-a") }.isFailure)
        assertTrue(runCatching { AssistantWire.response(body, "family-b") }.isFailure)
    }
}
