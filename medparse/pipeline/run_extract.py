"""High-level extraction runner with completeness guards and caching."""

from __future__ import annotations

import json
from copy import deepcopy
import time
from dataclasses import dataclass, field
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, Type, cast

from collections import defaultdict
import yaml

from medparse.chunking import build_document_chunks
from medparse.config import ExtractionConfig, ExtractionProfile
from medparse.extractors.article import extract_article
from medparse.extractors.guideline import extract_guideline
from medparse.extractors.ifu import extract_ifu
from medparse.ifu.safety_thresholds import expected_safety_with_source
from medparse.ifu.frontmatter import extract_front_matter
from medparse.ifu.revision import sync_revision_status
from medparse.extractors.textbook import extract_textbook_chapter
from medparse.extract.utils import load_pages
from medparse.ingest.models import PageData
from medparse.schema.article import ArticleDocument
from medparse.schema.common import BaseDocument, EvidenceSpan, SizeGuards
from medparse.schema.ifu import IFUDocument
from medparse.schema.textbook import TextbookChapterDocument
from medparse.utils.cache import compute_cache_key, load_cache_entry, store_cache_entry
from medparse.emit.evidence_bank import EvidenceBank
from medparse.second_pass import SecondPassContext, run_second_pass
from medparse.second_pass.types import SecondPassMode, SecondPassReport
from medparse.validate.ats_yield import validate_ats_yield
from medparse.validate.validators import ValidationIssue, validate_document
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

_SHARED_CHUNKING_DEFAULTS: Optional[Dict[str, Any]] = None


