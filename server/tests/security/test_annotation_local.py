"""Loopback-only model adapter contract; no real provider or network calls."""
import json
import sqlite3
import sys
from pathlib import Path
import unittest

import httpx
from httpx import SyncByteStream

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.access.annotation_local import LocalAnnotationModels, LocalProviderError
from app.access.annotation_processing import ProcessingRefused, recover_interrupted


class LocalAnnotationModelsTest(unittest.TestCase):
    def make_models(self, handler):
        return LocalAnnotationModels(asr_url='http://127.0.0.1:8001/api/voice-chat/transcribe',
            asr_model='whisper-base', ollama_url='http://127.0.0.1:11434',
            ollama_model='local-memory', transport=httpx.MockTransport(handler))

    def test_audio_and_wording_use_explicit_local_contract(self):
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.port == 8001:
                self.assertIn(b'name="audio_file"', request.content)
                self.assertIn(b'RIFF', request.content)
                return httpx.Response(200, json={'success': True, 'text': 'Grandma sang.'})
            body = json.loads(request.content)
            self.assertEqual('local-memory', body['model'])
            self.assertEqual('json', body['format'])
            self.assertFalse(body['stream'])
            self.assertIn('Grandma sang.', body['prompt'])
            return httpx.Response(200, json={'response': json.dumps({
                'text': 'Grandma sang at dinner.', 'tags': ['grandma', 'dinner']})})
        models = self.make_models(handler)
        self.assertEqual('Grandma sang.', models.transcribe(b'RIFFsynthetic', 'en')['text'])
        self.assertEqual(['grandma', 'dinner'], models.polish('Grandma sang.', 'en')['tags'])
        self.assertEqual(['127.0.0.1', '127.0.0.1'], [request.url.host for request in calls])

    def test_external_host_and_invalid_model_result_refuse(self):
        with self.assertRaises(ValueError):
            LocalAnnotationModels(asr_url='https://example.com/transcribe', asr_model='local',
                ollama_url='http://127.0.0.1:11434', ollama_model='local')
        models = self.make_models(lambda _: httpx.Response(200, json={'response': 'not JSON'}))
        with self.assertRaises(LocalProviderError):
            models.polish('A memory.', 'en')

    def test_provider_stream_cap_stops_reading_oversized_body(self):
        consumed = []

        class Oversized(SyncByteStream):
            def __iter__(self):
                consumed.append('first')
                yield b'{' + b' ' * (128 * 1024)
                self.fail_if_read = True
                raise AssertionError('adapter continued reading after cap')

            def close(self):
                pass

        models = self.make_models(lambda _: httpx.Response(200, stream=Oversized()))
        with self.assertRaises(LocalProviderError):
            models.polish('A memory.', 'en')
        self.assertEqual(['first'], consumed)

    def test_strict_json_rejects_duplicate_and_nonfinite_values(self):
        bodies = [b'{"success":true,"text":"first","text":"second"}',
                  b'{"success":true,"text":NaN}']
        for raw in bodies:
            with self.subTest(raw=raw):
                models = self.make_models(lambda _, body=raw: httpx.Response(200, content=body))
                with self.assertRaises(LocalProviderError):
                    models.transcribe(b'RIFFsynthetic', 'en')
        models = self.make_models(lambda _: httpx.Response(200, json={'response':
            '{"text":"x","tags":[],"tags":[]}'}))
        with self.assertRaises(LocalProviderError):
            models.polish('A memory.', 'en')

    def test_provider_envelope_and_inner_values_are_strict(self):
        for envelope in (
            {'response': '{"text":"ok","tags":[]}', 'model': 'foreign'},
            {'response': '{"text":"ok","tags":[]}', 'done': False},
            {'response': '{"text":"ok","tags":["same","same"]}'},
            {'response': '{"text":"ok","tags":["x\\u0000"]}'},
            {'response': '{"text":"x"}'},
        ):
            with self.subTest(envelope=envelope):
                models = self.make_models(lambda _, value=envelope: httpx.Response(200, json=value))
                with self.assertRaises(LocalProviderError):
                    models.polish('A memory.', 'en')
        # Older local Ollama versions omit model/done; retain that supported fixture contract.
        models = self.make_models(lambda _: httpx.Response(200, json={'response':
            '{"text":"ok","tags":[]}'}))
        self.assertEqual('ok', models.polish('A memory.', 'en')['text'])

    def test_sanitized_transport_redirect_and_deadline_failures(self):
        secret = 'private provider response and prompt'
        models = self.make_models(lambda _: (_ for _ in ()).throw(httpx.ConnectError(secret)))
        with self.assertRaises(LocalProviderError) as caught:
            models.polish('A memory.', 'en')
        self.assertNotIn(secret, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

        calls = []
        models = self.make_models(lambda request: calls.append(request) or httpx.Response(
            302, headers={'Location': 'http://example.com/secret'}))
        with self.assertRaises(LocalProviderError):
            models.polish('A memory.', 'en')
        self.assertEqual(1, len(calls))

        ticks = iter([0.0, 0.0, 0.0, 46.0])
        models = LocalAnnotationModels(asr_url='http://127.0.0.1:8001/transcribe',
            asr_model='whisper-base', ollama_url='http://127.0.0.1:11434',
            ollama_model='local-memory', monotonic=lambda: next(ticks),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'response':
                '{"text":"ok","tags":[]}'})))
        with self.assertRaises(LocalProviderError):
            models.polish('A memory.', 'en')

    def test_input_bounds_and_constructor_reject_unsafe_configuration(self):
        for timeout in (True, float('nan'), float('inf'), 0, 121):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                LocalAnnotationModels(asr_url='http://127.0.0.1:8001/transcribe',
                    asr_model='whisper', ollama_url='http://127.0.0.1:11434',
                    ollama_model='local', timeout=timeout)
        for label in ('model\nname', 'x' * 121):
            with self.subTest(label=label[:12]), self.assertRaises(ValueError):
                LocalAnnotationModels(asr_url='http://127.0.0.1:8001/transcribe',
                    asr_model=label, ollama_url='http://127.0.0.1:11434',
                    ollama_model='local')
        models = self.make_models(lambda _: self.fail('provider must not be called'))
        for text, language in (('x' * (16 * 1024 + 1), 'en'), ('x\x00y', 'en'), ('x', 'en\ny')):
            with self.subTest(text=text[:12], language=language), self.assertRaises(LocalProviderError):
                models.polish(text, language)
        with self.assertRaises(LocalProviderError):
            models.transcribe(b'x' * (2 * 1024 * 1024 + 1), 'en')

    def test_explicit_recovery_requires_exact_stale_running_revision(self):
        with sqlite3.connect(':memory:') as db:
            db.execute('''CREATE TABLE access_annotation_derivations (
                annotation_id TEXT,revision INTEGER,state TEXT,started_at INTEGER,
                error_code TEXT,updated_at INTEGER,finished_at INTEGER)''')
            db.execute("INSERT INTO access_annotation_derivations VALUES ('note',1,'running',100,NULL,100,NULL)")
            db.execute("INSERT INTO access_annotation_derivations VALUES ('recent',1,'running',950,NULL,950,NULL)")
            db.commit()
            for identifier, revision in [('note', 2), ('recent', 1), ('missing', 1)]:
                with self.subTest(identifier=identifier, revision=revision), self.assertRaises(ProcessingRefused):
                    recover_interrupted(db, identifier, revision, clock=lambda: 1000)
            self.assertEqual({'id': 'note', 'revision': 1, 'state': 'failed'},
                recover_interrupted(db, 'note', 1, clock=lambda: 1000))
            self.assertEqual(('failed', 'operator_recovered_interrupted', 1000),
                tuple(db.execute('''SELECT state,error_code,finished_at FROM access_annotation_derivations
                    WHERE annotation_id='note' ''').fetchone()))
            with self.assertRaises(ProcessingRefused):
                recover_interrupted(db, 'note', 1, clock=lambda: 1000)


if __name__ == '__main__':
    unittest.main()
