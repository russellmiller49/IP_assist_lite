"""Lightweight rule-based relation extraction for enriched documents."""

from __future__ import annotations

from itertools import combinations
from typing import Dict, Iterable, List, Optional, Union

from pydantic import BaseModel, Field


class RelationRecord(BaseModel):
    """Normalized triple with optional attributes and evidence text."""

    subject: str
    predicate: str
    object: str
    attributes: Dict[str, object] = Field(default_factory=dict)
    evidence: Optional[str] = None


def relations_from_outcomes(
    procedure_name: str,
    outcomes: Iterable[dict],
) -> List[Relation]:
    """Generate ``has_complication`` relations from outcome records."""

    relations: List[RelationRecord] = []
    for outcome in outcomes:
        name = outcome.get("name")
        if not name:
            continue

        attributes: Dict[str, object] = {}
        for key in ("percent", "value", "n", "denominator", "ci_lower", "ci_upper"):
            if outcome.get(key) is not None:
                attributes[key] = outcome[key]

        evidence = None
        evidence_data = outcome.get("evidence")
        if isinstance(evidence_data, dict):
            evidence = evidence_data.get("text")

        relations.append(
            RelationRecord(
                subject=procedure_name,
                predicate="has_complication",
                object=name,
                attributes=attributes,
                evidence=evidence,
            )
        )
    return relations


def relations_from_recommendations(
    guideline_title: str,
    recommendations: Iterable[dict],
) -> List[Relation]:
    """Generate ``recommends`` relations from guideline recommendations."""

    relations: List[RelationRecord] = []
    for rec in recommendations:
        text = rec.get("text")
        if not text:
            continue

        attributes: Dict[str, object] = {}
        for key in ("grade", "strength", "evidence_level", "statement_type", "votes"):
            value = rec.get(key)
            if value:
                attributes[key] = value

        evidence = None
        evidence_data = rec.get("evidence")
        if isinstance(evidence_data, dict):
            evidence = evidence_data.get("text")

        relations.append(
            RelationRecord(
                subject=guideline_title,
                predicate="recommends",
                object=text,
                attributes=attributes,
                evidence=evidence,
            )
        )
    return relations


def build_relations(
    *,
    title: str,
    outcomes: Iterable[dict] | None = None,
    recommendations: Iterable[dict] | None = None,
) -> List[RelationRecord]:
    """Convenience wrapper combining outcome and recommendation relations."""

    relations: List[RelationRecord] = []
    if outcomes:
        relations.extend(relations_from_outcomes(title, outcomes))
    if recommendations:
        relations.extend(relations_from_recommendations(title, recommendations))
    return relations


def build_cooccurrence(
    entities: Iterable[dict],
    *,
    window: Union[str, int] = "page",
) -> List[RelationRecord]:
    """Build simple co-occurrence edges between UMLS entities."""

    grouped: Dict[Optional[int], List[dict]] = {}
    for entity in entities:
        page = entity.get("page") if isinstance(entity, dict) else None
        grouped.setdefault(page, []).append(entity)

    relations: List[RelationRecord] = []
    dedupe: set[tuple[str, str, Optional[int]]] = set()
    window_tokens = window if isinstance(window, int) and window > 0 else None
    window_label: str = "token" if window_tokens else str(window)

    for page, items in grouped.items():
        if len(items) < 2:
            continue
        for left, right in combinations(items, 2):
            cui_left = left.get("cui") if isinstance(left, dict) else None
            cui_right = right.get("cui") if isinstance(right, dict) else None
            if not cui_left or not cui_right or cui_left == cui_right:
                continue

            key = tuple(sorted((cui_left, cui_right))) + (page,)
            if key in dedupe:
                continue
            dedupe.add(key)

            if window_tokens:
                left_offsets = left.get("offsets") or []
                right_offsets = right.get("offsets") or []
                if left_offsets and right_offsets:
                    min_distance = min(
                        abs(l_start - r_start)
                        for l_start, _ in left_offsets
                        for r_start, _ in right_offsets
                    )
                    approx_tokens = max(1, min_distance // 5)
                    if approx_tokens > window_tokens:
                        continue

            evidence = None
            if window_tokens:
                evidence = f"token_window<={window_tokens}"
            elif window == "page":
                evidence = f"page {page} co-mention"
            elif window == "evidence_span":
                evidence = " | ".join(
                    filter(None, (left.get("text"), right.get("text")))
                ) or None

            attributes: Dict[str, object] = {"page": page, "window": window_label}
            if window_tokens:
                attributes["window_tokens"] = window_tokens

            relations.append(
                RelationRecord(
                    subject=cui_left,
                    predicate="co_occurs_with",
                    object=cui_right,
                    attributes=attributes,
                    evidence=evidence,
                )
            )

    return relations


__all__ = [
    "RelationRecord",
    "build_relations",
    "build_cooccurrence",
    "relations_from_outcomes",
    "relations_from_recommendations",
]
