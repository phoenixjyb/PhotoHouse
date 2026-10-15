# Phone v53 and grounded voice API/Web delivery

## Release identity

The October 13 delivery uses source `5f92b94c9ecae090e75d69d9ac6f74df2eeba75a`.
Phone `dev.photohouse.connected` is version 53 / `0.53-grounded-voice`.
It includes current-result introductions, recorded-date follow-ups and the
preceding voice reliability fixes. The original icon pixels are unchanged.
The earlier v52 candidate remains preserved and unpublished.

| Artifact | SHA-256 | Bytes |
|---|---|---|
| API/Web source ZIP | `2050b8f05d787399f521051380b45cab7046ebf70faa6b0bf5a785ae979746cb` | 3,346,165 |
| Unsigned phone APK | `8b5f04d62a2d2994cd8c9289656a468724a3f0e8748dee2de00b1bff05e842bc` | 11,471,149 |
| Published signed phone APK | `447b6a2244ed1a4fef450cc313f76bfff7d04e4945eef7e5aa7565bb0ac4a18e` | 11,491,704 |

Signer certificate SHA-256:
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.

## Evidence and delivery scope

- Local backend assistant checks: 155 passed, one external-adapter skip.
- Phone offline build, release lint and JVM checks: 940 passed; icon and package
  identity verified. These counts include existing tests.
- Windows synthetic qualification: 11 scenarios passed; all 194 source files
  and report permissions were independently reconciled after an outer wrapper
  incorrectly rejected a trusted-owner Windows permission entry. Failed records
  remain preserved; the successful scenarios were not replayed.
- Full native maintenance preflight passed. The API/Web switch completed at
  08:00 UTC with a verified stopped-writer backup and five upload workers restored.
  Four backup integrity checks passed. Schema remains `a0c9d2e4f817`; configuration
  bytes remain unchanged. ASR/TTS tasks remain running.
- Served Web resources were independently matched to the fixed source over
  trusted HTTPS. Phone v53 was signed with the original certificate, published
  on the Windows phone feed and verified by native package checks and a complete
  trusted HTTPS download. TV remains v30. APK publication restarted no API task.
- The Mac independently verified all 11,491,704 APK bytes using 44 ordered HTTPS
  ranges in 43.39 seconds; the SHA-256 matches the signed candidate. Feed pointers
  stayed unchanged throughout this check.

The Mac's two single-connection APK download attempts timed out. Complete range
verification confirms file integrity, but does not establish physical phone
update behavior. Installation, actual listening and continuous voice session
acceptance remain pending owner testing.

## Owner checks

Update to v53 using “检查更新”, then search for photos in 拾光助手. Try
“介绍这些结果”, “这些照片是哪天拍的？” and “打开第二个”. Result introductions
use at most three current cards and valid recorded dates; missing dates are
explicit. During an opt-in voice session, confirm actual audible playback,
the next capture after playback, and immediate Pause/End behavior. Recovered
turns must not automatically replay speech or navigation.
