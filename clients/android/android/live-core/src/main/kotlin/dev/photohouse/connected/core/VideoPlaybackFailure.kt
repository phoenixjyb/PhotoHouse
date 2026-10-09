package dev.photohouse.connected.core

/** Fixed local player diagnoses. Transport authorization errors still take precedence. */
enum class VideoPlaybackFailure(val code: String, val canRetry: Boolean = false) {
    PREPARE_TIMEOUT("VIDEO-PREPARE-TIMEOUT", true),
    SEEK_TIMEOUT("VIDEO-SEEK-TIMEOUT", true),
    BUFFER_TIMEOUT("VIDEO-BUFFER-TIMEOUT", true),
    UNSUPPORTED("VIDEO-FORMAT"), DECODER("VIDEO-DECODER"), INVALID_MEDIA("VIDEO-FILE"),
    READ("VIDEO-READ", true), PLAYER("VIDEO-PLAYER"), SURFACE("VIDEO-SURFACE", true);

    fun message(zh: Boolean): String {
        val text = when (this) {
            PREPARE_TIMEOUT -> if (zh) "视频加载超时，请检查网络后重试。" else "Video loading timed out. Check your connection and retry."
            SEEK_TIMEOUT -> if (zh) "视频跳转超时，请重新打开视频。" else "Seeking timed out. Reopen the video."
            BUFFER_TIMEOUT -> if (zh) "视频缓冲超时，请检查网络后重试。" else "Video buffering timed out. Check your connection and retry."
            UNSUPPORTED -> if (zh) "此设备不支持该视频格式，请选择其他视频。" else "This device does not support this video format. Try another video."
            DECODER -> if (zh) "设备无法解码该视频，请重新打开或选择其他视频。" else "The device could not decode this video. Reopen it or try another video."
            INVALID_MEDIA -> if (zh) "无法读取该视频格式，可能需要重新准备此视频。" else "The video could not be parsed. It may need to be prepared again."
            READ -> if (zh) "视频读取中断，请检查连接后重试。" else "Video reading was interrupted. Check your connection and retry."
            PLAYER -> if (zh) "播放器无法继续，请重新打开视频。" else "Playback could not continue. Reopen the video."
            SURFACE -> if (zh) "视频画面被中断，请重新打开视频。" else "The video surface was interrupted. Reopen the video."
        }
        return "$text\n$code"
    }
}
