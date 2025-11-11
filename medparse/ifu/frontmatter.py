"""Front-matter extraction utilities for IFU documents."""

from __future__ import annotations

import functools
import re
from collections import Counter
from dataclasses import dataclass, field
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
            re.compile(r"ERBE\s+USA", re.IGNORECASE),
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
    (
        "Merit Medical Systems, Inc.",
        (
            re.compile(r"Merit\s+Medical\s+Systems", re.IGNORECASE),
            re.compile(r"Merit\s+Medical", re.IGNORECASE),
        ),
    ),
    (
        "Boston Scientific Corporation",
        (
            re.compile(r"Boston\s+Scientific\s+Corporation", re.IGNORECASE),
            re.compile(r"Boston\s+Scientific", re.IGNORECASE),
        ),
    ),
    (
        "Cook Medical Inc.",
        (
            re.compile(r"Cook\s+Medical", re.IGNORECASE),
            re.compile(r"Cook\s+Incorporated", re.IGNORECASE),
        ),
    ),
    (
        "Medtronic, Inc.",
        (
            re.compile(r"Medtronic", re.IGNORECASE),
            re.compile(r"Covidien", re.IGNORECASE),
        ),
    ),
    (
        "ConMed Corporation",
        (
            re.compile(r"ConMed\s+Corporation", re.IGNORECASE),
            re.compile(r"ConMed", re.IGNORECASE),
        ),
    ),
    (
        "Teleflex Incorporated",
        (
            re.compile(r"Teleflex\s+(?:Incorporated|Inc\.?)", re.IGNORECASE),
            re.compile(r"Teleflex\s+Medical", re.IGNORECASE),
        ),
    ),
    (
        "Pulmonx Corporation",
        (
            re.compile(r"Pulmonx\s+Corporation", re.IGNORECASE),
            re.compile(r"Pulmonx", re.IGNORECASE),
            re.compile(r"Zephyr\s+Endobronchial\s+Valve", re.IGNORECASE),
        ),
    ),
]

