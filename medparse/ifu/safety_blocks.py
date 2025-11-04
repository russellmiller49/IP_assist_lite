"""Safety block extraction and normalization for IFU documents."""

from __future__ import annotations

import functools
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import yaml

from medparse.ingest.models import PageData
from medparse.schema.common import EvidenceSpan
from medparse.schema.ifu import SafetyBlock

LEVEL_PATTERNS: Dict[str, Sequence[re.Pattern[str]]] = {
    "danger": (
        re.compile(r"\bdanger\b", re.IGNORECASE),
        re.compile(r"\bhazard\b", re.IGNORECASE),
    ),
    "warning": (
        re.compile(r"\bwarning(?:s|s and cautions|s and notes)?\b", re.IGNORECASE),
        re.compile(r"\bgeneral warnings\b", re.IGNORECASE),
        re.compile(r"\bclinical risks?(?:\s+and\s+benefits)?\b", re.IGNORECASE),
        re.compile(r"\bsafety precautions?\b", re.IGNORECASE),
    ),
    "caution": (
        re.compile(r"\bcaution(?:s)?\b", re.IGNORECASE),
        re.compile(r"\bprecaution(?:s)?\b", re.IGNORECASE),
    ),
    "note": (
        re.compile(r"\bnotice\b", re.IGNORECASE),
        re.compile(r"\bimportant\b", re.IGNORECASE),
        re.compile(r"\bnote(?:s)?\b", re.IGNORECASE),
    ),
    "attention": (
        re.compile(r"\battention\b", re.IGNORECASE),
    ),
}

LEVEL_TO_SEVERITY = {
    "danger": "warning",
    "warning": "warning",
    "caution": "caution",
    "note": "note",
    "attention": "warning",
}

ICON_PREFIX_PATTERN = re.compile(r"^[\s\-\u2022\u2023\u25AA\u25CF\u25A0\u25B6\u25C6\u25C7\u25CF\u25A1\u2023●▪■□▶►»⚠!]+")
COLON_HEADER_PATTERN = re.compile(r"^\s*([A-Z][A-Z0-9\s/&\-]+?)\s*[:：]\s*(.*)$")
DASH_HEADER_PATTERN = re.compile(r"^\s*([A-Z][A-Z0-9\s/&\-]+?)\s*[–—\-]\s*(.+)$")
HEADING_WITH_NUMBER_PATTERN = re.compile(r"^\s*\d+(?:\.\d+)*\s+[A-Z]")
UPPERCASE_SECTION_PATTERN = re.compile(r"^[A-Z0-9\s/&,\-]{3,}$")
BULLET_PATTERN = re.compile(
    r"^\s*(?:"
    r"[\-\*\u2022\u2023\u25AA\u25CF\u25A0\u25B6\u25C6\u25C7\u25CF\u25A1\u2023●▪■□▶►»]+"
    r"|(?:\d+|[a-zA-Z])[\.\)])\s+"
)
INDENT_PATTERN = re.compile(r"^\s{2,}")
FOOTER_CLEANUP_PATTERN = re.compile(r"(page\s+\d+(?:\s*/\s*\d+)?|\b\d+\s*/\s*\d+\b)", re.IGNORECASE)

PHRASES_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "ifu_safety_phrases.yaml"


@dataclass(slots=True)
class DetectedHeader:
    level: str
    title: str
    inline_text: str = ""
    lines_consumed: int = 1


