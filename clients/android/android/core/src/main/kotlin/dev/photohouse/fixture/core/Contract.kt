package dev.photohouse.fixture.core

import dev.photohouse.protocol.Wire
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable data class FixtureCase(
    val id: String, val operation_id: String, val status: Int, val body: JsonElement? = null,
    val body_kind: String? = null, val content_type: String? = null,
    val byte_length: Int? = null, val content_range: String? = null,
)
@Serializable data class FixtureFile(
    val contract_version: String, val synthetic_only: Boolean,
    val normalization: String, val cases: List<FixtureCase>,
)
@Serializable data class ClientScenario(val id: String, val action: String, val responses: List<String>, val expected: String)
@Serializable data class ClientScenarios(
    val contract_version: String, val evidence_kind: String, val network_enabled: Boolean,
    val thumbnail_resources: Map<String, String>, val scenarios: List<ClientScenario>,
)

object Contract {
    const val VERSION = "1.0.0-fixture.1"
    val json = Wire.json
    inline fun <reified T> body(response: FixtureCase): T =
        json.decodeFromString(requireNotNull(response.body).toString())
    fun fixtures(text: String) = json.decodeFromString<FixtureFile>(text).also {
        require(it.contract_version == VERSION && it.synthetic_only)
    }
    fun scenarios(text: String) = json.decodeFromString<ClientScenarios>(text).also {
        require(it.contract_version == VERSION && !it.network_enabled)
        require(it.thumbnail_resources.values.all { path -> path in setOf("media/amber.png", "media/blue.png") })
    }
    fun passwordLengthValid(password: String) = Wire.passwordLengthValid(password)
}
