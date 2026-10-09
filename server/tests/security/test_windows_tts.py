"""Bounded source tests for the Windows-local System.Speech bridge."""
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import httpx
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
import wave
from unittest.mock import patch
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

import serve_windows_tts as operator
from app.access import windows_tts as tts
from fastapi.testclient import TestClient


TOKEN = 'local-synthetic-token-' + 'x' * 32
SYNTHETIC_POWERSHELL = Path(tempfile.gettempdir()).resolve() / 'photohouse-synthetic-executable' / 'powershell.exe'


def wav_bytes(*, rate=16000, channels=1, width=2, seconds=0.1):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(b'\0' * int(rate * seconds) * channels * width)
    return output.getvalue()


def child_reply(audio):
    return json.dumps({'success': True,
        'audio_base64': base64.b64encode(audio).decode('ascii')}, separators=(',', ':')).encode()


class FakeProcess:
    def __init__(self, stdout, *, persistent=False):
        self.stdin = InputCapture()
        self.stdout = io.BytesIO(stdout)
        self.returncode = None if persistent else 0
        self.kills = 0
        self.waited = 0

    def poll(self):
        return self.returncode

    def kill(self):
        self.kills += 1
        self.returncode = -9

    def wait(self, timeout=None):
        self.waited += 1
        if self.returncode is None:
            raise TimeoutError()
        return self.returncode


class UnkillableProcess(FakeProcess):
    def kill(self):
        self.kills += 1

    def wait(self, timeout=None):
        self.waited += 1
        raise TimeoutError()


class BlockingPipe:
    def __init__(self):
        self.release = threading.Event()
        self.closed = False

    def read(self, _size):
        self.release.wait(5)
        return b''

    def close(self):
        self.closed = True


class InputCapture(io.BytesIO):
    def close(self):
        self.captured = self.getvalue()
        super().close()


class FakeSynthesis:
    def __init__(self, audio=None, *, entered=None, release=None):
        self.audio = audio or wav_bytes()
        self.entered, self.release = entered, release
        self.cancelled = False

    def synthesize(self, fields):
        if self.entered:
            self.entered.set()
            self.release.wait(3)
        return self.audio

    def cancel_active(self):
        self.cancelled = True
        if self.release:
            self.release.set()


