# First native story capture and follow-up fixes

Two separately authorized, single-request runs are recorded below. The initial
run's natural-drain failure remains intact; the revised run explicitly uses
owned-job teardown. Neither establishes human storytelling quality.

## Initial capture: result and scope

On October 16, one installed `qwen3.5:9b-q4_K_M` candidate processed the pinned
`synthetic-coherence` narrative case from source
`b194741c95b92f76bef895429cc1341e1507200a`. It returned a structurally valid,
source-cited, review-required proposal. **The complete runtime trial did not
qualify:** an owned provider helper outlived its parent and exceeded the natural
descendant-drain allowance. The guard refused completion, terminated the owned
job and drained it. A subsequent observation found the temporary listener closed
and selected GPU memory back at its admission baseline.

This was one text-only synthetic request, with no family database or media.
It does not evaluate image understanding, conversational response speed, other
models, the remaining seven cases or family storytelling quality. All human
quality criteria remain unreviewed. No provider selection, live service, task,
schema, family generation flag or APK changed.

## Observed evidence

| Observation | Result | Limit of the observation |
| --- | --- | --- |
| Selected model manifest | `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90` | Installed manifest identity, not a new weight download or quality verdict |
| Canonical case input | `4146b546ba71f011b9062017c5eb57e1addaefa6ed2a08e613df1b926532a5f3` | Exact existing three-chapter case; not real family material |
| Canonical captured output | `da7d95781326ee1e6c9f884ee59f1661481307439f1328b04df83d6a4f6bb475` | Output remains in private operator storage |
| Provider/driver | Ollama 0.34.2; NVIDIA driver major 580 | One native installation |
| Request count | One canary invocation and one successful request | Earlier refused preflights and diagnostics made no model request; no retry followed |
| Duration | 85.875 seconds inside the canary; 86.359 seconds around its child invocation | Cold-start profile; loading, prompt processing and generation are not separately timed |
| Loaded placement | Post-request provider inventory reported 5,589,560,196 bytes, all on GPU, with context 4096 | Post-request text-model placement; not a guarantee for other contexts or image workloads |
| Selected GPU samples | Admission 264 MiB used; maximum observed 6,787 MiB; 79 samples over 86.359 seconds | Approximately one-second sampling, not a continuous exact peak or process-specific allocation |
| Execution bounds | 180-second owned job, 24 GiB job-memory cap, 12 processes, 24 GiB free-RAM admission floor; 90-second request | Configured/enforced bounds, not measured peak host RAM |
| Preserved services | Eight task definitions, states and identified root processes matched before/after | Point-in-time preservation; not family/device acceptance |
| Review page | Actual capture rendered at desktop and 390 px / 150% text; no external requests or horizontal overflow | Offline operator preview, not delivered family UI |

The capture record still says `resource_limits_verified: false`: it is a capture
record, not a qualification document. The separate supervisor evidence must stay
attached to it, including the failed natural-drain result. Do not relabel the
capture or the overall trial as qualified because the output validates.

## Findings and source changes

### Native environment

The first provider preflight failed before inference. The exact GPU query also
failed outside the job with the same reduced environment. Restoring the ordinary
Windows variables `PROGRAMDATA`, `PROGRAMFILES`, `PROGRAMFILES(X86)`,
`PROGRAMW6432` and `ALLUSERSPROFILE` made it pass inside the unchanged job limits.
The private harness now preserves those variables for its child/provider while
excluding unrelated settings and secrets. Its 25 regression tests pass. This
isolates the environment difference as a group; it does not establish which
single variable the installed driver requires. Existing failed stages remain.

### Wording

A preliminary assistant comparison found the three chapter accounts supported
by their cited sources, in the supplied order, without the prohibited invented
harvest or exact date. However, repeated author labels in parentheses make the
prose mechanical. Three questions request optional detail rather than resolve
an ambiguity needed for the story; the date question needlessly asks for more
precision despite the input direction.

The following source prompt now asks for concise attribution, preserves the
distinction between record attribution and depicted person/speaker/uploader,
and asks a question only when ambiguity prevents a supported response. It
explicitly permits an empty question list when sources support the draft.
Chapter citation, uncertainty, conflicting accounts, transcript/quotation and
human-review rules remain. Mock transport checks verify those instructions reach
both narrative and companion requests for legacy and editorial bundles.
**No real model has evaluated this revised prompt yet.** These checks establish
the request contract, not improved prose quality.

