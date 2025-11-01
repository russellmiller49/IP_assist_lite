"""Utilities to detect and repair low-spacing PDF extractions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from medparse.extract.utils import load_pages
from medparse.ingest.models import PageData
from medparse.normalize.text_cleanup import restore_whitespace
from medparse.text.paragraphizer import compute_space_metrics
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)

DEFAULT_SPACE_RATIO_THRESHOLD = 0.05
DEFAULT_AVG_TOKEN_THRESHOLD = 12.0


def _needs_spacing_repair(metrics: Dict[str, float], *, space_threshold: float, token_threshold: float) -> bool:
    return (
        metrics.get("space_ratio", 1.0) < space_threshold
        and metrics.get("avg_token_length", 0.0) > token_threshold
    )


def _engine_sequence(current: str, preferred: Sequence[str]) -> Iterable[str]:
    seen = set()
    for candidate in preferred:
        normalized = candidate.lower()
        if normalized in seen or normalized == current.lower():
            continue
        seen.add(normalized)
        yield normalized
    for fallback in ("pymupdf", "pdfplumber"):
        if fallback not in seen and fallback != current.lower():
            seen.add(fallback)
            yield fallback


def _pages_to_engine_map(pages: Sequence[PageData], engine: str) -> Dict[int, str]:
    return {page.number: engine for page in pages}


def repair_space_poor_pages(
    pdf_path: Path,
    pages: List[PageData],
    *,
    current_engine: str,
    settings: Dict[str, object] | None = None,
) -> Tuple[List[PageData], Dict[str, object]]:
    """Detect low-spacing pages and rerun extraction with alternate engines if needed."""

    settings = settings or {}
    fallback_settings = settings.get("engine_fallback") if isinstance(settings, dict) else None
    if not isinstance(fallback_settings, dict):
        fallback_settings = {}

    space_threshold = float(fallback_settings.get("space_ratio_threshold", DEFAULT_SPACE_RATIO_THRESHOLD))
    token_threshold = float(fallback_settings.get("avg_token_length_threshold", DEFAULT_AVG_TOKEN_THRESHOLD))
    enable_ocr = bool(fallback_settings.get("enable_ocr", False))
    fallback_order = fallback_settings.get("fallback_engines") or []
    if not isinstance(fallback_order, Sequence):
        fallback_order = []

    info: Dict[str, object] = {
        "space_ratio_before": None,
        "avg_token_length_before": None,
        "space_ratio_after": None,
        "avg_token_length_after": None,
        "text_repair_applied": False,
        "engine_used_per_page": _pages_to_engine_map(pages, current_engine),
        "repair_strategy": None,
    }

    baseline_metrics = compute_space_metrics(pages)
    info["space_ratio_before"] = baseline_metrics["space_ratio"]
    info["avg_token_length_before"] = baseline_metrics["avg_token_length"]

    if not _needs_spacing_repair(
        baseline_metrics,
        space_threshold=space_threshold,
        token_threshold=token_threshold,
    ):
        return pages, info

    LOGGER.info(
        "Detected low spacing (ratio=%.4f avg_token=%.2f) with engine=%s; trying fallbacks.",
        baseline_metrics["space_ratio"],
        baseline_metrics["avg_token_length"],
        current_engine,
    )

    for engine in _engine_sequence(current_engine, fallback_order):
        try:
            candidate_pages = load_pages(
                pdf_path,
                engine=engine,
                max_pages=len(pages),
                ocr=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Fallback engine %s failed: %s", engine, exc)
            continue

        candidate_metrics = compute_space_metrics(candidate_pages)
        LOGGER.debug(
            "Fallback engine=%s space_ratio=%.4f avg_token=%.2f",
            engine,
            candidate_metrics["space_ratio"],
            candidate_metrics["avg_token_length"],
        )
        if not _needs_spacing_repair(
            candidate_metrics,
            space_threshold=space_threshold,
            token_threshold=token_threshold,
        ):
            info.update(
                {
                    "text_repair_applied": True,
                    "space_ratio_after": candidate_metrics["space_ratio"],
                    "avg_token_length_after": candidate_metrics["avg_token_length"],
                    "engine_used_per_page": _pages_to_engine_map(candidate_pages, engine),
                    "repair_strategy": f"engine:{engine}",
                }
            )
            return list(candidate_pages), info

    if enable_ocr:
        try:
            ocr_pages = load_pages(
                pdf_path,
                engine=current_engine,
                max_pages=len(pages),
                ocr=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("OCR fallback failed: %s", exc)
        else:
            ocr_metrics = compute_space_metrics(ocr_pages)
            LOGGER.debug(
                "OCR fallback space_ratio=%.4f avg_token=%.2f",
                ocr_metrics["space_ratio"],
                ocr_metrics["avg_token_length"],
            )
            if not _needs_spacing_repair(
                ocr_metrics,
                space_threshold=space_threshold,
                token_threshold=token_threshold,
            ):
                info.update(
                    {
                        "text_repair_applied": True,
                        "space_ratio_after": ocr_metrics["space_ratio"],
                        "avg_token_length_after": ocr_metrics["avg_token_length"],
                        "engine_used_per_page": _pages_to_engine_map(ocr_pages, f"{current_engine}+ocr"),
                        "repair_strategy": "ocr",
                    }
                )
                return list(ocr_pages), info

    # Final fallback: attempt whitespace restoration heuristic
    repaired_pages: List[PageData] = []
    for page in pages:
        restored = restore_whitespace(page.text or "")
        if restored and restored != page.text:
            updated = replace(page, text=restored, lines=[line for line in restored.splitlines() if line.strip()])
            repaired_pages.append(updated)
        else:
            repaired_pages.append(page)

    repaired_metrics = compute_space_metrics(repaired_pages)
    if repaired_metrics["space_ratio"] > baseline_metrics["space_ratio"]:
        info.update(
            {
                "text_repair_applied": True,
                "space_ratio_after": repaired_metrics["space_ratio"],
                "avg_token_length_after": repaired_metrics["avg_token_length"],
                "engine_used_per_page": _pages_to_engine_map(repaired_pages, current_engine),
                "repair_strategy": "restore_whitespace",
            }
        )
        return repaired_pages, info

    info["repair_strategy"] = "failed"
    info["space_ratio_after"] = repaired_metrics["space_ratio"]
    info["avg_token_length_after"] = repaired_metrics["avg_token_length"]
    return pages, info


__all__ = ["repair_space_poor_pages"]

