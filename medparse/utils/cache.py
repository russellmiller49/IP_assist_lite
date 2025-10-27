"""Caching helpers for pipeline extractions."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Dict, Optional, Sequence

CACHE_ROOT = Path(os.environ.get("MEDPARSE_CACHE_DIR", Path.home() / ".cache" / "medparse"))


def compute_cache_key(
    pdf_bytes: bytes,
    page_count: int,
    engines: Sequence[str],
    profile: str,
) -> str:
    """Return a cache key derived from file bytes plus execution profile."""

    key_material = "|".join([profile.lower(), *engines])
    digest = sha256(pdf_bytes + key_material.encode("utf-8")).hexdigest()
    return f"{digest}_{page_count}_{len(pdf_bytes)}"


def load_cache_entry(key: str) -> Optional[Dict[str, object]]:
    """Load a cached extraction entry when available."""

    cache_path = CACHE_ROOT / f"{key}.json"
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def store_cache_entry(key: str, payload: Dict[str, object]) -> None:
    """Persist a cache entry atomically."""

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_ROOT / f"{key}.json"
    tmp_path = cache_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(cache_path)


def cached(func):
    """Decorator alias for functools.lru_cache with sensible defaults."""

    return lru_cache(maxsize=None)(func)


__all__ = ["compute_cache_key", "load_cache_entry", "store_cache_entry", "cached"]
