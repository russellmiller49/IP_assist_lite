"""Caching helpers for expensive operations."""

from functools import lru_cache
from hashlib import md5
from pathlib import Path


def file_hash(path: Path) -> str:
    """Return an MD5 hash of the file bytes."""
    with path.open("rb") as fh:
        data = fh.read()
    return md5(data).hexdigest()


def cached(func):
    """Decorator alias for functools.lru_cache with sensible defaults."""

    return lru_cache(maxsize=None)(func)
