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

DEFAULT_SECTION_ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "indications_for_use": {
        "start": ["indications for use"],
        "stops": ["intended use", "intended user", "contraindications", "warnings"],
    },
    "intended_use": {
        "start": ["intended use"],
        "stops": ["intended user", "contraindications", "warnings", "adverse events"],
    },
    "intended_user": {
        "start": ["intended user", "user"],
        "stops": ["contraindications", "warnings", "adverse events"],
    },
    "contraindications": {
        "start": ["contraindications"],
        "stops": ["warnings", "adverse events", "precautions"],
    },
    "warnings": {"start": ["warnings"], "stops": ["cautions", "precautions", "notes"]},
    "cautions": {"start": ["cautions"], "stops": ["notes", "instructions", "warnings"]},
    "notes": {"start": ["notes"], "stops": ["warnings", "instructions", "cautions"]},
    "adverse_events": {
        "start": ["adverse events", "complications"],
        "stops": ["warnings", "precautions", "maintenance"],
    },
    "instructions": {"start": ["instructions"], "stops": ["sterilization", "specifications"]},
    "sterilization": {"start": ["sterilization"], "stops": ["specifications"]},
    "specifications": {"start": ["specifications"], "stops": ["appendix", "bibliography"]},
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

    for page in pages:
        if not page.lines:
            filtered.append(page)
            continue

        non_empty = [line for line in page.lines if line.strip()]
        if not non_empty:
            filtered.append(page)
            continue

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
    lowered = text.lower()
    if "table of contents" in lowered:
        return True

    dotted_lines = sum(1 for line in text.splitlines() if DOT_LEADER_PATTERN.search(line))
    numbered = sum(1 for line in text.splitlines() if TRAILING_NUMBER_PATTERN.search(line))
    total_lines = max(len(text.splitlines()), 1)

    if dotted_lines / total_lines >= 0.3 and numbered / total_lines >= 0.3:
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


def resolve_anchor_map(overrides: Dict[str, Any]) -> Dict[str, Dict[str, List[str]]]:
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

