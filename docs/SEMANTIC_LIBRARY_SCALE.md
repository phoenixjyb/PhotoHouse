# Bounded multilingual library indexing and serving

Semantic search stays OFF. These tools prepare private candidates and an explicit
owner-only runtime; they do not publish vectors, create accounts or change services.

## Multi-batch indexing

Keep the existing builder's 512-image/256 MiB batch limits. Use the complete
current-catalog coverage plan to build each batch under its own immutable private
output. Completed batches can be verified and reused; never overwrite or silently
resume incomplete outputs. Originals and their permissions remain unchanged.

`multilingual_index_collection.py` assembles a complete expected roster of up to
100,000 photos and the exact deterministic planned batch partition. Its default
command is no-I/O planning. Explicit `assemble` takes private `--snapshot` and
`--batch-references` documents plus a new `--output-directory`. The latter JSON
contains exactly `batches`, a list of `{cohort_path,index_path}` references.
`inspect --collection` revalidates a collection; `stage --collection` with a new
`--output-directory` exports only verified derived vectors and metadata.

Every batch retains its pinned cohort/index bytes and full ID/source-hash roster;
all batches must share exact image and text identities. Duplicate, omitted,
foreign, stale or corrupt artifacts refuse the complete collection. Input-copy
paths may differ from catalog-original paths; asset IDs and exact source-byte
hashes bind them. Batch limits include bytes as well as counts, so a library may
need more than ceil(image_count/512) batches.

The collection stores the entire roster, including blocked IDs, and distinguishes
complete candidate coverage from whole-library coverage. Private JSON reads are
bounded to 64 MiB; the exported metadata manifest is bounded to 128 MiB. The
export writes a new flat vector root, verifies destination vectors/metadata,
rechecks collection pins, then writes its completion record last. Failures remain
private evidence. There is no database insertion or activation. Run explicit
native work inside a resource/time-bounded Job; these functions are not a daemon.

## Explicit large-cohort serving

Local configuration version 5 adds the optional
[reviewed semantic eligibility and coverage contract](SEMANTIC_ELIGIBILITY_DESIGN.md).
It partitions the full current active-image roster without narrowing ordinary
search. Coverage metadata and bilingual replies disclose reviewed omissions;
unaccounted or stale assets still refuse. The implementation is unactivated and
the actual family failure disposition/native qualification remain pending.

Semantic runtime configuration version 3 extends version 2 with `serving_limits`:
exactly `candidate_limit`, `source_rows`, `source_bytes`, `search_seconds`.
The candidate limit is 513–100,000; metadata rows at most 1,000,000, packed SQLite
source bytes at most 256 MiB, and cooperative request time at most 120 seconds.
Use measured values, not maximums by default. An exact approved owner account is
mandatory. Versions 1/2 retain the 512-candidate behavior and source-binding policy.
The larger read view retains the existing admission semaphore and response/index
limits; it does not grant additional concurrency or relax library authorization.

After hard filters, the runtime validates every eligible artifact before calling
the provider. It encodes the query once, re-reads/scans batches of at most 128
vectors, and retains only IDs/scores between batches. Missing, stale, duplicate or
corrupt eligible vectors refuse the whole search; there is no truncated shortlist.
Sorting is deterministic by score then numeric ID, with complete paging. Current
source and owner authorization are rechecked before releasing results. Conversation
contexts allow bounded larger totals and recover their server-owned first page
only after current whole-cohort verification, without replaying inference.

Packed SQLite bytes and vector I/O have separate bounds. A fixed 256 MiB aggregate
vector-read allowance covers both passes; bytes are reserved before payload reads.
Requests that exceed this allowance or their metadata/time budget refuse. Vector
memory is bounded by a batch; complete metadata and ID/score storage still scale
with the configured candidate count. This is exact CPU scanning, not ANN indexing,
a cross-request cache, a hard peak-memory receipt or whole-library latency proof.

## Narrow bilingual clothing normalization

The optional multilingual text provider version 2 adds `inner_binding` and
`normalization_policy` (`photohouse.bilingual_clothing_normalization.v1`). Its
outer binding must preserve the exact image identity and pin a new text recipe.
The recipe binds the unchanged inner binding, normalizer source and provider driver.
The raw provider version 1 remains unchanged.

The normalizer recognizes only complete color + garment + wearer constructions
in Chinese, English or the supported mixed form. Generic 衣服/服装 stays generic
`clothing`; 戏服/戏装 means `costume`; ambiguous 裙子 is preserved, while explicit
连衣裙 maps to `dress`. Unrecognized or extended requests stay intact; there is no
partial rewrite, inferred name/date/location, truncation or unrestricted translation.
Original query hashes remain bound to responses. Exclusion/strict-condition guards
run on original and derived text before encoding, including the fallback path.

