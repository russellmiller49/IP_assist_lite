"""Serialization utilities for converting SDK objects to JSON."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def to_jsonable(obj):
    """Convert SDK objects to JSON-serializable format recursively."""

    def _convert(value, seen):
        if isinstance(value, (str, bytes, bytearray)) or value is None:
            return value
        if isinstance(value, (int, float, bool)):
            return value

        obj_id = id(value)
        if obj_id in seen:
            return repr(value)
        seen.add(obj_id)

        if hasattr(value, "model_dump"):
            return _convert(value.model_dump(), seen)
        if hasattr(value, "dict") and not isinstance(value, Mapping):
            return _convert(value.dict(), seen)
        if isinstance(value, Mapping):
            return {k: _convert(v, seen) for k, v in value.items()}
        if isinstance(value, Sequence):
            return [_convert(item, seen) for item in value]
        if hasattr(value, "__dict__"):
            return _convert(vars(value), seen)
        return value

    return _convert(obj, set())
