from __future__ import annotations
import os
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from .router import choose_store, RouterDecision

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLL_NAME   = os.getenv("QDRANT_COLLECTION_V2", "ip_docs_v2")

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# ADAPT these imports to your repo
from src.index.embedders import medcpt_query_encode

def _search_named(q: str, target_vector: str, top_k=8):
    q_emb = medcpt_query_encode(q).tolist()
    hits = client.search(
        collection_name=COLL_NAME,
        query_vector=(target_vector, q_emb),
        limit=top_k,
        with_payload=True
    )
    return [{
        "id": h.payload.get("chunk_id", h.id),
        "score": h.score,
        "text": h.payload.get("text") or h.payload.get("quote_text") or h.payload.get("summary_text",""),
        "payload": h.payload
    } for h in hits]

def _coverage(results: List[Dict[str,Any]]) -> float:
    if not results: return 0.0
    top = sorted((r["score"] for r in results), reverse=True)[:3]
    return sum(top)/len(top)

async def retrieve_with_fallback(query: str, top_k=8, score_threshold=0.32) -> Dict[str,Any]:
    decision: RouterDecision = choose_store(query)
    order = [decision.store] + [s for s in ["quotes","summaries","chunks"] if s != decision.store]
    for store in order:
        res = _search_named(query, store, top_k=top_k)
        if _coverage(res) >= score_threshold or store == "chunks":
            return {"store": store, "results": res, "router_confidence": decision.confidence}
    return {"store":"chunks", "results": _search_named(query, "chunks", top_k=top_k), "router_confidence": decision.confidence}