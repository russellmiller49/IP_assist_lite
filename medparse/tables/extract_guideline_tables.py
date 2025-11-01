"""Harvest grade metadata from guideline summary tables."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from medparse.guideline.grade_map import map_consensus, map_grade_strength, map_sign_letter
from medparse.schema.article import EnhancedTable

LABEL_RE = re.compile(
    r"(?i)\b(?:recommendation|statement)\s*([0-9]+(?:\.[0-9]+)*)"
)
LEADING_NUMBER_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)*)")
CONSENSUS_TOKENS = re.compile(r"(?i)\b(ucs|consensus|good\s+practice|best\s+practice)\b")


@dataclass
class TableGradeIndex:
    """Lookup structures for table-sourced grade metadata."""

    by_label: Dict[str, List[Dict[str, object]]] = field(default_factory=dict)
    by_signature: Dict[str, List[Dict[str, object]]] = field(default_factory=dict)
    matched_tables: List[str] = field(default_factory=list)

    def extend(self, label: Optional[str], signature: str, payload: Dict[str, object]) -> None:
        _append_unique(self.by_signature, signature, payload)
        if label:
            _append_unique(self.by_label, label, payload)


def extract_guideline_grade_index(
    tables: Sequence[EnhancedTable],
    *,
    signature_fn: Callable[[str], str],
) -> TableGradeIndex:
    index = TableGradeIndex()
    if not tables:
        return index

    for table in tables:
        headers = _resolve_headers(table.headers)
        if not headers:
            continue
        rec_idx = _first_match(headers, {"recommendation", "statement"})
        strength_idx = _first_match(headers, {"strength"})
        grade_idx = _first_match(headers, {"grade"})
        certainty_idx = _first_match(headers, {"certainty", "quality"})
        if rec_idx is None or certainty_idx is None or (strength_idx is None and grade_idx is None):
            continue

        table_label = table.label or table.caption or f"table_{table.page or 'x'}"
        index.matched_tables.append(str(table_label))

        for row in table.rows or []:
            if not isinstance(row, (list, tuple)):
                continue
            row_cells = list(row)
            while len(row_cells) < len(headers):
                row_cells.append("")
            rec_text = str(row_cells[rec_idx] or "").strip()
            if not rec_text:
                continue
            label = _extract_label(rec_text)
            signature = signature_fn(rec_text)

            raw_grade = str(row_cells[grade_idx]).strip() if grade_idx is not None and grade_idx < len(row_cells) else ""
            raw_strength = str(row_cells[strength_idx]).strip() if strength_idx is not None and strength_idx < len(row_cells) else ""
            raw_certainty = str(row_cells[certainty_idx]).strip() if certainty_idx < len(row_cells) else ""

            candidates = _row_candidates(raw_grade, raw_strength, raw_certainty)
            for payload in candidates:
                payload.setdefault("source", "table")
                payload.setdefault("confidence", 0.8)
                index.extend(label, signature, payload)

    return index


def _append_unique(bucket: Dict[str, List[Dict[str, object]]], key: str, payload: Dict[str, object]) -> None:
    existing = bucket.setdefault(key, [])
    for candidate in existing:
        if _candidate_equal(candidate, payload):
            return
    existing.append(payload)


def _candidate_equal(left: Dict[str, object], right: Dict[str, object]) -> bool:
    comparable_keys = ("scale", "strength", "letter", "certainty", "ungraded", "source")
    return all(left.get(key) == right.get(key) for key in comparable_keys)


def _resolve_headers(headers: Sequence[Sequence[str]]) -> List[str]:
    if not headers:
        return []
    if len(headers) == 1:
        return [str(cell or "").strip() for cell in headers[0]]
    depth = max(len(row) for row in headers)
    resolved: List[str] = []
    for col in range(depth):
        parts: List[str] = []
        for row in headers:
            if col < len(row):
                cell = row[col]
                if cell:
                    parts.append(str(cell).strip())
        resolved.append(" ".join(parts).strip())
    return resolved


def _first_match(headers: Sequence[str], keywords: Iterable[str]) -> Optional[int]:
    lowered = [header.lower() for header in headers]
    for idx, header in enumerate(lowered):
        for keyword in keywords:
            if keyword in header:
                return idx
    return None


def _extract_label(text: str) -> Optional[str]:
    match = LABEL_RE.search(text)
    if match:
        return match.group(1)
    leading = LEADING_NUMBER_RE.search(text)
    if leading:
        return leading.group(1)
    return None


def _row_candidates(grade: str, strength: str, certainty: str) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    grade_clean = grade.strip()
    strength_clean = strength.strip()
    certainty_clean = certainty.strip()

    if grade_clean:
        # Prioritise consensus tokens first
        if CONSENSUS_TOKENS.search(grade_clean):
            candidates.append(map_consensus(source="table", confidence=0.78, raw=grade_clean))
        else:
            letter_match = re.match(r"^\s*([ABCD])\s*$", grade_clean, re.IGNORECASE)
            if letter_match:
                mapped = map_sign_letter(letter_match.group(1), source="table", confidence=0.82, raw=grade_clean)
                if mapped:
                    candidates.append(mapped)
            else:
                mapped = map_grade_strength(grade_clean, certainty_clean or None, source="table", confidence=0.8, raw=grade_clean)
                if mapped:
                    candidates.append(mapped)

    if strength_clean:
        mapped = map_grade_strength(strength_clean, certainty_clean or None, source="table", confidence=0.8, raw=strength_clean)
        if mapped:
            candidates.append(mapped)

    if certainty_clean and not candidates:
        mapped = map_grade_strength(None, certainty_clean, source="table", confidence=0.78, raw=certainty_clean)
        if mapped:
            candidates.append(mapped)

    if not candidates and CONSENSUS_TOKENS.search(strength_clean):
        candidates.append(map_consensus(source="table", confidence=0.76, raw=strength_clean))

    if not candidates and CONSENSUS_TOKENS.search(certainty_clean):
        candidates.append(map_consensus(source="table", confidence=0.74, raw=certainty_clean))

    return _deduplicate_payloads(candidates)


def _deduplicate_payloads(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
    unique: List[Dict[str, object]] = []
    seen: set[tuple] = set()
    for payload in items:
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
        unique.append(payload)
    return unique


__all__ = ["TableGradeIndex", "extract_guideline_grade_index"]
