package dev.photohouse.tv

/** Only fixed labels and native numeric codes leave the player; never exception messages/URLs. */
internal data class TvPlaybackFailure(val stage: Stage, val what: Int? = null, val extra: Int? = null) {
    enum class Stage { SETUP, NATIVE, PREPARE_TIMEOUT, SEEK_TIMEOUT, REBUFFER_TIMEOUT, CONTROL, SURFACE }
    val code: String get() = "TV-${stage.name}" + if (stage == Stage.NATIVE) " (${what ?: 0}, ${extra ?: 0})" else ""
    fun message(zh: Boolean): String {
        val text = when (stage) {
            Stage.SURFACE -> if (zh) "视频画面被中断，请重新打开视频。" else "The video surface was interrupted. Reopen the video."
            Stage.PREPARE_TIMEOUT -> if (zh) "视频加载超时。请重试。" else "Video preparation timed out. Please retry."
            Stage.SEEK_TIMEOUT -> if (zh) "视频定位超时。请重试。" else "Video seeking timed out. Please retry."
            Stage.REBUFFER_TIMEOUT -> if (zh) "视频缓冲超时。请重试。" else "Video buffering timed out. Please retry."
            Stage.SETUP -> if (zh) "无法启动电视播放器。" else "The TV player could not start."
            Stage.CONTROL -> if (zh) "电视播放器操作失败。请重新打开视频。" else "The TV player could not complete the action. Reopen the video."
            Stage.NATIVE -> when (nativeKind(extra ?: what)) {
                NativeKind.UNSUPPORTED -> if (zh) "电视播放器不支持此视频格式。" else "The TV player does not support this video format."
                NativeKind.DECODER -> if (zh) "电视播放器无法解码此视频。" else "The TV player could not decode this video."
                NativeKind.INVALID -> if (zh) "视频文件无效或已损坏。" else "The video file is invalid or malformed."
                NativeKind.IO -> if (zh) "播放器无法读取视频。" else "The player could not read the video."
                NativeKind.OTHER -> if (zh) "电视播放器报告播放失败。" else "The TV player reported a playback failure."
            }
        }
        return "$text\n$code"
    }

    private enum class NativeKind { UNSUPPORTED, DECODER, INVALID, IO, OTHER }

    /** Media3 error-code families are stable and avoid interpreting legacy MediaPlayer negatives. */
    private fun nativeKind(code: Int?): NativeKind = when {
        code == null -> NativeKind.OTHER
        code == androidx.media3.common.PlaybackException.ERROR_CODE_PARSING_CONTAINER_UNSUPPORTED ||
            code == androidx.media3.common.PlaybackException.ERROR_CODE_PARSING_MANIFEST_UNSUPPORTED ||
            code == androidx.media3.common.PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED ||
            code == androidx.media3.common.PlaybackException.ERROR_CODE_DECODING_FORMAT_EXCEEDS_CAPABILITIES -> NativeKind.UNSUPPORTED
        code == androidx.media3.common.PlaybackException.ERROR_CODE_DECODER_INIT_FAILED ||
            code == androidx.media3.common.PlaybackException.ERROR_CODE_DECODER_QUERY_FAILED ||
            code == androidx.media3.common.PlaybackException.ERROR_CODE_DECODING_FAILED ||
            code == androidx.media3.common.PlaybackException.ERROR_CODE_AUDIO_TRACK_INIT_FAILED ||
            code == androidx.media3.common.PlaybackException.ERROR_CODE_AUDIO_TRACK_WRITE_FAILED -> NativeKind.DECODER
        code == androidx.media3.common.PlaybackException.ERROR_CODE_PARSING_CONTAINER_MALFORMED ||
            code == androidx.media3.common.PlaybackException.ERROR_CODE_PARSING_MANIFEST_MALFORMED -> NativeKind.INVALID
        code in 2000..2999 -> NativeKind.IO
        else -> NativeKind.OTHER
    }
}
