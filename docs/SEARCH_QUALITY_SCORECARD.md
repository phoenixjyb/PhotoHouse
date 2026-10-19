# Private search quality scorecard

`check_private_search.py --cases` accepts the existing version 1 envelope and
the version 2 envelope. Both run the same bounded, read-only search turns and
retain source and membership checks. If authorization, readiness, source
identity, or a bound snapshot fails, evaluation returns no scorecard.

Version 2 adds two optional fields to each case:

```json
{
  "version": 2,
  "cases": [
    {
      "id": "sample_1",
      "text": "private query text",
      "language": "en",
      "category": "person",
      "expect": {"kind": "results", "relevant_ids": ["101"]}
    }
  ]
}
```

`language` is one of `en`, `zh`, `mixed`, or the explicit `unassigned` label;
`category` is one of `person`, `date`, `text`, `scene`, `followup`, or
`no_match`. Both fields are optional. Cases without a language are reported in
the `unassigned` cohort. The report always includes every named language and
category cohort, including empty cohorts, so missing or failing coverage stays
visible. The legacy aggregate is descriptive; it does not establish a pooled
qualification grade. Category values use a fixed vocabulary; only those fixed
bucket names are exposed, never free-form category labels. A `no_match` case must
expect `total: 0`; its ordinary expected checks must also pass for the case to
pass.

The v2 report keeps the existing case counts and relevance summary, then adds
`scorecard.cohorts` and `scorecard.categories`. Each language cohort includes
its case denominator and pass/fail counts, annotated no-match and failed
dependency counts, hard-filter and absence check counts and failures, relevance
denominator, hit@5 count and rate, labeled recall@5, MRR@20, executed count,
latency sample count, and median/p95 local elapsed milliseconds. Category
cohorts expose fixed-category denominators and pass/fail counts. These
hard-filter and absence counts cover only cases that supplied those checks; they
do not measure all possible mistakes. A relevance case is a case with supplied
`relevant_ids`.
Clarifications, empty pages, and failed dependencies with relevance labels are
misses. Failed dependencies remain in the case denominator. The no-match count
is based on the explicit `no_match` category annotation. Dependency cases that
did not execute a search turn are excluded from executed counts and latency
samples.

Recall@5 is the fraction of supplied relevant IDs retrieved in the top five.
Incomplete labels do not measure population recall. Hit@5 and MRR@20 use
supplied labels as well.
The report contains no query text, names, IDs, context, result labels, or
free-form case labels. Timings are local evaluator elapsed times, not service
latency benchmarks. These descriptive metrics establish no threshold,
qualification, activation, or access authority.

Version 1 continues to emit its prior report version and keys, including its
existing hit@20 and MRR@20 relevance summary. For both versions, `absent_ids`
checks pass only against a complete page; a page with more results does not
prove absence.

The current private CLI constructs the deterministic v2 search runtime. Its
language cohorts measure those supplied queries only; they do not exercise
the v3 intent model, workspace-owned pending conversations, or v4 semantic
ranking. Those paths require separate authenticated journey and model-pair
qualification evidence. No score from this runner qualifies a multilingual
encoder or proves dialect recognition.
