package dev.photohouse.connected.core

interface SessionPersistence {
    fun load(): RememberedSession?
    fun save(value: RememberedSession)
    fun clear()
}

class RememberedSession(
    val accessToken: String,
    val issuedAtMillis: Long,
    val expiresAtMillis: Long,
) {
    override fun toString(): String =
        "RememberedSession(accessToken=<redacted>, issuedAtMillis=$issuedAtMillis, expiresAtMillis=$expiresAtMillis)"
}
