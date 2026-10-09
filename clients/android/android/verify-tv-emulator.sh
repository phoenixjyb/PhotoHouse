#!/usr/bin/env bash
# Synthetic component tests only, on an explicitly selected existing emulator.
set -euo pipefail
cd "$(dirname "$0")/.."
serial="${1:?Pass emulator-SERIAL}"
scale="${2:-1.0}"
evidence="${3:-docs/evidence/android/tv}"
suite="${4:-all}"
[[ "$suite" == all || "$suite" == catalog || "$suite" == discovery ]] || exit 2
[[ "$serial" == emulator-* && ( "$scale" == 1.0 || "$scale" == 2.0 ) ]] || exit 2
adb="${ANDROID_HOME:?}/platform-tools/adb"
[[ "$("$adb" -s "$serial" shell getprop ro.kernel.qemu | tr -d '\r')" == 1 ]] || exit 2
python3 - <<'PY'
from pathlib import Path
p=Path('android/tv/build/generated/source/buildConfig/debug/dev/photohouse/tv/BuildConfig.java')
assert 'PHOTOHOUSE_ORIGIN = "";' in p.read_text(), 'Use an unconfigured synthetic-test build'
PY
"$adb" -s "$serial" shell input keyevent KEYCODE_WAKEUP
"$adb" -s "$serial" shell wm dismiss-keyguard
previous="$("$adb" -s "$serial" shell settings get system font_scale | tr -d '\r')"
trap '"$adb" -s "$serial" shell settings put system font_scale "$previous" >/dev/null' EXIT
"$adb" -s "$serial" shell settings put system font_scale "$scale"
"$adb" -s "$serial" install -r -t android/tv/build/outputs/apk/debug/tv-debug.apk
"$adb" -s "$serial" install -r -t android/tv/build/outputs/apk/androidTest/debug/tv-debug-androidTest.apk
mkdir -p "$evidence/screenshots/$scale"
instrument=(-w -r -e notAnnotation dev.photohouse.tv.LiveCatalogOnly)
suffix=""
names=(setup connection-needed grid-en grid-zh detail-en fullscreen covered display-caption denied empty photo-zoom video-paused video-error video-error-zh catalog-grid catalog-unavailable catalog-pages catalog-pages-zh discovery-home discovery-zh discovery-advanced discovery-dates discovery-unavailable discovery-results discovery-empty discovery-error)
if [[ "$suite" == catalog ]]; then
    instrument+=(-e class dev.photohouse.tv.TvCatalogTest)
    suffix="-catalog"
    names=(catalog-grid catalog-unavailable catalog-pages catalog-pages-zh video-error video-error-zh)
fi
if [[ "$suite" == discovery ]]; then
    instrument+=(-e class dev.photohouse.tv.TvDiscoveryTest,dev.photohouse.tv.TvDiscoveryResultsTest)
    suffix="-discovery"
    names=(discovery-home discovery-zh discovery-advanced discovery-dates discovery-unavailable discovery-results discovery-empty discovery-error)
fi
"$adb" -s "$serial" shell am instrument "${instrument[@]}" dev.photohouse.tv.test/androidx.test.runner.AndroidJUnitRunner | tee "$evidence/instrumentation-$scale$suffix.log"
python3 - "$evidence/instrumentation-$scale$suffix.log" <<'PY'
import re,sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
declared=re.search(r'INSTRUMENTATION_STATUS: numtests=(\d+)',s)
completed=re.search(r'OK \((\d+) tests?\)',s)
assert declared and completed and int(declared.group(1)) == int(completed.group(1)) > 0 \
    and 'FAILURES!!!' not in s and 'INSTRUMENTATION_CODE: -1' in s, 'TV component tests failed'
print(f"Verified {completed.group(1)} TV component tests")
PY
for name in "${names[@]}"; do
    "$adb" -s "$serial" exec-out run-as dev.photohouse.tv cat "files/$name.png" > "$evidence/screenshots/$scale/$name.png"
    "$adb" -s "$serial" shell run-as dev.photohouse.tv rm "files/$name.png"
done
