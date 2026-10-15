# Story and search source integration — 2026-10-15

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

Phone version 61 is reserved for this combined candidate. Local source/profile,
package, Windows qualification, live API switch, release signing/OTA publication
and family/device acceptance are separate gates. No dated v60 controller or
one-time authorization may be replayed for this candidate. Production operations
need a new exact source/package plan with backup, verification and rollback.