IDENTIFIER_PATTERNS: Dict[str, Sequence[re.Pattern[str]]] = {
    "part_number": (
        re.compile(
            r"(?:PN|P/N|REF|Catalog(?:ue)?\s*(?:No\.?|Number)?|Cat(?:\.)?\s*No\.?|Order\s*(?:No\.?|Number)|Document\s*(?:No\.|#)|Article\s*(?:No\.?|Number))\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/]{2,})",
            re.IGNORECASE,
        ),
    ),
    "revision": (
        re.compile(r"(?:Rev(?:ision)?|Version)\s*[:#]?\s*([A-Z0-9][A-Z0-9\.\-]{0,9})", re.IGNORECASE),
        re.compile(r"(?:Revision\s*(?:Level|Code)|Rev\.)\s*[:#]?\s*([A-Z0-9][A-Z0-9\.\-]{0,9})", re.IGNORECASE),
    ),
    "publication_date": (
        # Standard date formats with labels
        re.compile(r"(?:Published|Issue(?:d)?|Revision|Release(?:d)?|Effective|Publication|Date\s*of\s*issue|Printed\s*on|Created(?:\s*on)?|Last\s+(?:updated|revised))\s*(?:Date)?\s*[:#]?\s*([0-9]{4}[-/\.][01]?[0-9](?:[-/\.][0-3]?[0-9])?)", re.IGNORECASE),
        # Month + year formats
        re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.IGNORECASE),
        re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{4})", re.IGNORECASE),
        # MM/YYYY or MM-YYYY
        re.compile(r"(0?[1-9]|1[0-2])[/-](\d{4})"),
        # Document number formats (common in IFUs)
        re.compile(r"(?:D0\d{5,6})\s*[\[(]?\s*(\d{4}-\d{2})\s*[\])]?"),
        # Revision date
        re.compile(r"(?:Rev(?:ision)?\.?|Version)\s*(?:Date)?\s*[:#]?\s*([0-9]{4}[-/\.][01]?[0-9](?:[-/\.][0-3]?[0-9])?)", re.IGNORECASE),
        # Copyright year (last resort - prefer revision/publication dates)
        re.compile(r"©\s*(\d{4})", re.IGNORECASE),
        re.compile(r"Copyright\s+©?\s*(\d{4})", re.IGNORECASE),
    ),
    "model": (
        re.compile(r"(?:Model(?:\s+No\.?|\s+Number)?|Type|Series)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/\s]{1,20})", re.IGNORECASE),
        re.compile(r"System\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/\s]{1,20})", re.IGNORECASE),
        re.compile(r"(?:Product\s+)?Code\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/]{1,15})", re.IGNORECASE),
        re.compile(r"(?:Device\s+)?ID\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/]{1,15})", re.IGNORECASE),
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
FOOTER_SAMPLE_PAGES = 2
DOMAIN_PATTERN = re.compile(r"https?://(?:www\.)?([A-Za-z0-9\-]+)\.(?:com|org|net|de|eu|co\.[a-z]{2}|[a-z]{2,})", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9_.+-]+@([A-Za-z0-9\-]+)\.[A-Za-z]{2,}", re.IGNORECASE)
COPYRIGHT_PATTERN = re.compile(r"©\s*(?:\d{4}\s*)?([A-Z][A-Za-z0-9&\-\s]{2,})")


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

    print_code_patterns: List[re.Pattern[str]] = []
    for pattern in data.get("print_code_patterns", []) or []:
        try:
            print_code_patterns.append(re.compile(str(pattern), re.IGNORECASE))
        except re.error:
            continue
    data["_print_code_patterns"] = print_code_patterns

    return data


@functools.lru_cache(maxsize=1)
def load_pattern_bundle() -> Dict[str, List[str]]:
    """Return the configured regex bundle used for second-pass backfills."""

    config = _load_frontmatter_config()
    raw_bundle = config.get("pattern_bundle") if isinstance(config, dict) else {}
    if not isinstance(raw_bundle, dict):
        return {}

    bundle: Dict[str, List[str]] = {}
    for key, values in raw_bundle.items():
        if not isinstance(values, list):
            continue
        cleaned: List[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            stripped = value.strip()
            if stripped:
                cleaned.append(stripped)
        if cleaned:
            bundle[str(key)] = cleaned
    return bundle
def infer_manufacturer_from_footer_texts(
    texts: Sequence[str],
    *,
    domain_hits: bool = True,
    copyright_hits: bool = True,
) -> Optional[str]:
    """Infer manufacturer name from footer/copyright text fragments."""

    if not texts:
        return None

    candidates: Counter[str] = Counter()
    domains: List[str] = []

    for raw_line in texts:
        line = (raw_line or "").strip()
        if not line:
            continue
        if domain_hits:
            for match in DOMAIN_PATTERN.finditer(line):
                domains.append(match.group(1).lower())
            for match in EMAIL_PATTERN.finditer(line):
                domains.append(match.group(1).lower())
        if copyright_hits:
            match = COPYRIGHT_PATTERN.search(line)
            if match:
                name = match.group(1).strip(" .")
                if name:
                    candidates[name] += 3

    proper_pattern = re.compile(r"\b([A-Z][A-Za-z0-9&\-]+(?:\s+[A-Z][A-Za-z0-9&\-]+){0,3})\b")
    for raw_line in texts:
        for match in proper_pattern.finditer(raw_line or ""):
            token = match.group(1).strip()
            if not token or len(token) < 3:
                continue
            lowered = token.lower()
            if lowered in {"warning", "caution", "danger", "notice", "important"}:
                continue
            candidates[token] += 1

    if not candidates:
        return None

    if domains:
        for name in list(candidates.keys()):
            lowered = name.lower().replace(" ", "")
            if any(domain in lowered or lowered in domain for domain in domains):
                candidates[name] += 5

    best = candidates.most_common(1)
    if not best:
        return None
    name, score = best[0]
    if score < 2:
        return None
    return name.strip()


def infer_manufacturer_from_footer(
    pages: Sequence[PageData],
    *,
    domain_hits: bool = True,
    copyright_hits: bool = True,
) -> Optional[str]:
    """Infer manufacturer name from the first few pages."""

    if not pages:
        return None

    samples: List[str] = []
    for page in pages[:FOOTER_SAMPLE_PAGES]:
        if page.lines:
            tail = page.lines[-6:] if len(page.lines) > 6 else page.lines
            samples.extend(tail)
        elif page.text:
            samples.extend(page.text.splitlines()[-6:])
    return infer_manufacturer_from_footer_texts(samples, domain_hits=domain_hits, copyright_hits=copyright_hits)


@dataclass(slots=True)
class FrontMatterResult:
    manufacturer: Optional[str] = None
    product_name: Optional[str] = None
    product_name_source: Optional[str] = None
    part_number: Optional[str] = None
    revision: Optional[str] = None
    publication_date: Optional[str] = None
    publication_date_precision: Optional[str] = None
    model: Optional[str] = None
    print_code: Optional[str] = None
    provenance: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Optional[str]]:
        payload: Dict[str, Optional[str]] = {
            "manufacturer": self.manufacturer,
            "product_name": self.product_name,
            "product_name_source": self.product_name_source,
            "part_number": self.part_number,
            "revision": self.revision,
            "publication_date": self.publication_date,
            "publication_date_precision": self.publication_date_precision,
            "model": self.model,
            "print_code": self.print_code,
        }
        if self.provenance:
            payload["_provenance"] = dict(self.provenance)
        return payload

    def record(self, field: str, source: Optional[str]) -> None:
        if source:
            self.provenance[field] = source


def extract_front_matter(
    pages: Sequence[PageData],
    *,
    metadata_title: Optional[str] = None,
    manufacturer_hint: Optional[str] = None,
    manufacturer_source: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Extract manufacturer, product name, and identifiers from the cover pages."""

    config = _load_frontmatter_config()
    result = FrontMatterResult()
    cover_text = _join_page_text(pages[:3])
    tail_text = _join_page_text(pages[-3:])
    normalized_title = metadata_title.replace("_", " ") if metadata_title else ""
    lower_title = normalized_title.lower() if normalized_title else ""

    if manufacturer_hint:
        result.manufacturer = manufacturer_hint
        result.record("manufacturer", manufacturer_source or "detector")

    if not result.manufacturer:
        manufacturer_cover = _detect_manufacturer(cover_text, config)
        if manufacturer_cover:
            result.manufacturer = manufacturer_cover
            result.record("manufacturer", "cover")
        else:
            manufacturer_tail = _detect_manufacturer(tail_text, config)
            if manufacturer_tail:
                result.manufacturer = manufacturer_tail
                result.record("manufacturer", "tail")

    if not result.manufacturer and lower_title:
        if "erbe" in lower_title:
            result.manufacturer = "ERBE Elektromedizin GmbH"
        elif "intuitive" in lower_title:
            result.manufacturer = "Intuitive Surgical, Inc."
        elif "olympus" in lower_title:
            result.manufacturer = "Olympus Corporation"
        if result.manufacturer:
            result.record("manufacturer", "metadata_title")

    if not result.manufacturer:
        footer_guess = infer_manufacturer_from_footer(pages)
        if footer_guess:
            result.manufacturer = footer_guess
            result.record("manufacturer", "footer")

    if not result.model:
        alt_match = re.search(r"\bALT[\s\-]*PRO\b", cover_text, re.IGNORECASE)
        if alt_match:
            result.model = "ALT PRO"
            result.record("model", "cover")

    for field, patterns in IDENTIFIER_PATTERNS.items():
        match_info = _search_patterns(cover_text, patterns)
        source = "pattern_cover"
        if not match_info:
            match_info = _search_patterns(tail_text, patterns)
            source = "pattern_tail"
        if not match_info:
            continue
        raw_value, _pattern = match_info
        if field == "publication_date":
            normalized = _normalize_date(raw_value)
            if normalized:
                result.publication_date = normalized
                result.record("publication_date", source)
                if re.fullmatch(r"\d{4}-\d{2}$", normalized):
                    result.publication_date_precision = "month"
        elif field == "part_number":
            result.part_number = raw_value.strip().upper()
            result.record("part_number", source)
        elif field == "revision":
            result.revision = raw_value.strip().upper()
            result.record("revision", source)
        elif field == "model":
            result.model = raw_value.strip()
            result.record("model", source)

    print_code_patterns = config.get("_print_code_patterns") if isinstance(config, dict) else None
    if isinstance(print_code_patterns, list) and print_code_patterns:
        match_info = _search_patterns(cover_text, print_code_patterns)
        source = "pattern_cover"
        if not match_info:
            match_info = _search_patterns(tail_text, print_code_patterns)
            source = "pattern_tail"
        if match_info:
            raw_value, _pattern = match_info
            result.print_code = raw_value.strip()
            result.record("print_code", source)

    product_name, product_source = _select_product_name(pages, result, metadata_title, config)
    if product_name:
        result.product_name = product_name
        result.product_name_source = product_source or "pattern"
        result.record("product_name", result.product_name_source)
    elif result.model and result.manufacturer:
        result.product_name = f"{result.manufacturer} {result.model}".strip()
        result.product_name_source = "model_hint"
        result.record("product_name", result.product_name_source)
    if metadata_title:
        if not result.part_number:
            part_match = re.search(r"\b([A-Z0-9]{2,}[-_][A-Z0-9]{2,})\b", normalized_title, re.IGNORECASE)
            if not part_match:
                part_match = re.search(r"\b([0-9]{3,}[-_][0-9]{2,})\b", normalized_title)
            if part_match:
                result.part_number = part_match.group(1).upper()
                result.record("part_number", "filename")
        if not result.part_number:
            doc_match = re.search(r"\b(D[0-9]{5,})\b", normalized_title, re.IGNORECASE)
            if doc_match:
                result.part_number = doc_match.group(1).upper()
                result.record("part_number", "filename")
        if not result.revision:
            rev_match = re.search(r"\brev(?:ision)?[_\-\s]*([A-Z0-9\.\-]{1,10})", normalized_title, re.IGNORECASE)
            if rev_match:
                result.revision = rev_match.group(1).upper()
                result.record("revision", "filename")

    return result.as_dict()


def _join_page_text(pages: Sequence[PageData]) -> str:
    text = "\n".join(page.text or "" for page in pages if page is not None)
    text = re.sub(r"\bGmb\s+H\b", "GmbH", text)
    return text


def _detect_manufacturer(text: str, config: Optional[Dict[str, object]] = None) -> Optional[str]:
    patterns_bundle = list(MANUFACTURER_PATTERNS)
    if isinstance(config, dict):
        patterns_bundle.extend(config.get("_manufacturer_patterns", []))
    for canonical, patterns in patterns_bundle:
        if any(pattern.search(text) for pattern in patterns):
            return canonical
    return None


def _search_patterns(text: str, patterns: Sequence[re.Pattern[str]]) -> Optional[Tuple[str, re.Pattern[str]]]:
    if not text:
        return None
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        if match.lastindex:
            value = match.group(match.lastindex)
        else:
            value = match.group(0)
        return value, pattern
    return None


def _normalize_date(raw: str) -> Optional[str]:
    candidate = raw.strip()
    if not candidate:
        return None
    candidate = candidate.replace("/", "-").replace(".", "-")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return candidate
    if re.fullmatch(r"\d{4}-\d{2}", candidate):
        return candidate
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
        return f"{year}-{month:02d}"
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


__all__ = [
    "extract_front_matter",
    "infer_manufacturer_from_footer",
    "infer_manufacturer_from_footer_texts",
    "load_pattern_bundle",
]
