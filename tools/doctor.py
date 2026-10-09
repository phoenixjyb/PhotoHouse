#!/usr/bin/env python3
"""Report local PhotoHouse development prerequisites without changing the system."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = Path("config/requirements-dev.lock")
WEB_SUITES = (
    "server/tests/security/test_assistant_pending_recovery_browser.cjs",
    "server/tests/security/test_memory_book_editorial_browser.cjs",
    "server/tests/security/test_memory_book_editorial_reader_browser.cjs",
    "server/tests/security/test_memory_community_browser.cjs",
)
MAX_LOCK_BYTES = 1024 * 1024
MAX_PROBE_SECONDS = 3
MAX_PROBE_OUTPUT = 4096
_PIN = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)"
    r"(?:\s*;\s*(.+))?\Z"
)
_JAVA_VERSION = re.compile(r'(?:version\s+["\']?|openjdk\s+)(\d+)(?:\.(\d+))?', re.I)
_NODE_VERSION = re.compile(r"\bv(\d+\.\d+\.\d+)\b")
_GRADLE_VERSION = re.compile(r"gradle-([0-9]+(?:\.[0-9]+)+)-(?:bin|all)\.zip\Z")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_PLAYWRIGHT_RESOLVE = (
    "try { const fs=require('fs'), path=require('path'); "
    "const entry=require.resolve(process.env.PH_DOCTOR_MODULE,{paths:[process.cwd()]}); "
    "const supported=new Set(['playwright-core','playwright']); "
    "let dir=path.dirname(entry), pkg=null; "
    "for(let i=0;i<8;i++){const file=path.join(dir,'package.json'); "
    "if(fs.existsSync(file)){try{const candidate=JSON.parse(fs.readFileSync(file,'utf8')); "
    "if(supported.has(candidate.name)){pkg=candidate;break;}}catch(_){}} "
    "const parent=path.dirname(dir); if(parent===dir) break; dir=parent;} "
    "process.stdout.write(JSON.stringify({resolved:true,nodeEngine:pkg&&pkg.engines&&pkg.engines.node||null})); } "
    "catch (_) { process.stdout.write(JSON.stringify({resolved:false})); }"
)


class LockError(ValueError):
    """The checked-in CPU lock is unreadable or outside the supported format."""


def _status(status: str, detail: str, **fields: object) -> dict[str, object]:
    result: dict[str, object] = {"status": status, "detail": detail}
    result.update(fields)
    return result


def _combine(*checks: dict[str, object]) -> str:
    statuses = {str(item.get("status")) for item in checks}
    if "missing" in statuses:
        return "missing"
    if "unverified" in statuses:
        return "unverified"
    return "available"


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _marker_applies(marker: str, platform: str) -> bool:
    match = re.fullmatch(r"\s*sys_platform\s*==\s*['\"]([A-Za-z0-9_]+)['\"]\s*", marker)
    if not match:
        raise LockError("unsupported_marker")
    return match.group(1) == platform


def parse_cpu_lock(lock_path: Path, platform: str) -> tuple[dict[str, str], int]:
    """Read local pinned requirements and includes; never resolve or contact an index."""
    config_root = lock_path.parent.resolve()
    pins: dict[str, str] = {}
    skipped_conditional = 0
    visited: set[Path] = set()

    def parse(path: Path) -> None:
        nonlocal skipped_conditional
        resolved = path.resolve()
        if not resolved.is_relative_to(config_root) or resolved in visited:
            raise LockError("unsafe_or_cyclic_include")
        visited.add(resolved)
        try:
            data = resolved.read_bytes()
        except OSError:
            raise LockError("lock_unavailable") from None
        if len(data) > MAX_LOCK_BYTES:
            raise LockError("lock_too_large")
        try:
            lines = data.decode("utf-8", "strict").splitlines()
        except UnicodeDecodeError:
            raise LockError("lock_encoding_invalid") from None

        for line in lines:
            item = line.strip()
            if not item or item.startswith("#") or item.startswith("--hash="):
                continue
            if item.endswith("\\"):
                item = item[:-1].rstrip()
            include = re.fullmatch(r"-r\s+([^\s]+)", item)
            if include:
                parse(resolved.parent / include.group(1))
                continue
            match = _PIN.fullmatch(item)
            if not match:
                raise LockError("unsupported_lock_line")
            name, version, marker = match.groups()
            if marker and not _marker_applies(marker, platform):
                skipped_conditional += 1
                continue
            canonical = _canonical_name(name)
            old = pins.get(canonical)
            if old is not None and old != version:
                raise LockError("conflicting_pins")
            pins[canonical] = version

    parse(lock_path)
    if not pins:
        raise LockError("empty_lock")
    return pins, skipped_conditional


def _package_checks(
    root: Path,
    platform: str,
    version_lookup: Callable[[str], str],
) -> dict[str, object]:
    try:
        pins, skipped = parse_cpu_lock(root / LOCK_PATH, platform)
    except LockError as exc:
        return _status("unverified", "cpu_lock_" + str(exc), packages=[])

    packages = []
    for canonical, required in sorted(pins.items()):
        display_name = canonical
        try:
            installed = version_lookup(display_name)
        except importlib.metadata.PackageNotFoundError:
            packages.append({
                "name": display_name,
                "required_version": required,
                "installed_version": None,
                "status": "missing",
            })
        except Exception:
            packages.append({
                "name": display_name,
                "required_version": required,
                "installed_version": None,
                "status": "unverified",
            })
        else:
            exact = installed == required
            packages.append({
                "name": display_name,
                "required_version": required,
                "installed_version": installed,
                "status": "available" if exact else "missing",
            })
    status = _combine(*packages)
    matching = sum(item["status"] == "available" for item in packages)
    return _status(
        status,
        "pinned_package_versions_checked",
        package_count=len(packages),
        matching_count=matching,
        conditional_package_count=skipped,
        packages=packages,
    )


def _python_check(version_info: object) -> dict[str, object]:
    major = getattr(version_info, "major", None)
    minor = getattr(version_info, "minor", None)
    micro = getattr(version_info, "micro", None)
    observed = ".".join(str(part) for part in (major, minor, micro) if part is not None)
    exact = (major, minor) == (3, 12)
    return _status(
        "available" if exact else "missing",
        "python_312_required",
        expected="3.12",
        observed=observed or "unknown",
    )


def _run_probe(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    popen_factory: Callable[..., object] = subprocess.Popen,
) -> dict[str, object]:
    """Run a fixed, local version/resolution probe with a short timeout."""
    try:
        process = popen_factory(
            argv,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except (FileNotFoundError, PermissionError, OSError):
        return _status("unverified", "probe_failed", output="")

    captured = bytearray()
    truncated = False

    def drain_output() -> None:
        stream = getattr(process, "stdout", None)
        if stream is None:
            return
        while True:
            try:
                chunk = stream.read(1024)
            except (OSError, ValueError):
                return
            if not chunk:
                return
            nonlocal truncated
            remaining = MAX_PROBE_OUTPUT - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True

    reader = threading.Thread(target=drain_output, daemon=True)
    reader.start()
    try:
        returncode = process.wait(timeout=MAX_PROBE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=1)
        except (subprocess.TimeoutExpired, OSError):
            pass
        reader.join(timeout=0.1)
        _close_probe_stream(process)
        return _status("unverified", "probe_timed_out", output="")
    except OSError:
        process.kill()
        reader.join(timeout=0.1)
        _close_probe_stream(process)
        return _status("unverified", "probe_failed", output="")
    reader.join(timeout=0.1)
    _close_probe_stream(process)
    output = bytes(captured).decode("utf-8", errors="replace")
    if returncode != 0:
        return _status("unverified", "probe_failed", output=output, truncated=truncated)
    return _status("available", "probe_passed", output=output, truncated=truncated)


def _close_probe_stream(process: object) -> None:
    stream = getattr(process, "stdout", None)
    if stream is not None:
        try:
            stream.close()
        except OSError:
            pass


def _probe_environment(env: dict[str, str], *, include_node_path: bool = False) -> dict[str, str]:
    keys = ["PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "JAVA_HOME"]
    if include_node_path:
        keys.append("NODE_PATH")
    return {key: env[key] for key in keys if key in env}


def _find_tool(name: str, env: dict[str, str], which: Callable[[str], str | None], platform: str) -> str | None:
    if name == "java" and env.get("JAVA_HOME"):
        java_name = "java.exe" if platform == "win32" else "java"
        candidate = Path(env["JAVA_HOME"]).expanduser() / "bin" / java_name
        return str(candidate) if candidate.is_file() else None
    return which(name)


def _java_check(
    env: dict[str, str],
    which: Callable[[str], str | None],
    probe: Callable[..., dict[str, object]],
    platform: str,
) -> dict[str, object]:
    java = _find_tool("java", env, which, platform)
    if not java:
        return _status("missing", "jdk_17_not_found", expected_major="17")
    result = probe([java, "-version"], env=_probe_environment(env))
    if result["status"] != "available":
        return _status("unverified", str(result["detail"]), expected_major="17")
    if result.get("truncated"):
        return _status("unverified", "jdk_probe_output_truncated", expected_major="17")
    output = str(result.get("output", ""))
    match = _JAVA_VERSION.search(output)
    if not match:
        return _status("unverified", "jdk_version_unreadable", expected_major="17")
    major = match.group(1)
    return _status(
        "available" if major == "17" else "missing",
        "jdk_17_detected" if major == "17" else "jdk_version_mismatch",
        expected_major="17",
        observed_major=major,
    )


def _node_check(
    env: dict[str, str],
    which: Callable[[str], str | None],
    probe: Callable[..., dict[str, object]],
) -> tuple[dict[str, object], str | None]:
    node = which("node")
    if not node:
        return _status("missing", "node_not_found"), None
    result = probe([node, "--version"], env=_probe_environment(env, include_node_path=True))
    if result["status"] != "available":
        return _status("unverified", str(result["detail"])), node
    if result.get("truncated"):
        return _status("unverified", "node_probe_output_truncated"), node
    match = _NODE_VERSION.search(str(result.get("output", "")))
    if not match:
        return _status("unverified", "node_version_unreadable"), node
    return _status("available", "node_detected", version=match.group(1)), node


def _sdk_location(env: dict[str, str], platform: str, home: Path) -> tuple[Path | None, str | None]:
    android_home = env.get("ANDROID_HOME")
    sdk_root = env.get("ANDROID_SDK_ROOT")
    if android_home and sdk_root:
        if Path(android_home).expanduser() != Path(sdk_root).expanduser():
            return None, "conflicting_sdk_environment"
    configured = android_home or sdk_root
    if configured:
        return Path(configured).expanduser(), None
    if platform == "win32" and env.get("LOCALAPPDATA"):
        return Path(env["LOCALAPPDATA"]) / "Android" / "Sdk", None
    if platform == "darwin":
        return home / "Library" / "Android" / "sdk", None
    return home / "Android" / "Sdk", None


def _sdk_check(env: dict[str, str], platform: str, home: Path) -> dict[str, object]:
    sdk, error = _sdk_location(env, platform, home)
    if error:
        return _status("unverified", error, platform_34="unverified", build_tools_34="unverified",
                       build_tools_components={})
    assert sdk is not None
    platform_file = sdk / "platforms" / "android-34" / "android.jar"
    build_tools = sdk / "build-tools" / "34.0.0"
    platform_status = "available" if platform_file.is_file() else "missing"
    names = {
        "aapt2": "aapt2.exe" if platform == "win32" else "aapt2",
        "d8": "d8.bat" if platform == "win32" else "d8",
        "zipalign": "zipalign.exe" if platform == "win32" else "zipalign",
        "apksigner": "lib/apksigner.jar",
    }
    components = {
        key: "available" if (build_tools / relative).is_file() else "missing"
        for key, relative in names.items()
    } if build_tools.is_dir() else {key: "missing" for key in names}
    build_status = _combine(*({"status": status} for status in components.values()))
    return _status(
        _combine({"status": platform_status}, {"status": build_status}),
        "android_sdk_components_checked",
        platform_34=platform_status,
        build_tools_34=build_status,
        build_tools_components=components,
    )


def _wrapper_check(root: Path, platform: str) -> tuple[dict[str, object], str | None]:
    android = root / "clients/android/android"
    wrapper = "gradlew.bat" if platform == "win32" else "gradlew"
    properties = android / "gradle/wrapper/gradle-wrapper.properties"
    jar = android / "gradle/wrapper/gradle-wrapper.jar"
    if not (android / wrapper).is_file() or not jar.is_file():
        return _status("missing", "platform_wrapper_missing", expected_wrapper=wrapper), None
    try:
        text = properties.read_text(encoding="utf-8")
    except OSError:
        return _status("unverified", "wrapper_properties_unavailable", expected_wrapper=wrapper), None
    match = re.search(r"distributionUrl=.*?/gradle-([0-9]+(?:\.[0-9]+)+)-(?:bin|all)\.zip", text)
    if not match:
        return _status("unverified", "wrapper_version_unreadable", expected_wrapper=wrapper), None
    digest = re.search(r"^\s*distributionSha256Sum\s*=\s*([^\s#]+)\s*$", text, re.M)
    if not digest or not _SHA256.fullmatch(digest.group(1)):
        return _status("unverified", "wrapper_distribution_sha256_unreadable",
                       expected_wrapper=wrapper), None
    version = match.group(1)
    return _status(
        "available",
        "pinned_wrapper_detected",
        expected_wrapper=wrapper,
        gradle_version=version,
    ), version


def _gradle_cache_check(env: dict[str, str], home: Path, platform: str, version: str | None) -> dict[str, object]:
    if not version:
        return _status("unverified", "wrapper_version_unavailable", optional=True)
    gradle_home = Path(env["GRADLE_USER_HOME"]).expanduser() if env.get("GRADLE_USER_HOME") else home / ".gradle"
    cache = gradle_home / "wrapper" / "dists" / f"gradle-{version}-bin"
    if not cache.is_dir():
        return _status("missing", "warm_wrapper_cache_not_found", optional=True, gradle_version=version)
    executable = "gradle.bat" if platform == "win32" else "gradle"
    try:
        candidates = list(cache.iterdir())[:64]
    except OSError:
        return _status("unverified", "wrapper_cache_unreadable", optional=True, gradle_version=version)
    for candidate in candidates:
        if (candidate / f"gradle-{version}" / "bin" / executable).is_file():
            return _status("available", "warm_wrapper_cache_found", optional=True, gradle_version=version)
    return _status("unverified", "wrapper_cache_distribution_unverified", optional=True, gradle_version=version)


def _playwright_check(
    server_root: Path,
    env: dict[str, str],
    node: str | None,
    node_status: dict[str, object],
    probe: Callable[..., dict[str, object]],
) -> dict[str, object]:
    module = env.get("PLAYWRIGHT_MODULE")
    module_path = env.get("PLAYWRIGHT_MODULE_PATH")
    if module and module_path and module != module_path:
        return _status("unverified", "conflicting_playwright_selection")
    selection = module or module_path or "playwright-core"
    if len(selection) > 512:
        return _status("unverified", "playwright_selection_too_long")
    if not node or node_status["status"] != "available":
        return _status("missing", "node_required_for_playwright_resolution")
    probe_env = _probe_environment(env, include_node_path=True)
    probe_env["PH_DOCTOR_MODULE"] = selection
    result = probe([node, "-e", _PLAYWRIGHT_RESOLVE], env=probe_env, cwd=server_root)
    if result["status"] != "available":
        return _status("unverified", "playwright_resolution_unverified")
    if result.get("truncated"):
        return _status("unverified", "playwright_probe_output_truncated")
    try:
        resolution = json.loads(str(result.get("output", "")))
    except (TypeError, ValueError):
        return _status("unverified", "playwright_resolution_unreadable")
    if not isinstance(resolution, dict):
        return _status("unverified", "playwright_resolution_unreadable")
    if resolution.get("resolved") is not True:
        return _status("missing", "playwright_module_not_resolvable")
    engine = resolution.get("nodeEngine")
    if not isinstance(engine, str):
        return _status("unverified", "playwright_node_engine_unavailable")
    minimum = re.fullmatch(r"\s*>=\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?\s*", engine)
    if not minimum:
        return _status("unverified", "playwright_node_engine_unsupported")
    installed = node_status.get("version")
    node_version = _NODE_VERSION.fullmatch("v" + str(installed or ""))
    if not node_version:
        return _status("unverified", "node_version_unavailable")
    required_version = tuple(int(part or 0) for part in minimum.groups())
    observed_version = tuple(int(part) for part in node_version.group(1).split("."))
    if observed_version < required_version:
        return _status("missing", "node_below_playwright_minimum",
                       required_node_version=".".join(map(str, required_version)),
                       observed_node_version=".".join(map(str, observed_version)))
    return _status("available", "playwright_module_and_node_engine_match",
                   required_node_version=".".join(map(str, required_version)),
                   observed_node_version=".".join(map(str, observed_version)))


def _chromium_check(env: dict[str, str], platform: str, home: Path) -> dict[str, object]:
    explicit = env.get("PH_BROWSER_EXECUTABLE")
    if explicit:
        return _status("available" if Path(explicit).expanduser().is_file() else "missing",
                       "browser_executable_detected" if Path(explicit).expanduser().is_file()
                       else "configured_browser_executable_missing", optional=True)
    if platform == "win32":
        local = env.get("LOCALAPPDATA")
        roots = [Path(local) / "ms-playwright"] if local else [home / "AppData/Local/ms-playwright"]
    elif platform == "darwin":
        roots = [home / "Library/Caches/ms-playwright"]
    else:
        roots = [home / ".cache/ms-playwright"]
    binaries = (
        "chrome-linux/chrome",
        "chrome-linux64/chrome",
        "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
        "chrome-win/chrome.exe",
        "chrome-win64/chrome.exe",
        "chrome-linux/headless_shell",
        "chrome-linux64/headless_shell",
        "chrome-mac/headless_shell",
        "chrome-mac-arm64/headless_shell",
    )
    unreadable = False
    for cache_root in roots:
        if not cache_root.is_dir():
            continue
        try:
            entries = list(cache_root.iterdir())[:128]
        except OSError:
            unreadable = True
            continue
        for entry in entries:
            if entry.name.startswith(("chromium-", "chromium_headless_shell-")):
                if any((entry / binary).is_file() for binary in binaries):
                    return _status("available", "cached_chromium_detected", optional=True)
    if unreadable:
        return _status("unverified", "browser_cache_unreadable", optional=True)
    return _status("missing", "cached_chromium_not_found", optional=True)


def _suite_check(root: Path) -> dict[str, object]:
    missing = [path for path in WEB_SUITES if not (root / path).is_file()]
    return _status("missing" if missing else "available",
                   "web_suite_files_missing" if missing else "web_suite_files_present",
                   missing_count=len(missing))


def build_report(
    root: Path = ROOT,
    *,
    env: dict[str, str] | None = None,
    platform: str = sys.platform,
    version_info: object = sys.version_info,
    version_lookup: Callable[[str], str] = importlib.metadata.version,
    which: Callable[[str], str | None] = shutil.which,
    probe: Callable[..., dict[str, object]] | None = None,
    home: Path | None = None,
) -> dict[str, object]:
    """Inspect local paths and metadata; never expose absolute paths or environment values."""
    env = dict(os.environ if env is None else env)
    home = Path.home() if home is None else Path(home)
    probe = probe or (lambda argv, **kwargs: _run_probe(argv, **kwargs))
    python = _python_check(version_info)
    packages = _package_checks(root, platform, version_lookup)
    cpu = _combine(python, packages)

    node_check, node = _node_check(env, which, probe)
    java_check = _java_check(env, which, probe, platform)
    sdk_check = _sdk_check(env, platform, home)
    wrapper_check, gradle_version = _wrapper_check(root, platform)
    gradle_cache = _gradle_cache_check(env, home, platform, gradle_version)
    playwright = _playwright_check(root / "server/tests/security", env, node, node_check, probe)
    chromium = _chromium_check(env, platform, home)
    web_suites = _suite_check(root)
    android = _combine(python, java_check, sdk_check, wrapper_check)
    web = _combine(python, packages, node_check, playwright, chromium, web_suites)
    all_status = _combine({"status": cpu}, {"status": android})
    profiles = [
        {"name": "api", "requirement": "required CPU profile", "status": cpu},
        {"name": "memory", "requirement": "focused CPU profile", "status": cpu},
        {"name": "android", "requirement": "phone/TV profile", "status": android},
        {"name": "web", "requirement": "optional browser profile", "status": web},
        {"name": "all", "requirement": "API plus Android; excludes optional Web", "status": all_status},
    ]
    return {
        "tool": "PhotoHouse development doctor",
        "read_only": True,
        "meaning": "prerequisite availability only; no tests or builds were run",
        "profiles": profiles,
        "checks": {
            "python312": python,
            "cpu_dependencies": packages,
            "node": node_check,
            "jdk17": java_check,
            "android_sdk34": sdk_check,
            "gradle_wrapper": wrapper_check,
            "gradle_wrapper_cache": gradle_cache,
            "playwright_module": playwright,
            "chromium_cache": chromium,
            "web_suite_files": web_suites,
        },
    }


def format_text(report: dict[str, object]) -> str:
    checks = report["checks"]
    profiles = report["profiles"]
    assert isinstance(checks, dict) and isinstance(profiles, list)
    packages = checks["cpu_dependencies"]
    assert isinstance(packages, dict)
    lines = [
        "PhotoHouse development environment (read-only prerequisite check; no tests/builds run)",
        "Profiles:",
    ]
    for profile in profiles:
        assert isinstance(profile, dict)
        lines.append(f"  {profile['name']}: {profile['status']} ({profile['requirement']})")
    lines.append("Components:")
    for key in ("python312", "cpu_dependencies", "node", "jdk17", "android_sdk34",
                "gradle_wrapper", "gradle_wrapper_cache", "playwright_module",
                "chromium_cache", "web_suite_files"):
        item = checks[key]
        assert isinstance(item, dict)
        summary = str(item["detail"])
        if key == "cpu_dependencies" and "package_count" in item:
            summary = f"{item['matching_count']}/{item['package_count']} pinned packages match"
        if key == "cpu_dependencies" and item.get("packages"):
            bad = [p["name"] for p in item["packages"] if p["status"] != "available"]
            if bad:
                summary += "; unavailable or mismatched: " + ", ".join(bad[:12])
        if key == "android_sdk34" and item.get("build_tools_components"):
            missing = [name for name, status in item["build_tools_components"].items()
                       if status != "available"]
            if missing:
                summary += "; missing build-tools: " + ", ".join(missing)
        if key == "playwright_module" and item.get("required_node_version"):
            summary += f"; Node >= {item['required_node_version']} required by module metadata"
        version = item.get("observed", item.get("version", item.get("observed_major")))
        suffix = f", version {version}" if version else ""
        lines.append(f"  {key}: {item['status']} — {summary}{suffix}")
    lines.append("Available means prerequisites were detected; it does not mean a profile passed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="write the report as JSON")
    args = parser.parse_args(argv)
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
