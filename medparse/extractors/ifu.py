"""Enhanced IFU extraction with post-processing hardening."""

from __future__ import annotations

import re
import functools
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from medparse.config import ExtractionConfig, get_extraction_config

from medparse.extract.utils import (
    collect_lines,
    collect_tables,
    iter_section_windows,
    load_pages,
    reference_section,
    section_text_between,
)
from medparse.ingest.models import PageData
from medparse.ifu.frontmatter import extract_front_matter
from medparse.ifu.manufacturer import detect_manufacturer
from medparse.ifu.safety import extract_safety_blocks as build_safety_blocks
from medparse.ifu.subtype import infer_ifu_subtype_from_pages
from medparse.normalize.ifu_anchors import lift_ifu_clinical_fields
from medparse.normalize.ifu_sections import clean_section_text
from medparse.normalize.page_furniture import strip_furniture
from medparse.normalize.references import gate_ifu_references, normalize_references
from medparse.normalize.software import filter_software_versions
from medparse.normalize.tables import clean_tables
from medparse.normalize.text_cleanup import clean_paragraph, deep_cleanup_fields
from medparse.pipeline.engine_select import repair_space_poor_pages
from medparse.schema.ifu import IFUDocument
from medparse.text.paragraphizer import build_paragraph_store
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

SECTION_FIELDS = {
    "indications for use": "indications_for_use",
    "intended use": "intended_use",
    "intended user": "intended_user",
    "intended patient population": "intended_patient_population",
    "contraindications": "contraindications",
    "adverse events": "adverse_events",
    "clinical risks and benefits": "clinical_risks_and_benefits",
    "clinical risks & benefits": "clinical_risks_and_benefits",
    "clinical benefits and risks": "clinical_risks_and_benefits",
}

SAFETY_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "second_pass.yaml"


