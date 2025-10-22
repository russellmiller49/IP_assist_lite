#!/usr/bin/env python3
"""Regenerate Medparse golden fixtures for test validation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapters.medparse_transport import get_medparse_transport  # noqa: E402
from config import AppConfig  # noqa: E402
from jobs.ingest_documents import _build_extract_request  # noqa: E402
from tests.golden_utils import (  # noqa: E402
    PDF_FIXTURES_DIR,
    canonicalize_payload,
    iter_fixture_pdfs,
    write_pdf_golden,
)

def _build_request(path: Path) -> dict:
    # Reuse the ingestion helper to ensure identical behavior.
    request = _build_extract_request(path, doc_id=path.stem)
    # _build_extract_request already base64-encodes the PDF.
    return dict(request)


def regenerate_goldens(
    pdf_paths: Iterable[Path],
    *,
    output_dir: Path | None = None,
    verbose: bool = False,
) -> Sequence[Path]:
    """Regenerate goldens for the provided PDF paths."""

    cfg = AppConfig()
    transport = get_medparse_transport(cfg)
    output_dir = output_dir or (PDF_FIXTURES_DIR.parents[1] / "golden" / "current")
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    try:
        for pdf_path in pdf_paths:
            if verbose:
                print(f"[goldens] regenerating for: {pdf_path}")
            request = _build_request(pdf_path)
            response = transport.extract(request)
            canonical = canonicalize_payload(json.loads(json.dumps(response)))
            written_path = write_pdf_golden(pdf_path.name, canonical, directory=output_dir)
            written.append(written_path)
    finally:
        close = getattr(transport, "close", None)
        if callable(close):
            close()
    return written


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate golden fixtures for Medparse tests.")
    parser.add_argument(
        "--pdf",
        action="append",
        help="Specific PDF name(s) inside tests/data/pdfs to regenerate. Defaults to all fixtures.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional override for the goldens output directory.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.pdf:
        targets = [PDF_FIXTURES_DIR / pdf for pdf in args.pdf]
    else:
        targets = list(iter_fixture_pdfs())
    missing = [path for path in targets if not path.exists()]
    if missing:
        for path in missing:
            print(f"[goldens] missing PDF fixture: {path}", file=sys.stderr)
        return 1
    regenerate_goldens(targets, output_dir=args.output, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
