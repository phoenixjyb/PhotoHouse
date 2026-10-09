# Offline model qualification evidence

This checker reviews a private record of model runtime observations, resource
measurements, and human review of synthetic voice or story cases. It does not
collect those observations, run a model, contact a provider, or activate a
selection. A consistent report means only that the submitted record is
internally consistent for its stated roles and selections.

The checker supports `assistant_asr`, `memory_asr`, `assistant_tts`, and
`narrative`. It binds each role to the selected current or rollback branch of a
private [deployment manifest](MODEL_DEPLOYMENT_MANIFEST.md), the source quality
case plan, and—when ASR is in scope—a separate pre-run audio input inventory.
The source cases and rubric are in [`models/quality-cases.json`](../models/quality-cases.json).
Narrative bundle hashes correspond to the synthetic cases in
[`MEMOIR_QUALITY_CASES_V1.md`](../server/docs/security/MEMOIR_QUALITY_CASES_V1.md).

## Plan the review

Keep the manifest, evidence record, ASR audio inventory, and selected audio
files outside the checkout in private storage. The manifest and evidence loader
requires an absolute path outside the checkout and owner-private storage. Do
not put model weights, household material, credentials, local endpoints, or
private machine details in the repository or a public report.

From the repository root, print the safe role/case plan for a selected branch:

```sh
python3 tools/check_model_qualification.py \
  --manifest /private/operator/model-evidence/deployment.json \
  --selection current
```

Use `--selection rollback` to plan against the declared rollback bindings. The
plan prints the manifest selection hash, case-plan hash, per-role selection
identity hashes, and case IDs. It reports `qualification_plan`, with
`observations_collected: false` and `activation_performed: false`. It does not
read runtime or model files.

For ASR cases, prepare a separate private input inventory before the evaluation.
Its `case_plan_sha256` must match the source case plan; each entry binds a role
and case ID to the SHA-256 and absolute path of the exact synthetic WAV file to
be reviewed:

```json
{
  "schema": 1,
  "kind": "photohouse-model-audio-inputs",
  "case_plan_sha256": "<64 lowercase hex characters from the plan>",
  "inputs": [
    {
      "role": "assistant_asr",
      "case_id": "mandarin-memory",
      "input_sha256": "<SHA-256 of the exact synthetic WAV file>",
      "file": "/private/operator/model-evidence/audio/mandarin-memory.wav"
    }
  ]
}
```

The sample path is illustrative. The checker does not make audio, and it does
not infer an audio hash from the case's reference transcript. Keep this plan
private because it contains local paths. During explicit file verification, the
checker hashes the named WAV files and compares them with this inventory.

Print the inventory's canonical hash for the later evidence record with
`--manifest /absolute/private/deployment.json --audio-inputs /absolute/private/audio-inputs.json`.
Without `--evidence`, this remains a plan: it reads private metadata only and
prints `audio_plan_sha256` without inspecting the recordings. Canonical hashes
use sorted JSON keys, compact separators and ASCII escapes, not the file's
whitespace-dependent byte hash. Preparing an inventory before a run is an
operator procedure; the checker does not prove when the inventory was created.

## Record observations and review

### Capture one synthetic story output

The separate [`run_memoir_quality_canary.py`](../server/scripts/run_memoir_quality_canary.py)
can submit one pinned generated bundle without a family database, API, or worker.
Its default command validates the three source cases and prints a redacted plan:

```sh
python3 server/scripts/run_memoir_quality_canary.py
```

Execution requires an explicit operator action and authority for that provider
request. Create an owner-private configuration outside the checkout with exactly
these fields, substituting an already installed model:

```json
{
  "format_version": 1,
  "ollama_url": "http://127.0.0.1:11434",
  "ollama_model": "operator-selected-model",
  "timeout_seconds": 30
}
```

The URL must be an explicit loopback HTTP endpoint. No credential or ambient
configuration is read, and no model is downloaded or service started. Then select
one case and a **new** output directory under an existing owner-private parent:

