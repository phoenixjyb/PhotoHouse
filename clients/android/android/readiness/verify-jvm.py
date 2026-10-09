#!/usr/bin/env python3
"""Compile selected JVM suites from source using cached artifacts; no Gradle/listeners.

Requires the project's existing JDK 17 and exact cached Maven artifact versions.
A JDK 17 SecurityManager denies network connects, listens and accepts in compiler
and test processes. This is a bounded test guard, not an Android security mechanism.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    evidence.relative_to(ROOT/'docs/evidence/android')
    evidence.mkdir(parents=True, exist_ok=True)
    java = args.java_home/'bin/java'
    version = subprocess.run([java, '-version'], capture_output=True, text=True, check=True).stderr
    assert 'version "17.' in version, 'Existing JDK 17 required'
    used = {}
    def jar(group, name, version):
        matches = list((args.cache/group/name/version).glob(f'*/{name}-{version}.jar'))
        assert len(matches) == 1, f'Missing or ambiguous cached artifact: {group}:{name}:{version}'
        path = matches[0].resolve()
        used[f'{group}:{name}:{version}'] = hashlib.sha256(path.read_bytes()).hexdigest()
        return str(path)
    kotlin = lambda name: jar('org.jetbrains.kotlin', name, '1.9.24')
    stdlib = kotlin('kotlin-stdlib')
    compiler = [kotlin('kotlin-compiler-embeddable'), stdlib, kotlin('kotlin-script-runtime'),
        jar('org.jetbrains.kotlin','kotlin-reflect','1.6.10'),
        jar('org.jetbrains.intellij.deps','trove4j','1.0.20200330'), jar('org.jetbrains','annotations','13.0')]
    plugin = kotlin('kotlin-serialization-compiler-plugin-embeddable')
    deps = [stdlib, jar('org.jetbrains','annotations','23.0.0'),
        jar('org.jetbrains.kotlinx','kotlinx-serialization-json-jvm','1.6.3'),
        jar('org.jetbrains.kotlinx','kotlinx-serialization-core-jvm','1.6.3'),
        jar('org.jetbrains.kotlinx','kotlinx-coroutines-core-jvm','1.8.1'),
        jar('org.jetbrains.kotlinx','kotlinx-coroutines-test-jvm','1.8.1'),
        jar('com.squareup.okhttp3','okhttp','4.12.0'), jar('com.squareup.okio','okio-jvm','3.6.0'),
        jar('junit','junit','4.13.2'), jar('org.hamcrest','hamcrest-core','1.3')]
    sources = []
    for module in ['protocol','core','live-core']:
        sources += sorted((ROOT/f'android/{module}/src/main/kotlin').rglob('*.kt'))
    tests = [ROOT/'android/core/src/test/kotlin/dev/photohouse/fixture/core/FixtureTest.kt']
    tests += [ROOT/f'android/live-core/src/test/kotlin/dev/photohouse/connected/core/{name}.kt'
        for name in ['ConnectedStoreTest','VideoReaderTest','ReadinessAdapterTest']]
    suites = ['dev.photohouse.fixture.core.FixtureTest'] + [f'dev.photohouse.connected.core.{name}'
        for name in ['ConnectedStoreTest','VideoReaderTest','ReadinessAdapterTest']]
    with tempfile.TemporaryDirectory(prefix='photohouse-readiness-') as temp:
        out = Path(temp); classes=out/'classes'; classes.mkdir()
        subprocess.run([args.java_home/'bin/javac','-d',str(classes),str(ROOT/'android/readiness/NoNetwork.java')],check=True)
        guard = ['-Djava.security.manager=NoNetwork']
        compile_result = subprocess.run([java,*guard,'-cp',os.pathsep.join([str(classes),*compiler]),
            'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17',
            '-Xplugin='+plugin,'-classpath',os.pathsep.join(deps),'-d',str(classes),*map(str,sources+tests)],capture_output=True,text=True)
        assert compile_result.returncode == 0, compile_result.stderr
        run = subprocess.run([java,*guard,'-cp',os.pathsep.join([str(classes),str(ROOT/'contracts/v1'),*deps]),
            'org.junit.runner.JUnitCore',*suites],capture_output=True,text=True)
        # Tests use only synthetic data; retain diagnostics without machine paths.
        log = (run.stdout+run.stderr).replace(str(ROOT),'<worktree>')
        (evidence/'jvm.log').write_text(log)
        print(log)
        assert run.returncode == 0, 'Readiness JVM checks failed'
        result = {'java':version.splitlines()[0], 'compiler':'Kotlin 1.9.24 embeddable, direct CLI',
            'network_guard':'JDK 17 SecurityManager denies connect/listen/accept',
            'suites':suites,'cached_artifact_sha256':used,
            'compiled_source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+tests},
            'apk_built':False,'device_run':False,'real_backend_run':False}
        (evidence/'jvm.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__ == '__main__': main()
