package dev.photohouse.connected.core

import kotlin.math.max
import kotlin.math.min

/** Display modes for a decoded photo. Dimensions are physical display pixels. */
enum class PhotoViewportMode(val label: String) {
    FIT("Fit"),
    FILL("Fill"),
    FIT_WIDTH("Fit width"),
    FIT_HEIGHT("Fit height"),
    ACTUAL_SIZE("Actual size")
}

/** Pure geometry for the phone photo viewer. No density or Compose types belong here. */
data class PhotoViewport(
    val width: Float,
    val height: Float,
    val baseScale: Float,
    val mode: PhotoViewportMode
) {
    fun panLimitX(viewportWidth: Float, zoom: Float): Float =
        max(0f, (width * zoom - viewportWidth) / 2f)

    fun panLimitY(viewportHeight: Float, zoom: Float): Float =
        max(0f, (height * zoom - viewportHeight) / 2f)

    fun clampPan(panX: Float, panY: Float, viewportWidth: Float, viewportHeight: Float, zoom: Float): Pair<Float, Float> {
        if (!panX.isFinite() || !panY.isFinite() ||
            listOf(viewportWidth, viewportHeight, zoom).any { !it.isFinite() || it <= 0f }) return 0f to 0f
        return panX.coerceIn(-panLimitX(viewportWidth, zoom), panLimitX(viewportWidth, zoom)) to
            panY.coerceIn(-panLimitY(viewportHeight, zoom), panLimitY(viewportHeight, zoom))
    }

    companion object {
        fun measure(imageWidth: Float, imageHeight: Float, viewportWidth: Float, viewportHeight: Float,
            mode: PhotoViewportMode): PhotoViewport {
            val valid = listOf(imageWidth, imageHeight, viewportWidth, viewportHeight).all { it.isFinite() && it > 0f }
            if (!valid) return PhotoViewport(0f, 0f, 0f, mode)
            val scale = when (mode) {
                PhotoViewportMode.FIT -> min(viewportWidth / imageWidth, viewportHeight / imageHeight)
                PhotoViewportMode.FILL -> max(viewportWidth / imageWidth, viewportHeight / imageHeight)
                PhotoViewportMode.FIT_WIDTH -> viewportWidth / imageWidth
                PhotoViewportMode.FIT_HEIGHT -> viewportHeight / imageHeight
                PhotoViewportMode.ACTUAL_SIZE -> 1f
            }
            return PhotoViewport(imageWidth * scale, imageHeight * scale, scale, mode)
        }
    }
}
