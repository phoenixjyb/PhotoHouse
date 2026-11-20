"""Characterization envelope for the bounded numeric kernel, not an API.

Authorization, file/cohort admission, IDs, sorting and cache publication remain
with their existing callers. The runtime adapter uses immutable byte buffers;
this JSON/hex envelope exists only for portable Rust parity recordings.
"""
import hashlib
import json
import math
import re
import struct

MAX_BYTES = 4 * 1024 * 1024
MAX_DIMENSION = 4096
PREFIX = b"photohouse-visual-vector-v1\0"


def _invalid():
    raise ValueError("invalid_vector_batch")


def _bytes(value):
    if (type(value) is not str or len(value) > MAX_BYTES * 2
            or len(value) % 2 or re.fullmatch(r"[0-9a-f]*", value) is None):
        _invalid()
    return bytes.fromhex(value)


def run_batch(payload: str) -> str:
    """Return exact normalized/scored bytes or a fixed invalid-input error."""
    if type(payload) is not str or len(payload) > 10 * 1024 * 1024:
        _invalid()
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        _invalid()
    if type(data) is not dict:
        _invalid()
    dimension, order = data.get("dimension"), data.get("byteorder")
    if (type(dimension) is not int or not 1 <= dimension <= MAX_DIMENSION
            or type(order) is not str or order not in ("little", "big")):
        _invalid()
    code = "<" if order == "little" else ">"
    raw = _bytes(data.get("data"))
    if data.get("op") == "canonicalize":
        if set(data) != {"op", "dimension", "byteorder", "data", "checksums"}:
            _invalid()
        checksums = data["checksums"]
        if (len(raw) % (dimension * 4) or len(raw) * 2 > MAX_BYTES
                or type(checksums) is not list or len(checksums) != len(raw) // (dimension * 4)):
            _invalid()
        result = bytearray()
        for index, checksum in enumerate(checksums):
            if type(checksum) is not str or re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
                _invalid()
            row = raw[index * dimension * 4:(index + 1) * dimension * 4]
            if hashlib.sha256(PREFIX + struct.pack(">I", dimension) + row).hexdigest() != checksum:
                _invalid()
            values = struct.unpack(f">{dimension}f", row)
            if not all(map(math.isfinite, values)):
                _invalid()
            norm = math.sqrt(math.fsum(value * value for value in values))
            if norm == 0 or not math.isfinite(norm) or abs(norm - 1.0) > 1e-3:
                _invalid()
            result.extend(struct.pack(f"{code}{dimension}d", *(value / norm for value in values)))
        return result.hex()
    if data.get("op") == "score":
        if set(data) != {"op", "dimension", "byteorder", "data", "query"}:
            _invalid()
        query_raw = _bytes(data["query"])
        if len(raw) % (dimension * 8) or len(query_raw) != dimension * 8:
            _invalid()
        query = struct.unpack(f"{code}{dimension}d", query_raw)
        if not all(map(math.isfinite, query)):
            _invalid()
        result = bytearray()
        for row in struct.iter_unpack(f"{code}{dimension}d", raw):
            result.extend(struct.pack(code + "d", math.fsum(a * b for a, b in zip(query, row))))
        return result.hex()
    _invalid()
