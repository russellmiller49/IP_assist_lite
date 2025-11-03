"""IFU anchor slicing with configurable TOC guards."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from medparse.ingest.models import PageData
from medparse.ifu.toc_guard import TocGuardConfig, TocGuardReport, apply_toc_guard, trim_anchor_bleed
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
HEADING_CASE_PATTERN = re.compile(r"^[A-Z][A-Za-z].+")

INDICATION_REQUIRED_PHRASES = (
    "indicated for",
    "intended for use",
    "intended to",
    "indications",
)

ANCHOR_TOC_WINDOW = 10
ANCHOR_TOC_RATIO = 0.4

SECTION_ALIAS_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "ifu_section_aliases.yaml"


@functools.lru_cache(maxsize=1)
def _load_section_aliases() -> Dict[str, List[str]]:
    if not SECTION_ALIAS_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(SECTION_ALIAS_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        LOGGER.debug("Failed to load IFU section aliases from %s: %s", SECTION_ALIAS_PATH, exc)
        return {}

    aliases: Dict[str, List[str]] = {}
    for field, values in data.items():
        if not isinstance(values, list):
            continue
        collected = [str(value) for value in values if isinstance(value, str) and value.strip()]
        if collected:
            aliases[field] = collected
    return aliases


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
            "intended audience",
            "definitions",
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
            "1.6 general warnings, cautions, and notes",
            "1.6 general warnings, cautions and notes",
            "1.6 general warnings cautions and notes",
            "1.6 general warnings, cautions & notes",
            "1.6 general warnings",
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
        "stops": [
            "cautions and notes",
            "cautions & notes",
            "notes and cautions",
            "cautions",
            "precautions",
            "notes",
        ],
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
        "stops": [
            "reprocessing and handling",
            "handling and storage",
            "handling",
            "specifications",
            "reprocessing",
            "storage",
            "troubleshooting",
            "references",
        ],
    },
    "specifications": {
        "start": ["specifications"],
        "stops": ["appendix", "bibliography"],
    },
    "references": {
        "start": ["references", "bibliography", "works cited", "literature"],
        "stops": ["appendix", "index"],
    },
}


INTUITIVE_ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "indications_for_use": {
        "start": [
            "1.4.1 indications for use",
            "1.4 professional instructions for use",  # Navigate to parent first
            "indications for use",
        ],
        "stops": [
            "1.4.2 intended use",
            "intended use",
            "1.4.3 intended user",
            "intended audience",
            "definitions",
            "clinical risks and benefits",
            "1.4.4 intended patient population",
            "contraindications",
            "warnings",
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
            "1.4.5 clinical risks and benefits",
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
            "general warnings, cautions, and notes",
        ],
    },
    # Add safety blocks extraction for Ion
    "warnings": {
        "start": [
            "1.6 general warnings, cautions, and notes",
            "general warnings, cautions, and notes",
            "warnings",
        ],
        "stops": [
            "cautions and notes",
            "cautions",
            "notes",
            "contraindications",
            "sterilization",
        ],
    },
    "sterilization": {
        "start": [
            "sterilization",
            "6 sterilization",
        ],
        "stops": [
            "reprocessing",
            "storage",
            "troubleshooting",
            "references",
        ],
    },
}


OLYMPUS_ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "indications_for_use": {
        "start": [
            "indications for use",
            "indication",
        ],
        "stops": [
            "contraindications",
            "contraindication",
            "important information — please read before use",
            "important information - please read before use",
            "user qualifications",
            "instruction manual",  # Stop at instruction manual section
            "warnings",
            "warning",
        ],
    },
    "contraindications": {
        "start": [
            "contraindications",
            "contraindication",
        ],
        "stops": [
            "warning",
            "warnings",
            "precautions",
            "user qualifications",
            "instrument compatibility",
            "instruction manual",  # Stop at instruction manual section
            "terms used in this manual",  # Stop at term definitions
        ],
    },
    "intended_use": {
        "start": [
            "intended use",
            "intended purpose",
            "1 intended use",  # BW 18V pattern
        ],
        "stops": [
            "contraindications",
            "contraindication",
            "user qualifications",
            "important information — please read before use",
            "important information - please read before use",
            "2 precautions",  # BW 18V pattern
            "precautions",
            "warnings",
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
class Section:
    anchor: str
    text: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    lines: List[str] = field(default_factory=list)
    trimmed_prefix: int = 0
    toc_report: Optional[TocGuardReport] = None


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
) -> Tuple[List[PageData], TocGuardReport]:
    """Apply TOC guard to pages and return filtered pages plus report."""

    filtered, report = apply_toc_guard(pages, guard)
    return filtered, report


def slice_section(
    pages: Sequence[PageData],
    start_anchor: Sequence[str],
    stop_anchors: Sequence[str] | None = None,
    *,
    toc_guard: bool = True,
    guard_config: Optional[TocGuardConfig] = None,
    min_start_page: Optional[int] = None,
    bleed_threshold: float = 0.8,
    field_name: Optional[str] = None,
    manufacturer_rules: Optional[Dict[str, object]] = None,
) -> Section:
    guard = guard_config or TocGuardConfig()

    working_pages = list(pages)
    guard_report: Optional[TocGuardReport] = None
    if toc_guard:
        working_pages, guard_report = strip_toc(working_pages, guard)

    min_page_threshold = min_start_page
    if isinstance(manufacturer_rules, dict):
        rule_min = manufacturer_rules.get("min_anchor_page")
        if isinstance(rule_min, int):
            if min_page_threshold is None or rule_min > min_page_threshold:
                min_page_threshold = rule_min
        field_rules = manufacturer_rules.get("fields") if field_name else None
        if isinstance(field_rules, dict):
            field_config = field_rules.get(field_name)
            if isinstance(field_config, dict):
                field_min = field_config.get("min_page")
                if isinstance(field_min, int):
                    if min_page_threshold is None or field_min > min_page_threshold:
                        min_page_threshold = field_min

    if min_page_threshold is not None:
        working_pages = [page for page in working_pages if page.number >= min_page_threshold]

    start_list = _coerce_anchor_list(start_anchor)
    stop_list = _coerce_anchor_list(stop_anchors)

    if not working_pages or not start_list:
        return Section(
            anchor=start_list[0] if start_list else "",
            text="",
            start_page=None,
            end_page=None,
            lines=[],
            trimmed_prefix=0,
            toc_report=guard_report,
        )

    start_patterns = [_compile_anchor_pattern(anchor) for anchor in start_list if anchor]
    if not start_patterns:
        return Section(
            anchor=start_list[0] if start_list else "",
            text="",
            start_page=None,
            end_page=None,
            lines=[],
            trimmed_prefix=0,
            toc_report=guard_report,
        )

    max_attempts = max(len(working_pages), 1)
    attempts = 0
    current_pages = working_pages
    bleed_detected = False

    while attempts < max_attempts and current_pages:
        candidate = _find_first_anchor_line(current_pages, start_patterns)
        if not candidate:
            break
        start_page_no, line_index, raw_line = candidate
        if min_page_threshold is not None and start_page_no < min_page_threshold:
            current_pages = _drop_first_anchor_occurrence(current_pages, start_patterns)
            attempts += 1
            continue
        if is_toc_like_para(raw_line) or not looks_like_section_heading(raw_line):
            current_pages = _drop_first_anchor_occurrence(current_pages, start_patterns)
            attempts += 1
            continue

        start_tokens = _extract_heading_tokens(raw_line)
        pages_for_slice: Sequence[PageData] = current_pages
        window_applied = False
        trimmed_prefix = 0

        while True:
            extracted = slice_between(
                pages_for_slice,
                start_anchors=start_list,
                stop_anchors=stop_list or (),
                guard_fn=None,
            )
            if not extracted:
                trimmed_text = ""
                break

            cleaned = clean_paragraph(extracted)
            cleaned = _truncate_to_stop(cleaned, stop_list, start_tokens)
            cleaned = normalize_bullets(cleaned)
            trimmed_text, trimmed_prefix = trim_anchor_bleed(cleaned, ratio_threshold=bleed_threshold)

            if not trimmed_text:
                break

            if not anchor_post_guard(trimmed_text):
                bleed_detected = True
                break

            if field_name == "indications_for_use" and not _contains_indication_phrase(trimmed_text):
                bleed_detected = True
                break

            if _span_contains_toc(trimmed_text) and not window_applied:
                limited_pages = _limit_pages_to_window(pages_for_slice, start_page_no, window=3)
                if len(limited_pages) < len(pages_for_slice):
                    pages_for_slice = limited_pages
                    window_applied = True
                    continue
                window_applied = True

            start_page = start_page_no
            end_page = _find_anchor_page(pages_for_slice, stop_list) if stop_list else None

            return Section(
                anchor=start_list[0] if start_list else "",
                text=trimmed_text,
                start_page=start_page,
                end_page=end_page,
                lines=[line for line in trimmed_text.splitlines() if line.strip()],
                trimmed_prefix=trimmed_prefix,
                toc_report=guard_report,
            )

        current_pages = _drop_first_anchor_occurrence(current_pages, start_patterns)
        attempts += 1
        continue

    if bleed_detected:
        raise AnchorBleedError(start_list[0] if start_list else "unknown")

    return Section(
        anchor=start_list[0] if start_list else "",
        text="",
        start_page=None,
        end_page=None,
        lines=[],
        trimmed_prefix=0,
        toc_report=guard_report,
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


def is_toc_like_para(line: str) -> bool:
    if not line:
        return False
    lowered = line.strip().lower()
    if not lowered:
        return False
    if "table of contents" in lowered or "contents" in lowered or lowered.endswith("index"):
        return True
    if DOT_LEADER_LINE.search(line) or PAGE_NUMBER_LINE.search(line) or TRAILING_NUMBER_PATTERN.search(line):
        return True
    return False


def looks_like_section_heading(line: str) -> bool:
    if not line:
        return False
    stripped = line.strip()
    if not stripped:
        return False
    if re.match(r"^\d+(?:\.\d+)*\s+", stripped):
        return True
    if HEADING_CASE_PATTERN.match(stripped):
        return True
    if stripped.isupper():
        words = stripped.split()
        if len(words) <= 6:
            return True
    return False


def anchor_post_guard(text: str, *, window: int = ANCHOR_TOC_WINDOW, threshold: float = ANCHOR_TOC_RATIO) -> bool:
    if not text:
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    if len(lines) == 1:
        sentence_chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text) if chunk.strip()]
        if len(sentence_chunks) > 1:
            lines = sentence_chunks
    window_lines = lines[: window]
    if not window_lines:
        return True
    toc_like = sum(1 for line in window_lines if is_toc_like_para(line))
    ratio = toc_like / len(window_lines)
    return ratio <= threshold


def normalize_bullets(text: str) -> str:
    """Normalize bullet points and remove common prefixes."""
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Remove common bullet characters
        if line and line[0] in {"•", "◾", "▪", "○", "◦", "‣", "-", "*", "·"}:
            line = line[1:].strip()

        # Remove leading dashes with spaces
        if line.startswith("- "):
            line = line[2:].strip()

        # Skip empty lines after bullet removal
        if not line:
            continue

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

    alias_map = _load_section_aliases()
    if alias_map:
        for field, alias_values in alias_map.items():
            target = merged.setdefault(field, {"start": [], "stops": []})
            starts = target.setdefault("start", [])
            for alias in alias_values:
                if alias not in starts:
                    starts.append(alias)

    return merged


def _truncate_to_stop(
    text: str,
    stop_anchors: Sequence[str],
    start_tokens: Optional[Sequence[int]] = None,
) -> str:
    if not text or not stop_anchors:
        return text

    lines = text.splitlines()
    normalized_stops = [_normalize_for_match(anchor) for anchor in stop_anchors if anchor]

    for idx, raw_line in enumerate(lines):
        if start_tokens:
            heading_tokens = _extract_heading_tokens(raw_line)
            if _should_stop_at_heading(heading_tokens, start_tokens):
                return "\n".join(lines[:idx])
        normalized_line = _normalize_for_match(raw_line)
        if not normalized_line:
            continue
        for normalized_stop in normalized_stops:
            if _matches_stop_heading(normalized_line, normalized_stop):
                return "\n".join(lines[:idx])
    return text


def _normalize_for_match(value: str) -> str:
    lowered = value.lower()
    lowered = lowered.replace("’", "'")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return " ".join(cleaned.split())


def _extract_heading_tokens(line: str) -> List[int]:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", line or "")
    if not match:
        return []
    tokens: List[int] = []
    for part in match.group(1).split("."):
        try:
            tokens.append(int(part))
        except ValueError:
            continue
    return tokens


def _should_stop_at_heading(tokens: Sequence[int], start_tokens: Sequence[int]) -> bool:
    if not tokens or not start_tokens:
        return False
    prefix_len = len(start_tokens)
    if len(tokens) > prefix_len and list(tokens[:prefix_len]) == list(start_tokens):
        return False
    compare_len = min(len(tokens), prefix_len)
    for idx in range(compare_len):
        if tokens[idx] > start_tokens[idx]:
            return True
        if tokens[idx] < start_tokens[idx]:
            return False
    if len(tokens) < prefix_len and list(tokens) == list(start_tokens[: len(tokens)]):
        return False
    return False


def _contains_indication_phrase(text: str) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in INDICATION_REQUIRED_PHRASES):
        return True
    if len(lowered) >= 160:
        sentence_marks = sum(1 for char in lowered if char in {".", "!", "?"})
        if sentence_marks >= 2:
            return True
    return False


def _span_contains_toc(text: str) -> bool:
    if not text:
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    return any(is_toc_like_para(line) for line in lines)


def _limit_pages_to_window(
    pages: Sequence[PageData],
    start_page_no: int,
    *,
    window: int = 3,
) -> List[PageData]:
    if not pages:
        return list(pages)
    try:
        start_index = next(idx for idx, page in enumerate(pages) if page.number == start_page_no)
    except StopIteration:
        start_index = 0
    start = max(0, start_index - window)
    end = min(len(pages), start_index + window + 1)
    return list(pages[start:end])


def _matches_stop_heading(line: str, stop: str) -> bool:
    if not line or not stop:
        return False
    if line.startswith(stop):
        return True
    if stop in line:
        return True
    if abs(len(line) - len(stop)) <= 3:
        ratio = SequenceMatcher(None, line, stop).ratio()
        if ratio >= 0.82:
            return True
    return False


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
    pattern = rf"^\s*(?:\d+(?:\.\d+)*\s+)?{escaped}(?:\b|[:\-–—]|\s)"
    return re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)


def _find_first_anchor_line(
    pages: Sequence[PageData],
    patterns: Sequence[re.Pattern[str]],
) -> Optional[Tuple[int, int, str]]:
    for page in pages:
        for idx, line in enumerate(page.lines or []):
            for pattern in patterns:
                if pattern.search(line):
                    return page.number, idx, line
    return None


def _drop_first_anchor_occurrence(
    pages: Sequence[PageData],
    patterns: Sequence[re.Pattern[str]],
) -> List[PageData]:
    updated: List[PageData] = []
    removed = False
    for page in pages:
        if removed:
            updated.append(page)
            continue

        lines = list(page.lines or [])
        for idx, line in enumerate(lines):
            if any(pattern.search(line) for pattern in patterns):
                new_lines = lines[idx + 1 :]
                new_text = "\n".join(new_lines)
                updated.append(replace(page, lines=new_lines, text=new_text))
                removed = True
                break
        else:
            updated.append(page)
    return updated


__all__ = [
    "AnchorBleedError",
    "DEFAULT_SECTION_ANCHORS",
    "Section",
    "TocGuardConfig",
    "anchor_post_guard",
    "is_toc_like_para",
    "looks_like_section_heading",
    "looks_like_toc",
    "normalize_bullets",
    "resolve_anchor_map",
    "resolve_toc_guard",
    "slice_section",
    "strip_toc",
]