def _deep_update(base: Dict[str, object], overrides: Dict[str, object]) -> Dict[str, object]:
    """Recursively merge ``overrides`` into ``base`` and return new dictionary."""

    result: Dict[str, object] = deepcopy(base)
    for key, value in overrides.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_update(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result


def _resolve_chunking_settings(emit_config: Dict[str, Any] | None, cli_mode: Optional[str]) -> Dict[str, Any]:
    """Return normalized chunking settings from emit config + CLI mode."""

    chunking_block: Dict[str, Any] = _load_shared_chunking_defaults()
    if isinstance(emit_config, dict):
        block = emit_config.get("chunking")
        if isinstance(block, dict):
            chunking_block.update(block)
    config_enabled = bool(chunking_block.get("enabled"))
    cli_normalized = (cli_mode or "").strip().lower()
    if cli_normalized not in {"smart", "off", ""}:
        cli_normalized = "smart"
    # When CLI mode is omitted we respect config; when explicitly "off" we disable.
    cli_enabled = cli_normalized != "off"
    enabled = config_enabled and cli_enabled
    settings = {
        "enabled": enabled,
        "mode": "smart" if enabled else "off",
        "token_min": chunking_block.get("token_min", 200),
        "token_max": chunking_block.get("token_max", 500),
        "overlap_ratio": chunking_block.get("overlap_ratio", 0.15),
        "enable_c99": chunking_block.get("enable_c99", False),
        "max_chunks_per_doc": chunking_block.get("max_chunks_per_doc", 0),
        "min_tokens_merge_threshold": chunking_block.get("min_tokens_merge_threshold", 0),
        "column_mode": str(chunking_block.get("column_mode", "off") or "off").lower(),
    }
    if not config_enabled:
        settings["reason"] = "config_disabled"
    elif not cli_enabled:
        settings["reason"] = "cli_disabled"
    return settings


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


def _register_research_outcome_evidence(
    document: BaseDocument,
    bank: EvidenceBank,
    paragraph_store: Dict[str, Dict[str, object]],
) -> None:
    outcomes = getattr(document, "research_outcomes", None)
    if not outcomes:
        return

    def _register_ids(evidence_ids: Sequence[str]) -> None:
        for evidence_hash in evidence_ids:
            if not evidence_hash:
                continue
            entry = paragraph_store.get(evidence_hash)
            if not isinstance(entry, dict):
                continue
            span = EvidenceSpan(
                page=entry.get("page"),
                confidence=0.85,
            )
            span.hash = evidence_hash
            span.paragraph_hash = evidence_hash
            bank.add_evidence(span)

    _register_ids(getattr(outcomes, "evidence_ids", []) or [])

    for metric in _iter_research_metrics(outcomes):
        _register_ids(getattr(metric, "evidence_ids", []) or [])

    for arm in getattr(outcomes, "arms", []) or []:
        _register_ids(getattr(arm, "evidence_ids", []) or [])
        for attr in ("diagnostic_accuracy", "diagnostic_yield"):
            metric = getattr(arm, attr, None)
            if metric:
                _register_ids(getattr(metric, "evidence_ids", []) or [])
        for metric in getattr(arm, "complications", {}).values():
            _register_ids(getattr(metric, "evidence_ids", []) or [])


def _iter_research_metrics(outcomes: object) -> List[object]:
    metrics: List[object] = []
    for attr in ("diagnostic_accuracy", "diagnostic_yield"):
        metric = getattr(outcomes, attr, None)
        if metric:
            metrics.append(metric)
    for metric in getattr(outcomes, "complications", {}).values():
        if metric:
            metrics.append(metric)
    return metrics


def _build_chunks_if_enabled(
    document: BaseDocument,
    pages: Sequence[PageData],
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    """Run smart chunker when enabled and capture metrics."""

    chunk_settings = settings or {}
    mode = str(chunk_settings.get("mode") or "smart")
    chunk_metrics: Dict[str, Any] = {
        "enabled": False,
        "mode": mode,
    }
    if not chunk_settings.get("enabled"):
        if chunk_settings.get("reason"):
            chunk_metrics["reason"] = chunk_settings["reason"]
        return chunk_metrics

    try:
        chunks, metrics = build_document_chunks(
            document,
            pages,
            settings=chunk_settings,
            mode=mode,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        LOGGER.exception("Chunking failed: %s", exc)
        chunk_metrics.update(
            {
                "reason": f"error:{exc.__class__.__name__}",
                "error": str(exc),
            }
        )
        return chunk_metrics

    document.chunks = chunks
    chunk_metrics.update(dict(metrics))
    chunk_metrics["mode"] = mode
    chunk_metrics["enabled"] = bool(chunks)
    return chunk_metrics


def _research_metric_has_value(metric: Optional[object]) -> bool:
    if metric is None:
        return False
    percent = getattr(metric, "percent", None)
    if percent is not None:
        return True
    ci_95 = getattr(metric, "ci_95", None)
    if ci_95:
        return True
    p_value = getattr(metric, "p_value", None)
    if p_value is not None:
        return True
    n_over_n = getattr(metric, "n_over_N", None) or getattr(metric, "n_over_n", None)
    if n_over_n and (getattr(n_over_n, "numerator", None) is not None or getattr(n_over_n, "denominator", None) is not None):
        return True
    evidence_ids = getattr(metric, "evidence_ids", None)
    if evidence_ids:
        return True
    return False


def _research_accuracy_present(outcomes: Optional[object]) -> bool:
    if outcomes is None:
        return False
    if _research_metric_has_value(getattr(outcomes, "diagnostic_accuracy", None)):
        return True
    for arm in getattr(outcomes, "arms", []) or []:
        if _research_metric_has_value(getattr(arm, "diagnostic_accuracy", None)):
            return True
    return False


def _research_yield_present(outcomes: Optional[object]) -> bool:
    if outcomes is None:
        return False
    if _research_metric_has_value(getattr(outcomes, "diagnostic_yield", None)):
        return True
    for arm in getattr(outcomes, "arms", []) or []:
        if _research_metric_has_value(getattr(arm, "diagnostic_yield", None)):
            return True
    return False


SECTION_GUARD_HINTS = (
    "too few sections",
    "too few populated sections",
    "insufficient structural signals",
    "no sections parsed",
)


def _normalize_validator_issues(
    document: BaseDocument,
    issues: Sequence[ValidationIssue],
) -> List[ValidationIssue]:
    if not isinstance(document, ArticleDocument):
        return list(issues)
    subtype = (getattr(document, "doc_subtype", "") or "").lower()
    if subtype not in {"editorial_or_economics", "statement"}:
        return list(issues)
    adjusted: List[ValidationIssue] = []
    for issue in issues:
        if issue.severity == "error" and _is_section_guard_issue(issue.message):
            adjusted.append(ValidationIssue(issue.message, severity="warning"))
        else:
            adjusted.append(issue)
    return adjusted


def _is_section_guard_issue(message: str) -> bool:
    lowered = (message or "").lower()
    return any(hint in lowered for hint in SECTION_GUARD_HINTS)


def _run_validation(document: BaseDocument) -> List[ValidationIssue]:
    if isinstance(document, IFUDocument):
        sync_revision_status(document)
    return _normalize_validator_issues(document, validate_document(document))


def _inject_metadata_sources(document: BaseDocument, metadata_sources: Dict[str, Any]) -> None:
    if not metadata_sources:
        return
    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    existing = pipeline_info.get("metadata_sources")
    merged = dict(metadata_sources)
    if isinstance(existing, dict):
        merged.update(existing)
    pipeline_info["metadata_sources"] = merged
    document.pipeline_info = pipeline_info


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
        sample_pages = int(auto_block.get("sample_pages", 3) or 3)
        metrics = _estimate_pdf_density(pdf_path, sample_pages=sample_pages)
        avg_chars = float(metrics.get("avg_chars_per_page", 0.0))
        image_ratio = float(metrics.get("image_ratio", 0.0))
        page_count = float(metrics.get("page_count", 0.0))

        char_threshold = float(auto_block.get("char_density_threshold", auto_block.get("char_threshold", 900)))
        image_threshold = float(auto_block.get("image_density_threshold", auto_block.get("image_threshold", 0.8)))
        low_density_threshold = float(auto_block.get("low_density_threshold", 100))
        low_density_image_threshold = float(auto_block.get("low_density_image_threshold", 0.5))
        large_doc_pages = float(auto_block.get("large_doc_pages", 120))
        prefer_engine = str(auto_block.get("prefer", text_engine or "pymupdf"))
        fallback = str(auto_block.get("fallback", fallback_engine or "pdfplumber"))

        primary = prefer_engine
        low_density_triggered = False
        if avg_chars <= low_density_threshold and image_ratio >= low_density_image_threshold:
            primary = fallback
            low_density_triggered = True
        elif avg_chars < char_threshold or image_ratio >= image_threshold:
            primary = fallback
        elif page_count >= large_doc_pages:
            primary = prefer_engine

        runtime_info["density_sample_pages"] = sample_pages
        runtime_info["avg_chars_per_page"] = avg_chars
        runtime_info["image_ratio"] = image_ratio
        if low_density_triggered:
            runtime_info["low_density_triggered"] = True

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
class PageLoadOutcome:
    pages: List[PageData]
    ocr_pages: List[int]
    engines_used: List[str]
    engines_consumed: int
    streaming_enabled: bool
    batches: int
    batches_failed: int
    engine_timeouts: Dict[str, float]
    complete: bool
    failure_reason: Optional[str] = None


def _resolve_streaming_settings(config: PipelineConfig) -> Dict[str, Any]:
    if config.doc_type != "ifu":
        return {
            "enabled": False,
            "page_threshold": 0,
            "pages_per_batch": 0,
            "max_failed_batches": 0,
        }
    ifu_settings = config.ifu if isinstance(config.ifu, dict) else {}
    extract_block = ifu_settings.get("extract") if isinstance(ifu_settings, dict) else {}
    if not isinstance(extract_block, dict):
        extract_block = {}
    long_doc_block = extract_block.get("long_doc") if isinstance(extract_block.get("long_doc"), dict) else {}
    streaming_block = long_doc_block if isinstance(long_doc_block, dict) else {}
    enabled = bool(streaming_block.get("streaming"))
    page_threshold = int(streaming_block.get("page_threshold", 250) or 250)
    pages_per_batch = int(streaming_block.get("pages_per_batch", 40) or 40)
    max_failed_batches = int(streaming_block.get("max_failed_batches", 5) or 5)
    per_page_timeout_s = float(streaming_block.get("per_page_timeout_s", streaming_block.get("per_page_timeout", 0)) or 0)
    return {
        "enabled": enabled,
        "page_threshold": max(1, page_threshold),
        "pages_per_batch": max(5, pages_per_batch),
        "max_failed_batches": max(1, max_failed_batches),
        "per_page_timeout_s": per_page_timeout_s if per_page_timeout_s > 0 else 0,
    }


def _load_document_pages(
    pdf_path: Path,
    *,
    engines: Sequence[str],
    start_index: int,
    total_pages: int,
    max_pages: Optional[int],
    ocr_enabled: bool,
    engine_timeouts: Dict[str, float],
    streaming_settings: Dict[str, Any],
) -> PageLoadOutcome:
    streaming_enabled = False
    if streaming_settings.get("enabled"):
        threshold = int(streaming_settings.get("page_threshold", 250) or 250)
        streaming_enabled = bool(total_pages and total_pages >= threshold)
        if not streaming_enabled and max_pages:
            streaming_enabled = max_pages >= threshold

    if streaming_enabled:
        return _stream_document_pages(
            pdf_path,
            engines=engines,
            start_index=start_index,
            total_pages=total_pages,
            max_pages=max_pages,
            ocr_enabled=ocr_enabled,
            engine_timeouts=engine_timeouts,
            streaming_settings=streaming_settings,
        )

    return _load_pages_single_engine(
        pdf_path,
        engines=engines,
        start_index=start_index,
        max_pages=max_pages,
        ocr_enabled=ocr_enabled,
        engine_timeouts=engine_timeouts,
    )


def _load_pages_single_engine(
    pdf_path: Path,
    *,
    engines: Sequence[str],
    start_index: int,
    max_pages: Optional[int],
    ocr_enabled: bool,
    engine_timeouts: Dict[str, float],
) -> PageLoadOutcome:
    engine = engines[start_index]
    load_start = time.perf_counter()
    try:
        pages = load_pages(
            pdf_path,
            engine=engine,
            max_pages=max_pages,
            ocr=ocr_enabled,
            start_page=1,
        )
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed to load pages with engine=%s: %s", engine, exc)
        return PageLoadOutcome(
            pages=[],
            ocr_pages=[],
            engines_used=[engine],
            engines_consumed=1,
            streaming_enabled=False,
            batches=0,
            batches_failed=1,
            engine_timeouts={},
            complete=False,
            failure_reason=f"load_failed:{engine}",
        )

    duration = time.perf_counter() - load_start
    ocr_pages = [page.number for page in pages if getattr(page, "ocr_applied", False)]
    timeouts_triggered: Dict[str, float] = {}
    limit = engine_timeouts.get(engine)
    if limit and duration > limit:
        timeouts_triggered[engine] = duration

    return PageLoadOutcome(
        pages=list(pages),
        ocr_pages=ocr_pages,
        engines_used=[engine],
        engines_consumed=1,
        streaming_enabled=False,
        batches=1,
        batches_failed=0,
        engine_timeouts=timeouts_triggered,
        complete=True,
        failure_reason=None,
    )


def _stream_document_pages(
    pdf_path: Path,
    *,
    engines: Sequence[str],
    start_index: int,
    total_pages: int,
    max_pages: Optional[int],
    ocr_enabled: bool,
    engine_timeouts: Dict[str, float],
    streaming_settings: Dict[str, Any],
) -> PageLoadOutcome:
    pages: List[PageData] = []
    ocr_pages: List[int] = []
    batches = 0
    failed_batches = 0
    engines_used: List[str] = []
    engine_timeouts_triggered: Dict[str, float] = {}
    current_index = start_index
    engines_consumed = 1
    pages_per_batch = max(1, int(streaming_settings.get("pages_per_batch", 40) or 40))
    max_failed_batches = max(1, int(streaming_settings.get("max_failed_batches", 5) or 5))
    per_page_timeout_s = float(streaming_settings.get("per_page_timeout_s", 0) or 0)

    target_final_page = 0
    if max_pages:
        target_final_page = int(max_pages)
        if total_pages:
            target_final_page = min(int(total_pages), target_final_page)
    elif total_pages:
        target_final_page = int(total_pages)

    start_page = 1
    complete = False
    consecutive_failures = 0

    while True:
        if target_final_page and start_page > target_final_page:
            complete = True
            break
        if current_index >= len(engines):
            break
        engine = engines[current_index]

        remaining = None
        if target_final_page:
            remaining = target_final_page - start_page + 1
            if remaining <= 0:
                complete = True
                break
        requested = pages_per_batch if remaining is None else min(pages_per_batch, remaining)
        batch_start = time.perf_counter()
        try:
            batch_pages = load_pages(
                pdf_path,
                engine=engine,
                max_pages=requested,
                ocr=ocr_enabled,
                start_page=start_page,
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning(
                "Streaming batch failed engine=%s start_page=%s count=%s: %s",
                engine,
                start_page,
                requested,
                exc,
            )
            failed_batches += 1
            consecutive_failures += 1
            start_page += requested
            if consecutive_failures >= max_failed_batches:
                current_index += 1
                engines_consumed = max(engines_consumed, current_index - start_index + 1)
                consecutive_failures = 0
            continue

        duration = time.perf_counter() - batch_start
        if not batch_pages:
            if target_final_page:
                failed_batches += 1
                start_page += requested
                continue
            complete = True
            break

        consecutive_failures = 0
        batches += 1
        if engine not in engines_used:
            engines_used.append(engine)
        pages.extend(batch_pages)
        ocr_pages.extend([page.number for page in batch_pages if getattr(page, "ocr_applied", False)])
        last_page_number = batch_pages[-1].number or (start_page + len(batch_pages) - 1)
        start_page = last_page_number + 1

        timeout_limit = engine_timeouts.get(engine)
        if per_page_timeout_s > 0:
            batch_pages_count = len(batch_pages) or requested or 1
            per_batch_limit = per_page_timeout_s * max(1, batch_pages_count)
            if per_batch_limit and (timeout_limit is None or per_batch_limit < timeout_limit):
                timeout_limit = per_batch_limit
        if timeout_limit and duration > timeout_limit:
            engine_timeouts_triggered[engine] = duration
            current_index += 1
            engines_consumed = max(engines_consumed, current_index - start_index + 1)
        if not target_final_page and len(batch_pages) < requested:
            complete = True
            break

    if not engines_used and start_index < len(engines):
        engines_used.append(engines[start_index])

    reason = None
    if not pages:
        reason = "streaming_no_pages"

    return PageLoadOutcome(
        pages=pages,
        ocr_pages=ocr_pages,
        engines_used=engines_used,
        engines_consumed=max(1, min(len(engines) - start_index, engines_consumed)),
        streaming_enabled=True,
        batches=batches,
        batches_failed=failed_batches,
        engine_timeouts=engine_timeouts_triggered,
        complete=complete,
        failure_reason=reason,
    )


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
    second_pass: Dict[str, Any] = field(default_factory=dict)

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
        shared_second_pass_path = path.parent / "_shared" / "second_pass.yaml"
        if not shared_second_pass_path.exists():
            raise FileNotFoundError(f"Second-pass configuration missing: {shared_second_pass_path}")
        try:
            raw_second_pass = yaml.safe_load(shared_second_pass_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Failed to parse second-pass config at {shared_second_pass_path}: {exc}") from exc

        if isinstance(raw_second_pass, dict) and "second_pass" in raw_second_pass:
            shared_second_pass = raw_second_pass.get("second_pass") or {}
        else:
            shared_second_pass = raw_second_pass

        if not isinstance(shared_second_pass, dict):
            raise ValueError(f"Second-pass configuration malformed at {shared_second_pass_path}")

        second_pass_config = deepcopy(shared_second_pass)
        overrides = data.get("second_pass")
        if isinstance(overrides, dict):
            second_pass_config = _deep_update(second_pass_config, overrides)
        elif isinstance(overrides, str) and overrides.strip():
            second_pass_config = dict(second_pass_config)
            second_pass_config["enabled"] = overrides.strip().lower()

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
            second_pass=second_pass_config,
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
    metrics: Dict[str, Any]
    engine: str
    mode: str
    cache_used: bool = False
    failure_reason: Optional[str] = None
    ocr_pages: List[int] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    emit_settings: Dict[str, Any] = field(default_factory=dict)
    second_pass_report: Optional[SecondPassReport] = None
    validator_issues: List[ValidationIssue] = field(default_factory=list)

    def to_payload(self) -> Dict[str, object]:
        if self.success and self.document is not None:
            payload = self.document.model_dump(mode="json", exclude_none=True)

            structured_outcomes = payload.get("outcomes")
            research_outcomes = payload.pop("research_outcomes", None)
            if research_outcomes:
                if not isinstance(structured_outcomes, list):
                    structured_outcomes = structured_outcomes or []
                payload["outcomes"] = {
                    "structured": structured_outcomes or [],
                    "research": research_outcomes,
                }
            elif structured_outcomes is None:
                payload["outcomes"] = []

            doc_subtype = payload.get("doc_subtype")
            if doc_subtype not in {"research_diagnostic", "research_therapeutic"}:
                if "outcomes" in payload:
                    payload.pop("outcomes", None)
                    emit_pruned = self.metrics.setdefault("emit_pruned", [])
                    if "outcomes" not in emit_pruned:
                        emit_pruned.append("outcomes")

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
            if self.second_pass_report:
                pipeline_metadata["second_pass"] = self.second_pass_report.as_metadata()
            if self.validator_issues:
                info_messages = [issue.message for issue in self.validator_issues if issue.severity == "info"]
                pipeline_metadata["validators"] = {
                    "passed": not any(issue.severity == "error" for issue in self.validator_issues),
                    "warnings": [issue.message for issue in self.validator_issues if issue.severity == "warning"],
                    "errors": [issue.message for issue in self.validator_issues if issue.severity == "error"],
                }
                if info_messages:
                    pipeline_metadata["validators"]["info"] = info_messages
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

    _register_research_outcome_evidence(document, bank, paragraph_store)

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
        "source_file": str(doc_path),
        "failure_reason": f"{exc.__class__.__name__}: {exc}",
        "issues": [stage],
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


def _sync_second_pass_summary(
    document: BaseDocument,
    report: SecondPassReport,
    metrics: Dict[str, Any],
) -> bool:
    """Propagate second-pass details onto the document pipeline info and metrics."""

    pipeline_info = getattr(document, "pipeline_info", {}) or {}
    if not isinstance(pipeline_info, dict):
        pipeline_info = {}
    summary = report.summary
    applied_names = list(summary.applied)
    reasons = list(summary.reasons)
    modifications = dict(summary.modifications)

    bucket = pipeline_info.setdefault("second_pass", {})
    bucket["mode"] = report.mode
    bucket["runtime_ms"] = report.runtime_ms
    bucket["patches_attempted"] = [result.name for result in report.patch_results]
    bucket["patches_applied"] = applied_names
    bucket["applied"] = applied_names
    bucket["reasons"] = reasons
    bucket["modifications"] = modifications
    bucket["diff_summary"] = dict(report.diff_summary)
    if report.notes:
        bucket["notes"] = list(report.notes)
    if report.skipped:
        bucket["skipped"] = True

    document.pipeline_info = pipeline_info

    metrics["second_pass"] = {
        "mode": report.mode,
        "applied": applied_names,
        "reasons": reasons,
        "modifications": modifications,
    }
    metrics["second_pass_applied"] = bool(applied_names)
    metrics["second_pass_patches"] = applied_names
    metrics["second_pass_reasons"] = reasons
    metrics["second_pass_modifications"] = modifications

    patch_summaries: List[Dict[str, object]] = []
    for result in report.patch_results:
        if not result.applied and not result.modifications:
            continue
        detail: Dict[str, object] = {"name": result.name}
        if result.modifications:
            for key, value in result.modifications.items():
                try:
                    detail[key] = int(value)
                except (TypeError, ValueError):
                    continue
        if result.reasons:
            detail["reasons"] = list(result.reasons)
        patch_summaries.append(detail)
    if patch_summaries:
        metrics["patches"] = patch_summaries
        bucket["patch_summaries"] = patch_summaries

    return bool(applied_names)


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
    second_pass_mode: SecondPassMode = "auto",
    chunking_mode: Optional[str] = None,
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

    chunking_settings = _resolve_chunking_settings(config.emit, chunking_mode)
    column_mode_active = False
    if config.doc_type == "ifu":
        ifu_settings = config.ifu if isinstance(config.ifu, dict) else {}
        column_pref = str((ifu_settings.get("column_mode") or "off")).lower()
        column_mode_active = bool(chunking_settings.get("enabled")) or column_pref == "auto"
        if isinstance(config.ifu, dict):
            config.ifu["_column_mode_active"] = column_mode_active
        chunking_settings["column_mode"] = "auto" if column_mode_active else "off"
    else:
        chunking_settings.setdefault("column_mode", "off")

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

    second_pass_config = config.second_pass or {}
    default_second_pass_mode = "auto"
    if isinstance(second_pass_config, dict) and isinstance(second_pass_config.get("enabled"), str):
        default_second_pass_mode = str(second_pass_config["enabled"]).lower()
    requested_second_pass_mode = str(second_pass_mode or default_second_pass_mode).lower()
    if requested_second_pass_mode not in {"off", "auto", "always"}:
        requested_second_pass_mode = default_second_pass_mode if default_second_pass_mode in {"off", "auto", "always"} else "auto"
    active_second_pass_mode = cast(SecondPassMode, requested_second_pass_mode)
    max_second_pass_runtime = 2500
    if isinstance(second_pass_config, dict) and isinstance(second_pass_config.get("max_runtime_ms"), int):
        max_second_pass_runtime = max(250, int(second_pass_config["max_runtime_ms"]))

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
    base_metadata["second_pass_mode"] = active_second_pass_mode
    if engine_timeouts:
        base_metadata["engine_timeouts"] = dict(engine_timeouts)
    if config.doc_type == "ifu":
        runtime_info = config.ifu.get("_engine_runtime") if isinstance(config.ifu, dict) else None
        if isinstance(runtime_info, dict):
            base_metadata["ifu_engine_mode"] = runtime_info.get("mode")
            base_metadata["ifu_engine_source"] = runtime_info.get("source")
            if runtime_info.get("override_key"):
                base_metadata["ifu_engine_override_key"] = runtime_info.get("override_key")
            if "avg_chars_per_page" in runtime_info:
                base_metadata["ifu_density_avg_chars"] = runtime_info.get("avg_chars_per_page")
            if "image_ratio" in runtime_info:
                base_metadata["ifu_density_image_ratio"] = runtime_info.get("image_ratio")
            if runtime_info.get("low_density_triggered"):
                base_metadata["ifu_low_density_triggered"] = True
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
            _inject_metadata_sources(document, dict(config.metadata_sources or {}))
            metrics = dict(cached_entry.get("metrics", {}))
            paragraph_store = getattr(document, "paragraph_store", {}) or {}
            validator_issues: List[ValidationIssue] = []
            if extraction_config.should_validate():
                validator_issues = _run_validation(document)
            second_pass_report: Optional[SecondPassReport] = None
            applied_any = False
            if active_second_pass_mode != "off":
                cache_second_pass_context = SecondPassContext(
                    validation_issues=list(validator_issues),
                    paragraph_store=dict(paragraph_store) if isinstance(paragraph_store, dict) else {},
                    evidence_bank=dict(getattr(document, "evidence_bank", {}) or {}),
                    profile=extraction_config.profile.value,
                    engines_tried=list(engines),
                    emit_policies=dict(config.emit or {}),
                    config=second_pass_config if isinstance(second_pass_config, dict) else {},
                    mode=active_second_pass_mode,
                    doc_metrics=dict(metrics),
                    max_runtime_ms=max_second_pass_runtime,
                )
                document, second_pass_report = run_second_pass(document, cache_second_pass_context)
                applied_any = _sync_second_pass_summary(document, second_pass_report, metrics)
                metrics.update(_document_metrics(document))
                needs_revalidation = applied_any or (second_pass_report.requires_revalidation if second_pass_report else False)
                if needs_revalidation and extraction_config.should_validate():
                    validator_issues = _run_validation(document)
            else:
                metrics["second_pass"] = {
                    "mode": active_second_pass_mode,
                    "applied": [],
                    "reasons": [],
                    "modifications": {},
                }
                metrics["second_pass_applied"] = False
                metrics["second_pass_patches"] = []
                metrics["second_pass_reasons"] = []
                metrics["second_pass_modifications"] = {}
                pipeline_info = getattr(document, "pipeline_info", {}) or {}
                if not isinstance(pipeline_info, dict):
                    pipeline_info = {}
                bucket = pipeline_info.setdefault("second_pass", {})
                bucket.clear()
                bucket.update(
                    {
                        "mode": active_second_pass_mode,
                        "applied": [],
                        "patches_applied": [],
                        "reasons": [],
                        "modifications": {},
                        "diff_summary": {},
                        "runtime_ms": 0,
                        "patches_attempted": [],
                    }
                )
                document.pipeline_info = pipeline_info
            metrics["engine_selected"] = cached_engine or engines[0]
            metrics["engines_tried"] = list(engines)
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
                second_pass_report=second_pass_report,
                validator_issues=list(validator_issues),
            )

    last_metrics: Dict[str, Any] = {}
    last_engine = engines[0]
    last_ocr_pages: List[int] = []
    failure_reason: Optional[str] = None
    last_metadata: Dict[str, Any] = dict(base_metadata)
    last_second_pass_report: Optional[SecondPassReport] = None
    last_validator_issues: List[ValidationIssue] = []


    last_metrics: Dict[str, Any] = {}
    last_engine = engines[0]
    last_ocr_pages: List[int] = []
    failure_reason: Optional[str] = None
    last_metadata: Dict[str, Any] = dict(base_metadata)
    last_second_pass_report: Optional[SecondPassReport] = None
    last_validator_issues: List[ValidationIssue] = []

    streaming_settings = _resolve_streaming_settings(config)
    preview_limit = None if force_deep else config.max_preview_pages
    idx = 0
    validator_issues: List[ValidationIssue] = []

    while idx < len(engines):
        base_engine = engines[idx]
        LOGGER.info(
            "Starting extraction: doc_type=%s engine=%s profile=%s",
            config.doc_type,
            base_engine,
            extraction_config.profile.value,
        )

        start = time.time()
        load_outcome = _load_document_pages(
            pdf_path,
            engines=engines,
            start_index=idx,
            total_pages=total_pages,
            max_pages=preview_limit,
            ocr_enabled=ocr_enabled,
            engine_timeouts=engine_timeouts,
            streaming_settings=streaming_settings,
        )
        engines_consumed = max(1, load_outcome.engines_consumed)
        idx += engines_consumed
        engines_used = load_outcome.engines_used or [base_engine]
        engine = engines_used[-1]
        pages = load_outcome.pages
        ocr_pages = list(load_outcome.ocr_pages)

        if not pages:
            LOGGER.warning(
                "Page loading failed for engine=%s (consumed=%d) reason=%s",
                engine,
                engines_consumed,
                load_outcome.failure_reason,
            )
            last_metrics = {
                "engines_tried": list(dict.fromkeys(engines_used)),
                "engine_selected": engine,
            }
            last_engine = engine
            last_ocr_pages = ocr_pages
            failure_reason = load_outcome.failure_reason or "pages_not_loaded"
            last_metadata = dict(base_metadata)
            warnings_bucket = last_metadata.setdefault("threshold_warnings", [])
            if failure_reason not in warnings_bucket:
                warnings_bucket.append(failure_reason)
            last_second_pass_report = None
            last_validator_issues = []
            continue

        document = extractor(
            pdf_path,
            engine=engine,
            page_limit=preview_limit,
            pages=pages,
            config=extraction_config,
        )
        _inject_metadata_sources(document, dict(config.metadata_sources or {}))
        duration = time.time() - start

        metrics = _compute_metrics(pages, total_pages, duration)
        metrics.update(_document_metrics(document))
        document.pipeline_info.setdefault("extracted_chars", metrics.get("extracted_chars"))
        pipeline_info = getattr(document, "pipeline_info", {}) or {}
        extracted_chars = int(metrics.get("extracted_chars") or 0)
        if extracted_chars == 0:
            LOGGER.warning(
                "Engine %s produced zero characters; attempting fallback engine if available.",
                engine,
            )
            metrics["engine_selected"] = engine
            metrics["engines_tried"] = list(dict.fromkeys(engines_used))
            last_metrics = metrics
            last_engine = engine
            last_ocr_pages = ocr_pages
            zero_warning = f"{engine}_zero_chars"
            metadata_with_zero = dict(base_metadata)
            zero_list = metadata_with_zero.setdefault("threshold_warnings", [])
            if zero_warning not in zero_list:
                zero_list.append(zero_warning)
            last_metadata = metadata_with_zero
            failure_reason = zero_warning
            last_second_pass_report = None
            last_validator_issues = []
            continue
        if bool(document.pipeline_info.get("paragraph_dedup_applied")):
            metrics["paragraph_dedup_applied"] = True
        if bool(document.pipeline_info.get("text_repair_applied")):
            metrics["text_repair_applied"] = True
        emit_warnings: List[str] = []
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

        emit_warnings = _apply_emit_constraints(document, config.emit, policy_source=emit_policy_source) or []

        chunk_metrics = _build_chunks_if_enabled(document, pages, chunking_settings)
        pipeline_info["chunking"] = chunk_metrics
        metrics["chunking"] = chunk_metrics

        metrics["engines_tried"] = list(dict.fromkeys(engines_used))
        metrics["engine_selected"] = engine
        if load_outcome.streaming_enabled:
            streaming_payload = {
                "enabled": True,
                "batches": load_outcome.batches,
                "batches_failed": load_outcome.batches_failed,
                "pages_per_batch": streaming_settings.get("pages_per_batch"),
                "per_page_timeout_s": streaming_settings.get("per_page_timeout_s") or 0,
            }
            metrics["streaming_fallback"] = streaming_payload
            pipeline_info["streaming_fallback"] = streaming_payload
        if load_outcome.engine_timeouts:
            metrics.setdefault("engine_timeouts", {}).update(load_outcome.engine_timeouts)
            existing_timeouts = pipeline_info.get("engine_timeouts_triggered")
            if isinstance(existing_timeouts, dict):
                existing_timeouts.update(load_outcome.engine_timeouts)
            else:
                pipeline_info["engine_timeouts_triggered"] = dict(load_outcome.engine_timeouts)
        document.pipeline_info = pipeline_info

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
            last_second_pass_report = None
            last_validator_issues = []
            timeout_bucket = pipeline_info.setdefault("engine_timeouts_triggered", {})
            if isinstance(timeout_bucket, dict):
                timeout_bucket[engine] = duration
            continue

        # Build evidence bank for deduplication and size reduction
        size_guards = SizeGuards(**(config.size_guards or {}))
        evidence_bank = _build_evidence_bank(document, size_guards)
        document.evidence_bank = evidence_bank.get_bank()

        cache_metadata = dict(base_metadata)
        cache_metadata.setdefault("engines_tried", []).extend(metrics["engines_tried"])

        second_pass_report: Optional[SecondPassReport] = None
        applied_any = False
        if active_second_pass_mode != "off":
            paragraph_store = dict(getattr(document, "paragraph_store", {}) or {})
            second_pass_context = SecondPassContext(
                validation_issues=list(validator_issues),
                paragraph_store=paragraph_store,
                evidence_bank=dict(document.evidence_bank or {}),
                profile=extraction_config.profile.value,
                engines_tried=list(engines),
                emit_policies=dict(config.emit or {}),
                config=second_pass_config if isinstance(second_pass_config, dict) else {},
                mode=active_second_pass_mode,
                doc_metrics=dict(metrics),
                max_runtime_ms=max_second_pass_runtime,
            )
            document, second_pass_report = run_second_pass(document, second_pass_context)
            applied_any = _sync_second_pass_summary(document, second_pass_report, metrics)
            metrics.update(_document_metrics(document))
            needs_revalidation = applied_any or (second_pass_report.requires_revalidation if second_pass_report else False)
            if needs_revalidation and extraction_config.should_validate():
                validator_issues = _run_validation(document)
        else:
            metrics["second_pass"] = {
                "mode": active_second_pass_mode,
                "applied": [],
                "reasons": [],
                "modifications": {},
            }
            metrics["second_pass_applied"] = False

        combined_warnings = list(dict.fromkeys(issue.message for issue in validator_issues))
        if emit_warnings:
            combined_warnings.extend(emit_warnings)
        combined_warnings = list(dict.fromkeys(combined_warnings))
        meets_thresholds, threshold_warnings = _meets_thresholds(
            config,
            metrics,
            document=document,
        )
        combined_warnings.extend(threshold_warnings)

        if meets_thresholds:
            warnings_payload = list(dict.fromkeys(combined_warnings))
            cache_metadata["threshold_warnings"] = warnings_payload
            if cache_enabled:
                _store_success_in_cache(
                    cache_key,
                    config.doc_type,
                    document,
                    metrics,
                    engine,
                    extraction_config.profile.value,
                    warnings_payload,
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
                warnings=warnings_payload,
                metadata=dict(base_metadata),
                emit_settings=config.emit,
                second_pass_report=second_pass_report,
                validator_issues=list(validator_issues),
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
        last_second_pass_report = second_pass_report
        last_validator_issues = list(validator_issues)

        LOGGER.warning(
            "Thresholds not met with engine=%s (chars=%d ratio=%.2f)",
            engine,
            metrics.get("extracted_chars", 0),
            metrics.get("unique_pages_ratio", 0.0),
        )

    if "engines_tried" not in last_metrics:
        last_metrics["engines_tried"] = list(engines)
    last_metrics.setdefault("engine_selected", last_engine)

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
        second_pass_report=last_second_pass_report,
        validator_issues=list(last_validator_issues),
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


def _resolve_safety_expected(pipeline_info: Dict[str, object], document: BaseDocument) -> Optional[int]:
    if document is None:
        return None
    if isinstance(pipeline_info, dict):
        existing = pipeline_info.get("safety_expected_min")
        try:
            existing_value = int(existing)
        except (TypeError, ValueError):
            existing_value = None
        else:
            if existing_value > 0:
                if not isinstance(pipeline_info.get("safety_threshold_rule"), str):
                    _, inferred_rule = expected_safety_with_source(document)
                    if inferred_rule:
                        pipeline_info["safety_threshold_rule"] = inferred_rule
                return existing_value
    expected_min, rule = expected_safety_with_source(document)
    if isinstance(pipeline_info, dict):
        if rule:
            pipeline_info.setdefault("safety_threshold_rule", rule)
        pipeline_info["safety_expected_min"] = expected_min
    return expected_min if expected_min > 0 else None


def _document_metrics(document: BaseDocument) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if isinstance(document, IFUDocument):
        sync_revision_status(document)
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

    research_scope = getattr(document, "research_scope", None) or pipeline_info.get("research_scope")
    if research_scope:
        payload["research_scope"] = research_scope
        pipeline_info["research_scope"] = research_scope
    else:
        payload.setdefault("research_scope", "unknown")

    imrad_required = bool(pipeline_info.get("imrad_required"))
    payload["imrad_required"] = imrad_required
    ats_required = bool(pipeline_info.get("ats_yield_required"))
    payload["ats_yield_required"] = ats_required
    fm_confidence = pipeline_info.get("front_matter_confidence")
    if isinstance(fm_confidence, dict):
        payload["front_matter_confidence"] = fm_confidence

    if hasattr(document, "tables"):
        tables = getattr(document, "tables") or []
        payload["tables_kept"] = len(tables)
        pipeline_info["tables_kept"] = len(tables)
        original_tables = pipeline_info.get("tables_original")
        if isinstance(original_tables, int):
            payload["tables_original"] = original_tables
        else:
            payload.setdefault("tables_original", len(tables))
        dropped_tables = pipeline_info.get("tables_dropped")
        if isinstance(dropped_tables, int):
            payload["tables_dropped"] = dropped_tables
        else:
            payload.setdefault("tables_dropped", 0)
    else:
        payload["tables_kept"] = payload.get("tables_kept", 0)
        pipeline_info.setdefault("tables_kept", 0)
        payload.setdefault("tables_original", payload.get("tables_kept", 0))
        payload.setdefault("tables_dropped", pipeline_info.get("tables_dropped", 0))

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
        grade_density = round(with_grade / total_recs, 2) if total_recs else 0.0
        typed_density = round((graded_count + typed_ungraded) / total_recs, 2) if total_recs else 0.0

        payload["recommendations_count"] = total_recs
        payload["recommendations_total"] = total_recs
        payload["graded_count"] = graded_count
        payload["recommendations_graded"] = graded_count
        payload["typed_ungraded_count"] = typed_ungraded
        payload["recommendations_ungraded_typed"] = typed_ungraded
        payload["grade_density"] = grade_density
        payload["typed_density"] = typed_density

        pipeline_info["recommendations_count"] = total_recs
        pipeline_info["recommendations_total"] = total_recs
        pipeline_info["graded_count"] = graded_count
        pipeline_info["recommendations_graded"] = graded_count
        pipeline_info["typed_ungraded_count"] = typed_ungraded
        pipeline_info["recommendations_ungraded_typed"] = typed_ungraded
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

    research_outcomes = getattr(document, "research_outcomes", None)
    if research_outcomes is not None:
        payload["research_outcomes_present"] = True
        accuracy_present = _research_accuracy_present(research_outcomes)
        yield_present = _research_yield_present(research_outcomes)
        if accuracy_present:
            payload["diagnostic_accuracy_present"] = True
        if yield_present:
            payload["diagnostic_yield_present"] = True
    else:
        payload.setdefault("research_outcomes_present", False)
        payload.setdefault("diagnostic_accuracy_present", payload.get("diagnostic_accuracy_present", False))

    if getattr(document, "doc_type", None) == "article":
        payload["ats"] = validate_ats_yield(document)
        ats_applicability = pipeline_info.get("ats_yield_applicability")
        if ats_applicability:
            payload["ats_yield_applicability"] = ats_applicability
        reasons = pipeline_info.get("ats_yield_reasons")
        if reasons is not None:
            if isinstance(reasons, list):
                payload["ats_yield_reasons"] = list(reasons)
            else:
                payload["ats_yield_reasons"] = [str(reasons)]
        ats_meta = getattr(document, "ats_profile", None)
        if ats_meta is not None:
            profile_payload = {
                "is_diagnostic_study": bool(getattr(ats_meta, "is_diagnostic_study", False)),
                "strict_yield_required": bool(getattr(ats_meta, "strict_yield_required", False)),
                "strict_yield_observed": bool(getattr(ats_meta, "strict_yield_observed", False)),
                "strict_exclusion_reasons": list(getattr(ats_meta, "strict_exclusion_reasons", []) or []),
            }
            payload["ats_profile"] = profile_payload
            pipeline_info["ats_profile"] = profile_payload

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
        payload["safety_found"] = len(blocks)
        pipeline_info["safety_blocks_found"] = len(blocks)
        expected_value = _resolve_safety_expected(pipeline_info, document)
        if expected_value is not None:
            payload["safety_expected"] = expected_value
            payload["safety_found"] = len(blocks)
            pipeline_info["safety_expected_min"] = expected_value
            added = 0
            try:
                added = int(pipeline_info.get("safety_blocks_added") or 0)
            except (TypeError, ValueError):
                added = 0
            payload["safety_added"] = added
            payload["safety_status"] = "ok" if len(blocks) >= expected_value else "low"
        try:
            value = int(pipeline_info.get("safety_blocks_added") or 0)
        except (TypeError, ValueError):
            value = 0
        payload["safety_blocks_added"] = value
        if "safety_added" not in payload:
            payload["safety_added"] = value
        if "safety_expected_min" in pipeline_info:
            try:
                payload["safety_expected_min"] = int(pipeline_info.get("safety_expected_min") or 0)
            except (TypeError, ValueError):
                payload["safety_expected_min"] = 0
        gap_value = pipeline_info.get("safety_gap")
        try:
            gap_int = int(gap_value) if gap_value is not None else max(0, (payload.get("safety_expected") or 0) - len(blocks))
        except (TypeError, ValueError):
            gap_int = max(0, (payload.get("safety_expected") or 0) - len(blocks))
        payload["safety_gap"] = gap_int
        pipeline_info["safety_gap"] = gap_int
        rule_value = pipeline_info.get("safety_threshold_rule")
        if isinstance(rule_value, str) and rule_value:
            payload["safety_threshold_rule"] = rule_value
        elif expected_value is not None:
            _, inferred_rule = expected_safety_with_source(document)
            if inferred_rule:
                payload["safety_threshold_rule"] = inferred_rule
                pipeline_info["safety_threshold_rule"] = inferred_rule

    if hasattr(document, "references"):
        references = getattr(document, "references") or []
        payload["references_count"] = len(references)
        pipeline_info["references_detected"] = len(references)
    if "references_anchor_backfill" in pipeline_info:
        payload["references_anchor_backfill"] = bool(pipeline_info.get("references_anchor_backfill"))
        anchor_info = pipeline_info.get("references_anchor")
        if isinstance(anchor_info, dict):
            payload["references_anchor_pages"] = anchor_info.get("pages", [])
    else:
        payload.setdefault("references_anchor_backfill", False)

    if "long_doc_fast_path" in pipeline_info:
        payload["long_doc_fast_path"] = bool(pipeline_info.get("long_doc_fast_path"))
        threshold_value = pipeline_info.get("long_doc_page_threshold")
        if threshold_value is not None:
            payload["long_doc_page_threshold"] = threshold_value
    streaming_meta = pipeline_info.get("streaming_fallback")
    if isinstance(streaming_meta, dict):
        payload["streaming_fallback"] = streaming_meta
    timeouts_meta = pipeline_info.get("engine_timeouts_triggered")
    if isinstance(timeouts_meta, dict) and timeouts_meta:
        payload["engine_timeouts"] = dict(timeouts_meta)

    unresolved_affiliations = pipeline_info.get("frontmatter_affiliations_unresolved")
    if unresolved_affiliations is not None:
        try:
            unresolved_count = int(unresolved_affiliations)
        except (TypeError, ValueError):
            unresolved_count = 0
        payload["frontmatter_affiliations_unresolved"] = unresolved_count
        pipeline_info["frontmatter_affiliations_unresolved"] = unresolved_count
    else:
        payload.setdefault("frontmatter_affiliations_unresolved", 0)
        pipeline_info.setdefault("frontmatter_affiliations_unresolved", 0)

    toc_guard_info = pipeline_info.get("toc_guard")
    if isinstance(toc_guard_info, dict):
        guard_metrics = {
            "pages_dropped": toc_guard_info.get("pages_dropped", pipeline_info.get("toc_guard_pages_dropped", [])),
            "pages_dropped_count": toc_guard_info.get(
                "pages_dropped_count", pipeline_info.get("toc_guard_pages_dropped_count", 0)
            ),
        }
        payload["toc_guard"] = guard_metrics
    if isinstance(pipeline_info.get("toc_guard_pages_dropped"), list):
        payload["toc_pages_dropped"] = pipeline_info.get("toc_guard_pages_dropped")
        payload["toc_drop_count"] = pipeline_info.get("toc_guard_pages_dropped_count", 0)
        payload["toc_guard_dropped_pages"] = pipeline_info.get("toc_guard_pages_dropped")
    if "toc_guard_severity" in pipeline_info:
        payload["toc_guard_severity"] = pipeline_info.get("toc_guard_severity")
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

    second_pass_info = pipeline_info.get("second_pass", {})
    applied_list: List[str] = []
    reasons_list: List[str] = []
    modifications_map: Dict[str, int] = {}
    patch_summaries: List[Dict[str, object]] = []
    if isinstance(second_pass_info, dict):
        applied_candidates = second_pass_info.get("applied")
        if isinstance(applied_candidates, list):
            applied_list = [str(candidate) for candidate in applied_candidates if candidate]
        else:
            patches_applied = second_pass_info.get("patches_applied")
            if isinstance(patches_applied, list):
                applied_list = [str(candidate) for candidate in patches_applied if candidate]
        if applied_list:
            applied_list = list(dict.fromkeys(applied_list))

        raw_reasons = second_pass_info.get("reasons")
        if isinstance(raw_reasons, list):
            reasons_list = [str(reason) for reason in raw_reasons if reason]

        raw_modifications = second_pass_info.get("modifications")
        if isinstance(raw_modifications, dict):
            for key, value in raw_modifications.items():
                try:
                    modifications_map[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue
        if not modifications_map:
            diff_summary = second_pass_info.get("diff_summary")
            if isinstance(diff_summary, dict):
                for key, value in diff_summary.items():
                    try:
                        modifications_map[str(key)] = int(value)
                    except (TypeError, ValueError):
                        continue
        raw_patch_summaries = second_pass_info.get("patch_summaries")
        if isinstance(raw_patch_summaries, list):
            for entry in raw_patch_summaries:
                if isinstance(entry, dict):
                    patch_summaries.append(dict(entry))

    rebuilt_sections = modifications_map.get("sections_rebuilt")
    if isinstance(rebuilt_sections, int) and rebuilt_sections > 0:
        payload["sections_rebuilt"] = rebuilt_sections
        if getattr(document, "doc_type", "") == "ifu":
            payload["sectionizer_mode"] = "ifu_salvage"

    if isinstance(second_pass_info, dict):
        payload["second_pass_applied"] = bool(applied_list)
        payload["second_pass_patches"] = applied_list
        payload["second_pass_reasons"] = reasons_list
        payload["second_pass_modifications"] = dict(modifications_map)
        if modifications_map:
            payload["second_pass_modifications_total"] = sum(modifications_map.values())
        pipeline_info["second_pass_modifications"] = dict(modifications_map)
        if patch_summaries:
            payload["patches"] = patch_summaries

        ro_backfill = second_pass_info.get("research_outcomes_backfill")
        if isinstance(ro_backfill, dict):
            payload["second_pass_research_outcomes_backfill"] = dict(ro_backfill)
    else:
        payload.setdefault("second_pass_applied", False)
        payload.setdefault("second_pass_patches", [])
        payload.setdefault("second_pass_reasons", [])
        payload.setdefault("second_pass_modifications", {})
    if "second_pass_modifications_total" not in payload:
        payload["second_pass_modifications_total"] = 0

    if "toc_guard_adjustments" in pipeline_info:
        try:
            payload["toc_guard_adjustments"] = int(pipeline_info.get("toc_guard_adjustments") or 0)
        except (TypeError, ValueError):
            payload["toc_guard_adjustments"] = 0

    if "grade_backfilled" in pipeline_info:
        try:
            payload["grade_backfilled"] = int(pipeline_info.get("grade_backfilled") or 0)
        except (TypeError, ValueError):
            payload["grade_backfilled"] = 0

    if "recommendations_retyped" in pipeline_info:
        try:
            payload["recommendations_retyped"] = int(pipeline_info.get("recommendations_retyped") or 0)
        except (TypeError, ValueError):
            payload["recommendations_retyped"] = 0

    if "affiliation_softmap_applied" in pipeline_info:
        payload["affiliation_softmap_applied"] = bool(pipeline_info.get("affiliation_softmap_applied"))

    if "indications_fallback_provenance" in pipeline_info:
        payload["indications_fallback_provenance"] = pipeline_info.get("indications_fallback_provenance")
    indications_value = getattr(document, "indications_for_use", None)
    if isinstance(indications_value, dict):
        anchor_page = indications_value.get("anchor_page")
        if isinstance(anchor_page, int):
            payload["indications_anchor_page"] = anchor_page
    elif isinstance(pipeline_info.get("indications_anchor_page"), int):
        payload["indications_anchor_page"] = pipeline_info.get("indications_anchor_page")

    if "front_matter_fallback_reason" in pipeline_info:
        payload["front_matter_fallback_reason"] = pipeline_info.get("front_matter_fallback_reason")
    if pipeline_info.get("front_matter_revision_sanitized"):
        payload["front_matter_revision_sanitized"] = True

    if "safety_density_boost_applied" in pipeline_info:
        payload["safety_density_boost_applied"] = bool(pipeline_info.get("safety_density_boost_applied"))

    second_pass_payload: Dict[str, object] = {
        "mode": None,
        "applied": [],
        "reasons": [],
        "modifications": {},
    }
    if isinstance(second_pass_info, dict):
        applied_candidates = second_pass_info.get("applied")
        if isinstance(applied_candidates, list):
            applied_list = list(dict.fromkeys(applied_candidates))
        else:
            patches_applied = second_pass_info.get("patches_applied")
            applied_list = list(dict.fromkeys(patches_applied)) if isinstance(patches_applied, list) else []
        reasons_list = second_pass_info.get("reasons") if isinstance(second_pass_info.get("reasons"), list) else []
        modifications_map: Dict[str, int] = {}
        raw_modifications = second_pass_info.get("modifications")
        if isinstance(raw_modifications, dict):
            for key, value in raw_modifications.items():
                try:
                    modifications_map[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue
        else:
            raw_diff_summary = second_pass_info.get("diff_summary")
            if isinstance(raw_diff_summary, dict):
                for key, value in raw_diff_summary.items():
                    try:
                        modifications_map.setdefault(str(key), int(value))
                    except (TypeError, ValueError):
                        continue
        second_pass_payload = {
            "mode": second_pass_info.get("mode"),
            "applied": applied_list,
            "reasons": list(reasons_list) if reasons_list else [],
            "modifications": modifications_map,
        }
        if patch_summaries:
            second_pass_payload["patch_summaries"] = patch_summaries
    payload["second_pass"] = second_pass_payload

    metrics_summary = {
        "toc_pages_dropped": int(
            pipeline_info.get("toc_guard_pages_dropped_count")
            if isinstance(pipeline_info.get("toc_guard_pages_dropped_count"), int)
            else len(payload.get("toc_pages_dropped") or [])
        ),
        "safety_blocks_found": payload.get("safety_blocks_found", 0),
        "safety_blocks_added": payload.get("safety_blocks_added", 0),
        "second_pass_applied": bool(second_pass_payload.get("applied")),
        "second_pass_patches": list(second_pass_payload.get("applied", [])),
        "second_pass_reasons": list(second_pass_payload.get("reasons", [])),
        "second_pass_modifications": dict(second_pass_payload.get("modifications", {})),
        "patches": list(second_pass_payload.get("patch_summaries", [])),
    }
    if "safety_expected_min" in payload:
        metrics_summary["safety_expected_min"] = payload.get("safety_expected_min", 0)
    metrics_summary["safety_found"] = payload.get("safety_found", 0)
    metrics_summary["safety_gap"] = payload.get("safety_gap", 0)
    if "safety_threshold_rule" in payload:
        metrics_summary["safety_threshold_rule"] = payload["safety_threshold_rule"]
    if isinstance(pipeline_info, dict) and "revision_status" in pipeline_info:
        metrics_summary["revision_status"] = pipeline_info.get("revision_status")
    if "sections_rebuilt" in payload:
        metrics_summary["sections_rebuilt"] = payload.get("sections_rebuilt", 0)
    if "sectionizer_mode" in payload:
        metrics_summary["sectionizer_mode"] = payload.get("sectionizer_mode")
    metrics_summary["tables_kept"] = int(payload.get("tables_kept", 0))
    metrics_summary["tables_dropped"] = int(payload.get("tables_dropped", 0))
    metrics_summary["tables_original"] = int(payload.get("tables_original", 0))
    if "streaming_fallback" in payload:
        metrics_summary["streaming_fallback"] = payload.get("streaming_fallback")
    if "engine_timeouts" in payload:
        metrics_summary["engine_timeouts"] = payload.get("engine_timeouts")
    chunk_metrics = pipeline_info.get("chunking")
    if isinstance(chunk_metrics, dict):
        metrics_summary["chunking"] = chunk_metrics
    payload["_metrics"] = metrics_summary

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
    else:
        pipeline_info.setdefault("tables_original", 0)
        pipeline_info.setdefault("tables_kept", 0)
        pipeline_info.setdefault("tables_dropped", 0)

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


def _load_shared_chunking_defaults() -> Dict[str, Any]:
    global _SHARED_CHUNKING_DEFAULTS
    if _SHARED_CHUNKING_DEFAULTS is not None:
        return dict(_SHARED_CHUNKING_DEFAULTS)
    config_path = Path(__file__).resolve().parents[2] / "configs" / "_shared" / "chunking.yaml"
    defaults: Dict[str, Any] = {}
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            if isinstance(data, dict):
                defaults = dict(data)
    except FileNotFoundError:
        defaults = {}
    except Exception as exc:  # pragma: no cover - config optional
        LOGGER.debug("Unable to load shared chunking defaults: %s", exc)
        defaults = {}
    _SHARED_CHUNKING_DEFAULTS = defaults
    return dict(defaults)


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


def _store_success_in_cache(
    cache_key: str,
    doc_type: str,
    document: BaseDocument,
    metrics: Dict[str, Any],
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
