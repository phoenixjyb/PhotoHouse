package dev.photohouse.connected.core

import kotlin.math.max
import kotlin.math.min

/** The same geometry drives a touch photo's pan limits and the native video surface. */
data class MediaViewport(val width: Float, val height: Float) {
    fun panLimitX(viewportWidth: Float, zoom: Float) = max(0f, (width * zoom - viewportWidth) / 2f)
    fun panLimitY(viewportHeight: Float, zoom: Float) = max(0f, (height * zoom - viewportHeight) / 2f)

    companion object {
        fun measure(mediaWidth: Float, mediaHeight: Float, viewportWidth: Float, viewportHeight: Float, fill: Boolean): MediaViewport {
            if (listOf(mediaWidth, mediaHeight, viewportWidth, viewportHeight).any { !it.isFinite() || it <= 0 }) return MediaViewport(0f, 0f)
            val scale = if (fill) max(viewportWidth / mediaWidth, viewportHeight / mediaHeight)
                else min(viewportWidth / mediaWidth, viewportHeight / mediaHeight)
            return MediaViewport(mediaWidth * scale, mediaHeight * scale)
        }
    }
}
