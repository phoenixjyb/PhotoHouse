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

The fixed suite's model-plus-compiler time was 846 ms median and 1291 ms maximum
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
phrase or expectation added to the prompt. This report does not claim that the
new payload improves model recall; it needs a new source-pinned native trial.
