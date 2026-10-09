# Private memory community v1

Source candidate, October 1, 2026. Existing `/memory-stories` v1 responses remain
unchanged for phone v33/v34. New routes live under `/memory-community/v1`; no
anonymous TV contract receives contributions, conversations or model drafts.

## Activation and transport

Three explicit booleans default to false: `memory_collaboration_enabled` (memoirs
and community reads), `memory_originals_enabled` (new retained text/voice), and
`memory_generation_enabled` (queue model/chat work). The latter two require the
first. `memory_originals_enabled` (and existing upload annotation intake) or
`memory_generation_enabled` also requires both `original_deletion_journal_path`
and `original_deletion_namespace` in `RuntimeConfiguration`. They must identify
an already initialized, private external journal bound to the same primary
database. Runtime and both worker modes validate the pairing; they do not create
the journal. A missing file, namespace mismatch or stale database watermark
fails closed. The source operator note `ORIGINAL_DELETION_RECOVERY.md` is outside
this curated candidate.

As of October 1, source migration and disposable-database tests are present, but
the observed live catalog remains e6. No live journal has been initialized or
bound, and original intake, generation, worker/model quality and family acceptance
remain unqualified. Source changes and schema tests do not activate runtime flags.

All routes require current authenticated membership in the selected active
library, trusted HTTPS origin and the existing cookie CSRF or native bearer
policy. `library` is the only scope parameter; paginated reads also accept
`page`. Every parent story and each of its selected media must still be readable.
A memoir is hidden as a whole if any referenced essay becomes unavailable.
Unknown methods/routes, extra fields, duplicate JSON keys and query credentials
are refused. Responses are private/no-store; personal words are never URL data.

`GET /capabilities` returns version 1, the three enable states, 30-day conversation
retention, WAV format, 30-second audio cap, 8,192-byte contribution text cap, and
`until_owner_deletes` original retention. Disabled features do not bypass auth.

## Family originals

Paths are `/stories/{story_id}/contributions` with `GET` for a 16-item page;
`/{contribution_id}` supports `GET` and owner-only `DELETE`. POST suffixes are
`/text`, `/audio`, and `/{contribution_id}/review`. Authorized original audio is
`GET /{contribution_id}/audio`.

Submission metadata has exactly these string fields:

```json
{"kind":"text","text":"家人的原话","language":"zh","byline":"家人的署名",
 "consent":"1","chapter_id":"","revision":"1","mutation_id":"UUID"}
```

Text is nonblank, valid UTF-8, at most 8,192 bytes; byline is at most 256 bytes.
Language is `zh`, `en`, `mixed` or `und`; consent is `0`/`1`. Empty `chapter_id`
means the whole story; otherwise it must be a current canonical chapter ID.
The author is always the authenticated account; a supplied byline does not change
that identity. Story revision must match on first submission. A retry freezes
metadata and mutation UUID; identical authorized retries return the same original.
Reusing an identifier for different content is a 409, never a second insertion.

Audio uploads use `Content-Type: audio/wav`. UTF-8 JSON metadata, with `kind` set
to `audio` and empty `text`, is base64 encoded in `X-PhotoHouse-Memory-Metadata`.
The header is ASCII and bounded to 4 KiB. Body is bounded to 2 MiB, ten seconds
of upload time, mono 16 kHz PCM16 and at most 30 seconds. No file or provider path
is accepted. Several short segments may form a longer recollection.

Every approved member may contribute without gaining story editing rights.
New originals are pending. Other members see accepted submissions and their own
pending/declined entries; the owner or authorized story editor may review all.
Review body is exactly `state` (`accepted`/`declined`) and current story `revision`.
Only accepted originals with processing consent queue a separate derivation.
Original text/audio never changes. AI transcription, suggested wording and tags
remain proposals. A chapter-bound original from an earlier story revision is not
silently reused for a newly arranged chapter with the same ID.

Owner deletion removes original/derivations and clears related unadopted story
and memoir proposals/replies, cancelling outstanding work. Explicitly adopted
human story prose is unchanged; an editor must revise it separately. Secure
SQLite deletion is enabled, but existing backup copies need the separate restore
replay/retention process before live original intake can open.

## Memoirs

`/books` supports `GET` pages of eight and `POST`; `/books/{book_id}` supports
`GET`/`PUT`. Exact string fields: `title`, `language`, `introduction`, `story_ids`,
`revision`, `mutation_id`. Titles are nonblank and at most 512 UTF-8 bytes;
introduction at most 6,000 bytes; language `zh`/`en`; `story_ids` is 1–24 distinct
canonical saved-story UUIDs in reading order. Create revision is `0`, edit is the
current revision. Owner may edit any memoir; contributors only their own.

Storage holds editorial text and IDs, never copies of family/AI source words.
Responses hydrate current ordered story titles/revisions/counts. One generation
context supports at most 24 chapters and 96 evidence sources across a book; a
larger memoir receives HTTP 422. A caller can generate per saved essay under the
existing story target, but that does not create memoir-wide transitions.

## Continuous story companion and drafts

`POST /conversations` takes exact strings `id` (client UUID), `target_type`
(`story`/`book`), `target_id`. Each conversation belongs to one current account and
library and expires 30 days after creation, without renewal. Maximum 32 active
conversations per account; at most 128 turns each. `GET /conversations` requires
`target_type` and `target_id` and returns the current account's newest eight
unexpired conversations for that fully authorized parent. `GET /conversations/{id}/turns`
returns 16-item pages; POST takes `revision`, `mutation_id`, `text` (1–4,096 UTF-8
bytes). One pending reply per conversation; at most four queued/running jobs per
account. DELETE closes that account's conversation and its dependent jobs/turns.

