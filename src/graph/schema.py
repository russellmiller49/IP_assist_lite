"""Graph schema helpers for Neo4j and Qdrant."""
from __future__ import annotations

from typing import Iterable


NEO4J_CONSTRAINTS: tuple[str, ...] = (
    "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Section) REQUIRE s.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Recommendation) REQUIRE r.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (st:Stat) REQUIRE st.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (f:Figure) REQUIRE f.uid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Table) REQUIRE t.uid IS UNIQUE",
)


def apply_neo4j_constraints(driver) -> None:  # pragma: no cover - executed in integration environments
    with driver.session() as session:
        for stmt in NEO4J_CONSTRAINTS:
            session.run(stmt)


__all__ = ["NEO4J_CONSTRAINTS", "apply_neo4j_constraints"]