Compositional source tests prove these boundaries, not retrieval quality. Native
before/after measurements use the frozen known regression plus a separately frozen
unseen-query case, preserve original labels, report every gain/regression and keep
human/family acceptance false. Complete household indexing, production publication,
account binding, protected device latency and operational acceptance remain separate.

## Qualification — October 20, 2026

Source `20f6ddba5f7af76b65eab86f385d15f2065fde20` passed generated checks for
actual builder/inspector/collection/staging of 513 artifacts, a 1,025-record
three-batch roster, 769 candidates at 768 dimensions,
and protected API paging with 515 eligible artifacts. Checks cover corrupt-tail
refusal before inference, hard filtering, vector-byte admission, mid-request
membership/source changes and conversation recovery without another model call.
The provider-v2 driver also passed a generated authenticated ASGI normalization
and original-query binding check. These are source fixtures, not household-scale
native serving or device performance acceptance.

The Windows CPU model comparison reused the existing private 32-image vectors,
with eight frozen known cases and one additional query case frozen before scoring.
That case uses previously seen photos; it is not a new image holdout. The unchanged
raw baseline reproduced the original literal clothing inconsistency. After the
bounded parser, all 24 variants of the original eight cases ranked a designated
relevant photo first. The additional case ranked a relevant photo second in all
three languages, improved from second/eighth/eighth without normalization.

| All nine cases / 27 queries | Raw | Normalized |
| --- | ---: | ---: |
| First relevant photo ranked first | 22/27 | 24/27 |
| Any relevant photo within five | 25/27 | 27/27 |
| Mean relevant-image recall within five | 89.815% | 97.222% |
| Mean reciprocal rank | 0.869 | 0.944 |

No first-relevant rank regressed in this small selected diagnostic. Multi-image
recall still differs by language, and the added case still misses first place;
do not interpret consistent first-hit ranks as identical complete rankings or
broad translation quality. Labels are assistant-reviewed, with human/family
acceptance false. Three unsupported exclusion probes refused before inference;
this does not repair the encoder's negation behavior.

The child proved an 8 GiB/four-process Windows Job before model imports, with a
600-second deadline, 16 GiB free-RAM floor and two CPU threads. It loaded the
existing seven pinned model artifacts and created no listener or image vectors.
Offline hub settings and Python socket-call guards were used; OS-firewall,
GPU, native larger-cohort HTTPS latency, load and peak memory were not qualified.
The image identity remained exact; only the composite text identity changed.

Independent model-free Windows readback verified all 266 packaged source files,
model/package pins, 32 artifact records, all 27 original/derived query receipts,
text-recipe binding and Job proof. It recomputed aggregate metrics from reported
ranks, not the model scores themselves. API task/listener/configuration and
phone/TV feed pointers were unchanged. Trusted Mac HTTPS checked UI 200,
anonymous session 401 and both update feeds 200; semantic remained OFF with no
semantic provider configuration. Private detailed evidence remains outside Git.

The full API profile passed **2746 tests and 3612 subtests** plus the
generated no-listener demo; seven packaging tests passed. Implementation and
documentation are local commits, unmerged and undeployed. Complete compatible
family indexing, blocked-file handling and real larger-library/device performance
remain open. No account binding, index publication or activation was performed.

## Full-library candidate preparation

The dedicated `library_semantic_index.py` worker accepts a frozen
`photohouse.library_semantic_snapshot.v1` roster and approved original roots.
It prepares private derivatives, uses `LibrarySiglipModel` in fixed batches of
eight, and writes immutable vectors with append-only batch checkpoints. Original
SHA-256 values remain the artifact source identity; derivative hashes and observed
image dimensions are separate receipts. Catalog dimensions never replace decoder
observations. This candidate workflow has no production publication path.

The preparation profile accepts single-frame JPEG/PNG up to 128 MiB, 256 megapixels
and 32,768 pixels per side. It normalizes EXIF orientation, converts to RGB, reduces
the longest side to 2,048 pixels, and strips metadata from the private PNG. The
profile, helper source, wrapper source and fixed-batch policy define a new image
preprocessing identity. Existing raw-image vectors cannot be relabeled with it.
The established text tower and its identity remain unchanged.

Original files are read-only and may have multiple hard links. Generated scratch
files must be private regular files with one link, outside original roots and
source. At most eight preparations are retained. A 32 GiB free-space floor is
checked between batches. Only verified, successfully checkpointed scratch files
owned by the current process are removed; failed or partial artifacts remain as
evidence. Missing, changed, unsupported or undecodable sources remain explicit
failures. An exact-hash alternative inside the same authorized library can be
selected in a frozen candidate roster without changing the production catalog.

