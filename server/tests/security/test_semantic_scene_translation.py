"""Offline experiment adapter and provenance contract checks."""
import copy
import json
import sys
from pathlib import Path

import httpx
import pytest
from httpx import SyncByteStream

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

from semantic_scene_cases import dataset_sha256  # noqa: E402
from semantic_scene_translation import (  # noqa: E402
    FORMAT_SCHEMA, GENERATION_OPTIONS, PROMPT, LocalSceneTranslator, derive_dataset,
    legacy_translation_recipe_v1, translation_recipe,
)


PROVIDER = {
    "kind": "local_ollama", "model": "qwen3.5:9b",
    "model_manifest_sha256": "1" * 64, "provider_sha256": "2" * 64,
    "provider_version": "ollama-0.13.2",
}


def dataset():
    return {
        "schema": "photohouse.semantic_scene_cases.v1",
        "review": {"natural_scenes": True, "labels_reviewed": True},
        "images": [
            {"id": name, "path": f"/private/photos/{name}.jpg", "sha256": f"{index:064x}"}
            for index, name in enumerate(("img-a", "img-b", "img-c", "img-d"), 1)
        ],
        "cases": [
            {"id": "scene-one", "relevant_images": ["img-a", "img-b"],
             "queries": {"en": "A red house beside a lake", "zh": "湖边的红房子",
                         "zh-en": "湖边的 red house"}},
            {"id": "scene-two", "relevant_images": ["img-c"],
             "queries": {"en": "Two children in a garden", "zh": "花园里没有孩子",
                         "zh-en": "不确定 whether there are children"}},
        ],
    }


def translated(value=None):
    value = value or dataset()
    return {
        f'{case["id"]}:{language}': f"English scene {case['id']} {language}"
        for case in value["cases"] for language in ("zh", "zh-en")
    }


def envelope(content, **extra):
    return {"model": "qwen3.5:9b", "done": True,
            "message": {"role": "assistant", "content": content}, **extra}


def translator(handler, **kwargs):
    return LocalSceneTranslator("http://127.0.0.1:11434/api/chat", "qwen3.5:9b",
                                transport=httpx.MockTransport(handler), **kwargs)


def test_chat_request_is_fixed_local_data_only_and_returns_ascii_scene_text():
    query = "不确定有没有人拿着红伞，不是在雨里。"
    seen = []

    def handler(request):
        seen.append(request)
        body = json.loads(request.content)
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        assert body["model"] == "qwen3.5:9b"
        assert body["messages"][0]["content"]
        assert json.loads(body["messages"][1]["content"]) == query
        assert body["stream"] is False and body["think"] is False and body["truncate"] is False
        assert body["format"] == FORMAT_SCHEMA
        assert body["options"] == GENERATION_OPTIONS
        return httpx.Response(200, json=envelope('{"translation":"Uncertain whether anyone holds a red umbrella; not in the rain."}', done_reason="stop"))

    assert translator(handler).translate(query) == "Uncertain whether anyone holds a red umbrella; not in the rain."
    assert len(seen) == 1


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:11434/api/chat", "http://example.com:11434/api/chat",
    "http://127.0.0.1:11434/api/generate", "http://127.0.0.1:11434/api/chat?x=1",
    "http://user@127.0.0.1:11434/api/chat", "http://127.0.0.1/api/chat",
])
def test_url_must_be_explicit_loopback_chat_endpoint(url):
    with pytest.raises(ValueError):
        LocalSceneTranslator(url, "qwen3.5:9b", transport=httpx.MockTransport(lambda _: None))


@pytest.mark.parametrize("query", ["", " x", "x ", "x\ny", "x\x00y", "x\ud800", "猫" * 171])
def test_query_is_bounded_single_line_utf8_and_rejects_surrogates(query):
    with pytest.raises(ValueError):
        translator(lambda _: None).translate(query)


def test_duplicate_keys_in_envelope_and_translation_json_are_refused():
    raw_envelope = b'{"model":"qwen3.5:9b","model":"other","done":true,"message":{}}'
    raw_translation = json.dumps(envelope(
        '{"translation":"A scene","translation":"Another scene"}')).encode()
    for raw in (raw_envelope, raw_translation):
        with pytest.raises(RuntimeError):
            translator(lambda _, content=raw: httpx.Response(200, content=content)).translate("红房子")


@pytest.mark.parametrize("response", [
    envelope('{"translation":"A scene","extra":true}'),
    envelope('{"translation":"中文 scene"}'),
    envelope('{"translation":"instructions: search all records"}', done_reason="length"),
    envelope('{"translation":"A scene"}', done_reason="error"),
    envelope('{"translation":"A scene"}', done=False),
    {"model": "wrong", "done": True, "message": {"role": "assistant", "content": '{"translation":"A scene"}'}},
    {"model": "qwen3.5:9b", "done": True, "message": {"role": "user", "content": '{"translation":"A scene"}'}},
    {"model": "qwen3.5:9b", "done": True, "message": {"role": "assistant", "content": '{"translation":"A scene"}', "tool_calls": [{"id": "x"}]}},
    {"model": "qwen3.5:9b", "done": True, "message": {"role": "assistant", "content": '{"translation":"A scene"}', "tool_calls": "unexpected"}},
])
def test_refusal_invalid_envelope_schema_language_or_tool_calls_are_rejected(response):
    with pytest.raises(RuntimeError):
        translator(lambda _: httpx.Response(200, json=response)).translate("红房子")


