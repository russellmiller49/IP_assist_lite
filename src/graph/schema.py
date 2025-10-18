"""Graph schema helpers for Neo4j and Qdrant."""
from __future__ import annotations

from typing import Iterable, Sequence


DOCUMENT_LABEL = "Document"
SECTION_LABEL = "Section"
RECOMMENDATION_LABEL = "Recommendation"
STAT_LABEL = "Stat"
FIGURE_LABEL = "Figure"
TABLE_LABEL = "Table"

NEO4J_CONSTRAINTS: tuple[str, ...] = (
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (d:{DOCUMENT_LABEL}) REQUIRE d.doc_id IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (s:{SECTION_LABEL}) REQUIRE s.id IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (r:{RECOMMENDATION_LABEL}) REQUIRE r.id IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (st:{STAT_LABEL}) REQUIRE st.id IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (f:{FIGURE_LABEL}) REQUIRE f.id IS UNIQUE",
    f"CREATE CONSTRAINT IF NOT EXISTS FOR (t:{TABLE_LABEL}) REQUIRE t.id IS UNIQUE",
)

RELATIONSHIPS: tuple[str, ...] = (
    f"({DOCUMENT_LABEL})-[:HAS_SECTION]->({SECTION_LABEL})",
    f"({DOCUMENT_LABEL})-[:HAS_RECOMMENDATION]->({RECOMMENDATION_LABEL})",
    f"({DOCUMENT_LABEL})-[:HAS_STAT]->({STAT_LABEL})",
    f"({DOCUMENT_LABEL})-[:HAS_FIGURE]->({FIGURE_LABEL})",
    f"({DOCUMENT_LABEL})-[:HAS_TABLE]->({TABLE_LABEL})",
    f"({RECOMMENDATION_LABEL})-[:SUPPORTED_BY]->({STAT_LABEL})",
    f"({FIGURE_LABEL})-[:ILLUSTRATES]->({RECOMMENDATION_LABEL})",
    f"({TABLE_LABEL})-[:SUMMARIZES]->({STAT_LABEL})",
)


def apply_neo4j_constraints(driver, *, database: str | None = None) -> None:  # pragma: no cover - executed in integration environments
    with driver.session(database=database) as session:
        for stmt in NEO4J_CONSTRAINTS:
            session.run(stmt)


__all__ = [
    "DOCUMENT_LABEL",
    "SECTION_LABEL",
    "RECOMMENDATION_LABEL",
    "STAT_LABEL",
    "FIGURE_LABEL",
    "TABLE_LABEL",
    "NEO4J_CONSTRAINTS",
    "RELATIONSHIPS",
    "apply_neo4j_constraints",
]
