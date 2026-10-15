import io
import json
from pathlib import Path
import sys
import wave

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.assistant_speech import (
    AssistantAsrFailure,
    AssistantSpeechUnavailable,
    LocalAssistantAsr,
    LocalAssistantTts,
)


def wav_payload():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\0\0' * 160)
    return output.getvalue()


def transcriber(handler):
    return LocalAssistantAsr(
        url='http://127.0.0.1:8765/asr',
        model='test-model',
        transport=httpx.MockTransport(handler),
    )


def response(status=200, body=b'{"text":"hello"}', content_type='application/json'):
    return httpx.Response(status, content=body, headers={'content-type': content_type})


@pytest.mark.parametrize('status,expected_code,expected_status', [
    (400, 'speech_unavailable', 503),
    (429, 'speech_busy', 503),
    (500, 'speech_unavailable', 503),
    (503, 'speech_unavailable', 503),
])
def test_asr_non_success_statuses_are_safely_classified(status, expected_code, expected_status):
    secret = 'provider error with transcript, token and private url'
    with pytest.raises(AssistantAsrFailure) as raised:
        transcriber(lambda request: response(status, secret.encode())).transcribe(wav_payload())

    error = raised.value
    assert (error.code, error.status) == (expected_code, expected_status)
    assert secret not in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_asr_timeout_has_a_bounded_public_category_and_hides_provider_detail():
    secret = 'sensitive timeout endpoint and request detail'

    def handle(_request):
        raise httpx.ReadTimeout(secret)

    with pytest.raises(AssistantAsrFailure) as raised:
        transcriber(handle).transcribe(wav_payload())

    assert (raised.value.code, raised.value.status) == ('speech_timeout', 504)
    assert secret not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


@pytest.mark.parametrize('body,content_type', [
    (b'{not-json', 'application/json'),
    (b'{"success":false,"error":"private provider text"}', 'application/json'),
    (b'{"text":42}', 'application/json'),
    (b'{"text":"' + b'x' * 1025 + b'"}', 'application/json'),
    (b'{"text":"hello"}', 'text/plain'),
])
def test_asr_invalid_successful_provider_replies_are_502(body, content_type):
    with pytest.raises(AssistantAsrFailure) as raised:
        transcriber(lambda _request: response(body=body, content_type=content_type)).transcribe(wav_payload())

    assert (raised.value.code, raised.value.status) == ('speech_invalid_response', 502)


def test_asr_oversized_successful_provider_reply_is_502():
    with pytest.raises(AssistantAsrFailure) as raised:
        transcriber(lambda _request: response(body=b' ' * 8193)).transcribe(wav_payload())

    assert (raised.value.code, raised.value.status) == ('speech_invalid_response', 502)


def test_asr_empty_successful_text_is_reported_as_no_input():
    with pytest.raises(AssistantAsrFailure) as raised:
        transcriber(lambda _request: response(body=json.dumps({'text': '  \n'}).encode())).transcribe(wav_payload())

    assert (raised.value.code, raised.value.status) == ('speech_no_input', 422)


@pytest.mark.parametrize('provider_error', [
    httpx.ConnectError('private host and token detail'),
    RuntimeError('private provider body and stack detail'),
])
def test_asr_transport_and_unknown_errors_are_generic_and_private(provider_error):
    with pytest.raises(AssistantAsrFailure) as raised:
        transcriber(lambda _request: (_ for _ in ()).throw(provider_error)).transcribe(wav_payload())

    assert (raised.value.code, raised.value.status) == ('speech_unavailable', 503)
    assert str(provider_error) not in str(raised.value)
    assert raised.value.__cause__ is None


def test_asr_valid_reply_still_returns_only_the_bounded_transcript():
    body = json.dumps({'success': True, 'text': '  你好 hello  '}).encode()
    result = transcriber(lambda _request: response(body=body)).transcribe(wav_payload())

    assert result == {'version': 1, 'text': '你好 hello', 'language': 'mixed'}


def test_invalid_unicode_provider_text_is_not_a_transport_failure():
    with pytest.raises(AssistantAsrFailure) as caught:
        transcriber(lambda _: response(body=b'{"text":"\\ud800"}')).transcribe(wav_payload())
    assert (caught.value.code, caught.value.status) == ('speech_invalid_response', 502)


def test_category_constructor_cannot_expose_arbitrary_provider_details():
    for code, status in [('provider-secret', 503), ('speech_no_input', 503), ({}, 503)]:
        with pytest.raises(ValueError, match='Invalid ASR category'):
            AssistantAsrFailure(code, status)


def test_shared_provider_helper_keeps_tts_failures_as_the_existing_base_type():
    tts = LocalAssistantTts(
        url='http://127.0.0.1:8765/tts',
        transport=httpx.MockTransport(lambda _request: response(429, b'private provider detail')),
    )

    with pytest.raises(AssistantSpeechUnavailable) as raised:
        tts.synthesize('hello', 'en')

    assert type(raised.value) is AssistantSpeechUnavailable
    assert 'private provider detail' not in str(raised.value)
