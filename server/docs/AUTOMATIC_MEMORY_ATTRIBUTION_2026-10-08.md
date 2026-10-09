# Automatic memory attribution

New photo and video memory editors may prefill the optional byline from the
authenticated profile's chosen display name. The server continues to assign the
author from the authenticated session. Missing, blank, malformed, control
containing, or overlong names produce an empty optional byline; the phone number,
account ID, face identity, and generated text are never fallbacks.

The default applies only to a new editor. Existing memories and restored drafts
keep their saved byline, including an intentionally blank value. Manual edits
remain part of the reviewed save request across retries and conflict handling.
The feature does not change memory text, create contributors, or save
automatically.

The browser behavior uses the existing protected save/read API and generated
test accounts. Malformed profile-name cases verify client handling and do not
qualify the profile API. Live Web delivery and family acceptance are separate.
