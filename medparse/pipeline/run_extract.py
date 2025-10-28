"""High-level extraction runner with completeness guards and caching."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Type

import hashlib
import yaml

from medparse.config import ExtractionConfig, ExtractionProfile
from medparse.extractors.article import extract_article
from medparse.extractors.guideline import extract_guideline
from medparse.extractors.ifu import extract_ifu
from medparse.extractors.textbook import extract_textbook_chapter
from medparse.extract.utils import load_pages
from medparse.schema.article import ArticleDocument
from medparse.schema.common import BaseDocument, EvidenceSpan, SizeGuards
from medparse.schema.ifu import IFUDocument
from medparse.schema.textbook import TextbookChapterDocument
from medparse.utils.cache import compute_cache_key, load_cache_entry, store_cache_entry
from medparse.utils.evidence_dedup import EvidenceBank
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

DocType = Literal["article", "guideline", "ifu", "textbook"]
SummaryLength = Literal["short", "medium", "long"]

EXTRACTOR_MAP = {
    "article": extract_article,
    "guideline": extract_guideline,
    "ifu": extract_ifu,
    "textbook": extract_textbook_chapter,
}

MODEL_MAP: Dict[str, Type[BaseDocument]] = {
    "article": ArticleDocument,
    "guideline": ArticleDocument,
    "ifu": IFUDocument,
    "textbook": TextbookChapterDocument,
}


@dataclass
class PipelineConfig:
    doc_type: DocType
    profile: ExtractionProfile = ExtractionProfile.ENRICHED
    engines: List[str] = field(default_factory=lambda: ["fitz", "pdfplumber"])
    min_chars: int = 0
    min_pages_ratio: float = 0
    ocr: bool = False
    enable_umls: Optional[bool] = None
    enable_relations: Optional[bool] = None
    enable_guideline_norms: Optional[bool] = None
    max_preview_pages: Optional[int] = None
    thresholds: Dict[str, Any] = field(default_factory=dict)
    ocr_settings: Dict[str, Any] = field(default_factory=dict)
    emit: Dict[str, Any] = field(default_factory=dict)
    size_guards: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_path(cls, path: Path) -> "PipelineConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        profile_value = data.get("profile", ExtractionProfile.ENRICHED.value)
        try:
            profile = ExtractionProfile(profile_value)
        except ValueError:
            profile = ExtractionProfile.ENRICHED

        engines = data.get("engines") or ["fitz", "pdfplumber"]
        thresholds = data.get("thresholds") or {}
        emit_settings = data.get("emit") or {}
        ocr_config = data.get("ocr", False)
        if isinstance(ocr_config, dict):
            ocr_enable = bool(ocr_config.get("enable", False))
            ocr_settings = {k: v for k, v in ocr_config.items()}
        else:
            ocr_enable = bool(ocr_config)
            ocr_settings = {"enable": ocr_enable}

        size_guards_config = data.get("size_guards") or {}

        return cls(
            doc_type=data["doc_type"],
            profile=profile,
            engines=[engine.lower() for engine in engines],
            min_chars=int(data.get("min_chars", 0)),
            min_pages_ratio=float(data.get("min_pages_ratio", 0.0)),
            ocr=ocr_enable,
            enable_umls=data.get("umls"),
            enable_relations=data.get("relations"),
            enable_guideline_norms=data.get("guideline_enrichment"),
            max_preview_pages=data.get("max_preview_pages"),
            thresholds=thresholds,
            ocr_settings=ocr_settings,
            emit=emit_settings,
            size_guards=size_guards_config,
        )

    def to_extraction_config(self, *, use_cache: bool) -> ExtractionConfig:
        kwargs = {
            "profile": self.profile,
            "use_cache": use_cache,
            "thresholds": self.thresholds,
        }
        if self.profile == ExtractionProfile.FAST_RAW:
            kwargs.update(
                {
                    "enable_umls": False,
                    "enable_relations": False,
                    "enable_guideline_norms": False,
                    "enable_validators": False,
                }
            )
        else:
            kwargs.update(
                {
                    "enable_umls": True,
                    "enable_relations": True,
                    "enable_guideline_norms": True,
                    "enable_validators": True,
                }
            )
        emit_settings = self.emit or {}
        relation_window = emit_settings.get("relation_window")
        if isinstance(relation_window, int) and relation_window > 0:
            kwargs["relation_window"] = relation_window
        max_entities = emit_settings.get("max_entities")
        if isinstance(max_entities, int) and max_entities > 0:
            kwargs["max_entities"] = max_entities
        max_relations = emit_settings.get("max_relations")
        if isinstance(max_relations, int) and max_relations > 0:
            kwargs["max_relations"] = max_relations
        return ExtractionConfig(**kwargs)

    def resolved_engines(self, *, force_deep: bool = False) -> List[str]:
        """Return normalized engine list honouring deep-run requirements."""

        engines = [engine.lower() for engine in (self.engines or [])]
        if not engines:
            engines = ["pymupdf", "pdfplumber"]

        normalized: List[str] = []
        for engine in engines:
            if engine in {"fitz", "pymupdf", "pdf"}:
                normalized.append("pymupdf")
            elif engine in {"pdfplumber", "plumber"}:
                normalized.append("pdfplumber")
            else:
                normalized.append(engine)

        # Ensure deterministic order and deduplicate while preserving input order
        seen: set[str] = set()
        ordered = []
        for engine in normalized:
            if engine not in seen:
                seen.add(engine)
                ordered.append(engine)

        if force_deep:
            # Deep runs must exercise both text engines
            for required in ("pymupdf", "pdfplumber"):
                if required not in seen:
                    ordered.append(required)
                    seen.add(required)
        return ordered


@dataclass
class PipelineOutcome:
    pdf_path: Path
    config: PipelineConfig
    success: bool
    document: Optional[BaseDocument]
    metrics: Dict[str, float | int | bool]
    engine: str
    mode: str
    cache_used: bool = False
    failure_reason: Optional[str] = None
    ocr_pages: List[int] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    emit_settings: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, object]:
        if self.success and self.document is not None:
            payload = self.document.model_dump(mode="json", exclude_none=True)

            # Simplify evidence_bank to just text strings for better usability
            if "evidence_bank" in payload and isinstance(payload["evidence_bank"], dict):
                simplified_bank = {}
                for hash_id, evidence_data in payload["evidence_bank"].items():
                    if isinstance(evidence_data, dict) and "text" in evidence_data:
                        simplified_bank[hash_id] = evidence_data["text"]
                    elif isinstance(evidence_data, str):
                        simplified_bank[hash_id] = evidence_data
                payload["evidence_bank"] = simplified_bank

            payload["_metrics"] = self.metrics
            payload["_engine"] = self.engine
            payload["_mode"] = self.mode
            payload["_cache_used"] = self.cache_used
            timestamp = getattr(self.document, "extraction_timestamp", None)
            if isinstance(timestamp, datetime):
                timestamp_value = timestamp.isoformat()
            else:
                timestamp_value = timestamp
            pipeline_metadata = {
                "profile": self.config.profile.value,
                "engines_requested": self.metadata.get(
                    "engines_requested",
                    self.config.resolved_engines(),
                ),
                "engine_used": self.engine,
                "mode": self.mode,
                "cache_used": self.cache_used,
                "ocr_used_pages": self.ocr_pages,
                "coverage_ratio": self.metrics.get("coverage_ratio"),
                "page_count": self.metrics.get("page_count"),
                "timestamp": timestamp_value,
                "version": getattr(self.document, "extraction_version", None),
                "warnings": list(self.warnings),
                "emit": self.emit_settings,
            }
            doc_pipeline_info = getattr(self.document, "pipeline_info", {})
            if isinstance(doc_pipeline_info, dict):
                for key, value in doc_pipeline_info.items():
                    pipeline_metadata.setdefault(key, value)
            pipeline_metadata.update({k: v for k, v in self.metadata.items() if k not in pipeline_metadata})
            payload["_pipeline_metadata"] = pipeline_metadata
            return payload
        return {
            "doc_type": self.config.doc_type,
            "source_file": str(self.pdf_path),
            "failure_reason": self.failure_reason or "extraction_failed",
            "metrics": self.metrics,
            "engine": self.engine,
            "mode": self.mode,
        }


def _build_evidence_bank(document: BaseDocument, size_guards: SizeGuards) -> EvidenceBank:
    """Build evidence bank from extracted document, deduplicating evidence spans.

    Args:
        document: Extracted document with evidence spans
        size_guards: Size limits configuration

    Returns:
        EvidenceBank with deduplicated evidence
    """
    bank = EvidenceBank(size_guards=size_guards)

    # Process recommendations
    if hasattr(document, "recommendations"):
        for rec in getattr(document, "recommendations") or []:
            evidence = getattr(rec, "evidence", None)
            if isinstance(evidence, list):
                refs = bank.add_evidence_list(evidence)
                if refs:
                    setattr(rec, "evidence_refs", refs)
                    setattr(rec, "evidence", None)  # Clear original
            elif isinstance(evidence, EvidenceSpan):
                ref = bank.add_evidence(evidence)
                if ref:
                    setattr(rec, "evidence_refs", [ref])
                    setattr(rec, "evidence", None)  # Clear original

    # Process outcomes
    if hasattr(document, "outcomes"):
        for outcome in getattr(document, "outcomes") or []:
            evidence = getattr(outcome, "evidence", None)
            if isinstance(evidence, list):
                refs = bank.add_evidence_list(evidence)
                if refs:
                    setattr(outcome, "evidence_refs", refs)
                    setattr(outcome, "evidence", None)
            elif isinstance(evidence, EvidenceSpan):
                ref = bank.add_evidence(evidence)
                if ref:
                    setattr(outcome, "evidence_refs", [ref])
                    setattr(outcome, "evidence", None)

    # Process diagnostic_yield
    if hasattr(document, "diagnostic_yield"):
        diag = getattr(document, "diagnostic_yield")
        if diag:
            evidence = getattr(diag, "evidence", None)
            if isinstance(evidence, EvidenceSpan):
                ref = bank.add_evidence(evidence)
                if ref:
                    setattr(diag, "evidence_refs", [ref])
                    setattr(diag, "evidence", None)

    # Process relations
    if hasattr(document, "relations"):
        for relation in getattr(document, "relations") or []:
            evidence = getattr(relation, "evidence", None)
            if isinstance(evidence, EvidenceSpan):
                ref = bank.add_evidence(evidence)
                if ref:
                    setattr(relation, "evidence_refs", [ref])
                    setattr(relation, "evidence", None)
            elif isinstance(evidence, list):
                refs = bank.add_evidence_list(evidence)
                if refs:
                    setattr(relation, "evidence_refs", refs)
                    setattr(relation, "evidence", None)

    # Process figures
    if hasattr(document, "figures"):
        for figure in getattr(document, "figures") or []:
            evidence = getattr(figure, "evidence", None)
            if isinstance(evidence, EvidenceSpan):
                ref = bank.add_evidence(evidence)
                if ref:
                    setattr(figure, "evidence_refs", [ref])
                    setattr(figure, "evidence", None)

    return bank


def run_extract(
    pdf_path: Path,
    config_path: Path,
    *,
    use_cache: bool = True,
    force_deep: bool = False,
    max_pages: Optional[int] = None,
    summary_length: Optional[SummaryLength] = None,
    profile_override: Optional[str] = None,
) -> PipelineOutcome:
    """Run extraction with completeness checks and caching."""

    config = PipelineConfig.from_path(config_path)
    if profile_override:
        try:
            config.profile = ExtractionProfile(profile_override)
        except ValueError:
            LOGGER.warning("Invalid profile override '%s', keeping %s", profile_override, config.profile.value)

    if max_pages is not None:
        config.max_preview_pages = max_pages
    elif force_deep:
        config.max_preview_pages = None

    if config.doc_type not in EXTRACTOR_MAP:
        raise ValueError(f"Unsupported doc_type '{config.doc_type}' in {config_path}")

    extractor = EXTRACTOR_MAP[config.doc_type]
    engines = config.resolved_engines(force_deep=force_deep)
    ocr_enabled = bool(config.ocr_settings.get("enable", config.ocr))
    pdf_bytes = pdf_path.read_bytes()
    total_pages = _determine_total_pages(pdf_path)

    threshold_signature = json.dumps(config.thresholds, sort_keys=True)
    cache_key = compute_cache_key(
        pdf_bytes,
        total_pages,
        [*engines, threshold_signature],
        config.profile.value,
    )
    cache_enabled = use_cache and not force_deep
    extraction_config = config.to_extraction_config(use_cache=cache_enabled)

    cached_entry = load_cache_entry(cache_key) if cache_enabled else None
    if cached_entry:
        cached_engine = cached_entry.get("engine")
        cached_profile = cached_entry.get("profile")
        if cached_profile == extraction_config.profile.value:
            document = _hydrate_document(config.doc_type, cached_entry)
            metrics = cached_entry.get("metrics", {})
            LOGGER.info(
                "Cache hit: doc_type=%s engine=%s page_count=%s",
                config.doc_type,
                cached_engine,
                metrics.get("page_count"),
            )
            return PipelineOutcome(
                pdf_path=pdf_path,
                config=config,
                success=True,
                document=document,
                metrics=metrics,
                engine=cached_engine or engines[0],
                mode="cache",
                cache_used=True,
                warnings=cached_entry.get("warnings", []),
                metadata=cached_entry.get("metadata", {}),
                emit_settings=cached_entry.get("emit", {}),
            )

    last_metrics: Dict[str, float | int] = {}
    last_engine = engines[0]
    last_ocr_pages: List[int] = []
    failure_reason: Optional[str] = None
    last_metadata: Dict[str, Any] = {"engines_requested": engines}

    for idx, engine in enumerate(engines):
        LOGGER.info(
            "Starting extraction: doc_type=%s engine=%s profile=%s",
            config.doc_type,
            engine,
            extraction_config.profile.value,
        )

        start = time.time()
        pages = load_pages(
            pdf_path,
            engine=engine,
            max_pages=None if force_deep else config.max_preview_pages,
            ocr=ocr_enabled,
        )
        ocr_pages = [page.number for page in pages if getattr(page, "ocr_applied", False)]
        document = extractor(
            pdf_path,
            engine=engine,
            page_limit=None if force_deep else config.max_preview_pages,
            pages=pages,
            config=extraction_config,
        )
        duration = time.time() - start

        metrics = _compute_metrics(pages, total_pages, duration)
        metrics.update(_document_metrics(document))

        emit_warnings = _apply_emit_constraints(document, config.emit)

        # Build evidence bank for deduplication and size reduction
        size_guards = SizeGuards(**(config.size_guards or {}))
        evidence_bank = _build_evidence_bank(document, size_guards)

        # Populate document with evidence bank
        document.evidence_bank = evidence_bank.get_bank()

        # Add truncation notice if any truncation occurred
        truncation_notice = evidence_bank.get_truncation_notice()
        if truncation_notice:
            document.truncation_notice = truncation_notice

        # Log deduplication stats
        stats = evidence_bank.get_stats()
        LOGGER.info(
            "Evidence deduplication: total=%d deduplicated=%d truncated=%d bank_size=%d",
            stats["total_added"],
            stats["deduplicated"],
            stats["truncated"],
            len(document.evidence_bank),
        )

        LOGGER.info(
            "Completed extraction: doc_type=%s engine=%s duration=%.2fs chars=%d coverage=%.2f",
            config.doc_type,
            engine,
            duration,
            metrics.get("extracted_chars", 0),
            metrics.get("unique_pages_ratio", 0.0),
        )

        meets_thresholds, threshold_warnings = _meets_thresholds(config, metrics, document=document)
        combined_warnings = list(dict.fromkeys(threshold_warnings + emit_warnings))
        if meets_thresholds:
            if cache_enabled and idx == 0:
                _store_success_in_cache(
                    cache_key,
                    config.doc_type,
                    document,
                    metrics,
                    engine,
                    extraction_config.profile.value,
                    combined_warnings,
                    {"engines_requested": engines},
                    config.emit,
                )
            return PipelineOutcome(
                pdf_path=pdf_path,
                config=config,
                success=True,
                document=document,
                metrics=metrics,
                engine=engine,
                mode="full",
                cache_used=False,
                ocr_pages=ocr_pages,
                warnings=combined_warnings,
                metadata={"engines_requested": engines},
                emit_settings=config.emit,
            )

        last_metrics = metrics
        last_engine = engine
        last_ocr_pages = ocr_pages
        last_metadata = {"engines_requested": engines, "threshold_warnings": combined_warnings}
        failure_reason = (
            "Extraction did not satisfy completeness thresholds"
        )

        LOGGER.warning(
            "Thresholds not met with engine=%s (chars=%d ratio=%.2f)",
            engine,
            metrics.get("extracted_chars", 0),
            metrics.get("unique_pages_ratio", 0.0),
        )

    return PipelineOutcome(
        pdf_path=pdf_path,
        config=config,
        success=False,
        document=None,
        metrics=last_metrics,
        engine=last_engine,
        mode="full",
        cache_used=False,
        failure_reason=failure_reason,
        ocr_pages=last_ocr_pages,
        warnings=last_metadata.get("threshold_warnings", []),
        metadata=last_metadata,
        emit_settings=config.emit,
    )


def _compute_metrics(pages, total_pages: int, duration: float) -> Dict[str, float]:
    unique_pages = len({page.number for page in pages})
    extracted_chars = sum(len(page.text or "") for page in pages)
    ratio = min(1.0, unique_pages / total_pages) if total_pages else 0.0
    return {
        "page_count": total_pages,
        "unique_pages_seen": unique_pages,
        "unique_pages_ratio": ratio,
        "extracted_chars": extracted_chars,
        "duration_s": duration,
        "coverage_ratio": ratio,
    }


def _meets_thresholds(
    config: PipelineConfig,
    metrics: Dict[str, float],
    *,
    document: Optional[BaseDocument] = None,
) -> Tuple[bool, List[str]]:
    """Evaluate extraction completeness thresholds returning (passes, warnings)."""

    warnings: List[str] = []

    page_count = int(metrics.get("page_count", 0) or 0)
    coverage = float(
        metrics.get("coverage_ratio")
        or metrics.get("unique_pages_ratio")
        or 0.0
    )
    extracted_chars = int(metrics.get("extracted_chars", 0) or 0)

    if page_count <= 0:
        return False, warnings

    # Resolve active threshold block
    thresholds = config.thresholds or {}
    if not isinstance(thresholds, dict):
        thresholds = {}
    active_thresholds: Dict[str, Any] = {}
    doc_subtype = getattr(document, "doc_subtype", None) if document else None
    if config.doc_type == "article" and isinstance(doc_subtype, str):
        candidate = thresholds.get(doc_subtype)
        if isinstance(candidate, dict):
            active_thresholds = candidate
    if config.doc_type == "ifu" and not active_thresholds:
        manufacturer = getattr(document, "manufacturer", None) if document else None
        if isinstance(manufacturer, str):
            manufacturer_lower = manufacturer.strip().lower()
            for key, value in thresholds.items():
                if not isinstance(value, dict):
                    continue
                if key.lower() == manufacturer_lower:
                    active_thresholds = value
                    break
        if not active_thresholds and isinstance(thresholds.get("default"), dict):
            active_thresholds = thresholds["default"]
    else:
        if not active_thresholds and isinstance(thresholds, dict):
            active_thresholds = thresholds

    min_coverage = (
        active_thresholds.get("min_coverage_ratio")
        if isinstance(active_thresholds, dict)
        else None
    )
    if min_coverage is None:
        min_coverage = config.min_pages_ratio or thresholds.get("min_pages_ratio") if isinstance(thresholds, dict) else None

    min_chars_abs = None
    if isinstance(active_thresholds, dict):
        min_chars_abs = active_thresholds.get("min_chars") or active_thresholds.get("min_chars_abs")
    if min_chars_abs is None and isinstance(thresholds, dict):
        min_chars_abs = thresholds.get("min_chars") or thresholds.get("min_chars_abs")
    if min_chars_abs is None:
        min_chars_abs = config.min_chars

    min_chars_per_page = None
    if isinstance(active_thresholds, dict):
        min_chars_per_page = active_thresholds.get("min_chars_per_page")
    if min_chars_per_page is None and isinstance(thresholds, dict):
        min_chars_per_page = thresholds.get("min_chars_per_page")

    # Short-document override
    if page_count < 10 and coverage >= 0.999:
        if min_chars_abs and extracted_chars < min_chars_abs:
            warnings.append("coverage_ok_chars_low")
        return True, warnings

    if min_coverage is not None and coverage < float(min_coverage):
        return False, warnings

    if min_chars_per_page and page_count:
        required_chars = int(min_chars_per_page) * max(page_count, 1)
        if extracted_chars < required_chars:
            return False, warnings

    if min_chars_abs and extracted_chars < int(min_chars_abs):
        if doc_subtype == "guideline" and document is not None:
            recs = getattr(document, "recommendations", []) or []
            min_recs = active_thresholds.get("min_recommendations", 0) if isinstance(active_thresholds, dict) else 0
            if min_recs and len(recs) >= int(min_recs):
                warnings.append("guideline_chars_below_min")
                return True, warnings
        return False, warnings

    return True, warnings


def _document_metrics(document: BaseDocument) -> Dict[str, int | float | bool]:
    payload: Dict[str, int | float | bool] = {}

    if hasattr(document, "sections"):
        sections = getattr(document, "sections") or {}
        payload["sections_count"] = len(sections)

    if hasattr(document, "doc_subtype"):
        payload["doc_subtype"] = getattr(document, "doc_subtype")

    if hasattr(document, "tables"):
        tables = getattr(document, "tables") or []
        payload["tables_kept"] = len(tables)

    if hasattr(document, "recommendations"):
        recs = getattr(document, "recommendations") or []
        payload["recommendations_count"] = len(recs)

    if hasattr(document, "diagnostic_yield"):
        payload["diagnostic_yield_present"] = bool(getattr(document, "diagnostic_yield"))
        diag = getattr(document, "diagnostic_yield")
        if diag is not None and hasattr(diag, "strict"):
            payload["diagnostic_yield_strict"] = bool(getattr(diag, "strict"))

    if hasattr(document, "umls_entities"):
        entities = getattr(document, "umls_entities") or []
        payload["umls_entities"] = len(entities)

    if hasattr(document, "relations"):
        relations = getattr(document, "relations") or []
        payload["relations_count"] = len(relations)

    return payload


def _hydrate_document(doc_type: str, cached_data: Dict[str, object]) -> BaseDocument:
    model_cls = MODEL_MAP.get(doc_type)
    if not model_cls:
        raise ValueError(f"Unsupported doc_type '{doc_type}' in cache entry.")
    document_payload = cached_data.get("document") or {}
    return model_cls.model_validate(document_payload)


def _apply_emit_constraints(document: BaseDocument, emit: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    if not document or not emit:
        return warnings

    def _coerce_positive_int(value: object) -> Optional[int]:
        try:
            number = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    evidence_limit = _coerce_positive_int(emit.get("evidence_max_chars")) or 0
    table_cell_limit = _coerce_positive_int(emit.get("table_cell_max_chars")) or 0
    max_tables = _coerce_positive_int(emit.get("max_tables"))
    table_sample_rows = _coerce_positive_int(emit.get("table_sample_rows")) or 20
    tables_mode = str(emit.get("tables_mode", "verbatim") or "verbatim").lower()
    max_entities = _coerce_positive_int(emit.get("max_entities"))
    max_relations = _coerce_positive_int(emit.get("max_relations"))
    keep_evidence_bank = bool(emit.get("keep_evidence_bank", True))
    paragraph_dedupe = bool(emit.get("paragraph_dedupe", False))

    def truncate_text(value: Optional[str], limit: int) -> Optional[str]:
        if not value or limit <= 0:
            return value
        if len(value) <= limit:
            return value
        warnings.append(f"truncated_text_{limit}")
        return value[:limit].rstrip() + "…"

    def clamp_evidence(span: Optional[EvidenceSpan], limit: int) -> None:
        if not span or limit <= 0 or not span.text:
            return
        if len(span.text) > limit:
            span.text = span.text[:limit].rstrip() + "…"
            span.truncated = True  # type: ignore[attr-defined]

    if evidence_limit > 0:
        for attr in ("recommendations", "outcomes", "figures"):
            items = getattr(document, attr, None)
            if not items:
                continue
            for item in items:
                span = getattr(item, "evidence", None)
                if isinstance(span, EvidenceSpan):
                    clamp_evidence(span, evidence_limit)

        diag = getattr(document, "diagnostic_yield", None)
        if diag and isinstance(getattr(diag, "evidence", None), EvidenceSpan):
            clamp_evidence(diag.evidence, evidence_limit)

        relations = getattr(document, "relations", None)
        if relations:
            for relation in relations:
                evidence = getattr(relation, "evidence", None)
                if isinstance(evidence, EvidenceSpan):
                    clamp_evidence(evidence, evidence_limit)
                elif isinstance(evidence, str) and len(evidence) > evidence_limit:
                    setattr(relation, "evidence", truncate_text(evidence, evidence_limit))

    if hasattr(document, "tables"):
        tables = getattr(document, "tables") or []
        cleaned_tables = []
        seen_rows: set[tuple] = set()
        for table in tables:
            headers = getattr(table, "headers", [])
            rows = getattr(table, "rows", [])
            truncated = False
            cleaned_rows = []
            for row in rows:
                cleaned_row = []
                for cell in row:
                    if isinstance(cell, str) and table_cell_limit > 0 and len(cell) > table_cell_limit:
                        cell = cell[:table_cell_limit].rstrip() + "…"
                        truncated = True
                    cleaned_row.append(cell)
                row_key = tuple(cleaned_row)
                if row_key in seen_rows:
                    continue
                seen_rows.add(row_key)
                cleaned_rows.append(cleaned_row)
            if tables_mode == "compact" and table_sample_rows and len(cleaned_rows) > table_sample_rows:
                setattr(table, "rows_truncated", True)
                cleaned_rows = cleaned_rows[:table_sample_rows]
            setattr(table, "rows", cleaned_rows)
            if truncated:
                setattr(table, "truncated_cells", True)
            cleaned_tables.append(table)

        if isinstance(max_tables, int) and max_tables >= 0 and len(cleaned_tables) > max_tables:
            warnings.append("table_limit_exceeded")
            cleaned_tables = cleaned_tables[:max_tables]
        setattr(document, "tables", cleaned_tables)

    entities = getattr(document, "umls_entities", None)
    if entities and max_entities and len(entities) > max_entities:
        try:
            sorted_entities = sorted(
                entities,
                key=lambda item: (
                    -float(getattr(item, "confidence", 0.0) or 0.0),
                    getattr(item, "page", 10**6),
                ),
            )
        except Exception:
            sorted_entities = list(entities)
        setattr(document, "umls_entities", sorted_entities[:max_entities])
        warnings.append("umls_entities_truncated")

    relations = getattr(document, "relations", None)
    if relations and max_relations and len(relations) > max_relations:
        try:
            sorted_relations = sorted(
                relations,
                key=lambda item: (
                    getattr(item, "attributes", {}).get("confidence", 0.0) if hasattr(item, "attributes") else 0.0,
                    getattr(item, "attributes", {}).get("page", 10**6) if hasattr(item, "attributes") else 10**6,
                ),
                reverse=True,
            )
        except Exception:
            sorted_relations = list(relations)
        setattr(document, "relations", sorted_relations[:max_relations])
        warnings.append("relations_truncated")

    if not keep_evidence_bank:
        setattr(document, "evidence_bank", {})

    if paragraph_dedupe and hasattr(document, "sections"):
        paragraph_bank: Dict[str, str] = {}
        section_refs: Dict[str, List[str]] = {}
        sections = getattr(document, "sections", {}) or {}
        for name, text in sections.items():
            if not isinstance(text, str):
                continue
            paragraphs = [para.strip() for para in text.split("\n\n") if para.strip()]
            refs: List[str] = []
            for paragraph in paragraphs:
                normalized = " ".join(paragraph.split())
                if not normalized:
                    continue
                hash_id = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
                if hash_id not in paragraph_bank:
                    paragraph_bank[hash_id] = paragraph
                refs.append(hash_id)
            if refs:
                section_refs[name] = refs
        if paragraph_bank:
            document.pipeline_info.setdefault("paragraph_bank", paragraph_bank)
            document.pipeline_info.setdefault("section_paragraph_refs", section_refs)

    return warnings


def _store_success_in_cache(
    cache_key: str,
    doc_type: str,
    document: BaseDocument,
    metrics: Dict[str, float | int | bool],
    engine: str,
    profile: str,
    warnings: List[str],
    metadata: Dict[str, Any],
    emit: Dict[str, Any],
) -> None:
    payload = {
        "doc_type": doc_type,
        "document": document.model_dump(mode="json", exclude_none=True),
        "metrics": metrics,
        "engine": engine,
        "profile": profile,
        "warnings": warnings,
        "metadata": metadata,
        "emit": emit,
    }
    store_cache_entry(cache_key, payload)


def _determine_total_pages(pdf_path: Path) -> int:
    try:
        import fitz  # type: ignore
    except ImportError:  # pragma: no cover
        fitz = None  # type: ignore

    if fitz is not None:
        try:
            document = fitz.open(pdf_path)  # type: ignore[arg-type]
        except Exception:
            document = None
        else:
            page_count = document.page_count
            document.close()
            return page_count

    try:
        import pdfplumber  # type: ignore
    except ImportError:  # pragma: no cover
        pdfplumber = None  # type: ignore

    if pdfplumber is not None:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                return len(pdf.pages)
        except Exception:
            pass

    # Fallback: count via ingestion iterator.
    return len(load_pages(pdf_path))


__all__ = ["PipelineOutcome", "run_extract"]
