# Assistant result assets and date provenance

## Compatible protected results

The protected search assistant's discovery result currently has seven asset
fields: `id`, `kind`, `width`, `height`, `duration_sec`, `taken_at` and
`thumbnail_url`. Gallery reads can separately opt into `date_hint`; the assistant
response does not promise it. Android accepts the seven-field form and the same
form with an optional `date_hint`, for both search results and opening a result.

Absent or null hints stay unknown. A present hint must retain a supported
`filename` or `received` source. Unknown asset fields, unsupported hint sources,
invalid IDs and thumbnails outside the selected library still fail validation.
Compatibility does not relax protected media access or open-effect checks.

Phone assistant result cards use the same date presentation as the gallery:
recorded capture metadata takes precedence; filename dates and receipt dates
carry their localized provenance labels. Missing dates display **Date unknown /
日期未知**. Neither fallback is presented as a confirmed capture date. This client
change does not add date hints to the server's assistant response.

## Local evidence

Source `c566ded` includes decoder regressions for seven-field results/open effects,
hint validation and a MockWebServer protected transport journey. The server's
existing find/refine/open HTTP journey now pins its actual seven-field response.
The focused server cohort passed 11 tests and five subtests before the later
conversation-limit cohort was integrated.

English and Chinese generated Compose journeys at 150% text size passed, checking
capture-date precedence, labeled filename/received hints and unknown dates in
actual assistant cards. JVM checks, phone debug/AndroidTest assembly and lint
also passed. A preceding complete Android profile reported 951 tests with no
failures, with unchanged tasks up to date; the later transport test is separately
checked and is not included in that historical inventory.

These are local source/transport/emulator checks. They do not establish newly
served bytes, an installed Samsung update or a live family search result.
