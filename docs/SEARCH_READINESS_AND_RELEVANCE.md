# Private search readiness and relevance

This local source increment adds an internal readiness read and an offline
operator check. It uses the same search-v2 authorization, reviewed index,
eligible text projection, source digest and kinship checks as ordinary search.
It adds no public route, login, permissions, model, listener or data migration.
Use it on the data-owning host; do not copy household databases/media to a
development Mac. Local fixture checks do not establish real-library relevance.

## Readiness before relevance

`AssistantSearchReads.readiness` counts the current authorized library by
image/video/other. It distinguishes catalog assets, reviewed indexed assets,
recorded capture dates, searchable dates, text sources and reviewed-person
coverage. Text source counts are per asset and may overlap. It reports whether
the caller has an available private kinship graph, without emitting the graph,
identity roster, paths, prose or account/asset/person IDs.

`current` means the selected sources passed integrity and authorization checks.
It does not mean the index is complete, dates are accurate, all people are
reviewed or retrieval is useful. A stored date outside the reviewed index is
recorded but not searchable. A disabled date/people field is not counted as
searchable. Unknown capture dates remain unknown. Issue codes identify missing
coverage; readiness itself always says `relevance_measured: false`.

The aggregate `people_readiness.status` distinguishes `disabled`, `empty_roster`,
`zero_assigned`, `partial_coverage` and `available`. Counts describe the reviewed
index and its indexed assets; they do not claim that every face or every person
in the library has been reviewed. An unassigned roster entry is permitted only
when its reviewed person record explicitly has `allow_zero`; the report counts
these entries separately. `kinship_bindings` reports aggregate `unique`,
`missing`, `ambiguous` and `stale` joins for the supplied private graph. It emits
no names, identifiers, aliases, graph facts or account scope. `unique_allow_zero`
counts current catalog joins intentionally approved without a face assignment.
An unresolved graph binding does not create an identity or change search access.

## People-search replies

Search-v2/v3 result replies, current-result overviews and their explicit speech
readout disclose that people search uses confirmed assignments. Unreviewed
photos or videos may be missing; a joint `all` search requires every selected
person to have a confirmed assignment in the same item. Empty-result guidance
keeps date, text and descriptive constraints and their existing explicit
relaxation suggestions. The explanation itself never changes a filter.

This fixed bilingual notice is an evidence boundary, not a measured coverage
percentage or a claim that the requested people are absent from the library.
It emits no additional names, roster counts, IDs or graph details. Reply shape,
the 600-byte bound, source revalidation and access checks remain unchanged.
General searches without people filters retain their existing wording.

## Reviewed people and index preparation

Reuse `server/scripts/prepare_access_discovery_index.py` for the reviewed index;
do not make a second roster or index generator. First run it against the
data-owning host's existing database without `--review`. Keep the output and
receipt in private owner-only storage. The receipt supplies the current source
digest and the artifact fixes the visible asset scope. The tool reads the
database read-only and refuses an empty library or an aliased output path.

For example, with placeholders replaced by native absolute paths and the
operator-selected library/revision:

```text
python server/scripts/prepare_access_discovery_index.py \
  --database /private/operator/library.sqlite \
  --library LIBRARY_ID \
  --revision 1 \
  --out /private/operator/review-base.json
```

The operator then prepares the existing review envelope privately, using only
confirmed catalog labels/aliases and manually approved face assignments. It
must repeat the current library ID, `source_digest` and exact `indexed_ids` from
the first artifact; face assignment rows must match current face detections.
Never infer a name, relationship, account ID or face identity from a model label
or a similar display name. Keep `allow_zero` explicit for a catalog person who
has no approved face assignment. The second producer invocation with `--review`
re-reads the source and refuses a stale digest, moved scope or mismatched face
row. It writes a new artifact once; it does not approve the review or activate
an application runtime.

The second invocation uses the same producer with `--review` and a new output
path:

```text
python server/scripts/prepare_access_discovery_index.py \
  --database /private/operator/library.sqlite \
  --library LIBRARY_ID \
  --revision 2 \
  --review /private/operator/review.json \
  --out /private/operator/reviewed-index.json
```

For kinship, bind each intended logical person with the exact reviewed catalog
`person_id` and current expected `label`, or rely on a unique explicit proper
name/alias match. A binding does not come from `account_id`, relationship words,
face clusters or a model prediction. Missing, duplicate or stale matches stay
unresolved until a person reviews the private roster and graph. Rerun the
readiness check after correcting the private inputs; never put those values in
the source review examples or report.

Run `check_private_search.py` against that artifact with `--kinship` only when
an existing private graph is intended for this library/account scope. The
readiness report separates reviewed people from the graph's catalog bindings;
resolve missing, ambiguous or stale entries through operator review and rerun
from current source. Cases, graph, token, database, index and report remain
outside Git and source packages. Use fictional records for source tests; real
family names, account bindings and relevance cases stay in private artifacts.
Readiness is an operator aid, not permission to enable production search or
evidence of household relevance.

The production factory and operator CLI explicitly allow up to 64 MiB of
serialized search-v2 source, while legacy discovery retains its 16 MiB limit.
Both use the same admission semaphore and retain the 100,000-row, index,
response and cancellation limits. Search v2 has a fixed five-second per-read
deadline; legacy discovery retains two seconds. This bounds the larger text
projection without changing the legacy allowance. An explicitly supplied budget
inherits its own source/deadline limits unless its caller selects separate
search allowances. The independent text fallback excludes superseded captions
at SQL selection time, so historical caption revisions cannot consume the
current-text projection. Current caption edits, supersession and ambiguity
still invalidate the source binding. The allowance is bounded capacity, not a
claim that every library fits or that a query meets a user latency target.

