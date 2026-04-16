"""Tests for payload hashing."""

import hashlib
import json

from backend.core.hashing import canonical_json, compute_payload_hash, verify_payload_hash


class TestCanonicalJson:
    def test_sorted_keys(self):
        result = canonical_json({"z": 1, "a": 2})
        assert result == b'{"a":2,"z":1}'

    def test_no_whitespace(self):
        result = canonical_json({"key": "value"})
        assert b" " not in result
        assert b"\n" not in result

    def test_nested_sorting(self):
        result = canonical_json({"b": {"d": 1, "c": 2}, "a": 3})
        assert result == b'{"a":3,"b":{"c":2,"d":1}}'

    def test_list_order_preserved(self):
        result = canonical_json({"items": [3, 1, 2]})
        assert result == b'{"items":[3,1,2]}'

    def test_deterministic(self):
        payload = {"name": "Test", "amount": 123.45, "items": [1, 2]}
        assert canonical_json(payload) == canonical_json(payload)


class TestComputePayloadHash:
    def test_returns_hex_string(self):
        h = compute_payload_hash({"test": "data"})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex = 64 chars

    def test_deterministic(self):
        payload = {"filing_id": "TEST/001", "amount": 1234.56}
        assert compute_payload_hash(payload) == compute_payload_hash(payload)

    def test_different_payloads_different_hashes(self):
        h1 = compute_payload_hash({"a": 1})
        h2 = compute_payload_hash({"a": 2})
        assert h1 != h2

    def test_key_order_irrelevant(self):
        h1 = compute_payload_hash({"z": 1, "a": 2})
        h2 = compute_payload_hash({"a": 2, "z": 1})
        assert h1 == h2

    def test_matches_manual_computation(self):
        payload = {"key": "value"}
        expected = hashlib.sha256(b'{"key":"value"}').hexdigest()
        assert compute_payload_hash(payload) == expected


class TestVerifyPayloadHash:
    def test_valid_hash(self):
        payload = {"test": "data"}
        h = compute_payload_hash(payload)
        assert verify_payload_hash(payload, h) is True

    def test_invalid_hash(self):
        payload = {"test": "data"}
        assert verify_payload_hash(payload, "wrong_hash") is False

    def test_tampered_payload(self):
        payload = {"amount": 1000}
        h = compute_payload_hash(payload)
        tampered = {"amount": 9999}
        assert verify_payload_hash(tampered, h) is False
