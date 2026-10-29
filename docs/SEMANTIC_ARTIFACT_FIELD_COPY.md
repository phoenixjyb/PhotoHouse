# Exact artifact field copying

Code `c01758491b87c6e2a7fb3f8bfff66d949df8e2c2` reduces Python iteration
while copying current artifact metadata. Semantic search remains **OFF**; this
source has not completed Windows qualification or been deployed.

The [October 24 readiness checkpoint](SEMANTIC_SEARCH_READINESS_2026-10-24.md)
records the later allocation-only attempt, its limited transport release and
the remaining full-run and activation gates. It adds no native timing result.

## Change and preserved checks

The bulk cohort key and request-local artifact snapshot still copy all 16 fields
in the same order. A fixed `operator.attrgetter` replaces the field extraction
generators. The bulk type check uses C-backed `map` iteration with
`operator.is_`: the two integer fields must have exact `int` type and the other
fields exact `str` type. Boolean, floating-point and subclass values remain
invalid, including subclasses whose metaclass spoofs equality.

Every row still invokes its check callback before copying. Current SQLite reads,
authorization, policy checks, file hashing, source and generation checks,
detached primitive snapshots, ranking and resource limits are unchanged. This
adds no cache or alternate validation policy.

## Local validation

The 70 focused tests passed with Python 3.12 / NumPy 2.2.6 and Python 3.14 /
NumPy 2.4.2. They cover bulk integrity and eligibility plus field order, exact
types, missing attributes and mutation during callbacks. A further 74 semantic
search and streaming tests passed on Python 3.12, including owner revocation,
source changes during encoding, hard filters, cancellation, deadlines and
generation invalidation. There are 122 unique cases across these overlapping
sets. The source ledger verification passed.

A generated library contained 23,696 eligible 768-dimensional vectors and 65
omitted images. Eighteen complete API requests alternated the old and new helper
implementations on the same verified store: three pairs each for English,
Chinese and mixed input. All pairs matched the full API JSON and all 23,696
ranked IDs and score bits.

| Local measurement | Previous helpers | New helpers |
| --- | ---: | ---: |
| Mean complete request | 2,986.678 ms | 2,774.770 ms |
| Median complete request | 2,785.835 ms | 2,561.767 ms |
| Maximum complete request | 3,973.912 ms | 3,976.701 ms |
| Mean exclusive bulk snapshot phase | 499.724 ms | 340.395 ms |

These are preliminary, noisy measurements from one generated fixture, with a
large Chinese candidate outlier and variation by language. The mean request
reduction is about 7%; the maximum did not improve. Exclusive phase means are
computed from complete requests; nested inclusive times must not be added.
Peak process RSS was 753,745,920 bytes, below the 768 MiB local test ceiling.
The generated temporary files were removed.

The API used in-process TestClient and a fixed generated text vector through the
actual encoder wire contract. Uniform synthetic vectors and captions do not
measure multilingual relevance. Learned-model inference, TCP/TLS, Windows,
phone/WAN and family acceptance are outside this comparison. The 2-second target
remains unmet. Keep the complete protected Windows run, current shared-host
preservation baseline and separate activation review before enabling search.
