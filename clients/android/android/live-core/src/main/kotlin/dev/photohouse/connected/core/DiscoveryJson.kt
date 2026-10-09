package dev.photohouse.connected.core

import kotlinx.serialization.json.*
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction

/** Bounded parser shared in behavior with HomeWire; no anonymous transport dependency. */
internal object DiscoveryJson {
    private fun bad(): Nothing = throw ApiFailure(FailureKind.INVALID_RESPONSE)
    private fun check(ok: Boolean) { if (!ok) bad() }
    /** Small bounded JSON reader: rejects duplicate keys, deep nesting and invalid UTF-8. */
    internal fun parse(bytes: ByteArray, limit: Int = HttpsPhotoHouseApi.JSON_LIMIT, maxArrayItems: Int = 100): JsonElement {
        check(bytes.size in 1..limit)
        val s = Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
        var i = 0; var nodes = 0
        fun ws() { while (i < s.length && s[i] in " \t\r\n") i++ }
        fun string(): JsonPrimitive {
            val start = i++; var escaped = false
            while (i < s.length) {
                val c = s[i++]
                if (!escaped && c == '"') {
                    val p = Json.parseToJsonElement(s.substring(start, i)) as JsonPrimitive
                    // JSON escapes may encode lone UTF-16 surrogates; never replace them silently.
                    Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(p.content))
                    return p
                }
                if (!escaped && c == '\\') escaped = true else escaped = false
            }
            bad()
        }
        fun value(depth: Int): JsonElement {
            check(depth <= 8 && ++nodes <= 10000); ws(); check(i < s.length)
            if (s[i] == '"') return string()
            if (s[i] == '{') {
                i++; ws(); val map = linkedMapOf<String, JsonElement>()
                if (i < s.length && s[i] == '}') { i++; return JsonObject(map) }
                while (true) {
                    ws(); check(i < s.length && s[i] == '"'); val key = string().content
                    check(key !in map); ws(); check(i < s.length && s[i++] == ':'); map[key] = value(depth + 1)
                    ws(); check(i < s.length); if (s[i] == '}') { i++; break }; check(s[i++] == ',')
                }
                return JsonObject(map)
            }
            if (s[i] == '[') {
                i++; ws(); val list = mutableListOf<JsonElement>()
                if (i < s.length && s[i] == ']') { i++; return JsonArray(list) }
                while (true) {
                    check(list.size < maxArrayItems); list += value(depth + 1); ws(); check(i < s.length)
                    if (s[i] == ']') { i++; break }; check(s[i++] == ',')
                }
                return JsonArray(list)
            }
            val start = i
            while (i < s.length && s[i] !in ",]} \t\r\n") i++
            check(i > start); return Json.parseToJsonElement(s.substring(start, i))
        }
        val result = value(0); ws(); check(i == s.length); return result
    }
}
