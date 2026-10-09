# Chat draft error accessibility

Story and memoir chat composers attach their draft-limit message to the text field as supporting text. Material `isError` marks the field invalid, and the supporting message has a polite live region. The full typed draft stays visible for correction; sending remains disabled under the existing store limit.

Base source: `e7a9cd4` on `codex/phone-v29-candidate-20260929`.

Two focused synthetic API36 emulator journeys passed with zero failures, errors or skips: `savedStoryCommunitySubmissionChatAndProposalStayReviewOnly` and `memoirChatKeepsItsBookThreadAndEditableDraftAcrossStories`. They check the field error semantic, polite supporting message, disabled send action, retained input and error removal after clearing. The memoir Chinese 150% error capture was inspected; the message wraps alongside the field.

The first run's test lookup failed because supporting text is merged into the text-field semantics. The corrected test queries that child tag with `useUnmergedTree = true` and still checks the field's merged error semantic. No validation limit was relaxed.

No new model request, automatic send, wire/store change, version change, signature or publication is included. These are synthetic source/emulator checks; audible TalkBack behavior and physical phone acceptance remain unverified. Lint was not rerun for this small follow-up; the preceding bubble layout had a passing debug lint result.
