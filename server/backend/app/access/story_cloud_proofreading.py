"""Explicit-preview, one-use cloud proofreading for review-required story drafts.

This module has no route, persistence, or automatic network behavior.  Preview
only builds the exact request bytes.  A caller must separately confirm those
bytes before the configured provider is invoked.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import httpx


MAX_PREVIEWS = 64
PREVIEW_TTL_SECONDS = 600
MAX_REQUEST_BYTES = 96 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
MAX_CHAPTERS = 6
MAX_CHAPTER_BYTES = 12 * 1024
MAX_STORY_BYTES = 48 * 1024
MAX_PEOPLE = 32
MAX_NAMES_PER_PERSON = 17
MAX_PERSON_NAME_BYTES = 256
MAX_PARAGRAPH_BYTES = 6000
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
_MODEL = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z", re.ASCII)
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z", re.ASCII)
_PLACEHOLDER = re.compile(r"⟦PH_PERSON_[0-9]{4}⟧")
_PLACEHOLDER_LIKE = re.compile(
    r"(?:⟦\s*PH_PERSON_[^⟧]{0,64}⟧|(?<![A-Za-z0-9_])PH_PERSON_[A-Za-z0-9_]{1,64}(?![A-Za-z0-9_]))",
    re.IGNORECASE,
)
_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"']{3,2048}")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]{1,64}@[A-Z0-9.-]{1,253}\.[A-Z]{2,63}\b")
_LOCAL_PATH = re.compile(
    r"(?i)(?<![\w])(?:[A-Z]:\\|\\\\[^\\\s]+\\[^\\\s]+\\?)"
    r"[^\s<>\"']*|(?<![\w])/(?:Users|home|root|tmp|var|private|mnt|Volumes|opt|etc|Library|Applications)/[^\s<>\"']+"
    r"|(?<![\w])~/(?:[^\s<>\"']+)"
)
_API_KEY = re.compile(
    r"(?i)\b(?:sk-[A-Z0-9_-]{16,}|AIza[A-Z0-9_-]{20,}|"
    r"gh[pousr]_[A-Z0-9_]{20,}|github_pat_[A-Z0-9_]{20,}|"
    r"AKIA[A-Z0-9]{16}|xox[baprs]-[A-Z0-9-]{16,}|"
    r"Bearer\s+[A-Z0-9._~+/-]{16,})\b"
)
_REDACTION = {
    "url": "[URL_REMOVED]",
    "email": "[EMAIL_REMOVED]",
    "path": "[LOCAL_PATH_REMOVED]",
    "secret": "[KEY_REMOVED]",
}
_CHINESE_PROMPT = (
    "你是谨慎的家庭故事校对助手。只改进表达与可读性，保留所有事实、时间、事件、"
    "语气和章节边界；空章节必须保持为空，不得添加、猜测、总结或删减事实，"
    "不得提出新姓名或替换内容。"
    "⟦PH_PERSON_0001⟧ 形式的占位符必须逐字保留。只输出 JSON 对象 "
    "{\"paragraphs\":[\"每章一段修改后的正文，顺序与输入相同\"]}，不得增加其他字段。"
)
_ENGLISH_PROMPT = (
    "You are a careful family-story proofreader. Improve wording and readability only; "
    "preserve every fact, date, event, tone, and chapter boundary. Do not add, infer, "
    "summarize, or remove facts; keep empty chapters empty; do not suggest or replace names. Preserve tokens "
    "such as ⟦PH_PERSON_0001⟧ exactly. Return only this exact JSON shape: "
    "{\"paragraphs\":[\"one revised paragraph per input chapter in the same order\"]}; "
    "include exactly one paragraph for each input chapter and no other fields."
)
_WARNING = (
    "Review the complete request body before confirming. If confirmed, the story text "
    "shown here will be sent to the configured cloud proofreading provider. Reviewed "
    "names are replaced locally, and common URLs, email addresses, local paths, and "
    "obvious API keys are removed, but other private content may remain. The result "
    "is an unsaved draft that still needs review."
)


def _strict_json_loads(value: str) -> Any:
    def no_duplicate_keys(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    def no_nonfinite(value):
        raise ValueError("nonfinite JSON value")

    return json.loads(value, object_pairs_hook=no_duplicate_keys,
                      parse_constant=no_nonfinite)


class CloudProofreadingError(RuntimeError):
    """Closed failure category; never includes prompt, reply, endpoint, or credential."""

    def __init__(self, category: str):
        if category not in {
            "invalid_input", "preview_unavailable", "preview_expired",
            "confirmation_required", "confirmation_mismatch", "disabled",
            "provider_unavailable", "invalid_provider_response",
        }:
            category = "provider_unavailable"
        self.category = category
        super().__init__("Cloud proofreading was not completed")


def _text(value: Any, limit: int, field: str, *, nonblank: bool = False) -> str:
    if type(value) is not str:
        raise CloudProofreadingError("invalid_input")
    try:
        size = len(value.encode("utf-8", errors="strict"))
    except UnicodeEncodeError:
        raise CloudProofreadingError("invalid_input") from None
    if (size > limit or any((ord(char) < 32 or 0x7F <= ord(char) <= 0x9F)
                            and char not in "\n\t" for char in value)
            or (nonblank and not value.strip())):
        raise CloudProofreadingError("invalid_input")
    return value


def _closed_object(value: Any, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise CloudProofreadingError("invalid_input")
    return value


def _canonical_json(value: Any, limit: int) -> bytes:
    try:
        body = json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise CloudProofreadingError("invalid_input") from None
    if len(body) > limit:
        raise CloudProofreadingError("invalid_input")
    return body


def _binding(value: Any) -> dict[str, str]:
    binding = _closed_object(value, {"actor", "library", "story", "revision", "fingerprint"})
    result = {}
    for key in ("actor", "library", "story", "revision", "fingerprint"):
        result[key] = _text(binding[key], 512, "binding", nonblank=True)
    return result


def _reviewed_people(value: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if type(value) is not list or len(value) > MAX_PEOPLE:
        raise CloudProofreadingError("invalid_input")
    folded_owner: dict[str, int] = {}
    canonical_names: list[str] = []
    rules: list[tuple[str, int]] = []
    for person_index, person in enumerate(value, start=1):
        person = _closed_object(person, {"name", "aliases"})
        name = _text(person["name"], MAX_PERSON_NAME_BYTES, "reviewed name", nonblank=True)
        aliases = person["aliases"]
        if type(aliases) is not list or len(aliases) > MAX_NAMES_PER_PERSON - 1:
            raise CloudProofreadingError("invalid_input")
        names = [name]
        names.extend(_text(alias, MAX_PERSON_NAME_BYTES, "reviewed alias", nonblank=True)
                     for alias in aliases)
        if any(_PLACEHOLDER_LIKE.search(item) or "\n" in item or "\t" in item
               for item in names):
            raise CloudProofreadingError("invalid_input")
        canonical_names.append(name)
        for item in names:
            folded = item.casefold()
            owner = folded_owner.get(folded)
            if owner is not None and owner != person_index:
                raise CloudProofreadingError("invalid_input")
            folded_owner[folded] = person_index
            rules.append((item, person_index))
    # Same-person duplicate spellings are harmless; conflicting ownership was
    # rejected above. Replacements use longest-first matching.
    unique_rules: dict[str, int] = {}
    for spelling, person_index in rules:
        previous = unique_rules.get(spelling.casefold())
        if previous is not None and previous != person_index:
            raise CloudProofreadingError("invalid_input")
        unique_rules[spelling.casefold()] = person_index
    ordered = sorted(rules, key=lambda row: (-len(row[0]), row[0].casefold(), row[1]))
    normalized = []
    seen = set()
    for spelling, person_index in ordered:
        key = spelling.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append((spelling, person_index))
    reverse_map = {f"⟦PH_PERSON_{index:04d}⟧": canonical_names[index - 1]
                   for index in range(1, len(canonical_names) + 1)}
    return normalized, reverse_map


def _scrub(text: str) -> str:
    if _PLACEHOLDER_LIKE.search(text):
        raise CloudProofreadingError("invalid_input")
    text = _URL.sub(_REDACTION["url"], text)
    text = _EMAIL.sub(_REDACTION["email"], text)
    text = _LOCAL_PATH.sub(_REDACTION["path"], text)
    text = _API_KEY.sub(_REDACTION["secret"], text)
    return text


def _redact(text: str, rules: list[tuple[str, int]]) -> tuple[str, set[str]]:
    text = _scrub(text)
    placeholders: set[str] = set()
    if not rules:
        return text, placeholders
    alternatives = []
    group_to_person = {}
    for rule_index, (spelling, person_index) in enumerate(rules):
        group = f"P{rule_index:04d}"
        escaped = re.escape(spelling)
        if spelling.isascii():
            expression = f"(?ai:(?<![A-Z0-9_]){escaped}(?![A-Z0-9_]))"
        else:
            expression = f"(?i:{escaped})"
        alternatives.append(f"(?P<{group}>{expression})")
        group_to_person[group] = person_index
    pattern = re.compile("|".join(alternatives))

    def replace(match: re.Match[str]) -> str:
        person_index = group_to_person[match.lastgroup]
        placeholder = f"⟦PH_PERSON_{person_index:04d}⟧"
        placeholders.add(placeholder)
        return placeholder

    return pattern.sub(replace, text), placeholders


def _validate_story(story: Any) -> tuple[str, list[dict[str, str]]]:
    story = _closed_object(story, {"title", "chapters"})
    title = _text(story["title"], 4096, "story title")
    chapters = story["chapters"]
    if type(chapters) is not list or not 1 <= len(chapters) <= MAX_CHAPTERS:
        raise CloudProofreadingError("invalid_input")
    checked = []
    total = 0
    ids = set()
    for chapter in chapters:
        chapter = _closed_object(chapter, {"id", "title", "narration"})
        ident = _text(chapter["id"], 256, "chapter id", nonblank=True)
        chapter_title = _text(chapter["title"], 1024, "chapter title")
        narration = _text(chapter["narration"], MAX_CHAPTER_BYTES,
                          "chapter narration")
        if ident in ids:
            raise CloudProofreadingError("invalid_input")
        ids.add(ident)
        total += len(narration.encode("utf-8"))
        checked.append({"id": ident, "title": chapter_title, "narration": narration})
    if total > MAX_STORY_BYTES:
        raise CloudProofreadingError("invalid_input")
    if not any(chapter["narration"].strip() for chapter in checked):
        raise CloudProofreadingError("invalid_input")
    return title, checked


def _provider_descriptor(provider: Any) -> tuple[str, str, bool, str]:
    if provider is None:
        return "DeepSeek", "deepseek-flash", False, DEEPSEEK_ENDPOINT
    provider_name = getattr(provider, "provider_name", "DeepSeek")
    model = getattr(provider, "model", None)
    endpoint = getattr(provider, "endpoint", DEEPSEEK_ENDPOINT)
    if (provider_name != "DeepSeek" or type(model) is not str
            or not _MODEL.fullmatch(model) or endpoint != DEEPSEEK_ENDPOINT
            or not callable(getattr(provider, "send", None))):
        raise CloudProofreadingError("invalid_input")
    return "DeepSeek", model, True, endpoint


@dataclass
class _Preview:
    binding: dict[str, str]
    request_body: bytes
    request_sha256: str
    expires_at: float
    reverse_map: dict[str, str]
    chapter_placeholders: list[set[str]]
    chapter_was_nonblank: list[bool]
    story_title: str
    chapter_ids: list[str]
    provider: Any
    provider_name: str
    model: str
    provider_endpoint: str
    enabled_at_preview: bool


class CloudProofreading:
    """Build reviewable request previews and consume each accepted preview once.

    Route integration should call ``preview`` with the current actor/library/
    story/revision/fingerprint binding, display ``request_body`` verbatim, and
    call ``confirm`` only after explicit user consent with that same binding and
    displayed SHA-256. Authentication freshness, route authorization, storage,
    and draft adoption remain the caller's responsibility; this class performs
    none of those actions.
    """

    def __init__(self, *, enabled: bool = False, provider: Any = None,
                 clock: Callable[[], float] = time.time):
        if type(enabled) is not bool or not callable(clock):
            raise ValueError("invalid_input")
        _provider_descriptor(provider)
        self._enabled = enabled
        self._provider = provider
        self._clock = clock
        self._lock = threading.Lock()
        self._previews: dict[str, _Preview] = {}

    def preview(self, binding: Any, story: Any, people: Any) -> dict[str, Any]:
        provider = self._provider
        enabled = self._enabled
        binding_copy = _binding(binding)
        title, chapters = _validate_story(story)
        rules, reverse_map = _reviewed_people(people)
        outbound_chapters = []
        chapter_placeholders = []
        chapter_was_nonblank = []
        for chapter in chapters:
            redacted, placeholders = _redact(chapter["narration"], rules)
            outbound_chapters.append({"narration": redacted})
            chapter_placeholders.append(placeholders)
            chapter_was_nonblank.append(bool(chapter["narration"].strip()))
        provider_name, model, configured, provider_endpoint = _provider_descriptor(provider)
        system = _CHINESE_PROMPT + "\n\n" + _ENGLISH_PROMPT
        request = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(
                    {"chapters": outbound_chapters}, ensure_ascii=False,
                    allow_nan=False, separators=(",", ":"))},
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
            "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
        }
        request_body = _canonical_json(request, MAX_REQUEST_BYTES)
        digest = hashlib.sha256(request_body).hexdigest()
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise CloudProofreadingError("preview_unavailable")
        preview_id = str(uuid.uuid4())
        record = _Preview(
            binding=binding_copy, request_body=request_body,
            request_sha256=digest, expires_at=now + PREVIEW_TTL_SECONDS,
            reverse_map=reverse_map, chapter_placeholders=chapter_placeholders,
            chapter_was_nonblank=chapter_was_nonblank,
            story_title=title, chapter_ids=[chapter["id"] for chapter in chapters],
            provider=provider, provider_name=provider_name, model=model,
            provider_endpoint=provider_endpoint, enabled_at_preview=enabled,
        )
        with self._lock:
            if self._provider is not provider or self._enabled is not enabled:
                raise CloudProofreadingError("preview_unavailable")
            self._expire_locked(now)
            if len(self._previews) >= MAX_PREVIEWS:
                raise CloudProofreadingError("preview_unavailable")
            self._previews[preview_id] = record
        return {
            "schema": "photohouse.private.story_cloud_proofreading_preview.v1",
            "preview_id": preview_id,
            "expires_in_seconds": PREVIEW_TTL_SECONDS,
            "enabled": enabled,
            "configured": configured,
            "provider": provider_name,
            "model": model,
            "endpoint": provider_endpoint,
            "request_body": request_body.decode("utf-8", errors="strict"),
            "request_sha256": digest,
            "warning": _WARNING,
        }

    def confirm(self, preview_id: Any, binding: Any, sha256: Any,
                confirmed: Any = False) -> dict[str, Any]:
        if confirmed is not True:
            raise CloudProofreadingError("confirmation_required")
        if not self._enabled or self._provider is None:
            raise CloudProofreadingError("disabled")
        binding_copy = _binding(binding)
        if type(preview_id) is not str or type(sha256) is not str or not _SHA256.fullmatch(sha256):
            raise CloudProofreadingError("confirmation_mismatch")
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise CloudProofreadingError("preview_unavailable")
        with self._lock:
            record = self._previews.get(preview_id)
            if record is None:
                raise CloudProofreadingError("preview_unavailable")
            if now >= record.expires_at:
                del self._previews[preview_id]
                raise CloudProofreadingError("preview_expired")
            if binding_copy != record.binding or sha256 != record.request_sha256:
                raise CloudProofreadingError("confirmation_mismatch")
            try:
                provider_name, model, configured, provider_endpoint = _provider_descriptor(self._provider)
            except CloudProofreadingError:
                del self._previews[preview_id]
                raise CloudProofreadingError("confirmation_mismatch") from None
            if (not self._enabled or not record.enabled_at_preview
                    or self._provider is not record.provider
                    or not configured or provider_name != record.provider_name
                    or model != record.model or provider_endpoint != record.provider_endpoint):
                del self._previews[preview_id]
                raise CloudProofreadingError("confirmation_mismatch")
            # Consume under the lock before any provider operation. Concurrent
            # confirmations can therefore produce at most one send.
            del self._previews[preview_id]
        try:
            reply = record.provider.send(record.request_body)
        except CloudProofreadingError:
            raise
        except Exception:
            raise CloudProofreadingError("provider_unavailable") from None
        paragraphs = self._validated_paragraphs(reply, record)
        chapters = [{"id": ident, "narration": narration}
                    for ident, narration in zip(record.chapter_ids, paragraphs)]
        return {
            "version": 1,
            "title": record.story_title,
            "chapters": chapters,
            "needs_review": True,
            "saved": False,
        }

    def _expire_locked(self, now: float) -> None:
        for preview_id, record in list(self._previews.items()):
            if now >= record.expires_at:
                del self._previews[preview_id]

    @staticmethod
    def _validated_paragraphs(reply: Any, record: _Preview) -> list[str]:
        if type(reply) is not dict or set(reply) != {"paragraphs"}:
            raise CloudProofreadingError("invalid_provider_response")
        paragraphs = reply["paragraphs"]
        if type(paragraphs) is not list or len(paragraphs) != len(record.chapter_ids):
            raise CloudProofreadingError("invalid_provider_response")
        restored = []
        for paragraph, required, original_nonblank in zip(
                paragraphs, record.chapter_placeholders, record.chapter_was_nonblank):
            try:
                paragraph = _text(paragraph, MAX_PARAGRAPH_BYTES,
                                  "proofread paragraph", nonblank=original_nonblank)
            except CloudProofreadingError:
                raise CloudProofreadingError("invalid_provider_response") from None
            if not original_nonblank and paragraph != "":
                raise CloudProofreadingError("invalid_provider_response")
            found = set(_PLACEHOLDER.findall(paragraph))
            all_reserved = _PLACEHOLDER_LIKE.findall(paragraph)
            if (all_reserved != _PLACEHOLDER.findall(paragraph)
                    or found - required or not required.issubset(found)):
                raise CloudProofreadingError("invalid_provider_response")
            if any(pattern.search(paragraph) for pattern in (_URL, _EMAIL, _LOCAL_PATH, _API_KEY)):
                raise CloudProofreadingError("invalid_provider_response")
            restored.append(_PLACEHOLDER.sub(
                lambda match: record.reverse_map[match.group(0)], paragraph))
        return restored


class DeepSeekProofreader:
    """Single-request DeepSeek chat-completions provider with a fixed endpoint."""

    provider_name = "DeepSeek"
    endpoint = DEEPSEEK_ENDPOINT
    __slots__ = ("_api_key", "_model")

    def __init__(self, *, api_key: str, model: str):
        if (type(api_key) is not str or not api_key or len(api_key) > 4096
                or not api_key.isascii() or any(not 33 <= ord(char) <= 126 for char in api_key)
                or type(model) is not str or not _MODEL.fullmatch(model)):
            raise ValueError("invalid_input")
        self._api_key = api_key
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def __repr__(self) -> str:
        return f"DeepSeekProofreader(model={self.model!r}, api_key=[redacted])"

    def send(self, body: bytes) -> dict[str, list[str]]:
        if type(body) is not bytes or not 0 < len(body) <= MAX_REQUEST_BYTES:
            raise CloudProofreadingError("invalid_provider_response")
        try:
            request = _strict_json_loads(body.decode("utf-8", errors="strict"))
            if (type(request) is not dict or request.get("model") != self.model
                    or set(request) != {"model", "messages", "temperature", "max_tokens",
                                        "stream", "response_format", "thinking"}):
                raise ValueError
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=45.0) as client:
                with client.stream(
                    "POST", DEEPSEEK_ENDPOINT,
                    headers={"Authorization": f"Bearer {self._api_key}",
                             "Content-Type": "application/json"},
                    content=body,
                ) as response:
                    if response.status_code != 200:
                        raise CloudProofreadingError("provider_unavailable")
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise CloudProofreadingError("invalid_provider_response")
                        chunks.append(chunk)
        except CloudProofreadingError:
            raise
        except Exception:
            raise CloudProofreadingError("provider_unavailable") from None
        try:
            envelope = _strict_json_loads(b"".join(chunks).decode("utf-8", errors="strict"))
            if (type(envelope) is not dict or type(envelope.get("choices")) is not list
                    or len(envelope["choices"]) != 1 or "tool_calls" in envelope):
                raise ValueError
            choice = envelope["choices"][0]
            if type(choice) is not dict or choice.get("finish_reason") != "stop":
                raise ValueError
            message = choice.get("message")
            if type(message) is not dict or "tool_calls" in message or "function_call" in message:
                raise ValueError
            content = message.get("content")
            if type(content) is not str or len(content.encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise ValueError
            decoded = _strict_json_loads(content)
            if type(decoded) is not dict or set(decoded) != {"paragraphs"}:
                raise ValueError
            return decoded
        except Exception:
            raise CloudProofreadingError("invalid_provider_response") from None
