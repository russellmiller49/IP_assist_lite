"""Batch processing utilities for Medparse."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from medparse.pipeline.run_extract import run_extract
from medparse.schema.common import BaseDocument
from medparse.utils.log import get_logger
from medparse.utils.slug import slugify
from medparse.validate.validators import validate_document

LOGGER = get_logger(__name__)

CONFIG_MAP = {
    "article": ("run_article.yaml", "article"),
    "guideline": ("run_guideline.yaml", "guideline"),
    "ifu": ("run_ifu.yaml", "ifu"),
    "textbook": ("run_textbook.yaml", "textbook"),
}


def run_batch(input_dir: Path, output_dir: Path, doc_type: str) -> None:
    """Process PDFs within ``input_dir`` using the specified document type."""

    if doc_type not in CONFIG_MAP:
        raise ValueError(f"Unsupported doc_type '{doc_type}'")

    config_name, prefix = CONFIG_MAP[doc_type]
    config_path = Path(__file__).resolve().parents[2] / "configs" / config_name

    output_dir.mkdir(parents=True, exist_ok=True)
    results: List[Tuple[str, str]] = []

    if doc_type == "textbook":
        jobs = _collect_textbook_jobs(input_dir, output_dir, prefix)
    else:
        jobs = _collect_simple_jobs(input_dir, output_dir, prefix)

    if not jobs:
        LOGGER.warning("No PDFs found for doc_type=%s in %s", doc_type, input_dir)
        return

    for pdf_path, out_path in jobs:
        try:
            outcome = run_extract(
                pdf_path=pdf_path,
                config_path=config_path,
                use_cache=False,
                force_deep=True,
                max_pages=None,
                summary_length=None,
            )
            payload = outcome.to_payload()
            out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            LOGGER.info("Extracted %s -> %s", pdf_path.name, out_path.name)
            if outcome.success and outcome.document is not None:
                _log_issues(outcome.document)
            else:
                results.append(("failed", pdf_path.name))
                LOGGER.error(
                    "Extraction did not meet thresholds for %s; failure_reason=%s",
                    pdf_path.name,
                    payload.get("failure_reason"),
                )
                continue
            results.append(("success", pdf_path.name))
        except Exception as exc:  # pragma: no cover - runtime logging
            LOGGER.exception("Failed to extract %s: %s", pdf_path.name, exc)
            results.append(("failed", pdf_path.name))

    report_path = output_dir / "extraction_report.json"
    report_path.write_text(json.dumps(_summarize(results), indent=2))
    LOGGER.info("Wrote batch report to %s", report_path)


def _collect_simple_jobs(input_dir: Path, output_dir: Path, prefix: str) -> List[Tuple[Path, Path]]:
    pdf_paths = sorted(path for path in input_dir.glob("*.pdf") if path.is_file())
    return [(pdf, output_dir / f"{prefix}_{slugify(pdf.stem)}.json") for pdf in pdf_paths]


def _collect_textbook_jobs(input_dir: Path, output_dir: Path, prefix: str) -> List[Tuple[Path, Path]]:
    jobs: List[Tuple[Path, Path]] = []
    for folder in sorted(path for path in input_dir.iterdir() if path.is_dir()):
        book_slug = slugify(folder.name)
        candidate_dirs = [folder]
        pdf_subdir = folder / "pdf"
        if pdf_subdir.exists():
            candidate_dirs.append(pdf_subdir)
        seen: set[Path] = set()
        for candidate in candidate_dirs:
            for pdf in sorted(candidate.glob("*.pdf")):
                if pdf in seen:
                    continue
                seen.add(pdf)
                chapter_slug = slugify(pdf.stem)
                jobs.append((pdf, output_dir / f"{prefix}_{book_slug}_{chapter_slug}.json"))
    return jobs


def _log_issues(document: BaseDocument) -> None:
    for issue in validate_document(document):
        LOGGER.warning("%s: %s", issue.severity.upper(), issue.message)


def _summarize(results: Iterable[Tuple[str, str]]) -> Dict[str, object]:
    summary: Dict[str, object] = {"success": [], "failed": []}
    for status, name in results:
        summary.setdefault(status, []).append(name)
    summary["total"] = len(summary["success"]) + len(summary["failed"])
    summary["success_count"] = len(summary["success"])
    summary["failed_count"] = len(summary["failed"])
    return summary

__all__ = ["run_batch"]
