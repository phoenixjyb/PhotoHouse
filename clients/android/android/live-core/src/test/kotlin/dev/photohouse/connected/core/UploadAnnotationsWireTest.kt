package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

internal fun syntheticAnnotationWav(): ByteArray {
    val wav = ByteArray(44 + 32000)
    val buffer = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
    buffer.put("RIFF".toByteArray()); buffer.putInt(wav.size - 8); buffer.put("WAVE".toByteArray())
    buffer.put("fmt ".toByteArray()); buffer.putInt(16); buffer.putShort(1); buffer.putShort(1)
    buffer.putInt(16000); buffer.putInt(32000); buffer.putShort(2); buffer.putShort(16)
    buffer.put("data".toByteArray()); buffer.putInt(32000)
    return wav
}

class UploadAnnotationsWireTest {
    private val mutation = "123e4567-e89b-12d3-a456-426614174000"

    @Test fun requestIsExactAndUsesByteBoundForUtf8Text() {
        val encoded = UploadAnnotationsWire.request(UploadTextAnnotationRequest("a".repeat(32), "42", "mixed", "yes", mutation, "旅拍 🌿"))
        val obj = Json.parseToJsonElement(encoded).jsonObject
        assertEquals(setOf("batch", "asset_id", "language", "consent", "mutation_id", "text"), obj.keys)
        assertEquals("旅拍 🌿", obj.getValue("text").jsonPrimitive.content)
        assertEquals("42", obj.getValue("asset_id").jsonPrimitive.content)
        val exactLimit = "🌿".repeat(4096)
        assertEquals(exactLimit, Json.parseToJsonElement(UploadAnnotationsWire.request(
            UploadTextAnnotationRequest("a".repeat(32), "", "und", "no", mutation, exactLimit))).jsonObject.getValue("text").jsonPrimitive.content)
        assertTrue(runCatching { UploadAnnotationsWire.request(UploadTextAnnotationRequest("a".repeat(32), "", "und", "no", mutation, exactLimit + "🌿")) }.isFailure)
        assertTrue(runCatching { UploadAnnotationsWire.request(UploadTextAnnotationRequest("a".repeat(32), "", "en", "no", mutation, "x".repeat(16 * 1024 + 1))) }.isFailure)
        assertTrue(runCatching { UploadAnnotationsWire.request(UploadTextAnnotationRequest("a".repeat(32), "042", "en", "no", mutation, "description")) }.isFailure)
    }

    @Test fun listPagePreservesOriginalAndDerivationForScopedAsset() {
        val item = annotation("42", "photo caption")
        val page = UploadAnnotationsWire.parsePage("""{"library_id":"family-a","asset_id":"42","batch":"${"a".repeat(32)}","page":1,"page_size":20,"total":1,"items":[$item]}""".toByteArray(), "family-a", "42", 1)
        assertEquals("photo caption", page.items.single().originalText)
        assertEquals("held", page.items.single().derivation.state)
        assertEquals("${"a".repeat(32)}", page.batch)
    }

    @Test fun listPageAcceptsFolderAndAudioOriginalsAlongsideItemNotes() {
        val folder = """{"id":"annotation-folder","scope":"folder","asset_id":null,"batch":"${"a".repeat(32)}","library_id":"family-a","author_id":"member-1","kind":"text","original_text":"the whole trip","audio_url":null,"mime":null,"duration_ms":null,"sha256":null,"language":"en","local_processing_consent":"no","created_at":1720000000,"derivation":{"revision":1,"state":"held","transcript":null,"polished_text":null,"provider":null,"model":null,"error_code":null},"tags":[]}"""
        val audio = """{"id":"annotation-audio","scope":"item","asset_id":"42","batch":"${"a".repeat(32)}","library_id":"family-a","author_id":"member-1","kind":"audio","original_text":null,"audio_url":"/upload-annotations/annotation-audio/audio?library=family-a&asset_id=42","mime":"audio/wav","duration_ms":1000,"sha256":"${"b".repeat(64)}","language":"en","local_processing_consent":"yes","created_at":1720000001,"derivation":{"revision":1,"state":"waiting","transcript":null,"polished_text":null,"provider":null,"model":null,"error_code":null},"tags":[]}"""
        val page = UploadAnnotationsWire.parsePage("""{"library_id":"family-a","asset_id":"42","batch":"${"a".repeat(32)}","page":1,"page_size":20,"total":2,"items":[$folder,$audio]}""".toByteArray(), "family-a", "42", 1)
        assertEquals("", page.items[0].assetId)
        assertEquals("folder", page.items[0].scope)
        assertNull(page.items[1].originalText)
        assertEquals("audio", page.items[1].kind)
    }

    @Test fun audioRequestAcceptsBoundedPcmAndRejectsUnsupportedFiles() {
        val wav = syntheticAnnotationWav()
        val request = UploadAudioAnnotationRequest("a".repeat(32), "", "en", "yes", mutation, wav)
        val info = UploadAnnotationsWire.audioInfo(request)
        assertEquals(1000L, info.durationMs)
        assertEquals(64, info.sha256.length)
        assertTrue(runCatching { UploadAnnotationsWire.audioInfo(UploadAudioAnnotationRequest(
            request.batch, "", "en", "yes", mutation, wav.copyOfRange(0, 100))) }.isFailure)
        val stereo = wav.copyOf().also { it[22] = 2 }
        assertTrue(runCatching { UploadAnnotationsWire.audioInfo(UploadAudioAnnotationRequest(
            request.batch, "", "en", "yes", mutation, stereo)) }.isFailure)
        assertTrue(runCatching { UploadAnnotationsWire.audioInfo(UploadAudioAnnotationRequest(
            request.batch, "", "en", "yes", mutation, ByteArray(2 * 1024 * 1024 + 1))) }.isFailure)
    }

    private fun annotation(asset: String, original: String) = """{"id":"annotation-1","scope":"item","asset_id":"$asset","batch":"${"a".repeat(32)}","library_id":"family-a","author_id":"member-1","kind":"text","original_text":"$original","audio_url":null,"mime":null,"duration_ms":null,"sha256":null,"language":"en","local_processing_consent":"no","created_at":1720000000,"derivation":{"revision":1,"state":"held","transcript":null,"polished_text":null,"provider":null,"model":null,"error_code":null},"tags":[]}"""
}
