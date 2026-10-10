import hashlib
import io
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import image_embedding_receipts as receipts


def test_checkpoint_pin_is_immutable_and_verifies_large_streamed_bytes(tmp_path, monkeypatch):
    checkpoint = tmp_path / "model.bin"
    content = b"checkpoint bytes" * 200_000
    checkpoint.write_bytes(content)
    monkeypatch.setattr(receipts, "_CHUNK_BYTES", 4096)

    pin = receipts.inspect_checkpoint(checkpoint, hashlib.sha256(content).hexdigest())

    assert pin.path == str(checkpoint)
    assert pin.sha256 == hashlib.sha256(content).hexdigest()
    assert receipts.verify_checkpoint(pin) is pin
    with pytest.raises(AttributeError):
        pin.sha256 = "0" * 64


def test_checkpoint_inspection_rejects_malformed_or_wrong_sha256(tmp_path):
    checkpoint = tmp_path / "model.bin"
    checkpoint.write_bytes(b"model")
    for malformed in (None, 123, "A" * 64, "0" * 63, "g" * 64):
        with pytest.raises(receipts.ReceiptError, match="invalid_expected_sha256"):
            receipts.inspect_checkpoint(checkpoint, malformed)
    with pytest.raises(receipts.ReceiptError, match="checkpoint_sha256_mismatch"):
        receipts.inspect_checkpoint(checkpoint, "0" * 64)


def test_verify_rejects_modified_checkpoint_bytes(tmp_path):
    checkpoint = tmp_path / "model.bin"
    checkpoint.write_bytes(b"before")
    pin = receipts.inspect_checkpoint(checkpoint, hashlib.sha256(b"before").hexdigest())
    checkpoint.write_bytes(b"after!")

    with pytest.raises(receipts.ReceiptError, match="checkpoint_changed"):
        receipts.verify_checkpoint(pin)


def test_checkpoint_stream_refuses_growth_beyond_pinned_size(tmp_path, monkeypatch):
    checkpoint = tmp_path / "model.bin"
    checkpoint.write_bytes(b"model")
    monkeypatch.setattr(receipts, "_open_pinned", lambda *_: io.BytesIO(b"modelgrew"))
    with pytest.raises(receipts.ReceiptError, match="checkpoint_changed"):
        receipts.inspect_checkpoint(checkpoint, hashlib.sha256(b"model").hexdigest())


def test_checkpoint_refuses_byte_budget_before_reading(tmp_path, monkeypatch):
    checkpoint = tmp_path / "model.bin"
    checkpoint.write_bytes(b"oversize")
    monkeypatch.setattr(receipts, "_MAX_CHECKPOINT_BYTES", 4)
    with pytest.raises(receipts.ReceiptError, match="checkpoint_byte_budget"):
        receipts.inspect_checkpoint(checkpoint, hashlib.sha256(b"oversize").hexdigest())


def test_verify_rejects_replaced_checkpoint_path(tmp_path):
    checkpoint = tmp_path / "model.bin"
    replacement = tmp_path / "replacement.bin"
    checkpoint.write_bytes(b"first")
    replacement.write_bytes(b"other")
    pin = receipts.inspect_checkpoint(checkpoint, hashlib.sha256(b"first").hexdigest())
    replacement.replace(checkpoint)

    with pytest.raises(receipts.ReceiptError, match="checkpoint_changed"):
        receipts.verify_checkpoint(pin)


def test_checkpoint_inspection_rejects_symlink_and_non_regular_file(tmp_path):
    target = tmp_path / "target.bin"
    target.write_bytes(b"model")
    link = tmp_path / "link.bin"
    link.symlink_to(target)
    digest = hashlib.sha256(b"model").hexdigest()

    with pytest.raises(receipts.ReceiptError, match="checkpoint_link_refused"):
        receipts.inspect_checkpoint(link, digest)
    with pytest.raises(receipts.ReceiptError, match="checkpoint_not_regular"):
        receipts.inspect_checkpoint(tmp_path, digest)


def test_recipe_digest_is_canonical_for_explicit_json_primitives():
    first = {"model": "clip-local", "options": {"batch": 2, "normalize": True}}
    second = {"options": {"normalize": True, "batch": 2}, "model": "clip-local"}
    expected = hashlib.sha256(
        json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    assert receipts.recipe_sha256(first) == expected
    assert receipts.recipe_sha256(second) == expected


@pytest.mark.parametrize(
    "recipe",
    [
        {1: "non-string key"},
        {"bad": float("nan")},
        {"bad": float("inf")},
        {"bad": object()},
        ["not", "an", "object"],
    ],
)
def test_recipe_digest_rejects_non_json_or_noncanonical_inputs(recipe):
    with pytest.raises(receipts.ReceiptError):
        receipts.recipe_sha256(recipe)


def test_verify_rejects_malformed_pin():
    with pytest.raises(receipts.ReceiptError, match="invalid_checkpoint_pin"):
        receipts.verify_checkpoint(object())
