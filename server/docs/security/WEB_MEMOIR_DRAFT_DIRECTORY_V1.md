# Web memoir draft chapter directory v1

This local Web UI aid presents the ordered chapter titles already present in a
reviewable whole-memoir narrative result. It does not generate a plan, start a
job, fetch a child story, save, adopt, or alter chapter prose.

## Behavior

- Only memoir narrative proposals with 1–24 chapters receive a directory.
- The native disclosure starts collapsed and lists each existing chapter title
  in proposal order, using its authorized story title and chapter number.
- Choosing a title collapses the directory, stops any prior read-aloud through
  the existing audio-start event, focuses the matching proposal heading, and
  scrolls its article into view. Reduced-motion preference disables smooth
  scrolling.
- One directory control carries `aria-current="location"`; a visible polite
  status names the current draft chapter. The marker exists only in the current
  proposal render.
- While private voice capture or transcription is active, a directory choice
  has no effect. It never starts, stops, or discards a voice task.
- Proposal wording stays visibly marked as AI text for family review. Existing
  source disclosures remain independent and collapsed by default. A memoir
  proposal does not claim to contain the saved original wording.

## Identity and disposal

The directory reuses the proposal renderer's current account/library, target
fingerprint, active job, active ideas tab, render epoch, mounted-root and
connected-node checks. A click also checks that its exact article and heading
remain connected under the rendered proposal and still match the captured
chapter title and ID. Replaced jobs, target revisions, scope changes, rerenders
and detached nodes therefore cannot navigate to stale prose. No directory
handler or selected chapter is retained outside its rendered DOM.

## Scope

This is a client-side view over the existing maximum of 24 ordered memoir
chapters. It preserves the narrative job result and existing source labels and
citations. It does not change API fields, backend validation, model/provider
behavior, whole-book eligibility or the separate story reader.

## Local qualification on 2026-10-06

The lightweight UI harness passed six behavior groups. The protected synthetic
browser suite passed 20 flows with no failures, page errors or external network
requests. Its maximum memoir fixture uses four stories with six chapters each.
Chinese and English at a 390px viewport and 150 percent text were inspected;
font sizes are captured before applying scaling so nested inheritance does not
compound the test font multiplier. The last-chapter heading is also checked
for visibility beneath the sticky reader header. The disclosure keeps its native
open/closed marker. Reduced-motion navigation is exercised explicitly.

These are local synthetic UI checks. No Windows API deployment, model-generated
story quality, real family data or physical-device acceptance is claimed.
