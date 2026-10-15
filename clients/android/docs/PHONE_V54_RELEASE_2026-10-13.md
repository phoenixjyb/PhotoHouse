# Phone v54 and voice presence API/Web delivery

## Release identity

October 13 source: `52c4c8134e13459e4e353efe0755bf1c32e90df7`.
Phone `dev.photohouse.connected`: version 54 / `0.54-voice-presence`.
The original signing certificate and launcher icon pixels are unchanged.

| Artifact | SHA-256 | Bytes |
|---|---|---|
| API/Web source ZIP | `f1e2e3cdb0632f83d4a646a5324317ba5736dc316ba023796c2f611d7e67c290` | 3,352,474 |
| Unsigned phone APK | `83ec73b4e9741a6bd5bceb7fcc974138f0287b3e484a96b3970718142c5b3999` | 11,479,241 |
| Published signed phone APK | `77fef88bd684113f53c0d088363b5eaa7b19f499fafa1ebcc64dd78298d368fe` | 11,499,896 |

Certificate SHA-256:
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.

## Changes

The [voice presence card](../../../docs/ASSISTANT_VOICE_PRESENCE.md) shows idle
microphone-off readiness, opening the microphone, confirmed listening,
recognition, search, preparing speech, actual playback, and pause. Start, Pause
and End remain explicit. Platform start observations are accepted only for the
current foreground session and operation. Motion is decorative and respects
reduced-motion settings.

## Evidence

- Local foreground Web voice and manual transcript journeys passed. Phone and
  desktop renders, including 150% text, were inspected.
- Android core: 915 passing tests; connected unit: 17 passing tests. Three
  generated emulator voice-workspace cases passed. These are overlapping local
  cohorts, not new physical microphone/speaker evidence.
- The fixed v54 APK passed the offline release build, lint, shared resource and
  package/icon checks. The delivery controllers passed 23 local guard checks.
- All 194 packaged server files matched their manifest; local and Windows
  qualification each passed 11 synthetic scenarios. The native child had a
  five-minute, 2 GiB, eight-process bound and an 8 GiB free-RAM floor.
- Eight native release controllers parsed successfully; 13 local release
  protections passed. Full preflight ran before service control. At 11:19 UTC,
  the new API/Web source was verified and five upload workers restored.
- A fresh stopped-writer backup passed four database integrity checks. Schema
  stays `a0c9d2e4f817`, configuration bytes are unchanged, and the ASR/TTS/OCR
  processes were independently verified as preserved. Eight required tasks
  remained running and enabled.
- Eight served Web resources matched the fixed package over trusted HTTPS.
- Original-certificate signing preserved DEX content. Native complete HTTPS
  APK readback passed; publication restarted no API or worker. TV stays v30.
- Independent Mac verification read all 11,499,896 bytes in 44 ordered HTTPS
  ranges over a persistent connection, in 9.83 seconds. The SHA-256 matched and
  both feed responses stayed unchanged. An earlier independent range attempt
  encountered a TLS connection reset; its failure record is preserved. The
  final verification made no reconnections and did not replay publication.

Physical phone installation, audible speech, microphone quality and family
acceptance remain pending owner testing. No new provider or model was activated.

## Owner test

1. Use “检查更新” to install v54, then enter 拾光助手 with a selected library.
2. Before Start, confirm the card says the microphone is off.
3. Start voice mode. Wait for “正在聆听” before asking to find photos.
4. Confirm the card changes through recognition/search and preparing speech;
   “正在说话” should appear when playback actually starts.
5. After the reply ends, confirm the next listening turn begins. Tap Pause and
   End separately; recording must stop immediately. Leaving the foreground or
   changing account/library must not resume an old session automatically.
6. Refresh WebUI and check the same visible phases and controls.
