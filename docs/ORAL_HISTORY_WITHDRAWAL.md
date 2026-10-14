# Recording withdrawal and backup replay

**October 15, 2026: internal source prototype.** No route, client recorder,
Alembic migration, runtime opt-in or Windows operation is provided. This builds
on the [intake foundation](ORAL_HISTORY_INTAKE_FOUNDATION.md).

## Withdrawal is explicit and owned

Only the current authenticated author with current library membership may
withdraw a recording. Owners cannot override another author's source. A separate
`withdrawal_enabled` opt-in requires the same journal object bound to the access
service. The default is off.

The caller supplies a canonical request UUID and expected revision. The journal
commits first; the primary then commits the withdrawn state and audit. Exact
retries return a content-free receipt. Other request IDs/payloads conflict. If
the primary commit fails after journal append, ordinary requests remain blocked
until reviewed offline replay succeeds.

Withdrawn sessions retain their immutable raw WAV sections, labels and source
receipts. Ordinary status, audio, append, close and create retries deny access.
The withdrawn state cannot reopen. **This is not permanent erasure:** database
bytes and backups still contain the original. Retained sessions still consume
the author quota. A separately qualified erasure/retention contract is required.

## V4 external journal

An explicitly created private V4 journal adds an `oral_history` collection with
`recording` records. Each record binds the session/library/author identity,
immutable metadata hash, original manifest and ordered section heads, original
state/revision, and exact withdrawal request. It contains no audio, title,
narrator label or narrative text. Identifiers and hashes are still private
metadata and belong outside public source.

Existing V1–V3 formats and digest domains remain supported. They refuse recording
withdrawal. There is no V3→V4 upgrader in this increment. Binding a fresh journal
requires empty original stores and an absent or exact, empty recording schema;
partial tables and retained recording history refuse adoption.

## Restore safety

Replay checks the full journal chain and original identity. A restored recording
must be the exact reviewed source or a verified older source prefix. A shorter
prefix must still have been open; a completed/cancelled recording cannot later
gain sections. Each retained WAV is checked one bounded section at a time.
Conflicting identities, source bytes, state or section heads refuse replay
without advancing the primary marker.

Full review also verifies previously applied recording withdrawals. Ordinary
session access performs an indexed per-UUID tombstone check, so copying a current
marker onto an older open database does not revive its recording. Ordinary reads
do not scan every recording's raw audio. Production admission must still qualify
paired restore, full-chain/source review and compatible schema/journal versions.

## Evidence and remaining delivery gates

Generated fixture tests cover ownership, revocation, exact retries, copied
markers, primary rollback, older open prefixes, terminal-prefix rejection,
corrupt raw audio, partial schema and legacy-format refusal. They use no family
recordings or model inference. The API and memoir check profiles include them;
source packages include the three recording modules without enabling them.

Next: a reviewed V4 upgrade and schema admission plan, permanent erasure with
backup replay, then protected section transport and a client recorder showing
saved/pending/retrying states. Speech processing, linking to family stories and
editorial stitching need their own consent, revision and provenance checks.
