# Web memoir editorial context choice v1

The memoir chat and draft suggestions forms offer an optional, unchecked choice to include the book's saved opening and transitions in a request. The control is available for family viewers as well as editors. It does not change story-only conversations, and it does not change any request when left unchecked.

## Explicit selection

Checking the control first performs a read-only request to `GET /memory-community/v1/books/{book_id}/plan?library={library}&editorial_context=1`. The browser selects the option only after the response matches the attached book and revision, reports `context_profile: memoir_editorial_v1`, has no generated or queued work, and reports `whole.state: within_limits` with an integer `whole.context_bytes` value from 1 through 65,536. A `smaller_scope_required` result must have `whole.context_bytes: null`. `whole.can_draft` may be false for a viewer; selection depends on the saved whole-book context being within limits, not on draft permission.

This preflight only verifies the saved context. It does not request a model reply, create a job or turn, start speech, or alter the request body. While it is pending, sending is blocked. A failed or invalid response leaves the choice unchecked and keeps typed words. A 409 asks the family to refresh the saved opening/transitions; a 422 asks them to narrow the scope; an unavailable response asks them to try later. After a failed check, sending remains blocked until the user retries the check or explicitly chooses to continue with the existing memoir context. The browser does not treat an unchecked box after an error as consent to silently fall back.

The selected choice is scoped to the current account, library, book, and revision. Detaching or changing that target, locking access, or successfully creating, switching, resuming, or closing a conversation clears it. Switching tabs during a pending check cancels that check and requires a fresh check or an explicit choice to continue with the existing context. Stale preflight responses are ignored; a ready choice and unsent text remain intact across an ordinary tab rerender.

## Sending and retrying

When the user explicitly sends a chat message or suggestion, the selected boolean is frozen with that message or job draft. An opted-in request adds `editorial_context=1` to the existing POST URL:

- `POST /memory-community/v1/conversations/{conversation_id}/turns?editorial_context=1`
- `POST /memory-community/v1/jobs?editorial_context=1`

The existing JSON fields remain unchanged. After an uncertain send result, retry reuses the same request ID, text, body, and frozen choice. Editing the visible input does not rewrite that pending request. A 409 clears the rejected frozen request but preserves its text, shows that saved context changed, and requires another check or an explicit choice to continue with the existing context before sending again. The job response does not carry a context profile for the browser to display.

With the option unchecked, the existing URLs and bodies are unchanged. No preference is persisted across books, accounts, or sessions.

## Verification boundary

The UI and browser journeys use synthetic requests and family data. The browser test adapts the synthetic API response for the opt-in plan query because its local server profile has editorial context disabled; it preserves and asserts the actual browser query and verifies no turn/job is sent by preflight. These checks do not establish behavior against a live service or a real family account.
