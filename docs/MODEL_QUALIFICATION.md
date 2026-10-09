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

The private evidence document uses schema version 1 and has these top-level
fields: `schema`, `kind`, `selection_sha256`, `selection`, `case_plan_sha256`,
`audio_plan_sha256`, `scope_roles`, `platform`, `started_at`, `ended_at`, and
`records`. Use the plan output hashes verbatim. Set `audio_plan_sha256` to the
canonical SHA-256 of the private audio inventory, or `null` when no ASR role is
in scope. Timestamps use UTC `YYYY-MM-DDTHH:MM:SSZ`. The measured window must be
no longer than six hours; evidence older than 30 days is reported stale.

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
is available only when the evidence platform matches the host OS. It hashes the
literal artifact, dependency-lock, preprocessing, and in-scope audio files named
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
