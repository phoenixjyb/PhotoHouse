#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
python3 scripts/verify-contracts.py
python3 android/verify-fixture-boundaries.py
python3 android/verify-connected-boundaries.py
python3 android/verify-home-contract.py
python3 android/verify-catalog-contract.py
python3 android/verify-discovery-contract.py
python3 android/verify-discovery-delivery-contract.py
python3 android/verify-tag-discovery-contract.py
python3 android/verify-calendar-contract.py
python3 android/verify-phone-discovery-contract.py
python3 android/verify-tv-boundaries.py
python3 android/verify-on-demand-contract.py
python3 android/verify-readiness-browse-contract.py
if [[ -z "${JAVA_HOME:-}" && "$(uname -s)" == Darwin ]]; then
  export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
fi
java_bin="${JAVA_HOME:+$JAVA_HOME/bin/}java"
java_version="$("$java_bin" -version 2>&1)"
if [[ "$java_version" != *'version "17.'* ]]; then
  echo 'JDK 17 required. Set JAVA_HOME to an already installed JDK 17.' >&2
  exit 2
fi
sdk_dir="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [[ -z "$sdk_dir" || ! -f "$sdk_dir/platforms/android-34/android.jar" || ! -d "$sdk_dir/build-tools/34.0.0" ]]; then
  echo 'Existing SDK platform 34 and build-tools 34.0.0 required. No SDK installation is performed.' >&2
  exit 2
fi
printf '%s\n' "$java_version"
android/gradlew -p android --version
# This verification lane always produces unconfigured, synthetic-test artifacts.
android/gradlew -p android :core:test :story-fixture-core:test :playback-core:test :live-core:test :home-core:test :tv:testDebugUnitTest \
  :app:lintDebug :app:assembleDebug :connected:lintDebug :connected:assembleDebug \
  :tv:lintDebug :tv:assembleDebug --console=plain "$@" \
  -PphotohouseOrigin= -PphotohousePhoneHomeOrigin= -PphotohousePhoneHomeLanAddress= -PphotohouseTvOrigin= -PphotohouseTvLanAddress= \
  -PphotohousePhoneUploadEnabled=false -PphotohouseStoryFixtureEnabled=false -PphotohouseHomeCalendarEnabled=false -PphotohouseHomeTagLookupEnabled=false -PphotohouseTvCatalogVersion=2 -PphotohouseTvBrowseEnabled=false -PphotohouseTvDiscoveryEnabled=false -PphotohousePhoneDiscoveryEnabled=false -PphotohousePhoneHomeDiscoveryEnabled=false
python3 - <<'PY'
import hashlib, pathlib, zipfile, xml.etree.ElementTree as ET
root = pathlib.Path('.')
apk = root / 'android/app/build/outputs/apk/debug/app-debug.apk'
with zipfile.ZipFile(apk) as z:
    for p in (root/'contracts/v1').rglob('*'):
        if p.is_file():
            name = 'assets/' + p.relative_to(root/'contracts/v1').as_posix()
            assert z.read(name) == p.read_bytes(), f'Bundled fixture drift: {name}'
print('PASS APK bundles the shared contract and media byte-for-byte')
print('APK SHA-256:', hashlib.sha256(apk.read_bytes()).hexdigest())
reports = [p for folder in ['playback-core/build/test-results/test', 'core/build/test-results/test', 'story-fixture-core/build/test-results/test', 'live-core/build/test-results/test', 'home-core/build/test-results/test', 'tv/build/test-results/testDebugUnitTest'] for p in sorted((root/'android'/folder).glob('TEST-*.xml'))]
assert reports, 'No JVM test reports'
for p in reports:
    s = ET.parse(p).getroot()
    assert s.attrib['failures'] == '0' and s.attrib['errors'] == '0', p
    print(f"JVM {s.attrib['name']}: {s.attrib['tests']} tests, {s.attrib['failures']} failures, {s.attrib['errors']} errors")
