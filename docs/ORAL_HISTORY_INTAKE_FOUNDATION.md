# Local oral-history intake foundation

**Status: internal source prototype, October 14, 2026.** The source implements
ordered recording sections and durable SQLite mutation receipts using generated
fixtures. There is no HTTP route, client recorder, Alembic migration, runtime
configuration, ASR queue, deployment or public recording feature. A new checkout
and the current Windows installation do not activate this prototype.

The October 15 source increment adds separate opt-in, author-only withdrawal
and V4 journal replay. Withdrawal retains original bytes but denies ordinary
source/status access, including after an older backup is restored. See the
[withdrawal contract](ORAL_HISTORY_WITHDRAWAL.md) for the remaining admission
and permanent-erasure gates.

## What this slice provides

[`OralHistoryIntake`](../server/backend/app/access/oral_history_intake.py) supports
explicit create, append, current status, original-section read and complete/cancel.
Each operation uses the existing `AccessService` transaction and current
session/library-membership policy. A recording remains private to its authenticated
author; a library owner has no override. Subject and narrator labels are authored
text, distinct from the account that submitted the source; they do not establish
person, face or consent identities.

A recording's title, labels, language and explicit local-processing consent are
immutable. Changing these requires a future reviewed metadata/version contract;
this prototype cannot silently reinterpret previously accepted sections. Session
creation accepts a bounded opaque library ID (up to 128 UTF-8 bytes).

## Section and quota contract

- Canonical PCM WAV: mono, 16-bit, 16 kHz, exact 44-byte header, no hidden/trailing
  chunks. Each section contains 1–320,000 frames, at most 20 seconds/640,044 bytes.
- Pause/end may produce shorter sections; a later resumed section can follow one.
  Offsets derive from accepted sample frames, not client duration estimates.
- At most 180 contiguous sections, 3,600 seconds and 128 MiB of original WAV
  bytes per session; at most eight retained sessions per author across libraries.
- Accepted raw WAV bytes remain unchanged. Reading one rechecks its format,
  frame count and original SHA-256. Status verifies the bounded metadata/hash
  chain and counters; it does not read/hash the complete recording's audio.
- Create/append/complete/cancel request IDs are canonical UUIDs unique per author.
  The digest binds operation, scope, expected revision/order and original source.
  Identical retries return the original receipt, including after close/reopen;
  changed payload/scope/consent or competing ordinal claims conflict.

An append writes source bytes, advances counters/manifest and records its exact
receipt/audit in one `BEGIN IMMEDIATE` transaction. A response is returned only
after commit. Failure rolls back all of them. Receipt JSON has its own checksum
and binding validation. Full synchronous SQLite in DELETE/WAL mode is required;
unsafe memory/off-journal or constraint-disabled settings refuse operations.
These are prototype caps, not published client limits or server admission guidance.

Completion closes further appends. Cancellation also closes capture and preserves
already accepted sources; it is not withdrawal or erasure. Original deletion is
unavailable, and SQL guards prevent accidental source/receipt edits, deletion or
reopening a terminal session. The retained-session quota deliberately does not
free itself by discarding raw sources.

## Storage and lifecycle boundary

[`oral_history_schema.py`](../server/backend/app/access/oral_history_schema.py)
contains an explicit fixture-only installer. It requires a caller-owned transaction,
foreign keys and supported account/library parent keys. It validates the exact
owned tables/index/triggers and refuses partial/drifted installations. Opening
an intake object never creates, alters, backfills or repairs a database.

The recording identity seeds a versioned manifest; each ordered section binds
its source hash, frame offset, frame count and preceding manifest. This supports
future exact transcript/citation anchors without inventing current ASR output.
No transcription, polish, title inference, story adoption or sharing occurs here,
even with processing consent. Consent is permission metadata, not a worker claim.

Existing deletion-journal transaction guards still refuse a stale primary marker.
They do not add an oral-history tombstone, full-chain review, eraser or restore
handler. Do not alias a recording to the existing `memory` journal collection.
Qualified withdrawal/dependency closure and paired restore are prerequisites
before adding this storage to an admitted production schema or accepting family
recordings. No indefinite raw retention is silently replaced by assistant expiry.

## Verification and next slice

The generated tests exercise reopened connections/exact retries, concurrent same
request and competing requests, rollback on receipt/commit failure, WAV limits,
short/resumed sections, original bytes/hashes, owner isolation, revocation/session
expiry, schema/receipt/source corruption, quotas and default-closed routes.
The final focused suite passed **18 tests / 15 subchecks**. The complete
`memory` profile passed **308 tests / 163 subchecks**. An adjacent intake/access/
contribution cohort passed **54 tests / 31 subchecks**; these scopes overlap and
must not be summed. The full API/Web/Android profiles were not rerun for this
internal, unreachable increment. The suite is included in `api` and `memory`:

```sh
.venv/bin/python tools/check.py memory
```

For the narrowly scoped source suite, from the repository root:

```sh
PYTHONPATH=server/backend .venv/bin/python -m pytest --noconftest -c config/pytest.ini server/tests/security/test_oral_history_intake.py
```

Reopening generated SQLite is not a Windows service restart, process/power-loss
experiment, native ACL/storage check or physical-device acceptance. No model,
GPU, family data or real recording is used. The exact API source package currently
served on Windows does not include or activate this experimental feature.

Next: define immutable recording source identity, authorized withdrawal and
content-free journal/replay behavior, qualify compatible schema/worker admission,
then add a bounded upload transport and local Web/phone recorder with explicit
saved/retrying states. Later transcription/proposal workers must recheck consent,
source/current membership and revision before accepting their output.
