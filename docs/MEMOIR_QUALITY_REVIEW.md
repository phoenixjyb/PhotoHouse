# Review story wording against its sources

October 15 source-only operator tool following v64. This is a private, offline
review page for the existing eight synthetic canary cases. It is not a family
app feature, a model-quality verdict or a live generation activation.

## Why this step

A model can return valid JSON and known citation IDs while still inventing a
date, confusing a speaker with an uploader, or joining unrelated activities.
The review page puts the proposed wording, original source records, chapter
input and current review criteria together. It keeps conflicting accounts and
recent conversation visible as different kinds of context. Citations jump to
numbered original sources; keyboard navigation and narrow screens are supported.

Every quality criterion starts and stays **unreviewed**. There is no automatic
semantic score, adoption button, recording, provider request or browser storage.
Read the complete input/output alongside the existing human-review worksheet;
the page does not create or modify qualification evidence.

## Create a page

Use the development environment with the locked API dependencies installed.
First obtain an existing captured synthetic case using the separately authorized
[canary procedure](MODEL_QUALIFICATION.md#capture-one-synthetic-story-output).
Planning, building this page and approval to develop code do not authorize a
model request. Then run:

```sh
python server/scripts/build_memoir_review_page.py \
  --capture-directory /absolute/private/captured-synthetic-case \
  --output /absolute/private/new-story-review.html
```

Both locations must be outside the checkout in owner-private storage. The
capture must contain `record.json`, `input-bundle.json` and `output.json`.
The output's private parent must already exist; existing output files, links,
reparse points and unprivate inputs are refused. No input file is changed.
Open the HTML locally. It includes its styles and makes no network requests;
script execution, remote assets, forms and base URL replacement are blocked.
Keep it private because generated output is retained in the page. Console output
contains only a fixed status, public case/task ID, page digest and false
quality/activation/provider-request flags.

## What is checked

- Stable, bounded, strict JSON reads use the existing private-storage checks.
- The current pinned case, role, task, canonical input hash, captured canonical
  output hash and configuration-identity hash must match. The exact current
  criterion inventory must still be unreviewed.
- Narrative, companion and title outputs are revalidated using the current
  application contracts, including chapter order, per-chapter citation scope,
  cited answers and review-required proposals. Invalid/failed captures do not
  produce a page. Fixing a hash cannot bypass these checks.
- A second read detects content replacement across the three files. The output
  is created exclusively with private permissions and is limited to 1 MiB.
- Model wording is escaped as literal text. Citation links are generated from
  validated IDs; provider text cannot add HTML, scripts or remote links.

The displayed hashes describe **canonical JSON content**, not file formatting.
The review-context hash binds the current source case/expectations and criterion
definitions; older run records do not establish which rubric was used then.
Matching content is not proof of authentic model execution, factual support,
runtime/resource qualification or a reviewer's identity. The page excludes the
capture record's provider configuration, model name, local endpoint and filesystem
paths. Generated wording itself is preserved literally, so keep the page private.

## Canary capture correction

The capture runner now independently revalidates narrative and companion output
after its one provider call, matching the existing title check. An uncited answer,
unknown/foreign citation or reordered chapter produces a sanitized
`invalid_response` failure record. The exact input remains, no `output.json` is
written, every quality item remains unreviewed and no retry is made. Existing
source-free clarification remains valid. Failed captures are retained as evidence.

## Evidence and next gate

The focused case/canary/page/narrator/qualification cohort passes 79 tests and
104 subchecks. The generated browser journey passes five groups, including
Chinese/English text, source jumps by keyboard, 390 px at 150% text, empty-title
abstention, clarification and literal malicious markup with zero external
requests. The first narrow render exposed long-label overflow; wrapping was
corrected before the passing run. Desktop and narrow rendered pages were inspected.
Render data uses a fake provider and does not constitute a model run.

Next obtain a separately authorized bounded synthetic capture from the intended
installed provider, inspect it against its exact sources, record human judgments
with the [qualification worksheet](MODEL_QUALIFICATION.md#enter-human-judgments-with-a-private-worksheet),
and retain the separate runtime/schema/recovery gates before family generation.
The existing Web/API and phone v64 delivery remain unchanged.
