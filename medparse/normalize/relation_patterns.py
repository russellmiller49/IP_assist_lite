"""Pattern bundle for heuristic relation extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple


@dataclass(frozen=True)
class RelationPattern:
    predicate: str
    keywords: Tuple[str, ...]
    confidence: float = 0.65


PATTERNS: Sequence[RelationPattern] = (
    RelationPattern(
        predicate="treated_with",
        keywords=(
            "treated with",
            "therapy with",
            "treatment with",
            "managed with",
            "receives",
            "administered",
        ),
        confidence=0.82,
    ),
    RelationPattern(
        predicate="diagnosed_by",
        keywords=(
            "diagnosed by",
            "identified by",
            "confirmed by",
            "detected by",
        ),
        confidence=0.78,
    ),
    RelationPattern(
        predicate="risk_factor_for",
        keywords=(
            "risk factor for",
            "risk for",
            "predisposes",
            "increase the risk",
        ),
        confidence=0.7,
    ),
    RelationPattern(
        predicate="requires",
        keywords=(
            "requires",
            "necessitates",
            "needs",
            "dependent on",
        ),
        confidence=0.68,
    ),
    RelationPattern(
        predicate="associated_with",
        keywords=(
            "associated with",
            "related to",
            "correlated with",
            "linked to",
        ),
        confidence=0.64,
    ),
    RelationPattern(
        predicate="prognostic_factor_for",
        keywords=(
            "prognostic factor",
            "predicts",
            "indicator of outcome",
        ),
        confidence=0.72,
    ),
    RelationPattern(
        predicate="subtype_of",
        keywords=(
            "subtype of",
            "type of",
            "variant of",
            "form of",
        ),
        confidence=0.66,
    ),
)

NEGATION_TERMS = ("no", "not", "without", "absence", "lacks", "lack")
CONDITIONAL_TERMS = ("if", "when", "whenever", "unless", "until")
TEMPORAL_TERMS = (
    ("before", "before"),
    ("after", "after"),
    ("during", "during"),
    ("prior to", "before"),
    ("following", "after"),
)


def detect_pattern(text: str) -> RelationPattern | None:
    lowered = text.lower()
    for pattern in PATTERNS:
        if any(keyword in lowered for keyword in pattern.keywords):
            return pattern
    return None


def detect_negation(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in NEGATION_TERMS)


def detect_conditional(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in CONDITIONAL_TERMS)


def detect_temporal(text: str) -> str | None:
    lowered = text.lower()
    for cue, label in TEMPORAL_TERMS:
        if cue in lowered:
            return label
    return None


__all__ = [
    "RelationPattern",
    "detect_pattern",
    "detect_negation",
    "detect_conditional",
    "detect_temporal",
]
