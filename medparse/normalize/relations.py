"""Lightweight rule-based relation extraction for enriched documents."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

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
) -> List[Relation]:
    """Convenience wrapper combining outcome and recommendation relations."""

    relations: List[RelationRecord] = []
    if outcomes:
        relations.extend(relations_from_outcomes(title, outcomes))
    if recommendations:
        relations.extend(relations_from_recommendations(title, recommendations))
    return relations


__all__ = [
    "RelationRecord",
    "build_relations",
    "relations_from_outcomes",
    "relations_from_recommendations",
]