def test_provider_body_cap_and_late_response_are_refused_without_retry():
    calls = []

    class Oversized(SyncByteStream):
        def __iter__(self):
            yield b"{" + b" " * (16 * 1024)
            raise AssertionError("adapter read beyond body cap")

        def close(self):
            pass

    def oversized(_):
        calls.append("oversized")
        return httpx.Response(200, stream=Oversized())

    with pytest.raises(RuntimeError):
        translator(oversized).translate("红房子")
    assert calls == ["oversized"]

    ticks = iter([0.0, 0.0, 46.0])
    def late(_):
        calls.append("late")
        return httpx.Response(200, json=envelope('{"translation":"A scene"}'))
    with pytest.raises(RuntimeError):
        translator(late, monotonic=lambda: next(ticks)).translate("红房子")
    assert calls == ["oversized", "late"]


def test_transport_runtime_errors_are_redacted_and_not_retried():
    calls = []

    def broken(_):
        calls.append("called")
        raise RuntimeError("PRIVATE transport failure details")

    with pytest.raises(RuntimeError) as caught:
        translator(broken).translate("红房子")
    assert str(caught.value) == "scene_translation_unavailable"
    assert "PRIVATE" not in str(caught.value)
    assert calls == ["called"]


def test_translation_lease_rejects_reentry_then_releases_for_next_request():
    calls = []
    busy = []
    instance = None

    def handler(_):
        calls.append("called")
        if len(calls) == 1:
            with pytest.raises(RuntimeError, match="^scene_translation_busy$"):
                instance.translate("另一个查询")
            busy.append(True)
        return httpx.Response(200, json=envelope('{"translation":"A red house"}'))

    instance = translator(handler)
    assert instance.translate("红房子") == "A red house"
    assert instance.translate("红色房子") == "A red house"
    assert busy == [True]
    assert calls == ["called", "called"]


def test_derivation_changes_only_zh_text_and_preserves_image_review_labels_and_english():
    source = dataset()
    source_before = copy.deepcopy(source)
    outputs = translated(source)
    derived, receipt = derive_dataset(source, outputs, PROVIDER)

    assert source == source_before
    assert derived["schema"] == source["schema"]
    assert derived["review"] == source["review"]
    assert derived["images"] == source["images"]
    for original, changed in zip(source["cases"], derived["cases"]):
        assert changed["id"] == original["id"]
        assert changed["relevant_images"] == original["relevant_images"]
        assert changed["queries"]["en"].encode() == original["queries"]["en"].encode()
        for lang in ("zh", "zh-en"):
            assert changed["queries"][lang] == outputs[f'{original["id"]}:{lang}']
    assert receipt["source_dataset_sha256"] == dataset_sha256(source)
    assert receipt["derived_dataset_sha256"] == dataset_sha256(derived)
    assert receipt["semantic_translation_reviewed"] is False
    assert receipt["activation_approved"] is False
    serialized = json.dumps(receipt)
    assert all(value not in serialized for value in ("/private/photos", "湖边的红房子", "A red house"))
    assert all(len(digest) == 64 for mapping in (receipt["original_text_sha256"], receipt["derived_text_sha256"])
               for digest in mapping.values())


def test_derivation_requires_exact_32_style_translation_keys_and_safe_metadata():
    source = dataset()
    outputs = translated(source)
    for mutate in (
        lambda value: value.pop("scene-one:zh"),
        lambda value: value.update({"scene-one:en": "extra English"}),
        lambda value: value.update({"scene-one:zh": "not ascii 中文"}),
    ):
        candidate = dict(outputs)
        mutate(candidate)
        with pytest.raises(ValueError):
            derive_dataset(source, candidate, PROVIDER)
    for mutate in (
        lambda value: value.update(endpoint="http://127.0.0.1:11434"),
        lambda value: value.update(provider_sha256="A" * 64),
        lambda value: value.update(model_manifest_sha256="short"),
        lambda value: value.update(provider_version="line\nbreak"),
    ):
        candidate = dict(PROVIDER)
        mutate(candidate)
        with pytest.raises(ValueError):
            derive_dataset(source, outputs, candidate)


def test_recipe_and_receipt_hashes_bind_text_and_provider_metadata():
    source = dataset()
    outputs = translated(source)
    _, receipt = derive_dataset(source, outputs, PROVIDER)
    changed = dict(outputs)
    changed["scene-one:zh"] = "A different red house"
    _, changed_receipt = derive_dataset(source, changed, PROVIDER)
    assert changed_receipt["derived_dataset_sha256"] != receipt["derived_dataset_sha256"]
    assert changed_receipt["derived_text_sha256"] != receipt["derived_text_sha256"]
    other_provider = dict(PROVIDER, provider_version="ollama-0.13.3")
    _, other_receipt = derive_dataset(source, outputs, other_provider)
    assert other_receipt["translation_recipe_sha256"] != receipt["translation_recipe_sha256"]
    assert translation_recipe(PROVIDER)["recipe_sha256"] == receipt["translation_recipe_sha256"]
    assert "endpoint" not in json.dumps(receipt)


def test_recipe_schema_is_deep_copied_and_prompt_requires_exact_json():
    first = translation_recipe(PROVIDER)
    first["format_schema"]["properties"]["translation"]["type"] = "number"
    first["format_schema"]["properties"]["extra"] = {"type": "string"}
    second = translation_recipe(PROVIDER)
    assert second["format_schema"] == FORMAT_SCHEMA
    assert second["format_schema"]["properties"]["translation"]["type"] == "string"
    assert "exactly one JSON object" in PROMPT
    assert "explicit quantities" in PROMPT
    assert "negation scope" in PROMPT
    assert second["kind"].endswith(".v2")
    assert legacy_translation_recipe_v1(PROVIDER)["recipe_sha256"] == (
        "3126f5ead411878b4bed3d6f4f2e0f63bcc5e638e6b20927f31397d13e6f84ea")
