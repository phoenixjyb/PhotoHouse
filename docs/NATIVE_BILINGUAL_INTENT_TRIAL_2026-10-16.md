# Bilingual intent trial — October 16, 2026

Two separate bounded Windows GPU trials measured source
`23466bece2e7f46009eb92d0396d238bfa06e989` against fictional inputs and captions.
They used installed `qwen3.5:9b-q4_K_M` through Ollama 0.40.0, a 4096-token context,
temperature zero, a 1024-token output limit and one attempt per eligible case.
Each trial had one separately counted warm-up. No production database, media,
family roster or user request was used.

**The results do not support enabling the optional intent provider.**

| Language | Fixed-suite expectations met | Held-out positive matches | Held-out negative false positives |
| --- | ---: | ---: | ---: |
| English | 3 / 4 | 0 / 20 | 0 / 20 |
| Chinese | 2 / 4 | 2 / 20 | 0 / 20 |
| Mixed | 2 / 4 | 0 / 20 | 0 / 20 |
| Total | 7 / 12 | 2 / 60 | 0 / 60 |

The fixed suite completed all twelve cases: nine model attempts and three
no-model date clarifications. All nine measured HTTP requests returned 200;
six proposals were accepted as responses and three were rejected. Including
warm-up, it made ten HTTP requests, with no retry. The fixed expectation measure
covers status, hard filters and the case's generated evidence; it is distinct
from held-out positive retrieval recall.

Public-suite diagnostics showed two proposals copying redaction markers into
scene surfaces, one treating a grammar-only Chinese particle as a scene clue,
and two valid clarification replies that failed to extract visible descriptions.
These were interpretation/validation failures, not HTTP timeouts. The strict
validator correctly withheld the unusable proposals. The separate warm-up
returned overlapping concepts; its ready envelope did not establish a usable plan.

The held-out suite completed all 24 cases with 21 model attempts and three
no-model cases, making 22 HTTP requests including warm-up. Sixteen proposals were
accepted as responses and five were refused. All 60 positive and 60 negative
fixture outcomes were counted; only two complete case expectations were met.
Zero false positives alongside two positive hits does not establish useful recall.
The held-out fixture remained frozen and separate from the public suite.

The fixed suite's adapter request/validation time was 846 ms median and 1291 ms maximum
among model-attempt cases. Each warm-up took about 79 seconds. These are synthetic
planning measurements, not signed-in API, browser, phone or family latency.
Full GPU residency was observed in both trials, with peak sampled target-GPU use
of 7002 MiB. Their model process trees were stopped through the owned Windows Jobs;
the trial port closed and no Ollama process remained after either operation.

An independent postflight confirmed live API/Web source `54394ed`, the same
schema and configuration bytes, all eight operational root tasks/processes and
API/OCR ownership preserved. Production intent remained unconfigured. No model
was downloaded, no service restarted, no migration run and no client published.
Private identity pins, controllers, captures and readback receipts remain outside
Git. Native execution is separate from semantic quality and family acceptance.

Ollama changed from 0.34.2 in the older trial to 0.40.0 here. Comparisons with that
older candidate cannot isolate a prompt-only effect. The source improvement that
follows this baseline sends only [safe visible fragments](BILINGUAL_SEARCH_REQUIREMENTS.md#explicit-redaction-boundaries-for-intent-proposals),
removing marker copying as an input representation problem while retaining strict
validation. Its design uses the public-suite failure mechanism, with no held-out
phrase or expectation added to the prompt. The following fixed-suite measurement tests that input change separately; it
does not establish broader recall.

## Follow-up: safe visible fragments

A separate source-pinned trial measured the fragment adapter at
`cd20f47927641ab089fc16101b161c65a2a5ef06` with the same installed binary/model,
fixed public fixture and inference settings. The raw surface/alternatives schema,
original-offset checks, required concepts and hard filters were retained.

| Language | Fixed-suite expectations met |
| --- | ---: |
| English | 4 / 4 |
| Chinese | 2 / 4 |
| Mixed | 3 / 4 |
| Total | 9 / 12 |

All twelve cases completed: nine measured HTTP requests returned 200, six
proposals were accepted and three were refused; three date questions needed no
model. Including warm-up, there were ten HTTP requests and no retry. None of the
ten captured assistant responses contained a redaction marker. The remaining
three failures each added the standalone grammar particle `的` as a scene clue;
strict validation rejected it. No validator or match requirement was relaxed to
make these cases pass.

Adapter request/validation time was 946 ms median and 8453 ms maximum among measured
model attempts. Warm-up took 79005 ms. GPU residency and owned-process cleanup
were verified. These observations describe this development fixture and source,
not full API/voice latency or general language quality.

The 24-case held-out suite was not rerun on this following source. Its earlier
2/60 positive result remains evidence of the broader gap; the 9/12 public-suite
result does not establish held-out recall. Provider activation remains unsupported.
Remaining work includes Chinese grammar-only proposal handling and multilingual
retrieval/ranking quality, with source-pinned evaluation and unchanged hard filters.

## Following source: stage diagnostics and Chinese grammar instructions

Source `6f18d72ba9ff295b0cc61a87f28cf8b130b7fd71` adds diagnostic schema v1 to the
fixed-suite qualifier, without changing its fixture digest or expectation policy.
The local-model prompt explicitly excludes standalone Chinese grammar particles;
the response schema and strict validator are unchanged. Offline checks cover
whole-proposal refusal when a grammar-only clue accompanies valid content, and
preservation of complete content words containing the same character.

Re-reading the prior fragment trial's retained full report distinguishes its
9/12 case expectations from descriptive recall: six ready descriptive searches
and three correct no-model date clarifications passed. The descriptive cases
produced 6/9 positive hits and 0/27 negative false positives. Three expected
descriptive cases never reached evidence matching. This is a retrospective
breakdown of the same earlier trial, not new inference or broader recall.

A subsequent native launch for the following source was refused by the
pre-existing-provider admission gate before source extraction, controller or
model startup. It produced no warm-up, case measurement or quality result.
The one-use transfer claim and failure evidence are retained privately, with no
automatic retry or interference with the existing process. The new prompt's
native quality remains unmeasured; provider activation remains unsupported.

The timing labels above now specify their actual scope: `elapsed_ms` measures
the adapter request and validation. It does not include the compiler work around
that call, the API, voice transport or device experience. The full native
measurement already retained detailed qualifier rows under `qualification`;
the new diagnostics summarize those stages without adding raw invalid responses
or pretending to observe separate uninstrumented validation steps.