A bounded slice can stop at a committed batch boundary with `max_new_assets`;
`resume=True` requires the same roster, model/preparation identities and roots.
It verifies committed work before continuing and never overwrites partial vector
files. Interruption inside an uncommitted batch or before scratch cleanup preserves
the files and refuses automatic resume until operator review; clean committed
batches are never silently re-encoded. Active and retained scratch share an
8 × 144 MiB ceiling. Final processing and complete source coverage are separate states: a
finished roster with failures is still incomplete coverage.

Ordinary Windows qualification jobs retain their 900-second cap. The explicitly
named `run_bounded_library_index` profile allows up to six hours, with fixed
8 GiB memory, four processes, a 16 GiB free-RAM floor and mandatory child Job
proof. It does not install a service or schedule future work.

`qualify_library_semantic.py` measures verified candidate vectors using temporary
synthetic accounts, captions and databases. It checks authorization before model
or vector access, multilingual exclusion clarification, hard date filters and
source-change refusal. Its optional network mode uses temporary loopback HTTPS
for the API and authenticated TCP for the provider, closing both before writing
a success receipt. This is host-local performance evidence; phone, remote-network,
concurrent load, broad relevance and family acceptance remain separate gates.
Semantic search remains OFF throughout this workflow.

The full-library network benchmark explicitly permits a 120-second API read
timeout within its existing search budget. Connect, write and connection-pool
timeouts remain two seconds, as does the provider client's default read timeout.
This qualification-only allowance is not a phone or production latency target.
Temporary sockets are owned immediately after reservation, including failures
during a second reservation, source validation or model binding; setup failures
preserve the synthetic fixture and cannot produce a success receipt.

## Full-family run and scale findings — October 21, 2026

The private Windows candidate worker at source `ad94d82` is processing a frozen
23,761-photo family roster in clean, resumable chunks. Six extreme-input probes
passed, including a roughly 200-megapixel panorama and an original around 56 MB.
This is image-only indexing; it does not establish video semantic coverage.
The final index, relevance rerun and independent current-roster readback are not
complete. Checkpoints and original failure evidence are retained.

Two catalog paths were missing at preparation time. One had an exact-hash source
inside the same authorized library; only the frozen candidate roster selects that
alternative. The other still needs a recoverable source. A separate exclusive-copy
restore proposal is prepared privately, without changing originals or catalog rows.
The running pass has also recorded a preparation failure. A resource-capped
private probe of the exact frozen preparer identified a 3,024 × 4,032 MPO
multi-picture JPEG stored under a PNG filename. The single-frame JPEG/PNG profile
refuses that container at its format guard, before pixel verification or decoding.
This establishes an unsupported format, not corrupted pixels. Original bytes and
stable file identity were unchanged. The failed preparation and private probe
copies remain retained; no failure was silently cleared or excluded.

MPO handling needs an explicit primary/auxiliary-frame policy and qualification
of preprocessing identity and vector reuse before integration. Changing the
running worker's frozen profile or relabeling existing vectors would invalidate
its identity evidence. The current run therefore keeps the refusal explicit;
MPO support and any original-path restoration remain separate unfinished work.

A generated 23,761-vector ASGI canary at source `de80bc5` passed all seven
protection checks and complete-candidate counts. Its three repeated language
samples took 76–94 seconds on this Mac while the API suite also ran. The image
index inspector and encoder were fixture substitutes, so this is neither actual
family-model relevance nor Windows, network, concurrent-load or device acceptance.
A single-request diagnostic identified repeated float32 component packing and
full-file/path checks as major costs; profiler phase times overlap.

Following source removes a checksum calculation immediately before the same
checksum is verified by canonical component validation. Packing performs builtin
numeric conversion in C while retaining exact type, finite float32 and unit-norm
checks. Mutable list inputs are copied into a bounded snapshot, and the checksum's
dimension tag comes from the packed bytes. Golden and differential tests preserve
canonical bytes across rounding, signed zero, subnormals, overflow and invalid
numeric types. Endpoint tail tests still refuse malformed checksums and nonunit
vectors before the provider runs. Both file-validation passes remain in place.
These serving changes leave the running worker's frozen image preparation and
model identities unchanged.