October 2 source accepts the explicit history query `reply_context=1` to add
`reply_source_ids` and `reply_questions` to each turn (empty arrays when
unavailable). Omitting it retains the original exact response keys for existing
clients; other values and duplicate flags are refused. These hydrate the existing retained
companion output only for a ready chat job matching the actor, library,
conversation, parent and current source fingerprint. The full companion is
revalidated against current authorized evidence and its reply/kind must match
the turn. Source IDs are references, not proof of truth; questions are optional
drafting suggestions, never instructions to execute or send. Expired/foreign
job references are stale; malformed or mismatched metadata is omitted. No
source prose, model call, schema or retention change is added to history reads.

The optional `order=recent` query selects pages from the newest end of the
conversation. Page 1 contains the latest up-to-16 turns; page 2 contains the
preceding group. Each page's items remain in ascending conversation sequence for
reading, and `has_more` means older turns remain. Clients merging pages must order
by sequence and deduplicate turn IDs. Pagination is a current offset view rather
than a retained snapshot; refresh reloads the chosen window when new turns arrive.
Omitting `order` preserves the legacy oldest-first paging and exact response keys.
Only `recent` is accepted as an explicit order; other/duplicate values are refused.
This option composes with `reply_context=1`. It changes no model context, retention,
read authorization, schema, job state or provider activity.

`POST /jobs` creates an editor-only narrative proposal from exact strings
`target_type`, `target_id`, `revision`, `mutation_id`, `instructions` (up to 4,096
bytes). `GET /jobs/{id}` reads one's own current job; DELETE cancels and discards
its unadopted result. States are queued/running/ready/failed/cancelled/stale.
Retries do not escape source freshness checks. `base_revision` is a decimal
string, matching story and book revision handling without JavaScript precision loss.

The companion model receives the current question plus at most seven preceding
exchanges (`memory_processing.job_context` selects eight turn rows including the
current one). Reading older history does not enlarge this window. The Web reader
explains the limit; no automatic conversational summary or long-term personal
memory is claimed.

Web backgrounding stops local recording/playback, aborts status requests and
clears protected reader material, while keeping already-submitted server jobs.
It never resends the question. After foreground authorization, reopen the same
saved story or memoir to read fresh history and recover its pending reply.
Standalone reader visibility refresh also checks its still-current job. Late
pre-hide status responses cannot restart checks or replace the visible state.
Explicit Cancel and ordinary reader/scope disposal retain cancellation behavior.

A queued job stores controls and reference IDs, not a snapshot of raw family
sources. The worker hydrates current evidence, labels raw family text,
AI-produced transcripts, existing editorial narration, AI captions and
observations distinctly, and includes deterministic bounded excerpts. The current
generation context does not pass `taken_at` or `date_hint`, so neither is a source
for model date claims. Distinct source overflow at 96 is an explicit error rather
than silent omission. The worker releases SQLite before model I/O, then
rechecks membership, consent, exact parent revision and full dependency fingerprint
before committing. Cancelled/deleted/revoked/stale
work cannot save an answer. Model results never overwrite an essay or publish it.
Responses have strict ordered chapter IDs and known source references, questions
and a required human-review marker. A citation pointer is not proof that a claim
is true; family review remains necessary.

Memoir creation and ordered table-of-contents links to essays are implemented in
source. Generation accepts at most 24 chapters and 96 sources in one context; a
larger book is not automatically split and currently receives HTTP 422 asking
for a smaller context. The local model request also caps its complete response at
2,048 predicted tokens, not 2,048 per chapter; narrative quality remains
unqualified. Book-level outline/transition generation and continuous novel-like
reading across essays are not implemented. Each essay remains its own reader and
generation/adoption target.

Expired conversations/jobs are purged on explicitly enabled runtime startup,
hourly and before new queued work. Reads hide expired rows immediately. An hourly
maintenance failure closes community operations until a successful purge. Backup
restoration must run expiry cleanup before serving history; backup expiry is a
separate operational retention gate.

## Local worker

`run_memory_worker.py` requires a closed nine-field explicit config, exact e7
storage, a current bound external deletion journal, and loopback-only model
endpoints. Keys are `database`, `mode`, `ollama_url`, `ollama_model`, `asr_url`,
`asr_model`, `asr_token`, `original_deletion_journal_path`, and
`original_deletion_namespace`; ASR fields are null for narrative mode. Both
`narrative` and `contributions` modes require the journal pair. `--preflight` is
read-only and makes no provider contact. Use `--once` or
`--max-items` (1–32) plus `--max-seconds` (1–1800). No daemon, schema creation,
automatic failure retry, task registration or service restart occurs.

Provider output and prompts are byte-bounded and errors sanitized. Synchronous
socket calls have inactivity timeouts plus checked narrative elapsed deadlines;
one blocked read may exceed the wall deadline until its timeout. An absolute
job runner bound still needs external task/process containment at deployment.

The source operator note `MEMORY_COLLABORATION_SCHEMA_APPLICATION.md` and product
plan `PHOTOHOUSE_SHARED_STORIES_PLAN_2026-10-01.md` are outside this curated
candidate. Local source, model mocks, browser/emulator, live providers and family
quality are separate acceptance stages.
