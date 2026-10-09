package dev.photohouse.connected.core

import dev.photohouse.protocol.*
import kotlinx.serialization.json.*

/** The protected profile evolves independently of the frozen fixture protocol. */
object ProtectedAccountWire {
    fun registration(phone: String, password: String, code: String, name: String): String {
        Admission.password(password, protectedNativeV2 = true, registration = true)
        Admission.invitationCode(code)
        return buildJsonObject {
            put("phone", Admission.phone(phone)); put("password", password)
            put("code", code); put("name", Admission.displayName(name)); put("transport", "native")
        }.toString()
    }

    fun session(body: String): Session = session(body.toByteArray(Charsets.UTF_8))

    fun session(body: ByteArray): Session {
        val value = DiscoveryJson.parse(body, maxArrayItems = 10000).jsonObject
        require(value.keys == setOf("account_id", "phone_login", "display_name", "memberships"))
        val field = value.getValue("display_name")
        val name = if (field == JsonNull) null else {
            require(field is JsonPrimitive && field.isString)
            field.content.also { require(Admission.displayName(it) == it) }
        }
        return Wire.json.decodeFromJsonElement(Session.serializer(), JsonObject(value - "display_name"))
            .copy(displayName = name)
    }
}
