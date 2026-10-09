package dev.photohouse.connected.core

import org.junit.Assert.*
import org.junit.Test

class MediaViewportTest {
    @Test fun landscapeVideoFitsInsidePortraitWithoutStretching() {
        val fitted = MediaViewport.measure(1920f, 1080f, 360f, 600f, false)
        assertEquals(360f, fitted.width, 0.001f)
        assertEquals(202.5f, fitted.height, 0.001f)
    }
    @Test fun portraitVideoFitsInsideLandscapeWithoutClipping() {
        val fitted = MediaViewport.measure(1080f, 1920f, 700f, 250f, false)
        assertEquals(140.625f, fitted.width, 0.001f)
        assertEquals(250f, fitted.height, 0.001f)
    }
    @Test fun fillPreservesAspectRatioAndPanCanReachBothCroppedEdges() {
        val fitted = MediaViewport.measure(800f, 600f, 300f, 600f, true)
        assertEquals(800f, fitted.width, 0.001f)
        assertEquals(600f, fitted.height, 0.001f)
        assertEquals(250f, fitted.panLimitX(300f, 1f), 0.001f)
        assertEquals(0f, fitted.panLimitY(600f, 1f), 0.001f)
    }
    @Test fun fitZoomPanIsClampedOnlyWhereImageExceedsViewport() {
        val fitted = MediaViewport.measure(800f, 600f, 400f, 600f, false)
        assertEquals(200f, fitted.panLimitX(400f, 2f), 0.001f)
        assertEquals(0f, fitted.panLimitY(600f, 2f), 0.001f)
    }
    @Test fun unavailableAndNonFiniteSizesDoNotReachNativeLayout() {
        for (dimension in listOf(0f, -1f, Float.NaN, Float.POSITIVE_INFINITY)) {
            assertEquals(MediaViewport(0f, 0f), MediaViewport.measure(dimension, 10f, 10f, 10f, false))
            assertEquals(MediaViewport(0f, 0f), MediaViewport.measure(10f, 10f, 10f, dimension, true))
        }
    }
}
