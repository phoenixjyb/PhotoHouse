package dev.photohouse.connected

import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises the same pending-selection effect used by both actual SAF callbacks. Synthetic data only. */
@RunWith(AndroidJUnit4::class)
class BatchPickerRecoveryUiTest {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()

    @Test fun folderWaitsForSessionAndGalleryThenKeepsItsOriginalDestination() {
        val selection = mutableStateOf<BatchPickerSelection<String>?>(BatchPickerSelection("a", "trip", "opaque-uri"))
        val covered = mutableStateOf(true)
        val busy = mutableStateOf(true)
        val account = mutableStateOf<String?>(null)
        var reads = 0
        var reviews = 0
        var reviewedDestination: String? = null
        rule.setContent {
            BatchPickerSelectionEffect(selection.value, account.value, covered.value, busy.value, 2,
                setOf("trip", "other"), load = { reads++; "three-supported-items" },
                onReady = { pending, result ->
                    assertEquals("three-supported-items", result)
                    reviewedDestination = pending.destination; reviews++; selection.value = null
                }, onDiscard = { selection.value = null })
        }
        rule.runOnIdle { assertEquals(0, reads); assertEquals(0, reviews) }
        // Both transport attempts failed: explicit Retry must still keep the opaque selection.
        rule.runOnIdle { busy.value = false }
        rule.runOnIdle { assertEquals(0, reads); assertEquals(true, selection.value != null) }
        // Retry succeeds; session is valid, but restoring the gallery is still in progress.
        rule.runOnIdle { account.value = "a"; covered.value = false; busy.value = true }
        rule.runOnIdle { assertEquals(0, reads); assertEquals(true, selection.value != null); busy.value = false }
        rule.waitUntil(5_000) { reviews == 1 }
        rule.runOnIdle { assertEquals(1, reads); assertEquals("trip", reviewedDestination); assertEquals(null, selection.value) }
    }

    @Test fun logoutDiscardsWithoutReading() = rejected(null, setOf("trip"))
    @Test fun anotherAccountDiscardsWithoutReading() = rejected("b", setOf("trip"))
    @Test fun revokedDestinationDiscardsWithoutReading() = rejected("a", setOf("other"))

    private fun rejected(newAccount: String?, libraries: Set<String>) {
        val covered = mutableStateOf(true)
        var reads = 0
        var discarded = 0
        rule.setContent {
            BatchPickerSelectionEffect(BatchPickerSelection("a", "trip", "opaque-uri"), newAccount,
                covered.value, false, 2, libraries, load = { reads++; "items" },
                onReady = { _, _ -> throw AssertionError("Stale picker result must not open review") },
                onDiscard = { discarded++ })
        }
        rule.runOnIdle { assertEquals(0, reads); assertEquals(0, discarded); covered.value = false }
        rule.waitUntil(5_000) { discarded == 1 }
        rule.runOnIdle { assertEquals(0, reads) }
    }

    @Test fun backgroundDuringSlowProviderReadCannotResurrectReview() {
        val covered = mutableStateOf(false)
        val generation = mutableStateOf(1L)
        val selection = mutableStateOf<BatchPickerSelection<String>?>(BatchPickerSelection("a", "trip", "opaque-uri"))
        val gate = CompletableDeferred<Unit>()
        var reads = 0
        var reviews = 0
        rule.setContent {
            BatchPickerSelectionEffect(selection.value, "a", covered.value, false, generation.value, setOf("trip"),
                load = {
                    reads++
                    // Simulate a provider that completes late despite cancellation.
                    if (reads == 1) withContext(NonCancellable) { gate.await() }
                    "items"
                }, onReady = { _, _ -> reviews++; selection.value = null },
                onDiscard = { selection.value = null })
        }
        rule.waitUntil(5_000) { reads == 1 }
        rule.runOnIdle { covered.value = true; generation.value++ }
        rule.runOnIdle { gate.complete(Unit) }
        rule.runOnIdle { assertEquals(0, reviews); assertEquals(true, selection.value != null) }
        rule.runOnIdle { covered.value = false }
        rule.waitUntil(5_000) { reviews == 1 }
        rule.runOnIdle { assertEquals(2, reads); assertEquals(null, selection.value) }
    }
}
