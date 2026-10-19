package dev.photohouse.connected

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberUpdatedState
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

/** Opaque picker result; no filenames or bytes are read until access is revalidated. */
internal data class BatchPickerSelection<T>(val account: String, val destination: String?, val value: T,
    val persistedReadAccess: Boolean = true)

/** Wait across same-account session recovery; never read or publish across an access change. */
@Composable
internal fun <T, R> BatchPickerSelectionEffect(
    selection: BatchPickerSelection<T>?, account: String?, covered: Boolean, busy: Boolean,
    generation: Long, availableLibraries: Set<String>,
    load: suspend (T) -> R, onReady: (BatchPickerSelection<T>, R) -> Unit, onDiscard: () -> Unit,
) {
    val currentLoad = rememberUpdatedState(load)
    val currentReady = rememberUpdatedState(onReady)
    val currentDiscard = rememberUpdatedState(onDiscard)
    LaunchedEffect(selection, account, covered, busy, generation, availableLibraries) {
        val pending = selection ?: return@LaunchedEffect
        if (covered) return@LaunchedEffect
        if (account != pending.account) { currentDiscard.value(); return@LaunchedEffect }
        if (busy) return@LaunchedEffect
        if (pending.destination != null && pending.destination !in availableLibraries) {
            currentDiscard.value(); return@LaunchedEffect
        }
        val result = currentLoad.value(pending.value)
        // A background, account, membership or generation change cancels this effect.
        currentCoroutineContext().ensureActive()
        currentReady.value(pending, result)
    }
}
