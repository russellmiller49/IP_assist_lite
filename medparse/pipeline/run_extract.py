"""High-level extraction runner with completeness guards and caching."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, Type

import yaml

from medparse.config import ExtractionConfig, ExtractionProfile
from medparse.extractors.article import extract_article
from medparse.extractors.guideline import extract_guideline
from medparse.extractors.ifu import extract_ifu
from medparse.extractors.textbook import extract_textbook_chapter
from medparse.extract.utils import load_pages
from medparse.schema.article import ArticleDocument
from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument
from medparse.schema.textbook import TextbookChapterDocument
from medparse.utils.cache import compute_cache_key, load_cache_entry, store_cache_entry
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

    @classmethod
    def from_path(cls, path: Path) -> "PipelineConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        profile_value = data.get("profile", ExtractionProfile.ENRICHED.value)
        try:
            profile = ExtractionProfile(profile_value)
        except ValueError:
            profile = ExtractionProfile.ENRICHED

        engines = data.get("engines") or ["fitz", "pdfplumber"]

        return cls(
            doc_type=data["doc_type"],
            profile=profile,
            engines=[engine.lower() for engine in engines],
            min_chars=int(data.get("min_chars", 0)),
            min_pages_ratio=float(data.get("min_pages_ratio", 0.0)),
            ocr=bool(data.get("ocr", False)),
            enable_umls=data.get("umls"),
            enable_relations=data.get("relations"),
            enable_guideline_norms=data.get("guideline_enrichment"),
            max_preview_pages=data.get("max_preview_pages"),
        )

    def to_extraction_config(self, *, use_cache: bool) -> ExtractionConfig:
        kwargs = {
            "profile": self.profile,
            "enable_umls": self.enable_umls if self.enable_umls is not None else True,
            "enable_relations": self.enable_relations if self.enable_relations is not None else True,
            "enable_guideline_norms": self.enable_guideline_norms if self.enable_guideline_norms is not None else True,
            "use_cache": use_cache,
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
        return ExtractionConfig(**kwargs)


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

    def to_payload(self) -> Dict[str, object]:
        if self.success and self.document is not None:
            payload = self.document.model_dump(mode="json")
            payload["_metrics"] = self.metrics
            payload["_engine"] = self.engine
            payload["_mode"] = self.mode
            payload["_cache_used"] = self.cache_used
            timestamp = getattr(self.document, "extraction_timestamp", None)
            if isinstance(timestamp, datetime):
                timestamp_value = timestamp.isoformat()
            else:
                timestamp_value = timestamp
            payload["_pipeline"] = {
                "profile": self.config.profile.value,
                "engines": self.config.engines,
                "ocr_used_pages": self.ocr_pages,
                "timestamp": timestamp_value,
                "version": getattr(self.document, "extraction_version", None),
            }
            return payload
        return {
            "doc_type": self.config.doc_type,
            "source_file": str(self.pdf_path),
            "failure_reason": self.failure_reason or "extraction_failed",
            "metrics": self.metrics,
            "engine": self.engine,
            "mode": self.mode,
        }


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

    if config.doc_type not in EXTRACTOR_MAP:
        raise ValueError(f"Unsupported doc_type '{config.doc_type}' in {config_path}")

    extractor = EXTRACTOR_MAP[config.doc_type]
    engines = config.engines or ["fitz"]
    pdf_bytes = pdf_path.read_bytes()
    total_pages = _determine_total_pages(pdf_path)

    cache_key = compute_cache_key(pdf_bytes, total_pages, engines, config.profile.value)
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
            )

    last_metrics: Dict[str, float | int] = {}
    last_engine = engines[0]
    last_ocr_pages: List[int] = []
    failure_reason: Optional[str] = None

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
            ocr=config.ocr,
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

        LOGGER.info(
            "Completed extraction: doc_type=%s engine=%s duration=%.2fs chars=%d coverage=%.2f",
            config.doc_type,
            engine,
            duration,
            metrics.get("extracted_chars", 0),
            metrics.get("unique_pages_ratio", 0.0),
        )

        if _meets_thresholds(config, metrics):
            if cache_enabled and idx == 0:
                _store_success_in_cache(
                    cache_key,
                    config.doc_type,
                    document,
                    metrics,
                    engine,
                    extraction_config.profile.value,
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
            )

        last_metrics = metrics
        last_engine = engine
        last_ocr_pages = ocr_pages
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


def _meets_thresholds(config: PipelineConfig, metrics: Dict[str, float]) -> bool:
    if metrics.get("page_count", 0) <= 0:
        return False
    if metrics.get("page_count", 0) < 10:
        return metrics.get("unique_pages_ratio", 0.0) >= 0.9
    if metrics.get("extracted_chars", 0) < config.min_chars:
        return False
    if metrics.get("unique_pages_ratio", 0.0) < config.min_pages_ratio:
        return False
    return True


def _document_metrics(document: BaseDocument) -> Dict[str, int | float | bool]:
    payload: Dict[str, int | float | bool] = {}

    if hasattr(document, "sections"):
        sections = getattr(document, "sections") or {}
        payload["sections_count"] = len(sections)

    if hasattr(document, "tables"):
        tables = getattr(document, "tables") or []
        payload["tables_kept"] = len(tables)

    if hasattr(document, "recommendations"):
        recs = getattr(document, "recommendations") or []
        payload["recommendations_count"] = len(recs)

    if hasattr(document, "diagnostic_yield"):
        payload["diagnostic_yield_present"] = bool(getattr(document, "diagnostic_yield"))

    if hasattr(document, "umls_entities"):
        entities = getattr(document, "umls_entities") or []
        payload["umls_entities"] = len(entities)

    return payload


def _hydrate_document(doc_type: str, cached_data: Dict[str, object]) -> BaseDocument:
    model_cls = MODEL_MAP.get(doc_type)
    if not model_cls:
        raise ValueError(f"Unsupported doc_type '{doc_type}' in cache entry.")
    document_payload = cached_data.get("document") or {}
    return model_cls.model_validate(document_payload)


def _store_success_in_cache(
    cache_key: str,
    doc_type: str,
    document: BaseDocument,
    metrics: Dict[str, float | int | bool],
    engine: str,
    profile: str,
) -> None:
    payload = {
        "doc_type": doc_type,
        "document": document.model_dump(mode="json"),
        "metrics": metrics,
        "engine": engine,
        "profile": profile,
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
