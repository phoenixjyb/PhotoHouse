"""Explicit loopback-only adapters for private upload annotation derivation."""
import json
import math
import time
from urllib.parse import urlsplit

import httpx


_MAX_PROVIDER_BODY = 128 * 1024
_MAX_AUDIO = 2 * 1024 * 1024
_MAX_TEXT = 16 * 1024
_LANGUAGES = {'en', 'zh', 'mixed', 'und'}


class LocalProviderError(RuntimeError):
    pass


def local_url(value, *, asr=False):
    parts = urlsplit(value)
    if (parts.scheme != 'http' or parts.hostname not in {'127.0.0.1', 'localhost'}
            or not parts.port or parts.username or parts.password or parts.fragment
            or parts.query or (not asr and parts.path.rstrip('/') not in {'', '/api/generate'})
            or (asr and not parts.path.startswith('/'))):
        raise ValueError('An explicit loopback HTTP provider URL is required')
    return value.rstrip('/')


def _strict_json(data):
    """Decode UTF-8 JSON while rejecting duplicate object keys and NaN/Infinity."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result

    def constant(_value):
        raise ValueError('non-finite JSON value')

    return json.loads(data.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                      parse_constant=constant)


def _valid_text(value, maximum, *, nonblank=True):
    if not isinstance(value, str) or '\x00' in value:
        return False
    try:
        encoded = value.encode('utf-8', errors='strict')
    except UnicodeError:
        return False
    if len(encoded) > maximum or (nonblank and not value.strip()):
        return False
    return all(ch in '\n\t' or (ord(ch) >= 32 and not 0x7f <= ord(ch) < 0xa0)
               for ch in value)


class LocalAnnotationModels:
    def __init__(self, *, asr_url, ollama_url, ollama_model, asr_model,
                 asr_token=None, timeout=45, transport=None, monotonic=None):
        self.asr_url = local_url(asr_url, asr=True)
        base = local_url(ollama_url)
        self.ollama_url = base if base.endswith('/api/generate') else base + '/api/generate'
        for label in (ollama_model, asr_model):
            if (not _valid_text(label, 120) or any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0
                                                  for c in label)):
                raise ValueError('Explicit local model names required')
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or not 0 < timeout <= 120):
            raise ValueError('Invalid local provider timeout')
        if asr_token is not None and (not isinstance(asr_token, str) or not asr_token
                or any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 for c in asr_token)):
            raise ValueError('Invalid local ASR credential')
        if monotonic is not None and not callable(monotonic):
            raise ValueError('Invalid monotonic clock')
        self.ollama_model, self.asr_model = ollama_model, asr_model
        self.asr_token, self.timeout, self.transport = asr_token, float(timeout), transport
        self._monotonic = monotonic or time.monotonic

    def _read_response(self, client, method, url, *, error_message, **kwargs):
        """Read at most 128 KiB; phase timeouts bound a blocked read, deadline checks bound trickle.

        A synchronous read already waiting on the socket cannot be cancelled by the monotonic
        check; the configured httpx read timeout limits that single wait. Checks before and
        after every yielded chunk prevent a provider from extending total elapsed time by
        continuously trickling data.
        """
        deadline = self._monotonic() + self.timeout

        def check_deadline():
            if self._monotonic() >= deadline:
                raise LocalProviderError(error_message)

        with client.stream(method, url, **kwargs) as response:
            check_deadline()  # headers have arrived
            if response.status_code != 200:
                raise LocalProviderError(error_message)
            payload = bytearray()
            for chunk in response.iter_bytes():
                check_deadline()
                if len(payload) + len(chunk) > _MAX_PROVIDER_BODY:
                    raise LocalProviderError(error_message)
                payload.extend(chunk)
                check_deadline()
        check_deadline()
        return bytes(payload), check_deadline

    def _client(self):
        return httpx.Client(timeout=self.timeout, trust_env=False, transport=self.transport,
                            follow_redirects=False)

    def transcribe(self, wav_bytes, language):
        if not isinstance(wav_bytes, (bytes, bytearray)) or not 0 < len(wav_bytes) <= _MAX_AUDIO:
            raise LocalProviderError('Local ASR input invalid') from None
        if not isinstance(language, str) or language not in _LANGUAGES:
            raise LocalProviderError('Local ASR input invalid') from None
        headers = {'Authorization': 'Bearer ' + self.asr_token} if self.asr_token else {}
        data = {'language': language} if language in {'en', 'zh'} else {}
        try:
            with self._client() as client:
                raw, check_deadline = self._read_response(client, 'POST', self.asr_url,
                    error_message='Local ASR unavailable', headers=headers, data=data,
                    files={'audio_file': ('annotation.wav', bytes(wav_bytes), 'audio/wav')})
            check_deadline()
            body = _strict_json(raw)
            if (not isinstance(body, dict) or body.get('success') is False
                    or not _valid_text(body.get('text'), _MAX_TEXT)):
                raise LocalProviderError('Local ASR response invalid') from None
            check_deadline()
            return {'text': body['text'].strip(), 'provider': 'local-whisper', 'model': self.asr_model}
        except LocalProviderError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, UnicodeError, OverflowError):
            raise LocalProviderError('Local ASR unavailable') from None

    def polish(self, source_text, language):
        if (not _valid_text(source_text, _MAX_TEXT) or not isinstance(language, str)
                or language not in _LANGUAGES):
            raise LocalProviderError('Local wording input invalid') from None
        prompt = (
            'Rewrite the following family photo memory clearly while preserving every factual detail. '
            'Do not add names, places, dates, or events. Return a JSON object with exactly "text" '
            'and "tags". "tags" is an array of at most 16 short factual topics found in the input. '
            'If uncertain, use an empty array. Use the input language.\n'
            'Language hint: ' + language + '\nInput JSON: ' + json.dumps(source_text, ensure_ascii=False)
        )
        try:
            with self._client() as client:
                raw, check_deadline = self._read_response(client, 'POST', self.ollama_url,
                    error_message='Local wording model unavailable', json={'model': self.ollama_model,
                    'prompt': prompt, 'format': 'json', 'stream': False,
                    'think': False,
                    'options': {'temperature': 0}})
            check_deadline()
            envelope = _strict_json(raw)
            if (not isinstance(envelope, dict) or not isinstance(envelope.get('response'), str)
                    or ('model' in envelope and envelope['model'] != self.ollama_model)
                    or ('done' in envelope and envelope['done'] is not True)):
                raise LocalProviderError('Local wording response invalid') from None
            result = _strict_json(envelope['response'].encode('utf-8', errors='strict'))
            if (not isinstance(result, dict) or set(result) != {'text', 'tags'}
                    or not _valid_text(result.get('text'), _MAX_TEXT)
                    or not isinstance(result.get('tags'), list) or len(result['tags']) > 16):
                raise LocalProviderError('Local wording response invalid') from None
            tags = result['tags']
            if (any(not _valid_text(tag, 128) for tag in tags)
                    or len(set(tags)) != len(tags)):
                raise LocalProviderError('Local wording response invalid') from None
            check_deadline()
            return {'text': result['text'], 'tags': tags,
                    'provider': 'local-ollama', 'model': self.ollama_model}
        except LocalProviderError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, UnicodeError, OverflowError):
            raise LocalProviderError('Local wording model unavailable') from None
