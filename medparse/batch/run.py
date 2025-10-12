"""Batch processing utilities for Medparse."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from medparse.config import ExtractionConfig
from medparse.extract.dispatcher import dispatch_document
from medparse.utils.log import get_logger

LOGGER = get_logger(__name__)


def run_batch(input_dir: Path, output_dir: Path, jobs: int = 1) -> None:
    """Process all PDFs within ``input_dir`` and emit JSON payloads into ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_paths = sorted(path for path in input_dir.glob("*.pdf") if path.is_file())
    results: List[Tuple[str, str]] = []

    for pdf_path in pdf_paths:
        try:
            document = dispatch_document(pdf_path, ExtractionConfig())
            out_file = output_dir / f"{pdf_path.stem}.json"
            out_file.write_text(document.model_dump_json(indent=2))
            LOGGER.info("Extracted %s -> %s", pdf_path.name, out_file.name)
            results.append(("success", pdf_path.name))
        except Exception as exc:  # pragma: no cover - error logging path
            LOGGER.exception("Failed to extract %s: %s", pdf_path.name, exc)
            results.append(("failed", pdf_path.name))

    summary = _summarize(results)
    report_path = output_dir / "extraction_report.json"
    report_path.write_text(json.dumps(summary, indent=2))
    LOGGER.info("Wrote batch report to %s", report_path)


def _summarize(results: List[Tuple[str, str]]) -> Dict[str, object]:
    summary: Dict[str, object] = {"success": [], "failed": []}
    for status, name in results:
        summary[status].append(name)
    summary["total"] = len(results)
    summary["success_count"] = len(summary["success"])
    summary["failed_count"] = len(summary["failed"])
    return summary
