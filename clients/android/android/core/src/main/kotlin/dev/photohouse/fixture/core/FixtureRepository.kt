package dev.photohouse.fixture.core

import dev.photohouse.protocol.*
import kotlinx.coroutines.delay

/** The only adapter in this project. Case IDs are local demo controls, never API fields. */
interface FixtureRepository {
    suspend fun response(caseId: String): FixtureCase
    fun thumbnail(path: String): ByteArray?
}

class BundledFixtureRepository(
    fixtureText: String,
    scenarioText: String,
    private val readAsset: (String) -> ByteArray,
    private val latencyMillis: Long = 150,
) : FixtureRepository {
    private val cases = Contract.fixtures(fixtureText).cases.associateBy { it.id }
    private val resources = Contract.scenarios(scenarioText).thumbnail_resources
    override suspend fun response(caseId: String): FixtureCase {
        delay(latencyMillis)
        return requireNotNull(cases[caseId]) { "Unknown synthetic case" }
    }
    override fun thumbnail(path: String): ByteArray? = resources[path]?.let(readAsset)
}

object DemoInputs {
    const val PHONE = "+12025550102"
    const val INVITED_PHONE = "+12025550103"
    const val PASSWORD = "synthetic-demo-only"
    const val INVITATION = "SYNTHETIC-INVITE-ONLY"
    // There are no editable credential fields: buttons use only these reserved inputs.
    fun login() = LoginRequest(PHONE, PASSWORD)
    fun register() = RegisterRequest(INVITED_PHONE, PASSWORD, INVITATION)
}
