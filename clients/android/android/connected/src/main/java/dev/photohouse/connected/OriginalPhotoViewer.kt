package dev.photohouse.connected

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import androidx.compose.foundation.Image
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.HttpsPhotoHouseApi
import dev.photohouse.connected.core.PhotoViewport
import dev.photohouse.connected.core.PhotoViewportMode
import dev.photohouse.connected.core.PhotoNavigation
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import java.io.ByteArrayInputStream

internal data class DecodedPhoto(val bitmap: Bitmap, val downsampled: Boolean)
private data class DecodeResult(val complete: Boolean = false, val photo: DecodedPhoto? = null)
private val decodePermit = Semaphore(1)

/** Header-first decoding bounds the displayed bitmap to four million pixels.
 * No URI, file, EXIF location, thumbnail fallback, or persistent image cache.
 */
internal fun decodeOriginalPhoto(bytes: ByteArray): DecodedPhoto? {
    if (bytes.isEmpty() || bytes.size > HttpsPhotoHouseApi.ORIGINAL_LIMIT) return null
    return try {
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
        val width = options.outWidth; val height = options.outHeight
        if (width !in 1..32768 || height !in 1..32768 || width.toLong() * height > 256_000_000) return null
        var sample = 1
        while (((width.toLong() + sample - 1) / sample) * ((height.toLong() + sample - 1) / sample) > 4_000_000) sample *= 2
        options.inJustDecodeBounds = false
        options.inSampleSize = sample
        options.inPreferredConfig = Bitmap.Config.ARGB_8888
        val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options) ?: return null
        if (decoded.width.toLong() * decoded.height > 4_000_000) { decoded.recycle(); return null }
        val orientation = runCatching {
            ExifInterface(ByteArrayInputStream(bytes)).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)
        DecodedPhoto(orientPhoto(decoded, orientation), sample > 1)
    } catch (_: IllegalArgumentException) { null }
      catch (_: OutOfMemoryError) { null }
}

