"""High-level extraction runner with completeness guards and caching."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, Type

from collections import defaultdict
import yaml

from medparse.config import ExtractionConfig, ExtractionProfile
from medparse.extractors.article import extract_article
from medparse.extractors.guideline import extract_guideline
from medparse.extractors.ifu import extract_ifu
from medparse.ifu.frontmatter import extract_front_matter
from medparse.extractors.textbook import extract_textbook_chapter
from medparse.extract.utils import load_pages
from medparse.schema.article import ArticleDocument
from medparse.schema.common import BaseDocument, EvidenceSpan, SizeGuards
from medparse.schema.ifu import IFUDocument
from medparse.schema.textbook import TextbookChapterDocument
from medparse.utils.cache import compute_cache_key, load_cache_entry, store_cache_entry
from medparse.emit.evidence_bank import EvidenceBank
from medparse.validate.ats_yield import validate_ats_yield
from medparse.text.hash import normalize_paragraph_text, stable_par_hash
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

DocType = Literal["article", "guideline", "ifu", "textbook"]
SummaryLength = Literal["short", "medium", "long"]

DROP_DEBUG_EVIDENCE = re.compile(r"^page\s+\d+\s+window<=\d+\s+tokens$", re.IGNORECASE)
WINDOW_PLACEHOLDER_RE = re.compile(r"^page\s+(-?\d+)\s+window<=\d+\s+tokens$", re.IGNORECASE)

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


def _estimate_pdf_density(pdf_path: Path, *, sample_pages: int = 6) -> Dict[str, float]:
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - optional dependency guard
        return {}

    try:
        doc = fitz.open(pdf_path)
    except Exception:  # pragma: no cover - defensive
        return {}

    page_count = int(getattr(doc, "page_count", 0) or 0)
    sample_total = max(1, min(sample_pages, page_count) or 1)
    total_chars = 0
    total_images = 0

    for idx in range(sample_total):
        try:
            page = doc.load_page(idx)
        except Exception:  # pragma: no cover - defensive
            continue
        text = page.get_text("text") or ""
        total_chars += len(text)
        try:
            total_images += len(page.get_images(full=True))
        except Exception:  # pragma: no cover - defensive
            try:
                total_images += len(page.get_images())
            except Exception:
                total_images += 0

    try:
        doc.close()
    except Exception:  # pragma: no cover - defensive
        pass

    avg_chars = total_chars / float(sample_total)
    image_ratio = total_images / float(sample_total)
    return {
        "page_count": float(page_count),
        "avg_chars_per_page": avg_chars,
        "image_ratio": image_ratio,
    }


def _normalize_override_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _infer_engine_override_key(
    pdf_path: Path,
    overrides: Dict[str, object],
    *,
    sample_pages: int = 4,
) -> tuple[Optional[str], Optional[str]]:
    """Return (override_key, engine_mode) when a manufacturer override matches."""

    if not overrides:
        return None, None

    normalized_path = _normalize_override_key(str(pdf_path))
    for raw_key, mode in overrides.items():
        if not isinstance(raw_key, str):
            continue
        match_key = _normalize_override_key(raw_key)
        if not match_key:
            continue
        if match_key in normalized_path:
            return raw_key, str(mode)

    # Fallback to lightweight front-matter detection using pymupdf pages
    try:
        pages = load_pages(pdf_path, engine="pymupdf", max_pages=sample_pages)
    except Exception:
        pages = []
    if pages:
        metadata_title = pdf_path.stem.replace("_", " ").strip()
        front_matter = extract_front_matter(pages, metadata_title=metadata_title or None)
        manufacturer = front_matter.get("manufacturer") if isinstance(front_matter, dict) else None
        if manufacturer:
            manufacturer_key = _normalize_override_key(str(manufacturer))
            for raw_key, mode in overrides.items():
                if not isinstance(raw_key, str):
                    continue
                match_key = _normalize_override_key(raw_key)
                if match_key and match_key in manufacturer_key:
                    return raw_key, str(mode)
    return None, None


def _resolve_ifu_engines(
    pdf_path: Path,
    config: PipelineConfig,
    *,
    force_deep: bool,
    total_pages: Optional[int] = None,
) -> tuple[list[str], Dict[str, float]]:
    base_engines = config.resolved_engines(force_deep=force_deep)
    if not isinstance(config.ifu, dict):
        config.ifu = {}
    ifu_settings = config.ifu
    engine_block = ifu_settings.get("engine") or {}
    if not isinstance(engine_block, dict):
        engine_block = {}

    mode = str(engine_block.get("mode") or "manual").lower()
    cli_engine = str(ifu_settings.get("cli_engine") or "").strip().lower()
    default_engine = str(ifu_settings.get("ifu_engine") or "").strip().lower()
    overrides_cfg = ifu_settings.get("engine_overrides")
    override_key: Optional[str] = None
    override_choice: Optional[str] = None
    if isinstance(overrides_cfg, dict) and overrides_cfg:
        override_key, override_choice = _infer_engine_override_key(pdf_path, overrides_cfg)

    resolved_mode = mode
    engine_source = "engine"
    if cli_engine:
        resolved_mode = cli_engine
        engine_source = "cli"
    elif override_choice:
        resolved_mode = str(override_choice).lower()
        engine_source = f"manufacturer:{override_key}" if override_key else "manufacturer"
    elif default_engine:
        resolved_mode = default_engine
        engine_source = "config"
    mode = resolved_mode or mode or "auto"

    text_engine = str(engine_block.get("text") or (base_engines[0] if base_engines else "pymupdf"))
    tables_engine = str(engine_block.get("tables") or "pdfplumber")
    fallback_engine = str(engine_block.get("fallback") or tables_engine or "pdfplumber")
    auto_block = engine_block.get("auto") or {}
    if not isinstance(auto_block, dict):
        auto_block = {}
    timeout_block = auto_block.get("timeouts") or engine_block.get("timeouts") or {}
    engine_timeouts: Dict[str, float] = {}
    if isinstance(timeout_block, dict):
        for key, value in timeout_block.items():
            try:
                engine_timeouts[str(key).lower()] = float(value)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                continue

    def _unique_order(candidates: Iterable[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate:
                continue
            lowered = candidate.lower()
            if lowered not in seen:
                seen.add(lowered)
                ordered.append(lowered)
        return ordered

    fast_long_docs = bool(ifu_settings.get("fast_long_docs", False))
    long_doc_threshold = int(ifu_settings.get("long_doc_page_threshold", 80) or 80)
    fast_engine = str(ifu_settings.get("fast_long_engine", "pymupdf") or "pymupdf").lower()

    runtime_info = {
        "mode": mode,
        "source": engine_source,
        "cli_engine": cli_engine or None,
    }
    if override_key:
        runtime_info["override_key"] = override_key

    if mode == "hybrid":
        engines = _unique_order(
            [
                text_engine,
                tables_engine,
                fallback_engine,
                *base_engines,
            ]
        )
    elif mode in {"pymupdf", "pdfplumber"}:
        engines = _unique_order([mode, *base_engines])
    elif mode != "auto":
        engines = _unique_order([text_engine, fallback_engine, *base_engines])
    else:
        sample_pages = int(auto_block.get("sample_pages", 6) or 6)
        metrics = _estimate_pdf_density(pdf_path, sample_pages=sample_pages)
        avg_chars = float(metrics.get("avg_chars_per_page", 0.0))
        image_ratio = float(metrics.get("image_ratio", 0.0))
        page_count = float(metrics.get("page_count", 0.0))

        char_threshold = float(auto_block.get("char_density_threshold", auto_block.get("char_threshold", 900)))
        image_threshold = float(auto_block.get("image_density_threshold", auto_block.get("image_threshold", 0.8)))
        large_doc_pages = float(auto_block.get("large_doc_pages", 120))
        prefer_engine = str(auto_block.get("prefer", text_engine or "pymupdf"))
        fallback = str(auto_block.get("fallback", fallback_engine or "pdfplumber"))

        primary = prefer_engine
        if avg_chars < char_threshold or image_ratio >= image_threshold:
            primary = fallback
        elif page_count >= large_doc_pages:
            primary = prefer_engine

        engines = _unique_order([primary, prefer_engine, fallback, fallback_engine, text_engine, *base_engines])

    fast_path = False
    if fast_long_docs and isinstance(total_pages, (int, float)) and total_pages > long_doc_threshold:
        fast_path = True
        if fast_engine not in engines:
            engines.insert(0, fast_engine)
        else:
            engines = [fast_engine, *[candidate for candidate in engines if candidate != fast_engine]]

    runtime_info["long_doc_fast_path"] = fast_path
    runtime_info["long_doc_page_threshold"] = long_doc_threshold
    if total_pages is not None:
        runtime_info["long_doc_page_count"] = int(total_pages)
    runtime_info["fast_long_engine"] = fast_engine
    config.ifu["_engine_runtime"] = runtime_info  # type: ignore[index]

    return engines, engine_timeouts


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
    metadata_sources: Dict[str, Any] = field(default_factory=dict)
    enrichment: Dict[str, Any] = field(default_factory=dict)
    ifu: Dict[str, Any] = field(default_factory=dict)

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
        shared_emit_path = path.parent / "_shared" / "emit.yaml"
        shared_emit: Dict[str, Any] = {}
        if shared_emit_path.exists():
            try:
                shared_data = yaml.safe_load(shared_emit_path.read_text(encoding="utf-8")) or {}
                if isinstance(shared_data, dict):
                    shared_emit = shared_data.get("emit", shared_data)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Failed to load shared emit defaults from %s: %s", shared_emit_path, exc)
        emit_settings = dict(shared_emit)
        emit_settings.update(data.get("emit") or {})
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
            metadata_sources=data.get("metadata_sources") or {},
            enrichment=data.get("enrichment") or {},
            ifu=data.get("ifu") or {},
        )

    def to_extraction_config(self, *, use_cache: bool) -> ExtractionConfig:
        kwargs = {
            "profile": self.profile,
            "use_cache": use_cache,
            "thresholds": self.thresholds,
            "metadata_sources": self.metadata_sources,
            "enrichment": self.enrichment,
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
        kwargs["ifu"] = self.ifu
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
            "issues": list(self.warnings) if self.warnings else [],
        }


def _build_evidence_bank(document: BaseDocument, size_guards: SizeGuards) -> EvidenceBank:
    """Build evidence bank from extracted document, deduplicating evidence spans.

    Args:
        document: Extracted document with evidence spans
        size_guards: Size limits configuration

    Returns:
        EvidenceBank with deduplicated evidence
    """
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    evidence_policy = str(pipeline_info.get("evidence_policy", "verbatim") or "verbatim").lower()
    inline_text = evidence_policy == "verbatim"

    raw_paragraph_store = getattr(document, "paragraph_store", {}) or {}
    paragraph_store: Dict[str, Dict[str, object]] = {}
    if isinstance(raw_paragraph_store, dict):
        for key, value in raw_paragraph_store.items():
            if not isinstance(value, dict):
                continue
            text_value = normalize_paragraph_text(value.get("text"))
            if not text_value:
                continue
            normalized_entry = dict(value)
            normalized_entry["text"] = text_value
            normalized_entry["length"] = len(text_value)
            paragraph_store[key] = normalized_entry
    setattr(document, "paragraph_store", paragraph_store)
    setattr(document, "paragraph_store", paragraph_store)

    bank = EvidenceBank(
        size_guards=size_guards,
        paragraph_store=paragraph_store,
        inline_text=inline_text,
    )
    max_evidence_list = max(1, size_guards.max_evidence_per_item)

    def _apply_pointer(parent, field: str, pointer: EvidenceSpan, ref_id: str) -> None:
        setattr(parent, field, pointer)
        setattr(parent, "evidence_refs", [ref_id])

    def _resolve_span(span: EvidenceSpan) -> Optional[EvidenceSpan]:
        if not isinstance(span, EvidenceSpan):
            return None
        text = span.text
        if not text and span.paragraph_hash:
            segment = paragraph_store.get(span.paragraph_hash)
            if isinstance(segment, dict):
                candidate = str(segment.get("text") or "")
            elif isinstance(segment, str):
                candidate = segment
            else:
                candidate = ""
            if candidate:
                start, end = span.paragraph_offset or (0, len(candidate))
                try:
                    text = candidate[start:end]
                except Exception:
                    text = candidate
        if not text and span.hash:
            candidate = paragraph_store.get(span.hash)
            if isinstance(candidate, dict):
                text = str(candidate.get("text") or "")
            elif isinstance(candidate, str):
                text = candidate
        if not text:
            return None
        resolved = EvidenceSpan(
            text=text,
            page=span.page,
            bbox=span.bbox,
            confidence=span.confidence,
            truncated=span.truncated,
        )
        resolved.hash = span.hash or span.paragraph_hash or resolved.compute_hash()
        resolved.paragraph_hash = span.paragraph_hash or resolved.hash
        resolved.paragraph_offset = span.paragraph_offset
        return resolved

    # Process recommendations
    if hasattr(document, "recommendations"):
        for rec in getattr(document, "recommendations") or []:
            evidence = getattr(rec, "evidence", None)
            if isinstance(evidence, list):
                prepared: List[tuple[EvidenceSpan, EvidenceSpan]] = []
                for span in evidence[:max_evidence_list]:
                    if not isinstance(span, EvidenceSpan):
                        continue
                    resolved = _resolve_span(span)
                    if resolved:
                        prepared.append((span, resolved))
                refs = bank.add_evidence_list([resolved for _, resolved in prepared])
                if refs and prepared:
                    for (original, resolved), ref in zip(prepared, refs, strict=False):
                        original.hash = resolved.hash or ref
                    pointer = prepared[0][0].as_pointer()
                    setattr(rec, "evidence_refs", refs)
                    setattr(rec, "evidence", pointer)
            elif isinstance(evidence, EvidenceSpan):
                resolved = _resolve_span(evidence)
                if resolved:
                    ref = bank.add_evidence(resolved)
                    if ref:
                        evidence.hash = resolved.hash or ref
                        pointer = evidence.as_pointer()
                        _apply_pointer(rec, "evidence", pointer, ref)

    # Process outcomes
    if hasattr(document, "outcomes"):
        for outcome in getattr(document, "outcomes") or []:
            evidence = getattr(outcome, "evidence", None)
            if isinstance(evidence, list):
                prepared: List[tuple[EvidenceSpan, EvidenceSpan]] = []
                for span in evidence[:max_evidence_list]:
                    if not isinstance(span, EvidenceSpan):
                        continue
                    resolved = _resolve_span(span)
                    if resolved:
                        prepared.append((span, resolved))
                refs = bank.add_evidence_list([resolved for _, resolved in prepared])
                if refs and prepared:
                    for (original, resolved), ref in zip(prepared, refs, strict=False):
                        original.hash = resolved.hash or ref
                    pointer = prepared[0][0].as_pointer()
                    setattr(outcome, "evidence_refs", refs)
                    setattr(outcome, "evidence", pointer)
            elif isinstance(evidence, EvidenceSpan):
                resolved = _resolve_span(evidence)
                if resolved:
                    ref = bank.add_evidence(resolved)
                    if ref:
                        evidence.hash = resolved.hash or ref
                        pointer = evidence.as_pointer()
                        _apply_pointer(outcome, "evidence", pointer, ref)

    # Process diagnostic_yield
    if hasattr(document, "diagnostic_yield"):
        diag = getattr(document, "diagnostic_yield")
        if diag:
            evidence = getattr(diag, "evidence", None)
            if isinstance(evidence, EvidenceSpan):
                resolved = _resolve_span(evidence)
                if resolved:
                    ref = bank.add_evidence(resolved)
                    if ref:
                        evidence.hash = resolved.hash or ref
                        pointer = evidence.as_pointer()
                        _apply_pointer(diag, "evidence", pointer, ref)

    # Process relations
    if hasattr(document, "relations"):
        for relation in getattr(document, "relations") or []:
            evidence = getattr(relation, "evidence", None)
            if isinstance(evidence, EvidenceSpan):
                resolved = _resolve_span(evidence)
                if resolved:
                    ref = bank.add_evidence(resolved)
                    if ref:
                        evidence.hash = resolved.hash or ref
                        pointer = evidence.as_pointer()
                        _apply_pointer(relation, "evidence", pointer, ref)
            elif isinstance(evidence, list):
                prepared: List[tuple[EvidenceSpan, EvidenceSpan]] = []
                for span in evidence[:max_evidence_list]:
                    if not isinstance(span, EvidenceSpan):
                        continue
                    resolved = _resolve_span(span)
                    if resolved:
                        prepared.append((span, resolved))
                refs = bank.add_evidence_list([resolved for _, resolved in prepared])
                if refs and prepared:
                    for (original, resolved), ref in zip(prepared, refs, strict=False):
                        original.hash = resolved.hash or ref
                    pointer = prepared[0][0].as_pointer()
                    setattr(relation, "evidence_refs", refs)
                    setattr(relation, "evidence", pointer)

    # Process figures
    if hasattr(document, "figures"):
        for figure in getattr(document, "figures") or []:
            evidence = getattr(figure, "evidence", None)
            if isinstance(evidence, EvidenceSpan):
                resolved = _resolve_span(evidence)
                if resolved:
                    ref = bank.add_evidence(resolved)
                    if ref:
                        evidence.hash = resolved.hash or ref
                        pointer = evidence.as_pointer()
                        _apply_pointer(figure, "evidence", pointer, ref)

    if hasattr(document, "key_points"):
        for point in getattr(document, "key_points") or []:
            evidence = getattr(point, "evidence", None)
            if isinstance(evidence, EvidenceSpan):
                resolved = _resolve_span(evidence)
                if resolved:
                    ref = bank.add_evidence(resolved)
                    if ref:
                        evidence.hash = resolved.hash or ref
                        pointer = evidence.as_pointer()
                        _apply_pointer(point, "evidence", pointer, ref)

    definitions_evidence = getattr(document, "definitions_evidence", None)
    if isinstance(definitions_evidence, EvidenceSpan):
        resolved = _resolve_span(definitions_evidence)
        if resolved:
            ref = bank.add_evidence(resolved)
            if ref:
                definitions_evidence.hash = resolved.hash or ref
                pointer = definitions_evidence.as_pointer()
                setattr(document, "definitions_evidence", pointer)
                setattr(document, "definitions_evidence_refs", [ref])

    diagnostic_flow = getattr(document, "diagnostic_flow", None)
    if diagnostic_flow:
        flow_evidence = getattr(diagnostic_flow, "evidence", None)
        if isinstance(flow_evidence, EvidenceSpan):
            resolved = _resolve_span(flow_evidence)
            if resolved:
                ref = bank.add_evidence(resolved)
                if ref:
                    flow_evidence.hash = resolved.hash or ref
                    pointer = flow_evidence.as_pointer()
                    setattr(diagnostic_flow, "evidence", pointer)
                    setattr(diagnostic_flow, "evidence_refs", [ref])

    return bank


def _prune_evidence_refs(document: BaseDocument, removed: set[str]) -> None:
    if not removed:
        return

    def _prune_object(item: object) -> None:
        if not item:
            return
        if hasattr(item, "evidence_refs"):
            refs = getattr(item, "evidence_refs")
            if isinstance(refs, list):
                filtered = [ref for ref in refs if ref not in removed]
                setattr(item, "evidence_refs", filtered or None)
        evidence = getattr(item, "evidence", None)
        if isinstance(evidence, EvidenceSpan):
            if getattr(evidence, "hash", None) in removed:
                evidence.hash = None
            if getattr(evidence, "paragraph_hash", None) in removed:
                evidence.paragraph_hash = None
            if not evidence.hash and not evidence.text:
                setattr(item, "evidence", None)

    def _prune_collection(collection: Optional[List[object]]) -> None:
        if not collection:
            return
        for entry in collection:
            _prune_object(entry)

    _prune_collection(getattr(document, "recommendations", None))
    _prune_collection(getattr(document, "outcomes", None))
    _prune_collection(getattr(document, "tables", None))
    _prune_collection(getattr(document, "relations", None))
    _prune_collection(getattr(document, "figures", None))
    diagnostic = getattr(document, "diagnostic_yield", None)
    _prune_object(diagnostic)


def _clean_debug_evidence(document: BaseDocument) -> set[str]:
    evidence_bank = getattr(document, "evidence_bank", None)
    if not isinstance(evidence_bank, dict) or not evidence_bank:
        return set()
    paragraph_store = getattr(document, "paragraph_store", {}) or {}
    removed: set[str] = set()

    for hash_id, payload in list(evidence_bank.items()):
        if not isinstance(payload, dict):
            continue
        snippet = str(payload.get("text") or "").strip()
        if not snippet:
            paragraph_hash = payload.get("paragraph_hash") or payload.get("hash") or hash_id
            if paragraph_hash and isinstance(paragraph_store, dict):
                entry = paragraph_store.get(paragraph_hash)
                if entry is None and isinstance(paragraph_hash, str):
                    entry = paragraph_store.get(paragraph_hash.lower())
                if isinstance(entry, dict):
                    snippet = str(entry.get("text") or "").strip()
        if snippet and DROP_DEBUG_EVIDENCE.match(snippet):
            evidence_bank.pop(hash_id, None)
            removed.add(hash_id)

    if removed:
        _prune_evidence_refs(document, removed)

    return removed


def write_failure_artifact(
    out_path: Path,
    exc: Exception,
    *,
    stage: str,
    profile: str,
    doc_path: Path,
) -> None:
    """Persist a structured failure artifact for batch operations."""

    from datetime import datetime

    failure_payload = {
        "failure_reason": f"{exc.__class__.__name__}: {exc}",
        "metrics": {
            "stage": stage,
            "profile": profile or "auto",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
        "doc_path": str(doc_path),
    }
    failure_path = out_path.with_suffix(out_path.suffix + ".failure.json")
    try:
        failure_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    failure_path.write_text(json.dumps(failure_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_extract(
    pdf_path: Path,
    config_path: Path,
    *,
    use_cache: bool = True,
    force_deep: bool = False,
    max_pages: Optional[int] = None,
    summary_length: Optional[SummaryLength] = None,
    profile_override: Optional[str] = None,
    emit_overrides: Optional[Dict[str, object]] = None,
    metadata_overrides: Optional[Dict[str, object]] = None,
    ifu_overrides: Optional[Dict[str, object]] = None,
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

    if emit_overrides:
        merged_emit = dict(config.emit or {})
        for key, value in emit_overrides.items():
            if value is None:
                continue
            merged_emit[key] = value
        config.emit = merged_emit

    if metadata_overrides:
        merged_metadata = dict(config.metadata_sources or {})
        for key, value in metadata_overrides.items():
            if value is None:
                continue
            merged_metadata[key] = value
        config.metadata_sources = merged_metadata

    emit_policy_source = "cli" if emit_overrides else "yaml"

    if ifu_overrides:
        merged_ifu = dict(config.ifu or {})
        for key, value in ifu_overrides.items():
            if value is None:
                continue
            if key == "engine" and isinstance(value, dict):
                existing_engine = merged_ifu.get("engine")
                if isinstance(existing_engine, dict):
                    updated_engine = dict(existing_engine)
                    updated_engine.update(value)
                    merged_ifu["engine"] = updated_engine
                else:
                    merged_ifu["engine"] = dict(value)
            else:
                merged_ifu[key] = value
        config.ifu = merged_ifu

    if config.doc_type not in EXTRACTOR_MAP:
        raise ValueError(f"Unsupported doc_type '{config.doc_type}' in {config_path}")

    extractor = EXTRACTOR_MAP[config.doc_type]
    pdf_bytes = pdf_path.read_bytes()
    total_pages = _determine_total_pages(pdf_path)
    engine_timeouts: Dict[str, float] = {}
    if config.doc_type == "ifu":
        engines, engine_timeouts = _resolve_ifu_engines(
            pdf_path,
            config,
            force_deep=force_deep,
            total_pages=total_pages,
        )
    else:
        engines = config.resolved_engines(force_deep=force_deep)
    ocr_enabled = bool(config.ocr_settings.get("enable", config.ocr))
    base_metadata = {
        "engines_requested": engines,
        "metadata_sources": dict(config.metadata_sources or {}),
        "emit_policy_source": emit_policy_source,
    }
    if engine_timeouts:
        base_metadata["engine_timeouts"] = dict(engine_timeouts)
    if config.doc_type == "ifu":
        runtime_info = config.ifu.get("_engine_runtime") if isinstance(config.ifu, dict) else None
        if isinstance(runtime_info, dict):
            base_metadata["ifu_engine_mode"] = runtime_info.get("mode")
            base_metadata["ifu_engine_source"] = runtime_info.get("source")
            if runtime_info.get("override_key"):
                base_metadata["ifu_engine_override_key"] = runtime_info.get("override_key")
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
    last_metadata: Dict[str, Any] = dict(base_metadata)

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
        document.pipeline_info.setdefault("extracted_chars", metrics.get("extracted_chars"))
        if bool(document.pipeline_info.get("paragraph_dedup_applied")):
            metrics["paragraph_dedup_applied"] = True
        if bool(document.pipeline_info.get("text_repair_applied")):
            metrics["text_repair_applied"] = True
        rec_metrics = document.pipeline_info.get("recommendation_metrics")
        if isinstance(rec_metrics, dict) and rec_metrics.get("total"):
            LOGGER.info(
                "Recommendation metrics: total=%s graded=%s ungraded_typed=%s grade_density=%.2f typed_density=%.2f",
                rec_metrics.get("total"),
                rec_metrics.get("graded"),
                rec_metrics.get("typed_ungraded"),
                float(rec_metrics.get("grade_density", 0.0)),
                float(rec_metrics.get("typed_density", 0.0)),
            )

        emit_warnings = _apply_emit_constraints(document, config.emit, policy_source=emit_policy_source)

        timeout_limit = engine_timeouts.get(engine)
        if timeout_limit and duration > timeout_limit:
            LOGGER.warning(
                "Engine %s exceeded soft timeout %.1fs (took %.1fs); attempting fallback.",
                engine,
                timeout_limit,
                duration,
            )
            metrics["engine_timeout"] = True
            last_metrics = metrics
            last_engine = engine
            last_ocr_pages = ocr_pages
            timeout_warning = f"{engine}_timeout"
            metadata_with_timeout = dict(base_metadata)
            warnings_list = metadata_with_timeout.setdefault("threshold_warnings", [])
            if timeout_warning not in warnings_list:
                warnings_list.append(timeout_warning)
            last_metadata = metadata_with_timeout
            failure_reason = timeout_warning
            continue

        # Build evidence bank for deduplication and size reduction
        size_guards = SizeGuards(**(config.size_guards or {}))
        evidence_bank = _build_evidence_bank(document, size_guards)

        # Populate document with evidence bank
        document.evidence_bank = evidence_bank.get_bank()
        metrics["evidence_bank_size"] = len(document.evidence_bank)

        paragraph_store = getattr(document, "paragraph_store", {})
        if isinstance(paragraph_store, dict):
            metrics["paragraph_store_size"] = len(paragraph_store)

        removed_hashes = _clean_debug_evidence(document)
        if removed_hashes:
            metrics["evidence_bank_size"] = len(document.evidence_bank)
            document.pipeline_info["evidence_bank_pruned"] = len(removed_hashes)

        # Add truncation notice if any truncation occurred
        truncation_notice = evidence_bank.get_truncation_notice()
        if truncation_notice:
            document.truncation_notice = truncation_notice

        # Log deduplication stats
        stats = evidence_bank.get_stats()
        if config.doc_type == "ifu" and stats["total_added"] == 0 and stats["deduplicated"] == 0 and stats["truncated"] == 0:
            LOGGER.debug(
                "Evidence deduplication skipped: total=0 doc_type=%s bank_size=%d",
                config.doc_type,
                len(document.evidence_bank),
            )
        else:
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
                cache_metadata = dict(base_metadata)
                _store_success_in_cache(
                    cache_key,
                    config.doc_type,
                    document,
                    metrics,
                    engine,
                    extraction_config.profile.value,
                    combined_warnings,
                    cache_metadata,
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
                metadata=dict(base_metadata),
                emit_settings=config.emit,
            )

        last_metrics = metrics
        last_engine = engine
        last_ocr_pages = ocr_pages
        metadata_with_warnings = dict(base_metadata)
        metadata_with_warnings["threshold_warnings"] = combined_warnings
        last_metadata = metadata_with_warnings
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
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    if "paragraph_dedup_applied" not in pipeline_info:
        pipeline_info["paragraph_dedup_applied"] = False
    policy_source = pipeline_info.get("emit_policy_source")
    if policy_source:
        payload["emit_policy_source"] = str(policy_source)

    if hasattr(document, "sections"):
        sections = getattr(document, "sections") or {}
        payload["sections_count"] = len(sections)

    if hasattr(document, "doc_subtype"):
        payload["doc_subtype"] = getattr(document, "doc_subtype")

    if hasattr(document, "tables"):
        tables = getattr(document, "tables") or []
        payload["tables_kept"] = len(tables)
        pipeline_info["tables_kept"] = len(tables)
    else:
        payload["tables_kept"] = payload.get("tables_kept", 0)
        pipeline_info.setdefault("tables_kept", 0)

    if hasattr(document, "recommendations"):
        recs = getattr(document, "recommendations") or []
        total_recs = len(recs)
        with_grade = 0
        graded_count = 0
        typed_ungraded = 0
        for rec in recs:
            normalized = getattr(rec, "grade_normalized", None) or {}
            if normalized:
                with_grade += 1
                if normalized.get("ungraded"):
                    typed_ungraded += 1
                else:
                    graded_count += 1
            elif getattr(rec, "ungraded", False):
                typed_ungraded += 1
        typed_ungraded = min(typed_ungraded, max(0, total_recs - graded_count))
        grade_density = round(with_grade / total_recs, 4) if total_recs else 0.0
        typed_density = round((graded_count + typed_ungraded) / total_recs, 4) if total_recs else 0.0

        payload["recommendations_count"] = total_recs
        payload["graded_count"] = graded_count
        payload["typed_ungraded_count"] = typed_ungraded
        payload["grade_density"] = grade_density
        payload["typed_density"] = typed_density

        pipeline_info["recommendations_count"] = total_recs
        pipeline_info["graded_count"] = graded_count
        pipeline_info["typed_ungraded_count"] = typed_ungraded
        pipeline_info["grade_density"] = grade_density
        pipeline_info["typed_density"] = typed_density
        grade_sources = pipeline_info.get("grade_source_breakdown")
        if isinstance(grade_sources, dict) and grade_sources:
            payload["grade_source_breakdown"] = dict(grade_sources)
        metrics_block = pipeline_info.setdefault("recommendation_metrics", {})
        metrics_block.update(
            {
                "total": total_recs,
                "graded": graded_count,
                "typed_ungraded": typed_ungraded,
                "grade_density": grade_density,
                "typed_density": typed_density,
            }
        )
        if isinstance(grade_sources, dict) and grade_sources:
            metrics_block["grade_source_breakdown"] = dict(grade_sources)

    if hasattr(document, "yield_definitions_present"):
        value = getattr(document, "yield_definitions_present")
        if value is not None:
            payload["yield_definitions_present"] = bool(value)

    if hasattr(document, "diagnostic_yield"):
        payload["diagnostic_yield_present"] = bool(getattr(document, "diagnostic_yield"))
        diag = getattr(document, "diagnostic_yield")
        if diag is not None and hasattr(diag, "strict"):
            payload["diagnostic_yield_strict"] = bool(getattr(diag, "strict"))

    if getattr(document, "doc_type", None) == "article":
        payload["ats"] = validate_ats_yield(document)

    payload["paragraph_dedup_applied"] = bool(pipeline_info.get("paragraph_dedup_applied"))
    try:
        payload["relations_dropped"] = int(pipeline_info.get("relations_dropped") or 0)
    except (TypeError, ValueError):
        payload["relations_dropped"] = 0
    pipeline_info["relations_dropped"] = payload["relations_dropped"]
    try:
        payload["tables_dropped"] = int(pipeline_info.get("tables_dropped") or 0)
    except (TypeError, ValueError):
        payload["tables_dropped"] = 0
    pipeline_info["tables_dropped"] = payload["tables_dropped"]
    if "window_placeholders_removed" in pipeline_info:
        try:
            payload["window_placeholders_removed"] = int(pipeline_info.get("window_placeholders_removed") or 0)
        except (TypeError, ValueError):
            payload["window_placeholders_removed"] = 0

    if hasattr(document, "umls_entities"):
        entities = getattr(document, "umls_entities") or []
        payload["umls_entities"] = len(entities)

    if hasattr(document, "relations"):
        relations = getattr(document, "relations") or []
        payload["relations_count"] = len(relations)
        payload["relations_kept"] = len(relations)
        pipeline_info["relations_kept"] = len(relations)
    else:
        payload.setdefault("relations_count", 0)
        payload.setdefault("relations_kept", 0)
        pipeline_info.setdefault("relations_kept", 0)

    if hasattr(document, "safety_blocks"):
        blocks = getattr(document, "safety_blocks") or []
        payload["safety_blocks_found"] = len(blocks)
        pipeline_info["safety_blocks_found"] = len(blocks)

    if hasattr(document, "references"):
        references = getattr(document, "references") or []
        payload["references_count"] = len(references)
        pipeline_info["references_detected"] = len(references)

    if "long_doc_fast_path" in pipeline_info:
        payload["long_doc_fast_path"] = bool(pipeline_info.get("long_doc_fast_path"))
        threshold_value = pipeline_info.get("long_doc_page_threshold")
        if threshold_value is not None:
            payload["long_doc_page_threshold"] = threshold_value

    toc_guard_info = pipeline_info.get("toc_guard")
    if isinstance(toc_guard_info, dict):
        guard_metrics = {
            "pages_dropped": toc_guard_info.get("pages_dropped", pipeline_info.get("toc_guard_pages_dropped", [])),
            "pages_dropped_count": toc_guard_info.get(
                "pages_dropped_count", pipeline_info.get("toc_guard_pages_dropped_count", 0)
            ),
        }
        payload["toc_guard"] = guard_metrics
    anchors_bleed = pipeline_info.get("anchors_bleed")
    if isinstance(anchors_bleed, dict):
        payload["anchors_bleed"] = dict(anchors_bleed)
    if "small_ifu_fallback_applied" in pipeline_info:
        payload["small_ifu_fallback_applied"] = bool(pipeline_info.get("small_ifu_fallback_applied"))
    if "small_ifu_threshold" in pipeline_info:
        payload["small_ifu_threshold"] = pipeline_info.get("small_ifu_threshold")
    if "extracted_chars" in pipeline_info:
        try:
            payload["extracted_chars"] = int(pipeline_info.get("extracted_chars") or 0)
        except (TypeError, ValueError):
            payload["extracted_chars"] = 0

    _validate_metrics_consistency(payload, pipeline_info)
    document.pipeline_info = pipeline_info
    return payload


def _hydrate_document(doc_type: str, cached_data: Dict[str, object]) -> BaseDocument:
    model_cls = MODEL_MAP.get(doc_type)
    if not model_cls:
        raise ValueError(f"Unsupported doc_type '{doc_type}' in cache entry.")
    document_payload = cached_data.get("document") or {}
    return model_cls.model_validate(document_payload)


def _validate_metrics_consistency(
    metrics: Dict[str, int | float | bool],
    pipeline_info: Dict[str, object],
) -> None:
    """Sanity-check metric counters against pipeline bookkeeping."""

    for key in ("recommendations_count", "graded_count", "typed_ungraded_count", "grade_density", "typed_density"):
        if key in pipeline_info:
            assert metrics.get(key) == pipeline_info.get(key), f"Metrics mismatch for {key}"
    for key in ("relations_dropped", "tables_dropped", "relations_kept", "tables_kept", "window_placeholders_removed"):
        if key in pipeline_info:
            assert metrics.get(key) == pipeline_info.get(key), f"Metrics mismatch for {key}"
    if "paragraph_dedup_applied" in pipeline_info:
        assert bool(metrics.get("paragraph_dedup_applied")) == bool(
            pipeline_info.get("paragraph_dedup_applied")
        ), "Metrics mismatch for paragraph_dedup_applied"


def _apply_emit_constraints(
    document: BaseDocument,
    emit: Dict[str, Any],
    *,
    policy_source: str = "yaml",
) -> List[str]:
    warnings: List[str] = []
    pipeline_info: Dict[str, Any] = {}
    if document is not None:
        existing_pipeline = getattr(document, "pipeline_info", {}) or {}
        if isinstance(existing_pipeline, dict):
            pipeline_info = existing_pipeline
    normalized_source = "cli" if str(policy_source).lower() == "cli" else "yaml"
    assert normalized_source in {"cli", "yaml"}
    pipeline_info["emit_policy_source"] = normalized_source
    pipeline_info.setdefault("paragraph_dedup_applied", False)
    if document is not None:
        document.pipeline_info = pipeline_info

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
    evidence_policy = str(emit.get("evidence_policy", "verbatim") or "verbatim").lower()
    relation_mode = str(emit.get("relation_mode", "verbatim") or "verbatim").lower()
    max_entities = _coerce_positive_int(emit.get("max_entities"))
    max_relations = _coerce_positive_int(emit.get("max_relations"))
    max_relations_per_pair = _coerce_positive_int(emit.get("max_relations_per_pair"))
    max_json_bytes = _coerce_positive_int(emit.get("max_json_bytes"))
    keep_evidence_bank = bool(emit.get("keep_evidence_bank", True))
    paragraph_requested = bool(emit.get("paragraph_store", emit.get("paragraph_dedupe", False)))
    tables_cfg = emit.get("tables")
    if not isinstance(tables_cfg, dict):
        tables_cfg = {}
    preserve_header_tokens = [
        str(value).lower()
        for value in tables_cfg.get("preserve_headers", [])
        if isinstance(value, str)
    ]
    preserve_summary_tables = bool(tables_cfg.get("preserve_summary_recommendations"))

    def _flatten_headers(raw_headers: Sequence[Sequence[str] | str]) -> List[str]:
        if not raw_headers:
            return []
        if all(isinstance(item, str) for item in raw_headers):
            return [str(item or "").strip() for item in raw_headers]  # type: ignore[list-item]
        breadth = 0
        for row in raw_headers:
            if isinstance(row, (list, tuple)):
                breadth = max(breadth, len(row))
        flattened: List[str] = []
        for idx in range(breadth):
            parts: List[str] = []
            for row in raw_headers:
                if isinstance(row, (list, tuple)) and idx < len(row):
                    cell = row[idx]
                    if cell:
                        parts.append(str(cell).strip())
            flattened.append(" ".join(parts).strip())
        return flattened

    def _contains_grade_columns(flattened_headers: Sequence[str]) -> bool:
        grade_tokens = ("grade", "strength", "certainty", "quality")
        for header in flattened_headers:
            lowered = str(header or "").lower()
            if any(token in lowered for token in grade_tokens):
                return True
        return False

    paragraph_mode = paragraph_requested or evidence_policy == "compact"
    window_placeholder = re.compile(r"^page\s+(-?\d+)\s+window<=\d+\s+tokens$", re.IGNORECASE)
    co_mention_placeholder = re.compile(r"^page\s+(-?\d+)\s+co[- ]mention", re.IGNORECASE)

    paragraph_store = getattr(document, "paragraph_store", None)
    placeholders_removed = 0
    if not isinstance(paragraph_store, dict):
        paragraph_store = {}
    else:
        for hash_id, entry in list(paragraph_store.items()):
            if not isinstance(entry, dict):
                paragraph_store.pop(hash_id, None)
                continue
            raw_text = str(entry.get("text") or "")
            if WINDOW_PLACEHOLDER_RE.match(raw_text.strip()):
                paragraph_store.pop(hash_id, None)
                placeholders_removed += 1
                continue
            text_value = normalize_paragraph_text(raw_text)
            if not text_value or WINDOW_PLACEHOLDER_RE.match(text_value):
                paragraph_store.pop(hash_id, None)
                placeholders_removed += 1
                continue
            entry["text"] = text_value
            entry["length"] = len(text_value)
            page_value = entry.get("page")
            pages_value = entry.get("pages")
            if isinstance(pages_value, list) and pages_value:
                entry["page"] = page_value if page_value is not None else pages_value[0]
            elif page_value is not None:
                entry["pages"] = [page_value]
            else:
                entry["pages"] = []
            char_span = entry.get("char_span")
            if isinstance(char_span, tuple):
                entry["char_span"] = list(char_span)
            elif not isinstance(char_span, list):
                entry["char_span"] = None
            occurrences = entry.get("occurrences")
            if isinstance(occurrences, list) and occurrences:
                normalized_occurrences = []
                for occurrence in occurrences:
                    if not isinstance(occurrence, dict):
                        continue
                    occurrence_page = occurrence.get("page")
                    occurrence_span = occurrence.get("char_span")
                    if isinstance(occurrence_span, tuple):
                        occurrence_span = list(occurrence_span)
                    normalized_occurrences.append(
                        {
                            "page": occurrence_page,
                            "char_span": occurrence_span,
                        }
                    )
                entry["occurrences"] = normalized_occurrences
            else:
                entry["occurrences"] = [
                    {
                        "page": entry.get("page"),
                        "char_span": entry.get("char_span"),
                    }
                ]
            if "order" not in entry or not isinstance(entry["order"], list):
                entry["order"] = []
    setattr(document, "paragraph_store", paragraph_store)

    paragraph_lookup: Dict[str, str] = {}
    page_lookup: Dict[int, List[str]] = defaultdict(list)
    max_order_index = -1

    for hash_id, entry in paragraph_store.items():
        text_value = normalize_paragraph_text(entry.get("text"))
        if text_value:
            paragraph_lookup.setdefault(text_value, hash_id)
        for occurrence in entry.get("occurrences", []):
            if not isinstance(occurrence, dict):
                continue
            occ_page = occurrence.get("page")
            if isinstance(occ_page, int):
                page_lookup.setdefault(occ_page, []).append(hash_id)
        order_list = entry.get("order") or []
        if isinstance(order_list, list) and order_list:
            try:
                max_order_index = max(max_order_index, max(int(idx) for idx in order_list))
            except (TypeError, ValueError):
                continue

    paragraph_counter = {"value": max_order_index + 1}

    def _record_occurrence(hash_id: str, page: Optional[int]) -> None:
        entry = paragraph_store.get(hash_id)
        if not isinstance(entry, dict):
            return
        occurrences = entry.setdefault("occurrences", [])
        occurrences.append({"page": page, "char_span": None})
        if isinstance(page, int):
            pages = entry.setdefault("pages", [])
            if page not in pages:
                pages.append(page)
            page_lookup.setdefault(page, []).append(hash_id)
        order = entry.setdefault("order", [])
        order.append(paragraph_counter["value"])

    def _store_paragraph(text: Optional[str], page: Optional[int] = None) -> Optional[tuple[str, str]]:
        nonlocal placeholders_removed
        if not paragraph_mode or not text:
            return None
        normalized_text = normalize_paragraph_text(text)
        if not normalized_text:
            return None
        if WINDOW_PLACEHOLDER_RE.match(normalized_text):
            placeholders_removed += 1
            return None

        existing_hash = paragraph_lookup.get(normalized_text)
        if existing_hash:
            _record_occurrence(existing_hash, page)
            paragraph_counter["value"] += 1
            stored_entry = paragraph_store.get(existing_hash) or {}
            stored_text = str(stored_entry.get("text") or normalized_text)
            document.pipeline_info["paragraph_dedup_applied"] = True
            return existing_hash, stored_text

        hash_id = stable_par_hash(document.doc_id, page, normalized_text)
        paragraph_store[hash_id] = {
            "text": normalized_text,
            "page": page,
            "pages": [page] if isinstance(page, int) else [],
            "char_span": None,
            "length": len(normalized_text),
            "order": [paragraph_counter["value"]],
            "occurrences": [
                {
                    "page": page,
                    "char_span": None,
                }
            ],
        }
        paragraph_lookup[normalized_text] = hash_id
        if isinstance(page, int):
            page_lookup.setdefault(page, []).append(hash_id)
        paragraph_counter["value"] += 1
        return hash_id, normalized_text

    def _resolve_placeholder_span(span: Optional[EvidenceSpan]) -> bool:
        nonlocal placeholders_removed
        if not paragraph_mode or not isinstance(span, EvidenceSpan):
            return False
        if not span.text:
            return False
        stripped = span.text.strip()
        match = window_placeholder.match(stripped) or co_mention_placeholder.match(stripped)
        if not match:
            return False
        try:
            page_hint = int(match.group(1))
        except (TypeError, ValueError):
            page_hint = None

        candidate_hashes: List[str] = []
        if page_hint is not None and page_hint in page_lookup:
            candidate_hashes = page_lookup[page_hint]
        elif page_hint == -1 and page_lookup:
            first_page = next(iter(page_lookup))
            candidate_hashes = page_lookup.get(first_page, [])

        if not candidate_hashes:
            placeholders_removed += 1
            span.text = None
            span.hash = None
            span.paragraph_hash = None
            span.paragraph_offset = None
            return True

        hash_id = candidate_hashes[0]
        entry = paragraph_store.get(hash_id, {})
        stored_text = str(entry.get("text") or "")
        if not stored_text:
            return False

        span.page = span.page if span.page is not None else entry.get("page") or page_hint
        span.hash = span.hash or hash_id
        span.paragraph_hash = hash_id
        span.paragraph_offset = (0, len(stored_text))
        if evidence_policy == "compact":
            span.text = None
        else:
            span.text = stored_text
        _record_occurrence(hash_id, span.page)
        document.pipeline_info["paragraph_dedup_applied"] = True
        paragraph_counter["value"] += 1
        return True

    document.pipeline_info["evidence_policy"] = evidence_policy
    document.pipeline_info["keep_evidence_bank"] = keep_evidence_bank
    document.pipeline_info["paragraph_store_enabled"] = paragraph_mode
    if paragraph_requested:
        document.pipeline_info["paragraph_store_requested"] = True

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

    def compact_span(span: Optional[EvidenceSpan]) -> None:
        if not isinstance(span, EvidenceSpan):
            return
        if not paragraph_mode:
            return
        if _resolve_placeholder_span(span):
            return
        if span.text:
            stored = _store_paragraph(span.text, span.page)
            if stored:
                hash_id, stored_text = stored
                span.hash = span.hash or hash_id
                span.paragraph_hash = hash_id
                span.paragraph_offset = (0, len(stored_text))
                if evidence_policy == "compact":
                    span.text = None
                else:
                    span.text = stored_text

    if evidence_limit > 0 or paragraph_mode:
        for attr in ("recommendations", "outcomes", "figures", "key_points"):
            items = getattr(document, attr, None)
            if not items:
                continue
            for item in items:
                span = getattr(item, "evidence", None)
                if isinstance(span, EvidenceSpan):
                    if evidence_limit > 0:
                        clamp_evidence(span, evidence_limit)
                    compact_span(span)

        diag = getattr(document, "diagnostic_yield", None)
        if diag and isinstance(getattr(diag, "evidence", None), EvidenceSpan):
            if evidence_limit > 0:
                clamp_evidence(diag.evidence, evidence_limit)
            compact_span(diag.evidence)

        definitions_evidence = getattr(document, "definitions_evidence", None)
        if isinstance(definitions_evidence, EvidenceSpan):
            if evidence_limit > 0:
                clamp_evidence(definitions_evidence, evidence_limit)
            compact_span(definitions_evidence)

        diagnostic_flow = getattr(document, "diagnostic_flow", None)
        if diagnostic_flow:
            flow_evidence = getattr(diagnostic_flow, "evidence", None)
            if isinstance(flow_evidence, EvidenceSpan):
                if evidence_limit > 0:
                    clamp_evidence(flow_evidence, evidence_limit)
                compact_span(flow_evidence)

        relations_payload = getattr(document, "relations", None)
        if relations_payload:
            for relation in relations_payload:
                evidence = getattr(relation, "evidence", None)
                if isinstance(evidence, EvidenceSpan):
                    if evidence_limit > 0:
                        clamp_evidence(evidence, evidence_limit)
                    compact_span(evidence)
                elif isinstance(evidence, str):
                    truncated = truncate_text(evidence, evidence_limit) if evidence_limit > 0 else evidence
                    if paragraph_mode:
                        span = EvidenceSpan(text=truncated or evidence)
                        compact_span(span)
                        if evidence_policy != "compact":
                            span.text = truncated or evidence
                        setattr(relation, "evidence", span)
                    else:
                        setattr(relation, "evidence", truncated)

    if evidence_policy == "compact" and hasattr(document, "recommendations"):
        for rec in getattr(document, "recommendations") or []:
            if hasattr(rec, "grade_candidates"):
                rec.grade_candidates = None

    tables_dropped = 0
    if hasattr(document, "tables"):
        tables = getattr(document, "tables") or []
        cleaned_tables = []
        doc_subtype = str(getattr(document, "doc_subtype", "") or "").lower()
        guideline_doc = doc_subtype in {"guideline", "statement"}
        seen_rows: set[tuple] = set()
        for table in tables:
            is_mapping = isinstance(table, dict)
            headers = list(table.get("headers", [])) if is_mapping else list(getattr(table, "headers", []))
            rows = table.get("rows") if is_mapping else getattr(table, "rows", [])
            rows = rows or []
            flattened_headers = _flatten_headers(headers)
            header_text = " ".join(flattened_headers).lower()
            caption_text = ""
            if is_mapping:
                caption_text = str(table.get("caption") or "").lower()
            else:
                caption_text = str(getattr(table, "caption", "") or "").lower()
            preserve_table = False
            if preserve_header_tokens:
                combined_text = " ".join(filter(None, [caption_text, header_text]))
                if any(token in combined_text for token in preserve_header_tokens):
                    preserve_table = True
            if not preserve_table and preserve_summary_tables and guideline_doc and _contains_grade_columns(flattened_headers):
                preserve_table = True
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
            if preserve_table and getattr(table, "table_type", None) is None:
                if is_mapping:
                    table = dict(table)
                    if "table_type" not in table:
                        table["table_type"] = "preserved_summary"
                else:
                    if not getattr(table, "table_type", None):
                        setattr(table, "table_type", "preserved_summary")
            if tables_mode == "compact" and table_sample_rows and len(cleaned_rows) > table_sample_rows and not preserve_table:
                if is_mapping:
                    table = dict(table)
                    table["rows_truncated"] = True
                else:
                    setattr(table, "rows_truncated", True)
                cleaned_rows = cleaned_rows[:table_sample_rows]

            if is_mapping:
                updated = dict(table)
                updated["headers"] = headers
                updated["rows"] = cleaned_rows
                if truncated:
                    updated["truncated_cells"] = True
                cleaned_tables.append(updated)
            else:
                setattr(table, "headers", headers)
                setattr(table, "rows", cleaned_rows)
                if truncated:
                    setattr(table, "truncated_cells", True)
                cleaned_tables.append(table)

        if isinstance(max_tables, int) and max_tables >= 0 and len(cleaned_tables) > max_tables:
            warnings.append("table_limit_exceeded")
            drop_count = len(cleaned_tables) - max_tables
            tables_dropped += drop_count
            cleaned_tables = cleaned_tables[:max_tables]
        setattr(document, "tables", cleaned_tables)
        document.pipeline_info.setdefault("tables_original", len(tables))
        document.pipeline_info["tables_kept"] = len(cleaned_tables)
        document.pipeline_info["tables_dropped"] = tables_dropped

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

    def _aggregate_relations(items: List[object]) -> List[object]:
        if len(items) < 2:
            return items
        aggregated: Dict[tuple, object] = {}
        counts: Dict[tuple, int] = defaultdict(int)
        order: List[tuple] = []
        passthrough: List[object] = []
        for relation in items:
            is_mapping = isinstance(relation, dict)
            subject = relation.get("subject") if is_mapping else getattr(relation, "subject", None)
            predicate = relation.get("predicate") if is_mapping else getattr(relation, "predicate", None)
            obj = relation.get("object") if is_mapping else getattr(relation, "object", None)
            attrs = relation.get("attributes") if is_mapping else getattr(relation, "attributes", None)
            if not isinstance(attrs, dict):
                attrs = {}
                if is_mapping:
                    relation = dict(relation)
                    relation["attributes"] = attrs
                else:
                    setattr(relation, "attributes", attrs)
            if not subject or not predicate or not obj:
                passthrough.append(relation)
                continue
            page_window = attrs.get("page_window")
            page = attrs.get("page")
            window_label = attrs.get("window_tokens") or attrs.get("window")
            key = (subject, predicate, obj, page_window, page, window_label)
            counts[key] += 1
            if key not in aggregated:
                aggregated[key] = relation
                order.append(key)
        result: List[object] = []
        for key in order:
            relation = aggregated[key]
            count = counts.get(key, 1)
            if count > 1:
                attrs = relation["attributes"] if isinstance(relation, dict) else getattr(relation, "attributes", {})
                if not isinstance(attrs, dict):
                    attrs = {}
                    if isinstance(relation, dict):
                        relation["attributes"] = attrs
                    else:
                        setattr(relation, "attributes", attrs)
                attrs["count"] = count
            result.append(relation)
        if passthrough:
            result.extend(passthrough)
        return result

    def _limit_relations_per_pair(items: List[object], cap: int) -> tuple[List[object], bool, int]:
        counts: Dict[tuple, int] = defaultdict(int)
        limited: List[object] = []
        truncated = False
        dropped = 0
        for relation in items:
            is_mapping = isinstance(relation, dict)
            subject = relation.get("subject") if is_mapping else getattr(relation, "subject", None)
            predicate = relation.get("predicate") if is_mapping else getattr(relation, "predicate", None)
            obj = relation.get("object") if is_mapping else getattr(relation, "object", None)
            if not subject or not predicate or not obj:
                limited.append(relation)
                continue
            key = (subject, predicate, obj)
            if counts[key] >= cap:
                truncated = True
                dropped += 1
                continue
            counts[key] += 1
            limited.append(relation)
        return limited, truncated, dropped

    relations = getattr(document, "relations", None)
    if relations:
        relation_list = list(relations)
        relations_original_count = len(relation_list)
        relations_dropped = 0
        mutated = False
        if relation_mode in {"compact", "aggregated", "aggregate"}:
            relation_list = _aggregate_relations(relation_list)
            mutated = True
            document.pipeline_info["relations_mode"] = relation_mode
        if max_relations_per_pair:
            relation_list, truncated, dropped = _limit_relations_per_pair(relation_list, max_relations_per_pair)
            if truncated:
                document.pipeline_info["relations_truncated"] = True
            if dropped:
                relations_dropped += dropped
            mutated = mutated or truncated
        if max_relations and len(relation_list) > max_relations:
            dropped = len(relation_list) - max_relations
            relation_list = relation_list[:max_relations]
            warnings.append("relations_truncated")
            document.pipeline_info["relations_truncated"] = True
            relations_dropped += dropped
            mutated = True
        if mutated:
            setattr(document, "relations", relation_list)
        document.pipeline_info.setdefault("relations_original", relations_original_count)
        document.pipeline_info["relations_kept"] = len(relation_list)
        document.pipeline_info["relations_dropped"] = relations_dropped

    if not keep_evidence_bank:
        setattr(document, "evidence_bank", {})

    if paragraph_requested:
        def _collect_paragraph_refs(text: Optional[str]) -> List[str]:
            if not isinstance(text, str):
                return []
            paragraphs = [para.strip() for para in text.split("\n\n") if para.strip()]
            refs: List[str] = []
            for paragraph in paragraphs:
                stored = _store_paragraph(paragraph)
                if not stored:
                    continue
                hash_id, _ = stored
                refs.append(hash_id)
            return refs

        section_refs: Dict[str, List[str]] = {}
        sections = getattr(document, "sections", {}) or {}
        if isinstance(sections, dict):
            for name, text in sections.items():
                refs = _collect_paragraph_refs(text)
                if refs:
                    section_refs[name] = refs
        if section_refs:
            document.pipeline_info.setdefault("section_paragraph_refs", section_refs)

        additional_refs: Dict[str, List[str]] = {}
        if getattr(document, "doc_type", None) == "ifu":
            ifu_fields = [
                "product_name",
                "indications_for_use",
                "intended_use",
                "intended_user",
                "intended_patient_population",
                "contraindications",
                "warnings",
                "precautions",
                "adverse_events",
                "cautions",
                "maintenance",
                "clinical_benefits",
            ]
            for field in ifu_fields:
                value = getattr(document, field, None)
                refs: List[str] = []
                if isinstance(value, str):
                    refs.extend(_collect_paragraph_refs(value))
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            refs.extend(_collect_paragraph_refs(item))
                if refs:
                    additional_refs[field] = refs
            safety_blocks = getattr(document, "safety_blocks", []) or []
            safety_refs: List[str] = []
            for block in safety_blocks:
                text = getattr(block, "text", None)
                safety_refs.extend(_collect_paragraph_refs(text))
            if safety_refs:
                additional_refs["safety_blocks"] = safety_refs
        if additional_refs:
            document.pipeline_info.setdefault("text_field_paragraph_refs", {}).update(additional_refs)
        document.pipeline_info["paragraph_store_size"] = len(paragraph_store)

    if paragraph_mode:
        document.pipeline_info["paragraph_store_size"] = len(paragraph_store)
        setattr(document, "paragraph_store", paragraph_store)

    document.pipeline_info["window_placeholders_removed"] = placeholders_removed

    if max_json_bytes:
        try:
            payload = document.model_dump(mode="json", exclude_none=True)
            approx_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        except Exception:  # pragma: no cover - defensive serialization guard
            approx_size = 0
        if approx_size and approx_size > max_json_bytes:
            warnings.append("max_json_bytes_exceeded")
            document.pipeline_info["max_json_bytes_exceeded"] = True
            document.pipeline_info["approx_size_bytes"] = approx_size

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


__all__ = ["PipelineOutcome", "run_extract", "write_failure_artifact"]
