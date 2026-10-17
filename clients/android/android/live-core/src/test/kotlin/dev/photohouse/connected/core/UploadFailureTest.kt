package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

class UploadFailureTest {
    @Test fun classifiesApiFailureKindsAndHttpStatuses() {
        val byKind = listOf(
            ApiFailure(FailureKind.OFFLINE) to "upload:offline",
            ApiFailure(FailureKind.TLS) to "upload:tls",
            ApiFailure(FailureKind.INVALID_RESPONSE) to "upload:response",
            ApiFailure(FailureKind.INVALID_INPUT) to "upload:source",
            ApiFailure(FailureKind.TOO_LARGE) to "upload:limit",
        )
        byKind.forEach { (error, expected) -> assertEquals(expected, uploadFailureCode(error)) }

        val byStatus = listOf(
            401 to "upload:auth",
            403 to "upload:access",
            404 to "upload:access",
            408 to "upload:offline",
            409 to "upload:conflict",
            413 to "upload:limit",
            415 to "upload:media",
            429 to "upload:busy",
            500 to "upload:server",
            503 to "upload:server",
            599 to "upload:server",
            400 to "upload:unknown",
            422 to "upload:unknown",
            418 to "upload:unknown",
        )
        byStatus.forEach { (status, expected) ->
            assertEquals(expected, uploadFailureCode(ApiFailure(FailureKind.HTTP, status)))
        }
    }

    @Test fun sourceExceptionsAreClassifiedWithoutReadingTheirMessages() {
        val privateDetails = "content://provider/private/family.jpg token=synthetic-secret"
        assertEquals("upload:source", uploadFailureCode(IOException(privateDetails)))
        assertEquals("upload:source", uploadFailureCode(SecurityException(privateDetails)))
        assertEquals("upload:unknown", uploadFailureCode(IllegalStateException(privateDetails)))
        assertFalse(uploadFailureCode(IOException(privateDetails)).contains("provider"))
        assertFalse(uploadFailureCode(IOException(privateDetails)).contains("synthetic-secret"))
    }

    @Test fun messagesAreBilingualWhitelistedAndDoNotIncludeSensitiveExceptionText() {
        val codes = listOf(
            "upload:offline", "upload:tls", "upload:response", "upload:auth", "upload:access",
            "upload:media", "upload:limit", "upload:busy", "upload:server", "upload:conflict", "upload:source",
        )
        val privateDetails = "content://provider/private/photo.jpg token=synthetic-secret"
        codes.forEach { code ->
            val english = uploadFailureMessage(code, zh = false)
            val chinese = uploadFailureMessage(code, zh = true)
            assertFalse(english.isBlank())
            assertFalse(chinese.isBlank())
            assertFalse(english.contains(privateDetails))
            assertFalse(chinese.contains(privateDetails))
            assertFalse(english.contains("synthetic-secret"))
            assertFalse(chinese.contains("synthetic-secret"))
        }

        val unknownEnglish = uploadFailureMessage("provider:content://private/token=synthetic-secret", zh = false)
        val unknownChinese = uploadFailureMessage("legacy provider path: /private/photo.jpg", zh = true)
        assertEquals(uploadFailureMessage("upload:unknown", zh = false), unknownEnglish)
        assertEquals(uploadFailureMessage("upload:unknown", zh = true), unknownChinese)
        assertFalse(unknownEnglish.contains("private"))
        assertFalse(unknownEnglish.contains("synthetic-secret"))
        assertFalse(unknownChinese.contains("private"))
        assertFalse(unknownEnglish.contains("photo.jpg"))
        assertFalse(unknownChinese.contains("photo.jpg"))
        assertTrue(uploadFailureMessage("upload:offline", zh = false).contains("Confirmed progress is kept"))
        assertTrue(uploadFailureMessage("upload:offline", zh = true).contains("进度已保留"))
        assertTrue(uploadFailureMessage("upload:response", zh = false).contains("Check server status"))
        assertTrue(uploadFailureMessage("upload:response", zh = true).contains("检查服务器状态"))
        assertTrue(uploadFailureMessage("upload:source", zh = false).contains("original file is still accessible"))
        assertTrue(uploadFailureMessage("upload:source", zh = true).contains("原文件仍可访问"))
    }
}
