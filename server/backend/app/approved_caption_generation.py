"""Bounded provider-neutral generation for reviewed bilingual captions."""
from __future__ import annotations

from typing import Any

from PIL import Image

from .caption_policy import (
    DEFAULT_DETAILED_CAPTION_PROMPT,
    build_caption_retry_prompt,
    bilingual_caption_issues,
    correct_chinese_policy_translation,
    neutralize_person_terms,
    parse_bilingual_caption,
    truncate_caption_text,
)


_MAX_CAPTION_BYTES = 16 * 1024
_REASON_MESSAGES = {
    'invalid_input': 'Caption generation input is invalid.',
    'provider_identity': 'Caption provider identity did not match the reviewed model.',
    'provider_error': 'Caption provider operation failed.',
    'invalid_output': 'Caption provider returned invalid text.',
    'policy_refused': 'Caption output did not pass bilingual policy.',
}


class CaptionGenerationRefused(ValueError):
    """A safe, fixed-reason refusal with no provider exception details."""

    def __init__(self, reason_code: str):
        if reason_code not in _REASON_MESSAGES:
            reason_code = 'provider_error'
        self.reason_code = reason_code
        super().__init__(_REASON_MESSAGES[reason_code])


def _operation_error(error: Exception) -> CaptionGenerationRefused:
    # Adapters may supply only these fixed reason identifiers. Never include
    # provider exception text or HTTP response bodies in an operator result.
    reason = getattr(error, 'reason_code', None)
    if reason in {'identity_mismatch', 'not_admitted'}:
        return CaptionGenerationRefused('provider_identity')
    if reason == 'invalid_response':
        return CaptionGenerationRefused('invalid_output')
    return CaptionGenerationRefused('provider_error')


def _check_text(value: Any) -> str:
    if (not isinstance(value, str) or not value.strip() or '\x00' in value
            or any(ch not in '\n\t' and (ord(ch) < 32 or 0x7f <= ord(ch) < 0xa0) for ch in value)):
        raise CaptionGenerationRefused('invalid_output')
    try:
        encoded = value.encode('utf-8', errors='strict')
    except UnicodeError:
        raise CaptionGenerationRefused('invalid_output') from None
    if len(encoded) > _MAX_CAPTION_BYTES:
        raise CaptionGenerationRefused('invalid_output')
    return value


def _provider_model(provider: Any, expected_model: str) -> str:
    try:
        actual = provider.get_model_name()
    except CaptionGenerationRefused:
        raise
    except Exception:
        raise CaptionGenerationRefused('provider_error') from None
    if not isinstance(actual, str) or actual != expected_model:
        raise CaptionGenerationRefused('provider_identity')
    return actual


def generate_caption_result(
    image: Image.Image,
    *,
    provider: Any,
    expected_model: str = 'qwen3-vl-http',
    max_policy_retries: int = 2,
    word_limit: int = 120,
) -> dict[str, str]:
    """Generate a validated bilingual caption with at most three visual calls.

    The caller retains ownership of ``image``. A distinct image returned by an
    explicitly enabled provider preparation hook is owned and closed here.
    """
    if (
        not isinstance(image, Image.Image)
        or not isinstance(expected_model, str)
        or not expected_model
        or type(max_policy_retries) is not int
        or max_policy_retries < 0
        or type(word_limit) is not int
        or word_limit < 0
    ):
        raise CaptionGenerationRefused('invalid_input')
    retries = min(max_policy_retries, 2)
    if not callable(getattr(provider, 'get_model_name', None)) or not callable(
        getattr(provider, 'generate_caption', None)
    ):
        raise CaptionGenerationRefused('invalid_input')

    model = _provider_model(provider, expected_model)
    caption_image = image
    prepared_image = None
    try:
        if getattr(provider, 'supports_image_preparation', False) is True:
            prepare = getattr(provider, 'prepare_image', None)
            if not callable(prepare):
                raise CaptionGenerationRefused('invalid_input')
            try:
                prepared_image = prepare(image)
            except Exception as error:
                raise _operation_error(error) from None
            if not isinstance(prepared_image, Image.Image):
                raise CaptionGenerationRefused('invalid_input')
            caption_image = prepared_image

        prompt = DEFAULT_DETAILED_CAPTION_PROMPT

        def generate(active_prompt: str) -> str:
            nonlocal model
            model = _provider_model(provider, expected_model)
            try:
                result = provider.generate_caption(caption_image, prompt=active_prompt)
            except Exception as error:
                raise _operation_error(error) from None
            _provider_model(provider, expected_model)
            return _check_text(result)

        text = _check_text(neutralize_person_terms(generate(prompt)))
        if word_limit:
            text = _check_text(truncate_caption_text(text, word_limit))
        issues = bilingual_caption_issues(text)
        supports_translation = getattr(provider, 'supports_text_translation', False) is True

        for retry_index in range(retries):
            if not issues:
                break
            translated = None
            if retry_index == 0 and issues == ['chinese_policy'] and parse_bilingual_caption(text) and supports_translation:
                translate = getattr(provider, 'translate_caption', None)
                if callable(translate):
                    def bounded_translate(english: str, avoid_terms: list[str]) -> str:
                        _provider_model(provider, expected_model)
                        try:
                            translated_text = translate(english, avoid_terms=avoid_terms)
                        except Exception as error:
                            raise _operation_error(error) from None
                        _provider_model(provider, expected_model)
                        return _check_text(translated_text)

                    translated = correct_chinese_policy_translation(text, bounded_translate)
                    if translated is not None:
                        translated = _check_text(translated)

            if translated is None:
                retry_prompt = build_caption_retry_prompt(prompt, issues, text.encode('utf-8')[:6000].decode('utf-8', errors='ignore'))
                text = generate(retry_prompt)
            else:
                text = translated
            text = _check_text(neutralize_person_terms(text))
            if word_limit:
                text = _check_text(truncate_caption_text(text, word_limit))
            issues = bilingual_caption_issues(text)

        if issues:
            raise CaptionGenerationRefused('policy_refused')

        bilingual = parse_bilingual_caption(text)
        if bilingual and 'zh-cn' not in model.lower():
            model = f'{model}|bilingual-en-zh-cn'
        return {
            'text': text,
            'model': model,
            'model_version': 'bilingual-v1',
            'quality_tier': 'balanced',
        }
    except CaptionGenerationRefused:
        raise
    except Exception:
        # Keep unexpected provider-adjacent errors from exposing private details.
        raise CaptionGenerationRefused('provider_error') from None
    finally:
        if prepared_image is not None and prepared_image is not image:
            try:
                prepared_image.close()
            except Exception:
                pass
