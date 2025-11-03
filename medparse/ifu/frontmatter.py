"""Front-matter extraction utilities for IFU documents."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from medparse.ingest.models import PageData

MANUFACTURER_PATTERNS: Sequence[tuple[str, Sequence[re.Pattern[str]]]] = [
    (
        "ERBE Elektromedizin GmbH",
        (
            re.compile(r"ERBE\s+Elektromedizin\s+GmbH", re.IGNORECASE),
            re.compile(r"ERBE\s+Medical", re.IGNORECASE),
        ),
    ),
    (
        "Intuitive Surgical, Inc.",
        (
            re.compile(r"Intuitive\s+Surgical", re.IGNORECASE),
            re.compile(r"Ion(?:™)?\s+Endoluminal\s+System", re.IGNORECASE),
        ),
    ),
    (
        "Olympus Corporation",
        (
            re.compile(r"Olympus\s+Corporation", re.IGNORECASE),
            re.compile(r"Olympus\s+America\s+Inc\.", re.IGNORECASE),
            re.compile(r"Olympus\s+Medical", re.IGNORECASE),
        ),
    ),
]

IDENTIFIER_PATTERNS: Dict[str, Sequence[re.Pattern[str]]] = {
    "part_number": (
        re.compile(
            r"(?:PN|P/N|REF|Cat(?:\.)?\s*No\.?|Document\s*(?:No\.|#)|Order\s*No\.)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/]{2,})",
            re.IGNORECASE,
        ),
    ),
    "revision": (
        re.compile(r"(?:Rev(?:ision)?|Version)\s*[:#]?\s*([A-Z0-9][A-Z0-9\.\-]{0,9})", re.IGNORECASE),
    ),
    "publication_date": (
        re.compile(r"(?:Published|Issue|Revision)\s*(?:Date)?\s*[:#]?\s*([0-9]{4}[-/\.][01]?[0-9](?:[-/\.][0-3]?[0-9])?)"),
        re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.IGNORECASE),
        re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{4})", re.IGNORECASE),
        re.compile(r"(0?[1-9]|1[0-2])[/-](\d{4})"),
    ),
    "model": (
        re.compile(r"(?:Model|Series)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/]{1,})", re.IGNORECASE),
    ),
}

BLOCKLIST_KEYWORDS = {
    "table of contents",
    "contents",
    "warning",
    "caution",
    "contraindications",
    "indications",
    "adverse events",
    "published",
    "issue",
    "revision",
    "rights",
    "reserved",
    "copyright",
    "printed",
}

CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "ifu_frontmatter.yaml"


@functools.lru_cache(maxsize=1)
def _load_frontmatter_config() -> Dict[str, object]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

    manufacturers_cfg: List[tuple[str, tuple[re.Pattern[str], ...]]] = []
    for entry in data.get("manufacturers", []) or []:
        name = entry.get("name")
        patterns_raw = entry.get("patterns") or []
        compiled: List[re.Pattern[str]] = []
        if name:
            for pattern in patterns_raw:
                try:
                    compiled.append(re.compile(str(pattern), re.IGNORECASE))
                except re.error:
                    continue
            if compiled:
                manufacturers_cfg.append((name, tuple(compiled)))
    data["_manufacturer_patterns"] = manufacturers_cfg

    product_patterns_cfg: Dict[str, List[tuple[re.Pattern[str], int]]] = {}
    product_section = data.get("product_patterns") or {}
    if isinstance(product_section, dict):
        for key, pattern_list in product_section.items():
            compiled_list: List[tuple[re.Pattern[str], int]] = []
            for pattern in pattern_list or []:
                if isinstance(pattern, dict):
                    regex = pattern.get("regex")
                    group = pattern.get("group", 0)
                else:
                    regex = pattern
                    group = 0
                if not regex:
                    continue
                try:
                    compiled_list.append((re.compile(str(regex), re.IGNORECASE), int(group)))
                except (re.error, ValueError):
                    continue
            if compiled_list:
                product_patterns_cfg[str(key)] = compiled_list
    data["_product_patterns"] = product_patterns_cfg

    return data


@dataclass(slots=True)
class FrontMatterResult:
    manufacturer: Optional[str] = None
    product_name: Optional[str] = None
    product_name_source: Optional[str] = None
    part_number: Optional[str] = None
    revision: Optional[str] = None
    publication_date: Optional[str] = None
    model: Optional[str] = None

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "manufacturer": self.manufacturer,
            "product_name": self.product_name,
            "product_name_source": self.product_name_source,
            "part_number": self.part_number,
            "revision": self.revision,
            "publication_date": self.publication_date,
            "model": self.model,
        }


def extract_front_matter(
    pages: Sequence[PageData],
    *,
    metadata_title: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Extract manufacturer, product name, and identifiers from the cover pages."""

    config = _load_frontmatter_config()
    result = FrontMatterResult()
    cover_text = _join_page_text(pages[:3])
    tail_text = _join_page_text(pages[-3:])
    lower_title = metadata_title.lower() if metadata_title else ""

    manufacturer = _detect_manufacturer(cover_text, config) or _detect_manufacturer(tail_text, config)
    if manufacturer:
        result.manufacturer = manufacturer
    elif lower_title:
        if "erbe" in lower_title:
            result.manufacturer = "ERBE Elektromedizin GmbH"
        elif "intuitive" in lower_title:
            result.manufacturer = "Intuitive Surgical, Inc."
        elif "olympus" in lower_title:
            result.manufacturer = "Olympus Corporation"

    for field, patterns in IDENTIFIER_PATTERNS.items():
        raw_value = _search_patterns(cover_text, patterns) or _search_patterns(tail_text, patterns)
        if not raw_value:
            continue
        if field == "publication_date":
            normalized = _normalize_date(raw_value)
            if normalized:
                result.publication_date = normalized
        elif field == "part_number":
            result.part_number = raw_value.strip().upper()
        elif field == "revision":
            result.revision = raw_value.strip().upper()
        elif field == "model":
            result.model = raw_value.strip()

    product_name, product_source = _select_product_name(pages, result, metadata_title, config)
    if product_name:
        result.product_name = product_name
        result.product_name_source = product_source or "pattern"
    elif result.model and result.manufacturer:
        result.product_name = f"{result.manufacturer} {result.model}".strip()
        result.product_name_source = "model_hint"
    if metadata_title:
        if not result.part_number:
            part_match = re.search(r"([A-Z0-9]{3,}-[A-Z0-9]{3,})", metadata_title)
            if part_match:
                result.part_number = part_match.group(1).upper()
        if not result.part_number:
            doc_match = re.search(r"(D[0-9]{5,})", metadata_title, re.IGNORECASE)
            if doc_match:
                result.part_number = doc_match.group(1).upper()
        if not result.revision:
            rev_match = re.search(r"(D[0-9]{5,})", metadata_title, re.IGNORECASE)
            if rev_match:
                result.revision = rev_match.group(1).upper()

    return result.as_dict()


