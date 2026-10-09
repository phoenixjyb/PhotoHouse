# Private model deployment manifest

The deployment manifest records an operator's declared choices for model
providers. It is private metadata, separate from the source catalog and from
inference itself. Its offline validator checks a declared graph against the
reviewed source catalog. A valid graph does not prove that a service, runtime,
checkpoint, system voice, GPU, license grant, or quality target is available.
The schema and loader are implemented in
[`model_deployment.py`](../server/backend/app/access/model_deployment.py); the
offline command is [`check_model_deployment.py`](../tools/check_model_deployment.py).

## Record location and handling

Keep the manifest outside the source checkout, at an explicitly selected absolute
path. Do not add a household configuration file to Git. The loader rejects paths
inside the checkout, `..` components, symlinks/reparse points, non-regular files,
hard-linked files, and manifests larger than 128 KiB. The containing directory
must already exist and pass private-storage checks; it does not create directories
or change permissions. On POSIX, use an owner-only directory (`0700`) and file
(`0600`); validation requires the current user to own them and rejects group or
other permissions. On Windows, the existing private-storage check inspects the
file owner and DACL and rejects untrusted access; it does not rewrite ACLs.

The sample [`models/deployment.synthetic.json`](../models/deployment.synthetic.json)
contains deliberately fake metadata and disabled bindings. It is for understanding
the schema only. Copy it to a separate private location, then replace every
placeholder with declared values; do not treat it as a working deployment or
evidence of runtime readiness.

## Graph structure

Schema version 1 links five record groups:

- **Runtimes** declare execution mode, operating system, environment identity,
  runtime version, dependency-lock SHA-256, implementation repository/revision,
  device identity, and resource budgets. Reuse an `environment_id` only for the
  same platform and dependency-lock digest. Give distinct dependency stacks
  distinct environment IDs. Keep VLM, ASR/TTS, face, and embedding environments
  separate when their package, accelerator, or resource needs differ; a single
  shared ML environment makes independent provider replacement risky.
- **Artifacts** declare artifact kind, model/voice name and version, artifact
  identity digest, license reference, preprocessing digest, and optional vector
  space (`id`, dimension, normalization). An identity digest is a declaration in
  this file; offline validation does not hash a local checkpoint.
- **Providers** bind a catalog role to one reviewed adapter symbol and contract,
  runtime, artifact, optional endpoint, and optional credential environment
  variable name. The adapter and contract must match the source catalog. HTTP
  endpoint values must be explicit loopback URLs with an explicit port and no
  user-info, query, or fragment. Text generation endpoints must use the accepted
  root or `/api/generate` path. The validator accepts credential variable names
  only (`A-Z`, digits, underscore); it neither reads environment variables nor
  returns secret values.
- **Bindings** select a provider for a catalog role and state whether that
  selection is requested enabled. Roles must be unique and every binding must
  refer to a provider whose declared role and contract agree.
- **Rollback bindings** identify a distinct, enabled provider for each enabled
  role. The provider must implement that same catalog role/contract. An enabled
  binding without an enabled rollback binding is invalid. Disabled selections
  need not have a rollback entry, but may predeclare one while the candidate is
  prepared. `rollback_declared_roles` includes those prepared entries;
  `requested_enabled_roles` includes only enabled current selections. Neither
  field reports an installed or active provider.

The catalog also inventories implementation symbols that are not selectable
request adapters. `CaptionSubprocessProvider` is not an HTTP provider, and
`WindowsSystemSpeech` implements the speech service rather than its HTTP client.
This manifest version refuses both selections. Select `HTTPCaptionProvider` for
the current caption HTTP contract and `LocalAssistantTts` for the speech client;
a Windows system-voice artifact describes the implementation behind that service.
A subprocess caption binding needs a separately reviewed bounded bridge.

The current schema also enforces role-specific constraints: face embeddings use
512 dimensions; approved image/video embedding model names use the supported
`clip-` family and declare unit L2 normalization; and a Windows system-voice
artifact can only serve assistant TTS.
When image and video embedding bindings are both enabled, they must declare the
same vector-space ID. Each vector-space ID and model/version pair must retain one
consistent artifact, preprocessing, and vector identity. Face, image, video, and
text vector spaces remain distinct contracts; a matching vector dimension alone
does not establish compatibility.

## Offline validation

From the repository root, select the private manifest explicitly:

```sh
python3 tools/check_model_deployment.py --manifest /absolute/private/path --json
```

To inspect a target-specific projection, also supply the target, its platform,
and an explicit feature opt-in assertion:

```sh
python3 tools/check_model_deployment.py --manifest /absolute/private/path \
  --project assistant --platform windows --feature-enabled --json
```

Supported targets are `assistant`, `memory-contributions`, and
`memory-narrative`; platforms are `windows`, `linux`, and `macos`. The projection
command reports only role IDs, selection hash, declared request timeouts, and
fixed status flags. It never prints model names, endpoints, credential references,
or credential values. `--feature-enabled` permits the projection check; it does
not edit a feature flag, grant operational authority, or start an application or
worker. The command accepts no credential-value argument and never resolves an
environment variable. The CLI does not load an application or worker config, so
its projection report does not check for conflicts with existing legacy settings.

