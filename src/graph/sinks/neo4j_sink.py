"""Neo4j sink for Medparse graph payloads."""
from __future__ import annotations

import re
from typing import Any, Mapping

from ...normalize.types import GraphPayload


class Neo4jSink:
    """Persist Medparse graph payloads into Neo4j."""

    def __init__(self, driver) -> None:  # driver type is neo4j.Driver, kept generic to avoid hard dependency
        self._driver = driver

    @classmethod
    def from_config(cls, config) -> "Neo4jSink":  # pragma: no cover - exercised in integration environments
        try:
            from neo4j import GraphDatabase
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing during tests
            raise RuntimeError(
                "neo4j python driver not installed. Install with `pip install neo4j` or "
                "set MEDPARSE_TRANSPORT=http to skip graph persistence."
            ) from exc

        auth = None
        if config.NEO4J_USER and config.NEO4J_PASSWORD:
            auth = (config.NEO4J_USER, config.NEO4J_PASSWORD)
        driver = GraphDatabase.driver(config.NEO4J_URI, auth=auth)
        return cls(driver)

    def close(self) -> None:
        self._driver.close()

    def upsert(self, payload: GraphPayload) -> None:
        with self._driver.session() as session:
            session.execute_write(self._merge_document, payload)

    @staticmethod
    def _merge_document(tx, payload: GraphPayload) -> None:
        doc_id = payload["doc_id"]
        tx.run(
            "MERGE (d:Document {uid: $uid}) SET d += $props",
            uid=doc_id,
            props=dict(payload.get("doc_meta", {})),
        )

        for section in payload.get("sections", []):
            section_props = {k: v for k, v in section.items() if k not in {"uid", "doc_id"}}
            tx.run(
                "MERGE (s:Section {uid: $uid}) SET s += $props",
                uid=section.get("uid"),
                props=section_props,
            )
            tx.run(
                "MATCH (d:Document {uid:$doc_id}), (s:Section {uid:$section_uid}) "
                "MERGE (d)-[:HAS_SECTION]->(s)",
                doc_id=doc_id,
                section_uid=section.get("uid"),
            )

        nodes = payload.get("nodes", {})
        for rec in nodes.get("Recommendation", []):
            Neo4jSink._merge_node(tx, "Recommendation", rec, doc_id)
        for stat in nodes.get("Stat", []):
            Neo4jSink._merge_node(tx, "Stat", stat, doc_id)
        for figure in nodes.get("Figure", []):
            Neo4jSink._merge_node(tx, "Figure", figure, doc_id)
        for table in nodes.get("Table", []):
            Neo4jSink._merge_node(tx, "Table", table, doc_id)

        for edge in payload.get("edges", []):
            source = edge.get("source_uid")
            target = edge.get("target_uid")
            if not source or not target:
                continue
            rel_type = _sanitize_relationship(edge.get("type", "RELATED_TO"))
            tx.run(
                f"MATCH (s {{uid:$source}}), (t {{uid:$target}}) "
                f"MERGE (s)-[:{rel_type}]->(t)",
                source=source,
                target=target,
            )

    @staticmethod
    def _merge_node(tx, label: str, node: Mapping[str, Any], doc_id: str) -> None:
        uid = node.get("uid")
        if not uid:
            return
        props = {k: v for k, v in node.items() if k not in {"uid", "section_uid"}}
        props.setdefault("doc_id", doc_id)
        tx.run(
            f"MERGE (n:{label} {{uid:$uid}}) SET n += $props",
            uid=uid,
            props=props,
        )
        tx.run(
            f"MATCH (d:Document {{uid:$doc_id}}), (n:{label} {{uid:$uid}}) MERGE (d)-[:HAS_{label.upper()}]->(n)",
            doc_id=doc_id,
            uid=uid,
        )
        section_uid = node.get("section_uid")
        if section_uid:
            tx.run(
                f"MATCH (s:Section {{uid:$section_uid}}), (n:{label} {{uid:$uid}}) "
                "MERGE (s)-[:CONTAINS]->(n)",
                section_uid=section_uid,
                uid=uid,
            )


def _sanitize_relationship(value: Any) -> str:
    rel = str(value or "RELATED_TO").upper()
    rel = re.sub(r"[^A-Z0-9_]+", "_", rel)
    return rel or "RELATED_TO"


__all__ = ["Neo4jSink"]
