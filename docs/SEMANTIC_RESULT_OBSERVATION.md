# Private semantic result observations

`qualify_library_semantic.measure()` accepts an optional `result_observer`
callback for a local qualification harness to review measured top results:

```python
result = measure(..., result_observer=observations.append)
```

The default is `None`. With no callback, the measurement report and sample
schema stay unchanged and no query-plan digest is computed for observation.
With a callback, the harness invokes it once for each successful measured warm
response, after the HTTP elapsed time has been captured. Warm-up, authorization
refusals, and protected probes are not sent to the callback. If request profiling
is enabled, the observation carries the corresponding bounded runtime request
ordinal; otherwise that field is `null`.

The callback receives a detached, bounded, redacted projection, not the API
response. Each observation contains query ID/language and a query hash, response
digest, library/model/index/query-plan pins, repetition and elapsed time, up to
20 ranked asset IDs and scores, plus eligible/omitted coverage counts. Response
projection is limited to a 4 MiB canonical input and a 32 KiB output; source
queries are capped at 12 and repetitions at 10 by the existing qualification
contract.

These outputs are **private and linkable**, not anonymous: `library_id`, ranked
asset IDs, and hashes can identify the private library or be joined back to its
index. Store callback output only in a private local destination; do not publish
or share it. The callback is caller code and runs synchronously, so keep it
small, local, and nonblocking. Its work is outside the measured HTTP elapsed
time, though it can extend overall harness wall time.

Observations report what the generated qualification run returned. They set no
quality threshold, do not label assets as relevant, do not measure family
relevance, and do not approve activation. No actual family media or relevance
review is represented by the synthetic observer tests. A reviewer must inspect
representative results and coverage separately before making a quality claim.