An intermediate three-sample canary failed its final synthetic-source restoration
check; that attempt and its fixture remain retained. A logged follow-up at
`9b9641b` passed all seven checks, including source-change refusal and restoration,
with one repeated full-cohort sample around 35 seconds. This was a diagnostic
follow-up, not a controlled cross-version comparison or closure of the broader
performance gate. The final three-language canary at `9eae2d7` also passed all seven checks,
with 23,761 candidates in every repeated sample: median 48.2 seconds and p95
55.5 seconds (three samples). It ran alongside local API checks for part of the
invocation. The failed earlier run remains unresolved as a reliability observation;
successful follow-ups do not establish concurrent-load acceptance. These timings
leave interactive serving performance unqualified.

The complete API profile at `9eae2d7` passed **2,808 tests and 3,628 subtests** plus
the generated no-listener demo, with matching source and commit identities at
both boundaries. Seven packaging tests passed. Its 270-file source-only archive
is prepared privately; it has not been deployed. Independent review covered socket
ownership, bounded HTTP read timeouts and canonical validation compatibility.

Real full-library HTTPS/TCP performance remains held. The actual runtime preflight
refused because the incumbent API task was not running during a separate exclusive
service-recovery window. A read-only configuration check still found semantic OFF
with no semantic provider configuration. This search round performed no service,
scheduled-task, production database, original-media or account changes. Prepared
foreground follow-up controls have not been frozen or started; they must recheck
service recovery, exact runtime pins and final current-roster coverage first.
No automation or recurring job was installed.

Remaining gates include resolving unavailable inputs without hiding failures,
finishing and independently verifying the real index and relevance receipts,
measuring protected Windows and device latency, and qualifying current-library
refresh, concurrency and broader family relevance. The generated large-library
checks demonstrate capacity and protection, while their request times still leave
a substantial serving-performance gap. Semantic search remains OFF.


## Latency and MPO qualification — October 21, 2026

Source `5da29ba` removes repeated root/ancestor walks inside each vector read and
uses native lexical path strings for the remaining before/after walks. Each
ancestor still must be a directory without a symlink or Windows reparse point.
File identity, size, bounded reads and full container digest checks remain in
both passes. Streaming ranking no longer repeats component validation immediately
before the ranker performs the same checksum, dimension, finiteness, identity and
unit-norm validation. The complete pre-inference validation pass remains, as do
current source and membership checks before releasing results.

A sequential generated 23,761-vector comparison used the same fixture, fake model
and index inspector for baseline and changed code, with one sample for each of
English, Chinese and mixed input. All seven protection checks and complete
candidate counts passed in both runs. Median request time fell from **21.3 to
17.3 seconds** (18.7%); p95/max fell from **23.1 to 17.5 seconds**. These are three
samples per version, baseline first, without randomized order or controlled
filesystem/thermal conditions. The earlier 48–55-second samples ran under a
different competing workload and are not the comparison baseline.

The next source increment reuses derived metadata only within one request and
only for an identical freshly computed opaque source binding. Every read still
reauthorizes and validates the complete current source; a new reader has a new
cache. A changed note invalidates the old binding and new requests rebuild their
literal facts. Component arithmetic now uses builtin iterators with unchanged
float32 packing, checksum, finiteness, norm and identity checks; differential
tests compare normalized components and scores bit for bit with the old path.
No authorization, path or vector validation decision is cached across requests.

A further generated 23,761-vector canary passed all seven protection checks with
complete counts across three language samples: **13.7 seconds median, 15.0 seconds
p95/max**. Its receipt records the actual modified source hashes. This invocation
followed a Mac reboot and may have briefly overlapped focused tests; it is not a
controlled cross-version speedup measurement. Phase profiling found substantial
component and repeated metadata work as well as file access costs. These checks
use a fake encoder and index inspector; actual model, Windows, network, device and
concurrent-load acceptance remain separate. Interactive serving is still too slow.

The full API profile at `5da29ba` passed **2,829 tests and 3,628 subtests**, plus
the generated no-listener demo. The packaging inspector passed **26 tests and
seven subtests**. The next increment, `a61de0d`, passed **2,838 tests and 3,630 subtests** plus
the generated demo, with matching start/end source and commit identities. Its
combined focused retrieval checks and expanded exact-boundary input tests also
passed.
Independent review found no protection regression in the request-local cache.

`library_mpo_inputs.py` adds a separate worker-only primary-frame preparation
profile. It bounds the MPF table to 2–16 entries before Pillow opens the file,
checks all declared image ranges and overlap before scanning, and prepares only
frame zero as metadata-stripped RGB PNG. Auxiliary pictures are never sought or
decoded. The original-copy/hash/stat and resource-cap requirements remain. The
base JPEG/PNG preparation module, model adapter and index source are unchanged.
This standalone profile is not integrated with the current model, index, serving
configuration or activation path. Existing vectors cannot be silently relabeled.

