# Grouped story creation

The phone flow lets an authorized family select 1–24 photos or videos from one
library, group them into editable chapters, review the sources, and explicitly
save one story. Only the protected server capability grants access to creation;
a displayed role label cannot override a denial. The server rechecks membership,
source revisions, media membership, and citations at save time.

The client keeps selection and draft state in memory. It clears that state and
thumbnail buffers on sign-out, library change, background privacy cover, or
explicit close. Requests and responses are bounded and tied to the account,
library, and editor generation. Save retries reuse the reviewed mutation body;
the client does not create a second save after an uncertain response.

Title suggestions are optional and require explicit adoption. The server's
capability remains off unless an adapter is deliberately supplied. Grouped-story
text and audio contributions belong once to the saved story or to one selected
chapter. Original recordings remain separate from transcripts and edited prose.

The current phone client uses the protected HTTPS API and has no LAN or legacy
fallback. Android contract fixtures replay against the curated `server/` tree;
the manifest retains upstream source hashes and separately pins the candidate
server files used by the replay. Local tests and builds do not establish live
service, provider, signed-package, device, or family acceptance.
