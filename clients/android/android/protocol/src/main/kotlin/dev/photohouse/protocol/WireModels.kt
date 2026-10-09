package dev.photohouse.protocol

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

// Names intentionally match the frozen wire fields. Optional date hints are
// requested only by newer connected clients and do not replace taken_at.
@Serializable data class SessionToken(val expires_in: Long, val access_token: String, val token_type: String)
@Serializable data class Session(val account_id: String, val phone_login: String, val memberships: List<Membership>,
    @kotlinx.serialization.Transient val displayName: String? = null)
@Serializable data class Membership(
    val library_id: String, val status: String, val role: String, val revision: Long,
    val expires_at: Long?, val originals: Int, val available: Boolean,
)
@Serializable data class Asset(
    val id: String, val kind: String, val width: Int?, val height: Int?,
    val duration_sec: Double?, val taken_at: String?, val thumbnail_url: String,
    val date_hint: DateHint? = null,
) {
    init { require(id.matches(Regex("[1-9][0-9]{0,18}")) && id.toLongOrNull() != null) }
}
@Serializable data class DateHint(val value: String, val source: String) {
    init {
        require(value.length in 10..64 && source in setOf("filename", "received"))
    }
}
@Serializable data class Gallery(
    val library_id: String, val page: Int, val page_size: Int, val total: Long,
    val originals_allowed: Boolean, val items: List<Asset>,
)
@Serializable data class Detail(val library_id: String, val originals_allowed: Boolean, val asset: Asset)
@Serializable data class Caption(
    val id: String, val text: String, val truncated: Boolean, val user_edited: Boolean,
    val created_at: String?, val updated_at: String?,
)
@Serializable data class Captions(
    val library_id: String, val asset_id: String, val has_more: Boolean, val items: List<Caption>,
)
@Serializable data class Ok(val ok: Boolean)
@Serializable data class LoginRequest(val phone: String, val password: String, val transport: String = "native")
@Serializable data class RegisterRequest(val phone: String, val password: String, val code: String, val transport: String = "native")
@Serializable data class AcceptRequest(val code: String)

object Wire {
    val json = Json { ignoreUnknownKeys = false; encodeDefaults = true }
    fun passwordLengthValid(password: String) = password.codePointCount(0, password.length) in 15..128
}
