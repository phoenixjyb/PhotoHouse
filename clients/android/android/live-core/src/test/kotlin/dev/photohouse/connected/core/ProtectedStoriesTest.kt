package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Test

class ProtectedStoriesTest {
    private val valid = """{"asset_id":"42","library_id":"family","page":1,"can_create":false,"has_more":false,"items":[]}"""
    private fun invalid(body: String) {
        val error = runCatching { ProtectedStoriesWire.parse(body.toByteArray(), "family", "42", 1) }.exceptionOrNull()
        assertEquals(FailureKind.INVALID_RESPONSE, (error as? ApiFailure)?.kind)
    }
    @Test fun parsesPinnedFamilyStoryShape() {
        val json = """
            {"asset_id":"42","library_id":"family","page":1,"can_create":true,"has_more":false,"items":[
              {"asset_id":"42","author_id":"123e4567-e89b-12d3-a456-426614174000","byline":"Mom","can_edit":true,"can_view_history":true,"created_at":10,"deleted":false,"id":"123e4567-e89b-12d3-a456-426614174001","language":"en","revision":1,"source":"family","text":"A literal story","title":"Trip","updated_at":11}
            ]}
        """.trimIndent().toByteArray()
        val result = ProtectedStoriesWire.parse(json, "family", "42", 1)
        assertEquals("A literal story", result.items.single().text)
        assertEquals(1L, result.items.single().revision)
    }

    @Test fun rejectsDuplicateStoryIdsAndWrongTypes() {
        val story = """{"asset_id":"42","author_id":"123e4567-e89b-12d3-a456-426614174000","byline":"","can_edit":false,"can_view_history":false,"created_at":0,"deleted":false,"id":"123e4567-e89b-12d3-a456-426614174001","language":"und","revision":1,"source":"family","text":"x","title":"","updated_at":0}"""
        val body = """{"asset_id":"42","library_id":"family","page":1,"can_create":false,"has_more":false,"items":[$story,$story]}"""
        invalid(body)
        invalid(valid.replace("\"page\":1", "\"page\":\"1\""))
        val one = valid.replace("[]", "[$story]")
        for (bad in listOf(story.replace("\"deleted\":false","\"deleted\":true"),
            story.replace("\"source\":\"family\"","\"source\":\"ai\""),
            story.replace("\"text\":\"x\"","\"text\":\""+"x".repeat(65537)+"\""),
            story.replace("\"text\":\"x\"","\"text\":\"\\uD800\""))) invalid(one.replace(story,bad))
        val boundary = one.replace("\"text\":\"x\"","\"text\":\""+"x".repeat(65536)+"\"")
        assertEquals(65536,ProtectedStoriesWire.parse(boundary.toByteArray(),"family","42",1).items.single().text.length)
        val six = (1..6).joinToString(",") { story.replace("426614174001", "42661417400$it") }
        invalid(valid.replace("[]","[$six]"))
    }

    @Test fun rejectsWrongScopeDuplicateKeysInvalidUtf8AndSurrogateEscapes() {
        invalid(valid.replace("family", "other"))
        invalid("""{"asset_id":"42","library_id":"family","page":1,"page":1,"can_create":false,"has_more":false,"items":[]}""")
        val invalidUtf8 = byteArrayOf('{'.code.toByte(), '"'.code.toByte(), 'x'.code.toByte(), '"'.code.toByte(), ':'.code.toByte(), -0x40, '}'.code.toByte())
        val utfError = runCatching { ProtectedStoriesWire.parse(invalidUtf8, "family", "42", 1) }.exceptionOrNull()
        assertEquals(FailureKind.INVALID_RESPONSE, (utfError as? ApiFailure)?.kind)
        invalid(valid.dropLast(1) + "\uD800" + "}")
    }
}
