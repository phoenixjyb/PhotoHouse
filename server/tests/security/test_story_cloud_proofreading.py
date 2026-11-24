"""Local security tests for exact-preview, one-use cloud proofreading."""
from __future__ import annotations

import hashlib
import json
import threading
import unittest
from unittest.mock import patch

from app.access.story_cloud_proofreading import (
    CloudProofreading,
    CloudProofreadingError,
    DeepSeekProofreader,
)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeProvider:
    provider_name = "DeepSeek"
    model = "test-model"

    def __init__(self, reply=None):
        self.reply = reply or {"paragraphs": ["已校对 ⟦PH_PERSON_0001⟧。"]}
        self.bodies = []

    def send(self, body):
        self.bodies.append(body)
        return self.reply


def binding():
    return {"actor": "actor-private", "library": "library-private",
            "story": "story-private", "revision": "9",
            "fingerprint": "opaque-fingerprint"}


def story():
    return {
        "title": "Private title should stay local",
        "chapters": [{
            "id": "chapter-private-id",
            "title": "Private chapter title",
            "narration": (
                "Mira and 小宁 went home. Contact me at family@example.test, "
                "see https://example.test/path, open C:\\Users\\Family\\note.txt, "
                "and key sk-abcdefghijklmnop1234567890."
            ),
        }],
    }


