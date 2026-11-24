# Local oral-history intake foundation

**Status: internal source prototype, November 25, 2026.** The source implements
ordered recording sections and durable SQLite mutation receipts using generated
fixtures. A protected HTTP transport is available only when its explicit
`oral_history_intake_enabled` app option is true. The optional Web recorder
shares that setting and uses the existing generated-fixture schema. The default app
and the current Windows runtime leave it off. Source now supports a separate
local transcription preview and editable author-reviewed text. Production
storage, native speech qualification and source-linked story adoption remain open.

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

A recording's title, labels, language, retention consent and local-processing
consent are immutable and separate. Creation requires an affirmative
`retention_consent`; declining creates no session, section or mutation receipt.
That consent permits the prototype to keep the original source in its private
store. It has no expiry: withdrawal hides a recording but retains its bytes, and
permanent erasure remains unqualified. This is not ready for family admission.
`processing_consent` separately controls whether later local processing may use
the source. A retained recording with processing declined can still be reopened,
read by its author and resumed, but does not authorize a worker. Session creation
accepts a bounded opaque library ID (up to 128 UTF-8 bytes).

## Protected resumable transport source

When an app explicitly enables intake, **Family → Oral history** opens an
author-private recorder. Starting a recording requires consent to keep original
audio. Permission for future local transcription has a separate, initially
unchecked control.

Record a section of up to 20 seconds, stop, and choose **Save section**. You can
listen to the unsaved audio locally before deciding.
The server receipt binds the exact saved section. If the link drops during
save, retry that same button while this tab is open. Reopen the recorder to
find your unfinished recordings and continue at the next section saved by the
server. Leaving the panel, signing out, or putting the browser in the
background clears unsaved audio and stops the microphone. **Finish recording**
closes an open session that has at least one saved section.

Choose **Review finished recordings** to see your completed sessions. Select
one section and choose **Load audio** before playing it with the browser's audio
controls. Sections remain in their recorded order. Closing the panel or leaving
the foreground stops playback and clears the browser's in-memory copy.

The generated browser checks use synthetic audio and a temporary database.
They exercise dropped replies, exact retry, foreground interruption and
resume after reload. They also finish, reopen and play the exact saved section
after reload. Device capture, paired storage recovery and family consent have
their own acceptance checks.

The internal transport in
[`oral_history_transport.py`](../server/backend/app/access/oral_history_transport.py)
is mounted only by `create_app(..., oral_history_intake_enabled=True)` with an
explicit `AccessRuntime`. The option defaults off; no route is mounted by the
default app. This flag is not schema admission: the exact fixture schema must
already exist, and the route never installs or repairs it. Requests use the
normal protected bearer or same-origin cookie/CSRF path, current author and
library membership, and no-store privacy headers.

`POST /oral-history/v1/libraries/{library_id}/sessions` requires strict typed
JSON, including separate explicit boolean `retention_consent` and
`processing_consent`. Declined retention is refused before a row or receipt is
written. `GET .../sessions/{session_id}` returns bounded resume status without
audio. `POST .../sessions/{session_id}/sections` accepts one raw canonical WAV;
the request ID, expected revision and ordinal are explicit headers. The route
checks current author access to that exact session before reading audio, then
the intake rechecks it atomically with the append. Identical retries return
the committed receipt without adding another section. Existing complete and
cancel operations are also wired through protected routes. `GET .../sessions/completed`
lists completed sessions for the current author and library, up to the existing
eight-session quota. `GET .../sessions/{session_id}/sections/{ordinal}` requires
the selected completed revision in `X-PhotoHouse-Expected-Revision`. It verifies
current author access, source state and the original WAV and hash before
returning one no-store section. Transcription and story adoption remain separate
actions.

### Review a local machine transcript

An explicit `oral_history_transcription_enabled=True` app setting requires
enabled intake and an injected `LocalAssistantAsr` provider. The setting defaults
off. For a completed recording with local-processing consent, the author can
select one section and choose **Transcribe locally**. Opening the recording or
playing its audio starts no processing.

