# Image-only semantic facts preparation

Semantic search remains **OFF**. This source change applies only when the
detached, normalized filters are exactly `{"media":["image"]}`. Additional
people, date, tag, location, caption, text or descriptive filters retain the
general facts path. An inconsistent internal mode or filter shape refuses.

Image-only requests do not consume per-row caption/tag/location/person filter
maps, facet counts or coverage facts, so this path omits their construction.
Asset conversion, invalid metadata handling, reviewed-face assignment equality,
`allow_zero` enforcement and per-index cancellation/deadline checks remain.
Every fresh SQL read, authorization/source binding, eligibility policy,
bulk-file/generation check and final post-provider authorization still runs.
The change adds no cross-request cache and changes no model, ranking, format,
schema, limits, permission or activation setting.

## Generated full-request comparison

The paired comparison used 23,696 generated 768-dimensional vectors, 65 generated
omissions and the actual FastAPI/encoder-contract/ranking response path with a
fixed generated encoder response. It ran nine alternating warm pairs across
English, Chinese and mixed input, plus three page-two pairs. All complete API
JSON, ranked IDs and score bits matched between the general and image-only
paths. No learned model, Windows/GPU or external network call was involved.

| Path | Mean wall | Median | Maximum | Exclusive facts mean |
| --- | ---: | ---: | ---: | ---: |
| General facts | 2,329 ms | 2,306 ms | 2,587 ms | 247 ms |
| Image-only facts | 2,180 ms | 2,118 ms | 2,615 ms | 78 ms |

Facts preparation fell by 169 ms/request and full-request mean by 149 ms (6.4%)
in this run. Only two of nine candidate samples met 2,000 ms. The cold candidate
request was 5,270 ms, reported separately. The generated profile stayed within
its 768 MiB RSS ceiling and removed its temporary data. Nested phase timings
are not added together.

Five focused tests cover path selection and fallback, response/pagination
parity, invalid metadata, reviewed-face/`allow_zero` checks, cancellation, two
fresh source/policy passes and post-provider source/policy/membership changes.
This source result does not meet the 2 s gate or establish native/model latency.
The [readiness checkpoint](SEMANTIC_SEARCH_READINESS_2026-10-24.md) records the
separate failed Windows run and remaining qualification/activation gates.

## Existing bulk-cohort grammar proof

A subsequent change avoids reparsing artifact grammar when the complete current
SQL projection exactly matches a bulk store's existing validated immutable
metadata. It requires the same file pin, library, model identity, canonical
16-column order, row count, row order, exact primitive types and every field
value. SQL asset IDs are exact positive signed-64-bit integers before conversion
to artifact strings. A hit returns detached artifact copies; a miss retains the
full parser. It adds no cache and retains per-row cancellation/deadline checks.

This proof covers metadata grammar only. Both fresh source reads, current source
hashes, eligibility-policy reads/validation, authorization and the bulk file's
secure reopen/hash checks around encoding still execute. It does not reuse an
authorization, policy, file-validity or source-freshness decision.

Seventy focused store/eligibility/bridge tests passed. In one separate generated
23,696-vector paired comparison, both modes enabled image-only facts; only this
grammar bridge differed. All nine English/Chinese/mixed response and complete
rank-bit pairs, plus three page-two pairs, matched. Each mode retained 18 fresh
source-SQL calls per measured request.

| Path | Mean wall | Median | Maximum | Exclusive source-extension mean |
| --- | ---: | ---: | ---: | ---: |
| Full parser | 2,102 ms | 1,977 ms | 2,805 ms | 332 ms |
| Exact cohort match | 1,872 ms | 1,871 ms | 1,991 ms | 187 ms |

All nine candidate warm samples were below 2 seconds in this fixture. Paired
savings ranged from 78 to 984 ms, with a 106 ms median; one baseline outlier
inflates the 230 ms mean difference. This single generated, fixed-encoder run
does not qualify native/model/network or production latency. The profile stayed
within its 768 MiB RSS and 180-second measurement limits and removed temporary
data. Semantic search remains OFF pending the separate native and activation
gates.
