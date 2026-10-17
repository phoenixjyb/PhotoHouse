"""Bounded local HTTP caption provider tests; all responses are mocked."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
import json

import httpx
from PIL import Image
import pytest

from app.approved_caption_http import LocalCaptionError, LocalCaptionHTTP


GOOD = 'EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子放在木桌上。'
HEALTHY = {'status': 'healthy', 'model_cache_ready': True, 'active_provider': 'qwen3-vl'}
MODEL_ID = 'Qwen/Qwen3-VL-8B-Instruct'


def response_handler(handler, calls=None):
    def send(request):
        if calls is not None:
            calls.append(request)
        return handler(request)
    return httpx.MockTransport(send)


def admitted(handler, *, calls=None, **kwargs):
    provider = LocalCaptionHTTP(
        url='http://127.0.0.1:8102',
        transport=response_handler(handler, calls),
        **kwargs,
    )
    provider.preflight()
    return provider


def test_constructor_does_no_io_and_admission_is_explicit():
    calls = []
    provider = LocalCaptionHTTP(
        url='http://127.0.0.1:8102',
        transport=response_handler(lambda request: httpx.Response(500), calls),
    )
    assert calls == []
    with pytest.raises(LocalCaptionError) as caught:
        provider.get_model_name()
    assert caught.value.reason_code == 'not_admitted'
    assert calls == []


@pytest.mark.parametrize('url', [
    'https://127.0.0.1:8102',
    'http://localhost:8102',
    'http://example.com:8102',
    'http://127.0.0.1',
    'http://user:pass@127.0.0.1:8102',
    'http://127.0.0.1:8102/api',
    'http://127.0.0.1:8102?x=1',
    'http://127.0.0.1:8102?',
    'http://127.0.0.1:8102#fragment',
    'http://127.0.0.1:8102#',
])
def test_rejects_non_loopback_or_ambiguous_urls(url):
    with pytest.raises(LocalCaptionError) as caught:
        LocalCaptionHTTP(url=url)
    assert caught.value.reason_code == 'invalid_config'


def test_ipv6_loopback_is_allowed_with_an_explicit_port():
    provider = LocalCaptionHTTP(url='http://[::1]:8102')
    assert provider.url == 'http://[::1]:8102'


@pytest.mark.parametrize('model_id', ['', '  ', 'model\nname', 'x' * 257])
def test_expected_model_id_must_be_a_bounded_plain_string(model_id):
    with pytest.raises(LocalCaptionError) as caught:
        LocalCaptionHTTP(url='http://127.0.0.1:8102', expected_model_id=model_id)
    assert caught.value.reason_code == 'invalid_config'


@pytest.mark.parametrize('body', [
    {'status': 'healthy', 'model_cache_ready': False, 'active_provider': 'qwen3-vl'},
    {'status': 'healthy', 'model_cache_ready': True, 'active_provider': 'other-vl'},
    {'status': 'starting', 'model_cache_ready': True, 'active_provider': 'qwen3-vl'},
    {'status': [], 'model_cache_ready': True, 'active_provider': 'qwen3-vl'},
])
def test_unready_or_drifted_backend_is_not_admitted(body):
    provider = LocalCaptionHTTP(
        url='http://127.0.0.1:8102',
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    with pytest.raises(LocalCaptionError) as caught:
        provider.preflight()
    assert caught.value.reason_code == 'invalid_response'
    with pytest.raises(LocalCaptionError) as caught:
        provider.get_model_name()
    assert caught.value.reason_code == 'not_admitted'


@pytest.mark.parametrize('raw', [
    b'{"status":"healthy","model_cache_ready":true,"active_provider":"qwen3-vl","x":1,"x":2}',
    b'{"status":"healthy","model_cache_ready":NaN,"active_provider":"qwen3-vl"}',
    b'{not-json',
    b'{}' + b' ' * (64 * 1024),
])
def test_preflight_rejects_invalid_or_oversized_json(raw):
    provider = LocalCaptionHTTP(
        url='http://127.0.0.1:8102',
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=raw)),
    )
    with pytest.raises(LocalCaptionError) as caught:
        provider.preflight()
    assert caught.value.reason_code == 'invalid_response'


def test_response_stream_cannot_extend_the_total_deadline(monkeypatch):
    class Trickling(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"status":"healthy","model_cache_ready":true,'
            yield b'"active_provider":"qwen3-vl"}'

        def close(self):
            pass

    ticks = iter([0.0, 0.0, 0.0, 6.0, 6.0])
    monkeypatch.setattr('app.approved_caption_http.time.monotonic', lambda: next(ticks, 6.0))
    provider = LocalCaptionHTTP(
        url='http://127.0.0.1:8102',
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Trickling())),
    )
    with pytest.raises(LocalCaptionError) as caught:
        provider.preflight()
    assert caught.value.reason_code == 'unavailable'


def test_caption_and_translation_use_exact_bounded_contracts():
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == '/health':
            assert request.extensions['timeout']['connect'] <= 5
            return httpx.Response(200, json=HEALTHY)
        if request.url.path == '/caption':
            body = request.read()
            assert b'name="file"; filename="image.png"' in body
            assert b'Content-Type: image/png' in body
            assert b'name="prompt"' in body
            return httpx.Response(200, json={
                'caption': GOOD, 'provider': 'qwen3-vl', 'model': MODEL_ID,
            })
        if request.url.path == '/translate':
            payload = json.loads(request.read())
            assert payload == {
                'text': 'A red cup rests on a wooden table.',
                'source_lang': 'en',
                'target_lang': 'zh-CN',
                'style': 'photo caption',
                'avoid_terms': ['可能', '拍摄'],
            }
            return httpx.Response(200, json={
                'translation': 'ZH-CN: 一个红色杯子放在木桌上。',
                'provider': 'qwen3-vl', 'model': MODEL_ID,
            })
        return httpx.Response(404)

    provider = admitted(handle)
    assert provider.get_model_name() == 'qwen3-vl-http'
    image = Image.new('RGB', (8, 8), 'red')
    assert provider.generate_caption(image, prompt='Detailed bilingual caption') == GOOD
    assert provider.translate_caption(
        'A red cup rests on a wooden table.', avoid_terms=['可能', '拍摄'],
    ) == '一个红色杯子放在木桌上。'
    assert [request.url.path for request in requests] == ['/health', '/caption', '/translate']
    image.close()


def test_redirect_is_rejected_without_following_it():
    paths = []

    def handle(request):
        paths.append(request.url.path)
        if request.url.path == '/health':
            return httpx.Response(302, headers={'Location': 'http://127.0.0.1:9999/steal'})
        return httpx.Response(200, json=HEALTHY)

    provider = LocalCaptionHTTP(url='http://127.0.0.1:8102', transport=httpx.MockTransport(handle))
    with pytest.raises(LocalCaptionError) as caught:
        provider.preflight()
    assert caught.value.reason_code == 'invalid_response'
    assert paths == ['/health']


def test_service_and_transport_failures_are_sanitized():
    def fail(_request):
        raise httpx.ConnectError('private host and secret token')

    provider = LocalCaptionHTTP(url='http://127.0.0.1:8102', transport=httpx.MockTransport(fail))
    with pytest.raises(LocalCaptionError) as caught:
        provider.preflight()
    assert caught.value.reason_code == 'unavailable'
    assert 'secret' not in str(caught.value)

    failed = admitted(lambda request: (
        httpx.Response(200, json=HEALTHY) if request.url.path == '/health'
        else httpx.Response(503, text='private provider trace')
    ))
    image = Image.new('RGB', (2, 2))
    with pytest.raises(LocalCaptionError) as caught:
        failed.generate_caption(image)
    assert caught.value.reason_code == 'unavailable'
    assert 'private' not in str(caught.value)
    image.close()


def test_caption_response_rejects_duplicate_or_oversized_body():
    def duplicate(request):
        if request.url.path == '/health':
            return httpx.Response(200, json=HEALTHY)
        return httpx.Response(200, content=(
            b'{"caption":"one","caption":"two","provider":"qwen3-vl",'
            b'"model":"Qwen/Qwen3-VL-8B-Instruct"}'
        ))

    provider = admitted(duplicate)
    with pytest.raises(LocalCaptionError) as caught:
        provider.generate_caption(Image.new('RGB', (2, 2)))
    assert caught.value.reason_code == 'invalid_response'

    provider = admitted(lambda request: httpx.Response(
        200,
        json=HEALTHY if request.url.path == '/health' else {
            'caption': 'x' * (64 * 1024), 'provider': 'qwen3-vl', 'model': MODEL_ID,
        },
    ))
    with pytest.raises(LocalCaptionError) as caught:
        provider.generate_caption(Image.new('RGB', (2, 2)))
    assert caught.value.reason_code == 'invalid_response'


@pytest.mark.parametrize('path', ['/caption', '/translate'])
def test_response_model_drift_invalidates_admission(path):
    def handle(request):
        if request.url.path == '/health':
            return httpx.Response(200, json=HEALTHY)
        response = {'provider': 'qwen3-vl', 'model': 'Qwen/Qwen3-VL-Next'}
        response['caption' if path == '/caption' else 'translation'] = GOOD
        return httpx.Response(200, json=response)

    provider = admitted(handle)
    image = Image.new('RGB', (2, 2))
    with pytest.raises(LocalCaptionError) as caught:
        if path == '/caption':
            provider.generate_caption(image)
        else:
            provider.translate_caption('A red cup.')
    assert caught.value.reason_code == 'identity_mismatch'
    with pytest.raises(LocalCaptionError) as caught:
        provider.get_model_name()
    assert caught.value.reason_code == 'not_admitted'
    image.close()


def test_image_preparation_resizes_only_when_needed_and_preserves_caller():
    provider = admitted(lambda request: httpx.Response(200, json=HEALTHY), max_image_edge=64)
    small = Image.new('RGB', (48, 32), 'red')
    assert provider.prepare_image(small) is small
    large = Image.new('RGB', (100, 50), 'blue')
    prepared = provider.prepare_image(large)
    assert prepared is not large
    assert prepared.size == (64, 32)
    assert large.size == (100, 50)
    assert large.getpixel((0, 0)) == (0, 0, 255)
    prepared.close()
    assert large.getpixel((0, 0)) == (0, 0, 255)
    large.close()
    small.close()


def test_image_frame_and_pixel_limits_are_checked_without_allocating_large_pixels():
    class OversizedImage(Image.Image):
        @property
        def size(self):
            return (8192, 8192)

        @property
        def n_frames(self):
            return 1

    provider = admitted(lambda request: httpx.Response(200, json=HEALTHY))
    with pytest.raises(LocalCaptionError) as caught:
        provider.prepare_image(OversizedImage())
    assert caught.value.reason_code == 'invalid_input'

    class AnimatedImage(Image.Image):
        @property
        def size(self):
            return (20, 20)

        @property
        def n_frames(self):
            return 2

    with pytest.raises(LocalCaptionError) as caught:
        provider.prepare_image(AnimatedImage())
    assert caught.value.reason_code == 'invalid_input'


def test_invalid_caption_and_translation_inputs_are_rejected():
    provider = admitted(lambda request: httpx.Response(200, json=HEALTHY))
    image = Image.new('RGB', (2, 2))
    with pytest.raises(LocalCaptionError) as caught:
        provider.generate_caption(image, prompt='x' * (16 * 1024 + 1))
    assert caught.value.reason_code == 'invalid_input'
    with pytest.raises(LocalCaptionError) as caught:
        provider.translate_caption('valid', avoid_terms=['x'] * 65)
    assert caught.value.reason_code == 'invalid_input'
    image.close()


def test_compressed_provider_response_is_refused_before_decoding():
    import gzip
    provider = LocalCaptionHTTP(url='http://127.0.0.1:8102', transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={'Content-Encoding': 'gzip'},
            stream=httpx.ByteStream(gzip.compress(json.dumps(HEALTHY).encode())))))
    with pytest.raises(LocalCaptionError) as caught:
        provider.preflight()
    assert caught.value.reason_code == 'invalid_response'
