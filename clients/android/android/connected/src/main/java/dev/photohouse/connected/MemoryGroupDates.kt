package dev.photohouse.connected

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Formats recorded fields without shifting their date into the phone's timezone. */
internal fun memoryGroupRecordedDate(value: String?, zh: Boolean): String? = runCatching {
    if (value == null || value.length !in 10..64 || value.startsWith("0000-")) return@runCatching null
    val dayFormat = DateTimeFormatter.ofPattern(if (zh) "uuuu年M月d日" else "d MMM uuuu", if (zh) Locale.CHINA else Locale.ENGLISH)
    if (value.length == 10) return@runCatching LocalDate.parse(value).format(dayFormat)
    val normalized = value.replace(' ', 'T').replace(Regex("([+-][0-9]{2})([0-9]{2})$"), "$1:$2")
    val offset = runCatching { OffsetDateTime.parse(normalized) }.getOrNull()
    val wall = offset?.toLocalDateTime() ?: LocalDateTime.parse(normalized)
    val zone = offset?.offset?.let { if (it.totalSeconds == 0) " · UTC" else " · UTC$it" }.orEmpty()
    wall.toLocalDate().format(dayFormat) + " · " + wall.format(DateTimeFormatter.ofPattern("HH:mm")) + zone
}.getOrNull()
