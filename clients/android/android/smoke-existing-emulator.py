#!/usr/bin/env python3
"""Manual-style adb smoke of the installed fixture APK; never selects a physical device."""
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

serial = sys.argv[1] if len(sys.argv) > 1 else ''
assert re.fullmatch(r'emulator-\d+', serial), 'Pass an explicit running emulator serial'
root = Path(__file__).resolve().parent.parent
adb = Path(os.environ['ANDROID_HOME']) / 'platform-tools/adb'
package = 'dev.photohouse.fixture'
out = root / 'docs/evidence/android/manual'
out.mkdir(parents=True, exist_ok=True)

def run(*args):
    return subprocess.check_output([str(adb), '-s', serial, *args], timeout=30)

assert run('shell', 'getprop', 'ro.kernel.qemu').strip() == b'1'

def tree(name):
    for attempt in range(3):
        data = run('exec-out', 'uiautomator', 'dump', '/dev/tty').decode()
        if '<?xml' in data and '</hierarchy>' in data:
            break
        time.sleep(1)
    else:
        raise AssertionError('UI automator did not produce an idle hierarchy after three attempts')
    xml = data[data.index('<?xml'):data.index('</hierarchy>') + len('</hierarchy>')]
    (out / f'{name}.xml').write_text(xml)
    return ET.fromstring(xml)

def tap_text(name, label):
    ui = tree(name)
    candidates = [n for n in ui.iter('node') if n.get('text') == label]
    assert len(candidates) == 1, f'Expected visible control: {label}'
    bounds = list(map(int, re.findall(r'\d+', candidates[0].get('bounds'))))
    x1, y1, x2, y2 = bounds
    run('shell', 'input', 'tap', str((x1 + x2)//2), str((y1 + y2)//2))
    time.sleep(1)

def launch():
    run('shell', 'am', 'start', '-n', f'{package}/.MainActivity')
    time.sleep(1)

run('shell', 'am', 'force-stop', package)
launch()
cold = tree('cold-start')
assert any(n.get('text') == 'Sign in to demo' for n in cold.iter('node'))
assert not any(n.get('text') == 'family-a' for n in cold.iter('node'))
tap_text('signin-control', 'Sign in to demo')
tap_text('library-control', 'Open library')
gallery = tree('gallery')
assert any('Synthetic photo' in n.get('content-desc', '') for n in gallery.iter('node'))
(out / 'secure-foreground.png').write_bytes(run('exec-out', 'screencap', '-p'))
run('shell', 'input', 'keyevent', 'KEYCODE_HOME')
time.sleep(1)
# Capture the system task preview only when all recent tasks are this fixture app.
recents = run('shell', 'dumpsys', 'activity', 'recents').decode()
activities = [a.strip('{}') for a in re.findall(r'realActivity=([^\s]+)', recents)]
recents_checked = bool(activities) and all(a.startswith((package + '/', package + '.test/')) for a in activities)
if recents_checked:
    run('shell', 'input', 'keyevent', 'KEYCODE_APP_SWITCH')
    time.sleep(1)
    (out / 'secure-recents.png').write_bytes(run('exec-out', 'screencap', '-p'))
    run('shell', 'input', 'keyevent', 'KEYCODE_HOME')
launch()
foreground = tree('foreground-revalidated')
assert any(n.get('text') == 'Your libraries' for n in foreground.iter('node'))
assert not any('Synthetic photo' in n.get('content-desc', '') for n in foreground.iter('node'))
tap_text('reopen-library', 'Open library')
run('shell', 'am', 'force-stop', package)
launch()
restarted = tree('process-restarted')
assert any(n.get('text') == 'Sign in to demo' for n in restarted.iter('node'))
assert not any(n.get('text') == 'family-a' for n in restarted.iter('node'))
result = 'PASS cold start, UI-tree-driven login/gallery, foreground revalidation and process-death sign-out.\n'
result += 'System foreground secure-window screenshot captured; inspect image separately.\n'
result += ('System recents screenshot captured; inspect image separately.\n' if recents_checked else
           'Recents visual gate skipped: other task identities present; no unrelated snapshots captured.\n')
(out / 'result.txt').write_text(result)
print(result)