`POST .../sessions/{session_id}/sections/{ordinal}/transcription` accepts only
`{"expected_revision": ...}`. The route binds the current author, library,
completed revision and consent before loading the verified original audio.
It sends the exact section to the configured loopback ASR provider and checks
the source and access again before returning a no-store result. Only one
recording transcription can run in the app at a time. A busy or failed
preview can be retried by the author.

The preview is an unsaved machine transcript. The Web panel removes it on a
section change, close, backgrounding or account/library change. The original
audio remains playable in the same view.

### Save the author's reviewed wording

With `oral_history_reviewed_text_enabled=True` and the separate review schema
installed, **Review text** opens the current section's saved wording. An empty
review can start from the displayed machine draft or from typed text. **Save
reviewed text privately** is the only action that writes the wording. It stays
separate from the original WAV and the machine preview. The author can reopen it
without running speech recognition again.

`GET .../sections/{ordinal}/reviewed-text` accepts the existing expected source
revision header. `PUT` accepts `expected_revision`, `expected_review_revision`
and `text`. Each action verifies the current completed recording, author,
original audio and exact section. Reviewed text is capped at 8 KiB of UTF-8.
An identical retry returns the current accepted wording. Saving different text
at a stale revision reports a conflict. A withdrawn source no longer returns
its review. These actions never change the WAV or save a story.

The generated restore check denies the reviewed wording before and after
replaying a later withdrawal against an older backup. The separate review table
still needs production migration and paired backup/restore qualification.

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

The recording identity seeds a version 2 manifest that binds both consent facts;
each ordered section binds its source hash, frame offset, frame count and
preceding manifest. This supports
future exact transcript/citation anchors without inventing current ASR output.
Recording intake creates no transcript, polish, title, story or sharing entry.
The separate preview requires both prior processing consent and an explicit
request for the completed section.

The prior experimental session schema has no retention fact. Exact schema checks
therefore fail closed on it; this source performs no automatic migration, does
not presume old recordings were retention-consented, and does not rewrite their
manifest or receipt hashes. A separately reviewed migration would need an
affirmative source and a compatible identity/journal plan.

Existing deletion-journal transaction guards refuse a stale primary marker.
The subsequent [withdrawal prototype](ORAL_HISTORY_WITHDRAWAL.md) adds a separate
V4 `oral_history` recording collection, author-only retained-source withdrawal,
full-chain review and older-prefix replay. Do not alias a recording to the
existing `memory` collection. Its generated qualification is source evidence,
not production schema/journal admission, paired recovery or permanent erasure.
Those remaining lifecycle gates must pass before accepting family recordings.
No indefinite raw retention is silently replaced by assistant expiry.

## Initial verification and current next slice

The generated tests exercise declined-retention refusal, separate retention and
processing consent, reopened connections/exact retries, concurrent same
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

The generated HTTP transport suite additionally exercises create, one committed
append, status after closing and reopening the client against SQLite, exact
retry without duplication, a following section, declined consent, author/scope
refusal, revocation and the default-unmounted route. It does not qualify a
production schema, live service, recorder, actual recording, processing worker
or family acceptance.

Immutable recording source identity, authorized retained-source withdrawal and
content-free V4 journal/replay behavior now have internal source implementations
and a [versioned generated rehearsal](ORAL_HISTORY_QUALIFICATION.md). Next
qualify the operator's journal/schema upgrade and paired restore, specify
permanent erasure and backup retention, and qualify recording on physical
devices. The generated transcript preview exercises current consent,
authorization and revision, including a withdrawal during the provider
request. A generated author review verifies explicit save, exact retry,
different-text conflict and reopen without recognition or audio changes.
Native ASR and household audio remain untested in this increment. Intake,
transcription and reviewed text each stay off in the deployed configuration.
