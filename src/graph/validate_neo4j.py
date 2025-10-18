"""Validation helpers for Neo4j evidence graph."""
from __future__ import annotations

import os
import sys
from typing import Sequence

from config import AppConfig
from .schema import (
    DOCUMENT_LABEL,
    FIGURE_LABEL,
    RECOMMENDATION_LABEL,
    SECTION_LABEL,
    STAT_LABEL,
    TABLE_LABEL,
)


def validate(cfg: AppConfig | None = None) -> bool:
    config = cfg or AppConfig()
    try:
        from neo4j import GraphDatabase
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing
        if _skip_validation():
            sys.stderr.write("[warn] Neo4j driver missing; skipping validation (set ALLOW_SKIP_NEO4J_VALIDATION=0 to enforce).\n")
            return False
        raise RuntimeError("neo4j python driver not installed; cannot validate graph.") from exc

    auth = None
    if config.NEO4J_USER and config.NEO4J_PASSWORD:
        auth = (config.NEO4J_USER, config.NEO4J_PASSWORD)
    driver = GraphDatabase.driver(config.NEO4J_URI, auth=auth)

    try:
        with driver.session(database=config.NEO4J_DATABASE) as session:
            counts = {
                label: session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
                for label in _LABELS
            }
            if counts[DOCUMENT_LABEL] <= 0:
                raise RuntimeError("Neo4j validation failed: no Document nodes present.")
            if counts[RECOMMENDATION_LABEL] <= 0:
                raise RuntimeError("Neo4j validation failed: no Recommendation nodes present.")

            rel_count = session.run(
                "MATCH (:Recommendation)-[r:SUPPORTED_BY]->(:Stat) RETURN count(r) AS c"
            ).single()["c"]
            if rel_count <= 0:
                raise RuntimeError("Neo4j validation failed: missing SUPPORTED_BY relationships.")
    finally:
        driver.close()

    return True


def main() -> None:  # pragma: no cover - CLI convenience
    validate()


def _skip_validation() -> bool:
    raw = os.getenv("ALLOW_SKIP_NEO4J_VALIDATION", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


_LABELS: Sequence[str] = (
    DOCUMENT_LABEL,
    SECTION_LABEL,
    RECOMMENDATION_LABEL,
    STAT_LABEL,
    FIGURE_LABEL,
    TABLE_LABEL,
)


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    main()
