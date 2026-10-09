package dev.photohouse.connected.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PhotoViewportTest {
    @Test fun fitHandlesPortraitAndLandscape() {
        val portrait = PhotoViewport.measure(1000f, 2000f, 300f, 400f, PhotoViewportMode.FIT)
        assertEquals(200f, portrait.width, 0.001f)
        assertEquals(400f, portrait.height, 0.001f)
        val landscape = PhotoViewport.measure(2000f, 1000f, 300f, 400f, PhotoViewportMode.FIT)
        assertEquals(300f, landscape.width, 0.001f)
        assertEquals(150f, landscape.height, 0.001f)
    }

    @Test fun widthHeightAndFillPreserveTheirMeaning() {
        val width = PhotoViewport.measure(2000f, 1000f, 300f, 400f, PhotoViewportMode.FIT_WIDTH)
        assertEquals(300f, width.width, 0.001f); assertEquals(150f, width.height, 0.001f)
        val height = PhotoViewport.measure(2000f, 1000f, 300f, 400f, PhotoViewportMode.FIT_HEIGHT)
        assertEquals(800f, height.width, 0.001f); assertEquals(400f, height.height, 0.001f)
        val fill = PhotoViewport.measure(2000f, 1000f, 300f, 400f, PhotoViewportMode.FILL)
        assertEquals(800f, fill.width, 0.001f); assertEquals(400f, fill.height, 0.001f)
    }

    @Test fun actualSizeIsOneDecodedPixelPerDisplayPixel() {
        val actual = PhotoViewport.measure(1200f, 800f, 300f, 400f, PhotoViewportMode.ACTUAL_SIZE)
        assertEquals(1200f, actual.width, 0.001f); assertEquals(800f, actual.height, 0.001f); assertEquals(1f, actual.baseScale, 0.001f)
    }

    @Test fun oversizePanIsBoundedAndInvalidInputsAreSafe() {
        val actual = PhotoViewport.measure(1200f, 800f, 300f, 400f, PhotoViewportMode.ACTUAL_SIZE)
        assertEquals(450f to -200f, actual.clampPan(999f, -999f, 300f, 400f, 1f))
        val invalid = PhotoViewport.measure(0f, 800f, 300f, 400f, PhotoViewportMode.FIT)
        assertTrue(invalid.width == 0f && invalid.height == 0f)
        assertEquals(0f to 0f, actual.clampPan(Float.NaN, 0f, 300f, 400f, 1f))
        assertEquals(0f to 0f, actual.clampPan(1f, 1f, 300f, 400f, 0f))
    }

    @Test fun physicalPixelGeometryIsIndependentOfDensityAndThinPanoramasHaveBoundedFitLayout() {
        val actual = PhotoViewport.measure(900f, 1200f, 1080f, 1700f, PhotoViewportMode.ACTUAL_SIZE)
        assertEquals(900f, actual.width, 0f)
        assertEquals(1200f, actual.height, 0f)
        val fit = PhotoViewport.measure(32768f, 1f, 1080f, 1700f, PhotoViewportMode.FIT)
        val fill = PhotoViewport.measure(32768f, 1f, 1080f, 1700f, PhotoViewportMode.FILL)
        assertTrue(fit.width <= 1080f && fit.height <= 1700f)
        assertEquals(1700f, fit.height * (fill.baseScale / fit.baseScale), 0.01f)
        assertEquals(0f, fill.panLimitY(1700f, 1f), 0f)
    }
}
