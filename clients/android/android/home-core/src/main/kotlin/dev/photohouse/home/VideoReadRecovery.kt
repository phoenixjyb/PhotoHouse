package dev.photohouse.home

import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull

/** Retry only transport interruptions, never server refusals or malformed media.
 * The caller freezes the asset, revision, range and response checks for every attempt.
 * Closing the owning reader cancels both the active HTTP call and retry backoff.
 */
internal suspend fun readVideoRangeWithRecovery(fetch: suspend () -> ByteArray): ByteArray =
    withTimeoutOrNull(20_000) {
        for (attempt in 0..2) {
            try { return@withTimeoutOrNull fetch() }
            catch (error: HomeFailure) {
                if (error.kind != HomeError.OFFLINE || attempt == 2) throw error
                delay(if (attempt == 0) 250 else 750)
            }
        }
        error("Video retry bound exceeded")
    } ?: throw HomeFailure(HomeError.OFFLINE)
