# Phone v43 source candidate

Version 43 (`0.43-memoir-voice-and-reading`) gathers the accepted phone
source increments after frozen v42. It includes reviewed voice instructions for
memoir drafting, optional chronicle/essay/memoir directions, explicit whole-book
planning and proposal review, a collapsed full-title draft directory, and
per-story plan reading that preserves the memoir draft. Earlier source increments
also improve dictation recovery, conversation history, source inspection and
chapter navigation.

The accepted memoir UI slices are `e2f0824`, `230acb9` and `694fd08`; each has
its scoped test and rendering evidence in the linked development plan. The
release build must pin the exact version commit and preserve the frozen v42
release feature profile, configured trusted origins and Home LAN address.
Release unit tests, lint, assembly, package identity, alignment, unsigned state
and full bytes/hash must be recorded for the actual resulting artifact.

The frozen v42 APK and its pending complete-release operation remain unchanged.
Preparing v43 source or an unsigned APK grants no signing, Windows staging, OTA
publication, device installation or provider activation authority. A separate
concrete v43 release scope is required before those operations. TV stays on its
independent release path.

See [Development plan](DEVELOPMENT_PLAN.md) for feature contracts and separate
source, emulator, runtime and family acceptance boundaries.
