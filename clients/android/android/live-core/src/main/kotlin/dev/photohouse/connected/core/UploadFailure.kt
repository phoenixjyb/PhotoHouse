package dev.photohouse.connected.core

import java.io.IOException

/** A stable, content-free classification for upload failures. */
fun uploadFailureCode(error: Exception): String = when (error) {
    is ApiFailure -> when (error.kind) {
        FailureKind.OFFLINE -> "upload:offline"
        FailureKind.TLS -> "upload:tls"
        FailureKind.INVALID_RESPONSE -> "upload:response"
        FailureKind.INVALID_INPUT -> "upload:source"
        FailureKind.TOO_LARGE -> "upload:limit"
        FailureKind.HTTP -> when (error.status) {
            401 -> "upload:auth"
            403, 404 -> "upload:access"
            408 -> "upload:offline"
            409 -> "upload:conflict"
            413 -> "upload:limit"
            415 -> "upload:media"
            429 -> "upload:busy"
            in 500..599 -> "upload:server"
            else -> "upload:unknown"
        }
    }
    is IOException, is SecurityException -> "upload:source"
    else -> "upload:unknown"
}

/** Maps only known codes to user-safe copy; legacy or arbitrary strings become unknown. */
fun uploadFailureMessage(code: String?, zh: Boolean): String = when (code) {
    "upload:offline" -> if (zh)
        "网络连接中断。已确认的进度已保留，请检查网络后重试。"
    else "Network connection was interrupted. Confirmed progress is kept; check your connection and retry."

    "upload:tls" -> if (zh)
        "无法验证安全连接。请检查网络设置，稍后再试。"
    else "The secure connection could not be verified. Check your network settings and try again later."

    "upload:response" -> if (zh)
        "暂时无法确认服务器结果。请先检查服务器状态，再决定是否重试。"
    else "The server result could not be confirmed. Check server status before deciding whether to retry."

    "upload:auth" -> if (zh)
        "登录状态可能已失效。请重新登录并检查任务状态。"
    else "Your login may have expired. Sign in again and check the task status."

    "upload:access" -> if (zh)
        "当前账号无法访问此资料库或上传任务。请检查账号和资料库权限。"
    else "This account cannot access the library or upload task. Check the account and library access."

    "upload:media" -> if (zh)
        "文件内容或格式不受支持。请选择有效的 JPEG、PNG、MP4 或 MOV 文件。"
    else "The file content or format is unsupported. Choose a valid JPEG, PNG, MP4, or MOV file."

    "upload:limit" -> if (zh)
        "文件或批次超过上传大小限制。请选择较小的文件或批次。"
    else "The file or batch exceeds the upload size limit. Choose a smaller file or batch."

    "upload:busy" -> if (zh)
        "上传服务繁忙。请稍后重试；已确认的进度已保留。"
    else "The upload service is busy. Try again later; confirmed progress is kept."

    "upload:server" -> if (zh)
        "服务器暂时无法处理上传。请稍后重试；已确认的进度已保留。"
    else "The server could not process the upload right now. Try again later; confirmed progress is kept."

    "upload:conflict" -> if (zh)
        "上传状态发生变化。请先检查服务器状态，再决定是否重试。"
    else "The upload state changed. Check server status before deciding whether to retry."

    "upload:source" -> if (zh)
        "无法读取所选文件。请确认原文件仍可访问后重试。"
    else "The selected file could not be read. Confirm the original file is still accessible and retry."

    else -> if (zh)
        "上传未能完成。请检查文件访问和服务器状态，再决定是否重试。"
    else "The upload could not be completed. Check file access and server status before retrying."
}