```sh
python3 server/scripts/run_memoir_quality_canary.py --run \
  --case synthetic-coherence \
  --configuration /absolute/private/canary-config.json \
  --output-directory /absolute/private/new-coherence-run
```

The coherence and conflict cases use the narrative contract; the provenance
case uses the companion contract and can return an answer, clarification, or
proposal. The command makes one request without retries or fallback. Client
timeouts are at most 30 seconds; the adapter also checks an elapsed deadline.
This does not prove server cancellation or enforce GPU/RAM budgets. Use a
supervised execution boundary when needed and inspect failures before another
explicit run.

The private directory retains the exact canonical input and output bytes, their
hashes, selected provider configuration and its canonical identity, timestamps,
duration, and every quality criterion as `unreviewed`. Standard output contains
only case/task IDs, hashes and fixed status flags. Existing output directories
are refused before any provider request, and partial files remain after a
persistence failure. `captured_for_human_review` establishes capture only.

The canary's `record.json` is **not** a qualification document. Supply separately
observed runtime/artifact/device/resource identities and human review in the
qualification schema below. A captured proposal does not enable generation,
alter library stories, or establish story quality.

### Enter human judgments with a private worksheet

[`review_model_qualification.py`](../tools/review_model_qualification.py) exports
the existing quality entries from a valid private qualification record into a
smaller worksheet. It requires an all-unreviewed source record and does not
construct runtime observations from a canary response. Unknown identities,
missing measurements and missing cases remain qualification gaps.

```sh
python3 tools/review_model_qualification.py export \
  --manifest /absolute/private/deployment.json \
  --evidence /absolute/private/unreviewed-evidence.json \
  --audio-inputs /absolute/private/audio-inputs.json \
  --output /absolute/private/new-review-worksheet.json
```

ASR scopes require `--audio-inputs`; omit it for a scope without an audio plan.
All files must use owner-private storage outside the checkout. Outputs must be
new files under an existing private parent; links, reparse points and overwrites
are refused. The worksheet binds the original evidence, selection, source rubric,
input and output hashes. It contains no media, playback paths or generated prose.

Listen to or read the separately retained synthetic input/output matching those
hashes. Edit only each criterion's `verdict` (`unreviewed`, `passed`, or `failed`)
and the entry's `reviewed_by` and `reviewed_at`. Any reviewed verdict requires a
reviewer ID and UTC timestamp in `YYYY-MM-DDTHH:MM:SSZ` form, between the recorded
run start and the current time. Leave judgments unreviewed until the review is
performed; successful capture does not imply a passing judgment.

```sh
python3 tools/review_model_qualification.py import \
  --manifest /absolute/private/deployment.json \
  --evidence /absolute/private/unreviewed-evidence.json \
  --audio-inputs /absolute/private/audio-inputs.json \
  --worksheet /absolute/private/new-review-worksheet.json \
  --output /absolute/private/new-reviewed-evidence.json
```

Import preserves the source file and all runtime/resource observations. It
refuses changed identities, rubric definitions, case inventory or source
evidence. To revise judgments, retain the original unreviewed evidence and
worksheet, then import into another new output file. An already reviewed source
is refused so its judgments cannot be silently reset by export.

Exit code 0 means a worksheet or evidence copy was written. Failed and incomplete
reviews can still be written successfully. Run the existing qualification checker
on that copy to inspect its gaps. This tool does not read or hash media/weights,
verify the reviewer's identity or listening, measure resources, or activate a
provider. Its safe report omits private values and keeps independent quality
verification and activation false.

The private evidence document uses schema version 1 and has these top-level
fields: `schema`, `kind`, `selection_sha256`, `selection`, `case_plan_sha256`,
`audio_plan_sha256`, `scope_roles`, `platform`, `started_at`, `ended_at`, and
`records`. Use the plan output hashes verbatim. Set `audio_plan_sha256` to the
canonical SHA-256 of the private audio inventory, or `null` when no ASR role is
in scope. Timestamps use UTC `YYYY-MM-DDTHH:MM:SSZ`. The measured window must be
no longer than six hours; evidence older than 30 days is reported stale.

