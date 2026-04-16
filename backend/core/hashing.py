"""
Payload hash computation for IES data integrity verification.

The IES protocol requires a SHA-256 hash of the canonical JSON payload
to travel alongside the data so the receiver can verify nothing was
tampered with in transit.

Canonicalization: keys sorted, no whitespace, ensure_ascii=True.
This gives a deterministic byte representation regardless of the
dict insertion order on the sender side.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: dict[str, Any] | list[Any]) -> bytes:
    """Serialize payload to deterministic canonical JSON bytes."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def compute_payload_hash(payload: dict[str, Any] | list[Any]) -> str:
    """Compute SHA-256 hex digest of the canonical JSON payload."""
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def verify_payload_hash(
    payload: dict[str, Any] | list[Any],
    expected_hash: str,
) -> bool:
    """Verify that a payload matches its declared hash."""
    return compute_payload_hash(payload) == expected_hash
