"""Utility helpers to load textbook-level metadata sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

import yaml

BOOK_META_FILENAMES = (
    "book.yaml",
    "book.yml",
    "book.json",
    "book_meta.yaml",
    "book_meta.yml",
    "book_meta.json",
)


def load_book_metadata(folder: Path) -> Optional[Dict[str, object]]:
    """Load metadata from ``folder`` or its ``pdf`` subfolder."""

    for candidate in _candidate_paths(folder):
        if candidate.exists():
            data = _read_meta_file(candidate)
            if data is not None:
                return data

    pdf_subdir = folder / "pdf"
    if pdf_subdir.exists():
        for candidate in _candidate_paths(pdf_subdir):
            if candidate.exists():
                data = _read_meta_file(candidate)
                if data is not None:
                    return data

    return None


def _candidate_paths(folder: Path):
    for filename in BOOK_META_FILENAMES:
        yield folder / filename


def _read_meta_file(path: Path) -> Optional[Dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return None


__all__ = ["load_book_metadata"]

