"""Explicit, bounded HTTP access to the local reviewed Qwen caption service."""
from __future__ import annotations

import io
import json
import math
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from PIL import Image


_MAX_RESPONSE_BYTES = 64 * 1024
_MAX_TEXT_BYTES = 16 * 1024
_MAX_IMAGE_BYTES = 16 * 1024 * 1024
_MAX_IMAGE_PIXELS = 64 * 1024 * 1024
_MAX_AVOID_TERMS = 64


_MESSAGES = {
    'invalid_input': 'Caption HTTP input is invalid.',
    'invalid_config': 'Caption HTTP configuration is invalid.',
    'not_admitted': 'Caption HTTP provider has not passed preflight.',
    'unavailable': 'Caption HTTP service is unavailable.',
    'invalid_response': 'Caption HTTP service returned an invalid response.',
    'identity_mismatch': 'Caption HTTP model identity changed.',
}


class LocalCaptionError(RuntimeError):
    """Fixed-reason error that never includes service or transport details."""

    def __init__(self, reason_code: str):
        if reason_code not in _MESSAGES:
            reason_code = 'unavailable'
        self.reason_code = reason_code
        super().__init__(_MESSAGES[reason_code])


def _valid_text(value: Any, maximum: int, *, nonblank: bool = True) -> bool:
    if not isinstance(value, str) or '\x00' in value:
        return False
    try:
        encoded = value.encode('utf-8', errors='strict')
    except UnicodeError:
        return False
    if len(encoded) > maximum or (nonblank and not value.strip()):
        return False
    return all(ch in '\n\t' or (ord(ch) >= 32 and not 0x7f <= ord(ch) < 0xa0) for ch in value)


def _strict_json(raw: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise ValueError('non-finite number')

    return json.loads(
        raw.decode('utf-8', errors='strict'),
        object_pairs_hook=object_pairs,
        parse_constant=reject_constant,
    )


class _BoundedBytesIO(io.BytesIO):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, data: bytes) -> int:
        end = self.tell() + len(data)
        if end > self.limit:
            raise LocalCaptionError('invalid_input')
        return super().write(data)


