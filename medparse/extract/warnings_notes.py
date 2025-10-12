"""Warning / caution / note parsing heuristics."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple, Literal

from medparse.ingest.pdf_reader import PageContent
from medparse.types.base import EvidenceSpan, IFUWarning

Severity = Literal["warning", "caution", "note"]

WARNING_REGEXES: Dict[Severity, re.Pattern[str]] = {
    "warning": re.compile(
        r"^(?:⚠\s*)?(?:warning|avertissement|warnung)\b[:\s]*", re.IGNORECASE
    ),
    "caution": re.compile(r"^(?:caution|attention|vorsicht)\b[:\s]*", re.IGNORECASE),
    "note": re.compile(r"^(?:note|nota)\b[:\s]*", re.IGNORECASE),
}

CATEGORY_PATTERNS: List[Tuple[str, Tuple[str, ...]]] = [
    ("laser_safety", ("laser", "eyewear")),
    ("electrical", ("leakage current", "electrical")),
    ("pinch_hazard", ("pinch", "pinching")),
    ("suction", ("suction",)),
    ("saline", ("saline",)),
]


def extract_warning_blocks(pages: Sequence[PageContent]) -> List[IFUWarning]:
    """Return structured warning blocks from pages."""
    blocks: List[IFUWarning] = []
    seen: set[tuple[str, str]] = set()

    for page in pages:
        lines = page.lines
        idx = 0
        while idx < len(lines):
            severity, cleaned = _match_severity(lines[idx])
            if not severity or not cleaned:
                idx += 1
                continue

            evidence_text = lines[idx].strip()
            text_parts = [cleaned]
            idx += 1

            while idx < len(lines):
                candidate = lines[idx].strip()
                if not candidate:
                    idx += 1
                    break
                next_severity, _ = _match_severity(candidate)
                if next_severity:
                    break
                text_parts.append(candidate)
                idx += 1

            full_text = re.sub(r"\s+", " ", " ".join(text_parts)).strip()
            dedupe_key = (severity, full_text.lower())
            if not full_text or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            category = _infer_category(full_text)
            evidence = EvidenceSpan(text=evidence_text, page=page.number)
            blocks.append(
                IFUWarning(
                    id="",
                    text=full_text,
                    severity=severity,  # type: ignore[arg-type]
                    category=category,
                    page=page.number,
                    bbox_norm=(0.0, 0.0, 1.0, 1.0),
                    evidence_spans=[evidence],
                )
            )

    return blocks


def _match_severity(line: str) -> Tuple[Optional[Severity], Optional[str]]:
    for severity, pattern in WARNING_REGEXES.items():
        match = pattern.match(line.strip())
        if match:
            cleaned = line[match.end() :].strip()
            return severity, cleaned
    return None, None


def _infer_category(text: str) -> Optional[str]:
    lowered = text.lower()
    for category, keywords in CATEGORY_PATTERNS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return None
