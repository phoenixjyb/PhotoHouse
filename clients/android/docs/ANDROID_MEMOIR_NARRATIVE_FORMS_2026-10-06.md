# Android memoir narrative forms

The memoir narrative store has a local form choice: `EXISTING`, `CHRONICLE`, `ESSAY`, or `LONG_MEMOIR`. The default `EXISTING` path keeps the current request instructions exactly as entered. The other choices add a fixed Chinese model instruction to the existing `instructions` field at queue time, separated from the user's editable text by one newline. The selected form is never a new API field and does not change the request schema.

Changing a form is an explicit local state update. It makes no plan, provider, or queue request and does not invalidate a saved structure plan because the plan is independent of writing style. It clears any prior job, review proposal, and frozen retry request. The form prompt and the base instructions are checked together against the existing 4,096-byte UTF-8 limit; a rejected change leaves the previous text and form intact.

A form selection with no user text counts as unfinished input. It remains selected after definite 409 stale-scope and 422 size rejections so the user can review the choice and explicitly check the plan again. A retry after an uncertain queue result stays frozen to the exact request, including its form instruction. Clearing the reader scope resets the form to `EXISTING`.

The focused core tests exercise exact legacy request text, form augmentation without changing the editable base, saved-plan reuse, combined UTF-8 overflow, frozen retries, definite rejection retention, and clear/stale-scope resets. This is source and unit-test evidence only; it does not establish provider quality or device, service, or family acceptance.

## Phone integration and checks

The optional chooser is collapsed by default and uses complete bilingual labels and
48dp radio rows. Voice work and uncertain requests freeze the form controls. Rejected
combined input retains the full local wording; the UI requires the user to shorten it
and explicitly choose again. Form and unsent text survive an acknowledged manual
memoir revision, while the old context plan is cleared. Library changes reset them.

Final source checks passed 12 narrative-store, 53 community-store and 6 editorial
integration cases (71 total), plus debug lint. Two Chinese/English 150% emulator
journeys passed the complete Gradle run; the owner reviewed the final unmasked
options/ready images. Earlier runs included an emulator transport cleanup failure
and SystemUI ANR overlays; those captures are not accepted visual evidence. The
same existing AVD was recovered without deleting userdata or creating another AVD.

No model, Windows service, signing, OTA publication or physical phone was qualified
by this slice. The source is newer than the frozen v42 APK.