def _join_page_text(pages: Sequence[PageData]) -> str:
    return "\n".join(page.text or "" for page in pages if page is not None)


def _detect_manufacturer(text: str, config: Optional[Dict[str, object]] = None) -> Optional[str]:
    patterns_bundle = list(MANUFACTURER_PATTERNS)
    if isinstance(config, dict):
        patterns_bundle.extend(config.get("_manufacturer_patterns", []))
    for canonical, patterns in patterns_bundle:
        if any(pattern.search(text) for pattern in patterns):
            return canonical
    return None


def _search_patterns(text: str, patterns: Sequence[re.Pattern[str]]) -> Optional[str]:
    if not text:
        return None
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        if match.lastindex:
            return match.group(match.lastindex)
        return match.group(0)
    return None


def _normalize_date(raw: str) -> Optional[str]:
    candidate = raw.strip()
    if not candidate:
        return None
    candidate = candidate.replace("/", "-").replace(".", "-")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return candidate
    if re.fullmatch(r"\d{4}-\d{2}", candidate):
        return f"{candidate}-01"
    month_map = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "sept": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    tokens = candidate.split("-")
    if len(tokens) == 3 and tokens[0].isdigit() and tokens[1].isdigit() and tokens[2].isdigit():
        try:
            return datetime(
                year=int(tokens[0]),
                month=int(tokens[1]),
                day=int(tokens[2]),
            ).strftime("%Y-%m-%d")
        except ValueError:
            return None
    month_match = re.match(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", candidate, re.IGNORECASE)
    if month_match:
        month = datetime.strptime(month_match.group(1), "%B").month
        return f"{month_match.group(2)}-{month:02d}-01"
    abbrev_match = re.match(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{4})", candidate, re.IGNORECASE)
    if abbrev_match:
        month = month_map.get(abbrev_match.group(1).lower())
        if month:
            return f"{abbrev_match.group(2)}-{month:02d}-01"
    month_year_match = re.match(r"(0?[1-9]|1[0-2])[/-](\d{4})", candidate)
    if month_year_match:
        month = int(month_year_match.group(1))
        year = month_year_match.group(2)
        return f"{year}-{month:02d}-01"
    return None


def _clean_product_name(value: str, *, manufacturer: Optional[str] = None) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"(?i)^product\s+name[:\-]\s*", "", cleaned)
    cleaned = cleaned.strip(" :-")
    if manufacturer and cleaned.lower() == manufacturer.lower():
        return ""
    return cleaned


