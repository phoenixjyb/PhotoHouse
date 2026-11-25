"""Real Git checkout regression for byte-bound Python source on Windows."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    "server/backend/app/access/search_policy.py",
    "server/backend/app/access/search_policy_binding.py",
    "server/scripts/semantic_siglip.py",
    "server/scripts/_semantic_siglip_encoding.py",
    "server/backend/app/access/search_exclusions.py",
)


class PythonCheckoutIdentityTests(unittest.TestCase):
    def test_autocrlf_checkout_preserves_bound_bytes_and_runtime_still_refuses_drift(self):
        # Use real checkout conversion, not a mocked digest or normalized reader.
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_ATTR_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
        expected = {name: (ROOT / name).read_bytes() for name in SOURCES}
        for data in expected.values():
            self.assertNotIn(b"\r\n", data)
        with tempfile.TemporaryDirectory() as selected:
            base = Path(selected).resolve()

            def git(where, *args):
                return subprocess.run(["git", "-C", str(where), *args], env=env,
                                      check=True, capture_output=True)

            for attributes in (False, True):
                with self.subTest(attributes=attributes):
                    seed, checkout = base / f"seed-{attributes}", base / f"checkout-{attributes}"
                    seed.mkdir()
                    git(seed, "init", "-q")
                    git(seed, "config", "core.autocrlf", "false")
                    git(seed, "config", "core.attributesFile", os.devnull)
                    for name, data in expected.items():
                        target = seed / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                    if attributes:
                        (seed / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
                    git(seed, "add", ".")
                    git(seed, "-c", "user.name=Generated fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "-qm", "Generated source")
                    git(base, "clone", "-q", "--no-hardlinks", "-c", "core.autocrlf=true",
                        "-c", "core.eol=crlf", str(seed), str(checkout))
                    for name, data in expected.items():
                        actual = (checkout / name).read_bytes()
                        self.assertEqual(actual, data if attributes else data.replace(b"\n", b"\r\n"))

                    verifier = checkout / SOURCES[1]
                    program = (
                        "import json,runpy,sys\n"
                        "try:\n"
                        " m=runpy.run_path(sys.argv[1])\n"
                        " print(json.dumps(m['capture_current_query_policy_binding']()))\n"
                        "except RuntimeError as e:\n"
                        " print(type(e).__name__);sys.exit(3)\n"
                    )

                    def capture():
                        return subprocess.run([sys.executable, "-I", "-c", program, str(verifier)],
                                              cwd=checkout, env=env, capture_output=True, text=True)

                    result = capture()
                    if not attributes:
                        self.assertEqual(result.returncode, 3, result.stderr)
                        self.assertEqual(result.stdout.strip(), "QueryPolicyUnavailable")
                        continue
                    self.assertEqual(result.returncode, 0, result.stderr)
                    binding = json.loads(result.stdout)
                    self.assertEqual(binding["policy_source_sha256"], hashlib.sha256(expected[SOURCES[0]]).hexdigest())
                    self.assertEqual(binding["public_guard_source_sha256"], hashlib.sha256(expected[SOURCES[2]]).hexdigest())
                    self.assertEqual(binding["binding_verifier_source_sha256"], hashlib.sha256(expected[SOURCES[1]]).hexdigest())
                    # An on-disk rewrite still fails; runtime verification stays byte-exact.
                    (checkout / SOURCES[0]).write_bytes(expected[SOURCES[0]].replace(b"\n", b"\r\n"))
                    drifted = capture()
                    self.assertEqual(drifted.returncode, 3, drifted.stderr)
                    self.assertEqual(drifted.stdout.strip(), "QueryPolicyUnavailable")


if __name__ == "__main__":
    unittest.main()