`platform` identifies the execution OS for the evidence scope. Every role in one
record must execute on that OS. For deployment-manifest schema 2, each role's
`observed_identity` must also include the exact declared `placement` object;
schema-1 runtimes remain native and do not add that field. The safe report
identifies the execution platform and a role-to-host-platform map, without
including placement instance names. A WSL2 ASR runtime therefore uses Linux
evidence and reports Windows as its application host. If another selected role,
such as native Windows TTS, executes on Windows, qualify it in a separate scope
and evidence record. Do not combine Linux ASR and Windows TTS in one scope.

Each role record contains `role`, `selection_identity_sha256`,
`observed_identity`, `runtime_capture_sha256`, `files`, `resources`, and
`quality`. This abbreviated example uses invented values and one TTS role; the
private evidence must include every field and every case required for each
listed scope role:

```json
{
  "schema": 1,
  "kind": "photohouse-model-qualification",
  "selection_sha256": "<manifest selection hash from the plan>",
  "selection": "current",
  "case_plan_sha256": "<case plan hash from the plan>",
  "audio_plan_sha256": null,
  "scope_roles": ["assistant_tts"],
  "platform": "macos",
  "started_at": "2026-10-09T01:00:00Z",
  "ended_at": "2026-10-09T01:05:00Z",
  "records": [
    {
      "role": "assistant_tts",
      "selection_identity_sha256": "<assistant_tts identity hash from the plan>",
      "observed_identity": {
        "runtime_version": "example-runtime-1",
        "implementation": {
          "repository": "https://example.invalid/provider",
          "revision": "0123456789abcdef0123456789abcdef01234567"
        },
        "dependency_lock_sha256": "<observed lock SHA-256>",
        "device": {"kind": "cuda", "index": 0, "hardware_id": "GPU-01234567-89AB-CDEF"},
        "artifact_sha256": "<observed artifact SHA-256>",
        "preprocessing_sha256": "<observed preprocessing SHA-256>"
      },
      "runtime_capture_sha256": "<SHA-256 of the private observation capture>",
      "files": {
        "artifact": "/private/operator/model-evidence/files/voice.bin",
        "dependency_lock": "/private/operator/model-evidence/files/requirements.lock",
        "preprocessing": "/private/operator/model-evidence/files/preprocess.json"
      },
      "resources": {
        "method": "owned_process_tree",
        "capture_sha256": "<SHA-256 of the private resource capture>",
        "sample_count": 20,
        "window_seconds": 300,
        "peak_ram_mib": 2048,
        "minimum_free_ram_mib": 4096,
        "minimum_free_vram_mib": 2048,
        "peak_concurrency": 1,
        "maximum_request_seconds": 8.5
      },
      "quality": [
        {
          "case_id": "mandarin-names-dates",
          "input_sha256": "<SHA-256 of the exact case text>",
          "output_sha256": "<SHA-256 of the reviewed speech output>",
          "criteria": {
            "mandarin_intelligibility": "passed",
            "names_numbers_pronounced": "passed",
            "uncertainty_preserved": "passed",
            "comfortable_pacing": "passed"
          },
          "reviewed_by": "reviewer-example",
          "reviewed_at": "2026-10-09T01:06:00Z"
        }
      ]
    }
  ]
}
```

For every quality case, provide the exact case ID and input/output SHA-256,
verdicts for every criterion defined in the source plan, and a private reviewer
ID and review timestamp. A missing review may be recorded with all criteria
`unreviewed` and both reviewer fields `null`; the report will mark it incomplete.
Keep audio, generated speech, story text, reviewer notes, and any source material
in private storage. The safe report omits those values. Case criteria cover
Mandarin fidelity and uncertainty for ASR, intelligibility and pacing for TTS,
and grounding, citation, attribution, and coherence for narrative. They are
bounded synthetic checks, not family acceptance or memoir-wide quality claims.

