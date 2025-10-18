from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Sequence

from qdrant_client import QdrantClient

from ..adapters.medparse_transport import (
    LinkRequest,
    MedparseTransportError,
    get_medparse_transport,
)
from ..config import AppConfig

try:  # pragma: no cover - optional dependency for local development
    from ..index.embedders import medcpt_query_encode
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments

    def medcpt_query_encode(_: str):  # type: ignore[unused-ignore]
        return [0.0] * 768

from .router import RouterDecision, choose_store

try:  # pragma: no cover - optional dependency
    from neo4j import GraphDatabase
except ModuleNotFoundError:  # pragma: no cover - environments without neo4j
    GraphDatabase = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLL_NAME = os.getenv("QDRANT_COLLECTION_V2", "ip_docs_v2")

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def _ensure_query_embedding(query: str) -> List[float]:
    return medcpt_query_encode(query).tolist()


def _search_named(query: str, target_vector: str, top_k: int = 8) -> List[Dict[str, Any]]:
    embedding = _ensure_query_embedding(query)
    hits = client.search(
        collection_name=COLL_NAME,
        query_vector=(target_vector, embedding),
        limit=top_k,
        with_payload=True,
    )
    return [
        {
            "id": h.payload.get("chunk_id", h.id),
            "score": h.score,
            "text": h.payload.get("text")
            or h.payload.get("quote_text")
            or h.payload.get("summary_text", ""),
            "payload": h.payload,
        }
        for h in hits
    ]


def _search_collection(collection: str, embedding: Sequence[float], top_k: int = 6) -> List[Dict[str, Any]]:
    try:
        hits = client.search(
            collection_name=collection,
            query_vector=list(embedding),
            limit=top_k,
            with_payload=True,
        )
    except Exception as exc:  # pragma: no cover - qdrant unavailable
        LOGGER.warning("Qdrant search failed for %s: %s", collection, exc)
        return []
    return [
        {
            "id": str(hit.id),
            "score": hit.score,
            "payload": hit.payload or {},
        }
        for hit in hits
    ]


def _coverage(results: List[Dict[str, Any]]) -> float:
    if not results:
        return 0.0
    top = sorted((r["score"] for r in results), reverse=True)[:3]
    return sum(top) / len(top)


def _expand_query(query: str, concepts: Sequence[str]) -> str:
    cleaned = [term for term in {c.strip() for c in concepts} if term]
    if not cleaned:
        return query
    hints = " ".join(cleaned[:8])
    return f"{query} {hints}".strip()


def _extract_concept_terms(link_response: Dict[str, Any]) -> List[str]:
    concepts = link_response.get("concepts") or []
    terms: List[str] = []
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        for key in ("preferred_name", "label", "text"):
            value = concept.get(key)
            if value:
                terms.append(str(value))
                break
        else:
            cui = concept.get("cui")
            if cui:
                terms.append(str(cui))
    return terms


@lru_cache(maxsize=1)
def _neo4j_driver(uri: str, user: str | None, password: str | None):  # pragma: no cover - cached setup
    if GraphDatabase is None:
        return None
    auth = None
    if user and password:
        auth = (user, password)
    return GraphDatabase.driver(uri, auth=auth)


