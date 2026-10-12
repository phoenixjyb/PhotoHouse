# Web assistant delivery — 2026-10-12

The central 拾光助手 workspace and explicit foreground read-only voice loop are
served on the protected WebUI. Phone v49 is separately published on HTTPS OTA.

## Exact delivered boundaries

- Web assets: `af26a99e98222984f1f11193faa1b9917f058964`; six-asset format-2 ZIP,
  1,014,061 bytes; SHA-256
  `bc8f8c93b8ce536357522caeebd9f40b6885ac1b6f7fd1b2b5e80f4a381117d6`.
- Static manifest SHA-256:
  `cf765f6c25011c34647b1dac056b9c557f5696ca72e7b97dc0e48bf8e0916b83`.
- Backend entry/source remains `c6b14018250f533dde73dda1bb899de525572217`.
  Its configuration and normal startup validation are preserved. The verified
  wrapper binds only the six static UI file paths before the existing listener starts.
- Phone remains v49; TV remains v30. Both OTA response bodies were identical
  across the successful Web restart. The original icon is preserved.
- Worker definitions/schedules, model configuration and original media were not
  changed. No schema migration was run. Normal existing startup journal
  maintenance may run during an API restart.

Windows native qualification checked the actual deployed UI router without a
listener or real database. The final live switch verified task/principal/process
ownership, configuration, all six served byte hashes, deployed security headers,
icon and OTA baselines. An independent Mac trusted HTTPS readback checked the
same six hashes, original icon and unchanged feeds. No TLS verification bypass,
redirect following, family login, microphone capture or GPU inference was used
for these delivery checks.

## Failure and recovery record

The rejected five-asset archive omitted memory-groups.js; it was never deployed.
Windows read-only preflights also caught collection/property handling errors.
The initial switch controllers exposed a reserved PowerShell `$Args` parameter:
the bound expected command line became empty and process matching was ambiguous.
Two failed attempts required an owned restore of the original task action; the
restores checked exact action, semantic task metadata, configuration, entry and
listener conditions. A later post-check incorrectly expected the standalone
router cache header instead of the closed application's `no-store` override;
its guarded rollback restored the original service automatically.

The final controller uses a non-reserved argument parameter, refuses an empty
command line, allows bounded shutdown completion, compares canonical XML task
metadata and validates live security/OTA baselines before stopping the API.
Native regressions verified the actual argument binding, rejection of empty
arguments, tolerance of action/format changes and rejection of real privilege
metadata changes. The final switch and independent readback passed. All failed
controller versions and recovery receipts remain private evidence.

## Acceptance and next work

Refresh the WebUI and open 拾光助手. On phone, update to v49 and open the same
workspace. Start voice explicitly, ask 找照片, refine to 只看视频, open a visible
result and exercise Pause/End. Real microphone, audio-focus/echo, owner/member
UI and family acceptance remain open. Clarifying and unsupported replies pause
the current read-only loop; it is not yet a general local-model agent.

Private history/preferences APIs are implemented and tested in source after this
Web pin, but are not deployed or enabled. No private conversation database was
created on Windows. Next work is server-owned turns, client continuation, applied
preferences and qualified grounded story/album/memoir tools; see
[the assistant design](PERSONAL_ASSISTANT.md) and [roadmap](ROADMAP.md).
