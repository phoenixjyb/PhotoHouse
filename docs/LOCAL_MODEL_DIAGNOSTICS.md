# Qualify a local narrative provider

A listening port, loaded model or successful ASR request does not establish that
story generation works. Keep generated text as a reviewable proposal and keep
family generation disabled until synthetic narrative cases pass.

## Record the actual installation

Record the selected provider binary hash and version, driver version, selected
GPU, model manifest/blob hashes, resource budget and request limits in private
operator evidence. File-version metadata can be empty; an absent version must
remain unknown. Keep machine paths, device identities and credentials out of
source and public reports.

Check the provider's current hardware requirements. Ollama currently lists
NVIDIA compute capability 5.0 or newer with driver 550 or newer; capabilities
5.0–6.2 require driver 570 or newer. Its table lists Quadro P2000 under 6.1.
Meeting that published floor is useful admission evidence, not a successful
inference result. See [Ollama hardware support](https://docs.ollama.com/gpu).

## Use an isolated synthetic canary

Use a separately selected loopback endpoint and process-local environment.
Bound process memory, lifetime, concurrent requests and output capture. Verify
free memory and GPU headroom before starting. Do not download weights, change
global environment, restart an existing provider or read family material as a
side effect. An operator must explicitly select the target and operation.

Verify these independently:

1. Process and endpoint identity.
2. Model discovery and loading.
3. Valid bounded response to a synthetic request.
4. Multi-chapter coherence, attribution, uncertainty and absence of invented facts.
5. Owned process/task cleanup, including failed requests.

A failed inference is not a story-quality evaluation. A generic CUDA error does
not identify memory exhaustion, driver incompatibility or a bad model.

## Keep diagnostics useful and private

`server/backend/app/access/model_diagnostics.py` summarizes bounded bytes into
fixed signals and at most eight sorted numeric CUDA codes. It never returns raw
text, paths or tokens. Preserve input byte count and overflow status so missing
signals are not mistaken for a complete capture. This classifier describes
recognized messages; it does not diagnose their cause.

Ollama's [troubleshooting documentation](https://docs.ollama.com/troubleshooting)
describes Windows logs, optional debug output and provider-library selection.
Raw logs may include prompts or local configuration. Review them privately;
public reports should use bounded classifications and synthetic case IDs.
Debug settings or a CPU/GPU fallback belong to a new, explicit canary scope.
Changing drivers, models or a live service requires its own reviewed operation.
