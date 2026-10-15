# PhotoHouse next-session handoff — October 13

Canonical development repository: PhotoHouse monorepo, branch
`codex/phone-conversation-navigation-20261010`. Recheck HEAD and preserve any
later changes before work. Previous application repositories are references.

## Completed source

- Compact phone conversation management and scoped dialog state: `f738d17`.
- Negotiated, default-off saved story/memoir retrieval and Web text cards:
  `f9ae4a8`, provenance `1fefbb9`.
- Source-validated saved-memory reply speech, optional independent capability,
  audio cancellation and eight-case offline qualifier: `bb1c2d4`, provenance
  `7daf740`.
- Explicit legacy/private browser fixture profiles: `55d7213`, `1c37252`,
  provenance through `9249c80`.

Source checks preserve account/library ownership, exact request recovery,
30-day private input records and transient assistant audio. Original family
stories are not rewritten by retrieval or reply speech. Web cards still have
no reader-opening action. Phone cards and free-form grounded story questions
remain outstanding. See [Roadmap](ROADMAP.md) and [Architecture](ARCHITECTURE.md).

## Qualification

The full API profile at `7daf740` passed 1,337 tests and 793 subtests, plus the
generated no-listener demo, with unchanged invocation source identity. The
focused follow-up passed 76 tests/39 subtests, 49 controller checks, eight memory
browser checkpoints and six portable qualifier tests covering eight scenarios.
Phone panel evidence is 19 simulator cases plus the final focused composer
check; it is outside the earlier pinned v51 APK.

Web fixture/profile corrections and the final missing-module fallback are
recorded in [Development](DEVELOPMENT.md). All 23 suites passed in cohorts;
rerun one complete invocation with the installed module selected:

```sh
PLAYWRIGHT_MODULE=playwright-core PH_BROWSER_PYTHON="$PWD/.venv/bin/python" \
  .venv/bin/python tools/check.py web
```

## Delivery boundaries

No Windows write, store initialization, task run, API switch, signing or APK
publication occurred in this source round. Read-only HTTPS checks returned 200
for the served UI and the phone feed, which still advertises v50. This does not
qualify signed-in family behavior or service/GPU health.

Two previously prepared approvals remain pending: native synthetic Windows
qualification of the exact `db95b6` six-case package, and signing/publishing the
exact phone v51 APK built from `3a56870`. Do not silently substitute new source
or reuse consumed v50 authority. Follow the private operation manifests and
AGENTS.md; newer source does not change those immutable candidates.

The newer source-only API ZIP at `7daf740` contains 194 files, SHA-256
`25c4c0e5f0bad80afaabb3a659af5d37fd714783d324af00c4f4bc042f30b1c9`.
It has not been staged or run on Windows. Qualify the intended source, provision
the separate private store under the service identity, and prepare a specific
live switch before enabling features. Family pronunciation, physical phone/TV
acceptance and deferred member checks remain separate gates.
