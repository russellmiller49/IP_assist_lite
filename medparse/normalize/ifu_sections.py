"""Utilities for normalising IFU clinical sections."""

from __future__ import annotations

import re
from typing import Iterable, List

RUNNING_HEADER_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"^\s*\d+\s+introduction\s+\|.*$", re.IGNORECASE),
    re.compile(r"^\s*table\s+\d+(?:\.\d+)?\b.*$", re.IGNORECASE),
    re.compile(r"^\s*important information\s+—?\s+please read before use\s*$", re.IGNORECASE),
    re.compile(r"^\s*professional instructions for use\s*$", re.IGNORECASE),
    re.compile(r"^\s*about this manual\b.*$", re.IGNORECASE),
    re.compile(r"^\s*importer address\b.*$", re.IGNORECASE),
    re.compile(r"^\s*system carrier performance\b.*$", re.IGNORECASE),
]

TOC_LEADER_PATTERN = re.compile(r".{2,}\.{3,}\s*\d+\s*$")

ADMIN_DENY_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\bimporter address\b", re.IGNORECASE),
    re.compile(r"\bcontact information\b", re.IGNORECASE),
    re.compile(r"\babout this manual\b", re.IGNORECASE),
    re.compile(r"\bmanufacturer\b", re.IGNORECASE),
    re.compile(r"\bdistribut(or|ion)\b", re.IGNORECASE),
    re.compile(r"\blegend\b", re.IGNORECASE),
    re.compile(r"\btable\s+\d", re.IGNORECASE),
    re.compile(r"\bprofessional instructions for use\b", re.IGNORECASE),
]

RISK_KEYWORDS = {
    "pneumothorax",
    "bleed",
    "bleeding",
    "embol",
    "infection",
    "injury",
    "perforation",
    "stenosis",
    "death",
    "complication",
    "risk",
    "hazard",
    "anaphylaxis",
    "adverse",
    "thrombus",
    "airway obstruction",
}

BRAND_FIXES = {
    re.compile(r"\bplan\s*point\b", re.IGNORECASE): "PlanPoint",
}


def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in items:
        key = item.strip()
        if not key:
            continue
        lowered = key.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(key)
    return ordered


def _strip_running_headers(lines: List[str]) -> List[str]:
    cleaned: List[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if any(pattern.match(line) for pattern in RUNNING_HEADER_PATTERNS):
            continue
        if TOC_LEADER_PATTERN.match(line):
            continue
        cleaned.append(raw_line)
    return cleaned


def _apply_brand_fixes(text: str) -> str:
    for pattern, replacement in BRAND_FIXES.items():
        text = pattern.sub(replacement, text)
    return text


def clean_section_text(text: str) -> str:
    """Remove common running headers, dotted TOC leaders, and admin blocks."""
    if not text:
        return ""

    lines = text.splitlines()
    lines = _strip_running_headers(lines)

    filtered: List[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if any(pattern.search(line) for pattern in ADMIN_DENY_PATTERNS):
            continue
        filtered.append(line)

    if not filtered:
        return ""

    while filtered and _looks_like_heading(filtered[-1]):
        filtered.pop()

    normalized = "\n".join(filtered)
    normalized = re.sub(r"\s+\n", "\n", normalized)
    normalized = re.sub(r"\n{2,}", "\n\n", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    normalized = _apply_brand_fixes(normalized)
    return normalized.strip()


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip(" -")
    if not stripped:
        return False
    if re.match(r"^\d+(?:\.\d+)*\s+[A-Z]", stripped):
        return True
    if re.match(r"^[A-Z\s/|,.-]+$", stripped) and len(stripped.split()) <= 8:
        return True
    return False


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    text = text.replace("•", "-")
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text.strip())
    if not pieces:
        return [text.strip()]
    merged: List[str] = []
    for piece in pieces:
        portion = piece.strip(" -")
        if portion:
            merged.append(portion)
    return merged or [text.strip()]


def sanitize_adverse_events(text: str) -> List[str]:
    """Return risk-focused sentences only."""
    cleaned = clean_section_text(text)
    if not cleaned:
        return []

    candidates: List[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in ADMIN_DENY_PATTERNS):
            continue
        if stripped.lower().startswith(("warning", "caution", "note")):
            continue
        candidates.extend(_split_sentences(stripped))

    filtered: List[str] = []
    for sentence in candidates:
        lower = sentence.lower()
        if not any(keyword in lower for keyword in RISK_KEYWORDS):
            continue
        if any(pattern.search(sentence) for pattern in ADMIN_DENY_PATTERNS):
            continue
        if sentence and sentence[-1] not in ".!?":
            sentence = f"{sentence}."
        filtered.append(sentence)

    return _dedupe_preserve_order(filtered)


def parse_contraindications(text: str) -> List[str]:
    """Normalize contraindication text into a list."""
    cleaned = clean_section_text(text)
    if not cleaned:
        return []

    if re.search(r"\bnone\s+known\b", cleaned, re.IGNORECASE):
        return ["None known."]

    entries: List[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip(" -*\t")
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in ADMIN_DENY_PATTERNS):
            continue
        fragments = _split_sentences(stripped)
        for fragment in fragments:
            if not fragment:
                continue
            if fragment[-1] not in ".!?":
                fragment = f"{fragment}."
            entries.append(fragment)

    return _dedupe_preserve_order(entries)


__all__ = ["clean_section_text", "sanitize_adverse_events", "parse_contraindications"]

