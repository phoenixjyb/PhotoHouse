# Optional local providers

The CPU API, generated demo, phone and TV source checks do not require model
weights. This directory contains a registry template, not a model installer.

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