def _select_product_name(
    pages: Sequence[PageData],
    result: FrontMatterResult,
    metadata_title: Optional[str],
    config: Optional[Dict[str, object]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    candidates = _collect_cover_lines(pages)
    manufacturer = (result.manufacturer or "").lower()

    pattern_bundle: List[tuple[re.Pattern[str], int]] = []
    if isinstance(config, dict):
        product_patterns = config.get("_product_patterns", {})
        if result.manufacturer and result.manufacturer in product_patterns:
            pattern_bundle.extend(product_patterns[result.manufacturer])
        pattern_bundle.extend(product_patterns.get("default", []))
    pattern_bundle.append((re.compile(r"(?i)product\s+name[:\-]\s*(.+)"), 1))

    for pattern, group_index in pattern_bundle:
        for line in candidates:
            match = pattern.search(line)
            if not match:
                continue
            try:
                extracted = match.group(group_index) if group_index <= match.lastindex else match.group(0)
            except IndexError:
                extracted = match.group(0)
            if extracted:
                cleaned = _clean_product_name(extracted, manufacturer=result.manufacturer)
                if cleaned:
                    return cleaned, "pattern"

    best_line = None
    best_score = 0.0
    for line in candidates:
        score = _score_title(line)
        if score <= 0:
            continue
        lowered = line.lower()
        if manufacturer and manufacturer in lowered:
            score *= 0.6
        if score > best_score:
            best_score = score
            best_line = line

    if best_line:
        cleaned = _clean_product_name(best_line, manufacturer=result.manufacturer)
        if cleaned:
            return cleaned, "cover_line"

    # Try to find a line that contains the detected model identifier
    if result.model:
        model_lower = result.model.lower()
        for line in candidates:
            if model_lower in line.lower():
                cleaned = _clean_product_name(line, manufacturer=result.manufacturer)
                if cleaned:
                    return cleaned, "model_hint"

    fallback_enabled = True
    if isinstance(config, dict):
        fallback_enabled = bool(config.get("product_name_from_filename", True))

    if fallback_enabled and metadata_title:
        cleaned = metadata_title.strip()
        if cleaned:
            normalized = _clean_product_name(cleaned, manufacturer=result.manufacturer)
            if normalized:
                return normalized, "metadata_title"

    return None, None


def _collect_cover_lines(pages: Sequence[PageData], max_pages: int = 3) -> List[str]:
    lines: List[str] = []
    for page in pages[:max_pages]:
        if not page or not page.lines:
            continue
        for raw_line in page.lines:
            stripped = raw_line.strip()
            if not stripped:
                continue
            lines.append(stripped)
    return lines


def _score_title(line: str) -> float:
    stripped = line.strip()
    if not stripped:
        return 0.0
    if stripped.endswith(("-", "–", "—")):
        return 0.0
    lowered = stripped.lower()
    if any(keyword in lowered for keyword in BLOCKLIST_KEYWORDS):
        return 0.0
    if re.search(r"\.{2,}\s*\d{1,3}$", stripped):
        return 0.0
    if len(stripped) < 4 or len(stripped) > 100:
        return 0.0
    if stripped.isupper() and len(stripped.split()) == 1:
        return 0.0
    alpha = sum(1 for char in stripped if char.isalpha())
    if alpha == 0:
        return 0.0
    uppercase_ratio = sum(1 for char in stripped if char.isupper()) / alpha
    digit_ratio = sum(1 for char in stripped if char.isdigit()) / max(len(stripped), 1)
    if digit_ratio > 0.4:
        return 0.0
    return len(stripped) * (1.0 + uppercase_ratio)


__all__ = ["extract_front_matter"]
