"""Shared helpers for working with golden fixtures."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator

TRUTHY_VALUES = {"1", "true", "yes", "on"}

TESTS_ROOT = Path(__file__).resolve().parent
PDF_FIXTURES_DIR = TESTS_ROOT / "data" / "pdfs"
GOLDEN_ROOT = TESTS_ROOT / "golden"
CURRENT_GOLDEN_DIR = GOLDEN_ROOT / "current"


def iter_fixture_pdfs() -> Iterator[Path]:
    """Return an iterator over known PDF fixtures."""

    yield from sorted(PDF_FIXTURES_DIR.glob("*.pdf"))


def canonicalize_payload(payload: Any) -> Any:
    """Strip non-deterministic fields from a payload so goldens remain stable."""

    if isinstance(payload, dict):
        cleaned: Dict[str, Any] = {}
        for key, value in payload.items():
            if key in {
                "doc_id",
                "extraction_timestamp",
                "generated_at",
                "ingested_at",
                "extraction_id",
            }:
                continue
            if key == "source_file" and isinstance(value, str):
                cleaned[key] = str(Path(value).name)
                continue
            if key == "evidence":
                # Evidence payloads often include bounding boxes and confidence values
                # that can drift between runs. Drop them entirely to keep comparisons stable.
                continue
            cleaned[key] = canonicalize_payload(value)
        return cleaned

    if isinstance(payload, list):
        return [canonicalize_payload(item) for item in payload]

    return payload


def golden_filename(pdf_filename: str) -> str:
    """Return the golden filename for a given PDF filename."""

    if pdf_filename.endswith(".json"):
        return pdf_filename
    if not pdf_filename.endswith(".pdf"):
        raise ValueError(f"Expected .pdf filename, got: {pdf_filename}")
    return f"{pdf_filename}.json"


def load_pdf_golden(pdf_filename: str, *, canonicalize: bool = True) -> Dict[str, Any]:
    """Load a golden payload for the provided PDF filename."""

    CURRENT_GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = CURRENT_GOLDEN_DIR / golden_filename(pdf_filename)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return canonicalize_payload(payload) if canonicalize else payload


def write_pdf_golden(pdf_filename: str, payload: Dict[str, Any], *, directory: Path | None = None) -> Path:
    """Write a golden payload for the provided PDF filename."""

    target_dir = directory or CURRENT_GOLDEN_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / golden_filename(pdf_filename)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def env_truthy(name: str) -> bool:
    """Return True when the named environment variable resolves to a truthy value."""

    raw = os.getenv(name, "")
    return raw.strip().lower() in TRUTHY_VALUES


__all__ = [
    "CURRENT_GOLDEN_DIR",
    "PDF_FIXTURES_DIR",
    "canonicalize_payload",
    "env_truthy",
    "iter_fixture_pdfs",
    "load_pdf_golden",
    "write_pdf_golden",
]