### Temporary-provider cleanup

`run_bounded` now has an explicit strict-boolean
`terminate_descendants_after_exit` option, defaulting to `false`. Existing
callers still require natural drain. An opting-in temporary-provider controller
may terminate only its assigned job after the parent exits, verify the remaining
process count reaches zero, then return the original parent exit code. Failed
termination, inventory, drain or handle cleanup remains a failure. Callers must
report the policy; forced cleanup never establishes natural shutdown.

The focused public narrator/controller/capture/review cohort passes 75 tests,
including 26 portable controller checks. A native **synthetic process-only**
canary exercised the new policy: the parent exited with code 7, the job reported
three remaining processes, one owned-job termination succeeded, the count reached
zero and the original code 7 was preserved. It made no inference or provider
request and changed no service. The actual model capture used the older default
policy and remains a failed overall trial. No inference controller is switched
to the new policy by this source change.
The native canary used `bounded_windows_job.py` SHA-256
`9ffd012c12afc44a7caa54b8aa40e360640ad8bf390a1b3f547fb162b44d3f79`.

## Initial follow-up gates (before the revised capture)

1. Prepare a fresh pinned harness declaring the cleanup policy and its receipts;
   retain failed evidence. A new real model run requires its own authority.
2. Re-evaluate the revised prompt on the exact case. Record human judgments
   separately using the [worksheet](MODEL_QUALIFICATION.md#enter-human-judgments-with-a-private-worksheet).
3. Qualify conflict, similar-photo separation, speaker/uploader/subject roles,
   provenance and independent title cases before broader use. One coherence
   sample cannot replace them.
4. Measure warm and cold latency separately before an interactive feature uses
   this model. The observed cold request is too slow to establish fluid chat.
5. Keep schema, recovery, resource, paired-backup, delivery and family-acceptance
   gates separate before any live generation activation.

See the [offline review page](MEMOIR_QUALITY_REVIEW.md),
[model qualification procedure](MODEL_QUALIFICATION.md) and
[project status](PROJECT_STATUS.md).

## Revised capture after PR #28

The next authorized run used source
`01c9f159c1cd07e7775cf68f8dc4fb532d2563d4` (merged through PR #28 at `ea43c48`)
and the same pinned case/input. Its private 18-member packet SHA-256 was
`dfc41072c7217b11edabd68bcbd5bb1d1695008dfa78526ca636391c98935d29`;
27 harness checks and extracted eight-case planning passed before execution.
It made exactly one model request, with no retry or other model run.

- The proposal validated and was captured with canonical output SHA-256
  `eb0d59068ce4879d4ae128788aae90251717a397e1b82b3dfbe0ddc08eca4fee`.
- Canary duration was **80.422 seconds**, with **80.875 seconds** around its
  child invocation. The unchanged 90/180-second, 24 GiB, 12-process and 4K
  context bounds applied. These two cold observations do not separate model
  loading from generation or demonstrate acceptable interactive latency.
- Post-request loaded-model size/GPU placement matched the first run. The
  selected GPU's sampled maximum was again **6,787 MiB**, across 73 samples.
- The supervisor explicitly reported `terminate_descendants_after_exit`,
  observed **3 → 0** remaining processes, recorded one successful owned-job
  termination and returned child exit code 0. The declared teardown gate passed;
  this is not evidence of natural provider shutdown.
- Eight task definitions/states/identified roots matched before and after. The
  temporary listener was closed; a later read-only GPU observation found the
  selected GPU back at **264 MiB** used. No service or model selection changed.
- The actual capture was rendered at desktop and 390 px / 150% text without
  external requests or horizontal overflow, then visually inspected.

The new output asks zero follow-up questions, compared with three in the earlier
capture, and no longer duplicates an author label in parentheses. A preliminary
assistant comparison still finds formulaic attribution; its wording can also
blur a recording's byline with the person speaking. Those are review issues,
not automatically passed criteria. The chapter order and cited IDs validate;
**all human quality items remain unreviewed**. One sample per prompt cannot
establish a general improvement or qualify the remaining cases.

Next record independent human judgments and qualify conflicting accounts,
speaker/uploader/subject separation, provenance and the separate title cases.
Additional model requests need their own authority. Generation stays off while
latency, complete-case quality, schema/recovery and family acceptance remain open.
