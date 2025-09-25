"""Utilities for translating Medparse payloads into graph-friendly structures."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, TypedDict


class EvidenceSummary(TypedDict):
    statistics: int
    figures: int
    tables: int


class ConceptRecord(TypedDict, total=False):
    cui: str
    label: str
    text: str
    tui: List[str]
    score: float
    sources: List[str]


class MedparseGraphPayload(TypedDict, total=False):
    doc_id: str
    metadata: Dict[str, Any]
    concepts: List[ConceptRecord]
    statistics: List[Dict[str, Any]]
    figures: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    references: List[Dict[str, Any]]
    validation: Dict[str, Any]
    evidence: EvidenceSummary


@dataclass
class _ConceptAccumulator:
    cui: str
    label: str
    text: str
    tui: List[str]
    score: float
    sources: List[str]

    def to_record(self) -> ConceptRecord:
        return {
            "cui": self.cui,
            "label": self.label,
            "text": self.text,
            "tui": list(self.tui),
            "score": self.score,
            "sources": list(dict.fromkeys(self.sources)),
        }


def _normalize_concept(raw: Mapping[str, Any]) -> _ConceptAccumulator:
    cui = str(raw.get("cui", "")).strip()
    text = str(raw.get("text", "")).strip()
    label = str(raw.get("preferred_name") or text).strip()
    tui_raw = raw.get("tui") or raw.get("tuis") or raw.get("semtypes") or []
    if isinstance(tui_raw, str):
        tui = [tui_raw]
    else:
        tui = [str(t).strip() for t in tui_raw if str(t).strip()]
    sources: List[str] = []
    source = raw.get("source")
    if source:
        sources.append(str(source))
    score_val = raw.get("score", 0.0)
    try:
        score = float(score_val)
    except (TypeError, ValueError):
        score = 0.0
    return _ConceptAccumulator(
        cui=cui,
        label=label or text or cui,
        text=text or label,
        tui=tui,
        score=score,
        sources=sources,
    )


def _dedupe_concepts(concepts: Iterable[Mapping[str, Any]]) -> List[ConceptRecord]:
    merged: Dict[str, _ConceptAccumulator] = {}
    for raw in concepts:
        acc = _normalize_concept(raw)
        key = acc.cui or acc.label.lower()
        existing = merged.get(key)
        if not existing:
            merged[key] = acc
            continue
        if len(acc.label) > len(existing.label):
            existing.label = acc.label
        if len(acc.text) > len(existing.text):
            existing.text = acc.text
        if acc.score > existing.score:
            existing.score = acc.score
        for tui in acc.tui:
            if tui not in existing.tui:
                existing.tui.append(tui)
        for source in acc.sources:
            if source not in existing.sources:
                existing.sources.append(source)
    return [bucket.to_record() for bucket in merged.values()]


def summarise_evidence(payload: Mapping[str, Any]) -> EvidenceSummary:
    """Return counts required by the UI evidence panel."""

    statistics = payload.get("statistics") or []
    figures = payload.get("figures") or []
    tables = payload.get("tables") or []
    return {
        "statistics": len(statistics),
        "figures": len(figures),
        "tables": len(tables),
    }


def build_graph_payload(extraction_result: Mapping[str, Any]) -> MedparseGraphPayload:
    """Convert a Medparse extraction payload into a graph-friendly structure."""

    doc_id = extraction_result.get("doc_id")
    if not doc_id:
        raise ValueError("Medparse extraction payload is missing 'doc_id'")

    metadata = extraction_result.get("metadata") or {}
    statistics = list(extraction_result.get("statistics") or [])
    figures = list(extraction_result.get("figures") or [])
    tables = list(extraction_result.get("tables") or [])
    references = list(extraction_result.get("references_enriched") or [])
    validation = extraction_result.get("validation") or {}

    concepts_primary = extraction_result.get("umls_links") or []
    concepts_fallback = extraction_result.get("umls_links_local") or []
    concepts = _dedupe_concepts([*concepts_primary, *concepts_fallback])

    return {
        "doc_id": str(doc_id),
        "metadata": dict(metadata),
        "concepts": concepts,
        "statistics": statistics,
        "figures": figures,
        "tables": tables,
        "references": references,
        "validation": dict(validation),
        "evidence": summarise_evidence(extraction_result),
    }


__all__ = [
    "build_graph_payload",
    "summarise_evidence",
    "MedparseGraphPayload",
    "ConceptRecord",
    "EvidenceSummary",
]
