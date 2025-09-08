# src/utils/serialization.py
"""
Safe JSON serialization utilities for OpenAI SDK objects
"""
from typing import Any

def to_jsonable(o: Any) -> Any:
    """Recursively convert OpenAI SDK / Pydantic models to plain Python types."""
    # Pydantic v2 models used by openai>=1.x expose model_dump / model_dump_json
    if hasattr(o, "model_dump"):
        try:
            return o.model_dump()
        except Exception:
            pass
    if isinstance(o, dict):
        return {k: to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_jsonable(x) for x in o]
    return o  # primitives and anything else

__all__ = ["to_jsonable"]