class LocalCaptionHTTP:
    """No-I/O-at-construction client for the explicitly configured loopback API."""

    supports_image_preparation = True
    supports_text_translation = True

    def __init__(
        self,
        *,
        url: str,
        timeout: float = 60,
        max_image_edge: int = 1536,
        expected_model_id: str = 'Qwen/Qwen3-VL-8B-Instruct',
        transport: httpx.BaseTransport | None = None,
    ):
        if not isinstance(url, str):
            raise LocalCaptionError('invalid_config') from None
        try:
            parts = urlsplit(url)
            host = parts.hostname
            port = parts.port
        except (TypeError, ValueError):
            raise LocalCaptionError('invalid_config') from None
        if (
            parts.scheme != 'http'
            or host not in {'127.0.0.1', '::1'}
            or port is None
            or not 1 <= port <= 65535
            or parts.netloc != (f'[{host}]:{port}' if host == '::1' else f'{host}:{port}')
            or parts.username is not None
            or parts.password is not None
            or parts.path not in {'', '/'}
            or parts.query
            or parts.fragment
            or '?' in url
            or '#' in url
        ):
            raise LocalCaptionError('invalid_config') from None
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or not 0 < timeout <= 120
            or type(max_image_edge) is not int
            or not 64 <= max_image_edge <= 8192
            or not _valid_text(expected_model_id, 256)
            or expected_model_id.strip() != expected_model_id
            or any(ord(ch) < 32 or 0x7f <= ord(ch) < 0xa0 for ch in expected_model_id)
            or (transport is not None and not isinstance(transport, httpx.BaseTransport))
        ):
            raise LocalCaptionError('invalid_config') from None

        self.url = f'http://[{host}]:{port}' if host == '::1' else f'http://{host}:{port}'
        self.timeout = float(timeout)
        self.max_image_edge = max_image_edge
        self.expected_model_id = expected_model_id
        self.transport = transport
        self._admitted = False

    def _client(self, *, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout if timeout is None else timeout,
            trust_env=False,
            follow_redirects=False,
            headers={'Accept-Encoding': 'identity'},
            transport=self.transport,
        )

    def _read_response(self, client: httpx.Client, method: str, path: str, **kwargs: Any) -> bytes:
        is_preflight = kwargs.pop('_preflight', False)
        request_budget = min(5.0, self.timeout) if is_preflight else self.timeout
        deadline = time.monotonic() + request_budget

        def check_deadline() -> None:
            if time.monotonic() >= deadline:
                raise LocalCaptionError('unavailable')

        try:
            with client.stream(method, self.url + path, **kwargs) as response:
                check_deadline()
                if response.status_code != 200:
                    reason = 'unavailable' if response.status_code >= 500 else 'invalid_response'
                    raise LocalCaptionError(reason)
                if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                    raise LocalCaptionError('invalid_response')
                length = response.headers.get('content-length')
                if length is not None and (not length.isascii() or not length.isdecimal()
                        or int(length) > _MAX_RESPONSE_BYTES):
                    raise LocalCaptionError('invalid_response')
                payload = bytearray()
                for chunk in response.iter_bytes(chunk_size=8192):
                    check_deadline()
                    if len(payload) + len(chunk) > _MAX_RESPONSE_BYTES:
                        raise LocalCaptionError('invalid_response')
                    payload.extend(chunk)
                    check_deadline()
            check_deadline()
            return bytes(payload)
        except LocalCaptionError:
            raise
        except httpx.HTTPError:
            raise LocalCaptionError('unavailable') from None
        except Exception:
            raise LocalCaptionError('unavailable') from None

    def _json_response(self, raw: bytes) -> dict[str, Any]:
        try:
            value = _strict_json(raw)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise LocalCaptionError('invalid_response') from None
        if not isinstance(value, dict):
            raise LocalCaptionError('invalid_response') from None
        return value

    def preflight(self) -> None:
        """Admit only a healthy, loaded Qwen3-VL backend; constructors never connect."""
        self._admitted = False
        try:
            with self._client(timeout=min(5.0, self.timeout)) as client:
                raw = self._read_response(client, 'GET', '/health', _preflight=True)
            body = self._json_response(raw)
        except LocalCaptionError:
            raise
        except Exception:
            raise LocalCaptionError('unavailable') from None
        status = body.get('status')
        if (
            body.get('model_cache_ready') is not True
            or body.get('active_provider') != 'qwen3-vl'
            or (
                status is not None
                and (not isinstance(status, str) or status not in {'healthy', 'ready', 'ok'})
            )
        ):
            raise LocalCaptionError('invalid_response') from None
        self._admitted = True

    def _require_admitted(self) -> None:
        if self._admitted is not True:
            raise LocalCaptionError('not_admitted') from None

    def _check_response_identity(self, body: dict[str, Any]) -> None:
        if body.get('provider') != 'qwen3-vl' or body.get('model') != self.expected_model_id:
            self._admitted = False
            raise LocalCaptionError('identity_mismatch') from None

    def get_model_name(self) -> str:
        self._require_admitted()
        return 'qwen3-vl-http'

    @staticmethod
    def _validate_image(image: Image.Image) -> tuple[int, int]:
        if not isinstance(image, Image.Image):
            raise LocalCaptionError('invalid_input') from None
        try:
            width, height = image.size
            frames = getattr(image, 'n_frames', 1)
        except Exception:
            raise LocalCaptionError('invalid_input') from None
        if (
            type(width) is not int
            or type(height) is not int
            or width <= 0
            or height <= 0
            or width * height > _MAX_IMAGE_PIXELS
            or frames != 1
        ):
            raise LocalCaptionError('invalid_input') from None
        return width, height

    def prepare_image(self, image: Image.Image) -> Image.Image:
        self._require_admitted()
        width, height = self._validate_image(image)
        longest = max(width, height)
        if longest <= self.max_image_edge:
            return image
        scale = self.max_image_edge / longest
        target = (max(1, round(width * scale)), max(1, round(height * scale)))
        try:
            return image.resize(target, Image.Resampling.LANCZOS)
        except Exception:
            raise LocalCaptionError('invalid_input') from None

    @staticmethod
    def _png_bytes(image: Image.Image) -> bytes:
        output = _BoundedBytesIO(_MAX_IMAGE_BYTES)
        try:
            image.save(output, format='PNG')
            return output.getvalue()
        except LocalCaptionError:
            raise
        except Exception:
            raise LocalCaptionError('invalid_input') from None
        finally:
            output.close()

    def generate_caption(self, image: Image.Image, prompt: str | None = None) -> str:
        self._require_admitted()
        self._validate_image(image)
        if prompt is not None and not _valid_text(prompt, _MAX_TEXT_BYTES):
            raise LocalCaptionError('invalid_input') from None
        png = self._png_bytes(image)
        try:
            with self._client() as client:
                raw = self._read_response(
                    client,
                    'POST',
                    '/caption',
                    files={'file': ('image.png', png, 'image/png')},
                    data={'prompt': prompt} if prompt is not None else {},
                )
            body = self._json_response(raw)
        except LocalCaptionError:
            raise
        except Exception:
            raise LocalCaptionError('unavailable') from None
        self._check_response_identity(body)
        caption = body.get('caption')
        if not _valid_text(caption, _MAX_TEXT_BYTES):
            raise LocalCaptionError('invalid_response') from None
        return caption.strip()

    def translate_caption(self, english: str, avoid_terms: list[str] | None = None) -> str:
        self._require_admitted()
        if not _valid_text(english, _MAX_TEXT_BYTES):
            raise LocalCaptionError('invalid_input') from None
        terms = [] if avoid_terms is None else avoid_terms
        if (
            not isinstance(terms, list)
            or len(terms) > _MAX_AVOID_TERMS
            or any(not _valid_text(term, 128) for term in terms)
        ):
            raise LocalCaptionError('invalid_input') from None
        payload = {
            'text': english,
            'source_lang': 'en',
            'target_lang': 'zh-CN',
            'style': 'photo caption',
            'avoid_terms': terms,
        }
        try:
            with self._client() as client:
                raw = self._read_response(client, 'POST', '/translate', json=payload)
            body = self._json_response(raw)
        except LocalCaptionError:
            raise
        except Exception:
            raise LocalCaptionError('unavailable') from None
        self._check_response_identity(body)
        translated = body.get('translation')
        if not _valid_text(translated, _MAX_TEXT_BYTES):
            raise LocalCaptionError('invalid_response') from None
        translated = translated.strip()
        if translated.upper().startswith('ZH-CN:'):
            translated = translated[6:].strip()
        if not translated:
            raise LocalCaptionError('invalid_response') from None
        return translated
