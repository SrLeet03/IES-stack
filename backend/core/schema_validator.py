"""
JSON Schema validation for IES data types.

Validates payloads against the IES JSON Schema files shipped in /schemas/.
Supports IES_ARR_Filing, IES_ARR_LineItem, and can be extended for
IES_Policy, IES_Report, etc.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator, ValidationError


SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"


@dataclass
class SchemaValidationResult:
    """Result of validating a payload against a JSON Schema."""

    is_valid: bool
    errors: list[str]

    def __bool__(self) -> bool:
        return self.is_valid


def _load_schema(schema_name: str) -> dict[str, Any]:
    path = SCHEMAS_DIR / schema_name
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    with open(path) as f:
        return json.load(f)


_schema_cache: dict[str, dict[str, Any]] = {}


def get_schema(schema_name: str) -> dict[str, Any]:
    """Load and cache a JSON Schema by filename."""
    if schema_name not in _schema_cache:
        _schema_cache[schema_name] = _load_schema(schema_name)
    return _schema_cache[schema_name]


def validate_payload(
    payload: dict[str, Any],
    schema_name: str,
) -> SchemaValidationResult:
    """
    Validate a payload dict against a named JSON Schema.

    Returns a result with is_valid=True if the payload conforms,
    or is_valid=False with a list of human-readable error messages.
    """
    schema = get_schema(schema_name)

    # Strip JSON-LD keys that aren't in the schema before validating
    cleaned = {k: v for k, v in payload.items() if k not in ("@context", "@type")}

    validator = Draft202012Validator(schema)
    errors: list[str] = []

    for error in sorted(validator.iter_errors(cleaned), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"{path}: {error.message}")

    return SchemaValidationResult(is_valid=len(errors) == 0, errors=errors)


def validate_arr_filing(payload: dict[str, Any]) -> SchemaValidationResult:
    """Convenience: validate an ARR filing payload."""
    return validate_payload(payload, "IES_ARR_Filing.schema.json")