The initial strict profile refused the actual eight-picture MPO because the
primary length field was 4,195 bytes short. Separate bounded diagnostics found
that strict whole-container frame-zero decoding succeeds, and the first physical
JPEG EOI ends exactly at the earliest auxiliary start. All seven auxiliary ranges
have exact JPEG framing. This establishes a length discrepancy, not its cause;
no original metadata was repaired or rewritten.

The new **v2 recipe** accepts an undercount only when the first primary EOI is
at or after its declared end, at or before the earliest auxiliary, and within
**65,537 bytes** (one maximum JPEG segment including its marker). Scanning stops
at the smaller bound. Declared and actual primary sizes are both recorded.
Auxiliary framing remains exact, permissive Pillow truncation mode is refused,
and all table/range checks precede image decoding. The MPO and unchanged legacy
input suites passed **46 tests**, including the exact undercount bound, one byte
over it, corrupt tables, overlap, truncation, primary-only pixels and cleanup
ownership refusals.

A fresh Windows/Pillow 11.3 worker qualified that actual file under v2 in **2.5
seconds**, with a mandatory 120-second / 2 GiB / two-process Job. Strict primary
pixels produced a 1,536 × 2,048 metadata-free PNG, with zero auxiliary seeks.
Original hash/stat, control/source hashes and semantic-off configuration were
unchanged. The worker loaded no model, opened no database and reported no socket
attempts; its process-local socket denial does not establish OS firewall isolation.
The private derivative and all earlier failures are retained. This qualifies one
input preparation, not an indexed vector or general MPO library coverage.

Index recovery preserved the original candidate and its failed scratch instead
of relaxing its nonempty-scratch guard. Only the verified committed prefix was
copied into a fresh private candidate: **8,431 ready photos and one failure**.
A transport timeout and Mac reboot interrupted local observation; independent
native readback confirmed the copy had completed before indexing resumed once.
That earlier observation had **1,218 committed batches** and no new child failure.
The frozen 23,761-photo roster and original JPEG/PNG worker identity remain;
MPO v2 is not spliced into that running index. Full indexing, final current-roster
coverage and full-library relevance remain unfinished. No recurring automation
or scheduled task was installed for this work.

The separate recovery task reports and records its completed exclusive window,
with original worker states restored and the incumbent API/schema unchanged.
Protected native serving checks still require fresh runtime pins, completed index
receipts and current-roster readback. This search round changed no production
database, original media, account, task or service. Source remains local, unmerged
and undeployed; the private index remains unpublished. Semantic search is **OFF**.


## Bulk serving and request budget follow-up — October 21, 2026

Local source `e4f06a5` introduces a separate, explicitly selected bulk-vector
format. It builds from validated image artifacts without replacing their NPY
files or changing the index recipe. The serving container is authoritative when
selected; the NPY files remain build provenance, with no query-time fallback.
Version-4 runtime configuration requires an exact owner, explicit serving limits,
a matching image-space identity, a private disjoint container path and a pinned
whole-file checksum. Existing versions and semantic-off defaults are unchanged.

Every snapshot validates the complete current ready-artifact cohort, library,
image identity and current asset source hashes. The private container is read and
hashed before and after encoding, with regular-file, link/reparse, ancestor,
permission and identity checks. Immutable canonical vector blocks may be reused
only for the same validated cohort and file; membership and source decisions are
not cached across requests. File reads are charged before their payload is read.
The file is capped at 128 MiB, retained canonical blocks at 256 MiB, and the
configured cohort at 100,000 candidates; a container that exceeds its byte bound
refuses even if its candidate count is otherwise permitted.

Scoring retains exact legacy normalized components, `math.fsum` results and
numeric-ID tie order across all eligible candidates. Hard people, date, tag,
place and literal-text filters remain gates. Unsupported exclusions clarify
before vector/provider reads; this does not claim exclusion filtering is
implemented by visual ranking. Authorization and current-source reads still run
before cards are released. Corruption, changed cohorts, revoked membership,
source changes during encoding and exceeded budgets refuse without NPY fallback.

Source `f5018e4` additionally captures one limits view per request instead of
copying it during each row's deadline checks. The view and reader preserve the
original admission semaphore. Focused checks verify a fresh view on the next
request, cancellation and elapsed-time refusal before provider execution.
Independent read-only reviews found no material issue in either implementation.

