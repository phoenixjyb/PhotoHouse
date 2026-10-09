#!/usr/bin/env python3
"""Offline guard for committed wrapper, ownership-independent fixture packaging and privacy wiring."""
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
expected_jar = (root / 'gradle/wrapper.sha256').read_text().strip()
assert expected_jar == '2db75c40782f5e8ba1fc278a5574bab070adccb2d21ca5a6e5ed840888448046'
assert hashlib.sha256((root / 'gradle/wrapper/gradle-wrapper.jar').read_bytes()).hexdigest() == expected_jar
expected_zip = (root / 'gradle/distribution.sha256').read_text().strip()
assert expected_zip == '31c55713e40233a8303827ceb42ca48a47267a0ad4bab9177123121e71524c26'
assert f'distributionSha256Sum={expected_zip}' in (root / 'gradle/wrapper/gradle-wrapper.properties').read_text()
manifest = ET.parse(root / 'app/src/main/AndroidManifest.xml').getroot()
assert not manifest.findall('uses-permission'), 'Fixture app must not request permissions'
app = manifest.find('application')
ns = '{http://schemas.android.com/apk/res/android}'
assert app.get(ns + 'allowBackup') == 'false'
assert app.get(ns + 'usesCleartextTraffic') == 'false'
assert app.get(ns + 'fullBackupContent') == 'false'
for source in list((root / 'app/src/main').rglob('*.kt')) + list((root / 'core/src/main').rglob('*.kt')) + list((root / 'protocol/src/main').rglob('*.kt')):
    text = source.read_text()
    for forbidden in ('import java.net.', 'import okhttp3.', 'import retrofit2.', 'WebView(', 'SharedPreferences', 'SavedStateHandle', 'rememberSaveable', 'FileOutputStream', 'MediaPlayer(', 'ExoPlayer'):
        assert forbidden not in text, f'Unexpected transport/storage/player in {source.name}: {forbidden}'
activity = (root / 'app/src/main/java/dev/photohouse/fixture/MainActivity.kt').read_text()
assert 'FLAG_SECURE' in activity and 'model.store.background()' in activity and 'model.store.foreground()' in activity
rules = ET.parse(root / 'app/src/main/res/xml/data_extraction_rules.xml').getroot()
for section in ('cloud-backup', 'device-transfer'):
    assert {e.attrib['domain'] for e in rules.find(section).findall('exclude')} == {'root', 'file', 'database', 'sharedpref', 'external'}
print('PASS wrapper SHA-256, no permissions/transport/storage/player, lifecycle/backup source guards')

for module in ('app', 'core', 'protocol'):
    config = (root / module / 'build.gradle.kts').read_text()
    for forbidden in ('okhttp', 'retrofit', ':live-core', ':connected'):
        assert forbidden not in config, f'Fixture module {module} depends on real transport'
