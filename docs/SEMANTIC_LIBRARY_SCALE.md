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
