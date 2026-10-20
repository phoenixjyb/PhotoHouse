# Private family-library semantic qualification

Semantic search remains disabled. The image builder, coverage planner and
temporary network canary prepare evidence; none publishes production vectors,
binds a real account or enables search. Household rosters, paths, queries,
review labels and measurements remain in private operator storage on the
data-owning host. No family media or model weights belong in the Mac checkout.

## Complete coverage planning

`server/scripts/multilingual_library_coverage.py` is a pure, import-safe planner.
Its closed `photohouse.multilingual_library_snapshot.v1` input contains exactly
`schema`, `library_id`, `source_revision_sha256` and `assets`. Each asset has
an integer SQLite `asset_id`, canonical absolute `path`, `db_source_sha256`,
`mime`, integer `width`, `height`, `bytes`, and collector-owned `file_status`.
The collector must use an explicit current library and read-only catalog
snapshot; this source revision is metadata provenance, not a file-content hash
verification. A snapshot admits at most 100,000 unique assets.

The planner retains the complete roster and reports fixed blockers instead of
silently dropping files. Available JPEG/PNG candidates must be nonempty, at most
32 MiB, at most 8192 pixels per side and at most 16*1024*1024 pixels. These are
the existing decoder's bounds. Missing/unreadable/out-of-root/unsafe files,
unsupported types and invalid or oversized images remain visible as blockers.
Candidates are deterministically partitioned into batches of at most 512 images
and 256 MiB. The digest covers the complete snapshot, candidates, blockers and
ordered batches. The plan is explicitly unreviewed, with source-byte hashes
unverified; it cannot be supplied directly as a reviewed builder cohort.

`coverage_summary()` checks a separately verified artifact roster against that
exact plan. It reports valid partial coverage without treating it as complete.
Missing, stale, duplicate or foreign artifacts, or a different joint image
identity, cannot qualify candidate coverage. Whole-library coverage additionally
requires no blocked catalog images. The helper checks supplied metadata, so the
operator must separately inspect every artifact's bytes, identity and source.
Production coverage and activation remain false even when a private candidate
roster is complete.

Ordinary library originals may be hard-linked or have different ACLs from the
strict offline builder. Do not relax those private-file checks or change
original permissions. A bounded private input copy on Windows can preserve the
exact original bytes and DB source hash while satisfying the offline boundary.
The operator must verify approved-root containment, path/handle identity,
file size and source hash, current catalog provenance, private destination ACLs
and copy budget. Record the copy and retain failures. This is separate from
publishing an index or changing originals.

## Relevance review

Freeze the cohort, original English/Chinese/mixed queries and relevant/forbidden
photo labels before scoring. Bind review to source hashes and cohort/query
digests. Separate scene descriptions from reviewed person identity and kinship;
a scene match cannot establish a person's identity. Existing face confirmations
do not approve unseen faces or arbitrary scene labels.

Assistant visual review can prepare a diagnostic. Label it explicitly as
assistant-reviewed, retain ambiguity and unjudged items, and keep human/family
acceptance false until the owner judges the exact examples. Existing captions,
high similarity, or the model's own results are not ground truth. Show literal,
vague and contrast results separately by language. Exclusion/strict-condition
clarification is measured separately from ranking correctness.

## Explicit network canary

The existing `photohouse.multilingual_pilot_run.v1` configuration stays
listener-free. Version 2 adds exactly `network`, with `transport` equal to
`loopback_https_tcp` and absolute private `certificate`, `private_key` and
`ca_file` paths. Unknown modes or missing TLS material refuse; there is no
fallback to mocked transport.

`semantic_loopback_network.py` reserves IPv4 loopback sockets before constructing
the API origin and provider binding. One-worker Uvicorn servers use the supplied
sockets, bounded startup/shutdown, no proxy trust or access logs, and small
connection/header limits. The API serves HTTPS; the provider uses authenticated
loopback HTTP. The client trusts only the supplied run CA, verifies the IP
hostname, requires TLS 1.2 or newer, disables environment proxies and redirects,
and uses a two-second timeout. No system certificate-store changes are needed.
Private run certificates must be prepared separately with verified tooling.

The canary keeps generated accounts, sessions, SQLite fixtures and vector copies
separate from production. Existing owner, denial, exclusion, date, corruption,
missing-vector and mid-request revocation checks also run through the network
path. No successful measurement is written until owned listeners have stopped.
It fingerprints the CA/certificate and records its transport boundary explicitly.

Timings cover host-loopback protected API HTTPS plus real authenticated provider
TCP and CPU inference. The API client is reused after admission probes; the
production encoder opens a new provider connection per encode. First successful
model-request warmup is separate. These are not remote Mac/phone timings,
whole-family serving, concurrency, peak-memory or operational acceptance.
The outer native Job timeout and resource limits remain mandatory.

The serving cohort still has a 512-candidate cap. A complete multi-batch offline
inventory or index does not remove that cap. Whole-library serving needs a
separately qualified scaling design, complete current coverage, relevance,
operational and device checks before activation. See the
[pilot preparation record](MULTILINGUAL_PILOT_PREPARATION.md).
