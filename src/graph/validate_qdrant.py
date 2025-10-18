"""Validation helpers for Qdrant collections."""
from __future__ import annotations

from config import AppConfig


def validate(cfg: AppConfig | None = None) -> bool:
    config = cfg or AppConfig()
    from qdrant_client import QdrantClient  # imported lazily to avoid heavy dependency at import time

    client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)

    collections = (
        config.QDRANT_COLLECTION_SECTIONS,
        config.QDRANT_COLLECTION_RECS,
        config.QDRANT_COLLECTION_FIGTABS,
    )

    for name in collections:
        info = client.get_collection(name)
        if info.vectors_count == 0:
            raise RuntimeError(f"Qdrant validation failed: collection '{name}' is empty.")
        count = client.count(name, exact=True).count
        if count <= 0:
            raise RuntimeError(f"Qdrant validation failed: collection '{name}' has no points.")

    return True


def main() -> None:  # pragma: no cover - CLI convenience
    validate()


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    main()