internal fun orientPhoto(bitmap: Bitmap, orientation: Int): Bitmap {
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

@OptIn(ExperimentalLayoutApi::class)
@Composable internal fun OriginalPhotoViewer(bytes: ByteArray?, loading: Boolean, zh: Boolean, onClose: () -> Unit,
    navigation: PhotoNavigation? = null, slideshow: Boolean = false,
    onAdjacent: (Int) -> Unit = {}, onToggleSlideshow: () -> Unit = {},
    onStopSlideshow: () -> Unit = {}, onAdvanceSlideshow: () -> Unit = {},
    originalQuality: Boolean = true, onOriginal: (() -> Unit)? = null,
    previewOnly: Boolean = false) {
    fun t(en: String, cn: String) = if (zh) cn else en
    val decodedState by produceState(DecodeResult(), bytes) {
        value = DecodeResult()
        if (bytes != null) value = DecodeResult(true, withContext(Dispatchers.Default) {
            decodePermit.withPermit { decodeOriginalPhoto(bytes) }
        })
    }
    // Capture one result for this composition. Reading the delegated state again
    // inside the effect could pair a new completion with the old null bitmap.
    val result = decodedState
    val photo = result.photo
    var zoom by remember(bytes) { mutableFloatStateOf(1f) }
    var offset by remember(bytes) { mutableStateOf(Offset.Zero) }
    var viewport by remember { mutableStateOf(IntSize.Zero) }
    var mode by remember(bytes) { mutableStateOf(PhotoViewportMode.FIT) }
    var fullScreen by remember { mutableStateOf(true) }
    val density = LocalDensity.current
    val currentZoom by rememberUpdatedState(zoom)
    val advance by rememberUpdatedState(onAdvanceSlideshow)
    val stop by rememberUpdatedState(onStopSlideshow)
    // Start the interval only once decoding has succeeded. No stale timer survives
    // a manual navigation, pause, byte change or removal of the private viewer.
    LaunchedEffect(slideshow, bytes, result, loading) {
        if (slideshow && result.complete && photo == null) stop()
        else if (slideshow && photo != null && !loading) { kotlinx.coroutines.delay(8000); advance() }
    }
    // The image always owns the entire window; controls never resize its viewport.
    MediaWindow(true, slideshow && photo != null && !loading)
    BackHandler(fullScreen) { fullScreen = false; onStopSlideshow() }
    fun updateZoom(factor: Float, pan: Offset = Offset.Zero) {
        if (!factor.isFinite() || !pan.x.isFinite() || !pan.y.isFinite()) return
        zoom = (zoom * factor).coerceIn(0.25f, 5f)
        val bitmap = photo?.bitmap ?: return
        val size = PhotoViewport.measure(bitmap.width.toFloat(), bitmap.height.toFloat(), viewport.width.toFloat(), viewport.height.toFloat(), mode)
        val clamped = size.clampPan(offset.x + pan.x, offset.y + pan.y, viewport.width.toFloat(), viewport.height.toFloat(), zoom)
        offset = Offset(clamped.first, clamped.second)
    }
    val transform = rememberTransformableState { zoomChange, panChange, _ -> updateZoom(zoomChange, panChange) }
    BoxWithConstraints(Modifier.fillMaxSize().testTag("original-viewer")) {
        val panelLimit = maxHeight * 0.45f
        Box(Modifier.fillMaxSize().background(Color.Black).clipToBounds().testTag("photo-viewport")
            .pointerInput(Unit) { detectTapGestures(onTap = { fullScreen = !fullScreen }) }.onSizeChanged {
            viewport = it
            photo?.let { decoded ->
                val bounds = PhotoViewport.measure(decoded.bitmap.width.toFloat(), decoded.bitmap.height.toFloat(), it.width.toFloat(), it.height.toFloat(), mode)
                val clamped = bounds.clampPan(offset.x, offset.y, it.width.toFloat(), it.height.toFloat(), zoom)
                offset = Offset(clamped.first, clamped.second)
            }
        }, contentAlignment = Alignment.Center) {
            val decoded = photo
            if (loading || !result.complete) CircularProgressIndicator()
            else if (decoded == null) Text(t("This image format or size cannot be displayed here.", "此处无法显示该图片格式或尺寸。"), color = Color.White, modifier = Modifier.padding(20.dp))
            if (decoded != null) {
            val fitted = PhotoViewport.measure(decoded.bitmap.width.toFloat(), decoded.bitmap.height.toFloat(), viewport.width.toFloat(), viewport.height.toFloat(), mode)
            // Keep layout bounded by the viewport even for very thin panoramas.
            // Scaling the complete fitted bitmap avoids huge Compose constraints.
            val layout = PhotoViewport.measure(decoded.bitmap.width.toFloat(), decoded.bitmap.height.toFloat(), viewport.width.toFloat(), viewport.height.toFloat(), PhotoViewportMode.FIT)
            val modeScale = if (layout.baseScale > 0f) fitted.baseScale / layout.baseScale else 1f
            Image(decoded.bitmap.asImageBitmap(),
                contentDescription = t("Photo. Pinch or use the zoom controls.", "照片。可双指缩放或使用缩放按钮。"),
                // Keep the full fitted bitmap in the layer. Cropping the Image
                // before translation would pan an already-clipped rectangle and
                // expose black gaps instead of revealing its hidden edges.
                contentScale = ContentScale.Fit,
                modifier = Modifier.requiredSize(with(density) { layout.width.toDp() }, with(density) { layout.height.toDp() }).testTag("original-image")
                    .graphicsLayer(scaleX = modeScale * zoom, scaleY = modeScale * zoom, translationX = offset.x, translationY = offset.y)
                    .transformable(transform)
                    .pointerInput(bytes) { detectTapGestures(onTap = { fullScreen = !fullScreen }, onDoubleTap = {
                        zoom = if (currentZoom > 1f) 1f else 2f; offset = Offset.Zero
                    }) })
            }
        }
        if (!fullScreen) Surface(
            modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().safeDrawingPadding(),
            color = MaterialTheme.colorScheme.surface.copy(alpha = 0.94f),
            tonalElevation = 3.dp
        ) {
        Column(Modifier.fillMaxWidth().heightIn(max = panelLimit).verticalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 8.dp).testTag("photo-controls")) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                TextButton(onClick = onClose) { Text(t("Close photo", "关闭照片")) }
                if (onOriginal != null && !originalQuality) TextButton(onClick = onOriginal, enabled = !loading) { Text(t("Original quality", "原图画质")) }
                TextButton(onClick = { fullScreen = true }, enabled = photo != null) { Text(t("Full screen", "全屏")) }
                TextButton(onClick = { updateZoom(1.5f) }, enabled = photo != null && zoom < 5f) { Text(t("Zoom in", "放大")) }
                TextButton(onClick = { updateZoom(1 / 1.5f) }, enabled = photo != null && zoom > 0.25f) { Text(t("Zoom out", "缩小")) }
                TextButton(onClick = { mode = PhotoViewportMode.FIT; zoom = 1f; offset = Offset.Zero }, enabled = photo != null,
                    modifier = Modifier.testTag("photo-fit-mode-fit")) { Text(t("Fit photo", "适合屏幕")) }
                TextButton(onClick = { mode = PhotoViewportMode.FILL; zoom = 1f; offset = Offset.Zero }, enabled = photo != null,
                    modifier = Modifier.testTag("photo-fit-mode-fill")) { Text(t("Fill screen", "填满屏幕")) }
                TextButton(onClick = { mode = PhotoViewportMode.FIT_WIDTH; zoom = 1f; offset = Offset.Zero }, enabled = photo != null,
                    modifier = Modifier.testTag("photo-fit-width")) { Text(t("Fit width", "适合宽度")) }
                TextButton(onClick = { mode = PhotoViewportMode.FIT_HEIGHT; zoom = 1f; offset = Offset.Zero }, enabled = photo != null,
                    modifier = Modifier.testTag("photo-fit-height")) { Text(t("Fit height", "适合高度")) }
                TextButton(onClick = { mode = PhotoViewportMode.ACTUAL_SIZE; zoom = 1f; offset = Offset.Zero }, enabled = photo != null,
                    modifier = Modifier.testTag("photo-actual-size")) { Text(t("Actual size", "实际大小")) }
            }
            Text(when {
                previewOnly -> t("Preview quality", "预览画质")
                originalQuality -> t("Original file", "原始文件")
                else -> t("Optimized display image", "高清展示图")
            }, Modifier.testTag("photo-quality"))
            if (photo != null) Text("${(zoom * 100).toInt()}%", Modifier.testTag("photo-zoom"))
            val modeLabel = when (mode) {
                PhotoViewportMode.FIT -> t("Fit · whole photo", "适合 · 完整照片")
                PhotoViewportMode.FILL -> t("Fill · edges cropped", "填满 · 边缘已裁切")
                PhotoViewportMode.FIT_WIDTH -> t("Fit width", "适合宽度")
                PhotoViewportMode.FIT_HEIGHT -> t("Fit height", "适合高度")
                PhotoViewportMode.ACTUAL_SIZE -> t("Actual size · base scale 1:1", "实际大小 · 基础比例 1:1")
            }
            Text(modeLabel, Modifier.testTag("photo-fit-mode"), style = MaterialTheme.typography.labelMedium)
            if (photo != null) {
                val scale = PhotoViewport.measure(photo.bitmap.width.toFloat(), photo.bitmap.height.toFloat(), viewport.width.toFloat(), viewport.height.toFloat(), mode).baseScale * zoom
                Text(t("Display scale ${(scale * 100).toInt()}%", "显示比例 ${(scale * 100).toInt()}%"), Modifier.testTag("photo-scale"), style = MaterialTheme.typography.labelMedium)
            }
            if (previewOnly) Text(t("Actual size uses preview pixels. Zoom does not add detail or download the original.", "实际大小按预览像素显示。缩放不会增加细节或下载原图。"))
            if (photo?.downsampled == true) Text(t("Large photo shown at reduced resolution. Actual size uses decoded pixels.", "大图已降低显示分辨率，实际大小按解码后的像素显示。"))
            navigation?.let { nav ->
                Text(t("Photo ${nav.index + 1} of ${nav.assetIds.size} · Page ${nav.page}", "第 ${nav.page} 页 · 第 ${nav.index + 1}/${nav.assetIds.size} 张"))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { onAdjacent(-1) }, enabled = !loading && nav.index > 0) { Text(t("Previous photo", "上一张")) }
                    OutlinedButton(onClick = { onAdjacent(1) }, enabled = !loading && nav.index < nav.assetIds.lastIndex) { Text(t("Next photo", "下一张")) }
                    Button(onClick = onToggleSlideshow, enabled = slideshow || !loading && photo != null && nav.index < nav.assetIds.lastIndex) {
                        Text(if (slideshow) t("Pause slideshow", "暂停幻灯片") else t("Start slideshow", "开始幻灯片"))
                    }
                }
                Text(t("8 seconds per photo on this page. Stops at videos or unavailable photos.", "本页每张照片停留 8 秒，遇到视频或不可用照片时停止。"), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
    if (fullScreen && navigation != null) Row(
        Modifier.align(Alignment.BottomCenter).widthIn(max = 560.dp).fillMaxWidth().safeDrawingPadding().padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        FilledTonalButton(onClick = { onAdjacent(-1) }, enabled = !loading && navigation.index > 0,
            modifier = Modifier.weight(1f).testTag("photo-fullscreen-previous")) { Text(t("Previous photo", "上一张")) }
        FilledTonalButton(onClick = { onAdjacent(1) }, enabled = !loading && navigation.index < navigation.assetIds.lastIndex,
            modifier = Modifier.weight(1f).testTag("photo-fullscreen-next")) { Text(t("Next photo", "下一张")) }
    }
    if (fullScreen) FilledTonalButton(onClick = { fullScreen = false; onStopSlideshow() },
        modifier = Modifier.align(Alignment.TopEnd).safeDrawingPadding().padding(12.dp).testTag("photo-exit-fullscreen")) {
        Text(t("Show controls", "显示控制"))
    }
    }
}
