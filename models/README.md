# Optional local providers

The CPU API, generated demo, phone and TV source checks do not require model
weights. This directory contains a registry template, not a model installer.

[`catalog.json`](catalog.json) maps thirteen model-backed capabilities to actual
source adapters, configuration owners, execution modes and replacement boundaries.
[`providers.example.json`](providers.example.json) contains corresponding disabled
selection placeholders. Neither file is loaded by the application as runtime
configuration. The private selection format and its validation boundaries are
described in [the deployment manifest guide](../docs/MODEL_DEPLOYMENT_MANIFEST.md).
Private deployment records and weights belong outside the source checkout.

From the repository root, run the offline check:

```sh
python3 tools/model_catalog.py --json
```

It parses adapter source without importing model libraries, detects stale class
names and contract mismatches, and refuses populated/active public example
selections or known weight files in this directory. It makes no network calls,
installs nothing and checks no live provider. The ASR paths have distinct raw-WAV
and multipart contracts; face and image vectors have different model identities.
See [the provider architecture](../docs/MODEL_PROVIDER_ARCHITECTURE.md) for the
infra layout, migration rules and runtime-selection integration gate.

The deployment checker is separate from the catalog checker. Run it with an
explicitly selected absolute manifest path outside the checkout:

```sh
python3 tools/check_model_deployment.py --manifest /absolute/private/path --json
```

Its `configuration_valid` result means the selected metadata graph passes offline
schema and source-catalog checks. It does not probe endpoints, inspect installed
files, load provider packages, verify weights, check a GPU, evaluate quality, or
activate any binding. [`deployment.synthetic.json`](deployment.synthetic.json)
is fake schema-validation data with all bindings disabled; use it only as a
starting template for a separate private file, never as a runtime profile.

Add `--project assistant --platform windows --feature-enabled --json` to inspect
an opted-in assistant mapping. Memory targets are `memory-contributions` and
`memory-narrative`. The source bridge returns private in-memory configuration
copies, refuses conflicting legacy settings, and preserves feature flags and
worker deadlines. It does not start a service or resolve tokens in the offline
command. See the [typed projection guide](../docs/MODEL_DEPLOYMENT_MANIFEST.md#typed-runtime-projection-and-lifecycle-gates)
for the explicit source APIs and remaining runtime qualification gates.

For each selected provider record its exact adapter, endpoint, runtime version,
dependency lock identity, checkpoint or service identity, license source,
permitted use, preprocessing/vector identity and resource budget outside source
control. The private manifest stores credential environment-variable names only;
the referenced values stay in the operator environment and are never included in
the validation report. An application code license does not establish a model
license. The public example registry deliberately leaves endpoints and model
identities unset.

## Qualification

The [qualification evidence checker](../docs/MODEL_QUALIFICATION.md) now reviews
scoped current/rollback identity observations, resource samples and human reviews
of Chinese ASR/TTS and the existing memoir cases. Optional explicit hashing
checks named files without loading them as models. Reports keep recorded claims,
file checks and provider/device/quality acceptance separate; no setting is applied.

1. Validate the configured provider without family data.
2. Run bounded synthetic ASR, narration or story/conversation examples.
3. Record response schema, attribution, uncertainty, latency and resource use.
4. Review Chinese recognition, audible speech and narrative quality.
5. Explicitly enable only the qualified worker and feature.

A model availability check is separate from quality acceptance. Processing
failures retain an honest state; source memories and failed proposals are not
replaced. Explicit assistant and memory projections are implemented; independent
runtime catalog packaging, face/embedding projection, measured provider
qualification and activation remain separate gates. No model weights, household endpoints,
private deployment manifests or provider tokens belong in this checkout.
