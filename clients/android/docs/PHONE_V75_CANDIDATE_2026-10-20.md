# Phone v75 gallery/search candidate — October 20, 2026

This preparation snapshot records phone **75 / `0.75-gallery-search`** as a
configured **signed candidate** for `dev.photohouse.connected`, before hosted UI
qualification and OTA publication. The prepublication feeds were independently
checked as phone v74 and TV v30. Final merge and publication results belong to
[release PR #104](https://github.com/phoenixjyb/PhotoHouse/pull/104); this snapshot
does not claim physical-phone installation.

## Source and behavior

Build source: `e07fe446de76f59347095f74b18c24cb31516c3e`; Android tree:
`d1ebe0f3d3b746c0f0a176d94cf00db26af646ec`. The candidate includes the integrated library-wide
photo-stack client and clearer English/Chinese scene rewording guidance, retaining
upload preparation and protected text/people search. Library-wide grouping needs
its separately qualified server schema/index; the client retains its guarded
fallback when that extension is unavailable.

Semantic search remains disabled. This APK does not migrate a database, create
an index, install a model, change people/kinship access or activate grouping.
The [current API/Web release](../../../docs/SEARCH_RELEASE_2026-10-20.md) and
[offline semantic exclusion scorecard](../../../docs/SEMANTIC_EXCLUSION_QUALIFICATION.md)
record their separate scopes.

## Local qualification

- Five shared JVM suites: **1,335 tests**, zero failures, errors or skips.
  Protocol has no test source and adds zero tests.
- Configured release lint and assembly passed. The initial fresh run completed
  JVM checks and lint before its local time limit; assembly completed with an
  unchanged-source incremental resume.
- All 19 explicit profile properties were preserved. Native APK inspection
  matched all 17 embedded settings fields, package/version and the original
  icon pixels in the original unsigned build. Signing preserved every original
  ZIP entry, including all embedded settings.
- The APK's ten permission entries match the published v74 artifact. The
  previous signed APK and its original certificate were independently verified;
  the approved signing operation subsequently preserved that certificate.
- The separate unconfigured QA app, instrumentation APK and debug lint passed.
  The isolated local emulator exhausted its boot budget before instrumentation.
  The hosted [fixture workflow](../../../.github/workflows/android-ui-qualification.yml)
  runs the seven selected cases and retains seven app-private screenshots. Its
  result is separate from build checks; no UI pass is claimed in this snapshot.
- Related qualification, profile, check-registry and extracted-package checks:
  **105 tests and 66 subtests** passed.

Unsigned APK: **11,778,753 bytes**. SHA-256:
`4614b02dd0be5e9ff5866d8ef72b3a4871f00f4e601883c4e74a290fd642f2a0`.

Signed APK: **11,798,960 bytes**. SHA-256:
`bce2f1fc2ab595c03bfe4d2a24949c75252f98aa22ff272fe91137067b26133b`.
The original certificate, alignment, DEX and icon continuity checks passed.

## Remaining delivery gates

Source review/hosted CI, enlarged-text English/Chinese QA presentation checks,
native Windows artifact checks and guarded phone OTA publication remain
separate gates. Signing alone does not satisfy publication or device acceptance. Recheck the current feed/version before
publishing and compare the complete trusted HTTPS APK after publication. TV
publication is outside this candidate.

No new emulator or physical-phone journey is claimed here. Owner/member access,
real-media viewing, background/lock-screen upload behavior and family grouping
quality remain physical-device acceptance checks. The semantic scorecard has
only generated-vector validation; real-encoder exclusion measurements,
compatible 768-dimensional coverage and protected serving/resource qualification
remain pending.
