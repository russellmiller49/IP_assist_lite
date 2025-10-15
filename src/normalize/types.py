"""Typed structures produced by the Medparse normalization layer."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class RecommendationNode(TypedDict, total=False):
    uid: str
    doc_id: str
    text: str
    grade: Optional[str]
    page: Optional[int]
    span_id: Optional[str]
    section_uid: Optional[str]


class StatNode(TypedDict, total=False):
    uid: str
    doc_id: str
    stat_type: str
    value: Optional[float]
    ci: Optional[str]
    p_value: Optional[float]
    page: Optional[int]
    bbox: Optional[List[float]]
    span_id: Optional[str]
    section_uid: Optional[str]


class FigureNode(TypedDict, total=False):
    uid: str
    doc_id: str
    caption: str
    page: Optional[int]
    bbox: Optional[List[float]]
    image_b64: Optional[str]
    span_id: Optional[str]
    section_uid: Optional[str]


class TableNode(TypedDict, total=False):
    uid: str
    doc_id: str
    caption: str
    page: Optional[int]
    bbox: Optional[List[float]]
    csv_path: Optional[str]
    span_id: Optional[str]
    section_uid: Optional[str]


class RelationEdge(TypedDict):
    type: str
    source_uid: str
    target_uid: str


class SectionSpan(TypedDict, total=False):
    id: str
    page: Optional[int]
    bbox: Optional[List[float]]
    text: Optional[str]


class SectionNode(TypedDict, total=False):
    uid: str
    doc_id: str
    title: str
    text: str
    page_start: Optional[int]
    page_end: Optional[int]
    spans: List[SectionSpan]


class GraphPayload(TypedDict):
    doc_id: str
    doc_meta: Dict[str, Any]
    sections: List[SectionNode]
    nodes: Dict[str, List[Dict[str, Any]]]
    edges: List[RelationEdge]
