# Automatic memory attribution

New photo and video memory editors prefill the optional byline from the
currently authorized account's chosen display name. The authenticated server
session still determines the author. Missing, blank, malformed, control
containing, or overlong names leave the optional byline empty; the phone number
and account ID are not fallbacks.

Existing memories and restored drafts retain their exact byline, including a
blank one. A family can clear or change the field during review. Those changes
stay bound to the frozen save request during retry and conflict recovery. The
feature does not rewrite the memory text, add unauthored contributors, or save
automatically.

The phone labels title and byline as optional in Chinese and English. JVM tests
cover profile bounds and save behavior; connected UI checks use synthetic
accounts and generated data. Candidate checks and installed-device acceptance
are recorded separately.
