"""Transient, loopback-only ASR for an authenticated assistant request."""
import base64
import binascii
import io
import json
import wave

import httpx

from .annotation_local import local_url


class AssistantSpeechUnavailable(RuntimeError):
    pass


class AssistantAsrFailure(AssistantSpeechUnavailable):
    """A safe, bounded ASR failure category for the assistant API."""

    def __init__(self, code='speech_unavailable', status=503):
        allowed = {'speech_no_input': 422, 'speech_busy': 503, 'speech_timeout': 504,
                   'speech_invalid_response': 502, 'speech_unavailable': 503}
        if type(code) is not str or type(status) is not int or allowed.get(code) != status:
            raise ValueError('Invalid ASR category')
        self.code = code
        self.status = status
        super().__init__(code)


MAX_AUDIO_SECONDS = 30
MAX_WAV_BYTES = 2 * 1024 * 1024


def _provider_reply(client, url, *, max_bytes, failure_factory=None, **kwargs):
    with client.stream('POST', url, **kwargs) as response:
        if response.status_code != 200:
            if failure_factory is not None:
                raise failure_factory('status', response.status_code)
            raise AssistantSpeechUnavailable()
        media_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
        payload = bytearray()
        for chunk in response.iter_bytes():
            if len(payload) + len(chunk) > max_bytes:
                if failure_factory is not None:
                    raise failure_factory('invalid_response', response.status_code)
                raise AssistantSpeechUnavailable()
            payload.extend(chunk)
    return media_type, bytes(payload)


def _asr_provider_failure(kind, status=None):
    if kind == 'status' and status == 429:
        return AssistantAsrFailure('speech_busy', 503)
    if kind == 'invalid_response':
        return AssistantAsrFailure('speech_invalid_response', 502)
    return AssistantAsrFailure()


def valid_wav(payload):
    if not isinstance(payload, bytes) or not 44 <= len(payload) <= MAX_WAV_BYTES:
        return False
    try:
        with wave.open(io.BytesIO(payload), 'rb') as audio:
            frames = audio.getnframes()
            return (audio.getnchannels() == 1 and audio.getsampwidth() == 2
                    and audio.getframerate() == 16000 and audio.getcomptype() == 'NONE'
                    and 0 < frames <= MAX_AUDIO_SECONDS * 16000
                    and len(audio.readframes(frames)) == frames * 2)
    except (EOFError, ValueError, wave.Error):
        return False


class LocalAssistantAsr:
    """No ambient proxy, redirect, cloud fallback, disk write or transcript log."""

    def __init__(self, *, url, model, token=None, timeout=45, transport=None):
        self.url = local_url(url, asr=True)
        if not isinstance(model, str) or not model.strip() or len(model) > 120:
            raise ValueError('Explicit ASR model name required')
        if token is not None and (not isinstance(token, str) or not token):
            raise ValueError('Invalid ASR token')
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ValueError('Invalid ASR timeout')
        self.model, self.token, self.timeout, self.transport = model, token, timeout, transport

    def transcribe(self, payload):
        if not valid_wav(payload):
            raise ValueError('Invalid WAV')
        headers = {'Content-Type': 'audio/wav'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        try:
            with httpx.Client(timeout=self.timeout, trust_env=False, transport=self.transport,
                              follow_redirects=False) as client:
                media_type, reply = _provider_reply(client, self.url, max_bytes=8192,
                    failure_factory=_asr_provider_failure, headers=headers, content=payload)
            if media_type != 'application/json':
                raise AssistantAsrFailure('speech_invalid_response', 502)
            try:
                result = json.loads(reply)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise AssistantAsrFailure('speech_invalid_response', 502) from None
            if (type(result) is not dict or result.get('success') is False
                    or type(result.get('text')) is not str):
                raise AssistantAsrFailure('speech_invalid_response', 502)
            words = result['text'].strip()
            if not words:
                raise AssistantAsrFailure('speech_no_input', 422)
            try:
                word_bytes = len(words.encode('utf-8'))
            except UnicodeError:
                raise AssistantAsrFailure('speech_invalid_response', 502) from None
            if word_bytes > 1024:
                raise AssistantAsrFailure('speech_invalid_response', 502)
            chinese = any('\u3400' <= c <= '\u9fff' for c in words)
            latin = any('a' <= c.casefold() <= 'z' for c in words)
            language = 'mixed' if chinese and latin else 'zh' if chinese else 'en' if latin else 'unknown'
            return {'version': 1, 'text': words, 'language': language}
        except AssistantAsrFailure:
            raise
        except httpx.TimeoutException:
            raise AssistantAsrFailure('speech_timeout', 504) from None
        except Exception:
            # Provider exceptions can contain private URLs, request data or bodies.
            raise AssistantAsrFailure() from None


def valid_reply_wav(payload):
    if not isinstance(payload, bytes) or not 44 <= len(payload) <= MAX_WAV_BYTES:
        return False
    try:
        with wave.open(io.BytesIO(payload), 'rb') as audio:
            frames = audio.getnframes()
            return (audio.getcomptype() == 'NONE' and audio.getnchannels() in (1, 2)
                    and audio.getsampwidth() in (1, 2, 3, 4)
                    and 8000 <= audio.getframerate() <= 48000
                    and 0 < frames <= MAX_AUDIO_SECONDS * audio.getframerate()
                    and len(audio.readframes(frames)) == frames * audio.getnchannels() * audio.getsampwidth())
    except (EOFError, ValueError, wave.Error):
        return False


class LocalAssistantTts:
    """Bounded local synthesis; no browser/platform/cloud fallback."""

    def __init__(self, *, url, token=None, timeout=45, transport=None):
        self.url = local_url(url, asr=True)
        if token is not None and (not isinstance(token, str) or not token):
            raise ValueError('Invalid TTS token')
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ValueError('Invalid TTS timeout')
        self.token, self.timeout, self.transport = token, timeout, transport

    def synthesize(self, words, language):
        if (type(words) is not str or not words.strip() or len(words.encode('utf-8')) > 600
                or language not in {'zh', 'en', 'mixed'}):
            raise ValueError('Invalid synthesis request')
        headers = {'Authorization': 'Bearer ' + self.token} if self.token else {}
        try:
            with httpx.Client(timeout=self.timeout, trust_env=False, transport=self.transport,
                              follow_redirects=False) as client:
                media_type, reply = _provider_reply(client, self.url,
                    max_bytes=MAX_WAV_BYTES * 2, headers=headers,
                    data={'text': words, 'language': language, 'voice_speed': '1.0',
                          'output_format': 'wav'})
            if media_type in ('audio/wav', 'audio/x-wav'):
                payload = reply
            else:
                envelope = json.loads(reply)
                if type(envelope) is not dict or envelope.get('success') is not True:
                    raise AssistantSpeechUnavailable()
                encoded = envelope.get('audio_base64') or envelope.get('audio_data')
                if type(encoded) is not str or len(encoded) > MAX_WAV_BYTES * 2:
                    raise AssistantSpeechUnavailable()
                payload = base64.b64decode(encoded, validate=True)
            if not valid_reply_wav(payload):
                raise AssistantSpeechUnavailable()
            return payload
        except (httpx.HTTPError, ValueError, TypeError, binascii.Error) as error:
            raise AssistantSpeechUnavailable() from error