The command uses the source-maintained catalog and the offline graph validator. It
checks strict JSON syntax (including duplicate keys), field sets and types,
catalog role/adapter/contract matches, declared cross-references, hash formats,
URL syntax, version uniqueness, vector-space consistency, resource bounds, and
rollback requirements. It does not import provider code or packages, read
credentials, inspect checkpoint or installation paths, calculate artifact hashes,
probe services, inspect devices, install dependencies, make model calls, qualify
quality, or activate a selection.

The graph report contains a canonical selection hash, role names, counts, and
explicit false values for runtime probing, artifact verification, quality
evaluation, and activation. The projection report uses `projection_valid` and
contains fixed false flags for resource enforcement, runtime probing, artifact
verification, quality evaluation, and activation. Both omit endpoint strings,
implementation URLs, model names, artifact paths, credential references, and
secret values. Keep the manifest itself private even though reports are designed
for safe review. `configuration_valid` and `projection_valid` mean only that
declared metadata or its mapping passed these offline checks; neither means
`ready` or `active`.

## Typed runtime projection and lifecycle gates

The separate [qualification checker](MODEL_QUALIFICATION.md) records the next
review tier: branch-specific identity observations, sampled resources and human
review of pinned synthetic inputs. Optional hashing checks explicitly named
files; it never proves which artifacts a process loaded or activates a provider.

The typed bridge in [`model_binding.py`](../server/backend/app/access/model_binding.py)
projects a validated manifest into private copies of the existing assistant or
memory-worker configuration. Validated snapshots come from the manifest validator;
their public constructor is disabled and their integrity is checked before
projection. This is a source API invariant, not a permission or execution boundary.
`RuntimeConfiguration.with_model_deployment`,
`StagingConfiguration.with_model_deployment`, and
`run_memory_worker.with_model_deployment` return configured copies; they do not
build or serve the app, open worker storage, start a worker, call a provider, or
activate a selection. Startup does not consume these projections automatically,
and there are no new serve/run flags. The API staging package allowlist includes
the bridge and manifest loader, but the source catalog stays in this monorepo;
packaging an independently deployed manifest loader and catalog remains a gate.

Projection is deliberately narrow:

- The assistant target permits either or both selected roles to be enabled;
  `assistant_enabled` must already be true when any role is projected. Its ASR
  model name maps from the declared artifact, while the current TTS interface has
  no model-name field. Assistant request timeouts are capped at 60 seconds and
  use the declared runtime timeout (the existing default is 45 seconds).
- `memory-contributions` requires both `memory_asr` and `annotation_polish`
  bindings enabled; `memory-narrative` requires its `narrative` binding enabled.
  The caller must separately pass `processing_enabled=True` for either memory
  projection. Existing worker phase caps remain: at most 30 seconds per provider
  request, with ASR and polishing sharing one 30-second item budget. A bounded
  run permits at most 32 items and 1,800 seconds. The projection does not extend
  these item or run limits.
- Every source API call requires an explicit platform. A declared runtime for a
  different platform is refused. Feature opt-ins remain independent and are
  never changed by projection.
- Credential environment names are references only. The source API accepts a
  caller-supplied `credential_values` dictionary as an explicit argument; it
  does not inspect ambient environment. The CLI never accepts or resolves these
  values. Keep tokens out of manifests, reports, command lines, and logs.
- Existing provider settings are not silently overwritten. If settings are
  present, they must match the selected provider tuple; when replacing a provider,
  clear the old endpoint/model/token fields explicitly first. A disabled assistant
  binding also refuses conflicting existing provider fields. Rollback is an
  explicit `rollback=True` projection against the separately declared rollback
  bindings; it is not automatic failover.

The projection can map request timeouts, but does not enforce declared RAM, GPU,
or concurrency budgets. The offline projection does not resolve credentials;
binding into a config copy uses only the caller's supplied private dictionary.
Neither step verifies actual runtime or checkpoint identity, performs storage
checks, or establishes quality. A successful
projection is source-level configuration evidence only, not permission to serve
or process data. The next gates remain installed-runtime and artifact verification,
measured resource/adapter checks, bounded synthetic quality, shadow outputs, and
an explicit activation decision.

Before activating a replacement, separately verify installed runtime and artifact
identity, effective device and resource budget, adapter behavior, and bounded
synthetic quality. Run changed embedding or recognition providers in a new
versioned namespace, compare shadow outputs, and review reindexing/re-embedding
effects before switching consumers. Keep the old enabled provider and its
versioned outputs available for the declared rollback until the replacement has
passed its task-specific quality and resource gates. Never combine face or CLIP
vectors across model/preprocessing identities because their dimensions happen to
match.

Model weights stay outside Git. Record model and dependency licenses separately
from application code licensing. Provider teams can replace an implementation by
publishing a new source revision, isolated runtime lock, immutable artifact
identity, and adapter-compatible contract; that change still needs measured
qualification and an explicit activation decision.
