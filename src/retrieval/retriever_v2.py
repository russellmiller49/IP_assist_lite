from __future__ import annotations

import logging
import os
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
    def medcpt_query_encode(_: str):
        return [0.0] * 768
from .router import RouterDecision, choose_store

LOGGER = logging.getLogger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLL_NAME = os.getenv("QDRANT_COLLECTION_V2", "ip_docs_v2")

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def _search_named(q: str, target_vector: str, top_k: int = 8) -> List[Dict[str, Any]]:
    q_emb = medcpt_query_encode(q).tolist()
    hits = client.search(
        collection_name=COLL_NAME,
        query_vector=(target_vector, q_emb),
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
            return {
                "store": store,
                "results": res,
                "router_confidence": decision.confidence,
                "medparse_terms": medparse_terms,
            }
    return {
        "store": "chunks",
        "results": _search_named(expanded_query, "chunks", top_k=top_k),
        "router_confidence": decision.confidence,
        "medparse_terms": medparse_terms,
    }
