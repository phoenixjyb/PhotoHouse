#!/usr/bin/env python3
"""Offline TV contract/fixture and independent phone-pin checks."""
from pathlib import Path
import hashlib,json,re
root = Path(__file__).resolve().parent
home = root/'home-core'
inputs = json.loads((home/'contract/source-inputs.json').read_text())
assert inputs['implementation_commit'] == 'e6b2827842b2c0b5223c85208299b60e8a1257f6'
contract = home/'contract/home-feed-contract-v1.json'
assert hashlib.sha256(contract.read_bytes()).hexdigest() == '70328a653ddaa559bad6a4d654cf9870c89c5217e8e9e6c46a3501e9dd9e7548'
value = json.loads(contract.read_text())
phone_pin = '87a60b475b37b1d6873cd977bcb6e7254472da7e'
assert value['protected_phone_api_pin'] == phone_pin
assert phone_pin in (root.parent/'contracts/v1/manifest.json').read_text()
for name in ['home-feed-contract-v1.json','home-feed-manifest.example.json']:
    assert hashlib.sha256((home/'contract'/name).read_bytes()).hexdigest() == inputs['files']['docs/security/'+name]
for name in ['home-8x8.jpg','home-3840x2160.jpg']:
    raw = (home/'src/test/resources'/name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == inputs['files']['tests/security/fixtures/'+name]
    assert raw == (root/'tv/src/androidTest/assets'/name).read_bytes()
for path in [home/'src/test/resources/feed.json',root/'tv/src/androidTest/assets/feed.json']:
    assert json.loads(path.read_text()) == value['feed_response_example']
assert not (root/'tv/src/main/assets').exists()
home_build = (home/'build.gradle.kts').read_text()
assert re.findall(r'project\(\s*"([^"]+)"\s*\)', home_build) == [':playback-core']
# The one shared module contains pure playback state only. Keep the anonymous
# Home client independent of protected/fixture clients and their transports.
playback = root/'playback-core'
assert 'project(' not in (playback/'build.gradle.kts').read_text()
for path in (playback/'src/main').rglob('*.kt'):
    assert not re.search(r'\bimport\s+(?:android\.|okhttp3\.|java\.net\.|dev\.photohouse\.(?:connected|home|fixture)\.)', path.read_text()), path
print('PASS independent home-feed pin, exact contract and synthetic fixtures; protected phone pin unchanged')
