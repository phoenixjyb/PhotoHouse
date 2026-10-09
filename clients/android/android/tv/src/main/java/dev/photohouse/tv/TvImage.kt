package dev.photohouse.tv

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import java.io.ByteArrayInputStream
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntSize
import kotlin.math.max
import kotlin.math.min
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import dev.photohouse.home.HomeLimits
import dev.photohouse.home.HomeWire
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext

internal data class DecodedPhoto(val bitmap: Bitmap, val downsampled: Boolean)

/** Header-first decoding bounds the displayed bitmap to 8,847,360 pixels.
 * No URI, file, EXIF location, thumbnail fallback, or persistent image cache.
 */
internal fun decodeTvPhoto(bytes: ByteArray, maxPixels: Int = 8_847_360): DecodedPhoto? {
    if (bytes.isEmpty() || bytes.size > HomeLimits.DISPLAY_BYTES) return null
    return try {
        val expected = HomeWire.jpegDimensions(bytes)
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
        val width = options.outWidth; val height = options.outHeight
        if (width != expected.first || height != expected.second || width !in 1..4096 || height !in 1..4096 || width.toLong() * height > HomeLimits.DISPLAY_PIXELS) return null
        var sample = 1
        while (((width.toLong() + sample - 1) / sample) * ((height.toLong() + sample - 1) / sample) > maxPixels) sample *= 2
        options.inJustDecodeBounds = false
        options.inSampleSize = sample
        options.inPreferredConfig = Bitmap.Config.ARGB_8888
        val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options) ?: return null
        if (decoded.width.toLong() * decoded.height > maxPixels) { decoded.recycle(); return null }
        DecodedPhoto(decoded, sample > 1)
    } catch (_: Exception) { null }
      catch (_: OutOfMemoryError) { null }
}

internal fun decodeTvOriginal(bytes: ByteArray): DecodedPhoto? {
    if (bytes.isEmpty() || bytes.size > dev.photohouse.home.CatalogWire.ORIGINAL_MAX_BYTES) return null
    return try {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
        val width = options.outWidth; val height = options.outHeight
        if (width !in 1..32768 || height !in 1..32768 || width.toLong() * height > 256_000_000) return null
        var sample = 1
        while (((width.toLong() + sample - 1) / sample) * ((height.toLong() + sample - 1) / sample) > 8_847_360) sample *= 2
        options.inJustDecodeBounds = false
        options.inSampleSize = sample
        options.inPreferredConfig = Bitmap.Config.ARGB_8888
        val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options) ?: return null
        if (decoded.width.toLong() * decoded.height > 8_847_360) { decoded.recycle(); return null }
        val orientation = runCatching {
            ExifInterface(ByteArrayInputStream(bytes)).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)
        DecodedPhoto(orientTvOriginal(decoded, orientation), sample > 1)
    } catch (_: IllegalArgumentException) { null }
      catch (_: OutOfMemoryError) { null }
}

internal fun orientTvOriginal(bitmap: Bitmap, orientation: Int): Bitmap {
    val matrix = Matrix()
    when (orientation) {
        ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.setScale(-1f, 1f)
        ExifInterface.ORIENTATION_ROTATE_180 -> matrix.setRotate(180f)
        ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.setScale(1f, -1f)
        ExifInterface.ORIENTATION_TRANSPOSE -> { matrix.setRotate(90f); matrix.postScale(-1f, 1f) }
        ExifInterface.ORIENTATION_ROTATE_90 -> matrix.setRotate(90f)
        ExifInterface.ORIENTATION_TRANSVERSE -> { matrix.setRotate(-90f); matrix.postScale(-1f, 1f) }
        ExifInterface.ORIENTATION_ROTATE_270 -> matrix.setRotate(270f)
        else -> return bitmap
    }
    val oriented = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, false)
    if (oriented !== bitmap) bitmap.recycle()
    return oriented
}

private data class DecodeResult(val complete: Boolean = false, val photo: DecodedPhoto? = null)
private val decodePermit = Semaphore(1)
/** One decode at a time, off the UI thread. A new byte identity cannot show an old photo. */
@Composable internal fun TvImage(bytes: ByteArray?, description: String, modifier: Modifier = Modifier, missing: String, maxPixels: Int = 8_847_360, transform: PhotoTransform = PhotoTransform(), loading: Boolean = false, original: Boolean = false) {
    key(bytes) {
        val result by produceState(DecodeResult(complete = bytes == null)) {
            if (bytes != null) value = DecodeResult(true, withContext(Dispatchers.Default) {
                decodePermit.withPermit { if (original) decodeTvOriginal(bytes) else decodeTvPhoto(bytes, maxPixels) }
            })
        }
        var viewport by remember { mutableStateOf(IntSize.Zero) }
        Box(modifier.onSizeChanged { viewport = it }.clipToBounds(), contentAlignment = Alignment.Center) {
            val current = result.photo
            if (!result.complete || bytes == null && loading) CircularProgressIndicator()
            else if (current == null) Text(missing)
            else {
                val width = current.bitmap.width.toFloat(); val height = current.bitmap.height.toFloat()
                val fit = min(viewport.width / width, viewport.height / height)
                val fill = max(viewport.width / width, viewport.height / height)
                val scale = (if (transform.fill) fill else fit) * transform.zoom
                val x = max(0f, (width * scale - viewport.width) / 2) * transform.panX
                val y = max(0f, (height * scale - viewport.height) / 2) * transform.panY
                Image(current.bitmap.asImageBitmap(), description,
                    Modifier.matchParentSize().graphicsLayer {
                        scaleX = transform.zoom; scaleY = transform.zoom
                        translationX = x; translationY = y
                    }.testTag("tv-image"), contentScale = if (transform.fill) ContentScale.Crop else ContentScale.Fit)
            }
        }
    }
}

/** Pan is a fraction of the actual overflow; portrait and landscape cannot pan into blank edges. */
internal data class PhotoTransform(val fill: Boolean = false, val zoom: Float = 1f, val panX: Float = 0f, val panY: Float = 0f) {
    fun nextZoom() = copy(zoom = when { zoom < 2f -> 2f; zoom < 4f -> 4f; else -> 1f }, panX = 0f, panY = 0f)
    fun pan(dx: Float, dy: Float) = copy(panX = (panX + dx).coerceIn(-1f, 1f), panY = (panY + dy).coerceIn(-1f, 1f))
}
