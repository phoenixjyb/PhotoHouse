"""Real isolated media-child regression against an immutable source tree."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def test_actual_hash_child_keeps_source_tree_immutable():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        scripts = root / 'workers' / 'scripts'
        scripts.mkdir(parents=True)
        for name in ('run_approved_cpu_worker.py', 'home_media_worker.py',
                     'home_preparation_resources.py', 'home_memory_envelope.py'):
            shutil.copyfile(ROOT / 'scripts' / name, scripts / name)
        before = {p.relative_to(scripts).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in scripts.rglob('*') if p.is_file()}
        source = root / 'generated.bin'
        source.write_bytes(b'generated hash-only fixture, no personal media')
        derived = root / 'derived'
        derived.mkdir()
        program = '''import hashlib,json,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import run_approved_cpu_worker as worker
# Only free-RAM/child-RSS observations are synthetic. The real child, hashing and
# child resource/timeout supervision execute against the generated fixture.
worker.observe_memory=lambda *_:(16*1024**3,512*1024)
source=Path(sys.argv[2]);derived=Path(sys.argv[3])
worker.sha_and_verify(source,source.stat().st_size,
 hashlib.sha256(source.read_bytes()).hexdigest(),derived,derived/'stop',time.monotonic()+30)
print(json.dumps({'hash_verified':True}))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', program,
                                 str(scripts), str(source), str(derived)],
                                capture_output=True, text=True, timeout=40)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {'hash_verified': True}
        after = {p.relative_to(scripts).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in scripts.rglob('*') if p.is_file()}
        assert after == before, 'Real child must not add bytecode to a sealed source payload'
