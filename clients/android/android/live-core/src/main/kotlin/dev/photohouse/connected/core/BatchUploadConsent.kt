package dev.photohouse.connected.core

enum class BatchUploadStartDecision {
    START,
    REQUIRE_NETWORK_REVIEW,
    ACKNOWLEDGE_NETWORK_REVIEW,
}

/** Decide whether the latest user action may start a batch on the current network. */
fun batchUploadStartDecision(
    network: UploadNetwork,
    networkApproved: Boolean,
    confirmationVisible: Boolean,
): BatchUploadStartDecision {
    if (network == UploadNetwork.UNMETERED || networkApproved) return BatchUploadStartDecision.START
    return if (confirmationVisible) BatchUploadStartDecision.ACKNOWLEDGE_NETWORK_REVIEW
    else BatchUploadStartDecision.REQUIRE_NETWORK_REVIEW
}