@functools.lru_cache(maxsize=1)
def _load_safety_phrases() -> Dict[str, List[str]]:
    if not PHRASES_CONFIG_PATH.exists():
        return {}
    try:
        raw = yaml.safe_load(PHRASES_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    phrases: Dict[str, List[str]] = {}
    for key, values in raw.items():
        if not isinstance(values, list):
            continue
        normalized_values = [str(value).strip() for value in values if str(value).strip()]
        phrases[str(key).upper()] = normalized_values
    return phrases


def extract_safety_blocks(
    pages: Sequence[PageData],
    *,
    manufacturer: Optional[str] = None,
) -> List[SafetyBlock]:
    """Extract safety blocks using severity keywords, vendor phrases, and layout heuristics."""

    blocks: List[SafetyBlock] = []
    seen_hashes: Set[str] = set()
    phrase_set = _combined_phrase_set(manufacturer)

    for page in pages:
        lines = list(page.lines or [])
        idx = 0
        while idx < len(lines):
            header = _detect_header(lines, idx, phrase_set)
            if not header:
                idx += 1
                continue

            content_lines, consumed = _collect_block_lines(lines, idx + header.lines_consumed, phrase_set)
            segments = _build_segments(header, content_lines)

            for segment in segments:
                cleaned_text = _clean_segment_text(segment)
                if not cleaned_text:
                    continue
                block_hash = _hash_block(header.level, cleaned_text)
                if block_hash in seen_hashes:
                    continue
                seen_hashes.add(block_hash)
                title = _normalize_title(header.title) or header.level.title()
                severity = LEVEL_TO_SEVERITY.get(header.level, "warning")
                blocks.append(
                    SafetyBlock(
                        level=header.level,
                        severity=severity,
                        title=title,
                        text=cleaned_text,
                        page=page.number,
                        hash=block_hash,
                        evidence=EvidenceSpan(
                            text=cleaned_text[:200],
                            page=page.number,
                            confidence=0.8,
                        ),
                    )
                )

            idx += header.lines_consumed + consumed

    return blocks


def _combined_phrase_set(manufacturer: Optional[str]) -> Set[str]:
    phrases = _load_safety_phrases()
    combined: Set[str] = {phrase.upper() for phrase in phrases.get("COMMON", [])}
    if manufacturer:
        key = _normalize_vendor_key(manufacturer)
        vendor_phrases = phrases.get(key, []) or phrases.get(manufacturer.strip().upper(), [])
        combined.update(phrase.upper() for phrase in vendor_phrases)
    return combined


def _normalize_vendor_key(value: str) -> str:
    tokens = value.strip().upper().split()
    return tokens[0] if tokens else value.strip().upper()


def _strip_leading_icons(text: str) -> str:
    return ICON_PREFIX_PATTERN.sub("", text or "").strip()


def _sanitize_label(label: str) -> str:
    cleaned = re.sub(r"\s{2,}", " ", label.strip())
    cleaned = cleaned.strip(" -–—|.:")
    return cleaned


def _match_level(label: str) -> Optional[str]:
    for level, patterns in LEVEL_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(label):
                return level
    return None


def _detect_header(
    lines: Sequence[str],
    idx: int,
    phrase_set: Set[str],
) -> Optional[DetectedHeader]:
    if idx >= len(lines):
        return None

    raw_line = lines[idx]
    if not raw_line or not raw_line.strip():
        return None

    candidate = _strip_leading_icons(raw_line)
    if not candidate:
        return None

    inline_text = ""
    label = candidate

    colon_match = COLON_HEADER_PATTERN.match(candidate)
    if colon_match:
        label = colon_match.group(1)
        inline_text = colon_match.group(2).strip()
    else:
        dash_match = DASH_HEADER_PATTERN.match(candidate)
        if dash_match:
            label = dash_match.group(1)
            inline_text = dash_match.group(2).strip()

    label = _sanitize_label(label)
    if not label:
        return None

    level = _match_level(label)
    upper_label = label.upper()
    if not level and upper_label in phrase_set:
        level = "warning"

    if not level:
        return None

    return DetectedHeader(level=level, title=label, inline_text=inline_text, lines_consumed=1)


def _collect_block_lines(
    lines: Sequence[str],
    start_idx: int,
    phrase_set: Set[str],
) -> Tuple[List[str], int]:
    collected: List[str] = []
    consumed = 0
    idx = start_idx
    blanks = 0

    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()
        if not stripped:
            blanks += 1
            collected.append("")
            idx += 1
            consumed += 1
            if blanks >= 2:
                break
            continue

        blanks = 0

        if _is_block_terminator(lines, idx, phrase_set):
            break

        collected.append(raw)
        idx += 1
        consumed += 1

    while collected and not collected[-1].strip():
        collected.pop()

    return collected, consumed


def _is_block_terminator(
    lines: Sequence[str],
    idx: int,
    phrase_set: Set[str],
) -> bool:
    if _detect_header(lines, idx, phrase_set):
        return True

    stripped = lines[idx].strip()
    if HEADING_WITH_NUMBER_PATTERN.match(stripped):
        return True
    if UPPERCASE_SECTION_PATTERN.match(stripped) and not BULLET_PATTERN.match(stripped):
        return True
    return False


def _build_segments(header: DetectedHeader, content_lines: List[str]) -> List[str]:
    segments: List[str] = []
    if header.inline_text:
        segments.append(header.inline_text)
    if not content_lines:
        return segments or [header.title]

    idx = 0
    length = len(content_lines)
    while idx < length:
        raw = content_lines[idx]
        stripped = raw.strip()
        if not stripped:
            idx += 1
            continue

        bullet_match = BULLET_PATTERN.match(stripped)
        if bullet_match:
            bullet_lines = [BULLET_PATTERN.sub("", stripped, count=1).strip(" :-")]
            idx += 1
            while idx < length:
                next_raw = content_lines[idx]
                next_stripped = next_raw.strip()
                if not next_stripped:
                    idx += 1
                    break
                if BULLET_PATTERN.match(next_stripped):
                    break
                if INDENT_PATTERN.match(next_raw):
                    bullet_lines.append(next_stripped)
                    idx += 1
                    continue
                break
            segments.append(" ".join(bullet_lines).strip())
            continue

        paragraph_lines = [stripped]
        idx += 1
        while idx < length:
            next_raw = content_lines[idx]
            next_stripped = next_raw.strip()
            if not next_stripped:
                idx += 1
                break
            if BULLET_PATTERN.match(next_stripped):
                break
            if INDENT_PATTERN.match(next_raw) or not UPPERCASE_SECTION_PATTERN.match(next_stripped):
                paragraph_lines.append(next_stripped)
                idx += 1
                continue
            break

        segments.append(" ".join(paragraph_lines).strip())

    return [segment for segment in segments if segment]


def _clean_segment_text(segment: str) -> str:
    if not segment:
        return ""
    lines = _normalize_block_lines(segment.splitlines() or [segment])
    return _normalize_block_text(lines)


def _normalize_block_lines(lines: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    for line in lines:
        stripped = (line or "").strip()
        if not stripped:
            continue
        stripped = FOOTER_CLEANUP_PATTERN.sub("", stripped)
        stripped = re.sub(r"\s{2,}", " ", stripped)
        cleaned = stripped.strip(" :-")
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _normalize_block_text(lines: Iterable[str]) -> str:
    cleaned: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        cleaned.append(stripped)
    combined = " ".join(cleaned)
    combined = re.sub(r"\s{2,}", " ", combined)
    return combined.strip()


def _normalize_title(line: str) -> str:
    stripped = line.strip()
    stripped = re.sub(r"\s{2,}", " ", stripped)
    stripped = stripped.rstrip(":")
    return stripped


def _hash_block(level: str, text: str) -> str:
    payload = f"{level}:{text.lower()}"
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=10).hexdigest()


__all__ = ["extract_safety_blocks"]