connected = root / 'android/connected/build/outputs/apk/debug/connected-debug.apk'
with zipfile.ZipFile(connected) as z:
    assert not any(n.startswith('assets/') for n in z.namelist()), 'Connected app must not bundle fixtures'
    assert not any(b'dev/photohouse/stories/' in z.read(n) for n in z.namelist() if n.endswith('.dex')), 'Story lab must be excluded from ordinary builds'
print('Connected APK SHA-256:', hashlib.sha256(connected.read_bytes()).hexdigest())
for module, package in [('connected', 'connected'), ('tv', 'tv')]:
    config = (root/f'android/{module}/build/generated/source/buildConfig/debug/dev/photohouse/{package}/BuildConfig.java').read_text()
    assert 'PHOTOHOUSE_ORIGIN = "";' in config, 'Public verification must use an unconfigured origin'
    if module == 'connected':
        assert 'PHOTOHOUSE_HOME_ORIGIN = "";' in config
        assert 'PHOTOHOUSE_HOME_LAN_ADDRESS = "";' in config
    if module == 'tv':
        assert 'PHOTOHOUSE_LAN_ADDRESS = "";' in config, 'Public verification must not embed a private address'
        tv = root/'android/tv/build/outputs/apk/debug/tv-debug.apk'
        with zipfile.ZipFile(tv) as z:
            assert not any(n.startswith('assets/') for n in z.namelist()), 'TV app must not bundle fixtures'
            assert not any(b'dev/photohouse/stories/' in z.read(n) for n in z.namelist() if n.endswith('.dex')), 'Story lab must be excluded from ordinary builds'
        print('TV APK SHA-256:', hashlib.sha256(tv.read_bytes()).hexdigest())
PY
"$sdk_dir/build-tools/34.0.0/aapt" dump permissions android/app/build/outputs/apk/debug/app-debug.apk > android/app/build/outputs/apk/debug/permissions.txt
python3 - <<'PY_PERMISSIONS'
from pathlib import Path
import re
text = Path('android/app/build/outputs/apk/debug/permissions.txt').read_text()
permissions = set(re.findall(r"uses-permission: name='([^']+)'", text))
assert permissions <= {'dev.photohouse.fixture.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION'}, permissions
print('PASS APK has no Internet, storage, camera or microphone permissions; only AndroidX app-internal signature permission')
PY_PERMISSIONS

"$sdk_dir/build-tools/34.0.0/aapt" dump permissions android/connected/build/outputs/apk/debug/connected-debug.apk > android/connected/build/outputs/apk/debug/permissions.txt
python3 - <<'PY_CONNECTED_PERMISSIONS'
from pathlib import Path
import re
text = Path('android/connected/build/outputs/apk/debug/permissions.txt').read_text()
permissions = set(re.findall(r"uses-permission: name='([^']+)'", text))
# Media3 merges the normal network-state permission for connectivity observation.
# Keep an exact allowlist so other dependency permissions still fail this gate.
assert permissions == {'android.permission.INTERNET', 'android.permission.ACCESS_NETWORK_STATE', 'dev.photohouse.connected.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION'}, permissions
print('PASS connected APK has only Internet, network-state and AndroidX app-internal permissions; no fixture assets')
PY_CONNECTED_PERMISSIONS

"$sdk_dir/build-tools/34.0.0/aapt" dump permissions android/tv/build/outputs/apk/debug/tv-debug.apk > android/tv/build/outputs/apk/debug/permissions.txt
python3 - <<'PY_TV_PERMISSIONS'
from pathlib import Path
import re
text = Path('android/tv/build/outputs/apk/debug/permissions.txt').read_text()
permissions = set(re.findall(r"uses-permission: name='([^']+)'", text))
assert permissions == {'android.permission.INTERNET', 'android.permission.ACCESS_NETWORK_STATE', 'dev.photohouse.tv.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION'}, permissions
print('PASS TV APK has only Internet, network-state and AndroidX app-internal permissions; no fixture assets')
PY_TV_PERMISSIONS
