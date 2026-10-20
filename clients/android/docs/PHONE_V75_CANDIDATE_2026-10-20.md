# Phone v75 gallery/search candidate — October 20, 2026

Phone **75 / `0.75-gallery-search`** is a configured **unsigned candidate** for
`dev.photohouse.connected`. It has not been signed, published or installed.
The published feeds were independently checked as phone v74 and TV v30.

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
  icon pixels. The candidate is unsigned.
- The APK's ten permission entries match the published v74 artifact. The
  previous signed APK and its original certificate were independently verified;
  no signing key was accessed.
- The separate unconfigured QA app, instrumentation APK and debug lint passed.
  No instrumentation or new UI render was executed in this round.
- Related qualification, profile, check-registry and extracted-package checks:
  **105 tests and 66 subtests** passed.

Unsigned APK: **11,778,753 bytes**. SHA-256:
`4614b02dd0be5e9ff5866d8ef72b3a4871f00f4e601883c4e74a290fd642f2a0`.

## Remaining delivery gates

Source review/hosted CI, enlarged-text English/Chinese QA presentation checks,
native Windows artifact checks, original-certificate signing and guarded phone
OTA publication remain separate gates. Recheck the current feed/version before
publishing and compare the complete trusted HTTPS APK after publication. TV
publication is outside this candidate.

No new emulator or physical-phone journey is claimed here. Owner/member access,
real-media viewing, background/lock-screen upload behavior and family grouping
quality remain physical-device acceptance checks. The semantic scorecard has
only generated-vector validation; real-encoder exclusion measurements,
compatible 768-dimensional coverage and protected serving/resource qualification
remain pending.