`observed_identity` is a recorded assertion compared with the corresponding
manifest declaration. It is not independently observed by the checker.
For a schema-2 runtime, include `placement` in `observed_identity`, exactly
matching the manifest's `kind`, `host_platform`, and `instance`; an incorrect
placement is reported as an identity mismatch. The instance is private metadata
and is omitted from the safe report.
`runtime_capture_sha256` and resource capture hashes identify private evidence
files but do not prove how those captures were produced. Resource observations
are compared with the declared RAM, free-memory, VRAM, concurrency, and request
limits. The checker does not enforce budgets; the shared memory ASR and
annotation-polish item budget is always reported unverified.

## Review the record

Validate the private record without hashing the named files:

```sh
python3 tools/check_model_qualification.py \
  --manifest /private/operator/model-evidence/deployment.json \
  --evidence /private/operator/model-evidence/qualification.json \
  --audio-inputs /private/operator/model-evidence/audio-inputs.json
```

The `--audio-inputs` option is needed when the scope contains ASR cases. A
record carries its own branch; optional `--selection current` or
`--selection rollback` checks that branch without overriding it. A
record may omit other model roles deliberately: `scope_roles` states the exact
review scope, and `other_declared_roles` lists declared roles outside it. The
checker reports `scoped_evidence_incomplete` if a scoped role is missing,
stale, mismatched, over budget, or has incomplete/failed human review. A fully
consistent scope reports `scoped_evidence_consistent`; neither status means the
whole deployment is qualified.

To explicitly verify the named files against the manifest and audio inventory,
add `--verify-files`:

```sh
python3 tools/check_model_qualification.py \
  --manifest /private/operator/model-evidence/deployment.json \
  --evidence /private/operator/model-evidence/qualification.json \
  --audio-inputs /private/operator/model-evidence/audio-inputs.json \
  --verify-files --hash-timeout-seconds 120
```

Hashing is limited to 28 explicitly named regular files,
64 GiB per file and 128 GiB total. Its soft deadline defaults to 120 seconds
and can be set up to 600 seconds with `--hash-timeout-seconds`; a host-level
process deadline is still needed for a blocked filesystem read. File verification
is available only when the evidence platform matches the host OS. For schema-2
WSL2 evidence, run it on the execution OS (Linux), with named files accessible
there; verify native Windows-role evidence on Windows. It hashes the literal
artifact, dependency-lock, preprocessing, and in-scope audio files named
in the private records. It performs no path search, model load, transitive blob
verification, service probe, or provider check. A successful literal-file hash
does not prove that a running process used that file.
Use operator-controlled local paths. Link/reparse and before/after identity
checks detect ordinary substitution or mutation; they are not a sandbox against
another process with permission to race parent-directory replacement.

The CLI returns code 0 for a plan or internally consistent scope, code 2 for an
incomplete scope, and code 1 for refused input. Reports contain hashes, role and
case IDs, fixed gap codes, and explicit false verification/activation flags;
they omit model names, endpoints, file paths, audio/text, generated outputs, and
reviewer IDs. `complete_deployment_qualification`,
`provider_probed`, `device_verified`, `runtime_environment_verified`,
`quality_independently_verified`, `resources_enforced`,
`shared_memory_item_budget_verified`, and `activation_performed` remain false.

## Separate qualification from activation

The evidence checker is read-only. Its report does not install dependencies,
inspect a live process, verify a provider's identity, independently verify a
device or runtime environment, establish semantic quality, enforce resource
limits, or authorize activation. File hashing adds only checks that explicitly
named files match declared hashes; it does not validate transitive model blobs.

Before activation, separately verify the installed runtime and artifact used by
the provider, the effective device, adapter behavior, measured resource limits,
and human-reviewed synthetic outputs. For embedding or recognition changes,
review versioned shadow outputs and reindexing effects. Keep rollback available
until the candidate passes its task-specific gates. Activation, deployment,
service restart, family data processing, and family acceptance remain separate
decisions and evidence.
