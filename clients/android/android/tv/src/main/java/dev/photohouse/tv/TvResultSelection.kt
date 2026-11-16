package dev.photohouse.tv

internal const val TV_RESULT_SELECTION_LIMIT = 24

/** Ordered, duplicate-safe selection for one already-authorized result page. */
internal fun toggleTvResultSelection(current: List<Int>, assetId: Int, eligible: Boolean): List<Int> {
    if (!eligible) return current
    if (assetId in current) return current.filterNot { it == assetId }
    if (current.size >= TV_RESULT_SELECTION_LIMIT) return current
    return current + assetId
}
