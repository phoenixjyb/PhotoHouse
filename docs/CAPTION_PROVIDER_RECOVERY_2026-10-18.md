# Caption provider recovery and released-batch verification

## Source and checkpoint

This follow-through uses the receipt-selected worker qualified at source
`d615583a2a2c98be3daf47e82dfab68fa3186b77`. Its
[native offline qualification](NATIVE_CAPTION_QUALIFICATION_2026-10-18.md) remains
separate evidence from loading a model or processing family media.

The existing Windows checkpoint is Qwen3-VL-8B-Instruct. All 16 local checkpoint
files were hashed; the four weight shards total **17,534,339,512 bytes** and match
the size and SHA-256 values in the
[publisher's LFS metadata](https://huggingface.co/api/models/Qwen/Qwen3-VL-8B-Instruct/tree/main).
Weights were reused on Windows. No checkpoint was downloaded to the source Mac.

The observed provider environment is Python 3.13.5, PyTorch 2.6.0+cu124,
Transformers 5.2.0, Accelerate 1.10.0 and bitsandbytes 0.49.2. This operation does
not install or upgrade those packages. The provider source, installed loader,
Python executables, checkpoint contents and selected GPU identity are pinned in
the private operation record.

## Startup diagnosis

The native attempts exposed three distinct boundaries:

- `nvidia-smi` succeeds in the outer supervisor but returns an NVML initialization
  error inside the restricted Job. GPU sampling belongs in the outer supervisor,
  including the readiness-record path. Monitoring refusal must fail the run.
- Full checkpoint loading under a 24 GiB server Job ended with Windows access
  violation `0xc0000005` during tensor materialization. Job accounting recorded
  approximately 26 GiB peak committed memory. Disabling asynchronous loading
  alone did not resolve it. Small, finite NF4 tensor quantization/dequantization
  passed separately; its result does not qualify full checkpoint loading.
- With a 32 GiB server Job and the same checkpoint/runtime, the full model loaded
  in 13.8 seconds after imports and checkpoint verification. Provider admission
  requires the exact local model-path identity, Qwen3-VL class, `cuda:0` on the
  selected RTX 3090, NF4 and actual four-bit loading.

The installed loader's supported `HF_DEACTIVATE_ASYNC_LOAD=1` switch keeps tensor
materialization sequential. The
[Transformers 5.2 loader source](https://raw.githubusercontent.com/huggingface/transformers/v5.2.0/src/transformers/core_model_loading.py)
documents that branch. This setting accompanies the measured resource budget;
the serial-only attempt still failed under the smaller budget.

Failed candidate directories, claims, stop markers, native logs and accounting
were retained. Each corrected attempt used a fresh private directory. No failed
operation was replayed or cleared.

## One-time supervision

The bounded recovery uses:

| Boundary | Policy |
| --- | --- |
| Whole session | 15 minutes maximum; stop guard after 13.5 minutes |
| Session process tree | 36 GiB Job memory; 16 processes |
| Provider process tree | 32 GiB Job memory; eight processes |
| RAM admission / running floor | 44 GiB / 8 GiB available RAM |
| GPU | One pinned RTX 3090 UUID; 70% PyTorch allocator fraction; outer sampling stops at 20 GiB total used |
| Each caption client | 2 GiB; eight processes; five minutes; 8 GiB available-RAM floor |

The admitted provider reported a **6,258,342,952-byte model footprint** and a
14.0-second model load after imports/checkpoint verification. This is the model's
reported footprint, not total GPU allocation or startup host-memory demand.

GPU sampling is periodic, and the allocator fraction covers PyTorch allocations;
these checks are not an instantaneous limit on every driver allocation. Both
provider and client run under owned Jobs. Explicit Job proofs are checked before
work; teardown terminates and drains owned descendants. Native stdout/stderr,
fault traces, exit codes and peak Job accounting are retained privately.

HF/Transformers offline mode, an explicit local checkpoint path and a private
scratch directory prevent an implicit model download. The legacy broad caption
task remains idle. This is a one-time batch operation; persistent provider startup
and automatic processing of later uploads are separate deployment work.

## Released-batch outcome

The generated-image canary passed against the actual local provider before family
media was admitted. The exact 17 released caption tasks then completed serially.
An independent read-only database/source/preview check confirmed:

| Evidence | Result |
| --- | --- |
| Caption tasks | 17 finished; zero task retries |
| New bilingual captions | 17; zero shared-policy violations |
| Completion receipts | 17; persisted digests verified |
| Originals | All 17 hashes match the initial snapshot and database |
| JPEG previews | All 34 files decode at the two expected variants |
| Earlier work | Vector, face and hash results preserved; original acceptance/release receipts retained |
| Earlier failed thumbnail row | Retained unchanged; its derived pair remains readable |
| Provider lifecycle | Owned server/session Jobs drained; provider endpoint no longer reachable |
| Other live delivery | API task/action/configuration/entry and both OTA pointers unchanged |

The measured server Job peak was **32,251,416,576 bytes of committed memory**;
the outer sampler observed **12,319 MiB total GPU usage** at its peak. No resource
monitor refused the successful run. These are observed accounting/sample values,
not a benchmark or a universal resource requirement for other model versions.

Ten private portable controller checks include scope/identity/quantization refusal,
exclusive claims, cleanup after errors, monitor refusal and a readiness-to-batch
workflow that rejects any GPU query inside the session. Native inference and
independent readback establish the additional live acceptance tier.

This completes the selected batch's caption work. Persistent startup, automatic
processing of later batches, the general API/installed CPU-worker repair, and
phone/Web/TV family review remain separate gates. The source PR is not merged by
this operation. See the [worker contract](../server/docs/security/RELEASED_CAPTION_WORKER.md)
for publication, concurrent-edit and retry rules.