class WindowsSpeechChildTests(unittest.TestCase):
    FIELDS = {'text': 'synthetic phrase', 'language': 'en',
              'voice_speed': '1.0', 'output_format': 'wav'}

    def test_windows_token_ancestor_guard_checks_stat_mode_and_reparse_flag(self):
        # lstat returns a stat_result-like value, not a Path with is_dir().
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0)
        regular = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_file_attributes=0)
        reparse = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0x400)
        self.assertTrue(tts._safe_windows_directory(directory))
        self.assertFalse(tts._safe_windows_directory(regular))
        self.assertFalse(tts._safe_windows_directory(reparse))

    def test_synthesis_sends_text_only_on_stdin_and_preserves_valid_wav(self):
        audio = wav_bytes()
        process = FakeProcess(child_reply(audio))
        calls = []

        def popen(args, **kwargs):
            calls.append((args, kwargs, process))
            return process

        child = tts.WindowsSystemSpeech(executable=SYNTHETIC_POWERSHELL, popen=popen)
        result = child.synthesize(self.FIELDS)
        self.assertEqual(result, audio)
        args, kwargs, proc = calls[0]
        self.assertEqual(args[0], str(SYNTHETIC_POWERSHELL))
        self.assertNotIn('synthetic phrase', ' '.join(args))
        self.assertNotIn(TOKEN, ' '.join(args))
        self.assertEqual(kwargs['shell'], False)
        request = json.loads(proc.stdin.captured.decode('utf-8'))
        self.assertEqual(request, {'operation': 'synthesize', **self.FIELDS})

    def test_failure_shape_oversized_stdout_and_bad_wav_fail_closed(self):
        for output, code in ((b'{"success":false,"error":"voice_unavailable"}', 1),
                             (b'{"success":true,"audio_base64":"!!!"}', 0),
                             (child_reply(b'not a wave'), 0),
                             (b'x' * (tts.MAX_CHILD_STDOUT + 2), 0)):
            proc = FakeProcess(output, persistent=len(output) > tts.MAX_CHILD_STDOUT)
            child = tts.WindowsSystemSpeech(executable=SYNTHETIC_POWERSHELL,
                popen=lambda *_a, _p=proc, **_kw: _p)
            if code:
                proc.returncode = code
            with self.assertRaises(tts.TtsFailure):
                child.synthesize(self.FIELDS)
            if len(output) > tts.MAX_CHILD_STDOUT:
                self.assertGreaterEqual(proc.kills, 1)
                self.assertGreaterEqual(proc.waited, 1)

    def test_timeout_kills_and_waits_for_only_its_child(self):
        proc = FakeProcess(b'', persistent=True)
        clock = [0.0]

        def sleep(seconds):
            clock[0] += seconds

        child = tts.WindowsSystemSpeech(executable=SYNTHETIC_POWERSHELL, timeout=.03,
            popen=lambda *_a, **_kw: proc, monotonic=lambda: clock[0], sleep=sleep)
        with self.assertRaises(tts.TtsFailure):
            child.synthesize(self.FIELDS)
        self.assertEqual(proc.kills, 1)
        self.assertGreaterEqual(proc.waited, 1)

    def test_unreaped_child_permanently_fences_second_spawn(self):
        proc = UnkillableProcess(b'', persistent=True)
        spawned = []
        clock = [0.0]

        def sleep(seconds):
            clock[0] += seconds

        def popen(*_args, **_kwargs):
            spawned.append(True)
            return proc

        child = tts.WindowsSystemSpeech(executable=SYNTHETIC_POWERSHELL,
            timeout=.01, popen=popen, monotonic=lambda: clock[0], sleep=sleep)
        with self.assertRaises(tts.TtsFailure):
            child.synthesize(self.FIELDS)
        with self.assertRaises(tts.TtsFailure):
            child.synthesize(self.FIELDS)
        with self.assertRaises(tts.TtsFailure):
            child.languages()
        self.assertEqual(len(spawned), 1)

    def test_blocked_reader_is_never_closed_and_failure_is_bounded_and_fenced(self):
        proc = UnkillableProcess(b'', persistent=True)
        pipe = BlockingPipe()
        proc.stdout = pipe
        spawned = []
        clock = [0.0]

        def sleep(seconds):
            clock[0] += seconds

        def popen(*_args, **_kwargs):
            spawned.append(True)
            return proc

        child = tts.WindowsSystemSpeech(executable=SYNTHETIC_POWERSHELL,
            timeout=.01, popen=popen, monotonic=lambda: clock[0], sleep=sleep)
        try:
            with self.assertRaises(tts.TtsFailure):
                child.synthesize(self.FIELDS)
            self.assertFalse(pipe.closed)
            with self.assertRaises(tts.TtsFailure):
                child.synthesize(self.FIELDS)
            self.assertEqual(len(spawned), 1)
        finally:
            pipe.release.set()

    def test_input_contract_rejects_mixed_speed_extra_and_oversized_utf8(self):
        bad = [dict(self.FIELDS, language='mixed'), dict(self.FIELDS, voice_speed='1.1'),
               dict(self.FIELDS, unexpected='field'), dict(self.FIELDS, text='猫' * 201)]
        for fields in bad:
            with self.subTest(fields=tuple(fields)):
                with self.assertRaises(ValueError):
                    tts.validate_request(fields)


class WindowsTtsHttpTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSynthesis()
        self.client = TestClient(operator.create_app(token=TOKEN, synthesizer=self.fake))
        self.headers = {'Authorization': 'Bearer ' + TOKEN,
                        'Content-Type': 'application/x-www-form-urlencoded'}
        self.form = {'text': 'Synthetic story reply.', 'language': 'en',
                     'voice_speed': '1.0', 'output_format': 'wav'}

    def request(self, *, headers=None, path='/speech', body=None):
        return self.client.post(path, content=urlencode(self.form).encode() if body is None else body,
            headers=self.headers | (headers or {}))

    def test_private_exact_form_returns_ephemeral_wav_without_cors_or_files(self):
        with tempfile.TemporaryDirectory() as folder:
            before = list(Path(folder).iterdir())
            response = self.request()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-type'], 'audio/wav')
            self.assertEqual(response.content, self.fake.audio)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(response.headers['cross-origin-resource-policy'], 'same-origin')
            self.assertNotIn('access-control-allow-origin', response.headers)
            self.assertEqual(list(Path(folder).iterdir()), before)

    def test_existing_local_adapter_sends_accepted_maximum_chinese_form(self):
        observed = []
        original = self.fake.synthesize
        def synthesize(fields):
            observed.append(fields.copy())
            return original(fields)
        self.fake.synthesize = synthesize
        def transport(request):
            response = self.client.request(request.method, request.url.path,
                content=request.content, headers=dict(request.headers))
            return httpx.Response(response.status_code, headers=dict(response.headers),
                                  content=response.content)
        from app.access.assistant_speech import LocalAssistantTts
        provider = LocalAssistantTts(url='http://127.0.0.1:7350/speech', token=TOKEN,
                                    transport=httpx.MockTransport(transport))
        self.assertEqual(provider.synthesize('猫'*200,'zh'),self.fake.audio)
        self.assertEqual(observed,[{'text':'猫'*200,'language':'zh',
                                  'voice_speed':'1.0','output_format':'wav'}])

    def test_auth_path_query_form_and_size_are_closed(self):
        self.assertEqual(self.request(headers={'Authorization': 'Bearer wrong'}).status_code, 403)
        self.assertEqual(self.client.post('/speech', content=b'',
            headers=[(b'authorization', b'Bearer \xff')]).status_code,403)
        self.assertEqual(self.request(headers={'Content-Length':'9'*100}).status_code,413)
        self.assertEqual(self.request(path='/speech/').status_code, 404)
        self.assertEqual(self.client.post('/speech?x=1', content=urlencode(self.form),
                         headers=self.headers).status_code, 400)
        self.assertEqual(self.request(body=b'text=ok&text=again&language=en&voice_speed=1.0&output_format=wav').status_code, 400)
        self.assertEqual(self.request(body=urlencode(self.form | {'extra':'x'}).encode()).status_code, 400)
        self.assertEqual(self.request(body=b'x' * (tts.MAX_FORM_BYTES + 1)).status_code, 413)
        self.assertEqual(self.client.post('/speech', content=urlencode(self.form),
            headers=self.headers | {'Content-Type':'text/plain'}).status_code, 415)

    def test_browser_signals_and_invalid_adapter_audio_are_refused(self):
        for browser_header in ({'Origin': 'http://127.0.0.1:7350'},
                               {'Sec-Fetch-Site': 'same-origin'}):
            self.assertEqual(self.request(headers=browser_header).status_code, 403)
        self.fake.audio = b'not a wav'
        response = self.request()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_mixed_language_and_wrong_rate_refuse_without_synthesis(self):
        for change in ({'language':'mixed'}, {'voice_speed':'1.2'}):
            response = self.client.post('/speech', content=urlencode(self.form | change), headers=self.headers)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.fake.cancelled, False)

    def test_one_active_synthesis_rejects_concurrent_request_as_busy(self):
        entered, release = threading.Event(), threading.Event()
        fake = FakeSynthesis(entered=entered, release=release)
        client1 = TestClient(operator.create_app(token=TOKEN, synthesizer=fake))
        client2 = TestClient(client1.app)
        body = urlencode(self.form).encode()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client1.post, '/speech', content=body, headers=self.headers)
            self.assertTrue(entered.wait(2))
            second = client2.post('/speech', content=body, headers=self.headers)
            self.assertEqual(second.status_code, 503)
            release.set()
            self.assertEqual(first.result(timeout=4).status_code, 200)


class WindowsTtsCliAndTokenTests(unittest.TestCase):
    def test_default_plan_and_check_do_not_spawn_or_enumerate_voices(self):
        with patch.object(operator.WindowsSystemSpeech, 'languages', side_effect=AssertionError('voice enumeration')):
            self.assertEqual(operator.main([]), 0)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'token.txt'
                path.write_text(TOKEN, encoding='ascii')
                path.chmod(0o600)
                with patch.object(operator.WindowsSystemSpeech, '__init__', side_effect=AssertionError('child')):
                    self.assertEqual(operator.main(['--check', '--token-file', str(path)]), 0)

    def test_cli_imports_backend_outside_checkout_and_powershell_loads_speech(self):
        with tempfile.TemporaryDirectory() as folder:
            env = os.environ.copy()
            env.pop('PYTHONPATH', None)
            result = __import__('subprocess').run([sys.executable, str(ROOT / 'scripts' / 'serve_windows_tts.py')],
                cwd=folder, env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"starts_listener":false', result.stdout)
        load = tts._POWERSHELL.index('Add-Type -AssemblyName System.Speech')
        creation = tts._POWERSHELL.index('New-Object System.Speech.Synthesis.SpeechSynthesizer')
        self.assertLess(load, creation)

    def test_app_uses_same_strong_token_policy_as_file_loader(self):
        for invalid in ('x' * 31, 'x' * 32 + '!', 'x' * 257):
            with self.subTest(invalid_length=len(invalid)):
                with self.assertRaises(ValueError):
                    operator.create_app(token=invalid)

    @unittest.skipIf(os.name == 'nt', 'POSIX mode-bit check only')
    def test_token_file_requires_private_mode_regular_direct_file_and_strong_token(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'token.txt'
            path.write_text(TOKEN, encoding='ascii')
            path.chmod(0o600)
            self.assertEqual(tts.read_private_token(path), TOKEN)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                tts.read_private_token(path)
            path.unlink()
            path.symlink_to(Path(folder) / 'other')
            with self.assertRaises(ValueError):
                tts.read_private_token(path)


if __name__ == '__main__':
    unittest.main()