A generated 23,761-vector diagnostic on a shared Mac measured **6.32 seconds
median / 7.20 seconds maximum** for the initial bulk path. The follow-up with
request-local budget capture measured **3.93 seconds median / 3.98 seconds
maximum**, with a **6.73-second cold request**. Each invocation used one timed
sample per English, Chinese and mixed query; all seven protection checks and
complete candidate counts passed, with zero individual NPY query reads. Earlier
attempts include a refused baseline and a highly variable 23.8-second bulk
median; those artifacts remain retained. Order, host load, swap and filesystem
cache were uncontrolled, so these observations establish no controlled speedup
ratio or p95 service SLO. The encoder and index inspector were mocked. The
2-second backend target and actual Windows/model/network/device latency remain
unqualified.

Full API qualification at `e4f06a5` passed **2,865 tests and 3,651 subtests** plus
the generated no-listener demo. At `f5018e4`, **2,866 tests and 3,651
subtests** plus the demo passed with identical source and commit identities at
both invocation boundaries. Bulk, endpoint, configuration, packaging and
qualification checks are included in that profile. These are local CPU fixture
checks, not deployed or hardware acceptance.

A newer private index observation supersedes the earlier running count:
**2,078 committed batches / 16,624 processed assets = 16,595 ready + 29 failed**.
A new chunk refused at the frozen worker's nonempty-preparation guard. Inspection
found 27 retained private original copies totaling about 13 MiB, all matching
committed preparation-failure source hashes. Signature-only inspection found
23 JPEG-unclassified copies and four unknown 4,096-byte files; none was decoded,
repaired or retried. These failures must not be assumed to be the already
qualified MPO case. Originals, ready vectors, failure rows and old controls are
preserved.

A private recovery proposal describes a durable intent, same-volume rename of
the whole failed preparation folder into a fresh private control stage, an empty
replacement folder, unchanged-prefix verification and a one-shot continuation
for the remaining **7,137 assets**. It is a proposal with local decision-rule
tests, not an executed quarantine or runnable continuation. Current native
process closure, exclusive ownership, ACL/link/stat checks, complete committed
inventory and fresh input pins must be established first; partial journals must
never trigger automatic replay. The frozen JPEG/PNG model recipe remains
unchanged, and MPO v2 remains separate.

No production database, account, media, service, scheduled task or runtime
configuration changed in this source round. The private index is unpublished;
semantic search remains **OFF**. Remaining work includes safe indexing recovery,
failed-input disposition, final current-roster coverage and relevance, bulk
refresh/retirement/deletion integration, real protected latency and family/device
acceptance before any activation proposal.


## Guarded index recovery preparation — October 21, 2026

A private recovery implementation now preserves a failed preparation folder by
moving the entire directory into a fresh, separate private control stage on the
same volume. It creates an exclusive flushed intent before the rename, verifies
retained bytes and file identities, creates a private empty replacement, and
rechecks the unchanged committed prefix before writing completion. Any unknown
control file, prior receipt, stale scratch, lost controller lease or interrupted
operation stops for manual inspection. No rollback, deletion or automatic replay
is implemented. The file is fsynced; this does not claim Windows parent-directory
fsync or protection from storage failure. Fresh stage, claim, destination and
cohort checks provide separate replay guards.

The native controls validate canonical non-reparse ancestors, private ACLs on
executable source files, the exact frozen source-file set, source/archive hashes,
old Windows controls, complete scratch ownership and the expected model recipe.
Scratch hashes use bounded reads through a checked file handle with before/after
metadata checks. A named mutex serializes cooperating controllers through the
child's completion, supplemented by checks for old candidate Python processes.
It is not an OS-wide write lock against uncooperative privileged processes.

The proposed real operation invokes the frozen normal committed-prefix verifier;
that verifier reads and hashes original media on Windows and validates all ready
vectors and metadata. It does not copy originals or models to the Mac. The
resume targets the existing private index, retains all old failed rows, and
starts exactly one child for at most 8,192 new assets. The existing recipe and
six-hour / 8 GiB / four-process child Job with a 16 GiB free-RAM floor remain
unchanged. There is no production database, API, task, service or activation path.
Python socket guards include datagram sends; this is not OS firewall isolation.

The generated core suite passed **10 local tests**. A fresh Windows rehearsal
passed the same **10 tests**, plus actual private ACL/canonical-path checks,
whole-folder inode/content preservation, named-lease collision and replay refusal.
Its real child Job proved flags `0x2208`, 2 GiB memory and four processes under a
120-second limit. Those are rehearsal limits, not the proposed indexing limits.
No model, family media, committed family-index contents or production database
was opened by the rehearsal. It did stat the candidate index directory and read
frozen source, reference controls and the pinned semantic-off configuration.

