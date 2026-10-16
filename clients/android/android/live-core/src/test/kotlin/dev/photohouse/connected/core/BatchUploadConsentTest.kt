package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Test

class BatchUploadConsentTest {
    @Test fun unmeteredNetworkStartsWithoutReview() {
        assertEquals(BatchUploadStartDecision.START,
            batchUploadStartDecision(UploadNetwork.UNMETERED, networkApproved = false, confirmationVisible = false))
        assertEquals(BatchUploadStartDecision.START,
            batchUploadStartDecision(UploadNetwork.UNMETERED, networkApproved = false, confirmationVisible = true))
    }

    @Test fun staleStartOnMeteredOrUnknownNetworkRequiresReview() {
        for (network in listOf(UploadNetwork.METERED, UploadNetwork.UNKNOWN)) {
            assertEquals(BatchUploadStartDecision.REQUIRE_NETWORK_REVIEW,
                batchUploadStartDecision(network, networkApproved = false, confirmationVisible = false))
        }
    }

    @Test fun visibleContinueAcknowledgesButDoesNotStart() {
        for (network in listOf(UploadNetwork.METERED, UploadNetwork.UNKNOWN)) {
            assertEquals(BatchUploadStartDecision.ACKNOWLEDGE_NETWORK_REVIEW,
                batchUploadStartDecision(network, networkApproved = false, confirmationVisible = true))
        }
    }

    @Test fun priorApprovalAllowsStartOnMeteredOrUnknownNetwork() {
        for (network in listOf(UploadNetwork.METERED, UploadNetwork.UNKNOWN)) {
            assertEquals(BatchUploadStartDecision.START,
                batchUploadStartDecision(network, networkApproved = true, confirmationVisible = false))
            assertEquals(BatchUploadStartDecision.START,
                batchUploadStartDecision(network, networkApproved = true, confirmationVisible = true))
        }
    }
}
