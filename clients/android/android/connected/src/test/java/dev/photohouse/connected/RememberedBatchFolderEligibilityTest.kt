package dev.photohouse.connected

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RememberedBatchFolderEligibilityTest {
    private val saved = RememberedBatchFolder("account-a", "family-a", "content://provider/tree/root")

    @Test fun requiresTheExactCurrentAccountDestinationForegroundAndPersistedGrant() {
        assertTrue(canReviewRememberedBatchFolder(saved, "account-a", covered = false, busy = false,
            availableLibraries = setOf("family-a", "family-b"), persistedReadGrant = true))
        assertFalse(canReviewRememberedBatchFolder(saved, "account-b", false, false,
            setOf("family-a"), true))
        assertFalse(canReviewRememberedBatchFolder(saved, "account-a", false, false,
            setOf("family-b"), true))
        assertFalse(canReviewRememberedBatchFolder(saved, "account-a", false, false,
            setOf("family-a"), false))
        assertFalse(canReviewRememberedBatchFolder(saved, "account-a", covered = true, busy = false,
            availableLibraries = setOf("family-a"), persistedReadGrant = true))
        assertFalse(canReviewRememberedBatchFolder(saved, "account-a", covered = false, busy = true,
            availableLibraries = setOf("family-a"), persistedReadGrant = true))
        assertFalse(canReviewRememberedBatchFolder(null, "account-a", false, false,
            setOf("family-a"), true))
    }
}
