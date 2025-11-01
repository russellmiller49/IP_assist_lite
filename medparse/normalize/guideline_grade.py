"""Grade detection helpers for guideline recommendations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from medparse.guideline.grade_map import (
    build_envelope,
    map_consensus,
    map_grade_code,
    map_grade_strength,
    map_sign_letter,
)

SIGN_INLINE_RE = re.compile(r"(?i)\brecommendation\s+grade\s*([ABCD])\b")
CHEST_GRADE_RE = re.compile(r"(?i)\bgrade\s*(?:recommendation\s*)?([12])\s*([ABCD])\b")
GRADE_PAIR_RE = re.compile(
    r"(?i)\b(strong|conditional|weak)\s+recommendation(?:s?)\b"
    r"(?:(?:\s|,|;|:|and|with){0,5}[^.;()]{0,60})?"
    r"\b(very\s*low|low|moderate|high)\s+(?:certainty|quality)"
    r"(?:\s+(?:of|in)\s+(?:the\s+)?evidence)?",
)
GRADE_SINGLE_RE = re.compile(
    r"(?i)\b(strong|conditional|weak)\s+recommendation(?:s?)\b"
)
CONSENSUS_RE = re.compile(
    r"(?i)\b("
    r"ungraded\s+consensus(?:-?based)?\s+statement"
    r"|ungraded\s+consensus"
    r"|good\s+practice\s+statement"
    r"|best\s+practice\s+statement"
    r"|ucs\b"
    r")",
)


@dataclass
class GradeCandidate:
    payload: dict
    raw: Optional[str] = None

    @property
    def scale(self) -> str:
        return str(self.payload.get("scale") or "")

    @property
    def source(self) -> str:
        return str(self.payload.get("source") or "")

    @property
    def confidence(self) -> float:
        try:
            return float(self.payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def to_payload(self) -> dict:
        if self.raw and "raw" not in self.payload:
            payload = dict(self.payload)
            payload["raw"] = self.raw
            return payload
        return dict(self.payload)


def detect_inline_candidates(text: Optional[str]) -> List[GradeCandidate]:
    return _detect_candidates(text, source="inline", strength_bias=0.9, letter_bias=0.92, consensus_bias=0.85)


def detect_context_candidates(text: Optional[str]) -> List[GradeCandidate]:
    return _detect_candidates(text, source="context", strength_bias=0.7, letter_bias=0.72, consensus_bias=0.68)


def _detect_candidates(
    text: Optional[str],
    *,
    source: str,
    strength_bias: float,
    letter_bias: float,
    consensus_bias: float,
) -> List[GradeCandidate]:
    if not text:
        return []
    matches: List[GradeCandidate] = []
    for match in SIGN_INLINE_RE.finditer(text):
        payload = map_sign_letter(match.group(1), source=source, confidence=letter_bias, raw=match.group(0))
        if payload:
            matches.append(GradeCandidate(payload=payload, raw=match.group(0)))

    for match in CHEST_GRADE_RE.finditer(text):
        payload = map_grade_code(
            match.group(1),
            match.group(2),
            source=source,
            confidence=max(strength_bias, letter_bias),
            raw=match.group(0),
        )
        if payload:
            matches.append(GradeCandidate(payload=payload, raw=match.group(0)))

    for match in GRADE_PAIR_RE.finditer(text):
        payload = map_grade_strength(
            match.group(1),
            match.group(2),
            source=source,
            confidence=strength_bias,
            raw=match.group(0),
        )
        if payload:
            matches.append(GradeCandidate(payload=payload, raw=match.group(0)))

    # If we saw a strength keyword without certainty, still record the strength-only signal.
    if not any(candidate.scale == "GRADE" for candidate in matches):
        single = GRADE_SINGLE_RE.search(text)
        if single:
            payload = map_grade_strength(
                single.group(1),
                None,
                source=source,
                confidence=strength_bias - 0.05,
                raw=single.group(0),
            )
            if payload:
                matches.append(GradeCandidate(payload=payload, raw=single.group(0)))

    for match in CONSENSUS_RE.finditer(text):
        payload = map_consensus(source=source, confidence=consensus_bias, raw=match.group(0))
        matches.append(GradeCandidate(payload=payload, raw=match.group(0)))

    return _deduplicate(matches)


def _deduplicate(candidates: Sequence[GradeCandidate]) -> List[GradeCandidate]:
    unique: List[GradeCandidate] = []
    seen: set[tuple] = set()
    for candidate in candidates:
        payload = candidate.payload
        key = (
            payload.get("scale"),
            payload.get("strength"),
            payload.get("letter"),
            payload.get("certainty"),
            payload.get("ungraded"),
            payload.get("source"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


__all__ = ["GradeCandidate", "detect_context_candidates", "detect_inline_candidates"]