class CloudProofreadingTests(unittest.TestCase):
    def people(self):
        return [{"name": "小宁", "aliases": ["Mira"]}]

    def test_preview_is_offline_exact_and_excludes_non_narration_context(self):
        clock = Clock()
        default_preview = CloudProofreading(clock=clock).preview(binding(), story(), self.people())
        self.assertFalse(default_preview["enabled"])
        self.assertFalse(default_preview["configured"])
        self.assertEqual(("DeepSeek", "deepseek-flash"),
                         (default_preview["provider"], default_preview["model"]))
        self.assertEqual("https://api.deepseek.com/chat/completions", default_preview["endpoint"])
        provider = FakeProvider()
        service = CloudProofreading(enabled=False, provider=provider, clock=clock)
        preview = service.preview(binding(), story(), self.people())

        self.assertFalse(preview["enabled"])
        self.assertTrue(preview["configured"])
        self.assertEqual("DeepSeek", preview["provider"])
        self.assertEqual("test-model", preview["model"])
        self.assertEqual("https://api.deepseek.com/chat/completions", preview["endpoint"])
        self.assertIn("other private content may remain", preview["warning"])
        body = preview["request_body"].encode("utf-8")
        self.assertEqual(hashlib.sha256(body).hexdigest(), preview["request_sha256"])
        decoded = json.loads(body)
        self.assertEqual({"model", "messages", "temperature", "max_tokens", "stream",
                          "response_format", "thinking"}, set(decoded))
        self.assertEqual("test-model", decoded["model"])
        self.assertFalse(decoded["stream"])
        self.assertEqual({"type": "json_object"}, decoded["response_format"])
        self.assertEqual({"type": "disabled"}, decoded["thinking"])
        system_prompt = decoded["messages"][0]["content"]
        self.assertIn('{"paragraphs":["one revised paragraph per input chapter in the same order"]}',
                      system_prompt)
        self.assertIn('不得增加其他字段', system_prompt)
        content = json.loads(decoded["messages"][1]["content"])
        self.assertEqual({"chapters"}, set(content))
        self.assertEqual({"narration"}, set(content["chapters"][0]))
        outbound = content["chapters"][0]["narration"]
        self.assertIn("⟦PH_PERSON_0001⟧", outbound)
        for private in ("Mira", "小宁", "Private title", "Private chapter", "chapter-private-id",
                        "actor-private", "library-private", "story-private", "example.test",
                        "family@example.test", "C:\\Users\\Family", "sk-abcdefghijklmnop"):
            self.assertNotIn(private, body.decode("utf-8"))
        self.assertIn("[URL_REMOVED]", outbound)
        self.assertIn("[EMAIL_REMOVED]", outbound)
        self.assertIn("[LOCAL_PATH_REMOVED]", outbound)
        self.assertIn("[KEY_REMOVED]", outbound)
        self.assertEqual([], provider.bodies)
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"])
        self.assertEqual("confirmation_required", caught.exception.category)
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("disabled", caught.exception.category)
        self.assertEqual([], provider.bodies)

    def test_ascii_alias_redaction_uses_word_boundaries_and_longest_first(self):
        service = CloudProofreading(clock=Clock())
        value = story()
        value["chapters"][0]["narration"] = (
            "Anniversary was fun. Ann visited with Ann Smith."
        )
        preview = service.preview(binding(), value, [
            {"name": "Ann Smith", "aliases": ["Ann"]},
        ])
        body = json.loads(preview["request_body"])
        text = json.loads(body["messages"][1]["content"])["chapters"][0]["narration"]
        self.assertIn("Anniversary", text)
        self.assertEqual(2, text.count("⟦PH_PERSON_0001⟧"))
        self.assertNotIn("Ann Smith", text)

    def test_empty_chapters_keep_their_position_and_must_remain_empty(self):
        value = story()
        value["chapters"] = [
            {"id": "chapter-one", "title": "One", "narration": "Mira visited."},
            {"id": "chapter-two", "title": "Two", "narration": ""},
            {"id": "chapter-three", "title": "Three", "narration": "小宁 waved."},
        ]
        provider = FakeProvider({"paragraphs": [
            "⟦PH_PERSON_0001⟧ visited.", "", "⟦PH_PERSON_0001⟧ waved."]})
        service = CloudProofreading(enabled=True, provider=provider, clock=Clock())
        preview = service.preview(binding(), value, self.people())
        body = json.loads(preview["request_body"])
        chapters = json.loads(body["messages"][1]["content"])["chapters"]
        self.assertEqual(["⟦PH_PERSON_0001⟧ visited.", "", "⟦PH_PERSON_0001⟧ waved."],
                         [chapter["narration"] for chapter in chapters])
        self.assertIn("keep empty chapters empty", body["messages"][0]["content"])
        result = service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                                 confirmed=True)
        self.assertEqual(["chapter-one", "chapter-two", "chapter-three"],
                         [chapter["id"] for chapter in result["chapters"]])
        self.assertEqual(["小宁 visited.", "", "小宁 waved."],
                         [chapter["narration"] for chapter in result["chapters"]])

        blank_story = dict(value, chapters=[
            {"id": "empty-one", "title": "", "narration": ""},
            {"id": "empty-two", "title": "", "narration": "  \n"},
        ])
        with self.assertRaises(CloudProofreadingError):
            service.preview(binding(), blank_story, self.people())

    def test_confirm_sends_preview_bytes_once_and_restores_names_locally(self):
        provider = FakeProvider()
        service = CloudProofreading(enabled=True, provider=provider, clock=Clock())
        source_story = story()
        preview = service.preview(binding(), source_story, self.people())
        body = preview["request_body"].encode("utf-8")
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), "0" * 64, confirmed=True)
        self.assertEqual("confirmation_mismatch", caught.exception.category)
        self.assertEqual([], provider.bodies)

        result = service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                                 confirmed=True)
        self.assertEqual([body], provider.bodies)
        self.assertEqual({"version", "title", "chapters", "needs_review", "saved"}, set(result))
        self.assertEqual(source_story["title"], result["title"])
        self.assertEqual(source_story["chapters"][0]["id"], result["chapters"][0]["id"])
        self.assertIn("小宁", result["chapters"][0]["narration"])
        self.assertNotIn("⟦PH_PERSON_0001⟧", result["chapters"][0]["narration"])
        self.assertTrue(result["needs_review"])
        self.assertFalse(result["saved"])
        with self.assertRaises(CloudProofreadingError):
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual(1, len(provider.bodies))

    def test_confirmation_is_bound_expires_and_is_atomically_one_use(self):
        clock = Clock()
        entered = threading.Event()
        release = threading.Event()

        class BlockingProvider(FakeProvider):
            def send(self, body):
                self.bodies.append(body)
                entered.set()
                release.wait(2)
                return self.reply

        provider = BlockingProvider()
        service = CloudProofreading(enabled=True, provider=provider, clock=clock)
        preview = service.preview(binding(), story(), self.people())
        wrong_binding = dict(binding(), revision="10")
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], wrong_binding, preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("confirmation_mismatch", caught.exception.category)
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=False)
        self.assertEqual("confirmation_required", caught.exception.category)

        results = []
        first = threading.Thread(target=lambda: results.append(
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)))
        first.start()
        self.assertTrue(entered.wait(1))
        with self.assertRaises(CloudProofreadingError):
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        release.set()
        first.join(2)
        self.assertFalse(first.is_alive())
        self.assertEqual(1, len(provider.bodies))
        self.assertEqual(1, len(results))

        expiring = CloudProofreading(enabled=True, provider=FakeProvider(), clock=clock)
        expired = expiring.preview(binding(), story(), self.people())
        clock.now += 601
        with self.assertRaises(CloudProofreadingError) as caught:
            expiring.confirm(expired["preview_id"], binding(), expired["request_sha256"],
                             confirmed=True)
        self.assertEqual("preview_expired", caught.exception.category)

    def test_changed_provider_model_and_provider_failures_consume_without_retry(self):
        provider = FakeProvider()
        service = CloudProofreading(enabled=True, provider=provider, clock=Clock())
        preview = service.preview(binding(), story(), self.people())
        provider.model = "changed-model"
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("confirmation_mismatch", caught.exception.category)
        self.assertEqual([], provider.bodies)
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("preview_unavailable", caught.exception.category)

        original_provider = FakeProvider()
        replacement_provider = FakeProvider()
        service = CloudProofreading(enabled=True, provider=original_provider, clock=Clock())
        preview = service.preview(binding(), story(), self.people())
        service._provider = replacement_provider
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("confirmation_mismatch", caught.exception.category)
        self.assertEqual([], original_provider.bodies)
        self.assertEqual([], replacement_provider.bodies)

        endpoint_provider = FakeProvider()
        service = CloudProofreading(enabled=True, provider=endpoint_provider, clock=Clock())
        preview = service.preview(binding(), story(), self.people())
        endpoint_provider.endpoint = "https://changed.invalid/"
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("confirmation_mismatch", caught.exception.category)
        self.assertEqual([], endpoint_provider.bodies)

        class FailingProvider(FakeProvider):
            def send(self, body):
                self.bodies.append(body)
                raise RuntimeError("private reply and key must not escape")

        failing = FailingProvider()
        service = CloudProofreading(enabled=True, provider=failing, clock=Clock())
        preview = service.preview(binding(), story(), self.people())
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("provider_unavailable", caught.exception.category)
        self.assertNotIn("private reply", str(caught.exception))
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("preview_unavailable", caught.exception.category)
        self.assertEqual(1, len(failing.bodies))

    def test_rejects_ambiguous_names_reserved_placeholders_and_bad_provider_output(self):
        service = CloudProofreading(enabled=True, provider=FakeProvider(), clock=Clock())
        ambiguous = [{"name": "Alex", "aliases": []}, {"name": "Alexa", "aliases": ["Alex"]}]
        with self.assertRaises(CloudProofreadingError):
            service.preview(binding(), story(), ambiguous)
        reserved = [{"name": "⟦PH_PERSON_0001⟧", "aliases": []}]
        with self.assertRaises(CloudProofreadingError):
            service.preview(binding(), story(), reserved)
        with self.assertRaises(CloudProofreadingError):
            service.preview(binding(), dict(story(), extra="ignored fields refuse"), self.people())

        bad_provider = FakeProvider({"paragraphs": ["Unknown ⟦PH_PERSON_9999⟧"]})
        bad = CloudProofreading(enabled=True, provider=bad_provider, clock=Clock())
        preview = bad.preview(binding(), story(), self.people())
        with self.assertRaises(CloudProofreadingError) as caught:
            bad.confirm(preview["preview_id"], binding(), preview["request_sha256"], confirmed=True)
        self.assertEqual("invalid_provider_response", caught.exception.category)
        self.assertEqual(1, len(bad_provider.bodies))

        missing_provider = FakeProvider({"paragraphs": ["Name omitted."]})
        missing = CloudProofreading(enabled=True, provider=missing_provider, clock=Clock())
        preview = missing.preview(binding(), story(), self.people())
        with self.assertRaises(CloudProofreadingError) as caught:
            missing.confirm(preview["preview_id"], binding(), preview["request_sha256"], confirmed=True)
        self.assertEqual("invalid_provider_response", caught.exception.category)

        malformed = FakeProvider({"paragraphs": [
            "⟦PH_PERSON_0001⟧ and malformed ⟦PH_PERSON_9999X⟧"]})
        service = CloudProofreading(enabled=True, provider=malformed, clock=Clock())
        preview = service.preview(binding(), story(), self.people())
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("invalid_provider_response", caught.exception.category)

        unseen_person_story = story()
        unseen_person_story["chapters"][0]["narration"] = "The family enjoyed a quiet afternoon."
        unseen_provider = FakeProvider({"paragraphs": ["⟦PH_PERSON_0001⟧ was there."]})
        service = CloudProofreading(enabled=True, provider=unseen_provider, clock=Clock())
        preview = service.preview(binding(), unseen_person_story, self.people())
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("invalid_provider_response", caught.exception.category)

        redacted_secret = FakeProvider({"paragraphs": [
            "⟦PH_PERSON_0001⟧ contact family@example.test https://example.test/ "
            "C:\\Users\\Family\\note.txt sk-abcdefghijklmnop1234567890"]})
        service = CloudProofreading(enabled=True, provider=redacted_secret, clock=Clock())
        preview = service.preview(binding(), story(), self.people())
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("invalid_provider_response", caught.exception.category)

        oversized = FakeProvider({"paragraphs": ["x" * 6001]})
        service = CloudProofreading(enabled=True, provider=oversized, clock=Clock())
        preview = service.preview(binding(), story(), self.people())
        with self.assertRaises(CloudProofreadingError) as caught:
            service.confirm(preview["preview_id"], binding(), preview["request_sha256"],
                            confirmed=True)
        self.assertEqual("invalid_provider_response", caught.exception.category)

    def test_deepseek_provider_uses_fixed_endpoint_no_proxy_and_exact_body(self):
        provider = DeepSeekProofreader(api_key="secret-key-for-test", model="deepseek-flash")
        self.assertNotIn("secret-key-for-test", repr(provider))
        with self.assertRaises(AttributeError):
            provider.model = "changed-model"
        with self.assertRaises(AttributeError):
            provider.endpoint = "https://other.invalid/"
        body = json.dumps({
            "model": "deepseek-flash", "messages": [], "temperature": 0.2,
            "max_tokens": 2048, "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
        }, separators=(",", ":")).encode()

        class Response:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def iter_bytes(self):
                payload = json.dumps({"choices": [{"finish_reason": "stop", "message": {
                    "content": '{"paragraphs":["ok"]}'}}]}).encode()
                yield payload

        class Client:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def stream(self, method, url, *, headers, content):
                calls.append((method, url, headers, content, self.kwargs))
                return Response()

        calls = []
        with patch("app.access.story_cloud_proofreading.httpx.Client", Client):
            self.assertEqual({"paragraphs": ["ok"]}, provider.send(body))
        self.assertEqual(1, len(calls))
        method, url, headers, sent_body, options = calls[0]
        self.assertEqual("POST", method)
        self.assertEqual("https://api.deepseek.com/chat/completions", url)
        self.assertEqual(body, sent_body)
        self.assertEqual("Bearer secret-key-for-test", headers["Authorization"])
        self.assertEqual({"trust_env": False, "follow_redirects": False, "timeout": 45.0}, options)

    def test_deepseek_rejects_duplicate_json_nonfinite_and_tool_calls(self):
        provider = DeepSeekProofreader(api_key="secret-key-for-test", model="deepseek-flash")
        body = json.dumps({
            "model": "deepseek-flash", "messages": [], "temperature": 0.2,
            "max_tokens": 2048, "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
        }, separators=(",", ":")).encode()
        responses = [
            b'{"choices":[],"choices":[]}',
            b'{"choices":[{"finish_reason":"stop","message":{"content":"{\\"paragraphs\\":[],\\"paragraphs\\":[]}"}}]}',
            b'{"choices":[{"finish_reason":"stop","message":{"content":"{\\"paragraphs\\":[NaN]}"}}]}',
            b'{"choices":[{"finish_reason":"stop","message":{"content":"{\\"paragraphs\\":[]}","tool_calls":[]}}]}',
        ]

        for payload in responses:
            class Response:
                status_code = 200

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def iter_bytes(self):
                    yield payload

            class Client:
                def __init__(self, **_kwargs):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def stream(self, *_args, **_kwargs):
                    return Response()

            with self.subTest(response=payload[:40]), \
                    patch("app.access.story_cloud_proofreading.httpx.Client", Client):
                with self.assertRaises(CloudProofreadingError) as caught:
                    provider.send(body)
                self.assertEqual("invalid_provider_response", caught.exception.category)


if __name__ == "__main__":
    unittest.main()
