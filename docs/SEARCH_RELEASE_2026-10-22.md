# Combined protected-search and grouping source release — October 22, 2026

PR [#108](https://github.com/phoenixjyb/PhotoHouse/pull/108) merged as
`a6dfe31f7df1149170a01fc5a171867b2aea0584`. Its Git tree exactly matches the reviewed
source commit `c5dd85018a36e9f574acabcd9ecaf47db609e051`. Native release R3 deployed
this source and passed independent postflight at **2026-10-22 11:48:33 Asia/Shanghai / 03:48:33 UTC**.

## Source and checks

| Evidence | Result |
| --- | --- |
| Hosted functional API, browser, Windows CPU, Windows private readers and Android | All passed, run `39705626876` |
| Android fixture UI | Passed, run `39705626811` |
| Exact-source local API | 3,339 tests / 4,018 subtests passed, plus generated demo |
| Source package | 1,718 files and 635 overlays verified |
| Generated browser journeys | Three passed |
| Main merge tree | Identical to reviewed source tree |

These source checks are separate from the native delivery evidence below. They do not establish
semantic activation, Android publication by PR #108, or family/device acceptance.

## Delivery state

The first native release attempt, R1, refused during preflight before maintenance or
task definitions changed. R2 staged 19 immutable files, then was retired before execution so the
independent furnishing publication could finish. R3 deployed the exact source `c5dd850` and passed
independent postflight at **2026-10-22 11:48:33 Asia/Shanghai / 03:48:33 UTC** (observed epoch
`1792640913.1490157`). The new API listener matched the pinned source, and all 293 API source files
were verified. API non-action settings were preserved; all nine runtime states were restored, and
80 other tracked task definitions were unchanged. Four stopped-writer backups and four disk-restore
rehearsals passed; total backup size was 955,863,040 bytes. No database was restored to production,
and no schema migration occurred.

Independent protected checks passed: 11 protected-name/relationship checks and three named parent
plans; the viewer remained excluded from kinship. Anonymous auth/upload and unauthenticated
session/assistant requests returned 401. Trusted-TLS WebUI, script and phone/TV feed reads returned
200. The final public 125 after-check also returned 200 over trusted TLS, matched the before-check asset
hashes and privacy headers, and created no accounts. The independently managed furniture static
service's task XML, configuration, module and manifest were preserved. No auth sessions were created.
Phone physical acceptance remains false.

Phone **v75 / `0.75-gallery-search`** was separately published as a release package/feed through
[PR #104](https://github.com/phoenixjyb/PhotoHouse/pull/104), merge `29f5d5d`. Physical installation
and family-device experience remain unaccepted. TV v30 is unchanged. PR #108 did not publish a new
Android package.

## Product and data boundaries

The source combines protected search and clarification/exclusion behavior, photo
grouping changes, and default-off AI tooling. Semantic search and local selected-story
generation/providers remain **OFF**. Default-off code and source qualification do not
prove that either capability is enabled in a runtime.

A0 schema `a0c9d2e4f817` remains in place. There is no F2 migration, index refresh,
identity or kinship expansion, or model change in this release. The native semantic
qualification on frozen source `e85c6e4` remains qualification only: 23,761 catalog
entries comprised 23,696 vectors and 65 approved omissions; all 15 protection checks
and both audits passed. Median latency was 7.860 seconds, maximum 8.328 seconds, and
cold latency 14.843 seconds. The 2-second backend target remains unmet, and R61/R62
source cache changes have not been native-performance-qualified.

The historical GitGuardian incident `38823392` concerns a synthetic URL test fixture
in historical commits. A human explicitly deferred disposition, so it remains open;
no finding dismissal or security-setting change was made.

## Current gate

The R3 API deployment and public 125 after-check are verified. The after-check preserves the
independent furniture static service and confirms matching pre/post asset hashes, HTTP 200, trusted TLS,
privacy headers and no accounts. Family/device search trials, semantic relevance and any future feature
activation remain separate decisions and evidence.

See [Project Status](PROJECT_STATUS.md), the [source ledger](feature-source-changes.json),
and the earlier [October 20 guarded-search snapshot](SEARCH_RELEASE_2026-10-20.md).