def _fetch_supported_stats(cfg: AppConfig, rec_ids: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not rec_ids or not cfg.APP_USE_NEO4J or GraphDatabase is None:
        return {}
    driver = _neo4j_driver(cfg.NEO4J_URI or "neo4j://localhost:7687", cfg.NEO4J_USER, cfg.NEO4J_PASSWORD)
    if driver is None:
        return {}
    stats: Dict[str, List[Dict[str, Any]]] = {}
    query = (
        "MATCH (r:Recommendation {id:$rec_id})-[:SUPPORTED_BY]->(s:Stat) "
        "RETURN s.id AS id, s.stat_type AS stat_type, s.value AS value, "
        "s.ci_low AS ci_low, s.ci_high AS ci_high, s.p_value AS p_value, s.page AS page"
    )
    try:
        with driver.session(database=cfg.NEO4J_DATABASE) as session:
            for rec_id in rec_ids:
                records = session.run(query, rec_id=rec_id)
                rows = [
                    {
                        "id": record["id"],
                        "stat_type": record["stat_type"],
                        "value": record["value"],
                        "ci_low": record["ci_low"],
                        "ci_high": record["ci_high"],
                        "p_value": record["p_value"],
                        "page": record["page"],
                    }
                    for record in records
                ]
                if rows:
                    stats[rec_id] = rows
    except Exception as exc:  # pragma: no cover - graph unreachable
        LOGGER.warning("Neo4j statistics lookup failed: %s", exc)
    return stats


def _collect_evidence(query: str, cfg: AppConfig) -> Dict[str, Any]:
    embedding = _ensure_query_embedding(query)

    rec_hits = []
    section_hits = []
    figtab_hits = []

    if cfg.APP_USE_QDRANT:
        rec_hits = _search_collection(cfg.QDRANT_COLLECTION_RECS, embedding)
        section_hits = _search_collection(cfg.QDRANT_COLLECTION_SECTIONS, embedding)
        figtab_hits = _search_collection(cfg.QDRANT_COLLECTION_FIGTABS, embedding)

    rec_hits.sort(
        key=lambda hit: (
            int(hit.get("payload", {}).get("supported_by", 0) or 0),
            hit.get("score", 0.0),
        ),
        reverse=True,
    )

    rec_ids = [hit.get("payload", {}).get("node_id") for hit in rec_hits if hit.get("payload")]
    rec_ids = [rid for rid in rec_ids if isinstance(rid, str)]
    stats_map = _fetch_supported_stats(cfg, rec_ids)

    evidence_items: List[Dict[str, Any]] = []
    for hit in rec_hits:
        payload = hit.get("payload", {})
        node_id = payload.get("node_id")
        if not isinstance(node_id, str):
            continue
        supported_by = int(payload.get("supported_by", 0) or 0)
        evidence_items.append(
            {
                "recommendation": {
                    "id": node_id,
                    "text": payload.get("text"),
                    "grade": payload.get("grade"),
                    "page": payload.get("page"),
                    "supported_by": supported_by,
                },
                "statistics": stats_map.get(node_id, []),
                "figures": [],
                "tables": [],
            }
        )

    summary = {
        "recommendations": len(evidence_items),
        "stats": sum(len(item["statistics"]) for item in evidence_items),
        "figures": sum(1 for hit in figtab_hits if hit.get("payload", {}).get("kind") == "figure"),
        "tables": sum(1 for hit in figtab_hits if hit.get("payload", {}).get("kind") == "table"),
    }

    return {
        "recommendation_hits": rec_hits,
        "section_hits": section_hits,
        "evidence_items": evidence_items,
        "evidence_summary": summary,
    }


async def retrieve_with_fallback(query: str, top_k: int = 8, score_threshold: float = 0.32) -> Dict[str, Any]:
    cfg = AppConfig()
    medparse_terms: List[str] = []
    expanded_query = query

    if cfg.MEDPARSE_ENABLED:
        try:
            transport = get_medparse_transport(cfg)
            if transport.health():
                link = transport.link(LinkRequest(text=query))
                medparse_terms = _extract_concept_terms(link)
                expanded_query = _expand_query(query, medparse_terms)
        except MedparseTransportError as exc:
            LOGGER.warning("Medparse link failed: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Unexpected Medparse transport error", exc_info=exc)

    decision: RouterDecision = choose_store(expanded_query)
    order = [decision.store] + [s for s in ["quotes", "summaries", "chunks"] if s != decision.store]
    for store in order:
        res = _search_named(expanded_query, store, top_k=top_k)
        if _coverage(res) >= score_threshold or store == "chunks":
            evidence = _collect_evidence(expanded_query, cfg)
            return {
                "store": store,
                "results": res,
                "router_confidence": decision.confidence,
                "medparse_terms": medparse_terms,
                **evidence,
            }

    fallback_results = _search_named(expanded_query, "chunks", top_k=top_k)
    evidence = _collect_evidence(expanded_query, cfg)
    return {
        "store": "chunks",
        "results": fallback_results,
        "router_confidence": decision.confidence,
        "medparse_terms": medparse_terms,
        **evidence,
    }


__all__ = ["retrieve_with_fallback"]
