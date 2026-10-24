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
