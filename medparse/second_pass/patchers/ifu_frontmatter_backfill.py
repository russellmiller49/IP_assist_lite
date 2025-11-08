"""Second-pass patcher that backfills IFU front-matter metadata."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument
from medparse.ifu.frontmatter import infer_manufacturer_from_footer_texts, load_pattern_bundle

from ..types import SecondPassContext, SecondPassPatchResult

PATCH_NAME = "ifu_frontmatter_backfill"

MONTH_LOOKUP = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "sept": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}

PUBLISHED_KEYWORDS = ("published", "issued", "printed", "publication", "effective")

LEGACY_PATTERNS: Dict[str, str] = {
    "part_number": (
        r"(?:part\s*(?:number|no\.?)|p/?n|catalog(?:ue)?\s*(?:no\.?|number)?|cat(?:\.)?\s*no\.?|order\s*(?:no\.?|number)|"
        r"ref|article\s*(?:no\.?|number)|document\s*(?:no\.?|number))\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/]{2,})"
    ),
    "revision": r"\brev(?:ision)?\s*[:#]?\s*([A-Z0-9.\-]+)",
    "publication_date": r"\b(?:date|issued|publication)\s*[:#]?\s*([0-9]{4}(?:[./-][0-9]{1,2}){0,2})",
    "model": r"\bmodel\s*[:#]?\s*([A-Z0-9\- ]{3,})",
}


def _earliest_pages(paragraph_store: Dict[str, Dict[str, object]], limit: int = 3) -> Dict[str, Dict[str, object]]:
    if not paragraph_store:
        return {}
    pages = [
        entry
        for entry in paragraph_store.values()
        if isinstance(entry.get("page"), int)
    ]
    if not pages:
        return paragraph_store
    min_page = min(entry.get("page") for entry in pages if isinstance(entry.get("page"), int))
    max_page = min_page + max(limit - 1, 0)
    return {
        key: entry
        for key, entry in paragraph_store.items()
        if isinstance(entry.get("page"), int) and min_page <= entry.get("page") <= max_page
    }


def _latest_pages(paragraph_store: Dict[str, Dict[str, object]], limit: int = 2) -> Dict[str, Dict[str, object]]:
    if not paragraph_store:
        return {}
    pages = [
        entry
        for entry in paragraph_store.values()
        if isinstance(entry.get("page"), int)
    ]
    if not pages:
        return {}
    max_page = max(entry.get("page") for entry in pages if isinstance(entry.get("page"), int))
    min_page = max(max_page - max(limit - 1, 0), 0)
    return {
        key: entry
        for key, entry in paragraph_store.items()
        if isinstance(entry.get("page"), int) and min_page <= entry.get("page") <= max_page
    }


def _normalize_date_token(value: str) -> str:
    token = (value or "").strip()
    if not token:
        return token
    month_match = re.match(
        r"(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[\s\-.,]+(\d{4})",
        token,
        re.IGNORECASE,
    )
    if month_match:
        month_key = month_match.group(1).lower()
        month_value = MONTH_LOOKUP.get(month_key, "01")
        year_value = month_match.group(2)
        return f"{year_value}-{month_value}"
    parts = re.split(r"[./-]", token)
    parts = [part for part in parts if part]
    if not parts:
        return token
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        first, second = parts
        if len(first) == 4:
            year, month = first, second
        else:
            year, month = second, first
        return f"{year}-{month.zfill(2)}"
    if len(parts) >= 3:
        year_candidates = [part for part in parts if len(part) == 4]
        if year_candidates:
            year = year_candidates[-1]
            remaining = [part for part in parts if part != year]
            month = remaining[0] if remaining else "01"
            day = remaining[1] if len(remaining) > 1 else "01"
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return token


def _ordered_paragraph_entries(paragraph_store: Dict[str, Dict[str, object]]) -> List[Dict[str, object]]:
    ordered: List[Tuple[int, int, Dict[str, object]]] = []
    for entry in paragraph_store.values():
        page = entry.get("page")
        if not isinstance(page, int):
            page_index = 10**6
        else:
            page_index = page
        orders = entry.get("order") or []
        order_index = 10**6
        if isinstance(orders, (list, tuple)):
            for raw in orders:
                try:
                    candidate = int(raw)
                except (TypeError, ValueError):
                    continue
                order_index = min(order_index, candidate)
        ordered.append((page_index, order_index, entry))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in ordered]


def _compile_pattern_list(patterns: List[str]) -> List[re.Pattern[str]]:
    compiled: List[re.Pattern[str]] = []
    for pattern in patterns:
        if not pattern:
            continue
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            continue
    return compiled


def _apply_pattern_list(text: str, patterns: List[re.Pattern[str]]) -> Optional[str]:
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        if match.groups():
            for group in match.groups():
                if group and group.strip():
                    return group.strip()
        return match.group(0).strip()
    return None


def _normalize_manufacturer(value: str) -> Optional[str]:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    lowered = candidate.lower()
    if "intuitive" in lowered:
        return "Intuitive Surgical, Inc."
    if "erbe" in lowered:
        return "ERBE Elektromedizin GmbH"
    if "olympus" in lowered:
        return "Olympus Corporation"
    return candidate


def _normalize_part_number(value: str) -> Optional[str]:
    if not value:
        return None
    return value.strip().upper()


def _sanitize_revision_token(value: str) -> Optional[str]:
    if not value:
        return None
    token = value.strip().upper()
    if not token:
        return None
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,10}", token):
        return None
    if re.fullmatch(r"[A-Z]{4,}", token) and not re.search(r"\d", token):
        return None
    return token


def _normalize_revision(value: str) -> Optional[str]:
    return _sanitize_revision_token(value)


def _normalize_model(value: str) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip(" :-\t")
    if not cleaned:
        return None
    if re.search(r"\bALT[\s\-]?PRO\b", cleaned, re.IGNORECASE):
        return "ALT PRO"
    if re.search(r"\bBW[\s\-]?18V\b", cleaned, re.IGNORECASE):
        return "BW-18V"
    return cleaned


def _normalize_product_name(value: str) -> Optional[str]:
    if not value:
        return None
    cleaned = re.sub(r"\s{2,}", " ", value.strip(" :-\t"))
    if not cleaned:
        return None
    return cleaned


def _resolve_frontmatter_settings(ctx: SecondPassContext) -> Dict[str, object]:
    if not isinstance(ctx.config, dict):
        return {}
    ifu_cfg = ctx.config.get("ifu", {})
    if not isinstance(ifu_cfg, dict):
        return {}
    frontmatter_cfg = ifu_cfg.get("frontmatter", {})
    return frontmatter_cfg if isinstance(frontmatter_cfg, dict) else {}


def _drop_heading_candidates(frontmatter_cfg: Dict[str, object]) -> set[str]:
    headings = frontmatter_cfg.get("drop_headings_as_product", []) if isinstance(frontmatter_cfg, dict) else []
    if not isinstance(headings, list):
        return set()
    return {str(value).strip().upper() for value in headings if isinstance(value, str) and value.strip()}


def _vendor_settings(frontmatter_cfg: Dict[str, object], vendor_key: str) -> Dict[str, object]:
    vendor_block = frontmatter_cfg.get("vendor_heuristics", {}) if isinstance(frontmatter_cfg, dict) else {}
    if not isinstance(vendor_block, dict):
        return {}
    entry = vendor_block.get(vendor_key)
    return entry if isinstance(entry, dict) else {}


def _resolve_pattern_bundle(ctx: SecondPassContext) -> Dict[str, List[str]]:
    bundle = load_pattern_bundle()
    if not isinstance(bundle, dict):
        bundle = {}

    if isinstance(ctx.config, dict):
        override_bundle = ctx.config.get("pattern_bundle")
        if isinstance(override_bundle, dict):
            for key, values in override_bundle.items():
                if not isinstance(values, list):
                    continue
                cleaned = [str(value).strip() for value in values if isinstance(value, str) and value.strip()]
                if cleaned:
                    bundle[str(key)] = cleaned
        legacy_override = ctx.config.get("frontmatter_patterns")
        if isinstance(legacy_override, dict):
            for key, pattern in legacy_override.items():
                if isinstance(pattern, str) and pattern.strip():
                    bundle[str(key)] = [pattern.strip()]

    if not bundle:
        bundle = {key: [pattern] for key, pattern in LEGACY_PATTERNS.items()}
    else:
        for legacy_key, legacy_pattern in LEGACY_PATTERNS.items():
            bundle.setdefault(legacy_key, [legacy_pattern])
    return bundle


CHANNEL_BRUSH_PATTERN = re.compile(r"\b(BW\s?-?\d{1,3}[A-Z0-9]{0,2})\b", re.IGNORECASE)


def _find_channel_brush(entries: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    hit_indices: List[int] = []
    for idx, entry in enumerate(entries):
        text = entry.get("text")
        if isinstance(text, str) and "channel cleaning brush" in text.lower():
            hit_indices.append(idx)
    if not hit_indices:
        return None
    for idx in hit_indices:
        start = max(0, idx - 3)
        end = min(len(entries), idx + 4)
        for neighbor in range(start, end):
            text = entries[neighbor].get("text")
            if not isinstance(text, str):
                continue
            match = CHANNEL_BRUSH_PATTERN.search(text)
            if not match:
                continue
            token = match.group(1).upper().replace(" ", "-")
            return {
                "part_number": token,
                "page": entries[neighbor].get("page"),
            }
    return None


def _find_print_code(entries: List[Dict[str, object]], pattern_str: Optional[str]) -> Optional[str]:
    if not pattern_str:
        return None
    try:
        pattern = re.compile(pattern_str, re.IGNORECASE)
    except re.error:
        return None
    for entry in entries:
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def _apply_channel_brush_template(
    document: IFUDocument,
    entries: List[Dict[str, object]],
    vendor_cfg: Dict[str, object],
    modifications: Dict[str, int],
) -> bool:
    context = _find_channel_brush(entries)
    if not context:
        return False
    applied = False
    part_number = context.get("part_number")
    if isinstance(part_number, str) and part_number and document.part_number != part_number:
        document.part_number = part_number
        modifications["part_number"] = modifications.get("part_number", 0) + 1
        applied = True
    if document.model != "Channel Cleaning Brush":
        document.model = "Channel Cleaning Brush"
        modifications["model"] = modifications.get("model", 0) + 1
        applied = True
    manufacturer_hint = vendor_cfg.get("manufacturer") if isinstance(vendor_cfg, dict) else None
    if manufacturer_hint and not document.manufacturer:
        document.manufacturer = str(manufacturer_hint)
        modifications["manufacturer"] = modifications.get("manufacturer", 0) + 1
        applied = True
    template = vendor_cfg.get("product_name_template") if isinstance(vendor_cfg, dict) else None
    if template and document.manufacturer and document.part_number and document.model:
        try:
            product_name = str(template).format(
                manufacturer=document.manufacturer,
                part_number=document.part_number,
                model=document.model,
            ).strip()
        except Exception:
            product_name = None
        if product_name and document.product_name != product_name:
            document.product_name = product_name
            try:
                document.product_name_source = "second_pass_vendor_template"  # type: ignore[attr-defined]
            except Exception:
                pass
            modifications["product_name"] = modifications.get("product_name", 0) + 1
            applied = True
    return applied

def _extract_fields(
    paragraph_store: Dict[str, Dict[str, object]],
    pattern_bundle: Dict[str, List[str]],
    *,
    frontmatter_cfg: Optional[Dict[str, object]] = None,
) -> Dict[str, str]:
    compiled_catalog: Dict[str, List[re.Pattern[str]]] = {}
    for key, patterns in pattern_bundle.items():
        compiled_catalog[key] = _compile_pattern_list(patterns)

    found: Dict[str, str] = {}
    ordered_entries = _ordered_paragraph_entries(paragraph_store)
    combined_text = "\n".join(
        str(entry.get("text") or "")
        for entry in ordered_entries
        if isinstance(entry, dict)
    )
    manufacturer_candidate: Optional[str] = None
    drop_headings = _drop_heading_candidates(frontmatter_cfg or {})

    for entry in ordered_entries:
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if not stripped:
            continue

        if "part_number" not in found and "part_number" in compiled_catalog:
            match = _apply_pattern_list(stripped, compiled_catalog["part_number"])
            normalized = _normalize_part_number(match) if match else None
            if normalized:
                found["part_number"] = normalized

        if "revision" not in found and "revision" in compiled_catalog:
            match = _apply_pattern_list(stripped, compiled_catalog["revision"])
            normalized = _normalize_revision(match) if match else None
            if normalized:
                found["revision"] = normalized

        if "publication_date" not in found and "publication_date" in compiled_catalog:
            match = _apply_pattern_list(stripped, compiled_catalog["publication_date"])
            normalized = _normalize_date_token(match) if match else None
            if normalized:
                found["publication_date"] = normalized

        if "model" not in found and "model" in compiled_catalog:
            match = _apply_pattern_list(stripped, compiled_catalog["model"])
            normalized = _normalize_model(match) if match else None
            if normalized:
                found["model"] = normalized

        if "product_name" not in found and "product_name" in compiled_catalog:
            match = _apply_pattern_list(stripped, compiled_catalog["product_name"])
            normalized = _normalize_product_name(match) if match else None
            if normalized and normalized.strip().upper() not in drop_headings:
                found["product_name"] = normalized

        if manufacturer_candidate is None and "manufacturers" in compiled_catalog:
            match = _apply_pattern_list(stripped, compiled_catalog["manufacturers"])
            normalized = _normalize_manufacturer(match) if match else None
            if normalized:
                manufacturer_candidate = normalized

        if "publication_date" not in found:
            doi_match = re.search(r"date of issue\s*[:#]?\s*([0-9]{4}(?:[./-][0-9]{1,2}){0,2})", stripped, re.IGNORECASE)
            if doi_match:
                normalized = _normalize_date_token(doi_match.group(1))
                if normalized:
                    found["publication_date"] = normalized

    if "publication_date" not in found:
        for entry in ordered_entries:
            text = entry.get("text")
            if not isinstance(text, str):
                continue
            lowered = text.lower()
            if "copyright" in lowered or "printed" in lowered:
                match = re.search(r"(20\d{2})(?:[./-](\d{1,2}))?(?:[./-](\d{1,2}))?", text)
                if match:
                    year = match.group(1)
                    month = match.group(2)
                    day = match.group(3)
                    if month and day:
                        found["publication_date"] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    elif month:
                        found["publication_date"] = f"{year}-{month.zfill(2)}"
                    else:
                        found["publication_date"] = year
                    break

    if "publication_date" not in found:
        rev_pattern = re.compile(
            r"(?:printed|rev(?:ision)?|revision)\s*(?:on|date|version|:)?\s*([0-9]{4}(?:[./-][0-9]{1,2}){0,2})",
            re.IGNORECASE,
        )
        alt_pattern = re.compile(r"\b([0-9]{1,2}[./-][0-9]{4})\b")
        for entry in ordered_entries:
            text = entry.get("text")
            if not isinstance(text, str):
                continue
            match = rev_pattern.search(text)
            if match:
                normalized = _normalize_date_token(match.group(1))
                if normalized:
                    found["publication_date"] = normalized
                    break
            alt_match = alt_pattern.search(text)
            if alt_match:
                normalized = _normalize_date_token(alt_match.group(1))
                if normalized:
                    found["publication_date"] = normalized
                    break

    if "publication_date" not in found:
        full_date_pattern = re.compile(
            r"\b(20\d{2}|19\d{2})[-/ .](0?[1-9]|1[0-2])[-/ .](0?[1-9]|[12]\d|3[01])\b"
        )
        for entry in ordered_entries:
            text = entry.get("text")
            if not isinstance(text, str):
                continue
            for match in full_date_pattern.finditer(text):
                normalized = f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
                if normalized:
                    found["publication_date"] = normalized
                    break
            if "publication_date" in found:
                break

    if "publication_date" not in found:
        month_pattern = re.compile(
            r"(?:"
            r"(?:Published|Issued|Printed|Publication|Effective)[\s:]*"
            r")?(January|February|March|April|May|June|July|August|September|October|November|December|"
            r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
            r"[^\d]{0,3}(\d{4})",
            re.IGNORECASE,
        )
        for entry in ordered_entries:
            text = entry.get("text")
            if not isinstance(text, str):
                continue
            match = month_pattern.search(text)
            if match:
                normalized = _normalize_date_token(" ".join(match.groups()))
                if normalized:
                    found["publication_date"] = normalized
                    break

    if "model" not in found:
        for entry in ordered_entries:
            text = entry.get("text")
            page = entry.get("page")
            if not isinstance(text, str):
                continue
            if page is not None and page > 2:
                continue
            stripped = text.strip()
            lowered = stripped.lower()
            if not stripped or stripped.startswith("ce "):
                continue
            if len(stripped) > 120:
                continue
            if "instruction" in lowered:
                after_instruction = stripped.lower().split("instruction", 1)[1].strip(" -:.")
                if after_instruction:
                    found["model"] = after_instruction.title()
                    break
                continue
            if len(stripped.split()) >= 2 and stripped[:1].isalpha():
                found["model"] = stripped
                break

    if "model" not in found:
        alt_match = re.search(r"\bALT[\s\-]*PRO\b", combined_text, re.IGNORECASE)
        if alt_match:
            found["model"] = "ALT PRO"

    if manufacturer_candidate:
        found["_manufacturer_candidate"] = manufacturer_candidate

    return found


def apply_ifu_frontmatter_backfill(document: BaseDocument, ctx: SecondPassContext) -> SecondPassPatchResult:
    if not isinstance(document, IFUDocument):
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="doc_not_ifu")

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    second_pass_bucket = pipeline_info.setdefault("second_pass", {})
    applied = second_pass_bucket.get("patches_applied") or []
    if isinstance(applied, list) and PATCH_NAME in applied:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="already_applied")

    frontmatter_cfg = _resolve_frontmatter_settings(ctx)
    drop_headings = _drop_heading_candidates(frontmatter_cfg)
    ordered_entries = _ordered_paragraph_entries(ctx.paragraph_store)
    vendor_olympus = _vendor_settings(frontmatter_cfg, "olympus")

    product_name_reset = False
    existing_product = getattr(document, "product_name", None)
    if isinstance(existing_product, str) and existing_product.strip():
        if existing_product.strip().upper() in drop_headings:
            document.product_name = None
            product_name_reset = True

    revision_reset = False
    if document.revision:
        normalized_revision = _sanitize_revision_token(document.revision)
        if normalized_revision:
            document.revision = normalized_revision
        else:
            document.revision = None
            revision_reset = True

    fields_missing = {
        "manufacturer": not document.manufacturer,
        "part_number": not document.part_number,
        "revision": not document.revision,
        "publication_date": not document.publication_date,
        "model": not document.model,
        "product_name": not getattr(document, "product_name", None),
    }
    needs_processing = any(fields_missing.values()) or product_name_reset or revision_reset
    if not needs_processing:
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="frontmatter_complete")

    pattern_bundle = _resolve_pattern_bundle(ctx)
    early_store = _earliest_pages(ctx.paragraph_store, limit=3)
    late_store = _latest_pages(ctx.paragraph_store, limit=2) if any(fields_missing.values()) else {}

    extracted = _extract_fields(early_store, pattern_bundle, frontmatter_cfg=frontmatter_cfg)
    if late_store:
        late_extracted = _extract_fields(late_store, pattern_bundle, frontmatter_cfg=frontmatter_cfg)
        for field, value in late_extracted.items():
            extracted.setdefault(field, value)

    manufacturer_candidate = extracted.pop("_manufacturer_candidate", None)
    modifications: Dict[str, int] = {}
    extra_meta: Dict[str, int] = {}
    reason_tags: List[str] = ["frontmatter_backfill"]

    if fields_missing["manufacturer"]:
        footer_lines: List[str] = []
        for entry in early_store.values():
            text = entry.get("text")
            if isinstance(text, str) and text.strip():
                footer_lines.extend(text.splitlines())
        if not footer_lines and late_store:
            for entry in late_store.values():
                text = entry.get("text")
                if isinstance(text, str) and text.strip():
                    footer_lines.extend(text.splitlines())
        manufacturer_guess = manufacturer_candidate or infer_manufacturer_from_footer_texts(footer_lines)
        if manufacturer_guess:
            normalized_manufacturer = _normalize_manufacturer(manufacturer_guess) or manufacturer_guess
            document.manufacturer = normalized_manufacturer
            modifications["manufacturer"] = modifications.get("manufacturer", 0) + 1

    if fields_missing["product_name"] and extracted.get("product_name"):
        document.product_name = extracted["product_name"]
        try:
            document.product_name_source = "second_pass_backfill"  # type: ignore[attr-defined]
        except Exception:
            pass
        modifications["product_name"] = modifications.get("product_name", 0) + 1
    if fields_missing["part_number"] and extracted.get("part_number"):
        document.part_number = extracted["part_number"]
        modifications["part_number"] = modifications.get("part_number", 0) + 1
    if fields_missing["revision"] and extracted.get("revision"):
        document.revision = extracted["revision"]
        modifications["revision"] = modifications.get("revision", 0) + 1
    if fields_missing["publication_date"] and extracted.get("publication_date"):
        document.publication_date = extracted["publication_date"]
        modifications["publication_date"] = modifications.get("publication_date", 0) + 1
    if fields_missing["model"] and extracted.get("model"):
        raw_model = extracted["model"]
        candidate_lines = [line.strip(" -") for line in str(raw_model).splitlines() if line.strip()]
        cleaned_model = candidate_lines[-1] if candidate_lines else str(raw_model).strip()
        for line in candidate_lines:
            if re.search(r"\bALT[\s\-]*PRO\b", line, re.IGNORECASE):
                cleaned_model = "ALT PRO"
                break
        document.model = cleaned_model
        modifications["model"] = modifications.get("model", 0) + 1

    if product_name_reset:
        extra_meta["product_name_reset"] = 1
        reason_tags.append("frontmatter_backfill:product_reset")
    if revision_reset:
        extra_meta["revision_sanitized"] = extra_meta.get("revision_sanitized", 0) + 1
        reason_tags.append("frontmatter_backfill:revision_sanitized")
        pipeline_info["front_matter_revision_sanitized"] = True
        warnings = pipeline_info.setdefault("threshold_warnings", [])
        if isinstance(warnings, list) and "front_matter_revision_sanitized" not in warnings:
            warnings.append("front_matter_revision_sanitized")

    channel_applied = _apply_channel_brush_template(document, ordered_entries, vendor_olympus, modifications)
    if channel_applied:
        reason_tags.append("frontmatter_backfill:channel_brush")

    late_entries_ordered = _ordered_paragraph_entries(late_store) if late_store else []
    print_code = _find_print_code(late_entries_ordered or ordered_entries[-6:], vendor_olympus.get("print_code_pattern")) if vendor_olympus else None
    if print_code:
        front_meta = pipeline_info.setdefault("front_matter_meta", {})
        if not isinstance(front_meta, dict):
            front_meta = {}
            pipeline_info["front_matter_meta"] = front_meta
        front_meta["print_code"] = print_code
        extra_meta["print_code"] = 1

    if not modifications and not extra_meta:
        pipeline_info.setdefault("front_matter_fallback_reason", "not_detected")
        pipeline_info["front_matter_incomplete"] = True
        document.pipeline_info = pipeline_info
        return SecondPassPatchResult.skipped_result(PATCH_NAME, reason="no_fields_detected")

    mod_payload = {f"front_matter_{field}": int(count) for field, count in modifications.items()}
    for key, count in extra_meta.items():
        mod_payload[f"front_matter_{key}"] = int(count)

    meta = second_pass_bucket.setdefault("meta", {})
    for key, count in mod_payload.items():
        meta[key] = meta.get(key, 0) + count

    mod_bucket = second_pass_bucket.setdefault("modifications", {})
    for key, count in mod_payload.items():
        mod_bucket[key] = mod_bucket.get(key, 0) + count

    pipeline_info.setdefault("front_matter_fallback_reason", "second_pass_backfill")
    patches_applied = second_pass_bucket.setdefault("patches_applied", [])
    if PATCH_NAME not in patches_applied:
        patches_applied.append(PATCH_NAME)
    applied_list = second_pass_bucket.setdefault("applied", [])
    if PATCH_NAME not in applied_list:
        applied_list.append(PATCH_NAME)
    reasons_list = second_pass_bucket.setdefault("reasons", [])
    for tag in reason_tags:
        if tag not in reasons_list:
            reasons_list.append(tag)

    remaining_missing = {
        "manufacturer": not document.manufacturer,
        "part_number": not document.part_number,
        "revision": not document.revision,
        "publication_date": not document.publication_date,
        "model": not document.model,
        "product_name": not getattr(document, "product_name", None),
    }
    if any(remaining_missing.values()):
        pipeline_info["front_matter_incomplete"] = True
    else:
        pipeline_info.pop("front_matter_incomplete", None)
    pipeline_info["second_pass"] = second_pass_bucket
    document.pipeline_info = pipeline_info

    return SecondPassPatchResult(
        name=PATCH_NAME,
        applied=True,
        modifications=dict(mod_payload),
        reasons=list(dict.fromkeys(reason_tags)),
    )
