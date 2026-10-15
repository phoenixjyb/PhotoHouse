# Story and search source integration — 2026-10-15

This records the staged v61 integration. Search-client v2 subsequently shipped
in v62 through PR #17; see [current status](PROJECT_STATUS.md). Version-1 and
next-search-gate statements below describe the earlier v61 release.

This integration combines the Web guide `259c178`, phone guide `66677db`, and
completed search backend source through `3594fc0`. The common parent is
`c4cac82`. It preserves the independent source branches and introduces no
production schema migration or automatic provider/kinship activation.

## User-visible release scope

- Web and phone guided story creation: choose moments, type or explicitly
  dictate/review/add wording, inspect the draft, explicitly save and reopen.
- Existing full editors, source review, capture cancellation and immutable
  uncertain-save recovery remain available.
- Conversational parser fixes inherited from `5e608ac` handle the documented
  simple request forms and report missing date/person evidence clearly.

The new text/reviewed-person search-v2 backend is included as a negotiated source
contract. Current Web/phone private conversations still use version 1. This
release does not claim improved semantic retrieval, activate relationship graphs,
prepare reviewed people indexes or reinterpret filename/receipt times as capture
dates. See [joint search](ASSISTANT_JOINT_SEARCH_V2.md) and
[private kinship](PRIVATE_KINSHIP_SEARCH.md).

## Next search integration gate

A subsequent coordinated slice must negotiate version 2 in private-workspace
capabilities, bind that mode durably to request identity, extend strict
context/result-summary validation and rehydration, and parse/display provenance
in Web and phone. Qualify lost-response GET/retry, mode collisions, source changes,
downgrade refusal, private receipt reconciliation and old-client compatibility.
An authenticated request's saved receipt IDs and the receipt tracking status
shown after recovery are separate contracts. Do not switch a header alone.

## Source ledger reconciliation

Both branches' original feature records are retained unchanged. The serialized
ledger inserts an explicit common-parent projection for shared-file provenance
before replaying the search branch, then overlays the actual merged files.
These records reconcile expected file hashes; they are not runtime file
operations or reversions. The public Git merge preserves both original parents.
The source verifier must accept the final combined tree.

## Delivery boundary

Final release source is `8f4690506106cb156f1bf4cc346c82b1da70357b`. API/Web is
deployed and phone v61 is signed and published, with native/complete HTTPS
readback, original icon/certificate and unchanged TV v30 verified.
[The release record](../clients/android/docs/PHONE_V61_RELEASE_2026-10-15.md)
distinguishes full profile sources, exact component reuse, native qualification,
guarded deployment and the still-open family/device acceptance. The unfinished
search clients were excluded according to the owner's chosen release scope.

## Qualification repair

The release browser qualification exposed a pre-existing delayed-capability
layout path: saved-memory reader and speech controls added after a card rendered
bypassed its primary action row. The repair uses the same wrapping action row
for those late controls, preserving the existing readiness and scope checks.
The browser regression holds all three optional probes pending, then checks
Chinese and English cards after they resolve, including the existing narrow
viewport and 48-pixel target checks. This changes Web presentation only; Android
source, API contracts, schema and provider activation remain unchanged.

Visual inspection also identified an unlabeled Stop control in that late path.
The common playback-control refresh now assigns its localized visible label;
the browser checks require named Chinese and English Stop buttons. The standalone
edition-shelf test harness now includes the guide controls from production HTML,
while retaining its intentional legacy font-control omission.
