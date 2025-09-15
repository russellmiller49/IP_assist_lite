from __future__ import annotations
from ..state import IPState
from ...retrieval.retriever_v2 import retrieve_with_fallback
from ...utils.text_utils import deduplicate_chunks, extract_temporal_markers
import asyncio

def retrieve_node(state: IPState) -> IPState:
    res = asyncio.run(retrieve_with_fallback(state["query"]))
    deduped = deduplicate_chunks(res["results"])
    state["retrieved_chunks"] = deduped
    state["temporal_context"] = extract_temporal_markers(deduped)
    return state