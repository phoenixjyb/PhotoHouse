"""Provider-neutral approved-caption generation using synthetic images only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from PIL import Image
import pytest

from app.approved_caption_generation import (
    CaptionGenerationRefused,
    generate_caption_result,
)


GOOD = 'EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子放在木桌上。'
CHINESE_POLICY = 'EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子可能放在木桌上。'
ENGLISH_POLICY = 'EN: A person is possibly holding a red cup.\n\nZH-CN: 一个人拿着一个红色杯子。'


class Provider:
    def __init__(self, outputs=(), *, model='qwen3-vl-http'):
        self.outputs = iter(outputs)
        self.model = model
        self.prompts = []
        self.translate_calls = []

    def get_model_name(self):
        return self.model

    def generate_caption(self, image, prompt=None):
        self.prompts.append(prompt)
        output = next(self.outputs)
        if isinstance(output, BaseException):
            raise output
        return output


def test_good_bilingual_result_has_existing_marker_and_contract():
    provider = Provider([GOOD])
    image = Image.new('RGB', (8, 8), 'red')
    result = generate_caption_result(image, provider=provider)
    assert result == {
        'text': GOOD,
        'model': 'qwen3-vl-http|bilingual-en-zh-cn',
        'model_version': 'bilingual-v1',
        'quality_tier': 'balanced',
    }
    assert len(provider.prompts) == 1
    assert image.getpixel((0, 0)) == (255, 0, 0)
    image.close()


def test_policy_corrections_are_bounded_and_neutralize_person_terms():
    provider = Provider([ENGLISH_POLICY, GOOD, GOOD, GOOD])
    result = generate_caption_result(Image.new('RGB', (2, 2)), provider=provider)
    assert result['text'] == GOOD
    assert len(provider.prompts) == 2
    assert len(provider.prompts[1]) > len(provider.prompts[0])


def test_unresolved_policy_refusal_stops_after_three_generation_calls():
    provider = Provider([ENGLISH_POLICY] * 5)
    with pytest.raises(CaptionGenerationRefused) as caught:
        generate_caption_result(Image.new('RGB', (2, 2)), provider=provider)
    assert caught.value.reason_code == 'policy_refused'
    assert str(caught.value) == 'Caption output did not pass bilingual policy.'
    assert len(provider.prompts) == 3


def test_chinese_only_policy_failure_uses_optional_translation_first():
    class TranslatingProvider(Provider):
        supports_text_translation = True

        def translate_caption(self, english, *, avoid_terms):
            self.translate_calls.append((english, avoid_terms))
            return '一个红色杯子放在木桌上。'

    provider = TranslatingProvider([CHINESE_POLICY])
    result = generate_caption_result(Image.new('RGB', (2, 2)), provider=provider)
    assert result['text'] == GOOD
    assert len(provider.translate_calls) == 1
    assert len(provider.prompts) == 1


@pytest.mark.parametrize('output', [
    'x' * (16 * 1024 + 1),
    'EN: A cup.\x00\n\nZH-CN: 一个杯子。',
    b'EN: A cup.',
    None,
])
def test_forbidden_or_invalid_provider_text_is_refused_without_leaking(output):
    provider = Provider([output])
    with pytest.raises(CaptionGenerationRefused) as caught:
        generate_caption_result(Image.new('RGB', (2, 2)), provider=provider)
    assert caught.value.reason_code == 'invalid_output'
    assert 'possibly' not in str(caught.value)
    assert 'EN: A cup' not in str(caught.value)


def test_forbidden_caption_is_retried_then_refused():
    forbidden = 'EN: A person is possibly outside.\n\nZH-CN: 一个人在外面。'
    provider = Provider([forbidden] * 3)
    with pytest.raises(CaptionGenerationRefused) as caught:
        generate_caption_result(Image.new('RGB', (2, 2)), provider=provider)
    assert caught.value.reason_code == 'policy_refused'
    assert len(provider.prompts) == 3
    assert 'possibly' not in str(caught.value)


def test_provider_exception_text_is_not_exposed():
    provider = Provider([RuntimeError('private endpoint token=secret')])
    with pytest.raises(CaptionGenerationRefused) as caught:
        generate_caption_result(Image.new('RGB', (2, 2)), provider=provider)
    assert caught.value.reason_code == 'provider_error'
    assert 'secret' not in str(caught.value)


def test_identity_must_match_before_generation_and_remain_stable():
    class DriftingProvider(Provider):
        def __init__(self):
            super().__init__([GOOD])
            self.lookups = 0

        def get_model_name(self):
            self.lookups += 1
            return 'qwen3-vl-http' if self.lookups == 1 else 'other-model'

    provider = DriftingProvider()
    with pytest.raises(CaptionGenerationRefused) as caught:
        generate_caption_result(Image.new('RGB', (2, 2)), provider=provider)
    assert caught.value.reason_code == 'provider_identity'
    assert provider.prompts == []


def test_prepared_image_is_closed_but_caller_image_remains_open(monkeypatch):
    closed = []
    original_close = Image.Image.close

    def track_close(image):
        closed.append(image)
        return original_close(image)

    monkeypatch.setattr(Image.Image, 'close', track_close)

    class PreparingProvider(Provider):
        supports_image_preparation = True

        def prepare_image(self, image):
            self.prepared = Image.new('RGB', image.size, 'blue')
            return self.prepared

        def generate_caption(self, image, prompt=None):
            assert image is self.prepared
            return super().generate_caption(image, prompt)

    provider = PreparingProvider([GOOD])
    source = Image.new('RGB', (2, 2), 'red')
    generate_caption_result(source, provider=provider)
    assert source.getpixel((0, 0)) == (255, 0, 0)
    assert closed == [provider.prepared]
    source.getpixel((0, 0))


def test_disabled_image_preparation_hook_is_not_called():
    class UnadvertisedProvider(Provider):
        def prepare_image(self, image):
            raise AssertionError('must not be called')

    result = generate_caption_result(Image.new('RGB', (2, 2)), provider=UnadvertisedProvider([GOOD]))
    assert result['text'] == GOOD



@pytest.mark.parametrize('output', ['', '   ', '\ud800'])
def test_empty_and_non_utf8_text_is_refused_without_policy_retry(output):
    provider = Provider([output])
    with Image.new('RGB', (2, 2)) as image, pytest.raises(CaptionGenerationRefused) as caught:
        generate_caption_result(image, provider=provider)
    assert caught.value.reason_code == 'invalid_output'
    assert len(provider.prompts) == 1


def test_negative_retry_setting_does_not_call_provider():
    provider = Provider([GOOD])
    with Image.new('RGB', (2, 2)) as image, pytest.raises(CaptionGenerationRefused) as caught:
        generate_caption_result(image, provider=provider, max_policy_retries=-1)
    assert caught.value.reason_code == 'invalid_input'
    assert provider.prompts == []
