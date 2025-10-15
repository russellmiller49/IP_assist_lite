"""JSON Schema validation helpers for Medparse contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator, RefResolver, ValidationError

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "shared" / "contracts" / "medparse"


@lru_cache(maxsize=32)
def _load_validator(schema_name: str) -> Draft7Validator:
    filename = schema_name
    if not filename.lower().endswith(".schema.json"):
        filename = f"{schema_name}.schema.json"
    schema_path = _SCHEMAS_DIR / filename
    if not schema_path.exists():
        raise FileNotFoundError(f"Medparse schema not found: {schema_path}")
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    resolver = RefResolver(base_uri=schema_path.parent.as_uri() + "/", referrer=schema)
    return Draft7Validator(schema, resolver=resolver)  # type: ignore[arg-type]


def validate_against_schema(instance: Any, schema_name: str) -> None:
    """Validate ``instance`` against the Medparse schema ``schema_name``.

    Raises:
        jsonschema.ValidationError: if ``instance`` violates the schema.
    """

    validator = _load_validator(schema_name)
    errors = sorted(validator.iter_errors(instance), key=lambda err: err.path)
    if errors:
        message = "; ".join(error.message for error in errors)
        raise ValidationError(message)
