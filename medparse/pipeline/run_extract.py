"""High-level extraction runner with completeness guards and caching."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, Type

import yaml

from medparse.extract.articles import extract_article
from medparse.extractors.ifu import extract_ifu
from medparse.extract.textbook import extract_textbook_chapter
from medparse.extract.utils import load_pages
from medparse.schema.article import ArticleDocument
from medparse.schema.common import BaseDocument
from medparse.schema.ifu import IFUDocument
from medparse.schema.textbook import TextbookChapterDocument
from medparse.utils.cache import compute_cache_key, load_cache_entry, store_cache_entry
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

DocType = Literal["article", "ifu", "textbook"]
SummaryLength = Literal["short", "medium", "long"]

EXTRACTOR_MAP = {
    "article": extract_article,
    "ifu": extract_ifu,
    "textbook": extract_textbook_chapter,
}

MODEL_MAP: Dict[str, Type[BaseDocument]] = {
    "article": ArticleDocument,
    "ifu": IFUDocument,
    "textbook": TextbookChapterDocument,
}


@dataclass
class PipelineConfig:
    doc_type: DocType
    layout_engine_primary: str
    layout_engine_fallbacks: List[str]
    table_extraction: bool
    max_pages: Optional[int]
    summary_length: SummaryLength
    min_chars: int
    min_pages_ratio: float
    sections: List[str]
    book_context_file: Optional[str] = None

    @classmethod
    def from_path(cls, path: Path) -> "PipelineConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        layout_fallbacks = data.get("layout_engine_fallbacks") or []
        return cls(
            doc_type=data["doc_type"],
            layout_engine_primary=data.get("layout_engine_primary", "pymupdf"),
            layout_engine_fallbacks=list(layout_fallbacks),
            table_extraction=bool(data.get("table_extraction", True)),
            max_pages=data.get("max_pages"),
            summary_length=data.get("summary_length", "medium"),
            min_chars=int(data.get("min_chars", 0)),
            min_pages_ratio=float(data.get("min_pages_ratio", 0.0)),
            sections=list(data.get("sections") or []),
            book_context_file=data.get("book_context_file"),
        )


@dataclass
class PipelineOutcome:
    pdf_path: Path
    config: PipelineConfig
    success: bool
    document: Optional[BaseDocument]
    metrics: Dict[str, float | int]
    engine: str
    mode: str
    cache_used: bool = False
    failure_reason: Optional[str] = None

    def to_payload(self) -> Dict[str, object]:
        if self.success and self.document is not None:
            payload = self.document.model_dump(mode="json")
            payload["_metrics"] = self.metrics
            payload["_engine"] = self.engine
            payload["_mode"] = self.mode
            payload["_cache_used"] = self.cache_used
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
) -> PipelineOutcome:
    """Run extraction with completeness checks and caching."""

    config = PipelineConfig.from_path(config_path)
    if summary_length:
        config.summary_length = summary_length
    if max_pages is not None:
        config.max_pages = max_pages

    if config.doc_type not in EXTRACTOR_MAP:
        raise ValueError(f"Unsupported doc_type '{config.doc_type}' in {config_path}")

    pdf_bytes = pdf_path.read_bytes()
    total_pages = _determine_total_pages(pdf_path)
    cache_key = compute_cache_key(pdf_bytes, total_pages)
    extractor = EXTRACTOR_MAP[config.doc_type]

    attempt_plan: List[Tuple[str, str]] = []
    primary_mode = "full" if force_deep else "preview"
    attempt_plan.append((config.layout_engine_primary, primary_mode))

    if config.layout_engine_fallbacks:
        for engine in config.layout_engine_fallbacks:
            attempt_plan.append((engine, "full"))
    elif primary_mode != "full":
        # Ensure at least one full run if no fallbacks provided.
        attempt_plan.append((config.layout_engine_primary, "full"))

    cached_data = None
    if use_cache and primary_mode == "full":
        cached_data = load_cache_entry(cache_key)
        if cached_data and cached_data.get("extraction_mode") == "full":
            document = _hydrate_document(config.doc_type, cached_data)
            metrics = cached_data.get("metrics", {})
            LOGGER.info(
                "Cache hit: doc_type=%s engine=%s mode=cache page_count=%s extracted_chars=%s unique_pages_seen=%s",
                config.doc_type,
                cached_data.get("engine"),
                metrics.get("page_count"),
                metrics.get("extracted_chars"),
                metrics.get("unique_pages_seen"),
            )
            return PipelineOutcome(
                pdf_path=pdf_path,
                config=config,
                success=True,
                document=document,
                metrics=metrics,
                engine=cached_data.get("engine", config.layout_engine_primary),
                mode="cache",
                cache_used=True,
            )

    last_metrics: Dict[str, float | int] = {}
    last_engine = attempt_plan[0][0]
    last_mode = attempt_plan[0][1]
    use_cache_flag = use_cache

    for index, (engine, mode) in enumerate(attempt_plan):
        page_limit = None
        if mode != "full":
            page_limit = config.max_pages
        allow_cache = use_cache_flag and mode == "full" and index == 0

        LOGGER.info(
            "Starting extraction: doc_type=%s engine=%s mode=%s page_count=%s",
            config.doc_type,
            engine,
            mode,
            total_pages,
        )

        start = time.time()
        pages = load_pages(pdf_path, engine=engine, max_pages=page_limit)
        document = extractor(
            pdf_path,
            engine=engine,
            page_limit=page_limit,
            pages=pages,
        )
        duration = time.time() - start
        metrics = _compute_metrics(pages, total_pages, duration)
        last_metrics = metrics
        last_engine = engine
        last_mode = mode

        LOGGER.info(
            "Completed extraction: doc_type=%s engine=%s mode=%s duration=%.2fs extracted_chars=%d unique_pages_seen=%d page_count=%d",
            config.doc_type,
            engine,
            mode,
            metrics["duration_s"],
            metrics["extracted_chars"],
            metrics["unique_pages_seen"],
            metrics["page_count"],
        )

        if _meets_thresholds(config, metrics):
            if allow_cache:
                _store_success_in_cache(
                    cache_key,
                    config.doc_type,
                    document,
                    metrics,
                    engine,
                    mode,
                )
            return PipelineOutcome(
                pdf_path=pdf_path,
                config=config,
                success=True,
                document=document,
                metrics=metrics,
                engine=engine,
                mode=mode,
                cache_used=False,
            )

        LOGGER.warning(
            "SHORT_RUN_DETECTED: rerunning with fallbacks... doc_type=%s engine=%s extracted_chars=%d unique_pages_ratio=%.2f required_chars=%d required_ratio=%.2f",
            config.doc_type,
            engine,
            int(metrics["extracted_chars"]),
            metrics["unique_pages_ratio"],
            config.min_chars,
            config.min_pages_ratio,
        )
        use_cache_flag = False

    failure_reason = "Failed to meet extraction completeness thresholds after fallbacks."
    return PipelineOutcome(
        pdf_path=pdf_path,
        config=config,
        success=False,
        document=None,
        metrics=last_metrics,
        engine=last_engine,
        mode=last_mode,
        cache_used=False,
        failure_reason=failure_reason,
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
    metrics: Dict[str, float],
    engine: str,
    mode: str,
) -> None:
    payload = {
        "doc_type": doc_type,
        "document": document.model_dump(mode="json"),
        "metrics": metrics,
        "engine": engine,
        "extraction_mode": mode,
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