Two earlier rehearsal attempts are preserved. The first refused before child
creation because a Mac-only controller was incorrectly listed as a native file.
The second child refused before its fixture tests because its restricted
environment omitted a computer-name variable. The corrected packet separates
local and native pins, queries the actual hostname, and records child exit and
failure evidence. A separate readback verified all final staged input hashes,
the native completion receipt and child exit zero.

Independent lightweight candidate readback confirms **2,078 batches / 16,624
processed = 16,595 ready + 29 failed**, no final manifest and all **27 retained
copy hashes** unchanged. It did not revalidate vector payloads or original bytes;
full real-prefix verification is still required before quarantine. The frozen
roster has **7,137 unprocessed assets**. Neither the family-folder quarantine nor
the actual model/index continuation has run.

The separate API/task recovery window subsequently closed. An initial real
admission refused the coordinator’s own Windows virtual-environment launcher.
The corrected guard exempts only the immediate owned launcher after matching
its PID relationship, owner SID, executable, creation order and exact decoded
arguments; other candidate or unreadable Python processes still refuse admission.
Twelve generated process-scope tests and native launcher readback qualify this
exception. No source or model recipe changed.

The admitted prefix reader was deliberately stopped before any quarantine intent,
folder move or model child. Its read-only workload established that a full prefix
pass hashes **62,666,621,494 original bytes**; the earlier 30-minute parent budget
was inadequate for two full passes. Post-stop readback verified the same 2,078
batches and all 27 retained scratch hashes. Its stage is preserved and cannot be
replayed.

A fresh controller now shares **six hours** between all pre-child work and one
bounded indexing child, caps pre-child work at **three hours**, and reserves
**120 seconds** for postflight. The parent deadline is checked cooperatively;
this is not an OS-enforced deadline on blocked parent I/O. The child receives
only the remaining budget through its Job timeout. File, vector, media, recipe,
ACL, scratch and process checks are unchanged. The three-hour cap also covers
artifact checks and guards before child admission. Seven fake-clock cases add
deadline, invalid-clock and backward-clock coverage.

The fresh packet passed **29 local and 29 native Windows tests**, plus the actual
ACL, inode, lease, replay and owned-launcher checks. This new native rehearsal
uses the actual indexing Job profile: flags `0x2208`, **8 GiB / four processes**,
a 16 GiB free-RAM admission floor and a 120-second generated-fixture timeout.
Independent readback verified all ten staged inputs, completion and child exit
zero. It opened no family media or index contents and loaded no model. The
original 10-test / 2 GiB rehearsal above remains historical evidence.

At **15:03 China time on October 21**, independent readback confirmed the fresh
coordinator admitted with the exact owned launcher pair and no other candidate
processes. It had read about **8.37 GB**, used about **68 MB** of working memory,
and was performing the full-prefix verification. There was no quarantine intent,
folder move, model child, final manifest or failure receipt. All 2,078 batches
and 27 preparation files remained in place. These are verification reads, not
newly indexed images; checkpoint counts will remain unchanged in this phase. The frozen roster still has 7,137
unprocessed assets. Every real phase requires fresh config/resource checks and
the verified window-closure record. No recurring automation was created.
Final coverage, failed-input disposition, current-roster and relevance checks,
real protected latency, bulk lifecycle and family/device acceptance remain open.
Semantic search remains **OFF**. These private controls add no public runtime
code, deployment or new API regression claim; the last behavioral API evidence
remains **2,866 tests / 3,651 subtests** at `f5018e4` plus the generated demo.


## Completed index and lifecycle qualification — October 21, 2026

The guarded continuation completed natively after about **3 hours 16 minutes**
including verification and indexing. Independent receipt readback found the final
manifest and **23,696 indexed / 65 failed / 23,761 roster assets**, with no failure
receipt or remaining controller processes. Job proof remained `0x2208`, 8 GiB and
four processes. The local SSH transport timed out; this completion claim relies
on independently read Windows terminal receipts, not transport exit zero. The
readback itself did not rehash all originals or vectors. The original 27 scratch
copies were retained by the completed folder-preservation operation, and 36 new
copies remain in the index preparation directory. None was deleted or retried.
Failure codes are **64 preparation_unavailable + 1 source_missing**. File suffixes
are diagnostic only; these codes do not establish corruption or a repair recipe.
Processing is complete; searchable coverage is incomplete.

A separate fresh read-only production-catalog audit used `mode=ro`, `query_only`,
a bounded transaction/progress deadline and a 100,001-row admission ceiling. All
23,761 active family images matched the frozen IDs and source hashes, with zero
additions/removals and the exact original catalog digest. It read database rows,
not original media or vector payloads, and wrote no production data. Its first
read-only attempt refused before opening the database because the diagnostic
used the wrong Unicode JSON canonicalization; the corrected ASCII canonical
form matched the frozen contract. Both attempts are retained. This is a current
roster observation, not ongoing monitoring or authorization for activation.

