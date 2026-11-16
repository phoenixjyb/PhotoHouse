#!/usr/bin/env python3
"""Source checks for TV isolation; not a runtime/security acceptance claim."""
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
main = root / 'tv/src/main'
a = '{http://schemas.android.com/apk/res/android}'
manifest = ET.parse(main / 'AndroidManifest.xml').getroot()
assert [p.get(a+'name') for p in manifest.findall('uses-permission')] == [
    'android.permission.INTERNET', 'android.permission.ACCESS_NETWORK_STATE', 'android.permission.REQUEST_INSTALL_PACKAGES'
]
features = {e.get(a+'name'): e.get(a+'required') for e in manifest.findall('uses-feature')}
assert features == {'android.software.leanback': 'false', 'android.hardware.touchscreen': 'false', 'android.hardware.faketouch': 'false'}
app = manifest.find('application')
for flag in ['allowBackup', 'fullBackupContent', 'usesCleartextTraffic']:
    assert app.get(a+flag) == 'false'
activity = app.find('activity')
assert activity.get(a+'screenOrientation') == 'landscape'
categories = {e.get(a+'name') for e in activity.findall('intent-filter/category')}
assert categories == {'android.intent.category.LAUNCHER', 'android.intent.category.LEANBACK_LAUNCHER'}
for name in ['network_security_config.xml', 'data_extraction_rules.xml']:
    assert (main/'res/xml'/name).read_bytes() == (root/'connected/src/main/res/xml'/name).read_bytes()
guest = root / 'tv/src/guestStories/java'
protected_stories = root / 'tv/src/protectedStories/java'
anonymous_files = [*(main/'java').rglob('*.kt'), *guest.rglob('*.kt')]
assert any(path.name == 'GuestTvProtectedStories.kt' for path in anonymous_files)
source = '\n'.join(p.read_text() for p in anonymous_files)
for forbidden in ['SharedPreferences', 'rememberSaveable', 'SavedStateHandle', 'FileOutputStream', 'WebView', 'hostnameVerifier', 'sslSocketFactory', 'android.util.Log', 'java.io.File', 'MediaStore', 'dev.photohouse.fixture', 'PasswordVisualTransformation', 'KeyboardType.Password', 'store.authenticate(', 'dev.photohouse.connected', 'originalPhoto', 'viewingOriginal', 'state.session', 'Bearer']:
    assert forbidden not in source, forbidden
# The user authorized search input. Only its memory-only editor may collect text;
# setup, connection and playback retain their no-personal-sign-in boundary.
for path in anonymous_files:
    if path.name != 'TvDiscovery.kt':
        assert 'OutlinedTextField' not in path.read_text() and 'BasicTextField' not in path.read_text(), path.name
for required in ['FLAG_SECURE', 'store?.background()', 'store?.foreground()', 'HomeOrigin.parse', 'HomeLanAddress.parse(BuildConfig.PHOTOHOUSE_LAN_ADDRESS)', 'state.display', 'state.feed']:
    assert required in source, required
build = (root/'tv/build.gradle.kts').read_text()
assert 'photohouseTvLanAddress' in build
assert 'photohouseTvOrigin' in build and 'project(":home-core")' in build
assert 'gradleProperty("photohouseTvStoryApprovalEnabled").orElse("false")' in build
assert 'if (storyApprovalEnabled == "true") "src/protectedStories/java" else "src/guestStories/java"' in build
assert build.count('project(":live-core")') == 1
assert 'if (storyApprovalEnabled == "true") implementation(project(":live-core"))' in build
assert 'createTvProtectedStories(scope: CoroutineScope): TvProtectedStories? = null' in source
protected = '\n'.join(path.read_text() for path in protected_stories.rglob('*.kt'))
assert 'TrustedOrigin.parse(BuildConfig.PHOTOHOUSE_TV_STORY_ORIGIN)' in protected
assert 'PHOTOHOUSE_ORIGIN' not in protected and 'PHOTOHOUSE_LAN_ADDRESS' not in protected
for forbidden in ['SharedPreferences', 'rememberSaveable', 'SavedStateHandle', 'FileOutputStream', 'WebView']:
    assert forbidden not in protected, forbidden
assert 'project(":core")' not in build and 'project(":app")' not in build
assert 'if (uiQa == "true") applicationIdSuffix = ".qa"' in build
print('PASS TV launcher/no-touch, anonymous catalog isolation, optional protected story origin and memory-only session')