@functools.lru_cache(maxsize=1)
def _load_safety_density_min_config() -> Dict[str, object]:
    if not SAFETY_CONFIG_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(SAFETY_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if isinstance(data, dict) and "second_pass" in data and isinstance(data["second_pass"], dict):
        data = data["second_pass"]
    if not isinstance(data, dict):
        return {}
    ifu_cfg = data.get("ifu")
    if not isinstance(ifu_cfg, dict):
        return {}
    density_cfg = ifu_cfg.get("safety_density_min")
    if isinstance(density_cfg, dict):
        return density_cfg
    return {}


def _as_positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def _compute_safety_expected_min(document: IFUDocument, config: ExtractionConfig) -> tuple[int, str]:
    raw_ifu_settings = getattr(config, "ifu", {})
    if isinstance(raw_ifu_settings, dict):
        ifu_settings = raw_ifu_settings
    elif hasattr(raw_ifu_settings, "to_dict"):
        ifu_settings = raw_ifu_settings.to_dict()
    else:
        ifu_settings = {}

    safety_cfg = ifu_settings.get("safety", {}) if isinstance(ifu_settings, dict) else {}
    min_blocks_cfg = safety_cfg.get("min_blocks", {}) if isinstance(safety_cfg, dict) else {}

    default_min = _as_positive_int(min_blocks_cfg.get("default"), 12)
    small_leaflet_pages_max = _as_positive_int(min_blocks_cfg.get("small_leaflet_pages_max"), 4)
    small_leaflet_min = _as_positive_int(
        min_blocks_cfg.get("small_leaflet_min"),
        max(1, default_min // 2),
    )
    vendor_overrides = min_blocks_cfg.get("vendor_overrides") if isinstance(min_blocks_cfg, dict) else {}

    density_cfg = _load_safety_density_min_config()
    if density_cfg:
        default_min = _as_positive_int(density_cfg.get("default"), default_min)
        if density_cfg.get("small_leaflet") is not None:
            small_leaflet_min = _as_positive_int(density_cfg.get("small_leaflet"), small_leaflet_min)
        if density_cfg.get("small_leaflet_pages_max") is not None:
            small_leaflet_pages_max = _as_positive_int(density_cfg.get("small_leaflet_pages_max"), small_leaflet_pages_max)
        overrides_cfg = density_cfg.get("by_manufacturer")
        if isinstance(overrides_cfg, dict):
            vendor_overrides = overrides_cfg

    manufacturer_label = (document.manufacturer or "").strip().lower()
    vendor_min = default_min
    vendor_override_applied = False
    if manufacturer_label and isinstance(vendor_overrides, dict):
        for key, value in vendor_overrides.items():
            if not isinstance(key, str):
                continue
            key_norm = key.strip().lower()
            if key_norm and key_norm in manufacturer_label:
                vendor_min = _as_positive_int(value, default_min)
                vendor_override_applied = True
                break

    page_count = getattr(document, "page_count", 0) or 0
    if page_count and page_count <= small_leaflet_pages_max:
        expected_min = small_leaflet_min
    else:
        expected_min = vendor_min

    if density_cfg:
        source = "density_config_override" if vendor_override_applied else "density_config"
    else:
        source = "vendor_override" if vendor_override_applied else "default"

    return expected_min, source
def _clamp_pages(pages: List[int], page_count: int) -> List[int]:
    if not pages:
        return []
    clamped: List[int] = []
    for value in pages:
        try:
            page_num = int(value)
        except (TypeError, ValueError):
            continue
        if page_count > 0:
            page_num = max(1, min(page_count, page_num))
        if page_num not in clamped:
            clamped.append(page_num)
    return clamped


def _set_safety_expectations(document: IFUDocument, config: ExtractionConfig) -> None:
    expected_min, source = _compute_safety_expected_min(document, config)
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
        document.pipeline_info = pipeline_info

    pipeline_info.setdefault("safety_expected_min", expected_min)
    pipeline_info.setdefault("safety_expectation_source", source)
    pipeline_info.setdefault("safety_blocks_added", pipeline_info.get("safety_blocks_added", 0))


def extract_ifu(
    pdf_path: Path,
    *,
    engine: str = "pymupdf",
    page_limit: Optional[int] = None,
    pages: Optional[List[PageData]] = None,
    config: Optional[ExtractionConfig] = None,
) -> IFUDocument:
    """Extract an IFU document with hardened normalization."""

    extraction_config = config or get_extraction_config()
    ifu_settings = getattr(extraction_config, "ifu", {}) or {}
    engine_runtime = ifu_settings.get("_engine_runtime") if isinstance(ifu_settings, dict) else {}
    pages = pages or load_pages(pdf_path, engine=engine, max_pages=page_limit)
    pages, spacing_info = repair_space_poor_pages(
        pdf_path,
        pages,
        current_engine=engine,
        settings=ifu_settings,
    )
    engine_overrides = ifu_settings.get("engine") or {}
    tables_engine = str(engine_overrides.get("tables") or "").lower()
    tables_pages = pages
    if tables_engine and tables_engine != engine:
        try:
            tables_pages = load_pages(pdf_path, engine=tables_engine, max_pages=page_limit)
        except Exception as exc:
            LOGGER.warning("Table engine '%s' failed (%s); using primary engine", tables_engine, exc)
            tables_pages = pages
    doc_subtype = infer_ifu_subtype_from_pages(pages, pdf_path)
    page_count = len(pages)
    metadata_title = pdf_path.stem.replace("_", " ").strip()
    manufacturer_detection = detect_manufacturer(pages, metadata_title=metadata_title or None, pdf_path=pdf_path)
    manufacturer_hint = manufacturer_detection.get("name") if manufacturer_detection else None
    manufacturer_source = manufacturer_detection.get("source") if manufacturer_detection else None
    meta = extract_front_matter(
        pages,
        metadata_title=metadata_title or None,
        manufacturer_hint=manufacturer_hint,
        manufacturer_source=manufacturer_source,
    )
    provenance = {}
    if isinstance(meta, dict) and "_provenance" in meta:
        provenance = dict(meta.pop("_provenance", {}) or {})

    # Strip page furniture (headers/footers) before processing
    lines_by_page = [page.lines for page in pages]
    clean_lines_by_page = strip_furniture(lines_by_page, threshold=0.6)

    # Update pages with cleaned lines and rebuild text
    for page, clean_lines in zip(pages, clean_lines_by_page):
        page.lines = clean_lines
        page.text = '\n'.join(clean_lines)

    lines = collect_lines(pages)
    pages_text = [page.text for page in pages]

    section_text: dict[str, str] = {}
    for heading, next_heading in iter_section_windows(pages):
        text, _evidence, _ = section_text_between(pages, heading, next_heading)
        section_text[heading.title.lower()] = text

    manufacturer_for_safety = None
    if isinstance(meta, dict):
        manufacturer_for_safety = meta.get("manufacturer")
    if not manufacturer_for_safety:
        manufacturer_for_safety = manufacturer_hint

    safety_blocks = build_safety_blocks(pages, manufacturer=manufacturer_for_safety)

    references = normalize_references(
        reference_section(lines),
        mode="ifu",
        headings=[heading.title for page in pages for heading in page.headings],
    )

    doc_kwargs: dict[str, object] = {
        "doc_type": "ifu",
        "doc_subtype": doc_subtype,
        "source_file": str(pdf_path),
        "page_count": page_count,
        "manufacturer": None,
        "product_name": None,
        "part_number": None,
        "revision": None,
        "publication_date": None,
        "model": None,
        "software_versions": [],
        "tables": collect_tables(tables_pages),
        "references": references,
        "safety_blocks": safety_blocks,
    }

    skip_clinical_fields = isinstance(doc_subtype, str) and doc_subtype in {"catalog", "installation_guide", "tech_manual"}
    for key, field in SECTION_FIELDS.items():
        if skip_clinical_fields and field in {
            "indications_for_use",
            "intended_use",
            "intended_user",
            "intended_patient_population",
            "contraindications",
            "adverse_events",
            "clinical_risks_and_benefits",
        }:
            continue
        if key in section_text:
            doc_kwargs[field] = section_text[key]

    for fld in (
        "indications_for_use",
        "intended_use",
        "intended_user",
        "intended_patient_population",
    ):
        val = doc_kwargs.get(fld)
        if isinstance(val, str):
            doc_kwargs[fld] = clean_section_text(val)

    toc_guard_info = None
    if not skip_clinical_fields:
        toc_guard_info = lift_ifu_clinical_fields(
            pages,
            doc_kwargs,
            settings=ifu_settings,
            manufacturer=meta.get("manufacturer") if isinstance(meta, dict) else None,
        )
        if toc_guard_info:
            doc_kwargs["_toc_guard_info"] = toc_guard_info

    # Collect software versions from Equipment/Software Version section
    raw_software: List[str] = []
    for page_idx, page_text in enumerate(pages_text[:10]):  # Check first 10 pages
        # Look for Equipment and Software Version section
        if "equipment" in page_text.lower() and "software" in page_text.lower():
            # Extract lines that mention Ion OS or PlanPoint
            for line in page_text.splitlines():
                if "ion" in line.lower() and "os" in line.lower():
                    raw_software.append(line.strip())
                elif "planpoint" in line.lower():
                    raw_software.append(line.strip())

    for key in (
        "part_number",
        "revision",
        "publication_date",
        "model",
        "manufacturer",
        "product_name",
    ):
        value = meta.get(key)
        if value:
            doc_kwargs[key] = value

    if manufacturer_hint and not doc_kwargs.get("manufacturer"):
        doc_kwargs["manufacturer"] = manufacturer_hint

    if not doc_kwargs.get("revision"):
        doc_id_match = re.search(r"(D\d{5,6})", pdf_path.stem, re.IGNORECASE)
        if doc_id_match:
            doc_kwargs["revision"] = doc_id_match.group(1).upper()

    # Apply text cleanup to narrative fields
    for fld in ("product_name", "indications_for_use", "intended_use",
                "intended_user", "intended_patient_population"):
        val = doc_kwargs.get(fld)
        if isinstance(val, str) and val:
            doc_kwargs[fld] = clean_paragraph(val)

    for fld in ("contraindications", "adverse_events"):
        val = doc_kwargs.get(fld)
        if isinstance(val, list):
            cleaned_list = []
            for item in val:
                if isinstance(item, str) and item.strip():
                    cleaned_list.append(clean_paragraph(item))
            doc_kwargs[fld] = cleaned_list

    if extraction_config.is_enriched():
        deep_cleanup_fields(doc_kwargs)
        doc_kwargs["tables"] = clean_tables(doc_kwargs.get("tables", []))
        doc_kwargs["software_versions"] = filter_software_versions(raw_software)
        gate_ifu_references(doc_kwargs, pages_text)
    else:
        doc_kwargs["tables"] = doc_kwargs.get("tables", [])
        doc_kwargs["software_versions"] = raw_software

    # Ensure list defaults
    for key in ("contraindications", "adverse_events"):
        if not doc_kwargs.get(key):
            doc_kwargs[key] = []

    anchor_errors = doc_kwargs.pop("_anchor_errors", [])
    anchor_error_fields = doc_kwargs.pop("_anchor_error_fields", [])
    anchor_spans = doc_kwargs.pop("_anchor_spans", {})
    toc_guard_info = doc_kwargs.pop("_toc_guard_info", None)

    document = IFUDocument.model_validate(doc_kwargs)
    document.pipeline_info["safety_blocks_found"] = len(safety_blocks)

    front_meta_payload: Dict[str, str] = {}
    if isinstance(meta, dict) and meta.get("product_name_source"):
        product_source = str(meta.get("product_name_source"))
        if product_source:
            front_meta_payload["product_name_source"] = product_source
    for field_name, source_name in provenance.items():
        key_name = f"{field_name}_source"
        if key_name not in front_meta_payload and source_name:
            front_meta_payload[key_name] = str(source_name)
    if manufacturer_detection:
        document.pipeline_info["manufacturer_detection"] = manufacturer_detection
        detection_confidence = manufacturer_detection.get("confidence")
        detection_source = manufacturer_detection.get("source")
        if detection_confidence and "manufacturer_detection_confidence" not in front_meta_payload:
            front_meta_payload["manufacturer_detection_confidence"] = str(detection_confidence)
        if detection_source and "manufacturer_detection_source" not in front_meta_payload:
            front_meta_payload["manufacturer_detection_source"] = str(detection_source)
    if front_meta_payload:
        front_meta = document.pipeline_info.setdefault("front_matter_meta", {})
        if isinstance(front_meta, dict):
            front_meta.update(front_meta_payload)

    if references:
        document.pipeline_info["references_detected"] = len(references)
    if isinstance(engine_runtime, dict):
        if engine_runtime.get("long_doc_fast_path"):
            document.pipeline_info["long_doc_fast_path"] = True
            if engine_runtime.get("long_doc_page_threshold") is not None:
                document.pipeline_info["long_doc_page_threshold"] = engine_runtime.get("long_doc_page_threshold")
            document.pipeline_info["long_doc_page_count"] = page_count
            document.pipeline_info["long_doc_fast_engine"] = engine_runtime.get("fast_long_engine")
        else:
            document.pipeline_info.setdefault("long_doc_fast_path", False)
    if anchor_errors:
        document.pipeline_info["anchor_bleed_errors"] = anchor_errors
        document.pipeline_info["anchor_bleed_fields"] = anchor_error_fields
    if anchor_spans:
        document.pipeline_info["anchor_spans"] = anchor_spans
    if toc_guard_info:
        toc_guard_info = dict(toc_guard_info)
        document.pipeline_info["toc_guard_applied"] = bool(toc_guard_info.get("enabled", False))
        dropped_raw = toc_guard_info.get("pages_dropped", [])
        clamped_pages: List[int] = _clamp_pages(dropped_raw if isinstance(dropped_raw, list) else [], page_count)
        toc_guard_info["pages_dropped"] = clamped_pages
        document.pipeline_info["toc_guard_pages_dropped"] = clamped_pages
        document.pipeline_info["toc_guard_pages_dropped_count"] = len(clamped_pages)
        document.pipeline_info["toc_guard"] = toc_guard_info
        if "anchors_bleed" in toc_guard_info:
            document.pipeline_info["anchors_bleed"] = toc_guard_info["anchors_bleed"]
        if "small_ifu_threshold" in toc_guard_info:
            document.pipeline_info["small_ifu_threshold"] = toc_guard_info.get("small_ifu_threshold")
        if "small_ifu_fallback_applied" in toc_guard_info:
            document.pipeline_info["small_ifu_fallback_applied"] = bool(
                toc_guard_info.get("small_ifu_fallback_applied")
            )
        if "manufacturer_rules" in toc_guard_info:
            document.pipeline_info["manufacturer_rules"] = toc_guard_info["manufacturer_rules"]
    if spacing_info:
        document.pipeline_info["text_repair_applied"] = bool(spacing_info.get("text_repair_applied"))
        engine_map = spacing_info.get("engine_used_per_page")
        if isinstance(engine_map, dict):
            document.pipeline_info["engine_used_per_page"] = engine_map
        spacing_metrics = {
            "space_ratio_before": spacing_info.get("space_ratio_before"),
            "space_ratio_after": spacing_info.get("space_ratio_after"),
            "avg_token_length_before": spacing_info.get("avg_token_length_before"),
            "avg_token_length_after": spacing_info.get("avg_token_length_after"),
            "repair_strategy": spacing_info.get("repair_strategy"),
        }
        document.pipeline_info["spacing_metrics"] = spacing_metrics

    paragraph_store, dedup_applied = build_paragraph_store(
        document.doc_id,
        pages,
        join_hyphens=True,
        drop_headers=True,
        drop_footers=True,
    )
    document.paragraph_store = paragraph_store
    if dedup_applied:
        document.pipeline_info["paragraph_dedup_applied"] = True
    else:
        document.pipeline_info.setdefault("paragraph_dedup_applied", False)
    _set_safety_expectations(document, extraction_config)
    return document
__all__ = ["extract_ifu"]
