"""Neo4j sink for Medparse graph payloads."""
from __future__ import annotations

from typing import Any, Mapping

from ...normalize.types import GraphPayload
from ..schema import (
    DOCUMENT_LABEL,
    FIGURE_LABEL,
    RECOMMENDATION_LABEL,
    SECTION_LABEL,
    STAT_LABEL,
    TABLE_LABEL,
    apply_neo4j_constraints,
)


class Neo4jSink:
    """Persist Medparse graph payloads into Neo4j."""

    def __init__(self, driver, *, database: str | None = None) -> None:
        self._driver = driver
        self._database = database

    @classmethod
    def from_config(cls, config) -> "Neo4jSink":  # pragma: no cover - exercised in integration environments
        try:
            from neo4j import GraphDatabase
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing during tests
            raise RuntimeError(
                "neo4j python driver not installed. Install with `pip install neo4j` or "
                "set APP_USE_NEO4J=false to skip graph persistence."
            ) from exc

        auth = None
        if config.NEO4J_USER and config.NEO4J_PASSWORD:
            auth = (config.NEO4J_USER, config.NEO4J_PASSWORD)
        driver = GraphDatabase.driver(config.NEO4J_URI, auth=auth)
        apply_neo4j_constraints(driver, database=config.NEO4J_DATABASE)
        return cls(driver, database=config.NEO4J_DATABASE)

    def close(self) -> None:
        self._driver.close()

    def upsert(self, payload: GraphPayload) -> None:
        with self._driver.session(database=self._database) as session:
            session.execute_write(self._merge_payload, payload)

    @staticmethod
    def _merge_payload(tx, payload: GraphPayload) -> None:
        doc_id = payload["doc_id"]
        doc_props = dict(payload.get("doc_meta", {}))
        doc_props["doc_id"] = doc_id
        tx.run(
            f"MERGE (d:{DOCUMENT_LABEL} {{doc_id:$doc_id}}) SET d += $props",
            doc_id=doc_id,
            props=doc_props,
        )

        for section in payload.get("sections", []):
            section_id = section.get("uid") or section.get("id")
            if not section_id:
                continue
            props = {
                "id": section_id,
                "title": section.get("title"),
                "page_start": section.get("page_start"),
                "page_end": section.get("page_end"),
                "text": section.get("text"),
            }
            tx.run(
                f"MERGE (s:{SECTION_LABEL} {{id:$id}}) SET s += $props",
                id=section_id,
                props=props,
            )
            tx.run(
                f"MATCH (d:{DOCUMENT_LABEL} {{doc_id:$doc_id}}), (s:{SECTION_LABEL} {{id:$id}}) "
                "MERGE (d)-[:HAS_SECTION]->(s)",
                doc_id=doc_id,
                id=section_id,
            )

        nodes = payload.get("nodes", {})
        for rec in nodes.get("Recommendation", []):
            Neo4jSink._merge_node(tx, RECOMMENDATION_LABEL, rec, doc_id)
        for stat in nodes.get("Stat", []):
            Neo4jSink._merge_node(tx, STAT_LABEL, stat, doc_id)
        for figure in nodes.get("Figure", []):
            Neo4jSink._merge_node(tx, FIGURE_LABEL, figure, doc_id)
        for table in nodes.get("Table", []):
            Neo4jSink._merge_node(tx, TABLE_LABEL, table, doc_id)

        for edge in payload.get("edges", []):
            Neo4jSink._merge_relationship(tx, edge)

    @staticmethod
    def _merge_node(tx, label: str, node: Mapping[str, Any], doc_id: str) -> None:
        node_id = node.get("uid") or node.get("id")
        if not node_id:
            return
        props = dict(node)
        props["id"] = node_id
        props.pop("uid", None)
        props.setdefault("doc_id", doc_id)
        section_uid = props.pop("section_uid", None)

        tx.run(
            f"MERGE (n:{label} {{id:$id}}) SET n += $props",
            id=node_id,
            props=props,
        )
        tx.run(
            f"MATCH (d:{DOCUMENT_LABEL} {{doc_id:$doc_id}}), (n:{label} {{id:$id}}) "
            f"MERGE (d)-[:HAS_{label.upper()}]->(n)",
            doc_id=doc_id,
            id=node_id,
        )
        if section_uid:
            tx.run(
                f"MATCH (s:{SECTION_LABEL} {{id:$section_id}}), (n:{label} {{id:$node_id}}) "
                "MERGE (s)-[:CONTAINS]->(n)",
                section_id=section_uid,
                node_id=node_id,
            )

    @staticmethod
    def _merge_relationship(tx, edge: Mapping[str, Any]) -> None:
        rel_type = str(edge.get("type", "RELATED_TO")).upper()
        source = edge.get("source_uid") or edge.get("source_id")
        target = edge.get("target_uid") or edge.get("target_id")
        if not source or not target:
            return
        tx.run(
            "MATCH (s {id:$source}), (t {id:$target}) "
            f"MERGE (s)-[r:{rel_type}]->(t)",
            source=source,
            target=target,
        )


__all__ = ["Neo4jSink"]
