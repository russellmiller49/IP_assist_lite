"""Helpers for parsing and normalizing guideline recommendation grades."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

CHEST_UNGRADED_PATTERN = re.compile(
    r"^Ungraded\s+Consensus-?Based\s+Statement$", re.IGNORECASE
)

STRENGTH_PATTERN = r"(?P<strength>strong|weak|conditional)\s+recommendation"
QUALITY_PATTERN = r"(?P<quality>very\s+low|low|moderate|high)\s*[-–\s]*quality\s+evidence"
GRADE_RX = re.compile(
    rf"\b{STRENGTH_PATTERN}(?:[,;]?\s+{QUALITY_PATTERN})?", re.IGNORECASE
)

QUALITY_KEYWORDS = {
    "high": "high",
    "moderate": "moderate",
    "low": "low",
    "very low": "very_low",
}


_GRADE_LEXICON_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "guideline_grade_lexicon.yaml"
_LEXICON_CACHE: Optional[List[Dict[str, Any]]] = None


def _load_grade_lexicon() -> List[Dict[str, Any]]:
    global _LEXICON_CACHE
    if _LEXICON_CACHE is not None:
        return _LEXICON_CACHE

    entries: List[Dict[str, Any]] = []
    if not _GRADE_LEXICON_PATH.exists():
        _LEXICON_CACHE = entries
        return entries

    try:
        raw_data = yaml.safe_load(_GRADE_LEXICON_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        _LEXICON_CACHE = entries
        return entries

    if not isinstance(raw_data, dict):
        _LEXICON_CACHE = entries
        return entries

    for key, block in raw_data.items():
        if isinstance(block, dict):
            scale = str(block.get("scale") or key or "").strip().upper() or key.upper()
            source = str(block.get("source") or "lexicon")
            entry_list = block.get("entries")
            if not isinstance(entry_list, list):
                continue
        elif isinstance(block, list):
            scale = str(key or "").strip().upper() or key.upper()
            source = "lexicon"
            entry_list = block
        else:
            continue
        for entry in entry_list:
            if not isinstance(entry, dict):
                continue
            pattern = entry.get("pattern")
            mapping = entry.get("map")
            if not isinstance(pattern, str) or not pattern.strip():
                continue
            if not isinstance(mapping, dict):
                continue
            flags = re.IGNORECASE
            flags_value = entry.get("flags")
            if isinstance(flags_value, str) and "m" in flags_value.lower():
                flags |= re.MULTILINE
            try:
                compiled = re.compile(pattern, flags)
            except re.error:
                continue
            entries.append(
                {
                    "pattern": compiled,
                    "map": mapping,
                    "scale": scale,
                    "source": source,
                }
            )

    _LEXICON_CACHE = entries
    return entries


def _normalize_strength(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"strong", "strong recommendation"}:
        return "strong"
    if lowered in {"weak", "conditional", "conditional recommendation"}:
        return "weak"
    return lowered or None


def _normalize_certainty(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"high", "moderate", "low", "very low"}:
        return lowered.replace(" ", "_")
    return lowered or None


def detect_grade_from_lexicon(
    text: Optional[str],
    *,
    scale_hint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    candidate = text.strip()
    if not candidate:
        return None

    lexicon = _load_grade_lexicon()
    if not lexicon:
        return None

    preferred_scale = scale_hint.upper() if isinstance(scale_hint, str) and scale_hint else None
    for entry in lexicon:
        scale = entry.get("scale")
        if preferred_scale and scale and scale != preferred_scale:
            continue
        match = entry["pattern"].search(candidate)
        if not match:
            continue
        mapping = entry.get("map", {})
        payload: Dict[str, Any] = {
            "source": entry.get("source") or "lexicon",
            "scale": scale or preferred_scale or "CHEST",
            "raw": match.group(0).strip(),
        }
        for key, value in mapping.items():
            if isinstance(value, str):
                try:
                    resolved = match.expand(value).strip()
                except re.error:
                    resolved = value.strip()
            else:
                resolved = value
            if key in {"strength", "strength_value"}:
                payload["strength"] = _normalize_strength(resolved if isinstance(resolved, str) else None)
            elif key in {"certainty", "quality"}:
                certainty = _normalize_certainty(resolved if isinstance(resolved, str) else None)
                if certainty:
                    payload["certainty"] = certainty
                    payload["quality"] = certainty
                    payload["evidence_quality"] = certainty
            elif key == "normalized" and isinstance(resolved, str):
                payload["normalized"] = resolved
            elif key == "ungraded":
                payload["ungraded"] = bool(resolved)
            elif isinstance(key, str):
                payload[key] = resolved

        strength = payload.get("strength")
        certainty = payload.get("certainty")
        scale_value = payload.get("scale")
        if strength:
            payload.setdefault("value", strength)
        if strength and certainty and isinstance(scale_value, str):
            payload["normalized"] = f"{scale_value}:{strength.title()}/{certainty.replace('_', ' ').title()}"
        if "normalized" not in payload and isinstance(scale_value, str):
            payload["normalized"] = scale_value
        return payload

    return None


def parse_grade_phrase(text: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
    """Parse a CHEST/GRADE-style strength + quality phrase with tolerant spacing."""

    if not text:
        return None

    match = GRADE_RX.search(text)
    if not match:
        return None

    strength_token = (match.group("strength") or "").strip().lower()
    quality_token = match.group("quality")

    if not strength_token:
        return None

    strength_normalized = "strong" if strength_token == "strong" else "weak"
    if strength_token == "conditional":
        strength_normalized = "weak"

    quality_normalized: Optional[str] = None
    if quality_token:
        normalized = re.sub(r"[-–]+", " ", quality_token.lower()).strip()
        quality_normalized = QUALITY_KEYWORDS.get(normalized)

    raw_phrase = match.group(0).strip(" ,.;")

    payload: Dict[str, Optional[str]] = {
        "scale": "GRADE",
        "strength": strength_normalized,
        "quality": quality_normalized,
        "raw": raw_phrase,
    }
    return payload


def _normalize_quality(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.lower()
    for phrase, normalized in QUALITY_KEYWORDS.items():
        if phrase in lowered:
            return normalized
    quality_match = re.search(r"grade\s+([a-d])", lowered)
    if quality_match:
        letter = quality_match.group(1)
        if letter in {"a", "b"}:
            return "high"
        if letter == "c":
            return "moderate"
        return "low"
    return None


def normalize_grade(
    grade_raw: Optional[str],
    strength: Optional[str],
    evidence_level: Optional[str],
    scale_hint: Optional[str] = None,
    *,
    text: Optional[str] = None,
) -> Optional[Dict[str, Optional[str]]]:
    """Normalize guideline grading metadata into strength/quality/scale."""

    grade_info = parse_grade_phrase(grade_raw) or parse_grade_phrase(text)
    if grade_info:
        normalized: Dict[str, Optional[str]] = {
            "scale": grade_info.get("scale") or "GRADE",
            "strength": grade_info.get("strength"),
            "quality": grade_info.get("quality"),
            "raw": grade_info.get("raw"),
        }
        if grade_info.get("quality"):
            normalized["evidence_quality"] = grade_info["quality"]
        # Remove None before returning
        return {k: v for k, v in normalized.items() if v is not None}

    normalized: Dict[str, Optional[str]] = {}

    if strength:
        normalized["strength"] = strength.lower()

    quality = _normalize_quality(evidence_level)
    if quality:
        normalized["quality"] = quality
        normalized["evidence_quality"] = quality

    scale_value = scale_hint.upper() if scale_hint else None

    if grade_raw:
        grade_clean = grade_raw.strip()
        if CHEST_UNGRADED_PATTERN.match(grade_clean):
            normalized["strength"] = "ungraded"
            normalized["scale"] = "Consensus"
            return normalized

        grade_upper = grade_clean.upper()
        if grade_upper in {"A", "B", "C", "D"}:
            scale_value = "SIGN"
            normalized.setdefault(
                "strength",
                "strong" if grade_upper in {"A", "B"} else "weak",
            )
        elif grade_upper.startswith("1"):
            scale_value = scale_value or "GRADE"

    if scale_value:
        normalized["scale"] = scale_value
    elif normalized:
        normalized.setdefault("scale", "GRADE" if normalized.get("quality") else None)

    return {key: value for key, value in normalized.items() if value is not None} or None


__all__ = ["normalize_grade", "parse_grade_phrase", "detect_grade_from_lexicon"]
