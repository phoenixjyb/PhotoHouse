# Story title assistance

Title assistance offers up to three editable proposals after a family arranges
selected media into chapters. It appears only when the protected capability
reports an explicitly injected adapter. The family chooses whether to adopt a
proposal, can edit it, and saves through the existing explicit story save. A
suggestion request does not save or publish a story.

Each proposal cites current source references or the edited chapter drafts used
to form it. The server validates the citation IDs and selection revision. A
changed selection or source invalidates the result. Dates, filenames, and receipt
times are not promoted into event claims. Suggestions remain editorial proposals,
not proof that people, dates, or activities are correct.

The protected preview, capability, suggestion, and create operations use bounded
requests and responses, current library authorization, and no-store responses.
Suggestion context and results are transient. Provider access is explicit,
loopback-only, serialized per process, and disabled by default; the normal
runtime does not configure the adapter. Synthetic API and browser tests use a
fixed adapter and generated family data. They do not qualify provider quality or
live delivery.
