#!/usr/bin/env python3
"""Source/package policy checks supplement behavioral TLS and privacy tests."""
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
ns = '{http://schemas.android.com/apk/res/android}'
manifest = ET.parse(root / 'connected/src/main/AndroidManifest.xml').getroot()
# Voice capture and owner-approved OTA installation are existing opt-in features.
# Retain an exact allowlist so unrelated permissions still fail this gate.
assert {p.get(ns + 'name') for p in manifest.findall('uses-permission')} == {
    'android.permission.INTERNET', 'android.permission.ACCESS_NETWORK_STATE',
    'android.permission.RECORD_AUDIO', 'android.permission.REQUEST_INSTALL_PACKAGES',
}
app = manifest.find('application')
for name in ('allowBackup', 'fullBackupContent', 'usesCleartextTraffic'):
    assert app.get(ns + name) == 'false'
network = ET.parse(root / 'connected/src/main/res/xml/network_security_config.xml').getroot()
assert network.find('base-config').get('cleartextTrafficPermitted') == 'false'
assert [cert.get('src') for cert in network.iter('certificates')] == ['system']
assert network.find('debug-overrides') is None
for module in ('connected', 'live-core'):
    config = (root / module / 'build.gradle.kts').read_text()
    assert 'project(":core")' not in config and 'project(":app")' not in config
    if module == 'live-core':
        assert 'project(":home-core")' not in config
    for source in (root / module / 'src/main').rglob('*.kt'):
        text = source.read_text()
        for forbidden in ('FixtureRepository', 'SharedPreferences', 'SavedStateHandle', 'rememberSaveable', 'FileOutputStream', 'hostnameVerifier(', 'sslSocketFactory(', 'WebView(', 'HttpLoggingInterceptor'):
            if forbidden == 'FileOutputStream' and source == root / 'connected/src/main/java/dev/photohouse/connected/KeystoreSessionPersistence.kt':
                assert 'noBackupFilesDir' in text and 'AndroidKeyStore' in text and 'AES/GCM/NoPadding' in text
                continue
            assert forbidden not in text, f'{source.name}: unexpected {forbidden}'
activity = (root / 'connected/src/main/java/dev/photohouse/connected/MainActivity.kt').read_text()
assert 'FLAG_SECURE' in activity and 'model.store?.background()' in activity and 'model.store?.foreground()' in activity
print('PASS connected app system TLS trust, no fixture dependencies, Keystore-only session persistence; no password/media persistence or logging')

# The owner's explicit Home mode is a separate Activity/transport, never an auth fallback.
activities = {a.get(ns + 'name'): a for a in app.findall('activity')}
assert activities['.HomeActivity'].get(ns + 'exported') == 'false'
assert activities['.MainActivity'].get(ns + 'exported') == 'false'
assert activities['.AccessActivity'].get(ns + 'exported') == 'true'
main = root / 'connected/src/main/java/dev/photohouse/connected'
for name in ('HomeActivity.kt', 'HomePhoneApp.kt', 'HomePlaybackSource.kt'):
    text = (main / name).read_text()
    for forbidden in ('HttpsPhotoHouseApi', 'ConnectedStore', 'Authorization', 'Bearer(', 'PHOTOHOUSE_ORIGIN', 'PHOTOHOUSE_DISCOVERY_ENABLED'):
        assert forbidden not in text, (name, forbidden)
assert 'dev.photohouse.home' not in activity
assert 'HomeLanAddress.parse(BuildConfig.PHOTOHOUSE_HOME_LAN_ADDRESS)' in (main / 'HomeActivity.kt').read_text()
assert 'Https' not in (main / 'AccessActivity.kt').read_text()
print('PASS explicit phone Home mode, private LAN routing, separate protected transport')

public_lane = (root.parent / 'scripts/verify-android.sh').read_text()
for field in ('photohousePhoneHomeOrigin', 'photohousePhoneHomeLanAddress'):
    assert '-P' + field + '=' in public_lane
