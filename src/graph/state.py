from __future__ import annotations
from typing import List, Dict, Any, TypedDict

class IPState(TypedDict, total=False):
    query: str
    config: Dict[str, Any]

    plan: Dict[str, Any]
    facets_needed: List[str]
    missing_facets: List[str]
    facets_covered: List[str]

    retrieved_chunks: List[Dict[str,Any]]
    answer_sentences: List[str]
    sentence_citations: List[str]
    sentence_confidences: List[float]
    needs_rewrite: bool

    temporal_context: Dict[str,int]
    replan_count: int
    max_replans: int