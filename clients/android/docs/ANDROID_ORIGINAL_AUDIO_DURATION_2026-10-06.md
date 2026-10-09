# Original recording duration

Source base: `dbd8d4a`; next-release phone source only.

Story contributions and memoir source inspection now display recording duration
in seconds with at most one decimal place. Short recordings retain their useful
fractional duration (for example, 1.2 seconds); missing duration is omitted.
This presentation change does not modify recordings, receipts or consent.

The existing synthetic audio-inspection emulator journey passed at 150% text
size, including explicit loading/playback, recording blocking playback, and
closing the original audio. Its rendered component capture was inspected and
shows `1.2 秒`. Kotlin and Android-test compilation passed in that run. No live
provider, physical device or server was exercised. Earlier lint evidence covers
the preceding source increment; lint was not repeated for this wording change.
