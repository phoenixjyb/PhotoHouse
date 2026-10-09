# Optional local providers

The CPU API, generated demo, phone and TV source checks do not require model
weights. This directory contains a registry template, not a model installer.

[`catalog.json`](catalog.json) maps thirteen model-backed capabilities to actual
source adapters, configuration owners, execution modes and replacement boundaries.
[`providers.example.json`](providers.example.json) contains corresponding disabled
selection placeholders. Neither file is loaded by the application as runtime
configuration. Private deployment records and weights belong on the runtime host.

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
infra layout, migration rules and remaining runtime-selection integration gate.

For each selected provider record its exact adapter, endpoint, runtime version,
checkpoint digest, license source, permitted use and resource budget outside
source control. An application code license does not establish a model license.
The example registry deliberately leaves endpoints and model identities unset.

## Qualification

1. Validate the configured provider without family data.
2. Run bounded synthetic ASR, narration or story/conversation examples.
3. Record response schema, attribution, uncertainty, latency and resource use.
4. Review Chinese recognition, audible speech and narrative quality.
5. Explicitly enable only the qualified worker and feature.

A model availability check is separate from quality acceptance. Processing
failures retain an honest state; source memories and failed proposals are not
replaced. No model weights, household endpoints or provider tokens belong here.
