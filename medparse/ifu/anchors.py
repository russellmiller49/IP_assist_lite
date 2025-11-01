"""IFU anchor slicing with configurable TOC guards."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from medparse.ingest.models import PageData
from medparse.normalize.layout import slice_between
from medparse.normalize.text_cleanup import clean_paragraph
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

DOT_LEADER_PATTERN = re.compile(r"\.{2,}")
TRAILING_NUMBER_PATTERN = re.compile(r"\s\d{1,4}\s*$")
ANCHOR_HEADING_PATTERN = re.compile(r"^\s*\d+\.\s+[A-Z].*$")

# Enhanced TOC detection patterns
TOC_HEADER_PATTERN = re.compile(r"^\s*(contents|table of contents|index)\s*$", re.IGNORECASE)
DOT_LEADER_LINE = re.compile(r".+(\.{2,}|\s{2,})\s*\d{1,3}\s*$")
PAGE_NUMBER_LINE = re.compile(r"^.+\s+\d{1,3}\s*$")

DEFAULT_SECTION_ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "indications_for_use": {
        "start": [
            "indications for use",
            "indication for use",
            "clinical indications",
        ],
        "stops": [
            "intended use",
            "intended patient population",
            "intended user",
            "clinical risks and benefits",
            "clinical risks & benefits",
            "clinical benefits and risks",
            "contraindications",
            "serious incident reporting",
            "general warnings, cautions, and notes",
            "general warnings",
            "warnings",
            "cautions",
            "notes",
            "professional instructions for use",
            "introduction | professional instructions for use",
            "table 1.1",
        ],
    },
    "intended_use": {
        "start": [
            "intended use",
            "use intended",
            "purpose",
        ],
        "stops": [
            "intended patient population",
            "intended user",
            "clinical risks and benefits",
            "clinical risks & benefits",
            "clinical benefits and risks",
            "contraindications",
            "serious incident reporting",
            "general warnings, cautions, and notes",
            "general warnings",
            "warnings",
            "cautions",
            "notes",
        ],
    },
    "intended_user": {
        "start": [
            "intended user",
            "user qualifications",
        ],
        "stops": [
            "intended patient population",
            "contraindications",
            "warnings",
            "cautions",
            "notes",
            "adverse events",
        ],
    },
    "intended_patient_population": {
        "start": [
            "intended patient population",
            "patient population",
            "intended patients",
        ],
        "stops": [
            "intended user",
            "contraindications",
            "clinical risks and benefits",
            "warnings",
            "cautions",
            "notes",
        ],
    },
    "contraindications": {
        "start": [
            "contraindications",
        ],
        "stops": [
            "clinical risks and benefits",
            "warnings",
            "cautions",
            "notes",
            "adverse events",
            "precautions",
        ],
    },
    "clinical_risks_and_benefits": {
        "start": [
            "clinical risks and benefits",
            "clinical risks & benefits",
        ],
        "stops": [
            "serious incident reporting",
            "general warnings, cautions, and notes",
            "general warnings",
            "warnings",
            "cautions",
            "notes",
        ],
    },
    "adverse_events": {
        "start": [
            "adverse events",
            "potential adverse events",
            "possible adverse events",
            "complications",
            "potential complications",
            "possible complications",
        ],
        "stops": [
            "warnings",
            "cautions",
            "notes",
            "maintenance",
            "serious incident reporting",
        ],
    },
    "warnings": {
        "start": ["warnings", "general warnings"],
        "stops": ["cautions", "precautions", "notes"],
    },
    "cautions": {
        "start": ["cautions"],
        "stops": ["notes", "instructions", "warnings"],
    },
    "notes": {
        "start": ["notes"],
        "stops": ["warnings", "instructions", "cautions"],
    },
    "instructions": {
        "start": ["instructions"],
        "stops": ["sterilization", "specifications"],
    },
    "sterilization": {
        "start": ["sterilization"],
        "stops": ["specifications"],
    },
    "specifications": {
        "start": ["specifications"],
        "stops": ["appendix", "bibliography"],
    },
}


INTUITIVE_ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "indications_for_use": {
        "start": [
            "1.4.1 indications for use",
            "indications for use",
        ],
        "stops": [
            "1.4.2 intended use",
            "intended use",
            "1.5 serious incident reporting",
            "serious incident reporting",
        ],
    },
    "intended_use": {
        "start": [
            "1.4.2 intended use",
            "intended use",
        ],
        "stops": [
            "1.4.3 intended user",
            "intended user",
            "1.5 serious incident reporting",
            "serious incident reporting",
        ],
    },
    "intended_user": {
        "start": [
            "1.4.3 intended user",
            "intended user",
        ],
        "stops": [
            "1.4.4 intended patient population",
            "intended patient population",
            "clinical risks and benefits",
            "1.5 serious incident reporting",
        ],
    },
    "intended_patient_population": {
        "start": [
            "1.4.4 intended patient population",
            "intended patient population",
        ],
        "stops": [
            "clinical risks and benefits",
            "1.5 serious incident reporting",
            "serious incident reporting",
        ],
    },
    "clinical_risks_and_benefits": {
        "start": [
            "1.4.5 clinical risks and benefits",
            "clinical risks and benefits",
        ],
        "stops": [
            "1.5 serious incident reporting",
            "serious incident reporting",
            "1.6 general warnings, cautions, and notes",
        ],
    },
}


OLYMPUS_ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "indications_for_use": {
        "start": [
            "indications for use",
        ],
        "stops": [
            "contraindications",
            "important information — please read before use",
            "important information - please read before use",
            "user qualifications",
        ],
    },
    "contraindications": {
        "start": [
            "contraindications",
        ],
        "stops": [
            "warning",
            "warnings",
            "precautions",
            "user qualifications",
            "instrument compatibility",
        ],
    },
    "intended_use": {
        "start": [
            "intended use",
            "intended purpose",
        ],
        "stops": [
            "contraindications",
            "user qualifications",
            "important information — please read before use",
        ],
    },
}


MANUFACTURER_ANCHORS: Dict[str, Dict[str, Dict[str, List[str]]]] = {
    "INTUITIVE SURGICAL, INC.": INTUITIVE_ANCHORS,
    "INTUITIVE SURGICAL": INTUITIVE_ANCHORS,
    "OLYMPUS CORPORATION": OLYMPUS_ANCHORS,
    "OLYMPUS": OLYMPUS_ANCHORS,
}


@dataclass(slots=True)
class TocGuardConfig:
    enabled: bool = True
    density_threshold: float = 0.65
    dot_leader_min: float = 0.20
    page_number_ratio: float = 0.40

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "TocGuardConfig":
        if not isinstance(data, dict):
            return cls()
        return cls(
            enabled=bool(data.get("enabled", True)),
            density_threshold=float(data.get("density_threshold", 0.65)),
            dot_leader_min=float(data.get("dot_leader_min", 0.20)),
            page_number_ratio=float(data.get("page_number_ratio", 0.40)),
        )

    def update(self, data: Dict[str, Any]) -> None:
        for key, value in (data or {}).items():
            if not hasattr(self, key):
                continue
            current = getattr(self, key)
            if isinstance(current, bool):
                setattr(self, key, bool(value))
            else:
                try:
                    setattr(self, key, float(value))
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    LOGGER.debug("Invalid toc_guard override for %s: %s", key, value)

    def as_dict(self) -> Dict[str, float | bool]:
        return {
            "enabled": self.enabled,
            "density_threshold": self.density_threshold,
            "dot_leader_min": self.dot_leader_min,
            "page_number_ratio": self.page_number_ratio,
        }


@dataclass(slots=True)
class Section:
    anchor: str
    text: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    lines: List[str] = field(default_factory=list)


class AnchorBleedError(Exception):
    """Raised when anchor extraction appears to include TOC bleed."""

    def __init__(self, anchor: str):
        super().__init__(anchor)
        self.anchor = anchor

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"anchor '{self.anchor}' captured table-of-contents bleed"


def resolve_toc_guard(settings: Dict[str, Any], manufacturer: Optional[str]) -> TocGuardConfig:
    guard = TocGuardConfig.from_dict(settings.get("toc_guard"))
    overrides = settings.get("manufacturer_overrides") or {}

    if not manufacturer or not isinstance(overrides, dict):
        return guard

    normalized = manufacturer.strip().upper()
    override_config = None
    for key, value in overrides.items():
        if key.upper() == normalized:
            override_config = value
            break
    if not override_config:
        return guard

    if isinstance(override_config, dict):
        if "toc_guard" in override_config and isinstance(override_config["toc_guard"], dict):
            guard.update(override_config["toc_guard"])
        for key, value in override_config.items():
            if key.startswith("toc_guard.") and len(key.split(".", 1)) == 2:
                field_name = key.split(".", 1)[1]
                guard.update({field_name: value})
    else:
        LOGGER.debug("Unexpected manufacturer override type for %s: %r", manufacturer, override_config)
    return guard


def strip_toc(
    pages: Sequence[PageData],
    guard: TocGuardConfig,
) -> Tuple[List[PageData], List[int]]:
    if not guard.enabled:
        return list(pages), []

    filtered: List[PageData] = []
    dropped: List[int] = []

    for page_idx, page in enumerate(pages):
        if not page.lines:
            filtered.append(page)
            continue

        non_empty = [line for line in page.lines if line.strip()]
        if not non_empty:
            filtered.append(page)
            continue

        # Only check for TOC/Index in first 15 pages
        if page_idx < 15:
            page_text = "\n".join(non_empty)

            # Check for explicit TOC/Index headers
            has_toc_header = any(TOC_HEADER_PATTERN.match(line) for line in non_empty[:5])

            # Check if entire page looks like TOC
            if has_toc_header or looks_like_toc(page_text):
                dropped.append(page.number)
                continue

        # Original density-based detection
        non_empty_ratio = len(non_empty) / max(len(page.lines), 1)
        dot_ratio = sum(1 for line in non_empty if DOT_LEADER_PATTERN.search(line)) / len(non_empty)
        trailing_ratio = sum(1 for line in non_empty if TRAILING_NUMBER_PATTERN.search(line)) / len(non_empty)

        if (
            non_empty_ratio >= guard.density_threshold
            and dot_ratio >= guard.dot_leader_min
            and trailing_ratio >= guard.page_number_ratio
        ):
            dropped.append(page.number)
            continue

        filtered.append(page)

    if dropped:
        LOGGER.debug("TOC guard dropped pages: %s", dropped)

    return filtered, dropped


def slice_section(
    pages: Sequence[PageData],
    start_anchor: Sequence[str],
    stop_anchors: Sequence[str] | None = None,
    *,
    toc_guard: bool = True,
    guard_config: Optional[TocGuardConfig] = None,
) -> Section:
    guard = guard_config or TocGuardConfig()

    working_pages = list(pages)
    dropped: List[int] = []
    if toc_guard:
        working_pages, dropped = strip_toc(working_pages, guard)

    start_list = _coerce_anchor_list(start_anchor)
    stop_list = _coerce_anchor_list(stop_anchors)

    extracted = slice_between(
        working_pages,
        start_anchors=start_list,
        stop_anchors=stop_list or (),
        guard_fn=None,
    )
    cleaned = clean_paragraph(extracted)
    if cleaned and looks_like_toc(cleaned):
        raise AnchorBleedError(start_list[0] if start_list else "unknown")

    start_page = _find_anchor_page(working_pages, start_list)
    end_page = _find_anchor_page(working_pages, stop_list) if stop_list else None

    return Section(
        anchor=start_list[0] if start_list else "",
        text=cleaned,
        start_page=start_page,
        end_page=end_page,
        lines=[line for line in cleaned.splitlines() if line.strip()],
    )


def looks_like_toc(text: str) -> bool:
    """Enhanced TOC detection with multiple heuristics."""
    lowered = text.lower()

    # Check for explicit TOC headers
    if "table of contents" in lowered or "index" in lowered:
        return True

    lines = text.splitlines()
    if not lines:
        return False

    # Check first few lines for TOC header pattern
    for line in lines[:3]:
        if TOC_HEADER_PATTERN.match(line):
            return True

    # Count different TOC indicators
    dotted_lines = sum(1 for line in lines if DOT_LEADER_LINE.search(line))
    numbered = sum(1 for line in lines if TRAILING_NUMBER_PATTERN.search(line))
    page_refs = sum(1 for line in lines if PAGE_NUMBER_LINE.search(line))
    total_lines = max(len(lines), 1)

    # Multiple detection thresholds
    if dotted_lines / total_lines >= 0.3 and numbered / total_lines >= 0.3:
        return True

    # Check for high density of page number references
    if page_refs / total_lines >= 0.5:
        # But not if it looks like actual content
        avg_line_length = sum(len(line.strip()) for line in lines) / total_lines
        if avg_line_length < 60:  # TOC lines tend to be shorter
            return True

    # Check for index-style patterns (short entries with page numbers)
    short_with_numbers = sum(1 for line in lines
                           if len(line.strip()) < 50 and
                           TRAILING_NUMBER_PATTERN.search(line))
    if short_with_numbers / total_lines >= 0.6:
        return True

    return False


def normalize_bullets(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line and line[0] in {"•", "-", "*"}:
            lines.append(f"- {line[1:].strip()}")
        else:
            lines.append(line)
    return "\n".join(lines)


def resolve_anchor_map(
    overrides: Dict[str, Any],
    manufacturer: Optional[str] = None,
) -> Dict[str, Dict[str, List[str]]]:
    merged: Dict[str, Dict[str, List[str]]] = {}
    for key, config in DEFAULT_SECTION_ANCHORS.items():
        merged[key] = {
            "start": list(config.get("start", [])),
            "stops": list(config.get("stops", [])),
        }

    for field, override in (overrides or {}).items():
        if field not in merged or not isinstance(override, dict):
            continue
        if "start" in override:
            merged[field]["start"] = _coerce_anchor_list(override.get("start"))
        if "stops" in override:
            merged[field]["stops"] = _coerce_anchor_list(override.get("stops"))

    if manufacturer:
        normalized = manufacturer.strip().upper()
        anchor_bundle = MANUFACTURER_ANCHORS.get(normalized)
        if anchor_bundle:
            for field, config in anchor_bundle.items():
                start_values = config.get("start")
                stop_values = config.get("stops")
                if start_values:
                    merged.setdefault(field, {"start": [], "stops": []})
                    merged[field]["start"] = _coerce_anchor_list(start_values)
                if stop_values is not None:
                    merged.setdefault(field, {"start": [], "stops": []})
                    merged[field]["stops"] = _coerce_anchor_list(stop_values)

    return merged


def _coerce_anchor_list(values: Sequence[str] | str | None) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    return [value for value in values if isinstance(value, str)]


def _find_anchor_page(pages: Sequence[PageData], anchors: Sequence[str]) -> Optional[int]:
    if not anchors:
        return None
    patterns = [_compile_anchor_pattern(anchor) for anchor in anchors]
    for page in pages:
        page_text = "\n".join(page.lines or [])
        for pattern in patterns:
            if pattern.search(page_text):
                return page.number
    return None


def _compile_anchor_pattern(anchor: str) -> re.Pattern[str]:
    escaped = re.escape(anchor)
    pattern = rf"(?:^|\n)\s*(?:\d+\.\s*)?{escaped}[\s:]*"
    return re.compile(pattern, flags=re.IGNORECASE)


__all__ = [
    "AnchorBleedError",
    "DEFAULT_SECTION_ANCHORS",
    "Section",
    "TocGuardConfig",
    "looks_like_toc",
    "normalize_bullets",
    "resolve_anchor_map",
    "resolve_toc_guard",
    "slice_section",
    "strip_toc",
]
