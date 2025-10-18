"""Backfill Medparse evidence into Neo4j and Qdrant from seed artifacts."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Sequence

from adapters.medparse_transport import get_medparse_transport
from config import AppConfig
from .ingest_documents import (
    IngestSummary,
    ingest_payload,
    ingest_pdf,
    _build_sinks,
    _close_sinks,
)


def _collect_files(root: Path | None, patterns: Sequence[str]) -> list[Path]:
    if root is None:
        return []
    files: list[Path] = []
    if root.is_file():
        return [root]
    for pattern in patterns:
        files.extend(sorted(root.glob(pattern)))
    return files


def backfill(
    *,
    pdf_dir: Path | None,
    json_dir: Path | None,
    doc_type: str | None,
    raw_output_dir: Path | None,
    report_path: Path,
) -> list[IngestSummary]:
    cfg = AppConfig()
    transport = get_medparse_transport(cfg)
    sinks = _build_sinks(cfg)

    summaries: list[IngestSummary] = []
    try:
        if pdf_dir:
            for pdf_path in _collect_files(pdf_dir, ("*.pdf",)):
                _, summary = ingest_pdf(
                    pdf_path,
                    doc_type=doc_type,
                    transport=transport,
                    sinks=sinks,
                    raw_output_dir=raw_output_dir,
                )
                summaries.append(summary)

        if json_dir:
            for json_path in _collect_files(json_dir, ("*.json",)):
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                _, summary = ingest_payload(
                    payload,
                    cfg=cfg,
                    sinks=sinks,
                    raw_output_dir=raw_output_dir,
                )
                summaries.append(summary)
    finally:
        _close_sinks(sinks)

    _write_report(report_path, summaries)
    return summaries


def _write_report(path: Path, summaries: Sequence[IngestSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["doc_id", "sections", "recommendations", "stats", "figures", "tables", "edges"])
        for summary in summaries:
            counts = summary.counts
            writer.writerow(
                [
                    summary.doc_id,
                    counts.get("sections", 0),
                    counts.get("recommendations", 0),
                    counts.get("stats", 0),
                    counts.get("figures", 0),
                    counts.get("tables", 0),
                    json.dumps(summary.edges),
                ]
            )


def _parse_args(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description="Backfill Medparse artifacts into Neo4j and Qdrant.")
    parser.add_argument("--pdf-dir", default="data/seed", help="Directory containing PDF documents.")
    parser.add_argument("--json-dir", default="data/seed", help="Directory containing Medparse JSON payloads.")
    parser.add_argument("--doc-type", default=None, help="Optional document type override.")
    parser.add_argument("--raw-dir", default=None, help="Directory to store raw extraction JSON.")
    parser.add_argument("--report", default="data/seed/backfill_report.csv", help="CSV report path.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else None
    json_dir = Path(args.json_dir) if args.json_dir else None
    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    report_path = Path(args.report)
    backfill(
        pdf_dir=pdf_dir if pdf_dir and pdf_dir.exists() else None,
        json_dir=json_dir if json_dir and json_dir.exists() else None,
        doc_type=args.doc_type,
        raw_output_dir=raw_dir,
        report_path=report_path,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
