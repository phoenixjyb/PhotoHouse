package dev.photohouse.home

/** Pinned home v3 browsing extension. Never sent to protected phone routes. */
enum class Availability(val wire: String) { ALL("all"), READY("ready") }
enum class BrowseOrder(val wire: String) { CATALOG("catalog"), READY_FIRST("ready_first") }
enum class BrowseMedia(val wire: String) { ALL("all"), PHOTOS("photo"), VIDEOS("video") }
data class BrowseSelection(val availability: Availability = Availability.ALL,
    val order: BrowseOrder = BrowseOrder.CATALOG, val media: BrowseMedia = BrowseMedia.ALL,
    val collectionId: String? = null) {
    init { require(collectionId == null || collectionId.matches(Regex("[a-z0-9-]{1,64}"))) }
    fun query() = "&browse=1&availability=${availability.wire}&order=${order.wire}&media=${media.wire}" +
        (collectionId?.let { "&collection=$it" } ?: "")
}
data class HomeCollection(val id: String, val title: String, val mediaCount: Int, val photoCount: Int, val videoCount: Int)
data class HomeCollections(val revision: Int, val collections: List<HomeCollection>)
data class BrowseCounts(val ready: Int, val matching: Int)
fun HomeAsset.deliveryReady() = when (kind) {
    AssetKind.PHOTO -> display != null || original != null
    AssetKind.VIDEO -> video != null
    else -> false
}