Source `3aa43c6` adds bulk-specific lifecycle checks to the generated-account
qualification harness. Revoking its synthetic owner's membership must return
401/403 before any provider, vector or bulk reads, and exact restoration must
recover. A synthetic soft deletion or removal of a library scope link advances
only that harness's reviewed source receipt; the unchanged bulk container must
then refuse the stale complete cohort before inference or cards. The omission
case uses a date-filtered subset to check library-wide validation. All changed
synthetic rows and the old reviewed provider are restored in `finally`. Immutable
vector rows and supplied index files remain unchanged. A fault-injection test
makes the store reuse a stale cached snapshot and confirms qualification fails;
this is evidence that the validator catches the intended failure.

Focused qualification passed **53 tests / 24 subtests**. Full API at the exact
unchanged `3aa43c6` source passed **2,867 tests / 3,651 subtests** plus the generated
no-listener demo. These checks qualify refusal/recovery, not an implemented
refresh, atomic swap or retirement workflow.

A fresh source-only private packet stages the real bulk canary with 271 pinned
source files, unchanged model/preparation sources, a 30-minute / 8 GiB /
four-process Job, a 16 GiB free-RAM floor and two CPU threads. It validates the
completed index, builds a separate derived bulk file and synthetic database, then
measures three language queries three times through temporary loopback HTTPS API
and authenticated TCP provider listeners. No existing index is modified. The
packet's source/control compatibility was independently reviewed. The initial full-index audit passed: all 23,696 vector payloads and metadata,
complete checkpoint inventory, original-source stat identities and all 65 failure
records verified. It did not rehash original bytes. The native real-model canary
then completed successfully in about 29 minutes 41 seconds, including extensive
setup and before/after full-index verification. Nine fixed query samples (three
languages, three repetitions) measured **9.781 seconds median / 10.156 seconds
maximum**; its cold request took **18.297 seconds**. All **10 protected checks**
passed, including the three new lifecycle probes, with **zero individual NPY
reads during queries** and 30 bulk snapshots. Fifteen provider/model encodes
across queries, filters and recovery checks took 2.179 seconds in total (about
145 ms average). The two instrumented full-index inspections took about 991
seconds in total; that setup/qualification cost is separate from query latency.
Observer overhead is included.

Independent readback verified all nine staged inputs, the measurement hash and
native receipt agreement, original index-manifest hash and Job proof. It also
confirmed zero remaining candidate processes and test listeners. Postflight
preserved the exact API task/action/entry/config/listener identity and phone/TV
feed pointers. The Mac operator and its temporary sleep inhibitor exited. No
production services or tasks were controlled. A first readback diagnostic had a
template syntax error before executing its verification body; a fresh AST-checked
read-only diagnostic passed. The original failure evidence remains retained.

These measurements use the real Windows CPU model and completed family-derived
vectors, but synthetic accounts/catalog data and server-loopback HTTPS/TCP. They
are not phone/WAN, concurrency, broad relevance or service-SLO acceptance. The
**2-second backend target remains unmet**. The model encode timings point to
remaining request processing/validation/scoring cost; finer profiling is still
needed before attributing the delay to a specific function. No controlled
speedup ratio is claimed against earlier different/uncontrolled runs.

The serving canary's synthetic catalog intentionally contains only the 23,696
ready artifacts. It does not prove serving behavior for the actual catalog's
65 missing embeddings. Current semantic ranking refuses a candidate set that
contains an image without a compatible ready vector; narrowing ordinary
`ReviewedIndex` scope would alter or invalidate normal discovery rather than
provide a semantic-only coverage policy. The shared `indexed_ids` field is not
such a policy. A reviewed, library/source-bound semantic eligibility cohort and
visible partial-coverage/failure receipt are still needed before a pilot can
serve incomplete coverage. Ordinary discovery scope and privacy gates must
remain intact; benchmark success must not be treated as resolving this gap.
The [proposed eligibility and coverage contract](SEMANTIC_ELIGIBILITY_DESIGN.md)
records the next implementation and acceptance checks; it is not implemented.

Semantic remains **OFF**. No production API, task, configuration, database write,
account creation, index publication or activation is included. Remaining gates
include finer request-performance qualification, broad
family relevance and explicit failed-input disposition, refresh/swap/retirement
packaging, controlled source integration/deployment and an owner-only activation
proposal. Family/device acceptance remains separate.
