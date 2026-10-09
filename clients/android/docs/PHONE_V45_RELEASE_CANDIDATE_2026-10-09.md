# Phone v45 source candidate

Version 45 (`0.45-grouped-family-stories`) integrates protected grouped-story
creation and review, conflict recovery, whole-story or chapter contributions,
and optional profile-derived bylines. The feature and contract provenance is
recorded in `docs/feature-source-changes.json`.

Curated-candidate checks passed: selected grouped-story/attribution JVM tests,
the connected app unit suite, connected instrumentation-source compilation, the
connected-boundary verifier, and 14 title validator/provider-mock cases. The
full supported CPU API profile passed 674 tests and 352 subtests on October 9,
2026, including the protected ASGI route suite and story-workspace contracts.
The candidate contract replay also passed using candidate server files and the
recorded upstream source hashes. This run used an existing macOS arm64 Python
3.12.12 / pytest 9.0.3 environment; it did not install dependencies afresh.
No candidate emulator journey or signed APK build was run here.

This file describes source integration; it does not identify a signed APK or
establish installation, live-service, physical-phone, TV, or family acceptance.
Signing and OTA delivery remain separate release evidence.
