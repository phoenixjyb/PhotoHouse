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


MAX_AUDIO_SECONDS = 30
MAX_WAV_BYTES = 2 * 1024 * 1024


def _provider_reply(client, url, *, max_bytes, **kwargs):
    with client.stream('POST', url, **kwargs) as response:
        if response.status_code != 200:
            raise AssistantSpeechUnavailable()
        media_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
        payload = bytearray()
        for chunk in response.iter_bytes():
            if len(payload) + len(chunk) > max_bytes:
                raise AssistantSpeechUnavailable()
            payload.extend(chunk)
    return media_type, bytes(payload)


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
                _, reply = _provider_reply(client, self.url, max_bytes=8192, headers=headers,
                    content=payload)
            result = json.loads(reply)
            if (type(result) is not dict or result.get('success') is False
                    or type(result.get('text')) is not str):
                raise AssistantSpeechUnavailable()
            words = result['text'].strip()
            if not words or len(words.encode('utf-8')) > 1024:
                raise AssistantSpeechUnavailable()
            chinese = any('\u3400' <= c <= '\u9fff' for c in words)
            latin = any('a' <= c.casefold() <= 'z' for c in words)
            language = 'mixed' if chinese and latin else 'zh' if chinese else 'en' if latin else 'unknown'
            return {'version': 1, 'text': words, 'language': language}
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise AssistantSpeechUnavailable() from error


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
