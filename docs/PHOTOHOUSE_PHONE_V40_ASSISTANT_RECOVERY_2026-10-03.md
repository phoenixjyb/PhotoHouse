# Phone v40 assistant recovery candidate

The source extends the existing protected assistant without adding wire fields,
automatic retries, background listening or automatic actions. Phone v39 remains
the last verified OTA release until a separate artifact/publication record says
otherwise.

## User flow

- Sending a reviewed question clears only the accepted submitted draft. Validation
  rejection keeps the draft editable.
- An uncertain POST result retains its exact question, context, request ID,
  account and library in the active assistant scope. Receipt queries are GETs;
  they never resubmit the question.
- A succeeded receipt does not pretend to recover an absent reply or updated
  context. The user can acknowledge and start a new conversation. A newer unsent
  draft survives this action; the old submitted question is not inserted again.
- A server-recorded failed/interrupted turn can restore its question as an
  editable draft only when no newer draft exists. Sending still requires an
  explicit user action.
- Clearing or changing scope fences late replies/transcripts. New recording and
  text submission cannot overwrite a pending turn's receipt.

The pending status, receipt query, acknowledgement and read-only question share
the scrollable conversation body. Core tests and a focused 150% emulator journey
passed at source `ced1e1090d47192563041e34b27e900797771942`; the screenshot was
reviewed. That Compose capture did not include the OS keyboard.

The unified open-source candidate imported the phone source at
`9717b7aaf89f4516aa18b0daaef29ca9be7084ac` and records it as the
`phone-assistant-receipt-recovery-v40` overlay in
`docs/feature-source-changes.json`. The candidate keeps its public build
configuration; only the phone version fields changed to v40. Two explanatory
strings in `AssistantScreen.kt` were clarified to name the unrecovered updated
context and state directly that receipt checking never resends the request.

On 2026-10-03, `python3 tools/check.py android` passed: 592 JVM unit tests,
both debug lint tasks, and connected/TV debug assembly. The focused
`ConnectedUiTest` cases `assistantUncertainTurnKeepsReviewedTextAndReceiptCheckNeverResends`
and `uploadHistoryShowsStatesPagesTenPlusTwoAndOpensAvailableAsset` then passed
on `emulator-5558` at 150% font scale (2 tests, 0 failures). The tests use a
synthetic API. Rendered pending-receipt and upload-history screenshots were
inspected; the upload test scrolls to the third row before asserting it is
visible. The pending-turn test also verifies the IME is open while the pending
status, receipt check, acknowledge action and composer are displayed. Its
`FLAG_SECURE` window prevents an OS-keyboard screenshot. The generated APKs are
unconfigured local debug artifacts, not release packages. Hosted CI and a
physical-device test were not run.

The broader 34-case emulator run had 33 passes and one upload-history visibility
assertion failure at 150%. Follow-up `8e07f4066f8e846235a6d4488b2585c03191b567`
confirmed that the row is reachable by scrolling and corrected the test to wait
for asynchronous pagination. The focused upload-history and pending-turn journeys
then passed at 150%; pending controls and the composer were displayed while OS
IME insets confirmed an open keyboard. FLAG_SECURE remains enabled; the app
surface was rendered and reviewed without an OS-keyboard screenshot. The whole
34-case class was not rerun after those focused corrections.

A release candidate build passed core tests, release unit tests, lint and assembly
at `0157f1d`; subsequent source simplifies recovery wording and imports the focused
test corrections. The final release artifact, original signing, OTA payload check
and physical Samsung use remain separate delivery checks.

Server assistant records retain text, commands and processing status for 30 days.
Recordings remain transient. Pending client details are memory-only and are
discarded on scope invalidation or process loss; this is not durable offline chat.
