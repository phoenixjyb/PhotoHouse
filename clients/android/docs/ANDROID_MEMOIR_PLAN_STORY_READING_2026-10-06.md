# Android memoir plan: per-story capacity and reading

This UI component presents the sections of an already checked saved memoir plan. It starts collapsed and offers an explicit **Read in this memoir / 在回忆集中阅读** action for each saved story. The component does not generate a story draft, save content, or contact a provider.

Each section shows the full story title, chapter and moment counts, available source counts and kinds, and its own capacity status. A section that fits can still be inspect-only when its `canDraft` flag is false. The whole-book request remains governed by the whole-plan capacity and editability; per-story status does not grant whole-book eligibility. A smaller-scope section does not provide source counts because the plan contract marks those counts unavailable.

The parent integration supplies a key containing the account, session generation, library, book ID and revision, ordered child IDs and revisions, and editorial-context choice. It must also validate the current plan identity and selected book immediately before resolving a section to its current story index. The existing `ConnectedStore.loadMemoryBookStory(index)` then re-fetches the parent book, checks its revision and ordered children, and reads the child at its checked revision. The narrative instructions, selected form, and review proposal remain in their current book scope while that saved story is opened.

After an explicit story selection, the availability directory collapses and the reader scrolls the loaded original into view. The expanded component is local navigation state only. Its caller disables the toggle and story actions while a known operation or scope transition makes navigation unsafe. No new API, request mode, story workspace, or standalone generation path is introduced.

## Verification boundary

The integrated source passed two final Chinese/English 150% emulator journeys
and debug lint. The valid four-story/six-chapter fixture makes the whole plan
over capacity and one readable story inspect-only. It verifies the exact parent
GET before the selected child read, unchanged plan identity, instructions and
ESSAY form, zero generation/save/chat mutations, and directory collapse after
selection. The integration owner inspected the final unmasked originals and
expanded availability screens. Original reading scrolls into view while the
memoir draft stays in its current scope.

The two existing 24-chapter proposal-directory journeys also passed after the
parent integration. An earlier exact-label fixture assertion failed and was
corrected; those failures remain recorded, not counted as passing runs. These
checks do not qualify a signed APK, provider, Windows service or family device.
