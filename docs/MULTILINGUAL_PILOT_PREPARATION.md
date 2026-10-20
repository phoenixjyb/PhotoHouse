# Multilingual image index and owner pilot preparation

Semantic search remains disabled. This source provides a CPU SigLIP2 adapter,
an unpublished image-index builder and a protected ASGI qualification canary.
It does not install a service, publish vectors into the production database,
bind a family account or enable a feature. Model acquisition remains a separate
Windows operation; no model weights belong in the Mac source checkout.

## One compatible image/text identity

`server/scripts/semantic_siglip.py` reuses the pinned local model loader,
single-frame JPEG/PNG decoder, tokenizer validation and normalization from the
[multilingual encoder qualification](MULTILINGUAL_ENCODER_QUALIFICATION.md).
It requires the seven exact artifact pins and package versions, local-only
loading, CPU float32 and two Torch threads. Image and text identities share
the 768-component joint space and checkpoint. Each role has its own recipe
hash, binding exact preprocessing, source and dependency receipts. The text
recipe preserves original UTF-8 query identity while explicitly lowercasing
model input. Overlength text is refused, never truncated.

The adapter checks source/model stat identities around inference and verifies
full hashes at startup and explicit batch verification. An operator-supplied
`JointSpaceBinding` must exactly match both derived identities. Existing
512-component OpenCLIP vectors or a changed tokenizer/preprocessor cannot
masquerade as this model. Unsupported exclusion/strict-condition meanings are
refused inside the provider as well as at the protected search boundary.

## Private unpublished image cohort

`server/scripts/build_multilingual_image_index.py` is plan-only without `--run`.
Run mode requires explicit private configuration and a new private output
directory outside source. Its closed `photohouse.multilingual_image_index_run.v1`
configuration contains `schema`, `model_directory`, `artifacts`,
`package_versions`, `cohort` and `max_elapsed_seconds` (30–1800).

The separate `photohouse.multilingual_image_cohort.v1` document contains exactly
`schema`, `library_id`, `reviewed: true` and `assets`. Each of 1–512 assets has
an exact positive SQLite `asset_id`, absolute `path` and `sha256`. A reviewer
owns cohort selection and its authority; this flag grants no library access.
The content fingerprint covers the library and complete asset-ID/source-hash
roster, excluding host-local paths. Inputs are bounded to 32 MiB per image,
256 MiB total and the existing single-frame decoder limits.

The builder writes private float32 NPY vectors and immutable artifact metadata
under a separate identity. Record IDs bind the complete cohort hash, asset ID
and image identity. `index.json` is written last, after source/model checks;
without it the candidate is incomplete. The inspector requires the frozen
expected cohort and checks its exact roster, source hashes, deterministic
record IDs, model recipes, metadata/file/component hashes and unit norms. A
shortened manifest, substituted source, corrupt tail or missing vector refuses
the whole candidate. There is no DB insertion, migration or legacy fallback.
Candidate files and failure evidence are retained for review rather than
automatically removed or resumed. Windows power-loss durability is unqualified.

## Explicit owner-only serving

`server/scripts/serve_multilingual_semantic_text.py` provides plan, `probe` and
`serve` operations. Its closed `photohouse.multilingual_text_provider.v1`
document names `model_directory`, `artifacts`, `package_versions`, `binding`,
`credential_file` and `port`, plus `schema`. Serving requires an exact binding
and a separately stored private bearer token before a listener is created.
The existing authenticated provider transport enforces loopback peer/Host,
body/time limits, one inference lease and bound response/refusal receipts.
The CLI listens on `127.0.0.1`, with one worker and request logs disabled.
Import and planning never read private files, load ML or start listeners.

The protected API runtime configuration has an explicit version 2, extending
version 1 with `pilot_owner_account_id`. It requires both that exact
authenticated account and current approved library-owner capability. The gate
runs before request-body/metadata/provider/vector reads and is checked again
before releasing ranking results, including restored server-owned snapshots.
Direct construction of a 768-component runtime also requires an owner ID.
Version 1 keeps the existing legacy schema and cannot bypass this 768-component
owner requirement. Account display names and phone labels are not authority.
No actual family account is configured by this source change.

## Protected latency measurement

`server/scripts/qualify_multilingual_pilot.py` validates an explicit index and
reviewed cohort, then creates new synthetic accounts, credentials, a temporary
SQLite database and copies of derived vectors. It loads the real version-2
runtime configuration and uses the production API/provider ASGI boundaries
with an injected in-process HTTP transport. It opens no production DB or
application listener and creates no real account sessions.

Its closed `photohouse.multilingual_pilot_run.v1` configuration contains
`schema`, `model_directory`, `artifacts`, `package_versions`, `index`, `cohort`,
`queries`, `repetitions` and `max_elapsed_seconds`. One to twelve operator-supplied
positive probes have exact `id`, `language` (`en`, `zh`, `zh-en`), `text` and
`relevant_asset_id`. Repetitions are 1–10. The receipt fingerprints the exact
query plan and records only query hashes, timings and top-one comparisons.
The script does not invent a relevance acceptance threshold. A native packet
must separately pin its exact cohort/query plan before measurement.

Checks cover a viewer, another owner, an invalid token and an oversized denied
body before vector/provider work; multilingual exclusion clarification;
hard date filters; corrupt/missing eligible vector refusal; membership role
and session revocation during provider execution; and a new request after
restoring the disposable fixture state. Mid-request role/revision changes can
return access denial or stale-source refusal, always without cards. Snapshot
restoration is covered separately by source unit tests.

Warmup is separate from repeated p50/p95/max request timings. These samples
include ASGI admission, SQLite authorization, vector reads, encoding, ranking,
rechecks and serialization. They exclude TCP/TLS, phone networking, large-library
coverage, GPU performance, peak-memory/load acceptance and family relevance.
Every result keeps `activation_approved: false`. Production cohort publication,
account binding, serving installation and activation remain separate gates.