## Private operator command

Prepare an existing login token in an owner-only file, outside every Git
repository. Case, graph and report files also stay outside Git, with an
owner-only parent and file permissions (POSIX directory 0700/files 0600, or
the equivalent checked Windows owner/DACL). All paths must be absolute, with
no symlinks, reparse points or parent traversal. The output must be new.

```text
python server/scripts/check_private_search.py \
  --database /private/operator/library.sqlite \
  --library LIBRARY_ID \
  --index /private/operator/reviewed-index.json \
  --token-file /private/operator/token.txt \
  --cases /private/operator/search-cases.json \
  --out /private/operator/new-search-report.json
```

Use native absolute paths on Windows. Omit `--cases` for readiness only. Pass
`--kinship` only for an existing private graph with reviewed bindings; future
account preapproval does not grant access. If the database has an original
deletion marker, supply the existing paired `--deletion-journal` and
`--deletion-namespace`. The CLI never creates or upgrades that journal and opens
both databases read-only. It neither approves nor refreshes an index. A missing
or stale index requires the separate reviewed index workflow.

Membership is checked before the index or private graph is loaded. Each case
and the final report boundary recheck the initial source binding. Revocation or
invalid inputs refuse output; source change/unavailability/busy produces only a
fixed status with readiness/evaluation cleared. No partial cohort score survives
a source change. Do not run against changing sources and interpret that failure
as a relevance result.

The CLI prints only completion/status, report SHA-256 and case/failure counts.
Exit 0 means a current report and all supplied expectations passed; 3 means a
source boundary failed or an expectation mismatched; 2 means refusal/incomplete
operation; 130 means interruption. After an interrupted/write-failed invocation,
inspect any newly created file privately. Reports are never overwritten.

## Cases and measurements

Cases are versioned UTF-8 JSON, at most 1 MiB, with 1–100 cases. This fictional
example checks search, refinement and ordinal opening:

```json
{"version":1,"cases":[
  {"id":"first","text":"找视频","expect":{"kind":"results","filters":{"media":["video"]}}},
  {"id":"year","after":"first","text":"只看2025年","expect":{"kind":"results"}},
  {"id":"open","after":"year","text":"打开第二个","expect":{"kind":"open"}}
]}
```

The example is a shape illustration, not a promised result for every library.
Keep actual queries, expected IDs and relevance judgments in the private case
file. IDs are distinct positive decimal strings. Case names are local references
and never appear in reports. `after` refers to an earlier case's actual current
context; a missing context fails the dependent case without executing it.

`expect.kind` is required: `results`, `open`, `clarification` or `unsupported`.
Optional `filters` and `effect` compare the complete expected JSON value.
`top_ids` checks an exact prefix of up to 20 results; an empty array requires no
results. `total` checks the exact count. Nonempty `relevant_ids` (up to 20) checks
a hit and reciprocal rank in the first 20 results. Clarifications and empty
pages count as misses. `absent_ids` (up to 100) proves absence only for a complete
page (`has_more: false`); a continuing page fails that check conservatively.

The report contains aggregate pass/failure counts, MRR@20 for labeled cases and
per-case numeric ordinal, boolean checks, result count and elapsed milliseconds.
It excludes query text, case names, labels, IDs, returned prose, filters,
contexts and effects. Opening is evaluated as a returned navigation instruction;
the runner never opens media, executes navigation or speaks. Timing measures
local protected retrieval/interpretation, not network, ASR, TTS or device UX.

Keep positive relevance, hard identity/date/filter correctness, no-match and
denied-account trials separate. A public source fixture cannot stand in for an
owner-reviewed household query set. Choose ranking improvements only after
incorrect identity/date/filter behavior and missing source coverage are known.

## Conservative video capture dates

The video probe now accepts only the exact
`com.apple.quicktime.creationdate` tag from the format or first video stream.
It requires a valid full timestamp with an explicit offset (Z or at most
±14:00), rejects malformed/conflicting candidates and preserves the recorded
local clock/day. Generic `creation_time`, filenames, receipt dates and file
mtime do not become capture dates. FFmpeg's own discussion explains that generic
creation time may describe container/presentation rather than content creation:
[FFmpeg metadata discussion](https://ffmpeg.org/pipermail/ffmpeg-devel/2023-April/308375.html).
An embedded tag remains source metadata, not independent proof of when a scene
happened.

New video ingestion copies an accepted timestamp to existing `assets.taken_at`.
The video-probe worker fills only a null value and preserves any existing value.
Unknown dates remain null. Offset/source diagnostics are returned by the probe;
the existing naive database column does not retain them separately. This slice
does not add complete per-row provenance, repair historical dates or enqueue a
backfill. A historical remediation needs a separate reviewed proposal and
production-write authority. A successful later write changes the source digest,
so the reviewed index must be refreshed before date search can use it.

## Local checks

The three readiness/evaluator/CLI suites are part of `tools/check.py api` and
use generated databases, without providers. Video worker tests are optional and
have a separate small dependency overlay:

```text
python -m pip install --require-hashes -r config/requirements-video-test.lock
python -m pytest --noconftest -c config/pytest.ini -q server/tests/security/test_video_capture_dates.py server/tests/security/test_uploaded_video_tasks.py
```

The video fixture injects fictional caption-prompt text for legacy worker import
and confines import-created derived directories to a temporary directory. It
does not instantiate model services. With installed FFmpeg/ffprobe, a generated
blue MP4 verifies the real tag/probe path; otherwise that one test is skipped.
Parser, ingestion propagation, null-only worker updates and protected date
filtering use generated data. No native Windows, deployed worker, household
library or physical-device acceptance follows from these local checks.
