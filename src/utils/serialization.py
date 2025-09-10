"""Serialization utilities for converting SDK objects to JSON."""

def to_jsonable(obj):
    """Convert SDK objects to JSON-serializable format."""
    if hasattr(obj, 'model_dump'):
        return obj.model_dump()
    elif hasattr(obj, 'dict'):
        return obj.dict()
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    return obj
