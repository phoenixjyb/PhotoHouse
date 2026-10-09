# Local story and conversation model shortlist

Researched on October 9, 2026. This is a candidate comparison and evaluation
plan, not an installed-provider or quality qualification. Model weights stay
outside Git and outside the Mac source workspace.

## Candidates worth testing

| Candidate and explicit Ollama tag | Release | Registry payload, approximately | Proposed use |
| --- | --- | --- | --- |
| Qwen 3.5 9B, `qwen3.5:9b-q4_K_M` | March 2, 2026 | 6.55 GB | First everyday candidate: conversation, wording, titles and short chapters |
| Gemma 4 12B, `gemma4:12b-it-qat` | June 3, 2026 | 7.15 GB | Compare the newer Gemma generation on the same story cases |
| Qwen 3.8 27B, `qwen3.8:27b-q4_K_M` | August 14, 2026 | 17.74 GB | Larger candidate for chapter synthesis and book outlines during low GPU contention |

The Qwen release dates come from the [official project news](https://github.com/QwenLM/Qwen3.8#news).
Google records Gemma 4's March 31 introduction and the June 3 addition of 12B
in its [release history](https://ai.google.dev/gemma/docs/releases).
All three selected artifacts carry Apache-2.0 licensing in their official
Ollama entries: [Qwen 3.5](https://ollama.com/library/qwen3.5:9b-q4_K_M),
[Gemma 4](https://ollama.com/library/gemma4:12b-it-qat), and
[Qwen 3.8](https://ollama.com/library/qwen3.8:27b-q4_K_M).

Payload totals were calculated from the registry manifests' declared config and
layer sizes. They are decimal GB, not measured GPU residency, peak host memory
or download bytes after cache reuse. The reviewed manifest digests are:

| Tag | Manifest SHA-256 |
| --- | --- |
| `qwen3.5:9b-q4_K_M` | `56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90` |
| `gemma4:12b-it-qat` | `38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3` |
| `qwen3.8:27b-q4_K_M` | `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e` |

Registry tags can move. Before installation, re-read the selected manifest and
refuse a changed digest; verify each installed blob against its digest and size.
The retained private metadata is not evidence that these weights are installed.

## Why these sizes

On a shared 24 GiB GPU, the 9B and 12B candidates offer more nominal headroom
than a 27B model. This is an engineering hypothesis to measure, not a throughput
claim. Context caches, temporary buffers, host allocations, speech and image
workers all consume additional resources. Start with one loaded model, one
request, and a 4,096-token context; the advertised 256K context is not a safe
default on this hardware. Refuse insufficient headroom instead of interrupting
another worker or silently switching to another model.

Qwen 3.6 remains a possible comparison, but 3.8 is newer at the same dense 27B
size. The [3.6 library](https://ollama.com/library/qwen3.6/tags) lists its 35B
MoE variants around 23–24 GB. A low active parameter count reduces per-token
computation; it does not eliminate the full expert weights' storage requirements.
The much larger Qwen 3.8 Max-class release and
[Mistral Small 4's 119B MoE](https://mistral.ai/news/mistral-small-4/)
are outside this initial shared-GPU plan.

Chinese language coverage and general benchmark improvements in the
[Qwen 9B card](https://huggingface.co/Qwen/Qwen3.5-9B),
[Qwen 27B card](https://huggingface.co/Qwen/Qwen3.8-27B), and
[Gemma overview](https://ai.google.dev/gemma/docs/core.md)
do not establish better family storytelling. The final choice needs our own
grounded Chinese chapter and follow-up cases, reviewed against the same inputs.

## Adapter readiness

PhotoHouse's narrative/companion, annotation-polish and title adapters use
Ollama's loopback `/api/generate` contract. Requests now explicitly send
`think: false` alongside their existing JSON format, bounded output and deadlines.
Ollama documents that control for both generation and chat in its
[thinking guide](https://docs.ollama.com/capabilities/thinking).
Qwen 3.8 otherwise enables thinking by default; uncontrolled reasoning can spend
the bounded output/time budget before producing the required JSON.

Keep the strict existing schema and source-citation validation. Do not strip
arbitrary thought markers to repair invalid JSON, interpret reasoning as a
family statement, or retry without the requested thinking control. Confirm
actual template, structured-output and non-thinking behavior on the exact
installed Ollama binary; a current registry listing alone proves none of them.
The source change does not update a deployed API or worker.

Offline Windows Job callers may explicitly select up to 60 seconds of normal
descendant shutdown grace; the default remains five seconds. Grace is capped by
the overall Job deadline, and failure termination retains its five-second drain.
This source option has portable controller tests. It has not yet closed the
native shutdown gate: a baseline story was captured successfully, but an owned
descendant exceeded the default grace. Subsequent checks found no remaining
provider process or listener after the controller's owned cleanup. The saved
evidence does not identify the lingering descendant or prove that longer grace
will suffice.

## Installation and comparison sequence

1. Prepare a private operation packet with the reviewed manifests, exact source
   and runtime hashes, candidate directory, storage budget and rollback identity.
   Obtain authority for downloading weights and running temporary providers.
2. Recheck disk, RAM and GPU capacity on the runtime host. Reuse verified cached
   blobs, refuse conflicting manifests, bound downloads, and preserve partial
   failure evidence. Do not download weights to the Mac or add them to Git.
3. Start only an owned loopback provider under an enforced process/memory/time
   limit. Test the 9B and 12B candidates first, then admit 27B only with sufficient
   headroom. Keep the live service selection unchanged.
4. Capture the same three [memoir cases](../server/docs/security/MEMOIR_QUALITY_CASES_V1.md)
   for each candidate, one request at a time. Measure cold load, request duration,
   peak memory, completion/truncation, valid schema and exact source citations.
   Add bounded companion follow-ups and separate polish/title cases before
   claiming those roles qualified. No automatic retry or fallback.
5. Review grounded facts, uncertainty, attribution, chapter continuity, Chinese
   style, repeated-caption avoidance and withheld-source handling using the
   [private worksheet](MODEL_QUALIFICATION.md#enter-human-judgments-with-a-private-worksheet).
   A valid schema is not a story-quality verdict.
6. Select roles independently. Keep a smaller interactive model if the larger
   one only helps book synthesis. Proposals remain reviewable and original
   contributions remain intact. Activate only after resource and quality gates,
   with a separately authorized switch and retained rollback.

Changing the narrative model does not replace ASR, TTS, face recognition,
embeddings or the image-caption provider. Each has its own contract and
[replacement lifecycle](MODEL_PROVIDER_ARCHITECTURE.md).
