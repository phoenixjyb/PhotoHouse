package dev.photohouse.connected.core

/** Exact spoken controls accepted only inside an explicitly started voice session. */
internal enum class VoiceSessionSpokenControl { PAUSE, END, CONTINUE_READING }

internal fun classifyVoiceSessionSpokenControl(text: String): VoiceSessionSpokenControl? {
    val normalized = text.trim().asciiLowercase().trimEnd('.', '!', '?', '。', '！', '？')
    return when (normalized) {
        "暂停", "暂停聆听", "暂停语音", "pause", "pause listening", "pause voice chat", "pause voice search", "stop" ->
            VoiceSessionSpokenControl.PAUSE
        "结束", "结束语音", "结束对话", "停止聆听", "end voice chat", "end voice search", "stop listening" ->
            VoiceSessionSpokenControl.END
        "继续朗读", "继续读", "读下一段", "continue reading", "read the next part", "read the next segment" ->
            VoiceSessionSpokenControl.CONTINUE_READING
        else -> null
    }
}

private fun String.asciiLowercase(): String = buildString(length) {
    for (character in this@asciiLowercase) {
        append(if (character in 'A'..'Z') character + ('a' - 'A') else character)
    }
}
