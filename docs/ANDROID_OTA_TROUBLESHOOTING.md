# Android update connection checks

The phone and TV update controls use the configured HTTPS origin. The published
version, the installed version and whether a device can reach that origin are
separate checks. A successful update-feed check on the server does not prove a
phone can download the update.

## Local updater improvement

The updater now displays the installed version and distinguishes these outcomes:

- A completely validated feed contains an equal or older version: already current.
- A connection or TLS failure: cannot securely reach the update service.
- Invalid update metadata: update information could not be validated.
- Other preparation failures: the update could not be prepared safely.

Older feed versions still undergo package, channel, signer and same-origin URL
validation before being classified as already current. TLS, artifact hashes,
package signatures and redirect restrictions remain enforced.

This improvement is delivered in phone v50; the earlier phone v49 APK does not
include it. See the [v50 delivery record](../clients/android/docs/PHONE_V50_RELEASE_CANDIDATE_2026-10-12.md).
The changed wire and HTTPS-client checks passed ten focused JVM tests, and the
OTA module and unconfigured phone debug application built successfully. Physical
phone and TV acceptance remains outstanding.

## Diagnose a device connection failure

1. Record the installed version, exact message and whether the device uses home
   Wi-Fi, mobile data or a VPN.
2. Open the configured HTTPS WebUI in the same device's browser. Distinguish a
   timeout from a certificate warning or a successfully loaded sign-in screen.
3. Check the live listener, feed identity and package hash on the server.
4. Compare public DNS with the network's public address. Check whether the server
   uses a hosts-file override; an override can make a server-side check succeed
   without exercising public routing.
5. Check effective firewall rules against the actual listener executable, network
   profile and remote address. Inspecting one port-specific rule is insufficient
   if a separate program rule also applies.
6. Test the public origin from outside the home network. A router hairpin test
   from inside the LAN does not prove external access.

Keep household addresses, screenshots and runtime receipts outside this public
repository. Do not bypass TLS checks or change network access policy to hide a
connection error. Verify the affected phone after any repair.
