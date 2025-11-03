"""Safety block extraction and normalization for IFU documents."""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Iterable, List, Optional, Sequence

from medparse.ingest.models import PageData
from medparse.schema.common import EvidenceSpan
from medparse.schema.ifu import SafetyBlock

LEVEL_PATTERNS: Dict[str, Sequence[re.Pattern[str]]] = {
    "danger": (
        re.compile(r"^(?:⚠|▲|∆|!|\u26a0)\s*(?:danger|hazard)", re.IGNORECASE),
        re.compile(r"^danger[:\s]", re.IGNORECASE),
    ),
    "warning": (
        re.compile(r"^(?:⚠|▲|∆|!|\u26a0)\s*(?:warning)", re.IGNORECASE),
        re.compile(r"^warning[:\s]", re.IGNORECASE),
    ),
    "caution": (
        re.compile(r"^(?:⚠|▲|∆|!|\u26a0)\s*(?:caution)", re.IGNORECASE),
        re.compile(r"^caution[:,\s]", re.IGNORECASE),
    ),
    "notice": (
        re.compile(r"^notice[:,\s]", re.IGNORECASE),
    ),
    "note": (
        re.compile(r"^note[:,\s]", re.IGNORECASE),
    ),
    "attention": (
        re.compile(r"^attention[:,\s]", re.IGNORECASE),
        re.compile(r"^(?:attention|important)[:,\s]", re.IGNORECASE),
    ),
}

LEVEL_TO_SEVERITY = {
    "danger": "warning",
    "warning": "warning",
    "caution": "caution",
    "notice": "note",
    "note": "note",
    "attention": "warning",
}

FOOTER_CLEANUP_PATTERN = re.compile(r"(page\s+\d+(?:\s*/\s*\d+)?|\b\d+\s*/\s*\d+\b)", re.IGNORECASE)


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


def extract_safety_blocks(pages: Sequence[PageData]) -> List[SafetyBlock]:
    """Extract safety blocks using severity keywords and icons."""

    blocks: List[SafetyBlock] = []
    seen_hashes: set[str] = set()

    for page in pages:
        lines = list(page.lines or [])
        idx = 0
        while idx < len(lines):
            raw_line = lines[idx].strip()
            level = _detect_level(raw_line)
            if not level:
                idx += 1
                continue

            block_lines = [raw_line]
            idx += 1
            while idx < len(lines):
                candidate = lines[idx].strip()
                if not candidate:
                    idx += 1
                    break
                if _detect_level(candidate):
                    break
                block_lines.append(candidate)
                idx += 1

            normalized_lines = _normalize_block_lines(block_lines)
            normalized_text = _normalize_block_text(normalized_lines)
            if not normalized_text:
                continue

            block_hash = _hash_block(level, normalized_text)
            if block_hash in seen_hashes:
                continue

            seen_hashes.add(block_hash)
            title = _normalize_title(normalized_lines[0] if normalized_lines else block_lines[0])
            severity = LEVEL_TO_SEVERITY.get(level, "warning")

            blocks.append(
                SafetyBlock(
                    level=level,
                    severity=severity,  # Backwards compatibility
                    title=title,
                    text=normalized_text,
                    page=page.number,
                    hash=block_hash,
                    evidence=EvidenceSpan(
                        text=normalized_text[:200],
                        page=page.number,
                        confidence=0.8,
                    ),
                )
            )

    return blocks


def _detect_level(line: str) -> Optional[str]:
    for level, patterns in LEVEL_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(line):
                return level
    return None


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
